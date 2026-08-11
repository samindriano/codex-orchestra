# IDX Trade task registry

Only MAIN changes ownership, dependencies, parallel grouping, model routing, or status.

| Task ID | Owner | Scope | Model / reasoning | Base source commit | Branch/worktree | Parallel group | Dependencies | Status |
|---|---|---|---|---|---|---|---|---|
| IDX-PRV2-HARDEN-W1 | VALIDATION | PR-002 stop-touch target/model adversarial hardening; tests only | Luna xhigh / xhigh | `8863857ae2` | isolated writer worktree | `PRV2-HARDENING` | current source state | READY |
| IDX-PRV2-HARDEN-W2 | VALIDATION | PR-003 person-period/CIF adversarial hardening; tests only | Luna xhigh / xhigh | `8863857ae2` | isolated writer worktree | `PRV2-HARDENING` | current source state | READY |
| IDX-PRV2-HARDEN-W3 | VALIDATION | Fold-specific V3-B alpha-only comparator leakage/incremental-information hardening; tests only | Luna xhigh / xhigh | `8863857ae2` | isolated writer worktree | `PRV2-HARDENING` | current source state | READY |
| IDX-PRV2-HARDEN-W4 | PRODUCTION / VALIDATION | Runner provenance, immutable-input, F1-F4 boundary and output-contract hardening; tests only | Luna xhigh / xhigh | `8863857ae2` | isolated writer worktree | `PRV2-HARDENING` | current source state | READY |
| IDX-PRV2-HARDEN-W5 | EXPERIMENT / VALIDATION | Frozen metric gate, winner selection and spec/code consistency hardening; tests only | Luna xhigh / xhigh | `8863857ae2` | isolated writer worktree | `PRV2-HARDENING` | current source state | READY |
| IDX-PRV2-HARDEN-INTEGRATE | MAIN | Review/integrate W1-W5, centrally patch any proven spec-conformance defect, run focused + full pytest, record wall-clock | Luna xhigh / xhigh; Sol High only if decision-changing ambiguity remains | `8863857ae2` | authoritative integration checkout | `PRV2-HARDEN-INTEGRATE` | W1-W5 complete | BLOCKED_ON_WORKERS |
| IDX-PRV2-PREFLIGHT-TESTS | VALIDATION | After hardening PASS, verify current-checkout import resolution and run/assess full repository test suite required before the frozen real discovery run | Luna xhigh / xhigh | `<hardening final head>` | source checkout or isolated validation worktree | `PRV2-PREFLIGHT` | hardening PASS | BLOCKED_ON_HARDENING |
| IDX-PRV2-PREFLIGHT-AUDIT | VALIDATION | After hardening PASS, read-only audit that PR-002/PR-003 frozen spec, immutable joined table identity, F1-F4-only boundary, and F5/F6 seal still match source | Luna xhigh / xhigh | `<hardening final head>` | read-only | `PRV2-PREFLIGHT` | hardening PASS | BLOCKED_ON_HARDENING |
| IDX-PRV2-DISCOVERY-RUN | RESEARCH / EXPERIMENT | Execute exactly one frozen PR-002/PR-003 Path Risk V2 F1-F4 development run; no new candidates; no F5/F6 | Luna xhigh / xhigh | `<hardening final head>` | authoritative local execution checkout | `SEQUENTIAL_EVIDENCE_RUN` | hardening PASS + both preflight tasks PASS | BLOCKED_ON_HARDENING |
| IDX-PRV2-RESULT-REVIEW | MAIN / VALIDATION | Verify generated evidence against frozen gates and record winner/fail-close without touching F5/F6 | Luna xhigh; Sol High only if decision-changing ambiguity remains | `<discovery run head>` | read-only review | `POST_RUN_REVIEW` | discovery result | BLOCKED_ON_RUN |
| IDX-FORWARD-OUTCOME-BLOCK | MAIN | Preserve fresh-forward outcome lock and 100 consecutive H10-mature post-2026-07-31 evaluation boundary | n/a | `8863857ae2` | policy guard | `SEQUENTIAL_GUARD` | final V3-B freeze | ACTIVE_GUARD |

## Closed research state

- V3/V4 alpha architecture search: `CLOSED`.
- final alpha: `V3-B-STRUCTURE-LITE-V1-CANDIDATE-005`.
- Path Risk V1 PR-001: `FAILED_CLOSED`; no rescue.
- Path Risk V2 PR-002/PR-003: only current discovery candidates and still unviewed on their real F1-F4 run.

## Current parallel launch rule

Launch `IDX-PRV2-HARDEN-W1` through `W5` together. Their source-side write ownership is deliberately disjoint. Workers write tests + handoffs only and never shared production files.

MAIN integrates only after all five return. The evidence-producing discovery run remains serialized and blocked until the hardening status is `PATH_RISK_V2_PARALLEL_HARDENING_PASS_READY_FOR_LOCAL_DISCOVERY` and the final local preflight passes.
