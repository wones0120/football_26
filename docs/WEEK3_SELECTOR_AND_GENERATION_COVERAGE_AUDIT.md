# Week 3 frozen-pool selector and generation coverage audit

Read-only retrospective shadow evaluation. Candidate pools were read directly from saved runs and hashed at audit time;
older runs without a persisted manifest cannot be independently hash-matched to their creation state. Eligible runs required
saved kickoff evidence after both run creation and data cutoff. Actuals were joined only after ranking.
Runs below 90% resolved candidate coverage were excluded. No production weights or defaults changed.

## Executive summary

- Sunday shows both a scoreable generation gap and a selection gap: the best scoreable generated lineup reached 157.00, while the saved portfolio reached 139.20. 20 of 212 candidates remain unscored, so the generation ceiling is a lower bound.
- Cross-slate evidence is unavailable: all eligible scored Classic pools are Week 3 Sunday Main research runs with highly overlapping inputs.
- Geno was eligible and four QB-family constructions were legal; two were sequential and two were added by exact-family discovery. His strongest saved selector rank was 118. This is an objective/search concentration finding, not a case for forcing him.
- Bring-backs existed in 105 of 212 candidates. The original portfolio objective plus 80% player exposure cap selected five no-bring-back lineups. This is selection, not absent legal generation.
- No safe original-input generator replay is claimed. The saved run does not contain a complete immutable solver-input snapshot for all 535 eligible players. The G1–G5 generation shadows remain pending.

## Eligible historical frozen Classic pools

| Run | Slate | Scoreable / saved | A top 5 best | B top 5 best | C top 5 best | E top 5 best |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| a6d7f5e7 | 2026 W3 SUNDAY_MAIN | 109/120 | 117.86 | 119.50 | 126.60 | 119.50 |
| 3699d1f9 | 2026 W3 SUNDAY_MAIN | 196/214 | 117.86 | 140.70 | 117.44 | 117.60 |
| c8164895 | 2026 W3 SUNDAY_MAIN | 192/212 | 117.86 | 119.50 | 117.44 | 119.50 |
| 84a32d00 | 2026 W3 SUNDAY_MAIN | 192/212 | 117.86 | 119.50 | 117.44 | 119.50 |
| 2ef9ee7e | 2026 W3 SUNDAY_MAIN | 192/212 | 117.86 | 119.50 | 117.44 | 119.50 |

These five are the only saved Classic pools with both strict timing and at least 90% resolved actuals.
Four 2026 W2 Sunday Main pools pass timing but have no imported Sunday Main actuals; later W2 Sunday Late pools fail timing.
These Week 3 runs are related research runs, not five independent slate observations.

### Full cross-run variant comparison

| Run | Selector | Top-5 best | Top-5 avg | Spearman | Regret ≥ |
| --- | --- | ---: | ---: | ---: | ---: |
| a6d7f5e7 | A_existing | 117.86 | 106.07 | 0.198 | 39.14 |
| a6d7f5e7 | B_mean | 119.50 | 108.32 | 0.277 | 37.50 |
| a6d7f5e7 | C_ceiling | 126.60 | 112.02 | 0.334 | 30.40 |
| a6d7f5e7 | E_without_context_correlation | 119.50 | 111.07 | 0.293 | 37.50 |
| a6d7f5e7 | D_mean_0.50_ceiling_0.50 | 126.60 | 112.02 | 0.331 | 30.40 |
| a6d7f5e7 | D_mean_0.35_ceiling_0.65 | 126.60 | 112.02 | 0.334 | 30.40 |
| a6d7f5e7 | D_mean_0.65_ceiling_0.35 | 126.60 | 112.02 | 0.327 | 30.40 |
| 3699d1f9 | A_existing | 117.86 | 110.15 | 0.070 | 40.84 |
| 3699d1f9 | B_mean | 140.70 | 113.52 | 0.133 | 18.00 |
| 3699d1f9 | C_ceiling | 117.44 | 108.59 | 0.242 | 41.26 |
| 3699d1f9 | E_without_context_correlation | 117.60 | 110.11 | 0.127 | 41.10 |
| 3699d1f9 | D_mean_0.50_ceiling_0.50 | 140.70 | 116.10 | 0.207 | 18.00 |
| 3699d1f9 | D_mean_0.35_ceiling_0.65 | 140.70 | 116.48 | 0.222 | 18.00 |
| 3699d1f9 | D_mean_0.65_ceiling_0.35 | 140.70 | 113.52 | 0.186 | 18.00 |
| c8164895 | A_existing | 117.86 | 106.07 | 0.027 | 39.14 |
| c8164895 | B_mean | 119.50 | 108.48 | 0.110 | 37.50 |
| c8164895 | C_ceiling | 117.44 | 108.59 | 0.257 | 39.56 |
| c8164895 | E_without_context_correlation | 119.50 | 112.13 | 0.101 | 37.50 |
| c8164895 | D_mean_0.50_ceiling_0.50 | 126.60 | 114.08 | 0.201 | 30.40 |
| c8164895 | D_mean_0.35_ceiling_0.65 | 119.50 | 112.24 | 0.223 | 37.50 |
| c8164895 | D_mean_0.65_ceiling_0.35 | 126.60 | 114.08 | 0.177 | 30.40 |
| 84a32d00 | A_existing | 117.86 | 106.07 | 0.027 | 39.14 |
| 84a32d00 | B_mean | 119.50 | 108.48 | 0.110 | 37.50 |
| 84a32d00 | C_ceiling | 117.44 | 108.59 | 0.257 | 39.56 |
| 84a32d00 | E_without_context_correlation | 119.50 | 112.13 | 0.101 | 37.50 |
| 84a32d00 | D_mean_0.50_ceiling_0.50 | 126.60 | 114.08 | 0.201 | 30.40 |
| 84a32d00 | D_mean_0.35_ceiling_0.65 | 119.50 | 112.24 | 0.223 | 37.50 |
| 84a32d00 | D_mean_0.65_ceiling_0.35 | 126.60 | 114.08 | 0.177 | 30.40 |
| 2ef9ee7e | A_existing | 117.86 | 106.07 | 0.027 | 39.14 |
| 2ef9ee7e | B_mean | 119.50 | 108.48 | 0.110 | 37.50 |
| 2ef9ee7e | C_ceiling | 117.44 | 108.59 | 0.257 | 39.56 |
| 2ef9ee7e | E_without_context_correlation | 119.50 | 112.13 | 0.101 | 37.50 |
| 2ef9ee7e | D_mean_0.50_ceiling_0.50 | 126.60 | 114.08 | 0.201 | 30.40 |
| 2ef9ee7e | D_mean_0.35_ceiling_0.65 | 119.50 | 112.24 | 0.223 | 37.50 |
| 2ef9ee7e | D_mean_0.65_ceiling_0.35 | 126.60 | 114.08 | 0.177 | 30.40 |

## Sunday frozen-pool selector comparison

All top-K values are observed among scoreable original candidates. Regret is a lower bound.
Selector A ranks by the saved objective; its raw top five differ from the globally selected five (ranks 1, 3, 7, 10, 58) because production applies an 80% player exposure cap.
Mean/ceiling blends use within-pool min–max normalization. E subtracts only saved context and correlation components.

| Selector | Top 1 | Top 3 | Top 5 | Top 10 | Top 20 | Top-5 avg | Spearman | Pearson | Regret ≥ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A_existing | 117.86 | 117.86 | 117.86 | 146.90 | 147.40 | 106.07 | 0.027 | -0.013 | 39.14 |
| B_mean | 114.70 | 119.50 | 119.50 | 139.50 | 142.90 | 108.48 | 0.110 | 0.075 | 37.50 |
| C_ceiling | 114.70 | 117.44 | 117.44 | 143.24 | 143.24 | 108.59 | 0.257 | 0.210 | 39.56 |
| E_without_context_correlation | 114.70 | 117.60 | 119.50 | 146.90 | 146.90 | 112.13 | 0.101 | 0.040 | 37.50 |
| D_mean_0.50_ceiling_0.50 | 114.70 | 119.50 | 126.60 | 131.30 | 143.24 | 114.08 | 0.201 | 0.153 | 30.40 |
| D_mean_0.35_ceiling_0.65 | 114.70 | 119.50 | 119.50 | 131.30 | 143.24 | 112.24 | 0.223 | 0.172 | 37.50 |
| D_mean_0.65_ceiling_0.35 | 114.70 | 119.50 | 126.60 | 126.60 | 146.90 | 114.08 | 0.177 | 0.131 | 30.40 |

No variant's raw top five reached the top-20% field line in any of the three imported contests. The structured JSON contains top-5 medians, actual-rank bounds, and per-contest top-20/10/5/1% attainment.
The saved objective did not demonstrate a repeatable advantage over mean or ceiling on these related Week 3 pools; its full-pool Spearman was 0.027 versus 0.110 for mean and 0.257 for summed ceiling in the target run. This does not establish a better production weight.
The strongest scoreable saved candidate was pregame rank 54 with 157.00 actual points. Its saved mean/P90 were 134.78/235.70.

### Original selected portfolio

| Saved rank | QB | Stack | Bring-backs | Actual |
| ---: | --- | --- | ---: | ---: |
| 1 | Jared Goff | QB+2 | 0 | 117.86 |
| 3 | Tyler Shough | QB+2 | 0 | 117.60 |
| 7 | Tyler Shough | QB+2 | 0 | 113.50 |
| 10 | Tyler Shough | QB+2 | 0 | 139.20 |
| 58 | Jared Goff | QB+3 | 0 | 96.46 |

## Sunday candidate coverage

All 25 eligible QBs have at least one saved candidate. Ranks are among those 25 eligible QBs; ownership is from the pinned pregame run.

| QB | Salary | Mean / rank | P90 / rank | Own % / rank | Total / rank | Team total | Spread | Generated | Selected | Stack families |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Aaron Rodgers | 5000 | 9.68 / #25 | 20.62 / #25 | 1.32 / #19 | 42.50 / #22 | 19.50 | 3.50 | 4 | 0 | QB+1: 1, QB+1+1 bring-back: 1, QB+2: 1, QB+2+1 bring-back: 1 |
| Baker Mayfield | 5300 | 15.04 / #16 | 25.76 / #17 | 2.35 / #14 | 42.50 / #19 | 20.50 | 1.50 | 4 | 0 | QB+1: 1, QB+1+1 bring-back: 1, QB+2: 1, QB+2+1 bring-back: 1 |
| Brock Purdy | 6500 | 18.77 / #6 | 29.49 / #7 | unavailable / #— | 47.50 / #7 | 28.00 | -8.50 | 4 | 0 | QB+1+1 bring-back: 1, QB+2: 1, QB+1: 1, QB+2+1 bring-back: 1 |
| Bryce Young | 5600 | 19.06 / #3 | 30.00 / #2 | 4.46 / #11 | 42.50 / #18 | 22.50 | -2.50 | 21 | 0 | QB+2+1 bring-back: 11, QB+1+1 bring-back: 8, QB+2: 1, QB+1: 1 |
| C.J. Stroud | 5500 | 16.18 / #14 | 27.12 / #14 | 2.53 / #13 | 43.50 / #16 | 23.00 | -2.50 | 4 | 0 | QB+1: 1, QB+2: 1, QB+1+1 bring-back: 1, QB+2+1 bring-back: 1 |
| Cam Ward | 5100 | 12.59 / #21 | 23.53 / #20 | 0.94 / #23 | 40.50 / #24 | 18.50 | 3.50 | 4 | 0 | QB+1: 1, QB+2: 1, QB+1+1 bring-back: 1, QB+2+1 bring-back: 1 |
| Dak Prescott | 6700 | 18.76 / #7 | 29.70 / #5 | 7.73 / #3 | 52.50 / #1 | 24.75 | 3.00 | 7 | 0 | QB+2+2 bring-back: 3, QB+2+1 bring-back: 1, QB+1+1 bring-back: 1, QB+2: 1, QB+1: 1 |
| Daniel Jones | 5000 | 11.05 / #23 | 21.99 / #23 | unavailable / #— | 43.50 / #14 | 20.50 | 2.50 | 4 | 0 | QB+1: 1, QB+2: 1, QB+1+1 bring-back: 1, QB+2+1 bring-back: 1 |
| Deshaun Watson | 4700 | 11.33 / #22 | 22.05 / #22 | 1.23 / #20 | 42.50 / #17 | 20.00 | 2.50 | 4 | 0 | QB+1+1 bring-back: 1, QB+2+1 bring-back: 1, QB+2: 1, QB+1: 1 |
| Drake Maye | 6100 | 16.48 / #12 | 27.20 / #13 | 4.78 / #9 | 45.50 / #11 | 21.25 | 3.00 | 4 | 0 | QB+1: 1, QB+1+1 bring-back: 1, QB+2: 1, QB+2+1 bring-back: 1 |
| Geno Smith | 4900 | 17.62 / #10 | 28.34 / #10 | 1.44 / #18 | 48.50 / #6 | 21.00 | 6.50 | 4 | 0 | QB+2+1 bring-back: 1, QB+1+1 bring-back: 1, QB+1: 1, QB+2: 1 |
| Jacoby Brissett | 4800 | 16.45 / #13 | 27.39 / #12 | 3.11 / #12 | 47.50 / #8 | 19.50 | 8.50 | 9 | 0 | QB+2: 6, QB+1: 1, QB+2+1 bring-back: 1, QB+1+1 bring-back: 1 |
| Jameis Winston | 4000 | 10.41 / #24 | 21.35 / #24 | 1.12 / #22 | 40.50 / #25 | 22.00 | -3.50 | 4 | 0 | QB+1: 1, QB+2: 1, QB+1+1 bring-back: 1, QB+2+1 bring-back: 1 |
| Jared Goff | 6300 | 18.91 / #4 | 29.84 / #4 | 6.79 / #4 | 48.50 / #5 | 27.50 | -6.50 | 62 | 2 | QB+2: 19, QB+3+1 bring-back: 12, QB+3: 11, QB+2+1 bring-back: 18, QB+1: 1, QB+1+1 bring-back: 1 |
| Joe Burrow | 6600 | 18.29 / #8 | 29.23 / #8 | 5.44 / #7 | 42.50 / #21 | 23.00 | -3.50 | 4 | 0 | QB+1: 1, QB+2: 1, QB+1+1 bring-back: 1, QB+2+1 bring-back: 1 |
| Josh Allen | 8000 | 24.26 / #1 | 34.98 / #1 | 14.32 / #1 | 50.50 / #4 | 28.75 | -7.00 | 4 | 0 | QB+2: 1, QB+1: 1, QB+2+1 bring-back: 1, QB+1+1 bring-back: 1 |
| Justin Herbert | 5800 | 15.50 / #15 | 26.22 / #15 | 4.53 / #10 | 50.50 / #3 | 21.75 | 7.00 | 4 | 0 | QB+1: 1, QB+1+1 bring-back: 1, QB+2: 1, QB+2+1 bring-back: 1 |
| Kirk Cousins | 4800 | 14.45 / #18 | 25.17 / #18 | 1.56 / #17 | 43.50 / #13 | 20.25 | 3.00 | 4 | 0 | QB+2+1 bring-back: 1, QB+1+1 bring-back: 1, QB+2: 1, QB+1: 1 |
| Kyler Murray | 5100 | 14.87 / #17 | 25.81 / #16 | 2.29 / #16 | 42.50 / #20 | 22.00 | -1.50 | 4 | 0 | QB+2: 1, QB+1: 1, QB+1+1 bring-back: 1, QB+2+1 bring-back: 1 |
| Lamar Jackson | 7500 | 18.84 / #5 | 29.56 / #6 | 7.77 / #2 | 52.50 / #2 | 27.75 | -3.00 | 4 | 0 | QB+2+1 bring-back: 1, QB+1+1 bring-back: 1, QB+2: 1, QB+1: 1 |
| Malik Willis | 4900 | 12.79 / #20 | 23.51 / #21 | 1.21 / #21 | 45.50 / #10 | 17.00 | 11.50 | 4 | 0 | QB+1+1 bring-back: 1, QB+1: 1, QB+2+1 bring-back: 1, QB+2: 1 |
| Patrick Mahomes | 6200 | 17.37 / #11 | 28.31 / #11 | 6.15 / #5 | 45.50 / #9 | 28.50 | -11.50 | 4 | 0 | QB+1: 1, QB+2: 1, QB+1+1 bring-back: 1, QB+2+1 bring-back: 1 |
| Sam Darnold | 5400 | 13.18 / #19 | 24.12 / #19 | 2.31 / #15 | 40.50 / #23 | 23.75 | -7.00 | 4 | 0 | QB+1: 1, QB+2: 1, QB+1+1 bring-back: 1, QB+2+1 bring-back: 1 |
| Trevor Lawrence | 5700 | 18.01 / #9 | 28.95 / #9 | 5.55 / #6 | 45.50 / #12 | 24.25 | -3.00 | 4 | 0 | QB+2: 1, QB+1: 1, QB+2+1 bring-back: 1, QB+1+1 bring-back: 1 |
| Tyler Shough | 5400 | 19.25 / #2 | 29.97 / #3 | 5.12 / #8 | 43.50 / #15 | 23.25 | -3.00 | 33 | 3 | QB+2: 18, QB+1: 3, QB+3: 4, QB+2+1 bring-back: 5, QB+3+1 bring-back: 2, QB+1+1 bring-back: 1 |

### Stack-family distribution

| Family | Generated | Selected |
| --- | ---: | ---: |
| QB+1 | 27 (12.7%) | 0 |
| QB+1+1 bring-back | 32 (15.1%) | 0 |
| QB+2 | 65 (30.7%) | 4 |
| QB+2+1 bring-back | 56 (26.4%) | 0 |
| QB+2+2 bring-back | 3 (1.4%) | 0 |
| QB+3 | 15 (7.1%) | 1 |
| QB+3+1 bring-back | 14 (6.6%) | 0 |

The imported top-1% fields used Geno at QB in 87/159, 48/80, and 84/179 lineups. This is postgame context only; it was not used to define any shadow rank or family target.

### Pregame game-environment exposure

Counts are candidate lineups containing the listed role in each game; QB, opposing bring-back, and full-stack counts refer to the game's primary QB path.
| Game | Total | Team implied totals | QB | Pass catcher | Bring-back | RB | DST | Full stack |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ARI–SF | 47.50 | SF 28.00, ARI 19.50 | 13 | 62 | 4 | 2 | 2 | 2 |
| BAL–DAL | 52.50 | DAL 24.75, BAL 27.75 | 11 | 36 | 7 | 208 | 0 | 5 |
| BUF–LAC | 50.50 | BUF 28.75, LAC 21.75 | 8 | 8 | 4 | 21 | 12 | 2 |
| CAR–CLE | 42.50 | CAR 22.50, CLE 20.00 | 25 | 208 | 21 | 0 | 2 | 12 |
| CIN–PIT | 42.50 | PIT 19.50, CIN 23.00 | 8 | 8 | 4 | 38 | 4 | 2 |
| DET–NYJ | 48.50 | NYJ 21.00, DET 27.50 | 66 | 132 | 33 | 8 | 27 | 31 |
| HOU–IND | 43.50 | HOU 23.00, IND 20.50 | 8 | 8 | 4 | 7 | 3 | 2 |
| JAX–NE | 45.50 | NE 21.25, JAX 24.25 | 8 | 49 | 4 | 6 | 0 | 2 |
| KC–MIA | 45.50 | MIA 17.00, KC 28.50 | 8 | 38 | 4 | 117 | 56 | 2 |
| LV–NO | 43.50 | LV 20.25, NO 23.25 | 37 | 96 | 10 | 11 | 2 | 8 |
| MIN–TB | 42.50 | TB 20.50, MIN 22.00 | 8 | 52 | 4 | 4 | 30 | 2 |
| NYG–TEN | 40.50 | TEN 18.50, NYG 22.00 | 8 | 8 | 4 | 2 | 3 | 2 |
| SEA–WAS | 40.50 | SEA 23.75 | 4 | 5 | 2 | 0 | 71 | 1 |

The 52.5-total BAL–DAL game had 11 primary-QB candidates and the 50.5-total BUF–LAC game had 8, while 48.5-total DET–NYJ had 66. This shows uneven exploration before portfolio selection; saved evidence does not isolate salary optimization from correlation scoring as its cause.
Saved context-rule trigger counts are available only for the whole eligible player pool, not by game; the exact aggregate counts are in the JSON artifact.

### High-ceiling players with little generated exposure

The following descriptive screen uses saved P90 percentile ≥95 among all 535 eligible players and fewer than 5% of generated candidates; it does not use actual points.
| Player | Position | Mean | P90 | Ownership | Salary | Generated | Selected | Game total |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Josh Allen | QB | 24.26 | 34.98 | 14.32 | 8000 | 4 | 0 | 50.50 |
| Jaxon Smith-Njigba | WR | 19.19 | 32.03 | 17.27 | 8600 | 1 | 0 | 40.50 |
| Jahmyr Gibbs | RB | 18.49 | 31.50 | 21.51 | 8800 | 0 | 0 | 48.50 |
| Jonathan Taylor | RB | 17.47 | 30.48 | 11.18 | 7600 | 7 | 0 | 43.50 |
| Ja'Marr Chase | WR | 17.00 | 29.85 | 11.27 | 8100 | 1 | 0 | 42.50 |
| Dak Prescott | QB | 18.76 | 29.70 | 7.73 | 6700 | 7 | 0 | 52.50 |
| Lamar Jackson | QB | 18.84 | 29.56 | 7.77 | 7500 | 4 | 0 | 52.50 |
| Brock Purdy | QB | 18.77 | 29.49 | 5.65 | 6500 | 4 | 0 | 47.50 |
| Christian McCaffrey | RB | 18.84 | 29.27 | 13.65 | 8300 | 1 | 0 | 47.50 |
| Joe Burrow | QB | 18.29 | 29.23 | 5.44 | 6600 | 4 | 0 | 42.50 |
| Trevor Lawrence | QB | 18.01 | 28.95 | 5.55 | 5700 | 4 | 0 | 45.50 |
| Ashton Jeanty | RB | 15.51 | 28.52 | 4.58 | 7100 | 6 | 0 | 43.50 |
| Geno Smith | QB | 17.62 | 28.34 | 1.44 | 4900 | 4 | 0 | 48.50 |
| Patrick Mahomes | QB | 17.37 | 28.31 | 6.15 | 6200 | 4 | 0 | 45.50 |
| Justin Jefferson | WR | 14.73 | 27.57 | 13.88 | 7500 | 1 | 0 | 42.50 |

A separate low-owned screen (ownership <5%, P90 percentile ≥85, at most four generated candidates) includes Brock Bowers (P90 24.70, ownership 4.2%, zero candidates) and Rashee Rice (P90 23.70, ownership 3.3%, zero candidates). Their eligibility and individual ceilings are saved; the absence of a forced legal solve prevents assigning salary, roster, or policy causality.

## Candidate similarity and funnel

- Distinct rosters: 212/212; average pairwise overlap: 3.61 of 9.
- Distinct QB paths: 25; effective QB/game/stack families: 27.24 across 105 observed families.
- Candidate pairs sharing at least 5 players: 22.19%.
- Candidate pairs sharing at least 6 players: 7.58%.
- Candidate pairs sharing at least 7 players: 1.77%.
- Candidate pairs sharing at least 8 players: 0.06%.
- Source pool 666; optimizer eligible 535; sequential 120; expanded/saved 212; selected 5.
- Sequential generation produced two Geno paths; exact QB-family discovery added two. All four legal paths were retained in the 212 saved candidates, ranked 118, 124, 133, and 139. No later pruning removed them.
- Geno's saved QB mean 17.62 and P90 28.34 ranked 10th of 25; salary $4,900, ownership 1.44%, game total 48.5, implied team total 21.0, spread +6.5. One Geno lineup had mean 138.06 and summed P90 240.69 versus selected rank 1's 135.96 and 239.19, yet its full objective was 5.3109 versus 5.4383. QB-stack, context and correlation contributions account for the rank gap in this comparison; ownership's soft objective contribution was zero.
- The first bring-back candidate was objective rank 2. It shared Amon-Ra St. Brown, Jalen Coker, Derrick Henry, and Denzel Boston with four of five selected lineups, so it could not simply be added without changing another lineup under the 80% exposure cap. The exact global selector reproduced ranks 1, 3, 7, 10, 58.
- Theoretical legal roster count, intermediate solver alternatives, and rejected quality-floor paths were not persisted. The existing architecture does not enumerate those stages.

## Portfolio diversification shadow

The JSON records all 40 predeclared overlap × distinct-QB × objective-loss configurations, including infeasible cases, exposures, overlap matrices, mean/P90 sacrifice, and actual capture.
Every F configuration keeps the saved candidate scores, so full-pool Pearson/Spearman and raw top-10/top-20 capture equal Selector A; the portfolio rows report selected top-1/3/5 capture separately.
| Overlap | Distinct QB | Loss | Status | Ranks | Best scoreable | Avg scoreable | Regret ≥ | Top-20% fields | Mean sacrifice | Ceiling sacrifice |
| ---: | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| off | False | unrestricted | feasible | 1,3,7,10,58 | 139.20 | 116.92 | 17.80 | 0 | 0.00 | 0.00 |
| off | False | 0.05 | infeasible |  | unavailable | unavailable | unavailable | 0 | unavailable | unavailable |
| off | False | 0.1 | feasible | 1,3,7,10,58 | 139.20 | 116.92 | 17.80 | 0 | 0.00 | 0.00 |
| off | False | 0.2 | feasible | 1,3,7,10,58 | 139.20 | 116.92 | 17.80 | 0 | 0.00 | 0.00 |
| off | True | unrestricted | feasible | 7,8,21,58,77 | 137.10 | 114.93 | 19.90 | 0 | 13.18 | 11.03 |
| off | True | 0.05 | infeasible |  | unavailable | unavailable | unavailable | 0 | unavailable | unavailable |
| off | True | 0.1 | feasible | 7,8,21,58,77 | 137.10 | 114.93 | 19.90 | 0 | 13.18 | 11.03 |
| off | True | 0.2 | feasible | 7,8,21,58,77 | 137.10 | 114.93 | 19.90 | 0 | 13.18 | 11.03 |
| 8 | False | unrestricted | feasible | 1,3,7,10,58 | 139.20 | 116.92 | 17.80 | 0 | 0.00 | 0.00 |
| 8 | False | 0.05 | infeasible |  | unavailable | unavailable | unavailable | 0 | unavailable | unavailable |
| 8 | False | 0.1 | feasible | 1,3,7,10,58 | 139.20 | 116.92 | 17.80 | 0 | 0.00 | 0.00 |
| 8 | False | 0.2 | feasible | 1,3,7,10,58 | 139.20 | 116.92 | 17.80 | 0 | 0.00 | 0.00 |
| 8 | True | unrestricted | feasible | 7,8,21,58,77 | 137.10 | 114.93 | 19.90 | 0 | 13.18 | 11.03 |
| 8 | True | 0.05 | infeasible |  | unavailable | unavailable | unavailable | 0 | unavailable | unavailable |
| 8 | True | 0.1 | feasible | 7,8,21,58,77 | 137.10 | 114.93 | 19.90 | 0 | 13.18 | 11.03 |
| 8 | True | 0.2 | feasible | 7,8,21,58,77 | 137.10 | 114.93 | 19.90 | 0 | 13.18 | 11.03 |
| 7 | False | unrestricted | feasible | 1,3,7,10,58 | 139.20 | 116.92 | 17.80 | 0 | 0.00 | 0.00 |
| 7 | False | 0.05 | infeasible |  | unavailable | unavailable | unavailable | 0 | unavailable | unavailable |
| 7 | False | 0.1 | feasible | 1,3,7,10,58 | 139.20 | 116.92 | 17.80 | 0 | 0.00 | 0.00 |
| 7 | False | 0.2 | feasible | 1,3,7,10,58 | 139.20 | 116.92 | 17.80 | 0 | 0.00 | 0.00 |
| 7 | True | unrestricted | feasible | 7,8,21,58,77 | 137.10 | 114.93 | 19.90 | 0 | 13.18 | 11.03 |
| 7 | True | 0.05 | infeasible |  | unavailable | unavailable | unavailable | 0 | unavailable | unavailable |
| 7 | True | 0.1 | feasible | 7,8,21,58,77 | 137.10 | 114.93 | 19.90 | 0 | 13.18 | 11.03 |
| 7 | True | 0.2 | feasible | 7,8,21,58,77 | 137.10 | 114.93 | 19.90 | 0 | 13.18 | 11.03 |
| 6 | False | unrestricted | feasible | 1,6,7,10,94 | 146.90 | 123.54 | 10.10 | 0 | 2.39 | 2.60 |
| 6 | False | 0.05 | infeasible |  | unavailable | unavailable | unavailable | 0 | unavailable | unavailable |
| 6 | False | 0.1 | feasible | 2,6,7,10,58 | 146.90 | 117.58 | 10.10 | 0 | 3.29 | 7.00 |
| 6 | False | 0.2 | feasible | 1,6,7,10,94 | 146.90 | 123.54 | 10.10 | 0 | 2.39 | 2.60 |
| 6 | True | unrestricted | feasible | 7,8,21,58,77 | 137.10 | 114.93 | 19.90 | 0 | 13.18 | 11.03 |
| 6 | True | 0.05 | infeasible |  | unavailable | unavailable | unavailable | 0 | unavailable | unavailable |
| 6 | True | 0.1 | feasible | 7,8,21,58,77 | 137.10 | 114.93 | 19.90 | 0 | 13.18 | 11.03 |
| 6 | True | 0.2 | feasible | 7,8,21,58,77 | 137.10 | 114.93 | 19.90 | 0 | 13.18 | 11.03 |
| 5 | False | unrestricted | feasible | 3,6,10,12,58 | 146.90 | 125.18 | 10.10 | 0 | 3.80 | 1.59 |
| 5 | False | 0.05 | infeasible |  | unavailable | unavailable | unavailable | 0 | unavailable | unavailable |
| 5 | False | 0.1 | feasible | 3,6,10,12,58 | 146.90 | 125.18 | 10.10 | 0 | 3.80 | 1.59 |
| 5 | False | 0.2 | feasible | 3,6,10,12,58 | 146.90 | 125.18 | 10.10 | 0 | 3.80 | 1.59 |
| 5 | True | unrestricted | feasible | 7,8,21,58,77 | 137.10 | 114.93 | 19.90 | 0 | 13.18 | 11.03 |
| 5 | True | 0.05 | infeasible |  | unavailable | unavailable | unavailable | 0 | unavailable | unavailable |
| 5 | True | 0.1 | feasible | 7,8,21,58,77 | 137.10 | 114.93 | 19.90 | 0 | 13.18 | 11.03 |
| 5 | True | 0.2 | feasible | 7,8,21,58,77 | 137.10 | 114.93 | 19.90 | 0 | 13.18 | 11.03 |

## Interpretation and remaining uncertainty

The scoreable generation pool is the binding top-10% limitation: its best 157.00 was below each imported contest's top-10% line (160.04–164.16). Selection also lost at least 17.80 points relative to that scoreable pool best. The 20 unscored candidates prevent a definitive full-pool generation conclusion.
Overlap ≤6 in shadow portfolio selection increased the best scoreable selected actual from 139.20 to 146.90 while distinct-QB selection reduced it to 137.10. This one-slate, incomplete-actual result does not support a default change.
All 212 rosters were distinct, but 208 contained Derrick Henry and 186 contained Jalen Coker. The 105 observed QB/game/stack families have an effective count of 27.24, indicating substantial core concentration despite broad QB labels.
Geno's four paths are best classified as search concentration plus objective-policy ranking, with competitive whole-lineup mean/P90 in one saved path. The causal effect of a larger Geno search remains unmeasured. Bring-back absence in the final five is portfolio-selection-limited, not a missing legal family. Other high-P90 player omissions without a forced legal solve remain insufficient evidence for a causal label.

## Actual resolution and Monday

Caleb Douglas, Bub Means, Mason Taylor, and Sincere McCormick have no Week 3 canonical DK actual in the imported Sunday observations or Week 3 canonical fact actuals. Earlier-week observations cannot establish their Week 3 scores. 20 affected candidates remain unscored.
Week 3 Monday Night standings are not imported; Monday effectiveness remains pending. The existing Learning UI refreshes a weekly report after a successful standings import when a DraftKings username is supplied.

## Shadow generation experiments

G1–G5 were not run. The original save includes eligible IDs, projection/P90, context summaries and candidate rosters, but not a complete immutable per-player solver-input snapshot with ownership, market and constraint state. Rebuilding from current tables could silently mix later inputs. The new run report records a more explicit generation funnel; a frozen replay contract is still needed before safe generation shadows.

## Evidence-based next experiment

Prospectively persist a complete pre-lock solver input snapshot and run one predeclared structural-coverage shadow against the same next Classic slate. Keep the production selector and generator defaults fixed; compare original and shadow candidate families before scoring, then score both after actuals resolve.
