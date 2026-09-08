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
DASHBOARD_VERSION = "1.0"
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
            "status": _safe_label(raw.get("launch_status")),
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
        "timestamp": _safe_timestamp(run.get("started_at_utc")),
        "ended_at_utc": _safe_timestamp(run.get("ended_at_utc")),
        "project": project,
        "worktree": worktree,
        "model": _safe_model(root.get("model")),
        "speed_mode": speed,
        "speed_mode_source": speed_source,
        "speed_certified": speed_certified,
        "duration_seconds": _nonnegative_number(execution.get("wall_clock_seconds")),
        "status": _status(run),
        "usage_quality": quality,
        "root_usage_quality": quality,
        "worker_usage_quality": worker_quality,
        "orchestra_usage_quality": orchestra_quality,
        "worker_count": _nonnegative_int(orchestra.get("actual_worker_count")),
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


def build_html(snapshot: dict[str, Any], *, live: bool = False) -> str:
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
