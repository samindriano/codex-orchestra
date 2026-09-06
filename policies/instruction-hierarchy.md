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

Profiles are below project and CLI configuration in native precedence. A project
or explicit override can change a model or developer instructions. Inspect effective
configuration when an overlay changes those keys. Never combine one family's profile
with a different family via `--model`; start a fresh matching profile. Same-family
reasoning overrides keep the same policy.

No automatic model-conditional AGENTS syntax is used. Unprofiled desktop sessions
receive global safety and skill discovery but no inferred model-specific policy.
The desktop model picker alone is not a verified profile selector. Use CLI profiles
for reproducible routing during this experiment.
