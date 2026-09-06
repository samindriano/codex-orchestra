---
name: orchestrate
description: Compatibility entrypoint for explicitly requested orchestration. Route through the runtime-selected Astra or Luna policy without choosing a model or adding a second workflow.
---

# Orchestrate

Use the session's explicit runtime policy: `ASTRA_ROOT` loads
`$astra-decision-orchestrator`; `LUNA_ROOT` loads `$luna-orchestra`. Do not load both.
`LUNA_WORKER` follows its assignment without root orchestration. If no marker is
present, do not guess model identity: work directly and explain that model-specific
orchestration requires a fresh matching profile. Explicit DIRECT/LIGHT/HEAVY requests
select width, never a different model tier. Project constraints remain controlling.
This compatibility entrypoint has no separate orchestration policy.
