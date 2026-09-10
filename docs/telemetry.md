# Exact worker telemetry

This repository contains a passive, local-only telemetry collector for
turn-level root and worker token usage. The collector stores normalized JSONL
records under the configured private telemetry directory. It never opens or
parses transcript paths and never stores prompts, tool inputs/outputs, or
assistant text.

## Identity contract

The `PostToolUse` hook is matched only for `spawn_agent` and `Agent`. It reads
only structured identity keys: `agent_id`, `child_agent_id`,
`receiver_thread_ids`, and `agents_states`. It records an exact parent
`(session_id, turn_id)` to child-agent edge and discards the response payload.

The validated native relation is:

`agent_id = OTel thread.id`

`SubagentStart/SubagentStop turn_id = OTel turn.id`

The lifecycle hook therefore supplies the native worker pair when the runtime
does not repeat it explicitly. OTel spans are attached only when exactly one
root or worker role matches. Ambiguous, malformed, missing, or conflicting
identity stays pending or UNKNOWN.

## Exact arithmetic

Root usage is aggregated only from `attribution_role=ROOT`; worker usage is
aggregated only from `attribution_role=WORKER` with a known worker ID. The
expected worker population is the deduplicated `worker_id` set from exact
`worker_edge_observed` records. A worker total is exact only when every
expected worker also has lifecycle observation and exact native OTel usage;
an orphan lifecycle or usage row cannot add a worker to the population, and an
edge without its lifecycle or usage keeps the worker total UNKNOWN. An omitted
worker count is never treated as proof of zero workers. The normal hook path
has no complete-set zero-worker attestation, so root-only turns remain UNKNOWN.
Zero workers are exact only with an explicit `actual_worker_count=0` and
`worker_presence_quality=EXACT` declaration.

The dashboard exposes three separate fields:

- `root_exact_total_tokens`
- `worker_exact_total_tokens`
- `orchestra_exact_total_tokens`

The last field is `root + worker` only when both sides and worker presence are
exact. It remains `UNKNOWN` rather than falling back to root tokens.

Native OTel deliveries are keyed by a normalized source digest. Duplicate
delivery does not increase totals; a conflicting second value makes the
affected role UNKNOWN. Spans arriving before lifecycle hooks remain in the
private pending file and are reconciled after the identity appears.

## Hook configuration

`config/hooks.json` is the source template. Replace the two Codex-home
placeholders when installing it. Hook commands are advisory and fail open so
telemetry cannot change a Codex request outcome.

## Validation

Run the telemetry tests with:

```text
python -m unittest discover -s tests -v
python -m py_compile scripts/orchestra_telemetry.py scripts/orchestra_dashboard.py
git diff --check
```
