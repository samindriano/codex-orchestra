# IDX Trade V0 status

Only MAIN may edit this file.

- **Phase:** `FINAL_ALPHA_FROZEN__PATH_RISK_V2_PARALLEL_HARDENING_PRE_OUTCOME`
- **Operating mode:** `EXPLORATORY_RESEARCH_ONLY`
- **Primary repository:** `samindriano/idx-trade`
- **Authoritative branch:** `research/idx-ranking-v2-spec-v1`
- **Source HEAD at sync:** `477b4411c8c294e9ca5012a3079248033de5641c`
- **Authoritative status:** `docs/CURRENT_STATUS.md` plus newest source checkpoint/handoff
- **Orchestra snapshot freshness:** `CURRENT_AT_SOURCE_HEAD_ABOVE`
- **Last orchestra sync:** `2026-08-11T04:58:00Z`
- **Market / venue:** `IDX listed equities / REGULAR / daily-EOD`
- **Orchestration active topology:** `HEAVY_PARALLEL_FIRST`
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
- **Execution frontier:** `five-way synthetic/static Path Risk V2 hardening in parallel, then MAIN integration; only after PASS return to local real-run preflight`
- **Parallel workers ready:** `W1 PR-002 / W2 PR-003 / W3 alpha comparator / W4 runner+provenance / W5 gate+selection`
- **Scientifically sequential boundary:** `real PR-002/PR-003 F1-F4 discovery remains blocked until hardening+preflight PASS; F5/F6 remain sealed`
- **MAIN-retained work:** `worker integration, shared production fixes, full-suite verification, gate protection, real-run authorization, result interpretation`
- **Current blocker for real run:** `parallel hardening not yet completed`
- **Next milestone:** `PATH_RISK_V2_PARALLEL_HARDENING_PASS_READY_FOR_LOCAL_DISCOVERY`

Root task:

`coordination/handoffs/IDX-PRV2-PARALLEL-HARDENING-ORCHESTRA.md`

The upgraded orchestra should launch all five ready workers before MAIN starts duplicating their audit work. Workers have disjoint write ownership and do not touch real outcome-bearing data.
