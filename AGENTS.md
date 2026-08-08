# IDX Trade working agreement

## Repository-wide principles

This project is **EXPLORATORY_RESEARCH_ONLY**. It is not investment advice and
must not silently become a live trading system.

The current authorized phase is the IDX **DATA GATE**: point-in-time identity,
Regular-Market tradability reconstruction, raw EOD backfill, corporate-action
verification, provider-gap classification, adversarial QA, full-universe
coverage, and reproducibility/provenance work required to certify a research
period.

Model/SR/probability/Kelly work remains blocked until the DATA GATE passes and
MAIN/user explicitly promotes the phase.

Non-negotiable rules:

- Do not fabricate market data, exchange state, performance, scores, or model state.
- Do not infer `SUSPENDED`, `NO_TRADE`, or `DATA_MISSING` from an absent Yahoo/provider row.
- Outside an audited tradability coverage window, missing suspension evidence resolves to `UNKNOWN`, not `ACTIVE`.
- Keep listing existence, market-specific tradability, and provider availability separate.
- Keep raw OHLC execution prices separate from adjusted/vendor information.
- Historical delisted securities remain eligible historically before their effective delisting date.
- Current survivors must never be backfilled into historical universes.
- Preserve unrelated user changes and existing IDX data contracts/tests.
- Never commit credentials, runtime market data, model artifacts, caches, or user-specific local paths.
- Each worker edits only its owned scope. Cross-ownership changes require a written handoff and MAIN integration.

## Sources and lineage

Primary implementation source of truth:

- `samindriano/idx-trade`
- audited orchestration source commit: `1ebfe62545993a3cd578127594216479f1730468`

`market-movement-analyzer-eventrank-v0` is read-only legacy reference material.
Do not migrate legacy weights, runtime datasets, predictions, ledgers, old
BULLISH/BEARISH/NEUTRAL semantics, overloaded confidence fields, or old
portfolio backtest logic without an explicit audit.

US-stock and Biohub repositories may be consulted for orchestration patterns
only. Do not copy their domain assumptions into IDX research.

## IDX Trade identity

- Project ID: `idx-trade-v0`
- Market: Indonesia Stock Exchange listed equities
- Initial execution venue: `REGULAR`
- Timeframe: daily/EOD
- Universe: point-in-time and dynamic
- Output direction: setup/opportunity score plus separate calibrated outcome probability and risk metrics; exact modelling semantics remain unfrozen
- Operating mode: `EXPLORATORY_RESEARCH_ONLY`

Current data-gate order:

1. listing/delisting identity;
2. suspension/resumption reconstruction;
3. source-discovery completeness + official snapshot reconciliation;
4. raw Yahoo EOD backfill;
5. corporate-action/raw-price semantic verification;
6. adversarial QA gate;
7. full point-in-time universe gate;
8. freeze data/provenance snapshot;
9. request promotion to setup/SR research.

A shorter clean historical period is preferred to a longer period with guessed states.

## Control plane and ownership

MAIN is the sole decomposer, integrator, and phase-transition authority. Only
MAIN edits shared coordination files.

| Role | Owned scope |
|---|---|
| RESEARCH / EXPERIMENT | bounded methodology proposals, source-reuse audit, future target/baseline proposals |
| VALIDATION | tests, point-in-time/leakage audit, snapshot reconciliation, data-gate integrity, adversarial checks |
| DATA | `src/idx_trade/providers/`, security/tradability state, universe/coverage/backfill/data-gate logic, related config data contracts |
| PRODUCTION | storage/provenance/package architecture and later simulator/runtime contracts |
| WEB | no active scope unless separately authorized |

Workers never spawn workers. Read-only workers may inspect the canonical
checkout; concurrent writers require isolated worktrees or provably disjoint
ownership. Workers never merge or push their own integration.

## Orchestration levels

Use the lightest reliable level:

- `DIRECT`: one tightly bounded parser/test/doc/fix or narrow audit.
- `LIGHT`: default for the current phase; usually one or two independent Luna workers such as implementation + tests/audit.
- `HEAVY`: three to six workers only when actual backfill/reconciliation has genuinely parallel, non-overlapping critical-path workstreams.

Do not keep HEAVY alive for maintenance or because workers are available.

## Model routing

The user may override this at any time.

- persistent Codex root default: **Luna xhigh**;
- normal worker default: **Luna xhigh**;
- **Sol High** is a bounded escalation model, not the persistent root by default.

Escalate to Sol High only for a specific decision-changing checkpoint, such as:

- unresolved architecture conflict after bounded Luna attempts;
- repeated integration/debugging failure;
- pre-model DATA GATE certification;
- suspiciously strong research result requiring adversarial review;
- final pre-deployment/live-money review.

After the checkpoint, return to Luna unless the user explicitly changes policy.
Workers never self-upgrade models.

An external ChatGPT research/audit thread may provide methodology research,
GitHub audits, and written specifications. Only explicit specs, artifacts,
commits, or user instructions transfer between chats; Codex must independently
verify repository state before edits.

## Task and research discipline

Every worker prompt states the exact repository/worktree, base commit, one
question, owned scope, prohibited changes, deliverable, required validation,
handoff path, and stop condition.

For research work preserve:

`hypothesis -> bounded audit/experiment -> compare -> prune -> validate -> integrate`

Do not introduce post-holdout tuning, new sources, relaxed data gates, or a new
target simply to rescue a failed result. `UNKNOWN` remains blocking when it can
change research validity.

Every task concludes with `coordination/handoffs/<task-id>-<role>.md`:

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

A handoff is evidence, not permission for the next phase.

## Git safety

- Verify exact repo root, branch, HEAD, and worktree state before edits.
- Preserve unrelated user changes; no hard reset, clean, force push, rebase, or history rewrite unless explicitly authorized.
- MAIN integrates only after checking scope, diff, tests/validation, and provenance.
- Runtime market data, credentials, generated models, and local caches stay out of Git.
