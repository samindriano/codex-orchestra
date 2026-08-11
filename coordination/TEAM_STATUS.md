# IDX Trade V0 status

Only MAIN may edit this file.

- **Phase:** `FINAL_ALPHA_FROZEN__PATH_RISK_V2_PRE_OUTCOME`
- **Operating mode:** `EXPLORATORY_RESEARCH_ONLY`
- **Primary repository:** `samindriano/idx-trade`
- **Authoritative branch:** `research/idx-ranking-v2-spec-v1`
- **Source HEAD at sync:** `477b4411c8c294e9ca5012a3079248033de5641c`
- **Authoritative status:** `docs/CURRENT_STATUS.md`
- **Orchestra snapshot freshness:** `CURRENT_AT_SOURCE_HEAD_ABOVE`
- **Last orchestra sync:** `2026-08-11T04:46:00Z`
- **Market / venue:** `IDX listed equities / REGULAR / daily-EOD`
- **Orchestration default:** `LIGHT_PARALLEL_FIRST`
- **Root / workers:** `Luna xhigh / Luna xhigh`
- **Escalation:** `Sol High bounded checkpoint only`
- **Final alpha ranker:** `V3-B-STRUCTURE-LITE-V1-CANDIDATE-005`
- **Final model SHA-256:** `1a702031113ff75f38158aa35d1c2bac477cd424d7f14b83d7a89e6c74fef0f6`
- **Feature-order SHA-256:** `100ff7a9bacf394b2adc1daa7eb73b0fe7b89613a6918a9e4ded60ca67a55e9e`
- **Alpha search:** `CLOSED`
- **Path Risk V1:** `FAILED_CLOSED`
- **Path Risk V2:** `FROZEN_IMPLEMENTED_PRE_OUTCOME`
- **PR-002 viewed:** `false`
- **PR-003 viewed:** `false`
- **Path Risk F5/F6:** `SEALED`
- **Fresh-forward post-2026-07-31 outcomes:** `LOCKED_NOT_ACCESSED`
- **Calibration / alpha+risk integration / PnL / Kelly / paper/live:** `NOT_AUTHORIZED_AUTOMATICALLY`
- **Execution frontier:** `checkout/import verification + full test suite; then one serialized PR-002/PR-003 F1-F4 discovery run`
- **Parallel-safe support work:** `read-only test failure diagnosis, import/environment audit, provenance/spec verification when non-overlapping`
- **Scientifically sequential boundary:** `do not launch later/rescue candidates or touch F5/F6 before current frozen discovery result`
- **MAIN-retained work:** `gate protection, authoritative run decision, result interpretation, integration, status update`
- **Current blocker:** `full local preflight/test result not yet returned for the frozen Path Risk V2 run`
- **Next milestone:** `complete exactly one authorized PR-002/PR-003 F1-F4 discovery execution and record the frozen verdict without accessing F5/F6`

A substantial future engineering task should not default to one Luna working alone. MAIN must first identify the ready independent workstreams and use LIGHT/HEAVY when that reduces wall-clock time safely.
