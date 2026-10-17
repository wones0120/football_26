# How often do two teammates come close to their pregame P90?

**In this small stored sample, two same-team receivers both reached 90% of their own pregame P90 in 13 of 756 WR-WR pairs (1.72%). Comparable different-game receivers were about as likely to do it. QB–receiver pairs behaved differently and reached together more often. There is no evidence here for a universal same-team penalty.**

This is retrospective, exploratory evidence from **972 canonical offensive player-games, 47 distinct NFL games and five weeks (2026 weeks 1–5)**. Coverage is uneven: 280 player-games in week1, 146 in week2, only20 in week3, 267 in week4 and259 in week5. Pair rows share players/games; 756 pairs are not 756 independent trials. Five raw week clusters (four after matching) cannot establish a durable optimizer policy or precise significance. No live projections/settings/optimizer behavior changed.

## Definitions frozen before outcomes

“Close” means actual DK points ≥ **0.90 × stored P90**. Exact P90 exceedance and 0.80 sensitivity are also shown. P90 is a marginal forecast quantile, not a maximum, and 90% of P90 is not the 81st percentile. All included P90 values are ≥5 points; small/zero/negative forecasts are excluded with counts.

Pre-kickoff storage is verified for projection row, projection run, model, feature row and feature run; cutoff and training cutoff must precede storage/kickoff as applicable. For a pair, both forecasts must exist before the earlier kickoff. Latest eligible stored projection per canonical player/game wins, with deterministic tie-breaking; optimizer repeats do not multiply observations. Aware timestamps are preserved. Naive legacy salary timestamps are conservatively interpreted in America/New_York; no four-hour correction creates extra eligible data. Schedule kickoff is reconstructed from already stored nflverse gameday/time in America/New_York, not fabricated from the week number.

## First check: marginal calibration

| Position | Player-games | ≥P90 | ≥90% P90 | ≥80% P90 |
|---|---:|---:|---:|---:|
| QB | 93 | 18.28% | 25.81% | 33.33% |
| RB | 244 | 11.89% | 17.62% | 22.13% |
| WR | 415 | 13.25% | 15.18% | 19.04% |
| TE | 220 | 11.36% | 15.91% | 19.09% |

Stored P90s were exceeded more than 10% in this sample, particularly QB. Therefore a blind independence assumption of 10% ×10%=1% is inappropriate. Ties count as hits. Calibration is conditional on this selected stored pool, not every NFL player or future model version.

## Same team: absolute joint rates and empirical marginal comparison

| Pair | Pairs | Distinct games / weeks | Both ≥P90 | Both ≥90% P90 | Both ≥80% P90 | Empirical marginal product at 90% | 90% joint week-bootstrap range |
|---|---:|---:|---:|---:|---:|---:|---:|
| WR-WR | 756 | 47 / 5 | 1.46% | 1.72% | 2.25% | 1.93% | 0.91%–2.49% |
| WR-TE | 975 | 47 / 5 | 1.33% | 2.77% | 4.00% | 2.38% | 1.81%–3.51% |
| RB-RB | 217 | 47 / 5 | 0.92% | 0.92% | 1.84% | 1.72% | 0.00%–1.58% |
| RB-WR | 1078 | 47 / 5 | 1.67% | 2.78% | 4.27% | 2.74% | 1.36%–3.75% |
| QB-WR | 411 | 47 / 5 | 4.87% | 7.30% | 9.25% | 3.62% | 6.58%–9.52% |
| QB-TE | 217 | 47 / 5 | 3.23% | 7.37% | 9.22% | 4.53% | 5.29%–9.70% |

The product uses the empirical hit rate of each side in that exact pair group. It is a descriptive reference; repeated appearances weight players and do not create independence. QB-WR/QB-TE show positive co-exceedance relative to these empirical marginals; RB-RB is rarer. WR-WR is slightly below its own marginal product, but that alone does not establish a worse roster choice.

## Matched different-game comparisons

Primary controls match season/week, ordered position pair, each player’s forecast mean in fixed five-point bins and salary in fixed $1,000 bins. Same-position sides are sorted by mean/salary/canonical ID. One deterministic different-game comparator is selected per matched same-team pair using identity hashes, never outcomes. Controls can be reused; unique control counts are retained. Both forecasts predate the earlier kickoff. Matching is partial and observational.

| Pair | Matched / all same-team pairs | Same-team close rate | Different-game close rate | Difference | Paired week-cluster 95% range |
|---|---:|---:|---:|---:|---:|
| WR-WR | 646 / 756 | 1.86% | 1.70% | +0.15 pp | -0.71 pp to +0.98 pp |
| WR-TE | 833 / 975 | 3.00% | 2.76% | +0.24 pp | -1.39 pp to +1.87 pp |
| RB-RB | 187 / 217 | 0.53% | 1.60% | -1.07 pp | -1.89 pp to +0.00 pp |
| RB-WR | 915 / 1078 | 2.62% | 2.51% | +0.11 pp | -1.26 pp to +1.70 pp |
| QB-WR | 340 / 411 | 7.06% | 4.12% | +2.94 pp | +0.00 pp to +5.24 pp |
| QB-TE | 178 / 217 | 7.30% | 3.93% | +3.37 pp | -1.84 pp to +8.00 pp |

Bootstrap resamples the four matched whole-week clusters 1,000 times with seed 20261016, preserving within-week player/game overlap and matching. These are coarse descriptive ranges with very few clusters, not evidence of causal or persistent statistical superiority. Controls may share a player with their treatment pair, reflecting one possible replacement; this is not a nine-player lineup solve.

### Workload and availability sensitivity

Model-linked original feature rows do retain some pregame context. A secondary sensitivity additionally matches exact recorded injury-status label (missing stays UNKNOWN) and opportunity proxy bins: two targets for WR/TE, five carries for RB, QB not applicable. These are stored lagged/model-input workload proxies, not future actual targets. This secondary specification was added after inspecting initial simple-match rates, without searching bin choices or thresholds for a desired result; treat it as exploratory.

| Pair | Matched pairs | Same team | Different games | Difference |
|---|---:|---:|---:|---:|
| WR-WR | 620 | 1.77% | 1.77% | +0.00 pp |
| WR-TE | 798 | 2.88% | 3.51% | -0.63 pp |
| RB-RB | 180 | 0.56% | 1.11% | -0.56 pp |
| RB-WR | 862 | 2.09% | 2.32% | -0.23 pp |
| QB-WR | 327 | 7.03% | 4.28% | +2.75 pp |
| QB-TE | 175 | 7.43% | 5.14% | +2.29 pp |

Feature coverage out of 972: `{'team_implied_total': 972, 'team_spread_line': 972, 'game_total_line': 972, 'targets_mean_3': 972, 'carries_mean_3': 972, 'pregame_injury_status': 251, 'pregame_availability_probability': 972, 'pregame_role_label': 504}`. Availability probabilities are stored model inputs, not independently verified game-clearance probabilities. Missing status is not treated as healthy. Full practice/game clearance and per-source publication proof are incomplete. Current source tables cannot retroactively make these old snapshots more informed.

## Opposing same-game and different-game raw controls

| Pair | Opposing pairs | Opposing close rate | Different-game pairs | Different-game close rate |
|---|---:|---:|---:|---:|
| WR-WR | 918 | 2.29% | 11917 | 1.90% |
| WR-TE | 955 | 2.62% | 13005 | 2.51% |
| RB-RB | 313 | 3.19% | 4094 | 3.27% |
| RB-WR | 1087 | 2.21% | 14000 | 2.57% |
| QB-WR | 412 | 3.64% | 5397 | 3.28% |
| QB-TE | 219 | 2.74% | 2939 | 4.25% |

These raw controls are not the matched results. Opponent-side and different-game counts also share observations and must not be read as independent sample sizes.

## Salary and contribution, not nine simultaneous ceiling hits

| Pair | Matched same-team mean salary | Different-game salary | Same-team actual combined points | Different-game actual points |
|---|---:|---:|---:|---:|
| WR-WR | $8,486 | $8,486 | 13.40 | 13.98 |
| WR-TE | $7,520 | $7,527 | 12.42 | 12.64 |
| RB-RB | $10,045 | $10,034 | 14.45 | 14.06 |
| RB-WR | $9,354 | $9,346 | 14.89 | 14.75 |
| QB-WR | $9,941 | $9,959 | 24.37 | 24.85 |
| QB-TE | $8,911 | $8,882 | 23.71 | 22.11 |

A lineup can succeed with two receivers contributing useful points without either reaching P90. Cheap same-team players may preserve salary for a stronger player elsewhere; these pair tables do not price that full-lineup tradeoff or contest payout. They also include backups/nonparticipants, rather than only optimizer-selected high-volume starters. No universal teammate cap, fixed penalty, tail-credit weight, or calibrated joint probability should be activated from this study. The useful next step is a frozen-pool, matched lineup comparison with observed inputs and prospective joint calibration.

## Coverage, scoring and chronology limits

29,237 original 2026 forecast rows collapse to2,873 unique eligible pregame player-games before offensive salary/P90/outcome filters. All 2024/25 forecasts inventoried were stored in2026 and excluded as postgame reconstructions. The empty2026 target.dim_game/target.fact_player_game_actual tables were not mistaken for absent source data: existing public raw schedule/stat records were linked through canonical nflreadpy native-ID aliases. No display-name joins. Five ambiguous/unmapped raw outcome identities were excluded.

Exclusion counts (different stages/units): `{'outcome_alias_ambiguous_or_missing': 5, 'forecast_model_or_feature_chronology_missing_or_postkick': 524, 'player_no_pregame_offensive_salary': 1445, 'player_actual_unknown': 94, 'player_p90_below_5': 362, 'pair_not_jointly_available_before_first_kickoff': 42843}`. Participation among included player-games: `{'played_confirmed': 862, 'did_not_play': 105, 'played_inferred': 5}`. Confirmed nonparticipants without stat rows contribute zero; missing outcomes are not silently zero. Including known DNP outcomes is intentional unconditional forecast evaluation, not a claim of pregame game-dressing clearance. A participants-only analysis would condition on postgame information and answer a different question.

Actual scoring version `research_dk_offense_unfloored_v1` is pinned in analyze.py: 0.04 passing yards/4 passing TD/−1 interception; 0.1 rushing and receiving yards, six TD, PPR, two-point conversions, six special-teams/fumble-recovery TD, −1 authoritative total fumbles lost, separate300/100/100-yard bonuses, no zero floor. Required components must be explicit; missing values exclude the record. This corrects the older shared-scorer default zero floor and checks the current raw schema’s special_teams_tds/fumbles_lost_total/fumble_recovery_tds fields. No DST labels enter this study. It is a transparent reconstructed offensive score from latest stored source stats, not independently certified DraftKings contest settlement.

Forecasts are retained as originally stored mean/P90 with calibration method/model code-hash lineage; original rows do **not** carry a first-class scoring-definition version or immutable publication evidence for every constituent source. They are the application’s DK offensive forecasts, but cross-version scoring equivalence/source freshness cannot be certified per row. This limits the strength of a “P90 calibration” interpretation. All richer-match paired-difference bootstrap ranges include zero; the basic QB-WR range only reaches zero at its lower edge. These small-cluster ranges are unstable and do not justify a significance claim. Original forecasts were never recomputed with outcomes; no historical cutoff is used as a substitute for actual pregame storage evidence.

Latest eligible forecast selection, slate coverage, changing models, different forecast horizons, salary import availability and prior research inspection create selection bias. Same-game observations share environments, and weeks are not fully independent either. Only one partial season/five weeks is available. Market strata in results.json use the median **stored pregame team implied total**, without a tuned “shootout” cutoff; many cells have few joint hits, so no market-conditioned policy is recommended. Role/share fields remain incomplete and no new numeric allocation probability is invented.

## Reproduction and next evidence

[Protocol](PROTOCOL.md) · [Inventory](inventory.json) · [Results including thresholds/strata/weekly counts](results.json) · [Canonical player-game audit](analysis_players.json). Run inventory.py, extract.py, extract_features.py using read-only DB access, then analyze.py and render_report.py; existing JSON inputs are frozen/hashes recorded for exact offline replay. Tests cover scoring/negative points, inclusive thresholds, no unknown-as-zero, identity relations, chronology and clustered summary.

Prospective logging should append one complete pre-kickoff pool snapshot at fixed horizons, original schedule/role/availability and market source clocks, explicit DK scoring version, model/calibration version and canonical/native IDs. Link corrected final outcomes with source/version separately. Freeze position/workload matching and uncertainty protocol before accumulating more games. Require enough independent weeks and out-of-time full-lineup validation before changing optimizer behavior.
