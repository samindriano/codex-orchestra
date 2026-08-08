# Decisions

Append only. MAIN records decisions with UTC timestamps and evidence.

| ID | Date/time | Decision | Alternatives | Rationale / evidence | Affected files | Approver |
|---|---|---|---|---|---|---|
| CRUS-D-001 | 2026-07-28T00:00:00Z | Use independent `US-Stock-Model` repository for CrossRank-US V0. | Convert the IDX repository in place. | User-directed isolation preserves legacy V1/V1.1 and EventRank history. | repository foundation | User |
| CRUS-D-002 | 2026-07-28T00:00:00Z | Block copying/refactoring web source until its uncommitted user change is resolved. | Clean, stash, commit, or copy the dirty source. | `stock-anomaly-web` audit found modified `frontend/next-env.d.ts`; source preservation policy forbids altering or copying from a dirty source. | web migration | User mandate |
