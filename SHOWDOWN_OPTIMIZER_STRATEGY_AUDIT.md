| Rule | Current Setting | Historical Evidence | Prospective Evidence | Recommendation | Confidence |
| --- | --- | --- | --- | --- | --- |
| QB Captain | Allowed; user can ban | 11/45 archive optima have QB CPT; current/no-prior select 10/28 QBs and capture 5/8 optimal QB CPTs | One frozen game; no evidence for blanket ban | KEEP eligibility; validate scoring separately | Medium for eligibility; low for edge |
| QB count | Up to 2 eligible starting QBs; require ≥1 in v3 ≤5-entry path | Four-way controlled structural replay; starter identity reconstructed | Frozen candidate filtering is time-safe, one game | KEEP permissive max 2; do not impose max 1 by theory alone | Low–medium |
| Team count | Requested policy max 4; production default max 5 | Max 3/4/5 compared on 45 games; labels incomplete | Max 4 is a user preference, not DK legality | NEEDS MORE EVIDENCE for max 4; preserve explicit preference | Low for performance |
| Captain-position prior | Strength 0.35; learned/fallback position multiplier on CPT objective | Two old 39-slate sweeps disagree; new 45-game replay cannot establish a winner | No/weaker prior +7.05 actual points in one completed freeze | MODIFY validation/strength policy; no production retuning from one game | High for validation gap; low for best strength |
| Hard QB correlations | ≥2 same-team WR/TE ⇒ QB; WR/TE CPT ⇒ QB; QB CPT needs 2 catchers, or 1 with high rushing | Constraints retained; not causally ablated with complete pregame pools | Current rules can block low-cost replacements | NEEDS MORE EVIDENCE; evaluate separately from rewards | Low |
| Correlation rewards | QB catchers 0.60/0.30/0.10; bring-back 0.45 once; scaled to QB; context/format terms | Each reward family removed independently; no robust confirmed improvement | No-correlation does not change top pick in frozen game | NEEDS MORE EVIDENCE for numeric weights | Low |
| Joint quality screen | ≥95% maximum baseline mean AND ≥95% maximum sum marginal P90 | Eight admissions compared; most top selections unchanged; broad evidence incomplete | 15/438 max-4 candidates survive on completed freeze | MODIFY research admission; retain current control while testing simpler alternatives | High for narrowing; low for outcome benefit |
| Core exposure | 80%, ceil(requested × rate), at least 1 | Isolated 2/5-entry experiments; fill and overlap measured | Can force underfill; denominator is requested count | MODIFY to entry-count-specific policy with visible regret | High for mechanics; low for optimal cap |
| Starting-QB exposure | 100% | Identical to uncapped QB appearances in 2/5 entries | Does not force either specific QB | KEEP as permissive capacity | High for mechanics |
| Captain exposure | 60%, ceil; 2/2 or 3/5 | Separate cap test; current two-entry cap imposes no Captain distinction | Distinct-Captain + overlap pair helps one game | MODIFY policy by entry count; evaluate soft regret-based diversity | High for mechanics; low for benefit |
| Cheap/punt exposure | ≤$1,000 FLEX: 40%, ceil; 1/2 or 2/5 | Independent cap experiments; can remove high-scoring rows and underfill | Austin is required in all 21 fresh joint-screened lineups: current cap prevents two-entry v3 fill | MODIFY hard percentage policy; never fix weak inputs through exposure alone | High for feasibility; low for outcome optimum |
| Cheap-player opportunity gate | RB/WR/TE thresholds; any explicit opportunity/role bypasses; separate current-role and kicker gates upstream | No archived current-role/snap evidence; prior-usage proxy is not current-role validation | Smyth excluded by role fix; Austin old target window remains a risk | MODIFY evidence currency requirement; retain sourced injury/role safety | High for failure mechanism; low for historical lift |
| Scenario candidate generation | Baseline + market-conditioned decisive wins; re-score on common baseline | Controlled coverage proxy plus frozen candidate sources; no established cross-game gain | Conditional forecasts are discovery assumptions, not event probabilities | NEEDS MORE EVIDENCE; retain as bounded research discovery | Low |
| Scenario diversity | Default off; soft opt-in 2% bounded credit per condition; legacy required-label mode available | No complete multi-game causal validation of these coefficients | Duplicate labels cannot add physical entries; forced label coverage can displace stronger rows | REMOVE mandatory label quotas from recommended strategy; NEEDS MORE EVIDENCE for soft credits | High for mechanism; low for benefit |
| Portfolio selector | Maximize entry count, then sum baseline selector (+ optional soft coverage) | No verified contest-EV validation; current point proxy can prioritize wrong lineup | Physical top 1% can still finish below field median | MODIFY objective architecture and validation before scaling entries | High |
| Single-entry selector | Normalized 35% mean / 30% P90 / 20% solver / 10% correlation / 5% context; −3% chalk | Separate heuristic; tested on same frozen candidates only | Solver already contains context/correlation; blend counts them again | NEEDS MORE EVIDENCE; compare against simple mean baseline | High for formula; low for performance |

**Decision: pause reliance on the current Showdown optimizer for paid lineup decisions; keep Showdown as a research capability. The evidence supports changing how the objectives and inputs are validated. It does not support permanently abandoning the format, or claiming that a particular weight change will fix it.**

Audit date: October 5, 2026 (America/New_York). Production code and defaults were not changed. The user’s follow-up prioritizes whether the objectives merit repair or Showdown should be abandoned. Recommendations below are research configurations and decision gates, not a deployment.

The concern is substantive: this optimizer has no demonstrated out-of-sample contest-profit edge. It currently maximizes a ceiling proxy and subjective construction scores. Recent role failures show that a mathematically correct solve can amplify unreliable football inputs. Neither stronger diversification nor more scenarios repairs an inaccurate player distribution.

### What the objectives actually reward

For portfolio v3, let `q_i = marginal player P90_i + player context adjustment_i`. Before portfolio constraints, the production lineup selector is:

```text
S(L) = sum_FLEX(q_i) + 1.5 × CPT_position_multiplier × q_CPT
       − role_ownership_penalty + correlation_and_format_rewards(L)
CPT multiplier = (1 − 0.35) + 0.35 × max(0.05, position_probability × class_count)
```

Ownership is used only with complete finite Captain/FLEX ownership; it is disabled uniformly in the completed frozen comparison. Captain multipliers can strongly change ranking without changing the player mean or P90 forecast. The new structural replay observes QB multipliers from 0.6675 to approximately 2.4000; the prior can suppress or boost QBs depending on the slate. It is not a blanket QB ban.

The portfolio solve prioritizes **number of generated entries before score**. It then maximizes the sum of these lineup selectors under hard caps and physical uniqueness. Repeating one player in different lineups is allowed up to its appearance cap. A physical signature is the Captain identity plus the six canonical identities; swapping FLEX order or relabeling a scenario does not create a new entry.

The single-entry path instead normalizes each candidate mean, P90 sum, solver total, correlation and context by the candidate-set maximum absolute value, applies the weights in the opening table, and subtracts relative chalk. Because the solver already includes context/correlation, the blend gives those inputs another vote. The normalization also makes effective tradeoffs depend on the discovery pool. These are heuristic choices, not fitted profit coefficients.

**Summed marginal P90 is not a calibrated lineup P90.** The sum of individual 90th percentiles generally is not the 90th percentile of their joint sum. These six player outcomes share game conditions; adding small correlation rewards does not turn the proxy into a joint distribution. Neither current selector estimates payout, probability of beating a contest field, duplication-adjusted winnings, or expected profit after fees. Improving raw fantasy score is necessary evidence, but not sufficient evidence of a profitable GPP strategy.

Code references: [optimizer](backend/app/product_services/optimizer.py), [portfolio selection](backend/app/product_services/showdown_portfolio_selection.py), [single-entry blend](backend/app/product_services/showdown_single_entry.py), [correlation library](backend/app/product_services/lineup_correlation_scoring.py), [scenario credits](backend/app/product_services/showdown_scenario_value.py).

### Evidence classes and limits

**TIME-SAFE:** one completed 2026 Week 4 PIT–CLE Thursday slate. The immutable pre-lock input hash matches the saved common scored universe; the saved job and candidate archive precede kickoff. There are 533 physical candidates, including 438 that meet max four/team. Every canonical identity in the full 51-player salary pool has a resolved, consistent DK actual-score observation. Independent exhaustive enumeration finds **105,583,982** DK salary/team-legal Captain/roster assignments and an actual optimum of **120.74** points. This is a selection-only replay: it does not claim that current generation ran historically under every challenger. Historical scoring coefficients are retained for isolated ablations. Current portfolio selector parity is asserted.

**STRUCTURAL REPLAY:** 45 unique games from the 46-slate oracle archive: 22 in 2024, 18 in 2025, five in 2026. One duplicate game is removed. Projections/markets/opportunity fields are reconstructed; archived current role, availability, snap data and receipt-time provenance are incomplete. QB eligibility is inferred by unique highest team QB salary; ambiguous top ties remain ineligible. The stored prior model is applied at its current 0.35 strength, including its own out-of-distribution fallback. That model was trained on overlapping historical seasons, so this replay is not a chronological evaluation of a newly trained prior. Missing role evidence is left unknown, not supplied from today’s depth charts.

Production player-context, Captain-prior and correlation builders supply coefficients. The opportunity gate precedes calculation of the prior, matching production ordering; the explicit starter filter follows it. The initial reconstruction that computed the prior before the gate is preserved under `superseded_prior_before_opportunity_gate` and excluded from all final results. A research-only C++ enumerator evaluates those coefficients under the hard QB rules, salary and team constraints. Exhaustive DK denominators include all archived salary identities, including backups; candidate eligibility excludes inferred nonstarting QBs and applies the reconstructed opportunity gate. Current sourced kicker/role filters cannot be replayed exactly without their historical evidence. Optional `avoid_dst_opponents` is off in structural research; the frozen TIME-SAFE candidates retain their saved legality. This is an objective/construction study, not a claim of exact historical end-to-end production input parity.

**Critical label limitation:** 1,255 player/game records in the deduplicated archive have `actual_source=unavailable` and a stored value of zero. Those can mean inactivity or a source gap. Only **5/45** current top selections have all six actual labels. Confirmed actual scores are null when any label is missing. The “archive” statistics below explicitly use the original zero assumptions; they cannot establish improved subsequent actual performance across many games. The two-team completion test proves a game was played, not that all player scores are resolved. Even paired comparisons with complete selected scores still use reconstructed inputs and an oracle with uncertain zeros.

Retained research rows cover all tested ≥93% admission screens, the exact mean/P90 Pareto frontier and ≥95% selector-regret candidates through exhaustive maxima and endpoint-dominance bounds. Portfolio solves with more than 5,000 qualifying rows retain top ranks plus Captain witnesses and flag truncation; those are finite-pool portfolio comparisons, not full-universe optimality certificates. One-entry winners and maxima are unaffected by that truncation. Scenario discovery uses a stated controlled breadth proxy, not a reconstruction of the complete historical production scheduler.

DraftKings legality is six distinct identities, one Captain and five FLEX, $50,000 salary, both teams represented, and 1.5× Captain salary/scoring. Thus max five/team is legal; max four and max three are preferences. [DraftKings Showdown overview](https://support.draftkings.com/dk/en-us/game-style-showdowns-overview?id=kb_article_view&sysparm_article=KB0010694), [DraftKings salary/roster explanation](https://dknetwork.draftkings.com/2020/06/17/advanced-nfl-dfs-showdown-strategy/).

### TIME-SAFE lineup and portfolio results

Max four/team, QB Captain allowed, at most two QBs. Screen maxima are held common when comparing admissions; team/QB experiments also report their own candidate-pool maxima. Scores below are actual DK points. Percentile is the fraction of **all DK physical lineups with strictly lower actual score**, so higher is better; regret is 120.74 minus actual score.

| Policy | Entries | Mean actual | Best actual | Mean regret | Best regret | Mean shared identities |
| --- | --- | --- | --- | --- | --- | --- |
| Current v3 top 1 | 1/1 | 87.370 | 87.370 | 33.370 | 33.370 | — |
| No Captain prior | 1/1 | 94.420 | 94.420 | 26.320 | 26.320 | — |
| Weaker prior (0.15) | 1/1 | 94.420 | 94.420 | 26.320 | 26.320 | — |
| No correlation reward | 1/1 | 87.370 | 87.370 | 33.370 | 33.370 | — |
| Mean ranker, joint admission | 1/1 | 98.020 | 98.020 | 22.720 | 22.720 | — |
| P90 ranker, joint admission | 1/1 | 94.420 | 94.420 | 26.320 | 26.320 | — |
| Current single-entry blend, same joint pool | 1/1 | 88.980 | 88.980 | 31.760 | 31.760 | — |
| Top two selector lineups | 2/2 | 90.895 | 94.420 | 29.845 | 26.320 | 5.000 |
| Different Captains | 2/2 | 90.895 | 94.420 | 29.845 | 26.320 | 5.000 |
| Different Captains + ≤4 shared | 2/2 | 97.545 | 99.770 | 23.195 | 20.970 | 4.000 |
| Current percentage caps, two entries | 2/2 | 90.895 | 94.420 | 29.845 | 26.320 | 5.000 |
| Soft repeats, two entries | 2/2 | 90.895 | 94.420 | 29.845 | 26.320 | 5.000 |
| No caps, five entries | 5/5 | 92.970 | 99.770 | 27.770 | 20.970 | 4.600 |
| Current caps, five entries | 4/5 | 92.382 | 99.770 | 28.358 | 20.970 | 4.667 |
| Soft repeats, five entries | 5/5 | 92.970 | 99.770 | 27.770 | 20.970 | 4.600 |

The two-entry overlap policy re-optimizes the pair globally; it does not necessarily retain the original #1 lineup. Its gain over top two is **+6.65 mean actual points / +5.35 best actual points** at **7.90649 fewer summed selector points**. Different Captains alone, current two-entry caps and the tested soft-repeat cost do not change that top-two pair. This is one game, not a fitted diversification premium. No selected candidate in the listed current/capped portfolios has the actual-optimal Captain.

Every listed selected lineup is in the physical-universe top 1%, and therefore top 5% and top 10%. This is a weak practical success criterion: the denominator contains millions of legal lineups composed largely of zero-scoring or little-used players.

**Observed contest fields tell a different story.** In contest 196187076 (99,088 loaded entries = reported field size), the current top lineup’s 87.37 points sit at the **39.252nd field percentile**, despite its **99.884th physical percentile**. The no-prior 94.42-point lineup reaches the **67.422nd field percentile**. The stronger diversified entry’s 99.77 points reach the **84.270th field percentile**, still outside that field’s top 10%. The other three complete loaded fields show similar rankings. These hypothetical ranks do not prove those entries were submitted. Payout ladders/fees are not complete here, so this audit cannot report realized profit or ROI.

Across the 438 max-four archived candidates, Spearman correlation with actual score is:

| Forecast/selector | Spearman rank correlation |
| --- | --- |
| mean | 0.401 |
| p90_sum | 0.286 |
| selector | 0.269 |
| selector_no_prior | 0.303 |

The current numeric selector ranks actual outcomes less well than mean on this game. Removing the prior helps ranking modestly; removing correlation does not change the top choice. This supports testing objective simplification, not choosing a new coefficient from a single outcome.

### Joint screen and alternative admissions

| Admission | Retained candidates (TIME-SAFE) | Selected actual | Regret |
| --- | --- | --- | --- |
| joint95 | 15 | 87.370 | 33.370 |
| mean95 | 56 | 87.370 | 33.370 |
| p90_95 | 32 | 87.370 | 33.370 |
| joint94 | 38 | 87.370 | 33.370 |
| joint93 | 61 | 87.370 | 33.370 |
| composite95 | 34 | 87.370 | 33.370 |
| pareto | 3 | 94.420 | 26.320 |
| selector_regret95 | 61 | 87.370 | 33.370 |

The joint 95% screen retains **15/438 = 3.42%** of max-four saved candidates, versus 56 with mean-only and 32 with P90-only. Their top selector choice is identical in this game. Tightening therefore demonstrably narrows the universe; this game supplies no top-lineup benefit from requiring both maxima. Mean and P90 ranks are correlated at approximately 0.693 on this archive; “two near-independent maxima” is a hypothesis, not an established property.

Composite admission means `(mean/max_mean + P90/max_P90)/2 ≥ 0.95`; neither component independently has to reach 95%. Pareto admission retains mean/P90 nondominated rows, including tied identical quality coordinates; it can discard a high-selector roster. Selector-regret admission means ≥95% of the best selector, not a calibrated quality guarantee. Quality thresholds are policy choices. Summed marginal P90 remains a proxy in every alternative.

### STRUCTURAL REPLAY: objective, rule and admission comparisons

Positive delta means the alternative has a higher zero-imputed archive score than current max-four, allowed-QB-CPT/max-two-QB, joint-95 top selection. All 45 games are paired by game; wins/losses ignore exact ties. The confirmed subset column uses only pairs where both selected lineups have six sourced actual labels. It is too small and selected to establish a better production policy.

| Experiment | Archive Δ score | Wins / losses / 45 | Fully scored pairs | Δ on fully scored subset |
| --- | --- | --- | --- | --- |
| objective_no_prior | 1.706 | 19 / 9 / 45 | 4 | -4.607 |
| objective_weak_prior | 0.266 | 2 / 0 / 45 | 5 | 0.000 |
| objective_mobile_qb_neutral_prior | 0.000 | 0 / 0 / 45 | 5 | 0.000 |
| objective_no_correlation | 0.493 | 6 / 3 / 45 | 5 | -1.050 |
| objective_no_first_catcher | 0.322 | 1 / 0 / 45 | 5 | 0.000 |
| objective_no_additional_catchers | -0.131 | 1 / 1 / 45 | 5 | 0.000 |
| objective_no_bringback | 0.322 | 1 / 0 / 45 | 5 | 0.000 |
| objective_no_concentration | 0.000 | 0 / 0 / 45 | 5 | 0.000 |
| objective_no_script_format | 0.305 | 4 / 3 / 45 | 5 | -1.230 |
| mean_ranker_joint | -0.942 | 17 / 19 / 45 | 4 | -10.020 |
| p90_ranker_joint | 0.350 | 16 / 13 / 45 | 5 | -4.516 |
| screen_mean95_n1 | 0.000 | 0 / 0 / 45 | 5 | 0.000 |
| screen_p90_95_n1 | -1.828 | 1 / 6 / 45 | 3 | 0.000 |
| screen_joint94_n1 | -1.806 | 1 / 5 / 45 | 3 | 0.000 |
| screen_joint93_n1 | -1.828 | 1 / 6 / 45 | 3 | 0.000 |
| screen_composite95_n1 | -1.828 | 1 / 6 / 45 | 3 | 0.000 |
| screen_pareto_n1 | -1.836 | 11 / 15 / 45 | 5 | -2.896 |
| screen_selector_regret95_n1 | -1.828 | 1 / 6 / 45 | 3 | 0.000 |
| team5_qbpolicy0 | -0.876 | 1 / 6 / 45 | 5 | 0.000 |
| team3_qbpolicy0 | -2.848 | 8 / 17 / 45 | 2 | -16.575 |
| team4_qbpolicy1 | 2.320 | 22 / 15 / 45 | 4 | -1.075 |
| team4_qbpolicy2 | 0.169 | 5 / 7 / 45 | 5 | 0.000 |
| team4_qbpolicy3 | 1.543 | 21 / 18 / 45 | 4 | -1.075 |
| gate_removed_fixed_benchmark | 0.322 | 1 / 0 / 45 | 5 | 0.000 |
| gate_prior_usage_proxy | -0.980 | 0 / 4 / 45 | 5 | 0.000 |

The no-prior archive delta is **+1.706** points across 45 games, but only 4 paired selections have complete scores; their delta is **-4.607**. Neither the uncertain-zero aggregate nor this small selected subset can be promoted as validated historical improvement. Equal game weighting prevents large-field contests or duplicate salary slates from creating artificial sample size.

### Captain prior and QB suppression

Current prior selects QB Captain in **10/45** games; no prior selects QB Captain in **28/45**. Their archive actual-optimal QB Captain capture counts are **5** and **8**, respectively. Total Captain correctness is **13/45** for current versus **10/45** without the prior. The prior changes QB opportunity, but incomplete inputs and labels prevent a causal claim that it overly suppresses good QB-Captain lineups. Scoring regret and Captain correctness answer different questions; correct Captain is not enough to make the other five identities optimal.

A neutral-prior challenger for high-rushing QBs is reported in the experiment table. It is an unfitted sensitivity test, not a supported learned QB-archetype adjustment. The descriptive 45-game archive has 11 QB optima and limited starter/archetype samples; it cannot justify a numeric adjustment for a pocket/mobile/goal-line class. Full current-role confirmation is missing.

Prior evidence is unstable: the [2,000-candidate 39-slate sweep](docs/showdown_captain_strength_sweep_2024_2025.md) favors 0.15 (+4.384 mean gap improvement; 53.8% wins), while the [2,500-candidate sweep](docs/showdown_captain_strength_sweep_2024_2025_2500.md) favors 0.35 (+6.741; 61.5% wins). These use a different learned lineup experiment and changing stochastic candidate pools; they are not an ablation of today’s full production selector with fixed candidates. Their training/availability provenance does not certify the current pipeline. A `production_validated` description in code is not stronger evidence than the study itself.

### Portfolio exposure and diversification

Effective appearances use `max(1, ceil(requested × rate))`, not a strict realized percentage ceiling:

| Class | Rate | 1 entry | 2 entries | 5 entries |
| --- | --- | --- | --- | --- |
| Starting QB | 100% | 1 | 2 | 5 |
| Core | 80% | 1 | 2 | 4 |
| Captain | 60% | 1 | 2 | 3 |
| ≤$1,000 punt | 40% | 1 | 1 | 2 |

For two entries, core/QB/Captain percentages do not force diversification. A two-entry 60% Captain cap permits the same Captain twice. A two-entry 40% punt cap permits the player once. An underfilled five-request portfolio can still use a core player in all four actual entries, giving 100% realized exposure while passing the requested-count cap. This is observable arithmetic, not an estimate of benefit.

| Portfolio policy | Archive mean score | Archive best score | Shared identities | Underfilled /45 | Fully scored / selected |
| --- | --- | --- | --- | --- | --- |
| exposure_none_n2 | 84.883 | 88.819 | 4.578 | 0 | 9/90 |
| two_different_captains | 84.853 | 90.311 | 4.644 | 0 | 16/90 |
| two_different_captains_max4shared | 83.891 | 90.186 | 3.932 | 1 | 14/89 |
| exposure_core_n2 | 84.883 | 88.819 | 4.578 | 0 | 10/90 |
| exposure_punt_n2 | 84.248 | 86.886 | 4.026 | 7 | 15/83 |
| exposure_qb_n2 | 84.883 | 88.819 | 4.578 | 0 | 10/90 |
| exposure_captain_n2 | 84.883 | 88.819 | 4.578 | 0 | 10/90 |
| exposure_all_n2 | 84.248 | 86.886 | 4.026 | 7 | 15/83 |
| exposure_soft_n2 | 85.633 | 89.761 | 4.444 | 0 | 11/90 |
| exposure_none_n5 | 84.091 | 93.666 | 4.438 | 1 | 30/222 |
| exposure_core_n5 | 82.951 | 95.040 | 4.129 | 7 | 28/216 |
| exposure_punt_n5 | 84.244 | 93.281 | 4.248 | 13 | 41/198 |
| exposure_qb_n5 | 84.091 | 93.666 | 4.438 | 1 | 30/222 |
| exposure_captain_n5 | 83.612 | 94.763 | 4.504 | 1 | 33/222 |
| exposure_all_n5 | 83.238 | 94.333 | 3.973 | 17 | 44/194 |
| exposure_soft_n5 | 84.311 | 95.333 | 4.256 | 1 | 34/222 |

The hard-cap combination underfills **7/45** two-entry portfolios and **17/45** five-entry portfolios in structural research. For uncapped five-entry selection, one game has fewer than five joint-eligible rows; hard caps add further bottlenecks. Lower overlap is demonstrated; improved realized result diversity is not established by overlap alone. Best-of-five and mean score should both be reported: a cap can improve the best result while hurting the average, and underfilled portfolios do not have the same number of chances.

The soft alternative penalizes repeated appearances by `0.05 × max(0, P90−mean) / (1+same-position mean replacement regret)`, with increasing cost for additional repetitions. This respects forecast uncertainty and replacement cost, allows repeats, and pays no reward for changing labels. The 0.05 coefficient and same-position replacement proxy are **unfitted research assumptions**. Its structural results cannot establish profit, covariance reduction, or protection from a bad projection.

An exposure cap can only protect against a common forecast miss if a useful replacement exists. The audit records cap-only selections and uncapped selections, actual labels, opportunity cost and overlap; incomplete actual labels prevent a trustworthy cross-slate count of “superior actual lineups removed” or “bad projection protected.” Such counts must not be inferred from smaller shared-player counts. Single-game actual examples and the paired structural archive are retained separately in the artifacts.

### Cheap players, Smyth and Kevin Austin

The current skill-player gate excludes RB/WR/TE with no explicit opportunity when either salary ≤$1,000 AND mean <3 AND P90 <10, or salary ≤$2,000 AND mean <2 AND P90 <8. Positive expected snaps/routes/carries/targets/shares, a newly assigned role, or many non-generic role labels bypass it. It is an exclusion of low projected opportunity, not a universal requirement for freshly sourced current usage. Kicker/current-role gates are separate upstream safeguards.

The [cheap-player CSV](artifacts/showdown_strategy_audit/cheap_player_metrics.csv) contains 1235 ≤$2,000 player/game rows with canonical ID, salary, prior targets/carries, projection, cap-selected 1/2/5-entry appearances and subsequent score provenance. Archived current-role and recent-snap columns are explicitly null. A stricter prior-usage proxy was tested separately; it cannot answer whether sourced **current** role improves historical results.

**Smyth, prospective failure example:** the earlier Monday pool treated him as a normal core kicker at mean 10.933/P90 16.577, selected 4/5. The [kicker audit](SHOWDOWN_KICKER_ROLE_AUDIT.md) establishes that this was his own older ability history, not copied Carlson output. Current roster/duties evidence led to exclusion. The later [role audit](CURRENT_SLATE_ROLE_AND_AVAILABILITY_AUDIT.md) confirms the practice-squad/current-duty distinction. Those fixes predate this audit; no historical outcome is rewritten with today’s depth chart.

**Kevin Austin, prospective failure example:** the [final two-entry analysis](ATL_NO_FINAL_TWO_ENTRIES.md) reports $800 salary, mean 5.076/P90 10.502, 4.218 modeled targets using an old receiving window (2025 W17/W18 and 2026 W2), against approximately 9% recent 2026 W1–W3 snaps. All 21 fresh joint-screened lineups include him. Under v3’s two-entry punt appearance cap of one, a full two-entry portfolio would be infeasible; the separately researched final pair allowed repetition and therefore retained common Austin forecast risk. Different Captains do not diversify away that risk. His sourced backup roster role permits eligibility, but does not substantiate that target forecast. No postgame Austin or Smyth result is used here.

Recommendation: use current roster/duty evidence and usage currency to qualify very cheap opportunities; retain uncertainty when a backup has plausible limited involvement. Salary and a high projection alone are not proof of opportunity. Validate any stricter threshold on historical fresh evidence, including cheap players who actually break out, before deploying it. Do not use an exposure exception as evidence that a forecast is correct.

### Correlations and scenarios

The independent ablations remove the first same-team pass-catcher reward, additional pass-catcher rewards (second 0.30 and third 0.10), once-per-QB-team bring-back, team concentration, and remaining script/format rewards. Positive QB-linked rewards scale to the QB projection relative to the strongest QB in the pool (bounded 0.4–1.0). Importantly, the saturated 0.45 bring-back is active when an opposing WR/TE is present; it is not restricted by a calibrated shootout probability. Penalties remain in the partial reward ablations; the all-correlation ablation removes the full adjustment.

Conventional correlation theory does not validate these magnitudes. The original constraints remain in these reward tests, so “no first-catcher reward” does not remove the hard stack requirements. There is insufficient complete multi-slate evidence to say any of these individual weights improves eventual ranking. The independent witness tests confirm scorer implementation, not predictive accuracy.

Current scenarios condition market total/spread and role volume toward a 14+ decisive winner with bounded factors, then restore baseline scoring before common quality admission. Baseline discovery plus scenario discovery is tested as coverage; one lineup per scenario is never imposed in recommendations. The 45-game research proxy takes top 25 baseline selector rows plus each Captain’s best witness, then adds top 25 per conditioned P90 axis. It differs from the production scheduler (multiple axes/Captains/constructions/role scripts), so it is a sensitivity experiment rather than historical end-to-end generation validation.

Controlled STRUCTURAL REPLAY discovery comparison (same capped selector and baseline quality):

| Entries | Archive Δ best score | Improved games /45 | Worse games /45 | Changed fill count /45 |
| --- | --- | --- | --- | --- |
| 1 | 0.000 | 0 | 0 | 0 |
| 2 | 0.229 | 2 | 0 | 3 |
| 5 | 1.594 | 5 | 1 | 13 |

These coverage differences are diagnostic because the retained forecasts and score labels are incomplete. More candidate coverage can improve or worsen the eventual result; it is not itself evidence of better calibrated scenario probabilities.

The completed frozen universe also separates production, research-baseline and all-source archives. Useful rediscoveries can be scored, but all-source improvement cannot be assigned solely to scenarios because Captain/forced-FLEX/construction research also expands the pool. Legacy required-label coverage prioritizes labels above selector; the default does not enable it. Optional soft coverage pays at most 2% of the ordinary median selector per condition after common quality, uplift, novelty and coherent winner construction. Its exact coefficients lack cross-game outcome validation. A scenario label is not evidence of calibrated probability.

### What would justify changing or abandoning the objectives

The audit confirms three different issues: input reliability (current opportunity), selector design (ceiling/prior/bonus proxies), and incomplete validation (few frozen scored slates). It does not isolate one universal cause of the user’s losses. A mode can have legal, correlated lineups and still lack a competitive forecasting edge.

Before promoting a replacement, freeze complete pregame player identities, current roles, forecasts, ownership status, salaries, candidate sets and code version. Resolve full actual labels afterward. Compare fixed candidates for attribution and independently regenerated candidates for discovery. Use distinct games as the statistical unit; report mean/median regret, field top-10/5/1 rates, tie/duplication-aware contest returns where fee/payout records exist, and one-/two-/five-entry results separately. Never count four contests on one game as four independent football forecasts.

A practical next research set is current control versus a simple mean-led ranker, no/weaker Captain prior, and bounded soft diversification. A fixed forward series of roughly 20–30 complete slates can expose persistent failures; it is an initial diagnostic sample, not an automatic profitability certificate. Pre-register the candidates and thresholds and retain losses. Do not search a wide weight grid and label its in-sample winner validated.

Retire the current strategy if it continues to lose to the simple baseline on complete held-out slates after role/label failures are corrected. Abandon paid Showdown play if the best validated forecast/selection combination cannot demonstrate competitiveness against real fields after contest economics, or if maintaining fresh inputs is not worth the effort. A profitable edge remains unproven today. Permanently removing Showdown software is not required to stop relying on it for paid entries.

### Reproducibility and verification

All work is offline and additive. [Per-slate metrics](artifacts/showdown_strategy_audit/slate_metrics.csv), [every selected lineup/experiment](artifacts/showdown_strategy_audit/selected_lineup_metrics.csv), [paired results](artifacts/showdown_strategy_audit/paired_experiments.csv), [aggregate JSON](artifacts/showdown_strategy_audit/aggregate.json), and per-slate prepared inputs, exhaustive histograms and retained physical rows are saved. The TIME-SAFE result contains Captain actual-optimal flags, verified physical percentiles, team splits, QB counts, Captain positions, actual scores, mean/median regret and overlap. The structural files keep sourced actual scores separate from zero-imputed diagnostics.

```sh
c++ -O3 -std=c++17 scripts/showdown_strategy_audit_enumerator.cpp -o artifacts/showdown_strategy_audit/enumerator
PYTHONPATH=. .venv/bin/python scripts/audit_showdown_strategy.py
PYTHONPATH=. .venv/bin/python scripts/audit_showdown_archived_candidates.py
PYTHONPATH=. .venv/bin/python scripts/render_showdown_strategy_audit.py
PYTHONPATH=. .venv/bin/pytest scripts/test_showdown_strategy_audit.py -q
```

Verification: two research tests pass. A small physical universe is compared exhaustively against an independent Python enumeration, including the exact score histogram; five distinct frozen historical roster witnesses match production MILP objective values within 1e-5. All 45 archive optima match independent enumeration within 0.021 points. The TIME-SAFE portfolio signatures match the actual production selector at five requested entries. A fixed seed is retained. Source/code SHA-256 manifests pin the audit; no new dependency is introduced. Tests do not establish forecasting or profit accuracy.

**Unresolved requested evidence:** fully time-safe multi-slate current-strategy reconstruction, exact archived current-role/snap gate ablation, calibrated QB-archetype prior, exact historical production scenario-generation ablation, causal bad-projection protection frequency, and fee/payout-based profitability are unavailable from the retained sources. They are marked insufficiently validated, not silently replaced with the structural diagnostics.

### Recommended configurations

**These are provisional research settings. The operational recommendation is to pause reliance on paid Showdown outputs until validation closes the gaps; no production setting is changed.**

| Setting | One-entry Showdown | Two-entry Showdown | Five-entry Showdown |
| --- | --- | --- | --- |
| Eligibility | Fresh canonical roster/duty/usage evidence; allow QB CPT; max 2 starting QBs | Same | Same |
| Team count | Keep max 4 if explicitly requested; compare legal max 5; do not force max 3 | Same | Same |
| Objective control | Retain current v3 and single-entry blend as controls | Retain top two current selector rows as control | Retain current v3 capped control |
| Objective challenger | Simple mean-led score; explicitly labeled uncertainty/ceiling diagnostic | Sum mean-led scores plus bounded uncertainty/replacement-regret repeat cost | Same, with best-result and average-result objectives reported separately |
| Captain prior | No prior and 0.15 challengers; retain 0.35 only as control | Same | Same |
| Correlation | Current weights as control; independent removals; do not fit weights on one recent game | Same | Same |
| Admission | 95% mean-only challenger versus joint-95 control; Pareto/composite/regret diagnostics | Same fixed benchmarks; explain cost of each replacement | Same; explicitly report infeasibility rather than chasing entry fill |
| Exposure | No cross-entry caps or diversity reward | Use whole-entry rules; allow core/QB repeats; compare different CPT + ≤4 shared with soft regret-based choice; no automatic punt veto solely from 40% | Compare current 4-core/5-QB/3-CPT/2-punt capacities with soft repeats; retain no unsupported hard-cap percentage as an established optimum |
| Scenarios | Optional discovery only; common baseline scoring | Optional discovery; no quotas | Optional discovery; no quotas; soft coverage is experimental |
| When to use for paid decisions | Only after complete prospective validation demonstrates competitiveness | Additionally demonstrate useful diversification without excessive regret | Additionally demonstrate five-entry benefit and trustworthy forecast/role coverage; otherwise do not scale |
