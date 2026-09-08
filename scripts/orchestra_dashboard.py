#!/usr/bin/env python3
"""Read-only local dashboard for the frozen Orchestra telemetry ledger.

This module is deliberately a separate consumer of ``orchestra_telemetry``.
It reads and validates the append-only JSONL ledger, folds only the existing
analytics view, and writes an optional rebuildable SQLite cache containing
whitelisted derived fields.  It never calls a telemetry append method and it
never opens a transcript, prompt, response, tool output, or source file.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import http.server
import json
import math
import os
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
from typing import Any, Iterable
import webbrowser

try:  # Direct execution from CODEX_HOME/scripts.
    from orchestra_telemetry import TelemetryStore, _fold_run, _validate_record
except ModuleNotFoundError:  # Import from the repository test package.
    from scripts.orchestra_telemetry import TelemetryStore, _fold_run, _validate_record


DASHBOARD_SCHEMA = "orchestra_dashboard_v1"
DASHBOARD_VERSION = "1.1"
SESSION_LEVEL = "SESSION_LEVEL_V1"
USAGE_QUALITIES = {"EXACT", "PARTIAL", "UNKNOWN"}
SPEED_MODES = {"FAST", "STANDARD", "UNKNOWN"}
SPEED_CERTIFICATION_SOURCE = "LAUNCHER_EXPLICIT"
TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "non_cached_input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "total_tokens",
)
_STATUS_VALUES = ("COMPLETED", "INTERRUPTED", "FAILED", "OPEN", "UNKNOWN")


class DashboardError(RuntimeError):
    """A dashboard error that must not affect telemetry capture."""


def _safe_text(value: Any, *, default: str = "UNKNOWN", max_length: int = 160) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        return default
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return default
    return value


def _safe_label(value: Any) -> str:
    """Accept already-normalized telemetry labels without exposing paths."""

    text = _safe_text(value)
    if text == "UNKNOWN" or "/" in text or "\\" in text:
        return "UNKNOWN"
    return text


def _safe_model(value: Any) -> str:
    return _safe_text(value)


def _safe_timestamp(value: Any) -> str:
    text = _safe_text(value)
    if text == "UNKNOWN":
        return text
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return "UNKNOWN"
    return text


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _nonnegative_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) and value >= 0:
        return float(value)
    return None


def _median(values: Iterable[Any]) -> float | None:
    known = [float(value) for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
    return statistics.median(known) if known else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_stable_ledger(store: TelemetryStore) -> tuple[list[dict[str, Any]], bytes, bool]:
    """Read the ledger without taking the collector's write lock.

    A capture append is atomic, but a dashboard can still observe a final
    incomplete JSONL line while a writer is completing its replace.  Complete
    lines are validated with the canonical validator; an invalid unterminated
    final line is ignored until the next refresh.  Any invalid complete line
    remains a hard error.
    """

    path = store.ledger_path
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise DashboardError("telemetry ledger is not a regular file")
    before = path.read_bytes() if path.exists() else b""
    records: list[dict[str, Any]] = []
    record_ids: set[str] = set()
    chunks = before.splitlines(keepends=True)
    partial_final_line = bool(chunks and not chunks[-1].endswith((b"\n", b"\r")))
    complete_chunks = chunks[:-1] if partial_final_line else chunks
    if partial_final_line:
        candidate = chunks[-1]
        try:
            parsed = json.loads(candidate.decode("utf-8"))
            _validate_record(parsed)
        except Exception:
            # The final chunk is allowed to be partial.  It is not persisted
            # into the derived view until it becomes a valid complete record.
            pass
        else:
            complete_chunks.append(candidate)
            partial_final_line = False
    for line_number, line in enumerate(complete_chunks, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line.decode("utf-8"))
            _validate_record(record)
        except Exception as exc:  # Keep the collector isolated from dashboard errors.
            raise DashboardError(f"ledger validation failed at complete line {line_number}: {exc}") from exc
        record_id = record["record_id"]
        if record_id in record_ids:
            raise DashboardError(f"duplicate record id at complete line {line_number}")
        record_ids.add(record_id)
        records.append(record)
    after = path.read_bytes() if path.exists() else b""
    if before != after:
        raise DashboardError("ledger changed while the dashboard was reading it; rerun the dashboard")
    return records, before, partial_final_line


def _status(run: dict[str, Any]) -> str:
    explicit = run.get("turn_status")
    if explicit == "COMPLETED":
        return "COMPLETED"
    if explicit == "INTERRUPTED":
        return "INTERRUPTED"
    if explicit == "FAILED":
        return "FAILED"
    if explicit == "STARTED":
        return "OPEN"
    if run.get("ended_at_utc") is None:
        return "OPEN"
    result = run.get("result") if isinstance(run.get("result"), dict) else {}
    execution = run.get("execution") if isinstance(run.get("execution"), dict) else {}
    if result.get("completed") is True:
        return "COMPLETED"
    if execution.get("abnormal_termination") is not None:
        return "INTERRUPTED"
    if result.get("completed") is False:
        return "FAILED"
    return "UNKNOWN"


def _worker_summary(orchestra: dict[str, Any]) -> tuple[list[dict[str, Any]], str, int | None]:
    raw_workers = orchestra.get("workers")
    if not isinstance(raw_workers, list) or not raw_workers:
        return [], "UNKNOWN", None
    workers: list[dict[str, Any]] = []
    qualities: list[str] = []
    totals: list[int | None] = []
    for raw in raw_workers:
        if not isinstance(raw, dict):
            continue
        usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
        quality = raw.get("usage_quality") if raw.get("usage_quality") in USAGE_QUALITIES else "UNKNOWN"
        total = _nonnegative_int(usage.get("total_tokens"))
        qualities.append(quality)
        totals.append(total)
        workers.append({
            "worker_id": _safe_label(raw.get("worker_id")),
            "model": _safe_model(raw.get("model")),
            "reasoning_effort": _safe_label(raw.get("reasoning_effort")),
            "status": _safe_label(raw.get("launch_status")),
            "usage_source": _safe_label(raw.get("usage_source")),
            "usage_quality": quality,
            "total_tokens": total if quality == "EXACT" else None,
        })
    if not workers:
        return [], "UNKNOWN", None
    if all(quality == "EXACT" and total is not None for quality, total in zip(qualities, totals)):
        return workers, "EXACT", sum(total for total in totals if total is not None)
    if "PARTIAL" in qualities:
        return workers, "PARTIAL", None
    return workers, "UNKNOWN", None


def _turn_row(run: dict[str, Any]) -> dict[str, Any]:
    task = run.get("task") if isinstance(run.get("task"), dict) else {}
    orchestra = run.get("orchestra") if isinstance(run.get("orchestra"), dict) else {}
    root = orchestra.get("root") if isinstance(orchestra.get("root"), dict) else {}
    usage = run.get("usage") if isinstance(run.get("usage"), dict) else {}
    execution = run.get("execution") if isinstance(run.get("execution"), dict) else {}
    quality = run.get("usage_quality") if run.get("usage_quality") in USAGE_QUALITIES else "UNKNOWN"
    workers, worker_quality, worker_total = _worker_summary(orchestra)
    orchestra_quality = orchestra.get("orchestra_total_quality")
    if orchestra_quality not in USAGE_QUALITIES:
        orchestra_quality = "UNKNOWN"
    orchestra_total = _nonnegative_int(orchestra.get("orchestra_total_tokens"))
    if orchestra_quality != "EXACT":
        orchestra_total = None
    project = _safe_label(task.get("project_label"))
    repo_label = _safe_label(task.get("project_repo_label"))
    branch = _safe_label(task.get("project_branch"))
    worktree_parts = [part for part in (repo_label, branch) if part != "UNKNOWN"]
    worktree = " / ".join(worktree_parts) if worktree_parts else "UNKNOWN"
    speed = orchestra.get("speed_mode") if orchestra.get("speed_mode") in SPEED_MODES else "UNKNOWN"
    speed_source = _safe_label(orchestra.get("speed_mode_source"))
    speed_certified = speed_source == SPEED_CERTIFICATION_SOURCE and speed in {"FAST", "STANDARD"}
    input_tokens = _nonnegative_int(usage.get("input_tokens"))
    cached_input = _nonnegative_int(usage.get("cached_input_tokens"))
    cache_ratio = None
    if quality == "EXACT" and input_tokens is not None and cached_input is not None and input_tokens > 0:
        cache_ratio = cached_input / input_tokens
    return {
        "run_id": _safe_label(run.get("run_id")),
        "turn_id": _safe_label(run.get("turn_id")),
        "session_id": _safe_label(run.get("session_id")),
        "thread_id": _safe_label(run.get("thread_id")),
        "timestamp": _safe_timestamp(run.get("started_at_utc")),
        "ended_at_utc": _safe_timestamp(run.get("ended_at_utc")),
        "project": project,
        "worktree": worktree,
        "model": _safe_model(root.get("model")),
        "reasoning_effort": _safe_label(root.get("reasoning_effort")),
        "reasoning_effort_source": _safe_label(run.get("reasoning_effort_source")),
        "profile": _safe_label(root.get("profile")),
        "speed_mode": speed,
        "speed_mode_source": speed_source,
        "speed_certified": speed_certified,
        "duration_seconds": _nonnegative_number(execution.get("wall_clock_seconds")),
        "root_wall_seconds": _nonnegative_number(execution.get("root_wall_seconds")),
        "worker_wall_seconds": _nonnegative_number(execution.get("worker_wall_seconds")),
        "status": _status(run),
        "turn_status": _safe_label(run.get("turn_status")),
        "measurement_generation": _safe_label(run.get("measurement_generation")),
        "usage_source": _safe_label(run.get("usage_source")),
        "attribution_source": _safe_label(orchestra.get("attribution_source")),
        "attribution_quality": _safe_label(orchestra.get("attribution_quality")),
        "orchestra_mode": _safe_label(orchestra.get("mode")),
        "usage_quality": quality,
        "root_usage_quality": quality,
        "worker_usage_quality": worker_quality,
        "orchestra_usage_quality": orchestra_quality,
        "worker_count": _nonnegative_int(orchestra.get("actual_worker_count")),
        "max_concurrency": _nonnegative_int(orchestra.get("max_concurrency")),
        "workers_started": _nonnegative_int(orchestra.get("workers_started")),
        "workers_completed": _nonnegative_int(orchestra.get("workers_completed")),
        "workers_cancelled": _nonnegative_int(orchestra.get("workers_cancelled")),
        "workers_failed": _nonnegative_int(orchestra.get("workers_failed")),
        "root_model": _safe_model(root.get("model")),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input,
        "cache_write_input_tokens": _nonnegative_int(usage.get("cache_write_input_tokens")),
        "non_cached_input_tokens": _nonnegative_int(usage.get("non_cached_input_tokens")),
        "output_tokens": _nonnegative_int(usage.get("output_tokens")),
        "reasoning_tokens": _nonnegative_int(usage.get("reasoning_tokens")),
        "total_tokens": _nonnegative_int(usage.get("total_tokens")),
        "exact_total_tokens": _nonnegative_int(usage.get("total_tokens")) if quality == "EXACT" else None,
        "root_exact_total_tokens": _nonnegative_int(usage.get("total_tokens")) if quality == "EXACT" else None,
        "worker_exact_total_tokens": worker_total,
        "orchestra_exact_total_tokens": orchestra_total,
        "worker_availability": worker_quality,
        "cache_ratio": cache_ratio,
        "workers": workers,
    }


def _percent(numerator: int, denominator: int) -> float | None:
    return round((100.0 * numerator) / denominator, 2) if denominator else None


def _aggregate_speed(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for mode in ("FAST", "STANDARD"):
        selected = [row for row in rows if row["speed_certified"] and row["speed_mode"] == mode]
        exact_tokens = [row["exact_total_tokens"] for row in selected if row["exact_total_tokens"] is not None]
        durations = [row["duration_seconds"] for row in selected if row["duration_seconds"] is not None]
        result[mode] = {
            "record_count": len(selected),
            "known_duration_count": len(durations),
            "median_duration_seconds": _median(durations),
            "exact_token_count": len(exact_tokens),
            "median_exact_total_tokens": _median(exact_tokens),
        }
    return result


def _build_snapshot(records: list[dict[str, Any]], ledger_bytes: bytes, *, partial_final_line: bool = False) -> dict[str, Any]:
    runs: dict[str, list[dict[str, Any]]] = {}
    manual_count = 0
    for record in records:
        if record.get("record_type") == "legacy_manual_observation":
            manual_count += 1
        elif record.get("run_id"):
            runs.setdefault(str(record["run_id"]), []).append(record)
    synthetic_run_ids = {
        run_id
        for run_id, items in runs.items()
        if any(item.get("record_type") == "usage_observed" and item.get("source_kind") == "SYNTHETIC_FIXTURE" for item in items)
    }
    session_level_count = 0
    rows: list[dict[str, Any]] = []
    fold_errors: list[str] = []
    for run_id, items in runs.items():
        try:
            folded = _fold_run(items)
        except Exception:
            # A malformed individual run cannot take down the dashboard.  The
            # canonical reader still remains fail-closed for ledger corruption.
            fold_errors.append(_safe_label(run_id))
            continue
        if folded.get("measurement_generation") == SESSION_LEVEL:
            session_level_count += 1
            continue
        if run_id in synthetic_run_ids:
            continue
        rows.append(_turn_row(folded))
    rows.sort(key=lambda row: (row["timestamp"] == "UNKNOWN", row["timestamp"], row["run_id"]))

    total_turns = len(rows)
    status_counts = {status: sum(row["status"] == status for row in rows) for status in _STATUS_VALUES}
    exact_usage_count = sum(row["usage_quality"] == "EXACT" for row in rows)
    exact_token_values = [row["exact_total_tokens"] for row in rows if row["exact_total_tokens"] is not None]
    wall_values = [row["duration_seconds"] for row in rows if row["duration_seconds"] is not None]
    projects = {row["project"] for row in rows if row["project"] != "UNKNOWN"}
    root_values = [row["root_exact_total_tokens"] for row in rows if row["root_exact_total_tokens"] is not None]
    worker_values = [row["worker_exact_total_tokens"] for row in rows if row["worker_exact_total_tokens"] is not None]
    orchestra_values = [row["orchestra_exact_total_tokens"] for row in rows if row["orchestra_exact_total_tokens"] is not None]
    lifecycle_counts = {status: status_counts[status] for status in _STATUS_VALUES}
    filters = {
        "projects": sorted({row["project"] for row in rows}),
        "models": sorted({row["model"] for row in rows}),
        "speed_modes": sorted({row["speed_mode"] for row in rows}),
        "statuses": sorted({row["status"] for row in rows}),
        "availability": sorted({"ROOT_EXACT", "WORKER_EXACT", "WORKER_UNKNOWN", "ORCHESTRA_EXACT"} | {
            "ROOT_EXACT" if row["root_usage_quality"] == "EXACT" else "ROOT_UNKNOWN"
            for row in rows
        }),
    }
    return {
        "schema": DASHBOARD_SCHEMA,
        "dashboard_version": DASHBOARD_VERSION,
        "source": {
            "ledger_sha256": hashlib.sha256(ledger_bytes).hexdigest(),
            "ledger_bytes": len(ledger_bytes),
            "record_count": len(records),
            "partial_final_line_ignored": partial_final_line,
        },
        "overview": {
            "total_turns": total_turns,
            "completed": status_counts["COMPLETED"],
            "interrupted": status_counts["INTERRUPTED"],
            "failed": status_counts["FAILED"],
            "open": status_counts["OPEN"],
            "unknown_status": status_counts["UNKNOWN"],
            "exact_usage_coverage": {
                "exact_turns": exact_usage_count,
                "total_turns": total_turns,
                "percent": _percent(exact_usage_count, total_turns),
            },
            "exact_tokens": {
                "total": sum(exact_token_values) if exact_token_values else None,
                "turn_count": len(exact_token_values),
            },
            "wall_time": {
                "total_seconds": sum(wall_values) if wall_values else None,
                "known_turn_count": len(wall_values),
                "percent_known": _percent(len(wall_values), total_turns),
            },
            "project_count": len(projects) if projects else None,
            "root_vs_worker_exact_tokens": {
                "root": sum(root_values) if root_values else None,
                "worker": sum(worker_values) if worker_values else None,
                "orchestra": sum(orchestra_values) if orchestra_values else None,
            },
        },
        "lifecycle": lifecycle_counts,
        "speed_comparison": _aggregate_speed(rows),
        "filters": filters,
        "turns": rows,
        "exclusions": {
            "session_level_runs_excluded": session_level_count,
            "synthetic_runs_excluded": len(synthetic_run_ids),
            "legacy_manual_observations_excluded": manual_count,
            "fold_errors": len(fold_errors),
            "fold_error_run_ids": fold_errors,
            "speed_comparison_source": SPEED_CERTIFICATION_SOURCE,
        },
        "privacy": {
            "raw_transcript_read": False,
            "prompt_response_tool_content_persisted": False,
            "internet_or_cloud_access": False,
        },
    }


def _cache_path(store: TelemetryStore, requested: str | None) -> Path:
    path = Path(requested).expanduser() if requested else store.root / "dashboard-cache.sqlite3"
    try:
        resolved = path.resolve()
        ledger = store.ledger_path.resolve()
    except (OSError, RuntimeError) as exc:
        raise DashboardError(f"cannot resolve cache path: {exc}") from exc
    if resolved == ledger or resolved.name.lower() == ledger.name.lower():
        raise DashboardError("derived cache must not overwrite ledger.jsonl")
    if path.exists() and path.is_symlink():
        raise DashboardError("refusing a symlink dashboard cache")
    return path


def _load_cached(cache: Path, ledger_sha256: str) -> dict[str, Any] | None:
    if not cache.exists() or cache.is_symlink() or not cache.is_file():
        return None
    uri = f"file:{cache.resolve().as_posix()}?mode=ro"
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(uri, uri=True)
        row = connection.execute(
            "SELECT payload FROM dashboard_snapshot WHERE id = 1 AND ledger_sha256 = ? AND dashboard_version = ?",
            (ledger_sha256, DASHBOARD_VERSION),
        ).fetchone()
    except (OSError, sqlite3.DatabaseError):
        return None
    finally:
        if connection is not None:
            connection.close()
    if not row:
        return None
    try:
        payload = json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_cache(cache: Path, snapshot: dict[str, Any]) -> None:
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and cache.is_symlink():
        raise DashboardError("refusing a symlink dashboard cache")
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{cache.stem}.", suffix=".tmp", dir=cache.parent, delete=False) as handle:
            temporary = handle.name
        connection = sqlite3.connect(temporary)
        try:
            connection.execute(
                "CREATE TABLE dashboard_snapshot (id INTEGER PRIMARY KEY CHECK(id = 1), ledger_sha256 TEXT NOT NULL, dashboard_version TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO dashboard_snapshot(id, ledger_sha256, dashboard_version, payload) VALUES (1, ?, ?, ?)",
                (snapshot["source"]["ledger_sha256"], DASHBOARD_VERSION, json.dumps(snapshot, sort_keys=True, separators=(",", ":"))),
            )
            connection.commit()
        finally:
            connection.close()
        os.replace(temporary, cache)
        temporary = None
    except (OSError, sqlite3.DatabaseError) as exc:
        raise DashboardError(f"could not write derived dashboard cache: {exc}") from exc
    finally:
        if temporary:
            try:
                Path(temporary).unlink()
            except OSError:
                pass


def load_snapshot(store: TelemetryStore, *, cache: Path | None, rebuild: bool = False) -> dict[str, Any]:
    records, ledger_bytes, partial_final_line = _read_stable_ledger(store)
    digest = hashlib.sha256(ledger_bytes).hexdigest()
    if cache is not None and not rebuild:
        cached = _load_cached(cache, digest)
        if cached is not None:
            return cached
    snapshot = _build_snapshot(records, ledger_bytes, partial_final_line=partial_final_line)
    if cache is not None:
        _write_cache(cache, snapshot)
    return snapshot


def _json_for_html(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")


def _legacy_build_html(snapshot: dict[str, Any], *, live: bool = False) -> str:
    """Render a self-contained report with no external assets or connections."""

    payload = _json_for_html(snapshot)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Orchestra telemetry dashboard</title>
<style>
:root {{ --bg:#0b1020; --panel:#131b30; --line:#2b3858; --text:#edf2ff; --muted:#9eaccb; --accent:#67e8f9; --green:#72e6a1; --amber:#f6c76b; --red:#ff8b8b; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:linear-gradient(135deg,#0b1020,#111a31); color:var(--text); font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif; }}
main {{ max-width:1500px; margin:0 auto; padding:28px; }} h1 {{ margin:0 0 4px; font-size:28px; }} h2 {{ font-size:17px; margin:0 0 12px; }} h3 {{ font-size:14px; margin:0 0 8px; }} .subtle,.note {{ color:var(--muted); }} .subtle {{ margin:0 0 22px; }}
 .toolbar,.card,.panel {{ background:rgba(19,27,48,.92); border:1px solid var(--line); border-radius:14px; }} .toolbar {{ display:flex; flex-wrap:wrap; gap:12px; padding:14px; margin-bottom:18px; }} label {{ color:var(--muted); display:flex; flex-direction:column; gap:4px; font-size:12px; }} select,input {{ min-width:132px; padding:7px 9px; color:var(--text); background:#0c1428; border:1px solid var(--line); border-radius:7px; }} input[type=checkbox] {{ min-width:0; width:16px; height:16px; }} button {{ align-self:end; padding:8px 12px; color:#06121c; background:var(--accent); border:0; border-radius:7px; cursor:pointer; }} button:disabled {{ opacity:.55; cursor:not-allowed; }} .refresh-meta {{ flex:1 1 280px; align-self:center; color:var(--muted); }} .error {{ color:var(--red); }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:18px; }} .card {{ padding:14px; min-height:92px; }} .card .value {{ display:block; font-size:24px; font-weight:700; margin-top:8px; }} .card .label {{ color:var(--muted); font-size:12px; }}
.grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; margin-bottom:18px; }} .panel {{ padding:15px; min-width:0; }} .wide {{ grid-column:1/-1; }} svg {{ width:100%; height:230px; overflow:visible; }} .axis {{ stroke:var(--line); stroke-width:1; }} .chart-label {{ fill:var(--muted); font-size:11px; }} .bar {{ fill:var(--accent); }} .bar.alt {{ fill:var(--green); }} .dot {{ fill:var(--amber); }} .line {{ fill:none; stroke:var(--accent); stroke-width:2.5; }} .empty {{ color:var(--muted); padding:70px 8px; text-align:center; }}
.table-wrap {{ overflow:auto; max-height:640px; border:1px solid var(--line); border-radius:10px; }} table {{ border-collapse:collapse; width:100%; min-width:1550px; }} th,td {{ padding:8px 9px; border-bottom:1px solid #24304d; text-align:left; white-space:nowrap; }} th {{ position:sticky; top:0; background:#16213b; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em; }} td.num {{ text-align:right; font-variant-numeric:tabular-nums; }} .status-COMPLETED {{ color:var(--green); }} .status-INTERRUPTED,.status-FAILED {{ color:var(--red); }} .status-OPEN {{ color:var(--amber); }} .tag {{ color:var(--accent); }} footer {{ color:var(--muted); margin-top:18px; font-size:12px; }} code {{ color:#d7e5ff; }}
@media(max-width:900px) {{ main {{ padding:15px; }} .grid {{ grid-template-columns:1fr; }} .wide {{ grid-column:auto; }} }}
</style></head><body><main>
<h1>Orchestra telemetry dashboard</h1>
<p class="subtle">Read-only local analytics. Exact token totals use <code>usage_quality=EXACT</code>; certified speed views use <code>speed_mode_source=LAUNCHER_EXPLICIT</code>.</p>
<div id="refreshMeta" class="refresh-meta">Last refreshed: pending · Auto-refresh: ON</div>
<section class="toolbar" aria-label="Filters and refresh controls">
<label>From date<input id="fromDate" type="date"></label><label>To date<input id="toDate" type="date"></label>
<label>Project<select id="project"></select></label><label>Model<select id="model"></select></label><label>Speed<select id="speed"></select></label>
<label>Status<select id="status"></select></label><label>Root/worker availability<select id="availability"></select></label><button id="reset">Reset</button><button id="refreshNow">Refresh</button><label>Auto-refresh<input id="autoRefresh" type="checkbox" checked></label>
</section>
<section id="cards" class="cards"></section>
<section class="grid">
<div class="panel"><h2>Exact total tokens per turn</h2><div id="tokensChart"></div><p class="note">Unknown and non-exact totals are left out of this exact-only chart.</p></div>
<div class="panel"><h2>Duration per turn</h2><div id="durationChart"></div><p class="note">Missing wall time remains UNKNOWN.</p></div>
<div class="panel"><h2>Duration vs exact total tokens</h2><div id="scatterChart"></div><p class="note">Only turns with both known duration and exact total tokens are plotted.</p></div>
<div class="panel"><h2>Cache ratio per turn</h2><div id="cacheChart"></div><p class="note">Cached input divided by input; zero/unknown denominators are not coerced.</p></div>
<div class="panel"><h2>Exact tokens by project</h2><div id="projectChart"></div></div>
<div class="panel"><h2>Root vs worker exact usage</h2><div id="rootWorkerChart"></div><p class="note">No worker observation is UNKNOWN, not zero.</p></div>
<div class="panel"><h2>Certified FAST vs STANDARD</h2><div id="speedChart"></div><p class="note">Only launcher-certified records are compared.</p></div>
<div class="panel"><h2>Lifecycle distribution</h2><div id="lifecycleChart"></div></div>
</section>
<section class="panel wide"><h2>Turn table</h2><div id="table" class="table-wrap"></div></section>
<footer id="footer"></footer>
<script>
let DATA={payload};
const LIVE_MODE={str(live).lower()};
const UNKNOWN='UNKNOWN';
const esc=(v)=>String(v??'').replace(/[&<>'"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}}[c]));
const val=(v)=>v===null||v===undefined||v===''?UNKNOWN:v;
const num=(v)=>v===null||v===undefined?UNKNOWN:(Number.isInteger(v)?v.toLocaleString():Number(v).toLocaleString(undefined,{{maximumFractionDigits:2}}));
const pct=(v)=>v===null||v===undefined?UNKNOWN:Number(v).toFixed(1)+'%';
const setOptions=(id,values)=>{{const el=document.getElementById(id); const old=el.value; el.innerHTML='<option value="">All</option>'+values.map(v=>`<option value="${{esc(v)}}">${{esc(v)}}</option>`).join(''); if(values.includes(old))el.value=old;}};
setOptions('project',DATA.filters.projects); setOptions('model',DATA.filters.models); setOptions('speed',DATA.filters.speed_modes); setOptions('status',DATA.filters.statuses); setOptions('availability',['ROOT_EXACT','WORKER_EXACT','WORKER_UNKNOWN','ORCHESTRA_EXACT','ROOT_UNKNOWN']);
const filters=['project','model','speed','status','availability','fromDate','toDate']; filters.forEach(id=>document.getElementById(id).addEventListener('change',render));
document.getElementById('reset').onclick=()=>{{filters.forEach(id=>document.getElementById(id).value='');render();}};
let refreshTimer=null, refreshInFlight=false, lastRefreshed=new Date().toLocaleString();
function refreshMeta(message='',isError=false){{const el=document.getElementById('refreshMeta');el.className='refresh-meta'+(isError?' error':'');el.textContent=`Last refreshed: ${{lastRefreshed}} · Auto-refresh: ${{document.getElementById('autoRefresh').checked?'ON':'OFF'}}${{message?' · '+message:''}}`;}}
async function refreshData(){{if(!LIVE_MODE||refreshInFlight)return;refreshInFlight=true;refreshMeta('refreshing…');try{{const response=await fetch('/api/snapshot?ts='+Date.now(),{{cache:'no-store'}});if(!response.ok)throw new Error('server returned '+response.status);const next=await response.json();if(!next.schema)throw new Error('invalid dashboard snapshot');DATA=next;setOptions('project',DATA.filters.projects);setOptions('model',DATA.filters.models);setOptions('speed',DATA.filters.speed_modes);setOptions('status',DATA.filters.statuses);render();lastRefreshed=new Date().toLocaleString();refreshMeta();}}catch(error){{refreshMeta('refresh failed: '+error.message,true);}}finally{{refreshInFlight=false;}}}}
function setAutoRefresh(){{if(refreshTimer)clearInterval(refreshTimer);refreshTimer=null;if(document.getElementById('autoRefresh').checked&&LIVE_MODE)refreshTimer=setInterval(refreshData,5000);refreshMeta();}}
document.getElementById('refreshNow').onclick=refreshData;document.getElementById('autoRefresh').onchange=setAutoRefresh;
function filtered(){{const get=id=>document.getElementById(id).value; return DATA.turns.filter(r=>{{if(get('project')&&r.project!==get('project'))return false;if(get('model')&&r.model!==get('model'))return false;if(get('speed')&&r.speed_mode!==get('speed'))return false;if(get('status')&&r.status!==get('status'))return false;const a=get('availability');if(a==='ROOT_EXACT'&&r.root_usage_quality!=='EXACT')return false;if(a==='ROOT_UNKNOWN'&&r.root_usage_quality==='EXACT')return false;if(a==='WORKER_EXACT'&&r.worker_usage_quality!=='EXACT')return false;if(a==='WORKER_UNKNOWN'&&r.worker_usage_quality==='EXACT')return false;if(a==='ORCHESTRA_EXACT'&&r.orchestra_usage_quality!=='EXACT')return false;const from=get('fromDate'),to=get('toDate');if(from&&r.timestamp!==UNKNOWN&&r.timestamp.slice(0,10)<from)return false;if(to&&r.timestamp!==UNKNOWN&&r.timestamp.slice(0,10)>to)return false;return true;}});}}
function derive(rows){{const count=rows.length, exact=rows.filter(r=>r.usage_quality==='EXACT'), durations=rows.map(r=>r.duration_seconds).filter(v=>v!==null), projects=new Set(rows.map(r=>r.project).filter(v=>v!==UNKNOWN));const statuses={{COMPLETED:0,INTERRUPTED:0,FAILED:0,OPEN:0,UNKNOWN:0}};rows.forEach(r=>statuses[r.status]=(statuses[r.status]||0)+1);return {{count,exact,durations,projects,statuses,exactTokens:exact.map(r=>r.exact_total_tokens).filter(v=>v!==null),wall:durations.reduce((a,b)=>a+b,0)}};}}
function card(label,value){{return `<div class="card"><span class="label">${{esc(label)}}</span><span class="value">${{esc(value)}}</span></div>`;}}
function renderCards(rows){{const d=derive(rows), exactPct=d.count?100*d.exact.length/d.count:null;document.getElementById('cards').innerHTML=[card('Total turns',num(d.count)),card('Completed',num(d.statuses.COMPLETED)),card('Interrupted',num(d.statuses.INTERRUPTED)),card('Open',num(d.statuses.OPEN)),card('Exact usage coverage',pct(exactPct)),card('Total exact tokens',d.exactTokens.length?num(d.exactTokens.reduce((a,b)=>a+b,0)):UNKNOWN),card('Known wall time',d.durations.length?num(d.wall)+' s':UNKNOWN),card('Projects',d.projects.size?num(d.projects.size):UNKNOWN)].join('');}}
function svgShell(content){{return `<svg viewBox="0 0 620 230" role="img">${{content}}</svg>`;}}
function empty(id){{document.getElementById(id).innerHTML='<div class="empty">No known values for this selection</div>';}}
function lineChart(id,rows,field,exactOnly=false,ratio=false){{let a=rows.filter(r=>r[field]!==null&&(!exactOnly||r.usage_quality==='EXACT'));if(!a.length)return empty(id);a=a.slice(-80);const vals=a.map(r=>Number(r[field])), max=Math.max(...vals,1),w=580,h=175,pts=vals.map((v,i)=>`${{30+i*(w-30)/Math.max(a.length-1,1)}},${{h-10-(v/max)*(h-20)}}`).join(' ');let dots=vals.map((v,i)=>`<circle class="dot" cx="${{30+i*(w-30)/Math.max(a.length-1,1)}}" cy="${{h-10-(v/max)*(h-20)}}" r="3"><title>${{esc(a[i].turn_id)}}: ${{ratio?(v*100).toFixed(1)+'%':num(v)}}</title></circle>`).join('');document.getElementById(id).innerHTML=svgShell(`<line class="axis" x1="30" y1="${{h-10}}" x2="610" y2="${{h-10}}"/><polyline class="line" points="${{pts}}"/>${{dots}}<text class="chart-label" x="30" y="215">oldest</text><text class="chart-label" x="555" y="215">newest</text><text class="chart-label" x="35" y="20">${{esc(ratio?(max*100).toFixed(0)+'%':num(max))}}</text>`);}}
function scatter(id,rows){{const a=rows.filter(r=>r.duration_seconds!==null&&r.exact_total_tokens!==null);if(!a.length)return empty(id);const maxX=Math.max(...a.map(r=>r.duration_seconds),1),maxY=Math.max(...a.map(r=>r.exact_total_tokens),1);const dots=a.slice(-120).map(r=>`<circle class="dot" cx="${{35+(r.duration_seconds/maxX)*550}}" cy="${{190-(r.exact_total_tokens/maxY)*165}}" r="4"><title>${{esc(r.turn_id)}}: ${{num(r.duration_seconds)}} s / ${{num(r.exact_total_tokens)}} tokens</title></circle>`).join('');document.getElementById(id).innerHTML=svgShell(`<line class="axis" x1="35" y1="190" x2="600" y2="190"/><line class="axis" x1="35" y1="25" x2="35" y2="190"/>${{dots}}<text class="chart-label" x="40" y="215">duration</text><text class="chart-label" x="40" y="18">tokens</text>`);}}
function bars(id,items,formatter=(v)=>num(v)){{const a=items.filter(x=>x[1]!==null&&x[1]!==undefined);if(!a.length)return empty(id);const max=Math.max(...a.map(x=>x[1]),1),bw=Math.min(72,520/a.length);const b=a.map((x,i)=>{{const height=(x[1]/max)*155,xpos=45+i*(540/a.length);return `<rect class="bar ${{i%2?'alt':''}}" x="${{xpos}}" y="${{185-height}}" width="${{bw}}" height="${{height}}"><title>${{esc(x[0])}}: ${{esc(formatter(x[1]))}}</title></rect><text class="chart-label" transform="translate(${{xpos+bw/2}},205) rotate(-35)" text-anchor="end">${{esc(x[0])}}</text>`;}}).join('');document.getElementById(id).innerHTML=svgShell(`<line class="axis" x1="35" y1="185" x2="605" y2="185"/>${{b}}`);}}
function renderCharts(rows){{lineChart('tokensChart',rows,'exact_total_tokens',true);lineChart('durationChart',rows,'duration_seconds');lineChart('cacheChart',rows,'cache_ratio',true,true);scatter('scatterChart',rows);const proj={{}};rows.forEach(r=>{{if(r.exact_total_tokens!==null)proj[r.project]=(proj[r.project]||0)+r.exact_total_tokens;}});bars('projectChart',Object.entries(proj).sort((a,b)=>b[1]-a[1]).slice(0,12));const exactRoot=rows.map(r=>r.root_exact_total_tokens).filter(v=>v!==null),exactWorker=rows.map(r=>r.worker_exact_total_tokens).filter(v=>v!==null),exactOrch=rows.map(r=>r.orchestra_exact_total_tokens).filter(v=>v!==null);bars('rootWorkerChart',[['ROOT',exactRoot.length?exactRoot.reduce((a,b)=>a+b,0):null],['WORKER',exactWorker.length?exactWorker.reduce((a,b)=>a+b,0):null],['ORCHESTRA',exactOrch.length?exactOrch.reduce((a,b)=>a+b,0):null]]);const speed=['FAST','STANDARD'].map(m=>[m,rows.filter(r=>r.speed_certified&&r.speed_mode===m).length]);bars('speedChart',speed,(v)=>v+' certified turns');bars('lifecycleChart',Object.entries(derive(rows).statuses));}}
function renderTable(rows){{if(!rows.length)return document.getElementById('table').innerHTML='<div class="empty">No turns match the filters</div>';const headers=['Timestamp','Turn ID','Project / worktree','Model','Speed','Duration (s)','Input','Cached','Non-cached','Output','Reasoning','Total','Root exact','Worker exact','Orchestra exact','Usage','Lifecycle'];const body=rows.slice().reverse().map(r=>`<tr><td>${{esc(r.timestamp)}}</td><td><code>${{esc(r.turn_id)}}</code></td><td>${{esc(r.project)}} / ${{esc(r.worktree)}}</td><td>${{esc(r.model)}}</td><td class="${{r.speed_certified?'tag':''}}">${{esc(r.speed_mode+(r.speed_certified?' (certified)':''))}}</td><td class="num">${{esc(num(r.duration_seconds))}}</td><td class="num">${{esc(num(r.input_tokens))}}</td><td class="num">${{esc(num(r.cached_input_tokens))}}</td><td class="num">${{esc(num(r.non_cached_input_tokens))}}</td><td class="num">${{esc(num(r.output_tokens))}}</td><td class="num">${{esc(num(r.reasoning_tokens))}}</td><td class="num">${{esc(num(r.total_tokens))}}</td><td class="num">${{esc(num(r.root_exact_total_tokens))}}</td><td class="num">${{esc(num(r.worker_exact_total_tokens))}}</td><td class="num">${{esc(num(r.orchestra_exact_total_tokens))}}</td><td>${{esc(r.usage_quality)}}</td><td class="status-${{esc(r.status)}}">${{esc(r.status)}}</td></tr>`).join('');document.getElementById('table').innerHTML=`<table><thead><tr>${{headers.map(h=>`<th>${{esc(h)}}</th>`).join('')}}</tr></thead><tbody>${{body}}</tbody></table>`;}}
function render(){{const rows=filtered();renderCards(rows);renderCharts(rows);renderTable(rows);const e=DATA.exclusions;document.getElementById('footer').innerHTML=`Ledger SHA-256 <code>${{esc(DATA.source.ledger_sha256)}}</code> · ${{num(DATA.source.record_count)}} source records · ${{num(e.session_level_runs_excluded)}} session-level runs excluded · ${{num(e.synthetic_runs_excluded)}} synthetic runs excluded · ${{num(e.legacy_manual_observations_excluded)}} legacy manual observations excluded · ${{DATA.source.partial_final_line_ignored?'partial final line ignored until complete · ':''}}no transcript/prompt/tool content read.`;}}
if(!LIVE_MODE){{document.getElementById('refreshNow').disabled=true;document.getElementById('autoRefresh').disabled=true;refreshMeta('static report');}}else{{refreshMeta();setAutoRefresh();refreshData();}}
render();
</script></main></body></html>'''


def build_html(snapshot: dict[str, Any], *, live: bool = False) -> str:
    """Render the polished single-file dashboard without adding data semantics."""

    payload = _json_for_html(snapshot)
    template = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Orchestra telemetry dashboard</title>
<style>
:root {
  --bg: #080b10;
  --bg-soft: #0d1219;
  --panel: #111821;
  --panel-strong: #151f2b;
  --panel-hover: #192536;
  --line: #23303d;
  --line-strong: #304254;
  --text: #edf3f8;
  --muted: #93a2b1;
  --faint: #607180;
  --accent: #70c9ff;
  --accent-soft: rgba(112, 201, 255, .13);
  --green: #6ee7ad;
  --green-soft: rgba(110, 231, 173, .12);
  --amber: #f3c56b;
  --amber-soft: rgba(243, 197, 107, .12);
  --red: #ff8c9a;
  --red-soft: rgba(255, 140, 154, .12);
  --purple: #b5a2ff;
  --radius: 12px;
}
* { box-sizing: border-box; }
html { background: var(--bg); }
body {
  margin: 0;
  color: var(--text);
  background:
    radial-gradient(circle at 78% -10%, rgba(70, 134, 182, .13), transparent 34rem),
    linear-gradient(180deg, #0a0e14 0%, var(--bg) 36rem);
  font: 13px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
}
button, input, select { font: inherit; }
button { cursor: pointer; }
.app-shell { max-width: 1880px; margin: 0 auto; padding: 22px 28px 42px; }
.topbar { display: flex; justify-content: space-between; gap: 26px; align-items: flex-start; margin-bottom: 22px; }
.kicker { color: var(--accent); font-size: 10px; font-weight: 700; letter-spacing: .16em; text-transform: uppercase; }
h1 { margin: 5px 0 4px; font-size: 29px; line-height: 1.05; letter-spacing: -.045em; }
h1 span { color: var(--accent); }
.subtitle { color: var(--muted); margin: 0; max-width: 680px; }
.live-cluster { display: flex; align-items: center; gap: 8px; color: var(--muted); white-space: nowrap; padding: 9px 12px; background: rgba(17, 24, 33, .78); border: 1px solid var(--line); border-radius: 9px; }
.live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 4px var(--green-soft); }
.live-cluster strong { color: var(--text); font-size: 12px; }
.tabs { display: flex; align-items: center; gap: 3px; border-bottom: 1px solid var(--line); margin-bottom: 13px; }
.tab { border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--muted); padding: 11px 15px 10px; font-size: 11px; font-weight: 750; letter-spacing: .09em; text-transform: uppercase; }
.tab:hover { color: var(--text); }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.filterbar { position: sticky; top: 0; z-index: 20; display: flex; flex-wrap: wrap; align-items: end; gap: 9px 14px; padding: 10px 12px; margin-bottom: 18px; background: rgba(13, 18, 25, .92); border: 1px solid var(--line); border-radius: 10px; backdrop-filter: blur(12px); }
.filter-group { display: flex; align-items: center; gap: 7px; }
.filter-label { color: var(--faint); font-size: 10px; font-weight: 750; letter-spacing: .09em; text-transform: uppercase; }
.segmented { display: flex; gap: 2px; padding: 2px; background: #0a0f15; border: 1px solid var(--line); border-radius: 7px; }
.segmented button { border: 0; border-radius: 5px; padding: 5px 9px; color: var(--muted); background: transparent; font-size: 11px; }
.segmented button.active { color: var(--text); background: var(--panel-hover); box-shadow: inset 0 0 0 1px var(--line-strong); }
.filterbar select, .filterbar input[type="search"] { min-width: 122px; height: 29px; color: var(--text); background: #0a0f15; border: 1px solid var(--line); border-radius: 6px; padding: 5px 8px; outline: none; }
.filterbar input[type="search"] { width: 185px; min-width: 150px; }
.filterbar select:focus, .filterbar input:focus { border-color: var(--accent); }
.search-wrap { position: relative; }
.search-wrap span { position: absolute; left: 8px; top: 6px; color: var(--faint); }
.search-wrap input { padding-left: 25px !important; }
.filter-spacer { flex: 1; min-width: 14px; }
.check { display: flex; align-items: center; gap: 6px; color: var(--muted); font-size: 11px; white-space: nowrap; }
.check input { accent-color: var(--accent); }
.action { height: 29px; border: 1px solid var(--line-strong); border-radius: 6px; color: var(--text); background: var(--panel-strong); padding: 4px 10px; font-size: 11px; }
.action:hover { background: var(--panel-hover); border-color: var(--accent); }
.action.primary { color: #06111a; background: var(--accent); border-color: var(--accent); font-weight: 750; }
.refresh-state { color: var(--faint); font-size: 11px; white-space: nowrap; }
.view { display: none; }
.view.active { display: block; }
.section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; margin: 23px 0 10px; }
.section-head h2 { margin: 0; font-size: 14px; letter-spacing: -.01em; }
.section-head p { margin: 0; color: var(--muted); font-size: 11px; }
.hero-panel { display: grid; grid-template-columns: minmax(310px, 1.55fr) repeat(5, minmax(112px, .65fr)); gap: 0; min-height: 174px; overflow: hidden; background: linear-gradient(120deg, #15283a 0%, #111b26 52%, #111821 100%); border: 1px solid #2b5069; border-radius: var(--radius); box-shadow: 0 16px 36px rgba(0, 0, 0, .2); }
.hero-main { padding: 23px 25px; border-right: 1px solid rgba(112, 201, 255, .16); }
.hero-eyebrow { color: var(--accent); font-size: 10px; font-weight: 800; letter-spacing: .15em; text-transform: uppercase; }
.hero-title { margin: 11px 0 3px; font-size: 22px; font-weight: 760; letter-spacing: -.035em; }
.hero-subtitle { color: var(--muted); font-size: 12px; }
.hero-badges { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 14px; }
.hero-meta { margin-top: 13px; color: var(--faint); font-size: 11px; }
.hero-meta strong { color: var(--text); font-weight: 600; }
.hero-stat { display: flex; flex-direction: column; justify-content: center; gap: 6px; padding: 17px 15px; border-right: 1px solid rgba(255, 255, 255, .06); }
.hero-stat:last-child { border-right: 0; }
.hero-stat .label { color: var(--muted); font-size: 10px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.hero-stat .value { font-size: 20px; font-weight: 750; letter-spacing: -.035em; font-variant-numeric: tabular-nums; }
.hero-stat .hint { color: var(--faint); font-size: 10px; }
.metric-grid { display: grid; grid-template-columns: repeat(6, minmax(130px, 1fr)); gap: 10px; margin-top: 12px; }
.metric-card { padding: 14px 15px; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; }
.metric-card .label { color: var(--muted); font-size: 10px; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
.metric-card .value { display: block; margin-top: 7px; font-size: 21px; font-weight: 750; letter-spacing: -.035em; font-variant-numeric: tabular-nums; }
.metric-card .detail { display: block; min-height: 16px; margin-top: 4px; color: var(--faint); font-size: 10px; }
.metric-card.accent { border-color: rgba(112, 201, 255, .38); background: linear-gradient(145deg, rgba(112, 201, 255, .11), var(--panel)); }
.metric-card.good .value { color: var(--green); }
.metric-card.warn .value { color: var(--amber); }
.metric-card.alert .value { color: var(--red); }
.chart-grid { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(320px, 1fr); gap: 12px; }
.chart-grid.secondary { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-top: 12px; }
.panel { min-width: 0; background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); }
.chart-panel { min-height: 304px; padding: 16px 17px 11px; }
.chart-panel.large { min-height: 330px; }
.panel-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 8px; }
.panel-head h3 { margin: 0; font-size: 13px; letter-spacing: -.01em; }
.panel-head p { margin: 3px 0 0; color: var(--muted); font-size: 11px; }
.chart-meta { color: var(--faint); font-size: 10px; white-space: nowrap; }
.chart { height: 244px; }
.chart svg { display: block; width: 100%; height: 100%; overflow: visible; }
.chart-gridline { stroke: #22303d; stroke-width: 1; stroke-dasharray: 3 5; }
.chart-axis { stroke: #324352; stroke-width: 1; }
.chart-label { fill: #778897; font-size: 10px; }
.chart-line { fill: none; stroke: var(--accent); stroke-width: 2.6; stroke-linecap: round; stroke-linejoin: round; }
.chart-area { fill: url(#areaFill); opacity: .72; }
.chart-point { fill: var(--accent); stroke: #d6f2ff; stroke-width: 1.4; }
.chart-point.amber { fill: var(--amber); }
.chart-point.green { fill: var(--green); }
.empty-chart { display: grid; place-items: center; height: 215px; padding: 18px; text-align: center; color: var(--muted); border: 1px dashed var(--line-strong); border-radius: 8px; background: rgba(8, 11, 16, .27); }
.empty-chart strong { display: block; color: var(--text); font-size: 12px; }
.empty-chart span { display: block; max-width: 330px; margin-top: 5px; color: var(--faint); font-size: 11px; }
.view-toolbar { display: flex; align-items: center; gap: 12px; margin: 0 0 10px; color: var(--muted); font-size: 11px; }
.view-toolbar strong { color: var(--text); }
.table-panel { overflow: hidden; }
.table-scroll { overflow: auto; }
table { width: 100%; border-collapse: collapse; min-width: 1040px; }
th, td { padding: 11px 12px; border-bottom: 1px solid #1d2934; text-align: left; white-space: nowrap; }
th { position: sticky; top: 0; z-index: 1; color: var(--faint); background: #131d28; font-size: 10px; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
th button { padding: 0; border: 0; color: inherit; background: transparent; font-size: inherit; font-weight: inherit; letter-spacing: inherit; text-transform: inherit; }
th button:hover { color: var(--accent); }
td { color: #c6d1da; font-variant-numeric: tabular-nums; }
tbody tr { transition: background .12s ease; }
tbody tr:hover, tbody tr:focus { outline: none; background: var(--panel-hover); }
td.num { text-align: right; }
.cell-title { color: var(--text); font-weight: 600; }
.cell-sub { margin-top: 2px; color: var(--faint); font-size: 10px; }
.badge { display: inline-flex; align-items: center; gap: 5px; padding: 3px 7px; border: 1px solid var(--line-strong); border-radius: 5px; color: var(--muted); background: rgba(255, 255, 255, .025); font-size: 10px; font-weight: 750; letter-spacing: .04em; }
.badge-speed { color: var(--accent); border-color: rgba(112, 201, 255, .32); background: var(--accent-soft); }
.badge-fast { color: var(--green); border-color: rgba(110, 231, 173, .3); background: var(--green-soft); }
.badge-status-completed { color: var(--green); border-color: rgba(110, 231, 173, .3); background: var(--green-soft); }
.badge-status-interrupted, .badge-status-failed { color: var(--red); border-color: rgba(255, 140, 154, .3); background: var(--red-soft); }
.badge-status-open { color: var(--amber); border-color: rgba(243, 197, 107, .3); background: var(--amber-soft); }
.pagination { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 13px; color: var(--muted); font-size: 11px; }
.pagination-actions { display: flex; gap: 5px; }
.pagination button { border: 1px solid var(--line); border-radius: 5px; color: var(--muted); background: var(--panel-strong); padding: 5px 8px; }
.pagination button:disabled { opacity: .4; cursor: default; }
.orchestra-layout { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(320px, .8fr); gap: 12px; }
.orchestra-panel { padding: 17px; }
.turn-select { width: 100%; height: 33px; color: var(--text); background: #0a0f15; border: 1px solid var(--line); border-radius: 6px; padding: 5px 8px; }
.timeline { margin-top: 20px; }
.timeline-row { display: grid; grid-template-columns: 104px minmax(0, 1fr) 116px; align-items: center; gap: 10px; margin: 11px 0; }
.timeline-label { overflow: hidden; color: var(--muted); font-size: 11px; text-overflow: ellipsis; }
.timeline-track { position: relative; height: 21px; overflow: hidden; border: 1px solid var(--line); border-radius: 4px; background: #0a0f15; }
.timeline-bar { height: 100%; min-width: 5px; border-radius: 3px; background: linear-gradient(90deg, #5bb9ee, #a6e3ff); }
.timeline-bar.worker { background: linear-gradient(90deg, #8876dc, #c2b5ff); }
.timeline-track.unknown { display: flex; align-items: center; padding: 0 8px; border-style: dashed; color: var(--faint); font-size: 10px; }
.timeline-value { color: var(--faint); font-size: 10px; text-align: right; }
.timeline-note { margin: 16px 0 0; padding: 9px 10px; border-left: 2px solid var(--amber); color: var(--muted); background: var(--amber-soft); font-size: 11px; }
.small-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 9px; margin-top: 14px; }
.small-metric { padding: 11px 12px; background: var(--bg-soft); border: 1px solid var(--line); border-radius: 8px; }
.small-metric span { display: block; color: var(--faint); font-size: 10px; text-transform: uppercase; letter-spacing: .06em; }
.small-metric strong { display: block; margin-top: 4px; font-size: 16px; }
.subgrid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 12px; }
.benchmark-grid, .quality-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 11px; }
.benchmark-card, .quality-card { padding: 16px; background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); }
.benchmark-card h3, .quality-card h3 { margin: 0; font-size: 13px; }
.benchmark-card .sample { margin-top: 4px; color: var(--muted); font-size: 11px; }
.benchmark-metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 18px; }
.benchmark-metrics span { display: block; color: var(--faint); font-size: 10px; }
.benchmark-metrics strong { display: block; margin-top: 3px; font-size: 17px; }
.benchmark-empty { margin-top: 20px; padding: 11px 12px; border: 1px dashed var(--line-strong); border-radius: 7px; color: var(--muted); font-size: 11px; }
.quality-card .value { display: block; margin-top: 8px; font-size: 23px; font-weight: 760; }
.quality-card .note { margin: 3px 0 0; color: var(--faint); font-size: 10px; }
.quality-card .value.good { color: var(--green); }
.quality-card .value.warn { color: var(--amber); }
.quality-card .value.alert { color: var(--red); }
.quality-list { margin-top: 12px; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
.quality-row { display: flex; justify-content: space-between; gap: 20px; padding: 11px 13px; border-bottom: 1px solid var(--line); }
.quality-row:last-child { border-bottom: 0; }
.quality-row span { color: var(--muted); }
.quality-row strong { color: var(--text); font-variant-numeric: tabular-nums; }
.privacy-note { margin-top: 12px; padding: 11px 13px; color: var(--muted); background: var(--accent-soft); border: 1px solid rgba(112, 201, 255, .22); border-radius: 8px; font-size: 11px; }
.drawer-scrim { display: none; position: fixed; inset: 0; z-index: 39; background: rgba(0, 0, 0, .46); }
.drawer-scrim.open { display: block; }
.drawer { position: fixed; z-index: 40; top: 0; right: 0; bottom: 0; width: min(560px, 94vw); overflow: auto; padding: 22px; background: #0e151e; border-left: 1px solid var(--line-strong); box-shadow: -18px 0 50px rgba(0, 0, 0, .35); transform: translateX(102%); transition: transform .18s ease; }
.drawer.open { transform: translateX(0); }
.drawer-head { display: flex; justify-content: space-between; gap: 14px; align-items: flex-start; }
.drawer-close { width: 28px; height: 28px; border: 1px solid var(--line); border-radius: 6px; color: var(--muted); background: var(--panel); }
.drawer h2 { margin: 4px 0 4px; font-size: 20px; letter-spacing: -.03em; }
.drawer-sub { color: var(--muted); font-size: 11px; }
.drawer-section { margin-top: 23px; }
.drawer-section h3 { margin: 0 0 10px; color: var(--faint); font-size: 10px; letter-spacing: .1em; text-transform: uppercase; }
.token-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.token-cell { padding: 10px 11px; background: var(--panel); border: 1px solid var(--line); border-radius: 7px; }
.token-cell span { display: block; color: var(--faint); font-size: 10px; }
.token-cell strong { display: block; margin-top: 3px; color: var(--text); font-size: 15px; font-variant-numeric: tabular-nums; }
.detail-list { border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.detail-row { display: grid; grid-template-columns: 148px minmax(0, 1fr); gap: 10px; padding: 9px 11px; border-bottom: 1px solid var(--line); }
.detail-row:last-child { border-bottom: 0; }
.detail-row span { color: var(--faint); font-size: 11px; }
.detail-row strong { overflow: hidden; color: var(--text); font-size: 11px; font-weight: 550; text-overflow: ellipsis; }
.worker-list { display: grid; gap: 7px; }
.worker-row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 10px; align-items: center; padding: 9px 10px; background: var(--panel); border: 1px solid var(--line); border-radius: 7px; }
.worker-row .worker-name { overflow: hidden; color: var(--text); text-overflow: ellipsis; }
.worker-row small { color: var(--muted); }
.footer-note { margin-top: 20px; color: var(--faint); font-size: 10px; }
@media (max-width: 1180px) {
  .hero-panel { grid-template-columns: minmax(280px, 1.4fr) repeat(3, 1fr); }
  .hero-stat:nth-last-child(-n+2) { border-top: 1px solid rgba(255, 255, 255, .06); }
  .metric-grid { grid-template-columns: repeat(3, 1fr); }
  .benchmark-grid, .quality-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 820px) {
  .app-shell { padding: 16px 13px 30px; }
  .topbar { display: block; }
  .live-cluster { display: inline-flex; margin-top: 15px; }
  .hero-panel, .chart-grid, .chart-grid.secondary, .orchestra-layout, .subgrid { grid-template-columns: 1fr; }
  .hero-main { border-right: 0; border-bottom: 1px solid rgba(112, 201, 255, .16); }
  .hero-stat { min-height: 82px; border-top: 1px solid rgba(255, 255, 255, .06); }
  .metric-grid { grid-template-columns: repeat(2, 1fr); }
  .filterbar { position: static; align-items: stretch; }
  .filter-spacer { display: none; }
  .benchmark-grid, .quality-grid { grid-template-columns: 1fr; }
  .small-grid { grid-template-columns: 1fr 1fr; }
}
</style>
</head>
<body>
<div class="app-shell">
  <header class="topbar">
    <div>
      <div class="kicker">Local observability · read-only</div>
      <h1>Orchestra <span>Telemetry</span></h1>
      <p class="subtitle">A calm, evidence-first view of turn lifecycle, usage quality, and orchestration cost.</p>
    </div>
    <div class="live-cluster"><span class="live-dot"></span><strong>Live ledger</strong><span id="updatedText">Last updated: pending</span></div>
  </header>
  <nav class="tabs" aria-label="Dashboard views">
    <button class="tab active" data-nav-view="overview">Overview</button>
    <button class="tab" data-nav-view="turns">Turns</button>
    <button class="tab" data-nav-view="orchestra">Orchestra</button>
    <button class="tab" data-nav-view="benchmarks">Benchmarks</button>
    <button class="tab" data-nav-view="quality">Data quality</button>
  </nav>
  <section class="filterbar" aria-label="Dashboard filters">
    <div class="filter-group"><span class="filter-label">Period</span><div class="segmented">
      <button data-period="today">Today</button><button data-period="7d">7D</button><button data-period="30d">30D</button><button class="active" data-period="all">All</button>
    </div></div>
    <div class="filter-group"><span class="filter-label">Project</span><select id="projectFilter"><option value="">All</option></select></div>
    <div class="filter-group"><span class="filter-label">Model</span><select id="modelFilter"><option value="">All</option></select></div>
    <div class="filter-group"><span class="filter-label">Speed</span><select id="speedFilter"><option value="">All</option></select></div>
    <div class="filter-group"><span class="filter-label">Status</span><select id="statusFilter"><option value="">All</option></select></div>
    <div class="filter-group"><span class="filter-label">Workers</span><select id="workersFilter"><option value="">All</option><option value="has">Has workers</option><option value="none">No workers</option></select></div>
    <div class="filter-group search-wrap"><span>⌕</span><input id="searchFilter" type="search" placeholder="Search project or model"></div>
    <label class="check"><input id="exactFilter" type="checkbox"> Exact only</label>
    <div class="filter-spacer"></div>
    <button id="refreshNow" class="action primary">Refresh</button>
    <label class="check"><input id="autoRefresh" type="checkbox" checked> Auto refresh</label>
    <span id="refreshState" class="refresh-state">ON · 5s</span>
  </section>
  <main>
    <section id="overviewView" class="view active"></section>
    <section id="turnsView" class="view"></section>
    <section id="orchestraView" class="view"></section>
    <section id="benchmarksView" class="view"></section>
    <section id="qualityView" class="view"></section>
  </main>
</div>
<div id="drawerScrim" class="drawer-scrim"></div>
<aside id="detailDrawer" class="drawer" aria-hidden="true"></aside>
<script>
let DATA = __PAYLOAD__;
const LIVE_MODE = __LIVE_MODE__;
const UNKNOWN = "UNKNOWN";
const PAGE_SIZE = 14;
const STATE = {
  view: "overview", period: "all", project: "", model: "", speed: "", status: "",
  workers: "", query: "", exact: false, sort: "timestamp", direction: -1,
  page: 1, drawer: null, orchestra: null, updated: null
};
const URL_STATE = new URLSearchParams(location.search);
if (["overview", "turns", "orchestra", "benchmarks", "quality"].includes(URL_STATE.get("view"))) STATE.view = URL_STATE.get("view");
if (URL_STATE.get("turn")) STATE.drawer = URL_STATE.get("turn");
if (URL_STATE.get("orchestra")) STATE.orchestra = URL_STATE.get("orchestra");
const $ = id => document.getElementById(id);
const esc = value => String(value == null ? "" : value).replace(/[&<>'"]/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", "'":"&#39;", '"':"&quot;" }[c]));
const isKnown = value => value !== null && value !== undefined && value !== "" && value !== UNKNOWN;
const num = value => isKnown(value) ? Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 }) : UNKNOWN;
const compact = value => {
  if (!isKnown(value)) return UNKNOWN;
  const n = Number(value), a = Math.abs(n);
  if (a >= 1000000000) return (n / 1000000000).toFixed(a >= 10000000000 ? 1 : 2).replace(/\.0+$/, "") + "B";
  if (a >= 1000000) return (n / 1000000).toFixed(a >= 10000000 ? 1 : 2).replace(/\.0+$/, "") + "M";
  if (a >= 1000) return (n / 1000).toFixed(a >= 100000 ? 0 : 1).replace(/\.0+$/, "") + "K";
  return num(n);
};
const percent = value => isKnown(value) ? Number(value).toFixed(1) + "%" : UNKNOWN;
const ratioPercent = value => isKnown(value) ? (Number(value) * 100).toFixed(1) + "%" : UNKNOWN;
const duration = value => {
  if (!isKnown(value)) return UNKNOWN;
  const s = Math.max(0, Math.round(Number(value)));
  if (s < 60) return s + "s";
  if (s < 3600) return Math.floor(s / 60) + "m " + String(s % 60).padStart(2, "0") + "s";
  return Math.floor(s / 3600) + "h " + String(Math.floor((s % 3600) / 60)).padStart(2, "0") + "m";
};
const dateKey = value => {
  if (!isKnown(value)) return UNKNOWN;
  const d = new Date(value);
  return isNaN(d.getTime()) ? UNKNOWN : d.toISOString().slice(0, 10);
};
const dateLabel = value => {
  if (!isKnown(value)) return UNKNOWN;
  const d = new Date(value);
  return isNaN(d.getTime()) ? UNKNOWN : d.toLocaleString([], { month:"short", day:"numeric", hour:"2-digit", minute:"2-digit" });
};
const timestamp = value => isKnown(value) ? Date.parse(value) || 0 : 0;
const statusBadge = value => '<span class="badge badge-status-' + String(value || "UNKNOWN").toLowerCase() + '">' + esc(value || UNKNOWN) + '</span>';
const speedBadge = row => {
  const speed = row.speed_mode || UNKNOWN;
  const cls = row.speed_certified ? (speed === "FAST" ? "badge-fast" : "badge-speed") : "";
  return '<span class="badge ' + cls + '">' + esc(speed) + (row.speed_certified ? " · certified" : "") + '</span>';
};
const emptyChart = (id, title, detail) => {
  const el = $(id);
  if (el) el.innerHTML = '<div class="empty-chart"><div><strong>' + esc(title) + '</strong><span>' + esc(detail) + '</span></div></div>';
};
const median = values => {
  const a = values.filter(isKnown).map(Number).sort((x, y) => x - y);
  if (!a.length) return null;
  const m = Math.floor(a.length / 2);
  return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
};
const latest = rows => rows.slice().sort((a, b) => timestamp(b.timestamp) - timestamp(a.timestamp))[0] || null;
const rowById = id => DATA.turns.find(row => row.run_id === id) || null;
function setOptions(id, values) {
  const el = $(id), old = el.value;
  el.innerHTML = '<option value="">All</option>' + values.map(v => '<option value="' + esc(v) + '">' + esc(v) + '</option>').join("");
  if (values.includes(old)) el.value = old;
}
function periodAllows(row) {
  if (STATE.period === "all" || !isKnown(row.timestamp)) return true;
  const stamp = timestamp(row.timestamp);
  if (!stamp) return false;
  if (STATE.period === "today") return dateKey(row.timestamp) === dateKey(new Date().toISOString());
  const days = STATE.period === "7d" ? 7 : 30;
  return stamp >= Date.now() - days * 86400000;
}
function filteredRows(ignorePeriod = false) {
  const query = STATE.query.trim().toLowerCase();
  return DATA.turns.filter(row => {
    if (!ignorePeriod && !periodAllows(row)) return false;
    if (STATE.project && row.project !== STATE.project) return false;
    if (STATE.model && row.model !== STATE.model) return false;
    if (STATE.speed && row.speed_mode !== STATE.speed) return false;
    if (STATE.status && row.status !== STATE.status) return false;
    if (STATE.workers === "has" && !(row.worker_count > 0)) return false;
    if (STATE.workers === "none" && row.worker_count > 0) return false;
    if (STATE.exact && row.usage_quality !== "EXACT") return false;
    if (query && !(String(row.project).toLowerCase().includes(query) || String(row.model).toLowerCase().includes(query) || String(row.worktree).toLowerCase().includes(query))) return false;
    return true;
  });
}
function valueForSort(row, key) {
  const value = row[key];
  if (key === "timestamp") return timestamp(value);
  if (value === null || value === undefined || value === UNKNOWN) return -Infinity;
  if (typeof value === "number") return value;
  return String(value).toLowerCase();
}
function sortedRows(rows) {
  return rows.slice().sort((a, b) => {
    const av = valueForSort(a, STATE.sort), bv = valueForSort(b, STATE.sort);
    if (av < bv) return -1 * STATE.direction;
    if (av > bv) return 1 * STATE.direction;
    return timestamp(b.timestamp) - timestamp(a.timestamp);
  });
}
function metricCard(label, value, detail, cls) {
  return '<div class="metric-card ' + (cls || "") + '"><span class="label">' + esc(label) + '</span><span class="value">' + esc(value) + '</span><span class="detail">' + esc(detail || "") + '</span></div>';
}
function smallMetric(label, value) {
  return '<div class="small-metric"><span>' + esc(label) + '</span><strong>' + esc(value) + '</strong></div>';
}
function chartPanel(title, subtitle, id, extra) {
  return '<article class="panel chart-panel ' + (extra || "") + '"><div class="panel-head"><div><h3>' + esc(title) + '</h3><p>' + esc(subtitle) + '</p></div><span id="' + id + 'Meta" class="chart-meta"></span></div><div id="' + id + '" class="chart"></div></article>';
}
function lineChart(id, rows, field, exactOnly, formatter, pointClass) {
  let data = rows.filter(row => isKnown(row[field]) && (!exactOnly || row.usage_quality === "EXACT")).slice(-90);
  if (!data.length) {
    emptyChart(id, exactOnly ? "No exact observations in this selection" : "No valid observations in this selection", exactOnly ? "Exact telemetry is shown only when the canonical quality is EXACT." : "Missing duration values remain UNKNOWN.");
    const meta = $(id + "Meta"); if (meta) meta.textContent = "N=0";
    return;
  }
  const values = data.map(row => Number(row[field])), max = Math.max(...values, 1);
  const W = 820, H = 240, L = 48, R = 16, T = 16, B = 35, CW = W - L - R, CH = H - T - B;
  const x = i => L + (CW * i / Math.max(data.length - 1, 1));
  const y = value => T + CH - (value / max) * CH;
  const grid = [0, 1, 2, 3, 4].map(i => {
    const yy = T + CH * i / 4;
    return '<line class="chart-gridline" x1="' + L + '" y1="' + yy + '" x2="' + (W - R) + '" y2="' + yy + '"></line><text class="chart-label" x="' + (L - 8) + '" y="' + (yy + 3) + '" text-anchor="end">' + esc(formatter(max * (1 - i / 4))) + '</text>';
  }).join("");
  const points = values.map((value, i) => x(i) + "," + y(value)).join(" ");
  const area = "M " + L + " " + (T + CH) + " L " + values.map((value, i) => x(i) + " " + y(value)).join(" L ") + " L " + x(values.length - 1) + " " + (T + CH) + " Z";
  const dots = data.map((row, i) => '<circle class="chart-point ' + (pointClass || "") + '" cx="' + x(i) + '" cy="' + y(Number(row[field])) + '" r="3.4"><title>' + esc(dateLabel(row.timestamp) + " · " + formatter(row[field])) + '</title></circle>').join("");
  $(id).innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img">' +
    '<defs><linearGradient id="areaFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#70c9ff" stop-opacity=".25"></stop><stop offset="1" stop-color="#70c9ff" stop-opacity="0"></stop></linearGradient></defs>' +
    grid + '<line class="chart-axis" x1="' + L + '" y1="' + (T + CH) + '" x2="' + (W - R) + '" y2="' + (T + CH) + '"></line><path class="chart-area" d="' + area + '"></path><polyline class="chart-line" points="' + points + '"></polyline>' + dots +
    '<text class="chart-label" x="' + L + '" y="' + (H - 9) + '">' + esc(dateLabel(data[0].timestamp)) + '</text><text class="chart-label" x="' + (W - R) + '" y="' + (H - 9) + '" text-anchor="end">' + esc(dateLabel(data[data.length - 1].timestamp)) + '</text></svg>';
  const meta = $(id + "Meta"); if (meta) meta.textContent = "N=" + data.length + (exactOnly ? " · exact" : "");
}
function scatterChart(id, rows, xField = "duration_seconds", yField = "exact_total_tokens", xLabel = "duration", yLabel = "tokens", xFormatter = duration, yFormatter = compact) {
  const data = rows.filter(row => isKnown(row[xField]) && isKnown(row[yField])).slice(-120);
  if (!data.length) {
    emptyChart(id, "No paired exact observations", "This view needs both a valid duration and exact total tokens.");
    const meta = $(id + "Meta"); if (meta) meta.textContent = "N=0";
    return;
  }
  const maxX = Math.max(...data.map(row => Number(row[xField])), 1), maxY = Math.max(...data.map(row => Number(row[yField])), 1);
  const W = 820, H = 240, L = 54, R = 16, T = 16, B = 35, CW = W - L - R, CH = H - T - B;
  const x = value => L + (Number(value) / maxX) * CW, y = value => T + CH - (Number(value) / maxY) * CH;
  const dots = data.map(row => '<circle class="chart-point amber" cx="' + x(row[xField]) + '" cy="' + y(row[yField]) + '" r="4"><title>' + esc(row.project + " · " + xFormatter(row[xField]) + " · " + yFormatter(row[yField])) + '</title></circle>').join("");
  $(id).innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img"><line class="chart-axis" x1="' + L + '" y1="' + (T + CH) + '" x2="' + (W - R) + '" y2="' + (T + CH) + '"></line><line class="chart-axis" x1="' + L + '" y1="' + T + '" x2="' + L + '" y2="' + (T + CH) + '"></line>' + dots + '<text class="chart-label" x="' + L + '" y="' + (H - 9) + '">' + esc(xLabel + " → " + xFormatter(maxX)) + '</text><text class="chart-label" x="' + (L + 5) + '" y="' + (T + 11) + '">' + esc(yLabel + " ↑ " + yFormatter(maxY)) + '</text></svg>';
  const meta = $(id + "Meta"); if (meta) meta.textContent = "N=" + data.length + " · exact pairs";
}
function renderOverview() {
  const rows = filteredRows(), todayRows = filteredRows(true).filter(row => dateKey(row.timestamp) === dateKey(new Date().toISOString()));
  const row = latest(rows);
  const exactToday = todayRows.filter(item => item.usage_quality === "EXACT");
  const exactAll = rows.filter(item => item.usage_quality === "EXACT");
  const wallToday = todayRows.filter(item => isKnown(item.duration_seconds)).reduce((sum, item) => sum + Number(item.duration_seconds), 0);
  const workersUsed = todayRows.filter(item => item.worker_count > 0).length;
  const statusText = row ? statusBadge(row.status) : '<span class="badge">NO DATA</span>';
  const hero = row ? '<section class="hero-panel"><div class="hero-main"><div class="hero-eyebrow">Latest substantive turn</div><div class="hero-title">' + esc(row.project || UNKNOWN) + '</div><div class="hero-subtitle">' + esc(row.worktree || UNKNOWN) + ' · ' + esc(row.model || UNKNOWN) + (row.reasoning_effort && row.reasoning_effort !== UNKNOWN ? ' · ' + esc(row.reasoning_effort) : "") + '</div><div class="hero-badges">' + speedBadge(row) + statusText + '</div><div class="hero-meta"><strong>' + esc(dateLabel(row.timestamp)) + '</strong> · ' + esc(row.turn_id || UNKNOWN) + '</div></div>' +
    '<div class="hero-stat"><span class="label">Duration</span><span class="value">' + esc(duration(row.duration_seconds)) + '</span><span class="hint">wall time</span></div>' +
    '<div class="hero-stat"><span class="label">Root tokens</span><span class="value">' + esc(compact(row.root_exact_total_tokens)) + '</span><span class="hint">' + esc(row.root_usage_quality) + '</span></div>' +
    '<div class="hero-stat"><span class="label">Worker tokens</span><span class="value">' + esc(compact(row.worker_exact_total_tokens)) + '</span><span class="hint">' + esc(row.worker_usage_quality) + '</span></div>' +
    '<div class="hero-stat"><span class="label">Orchestra total</span><span class="value">' + esc(compact(row.orchestra_exact_total_tokens)) + '</span><span class="hint">' + esc(row.orchestra_usage_quality) + '</span></div>' +
    '<div class="hero-stat"><span class="label">Cached</span><span class="value">' + esc(ratioPercent(row.cache_ratio)) + '</span><span class="hint">' + esc(row.worker_count == null ? "workers UNKNOWN" : row.worker_count + " workers") + '</span></div></section>' :
    '<section class="hero-panel"><div class="hero-main"><div class="hero-eyebrow">Latest substantive turn</div><div class="hero-title">No turns match the current filters</div><div class="hero-subtitle">Reset filters to restore the latest telemetry state.</div></div></section>';
  const statusCounts = ["COMPLETED", "INTERRUPTED"].map(status => todayRows.filter(item => item.status === status).length).join(" / ");
  $("overviewView").innerHTML = hero +
    '<div class="metric-grid">' +
      metricCard("Turns today", num(todayRows.length), todayRows.length + " observed turns", "") +
      metricCard("Exact tokens today", compact(exactToday.reduce((sum, item) => sum + Number(item.exact_total_tokens), 0)), "N=" + exactToday.length + " exact turns", "accent") +
      metricCard("Wall time today", duration(wallToday), todayRows.filter(item => isKnown(item.duration_seconds)).length + " known durations", "") +
      metricCard("Exact coverage", percent(rows.length ? 100 * exactAll.length / rows.length : null), exactAll.length + " / " + rows.length + " turns", exactAll.length ? "good" : "warn") +
      metricCard("Completed / interrupted", statusText === "" ? UNKNOWN : statusCounts, "today · lifecycle", "") +
      metricCard("Workers used", num(workersUsed), "today · declared workers", workersUsed ? "accent" : "") +
    '</div>' +
    '<div class="section-head"><div><h2>Signal overview</h2><p>Token charts are exact-only; duration accepts every valid observation.</p></div><p>' + esc(rows.length + " turns in selection") + '</p></div>' +
    '<div class="chart-grid">' +
      chartPanel("Token usage per turn", "Canonical exact total tokens", "tokenChart", "large") +
      chartPanel("Turn duration over time", "All valid wall-clock observations", "durationChart", "") +
    '</div><div class="chart-grid secondary">' +
      chartPanel("Duration vs orchestra tokens", "Only paired exact observations", "scatterChart", "") +
      chartPanel("Cache ratio / context reuse", "Cached input ÷ input, exact usage only", "cacheChart", "") +
    '</div>';
  lineChart("tokenChart", rows, "exact_total_tokens", true, compact, "");
  lineChart("durationChart", rows, "duration_seconds", false, duration, "green");
  scatterChart("scatterChart", rows);
  lineChart("cacheChart", rows, "cache_ratio", true, ratioPercent, "amber");
}
function sortable(key, label) {
  const marker = STATE.sort === key ? (STATE.direction === 1 ? " ↑" : " ↓") : "";
  return '<th><button data-sort="' + key + '">' + esc(label + marker) + '</button></th>';
}
function renderTurns() {
  const all = sortedRows(filteredRows()), pages = Math.max(1, Math.ceil(all.length / PAGE_SIZE));
  STATE.page = Math.min(STATE.page, pages);
  const start = (STATE.page - 1) * PAGE_SIZE, rows = all.slice(start, start + PAGE_SIZE);
  const body = rows.length ? rows.map(row => '<tr tabindex="0" data-run="' + esc(row.run_id) + '">' +
    '<td>' + esc(dateLabel(row.timestamp)) + '</td><td><div class="cell-title">' + esc(row.project) + '</div><div class="cell-sub">' + esc(row.worktree) + '</div></td>' +
    '<td>' + esc(row.model || UNKNOWN) + (row.reasoning_effort && row.reasoning_effort !== UNKNOWN ? '<div class="cell-sub">' + esc(row.reasoning_effort) + '</div>' : "") + '</td><td>' + speedBadge(row) + '</td>' +
    '<td class="num">' + esc(row.worker_count == null ? UNKNOWN : num(row.worker_count)) + '</td><td class="num">' + esc(duration(row.duration_seconds)) + '</td>' +
    '<td class="num">' + esc(compact(row.root_exact_total_tokens)) + '</td><td class="num">' + esc(compact(row.worker_exact_total_tokens)) + '</td><td class="num">' + esc(compact(row.orchestra_exact_total_tokens)) + '</td>' +
    '<td class="num">' + esc(ratioPercent(row.cache_ratio)) + '</td><td>' + statusBadge(row.status) + '</td></tr>').join("") : '<tr><td colspan="11"><div class="empty-chart">No turns match the current filters.</div></td></tr>';
  $("turnsView").innerHTML = '<div class="section-head"><div><h2>Turns</h2><p>Click a row for the complete evidence detail. Long identifiers stay out of the table.</p></div><p><strong>' + all.length + '</strong> matching turns</p></div>' +
    '<div class="panel table-panel"><div class="table-scroll"><table><thead><tr>' + sortable("timestamp", "Time") + sortable("project", "Project") + sortable("model", "Model") + '<th>Speed</th>' + sortable("worker_count", "Workers") + sortable("duration_seconds", "Duration") + sortable("root_exact_total_tokens", "Root tokens") + sortable("worker_exact_total_tokens", "Worker tokens") + sortable("orchestra_exact_total_tokens", "Orchestra tokens") + sortable("cache_ratio", "Cache %") + '<th>Status</th></tr></thead><tbody>' + body + '</tbody></table></div>' +
    '<div class="pagination"><span>Showing ' + (all.length ? (start + 1) : 0) + '–' + Math.min(start + PAGE_SIZE, all.length) + ' of ' + all.length + '</span><div class="pagination-actions"><button data-page="prev" ' + (STATE.page <= 1 ? "disabled" : "") + '>Previous</button><button data-page="next" ' + (STATE.page >= pages ? "disabled" : "") + '>Next</button></div></div></div>';
}
function tokenCell(label, value) {
  return '<div class="token-cell"><span>' + esc(label) + '</span><strong>' + esc(value) + '</strong></div>';
}
function detailRow(label, value) {
  return '<div class="detail-row"><span>' + esc(label) + '</span><strong title="' + esc(value) + '">' + esc(value) + '</strong></div>';
}
function renderDrawer() {
  const drawer = $("detailDrawer"), scrim = $("drawerScrim"), row = rowById(STATE.drawer);
  if (!row) { drawer.classList.remove("open"); scrim.classList.remove("open"); drawer.setAttribute("aria-hidden", "true"); return; }
  const workerRows = row.workers && row.workers.length ? row.workers.map(worker => '<div class="worker-row"><span class="worker-name">' + esc(worker.worker_id) + '<small> · ' + esc(worker.model) + '</small></span><small>' + esc(worker.status) + '</small><strong>' + esc(compact(worker.total_tokens)) + '</strong></div>').join("") : '<div class="empty-chart">No worker observations for this turn.</div>';
  drawer.innerHTML = '<div class="drawer-head"><div><div class="kicker">Turn detail</div><h2>' + esc(row.project) + '</h2><div class="drawer-sub">' + esc(row.model) + ' · ' + esc(duration(row.duration_seconds)) + ' · ' + statusBadge(row.status) + '</div></div><button class="drawer-close" data-close-drawer aria-label="Close detail">×</button></div>' +
    '<div class="drawer-section"><h3>Token breakdown</h3><div class="token-grid">' +
      tokenCell("Input", compact(row.input_tokens)) + tokenCell("Cached", compact(row.cached_input_tokens)) + tokenCell("Non-cached", compact(row.non_cached_input_tokens)) + tokenCell("Output", compact(row.output_tokens)) + tokenCell("Reasoning", compact(row.reasoning_tokens)) + tokenCell("Root total", compact(row.root_exact_total_tokens)) + tokenCell("Worker total", compact(row.worker_exact_total_tokens)) + tokenCell("Orchestra total", compact(row.orchestra_exact_total_tokens)) +
    '</div></div><div class="drawer-section"><h3>Orchestra</h3><div class="detail-list">' +
      detailRow("Worker count", row.worker_count == null ? UNKNOWN : num(row.worker_count)) + detailRow("Worker active time", duration(row.worker_wall_seconds)) + detailRow("Max concurrency", row.max_concurrency == null ? UNKNOWN : num(row.max_concurrency)) + detailRow("Attribution", row.attribution_quality) +
    '</div><div class="worker-list" style="margin-top:8px">' + workerRows + '</div></div>' +
    '<div class="drawer-section"><h3>Metadata</h3><div class="detail-list">' +
      detailRow("Turn ID", row.turn_id || UNKNOWN) + detailRow("Session / thread", (row.session_id || UNKNOWN) + " / " + (row.thread_id || UNKNOWN)) + detailRow("Worktree", row.worktree || UNKNOWN) + detailRow("Usage source", row.usage_source || UNKNOWN) + detailRow("Usage quality", row.usage_quality || UNKNOWN) + detailRow("Speed evidence", row.speed_mode_source || UNKNOWN) + detailRow("Measurement", row.measurement_generation || UNKNOWN) + detailRow("Reasoning effort", row.reasoning_effort || UNKNOWN) +
    '</div></div><div class="footer-note">Only lifecycle metadata and whitelisted usage fields are shown here. Prompt and response content are never part of this view.</div>';
  drawer.classList.add("open"); scrim.classList.add("open"); drawer.setAttribute("aria-hidden", "false");
}
function renderOrchestra() {
  const rows = sortedRows(filteredRows()), selected = rowById(STATE.orchestra) || latest(rows) || null;
  if (selected) STATE.orchestra = selected.run_id;
  const options = rows.map(row => '<option value="' + esc(row.run_id) + '"' + (selected && selected.run_id === row.run_id ? " selected" : "") + '>' + esc(dateLabel(row.timestamp) + " · " + row.project + " · " + row.model) + '</option>').join("");
  if (!selected) {
    $("orchestraView").innerHTML = '<div class="section-head"><div><h2>Orchestra</h2><p>Worker timelines and contribution analysis.</p></div></div><div class="panel orchestra-panel"><div class="empty-chart"><div><strong>No turn selected</strong><span>Reset filters or choose a turn with orchestra metadata.</span></div></div></div>';
    return;
  }
  const workerItems = selected.workers || [];
  const rootTimed = isKnown(selected.duration_seconds);
  const rootLine = '<div class="timeline-row"><div class="timeline-label">ROOT · ' + esc(selected.model || UNKNOWN) + '</div><div class="timeline-track ' + (rootTimed ? "" : "unknown") + '">' + (rootTimed ? '<div class="timeline-bar" style="width:100%"></div>' : "duration UNKNOWN") + '</div><div class="timeline-value">' + esc(duration(selected.duration_seconds)) + '</div></div>';
  const workerLines = workerItems.length ? workerItems.map(worker => {
    const timed = isKnown(selected.worker_wall_seconds) && Number(selected.duration_seconds) > 0;
    const width = timed ? Math.max(5, Math.min(100, Number(selected.worker_wall_seconds) / Number(selected.duration_seconds) * 100 / Math.max(workerItems.length, 1))) : 0;
    return '<div class="timeline-row"><div class="timeline-label">' + esc(worker.worker_id) + '</div><div class="timeline-track ' + (timed ? "" : "unknown") + '">' + (timed ? '<div class="timeline-bar worker" style="width:' + width + '%"></div>' : "start offset UNKNOWN · active duration UNKNOWN") + '</div><div class="timeline-value">' + esc(compact(worker.total_tokens)) + ' tokens</div></div>';
  }).join("") : '<div class="empty-chart"><div><strong>No worker observations</strong><span>This turn is root-only or worker metadata is unavailable.</span></div></div>';
  const workerShare = isKnown(selected.worker_exact_total_tokens) && isKnown(selected.orchestra_exact_total_tokens) && Number(selected.orchestra_exact_total_tokens) > 0 ? Number(selected.worker_exact_total_tokens) / Number(selected.orchestra_exact_total_tokens) : null;
  const parallel = isKnown(selected.worker_wall_seconds) && Number(selected.duration_seconds) > 0 ? Number(selected.worker_wall_seconds) / Number(selected.duration_seconds) : null;
  $("orchestraView").innerHTML = '<div class="section-head"><div><h2>Orchestra</h2><p>Inspect worker timing, overlap, and token share without inferring missing evidence.</p></div></div><div class="orchestra-layout"><section class="panel orchestra-panel"><select id="orchestraSelect" class="turn-select">' + options + '</select><div class="timeline">' + rootLine + workerLines + '</div><div class="timeline-note">Worker start offsets and active durations are shown only when captured. UNKNOWN values are not rendered as inferred bars.</div><div class="small-grid">' + smallMetric("Root duration", duration(selected.duration_seconds)) + smallMetric("Worker active time", duration(selected.worker_wall_seconds)) + smallMetric("Parallelism factor", isKnown(parallel) ? parallel.toFixed(2) + "×" : UNKNOWN) + smallMetric("Max concurrency", selected.max_concurrency == null ? UNKNOWN : num(selected.max_concurrency)) + smallMetric("Worker token share", ratioPercent(workerShare)) + smallMetric("Exact orchestra total", compact(selected.orchestra_exact_total_tokens)) + '</div></section><section class="panel orchestra-panel"><div class="panel-head"><div><h3>Selected turn</h3><p>' + esc((selected.project || UNKNOWN) + " · " + (selected.worktree || UNKNOWN)) + '</p></div>' + statusBadge(selected.status) + '</div><div class="detail-list">' + detailRow("Speed", (selected.speed_mode || UNKNOWN) + (selected.speed_certified ? " · certified" : "")) + detailRow("Root usage", selected.root_usage_quality || UNKNOWN) + detailRow("Worker usage", selected.worker_usage_quality || UNKNOWN) + detailRow("Orchestra usage", selected.orchestra_usage_quality || UNKNOWN) + detailRow("Attribution source", selected.attribution_source || UNKNOWN) + detailRow("Turn ID", selected.turn_id || UNKNOWN) + '</div><button class="action primary" data-open-drawer="' + esc(selected.run_id) + '" style="margin-top:13px">Open turn detail</button></section></div>' +
    '<div class="section-head"><div><h2>Aggregate orchestration signals</h2><p>Charts stay compact when the ledger has no certified observations.</p></div></div><div class="subgrid">' + chartPanel("Worker count vs duration", "Known duration observations", "workerDurationChart", "") + chartPanel("Worker count vs orchestra tokens", "Exact orchestra totals only", "workerTokenChart", "") + chartPanel("Duration vs orchestra tokens", "Exact paired observations", "orchestraScatterChart", "") + chartPanel("Root vs worker exact usage", "Exact root/worker token share", "shareChart", "") + '</div>';
  $("orchestraSelect").onchange = event => { STATE.orchestra = event.target.value; renderOrchestra(); };
  const workerDuration = rows.filter(item => item.worker_count != null && item.duration_seconds != null);
  if (!workerDuration.length) emptyChart("workerDurationChart", "No worker duration cohort", "Worker timing is UNKNOWN for the available observations.");
  else scatterChart("workerDurationChart", workerDuration.map(item => Object.assign({}, item, { exact_total_tokens: item.worker_count })), "duration_seconds", "exact_total_tokens", "duration", "worker count", duration, num);
  const workerTokenRows = rows.filter(item => item.worker_count != null && item.orchestra_exact_total_tokens != null);
  if (!workerTokenRows.length) emptyChart("workerTokenChart", "No exact orchestra cohort", "Worker-count comparisons require exact orchestra totals.");
  else scatterChart("workerTokenChart", workerTokenRows.map(item => Object.assign({}, item, { duration_seconds: item.worker_count, exact_total_tokens: item.orchestra_exact_total_tokens })), "duration_seconds", "exact_total_tokens", "worker count", "orchestra tokens", num, compact);
  scatterChart("orchestraScatterChart", rows);
  const shareRows = rows.filter(item => item.worker_exact_total_tokens != null && item.root_exact_total_tokens != null);
  if (!shareRows.length) emptyChart("shareChart", "No exact root/worker split", "Root and worker totals must both be exact.");
  else {
    const totalRoot = shareRows.reduce((sum, item) => sum + Number(item.root_exact_total_tokens), 0), totalWorker = shareRows.reduce((sum, item) => sum + Number(item.worker_exact_total_tokens), 0);
    $("shareChart").innerHTML = '<div class="small-grid" style="margin-top:35px">' + smallMetric("Root", compact(totalRoot)) + smallMetric("Worker", compact(totalWorker)) + smallMetric("Worker share", ratioPercent(totalWorker / Math.max(totalRoot + totalWorker, 1))) + '</div>';
    const meta = $("shareChartMeta"); if (meta) meta.textContent = "N=" + shareRows.length;
  }
}
function benchmarkStats(rows, mode) {
  const cohort = rows.filter(row => row.speed_certified && row.speed_mode === mode);
  const exact = cohort.filter(row => row.usage_quality === "EXACT");
  return { n: cohort.length, duration: median(cohort.map(row => row.duration_seconds)), tokens: median(exact.map(row => row.exact_total_tokens)), fresh: median(exact.map(row => row.non_cached_input_tokens)), cache: median(exact.map(row => row.cache_ratio)) };
}
function benchmarkCard(mode, stats) {
  const cls = mode === "FAST" ? "badge-fast" : "badge-speed";
  const metrics = stats.n ? '<div class="benchmark-metrics"><div><span>Median duration</span><strong>' + esc(duration(stats.duration)) + '</strong></div><div><span>Median total tokens</span><strong>' + esc(compact(stats.tokens)) + '</strong></div><div><span>Median fresh input</span><strong>' + esc(compact(stats.fresh)) + '</strong></div><div><span>Median cache ratio</span><strong>' + esc(ratioPercent(stats.cache)) + '</strong></div></div>' : '<div class="benchmark-empty">No launcher-certified turns yet. Use codex-fast or codex-standard to populate this comparison.</div>';
  return '<article class="benchmark-card"><h3><span class="badge ' + cls + '">' + mode + '</span></h3><div class="sample">N=' + stats.n + ' certified turns</div>' + metrics + '</article>';
}
function renderBenchmarks() {
  const rows = filteredRows(), fast = benchmarkStats(rows, "FAST"), standard = benchmarkStats(rows, "STANDARD");
  $("benchmarksView").innerHTML = '<div class="section-head"><div><h2>Benchmarks</h2><p>Scientific comparison surface for launcher-certified cohorts only.</p></div><p>Always show N · no recommendation score</p></div><div class="benchmark-grid">' + benchmarkCard("FAST", fast) + benchmarkCard("STANDARD", standard) + '<article class="benchmark-card"><h3><span class="badge">DIRECT / LIGHT / HEAVY</span></h3><div class="sample">Future cohort boundary</div><div class="benchmark-empty">Mode cohorts are displayed only when their source records carry a comparable certification boundary.</div></article><article class="benchmark-card"><h3><span class="badge">Worker cohorts</span></h3><div class="sample">Future cohort boundary</div><div class="benchmark-empty">Worker-count comparisons remain descriptive until exact timing and usage coverage are available.</div></article></div><div class="privacy-note">Benchmark panels use only <strong>speed_mode_source=LAUNCHER_EXPLICIT</strong>. Missing or insufficient data stays visible as UNKNOWN rather than being treated as zero.</div>';
}
function renderQuality() {
  const rows = filteredRows(), exact = rows.filter(row => row.usage_quality === "EXACT").length, unknown = rows.length - exact, open = rows.filter(row => row.status === "OPEN").length, certified = rows.filter(row => row.speed_certified).length;
  $("qualityView").innerHTML = '<div class="section-head"><div><h2>Data quality</h2><p>Technical health and evidence boundaries for the current selection.</p></div><p>Fail-closed presentation</p></div><div class="quality-grid">' +
    '<article class="quality-card"><h3>Exact usage coverage</h3><span class="value ' + (exact ? "good" : "warn") + '">' + esc(percent(rows.length ? 100 * exact / rows.length : null)) + '</span><p class="note">' + exact + ' exact · ' + unknown + ' UNKNOWN/PARTIAL</p></article>' +
    '<article class="quality-card"><h3>Open turns</h3><span class="value ' + (open ? "warn" : "good") + '">' + esc(num(open)) + '</span><p class="note">Lifecycle has no completed close yet.</p></article>' +
    '<article class="quality-card"><h3>Certified speed</h3><span class="value">' + esc(num(certified)) + '</span><p class="note">LAUNCHER_EXPLICIT records</p></article>' +
    '<article class="quality-card"><h3>Fold errors</h3><span class="value ' + (DATA.exclusions.fold_errors ? "alert" : "good") + '">' + esc(num(DATA.exclusions.fold_errors)) + '</span><p class="note">Malformed runs are isolated.</p></article></div>' +
    '<div class="section-head"><div><h2>Exclusion ledger</h2><p>Excluded source classes remain counted here for auditability.</p></div></div><div class="quality-list">' +
      '<div class="quality-row"><span>Session-level runs excluded</span><strong>' + esc(num(DATA.exclusions.session_level_runs_excluded)) + '</strong></div><div class="quality-row"><span>Synthetic runs excluded</span><strong>' + esc(num(DATA.exclusions.synthetic_runs_excluded)) + '</strong></div><div class="quality-row"><span>Legacy manual observations excluded</span><strong>' + esc(num(DATA.exclusions.legacy_manual_observations_excluded)) + '</strong></div><div class="quality-row"><span>Valid source records</span><strong>' + esc(num(DATA.source.record_count)) + '</strong></div><div class="quality-row"><span>Ledger SHA-256</span><strong title="' + esc(DATA.source.ledger_sha256) + '">' + esc(DATA.source.ledger_sha256.slice(0, 16) + "…") + '</strong></div></div>' +
    '<div class="privacy-note">Read-only boundary: this page reads the append-only ledger and writes only an optional rebuildable derived cache. No prompt, response, tool, code, or secret content is read or persisted.</div>';
}
function syncControls() {
  setOptions("projectFilter", DATA.filters.projects);
  setOptions("modelFilter", DATA.filters.models);
  setOptions("speedFilter", DATA.filters.speed_modes);
  setOptions("statusFilter", DATA.filters.statuses);
  $("projectFilter").value = STATE.project; $("modelFilter").value = STATE.model; $("speedFilter").value = STATE.speed; $("statusFilter").value = STATE.status; $("workersFilter").value = STATE.workers; $("searchFilter").value = STATE.query; $("exactFilter").checked = STATE.exact;
  document.querySelectorAll("[data-period]").forEach(button => button.classList.toggle("active", button.dataset.period === STATE.period));
  document.querySelectorAll("[data-nav-view]").forEach(button => button.classList.toggle("active", button.dataset.navView === STATE.view));
}
function renderAll() {
  syncControls();
  $("overviewView").classList.toggle("active", STATE.view === "overview");
  $("turnsView").classList.toggle("active", STATE.view === "turns");
  $("orchestraView").classList.toggle("active", STATE.view === "orchestra");
  $("benchmarksView").classList.toggle("active", STATE.view === "benchmarks");
  $("qualityView").classList.toggle("active", STATE.view === "quality");
  renderOverview(); renderTurns(); renderOrchestra(); renderBenchmarks(); renderQuality(); renderDrawer();
  updateRefreshText();
}
function updateRefreshText(message) {
  const stamp = STATE.updated ? STATE.updated.toLocaleTimeString() : "pending";
  $("updatedText").textContent = "Last updated: " + stamp;
  $("refreshState").textContent = (message || (LIVE_MODE && $("autoRefresh").checked ? "ON · 5s" : "OFF")) + (LIVE_MODE ? "" : " · static report");
}
let refreshTimer = null, refreshInFlight = false;
async function refreshData() {
  if (!LIVE_MODE || refreshInFlight) return;
  refreshInFlight = true; updateRefreshText("refreshing…");
  try {
    const response = await fetch("/api/snapshot?ts=" + Date.now(), { cache: "no-store" });
    if (!response.ok) throw new Error("server returned " + response.status);
    const next = await response.json();
    if (!next.schema) throw new Error("invalid dashboard snapshot");
    DATA = next; STATE.updated = new Date(); renderAll();
  } catch (error) {
    updateRefreshText("refresh failed");
  } finally { refreshInFlight = false; }
}
function setAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = null;
  if (LIVE_MODE && $("autoRefresh").checked) refreshTimer = setInterval(refreshData, 5000);
  updateRefreshText();
}
document.addEventListener("click", event => {
  const nav = event.target.closest("[data-nav-view]");
  if (nav) { STATE.view = nav.dataset.navView; STATE.page = 1; renderAll(); return; }
  const period = event.target.closest("[data-period]");
  if (period) { STATE.period = period.dataset.period; STATE.page = 1; renderAll(); return; }
  const sort = event.target.closest("[data-sort]");
  if (sort) { STATE.direction = STATE.sort === sort.dataset.sort ? -STATE.direction : -1; STATE.sort = sort.dataset.sort; STATE.page = 1; renderTurns(); return; }
  const page = event.target.closest("[data-page]");
  if (page) { STATE.page += page.dataset.page === "next" ? 1 : -1; renderTurns(); return; }
  const row = event.target.closest("tr[data-run]");
  if (row) { STATE.drawer = row.dataset.run; renderDrawer(); return; }
  const detail = event.target.closest("[data-open-drawer]");
  if (detail) { STATE.drawer = detail.dataset.openDrawer; renderDrawer(); return; }
  if (event.target.closest("[data-close-drawer]") || event.target.id === "drawerScrim") { STATE.drawer = null; renderDrawer(); return; }
});
["projectFilter", "modelFilter", "speedFilter", "statusFilter", "workersFilter"].forEach(id => $(id).addEventListener("change", event => { STATE[id.replace("Filter", "")] = event.target.value; STATE.page = 1; renderAll(); }));
$("searchFilter").addEventListener("input", event => { STATE.query = event.target.value; STATE.page = 1; renderAll(); });
$("exactFilter").addEventListener("change", event => { STATE.exact = event.target.checked; STATE.page = 1; renderAll(); });
$("refreshNow").addEventListener("click", refreshData);
$("autoRefresh").addEventListener("change", setAutoRefresh);
document.addEventListener("keydown", event => { if (event.key === "Escape") { STATE.drawer = null; renderDrawer(); }});
if (!LIVE_MODE) { $("autoRefresh").checked = false; $("autoRefresh").disabled = true; $("refreshNow").disabled = true; }
renderAll(); setAutoRefresh();
if (LIVE_MODE) refreshData();
</script>
</body>
</html>"""
    return template.replace("__PAYLOAD__", payload).replace("__LIVE_MODE__", "true" if live else "false")


def _summary_line(snapshot: dict[str, Any]) -> dict[str, Any]:
    overview = snapshot["overview"]
    return {
        "schema": snapshot["schema"],
        "ledger_sha256": snapshot["source"]["ledger_sha256"],
        "total_turns": overview["total_turns"],
        "completed": overview["completed"],
        "interrupted": overview["interrupted"],
        "open": overview["open"],
        "exact_usage_coverage_percent": overview["exact_usage_coverage"]["percent"],
        "total_exact_tokens": overview["exact_tokens"]["total"],
        "known_wall_time_seconds": overview["wall_time"]["total_seconds"],
        "project_count": overview["project_count"],
        "cache_location": None,
    }


class _DashboardHandler(http.server.BaseHTTPRequestHandler):
    html_payload = ""
    store_root: str | None = None
    cache_path: str | None = None

    def _current_snapshot(self) -> dict[str, Any]:
        store = TelemetryStore(self.store_root)
        cache = Path(self.cache_path) if self.cache_path else None
        return load_snapshot(store, cache=cache)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API.
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self._send(200, b"ok\n", "text/plain; charset=utf-8")
            return
        if path == "/api/snapshot":
            try:
                body = json.dumps(self._current_snapshot(), sort_keys=True, separators=(",", ":")).encode("utf-8")
            except DashboardError as exc:
                body = json.dumps({"error": str(exc)}, sort_keys=True).encode("utf-8")
                self._send(503, body, "application/json; charset=utf-8")
                return
            self._send(200, body, "application/json; charset=utf-8")
            return
        elif path in {"/", "/index.html"}:
            try:
                body = build_html(self._current_snapshot(), live=True).encode("utf-8")
            except DashboardError as exc:
                body = f"orchestra-dashboard: {html.escape(str(exc))}\n".encode("utf-8")
                self._send(503, body, "text/plain; charset=utf-8")
                return
            self._send(200, body, "text/html; charset=utf-8")
            return
        else:
            self._send(404, b"not found\n", "text/plain; charset=utf-8")
            return

    def log_message(self, format: str, *args: Any) -> None:
        return


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=None, help="telemetry directory; defaults to CODEX_HOME/orchestra-telemetry")
    parser.add_argument("--cache", default=None, help="derived SQLite cache; defaults to <store>/dashboard-cache.sqlite3")
    parser.add_argument("--no-cache", action="store_true", help="do not read or write the derived cache")
    parser.add_argument("--rebuild", action="store_true", help="rebuild the derived cache from the ledger")
    sub = parser.add_subparsers(dest="command", required=False)
    serve = sub.add_parser("serve", help="serve the dashboard on loopback")
    serve.add_argument("--host", default="127.0.0.1", help="must be 127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-browser", action="store_true")
    report = sub.add_parser("report", help="write a self-contained static HTML report")
    report.add_argument("--output", default="orchestra-dashboard-report.html", help="HTML path, or - for stdout")
    sub.add_parser("rebuild", help="rebuild the derived cache and print a summary")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command is None:
        args.command = "serve"
        args.host = "127.0.0.1"
        args.port = 8765
        args.no_browser = False
    try:
        if args.command == "serve":
            if args.host != "127.0.0.1":
                raise DashboardError("dashboard binds to loopback only: use --host 127.0.0.1")
            if not 0 <= args.port <= 65535:
                raise DashboardError("port must be between 0 and 65535")
        store = TelemetryStore(args.store)
        cache = None if args.no_cache else _cache_path(store, args.cache)
        snapshot = load_snapshot(store, cache=cache, rebuild=args.rebuild)
        if args.command == "rebuild":
            summary = _summary_line(snapshot)
            summary["cache_location"] = str(cache) if cache is not None else None
            print(json.dumps(summary, sort_keys=True, indent=2))
            return 0
        if args.command == "report":
            output = args.output
            report_html = build_html(snapshot, live=False)
            if output == "-":
                sys.stdout.write(report_html)
            else:
                target = Path(output).expanduser()
                try:
                    if target.resolve() == store.ledger_path.resolve():
                        raise DashboardError("static report must not overwrite ledger.jsonl")
                except (OSError, RuntimeError) as exc:
                    raise DashboardError(f"cannot resolve report path: {exc}") from exc
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(report_html, encoding="utf-8", newline="\n")
                print(str(target.resolve()))
            return 0
        handler = type("DashboardHandler", (_DashboardHandler,), {})
        handler.html_payload = build_html(snapshot, live=True)
        handler.store_root = str(store.root)
        handler.cache_path = str(cache) if cache is not None else None
        with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
            url = f"http://127.0.0.1:{server.server_port}/"
            print(f"Orchestra dashboard: {url}", flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        return 0
    except DashboardError as exc:
        print(f"orchestra-dashboard: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"orchestra-dashboard: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
