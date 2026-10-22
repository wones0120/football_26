# Monday workload feature — completed public acceptance

All three arms used Prepare `0492fea9-c01a-487f-86f7-d54f69e697c4`, projection `21c3d2b7-601a-4987-8492-3abb7225610b`, cutoff `2026-10-19T16:41:01.318806+00:00`. Count/control share forecast receipt `3bd58cf3c42b3a97879c829ee48fefe39e30f9b23e4f958dd9193e6ab1e1f170`. Standard remains the default.

Actual app Prepare → Optimize → reopen → Check upload readiness passed. All six public CSV responses (recommended/all across three runs) returned200, text/csv, correct CPT/FLEX headers, exact saved native IDs. No browser downloads or contest submissions. All are preliminary upload-ready pending final inactives; each clearance expires30minutes after check. See `FINAL_CSV_VALIDATION.json` and `three_saved_downloads.png`.

## Saved portfolios

### Standard recommendation — `2e3cd407-d843-4b2e-9734-97616427c8bb`

| # | Captain / FLEX | Salary | Original FP mean |
|---|---|---:|---:|
| 1 | Jayden Daniels CPT / Drew Stevens / Brock Purdy / Christian McCaffrey / Treylon Burks / Antonio Williams | $50,000 | 77.004 |
| 2 | Jayden Daniels CPT / Brock Purdy / Chig Okonkwo / Austin Ekeler / Christian McCaffrey / Antonio Williams | $50,000 | 75.582 |
| 3 | Brock Purdy CPT / Drew Stevens / Jordan Watkins / Jayden Daniels / Christian McCaffrey / Antonio Williams | $49,200 | 74.920 |
| 4 | Brock Purdy CPT / Drew Stevens / Jordan Watkins / Jayden Daniels / Chig Okonkwo / Christian McCaffrey | $49,600 | 75.472 |

Captain appearances: {'Jayden Daniels': 2, 'Brock Purdy': 2}. Four requested/four achieved,50%Captain cap, floor1700, maximum4perteam checked. No settings relaxed.

### Offensive workload — `4707b279-e480-4d04-afce-3796332bd07c`

| # | Captain / FLEX | Salary | Original FP mean |
|---|---|---:|---:|
| 1 | Christian McCaffrey CPT / George Kittle / Jayden Daniels / Rachaad White / Treylon Burks / Antonio Williams | $49,900 | 64.302 |
| 2 | Christian McCaffrey CPT / George Kittle / Jayden Daniels / Kaelon Black / Rachaad White / Treylon Burks | $49,500 | 61.081 |
| 3 | Jayden Daniels CPT / Jacob Cowing / Brock Purdy / Rachaad White / Christian McCaffrey / Treylon Burks | $49,600 | 71.430 |
| 4 | Jayden Daniels CPT / Brock Purdy / Rachaad White / Dyami Brown / Christian McCaffrey / Treylon Burks | $50,000 | 72.314 |

Captain appearances: {'Christian McCaffrey': 2, 'Jayden Daniels': 2}. Four requested/four achieved,50%Captain cap, floor1700, maximum4perteam checked. No settings relaxed.

### Matched offensive-domain FP mean — `c968d674-a83e-43d9-9f77-d75fcb069049`

| # | Captain / FLEX | Salary | Original FP mean |
|---|---|---:|---:|
| 1 | Jayden Daniels CPT / Brock Purdy / Rachaad White / Dyami Brown / Christian McCaffrey / Treylon Burks | $50,000 | 72.314 |
| 2 | Brock Purdy CPT / Jayden Daniels / Kaelon Black / Christian McCaffrey / Treylon Burks / Antonio Williams | $49,200 | 71.992 |
| 3 | Brock Purdy CPT / Jacob Cowing / Jayden Daniels / Rachaad White / Christian McCaffrey / Treylon Burks | $50,000 | 71.963 |
| 4 | Jayden Daniels CPT / Brock Purdy / Kaelon Black / Christian McCaffrey / Treylon Burks / Antonio Williams | $48,800 | 71.458 |

Captain appearances: {'Jayden Daniels': 2, 'Brock Purdy': 2}. Four requested/four achieved,50%Captain cap, floor1700, maximum4perteam checked. No settings relaxed.

## Football interpretation

The standard#1 retains both starting QBs and CMC, with Burks/Antonio salary support and Stevens kicking opportunity. It succeeds through productive possessions on both sides, CMC involvement and enough cheap receiving work; three core players share every standard lineup. #2 replaces kicker/Burks with Okonkwo/Ekeler, avoiding Watkins and reducing dependence on field goals, at lower modeled mean. These remain the standard choices, not automatically displaced by count utility.

Count#1 chooses CMC Captain/Kittle/Daniels/White/Burks/Antonio. It favors expected CMC rushing/receiving work, Kittle targets and Daniels pass/rush volume, paying for them by omitting Purdy. The matched FP-control#1 instead buys both QBs, removes Kittle/Antonio for cheaper Dyami, and places Daniels at Captain. The7.717count utility and64.302FP mean are different objectives, not a claim that64.302is a better fantasy expectation than72.314or77.004. Count#2 also uses Black with CMC; both compete for SF carries, and all count lineups share CMC/Daniels/White/Burks. This portfolio is not diversified across all game failure paths and is not a calibrated joint-upside optimizer.

McLaurin is eligible under verified final NO_GAME_DESIGNATION, salary8000, FP10.364, count forecast5.990targets; he is not omitted due nativeQ. Kittle targets6.906and position-normalized utility1.122beat McLaurin utility0.735in this declared objective. These scales are preferences, not scoring-event equivalence. Raw targets/carries retain their own meaning. Salary is a constraint, not a bonus. No injury volume was invented: unavailable actors retain their conditional model assessments and their opportunities are not donated. Ekeler/Okonkwo/Watkins missing count support remains explicit; the FP standard retains their original assessments.

The automatic standard Analyst handoff is a neutral reference scenario, with no authored workload/story mechanism demonstrated. Count/control explicitly do not consume its semantic scenarios. A shared FP/count/authored-Analyst recommendation layer and weighted red-zone/goal-line opportunity extension are queued, not active in these runs.

## Evidence and checks

High approved the count/verified-gap feature and each actual acceptance integration repair.55 adapter/core tests passed plusUIbuild;55 saved-upload tests passed;15 history tests passed; affected diff whitespace clean. The source intake uses officialW3/W4NFLgamebooks, exact historical roster week/current revision, canonical identity and fresh current role, with no DNPzero insertion. Daniels28.556passes/7.389rushes and McLaurin5.990targets are now actual saved producer forecasts. New bridged returner cases do not have a separate predictive-calibration claim. Existing W2–5conditional/revised-data validation is mixed and already inspected; no tournament superiority inferred.

Actual acceptance fixed unused-Analyst-snapshot dependence, new-policy history download recognition, and resolver recomputation-clock false invalidation. All original facts/source/conflict fields and freshness checks remain bound; only top-level resolver evaluated_at is excluded from semantic hash. Cross-run CSV checks passed after all three source recaptures.

Queued next: MondaySingleStat contest196787359. Existing Captainfallback2c10 and firstworkload5c9c are preserved; neither is misrepresented as the matched current control.
