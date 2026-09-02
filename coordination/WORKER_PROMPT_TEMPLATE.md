# Worker prompt template

Use this as a starting point. Delete irrelevant fields rather than leaving ambiguous placeholders.

```text
ROLE: <role>
TASK ID: <id>
PARALLEL GROUP: <group>

Repository: <owner/repo>
Local checkout/worktree: <absolute local path when relevant>
Execution surface: LOCAL_CHILD_AGENT | LOCAL_ISOLATED_WORKTREE | EXTERNAL_OR_REMOTE_WORKER
Parent session: MAIN
Base commit: <sha>
Question/task: <one bounded question>
Why this can run now: <dependencies already satisfied; independent from sibling scopes>

Owned scope:
- <paths/components>

Allowed changes:
- <explicit changes>

Prohibited changes:
- <explicit no-go areas>
- do not merge/rebase/force-push
- do not touch unrelated user changes
- do not spawn workers
- do not create a separate user-facing conversation
- do not independently move the task to cloud/remote execution unless the assigned execution surface explicitly authorizes it
- do not redefine frozen gates/targets/specifications
- do not duplicate a sibling worker's owned scope

Dependencies/assumptions:
- <inputs already verified by MAIN>

Sibling scopes running in parallel:
- <task IDs + ownership, so this worker knows the boundaries>

Deliverable:
- <code/audit/report/tests>

Validation required:
- <commands/checks/evidence>

Integration contract:
- <what MAIN needs to integrate/compare this result>

Stop and hand off if:
- source state differs from the stated base in a decision-changing way;
- ownership conflicts appear;
- a dependency is missing;
- a frozen term would need to change;
- the task premise is invalidated.

Write handoff to:
coordination/handoffs/<task-id>-<role>.md
```

Execution-surface default is `LOCAL_CHILD_AGENT`. Use `LOCAL_ISOLATED_WORKTREE` only when concurrent filesystem/Git writes genuinely require isolation. Use `EXTERNAL_OR_REMOTE_WORKER` only with an explicit reason such as user request, unavailable local capability, or genuine remote/resource-isolation need.

A worker solves the assigned question quickly and independently and reports back to MAIN. It does not redesign the entire project, wait for unrelated sibling work, expand its scope simply because capacity remains, or become a new user-facing control plane by default.
