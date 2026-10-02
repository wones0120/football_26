# Week 4 Dynamic Thesis Portfolio Shadow

**Completed prospective analysis.** The frozen 205-candidate pool supports **three competitive QB directions** (Lawrence, Burrow, Brissett), expressed as **four competitive stack families**, across **two canonical games: JAX@CIN and ARI@NYG** at the 0.20 selector tolerance. It does not support five strong independent game environments.

Brissett is a **GENUINE SALARY-EFFICIENCY THESIS** within the saved model: his weaker QB projection is offset by stronger non-QB allocation, especially McBride and the RB/WR core. Lawrence and Burrow still lead him on the existing selector. The recommended shadow five remain ranks **1, 6, 31, 48, 83**; the shadow 20 allocate **12 Lawrence, 4 Burrow, 4 Brissett**. These are prospective experiments, not validated contest-win claims.

## Frozen evidence and production boundary

Source optimizer: `8b5c114c-b0d2-419e-8f41-bdcbc2674c71`. Source decision cutoff: **2026-09-30T11:06:20.593580+00:00**. First saved kickoff: **2026-10-04T13:00:00-04:00**. Supplement completed pre-lock: **2026-09-30T14:13:20.228396+00:00**.

Candidate-universe SHA-256: `b60f41e6755649d556e4a494417f278aabcc2ad1c77b68f5acdaf9546b8024a4`. Preserved v3 shadow SHA-256: `a4fd29d063b396fa7be2ece432b3fd61498b210d7f8c1080748bc3ee153b2700`. Completion supplement SHA-256: `6944fe97ceecf5f9b02cfc1606ec48b26c5f657382e2bd95b53cade44408496c`.

The inputs are saved player IDs, projections, salaries, P90, ownership, pregame risk/market/context facts, and resolved solver configuration. All five saved scoring/solver file hashes match the source snapshot, and all 205 candidate selectors were replayed to within 1e-9. No live player refresh, outcomes, or postgame data was consulted. The redundant database `run_created_at` local-offset display is not the chronology authority; the saved UTC decision cutoff above is.

Production stays at overlap **4**, distinct QB paths **true**, **205 candidates**, and selected ranks **31, 48, 83, 90, 93**. Projections, player P90, selector/correlation weights, ownership logic, candidate caps and questionable-player controls are unchanged. Forced/control rosters are diagnostics and never enter the 205-candidate pool, production, or the frozen shadow portfolios.

The immutable v3 database shadow is preserved. This completion is a separate hashed local supplement with its own pre-lock timestamp; it does not rewrite v3. The initial template-only opportunity-cost JSON is superseded by the v2 completion supplement, which also searches the saved hard stack rules.

## Dynamic football discovery and interpretation

The pool discovers **47 stack families**, **15 QB directions**, and **10 primary canonical games**. No fixed number of theses is imposed.

A broad football direction is canonical game + canonical QB ID. A construction family further records QB pass-catcher count and bring-back presence. Bring-back identities/counts and one-offs are variants. QB+2 and QB+3 Lawrence families remain one Lawrence passing direction. Lawrence/JAX and Burrow/CIN are different passing directions in **the same JAX@CIN game**. Mahomes/KC and Cousins/LV likewise share **KC@LV**. None are independent game environments merely because the quarterbacks differ.

Market labels use only saved point-in-time-safe source evidence. “Passing thesis” identifies roster construction, not an inferred promise of a shootout. **All P90 totals below sum individual player P90s; they are not the 90th percentile of joint lineup outcomes.** Portfolio sums are descriptive totals, not probabilities or independent scenario counts.

## Quality tolerance and thesis depth

The global selector frontier is **5.606632** (rank 1). Tolerances are absolute selector-point losses, not percentages. A family is viable at a tolerance if at least one saved candidate lies inside it. Near-frontier depth labels are descriptive: ≥5 candidates = deep, 3–4 = moderate, 1–2 = thin, 0 = absent. Overall family labels also require selector depth: deep = ≥5 variants and best→5th drop ≤0.10; moderate = ≥3 and best→3rd drop ≤0.10; otherwise thin. These cutoffs are heuristics, not learned classes.

| Tolerance | Viable stack families | Viable QB directions | Canonical games | Candidates in window |
| --- | --- | --- | --- | --- |
| 0.05 | 2 | 1 | JAX@CIN | 20 |
| 0.10 | 3 | 2 | JAX@CIN | 49 |
| 0.15 | 3 | 2 | JAX@CIN | 75 |
| 0.20 | 4 | 3 | ARI@NYG, JAX@CIN | 84 |

**The working observation is confirmed:** at **0.20**, the leading families are Lawrence QB+2/3 with bring-back, Burrow QB+2 with bring-back, and Brissett QB+2 without bring-back. At that boundary Brissett has only two qualifying variants; this is a thin near-frontier branch.

| Tolerance | Viable family / best global rank | Count in window | Window depth |
| --- | --- | --- | --- |
| 0.05 | Trevor Lawrence QB+2 + BB / #1 | 17 | deep |
| 0.05 | Trevor Lawrence QB+3 + BB / #13 | 3 | moderate |
| 0.10 | Trevor Lawrence QB+2 + BB / #1 | 40 | deep |
| 0.10 | Trevor Lawrence QB+3 + BB / #13 | 7 | deep |
| 0.10 | Joe Burrow QB+2 + BB / #48 | 2 | thin |
| 0.15 | Trevor Lawrence QB+2 + BB / #1 | 40 | deep |
| 0.15 | Trevor Lawrence QB+3 + BB / #13 | 7 | deep |
| 0.15 | Joe Burrow QB+2 + BB / #48 | 28 | deep |
| 0.20 | Trevor Lawrence QB+2 + BB / #1 | 40 | deep |
| 0.20 | Trevor Lawrence QB+3 + BB / #13 | 7 | deep |
| 0.20 | Joe Burrow QB+2 + BB / #48 | 35 | deep |
| 0.20 | Jacoby Brissett QB+2 / no BB / #83 | 2 | thin |

### Every discovered family: viability, ranks and depth

Counts .05/.10/.15/.20 explicitly encode viability at every tolerance: zero means no viable candidate. The rank columns use the saved global selector ordering. Labels describe internal depth; a deep family can still be far below the global frontier.

| Family | Game | N | Best selector | Ranks 1 / 2 / 3 / 5 | Counts .05 / .10 / .15 / .20 | Drop best→3 / best→5 | Depth |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Trevor Lawrence QB+2 + BB | JAX@CIN | 40 | 5.607 | 1 / 2 / 3 / 5 | 17 / 40 / 40 / 40 | 0.020 / 0.027 | deep |
| Trevor Lawrence QB+3 + BB | JAX@CIN | 7 | 5.565 | 13 / 15 / 16 / 31 | 3 / 7 / 7 / 7 | 0.003 / 0.016 | deep |
| Joe Burrow QB+2 + BB | JAX@CIN | 35 | 5.529 | 48 / 49 / 50 / 52 | 0 / 2 / 28 / 35 | 0.035 / 0.052 | deep |
| Jacoby Brissett QB+2 / no BB | ARI@NYG | 7 | 5.426 | 83 / 84 / 88 / 103 | 0 / 0 / 0 / 2 | 0.048 / 0.130 | moderate |
| Trevor Lawrence QB+1 + BB | JAX@CIN | 3 | 5.400 | 85 / 87 / 89 / — | 0 / 0 / 0 / 0 | 0.025 / — | moderate |
| Joe Burrow QB+1 + BB | JAX@CIN | 1 | 5.389 | 86 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Patrick Mahomes QB+2 / no BB | KC@LV | 1 | 5.358 | 90 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Jacoby Brissett QB+1 / no BB | ARI@NYG | 1 | 5.357 | 91 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Jacoby Brissett QB+2 + BB | ARI@NYG | 1 | 5.355 | 92 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Kirk Cousins QB+2 + BB | KC@LV | 1 | 5.342 | 93 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Patrick Mahomes QB+2 + BB | KC@LV | 34 | 5.337 | 94 / 99 / 100 / 102 | 0 / 0 / 0 / 0 | 0.038 / 0.040 | deep |
| Trevor Lawrence QB+1 / no BB | JAX@CIN | 1 | 5.336 | 95 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Kirk Cousins QB+2 / no BB | KC@LV | 1 | 5.333 | 96 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Josh Allen QB+2 / no BB | NE@BUF | 1 | 5.330 | 97 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Josh Allen QB+3 + BB | NE@BUF | 4 | 5.296 | 104 / 134 / 135 / — | 0 / 0 / 0 / 0 | 0.033 / — | moderate |
| Josh Allen QB+2 + BB | NE@BUF | 8 | 5.295 | 105 / 112 / 120 / 126 | 0 / 0 / 0 / 0 | 0.019 / 0.026 | deep |
| Patrick Mahomes QB+3 + BB | KC@LV | 1 | 5.289 | 111 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| C.J. Stroud QB+2 / no BB | DAL@HOU | 1 | 5.285 | 113 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Patrick Mahomes QB+1 / no BB | KC@LV | 1 | 5.285 | 114 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| C.J. Stroud QB+2 + BB | DAL@HOU | 4 | 5.282 | 115 / 152 / 170 / — | 0 / 0 / 0 / 0 | 0.076 / — | moderate |
| Jacoby Brissett QB+1 + BB | ARI@NYG | 1 | 5.278 | 118 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Joe Burrow QB+1 / no BB | JAX@CIN | 1 | 5.277 | 119 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Josh Allen QB+1 / no BB | NE@BUF | 1 | 5.267 | 129 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Matthew Stafford QB+1 / no BB | LAR@PHI | 1 | 5.260 | 139 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Patrick Mahomes QB+1 + BB | KC@LV | 1 | 5.255 | 145 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Kirk Cousins QB+1 / no BB | KC@LV | 1 | 5.255 | 146 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Kirk Cousins QB+1 + BB | KC@LV | 1 | 5.252 | 149 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Bo Nix QB+1 / no BB | DEN@SF | 1 | 5.234 | 156 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| C.J. Stroud QB+1 / no BB | DAL@HOU | 1 | 5.228 | 157 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Jordan Love QB+1 / no BB | GB@TB | 1 | 5.227 | 158 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Jordan Love QB+1 + BB | GB@TB | 1 | 5.226 | 159 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Matthew Stafford QB+1 + BB | LAR@PHI | 1 | 5.221 | 161 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Jordan Love QB+2 + BB | GB@TB | 1 | 5.218 | 164 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Jameis Winston QB+2 / no BB | ARI@NYG | 9 | 5.214 | 165 / 166 / 175 / 180 | 0 / 0 / 0 / 0 | 0.025 / 0.041 | deep |
| Bo Nix QB+2 / no BB | DEN@SF | 1 | 5.211 | 167 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Jameis Winston QB+1 + BB | ARI@NYG | 1 | 5.207 | 168 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Jameis Winston QB+1 / no BB | ARI@NYG | 1 | 5.207 | 169 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| C.J. Stroud QB+1 + BB | DAL@HOU | 1 | 5.205 | 172 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Jameis Winston QB+2 + BB | ARI@NYG | 10 | 5.192 | 173 / 174 / 179 / 184 | 0 / 0 / 0 / 0 | 0.016 / 0.034 | deep |
| Drake Maye QB+1 / no BB | NE@BUF | 1 | 5.185 | 177 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Jordan Love QB+2 / no BB | GB@TB | 1 | 5.180 | 178 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Jalen Hurts QB+1 + BB | LAR@PHI | 1 | 5.169 | 181 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Sam Darnold QB+2 / no BB | LAC@SEA | 6 | 5.160 | 183 / 187 / 199 / 203 | 0 / 0 / 0 / 0 | 0.018 / 0.097 | deep |
| Jalen Hurts QB+1 / no BB | LAR@PHI | 1 | 5.156 | 186 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Cam Ward QB+2 + BB | TEN@BAL | 1 | 5.150 | 188 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |
| Drake Maye QB+2 + BB | NE@BUF | 4 | 5.149 | 189 / 200 / 201 / — | 0 / 0 / 0 / 0 | 0.077 / — | moderate |
| Sam Darnold QB+1 / no BB | LAC@SEA | 1 | 5.145 | 192 / — / — / — | 0 / 0 / 0 / 0 | — / — | thin |

### Every discovered family: projected quality

“Best” means the selector-leading candidate. Best 3 and best 5 mean/P90 values average the first 3/5 selector-ranked variants, using all available variants when fewer exist. Peak mean/P90 are separate maxima and may come from different rosters; they are not combined into a fictitious lineup.

| Family | Mean best / best 3 / best 5 | P90 best / best 3 / best 5 | Peak mean / P90 |
| --- | --- | --- | --- |
| Trevor Lawrence QB+2 + BB | 133.32 / 131.34 / 131.21 | 225.60 / 227.05 / 226.92 | 133.32 / 231.30 |
| Trevor Lawrence QB+3 + BB | 129.06 / 129.73 / 129.17 | 227.14 / 226.03 / 224.68 | 132.03 / 227.14 |
| Joe Burrow QB+2 + BB | 128.12 / 128.14 / 128.12 | 224.42 / 223.44 / 222.21 | 129.67 / 224.42 |
| Jacoby Brissett QB+2 / no BB | 133.82 / 132.90 / 131.37 | 231.33 / 230.83 / 230.02 | 133.82 / 231.74 |
| Trevor Lawrence QB+1 + BB | 134.23 / 134.30 / 134.30 | 233.83 / 233.13 / 233.13 | 135.77 / 234.81 |
| Joe Burrow QB+1 + BB | 130.53 / 130.53 / 130.53 | 227.11 / 227.11 / 227.11 | 130.53 / 227.11 |
| Patrick Mahomes QB+2 / no BB | 126.63 / 126.63 / 126.63 | 218.85 / 218.85 / 218.85 | 126.63 / 218.85 |
| Jacoby Brissett QB+1 / no BB | 134.75 / 134.75 / 134.75 | 233.17 / 233.17 / 233.17 | 134.75 / 233.17 |
| Jacoby Brissett QB+2 + BB | 131.65 / 131.65 / 131.65 | 228.44 / 228.44 / 228.44 | 131.65 / 228.44 |
| Kirk Cousins QB+2 + BB | 129.31 / 129.31 / 129.31 | 227.86 / 227.86 / 227.86 | 129.31 / 227.86 |
| Patrick Mahomes QB+2 + BB | 126.97 / 125.52 / 125.92 | 224.06 / 222.97 / 223.11 | 126.97 / 224.78 |
| Trevor Lawrence QB+1 / no BB | 133.69 / 133.69 / 133.69 | 231.72 / 231.72 / 231.72 | 133.69 / 231.72 |
| Kirk Cousins QB+2 / no BB | 129.06 / 129.06 / 129.06 | 227.61 / 227.61 / 227.61 | 129.06 / 227.61 |
| Josh Allen QB+2 / no BB | 129.04 / 129.04 / 129.04 | 222.56 / 222.56 / 222.56 | 129.04 / 222.56 |
| Josh Allen QB+3 + BB | 127.07 / 126.20 / 125.95 | 215.49 / 214.81 / 214.58 | 127.07 / 215.49 |
| Josh Allen QB+2 + BB | 129.86 / 128.50 / 128.83 | 219.91 / 220.17 / 219.31 | 129.86 / 220.86 |
| Patrick Mahomes QB+3 + BB | 123.02 / 123.02 / 123.02 | 218.38 / 218.38 / 218.38 | 123.02 / 218.38 |
| C.J. Stroud QB+2 / no BB | 127.15 / 127.15 / 127.15 | 222.56 / 222.56 / 222.56 | 127.15 / 222.56 |
| Patrick Mahomes QB+1 / no BB | 129.68 / 129.68 / 129.68 | 221.96 / 221.96 / 221.96 | 129.68 / 221.96 |
| C.J. Stroud QB+2 + BB | 123.20 / 121.76 / 121.61 | 217.26 / 216.04 / 216.07 | 123.20 / 217.26 |
| Jacoby Brissett QB+1 + BB | 130.11 / 130.11 / 130.11 | 228.54 / 228.54 / 228.54 | 130.11 / 228.54 |
| Joe Burrow QB+1 / no BB | 129.83 / 129.83 / 129.83 | 230.07 / 230.07 / 230.07 | 129.83 / 230.07 |
| Josh Allen QB+1 / no BB | 131.02 / 131.02 / 131.02 | 228.27 / 228.27 / 228.27 | 131.02 / 228.27 |
| Matthew Stafford QB+1 / no BB | 131.42 / 131.42 / 131.42 | 231.66 / 231.66 / 231.66 | 131.42 / 231.66 |
| Patrick Mahomes QB+1 + BB | 129.64 / 129.64 / 129.64 | 226.81 / 226.81 / 226.81 | 129.64 / 226.81 |
| Kirk Cousins QB+1 / no BB | 130.97 / 130.97 / 130.97 | 229.52 / 229.52 / 229.52 | 130.97 / 229.52 |
| Kirk Cousins QB+1 + BB | 131.22 / 131.22 / 131.22 | 229.77 / 229.77 / 229.77 | 131.22 / 229.77 |
| Bo Nix QB+1 / no BB | 130.94 / 130.94 / 130.94 | 227.40 / 227.40 / 227.40 | 130.94 / 227.40 |
| C.J. Stroud QB+1 / no BB | 125.60 / 125.60 / 125.60 | 221.01 / 221.01 / 221.01 | 125.60 / 221.01 |
| Jordan Love QB+1 / no BB | 132.72 / 132.72 / 132.72 | 228.13 / 228.13 / 228.13 | 132.72 / 228.13 |
| Jordan Love QB+1 + BB | 131.05 / 131.05 / 131.05 | 228.27 / 228.27 / 228.27 | 131.05 / 228.27 |
| Matthew Stafford QB+1 + BB | 129.44 / 129.44 / 129.44 | 227.58 / 227.58 / 227.58 | 129.44 / 227.58 |
| Jordan Love QB+2 + BB | 130.09 / 130.09 / 130.09 | 225.88 / 225.88 / 225.88 | 130.09 / 225.88 |
| Jameis Winston QB+2 / no BB | 126.22 / 125.92 / 125.49 | 223.29 / 222.43 / 221.90 | 126.63 / 223.70 |
| Bo Nix QB+2 / no BB | 126.32 / 126.32 / 126.32 | 221.38 / 221.38 / 221.38 | 126.32 / 221.38 |
| Jameis Winston QB+1 + BB | 128.65 / 128.65 / 128.65 | 228.46 / 228.46 / 228.46 | 128.65 / 228.46 |
| Jameis Winston QB+1 / no BB | 128.75 / 128.75 / 128.75 | 226.89 / 226.89 / 226.89 | 128.75 / 226.89 |
| C.J. Stroud QB+1 + BB | 127.76 / 127.76 / 127.76 | 223.17 / 223.17 / 223.17 | 127.76 / 223.17 |
| Jameis Winston QB+2 + BB | 125.06 / 124.62 / 124.21 | 222.13 / 221.60 / 220.98 | 125.82 / 222.13 |
| Drake Maye QB+1 / no BB | 125.55 / 125.55 / 125.55 | 220.71 / 220.71 / 220.71 | 125.55 / 220.71 |
| Jordan Love QB+2 / no BB | 129.35 / 129.35 / 129.35 | 223.04 / 223.04 / 223.04 | 129.35 / 223.04 |
| Jalen Hurts QB+1 + BB | 128.99 / 128.99 / 128.99 | 227.16 / 227.16 / 227.16 | 128.99 / 227.16 |
| Sam Darnold QB+2 / no BB | 124.01 / 123.65 / 122.68 | 220.72 / 220.92 / 220.77 | 124.01 / 222.29 |
| Jalen Hurts QB+1 / no BB | 130.09 / 130.09 / 130.09 | 224.82 / 224.82 / 224.82 | 130.09 / 224.82 |
| Cam Ward QB+2 + BB | 126.61 / 126.61 / 126.61 | 225.78 / 225.78 / 225.78 | 126.61 / 225.78 |
| Drake Maye QB+2 + BB | 123.15 / 121.27 / 121.39 | 219.05 / 218.57 / 218.06 | 123.15 / 219.50 |
| Sam Darnold QB+1 / no BB | 125.83 / 125.83 / 125.83 | 224.63 / 224.63 / 224.63 | 125.83 / 224.63 |

## Pareto / frontier evidence

The preserved v3 screen compares peak selector, peak mean, peak P90, depth within 0.10, availability and ownership completeness. It marks Burrow and Lawrence QB+3 dominated because it does not treat correlation structure as a separate dimension. That is numerical dominance under those axes, not proof that the reverse passing direction has no football value.

For this completed review, a second **correlation-aware Pareto screen** compares peak selector, mean, summed P90, depth within 0.20, best-candidate total rule contribution, elevated-player count, availability evidence gaps, cheap-role evidence gaps and ownership completeness. Higher quality/depth/rule contribution and lower gaps/dependencies are favored; every dimension must be at least as good, with one strict improvement, to dominate. Rule contribution is the existing QB-stack + bring-back + game + other correlation/penalty terms, not a new thesis score. This screen is diagnostic and does not rerun or rewrite the frozen v3 portfolio allocation.

Positive correlation bonuses are selector-policy evidence, not empirical covariance estimates. Different stack/game structures remain interpretable dimensions; dominance is not a causal outcome claim.

| Family | Best rank | Selector gap | Rule total | Q elevated / availability gaps / cheap gaps | Ownership coverage | Correlation-aware frontier |
| --- | --- | --- | --- | --- | --- | --- |
| Trevor Lawrence QB+2 + BB | 1 | 0.000 | 0.390 | 1 / 1 / 1 | 100% | survives |
| Trevor Lawrence QB+3 + BB | 13 | 0.042 | 0.396 | 1 / 1 / 1 | 100% | survives |
| Joe Burrow QB+2 + BB | 48 | 0.078 | 0.407 | 1 / 1 / 1 | 100% | survives |
| Jacoby Brissett QB+2 / no BB | 83 | 0.181 | 0.188 | 1 / 1 / 1 | 100% | survives |
| Trevor Lawrence QB+1 + BB | 85 | 0.207 | 0.092 | 1 / 1 / 1 | 100% | survives |
| Joe Burrow QB+1 + BB | 86 | 0.218 | 0.205 | 1 / 1 / 1 | 100% | dominated by Trevor Lawrence QB+2 + BB |
| Patrick Mahomes QB+2 / no BB | 90 | 0.248 | 0.315 | 0 / 0 / 1 | 100% | survives |
| Jacoby Brissett QB+1 / no BB | 91 | 0.250 | 0.067 | 1 / 1 / 1 | 100% | dominated by Trevor Lawrence QB+1 + BB |
| Jacoby Brissett QB+2 + BB | 92 | 0.252 | 0.192 | 1 / 1 / 1 | 100% | dominated by Trevor Lawrence QB+2 + BB |
| Kirk Cousins QB+2 + BB | 93 | 0.265 | 0.201 | 1 / 1 / 1 | 100% | dominated by Trevor Lawrence QB+2 + BB |
| Patrick Mahomes QB+2 + BB | 94 | 0.270 | 0.254 | 0 / 0 / 0 | 100% | survives |
| Trevor Lawrence QB+1 / no BB | 95 | 0.271 | 0.092 | 1 / 1 / 1 | 100% | dominated by Jacoby Brissett QB+2 / no BB |
| Kirk Cousins QB+2 / no BB | 96 | 0.274 | 0.190 | 1 / 1 / 1 | 100% | dominated by Trevor Lawrence QB+2 + BB |
| Josh Allen QB+2 / no BB | 97 | 0.276 | 0.228 | 1 / 1 / 1 | 100% | dominated by Trevor Lawrence QB+2 + BB |
| Josh Allen QB+3 + BB | 104 | 0.311 | 0.309 | 1 / 1 / 0 | 100% | survives |
| Josh Allen QB+2 + BB | 105 | 0.312 | 0.228 | 1 / 1 / 0 | 100% | survives |
| Patrick Mahomes QB+3 + BB | 111 | 0.318 | 0.339 | 0 / 0 / 0 | 100% | survives |
| C.J. Stroud QB+2 / no BB | 113 | 0.321 | 0.237 | 1 / 1 / 1 | 100% | dominated by Trevor Lawrence QB+2 + BB |
| Patrick Mahomes QB+1 / no BB | 114 | 0.321 | 0.173 | 0 / 0 / 1 | 100% | survives |
| C.J. Stroud QB+2 + BB | 115 | 0.325 | 0.316 | 0 / 0 / 2 | 100% | survives |
| Jacoby Brissett QB+1 + BB | 118 | 0.328 | 0.096 | 0 / 0 / 1 | 100% | survives |
| Joe Burrow QB+1 / no BB | 119 | 0.330 | 0.098 | 1 / 1 / 1 | 100% | dominated by Trevor Lawrence QB+2 + BB |
| Josh Allen QB+1 / no BB | 129 | 0.339 | 0.081 | 1 / 1 / 1 | 100% | dominated by Trevor Lawrence QB+2 + BB |
| Matthew Stafford QB+1 / no BB | 139 | 0.347 | 0.061 | 1 / 1 / 1 | 100% | dominated by Jacoby Brissett QB+2 / no BB |
| Patrick Mahomes QB+1 + BB | 145 | 0.351 | 0.106 | 1 / 1 / 1 | 100% | dominated by Trevor Lawrence QB+2 + BB |
| Kirk Cousins QB+1 / no BB | 146 | 0.352 | 0.067 | 1 / 1 / 1 | 100% | dominated by Trevor Lawrence QB+2 + BB |
| Kirk Cousins QB+1 + BB | 149 | 0.354 | 0.067 | 1 / 1 / 1 | 100% | dominated by Trevor Lawrence QB+2 + BB |
| Bo Nix QB+1 / no BB | 156 | 0.373 | 0.072 | 1 / 1 / 1 | 100% | dominated by Trevor Lawrence QB+2 + BB |
| C.J. Stroud QB+1 / no BB | 157 | 0.379 | 0.179 | 0 / 0 / 2 | 100% | dominated by Patrick Mahomes QB+2 + BB |
| Jordan Love QB+1 / no BB | 158 | 0.380 | 0.043 | 0 / 0 / 1 | 100% | survives |
| Jordan Love QB+1 + BB | 159 | 0.380 | 0.067 | 0 / 0 / 1 | 100% | survives |
| Matthew Stafford QB+1 + BB | 161 | 0.386 | 0.086 | 1 / 1 / 1 | 100% | dominated by Trevor Lawrence QB+2 + BB |
| Jordan Love QB+2 + BB | 164 | 0.389 | 0.120 | 0 / 0 / 1 | 100% | survives |
| Jameis Winston QB+2 / no BB | 165 | 0.393 | 0.178 | 1 / 1 / 2 | 100% | dominated by Trevor Lawrence QB+2 + BB |
| Bo Nix QB+2 / no BB | 167 | 0.396 | 0.203 | 1 / 1 / 1 | 100% | dominated by Trevor Lawrence QB+2 + BB |
| Jameis Winston QB+1 + BB | 168 | 0.400 | 0.068 | 1 / 1 / 1 | 100% | dominated by Trevor Lawrence QB+2 + BB |
| Jameis Winston QB+1 / no BB | 169 | 0.400 | 0.088 | 1 / 1 / 1 | 100% | dominated by Trevor Lawrence QB+2 + BB |
| C.J. Stroud QB+1 + BB | 172 | 0.402 | 0.121 | 0 / 0 / 1 | 100% | survives |
| Jameis Winston QB+2 + BB | 173 | 0.415 | 0.188 | 0 / 0 / 1 | 100% | dominated by Patrick Mahomes QB+2 + BB |
| Drake Maye QB+1 / no BB | 177 | 0.422 | 0.158 | 0 / 0 / 2 | 100% | dominated by Patrick Mahomes QB+2 + BB |
| Jordan Love QB+2 / no BB | 178 | 0.426 | 0.120 | 0 / 0 / 1 | 100% | dominated by Jordan Love QB+2 + BB |
| Jalen Hurts QB+1 + BB | 181 | 0.438 | 0.054 | 0 / 0 / 1 | 100% | dominated by Jacoby Brissett QB+1 + BB |
| Sam Darnold QB+2 / no BB | 183 | 0.446 | 0.176 | 0 / 0 / 2 | 100% | dominated by Patrick Mahomes QB+2 + BB |
| Jalen Hurts QB+1 / no BB | 186 | 0.451 | 0.054 | 0 / 0 / 1 | 100% | dominated by Jacoby Brissett QB+1 + BB |
| Cam Ward QB+2 + BB | 188 | 0.457 | 0.074 | 0 / 0 / 1 | 100% | dominated by Jacoby Brissett QB+1 + BB |
| Drake Maye QB+2 + BB | 189 | 0.458 | 0.180 | 0 / 0 / 1 | 100% | dominated by Patrick Mahomes QB+2 + BB |
| Sam Darnold QB+1 / no BB | 192 | 0.462 | 0.078 | 0 / 0 / 2 | 100% | dominated by Patrick Mahomes QB+2 + BB |

- **Trevor Lawrence QB+2 + BB:** remains on this frontier because best selector and deepest competitive family; strong mean with double-stack and bring-back support.
- **Trevor Lawrence QB+3 + BB:** remains on this frontier because slightly more rule contribution from the third catcher (0.396 vs 0.390), preserving a defensible stack variant despite lower raw quality.
- **Joe Burrow QB+2 + BB:** remains on this frontier because reverse CIN passing direction and the highest best-family rule contribution (0.407); a deep near-frontier hedge within JAX@CIN.
- **Jacoby Brissett QB+2 / no BB:** remains on this frontier because higher raw mean/P90 allocation than the leading selector roster and a second primary game, despite weaker context and correlation.
- **Trevor Lawrence QB+1 + BB:** remains on this frontier because highest family peak mean/P90, but outside 0.20 and dependent on elevated availability evidence.
- **Patrick Mahomes QB+2 / no BB:** remains on this frontier because zero elevated dependencies/evidence gaps and a competitive KC stack rule contribution; outside the strong-quality window.
- **Patrick Mahomes QB+2 + BB:** remains on this frontier because many KC variants with no elevated dependency in the best candidate and zero cheap-role gaps; lower selector but a depth/risk tradeoff.
- **Josh Allen QB+3 + BB:** remains on this frontier because BUF triple-stack rule support and no cheap-role gaps; outside 0.20.
- **Josh Allen QB+2 + BB:** remains on this frontier because BUF double-stack/bring-back depth with no cheap-role gaps; outside 0.20.
- **Patrick Mahomes QB+3 + BB:** remains on this frontier because KC triple-stack contribution with zero elevated, availability or cheap-role gaps; only one candidate, outside 0.20.
- **Patrick Mahomes QB+1 / no BB:** remains on this frontier because higher raw mean in a KC single-stack with clean availability evidence; only one candidate, outside 0.20.
- **C.J. Stroud QB+2 + BB:** remains on this frontier because HOU passing construction with clean elevated/availability evidence and a relatively high rule contribution; thin and outside 0.20.
- **Jacoby Brissett QB+1 + BB:** remains on this frontier because ARI single-stack/bring-back with clean elevated/availability evidence, retaining raw P90 support; thin and outside 0.20.
- **Jordan Love QB+1 / no BB:** remains on this frontier because GB single-stack raw mean with clean elevated/availability evidence; thin and outside 0.20.
- **Jordan Love QB+1 + BB:** remains on this frontier because GB single-stack/bring-back raw P90 with clean elevated/availability evidence; thin and outside 0.20.
- **Jordan Love QB+2 + BB:** remains on this frontier because GB double-stack/bring-back balances more correlation contribution with clean elevated/availability evidence; thin and outside 0.20.
- **C.J. Stroud QB+1 + BB:** remains on this frontier because HOU single-stack/bring-back preserves more raw mean/P90 than its double-stack family with clean availability; thin and outside 0.20.

Exactly four correlation-aware survivors are inside 0.20, but only three QB directions and two games. Families outside the tolerance can be defensible on one dimension without being strong portfolio recommendations. Dominated rows above have an explicit witness and are not rewarded as new scenarios.

## Why Brissett survives: QB opportunity cost

Baseline is the strongest saved Brissett candidate, **rank 83**, salary **$49,900**, selector **5.425765**, mean **133.82**, summed P90 **231.33**. It uses Brissett + Michael Wilson + Trey McBride, no ARI–NYG bring-back, and an RB flex. Brissett’s saved QB values are **$5,000 / 16.40 mean / 27.30 P90 / 1.81% ownership**. Rankings here use unrounded saved projections.

| QB | Salary | Mean | P90 | Ownership | Salary ↑ vs Brissett | Mean ↑ | P90 ↑ | Ownership ↑ (pp) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Josh Allen (highest projected viable) | 7700 | 22.48 | 33.13 | 10.12% | 2700 | 6.08 | 5.83 | 8.31 |
| Joe Burrow | 6800 | 19.68 | 30.58 | 5.57% | 1800 | 3.28 | 3.28 | 3.76 |
| Trevor Lawrence | 5900 | 19.49 | 30.39 | 5.31% | 900 | 3.09 | 3.09 | 3.50 |
| Patrick Mahomes | 6500 | 18.59 | 29.49 | 4.67% | 1500 | 2.19 | 2.19 | 2.86 |

Josh Allen is the highest-projected saved starting QB with a legal construction and a candidate in the frozen universe, so he also satisfies the highest-projected viable QB control. Ownership is diagnostic: all these QB values exist, while leverage weight is zero and soft ownership/chalk penalties are disabled. Lower Brissett ownership is not a hidden selector bonus.

### Best saved lineup for each QB

| QB | Global rank | Mean | P90 sum | Selector | Stack | QB-stack / BB / other correlation | All rule terms | Context |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Jacoby Brissett | 83 | 133.82 | 231.33 | 5.426 | QB+2 | 0.134 / 0.000 / 0.054 | 0.188 | 0.068 |
| Josh Allen | 97 | 129.04 | 222.56 | 5.330 | QB+2 | 0.162 / 0.000 / 0.066 | 0.228 | 0.124 |
| Joe Burrow | 48 | 128.12 | 224.42 | 5.529 | QB+2+bring-back | 0.196 / 0.037 / 0.129 | 0.407 | 0.132 |
| Trevor Lawrence | 1 | 133.32 | 225.60 | 5.607 | QB+2+bring-back | 0.184 / 0.037 / 0.124 | 0.390 | 0.133 |
| Patrick Mahomes | 90 | 126.63 | 218.85 | 5.358 | QB+2 | 0.157 / 0.000 / 0.113 | 0.315 | 0.152 |

- **Josh Allen #97:** QB: Josh Allen; RB: Chase Brown, Kenneth Walker III; WR: Elic Ayomanor, Parker Washington, Michael Wilson, DJ Moore; TE: Dalton Kincaid; DST: Dolphins.
- **Joe Burrow #48:** QB: Joe Burrow; RB: Chase Brown, Kyren Williams; WR: Tee Higgins, Parker Washington, Michael Wilson, Ja'Marr Chase; TE: Colby Parkinson; DST: Dolphins.
- **Trevor Lawrence #1:** QB: Trevor Lawrence; RB: Chase Brown, Kyren Williams; WR: Parker Washington, Puka Nacua, Travis Hunter, Ja'Marr Chase; TE: Travis Kelce; DST: Dolphins.
- **Patrick Mahomes #90:** QB: Patrick Mahomes; RB: Chase Brown, Kenneth Walker III; WR: Parker Washington, Xavier Worthy, Travis Hunter, Ja'Marr Chase; TE: Travis Kelce; DST: Dolphins.

### QB sacrifice versus whole-lineup gains

Positive gains below favor the Brissett baseline. These compare each QB’s saved best, allowing different stack/flex choices; the structure-preserving controls follow next.

| Opponent QB | QB mean sacrificed | Non-QB mean gained | Net lineup mean | QB P90 sacrificed | Non-QB P90 gained | Net lineup P90 | Selector Δ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Josh Allen | 6.08 | 10.86 | 4.78 | 5.83 | 14.59 | 8.76 | 0.095 |
| Joe Burrow | 3.28 | 8.98 | 5.71 | 3.28 | 10.18 | 6.91 | -0.103 |
| Trevor Lawrence | 3.09 | 3.59 | 0.50 | 3.09 | 8.81 | 5.72 | -0.181 |
| Patrick Mahomes | 2.19 | 9.38 | 7.19 | 2.19 | 14.66 | 12.47 | 0.068 |

## Legal pay-up-at-QB counterfactual

Each control forces the alternative QB and reoptimizes the rest legally. It preserves **QB+WR+TE, no bring-back, RB flex, and at least four of rank 83’s eight non-QB players**. The four-player retention rule is an explicit comparability heuristic. Salary ≤$50,000, exactly one TE, team ≤4, game ≤5, DST-opponent avoidance, punt limits, locks and at most one elevated-questionable player remain the saved rules. An additional free-structure solve tests sensitivity to these controls. CBC reports an optimal legal solution for each run. Candidate/portfolio exposure percentages apply to pools and portfolios; a single forced roster instead enforces the saved per-lineup risk rule.

The Brissett control reproduces rank 83 exactly. Thus he remains optimal with his QB required even when stack size and flex may vary, rather than being an accident of his saved family representative.

| QB | Comparable mean | P90 | Selector | Equivalent global rank | Salary | Original non-QBs retained | Stack catchers | Rule total / context |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Josh Allen | 128.45 | 223.61 | 5.318 | 99 | 50000 | 4 | Khalil Shakir, Dalton Kincaid | 0.228 / 0.106 |
| Joe Burrow | 124.76 | 223.18 | 5.337 | 95 | 50000 | 5 | Drew Sample, Ja'Marr Chase | 0.276 / 0.139 |
| Trevor Lawrence | 131.14 | 227.08 | 5.435 | 83 | 50000 | 5 | Parker Washington, Brenton Strange | 0.259 / 0.105 |
| Patrick Mahomes | 126.61 | 225.41 | 5.311 | 99 | 50000 | 4 | Travis Kelce, Xavier Worthy | 0.220 / 0.110 |
| Jacoby Brissett | 133.82 | 231.33 | 5.426 | 83 | 49900 | 8 | Michael Wilson, Trey McBride | 0.188 / 0.068 |

Equivalent global rank means one plus the count of saved candidates with a strictly better selector; it does not insert a new roster into the frozen universe.

- **Josh Allen comparable:** QB: Josh Allen; RB: Chase Brown, Kyren Williams, Kenneth Walker III; WR: Khalil Shakir, Michael Wilson, Wan'Dale Robinson; TE: Dalton Kincaid; DST: Dolphins.
- **Joe Burrow comparable:** QB: Joe Burrow; RB: Chase Brown, Kyren Williams, Derrick Henry; WR: Michael Wilson, Wan'Dale Robinson, Ja'Marr Chase; TE: Drew Sample; DST: Dolphins.
- **Trevor Lawrence comparable:** QB: Trevor Lawrence; RB: Kyren Williams, Derrick Henry, Rhamondre Stevenson; WR: Parker Washington, Puka Nacua, Michael Wilson; TE: Brenton Strange; DST: Dolphins.
- **Patrick Mahomes comparable:** QB: Patrick Mahomes; RB: Chase Brown, Kyren Williams, Derrick Henry; WR: Xavier Worthy, Wan'Dale Robinson, Zay Flowers; TE: Travis Kelce; DST: Dolphins.

### Where the saved salary goes

These are position-group differences for rank 83 minus each comparable pay-up roster. A positive salary amount means Brissett spends more at that position. Player switches also reflect stack requirements; the dollar savings are not a randomized causal effect. A negative projection gain is shown instead of pretending every position improves.

| Pay-up QB | Position | Brissett-only players | Pay-up-only players | Salary gained | Mean gained | P90 gained |
| --- | --- | --- | --- | --- | --- | --- |
| Josh Allen | DST | unchanged | unchanged | 0 | 0.00 | 0.00 |
| Josh Allen | RB | Derrick Henry | Kenneth Walker III | 200 | -0.25 | -0.25 |
| Josh Allen | TE | Trey McBride | Dalton Kincaid | 1200 | 4.33 | 6.42 |
| Josh Allen | WR | Elic Ayomanor, Puka Nacua | Khalil Shakir, Wan'Dale Robinson | 1200 | 7.37 | 7.37 |
| Joe Burrow | DST | unchanged | unchanged | 0 | 0.00 | 0.00 |
| Joe Burrow | RB | unchanged | unchanged | 0 | 0.00 | 0.00 |
| Joe Burrow | TE | Trey McBride | Drew Sample | 3900 | 14.72 | 16.81 |
| Joe Burrow | WR | Elic Ayomanor, Puka Nacua | Wan'Dale Robinson, Ja'Marr Chase | -2200 | -2.38 | -5.39 |
| Trevor Lawrence | DST | unchanged | unchanged | 0 | 0.00 | 0.00 |
| Trevor Lawrence | RB | Chase Brown | Rhamondre Stevenson | 1000 | 4.89 | 7.38 |
| Trevor Lawrence | TE | Trey McBride | Brenton Strange | 3300 | 10.59 | 12.68 |
| Trevor Lawrence | WR | Elic Ayomanor | Parker Washington | -3500 | -9.71 | -12.73 |
| Patrick Mahomes | DST | unchanged | unchanged | 0 | 0.00 | 0.00 |
| Patrick Mahomes | RB | unchanged | unchanged | 0 | 0.00 | 0.00 |
| Patrick Mahomes | TE | Trey McBride | Travis Kelce | 1500 | 4.71 | 4.71 |
| Patrick Mahomes | WR | Elic Ayomanor, Puka Nacua, Michael Wilson | Xavier Worthy, Wan'Dale Robinson, Zay Flowers | -100 | 4.70 | 3.40 |

Salary accounting: the Brissett baseline leaves $100 unused; every comparable pay-up roster uses $50,000. Therefore his extra non-QB spend equals the QB savings **minus $100**. Against Allen, $2,700 QB savings become $2,600 non-QB spend: $1,200 at TE, $1,200 net at WR, $200 at RB. McBride replaces Kincaid (+4.33 mean/+6.42 P90); Nacua plus Ayomanor replace Shakir plus Robinson (+7.37/+7.37); Henry replaces Walker at a slight projection loss (−0.25/−0.25).

Against Lawrence, the net $800 non-QB spend is **+$1,000 RB, +$3,300 TE, −$3,500 WR**. McBride over Strange gains 10.59 mean/12.68 P90 and Brown over Stevenson gains 4.89/7.38, while Ayomanor instead of Washington loses 9.71/12.73. This is salary allocation across an entire stack, not a claim that $900 alone purchases every named upgrade.

| Pay-up QB | QB salary saved | Non-QB spend ↑ | QB mean sacrificed | Non-QB mean gained | Net mean | QB P90 sacrificed | Non-QB P90 gained | Net P90 | Selector Δ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Josh Allen | 2700 | 2600 | 6.08 | 11.45 | 5.37 | 5.83 | 13.54 | 7.71 | 0.108 |
| Joe Burrow | 1800 | 1700 | 3.28 | 12.34 | 9.06 | 3.28 | 11.42 | 8.14 | 0.089 |
| Trevor Lawrence | 900 | 800 | 3.09 | 5.77 | 2.68 | 3.09 | 7.33 | 4.24 | -0.009 |
| Patrick Mahomes | 1500 | 1400 | 2.19 | 9.40 | 7.21 | 2.19 | 8.10 | 5.92 | 0.115 |

### Free-structure sensitivity and evidence classification

| Required QB | Free-structure selector | Equivalent rank | Stack | Mean / P90 | Same as saved best? |
| --- | --- | --- | --- | --- | --- |
| Josh Allen | 5.330 | 97 | QB+2 | 129.04 / 222.56 | True |
| Joe Burrow | 5.529 | 48 | QB+2+bring-back | 128.12 / 224.42 | True |
| Trevor Lawrence | 5.607 | 1 | QB+2+bring-back | 133.32 / 225.60 | True |
| Patrick Mahomes | 5.358 | 90 | QB+2 | 126.63 / 218.85 | True |
| Jacoby Brissett | 5.426 | 83 | QB+2 | 133.82 / 231.33 | True |

**GENUINE SALARY-EFFICIENCY THESIS, conditional on the saved projections and roles.** Brissett sacrifices 2.19–6.08 QB mean points against the required alternatives. His legal comparable rosters gain 5.77–12.34 non-QB mean points, leaving 2.68–9.06 net mean gains. The summed-P90 accounting also stays positive. His rule and context bonuses are weaker, so his viability is primarily **salary allocation plus the projected Wilson/McBride stack**, not a correlation boost. He is not the selector winner: Lawrence’s comparable selector is 0.00884 higher; free-structure Lawrence and Burrow beat him by 0.18087 and 0.10292 respectively.

Plain English: **the optimizer can buy enough extra projected production at tight end and the other non-QB positions to compensate for Brissett’s lower projection. It sees an affordable Wilson/McBride stack and a strong supporting roster. Paying more for the quarterback forces tradeoffs elsewhere.** This does not make Brissett a better real quarterback. His modest frontier depth and dependencies on Ayomanor’s cheap role and Nacua’s saved elevated-questionable status remain material. The comparison does not prove the projections or stack correlations are calibrated, and the arbitrary four-player core is tested by the free-structure sensitivity.

## Dynamic shadow portfolios: 1, 3, 5, 10, 20

Preserve the existing v3 joint solves. For each size, they maximize qualified non-dominated family coverage, then canonical game coverage, then the existing selector. They enforce saved player exposure (80% ordinary, 60% QB), questionable caps, at least two QB paths for multiple entries, and a shadow overlap cap of six. They try .05/.10/.15/.20, then the full saved pool if needed. No fixed five-family rule or equal allocation is imposed. Diversity credit remains limited to families whose best candidate is within 0.20.

| Entries | Tolerance | Selector total | Mean total | P90 total | Stack families / QB directions / games | Ranks |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 0.05 | 5.578 | 129.36 | 228.24 | 1 / 1 / 1 | 6 |
| 3 | 0.2 | 16.432 | 393.13 | 666.52 | 3 / 3 / 2 | 18, 82, 83 |
| 5 | 0.2 | 27.688 | 649.23 | 1131.94 | 4 / 3 / 2 | 1, 6, 31, 48, 83 |
| 10 | 0.2 | 55.280 | 1301.16 | 2256.27 | 4 / 3 / 2 | 1, 3, 5, 6, 11, 31, 48, 82, 83, 84 |
| 20 | full saved pool | 110.188 | 2603.39 | 4507.10 | 4 / 3 / 2 | 1, 3, 5, 6, 10, 11, 12, 18, 21, 26, 31, 33, 48, 50, 52, 82, 83, 84, 103, 109 |

| Family | 1 entry | 3 entries | 5 entries | 10 entries | 20 entries |
| --- | --- | --- | --- | --- | --- |
| Trevor Lawrence QB+2 + BB | 1 | 1 | 2 | 5 | 10 |
| Trevor Lawrence QB+3 + BB | 0 | 0 | 1 | 1 | 2 |
| Joe Burrow QB+2 + BB | 0 | 1 | 1 | 2 | 4 |
| Jacoby Brissett QB+2 / no BB | 0 | 1 | 1 | 2 | 4 |

The 20-entry solve needs the full saved pool because the .20 window cannot fill all slots under the saved exposure constraints. Its ranks 103 and 109 fall outside .20 (gaps **0.311** and **0.315**). This is a disclosed quality relaxation within Brissett’s existing direction, not a weak fifth game introduced for diversity. The other 18 entries remain within .20.

### The intended “five similar sets” concept

This slate supports **three competitive broad passing directions**, with Lawrence split into two stack shapes. The 20-entry allocation is **10 Lawrence QB+2, 2 Lawrence QB+3, 4 Burrow QB+2, 4 Brissett QB+2**. Thus there are four construction sets, three QB directions, and two primary games—not five independent sets of football outcomes. The weights emerge from selector quality, candidate availability/depth and exposure constraints rather than equal shares. They are constrained allocation results, not validated optimal betting fractions.

| Entries | Within-family avg / max | Across-family avg / max | Within pairs / across pairs |
| --- | --- | --- | --- |
| 1 | — / — | — / — | 0 / 0 |
| 3 | — / — | 2.67 / 4 | 0 / 3 |
| 5 | 5.00 / 5 | 4.11 / 6 | 1 / 9 |
| 10 | 5.42 / 6 | 4.00 / 6 | 12 / 33 |
| 20 | 5.38 / 6 | 3.46 / 6 | 58 / 132 |

Using the broader QB-direction definition, 20-entry overlap is **5.28 average / 6 max within direction**, and **3.19 average / 5 max across directions**. Shared one-offs and the common game make these directions dependent; six shared players across some families remains substantial redundancy.

## Five-entry shadow representatives and joint tradeoffs

| Thesis | Canonical game | QB | Candidate rank | Selector | Mean | P90 | Why selected |
| --- | --- | --- | --- | --- | --- | --- | --- |
| QB+2 + BB | JAX@CIN | Trevor Lawrence | 1 | 5.607 | 133.32 | 225.60 | highest selector; anchor double-stack construction |
| QB+2 + BB | JAX@CIN | Trevor Lawrence | 6 | 5.578 | 129.36 | 228.24 | second Lawrence double-stack at 0.028 cost; jointly legal distinct core |
| QB+3 + BB | JAX@CIN | Trevor Lawrence | 31 | 5.548 | 124.60 | 222.35 | triple-stack variant at 0.016 cost; avoids elevated-risk/core-cap conflict |
| QB+2 + BB | JAX@CIN | Joe Burrow | 48 | 5.529 | 128.12 | 224.42 | strong reverse CIN passing direction; deep quality |
| QB+2 / no BB | ARI@NYG | Jacoby Brissett | 83 | 5.426 | 133.82 | 231.33 | competitive salary allocation and second primary game |

| Overlap | 1 | 6 | 31 | 48 | 83 |
| --- | --- | --- | --- | --- | --- |
| 1 | — | 5 | 4 | 5 | 4 |
| 6 | 5 | — | 6 | 5 | 3 |
| 31 | 4 | 6 | — | 4 | 2 |
| 48 | 5 | 5 | 4 | — | 4 |
| 83 | 4 | 3 | 2 | 4 | — |

Taking each family’s #1 independently fails the joint constraints. Rank 13 (the triple-stack peak) would put Nacua in **3/5 entries**, above his saved **2/5 elevated-player cap**, alongside ranks 1 and 83. Rank 31 gives up **0.016291 selector**, drops that elevated dependency, and reduces average overlap against ranks 1/6/48/83 from **4.75 to 4.00**; maximum stays six. Rank 6 costs **0.028217** versus rank 1 and overlaps rank 1 by five; taking rank 1 twice would duplicate all nine players. These are joint legality/redundancy tradeoffs, not five independently chosen peaks.

- **8b5c114c-b0d2-419e-8f41-bdcbc2674c71 / candidate rank 1**, Trevor Lawrence QB+2 + BB; canonical roster SHA-256 `2106a933cc68480a9a7f34a914157f91c769689d7a90956d5bef4b4a69a3f5a6`. QB: Trevor Lawrence; RB: Chase Brown, Kyren Williams; WR: Parker Washington, Puka Nacua, Travis Hunter, Ja'Marr Chase; TE: Travis Kelce; DST: Dolphins.
- **8b5c114c-b0d2-419e-8f41-bdcbc2674c71 / candidate rank 6**, Trevor Lawrence QB+2 + BB; canonical roster SHA-256 `67c545e95c44f0fa0e9878e30f02dfdb3d1094d8aad4298e31694f358ed88337`. QB: Trevor Lawrence; RB: Chase Brown, Kenneth Walker III; WR: Brian Thomas Jr., Parker Washington, Michael Wilson, Ja'Marr Chase; TE: Cade Otton; DST: Dolphins.
- **8b5c114c-b0d2-419e-8f41-bdcbc2674c71 / candidate rank 31**, Trevor Lawrence QB+3 + BB; canonical roster SHA-256 `bba0223a940725bd58e1b4626c1c28a245a3e80b4d4c7e79c4dd1cdd21e2f664`. QB: Trevor Lawrence; RB: Kyren Williams, Kenneth Walker III; WR: Brian Thomas Jr., Parker Washington, Michael Wilson, Ja'Marr Chase; TE: Brenton Strange; DST: Jets.
- **8b5c114c-b0d2-419e-8f41-bdcbc2674c71 / candidate rank 48**, Joe Burrow QB+2 + BB; canonical roster SHA-256 `e64826e351e68cc06a6085a2dbada446495d829db4325c08c50d53470f643dba`. QB: Joe Burrow; RB: Chase Brown, Kyren Williams; WR: Tee Higgins, Parker Washington, Michael Wilson, Ja'Marr Chase; TE: Colby Parkinson; DST: Dolphins.
- **8b5c114c-b0d2-419e-8f41-bdcbc2674c71 / candidate rank 83**, Jacoby Brissett QB+2 / no BB; canonical roster SHA-256 `7a506d74380822e58afc421d0c5b0e73684927348feb3e7024059ea25247873c`. QB: Jacoby Brissett; RB: Chase Brown, Kyren Williams, Derrick Henry; WR: Elic Ayomanor, Puka Nacua, Michael Wilson; TE: Trey McBride; DST: Dolphins.

Saved candidates have no separate lineup UUID. Run UUID + complete candidate rank is the saved identifier; the canonical-ID roster hash disambiguates it. Full canonical player IDs are retained in the shadow JSON.

### Exposures and totals

| Player | Shadow five | Saved production five |
| --- | --- | --- |
| Brenton Strange | 1/5 | 1/5 |
| Brian Thomas Jr. | 2/5 | 1/5 |
| Cade Otton | 1/5 | 0/5 |
| Chase Brown | 4/5 | 4/5 |
| Colby Parkinson | 1/5 | 1/5 |
| Derrick Henry | 1/5 | 1/5 |
| Dolphins | 4/5 | 4/5 |
| Elic Ayomanor | 1/5 | 1/5 |
| Ja'Marr Chase | 4/5 | 3/5 |
| Jacoby Brissett | 1/5 | 1/5 |
| Jets | 1/5 | 1/5 |
| Joe Burrow | 1/5 | 1/5 |
| Kenneth Walker III | 2/5 | 3/5 |
| Kirk Cousins | 0/5 | 1/5 |
| Kyren Williams | 4/5 | 4/5 |
| Michael Mayer | 0/5 | 1/5 |
| Michael Wilson | 4/5 | 3/5 |
| Parker Washington | 4/5 | 4/5 |
| Patrick Mahomes | 0/5 | 1/5 |
| Puka Nacua | 2/5 | 2/5 |
| Tee Higgins | 1/5 | 1/5 |
| Travis Hunter | 1/5 | 1/5 |
| Travis Kelce | 1/5 | 1/5 |
| Tre Tucker | 0/5 | 1/5 |
| Trevor Lawrence | 3/5 | 1/5 |
| Trey McBride | 1/5 | 1/5 |
| Xavier Worthy | 0/5 | 1/5 |

| QB direction | Shadow | Production |
| --- | --- | --- |
| Jacoby Brissett | 1/5 | 1/5 |
| Joe Burrow | 1/5 | 1/5 |
| Kirk Cousins | 0/5 | 1/5 |
| Patrick Mahomes | 0/5 | 1/5 |
| Trevor Lawrence | 3/5 | 1/5 |

| Primary canonical game | Shadow | Production |
| --- | --- | --- |
| ARI@NYG | 1/5 | 1/5 |
| JAX@CIN | 4/5 | 2/5 |
| KC@LV | 0/5 | 2/5 |

Primary-game exposure above counts the thesis anchor once per lineup. Full-roster game participation includes one-offs and DSTs and is: ARI@NYG 4/5, GB@TB 1/5, JAX@CIN 5/5, KC@LV 3/5, LAR@PHI 4/5, MIA@MIN 4/5, NYJ@CHI 1/5, TEN@BAL 1/5. Those incidental games are not additional discovered primary thesis environments.

### Objective production comparison

Production uses the user’s overlap=4 and distinct-QB settings. The shadow allows repeat QBs and overlap=6. Higher shadow score describes that different feasible set; it does not establish that the user settings are wrong or that the shadow will perform better.

| Metric | Production | Shadow | Shadow − production |
| --- | --- | --- | --- |
| Selector total | 27.203 | 27.688 | 0.485 |
| Projected mean total | 642.483 | 649.227 | 6.745 |
| Summed player P90 total | 1124.809 | 1131.943 | 7.134 |

Production ranks **[31, 48, 83, 90, 93]**, shadow ranks **[1, 6, 31, 48, 83]**. Both have **3/5 elevated-questionable lineups**. Production has five QB directions and three primary canonical games; shadow has three QB directions and two games. Shadow trades that broader game coverage for more of the saved selector-leading constructions.

## Forced-inclusion diagnostics for zero-coverage players

Every named player has **0/205** production candidate coverage. Each was forced by canonical ID under saved legal salary, stack, team, game, TE, DST and per-lineup risk constraints. The completed diagnostics optimize unrestricted saved hard stack rules **and every saved exact stack template**, then retain the best selector. This corrects the earlier JSN diagnostic: an allowed QB+3 construction achieves **5.429477**, rather than the template-restricted **5.402880**. Therefore JSN is within .20, and “below quality floor” is not a sufficient explanation for his absence.

| Player | Best legal QB / stack | Selector | Equivalent rank | Mean | P90 | Frontier loss | Salary / unused | Admission single-swap feasible? | Diagnostic classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Brock Bowers | Trevor Lawrence / QB+2+bring-back | 5.481 | 52 | 129.19 | 221.47 | 0.126 | 49900 / 100 | True | candidate search omission |
| Bucky Irving | Trevor Lawrence / QB+2+bring-back | 5.530 | 48 | 127.67 | 227.48 | 0.077 | 49900 / 100 | True | candidate search omission |
| Jaxon Smith-Njigba | Trevor Lawrence / QB+3+bring-back | 5.429 | 83 | 125.89 | 221.02 | 0.177 | 49900 / 100 | True | candidate search omission |
| Justin Jefferson | Trevor Lawrence / QB+2+bring-back | 5.447 | 82 | 127.75 | 220.03 | 0.159 | 49900 / 100 | True | candidate search omission |
| Lamar Jackson | Lamar Jackson / QB+1+bring-back | 5.119 | 200 | 125.99 | 226.72 | 0.488 | 50000 / 0 | True | quality floor |

Production admission recorded **286 legal inputs, 16 injury-count rejections, 65 residual admission exclusions, 205 accepted, 0 quality rejections, and 0 refill attempts**. The `rejected_by_player_cap` residual counter includes competition for the target count as well as caps; it is not a player-specific causal rejection log. The .20 quality floor used here is a shadow competitiveness criterion, not a hard production admission cutoff.

The single-swap check establishes that one legal forced roster can replace some saved candidate without violating unchanged pool exposure caps. It rules out an absolute aggregate-cap prohibition for these five. It does not prove which seed solver branch originally omitted every possible alternative roster.

### Brock Bowers

**Candidate search omission with salary opportunity cost.** No saved structural discovery injection includes Bowers. A $6,900 TE absorbs salary otherwise allocated to the supporting roster; nonetheless a required Lawrence double-stack is only 0.126 below the frontier and swap-feasible under his 90% candidate cap. Zero representation is not justified by a hard exposure/risk prohibition.

Best legal diagnostic roster: QB: Trevor Lawrence; RB: Chase Brown, Kyren Williams; WR: Parker Washington, Travis Hunter, Michael Wilson, Ja'Marr Chase; TE: Brock Bowers; DST: Dolphins.

Canonical roster SHA-256: `5ad35a820f24feea8408c60a2b60188cb875e87941e0046b52892b6e15886e13`. Ownership completeness: True. It remains diagnostic only.

### Bucky Irving

**Candidate search omission.** No saved structural discovery injection includes Bucky. The forced roster is equivalent to rank 48, only 0.077 below the frontier, and fits a legal cap-preserving pool swap. His 90% candidate cap is not zero. The finite QB-shard/uniqueness search plus admission did not explore/retain this strong legal construction; no lack of legal rosters or hard quality exclusion is supported.

Best legal diagnostic roster: QB: Trevor Lawrence; RB: Chase Brown, Bucky Irving; WR: Parker Washington, Puka Nacua, Wan'Dale Robinson, Ja'Marr Chase; TE: Brenton Strange; DST: Dolphins.

Canonical roster SHA-256: `0a241fa8348944e90b0b30cc0ceff3ae96e5239cc0b76e294ab276956b430a39`. Ownership completeness: True. It remains diagnostic only.

### Jaxon Smith-Njigba

**Candidate search omission / stack construction.** Two saved discovery injections already contained JSN, but neither survived joint target/cap/selector admission. His stronger forced Lawrence QB+3 shape was not in the final pool; exact QB+1/2 discovery is not exhaustive over three-catcher variants. The $9,100 salary displaces strong alternatives, but the best legal loss is only 0.177. Earlier “quality floor” attribution was too restrictive.

Best legal diagnostic roster: QB: Trevor Lawrence; RB: Chase Brown, Kyren Williams; WR: Jaxon Smith-Njigba, Brian Thomas Jr., Parker Washington, Zay Flowers; TE: Brenton Strange; DST: Dolphins.

Canonical roster SHA-256: `c83113220fda60df2727e5fdf13eb6625816ad37a2b1b538793fb4b3e691973d`. Ownership completeness: True. It remains diagnostic only.

### Justin Jefferson

**Candidate search omission, with a real availability constraint.** The saved structural discovery injections contain no Jefferson roster. He is Q/elevated, with uncertain workload and an evidence gap; his candidate cap is 25% and the per-lineup elevated limit is one. The required solve retains those controls, is inside .20, and can fit the unchanged pool by a single swap. The separate prospective shadow-generation arm had Jefferson exposure, confirming that generation method matters; it is not the frozen production universe. No hard ban explains zero.

Best legal diagnostic roster: QB: Trevor Lawrence; RB: Chase Brown, Kyren Williams; WR: Justin Jefferson, Parker Washington, Travis Hunter, Ja'Marr Chase; TE: Travis Kelce; DST: Titans.

Canonical roster SHA-256: `7ab88acee20f38b7c9bd1a8aaf29b1c149975e7880df9cb7062ca100c16cffa5`. Ownership completeness: True. It remains diagnostic only.

### Lamar Jackson

**Quality floor for shadow viability; correlation structure and admission competition for production absence.** Five saved Lamar discovery injections were legal, then absent from the final 205. His strongest saved-rule forced roster is 0.488 below the frontier, with only 0.042631 QB-stack support and no other active positive correlation terms. The saved BAL–TEN total is 43.5, and his saved mean is 16.92 despite a $7,300 salary. He cannot match the Lawrence/CIN stack contributions under these frozen values. This is model salary/stack opportunity cost plus joint admission competition, not reputation or no viable legal lineup.

Best legal diagnostic roster: QB: Lamar Jackson; RB: Chase Brown, Kenneth Walker III; WR: Parker Washington, Michael Wilson, Wan'Dale Robinson, Zay Flowers; TE: Colby Parkinson; DST: Dolphins.

Canonical roster SHA-256: `c36875acf341dd214bce003fd95a7b4b49302a4391076b63104be215fd46a604`. Ownership completeness: True. It remains diagnostic only.

The original solver branch/rejection lineage is not exhaustive enough to attribute every missing player to a single dollar or cap. The exact observable mechanics above replace “construction cause unisolated”; deeper causal separation would require a new generation/admission experiment while keeping this frozen pool unchanged.

## Validation, saved artifacts and prospective limits

The 14 focused thesis-shadow/completion tests passed. Completion validation replays all 205 saved scores, checks source/supplement hashes, checks each required player, validates every diagnostic/control roster and arithmetic, and compares production state before/after. A local completion manifest hashes this document and its evidence. The v3 database freeze and historical validation results reported in the prior handoff are preserved; no database append/update/delete is performed by this completion.

Evidence files: `artifacts/week4-dynamic-thesis-shadow-8b5c114c.json` (preserved v3), `artifacts/week4-thesis-frozen-analysis-inputs-8b5c114c.json` (read-only export), `artifacts/week4-thesis-opportunity-cost-8b5c114c-v2.json` (authoritative completion supplement), `artifacts/week4-thesis-completion-manifest.json` (file hashes). The initial `week4-thesis-opportunity-cost-8b5c114c.json` is a superseded template-only diagnostic, not the final evidence for forced inclusion.

These hypotheses are frozen pre-lock: membership, four tolerances, descriptive depth labels, Pareto axes, QB controls, shadow representatives and allocation. Future outcomes belong in a separate evaluation artifact and must not revise these decisions.

## Required final answers

### Does this slate support five genuinely strong directional theses?

**NO.** Inside .20 there are four viable stack families, but only three broad QB directions (Lawrence/JAX passing, Burrow/CIN passing, Brissett/ARI passing). Brissett is thin at that quality boundary. Lawrence’s two stack shapes do not create two independent games.

### How many genuinely distinct canonical game environments are represented?

**Two primary environments: JAX@CIN and ARI@NYG** in the five- and twenty-entry shadows. The full candidate universe spans more games, and production also anchors KC@LV. Mahomes and Cousins are opposite directions within that same KC@LV environment.

### Why is Brissett viable?

His $5,000 salary and the projected Wilson/McBride stack leave room for enough non-QB production to offset the QB points sacrificed. Against Allen’s comparable legal roster, he gives up **6.08 QB mean** and gains **11.45 non-QB mean**, net **+5.37**; summed P90 is **+7.71**. Against Lawrence’s comparable roster, mean is **+2.68** and summed P90 **+4.24**, but the selector is **0.00884 worse**. He is competitive, not the overall winner.

### Is Brissett’s viability driven primarily by QB value, salary allocation, stack quality, correlation, candidate-generation behavior, or a mixture?

**Primarily salary allocation, supported by projected stack quality; a mixture with role/model dependencies.** His correlation/context bonuses are weaker than the leaders. Free-structure required-QB optimization reproduces rank 83, reducing the case for a pure candidate/selector artifact. Classification: **GENUINE SALARY-EFFICIENCY THESIS**, conditional on the frozen model.

### If I entered exactly five lineups, which five shadow representatives would the thesis system choose?

- `8b5c114c-b0d2-419e-8f41-bdcbc2674c71` / **candidate #1** — Trevor Lawrence QB+2 + BB, JAX@CIN.
- `8b5c114c-b0d2-419e-8f41-bdcbc2674c71` / **candidate #6** — Trevor Lawrence QB+2 + BB, JAX@CIN.
- `8b5c114c-b0d2-419e-8f41-bdcbc2674c71` / **candidate #31** — Trevor Lawrence QB+3 + BB, JAX@CIN.
- `8b5c114c-b0d2-419e-8f41-bdcbc2674c71` / **candidate #48** — Joe Burrow QB+2 + BB, JAX@CIN.
- `8b5c114c-b0d2-419e-8f41-bdcbc2674c71` / **candidate #83** — Jacoby Brissett QB+2 / no BB, ARI@NYG.

The complete rosters, canonical roster hashes, exposures and overlap matrix are listed above. These five remain shadow recommendations.

### If I entered 20 lineups, how would the system allocate them by thesis?

- **4** — Jacoby Brissett QB+2 / no BB, ARI@NYG.
- **10** — Trevor Lawrence QB+2 + BB, JAX@CIN.
- **2** — Trevor Lawrence QB+3 + BB, JAX@CIN.
- **4** — Joe Burrow QB+2 + BB, JAX@CIN.

**Totals: 12 Lawrence, 4 Burrow, 4 Brissett; 16 JAX@CIN, 4 ARI@NYG.** Two Brissett entries require widening beyond .20. Four construction sets do not establish five independent football scenarios.

### What is still heuristic or unvalidated?

- Thesis boundaries, absolute tolerances, depth labels, Pareto axes and lexicographic priorities are pregame research choices, not learned contest-outcome rules.
- The saved small-field strategy borrows the Classic large-GPP correlation policy, explicitly marked unvalidated for small fields. Rule bonuses are not calibrated joint outcome probabilities.
- Summed player P90 is not lineup P90. No joint outcome simulation, covariance, field percentile, contest EV or confidence interval establishes superiority of these portfolios.
- The 205-candidate universe is finite and generated by QB shards plus structural discovery and joint cap/target admission. Strong forced-inclusion omissions demonstrate incomplete search coverage. Diagnoses isolate legal feasibility and observable stages, not every hidden causal branch.
- The four-non-QB comparability rule and RB-flex/WR+TE structure are heuristic. The free-structure sensitivity confirms the original QB peaks but does not isolate salary independently of teammates.
- Availability uncertainty, cheap-role evidence gaps, ownership coverage and projection error remain. Brissett’s thin frontier depth and the relaxed two slots in the 20-entry portfolio matter.
- Different portfolio constraints make production/shadow deltas descriptive. Actuals must be evaluated later in a separate time-safe artifact, without changing this pre-lock record.
