# Decisions

Append only. MAIN records decisions with UTC timestamps and evidence.

| ID | Date/time | Decision | Alternatives | Rationale / evidence | Affected files | Approver |
|---|---|---|---|---|---|---|
| IDX-D-001 | 2026-08-08T00:00:00Z | Keep `idx-trade` as the independent Indo Stock repository and add orchestration as an additive control plane. | Create a second IDX repository or copy the US repository wholesale. | User requested an Indo Stock orchestrator in `/Project/idx-trade`; the existing remote already contains the IDX-specific data foundation. | `AGENTS.md`, `coordination/`, `docs/ORCHESTRATION.md` | User |
| IDX-D-002 | 2026-08-08T00:00:00Z | Reuse the US orchestration characteristics: parent control plane, bounded non-overlapping workers, isolated writers, written handoffs, fail-closed gates, and milestone review. | Use an unstructured multi-chat workflow. | User requested the same orchestration approach while replacing US-specific content with IDX-specific contracts. | `AGENTS.md`, `coordination/` | User |
| IDX-D-003 | 2026-08-08T00:00:00Z | Keep model, prediction, monitoring, paper-trading, and trading phases disabled until the research specification and data-readiness gate are approved. | Begin modeling from the existing data foundation. | Existing README and IDX data contracts require point-in-time universe, tradability, coverage, and provenance controls before model work. | `AGENTS.md`, `coordination/TEAM_STATUS.md` | MAIN |
