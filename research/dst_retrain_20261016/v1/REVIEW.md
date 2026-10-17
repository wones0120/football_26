# Corrected-label DST production retrain — rejected for live promotion

**The corrected-label candidate fails the predeclared MAE gate. Sunday live projections and saved lineup remain unchanged.** On the same 446 verified outcomes, MAE rises 4.3225→4.4484 (+0.1259; 95% paired week-cluster interval [0.0287, 0.2374]). The frozen tolerance was +0.10 point. Five other gates pass. No tuning or train-on-test was used.

## Actual production path and source evidence

Production has one shared `GradientBoostingRegressor(random_state=42)` across all positions, rather than a separate DST component model. This experiment retains its 27 explicit features, zero-fill preprocessing, 80/20 model/history blend, seed and parameters. Opponent-QB shadow features are absent from both current live and candidate feature contracts. No new QB features or starter assumptions enter training. Only verified DST labels change. Frozen historical roll/history features remain as recorded; recomputing those features is a separate experiment.

Verified correction snapshot `e81b5772-5d81-505b-a44c-0660480098c4`, SHA256 `1ee194029dcdb0d7e8ffc075394ae9e470d00a2635dd51b474f580fce7f7b2ff`, uses `draftkings_classic_dst_event_scoring_v1`. Strict selection replaces 285 of804 deduplicated DST labels; all848 physical correction versions remain independently preserved. Missing labels, wrong canonical/source identity, unverified scoring versions, and absent/nonfinite scores reject; verified zeros remain valid. All804 legacy rows lack game IDs: original matrix row ID, canonical UUID, season/week/team/opponent and source match exactly; corrected game IDs are independently checked against canonical team/week identity. Original missing IDs remain explicit and are not overwritten.

The independent prior reconciliation covers all79 completed2026 games and81 official gamebooks. See [source audit](../../dst_scoring_repair_20261015/v1/REVIEW.md). Original outcomes, matrix rows and source snapshots were not overwritten.

## Chronological retrospective validation

The comparator is an incumbent-policy refit on each prior training window, scored against the same corrected heldout truth as the candidate; it is not a full-history incumbent scored in-sample. Calibration uses the same corrected truth in an intervening prior-only window for both arms.2025 trains through2024W13 and calibrates2024W14 onward;2026 trains through2025W14 and calibrates the remaining2025 rows.2026W1–3 and previously inspectedW4–5 are reported separately. Production active and latest prepared artifacts have identical historical fit inputs for these windows.

**These outcomes were previously inspected. Historical source capture clocks are incomplete. These are retrospective chronological comparisons, not fresh held-out or fully source-clock-attested validation.** Source corrections captured later reconstruct scoring truth; they do not prove original decision-time source availability.

| Block | N | MAE old → candidate | RMSE old → candidate | Bias old → candidate | 80% coverage old → candidate |
|---|---:|---:|---:|---:|---:|
| 2025_retrospective | 298 | 4.426 → 4.536 | 5.816 → 5.815 | -0.863 → +0.077 | 82.9% → 83.6% |
| 2026_w1_3_retrospective | 90 | 4.358 → 4.420 | 5.653 → 5.653 | -0.265 → +0.365 | 85.6% → 84.4% |
| 2026_w4_5_inspected | 58 | 3.737 → 4.045 | 4.751 → 5.130 | +0.979 → +1.654 | 81.0% → 79.3% |
| All |446| 4.322 → 4.448 | 5.656 → 5.698 | -0.503 → +0.340 | 83.2% → 83.2% |

Combined2026 MAE: 4.1146→4.2728. Only 18 week clusters support the aggregate interval, including just five current-season weeks; block-level uncertainty is substantial. Bias improves and coverage is unchanged, but point error worsens. Correct truth remains correct even when the unchanged model learns less accurately from it.

[Frozen criteria](CRITERIA.md), [complete metrics/gates](validation.json), [row predictions](heldout_predictions.json), [component-conditioned diagnostics](component_strata.json). The production model predicts total DK points only; there are no sack/INT/component heads to assign component MAE to. Diagnostics report total-error strata for touchdown games, sack totals, turnovers, negative scores and season, retaining small-group counts.

## Sunday impact — shadow counterfactual only

Candidate `v4.2-dst-exact-label-shadow-20261016` is saved as a checksum-addressed local fitted artifact with training/feature/code/source hashes. Its10659 prior training rows end2026W5, including804 verified DST labels. This full-history fit follows validation solely to inspect futureWeek6 impact; it never contributes to heldout metrics and is not eligible for live use.

Freeze: saved Sunday Main run `f84e75db-b286-48f4-8740-c03d11323889`, projection `b2ae485d-f436-470b-a52c-fa53095bbd4d`, cutoff2026-10-15T19:17:26.763111Z. This is the prior prepared snapshot, not a new injury/news refresh. Only DST means are substituted into its exact201-player eligible pool. Every non-DST cell, salary, ownership, eligibility, optional stacks/bringbacks and user controls is unchanged. Both exact pure-baseline-mean solves are Optimal, with no relaxation. Shared-tree retraining can change offense predictions; none of those changes are applied in this isolated comparison.

**13 of20 DST rank numbers change** (minimum rank for ties). All20 scores rise. Baltimore becomes first; Carolina stays selected. Rankings alone do not override the preserved user eligibility and lineup constraints.

| DST | Salary | Rank old → candidate | Mean old → candidate |
|---|---:|---:|---:|
| BAL | $3,200 | 4 → 1 | 5.540 → 7.469 |
| PIT | $3,300 | 6 → 2 | 5.525 → 7.425 |
| KC | $3,600 | 3 → 2 | 5.631 → 7.425 |
| IND | $3,400 | 5 → 4 | 5.526 → 7.308 |
| NE | $3,500 | 2 → 5 | 5.662 → 7.243 |
| LAR | $3,800 | 1 → 6 | 5.946 → 7.116 |
| PHI | $3,000 | 7 → 7 | 5.035 → 6.844 |
| TB | $2,600 | 9 → 8 | 4.809 → 6.721 |
| CAR | $2,500 | 10 → 9 | 4.612 → 6.423 |
| BUF | $3,100 | 8 → 10 | 4.989 → 6.033 |
| NYG | $2,800 | 11 → 11 | 4.464 → 5.669 |
| NO | $2,600 | 12 → 12 | 4.418 → 5.531 |
| CHI | $2,700 | 13 → 13 | 4.405 → 5.515 |
| ATL | $2,900 | 14 → 14 | 4.396 → 5.498 |
| LAC | $2,100 | 17 → 15 | 3.952 → 5.225 |
| CLE | $2,500 | 16 → 16 | 4.007 → 5.127 |
| NYJ | $2,200 | 19 → 17 | 3.914 → 5.014 |
| LV | $2,400 | 15 → 18 | 4.139 → 4.985 |
| TEN | $2,300 | 18 → 19 | 3.947 → 4.962 |
| ARI | $2,000 | 20 → 20 | 3.879 → 4.889 |

**The optimal roster stays the same: $49,800;133.1430→134.9537 shadow points.** The entire+1.8106 change is Carolina DST. This is not measured performance improvement.

| Player | Salary | Baseline → shadow mean |
|---|---:|---:|
| Matthew Stafford | $6,400 | 25.2159 → 25.2159 |
| Kyren Williams | $6,800 | 19.7847 → 19.7847 |
| Derrick Henry | $8,200 | 18.8087 → 18.8087 |
| Panthers | $2,500 | 4.6123 → 6.4229 |
| Puka Nacua | $8,100 | 21.8141 → 21.8141 |
| Carnell Tate | $5,000 | 11.2019 → 11.2019 |
| Tyler Higbee | $3,400 | 9.8587 → 9.8587 |
| Wan'Dale Robinson | $4,500 | 10.3182 → 10.3182 |
| Rome Odunze | $4,900 | 11.5285 → 11.5285 |

[Exact frozen lineups, input pools and solver audits](matched_lineups.json), [ranking CSV](sunday_defense_rankings.csv), [candidate manifest](candidate_manifest.json).

## Live status, rollback and remaining work

No model or projection pointer was promoted, no live Prepare was run, and no optimizer result was saved or replaced. Main’s active pointer and all288 prepared projection means were reread and verified unchanged in [live check](live_unchanged.json). The previous artifact and saved lineup remain available, so rollback is unnecessary. Morning preparation and closed Thursday slates were not modified. No exports or entries were made.

The explicit correction selector is candidate-only; live Prepare still uses the existing model/label path. Exact future historical scoring integration and atomic scoped promotion remain unactivated because the validation gate failed. A later model-policy experiment must separately address the measured error increase, retain corrected truth, and define its criteria before evaluation. Existing Sunday preliminary research readiness remains NOT_READY for final entry; this task did not refresh injury/news or final inactives.

Validation:39 focused tests pass across strict label selection, scoring reconciliation and legacy DST contract. Source hash/identity/version, known zero, missing/fallback rejection, time boundary and live QB-feature exclusion are covered. [Test output](tests.txt), [strict selection/input audit](audit.json). No UI code changed.

Reproduce offline: run `validate_candidate.py` using captured `incumbent.joblib`, then `shadow_impact.py` and `diagnostics.py`. `capture_incumbent.py`, `capture_prepared.py` and `verify_live_unchanged.py` use read-only database transactions. Candidate artifact and full frozen inputs are preserved in this directory.
