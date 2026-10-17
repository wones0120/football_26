# DST rankings — reliable advantage not demonstrated

**Neither bounded ranking alternative passes the frozen reliability gates. Keep live projections unchanged and do not promote a new defense ranking.** The fixed ensemble improves recent MAE, but its pairwise ordering advantage over the incumbent is only **+0.15 percentage point**, with95% week-cluster interval **[-5.49,+4.85] percentage points**. The ranking selector is slightly worse on aggregate ordering. Both uncertainty intervals also include no advantage over the flat baseline.

All five2026 weeks and the2025 reference were previously inspected. These are retrospective rolling comparisons, not fresh blind validation. Historical pregame capture clocks remain incomplete; using strictly prior games reconstructs available statistics but does not prove when the original system captured them.

## Why five points wins

The old full-history inner selector minimizes pooled absolute error over88 prior rows in2026W3–5. Median5 scores **3.90909MAE**, shallow tree **3.91171**, and Ridge **3.98973**. Its rule correctly picks the median by **0.00261464point** over the tree. The paired three-week95% tree-minus-median interval is **[-0.30468,+0.36671]**: selection is highly uncertain. Earlier fitting windows chose tree/Ridge; a three-week point-loss selector is unstable in this small, volatile sample.

This is an objective/selection result, **not another broken home/history delivery path**. All14 repaired future inputs vary across the20 defenses, home has both values, and every field is present except six missing prior meetings with the particular opponent. Those missing meetings stay explicit until train-only imputation. Real rolling-score histories are nonconstant. Fresh repair from the raw frozen target followed by artifact inference reproduces every future score exactly. [Selection/input diagnosis](selection_diagnosis.json), [fresh artifact parity](artifact_scoring_parity.json).

The base models are not flat: future Ridge has20distinct forecasts, range0.959–8.951/std2.022; tree has20distinct forecasts,4.114–8.525/std1.534. Their frozen regularization is intentionally conservative (Ridgealpha100; tree depth2,minleaf30,L2=10), but it does not force the five-point outcome. The selector chooses the valid training median. MAE rewards a conditional median and does not reward correct pair ordering directly; replacing the selector merely to produce variance would not establish useful ranks.

## Frozen experiment

[Protocol](CRITERIA.md), SHA256 `52b140d6f824f005c12f76a3000ae9c76e195711138f96dbb4b6d4a461cc17cb`, was written before new evaluation. No feature, parameter, weight, threshold or gate changed after results.

Reused inputs are the same804canonical DST rows, corrected scoring snapshot `e81b5772-5d81-505b-a44c-0660480098c4`, scoring `draftkings_classic_dst_event_scoring_v1`, prior-only histories from1,298 verified team/game outcomes, and the inactive14-field matrix/training/prediction contract. No opponent-QB features or inferred future starters enter any arm. All test/calibration truth is corrected; the incumbent refit retains original training labels/features to represent the existing policy. All alternative arms share corrected labels/features/splits, so their only declared difference is selection/combination policy.

Primary recent tests are2026W1–5,148rows/five week clusters, with a separate expanding origin for each week. Calibration uses the last three **prior** observed DST weeks; fit rows precede calibration. Inner selection uses a separate last-three-fitting-week block and fits its component candidates on still earlier weeks. Missing calendar-week source coverage is never invented. Histories update from strictly earlier weeks, while model parameters/calibration never fit on outer evaluation labels. [Every origin, count and cutoff](selection_audits.json).

The2025 reference retains all298rows on the prior pre2024W14 fit/later2024 calibration split. All arms have the same cohort. The two-row2025W16 slice remains in point metrics and is explicitly unsupported for primary ranking; the12supported2025 weeks contain296rows. This avoids treating a single pair as equal evidence to a normal slate while preserving its original evidence.

Arms:

- Current incumbent shared-position model policy, refitted chronologically.
- Flat corrected-training-label median.
- Existing repaired dedicated MAE selector: same median/Ridge/tree candidates and inner rule.
- Fixed ensemble: **.50median +.25Ridge +.25tree**, no estimated weights or tuning.
- Ranking selector: same candidates plus that ensemble, selected by supported-week pairwise ordering on inner data, with MAE<=median+.15 guard and pairwise>=.52. It retains the median fallback when no variable candidate qualifies.

Main evaluation/refits use **33bounded fits**, shared across all policies. Two fixed prefix-model replays add inner uncertainty diagnostics; a diagnostic output-assembly retry executed two extra identical fits, bringing this session to37, below the45fit budget. No sweep or post-result alternative was attempted.

## Recent results: point stability does not establish ranking skill

|Policy|MAE|RMSE|Bias|Pairwise accuracy|Spearman|Top5 actual mean|Top5 regret|80%coverage|
|---|---:|---:|---:|---:|---:|---:|---:|---:|
|Incumbent|4.1590|5.3774|+0.3066|54.75%|0.1519|5.920|8.640|77.03%|
|Flat|4.1149|5.3024|+0.0068|50.00%|0.0000|5.796|8.764|83.11%|
|Existing MAE selector|4.3086|5.4127|+0.7407|53.94%|0.0969|7.080|7.480|77.03%|
|Fixed ensemble|**4.0598**|**5.2374**|+0.3387|54.90%|0.1409|6.280|8.280|83.78%|
|Ranking selector|4.1875|5.3362|+0.6508|54.61%|0.1212|6.960|7.600|75.68%|

Pairwise comparisons exclude tied actual outcomes; predicted ties get.5credit. Constant forecasts have Spearman0, explicitly no ordering information. Top5 uses fractional boundary ties, so the flat forecast's expected top5 outcome is the cohort mean; no alphabetical or favorable team tie-break is used. Regret is the oracle top5 actual mean minus the selected expected actual mean. Rank/top5 metrics give each week equal weight; point error is row weighted.

The ensemble's MAE difference versus incumbent is-0.09915,95% interval[-0.35075,+0.10920]; RMSE difference-0.14006, interval[-0.32819,+0.01476]. These point improvements are also uncertain. Its mean top5 regret falls0.36points, but95%interval[-2.08,+1.20] includes deterioration. The ranking selector lowers top5 regret1.04points, interval[-2.76,+0.40], while its pairwise advantage is-0.14percentage point, interval[-8.78,+6.24]. No reliable rank advantage is demonstrated.

### Every recent week

|Week|N|Incumbent pairwise|Flat|Existing MAE|Ensemble|Rank selector|
|---|---:|---:|---:|---:|---:|---:|
|1|28|59.07%|50.00%|64.87%|59.21%|64.87%|
|2|32|47.74%|50.00%|51.40%|52.47%|53.98%|
|3|30|51.44%|50.00%|47.85%|51.67%|47.85%|
|4|30|61.14%|50.00%|66.84%|67.59%|67.59%|
|5|28|54.35%|50.00%|38.76%|43.54%|38.76%|

Exact values rather than rounded percentages are in [weekly metrics](weekly_metrics.json). The ensemble improves pairwise accuracy versus incumbent in4/5weeks, but its Week5 reversal wipes out most average gain. The ranking selector improves3/5weeks and worsensWeeks3/5. Week4 is strong for the new forecasts; it is not representative enough to cherry-pick. Week5's variable forecasts have negative Spearman (ensemble-0.176, ranking selector-0.327), so greater spread clearly does not imply skill.

### Historical consistency reference and gates

On2025, supported-week pairwise accuracy is61.14% incumbent,50% flat,61.00% existing MAE,62.29% ensemble/rank-selector. Point MAE is4.42572 incumbent,4.60738 flat,4.40224 existing selector and4.44317 ensemble/rank-selector. These historical results meet the declared non-regression guard but do not resolve recent uncertainty.

Both alternatives fail the predeclared recent pairwise level/improvement and lower-confidence-bound gates. The ranking selector also fails the4/5week consistency requirement. Point accuracy, bias, calibration, historical consistency and mean top5 regret gates pass; passing those does not substitute for reliable ranking. All gates, calibration bins, widths, sample counts and rank uncertainty are in [validation](validation.json). [Paired point uncertainty and score strata](point_uncertainty_and_strata.json), [all canonical row predictions](row_predictions.json).

## What the alternative inner objective changes

Full-history inner selection still picks the median under the original MAE-only three-candidate rule. The fixed ensemble, a separately predeclared fourth alternative, has3.83032innerMAE; its difference versus median is-0.07877,95%three-week interval[-0.26600,+0.02902]. It remains uncertain. The ranking selector chooses the tree because its inner pairwise mean57.50% beats ensemble56.94%, Ridge54.12%, median50%, while its tiny MAE penalty meets the guard. These choices use only inner data.

Changing the objective therefore **can** produce ranks, but the rolling outer results show those ranks are not reliably better. [Per-model/per-week inner MAE, pairwise results, dispersion and uncertainty](inner_loss_diagnostics.json); [inner row evidence](inner_row_predictions.json). No final-history inner score is presented as independent validation.

## Sunday shadow, not a recommendation

All20 scores/ranks are saved in [Sunday CSV](sunday_defense_rankings.csv). The existing MAE policy/flat control stay5for every defense. The fixed ensemble ranks KC6.780,NE6.689,BAL6.626, with CAR6.600 fourth. The ranking selector's tree ranks NE8.525,IND8.439,BAL8.247, with CAR8.101 fifth. The ensemble changes14numerical ranks and the ranking selector16; these are failed-reliability research forecasts, not recommended live ranks. No new injury/news refresh is implied.

Only DST means are substituted into the exact201-player eligible pool from saved run `f84e75db-b286-48f4-8740-c03d11323889`, projection `b2ae485d-f436-470b-a52c-fa53095bbd4d`, cutoff2026-10-15T19:17:26.763111Z. Salary,ownership,userpreferences,eligibility and every non-DST cell are unchanged. All five exact highest-baseline-mean solves are Optimal without relaxation.

Every arm keeps the **same $49,800 roster**: Stafford,Kyren Williams,Derrick Henry,Puka Nacua,Carnell Tate,Tyler Higbee,Wan'Dale Robinson,Rome Odunze,Carolina DST. Lineup means are133.1430 incumbent,133.5307 flat/existing selector,135.1312 ensemble and136.6314 ranking selector. The differences are forecast substitutions, not measured performance gains. [Canonical lineups, frozen pools and solver audits](matched_lineups.json).

## Promotion recommendation and reproducibility

**Do not promote either ranking alternative.** Preserve the repaired inactive feature contract, corrected truth and median control. Additional genuinely prospective weeks with retained source timestamps are needed to test ranking stability and target-tail behavior. This task's37bounded fits, known retrospective outcomes and five recent clusters cannot establish fresh reliability. No parameter sweep, fallback removal or threshold relaxation follows this failure.

[Research artifact](ranking_candidate.joblib) preserves both fitted base learners, all policy selections, verified context, training/target features, source/scoring/code/runtime hashes and proposed forecasts. `policies.predict(repaired_targets,policy='ensemble'|'rank_selector')` is reproducible, and [fresh artifact scoring parity](artifact_scoring_parity.json) confirms exact20-row results from raw frozen targets. [Manifest](candidate_manifest.json). The new `dst_rank_policy.py` is research-only and imported by no live route or default.

Read-only [before](live_before.json)/[after](live_after.json) checks confirm the actual current Main pointer `28f764f0-6fe9-4463-b55e-c6c93804848c` and all288live means remain unchanged; the older frozen projection's288means are independently unchanged. No live fitting/regeneration, model promotion, matrix rewrite, optimizer save, export or contest entry occurred.

Validation: **39focused tests pass**, including5new tests for tie-aware top5, actual/prediction ties, permutation invariance, variance-versus-skill, fixed ensemble weights, temporal separation, unchanged train-only imputation and retaining the median fallback. Existing source/feature/leakage tests also pass. [Test log](tests.txt). Compilation and diff checks pass.

Reproduce offline:

```sh
PYTHONPATH=. LOKY_MAX_CPU_COUNT=2 .venv/bin/python research/dst_rank_stability_20261016/v1/run_experiment.py
PYTHONPATH=. .venv/bin/python research/dst_rank_stability_20261016/v1/diagnostics.py
PYTHONPATH=. LOKY_MAX_CPU_COUNT=2 .venv/bin/python research/dst_rank_stability_20261016/v1/selection_diagnostics.py
PYTHONPATH=. .venv/bin/python research/dst_rank_stability_20261016/v1/finalize_manifest.py
```

A clean reproduction uses33main+2diagnostic fits; this first session's diagnostic output retry is retained separately in the manifest. `verify_live.py before|after` performs only read-only DB checks. Source paths and immutable correction receipts are inherited from the prior verified experiment. No runtime activation is part of these scripts.
