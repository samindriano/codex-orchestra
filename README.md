# Codex Orchestra

A versioned, offline-installable global foundation: GPT-5.6 Luna XHigh is the
normal global root and worker tier. Astra remains a manual experimental profile;
the user selects its reasoning effort explicitly. Optimize useful verified work per
constrained resource, subject to correctness and user intent.

## Architecture

```text
codex-orchestra (reviewed source)
  -> explicit local install
  -> CODEX_HOME: small AGENTS + profiles + skills + pinned worker roles
  -> new generic session, or global rules + project-local overlay
```

The repository's AGENTS governs development. `policies/GLOBAL_AGENTS.md` is the
installed global artifact. Runtime profiles select model and policy together;
there is no model introspection, conditional AGENTS syntax, or startup Git fetch.

| Profile | Root | Policy skill | Workers |
|---|---|---|---|
| normal global default | gpt-5.6-luna / xhigh | luna-orchestra | Luna xhigh |
| global-luna | gpt-5.6-luna / xhigh | luna-orchestra | Luna xhigh |
| global-astra-low (manual experimental, explicit opt-in) | gpt-6-astra / low | astra-decision-orchestrator | Luna xhigh |
| global-astra-medium (manual experimental, explicit opt-in) | gpt-6-astra / medium | astra-decision-orchestrator | Luna xhigh |
| global-astra (backward-compatible Medium alias) | gpt-6-astra / medium | astra-decision-orchestrator | Luna xhigh |

DIRECT means one useful frontier, even for a difficult problem. LIGHT means roughly
1–2 delegated lanes; HEAVY roughly 3–5, within runtime limits. Width does not select
model intelligence or escalate to Astra. Difficulty, conflict, review, HEAVY work,
ambiguity, and disagreement never auto-select Astra. Astra is decision-first but
manual-only; Luna launches useful independent work more readily. Neither mode
forces fan-out. The skills contain their own policies; `orchestrate` is only a
compatibility router.

## Install and verify

Requires Python 3.11+ (standard library) and a Codex build supporting separate
`<name>.config.toml` profiles, custom role files, and subagent model defaults.
From this repository in PowerShell:

```powershell
python scripts/global_policy.py install --dry-run
python scripts/global_policy.py install
python scripts/global_policy.py verify
```

For a runtime that has been checked to support the exact experimental context key:

```powershell
python scripts/global_policy.py install --enable-context-management --dry-run
python scripts/global_policy.py install --enable-context-management
python scripts/global_policy.py verify --require-context-management
```

The installer resolves CODEX_HOME from the environment or the user's home. It copies
owned files, preserves unrelated settings, backs up existing files before changes,
and records installed hashes. It uses no symlinks or runtime repository dependency.
Review changed paths before applying; rerunning an unchanged install is a no-op.
Backups may contain private configuration and must remain local. To undo, inspect
the backup manifest and restore only affected files; remove newly created files
only when they still match installed hashes. Do not blindly restore an old entire
config after later user edits.

## Launch

For the normal Luna default, start a fresh session with the installed configuration.
For a manual Astra experiment, explicitly select the effort profile:

```powershell
codex
codex --profile global-astra-low
codex --profile global-astra-medium
codex --profile global-astra
codex --profile global-luna
```

The unprofiled global configuration is Luna XHigh. Start a fresh session when
switching root families. Do not combine the Astra profile with `--model` selecting
Luna, or the reverse. Astra Low and Astra Medium are explicit session/profile
choices; neither escalates automatically. During a requested bootstrap test the root
may print a one-line mode marker; ordinary tasks need no bootstrap ceremony.

Profiles sit below project and CLI overrides. Projects overriding model or developer
instructions must keep model/policy paired. The desktop model picker alone is not
a verified profile selector; unprofiled sessions use global safety with DIRECT
fallback. Use the profiled CLI for the initial reproducible experiment.

## Worker enforcement

The top-level `model` and `model_reasoning_effort` provide the normal Luna/xhigh
root default. `agents.default_subagent_model` and
`default_subagent_reasoning_effort` provide Luna/xhigh worker defaults. The three
built-in role names are overridden by standalone
files in `agents/`, each pinning both values. Role settings take precedence over
spawn values. Each role sets `agents.enabled=false` to disable nested delegation
and replaces the root marker with LUNA_WORKER. Custom project roles can override
personal roles, so MAIN must check exposed role metadata before delegation.

This is runtime configuration, not an account-wide ban: another session, a config
edit, or a new unpinned custom role can bypass these defaults. No Astra worker is
allowed by the normal policy. If pinning is unavailable, stay DIRECT and report it.

## Capabilities and evidence

See [runtime acceptance](docs/runtime-acceptance.md) for installed-version evidence,
profiles, probes, and limitations; [instruction hierarchy](policies/instruction-hierarchy.md)
for precedence; and [trial checklist](docs/trial-checklist.md) for quota experiments.
The exact context option is experimental; parsing and clean startup do not prove
long-session quota savings or recovery quality.

Old project branches remain snapshots. Do not copy this repository's development
AGENTS or old snapshot policies into a project. Optional `coordination/` templates
are project conveniences, never required session context or installed global policy.

## Project overlays

Keep repository commands, ownership, domain constraints, approval gates, provenance,
and authoritative state locations in the project's AGENTS. Refer to the global
runtime-selected orchestration skills rather than duplicating their text. Preserve
all stronger existing restrictions during migration; use a separate reviewed task.
No project repository is modified by this installer.

## Development

```powershell
python -m unittest discover -s tests -v
git diff --check
```
