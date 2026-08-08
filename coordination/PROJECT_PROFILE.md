# IDX Trade project profile

Only MAIN edits this file.

## Identity

- **Project ID:** `idx-trade-v0`
- **Project:** IDX daily/EOD trade-setup research
- **Primary repository:** `samindriano/idx-trade`
- **Current source commit:** `3a7d7d4a47d9f69c9e285bf5c0b4292e392beed7`
- **Integration branch:** `main`
- **Operating mode:** `EXPLORATORY_RESEARCH_ONLY`
- **Initial venue:** IDX `REGULAR` market
- **Objective:** build an auditable point-in-time data foundation, then research a setup/opportunity scoring engine with calibrated outcome probabilities and risk metrics.

## Current phase boundary

Authorized now:

- official IDX identity/tradability/session source audit and ingestion;
- Yahoo daily/EOD research backfill with raw prices preserved;
- corporate-action and provider-gap verification;
- adversarial and full-universe DATA GATE work;
- code/tests/docs required to execute those gates.

Still blocked until DATA GATE passes and MAIN/user explicitly promotes the phase:

- support/resistance modelling;
- target/outcome model training or tuning;
- opportunity-score optimization;
- Kelly/Monte Carlo sizing as a live recommendation;
- paper/live trading or broker execution.

## Model routing

The user may override this at any time.

- **Codex root default:** `Luna xhigh`
- **Codex worker default:** `Luna xhigh`
- **Escalation model:** `Sol High`
- **Sol use:** bounded checkpoint only for unresolved architecture conflicts, repeated Luna integration failure, decision-changing methodology audit, suspiciously strong result, pre-model DATA GATE certification, or final pre-deployment review.
- **Persistent Sol root:** not default.
- **External research/audit lead:** ChatGPT thread may research methodology and audit GitHub state. Only explicit written specs/commits are transferable; Codex must verify repository state independently.

## Orchestration levels

- **DIRECT:** one bounded parser/test/doc/fix or narrow audit.
- **LIGHT (default for current phase):** implementation + independent tests/audit; usually 1-2 Luna workers.
- **HEAVY:** 3-6 workers only when actual backfill/reconciliation has multiple non-overlapping critical-path workstreams.
- **Nested workers:** prohibited.

## Current roles

| Role | Owned scope |
|---|---|
| RESEARCH / EXPERIMENT | methodology proposals and bounded research questions; no silent target/gate changes |
| VALIDATION | tests, point-in-time/leakage audit, official-session/snapshot reconciliation, gate integrity |
| DATA | IDX/Yahoo providers, security/tradability/session state, coverage, backfill, data gate, config data contracts |
| PRODUCTION | storage/provenance/package architecture and later simulator/runtime contracts |
| WEB | no active scope |

## DATA GATE sequence

1. official listing/delisting identity reference;
2. official IDX Exchange-Day calendar from Digital Statistics;
3. Regular-Market suspension/resumption reconstruction;
4. source-discovery completeness audit + official snapshot reconciliation;
5. raw Yahoo EOD backfill with revision conflicts surfaced;
6. corporate-action + raw-price semantic verification;
7. adversarial QA catalog gate;
8. full point-in-time universe gate;
9. freeze versioned data snapshot + provenance;
10. only then request promotion to setup/SR research.

## Known source constraint

The public IDX announcement page states that only three years of announcement data are available there; older historical data is directed to TICMI. Therefore free-only suspension/resumption completeness must not be claimed back to 2009 merely because Yahoo prices exist. Start with the cleanest auditable recent period; extend backward only with appropriate official/licensed evidence.

Outside an audited tradability coverage window, absence of an event is `UNKNOWN`, not `ACTIVE`.
A shorter clean research period is preferred to a longer guessed one.
