# Worker prompt template

Use this as a starting point. Delete irrelevant fields rather than leaving
ambiguous placeholders.

```text
ROLE: <role>
TASK ID: <id>

Repository/worktree: <absolute path or owner/repo + branch>
Base commit: <sha>
Question/task: <one bounded question>

Owned scope:
- <paths/components>

Allowed changes:
- <explicit changes>

Prohibited changes:
- <explicit no-go areas>
- do not merge/rebase/force-push
- do not touch unrelated user changes
- do not spawn workers

Dependencies/assumptions:
- <inputs already verified by MAIN>

Deliverable:
- <code/audit/report/tests>

Validation required:
- <commands/checks/evidence>

Stop and hand off if:
- source state differs from the stated base;
- ownership conflicts appear;
- a dependency is missing;
- a frozen term would need to change;
- the task premise is invalidated.

Write handoff to:
coordination/handoffs/<task-id>-<role>.md
```

A worker should solve the assigned question, not redesign the entire project.
