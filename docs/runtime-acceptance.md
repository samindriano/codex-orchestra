# Runtime acceptance — 2026-09-06

This is a bounded local installation acceptance record, not a performance benchmark.
The normal global default is now GPT-5.6 Luna XHigh; Astra Low and Medium are
manual experimental profiles requiring explicit user opt-in.

- Initial terminal CLI: 0.150.1. Profiles already use separate name.config.toml files.
- Initial desktop engine: 0.153.1. The desktop independently updated to 0.153.4
  during the resumed task; both newer versions accept the exact context setting.
- The npm CLI was aligned to 0.153.1 with `npm install -g @openai/codex@0.153.1`.
  The old 0.150.1 rejects the nested context feature value; do not use it with this
  experiment enabled. npm left a locked old binary copy; no active process was killed.
- Actual model catalogs in 0.153.1 include gpt-6-astra with medium and
  gpt-5.6-luna with xhigh. Root rollout turn_context metadata confirms Astra medium.
- Custom default, explorer and worker roles pin Luna/xhigh. The runtime's threads
  database links a real explorer child to the Astra parent and records Luna/xhigh;
  the child's rollout turn_context independently agrees. This predates installation
  of the new worker instructions but uses the same model/effort role mechanism.
- Isolated dry prompt discovery passed for both profiles: model-specific developer
  policy marker, global AGENTS and skills are discovered. The no-project prompts
  contain no IDX-Trade, Stockbit, ZAPI or TEAM_STATUS instructions.
- `--strict-config doctor --json -c features.context_management.experimental_mode=true`
  reports config.load=ok. Doctor's overall status is not claimed as passing: the
  noninteractive harness has TERM=dumb. Configuration acceptance is distinct from
  that terminal UI diagnostic.

The earlier independent read-only policy review remains applicable to the width
semantics: a hard sequential task stays DIRECT and two independent ready lanes may
use LIGHT. Root model and worker count remain separate. Under the revised policy,
Astra is manual-only and no difficulty, conflict, review, HEAVY work, ambiguity, or
disagreement auto-escalates the root.

## Sources and interpretation

The installed runtime help and metadata are the primary compatibility evidence.
Official documentation confirms [separate profile layers](https://learn.chatgpt.com/docs/config-file/config-advanced),
[custom role precedence and subagent defaults](https://learn.chatgpt.com/docs/agent-configuration/subagents),
and the [exact context key](https://learn.chatgpt.com/docs/config-file/config-reference).

Profiles are below project and CLI overrides. The desktop model picker alone is
not verified to apply these CLI profiles. Fresh profiled CLI sessions are the
reproducible experiment entrypoint. Config pinning is not an account-level policy:
new custom roles or explicit configuration changes can bypass it.

Context management is experimental and account/rollout dependent. Enabled config,
accepted tools and a clean fresh task do not establish long-context recovery quality
or quota benefit. Use the trial checklist to observe that separately.

## Prior installed acceptance results

- Installer regression suite: 11 tests passed, including concurrent config-edit
  preservation. `git diff --check` passed.
- Installation and `verify --require-context-management`: PASS. All ten managed
  files verified. Second dry-run: no changes. Backup hashes verified.
- Original config bytes are an unchanged prefix of the installed config; removing
  only the newly added context feature yields exact original TOML values.
- Global AGENTS reduced from 15,710 bytes to 1,927 bytes. Installed-home prompt
  discovery also passed with zero tested project-domain markers.
- Astra fresh task `01a07743-b98c-74d2-bf17-fc19337cf736`: exit 0,
  ASTRA_ROOT bootstrap, selected astra-decision-orchestrator skill. Thread metadata
  and rollout turn_context record gpt-6-astra / medium.
- Its explorer child `01a07744-0e42-7ce0-973d-6c7b06a83e8b`: actual parent linkage,
  role explorer, gpt-5.6-luna / xhigh in both thread metadata and rollout context.
  It completed the trivial read-only task (2+2=4). This verifies post-install pinning.
- Luna fresh task `01a07743-b1e5-70d0-8f11-2c40ec334692`: exit 0,
  LUNA_ROOT bootstrap, selected luna-orchestra skill. Metadata records Luna/xhigh.
  It recognized the temporary project's LOCAL_ONLY canary and restrictions on
  network/delegation. Protected file content stayed unchanged.
- Context feature reports enabled in the installed config and runtime. Both fresh
  tasks started and completed with it enabled; long-context recovery and quota
  benefits remain unmeasured.
- A later Luna XHigh context capture initially found the host Python environment
  had no usable temporary directory, so its first test rerun errored before setup.
  Re-running with `TEMP`, `TMP`, and `TMPDIR` set to a writable workspace temp
  directory passed all 11 tests. This was an environment issue, not a test or
  installer failure; the repository remains clean.

Fresh tasks emitted existing plugin-icon and Cloudflare MCP OAuth warnings. These
were not changed or repaired by this task. Exit-zero model/skill acceptance should
not be described as an entirely warning-free environment. The project's no-network
rule governs agent actions; connector initialization may still make runtime-level
requests and is not a network sandbox.

## Revised-policy continuation

- The source policy now makes the normal global root and workers GPT-5.6 Luna
  XHigh. Astra Low and Medium are `MANUAL_EXPERIMENTAL` /
  `EXPLICIT_USER_OPT_IN`; the existing `global-astra` profile remains a
  backward-compatible Medium alias. All delegated workers remain Luna XHigh.
- Focused installer regression suite: 12 tests passed with `TEMP`, `TMP`, and
  `TMPDIR` set to the writable `work\test-temp` directory.
- `python -m py_compile scripts/global_policy.py tests/test_global_policy.py` and
  `git diff --check` passed.
- An isolated writable-home install followed by `verify --require-context-management`
  passed and reported `model="gpt-5.6-luna"`, `model_reasoning_effort="xhigh"`,
  Luna/xhigh worker defaults, and `context_management_enabled=true`.
- The final read-only state of the requested real-home installation is PASS. It
  created the timestamped backup
  `C:\Users\Sam\.codex\orchestra-backups\20260906T152830942033Z`, with manifest
  `C:\Users\Sam\.codex\orchestra-backups\20260906T152830942033Z\manifest.json`,
  and installed the revised source policy, profiles, skills, and Luna root defaults.
  `verify --require-context-management` passed against the real home.
- The installed real config now reports `model="gpt-5.6-luna"`,
  `model_reasoning_effort="xhigh"`, Luna/xhigh worker defaults, and
  `context_management_enabled=true`; existing `personality`, plugin settings,
  project trust entries, and other unowned settings were preserved.
- The first synchronous attempt returned `WinError 5` while creating a backup path;
  the later complete manifest and current hashes are authoritative, while the
  delayed completion mechanism remains UNKNOWN.
- A fresh Luna profile bootstrap was not run under the no-network constraint;
  installed file/config verification passed instead.

## Astra effort-profile refinement — 2026-09-07

- Starting commit: `162a24f feat: make Luna the global orchestration default`.
- Added `global-astra-low` (`gpt-6-astra` / `low`) and
  `global-astra-medium` (`gpt-6-astra` / `medium`). The existing
  `global-astra` profile remains a backward-compatible Medium alias. Each profile
  carries the manual opt-in markers and keeps workers on Luna XHigh.
- The installer now treats all three Astra profiles as canonical managed files.
  Real-home installation passed and created backup
  `C:\Users\Sam\.codex\orchestra-backups\20260907T002833063216Z` with its
  manifest. `verify --require-context-management` passed; the second dry run
  reported `changed_files=[]` and context management remained enabled.
- Installer regression suite: 13 tests passed. Skill validators for Astra,
  Luna, and the compatibility router passed. Python compilation and
  `git diff --check` passed.
- `codex exec --profile global-astra-low --help`,
  `global-astra-medium --help`, `global-astra --help`, and
  `global-luna --help` all exited zero on Codex 0.153.1. No Astra task was
  launched solely for this configuration check, so Low/Medium live model metadata,
  quota economics, and quality remain UNKNOWN until bounded user-directed trials.
