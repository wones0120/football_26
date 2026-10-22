# Scenario-first Captain: market primary, conditional v6

Choose **Scenario-first Captain · market primary · 3–3 · conditional v6** under **Optimizer comparison**, request one lineup, then use **Prepare slate for optimization → Run Optimizer → Reopen results**. Existing points/count/yard/default optimizers and saved v1/v2/v3/v4/v5 results remain comparisons. Download tests are not part of routine lineup validation.

The direction is market outlook → shared scoring cases → team opportunities → player production → complete-roster selection. Version 2 corrected v1's protected quarterback yards, fixed integer backup work and worst-case selection objective. Version 3 makes the market-implied primary environment govern selection. It remains a conditional comparison with **unknown case likelihood**, not calibrated tournament probability or a full possession/clock model.

## Roles and injury ordering

The visible **Exclude low-involvement backups** preference defaults on for this opt-in mode. Approved initial cutoffs are:

- RB backups: at least **6 projected carries + targets**.
- WR/TE backups: at least **3 projected targets**.

These are user eligibility preferences, not trained weights or changes to projections. The entire model assessment—including excluded players' scoring cases—remains saved. Source-factual nonparticipation stays separate from preference exclusions. Captain and FLEX both obey the preference; locks cannot bypass it.

Prepare must apply supported availability/role adjustments **before** these cutoffs use the learned counts. Injuries do not automatically justify a recipient's expanded workload. Sourced role promotions change the current role assessment; supported upstream conditional workload allocations change counts before the preference. Missing recipient/vacancy evidence remains explicit rather than redistributing all missing targets or waiving a cutoff. Authored allocation assumptions are not measured replacement shares. Excluding a player as a user preference never donates that player's work.

## Market-implied primary scenario

Prepare requires a current exact-game market quote. Home implied points are `(total - home_spread) / 2`; away implied points are `(total + home_spread) / 2`. No user choice of weekly game category is required and missing market evidence has no neutral fallback. Positive/negative home spread direction is tested. The numerical targets move continuously with the market; no hard high/low-total cutoff or invented probability is added.

Only the four **central** cases enter primary eligibility utility, legal full-roster benchmarks, coverage, mean-relative-capture tie-breaks and Captain/reference comparisons. They vary sourced TD/FG composition and role/efficiency allocation while staying within three actual scoring points of each team's market-implied target. That support band is a declared discrete-score modeling tolerance, not a confidence interval. Twenty cases are still retained, but the other sixteen scripts are separate diagnostic scores without additional benchmark solves, selection weight or tie-break influence. A regression changes their scores to extreme values and confirms the primary roster/objective/benchmarks remain identical.

The market gives an expected scoring environment, not proof of a modal exact score or which players score touchdowns. Four conditional cases do not establish a win probability. The existing explicit 3–3 construction and Captain restrictions remain separate user policies; this change does not claim every close game has a 3–3 winning roster or implement other team-split families. The saved review displays the actual market, implied scores, primary denominator and excluded alternatives.

## Shared cases and artificial floors

The current total/spread anchor central, lower-total, higher-total, home-ahead and away-ahead coordinates. Four source-based sensitivity strata at each coordinate give twenty seeded cases. Actual same-team prior TD/FG combinations **within one field goal** of each target supply composition; low-scoring all-FG games are not scaled upward. TD-heavy/zero-FG combinations participate when the source supports them.

Within the current season, at least three complete prior team-games in which the current sourced quarterback attempted passes support joint role/passing sensitivity. Low, middle and high historical passing-efficiency strata plus a sourced backup-zero-work stress stratum vary volumes, role shares, completions and yards per completion. These strata are not fitted frequencies. QB participation in a donor is not proof of its opening starter, identical injury context or unchanged current roles. Missing player rows/measurements retain an explicitly uncertain anchor; they never become observed zeros. Missing a sufficient current-QB reference blocks this version rather than inventing a population profile.

Known player opportunities follow sourced joint-profile shares within the shared integer team budget. Targets and carries use deterministic largest-remainder rounding: each actor receives the floor or ceiling of its conditional expected count. Historical joint profiles supply workload variation; no second, uncalibrated multinomial opportunity draw is added. This is a conditional sensitivity method, not a calibrated distribution. Role-supported expansion remains possible without a player-specific target/carry ceiling. Per-team/channel audits retain base anchors, profile factors, conditional expectations and protected unknown counts. An observed zero-work role can receive zero carries and targets; a fractional target estimate does not round to one in every case. The baseline unknown share remains protected. Passing yards arise from **actual sampled receiver completions and sourced yards per completion**, including an explicit unknown receiver. The producer does not normalize receivers back up to an attempts-times-YPA quarterback yard floor. Passing/receiving yards and TDs are credits on shared physical events. Captain changes fantasy scoring/salary only.

Latest learned count anchors, model publications and original yard comparisons remain intact. Conditional case averages are not new calibrated expected forecasts. Current source IDs/import clocks, current-QB donor periods, missing observations, seed and producer/helper code hashes freeze in Prepare. A v1/v2/v3/v4/v5 receipt cannot substitute for a v6 run.

## Passer reconciliation

Version 4 fixes a semantic accounting error: the independent learned team/player forecast difference is **not** evidence of an unknown backup. Original forecasts remain visible and unchanged. Team learned attempts still anchor scenario volume, with the existing market/source volume variation. Passing ownership follows the full-source donor game's observed passer shares, conditioned on the current sourced starting QB. The independent QB count head is retained for comparison; it no longer silently sets a phantom-passer share in these conditional cases.

A single-passer donor credits that passer with every case attempt, completion yard and passing touchdown, including throws to unknown receivers. A multi-passer donor preserves every observed relief/trick-play share. Exact native/canonical identities and raw source IDs are retained; integer allocation conserves the full team attempt budget. Unsupported or unlinked passers keep their share in the audited unmodeled bucket rather than donating it to an eligible starter. User exclusions do not enter this producer. Historical relief participation is a conditional example, not a calibrated current-week exit probability.

The receipt stores current starter proof, original team/player forecasts and their difference, full-source donor passers, and issued per-passer attempts. The saved UI exposes this distinction and a selected QB's actual primary-case attempt range alongside the raw learned anchor. Unknown receiving and rushing shares remain protected; this fix does not fabricate missing recipients, retrain the raw heads, impose quarterback inclusion or change baseline objectives.

## Calibration status after the bounded October22 diagnostic

V6 remains the active opt-in case version. A research-only FG-frequency classifier and TD-concentration alternative failed their frozen validation criteria; no new case weights, forecasts or selector were activated and no operational rerun occurred.57 team-game input sets across29 games have verified predecision source availability for a reconstructed2026 evaluation; older archived quote chronology is unknown. All outcomes remain retrospective evidence. Conditional TD checks use realized exposures and exactly two team TDs; they are not named-player or pregame likelihoods. Marginal FG rates cannot weight combined stress cases without a validated joint sampling/mass contract. [Numeric findings, source exclusions and receiver alternatives](../../artifacts/scenario_scoring_calibration_20261022/RESULTS.md).

## Joint kicking provenance

Version6 keeps each same-team scoring donor’s made field goals, made-distance bins and missed FG attempts together. Made bins must reconcile to makes; attempts must cover makes; missing/inconsistent evidence has no marginal-distance fallback. Current expected-starter proof remains separate from the historical donor kicker. Multiple donor kickers retain their canonical/native identities and source IDs. Unsupported current kickers retain FG/PAT event points in the explicit unknown actor alongside unknown offense work.

Distance scoring uses3points below40yards,4at40–49and5at50+, including60+. Independent resampling from the current kicker’s marginal made-distance mix no longer changes the donor outcome. Legacy distance weights remain in current-kicker evidence as a comparison; case scoring consumes the donor’s bins. The case ledger records attempts, makes, misses, bins and FG points; the saved review exposes all four primary cases. These are conditional source outcomes, not a learned current-kicker distance/make distribution or an estimate of how frequently four-FG games occur. All case TDs still receive a successful PAT; observed donor PAT outcomes, two-point decisions and full possession/clock mechanics are outside this slice.

No high-FG outcome is removed solely for being unusual. Source-period/kicker/context differences and uncalibrated composition frequencies remain explicit. This repair does not promote or retrain the original points-head kicker model, change Captain/team/QB preferences, or add kicker penalties.

## Selection and complete Captain comparisons

The explicit3–3 policy remains a user construction policy, not a learned claim that all close games have3–3 winners. Current salary, Captain-position/exceptions, QB, lock/exclusion and exposure rules remain binding. Points-leader preferences are inactive only in the comparison request; their stored controls remain unchanged. Static strategy QB-stack rules are replaced by shared-event evaluation. No incumbent points, individual P90 or ownership gate selects this mode.

**Competitive case target (%)** defaults to90. Within the market-implied primary environment, the selector counts complete-roster cases reaching90% of that case's proven best legal score. More covered cases take priority; mean relative capture breaks ties. The exact objective is `(N+1) × covered_cases + sum(case_score / best_legal_case_score)` for N primary cases. Every legal ratio is at most1, so one additional covered case dominates every possible secondary-score change. This is an explicit decision policy, not a learned win threshold, payoff estimate or set of case probabilities. **Worst relative capture is diagnostic only.** Individual case means are display-only; whole-roster relative means are the stated secondary criterion.

The same frozen implicit legal roster space supplies the selected roster and a fully reoptimized different-Captain alternative. The declared treatment excludes only the selected Captain in the alternative. Reported six-player rosters, salaries, Captain premium, FLEX spending, coverage and case scores expose the actual salary tradeoff.

Optionally select **six Reference players** and a **Reference Captain**. The exact specified reference is scored without changing it or imposing its players as locks. User-preference/constraint conflicts remain explicit. A further best roster with the reference Captain and five reoptimized FLEX players is retained when eligible; an already-proven matching optimum is reused. A TE reference Captain does not create a Captain exception. A reference outside the current preferences is a descriptive sensitivity, not a controlled eligible-selector comparison.

## Bounds and remaining limits

One requested lineup, twenty cases, four proven-Optimal primary case benchmarks (up to1.5seconds each), one final solve (up to10seconds), and at most two additional Captain comparisons (up to5seconds each), with a65-second selector deadline. Serial CBC and fixed seeds are scoped to this path. Infeasibility is recorded; an unproved feasible incumbent, timeout or missing evidence never becomes a fallback or constraint relaxation. Full public source/preparation work is outside the selector deadline. No portfolio or broader slate activation is implied.

The conditional family still omits missed PATs, turnovers, defensive/return scores and two-point plays and assumes successful PATs. Historical whole-field rates approximate scoring roles; donor/current injury-context compatibility, sparse players, broader role/efficiency coverage and calibration remain limitations. Twenty stress cases do not establish effectiveness, tournament superiority or exhaustive football coverage.

The saved view exposes opportunity preference exclusions, role/yard uncertainty, matched Captain rosters and the offensive reference. Existing v1/v2 reports retain their original policy interpretation. First-v1 evidence remains [preserved](../../artifacts/scenario_first_captain_20261022/RESULTS.md); the current correction is recorded [separately](../../artifacts/scenario_captain_role_correction_20261022/RESULTS.md). No environment variable, migration or dependency changed.

The market-primary operational rerun is recorded [separately](../../artifacts/scenario_market_primary_20261022/RESULTS.md).

The passer repair and public rerun are recorded [separately](../../artifacts/scenario_qb_passing_repair_20261022/RESULTS.md).
