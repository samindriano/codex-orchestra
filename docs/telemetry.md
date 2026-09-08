# CODEX ORCHESTRA TELEMETRY V1.2

Telemetry is an optional, local-only JSONL ledger. It is outside the model
loop, launches no model worker, uses only loopback OTel export, and emits no
hook stdout.
The schema remains `orchestra_telemetry_v1` for append-only compatibility.

## Measurement hierarchy

The benchmark unit is one Codex turn, not a session:

```text
SESSION
  └── TURN (exact session_id + turn_id)
       └── SUBAGENT LIFECYCLE (same turn_id)
```

`SessionStart` and `SessionEnd` write context-only `session_observed` records
with `measurement_generation = SESSION_LEVEL_V1`. They never create or close a
benchmark run. `UserPromptSubmit` creates a `turn_start` record and `Stop`
creates its matching `turn_finalize`; `Interrupt` finalizes only the interrupted
turn. New turn records use `measurement_generation = TURN_LEVEL_V1_2`. A later
inspection turn in the same session therefore cannot be confused with the
substantive turn that preceded it.

Existing append-only V1 records are not rewritten. Legacy automatic
`codex-session` runs are classified analytically as `SESSION_LEVEL_V1` and are
excluded from default reports; use `--include-session-level` only for an
explicit compatibility view. Synthetic fixtures and approximate manual imports
remain separate.

## Stable global hook metadata

### Layer A: stable global hook metadata

The automatic hook path records only fields supplied by the hook contract:

- `session_id`, `turn_id`, `hook_event_name`, `cwd` (reduced to project
  metadata), `model`, lifecycle timestamps, interruption state, and subagent
  lifecycle fields;
- normalized project kind: `GIT`, `NON_GIT`, `NO_PROJECT`, or `UNKNOWN`, plus a
  path-free worktree label, repository label/id, and branch when local Git
  metadata supplies them;
- model names as open strings, including future model identifiers;
- worker lifecycle counts independent of token attribution.

`transcript_path` and `agent_transcript_path` may arrive in hook input, but the
collector never opens, parses, watches, hashes, stores, or uses either path.
The retired transcript parser is disabled. Codex documents the transcript
format as unstable for hooks; see the [official hooks documentation](https://learn.chatgpt.com/docs/hooks).

Profile, reasoning effort, and orchestra mode are not inferred from model names
or worker counts. They remain `UNKNOWN`/`NONE` unless a canonical launcher sends
the reserved explicit `orchestra_launcher` metadata object. Raw sessions use
`orchestra_mode = NOT_APPLICABLE`.

Fast mode is recorded separately as `orchestra.speed_mode` (`FAST`, `STANDARD`,
or `UNKNOWN`) with `orchestra.speed_mode_source`. The benchmark launchers pass a
versioned, process-scoped `orchestra_launcher_v1` contract through
`CODEX_ORCHESTRA_LAUNCHER_METADATA`; the contract contains only the explicit
speed mode, documented `-c` overrides, a normalized configuration hash, and
path-free launcher version/name. These records use
`speed_mode_source = LAUNCHER_EXPLICIT`. The collector does not inspect or infer
speed state from `/fast` commands, UI text, latency, model names, priority
wording, timestamps, or transcripts. Ordinary hooks without a launcher contract
remain `UNKNOWN` unless the separately documented exact Fast config is active.

For a fresh session, the collector additionally records `FAST` with source
`CODEX_CONFIG_EXPLICIT` only when the active `CODEX_HOME/config.toml` contains
both `service_tier = "fast"` and `[features].fast_mode = true`. Partial,
malformed, absent, or otherwise different configuration remains `UNKNOWN`.
Legacy turn records missing speed fields are normalized only while reading as
`UNKNOWN` with source `LEGACY_MISSING`; historical ledger rows are never
rewritten or backfilled.

### Reproducible benchmark launchers

The canonical installer places `codex-standard.cmd`, `codex-fast.cmd`, and their
small Python dispatch helper under `CODEX_HOME\launchers`. They invoke the
installed `codex` executable with invocation-scoped overrides:

| Entry point | Codex overrides | Telemetry speed source |
| --- | --- | --- |
| `codex-standard.cmd` | `-c service_tier="default"` | `LAUNCHER_EXPLICIT` |
| `codex-fast.cmd` | `-c service_tier="fast" -c features.fast_mode=true` | `LAUNCHER_EXPLICIT` |

The launchers reject user-supplied overrides for `service_tier` and
`features.fast_mode`, so the benchmark contract cannot be silently superseded.
User profile/model/effort arguments are forwarded unchanged. The process-scoped
metadata is not inherited by the caller after the Codex child exits, and the
normal `codex` command remains unchanged.

Certified FAST-vs-STANDARD analytics must use only
`speed_mode_source = LAUNCHER_EXPLICIT`. Use `report --speed-benchmark`; it
excludes `UNKNOWN`, legacy, config-only, and other non-launcher records from the
comparison while leaving those records available to ordinary descriptive reports.
Do not use `/fast on` or `/fast off` mid-session in a certified benchmark.

### Stable usage adapters

Usage is populated only by an explicitly correlated machine-readable source:

| Source | Status | Automatic by ordinary hooks |
| --- | --- | --- |
| `CODEX_EXEC_JSON` | Supported when exact `thread.started.thread_id` and, when requested, `turn_id` correlation succeeds | No |
| `ORCHESTRA_LAUNCHER` | Supported when the canonical launcher supplies the values | Only when supplied |
| `STABLE_RUNTIME_METADATA` | Reserved for a separately proven stable runtime field | No |
| `NATIVE_OTEL_TRACE` | Supported for canonical `session_task.turn` spans joined by exact `thread.id + turn.id` | Yes, when local OTel is configured |
| `MANUAL` | Separate user-supplied historical evidence | No |
| `NONE` | Safe unknown fallback | Yes, for ordinary interactive sessions |

The documented `codex exec --json` stream is JSONL and includes
`turn.completed.usage`; the adapter requires an explicit expected thread ID and
can require an exact turn ID. It never uses newest-file, timestamp,
latest-session, or directory-scanning correlation. See the [official
non-interactive mode documentation](https://learn.chatgpt.com/docs/non-interactive-mode).

### Native interactive usage

The installed local OTel configuration exports to loopback only, with
`log_user_prompt = false`. The receiver consumes only trace spans named
`session_task.turn` and allowlists `thread.id`, `turn.id`, and the canonical
`codex.turn.token_usage.*` attributes. It joins by exact `(thread.id, turn.id)`;
it never uses timestamps or SSE-event summation. A turn with multiple
`response.completed` events therefore contributes one aggregate span.

The receiver starts idempotently from the `SessionStart` hook and continues as a
small local process. If it is unavailable, malformed, missing identity, or
conflicting, Codex continues normally and the turn remains `UNKNOWN`. Pending
normalized spans are reconciled when the lifecycle record appears. Raw OTLP,
prompts, assistant text, tool contents, code, secrets, and full paths are not
persisted.

If no supported source is available, all usage values are null and
`usage_quality = UNKNOWN`. `UNKNOWN` is preferred to unstable inference.

Each usage-bearing record includes:

- `usage_source`: `CODEX_EXEC_JSON`, `ORCHESTRA_LAUNCHER`,
  `STABLE_RUNTIME_METADATA`, `NATIVE_OTEL_TRACE`, `MANUAL`, or `NONE`;
- `usage_quality`: `EXACT`, `PARTIAL`, or `UNKNOWN`;
- `source_capability`: `USAGE_SOURCE_SUPPORTED`, `USAGE_SOURCE_PARTIAL`,
  `USAGE_SOURCE_UNSTABLE`, or `USAGE_SOURCE_UNAVAILABLE`.

The canonical numeric fields are `input_tokens`, `cached_input_tokens`,
`cache_write_input_tokens`, `non_cached_input_tokens`, `output_tokens`,
`reasoning_output_tokens`, `reasoning_tokens`, and `total_tokens`. Missing
values remain null; they are never converted to zero.

## Root and worker attribution

Turn-scoped `SubagentStart`/`SubagentStop` pairs record worker identity, model,
status, and counts against the exact parent `turn_id`. When the lifecycle event
also supplies a native worker `(thread.id, turn.id)` pair, the receiver attaches
the separate native span to that worker. Root usage never includes worker
usage. `orchestra_total_tokens` is emitted only when root and every included
worker have exact, deterministic usage; otherwise it remains `UNKNOWN`.

## Privacy and overhead

The ledger never persists prompts, responses, tool arguments or outputs, source
contents, command output, secrets, environment dumps, transcript paths, or full
personal paths. Project classification is local and stores only normalized
metadata.

Every run records measurement fields fixed by the collector:

- additional model requests: `0`;
- telemetry workers launched: `0`;
- additional model-context tokens: `0`;
- local wall/CPU time and bytes read/written where available.

## Storage and fail-open behavior

The default ledger is `CODEX_HOME/orchestra-telemetry/ledger.jsonl`, or
`~/.codex/orchestra-telemetry/ledger.jsonl` when `CODEX_HOME` is unset. Writers
use a private directory, a persistent lock, full-ledger validation, fsync, and
atomic replacement. Corrupt ledgers block telemetry writes and reporting, but
the command hook still exits successfully so telemetry failure cannot become a
Codex task failure.

`CODEX_ORCHESTRA_TELEMETRY=0` (also `false`, `off`, `disabled`, or `no`) makes
the hook return without creating or changing the ledger.

## Commands

Create and finalize metadata without involving Codex:

```powershell
python scripts/orchestra_telemetry.py --store $store create `
  --task-label example --task-class CODE_CHANGE --complexity SMALL --mode DIRECT

python scripts/orchestra_telemetry.py --store $store finalize --run-id $run `
  --completed true --validation-status PASS
```

Ingest a documented `codex exec --json` output file only with its exact thread
identifier:

```powershell
python scripts/orchestra_telemetry.py --store $store ingest-exec-json `
  --run-id $run --source-file .\exec-output.jsonl --thread-id $threadId
```

For a turn-level non-interactive stream, also require its exact turn ID with
`--turn-id $turnId`. Reports default to turn-level records:

```powershell
python scripts/orchestra_telemetry.py --store $store report
python scripts/orchestra_telemetry.py --store $store report --include-session-level
```

`ingest-synthetic`, `snapshot`, `annotate`, and `import-manual` remain available.
Synthetic and approximate manual records stay separate from ordinary run
counts.

## Reporting

Reports are descriptive and offline. Unknown usage is never treated as zero.
Token medians include a sample-size field such as
`median_total_tokens_n`, plus `usage_qualified_runs` and `usage_total_runs`.
No routing recommendation or composite quality score is emitted.

## Installation boundary

The canonical installer copies the collector, benchmark launcher entry points,
and merged lifecycle hooks into an explicitly selected `CODEX_HOME`. Validate
installation in a temporary home first with install, verify, and a second-install
idempotence check. Do not install or trust hooks in a real home without explicit
user authorization.

## Validation

```powershell
python -m unittest discover -s tests -v
python -m py_compile scripts/orchestra_telemetry.py tests/test_orchestra_telemetry.py
python -m compileall -q scripts tests
git diff --check
```

The telemetry tests cover exact two-turn chronology in one session,
interruption/resume/compaction handling, concurrent session/turn isolation,
turn-linked workers with unknown worker usage, deterministic Git worktree
metadata, transcript non-opening, malicious/huge transcript isolation, stable
model capture, future model labels, unknown effort/profile, interactive unknown
usage, exact `codex exec --json` usage, malformed-source fallback, privacy,
reporting sample sizes, fail-open behavior, and telemetry-off behavior.
