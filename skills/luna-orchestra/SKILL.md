---
name: luna-orchestra
description: Throughput-oriented orchestration selected by LUNA_ROOT or GPT6_LUNA_ROOT. Identify independent execution lanes, launch useful bounded workers early, and integrate verified results.
---

# Luna Orchestra

Optimize useful verified work per constrained resource, subject to correctness and
user intent. The selected profile pins the root model and effort: legacy `global-luna`
uses GPT-5.6 Luna XHigh; `global-gpt6-luna` uses GPT-6 Luna Max. Every configured
subagent role is GPT-6 Luna Max. Execution width is a separate choice. Do not change
model families or self-upgrade workers. Astra is manual-only and is never an automatic
escalation for difficulty, conflict, review, HEAVY work, ambiguity, or disagreement.

For meaningful work, perform a brief parallelism preflight: what can run now,
which scopes are independent, what must MAIN retain, and what should launch early?
This ready independent set is the execution frontier. Prefer useful early parallel
execution without manufacturing lanes or requiring fan-out for every task.

Apply a soft **+20–30% delegation bias** on tasks already suitable for
orchestration: when one bounded, independent lane can start now and materially
shorten wall-clock time, lean toward assigning one configured worker in borderline
DIRECT/LIGHT cases. This is not a quota or a per-task worker-count increase. Keep
trivial, serial, and high-coordination work DIRECT; add workers only for distinct
ready lanes whose benefit justifies coordination and integration cost.

- **DIRECT:** one useful immediate lane, including hard sequential problems.
- **LIGHT:** roughly 1–2 useful independent worker lanes.
- **HEAVY:** roughly 3–5 genuinely independent lanes within runtime capacity.

Launch independent work before MAIN starts doing that same work. Keep dependent
experiments or decisions sequential. MAIN retains framing, shared-file integration,
conflict resolution, and final judgment. Prefer local children in one visible MAIN;
use isolated worktrees only where writes would collide. Workers do not spawn workers.

Each assignment names the exact source/commit where relevant, question, ownership,
prohibited changes, deliverable, verification, and stop point. Use runtime-pinned
`default`, `explorer`, or `worker` roles (`gpt-6-luna`, `max`) whenever workers are
used. Omit spawn-level model and reasoning-effort overrides. For custom roles,
verify their effective model and effort before use. If pinning cannot be
established, stay DIRECT and report the gap; never silently change the configured
model or switch to Astra.

Request compact verdicts, decision-changing findings, exact file/run/commit references,
counterexamples, UNKNOWNs, and next actions. Pull raw evidence only as needed.
MAIN checks claims, diffs, and proportional tests before integration. Independent
validation or adversarial review should answer a material question, not be a ritual.
De-escalate when the frontier collapses; stop after acceptance criteria are met.
Project constraints and actual state control over throughput preferences.
