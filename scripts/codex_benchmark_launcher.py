#!/usr/bin/env python3
"""Launch an explicitly configured, reproducible Codex speed benchmark.

This wrapper owns only the documented per-invocation ``-c`` overrides and a
small process-scoped metadata contract inherited by Codex lifecycle hooks.  It
does not replace or alter the normal ``codex`` command, persistent config, or
profile selection.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Sequence


LAUNCHER_SCHEMA = "orchestra_launcher_v1"
LAUNCHER_VERSION = "1"
METADATA_ENV = "CODEX_ORCHESTRA_LAUNCHER_METADATA"

_CONFIG = {
    "standard": {
        "speed_mode": "STANDARD",
        "service_tier": "default",
        "config_overrides": ['service_tier="default"'],
        "codex_overrides": ['service_tier="default"'],
    },
    "fast": {
        "speed_mode": "FAST",
        "service_tier": "fast",
        "fast_mode": True,
        "config_overrides": ['features.fast_mode=true', 'service_tier="fast"'],
        "codex_overrides": ['service_tier="fast"', "features.fast_mode=true"],
    },
}
_BLOCKED_CONFIG_KEYS = {"service_tier", "features.fast_mode"}
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@+-]{0,79}$")


class LauncherError(RuntimeError):
    """The benchmark launcher cannot establish an immutable speed contract."""


def _config_hash(config: dict[str, object]) -> str:
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _explicit_profile(args: Sequence[str]) -> str | None:
    for index, argument in enumerate(args):
        if argument == "--profile" and index + 1 < len(args):
            candidate = args[index + 1]
        elif argument.startswith("--profile="):
            candidate = argument.split("=", 1)[1]
        else:
            continue
        return candidate if _SAFE_LABEL.fullmatch(candidate) else None
    return None


def launcher_metadata(mode: str, user_args: Sequence[str] = ()) -> dict[str, object]:
    """Return the path-free contract passed to the inherited hook environment."""

    try:
        config = _CONFIG[mode]
    except KeyError as exc:
        raise LauncherError(f"unsupported benchmark mode: {mode!r}") from exc
    metadata: dict[str, object] = {
        "schema": LAUNCHER_SCHEMA,
        "launcher_name": f"codex-{mode}",
        "launcher_version": LAUNCHER_VERSION,
        "speed_mode": config["speed_mode"],
        "speed_mode_source": "LAUNCHER_EXPLICIT",
        "service_tier": config["service_tier"],
        "config_overrides": list(config["config_overrides"]),
        "config_hash": _config_hash({"config_overrides": config["config_overrides"]}),
    }
    if "fast_mode" in config:
        metadata["fast_mode"] = config["fast_mode"]
    profile = _explicit_profile(user_args)
    if profile is not None:
        metadata["profile"] = profile
    return metadata


def _config_key(value: str) -> str | None:
    if "=" not in value:
        return None
    return value.split("=", 1)[0].strip()


def _reject_speed_overrides(args: Sequence[str]) -> None:
    """Fail closed if user arguments could change the benchmark speed tier."""

    index = 0
    while index < len(args):
        argument = args[index]
        value: str | None = None
        if argument in {"-c", "--config"}:
            if index + 1 < len(args):
                value = args[index + 1]
                index += 1
        elif argument.startswith("-c=") or argument.startswith("--config="):
            value = argument.split("=", 1)[1]
        if value is not None and _config_key(value) in _BLOCKED_CONFIG_KEYS:
            raise LauncherError(f"benchmark speed override is owned by the launcher: {_config_key(value)}")
        if argument in {"--enable", "--disable"} and index + 1 < len(args):
            feature = args[index + 1].split("=", 1)[0].strip()
            if feature == "fast_mode":
                raise LauncherError("benchmark fast_mode override is owned by the launcher")
            index += 1
        elif argument.startswith("--enable=") or argument.startswith("--disable="):
            feature = argument.split("=", 1)[1].split("=", 1)[0].strip()
            if feature == "fast_mode":
                raise LauncherError("benchmark fast_mode override is owned by the launcher")
        index += 1


def codex_argv(mode: str, user_args: Sequence[str], *, executable: str = "codex") -> list[str]:
    """Build the exact Codex command with launcher-owned config overrides."""

    if mode not in _CONFIG:
        raise LauncherError(f"unsupported benchmark mode: {mode!r}")
    _reject_speed_overrides(user_args)
    # CLI -c overrides are intentionally appended after user arguments so a
    # profile or other normal option cannot supersede the benchmark contract.
    overrides = [item for value in _CONFIG[mode]["codex_overrides"] for item in ("-c", value)]
    return [executable, *user_args, *overrides]


def run(mode: str, user_args: Sequence[str], *, executable: str | None = None) -> int:
    """Run Codex with inherited stdio and process-scoped launcher metadata."""

    command = executable or shutil.which("codex")
    if not command:
        raise LauncherError("codex executable was not found on PATH")
    environment = os.environ.copy()
    environment[METADATA_ENV] = json.dumps(
        launcher_metadata(mode, user_args),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    completed = subprocess.run(codex_argv(mode, user_args, executable=command), env=environment, check=False)
    return int(completed.returncode)


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values or values[0] not in _CONFIG:
        print("usage: codex_benchmark_launcher.py {standard|fast} [-- <codex arguments...>]", file=sys.stderr)
        return 2
    mode = values.pop(0)
    if values[:1] == ["--"]:
        values.pop(0)
    try:
        return run(mode, values)
    except LauncherError as exc:
        print(f"BENCHMARK_LAUNCHER_ERROR={exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
