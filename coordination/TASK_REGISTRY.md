# Task registry

Only MAIN changes task ownership, dependencies, model routing, or status.

| Task ID | Owner | Scope | Model / reasoning | Base source commit | Branch/worktree | Dependencies | Status |
|---|---|---|---|---|---|---|---|
| `<ID>` | `<ROLE>` | `<one bounded question>` | `<model / level>` | `<sha>` | `<branch/path>` | `<deps>` | `PLANNED` |

Recommended statuses:

- `PLANNED`
- `READY`
- `IN_PROGRESS`
- `BLOCKED`
- `HANDOFF_READY`
- `INTEGRATED`
- `REJECTED`

Do not pre-create worker tasks merely to fill roles. Register only work that is
actually on the current critical path.
