# CODEX ORCHESTRA TELEMETRY V1

Telemetry V1 is an optional, local-only metadata ledger. It is not part of the
model prompt, does not ask the root or a worker to report usage, and does not
launch a telemetry worker. The automatic path is a Codex lifecycle command hook:
`SessionStart` creates a run, `SubagentStart`/`SubagentStop` observe workers,
`Interrupt` records an interruption, and `SessionEnd` ingests the exact
transcript path and finalizes the run. Manual commands remain available for
legacy or explicitly controlled observations.

## Privacy and overhead contract

The collector stores explicit short labels and structural metadata only. It does
not persist prompts, responses, tool arguments, tool outputs, source contents,
secrets, environment values, transcript paths, or full project paths. Session
ingestion scans one explicit regular file, JSON-decodes only allowlisted
`token_usage_record` lines, and extracts only scalar model/effort metadata from
`turn_context` lines. Other JSONL records are skipped as bytes; their content is
not fed into a model or written to the ledger.

The normal measured-run target is:

- additional model requests: `0`;
- telemetry-specific worker launches: `0`;
- additional model-context tokens: `0`;
- local collector work: `NEGLIGIBLE_LOCAL_OVERHEAD`, measured with wall/CPU time
  and bytes read/written where available.

Every run carries `measurement_overhead_class`, `measurement_validity`,
`telemetry_model_requests_added`, `telemetry_tokens_added`,
`telemetry_worker_launches_added`, and `telemetry_context_tokens_added`. The
collector fixes the last four fields to zero; it has no option to claim model
work that it did not measure. If a future integration cannot preserve this
contract, the required verdict is `ORCHESTRA_TELEMETRY_V1_REWORK_REQUIRED`.

## Observed Codex source

The installed CLI was inspected locally as `codex-cli 0.153.1`. Rollout JSONL
contains `token_usage_record` events with these allowlisted fields:

```text
payload.session_id
payload.thread_id
payload.usage.*
payload.turn_token_usage.*
payload.thread_token_usage.*
```

The numeric usage fields are input, cached input, cache-write input, output,
reasoning output, and total tokens. The collector uses the latest
`thread_token_usage` per exact transcript and aggregates independent root/worker
observations. If no usage event is available, values remain `null`; they are
never changed to zero. Automatic root/worker attribution is
`ROOT_WORKER_USAGE_PARTIAL`: root and worker transcript paths are bound by
lifecycle-provided session IDs, but Codex does not expose a complete stable
profile/mode/worker inventory in one metadata record.

The hook input exposes the active model slug. Reasoning effort is recovered from
the allowlisted scalar `turn_context.effort` field. Profile name and orchestra
mode remain `UNKNOWN` unless a future Codex hook exposes them; model and effort
are open strings, so future model names require no schema change.

## Storage and record lifecycle

The default ledger is `CODEX_HOME/orchestra-telemetry/ledger.jsonl`, or
`~/.codex/orchestra-telemetry/ledger.jsonl` when `CODEX_HOME` is not set. The
directory is private where the platform supports permissions. A persistent lock
serializes writers; each append validates the complete existing ledger, writes a
new complete file in the same directory, fsyncs it, and atomically replaces the
ledger. A malformed, truncated, unknown-schema, unknown-field, or duplicate-ID
ledger blocks further writes and reporting.

The canonical codex-orchestra installer has one explicit telemetry mapping:

```text
scripts/orchestra_telemetry.py
    -> CODEX_HOME/scripts/orchestra_telemetry.py
config/hooks.json
    -> CODEX_HOME/hooks.json (merged with existing user hooks)
```

No other repository scripts are copied. Hook execution is still optional: Codex
requires a one-time review/trust decision for non-managed user hooks. The hook
checks `CODEX_ORCHESTRA_TELEMETRY`; values `0`, `false`, `off`, `disabled`, and
`no` make it return without creating or changing a ledger.

Records are append-only events folded into a run view:

- `run_start` — task label/class/complexity, explicit orchestra metadata, and
  unknown-safe initial fields;
- `usage_observed` — synthetic usage or allowlisted root/worker usage from an
  exact hook transcript path;
- `metadata_observed` — model, effort, project, and other allowlisted runtime
  metadata;
- `worker_observed` — exact lifecycle worker identity/model/effort when exposed;
- `interruption_observed` — a structured interruption marker without content;
- `run_finalize` — timing, exit/validation fields, and completion state;
- `allowance_snapshot` — explicit before/after subscription snapshots;
- `annotation` — reviewer/first-pass/rework and successor lineage;
- `legacy_manual_observation` — separate approximate historical evidence.

## Commands

The commands do not invoke `codex` or any model API. A minimal wrapper can create
metadata before a normal run and finalize after it:

```powershell
$codexHomeForTelemetry = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$store = Join-Path $codexHomeForTelemetry 'orchestra-telemetry'
$start = python scripts/orchestra_telemetry.py --store $store create `
  --task-label github-ci-remediation --task-class DEBUGGING --complexity MEDIUM `
  --mode DIRECT --root-model gpt-5.6-luna --root-reasoning-effort xhigh
$run = ($start | ConvertFrom-Json).run_id

# Run Codex normally here. No telemetry prompt or worker is added.

python scripts/orchestra_telemetry.py --store $store finalize --run-id $run `
  --session-file $env:CODEX_ROLLOUT_JSONL --completed true `
  --validation-status PASS --process-exit-status 0
python scripts/orchestra_telemetry.py --store $store report
```

The post-run source parser can also be called separately:

```powershell
python scripts/orchestra_telemetry.py --store $store ingest `
  --run-id $run --session-file $env:CODEX_ROLLOUT_JSONL
```

The automatic hook command is best-effort and fail-open. It emits no stdout,
never blocks a model request with a prompt, and swallows collector failures so a
corrupt ledger or unavailable transcript cannot break raw Codex usage. Exact
session/transcript correlation is required; a mismatched session ID is not
ingested. A terminal crash or forced process kill that emits no lifecycle hook
remains an explicit coverage blind spot.

For development, `ingest-synthetic` creates a fully deterministic usage event
without any session file or model call. `snapshot` records explicit allowance
before/after values. `annotate` records review and rework lineage. `import-manual`
is intentionally marked `APPROXIMATE_MANUAL` and is excluded from run counts.

Reporting is descriptive and offline. It groups by task class, mode, root model,
reasoning effort, and worker count, and reports completion, first-pass, rework,
medians, and allowance deltas only when denominators exist. It emits no routing
recommendation or composite quality score. Synthetic runs are explicitly marked
by `source_kind = SYNTHETIC_FIXTURE` and excluded from default reports; use
`report --include-synthetic` only for fixture inspection. Approximate manual
observations remain separate from both normal and synthetic run counts.

## Validation

Run the existing suite and the telemetry tests from the source worktree:

```powershell
python -m unittest discover -s tests -v
python -m py_compile scripts/orchestra_telemetry.py tests/test_orchestra_telemetry.py
git diff --check
```

Tests cover telemetry-off isolation, automatic lifecycle create/ingest/finalize,
future model strings, exact correlation, worker aggregation, interruption
retention, content non-persistence, unknown-safe missing usage, duplicate and
corruption handling, offline deterministic reporting, allowance/manual
separation, concurrent writes, hook merge/idempotence, and the absence of
model/network/worker runtime calls. Validate installation in an isolated
temporary `CODEX_HOME` before applying it to a real home.
