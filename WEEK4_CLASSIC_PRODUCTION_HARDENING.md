# Week 4 Classic production hardening

## Decision

The new pre-lock Classic small-field run is [532ff446-8261-4be2-b26e-3e44837e556a](artifacts/optimizer-report-2026-w4-sunday-main-532ff446.html). It is **DEVELOPMENT_PREVIEW — NOT ENTRY READY**. The original optimizer run `40f1c849-07cf-4346-994c-04b9663e662d` remains unchanged. These are pregame comparisons; no Week 3 winner fitting, postgame outcomes, player-specific rules, projection-weight changes, or ownership-model changes were used.

### Would you trust this run as entry-ready if kickoff were in five minutes?

**NO.** All 466 eligible players lack a captured Week 4 market total, spread, and implied total. Capture a real, timestamped, pre-lock line for every game, build a new projection run from those inputs, and rerun the optimizer. The current preview must not be exported as entry-ready.

## 1. Market root cause and lineage

The market source was `public.raw_nfl_schedule` from nflreadpy. Before the original optimizer cutoff, the database contained **16 Week 4 schedule rows and 0 rows with both total and spread**. The rows were ingested on September 22; their `raw_row_json.total_line`, `spread_line`, and `observed_at` were null. No captured market snapshot matched the Week 4 slate because no source row contained a line. Team aliases (including `LA` → `LAR`) and the raw game IDs were present, but could not turn an absent line into a market quote.

`canonical_projection_inputs.prepare_inputs` filled missing numeric feature-matrix fields with `0.0`, including all market fields. The old projection feature JSON therefore stored zeros for 538 players; the old optimizer's frozen eligible pool had 471/471 zero totals, spreads, and implied totals with null market source and observation time. Its SQL nevertheless marked those projection features `market_context_point_in_time_safe = TRUE`. The candidate reporter ranked an all-zero distribution and labeled some zero-total games `high-total competitive`. The failure was **A (source lines absent) plus C (null converted to zero)**, followed by an incorrect safe flag. There is no evidence of a valid Week 4 line lost by team normalization or a failed source-to-game join.

The corrected projection-input contract preserves null market fields; model matrices may still impute internally without publishing imputed numbers as market truth. Optimizer SQL exposes a line only with captured source and observation metadata, and its safe flag requires a positive game total. Market lookup uses season/week, normalized team/opponent and, when available, the source game ID. A line observed after the decision cutoff or at/after kickoff is rejected. The report labels missing evidence `market environment unavailable` and shows null values, including in component availability.

## 2. Team, opponent, exclusion and salary identity

The original request excluded opponents `DEN`. The frozen pre-exclusion pool had **29** such players, all on `SF`; all 29 were removed, and zero survived in the final eligible pool. All 29 matched their saved DraftKings salary-row team/opponent. The original 471 eligible players had zero team/opponent mismatches against the saved salary rows that also appeared in `target.snapshot_salary`; names that looked surprising were the same in the DraftKings salary evidence. The new run checks **466** eligible canonical IDs, salary-row IDs, teams, opponents, and salaries against `public.curated_salary`: **0 violations**. This is a hard invariant before candidate generation.

## 3. Production rules

| Area | Rule |
| --- | --- |
| Availability mode | `availability_risk_mode=conservative` by default; `off` must be explicit |
| OUT / INACTIVE | Excluded |
| DOUBTFUL | Excluded unless canonical-ID override includes a saved reason |
| QUESTIONABLE ELEVATED | Candidate ≤25%; selected ≤40%; max one per lineup; ≤60% of selected lineups contain any |
| QUESTIONABLE FULL ROLE | Candidate ≤50%; selected ≤60%; full role requires saved full practice and unrestricted workload with timestamps |
| Normal non-elite candidate | ≤70%; healthy elite ≤90%; a normal explicit lock can be 100% |
| Selected portfolio | Pairwise overlap ≤6/9; QB ≤60%; normal non-elite skill player ≤80%; at least two QB paths for multi-entry |
| Quality-tolerant diversity | Consider third QB path and second stack family if each costs ≤0.10 selector points per lineup versus the constrained baseline |
| Ownership | Complete estimate required for every selected player; no soft ownership selector weight |

Overrides are persisted with canonical player ID and reason. They cannot silently relax a cap. A healthy elite selected in 5/5 is a visible warning. Market-dependent components are reported as `UNAVAILABLE` with a reason; ownership soft terms are `DISABLED`; active zero terms are distinguished from missing evidence.

## 4. Entry readiness and severity

`ENTRY_READY` requires positive salaries, saved salary identity, valid team/opponent/game/kickoff, pre-lock decision time, positive mean/P90 for all eligible players and at least 100 eligible projections, complete selected ownership, valid market data for every eligible game, dated questionable evidence, a filled pool of at least 100 legal candidates, all production risk and concentration caps, five legal selections, ≤6 overlap, and at least two QB paths. An eligible-pool ownership gap outside otherwise complete candidates/selection is a warning. Missing market data yields `DEVELOPMENT_PREVIEW`; corrupt sourced market values, salary/identity conflicts, post-lock evidence used, underfill, illegal lineups, and cap violations are `BLOCKER`s and yield `BLOCKED`. Healthy elite 100% selected exposure and only two QB paths are warnings.

| Check | Status | Evidence |
| --- | --- | --- |
| Portfolio overlap | PASS | maximum 6/9 |
| Ownership coverage | WARNING | eligible 458/466; candidate lineups 205/205; selected players 18/18 |
| Candidate-pool size | PASS | 205 candidates; deficit 0 |
| Projection coverage | PASS | 466/466 eligible projections |
| Availability evidence | PASS | questionable with undated evidence: 0 |
| QB/game-path diversity | PASS | 3 distinct paths |
| Salary/slate integrity | PASS | positive saved salaries |
| Candidate concentration | PASS | cap violations []; unexplained >80% [] |
| Legal lineup validation | PASS | 5/5 selected lineups |
| Market/game environment | DEVELOPMENT_PREVIEW | missing 466/466; corrupt or late 0 |
| Questionable-player risk | PASS | candidate violations []; selected violations [] |
| Selected player exposure | WARNING | cap violations []; 100% elite cores ['1f90d290-afb4-48ae-8052-fa99040b8ddb', '319a7e5c-7967-4405-90f9-36ddfea66dfd'] |
| Kickoff/pre-lock evidence | PASS |  |
| Player/team/opponent identity | PASS | saved salary identities match |

The first section of the HTML report prints `ENTRY READY: NO` and these checks. A failed optimizer job renders as `BLOCKED` rather than a polished ready report.

## 5. Structural-shadow underfill and production funnel

The original structural shadow requested **209** candidates and admitted **29**, so `180 underfill` meant **180 missing candidates**, not 180 rejected lineups. It tried 73 targeted discovery requests: 50 new, 1 duplicate, and 22 infeasible or below quality floor. It missed minimum coverage in 66/72 QB/family combinations. Most high-score alternatives still reused the same salary core; admission hit player and questionable budgets, then pruned against the smaller actual denominator. It did not search enough alternate legal paths after rejection. Quality floors, family feasibility and caps interacted; the old report did not separate exact rejection counts.

Production candidate admission enforces caps, and refill applies the remaining cap budgets in each solver call while searching alternate legal stack templates. It does not relax a cap to fill a pool. The final run requested **205**, solved **284**, found **284** legal rosters, rejected **18** by injury cap and **61** by player cap, and admitted **205** with **0** deficit. Duplicate, quality, and family rejection counts were zero in this final admission. Fixed-input reruns `19320fb4-7fe0-46fa-ae89-1e308c29b38d` and `ce73746e-8b27-45de-ad26-098647d1467f`, plus the fresh-cutoff run, had identical ordered candidate-roster and selected-roster hashes and selected ranks. The fresh run used decision cutoff `2026-09-29 21:02:47 EDT`. The new frozen structural comparison admitted **205/205**, with 0 underfill. If a future search cannot fill its target, it records `CANDIDATE_POOL_UNDERFILLED` and the funnel, and readiness is blocked.

## 6. Before and after, pregame only

| Measure | Original 40f1c849 | New 532ff446 |
| --- | ---: | ---: |
| Entry readiness | Not evaluated; market zeros falsely shown | DEVELOPMENT_PREVIEW |
| Sourced market coverage | 0/471; rendered as zero | 0/466; rendered unavailable |
| Candidates | 209 | 205 |
| Structural shadow underfill | 180/209 | 0/205 |
| Puka candidate exposure | 195/209 (93.3%) | 51/205 (24.9%) |
| Puka selected exposure | 5/5 | 2/5 |
| Jacoby Brissett selected | 5/5 | 3/5 |
| Distinct QB/game paths | 1 | 3 |
| Maximum pairwise overlap | 7/9 | 6/9 |
| Projected mean sum | 550.489 | 541.899 (cost 8.591) |
| Summed player P90 | 1052.367 | 1045.400 (cost 6.966) |
| Selector score sum | 28.270 | 27.982 (cost 0.288) |
| Selected ownership | 5/5 complete lineups | 5/5 complete lineups; eligible 458/466; candidate lineups 205/205; selected players 18/18 |

### Candidate exposure (top 20)

The [complete candidate exposure CSV](artifacts/week4-classic-candidate-exposure-532ff446.csv) has every generated player, canonical ID, cap, availability status, and selected exposure.

| Player | Count | Share | Core class |
| --- | ---: | ---: | --- |
| Kyren Williams | 159/205 | 77.6% | elite_high_confidence |
| Kenneth Walker III | 153/205 | 74.6% | elite_high_confidence |
| Chase Brown | 142/205 | 69.3% | elite_high_confidence |
| Michael Wilson | 141/205 | 68.8% | elite_high_confidence |
| Parker Washington | 134/205 | 65.4% | elite_high_confidence |
| Jacoby Brissett | 134/205 | 65.4% | low_owned_value |
| Cade Otton | 116/205 | 56.6% | elite_high_confidence |
| Dolphins | 97/205 | 47.3% | low_owned_value |
| Zay Flowers | 82/205 | 40.0% | elite_high_confidence |
| Trey McBride | 74/205 | 36.1% | elite_high_confidence |
| Derrick Henry | 73/205 | 35.6% | elite_high_confidence |
| Puka Nacua | 51/205 | 24.9% | elevated_risk_questionable |
| Trevor Lawrence | 49/205 | 23.9% | ordinary_core |
| Bucky Irving | 45/205 | 22.0% | elite_high_confidence |
| Chargers | 35/205 | 17.1% | low_owned_value |
| Cooper Kupp | 29/205 | 14.1% | elite_high_confidence |
| Caleb Douglas | 24/205 | 11.7% | elevated_risk_questionable |
| Titans | 21/205 | 10.2% | low_owned_value |
| Darnell Mooney | 20/205 | 9.8% | elite_high_confidence |
| Patriots | 19/205 | 9.3% | low_owned_value |

### Five-lineup player exposure

| Player | Count | Share |
| --- | ---: | ---: |
| Cade Otton | 5/5 | 100.0% |
| Kyren Williams | 5/5 | 100.0% |
| Kenneth Walker III | 4/5 | 80.0% |
| Michael Wilson | 4/5 | 80.0% |
| Chase Brown | 4/5 | 80.0% |
| Dolphins | 3/5 | 60.0% |
| Parker Washington | 3/5 | 60.0% |
| Jacoby Brissett | 3/5 | 60.0% |
| Puka Nacua | 2/5 | 40.0% |
| Chargers | 2/5 | 40.0% |
| Zay Flowers | 2/5 | 40.0% |
| Carnell Tate | 2/5 | 40.0% |
| Bucky Irving | 1/5 | 20.0% |
| Derrick Henry | 1/5 | 20.0% |
| Matthew Golden | 1/5 | 20.0% |
| Jordan Love | 1/5 | 20.0% |
| Jaxon Smith-Njigba | 1/5 | 20.0% |
| Trevor Lawrence | 1/5 | 20.0% |

### Pairwise overlap

| Lineup | 1 | 2 | 3 | 4 | 5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 9 | 5 | 6 | 6 | 4 |
| 2 | 5 | 9 | 4 | 5 | 6 |
| 3 | 6 | 4 | 9 | 6 | 4 |
| 4 | 6 | 5 | 6 | 9 | 5 |
| 5 | 4 | 6 | 4 | 5 | 9 |

### QB/game paths and stack families

| QB and primary game | Lineups |
| --- | ---: |
| Jacoby Brissett / ARI–NYG | 3 |
| Jordan Love / GB–TB | 1 |
| Trevor Lawrence / JAX–CIN | 1 |

| Stack family | Lineups |
| --- | ---: |
| QB+1 | 3 |
| QB+1+bring-back | 2 |

### Quality-tolerant path frontier

These are saved selector scores and summed player means/P90s under the same hard caps. The one-path minimum does not produce one-path exposure because the 60% QB cap already forces at least two.

| Required paths | Feasible | Selector sum | Mean sum | P90 sum | Max overlap |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | YES | 28.015 | 542.802 | 1046.303 | 6 |
| 2 | YES | 28.015 | 542.802 | 1046.303 | 6 |
| 3 | YES | 27.982 | 541.899 | 1045.400 | 6 |

Three paths cost 0.033 selector points, 0.903 mean, and 0.903 summed P90 compared with the best two-path portfolio. The selector cost per lineup is 0.007, below 0.05, 0.10, and 0.15 candidate tolerances, so all three tolerances select the third path on this frozen slate. The saved best alternative stack-family cost is 0.000 selector points; the selected portfolio contains 2 families, including 2 bring-back lineups. Diversification follows the selector score; it does not force a bring-back in each entry.

## 7. Validation and files

Targeted Classic/market/optimizer tests: **142 passed**. Full backend suite: **885 passed, 4 failed**; the four failures are Showdown single-TE expectations in `test_showdown_single_entry.py` and `test_showdown_three_max.py`. They do not exercise the changed Classic paths; their baseline status was not independently verified. UI tests: **37 passed**. TypeScript/Vite build: **passed**. The final run persisted five legal lineups, the original run remains unchanged, and the saved market fields are null rather than zero.

Changed code: `backend/app/product_services/canonical_projection_inputs.py`, `predictions.py`, `optimizer.py`, `gpp_optimizer.py`, `classic_prospective.py`, `classic_small_field.py`, `ui/src/optimizerReport.ts`, and targeted Python tests. Updated `README.md`, `docs/product/optimizer_filters.md`, and `RELEASE_NOTES.md`. This report, the exposure CSV, and the new HTML optimizer report are new artifacts.

The remaining product input is a captured Week 4 market snapshot. Recheck market freshness, rebuild projections, and rerun before entry. Shared market null handling reaches Showdown through the projection and pool loaders; Showdown captain/game-script selection was not changed. Full Showdown salary identity and entry-readiness rules still need their own verified run before Thursday use.

## Final entry decision

### Would you trust this run as entry-ready if kickoff were in five minutes?

**NO.** Capture timestamped Week 4 totals and spreads for the slate games, rebuild the projection run, and rerun the optimizer so all 466 eligible players have sourced pre-lock market context. Until then, the saved run is `DEVELOPMENT_PREVIEW — NOT ENTRY READY`.
