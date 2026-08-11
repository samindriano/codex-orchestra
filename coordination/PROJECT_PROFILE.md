# Project profile

Only MAIN edits this file. Replace placeholders before delegating project work.

## Identity

- **Project ID:** `<project-id>`
- **Project name:** `<project-name>`
- **Primary repository:** `<owner/repo or absolute local path>`
- **Integration branch:** `main`
- **Operating mode:** `<research / engineering / competition / production>`
- **Objective:** `<one-sentence objective>`
- **Explicitly out of scope:** `<items>`

## Source of truth and status sync

- **Primary source branch:** `<branch>`
- **Primary source commit:** `<sha>`
- **Authoritative status document:** `<path, e.g. docs/CURRENT_STATUS.md>`
- **Reference repositories:** `<optional>`
- **Protected/legacy sources:** `<optional>`
- **Runtime data/artifact policy:** `<what must remain outside Git>`
- **Last orchestra sync source commit:** `<sha>`
- **Last orchestra sync time:** `<UTC timestamp>`
- **Snapshot freshness:** `CURRENT | STALE`

If this profile conflicts with the authoritative source repository/status document, the source repository wins and this snapshot becomes `STALE` until refreshed.

## Optimization objective

- **Primary orchestration objective:** `REDUCE_WALL_CLOCK_TIME_WITHOUT_WEAKENING_GATES`
- **Default meaningful-task topology:** `LIGHT`
- **Maximum useful concurrent workers:** `<n, typically 3 for LIGHT and 6 for HEAVY>`
- **Maximum concurrent writers:** `<n>`
- **Nested workers:** `PROHIBITED`

MAIN must run the parallelism preflight before substantial implementation and must not retain independent critical-path work merely because MAIN can perform it alone.

## Model policy

The user may override this at any time.

- **Root default:** `<cost-efficient strong model, e.g. Luna xhigh>`
- **Worker default:** `<usually same as root>`
- **Escalation model:** `<optional stronger model, e.g. Sol High>`
- **Escalation triggers:** `<architecture conflict / repeated failure / final gate / other>`
- **Independent external reviewer:** `<optional ChatGPT/research thread or NONE>`

Model strength and worker count are separate decisions. Prefer safe concurrency for latency reduction before persistent premium-model use.

## Orchestration policy

- **DIRECT:** `<small/sequential examples; substantial DIRECT requires rationale>`
- **LIGHT:** `<normal meaningful project examples with 2-3 ready workstreams>`
- **HEAVY:** `<project examples with 3-6 independent critical-path workstreams or independent review>`
- **Spawn-before-work rule:** `ENABLED`
- **MAIN-hoarding rule:** `PROHIBITED_FOR_INDEPENDENT_CRITICAL_PATH_WORK`

### Project-specific parallelism guardrails

- **Safe parallel dimensions:** `<e.g. implementation / tests / audit / frontend / backend>`
- **Must remain sequential:** `<e.g. experiment B depends on result of experiment A>`
- **Shared resources that limit concurrency:** `<e.g. one GPU/cache/DB/locked dataset>`

## Roles and ownership

| Role | Owned scope | Write access |
|---|---|---|
| `<ROLE_1>` | `<scope>` | `<paths or read-only>` |
| `<ROLE_2>` | `<scope>` | `<paths or read-only>` |

MAIN owns root orchestration and shared coordination files.

## Gates

| Gate | Requirement | Current status |
|---|---|---|
| G0 | `<foundation/readiness requirement>` | `NOT_EVALUATED` |
| G1 | `<validation requirement>` | `NOT_EVALUATED` |
| G2 | `<promotion/release requirement>` | `NOT_EVALUATED` |

No downstream phase is authorized merely because a worker completed its task. MAIN records phase transitions in `DECISIONS.md`.

## Frozen decision-changing terms

List terms that may not be changed after the relevant gate without explicitly invalidating/restarting evaluation, for example:

- target/objective definition;
- data/source contract;
- evaluation split/holdout;
- acceptance metrics and thresholds;
- runtime/resource budget;
- deployment/output contract.

## Stop conditions

Stop and return to MAIN on:

- source snapshot marked stale and the task depends on stale project state;
- missing provenance or ambiguous source state;
- ownership conflict or dirty worktree that threatens unrelated changes;
- unauthorized credentials/network/data access;
- failed required validation;
- need to change a frozen decision-changing term;
- evidence that invalidates the current task premise.
