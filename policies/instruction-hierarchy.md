# Instruction and evidence hierarchy

System and runtime instructions retain native authority. Within user/project
guidance, explicit task constraints control over generic workflow preferences.
Global AGENTS provides invariants; project AGENTS adds domain-specific rules.
Profiles inject a root marker and select exactly one operating skill. Worker role
files replace root policy instructions with LUNA_WORKER and disable nested agents.
A project may strengthen constraints without copying these skills.

Evidence precedence is actual repository / immutable artifacts, then authoritative
project checkpoints, current task evidence, and finally notes. Notes can locate
evidence; they cannot certify current state or authorize changes.

The normal global configuration default is GPT-5.6 Luna XHigh for the root and
Luna XHigh for workers. Profiles are below project and CLI configuration in native
precedence. The `global-astra-low` and `global-astra-medium` profiles are
`MANUAL_EXPERIMENTAL` and `EXPLICIT_USER_OPT_IN`; the backward-compatible
`global-astra` alias means Medium. The selected profile supplies Astra's effort
and its workers remain Luna XHigh; effort never escalates automatically. A project
or explicit override can change a model or developer instructions. Inspect effective
configuration when an overlay changes those keys. Never combine one family's
profile with a different family via `--model`; start a fresh matching profile.
Same-family reasoning overrides keep the same policy.

DIRECT, LIGHT, and HEAVY are width choices, not escalation rules. Difficulty,
conflict, review, HEAVY work, ambiguity, and disagreement never auto-select Astra.

No automatic model-conditional AGENTS syntax is used. Unprofiled sessions use the
normal Luna XHigh global default and global safety/skill discovery. The desktop
model picker alone is not a verified profile selector. Use `global-astra` only as
an explicit manual experiment and use CLI profiles for reproducible routing.
