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
Before the UI starts an optimizer run, it reconciles salary identities and
quarantines unresolved rows. A matching team alone cannot resolve a player
whose known canonical position conflicts with the salary position.

## Hard exclusions

- unresolved or duplicate canonical identity;
- confirmed unavailable salary or cutoff-safe injury status;
- a non-`ACT` current roster record when weekly roster evidence exists for that
  player's canonical team;
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

Roster coverage is never inferred globally from another team. Team joins use the
shared NFL alias contract (for example, nflverse `LA` and DraftKings `LAR`). A
missing row for an uncovered team is retained with missing-evidence diagnostics;
it is not converted into an inactive player. Readiness, pregame context, and the
optimizer use this same rule.

Before eligibility filtering, the optimizer also checks that an evidence-backed
starting quarterback does not carry a non-`ACT` roster state. A disagreement now
fails as a `Slate player evidence conflict` naming the player, team, and roster
state, rather than removing the quarterback and later claiming the slate has none.
The starter-evidence loader itself excludes salary QBs marked `OUT` or otherwise
unavailable. Sourced provisional selections are retained across projection-worker
runs; automatic depth-chart QB1 selections are re-evaluated.
Automatic next-active-QB selections after a salary OUT designation are provisional
and re-evaluated too. They require agreement between the unique next depth rank
and unique top eligible salary; a disagreement blocks the run for review.
On September 29, 2026, the Week 4 Sunday Main salary slice marked Baker Mayfield
OUT while the preserved nflverse chart still ranked him TB QB1. Jalon Daniels
was the unique next-ranked and highest-paid eligible TB QB. The resulting
provisional selection is saved under depth snapshot
`13e6a2d5-2edb-5c95-9a57-d2b22bc0ddd2`; projection run
`58d57106-d0ec-4d55-88a6-df0e8e29a316` completed with 527 rows at the
September 29 19:59:22 UTC cutoff. The first standard worker retries hit an
iCloud file-provider read error; this completed run used the already-verified
starter evidence at an explicit point-in-time cutoff.
After adding the bounded file-provider retry, a read-only launchd-process
rehearsal resolved all 24 Sunday teams from the normal current-slate path;
starter persistence was disabled for that rehearsal. The depth snapshot count
remained one and the completed projection count remained one.

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

An unavailable player's pre-injury carry and target shares are preserved until
the allocator measures removed work. A context row may set
`evidence.carry_redistribution_fraction` or
`evidence.target_redistribution_fraction` between 0 and 1. The remainder stays
unallocated in the run audit. An absent fraction retains the existing full
redistribution behavior. Route, air-yard, and red-zone beneficiary estimates
remain unavailable unless independently supplied; target redistribution alone
does not establish them.

## User controls

Optimizer `params` accepts:

- `exclude_player_ids`: canonical IDs removed by the safety library;
- `exclude_questionable`: optional boolean (default `false`), exposed as
  **Exclude questionable (Q) players** directly below the Portfolio optimizer
  heading in Operations. Applies to
  every Classic/Showdown strategy and weekly run. Removes a player when the
  selected salary status or effective injury designation is `Q`/`QUESTIONABLE`
  (case-insensitive). Effective injury status uses pregame context first, then
  the injury snapshot. Missing designations and doubtful status are unaffected.
  This API parameter is a user eligibility preference: raw projections, P90, role and model
  assessment remain in the audit with `user_excluded_questionable` and a
  categorized user reason. A lock cannot override this exclusion;
- `exclude_players`: legacy normalized display-name exclusions, retained for
  compatibility and audited as user exclusions;
- `lock_player_ids` or `locked_player_ids`: canonical IDs required in every
  generated lineup.
- `locked_captain_player_id`: canonical ID for a forced-Captain Showdown
  diagnostic run, including cash baseline and single-entry selection.

A player cannot be both locked and excluded. Locks cannot override identity,
eligibility, slate, or data-cutoff failures, but they do override later
strategy-only candidate trimming. Classic supports at most nine locks and
Showdown at most six. For portfolio GPP runs, locks become exact 100% minimum
and maximum player exposure controls.

Operations **Run Optimizer** refreshes features and builds a new projection run
before lineup construction. Its explicit player-name/ID exclusions and
**Exclude and assume out** control generate `availability_overrides=assume_out`;
the questionable checkbox also sends projection `assume_questionable_out=true`.
This applies the existing generic opportunity allocator before scoring. Assumed-out
players have zero participation and projected points, while audit rows and baseline
assessments remain available. Official source statuses and historical training labels
are not rewritten. Exposure, overlap, FLEX-only/Captain restrictions and opponent-team
exclusions do not change availability. Weekly requests use `refresh_projections=true`
and forward the same scenario; retries reuse their already-persisted stage artifacts.

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
