# Format-Specific Lineup Rules

## Direct lineup downloads

`GET /api/optimizer/results/{job_id}/draftkings/download` exports all lineups from a
completed saved run without contest-entry assignments. Classic columns are
`QB,RB,RB,WR,WR,WR,TE,FLEX,DST`; Showdown columns are
`CPT,FLEX,FLEX,FLEX,FLEX,FLEX`. Captain cells use saved `dk_captain_id` values.
Downloads validate IDs, roster composition, salaries and duplicates before
returning a CSV, or a ZIP of CSVs for runs exceeding 500 lineups. The result-card
button is **Download all N lineups for DraftKings**. Matching entry templates
remain necessary only for the separate export that updates existing entries.

## Contract

Showdown cash player scoring uses `showdown_cash_distribution_v1`: the declared
profile's mean, median, P10 and P90 weights plus context. The Captain solver
applies 1.5 to that score. Missing quantiles fall back to mean; existing lineup
correlation terms remain separate. Saved runs retain component explanations and
weights. Showdown GPP continues using its context-adjusted ceiling objective.

Phase 5 advanced the active `optimizer_lineup_correlation` library to v2. Phase
5A advances it to v3 by context-weighting positive stack terms and removing
structural correlation floors. The active v4 adds Classic H2H variance controls
without changing lineup feasibility. It retains the configured maximum weights
and higher-order construction terms for Classic and Showdown. The same term
builder and exact binary linearization run in the baseline optimizer and
advanced Classic GPP engine.

These are objective preferences, not eligibility gates. They do not alter
DraftKings roster or salary rules, user locks, exposure controls, or explicit
strategy-owned stack requirements. A legal lineup that triggers a penalty can
still win when its projections justify it.

## Classic rules

Classic construction rules include:

- a GPP-only naked-QB penalty of up to `-1.10`, reduced continuously by the
  quarterback's source-backed rushing-role strength and eliminated at maximum
  rushing strength;
- a GPP-only QB double-stack bonus of up to `+0.65`, multiplied by a
  cutoff-safe game-total, implied-team-total, competitiveness, opponent-push,
  and blowout-risk score; missing context contributes zero;
- a Classic H2H-only `-0.85` QB variance penalty before profile scaling when a
  quarterback is paired with at least two same-team WR/TE players;
- a Classic H2H-only `-0.55` concentration penalty before profile scaling when
  three or more QB/RB/WR/TE players come from one team;
- a penalty of `-0.75` before profile scaling when three or more RB/WR/TE
  players from one team appear without that team's quarterback;
- a GPP-only full-game-stack bonus of up to `+0.55` when at least four
  offensive players span both teams in a cutoff-safe competitive shootout.
- a contradiction penalty of up to `-0.90` when a meaningful favorite's
  early-down RB appears with the opposing DST and multiple pass catchers from
  that underdog.

The existing pair rules still score QB + WR/TE, receiving RB stacks,
bring-backs, RB/DST combinations, mini-correlations, and DST conflicts. In H2H,
the higher-order variance terms reduce the appeal of concentrated offense when
individual objective scores are similar. They remain soft, so a sufficient
projection advantage or a user lock can still select the same-team build. DST
is excluded from the offensive concentration count, preserving the RB/DST
benefit.

## Showdown rules

Showdown v2 adds:

- up to `+0.90` for a QB Captain with at least two same-team WR/TE partners,
  multiplied by the same cutoff-safe stack-environment score;
- `-0.80` for a WR/TE Captain without his quarterback;
- up to `+0.60` in large-field GPP for a 5-1 build led by a meaningful favorite;
- up to `-1.10` for a 5-1 build led by a meaningful underdog;
- up to `+0.35` for a competitive 3-3 build and `+0.20` for a competitive 4-2;
- up to `+0.65` for a favorite RB Captain with source-backed rushing volume;
- a sub-$1,000 no-role punt penalty of `-0.90` in H2H and `-0.35` in GPP before
  canonical profile scaling.

A cheap RB/WR/TE avoids the punt penalty when current evidence supplies a
positive snaps, routes, carries, targets, usage-share, red-zone, goal-line, or
specialty-role path. Missing evidence is never fabricated. Pick'em or missing
spread data does not create a favorite/underdog 5-1 contribution.

Operations also supports the Showdown-only
`FLEX-only players (comma-separated names)` control. It resolves each supplied
name to an unambiguous canonical ID inside the selected slate, constrains that
player's Captain variable to zero,
and leaves the FLEX variable eligible. FLEX-only is independent of a player
lock: using both means the player is required in FLEX, while FLEX-only by itself
does not require selection. The canonical IDs and supplied names are retained
in `strategy_runtime.player_controls`, and completed-lineup validation rejects
any FLEX-only player returned at CPT.

## Exact activation and audit

Higher-order terms use binary indicators for all required conditions:

- selected anchor or Captain;
- minimum and maximum selected counts;
- required team representation;
- absence of a specific partner such as the quarterback.

Both positive and negative indicators are constrained in both directions, so
the solver cannot hide a penalty by setting an optional helper variable to
zero. Completed lineups are recomputed from their selected players and persist
the same contribution in `lineup_correlation_summary`. Each format-specific
entry includes `construction_kind`, involved players, source evidence, raw
rule contribution, and effective objective contribution.

Operations already renders these entries under `Correlation rules`, so older
runs remain compatible and v4 runs require no new UI control. Runtime metadata
stores the library and profile versions used for the solve.

## Current limits

The v4 weights are an `initial_policy_unvalidated` prior. Team splits and
construction labels are explainable heuristics, not estimated game-script
probabilities. Phase 6A now computes experimental joint lineup median/P75/P90 and generic score-threshold probabilities through `joint_game_factor_research_v1`; see `docs/PHASE_6A_JOINT_SIMULATION.md`. Learned joint outcomes and tournament thresholds still require point-in-time-safe simulation/field evidence before any production promotion claim.

Until joint lineup simulation is implemented, completed lineups expose
`Individual Ceiling Sum`, the sum of selected player P90 values. That metric is
explicitly marked `is_joint_quantile: false` and must not be presented as a
lineup P90.
