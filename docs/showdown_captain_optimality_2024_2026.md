# Historical Showdown Captain Optimality

**45 unique legal actual-score games**; 1 duplicate removed, 1 tied-optimum game preserved.

Games by season: 2024: 22, 2025: 18, 2026: 5.
DraftKings salary coverage: 2024, 2025, 2026; no earlier salary slates are stored.
Player actual-score source rows: curated_weekly_stats 23, raw_nfl_schedule 90, raw_nfl_weekly_stat 1050, unavailable 1255.
Oracle scoring assigns zero to salary rows absent from both matched actual-stat sources; this may mean inactivity or a source gap, so those zeros are not independently verified. The two-team usage completion gate excludes wholly unplayed games.
Excluded: 2026 W3 MONDAY_NIGHT: final_actual_usage_incomplete.

Position shares use one deterministic optimum per game. The QB opportunity tables include backups unless labeled starter-only.

## Overall positions

| Position | Optimal Captains | Games | Game share | Game-share 95% interval | Eligible opportunities | Opportunity rate | Reliability |
|---|---:|---:|---:|---:|---:|---:|---|
| QB | 11 | 45 | 24.4% | 14.2%–38.7% | 303 | 3.6% | moderate |
| RB | 8 | 45 | 17.8% | 9.3%–31.3% | 534 | 1.5% | limited |
| WR | 19 | 45 | 42.2% | 29.0%–56.7% | 880 | 2.2% | moderate |
| TE | 6 | 45 | 13.3% | 6.3%–26.2% | 498 | 1.2% | limited |
| DST | 1 | 45 | 2.2% | 0.4%–11.6% | 90 | 1.1% | limited |
| K | 0 | 45 | 0.0% | 0.0%–7.9% | 113 | 0.0% | limited |

## Starter identification

76/90 team-QB opportunities identified before kickoff; 32/45 games have both starters identified. Methods: {'salary_and_prior_pass_volume_inferred': 70, 'pregame_inferred': 6}. 14 team opportunities remain ambiguous.

Use pre-kickoff identity evidence when present; otherwise require a $1,200 FLEX salary lead, at least 20 prior-three pass attempts, and no backup exceeding that prior volume by more than eight. Actual game usage is audit-only.

Postgame pass-leader mismatches, audit only: 2. Actual usage never selects the starter label.

Recent-carry tercile boundaries: 1.67 and 3.33. These describe volume; goal-line role is unverified.

## All eligible QB archetypes

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| Pocket-oriented | 0 | 109 | 0.0% | 0.0%–3.4% | limited |
| Mobile | 5 | 58 | 8.6% | 3.7%–18.6% | limited |
| High-rush / goal-line unverified | 6 | 79 | 7.6% | 3.5%–15.6% | limited |
| Unknown rushing role | 0 | 57 | 0.0% | 0.0%–6.3% | limited |

## Pregame-identified starter QB archetypes

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| Pocket-oriented | 0 | 18 | 0.0% | 0.0%–17.6% | limited |
| Mobile | 3 | 17 | 17.6% | 6.2%–41.0% | limited |
| High-rush / goal-line unverified | 6 | 41 | 14.6% | 6.9%–28.4% | limited |
| Unknown rushing role | 0 | 0 | Unavailable | Unavailable | limited |

## Starter QB game shares

| Group | Optimal-CPT games | Games with group | Game share | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| Either identified starting QB | 8 | 32 | 25.0% | 13.3%–42.1% | limited |
| Favorite starting QB | 7 | 32 | 21.9% | 11.0%–38.8% | limited |
| Underdog/tied starting QB | 1 | 32 | 3.1% | 0.6%–15.7% | limited |
| Pocket-oriented starting QB | 0 | 15 | 0.0% | 0.0%–20.4% | limited |
| Mobile starting QB | 3 | 14 | 21.4% | 7.6%–47.6% | limited |
| High-rush / goal-line unverified starting QB | 5 | 27 | 18.5% | 8.2%–36.7% | limited |
| Unknown rushing role starting QB | 0 | 0 | Unavailable | Unavailable | limited |

## All QB: Rushing-volume buckets

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| 0–2 | 0 | 109 | 0.0% | 0.0%–3.4% | limited |
| 2–4 | 6 | 68 | 8.8% | 4.1%–17.9% | limited |
| 4–6 | 2 | 43 | 4.7% | 1.3%–15.5% | limited |
| 6–8 | 1 | 14 | 7.1% | 1.3%–31.5% | limited |
| 8+ | 2 | 12 | 16.7% | 4.7%–44.8% | limited |
| Unavailable | 0 | 57 | 0.0% | 0.0%–6.3% | limited |

## Starter QB: Rushing-volume buckets

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| 0–2 | 0 | 18 | 0.0% | 0.0%–17.6% | limited |
| 2–4 | 4 | 22 | 18.2% | 7.3%–38.5% | limited |
| 4–6 | 2 | 20 | 10.0% | 2.8%–30.1% | limited |
| 6–8 | 1 | 10 | 10.0% | 1.8%–40.4% | limited |
| 8+ | 2 | 6 | 33.3% | 9.7%–70.0% | limited |
| Unavailable | 0 | 0 | Unavailable | Unavailable | limited |

## All QB: Prior rushing-TD buckets

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| 0 prior-three rush TD/game | 8 | 182 | 4.4% | 2.2%–8.4% | limited |
| >0 to 0.33 prior-three rush TD/game | 2 | 41 | 4.9% | 1.3%–16.1% | limited |
| >0.33 prior-three rush TD/game | 1 | 15 | 6.7% | 1.2%–29.8% | limited |
| Unavailable | 0 | 65 | 0.0% | 0.0%–5.6% | limited |

## Starter QB: Prior rushing-TD buckets

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| 0 prior-three rush TD/game | 6 | 51 | 11.8% | 5.5%–23.4% | limited |
| >0 to 0.33 prior-three rush TD/game | 2 | 18 | 11.1% | 3.1%–32.8% | limited |
| >0.33 prior-three rush TD/game | 1 | 7 | 14.3% | 2.6%–51.3% | limited |
| Unavailable | 0 | 0 | Unavailable | Unavailable | limited |

## All QB: Favorite versus underdog

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| Favorite | 9 | 150 | 6.0% | 3.2%–11.0% | limited |
| Underdog/tied | 2 | 153 | 1.3% | 0.4%–4.6% | limited |

## Starter QB: Favorite versus underdog

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| Favorite | 8 | 41 | 19.5% | 10.2%–34.0% | limited |
| Underdog/tied | 1 | 35 | 2.9% | 0.5%–14.5% | limited |

## All QB: Team implied total

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| Q1: -inf to 21 | 0 | 72 | 0.0% | 0.0%–5.1% | limited |
| Q2: 21 to 23.25 | 2 | 73 | 2.7% | 0.8%–9.5% | limited |
| Q3: 23.25 to 25.75 | 5 | 80 | 6.2% | 2.7%–13.8% | limited |
| Q4: 25.75 to inf | 4 | 78 | 5.1% | 2.0%–12.5% | limited |

## Starter QB: Team implied total

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| Q1: -inf to 21 | 0 | 15 | 0.0% | 0.0%–20.4% | limited |
| Q2: 21 to 23.25 | 1 | 16 | 6.2% | 1.1%–28.3% | limited |
| Q3: 23.25 to 25.75 | 4 | 21 | 19.0% | 7.7%–40.0% | limited |
| Q4: 25.75 to inf | 4 | 24 | 16.7% | 6.7%–35.9% | limited |

## All QB: QB salary

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| Q1: -inf to 6000 | 0 | 0 | Unavailable | Unavailable | limited |
| Q2: 6000 to 6000 | 0 | 0 | Unavailable | Unavailable | limited |
| Q3: 6000 to 9300 | 1 | 227 | 0.4% | 0.1%–2.5% | limited |
| Q4: 9300 to inf | 10 | 76 | 13.2% | 7.3%–22.6% | limited |

## Starter QB: QB salary

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| Q1: -inf to 6000 | 0 | 0 | Unavailable | Unavailable | limited |
| Q2: 6000 to 6000 | 0 | 0 | Unavailable | Unavailable | limited |
| Q3: 6000 to 9300 | 0 | 12 | 0.0% | 0.0%–24.3% | limited |
| Q4: 9300 to inf | 9 | 64 | 14.1% | 7.6%–24.6% | limited |

## All QB: QB projected mean

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| Q1: -inf to 5.32388 | 0 | 76 | 0.0% | 0.0%–4.8% | limited |
| Q2: 5.32388 to 8.69923 | 0 | 75 | 0.0% | 0.0%–4.9% | limited |
| Q3: 8.69923 to 17.9516 | 1 | 76 | 1.3% | 0.2%–7.1% | limited |
| Q4: 17.9516 to inf | 10 | 76 | 13.2% | 7.3%–22.6% | limited |

## Starter QB: QB projected mean

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| Q1: -inf to 5.32388 | 0 | 0 | Unavailable | Unavailable | limited |
| Q2: 5.32388 to 8.69923 | 0 | 0 | Unavailable | Unavailable | limited |
| Q3: 8.69923 to 17.9516 | 0 | 17 | 0.0% | 0.0%–18.4% | limited |
| Q4: 17.9516 to inf | 9 | 59 | 15.3% | 8.2%–26.5% | limited |

## All QB: Prior rushing yards

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| Q1: -inf to 0.75 | 0 | 60 | 0.0% | 0.0%–6.0% | limited |
| Q2: 0.75 to 6 | 1 | 57 | 1.8% | 0.3%–9.3% | limited |
| Q3: 6 to 18.1667 | 3 | 61 | 4.9% | 1.7%–13.5% | limited |
| Q4: 18.1667 to inf | 7 | 60 | 11.7% | 5.8%–22.2% | limited |

## Starter QB: Prior rushing yards

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| Q1: -inf to 0.75 | 0 | 7 | 0.0% | 0.0%–35.4% | limited |
| Q2: 0.75 to 6 | 1 | 12 | 8.3% | 1.5%–35.4% | limited |
| Q3: 6 to 18.1667 | 1 | 20 | 5.0% | 0.9%–23.6% | limited |
| Q4: 18.1667 to inf | 7 | 37 | 18.9% | 9.5%–34.2% | limited |

## All QB: Prior pass volume

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| Q1: -inf to 7.75 | 0 | 62 | 0.0% | 0.0%–5.8% | limited |
| Q2: 7.75 to 23 | 0 | 59 | 0.0% | 0.0%–6.1% | limited |
| Q3: 23 to 30.3333 | 5 | 59 | 8.5% | 3.7%–18.4% | limited |
| Q4: 30.3333 to inf | 6 | 66 | 9.1% | 4.2%–18.4% | limited |

## Starter QB: Prior pass volume

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| Q1: -inf to 7.75 | 0 | 0 | Unavailable | Unavailable | limited |
| Q2: 7.75 to 23 | 0 | 1 | 0.0% | 0.0%–79.3% | limited |
| Q3: 23 to 30.3333 | 4 | 28 | 14.3% | 5.7%–31.5% | limited |
| Q4: 30.3333 to inf | 5 | 47 | 10.6% | 4.6%–22.6% | limited |

## All QB: Teammate target concentration

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| Q1: -inf to 0.209091 | 3 | 74 | 4.1% | 1.4%–11.3% | limited |
| Q2: 0.209091 to 0.231343 | 0 | 76 | 0.0% | 0.0%–4.8% | limited |
| Q3: 0.231343 to 0.267241 | 5 | 70 | 7.1% | 3.1%–15.7% | limited |
| Q4: 0.267241 to inf | 3 | 83 | 3.6% | 1.2%–10.1% | limited |

## Starter QB: Teammate target concentration

| Group | Optimal CPT | Sample | Rate | 95% Wilson interval | Reliability |
|---|---:|---:|---:|---:|---|
| Q1: -inf to 0.209091 | 2 | 17 | 11.8% | 3.3%–34.3% | limited |
| Q2: 0.209091 to 0.231343 | 0 | 18 | 0.0% | 0.0%–17.6% | limited |
| Q3: 0.231343 to 0.267241 | 5 | 19 | 26.3% | 11.8%–48.8% | limited |
| Q4: 0.267241 to inf | 2 | 22 | 9.1% | 2.5%–27.8% | limited |

## Goal-line evidence

No historical pregame red-zone/inside-5/design-run play-by-play features in the source snapshot

Prior-three-game rushing yards/TDs and passing TDs are observed pregame proxies, not model projections. Goal-line/design/scramble roles remain unavailable.

## Chronological validation: All QB

exploratory_insufficient_training_events; train 149 (3 optimal), holdout 154 (8 optimal).

| Model | Holdout AUC | Brier | Log loss | Calibration error |
|---|---:|---:|---:|---:|
| A base | 0.919 | 0.0446 | 0.1580 | 0.0294 |
| B + carries | 0.915 | 0.0444 | 0.1577 | 0.0292 |
| C + prior TD proxy | 0.830 | 0.0464 | 0.1818 | 0.0342 |
| D + archetype | 0.923 | 0.0455 | 0.1585 | 0.0326 |
| E full supported | 0.795 | 0.0472 | 0.1996 | 0.0367 |

Calibration bins and standardized coefficients are in the JSON artifact. These sparse estimates do not authorize a production prior.

## Chronological validation: Starter QB

exploratory_insufficient_training_events; train 34 (2 optimal), holdout 42 (7 optimal).

| Model | Holdout AUC | Brier | Log loss | Calibration error |
|---|---:|---:|---:|---:|
| A base | 0.718 | 0.1436 | 0.4786 | 0.1018 |
| B + carries | 0.694 | 0.1416 | 0.4738 | 0.1006 |
| C + prior TD proxy | 0.649 | 0.1506 | 0.5664 | 0.1213 |
| D + archetype | 0.657 | 0.1422 | 0.4767 | 0.0961 |
| E full supported | 0.653 | 0.1476 | 0.6074 | 0.1258 |

Calibration bins and standardized coefficients are in the JSON artifact. These sparse estimates do not authorize a production prior.

## Missing data and status

Unavailable: model projected rushing yards, model rushing TD expectation, red-zone carries, inside-10 carries, inside-5 carries, goal-line carry share, passing TD expectation, designed-run rate, scramble rate.
- **model projected rushing yards:** No archived prelock rushing-yard component from the fitted projection model; prior-three observed yards are shown separately
- **model rushing TD expectation:** No archived prelock rushing-TD component; prior-three observed TD rate is shown separately
- **passing TD expectation:** No archived prelock passing-TD component; prior-three observed TD rate is shown separately
- **red-zone carries:** No historical play-by-play location data in the local database
- **inside-10 carries:** No historical play-by-play location data in the local database
- **inside-5 carries:** No historical play-by-play location data in the local database
- **goal-line carry share:** No historical play-by-play location data in the local database
- **designed-run rate:** Weekly box scores do not distinguish designed runs from scrambles
- **scramble rate:** Weekly box scores do not distinguish scrambles from designed runs
Actual historical field CPT ownership, tournament-winning Captains, and top-1% distributions are unavailable.
The QB archetype prior remains **shadow-only**; live rankings and eligibility are unchanged.
