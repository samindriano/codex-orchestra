---
name: luna-orchestra
description: Throughput-oriented orchestration selected by the LUNA_ROOT runtime policy. Identify independent execution lanes, launch useful Luna XHigh workers early, and integrate verified results.
---

# Luna Orchestra

Optimize useful verified work per constrained resource, subject to correctness and
user intent. Luna XHigh is the root and default worker tier; execution width is a
separate choice. Do not change model families or self-upgrade workers.

For meaningful work, perform a brief parallelism preflight: what can run now,
which scopes are independent, what must MAIN retain, and what should launch early?
This ready independent set is the execution frontier. Prefer useful early parallel
execution without manufacturing lanes or requiring fan-out for every task.

- **DIRECT:** one useful immediate lane, including hard sequential problems.
- **LIGHT:** roughly 1–2 useful independent worker lanes.
- **HEAVY:** roughly 3–5 genuinely independent lanes within runtime capacity.

Launch independent work before MAIN starts doing that same work. Keep dependent
experiments or decisions sequential. MAIN retains framing, shared-file integration,
conflict resolution, and final judgment. Prefer local children in one visible MAIN;
use isolated worktrees only where writes would collide. Workers do not spawn workers.

Each assignment names the exact source/commit where relevant, question, ownership,
prohibited changes, deliverable, verification, and stop point. Use runtime-pinned
`default`, `explorer`, or `worker` roles (`gpt-5.6-luna`, `xhigh`). If pinning cannot
be established, stay DIRECT and report the gap; never silently inherit a costly tier.

Request compact verdicts, decision-changing findings, exact file/run/commit references,
counterexamples, UNKNOWNs, and next actions. Pull raw evidence only as needed.
MAIN checks claims, diffs, and proportional tests before integration. Independent
validation or adversarial review should answer a material question, not be a ritual.
De-escalate when the frontier collapses; stop after acceptance criteria are met.
Project constraints and actual state control over throughput preferences.
