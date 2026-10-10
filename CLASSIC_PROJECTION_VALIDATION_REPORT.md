# Classic NFL projection validation

Assessment date: October 10, 2026. **Historical expansion stopped at the user’s request; retain this evidence for later research.** **Production recommendation: INSUFFICIENT EVIDENCE.** Keep `PLAYER_OPPORTUNITY_ALLOCATION_POLICY=legacy_v1`. Production forecasting defaults, active projections, optimizer scores, constraints, selection and original artifacts remain unchanged. Subsequent focused stabilization fixes explanation replay and missing-support handling, described below. Week 5 outcomes were not used.

The allocation repair addresses a real accounting defect. Its accuracy across the NFL is **NOT ESTABLISHED**. This audit recovers a genuine prelock Week 4 source snapshot and produces a fairer paired **frozen-model diagnostic**, but cannot produce the requested trustworthy refitted walk-forward study from the available evidence. The distinction applies to every numerical result below.

Classification: **VERIFIED** means reproduced from local bytes, stored metadata, code or executed checks; **LIKELY** is a supported explanation requiring additional evidence; **NOT ESTABLISHED** is an unanswered question. A verified diagnostic number is not a verified promotion claim.

## 1. Historical source integrity

**VERIFIED — destructive refresh breaks raw-table historical reconstruction.** `IngestService._clear_existing_nflreadpy_weekly_stats` deletes the existing source/season/week slice before each fresh ingest. The October 2 ingest stored 3,339 rows; the October 4 19:25 UTC refresh inserted 3,407 rows and replaced earlier raw receipts. The currently surviving Weeks 1–3 rows date from that refresh. They are later than the saved October 4 Week 4 cutoffs at 10:47, 12:23 and 15:44 UTC. This is not evidence that the statistics were unavailable before kickoff: the earlier source file survived.

**VERIFIED — original mismatch reproduced.** Reading only surviving raw rows received by each Week 4 cutoff produces 135 carry-count, 234 target-count, 69 carry-share and 252 target-share mismatches. Allowing later raw receipts reproduces all four saved features exactly. This diagnostic deliberately relaxing receipt time is used only to explain the mismatch, never to certify forecasts.

**VERIFIED — an earlier immutable source survives.** Snapshot `70a8d921-277f-5ee5-a487-21d90c021673` was captured October 2 at 02:36:09 UTC. Its CSV hash is `7599cc9e4480f20820eb578358b190a9d2c25992cd22f1500c4ddb881fde0e73`, matching the original ingest checksum. It contains 3,339 Weeks 1–3 rows. Earlier September 19 Week 1 and partial Week 2 snapshots are also inventoried and hashed. Recovery uses their recorded capture times; it does not relabel October 4 rows as prelock data.

**LIKELY — overwritten receipt timestamps explain the previous apparent fallback.** Original Week 4 counts match the current-season observations; raw-table-only reconstruction loses those observations and falls back to 2025. The recovered-source parity artifact gives the exact reconstruction result. An allocation comparison using the previous mismatched baseline is invalid.

**VERIFIED — membership and identity limits remain.** Research keeps the frozen salary/current-team pool and context fixed, joins workload through native `nflreadpy` IDs to canonical UUIDs, and checks native-ID mapping ambiguity. It does not join display names. `player_alias` has `created_at` and `last_seen_at`, but no effective-dated mapping history; the original export joined the current alias table. A unique current mapping is not proof it existed at the original cutoff. Frozen current-team assignments and context preserve the original experiment; they do not independently certify correct historical roster or injury status. Exact complete point-in-time reconstruction remains **NOT ESTABLISHED**, even if numerical count/share parity passes.

**VERIFIED — training temporal evidence is incomplete.** Saved Week 4 training ends at 2026 Week 3; Week 5 training ends at Week 4. Archived training/target matrix creation timestamps do not exceed their outer run cutoffs. However, the lagged opportunity histories were rebuilt using the outer projection cutoff, rather than each training game's original source cutoff. Older source versions and feature definitions at each historical forecast are not frozen. Prior game-week labels alone do not prove features were available at those games.

**VERIFIED — old-season backtests cannot supply the missing proof.** The available 2024/2025 weekly source receipts are from February 25, 2026. Those rows can train a later 2026 model; they cannot certify what was known before the 2024/2025 games. Today’s final statistics restricted by game week are not an acceptable substitute for versioned prelock sources.

**NOT ESTABLISHED — precise original feature-code equivalence beyond the four tested fields.** Existing artifact model bytes reproduce their raw outputs and saved feature frames remain available, but that does not recover every original transform version and source dependency. Full code/config/source lineage must accompany future folds.

The ingest defect is retained as a later engineering follow-up, not patched by removing its deletion call: existing learning readers sum raw rows without selecting a version. Simply appending would double-count workloads and DST statistics. Fix retention and version-aware readers together in a separately verified ingest change; do not mutate or backdate historical receipts to make this study pass.

## 2. Exact data available for walk-forward validation

Read-only database inventory covers all saved Sunday Main projection runs, not just the three previously selected Week 4 snapshots.

| Period | Saved runs | Fitted artifacts | Usability |
| --- | ---: | ---: | --- |
| 2026 Week 1 | 2 | 0 | Prelock forecasts exist; no fitted artifact; complete prior source package not established |
| 2026 Week 2 | 16 | 0 | No fitted artifact; Week 1 source survives, Week 2 statistics snapshot is partial |
| 2026 Week 3 | 2 | 0 | No fitted artifact; prelock Week 2 source version not established |
| 2026 Week 4 | 26 | 26 | One independent completed week; prelock Weeks 1–3 CSV recovered; original fold training/identity provenance incomplete |
| 2026 Week 5 | 9 | 9 | Future Sunday Main; evidence review only; no accuracy evaluation |

**VERIFIED:** three Week 4 snapshots count as one independent week. This diagnostic selects only the latest archived prelock Week 4 artifact, `e56ee32e-5b03-49a8-a4c4-5cf74bceeb3c`, before reading labels. Other snapshots are used only for provenance auditing.

**Trustworthy completed refitted evaluation weeks: 0.** Independent completed diagnostic weeks: 1. There is no qualifying chronological validation/test split for coefficient selection. More fitted snapshots cannot increase the number of independent weeks.

## 3. Baseline versus repaired comparison design

Both branches rebuild historical opportunity counts/shares from the exact same recovered prelock source objects, frozen canonical pool, unavailable-player pool, starter assumptions and explicit context. Each branch applies its own general allocation policy and refreshes derived offensive-role features. Non-opportunity scoring features, fitted model, model training frame, saved residual profiles and market corrections are held fixed. Predictions are saved before outcome joining.

This removes the previous asymmetric raw-input comparison. It does **not** refit the repaired model or certify every historical source domain. The labels are postgame Week 4 statistics joined by canonical ID and team; absent actual rows remain unknown, not zero. There is no Week 5 outcome access. Numerical results are conditional on the archived statistics and mappings, not an independent official-results audit.

`build_opportunity_pair` implements same-input feature/allocation construction. `refit_forecast_pair` implements separate GradientBoosting fits with identical parameters, chronological prior residual fits, opportunity anchors fitted on prior data, and separate position/role calibration. It rejects evaluation labels, future training weeks, unmatched non-opportunity feature values, absent provenance, and missing prior OOF calibration. It also refuses frozen nonzero market point corrections: full market reconciliation must be recomputed for each refit before those folds qualify. The helper has a synthetic regression smoke test; no synthetic data enters this report’s evidence.

**NOT ESTABLISHED:** an end-to-end certified historical walk-forward run. The helper and metric framework are usable building blocks, not a claim that the missing source packages or market refit integration exist. A trustworthy run is blocked before fitting; no substitute validation is manufactured.

## 4. Opportunity forecast accuracy

The paired workload metrics below use only players with actual workload and a supported numerical forecast in both methods. Missing forecasts and each method’s full available cohort are separately exported. Removing unsupported forecasts can select an easier cohort, so missingness is part of the promotion gate.

| Workload | Paired n | Legacy MAE / RMSE / bias | Repaired MAE / RMSE / bias |
| --- | ---: | --- | --- |
| RB carries | 68 | 2.977 / 4.524 / -1.126 | 3.029 / 4.487 / -0.843 |
| RB targets | 68 | 1.484 / 2.305 / -0.514 | 1.485 / 2.320 / -0.466 |
| WR targets | 102 | 1.976 / 2.925 / -0.399 | 2.127 / 3.112 / -0.408 |
| TE targets | 55 | 1.545 / 2.380 / -0.608 | 1.624 / 2.566 / -0.679 |

Missing repaired workload forecasts among labeled players: RB 2/70, WR 5/107, TE 4/59. They are unknown, not confident zero. Team carry-budget MAE is 4.000 → 4.111 across 24 teams; target-budget MAE is 7.333 → 7.458. Unallocated-versus-actual-unrepresented MAE is 0.576 → 0.972 carries and 0.781 → 1.278 targets; interpret that residual using the qualification below.

**VERIFIED diagnostic; NOT ESTABLISHED generalization.** Bias is forecast minus actual. The allocation budgets are lagged team averages, not a trained current-week team-volume model. Team capacity conservation cannot establish football forecast accuracy.

Team totals and unallocated residuals are exported separately in `paired_week4_team_allocation.csv`. “Actual unrepresented” means actual workload of players outside that allocation’s canonical player list. The predicted unallocated residual also includes withheld work for included unavailable players, so its difference from actual unrepresented volume diagnoses residual mismatch rather than identifying the correct recipient. Raw team labels require known source rows; no missing outcome is converted to zero.

Expected starter/backup labels are absent in this Week 4 artifact: this slice is **NOT ESTABLISHED**, not inferred from observed output. Cohort exports include prelock injury-status/role-change fields when present, missing-history groups and a prior-team-differs proxy. That proxy is not a verified trade date. Role changes, injuries and source omissions need independent roster/participation evidence. In particular, no player row in a team game may mean nonparticipation or missing source coverage; the repaired zero-in-window treatment cannot distinguish them by itself.

## 5. Fantasy-point forecast accuracy

| Cohort | n | Legacy MAE / RMSE / bias | Repaired MAE / RMSE / bias |
| --- | ---: | --- | --- |
| overall | 261 | 4.492 / 6.621 / -0.824 | 4.499 / 6.627 / -0.836 |
| position:QB | 25 | 5.466 / 7.115 / -1.728 | 5.466 / 7.115 / -1.728 |
| position:RB | 70 | 4.388 / 6.536 / -1.031 | 4.366 / 6.527 / -1.063 |
| position:WR | 107 | 4.900 / 7.349 / -0.793 | 4.905 / 7.358 / -0.804 |
| position:TE | 59 | 3.464 / 4.882 / -0.250 | 3.510 / 4.911 / -0.248 |
| price_band:expensive | 13 | 8.811 / 11.514 / -2.460 | 8.776 / 11.520 / -2.536 |
| price_band:inexpensive | 160 | 3.212 / 4.959 / -0.515 | 3.224 / 4.972 / -0.517 |
| volume_band:high | 28 | 7.815 / 9.862 / -0.787 | 7.848 / 9.891 / -0.819 |
| volume_band:low | 233 | 4.093 / 6.117 / -0.828 | 4.096 / 6.119 / -0.838 |

**VERIFIED diagnostic:** paired overall ΔMAE = +0.0067 and ΔRMSE = +0.0066 (repaired minus legacy); both slightly worse. RB MAE improves by 0.0220; WR worsens by 0.0051; TE worsens by 0.0466. These tiny one-week differences neither establish improvement nor justify rejecting the repair. Biggest absolute-error improvements include Marvin Mims Jr. (0.79), McCaffrey (0.73) and Jauan Jennings (0.53); biggest regressions include Brevin Jordan (1.16), Chris Manhertz (1.11) and Jalen Tolbert (0.86). These are diagnostic examples, not adjustment targets.

All numbers are the single recovered-source frozen-model diagnostic. QB labels can be derived from player statistics; DST labels are not constructed from offensive player statistics. Missing outcomes are counted in the CSV. Signed bias and price/volume/cohort breakdowns are in the JSON; expensive means salary ≥ $7,000, inexpensive ≤ $4,500. High volume uses the original prelock ≥6 targets or RB ≥14 carries, never realized workload.

`delta_absolute_point_error` in the paired CSV identifies every individual improvement and regression; negative is improved. It is not a player-specific tuning target. One week's gains cannot establish stable role effects. No per-player overrides were added.

## 6. P10/P90 calibration

| Method | n | Below P10 | Above P90 | Coverage | Width | Interval score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| legacy_v1 | 261 | 6.5% | 11.5% | 82.0% | 12.589 | 21.404 |
| team_window_v2 | 261 | 5.7% | 13.0% | 81.2% | 12.411 | 21.935 |

Nominal central interval coverage is 80%. The report counts strict misses below P10 and above P90, includes boundary values in coverage, and exports interval width and the 80% interval score to discourage gaining coverage merely by widening intervals. **NOT ESTABLISHED:** independent refitted distribution calibration, role/price reliability, or a stable uncertainty estimate. These profiles were fitted on legacy inputs and reused for this diagnostic.

Paired metric code uses equal-week deltas and seeded bootstrap sampling of whole independent weeks. With one week the confidence interval is explicitly null. Bootstrapping hundreds of player rows or three same-week snapshots would understate week-level uncertainty and is not used.

## 7. Evidence for 55%/70% blending

**VERIFIED:** production uses 55% for players with at least three historical games and 70% below that threshold. Isotonic opportunity curves are fitted from the prior training frame. Context/evidence activation determines whether a coefficient is used at all. Removing an unsupported anchor can raise a player's fallback mean even when the repaired workload is unknown.

**NOT ESTABLISHED:** either coefficient is optimal; zero anchor is better; or any alternate weight generalizes across positions and roles. No weight was selected from Week 4 outcomes or Week 5 deltas. Keep both existing weights unchanged.

The implemented selector accepts only prior OOF rows, checks training-through < validation period, requires at least three independent validation weeks, and rejects any validation row in the chronological test period. Its predefined grid is (veteran, low-history): (0.55, 0.70), (0.25, 0.40), (0.40, 0.55), (0.70, 0.85), (0, 0), (1, 1). Default wins exact ties. Inactive or unsupported anchors stay inactive. The selector operates on conditional base/anchor predictions; a full selection experiment must also apply frozen availability/market context, generate candidate-specific prior residuals, and evaluate final calibrated forecasts. Do not call the helper's conditional MAE a production pipeline result.

Pre-register training, validation and a final untouched chronological test block before future results arrive. Select weights on validation equal-week MAE, with RMSE/bias and position/role stability as secondary checks. Freeze the selected policy before opening test outcomes. Report activation/sample counts, all grid scores, and default-versus-selected test effects. Preserve the defaults if evidence is equivocal or only one player/group benefits.

## 8. Suspicious Week 5 changes: prelock evidence only

All observations below are from archived Weeks 2–4 and current frozen context. No Week 5 results are used. Raw source rows, canonical IDs, capture timestamps, observed-game counts, window definitions, old/new predictions and anchor weights are exported in `week5_player_evidence.json`.

| Player | Mean change | Same-team workload in shared W2–4 window | Assessment |
| --- | --- | --- | --- |
| Jahmyr Gibbs | 19.38 → 23.87 | DET carries 16/20/15; targets 8/8/7; repaired 17 carries, 7.67 targets | **VERIFIED** current workload support. Former-team Pacheco work no longer activates DET's phantom 55% anchor; corrected weight 0. **NOT ESTABLISHED** that 23.87 is an accurately calibrated fantasy mean. |
| Garrett Wilson | 12.21 → 14.82 | NYJ targets 7/13/4; 24/87 team targets = 27.59%; repaired 8 targets | **VERIFIED** volume support. Genuine unavailable same-team work keeps a 55% anchor. No automatic transfer of all missing targets to Wilson. Week-to-week variability remains. |
| Sam LaPorta | 14.28 → 19.25 | DET targets 7/4/13; repaired 8 targets | **VERIFIED** support for the three-game average. The removed DET anchor restores the fallback mean (weight 0); a 13-target latest game does not independently validate 19.25 fantasy points. |
| Christian McCaffrey | 13.13 → 17.99 | SF carries 10/15/15; targets 4/5/5; repaired 13.33 carries and 4.67 targets | **VERIFIED** same-team role observations; corrected 55% anchor remains. Current workload support is stronger than the compressed old estimate; future health/role stability and fantasy improvement are **NOT ESTABLISHED**. |
| Darius Slayton | 6.71 → 12.31 | No IND observation in this window; old 3.08 target forecast becomes unknown | **VERIFIED** unsupported anchor disappears (weight 0), restoring historical/model fallback. **NOT ESTABLISHED** expanded IND role or support for 12.31. Treat as a missing-evidence review case, not repair success. Frozen label says expected backup. |
| Nico Collins | 13.38 → 10.46 | Only HOU Week 4 row: 8 targets; W2/W3 absent; divided by three → 2.67 | **VERIFIED** arithmetic, **NOT ESTABLISHED** healthy next-game workload. The method effectively penalizes absent games even after a return; current start/status and reason for absence must be reviewed. A general participation-conditioned role model may be needed. |
| Justin Jefferson | 11.14 → 8.55 | MIN targets 6/2 in W2/W3; W4 absent; divided by three → 2.67 | **VERIFIED** arithmetic, **NOT ESTABLISHED** that absence implies a continuing reduced role. Need coverage, participation and current availability evidence before interpreting the low anchored mean as football truth. |

**LIKELY remaining weakness:** common-window workload averages blend participation probability with conditional active-game role, while fantasy means also apply availability. This can depress a returning player's role or apply an absence effect twice. Conversely, disabling an anchor for entirely missing same-team history exposes an old model fallback without a proven new-team role. These are general research questions; no player-specific correction is justified.

## 9. Remaining limitations and required evidence

- Preserve raw versions by ingest run and select the latest receipt-qualified version in every reader. Existing immutable CSV capture helps recover this incident, but does not make destructive raw refresh acceptable.
- Freeze canonical alias mappings, roster/team membership, current context, source hashes, original receipt timestamps, code/config versions and coverage/participation evidence with every forecast. Record absent-versus-not-received explicitly.
- Rebuild each training game's opportunity features from its own prelock package; use later labels only after its forecast. Reject final-stat reconstruction as a time-safe substitute.
- Complete paired refit integration for market reconciliation and candidate-specific anchor/calibration stages. Research helper refusal is intentional; the complete requested walk-forward experiment remains blocked.
- Gather independent Sunday Main weeks covering starters, backups, trades, injuries, returns, low-history players, stale prior-season windows and missing same-team history. Freeze both policy forecasts before outcomes arrive. Future evidence collection is a requirement, not an automation created by this task.
- Validate QB and DST labels and full salary-pool outcome coverage separately; do not treat absent statistical rows as DNP without sourced participation evidence.

## 10. Production promotion gate

These are parked research-study thresholds from the original request, not prerequisites for fixing identifiable pipeline defects or resuming optimizer work; they are not empirically validated constants or a promotion authorization.

| Gate | Required evidence | Current status |
| --- | --- | --- |
| Point-in-time integrity | Hash-verified immutable receipts for every source and identity/roster/context domain; per-game historical training snapshots; exact replay or a fully documented same-source paired rebuild | FAIL: partial recovery only |
| Independent sample | At least 12 distinct evaluation weeks: ≥6 validation weeks and ≥6 untouched subsequent test weeks; adequate prior training/calibration; ≥100 labeled players per principal position and ≥50 per critical role/history group across ≥3 weeks, otherwise defer | FAIL |
| Workload | Paired RB carries, RB/WR/TE targets and team budgets: upper 95% week-cluster CI for relative MAE/RMSE regression ≤2%; no material missing-forecast coverage loss; bias and residual allocation explained | NOT ESTABLISHED |
| Fantasy | Test equal-week MAE improves, or upper 95% paired CI excludes >2% MAE/RMSE regression; at least one predeclared workload/fantasy metric shows credible improvement | NOT ESTABLISHED |
| Group safety | No unexplained >5% MAE/RMSE regression in position, price, starter/backup, low-history, new-team, injury-return or missing-history groups; insufficient group evidence means defer | NOT ESTABLISHED |
| Distribution | Test coverage near 80% (75–85% overall); both tail miss rates near 10% (5–15%); no material interval-score regression; subgroup sample adequacy and uncertainty reported | NOT ESTABLISHED |
| Missing role history | Unknown workload is distinct from zero; forecast reports disclose fallback source/freshness and role confidence; inactive/returning-player behavior validated without participant-conditioned double suppression | FAIL: fallback confidence not validated |
| Regression and operations | Identity, transforms, feature leakage, source-replay, policy default and projection contract tests pass; originals preserved; code/config frozen and rollback documented | Targeted tests pass; complete production study gates remain open |

Evaluate all gates on independent weeks and paired cohorts. A tiny RMSE improvement alongside worsening workload, unexplained missingness or wider intervals is insufficient. Week 5 totals and optimizer selections are never gate criteria. Final decision is **INSUFFICIENT EVIDENCE**, not PROMOTE and not a rejection of the identity/allocation repair itself.

## Focused stabilization after the scope change

The user stopped broad historical reconstruction and prioritized correct, explainable projections followed by optimizer issues. Historical research is parked. **VERIFIED fixes:** saved explanation replay now includes the stored market correction and production zero floor before participation scaling. Missing/NaN/pandas-NA support flags cannot count as positive workload evidence or activate a repaired anchor. New persisted explanation fields identify anchored versus historical fallback means, explicit current workload, partial same-team windows, prior-season windows, and missing same-team history. Review flags explain uncertainty; they do not invent workloads, exclude players or change optimizer preferences.

Current-slate regression checks representative positions and the largest saved market corrections against their frozen Week 5 means, without outcomes; opportunity evidence is reviewed across the full 310-player pool. Nine representative explanation means reproduce with maximum error 0.0. The full pool evidence CSV flags 108 players (81 partial-window, 27 missing-history) for review, rather than repeatedly tuning individual players. The corrected policy remains opt-in; the existing 55%/70% weights are preserved. General injury-return role forecasting is still a model improvement question, not silently “fixed” by replacing observed missing games with invented workload.

Next work returns to remaining practical optimizer issues, starting with preference-versus-football-availability separation (parked C09), while keeping this research available. No broad data-reconstruction project or automatic future collection is scheduled.

## 11. Reproducible scripts, tests and artifacts

Run from the repository root:

```sh
# Optional read-only local DB metadata refresh; never reads Week 5 outcomes.
.venv/bin/python scripts/capture_classic_projection_validation_inventory.py
# Offline audit/recovery; reads frozen originals and writes only new evidence.
.venv/bin/python scripts/audit_classic_projection_validation.py
.venv/bin/python scripts/validate_classic_projection_explanations.py
.venv/bin/python -m unittest scripts.test_classic_projection_validation
.venv/bin/python -m pytest backend/app/tests/product/test_opportunity_team_window.py backend/app/tests/product/test_prediction_calibration.py backend/app/tests/product/test_canonical_projection_inputs.py -q
```

Evidence lives in `artifacts/classic_projection_validation/`: database inventory, surviving source receipt inventory, recovered source receipts/checksums, original/recovered source parity, paired forecasts saved before labels, labeled player diagnostics, workload/fantasy/calibration cohort metrics, team allocations, Week 5 evidence, test logs and SHA-256 manifest. Original `artifacts/classic_opportunity_repair/` files are read-only inputs; the audit checks every original file's before/after hash. It also rechecks recovered source-file hashes.

Research framework: `scripts/classic_projection_validation.py`. Regression suite: `scripts/test_classic_projection_validation.py`. Targeted results: **12 research guard tests, 84 projection stabilization tests and 97 optimizer/preparation boundary tests pass**. The latter verify Classic/Showdown preference exclusions preserve model assessments, optimizer modes and preparation contracts. They establish fixture behavior, not current live lineup clearance. No full application suite or production deployment was performed; passing these tests does not replace the missing historical experiment.
