# DST scoring repair and repeated opponent-QB ablation

**All33 originally flagged labels are confirmed incorrect and corrected in a separately versioned research dataset.** The full audit found a larger problem: **114/148 unique2026 team/week labels change;34 match; six original zero labels are valid.** There are no unresolved game/identity/coverage mappings in this correction. Live projections remain unchanged.

The experiment's804 unique2024–2026 DST team/week rows contain285 corrections and519 verified matches. Auditing duplicate slate copies separately covers **848 physical matrix row versions:319 corrections/529 unchanged**.2026 has192 physical rows (148 corrected/44 unchanged), representing the148 unique game/team outcomes above.2024 contributes95 corrected unique/physical rows,2025 contributes76. These counts distinguish physical records from the deduplicated experiment cohort. Original database rows and prior reports remain preserved; no silent overwrite.

## What was wrong

1. `_fetch_slate_player_pool` used `dst_points_by_team.get(team,0.0)`. Missing final schedule/stat evidence could therefore become a completed zero. Stored2026 Week1/3/5 DST labels are entirely zero, with28/30 zeros inWeek4. Current final schedules forWeeks1–3 arrived after those matrix builds; only twoWeek4 finals and noWeek5 finals are present in that legacy schedule table. The existing completed-outcome freshness test looked for a whole period of zero labels mixed across positions, so positive offensive labels masked stale DST labels.
2. The legacy aggregate scorer sums opposing player sack/INT/fumble fields and team `def_tds`/`special_teams_tds`, with absent fields defaulting to zero. It misses recoveries on special teams or after defensive possession, blocked kicks, safeties and conversion returns when those are not in its narrow aggregate fields. It also charges the full opponent score instead of separating scores made against the offense. Raw multiple source versions are not deduplicated there. These limitations explain why the problem extends beyond zero placeholders and into older seasons.

The new **`draftkings_classic_dst_event_scoring_v1`** scorer uses complete final play-by-play with canonical game/team identity and an explicit existing32-UUID DST map. It does not generate replacement identities from display names. It counts sacks, INTs, opposing fumble recoveries (including possession changes within one play), defensive/ST TDs exactly once, safeties, blocked kicks and conversion returns. It attributes allowed points per scoring event: offensive/ST TDs, FGs, XP/conversions and conversion returns count; scores against the offense do not. An XP after a defensive TD still counts against the opposing DST, so subtracting seven points per defensive TD is not exact. No-play/nullified events, official score timelines and replay-adjusted `order_sequence` are handled explicitly. Missing/incomplete/ambiguous evidence fails rather than becoming zero.

The **normal historical builder now blocks completed-date games with missing final scores or missing weekly-stat team coverage**, preventing that particular zero-default failure on a rebuild. Future target placeholders are preserved and are not relabeled as observed outcomes. The older aggregate method is still approximate; the exact event-derived labels are explicitly selected for this research version and are **not activated automatically in live training**. No model or feature change was smuggled into the repair.

## Verification and coverage

Captured versioned nflverse PBP covers649 complete games in2024–2026, including **all79 completed2026 games (158 team outcomes)**. Each game matches an independently captured canonical schedule's teams/date; available old schedule final scores also reconcile. We captured **81 official NFL gamebooks**: all79 current-season games plus two older examples. Every book passed final-score, sack, INT, fumble-loss/recovery, blocked-kick, safety, non-rushing/passing touchdown and date checks against the reconstruction. The Melbourne opener's local Friday date converts to the NFL US-Eastern Thursday date; it was checked explicitly rather than dismissed as a mismatch. All804 cohort rows and848 physical row versions map by canonical UUID/team/opponent/game, with no missing rows dropped silently.

The scoring contract follows [DraftKings' NFL DFS scoring guide](https://dknetwork.draftkings.com/2025/08/27/nfl-dfs-beginners-guide-draftkings/) and its [points-allowed/possession notes](https://dknetwork.draftkings.com/2022/09/19/how-reignmakers-football-scoring-works/). The generic rules URL currently renders a shell, so the retained primary guide/notes and explicit versioned contract provide the checkable definition. This is an independently reconciled NFL-stat reconstruction, **not a claim of downloaded DraftKings contest-result scores**.

| Game | DST | Original matrix row | Old | Corrected |
|---|---|---:|---:|---:|
| 2026_01_ARI_LAC | ARI | 101203 | 0 | 10 |
| 2026_05_PHI_JAX | PHI | 152620 | 0 | 5 |
| 2024_04_NO_ATL | ATL | 78247 | 9 | 17 |
| 2024_04_CLE_LV | CLE | 78252 | 5 | 11 |

The Eagles Week5 example is two sacks, one INT, no opponent fumble recovery and19 allowed points:5DK points, confirmed in the [official gamebook](https://static.www.nfl.com/image/upload/v1791805919/gamecenter/aa6b5c2b-4feb-11f1-abca-2c54536568a9.pdf). Atlanta's2024 example includes a muffed-punt recovery TD and a pick-six, showing why six-plus-two-point omissions matter. A lower-bound flag alone did not establish these repairs: full components and official source checks did.

## Separate correction versions and lineage

- Full848-row correction version: source snapshot **`e81b5772-5d81-505b-a44c-0660480098c4`**, contentSHA256 `1ee194029dcdb0d7e8ffc075394ae9e470d00a2635dd51b474f580fce7f7b2ff`. [Full physical records, old→new receipts](corrected_all_matrix_rows.json).
- Exact804-row experiment cohort: source snapshot **`b1f073be-94d9-5702-806b-82f4448d80b8`**, logical dataset hash `acaac2d267eebceaf2cd68892e29050f465f1d78a1a1a286ffa0becb0ac275b0`. [Corrected cohort](corrected_dst_matrix.json).
- [Append-only persistence receipts](persistence_receipt.json), [full-version receipt](full_matrix_version_receipt.json), [all scoring events/components](scored_games.json), [official book checks](official_gamebook_checks.json), [raw book capture index](gamebook_manifest.json), [canonical identities](canonical_dst_identity.json).

Published copies live in the immutable `source_snapshot` artifact paths in those receipts; worktree files are reproducible research copies. Every correction preserves the original matrix row ID/value, canonical UUID/game/team, new value, reason/status, source content hash and scoring contract. Original raw snapshots and original evaluation evidence are untouched. This is a separate research label version, not an in-place update to `player_game_feature_matrix` or an active projection table. No migration or new dependency was needed; PDF extraction used the existing bundled pypdf runtime.

## Matched feature comparison on corrected truth

Both arms use the **same frozen804-row feature frame, same splits, GradientBoosting parameters/seed42, train-only imputer, history blend, calibration and newly corrected labels**. No feature definitions, QB context, pool or hyperparameters changed. The study exactly reproduces every original control prediction before changing labels; sack/INT targets and their predictions are unchanged.24 bounded fits include corrected arms plus legacy-training-label controls evaluated on the same corrected truth. [Metrics](ablation_metrics.json), [row predictions](ablation_predictions.json).

| Block | N | Corrected baseline MAE / RMSE | + opponent-QB MAE / RMSE | MAE difference | 95% week-cluster interval | 80% coverage baseline / +QB |
|---|---:|---:|---:|---:|---|---|
| 2025_holdout | 298 | 4.642 / 5.959 | 4.682 / 5.989 | +0.040 | [-0.237, +0.289] | 82.2% / 81.2% |
| 2026_weeks1_3 | 90 | 4.566 / 5.720 | 4.716 / 5.995 | +0.150 | [+0.087, +0.242] | 85.6% / 80.0% |
| 2026_weeks4_5_inspected | 58 | 4.360 / 5.185 | 4.499 / 5.375 | +0.139 | [+0.094, +0.181] | 87.9% / 82.8% |

**The opponent-QB extension still does not improve DK-point MAE in any block. Keep it shadow-only.**2025's tiny sack/INT MAE gains remain within their week-cluster uncertainty intervals;2026 count-target errors worsen. Calibration coverage and RMSE do not establish a compensating, validated improvement. Only13/3/2 week clusters support the respective95% intervals, especially limiting the two-week estimate. No new tuning search was performed.

To isolate data repair from feature effect, these controls use **corrected test truth for both fits**:

| Block | Baseline fit on old training labels, evaluated on corrected truth | Baseline fit on corrected training labels, same corrected truth |
|---|---:|---:|
| 2025_holdout | 4.526 | 4.642 |
| 2026_weeks1_3 | 4.372 | 4.566 |
| 2026_weeks4_5_inspected | 3.844 | 4.360 |

Repairing labels does not guarantee a fixed model's MAE improves. The corrected labels are source-supported truth; the frozen model trained on them performs worse here. That is a model-validation result, not a reason to retain incorrect scores. These are retrospective chronological comparisons: historical raw receipts and archived pregame starter decisions are incomplete;2026 Weeks4/5 were already inspected. The historical QB remains the previous completed game's primary-dropback QB, never the actual future starter chosen with hindsight. No fresh outcome-blind or fully source-clock-verified backtest is claimed.

**Live unchanged:** [fresh read/hash verification](live_unchanged.json) confirms the Sunday Main active projection pointer and all288 persisted rows of projection `b2ae485d-f436-470b-a52c-fa53095bbd4d` exactly match the pre-task capture. The133.14 saved lineup is intact. There was no optimizer generation, API/worker restart, live feature activation, live model fit, CSV export or contest entry during this repair. Morning preparation is a separate scope owned by its agent.

Validation: **75 focused scoring/QB/canonical-input tests plus8 existing feature-matrix/route tests passed (83 total)**. Exact scoring tests cover missing/real zero, canonical mismatches, duplicate plays, replay order, defensive TD/PAT attribution, ST TDs, blocks, safeties, conversion returns, offensive recoveries and future/completed source gates. The builder diff is limited to missing-source guards; pre-existing work is preserved.

Reproduce source reconciliation with `reconcile.py`, official PDF verification with the bundled runtime and `verify_gamebooks.py`, then `rerun_ablation.py`. All source captures, source hashes, code hashes, split definitions and environment versions remain in this directory and the prior frozen feature study. Promotion of corrected labels or opponent-QB features into live fitting remains a separate explicit review step.
