# Developing Codex Orchestra

This repository is the canonical, offline-installable source for a generic Codex
foundation. Installed global instructions come from `policies/GLOBAL_AGENTS.md`,
not this development agreement. Project-specific policy stays in its project.

Read relevant source and current Git diff before edits. Preserve unrelated changes
and user configuration. Keep one canonical policy per root mode; do not duplicate
workflow manuals into global instructions or project overlays.

Use supported runtime capabilities. Verify models and effort from metadata, not
self-description. Never silently substitute an expensive worker or change the root
model. MAIN owns integration; workers stay in their scope and do not spawn workers,
merge, rebase, or push.

Installer changes require temporary-home tests for preservation, backups, dry-run,
idempotence, and verification failure. Test instruction changes with fresh prompt
discovery and bounded runtime probes. Keep secrets, local backups, logs, test homes,
and machine paths out of Git. Before committing run:
`python -m unittest discover -s tests -v` and `git diff --check`.
Do not push or merge without user authorization.
