# Showdown kicker role audit

The defect was missing current kicking-role eligibility. Smyth’s projection was his own 2025 history, not Carlson’s copied projection. The slate-agnostic gate now excludes him, identifies Carlson/Folk, and produces five corrected production entries without changing portfolio balancing.

Saved optimizer: `2823f965-f410-48aa-8d24-13c114c99002`. Projection: `7c5084da-b321-4789-80dd-4558d488963c`. Reference: `c9a9a25c-e31c-4cca-b662-9ee3cd71b1fb`.

## Root cause and available evidence

- There was no starting-kicker identity table/filter. The starter workflow and ranked nflverse capture were QB-only; the Showdown opportunity gate applies to RB/WR/TE. Multiple same-team kickers could remain eligible.
- Week 4 raw weekly roster records, joined through canonical nflreadpy GSIS aliases, list Smyth `DEV`, Carlson `ACT`, Folk `ACT`. Their unranked `depth_chart_position=K` does not specify K1/K2. The optimizer’s older roster safety check reads the curated participation table, whose current-week team coverage was absent.
- Current same-season prior FG/PAT usage exists: Carlson attempts 5/4/4 in Weeks 1/2/3; Folk 5/2/5. Smyth has no 2026 kicking usage. Older 2025 ability was incorrectly carried forward into a normal core exposure classification.
- Smyth has six historical games: roll-three 12.0, roll-eight 9.3333; 60% × 12 + 40% × 9.3333 = 10.9333. Residual calibration added 5.64396 for P90 16.57729. Generic availability defaulted to 1; kicker starting probability/role was not gated.
- A separate old fallback could also lend a peer kicker’s history to a no-history backup. New projections permit peer anchoring only for an expected primary; unsupported roles have zero mean and all quantiles. Shared-duty kickers require their own history.
- Official Saints depth chart lists Carlson; its August 31 preseason report describes him ahead of Smyth. Public checks corroborate the local roster/usage evidence, but no current web chart was injected into historical replays. Sources: [Saints depth chart](https://www.neworleanssaints.com/team/depth-chart), [Saints preseason kicker report](https://www.neworleanssaints.com/news/kicker-daniel-carlson-made-most-of-limited-preseason-time-with-new-orleans-saints).

## Gate contract

Use sourced pregame primary duties, ranked K1, unique current active-roster kicker, then unique recent prior FG/PAT usage. Resolve by canonical IDs and normalized team across the entire evidence pool, including players absent from salaries. Never rank roles by salary or fantasy projection. Backups/unresolved identities are excluded with retained assessments and explicit reasons; missing/conflicting identity produces a warning. Explicit sourced replacement/shared duties are the exception. Receipts and observations must precede the selected projection cutoff; usage must precede the target week in the same season. No schema migration or dependency was needed.

## Historical/current scope

Before correction, 17 team/slate salary pools in 2024–2026 contained multiple kickers. These are exposure points, not proof that every backup was selected. All 10 persisted duplicate-kicker projection runs were 2026 Week 4 Monday ATL–NO. All 28 saved Smyth lineup appearances were on that slate. No saved lineup selected two kickers from the same team. Thus the current failure is confirmed; the inspected saved projections/lineups do not demonstrate another historical occurrence. Existing generic roster/availability exclusions sometimes protected historical pools; missing coverage left the structural gap. Full inventory: `artifacts/kicker_role_audit/database_evidence.json` and `historical_audit.json`.

## ATL–NO comparison

The original saved reference used an earlier projection run; several small non-kicker differences exist versus today’s local rebuild. Causal comparison uses the prior controlled experiment’s immutable freeze: every non-kicker projection and both primary-kicker projections remain identical. The fresh production result exactly matches corrected frozen Policy A. Salary identities/counts remain 55 raw rows; prepared eligibility falls from 20 to 19, with Smyth the only role removal.

| Metric | Original saved reference | Corrected production |
| --- | --- | --- |
| Entries | 5.000 | 5.000 |
| Average mean | 90.251 | 86.857 |
| Average P90 | 151.574 | 147.972 |
| Portfolio selector | 843.576 | 835.459 |
| Average shared identities | 3.700 | 3.800 |
| Bijan Robinson exposure | 1/5 | 3/5 |
| Tyler Shough exposure | 5/5 | 5/5 |
| Michael Penix Jr. exposure | 2/5 | 0/5 |
| Chris Olave exposure | 4/5 | 4/5 |
| Charlie Smyth exposure | 4/5 | 0/5 |
| Daniel Carlson exposure | 0/5 | 1/5 |
| Nick Folk exposure | 0/5 | 3/5 |
| Team splits | {'ATL 1/NO 5': 2, 'ATL 2/NO 4': 3} | {'ATL 2/NO 4': 3, 'ATL 1/NO 5': 1, 'ATL 3/NO 3': 1} |
| Captain distribution | {'Chris Olave': 3, 'Tyler Shough': 2} | {'Chris Olave': 3, 'Devaughn Vele': 1, 'Tyler Shough': 1} |

**NO 4–2 remains the majority: 3/5 before and 3/5 after.** One former NO 5–1 entry becomes 3–3. This does not establish a universal team-split preference across games.

| Kicker | Before mean / P90 | Rebuilt mean / P90 | Eligibility |
| --- | --- | --- | --- |
| Charlie Smyth | 10.933 / 16.577 | 0 / 0 | Excluded: backup without expected duties |
| Daniel Carlson | 6.750 / 12.394 | 6.750 / 12.394 | Primary NO |
| Nick Folk | 7.000 / 12.644 | 7.000 / 12.644 | Primary ATL |

### Original five reference lineups

| Entry | Captain | FLEX |
| --- | --- | --- |
| 1 | Chris Olave | Charlie Smyth, Tyler Shough, Juwan Johnson, Jahan Dotson, Devaughn Vele |
| 2 | Chris Olave | Charlie Smyth, Tyler Shough, Michael Penix Jr., Juwan Johnson, Jahan Dotson |
| 3 | Chris Olave | Charlie Smyth, Tyler Shough, Juwan Johnson, Brian Robinson Jr., Devaughn Vele |
| 4 | Tyler Shough | Juwan Johnson, Brian Robinson Jr., Chris Olave, Kyle Pitts Sr., Devaughn Vele |
| 5 | Tyler Shough | Charlie Smyth, Bijan Robinson, Bryce Lance, Michael Penix Jr., Devaughn Vele |

### Five corrected lineups

| Entry | Captain | FLEX | Salary | Mean | P90 | Selector | Split |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Chris Olave | Nick Folk, Tyler Shough, Juwan Johnson, Jahan Dotson, Devaughn Vele | 49400 | 86.333 | 149.747 | 172.504 | ATL 2/NO 4 |
| 2 | Chris Olave | Bijan Robinson, Tyler Shough, Bryce Lance, Juwan Johnson, Jahan Dotson | 49800 | 87.080 | 148.937 | 171.958 | ATL 2/NO 4 |
| 3 | Chris Olave | Bijan Robinson, Tyler Shough, Bryce Lance, Devaughn Vele, Austin Hooper | 50000 | 86.142 | 148.146 | 171.166 | ATL 2/NO 4 |
| 4 | Devaughn Vele | Nick Folk, Tyler Shough, Juwan Johnson, Chris Olave, Daniel Carlson | 49700 | 87.488 | 146.036 | 164.048 | ATL 1/NO 5 |
| 5 | Tyler Shough | Bijan Robinson, Nick Folk, Juwan Johnson, Jahan Dotson, Devaughn Vele | 49800 | 87.242 | 146.994 | 155.783 | ATL 3/NO 3 |

### Prepared player pool

| Player | Team | Position | Mean | P90 |
| --- | --- | --- | --- | --- |
| Falcons | ATL | DST | 5.031 | 11.795 |
| Nick Folk | ATL | K | 7.000 | 12.644 |
| Michael Penix Jr. | ATL | QB | 12.656 | 23.468 |
| Bijan Robinson | ATL | RB | 18.006 | 28.041 |
| Brian Robinson Jr. | ATL | RB | 3.912 | 11.822 |
| Kyle Pitts Sr. | ATL | TE | 8.759 | 13.402 |
| Austin Hooper | ATL | TE | 2.753 | 8.620 |
| Drake London | ATL | WR | 12.256 | 24.963 |
| Jahan Dotson | ATL | WR | 2.997 | 12.719 |
| Zachariah Branch | ATL | WR | 1.106 | 6.532 |
| Saints | NO | DST | 5.072 | 11.836 |
| Daniel Carlson | NO | K | 6.750 | 12.394 |
| Tyler Shough | NO | QB | 21.296 | 32.022 |
| Alvin Kamara | NO | RB | 7.438 | 15.349 |
| Kendre Miller | NO | RB | 5.541 | 13.452 |
| Juwan Johnson | NO | TE | 13.995 | 21.125 |
| Chris Olave | NO | WR | 18.496 | 31.203 |
| Devaughn Vele | NO | WR | 13.301 | 24.433 |
| Bryce Lance | NO | WR | 3.042 | 8.226 |

## Corrected controlled QB-policy experiment

All six policies use the same 19-player prepared football frame, seed 20261005, unchanged 95% joint mean/P90 quality screen, requested-count core/QB/punt/Captain caps, candidate-generation breadth and disabled scenario diversity. A–D change only QB eligibility; E/F retain the previously authorized team-cap challengers. No new balancing rule or automatic relaxation was applied.

| Policy | QB Captain | Max QBs | Max/team | Entries | Mean | P90 | Overlap | Selector | Penix appearances |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | Yes | 2 | 5 | 5/5 | 86.857 | 147.972 | 3.800 | 835.459 | 0 |
| B | Yes | 1 | 5 | 5/5 | 86.857 | 147.972 | 3.800 | 835.459 | 0 |
| C | No | 2 | 5 | 4/5 | 86.423 | 148.734 | 4.500 | 680.946 | 0 |
| D | No | 1 | 5 | 4/5 | 86.423 | 148.734 | 4.500 | 680.946 | 0 |
| E | Yes | 2 | 4 | 5/5 | 86.641 | 148.009 | 3.600 | 836.840 | 0 |
| F | Yes | 2 | 3 | 5/5 | 85.141 | 148.538 | 3.700 | 810.481 | 4 |

A/B now select identical portfolios; C/D also select identical portfolios. All six select no two-QB entry. The prior two-QB/Penix tradeoff and Smyth-dependent bottleneck/relaxation conclusions are superseded. C/D still cannot reach five under the exact unchanged constraints: **Olave alone is mandatory in every quality-eligible roster, and his four-appearance cap prevents five entries.** Increasing only his cap to five is mathematically sufficient; the diagnostic quality-only five-entry threshold is now 93.934648%, not the old 94.443492%. These are diagnostics, not applied changes. Allowing Shough Captain also creates a five-entry witness; allowing only Penix Captain does not.

Exhaustive enumeration examined 149,791 salary/team-legal signatures and certified 4,453 retained signatures against the frozen production MILP. All policy raw maxima match their production candidate benchmark. Selected-versus-full-universe selector gaps by policy: {'A': 1.564883, 'B': 1.564883, 'C': 1.564883, 'D': 1.564883, 'E': 0.0, 'F': 0.0}. These are candidate discovery gaps; no discovery or balancing changes were made. The archived PIT–CLE historical replay is unchanged; no duplicate projected kicker pool was found there, and this audit makes no new standings-success inference.

## Validation and replay limits

- Latest broader validation: 206 passed, 1 unrelated QB-starter expectation failed. `test_confirmed_starters_allow_partial_canonical_team_coverage` expects a missing team’s QB to fall back to salary; separate working-tree changes now forbid that fallback. This task did not change that QB policy or its test. Kicker tests (including mixed projected/unprojected salary rows, explicit backup duties, cutoff/known-kickoff rejection and no-history projection protection), calibration, pool safety, Showdown policies and production/research parity pass. `git diff --check` and Python compilation pass.
- The original projection cutoff cannot be reconstructed from today’s replaced curated salary table; its raw source/frozen research frame remains preserved. Fresh projections use current local data. The frozen correction only changes kicking eligibility and asserts identical prepared inputs across all policies; fresh production asserts the same selected signatures and unchanged non-kicker projections versus that freeze.
- Two intermediate local optimizer runs (`8143caff-ecfc-42bd-80ef-0b20b5eb0335`, `06d6f155-7d67-4f2e-886c-dcc466dfd284`) excluded all kickers because the new loader initially required every salary row to have a projection cutoff. They are superseded by the final run above. The fix uses available cutoffs, with a regression test; no records were deleted.
- Existing stale market/final-clearance/native-draft-group warnings remain. The rebuild is a development preview and was not submitted. Original projections, lineups, raw snapshots and prior research were retained.

Machine-readable comparisons, full player pool, all selected lineups, exact feasibility witnesses and checksum envelopes: `artifacts/kicker_role_audit/comparison_verified.json` and `artifacts/kicker_role_audit/controlled/`. The earlier `comparison.json` omitted persisted solver metadata and reported zero for the fresh selector; the verified comparison restores it from the saved selection report. Reproduction: `scripts/audit_kicker_roles.py`, existing `run_showdown_qb_policy_experiment.py`, `enumerate_showdown_policy_universe.py`, `audit_showdown_qb_policy_feasibility.py`, `rebuild_kicker_role_slate.py`, and `report_kicker_role_audit.py`.
