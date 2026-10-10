# Classic Gibbs / Garrett Wilson Root-Cause Audit
Research-only audit of the two saved 2026 Week 5 Sunday Main `classic_large_gpp_v1` five-entry runs. No production changes, player bonuses, forced production inclusion, hindsight, or weight recommendations based on realized results. Evidence captured October 9, 2026, America/Chicago.

**Classification:** VERIFIED = demonstrated by saved inputs, source, matched mathematical models, or solver proofs; LIKELY = supported interpretation requiring further validation; NOT ESTABLISHED = the available evidence cannot decide. Numerical values are rounded for display; JSON retains full precision.

## 1. Executive summary

**VERIFIED — the optimizer is solving the stated objective correctly.** Every one of the ten saved sequential steps reproduces its exact roster, objective value, objective fingerprint, and feasible-region fingerprint. Both omitted players are feasible at every step. Their omission is an objective/construction result, not an identity loss, silent eligibility exclusion, timeout, or failure to find the conditional best lineup.

**VERIFIED — Gibbs is the highest projected eligible RB, but his salary premium is inefficient under the frozen model.** He costs $9,800 for 19.3750 mean / 32.4991 P90, versus Chase Brown’s $6,900 for 17.3314 / 30.4555. Tight-cap unrestricted score is 4.620257829; forcing Gibbs gives 4.456067730: a 0.164190099 sacrifice (3.55%). The 4-team/5-game configuration also excludes him and costs 0.190451769 to force him.

**VERIFIED — Wilson is a close portfolio alternative but a weak individual purchase under these inputs.** At $6,600, his 12.2087 mean / 25.0869 P90 trails DK Metcalf’s $5,400 for 13.5991 / 26.4773. Tight-cap forcing Wilson costs 0.034680461 (0.75%); at the second sequential step it costs only 0.011552165. The solver searches for the single winning objective, and the pipeline retains accepted entries, not near-optimal alternatives.

**VERIFIED mechanism / LIKELY projection weakness — team opportunity normalization mixes player histories from different teams and windows.** Gibbs’s recent 90.35% Detroit RB carry share is diluted to 55.67% when allocation includes unavailable Isiah Pacheco, whose latest three observed games are Kansas City Weeks 15–17 of 2025. After normalization, Pacheco’s 7.4206 allocated carries are removed without redistribution. Gibbs ends up with 10.7628 carries rather than his 17.0 prior-game average. Wilson’s targets similarly fall from an 8.0 recent average to 5.1600; unavailable NYJ histories consume 33.53% of normalized target volume. A 55% opportunity-anchor blend then reduces Gibbs’s mean by 4.4981 and Wilson’s by 3.7851. These are real upstream mechanisms, not an assertion that either corrected player must be selected.

**VERIFIED — the two-player cap matters, but is not the sole root cause.** Goff plus Gibbs is infeasible with a mandatory Detroit pass catcher under a two-player team cap. Raising only the team cap to four improves Gibbs’s best lineup by just 0.020924339; the unrestricted lineup improves much more, so Gibbs’s relative gap widens. Raising only the game cap from three to five improves Gibbs’s best lineup by 0.145910885. Neither isolated relaxation selects him.

**VERIFIED design limitations:** P90 is mean plus a calibration-bin offset, so ceiling largely repeats mean within bins; all 121 optimal-lineup probabilities are absent and leverage is zero despite a nominal 5% weight; all receiving/rushing correlation-role strengths are zero; broad-cap correlation bonuses change the winning construction and give all five entries the same primary game. **NOT ESTABLISHED:** actual projections are accurate, the chosen objective measures contest EV, or increased player coverage would improve outcomes.

## 2. Frozen inputs, identity, and reproduction scope

| Run | Team/game caps | Templates used | Projection run | Snapshot SHA256 |
| --- | --- | --- | --- | --- |
| bd990e1b | 4/5 | [[1, 0], [1, 1], [2, 0], [2, 1]] | f3a3b0d0-30e7-48fa-a968-9889cccf927f | 006da5af391b016fc5b129cbf4071ab7d7344aa67851c4af19af3c018f1c0dec |
| 139d5544 | 2/3 | [[1, 0], [1, 1]] | f3a3b0d0-30e7-48fa-a968-9889cccf927f | 516ec088fa76be314611320d565ef30ecfed78e4d26681894433f6467c94d84f |

Both have 121 canonical IDs, five entries, global max exposure 0.8 (four appearances), max overlap five (at least four different players), ownership available, no primary-game portfolio cap, no locks/minimum exposures, no elevated-player caps, DST-opponent avoidance enabled, and TE permitted in FLEX. **VERIFIED:** ordered adapted `Player` inputs are identical, although full snapshot hashes differ. Ablations use only `139d5544`; the broad 4/5 configuration is independently solved on that same ordered frame. Original raw exports, contracts, source hashes, configuration, projection lineage, and logs are in `artifacts/classic_gibbs_wilson_audit/`.

Gibbs canonical UUID: `693463af-73ba-41d5-889c-388c36703430`; Wilson: `b5c3da49-f977-49ea-bdef-e18b45802d84`. Joins use these IDs, never display names. The original salary source checksum is `21aaaeff559a2dc434e38fce457b8f80aed4e245b75732b9e8b07c1073b99655`.

The tight run’s full implementation fingerprint matches current code and bundled CBC. The broad run’s historical `gpp_optimizer.py` and `classic_strategy_contract.py` hashes differ; no generic historical source equivalence is claimed. **VERIFIED for these ten solves:** both full mathematical fingerprints and rosters match. That establishes objective/constraint parity for the audited steps without silently bypassing the strict strategy-contract validator. The original hashes remain preserved.

## 3. Gibbs and Wilson projections, compared with selected alternatives

| Player | Salary | Mean | P10 | P90 | GPP ceiling = P90 + context | Ownership % | Mean/$1k | Position ranks mean/P90/additive | Additive objective | Additive/$1k | Tight entries |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Jahmyr Gibbs | 9800 | 19.3750 | 8.8566 | 32.4991 | 33.7366 | 35.2853 | 1.9770 | 1/1/1 | 0.654892 | 0.066826 | 0/5 |
| Chase Brown | 6900 | 17.3314 | 6.8130 | 30.4555 | 30.9395 | 8.5613 | 2.5118 | 2/2/2 | 0.586837 | 0.085049 | 4/5 |
| Jaylen Warren | 6700 | 15.4781 | 4.9596 | 28.6021 | 28.7037 | 8.3114 | 2.3102 | 4/4/4 | 0.532436 | 0.079468 | 4/5 |
| Garrett Wilson | 6600 | 12.2087 | 1.3319 | 25.0869 | 25.0869 | 8.6664 | 1.8498 | 6/5/5 | 0.447545 | 0.067810 | 0/5 |
| DK Metcalf | 5400 | 13.5991 | 2.7223 | 26.4773 | 26.5788 | 8.1000 | 2.5184 | 4/4/4 | 0.483845 | 0.089601 | 4/5 |
| Amon-Ra St. Brown | 7900 | 19.6482 | 8.7714 | 32.5264 | 33.7121 | 18.1478 | 2.4871 | 1/1/1 | 0.657407 | 0.083216 | 2/5 |
| Michael Wilson | 6200 | 15.1146 | 4.2378 | 27.9928 | 28.8441 | 8.1298 | 2.4378 | 3/3/3 | 0.538963 | 0.086930 | 4/5 |
| Isaac TeSlaa | 3400 | 8.2483 | 0.5614 | 17.9412 | 19.1269 | 0.3898 | 2.4260 | 21/22/16 | 0.342810 | 0.100826 | 0/5 |

“Modeled GPP value” above is explicitly the individual additive projection + ceiling + context score, with the original frozen denominators; leverage is zero. A player cannot have one unconditional full GPP rank because correlation depends on the other eight players. Exact lineup-dependent value is measured by forced-inclusion solves below. `gpp_score`/`strategy_p90_score` in the UI pool is P90 + context; the actual Large-GPP solver does not optimize that column alone.

### Upstream football inputs and the point-estimate chain

| Player | Prior carries → projected | Prior targets → projected | Projected carry/target share | Snap share | Pre-opportunity mean | Opportunity anchor | Blend weight | Final mean | P90 calibration role / samples |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Jahmyr Gibbs | 17.000 → 10.763 | 7.667 → 7.052 | 0.557 / 0.176 | 0.753 | 23.8732 | 15.6947 | 0.55 | 19.3750 | LEAD / 295.0 |
| Chase Brown | 14.000 → 12.141 | 6.000 → 4.687 | 0.728 / 0.116 | 0.660 | 21.5646 | 13.8680 | 0.55 | 17.3314 | LEAD / 295.0 |
| Jaylen Warren | 15.000 → 12.375 | 4.667 → 3.963 | 0.640 / 0.111 | 0.660 | 17.4460 | 13.8680 | 0.55 | 15.4781 | LEAD / 295.0 |
| Garrett Wilson | 0.000 → missing | 8.000 → 5.160 | 0.000 / 0.178 | 0.857 | 15.9938 | 9.1118 | 0.55 | 12.2087 | PRIMARY / 518.0 |
| DK Metcalf | 0.000 → missing | 7.667 → 6.439 | 0.000 / 0.181 | 0.960 | 15.8893 | 11.7253 | 0.55 | 13.5991 | PRIMARY / 518.0 |
| Amon-Ra St. Brown | 0.000 → missing | 10.667 → 9.497 | 0.000 / 0.237 | 0.863 | 24.2422 | 15.8896 | 0.55 | 19.6482 | PRIMARY / 518.0 |
| Michael Wilson | 0.000 → missing | 12.333 → 8.129 | 0.000 / 0.220 | 0.907 | 16.6486 | 13.8596 | 0.55 | 15.1146 | PRIMARY / 518.0 |
| Isaac TeSlaa | 0.000 → missing | 5.333 → 4.484 | 0.000 / 0.112 | 0.637 | 8.0409 | 8.4179 | 0.55 | 8.2483 | SECONDARY / 560.0 |

**VERIFIED:** all eight are ACT/available, model availability probability 1.0, high-confidence and role eligible. Seven have expected-starter depth roles; TeSlaa is an expected backup with SECONDARY calibration, not a modeled starter. No questionable override or player exclusion causes these comparisons. Three-game snaps and projected opportunity are model inputs, not sourced forward snaps/routes. The saved forward expected routes, expected snaps, explicit expected carries/targets, goal-line/red-zone shares, receiving yards and receptions are missing. No explicit Week 5 touchdown forecast or catch-rate model is supplied here. It would be unsupported to claim a particular TD, coverage assignment, route count, or injury limitation explains the selections.

The saved model contract is gradient boosting with 27 features, including salary, lagged fantasy points, matchup defensive fantasy allowance, missing-team opportunity indicators, snaps, role importance and market totals. The pre-opportunity mean uses the recorded 80% raw-model / 20% historical-anchor path (historical anchor 60% three-game mean + 40% eight-game mean). Final means for these eight exactly satisfy `0.45 × pre-opportunity mean + 0.55 × prior-training isotonic opportunity anchor`; market-point reconciliation adjustment is zero for all eight. RB opportunity units are carries + 1.75 × targets; WR opportunity units are targets. The stored artifact and training-data hashes are preserved in `projection_lineage.json`; this audit verifies the recorded arithmetic, not a retraining of the model or a SHAP decomposition of the pre-opportunity predictor.

The matchup features and recorded market/optimizer adjustments are available even though causal attribution inside the tree model is not. Defensive values below are lagged position fantasy allowance features, not a specific-player coverage forecast. All are retained as numeric evidence, without inventing a matchup penalty.

| Player | Fantasy mean last 3 / 8 | Opponent defense position allowed last 3 / 8 | Opponent defense position P90 last 8 | Game total / team total / spread | Context adjustment | Triggered context reasons |
| --- | --- | --- | --- | --- | --- | --- |
| Jahmyr Gibbs | 27.467 / 22.538 | 1.700 / 5.963 | 12.920 | 54.50 / 30.00 / -5.50 | 1.237500 | high_game_total, high_implied_team_total, favorite_running_back |
| Chase Brown | 13.067 / 19.750 | 6.667 / 8.375 | 21.690 | 43.50 / 25.25 / -7.00 | 0.484063 | high_implied_team_total, favorite_running_back |
| Jaylen Warren | 16.300 / 14.913 | 4.133 / 6.900 | 14.410 | 43.50 / 23.25 / -3.00 | 0.101562 | high_implied_team_total |
| Garrett Wilson | 17.367 / 13.700 | 8.233 / 6.762 | 17.330 | 39.50 / 21.00 / -2.50 | 0.000000 | none |
| DK Metcalf | 12.767 / 12.500 | 9.900 / 6.300 | 10.160 | 43.50 / 23.25 / -3.00 | 0.101562 | high_implied_team_total |
| Amon-Ra St. Brown | 21.867 / 23.850 | 0.000 / 8.400 | 18.640 | 54.50 / 30.00 / -5.50 | 1.185714 | high_game_total, high_implied_team_total, competitive_high_total_pass_environment |
| Michael Wilson | 15.400 / 15.900 | 3.967 / 12.025 | 35.250 | 54.50 / 24.50 / 5.50 | 0.851339 | high_game_total, high_implied_team_total, competitive_high_total_pass_environment, underdog_receiving_volume |
| Isaac TeSlaa | 9.233 / 7.450 | 0.000 / 8.400 | 18.640 | 54.50 / 30.00 / -5.50 | 1.185714 | high_game_total, high_implied_team_total, competitive_high_total_pass_environment |

### Gibbs: the model ranks him first, then spends elsewhere

**VERIFIED:** Gibbs exceeds Brown by 2.0436 mean and the same 2.0436 P90, but costs $2,900 more. Brown has 12.1411 modeled carries versus Gibbs’s 10.7628; Gibbs has more targets (7.0523 versus 4.6867), making his opportunity anchor stronger. Warren offers 15.4781 mean / 28.6021 P90 at $6,700: $3,100 cheaper. Neither RB is “better” in absolute projection; they are more efficient ways to satisfy two mandatory RB slots while preserving strong WR/TE/stack combinations. Brown and Warren are both calibrated LEAD backs with the same +13.1240 P90 offset as Gibbs. Gibbs’s strong environment adds +1.2375 objective-context points, which helps him rather than suppressing him. His 35.2853% ownership does not penalize his objective because leverage is unavailable, and none of these diagnostic lineups approaches the 160% ownership ceiling.

Under tight caps, forcing Gibbs replaces Warren and St. Brown with Gibbs and Luther Burden III. That two-player package loses 4.4143 mean and 7.5995 summed P90, even though Gibbs is an individual upgrade over Warren. The projection/ceiling loss, net of context, is 0.140082956; correlation loses another 0.024107143. This is the exact salary-and-construction opportunity cost, not a single-player rank error.

### Wilson: lower targets, lower model output, less favorable environment

**VERIFIED:** Metcalf is $1,200 cheaper and exceeds Garrett Wilson by 1.3904 mean and P90; modeled targets are 6.4391 versus 5.1600. Their pre-opportunity means are close (15.8893 versus 15.9938), so the opportunity anchor is the immediate reason their final ranking reverses. Michael Wilson is $400 cheaper, has 8.1290 targets versus 5.1600, and exceeds Garrett by 2.9059 mean/P90, before +0.8513 context and ARI–DET bring-back benefits. St. Brown costs $1,300 more but buys +7.4395 mean/P90, 9.4969 modeled targets, +1.1857 context, and a Detroit pass-catcher role in the favored stack. TeSlaa is not superior in absolute projection: he saves $3,200, supplies 4.4841 modeled targets and 17.9412 P90, gets +1.1857 context, and fills a cheap Detroit stack slot. His additive objective per $1k is 0.100826 versus Garrett’s 0.067810.

Garrett’s CLE–NYJ game total is 39.5 / team total 21.0, compared with DET–ARI 54.5 and Detroit 30.0. Metcalf’s game total is 43.5 / PIT 23.25, and Michael Wilson’s ARI implied total is 24.5. Garrett gets zero soft context adjustment. These recorded totals explain optimizer scoring, not a verified physiological or matchup disadvantage. In the tight forced lineup, St. Brown + Mayer are replaced by Garrett + LaPorta; the correlated ARI–DET receiver pairing is preserved via LaPorta, so there is no correlation loss. The package costs +$100, loses 2.0497 mean and only 0.4999 summed P90 (TE calibration offsets matter), giving the small 0.034680461 gap.

### The upstream allocation concern

**VERIFIED:** saved Gibbs base carry share 0.90346908 is divided by an inferred team sum of 1.62290670, producing 0.55669810. The active Detroit backs’ base shares sum to 1.0; an additional unavailable Pacheco prior adds approximately 0.62290670. The allocator normalizes first and applies availability second. It therefore assigns Pacheco 7.42055156 carries, removes them, and does not return them to Gibbs. Gibbs has no explicit forward workload; `opportunity_redistributed=False`, `recipient_supported=False`. His role explanation continues to show the preallocation 90.3% share while the actual scored opportunity uses 55.7%, making the explanation easy to misread.

`opportunity_history.json` confirms Gibbs’s last three prelock observations are DET 2026 W2/W3/W4 (16/20/15 carries). Pacheco’s are KC 2025 W15/W16/W17 (11/8/9 carries). Saved role evidence puts Pacheco on DET and unavailable. Source code collects each player’s last three observed games without requiring the current team or a common calendar window, then normalizes those shares against the current team pool. **VERIFIED mechanism:** old-team and different-window shares compete with current Detroit shares. **LIKELY defect:** treating Pacheco’s old KC workload as vacated present Detroit workload is not a coherent shared team-period accounting basis. A source/role reconciliation must establish his intended current role before selecting a correction.

Wilson’s base target share 0.27407407 becomes 0.17792952 (inferred normalization sum 1.54035190); multiplied by 29 team targets, this gives 5.15995607. NYJ allocates only 19.27599421 targets and leaves 9.72400579 unassigned. The unavailable pool includes Breece Hall, Adonai Mitchell, Sterling Shepard, Tim Patrick, Omar Cooper Jr., Arian Smith, and Tyler Johnson. **VERIFIED:** this reduces Wilson’s volume and activates the team opportunity blend. **NOT ESTABLISHED:** all those withheld targets should flow to Wilson, or which source/status/role/window correction is warranted for each player. Do not repair this by blindly distributing all missing work.

## 4. Best forced-inclusion lineups and objective costs

“Unrestricted” means no diagnostic player lock and no portfolio history, with the original Large-GPP hard lineup constraints retained. No exposure limit can bind a first entry; the least restrictive original template is QB + at least one WR/TE, no required bring-back. Templates specify minima, not exact counts.

| Solve | Salary | Mean | Σ marginal P90 | Σ ownership % | Projection | Ceiling | Context | Correlation | Leverage | Original score | Gap vs unrestricted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 49800 | 131.9422 | 235.0120 | 74.6728 | 1.668449 | 2.746316 | 0.096464 | 0.109029 | 0.000000 | 4.620257829 | 0.000000000 |
| B | 49900 | 127.5279 | 227.4125 | 84.8270 | 1.612629 | 2.657509 | 0.101008 | 0.084921 | 0.000000 | 4.456067730 | 0.164190099 |
| C | 49900 | 129.8925 | 234.5121 | 66.9004 | 1.642530 | 2.740475 | 0.093545 | 0.109029 | 0.000000 | 4.585577368 | 0.034680461 |
| D | 50000 | 125.2235 | 225.1080 | 87.2800 | 1.583489 | 2.630580 | 0.099745 | 0.084921 | 0.000000 | 4.398734738 | 0.221523091 |

### A. Best unrestricted — frozen team 2 / game 3

| Position (intrinsic) | Player | Team | Salary | Mean | P90 |
| --- | --- | --- | --- | --- | --- |
| RB | Chase Brown | CIN | 6900 | 17.3314 | 30.4555 |
| RB | Jaylen Warren | PIT | 6700 | 15.4781 | 28.6021 |
| TE | Michael Mayer | LV | 3500 | 8.8867 | 16.7967 |
| WR | Amon-Ra St. Brown | DET | 7900 | 19.6482 | 32.5264 |
| WR | Michael Wilson | ARI | 6200 | 15.1146 | 27.9928 |
| WR | DK Metcalf | PIT | 5400 | 13.5991 | 26.4773 |
| WR | Malik Washington | MIA | 4600 | 9.4814 | 22.3595 |
| DST | Vikings | MIN | 3100 | 6.0269 | 12.5963 |
| QB | Jacoby Brissett | ARI | 5500 | 26.3757 | 37.2055 |

One of the extra RB/WR/TE occupies FLEX; rows are intrinsic positions, not a persisted slot allocation. Status **Optimal**, solution status **Optimal Solution Found**, CBC certified relative gap **0 within its numerical tolerances**; no time/node limit or nonzero requested gap. Mean/P90 are untouched player outputs. Σ marginal P90 is not the joint lineup P90, and summed ownership is not a lineup ownership probability.

### B. Require Gibbs — frozen team 2 / game 3

| Position (intrinsic) | Player | Team | Salary | Mean | P90 |
| --- | --- | --- | --- | --- | --- |
| RB | Jahmyr Gibbs | DET | 9800 | 19.3750 | 32.4991 |
| RB | Chase Brown | CIN | 6900 | 17.3314 | 30.4555 |
| TE | Michael Mayer | LV | 3500 | 8.8867 | 16.7967 |
| WR | Michael Wilson | ARI | 6200 | 15.1146 | 27.9928 |
| WR | DK Metcalf | PIT | 5400 | 13.5991 | 26.4773 |
| WR | Malik Washington | MIA | 4600 | 9.4814 | 22.3595 |
| WR | Luther Burden III | CHI | 4900 | 11.3370 | 21.0299 |
| DST | Vikings | MIN | 3100 | 6.0269 | 12.5963 |
| QB | Jacoby Brissett | ARI | 5500 | 26.3757 | 37.2055 |

One of the extra RB/WR/TE occupies FLEX; rows are intrinsic positions, not a persisted slot allocation. Status **Optimal**, solution status **Optimal Solution Found**, CBC certified relative gap **0 within its numerical tolerances**; no time/node limit or nonzero requested gap. Mean/P90 are untouched player outputs. Σ marginal P90 is not the joint lineup P90, and summed ownership is not a lineup ownership probability.

### C. Require Garrett Wilson — frozen team 2 / game 3

| Position (intrinsic) | Player | Team | Salary | Mean | P90 |
| --- | --- | --- | --- | --- | --- |
| RB | Chase Brown | CIN | 6900 | 17.3314 | 30.4555 |
| RB | Jaylen Warren | PIT | 6700 | 15.4781 | 28.6021 |
| TE | Sam LaPorta | DET | 4900 | 14.2765 | 23.7363 |
| WR | Michael Wilson | ARI | 6200 | 15.1146 | 27.9928 |
| WR | DK Metcalf | PIT | 5400 | 13.5991 | 26.4773 |
| WR | Garrett Wilson | NYJ | 6600 | 12.2087 | 25.0869 |
| WR | Malik Washington | MIA | 4600 | 9.4814 | 22.3595 |
| DST | Vikings | MIN | 3100 | 6.0269 | 12.5963 |
| QB | Jacoby Brissett | ARI | 5500 | 26.3757 | 37.2055 |

One of the extra RB/WR/TE occupies FLEX; rows are intrinsic positions, not a persisted slot allocation. Status **Optimal**, solution status **Optimal Solution Found**, CBC certified relative gap **0 within its numerical tolerances**; no time/node limit or nonzero requested gap. Mean/P90 are untouched player outputs. Σ marginal P90 is not the joint lineup P90, and summed ownership is not a lineup ownership probability.

### D. Require both — frozen team 2 / game 3

| Position (intrinsic) | Player | Team | Salary | Mean | P90 |
| --- | --- | --- | --- | --- | --- |
| RB | Jahmyr Gibbs | DET | 9800 | 19.3750 | 32.4991 |
| RB | Chase Brown | CIN | 6900 | 17.3314 | 30.4555 |
| TE | AJ Barner | SEA | 3200 | 7.1211 | 15.0310 |
| WR | Michael Wilson | ARI | 6200 | 15.1146 | 27.9928 |
| WR | DK Metcalf | PIT | 5400 | 13.5991 | 26.4773 |
| WR | Garrett Wilson | NYJ | 6600 | 12.2087 | 25.0869 |
| WR | Roman Wilson | PIT | 3700 | 8.8529 | 18.5458 |
| DST | Jets | NYJ | 2700 | 5.2448 | 11.8142 |
| QB | Jacoby Brissett | ARI | 5500 | 26.3757 | 37.2055 |

One of the extra RB/WR/TE occupies FLEX; rows are intrinsic positions, not a persisted slot allocation. Status **Optimal**, solution status **Optimal Solution Found**, CBC certified relative gap **0 within its numerical tolerances**; no time/node limit or nonzero requested gap. Mean/P90 are untouched player outputs. Σ marginal P90 is not the joint lineup P90, and summed ownership is not a lineup ownership probability.

### Same fixed snapshot with the original broad 4 / 5 controls

This secondary configuration sensitivity is two changed controls relative to tight A; its component steps are isolated in Section 5. It reproduces the broad run’s first entry exactly.

| Solve | Salary | Mean | Σ marginal P90 | Σ ownership % | Projection | Ceiling | Context | Correlation | Leverage | Original score | Gap vs unrestricted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| broad_A | 49900 | 131.0159 | 232.4503 | 68.1263 | 1.656736 | 2.716381 | 0.159646 | 0.429767 | 0.000000 | 4.962530123 | 0.000000000 |
| broad_B | 50000 | 129.0174 | 227.2665 | 86.0554 | 1.631464 | 2.655804 | 0.161393 | 0.323417 | 0.000000 | 4.772078354 | 0.190451769 |
| broad_C | 49900 | 124.6494 | 224.6002 | 66.5327 | 1.576229 | 2.624646 | 0.157662 | 0.429767 | 0.000000 | 4.788303481 | 0.174226642 |
| broad_D | 50000 | 125.3294 | 223.5785 | 85.3954 | 1.584829 | 2.612706 | 0.140679 | 0.271989 | 0.000000 | 4.610202263 | 0.352327860 |

**broad_A** (nine players): Chase Brown $6900; Jaylen Warren $6700; Sam LaPorta $4900; Amon-Ra St. Brown $7900; Michael Wilson $6200; Malik Washington $4600; Isaac TeSlaa $3400; Jets $2700; Jared Goff $6600. **Optimal**, certified gap 0 within CBC tolerances.

**broad_B** (nine players): Jahmyr Gibbs $9800; Chase Brown $6900; Sam LaPorta $4900; Michael Wilson $6200; DK Metcalf $5400; Isaac TeSlaa $3400; Roman Wilson $3700; Vikings $3100; Jared Goff $6600. **Optimal**, certified gap 0 within CBC tolerances.

**broad_C** (nine players): Chase Brown $6900; Jaylen Warren $6700; Sam LaPorta $4900; Michael Wilson $6200; Garrett Wilson $6600; Jameson Williams $5900; Isaac TeSlaa $3400; Jets $2700; Jared Goff $6600. **Optimal**, certified gap 0 within CBC tolerances.

**broad_D** (nine players): Jahmyr Gibbs $9800; Chase Brown $6900; Sam LaPorta $4900; DK Metcalf $5400; Garrett Wilson $6600; Isaac TeSlaa $3400; Roman Wilson $3700; Jets $2700; Jared Goff $6600. **Optimal**, certified gap 0 within CBC tolerances.

### Gap decomposition (unrestricted minus forced; negative = forced benefit)

| Controls / requirement | Projection | Ceiling | Context | Correlation | Leverage | Total sacrifice |
| --- | --- | --- | --- | --- | --- | --- |
| tight / B | 0.055819583 | 0.088807000 | -0.004543627 | 0.024107143 | 0.000000000 | 0.164190099 |
| tight / C | 0.025919124 | 0.005841598 | 0.002919739 | 0.000000000 | 0.000000000 | 0.034680461 |
| tight / D | 0.084959942 | 0.115736368 | -0.003280362 | 0.024107143 | 0.000000000 | 0.221523091 |
| broad_4/5 / B | 0.025271594 | 0.060576805 | -0.001746630 | 0.106350000 | 0.000000000 | 0.190451769 |
| broad_4/5 / C | 0.080507158 | 0.091734974 | 0.001984510 | 0.000000000 | 0.000000000 | 0.174226642 |
| broad_4/5 / D | 0.071907542 | 0.103674304 | 0.018967442 | 0.157778571 | 0.000000000 | 0.352327860 |

These scalar objective gaps are not dollars, expected contest winnings, win probability, or a football-point confidence interval. Gibbs costs more original objective than Garrett in the tight first entry, but whether 3.55% constitutes a substantial true-EV sacrifice is NOT ESTABLISHED. A 0.0116 gap can be small relative to projection uncertainty without implying the lower-scoring lineup has higher true EV. The deterministic optimizer has no uncertainty-aware near-tie acceptance or alternative-retention rule: even a very small positive sacrifice loses unless later constraints reverse the ranking.

## 5. Structural rules and controlled ablations

Each row below changes one rule from tight 2/3 A/B/C, uses the same fixed player inputs, and preserves the nine-slot $50,000 DraftKings roster. Other than the explicitly labelled scoring ablations, original objective coefficients and normalization are unchanged. No claim is made that a relaxed rule improves contest performance.

| One changed rule | Best objective | Gibbs objective | Gibbs gap | Wilson objective | Wilson gap | Gibbs/Wilson in best |
| --- | --- | --- | --- | --- | --- | --- |
| team_cap4 | 4.749130 | 4.476992 | 0.272138 | 4.649105 | 0.100024 | Neither |
| game_cap5 | 4.748023 | 4.601979 | 0.146045 | 4.613190 | 0.134833 | Neither |
| no_mandatory_stack | 4.620258 | 4.456068 | 0.164190 | 4.585577 | 0.034680 | Neither |
| no_ownership_cap | 4.620258 | 4.456068 | 0.164190 | 4.585577 | 0.034680 | Neither |
| no_chalk_cap | 4.620258 | 4.456068 | 0.164190 | 4.585577 | 0.034680 | Neither |
| no_punt_cap | 4.620258 | 4.456068 | 0.164190 | 4.585577 | 0.034680 | Neither |
| no_correlation | 4.511229 | 4.371146 | 0.140083 | 4.476549 | 0.034680 | Neither |

**VERIFIED:** team cap 2→4 improves unrestricted score +0.128871995 but Gibbs +0.020924339, so his relative gap grows from 0.164190099 to 0.272137755. Game cap 3→5 improves unrestricted +0.127765330 and Gibbs +0.145910885, narrowing his gap to 0.146044544. With both relaxed, unrestricted improves +0.342272294 and Gibbs +0.316010624; neither enters. Effects interact and must not be added as independent causal shares.

| Direct Detroit diagnostic | Status | Original objective |
| --- | --- | --- |
| tight_Goff_Gibbs | Infeasible | no feasible integer lineup |
| team4_Goff_Gibbs | Optimal | 4.441632 |
| tight_Goff_Gibbs_StBrown | Infeasible | no feasible integer lineup |
| broad_Goff_Gibbs_StBrown | Optimal | 4.619294 |

Goff + Gibbs alone requires a third Detroit player to satisfy the mandatory WR/TE stack, so it is infeasible at team cap two. With team cap four and game cap three it becomes legal (4.441631870), but remains below tight unrestricted A. Goff + Gibbs + St. Brown is legal in broad controls (4.619294488), still below broad unrestricted 4.962530123. Gibbs is not intrinsically infeasible: Brissett-led lineups can include him under tight caps.

**Salary:** A/B/C/D spend $49,800/$49,900/$49,900/$50,000; no minimum-spend rule exists. The salary cap drives package tradeoffs but is not violated or relaxed for research. **Mandatory stacks:** removing only the minimum stack leaves tight A/B/C unchanged. Removing it in broad controls also leaves broad A unchanged. **DST:** allowing offensive opponents of DST leaves tight A and B unchanged; original avoidance is not causing these omissions. **Ownership/chalk/punts:** removing each relevant cap independently leaves A/B/C unchanged; five chalk / two punt limits and 160% summed ownership are not binding explanations here.

**Context ablation caveat:** the generic no-context experiment zeroes environmental additions, and the production builder recomputes max-projection/P90 denominators. Its raw score is therefore on another scale and is not a causal score delta. Original-objective rescoring verifies the same A/B/C rosters win and yields their original scores. All scoring-ablation rosters are rescored under the fixed original objective in `original_objective_rescore`. Constraint-ablation scores already use that objective.

## 6. Objective mathematics and scoring audit

The exact original objective is:

```text
Σ [0.35 × (mean_i + context_i) / 27.678259770127184
 + 0.45 × (P90_i  + context_i) / 38.50809059260224
 + 0.05 × leverage_i / 1]
 + 0.15 × (active pair-rule adjustments + active format-rule adjustments).
```

The denominators are full eligible-pool maxima, computed before exposure blocking; they stay fixed across the sequential steps and forced-inclusion solves. Context is added to both mean and ceiling; the report splits it out as `context × (0.35/Mmean + 0.45/MP90)` to avoid attributing it to model truth. Context therefore carries an extra objective channel even though the nominal UI lists only four weights. Every reported component reconciles to the actual solver objective within 1e-7, and independent production-rule rescoring agrees.

### Ceiling information and clipping

**VERIFIED:** the Large-GPP path uses saved calibrated P90 directly, with no single-lineup upside-discovery clipping/saturation formula. Calibration adds empirical chronological residual quantiles to the conditional mean, with nonnegative/ordered quantile handling. There is no score cap that makes Gibbs and Garrett share an identical top score. Gibbs/Brown/Warren have exactly the same +13.12402633 P90 offset; Garrett/Metcalf/St. Brown/Michael Wilson share +12.87815501. Within each such bin, a one-point mean gain creates the same one-point P90 gain: the nominal ceiling term supplies no new within-bin upside ranking. Across bins it supplies meaningful, but coarse, distribution information.

| Position | Players | Distinct P90−mean offsets | Largest repeated bin |
| --- | --- | --- | --- |
| QB | 21 | 2 | 15 |
| RB | 14 | 3 | 8 |
| WR | 45 | 6 | 18 |
| TE | 29 | 5 | 9 |
| DST | 12 | 1 | 12 |

The $3,400 TeSlaa gets +9.69288017 P90 above 8.24828245 mean. That cohort offset plus a fixed roster size can reward cheap role-bin members without a player-specific tail model. **LIKELY:** salary-efficient cohort ceilings encourage the repeated cheap/favored stacks. **NOT ESTABLISHED:** the residual quantiles are miscalibrated for these players, or an individually conditional tail model would improve out-of-time contest outcomes. The archived Week 3 prelock pool also shows repeated role/position offsets; only its frozen inputs were read, not its outcomes.

### Correlation scale and favored games

**VERIFIED:** pair and format terms are unnormalized policy points, whereas player mean/P90 terms are normalized individually then summed. “15% correlation” is a coefficient, not a promise that correlation constitutes 15% of the final score. Tight A has 0.109028571 correlation; broad A has 0.429767411 (8.66% of total). Broad A has three Detroit pass catchers, even though the first template requires only one. QB-pass-catcher pair rewards accumulate alongside a double-stack format reward and a competitive-game-stack reward. Per-rule signals are bounded; the original Large-GPP selection does not apply the separate single-lineup/captain saturation policy to erase these extra classic stack rewards.

| Broad A triggered rule | Players | Weighted contribution |
| --- | --- | --- |
| correlation.opposing_pass_catchers_v1 | Sam LaPorta, Michael Wilson | 0.009642857 |
| correlation.qb_pass_catcher_v2 | Sam LaPorta, Jared Goff | 0.096707143 |
| correlation.opposing_pass_catchers_v1 | Amon-Ra St. Brown, Michael Wilson | 0.009642857 |
| correlation.qb_pass_catcher_v2 | Amon-Ra St. Brown, Jared Goff | 0.096707143 |
| correlation.opposing_pass_catchers_v1 | Michael Wilson, Isaac TeSlaa | 0.009642857 |
| correlation.shootout_bring_back_v1 | Michael Wilson, Jared Goff | 0.014464286 |
| correlation.qb_pass_catcher_v2 | Isaac TeSlaa, Jared Goff | 0.096707143 |
| construction.classic_qb_double_stack_v2 | Jared Goff, Sam LaPorta, Amon-Ra St. Brown, Isaac TeSlaa | 0.078574554 |
| construction.classic_competitive_game_stack_v1 | Sam LaPorta, Amon-Ra St. Brown, Michael Wilson, Isaac TeSlaa, Jared Goff | 0.017678571 |

Removing correlation alone in the broad 4/5 region picks a Brissett lineup with mean 136.09887344 and summed P90 237.53324112 instead of original Goff lineup 131.01591828 / 232.45028595. That alternative’s original score is 4.708471971, below 4.962530123; the original rewards exchange 5.0830 modeled mean points for construction preference. The original-minus-alternative correlation advantage is 0.367345982, exceeding the additive disadvantage of 0.113287830. **VERIFIED construction preference; NOT ESTABLISHED EV benefit.** Rule metadata explicitly calls these correlation policies `initial_policy_unvalidated`; changing them requires historical prelock validation, not blind reweighting. Tight A is unchanged when correlation is removed.

### Why leverage is zero, and role-based correlations are unavailable

`tag_players` calculates `optimal_lineup_probability − ownership` only when both exist; otherwise leverage is zero. **VERIFIED:** ownership exists but all 121 optimal-lineup probabilities are null, so all 121 leverage values and selected lineup contributions are zero. Ownership availability selects the 45/35/15/5 branch; actual leverage support does not activate any signal here, and the unused 5% is not redistributed. This is an availability/reporting mismatch, not clipping and not low ownership exactly offsetting high ownership. Ownership still affects hard caps/tags, which the controlled ablations show are not the cause here.

**VERIFIED:** all 121 `optimizer_receiving_role_strength` and `optimizer_rushing_role_strength` values are zero. The source derives them from explicit forward role evidence (shares/expected counts/routes), which is missing for these eight, while lagged opportunity projections do exist. The adapted `Player` exposes the explicit zero, so correlation does not infer a receiving-back strength from Gibbs’s 7.0523 projected targets. QB + same-team WR/TE can earn its role reward; Goff + Gibbs cannot earn the receiving-back rule. **LIKELY:** this evidence gap favors pass-catcher constructions relative to legitimate receiving RB alternatives; the magnitude of an evidence-backed corrected signal is NOT ESTABLISHED. No synthetic strength or player-specific reward was added.

## 7. Sequential five-entry selection effects

These are five accepted sequential ILP winners, not five selections from a saved 120-lineup universe. Each step uses a minimum stack template, remaining appearance counts, and overlap constraints against every accepted prior roster. No earlier entry is revisited to maximize a joint five-entry objective.

### Run bd990e1b

| Step | Template (catchers, bring-backs) | Winner objective | Gibbs best / gap | Wilson best / gap | Already exposure-blocked |
| --- | --- | --- | --- | --- | --- |
| 1 | [1, 0] | 4.962530123 | 4.772078354 / 0.190451769 | 4.788303481 / 0.174226642 | none |
| 2 | [1, 1] | 4.896582611 | 4.772078354 / 0.124504257 | 4.775904514 / 0.120678097 | none |
| 3 | [2, 0] | 4.871738798 | 4.772078354 / 0.099660444 | 4.776282216 / 0.095456582 | none |
| 4 | [2, 1] | 4.848516340 | 4.772078354 / 0.076437986 | 4.758294193 / 0.090222147 | none |
| 5 | [1, 0] | 4.755957437 | 4.601915551 / 0.154041886 | 4.594443096 / 0.161514341 | Chase Brown, Sam LaPorta |

**Entry 1**: Chase Brown $6900; Jaylen Warren $6700; Sam LaPorta $4900; Amon-Ra St. Brown $7900; Michael Wilson $6200; Malik Washington $4600; Isaac TeSlaa $3400; Jets $2700; Jared Goff $6600.

**Entry 2**: Chase Brown $6900; Jaylen Warren $6700; Sam LaPorta $4900; Amon-Ra St. Brown $7900; Michael Wilson $6200; DK Metcalf $5400; Kendrick Bourne $3400; Vikings $3100; Jacoby Brissett $5500.

**Entry 3**: Chase Brown $6900; RJ Harvey $5200; Trey McBride $6700; Sam LaPorta $4900; Amon-Ra St. Brown $7900; DK Metcalf $5400; Isaac TeSlaa $3400; Commanders $2900; Jared Goff $6600.

**Entry 4**: Chase Brown $6900; Jonathan Taylor $7800; Sam LaPorta $4900; Michael Wilson $6200; DK Metcalf $5400; Jameson Williams $5900; Isaac TeSlaa $3400; Browns $2800; Jared Goff $6600.

**Entry 5**: Jaylen Warren $6700; RJ Harvey $5200; Trey McBride $6700; Amon-Ra St. Brown $7900; Michael Wilson $6200; DK Metcalf $5400; Isaac TeSlaa $3400; Jets $2700; Jacoby Brissett $5500.

### Run 139d5544

| Step | Template (catchers, bring-backs) | Winner objective | Gibbs best / gap | Wilson best / gap | Already exposure-blocked |
| --- | --- | --- | --- | --- | --- |
| 1 | [1, 0] | 4.620257829 | 4.456067730 / 0.164190099 | 4.585577368 / 0.034680461 | none |
| 2 | [1, 1] | 4.591217214 | 4.448569173 / 0.142648041 | 4.579665049 / 0.011552165 | none |
| 3 | [1, 0] | 4.566800728 | 4.448569173 / 0.118231555 | 4.532189741 / 0.034610988 | none |
| 4 | [1, 1] | 4.555643561 | 4.448569173 / 0.107074388 | 4.511047232 / 0.044596329 | none |
| 5 | [1, 0] | 4.421622239 | 4.317375197 / 0.104247042 | 4.367377077 / 0.054245162 | Chase Brown, Michael Wilson, Jaylen Warren |

**Entry 1**: Chase Brown $6900; Jaylen Warren $6700; Michael Mayer $3500; Amon-Ra St. Brown $7900; Michael Wilson $6200; DK Metcalf $5400; Malik Washington $4600; Vikings $3100; Jacoby Brissett $5500.

**Entry 2**: Chase Brown $6900; Jonathan Taylor $7800; Jaylen Warren $6700; Sam LaPorta $4900; Michael Wilson $6200; DK Metcalf $5400; Kalif Raymond $3900; Jets $2700; Jacoby Brissett $5500.

**Entry 3**: Chase Brown $6900; Jaylen Warren $6700; Sam LaPorta $4900; Michael Wilson $6200; DK Metcalf $5400; Devaughn Vele $5200; Luther Burden III $4900; Broncos $3200; Jared Goff $6600.

**Entry 4**: Chase Brown $6900; Jaylen Warren $6700; Sam LaPorta $4900; Harold Fannin Jr. $4400; Jaxon Smith-Njigba $8800; Michael Wilson $6200; Roman Wilson $3700; Commanders $2900; Jacoby Brissett $5500.

**Entry 5**: Jonathan Taylor $7800; RJ Harvey $5200; Trey McBride $6700; Amon-Ra St. Brown $7900; DK Metcalf $5400; Malik Washington $4600; Roman Wilson $3700; Broncos $3200; Jacoby Brissett $5500.

**VERIFIED:** both players remain feasible in all ten conditional solves; neither is exposure-blocked. The broad run’s fifth step blocks Brown and LaPorta; tight fifth step blocks Brown, Warren, and Michael Wilson. Original overlap≤5 binds roster exploration, but does not make Gibbs or Garrett infeasible. Their best alternatives are quantified above under exactly the original exposure/overlap history, not under a reset portfolio. Full remaining-count maps, excluded roster UUIDs, selected roster UUIDs, and objective decompositions are preserved for every step.

The broad run cycles `[1,0], [1,1], [2,0], [2,1], [1,0]`; the tight cap filters out double-stack templates, producing `[1,0], [1,1], [1,0], [1,1], [1,0]`. No exact-count ceiling prevents the broader first entry from carrying three pass catchers. All five entries in each run have ARI–DET as the primary QB game; broad QB mix is Goff three / Brissett two, tight mix Goff one / Brissett four. There is no primary-game portfolio cap, so opposite QB directions are allowed to concentrate in the same game.

| Tight portfolio one-rule change | Entries solved | Gibbs entries | Wilson entries | QB primary-game counts |
| --- | --- | --- | --- | --- |
| fixed_template | 5 | 0 | 0 | {'ARI-DET': 5} |
| no_exposure | 5 | 0 | 0 | {'ARI-DET': 5} |
| no_overlap | 5 | 0 | 0 | {'ARI-DET': 5} |

`fixed_template` replaces cycling with `[1,0]` throughout; `no_exposure` raises the global limit from four to five appearances while preserving overlap; `no_overlap` raises allowed overlap from five to eight while preserving exposure and excluding exact duplicate rosters. Neither player enters any of these one-rule portfolios. This does not prove every joint portfolio optimum omits them. It does show no single tested sequential policy is sufficient to reverse their omission.

**Single-entry versus portfolio:** unrestricted A equals the actual first entry of the corresponding saved run exactly. Later entries deliberately sacrifice individual objective because of template/overlap/exposure history; they are not competing recommendations for a single entry on a common feasible region. The sum of five scores is not a contest-portfolio EV calculation. If the product wants one recommendation, it should explicitly solve/select one entry and separately expose robustness alternatives.

## 8. Small control group and systemic interpretation

Control players were chosen by frozen mean, salary band, and saved exposure, never realized results: highest-mean omitted RB/WR examples, frequently selected players, and competitive $4,500–$7,000 omitted/rare players. This is a small diagnostic group, not a league-wide statistical test.

| Control | Salary | Mean | P90 | Tight frequency | Best forced objective | Gap |
| --- | --- | --- | --- | --- | --- | --- |
| Jahmyr Gibbs | 9800 | 19.3750 | 32.4991 | 0/5 | 4.456067730 | 0.164190099 |
| Christian McCaffrey | 8200 | 13.1325 | 21.1619 | 0/5 | 4.431767682 | 0.188490147 |
| Nico Collins | 7500 | 13.3802 | 23.0731 | 0/5 | 4.505761693 | 0.114496136 |
| Garrett Wilson | 6600 | 12.2087 | 25.0869 | 0/5 | 4.585577368 | 0.034680461 |
| Chase Brown | 6900 | 17.3314 | 30.4555 | 4/5 | 4.620257829 | 0.000000000 |
| Jaylen Warren | 6700 | 15.4781 | 28.6021 | 4/5 | 4.620257829 | 0.000000000 |
| Michael Wilson | 6200 | 15.1146 | 27.9928 | 4/5 | 4.620257829 | 0.000000000 |
| DK Metcalf | 5400 | 13.5991 | 26.4773 | 4/5 | 4.620257829 | 0.000000000 |
| Jared Goff | 6600 | 26.1925 | 37.0224 | 1/5 | 4.566800728 | 0.053457100 |
| Brock Purdy | 6500 | 24.2888 | 35.0095 | 0/5 | 4.347565676 | 0.272692152 |

**VERIFIED:** Brown, Warren, Michael Wilson and Metcalf each reach the four-of-five exposure ceiling; requiring them in the best entry costs zero. Omitted McCaffrey, Nico Collins, Purdy and Gibbs remain feasible but have positive objective gaps. This is salary/construction efficiency rather than an explicit expensive-player exclusion. No points/$ score is directly added to the objective; the salary constraint produces that preference endogenously. Salary also appears upstream as a model feature; that is a separate model-design question.

**LIKELY systemic weaknesses:** mixing stale cross-team opportunity histories can overcompress current roles; a strong shared anchor weight propagates that compression into many player means; coarse within-role tails give limited individual ceiling discrimination; unvalidated repeated correlation rewards can concentrate a portfolio into one game; zero forward-role signals and missing optimal probabilities leave promised scoring channels partially unsupported; retaining only strict sequential winners hides near-optimal, uncertainty-relevant alternatives.

**NOT ESTABLISHED:** cheap players are overprojected in actual performance, expensive stars are systematically underprojected, any particular roster would outperform the selected roster, more coverage is inherently desirable, or any adjusted scoring model would improve out-of-time EV. Week 3 frozen P90 offset repetition is corroborating structural evidence only; no past realized outcomes were used to alter or select Week 5 players.

## 9. Ranked root causes

| Rank | Cause | Evidence status | What it explains |
| --- | --- | --- | --- |
| 1 | Upstream opportunity allocation + 55% anchor blend | VERIFIED mechanism; LIKELY modeling defect | Stale KC/Pacheco shares suppress Gibbs workload; normalized NYJ allocations reduce Garrett targets; Gibbs mean −4.4981 and Garrett −3.7851 versus pre-opportunity means. |
| 2 | Salary opportunity cost under the resulting means/tails | VERIFIED | Gibbs only +2.0436 over Brown for +$2,900; Garrett trails Metcalf for +$1,200; exact forced package gaps persist under tested rule relaxations. |
| 3 | Caps interact with mandatory stacking and game concentration | VERIFIED | Team 2 forbids Goff+Gibbs+catcher; game 3 materially cuts Gibbs alternatives; relaxing team alone favors competing lineups even more. |
| 4 | Coarse cohort P90 and accumulating correlation policy | VERIFIED structure; LIKELY design weakness | Same-bin P90 repeats mean; broad original favors Goff stack despite lower aggregate mean/P90 than correlation-off alternative. |
| 5 | Partial scoring support: zero leverage and role signals | VERIFIED missing inputs; impact of correction NOT ESTABLISHED | Nominal 5% term contributes zero; Gibbs receiving targets do not activate receiving-back correlations. |
| 6 | Only sequential winners are retained | VERIFIED | Garrett second-entry alternative at gap 0.011552 is not exported; internal exact solver search is not user-visible candidate discovery. |

The omission is therefore mathematically defensible conditional on the frozen model and policies. It is **not** evidence that those football assumptions or the contest objective are accurate. There is concrete evidence warranting a general upstream allocation and objective-support audit before any production optimizer change.

## 10. Recommended corrections, risks, and expected effects

| Priority | Correction to investigate | Expected effect | Risk / acceptance gate |
| --- | --- | --- | --- |
| 1 | Reconcile opportunity windows/team membership before normalization; record source game weeks, team, age and denominator; distinguish historical removals from actual current-team vacated work. | Prevent unavailable old-team roles from diluting current-team shares; make the football workload chain reviewable. | Do not automatically allocate all missing work. Require common-window conservation, transfer/inactive-player fixtures and prior-only backtests; player means may rise or fall. |
| 2 | Audit anchor activation and 55% blend using the original allocations; expose pre/post workload and pre/post point means. | Reveal when team availability changes suppress unrelated players or overpower other projection evidence. | Validate out of time before changing a shared coefficient; individual Gibbs/Wilson before/after mean differences are not treatment estimates of a corrected policy. |
| 3 | Expose actual leverage support separately from ownership support. | Report the effective four-channel score truthfully; make absent optimal probability explicit. | No blind redistribution of 5% or ownership-only leverage substitute; estimate and calibrate optimal probability with time-safe simulations before adding it. |
| 4 | Reconcile forward role evidence with usable receiving/rushing correlation inputs and distinguish missing from measured zero. | Enable evidence-backed receiving-back construction evaluation; stop presenting unsupported zeros as complete football context. | Do not infer true forward role merely from salary or grant a Gibbs bonus; certify provenance and compare all eligible roles uniformly. |
| 5 | Offer one-entry selection plus bounded near-optimal alternative diagnostics using the same original objective. | Retain/report close alternatives and construction reasons, including Wilson’s 0.011552 second-step gap; clarify five-entry objective mismatch. | Coverage is a diagnostic, not EV; specify objective-gap bounds and legality, preserve model truth, do not auto-promote the alternative. |
| 6 | Validate correlation pair/format increments and repeated calibration-bin tails against historical frozen prelock slates. | Test whether construction bonuses and cohort P90 improve actual ranking/calibration rather than just concentration. | Avoid outcome leakage and arbitrary weights. Evaluate incrementally with mean/uncertainty calibration, lineup ranking and contest-aware metrics; no conclusion from Week 5 outcomes. |
| 7 | Explain joint cap/stack feasibility before solving and report primary-game exposure. | Show why Goff+Gibbs is impossible at team two; make repeated ARI–DET portfolio concentration explicit. | Do not relax user limits silently or assume concentrated/relaxed lineups are worse/better; allow the user to choose a construction policy with quantified tradeoffs. |

No listed correction was applied to production in this audit. No player-specific bonus, lock rule, lineup deployment, or weight change is recommended as an immediate fix.

## 11. Reproduction, tests, source hashes, and limits

Offline reproduction from the committed-style research artifacts (run from repository root):

```sh
.venv/bin/python scripts/audit_classic_gibbs_wilson.py
.venv/bin/python scripts/complete_classic_gibbs_wilson_audit.py
.venv/bin/python scripts/test_classic_gibbs_wilson_audit.py
.venv/bin/python scripts/render_classic_gibbs_wilson_audit.py
```

The first script validates the tight saved contract against current implementation/solver and fails on drift. Recover the archived source/environment or establish explicitly labelled model parity if that guard fails. `source/` preserves analyzed module content, but is not a standalone full environment. Capture scripts are optional read-only local PostgreSQL exports using `SET TRANSACTION READ ONLY`; they must not replace frozen exports for an ordinary reproduction. Source native keys and canonical UUIDs are retained.

**VERIFIED validation:** 95 diagnostic/replay solves, 93 feasible optimal proofs and two deliberately infeasible Detroit constructions; eight acceptance tests passed. Tests cover export/source hash integrity, all ten original mathematical fingerprints/rosters/scores, DraftKings position/salary/identity and DST restrictions for returned lineups, forced-inclusion monotonicity, cap relaxation monotonicity, CBC proof logs, independent original-score reconstruction, upstream blend arithmetic, stale cross-team raw history, and zero leverage/role signals. All viable solves use bundled CBC 2.10.3 with no configured time/node/nonzero-gap stop. Integer optimum is certified within solver tolerances, not an exact-arithmetic proof. Infeasible solve objective values in raw JSON are LP/intermediate values and are never interpreted as lineup scores.

Evidence files: `results.json` (full solver/constraint/score evidence), `bd990e1b_run.json`, `139d5544_run.json` (original saved records), `projection_lineage.json` (310 original feature rows + saved model/run metadata), `opportunity_history.json` (last-three prelock raw observations), `solver_logs/`, `source/`, `tests.log`, and `manifest.json`. `player_evidence.json` is a compact convenience view; the full frozen snapshots and original feature rows are authoritative.

| Immutable input | SHA256 |
| --- | --- |
| bd990e1b_run.json | 3f9e5947a862af244be8b1cc94f17fd25ba9e4a7c0d61a3f4e4e0e1ec22baa3d |
| 139d5544_run.json | 417f0baf54e0b68cbc07374692b5ffc1365c40994cb7294c29776256c6bd04fa |
| projection_lineage.json | 4e2ce15e5226b50fedd4d914344d86437f8bce2f2ee1fe7393aa9cd32297ace7 |
| projection model artifact | 61bd54c9235aad78c12977fb1e4f2f9747ae5a3489d88e917d34a976586d6412 |
| training dataset | 8caf66c7cd63dde8d6ac4a50f02258e61fe7724869c126efa7c1cb66269cef83 |

**Limits:** no joint portfolio solve, contest-field simulation, outcome-based EV validation, retraining, full counterfactual projection rebuild, or independent official-stat verification was performed. Raw history reads are bounded by the original received cutoff and game week, but use the current alias mapping; the canonical native keys match saved role evidence, and this limitation is recorded. Upstream saved arithmetic and inputs are verified; current projection-source code is a mechanism explanation, not a claim to possess its complete original historical implementation. The original run/model code hashes remain preserved. Snapshot cutoff is October 9, 2026 21:56:16 UTC (4:56:16 p.m. America/Chicago), before Sunday October 11 games. Earlier Week 3 evidence is prelock offsets only. Neither external results nor realized Week 5 outcomes were consulted.

**Answer to the final question:** other players win consistently because the frozen model makes Brown/Warren and selected WR packages more affordable sources of mean/cohort ceiling, favors ARI–DET stacks, and only exports the best remaining sequential solve. Gibbs’s salary and cap/stack opportunity cost is larger; Garrett can be nearly tied yet still omitted without any retention mechanism. The solver behavior is demonstrated and correct for its stated objective. The stale cross-team opportunity normalization, partial scoring support and coarse tail/construction design prevent treating that correctness as proof of sound football projections or contest EV. Address those general mechanisms with reproducible, time-safe validation before changing production.
