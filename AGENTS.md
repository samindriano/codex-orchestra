# Biohub Cell Tracking working agreement

## Objective

Build a reproducible research pipeline that converts 3D+time microscopy
volumes into a graph of cell detections and temporal links, including cell
division branches, and produces a valid Kaggle `submission.csv` within the
12-hour notebook limit.

## Non-negotiable research rules

- Do not fabricate detections, scores, runtime evidence, or model state.
- Treat unannotated cells as unknown, not automatically as background.
- Group validation by embryo identity (the prefix before the first `_`).
- Compute geometry in physical micrometers using z/y/x scales
  `1.625/0.40625/0.40625`, not raw voxel Euclidean distance.
- Reproduce the official sparse-label evaluator before optimizing models.
- Keep the hidden test and leaderboard out of model-selection decisions.
- Freeze folds, seeds, metric implementation, acceptance gates, and runtime
  budget before comparing challengers.
- Do not rescue a failed candidate by changing thresholds or folds after
  holdout inspection.
- Keep the 81+ GB competition data outside Git and read it in place.
- Never commit credentials, user-specific paths, raw volumes, model weights,
  predictions, caches, or generated artifacts.

## Orchestration

The parent thread is `MAIN`, the sole control plane and integrator. It chooses
DIRECT, LIGHT, or HEAVY adaptively, delegates only concrete non-overlapping
work, verifies every handoff, and records final decisions.

| Role | Owned scope |
|---|---|
| DATA_FORMAT | Zarr/GEFF readers, schema, physical coordinates, bounded inventory |
| METRIC_VALIDATION | official evaluator parity, embryo folds, diagnostics, leakage checks |
| VISION_DETECTION | center detection, heatmaps, count calibration, detector experiments |
| TRACKING_DIVISION | association, graph optimization, gap handling, division branches |
| NOTEBOOK_QA | submission contract, offline dependencies, runtime and memory checks |

- Read-only workers may share the canonical checkout.
- Concurrent writers require isolated worktrees and disjoint file ownership.
- Workers never spawn workers and never integrate their own branches.
- MAIN does not repeat a completed audit unless evidence or code changed.
- Independent review is reserved for evaluator certification, major
  architecture decisions, suspicious breakthroughs, and final candidates.

Every delegated task must define the exact repository/worktree, role,
question, allowed and prohibited changes, deliverables, verification, and
handoff dependency.

## Research gates

| Gate | Requirement |
|---|---|
| G0 FORMAT | Zarr/GEFF and submission schemas read deterministically |
| G1 METRIC | official node, edge, division, sparse-label, and count adjustment reproduced |
| G2 SPLIT | embryo-disjoint folds frozen with no sample/frame leakage |
| G3 BASELINE | deterministic detection-to-graph baseline reproduced end to end |
| G4 CHALLENGER | candidate improves frozen gates across embryos, including worst embryo |
| G5 RUNTIME | hidden-test-sized notebook completes offline within 12 hours |
| G6 SUBMISSION | CSV integrity, dataset coverage, node references, and output path pass |

Model work is blocked until G0-G2 pass. Promotion is blocked until G3-G6 pass.

## Handoffs

Every delegated task concludes in `coordination/handoffs/<task-id>-<role>.md`:

```text
# Handoff
from:
to:
task_id:
source_repository:
source_commit:
branch:
head_commit:
scope:
files_changed:
findings:
decisions_made:
decisions_needed:
blocking_risks:
validation_run:
recommended_next_action:
```

## Reporting

For meaningful updates, report in this order:

1. Work type: DIRECT, LIGHT, or HEAVY.
2. Bottom line in plain language.
3. What was done and why.
4. Metrics with interpretation, including component and worst-embryo results.
5. Decision: ACCEPT, REWORK, REJECT, INCONCLUSIVE, or BLOCKED.
6. Highest-value next action.
7. Technical details, files, commit, tests, and caveats.
