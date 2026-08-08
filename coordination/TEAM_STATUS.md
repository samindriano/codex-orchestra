# Team status

- **Phase:** `G4_IMPLEMENTATION_ACCEPTED`
- **Operating mode:** `RESEARCH_COMPETITION_ONLY`
- **Canonical repository:** dedicated Biohub repository
- **Competition data:** external archive discovered; full extraction deferred
- **G0 FORMAT:** `PASS_BOUNDED_SAMPLE`
- **G1 METRIC:** `PASS_PINNED_OFFICIAL_83_TESTS`
- **G2 SPLIT:** `PASS_FROZEN_TWO_EMBRYO_FOLDS`
- **G3 BASELINE:** `PASS_BOUNDED_TWO_EMBRYO_SMOKE`
- **G4 CHALLENGER:** `IMPLEMENTATION_ACCEPTED_NOT_SCORED`
- **G5 RUNTIME:** `NOT_RUN`
- **G6 SUBMISSION:** `PASS_FOUR_EXAMPLE_DATASETS_HIDDEN_NOT_RUN`
- **Best baseline:** `baseline_v0` (engineering smoke only; not unbiased CV)
- **Best candidate:** `g4-adaptive-log-otsu-v0` (`IMPLEMENTED_NOT_EVALUATED`)
- **Sparse-label policy:** `LOCKED_UNANNOTATED_IS_UNKNOWN`
- **Validation structure:** 199 train datasets, 2 embryos; fold 0 is 71 `44b6`
  samples and fold 1 is 128 `6bba` samples.
- **Foundation validation:** organizer metric suite `83_TESTS_PASS`; local
  suite and exact `1.1` sanity PASS; official sample submission PASS.
- **Bounded G3 evidence:** deterministic rerun PASS. `44b6_d754aa59 [60,67)`
  smoke score `1.131486` (raw edge Jaccard `1.000000`, division Jaccard
  `1.000000`); `6bba_705ec2c9 [39,46)` smoke score `0.519515` (raw edge
  Jaccard `0.500000`, division Jaccard `0.000000`). Approximate window count
  adjustment makes these engineering diagnostics, not leaderboard estimates.
- **G4 diagnosis:** representative-panel node recall is `0.375` for `44b6`
  and `0.392` for `6bba`; oracle-node non-division edge Jaccard is `0.977690`.
  Detector thresholding is the first target. The single adaptive log-Otsu
  feasibility probe raises panel recall to `0.750` and `0.976` without using
  training-only count metadata at inference.
- **G4 design review:** `APPROVE`. The final contract fixes canonical node
  indexing, bit-exact Otsu behavior, image-only inference, GEFF load order,
  full-199 aggregation, runtime/resource evidence, submission coverage, and
  no-rescue rules. Archive verification found the required nested quantiles in
  all 203 train/test image roots. Local suite: `31 passed`.
- **G4 implementation review:** `APPROVE_IMPLEMENTATION_ONLY`. Focused tests
  `18 passed`; full worktree suite `47 passed, 2 skipped` because the isolated
  worktree does not contain the ignored official-metric checkout. The frozen
  18-frame panel reproduced exactly twice: 5,329 nodes, 0 nonconsecutive-frame
  edges, and identical per-dataset fingerprints.
- **Four-example submission smoke:** exact datasets PASS, `255,858` rows
  (`137,057` node and `118,801` edge), runtime `444.241s`, peak RSS
  `303.844 MB`, CSV SHA-256
  `16a50f9fd3ff060af8fb63f157cdc99499aca77d32c94e30410abefa6aaedca0`.
  The disposable CSV was deleted and no artifact entered Git.
- **Next action:** implement and review the frozen all-199 G3/G4 evaluation
  runner with `Luna` reasoning `xhigh`, then execute once in the preregistered
  order. MAIN uses `Sol` reasoning `xhigh` for the scientific accept/reject
  decision. No design, gate, or parameter changes are allowed.
