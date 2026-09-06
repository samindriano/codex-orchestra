---
name: orchestrate
description: Compatibility entrypoint for explicitly requested orchestration. Route through the runtime-selected Astra or Luna policy without choosing a model or adding a second workflow.
---

# Orchestrate

Use the normal global Luna XHigh policy by default: `LUNA_ROOT` loads
`$luna-orchestra`. Only an explicitly selected Astra profile or explicit
`ASTRA_ROOT` loads `$astra-decision-orchestrator`; never auto-escalate to Astra.
Do not load both. `LUNA_WORKER` follows its assignment without root orchestration.
Explicit DIRECT/LIGHT/HEAVY requests select width, never a different model tier.
Project constraints remain controlling.
This compatibility entrypoint has no separate orchestration policy.
