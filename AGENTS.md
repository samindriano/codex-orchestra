# CrossRank-US V0 working agreement

## Repository-wide principles

This repository is **EXPLORATORY_RESEARCH_ONLY**. It is not investment advice
and must never produce an execution signal, `BUY`, `SELL`, `EXIT`, or a live
trading workflow. Do not download market data, request credentials, build a
dataset, train, tune, predict, monitor, paper trade, or real trade unless the
user separately authorizes that phase.

- Do not fabricate market data, performance, rankings, or model state.
- Do not silently substitute a data source or rewrite historical artifacts.
- Unknown lineage, provenance, timing, or entitlement fails closed.
- Never commit credentials, runtime data, model artifacts, or user-specific
  local paths.
- Each agent edits only its owned files. Cross-ownership changes require a
  written handoff and MAIN integration.

## Legacy source policy

The following repositories are read-only reference material:

- Python research: `market-movement-analyzer-eventrank-v0`
- Next.js frontend: `stock-anomaly-web`

Do not commit to, rename, delete from, or alter either source repository.
Never reuse trained IDX weights, the monitoring ledger, runtime datasets,
legacy predictions, or Model V1/V1.1 artifacts. Legacy assumptions must be
audited before any engineering pattern is reused.

## CrossRank-US identity

- Project ID: `crossrank-us-v0`
- Market: US listed common stocks
- Benchmark candidate: SPY
- Prediction unit: `security × signal_date`
- Horizon candidate: open T+1 through close T+5
- Output: ranking score only
- Operating mode: `EXPLORATORY_RESEARCH_ONLY`
- No data source is approved and no model has been trained.

Training is prohibited until MAIN approves both a frozen research specification
and a fail-closed data-readiness gate.

## Ownership and coordination

MAIN alone integrates branches and may edit root `AGENTS.md`, shared
coordination, the charter, frozen specification, migration record, and final
decision log.

| Role | Owned scope |
|---|---|
| EXPERIMENT | reuse audit, feature inventory, baseline design, target candidates |
| VALIDATION | risk register, data readiness, evaluation integrity, leakage audit |
| WEB | `apps/web`, frontend contracts, web migration docs, demo-fixture policy |
| PRODUCTION | `src/crossrank_us`, architecture, artifact contracts, CLI proposal; scaffold only after MAIN approval |

Agents work from isolated branches/worktrees, never merge into the integration
branch, and stop on source dirtiness, ownership conflict, missing lineage, or
an instruction that would require data, credentials, training, or fabricated
outputs. Only MAIN updates `coordination/TEAM_STATUS.md`.

Every task concludes with `coordination/handoffs/<task-id>-<agent>.md`:

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
