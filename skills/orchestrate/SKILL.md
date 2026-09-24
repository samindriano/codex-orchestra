---
name: orchestrate
description: Compatibility entrypoint for explicitly requested orchestration. Route through the runtime-selected Astra, Luna, or Sol policy without choosing a model or adding a second workflow.
---

# Orchestrate

`LUNA_ROOT` and `GPT6_LUNA_ROOT` load `$luna-orchestra` with a GPT-6 Luna XHigh
root; `GPT6_SOL_ROOT` loads `$sol-orchestra` only for an explicit override;
`ASTRA_ROOT` loads `$astra-decision-orchestrator` only for a manually selected
Astra profile. Never auto-escalate to Astra or infer a root from task difficulty.
Load only the selected root policy. `LUNA_WORKER` follows its assignment without
root orchestration.
Explicit DIRECT/LIGHT/HEAVY requests select width, never a different model tier.
Project constraints remain controlling.
This compatibility entrypoint has no separate orchestration policy.
