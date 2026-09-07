# CODEX ORCHESTRA TELEMETRY V1

Telemetry V1 is an optional, local-only metadata ledger. It is not part of the
model prompt, does not ask the root or a worker to report usage, and does not
launch a telemetry worker. Normal collection is deterministic Python executed
before/after a task or after a rollout has ended.

## Privacy and overhead contract

The collector stores explicit short labels and structural metadata only. It does
not persist prompts, responses, tool arguments, tool outputs, source contents,
secrets, environment values, or full paths. Session ingestion scans one explicit
regular file and JSON-decodes only allowlisted `token_usage_record` lines. Other
JSONL records are skipped as bytes; their content is not fed into a model or
written to the ledger.

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
`thread_token_usage` as the session total and counts observed usage events as a
machine-readable request count. If no usage event is available, values remain
`null`; they are never changed to zero. Root/worker attribution is only
`DECLARED` when the launcher supplies explicit metadata. Otherwise it remains
`UNKNOWN`.

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
```

No other repository scripts are copied. The collector remains optional and is
not imported by Codex startup.

Records are append-only events folded into a run view:

- `run_start` — task label/class/complexity, explicit orchestra metadata, and
  unknown-safe initial fields;
- `usage_observed` — synthetic usage or allowlisted post-run session usage;
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

No V1 command is on Codex's execution path. A future launcher must invoke
`create`/`finalize` best-effort and preserve the task's exit status; chaining a
telemetry command as a hard `&&` prerequisite would violate the fail-open
contract.

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

Tests cover telemetry-off isolation, zero-model synthetic collection, content
non-persistence, unknown-safe missing usage, duplicate and corruption handling,
offline deterministic reporting, allowance/manual separation, concurrent writes,
and the absence of model/network/worker runtime calls. Installation is not
changed by this feature; use an isolated temporary `CODEX_HOME` for any future
installer integration test.
