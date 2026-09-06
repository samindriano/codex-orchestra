#!/usr/bin/env python3
"""Install and verify the reusable Codex Orchestra global policy.

The installer deliberately has a small write surface.  Repository-owned text
and profile files are copied to their canonical locations; an existing
``config.toml`` is edited only at the two ``[agents]`` defaults and, when
explicitly requested, the context-management capability flag.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Iterable
import tomllib


ASTRA_MODEL = "gpt-6-astra"
LUNA_MODEL = "gpt-5.6-luna"
LUNA_REASONING = "xhigh"

_SOURCE_DESTINATIONS = (
    ("policies/GLOBAL_AGENTS.md", "AGENTS.md", "text"),
    (
        "skills/astra-decision-orchestrator/SKILL.md",
        "skills/astra-decision-orchestrator/SKILL.md",
        "text",
    ),
    ("skills/luna-orchestra/SKILL.md", "skills/luna-orchestra/SKILL.md", "text"),
    ("skills/orchestrate/SKILL.md", "skills/orchestrate/SKILL.md", "text"),
    ("config/global-astra.config.toml", "global-astra.config.toml", "profile"),
    ("config/global-luna.config.toml", "global-luna.config.toml", "profile"),
    ("config/agents/default.toml", "agents/default.toml", "role"),
    ("config/agents/worker.toml", "agents/worker.toml", "role"),
    ("config/agents/explorer.toml", "agents/explorer.toml", "role"),
)

_ROLE_MODELS = {
    "default.toml": LUNA_MODEL,
    "worker.toml": LUNA_MODEL,
    "explorer.toml": LUNA_MODEL,
}
_PROFILE_MODELS = {
    "global-astra.config.toml": ASTRA_MODEL,
    "global-luna.config.toml": LUNA_MODEL,
}
_PROFILE_REASONING = {
    "global-astra.config.toml": "medium",
    "global-luna.config.toml": LUNA_REASONING,
}
_MANAGED_CONFIG_PATHS = {
    ("agents", "default_subagent_model"): LUNA_MODEL,
    ("agents", "default_subagent_reasoning_effort"): LUNA_REASONING,
}
_ROLE_CONFIG_PATHS = {
    ("agents", "default", "config_file"): "./agents/default.toml",
    ("agents", "worker", "config_file"): "./agents/worker.toml",
    ("agents", "explorer", "config_file"): "./agents/explorer.toml",
}
_CONTEXT_PATH = ("features", "context_management", "experimental_mode")
_SECTION_RE = re.compile(r"^\s*\[([^\[\]]+)\]\s*(?:#.*)?(?:\r?\n)?$")
_ASSIGNMENT_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(.*?)(\r?\n)?$")


class PolicyError(RuntimeError):
    """A fail-closed policy installation or verification error."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _toml_bytes(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise PolicyError(f"invalid TOML {path}: {exc}") from exc


def _toml_source(path: Path, data: bytes | None = None) -> dict[str, Any]:
    try:
        return tomllib.loads((data if data is not None else path.read_bytes()).decode("utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise PolicyError(f"invalid TOML {path}: {exc}") from exc


def _get_path(data: dict[str, Any], path: Iterable[str]) -> Any:
    value: Any = data
    for component in path:
        if not isinstance(value, dict) or component not in value:
            return None
        value = value[component]
    return value


def _set_path(data: dict[str, Any], path: Iterable[str], value: Any) -> None:
    parts = list(path)
    current = data
    for component in parts[:-1]:
        current = current.setdefault(component, {})
    current[parts[-1]] = value


def _scan_multiline_state(line: str, state: str | None) -> str | None:
    """Track TOML multiline basic/literal strings without parsing assignments."""

    index = 0
    while index < len(line):
        if state:
            end = line.find(state, index)
            if end < 0:
                return state
            # A TOML quote is escaped only for basic multiline strings.  A
            # literal triple quote has no escape syntax.
            if state == '"""':
                backslashes = 0
                cursor = end - 1
                while cursor >= 0 and line[cursor] == "\\":
                    backslashes += 1
                    cursor -= 1
                if backslashes % 2:
                    index = end + 3
                    continue
            index = end + 3
            state = None
            continue

        if line.startswith('"""', index):
            state = '"""'
            index += 3
            continue
        if line.startswith("'''", index):
            state = "'''"
            index += 3
            continue
        if line[index] == "#":
            break
        if line[index] in ('"', "'"):
            quote = line[index]
            index += 1
            while index < len(line):
                if line[index] == quote and (quote == "'" or line[index - 1] != "\\"):
                    index += 1
                    break
                index += 1
            continue
        index += 1
    return state


def _section_ranges(text: str) -> tuple[list[str], dict[str, tuple[int, int]]]:
    lines = text.splitlines(keepends=True)
    ranges: dict[str, tuple[int, int]] = {}
    current: str | None = None
    start = 0
    state: str | None = None
    for index, line in enumerate(lines):
        if state is None:
            match = _SECTION_RE.match(line)
            if match:
                # Array-of-table headers are excluded by the regex, and a
                # duplicate table is ambiguous for a surgical edit.
                section = match.group(1).strip()
                if section in ranges:
                    raise PolicyError(f"ambiguous duplicate TOML table [{section}]")
                if current is not None:
                    ranges[current] = (start, index)
                current = section
                start = index
        state = _scan_multiline_state(line, state)
    if current is not None:
        ranges[current] = (start, len(lines))
    return lines, ranges


def _comment_start(value: str) -> int | None:
    state: str | None = None
    index = 0
    while index < len(value):
        if state:
            if value[index] == state and (state == "'" or index == 0 or value[index - 1] != "\\"):
                state = None
            index += 1
            continue
        if value[index] in ('"', "'"):
            state = value[index]
        elif value[index] == "#":
            return index
        index += 1
    return None


def _replace_key_in_section(
    lines: list[str],
    ranges: dict[str, tuple[int, int]],
    section: str,
    key: str,
    rendered: str,
) -> bool:
    """Replace one simple scalar or insert it, preserving all other bytes."""

    if section not in ranges:
        return False
    start, end = ranges[section]
    found: list[int] = []
    state: str | None = None
    for index in range(start + 1, end):
        line = lines[index]
        if state is None:
            match = _ASSIGNMENT_RE.match(line)
            if match and match.group(2) == key:
                found.append(index)
        state = _scan_multiline_state(line, state)
    if len(found) > 1:
        raise PolicyError(f"ambiguous duplicate key {section}.{key}")
    if found:
        index = found[0]
        match = _ASSIGNMENT_RE.match(lines[index])
        assert match is not None
        value = match.group(3)
        comment = _comment_start(value)
        suffix = ""
        if comment is not None:
            suffix = value[comment:]
        newline = "\r\n" if lines[index].endswith("\r\n") else "\n" if lines[index].endswith("\n") else ""
        lines[index] = f"{match.group(1)}{key} = {rendered}{('  ' + suffix.lstrip()) if suffix else ''}{newline}"
        return True

    newline = "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"
    insertion = f"{key} = {rendered}{newline}"
    lines.insert(end, insertion)
    # Later ranges are invalid after an insertion; callers perform one edit at
    # a time and recompute them.
    return True


def _ensure_section(text: str, section: str, key: str, rendered: str) -> str:
    lines, ranges = _section_ranges(text)
    if section in ranges:
        _replace_key_in_section(lines, ranges, section, key, rendered)
        return "".join(lines)

    newline = "\r\n" if "\r\n" in text else "\n"
    if text and not text.endswith(("\n", "\r")):
        text += newline
    return text + f"[{section}]{newline}{key} = {rendered}{newline}"


def _edit_config(config_path: Path, enable_context_management: bool) -> tuple[bytes, bytes, dict[str, Any]]:
    before = config_path.read_bytes() if config_path.exists() else b""
    before_data = _toml_source(config_path, before)
    text = before.decode("utf-8")

    # Recompute table ranges after each insertion.  This keeps edits safe when
    # a fixture has no existing key/table and avoids broad regex rewrites.
    for path, value in _MANAGED_CONFIG_PATHS.items():
        section, key = path
        lines, ranges = _section_ranges(text)
        if section in ranges:
            _replace_key_in_section(lines, ranges, section, key, json.dumps(value))
            text = "".join(lines)
        else:
            text = _ensure_section(text, section, key, json.dumps(value))

    # A newly created base config needs role pins so the installed legacy
    # ``./agents/*.toml`` files are actually reachable.  Existing configs are
    # left byte-for-byte alone at these paths and are checked separately.
    if not before:
        for path, value in _ROLE_CONFIG_PATHS.items():
            section = ".".join(path[:-1])
            text = _ensure_section(text, section, path[-1], json.dumps(value))

    if enable_context_management:
        section = "features.context_management"
        text = _ensure_section(text, section, "experimental_mode", "true")

    after = text.encode("utf-8")
    after_data = _toml_source(config_path, after)
    owned = set(_MANAGED_CONFIG_PATHS)
    if not before:
        owned.update(_ROLE_CONFIG_PATHS)
    if enable_context_management:
        owned.add(_CONTEXT_PATH)
    _assert_unowned_semantic_equivalence(before_data, after_data, owned, config_path)
    return before, after, after_data


def _assert_unowned_semantic_equivalence(
    before: dict[str, Any], after: dict[str, Any], owned_paths: set[tuple[str, ...]], path: Path
) -> None:
    def prune(value: Any, prefix: tuple[str, ...]) -> tuple[bool, Any]:
        if prefix in owned_paths:
            return False, None
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, child in value.items():
                keep, cleaned = prune(child, prefix + (str(key),))
                if keep:
                    result[key] = cleaned
            return bool(result), result
        return True, value

    _, clean_before = prune(before, ())
    _, clean_after = prune(after, ())
    if clean_before != clean_after:
        raise PolicyError(f"surgical TOML edit changed an unowned setting in {path}")


def _validate_profile(
    data: dict[str, Any],
    path: Path,
    expected_model: str,
    role: bool,
    marker: str,
    expected_reasoning: str,
) -> None:
    developer_instructions = data.get("developer_instructions")
    if not isinstance(developer_instructions, str) or not developer_instructions.strip():
        raise PolicyError(f"{path} lacks a non-empty developer_instructions marker")
    if marker not in developer_instructions:
        raise PolicyError(f"{path} developer_instructions must include {marker!r}")
    if data.get("model") != expected_model:
        raise PolicyError(f"{path} model must be {expected_model!r}")
    if data.get("model_reasoning_effort") != expected_reasoning:
        raise PolicyError(f"{path} model_reasoning_effort must be {expected_reasoning!r}")
    if role:
        agents = data.get("agents")
        if not isinstance(agents, dict) or agents.get("enabled") is not False:
            raise PolicyError(f"{path} [agents].enabled must be false")


def _validate_existing_profile(target: Path, source_data: dict[str, Any], kind: str) -> dict[str, Any] | None:
    if not target.exists():
        return None
    target_data = _toml_bytes(target)
    def unknown_paths(target_value: Any, source_value: Any, prefix: tuple[str, ...] = ()) -> list[str]:
        if isinstance(target_value, dict):
            result: list[str] = []
            source_dict = source_value if isinstance(source_value, dict) else {}
            for key, value in target_value.items():
                child = prefix + (str(key),)
                if key not in source_dict:
                    result.append(".".join(child))
                else:
                    result.extend(unknown_paths(value, source_dict[key], child))
            return result
        return []

    unknown = unknown_paths(target_data, source_data)
    if unknown:
        raise PolicyError(f"refusing to clobber unrecognized settings in {target}: {', '.join(unknown)}")
    return target_data


def _validate_source_tree(source_root: Path) -> list[tuple[Path, Path, str, bytes, dict[str, Any] | None]]:
    planned: list[tuple[Path, Path, str, bytes, dict[str, Any] | None]] = []
    for source_rel, target_rel, kind in _SOURCE_DESTINATIONS:
        source = source_root / Path(source_rel)
        if not source.is_file():
            raise PolicyError(f"missing canonical source artifact: {source}")
        data = source.read_bytes()
        parsed: dict[str, Any] | None = None
        if kind in {"profile", "role"}:
            parsed = _toml_source(source, data)
            if kind == "profile":
                expected = _PROFILE_MODELS[Path(source_rel).name]
                marker = "ASTRA_ROOT" if expected == ASTRA_MODEL else "LUNA_ROOT"
                _validate_profile(
                    parsed,
                    source,
                    expected,
                    role=False,
                    marker=marker,
                    expected_reasoning=_PROFILE_REASONING[Path(source_rel).name],
                )
            else:
                expected = _ROLE_MODELS[Path(source_rel).name]
                _validate_profile(
                    parsed,
                    source,
                    expected,
                    role=True,
                    marker="LUNA_WORKER",
                    expected_reasoning=LUNA_REASONING,
                )
        planned.append((source, Path(target_rel), kind, data, parsed))
    return planned


def _config_file_has_legacy_agent_pins(data: dict[str, Any], path: Path) -> None:
    for role in ("default", "worker", "explorer"):
        table = data.get("agents", {}).get(role) if isinstance(data.get("agents"), dict) else None
        if not isinstance(table, dict):
            continue
        expected = f"./agents/{role}.toml"
        if "config_file" in table and table["config_file"] != expected:
            raise PolicyError(f"{path} [agents.{role}].config_file must remain {expected!r}")


def _plan(
    source_root: Path, codex_home: Path, enable_context_management: bool
) -> tuple[list[tuple[Path, Path, bytes, str]], tuple[Path, bytes, bytes, dict[str, Any]] | None]:
    source_entries = _validate_source_tree(source_root)
    changes: list[tuple[Path, Path, bytes, str]] = []
    for source, target_rel, kind, data, parsed in source_entries:
        target = codex_home / target_rel
        if target.exists() and not target.is_file():
            raise PolicyError(f"installed destination is not a file: {target}")
        if target.exists() and kind in {"profile", "role"}:
            _validate_existing_profile(target, parsed or {}, kind)
        existing = target.read_bytes() if target.is_file() else None
        if existing != data:
            changes.append((source, target, data, kind))

    config_change: tuple[Path, bytes, bytes, dict[str, Any]] | None = None
    config_path = codex_home / "config.toml"
    if config_path.exists() or enable_context_management:
        before, after, after_data = _edit_config(config_path, enable_context_management)
        _config_file_has_legacy_agent_pins(after_data, config_path)
        if before != after:
            config_change = (config_path, before, after, after_data)
    else:
        # The global role files need a base config even on a fresh CODEX_HOME.
        before, after, after_data = _edit_config(config_path, False)
        _config_file_has_legacy_agent_pins(after_data, config_path)
        config_change = (config_path, before, after, after_data)
    return changes, config_change


def _backup_dir(codex_home: Path) -> Path:
    root = codex_home / "orchestra-backups"
    if root.exists() and not root.is_dir():
        raise PolicyError(f"backup path is not a directory: {root}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = root / stamp
    suffix = 0
    while candidate.exists():
        suffix += 1
        candidate = root / f"{stamp}-{suffix}"
    return candidate


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _copy_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _manifest(
    codex_home: Path,
    backup_path: Path,
    entries: list[tuple[Path, Path, bytes, str]],
    config_change: tuple[Path, bytes, bytes, dict[str, Any]] | None,
    backups: list[dict[str, str]],
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    installed: list[dict[str, str]] = []
    for _, target, data, _ in entries:
        if target.is_file():
            installed.append({"path": target.relative_to(codex_home).as_posix(), "sha256": _sha256_file(target)})
        else:
            installed.append({"path": target.relative_to(codex_home).as_posix(), "sha256": _sha256_bytes(data)})
    if config_change is not None:
        target = config_change[0]
        installed.append({"path": target.relative_to(codex_home).as_posix(), "sha256": _sha256_file(target)})
    payload: dict[str, Any] = {
        "version": 1,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "codex_home": str(codex_home),
        "installed": installed,
        "backups": backups,
    }
    if error:
        payload["error"] = error
    return payload


def install(
    codex_home: Path | str | None = None,
    *,
    dry_run: bool = False,
    enable_context_management: bool = False,
    source_root: Path | str | None = None,
) -> dict[str, Any]:
    """Plan or install the global policy and return a machine-readable report."""

    home = Path(codex_home or os.environ.get("CODEX_HOME") or (Path.home() / ".codex")).expanduser().resolve()
    root = Path(source_root).resolve() if source_root is not None else Path(__file__).resolve().parents[1]
    entries, config_change = _plan(root, home, enable_context_management)
    changed_targets = [target for _, target, _, _ in entries]
    if config_change is not None:
        changed_targets.append(config_change[0])
    report: dict[str, Any] = {
        "verdict": "DRY_RUN" if dry_run else "PASS",
        "changed_files": [str(path.relative_to(home).as_posix()) for path in changed_targets],
        "backup_dir": None,
    }
    if dry_run or not changed_targets:
        return report

    backup_dir = _backup_dir(home)
    backups: list[dict[str, str]] = []
    try:
        backup_dir.mkdir(parents=True, exist_ok=False)
        for target in changed_targets:
            if target.is_file():
                backup_target = backup_dir / target.relative_to(home)
                _copy_backup(target, backup_target)
                backups.append(
                    {
                        "path": target.relative_to(home).as_posix(),
                        "backup": backup_target.relative_to(backup_dir).as_posix(),
                        "sha256": _sha256_file(target),
                    }
                )

        def check_config_unchanged() -> None:
            if config_change is not None:
                path, before, _, _ = config_change
                current = path.read_bytes() if path.exists() else b""
                if current != before:
                    raise PolicyError("config.toml changed during installation; preserve it and rerun")

        check_config_unchanged()
        for _, target, data, _ in entries:
            _atomic_write(target, data)
        if config_change is not None:
            check_config_unchanged()
            _atomic_write(config_change[0], config_change[2])

        payload = _manifest(home, backup_dir, entries, config_change, backups, "complete")
        _atomic_write(backup_dir / "manifest.json", json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        report["backup_dir"] = str(backup_dir)
        report["manifest"] = str(backup_dir / "manifest.json")
        return report
    except BaseException as exc:
        # A partial manifest records the failure and hashes of any files that
        # were successfully replaced.  It is best-effort and never masks the
        # original exception.
        try:
            payload = _manifest(home, backup_dir, entries, config_change, backups, "partial_failure", str(exc))
            _atomic_write(backup_dir / "manifest.json", json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n")
        except BaseException:
            pass
        raise PolicyError(f"partial installation; backup={backup_dir}: {exc}") from exc


def verify(
    codex_home: Path | str | None = None,
    *,
    source_root: Path | str | None = None,
    require_context_management: bool = False,
) -> dict[str, Any]:
    """Verify installed hashes, profile invariants, and base config pins."""

    home = Path(codex_home or os.environ.get("CODEX_HOME") or (Path.home() / ".codex")).expanduser().resolve()
    root = Path(source_root).resolve() if source_root is not None else Path(__file__).resolve().parents[1]
    entries = _validate_source_tree(root)
    verified: list[str] = []
    for source, target_rel, kind, data, parsed in entries:
        target = home / target_rel
        if not target.is_file():
            raise PolicyError(f"missing installed file: {target}")
        if target.read_bytes() != data:
            raise PolicyError(f"hash/content mismatch: {target}")
        if kind in {"profile", "role"}:
            expected = (_PROFILE_MODELS if kind == "profile" else _ROLE_MODELS)[Path(source).name]
            marker = "ASTRA_ROOT" if expected == ASTRA_MODEL else ("LUNA_WORKER" if kind == "role" else "LUNA_ROOT")
            expected_reasoning = (
                LUNA_REASONING
                if kind == "role"
                else _PROFILE_REASONING[Path(source).name]
            )
            _validate_profile(
                _toml_bytes(target),
                target,
                expected,
                role=kind == "role",
                marker=marker,
                expected_reasoning=expected_reasoning,
            )
        verified.append(target.relative_to(home).as_posix())

    config_path = home / "config.toml"
    if not config_path.is_file():
        raise PolicyError(f"missing installed base config: {config_path}")
    config_data = _toml_bytes(config_path)
    for path, expected in _MANAGED_CONFIG_PATHS.items():
        if _get_path(config_data, path) != expected:
            raise PolicyError(f"{config_path} {'.'.join(path)} must be {expected!r}")
    _config_file_has_legacy_agent_pins(config_data, config_path)
    verified.append("config.toml")
    context_enabled = _get_path(config_data, _CONTEXT_PATH) is True
    if require_context_management and not context_enabled:
        raise PolicyError(f"{config_path} features.context_management.experimental_mode must be true")
    return {"verdict": "PASS", "verified_files": verified, "context_management_enabled": context_enabled}


def _resolve_cli_home(value: str | None) -> Path:
    return Path(value or os.environ.get("CODEX_HOME") or (Path.home() / ".codex")).expanduser().resolve()


def _print_report(report: dict[str, Any]) -> None:
    print(f"VERDICT={report['verdict']}")
    for key in ("changed_files", "verified_files"):
        if key in report:
            print(f"{key}=" + json.dumps(report[key], separators=(",", ":")))
    if report.get("backup_dir"):
        print(f"backup_dir={report['backup_dir']}")
    if report.get("manifest"):
        print(f"manifest={report['manifest']}")
    if "context_management_enabled" in report:
        print(f"context_management_enabled={str(report['context_management_enabled']).lower()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", dest="global_codex_home", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install", help="install or dry-run the global policy")
    install_parser.add_argument("--codex-home", dest="codex_home", default=argparse.SUPPRESS)
    install_parser.add_argument("--dry-run", action="store_true")
    install_parser.add_argument("--enable-context-management", action="store_true")

    verify_parser = subparsers.add_parser("verify", help="verify installed policy and config invariants")
    verify_parser.add_argument("--codex-home", dest="codex_home", default=argparse.SUPPRESS)
    verify_parser.add_argument("--require-context-management", action="store_true")

    args = parser.parse_args(argv)
    home = _resolve_cli_home(getattr(args, "codex_home", None) if hasattr(args, "codex_home") else args.global_codex_home)
    try:
        if args.command == "install":
            report = install(
                home,
                dry_run=args.dry_run,
                enable_context_management=args.enable_context_management,
            )
        else:
            report = verify(home, require_context_management=args.require_context_management)
        _print_report(report)
        return 0
    except PolicyError as exc:
        print("VERDICT=FAIL")
        print(f"error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
