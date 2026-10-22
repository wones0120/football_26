# Broader full-game generation and frozen top-decile selector comparison

**Completed public app research replay; no live promotion.** Generation now explores materially different complete-game outcomes. The pool doubled from 38 to 76 distinct canonical rosters, including 12 with no Rams offense. Two newly available rosters reached the observed contest top decile, versus zero in the old 38. None of the four frozen selectors chose them. This is a demonstrated coverage gain on this retrospective slate, and a remaining selection problem—not evidence that the top-decile model is ready to recommend entries.

Final corrected replay: `941f74f4c02d56b76dc73133613b89d00eda832949168ea94ca470f1ddd59a75`. Decision artifact digest `41a4a694dca86cd17932efdccb7dc9268e275728399d963b7005d5563667706a`; saved 2026-10-19T03:24:58.124137+00:00. Settings digest `3525d348bcbea80dfba7c2041946b03e06769e01766a5e138a9ceaf14bd0920f`. Source optimizer 398efe88-a871-47fa-a4f1-4d3e9924a825, original projection c8869a96-440c-4c36-aead-3614d6ef4d97. Original stored decision 2026-10-17T03:52:23.077047Z; player-data cutoff 2026-10-16T14:58:29.446687Z. Original saved/entered lineups remain unchanged. Research rosters have no optimizer-run/save/export/entry clearance.

## Frozen design and football mechanism

Protocol and source/model hashes were saved before new generation. The predeclared budget was 38 joint states: 8 seeded market/QB-style analog draws, plus one favored-team stalled-drive, low-pace and productive-two-sided stress for each of the 10 games. Every game receives the same stress treatment. No Rams/player penalty, new cap, mean floor, forced stack, player projection change or outcome-directed retry was added. Each state gets one frozen-legal-model solve, maximizing the score of that whole physical state. Final 38/38 solves were Optimal, with 38 distinct new rosters; adding 41 old source variants gives 79 variants/76 distinct rosters. Different names alone are not the breadth measure.

Historical source: 85 complete 2025 paired games, with immutable source SHA lineage and capture by October 13 before the frozen W6 decision. The larger 208-game draft was narrowed to require native active-role evidence: 121 leading-role inactive/unknown cases, 11 passing/receiving reconciliation failures, 6 ambiguous active identities and 1 missing active event actor were excluded. Those counts are rejection classifications, not empirical event probabilities. The revised historical statistics are not contemporaneous 2025 receipts. The library conditions strongly on healthy leading roles and has selection bias.

Match context uses only original total, spread and recorded QB rushing proxies; retain 40 nearest analogs, with distances/support in the artifact. Rams 51.5 total/+12.5 home margin has nearest squared standardized distance 1.71 and effective kernel support 17.2; BUF–LV effective support 7.8. Those are analog-design diagnostics, not probabilities or effective independent future samples. Game scores, possessions/plays, pass/rush vectors, receiving and TD outcomes remain paired. Full 513-player role universe preserves user-excluded but model-available players; the legal 137-player pool is unchanged. Preceding historical role rank maps to current recorded workload rank; unmapped roles/backup passers remain anonymous residuals. No user exclusion transfers volume.

Passing/receiving yards, completions and TDs reconcile. DK scoring retains negative points, yardage bonuses and typed fumble categories; corrected DST comes from full PBP events. Receiving rank never grants return duties: unverified return TDs remain anonymous. Source zero-stat active players require native identity, positive snaps and no relevant complete event; missing eligible workload fails closed. Extra current role holders can realize zero in a complete conditional game, which is not an expected zero. Frozen starting-QB assumptions—including uncertain/Q-excluded players—remain explicit; this does not reverify health or transfer volume to backups.

A useful contrast: the Rams-stall state transports Cincinnati’s real 0-point,71-play game versus Baltimore 24. It still preserves 26.2 DK points for the mapped leading WR and 16 for the leading RB. It does not suppress legitimate individual upside because the team stalls. The maximizing full roster nevertheless buys different games: $47,500, mean 95.246, Gadsden/Hubbard/London/Skattebo/Garrett Wilson/Stevenson/Tucker/Winston/Cardinals. The alternatives must overcome that large baseline-mean cost; a dramatic stress result is not proof of likelihood.

## Same-pool selector comparison

All comparators use the same 76 canonical rosters and the unchanged requested 5, 80% player cap, overlap 5, single TE, max 3/team and 4/game, original exclusions/floors and existing 60% receiving-pair/shared-triple policy. Actual checks pass: each portfolio has 5 unique legal rosters, max 4 player appearances, overlap≤5, triples≤3 and receiving pairs≤3. No relaxation. Legacy additionally retains its inherent story construction/fallback policy; those are part of the policy being compared, not newly imposed user constraints.

The true old policy allocated story slots before an ILP per slot. Its finite-pool adaptation keeps planned slot/fallback order, mean+0.35 summed marginal P90 spread objective, structural audits, sequential exposures/minimums and existing dependence controls. Original ordered 5 are reproduced exactly before generation. A finite pool replaces original search; challenger/teammate generation stages are not rerun as if they were selection. The earlier ordinal-coverage research selector is not called the old selector. Highest-mean preserves the genuine baseline objective. Core/rich models remain frozen trainW1–5, with original player moments/features; no Week 6 fit or retuning.

| Policy | Original 38 summed mean | Broader 76 summed mean | Changed canonical selections | Top-decile hits old → broad | Rams offense |
|---|---:|---:|---:|---:|---:|
| legacy_sequential_adapted | 643.650 | 643.650 | 0/5 | 0 → 0 | 5/5 |
| highest_mean | 647.612 | 647.612 | 0/5 | 0 → 0 | 5/5 |
| top10_core | 637.219 | 617.397 | 2/5 | 0 → 0 | 5/5 |
| top10_rich | 636.841 | 636.841 | 0/5 | 0 → 0 | 5/5 |

All achieve 5/5: legacy finite_pool_complete; other three Optimal. The old, mean and rich choices remain unchanged. Core chooses two new rosters, spending 19.822 baseline mean relative to its own old-pool portfolio and 26.253 relative to legacy. The new core portfolio still uses Rams offense 5/5. It increases NO–NYG exposure to 3/5 and offers a different CAR/NYG/LV path in one roster, but does not solve shared Rams failure. Rich still depends on PIT–TB 5/5 and Rams 5/5; old depends on TEN–IND, PIT–TB and Rams in all five.

As conditional sensitivity only, average best-selected score over the 38 designed states is 129.57 old, 131.27 mean, 139.60 core and 133.12 rich; minimum best-selected state score 83.88/79.54/90.94/85.14. These deliberately stressed, generation-reused worlds are not a calibrated distribution, expected score, P90, independent validation or evidence of model superiority.

## Actual outcomes appended after decisions froze

The final immutable decision artifact and receipt precede the separate evaluation. All 76 rosters are canonically scoreable from observed Main contest 196653899 player scores; the field’s 150.20 top-decile boundary includes ties. Old 38 has 0 positive rosters; broader 76 has 2(best 170.58), and a separately labeled post-decision label oracle confirms both can fit a legal five-entry portfolio. The oracle is only a coverage ceiling, never a recommendation. Old, mean, core and rich attain 0/5. All 2026 Weeks 1–6 outcomes had been inspected previously: this is retrospective temporal research, not fresh blind validation or causal evidence of a better policy.

The two newly covered rosters have baseline means 103.35 and 96.85, well below normal selected means. Frozen core assigns research scores 0.0354/0.0083; rich 0.0289/0.0070, versus selected minima 0.0959/0.1412. These are uncalibrated classification propensities, not cash/win probabilities. Both fit the old CAR run-control construction, so their rejection is not simply absence or universal structural ineligibility: objective/ranking plus sequential allocation matters. Do not tune features or weights now to reward their known outcome.

## Complete broader-pool selections

### legacy_sequential_adapted
#### Roster 1 · **$50,000 · baseline mean 133.483** · observed actual 101.18
RB Chuba Hubbard (CAR, $6,300, mean 14.51); TE Cade Otton (TB, $3,300, mean 8.39); QB Matthew Stafford (LAR, $6,400, mean 24.93); RB Kyren Williams (LAR, $6,800, mean 19.91); DST Panthers (CAR, $2,500, mean 6.60); WR Puka Nacua (LAR, $8,100, mean 22.15); WR Carnell Tate (TEN, $5,000, mean 11.14); WR Michael Wilson (ARI, $6,700, mean 14.36); WR Rome Odunze (CHI, $4,900, mean 11.50).

#### Roster 2 · **$49,900 · baseline mean 129.010** · observed actual 97.82
TE Cade Otton (TB, $3,300, mean 8.39); RB Kyren Williams (LAR, $6,800, mean 19.91); RB Kenneth Walker III (KC, $8,500, mean 19.22); DST Panthers (CAR, $2,500, mean 6.60); WR Laquon Treadwell (IND, $3,300, mean 5.55); WR Puka Nacua (LAR, $8,100, mean 22.15); WR Rome Odunze (CHI, $4,900, mean 11.50); RB Jaylen Warren (PIT, $7,000, mean 15.06); QB Aaron Rodgers (PIT, $5,500, mean 20.63).

#### Roster 3 · **$50,000 · baseline mean 130.994** · observed actual 89.14
RB Chuba Hubbard (CAR, $6,300, mean 14.51); TE Cade Otton (TB, $3,300, mean 8.39); RB Kyren Williams (LAR, $6,800, mean 19.91); RB Derrick Henry (BAL, $8,200, mean 19.03); QB Bryce Young (CAR, $5,700, mean 20.25); DST Jets (NYJ, $2,200, mean 4.91); WR Puka Nacua (LAR, $8,100, mean 22.15); WR Wan'Dale Robinson (TEN, $4,500, mean 10.35); WR Rome Odunze (CHI, $4,900, mean 11.50).

#### Roster 4 · **$49,900 · baseline mean 126.198** · observed actual 134.80
RB Chuba Hubbard (CAR, $6,300, mean 14.51); TE Michael Mayer (LV, $3,200, mean 6.95); RB Kyren Williams (LAR, $6,800, mean 19.91); DST Panthers (CAR, $2,500, mean 6.60); WR Puka Nacua (LAR, $8,100, mean 22.15); WR Carnell Tate (TEN, $5,000, mean 11.14); QB Josh Allen (BUF, $7,500, mean 26.10); WR Khalil Shakir (BUF, $5,300, mean 8.08); WR Emeka Egbuka (TB, $5,200, mean 10.76).

#### Roster 5 · **$49,900 · baseline mean 123.966** · observed actual 119.98
RB Jonathan Taylor (IND, $8,000, mean 15.60); RB Chuba Hubbard (CAR, $6,300, mean 14.51); QB Matthew Stafford (LAR, $6,400, mean 24.93); RB Derrick Henry (BAL, $8,200, mean 19.03); DST Panthers (CAR, $2,500, mean 6.60); WR Carnell Tate (TEN, $5,000, mean 11.14); TE Tyler Higbee (LAR, $3,400, mean 9.91); WR Rome Odunze (CHI, $4,900, mean 11.50); WR Emeka Egbuka (TB, $5,200, mean 10.76).


### highest_mean
#### Roster 1 · **$50,000 · baseline mean 125.822** · observed actual 133.98
RB Ashton Jeanty (LV, $6,500, mean 14.57); RB Chuba Hubbard (CAR, $6,300, mean 14.51); TE Cade Otton (TB, $3,300, mean 8.39); QB Matthew Stafford (LAR, $6,400, mean 24.93); DST Panthers (CAR, $2,500, mean 6.60); RB D'Andre Swift (CHI, $6,700, mean 12.77); WR Puka Nacua (LAR, $8,100, mean 22.15); WR Carnell Tate (TEN, $5,000, mean 11.14); WR Emeka Egbuka (TB, $5,200, mean 10.76).

#### Roster 2 · **$50,000 · baseline mean 128.623** · observed actual 130.88
TE Cade Otton (TB, $3,300, mean 8.39); QB Matthew Stafford (LAR, $6,400, mean 24.93); RB Kyren Williams (LAR, $6,800, mean 19.91); RB Kenneth Walker III (KC, $8,500, mean 19.22); DST Panthers (CAR, $2,500, mean 6.60); RB James Cook III (BUF, $7,400, mean 16.18); WR Carnell Tate (TEN, $5,000, mean 11.14); WR Rome Odunze (CHI, $4,900, mean 11.50); WR Emeka Egbuka (TB, $5,200, mean 10.76).

#### Roster 3 · **$50,000 · baseline mean 130.994** · observed actual 89.14
RB Chuba Hubbard (CAR, $6,300, mean 14.51); TE Cade Otton (TB, $3,300, mean 8.39); RB Kyren Williams (LAR, $6,800, mean 19.91); RB Derrick Henry (BAL, $8,200, mean 19.03); QB Bryce Young (CAR, $5,700, mean 20.25); DST Jets (NYJ, $2,200, mean 4.91); WR Puka Nacua (LAR, $8,100, mean 22.15); WR Wan'Dale Robinson (TEN, $4,500, mean 10.35); WR Rome Odunze (CHI, $4,900, mean 11.50).

#### Roster 4 · **$50,000 · baseline mean 132.374** · observed actual 106.18
RB Chuba Hubbard (CAR, $6,300, mean 14.51); TE Cade Otton (TB, $3,300, mean 8.39); QB Matthew Stafford (LAR, $6,400, mean 24.93); RB Kyren Williams (LAR, $6,800, mean 19.91); DST Browns (CLE, $2,500, mean 5.49); WR Puka Nacua (LAR, $8,100, mean 22.15); WR Carnell Tate (TEN, $5,000, mean 11.14); WR Michael Wilson (ARI, $6,700, mean 14.36); WR Rome Odunze (CHI, $4,900, mean 11.50).

#### Roster 5 · **$50,000 · baseline mean 129.799** · observed actual 111.62
RB Ashton Jeanty (LV, $6,500, mean 14.57); RB Chuba Hubbard (CAR, $6,300, mean 14.51); RB Kyren Williams (LAR, $6,800, mean 19.91); DST Panthers (CAR, $2,500, mean 6.60); WR Puka Nacua (LAR, $8,100, mean 22.15); WR Carnell Tate (TEN, $5,000, mean 11.14); TE Pat Freiermuth (PIT, $4,400, mean 8.79); WR Rome Odunze (CHI, $4,900, mean 11.50); QB Aaron Rodgers (PIT, $5,500, mean 20.63).


### top10_core
#### Roster 1 · **$49,900 · baseline mean 126.278** · observed actual 124.26
RB Chuba Hubbard (CAR, $6,300, mean 14.51); RB Kyren Williams (LAR, $6,800, mean 19.91); QB Tyler Shough (NO, $5,600, mean 18.65); DST Panthers (CAR, $2,500, mean 6.60); WR Puka Nacua (LAR, $8,100, mean 22.15); WR Malik Nabers (NYG, $6,500, mean 13.45); WR Devaughn Vele (NO, $5,100, mean 10.67); TE Harold Fannin Jr. (CLE, $4,100, mean 8.85); WR Rome Odunze (CHI, $4,900, mean 11.50).

#### Roster 2 · **$49,900 · baseline mean 127.929** · observed actual 86.78
TE Cade Otton (TB, $3,300, mean 8.39); RB Kyren Williams (LAR, $6,800, mean 19.91); QB Patrick Mahomes (KC, $6,500, mean 20.39); RB Derrick Henry (BAL, $8,200, mean 19.03); DST Panthers (CAR, $2,500, mean 6.60); WR Puka Nacua (LAR, $8,100, mean 22.15); WR Carnell Tate (TEN, $5,000, mean 11.14); WR Xavier Worthy (KC, $4,600, mean 8.83); WR Rome Odunze (CHI, $4,900, mean 11.50).

#### Roster 3 · **$50,000 · baseline mean 125.895** · observed actual 130.22
TE Cade Otton (TB, $3,300, mean 8.39); RB Kyren Williams (LAR, $6,800, mean 19.91); RB Kenneth Walker III (KC, $8,500, mean 19.22); DST Panthers (CAR, $2,500, mean 6.60); WR Carnell Tate (TEN, $5,000, mean 11.14); WR Malik Nabers (NYG, $6,500, mean 13.45); WR Rome Odunze (CHI, $4,900, mean 11.50); RB Jaylen Warren (PIT, $7,000, mean 15.06); QB Aaron Rodgers (PIT, $5,500, mean 20.63).

#### Roster 4 · **$50,000 · baseline mean 126.204** · observed actual 108.42
RB Chuba Hubbard (CAR, $6,300, mean 14.51); TE Darnell Washington (PIT, $2,900, mean 5.59); RB Derrick Henry (BAL, $8,200, mean 19.03); DST Panthers (CAR, $2,500, mean 6.60); WR Davante Adams (LAR, $6,600, mean 15.06); WR Puka Nacua (LAR, $8,100, mean 22.15); WR Carnell Tate (TEN, $5,000, mean 11.14); WR Rome Odunze (CHI, $4,900, mean 11.50); QB Aaron Rodgers (PIT, $5,500, mean 20.63).

#### Roster 5 · **$49,300 · baseline mean 111.091** · observed actual 102.04
RB Bijan Robinson (ATL, $8,700, mean 18.23); RB Kyren Williams (LAR, $6,800, mean 19.91); WR Tetairoa McMillan (CAR, $7,300, mean 14.52); RB Cam Skattebo (NYG, $5,800, mean 11.39); DST Giants (NYG, $2,800, mean 5.26); QB Bryce Young (CAR, $5,700, mean 20.25); WR John Metchie III (CAR, $3,200, mean 4.37); TE Colston Loveland (CHI, $4,300, mean 9.61); WR Tre Tucker (LV, $4,700, mean 7.55).


### top10_rich
#### Roster 1 · **$49,800 · baseline mean 126.375** · observed actual 111.46
TE Cade Otton (TB, $3,300, mean 8.39); RB Kyren Williams (LAR, $6,800, mean 19.91); QB Tyler Shough (NO, $5,600, mean 18.65); DST Panthers (CAR, $2,500, mean 6.60); WR Puka Nacua (LAR, $8,100, mean 22.15); WR Malik Nabers (NYG, $6,500, mean 13.45); WR Devaughn Vele (NO, $5,100, mean 10.67); WR Rome Odunze (CHI, $4,900, mean 11.50); RB Jaylen Warren (PIT, $7,000, mean 15.06).

#### Roster 2 · **$49,900 · baseline mean 127.929** · observed actual 86.78
TE Cade Otton (TB, $3,300, mean 8.39); RB Kyren Williams (LAR, $6,800, mean 19.91); QB Patrick Mahomes (KC, $6,500, mean 20.39); RB Derrick Henry (BAL, $8,200, mean 19.03); DST Panthers (CAR, $2,500, mean 6.60); WR Puka Nacua (LAR, $8,100, mean 22.15); WR Carnell Tate (TEN, $5,000, mean 11.14); WR Xavier Worthy (KC, $4,600, mean 8.83); WR Rome Odunze (CHI, $4,900, mean 11.50).

#### Roster 3 · **$50,000 · baseline mean 132.374** · observed actual 106.18
RB Chuba Hubbard (CAR, $6,300, mean 14.51); TE Cade Otton (TB, $3,300, mean 8.39); QB Matthew Stafford (LAR, $6,400, mean 24.93); RB Kyren Williams (LAR, $6,800, mean 19.91); DST Browns (CLE, $2,500, mean 5.49); WR Puka Nacua (LAR, $8,100, mean 22.15); WR Carnell Tate (TEN, $5,000, mean 11.14); WR Michael Wilson (ARI, $6,700, mean 14.36); WR Rome Odunze (CHI, $4,900, mean 11.50).

#### Roster 4 · **$49,900 · baseline mean 126.198** · observed actual 134.80
RB Chuba Hubbard (CAR, $6,300, mean 14.51); TE Michael Mayer (LV, $3,200, mean 6.95); RB Kyren Williams (LAR, $6,800, mean 19.91); DST Panthers (CAR, $2,500, mean 6.60); WR Puka Nacua (LAR, $8,100, mean 22.15); WR Carnell Tate (TEN, $5,000, mean 11.14); QB Josh Allen (BUF, $7,500, mean 26.10); WR Khalil Shakir (BUF, $5,300, mean 8.08); WR Emeka Egbuka (TB, $5,200, mean 10.76).

#### Roster 5 · **$49,900 · baseline mean 123.966** · observed actual 119.98
RB Jonathan Taylor (IND, $8,000, mean 15.60); RB Chuba Hubbard (CAR, $6,300, mean 14.51); QB Matthew Stafford (LAR, $6,400, mean 24.93); RB Derrick Henry (BAL, $8,200, mean 19.03); DST Panthers (CAR, $2,500, mean 6.60); WR Carnell Tate (TEN, $5,000, mean 11.14); TE Tyler Higbee (LAR, $3,400, mean 9.91); WR Rome Odunze (CHI, $4,900, mean 11.50); WR Emeka Egbuka (TB, $5,200, mean 10.76).

## Football review of the full portfolios

Legacy#1 buys the strongest baseline 133.48 and connects Stafford/Puka with Kyren plus Wilson’s response. Kyren and Puka can both succeed through sustained drives and complementary scoring, but stalled Rams TD conversion hurts multiple entries. Other slots change the named leading game (KCrun, BALrun, BUFpassing, INDrun), while repeatedly buying Puka/Kyren, Carolina savings, Tate and Odunze. This explains why distinct stories did not create distinct full-roster failure paths.

Highest mean is a valid expected-score control: its unchanged selection is rational for that objective. It does not price tournament tails or failure concentration. Its five rosters continue cheap Otton/Tate/Odunze/Carolina support and Rams exposure; a higher sum of means says nothing about calibrated contest success probability.

Core#1 uses Shough/Vele with Nabers returning production, and Fannin provides a different midrange support route. Core#5 uses Bryce/McMillan, receiving support from Metchie, Skattebo as a separate rushing engine, Bijan, Loveland and Tucker with Giants DST. That is a real alternate full-roster opportunity path and saves $700, but drops baseline mean to 111.09. It still spends on Kyren, so all five remain tied to some Rams production. Several receiver/TE supports require unusually concentrated scoring/volume; current evidence does not establish those expansions as expected. The model’s choice is a diagnostic, not a hand-picked endorsement.

Rich’s recorded workload/context features keep its prior five, retaining the same Rams/PIT–TB risk. Its Shough/Nabers/Vele, Mahomes/Worthy, Stafford/Puka/Wilson and Allen/Shakir combinations have coherent passing-response paths, with different Henry/Taylor/Chuba rushing supports. Reusing cheap receiving cores across entries means those alternatives do not diversify all important dependencies. Both learned variants have mixed earlier temporal metrics and few independent slates; no live promotion is justified.

### Newly covered top-decile rosters — hindsight diagnostics only
#### Roster 1 · **$48,300 · baseline mean 103.349** · observed actual 156.58
TE Oronde Gadsden II (LAC, $3,800, mean 4.56); RB Chuba Hubbard (CAR, $6,300, mean 14.51); QB Patrick Mahomes (KC, $6,500, mean 20.39); WR Luther Burden III (CHI, $5,400, mean 11.35); RB Kenneth Walker III (KC, $8,500, mean 19.22); WR Chris Godwin Jr. (TB, $4,400, mean 7.42); DST Jets (NYJ, $2,200, mean 4.91); WR Tre Tucker (LV, $4,700, mean 7.55); WR Malik Nabers (NYG, $6,500, mean 13.45).

#### Roster 2 · **$46,200 · baseline mean 96.848** · observed actual 170.58
TE Dallas Goedert (PHI, $3,900, mean 7.39); RB Chuba Hubbard (CAR, $6,300, mean 14.51); QB Patrick Mahomes (KC, $6,500, mean 20.39); RB Kenneth Walker III (KC, $8,500, mean 19.22); WR Germie Bernard (PIT, $4,000, mean 5.99); RB Cam Skattebo (NYG, $5,800, mean 11.39); WR DeMario Douglas (NE, $4,200, mean 5.80); DST Titans (TEN, $2,300, mean 4.61); WR Tre Tucker (LV, $4,700, mean 7.55).

The first combines KC production through Mahomes/Walker with Gadsden’s opposing receiving response, Nabers, Chicago receiving production and Godwin/Tucker salary savings, while Jets DST profits from stalled NE. The second combines Mahomes/Walker’s shared passing/rushing scoring, Hubbard/Goedert across CAR–PHI, Skattebo’s rushing/receiving route, Douglas/Bernard/Tucker savings and Titans DST against stalled IND. They have four shared players but can coexist under the unchanged limits. Neither needs Rams success. A favorite failing in one game allows other games to supply the roster score; there is no team penalty.

Material football limit: rank transport alone can give Gadsden a 13-target/134-yard/2 TD historical TE realization despite a 2.37 recorded target proxy, or Goedert 11 targets despite 2.86. These are conditional tails with unknown likelihood, not verified role expansions or supported expected workloads. Cheap players’ concentration and cross-season role transport need calibration before such candidates are normal recommendations. More physical accounting does not make the probability model valid. No Captain workload rule was changed.

## Acceptance, lineage and next evidence

Actual Chrome app: Analyst Reports → frozen research replay → source 398efe88 → Build full-game and top-decile comparison → completed → saved comparison 941f74f4c02d reselected/reopened. Public GET integrity validates decision and full actor-state evidence. Artifact is research-only/no entry clearance; saved operational 398efe88 and Monday 3cefbcab remain untouched. Screenshot app_acceptance.png. The report catalog exposes this review; reading applies no changes.

A first public draft 413eeeb1edc8 was rejected during mechanism review before any actual-score evaluation: receiving rank had improperly transported historical return TDs. The narrow correction keeps these events residual; a targeted test covers it. That first draft is preserved and not recommended. Its canonical rosters and selected portfolios happened to be unchanged after correction; joint scores/accounting differ. There were 38 solves per version, 76 total across the mechanism repair; no outcome-driven retry.

Targeted backend tests and UI TypeScript/Vite build passed; existing bundle-size advisory remains. Original-five reproduction and actual-pool constraint checks pass. Before each necessary managed backend reload, running and queued job lists were empty. No jobs interrupted, new model training, browser downloads, contest submissions or lineup DB writes occurred.

Next is validation, not promotion: test rank transport and workload/TD-tail support on chronological source-only cohorts, then compare selectors over additional frozen pools without choosing settings to reward these two known W6 rosters. Separate workload/efficiency/TD and information-delivery projection diagnosis remains queued. The broad search now supplies alternatives that the old search missed; a materially better selector has not yet been demonstrated.

Artifacts: PROTOCOL.md; inputs_manifest.json; historical_templates_v2.json; frozen_predictor_inputs.json; decision_receipt.json; evaluation.json; evaluation_v2.json (adds a label-oracle ceiling with parent digest); final public decision and .states.json under artifacts/full_game_breadth_replays. Original 38 control and the prior top-decile report remain unchanged. No strict original-code/source chronology certification is claimed.
