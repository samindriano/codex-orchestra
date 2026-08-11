# Codex Orchestra — IDX Trade

IDX-specific orchestration snapshot for `samindriano/idx-trade`.

- Source repository: `samindriano/idx-trade`
- Authoritative source branch: `research/idx-ranking-v2-spec-v1`
- Source HEAD at this sync: `477b4411c8c294e9ca5012a3079248033de5641c`
- Authoritative source status: `docs/CURRENT_STATUS.md`
- Snapshot branch: `orchestra/idx-trade`
- Last synchronized: `2026-08-11T04:46:00Z`
- Scope: orchestration/control-plane settings only
- Excluded: source code, tests, market data, generated models, caches, credentials, and runtime artifacts

## Current state

The old DATA-GATE snapshot was stale. The source project has advanced substantially:

- alpha architecture search is **closed**;
- final historical-development ranker is **V3-B Structure-Lite**;
- final V3-B refit is frozen;
- Path Risk V1 failed and is closed;
- Path Risk V2 PR-002/PR-003 are frozen + implemented but their F1-F4 development outcomes have not yet been viewed;
- Path Risk F5/F6 remain sealed;
- post-2026-07-31 fresh-forward realized outcomes remain locked.

See `coordination/PROJECT_PROFILE.md` and `coordination/TEAM_STATUS.md` for the synchronized details.

## Revised orchestration policy

This profile is now **parallel-first for latency**, not single-agent-first by habit.

- root: `Luna xhigh`
- normal workers: `Luna xhigh`
- meaningful task default: **LIGHT**
- LIGHT: MAIN + 1–3 workers when 2–3 useful independent scopes can start now
- HEAVY: MAIN + 3–6 workers when the critical-path frontier is genuinely wider
- DIRECT: small/inherently sequential work; substantial DIRECT requires an explicit reason that workers would not shorten the critical path
- `Sol High`: bounded escalation only for decision-changing ambiguity/high-risk gates

The key rule is: **MAIN must not keep independent critical-path work to itself merely because one Luna can eventually finish everything. Spawn useful parallel scopes before MAIN duplicates them.**

Research dependencies remain sequential. Do not parallelize a later scientific candidate whose design should depend on the current result; instead parallelize implementation, tests, leakage/PIT audit, runtime preparation, and independent validation around the current frozen experiment.

## Snapshot freshness

This branch is not a live mirror. It does not automatically update when `idx-trade` advances.

If this branch conflicts with the source repository, `samindriano/idx-trade` and its `docs/CURRENT_STATUS.md` are authoritative. The orchestra snapshot should be marked stale and refreshed at the next material milestone.
