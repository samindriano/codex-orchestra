# Recorded Orchestra turn telemetry review

**Snapshot cutoff:** latest ledger event `2026-09-24T08:59:08Z` UTC on 2026-09-24.

**Unit:** one Codex turn per row. **Audience:** model/research review.
This public artifact contains normalized telemetry only, not conversation content.

## Executive readout

- **221 turn rows** across **25 pseudonymous sessions**, starting 2026-09-22T06:33:47Z through 2026-09-24T08:57:46Z (UTC).
- **193 COMPLETED, 16 INTERRUPTED, 12 STARTED** at the cutoff. STARTED means no finalizer existed in this snapshot; it does not prove the turn was still active.
- Root models: gpt-5.6-luna 42, gpt-5.6-terra 4, gpt-6-luna 163, gpt-6-sol 12. Root reasoning effort is **UNKNOWN for every turn**; historical XHigh/Max cannot be verified.
- Root usage is exact on **194/221 turns**: **1,040,701,046 tokens**. Worker usage is **3,233,352 tokens across 3 turns** under the installed fold, but the repository-documented edge contract certifies **216,827 tokens across 2 turns**.
- The complete root-plus-worker total for all turns remains **UNKNOWN**. The documented contract has exact full Orchestra totals for only **2 turns: 21,541,437 tokens**.
- Per-turn start/finalizer times exist. Median hook-to-hook elapsed time is **423 seconds** across 209 finalized turns; this includes tool/idle time and is not active model-generation time.
- Material review issue: installed collector and checked-in template differ, and the installed fold accepts a worker turn without an edge required by the repository contract.

## Snapshot integrity and provenance

- Ledger: **714 records**, 1,203,055 bytes, SHA-256 `11cf19f9ce5b6e78ee186560ca2e53d81ec1a8e9022a73dc6ca7d351f83782bf`.
- Unique record IDs: 714; duplicate record IDs: 0; duplicate JSONL lines: 0; final line terminated: yes.
- Latest ledger event: **2026-09-24T08:59:08Z**; latest turn start: **2026-09-24T08:57:46Z**.
- All turn rows use `TURN_LEVEL_V1_2`; turn identity pairs: 221.
- Counts by record type:

| Record type | Count |
|---|---:|
| `turn_start` | 221 |
| `worker_edge_observed` | 2 |
| `worker_observed` | 5 |
| `usage_observed` | 213 |
| `turn_finalize` | 209 |
| `session_observed` | 48 |
| `interruption_observed` | 16 |

The ledger was read-only. Each exported chunk was checked against the same ledger SHA-256. Folding/validation used the installed collector (SHA-256 `ec67e887dcb07ee07f513e839fb4c9f342d04a6c14a3307f446d6e7c9734a35f`, 138,469 bytes). The checked-in template at base commit `52e9a372724d864624b5b2ba29e3e72f7f68ee5b` is SHA-256 `587fc563bbaa56bc32643b735adedefd8a9ad56e65a678927f76a9f8348b230d` (45,728 bytes). They differ. The checked-in parser rejects fields present in the captured ledger (`boundary_source`, `economics`, `execution`, `measurement_generation`, `reasoning_effort_source`, and `result`), so this snapshot cannot be independently folded by the checked-in parser alone.

## Turn status

| Status | Turns |
|---|---:|
| COMPLETED | 193 |
| STARTED | 12 |
| INTERRUPTED | 16 |

## Root model and exact usage

Status column is completed / interrupted / started. Worker columns show **documented-contract / installed-fold** token totals. Elapsed medians use rows with both timestamps. Task class and complexity are UNKNOWN across this sample, so these values are descriptive telemetry, not a model-speed comparison.

| Root model | Turns | Status C/I/S | Root exact / unknown | Root exact tokens | Worker tokens: contract / installed | Full Orchestra exact tokens under contract | Elapsed n; median |
| gpt-5.6-luna | 42 | 36/4/2 | 36/6 | 205,294,818 | 62,283 / 3,078,808 | 6,019,155 | 40; 126 s |
| gpt-5.6-terra | 4 | 4/0/0 | 4/0 | 996,841 | UNKNOWN / UNKNOWN | UNKNOWN | 4; 55 s |
| gpt-6-luna | 163 | 142/12/9 | 142/21 | 787,095,813 | 154,544 / 154,544 | 15,522,282 | 154; 687 s |
| gpt-6-sol | 12 | 11/0/1 | 12/0 | 47,313,574 | UNKNOWN / UNKNOWN | UNKNOWN | 11; 206 s |

Exact root usage by field (194 exact turns):

| Field | Tokens | Interpretation |
|---|---:|---|
| Input | 1,034,332,397 | Includes cached input |
| Cached input | 1,005,388,672 | Subset of input; do not add again |
| Non-cached input | 28,943,725 | Breakdown of input |
| Output | 6,368,649 | Output tokens |
| Reasoning output | 4,230,848 | `reasoning_tokens` is a compatibility alias; do not add twice |
| **Total** | **1,040,701,046** | Exact root role totals only |

Installed-fold exact worker role usage totals **3,233,352** across 3 folded worker rows. Under the documented edge contract, the exact worker sum is **216,827**. The contract-aligned exact role subtotal (exact root plus edge-valid exact worker) is **1,040,917,873 tokens**, still incomplete; it is not the all-turn total. Cached input is already within input totals.

## Worker detection and contract mismatch

Raw ledger evidence has 5 `worker_observed` records, 2 `worker_edge_observed` records, and 213 usage records (210 ROOT and 3 WORKER). The installed fold yields 3 worker rows; their model/effort/usage fields are in the JSON sidecar.

The checked-in `docs/telemetry.md` defines the exact worker population from exact worker edges and requires matching lifecycle/native identity plus exact usage. Applying that contract:

| Turn ref | Root model | Status | Folded worker model | Worker exact tokens | Edge rows | Installed fold | Documented contract |
| `T0001` | gpt-5.6-luna | COMPLETED | gpt-5.6-luna | 62,283 | 1 | EXACT | EXACT |
| `T0002` | gpt-5.6-luna | STARTED | gpt-5.6-luna | 3,016,525 | 0 | EXACT | UNKNOWN |
| `T0053` | gpt-6-luna | COMPLETED | gpt-6-luna | 154,544 | 1 | EXACT | EXACT |

A key disagreement is visible on `T0002` in this snapshot: an exact WORKER-role usage row has parent-turn identity but no `worker_edge_observed`. The installed fold counts its 3,016,525 tokens as exact worker usage; the documented contract keeps the worker population UNKNOWN. That amount remains in the row-level observed evidence but is excluded from the documented-contract worker total. Do not silently choose between these views.

No-worker turns are generally **UNKNOWN**, not zero: absent worker records do not prove that no subagent ran without an explicit complete-set zero-worker attestation.

## Timing

Every row includes start time in UTC and WIB; finalized rows also include end time and derived `elapsed_seconds`. Elapsed time is finalizer timestamp minus start timestamp, not active generation time. Overall median is **423 seconds**, p90 **2209 seconds** across 209 finalized turns. Event timestamps have whole-second resolution, so zero elapsed does not mean zero work. Missing elapsed means no finalizer existed at this cutoff.

## Pending OTel

Pending file SHA-256: `092a7fe39b0354edba22226a1250e251fd651f1c4054e26584b2c32b11287331` (20,221 bytes). It contains 51 well-formed JSON records and 51 unique source digests; 2 payloads carry a malformed marker. None matched exact recorded root/worker identity, leaving 51 unresolved; they are excluded from all totals. Pending payloads and identities are not published.

## Limitations and reviewer checklist

1. Root reasoning effort is UNKNOWN for 221/221 turns; worker effort is UNKNOWN for 3/3 folded worker rows. Historical model effort pins cannot be proven.
2. Installed-fold worker exactness is 3 turns; repository-contract exactness is 2. Other worker presence/usage is UNKNOWN, not zero.
3. Root usage is exact on 194 turns and UNKNOWN on 27 (16 UNKNOWN root usage observations plus 11 turns without a ROOT usage observation).
4. 12 rows are STARTED with no finalizer at this cutoff; they may be active or missing finalization.
5. Prompts, assistant/tool content, local paths, raw session/turn/worker IDs, task/project/repository labels, and branches are intentionally absent. This cannot support answer-quality or workload-matched speed claims.
6. Installed collector and checked-in template are different code artifacts; synchronize/version them before treating future samples as reproducible research data.
7. All pending spans remain unresolved; do not ingest/count them without exact identity reconciliation.

## Files

- Complete anonymized per-turn dataset: [recorded-turn-review-2026-09-24.json](recorded-turn-review-2026-09-24.json)
- This interpretation and quality report: [recorded-turn-review-2026-09-24.md](recorded-turn-review-2026-09-24.md)

JSON contains all 221 pseudonymous turn rows, times, status, root/worker usage and model/effort attribution, installed-fold and repository-contract totals, per-turn event counts, and selected execution/result/measurement counters. UNKNOWN metrics remain null or explicit UNKNOWN, not zero.
