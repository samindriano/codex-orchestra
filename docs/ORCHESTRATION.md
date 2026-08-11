# IDX Trade orchestration

The parent/root thread is `MAIN`, the sole control plane and integrator. The authoritative project state lives in `samindriano/idx-trade`, especially `docs/CURRENT_STATUS.md`. This orchestra branch is a synchronized snapshot, not a live mirror.

## Operating objective

Minimize useful wall-clock time with **Luna xhigh parallelism** while preserving frozen research boundaries, point-in-time/leakage controls, sealed evidence, provenance, and integration safety.

## Operating loop

1. Verify the authoritative source repository, branch, HEAD, `docs/CURRENT_STATUS.md`, current checkout/worktree state, and relevant frozen specs/checkpoints.
2. If this orchestra snapshot does not match the source state, mark it stale and refresh before relying on it.
3. Freeze the decision-changing terms for the current milestone.
4. Build the execution frontier: everything useful that can start now without another unfinished result.
5. Remove overlapping ownership and scientifically dependent future work from that frontier.
6. Choose DIRECT/LIGHT/HEAVY from the width of the ready frontier, not from how difficult the task feels.
7. Spawn independent workers before MAIN begins those delegated scopes.
8. MAIN handles cross-cutting architecture, gate protection, coupling, integration prep, and a separate coupled path where useful.
9. Collect evidence/handoffs and verify actual diffs/tests/provenance.
10. Record the milestone verdict, update source project status, then refresh this orchestra snapshot when the source state materially changes.
11. De-escalate when dependencies make the next step sequential.

## Execution levels

| Level | Use when | IDX pattern |
|---|---|---|
| DIRECT | one small or inherently sequential ready path | MAIN works directly + proportional validation |
| LIGHT | 2–3 independent ready paths; default for meaningful work | MAIN + 1–3 Luna xhigh workers, launched early |
| HEAVY | 3–6 independent critical-path paths, broad separable work, uncertain root cause, or decision-changing review | MAIN + 3–6 Luna xhigh workers/reviewer with isolated ownership |

A substantial task may stay DIRECT only when MAIN records why worker startup/coordination would not materially shorten the critical path.

## Parallelism examples

Good LIGHT/HEAVY decomposition for IDX Trade:

- model/runtime implementation + independent regression tests + leakage/PIT audit;
- backend scorer integration + frontend/API contract inspection + validation coverage;
- cache/runtime performance audit + code implementation + provenance verification;
- multiple independent root-cause investigations when a local run fails;
- implementation + independent methodology/result review for one frozen experiment.

Do not parallelize:

- a later experiment whose specification should depend on the current result;
- sealed-fold/outcome access before authorization;
- overlapping writes to the same code paths;
- duplicated implementation without an explicit comparison purpose.

## Current research boundary

The source project has closed alpha architecture search and frozen:

- final ranker: `V3-B-STRUCTURE-LITE-V1-CANDIDATE-005`;
- model SHA-256: `1a702031113ff75f38158aa35d1c2bac477cd424d7f14b83d7a89e6c74fef0f6`;
- exact 33-feature order SHA-256: `100ff7a9bacf394b2adc1daa7eb73b0fe7b89613a6918a9e4ded60ca67a55e9e`.

Path Risk state:

- PR-001 / V1: failed and closed;
- PR-002/PR-003 / V2: frozen + implemented, discovery results not yet viewed;
- F5/F6: sealed.

Fresh-forward alpha state:

- first exact 100 consecutive H10-mature official signal sessions strictly after 2026-07-31 are reserved for the one-shot independent verdict;
- realized forward outcomes remain locked until the explicit outcome-access boundary.

No automatic calibration, risk-veto/reranking, sizing, execution-PnL, paper trading, or live trading promotion exists.

## Immediate execution frontier

The authoritative next step is:

1. current-checkout import/preflight verification;
2. full repository tests;
3. if preflight passes, exactly one PR-002/PR-003 F1-F4 development run;
4. result review against the frozen V2 gates;
5. no F5/F6 access yet.

The test/import verification and read-only spec/provenance audit may run concurrently when isolated. The single evidence-producing discovery run remains sequential after preflight because its result defines the next scientific decision.

## Model routing

- Default MAIN/root: `Luna xhigh`.
- Default workers: `Luna xhigh`.
- `Sol High`: bounded decision-changing checkpoint only.
- HEAVY does not imply Sol.

Useful Sol cases: unresolved architecture conflict after bounded Luna attempts, repeated integration failure, methodology certification, suspicious result, or final high-risk promotion/release review.

## Worker contract

Every worker gets:

```text
repository/worktree:
base commit:
task id:
parallel group:
role:
question/task:
why this can run now:
owned files/scope:
prohibited changes:
dependencies/assumptions:
deliverable:
validation required:
integration contract:
handoff path:
stopping condition:
```

Workers do not spawn workers. Concurrent writers do not share ownership.

## Snapshot sync

At every material source milestone, final-model/gate change, or meaningful source-HEAD transition, refresh at least:

- `coordination/PROJECT_PROFILE.md`;
- `coordination/TEAM_STATUS.md`;
- `coordination/TASK_REGISTRY.md`;
- material entries in `coordination/DECISIONS.md`.

If source and orchestra disagree, source wins.
