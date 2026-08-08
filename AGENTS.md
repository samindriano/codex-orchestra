# IDX Trade V0 working agreement

## Repository-wide principles

This repository is **EXPLORATORY_RESEARCH_ONLY**. It is not investment advice
and must never produce an execution signal, `BUY`, `SELL`, `EXIT`, or a live
trading workflow. The existing repository contains an IDX data foundation, but
this orchestration layer does not authorize new market-data acquisition,
credential use, dataset materialization, model training, tuning, prediction,
monitoring, paper trading, or real trading. Those phases require a separate
written authorization and an approved gate.

- Do not fabricate market data, performance, rankings, scores, or model state.
- Do not silently substitute a provider, rewrite historical artifacts, or
  infer exchange state from missing provider rows.
- Unknown lineage, provenance, point-in-time identity, timing, entitlement, or
  session coverage fails closed.
- Keep raw OHLC execution prices separate from adjusted/vendor information.
- Preserve the existing IDX source, tests, configuration, and user changes.
- Never commit credentials, runtime data, model artifacts, or user-specific
  local paths.
- Each agent edits only its owned files. Cross-ownership changes require a
  written handoff and MAIN integration.

## Legacy source policy

`market-movement-analyzer-eventrank-v0` is read-only reference material for
auditing reusable engineering patterns. The legacy source must not be edited,
renamed, deleted from, or copied from a dirty worktree. Do not migrate legacy
weights, predictions, monitoring ledgers, runtime datasets, or old target
semantics without an explicit audit and approval.

The current `idx-trade` implementation is the source of truth for IDX-specific
contracts. A US Stock implementation may be consulted for orchestration
patterns only; do not copy US-specific market assumptions into this repository.

## IDX Trade identity

- Project ID: `idx-trade-v0`
- Market: Indonesia Stock Exchange listed equities
- Initial venue: `REGULAR` market
- Timeframe: daily/EOD
- Universe: point-in-time and dynamic; never backfill current survivors into
  historical dates
- Candidate prediction unit: `security x signal_date` (target semantics remain
  to be frozen)
- Candidate forward horizon: daily/EOD forward window (not frozen)
- Benchmark: not frozen; do not assume IHSG or another index without a written
  decision
- Output: research score/ranking candidate only
- Operating mode: `EXPLORATORY_RESEARCH_ONLY`

The IDX state model keeps listing existence, market-specific tradability, and
provider availability separate. `UNKNOWN` is a valid state and must not be
collapsed into `NO_TRADE`, `SUSPENDED`, or background data. Regular-Market
eligibility, suspension/resumption intervals, IPO warm-up, delisted history,
corporate-action provenance, and expected-vs-observed session coverage are
decision-changing controls.

Model work is prohibited until MAIN approves both a frozen research
specification and a fail-closed data-readiness gate.

## Ownership and coordination

MAIN alone integrates branches and may edit the root working agreement, shared
coordination state, frozen specification, migration record, and final decision
log. Only MAIN updates `coordination/TEAM_STATUS.md` and the task registry.

| Role | Owned scope |
|---|---|
| EXPERIMENT | `docs/` research questions, source-reuse audits, feature inventory, target and baseline proposals |
| VALIDATION | `tests/`, data-readiness and leakage audits, evaluation integrity, risk register, adversarial checks |
| DATA | `src/idx_trade/providers/`, `security_master.py`, `states.py`, `universe.py`, `coverage.py`, `data_gate.py`, and related `config/` contracts |
| PRODUCTION | `src/idx_trade/data.py`, `storage.py`, `provenance.py`, package/API architecture, artifact contracts, and CLI proposals |
| WEB | Future `apps/web` or demo-fixture work only after a separate source audit and MAIN approval; no active web scope exists today |

Agents work from isolated branches/worktrees for writers and never merge into
the integration branch. Read-only workers may inspect the named repository
without a worktree. Stop on source dirtiness, ownership conflict, missing
lineage, credential requirements, unauthorized network/data access, or an
instruction that would require fabricated output. Workers do not spawn nested
workers.

Every task concludes with
`coordination/handoffs/<task-id>-<agent>.md` using the repository handoff
contract. A handoff is evidence, not permission to begin the next phase.

## Orchestration levels

The parent chat is the control plane. Choose the lightest level that is still
reliable:

- `DIRECT`: sequential work in the parent chat for tightly bounded tasks.
- `LIGHT`: one or two bounded, non-overlapping workers for independent audits
  or reviews; MAIN synthesizes and verifies the result.
- `HEAVY`: three to six bounded workers only for genuinely open-ended,
  high-risk, or highly parallelizable work; use isolated worktrees for
  concurrent writers and a milestone review when the decision is material.

The user selects the root model. Do not hardcode or silently switch it. Every
worker prompt must state the exact repository/worktree, role/question, allowed
and prohibited changes, deliverable, verification, and dependency or handoff
condition.

For research work, preserve the sequence:

`hypothesis -> bounded audit/experiment -> compare -> prune -> validate -> integrate`

Do not introduce post-holdout tuning, new data, or a new target to rescue a
failed result. Report `GO` or `NO-GO`, exact evidence, the smallest safe next
action, and remaining blockers.

## Git and handoff safety

- Use an explicit absolute repository path or `git -C` and verify root,
  branch, and HEAD before edits.
- Preserve unrelated user changes; never use `reset --hard`, `clean`, force
  push, rebase, or history rewriting unless explicitly authorized.
- MAIN integrates worker branches after checking scope, diff, tests, and
  provenance. Workers do not merge or push.
- Runtime data, credentials, generated model artifacts, and local caches stay
  out of Git.

Required handoff shape:

```text
# Handoff
from:
to:
task_id:
model_used:
reasoning_level:
source_repository:
source_commit:
branch:
head_commit:
scope:
files_changed:
findings:
decisions_made:
decisions_needed:
blocking_risks:
validation_run:
recommended_next_action:
```
