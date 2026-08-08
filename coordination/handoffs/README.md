# Handoff directory

Each completed task writes one file named
`<task-id>-<agent>.md` in this directory. Handoffs must record the source
commit, branch, exact scope, files changed, evidence, validation, blockers,
and the smallest safe next action. A handoff does not authorize a downstream
phase; MAIN records that decision in `coordination/DECISIONS.md`.
