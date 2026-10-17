# Captain scenario research

A separate [Monday football game simulation](monday_game_simulation.md) now generates possession/play outcomes and exhaustively compares legal FLEX combinations. This page describes the earlier empirical bootstrap; its backtests do not validate the new model.

This offline report compares scenario-generated FLEX combinations with unrestricted FLEX for each top-four pregame P90 captain candidate. QBs are eligible in the Monday-night research even when the saved production run restricts captain positions to WR/RB. It does not change the optimizer, active projections, user preferences, or exported entries.

## Run and replay

```sh
.venv/bin/python -m scripts.research_captain_scenarios
.venv/bin/python -m pytest backend/app/tests/product/test_captain_scenario_research.py -q
```

The default is 2,000 draws in each of three independently seeded streams and a fixed reference pool of up to 1,000 sampled legal lineups. Optional flags are `--draws`, `--seed`, and `--reference-limit`. Output is `artifacts/captain_scenario_research/report.html` and `report.json`. JSON retains source hashes, snapshot manifests, training game IDs and availability clocks, seeds, draw hashes, selected rosters, per-captain results, and skipped games. Replay reads frozen files, without a database connection. Identical inputs and parameters reproduce draws and selections with the same solver version.

The supplied inputs were captured read-only from Monday's saved run and the existing 2026 replay snapshots. Capture scripts are kept under `artifacts/captain_scenario_research`; existing immutable captures are preserved. Capturing a new slate should use a fresh artifact directory and explicit scope rather than overwriting these inputs.

## Model and scenarios

`pregame_game_block_residual_bootstrap_v1` resamples paired home/away football-score errors and player fantasy-point forecast errors from the same historical game. Player errors map by team side, natural position and pregame mean rank. Historical identities and actual-score evidence use canonical IDs plus exact week/matchup, not display names.

Simulated team scores equal the target's saved market-implied scores plus the historical game's paired score residuals, rounded and floored at zero. Player outcomes equal current projected mean plus additive historical role forecast error; signed fantasy outcomes remain signed. P90 is used for captain eligibility and the hybrid baseline, not to extrapolate a small historical P90 gap into an enormous residual.

The fixed scenario definitions are:

- High scoring: combined football score at least 48; low scoring: below 48.
- Close/non-blowout: absolute margin below 14. This includes 7–13 point margins.
- Blowout: margin at least 14, separated into home and away wins.

These six mutually exclusive states cover every draw. They are research definitions, not learned optimal thresholds. A scenario's probability is its frequency among evaluation draws. Supporting historical-block counts are shown separately: thousands of bootstrap draws do not create thousands of independent games.

This is a **correlated empirical surrogate**, not a calibrated possession simulator. It does not conserve passing/receiving yards, allocate individual touchdowns, enforce football scoring increments or distinguish every workload archetype. Missing historical role errors use zero forecast error, which is disclosed by player/block counts; unknown historical actual scores are never treated as zero. Simulation mean deviations from the unchanged source projections are retained in JSON.

## Lineup selection and leakage controls

1. Freeze the top four eligible captains by unmultiplied P90, canonical ID breaking ties. Research removes the saved WR/RB-only restriction and derived position-only FLEX labels; explicit FLEX-only player preferences remain.
2. For each captain, generate an unrestricted mean-FLEX baseline and one conditional-mean FLEX lineup per scenario with at least 30 development draws.
3. Select among these frozen rosters using a separate selection stream. Its objective is frequency of meeting the fixed comparison pool's per-draw 95th-percentile score, with mean score breaking rate ties.
4. Evaluate the frozen selections on a third stream. Final evaluation outcomes and actual scores cannot select a roster or its strongest scenario.
5. Attach historical actuals only after selection. Unknown scores make the paired comparison unscorable.

Three controls are reported: the original 1.5× captain P90 plus mean-FLEX baseline, simulation-ranked unrestricted baselines, and simulation-ranked scenario candidates. The second control distinguishes changing captain selection from changing FLEX construction.

For a given fixed lineup, overall success equals the sum of scenario probability times conditional success. Conditional rates are **not** combined across different scenario-specific rosters as though the future scenario were known. The strongest-scenario roster and best overall roster are separately identified.

## Constraints

All comparisons use six unique players, exactly one captain, five FLEX, $50,000 cap, exact 4–2 team split, and 1.5× captain salary and fantasy points. Scenario generation adds no mandatory DST/kicker/bring-back pairing.

Monday retains the saved included pool, minimum salary filtering, explicit locks/FLEX-only settings, season-leader requirement, starting-QB/pass-catcher correlations, DST avoidance and optional TE/QB limits. Its QB captain stack distinguishes high-rushing QBs using saved pregame carries/role features. Multi-entry exposure caps do not apply to independent single-lineup comparisons.

The historical replay applies the same current per-lineup preference profile where reconstructable. Historical QB starters use saved pregame mean rank; leaders use saved prior-week season averages among verified-score pools. This is a common research policy replay, not reproduction of every historical production run. Games without matching market/player features or usable leader history are skipped explicitly.

Training also requires final team scores and matching fantasy-score evidence imported before the target's forecast cutoff, with at least six earlier game blocks. Market lines come from immutable pregame feature rows; original quote observation clocks are enforced when present. Missing quote publication clocks remain a freshness limitation. Native Showdown and hypothetical Classic pricing are kept separate, with the Monday native subset shown separately.

## Interpretation

High finish means meeting or exceeding the 95th-percentile score of the declared **sampled legal reference pool**, including ties. It is not top 5% of all legal lineups, a simulated contest field, or probability of getting paid. Reference-pool size/hash are retained. Wilson intervals measure Monte Carlo precision only, not model uncertainty.

All simulation streams resample the same historical evidence. Separate seeds prevent evaluation-draw leakage but cannot establish model validity. Historical actual-result replay is the external comparison, and its surviving sample is small. Scenario-probability calibration has not been established; no automatic promotion or recommendation is authorized. A positive hypothetical result does not override a negative native result.
