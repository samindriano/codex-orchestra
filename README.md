# Codex Orchestra - IDX Trade settings

IDX-specific orchestration profile for `samindriano/idx-trade`.

- Source repository: `samindriano/idx-trade`
- Audited source commit: `1ebfe62545993a3cd578127594216479f1730468`
- Snapshot branch: `orchestra/idx-trade`
- Scope: orchestration/control-plane settings only
- Excluded: source code, tests, market data, models, caches, credentials, and runtime artifacts

Current phase: **DATA GATE / historical data-readiness**. Support/resistance,
model training, probability scoring, Kelly sizing, and paper/live trading remain
blocked until the gate passes and the phase is explicitly promoted.

Default Codex routing for this project:

- root: `Luna xhigh`
- workers: `Luna xhigh`
- `Sol High`: bounded escalation checkpoints only

See `coordination/PROJECT_PROFILE.md` for the current authoritative orchestration profile.
