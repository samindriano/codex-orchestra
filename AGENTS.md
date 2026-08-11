# IDX Trade working agreement

## Authority and current state

This repository branch is an orchestration snapshot for `samindriano/idx-trade`. The source repository and its `docs/CURRENT_STATUS.md` are authoritative. If this file conflicts with the source project, treat this snapshot as `STALE` until MAIN refreshes it.

Synchronized source state at `cbecbe3993e1c2adb0dab660b687e316b14a69c4`:

- operating mode: `EXPLORATORY_RESEARCH_ONLY`;
- alpha architecture search: closed;
- final alpha ranker: `V3-B-STRUCTURE-LITE-V1-CANDIDATE-005`;
- final model SHA-256: `1a702031113ff75f38158aa35d1c2bac477cd424d7f14b83d7a89e6c74fef0f6`;
- exact 33-feature order SHA-256: `100ff7a9bacf394b2adc1daa7eb73b0fe7b89613a6918a9e4ded60ca67a55e9e`;
- Path Risk V1: failed/closed;
- Path Risk V2 PR-002/PR-003: frozen + implemented, discovery outcomes unviewed;
- Path Risk F5/F6: sealed;
- fresh-forward realized outcomes after 2026-07-31: locked/unaccessed;
- calibration, alpha+risk integration, execution-PnL, Kelly, paper/live: not automatically authorized.

## Primary objective of the orchestra

Use **Luna xhigh concurrency to reduce wall-clock time** without weakening ownership, validation, leakage/PIT controls, frozen experiments, sealed evidence, or phase gates.

The orchestra is not useful if MAIN simply performs every meaningful scope sequentially. It is also not useful if workers are spawned without independent work.

## Mandatory parallelism preflight

Before meaningful implementation/research work, MAIN must explicitly identify:

1. workstreams that can start now without another unfinished result;
2. which of those workstreams are independent and non-overlapping;
3. which cross-cutting/coupled work MAIN should retain;
4. which ready scopes should be spawned immediately.

The ready independent set is the **execution frontier**.

Rules:

- MAIN must not hoard independent critical-path work merely because it can finish it alone.
- Spawn workers before MAIN starts doing the same delegated work.
- Do not create artificial parallelism by fragmenting tightly coupled edits.
- Do not duplicate work unless the explicit purpose is independent comparison/adversarial review.
- A substantial task that remains DIRECT must state why parallelism would not materially reduce wall-clock time.

## Orchestration levels

### DIRECT

Use for small/inherently sequential work with at most one useful immediate path: one localized fix, one command whose result gates everything, one tiny documentation change, or another scope where worker startup would not repay itself.

### LIGHT — default for meaningful work

Use when roughly 2–3 useful independent scopes are ready now.

Typical IDX shape:

- MAIN: architecture/integration/gate protection or one coupled path;
- Worker A: implementation;
- Worker B: independent tests/leakage/PIT audit;
- optional Worker C: runtime/data/API/frontend inspection;
- launch concurrently where dependencies permit;
- MAIN verifies and integrates evidence.

### HEAVY

Use when roughly 3–6 independent critical-path scopes exist, a migration has separable data/model/runtime/web dimensions, debugging has several plausible independent root causes, or an independent high-value review is decision-changing.

HEAVY does not imply Sol. It means a wider useful frontier.

De-escalate as soon as the frontier becomes sequential.

## Research parallelism rule

Preserve scientific dependency order:

`hypothesis -> frozen experiment -> evidence -> compare/prune -> next hypothesis`

Do not launch a later candidate early if its specification should depend on the current result.

Inside the current frozen experiment, parallelize orthogonal work aggressively when safe:

- implementation;
- regression tests;
- leakage/PIT/provenance audit;
- runtime/cache preparation;
- source/data-contract inspection;
- independent result validation.

Never change a frozen target, fold, holdout, candidate definition, metric, threshold, or source after viewing results merely to rescue a failure.

## Current Path Risk V2 boundary

Immediate source-authorized flow:

1. verify checkout/import resolution and full repository tests;
2. if preflight passes, execute exactly one frozen PR-002/PR-003 F1-F4 discovery run;
3. review the result against frozen gates;
4. do not touch F5/F6 without a separate one-shot confirmation specification.

The final evidence-producing discovery execution is intentionally serialized. Supporting read-only audit/test diagnosis may run in parallel if it cannot contaminate the run.

Do not:

- reopen final V3-B/V4 alpha architecture automatically;
- rescue Path Risk V1 PR-001;
- add PR-004 after seeing PR-002/PR-003;
- access F5/F6 during V2 discovery;
- access post-2026-07-31 fresh-forward realized outcomes early;
- create risk-veto/reranking/sizing/execution rules automatically.

## Model routing

The user may override this at any time.

- persistent MAIN/root default: **Luna xhigh**;
- normal workers: **Luna xhigh**;
- escalation: **Sol High**, bounded to a decision-changing checkpoint.

Appropriate Sol checkpoints include unresolved architecture conflict after bounded Luna attempts, repeated integration failure, methodology certification, suspiciously strong research evidence, or a final high-risk promotion/release decision.

Use safe Luna concurrency for latency reduction before relying on a persistent premium root.

## Ownership

| Role | Typical owned scope |
|---|---|
| RESEARCH / EXPERIMENT | bounded hypotheses/specifications, experiment implementation/interpretation; no silent gate changes |
| VALIDATION | tests, leakage/PIT audit, sealed-fold controls, result verification |
| DATA | source/provenance, point-in-time universe, coverage/data contracts |
| PRODUCTION | package/runtime architecture, scoring/artifact/runtime integration |
| WEB | monitoring/API/frontend work when explicitly scoped; no locked-outcome exposure |

MAIN alone integrates and edits shared coordination state.

Workers never spawn workers, merge, rebase, force-push, or rewrite history. Concurrent writers require isolated worktrees or provably disjoint ownership.

## Task contract

Every worker receives:

- exact repo/worktree and base commit;
- task ID and parallel group;
- one bounded question and why it can run now;
- owned scope and prohibited changes;
- satisfied dependencies/assumptions;
- deliverable and validation evidence;
- integration contract;
- stopping condition and handoff path.

Every delegated task returns a concise decision-complete handoff.

## Snapshot synchronization

This `orchestra/idx-trade` branch is not automatically updated by source-project work. On a material source phase transition, final-model/gate change, or meaningful source-HEAD milestone, MAIN refreshes `PROJECT_PROFILE`, `TEAM_STATUS`, `TASK_REGISTRY`, and material `DECISIONS` entries.

If synchronization is missed, stale orchestration state must never override the source repository.
