# IDX Trade task registry

Only MAIN changes ownership, dependencies, parallel grouping, model routing, or status.

| Task ID | Owner | Scope | Model / reasoning | Base source commit | Branch/worktree | Parallel group | Dependencies | Status |
|---|---|---|---|---|---|---|---|---|
| IDX-PRV2-PREFLIGHT-TESTS | VALIDATION | Verify current-checkout import resolution and run/assess the full repository test suite required before the frozen Path Risk V2 discovery run | Luna xhigh / xhigh | `cbecbe3993` | source checkout or isolated validation worktree | `PRV2-PREFLIGHT` | current source state | READY |
| IDX-PRV2-PREFLIGHT-AUDIT | VALIDATION | Read-only audit that PR-002/PR-003 frozen spec, immutable joined table identity, F1-F4-only boundary, and F5/F6 seal still match the authoritative source before execution | Luna xhigh / xhigh | `cbecbe3993` | read-only | `PRV2-PREFLIGHT` | current source state | READY |
| IDX-PRV2-DISCOVERY-RUN | RESEARCH / EXPERIMENT | Execute exactly one frozen PR-002/PR-003 Path Risk V2 F1-F4 development run using the authorized handoff; no new candidates; no F5/F6 | Luna xhigh / xhigh | `cbecbe3993` | authoritative local execution checkout | `SEQUENTIAL_EVIDENCE_RUN` | both PRV2 preflight tasks PASS | BLOCKED_ON_PREFLIGHT |
| IDX-PRV2-RESULT-REVIEW | MAIN / VALIDATION | Verify generated evidence against frozen gates and record winner/fail-close without touching F5/F6 | Luna xhigh; Sol High only if decision-changing ambiguity remains | `<discovery run head>` | read-only review | `POST_RUN_REVIEW` | discovery result | BLOCKED_ON_RUN |
| IDX-FORWARD-OUTCOME-BLOCK | MAIN | Preserve fresh-forward outcome lock and 100 consecutive H10-mature post-2026-07-31 evaluation boundary | n/a | `cbecbe3993` | policy guard | `SEQUENTIAL_GUARD` | final V3-B freeze | ACTIVE_GUARD |

## Closed research state

- V3/V4 alpha architecture search: `CLOSED`.
- final alpha: `V3-B-STRUCTURE-LITE-V1-CANDIDATE-005`.
- Path Risk V1 PR-001: `FAILED_CLOSED`; no rescue.
- Path Risk V2 PR-002/PR-003: only current discovery candidates.

## Parallel launch rule

`IDX-PRV2-PREFLIGHT-TESTS` and `IDX-PRV2-PREFLIGHT-AUDIT` are independent enough to run together if their checkouts/ownership remain non-overlapping. The evidence-producing discovery run itself remains serialized until both preflight checks pass.

For future meaningful tasks, MAIN should create a real parallel group whenever 2–3 useful independent workstreams are immediately runnable. Do not process those scopes serially merely because one Luna could eventually finish all of them.
