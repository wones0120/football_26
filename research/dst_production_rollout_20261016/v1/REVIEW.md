# Corrected DST production rollout staging

**Implementation complete; forecast activation pending acceptance. No live forecast, model pointer or stored projection changed.** The unrelated four-player availability guard was not bypassed. Thursday audit is checkpointed at `research/thursday_entry_portfolio_audit_20261016/v1/RESUME.md` for resumption.

## Root cause and correction

The old matrix DST branch skipped the normal player-history path and supplied missing game/home/history as zero or empty values. Eighteen of 27 input columns were constant/missing; all 804 training DST home flags were zero. The original fantasy labels also omitted verified DST scoring events. A corrected-label shared model alone worsened MAE. The repaired canonical DST adapter supplies true home/away and strictly prior defense/opponent scoring history to both training and inference, preserving missing history separately from true zero and retaining corrected event-scored outcomes with source hashes. Opponent-QB experimental features remain excluded.

The later flat five-point result has a different cause: MAE selection favors a median by only 0.0026 points over the regularized tree on the last three training weeks. Repaired inputs reach all components; the median legitimately ignores them. Replacing a tie with fabricated variation would not fix ranking.

## Existing validation, unchanged conclusions

| Experiment | Compared outcome | Conclusion |
|---|---|---|
| Frozen repaired dedicated policy, 446 corrected outcomes | MAE 4.3294 vs incumbent 4.3225; RMSE 5.4947 vs 5.6559 | Passed all nine frozen point/noninferiority gates; Sunday final selector is flat five |
| Fixed ensemble, 5 rolling recent weeks / 148 outcomes | MAE 4.0598 vs 4.1590; RMSE 5.2374 vs 5.3774; bias +0.3387; 80% coverage 83.78% | Favorable point estimates; not proof of superiority |
| Ensemble recent ranking | Pairwise 54.90% vs incumbent 54.75%; delta +0.15 percentage points, week-cluster CI −5.49 to +4.85 points | Failed predeclared ranking superiority/uncertainty gates; W5 worsens |
| Fixed ensemble, 2025 reference / 298 outcomes | MAE 4.4432 vs 4.4257; pairwise 62.29% vs 61.14% | Retrospective reference, modest mixed effects |

Recent ensemble MAE delta CI is −0.3508 to +0.1092; rank evidence includes zero against the flat baseline too. All outcomes were previously inspected. Original historical capture clocks are incomplete. A later deployment standard or acceptance decision cannot turn this into a fresh blind evaluation or erase failed gates.

## Football mechanism and recommendation

The ensemble has a defensible but incompletely validated mechanism: corrected own defense and opponent-conceded history, true home/away and current market environment feed a small regularized model; a 50% median anchor shrinks noisy DST event forecasts. Forecast dispersion itself is not evidence of skill. Current quarterback/line injuries are not silently invented or encoded; the excluded experimental QB features remain excluded. There is no possession accounting or calibrated joint-game probability claim.

For a differentiated repair, recommend the fixed ensemble only under an explicitly recorded, limited Week 6 **forecast noninferiority acceptance** that acknowledges uncertain ranking superiority and retrospective timing limitations. This is a separate operational decision, not a passed research gate. If the required standard remains demonstrated rank superiority, retain the incumbent. The validated MAE-policy alternative can provide corrected forecast lineage today but would still be flat five, so it does not solve useful defense differentiation. No acceptance decision has been manufactured in this task.

The saved Sunday shadow comparison remains matched to old valid inputs, not fresh Sunday readiness. Ensemble top DSTs are KC 6.780, NE 6.689, BAL 6.626, CAR 6.600. CAR remains the selected defense because a higher absolute defense mean costs salary that reduces the rest of the roster. The matched optimal $49,800 roster remains Stafford / Kyren / Henry / CAR / Puka / Tate / Higbee / Wan'Dale / Odunze. Total mean changes 133.143 to 135.131; all other player means, salary, ownership, eligibility and user constraints are fixed. This is expected-score sensitivity, not a tournament win-probability statement.

## Concrete production implementation

- `dst_deployment.py`: checksum-pinned selection/component, explicit acceptance decision and evidence, source/feature/calibration validation, canonical keyed overlay, exact target-period expiry, explicit failure. Empty default preserves incumbent. Two pending selections are staged; isolated verification selections are marked **ISOLATED_TEST** and never configured.
- Normal canonical Prepare replaces only DST means after legacy opportunity/market reconciliation, then applies dedicated DST calibration. The existing shared offense model and inputs remain numerically unchanged. Corrected DST forecasts do not receive legacy market adjustments twice.
- Fitted artifacts embed both components and verify both forecasts on reload. DST explanations show corrected actual inputs, decision lineage and limitations; they do not attribute DST forecasts to an unrelated shared tree.
- Combined model IDs/feature hashes distinguish the DST policy. Gold feature JSON retains corrected `dst_serving_component_inputs` and source metadata records training-feature, event, identity, calibration and artifact hashes. Legacy saved artifacts remain readable.
- Both components are frozen to 2026 W6. Future weeks fail rather than silently using stale support.
- Exact current pointer/artifact checksum and rollback procedure are in `rollback.json`. No restart was performed by this task and the deployment configuration keys remain empty.

## Verification

`stage.py` creates the two concrete components with **zero new fits**. Both reproduce the 20 saved Sunday DST forecasts.

`verify_prepare.py` uses the actual canonical Prepare scoring path and serializer against the preserved valid 288-player snapshot; persistence is intercepted. All **268 non-DST forecasts are bit-for-bit unchanged**, both components supply 20 DST means and separate 88-row prior residual calibration, and saved-artifact DST explanations match within 1e-12. Batch artifact rescoring is exact. This is not a fresh complete-slate Prepare or a database-persisted accepted forecast.

Targeted tests cover acceptance/hash rejection, canonical overlay and true home/history delivery, source/offense immutability, expiry/overlap/identity failure, legacy compatibility, component reload/explanation, and invalid selection failing before fit/persistence. The full focused command and final result are recorded in `delivery.json`.

## Smallest remaining path

Resolve and record the deployment standard; notify the coordinating parent before configuring an accepted selection. Then coordinate idle API+worker restart, run a valid scoped Prepare, verify selected component/source/quantile lineage and matched offense parity, and explicitly advance the intended slate pointer. Preserve the recorded baseline as rollback. An unrelated fresh-player source blocker must remain explicit and must not be repaired by claiming unknown players healthy. No further broad research sweep is needed to make the acceptance decision.
