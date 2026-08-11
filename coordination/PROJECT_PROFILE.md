# IDX Trade project profile

Only MAIN edits this file.

## Identity

- **Project ID:** `idx-trade-v0`
- **Project:** IDX daily/EOD trade-setup research
- **Primary repository:** `samindriano/idx-trade`
- **Authoritative source branch:** `research/idx-ranking-v2-spec-v1`
- **Source HEAD at sync:** `477b4411c8c294e9ca5012a3079248033de5641c`
- **Authoritative status document:** `docs/CURRENT_STATUS.md`
- **Orchestra snapshot branch:** `orchestra/idx-trade`
- **Last orchestra sync:** `2026-08-11T04:58:00Z`
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
- Path Risk V2 PR-002/PR-003: frozen + implemented, real development outcomes not yet viewed;
- Path Risk F5/F6: sealed;
- post-2026-07-31 fresh-forward outcomes: locked/unaccessed.

Calibration, alpha+risk integration, execution-PnL, Kelly, paper trading, and live trading are not automatically authorized.

## Optimization objective

The orchestra is optimized to reduce wall-clock time with Luna xhigh concurrency while retaining frozen research gates.

- **Primary orchestration objective:** `LATENCY_FIRST_WITH_FROZEN_RESEARCH_GATES`
- **Default meaningful-task topology:** `LIGHT`
- **LIGHT target:** MAIN + 1–3 Luna xhigh workers when 2–3 useful scopes are immediately runnable
- **HEAVY target:** MAIN + 3–6 Luna xhigh workers when at least three independent critical-path scopes exist
- **DIRECT:** reserved for small/inherently sequential work; substantial DIRECT requires an explicit latency rationale
- **Nested workers:** prohibited
- **Spawn-before-work:** enabled
- **MAIN hoarding of independent critical-path work:** prohibited

## Model routing

- **Codex MAIN/root default:** `Luna xhigh`
- **Codex worker default:** `Luna xhigh`
- **Escalation model:** `Sol High`
- **Sol use:** bounded checkpoint only for unresolved architecture conflicts, repeated Luna integration failure, decision-changing methodology audit, suspiciously strong research results, or final high-risk gates
- **Persistent Sol root:** not default
- **External research/audit lead:** ChatGPT may design methodology, inspect GitHub, and provide explicit written specs; Codex independently verifies repository state before edits/runs

## Parallelism policy

Parallelize orthogonal implementation/audit work inside the current frozen experiment. Keep decision-dependent scientific learning sequential.

Safe dimensions include:

- implementation hardening;
- independent regression/adversarial tests;
- leakage/PIT/provenance audit;
- runtime/cache/performance inspection;
- backend/API/frontend contract inspection;
- independent result validation/review;
- independent root-cause investigations.

Do not parallelize:

- later candidates whose specification depends on a current result;
- sealed-fold/outcome access;
- F5/F6 winner selection during F1-F4 discovery;
- post-result rescue candidates;
- reopening final alpha architecture without new explicit authorization.

## Current execution frontier

The active task is a **HEAVY five-way Path Risk V2 pre-outcome hardening pass**.

Run concurrently:

1. W1 — PR-002 stop-touch classifier contract;
2. W2 — PR-003 competing-risk/CIF contract;
3. W3 — fold-specific alpha-only comparator leakage contract;
4. W4 — runner/provenance/F1-F4 boundary contract;
5. W5 — frozen gate/selection/spec consistency.

Each worker owns a separate new test file and its own handoff. Workers do not edit shared production code. MAIN integrates after all five return and centrally patches any proven implementation-to-spec defect.

The one real PR-002/PR-003 F1-F4 evidence-producing run remains serialized and blocked until:

`PATH_RISK_V2_PARALLEL_HARDENING_PASS_READY_FOR_LOCAL_DISCOVERY`

followed by the final local import/full-suite/provenance preflight.

Root orchestra task:

`coordination/handoffs/IDX-PRV2-PARALLEL-HARDENING-ORCHESTRA.md`

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

`codex-orchestra/orchestra/idx-trade` is a snapshot, not a live mirror. On every material source phase transition, final-model change, gate change, or meaningful source-HEAD milestone, MAIN refreshes `PROJECT_PROFILE.md`, `TEAM_STATUS.md`, `TASK_REGISTRY.md`, and appends `DECISIONS.md` when needed.
