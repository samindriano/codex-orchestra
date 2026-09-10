"""Passive local telemetry for exact root/worker token attribution.

The hook path consumes only stable lifecycle metadata.  It never opens a
transcript or stores prompt, tool, or assistant content.  Exact token usage is
accepted only from the native aggregate OTel turn span; missing or ambiguous
identity remains UNKNOWN.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import http.server
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import tomllib
import uuid
from typing import Any, Iterable


SCHEMA = "orchestra_telemetry_v1"
LEDGER_NAME = "ledger.jsonl"
LOCK_NAME = "ledger.lock"
PENDING_NAME = "otel-pending.jsonl"
PENDING_LOCK_NAME = "otel-pending.lock"
RECORD_TYPES = {
    "turn_start",
    "turn_finalize",
    "worker_edge_observed",
    "worker_observed",
    "usage_observed",
    "session_observed",
}
USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "non_cached_input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)
OTEL_TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "non_cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)
USAGE_QUALITIES = {"EXACT", "UNKNOWN"}
USAGE_SOURCES = {"NATIVE_OTEL_TRACE", "NONE"}
TURN_STATUSES = {"STARTED", "COMPLETED", "INTERRUPTED", "UNKNOWN"}
WORKER_STATUSES = {"LAUNCHED", "COMPLETED", "CANCELLED", "FAILED", "UNKNOWN"}
MEASUREMENT_GENERATION = "TURN_LEVEL_V1_2"
_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@+-]{0,79}$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@+:/-]{0,119}$")
_DISABLED = {"0", "false", "off", "disabled", "no"}
_OTEL_SPAN_NAME = "session_task.turn"
_OTEL_HOST = "127.0.0.1"
_OTEL_PORT = 4318
_OTEL_MAX_BODY = 8 * 1024 * 1024


class TelemetryError(RuntimeError):
    """A fail-closed telemetry error."""


class LedgerCorruptionError(TelemetryError):
    """The ledger is not valid canonical JSONL."""


class DuplicateRecordError(TelemetryError):
    """An idempotency invariant rejected a duplicate."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def telemetry_enabled() -> bool:
    return os.environ.get("CODEX_ORCHESTRA_TELEMETRY", "1").strip().lower() not in _DISABLED


def _label(value: Any, *, field: str, required: bool = False) -> str | None:
    if value is None or value == "":
        if required:
            raise TelemetryError(f"{field} is required")
        return None
    if not isinstance(value, str) or not _LABEL_RE.fullmatch(value):
        raise TelemetryError(f"{field} must be a short path-free label")
    return value


def _model(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not _MODEL_RE.fullmatch(value):
        raise TelemetryError("model must be a short identifier")
    return value


def _nonnegative_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TelemetryError("token values must be non-negative integers or null")
    return value


def _usage(values: dict[str, Any] | None = None) -> dict[str, int | None]:
    values = values or {}
    result = {field: _nonnegative_int(values.get(field)) for field in USAGE_FIELDS}
    if result["reasoning_tokens"] is None:
        result["reasoning_tokens"] = result["reasoning_output_tokens"]
    if result["reasoning_output_tokens"] is None:
        result["reasoning_output_tokens"] = result["reasoning_tokens"]
    result["model_requests"] = _nonnegative_int(values.get("model_requests"))
    return result


def _measurement() -> dict[str, Any]:
    return {
        "measurement_generation": MEASUREMENT_GENERATION,
        "telemetry_tokens_added": 0,
        "telemetry_model_requests_added": 0,
    }


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


def _codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def default_store_root() -> Path:
    return _codex_home() / "orchestra-telemetry"


def _private_dir(path: Path) -> None:
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
        _private_dir(self.path.parent)
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

    def __exit__(self, *_args: Any) -> None:
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
        "turn_start": {"run_id", "session_id", "turn_id", "started_at_utc", "task", "orchestra", "usage", "usage_source", "usage_quality", "measurement", "turn_status"},
        "turn_finalize": {"run_id", "session_id", "turn_id", "ended_at_utc", "usage", "usage_source", "usage_quality", "measurement", "turn_status"},
        "worker_edge_observed": {"run_id", "parent_session_id", "parent_turn_id", "worker_id", "source_kind", "tool_name", "measurement_generation", "measurement_quality"},
        "worker_observed": {"run_id", "session_id", "turn_id", "worker_id", "agent_type", "model", "launch_status", "native_thread_id", "native_turn_id", "measurement_generation", "measurement_quality"},
        "usage_observed": {"run_id", "source_kind", "source_schema", "source_digest", "source_capability", "usage_source", "usage_quality", "session_id", "thread_id", "turn_id", "attribution_role", "worker_id", "usage", "observed_event_count", "measurement", "measurement_generation"},
        "session_observed": {"session_id", "lifecycle"},
    }
    return common | fields[record_type]


def _validate_record(record: dict[str, Any]) -> None:
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise LedgerCorruptionError("unsupported telemetry schema")
    record_type = record.get("record_type")
    if record_type not in RECORD_TYPES:
        raise LedgerCorruptionError(f"unsupported record type: {record_type!r}")
    required = {"schema", "record_type", "record_id", "recorded_at_utc"}
    if not required.issubset(record) or not isinstance(record["record_id"], str):
        raise LedgerCorruptionError("missing common ledger fields")
    unknown = set(record) - _allowed_fields(record_type)
    if unknown:
        raise LedgerCorruptionError(f"unrecognized fields in {record_type}: {sorted(unknown)}")


class TelemetryStore:
    """Private append-only JSONL storage with cross-process locking."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root).expanduser() if root is not None else default_store_root()
        self.ledger_path = self.root / LEDGER_NAME
        self.lock_path = self.root / LOCK_NAME

    def _read_unlocked(self) -> list[dict[str, Any]]:
        if not self.ledger_path.exists():
            return []
        if self.ledger_path.is_symlink() or not self.ledger_path.is_file():
            raise LedgerCorruptionError("ledger is not a regular file")
        raw = self.ledger_path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            raise LedgerCorruptionError("ledger has an unterminated final record")
        records: list[dict[str, Any]] = []
        ids: set[str] = set()
        for line_number, line in enumerate(raw.splitlines(), 1):
            try:
                record = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise LedgerCorruptionError(f"invalid JSON at line {line_number}") from exc
            _validate_record(record)
            if record["record_id"] in ids:
                raise LedgerCorruptionError("duplicate record id")
            ids.add(record["record_id"])
            records.append(record)
        return records

    def read(self) -> list[dict[str, Any]]:
        return self._read_unlocked()

    def _replace(self, previous: bytes, addition: bytes) -> None:
        _private_dir(self.root)
        fd, temporary = tempfile.mkstemp(prefix=".ledger.", suffix=".tmp", dir=str(self.root))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(previous)
                handle.write(addition)
                handle.flush()
                os.fsync(handle.fileno())
            last_error: PermissionError | None = None
            for delay in (0.0, 0.005, 0.02, 0.05):
                if delay:
                    time.sleep(delay)
                try:
                    os.replace(temporary, self.ledger_path)
                    last_error = None
                    break
                except PermissionError as exc:
                    last_error = exc
            if last_error is not None:
                raise last_error
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
            if any(item["record_id"] == record["record_id"] for item in existing):
                raise DuplicateRecordError("duplicate record id")
            if unique_run_id and any(
                item.get("record_type") == "turn_start" and item.get("run_id") == record.get("run_id")
                for item in existing
            ):
                raise DuplicateRecordError("run already exists")
            if unique_source_digest and any(
                item.get("record_type") == "usage_observed" and item.get("source_digest") == record.get("source_digest")
                for item in existing
            ):
                raise DuplicateRecordError("source has already been ingested")
            previous = self.ledger_path.read_bytes() if self.ledger_path.exists() else b""
            line = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            self._replace(previous, line)
        return record

    def run_records(self, run_id: str) -> list[dict[str, Any]]:
        records = [item for item in self.read() if item.get("run_id") == run_id]
        if not any(item.get("record_type") == "turn_start" for item in records):
            raise TelemetryError(f"unknown run id: {run_id}")
        return records


def _turn_run_id(session_id: str, turn_id: str) -> str:
    digest = hashlib.sha256(f"{session_id}\0{turn_id}".encode("utf-8")).hexdigest()[:24]
    return f"turn_{digest}"


def _empty_orchestra() -> dict[str, Any]:
    return {
        "root": {"model": None},
        "workers": [],
        "actual_worker_count": None,
        "worker_presence_quality": "UNKNOWN",
    }


def create_turn(
    store: TelemetryStore,
    *,
    session_id: str,
    turn_id: str,
    model: str | None = None,
    actual_worker_count: int | None = None,
    worker_presence_quality: str = "UNKNOWN",
) -> dict[str, Any]:
    session_id = _label(session_id, field="session_id", required=True)  # type: ignore[assignment]
    turn_id = _label(turn_id, field="turn_id", required=True)  # type: ignore[assignment]
    run_id = _turn_run_id(session_id, turn_id)
    orchestra = _empty_orchestra()
    orchestra["root"]["model"] = _model(model)
    if actual_worker_count is not None:
        if isinstance(actual_worker_count, bool) or actual_worker_count < 0:
            raise TelemetryError("actual_worker_count must be a non-negative integer")
        if worker_presence_quality not in {"EXACT", "UNKNOWN"}:
            raise TelemetryError("worker_presence_quality is not supported")
        orchestra["actual_worker_count"] = actual_worker_count
        orchestra["worker_presence_quality"] = worker_presence_quality
    record = _record(
        "turn_start",
        run_id=run_id,
        session_id=session_id,
        turn_id=turn_id,
        started_at_utc=_utc_now(),
        task={"task_label": "codex-turn"},
        orchestra=orchestra,
        usage=_usage(),
        usage_source="NONE",
        usage_quality="UNKNOWN",
        measurement=_measurement(),
        turn_status="STARTED",
    )
    try:
        return store.append(record, unique_run_id=True)
    except DuplicateRecordError:
        return next(item for item in store.run_records(run_id) if item.get("record_type") == "turn_start")


def observe_session(store: TelemetryStore, *, session_id: str, lifecycle: str) -> dict[str, Any]:
    return store.append(_record("session_observed", session_id=_label(session_id, field="session_id", required=True), lifecycle=_label(lifecycle, field="lifecycle", required=True)))


def observe_worker_edge(
    store: TelemetryStore,
    run_id: str,
    *,
    parent_session_id: str,
    parent_turn_id: str,
    worker_id: str,
    tool_name: str = "spawn_agent",
) -> dict[str, Any]:
    store.run_records(run_id)
    normalized = {
        "run_id": run_id,
        "parent_session_id": _label(parent_session_id, field="parent_session_id", required=True),
        "parent_turn_id": _label(parent_turn_id, field="parent_turn_id", required=True),
        "worker_id": _label(worker_id, field="worker_id", required=True),
        "source_kind": "CODEX_POST_TOOL_USE",
        "tool_name": _label(tool_name, field="tool_name", required=True),
        "measurement_generation": MEASUREMENT_GENERATION,
        "measurement_quality": "EXACT_MACHINE_READABLE",
    }
    with _LedgerLock(store.root / "worker-edge.lock"):
        for item in store.read():
            if item.get("record_type") == "worker_edge_observed" and all(item.get(key) == value for key, value in normalized.items()):
                return item
        return store.append(_record("worker_edge_observed", **normalized))


def observe_worker(
    store: TelemetryStore,
    run_id: str,
    *,
    worker_id: str,
    session_id: str,
    turn_id: str,
    launch_status: str,
    agent_type: str | None = None,
    model: str | None = None,
    native_thread_id: str | None = None,
    native_turn_id: str | None = None,
) -> dict[str, Any]:
    store.run_records(run_id)
    normalized_status = _label(launch_status, field="launch_status", required=True)
    if normalized_status not in WORKER_STATUSES:
        raise TelemetryError("launch_status is not supported")
    return store.append(_record(
        "worker_observed",
        run_id=run_id,
        session_id=_label(session_id, field="session_id"),
        turn_id=_label(turn_id, field="turn_id"),
        worker_id=_label(worker_id, field="worker_id", required=True),
        agent_type=_label(agent_type, field="agent_type"),
        model=_model(model),
        launch_status=normalized_status,
        native_thread_id=_label(native_thread_id, field="native_thread_id"),
        native_turn_id=_label(native_turn_id, field="native_turn_id"),
        measurement_generation=MEASUREMENT_GENERATION,
        measurement_quality="EXACT_MACHINE_READABLE",
    ))


def _aggregate_usage(records: Iterable[dict[str, Any]]) -> tuple[dict[str, int | None], str, str]:
    items = list(records)
    if not items:
        return _usage(), "NONE", "UNKNOWN"
    if not all(item.get("usage_quality") == "EXACT" for item in items):
        return _usage(), "NONE", "UNKNOWN"
    values = [_usage(item.get("usage")) for item in items]
    if not all(all(item[field] is not None for field in USAGE_FIELDS) for item in values):
        return _usage(), "NONE", "UNKNOWN"
    total = {field: sum(int(item[field] or 0) for item in values) for field in USAGE_FIELDS}
    total["model_requests"] = None
    return total, "NATIVE_OTEL_TRACE", "EXACT"


def _structured_child_ids(value: Any) -> list[str]:
    """Read only allowlisted IDs from structured spawn-result containers."""

    found: list[str] = []

    def add(candidate: Any) -> None:
        if isinstance(candidate, str) and _LABEL_RE.fullmatch(candidate) and candidate not in found:
            found.append(candidate)

    def visit(candidate: Any) -> None:
        if isinstance(candidate, dict):
            add(candidate.get("agent_id"))
            add(candidate.get("child_agent_id"))
            receiver_ids = candidate.get("receiver_thread_ids")
            if isinstance(receiver_ids, list):
                for item in receiver_ids:
                    add(item)
            states = candidate.get("agents_states")
            if isinstance(states, dict):
                for key in states:
                    add(key)
            for key in ("structured_content", "structuredContent", "result", "data"):
                visit(candidate.get(key))
        elif isinstance(candidate, str):
            try:
                decoded = json.loads(candidate)
            except (TypeError, ValueError):
                return
            visit(decoded)
        elif isinstance(candidate, list):
            for item in candidate:
                if isinstance(item, (dict, str)):
                    visit(item)

    visit(value)
    return found


def _worker_parent_run(store: TelemetryStore, worker_id: str) -> str | None:
    matches = {
        (item.get("run_id"), item.get("parent_session_id"), item.get("parent_turn_id"))
        for item in store.read()
        if item.get("record_type") == "worker_edge_observed" and item.get("worker_id") == worker_id
    }
    if len(matches) != 1:
        return None
    run_id, parent_session_id, parent_turn_id = next(iter(matches))
    if not all(isinstance(value, str) and value for value in (run_id, parent_session_id, parent_turn_id)):
        return None
    try:
        records = store.run_records(run_id)
    except TelemetryError:
        return None
    if not any(item.get("record_type") == "turn_start" and item.get("session_id") == parent_session_id and item.get("turn_id") == parent_turn_id for item in records):
        return None
    return run_id


def _parent_hook_run(store: TelemetryStore, session_id: str, turn_id: str) -> str | None:
    root = {
        item.get("run_id") for item in store.read()
        if item.get("record_type") == "turn_start" and item.get("session_id") == session_id and item.get("turn_id") == turn_id
    }
    if len(root) == 1:
        return next(iter(root))
    worker = {
        item.get("run_id") for item in store.read()
        if item.get("record_type") == "worker_observed" and item.get("session_id") == session_id and item.get("turn_id") == turn_id
    }
    return next(iter(worker)) if len(worker) == 1 else None


def _otel_scalar(value: Any) -> Any:
    if not isinstance(value, dict):
        return None
    for key in ("stringValue", "intValue", "longValue", "doubleValue", "boolValue"):
        if key in value:
            candidate = value[key]
            if key in {"intValue", "longValue"} and isinstance(candidate, str) and re.fullmatch(r"\d+", candidate):
                return int(candidate)
            return candidate
    return None


def _otel_attributes(span: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in span.get("attributes", []):
        if isinstance(item, dict) and isinstance(item.get("key"), str):
            result[item["key"]] = _otel_scalar(item.get("value"))
    return result


def _otel_span_items(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    result: list[dict[str, Any]] = []
    for resource in payload.get("resourceSpans", []):
        if not isinstance(resource, dict):
            continue
        scopes = resource.get("scopeSpans") or resource.get("instrumentationLibrarySpans") or []
        for scope in scopes:
            if not isinstance(scope, dict):
                continue
            for span in scope.get("spans", []):
                if not isinstance(span, dict) or span.get("name") != _OTEL_SPAN_NAME:
                    continue
                attrs = _otel_attributes(span)
                thread_id = attrs.get("thread.id")
                turn_id = attrs.get("turn.id")
                if not isinstance(thread_id, str) or not _LABEL_RE.fullmatch(thread_id) or not isinstance(turn_id, str) or not _LABEL_RE.fullmatch(turn_id):
                    continue
                usage: dict[str, int | None] = {field: None for field in OTEL_TOKEN_FIELDS}
                malformed = False
                for field in OTEL_TOKEN_FIELDS:
                    value = attrs.get(f"codex.turn.token_usage.{field}")
                    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                        malformed = True
                    else:
                        usage[field] = value
                normalized = {"thread_id": thread_id, "turn_id": turn_id, "usage": usage, "malformed": malformed}
                normalized["source_digest"] = hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
                result.append(normalized)
    return result


def _pending_read(store: TelemetryStore) -> list[dict[str, Any]]:
    path = store.root / PENDING_NAME
    if not path.exists() or path.is_symlink() or not path.is_file():
        return []
    result: list[dict[str, Any]] = []
    for line in path.read_bytes().splitlines():
        try:
            item = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(item, dict) and isinstance(item.get("source_digest"), str):
            result.append(item)
    return result


def _pending_write(store: TelemetryStore, items: list[dict[str, Any]]) -> None:
    path = store.root / PENDING_NAME
    if not items:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    _private_dir(store.root)
    fd, temporary = tempfile.mkstemp(prefix=".otel-pending.", suffix=".tmp", dir=str(store.root))
    try:
        with os.fdopen(fd, "wb") as handle:
            for item in items:
                handle.write(json.dumps(item, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _otel_target(store: TelemetryStore, item: dict[str, Any]) -> tuple[str, str | None] | None:
    thread_id, turn_id = item.get("thread_id"), item.get("turn_id")
    if not isinstance(thread_id, str) or not isinstance(turn_id, str):
        return None
    records = store.read()
    roots = {
        (record.get("run_id"), None)
        for record in records
        if record.get("record_type") == "turn_start" and record.get("session_id") == thread_id and record.get("turn_id") == turn_id
    }
    workers = {
        (record.get("run_id"), record.get("worker_id"))
        for record in records
        if record.get("record_type") == "worker_observed" and record.get("native_thread_id") == thread_id and record.get("native_turn_id") == turn_id
    }
    matches = roots | workers
    if len(matches) != 1:
        return None
    run_id, worker_id = next(iter(matches))
    return (str(run_id), str(worker_id) if worker_id is not None else None)


def _otel_attach(store: TelemetryStore, item: dict[str, Any], target: tuple[str, str | None]) -> None:
    run_id, worker_id = target
    same_key = [
        record for record in store.run_records(run_id)
        if record.get("record_type") == "usage_observed"
        and record.get("usage_source") == "NATIVE_OTEL_TRACE"
        and record.get("thread_id") == item.get("thread_id")
        and record.get("turn_id") == item.get("turn_id")
    ]
    if any(record.get("source_digest") == item.get("source_digest") for record in same_key):
        return
    conflict = bool(same_key)
    usage = _usage(item.get("usage") if not conflict and not item.get("malformed") else {})
    quality = "UNKNOWN" if conflict or item.get("malformed") else "EXACT"
    source = "NATIVE_OTEL_TRACE" if quality == "EXACT" else "NATIVE_OTEL_CONFLICT"
    record = _record(
        "usage_observed",
        run_id=run_id,
        source_kind=source,
        source_schema="otel.session_task.turn",
        source_digest=item["source_digest"],
        source_capability="USAGE_SOURCE_SUPPORTED" if quality == "EXACT" else "USAGE_SOURCE_UNSTABLE",
        usage_source="NATIVE_OTEL_TRACE",
        usage_quality=quality,
        session_id=item.get("thread_id"),
        thread_id=item.get("thread_id"),
        turn_id=item.get("turn_id"),
        attribution_role="WORKER" if worker_id is not None else "ROOT",
        worker_id=worker_id,
        usage=usage,
        observed_event_count=1,
        measurement=_measurement(),
        measurement_generation=MEASUREMENT_GENERATION,
    )
    try:
        store.append(record, unique_source_digest=True)
    except DuplicateRecordError:
        return


def _reconcile_otel_pending(store: TelemetryStore) -> int:
    with _LedgerLock(store.root / PENDING_LOCK_NAME):
        pending = _pending_read(store)
        remaining: list[dict[str, Any]] = []
        attached = 0
        for item in pending:
            target = _otel_target(store, item)
            if target is None:
                remaining.append(item)
            else:
                _otel_attach(store, item, target)
                attached += 1
        _pending_write(store, remaining)
        return attached


def ingest_otel_payload(store: TelemetryStore, payload: Any) -> int:
    accepted = 0
    for item in _otel_span_items(payload):
        target = _otel_target(store, item)
        if target is None:
            with _LedgerLock(store.root / PENDING_LOCK_NAME):
                pending = _pending_read(store)
                if item["source_digest"] not in {entry.get("source_digest") for entry in pending}:
                    pending.append(item)
                    _pending_write(store, pending)
        else:
            _otel_attach(store, item, target)
            accepted += 1
    _reconcile_otel_pending(store)
    return accepted


def _finalize_turn(store: TelemetryStore, run_id: str, *, session_id: str, turn_id: str, status: str) -> dict[str, Any]:
    if status not in TURN_STATUSES:
        raise TelemetryError("turn status is not supported")
    records = store.run_records(run_id)
    existing = next((item for item in records if item.get("record_type") == "turn_finalize"), None)
    if existing is not None:
        return existing
    root_usage, source, quality = _aggregate_usage(
        item for item in records if item.get("record_type") == "usage_observed" and item.get("attribution_role") == "ROOT"
    )
    return store.append(_record(
        "turn_finalize",
        run_id=run_id,
        session_id=session_id,
        turn_id=turn_id,
        ended_at_utc=_utc_now(),
        usage=root_usage,
        usage_source=source,
        usage_quality=quality,
        measurement=_measurement(),
        turn_status=status,
    ))


def handle_hook_event(store: TelemetryStore, event: dict[str, Any]) -> dict[str, Any]:
    """Process one stable hook event without reading any transcript path."""

    if not telemetry_enabled():
        return {"status": "DISABLED"}
    if not isinstance(event, dict) or not isinstance(event.get("hook_event_name"), str) or not isinstance(event.get("session_id"), str):
        raise TelemetryError("hook input lacks event name or session id")
    event_name = event["hook_event_name"]
    session_id = _label(event["session_id"], field="session_id", required=True)
    if event_name == "SessionStart":
        ensure_otel_receiver(store)
        _reconcile_otel_pending(store)
        try:
            record = observe_session(store, session_id=session_id, lifecycle="STARTED")  # type: ignore[arg-type]
        except DuplicateRecordError:
            record = {"session_id": session_id}
        return {"status": "SESSION_STARTED", "session_id": record["session_id"]}
    if event_name == "SessionEnd":
        _reconcile_otel_pending(store)
        record = observe_session(store, session_id=session_id, lifecycle="ENDED")  # type: ignore[arg-type]
        return {"status": "SESSION_ENDED", "session_id": record["session_id"]}
    if event_name == "PostToolUse" and event.get("tool_name") not in {"spawn_agent", "Agent"}:
        return {"status": "IGNORED", "event": event_name}
    if event_name not in {"UserPromptSubmit", "PostToolUse", "SubagentStart", "SubagentStop", "Stop", "Interrupt"}:
        return {"status": "IGNORED", "event": event_name}
    turn_id = _label(event.get("turn_id"), field="turn_id", required=True)
    raw_worker_id = event.get("agent_id") if event_name in {"SubagentStart", "SubagentStop"} else None
    run_id = _parent_hook_run(store, session_id, turn_id)
    if run_id is None and isinstance(raw_worker_id, str):
        run_id = _worker_parent_run(store, raw_worker_id)
    if run_id is None:
        run_id = create_turn(store, session_id=session_id, turn_id=turn_id, model=event.get("model"))["run_id"]
    if event_name == "UserPromptSubmit":
        _reconcile_otel_pending(store)
        return {"status": "TURN_STARTED", "run_id": run_id, "turn_id": turn_id}
    if event_name == "PostToolUse":
        ids = _structured_child_ids(event.get("tool_response"))
        for worker_id in ids:
            observe_worker_edge(store, run_id, parent_session_id=session_id, parent_turn_id=turn_id, worker_id=worker_id, tool_name=event["tool_name"])
        _reconcile_otel_pending(store)
        return {"status": "WORKER_EDGES_OBSERVED", "run_id": run_id, "edge_count": len(ids)}
    if event_name in {"SubagentStart", "SubagentStop"}:
        if not isinstance(raw_worker_id, str):
            return {"status": "WORKER_IDENTITY_UNKNOWN", "run_id": run_id}
        parent = _worker_parent_run(store, raw_worker_id)
        if parent is not None:
            run_id = parent
        worker_id = _label(raw_worker_id, field="agent_id", required=True)
        native_thread_id = _label(event.get("native_thread_id") or worker_id, field="native_thread_id")
        native_turn_id = _label(event.get("native_turn_id") or turn_id, field="native_turn_id")
        observe_worker(
            store,
            run_id,
            worker_id=worker_id,
            session_id=session_id,
            turn_id=turn_id,
            launch_status="LAUNCHED" if event_name == "SubagentStart" else "COMPLETED",
            agent_type=event.get("agent_type"),
            model=event.get("model"),
            native_thread_id=native_thread_id,
            native_turn_id=native_turn_id,
        )
        _reconcile_otel_pending(store)
        return {"status": "WORKER_STARTED" if event_name == "SubagentStart" else "WORKER_STOPPED", "run_id": run_id}
    status = "INTERRUPTED" if event_name == "Interrupt" else "COMPLETED"
    result = _finalize_turn(store, run_id, session_id=session_id, turn_id=turn_id, status=status)
    _reconcile_otel_pending(store)
    return {"status": "TURN_INTERRUPTED" if status == "INTERRUPTED" else "TURN_FINALIZED", "run_id": run_id, "turn_id": turn_id, "record_id": result["record_id"]}


class _OTELServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class _OTELHandler(http.server.BaseHTTPRequestHandler):
    server_version = "CodexOrchestraOTel/1"

    def log_message(self, *_args: Any) -> None:
        return

    def _reply(self, status: int, body: bytes = b"ok") -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        self._reply(200, b"codex-orchestra-otel") if self.path == "/health" else self._reply(404, b"")

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 0 or length > _OTEL_MAX_BODY:
            self._reply(413, b"")
            return
        body = self.rfile.read(length)
        if self.path == "/v1/traces":
            try:
                ingest_otel_payload(self.server.store, json.loads(body.decode("utf-8")))  # type: ignore[attr-defined]
            except Exception:
                pass
        self._reply(200)


def run_otel_receiver(store: TelemetryStore, *, host: str = _OTEL_HOST, port: int = _OTEL_PORT) -> None:
    _private_dir(store.root)
    server = _OTELServer((host, port), _OTELHandler)
    server.store = store  # type: ignore[attr-defined]
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()


def _otel_configured() -> bool:
    try:
        config = tomllib.loads((_codex_home() / "config.toml").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        return False
    return isinstance(config.get("otel"), dict) and isinstance(config["otel"].get("trace_exporter"), dict)


def ensure_otel_receiver(store: TelemetryStore, *, host: str = _OTEL_HOST, port: int = _OTEL_PORT) -> bool:
    """Start only the default local receiver when native OTel is configured."""

    if store.root.resolve() != default_store_root().resolve() or not _otel_configured():
        return False
    try:
        connection = http.client.HTTPConnection(host, port, timeout=0.15)
        connection.request("GET", "/health")
        if connection.getresponse().status == 200:
            connection.close()
            return True
        connection.close()
    except OSError:
        pass
    command = [sys.executable, str(Path(__file__).resolve()), "--store", str(store.root), "otel-receiver", "--host", host, "--port", str(port)]
    try:
        kwargs: dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(command, **kwargs)
    except OSError:
        return False
    deadline = time.monotonic() + 0.8
    while time.monotonic() < deadline:
        try:
            connection = http.client.HTTPConnection(host, port, timeout=0.15)
            connection.request("GET", "/health")
            if connection.getresponse().status == 200:
                connection.close()
                return True
            connection.close()
        except OSError:
            pass
        time.sleep(0.03)
    return False


def _fold_run(records: list[dict[str, Any]]) -> dict[str, Any]:
    start = next(item for item in records if item.get("record_type") == "turn_start")
    root_records = [item for item in records if item.get("record_type") == "usage_observed" and item.get("attribution_role") == "ROOT"]
    root_usage, root_source, root_quality = _aggregate_usage(root_records)
    workers: dict[str, dict[str, Any]] = {}
    worker_records: dict[str, list[dict[str, Any]]] = {}
    unmatched_worker_usage = 0
    ambiguous_usage = 0
    for item in records:
        if item.get("record_type") == "worker_observed" and isinstance(item.get("worker_id"), str):
            workers[item["worker_id"]] = {
                "worker_id": item["worker_id"],
                "agent_type": item.get("agent_type"),
                "model": item.get("model"),
                "launch_status": item.get("launch_status"),
                "native_thread_id": item.get("native_thread_id"),
                "native_turn_id": item.get("native_turn_id"),
            }
        elif item.get("record_type") == "usage_observed" and item.get("attribution_role") == "WORKER":
            if isinstance(item.get("worker_id"), str):
                worker_records.setdefault(item["worker_id"], []).append(item)
            else:
                unmatched_worker_usage += 1
        elif item.get("record_type") == "usage_observed" and item.get("attribution_role") not in {"ROOT", "WORKER"}:
            ambiguous_usage += 1
    for worker_id, worker in workers.items():
        usage, source, quality = _aggregate_usage(worker_records.get(worker_id, []))
        worker["usage"] = usage
        worker["usage_source"] = source
        worker["usage_quality"] = quality
    unmatched_worker_ids = set(worker_records) - set(workers)
    declared_count = start.get("orchestra", {}).get("actual_worker_count")
    if workers and (declared_count is None or declared_count == len(workers)):
        presence_quality = "EXACT"
    elif declared_count == 0 and start.get("orchestra", {}).get("worker_presence_quality") == "EXACT":
        presence_quality = "EXACT"
    else:
        presence_quality = "UNKNOWN"
    worker_exact = bool(workers) and presence_quality == "EXACT" and not unmatched_worker_ids and not unmatched_worker_usage and all(worker["usage_quality"] == "EXACT" for worker in workers.values())
    if not workers and declared_count == 0 and presence_quality == "EXACT":
        worker_exact = True
    worker_total = sum(worker["usage"]["total_tokens"] for worker in workers.values()) if worker_exact else (0 if not workers and declared_count == 0 else None)
    orchestra_total = root_usage["total_tokens"] + worker_total if root_quality == "EXACT" and worker_exact and root_usage["total_tokens"] is not None and worker_total is not None else None
    orchestra = dict(start.get("orchestra", {}))
    orchestra.update({
        "workers": list(workers.values()),
        "actual_worker_count": len(workers) if workers else declared_count,
        "worker_presence_quality": presence_quality,
        "worker_total_tokens": worker_total,
        "worker_total_quality": "EXACT" if worker_exact else "UNKNOWN",
        "orchestra_total_tokens": orchestra_total,
        "orchestra_total_quality": "EXACT" if orchestra_total is not None else "UNKNOWN",
        "root_turn_tokens": root_usage,
        "individual_worker_tokens": {worker_id: worker["usage"] for worker_id, worker in workers.items()},
    })
    if unmatched_worker_ids or unmatched_worker_usage:
        orchestra["worker_usage_unmatched"] = True
    if ambiguous_usage:
        orchestra["ambiguous_usage"] = True
    return {
        "run_id": start["run_id"],
        "session_id": start.get("session_id"),
        "turn_id": start.get("turn_id"),
        "started_at_utc": start.get("started_at_utc"),
        "ended_at_utc": next((item.get("ended_at_utc") for item in records if item.get("record_type") == "turn_finalize"), None),
        "usage": root_usage,
        "usage_source": root_source,
        "usage_quality": root_quality,
        "orchestra": orchestra,
        "turn_status": next((item.get("turn_status") for item in reversed(records) if item.get("record_type") == "turn_finalize"), "UNKNOWN"),
    }


def report(store: TelemetryStore) -> dict[str, Any]:
    runs: dict[str, list[dict[str, Any]]] = {}
    for item in store.read():
        if item.get("run_id"):
            runs.setdefault(item["run_id"], []).append(item)
    rows = [_fold_run(items) for items in runs.values() if any(item.get("record_type") == "turn_start" for item in items)]
    return {
        "schema": SCHEMA,
        "run_count": len(rows),
        "exact_count": sum(row["usage_quality"] == "EXACT" for row in rows),
        "turns": rows,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", default=str(default_store_root()))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("hook")
    receiver = sub.add_parser("otel-receiver")
    receiver.add_argument("--host", default=_OTEL_HOST)
    receiver.add_argument("--port", type=int, default=_OTEL_PORT)
    sub.add_parser("report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    store = TelemetryStore(args.store)
    if args.command == "otel-receiver":
        run_otel_receiver(store, host=args.host, port=args.port)
        return 0
    if args.command == "hook":
        try:
            payload = json.load(sys.stdin)
            handle_hook_event(store, payload)
        except Exception:
            pass
        return 0
    print(json.dumps(report(store), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
