# IDX Trade project profile

Only MAIN edits this file.

## Identity

- **Project ID:** `idx-trade-v0`
- **Project:** IDX daily/EOD trade-setup research
- **Primary repository:** `samindriano/idx-trade`
- **Authoritative source branch:** `research/idx-ranking-v2-spec-v1`
- **Source HEAD at sync:** `cbecbe3993e1c2adb0dab660b687e316b14a69c4`
- **Authoritative status document:** `docs/CURRENT_STATUS.md`
- **Orchestra snapshot branch:** `orchestra/idx-trade`
- **Last orchestra sync:** `2026-08-11T04:46:00Z`
- **Snapshot freshness:** `CURRENT_AT_SOURCE_HEAD_ABOVE`
- **Operating mode:** `EXPLORATORY_RESEARCH_ONLY`
- **Initial venue:** IDX `REGULAR` market

If this snapshot conflicts with `samindriano/idx-trade` or its `docs/CURRENT_STATUS.md`, the source repository wins and this snapshot becomes `STALE` until refreshed.

## Current research state

Alpha architecture search is closed.

- final historical-development ranker: `V3-B-STRUCTURE-LITE-V1-CANDIDATE-005`;
- final V3-B refit: frozen successfully;
- final model SHA-256: `1a702031113ff75f38158aa35d1c2bac477cd424d7f14b83d7a89e6c74fef0f6`;
- exact 33-feature order SHA-256: `100ff7a9bacf394b2adc1daa7eb73b0fe7b89613a6918a9e4ded60ca67a55e9e`;
- V3-A Recency: failed/closed;
- V3-B Structure-Lite: final survivor;
- V3-C Regime: failed/closed;
- V3-D Sector Relative: PIT-data blocked/parked;
- V3-E true ranking/LambdaMART path: failed/closed;
- V4-A Participation: no survivor;
- V4-B Price Path: no survivor;
- V4-C Cross-Sectional Context: no survivor;
- Path Risk V1 PR-001: failed/closed and may not be rescued;
- Path Risk V2 PR-002/PR-003: frozen + implemented, development outcomes not yet viewed;
- Path Risk F5/F6: sealed;
- post-2026-07-31 fresh-forward outcomes: locked/unaccessed.

Calibration, alpha+risk integration, execution-PnL, Kelly, paper trading, and live trading are not automatically authorized.

## Optimization objective

The user is using the orchestra primarily to **reduce wall-clock time with Luna xhigh concurrency** while retaining research integrity.

- **Primary orchestration objective:** `LATENCY_FIRST_WITH_FROZEN_RESEARCH_GATES`
- **Default meaningful-task topology:** `LIGHT`
- **LIGHT target:** MAIN + 1–3 Luna xhigh workers when 2–3 useful scopes are immediately runnable
- **HEAVY target:** MAIN + 3–6 Luna xhigh workers when at least three independent critical-path scopes exist
- **DIRECT:** reserved for small/inherently sequential work; substantial DIRECT requires an explicit latency rationale
- **Nested workers:** prohibited
- **Spawn-before-work:** enabled
- **MAIN hoarding of independent critical-path work:** prohibited

## Model routing

The user may override this at any time.

- **Codex MAIN/root default:** `Luna xhigh`
- **Codex worker default:** `Luna xhigh`
- **Escalation model:** `Sol High`
- **Sol use:** bounded checkpoint only for unresolved architecture conflicts, repeated Luna integration failure, decision-changing methodology audit, suspiciously strong research results, or final high-risk gates
- **Persistent Sol root:** not default
- **External research/audit lead:** ChatGPT may design methodology, inspect GitHub, and provide explicit written specs; Codex must verify repository state independently before edits/runs

Model strength and concurrency are separate. Use safe Luna parallelism to reduce latency; do not replace useful concurrency with a persistent premium root.

## Parallelism policy

Before meaningful work MAIN identifies the execution frontier: everything that can start now without waiting on another result.

### Safe parallel dimensions

When ownership is disjoint, these should usually be parallelized:

- implementation of the current frozen design;
- independent regression-test work;
- leakage/PIT/provenance audit;
- runtime/cache/performance inspection;
- backend/API/frontend contract inspection;
- independent result validation/review;
- alternative root-cause investigations during debugging.

### Must remain sequential

Do not parallelize decision-dependent scientific steps merely for speed:

- do not launch a later candidate whose specification should depend on the current experiment result;
- do not inspect sealed folds/outcomes early;
- do not choose a winner using F5/F6 during F1-F4 discovery;
- do not reopen V3/V4 alpha architecture after the final freeze without an explicit new research authorization;
- do not create post-result rescue candidates after a frozen candidate fails.

Parallelize the engineering/audit work **inside** the current frozen experiment; keep dependent scientific learning sequential.

## Current execution frontier

Immediate authoritative next action from the source project:

1. verify the current checkout/import resolution and run the full repository test suite;
2. if that passes, execute exactly one Path Risk V2 PR-002/PR-003 F1-F4 development run from the frozen handoff;
3. return the result without touching F5/F6.

The final evidence-producing PR-002/PR-003 run is intentionally serialized after preflight because it is the one frozen development execution. Supporting read-only inspection/test diagnosis may run in parallel if it does not duplicate or contaminate the run.

## Current roles

| Role | Typical ownership |
|---|---|
| RESEARCH / EXPERIMENT | bounded hypotheses/specification work and experiment interpretation; no silent target/gate changes |
| VALIDATION | tests, leakage/PIT audit, evaluation integrity, sealed-fold/outcome controls, independent result review |
| DATA | source/provenance, point-in-time universe/data contracts, coverage and data-readiness constraints |
| PRODUCTION | package/runtime architecture, artifact contracts, scoring/runtime integration |
| WEB | monitoring frontend/API work when explicitly scoped; must not expose locked outcomes |

MAIN owns integration, shared coordination state, final phase decisions, and the right to open sealed evidence.

## Frozen decision-changing boundaries

- final alpha model identity and exact 33-feature order;
- historical folds/holdouts already consumed or sealed;
- Path Risk V1 closed verdict;
- Path Risk V2 PR-002/PR-003 candidate definitions and F1-F4-only discovery boundary;
- Path Risk F5/F6 seal;
- fresh-forward 100-session H10-mature block after 2026-07-31;
- no forward realized-outcome access before the explicit one-shot boundary;
- no automatic calibration/risk-veto/reranking/sizing/execution promotion.

## Status synchronization contract

`codex-orchestra/orchestra/idx-trade` is a snapshot, not a live mirror. On every material source phase transition, final-model change, gate change, or meaningful source-HEAD milestone, MAIN should refresh:

- `coordination/PROJECT_PROFILE.md`;
- `coordination/TEAM_STATUS.md`;
- `coordination/TASK_REGISTRY.md`;
- append a material entry to `coordination/DECISIONS.md` when needed.

If that refresh does not happen, the orchestra branch can become stale even while the source project continues correctly.
