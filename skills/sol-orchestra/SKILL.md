---
name: sol-orchestra
description: Model-pinned orchestration for GPT6_SOL_ROOT. Keep GPT-6 Sol High as the root and use configured GPT-6 Luna Max roles for bounded independent work.
---

# Sol Orchestra

Use this policy only when an explicitly selected profile sets `GPT6_SOL_ROOT`.
That profile pins the root to `gpt-6-sol` / `high`; every configured subagent role
is pinned to `gpt-6-luna` / `max`. Do not infer a different model from task
difficulty, and do not switch to Ultra because it enables automatic delegation.
If effective session or role metadata contradicts these pins, do not delegate;
resolve the mismatch first.

Optimize useful verified work per constrained resource, subject to correctness and
user intent. Do a brief parallelism preflight for meaningful tasks: identify what
can run now, which scopes are independent, what MAIN retains, and which ready worker
assignments should launch early. Do not manufacture lanes or fan out by default.

Apply a soft **+20–30% delegation bias** on tasks already suitable for
orchestration: when one bounded, independent lane can start now and materially
shorten wall-clock time, lean toward assigning one configured worker in borderline
DIRECT/LIGHT cases. This is not a quota or a per-task worker-count increase. Keep
trivial, serial, and high-coordination work DIRECT; add workers only for distinct
ready lanes whose benefit justifies coordination and integration cost.

- **DIRECT:** one useful immediate frontier, including difficult sequential work.
- **LIGHT:** roughly 1–2 useful independent worker lanes.
- **HEAVY:** roughly 3–5 genuinely independent lanes within actual runtime limits.

Launch independent work before MAIN repeats it. Keep dependent experiments or
decisions sequential. MAIN owns framing, shared-file integration, conflict
resolution, and final judgment. Each worker assignment names the exact question,
ownership, prohibited changes, deliverable, verification, and stop point. Use only
configured `default`, `explorer`, or `worker` roles after checking their exposed
metadata; omit spawn-level model and reasoning-effort overrides. For custom roles,
verify their effective model and effort before use. If a pin is absent or
contradicted, stay DIRECT and report the gap.
Workers do not spawn workers, self-upgrade, merge, rebase, or push.

Request compact verdicts with decision-changing findings, exact evidence
references, counterexamples, UNKNOWNs, and next action. MAIN verifies claims and
relevant changes before integration. Independent review should answer a material
question, not be a ritual. De-escalate when the execution frontier collapses.
Project constraints and actual state control over throughput preferences.
