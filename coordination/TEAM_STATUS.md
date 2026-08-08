# CrossRank-US V0 status

Only MAIN may edit this file.

- **Phase:** `BOOTSTRAP_AUDITS`
- **Operating mode:** `EXPLORATORY_RESEARCH_ONLY`
- **Integration branch:** `research/crossrank-us-v0-bootstrap` (created after initial main)
- **Data source:** `NOT_APPROVED`
- **Training / prediction / monitoring / trading:** `DISABLED`
- **Legacy Python source:** `market-movement-analyzer-eventrank-v0 @ a5cd2ff3d80d22c845d43e97f5fd0ec6f604866b` (`research/eventrank-vendor-sample-pack`, clean at audit)
- **Legacy web source:** `stock-anomaly-web @ 917d699764c911e08a81a62f4738815f188156b5` (`migration/nextjs-fastapi-monitoring-actions`, dirty: `frontend/next-env.d.ts`)
- **Active tasks:** `CRUS-EXP-001`, `CRUS-VAL-001`, `CRUS-WEB-001`, `CRUS-PROD-001`
- **Blocked:** web file migration is blocked until the source worktree is clean; no source files may be copied.
- **Completed handoffs:** none
- **Next integration action:** initialize the integration branch; collect read-only audits and resolve source-web dirtiness before web copy/refactor.
