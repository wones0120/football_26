# Dedicated DST model — validation failed; live unchanged

**The dedicated DST policy fails its frozen MAE improvement gate.** On the exact same 446 corrected outcomes, MAE changes **4.32247 → 4.35703** (+0.03455). The paired week-cluster 95% interval is **[-0.10944, +0.17797]**, so this is inconclusive rather than evidence of improvement. Seven other gates pass. No criterion, learner or feature was changed after inspecting the new results, and no model was promoted.

This is a separate DST-only model-design experiment after the prior shared-tree corrected-label refit failed. The [protocol](CRITERIA.md) was written before fitting, SHA256 `978406146d9e8a7c5c2c90dbed4ca687e218034a2c8510bcbcc0e1a5636b70f8`. **All evaluation outcomes were previously inspected, and original pregame capture clocks remain incomplete. These are retrospective chronological comparisons, not a new blind holdout or a claim of fully attested historical source timing.**

## Structural defect and implemented correction

The frozen production artifact shares one GradientBoosting model across offense and DST. Its 27-feature DST input has **18 constant/all-missing columns** across all804 DST samples. `is_home` is always zero; all player history, opponent-position history, snap and offense-role completeness inputs are zero, while offense-role importance is entirely missing. The four market columns have28 missing rows. A previous label-only correction could not repair those feature contracts.

The new research module, [dedicated_dst_model.py](../../../backend/app/product_services/dedicated_dst_model.py), builds a separate **17-feature DST contract** from salary/markets, checked canonical game home identity, and strictly prior verified defense/opponent-conceded history. It repairs402 home flags. History includes prior score means/dispersion, sacks, takeaways and points allowed; no current-game component or outcome enters its features. Prior histories use1,298 complete canonical team/game outcomes rather than sparse/zero-filled matrix fields. The training target remains the exact same804 canonical matrix rows. Unknown history/markets remain missing until train-only median imputation with indicators; genuine observed zeros and negative scores remain intact. Existing lagged missing-share fields are excluded because their DST source completeness and zero meaning are not established.

Source selection requires verified snapshot `e81b5772-5d81-505b-a44c-0660480098c4`, SHA256 `1ee194029dcdb0d7e8ffc075394ae9e470d00a2635dd51b474f580fce7f7b2ff`, scoring `draftkings_classic_dst_event_scoring_v1`. The strict selector replaces285 of804 labels; all804 match the independent canonical event outcome. Component/history sources and the32-UUID identity map are separately hashed. Missing scores, duplicate game identities, wrong UUID/team/game/version, and incomplete coverage reject. No display-name joins, fabricated starter assumptions or opponent-QB features are used. Original matrix values, source bytes and live feature builders remain preserved. See the [source/feature audit](feature_source_audit.json) and [independent scoring repair](../../dst_scoring_repair_20261015/v1/REVIEW.md).

## Bounded model comparison

The frozen candidate set is a training-label median, standardized Ridge(alpha100), and a shallow regularized HistGradientBoosting tree (depth2,100 iterations, minimum30 samples/leaf,L2=10). Inner selection uses the last three training weeks, with model fitting only on earlier weeks. No outer test/calibration result selects a learner. After selection, each learner is refit on its whole outer training window.

For2025,246 DST training rows end2024W13;112 remaining2024 rows calibrate intervals. For2026,602 training rows end2025W13 (noW14 rows exist),54 later2025 rows calibrate. Both arms score corrected test truth; the incumbent is its original shared-position policy refit on the prior window, including its existing zero-fill,80/20 history blend and nonnegative prediction rule. All446 incumbent predictions and corrected labels reproduce the prior study exactly. Candidate point predictions permit negative values. 80% intervals use each arm's prior10th/90th residual quantiles. Histories update with completed prior weeks; parameters/calibration never fit on outer evaluation rows.

Inner choice: shallow tree for the2025 block, Ridge for both2026 blocks. [All inner scores and chronology](inner_selection.json).

| Block | N | MAE incumbent → dedicated | RMSE incumbent → dedicated | Bias incumbent → dedicated | 80% coverage incumbent → dedicated |
|---|---:|---:|---:|---:|---:|
| 2025 retrospective |298|4.426 →4.430|5.816 →5.614|-0.863 →-0.120|82.9% →83.6%|
| 2026W1–3 retrospective |90|4.358 →4.442|5.653 →5.684|-0.265 →+0.434|85.6% →78.9%|
| 2026W4–5 previously inspected |58|3.737 →3.848|4.751 →4.758|+0.979 →+0.934|81.0% →82.8%|
| Combined |446|**4.322 →4.357**|**5.656 →5.525**|**-0.503 →+0.129**|**83.2% →82.5%**|

Combined2026 MAE is4.11458 →4.20954. Mean per-week Spearman ranking correlation improves0.260 →0.301 overall, and0.022 →0.128 in2026. Average80% interval width narrows15.316 →14.885 points. Only18 week clusters (five current-season weeks, two in the inspected block) support the intervals. Calibration bins, individual weeks and block-level uncertainty remain explicit in [validation](validation.json) and [row predictions](heldout_predictions.json).

Error improves in the rare defensive/ST-touchdown stratum (46 outcomes;9.639 →8.557 MAE), but worsens on the much larger no-defensive/ST-TD stratum (400 outcomes;3.711 →3.874). On15+ actual scores (41 outcomes), MAE improves12.636 →11.620 while remaining large. These are total-score errors conditioned on observed components, not fitted component heads. Both models still poorly resolve the volatile tail. [Component/tail and weekly diagnostics](diagnostics.json).

The failed gate required at least0.05 MAE improvement. RMSE, combined2026 noninferiority, bias, aggregate coverage, paired uncertainty and rank gates pass. Improved RMSE/rank/bias do not establish the required point accuracy gain. No post-result tuning or relaxed gate is proposed as a pass.

## Sunday shadow — same roster, no differentiated DST ranking

After evaluation, the frozen inner selection rule applied to all804 prior DST training rows selects the **median baseline**, beating Ridge/tree on its last-three-training-week MAE (3.909 vs3.957/4.026). Its full-history median is **5 points for every defense**. Thus all20 Sunday DSTs tie at rank1;19 numerical ranks differ, but this supplies **no ranking signal** and is not evidence that19 defenses improved. [Exact canonical rankings and salaries](sunday_defense_rankings.csv).

Only DST means are substituted into the frozen201-player eligible pool from run `f84e75db-b286-48f4-8740-c03d11323889`, projection `b2ae485d-f436-470b-a52c-fa53095bbd4d`, cutoff2026-10-15T19:17:26.763111Z. Every non-DST cell, salary, ownership, eligibility and user setting is identical. Both pure highest-baseline-mean solves are Optimal with no relaxed constraints. The roster remains Stafford, Kyren Williams, Derrick Henry, Puka Nacua, Carnell Tate, Tyler Higbee, Wan'Dale Robinson, Rome Odunze and Carolina DST; **$49,800**, baseline133.1430 →shadow133.5307. The whole+0.3877 difference is Carolina4.6123 →5.0. This is a hypothetical forecast change, not realized improvement. [Pools, canonical lineups and solver audits](matched_lineups.json).

## Artifacts, live protection and reproducibility

[Versioned research artifact](dedicated_dst.joblib), [training/feature/source/code hashes and manifest](candidate_manifest.json), [experiment script](run_experiment.py), [diagnostic script](diagnostics.py). The full-history fit is not included in validation metrics. No new dependency or production-serving integration was introduced.

The actual active Main pointer at this experiment's start was already `28f764f0-6fe9-4463-b55e-c6c93804848c`, different from the older frozen research snapshot. Both the actual active288-row projection and the preserved288-row research projection are independently read and hashed before/after. **The actual current pointer and every mean remain unchanged.** [Before](live_before.json), [after](live_after.json). No live Prepare, model promotion, optimizer save, export or contest entry occurred. Morning work and offense models were untouched.

Validation: **29 focused tests pass**, covering strict verified label selection, missing-vs-real-zero histories, no current/future-week feature leakage, canonical identities/duplicates, no offense/QB feature path, frozen model parameters and train-only imputation/selection. [Test output](tests.txt). Python compilation and diff whitespace checks pass. The existing Entry History work was validated separately and is unrelated to these modeling results.

From repository root, reproduce offline with:

```sh
PYTHONPATH=. LOKY_MAX_CPU_COUNT=2 .venv/bin/python research/dst_dedicated_20261016/v1/run_experiment.py
PYTHONPATH=. .venv/bin/python research/dst_dedicated_20261016/v1/diagnostics.py
PYTHONPATH=. .venv/bin/python research/dst_dedicated_20261016/v1/finalize_manifest.py
PYTHONPATH=. .venv/bin/python -m pytest backend/app/tests/product/test_dedicated_dst_model.py backend/app/tests/product/test_dst_training_labels.py -q
```

`verify_live.py before|after` uses read-only local database transactions. Source correction paths come from the retained receipt; all offline inputs are preserved locally. This version is rejected for live use. The structural research fix is available for a separately declared future model design; a validated scorer and reviewed serving integration are still needed before replacing live DST projections.
