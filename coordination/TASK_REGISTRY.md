# IDX Trade task registry

Only MAIN changes ownership, dependencies, parallel grouping, model routing, or status.

| Task ID | Owner | Scope | Model / reasoning | Base source commit | Branch/worktree | Parallel group | Dependencies | Status |
|---|---|---|---|---|---|---|---|---|
| IDX-PRV2-HARDEN-W1 | VALIDATION | PR-002 stop-touch target/model adversarial hardening | Luna xhigh / xhigh | `477b4411c8` | isolated writer worktree | `PRV2-HARDENING` | current source state | DONE |
| IDX-PRV2-HARDEN-W2 | VALIDATION | PR-003 person-period/CIF adversarial hardening | Luna xhigh / xhigh | `477b4411c8` | isolated writer worktree | `PRV2-HARDENING` | current source state | DONE |
| IDX-PRV2-HARDEN-W3 | VALIDATION | Fold-specific V3-B alpha-only comparator leakage/incremental-information hardening | Luna xhigh / xhigh | `477b4411c8` | isolated writer worktree | `PRV2-HARDENING` | current source state | DONE |
| IDX-PRV2-HARDEN-W4 | PRODUCTION / VALIDATION | Runner provenance, immutable-input, F1-F4 boundary and output-contract hardening | Luna xhigh / xhigh | `477b4411c8` | isolated writer worktree | `PRV2-HARDENING` | current source state | DONE |
| IDX-PRV2-HARDEN-W5 | EXPERIMENT / VALIDATION | Frozen metric gate, winner selection and spec/code consistency hardening | Luna xhigh / xhigh | `477b4411c8` | isolated writer worktree | `PRV2-HARDENING` | current source state | DONE |
| IDX-PRV2-HARDEN-INTEGRATE | MAIN | Integrate W1-W5, patch proven schema defect, run focused/full pytest | Luna xhigh / xhigh | `477b4411c8` | authoritative integration checkout | `PRV2-HARDEN-INTEGRATE` | W1-W5 complete | DONE |
| IDX-PRV2-PREFLIGHT-TESTS | VALIDATION | Verify import resolution and full repository suite before real discovery | Luna xhigh / xhigh | `9378943bde` | source checkout | `PRV2-PREFLIGHT` | hardening PASS | DONE |
| IDX-PRV2-PREFLIGHT-AUDIT | VALIDATION | Verify frozen spec/input/F1-F4-only boundary and F5/F6 seal | Luna xhigh / xhigh | `9378943bde` | read-only | `PRV2-PREFLIGHT` | hardening PASS | DONE |
| IDX-PRV2-DISCOVERY-RUN | RESEARCH / EXPERIMENT | Execute exactly one frozen PR-002/PR-003 F1-F4 development run | Luna xhigh / xhigh | `9378943bde` | authoritative local execution checkout | `SEQUENTIAL_EVIDENCE_RUN` | hardening + preflight PASS | DONE_FAIL_CLOSE |
| IDX-PRV2-RESULT-REVIEW | MAIN / VALIDATION | Verify evidence and record winner/fail-close | Luna xhigh | `9378943bde` | read-only review | `POST_RUN_REVIEW` | discovery result | DONE_FAIL_CLOSE |
| IDX-PATH-RISK-F5F6-GUARD | MAIN | Keep Path Risk F5/F6 sealed after V2 fail-close | n/a | `80d78a5bed` | policy guard | `SEQUENTIAL_GUARD` | V2 fail-close | ACTIVE_GUARD |
| IDX-FORWARD-OUTCOME-BLOCK | MAIN | Preserve fresh-forward outcome lock and exact 100-session H10-mature evaluation boundary | n/a | `80d78a5bed` | policy guard | `SEQUENTIAL_GUARD` | final V3-B freeze | ACTIVE_GUARD |
| IDX-V3B-FORWARD-OPERATION | PRODUCTION / WEB / MAIN | Continue outcome-blind V3-B data/score/rank accumulation without realized outcome access | Luna xhigh as scoped by owning lane | `80d78a5bed` | dedicated source/frontend lanes | `FORWARD_OPERATION` | final V3-B freeze | READY |

## Closed research state

- V3/V4 alpha architecture search: `CLOSED`.
- final alpha: `V3-B-STRUCTURE-LITE-V1-CANDIDATE-005`.
- Path Risk V1 PR-001: `FAILED_CLOSED`.
- Path Risk V2 PR-002/PR-003: `FAILED_CLOSED`; winner none.
- no PR-004 rescue task is authorized.

## Current launch rule

Do not launch additional Path Risk candidates from the V2 result. F5/F6 remain sealed.

For meaningful engineering work around outcome-blind V3-B forward operation, use the normal parallel-first preflight and spawn independent Luna scopes when useful. Any new Path Risk V3 must first be separately researched and preregistered before execution tasks enter this registry.
