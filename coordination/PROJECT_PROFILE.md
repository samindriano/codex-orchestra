# IDX Trade project profile

Only MAIN edits this file.

## Identity

- **Project ID:** `idx-trade-v0`
- **Project:** IDX daily/EOD trade-setup research
- **Primary repository:** `samindriano/idx-trade`
- **Authoritative source branch:** `research/idx-ranking-v2-spec-v1`
- **Source HEAD at sync:** `80d78a5bed812209639d8e5d07b44e908c3a1c57`
- **Authoritative status document:** `docs/CURRENT_STATUS.md`
- **Orchestra snapshot branch:** `orchestra/idx-trade`
- **Last orchestra sync:** `2026-08-11T06:27:00Z`
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
- Path Risk V1 PR-001: failed/closed;
- Path Risk V2 PR-002/PR-003: both viewed and closed as `PATH_RISK_V2_DISCOVERY_FAIL_CLOSE`;
- Path Risk V2 winner: none;
- Path Risk F5/F6: sealed / not needed after V2 fail-close;
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

Safe dimensions include implementation hardening, independent tests, leakage/PIT/provenance audit, runtime/cache inspection, frontend/backend contract work, and independent result review.

Do not parallelize later candidates whose specification depends on a current result, sealed-fold/outcome access, post-result rescue candidates, or reopening final alpha architecture without explicit authorization.

## Current execution frontier

Path Risk V2 is closed. The five-worker HEAVY hardening task and subsequent serialized F1-F4 evidence run are complete.

Current safe frontier:

1. preserve the final V3-B ranker and continue outcome-blind fresh-forward operation under the existing 100-session contract;
2. keep Path Risk inactive unless a genuinely new preregistered V3 family is explicitly authorized;
3. keep F5/F6, fresh-forward outcomes, calibration, risk integration, sizing, execution-PnL and paper/live blocked.

No automatic Path Risk PR-004 rescue task exists.

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
- Path Risk V2 PR-002/PR-003 fail-close verdict;
- Path Risk F5/F6 seal;
- fresh-forward 100-session H10-mature block after 2026-07-31;
- no forward realized-outcome access before the explicit one-shot boundary;
- no automatic calibration/risk-veto/reranking/sizing/execution promotion.

## Status synchronization contract

`codex-orchestra/orchestra/idx-trade` is a snapshot, not a live mirror. On every material source phase transition, final-model change, gate change, or meaningful source-HEAD milestone, MAIN refreshes `PROJECT_PROFILE.md`, `TEAM_STATUS.md`, `TASK_REGISTRY.md`, and appends `DECISIONS.md` when needed.
