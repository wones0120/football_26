# Week 4 Thursday Showdown pre-lock audit

## 1. Entry readiness

**PRE-LOCK PREPARATION COMPLETE; NOT ENTRY READY.** PIT at CLE, Thursday October 1, 2026, 8:15 PM EDT. All numbers are prospective. No game results, realized ownership, exports or contest entries were used.

Freeze: 2026-10-01T03:35:34.082594+00:00; projection cutoff 2026-09-30 23:29:12.566568-04:00; completed projection `9d894467-e0c7-4fdc-a097-fd21c8383148`. This is the latest imported DK salary file, observed September 29 at 15:41 EDT—not a freshly authenticated DK download. Its checksum matches the immutable source copy. Recheck salaries tomorrow.

| Check | Finding | Disposition |
| --- | --- | --- |
| Salary/identity | 102 CPT/FLEX salary rows; 51 canonical players; 2 teams; unique slot IDs | PASS within imported snapshot |
| Projection | 47 stored projections; 31 positive means; 23 final eligible research players | WARN: four currently inactive/PS salary players lack projections |
| Ownership | 50/51 identities, KC missing; estimates have poor Showdown calibration | DIAGNOSTIC ONLY; uniformly unavailable to shadow selection |
| Market | Fresh DK observation 23:24 EDT; PIT −2.5, total 38.5 | PASS for tonight; refresh tomorrow |
| Injuries | Wednesday final club reports reconciled; both offensive OUT players zeroed | PASS for tonight; game-day actives not published |
| Starters | Rodgers and Watson; backups excluded by existing evidence hierarchy | Provisional; refresh quarterback news |
| Role | Official active roster/depth plus lagged opportunity; no invented forward routes/snaps | Fragile bench roles remain conditional |
| Duplicates | CPT/FLEX source rows map to one canonical identity; six distinct players per roster | PASS |
| Legal generation | 769 unique research rosters validated; 1 CPT/5 FLEX, ≤$50,000, both teams | PASS |
| Production entry readiness | Existing Showdown GPP gate warns on projection coverage | Additional source/ownership gates prevent ENTRY READY label |

KC's new CPT/FLEX aliases were resolved against its unique canonical CLE/WR identity and official roster/depth evidence, not raw display-name matching. The initial blocked freeze remains preserved. Four missing projection rows are not treated as usable punts; all have non-active source evidence. Active-roster availability=1 is an eligibility assumption before inactives, not a literal certainty of playing.

## 2. Current injury/status summary

Wednesday's authoritative reports agree with all seven supplied designations.

| Team | Player | Status | Treatment |
| --- | --- | --- | --- |
| PIT | Rico Dowdle, toe | OUT | Mean/P90 zero; unavailable; absent from all candidates |
| PIT | Joey Porter Jr., back/conditioning | OUT | Secondary matchup uncertainty; no fantasy-player exclusion |
| PIT | Jalen Ramsey, wrist | QUESTIONABLE | Monitor defensive personnel; no offensive-player exclusion |
| PIT | Brandin Echols, concussion | QUESTIONABLE | Cleared protocol but designation persists; monitor actives |
| CLE | Tylan Wallace, knee | OUT | Mean/P90 zero; unavailable; absent from all candidates |
| CLE | Elgton Jenkins, concussion | OUT | Center replacement/pressure uncertainty |
| CLE | Teven Jenkins, back | OUT | Offensive-line depth uncertainty |

[Steelers final report](https://www.steelers.com/news/week-4-injury-report-browns), [Browns final report](https://www.clevelandbrowns.com/news/elgton-jenkins-out-for-week-4-against-the-steelers-injury-report).

The old inputs still had Wallace questionable and a stale Dowdle committee projection. Fresh source snapshots and the existing feature/projection pipeline correct those. Warren's refreshed mean is 12.51, P90 23.98. Homer is on the active roster; last week's Nichols elevation does not establish this week's availability. Defensive/OL evidence is qualitative in this audit: no bespoke projection bump or newly fitted injury coefficient was invented. Losing PIT defensive backs supports scrutiny of CLE passing; losing CLE linemen adds pressure uncertainty in the other direction.

## 3. Market environment

Frozen DraftKings line: PIT −2.5 / CLE +2.5, total 38.5; implied PIT 20.5, CLE 18.0. This modest favorite and low total do not justify declaring either team a likely blowout. The source has no reliable publication timestamp; the freeze preserves the retrieval observation separately. [DraftKings market](https://dknetwork.draftkings.com/moneyline-total-spread/).

NWS hourly forecast updated September 30 at 21:32 EDT: kickoff approximately 76°F, SW wind 9 mph, precipitation probability 4%; late evening approximately 75°F/8 mph. No manual weather adjustment was applied. [NWS point/forecast lineage](https://api.weather.gov/points/41.506,-81.699).

Existing symmetric 14-point conditional scenarios retain total 38.5 and condition winner/loser implied scoring to 26.25/12.25. They are bounded role/scoring heuristics, not estimated scenario probabilities or a joint simulation. Each conditional roster is re-solved on the unconditioned model before baseline comparison.

## 4. Player projection/role summary

| Player | Pos | Salary | Mean | P90 | Official depth | Role confidence / uncertain |
| --- | --- | --- | --- | --- | --- | --- |
| Jerry Jeudy | WR | 3000 | 6.24 | 17.37 | STARTER | high / False |
| Eli Heidenreich | RB | 2200 | 1.56 | 3.77 | reserve/unit | medium / True |
| Darnell Washington | TE | 3600 | 3.67 | 8.29 | STARTER | high / False |
| Quinshon Judkins | RB | 8800 | 10.42 | 21.89 | STARTER | high / False |
| Michael Pittman Jr. | WR | 7000 | 7.19 | 18.32 | STARTER | high / False |
| Denzel Boston | WR | 8000 | 9.61 | 22.45 | STARTER | medium / False |
| KC Concepcion Jr. | WR | 6400 | 7.34 | 17.17 | STARTER | medium / False |
| Germie Bernard | WR | 3200 | 6.76 | 12.71 | reserve/unit | medium / True |
| Blake Whiteheart | TE | 1600 | 2.07 | 6.69 | reserve/unit | high / True |
| Deshaun Watson | QB | 9400 | 12.32 | 22.98 | STARTER | unavailable / False |
| Roman Wilson | WR | 4000 | 7.03 | 12.98 | STARTER | high / False |
| Browns | DST | 4800 | 5.69 | 12.46 | reserve/unit | unavailable / False |
| Travis Homer | RB | 2600 | 0.93 | 3.14 | reserve/unit | high / True |
| Jaleel McLaughlin | RB | 400 | 2.98 | 11.00 | reserve/unit | high / True |
| Chris Boswell | K | 5200 | 6.50 | 11.66 | STARTER | unavailable / False |
| Raheim Sanders | RB | 4400 | 4.03 | 12.05 | reserve/unit | high / True |
| Pat Freiermuth | TE | 5600 | 8.53 | 15.65 | STARTER | high / False |
| Andre Szmyt | K | 4600 | 7.90 | 13.06 | STARTER | unavailable / False |
| Harold Fannin Jr. | TE | 7400 | 7.87 | 14.99 | STARTER | high / False |
| DK Metcalf | WR | 9000 | 12.23 | 25.07 | STARTER | high / False |
| Steelers | DST | 5000 | 5.78 | 12.55 | reserve/unit | unavailable / False |
| Jaylen Warren | RB | 9600 | 12.51 | 23.98 | STARTER | high / False |
| Aaron Rodgers | QB | 9800 | 9.22 | 20.13 | STARTER | unavailable / False |

Role confidence comes from lagged model features; it is distinct from official future role certainty. For example Bernard's 4% recent snap share conflicts with treating a medium model confidence tag as secure usage. Official depth charts are unofficial and are not guaranteed workloads. [PIT depth](https://www.steelers.com/team/depth-chart/), [CLE depth](https://www.clevelandbrowns.com/news/browns-announce-unofficial-depth-chart-for-week-4-vs-the-steelers). Forward snaps/routes are unavailable. Σ marginal P90 throughout this report is a sum of player ceilings, not a calibrated lineup 90th percentile or payout estimate.

## 5. Candidate-generation coverage

The unchanged single-entry production control creates 30 candidates. The expanded baseline search creates 691; full conditional-model discovery adds 78 unique baseline-legal rosters, producing **769**. Discovery covers global ceiling/mean, every retained CPT, forced FLEX, both single-QB paths, dual QB, exact 3–3/4–2/5–1 allocations, RB+DST, QB+WR, K+DST, and both symmetric decisive conditions.

Every one of the 23 eligible players has CPT and FLEX coverage. The full 51-player audit includes excluded players with explicit status/model reasons in `player_coverage.csv`. No meaningful eligible player has unexpected zero coverage.

| Player | FLEX count | CPT count | Best FLEX selector | Best CPT selector | Peak containing mean | Peak containing ΣP90 |
| --- | --- | --- | --- | --- | --- | --- |
| Jaylen Warren | 442 | 36 | 0.91883 | 0.90096 | 67.88 | 142.42 |
| Deshaun Watson | 601 | 30 | 0.92327 | 0.91847 | 67.88 | 142.42 |
| DK Metcalf | 525 | 80 | 0.91847 | 0.92327 | 67.88 | 142.42 |
| Quinshon Judkins | 328 | 30 | 0.90060 | 0.88419 | 67.88 | 142.42 |
| Denzel Boston | 360 | 46 | 0.92327 | 0.90693 | 67.06 | 142.42 |
| Aaron Rodgers | 453 | 27 | 0.92327 | 0.90744 | 66.54 | 138.57 |
| Pat Freiermuth | 75 | 29 | 0.92327 | 0.88626 | 66.09 | 136.30 |
| Andre Szmyt | 73 | 33 | 0.91785 | 0.86381 | 67.88 | 136.89 |
| Harold Fannin Jr. | 29 | 32 | 0.89197 | 0.83613 | 64.72 | 135.98 |
| KC Concepcion Jr. | 120 | 28 | 0.89660 | 0.87638 | 65.85 | 140.24 |
| Michael Pittman Jr. | 122 | 30 | 0.90043 | 0.89605 | 63.90 | 138.21 |
| Roman Wilson | 42 | 30 | 0.91883 | 0.87603 | 66.33 | 135.04 |
| Germie Bernard | 44 | 28 | 0.89422 | 0.85191 | 66.33 | 134.77 |
| Chris Boswell | 31 | 33 | 0.89077 | 0.84398 | 66.48 | 135.49 |
| Jerry Jeudy | 338 | 30 | 0.92327 | 0.90060 | 67.88 | 142.42 |
| Steelers | 94 | 25 | 0.81543 | 0.76846 | 65.76 | 136.38 |
| Browns | 93 | 27 | 0.84587 | 0.79154 | 65.67 | 136.29 |
| Raheim Sanders | 19 | 34 | 0.86589 | 0.79075 | 64.01 | 135.88 |
| Darnell Washington | 4 | 31 | 0.88551 | 0.81862 | 62.31 | 130.34 |
| Jaleel McLaughlin | 43 | 34 | 0.86587 | 0.81187 | 66.32 | 139.36 |
| Blake Whiteheart | 3 | 31 | 0.84888 | 0.79130 | 60.71 | 128.75 |
| Eli Heidenreich | 3 | 33 | 0.82848 | 0.77012 | 60.19 | 125.83 |
| Travis Homer | 3 | 32 | 0.82312 | 0.76203 | 59.57 | 126.22 |

This is a broad best-found frontier, not exhaustive enumeration of all DK-legal rosters. Existing single-entry policy requires a starting QB, requires QB backing for WR/TE CPT, and restricts multiple same-team pass catchers without QB. Zero-QB builds are therefore outside this policy's feasible set; that is an explicit architectural restriction, not a discovered impossibility. Low-opportunity gate exclusions also remain intact. CPT depth of 20 ceiling/5 mean proposals is a search budget, not a count of every possible competitive roster.

| Discovery family | Unique rosters touched | Within .05 | Exclusive .05 | Exclusive .10 | Solve seconds |
| --- | --- | --- | --- | --- | --- |
| captain_ceiling | 460 | 50 | 11 | 71 | 74.05 |
| captain_mean | 115 | 10 | 0 | 8 | 7.38 |
| conditional_exact | 354 | 30 | 2 | 9 | 16.33 |
| construction | 50 | 17 | 1 | 3 | 5.32 |
| forced_flex | 48 | 17 | 3 | 11 | 4.42 |
| global_ceiling | 40 | 19 | 0 | 1 | 6.43 |
| global_mean | 25 | 4 | 0 | 1 | 7.31 |
| qb_construction | 45 | 15 | 0 | 1 | 4.71 |
| scenario | 238 | 26 | 0 | 0 | 7.04 |
| structure | 54 | 11 | 0 | 0 | 5.70 |

Contribution counts overlap; exclusivity is conditional on these search budgets. Early `scenario` proposals reused baseline correlation coefficients; they are retained as legal discovery proposals only. `conditional_exact` rebuilds the complete conditional model, including QB correlation scaling, and exclusively supplies the decisive-scenario results below. Search/selection runtime: 146.24 seconds, excluding source refresh, model training, tests and report rendering. Native CBC solves the unchanged mathematical objective; no solver timeouts or unproven incumbents were accepted.

Per-captain ceiling search adds the most exclusive close-frontier coverage (11 within .05) but consumes 74 seconds, approximately half the search/selection runtime. Forced FLEX adds three exclusive .05 candidates in 4.4 seconds; complete conditional rebuilding adds two in 16.3 seconds and supports the decisive-game audit. Per-captain mean adds eight exclusive candidates within .10, none within .05. Initial approximate scenario and generic structural sweeps have no exclusive .10 candidates in this budget; keep their diagnostic purpose separate from claiming incremental frontier gains. These order/budget-dependent contributions do not prove a source can be safely removed on future slates.

## 6. CPT frontier

| Tolerance | Candidates | Distinct CPTs | CPT names |
| --- | --- | --- | --- |
| 0.05 | 59 | 11 | DK Metcalf, Deshaun Watson, Aaron Rodgers, Denzel Boston, Jaylen Warren, Jerry Jeudy, Michael Pittman Jr., Pat Freiermuth, Quinshon Judkins, KC Concepcion Jr., Roman Wilson |
| 0.10 | 238 | 15 | DK Metcalf, Deshaun Watson, Aaron Rodgers, Denzel Boston, Jaylen Warren, Jerry Jeudy, Michael Pittman Jr., Pat Freiermuth, Quinshon Judkins, KC Concepcion Jr., Roman Wilson, Andre Szmyt, Germie Bernard, Chris Boswell, Harold Fannin Jr. |
| 0.15 | 446 | 20 | DK Metcalf, Deshaun Watson, Aaron Rodgers, Denzel Boston, Jaylen Warren, Jerry Jeudy, Michael Pittman Jr., Pat Freiermuth, Quinshon Judkins, KC Concepcion Jr., Roman Wilson, Andre Szmyt, Germie Bernard, Chris Boswell, Harold Fannin Jr., Darnell Washington, Jaleel McLaughlin, Browns, Blake Whiteheart, Raheim Sanders |
| 0.20 | 617 | 23 | DK Metcalf, Deshaun Watson, Aaron Rodgers, Denzel Boston, Jaylen Warren, Jerry Jeudy, Michael Pittman Jr., Pat Freiermuth, Quinshon Judkins, KC Concepcion Jr., Roman Wilson, Andre Szmyt, Germie Bernard, Chris Boswell, Harold Fannin Jr., Darnell Washington, Jaleel McLaughlin, Browns, Blake Whiteheart, Raheim Sanders, Eli Heidenreich, Steelers, Travis Homer |
| 0.30 | 746 | 23 | DK Metcalf, Deshaun Watson, Aaron Rodgers, Denzel Boston, Jaylen Warren, Jerry Jeudy, Michael Pittman Jr., Pat Freiermuth, Quinshon Judkins, KC Concepcion Jr., Roman Wilson, Andre Szmyt, Germie Bernard, Chris Boswell, Harold Fannin Jr., Darnell Washington, Jaleel McLaughlin, Browns, Blake Whiteheart, Raheim Sanders, Eli Heidenreich, Steelers, Travis Homer |

Best selector 0.92327. Tolerances are absolute score differences, not fantasy-point gaps or probabilities. Normalizers are frozen once over the identical 769-roster universe. Scores from the narrow 30-roster control have different normalizers and are not directly subtracted. Projection/context/correlation/CPT-prior parameters are unchanged. Weights remain mean .35, ceiling .30, solver .20, correlation .10, context .05, existing chalk coefficient .03; ownership is uniformly unavailable in the quality shadow.

## 7. CPT depth

| CPT | CPT salary | Base mean | CPT mean | CPT P90 | Best selector | Best lineup mean | Best lineup ΣP90 | Depth .05/.10/.15/.20/.30 | Salary premium |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DK Metcalf | 13500 | 12.23 | 18.34 | 37.61 | 0.92327 | 64.27 | 136.18 | 16/39/64/79/80 | 4500 |
| Deshaun Watson | 14100 | 12.32 | 18.48 | 34.46 | 0.91847 | 64.31 | 135.13 | 9/23/29/30/30 | 4700 |
| Aaron Rodgers | 14700 | 9.22 | 13.84 | 30.19 | 0.90744 | 62.76 | 133.71 | 8/17/27/27/27 | 4900 |
| Denzel Boston | 12000 | 9.61 | 14.41 | 33.68 | 0.90693 | 62.96 | 134.87 | 5/22/36/43/46 | 4000 |
| Jaylen Warren | 14400 | 12.51 | 18.76 | 35.96 | 0.90096 | 65.81 | 134.49 | 3/21/30/36/36 | 4800 |
| Jerry Jeudy | 4500 | 6.24 | 9.36 | 26.06 | 0.90060 | 63.17 | 138.57 | 11/21/26/29/30 | 1500 |
| Michael Pittman Jr. | 10500 | 7.19 | 10.79 | 27.48 | 0.89605 | 60.41 | 135.48 | 1/13/23/30/30 | 3500 |
| Pat Freiermuth | 8400 | 8.53 | 12.79 | 23.47 | 0.88626 | 65.32 | 132.99 | 2/16/24/29/29 | 2800 |
| Quinshon Judkins | 13200 | 10.42 | 15.64 | 32.84 | 0.88419 | 64.18 | 134.03 | 1/12/25/28/30 | 4400 |
| KC Concepcion Jr. | 9600 | 7.34 | 11.01 | 25.75 | 0.87638 | 61.42 | 129.36 | 2/13/23/28/28 | 3200 |
| Roman Wilson | 6000 | 7.03 | 10.55 | 19.47 | 0.87603 | 63.07 | 129.00 | 1/17/24/29/30 | 2000 |
| Andre Szmyt | 6900 | 7.90 | 11.85 | 19.59 | 0.86381 | 64.38 | 129.11 | 0/10/24/28/33 | 2300 |
| Germie Bernard | 4800 | 6.76 | 10.14 | 19.07 | 0.85191 | 63.94 | 131.59 | 0/8/20/24/28 | 1600 |
| Chris Boswell | 7800 | 6.50 | 9.75 | 17.49 | 0.84398 | 62.28 | 127.01 | 0/3/20/25/33 | 2600 |
| Harold Fannin Jr. | 11100 | 7.87 | 11.81 | 22.49 | 0.83613 | 59.02 | 126.35 | 0/3/18/30/32 | 3700 |
| Darnell Washington | 5400 | 3.67 | 5.50 | 12.43 | 0.81862 | 59.12 | 121.75 | 0/0/15/25/31 | 1800 |
| Jaleel McLaughlin | 600 | 2.98 | 4.47 | 16.50 | 0.81187 | 60.36 | 131.10 | 0/0/6/20/31 | 200 |
| Browns | 7200 | 5.69 | 8.54 | 18.69 | 0.79154 | 62.54 | 130.33 | 0/0/4/19/27 | 2400 |
| Blake Whiteheart | 2400 | 2.07 | 3.11 | 10.03 | 0.79130 | 59.00 | 124.64 | 0/0/2/14/29 | 800 |
| Raheim Sanders | 6600 | 4.03 | 6.04 | 18.07 | 0.79075 | 58.57 | 127.59 | 0/0/6/21/31 | 2200 |
| Eli Heidenreich | 3300 | 1.56 | 2.33 | 5.66 | 0.77012 | 58.22 | 120.26 | 0/0/0/8/26 | 1100 |
| Steelers | 7500 | 5.78 | 8.67 | 18.82 | 0.76846 | 60.77 | 126.09 | 0/0/0/9/25 | 2500 |
| Travis Homer | 3900 | 0.93 | 1.39 | 4.72 | 0.76203 | 57.28 | 119.32 | 0/0/0/6/24 | 1300 |

A low-salary CPT creates room relative to a more expensive CPT, but still costs 50% more than its own FLEX salary. `captain_frontier.csv` contains all construction/thesis memberships and peaks; `quality_shadow.json` retains full correlated/negative-rule evidence and supporting lineups. Kicker/DST/backup-role CPT coverage does not make them equally viable primary captains.

## 8. QB CPT vs FLEX analysis

**Deshaun Watson**: recent carries/game 5.00; high-rushing classifier=True. CPT salary $14,100, premium $4,700; point gain 6.16 mean / 11.49 ceiling. Best CPT #3 selector 0.91847; best FLEX #1 0.92327; opportunity cost 0.00480.

CPT: **CPT Deshaun Watson** ($14,100, CLE); **FLEX Denzel Boston** ($8,000, CLE); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX Aaron Rodgers** ($9,800, PIT); **FLEX DK Metcalf** ($9,000, PIT); **FLEX Pat Freiermuth** ($5,600, PIT)

FLEX: **CPT DK Metcalf** ($13,500, PIT); **FLEX Denzel Boston** ($8,000, CLE); **FLEX Deshaun Watson** ($9,400, CLE); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX Aaron Rodgers** ($9,800, PIT); **FLEX Pat Freiermuth** ($5,600, PIT)

**Aaron Rodgers**: recent carries/game 1.33; high-rushing classifier=False. CPT salary $14,700, premium $4,900; point gain 4.61 mean / 10.06 ceiling. Best CPT #5 selector 0.90744; best FLEX #1 0.92327; opportunity cost 0.01583.

CPT: **CPT Aaron Rodgers** ($14,700, PIT); **FLEX Denzel Boston** ($8,000, CLE); **FLEX Deshaun Watson** ($9,400, CLE); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX DK Metcalf** ($9,000, PIT); **FLEX Pat Freiermuth** ($5,600, PIT)

FLEX: **CPT DK Metcalf** ($13,500, PIT); **FLEX Denzel Boston** ($8,000, CLE); **FLEX Deshaun Watson** ($9,400, CLE); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX Aaron Rodgers** ($9,800, PIT); **FLEX Pat Freiermuth** ($5,600, PIT)

Watson qualifies as mobile from five lagged carries/game; no new rushing projection was fabricated. His best CPT includes two CLE pass catchers and is competitive. Rodgers has approximately 1.33 carries/game; CPT requires two PIT WR/TE under the unchanged hard rule. Rodgers remains mathematically close but adds no independent thesis when only the slot rotates on the same core. Keep him out of the primary three; the ten-entry sensitivity retains one explicit marginal test. Neither passing yards nor a dollar salary premium proves optimal-CPT probability.

## 9. Football thesis discovery

| Thesis | Raw depth | Depth .05 | Peak selector | Peak mean | Peak ΣP90 | Competitive CPTs ≤.10 |
| --- | --- | --- | --- | --- | --- | --- |
| CLE passing concentration | 157 | 9 | 0.90118 | 63.64 | 133.59 | DK Metcalf, Jerry Jeudy, Denzel Boston, Deshaun Watson, KC Concepcion Jr., Jaylen Warren, Michael Pittman Jr., Andre Szmyt, Pat Freiermuth |
| CLE rushing-led concentration | 67 | 0 | 0.86209 | 63.55 | 131.44 | Quinshon Judkins |
| CLE rushing/control | 9 | 0 | 0.72721 | 61.53 | 131.84 | none within .10 |
| PIT passing concentration | 156 | 14 | 0.91883 | 65.67 | 135.04 | DK Metcalf, Deshaun Watson, Aaron Rodgers, Jerry Jeudy, Pat Freiermuth, Roman Wilson, Michael Pittman Jr., Germie Bernard, Chris Boswell, Andre Szmyt |
| PIT rushing-led concentration | 41 | 2 | 0.90096 | 65.81 | 134.49 | Jaylen Warren |
| PIT rushing/control | 9 | 0 | 0.77160 | 65.76 | 135.82 | none within .10 |
| balanced competitive | 297 | 34 | 0.92327 | 64.27 | 136.18 | DK Metcalf, Deshaun Watson, Aaron Rodgers, Denzel Boston, Jerry Jeudy, Michael Pittman Jr., Quinshon Judkins, Jaylen Warren, KC Concepcion Jr., Pat Freiermuth, Roman Wilson, Andre Szmyt, Germie Bernard, Chris Boswell, Harold Fannin Jr. |
| defensive/kicking | 33 | 0 | 0.80897 | 64.31 | 125.03 | none within .10 |

These are transparent roster-based hypotheses, not independent simulated outcomes. A 3–3 dual-QB roster stays balanced when its captain changes. Four-plus same-team concentration plus its QB and multiple receivers supports passing concentration. Own-team RB CPT with four-plus teammates supports rushing-led scoring with passing support; it does not prove run-only control. RB+DST supports a separate control family. A K/DST CPT requires another K/DST selection before receiving a defensive/kicking label. Each legal thesis's QB exposure, team allocations, rule triggers and player dependencies are retained in the raw rosters; no empty categories were manufactured. CLE passing depends on Watson/Boston/Jeudy plus uncertain PIT secondary health; PIT offense depends on Rodgers/Metcalf and Warren's post-Dowdle workload.

| Thesis | QB coverage within family | PIT-CLE allocation counts | Most common player dependencies |
| --- | --- | --- | --- |
| CLE passing concentration | Deshaun Watson: 100.0%, Aaron Rodgers: 20.4% | {'2-4': 100, '1-5': 57} | {'Deshaun Watson': 157, 'Denzel Boston': 128, 'Jerry Jeudy': 114, 'DK Metcalf': 105} |
| CLE rushing-led concentration | Deshaun Watson: 97.0%, Aaron Rodgers: 25.4% | {'2-4': 45, '1-5': 22} | {'Deshaun Watson': 65, 'Quinshon Judkins': 57, 'DK Metcalf': 55, 'Denzel Boston': 42} |
| CLE rushing/control | Aaron Rodgers: 100.0%, Deshaun Watson: 33.3% | {'3-3': 9} | {'Browns': 9, 'DK Metcalf': 9, 'Aaron Rodgers': 9, 'Quinshon Judkins': 7} |
| PIT passing concentration | Deshaun Watson: 48.1%, Aaron Rodgers: 100.0% | {'4-2': 90, '5-1': 66} | {'Aaron Rodgers': 156, 'DK Metcalf': 142, 'Jaylen Warren': 126, 'Deshaun Watson': 75} |
| PIT rushing-led concentration | Deshaun Watson: 65.9%, Aaron Rodgers: 90.2% | {'4-2': 23, '5-1': 18} | {'Jaylen Warren': 39, 'Aaron Rodgers': 37, 'DK Metcalf': 36, 'Deshaun Watson': 27} |
| PIT rushing/control | Deshaun Watson: 100.0%, Aaron Rodgers: 11.1% | {'3-3': 9} | {'Deshaun Watson': 9, 'Steelers': 9, 'Jaylen Warren': 9, 'Denzel Boston': 8} |
| balanced competitive | Deshaun Watson: 90.9%, Aaron Rodgers: 72.7% | {'3-3': 203, '2-4': 58, '4-2': 29, '1-5': 5, '5-1': 2} | {'Deshaun Watson': 270, 'DK Metcalf': 227, 'Aaron Rodgers': 216, 'Jaylen Warren': 160} |
| defensive/kicking | Deshaun Watson: 75.8%, Aaron Rodgers: 36.4% | {'3-3': 15, '2-4': 5, '1-5': 3, '4-2': 7, '5-1': 3} | {'DK Metcalf': 29, 'Jaylen Warren': 26, 'Deshaun Watson': 25, 'Andre Szmyt': 19} |

QB coverage above is across discovered candidates, not proposed entry exposure or scenario probability. Ownership for every family remains diagnostic and unreliable. The full rule/stack structures and source-specific conditioned role dependencies accompany each candidate.

## 10. PIT-wins-big thesis

The complete existing conditional model boosts winner rush/control and DST paths, reduces loser rushing, allows loser passing chase, and modestly suppresses loser kicking. Each search requires the winner CPT and either winner RB+DST or winner QB+WR, across 3–3, 4–2 and 5–1. A 5–1 allocation alone is insufficient. The top-five table below uses ≥4 winner players for the explicit dominant subset; 3–3 conditional candidates are preserved separately.

Unique dominant depth 131; 8 inside .05; 23 inside .10. The closest-to-global dominant variant is baseline #2, CPT DK Metcalf, selector 0.91883, gap 0.00444. Conditional objective ordering and baseline-quality ordering differ.

1. CPT **DK Metcalf**, PIT 4–2; conditional objective 160.70, mean/ΣP90 69.90/143.33; baseline #2 selector 0.91883, gap 0.00444.

   **CPT DK Metcalf** ($13,500, PIT); **FLEX Deshaun Watson** ($9,400, CLE); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX Aaron Rodgers** ($9,800, PIT); **FLEX Jaylen Warren** ($9,600, PIT); **FLEX Roman Wilson** ($4,000, PIT)

2. CPT **DK Metcalf**, PIT 4–2; conditional objective 160.02, mean/ΣP90 69.61/143.04; baseline #21 selector 0.89422, gap 0.02905.

   **CPT DK Metcalf** ($13,500, PIT); **FLEX Deshaun Watson** ($9,400, CLE); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX Aaron Rodgers** ($9,800, PIT); **FLEX Germie Bernard** ($3,200, PIT); **FLEX Jaylen Warren** ($9,600, PIT)

3. CPT **DK Metcalf**, PIT 5–1; conditional objective 159.70, mean/ΣP90 66.96/142.89; baseline #161 selector 0.84239, gap 0.08088.

   **CPT DK Metcalf** ($13,500, PIT); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX Aaron Rodgers** ($9,800, PIT); **FLEX Jaylen Warren** ($9,600, PIT); **FLEX Michael Pittman Jr.** ($7,000, PIT); **FLEX Pat Freiermuth** ($5,600, PIT)

4. CPT **DK Metcalf**, PIT 5–1; conditional objective 158.44, mean/ΣP90 69.84/142.02; baseline #192 selector 0.83344, gap 0.08983.

   **CPT DK Metcalf** ($13,500, PIT); **FLEX Denzel Boston** ($8,000, CLE); **FLEX Aaron Rodgers** ($9,800, PIT); **FLEX Germie Bernard** ($3,200, PIT); **FLEX Jaylen Warren** ($9,600, PIT); **FLEX Pat Freiermuth** ($5,600, PIT)

5. CPT **DK Metcalf**, PIT 5–1; conditional objective 157.34, mean/ΣP90 64.71/141.01; baseline #345 selector 0.79977, gap 0.12350.

   **CPT DK Metcalf** ($13,500, PIT); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX Aaron Rodgers** ($9,800, PIT); **FLEX Jaylen Warren** ($9,600, PIT); **FLEX Michael Pittman Jr.** ($7,000, PIT); **FLEX Steelers** ($5,000, PIT)

The conditional assumptions do not estimate the chance of a 14-point win. Winner pass-led constructions can include the opposing QB/receiver because losing-side chase production can coexist with a decisive score margin. Winner RB+DST alternatives are retained even when they rank lower. Future lineman/secondary news can change which version is credible.

## 11. CLE-wins-big thesis

The complete existing conditional model boosts winner rush/control and DST paths, reduces loser rushing, allows loser passing chase, and modestly suppresses loser kicking. Each search requires the winner CPT and either winner RB+DST or winner QB+WR, across 3–3, 4–2 and 5–1. A 5–1 allocation alone is insufficient. The top-five table below uses ≥4 winner players for the explicit dominant subset; 3–3 conditional candidates are preserved separately.

Unique dominant depth 124; 5 inside .05; 28 inside .10. The closest-to-global dominant variant is baseline #13, CPT Jerry Jeudy, selector 0.90060, gap 0.02267. Conditional objective ordering and baseline-quality ordering differ.

1. CPT **Denzel Boston**, CLE 5–1; conditional objective 163.04, mean/ΣP90 67.43/147.96; baseline #144 selector 0.84812, gap 0.07515.

   **CPT Denzel Boston** ($12,000, CLE); **FLEX Deshaun Watson** ($9,400, CLE); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX KC Concepcion Jr.** ($6,400, CLE); **FLEX Quinshon Judkins** ($8,800, CLE); **FLEX DK Metcalf** ($9,000, PIT)

2. CPT **Denzel Boston**, CLE 5–1; conditional objective 160.74, mean/ΣP90 68.00/145.66; baseline #156 selector 0.84349, gap 0.07978.

   **CPT Denzel Boston** ($12,000, CLE); **FLEX Deshaun Watson** ($9,400, CLE); **FLEX Harold Fannin Jr.** ($7,400, CLE); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX Quinshon Judkins** ($8,800, CLE); **FLEX DK Metcalf** ($9,000, PIT)

3. CPT **Denzel Boston**, CLE 5–1; conditional objective 159.74, mean/ΣP90 68.66/144.65; baseline #168 selector 0.83954, gap 0.08373.

   **CPT Denzel Boston** ($12,000, CLE); **FLEX Andre Szmyt** ($4,600, CLE); **FLEX Deshaun Watson** ($9,400, CLE); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX Quinshon Judkins** ($8,800, CLE); **FLEX DK Metcalf** ($9,000, PIT)

4. CPT **Denzel Boston**, CLE 4–2; conditional objective 159.32, mean/ΣP90 65.71/144.50; baseline #139 selector 0.84952, gap 0.07375.

   **CPT Denzel Boston** ($12,000, CLE); **FLEX Deshaun Watson** ($9,400, CLE); **FLEX Jaleel McLaughlin** ($400, CLE); **FLEX Quinshon Judkins** ($8,800, CLE); **FLEX Aaron Rodgers** ($9,800, PIT); **FLEX DK Metcalf** ($9,000, PIT)

5. CPT **Jerry Jeudy**, CLE 4–2; conditional objective 159.28, mean/ΣP90 66.91/146.80; baseline #13 selector 0.90060, gap 0.02267.

   **CPT Jerry Jeudy** ($4,500, CLE); **FLEX Denzel Boston** ($8,000, CLE); **FLEX Deshaun Watson** ($9,400, CLE); **FLEX Quinshon Judkins** ($8,800, CLE); **FLEX Aaron Rodgers** ($9,800, PIT); **FLEX DK Metcalf** ($9,000, PIT)

The conditional assumptions do not estimate the chance of a 14-point win. Winner pass-led constructions can include the opposing QB/receiver because losing-side chase production can coexist with a decisive score margin. Winner RB+DST alternatives are retained even when they rank lower. Future lineman/secondary news can change which version is credible.

## 12. Competitive-game thesis

| Rank | CPT | Selector | Gap | Mean | Σ marginal P90 | Salary | PIT | CLE | Structure thesis |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | DK Metcalf | 0.92327 | 0.00000 | 64.27 | 136.18 | 49300 | 3 | 3 | balanced competitive |
| 3 | Deshaun Watson | 0.91847 | 0.00480 | 64.31 | 135.13 | 49500 | 3 | 3 | balanced competitive |
| 4 | DK Metcalf | 0.91785 | 0.00542 | 66.54 | 135.12 | 49900 | 3 | 3 | balanced competitive |
| 5 | Aaron Rodgers | 0.90744 | 0.01583 | 62.76 | 133.71 | 49700 | 3 | 3 | balanced competitive |
| 6 | Denzel Boston | 0.90693 | 0.01634 | 62.96 | 134.87 | 48800 | 3 | 3 | balanced competitive |

The central family includes both QBs and contributing pass catchers. Metcalf/Watson/Boston/Rodgers captain rotation on the same six-player roster creates captain alternatives, not four independent football stories. The primary joint search gives up the single top roster to obtain structurally distinct PIT- and CLE-concentrated alternatives with at least two changed players per pair.

## 13. Questionable-player analysis

No currently eligible offensive player carries a final QUESTIONABLE designation. Offensive OUTs have zero candidate/CPT exposure. Ramsey/Echols are defensive matchup uncertainties and are not silently removed from an offensive DK pool. Thus the cost of avoiding a designated offensive Q is 0 mean/ceiling/selector in this freeze. Role-fragile active backups are separate: primary exposure is capped at one of three for ≤$1,000 punts or uncertain reserves with <10% lagged snap share. The raw universe retains their original model assessments. New offensive Q designations tomorrow require fresh availability evidence and an avoidance-cost solve; they must not inherit today's assumed-active treatment.

The global best roster contains none of Homer, Heidenreich, Bernard, McLaughlin or Whiteheart. Avoiding each of those names individually leaves that exact frontier roster intact: cost versus its selector, mean and ceiling is zero. This does not imply their forced-containing upside is zero; coverage and containing-quality diagnostics remain in the player CSV.

## 14. Cheap-player audit

| Player | Salary | Mean/P90 | Recent snap share | Projected carries | Projected targets | Routes / forward snaps | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Jerry Jeudy | 3000 | 6.24/17.37 | 81.7% | N/A | 3.62 | N/A / N/A | high / uncertain=False |
| Eli Heidenreich | 2200 | 1.56/3.77 | 4.0% | 0.91 | 0.50 | N/A / N/A | medium / uncertain=True |
| Germie Bernard | 3200 | 6.76/12.71 | 4.0% | N/A | 4.28 | N/A / N/A | medium / uncertain=True |
| Blake Whiteheart | 1600 | 2.07/6.69 | 55.3% | N/A | 1.16 | N/A / N/A | high / uncertain=True |
| Travis Homer | 2600 | 0.93/3.14 | 0.0% | 0.94 | 0.00 | N/A / N/A | high / uncertain=True |
| Jaleel McLaughlin | 400 | 2.98/11.00 | 19.7% | 2.98 | 0.95 | N/A / N/A | high / uncertain=True |

These carries/targets are model expectations from lagged team-volume reconciliation with salary fallback; they are not reported Week 4 snap/route commitments. Jeudy's $3,000 salary and 81.7% recent snap share support meaningful use despite modest projected targets. McLaughlin's $400 salary buys limited rotational rushing/receiving access, not a guaranteed workload. Bernard has only 4% recent snaps despite modeled targets; Homer 0%, Heidenreich 4%: verify role/elevations, avoid heavy unsupported exposure. Whiteheart has recent snaps but low target volume. Wetjen, Ryan, Corley, Tonyan, Nowakowski/Burton and Skowronek do not pass the existing positive-opportunity/low-salary gate in this freeze; inactive practice-squad names are also absent. The final primary three uses none of the unsupported reserve punts; the thesis ten uses Bernard once. Return-role designation alone is not adequate receiving evidence. [PIT roster](https://www.steelers.com/team/players-roster/), [CLE roster](https://www.clevelandbrowns.com/team/players-roster/), [PIT transactions](https://www.steelers.com/team/transactions/), [CLE transactions](https://www.clevelandbrowns.com/team/transactions/).

## 15. Correlation audit

**A:** construction.showdown_competitive_four_two_v1=+0.096; correlation.qb_pass_catcher_saturated_1_v1=+0.600; correlation.shootout_bring_back_team_once_v1=+0.450; correlation.qb_pass_catcher_saturated_1_v1=+0.449; correlation.qb_pass_catcher_saturated_2_v1=+0.225; correlation.shootout_bring_back_team_once_v1=+0.337

**B:** construction.showdown_qb_captain_double_stack_v2=+0.216; construction.showdown_competitive_three_three_v1=+0.168; correlation.qb_pass_catcher_saturated_1_v1=+0.600; correlation.qb_pass_catcher_saturated_2_v1=+0.300; correlation.shootout_bring_back_team_once_v1=+0.450; correlation.qb_pass_catcher_saturated_1_v1=+0.449; correlation.qb_pass_catcher_saturated_2_v1=+0.225; correlation.shootout_bring_back_team_once_v1=+0.337

**C:** construction.showdown_competitive_four_two_v1=+0.129; correlation.qb_pass_catcher_saturated_1_v1=+0.600; correlation.qb_pass_catcher_saturated_2_v1=+0.300; correlation.shootout_bring_back_team_once_v1=+0.450

QB+catcher bonuses actually fire with diminishing 60/30/10 stacking rewards and one opposing bring-back per QB team, scaled by QB projection quality. WR/TE CPT requires own QB; non-mobile QB CPT requires two own pass catchers. RB+DST, opposing DST conflicts, kicker/environment and 5–1 coherence are audited in `correlation_rules_fired.csv`, including negative adjustments and zero-fire cases. No blanket DST/opponent ban or generic opposing-RB exclusion was added. Opposing RB/control conflict is chiefly expressed in the conditional role model, not a new arbitrary pair penalty. Opposing-pass-catcher/QB exposure can represent chase volume. A 4–2/5–1 format bonus is a construction rule, not proof of a blowout. Small model/report correlation-attribution residuals are retained as `other_or_unattributed`; they are not reallocated into invented football bonuses.

## 16. Recommended 3-entry shadow

| Rank | CPT | Selector | Gap | Mean | Σ marginal P90 | Salary | PIT | CLE | Structure thesis |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | DK Metcalf | 0.91883 | 0.00444 | 65.67 | 135.04 | 49300 | 4 | 2 | PIT passing concentration |
| 3 | Deshaun Watson | 0.91847 | 0.00480 | 64.31 | 135.13 | 49500 | 3 | 3 | balanced competitive |
| 35 | Jerry Jeudy | 0.88427 | 0.03900 | 66.45 | 142.42 | 49300 | 2 | 4 | CLE passing concentration |

**Lineup A — PIT passing concentration:**

**CPT DK Metcalf** ($13,500, PIT); **FLEX Deshaun Watson** ($9,400, CLE); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX Aaron Rodgers** ($9,800, PIT); **FLEX Jaylen Warren** ($9,600, PIT); **FLEX Roman Wilson** ($4,000, PIT)

**Lineup B — balanced competitive:**

**CPT Deshaun Watson** ($14,100, CLE); **FLEX Denzel Boston** ($8,000, CLE); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX Aaron Rodgers** ($9,800, PIT); **FLEX DK Metcalf** ($9,000, PIT); **FLEX Pat Freiermuth** ($5,600, PIT)

**Lineup C — CLE passing concentration:**

**CPT Jerry Jeudy** ($4,500, CLE); **FLEX Denzel Boston** ($8,000, CLE); **FLEX Deshaun Watson** ($9,400, CLE); **FLEX Quinshon Judkins** ($8,800, CLE); **FLEX DK Metcalf** ($9,000, PIT); **FLEX Jaylen Warren** ($9,600, PIT)

Joint constraints: three distinct CPTs; three supported structural theses; ≤4 shared players per pair; limited fragile-role exposure; candidates within .10 of the same frontier. This is an explicit research selection policy implementing the user's diversity request, not a production default change. Three raw-best distinct rosters total 2.76057; primary total 2.72157, sacrifice 0.03900 (1.41%). Compared with repeating the single strongest roster three times, sacrifice is 0.04824 (1.74%). Captain-only selection costs less but merely rotates slots on an identical core. No payouts/EV are inferred.

## 17. Recommended 10-entry shadow

| Rank | CPT | Selector | Gap | Mean | Σ marginal P90 | Salary | PIT | CLE | Structure thesis |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | DK Metcalf | 0.92327 | 0.00000 | 64.27 | 136.18 | 49300 | 3 | 3 | balanced competitive |
| 2 | DK Metcalf | 0.91883 | 0.00444 | 65.67 | 135.04 | 49300 | 4 | 2 | PIT passing concentration |
| 3 | Deshaun Watson | 0.91847 | 0.00480 | 64.31 | 135.13 | 49500 | 3 | 3 | balanced competitive |
| 4 | DK Metcalf | 0.91785 | 0.00542 | 66.54 | 135.12 | 49900 | 3 | 3 | balanced competitive |
| 5 | Aaron Rodgers | 0.90744 | 0.01583 | 62.76 | 133.71 | 49700 | 3 | 3 | balanced competitive |
| 6 | Denzel Boston | 0.90693 | 0.01634 | 62.96 | 134.87 | 48800 | 3 | 3 | balanced competitive |
| 11 | DK Metcalf | 0.90118 | 0.02209 | 63.64 | 133.59 | 48300 | 2 | 4 | CLE passing concentration |
| 18 | Denzel Boston | 0.89617 | 0.02710 | 63.24 | 133.77 | 49400 | 3 | 3 | balanced competitive |
| 37 | DK Metcalf | 0.88281 | 0.04046 | 64.78 | 131.52 | 49500 | 4 | 2 | PIT passing concentration |
| 96 | Roman Wilson | 0.86171 | 0.06157 | 61.40 | 127.32 | 49800 | 4 | 2 | PIT passing concentration |

The quality-maximizing cap-constrained ten totals 9.03997. Requiring one representative of each of the three supported primary theses totals 9.03466, incremental sacrifice 0.00531 (0.059%). This is the preferred thesis sensitivity; it does not force weak defensive or pure-rushing categories. Existing v3 exposure ceilings are retained: CPT ≤6/10, core ≤8/10, starting QB ≤10/10, ≤$1,000 punt ≤4/10. The allocation emerges from this slate; no previous-game CPT distribution is reused. Ten distinct rosters are retained, but both QBs remain heavily exposed.

## 18. CPT allocation

| Portfolio | CPT allocation |
| --- | --- |
| Primary three | {'DK Metcalf': 1, 'Deshaun Watson': 1, 'Jerry Jeudy': 1} |
| Quality ten | {'DK Metcalf': 5, 'Deshaun Watson': 1, 'Aaron Rodgers': 1, 'Denzel Boston': 2, 'Roman Wilson': 1} |
| Thesis ten | {'DK Metcalf': 5, 'Deshaun Watson': 1, 'Aaron Rodgers': 1, 'Denzel Boston': 2, 'Roman Wilson': 1} |

Ownership is descriptive only in the quality/thesis shadows. The generated estimates sum to 247.66% CPT and 369.90% FLEX across loaded players, rather than the expected 100% and 500% for complete slate slot marginals. Showdown CPT held-out MAE 12.92 percentage points/bias +11.57; FLEX MAE 7.59/bias −3.99. The pooled diagnostic promotion check passes, but that does not establish reliable Showdown marginals or authorize promotion. KC has no estimate. `player_coverage.csv` retains individual draft estimates. Original production control preserves its existing chalk behavior, including the missing-ownership inconsistency; the quality shadow masks every candidate's ownership uniformly, while retaining the .03 coefficient unchanged. No reliable duplication or leverage probability is available.

## 19. Thesis allocation

| Portfolio | Thesis allocation |
| --- | --- |
| Primary three | {'PIT passing concentration': 1, 'balanced competitive': 1, 'CLE passing concentration': 1} |
| Quality ten | {'balanced competitive': 7, 'PIT passing concentration': 3} |
| Thesis ten | {'balanced competitive': 6, 'PIT passing concentration': 3, 'CLE passing concentration': 1} |

Distinct CPT is not distinct thesis. The same six-player dual-QB core supports several CPT choices. The ten-entry diversity increment covers a CLE-concentrated construction without pretending that five CPTs are five independent game scenarios. All selected offensive families share important scoring dependencies.

## 20. Player exposures

| Player | Primary count / 3 | Thesis-ten count / 10 |
| --- | --- | --- |
| Aaron Rodgers | 2 | 10 |
| Andre Szmyt | 0 | 2 |
| DK Metcalf | 3 | 8 |
| Denzel Boston | 2 | 8 |
| Deshaun Watson | 3 | 10 |
| Germie Bernard | 0 | 1 |
| Jaylen Warren | 2 | 4 |
| Jerry Jeudy | 3 | 8 |
| Michael Pittman Jr. | 0 | 1 |
| Pat Freiermuth | 1 | 6 |
| Quinshon Judkins | 1 | 0 |
| Roman Wilson | 1 | 2 |

The primary three still shares Jeudy, Watson and Metcalf in all entries. These are concentrated exposure decisions supported by the frozen frontier, not independence claims. Both QBs are 10/10 in the ten-entry sensitivity; this is the largest residual dependence. Fragile/cheap alternatives remain capped rather than being purchased purely for salary fit.

## 21. Pairwise overlap

| Primary pair ranks | Shared players | Same structural thesis |
| --- | --- | --- |
| (2, 3) | 4 | False |
| (2, 35) | 4 | False |
| (3, 35) | 4 | False |

Primary average overlap 4.00/6; CPT count 3, thesis count 3. Within-thesis average N/A because all three labels differ. Ten average 4.38/6, within-thesis 4.78/6, across-thesis 4.11/6; CPT count 5, thesis count 3. Full pair rows and allocation counts are saved in `audit_tables.json`. Overlap is a dependence diagnostic, not a measured fantasy-score correlation.

## 22. Remaining uncertainty

The imported DK file is not a fresh live verification. Final inactives/elevations are outstanding. Defensive back health and CLE center replacement affect the plausibility of passing/control theses but lack quantified incremental adjustments. Backup/rookie role tags and salary-fallback opportunity can overstate certainty. Ownership is unsuitable for promotion. The search is broad but does not certify global selector optimality, and existing hard QB/opportunity gates define its universe. Conditional models are heuristic, not joint-score simulations. No contest field, fee/payout metadata or payout simulation was supplied, so the three outputs are prospective shadows rather than expected-profit recommendations.

Tomorrow: capture new immutable official reports/transactions and market/weather snapshots; import a fresh DK salary file; reconcile actives/elevations/starters against canonical IDs; refresh normal context/features/projection; use reliable ownership only when coverage, slot marginals and calibration support it; create a **new** freeze/output path, then re-run the same discovery and joint constraints. Review changes in thesis/CPT depth and make the final three-entry decision. Retain tonight's files; do not overwrite freezes. Do not run the archived one-off preparation scripts blindly—they are provenance, not an automatic news parser. No automation or entry submission was scheduled.

## 23. Files changed

Primary report `WEEK4_THURSDAY_SHOWDOWN_PRELOCK_AUDIT.md`; new offline scripts `freeze_showdown_prelock.py`, `research_showdown_prelock.py`, `replay_showdown_single_entry_control.py`, `finalize_showdown_prelock_shadow.py`, `render_showdown_prelock_audit.py`; new focused research tests and one corrected existing multiple-TE contract test; small README/release-note references. Artifacts contain original/fresh database freezes, immutable public/DK sources, prepared pool, exact baseline LP, full raw universes, original production control, quality/thesis shadows, CSV coverage and rule audits, logs and preservation verification.

Local data refresh resolved two salary aliases, appended source/context/market/injury lineage, rebuilt only Thursday features and produced new Thursday projection/ownership runs through existing services. No optimizer run, export or entry was persisted. Production optimizer, projection/selector/correlation/CPT-prior/thesis code and configuration are unchanged; Classic report/research remain in place. The unchanged 30-candidate control selects A/B/A, all Metcalf CPT, showing why it does not implement the requested three-captain decision.

Reproduction (from repo root, with a new output path):

```sh
PYTHONPATH=. .venv/bin/python scripts/research_showdown_prelock.py <hashed-freeze.json> <new-directory>/discovery_v1.json
PYTHONPATH=. .venv/bin/python scripts/replay_showdown_single_entry_control.py <hashed-freeze.json> <new-directory>/production_single_entry_control.json
PYTHONPATH=. .venv/bin/python scripts/finalize_showdown_prelock_shadow.py <new-directory> <new-directory>/quality_shadow.json
```

The finalizer expects the freeze/control files under the same documented names. The ten-thesis sensitivity and final report are evidence-derived supplements, not an entry API. The archived preparation/refresh scripts document today's source reconciliation; they are not production integration changes.

## 24. Tests

**159 passed**: 92 optimizer/Showdown, captain, portfolio, scenario, starter, safety, pregame, readiness, ownership and research tests; 67 input-lineage, canonical projection, forward-opportunity, source-capture and matching tests. New tests verify hash failure, canonical/slot/salary/status legality, captured-model agreement with production, uniformly unavailable diagnostic ownership, same-core CPT/thesis distinction and joint core/captain constraints.

The initial run found one pre-existing stale test expecting the old one-TE restriction. The test now verifies the current schema forces `enforce_single_te=false`, multiple-TE candidates survive selection and final validation, and the production implementation was not changed.

All 769 full-universe lineups were independently checked for legal slots, salary, canonical uniqueness, team representation and frozen availability; all 23 retained players have both CPT/FLEX coverage. Conditional rosters were re-solved on the baseline model. Source hashes and freeze hashes are checked before analysis. Protected code/report/artifact hashes: True; 75 saved Classic objective/constraint configurations unchanged; Thursday persisted optimizer runs 0. No actual results were queried or attached for this future slate. See test logs and `production_preservation_verified.json`.

### What are the strongest football theses for PIT-CLE?

Balanced dual-QB competition; PIT passing concentration with Warren support; CLE passing concentration with a PIT bring-back. These are the three supported primary structural alternatives. Pure RB+DST control and defensive/kicking families are weaker on the current selector.

### Which captains are genuinely viable?

DK Metcalf, Deshaun Watson, Aaron Rodgers, Denzel Boston, Jaylen Warren, Jerry Jeudy, Michael Pittman Jr., Pat Freiermuth, Quinshon Judkins, KC Concepcion Jr., Roman Wilson. These have best-found depth within .05. Treat lower-cost WRs/TEs, kickers and defensive CPTs farther down the frontier as conditional alternatives; do not equate .30 coverage with a primary recommendation.

### Which three captains would you use if entering exactly three lineups?

DK Metcalf, Deshaun Watson, Jerry Jeudy, subject to tomorrow’s fresh inputs. Watson is mobile under the existing five-carries evidence rule; Rodgers is not selected in the primary three.

### What three lineups would the current system select?

The **unchanged production single-entry control** selects A/B/A and only Metcalf CPT:

1. **CPT DK Metcalf** ($13,500, PIT); **FLEX Deshaun Watson** ($9,400, CLE); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX Aaron Rodgers** ($9,800, PIT); **FLEX Jaylen Warren** ($9,600, PIT); **FLEX Roman Wilson** ($4,000, PIT)

2. **CPT DK Metcalf** ($13,500, PIT); **FLEX Denzel Boston** ($8,000, CLE); **FLEX Deshaun Watson** ($9,400, CLE); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX Aaron Rodgers** ($9,800, PIT); **FLEX Pat Freiermuth** ($5,600, PIT)

3. **CPT DK Metcalf** ($13,500, PIT); **FLEX Deshaun Watson** ($9,400, CLE); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX Aaron Rodgers** ($9,800, PIT); **FLEX Jaylen Warren** ($9,600, PIT); **FLEX Roman Wilson** ($4,000, PIT)

The **requested expanded joint shadow** selects three distinct captains and structurally different cores:

A. **CPT DK Metcalf** ($13,500, PIT); **FLEX Deshaun Watson** ($9,400, CLE); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX Aaron Rodgers** ($9,800, PIT); **FLEX Jaylen Warren** ($9,600, PIT); **FLEX Roman Wilson** ($4,000, PIT)

B. **CPT Deshaun Watson** ($14,100, CLE); **FLEX Denzel Boston** ($8,000, CLE); **FLEX Jerry Jeudy** ($3,000, CLE); **FLEX Aaron Rodgers** ($9,800, PIT); **FLEX DK Metcalf** ($9,000, PIT); **FLEX Pat Freiermuth** ($5,600, PIT)

C. **CPT Jerry Jeudy** ($4,500, CLE); **FLEX Denzel Boston** ($8,000, CLE); **FLEX Deshaun Watson** ($9,400, CLE); **FLEX Quinshon Judkins** ($8,800, CLE); **FLEX DK Metcalf** ($9,000, PIT); **FLEX Jaylen Warren** ($9,600, PIT)

### What thesis does each lineup represent?

A: PIT passing concentration (4 PIT/2 CLE); B: balanced competitive (3 PIT/3 CLE); C: CLE passing concentration (2 PIT/4 CLE). The labels describe allocations and actual stacks, not independent simulated outcomes.

### What is the quality cost of using three different captains?

Captain uniqueness alone sacrifices 0.01139 total selector points versus the best three distinct rosters, but rotates the same core. Requiring three supported theses and ≤4 overlap costs 0.03900 (1.41%). Versus repeating the best roster three times: 1.74%. No monetary EV inference.

### Does PIT-wins-big deserve one of the three entries?

**YES, through the competitive 4–2 PIT pass-led variant.** It is the strongest conditional PIT candidate and the primary A roster, only 0.00444 below the baseline frontier. No extra low-quality 5–1 or RB+DST roster is forced; the lineup also works in closer games.

### Does CLE-wins-big deserve one of the three entries?

**BORDERLINE as a dedicated 14+ blowout bet.** The closest competitive CLE-dominant variant costs 0.02267, while the conditionally top Boston 5–1 costs 0.07515. Primary C provides a CLE-concentrated alternate with three different captains/cores, without declaring a 14-point win likely. Avoid forcing the more expensive pure-blowout variant.

### Are any non-rushing QB CPTs justified?

**BORDERLINE.** Rodgers is mathematically close but captain-only rotation adds no game-thesis diversity and costs salary flexibility. Keep him out of the primary three. The ten-entry sensitivity reserves one explicit Rodgers CPT test. Watson’s five lagged carries/game classify him as mobile, so his primary CPT does not rely on casually accepting a non-rushing QB.

### Which questionable or fragile players need monitoring tomorrow?

Ramsey/Echols actives and PIT secondary alignment; CLE center replacement/line status; both QB starters; Warren/Homer and any Nichols elevation; Bernard/Heidenreich/McLaughlin roles. Confirm Dowdle/Wallace remain OUT and watch any new offensive Q designation. Preserve model assessments when applying user risk limits.

### Which cheap players require special scrutiny?

McLaughlin ($400), Bernard ($3,200), Heidenreich ($2,200), Homer ($2,600), Whiteheart ($1,600), and any newly activated minimum-salary player. Jeudy ($3,000) has stronger snap evidence but his 3/3 primary dependence and target expectations must be rechecked. Do not buy a PS/inactive punt or treat return duty as an established receiving role.

### If entering 10 lineups, what CPT allocation does the slate support?

DK Metcalf: 5, Deshaun Watson: 1, Aaron Rodgers: 1, Denzel Boston: 2, Roman Wilson: 1. This is generated from current quality/depth and retained exposure ceilings. It covers three structural theses at an incremental 0.059% selector cost; both QBs remain 10/10 and the portfolio is not independent.

### What must be refreshed again tomorrow before lock?

Fresh DK salary/slot IDs; official injuries, inactives and elevations; starters/depth and credible opportunity news; reliable slot-specific ownership; total/spread/implied scoring; weather. Rebuild normal context/features/projections, freeze a new hashed input, repeat discovery/selection, and review all three full rosters. Tonight is not ENTRY READY. No export or entry has been authorized or performed.
