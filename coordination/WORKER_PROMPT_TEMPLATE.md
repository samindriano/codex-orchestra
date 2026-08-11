# Worker prompt template

Use this as a starting point. Delete irrelevant fields rather than leaving ambiguous placeholders.

```text
ROLE: <role>
TASK ID: <id>
PARALLEL GROUP: <group>

Repository/worktree: <absolute path or owner/repo + branch>
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

A worker solves the assigned question quickly and independently. It does not redesign the entire project, wait for unrelated sibling work, or expand its scope simply because capacity remains.
