# Additional candidate families for review

80 proposed stable IDs `X01-M01`–`X08-M10`, separate from the unchanged 240 G-series IDs. These extend the feature-platform wishlist; no measurement, source access, implementation or predictive value is claimed. Some are explicit variants/interactions of existing metrics, not independent signals. Preserve parent IDs and one underlying measured event rather than counting variants as new independent evidence. These are proposed definitions for user review before implementation.

All families inherit the shared contract: canonical/native game/player/team identity, predecision source clocks, exposure/coverage and null semantics. History uses specified prior games only; team/season/verified-DNP transport is explicit. Every candidate gets owner, source availability and exact model/report consumer during W0–W5. Source access and costs are unknown unless verified; no purchase is authorized.

For interactions, center continuous variables using training-only transforms. Any high/low/close/large-spread bin uses a predeclared threshold or training-only quantile, stored with version; no retrospective threshold choice from target outcomes. Compare home/away within role/team-adjusted cohorts; do not interpret sparse descriptive differences as causal effects. Quote total/spread/implied points must be genuinely available at the prediction cutoff. A derived interaction cannot fix a missing parent input.

## X01 — continuous and binned pregame context interactions

Owner: environment with QB/rushing/receiving. Parents G01,G02,G19–G21. W4; source/clock definitions start W0. Units are channel count/rate response to centered pregame conditions; binary interaction variants use the same target, not another physical budget. Require exposure by condition, within-time validation and shrinkage; no free model per tiny cell.

| ID | Candidate / proposed definition |
|---|---|
| X01-M01 | Team play volume × pregame total, continuous response |
| X01-M02 | Team pass rate × signed pregame spread, continuous response |
| X01-M03 | Team rush volume × team implied points, continuous response |
| X01-M04 | Home/away × pregame total interaction on team volume |
| X01-M05 | Home/away × signed spread interaction on pass/rush allocation |
| X01-M06 | Training-defined high-total × favorite/underdog channel response |
| X01-M07 | Training-defined low-total × favorite/underdog channel response |
| X01-M08 | Close-spread versus large-spread workload interaction, with declared sign |
| X01-M09 | Opponent pace × own pace on joint possession/play budgets |
| X01-M10 | Pregame total movement × role-specific opportunity, with comparable quote clocks |

## X02 — workload distribution beyond the mean

Owner: QB/rushing/receiving. Parents G03,G05,G06,G08,G17. W2 descriptive distributions, W5 forward distribution modeling. Units are count quantiles/variance/probability under an explicitly active-conditional or unconditional estimand. Sample games, role stability and forecast calibration are required; historical quantiles are not next-game predictive quantiles by relabeling.

| ID | Candidate / proposed definition |
|---|---|
| X02-M01 | Active-conditional target-count dispersion by role |
| X02-M02 | Active-conditional rush-count dispersion by role |
| X02-M03 | Active-conditional QB pass-attempt dispersion |
| X02-M04 | Observed zero-target rate among verified active participants |
| X02-M05 | Observed zero-carry rate among verified active applicable rushers |
| X02-M06 | Upper target-count quantile conditional on stable role |
| X02-M07 | Upper rush-count quantile conditional on stable role |
| X02-M08 | Workload threshold exceedance under declared role, with calibrated probability status |
| X02-M09 | Within-team target-allocation covariance including residual actors |
| X02-M10 | Within-team rush-allocation covariance including QB and residual actors |

## X03 — availability and role-transition conditions

Owner: availability with channel owners. Parents G17,G18,G22. W1 evidence/history and W4 conditional response. These are counts/shares or documented transition conditions, not automatic injury boosts. Verified inactivity, missing participation, same-team role and actual current restrictions remain separate. A learned participation probability would be another declared forecast, not inferred from ACT.

| ID | Candidate / proposed definition |
|---|---|
| X03-M01 | First verified active game after absence versus pre-absence role |
| X03-M02 | Second/third active game after absence recovery profile |
| X03-M03 | Current-starting-QB continuity × receiver opportunity |
| X03-M04 | Current-starting-QB change × backfield target opportunity |
| X03-M05 | Missing primary receiver × other-role target distribution, with no forced transfer |
| X03-M06 | Missing primary rusher × full backfield/QB rush allocation |
| X03-M07 | Explicit workload restriction × opportunity forecast sensitivity |
| X03-M08 | Multi-player simultaneous absence × unallocated opportunity residual |
| X03-M09 | New-team first/second active game role transport uncertainty |
| X03-M10 | Depth promotion/demotion evidence × next-game role persistence |

## X04 — personnel and protection conditions

Owner: rushing/protection, availability and defense/matchups. Parents G13,G14,G16,G18. W3 source/identity and W4 interactions. Need actual line/personnel roles and measured event/assignment definitions; aggregate snaps and a depth-chart title alone do not prove protection responsibility. All availability is known at the cutoff; same-game realized lineup is not a predictor.

| ID | Candidate / proposed definition |
|---|---|
| X04-M01 | Starting center continuity × pressure/sack response |
| X04-M02 | Starting tackle availability × edge-pressure exposure |
| X04-M03 | Starting guard continuity × interior run effectiveness |
| X04-M04 | Multiple missing linemen × pass/rush budget sensitivity |
| X04-M05 | Protection personnel/package continuity across prior games |
| X04-M06 | Opponent front personnel × directional rush exposure |
| X04-M07 | Opponent primary coverage personnel absence × receiver deployment |
| X04-M08 | TE blocking-versus-route assignment share under protection changes |
| X04-M09 | RB pass-protection-versus-route assignment share |
| X04-M10 | New play-caller × personnel-package and pass/rush decisions |

## X05 — drive, field-position and scoring transitions

Owner: scoring/environment. Parents G01,G02,G11,G12,G23. W2 event derivation and W4 transition forecasting. Units are per-drive transition counts/proportions or opportunity distributions; goal-to-go overlaps zones. Drive/trip eligibility, retries/reentries/end-half behavior and unknown play coordinates must be defined. Do not multiply unrelated marginal probabilities and call it calibrated TD probability.

| ID | Candidate / proposed definition |
|---|---|
| X05-M01 | Offensive drive starting-field-position distribution |
| X05-M02 | Probability/observed rate a drive reaches opponent20, distinctly labeled |
| X05-M03 | Inside20-to-inside5 drive transition rate |
| X05-M04 | Inside5 pass/rush decision distribution by down/distance |
| X05-M05 | Goal-to-go pass/rush decision distribution by down |
| X05-M06 | Red-zone sacks/turnovers per eligible drive/opportunity |
| X05-M07 | Inside5 target allocation versus end-zone target allocation |
| X05-M08 | Failed third-down drive × field-goal/punt/go-for-it decision |
| X05-M09 | Two-minute end-half possession and scoring opportunity |
| X05-M10 | Pregame favorite/underdog context × late-game runout/scoring sensitivity |

## X06 — specialist and defensive event extensions

Owner: scoring/defense/environment. Parents G14,G15,G19,G20,G23. W2 observed components, W3 any missing source and W4 conditions. Keep field-goal attempts, distance, makes and PAT events separate; tackles/fumbles/INT opportunities require their exact event taxonomy. Team real points, opponent EPA and DST FP are different targets.

| ID | Candidate / proposed definition |
|---|---|
| X06-M01 | Expected field-goal attempts by distance band |
| X06-M02 | Expected PAT attempts tied to coherent team TD events |
| X06-M03 | Field-goal make response to forecast wind and roof status |
| X06-M04 | Field-goal range/decision response to score/time context |
| X06-M05 | Opponent drive starts after turnovers versus normal possessions |
| X06-M06 | Defensive sack count distribution conditional on opponent dropbacks |
| X06-M07 | Defensive interception count distribution conditional on pass events |
| X06-M08 | Fumble occurrence versus recovery probability, separated |
| X06-M09 | Defensive/return TD opportunity versus realized return-TD count |
| X06-M10 | Opponent real-points-allowed distribution distinct from DST scoring distribution |

## X07 — joint outcome and portfolio extensions

Owner: lineup integration with event/scoring owners. Parents G24 and shared count/TD budgets. W4 structured world assessment and W5 fitted/calibrated variants. One physical event produces both QB and receiver scoring; CPT changes scoring only. Monte Carlo error under assumptions is not empirical predictive calibration. Thresholds and policy must be declared before outcome inspection.

| ID | Candidate / proposed definition |
|---|---|
| X07-M01 | QB-pass/receiver-target shared event covariance |
| X07-M02 | QB rushing versus teammate rushing TD event allocation |
| X07-M03 | Receiver pair shared efficiency versus target-competition decomposition |
| X07-M04 | Opposing offenses' play/score covariance through shared clock |
| X07-M05 | Kicker stall-path versus offensive-TD-path full-roster sensitivity |
| X07-M06 | Full-roster useful-threshold exceedance, k-of-n variant |
| X07-M07 | Portfolio joint downside across all saved entries in shared worlds |
| X07-M08 | Replacement-role uncertainty contribution to portfolio concentration |
| X07-M09 | Marginal benefit of an alternative roster to shared-world coverage |
| X07-M10 | Salary-constrained conditional roster frontier across FP/count/world outcomes |

## X08 — source and estimation robustness diagnostics

Owner: shared contract/integration, with each workstream's actual source producer. W0/W1 diagnostics and W5 monitoring. These are provenance/coverage/uncertainty diagnostics; not all should be model features. Any predictive use needs availability-time proof and protection from ingest/outcome leakage. Do not turn missing evidence into a positive numeric workload signal.

| ID | Candidate / proposed definition |
|---|---|
| X08-M01 | Per-channel full-source actor and canonical identity coverage |
| X08-M02 | Unknown/unattributed team opportunity residual by channel |
| X08-M03 | Effective sample/exposure size for weighted role windows |
| X08-M04 | Source disagreement on status/role/component values |
| X08-M05 | Forecast-input age relative to original effective/source clocks |
| X08-M06 | Same-team versus transported-history coverage fraction |
| X08-M07 | Source revision magnitude/frequency with original snapshot preserved |
| X08-M08 | Component-level missingness and imputation ancestry |
| X08-M09 | Forecast drift by role/channel/source version |
| X08-M10 | Decision sensitivity to unresolved source/role assumptions |

## Acceptance for the extension program

Assign each accepted X-series ID a definition/version, parent ancestry, source disposition, owner and wave in the same coverage roadmap format. Collect/derive broadly under authorized access, then select model groups using chronological comparisons and regularization; keep unused or redundant candidates visible. No blanket exclusion of long-tail features because usefulness is unknown, and no claim that duplicate/interacted ancestry creates independent evidence. Each production consumer must preserve source clocks, missingness, conditioning, scoring conservation, model/version/uncertainty and public saved-result traceability.
