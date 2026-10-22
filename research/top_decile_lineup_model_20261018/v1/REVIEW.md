# Complete-lineup top-decile model — bounded prototype checkpoint

Implemented and trained: separate interpretable Classic and Showdown lineup models, with core and recorded-workload/game-context variants. **No live promotion:** retrospective results are mixed, independent slates are few, original source/code chronology is not fully certified, and the frozen38-roster Main pool has no observed top-decile lineup for any selector to choose. All entered/saved lineups, user settings and player projections remain unchanged.

## Data and labels

- 55 SHA-verified complete contest source files, 2,393,034 final observed entries. Label boundary is the score at ceil(10% × valid field entries) within each contest, including all ties at official DK cent precision; CSV floating noise does not split ties. Actuals are labels only. No ranks are merged across fields.
- 46 fields have usable original pregame inputs, covering2,033,053 observed entries and1,232,371 scoreable distinct canonical roster-contexts. Nine fields cannot train:7lack resolved native canonical source observations; Week3Thursday andWeek5SundayNight have no admissible same-slate pre-first-lock forecast. Exclusion remains explicit. There is no Week2Classic field in this inventory.
- Bounded, label-independent SHA sample: at most5,000 canonical rosters per contest,152,543 sampled context rows and132,528 distinct roster/week/format identities across formats. Original complete field still determines labels. Scores of sampled field portfolios are not claims about the best five across the entire source field.
- Native salary row ID/source player key/format-slot/contest-source scope binds canonical identity; no raw-name-only join. Captain identity stays distinct. Training deduplicates canonical rosters; input-version variants share one total loss weight, contest-specific labels and entry multiplicity remain as provenance. A fractional Bernoulli target preserves disagreement when identical rosters fall on different contest decile boundaries. Multiplicity is never a predictor or training weight.
- Latest physically stored completed same-slate projection snapshot before the first contest kickoff; model, feature and salary creation clocks prelock. No postgame/current forecast fallback and no imputed player projections. Rich inputs use recorded historical workload/share proxies and game context, not calibrated target/carry forecasts. Their original source capture/code execution are not independently certified: this is a qualified stored-pregame retrospective prototype, not a strict source-verified backtest.
- Tiers and Single Stat remain separate: existing2026W6 Tiers5,945entries (five blank rosters), TD10entries, with distinct FP versus TD units. Canonical forecast origin/identity for those raw rosters is not sufficiently linked, and the independent sample is tiny. They were not pooled into this model.

## Model and validation contract

Fixed regularized logistic regression C=0.1, no hyperparameter search:2formats ×2feature sets ×3temporal folds =12small fits. Entire weeks, overlapping slates and games stay together. TrainW1–3/testW4; trainW1–4/testW5; trainW1–5/testW6. Scalers fit training only. Weeks1–6 outcomes had previously been inspected: temporal separation does not create fresh blind validation.

Core predictors are complete-lineup forecast mean, marginal spread summary (not jointP90), salary/forecast concentration and minima, canonical team/game roster dependencies, QB/receiver relationships and Captain role. Rich adds recorded workload concentration and pregame game context. These are learned associations, not mandatory stack rules or causal mechanisms. No actual score, final ownership, rank, player outcome, entry multiplicity, payout or winner identity is a predictor.

Earliest Classic fit has only2slate scopes despite20,795 canonical training rosters; earliest Showdown fit5game/slate scopes. Later Classic scopes overlap games. Large entry counts do not establish many independent football outcomes. Coefficients are collinear and unstable; no learned single-feature sign should become an eligibility rule.

## Retrospective fixed-five comparison on sampled field cohorts

AUC values below are unweighted averages over contest contexts; top-five hits aggregate context portfolios, which share games and sometimes rosters. They are not independent trials, not a direct old-optimizer benchmark and not operational recommendations under current user settings. The exact frozen candidate comparison follows separately.

| Format / features | Test week | Contests | Model AUC | Mean-rank AUC | Model hits / slots | Mean-rank hits / slots |
|---|---:|---:|---:|---:|---:|---:|
| classic / core | 4 | 4 | 0.545 | 0.530 | 1/20 | 6/20 |
| classic / core | 5 | 4 | 0.624 | 0.538 | 1/20 | 0/20 |
| classic / core | 6 | 1 | 0.577 | 0.481 | 1/5 | 0/5 |
| classic / rich | 4 | 4 | 0.546 | 0.530 | 1/20 | 6/20 |
| classic / rich | 5 | 4 | 0.645 | 0.538 | 2/20 | 0/20 |
| classic / rich | 6 | 1 | 0.552 | 0.481 | 1/5 | 0/5 |
| showdown / core | 4 | 11 | 0.481 | 0.529 | 4/55 | 4/55 |
| showdown / core | 5 | 8 | 0.534 | 0.559 | 2/40 | 3/40 |
| showdown / core | 6 | 2 | 0.630 | 0.728 | 2/10 | 4/10 |
| showdown / rich | 4 | 11 | 0.492 | 0.529 | 12/55 | 4/55 |
| showdown / rich | 5 | 8 | 0.494 | 0.559 | 9/40 | 3/40 |
| showdown / rich | 6 | 2 | 0.658 | 0.728 | 2/10 | 4/10 |

Rich Classic improves ranking on some tests, but loses the fixed-five comparison badly inWeek4. Rich Showdown finds more top-decile sample rosters inWeeks4–5, but loses to mean ranking inWeek6. Neither is a reliably superior selector.

## Calibration, without invented win probabilities

| Rich model | Week | Model Brier | Train-only constant-prevalence Brier |
|---|---:|---:|---:|
| classic | 4 | 0.1216 | 0.1156 |
| classic | 5 | 0.0731 | 0.0746 |
| classic | 6 | 0.0960 | 0.0953 |
| showdown | 4 | 0.0929 | 0.0906 |
| showdown | 5 | 0.0863 | 0.0831 |
| showdown | 6 | 0.0638 | 0.0648 |

The constant reference is often as good or better. Model scores are **uncalibrated sampled-context top-decile propensities**, not cash, paid-finish, win probabilities or ROI. Per-context reliability bins are retained in metrics.json; no confident forward calibration claim follows from these few slates.

## Exact frozen Main pool: generation ceiling versus selection

Source saved optimizer398efe88-a871-47fa-a4f1-4d3e9924a825; source research replay79c06be0698eb363eef557afe63bf3cd7b1ff3abc29f24a3fbee084575fb15d9; original projectionc8869a96-440c-4c36-aead-3614d6ef4d97; settings digest3525d348bcbea80dfba7c2041946b03e06769e01766a5e138a9ceaf14bd0920f.

Both models use frozen trainW1–5 coefficients, the exact original raw point-projection/feature run and native frozen salary/team/position. Its summed means equal the original prepared means for all original five controls. No projections are overwritten to inject model scores: the selector accepts a separately labeled complete-lineup utility. Same41candidate variants /38distinct canonical rosters, unchanged exposure/overlap/legal/allocation controls, original5and highest-mean control retained.

**None of38distinct candidates reaches the observed Main top-decile cutoff150.20.** Thus the maximum possible top-decile hits for any five from this pool is0, even ignoring portfolio conflicts. Original best actual134.80. Neither a new selector nor a more attractive story can select an absent top-decile candidate. This is a retrospective empirical coverage ceiling, not a target used for fitting/generating the pool.

| Policy on same38distinct pool | Selected | Baseline mean sum | Rams offense | Observed top-decile hits |
|---|---:|---:|---:|---:|
| Original saved / ordinal conditional | 5 | 643.650 | 5/5 | 0 |
| Highest baseline mean control | 5 | 647.612 | 5/5 | 0 |
| classic_core_train_before_w6 | 5 | 637.219 | 5/5 | 0 |
| classic_rich_train_before_w6 | 5 | 636.841 | 5/5 | 0 |

The two models preserve80%player exposure and5-player maximum overlap, solve5/5without relaxation, but spend~6.4–6.8baseline expected points versus the old portfolio and still retain Rams in every roster. This is not demonstrated football improvement. Highest-mean remains an explicit separate control. The saved operational recommendation is unchanged.

### classic_core_train_before_w6

#### Roster 1: $49,900; baseline mean 127.929

TE Cade Otton (TB, $3,300) / RB Kyren Williams (LAR, $6,800) / QB Patrick Mahomes (KC, $6,500) / RB Derrick Henry (BAL, $8,200) / DST Panthers (CAR, $2,500) / WR Puka Nacua (LAR, $8,100) / WR Carnell Tate (TEN, $5,000) / WR Xavier Worthy (KC, $4,600) / WR Rome Odunze (CHI, $4,900)

Research model score0.186 (uncalibrated). Actual86.78, appended only after selection. Primary generation path `2026_06_LAC_KC:KC:passing`.

#### Roster 2: $50,000; baseline mean 130.994

RB Chuba Hubbard (CAR, $6,300) / TE Cade Otton (TB, $3,300) / RB Kyren Williams (LAR, $6,800) / RB Derrick Henry (BAL, $8,200) / QB Bryce Young (CAR, $5,700) / DST Jets (NYJ, $2,200) / WR Puka Nacua (LAR, $8,100) / WR Wan'Dale Robinson (TEN, $4,500) / WR Rome Odunze (CHI, $4,900)

Research model score0.111 (uncalibrated). Actual89.14, appended only after selection. Primary generation path `2026_06_BAL_CLE:BAL:run_control`.

#### Roster 3: $50,000; baseline mean 125.895

TE Cade Otton (TB, $3,300) / RB Kyren Williams (LAR, $6,800) / RB Kenneth Walker III (KC, $8,500) / DST Panthers (CAR, $2,500) / WR Carnell Tate (TEN, $5,000) / WR Malik Nabers (NYG, $6,500) / WR Rome Odunze (CHI, $4,900) / RB Jaylen Warren (PIT, $7,000) / QB Aaron Rodgers (PIT, $5,500)

Research model score0.173 (uncalibrated). Actual130.22, appended only after selection. Primary generation path `2026_06_ARI_LA:LAR:run_control`.

#### Roster 4: $50,000; baseline mean 126.204

RB Chuba Hubbard (CAR, $6,300) / TE Darnell Washington (PIT, $2,900) / RB Derrick Henry (BAL, $8,200) / DST Panthers (CAR, $2,500) / WR Davante Adams (LAR, $6,600) / WR Puka Nacua (LAR, $8,100) / WR Carnell Tate (TEN, $5,000) / WR Rome Odunze (CHI, $4,900) / QB Aaron Rodgers (PIT, $5,500)

Research model score0.154 (uncalibrated). Actual108.42, appended only after selection. Primary generation path `2026_06_PIT_TB:PIT:passing`.

#### Roster 5: $49,900; baseline mean 126.198

RB Chuba Hubbard (CAR, $6,300) / TE Michael Mayer (LV, $3,200) / RB Kyren Williams (LAR, $6,800) / DST Panthers (CAR, $2,500) / WR Puka Nacua (LAR, $8,100) / WR Carnell Tate (TEN, $5,000) / QB Josh Allen (BUF, $7,500) / WR Khalil Shakir (BUF, $5,300) / WR Emeka Egbuka (TB, $5,200)

Research model score0.123 (uncalibrated). Actual134.80, appended only after selection. Primary generation path `2026_06_BUF_LV:BUF:passing`.

### classic_rich_train_before_w6

#### Roster 1: $49,800; baseline mean 126.375

TE Cade Otton (TB, $3,300) / RB Kyren Williams (LAR, $6,800) / QB Tyler Shough (NO, $5,600) / DST Panthers (CAR, $2,500) / WR Puka Nacua (LAR, $8,100) / WR Malik Nabers (NYG, $6,500) / WR Devaughn Vele (NO, $5,100) / WR Rome Odunze (CHI, $4,900) / RB Jaylen Warren (PIT, $7,000)

Research model score0.158 (uncalibrated). Actual111.46, appended only after selection. Primary generation path `2026_06_NO_NYG:NO:passing`.

#### Roster 2: $49,900; baseline mean 127.929

TE Cade Otton (TB, $3,300) / RB Kyren Williams (LAR, $6,800) / QB Patrick Mahomes (KC, $6,500) / RB Derrick Henry (BAL, $8,200) / DST Panthers (CAR, $2,500) / WR Puka Nacua (LAR, $8,100) / WR Carnell Tate (TEN, $5,000) / WR Xavier Worthy (KC, $4,600) / WR Rome Odunze (CHI, $4,900)

Research model score0.193 (uncalibrated). Actual86.78, appended only after selection. Primary generation path `2026_06_LAC_KC:KC:passing`.

#### Roster 3: $50,000; baseline mean 132.374

RB Chuba Hubbard (CAR, $6,300) / TE Cade Otton (TB, $3,300) / QB Matthew Stafford (LAR, $6,400) / RB Kyren Williams (LAR, $6,800) / DST Browns (CLE, $2,500) / WR Puka Nacua (LAR, $8,100) / WR Carnell Tate (TEN, $5,000) / WR Michael Wilson (ARI, $6,700) / WR Rome Odunze (CHI, $4,900)

Research model score0.152 (uncalibrated). Actual106.18, appended only after selection. Primary generation path `2026_06_ARI_LA:LAR:passing`.

#### Roster 4: $49,900; baseline mean 126.198

RB Chuba Hubbard (CAR, $6,300) / TE Michael Mayer (LV, $3,200) / RB Kyren Williams (LAR, $6,800) / DST Panthers (CAR, $2,500) / WR Puka Nacua (LAR, $8,100) / WR Carnell Tate (TEN, $5,000) / QB Josh Allen (BUF, $7,500) / WR Khalil Shakir (BUF, $5,300) / WR Emeka Egbuka (TB, $5,200)

Research model score0.141 (uncalibrated). Actual134.80, appended only after selection. Primary generation path `2026_06_BUF_LV:BUF:passing`.

#### Roster 5: $49,900; baseline mean 123.966

RB Jonathan Taylor (IND, $8,000) / RB Chuba Hubbard (CAR, $6,300) / QB Matthew Stafford (LAR, $6,400) / RB Derrick Henry (BAL, $8,200) / DST Panthers (CAR, $2,500) / WR Carnell Tate (TEN, $5,000) / TE Tyler Higbee (LAR, $3,400) / WR Rome Odunze (CHI, $4,900) / WR Emeka Egbuka (TB, $5,200)

Research model score0.152 (uncalibrated). Actual119.98, appended only after selection. Primary generation path `2026_06_TEN_IND:IND:run_control`.

Football review: Mahomes/Worthy needs KC passing TDs while Henry and Puka/Kyren still deliver; Shough/Vele/Nabers needs genuine NO–NYG two-sided passing and enough cheap supporting production; Allen/Shakir/Mayer needs BUFpassing with LVresponse. These are complete paths, but all retain shared Rams performance and several retain Otton/Tate/Odunze. The learned classifier has not solved joint game inefficiency or TD allocation. The selected Shough alternative is not the realized successful NO lineup merely because the game label matches.

## What is justified next

1. Broaden generation using physically coherent shared full-game outcomes, including low scoring/inefficiency for favorites and other games succeeding, then rerun old selector, highest-mean and these frozen core/rich models on the exact same broader pool. Predeclare sampling/budget, freeze decisions before appending known outcomes, keep source/state uncertainty explicit. No arbitrary Rams exclusion or teammate cap.
2. Continue point-forecast root-cause diagnosis separately: stored workload versus observed opportunity, efficiency/TD residuals and stale/missing role/QB/injury delivery. Recorded targets_mean3/allocated proxies are not calibrated forecasts; do not invent causal attribution or blanket raises.
3. No live model or selector promotion from these retrospective mixed results. Need independent chronological slates, original predecision source/code receipts, reliable complete-lineup scoring/coverage, and prospective football acceptance.

## Checks and artifacts

- 29focused feature/label/Captain/selector tests passed after correcting an initial test-fixture syntax typo. Tests cover cent-precision ties, no postgame predictors, missing projections/workload fail closed, portable frozen scaler, and external utility preserving player truth/hard controls.
- validate.py verified152,543canonical rows and12model artifacts, temporal week separation, source cohort hashes, correct labels/signatures, feature names/lengths and source lineage limitations. No additional model fits in calibration validation.
- Protocol before fitting: PROTOCOL.md. Full context coverage/exclusions: dataset_inventory_v2.json. Original float-boundary dataset remains separately preserved; cent-normalized labels are a versioned correction with unchanged inputs. Coefficients/scalers: models/*.json. Per-contest metrics/reliability: metrics.json; constant reference: calibration_baseline.json. Matched complete rosters/constraints/actual coverage: saved_pool_comparison.json.
- No new dependencies, production data writes, training sweeps, contest submissions or browser CSV downloads. Training was explicitly user-authorized, bounded and single-threaded; original lineups/settings are unchanged. Other joint-outcome and projection work is safely queued, not canceled.
