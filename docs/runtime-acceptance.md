# Runtime acceptance — 2026-09-06

This is a bounded local installation acceptance record, not a performance benchmark.

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

Independent read-only policy review: APPROVE. A hard sequential Astra decision
stays DIRECT; Luna with two independent ready lanes may use LIGHT. Root model and
worker count remain separate. Skill frontmatter validation passed for all three
skills, including the compatibility router.

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

## Installed acceptance results

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

Fresh tasks emitted existing plugin-icon and Cloudflare MCP OAuth warnings. These
were not changed or repaired by this task. Exit-zero model/skill acceptance should
not be described as an entirely warning-free environment. The project's no-network
rule governs agent actions; connector initialization may still make runtime-level
requests and is not a network sandbox.
