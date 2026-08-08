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

## Source of truth

- **Primary source commit:** `<sha>`
- **Reference repositories:** `<optional>`
- **Protected/legacy sources:** `<optional>`
- **Runtime data/artifact policy:** `<what must remain outside Git>`

## Model policy

The user may override this at any time.

- **Root default:** `<cost-efficient strong model, e.g. Luna xhigh>`
- **Worker default:** `<usually same as root>`
- **Escalation model:** `<optional stronger model, e.g. Sol High>`
- **Escalation triggers:** `<architecture conflict / repeated failure / final gate / other>`
- **Independent external reviewer:** `<optional ChatGPT/research thread or NONE>`

## Orchestration policy

- **DIRECT:** `<project examples>`
- **LIGHT:** `<project examples>`
- **HEAVY:** `<project examples>`
- **Maximum concurrent writers:** `<n>`
- **Nested workers:** `PROHIBITED`

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

No downstream phase is authorized merely because a worker completed its task.
MAIN records phase transitions in `DECISIONS.md`.

## Frozen decision-changing terms

List terms that may not be changed after the relevant gate without explicitly
invalidating/restarting evaluation, for example:

- target/objective definition;
- data/source contract;
- evaluation split/holdout;
- acceptance metrics and thresholds;
- runtime/resource budget;
- deployment/output contract.

## Stop conditions

Stop and return to MAIN on:

- missing provenance or ambiguous source state;
- ownership conflict or dirty worktree that threatens unrelated changes;
- unauthorized credentials/network/data access;
- failed required validation;
- need to change a frozen decision-changing term;
- evidence that invalidates the current task premise.
