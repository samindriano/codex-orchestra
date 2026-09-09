# Orchestra review snapshot

Captured: `2026-09-09T04:51:02Z` (point-in-time; the producing turn may still be `OPEN`).

## Current state

- Ledger integrity: **PASS** — `398` validated records, SHA-256 `39b56705dbe0c080a942e5e31bf8c02dba325b112d8ca7a5ac721908e2b9f9fa`.
- Turn coverage: `119` turns — `104` completed, `3` interrupted, `0` failed, `12` open.
- Exact usage: **33/119 (27.73%)**; exact total `125,343,090` tokens.
- Worker attribution: `0/119` turns have exact worker usage; deterministic orchestra total is `125,343,090` exact tokens across `33` exact turns.
- Speed benchmark: **not ready** — FAST certified `0`, STANDARD certified `0`.
- Receiver: **HEALTHY**; pending OTel lines `5`.

## Interpretation

- The ledger is structurally readable and the default dashboard view is turn-level; session-level and synthetic observations remain excluded.
- Native OTel provides an exact subset, but unknown usage is not zero and must not be extrapolated.
- Worker lifecycle observations do not yet provide exact worker token attribution in this snapshot.
- Model, reasoning effort, task class, and orchestra mode are not sufficiently populated for strong routing or quality conclusions.

## Exact-only aggregate

- Input `124,850,362`; cached input `120,716,800`; non-cached input `4,133,562`.
- Output `492,728`; reasoning `236,381`; total `125,343,090`.
- Aggregate cached/input ratio: `96.69%`.

## Review blockers / next evidence

1. Usage completeness: `86` turns lack exact usage; review native OTel join and pending-line drain.
2. Worker totals: worker exact count is `0`; do not claim full Orchestra token cost from root-only observations.
3. Lifecycle closure: `12` turns are open/unfinished in this snapshot; do not classify them as failed.
4. Benchmark readiness: no launcher-certified FAST/STANDARD cohort is present.

## Provenance and privacy

Implementation: `codex-orchestra-global` / `codex/orchestra-telemetry-snapshots` / `6d0f1644f4ca11890cb11a56987bdcafc74cfad0`; worktree clean: `True`.
This file is derived and path-free. It contains no prompts, responses, tool arguments/outputs, transcripts, raw ledger records, secrets, or cloud data.

Machine-readable companion: `orchestra-usage-latest.json`.
