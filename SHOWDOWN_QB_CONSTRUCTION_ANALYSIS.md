# DraftKings NFL Showdown QB Construction Analysis

## Executive summary

**Decision: retain current optimizer rules. These standings do not support a general QB-Captain penalty, a two-QB penalty, or a prohibition of QB Captain + both starting QBs.** They also do not validate the current optimizer weights. This is an observational analysis of the locally stored contests, with a small number of independent games.

1. **QB Captain: efficiency is unresolved.** Field usage is 24.71%; pooled top-10% lift is 1.29×. Equal-contest mean lift is 0.96×, with game-clustered 95% interval 0.68–1.28×. Neither “overused” nor “underused” is established across games.
2. **Both starters: no stable underperformance at top 10% or top 1%.** Usage is 36.31%; entry-weighted top-10% lift is 1.33×, equal-contest mean 1.04×. Actual first-place rates are much weaker; duplication is higher. This distinction prevents calling the construction tournament-efficient.
3. **QB Captain + both starters is not generally shown to be weak.** Its top-10% rate is 19.07% and pooled lift 1.86×. The 2025 top-10% lift is 3.37× across only two usable games, versus 0.89× across eight 2026 games. The result is unstable across seasons and starter-evidence cohorts.
4. **The evidence is not strong enough to justify changing production rules.** Only 12 games support the Captain analysis and 10 support both-starter comparisons. Major top-10% pairwise intervals mostly include zero absolute difference; every available Holm-adjusted top-10%/top-1% sign-flip p-value exceeds 0.05. This is limited directional evidence, not proof of no effect.
5. **Recommended next optimizer treatment: no scoring/eligibility change.** Collect more independent completed games with archived starter identity and exact payout economics, then test a modest exposure cap or soft adjustment in a frozen, chronological shadow replay. First-place/duplication-aware validation is the priority. The current data does not establish the sign or size of a penalty.

## Data actually available

The read-only snapshot contains 47 normalized contests. Actual six-slot Showdown standings are present in **28 files, 904,278 entries, and 12 salary-dated NFL games**. 900,342 entries (99.56%) have fully parsed, uniquely resolved, structurally valid rosters; salary legality is checked where native Showdown salaries exist. The other 3,936 entries have blank/malformed lineups and remain in the coverage audit.

The starting-QB cohort contains 733,434 entries in 26 contests / 10 games, after uncertain starter slates and nonstarter QB rosters are excluded. Each roster is counted once per actual entry, including repeated physical lineups. Contest IDs inferred by the old importer from source content are retained as synthetic local IDs; they cannot be assumed to match live DraftKings contest economics.

**There are no stored 2024 contest standings.** The 2024 actual-score oracle is not a substitute. Four 2025 contests and 24 2026 contests are available; only two 2025 games qualify for both-starter analysis. No older standings were found in the normalized or legacy inventory. Legacy CPT files have matching normalized season/week/slate inventory; legacy data is not added again. These are the contests available locally, not a representative sample of all DraftKings Showdowns.

The season/format labels are source/import labels, not independently authenticated historical contest records. Six slots, distinct players, two opposing teams and available native Showdown salaries are checked. Historical scoring-rule version is not stored, so era equivalence is not certified; season results are kept separate and no older eras are silently pooled.

### Coverage and starter provenance by game

| Game | Files | Loaded / resolved | Starting-QB evidence | Winner entries / distinct winning rosters |
| --- | --- | --- | --- | --- |
| 2025_13_BAL_CIN | 1 | 46,810 / 46,446 | Uncertain; excluded from starter cohort | 1 / 1 |
| 2025_5_JAX_KC | 1 | 118,906 / 118,425 | Trevor Lawrence: reconstructed_salary_prior_volume; Patrick Mahomes: reconstructed_salary_prior_volume | 1 / 1 |
| 2025_8_LAC_MIN | 1 | 118,897 / 118,411 | Justin Herbert: reconstructed_salary_prior_volume | 58 / 1 |
| 2025_9_SEA_WAS | 1 | 79,270 / 79,018 | Sam Darnold: reconstructed_salary_prior_volume; Jayden Daniels: reconstructed_salary_prior_volume | 1 / 1 |
| 2026_1_DAL_NYG | 2 | 60,372 / 60,078 | Dak Prescott: reconstructed_salary_prior_volume; Jaxson Dart: reconstructed_salary_prior_volume | 9 / 4 |
| 2026_1_NE_SEA | 1 | 95,124 / 94,647 | Drake Maye: archived_pregame_inferred; Sam Darnold: archived_pregame_inferred | 24 / 1 |
| 2026_2_BUF_DET | 3 | 23,779 / 23,686 | Josh Allen: archived_pregame_inferred; Jared Goff: archived_pregame_inferred | 7 / 3 |
| 2026_2_IND_KC | 3 | 86,800 / 86,488 | Daniel Jones: reconstructed_salary_prior_volume; Patrick Mahomes: reconstructed_salary_prior_volume | 87 / 3 |
| 2026_2_LAR_NYG | 2 | 89,179 / 88,772 | Matthew Stafford: archived_pregame_inferred; Jaxson Dart: archived_pregame_inferred | 39 / 2 |
| 2026_3_ATL_GB | 5 | 11,937 / 11,880 | Michael Penix Jr.: archived_pregame_inferred; Jordan Love: archived_pregame_inferred | 9 / 5 |
| 2026_4_CAR_DET | 4 | 59,848 / 59,546 | Bryce Young: archived_pregame_inferred; Jared Goff: archived_pregame_inferred | 17 / 4 |
| 2026_4_CLE_PIT | 4 | 113,356 / 112,945 | Deshaun Watson: archived_pregame_inferred; Aaron Rodgers: archived_pregame_inferred | 55 / 4 |

Winning-roster counts in this table are summed per contest; the same physical winner may occur in several contests on one game. Counts of tied-first entries are not counts of independent winning events.

### Specific corrections and exclusions

- The 2025 file labeled Week 6 / SUNDAY_LATE resolves completely to the preserved **Week 5 KC–JAX Monday game**, dated October 6, 2025 in the salary game information and matched schedule. The analysis uses that game as its cluster and uses only pre-Week-5 statistics for starter/role inference. The original source labels remain intact.
- Week 3 2026 THURSDAY_NIGHT curated salary rows were overwritten by a later 671-row import. The original **106 raw DK salary rows** from ingest `ed209cc0-fe7e-45a9-ac8f-7a7be79896cf`, checksum `cdaba70ab3cac21c18d88bd73fdc5fce1caad8e26554a720e4bccdd956db44d2`, were recovered for research. Source-native IDs link them to existing canonical aliases; no database record was repaired.
- The 2025 Week 8 MIN starter remains uncertain. The higher-salary QB does not satisfy the prior-volume rule. That game remains in the Captain-position analysis but is excluded from both-starter/combination analyses.
- The 2025 Week 13 CIN–BAL file has Classic Thanksgiving salaries, not a retained Showdown salary grid. Its rosters can be identified using the specific game/team/position salary and alias universe, including team-constrained kicker aliases, but salary-cap validation is unavailable. Both starter identities remain uncertain and the game is excluded from starter-dependent results.
- Some Week 1 Sunday and Week 2 Sunday starter rows were stored after kickoff. A claimed earlier observation inside those rows is insufficient; those rows are rejected. A separately labeled salary/prior-volume inference may qualify the slate. No current-game usage, schedule QB-name field, or actual-score optimality identifies a starter.

Identity joins require the selected source salary slate and matchup, native/canonical IDs, team and position. Normalized-name matching is only a candidate lookup inside that constrained universe. Conflicting IDs are quarantined. Alias fallback supplies identity only, never missing salary, availability or starter status.

## Definitions and statistical method

**Successful-lineup share:** `successful entries with X / all successful entries in the eligible cohort`. **Success rate:** `successful entries with X / all entries using X`. **Lift/performance index:** `success rate of X / success rate of the full eligible cohort`, algebraically equal to `successful-lineup share / field usage share`. **Odds ratio:** `(success_X / failure_X) / (success_comparator / failure_comparator)`. Zero comparator successes produce an unavailable/infinite-limit ratio; no arbitrary continuity correction is applied.

Rank cutoffs use `floor(N × fraction)` of the complete contest field, with all competition-rank ties at the boundary included. Consequently, the realized top-10% rate can exceed 10%. Top 0.1% is available only for fields of at least 1,000; top 1% requires at least 100. Tiny contests are not relabeled as top 0.1% simply because they have a winner. Each cutoff’s conditional rates and lift use only supported contests; cutoff-specific field shares and denominators are exported. The Captain-position share index uses its displayed all-field usage, which differs slightly from the cutoff-eligible lift when tiny contests are excluded. A fractional boundary-tie sensitivity allocates the remaining threshold positions proportionally within the tied block.

Average/median finish percentile uses the full-field **tie midrank / N × 100**, with lower values better. Winners are entries with actual standings rank 1, including ties. Optimizers/oracles do not supply any success outcome.

Captain and position tables use complete resolved rosters. Starter/combination tables additionally require two identified expected starters and no backup/gadget/emergency QB. These populations differ: Captain metrics use 900,342 entries; starter metrics use 733,434. An excluded backup is not a zero-QB roster. Group counts partition their own cohort; groups across these cohorts should not be added together.

Entry-weighted pooling gives each entry equal weight. Equal-contest results compute each contest metric first and report its mean, median, IQR and outperforming count. Bootstrap intervals resample **NFL games**, retaining all contests on each sampled game together (4,000 draws; seed 20261005). Pairwise rates use only contests with both constructions represented. Exact paired game-level sign flips are diagnostic under a symmetric null; Holm adjustment covers all available major top-10%/top-1% comparisons. P-values use a game-mean paired effect, whereas entry-weighted intervals use a pooled entry effect; they answer different estimand questions.

There are only 10–12 independent clusters. Bootstrap intervals and p-values are exploratory, not precise guarantees. Repeated entries/users, endogenous construction choice, slate differences and contest-type selection prevent causal inference. No binomial test treating 900,000 entries as independent is used.

## Frequency among successful entries (A, B, E)

Percentages below are shares within the complete classified cohort for that row. They answer how prevalent the construction is among successful entries.

| Construction | Entries | Field usage | Top 20 share | Top 10 share | Top 5 share | Top 1 share | Top 0.1 share | Winner share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QB Captain | 222,469 | 24.71% | 30.82% | 31.95% | 34.05% | 27.13% | 47.10% | 39.61% |
| Non-QB Captain | 677,873 | 75.29% | 69.18% | 68.05% | 65.95% | 72.87% | 52.90% | 60.39% |
| Both QBs | 266,318 | 36.31% | 48.12% | 48.20% | 49.80% | 54.65% | 46.15% | 4.82% |
| Exactly one QB | 410,464 | 55.96% | 47.63% | 47.69% | 47.84% | 43.51% | 53.16% | 94.78% |
| Zero QB | 56,652 | 7.72% | 4.25% | 4.11% | 2.36% | 1.85% | 0.69% | 0.40% |

## Conditional success and combined construction (A–C)

These percentages answer how likely an entry using the construction was to achieve the specified finish. Relative lift compares with its own eligible full field.

| Construction | Entries | Field usage | Avg / median percentile | Top 20 rate | Top 10 rate | Top 5 rate | Top 1 rate | Winner rate | Lift top 10 / top 1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QB Captain | 222,469 | 24.71% | 45.70 / 43.72 | 25.13% | 13.18% | 7.06% | 1.22% | 0.0548% | 1.29× / 1.10× |
| Non-QB Captain | 677,873 | 75.29% | 51.12 / 51.72 | 18.51% | 9.21% | 4.49% | 1.07% | 0.0274% | 0.90× / 0.97× |
| Both QBs | 266,318 | 36.31% | 40.91 / 37.67 | 26.77% | 13.60% | 7.07% | 1.71% | 0.0045% | 1.33× / 1.50× |
| Exactly one QB | 410,464 | 55.96% | 54.14 / 56.51 | 17.19% | 8.73% | 4.41% | 0.88% | 0.0575% | 0.85× / 0.78× |
| Zero QB | 56,652 | 7.72% | 59.09 / 60.99 | 11.13% | 5.45% | 1.58% | 0.27% | 0.0018% | 0.53× / 0.24× |
| QB Captain + both QBs | 80,295 | 10.95% | 36.33 / 30.55 | 34.45% | 19.07% | 10.53% | 2.17% | 0.0112% | 1.86× / 1.91× |
| QB Captain + one QB | 100,228 | 13.67% | 53.59 / 55.43 | 17.38% | 8.28% | 3.82% | 0.65% | 0.0549% | 0.81× / 0.58× |
| Non-QB Captain + both QBs | 186,023 | 25.36% | 42.88 / 40.97 | 23.45% | 11.23% | 5.58% | 1.51% | 0.0016% | 1.10× / 1.33× |
| Non-QB Captain + one QB | 310,236 | 42.30% | 54.32 / 56.62 | 17.13% | 8.87% | 4.60% | 0.96% | 0.0583% | 0.87× / 0.84× |
| Non-QB Captain + zero QB | 56,652 | 7.72% | 59.09 / 60.99 | 11.13% | 5.45% | 1.58% | 0.27% | 0.0018% | 0.53× / 0.24× |

The complete underlying table also contains top-0.1% rates, every success count/denominator, economic coverage and fractional-tie lift: [summary.csv](artifacts/showdown_qb_construction/summary.csv). The five combination groups are disjoint and exhaustive within the starter-eligible cohort.

### All-entry missing-roster bounds

Complete-case estimates above cannot assign a construction to blank rosters. All-entry usage below assigns every unknown roster away from, then to, the construction. Success-rate bounds separately allocate unknown successes and unknown failures. These are deterministic missingness bounds, not confidence intervals.

| Construction | Full contest entries / unknown | All-entry usage interval | Top 10 conditional-rate interval | Unknown top-10 successes |
| --- | --- | --- | --- | --- |
| QB Captain | 904,278 / 3,936 | 24.60%–25.04% | 12.95%–13.18% | 0 |
| Both QBs | 738,571 / 3,086 | 36.06%–36.48% | 13.44%–13.60% | 0 |
| QB Captain + both QBs | 738,571 / 3,086 | 10.87%–11.29% | 18.36%–19.07% | 0 |

No unknown roster is top 10%, top 1%, or tied first in these exports. Blank rosters mostly have zero scores; removing them modestly raises the classified-field baseline. For starter rows, all-entry exposure refers only to the contests with identified starters, and retains known nonstarter-QB rosters in the exposure denominator. Full per-contest bounds are in [missing_roster_bounds.csv](artifacts/showdown_qb_construction/missing_roster_bounds.csv).

## Captain-position baseline (D)

| Captain position | Field usage | Top 10 share | Top 1 share | Winner share | Index top 10 | Index top 1 | Index winner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| QB | 24.71% | 31.95% | 27.13% | 39.61% | 1.29× | 1.10× | 1.60× |
| RB | 27.04% | 19.70% | 13.98% | 1.95% | 0.73× | 0.52× | 0.07× |
| WR | 30.93% | 34.77% | 44.30% | 27.27% | 1.12× | 1.43× | 0.88× |
| TE | 11.14% | 10.55% | 10.96% | 31.17% | 0.95× | 0.98× | 2.80× |
| DST | 4.08% | 1.84% | 1.02% | 0.00% | 0.45× | 0.25× | 0.00× |
| K | 2.09% | 1.19% | 2.61% | 0.00% | 0.57× | 1.25× | 0.00× |

## Contest-weighted and statistical comparisons (F, K)

| Construction | Contests / games | Entries | Mean top 10 rate | Mean lift | Median lift | Lift IQR | Outperformed field | 95% CI mean lift |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QB Captain | 28 / 12 | 222,469 | 9.71% | 0.96× | 0.84× | 0.64–1.33 | 13/28 (46.43%) | 0.68–1.28 |
| Non-QB Captain | 28 / 12 | 677,873 | 10.05% | 0.98× | 1.03× | 0.88–1.10 | 15/28 (53.57%) | 0.88–1.06 |
| Both QBs | 26 / 10 | 266,318 | 10.67% | 1.04× | 0.93× | 0.33–1.33 | 11/26 (42.31%) | 0.57–1.65 |
| Exactly one QB | 26 / 10 | 410,464 | 10.20% | 1.00× | 1.12× | 0.85–1.20 | 16/26 (61.54%) | 0.81–1.14 |
| Zero QB | 25 / 10 | 56,652 | 4.45% | 0.44× | 0.52× | 0.00–0.68 | 3/25 (12.00%) | 0.19–0.65 |
| QB Captain + both QBs | 25 / 10 | 80,295 | 13.17% | 1.29× | 1.11× | 0.19–2.03 | 14/25 (56.00%) | 0.61–2.01 |
| QB Captain + one QB | 26 / 10 | 100,228 | 8.44% | 0.83× | 0.88× | 0.51–1.05 | 9/26 (34.62%) | 0.57–1.17 |
| Non-QB Captain + both QBs | 26 / 10 | 186,023 | 9.96% | 0.97× | 0.90× | 0.43–1.19 | 11/26 (42.31%) | 0.54–1.51 |
| Non-QB Captain + one QB | 26 / 10 | 310,236 | 10.37% | 1.02× | 1.20× | 0.79–1.29 | 14/26 (53.85%) | 0.78–1.20 |
| Non-QB Captain + zero QB | 25 / 10 | 56,652 | 4.45% | 0.44× | 0.52× | 0.00–0.68 | 3/25 (12.00%) | 0.20–0.64 |

A construction absent from a contest has an undefined conditional success rate; that contest is omitted from that row’s mean/median/IQR. Thus the 25-contest rows do not have the same denominator as the 26-contest rows. The pooled field exposure still includes zero exposure in otherwise eligible contests.

### Game-clustered rate and lift intervals

| Construction | Top 10 rate 95% CI | Top 10 lift 95% CI | Top 1 rate 95% CI | Top 1 lift 95% CI | Winner lift 95% CI |
| --- | --- | --- | --- | --- | --- |
| QB Captain | 9.08%–16.76% | 0.89–1.65 | 0.64%–1.76% | 0.60–1.55 | 0.08–3.30 |
| Non-QB Captain | 7.62%–10.57% | 0.75–1.03 | 0.87%–1.24% | 0.79–1.13 | 0.24–1.32 |
| Both QBs | 8.37%–18.29% | 0.83–1.76 | 0.94%–2.61% | 0.87–2.08 | 0.02–0.53 |
| Exactly one QB | 5.39%–11.51% | 0.52–1.14 | 0.43%–1.25% | 0.35–1.16 | 1.39–1.86 |
| Zero QB | 2.42%–8.18% | 0.23–0.80 | 0.00%–0.60% | 0.00–0.55 | 0.00–0.27 |
| QB Captain + both QBs | 7.10%–30.60% | 0.70–2.98 | 0.42%–3.75% | 0.39–3.16 | 0.00–1.57 |
| QB Captain + one QB | 5.30%–11.22% | 0.52–1.10 | 0.15%–1.23% | 0.13–1.09 | 0.00–4.91 |
| Non-QB Captain + both QBs | 7.68%–16.07% | 0.76–1.53 | 0.84%–2.33% | 0.80–1.85 | 0.00–0.19 |

### Top 10% paired comparisons

| Comparison A vs B | Games | N A / N B | Rate A / B | Difference (pp), 95% CI | Rate ratio | Odds ratio, 95% CI | Game p / Holm p |
| --- | --- | --- | --- | --- | --- | --- | --- |
| QB Captain vs Non-QB Captain | 12 | 222,469 / 677,873 | 13.18% / 9.21% | 3.97; -1.36–9.07 | 1.43 | 1.50; 0.86–2.42 | 0.61 / 1.00 |
| Both QBs vs Exactly one QB | 10 | 266,318 / 410,464 | 13.60% / 8.73% | 4.87; -3.46–12.58 | 1.56 | 1.65; 0.67–3.81 | 0.46 / 1.00 |
| Both QBs vs Zero QB | 10 | 266,317 / 56,652 | 13.60% / 5.45% | 8.14; 0.50–15.31 | 2.49 | 2.73; 1.07–8.97 | 0.08 / 1.00 |
| QB Captain + both QBs vs QB Captain + one QB | 10 | 80,295 / 100,222 | 19.07% / 8.28% | 10.78; -3.50–24.61 | 2.30 | 2.61; 0.64–7.60 | 0.26 / 1.00 |
| QB Captain + both QBs vs Non-QB Captain + both QBs | 10 | 80,295 / 186,022 | 19.07% / 11.23% | 7.83; -3.10–20.02 | 1.70 | 1.86; 0.69–4.10 | 0.33 / 1.00 |
| QB Captain + both QBs vs Non-QB Captain + one QB | 10 | 80,295 / 310,220 | 19.07% / 8.87% | 10.19; -5.20–24.45 | 2.15 | 2.42; 0.54–7.33 | 0.37 / 1.00 |
| QB Captain + both QBs vs Non-QB Captain + zero QB | 10 | 80,295 / 56,652 | 19.07% / 5.45% | 13.61; -0.71–26.19 | 3.50 | 4.08; 0.90–14.95 | 0.08 / 1.00 |

### Top 1% paired comparisons

| Comparison A vs B | Games | N A / N B | Rate A / B | Difference (pp), 95% CI | Rate ratio | Odds ratio, 95% CI | Game p / Holm p |
| --- | --- | --- | --- | --- | --- | --- | --- |
| QB Captain vs Non-QB Captain | 12 | 222,461 / 677,835 | 1.22% / 1.07% | 0.14; -0.56–0.81 | 1.13 | 1.14; 0.54–1.94 | 0.81 / 1.00 |
| Both QBs vs Exactly one QB | 10 | 266,314 / 410,424 | 1.71% / 0.88% | 0.83; -0.34–2.04 | 1.94 | 1.95; 0.73–5.66 | 0.20 / 1.00 |
| Both QBs vs Zero QB | 10 | 266,314 / 56,650 | 1.71% / 0.27% | 1.44; 0.45–2.37 | 6.29 | 6.38; 1.87–34.80 | 0.09 / 1.00 |
| QB Captain + both QBs vs QB Captain + one QB | 10 | 80,294 / 100,221 | 2.17% / 0.65% | 1.52; -0.62–3.37 | 3.32 | 3.37; 0.40–19.01 | 0.18 / 1.00 |
| QB Captain + both QBs vs Non-QB Captain + both QBs | 10 | 80,294 / 186,020 | 2.17% / 1.51% | 0.67; -0.95–2.14 | 1.44 | 1.45; 0.30–3.10 | 0.43 / 1.00 |
| QB Captain + both QBs vs Non-QB Captain + one QB | 10 | 80,294 / 310,203 | 2.17% / 0.96% | 1.22; -0.93–3.17 | 2.27 | 2.30; 0.28–8.11 | 0.31 / 1.00 |
| QB Captain + both QBs vs Non-QB Captain + zero QB | 10 | 80,294 / 56,650 | 2.17% / 0.27% | 1.90; 0.02–3.48 | 8.00 | 8.15; 1.00–44.45 | 0.16 / 1.00 |

Relative-rate intervals, contest-weighted paired differences and their intervals are also stored in [comparisons.csv](artifacts/showdown_qb_construction/comparisons.csv). A bootstrap interval excluding zero in an isolated comparison does not override small-cluster, multiple-comparison and season-instability concerns.

## Season and sensitivity checks (L)

2024: unavailable, not zero success. 2025 and 2026 rows are actual standings under their stored source-season labels.

| Season | Construction | Contests / games | Entries | Field usage | Top 10 rate / lift | Top 1 rate / lift | Winner rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2025 | QB Captain | 4 / 4 | 101,594 | 28.04% | 17.11% / 1.66× | 1.67% / 1.46× | 0.0591% |
| 2025 | Both QBs | 2 / 2 | 88,383 | 44.87% | 21.83% / 2.07× | 2.82% / 2.23× | 0.0023% |
| 2025 | QB Captain + both QBs | 2 / 2 | 30,339 | 15.40% | 35.63% / 3.37× | 4.57% / 3.62× | 0.0066% |
| 2026 | QB Captain | 24 / 8 | 120,875 | 22.47% | 9.87% / 0.98× | 0.84% / 0.77× | 0.0513% |
| 2026 | Both QBs | 24 / 8 | 177,935 | 33.17% | 9.50% / 0.94× | 1.16% / 1.06× | 0.0056% |
| 2026 | QB Captain + both QBs | 24 / 8 | 49,956 | 9.31% | 9.00% / 0.89× | 0.72% / 0.66× | 0.0140% |

| Sensitivity | Construction | Games | Top 10 lift | Top 1 lift |
| --- | --- | --- | --- | --- |
| archived_starters_only | QB Captain | 6 | 0.91× | 0.47× |
| archived_starters_only | Both QBs | 6 | 0.98× | 1.08× |
| archived_starters_only | QB Captain + both QBs | 6 | 0.90× | 0.34× |
| fields_at_least_1000 | QB Captain | 12 | 1.29× | 1.10× |
| fields_at_least_1000 | Both QBs | 10 | 1.33× | 1.50× |
| fields_at_least_1000 | QB Captain + both QBs | 10 | 1.87× | 1.91× |

| Construction | Boundary-tie lift top 10 | Fractional-tie lift top 10 | Boundary-tie lift top 1 | Fractional-tie lift top 1 | Leave-one-game-out top 10 lift range |
| --- | --- | --- | --- | --- | --- |
| QB Captain | 1.29 | 1.31 | 1.10 | 1.12 | 1.09–1.37 |
| Both QBs | 1.33 | 1.31 | 1.50 | 1.40 | 1.15–1.45 |
| QB Captain + both QBs | 1.86 | 1.89 | 1.91 | 2.02 | 1.09–2.14 |

The archived-starters-only sensitivity has 19 contests but just six games; all starter records in that subset are still inferred, not final independent confirmation of kickoff starters. Reconstructed starter inference adds two 2025 games and two 2026 games. Its very different mix explains why pooled success should not be promoted into a general rule. Leave-one-game-out pooling stays positive at top 10%, but that does not resolve the broader 2025-versus-2026 reversal.

## Slate characteristics (G)

**All strata are exploratory.** The CSV includes group counts, rates, field shares, success shares, lift and number of contests/games within each stratum. The full set is [exploratory_summary.csv](artifacts/showdown_qb_construction/exploratory_summary.csv), with per-contest inputs in [exploratory.csv](artifacts/showdown_qb_construction/exploratory.csv). The selected tables below show the main QB exposures and their conditional rates.

Three games have hash-verified market CSV snapshots with both observed and captured timestamps before kickoff (2026 ATL–GB, CLE–PIT, CAR–DET). Those are the pregame market strata. Retrospective schedule closing lines cover more games and are reported separately as audit-only; they do not establish what a historical optimizer knew. A winning-team label is inherently postgame and audit-only.

### Pregame-supported total, spread and favorite

| Dimension | Bucket | Construction | Games | Entries | Top 10 rate | Top 1 rate |
| --- | --- | --- | --- | --- | --- | --- |
| favorite_captain_pregame | favorite | QB Captain | 3 | 12,487 | 22.91% | 1.98% |
| favorite_captain_pregame | favorite | Both QBs | 3 | 4,972 | 25.97% | 0.76% |
| favorite_captain_pregame | favorite | QB Captain + both QBs | 3 | 4,972 | 25.97% | 0.76% |
| favorite_captain_pregame | underdog | QB Captain | 3 | 20,598 | 5.19% | 0.0437% |
| favorite_captain_pregame | underdog | Both QBs | 3 | 6,847 | 10.25% | 0.0438% |
| favorite_captain_pregame | underdog | QB Captain + both QBs | 3 | 6,847 | 10.25% | 0.0438% |
| game_total_pregame | <43 | QB Captain | 2 | 24,379 | 13.31% | 1.01% |
| game_total_pregame | <43 | Both QBs | 2 | 42,238 | 13.24% | 1.45% |
| game_total_pregame | <43 | QB Captain + both QBs | 2 | 9,320 | 18.05% | 0.44% |
| game_total_pregame | >49 | QB Captain | 1 | 8,706 | 7.88% | 0.10% |
| game_total_pregame | >49 | Both QBs | 1 | 14,791 | 9.54% | 1.96% |
| game_total_pregame | >49 | QB Captain + both QBs | 1 | 2,499 | 12.44% | 0.00% |
| spread_pregame | close <=3 | QB Captain | 1 | 22,555 | 14.05% | 1.09% |
| spread_pregame | close <=3 | Both QBs | 1 | 40,565 | 13.65% | 1.51% |
| spread_pregame | close <=3 | QB Captain + both QBs | 1 | 8,925 | 18.83% | 0.46% |
| spread_pregame | moderate 3-7 | QB Captain | 2 | 10,530 | 7.24% | 0.0950% |
| spread_pregame | moderate 3-7 | Both QBs | 2 | 16,464 | 8.90% | 1.76% |
| spread_pregame | moderate 3-7 | QB Captain + both QBs | 2 | 2,894 | 10.78% | 0.00% |

### QB rushing archetype

| Dimension | Bucket | Construction | Games | Entries | Top 10 rate | Top 1 rate |
| --- | --- | --- | --- | --- | --- | --- |
| captain_archetype | high_rush | QB Captain | 11 | 168,986 | 12.30% | 1.12% |
| captain_archetype | high_rush | Both QBs | 8 | 58,838 | 18.69% | 2.14% |
| captain_archetype | high_rush | QB Captain + both QBs | 8 | 58,838 | 18.69% | 2.14% |
| captain_archetype | mobile | QB Captain | 10 | 30,950 | 16.88% | 2.23% |
| captain_archetype | mobile | Both QBs | 4 | 12,026 | 25.37% | 3.99% |
| captain_archetype | mobile | QB Captain + both QBs | 4 | 12,026 | 25.37% | 3.99% |
| captain_archetype | pocket | QB Captain | 12 | 22,497 | 14.76% | 0.55% |
| captain_archetype | pocket | Both QBs | 5 | 9,431 | 13.35% | 0.0848% |
| captain_archetype | pocket | QB Captain + both QBs | 5 | 9,431 | 13.35% | 0.0848% |
| captain_archetype | unknown | QB Captain | 7 | 36 | 0.00% | 0.00% |

### Salary level

| Dimension | Bucket | Construction | Games | Entries | Top 10 rate | Top 1 rate |
| --- | --- | --- | --- | --- | --- | --- |
| captain_qb_salary | 9000-10400 | QB Captain | 11 | 153,378 | 11.76% | 0.92% |
| captain_qb_salary | 9000-10400 | Both QBs | 9 | 56,097 | 10.98% | 0.87% |
| captain_qb_salary | 9000-10400 | QB Captain + both QBs | 9 | 56,097 | 10.98% | 0.87% |
| captain_qb_salary | <9000 | QB Captain | 11 | 323 | 1.86% | 0.31% |
| captain_qb_salary | >=10500 | QB Captain | 3 | 56,893 | 18.58% | 2.21% |
| captain_qb_salary | >=10500 | Both QBs | 3 | 24,198 | 37.81% | 5.20% |
| captain_qb_salary | >=10500 | QB Captain + both QBs | 3 | 24,198 | 37.81% | 5.20% |
| captain_qb_salary | unknown | QB Captain | 1 | 11,875 | 5.97% | 0.32% |
| combined_starting_qb_salary | 38-42% | QB Captain | 9 | 163,368 | 12.96% | 1.20% |
| combined_starting_qb_salary | 38-42% | Both QBs | 9 | 236,333 | 12.08% | 1.38% |
| combined_starting_qb_salary | 38-42% | QB Captain + both QBs | 9 | 73,420 | 18.32% | 1.78% |
| combined_starting_qb_salary | >42% | QB Captain | 1 | 17,984 | 13.63% | 2.46% |
| combined_starting_qb_salary | >42% | Both QBs | 1 | 29,985 | 25.52% | 4.31% |
| combined_starting_qb_salary | >42% | QB Captain + both QBs | 1 | 6,875 | 27.08% | 6.43% |
| combined_starting_qb_salary | unknown | QB Captain | 2 | 41,117 | 13.85% | 0.75% |

### 5–1, 4–2 and 3–3 team construction

| Dimension | Bucket | Construction | Games | Entries | Top 10 rate | Top 1 rate |
| --- | --- | --- | --- | --- | --- | --- |
| team_split | 3-3 | QB Captain | 12 | 72,384 | 12.08% | 1.09% |
| team_split | 3-3 | Both QBs | 10 | 116,683 | 10.81% | 1.39% |
| team_split | 3-3 | QB Captain + both QBs | 10 | 34,848 | 19.34% | 1.90% |
| team_split | 4-2 | QB Captain | 12 | 105,415 | 12.78% | 0.98% |
| team_split | 4-2 | Both QBs | 10 | 127,182 | 13.35% | 0.95% |
| team_split | 4-2 | QB Captain + both QBs | 10 | 37,328 | 16.25% | 1.58% |
| team_split | 5-1 | QB Captain | 12 | 44,670 | 15.91% | 2.01% |
| team_split | 5-1 | Both QBs | 10 | 22,453 | 29.43% | 7.64% |
| team_split | 5-1 | QB Captain + both QBs | 10 | 8,119 | 30.85% | 6.08% |

### Winning versus losing team QB Captain (audit only)

| Dimension | Bucket | Construction | Games | Entries | Top 10 rate | Top 1 rate |
| --- | --- | --- | --- | --- | --- | --- |
| winning_team_captain_audit | losing_team | QB Captain | 11 | 111,297 | 10.89% | 0.90% |
| winning_team_captain_audit | losing_team | Both QBs | 9 | 43,855 | 20.62% | 1.77% |
| winning_team_captain_audit | losing_team | QB Captain + both QBs | 9 | 43,855 | 20.62% | 1.77% |
| winning_team_captain_audit | unknown | QB Captain | 1 | 8,706 | 7.88% | 0.10% |
| winning_team_captain_audit | unknown | Both QBs | 1 | 2,499 | 12.44% | 0.00% |
| winning_team_captain_audit | unknown | QB Captain + both QBs | 1 | 2,499 | 12.44% | 0.00% |
| winning_team_captain_audit | winning_team | QB Captain | 11 | 102,466 | 16.12% | 1.66% |
| winning_team_captain_audit | winning_team | Both QBs | 9 | 33,941 | 17.54% | 2.85% |
| winning_team_captain_audit | winning_team | QB Captain + both QBs | 9 | 33,941 | 17.54% | 2.85% |

### Retrospective schedule markets (audit only)

| Dimension | Bucket | Construction | Games | Entries | Top 10 rate | Top 1 rate |
| --- | --- | --- | --- | --- | --- | --- |
| favorite_captain_audit | favorite | QB Captain | 12 | 127,388 | 17.41% | 1.65% |
| favorite_captain_audit | favorite | Both QBs | 10 | 41,663 | 27.37% | 3.11% |
| favorite_captain_audit | favorite | QB Captain + both QBs | 10 | 41,663 | 27.37% | 3.11% |
| favorite_captain_audit | underdog | QB Captain | 12 | 95,081 | 7.51% | 0.64% |
| favorite_captain_audit | underdog | Both QBs | 10 | 38,632 | 10.11% | 1.16% |
| favorite_captain_audit | underdog | QB Captain + both QBs | 10 | 38,632 | 10.11% | 1.16% |
| game_total_audit | 43-49 | QB Captain | 8 | 172,974 | 13.79% | 1.35% |
| game_total_audit | 43-49 | Both QBs | 7 | 207,143 | 13.63% | 1.66% |
| game_total_audit | 43-49 | QB Captain + both QBs | 7 | 67,799 | 19.14% | 2.38% |
| game_total_audit | <43 | QB Captain | 1 | 22,555 | 14.05% | 1.09% |
| game_total_audit | <43 | Both QBs | 1 | 40,565 | 13.65% | 1.51% |
| game_total_audit | <43 | QB Captain + both QBs | 1 | 8,925 | 18.83% | 0.46% |
| game_total_audit | >49 | QB Captain | 3 | 26,940 | 8.52% | 0.52% |
| game_total_audit | >49 | Both QBs | 2 | 18,610 | 13.10% | 2.73% |
| game_total_audit | >49 | QB Captain + both QBs | 2 | 3,571 | 18.31% | 2.58% |
| spread_audit | close <=3 | QB Captain | 5 | 107,662 | 12.95% | 1.20% |
| spread_audit | close <=3 | Both QBs | 4 | 129,824 | 13.43% | 1.87% |
| spread_audit | close <=3 | QB Captain + both QBs | 4 | 33,885 | 13.69% | 2.09% |
| spread_audit | moderate 3-7 | QB Captain | 7 | 114,807 | 13.39% | 1.23% |
| spread_audit | moderate 3-7 | Both QBs | 6 | 136,494 | 13.75% | 1.55% |
| spread_audit | moderate 3-7 | QB Captain + both QBs | 6 | 46,410 | 22.99% | 2.24% |

There are no pregame-supported 43–49 total or >7 spread games in this sample. Historical pregame large-favorite comparisons remain unavailable. Archetypes use the mean carries in the last up-to-three completed regular-season games: pocket ≤1.67, mobile (1.67, 3.33], high-rush >3.33; these fixed descriptive cutoffs approximate existing research buckets. They do not measure designed runs, scramble rate or goal-line role. Unknown/sparse prior history is retained and sample sizes are shown. No fitted effect or rushing-specific penalty is warranted.

QB salary is FLEX salary. Combined starting-QB salary is the sum of the two FLEX salaries divided by the $50,000 cap, a slate affordability measure. If one QB is Captain, the actual two-QB roster cost adds another half of that QB’s FLEX salary. Missing Showdown salaries remain unknown; Classic salaries are not substituted. Favorite/archetype/which-team Captain strata condition on QB-Captain entries, so their baseline is that stratum rather than all non-QB Captains. Within a bucket several contests can still represent one underlying game.

Winning-team labels cannot be used as pregame optimizer conditions. The CAR–DET schedule record lacks final team scores, so its winning/losing-team label remains unknown even though final contest standings are available.

## Duplication, wins and payouts (H, I)

Duplicate signatures preserve canonical Captain identity and sort the five FLEX identities. Different FLEX orderings are the same lineup; the same six players with a different Captain are different lineups. Counts below are entry-weighted total copies including the entry itself (additional opponents = copies − 1), within each contest. Uniqueness means exactly one copy.

| Construction | Mean copies | Median copies | Unique entries | Top 10 entries duplicated | Tied-first entries | Median first-place chop size |
| --- | --- | --- | --- | --- | --- | --- |
| QB Captain | 78.54 | 24.00 | 8.15% | 95.82% | 122 | 48.00 |
| Non-QB Captain | 67.42 | 22.00 | 8.92% | 95.30% | 186 | 38.00 |
| Both QBs | 98.46 | 31.00 | 6.32% | 96.33% | 12 | 2.00 |
| Exactly one QB | 55.16 | 20.00 | 9.34% | 94.21% | 236 | 48.00 |
| Zero QB | 29.98 | 8.00 | 18.38% | 89.93% | 1 | 1.00 |
| QB Captain + both QBs | 92.16 | 25.00 | 7.50% | 96.02% | 9 | 2.00 |
| QB Captain + one QB | 53.18 | 21.00 | 8.94% | 93.94% | 55 | 48.00 |
| Non-QB Captain + both QBs | 101.18 | 34.00 | 5.82% | 96.56% | 3 | 2.00 |
| Non-QB Captain + one QB | 55.81 | 19.00 | 9.47% | 94.29% | 181 | 38.00 |
| Non-QB Captain + zero QB | 29.98 | 8.00 | 18.38% | 89.93% | 1 | 1.00 |

**Top-percentile strength does not imply first-place or payout strength.** Both-QB entries have higher pooled top-10% and top-1% rates, yet much lower actual winner rates. A handful of tied winning rosters can create many winning entries in the one-QB group. The winner index and clustered intervals are shown separately; this is a reason to investigate tournament value rather than optimize solely for top-10% frequency.

No normalized historical payout tiers are stored. One exact-native match, contest **195943257**, has a complete cash ladder, entry fee $1 and field size 8,917 in a saved observation. ROI below is reconstructed for that one contest only, with 8,871 classified entries; it is not an overall historical ROI estimate. Tied scores share the sum of prizes at all occupied ranks, including ties involving different rosters. This follows [DraftKings tie rules](https://support.draftkings.com/dk/en-us/what-happens-when-i-tie-with-others-in-a-fantasy-sports-contest?id=kb_article_view&sysparm_article=KB0010633). Six-player roster and Captain conventions follow [DraftKings Showdown overview](https://support.draftkings.com/dk/en-us/game-style-showdowns-overview?id=kb_article_view&sysparm_article=KB0010694).

| Construction | Economic entries | Reconstructed ROI (one game) | Average cash reduction from all score ties |
| --- | --- | --- | --- |
| QB Captain | 1,344 | -68.42% | $0.00 |
| Non-QB Captain | 7,527 | -6.00% | $0.10 |
| Both QBs | 1,182 | -72.12% | $0.00 |
| Exactly one QB | 6,096 | -27.96% | $0.03 |
| Zero QB | 1,564 | 77.69% | $0.36 |
| QB Captain + both QBs | 281 | -84.34% | $0.00 |
| QB Captain + one QB | 1,050 | -63.76% | $0.00 |
| Non-QB Captain + both QBs | 901 | -68.31% | $0.00 |
| Non-QB Captain + one QB | 5,046 | -20.51% | $0.04 |
| Non-QB Captain + zero QB | 1,564 | 77.69% | $0.36 |

The reduction compares the prize at an entry’s displayed starting rank with its split payout. It includes all score ties and cannot attribute the loss exclusively to identical-lineup duplication. There is no calibrated ex ante win probability or payout distribution, so **expected future payout impact remains unavailable**. Zero-QB profitability on this single game does not outweigh its weaker top-percentile rates across games.

Actual-score optimum, actual rank-1 roster, top 1%, and top 10% are separate concepts throughout. The existing oracle’s 45 games (22 in 2024, 18 in 2025, five in 2026) and 11 QB optimal Captains are background only; zero oracle results enter any standings numerator or denominator.

## Current optimizer audit (O)

This is a review of the working-tree implementation and frozen saved-output inventory, not a controlled causal backtest of those rules. Production files were already modified before this task, and a concurrent optimizer edit was detected during final checks. The reviewed QB mechanisms were rechecked after that edit. Audited source copies and hashes are retained under `artifacts/showdown_qb_construction/audited_code/` and `source_hashes.json`; later working-tree edits do not change this audit. No optimizer rule, projection, default, job or database state was changed by this research task.

### Confirmed code mechanisms

- `build_showdown_captain_prior` multiplies Captain selector score by `(1−s) + s × max(0.05, class_count × position_probability)`. Configured strength is **0.35** and the artifact is `docs/showdown_captain_model_2024_2025.json`. It predicts actual-score optimal Captain position, not realized contest success or payout. In the historical-mix fallback (five model classes), QB 24.39% becomes **1.07683×** and WR 41.46% becomes **1.37561×**. QB receives positive credit, but WR receives substantially more. A rushing-specific prior in the newer oracle remains shadow-only.
- The strategy hard-correlations branch requires a team’s starting QB if two same-team WR/TE are selected; WR/TE Captain also requires that team’s QB. Pocket QB Captain requires two own WR/TE, while high-rush QB Captain requires one. This can indirectly pull the opposing QB into a lineup when the opposing pass-catcher stack reaches two.
- A `shootout` script directly requires a QB on **each** team. The legacy five-lineup v3 script schedule has two shootout slots out of five. That is a structural two-QB requirement in those solves, not an empirical demonstration of tournament superiority. Later candidate portfolio selection can alter which discoveries are actually selected.
- Modern v3/single-entry/three-max/small-max paths saturate positive correlation rewards: **0.60 + 0.30 + 0.10** for the first three pass catchers and **0.45** for one opposing WR/TE bring-back per selected QB, before QB-quality scaling. With both QBs selected, each team can activate its own reward set (maximum 1.45 per QB). Generic QB/pass-catcher, bring-back, opposing-pass-catcher and QB/receiver-Captain pair bonuses are removed in the saturated path. They are not all stacked together there.
- The bring-back soft reward targets opposing WR/TE, not the opposing QB directly. There is no basis for asserting that a QB Captain automatically forces both QBs in every strategy. Historical versions, cash paths and current paths differ. Individual starting-QB exposure defaults can be 100%; that is not a joint two-QB portfolio cap.

Relevant functions are in [optimizer.py](backend/app/product_services/optimizer.py), [lineup_correlation_scoring.py](backend/app/product_services/lineup_correlation_scoring.py) and [showdown_portfolio_selection.py](backend/app/product_services/showdown_portfolio_selection.py). Model evaluation in the configured Captain artifact reports 41 slates, 33 walk-forward evaluations and optimal-position accuracy lift; these metrics do not validate top-1% finish, first place, ROI or duplication.

### Quantified saved-output effect

Across **239 saved runs / 569 saved six-slot lineups**, QB Captain occurs in 27.24%, two positional QBs in 72.76%, and QB Captain + two positional QBs in 20.56%. These are repeated local runs, not independent contests or verified submissions. One older roster has three positional QBs and stays in an “other QBs” audit row. Starting identities are not retroactively assumed for every saved run.

The 326 saved v3 lineups contain two positional QBs in 70.86%. Deduplicating physical roster by stored season/week/slate leaves 152 rosters overall. Saved-output exposure is much larger than the historical field’s two-starter exposure, but mixes slates, objectives and versions; it is an overconcentration diagnostic, not proof of a negative expected return.

| Saved construction (positional QB audit) | Lineups | Avg Captain-prior contribution | Avg correlation contribution | Captain multiplier range |
| --- | --- | --- | --- | --- |
| Non-QB Captain + both QBs | 297 | 11.70 | 2.38 | 0.69–1.38 |
| Non-QB Captain + one QB | 111 | 11.69 | 1.14 | 1.00–1.38 |
| Non-QB Captain + zero QB | 6 | 8.82 | -0.33 | 1.00–1.38 |
| QB Captain + both QBs | 117 | 2.83 | 2.76 | 1.00–1.08 |
| QB Captain + one QB | 37 | 1.23 | 0.91 | 1.00–1.08 |
| QB Captain + other QBs | 1 | 0.00 | 0.00 | 1.00–1.00 |

Saved quality-eligible candidate sets are available in **19 runs**. Holding those candidates and their quality eligibility fixed, removing reported score components produces the following individual-best-candidate rank changes. This does not regenerate candidates or reoptimize exposure-feasible portfolios.

| Removed score contribution | Changed best rank | Unchanged best rank |
| --- | --- | --- |
| correlation | 1 | 18 |
| captain_position_prior_contribution | 12 | 7 |
| both | 13 | 6 |

Of these 19 reports, nine have complete canonical candidate-position coverage sufficient to classify both compared rosters. Among those nine, removing Captain-position prior changes every best candidate: two move from non-QB Captain/two QBs to non-QB Captain/one QB, and seven move **toward QB Captain/two QBs**. Removing correlation alone changes none of those nine constructions. The other ten reports have insufficient complete candidate roster identity for this construction comparison, though their stored rank changes remain observable.

This directly cautions against the claim that the current prior is uniquely inflating QB Captain. The confirmed issue is a surrogate objective and substantial two-QB generation pressure, with effect sizes attributable to constraints versus scores not isolated by an end-to-end historical A/B. A same-pool, same-policy, prelock candidate-generation and portfolio replay across many independent games remains necessary before assigning causality to each rule.

## Reproducibility, artifacts and checks

- Standings capture uses an enforced `REPEATABLE READ READ ONLY` transaction; primary inputs are hashed in `inputs/manifest.json`. Recovery/identity/QB-stat supplements were read in separate read-only transactions minutes later, so they are not claimed to be part of the exact same MVCC snapshot. Every supplemental input and market archive is hashed in `analysis.json`.
- Recompute from saved inputs: `PYTHONPATH=. .venv/bin/python scripts/analyze_showdown_qb_construction.py`; render: `PYTHONPATH=. .venv/bin/python scripts/render_showdown_qb_construction.py`. For a future database capture, use `scripts/capture_showdown_qb_construction.py --output <new-directory>`; existing snapshots are never overwritten.
- Targeted validation: `PYTHONPATH=. .venv/bin/python -m pytest scripts/test_showdown_qb_construction.py -q`. Checks cover ties, tiny fields, medians, source-native/canonical identity conflicts, backups, after-lock starter evidence, prior-stat leakage, cash tie splits, missing-roster bounds and game-cluster comparisons.
- Main JSON: [analysis.json](artifacts/showdown_qb_construction/analysis.json). Tables: [summary.csv](artifacts/showdown_qb_construction/summary.csv), [contest_weighted.csv](artifacts/showdown_qb_construction/contest_weighted.csv), [comparisons.csv](artifacts/showdown_qb_construction/comparisons.csv), [contest_inventory.csv](artifacts/showdown_qb_construction/contest_inventory.csv), [contest_metrics.csv](artifacts/showdown_qb_construction/contest_metrics.csv), [rate_confidence_intervals.csv](artifacts/showdown_qb_construction/rate_confidence_intervals.csv), [sensitivities.csv](artifacts/showdown_qb_construction/sensitivities.csv).
- Optimizer attribution: [optimizer_lineups.csv](artifacts/showdown_qb_construction/optimizer_lineups.csv), [optimizer_runs.csv](artifacts/showdown_qb_construction/optimizer_runs.csv), [optimizer_candidate_rerank.csv](artifacts/showdown_qb_construction/optimizer_candidate_rerank.csv). Unknown roster records are retained separately; no raw source is deleted or overwritten.

## Final decision table (P)

All displayed usage/rates are entry-weighted complete-cohort percentages; relative lift is top 10% / top 1%. Evidence strength reflects games, stability and economics, not raw entry count.

| Construction | Field usage | Top-10% rate | Top-1% rate | Winner rate | Relative lift (10 / 1) | Evidence strength | Recommended optimizer treatment |
| --- | --- | --- | --- | --- | --- | --- | --- |
| QB Captain | 24.71% | 13.18% | 1.22% | 0.0548% | 1.29× / 1.10× | Limited; season/starter-sensitive | No new penalty, exclusion or cap |
| Non-QB Captain | 75.29% | 9.21% | 1.07% | 0.0274% | 0.90× / 0.97× | Limited; season/starter-sensitive | No new penalty, exclusion or cap |
| Both QBs | 36.31% | 13.60% | 1.71% | 0.0045% | 1.33× / 1.50× | Limited; season/starter-sensitive | No new penalty, exclusion or cap |
| Exactly one QB | 55.96% | 8.73% | 0.88% | 0.0575% | 0.85× / 0.78× | Limited; season/starter-sensitive | No new penalty, exclusion or cap |
| Zero QB | 7.72% | 5.45% | 0.27% | 0.0018% | 0.53× / 0.24× | Limited; weak percentile results, one-game ROI exception | Retain eligibility; no boost |
| QB Captain + both QBs | 10.95% | 19.07% | 2.17% | 0.0112% | 1.86× / 1.91× | Limited; season/starter-sensitive | No new penalty, exclusion or cap |
| QB Captain + one QB | 13.67% | 8.28% | 0.65% | 0.0549% | 0.81× / 0.58× | Limited; season/starter-sensitive | No new penalty, exclusion or cap |
| Non-QB Captain + both QBs | 25.36% | 11.23% | 1.51% | 0.0016% | 1.10× / 1.33× | Limited; season/starter-sensitive | No new penalty, exclusion or cap |

**Concrete next recommendation:** make no optimizer rule change from this study. Keep QB Captain and both starters legal, including rare exceptions. Before any future adjustment, run chronological shadow A/Bs that separate Captain-position prior, hard stack/script constraints and saturated correlation scoring; evaluate first-place/chop-adjusted return as well as top-10% and top-1% rates. A soft cap/penalty is a candidate to test, not a result established here. No recommendation is tuned to Week 4 Monday Night.
