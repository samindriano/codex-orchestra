# Reusable Codex Orchestra working agreement

## Purpose

This repository is a reusable control plane for multi-agent research and
engineering work. Project-specific facts belong in
`coordination/PROJECT_PROFILE.md`; keep this file generic unless the orchestration
protocol itself changes.

## Non-negotiable principles

- The user request and the project source of truth are authoritative.
- Never fabricate code state, test results, data, metrics, research evidence,
  credentials, or completed work.
- Unknown provenance, timing, ownership, or validation status fails closed when
  it can change the decision.
- Preserve unrelated user changes. Never rewrite history, force-push, hard
  reset, clean a worktree, or delete artifacts unless explicitly authorized.
- Never commit credentials, private runtime data, model artifacts, caches, or
  user-specific local paths.
- Workers edit only their owned scope. Cross-ownership edits require a handoff
  and MAIN integration.
- A successful handoff is evidence, not permission to start the next phase.

## Control plane

The parent/root thread is `MAIN`. MAIN is the sole decomposer, integrator, and
phase-transition authority.

MAIN must:

1. orient from the exact repository, branch, HEAD, project profile, team status,
   task registry, and relevant source contracts;
2. choose the lightest orchestration level that is still reliable;
3. delegate concrete, non-overlapping tasks with explicit ownership;
4. verify handoffs, diffs, tests, and evidence before integration;
5. record material decisions and blockers;
6. stop when acceptance criteria are met rather than creating work for idle
   workers.

Workers never spawn nested workers and never merge their own branches.
Read-only workers may share a checkout; concurrent writers require isolated
worktrees or otherwise provably disjoint ownership.

## Orchestration levels

Use levels as coordination intensity, not quotas.

### DIRECT

Use when the task is tightly bounded, sequential, and does not benefit from
independent parallel work. MAIN performs the work and targeted verification.

Typical examples: one bug, one parser, one small refactor, one focused audit,
one documentation decision.

### LIGHT

Default for meaningful but bounded work. Use one or two workers when there are
independent questions such as implementation + tests, or primary audit +
independent validation. MAIN synthesizes and verifies.

### HEAVY

Use three to six workers only when work is genuinely parallelizable, high-risk,
or open-ended. Partition by non-overlapping ownership. Require a milestone
review before integrating decision-changing results.

Do not use HEAVY merely because workers are available.

## Model routing

The user's explicit model choice always wins. Never silently change the root
model or reasoning level.

When the user has not specified a policy, prefer a cost-efficient strong model
for persistent root and worker execution. A project profile may name an exact
default (for example `Luna xhigh`).

Use a more expensive/stronger model as a bounded escalation, not as a permanent
root by default. Escalation is justified for cases such as:

- unresolved architecture conflicts with multiple plausible solutions;
- repeated integration/debugging failure after bounded attempts;
- decision-changing methodology or safety review;
- suspiciously strong research results requiring adversarial review;
- final high-risk promotion or deployment gate.

An escalation should answer a specific question or certify a checkpoint. After
that, return to the project default unless the user says otherwise.

Workers do not self-upgrade models. Record `model_used` and `reasoning_level` in
handoffs when available.

## External research/review threads

A project may use another ChatGPT/research thread as methodology or audit lead.
Treat only explicit written specifications, linked artifacts, commits, or user
instructions as transferable state. Do not assume another chat's unstated
memory. Codex remains responsible for verifying repository state before edits.

## Generic roles

Projects may rename or omit roles in `PROJECT_PROFILE.md`. Common roles are:

| Role | Typical ownership |
|---|---|
| RESEARCH / EXPERIMENT | hypotheses, source-reuse audit, candidate designs, experiments |
| VALIDATION | tests, leakage/integrity checks, risk register, acceptance gates |
| DATA | ingestion, schemas, identity/provenance, data-readiness contracts |
| PRODUCTION | package architecture, runtime contracts, integration, CLI/service work |
| WEB | frontend/API surface when explicitly in scope |

MAIN owns root coordination files and final integration decisions.

## Task contract

Every delegated task must state:

- exact repository/worktree and base commit;
- role and one bounded question;
- allowed files/scope and prohibited changes;
- dependencies and assumptions;
- required deliverable;
- validation/evidence required;
- handoff destination and stopping condition.

Prefer the research loop:

`hypothesis -> bounded work -> compare -> prune -> validate -> integrate`

Do not alter frozen targets, folds, holdouts, acceptance gates, or source data
post hoc merely to rescue a failed result.

## Coordination files

Only MAIN edits shared coordination state:

- `coordination/PROJECT_PROFILE.md`
- `coordination/TEAM_STATUS.md`
- `coordination/TASK_REGISTRY.md`
- `coordination/DECISIONS.md`

Every delegated task concludes with
`coordination/handoffs/<task-id>-<role>.md` using this shape:

```text
# Handoff
from:
to:
task_id:
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

## Git safety

- Verify repository root, branch, HEAD, and worktree cleanliness before edits.
- Use explicit paths or `git -C` when multiple repositories/worktrees exist.
- Workers do not merge, rebase, force-push, or rewrite history.
- MAIN integrates only after checking scope, diff, validation, and provenance.
- Runtime data and generated artifacts remain outside Git unless the project
  profile explicitly classifies a small deterministic fixture as source.
