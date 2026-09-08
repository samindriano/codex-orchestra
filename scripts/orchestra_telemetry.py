#!/usr/bin/env python3
"""Passive, local-only CODEX ORCHESTRA TELEMETRY V1.2.

The automatic hook path consumes only stable lifecycle metadata delivered to
command hooks.  It deliberately accepts, but never opens or parses,
``transcript_path`` or ``agent_transcript_path``.  Exact usage is an explicit
adapter for the documented ``codex exec --json`` JSONL stream or trusted
launcher metadata; interactive sessions without one of those sources retain
null usage fields.  The collector never calls Codex, launches workers, or
persists conversation content.
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
import tomllib
import uuid
from typing import Any, Iterable


SCHEMA = "orchestra_telemetry_v1"
LEDGER_NAME = "ledger.jsonl"
LOCK_NAME = "ledger.lock"
RECORD_TYPES = {
    "run_start",
    "usage_observed",
    "session_observed",
    "turn_start",
    "turn_finalize",
    "metadata_observed",
    "worker_observed",
    "interruption_observed",
    "run_finalize",
    "allowance_snapshot",
    "annotation",
    "legacy_manual_observation",
}
MODES = {"DIRECT", "LIGHT", "HEAVY", "MANUAL", "NOT_APPLICABLE", "UNKNOWN"}
SPEED_MODES = {"FAST", "STANDARD", "UNKNOWN"}
SPEED_MODE_SOURCES = {
    "LAUNCHER_EXPLICIT",
    "EXPLICIT_COMMAND",
    "ORCHESTRA_LAUNCHER",
    "STABLE_RUNTIME_METADATA",
    "SESSION_LATCH",
    "CODEX_CONFIG_EXPLICIT",
    "LEGACY_MISSING",
    "NONE",
}
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
PROJECT_KINDS = {"GIT", "NON_GIT", "NO_PROJECT", "UNKNOWN"}
USAGE_SOURCES = {"CODEX_EXEC_JSON", "ORCHESTRA_LAUNCHER", "STABLE_RUNTIME_METADATA", "MANUAL", "NONE"}
USAGE_QUALITY = {"EXACT", "PARTIAL", "UNKNOWN"}
USAGE_SOURCE_CAPABILITIES = {
    "USAGE_SOURCE_SUPPORTED",
    "USAGE_SOURCE_PARTIAL",
    "USAGE_SOURCE_UNSTABLE",
    "USAGE_SOURCE_UNAVAILABLE",
}
REASONING_EFFORT_SOURCES = {"LAUNCHER", "PROFILE", "STABLE_RUNTIME_METADATA", "NONE"}
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
MEASUREMENT_GENERATIONS = {"SESSION_LEVEL_V1", "TURN_LEVEL_V1_2"}
TURN_STATUSES = {"STARTED", "COMPLETED", "INTERRUPTED", "FAILED", "UNKNOWN"}
# Labels are deliberately path-free.  A caller can provide a normalized project
# name, but cannot accidentally persist a drive, UNC path, or directory string.
_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@_+-]{0,79}$")
_MODEL_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@+:/-]{0,119}$")
_DISABLE_VALUES = {"0", "false", "off", "disabled", "no"}
_LAUNCHER_METADATA_ENV = "CODEX_ORCHESTRA_LAUNCHER_METADATA"
_LAUNCHER_METADATA_SCHEMA = "orchestra_launcher_v1"
_LAUNCHER_METADATA_MAX_BYTES = 8192


class TelemetryError(RuntimeError):
    """Base class for fail-closed telemetry errors."""


class LedgerCorruptionError(TelemetryError):
    """The local telemetry ledger is not a valid V1 ledger."""


class DuplicateRecordError(TelemetryError):
    """An idempotency or uniqueness invariant would be violated."""


class SessionParseError(TelemetryError):
    """Legacy transcript parsing was requested; it is intentionally disabled."""


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
        "reasoning_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    ):
        result[name] = _nonnegative_int(values.get(name), field=f"usage.{name}")
    if result["reasoning_tokens"] is None:
        result["reasoning_tokens"] = result["reasoning_output_tokens"]
    if result["reasoning_output_tokens"] is None:
        result["reasoning_output_tokens"] = result["reasoning_tokens"]
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
    return _codex_home_path() / "orchestra-telemetry"


def _codex_home_path() -> Path:
    home = os.environ.get("CODEX_HOME")
    return Path(home).expanduser() if home else Path.home() / ".codex"


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
        "run_start": {"run_id", "task", "orchestra", "started_at_utc", "usage", "usage_source", "usage_quality", "reasoning_effort_source", "execution", "result", "economics", "measurement", "measurement_generation", "session_id", "turn_id"},
        "turn_start": {"run_id", "task", "orchestra", "started_at_utc", "usage", "usage_source", "usage_quality", "reasoning_effort_source", "execution", "result", "economics", "measurement", "measurement_generation", "session_id", "turn_id", "boundary_source", "turn_status"},
        "session_observed": {"session_id", "lifecycle", "root_model", "root_reasoning_effort", "reasoning_effort_source", "profile", "orchestra_mode", "speed_mode", "speed_mode_source", "launcher", "project_kind", "project_label", "project_repo_label", "project_repo_id", "project_branch", "measurement_generation", "measurement_quality"},
        "usage_observed": {"run_id", "source_kind", "source_schema", "source_digest", "source_capability", "usage_source", "usage_quality", "session_id", "thread_id", "turn_id", "attribution_role", "worker_id", "usage", "observed_event_count", "measurement", "measurement_generation"},
        "metadata_observed": {"run_id", "source_kind", "session_id", "turn_id", "measurement_generation", "root_model", "root_reasoning_effort", "reasoning_effort_source", "profile", "orchestra_mode", "speed_mode", "speed_mode_source", "launcher", "project_kind", "project_label", "project_repo_label", "project_repo_id", "project_branch", "measurement_quality"},
        "worker_observed": {"run_id", "session_id", "turn_id", "measurement_generation", "worker_id", "agent_type", "model", "reasoning_effort", "reasoning_effort_source", "launch_status", "measurement_quality"},
        "interruption_observed": {"run_id", "session_id", "thread_id", "turn_id", "measurement_generation", "reason", "measurement_quality"},
        "run_finalize": {"run_id", "ended_at_utc", "usage", "usage_source", "usage_quality", "reasoning_effort_source", "execution", "result", "measurement", "measurement_generation", "session_id", "turn_id"},
        "turn_finalize": {"run_id", "ended_at_utc", "usage", "usage_source", "usage_quality", "reasoning_effort_source", "execution", "result", "measurement", "measurement_generation", "session_id", "turn_id", "turn_status"},
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
                if any(r.get("record_type") in {"run_start", "turn_start"} and r.get("run_id") == run_id for r in existing):
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
        if not any(r.get("record_type") in {"run_start", "turn_start"} for r in records):
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
    project_repo_label: str | None = None,
    project_repo_id: str | None = None,
    project_branch: str | None = None,
    task_class: str = "UNKNOWN",
    complexity: str = "UNKNOWN",
    project_kind: str = "UNKNOWN",
    measurement_scope: str = "UNCLASSIFIED",
    mode: str = "UNKNOWN",
    root_model: str | None = None,
    root_reasoning_effort: str | None = None,
    profile: str | None = None,
    reasoning_effort_source: str | None = None,
    usage_source: str = "NONE",
    usage_quality: str = "UNKNOWN",
    requested_worker_count: int | None = None,
    actual_worker_count: int | None = None,
    workers: Iterable[dict[str, Any]] = (),
    max_concurrency: int | None = None,
    run_id: str | None = None,
    record_type: str = "run_start",
    measurement_generation: str | None = None,
    session_id: str | None = None,
    turn_id: str | None = None,
    boundary_source: str | None = None,
    turn_status: str | None = None,
    speed_mode: str = "UNKNOWN",
    speed_mode_source: str = "NONE",
    launcher_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if record_type not in {"run_start", "turn_start"}:
        raise TelemetryError("create_run record_type must be run_start or turn_start")
    run_id = _label(run_id, field="run_id") or _new_id("run")
    task = {
        "task_id": _label(task_id, field="task_id"),
        "task_label": _label(task_label, field="task_label", required=True),
        "project_label": _label(project_label, field="project_label"),
        "project_repo_label": _label(project_repo_label, field="project_repo_label"),
        "project_repo_id": _label(project_repo_id, field="project_repo_id"),
        "project_branch": _label(project_branch, field="project_branch"),
        "project_kind": _enum(project_kind, PROJECT_KINDS, field="project_kind"),
        "task_class": _enum(task_class, TASK_CLASSES, field="task_class"),
        "complexity": _enum(complexity, COMPLEXITIES, field="complexity"),
        "measurement_scope": _enum(measurement_scope, MEASUREMENT_SCOPES, field="measurement_scope"),
    }
    normalized_effort = _label(root_reasoning_effort, field="root_reasoning_effort")
    effort_source = _enum(
        reasoning_effort_source or ("LAUNCHER" if normalized_effort else "NONE"),
        REASONING_EFFORT_SOURCES,
        field="reasoning_effort_source",
    )
    if normalized_effort is None:
        effort_source = "NONE"
    root = {
        "model": _model_label(root_model, field="root_model"),
        "reasoning_effort": normalized_effort,
        "profile": _label(profile, field="profile"),
    }
    worker_list: list[dict[str, Any]] = []
    for index, worker in enumerate(workers):
        if not isinstance(worker, dict):
            raise TelemetryError("worker descriptor must be an object")
        worker_list.append({
            "ordinal": index,
            "model": _model_label(worker.get("model"), field="worker.model"),
            "reasoning_effort": _label(worker.get("reasoning_effort"), field="worker.reasoning_effort"),
            "reasoning_effort_source": _enum(
                worker.get("reasoning_effort_source") or ("LAUNCHER" if worker.get("reasoning_effort") else "NONE"),
                REASONING_EFFORT_SOURCES,
                field="worker.reasoning_effort_source",
            ),
            "launch_status": _enum(str(worker.get("launch_status", "UNKNOWN")), {"LAUNCHED", "COMPLETED", "CANCELLED", "FAILED", "UNKNOWN"}, field="worker.launch_status"),
        })
    if actual_worker_count is None and worker_list:
        actual_worker_count = len(worker_list)
    orchestra = {
        "mode": _enum(mode, MODES, field="orchestra.mode"),
        "speed_mode": _enum(speed_mode, SPEED_MODES, field="orchestra.speed_mode"),
        "speed_mode_source": _enum(speed_mode_source, SPEED_MODE_SOURCES, field="orchestra.speed_mode_source"),
        "launcher": launcher_contract,
        "root": root,
        "requested_worker_count": _nonnegative_int(requested_worker_count, field="requested_worker_count"),
        "actual_worker_count": _nonnegative_int(actual_worker_count, field="actual_worker_count"),
        "workers": worker_list,
        "workers_started": sum(worker["launch_status"] == "LAUNCHED" for worker in worker_list),
        "workers_completed": sum(worker["launch_status"] == "COMPLETED" for worker in worker_list),
        "workers_cancelled": sum(worker["launch_status"] == "CANCELLED" for worker in worker_list),
        "workers_failed": sum(worker["launch_status"] == "FAILED" for worker in worker_list),
        "max_concurrency": _nonnegative_int(max_concurrency, field="max_concurrency"),
        "attribution_quality": "DECLARED" if root["model"] or root["reasoning_effort"] or worker_list else "UNKNOWN",
        "attribution_source": "EXPLICIT_LAUNCH_METADATA" if root["model"] or root["reasoning_effort"] or worker_list else "UNKNOWN",
    }
    extra: dict[str, Any] = {}
    if measurement_generation is not None:
        extra["measurement_generation"] = _enum(measurement_generation, MEASUREMENT_GENERATIONS, field="measurement_generation")
    if session_id is not None:
        extra["session_id"] = _label(session_id, field="session_id", required=True)
    if turn_id is not None:
        extra["turn_id"] = _label(turn_id, field="turn_id", required=True)
    if boundary_source is not None:
        extra["boundary_source"] = _label(boundary_source, field="boundary_source", required=True)
    if turn_status is not None:
        extra["turn_status"] = _enum(turn_status, TURN_STATUSES, field="turn_status")
    record = _record(
        record_type,
        run_id=run_id,
        task=task,
        orchestra=orchestra,
        started_at_utc=_utc_now(),
        usage=_usage(),
        usage_source=_enum(usage_source, USAGE_SOURCES, field="usage_source"),
        usage_quality=_enum(usage_quality, USAGE_QUALITY, field="usage_quality"),
        reasoning_effort_source=effort_source,
        execution=_empty_execution(),
        result=_empty_result(),
        economics={"snapshots": [], "five_hour_pp_consumed": None, "weekly_pp_consumed": None},
        measurement=_measurement(collector_wall_ms=0.0, collector_cpu_ms=0.0),
        **extra,
    )
    return store.append(record, unique_run_id=True)


def _structured_usage_file(path: Path | str) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_symlink() or not candidate.is_file():
        raise TelemetryError("usage source must be an explicit regular file, not a symlink or directory")
    if candidate.suffix.lower() not in {".jsonl", ".ndjson"}:
        raise TelemetryError("usage source must use a .jsonl or .ndjson extension")
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
    usage_source: str = "NONE"
    usage_quality: str = "UNKNOWN"
    source_capability: str = "USAGE_SOURCE_UNAVAILABLE"
    turn_id: str | None = None


def _unknown_usage_observation(*, source_digest: str, bytes_read: int, collector_wall_ms: float, collector_cpu_ms: float, source_capability: str) -> UsageObservation:
    return UsageObservation(
        source_digest=source_digest,
        bytes_read=bytes_read,
        collector_wall_ms=collector_wall_ms,
        collector_cpu_ms=collector_cpu_ms,
        session_id=None,
        thread_id=None,
        usage=_usage(),
        observed_event_count=0,
        usage_source="NONE",
        usage_quality="UNKNOWN",
        source_capability=source_capability,
    )


def parse_codex_exec_json(
    path: Path | str,
    *,
    expected_thread_id: str | None = None,
    expected_turn_id: str | None = None,
) -> UsageObservation:
    """Parse the documented ``codex exec --json`` JSONL output.

    This adapter is explicit and exact-correlated.  It never accepts a
    transcript path and it never guesses by newest-file, timestamp, or
    directory scanning.  A malformed or ambiguously correlated stream yields
    unknown usage rather than an inferred value.
    """

    source = _structured_usage_file(path)
    start_wall = time.perf_counter()
    start_cpu = time.process_time()
    digest = hashlib.sha256()
    bytes_read = 0
    thread_ids: list[str] = []
    turn_ids: list[str] = []
    turn_usages: list[dict[str, Any]] = []
    malformed = False
    with source.open("rb") as handle:
        for line_number, line in enumerate(handle, 1):
            bytes_read += len(line)
            if not line.strip():
                continue
            try:
                event = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                digest.update(b"<malformed>\n")
                malformed = True
                continue
            if not isinstance(event, dict):
                digest.update(b"<non-object>\n")
                malformed = True
                continue
            event_type = event.get("type")
            if event_type == "thread.started":
                thread_id = event.get("thread_id")
                if isinstance(thread_id, str) and thread_id:
                    thread_ids.append(thread_id)
                    digest.update(json.dumps({"type": event_type, "thread_id": thread_id}, sort_keys=True).encode("utf-8"))
            elif event_type in {"turn.started", "turn.completed"}:
                turn_id = event.get("turn_id")
                if not isinstance(turn_id, str) or not turn_id:
                    turn = event.get("turn")
                    turn_id = turn.get("id") if isinstance(turn, dict) else None
                if isinstance(turn_id, str) and turn_id:
                    turn_ids.append(turn_id)
            if event_type != "turn.completed":
                continue
            if event_type == "turn.completed":
                raw_usage = event.get("usage")
                if not isinstance(raw_usage, dict):
                    digest.update(b"<turn-without-usage>\n")
                    malformed = True
                    continue
                turn_usages.append(raw_usage)
                digest.update(json.dumps({"type": event_type, "usage": raw_usage}, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    wall_ms = (time.perf_counter() - start_wall) * 1000.0
    cpu_ms = (time.process_time() - start_cpu) * 1000.0
    thread_id = thread_ids[0] if len(set(thread_ids)) == 1 else None
    turn_id = turn_ids[0] if len(set(turn_ids)) == 1 else None
    if expected_thread_id is not None and thread_id != expected_thread_id:
        return _unknown_usage_observation(
            source_digest=digest.hexdigest(),
            bytes_read=bytes_read,
            collector_wall_ms=wall_ms,
            collector_cpu_ms=cpu_ms,
            source_capability="USAGE_SOURCE_UNAVAILABLE",
        )
    if expected_turn_id is not None and turn_id != expected_turn_id:
        return _unknown_usage_observation(
            source_digest=digest.hexdigest(),
            bytes_read=bytes_read,
            collector_wall_ms=wall_ms,
            collector_cpu_ms=cpu_ms,
            source_capability="USAGE_SOURCE_UNAVAILABLE",
        )
    if malformed or thread_id is None or not turn_usages:
        return _unknown_usage_observation(
            source_digest=digest.hexdigest(),
            bytes_read=bytes_read,
            collector_wall_ms=wall_ms,
            collector_cpu_ms=cpu_ms,
            source_capability="USAGE_SOURCE_UNSTABLE" if malformed else "USAGE_SOURCE_UNAVAILABLE",
        )
    fields = (
        "input_tokens",
        "cached_input_tokens",
        "cache_write_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    )
    usage: dict[str, int | None] = {"model_requests": len(turn_usages)}
    quality = "EXACT"
    for field in fields:
        values: list[int] = []
        for raw_usage in turn_usages:
            value = raw_usage.get(field)
            if field == "reasoning_output_tokens" and value is None:
                value = raw_usage.get("reasoning_tokens")
            if value is None:
                if field != "cache_write_input_tokens":
                    quality = "PARTIAL"
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return _unknown_usage_observation(
                    source_digest=digest.hexdigest(),
                    bytes_read=bytes_read,
                    collector_wall_ms=wall_ms,
                    collector_cpu_ms=cpu_ms,
                    source_capability="USAGE_SOURCE_UNSTABLE",
                )
            values.append(value)
        usage[field] = sum(values) if len(values) == len(turn_usages) else None
    usage["reasoning_tokens"] = usage["reasoning_output_tokens"]
    return UsageObservation(
        source_digest=digest.hexdigest(),
        bytes_read=bytes_read,
        collector_wall_ms=wall_ms,
        collector_cpu_ms=cpu_ms,
        session_id=thread_id,
        thread_id=thread_id,
        usage=usage,
        observed_event_count=len(turn_usages),
        usage_source="CODEX_EXEC_JSON",
        usage_quality=quality,
        source_capability="USAGE_SOURCE_SUPPORTED",
        turn_id=turn_id,
    )


def parse_session_usage(path: Path | str) -> UsageObservation:
    """Reject the retired transcript adapter without touching the path."""

    raise SessionParseError("transcript parsing is disabled; use codex exec --json or explicit launcher metadata")


def ingest_usage(
    store: TelemetryStore,
    run_id: str,
    observation: UsageObservation,
    *,
    source_kind: str | None = None,
    source_schema: str | None = None,
    attribution_role: str = "ROOT",
    worker_id: str | None = None,
    turn_id: str | None = None,
    measurement_generation: str | None = None,
) -> dict[str, Any]:
    store.run_records(run_id)
    usage_source = _enum(observation.usage_source, USAGE_SOURCES, field="usage_source")
    usage_quality = _enum(observation.usage_quality, USAGE_QUALITY, field="usage_quality")
    source_capability = _enum(observation.source_capability, USAGE_SOURCE_CAPABILITIES, field="source_capability")
    record = _record(
        "usage_observed",
        run_id=run_id,
        source_kind=_label(source_kind or usage_source, field="source_kind", required=True),
        source_schema=_label(source_schema or usage_source.lower(), field="source_schema", required=True),
        source_digest=observation.source_digest,
        source_capability=source_capability,
        usage_source=usage_source,
        usage_quality=usage_quality,
        session_id=_label(observation.session_id, field="session_id"),
        thread_id=_label(observation.thread_id, field="thread_id"),
        turn_id=_label(turn_id or observation.turn_id, field="turn_id"),
        attribution_role=_enum(attribution_role, {"ROOT", "WORKER", "UNKNOWN"}, field="attribution_role"),
        worker_id=_label(worker_id, field="worker_id"),
        usage=observation.usage,
        observed_event_count=observation.observed_event_count,
        measurement_generation=_enum(measurement_generation, MEASUREMENT_GENERATIONS, field="measurement_generation") if measurement_generation else None,
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
        source_capability="USAGE_SOURCE_SUPPORTED",
        usage_source="NONE",
        usage_quality="EXACT",
        session_id=None,
        thread_id=None,
        attribution_role="UNKNOWN",
        worker_id=None,
        usage=usage,
        observed_event_count=usage["model_requests"],
        measurement=_measurement(collector_wall_ms=0.0, collector_cpu_ms=0.0, bytes_read=0),
    )
    return store.append(record, unique_source_digest=True)


def _metadata_usage_observation(values: dict[str, Any], *, source: str, session_id: str | None = None, thread_id: str | None = None, attribution_role: str = "ROOT", worker_id: str | None = None) -> UsageObservation:
    usage = _usage(values)
    numeric_fields = (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    )
    known = sum(usage[field] is not None for field in numeric_fields)
    quality = "EXACT" if known == len(numeric_fields) else ("PARTIAL" if known else "UNKNOWN")
    payload = json.dumps({"source": source, "session_id": session_id, "thread_id": thread_id, "attribution_role": attribution_role, "worker_id": worker_id, "usage": usage}, sort_keys=True).encode("utf-8")
    return UsageObservation(
        source_digest=hashlib.sha256(payload).hexdigest(),
        bytes_read=0,
        collector_wall_ms=0.0,
        collector_cpu_ms=0.0,
        session_id=session_id,
        thread_id=thread_id,
        usage=usage,
        observed_event_count=usage["model_requests"] or 0,
        usage_source=source,
        usage_quality=quality,
        source_capability="USAGE_SOURCE_SUPPORTED",
    )


def ingest_launcher_usage(
    store: TelemetryStore,
    run_id: str,
    values: dict[str, Any],
    *,
    session_id: str | None = None,
    thread_id: str | None = None,
    attribution_role: str = "ROOT",
    worker_id: str | None = None,
    turn_id: str | None = None,
    measurement_generation: str | None = None,
) -> dict[str, Any]:
    """Ingest usage explicitly supplied by the canonical launcher."""

    observation = _metadata_usage_observation(
        values,
        source="ORCHESTRA_LAUNCHER",
        session_id=session_id,
        thread_id=thread_id,
        attribution_role=attribution_role,
        worker_id=worker_id,
    )
    return ingest_usage(
        store,
        run_id,
        observation,
        attribution_role=attribution_role,
        worker_id=worker_id,
        turn_id=turn_id,
        measurement_generation=measurement_generation,
    )


def ingest_codex_exec_json(
    store: TelemetryStore,
    run_id: str,
    path: Path | str,
    *,
    expected_thread_id: str,
    expected_turn_id: str | None = None,
    attribution_role: str = "ROOT",
    worker_id: str | None = None,
    turn_id: str | None = None,
    measurement_generation: str | None = None,
) -> dict[str, Any]:
    """Ingest an explicitly supplied, exactly correlated exec JSONL stream."""

    observation = parse_codex_exec_json(path, expected_thread_id=expected_thread_id, expected_turn_id=expected_turn_id)
    return ingest_usage(
        store,
        run_id,
        observation,
        attribution_role=attribution_role,
        worker_id=worker_id,
        turn_id=turn_id,
        measurement_generation=measurement_generation,
    )


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
    result["reasoning_tokens"] = result["reasoning_output_tokens"]
    return result


def _fold_usage_source(records: Iterable[dict[str, Any]]) -> str:
    sources = {
        record.get("usage_source")
        for record in records
        if record.get("record_type") == "usage_observed" and record.get("usage_source") in USAGE_SOURCES
    }
    if not sources:
        return "NONE"
    non_none = sources - {"NONE"}
    return next(iter(non_none)) if len(non_none) == 1 else (next(iter(sources)) if len(sources) == 1 else "NONE")


def _fold_usage_quality(records: Iterable[dict[str, Any]]) -> str:
    qualities = {
        record.get("usage_quality")
        for record in records
        if record.get("record_type") == "usage_observed" and record.get("usage_quality") in USAGE_QUALITY
    }
    if not qualities or "UNKNOWN" in qualities:
        return "UNKNOWN"
    return "PARTIAL" if "PARTIAL" in qualities else "EXACT"


def observe_metadata(
    store: TelemetryStore,
    run_id: str,
    *,
    source_kind: str,
    root_model: str | None = None,
    root_reasoning_effort: str | None = None,
    reasoning_effort_source: str = "NONE",
    profile: str | None = None,
    orchestra_mode: str | None = None,
    speed_mode: str | None = None,
    speed_mode_source: str = "NONE",
    project_kind: str | None = None,
    project_label: str | None = None,
    project_repo_label: str | None = None,
    project_repo_id: str | None = None,
    project_branch: str | None = None,
    session_id: str | None = None,
    turn_id: str | None = None,
    measurement_generation: str | None = None,
    measurement_quality: str = "EXACT_MACHINE_READABLE",
) -> dict[str, Any]:
    store.run_records(run_id)
    normalized_speed_mode = _enum(speed_mode, SPEED_MODES, field="speed_mode") if speed_mode else None
    normalized_speed_source = _enum(speed_mode_source, SPEED_MODE_SOURCES, field="speed_mode_source") if normalized_speed_mode else "NONE"
    return store.append(_record(
        "metadata_observed",
        run_id=run_id,
        source_kind=_label(source_kind, field="source_kind", required=True),
        session_id=_label(session_id, field="session_id"),
        turn_id=_label(turn_id, field="turn_id"),
        measurement_generation=_enum(measurement_generation, MEASUREMENT_GENERATIONS, field="measurement_generation") if measurement_generation else None,
        root_model=_model_label(root_model, field="root_model"),
        root_reasoning_effort=_label(root_reasoning_effort, field="root_reasoning_effort"),
        reasoning_effort_source=_enum(reasoning_effort_source, REASONING_EFFORT_SOURCES, field="reasoning_effort_source"),
        profile=_label(profile, field="profile"),
        orchestra_mode=_enum(orchestra_mode, MODES, field="orchestra_mode") if orchestra_mode else None,
        speed_mode=normalized_speed_mode,
        speed_mode_source=normalized_speed_source,
        project_kind=_enum(project_kind, PROJECT_KINDS, field="project_kind") if project_kind else None,
        project_label=_label(project_label, field="project_label"),
        project_repo_label=_label(project_repo_label, field="project_repo_label"),
        project_repo_id=_label(project_repo_id, field="project_repo_id"),
        project_branch=_label(project_branch, field="project_branch"),
        measurement_quality=_label(measurement_quality, field="measurement_quality", required=True),
    ))


def observe_worker(
    store: TelemetryStore,
    run_id: str,
    *,
    worker_id: str,
    session_id: str | None = None,
    turn_id: str | None = None,
    measurement_generation: str | None = None,
    agent_type: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    reasoning_effort_source: str = "NONE",
    launch_status: str = "UNKNOWN",
    measurement_quality: str = "EXACT_MACHINE_READABLE",
) -> dict[str, Any]:
    store.run_records(run_id)
    return store.append(_record(
        "worker_observed",
        run_id=run_id,
        session_id=_label(session_id, field="session_id"),
        turn_id=_label(turn_id, field="turn_id"),
        measurement_generation=_enum(measurement_generation, MEASUREMENT_GENERATIONS, field="measurement_generation") if measurement_generation else None,
        worker_id=_label(worker_id, field="worker_id", required=True),
        agent_type=_label(agent_type, field="agent_type"),
        model=_model_label(model, field="worker.model"),
        reasoning_effort=_label(reasoning_effort, field="worker.reasoning_effort"),
        reasoning_effort_source=_enum(reasoning_effort_source, REASONING_EFFORT_SOURCES, field="worker.reasoning_effort_source"),
        launch_status=_enum(launch_status, {"LAUNCHED", "COMPLETED", "CANCELLED", "FAILED", "UNKNOWN"}, field="worker.launch_status"),
        measurement_quality=_label(measurement_quality, field="measurement_quality", required=True),
    ))


def observe_interruption(
    store: TelemetryStore,
    run_id: str,
    *,
    session_id: str | None,
    thread_id: str | None,
    turn_id: str | None = None,
    measurement_generation: str | None = None,
    reason: str = "INTERRUPTED",
) -> dict[str, Any]:
    store.run_records(run_id)
    return store.append(_record(
        "interruption_observed",
        run_id=run_id,
        session_id=_label(session_id, field="session_id"),
        thread_id=_label(thread_id, field="thread_id"),
        turn_id=_label(turn_id, field="turn_id"),
        measurement_generation=_enum(measurement_generation, MEASUREMENT_GENERATIONS, field="measurement_generation") if measurement_generation else None,
        reason=_label(reason, field="reason", required=True),
        measurement_quality="EXACT_MACHINE_READABLE",
    ))


@dataclass(frozen=True)
class ProjectMetadata:
    kind: str
    label: str | None
    repo_label: str | None = None
    repo_id: str | None = None
    branch: str | None = None


def _git_dir_from_marker(root: Path, marker: Path) -> Path | None:
    if marker.is_dir():
        return marker
    if not marker.is_file():
        return None
    try:
        line = marker.read_text(encoding="utf-8", errors="strict").splitlines()[0]
    except (OSError, UnicodeError, IndexError):
        return None
    prefix = "gitdir:"
    if not line.lower().startswith(prefix):
        return None
    raw = line[len(prefix):].strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return None


def _project_metadata(cwd: str | None) -> ProjectMetadata:
    """Derive deterministic, path-free project metadata from local Git files."""

    if not isinstance(cwd, str) or not cwd:
        return ProjectMetadata("NO_PROJECT", None)
    try:
        candidate = Path(cwd).expanduser().resolve()
    except (OSError, RuntimeError):
        return ProjectMetadata("UNKNOWN", None)
    if not candidate.exists() or not candidate.is_dir():
        return ProjectMetadata("UNKNOWN", None)
    for directory in (candidate, *candidate.parents):
        marker = directory / ".git"
        if not marker.exists():
            continue
        git_dir = _git_dir_from_marker(directory, marker)
        if git_dir is None or not git_dir.exists() or not git_dir.is_dir():
            return ProjectMetadata("UNKNOWN", _derived_label(directory.name, fallback="git-project"))
        common_dir = git_dir
        common_file = git_dir / "commondir"
        if common_file.is_file():
            try:
                common_raw = common_file.read_text(encoding="utf-8", errors="strict").splitlines()[0].strip()
                if common_raw:
                    common_candidate = Path(common_raw)
                    if not common_candidate.is_absolute():
                        common_candidate = git_dir / common_candidate
                    common_dir = common_candidate.resolve()
            except (OSError, UnicodeError, IndexError, RuntimeError):
                common_dir = git_dir
        branch: str | None = None
        try:
            head = (git_dir / "HEAD").read_text(encoding="utf-8", errors="strict").strip()
            if head.startswith("ref: refs/heads/"):
                branch = _derived_label(head[len("ref: refs/heads/"):], fallback="unknown")
            elif head:
                branch = "DETACHED"
        except (OSError, UnicodeError):
            pass
        repo_name = common_dir.parent.name if common_dir.name == ".git" else directory.name
        repo_id = hashlib.sha256(("git:" + str(common_dir).casefold()).encode("utf-8")).hexdigest()[:20]
        return ProjectMetadata(
            "GIT",
            _derived_label(directory.name, fallback="git-project"),
            _derived_label(repo_name, fallback="git-repository"),
            repo_id,
            branch,
        )
    return ProjectMetadata("NON_GIT", _derived_label(candidate.name, fallback="non-git"))


def _launcher_metadata(event: dict[str, Any]) -> dict[str, Any]:
    """Read only explicit metadata emitted by the canonical launcher.

    Ordinary Codex hooks do not provide profile, mode, effort, or usage.  The
    reserved object is an opt-in launcher contract; arbitrary hook fields and
    model names never imply those dimensions.
    """

    raw = event.get("orchestra_launcher")
    from_environment = not isinstance(raw, dict)
    if from_environment:
        raw = _launcher_environment_payload()
    if not isinstance(raw, dict):
        return {}
    result: dict[str, Any] = {}
    if isinstance(raw.get("profile"), str):
        result["profile"] = raw["profile"]
    if isinstance(raw.get("mode"), str):
        result["mode"] = raw["mode"]
    if isinstance(raw.get("reasoning_effort"), str):
        result["reasoning_effort"] = raw["reasoning_effort"]
        result["reasoning_effort_source"] = "LAUNCHER"
    if isinstance(raw.get("usage"), dict):
        result["usage"] = raw["usage"]
    speed_mode = _speed_mode_from_explicit_fields(raw)
    contract = _launcher_contract(raw, require_explicit_source=from_environment)
    if speed_mode is not None and (not from_environment or contract is not None):
        result["speed_mode"] = speed_mode
        result["speed_mode_source"] = str(raw.get("speed_mode_source") or "ORCHESTRA_LAUNCHER")
    if contract is not None:
        result["contract"] = contract
    return result


def _speed_mode_from_value(value: Any) -> str | None:
    """Normalize one explicit speed signal; unrelated service tiers stay unknown."""

    if isinstance(value, bool):
        return "FAST" if value else "STANDARD"
    if not isinstance(value, str):
        return None
    candidate = value.strip().upper()
    if candidate in {"FAST", "ON"}:
        return "FAST"
    if candidate in {"STANDARD", "DEFAULT", "OFF"}:
        return "STANDARD"
    # API priority is not Codex Fast mode.  Do not reverse-infer one from the other.
    return None


def _speed_mode_from_explicit_fields(fields: dict[str, Any]) -> str | None:
    """Use only explicit speed fields, rejecting conflicting declarations."""

    signals: list[str] = []
    if "speed_mode" in fields:
        signals.append(_speed_mode_from_value(fields["speed_mode"]) or "UNKNOWN")
    if "service_tier" in fields:
        signals.append(_speed_mode_from_value(fields["service_tier"]) or "UNKNOWN")
    if "fast_mode" in fields:
        signals.append(_speed_mode_from_value(fields["fast_mode"]) or "UNKNOWN")
    if not signals or len(set(signals)) != 1 or signals[0] == "UNKNOWN":
        return None
    return signals[0]


def _codex_config_speed_mode() -> str | None:
    """Read only the documented two-key Fast default from CODEX_HOME/config.toml."""

    config_path = _codex_home_path() / "config.toml"
    if config_path.is_symlink() or not config_path.is_file():
        return None
    try:
        with config_path.open("rb") as handle:
            config = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    features = config.get("features")
    if (
        config.get("service_tier") == "fast"
        and isinstance(features, dict)
        and features.get("fast_mode") is True
    ):
        return "FAST"
    return None


def _launcher_contract(raw: Any, *, require_explicit_source: bool = False) -> dict[str, Any] | None:
    """Keep only the path-free, versioned launcher contract fields."""

    if not isinstance(raw, dict):
        return None
    if require_explicit_source and raw.get("schema") != _LAUNCHER_METADATA_SCHEMA:
        return None
    mode = _speed_mode_from_value(raw.get("speed_mode"))
    source = raw.get("speed_mode_source")
    if mode not in {"FAST", "STANDARD"}:
        return None
    if source != "LAUNCHER_EXPLICIT" and require_explicit_source:
        return None
    contract: dict[str, Any] = {
        "speed_mode": mode,
        "speed_mode_source": str(source or "ORCHESTRA_LAUNCHER"),
    }
    for field in ("launcher_name", "launcher_version", "service_tier", "config_hash"):
        value = raw.get(field)
        if isinstance(value, str) and _LABEL_RE.fullmatch(value):
            contract[field] = value
    overrides = raw.get("config_overrides")
    if isinstance(overrides, list) and all(isinstance(value, str) and len(value) <= 160 for value in overrides):
        contract["config_overrides"] = list(overrides)
    if isinstance(raw.get("fast_mode"), bool):
        contract["fast_mode"] = raw["fast_mode"]
    if require_explicit_source:
        required = {"launcher_name", "launcher_version", "service_tier", "config_hash", "config_overrides"}
        if not required.issubset(contract):
            return None
        expected_mode = "FAST" if contract["launcher_name"] == "codex-fast" else "STANDARD" if contract["launcher_name"] == "codex-standard" else None
        if expected_mode != mode or contract["launcher_version"] != "1":
            return None
        expected_overrides = (
            ['features.fast_mode=true', 'service_tier="fast"']
            if mode == "FAST"
            else ['service_tier="default"']
        )
        if contract["config_overrides"] != expected_overrides:
            return None
        if contract["service_tier"] != ("fast" if mode == "FAST" else "default"):
            return None
        if mode == "FAST" and contract.get("fast_mode") is not True:
            return None
        if mode == "STANDARD" and "fast_mode" in contract:
            return None
        canonical = json.dumps({"config_overrides": expected_overrides}, sort_keys=True, separators=(",", ":"))
        if contract["config_hash"] != hashlib.sha256(canonical.encode("utf-8")).hexdigest():
            return None
    return contract


def _launcher_environment_payload() -> dict[str, Any] | None:
    """Read the small process-scoped contract supplied by a benchmark launcher."""

    raw = os.environ.get(_LAUNCHER_METADATA_ENV)
    if not isinstance(raw, str) or not raw or len(raw.encode("utf-8", errors="ignore")) > _LAUNCHER_METADATA_MAX_BYTES:
        return None
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _last_session_speed(store: TelemetryStore, session_id: str) -> tuple[str, str] | None:
    """Carry forward only a known state observed by this same session."""
    return _session_speed(store, session_id)


def _speed_metadata(store: TelemetryStore, event: dict[str, Any], launcher: dict[str, Any]) -> tuple[str, str]:
    explicit = launcher.get("speed_mode")
    if explicit in SPEED_MODES and explicit != "UNKNOWN":
        return str(explicit), str(launcher.get("speed_mode_source", "ORCHESTRA_LAUNCHER"))
    stable = _speed_mode_from_explicit_fields(event)
    if stable is not None:
        return stable, "STABLE_RUNTIME_METADATA"
    inherited = _last_session_speed(store, _hook_id(event.get("session_id"), field="session_id"))
    if inherited is not None:
        mode, source = inherited
        return mode, source if source in {"CODEX_CONFIG_EXPLICIT", "LAUNCHER_EXPLICIT"} else "SESSION_LATCH"
    configured = _codex_config_speed_mode()
    if configured is not None:
        return configured, "CODEX_CONFIG_EXPLICIT"
    return "UNKNOWN", "NONE"


def _hook_id(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise TelemetryError(f"hook event lacks {field}")
    return _label(value, field=field, required=True) or ""


def _session_records(store: TelemetryStore, session_id: str) -> list[dict[str, Any]]:
    return [
        record for record in store.read()
        if record.get("record_type") == "session_observed" and record.get("session_id") == session_id
    ]


def _session_speed(store: TelemetryStore, session_id: str) -> tuple[str, str] | None:
    for record in reversed(store.read()):
        if record.get("session_id") != session_id:
            continue
        if record.get("record_type") == "turn_start":
            orchestra = record.get("orchestra")
            value = orchestra.get("speed_mode") if isinstance(orchestra, dict) else None
            source = orchestra.get("speed_mode_source", "NONE") if isinstance(orchestra, dict) else "NONE"
        elif record.get("record_type") == "session_observed":
            value = record.get("speed_mode")
            source = record.get("speed_mode_source", "NONE")
        else:
            continue
        if value in {"FAST", "STANDARD"}:
            return str(value), str(source)
    return None


def _observe_session(store: TelemetryStore, event: dict[str, Any], lifecycle: str) -> dict[str, Any]:
    session_id = _hook_id(event.get("session_id"), field="session_id")
    existing = _session_records(store, session_id)
    for record in existing:
        if record.get("lifecycle") == lifecycle:
            return record
    project = _project_metadata(event.get("cwd"))
    launcher = _launcher_metadata(event)
    speed_mode, speed_source = _speed_metadata(store, event, launcher)
    return store.append(_record(
        "session_observed",
        session_id=session_id,
        lifecycle=_enum(lifecycle, {"STARTED", "ENDED"}, field="session.lifecycle"),
        root_model=_model_label(event.get("model"), field="hook.model"),
        root_reasoning_effort=_label(launcher.get("reasoning_effort"), field="root_reasoning_effort"),
        reasoning_effort_source=_enum(launcher.get("reasoning_effort_source", "NONE"), REASONING_EFFORT_SOURCES, field="reasoning_effort_source"),
        profile=_label(launcher.get("profile"), field="profile"),
        orchestra_mode=_enum(launcher.get("mode", "NOT_APPLICABLE"), MODES, field="session.mode"),
        speed_mode=speed_mode,
        speed_mode_source=speed_source,
        launcher=launcher.get("contract"),
        project_kind=project.kind,
        project_label=_label(project.label, field="project_label"),
        project_repo_label=_label(project.repo_label, field="project_repo_label"),
        project_repo_id=_label(project.repo_id, field="project_repo_id"),
        project_branch=_label(project.branch, field="project_branch"),
        measurement_generation="SESSION_LEVEL_V1",
        measurement_quality="EXACT_MACHINE_READABLE",
    ))


def _turn_candidates(store: TelemetryStore, session_id: str, turn_id: str) -> list[tuple[str, bool]]:
    records = store.read()
    finalized = {
        record.get("run_id") for record in records
        if record.get("record_type") == "turn_finalize" and isinstance(record.get("run_id"), str)
    }
    return [
        (record["run_id"], record["run_id"] in finalized)
        for record in records
        if record.get("record_type") == "turn_start"
        and record.get("session_id") == session_id
        and record.get("turn_id") == turn_id
        and isinstance(record.get("run_id"), str)
    ]


def _turn_run_id(session_id: str, turn_id: str) -> str:
    digest = hashlib.sha256((session_id + "\0" + turn_id).encode("utf-8")).hexdigest()[:24]
    return "turn_" + digest


def _ensure_turn(store: TelemetryStore, event: dict[str, Any], *, boundary_source: str) -> str:
    session_id = _hook_id(event.get("session_id"), field="session_id")
    turn_id = _hook_id(event.get("turn_id"), field="turn_id")
    candidates = _turn_candidates(store, session_id, turn_id)
    if candidates:
        return candidates[0][0]
    project = _project_metadata(event.get("cwd"))
    launcher = _launcher_metadata(event)
    resolved_speed_mode, resolved_speed_source = _speed_metadata(store, event, launcher)
    try:
        create_run(
            store,
            record_type="turn_start",
            run_id=_turn_run_id(session_id, turn_id),
            task_id=turn_id,
            task_label="codex-turn",
            project_label=project.label,
            project_repo_label=project.repo_label,
            project_repo_id=project.repo_id,
            project_branch=project.branch,
            project_kind=project.kind,
            measurement_scope="UNCLASSIFIED",
            measurement_generation="TURN_LEVEL_V1_2",
            session_id=session_id,
            turn_id=turn_id,
            boundary_source=boundary_source,
            turn_status="STARTED",
            root_model=_model_label(event.get("model"), field="hook.model"),
            root_reasoning_effort=launcher.get("reasoning_effort"),
            profile=launcher.get("profile"),
            reasoning_effort_source=launcher.get("reasoning_effort_source"),
            mode=launcher.get("mode", "NOT_APPLICABLE"),
            speed_mode=resolved_speed_mode,
            speed_mode_source=resolved_speed_source,
            launcher_contract=launcher.get("contract"),
        )
    except DuplicateRecordError:
        candidates = _turn_candidates(store, session_id, turn_id)
        if candidates:
            return candidates[0][0]
        raise
    return _turn_run_id(session_id, turn_id)


def _observe_launcher_usage(
    store: TelemetryStore,
    run_id: str,
    event: dict[str, Any],
    launcher: dict[str, Any],
    *,
    attribution_role: str,
    worker_id: str | None = None,
    turn_id: str | None = None,
) -> bool:
    values = launcher.get("usage")
    if not isinstance(values, dict):
        return False
    try:
        ingest_launcher_usage(
            store,
            run_id,
            values,
            session_id=event.get("session_id"),
            thread_id=event.get("thread_id"),
            attribution_role=attribution_role,
            worker_id=worker_id,
            turn_id=turn_id,
            measurement_generation="TURN_LEVEL_V1_2" if turn_id else None,
        )
    except DuplicateRecordError as exc:
        if "source has already been ingested" not in str(exc):
            raise
    return True


def handle_hook_event(store: TelemetryStore, event: dict[str, Any]) -> dict[str, Any]:
    """Handle stable Codex lifecycle metadata without reading transcript paths."""

    if not telemetry_enabled():
        return {"status": "DISABLED"}
    if not isinstance(event, dict):
        raise TelemetryError("hook input must be an object")
    event_name = event.get("hook_event_name")
    session_id = event.get("session_id")
    if not isinstance(event_name, str) or not isinstance(session_id, str):
        raise TelemetryError("hook input lacks event name or session_id")
    if event_name == "SessionStart":
        record = _observe_session(store, event, "STARTED")
        return {"status": "SESSION_STARTED", "session_id": record["session_id"]}
    if event_name == "SessionEnd":
        record = _observe_session(store, event, "ENDED")
        return {"status": "SESSION_ENDED", "session_id": record["session_id"]}
    if event_name not in {"UserPromptSubmit", "Stop", "SubagentStart", "SubagentStop", "Interrupt"}:
        return {"status": "IGNORED", "event": event_name}
    session_id = _hook_id(event.get("session_id"), field="session_id")
    turn_id = _hook_id(event.get("turn_id"), field="turn_id")
    launcher = _launcher_metadata(event)
    boundary_source = "USER_PROMPT_SUBMIT" if event_name == "UserPromptSubmit" else "TURN_HOOK_RECOVERY"
    run_id = _ensure_turn(store, event, boundary_source=boundary_source)
    if event_name == "UserPromptSubmit":
        return {"status": "TURN_STARTED", "run_id": run_id, "turn_id": turn_id}
    if event_name == "SubagentStart":
        worker_id = event.get("agent_id") or _derived_label(event.get("agent_type"), fallback="unknown-worker")
        observe_worker(
            store,
            run_id,
            session_id=session_id,
            turn_id=turn_id,
            measurement_generation="TURN_LEVEL_V1_2",
            worker_id=_derived_label(worker_id, fallback="unknown-worker"),
            agent_type=_derived_label(event.get("agent_type"), fallback="unknown") if event.get("agent_type") else None,
            model=_model_label(event.get("model"), field="hook.model"),
            reasoning_effort=launcher.get("reasoning_effort"),
            reasoning_effort_source=launcher.get("reasoning_effort_source", "NONE"),
            launch_status="LAUNCHED",
        )
        _observe_launcher_usage(
            store,
            run_id,
            event,
            launcher,
            attribution_role="WORKER",
            worker_id=worker_id,
            turn_id=turn_id,
        )
        return {"status": "WORKER_STARTED", "run_id": run_id}
    if event_name == "SubagentStop":
        worker_id = event.get("agent_id") or _derived_label(event.get("agent_type"), fallback="unknown-worker")
        usage_observed = _observe_launcher_usage(
            store,
            run_id,
            event,
            launcher,
            attribution_role="WORKER",
            worker_id=worker_id,
            turn_id=turn_id,
        )
        observe_worker(
            store,
            run_id,
            session_id=session_id,
            turn_id=turn_id,
            measurement_generation="TURN_LEVEL_V1_2",
            worker_id=_derived_label(worker_id, fallback="unknown-worker"),
            agent_type=_derived_label(event.get("agent_type"), fallback="unknown") if event.get("agent_type") else None,
            model=_model_label(event.get("model"), field="hook.model"),
            reasoning_effort=launcher.get("reasoning_effort"),
            reasoning_effort_source=launcher.get("reasoning_effort_source", "NONE"),
            launch_status="COMPLETED",
        )
        return {"status": "WORKER_STOPPED", "run_id": run_id}
    if event_name == "Interrupt":
        observe_interruption(
            store,
            run_id,
            session_id=session_id,
            thread_id=None,
            turn_id=turn_id,
            measurement_generation="TURN_LEVEL_V1_2",
            reason="INTERRUPTED",
        )
        _finalize_turn(store, run_id, session_id=session_id, turn_id=turn_id, turn_status="INTERRUPTED")
        return {"status": "TURN_INTERRUPTED", "run_id": run_id, "turn_id": turn_id}
    if event_name == "Stop":
        usage_observed = _observe_launcher_usage(store, run_id, event, launcher, attribution_role="ROOT", turn_id=turn_id)
        _finalize_turn(store, run_id, session_id=session_id, turn_id=turn_id, turn_status="COMPLETED")
        return {"status": "TURN_FINALIZED", "run_id": run_id, "turn_id": turn_id, "usage_observed": usage_observed}
    return {"status": "IGNORED", "run_id": run_id, "event": event_name}


def _finalize_turn(
    store: TelemetryStore,
    run_id: str,
    *,
    session_id: str,
    turn_id: str,
    turn_status: str,
) -> dict[str, Any]:
    records = store.run_records(run_id)
    existing = next((record for record in records if record.get("record_type") == "turn_finalize"), None)
    if existing is not None:
        return existing
    interruptions = any(record.get("record_type") == "interruption_observed" for record in records)
    try:
        return finalize_run(
            store,
            run_id,
            record_type="turn_finalize",
            measurement_generation="TURN_LEVEL_V1_2",
            session_id=session_id,
            turn_id=turn_id,
            turn_status=turn_status,
            usage=_aggregate_usage(record for record in records if record.get("record_type") == "usage_observed"),
            usage_source=_fold_usage_source(records),
            usage_quality=_fold_usage_quality(records),
            execution={"abnormal_termination": "INTERRUPTED" if interruptions else None},
            result={"completed": False if interruptions or turn_status != "COMPLETED" else True},
        )
    except DuplicateRecordError:
        return next(record for record in store.run_records(run_id) if record.get("record_type") == "turn_finalize")


def finalize_run(
    store: TelemetryStore,
    run_id: str,
    *,
    ended_at_utc: str | None = None,
    usage: dict[str, Any] | None = None,
    usage_source: str | None = None,
    usage_quality: str | None = None,
    execution: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    measurement: dict[str, Any] | None = None,
    record_type: str = "run_finalize",
    measurement_generation: str | None = None,
    session_id: str | None = None,
    turn_id: str | None = None,
    turn_status: str | None = None,
) -> dict[str, Any]:
    records = store.run_records(run_id)
    if record_type not in {"run_finalize", "turn_finalize"}:
        raise TelemetryError("finalize_run record_type must be run_finalize or turn_finalize")
    if any(r.get("record_type") == record_type for r in records):
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
    final_usage_source = _enum(usage_source or _fold_usage_source(records), USAGE_SOURCES, field="usage_source")
    final_usage_quality = _enum(usage_quality or _fold_usage_quality(records), USAGE_QUALITY, field="usage_quality")
    start = next(record for record in records if record.get("record_type") in {"run_start", "turn_start"})
    final_effort_source = start.get("reasoning_effort_source", "NONE")
    final_ended_at = ended_at_utc or _utc_now()
    if final_execution.get("wall_clock_seconds") is None:
        try:
            started = datetime.fromisoformat(str(start["started_at_utc"]).replace("Z", "+00:00"))
            ended = datetime.fromisoformat(final_ended_at.replace("Z", "+00:00"))
            final_execution["wall_clock_seconds"] = max(0.0, (ended - started).total_seconds())
        except (KeyError, TypeError, ValueError):
            pass
    final_measurement = measurement or _measurement(collector_wall_ms=0.0, collector_cpu_ms=0.0)
    extra: dict[str, Any] = {}
    generation = measurement_generation or start.get("measurement_generation")
    if generation is not None:
        extra["measurement_generation"] = _enum(generation, MEASUREMENT_GENERATIONS, field="measurement_generation")
    if session_id is not None:
        extra["session_id"] = _label(session_id, field="session_id", required=True)
    elif start.get("session_id") is not None:
        extra["session_id"] = start["session_id"]
    if turn_id is not None:
        extra["turn_id"] = _label(turn_id, field="turn_id", required=True)
    elif start.get("turn_id") is not None:
        extra["turn_id"] = start["turn_id"]
    if turn_status is not None:
        extra["turn_status"] = _enum(turn_status, TURN_STATUSES, field="turn_status")
    record = _record(
        record_type,
        run_id=_label(run_id, field="run_id", required=True),
        ended_at_utc=final_ended_at,
        usage=final_usage,
        usage_source=final_usage_source,
        usage_quality=final_usage_quality,
        reasoning_effort_source=_enum(final_effort_source, REASONING_EFFORT_SOURCES, field="reasoning_effort_source"),
        execution=final_execution,
        result=final_result,
        measurement=final_measurement,
        **extra,
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


def _median_with_count(values: Iterable[Any]) -> tuple[float | None, int]:
    known = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    return (statistics.median(known) if known else None, len(known))


def _normalize_folded_speed_fields(run: dict[str, Any]) -> None:
    """Supply read-only defaults for records written before speed telemetry."""

    orchestra = run.get("orchestra")
    if not isinstance(orchestra, dict):
        return
    if "speed_mode" not in orchestra:
        orchestra["speed_mode"] = "UNKNOWN"
        orchestra["speed_mode_source"] = "LEGACY_MISSING"
    elif "speed_mode_source" not in orchestra:
        orchestra["speed_mode_source"] = "LEGACY_MISSING"


def _fold_run(records: list[dict[str, Any]]) -> dict[str, Any]:
    start = next(r for r in records if r["record_type"] in {"run_start", "turn_start"})
    run = json.loads(json.dumps(start))
    generation = start.get("measurement_generation")
    if generation is None:
        generation = "SESSION_LEVEL_V1" if (
            start.get("task", {}).get("task_label") == "codex-session"
            or any(record.get("source_kind") == "CODEX_HOOK_EVENT" for record in records)
        ) else "UNKNOWN"
    run["measurement_generation"] = generation
    run["benchmark_unit"] = "TURN" if generation == "TURN_LEVEL_V1_2" else "SESSION"
    snapshots: list[dict[str, Any]] = []
    annotations: list[dict[str, Any]] = []
    workers: dict[str, dict[str, Any]] = {}
    usage_records: list[dict[str, Any]] = []
    for record in records:
        kind = record["record_type"]
        if kind == "usage_observed":
            usage_records.append(record)
            run["usage"] = _aggregate_usage(usage_records)
            run["usage_source"] = _fold_usage_source(usage_records)
            run["usage_quality"] = _fold_usage_quality(usage_records)
            run["measurement"] = record["measurement"]
        elif kind == "metadata_observed":
            if record.get("root_model") is not None:
                run["orchestra"]["root"]["model"] = record["root_model"]
            if record.get("root_reasoning_effort") is not None:
                run["orchestra"]["root"]["reasoning_effort"] = record["root_reasoning_effort"]
            if record.get("reasoning_effort_source") is not None:
                run["reasoning_effort_source"] = record["reasoning_effort_source"]
            if record.get("profile") is not None:
                run["orchestra"]["root"]["profile"] = record["profile"]
            if record.get("orchestra_mode") is not None:
                run["orchestra"]["mode"] = record["orchestra_mode"]
            if record.get("speed_mode") is not None:
                run["orchestra"]["speed_mode"] = record["speed_mode"]
                run["orchestra"]["speed_mode_source"] = record.get("speed_mode_source", "NONE")
            if record.get("project_kind") is not None:
                run["task"]["project_kind"] = record["project_kind"]
            if record.get("project_label") is not None:
                run["task"]["project_label"] = record["project_label"]
            for field in ("project_repo_label", "project_repo_id", "project_branch"):
                if record.get(field) is not None:
                    run["task"][field] = record[field]
        elif kind == "worker_observed":
            workers[record["worker_id"]] = {
                "worker_id": record["worker_id"],
                "agent_type": record.get("agent_type"),
                "model": record.get("model"),
                "reasoning_effort": record.get("reasoning_effort"),
                "reasoning_effort_source": record.get("reasoning_effort_source", "NONE"),
                "launch_status": record.get("launch_status", "UNKNOWN"),
            }
        elif kind == "interruption_observed":
            run["execution"]["abnormal_termination"] = record.get("reason", "INTERRUPTED")
        elif kind in {"run_finalize", "turn_finalize"}:
            run["ended_at_utc"] = record["ended_at_utc"]
            run["usage"] = record["usage"]
            run["usage_source"] = record.get("usage_source", "NONE")
            run["usage_quality"] = record.get("usage_quality", "UNKNOWN")
            run["reasoning_effort_source"] = record.get("reasoning_effort_source", run.get("reasoning_effort_source", "NONE"))
            run["execution"] = record["execution"]
            run["result"] = record["result"]
            run["measurement"] = record["measurement"]
            if record.get("measurement_generation") is not None:
                run["measurement_generation"] = record["measurement_generation"]
            if record.get("turn_status") is not None:
                run["turn_status"] = record["turn_status"]
        elif kind == "allowance_snapshot":
            snapshots.append(record)
        elif kind == "annotation":
            annotations.append(record)
    if workers:
        run["orchestra"]["workers"] = list(workers.values())
        run["orchestra"]["actual_worker_count"] = len(workers)
        worker_statuses = [record.get("launch_status", "UNKNOWN") for record in records if record.get("record_type") == "worker_observed"]
        run["orchestra"]["workers_started"] = worker_statuses.count("LAUNCHED")
        run["orchestra"]["workers_completed"] = worker_statuses.count("COMPLETED")
        run["orchestra"]["workers_cancelled"] = worker_statuses.count("CANCELLED")
        run["orchestra"]["workers_failed"] = worker_statuses.count("FAILED")
        run["orchestra"]["attribution_quality"] = "ROOT_WORKER_USAGE_PARTIAL"
        run["orchestra"]["attribution_source"] = "CODEX_LIFECYCLE_HOOKS"
    elif any(record.get("source_kind") == "CODEX_HOOK_EVENT" for record in records):
        run["orchestra"]["attribution_quality"] = "ROOT_WORKER_USAGE_PARTIAL"
        run["orchestra"]["attribution_source"] = "CODEX_LIFECYCLE_HOOKS"
    if generation == "TURN_LEVEL_V1_2":
        run["orchestra"]["attribution_source"] = "CODEX_TURN_HOOKS"
        run["orchestra"]["attribution_quality"] = "ROOT_WORKER_USAGE_PARTIAL" if workers else "ROOT_USAGE_UNKNOWN"
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
    _normalize_folded_speed_fields(run)
    return run


def report(
    store: TelemetryStore,
    *,
    group_by: list[str] | None = None,
    include_synthetic: bool = False,
    include_session_level: bool = False,
    speed_benchmark: bool = False,
) -> dict[str, Any]:
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
    generation_runs = {
        run_id: items for run_id, items in runs.items()
        if include_session_level or _fold_run(items).get("measurement_generation") != "SESSION_LEVEL_V1"
    }
    session_level_run_count = len(runs) - len(generation_runs)
    report_runs = (
        generation_runs
        if include_synthetic
        else {run_id: items for run_id, items in generation_runs.items() if run_id not in synthetic_run_ids}
    )
    folded = [_fold_run(items) for items in report_runs.values()]
    speed_benchmark_excluded_runs = 0
    if speed_benchmark:
        eligible = [
            run for run in folded
            if run["orchestra"]["speed_mode_source"] == "LAUNCHER_EXPLICIT"
            and run["orchestra"]["speed_mode"] in {"FAST", "STANDARD"}
        ]
        speed_benchmark_excluded_runs = len(folded) - len(eligible)
        folded = eligible
    folded.sort(key=lambda item: item["run_id"])
    fields = group_by or ["task_class", "mode", "root_model", "reasoning_effort", "worker_count"]

    def group_key(run: dict[str, Any]) -> tuple[Any, ...]:
        mapping = {
            "task_class": run["task"]["task_class"],
            "mode": run["orchestra"]["mode"],
            "speed_mode": run["orchestra"]["speed_mode"],
            "speed_mode_source": run["orchestra"]["speed_mode_source"],
            "root_model": run["orchestra"]["root"]["model"] or "UNKNOWN",
            "reasoning_effort": run["orchestra"]["root"]["reasoning_effort"] or "UNKNOWN",
            "worker_count": run["orchestra"]["actual_worker_count"],
            "usage_source": run.get("usage_source", "NONE"),
            "usage_quality": run.get("usage_quality", "UNKNOWN"),
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
        median_input, input_n = _median_with_count(r["usage"]["input_tokens"] for r in members)
        median_cached, cached_n = _median_with_count(r["usage"]["cached_input_tokens"] for r in members)
        median_output, output_n = _median_with_count(r["usage"]["output_tokens"] for r in members)
        median_total, total_n = _median_with_count(r["usage"]["total_tokens"] for r in members)
        usage_quality_counts = {quality: sum(r.get("usage_quality") == quality for r in members) for quality in sorted(USAGE_QUALITY)}
        summaries.append({
            "group": dict(zip(fields, key)),
            "runs": len(members),
            "completion_rate": (sum(completed) / len(completed)) if completed else None,
            "first_pass_pass_rate": (sum(value == "PASS" for value in first_pass) / len(first_pass)) if first_pass else None,
            "rework_rate": (sum(rework) / len(rework)) if rework else None,
            "median_wall_time_seconds": _median(r["execution"]["wall_clock_seconds"] for r in members),
            "median_input_tokens": median_input,
            "median_input_tokens_n": input_n,
            "median_cached_input_tokens": median_cached,
            "median_cached_input_tokens_n": cached_n,
            "median_output_tokens": median_output,
            "median_output_tokens_n": output_n,
            "median_total_tokens": median_total,
            "median_total_tokens_n": total_n,
            "usage_total_runs": len(members),
            "usage_qualified_runs": total_n,
            "usage_quality_counts": usage_quality_counts,
            "median_weekly_allowance_pp_consumed": _median(total_allowance),
            "median_five_hour_allowance_pp_consumed": _median(r["economics"]["five_hour_pp_consumed"] for r in members),
            "accepted_runs_per_weekly_allowance_pp": (accepted / allowance_sum) if allowance_sum and allowance_sum > 0 else None,
        })
    return {
        "schema": SCHEMA,
        "report_kind": "SPEED_BENCHMARK" if speed_benchmark else "DESCRIPTIVE_OFFLINE",
        "groups": summaries,
        "run_count": len(folded),
        "include_synthetic": include_synthetic,
        "include_session_level": include_session_level,
        "session_level_run_count": session_level_run_count,
        "synthetic_run_count": len(synthetic_run_ids),
        "synthetic_runs_excluded": 0 if include_synthetic else len(synthetic_run_ids),
        "speed_benchmark_source": "LAUNCHER_EXPLICIT" if speed_benchmark else None,
        "speed_benchmark_excluded_runs": speed_benchmark_excluded_runs,
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
    create.add_argument("--speed-mode", choices=sorted(SPEED_MODES), default="UNKNOWN")
    create.add_argument("--speed-mode-source", choices=sorted(SPEED_MODE_SOURCES), default="NONE")
    create.add_argument("--root-model")
    create.add_argument("--root-reasoning-effort")
    create.add_argument("--profile")
    create.add_argument("--reasoning-effort-source", choices=sorted(REASONING_EFFORT_SOURCES))
    create.add_argument("--requested-worker-count", type=int)
    create.add_argument("--actual-worker-count", type=int)
    create.add_argument("--max-concurrency", type=int)
    create.add_argument("--worker", action="append", default=[], metavar="MODEL:EFFORT:STATUS")

    ingest = sub.add_parser("ingest-exec-json")
    ingest.add_argument("--run-id", required=True)
    ingest.add_argument("--source-file", required=True)
    ingest.add_argument("--thread-id", required=True)
    ingest.add_argument("--turn-id")
    sub.add_parser("hook", help="consume one Codex lifecycle hook JSON object from stdin")
    synthetic = sub.add_parser("ingest-synthetic")
    synthetic.add_argument("--run-id", required=True)
    for name in ("model-requests", "input-tokens", "cached-input-tokens", "cache-write-input-tokens", "output-tokens", "reasoning-tokens", "reasoning-output-tokens", "total-tokens"):
        synthetic.add_argument("--" + name, type=int)

    finalize = sub.add_parser("finalize")
    finalize.add_argument("--run-id", required=True)
    finalize.add_argument("--exec-json-file")
    finalize.add_argument("--exec-thread-id")
    finalize.add_argument("--exec-turn-id")
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
    summary.add_argument("--group-by", action="append", choices=["task_class", "mode", "speed_mode", "speed_mode_source", "root_model", "reasoning_effort", "worker_count", "usage_source", "usage_quality"])
    summary.add_argument("--include-synthetic", action="store_true")
    summary.add_argument("--include-session-level", action="store_true")
    summary.add_argument("--speed-benchmark", action="store_true", help="include only FAST/STANDARD runs certified by LAUNCHER_EXPLICIT")
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
            result = create_run(store, task_label=args.task_label, task_id=args.task_id, project_label=args.project_label, task_class=args.task_class, complexity=args.complexity, mode=args.mode, speed_mode=args.speed_mode, speed_mode_source=args.speed_mode_source, root_model=args.root_model, root_reasoning_effort=args.root_reasoning_effort, profile=args.profile, reasoning_effort_source=args.reasoning_effort_source, requested_worker_count=args.requested_worker_count, actual_worker_count=args.actual_worker_count, workers=workers, max_concurrency=args.max_concurrency, run_id=args.run_id)
        elif args.command == "ingest-exec-json":
            result = ingest_codex_exec_json(store, args.run_id, args.source_file, expected_thread_id=args.thread_id, expected_turn_id=args.turn_id)
        elif args.command == "ingest-synthetic":
            result = ingest_synthetic_usage(store, args.run_id, {"model_requests": args.model_requests, "input_tokens": args.input_tokens, "cached_input_tokens": args.cached_input_tokens, "cache_write_input_tokens": args.cache_write_input_tokens, "output_tokens": args.output_tokens, "reasoning_tokens": args.reasoning_tokens, "reasoning_output_tokens": args.reasoning_output_tokens, "total_tokens": args.total_tokens})
        elif args.command == "finalize":
            observation = None
            if args.exec_json_file:
                if not args.exec_thread_id:
                    raise TelemetryError("--exec-thread-id is required with --exec-json-file")
                observation = parse_codex_exec_json(args.exec_json_file, expected_thread_id=args.exec_thread_id, expected_turn_id=args.exec_turn_id)
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
            result = finalize_run(store, args.run_id, usage=latest_usage, usage_source=(observation.usage_source if observation else None), usage_quality=(observation.usage_quality if observation else None), execution=execution, result=result_fields, measurement=measurement)
        elif args.command == "snapshot":
            result = add_snapshot(store, args.run_id, source=args.source, snapshot_kind=args.snapshot_kind, five_hour_allowance_pp=args.five_hour_allowance_pp, weekly_allowance_pp=args.weekly_allowance_pp, credit_balance=args.credit_balance, measurement_quality=args.measurement_quality)
        elif args.command == "annotate":
            result = add_annotation(store, args.run_id, reviewer_verdict=args.reviewer_verdict, first_pass=args.first_pass, rework_required=args.rework_required, rework_reason_code=args.rework_reason_code, successor_run_id=args.successor_run_id)
        elif args.command == "import-manual":
            result = import_manual(store, label=args.label, source_note=args.source_note, root_model=args.root_model, reasoning_effort=args.reasoning_effort, mode=args.mode, worker_count=args.worker_count, values={"input_tokens": args.input_tokens, "cached_input_tokens": args.cached_input_tokens, "output_tokens": args.output_tokens, "total_tokens": args.total_tokens}, allowances={"weekly_before": args.weekly_before, "weekly_after": args.weekly_after, "five_hour_before": args.five_hour_before, "five_hour_after": args.five_hour_after})
        elif args.command == "report":
            _json_print(report(store, group_by=args.group_by, include_synthetic=args.include_synthetic, include_session_level=args.include_session_level, speed_benchmark=args.speed_benchmark))
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
