# Task registry

Only MAIN changes task ownership, dependencies, model routing, parallel grouping, or status.

| Task ID | Owner | Scope | Model / reasoning | Base source commit | Branch/worktree | Parallel group | Dependencies | Status |
|---|---|---|---|---|---|---|---|---|
| `<ID>` | `<ROLE>` | `<one bounded question>` | `<model / level>` | `<sha>` | `<branch/path>` | `<group or SEQUENTIAL>` | `<deps>` | `PLANNED` |

Recommended statuses:

- `PLANNED`
- `READY`
- `IN_PROGRESS`
- `BLOCKED`
- `HANDOFF_READY`
- `INTEGRATED`
- `REJECTED`

## Execution-frontier rule

Tasks in the same parallel group may launch together only when their listed dependencies are already satisfied and their write ownership does not overlap.

For a meaningful task, MAIN should register the actual current execution frontier before implementation. Launch independent `READY` tasks in the same frontier promptly rather than processing them serially by habit.

Do not pre-create workers merely to fill roles, and do not mark scientifically dependent future experiments `READY` early. Register only work that is genuinely useful on the current critical path.
