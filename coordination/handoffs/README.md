# Handoff directory

For projects that need durable handoffs, a delegated task may write one file named
`<task-id>-<role>.md` here. Ordinary workers can return a compact packet in MAIN.
A handoff records evidence; it never authorizes a downstream phase by itself.
MAIN verifies it and records material decisions in `coordination/DECISIONS.md`.

Optional detailed shape:

```text
# Handoff
from:
to:
task_id:
model_used:
reasoning_level:
source_repository:
source_commit:
branch:
head_commit:
scope:
files_changed:
findings:
decisions_made:
decisions_needed:
blocking_risks:
validation_run:
recommended_next_action:
```

`validation_run` must distinguish what was actually executed from what was only
reviewed statically. Never write `pass` for a check that was not run.
