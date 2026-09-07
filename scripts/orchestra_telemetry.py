#!/usr/bin/env python3
"""Passive, local-only CODEX ORCHESTRA TELEMETRY V1.

The collector is deliberately outside the model loop.  It reads only the
allowlisted numeric fields of Codex ``token_usage_record`` events and the
allowlisted lifecycle metadata delivered to command hooks.  It stores
normalized metadata in an append-only JSONL ledger.  It never calls Codex,
launches workers, or persists conversation content.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import tempfile
import time
import uuid
from typing import Any, Iterable


SCHEMA = "orchestra_telemetry_v1"
LEDGER_NAME = "ledger.jsonl"
LOCK_NAME = "ledger.lock"
RECORD_TYPES = {
    "run_start",
    "usage_observed",
    "metadata_observed",
    "worker_observed",
    "interruption_observed",
    "run_finalize",
    "allowance_snapshot",
    "annotation",
    "legacy_manual_observation",
}
MODES = {"DIRECT", "LIGHT", "HEAVY", "MANUAL", "UNKNOWN"}
TASK_CLASSES = {
    "CODE_CHANGE",
    "RESEARCH",
    "REVIEW",
    "DEBUGGING",
    "DATA_ANALYSIS",
    "OPERATIONS",
    "DOCUMENTATION",
    "OTHER",
    "UNKNOWN",
}
COMPLEXITIES = {"SMALL", "MEDIUM", "LARGE", "UNKNOWN"}
PROJECT_KINDS = {"GIT", "NO_PROJECT", "UNKNOWN"}
MEASUREMENT_SCOPES = {"UNCLASSIFIED", "SUBSTANTIVE", "TRIVIAL", "SYNTHETIC", "EXCLUDED"}
MEASUREMENT_OVERHEAD = {
    "ZERO_MODEL_OVERHEAD",
    "NEGLIGIBLE_LOCAL_OVERHEAD",
    "MATERIAL_OVERHEAD",
    "UNKNOWN",
}
MEASUREMENT_VALIDITY = {
    "VALID_LOW_OVERHEAD",
    "VALID_WITH_KNOWN_OVERHEAD",
    "INVALID_MEASUREMENT_PERTURBED",
    "UNKNOWN",
}
# Labels are deliberately path-free.  A caller can provide a normalized project
# name, but cannot accidentally persist a drive, UNC path, or directory string.
_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@_+-]{0,79}$")
_MODEL_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@+:/-]{0,119}$")
_TYPE_RE = re.compile(br'^\s*\{.*?"type"\s*:\s*"([^"\\]+)"')
_TURN_MODEL_RE = re.compile(br'"model"\s*:\s*"([^"\\]*)"')
_TURN_EFFORT_RE = re.compile(br'"effort"\s*:\s*"([^"\\]*)"')
_DISABLE_VALUES = {"0", "false", "off", "disabled", "no"}


class TelemetryError(RuntimeError):
    """Base class for fail-closed telemetry errors."""


class LedgerCorruptionError(TelemetryError):
    """The local telemetry ledger is not a valid V1 ledger."""


class DuplicateRecordError(TelemetryError):
    """An idempotency or uniqueness invariant would be violated."""


class SessionParseError(TelemetryError):
    """An allowlisted session event could not be safely parsed."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _label(value: str | None, *, field: str, required: bool = False) -> str | None:
    if value is None or value == "":
        if required:
            raise TelemetryError(f"{field} is required")
        return None
    if not _LABEL_RE.fullmatch(value):
        raise TelemetryError(
            f"{field} must be a short explicit label matching {_LABEL_RE.pattern}; "
            "prompt text and paths are not accepted"
        )
    return value


def _derived_label(value: str | None, *, fallback: str) -> str:
    """Turn local metadata into a short path-free label."""

    if not isinstance(value, str):
        return fallback
    candidate = re.sub(r"[^A-Za-z0-9_.@+-]+", "-", value.strip()).strip("-")[:80]
    return candidate or fallback


def _model_label(value: str | None, *, field: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not _MODEL_LABEL_RE.fullmatch(value):
        raise TelemetryError(f"{field} must be a short model identifier")
    return value


def telemetry_enabled() -> bool:
    """Return whether automatic hooks are enabled for this process."""

    return os.environ.get("CODEX_ORCHESTRA_TELEMETRY", "1").strip().lower() not in _DISABLE_VALUES


def _enum(value: str | None, allowed: set[str], *, field: str, default: str = "UNKNOWN") -> str:
    candidate = default if value in (None, "") else str(value).upper()
    if candidate not in allowed:
        raise TelemetryError(f"{field} must be one of {sorted(allowed)}")
    return candidate


def _nonnegative_int(value: Any, *, field: str, allow_none: bool = True) -> int | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TelemetryError(f"{field} must be a non-negative integer or null")
    return value


def _number(value: Any, *, field: str, allow_none: bool = True) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise TelemetryError(f"{field} must be a finite number or null")
    return float(value)


def _measurement(
    *,
    overhead_class: str = "NEGLIGIBLE_LOCAL_OVERHEAD",
    validity: str = "VALID_LOW_OVERHEAD",
    collector_wall_ms: float | None = None,
    collector_cpu_ms: float | None = None,
    bytes_read: int | None = None,
    bytes_written: int | None = None,
) -> dict[str, Any]:
    overhead = _enum(overhead_class, MEASUREMENT_OVERHEAD, field="measurement_overhead_class")
    valid = _enum(validity, MEASUREMENT_VALIDITY, field="measurement_validity")
    # These fields are intentionally fixed by the collector.  There is no CLI
    # switch that can make a user claim that telemetry caused no model work.
    return {
        "measurement_overhead_class": overhead,
        "measurement_validity": valid,
        "collector_wall_ms": _number(collector_wall_ms, field="collector_wall_ms"),
        "collector_cpu_ms": _number(collector_cpu_ms, field="collector_cpu_ms"),
        "bytes_read": _nonnegative_int(bytes_read, field="bytes_read"),
        "bytes_written": _nonnegative_int(bytes_written, field="bytes_written"),
        "telemetry_model_requests_added": 0,
        "telemetry_tokens_added": 0,
        "telemetry_worker_launches_added": 0,
        "telemetry_context_tokens_added": 0,
    }


def _usage(values: dict[str, Any] | None = None) -> dict[str, int | None]:
    values = values or {}
    result: dict[str, int | None] = {}
    for name in (
        "model_requests",
        "input_tokens",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    ):
        result[name] = _nonnegative_int(values.get(name), field=f"usage.{name}")
    return result


def _record(record_type: str, **fields: Any) -> dict[str, Any]:
    if record_type not in RECORD_TYPES:
        raise TelemetryError(f"unsupported record type: {record_type}")
    return {
        "schema": SCHEMA,
        "record_type": record_type,
        "record_id": _new_id("rec"),
        "recorded_at_utc": _utc_now(),
        **fields,
    }


def default_store_root() -> Path:
    home = os.environ.get("CODEX_HOME")
    base = Path(home).expanduser() if home else Path.home() / ".codex"
    return base / "orchestra-telemetry"


def _ensure_private_dir(path: Path) -> None:
    if path.exists() and path.is_symlink():
        raise TelemetryError(f"refusing symlink telemetry directory: {path}")
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise TelemetryError(f"telemetry path is not a directory: {path}")
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


class _LedgerLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any = None

    def __enter__(self) -> "_LedgerLock":
        _ensure_private_dir(self.path.parent)
        self.handle = self.path.open("a+b")
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.handle is None:
            return
        if os.name == "nt":
            import msvcrt

            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


def _allowed_fields(record_type: str) -> set[str]:
    common = {"schema", "record_type", "record_id", "recorded_at_utc"}
    fields = {
        "run_start": {"run_id", "task", "orchestra", "started_at_utc", "usage", "execution", "result", "economics", "measurement"},
        "usage_observed": {"run_id", "source_kind", "source_schema", "source_digest", "session_id", "thread_id", "attribution_role", "worker_id", "usage", "observed_event_count", "measurement"},
        "metadata_observed": {"run_id", "source_kind", "root_model", "root_reasoning_effort", "profile", "orchestra_mode", "project_kind", "project_label", "measurement_quality"},
        "worker_observed": {"run_id", "worker_id", "agent_type", "model", "reasoning_effort", "launch_status", "measurement_quality"},
        "interruption_observed": {"run_id", "session_id", "thread_id", "reason", "measurement_quality"},
        "run_finalize": {"run_id", "ended_at_utc", "usage", "execution", "result", "measurement"},
        "allowance_snapshot": {"run_id", "snapshot_kind", "source", "measurement_quality", "five_hour_allowance_pp", "weekly_allowance_pp", "credit_balance", "captured_at_utc"},
        "annotation": {"run_id", "reviewer_verdict", "first_pass", "rework_required", "rework_reason_code", "successor_run_id", "measurement_quality"},
        "legacy_manual_observation": {"observation_id", "label", "source_note", "measurement_quality", "root_model", "reasoning_effort", "mode", "worker_count", "input_tokens", "cached_input_tokens", "output_tokens", "total_tokens", "weekly_allowance_before_pp", "weekly_allowance_after_pp", "five_hour_allowance_before_pp", "five_hour_allowance_after_pp", "observed_at_utc"},
    }
    return common | fields[record_type]


def _validate_record(record: dict[str, Any]) -> None:
    if not isinstance(record, dict):
        raise LedgerCorruptionError("ledger record is not an object")
    if record.get("schema") != SCHEMA:
        raise LedgerCorruptionError("unsupported or missing telemetry schema")
    record_type = record.get("record_type")
    if record_type not in RECORD_TYPES:
        raise LedgerCorruptionError(f"unsupported ledger record type: {record_type!r}")
    required = {"schema", "record_type", "record_id", "recorded_at_utc"}
    if not required.issubset(record):
        raise LedgerCorruptionError("ledger record is missing common fields")
    if not isinstance(record["record_id"], str) or not record["record_id"]:
        raise LedgerCorruptionError("ledger record id is invalid")
    unknown = set(record) - _allowed_fields(record_type)
    if unknown:
        raise LedgerCorruptionError(f"unrecognized fields in {record_type}: {sorted(unknown)}")


class TelemetryStore:
    """A private JSONL ledger with atomic replace and cross-process locking."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root).expanduser() if root is not None else default_store_root()
        self.ledger_path = self.root / LEDGER_NAME
        self.lock_path = self.root / LOCK_NAME

    def _read_unlocked(self) -> list[dict[str, Any]]:
        if not self.ledger_path.exists():
            return []
        if self.ledger_path.is_symlink() or not self.ledger_path.is_file():
            raise LedgerCorruptionError("telemetry ledger is not a regular file")
        raw = self.ledger_path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            raise LedgerCorruptionError("telemetry ledger has an unterminated final record")
        records: list[dict[str, Any]] = []
        ids: set[str] = set()
        for line_number, line in enumerate(raw.splitlines(), 1):
            try:
                record = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise LedgerCorruptionError(f"invalid JSON at ledger line {line_number}") from exc
            _validate_record(record)
            if record["record_id"] in ids:
                raise LedgerCorruptionError(f"duplicate record id at ledger line {line_number}")
            ids.add(record["record_id"])
            records.append(record)
        return records

    def read(self) -> list[dict[str, Any]]:
        return self._read_unlocked()

    def _atomic_replace(self, old: bytes, addition: bytes) -> None:
        _ensure_private_dir(self.root)
        fd, temporary = tempfile.mkstemp(prefix=".ledger.", suffix=".tmp", dir=str(self.root))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(old)
                handle.write(addition)
                handle.flush()
                os.fsync(handle.fileno())
            replace_error: PermissionError | None = None
            # Windows scanners can hold the destination for a few
            # milliseconds.  Retry only this local atomic filesystem step;
            # no model/API operation is retried and no partial ledger is used.
            for delay in (0.0, 0.005, 0.02, 0.05):
                if delay:
                    time.sleep(delay)
                try:
                    os.replace(temporary, self.ledger_path)
                    replace_error = None
                    break
                except PermissionError as exc:
                    replace_error = exc
            if replace_error is not None:
                raise replace_error
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def append(self, record: dict[str, Any], *, unique_run_id: bool = False, unique_source_digest: bool = False) -> dict[str, Any]:
        _validate_record(record)
        with _LedgerLock(self.lock_path):
            existing = self._read_unlocked()
            if any(r["record_id"] == record["record_id"] for r in existing):
                raise DuplicateRecordError(f"duplicate record id: {record['record_id']}")
            if unique_run_id:
                run_id = record.get("run_id")
                if any(r.get("record_type") == "run_start" and r.get("run_id") == run_id for r in existing):
                    raise DuplicateRecordError(f"run_id already exists: {run_id}")
            if unique_source_digest:
                digest = record.get("source_digest")
                if any(r.get("record_type") == "usage_observed" and r.get("source_digest") == digest for r in existing):
                    raise DuplicateRecordError("source has already been ingested")
            previous = self.ledger_path.read_bytes() if self.ledger_path.exists() else b""
            line = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            self._atomic_replace(previous, line)
        return record

    def run_records(self, run_id: str) -> list[dict[str, Any]]:
        records = [r for r in self.read() if r.get("run_id") == run_id]
        if not any(r.get("record_type") == "run_start" for r in records):
            raise TelemetryError(f"unknown run_id: {run_id}")
        return records


def _empty_execution() -> dict[str, Any]:
    return {
        "wall_clock_seconds": None,
        "root_wall_seconds": None,
        "worker_wall_seconds": None,
        "retries": None,
        "context_compactions": None,
        "session_count": None,
        "process_exit_status": None,
        "abnormal_termination": None,
        "tool_call_count": None,
    }


def _empty_result() -> dict[str, Any]:
    return {
        "completed": None,
        "local_validation_status": "UNKNOWN",
        "tests_passed": None,
        "tests_failed": None,
        "files_changed": None,
        "commits_produced": None,
        "worktree_clean": None,
        "reviewer_verdict": "UNKNOWN",
        "first_pass": "UNKNOWN",
        "rework_required": None,
        "successor_run_id": None,
    }


def create_run(
    store: TelemetryStore,
    *,
    task_label: str,
    task_id: str | None = None,
    project_label: str | None = None,
    task_class: str = "UNKNOWN",
    complexity: str = "UNKNOWN",
    project_kind: str = "UNKNOWN",
    measurement_scope: str = "UNCLASSIFIED",
    mode: str = "UNKNOWN",
    root_model: str | None = None,
    root_reasoning_effort: str | None = None,
    requested_worker_count: int | None = None,
    actual_worker_count: int | None = None,
    workers: Iterable[dict[str, Any]] = (),
    max_concurrency: int | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    run_id = _label(run_id, field="run_id") or _new_id("run")
    task = {
        "task_id": _label(task_id, field="task_id"),
        "task_label": _label(task_label, field="task_label", required=True),
        "project_label": _label(project_label, field="project_label"),
        "project_kind": _enum(project_kind, PROJECT_KINDS, field="project_kind"),
        "task_class": _enum(task_class, TASK_CLASSES, field="task_class"),
        "complexity": _enum(complexity, COMPLEXITIES, field="complexity"),
        "measurement_scope": _enum(measurement_scope, MEASUREMENT_SCOPES, field="measurement_scope"),
    }
    root = {"model": _model_label(root_model, field="root_model"), "reasoning_effort": _label(root_reasoning_effort, field="root_reasoning_effort")}
    worker_list: list[dict[str, Any]] = []
    for index, worker in enumerate(workers):
        if not isinstance(worker, dict):
            raise TelemetryError("worker descriptor must be an object")
        worker_list.append({
            "ordinal": index,
            "model": _model_label(worker.get("model"), field="worker.model"),
            "reasoning_effort": _label(worker.get("reasoning_effort"), field="worker.reasoning_effort"),
            "launch_status": _enum(str(worker.get("launch_status", "UNKNOWN")), {"LAUNCHED", "COMPLETED", "CANCELLED", "FAILED", "UNKNOWN"}, field="worker.launch_status"),
        })
    if actual_worker_count is None and worker_list:
        actual_worker_count = len(worker_list)
    orchestra = {
        "mode": _enum(mode, MODES, field="orchestra.mode"),
        "root": root,
        "requested_worker_count": _nonnegative_int(requested_worker_count, field="requested_worker_count"),
        "actual_worker_count": _nonnegative_int(actual_worker_count, field="actual_worker_count"),
        "workers": worker_list,
        "max_concurrency": _nonnegative_int(max_concurrency, field="max_concurrency"),
        "attribution_quality": "DECLARED" if root["model"] or root["reasoning_effort"] or worker_list else "UNKNOWN",
        "attribution_source": "EXPLICIT_LAUNCH_METADATA" if root["model"] or root["reasoning_effort"] or worker_list else "UNKNOWN",
    }
    record = _record(
        "run_start",
        run_id=run_id,
        task=task,
        orchestra=orchestra,
        started_at_utc=_utc_now(),
        usage=_usage(),
        execution=_empty_execution(),
        result=_empty_result(),
        economics={"snapshots": [], "five_hour_pp_consumed": None, "weekly_pp_consumed": None},
        measurement=_measurement(collector_wall_ms=0.0, collector_cpu_ms=0.0),
    )
    return store.append(record, unique_run_id=True)


def _session_file(path: Path | str) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_symlink() or not candidate.is_file():
        raise SessionParseError("session source must be an explicit regular file, not a symlink or directory")
    if candidate.suffix.lower() not in {".jsonl", ".ndjson"}:
        raise SessionParseError("session source must use a .jsonl or .ndjson extension")
    return candidate


@dataclass(frozen=True)
class UsageObservation:
    source_digest: str
    bytes_read: int
    collector_wall_ms: float
    collector_cpu_ms: float
    session_id: str | None
    thread_id: str | None
    usage: dict[str, int | None]
    observed_event_count: int
    model: str | None = None
    reasoning_effort: str | None = None


def _event_kind(line: bytes) -> str | None:
    match = _TYPE_RE.match(line)
    return match.group(1).decode("ascii", errors="ignore") if match else None


def parse_session_usage(path: Path | str) -> UsageObservation:
    """Parse only numeric fields from allowlisted token usage events.

    Non-usage JSONL records are skipped as bytes.  Their prompt/response/tool
    content is never JSON-decoded, retained, or emitted.
    """

    source = _session_file(path)
    start_wall = time.perf_counter()
    start_cpu = time.process_time()
    digest = hashlib.sha256()
    bytes_read = 0
    event_count = 0
    session_id: str | None = None
    thread_id: str | None = None
    latest: dict[str, Any] | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    with source.open("rb") as handle:
        for line_number, line in enumerate(handle, 1):
            bytes_read += len(line)
            digest.update(line)
            event_kind = _event_kind(line)
            if event_kind == "turn_context":
                # The rollout wire format contains other prompt-adjacent
                # fields on this line.  Extract only the two allowlisted
                # scalar metadata values without JSON-decoding that content.
                if model is None:
                    match = _TURN_MODEL_RE.search(line)
                    if match:
                        model = _model_label(match.group(1).decode("utf-8", errors="ignore"), field="turn_context.model")
                if reasoning_effort is None:
                    match = _TURN_EFFORT_RE.search(line)
                    if match:
                        reasoning_effort = _label(match.group(1).decode("utf-8", errors="ignore"), field="turn_context.effort")
                continue
            if event_kind != "token_usage_record":
                continue
            try:
                event = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SessionParseError(f"invalid allowlisted usage event at line {line_number}") from exc
            if event.get("type") != "token_usage_record" or not isinstance(event.get("payload"), dict):
                raise SessionParseError(f"malformed usage event at line {line_number}")
            payload = event["payload"]
            raw_usage = payload.get("thread_token_usage") or payload.get("usage")
            if not isinstance(raw_usage, dict):
                continue
            latest = raw_usage
            event_count += 1
            if session_id is None and isinstance(payload.get("session_id"), str):
                session_id = payload["session_id"]
            if thread_id is None and isinstance(payload.get("thread_id"), str):
                thread_id = payload["thread_id"]
    wall_ms = (time.perf_counter() - start_wall) * 1000.0
    cpu_ms = (time.process_time() - start_cpu) * 1000.0
    observed_usage = _usage(latest)
    observed_usage["model_requests"] = event_count or None
    return UsageObservation(
        source_digest=digest.hexdigest(),
        bytes_read=bytes_read,
        collector_wall_ms=wall_ms,
        collector_cpu_ms=cpu_ms,
        session_id=session_id,
        thread_id=thread_id,
        usage=observed_usage,
        observed_event_count=event_count,
        model=model,
        reasoning_effort=reasoning_effort,
    )


def ingest_usage(
    store: TelemetryStore,
    run_id: str,
    observation: UsageObservation,
    *,
    source_kind: str = "CODEX_ROLLOUT_JSONL",
    source_schema: str = "codex_rollout_jsonl",
    attribution_role: str = "ROOT",
    worker_id: str | None = None,
) -> dict[str, Any]:
    store.run_records(run_id)
    record = _record(
        "usage_observed",
        run_id=run_id,
        source_kind=_label(source_kind, field="source_kind", required=True),
        source_schema=_label(source_schema, field="source_schema", required=True),
        source_digest=observation.source_digest,
        session_id=_label(observation.session_id, field="session_id"),
        thread_id=_label(observation.thread_id, field="thread_id"),
        attribution_role=_enum(attribution_role, {"ROOT", "WORKER", "UNKNOWN"}, field="attribution_role"),
        worker_id=_label(worker_id, field="worker_id"),
        usage=observation.usage,
        observed_event_count=observation.observed_event_count,
        measurement=_measurement(
            collector_wall_ms=observation.collector_wall_ms,
            collector_cpu_ms=observation.collector_cpu_ms,
            bytes_read=observation.bytes_read,
        ),
    )
    return store.append(record, unique_source_digest=True)


def ingest_synthetic_usage(store: TelemetryStore, run_id: str, values: dict[str, Any]) -> dict[str, Any]:
    store.run_records(run_id)
    usage = _usage(values)
    if usage["model_requests"] is None:
        usage["model_requests"] = 0
    record = _record(
        "usage_observed",
        run_id=run_id,
        source_kind="SYNTHETIC_FIXTURE",
        source_schema="synthetic_usage_v1",
        source_digest=hashlib.sha256((run_id + ":" + json.dumps(usage, sort_keys=True)).encode("utf-8")).hexdigest(),
        session_id=None,
        thread_id=None,
        attribution_role="UNKNOWN",
        worker_id=None,
        usage=usage,
        observed_event_count=usage["model_requests"],
        measurement=_measurement(collector_wall_ms=0.0, collector_cpu_ms=0.0, bytes_read=0),
    )
    return store.append(record, unique_source_digest=True)


def _aggregate_usage(records: Iterable[dict[str, Any]]) -> dict[str, int | None]:
    """Sum independent root/worker observations without treating missing data as zero."""

    usages = [record.get("usage") for record in records if isinstance(record.get("usage"), dict)]
    if not usages:
        return _usage()
    result: dict[str, int | None] = {}
    for field in (
        "model_requests",
        "input_tokens",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    ):
        values = [usage.get(field) for usage in usages]
        result[field] = sum(values) if all(isinstance(value, int) and not isinstance(value, bool) for value in values) else None
    return result


def observe_metadata(
    store: TelemetryStore,
    run_id: str,
    *,
    source_kind: str,
    root_model: str | None = None,
    root_reasoning_effort: str | None = None,
    profile: str | None = None,
    orchestra_mode: str | None = None,
    project_kind: str | None = None,
    project_label: str | None = None,
    measurement_quality: str = "EXACT_MACHINE_READABLE",
) -> dict[str, Any]:
    store.run_records(run_id)
    return store.append(_record(
        "metadata_observed",
        run_id=run_id,
        source_kind=_label(source_kind, field="source_kind", required=True),
        root_model=_model_label(root_model, field="root_model"),
        root_reasoning_effort=_label(root_reasoning_effort, field="root_reasoning_effort"),
        profile=_label(profile, field="profile"),
        orchestra_mode=_enum(orchestra_mode, MODES, field="orchestra_mode") if orchestra_mode else None,
        project_kind=_enum(project_kind, PROJECT_KINDS, field="project_kind") if project_kind else None,
        project_label=_label(project_label, field="project_label"),
        measurement_quality=_label(measurement_quality, field="measurement_quality", required=True),
    ))


def observe_worker(
    store: TelemetryStore,
    run_id: str,
    *,
    worker_id: str,
    agent_type: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    launch_status: str = "UNKNOWN",
    measurement_quality: str = "EXACT_MACHINE_READABLE",
) -> dict[str, Any]:
    store.run_records(run_id)
    return store.append(_record(
        "worker_observed",
        run_id=run_id,
        worker_id=_label(worker_id, field="worker_id", required=True),
        agent_type=_label(agent_type, field="agent_type"),
        model=_model_label(model, field="worker.model"),
        reasoning_effort=_label(reasoning_effort, field="worker.reasoning_effort"),
        launch_status=_enum(launch_status, {"LAUNCHED", "COMPLETED", "CANCELLED", "FAILED", "UNKNOWN"}, field="worker.launch_status"),
        measurement_quality=_label(measurement_quality, field="measurement_quality", required=True),
    ))


def observe_interruption(
    store: TelemetryStore,
    run_id: str,
    *,
    session_id: str | None,
    thread_id: str | None,
    reason: str = "INTERRUPTED",
) -> dict[str, Any]:
    store.run_records(run_id)
    return store.append(_record(
        "interruption_observed",
        run_id=run_id,
        session_id=_label(session_id, field="session_id"),
        thread_id=_label(thread_id, field="thread_id"),
        reason=_label(reason, field="reason", required=True),
        measurement_quality="EXACT_MACHINE_READABLE",
    ))


def _project_metadata(cwd: str | None) -> tuple[str, str | None]:
    """Derive a path-free project label without invoking a shell or Git."""

    if not isinstance(cwd, str) or not cwd:
        return "UNKNOWN", None
    try:
        candidate = Path(cwd).expanduser().resolve()
    except (OSError, RuntimeError):
        return "UNKNOWN", None
    if not candidate.exists() or not candidate.is_dir():
        return "UNKNOWN", None
    for directory in (candidate, *candidate.parents):
        if (directory / ".git").exists():
            return "GIT", _derived_label(directory.name, fallback="git-project")
    return "NO_PROJECT", None


def _hook_run_candidates(store: TelemetryStore, session_id: str) -> list[tuple[str, bool]]:
    records = store.read()
    finalized_run_ids = {
        record.get("run_id")
        for record in records
        if record.get("record_type") == "run_finalize" and isinstance(record.get("run_id"), str)
    }
    candidates: list[tuple[str, bool]] = []
    for record in records:
        if record.get("record_type") != "run_start":
            continue
        task = record.get("task")
        if isinstance(task, dict) and task.get("task_id") == session_id:
            run_id = record.get("run_id")
            if isinstance(run_id, str):
                candidates.append((run_id, run_id in finalized_run_ids))
    return candidates


def _ensure_automatic_run(store: TelemetryStore, event: dict[str, Any]) -> str:
    session_id = event.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise TelemetryError("hook event lacks session_id")
    candidates = _hook_run_candidates(store, session_id)
    for run_id, finalized in reversed(candidates):
        if not finalized:
            return run_id
    # A duplicate SessionEnd is an expected delivery/retry shape.  Bind it to
    # the already-finalized exact session instead of creating a second run.
    if event.get("hook_event_name") == "SessionEnd" and candidates:
        return candidates[-1][0]
    project_kind, project_label = _project_metadata(event.get("cwd"))
    base = _derived_label(f"auto_{session_id}", fallback="auto-session")
    run_id = base if not candidates else f"{base}_{len(candidates) + 1}"
    try:
        create_run(
            store,
            run_id=run_id,
            task_id=session_id,
            task_label="codex-session",
            project_label=project_label,
            project_kind=project_kind,
            measurement_scope="UNCLASSIFIED",
            root_model=_model_label(event.get("model"), field="hook.model"),
            mode="UNKNOWN",
        )
    except DuplicateRecordError:
        # Two lifecycle events for the same session can arrive concurrently.
        # Re-read the ledger and bind to the already-created exact run.
        for candidate, finalized in reversed(_hook_run_candidates(store, session_id)):
            if not finalized:
                return candidate
        raise
    return run_id


def _event_path(event: dict[str, Any], field: str) -> Path | None:
    value = event.get(field)
    if not isinstance(value, str) or not value:
        return None
    return Path(value).expanduser()


def _observe_rollout(
    store: TelemetryStore,
    run_id: str,
    path: Path | None,
    *,
    attribution_role: str,
    worker_id: str | None = None,
    expected_session_id: str | None = None,
) -> UsageObservation | None:
    if path is None:
        return None
    observation = parse_session_usage(path)
    if expected_session_id and observation.session_id != expected_session_id:
        raise SessionParseError("hook transcript session_id does not match lifecycle session_id")
    try:
        ingest_usage(
            store,
            run_id,
            observation,
            source_kind="CODEX_HOOK_EVENT",
            attribution_role=attribution_role,
            worker_id=worker_id,
        )
    except DuplicateRecordError as exc:
        if "source has already been ingested" not in str(exc):
            raise
    return observation


def handle_hook_event(store: TelemetryStore, event: dict[str, Any]) -> dict[str, Any]:
    """Handle one Codex lifecycle hook event without emitting hook output."""

    if not telemetry_enabled():
        return {"status": "DISABLED"}
    if not isinstance(event, dict):
        raise TelemetryError("hook input must be an object")
    event_name = event.get("hook_event_name")
    session_id = event.get("session_id")
    if not isinstance(event_name, str) or not isinstance(session_id, str):
        raise TelemetryError("hook input lacks event name or session_id")
    run_id = _ensure_automatic_run(store, event)
    if event_name == "SessionStart":
        observe_metadata(
            store,
            run_id,
            source_kind="CODEX_HOOK_EVENT",
            root_model=_model_label(event.get("model"), field="hook.model"),
            project_kind=_project_metadata(event.get("cwd"))[0],
            project_label=_project_metadata(event.get("cwd"))[1],
        )
        return {"status": "STARTED", "run_id": run_id}
    if event_name == "SubagentStart":
        worker_id = event.get("agent_id") or _derived_label(event.get("agent_type"), fallback="unknown-worker")
        observe_worker(
            store,
            run_id,
            worker_id=_derived_label(worker_id, fallback="unknown-worker"),
            agent_type=_derived_label(event.get("agent_type"), fallback="unknown") if event.get("agent_type") else None,
            model=_model_label(event.get("model"), field="hook.model"),
            launch_status="LAUNCHED",
        )
        return {"status": "WORKER_STARTED", "run_id": run_id}
    if event_name == "SubagentStop":
        path = _event_path(event, "agent_transcript_path")
        observation = _observe_rollout(
            store,
            run_id,
            path,
            attribution_role="WORKER",
            worker_id=event.get("agent_id"),
            expected_session_id=session_id,
        )
        worker_id = event.get("agent_id") or (observation.thread_id if observation else None) or "unknown-worker"
        observe_worker(
            store,
            run_id,
            worker_id=_derived_label(worker_id, fallback="unknown-worker"),
            agent_type=_derived_label(event.get("agent_type"), fallback="unknown") if event.get("agent_type") else None,
            model=_model_label(observation.model if observation else event.get("model"), field="hook.model"),
            reasoning_effort=observation.reasoning_effort if observation else None,
            launch_status="COMPLETED" if observation else "UNKNOWN",
        )
        return {"status": "WORKER_STOPPED", "run_id": run_id}
    if event_name == "Interrupt":
        observe_interruption(
            store,
            run_id,
            session_id=session_id,
            thread_id=event.get("turn_id"),
            reason="INTERRUPTED",
        )
        return {"status": "INTERRUPTED", "run_id": run_id}
    if event_name == "SessionEnd":
        existing_records = store.run_records(run_id)
        if any(record.get("record_type") == "run_finalize" for record in existing_records):
            return {
                "status": "FINALIZED",
                "run_id": run_id,
                "usage_observed": any(
                    record.get("record_type") == "usage_observed"
                    and record.get("attribution_role") == "ROOT"
                    for record in existing_records
                ),
            }
        path = _event_path(event, "transcript_path")
        observation = _observe_rollout(store, run_id, path, attribution_role="ROOT", expected_session_id=session_id)
        observe_metadata(
            store,
            run_id,
            source_kind="CODEX_HOOK_EVENT",
            root_model=_model_label(observation.model if observation else event.get("model"), field="hook.model"),
            root_reasoning_effort=observation.reasoning_effort if observation else None,
        )
        records = store.run_records(run_id)
        usage = _aggregate_usage(record for record in records if record.get("record_type") == "usage_observed")
        interruptions = [record for record in records if record.get("record_type") == "interruption_observed"]
        try:
            finalize_run(
                store,
                run_id,
                usage=usage,
                execution={"session_count": 1, "abnormal_termination": "INTERRUPTED" if interruptions else None},
                result={"completed": False if interruptions else True},
            )
        except DuplicateRecordError:
            pass
        return {"status": "FINALIZED", "run_id": run_id, "usage_observed": observation is not None}
    return {"status": "IGNORED", "run_id": run_id, "event": event_name}


def finalize_run(store: TelemetryStore, run_id: str, *, ended_at_utc: str | None = None, usage: dict[str, Any] | None = None, execution: dict[str, Any] | None = None, result: dict[str, Any] | None = None, measurement: dict[str, Any] | None = None) -> dict[str, Any]:
    records = store.run_records(run_id)
    if any(r.get("record_type") == "run_finalize" for r in records):
        raise DuplicateRecordError(f"run already finalized: {run_id}")
    final_execution = _empty_execution()
    if execution:
        final_execution.update(execution)
    final_result = _empty_result()
    if result:
        final_result.update(result)
    final_usage = _usage(usage) if usage is not None else _aggregate_usage(
        record for record in records if record.get("record_type") == "usage_observed"
    )
    final_measurement = measurement or _measurement(collector_wall_ms=0.0, collector_cpu_ms=0.0)
    record = _record(
        "run_finalize",
        run_id=_label(run_id, field="run_id", required=True),
        ended_at_utc=ended_at_utc or _utc_now(),
        usage=final_usage,
        execution=final_execution,
        result=final_result,
        measurement=final_measurement,
    )
    return store.append(record)


def add_snapshot(store: TelemetryStore, run_id: str, *, source: str, five_hour_allowance_pp: float | None = None, weekly_allowance_pp: float | None = None, credit_balance: float | None = None, snapshot_kind: str = "BEFORE", measurement_quality: str = "EXACT_MACHINE_READABLE") -> dict[str, Any]:
    store.run_records(run_id)
    return store.append(_record(
        "allowance_snapshot",
        run_id=run_id,
        snapshot_kind=_enum(snapshot_kind, {"BEFORE", "AFTER", "POINT_IN_TIME"}, field="snapshot_kind"),
        source=_label(source, field="source", required=True),
        measurement_quality=_label(measurement_quality, field="measurement_quality", required=True),
        five_hour_allowance_pp=_number(five_hour_allowance_pp, field="five_hour_allowance_pp"),
        weekly_allowance_pp=_number(weekly_allowance_pp, field="weekly_allowance_pp"),
        credit_balance=_number(credit_balance, field="credit_balance"),
        captured_at_utc=_utc_now(),
    ))


def add_annotation(store: TelemetryStore, run_id: str, *, reviewer_verdict: str = "UNKNOWN", first_pass: str = "UNKNOWN", rework_required: bool | None = None, rework_reason_code: str | None = None, successor_run_id: str | None = None, measurement_quality: str = "USER_SUPPLIED") -> dict[str, Any]:
    store.run_records(run_id)
    verdict = _enum(reviewer_verdict, {"PASS", "FAIL", "UNKNOWN"}, field="reviewer_verdict")
    first = _enum(first_pass, {"PASS", "FAIL", "UNKNOWN"}, field="first_pass")
    if rework_required is not None and not isinstance(rework_required, bool):
        raise TelemetryError("rework_required must be true, false, or null")
    return store.append(_record(
        "annotation",
        run_id=run_id,
        reviewer_verdict=verdict,
        first_pass=first,
        rework_required=rework_required,
        rework_reason_code=_label(rework_reason_code, field="rework_reason_code"),
        successor_run_id=_label(successor_run_id, field="successor_run_id"),
        measurement_quality=_label(measurement_quality, field="measurement_quality", required=True),
    ))


def import_manual(store: TelemetryStore, *, label: str, source_note: str, root_model: str | None = None, reasoning_effort: str | None = None, mode: str = "MANUAL", worker_count: int | None = None, values: dict[str, Any] | None = None, allowances: dict[str, Any] | None = None) -> dict[str, Any]:
    values = values or {}
    allowances = allowances or {}
    return store.append(_record(
        "legacy_manual_observation",
        observation_id=_new_id("manual"),
        label=_label(label, field="label", required=True),
        source_note=_label(source_note, field="source_note", required=True),
        measurement_quality="APPROXIMATE_MANUAL",
        root_model=_label(root_model, field="root_model"),
        reasoning_effort=_label(reasoning_effort, field="reasoning_effort"),
        mode=_enum(mode, MODES, field="mode"),
        worker_count=_nonnegative_int(worker_count, field="worker_count"),
        input_tokens=_nonnegative_int(values.get("input_tokens"), field="input_tokens"),
        cached_input_tokens=_nonnegative_int(values.get("cached_input_tokens"), field="cached_input_tokens"),
        output_tokens=_nonnegative_int(values.get("output_tokens"), field="output_tokens"),
        total_tokens=_nonnegative_int(values.get("total_tokens"), field="total_tokens"),
        weekly_allowance_before_pp=_number(allowances.get("weekly_before"), field="weekly_before"),
        weekly_allowance_after_pp=_number(allowances.get("weekly_after"), field="weekly_after"),
        five_hour_allowance_before_pp=_number(allowances.get("five_hour_before"), field="five_hour_before"),
        five_hour_allowance_after_pp=_number(allowances.get("five_hour_after"), field="five_hour_after"),
        observed_at_utc=_utc_now(),
    ))


def _delta(before: float | None, after: float | None) -> float | None:
    if before is None or after is None or after > before:
        return None
    return round(before - after, 6)


def _median(values: Iterable[Any]) -> float | None:
    known = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return statistics.median(known) if known else None


def _fold_run(records: list[dict[str, Any]]) -> dict[str, Any]:
    start = next(r for r in records if r["record_type"] == "run_start")
    run = json.loads(json.dumps(start))
    snapshots: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    workers: dict[str, dict[str, Any]] = {}
    usage_records: list[dict[str, Any]] = []
    for record in records:
        kind = record["record_type"]
        if kind == "usage_observed":
            usage_records.append(record)
            run["usage"] = _aggregate_usage(usage_records)
            run["measurement"] = record["measurement"]
        elif kind == "metadata_observed":
            if record.get("root_model") is not None:
                run["orchestra"]["root"]["model"] = record["root_model"]
            if record.get("root_reasoning_effort") is not None:
                run["orchestra"]["root"]["reasoning_effort"] = record["root_reasoning_effort"]
            if record.get("profile") is not None:
                run["orchestra"]["root"]["profile"] = record["profile"]
            if record.get("orchestra_mode") is not None:
                run["orchestra"]["mode"] = record["orchestra_mode"]
            if record.get("project_kind") is not None:
                run["task"]["project_kind"] = record["project_kind"]
            if record.get("project_label") is not None:
                run["task"]["project_label"] = record["project_label"]
        elif kind == "worker_observed":
            workers[record["worker_id"]] = {
                "worker_id": record["worker_id"],
                "agent_type": record.get("agent_type"),
                "model": record.get("model"),
                "reasoning_effort": record.get("reasoning_effort"),
                "launch_status": record.get("launch_status", "UNKNOWN"),
            }
        elif kind == "interruption_observed":
            run["execution"]["abnormal_termination"] = record.get("reason", "INTERRUPTED")
        elif kind == "run_finalize":
            run["ended_at_utc"] = record["ended_at_utc"]
            run["usage"] = record["usage"]
            run["execution"] = record["execution"]
            run["result"] = record["result"]
            run["measurement"] = record["measurement"]
        elif kind == "allowance_snapshot":
            snapshots.append(record)
        elif kind == "annotation":
            annotations.append(record)
    if workers:
        run["orchestra"]["workers"] = list(workers.values())
        run["orchestra"]["actual_worker_count"] = len(workers)
        run["orchestra"]["attribution_quality"] = "ROOT_WORKER_USAGE_PARTIAL"
        run["orchestra"]["attribution_source"] = "CODEX_LIFECYCLE_HOOKS"
    elif any(record.get("source_kind") == "CODEX_HOOK_EVENT" for record in records):
        run["orchestra"]["attribution_quality"] = "ROOT_WORKER_USAGE_PARTIAL"
        run["orchestra"]["attribution_source"] = "CODEX_LIFECYCLE_HOOKS"
    weekly_pairs = [s for s in snapshots if s.get("weekly_allowance_pp") is not None]
    five_pairs = [s for s in snapshots if s.get("five_hour_allowance_pp") is not None]
    run["economics"] = {
        "snapshots": snapshots,
        "weekly_pp_consumed": _delta(
            next((s["weekly_allowance_pp"] for s in weekly_pairs if s["snapshot_kind"] == "BEFORE"), None),
            next((s["weekly_allowance_pp"] for s in reversed(weekly_pairs) if s["snapshot_kind"] == "AFTER"), None),
        ),
        "five_hour_pp_consumed": _delta(
            next((s["five_hour_allowance_pp"] for s in five_pairs if s["snapshot_kind"] == "BEFORE"), None),
            next((s["five_hour_allowance_pp"] for s in reversed(five_pairs) if s["snapshot_kind"] == "AFTER"), None),
        ),
    }
    run["annotations"] = annotations
    if annotations:
        latest = annotations[-1]
        run["result"]["reviewer_verdict"] = latest["reviewer_verdict"]
        run["result"]["first_pass"] = latest["first_pass"]
        run["result"]["rework_required"] = latest["rework_required"]
        run["result"]["successor_run_id"] = latest["successor_run_id"]
    return run


def report(store: TelemetryStore, *, group_by: list[str] | None = None, include_synthetic: bool = False) -> dict[str, Any]:
    records = store.read()
    runs: dict[str, list[dict[str, Any]]] = {}
    manual: list[dict[str, Any]] = []
    for record in records:
        if record["record_type"] == "legacy_manual_observation":
            manual.append(record)
        elif record.get("run_id"):
            runs.setdefault(record["run_id"], []).append(record)
    synthetic_run_ids = {
        run_id
        for run_id, items in runs.items()
        if any(
            item.get("record_type") == "usage_observed"
            and item.get("source_kind") == "SYNTHETIC_FIXTURE"
            for item in items
        )
    }
    report_runs = (
        runs
        if include_synthetic
        else {run_id: items for run_id, items in runs.items() if run_id not in synthetic_run_ids}
    )
    folded = [_fold_run(items) for items in report_runs.values()]
    folded.sort(key=lambda item: item["run_id"])
    fields = group_by or ["task_class", "mode", "root_model", "reasoning_effort", "worker_count"]

    def group_key(run: dict[str, Any]) -> tuple[Any, ...]:
        mapping = {
            "task_class": run["task"]["task_class"],
            "mode": run["orchestra"]["mode"],
            "root_model": run["orchestra"]["root"]["model"] or "UNKNOWN",
            "reasoning_effort": run["orchestra"]["root"]["reasoning_effort"] or "UNKNOWN",
            "worker_count": run["orchestra"]["actual_worker_count"],
        }
        unknown = set(fields) - set(mapping)
        if unknown:
            raise TelemetryError(f"unsupported report grouping: {sorted(unknown)}")
        return tuple(mapping[field] for field in fields)

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for run in folded:
        grouped.setdefault(group_key(run), []).append(run)
    summaries: list[dict[str, Any]] = []
    for key in sorted(grouped, key=lambda value: tuple("" if item is None else str(item) for item in value)):
        members = grouped[key]
        completed = [r["result"]["completed"] for r in members if r["result"]["completed"] is not None]
        first_pass = [r["result"]["first_pass"] for r in members if r["result"]["first_pass"] != "UNKNOWN"]
        rework = [r["result"]["rework_required"] for r in members if r["result"]["rework_required"] is not None]
        total_allowance = [r["economics"]["weekly_pp_consumed"] for r in members if r["economics"]["weekly_pp_consumed"] is not None]
        accepted = sum(1 for r in members if r["result"]["reviewer_verdict"] == "PASS")
        allowance_sum = sum(total_allowance) if total_allowance else None
        summaries.append({
            "group": dict(zip(fields, key)),
            "runs": len(members),
            "completion_rate": (sum(completed) / len(completed)) if completed else None,
            "first_pass_pass_rate": (sum(value == "PASS" for value in first_pass) / len(first_pass)) if first_pass else None,
            "rework_rate": (sum(rework) / len(rework)) if rework else None,
            "median_wall_time_seconds": _median(r["execution"]["wall_clock_seconds"] for r in members),
            "median_input_tokens": _median(r["usage"]["input_tokens"] for r in members),
            "median_cached_input_tokens": _median(r["usage"]["cached_input_tokens"] for r in members),
            "median_output_tokens": _median(r["usage"]["output_tokens"] for r in members),
            "median_total_tokens": _median(r["usage"]["total_tokens"] for r in members),
            "median_weekly_allowance_pp_consumed": _median(total_allowance),
            "median_five_hour_allowance_pp_consumed": _median(r["economics"]["five_hour_pp_consumed"] for r in members),
            "accepted_runs_per_weekly_allowance_pp": (accepted / allowance_sum) if allowance_sum and allowance_sum > 0 else None,
        })
    return {
        "schema": SCHEMA,
        "report_kind": "DESCRIPTIVE_OFFLINE",
        "groups": summaries,
        "run_count": len(folded),
        "include_synthetic": include_synthetic,
        "synthetic_run_count": len(synthetic_run_ids),
        "synthetic_runs_excluded": 0 if include_synthetic else len(synthetic_run_ids),
        "legacy_manual_observation_count": len(manual),
        "manual_observations_are_separate": True,
        "routing_recommendations": None,
    }


def _json_print(value: Any) -> None:
    print(json.dumps(value, sort_keys=True, indent=2))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=None, help="telemetry directory; defaults to CODEX_HOME/orchestra-telemetry")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--run-id")
    create.add_argument("--task-id")
    create.add_argument("--task-label", required=True)
    create.add_argument("--project-label")
    create.add_argument("--task-class", choices=sorted(TASK_CLASSES), default="UNKNOWN")
    create.add_argument("--complexity", choices=sorted(COMPLEXITIES), default="UNKNOWN")
    create.add_argument("--mode", choices=sorted(MODES), default="UNKNOWN")
    create.add_argument("--root-model")
    create.add_argument("--root-reasoning-effort")
    create.add_argument("--requested-worker-count", type=int)
    create.add_argument("--actual-worker-count", type=int)
    create.add_argument("--max-concurrency", type=int)
    create.add_argument("--worker", action="append", default=[], metavar="MODEL:EFFORT:STATUS")

    ingest = sub.add_parser("ingest")
    ingest.add_argument("--run-id", required=True)
    ingest.add_argument("--session-file", required=True)
    sub.add_parser("hook", help="consume one Codex lifecycle hook JSON object from stdin")
    synthetic = sub.add_parser("ingest-synthetic")
    synthetic.add_argument("--run-id", required=True)
    for name in ("model-requests", "input-tokens", "cached-input-tokens", "cache-write-input-tokens", "output-tokens", "reasoning-output-tokens", "total-tokens"):
        synthetic.add_argument("--" + name, type=int)

    finalize = sub.add_parser("finalize")
    finalize.add_argument("--run-id", required=True)
    finalize.add_argument("--session-file")
    finalize.add_argument("--completed", type=lambda value: value.lower() in {"1", "true", "yes"})
    finalize.add_argument("--validation-status", choices=["PASS", "FAIL", "UNKNOWN"], default="UNKNOWN")
    finalize.add_argument("--tests-passed", type=int)
    finalize.add_argument("--tests-failed", type=int)
    finalize.add_argument("--files-changed", type=int)
    finalize.add_argument("--commits-produced", type=int)
    finalize.add_argument("--worktree-clean", type=lambda value: value.lower() in {"1", "true", "yes"})
    finalize.add_argument("--process-exit-status", type=int)
    finalize.add_argument("--retries", type=int)
    finalize.add_argument("--context-compactions", type=int)
    finalize.add_argument("--tool-call-count", type=int)
    finalize.add_argument("--wall-clock-seconds", type=float)

    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--run-id", required=True)
    snapshot.add_argument("--source", required=True)
    snapshot.add_argument("--snapshot-kind", choices=["BEFORE", "AFTER", "POINT_IN_TIME"], default="POINT_IN_TIME")
    snapshot.add_argument("--five-hour-allowance-pp", type=float)
    snapshot.add_argument("--weekly-allowance-pp", type=float)
    snapshot.add_argument("--credit-balance", type=float)
    snapshot.add_argument("--measurement-quality", default="EXACT_MACHINE_READABLE")

    annotation = sub.add_parser("annotate")
    annotation.add_argument("--run-id", required=True)
    annotation.add_argument("--reviewer-verdict", choices=["PASS", "FAIL", "UNKNOWN"], default="UNKNOWN")
    annotation.add_argument("--first-pass", choices=["PASS", "FAIL", "UNKNOWN"], default="UNKNOWN")
    annotation.add_argument("--rework-required", type=lambda value: value.lower() in {"1", "true", "yes"})
    annotation.add_argument("--rework-reason-code")
    annotation.add_argument("--successor-run-id")

    manual = sub.add_parser("import-manual")
    manual.add_argument("--label", required=True)
    manual.add_argument("--source-note", required=True)
    manual.add_argument("--root-model")
    manual.add_argument("--reasoning-effort")
    manual.add_argument("--mode", choices=sorted(MODES), default="MANUAL")
    manual.add_argument("--worker-count", type=int)
    for name in ("input-tokens", "cached-input-tokens", "output-tokens", "total-tokens"):
        manual.add_argument("--" + name, type=int)
    for name in ("weekly-before", "weekly-after", "five-hour-before", "five-hour-after"):
        manual.add_argument("--" + name, type=float)

    summary = sub.add_parser("report")
    summary.add_argument("--group-by", action="append", choices=["task_class", "mode", "root_model", "reasoning_effort", "worker_count"])
    summary.add_argument("--include-synthetic", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    store = TelemetryStore(args.store)
    try:
        if args.command == "hook":
            # Hooks are advisory and fail-open.  Never write hook output to
            # stdout because Codex treats it as model-visible context.
            try:
                payload = json.load(sys.stdin)
                handle_hook_event(store, payload)
            except Exception:
                pass
            return 0
        if args.command == "create":
            workers = []
            for descriptor in args.worker:
                parts = descriptor.split(":")
                if len(parts) != 3:
                    raise TelemetryError("--worker must be MODEL:EFFORT:STATUS")
                workers.append({"model": parts[0], "reasoning_effort": parts[1], "launch_status": parts[2]})
            result = create_run(store, task_label=args.task_label, task_id=args.task_id, project_label=args.project_label, task_class=args.task_class, complexity=args.complexity, mode=args.mode, root_model=args.root_model, root_reasoning_effort=args.root_reasoning_effort, requested_worker_count=args.requested_worker_count, actual_worker_count=args.actual_worker_count, workers=workers, max_concurrency=args.max_concurrency, run_id=args.run_id)
        elif args.command == "ingest":
            result = ingest_usage(store, args.run_id, parse_session_usage(args.session_file))
        elif args.command == "ingest-synthetic":
            result = ingest_synthetic_usage(store, args.run_id, {"model_requests": args.model_requests, "input_tokens": args.input_tokens, "cached_input_tokens": args.cached_input_tokens, "cache_write_input_tokens": args.cache_write_input_tokens, "output_tokens": args.output_tokens, "reasoning_output_tokens": args.reasoning_output_tokens, "total_tokens": args.total_tokens})
        elif args.command == "finalize":
            observation = None
            if args.session_file:
                observation = parse_session_usage(args.session_file)
                try:
                    ingest_usage(store, args.run_id, observation)
                except DuplicateRecordError as exc:
                    if "source has already been ingested" not in str(exc):
                        raise
            run_records = store.run_records(args.run_id)
            latest_usage = next((r["usage"] for r in reversed(run_records) if r["record_type"] == "usage_observed"), _usage())
            if observation is not None:
                latest_usage = observation.usage
            execution = {"wall_clock_seconds": args.wall_clock_seconds, "process_exit_status": args.process_exit_status, "retries": args.retries, "context_compactions": args.context_compactions, "tool_call_count": args.tool_call_count}
            result_fields = {"completed": args.completed, "local_validation_status": args.validation_status, "tests_passed": args.tests_passed, "tests_failed": args.tests_failed, "files_changed": args.files_changed, "commits_produced": args.commits_produced, "worktree_clean": args.worktree_clean}
            measurement = _measurement(collector_wall_ms=(observation.collector_wall_ms if observation else 0.0), collector_cpu_ms=(observation.collector_cpu_ms if observation else 0.0), bytes_read=(observation.bytes_read if observation else 0))
            result = finalize_run(store, args.run_id, usage=latest_usage, execution=execution, result=result_fields, measurement=measurement)
        elif args.command == "snapshot":
            result = add_snapshot(store, args.run_id, source=args.source, snapshot_kind=args.snapshot_kind, five_hour_allowance_pp=args.five_hour_allowance_pp, weekly_allowance_pp=args.weekly_allowance_pp, credit_balance=args.credit_balance, measurement_quality=args.measurement_quality)
        elif args.command == "annotate":
            result = add_annotation(store, args.run_id, reviewer_verdict=args.reviewer_verdict, first_pass=args.first_pass, rework_required=args.rework_required, rework_reason_code=args.rework_reason_code, successor_run_id=args.successor_run_id)
        elif args.command == "import-manual":
            result = import_manual(store, label=args.label, source_note=args.source_note, root_model=args.root_model, reasoning_effort=args.reasoning_effort, mode=args.mode, worker_count=args.worker_count, values={"input_tokens": args.input_tokens, "cached_input_tokens": args.cached_input_tokens, "output_tokens": args.output_tokens, "total_tokens": args.total_tokens}, allowances={"weekly_before": args.weekly_before, "weekly_after": args.weekly_after, "five_hour_before": args.five_hour_before, "five_hour_after": args.five_hour_after})
        elif args.command == "report":
            _json_print(report(store, group_by=args.group_by, include_synthetic=args.include_synthetic))
            return 0
        else:
            raise TelemetryError(f"unsupported command: {args.command}")
        _json_print(result)
        return 0
    except TelemetryError as exc:
        print(f"TELEMETRY_ERROR={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
