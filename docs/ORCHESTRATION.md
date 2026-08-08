# IDX Trade orchestration

The parent/root thread is `MAIN`, the sole control plane and integrator. The
current project profile is `coordination/PROJECT_PROFILE.md`.

## Current operating loop

1. Verify `samindriano/idx-trade` root/branch/HEAD and current data contracts.
2. Read `PROJECT_PROFILE`, `TEAM_STATUS`, task registry, DATA GATE runbook, and relevant code/tests.
3. Choose DIRECT/LIGHT/HEAVY based on coordination need, not worker availability.
4. Delegate bounded non-overlapping work with explicit ownership and stopping conditions.
5. Collect written handoffs and verify actual diffs/tests/evidence.
6. Record material GO/NO-GO/BLOCKED decisions in `DECISIONS.md`.
7. Integrate only approved changes and update shared status.
8. Stop when the current gate is answered; do not drift into modelling.

## Execution levels

| Level | Use when | Pattern |
|---|---|---|
| DIRECT | one bounded fix/audit | MAIN works sequentially + targeted validation |
| LIGHT | default current mode | 1-2 Luna xhigh workers, usually implementation + tests/audit |
| HEAVY | genuinely parallel high-risk backfill/reconciliation | 3-6 Luna xhigh workers with isolated ownership + milestone review |

HEAVY does not imply Sol. Model strength and orchestration intensity are separate.

## Model routing

- User override is authoritative.
- Default root: `Luna xhigh`.
- Default workers: `Luna xhigh`.
- `Sol High` is used only for bounded escalation checkpoints: unresolved architecture conflict, repeated integration failure, pre-model DATA GATE certification, suspicious research result, or final pre-deployment review.
- Return to Luna after the checkpoint unless the user changes policy.

An external ChatGPT thread may act as research/methodology/audit lead. Codex
must receive explicit written specifications or commits and independently
verify repository state; do not assume unstated cross-chat memory.

## Current DATA GATE

Model/SR/probability/Kelly work remains blocked until the chosen research
period passes all of the following:

1. point-in-time listing/delisting identity;
2. Regular-Market suspension/resumption intervals;
3. source-discovery completeness and official snapshot reconciliation;
4. raw Yahoo EOD backfill without silent history revisions;
5. corporate-action provenance and raw execution-price semantics;
6. adversarial QA catalog gate;
7. full point-in-time universe coverage;
8. frozen reproducibility/data snapshot.

Important invariants:

- `UNKNOWN` does not become `ACTIVE` by default.
- Missing Yahoo rows do not imply suspend/no-trade/provider failure.
- Current survivors never define historical universes.
- Raw execution OHLC remains separate from adjusted/vendor data.
- A shorter clean period beats a longer guessed period.
- Parser success does not prove source-discovery completeness.

## Promotion

After full DATA GATE evidence is available, MAIN should request an independent
pre-model review (Sol High is justified here), record PASS/FAIL/UNKNOWN, and
only then ask the user to promote the project to setup/SR research.

A failed or unknown gate is not repaired by weakening the standard.
