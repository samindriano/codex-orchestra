# Reusable orchestration guide

The parent/root thread is `MAIN`, the sole control plane and integrator. Project
specific rules live in `coordination/PROJECT_PROFILE.md` and in the target
repository's own source contracts.

## Operating loop

1. **Orient.** Verify project profile, repository root, branch, HEAD, worktree
   state, team status, task registry, and source-of-truth contracts.
2. **Freeze decision-changing terms.** Identify the data/source contract,
   objective, evaluation protocol, acceptance gate, holdout, runtime budget, or
   deployment/output contract that must not drift mid-evaluation.
3. **Choose level.** Use DIRECT, LIGHT, or HEAVY based on actual coordination
   need, not worker availability.
4. **Delegate bounded work.** One worker gets one question, explicit ownership,
   prohibited changes, deliverable, verification, and stopping condition.
5. **Collect handoffs.** Treat worker output as evidence to verify, not as an
   automatic phase transition.
6. **Milestone review.** MAIN compares evidence, resolves conflicts, and records
   ACCEPT/REWORK/REJECT/INCONCLUSIVE/BLOCKED or project-equivalent decisions.
7. **Integrate.** Check diff, tests/validation, provenance, and unrelated user
   changes before integration.
8. **Stop.** End orchestration when acceptance criteria are met or evidence says
   the premise is invalid.

## Level selection

| Level | Use when | Pattern |
|---|---|---|
| DIRECT | one bounded sequential task | MAIN works directly + targeted verification |
| LIGHT | 1-2 independent questions materially help | bounded workers, usually implementation+tests or audit+validation |
| HEAVY | 3-6 genuinely parallel high-risk/open-ended scopes | isolated ownership + milestone review before integration |

### Escalate DIRECT -> LIGHT when

- implementation and independent tests/review can proceed separately;
- two plausible approaches need independent evaluation;
- source/research audit can proceed independently from code inspection.

### Escalate LIGHT -> HEAVY when

- at least three non-overlapping workstreams are actually on the critical path;
- a major migration has separable data/model/runtime/UI dimensions;
- independent adversarial review is decision-changing;
- one worker cannot reasonably hold all relevant context without losing scope.

### De-escalate

Return to LIGHT/DIRECT after the milestone. Do not keep a HEAVY topology alive
for maintenance or trivial follow-ups.

## Model routing

Model selection is independent of orchestration level. HEAVY does not imply a
more expensive root model.

Default philosophy when the user has not specified otherwise:

1. use the cost-efficient strong project default for persistent MAIN/root;
2. use the same class for routine workers;
3. escalate one bounded question/checkpoint to a stronger model only when its
   judgment is likely to change the decision;
4. return to the normal model after the checkpoint.

Good escalation cases: unresolved architecture conflict, repeated integration
failure, methodology certification, suspicious breakthrough, final high-risk
release/promotion gate.

Poor escalation cases: routine test fixes, parser edits, file moves, standard
refactors, mechanical integration, or simply having a large repository.

## Worker prompt contract

Every worker prompt should include:

```text
repository/worktree:
base commit:
role:
question/task:
owned files/scope:
prohibited changes:
dependencies/assumptions:
deliverable:
validation required:
handoff path:
stopping condition:
```

Workers never spawn workers. Concurrent writers must not share ownership.

## Research integrity

For research projects, preserve:

`hypothesis -> bounded audit/experiment -> compare -> prune -> validate -> integrate`

Do not rescue a failed result by changing the target, source data, holdout,
folds, metric, threshold, or acceptance gate after inspecting the result unless
MAIN explicitly records that the previous evaluation is invalidated.

Unknown or incomplete evidence remains UNKNOWN/BLOCKED rather than being
silently coerced into a passing state.

## Engineering integrity

- preserve unrelated user changes;
- verify exact source commit and branch before porting/reusing code;
- migrate tests/invariants with reusable code where possible;
- do not claim validation that was not actually run;
- keep credentials and runtime artifacts out of Git;
- prefer small reversible integrations over big-bang rewrites when the old
  system contains reusable validated infrastructure.

## Reporting format

For meaningful orchestration milestones, prefer:

1. level: DIRECT/LIGHT/HEAVY;
2. bottom line;
3. work completed and evidence;
4. validation/results with interpretation;
5. decision/status;
6. blockers and uncertainty;
7. highest-value next action;
8. commits/files/tests and caveats.
