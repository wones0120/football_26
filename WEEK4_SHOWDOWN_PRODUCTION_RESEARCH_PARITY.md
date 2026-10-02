# Week 4 PIT–CLE Showdown production/research parity

## Executive summary

The original run is reproduced exactly: **149 scenario/CPT/FLEX variants, 117 distinct canonical CPT/FLEX rosters, five quality-eligible choices, four selected entries**. Every saved ranked metric matches. The fresh expanded replay reproduces **all 770 research rosters**, with no missing or additional rosters and the same primary ranks 2 / 3 / 35.

Two scoring bugs are confirmed: conditional-world forecasts raise the common quality floor and remain in cross-world portfolio ranking; complete but unreliable ownership is enabled without Showdown selector promotion. Both are corrected locally. The CLE 5–1 reward uses the intentional −14 conditional margin, not CLE's +2.5 baseline spread; its description/evidence now identifies that assumption.

**Use the research shadow for the requested three-entry decision, subject to final-lock availability checks.** The corrected, unchanged production 95% quality policy cannot provide three distinct supported theses with distinct captains and overlap ≤4. It returns two in the audited three-entry joint solve. No third roster is invented and no quality, exposure, ownership weight, prior, projection, correlation weight, or thesis parameter is lowered. Fixing semantics does not make the two portfolio policies equivalent.

## Production vs research architecture

Audit frozen at 20261001T153239Z; report generated 2026-10-01T17:08:12.259594+00:00. Inputs and every shadow are stored under [artifacts/week4_showdown_production_research_parity/20261001T153239Z](artifacts/week4_showdown_production_research_parity/20261001T153239Z). The morning and overnight reports/source bundles are unchanged.

The morning projection run is `e62f4bbb-690b-40a2-8f09-0f026692a649` (06:46 EDT); production job `ffb8acf8-2e31-414e-81da-417d6d82c584` pins `7b1146b4-e4b5-41d4-bad4-64f7c9f406a7` (11:07 EDT) and ownership run `110444e7-2ae3-401b-98ed-e167c575a2c6`. **All 51 canonical players have exactly equal salaries, means, P90s, CPT/FLEX DK IDs and ownership values across the two freezes.** Preparation/conditional scoring agrees with all 206 production discovery outputs within 4.27×10⁻¹⁴ selector points. Common final rows retain the pinned production lineage. Run-ID equality was not assumed.

Production v3 solves 30 global objective alternatives, a sequential five, existing scripts, raw global mean/P90, each viable captain's best plus two alternatives and raw mean/P90 choices, two conditional winners, conditional constructions, and exposure-gap probes. Research enumerates 20 ceiling and five mean alternatives per captain, forced FLEX, QB directions, team splits, structural combinations and conditional exact captain/construction sweeps; conditional rosters are then baseline-rescored.

Production ranks by the raw captain-informed MILP selector and uses a 95% joint mean/P90 screen. Research uses `showdown_single_entry.DEFAULT_WEIGHTS` (mean .35, P90 .30, solver .20, correlation .10, context .05, chalk .03), fixed-universe normalization, a .10 selector frontier and a joint captain/thesis/overlap solve. These **existing selectors differ intentionally**; neither is retuned here. The 5-max production solve has exposure caps and roster uniqueness but no max-overlap-four or distinct-thesis constraint. Those constraints are applied in the requested three-entry audit shadows.

## Candidate-universe diff

| Quantity | Count |
| --- | --- |
| both | 115 |
| common_legal | 533 |
| production_only | 2 |
| production_rosters | 117 |
| production_scenario_variants | 149 |
| rejected | 239 |
| research_only | 655 |
| research_rosters | 770 |

The original “149 distinct candidates” means distinct **scenario plus canonical CPT/FLEX signature**, not 149 independent rosters. There are 102 baseline, 23 CLE-decisive and 24 PIT-decisive variants. Canonical identity includes captain allocation; row ordering and scenario labels do not create another entered roster.

The 772-roster union contains 239 rosters with a selected DST and an opposing non-DST player. All 239 fail the saved production `avoid_dst_opponents=true` rule. The common legal universe is therefore **533**; no salary, projection or source is changed to admit them. This explains the two absent production DSTs. Research covers 23 CPT and 23 FLEX players; production covers 21 CPT and 17 FLEX players. Its raw universe has zero total coverage only for Browns and Steelers. Zero production FLEX coverage: Whiteheart, Browns, Washington, Heidenreich, Steelers, Homer. These gaps include role legality and shallow generation; they are not all hard exclusions.

Canonical production/research QB-direction counts: PIT-only **7 / 139**, CLE-only **45 / 290**, both QBs **65 / 341**. No zero-QB roster is allowed. CLE/PIT construction counts: 1/5 **11 / 90**, 2/4 **18 / 150**, 3/3 **36 / 234**, 4/2 **37 / 208**, 5/1 **15 / 88**. Every legal team split and starting-QB direction is present; research deepens them. Conditional production variants include both team winner families, but no scenario label is interpreted as a new unconditional forecast.

Best original research-only candidates: rank 10 Watson CPT / Jeudy, Boston, Roman Wilson, Metcalf, Rodgers (selector .901259); rank 17 Jeudy CPT / Concepcion, Watson, Metcalf, Warren, Rodgers (.896310); rank 18 Jeudy CPT / Watson, Freiermuth, Metcalf, Warren, Rodgers (.896232). They are discovery-depth gaps, not removed by a candidate-count admission cap. The two production-only signatures are Metcalf CPT with Jeudy/Boston/Watson/McLaughlin/Rodgers, and Judkins CPT with Jeudy/Roman Wilson/Metcalf/Warren/Rodgers. McLaughlin is excluded from final three-entry shadows because the immutable evidence does not verify a credible offensive role.

Discovery classification and original expanded-universe contribution (sources overlap; exclusive means no other source family covers that roster in the .10 frontier):

| Source family | Roster coverage | Research only | Frontier .10 | Exclusive .10 | Seconds |
| --- | --- | --- | --- | --- | --- |
| captain_ceiling | 460 | 356 | 196 | 75 | 75.70 |
| captain_mean | 115 | 73 | 43 | 7 | 7.76 |
| conditional_exact | 354 | 295 | 97 | 10 | 17.98 |
| construction | 50 | 21 | 39 | 4 | 5.34 |
| forced_flex | 49 | 26 | 40 | 11 | 4.94 |
| global_ceiling | 40 | 13 | 40 | 1 | 5.93 |
| global_mean | 25 | 11 | 22 | 2 | 4.51 |
| overnight_primary_re_evaluation | 3 | 0 | 3 | 0 | 0.00 |
| qb_construction | 45 | 21 | 35 | 1 | 4.26 |
| scenario | 238 | 190 | 70 | 0 | 6.88 |
| structure | 54 | 39 | 16 | 1 | 5.58 |

Captain ceiling enumeration adds the most coverage (75 exclusive frontier rosters), then forced FLEX (11), exact conditional enumeration (10), captain mean (7), and construction (4). The cheaper approximate `scenario` sweep has zero exclusive frontier coverage and overlaps the exact conditional/other sweeps. It is a candidate for removal in a later measured shadow, not removed here. Captain ceiling costs the most compute but adds substantial coverage. These are one-slate measurements, not evidence of historical generalization.

Original discovery took 146.80 seconds plus 21.91 seconds for exact conditional extension. Fresh replay took 159.67 seconds including its 24.82-second extension. Original production reconstruction took 30.64 seconds; corrected reconstruction took 51.55 seconds. Runtime varies with concurrent local work; source counts and exact rosters are the reproducibility checks. No configured production discovery source was accidentally skipped; broader research depth and missing research-only families are intentional architecture differences.

## Ownership-policy diff

Source: `slate_aware_ownership_v2_prelock`, pinned run `110444e7-2ae3-401b-98ed-e167c575a2c6`. Raw full-slate totals are **260.871164% CPT / 380.727935% FLEX**, rather than 100% / 500%. The model clips individual predictions to [0,100] but does not normalize these slot totals. The original selector subtracts **.08 × summed selected slot ownership**. This is a soft objective penalty; there is no hard ownership feasibility constraint.

| Player | Raw CPT % | Raw FLEX % |
| --- | --- | --- |
| Jerry Jeudy | 3.192805 | 10.609392 |
| Denzel Boston | 14.396988 | 23.236448 |
| Deshaun Watson | 18.366259 | 34.135491 |
| DK Metcalf | 16.182402 | 33.915727 |
| Jaylen Warren | 23.923400 | 48.105893 |
| Aaron Rodgers | 36.341026 | 32.059902 |

Saved Showdown calibration: CPT MAE 12.920635 / bias +11.568737 / 241 observations; FLEX MAE 7.593293 / bias −3.985002 / 429 observations. The overall model gate says passed but explicitly says “diagnostic only; model promotion remains explicit.” That global validation pass is not reliable Showdown slot promotion. Production originally checked complete values alone; research masked these same estimates before both MILP capture and selection.

On the identical 149 variants, masking changes **134 ranks**, top-20 overlap is 17/20, maximum movement 19 ranks. The raw ownership penalty ranges from -14.042065 to -9.572219. Denzel Boston remains first. The original four-entry portfolio is unchanged by ownership alone; its total selector rises from 572.814840 to 616.307771 because that penalty is unavailable. Those different score scales are not a measured football improvement.

Duplication diagnostics use the product of selected slot probabilities (log-summed), then relative chalk = 100 × exp(log probability − chalkiest candidate log probability). The single-entry selector uses −.03 × relative-chalk fraction. Production v3's final solve uses the raw solver objective; duplication/chalk does not impose a separate constraint. No unsupported absolute duplication probability is inferred from the unnormalized estimates. In masked shadows chalk/duplication is unavailable, not zero-filled to confer an advantage; normalized selector weights remain unchanged.

The fix requires saved `metrics_json.selector_approval_by_format.showdown.status = approved` before live use. Missing approval or incomplete values masks every player's live ownership uniformly and retains diagnostic estimates. It adds no calibration threshold or ownership-weight change, does not train or promote a model, and leaves Classic ownership alone.

## Scenario quality-floor audit

**Confirmed semantic bug:** the original portfolio compares conditioned means/P90s in both raw ranking and the common quality screen. Its mean maximum 72.476553 comes from PIT-decisive; its P90 maximum 149.632226 comes from CLE-decisive. The 95% thresholds, 68.852726 / 142.150615, combine mutually conditional worlds. The baseline family cannot pass: its best mean is only 67.921047 even though its best P90 is 142.535788.

Method B uses conditional pools only to discover identities/CPT allocation, then solves each exact roster under baseline projections, market context, correlation objective and prior. Conditioned values remain diagnostic. Common thresholds are **64.524995 mean / 135.408999 summed marginal P90**. Method C screens within each world's local maxima first, then combines survivors under the common baseline selector with no second global floor; it is diagnostic and is not promoted.

The same original raw discovery universe is used for A/B/C; discovery is not rerun between these methods. Totals below sum entry metrics; summed marginal P90 is not portfolio P90:

| Method | Entries | Raw selector | Baseline mean | Baseline P90 | Conditioned mean | Conditioned P90 | Captains |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A_current | 4 | 572.814840 | 258.681403 | 546.072371 | 277.926627 | 586.168816 | DK Metcalf, Deshaun Watson, Quinshon Judkins, Deshaun Watson |
| B_baseline_live | 4 | 554.335323 | 261.661580 | 558.847862 | 261.661580 | 558.847862 | Denzel Boston, Jerry Jeudy, Denzel Boston, KC Concepcion Jr. |
| B_baseline_masked | 4 | 607.954571 | 261.661580 | 558.847862 | 261.661580 | 558.847862 | Denzel Boston, Jerry Jeudy, Denzel Boston, KC Concepcion Jr. |
| C_scenario_local_then_baseline | 5 | 751.586916 | 325.284821 | 692.096037 | 333.299436 | 709.350475 | Denzel Boston, Jerry Jeudy, DK Metcalf, DK Metcalf, Jaylen Warren |

**A_current**

| Entry | Exact roster |
| --- | --- |
| 1 | DK Metcalf CPT; Jerry Jeudy, Deshaun Watson, Roman Wilson, Jaylen Warren, Aaron Rodgers |
| 2 | Deshaun Watson CPT; Jerry Jeudy, Quinshon Judkins, Denzel Boston, KC Concepcion Jr., DK Metcalf |
| 3 | Quinshon Judkins CPT; Jerry Jeudy, Denzel Boston, KC Concepcion Jr., Deshaun Watson, DK Metcalf |
| 4 | Deshaun Watson CPT; Jerry Jeudy, Quinshon Judkins, Denzel Boston, Andre Szmyt, DK Metcalf |

Scenario allocation: {'team_a_decisive_win': 3, 'team_b_decisive_win': 1}; pairwise shared-player counts: [3, 3, 3, 6, 5, 5].

**B_baseline_live**

| Entry | Exact roster |
| --- | --- |
| 1 | Denzel Boston CPT; Jerry Jeudy, KC Concepcion Jr., Deshaun Watson, DK Metcalf, Jaylen Warren |
| 2 | Jerry Jeudy CPT; Quinshon Judkins, Denzel Boston, Deshaun Watson, DK Metcalf, Jaylen Warren |
| 3 | Denzel Boston CPT; Quinshon Judkins, Deshaun Watson, Jaleel McLaughlin, DK Metcalf, Jaylen Warren |
| 4 | KC Concepcion Jr. CPT; Jerry Jeudy, Quinshon Judkins, Deshaun Watson, DK Metcalf, Jaylen Warren |

Scenario allocation: {'baseline': 4}; pairwise shared-player counts: [5, 4, 5, 5, 5, 4].

**B_baseline_masked**

| Entry | Exact roster |
| --- | --- |
| 1 | Denzel Boston CPT; Jerry Jeudy, KC Concepcion Jr., Deshaun Watson, DK Metcalf, Jaylen Warren |
| 2 | Jerry Jeudy CPT; Quinshon Judkins, Denzel Boston, Deshaun Watson, DK Metcalf, Jaylen Warren |
| 3 | Denzel Boston CPT; Quinshon Judkins, Deshaun Watson, Jaleel McLaughlin, DK Metcalf, Jaylen Warren |
| 4 | KC Concepcion Jr. CPT; Jerry Jeudy, Quinshon Judkins, Deshaun Watson, DK Metcalf, Jaylen Warren |

Scenario allocation: {'baseline': 4}; pairwise shared-player counts: [5, 4, 5, 5, 5, 4].

**C_scenario_local_then_baseline**

| Entry | Exact roster |
| --- | --- |
| 1 | Denzel Boston CPT; Jerry Jeudy, KC Concepcion Jr., Deshaun Watson, DK Metcalf, Jaylen Warren |
| 2 | Jerry Jeudy CPT; Quinshon Judkins, Denzel Boston, Deshaun Watson, DK Metcalf, Jaylen Warren |
| 3 | DK Metcalf CPT; Quinshon Judkins, Denzel Boston, Deshaun Watson, Jaleel McLaughlin, Aaron Rodgers |
| 4 | DK Metcalf CPT; Jerry Jeudy, Deshaun Watson, Roman Wilson, Jaylen Warren, Aaron Rodgers |
| 5 | Jaylen Warren CPT; Jerry Jeudy, Quinshon Judkins, Denzel Boston, KC Concepcion Jr., Deshaun Watson |

Scenario allocation: {'baseline': 3, 'team_a_decisive_win': 1, 'team_b_decisive_win': 1}; pairwise shared-player counts: [5, 3, 4, 5, 4, 4, 5, 3, 3, 3].

The corrected generator rerun additionally masks ownership during discovery and repairs exposure-gap probing's common floor: **148 variants, 17 qualifying variants, 4 entries**. Its baseline maxima remain 67.921047 / 142.535788. This is distinct from the fixed-universe Method B comparison. Full conditioned/baseline player diagnostics and family reports are preserved in JSON.

## 5–1 favorite rule audit

Rule `construction.showdown_favorite_five_one_v1` has unchanged weight +.60 and uses `favorite_script = scaled_below(team_spread, −3, 10)`. Baseline CLE +2.5 produces zero. `condition_player_pool` deliberately substitutes CLE −14 / PIT +14 in the CLE-decisive world; that saturates the signal at 1.0 and yields +.60. This is **LABELING ISSUE**, not an incorrect baseline favorite input.

Conditional evidence now carries `market_basis=conditional_winner_assumption`, and the triggered description says “Reward a 5-1 build under the conditional decisive-winner assumption.” Baseline evidence says `baseline_market`. Rule IDs, signal formula, weights, construction legality and decisive margins are unchanged. Common-baseline rescoring removes the conditional favorite reward from final cross-world comparison.

## Four-of-five underfill diagnosis

The exact original joint screen leaves Metcalf CPT, Watson CPT twice with different FLEX constructions, Judkins CPT and Warren CPT. Every one includes **Metcalf + Jeudy + Watson**. Metcalf and Jeudy each have ceil(5 × .80) = four allowed appearances; Watson's starting-QB cap is five. Selecting all five violates both non-QB caps. Relaxing either Metcalf alone or Jeudy alone still returns four. Captain cap three is not the binding cause.

No ownership, overlap or scenario restriction causes the original underfill: ownership is soft; max overlap is not enforced by v3; `require_scenario_diversity=false`. Canonical captain/slot signatures are distinct and duplicates are grouped across scenarios. The MILP maximizes count first, then selector; this is true finite-universe infeasibility, not a greedy selector failure.

Every relaxation below changes one category relative to A:

| Shadow | Entries | Captains |
| --- | --- | --- |
| A_current | 4 | DK Metcalf, Deshaun Watson, Quinshon Judkins, Deshaun Watson |
| relax_universe_only | 4 | DK Metcalf, DK Metcalf, DK Metcalf, Deshaun Watson |
| relax_quality_floor_only | 5 | Denzel Boston, DK Metcalf, DK Metcalf, DK Metcalf, Michael Pittman Jr. |
| relax_ownership_only | 4 | DK Metcalf, Deshaun Watson, Quinshon Judkins, Deshaun Watson |
| relax_exposure_caps_only | 5 | DK Metcalf, Deshaun Watson, Quinshon Judkins, Deshaun Watson, Jaylen Warren |
| relax_scenario_restrictions_only | 4 | DK Metcalf, Deshaun Watson, Quinshon Judkins, Deshaun Watson |

Universe-only means all 533 common legal rosters across the same three conditioned worlds; it still returns four. Ownership-only returns the same four. Removing exposure caps or the quality floor permits five. The first exact original-universe quality breakpoint permitting five is **0.897643059975**; the next stricter candidate breakpoint is 0.899731834863. This roughly 89.76% requirement is a diagnostic feasibility result, **not a recommendation to lower 95%**. Exposure removal admits Metcalf/Jeudy five-of-five. Neither is promoted.

After baseline corrections, exposure-gap discovery adds eight source hits but the corrected production universe still fills four under existing caps. Underfill diagnostics explicitly distinguish insufficient distinct quality-eligible rosters from exposure infeasibility. Original and corrected per-candidate omission reasons remain available.

## Exposure denominator audit

Caps intentionally use requested entries; realized percentages use actual selected entries. For the original job:

| Player | Configured class cap | Requested denominator | Allowed appearances | Actual appearances | Realized denominator | Realized exposure |
| --- | --- | --- | --- | --- | --- | --- |
| Metcalf | .80 core | 5 | 4 | 4 | 4 | 100% |
| Jeudy | .80 core | 5 | 4 | 4 | 4 | 100% |
| Watson | 1.00 starting QB | 5 | 5 | 4 | 4 | 100% |

“Cap respected” is correct as an appearance-count statement, not a promise of ≤80% realized exposure when the portfolio underfills. The existing accounting already used both denominators; there is no arithmetic bug. Top-level `cap_denominator` and `realized_exposure_denominator` are now explicit. No cap is recalculated from four and no selection parameter is changed.

## Three-entry A/B comparison

All common-universe arms share the same 533 legal canonical rosters. The three-entry solve requires distinct captains, three distinct supported thesis families, maximum pairwise overlap four, requested-three exposure accounting (core/QB ceil-caps three, cheap punt cap two), and excludes unsupported fragile punts. The named unresolved five-player watch list is excluded from final three-entry choices using immutable role evidence; no new activation or role claim is invented.

For production arms, the existing 95% joint quality floor is retained, using conditional forecasts only in the two original-semantics diagnostic arms. The corrected and research arms compare baseline values. The research reference retains its existing .10 normalized-selector frontier instead of production's 95% floor. Thus this table separates selector/floor policy from universe coverage:

| Arm | Entries | Raw solver total | Baseline mean | Baseline P90 | Captains | Overlap |
| --- | --- | --- | --- | --- | --- | --- |
| three_current_common | 3 | 438.238259 | 190.809792 | 405.692846 | Denzel Boston, Jaylen Warren, DK Metcalf | [2, 3, 4] |
| three_masked_conditional_common | 3 | 472.075370 | 194.524737 | 408.918120 | Denzel Boston, Jaylen Warren, DK Metcalf | [4, 3, 4] |
| three_baseline_live_common | 2 | 269.075963 | 133.037679 | 276.273825 | Deshaun Watson, Denzel Boston | [4] |
| three_corrected_common | 2 | 294.179601 | 133.037679 | 276.273825 | Deshaun Watson, Denzel Boston | [4] |
| three_research_reference_common | 3 | 446.093546 | 196.424598 | 412.583390 | DK Metcalf, Deshaun Watson, Jerry Jeudy | [4, 4, 4] |
| three_corrected_production_universe | 2 | 294.179601 | 133.037679 | 276.273825 | Denzel Boston, Deshaun Watson | [4] |

**three_current_common**

| Entry | Exact roster |
| --- | --- |
| 1 | Denzel Boston CPT; Jerry Jeudy, Quinshon Judkins, KC Concepcion Jr., Deshaun Watson, DK Metcalf |
| 2 | Jaylen Warren CPT; Jerry Jeudy, Michael Pittman Jr., Pat Freiermuth, DK Metcalf, Aaron Rodgers |
| 3 | DK Metcalf CPT; Jerry Jeudy, Deshaun Watson, Roman Wilson, Jaylen Warren, Aaron Rodgers |

Theses: ['CLE passing concentration', 'PIT rushing-led concentration', 'PIT passing concentration']; discovery scenarios: {'team_a_decisive_win': 1, 'team_b_decisive_win': 2}.

**three_masked_conditional_common**

| Entry | Exact roster |
| --- | --- |
| 1 | Denzel Boston CPT; Jerry Jeudy, Quinshon Judkins, KC Concepcion Jr., Deshaun Watson, DK Metcalf |
| 2 | Jaylen Warren CPT; Jerry Jeudy, Denzel Boston, Deshaun Watson, Chris Boswell, DK Metcalf |
| 3 | DK Metcalf CPT; Jerry Jeudy, Deshaun Watson, Roman Wilson, Jaylen Warren, Aaron Rodgers |

Theses: ['CLE passing concentration', 'balanced competitive', 'PIT passing concentration']; discovery scenarios: {'team_a_decisive_win': 1, 'team_b_decisive_win': 2}.

**three_baseline_live_common**

| Entry | Exact roster |
| --- | --- |
| 1 | Deshaun Watson CPT; Jerry Jeudy, Quinshon Judkins, Andre Szmyt, DK Metcalf, Jaylen Warren |
| 2 | Denzel Boston CPT; Jerry Jeudy, KC Concepcion Jr., Deshaun Watson, DK Metcalf, Jaylen Warren |

Theses: ['balanced competitive', 'CLE passing concentration']; discovery scenarios: {'baseline': 2}.

**three_corrected_common**

| Entry | Exact roster |
| --- | --- |
| 1 | Deshaun Watson CPT; Jerry Jeudy, Quinshon Judkins, Andre Szmyt, DK Metcalf, Jaylen Warren |
| 2 | Denzel Boston CPT; Jerry Jeudy, KC Concepcion Jr., Deshaun Watson, DK Metcalf, Jaylen Warren |

Theses: ['balanced competitive', 'CLE passing concentration']; discovery scenarios: {'baseline': 2}.

**three_research_reference_common**

| Entry | Exact roster |
| --- | --- |
| 1 | DK Metcalf CPT; Jerry Jeudy, Deshaun Watson, Roman Wilson, Jaylen Warren, Aaron Rodgers |
| 2 | Deshaun Watson CPT; Jerry Jeudy, Denzel Boston, Pat Freiermuth, DK Metcalf, Aaron Rodgers |
| 3 | Jerry Jeudy CPT; Quinshon Judkins, Denzel Boston, Deshaun Watson, DK Metcalf, Jaylen Warren |

Theses: ['PIT passing concentration', 'balanced competitive', 'CLE passing concentration']; discovery scenarios: {'baseline': 3}.

**three_corrected_production_universe**

| Entry | Exact roster |
| --- | --- |
| 1 | Denzel Boston CPT; Jerry Jeudy, KC Concepcion Jr., Deshaun Watson, DK Metcalf, Jaylen Warren |
| 2 | Deshaun Watson CPT; Jerry Jeudy, Quinshon Judkins, Andre Szmyt, DK Metcalf, Jaylen Warren |

Theses: ['CLE passing concentration', 'balanced competitive']; discovery scenarios: {'baseline': 2}.

**No compliant corrected-production trio exists in this universe.** With no fragile punts, only 13 baseline-quality rosters remain. The captain/thesis/overlap MILP's maximum feasible count is two even with the full expanded legal universe. The research primary Watson lineup misses production's baseline mean floor by approximately .288582, and its Metcalf lineup misses the baseline P90 floor by approximately .417254. Enlarging generation cannot remove those intentional policy exclusions. The research common-universe reference reproduces the exact original Metcalf / Watson / Jeudy three; total normalized selector is 2.719396. All pairs overlap four. This is a supported research shadow, not a production trio mislabelled as corrected output.

The two returned corrected-production shadow entries, with their native DK slot identities:

| Entry | Slot | Player | Salary | Native DK ID |
| --- | --- | --- | --- | --- |
| 1 | CPT | Deshaun Watson | 14100 | 44315945 |
| 1 | FLEX | Jerry Jeudy | 3000 | 44315917 |
| 1 | FLEX | Quinshon Judkins | 8800 | 44315896 |
| 1 | FLEX | Andre Szmyt | 4600 | 44315912 |
| 1 | FLEX | DK Metcalf | 9000 | 44315895 |
| 1 | FLEX | Jaylen Warren | 9600 | 44315893 |
| 2 | CPT | Denzel Boston | 12000 | 44315948 |
| 2 | FLEX | Jerry Jeudy | 3000 | 44315917 |
| 2 | FLEX | KC Concepcion Jr. | 6400 | 44315901 |
| 2 | FLEX | Deshaun Watson | 9400 | 44315894 |
| 2 | FLEX | DK Metcalf | 9000 | 44315895 |
| 2 | FLEX | Jaylen Warren | 9600 | 44315893 |

The research reference, retained without forcing agreement:

| Entry | Slot | Player | Salary | Native DK ID |
| --- | --- | --- | --- | --- |
| 1 | CPT | DK Metcalf | 13500 | 44315946 |
| 1 | FLEX | Jerry Jeudy | 3000 | 44315917 |
| 1 | FLEX | Deshaun Watson | 9400 | 44315894 |
| 1 | FLEX | Roman Wilson | 4000 | 44315914 |
| 1 | FLEX | Jaylen Warren | 9600 | 44315893 |
| 1 | FLEX | Aaron Rodgers | 9800 | 44315892 |
| 2 | CPT | Deshaun Watson | 14100 | 44315945 |
| 2 | FLEX | Jerry Jeudy | 3000 | 44315917 |
| 2 | FLEX | Denzel Boston | 8000 | 44315897 |
| 2 | FLEX | Pat Freiermuth | 5600 | 44315908 |
| 2 | FLEX | DK Metcalf | 9000 | 44315895 |
| 2 | FLEX | Aaron Rodgers | 9800 | 44315892 |
| 3 | CPT | Jerry Jeudy | 4500 | 44315968 |
| 3 | FLEX | Quinshon Judkins | 8800 | 44315896 |
| 3 | FLEX | Denzel Boston | 8000 | 44315897 |
| 3 | FLEX | Deshaun Watson | 9400 | 44315894 |
| 3 | FLEX | DK Metcalf | 9000 | 44315895 |
| 3 | FLEX | Jaylen Warren | 9600 | 44315893 |

## Confirmed bugs

1. Conditional worlds contaminated cross-world raw selector comparison and the shared quality floor; exposure-gap probing inherited the same mixed maxima.
2. Production enabled the same unreliable, diagnostic-only ownership estimates that the established research reliability decision masked. Coverage was incorrectly treated as selector promotion.
3. Conditional CLE 5–1 output used a baseline-favorite description despite evaluating a conditional winner assumption. The score itself was correct for that world.

Underfill denominators and canonical roster grouping are not bugs. The source-volume gap is not an accidental configured-source omission.

## Intentional policy differences

Research's deeper per-captain/global/forced-FLEX/QB/construction discovery; production's avoid-DST-opponents toggle; normalized single-entry research selector versus raw v3 MILP ranking; .10 research frontier versus 95% production joint quality floor; requested-entry exposure caps; research captain/thesis/overlap constraints versus v3's ordinary five-entry exposure solve. The conditional winner heuristic remains an intentionally unvalidated discovery assumption, not a scenario probability.

No new QB-archetype prior is active: production still loads `docs/showdown_captain_model_2024_2025.json`, strength .35, classes DST/QB/RB/TE/WR, with the same out-of-distribution historical-position-mix fallback. Its priors are unchanged (WR .414634, QB .243902, RB .219512, TE .097561, DST .024390). No training, archetype promotion or new prior artifact occurs.

## Fixes made

Narrow Showdown changes: `showdown_candidate_comparison.baseline_rescore_discovery` preserves exact identities/CPT and conditioned evidence while baseline-rescoring; `showdown_portfolio_selection` computes common baseline maxima/floors and explicit underfill diagnostics; the v3 candidate branch calls that helper and repairs its exposure-gap floor; `showdown_ownership_policy` requires explicit saved slot promotion and the Showdown strategy branch masks unapproved live inputs; correlation evidence/description distinguishes conditional winner versus baseline market; exposure output explicitly names both denominators.

Discovery depths, 95% policy, weighting functions, priors, role/availability models, projections, scenario formulas, caps and Classic branches are unchanged. New audit scripts are offline, hash-check their inputs and refuse to overwrite result files. Their persistence callback deliberately returns false, so the normal service's final job wrapper reports a persistence failure; the captured candidate/selection shadows are successful. This is a fail-closed **offline harness status**, not an optimizer or database failure. No shadow job or lineup was persisted.

## Tests

**238 targeted/regression tests pass**, covering canonical captain/slot identity, exact discovery-to-baseline rescoring, conditional forecasts unable to raise a baseline floor, local versus common screening, CLE +2.5 and conditional-winner 5–1 semantics, explicit ownership promotion and masking, five-requested/four-selected exposure accounting and exact underfill cause, joint three-entry captain/thesis/overlap solves, no postgame-field influence, selector/optimizer contracts and Classic prospective/thesis/small-field behavior. The final correlation-label check also passes (37 tests).

The original replay matches every saved ranked metric and selected rank 3/11/13/31. All 206 discovery evaluations match exact common conditional-model scores to floating-point tolerance. Fresh expanded generation yields the exact same 770 canonical rosters and ranks 2/3/35. All 239 common-universe rejected rosters have the saved DST-opponent conflict. Python compilation and patch review are recorded in the delivery verification bundle.

## Production preservation

149 protected files are hash-verified unchanged, including morning/overnight evidence, Classic-specific modules, captain model artifacts and `.env.example`; **86 saved Classic configurations** have identical before/after aggregate hash. The original production job's configuration, selected entries and frozen input lineage remain unchanged. The broad optimizer file was already dirty; `audit_code_changes_final.patch` isolates this audit's changes from its starting state.

Only the documented Showdown code paths and diagnostic labels/accounting changed locally. The running backend was not restarted or given a live optimizer job by this audit. No projection/model/ownership job, raw ingest, actual result, submission, or upload CSV was created. No model artifact or configuration weight is promoted. The final-lock report and existing morning/overnight documents are not overwritten.

## Remaining uncertainty

This is a frozen pregame parity audit, not tonight's final inactive/elevation/weather/market reconciliation. The morning availability blockers remain until a separate final-lock check. Ownership is diagnostic pending explicit Showdown promotion, and conditional discovery is heuristic. One slate does not prove generalized completeness or realized performance. A complete corrected-production three cannot be supplied under its unchanged floor; changing the quality/selector portfolio policy requires a separate authorized evaluation. The chronological Classic validation remains outside this redirected task.

### Why does production generate 149 candidates while research generates ~770?

149 is 117 distinct CPT/FLEX rosters tagged across three discovery worlds. Production explores shallow captain alternatives and scripts; research deeply enumerates captain ceiling/mean, forced FLEX, QB constructions, structural/team combinations and exact conditional frontiers. Another 239 research-union rosters conflict with the saved production DST-opponent rule. No arbitrary admission cap or accidentally skipped configured source explains the gap.

### Is production using unreliable Showdown ownership in the live selector?

**YES in the saved/current running job. NO in the corrected offline replay:** estimates are uniformly diagnostic until explicit Showdown selector approval.

### Are conditioned scenario projections contaminating the common quality floor?

**YES in the original implementation. NO after the tested corrections.** Discovery worlds are now baseline-rescored before comparison.

### Why are zero baseline-market lineups selected?

Mixed-world maxima created a 68.852726 mean floor above the entire baseline family's 67.921047 maximum. Baseline correction restores comparable floors; the corrected five-entry replay selects four baseline-tagged rosters.

### Why are three of four selected lineups CLE-decisive?

CLE conditional scoring supplied three of the five quality survivors and elevated their selectors; PIT supplied two, one excluded by shared-core caps. There was no enforced CLE scenario quota or inferred scenario probability.

### Why did production generate only 4 of requested 5 lineups?

All five quality survivors contain both Metcalf and Jeudy; each is capped at four appearances. Ownership/scenario/overlap restrictions are not the binding cause. Masking ownership or widening generation alone still fills four; removing quality or exposure restrictions permits five only diagnostically.

### Is the CLE 5-1 “meaningful favorite” bonus firing correctly?

**LABELING ISSUE.** It correctly fires under CLE −14 conditional winner assumptions, never under baseline CLE +2.5. Evidence/description now states that distinction; +.60 is unchanged.

### Which differences are real bugs?

Mixed-world comparison and floors; unreliable diagnostic ownership enabled by coverage alone; conditional reward labelled as baseline-favorite evidence. All three have narrow tested fixes.

### Which differences are intentional policy differences?

Discovery depth/source families, saved DST-opponent exclusion, raw versus normalized selector, 95% joint floor versus .10 research frontier, and exposure-only v3 versus research captain/thesis/overlap solve. Requested-count caps are intentional and clearly distinguished from realized exposure.

### On identical inputs, what three-lineup portfolio does corrected production select?

**No feasible trio under the unchanged production quality policy.** It returns Watson CPT / Jeudy, Judkins, Szmyt, Metcalf, Warren; and Boston CPT / Jeudy, Concepcion, Watson, Metcalf, Warren. They overlap four. A third distinct supported thesis cannot pass all unchanged requirements. The expanded research policy supports the exact Metcalf / Watson / Jeudy three documented above.

### Does corrected production converge materially toward the expanded research three?

**NO.** Corrected scoring semantics agree; the unchanged quality/selector policy still yields only two rather than the research three. Universe expansion alone does not solve that policy difference.

### Is the current production Showdown optimizer safe to use for tonight?

**USE RESEARCH SHADOW**, after final-lock player/identity/market/weather reconciliation. The original running implementation has confirmed comparison/reliability bugs; corrected production still does not furnish the requested compliant trio.

### What exact production change should be promoted next?

Promote the tested Showdown-only baseline-rescore/common-floor fix, explicit slot-promotion ownership gate, truthful conditional 5–1 labels, and denominator/underfill diagnostics. Restart the backend only after this reviewed code is accepted for use. Keep the current .95 floor, selector weights, priors and exposure policy unchanged. Evaluate adopting expanded discovery and the research three-entry portfolio policy in a separate frozen shadow; neither is automatically promoted by this audit.
