# Classic Large-GPP app/Codex parity and primary-game cap

Frozen reference: `d0e2ff8f-96cd-4fc0-ac7e-8297d4504701`, 2026 Week 4 Sunday Main, created 2026-10-03 11:39:57 UTC. Projection run `ce719439-c999-4f88-a15c-ebdd89e28618`; ownership run `5cf3c66d-232a-497a-b17e-386f87660e71`. Five entries and 80% global maximum exposure throughout.

**Exact frozen solver parity: PASS.** The uncapped app has five CIN–JAX primary games. Cap 3 changes this to three CIN–JAX and two DAL–HOU lineups at a 0.7167% lower objective total. This is the clearest tested expression of the concentration preference. No permanent defaults, projections, weights, injury rules, ownership rules, or entries were changed.

## Authoritative contract and scope

`classic_large_gpp_effective_strategy_v1` stores the ordered canonical Player inputs, eligibility policy/IDs, all pipeline options, resolved runtime configuration, requested/effective game cap and source, execution mode, deviations, input/code/solver hashes, and effective-contract hash. App execution and offline parity call the same `execute_strategy_contract`; reports consume the saved contract and audit. New app runs persist it in existing optimizer-run JSON and expose it through the saved-results API.

The legacy fixture predates this contract. Its immutable `classic_run_input_snapshot` freezes the full ordered 154-player final solver frame, and the saved upstream inclusion/removal ledger confirms exactly those 154 IDs. Replay starts at that eligibility boundary. It does not reconstruct upstream ingestion, identity matching or injury assessment from today’s database. The fixture manifest preserves the original five source files and hashes. This bounds the YES below to the frozen app execution, not a claim of independently regenerating missing historical raw source inputs.

### Production trace

| Dimension | Effective production behavior |
|---|---|
| Eligibility | Saved salary identity and upstream safety/availability/user exclusions; positive mean/P90; starting QB or explicit specialty role; then shared Large-GPP ranking policy. DEN-opponent exclusions are frozen. |
| Initial positional caps | QB 14, RB 20, WR 34, TE 16, DST 12. Safety addbacks can exceed these caps. |
| Score floors | Context-adjusted P90: QB 17, RB 11, WR 10, TE 8, DST 0. Qualify by score OR positional ceiling/value minimum, then value floor. |
| Ceiling/value thresholds | QB/RB 3.0 per $1K; WR/TE 3.4; DST 0. WR/TE darts ≤$4,500 and ≥3.4 per $1K. |
| Initial team candidate caps | WR 4, TE 3, RB 2. |
| Safety addbacks | Best missing QB per team, top two WR/TE per team, strongest opposing RB/WR/TE, strongest same-team WR/TE ≤$4,000. They do not undo upstream exclusions. Final frozen frame has 23 QBs and 154 total players. |
| Local legality | Nine unique canonical IDs; one QB, at least two RB/three WR/one TE, one DST, skill FLEX, salary ≤$50,000; single TE; no offense against selected DST; team ≤4 and game ≤5. |
| Stacks | Minimum WR/TE catchers and RB/WR/TE bring-backs cycle (1,0), (1,1), (2,0), (2,1), (1,0). These are minimums, not exact stack sizes. |
| Scoring | Existing normalized mean/context .35, marginal P90/context .45, leverage .05, correlation .15 with multiplier 1.0. Existing pair/format rules apply. No soft ownership/duplication score is invented. The full frozen ownership frame is available. |
| Ownership/tag constraints | Chalk ≤5; punts ≤2; minimum leverage 0; ownership sum ≤160. Existing data-availability fallbacks are resolved in the contract. |
| Player exposure | ceil(5 × .80)=4, intersect stricter floor(5 × per-player cap). Explicit locks/minimums retain existing semantics; none are present here. |
| Injury/risk | Existing upstream eligibility only for Large GPP; no Small-field conservative risk policy added. Frozen risk buckets are diagnostic and shown below. |
| Uniqueness | At least two distinct players; overlap ≤7 against every accepted prior roster. |
| Primary game | Sorted uppercase QB team/opponent pair; CIN-JAX and JAX-CIN share one budget. Null/omitted means no portfolio game cap. |
| Generation/selection | Sequential exposure-aware exact lineup ILP. Each accepted candidate becomes the next selected lineup; there is no separate broad production candidate pool or joint portfolio optimization. An infeasible cap can fail/underfill; exposure and game caps are never relaxed. |

## Reconciliation and evidence

For each of the five solves, numerical variable bounds and feasible constraints match the saved app control-model replay; primary objective coefficients match the pre-change capture; selected canonical roster sets match; primary and reconstructed report scores match to 1e-9. Normalized structural SHA-256 comparisons ignore only JSON integer/float spelling, additive term ordering and solved values. They retain variable identities, categories, bounds, senses and coefficients. The complete final Player input digest and implementation/CBC fingerprints remain saved.

| Check | Outcome |
|---|---|
| Frozen fixture/snapshot checksums | PASS |
| Eligible 154 IDs and immutable inclusion ledger | PASS |
| Every frozen projection/P90 | PASS |
| Ordered generation inputs and resolved configuration | PASS |
| Five feasible regions and objective coefficient sets | PASS |
| Five accepted candidates / final five rosters | PASS |
| Each candidate score / summed portfolio score | PASS |
| Player exposures, canonical primary games and overlap | PASS, independently counted from identical roster IDs |

No material INPUT_MISMATCH, ELIGIBILITY_MISMATCH, GENERATION_MISMATCH, SCORING_MISMATCH, CONSTRAINT_MISMATCH or SOLVER/TIE_BREAK_MISMATCH remains. No alternative tied roster was observed; the ordered frozen canonical-ID frame, fixed variable/constraint creation order, exact coefficient set and recorded bundled CBC/PuLP implementation reproduce the same tie behavior. Replay refuses code/solver drift pending a new explicit parity check.

**REPORT_ONLY_MISMATCH reconciled:** legacy generic rule-profile weights differ from the actual resolved Large-GPP weights; the old stack description says “include RB” while the actual QB catcher constraint uses WR/TE; raw JSON checksums differed without coefficient/bound differences. The new contract renders executed settings. These descriptions were not used to change the solver. The old app’s candidate manifest says unavailable because it did not save a complete explicit candidate pool; its sequential candidate universe is defined by the five proven-equal ILP feasible regions, not an undocumented expanded pool.

Prior broad Small-field research must not be relabelled as Large-GPP parity: it changes eligible breadth, generation/selection and risk/overlap policy. `PARITY` requires named production behavior. `RESEARCH_SHADOW` requires declared deviations and is never silently promoted.

## Same-frame sensitivity

Objective cost is measured against the uncapped **sequential** portfolio. It is not a proof of the globally best possible five-lineup portfolio. Summed marginal P90 is the sum of player P90 values across entries, not a portfolio quantile or win probability.

| Case | Canonical games | Objective total | Objective cost | Cost % | Mean sum | Marginal P90 sum | Max overlap | Status / solve time |
|---|---|---:|---:|---:|---:|---:|---:|---|
| A_no_cap | CIN-JAX: 5 | 26.843941128 | 0.000000000 | 0.0000% | 650.684805 | 1146.725459 | 7 | completed; 10.53s |
| B_cap4 | CIN-JAX: 4, DAL-HOU: 1 | 26.791249034 | 0.052692094 | 0.1963% | 656.994430 | 1153.201165 | 7 | completed; 9.86s |
| C_cap3 | CIN-JAX: 3, DAL-HOU: 2 | 26.651544346 | 0.192396783 | 0.7167% | 656.014674 | 1149.937775 | 7 | completed; 8.26s |
| D_cap2 | CHI-NYJ: 1, CIN-JAX: 2, DAL-HOU: 2 | 26.408394658 | 0.435546470 | 1.6225% | 655.751883 | 1147.863903 | 7 | completed; 7.89s |

Each accepted lineup solve returned CBC Optimal with a proven optimal primary objective for that sequential step. All four cases contain exactly five legal lineups, retain the four-appearance player ceiling, and pass the game-cap/overlap audit. The app reference’s worker duration was approximately 21 seconds; offline solves here take about 8–12 seconds including mean/P90 control comparisons. These are frozen Large-GPP timings, not estimates for broader Small-field workflows or projection rebuilds.

## Exact selected portfolios and risk

### A_no_cap

Mode: **PARITY**; label `classic_large_gpp_v1`. No strategy deviation. Solver status: **completed**. Portfolio optimality: sequential; joint optimum not proven.

QB allocation: Trevor Lawrence: 4, Joe Burrow: 1. Canonical games: CIN-JAX: 5.

| Slot | Exact roster | QB | Objective | Mean | Marginal P90 | Salary |
|---|---|---|---:|---:|---:|---:|
| 1 | R1 | Trevor Lawrence | 5.419170110 | 129.973397 | 228.607672 | $49,600 |
| 2 | R2 | Trevor Lawrence | 5.415412070 | 133.325159 | 233.534591 | $50,000 |
| 3 | R3 | Trevor Lawrence | 5.411899068 | 132.526873 | 233.155875 | $49,800 |
| 4 | R4 | Trevor Lawrence | 5.405767881 | 130.048404 | 228.366650 | $49,800 |
| 5 | R5 | Joe Burrow | 5.191691999 | 124.810970 | 223.060672 | $50,000 |

Frozen risk appearances: out: 0, doubtful: 0, questionable_elevated: 6, questionable_full_role: 0, normal: 39. No new risk cap is enforced.

Risk player exposures: D'Andre Swift: 1/5 (questionable_elevated); Puka Nacua: 1/5 (questionable_elevated); Jakobi Meyers: 4/5 (questionable_elevated).

Pairwise overlap (diagonal=9):

```text
9 7 7 7 3
7 9 6 6 2
7 6 9 6 3
7 6 6 9 2
3 2 3 2 9
```

Player exposures (all selected IDs appear in the roster catalog):


| Player | Appearances / 5 | Rate | Effective appearance limit |
|---|---:|---:|---:|
| Brenton Strange | 4 | 80% | 4 |
| Jakobi Meyers | 4 | 80% | 4 |
| Javonte Williams | 4 | 80% | 4 |
| Michael Wilson | 4 | 80% | 4 |
| Parker Washington | 4 | 80% | 4 |
| Trevor Lawrence | 4 | 80% | 4 |
| Chase Brown | 3 | 60% | 4 |
| Kenneth Walker III | 3 | 60% | 4 |
| Rams | 3 | 60% | 4 |
| Tee Higgins | 3 | 60% | 4 |
| Ja'Marr Chase | 2 | 40% | 4 |
| Buccaneers | 1 | 20% | 4 |
| Cade Otton | 1 | 20% | 4 |
| Cardinals | 1 | 20% | 4 |
| D'Andre Swift | 1 | 20% | 4 |
| Joe Burrow | 1 | 20% | 4 |
| Puka Nacua | 1 | 20% | 4 |
| Ryan Flournoy | 1 | 20% | 4 |

Displaced: none. Additional: none. Reference: uncapped A.

### B_cap4

Mode: **RESEARCH_SHADOW**; label `classic_large_gpp_v1 + research_shadow`. Deviations: max_lineups_per_primary_game=4; all other frozen inputs and constraints unchanged Solver status: **completed**. Portfolio optimality: sequential; joint optimum not proven.

QB allocation: Trevor Lawrence: 4, Dak Prescott: 1. Canonical games: CIN-JAX: 4, DAL-HOU: 1.

| Slot | Exact roster | QB | Objective | Mean | Marginal P90 | Salary |
|---|---|---|---:|---:|---:|---:|
| 1 | R1 | Trevor Lawrence | 5.419170110 | 129.973397 | 228.607672 | $49,600 |
| 2 | R2 | Trevor Lawrence | 5.415412070 | 133.325159 | 233.534591 | $50,000 |
| 3 | R3 | Trevor Lawrence | 5.411899068 | 132.526873 | 233.155875 | $49,800 |
| 4 | R4 | Trevor Lawrence | 5.405767881 | 130.048404 | 228.366650 | $49,800 |
| 5 | R6 | Dak Prescott | 5.138999905 | 131.120596 | 229.536378 | $50,000 |

Frozen risk appearances: out: 0, doubtful: 0, questionable_elevated: 5, questionable_full_role: 0, normal: 40. No new risk cap is enforced.

Risk player exposures: D'Andre Swift: 1/5 (questionable_elevated); Puka Nacua: 1/5 (questionable_elevated); Jakobi Meyers: 3/5 (questionable_elevated).

Pairwise overlap (diagonal=9):

```text
9 7 7 7 2
7 9 6 6 2
7 6 9 6 2
7 6 6 9 2
2 2 2 2 9
```

Player exposures (all selected IDs appear in the roster catalog):


| Player | Appearances / 5 | Rate | Effective appearance limit |
|---|---:|---:|---:|
| Brenton Strange | 4 | 80% | 4 |
| Javonte Williams | 4 | 80% | 4 |
| Michael Wilson | 4 | 80% | 4 |
| Parker Washington | 4 | 80% | 4 |
| Rams | 4 | 80% | 4 |
| Trevor Lawrence | 4 | 80% | 4 |
| Chase Brown | 3 | 60% | 4 |
| Jakobi Meyers | 3 | 60% | 4 |
| Kenneth Walker III | 3 | 60% | 4 |
| Ja'Marr Chase | 2 | 40% | 4 |
| Tee Higgins | 2 | 40% | 4 |
| Buccaneers | 1 | 20% | 4 |
| Cade Otton | 1 | 20% | 4 |
| CeeDee Lamb | 1 | 20% | 4 |
| D'Andre Swift | 1 | 20% | 4 |
| Dak Prescott | 1 | 20% | 4 |
| Kalif Raymond | 1 | 20% | 4 |
| Puka Nacua | 1 | 20% | 4 |
| Ryan Flournoy | 1 | 20% | 4 |

Displaced: R5. Additional: R6. Reference: uncapped A.

### C_cap3

Mode: **RESEARCH_SHADOW**; label `classic_large_gpp_v1 + research_shadow`. Deviations: max_lineups_per_primary_game=3; all other frozen inputs and constraints unchanged Solver status: **completed**. Portfolio optimality: sequential; joint optimum not proven.

QB allocation: Trevor Lawrence: 3, Dak Prescott: 2. Canonical games: CIN-JAX: 3, DAL-HOU: 2.

| Slot | Exact roster | QB | Objective | Mean | Marginal P90 | Salary |
|---|---|---|---:|---:|---:|---:|
| 1 | R1 | Trevor Lawrence | 5.419170110 | 129.973397 | 228.607672 | $49,600 |
| 2 | R2 | Trevor Lawrence | 5.415412070 | 133.325159 | 233.534591 | $50,000 |
| 3 | R3 | Trevor Lawrence | 5.411899068 | 132.526873 | 233.155875 | $49,800 |
| 4 | R7 | Dak Prescott | 5.251963032 | 132.152052 | 230.952406 | $50,000 |
| 5 | R8 | Dak Prescott | 5.153100065 | 128.037192 | 223.687231 | $49,800 |

Frozen risk appearances: out: 0, doubtful: 0, questionable_elevated: 4, questionable_full_role: 0, normal: 41. No new risk cap is enforced.

Risk player exposures: Puka Nacua: 1/5 (questionable_elevated); Jakobi Meyers: 3/5 (questionable_elevated).

Pairwise overlap (diagonal=9):

```text
9 7 7 3 4
7 9 6 4 3
7 6 9 4 4
3 4 4 9 4
4 3 4 4 9
```

Player exposures (all selected IDs appear in the roster catalog):


| Player | Appearances / 5 | Rate | Effective appearance limit |
|---|---:|---:|---:|
| Brenton Strange | 4 | 80% | 4 |
| Chase Brown | 4 | 80% | 4 |
| Javonte Williams | 4 | 80% | 4 |
| Michael Wilson | 4 | 80% | 4 |
| Parker Washington | 4 | 80% | 4 |
| Jakobi Meyers | 3 | 60% | 4 |
| Kenneth Walker III | 3 | 60% | 4 |
| Tee Higgins | 3 | 60% | 4 |
| Trevor Lawrence | 3 | 60% | 4 |
| CeeDee Lamb | 2 | 40% | 4 |
| Dak Prescott | 2 | 40% | 4 |
| Rams | 2 | 40% | 4 |
| Ryan Flournoy | 2 | 40% | 4 |
| Buccaneers | 1 | 20% | 4 |
| Cardinals | 1 | 20% | 4 |
| Dalton Schultz | 1 | 20% | 4 |
| Packers | 1 | 20% | 4 |
| Puka Nacua | 1 | 20% | 4 |

Displaced: R5, R4. Additional: R8, R7. Reference: uncapped A.

### D_cap2

Mode: **RESEARCH_SHADOW**; label `classic_large_gpp_v1 + research_shadow`. Deviations: max_lineups_per_primary_game=2; all other frozen inputs and constraints unchanged Solver status: **completed**. Portfolio optimality: sequential; joint optimum not proven.

QB allocation: Trevor Lawrence: 2, Dak Prescott: 2, Caleb Williams: 1. Canonical games: CHI-NYJ: 1, CIN-JAX: 2, DAL-HOU: 2.

| Slot | Exact roster | QB | Objective | Mean | Marginal P90 | Salary |
|---|---|---|---:|---:|---:|---:|
| 1 | R1 | Trevor Lawrence | 5.419170110 | 129.973397 | 228.607672 | $49,600 |
| 2 | R2 | Trevor Lawrence | 5.415412070 | 133.325159 | 233.534591 | $50,000 |
| 3 | R7 | Dak Prescott | 5.251963032 | 132.152052 | 230.952406 | $50,000 |
| 4 | R9 | Dak Prescott | 5.205323150 | 131.725826 | 229.054564 | $50,000 |
| 5 | R10 | Caleb Williams | 5.116526297 | 128.575447 | 225.714670 | $49,800 |

Frozen risk appearances: out: 0, doubtful: 1, questionable_elevated: 3, questionable_full_role: 0, normal: 41. No new risk cap is enforced.

Risk player exposures: D'Andre Swift: 1/5 (questionable_elevated); Puka Nacua: 1/5 (questionable_elevated); Jakobi Meyers: 1/5 (questionable_elevated); Caleb Williams: 1/5 (doubtful).

Pairwise overlap (diagonal=9):

```text
9 7 3 3 4
7 9 4 4 4
3 4 9 7 2
3 4 7 9 2
4 4 2 2 9
```

Player exposures (all selected IDs appear in the roster catalog):


| Player | Appearances / 5 | Rate | Effective appearance limit |
|---|---:|---:|---:|
| Chase Brown | 4 | 80% | 4 |
| Javonte Williams | 4 | 80% | 4 |
| Michael Wilson | 4 | 80% | 4 |
| Parker Washington | 4 | 80% | 4 |
| Rams | 4 | 80% | 4 |
| Brenton Strange | 3 | 60% | 4 |
| CeeDee Lamb | 2 | 40% | 4 |
| Dak Prescott | 2 | 40% | 4 |
| Dalton Schultz | 2 | 40% | 4 |
| Kenneth Walker III | 2 | 40% | 4 |
| Ryan Flournoy | 2 | 40% | 4 |
| Tee Higgins | 2 | 40% | 4 |
| Trevor Lawrence | 2 | 40% | 4 |
| Caleb Williams | 1 | 20% | 4 |
| Cardinals | 1 | 20% | 4 |
| D'Andre Swift | 1 | 20% | 4 |
| Ja'Marr Chase | 1 | 20% | 4 |
| Jakobi Meyers | 1 | 20% | 4 |
| Kalif Raymond | 1 | 20% | 4 |
| Luther Burden III | 1 | 20% | 4 |
| Puka Nacua | 1 | 20% | 4 |

Displaced: R3, R5, R4. Additional: R10, R7, R9. Reference: uncapped A.

### expanded_no_cap

Mode: **RESEARCH_SHADOW**; label `classic_large_gpp_v1 + expanded_discovery`. Deviations: Broader discovery: each eligible QB and production minimum-stack template, two unique score-optimal constructions; production sensitivity rosters included; Candidate generation defers 80% player and game caps to final finite-pool selection; Joint finite-candidate assignment replaces sequential selection; same five production template slots and scoring Solver status: **Optimal**. Portfolio optimality: CBC optimum over this explicit finite candidate pool; no all-feasible-portfolio optimum claim.

QB allocation: Trevor Lawrence: 4, Joe Burrow: 1. Canonical games: CIN-JAX: 5.

| Slot | Exact roster | QB | Objective | Mean | Marginal P90 | Salary |
|---|---|---|---:|---:|---:|---:|
| 1 | R3 | Trevor Lawrence | 5.411899068 | 132.526873 | 233.155875 | $49,800 |
| 2 | R1 | Trevor Lawrence | 5.419170110 | 129.973397 | 228.607672 | $49,600 |
| 3 | R2 | Trevor Lawrence | 5.415412070 | 133.325159 | 233.534591 | $50,000 |
| 4 | R4 | Trevor Lawrence | 5.405767881 | 130.048404 | 228.366650 | $49,800 |
| 5 | R5 | Joe Burrow | 5.191691999 | 124.810970 | 223.060672 | $50,000 |

Frozen risk appearances: out: 0, doubtful: 0, questionable_elevated: 6, questionable_full_role: 0, normal: 39. No new risk cap is enforced.

Risk player exposures: D'Andre Swift: 1/5 (questionable_elevated); Puka Nacua: 1/5 (questionable_elevated); Jakobi Meyers: 4/5 (questionable_elevated).

Pairwise overlap (diagonal=9):

```text
9 7 6 6 3
7 9 7 7 3
6 7 9 6 2
6 7 6 9 2
3 3 2 2 9
```

Player exposures (all selected IDs appear in the roster catalog):


| Player | Appearances / 5 | Rate | Effective appearance limit |
|---|---:|---:|---:|
| Brenton Strange | 4 | 80% | 4 |
| Jakobi Meyers | 4 | 80% | 4 |
| Javonte Williams | 4 | 80% | 4 |
| Michael Wilson | 4 | 80% | 4 |
| Parker Washington | 4 | 80% | 4 |
| Trevor Lawrence | 4 | 80% | 4 |
| Chase Brown | 3 | 60% | 4 |
| Kenneth Walker III | 3 | 60% | 4 |
| Rams | 3 | 60% | 4 |
| Tee Higgins | 3 | 60% | 4 |
| Ja'Marr Chase | 2 | 40% | 4 |
| Buccaneers | 1 | 20% | 4 |
| Cade Otton | 1 | 20% | 4 |
| Cardinals | 1 | 20% | 4 |
| D'Andre Swift | 1 | 20% | 4 |
| Joe Burrow | 1 | 20% | 4 |
| Puka Nacua | 1 | 20% | 4 |
| Ryan Flournoy | 1 | 20% | 4 |

Displaced: none. Additional: none. Reference: matching production sensitivity.

### expanded_cap3

Mode: **RESEARCH_SHADOW**; label `classic_large_gpp_v1 + expanded_discovery`. Deviations: Broader discovery: each eligible QB and production minimum-stack template, two unique score-optimal constructions; production sensitivity rosters included; Candidate generation defers 80% player and game caps to final finite-pool selection; Joint finite-candidate assignment replaces sequential selection; same five production template slots and scoring; max_lineups_per_primary_game=3 Solver status: **Optimal**. Portfolio optimality: CBC optimum over this explicit finite candidate pool; no all-feasible-portfolio optimum claim.

QB allocation: Dak Prescott: 2, Trevor Lawrence: 3. Canonical games: CIN-JAX: 3, DAL-HOU: 2.

| Slot | Exact roster | QB | Objective | Mean | Marginal P90 | Salary |
|---|---|---|---:|---:|---:|---:|
| 1 | R7 | Dak Prescott | 5.251963032 | 132.152052 | 230.952406 | $50,000 |
| 2 | R3 | Trevor Lawrence | 5.411899068 | 132.526873 | 233.155875 | $49,800 |
| 3 | R8 | Dak Prescott | 5.153100065 | 128.037192 | 223.687231 | $49,800 |
| 4 | R1 | Trevor Lawrence | 5.419170110 | 129.973397 | 228.607672 | $49,600 |
| 5 | R2 | Trevor Lawrence | 5.415412070 | 133.325159 | 233.534591 | $50,000 |

Frozen risk appearances: out: 0, doubtful: 0, questionable_elevated: 4, questionable_full_role: 0, normal: 41. No new risk cap is enforced.

Risk player exposures: Puka Nacua: 1/5 (questionable_elevated); Jakobi Meyers: 3/5 (questionable_elevated).

Pairwise overlap (diagonal=9):

```text
9 4 4 3 4
4 9 4 7 6
4 4 9 4 3
3 7 4 9 7
4 6 3 7 9
```

Player exposures (all selected IDs appear in the roster catalog):


| Player | Appearances / 5 | Rate | Effective appearance limit |
|---|---:|---:|---:|
| Brenton Strange | 4 | 80% | 4 |
| Chase Brown | 4 | 80% | 4 |
| Javonte Williams | 4 | 80% | 4 |
| Michael Wilson | 4 | 80% | 4 |
| Parker Washington | 4 | 80% | 4 |
| Jakobi Meyers | 3 | 60% | 4 |
| Kenneth Walker III | 3 | 60% | 4 |
| Tee Higgins | 3 | 60% | 4 |
| Trevor Lawrence | 3 | 60% | 4 |
| CeeDee Lamb | 2 | 40% | 4 |
| Dak Prescott | 2 | 40% | 4 |
| Rams | 2 | 40% | 4 |
| Ryan Flournoy | 2 | 40% | 4 |
| Buccaneers | 1 | 20% | 4 |
| Cardinals | 1 | 20% | 4 |
| Dalton Schultz | 1 | 20% | 4 |
| Packers | 1 | 20% | 4 |
| Puka Nacua | 1 | 20% | 4 |

Displaced: none. Additional: none. Reference: matching production sensitivity.

## Exact roster catalog

Every identity below is a canonical `player_master_id`; matching and comparison never use display names alone. RB/WR FLEX placement may be assigned among eligible players without changing the canonical roster.

### R1

Canonical roster digest: `d9f09bcba6f1880b57648d856eb42b2e8903e54902c68b2e93133906793c8353`.

| Position | Player | Team | Canonical ID |
|---|---|---|---|
| QB | Trevor Lawrence | JAX | `af4cc0b8-e85c-4a6a-847b-d92fdd75ec80` |
| RB | Javonte Williams | DAL | `893d01f0-9572-4d0c-a680-79fdf8276409` |
| RB | Kenneth Walker III | KC | `5169c450-ece6-4729-8952-ba040d3f64f2` |
| WR | Jakobi Meyers | JAX | `e6f33396-aab8-4d70-bc70-2717b52aa86c` |
| WR | Michael Wilson | ARI | `d0ae658e-ab5e-49ad-bec3-5ae2c19867f1` |
| WR | Parker Washington | JAX | `734de5e7-0dc0-4ded-8156-c4a0e9093012` |
| WR | Tee Higgins | CIN | `1bc5ea87-e6bb-4608-a110-2b657344f1ed` |
| TE | Brenton Strange | JAX | `ddb43b49-94bf-4c9c-b875-99a2d8313797` |
| DST | Rams | LAR | `fcbaad85-7f54-4df5-8678-0131e74c265f` |

### R2

Canonical roster digest: `5b8557a04b042484c124a8a7f117c66be123301c3e33b8af7f4bb2e98771e223`.

| Position | Player | Team | Canonical ID |
|---|---|---|---|
| QB | Trevor Lawrence | JAX | `af4cc0b8-e85c-4a6a-847b-d92fdd75ec80` |
| RB | Chase Brown | CIN | `0be06444-4cd6-41a4-98a5-877a9a5c42b2` |
| RB | Javonte Williams | DAL | `893d01f0-9572-4d0c-a680-79fdf8276409` |
| WR | Michael Wilson | ARI | `d0ae658e-ab5e-49ad-bec3-5ae2c19867f1` |
| WR | Parker Washington | JAX | `734de5e7-0dc0-4ded-8156-c4a0e9093012` |
| WR | Puka Nacua | LAR | `a7d14336-632e-48c8-b0c1-45916b8476e4` |
| WR | Tee Higgins | CIN | `1bc5ea87-e6bb-4608-a110-2b657344f1ed` |
| TE | Brenton Strange | JAX | `ddb43b49-94bf-4c9c-b875-99a2d8313797` |
| DST | Rams | LAR | `fcbaad85-7f54-4df5-8678-0131e74c265f` |

### R3

Canonical roster digest: `63c0dc1f589eecc28829aece9caa3070fd876cb1947f2f9496af1633102a59e1`.

| Position | Player | Team | Canonical ID |
|---|---|---|---|
| QB | Trevor Lawrence | JAX | `af4cc0b8-e85c-4a6a-847b-d92fdd75ec80` |
| RB | Chase Brown | CIN | `0be06444-4cd6-41a4-98a5-877a9a5c42b2` |
| RB | Javonte Williams | DAL | `893d01f0-9572-4d0c-a680-79fdf8276409` |
| RB | Kenneth Walker III | KC | `5169c450-ece6-4729-8952-ba040d3f64f2` |
| WR | Jakobi Meyers | JAX | `e6f33396-aab8-4d70-bc70-2717b52aa86c` |
| WR | Michael Wilson | ARI | `d0ae658e-ab5e-49ad-bec3-5ae2c19867f1` |
| WR | Parker Washington | JAX | `734de5e7-0dc0-4ded-8156-c4a0e9093012` |
| TE | Brenton Strange | JAX | `ddb43b49-94bf-4c9c-b875-99a2d8313797` |
| DST | Buccaneers | TB | `0a6edce6-ea10-4fea-bdd0-3411df21bc7f` |

### R4

Canonical roster digest: `6b4dad210fca643622c144bfd8310ab6ac51698d134b75f50f1ee41a7a9e8901`.

| Position | Player | Team | Canonical ID |
|---|---|---|---|
| QB | Trevor Lawrence | JAX | `af4cc0b8-e85c-4a6a-847b-d92fdd75ec80` |
| RB | D'Andre Swift | CHI | `7e4bc294-c085-432c-8413-a76ab5b57911` |
| RB | Javonte Williams | DAL | `893d01f0-9572-4d0c-a680-79fdf8276409` |
| WR | Ja'Marr Chase | CIN | `f816bdba-894a-40e6-adf6-a3c2c0d659cb` |
| WR | Jakobi Meyers | JAX | `e6f33396-aab8-4d70-bc70-2717b52aa86c` |
| WR | Michael Wilson | ARI | `d0ae658e-ab5e-49ad-bec3-5ae2c19867f1` |
| WR | Parker Washington | JAX | `734de5e7-0dc0-4ded-8156-c4a0e9093012` |
| TE | Brenton Strange | JAX | `ddb43b49-94bf-4c9c-b875-99a2d8313797` |
| DST | Rams | LAR | `fcbaad85-7f54-4df5-8678-0131e74c265f` |

### R5

Canonical roster digest: `218b9ba4c887ceda60e63a9fe8d881ff8a9e80253b020448d6503ac0b7acfdb5`.

| Position | Player | Team | Canonical ID |
|---|---|---|---|
| QB | Joe Burrow | CIN | `eed8fc95-3591-4fa6-b7e6-4abb70a2885d` |
| RB | Chase Brown | CIN | `0be06444-4cd6-41a4-98a5-877a9a5c42b2` |
| RB | Kenneth Walker III | KC | `5169c450-ece6-4729-8952-ba040d3f64f2` |
| WR | Ja'Marr Chase | CIN | `f816bdba-894a-40e6-adf6-a3c2c0d659cb` |
| WR | Jakobi Meyers | JAX | `e6f33396-aab8-4d70-bc70-2717b52aa86c` |
| WR | Ryan Flournoy | DAL | `71dd15dd-c40f-41b2-9303-274042926afa` |
| WR | Tee Higgins | CIN | `1bc5ea87-e6bb-4608-a110-2b657344f1ed` |
| TE | Cade Otton | TB | `1f90d290-afb4-48ae-8052-fa99040b8ddb` |
| DST | Cardinals | ARI | `f201e474-a7d5-47b7-8c20-f72440e2847b` |

### R6

Canonical roster digest: `e40a7f4a57a9ed3bc910a93f20965a9053417d6d24a2920f02b1ec9c6e0988f3`.

| Position | Player | Team | Canonical ID |
|---|---|---|---|
| QB | Dak Prescott | DAL | `2ecc7127-a87e-40ac-befa-b975f688ac93` |
| RB | Chase Brown | CIN | `0be06444-4cd6-41a4-98a5-877a9a5c42b2` |
| RB | Kenneth Walker III | KC | `5169c450-ece6-4729-8952-ba040d3f64f2` |
| WR | CeeDee Lamb | DAL | `ea3f9527-a8b6-42c1-9607-5043fd3cf7c5` |
| WR | Ja'Marr Chase | CIN | `f816bdba-894a-40e6-adf6-a3c2c0d659cb` |
| WR | Kalif Raymond | CHI | `be517a8a-6d7c-4c5b-a236-32baed16ddb0` |
| WR | Ryan Flournoy | DAL | `71dd15dd-c40f-41b2-9303-274042926afa` |
| TE | Cade Otton | TB | `1f90d290-afb4-48ae-8052-fa99040b8ddb` |
| DST | Rams | LAR | `fcbaad85-7f54-4df5-8678-0131e74c265f` |

### R7

Canonical roster digest: `1ecaa53eafc2f768318b142b6dd63fc5251b80bd44673daf55689c34346e0868`.

| Position | Player | Team | Canonical ID |
|---|---|---|---|
| QB | Dak Prescott | DAL | `2ecc7127-a87e-40ac-befa-b975f688ac93` |
| RB | Chase Brown | CIN | `0be06444-4cd6-41a4-98a5-877a9a5c42b2` |
| RB | Javonte Williams | DAL | `893d01f0-9572-4d0c-a680-79fdf8276409` |
| WR | CeeDee Lamb | DAL | `ea3f9527-a8b6-42c1-9607-5043fd3cf7c5` |
| WR | Michael Wilson | ARI | `d0ae658e-ab5e-49ad-bec3-5ae2c19867f1` |
| WR | Parker Washington | JAX | `734de5e7-0dc0-4ded-8156-c4a0e9093012` |
| WR | Ryan Flournoy | DAL | `71dd15dd-c40f-41b2-9303-274042926afa` |
| TE | Dalton Schultz | HOU | `21e1ea77-10be-484d-85fd-90dd844747d5` |
| DST | Cardinals | ARI | `f201e474-a7d5-47b7-8c20-f72440e2847b` |

### R8

Canonical roster digest: `f8f808a614df975b39aa43be30c6c13a7e8fedbed544d08c45b3870e3378f869`.

| Position | Player | Team | Canonical ID |
|---|---|---|---|
| QB | Dak Prescott | DAL | `2ecc7127-a87e-40ac-befa-b975f688ac93` |
| RB | Chase Brown | CIN | `0be06444-4cd6-41a4-98a5-877a9a5c42b2` |
| RB | Kenneth Walker III | KC | `5169c450-ece6-4729-8952-ba040d3f64f2` |
| WR | CeeDee Lamb | DAL | `ea3f9527-a8b6-42c1-9607-5043fd3cf7c5` |
| WR | Jakobi Meyers | JAX | `e6f33396-aab8-4d70-bc70-2717b52aa86c` |
| WR | Ryan Flournoy | DAL | `71dd15dd-c40f-41b2-9303-274042926afa` |
| WR | Tee Higgins | CIN | `1bc5ea87-e6bb-4608-a110-2b657344f1ed` |
| TE | Brenton Strange | JAX | `ddb43b49-94bf-4c9c-b875-99a2d8313797` |
| DST | Packers | GB | `466b791d-7771-4fa5-9ae1-1d84cf1b40a3` |

### R9

Canonical roster digest: `f4ca6db4b11948ae75869ae2872133a1976ee476b852a1f4b38b996ac00212b1`.

| Position | Player | Team | Canonical ID |
|---|---|---|---|
| QB | Dak Prescott | DAL | `2ecc7127-a87e-40ac-befa-b975f688ac93` |
| RB | Chase Brown | CIN | `0be06444-4cd6-41a4-98a5-877a9a5c42b2` |
| RB | D'Andre Swift | CHI | `7e4bc294-c085-432c-8413-a76ab5b57911` |
| RB | Javonte Williams | DAL | `893d01f0-9572-4d0c-a680-79fdf8276409` |
| WR | CeeDee Lamb | DAL | `ea3f9527-a8b6-42c1-9607-5043fd3cf7c5` |
| WR | Michael Wilson | ARI | `d0ae658e-ab5e-49ad-bec3-5ae2c19867f1` |
| WR | Ryan Flournoy | DAL | `71dd15dd-c40f-41b2-9303-274042926afa` |
| TE | Dalton Schultz | HOU | `21e1ea77-10be-484d-85fd-90dd844747d5` |
| DST | Rams | LAR | `fcbaad85-7f54-4df5-8678-0131e74c265f` |

### R10

Canonical roster digest: `277938711f645a9b69617ba85fb376305301dc078fb12c4f1f791039c02467cb`.

| Position | Player | Team | Canonical ID |
|---|---|---|---|
| QB | Caleb Williams | CHI | `0ad9dc76-9ee5-4940-9f07-ca9839134784` |
| RB | Chase Brown | CIN | `0be06444-4cd6-41a4-98a5-877a9a5c42b2` |
| RB | Kenneth Walker III | KC | `5169c450-ece6-4729-8952-ba040d3f64f2` |
| WR | Ja'Marr Chase | CIN | `f816bdba-894a-40e6-adf6-a3c2c0d659cb` |
| WR | Kalif Raymond | CHI | `be517a8a-6d7c-4c5b-a236-32baed16ddb0` |
| WR | Luther Burden III | CHI | `4b528eb2-cbb6-426a-9220-bcf048d058a9` |
| WR | Parker Washington | JAX | `734de5e7-0dc0-4ded-8156-c4a0e9093012` |
| TE | Brenton Strange | JAX | `ddb43b49-94bf-4c9c-b875-99a2d8313797` |
| DST | Rams | LAR | `fcbaad85-7f54-4df5-8678-0131e74c265f` |

## Expanded discovery boundary

Only after parity PASS, `classic_large_gpp_v1 + expanded_discovery` tested the same ordered 154 players, exact scoring/normalizers, legality and risk rules. It made two score-optimal distinct solves for each of 23 QBs × four existing minimum-stack templates (92 requests; up to 184 lineup solves), and included the four production sensitivity portfolios. Canonical-ID deduplication produced 137 candidates. No alternate mean/P90 objective, projection model, ownership weight, eligibility threshold or new risk policy was used.

This deliberately defers player exposure to selection and uses joint finite-candidate assignment instead of sequential generation. The assignment preserves the five production template slots, 80%/four-appearance ceiling, overlap ≤7, entry count and requested game cap. These generation and selection deviations are declared on every shadow. CBC proves the finite-pool selection optimum for this pool only. It selects exactly the same roster sets and objective totals as production A and C; this does not prove exhaustive discovery over all legal portfolios.

## min_distinct_primary_games assessment

An upper concentration bound expresses the current intent directly. With five entries, cap 4 or 3 already implies at least two primary games; cap 2 implies at least three. A separate minimum could express an independent “at least K games” preference while permitting more concentration in the strongest one, so it is conceptually useful only as an advanced explicit preference. No new minimum-game control/default was added. More games alone is not evidence of a better portfolio.

## UI and replay

Operations → Classic Large GPP / Small-field GPP → **Max lineups per primary game**: **No limit / 4 / 3 / 2 / Custom**. No limit omits the parameter; null is also accepted. Preset/custom choices survive page reload as user preferences. Saved results and downloaded HTML show requested/effective/source, validation and achieved canonical counts; new Large-GPP reports also expose the saved strategy contract. Historical reports without a contract remain readable.

Invalid/nonpositive/noninteger caps are rejected before enqueueing. Classic Small-field maps the top-level option to its existing canonical-game selector constraint and preserves its existing independent risk policy. Opposite QB directions share one canonical identity in Large-GPP solving, Small-field solving and independent validation. Saved requested/effective values are tied to the run, not inferred from the current form.

Validation: 85 targeted backend tests passed, including queued-cap persistence and original unspecified-ownership behavior; 53 UI tests and TypeScript/Vite build passed. Actual browser checked default No limit, cap-3 reload retention, Custom 7, unclipped 1440px desktop/390px mobile layout, and restoration to No limit with the user’s current 5/80 inputs. Local API/worker were restarted only after confirming no queued/running jobs. No live projection or lineup rebuild was used to construct this comparison.

Commands:

```sh
.venv/bin/python scripts/audit_classic_large_gpp_parity.py
.venv/bin/python scripts/replay_classic_strategy_contract.py --contract artifacts/classic_large_gpp_parity/d0e2ff8f/A_no_cap_contract.json --output /tmp/large-gpp-replay.json
.venv/bin/python scripts/research_classic_large_gpp_discovery.py
```

Evidence: `artifacts/classic_large_gpp_parity/d0e2ff8f/`: immutable app fixture/manifest, pre-change source copies and baseline coefficient capture, parity comparison, six contracts/audits, sensitivity summary and full expanded candidate pool/solve traces. A compressed evidence archive is committed alongside its SHA-256 manifest. Expanded contracts require the explicitly labelled research command; the production replay entry point rejects an expanded plan rather than silently running sequential production.

### Does Codex parity mode exactly reproduce the app?

**YES**, at the frozen solver-frame/eligibility-ledger boundary described above: same candidate regions, five rosters, scores, constraints, exposure and overlap.

### If NO, what differs?

Not applicable. The three reconciled legacy report/serialization descriptions are listed above; no material solver mismatch remains.

### Does the 80% player exposure setting behave identically in both paths?

**YES.** Five entries × 80% = maximum four appearances here; all sensitivity and expanded portfolios honor it. Existing stricter player caps remain applicable; none exist in this fixture.

### Is canonical primary-game identity handled consistently?

**YES.** Both QB directions consume the same sorted uppercase pair across solver, audit and report.

### Current app primary-game exposure

CIN-JAX: 5.

### max-game=4 result

CIN-JAX: 4, DAL-HOU: 1. Objective cost 0.052692094 (0.1963%). Mean/P90 sums increase versus A.

### max-game=3 result

CIN-JAX: 3, DAL-HOU: 2. Objective cost 0.192396783 (0.7167%). Mean/P90 sums increase versus A; no doubtful appearances.

### max-game=2 result

CHI-NYJ: 1, CIN-JAX: 2, DAL-HOU: 2. Feasible under the unchanged frozen Large-GPP rules. Objective cost 0.435546470 (1.6225%). Includes one doubtful Caleb Williams appearance; do not mistake feasibility for cleared availability.

### Does max_lineups_per_primary_game solve the user's concentration concern without forcing weak game families?

**YES for cap 3 on this frame.** It uses the strongest next available DAL–HOU family with a measured 0.7167% objective tradeoff and higher summed mean/P90. Cap 2 is a less attractive tradeoff because it forces a third primary family and adds doubtful-QB exposure. These are heuristic portfolio scores, not win-probability estimates.

### Should min_distinct_primary_games also be exposed?

**ADVANCED_ONLY.** No additional UI control is necessary for this concentration preference; a separately requested minimum could support a different future intent.

### Does expanded discovery change the preferred result?

**NO.** The 137-candidate finite-pool shadow retains exactly the same uncapped and cap-3 roster sets and objective totals. It does not alter production defaults.
