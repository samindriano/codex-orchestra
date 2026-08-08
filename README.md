# Codex Orchestra

Reusable settings-only control plane for Codex multi-agent projects.

`main` is the generic template. Project branches are examples/snapshots, not
sources to merge wholesale:

- `orchestra/us-stock`
- `orchestra/idx-trade`
- `orchestra/biohub`

No project source code, market/competition data, model artifacts, credentials,
or runtime caches belong in this repository.

## Recommended use

1. Copy `AGENTS.md`, `coordination/`, and optionally `docs/ORCHESTRATION.md` into
   the target project.
2. Fill `coordination/PROJECT_PROFILE.md` with project identity, repositories,
   operating mode, roles, gates, and model policy.
3. Initialize `TEAM_STATUS.md`, `TASK_REGISTRY.md`, and `DECISIONS.md`.
4. Keep the generic orchestration protocol stable; project-specific constraints
   should live in the project profile or the target repository's own contracts.
5. Start with `DIRECT`, promote to `LIGHT` when independent work helps, and use
   `HEAVY` only for genuinely parallel/high-risk work.

## Default model-routing philosophy

The user can always choose another setup. Otherwise the reusable default is:

- persistent root: cost-efficient strong reasoning model;
- normal workers: the same cost-efficient strong model;
- expensive model: bounded escalation for hard architecture conflicts,
  repeated failures, suspicious research results, or final high-risk gates.

For the current IDX workflow, the intended concrete mapping is Luna xhigh for
root/workers, with Sol High reserved for escalation checkpoints.

## Files

- `AGENTS.md` — generic orchestration contract.
- `coordination/PROJECT_PROFILE.md` — per-project configuration.
- `coordination/TEAM_STATUS.md` — current phase/status, MAIN-owned.
- `coordination/TASK_REGISTRY.md` — task ownership/dependencies/status.
- `coordination/DECISIONS.md` — append-only material decisions.
- `coordination/handoffs/` — worker evidence and handoffs.
- `docs/ORCHESTRATION.md` — detailed operating loop and level-selection guide.
