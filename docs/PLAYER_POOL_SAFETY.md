# Optimizer Player-Pool Safety

## Contract

Phase 2 adds a common safety gate before every Classic and Showdown solver.
`backend/app/product_services/player_pool_safety.py` evaluates each salary-pool
row with the canonical strategy profile and versioned
`optimizer_player_pool_safety` rule library. A hard-excluded row never reaches
lineup construction. Eligible rows retain warnings and their complete rule
evaluation for inspection.

The gate uses canonical `player_master_id`/`player_id` values only. Display
names are retained for explanation but are never identity keys.

## Hard exclusions

- unresolved or duplicate canonical identity;
- confirmed unavailable salary or cutoff-safe injury status;
- a non-`ACT` current roster record when weekly roster evidence exists;
- a team outside an explicitly supplied `slate_teams` set, or a contradictory
  team/opponent pair;
- zero cutoff-safe availability;
- backup QB when starter evidence exists and no explicit package/specialty
  workload is present;
- pregame context observed after the projection cutoff;
- an explicit canonical-ID user exclusion.

Target-pool SQL still selects injury and roster evidence point-in-time, but the
final status/roster decision is made by this gate so the rejected player and
reason remain in the run audit.

## Current-week context

Migration `0027_pregame_context_opportunity.sql` extends the append-only
pregame context contract with optional expected snaps, routes, carries,
targets, red-zone share, and goal-line share. The API validates non-negative
counts and probability bounds. These fields, injury status, role labels,
source/run IDs, and observed timestamps flow through immutable projection
feature lineage into optimizer audits.

Missing or stale context remains eligible but produces a warning, as do
uncertain/new roles, depth-chart conflicts, missing team/opponent fields, and
injury designations not tied to a context run. The default freshness window is
24 hours. Role uncertainty, newly assigned roles, and depth-chart conflicts
can be supplied in the context row's `evidence` object.

Expected opportunity fields are recorded as source-backed current context.
Existing carry/target-share logic continues to redistribute team opportunity
before projection scoring. The new expected-count fields do not silently
replace model features or point projections.

## User controls

Optimizer `params` accepts:

- `exclude_player_ids`: canonical IDs removed by the safety library;
- `exclude_players`: legacy normalized display-name exclusions, retained for
  compatibility and audited as user exclusions;
- `lock_player_ids` or `locked_player_ids`: canonical IDs required in every
  generated lineup.

A player cannot be both locked and excluded. Locks cannot override identity,
eligibility, slate, or data-cutoff failures, but they do override later
strategy-only candidate trimming. Classic supports at most nine locks and
Showdown at most six. For portfolio GPP runs, locks become exact 100% minimum
and maximum player exposure controls.

## Audit output

`strategy_runtime.player_pool` contains every loaded canonical candidate with:

- inclusion status and plain reason codes;
- structured exclusion details categorized as `eligibility`, `projection`,
  `strategy`, or `user`;
- warnings and the full versioned rule evaluation;
- current context run/source/observed time, role, injury, and availability;
- aggregate eligible, included, excluded, and warning counts.

The Operations player-pool summary shows the warning count and warning reason
codes. Its optimizer form accepts comma-separated canonical lock and exclusion
IDs in addition to the legacy display-name exclusion field. The full JSON
remains downloadable for detailed inspection.

## Verification

Focused tests cover identity/status/roster/slate/availability/cutoff gates,
backup-QB specialty exceptions, freshness and role warnings, category
classification, current opportunity lineage, canonical locks in Classic and
Showdown, and 100% GPP minimum exposure behavior.
