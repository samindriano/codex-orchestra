# CODEX ORCHESTRA TELEMETRY V1.1

Telemetry is an optional, local-only JSONL ledger. It is outside the model
loop, launches no worker, makes no network request, and emits no hook stdout.
The schema remains `orchestra_telemetry_v1` for append-only compatibility.

## Two explicit layers

### Layer A: stable global hook metadata

The automatic hook path records only fields supplied by the hook contract:

- `session_id`, `hook_event_name`, `cwd` (reduced to project metadata), `model`,
  lifecycle timestamps, interruption state, and subagent lifecycle fields;
- normalized project kind: `GIT`, `NON_GIT`, `NO_PROJECT`, or `UNKNOWN`;
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

### Layer B: stable usage adapters

Usage is populated only by an explicitly correlated machine-readable source:

| Source | Status | Automatic by ordinary hooks |
| --- | --- | --- |
| `CODEX_EXEC_JSON` | Supported when exact `thread.started.thread_id` correlation succeeds | No |
| `ORCHESTRA_LAUNCHER` | Supported when the canonical launcher supplies the values | Only when supplied |
| `STABLE_RUNTIME_METADATA` | Reserved for a separately proven stable runtime field | No |
| `MANUAL` | Separate user-supplied historical evidence | No |
| `NONE` | Safe unknown fallback | Yes, for ordinary interactive sessions |

The documented `codex exec --json` stream is JSONL and includes
`turn.completed.usage`; the adapter requires an explicit expected thread ID and
never uses newest-file, timestamp, latest-session, or directory-scanning
correlation. See the [official non-interactive mode documentation](https://learn.chatgpt.com/docs/non-interactive-mode).

If no supported source is available, all usage values are null and
`usage_quality = UNKNOWN`. `UNKNOWN` is preferred to unstable inference.

Each usage-bearing record includes:

- `usage_source`: `CODEX_EXEC_JSON`, `ORCHESTRA_LAUNCHER`,
  `STABLE_RUNTIME_METADATA`, `MANUAL`, or `NONE`;
- `usage_quality`: `EXACT`, `PARTIAL`, or `UNKNOWN`;
- `source_capability`: `USAGE_SOURCE_SUPPORTED`, `USAGE_SOURCE_PARTIAL`,
  `USAGE_SOURCE_UNSTABLE`, or `USAGE_SOURCE_UNAVAILABLE`.

The canonical numeric fields are `input_tokens`, `cached_input_tokens`,
`output_tokens`, `reasoning_tokens`, and `total_tokens`. Missing values remain
null; they are never converted to zero.

## Root and worker attribution

`ROOT_WORKER_USAGE_PARTIAL` remains the honest automatic capability. A
`SubagentStart`/`SubagentStop` pair records worker identity, model, status, and
counts, but does not imply worker token usage. For example, three workers may
be started while worker token usage remains unknown.

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

`ingest-synthetic`, `snapshot`, `annotate`, and `import-manual` remain available.
Synthetic and approximate manual records stay separate from ordinary run
counts.

## Reporting

Reports are descriptive and offline. Unknown usage is never treated as zero.
Token medians include a sample-size field such as
`median_total_tokens_n`, plus `usage_qualified_runs` and `usage_total_runs`.
No routing recommendation or composite quality score is emitted.

## Installation boundary

The canonical installer copies only the collector and merged lifecycle hooks
into an explicitly selected `CODEX_HOME`. Validate installation in a temporary
home first with install, verify, and a second-install idempotence check. Do not
install or trust hooks in a real home without explicit user authorization.

## Validation

```powershell
python -m unittest discover -s tests -v
python -m py_compile scripts/orchestra_telemetry.py tests/test_orchestra_telemetry.py
python -m compileall -q scripts tests
git diff --check
```

The telemetry tests cover transcript non-opening, malicious/huge transcript
isolation, stable model capture, future model labels, unknown effort/profile,
interactive unknown usage, exact `codex exec --json` usage, malformed-source
fallback, concurrent correlation, root/worker attribution, privacy, reporting
sample sizes, fail-open behavior, and telemetry-off behavior.
