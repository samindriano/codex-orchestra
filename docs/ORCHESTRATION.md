# Reusable orchestration guide

The parent/root thread is `MAIN`, the sole control plane and integrator. Project-specific rules live in `coordination/PROJECT_PROFILE.md` and in the target repository's source-of-truth contracts.

The operating objective is **minimum useful wall-clock time subject to correctness and frozen gates**.

## Operating loop

1. **Orient.** Verify authoritative project status, source repository, branch, HEAD, worktree state, relevant contracts, and whether any orchestra snapshot is stale.
2. **Freeze decision-changing terms.** Identify the source/data contract, objective, evaluation protocol, acceptance gate, holdout, runtime budget, or deployment/output contract that must not drift mid-evaluation.
3. **Build the execution frontier.** List workstreams that can start now without waiting on another unfinished result.
4. **Remove unsafe parallelism.** Eliminate overlapping ownership, duplicate work without a comparison purpose, and downstream research decisions that depend on current results.
5. **Choose topology.** DIRECT for one useful sequential path; LIGHT for normal meaningful work with 2–3 ready paths; HEAVY for a wider 3–6-path frontier or decision-changing independent review.
6. **Spawn first.** Launch ready workers before MAIN starts performing the same delegated work. MAIN retains cross-cutting architecture, coupling, synthesis, blocker resolution, and integration work.
7. **Execute concurrently.** Workers solve bounded non-overlapping questions and stop on dependency/ownership/frozen-term violations.
8. **Collect evidence.** Treat handoffs as evidence to verify, not automatic phase transitions.
9. **Milestone review.** MAIN compares results, resolves conflicts, and records ACCEPT/REWORK/REJECT/INCONCLUSIVE/BLOCKED or project-equivalent decisions.
10. **Integrate.** Check scope, diff, tests/validation, provenance, and unrelated user changes before integration.
11. **Refresh status.** Update source project status and, when applicable, refresh the project-specific orchestra snapshot against the exact source commit.
12. **De-escalate or stop.** Collapse HEAVY -> LIGHT -> DIRECT as dependencies narrow the frontier; stop when acceptance criteria are met or the premise is invalidated.

## Parallelism preflight

For every substantial task, MAIN should be able to state:

```text
execution frontier:
- <ready workstream A>
- <ready workstream B>
- <ready workstream C>

blocked/dependent work:
- <cannot start until X>

MAIN-retained work:
- <integration/cross-cutting/final judgment>

selected topology: DIRECT | LIGHT | HEAVY
DIRECT rationale if substantial: <why workers would not shorten critical path>
```

A large task is not automatically HEAVY. A modest task can be LIGHT if several independent scopes are immediately runnable.

## Level selection

| Level | Use when | Pattern |
|---|---|---|
| DIRECT | one small or inherently sequential useful path | MAIN works directly + targeted verification |
| LIGHT | 2–3 independent ready paths; default for meaningful work | MAIN + 1–3 bounded workers, launched concurrently |
| HEAVY | 3–6 independent critical-path paths, broad separable migration/research, uncertain root cause, or high-value independent review | isolated ownership + concurrent execution + milestone review |

### DIRECT is an exception for substantial work

A substantial task should not remain DIRECT merely because MAIN can complete all parts. DIRECT is justified when:

- one result gates all subsequent work;
- implementation and validation are too tightly coupled to separate safely;
- the task is too small for worker startup/coordination to repay itself;
- all plausible worker scopes would duplicate MAIN or overlap ownership.

### Promote to LIGHT when

- implementation and independent tests/review can proceed separately;
- backend and frontend/API contract work can progress independently;
- code inspection and source/research audit can run concurrently;
- a worker can investigate one root-cause hypothesis while MAIN or another worker investigates another;
- one worker can prepare validation/runtime infrastructure while another implements the current frozen design.

### Promote to HEAVY when

- at least three non-overlapping workstreams are genuinely on the current critical path;
- a migration has separable data/model/runtime/UI dimensions;
- root cause is broad enough that parallel investigations reduce uncertainty faster;
- independent adversarial review is decision-changing;
- a single context window would otherwise force serial rediscovery across unrelated scopes.

### Spawn-before-work rule

If MAIN decides a scope belongs to a worker, spawn it before MAIN begins that scope. Late delegation after MAIN has already done most of the work defeats the latency objective.

## MAIN's preferred work while workers run

MAIN should avoid duplicating worker scopes. High-value MAIN work during concurrency includes:

- resolving cross-scope architecture questions;
- reading source-of-truth contracts workers should not redefine;
- preparing integration points;
- checking dependencies and acceptance gates;
- reviewing finished handoffs as they arrive;
- handling a separate coupled workstream;
- preparing the next frontier without authorizing scientifically dependent work early.

## Model routing

Model selection is independent of orchestration level. HEAVY does not imply a more expensive root model.

Default philosophy when the user has not specified otherwise:

1. use the cost-efficient strong project default for persistent MAIN/root;
2. use the same class for routine workers;
3. buy speed with concurrency before buying persistent premium-model usage when the work is safely parallelizable;
4. escalate one bounded question/checkpoint to a stronger model only when its judgment is likely to change the decision;
5. return to the normal model after the checkpoint.

Good stronger-model escalation cases: unresolved architecture conflict, repeated integration failure, methodology certification, suspicious breakthrough, final high-risk release/promotion gate.

Poor escalation cases: routine test fixes, parser edits, file moves, standard refactors, mechanical integration, or simply having a large repository.

## Worker prompt contract

Every worker prompt should include:

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

Workers never spawn workers. Concurrent writers must not share ownership.

## Research integrity

For research projects preserve the scientific sequence:

`hypothesis -> frozen experiment -> evidence -> compare/prune -> next hypothesis`

The next scientific candidate should not launch early when its definition depends on the current result.

Inside one frozen experiment, however, parallelize orthogonal work aggressively when safe:

- implementation;
- leakage/PIT/data-lineage audit;
- independent tests/evaluation harness review;
- runtime/cache preparation;
- source/provenance review;
- adversarial validation.

Do not rescue a failed result by changing target, source data, holdout, folds, metric, threshold, or acceptance gate after inspecting the result unless MAIN explicitly records that the prior evaluation is invalidated.

Unknown or incomplete evidence remains UNKNOWN/BLOCKED rather than being silently coerced into passing state.

## Engineering integrity

- preserve unrelated user changes;
- verify exact source commit and branch before porting/reusing code;
- migrate tests/invariants with reusable code where possible;
- do not claim validation that was not actually run;
- keep credentials and runtime artifacts out of Git;
- prefer small reversible integrations over big-bang rewrites when validated infrastructure already exists.

## Status synchronization

Project-specific branches in `codex-orchestra` are snapshots unless another tool explicitly synchronizes them.

Each project profile should record:

- authoritative source repository;
- authoritative source branch;
- authoritative status document;
- last synchronized source commit;
- last synchronization time;
- snapshot freshness: `CURRENT` or `STALE`.

A source milestone, phase transition, controlling gate change, or material source-HEAD change should trigger a snapshot refresh. If source and orchestra disagree, source wins.

## Reporting format

For meaningful orchestration milestones, prefer:

1. selected level and execution frontier;
2. bottom line;
3. work launched in parallel and why;
4. work completed and evidence;
5. validation/results with interpretation;
6. decision/status;
7. blockers and uncertainty;
8. highest-value next action/frontier;
9. commits/files/tests and caveats.
