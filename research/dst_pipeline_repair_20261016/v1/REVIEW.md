# DST feature-pipeline repair — inactive candidate verified

**The production feature defect is repaired in an explicit inactive candidate path, and the repaired dedicated policy passes all nine predeclared statistical gates. Live projections remain unchanged.** Its MAE is4.32941 versus4.44840 for corrected-label/unrepaired inputs and4.32247 for the original incumbent policy. This is **noninferiority to the incumbent, not proof of improved current-model accuracy**: the paired95% MAE difference versus incumbent is+0.00694, interval[-0.13143,+0.14024].

The repaired shared model and simple historical baseline fail. The full-history dedicated selector still chooses the median baseline, giving all20 Sunday DSTs5points; it supplies no differentiated ranking. Statistical acceptance does not justify quietly deploying either the failed shared model or an arbitrary new defense ranking. All models remain candidate artifacts; this task makes no live activation.

## Exact root causes

1. `LineupLearningService._compute_player_projection_lookup` explicitly skips DST before the offense/player-history payload is assembled. Its team defense projection lookup is a separate heuristic, not the feature payload consumed by the shared predictor.
2. `rebuild_player_game_feature_matrix` builds a separate DST placeholder dictionary: `game_id=None`, `is_home=None`, history count0 and all rolling/opponent history fieldsNone. Thus team outcomes never reach those model fields, even when schedules and prior results exist.
3. Canonical `prepare_inputs` fills non-market base-feature NaNs with0, and shared fitting/scoring again fills NaNs0. A later market update can recover a missing game ID but does not reconstruct home/history. Consequently all804 DST rows have home0 and empty histories;402 real home games are represented as away.
4. The point-history blend sees count0 and falls back to the training position mean. It never uses the available canonical defense-game history. The previous corrected-label-only experiment could not fix this.

## Implemented path and isolation

[dst_feature_pipeline.py](../../../backend/app/product_services/dst_feature_pipeline.py) supplies one canonical adapter for matrix generation, training and inference. It resolves game identity from checked canonical UUID/team/week evidence, populates home and the existing real matrix history fields, and derives defense/opponent-conceded histories only from complete outcomes in **strictly earlier NFL weeks**. Current/future-week values cannot enter features. Missing history remainsNaN and real observed zeros remainzero. Candidate matrix generation preserves missing future labels instead of the legacy pool's zero placeholder. Component and scoring source identities come from the previously independently verified event source.

The actual matrix builder now accepts an explicitly supplied `dst_candidate_context` **only with `persist=False`**. The resulting rows are returned as separate candidates; no delete/insert/commit branch runs. Its default behavior and existing callers remain unchanged. Canonical `load_dst_candidate_inputs` explicitly requires that context plus a verified corrected-label dataset, calls the normal canonical selection path, and applies the same repair to both training and prediction frames. It has no live route or automatic setting. `score_dst_candidate_bundle` is a concrete read-only artifact scorer: it checks that prediction weeks follow the training window, reconstructs the exact same fields, and returns only a DST overlay with `persisted=False`; offense predictions cannot be replaced accidentally.

This fixes the production branch's data contract without activating an unvalidated pipeline in the running app. The original historical matrix, corrected scoring evidence, offense cells and current live inputs remain preserved. No opponent-QB features, starter inference, new dependency, migration or display-name joins were added.

The source contract is the same804 canonical target rows from correction snapshot `e81b5772-5d81-505b-a44c-0660480098c4`, SHA256 `1ee194029dcdb0d7e8ffc075394ae9e470d00a2635dd51b474f580fce7f7b2ff`, scoring `draftkings_classic_dst_event_scoring_v1`. Prior histories use the verified1,298 team/game outcomes and32-UUID identity map. The repair restores402 home flags and prior history for all804 cohort rows. All source/frame/code hashes and missingness policy are preserved in [pipeline audit](pipeline_audit.json) and [manifest](candidate_manifest.json).

**Chronology limitation:** historical source capture clocks remain incomplete. These are later reconstructed, source-supported outcomes and retrospective prior-week features, not proof of what was captured at each original decision. Every test block was previously inspected. Frozen Sunday pool comparisons are model-design counterfactuals using the now-verified correction source, not claims that the corrections were captured by that pool's original cutoff.

## Frozen evaluation

[Criteria](CRITERIA.md), SHA256 `039ef66af6b8587e78abb9a536c38da8ee07261eb0c5b90dd13f39c3fe116e77`, was written before new fits/results. No learner, feature, tolerance or selection rule changed after evaluation.

Arms: original shared-model policy; corrected-label shared policy with unrepaired fields; repaired shared model with train-only median/indicator preprocessing; repaired dedicated model on14 football-relevant real matrix columns; and a fixed history baseline shrinking .65last3+.35last8 to the prior league mean with eight prior games of strength. The dedicated learner chooses among median, Ridge100 and a fixed shallow regularized tree using only the last three **training** weeks; no outer outcome chooses its model. It chooses tree for2025, Ridge for2026, and median for the future full-history artifact. [All inner scores](inner_selection.json).

Outer windows match the prior experiments: train before2024W14, calibrate later2024, evaluate2025; train before2025W15, calibrate later2025, evaluate2026W1–3 and separately already-inspectedW4–5. Both prior incumbent and corrected-label shared predictions reproduce exactly on every one of the446 canonical corrected outcomes. Histories update from earlier completed test weeks as operational rolling features would; parameters/calibration never fit on outer evaluation labels. The80% intervals use prior10th/90th residuals.

| Model policy | MAE | RMSE | Bias | Weekly rank correlation |80%coverage|Gate|
|---|---:|---:|---:|---:|---:|---|
|Original incumbent|4.32247|5.65586|-0.50299|0.26023|83.18%|Reference|
|Corrected labels, unrepaired shared|4.44840|5.69787|+0.34022|0.28315|83.18%|Feature control|
|Repaired shared|4.43227|5.80397|-0.22623|0.20414|85.65%|Fail|
|Repaired dedicated|**4.32941**|**5.49465**|**+0.20684**|**0.30250**|80.49%|**Pass declared gates**|
|Shrunk historical baseline|4.56857|5.79970|+0.03044|0.12405|84.08%|Fail|

|Period|N|Original MAE|Corrected/shared MAE|Repaired/shared MAE|Repaired/dedicated MAE|History MAE|
|---|---:|---:|---:|---:|---:|---:|
|2025 retrospective|298|4.426|4.536|4.637|4.402|4.742|
|2026W1–3 retrospective|90|4.358|4.420|4.278|4.422|4.469|
|2026W4–5 already inspected|58|3.737|4.045|3.619|3.812|3.831|

Combined2026 MAE:4.11458 original,4.27283 corrected/shared,4.01942 repaired/shared,4.18277 repaired/dedicated,4.21900 history. The dedicated policy meets the frozen<=original+.10 current-season allowance. Its absolute gain versus corrected/unrepaired shared is0.11899MAE, with paired95% difference[-0.31447,+0.05357]. Eighteen week clusters support aggregate uncertainty; only five current-season weeks and two already-inspected late weeks remain a substantial limitation. The interval includes no gain. This does not establish reliable superiority to the old incumbent or fresh prospective validation.

The repaired shared policy fails three aggregate gates: too little improvement over corrected/unrepaired shared, more than.05 above original MAE, and RMSE above the2% allowance. It improves2026 error but materially worsens2025 error. The history baseline fails accuracy/ranking gates. Criteria were not relaxed to accept them. Calibration bins, interval widths, per-period metrics, per-week ranks and tail/component strata are in [validation](validation.json), [row predictions](heldout_predictions.json) and [diagnostics](diagnostics.json).

Offense non-regression: every source/frame offense cell is unchanged by repair. Refitting a shared model can still change offense forecasts, which is why a serving proposal uses a DST-only overlay. Its heldout aggregate offense MAE changes4.37980→4.39588 in2025 and4.43990→4.40734 in2026, within the frozen.05 aggregate tolerance; position-level results remain in validation. A dedicated overlay preserves all offense predictions exactly. No offense model was deployed or rewritten.

## Sunday counterfactuals

All arms use the exact201-player eligible pool, salary/ownership/eligibility/user controls from saved run `f84e75db-b286-48f4-8740-c03d11323889`, projection `b2ae485d-f436-470b-a52c-fa53095bbd4d`, cutoff2026-10-15T19:17:26.763111Z. Only20 DST means change. Every non-DST cell is unchanged; each exact highest-baseline-mean solve is Optimal, with no relaxation.

|Arm|DST rank changes|CAR mean|Lineup mean|Roster/salary|
|---|---:|---:|---:|---|
|Original|—|4.6123|133.1430|Baseline $49,800|
|Repaired shared (failed)|17|7.4317|135.9625|Same $49,800|
|Repaired dedicated|19 numerical changes; all20tie|5.0000|133.5307|Same $49,800|
|History baseline (failed)|19|7.6438|136.1745|Same $49,800|

The full-history inner selector chooses median5.0, only narrowly ahead of the shallow tree on its last-three-training-week score (3.90909 vs3.91171; Ridge3.98973). All20 dedicated projections therefore tie at rank1: **there is no differentiated defense ranking**. Failed shared ranks put PIT first and CAR second, while the failed history baseline puts NYG first/CAR second; these are disclosed research results, not recommendations. [All20 exact scores/ranks](sunday_defense_rankings.csv).

The roster remains Stafford, Kyren Williams, Derrick Henry, Puka Nacua, Carnell Tate, Tyler Higbee, Wan'Dale Robinson, Rome Odunze and Carolina DST. Forecast increases are counterfactual model outputs, not realized performance improvements. [Exact pools, canonical rosters and solver evidence](matched_lineups.json).

## Ready for review; live unchanged

The concrete [candidate model bundle](candidate_models.joblib) stores fitted shared/dedicated pipelines, verified feature context, corrected training rows, target rows and model/feature/source/runtime hashes. `score_dst_candidate_bundle(bundle,target,arm='repaired_dedicated')` produces its read-only DST overlay. All three artifact-scoring arms reproduce every one of their20 saved future shadow means exactly: [artifact scorer parity](artifact_scoring_parity.json). Historical model selection, current feature delivery and artifact inference are independently checked.

Statistical status is PASS for the dedicated **policy**, FAIL for shared/history. Serving status remains **INACTIVE / NOT PROMOTED**. No route or default invokes the candidate context, so reloading the API cannot silently activate it. A future promotion review must explicitly choose the versioned artifact and DST-only serving policy, preserve offense, and address incomplete historical source clocks and the median artifact's absent ranking signal. This report does not authorize or perform that promotion.

Read-only [before](live_before.json) and [after](live_after.json) checks confirm the actual active Main pointer `28f764f0-6fe9-4463-b55e-c6c93804848c` and all288 active means are unchanged. The older frozen research projection's288 means are independently unchanged. No live matrix rewrite, model pointer update, projection regeneration, optimizer save, entry or export was made. Other agents' UI/API work is outside this experiment.

Validation: **86 focused tests pass** across the actual nonpersistent matrix-generation branch, canonical candidate loader, strict correction selectors, train/prediction parity, final artifact scoring, home flags, genuine zeros vs missing/future labels, current/future leakage, offense preservation, feature-matrix API compatibility and existing canonical/lineup-learning features. [Test log](tests.txt). Compilation and diff checks pass. Final code tightening added the verified-label requirement and the read-only artifact scorer without changing fitted feature/model arithmetic; original fit and final reviewed code hashes are both retained.

Reproduce from the repo root:

```sh
PYTHONPATH=. LOKY_MAX_CPU_COUNT=2 .venv/bin/python research/dst_pipeline_repair_20261016/v1/run_experiment.py
PYTHONPATH=. .venv/bin/python research/dst_pipeline_repair_20261016/v1/diagnostics.py
PYTHONPATH=. .venv/bin/python research/dst_pipeline_repair_20261016/v1/finalize_manifest.py
```

The scripts write only versioned local research artifacts. `verify_live.py before|after` uses read-only local DB transactions. Live activation remains a separate explicit, reviewed operation.
