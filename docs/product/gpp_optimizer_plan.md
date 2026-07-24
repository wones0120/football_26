# GPP Optimizer Roadmap

> Status: area-specific design reference. Live implementation status and priority are tracked in `docs/TODO.md`. Checked items here do not imply the service is wired into the live optimizer path.

This document tracks the implementation steps for a GPP-focused lineup optimizer and feedback loop. It maps directly to the goals provided.

## Data + Inputs
- [x] **Goal 1**: Load and validate a clean player pool per slate (salaries + projections + metadata), normalize fields, and expose a typed in-memory structure. Derive missing opponent/team when possible. Validation: salary, projection, position, team, opponent, game ids.
- [x] **Goal 2**: Compute derived metrics (value per $1k, ceiling per $1k, leverage vs ownership) and configurable tags (`chalk`, `leverage`, `punt`) driven by thresholds.

## Slate Understanding
- [x] **Goal 3**: Analyze slate (game count, chalk concentration, feature games by total).
- [x] **Goal 4**: Build `SlateConfig` from analysis: stacking defaults, ownership caps, tag thresholds, and objective weights (projection/correlation/leverage).

## Lineup Structure + Stacking Rules
- [x] **Goal 5**: Configurable validity rules (roster, salary, teams).
- [x] **Goal 6**: Config-driven stacking (QB + pass catchers, bring-backs, team limits).

## GPP Objective + Constraints
- [x] **Goal 7**: Composite objective combining projection, correlation (stacks), and leverage with tunable weights.
- [x] **Goal 8**: Constraints on tag mix per lineup (max chalk, min leverage, punt limits) sourced from config.

## Portfolio Generation + Evaluation
- [x] **Goal 9**: Generate N lineups with uniqueness control and exposure caps.
- [x] **Goal 10**: Portfolio stats (player exposure, stack distribution, ownership profile).
- [x] **Goal 11**: Compare portfolio vs targets (exposure/ownership ranges) and flag violations.

## Feedback Loop
- [x] **Goal 12**: Iterative feedback loop: adjust config (exposures/ownership caps) when targets missed; regenerate until convergence/max iterations with logged adjustments.

## Agent Hooks
- [x] **Goal 13**: Clean interfaces for agents: slate summary, portfolio summary, config mutation + regenerate entry points.

## Operational / UX
- [x] **Goal 14**: Single entry to load slate, build config, generate portfolio, and run feedback loop.
- [x] **Goal 15**: Export CSV lineups and text summary.

## Notes
- All tunables live in `SlateConfig` (no magic numbers in solver).
- ILP solver uses PuLP CBC and runs fully in-memory.
- Existing API routes remain unchanged; a new service module can be wired later as needed.
