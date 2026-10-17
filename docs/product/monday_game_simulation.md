# Monday-night football game simulation research

This offline tool simulates football events before selecting lineups. It does not call or change production optimization, alter saved projections, export entries, or write to the database. It extends the earlier [empirical scenario report](captain_scenario_research.md) with a separate model.

## Run

```sh
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m scripts.research_monday_game_simulation --output artifacts/monday_game_simulation/main
.venv/bin/python -m pytest backend/app/tests/product/test_research_game_simulation.py -q
```

Choose a fresh `--output` directory for each run. Existing reports are preserved. Defaults are 5,000 selection games and 5,000 evaluation games with independent seeds; `--draws` and `--seed` are configurable. A separate 800-game pilot repeated five times adjusts yardage efficiency toward market-implied scores, red-zone pass/rush odds toward shrunk team touchdown shares, and red-zone player weights toward shrunk scoring-role shares. It never selects lineups. Reports retain frozen input manifests, source/code hashes, canonical identities, parameters, seeds, draw hashes, rosters and an example game's event trace. The corrected Monday run is in `artifacts/monday_game_simulation/v2_corrected`; earlier reports remain immutable.

## Game construction

`research_possession_play_v2` tracks possession, field position, down, distance, clock and score. Pass/rush selection responds to pregame volume, score margin, time, third-down distance and calibrated red-zone odds inside the opposing 20. Goal-line carry weights and red-zone target weights represent player scoring roles. Events generate completions, receiving/rushing yards, sacks, interceptions, lost fumbles, touchdowns, safeties, punts, field goals and conversions. Touchdowns are not relabeled afterward. Regulation has two half clocks; ties receive simplified ten-minute overtime. Final scores label six scenarios using the existing 48-point total and 14-point blowout thresholds.

Targets and carries come from the exact Monday feature run. Canonical starter IDs determine QBs. Completion, catch, yardage, turnover and kick rates use captured 2026 weekly actuals imported before the frozen forecast cutoff, with sparse player rates shrunk toward observed position rates. Deduplication uses canonical player and exact game; native IDs resolve through persisted aliases. Naive captured PostgreSQL stat clocks are interpreted as UTC, matching the existing capture convention. Admit only earlier-week REG `nflreadpy` weekly records imported at least eight hours after scheduled kickoff and before the forecast cutoff, using pre-cutoff schedule evidence. Schedule game times use America/New_York. Missing final-score fields no longer exclude available Week 4 weekly actuals. This conservative completion window is disclosed; it is not a claim that a final-game status was recorded. Original per-player training weeks are retained, and current/future weeks cannot train rates.

Team passing-TD fractions shrink toward the observed NFL fraction using a four-touchdown prior. Player rushing/receiving TD shares shrink toward current participating opportunity shares with the same prior; nonparticipating players cannot receive allocated plays. Pilot draws adjust red-zone odds and player multipliers, with a five-TD pilot pseudocount to stabilize rare-role updates. Fitted targets and independent evaluation TD shares appear in the report. Historical shares are estimates, not guaranteed Monday expectations; fitting them does not establish matchup accuracy.

Available players excluded only by optimizer preferences still participate in football, including minimum-salary exclusions and the user's questionable exclusion. Explicitly unavailable players and backup QBs without a modeled package do not participate. Unallocated volume goes to labeled, noneligible aggregate buckets. Questionable participation is currently assumed, not probabilistically modeled. Exclusions and assumptions are saved separately.

Every completed pass credits identical QB/receiver yards, every passing TD credits a receiver, and fantasy points derive from events. Each game asserts passing/receiving yard, completion and TD conservation plus team-score reconciliation. Signed fantasy scores, yardage bonuses, distance-based kicker scoring and DST points allowed are retained. Defensive scores and safeties are excluded from opposing DST points allowed. These checks establish accounting consistency, not predictive accuracy. Scoring follows the existing DK calculator and [DraftKings guidance](https://dknetwork.draftkings.com/2025/08/27/nfl-dfs-beginners-guide-draftkings/).

## Lineup selection

Freeze the top-four eligible pregame P90 captains, including QBs. Enumerate **every** legal five-player FLEX combination before reading simulated outcomes. Apply six unique players, $50,000 cap, exact 4–2 split, 1.5× captain salary/points and saved locks, explicit FLEX-only preferences, season-leader requirement, QB correlations, DST avoidance and optional TE/QB limits. Global quality floors and portfolio exposure caps do not reject individual research lineups.

For each captain, the unrestricted mean-FLEX baseline maximizes saved FLEX mean within the same legal pool. Simulation selection chooses the fixed roster most often meeting the per-game 95th-percentile score across the **entire legal pool restricted to these four captains**. Simulated mean breaks ties; enumeration resolves remaining ties. Evaluate frozen rosters on separate games. Every captain uses identical outcomes. Evaluation games and actual scores never select a roster. Strongest scenarios are identified on selection games, then reported on evaluation games for that same roster; conditional rates from different rosters are never stitched together.

Two halves of the selection sample independently choose rosters to expose sampling sensitivity. Agreement does not prove model correctness. Monte Carlo intervals describe simulation sampling precision only. High-finish rates include ties and are not contest-field ranks, ownership-adjusted value, paid probabilities or ROI.

## Lineup structures

For each captain, group all legal rosters by FLEX positions and team relative to the captain, then by position/team/pregame role. No player identities enter the structure key. QB roles use five projected carries; receiving RBs use two targets; the lead RB has the highest team RB carries. Primary WRs are the top two team WRs with at least three targets, while secondary WRs and receiving TEs use a three-target threshold. Other roles are explicitly labeled. These thresholds are declared research classifications, not fitted optimal rules.

Rank structures by **selection-sample average high-finish rate across every legal roster in the group**, preferring groups with at least three rosters. Show held-out group averages, ranges, member counts and a representative roster selected exclusively on selection games. The best individual roster and strongest average structure can differ. All groups remain in JSON; the report displays five supported groups per captain at each detail level. Sparse groups are identified. These uniform legal-roster averages are pool-dependent comparisons, not causal position effects or ownership-weighted outcomes. With the retained DST avoidance and 4–2 split, no DST-containing lineups are legal; this run cannot evaluate RB–DST patterns.

## Limits and next validation

Weekly aggregates supply rates; play-by-play transition coefficients are not fitted. Clocks, score response, workload variation, gamma yards, punt field position and fourth-down choices are explicit, saved assumptions. Timeouts, penalties, onside kicks, in-game injuries, blocked kicks and special-teams return TDs are omitted. Overtime, kneel-out and coaching decisions are simplified. Weather and matchup-specific defensive play rates are not separately fitted.

The pilot approximately matches market score means and shrunk historical TD/role shares; it does not calibrate each player's fantasy distribution. The report displays simulated mean/P90 against unchanged saved projections. Large gaps require model investigation, not silent fantasy rescaling that breaks football accounting. Aligning touchdown shares can reduce passing TDs while increasing rushing TDs, so it need not move Allen's mean to his regression projection.

This event model has not passed chronological historical validation. Earlier bootstrap backtests do not validate it. Its Monday comparison is reproducible research, not a production recommendation. Follow-up work should fit pace/score response from pregame-available play-by-play, validate workload/yard/TD distributions and correlations, perform historical walk-forward lineup comparisons and test assumption sensitivity.
