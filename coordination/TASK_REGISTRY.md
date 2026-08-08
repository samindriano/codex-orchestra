# Task registry

Only MAIN changes task ownership, dependencies, or status.

| Task ID | Owner | Scope | Model / reasoning | Base source commit | Branch | Dependencies | Status |
|---|---|---|---|---|---|---|---|
| IDX-EXP-001 | EXPERIMENT | Read-only audit of reusable legacy patterns and IDX research-question/target candidates | TBD / TBD | `8fe2e13` | `experiment/idx-trade-reuse-audit` | initial coordination branch | PLANNED |
| IDX-VAL-001 | VALIDATION | Risk register, point-in-time/leakage controls, evaluation integrity, and data-readiness gate audit | TBD / TBD | `8fe2e13` | `validation/idx-trade-risk-audit` | initial coordination branch | PLANNED |
| IDX-DATA-001 | DATA | Reconcile existing IDX listing, tradability, provider-state, session-coverage, and provenance contracts | TBD / TBD | `8fe2e13` | `data/idx-trade-contract-audit` | IDX-VAL-001 read-only findings | PLANNED |
| IDX-PROD-001 | PRODUCTION | Architecture and artifact-contract proposal for the next authorized phase; no model or execution path | TBD / TBD | `8fe2e13` | `production/idx-trade-scaffold` | frozen specification and data gate | BLOCKED_UNTIL_GATE |

WEB has no active task until the user authorizes a web surface and MAIN
creates a separate source-audit task.
