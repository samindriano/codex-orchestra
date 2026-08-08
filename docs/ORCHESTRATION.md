# IDX Trade orchestration

This repository uses the same control-plane pattern as the US Stock
orchestrator, with the content adapted to Indonesian Stock Exchange research.
The parent chat is MAIN: it decomposes work, protects scope, compares evidence,
integrates only verified results, and decides when to stop.

## Operating loop

1. Orient from `coordination/TEAM_STATUS.md`, the task registry, current Git
   root/branch/HEAD, and the existing IDX data contracts.
2. Freeze the decision-changing research terms: target, horizon, benchmark,
   prediction unit, point-in-time universe, sessions, purge/embargo, metrics,
   acceptance gates, and holdout policy.
3. Delegate only bounded, non-overlapping work. Every worker gets one question,
   one repository/worktree, explicit prohibitions, a deliverable, and a
   verification requirement.
4. Collect a written handoff in `coordination/handoffs/`.
5. Review evidence at the milestone. Record `GO`, `NO-GO`, or `BLOCKED` in the
   shared decision log with the exact reason.
6. Integrate only approved changes, run proportional validation, update shared
   status, and stop when the acceptance criteria are met.

## Execution levels

| Level | Use when | Coordination pattern |
|---|---|---|
| `DIRECT` | tightly bounded task | MAIN works sequentially with targeted validation |
| `LIGHT` | one or two independent audits | one or two bounded workers; MAIN synthesizes and verifies |
| `HEAVY` | high-risk or genuinely parallel research | three to six isolated workers, with milestone review before integration |

Do not use the level as a quota. The user selects the root model; the
orchestrator controls only delegation intensity. Workers do not spawn workers,
and concurrent writers never share a worktree or file ownership.

## IDX-specific readiness gate

The next phase remains blocked until the evidence covers, at minimum:

- point-in-time listing and delisting identity;
- Regular-Market tradability intervals, including suspension/resumption where
  known and explicit `UNKNOWN` where reconstruction is incomplete;
- provider availability separated from exchange state;
- expected-vs-observed IDX session coverage and internal gap checks;
- IPO warm-up and historical delisted-security handling;
- raw OHLC execution semantics and corporate-action provenance;
- frozen target, horizon, benchmark, universe, temporal split, purge/embargo,
  metrics, acceptance gate, and locked holdout;
- reproducible source, configuration, environment, and artifact manifests.

Missing evidence is not a passing default. `UNKNOWN` is not a negative label,
and a schema smoke or design document is not research readiness.
