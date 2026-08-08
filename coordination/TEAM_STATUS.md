# IDX Trade V0 status

Only MAIN may edit this file.

- **Phase:** `DATA_GATE_BACKFILL_AND_RECONCILIATION`
- **Operating mode:** `EXPLORATORY_RESEARCH_ONLY`
- **Primary repository:** `samindriano/idx-trade`
- **Audited source commit:** `1ebfe62545993a3cd578127594216479f1730468`
- **Integration branch:** `main`
- **Market / venue:** `IDX listed equities / REGULAR / daily-EOD`
- **Orchestration default:** `LIGHT`
- **Root / workers:** `Luna xhigh / Luna xhigh`
- **Escalation:** `Sol High checkpoint only`
- **Data foundation:** `IMPLEMENTED; ACTUAL HISTORICAL DATA GATE NOT YET PASSED`
- **Tradability coverage registry:** `EMPTY_BY_DEFAULT; NO COMPLETE WINDOW CLAIMED`
- **Model / SR / probability / Kelly:** `BLOCKED_UNTIL_DATA_GATE`
- **Paper/live trading:** `DISABLED`
- **Active tasks:** `IDX-DATA-002`, `IDX-VAL-002`
- **Blocked task:** `IDX-MODEL-001`
- **Current blockers:** actual EOD backfill, official suspension-source completeness audit, corporate-action verification, adversarial gate, full-universe gate.
- **Next milestone:** produce auditable data-gate artifacts for a candidate historical period and determine PASS/FAIL/UNKNOWN without weakening the gate.
