"""Read-only dashboard projection for exact root/worker telemetry."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any

from scripts.orchestra_telemetry import TelemetryStore, _fold_run


def _row(run: dict[str, Any]) -> dict[str, Any]:
    orchestra = run.get("orchestra", {})
    root = run.get("usage", {})
    root_exact = root.get("total_tokens") if run.get("usage_quality") == "EXACT" else None
    worker_exact = orchestra.get("worker_total_tokens") if orchestra.get("worker_total_quality") == "EXACT" else None
    total_exact = orchestra.get("orchestra_total_tokens") if orchestra.get("orchestra_total_quality") == "EXACT" else None
    return {
        "run_id": run.get("run_id"),
        "session_id": run.get("session_id"),
        "turn_id": run.get("turn_id"),
        "status": run.get("turn_status", "UNKNOWN"),
        "worker_count": orchestra.get("actual_worker_count"),
        "root_usage_quality": run.get("usage_quality", "UNKNOWN"),
        "worker_usage_quality": orchestra.get("worker_total_quality", "UNKNOWN"),
        "orchestra_usage_quality": orchestra.get("orchestra_total_quality", "UNKNOWN"),
        "root_exact_total_tokens": root_exact,
        "worker_exact_total_tokens": worker_exact,
        "orchestra_exact_total_tokens": total_exact,
    }


def load_snapshot(store: TelemetryStore) -> dict[str, Any]:
    raw = store.ledger_path.read_bytes() if store.ledger_path.exists() else b""
    runs: dict[str, list[dict[str, Any]]] = {}
    for item in store.read():
        if item.get("run_id"):
            runs.setdefault(item["run_id"], []).append(item)
    turns = [_row(_fold_run(items)) for items in runs.values() if any(item.get("record_type") == "turn_start" for item in items)]
    turns.sort(key=lambda row: str(row.get("turn_id")))
    return {
        "schema": "orchestra_dashboard_v1",
        "source": {"ledger_sha256": hashlib.sha256(raw).hexdigest(), "ledger_bytes": len(raw)},
        "overview": {
            "total_turns": len(turns),
            "root_exact_total_tokens": sum(row["root_exact_total_tokens"] or 0 for row in turns) if all(row["root_exact_total_tokens"] is not None for row in turns) else None,
            "worker_exact_total_tokens": sum(row["worker_exact_total_tokens"] or 0 for row in turns) if all(row["worker_exact_total_tokens"] is not None for row in turns) else None,
            "orchestra_exact_total_tokens": sum(row["orchestra_exact_total_tokens"] or 0 for row in turns) if all(row["orchestra_exact_total_tokens"] is not None for row in turns) else None,
        },
        "turns": turns,
        "privacy": {"raw_prompt_or_tool_content": False},
    }


def build_html(snapshot: dict[str, Any]) -> str:
    def show(value: Any) -> str:
        return "UNKNOWN" if value is None else html.escape(str(value))

    rows = []
    for row in snapshot.get("turns", []):
        rows.append(
            "<tr>"
            f"<td>{show(row.get('turn_id'))}</td>"
            f"<td>{show(row.get('worker_count'))}</td>"
            f"<td>{show(row.get('root_exact_total_tokens'))}</td>"
            f"<td>{show(row.get('worker_exact_total_tokens'))}</td>"
            f"<td>{show(row.get('orchestra_exact_total_tokens'))}</td>"
            "</tr>"
        )
    return "<!doctype html><html><body><h1>Orchestra telemetry</h1><table>" \
        "<thead><tr><th>Turn</th><th>Workers</th><th>Root exact</th><th>Worker exact</th><th>Orchestra exact</th></tr></thead>" \
        f"<tbody>{''.join(rows)}</tbody></table></body></html>"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    args = parser.parse_args()
    print(build_html(load_snapshot(TelemetryStore(Path(args.store)))))
