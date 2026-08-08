# Task registry

Only MAIN changes task ownership, dependencies, model routing, or status.

| Task ID | Owner | Scope | Model / reasoning | Base source commit | Branch/worktree | Dependencies | Status |
|---|---|---|---|---|---|---|---|
| IDX-DATA-002 | DATA | Verify the current source, run the full pytest suite, exercise official IDX Exchange-Day extraction, execute auditable Yahoo EOD backfill for the adversarial catalog, and execute official IDX identity/tradability ingestion where sources are available; emit artifacts/provenance/unresolved gaps; no modelling | Luna xhigh / xhigh | `3a7d7d4a` | isolated DATA worktree | current data foundation | READY |
| IDX-VAL-002 | VALIDATION | Independently audit official-session artifacts, announcement-history completeness evidence, official snapshot reconciliation, corporate-action/raw-price verification, and adversarial DATA GATE outputs | Luna xhigh / xhigh | `3a7d7d4a` | read-only or isolated VALIDATION worktree | IDX-DATA-002 artifacts | BLOCKED_ON_DATA |
| IDX-DATA-003 | DATA | Run full point-in-time universe gate only after adversarial QA passes; determine clean candidate research period | Luna xhigh / xhigh | `<post IDX-DATA-002/VAL-002 integration>` | isolated DATA worktree | adversarial gate PASS | BLOCKED_UNTIL_GATE |
| IDX-SOL-001 | VALIDATION | Bounded independent pre-model DATA GATE certification | Sol High | `<frozen data-gate candidate>` | read-only | full-universe gate candidate | BLOCKED_UNTIL_FULL_GATE |
| IDX-MODEL-001 | RESEARCH / EXPERIMENT | Define/freeze setup/SR target, horizon, probability and evaluation protocol; no training until user/MAIN promotion | Luna xhigh by default | `<future>` | future isolated worktree | DATA GATE PASS + user promotion | BLOCKED_UNTIL_GATE |

Known constraint: the public IDX announcement page exposes only three years of announcement data and points older history to TICMI. IDX-DATA-002 must not claim older free-only tradability completeness without independent official/licensed evidence.

Do not create modelling workers merely because DATA workers are idle. The current critical path is DATA -> VALIDATION -> full gate -> independent certification.
