"""Create a prompt-blind, path-free Orchestra usage snapshot.

The snapshot is a derived review artifact. This module never copies raw ledger
records and never reads prompts, responses, tools, transcripts, or source files.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import statistics
import subprocess
from typing import Any

from orchestra_dashboard import _read_stable_ledger, load_snapshot
from orchestra_telemetry import TelemetryStore


SCHEMA = "orchestra_review_snapshot_v1"
FORBIDDEN_KEYS = {
    "prompt", "response", "tool_args", "tool_arguments", "tool_output",
    "tool_outputs", "transcript_path", "agent_transcript_path", "secret",
    "credential",
}
PATH_LIKE = re.compile(r"(?i)([a-z]:[\\/]|\\\\|/users/|/home/|/private/)")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_store() -> Path:
    configured = os.environ.get("CODEX_ORCHESTRA_STORE")
    if configured:
        return Path(configured).expanduser()
    codex_home = os.environ.get("CODEX_HOME")
    return (Path(codex_home).expanduser() if codex_home else Path.home() / ".codex") / "orchestra-telemetry"


def count_map(values: list[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def number_summary(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values = [
        row[field] for row in rows
        if isinstance(row.get(field), (int, float)) and not isinstance(row.get(field), bool)
    ]
    if not values:
        return {"n": 0, "sum": None, "median": None, "min": None, "max": None}
    return {"n": len(values), "sum": sum(values), "median": statistics.median(values), "min": min(values), "max": max(values)}


def git_value(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo_root), *args], text=True, stderr=subprocess.STDOUT
    ).strip()


def receiver_state(store_root: Path) -> dict[str, Any]:
    pid_path = store_root / "otel-receiver.pid"
    pid_text = pid_path.read_text(encoding="utf-8").strip() if pid_path.is_file() else ""
    try:
        pid = int(pid_text)
    except ValueError:
        pid = None
    process_alive = False
    if pid is not None:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, check=False,
        )
        process_alive = result.returncode == 0 and f'"{pid}"' in result.stdout
    listening = False
    try:
        with socket.create_connection(("127.0.0.1", 4318), timeout=0.5):
            listening = True
    except OSError:
        pass
    return {
        "pid_present": pid is not None,
        "process_alive": process_alive,
        "loopback_4318_accepts_tcp": listening,
        "health": "HEALTHY" if process_alive and listening else "NOT_CONFIRMED",
    }


def pending_state(store_root: Path) -> dict[str, Any]:
    path = store_root / "otel-pending.jsonl"
    raw = path.read_bytes() if path.is_file() else b""
    lines = raw.splitlines()
    parse_errors = 0
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line.decode("utf-8"))
            if not isinstance(value, dict):
                parse_errors += 1
        except (UnicodeDecodeError, json.JSONDecodeError):
            parse_errors += 1
    return {"bytes": len(raw), "line_count": len(lines), "parse_error_count": parse_errors, "may_be_enriched_later": len(lines) > 0}


def privacy_scan(value: object, location: str = "root") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                findings.append(f"forbidden_key:{location}.{key}")
            findings.extend(privacy_scan(child, f"{location}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(privacy_scan(child, f"{location}[{index}]"))
    elif isinstance(value, str) and PATH_LIKE.search(value):
        findings.append(f"path_like_value:{location}")
    return findings


def build_export(repo_root: Path, store_root: Path) -> dict[str, Any]:
    store = TelemetryStore(store_root)
    records, ledger_bytes, partial_final_line = _read_stable_ledger(store)
    dashboard = load_snapshot(store, cache=None, rebuild=True)
    rows = dashboard["turns"]
    exact_rows = [row for row in rows if row["usage_quality"] == "EXACT"]
    exact_fields = {
        field: number_summary(exact_rows, field)
        for field in (
            "input_tokens", "cached_input_tokens", "cache_write_input_tokens",
            "non_cached_input_tokens", "output_tokens", "reasoning_tokens", "total_tokens",
        )
    }
    input_sum = exact_fields["input_tokens"]["sum"]
    cached_sum = exact_fields["cached_input_tokens"]["sum"]
    cache_ratio = cached_sum / input_sum if isinstance(input_sum, (int, float)) and input_sum > 0 and isinstance(cached_sum, (int, float)) else None
    ledger_path = store_root / "ledger.jsonl"
    ledger_mtime = None
    if ledger_path.exists():
        ledger_mtime = datetime.fromtimestamp(ledger_path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "schema": SCHEMA,
        "captured_at_utc": utc_now(),
        "purpose": "Outcome-blind, prompt-blind review package for the local Orchestra telemetry structure.",
        "review_questions": [
            "Assess exact usage coverage and whether unknown values are handled fail-closed.",
            "Assess root versus worker attribution and deterministic orchestra totals.",
            "Assess lifecycle completeness, open turns, and enrichment timing.",
            "Assess benchmark readiness, privacy boundary, and the smallest safe next action.",
        ],
        "implementation": {
            "repository_label": "codex-orchestra-global",
            "branch": git_value(repo_root, "branch", "--show-current"),
            "commit": git_value(repo_root, "rev-parse", "HEAD"),
            "worktree_clean": git_value(repo_root, "status", "--porcelain") == "",
        },
        "source": {
            "ledger_kind": "local_append_only_jsonl",
            "ledger_sha256": hashlib.sha256(ledger_bytes).hexdigest(),
            "ledger_bytes": len(ledger_bytes),
            "ledger_record_count": len(records),
            "ledger_last_write_utc": ledger_mtime,
            "partial_final_line_ignored": partial_final_line,
            "schema": "orchestra_telemetry_v1",
        },
        "runtime": {"otel_receiver": receiver_state(store_root), "otel_pending": pending_state(store_root)},
        "coverage": {
            "turns": dashboard["overview"],
            "lifecycle": dashboard["lifecycle"],
            "usage_quality_by_turn": count_map([row["usage_quality"] for row in rows]),
            "usage_source_by_turn": count_map([row["usage_source"] for row in rows]),
            "measurement_generation_by_turn": count_map([row["measurement_generation"] for row in rows]),
            "model_by_turn": count_map([row["model"] for row in rows]),
            "project_by_turn": count_map([row["project"] for row in rows]),
            "speed_mode_by_turn": count_map([row["speed_mode"] for row in rows]),
            "speed_certified_turns": sum(1 for row in rows if row["speed_certified"]),
            "worker_rows_with_observation": sum(1 for row in rows if row["worker_count"] is not None),
            "worker_usage_quality_by_turn": count_map([row["worker_usage_quality"] for row in rows]),
            "orchestra_usage_quality_by_turn": count_map([row["orchestra_usage_quality"] for row in rows]),
            "open_turn_ids": [row["turn_id"] for row in rows if row["status"] == "OPEN"],
            "exact_usage_fields": exact_fields,
            "exact_cache_ratio": {"cached_input_sum_over_input_sum": cache_ratio, "cached_input_sum": cached_sum, "input_sum": input_sum},
            "raw_record_type_counts": count_map([record.get("record_type", "UNKNOWN") for record in records]),
            "raw_measurement_generation_counts": count_map([record.get("measurement_generation", "MISSING") for record in records]),
        },
        "exclusions_and_privacy": {
            "dashboard_exclusions": dashboard["exclusions"],
            "privacy": dashboard["privacy"],
            "review_export_contains_raw_ledger_records": False,
            "review_export_contains_prompts_responses_tools_or_transcripts": False,
        },
        "dashboard": dashboard,
        "interpretation_notes": [
            "Exact token totals use only usage_quality=EXACT; UNKNOWN is not zero.",
            "Root usage excludes worker usage; orchestra totals stay unknown unless root and all included workers are exact and deterministic.",
            "A live capture is point-in-time; the producing turn may still appear as OPEN.",
            "This package is descriptive evidence, not a routing recommendation or model-quality score.",
        ],
    }


def summary_markdown(export: dict[str, Any]) -> str:
    overview = export["coverage"]["turns"]
    exact = overview["exact_usage_coverage"]
    fields = export["coverage"]["exact_usage_fields"]
    speed = export["dashboard"]["speed_comparison"]
    worker_exact = export["coverage"]["worker_usage_quality_by_turn"].get("EXACT", 0)
    orchestra_total = overview["root_vs_worker_exact_tokens"]["orchestra"]
    ratio = export["coverage"]["exact_cache_ratio"]["cached_input_sum_over_input_sum"]
    return "\n".join([
        "# Orchestra review snapshot", "",
        f"Captured: `{export['captured_at_utc']}` (point-in-time; the producing turn may still be `OPEN`).", "",
        "## Current state", "",
        f"- Ledger integrity: **PASS** — `{export['source']['ledger_record_count']}` validated records, SHA-256 `{export['source']['ledger_sha256']}`.",
        f"- Turn coverage: `{overview['total_turns']}` turns — `{overview['completed']}` completed, `{overview['interrupted']}` interrupted, `{overview['failed']}` failed, `{overview['open']}` open.",
        f"- Exact usage: **{exact['exact_turns']}/{exact['total_turns']} ({exact['percent']:.2f}%)**; exact total `{overview['exact_tokens']['total']:,}` tokens.",
        f"- Worker attribution: `{worker_exact}/{overview['total_turns']}` turns have exact worker usage; deterministic orchestra total is `{orchestra_total:,}` exact tokens across `{overview['exact_tokens']['turn_count']}` exact turns.",
        f"- Speed benchmark: **not ready** — FAST certified `{speed['FAST']['record_count']}`, STANDARD certified `{speed['STANDARD']['record_count']}`.",
        f"- Receiver: **{export['runtime']['otel_receiver']['health']}**; pending OTel lines `{export['runtime']['otel_pending']['line_count']}`.", "",
        "## Interpretation", "",
        "- The ledger is structurally readable and the default dashboard view is turn-level; session-level and synthetic observations remain excluded.",
        "- Native OTel provides an exact subset, but unknown usage is not zero and must not be extrapolated.",
        "- Worker lifecycle observations do not yet provide exact worker token attribution in this snapshot.",
        "- Model, reasoning effort, task class, and orchestra mode are not sufficiently populated for strong routing or quality conclusions.", "",
        "## Exact-only aggregate", "",
        f"- Input `{fields['input_tokens']['sum']:,}`; cached input `{fields['cached_input_tokens']['sum']:,}`; non-cached input `{fields['non_cached_input_tokens']['sum']:,}`.",
        f"- Output `{fields['output_tokens']['sum']:,}`; reasoning `{fields['reasoning_tokens']['sum']:,}`; total `{fields['total_tokens']['sum']:,}`.",
        f"- Aggregate cached/input ratio: `{ratio:.2%}`.", "",
        "## Review blockers / next evidence", "",
        f"1. Usage completeness: `{exact['total_turns'] - exact['exact_turns']}` turns lack exact usage; review native OTel join and pending-line drain.",
        f"2. Worker totals: worker exact count is `{worker_exact}`; do not claim full Orchestra token cost from root-only observations.",
        f"3. Lifecycle closure: `{overview['open']}` turns are open/unfinished in this snapshot; do not classify them as failed.",
        "4. Benchmark readiness: no launcher-certified FAST/STANDARD cohort is present.", "",
        "## Provenance and privacy", "",
        f"Implementation: `codex-orchestra-global` / `{export['implementation']['branch']}` / `{export['implementation']['commit']}`; worktree clean: `{export['implementation']['worktree_clean']}`.",
        "This file is derived and path-free. It contains no prompts, responses, tool arguments/outputs, transcripts, raw ledger records, secrets, or cloud data.", "",
        "Machine-readable companion: `orchestra-usage-latest.json`.", "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=default_store(), help="local Orchestra telemetry store")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "snapshots")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    export = build_export(repo_root, args.store.expanduser().resolve())
    findings = privacy_scan(export)
    if findings:
        raise RuntimeError("privacy scan failed: " + ", ".join(findings[:10]))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "orchestra-usage-latest.json"
    md_path = args.output_dir / "orchestra-usage-latest.md"
    json_path.write_text(json.dumps(export, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(summary_markdown(export), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "ledger_sha256": export["source"]["ledger_sha256"], "turns": export["coverage"]["turns"]["total_turns"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
