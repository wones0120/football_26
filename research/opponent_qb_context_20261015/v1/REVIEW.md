# Opponent starting-QB context — shadow implementation and validation

**Implemented, tested, and deliberately left out of live projections.** The direct opponent-QB information gap is real, but this first bounded ablation does not justify activating a numerical Panthers boost. The completed current-model Sunday rerun remains saved separately as `f84e75db-b286-48f4-8740-c03d11323889`, 133.14/$49,800; [fresh lineup review](../../sunday_hurts_refresh_20261015/v1/REVIEW.md).

The new service `backend/app/product_services/opponent_qb_context.py` exposes `QBContextIndex.context` and an explicit feature contract. It uses canonical UUIDs, team/game period and source-row lineage. Eight prior observed QB appearances supply attempts+sacks (a dropback proxy), sack/INT/sack-fumble-lost rates, passing yards per attempt, passing EPA per proxy dropback, rushing yards per carry, observed games/dropbacks, missing-value indicators, small-sample flag, starter uncertainty and change from the prior team's primary QB. Rushing includes designed carries/kneels; there is no fabricated pressure rate, pressure-escape score or opaque quality scalar.

**Strict mode is default.** A history row must precede the target week, have completion evidence before the decision and source availability at/before the cutoff. Sourced starter evidence requires matching canonical team/UUID, URI, observed and received clocks before cutoff; otherwise the helper uses the previous completed team game's primary dropback QB. Tied primary volume stays unknown. Upcoming game's actual QB, inactive list and outcomes are never used to select historical starters. Missing rates remain missing; the experiment's imputer fits only on the training partition. The eight-game window/100-dropback small-sample flag were fixed before fitting, not tuned for this Sunday news.

The current Panthers context correctly selects expected McKee from the captured Hurts OUT/depth evidence, with **4 prior games/93 proxy dropbacks**, small sample and inferred starter flags. His observed sack rate is5.38% and INT rate1.14%; the eight-game Hurts proxy is6.46% and1.22% across263 proxy dropbacks. These unequal, selected samples do not establish that the backup is more turnover-prone, and illustrate why an automatic backup-QB bonus would be unjustified. Chicago's provisional Williams source is flagged uncertain; separate Williams/Bagent/Keenum if-starts contexts are retained as conditional scenarios without mixture probabilities. No feature changes the current availability truth or user preference eligibility.

## Controlled retrospective ablation

Existing data contain16,898 canonically mapped QB/period rows (2000–2026) and804 unique DST team/period matrix rows from2024–2026. Each decision uses only prior-week completed QB history. All matched logs resolve by native nflreadpy alias → canonical UUID, never display name. The historical schedule's final QB fields are retained in raw evidence but never read for feature selection.

Only148/804 historical rows have any strict source-clock QB history; all2024/2025 records were imported after their decisions. Thus the meaningful broad comparison is an **explicit retrospective event-time reconstruction**, not a verified historical-as-of or fresh outcome-blind backtest. All outcomes are treated as retrospectively available;2026 Week4/5 were previously inspected. Stored matrix features/markets also lack complete historical publication proof.

Both arms use the same DST rows, existing baseline feature names, `GradientBoostingRegressor(random_state=42)` defaults, train-only median imputation, splits and production DK point/history blend. This is a **DST-only** model-family ablation, not an exact replay of the pooled live model. No hyperparameter search.2025 holdout trains on2024 throughWeek13, calibratesWeek14 onward, tests2025.2026 count-target holdouts train before2025 Week15 and calibrate the rest of2025, never using2026 outcomes to fit. Calibration80% intervals come only from prior calibration residuals.

| Held-out block | Target | N | Baseline MAE | +QB MAE | Difference (lower better) | Week-cluster 95% interval |
|---|---|---:|---:|---:|---:|---|
| 2025_holdout | DST DK points | 298 | 4.232 | 4.310 | +0.078 | [-0.054, +0.202] |
| 2025_holdout | Opposing QB sacks | 298 | 1.691 | 1.688 | -0.003 | [-0.068, +0.066] |
| 2025_holdout | Opposing QB INTs | 298 | 0.692 | 0.681 | -0.011 | [-0.064, +0.035] |
| 2026_weeks1_3 | Opposing QB sacks | 90 | 1.275 | 1.343 | +0.068 | [+0.026, +0.094] |
| 2026_weeks1_3 | Opposing QB INTs | 90 | 0.643 | 0.719 | +0.076 | [+0.009, +0.118] |
| 2026_weeks4_5_inspected | Opposing QB sacks | 58 | 1.442 | 1.471 | +0.029 | [+0.002, +0.057] |
| 2026_weeks4_5_inspected | Opposing QB INTs | 58 | 0.770 | 0.811 | +0.041 | [+0.002, +0.077] |

On the usable298-row2025 DK block, MAE worsened4.232→4.310; bias moved+0.031→−0.225. Nominal80% interval coverage moved78.2%→80.9%, which does not offset worse point accuracy or establish forward calibration. Tiny2025 sack/INT improvements are uncertain; the later2026 count blocks worsen. Intervals resample entire season/week clusters (2,000 draws, fixed seed), not individual supposedly independent players; Week4/5 has only two week clusters, so its interval is especially weak. Full RMSE, bias, prediction-bin calibration, counts and intervals remain in [metrics.json](metrics.json) and [paired_comparison.json](paired_comparison.json).

**A data-quality finding prevents using2026 DST fantasy points as validation truth.**2026 Week1,Week3 andWeek5 are entirely zero in the stored DST matrix; Week4 has28/30 zeros.33 rows violate a conservative DK lower bound: QB sacks +2×QB interceptions −4 (the worst points-allowed deduction). Passing this bound does not prove all other rows correct, so all1482026 DK labels are withheld pending complete sourced reconciliation. Opponent-QB sack/INT targets remain available from complete raw QB boxes; non-QB trick-play outcomes can differ from exact DST totals. The module adds a tested impossible-label check, without filling missing labels or mutating production tables. [Exact violations](dst_label_audit.json). Initial diagnostic results using those unverified labels are preserved separately, not presented as accepted accuracy evidence: [superseded diagnostic](metrics_diagnostic_unverified_2026.json).

## Activation decision and remaining work

**Shadow only; no live feature-list, model version, optimizer policy, salary, ownership or projection changes.** No Thursday interference, API restart, CSV, contest entry or live refit for this new feature. The earlier normal source refresh remains independently traceable.

The first supported target is DST sacks/turnovers and eventually total DK points. QB-adjusted PHI receiving/rushing efficiency, scoring/play volume and opponent offensive script need separately validated models with historical pregame starter/availability evidence; they do not receive arbitrary bonuses from this module. The existing team/game outlook uses prior team history/home/rest, so current-QB changes are still not learned there. Improving this feature set is bounded by small DST labels, selection effects in backup samples, missing archived starter decisions and the2026 label defect; negative ablation should not be hidden by activating it anyway.

Next necessary steps are reconcile complete2026 DST outcomes with provenance; archive prospective starter uncertainty/candidate evidence before decisions; then repeat matched chronological validation with those cases. Any actual starter-change sensitivity remains conditional research until those examples exist. No activation is claimed.

Reproduce using `PYTHONPATH=. .venv/bin/python research/opponent_qb_context_20261015/v1/validate_shadow.py` on the immutable captured input files, followed by `render_review.py`. Final corrected experiment:14 fits; initial18-fit diagnostic preserved after label validation exposed the problem. Source hashes, folds and held-out predictions are retained. Tests:12 focused new cases;33 combined relevant backend cases pass. No UI changes, so no UI rebuild was necessary.
