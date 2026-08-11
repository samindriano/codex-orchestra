# Reusable Codex Orchestra working agreement

## Purpose

This repository is a reusable control plane for multi-agent research and engineering work. Project-specific facts belong in `coordination/PROJECT_PROFILE.md`; keep this file generic unless the orchestration protocol itself changes.

The optimization target is **wall-clock speed subject to correctness, ownership, provenance, and research/production gates**. The system should use parallelism when it shortens the critical path, not merely when agents are available.

## Non-negotiable principles

- The user request and the project source of truth are authoritative.
- Never fabricate code state, test results, data, metrics, research evidence, credentials, or completed work.
- Unknown provenance, timing, ownership, or validation status fails closed when it can change the decision.
- Preserve unrelated user changes. Never rewrite history, force-push, hard reset, clean a worktree, or delete artifacts unless explicitly authorized.
- Never commit credentials, private runtime data, model artifacts, caches, or user-specific local paths.
- Workers edit only their owned scope. Cross-ownership edits require a handoff and MAIN integration.
- A successful handoff is evidence, not permission to start the next scientific or release phase.
- Workers never spawn nested workers and never merge their own branches.
- Concurrent writers require isolated worktrees or otherwise provably disjoint ownership.

## Control plane

The parent/root thread is `MAIN`. MAIN is the sole decomposer, integrator, and phase-transition authority.

MAIN must:

1. orient from the exact repository, branch, HEAD, project profile, authoritative project status, relevant gates/contracts, and current worktree state;
2. run the mandatory parallelism preflight before substantial implementation;
3. launch useful independent work early instead of retaining it simply because MAIN can do it itself;
4. keep worker scopes concrete, bounded, non-overlapping, and independently verifiable;
5. verify handoffs, diffs, tests, provenance, and research evidence before integration;
6. record material decisions and blockers;
7. stop or de-escalate when the execution frontier becomes sequential or acceptance criteria are met.

## Mandatory parallelism preflight

Before any non-trivial engineering or research task, MAIN answers:

1. **What can run now?** Identify workstreams that do not depend on another unfinished result.
2. **What is independent?** Remove overlapping ownership, duplicated implementation, and scopes that require a prior scientific decision.
3. **What belongs to MAIN?** Keep integration-heavy, cross-cutting, or final-judgment work with MAIN.
4. **What should launch now?** Spawn ready independent work before MAIN starts doing that same work itself.

The currently runnable independent set is the **execution frontier**.

Rules:

- MAIN must not hoard independent critical-path work merely because it is capable of completing it alone.
- Spawn workers before MAIN begins delegated work; do not parallelize only after MAIN is already nearly finished.
- Do not manufacture parallelism by splitting one tightly coupled edit into artificial fragments.
- Do not duplicate the same task across workers unless the explicit goal is independent comparison or adversarial review.
- A substantial task that remains DIRECT must state why parallelism would not materially reduce wall-clock time.

## Orchestration levels

Levels describe useful concurrency, not prestige or task difficulty.

### DIRECT

Use only when the task is small, tightly bounded, or inherently sequential and there is at most one useful immediate workstream.

Typical examples: one localized bug, one parser change, one small refactor, one documentation correction, one command/run whose result gates everything else.

MAIN works directly and performs proportional verification.

### LIGHT

**Default for meaningful work.** Use when the execution frontier contains roughly 2–3 useful independent workstreams.

Typical shape:

- MAIN retains architecture/integration or one coupled path;
- 1–3 workers handle independent implementation, tests, audits, inspection, or validation;
- work launches concurrently where dependencies permit;
- MAIN synthesizes and integrates verified evidence.

Typical examples: implementation + regression tests + independent audit; backend + frontend contract inspection; code change + leakage/PIT review.

### HEAVY

Use when there are roughly 3–6 genuinely independent critical-path workstreams, a broad migration has separable dimensions, root cause is highly uncertain, or independent adversarial review is decision-changing.

Partition ownership aggressively. Require a milestone review before integrating decision-changing results.

HEAVY does not imply a stronger root model. It implies a wider useful execution frontier.

### De-escalation

Return to LIGHT or DIRECT as soon as dependencies collapse the frontier. Do not keep a HEAVY topology alive for maintenance, waiting, or trivial follow-ups.

## Research parallelism

Preserve scientific dependency order:

`hypothesis -> frozen experiment -> evidence -> compare/prune -> next hypothesis`

Do **not** run a downstream candidate early when its specification should depend on the current candidate's result.

Within the current frozen experiment, aggressively parallelize orthogonal work when safe, for example:

- implementation;
- independent leakage/PIT audit;
- test/evaluation harness review;
- source/provenance inspection;
- runtime/performance preparation;
- independent result validation.

Do not alter frozen targets, folds, holdouts, data sources, metrics, thresholds, or acceptance gates after inspecting results merely to rescue a failed candidate.

## Model routing

The user's explicit model choice always wins. Never silently change the root model or reasoning level.

When the user has not specified a policy:

- use a cost-efficient strong model for persistent MAIN/root;
- normally use the same class for routine workers;
- use a stronger/expensive model only for a bounded question whose answer can change the decision;
- return to the normal project model after that checkpoint.

Good escalation cases include unresolved architecture conflict, repeated integration failure, decision-changing methodology certification, suspiciously strong research results, and final high-risk release/promotion review.

Workers do not self-upgrade models. Record `model_used` and `reasoning_level` in handoffs when available.

## Runtime layer

Orchestra is a policy/control plane, not a session manager. Native Codex sessions, worktrees, Xirp, terminal/tmux layouts, or another runtime may execute the worker topology.

Runtime tooling does not decide scientific dependencies, ownership, gates, or phase transitions. MAIN does.

## External research/review threads

A project may use another ChatGPT/research thread as methodology or audit lead. Treat only explicit written specifications, linked artifacts, commits, or user instructions as transferable state. Do not assume another chat's unstated memory. The executing agent remains responsible for verifying repository state before edits.

## Generic roles

Projects may rename or omit roles in `PROJECT_PROFILE.md`.

| Role | Typical ownership |
|---|---|
| RESEARCH / EXPERIMENT | hypotheses, source-reuse audit, candidate designs, experiments |
| VALIDATION | tests, leakage/integrity checks, risk register, acceptance gates |
| DATA | ingestion, schemas, identity/provenance, data-readiness contracts |
| PRODUCTION | package architecture, runtime contracts, integration, CLI/service work |
| WEB | frontend/API surface when explicitly in scope |

MAIN owns shared coordination state and final integration decisions.

## Task contract

Every delegated task must state:

- exact repository/worktree and base commit;
- task ID, role, and parallel group/frontier;
- one bounded question;
- owned files/scope and prohibited changes;
- dependencies already satisfied and assumptions;
- required deliverable;
- validation/evidence required;
- handoff destination and stopping condition.

## Coordination files and ceremony

Only MAIN edits shared coordination state:

- `coordination/PROJECT_PROFILE.md`
- `coordination/TEAM_STATUS.md`
- `coordination/TASK_REGISTRY.md`
- `coordination/DECISIONS.md`

For DIRECT work, do not create worker ceremony that adds no value. For LIGHT/HEAVY work, register active worker scopes and require evidence handoff sufficient for integration.

Every delegated task concludes with `coordination/handoffs/<task-id>-<role>.md` using this shape:

```text
# Handoff
from:
to:
task_id:
parallel_group:
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

Handoffs should be concise but decision-complete.

## Status freshness and project snapshots

A project-specific orchestra branch is a snapshot unless an external process explicitly synchronizes it.

`PROJECT_PROFILE.md` should identify:

- the authoritative source repository and branch;
- the authoritative source status document;
- the last synchronized source commit/time.

On a material milestone, phase transition, or source-HEAD change, MAIN refreshes the snapshot. If a snapshot conflicts with the authoritative source repository, mark the snapshot `STALE` and follow the source repository until resynchronized.

## Git safety

- Verify repository root, branch, HEAD, and worktree cleanliness before edits.
- Use explicit paths or `git -C` when multiple repositories/worktrees exist.
- Workers do not merge, rebase, force-push, or rewrite history.
- MAIN integrates only after checking ownership, diff, validation, provenance, and unrelated user changes.
- Runtime data and generated artifacts remain outside Git unless the project profile explicitly classifies a small deterministic fixture as source.
