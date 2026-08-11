# IDX Path Risk V2 — Heavy Parallel Hardening Task

Date: 2026-08-11T04:58:00Z
Status: **READY — HEAVY PARALLEL PRE-OUTCOME HARDENING**

## Source of truth

Primary repository: `samindriano/idx-trade`
Authoritative branch: `research/idx-ranking-v2-spec-v1`
Required source HEAD at task start: latest remote HEAD, at least `8863857ae2b7840648575eaca7885f9416bb01eb`.

Source-side task contract:

`coordination/handoffs/IDX-PATH-RISK-V2-PARALLEL-HARDENING-ORCHESTRA.md`

The source repository wins if this orchestra snapshot becomes stale.

## Goal

Use the upgraded latency-first orchestra to harden the already-implemented Path Risk V2 stack before the one-shot local PR-002/PR-003 F1-F4 discovery run.

This is deliberately parallelizable engineering/validation work. It does **not** open any new research outcome.

## Topology

Use **HEAVY**:

- MAIN / integrator: Luna xhigh
- W1: Luna xhigh — PR-002 stop-touch classifier contract
- W2: Luna xhigh — PR-003 competing-risk/CIF contract
- W3: Luna xhigh — alpha-only comparator/leakage contract
- W4: Luna xhigh — runner/provenance/F1-F4 boundary contract
- W5: Luna xhigh — gate/selection/spec-consistency contract

Workers launch concurrently after MAIN verifies source HEAD and reads the source-side handoff.

## Ownership

Each worker uses an isolated worktree/branch and writes only its source-side assigned new test file plus its own result handoff.

Workers must not edit shared production files. If they find a defect, they encode it as a failing test and report the smallest spec-conforming production fix. MAIN alone patches shared production code after integration.

## Dependencies

All W1-W5 are in parallel group `PRV2-HARDENING` and have no dependency on one another.

MAIN integration depends on all five worker handoffs.

The real Path Risk V2 F1-F4 run remains blocked until MAIN records:

`PATH_RISK_V2_PARALLEL_HARDENING_PASS_READY_FOR_LOCAL_DISCOVERY`

## Hard boundaries

No worker may access:

- the real local V1 Path Risk model table;
- raw H10 label/path artifacts;
- Path Risk F5/F6;
- post-2026-07-31 fresh-forward outcomes;
- the real V2 discovery output directory.

Do not change frozen candidate definitions, 33-feature order, model hyperparameters, metrics, gates, F1-F4 boundaries, F5/F6 seal, final V3-B ranker, or fresh-forward contract.

## MAIN completion requirements

MAIN must:

1. integrate worker commits only after scope/diff review;
2. run focused Path Risk V2 tests;
3. run full pytest;
4. patch shared production code only when a new failing adversarial test proves a spec-conformance defect;
5. rerun focused/full tests after any patch;
6. record worker timings and total wall-clock to assess orchestra speedup;
7. stop before the real outcome-bearing discovery run.

Return final status as exactly one of:

- `PATH_RISK_V2_PARALLEL_HARDENING_PASS_READY_FOR_LOCAL_DISCOVERY`
- `PATH_RISK_V2_PARALLEL_HARDENING_BLOCKED_IMPLEMENTATION_DEFECT`
