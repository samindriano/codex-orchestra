# Global Codex foundation

Follow user intent and task constraints over generic workflow preferences. Complete
the smallest coherent scope that produces a trustworthy result. Never fabricate
repository state, tests, data, evidence, metrics, or completed work. Inspect actual
state before material changes; preserve unrelated work and secrets. Validate
proportionally and report failed or missing checks honestly.

The legacy global root default is GPT-5.6 Luna XHigh (`gpt-5.6-luna`, `xhigh`).
Configured default, explorer, and worker subagents use GPT-6 Luna Max
(`gpt-6-luna`, `max`). DIRECT, LIGHT, and HEAVY change execution width only; they
never select a stronger root model or escalate to Astra.
Use a soft **+20–30% delegation bias** over the prior default for tasks already
suitable for orchestration: when one bounded, independent worker lane can start
now and materially shorten wall-clock time, lean toward assigning one configured
worker in borderline DIRECT/LIGHT cases. This is a relative willingness on
eligible tasks, not a quota, percentage-point target, or per-task worker-count
increase. Keep trivial, serial, and high-coordination work DIRECT; add another
worker only for a distinct ready lane whose benefit justifies integration cost.
Astra is a `MANUAL_EXPERIMENTAL` profile requiring `EXPLICIT_USER_OPT_IN`; its
reasoning effort is selected by the user/session (for example Low or Medium). It is
never auto-selected or auto-escalated for difficulty, conflict, review, HEAVY work,
ambiguity, or disagreement, and effort never escalates automatically.

Do not reset, clean, rewrite history, force-push, rebase, merge, delete branches,
or push without authorization. Stage only the task's files. A completed, validated,
coherent implementation may receive one local commit unless the user requested an
uncommitted review or unrelated changes cannot safely be excluded.

The runtime selects policy, never guessed model identity: legacy Luna profiles
select `LUNA_ROOT` and `$luna-orchestra`; explicit `global-gpt6-luna` selects
`GPT6_LUNA_ROOT` and `$luna-orchestra`; explicit `global-gpt6-sol` selects
`GPT6_SOL_ROOT` and `$sol-orchestra`; an explicitly selected `global-astra-low`,
`global-astra-medium`, or backward-compatible `global-astra` profile selects
`ASTRA_ROOT` and `$astra-decision-orchestrator`.
`LUNA_WORKER` follows its bounded assignment and loads neither root skill. Load
only the selected root skill. All configured worker roles stay pinned to GPT-6
Luna Max in every root profile. Resolve conflicting markers through session
configuration before delegation; do not infer Astra from task difficulty or
disagreement.

Prefer one visible MAIN with internal/local workers. MAIN owns final judgment and
integration. Workers never self-upgrade, spawn nested workers, merge, rebase, or
force-push. For delegation, use the configured `default`, `explorer`, or `worker`
roles and omit spawn-level `model` and `reasoning_effort` overrides. Verify the
effective role metadata is GPT-6 Luna Max. A custom agent file or explicit spawn
value can override the global default; use a custom role only after verifying its
effective model and effort are also GPT-6 Luna Max. If any pin is absent or
contradictory, work directly and report the gap instead of assuming it.

Project-local instructions extend these rules; stronger project constraints control
over orchestration preferences. Installed policy is self-contained: do not fetch
a policy repository at session startup.

Context notes are convenience state. Actual repository/immutable artifacts outrank
authoritative project checkpoints, then current task evidence, then context notes.
Verify stale notes against actual state before relying on them.
