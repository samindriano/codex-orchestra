# Decision log

| ID | Decision | Reason |
|---|---|---|
| BIO-D-001 | Use a dedicated Biohub repository and keep competition data external. | Prevent cross-project contamination and accidental data commits. |
| BIO-D-002 | Defer full archive extraction; begin with one bounded train sample. | The archive and extracted data together would consume most free D: space. |
| BIO-D-003 | Use a modular detector -> tracker -> division pipeline first. | Labels are centroids/edges and modular diagnostics match the scoring components. |
| BIO-D-004 | Validate by embryo identity only. | Samples from the same embryo are correlated and hidden test embryos are disjoint. |
| BIO-D-005 | Require official evaluator parity before model optimization. | Sparse-label and count-adjustment details can reverse experiment conclusions. |
| BIO-D-006 | Pin the organizer metric at commit `075fc5f5a52d11077f9dc2b074644618f26939e2`. | Metric behavior and dependencies may change; experiments need immutable scoring provenance. |
| BIO-D-007 | Treat missing annotation as unknown and never manually synthesize missing GT. | The official sparse metric ignores predictions without evaluable GT evidence and the organizer baseline ignores unannotated cells during training. |
| BIO-D-008 | Freeze two leave-one-embryo-out folds: `44b6` and `6bba`. | The 199 train datasets contain only two embryo identities, so any sample-level or frame-level split would leak embryo-specific structure. |
| BIO-D-009 | Gate G3 with one division-bearing sample per embryo before full-fold execution. | This proves the complete detector-to-division path while avoiding an unnecessary 87 GB extraction and exposes the strong annotation-density shift between embryos. |
| BIO-D-010 | Accept `baseline_v0` as the deterministic G3 engineering reference, but do not promote it as a competitive model. | The full detector-to-tracker-to-division path, submission schema, pinned metric, runtime, and memory checks reproduce; however, the `6bba` smoke window has raw edge Jaccard `0.500000` and division Jaccard `0.000000`, and the window count adjustment is only approximate. |
| BIO-D-011 | Target detection first in G4 and keep tracking and division frozen. | Representative-panel node recall is only 0.375/0.392 by embryo, while oracle-node non-division edge Jaccard is 0.977690; changing association first has lower expected value and would confound diagnosis. |
| BIO-D-012 | Preregister `g4-adaptive-log-otsu-v0` as the only G4 design submitted for independent review. | A single parameter-free feasibility probe improves panel recall to 0.750/0.976 and count ratio to 0.916/1.067 using only image metadata available at hidden-test inference. Full evaluation and any parameter rescue remain prohibited until review and implementation. |
| BIO-D-013 | Lock `g4-adaptive-log-otsu-v0` for implementation after independent `APPROVE`. | The repaired contract is image-only and bit-exact, preserves the G3 tracker/division logic, freezes all-199 aggregation and acceptance gates, and resolves every review blocker. This approves design implementation only; it does not claim a G4 score improvement. |
| BIO-D-014 | Accept the G4 implementation for frozen evaluation, but do not promote the challenger. | Independent review, 18 focused tests, exact two-pass panel fingerprints, and a valid four-video submission smoke pass. No full-199 official metric has been viewed, so scientific and runtime acceptance remain undecided. |
