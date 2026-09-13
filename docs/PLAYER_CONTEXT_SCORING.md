# Optimizer Player Context Scoring

## Contract

Phase 3 added `optimizer_player_context` v1, a shared soft-scoring library for
Classic and Showdown Head-to-Head and Large-GPP strategies. It runs only after
the Phase 2 eligibility gate. It cannot exclude a player, alter salary or roster
rules, or replace the selected projection's mean and quantiles.

Phase 5A advances the runtime and audit contract to v2. Scoring formulas remain
unchanged, but readiness reporting now distinguishes players with usable
context from players whose optimizer objective actually changed.

The adapter adds separate optimizer-only mean and ceiling scores. Baseline ILP
solvers consume the appropriate adjusted score, while portfolio GPP combines
the adjustment with its existing normalized mean, ceiling, leverage, and
correlation terms. Candidate-pool ranking may use the adjusted ceiling, but its
specific projection and strategy exclusions remain separately audited.

## Point-in-time inputs

Game total, team-relative spread, and implied team total come from the exact
`target.feature_player_game` row attached to the selected projection's model
and feature run. The optimizer no longer scores from the newest mutable
`player_game_feature_matrix` row. Current opportunity inputs come from that
same immutable feature JSON:

- expected snaps, routes, carries, and targets;
- carry and target share;
- red-zone and goal-line share;
- start probability, role label, and explicit uncertainty flags.

Unless all three market fields are available, every market magnitude is zero.
The explicit point-in-time-safety marker is also required; an absent or false
marker fails closed.
If an offensive player has no current opportunity field, opportunity-based
preferences are zero. Both cases remain lineup-eligible and create explicit
warnings.

## Continuous magnitudes

Every magnitude is clamped to the inclusive `0..1` range before multiplying
the rule's configured maximum adjustment. Team spread is from the player's
team perspective, so a negative value means favorite.

| Signal | Magnitude |
| --- | --- |
| High game total | `(game_total - 44) / 10` |
| High implied team total | `(team_total - 22) / 8` |
| Low implied team total | `(20 - team_total) / 8` |
| Favorite | `(-team_spread - 3) / 10` |
| Underdog | `(team_spread - 3) / 10` |
| Competitive game | `1 - abs(team_spread) / 7` |
| Competitive shootout | `high_game_total * competitive_game` |
| Extreme favorite | `(-team_spread - 9) / 7` |
| Goal-line role | `goal_line_share / 0.60` |
| Red-zone role | `red_zone_share / 0.35` |

Receiving strength is the maximum normalized target share, expected targets,
or expected routes. Rushing strength is the maximum normalized carry share or
expected carries. Stable-volume strength also requires a persisted current
context run and is reduced by explicit role uncertainty, a new assignment, or
a depth-chart conflict.

## Versioned preferences

Configured adjustments are intentionally modest because v1 is an unvalidated
policy prior, not a promoted projection model. The maximum player-level
contributions are:

- +0.45 high game total;
- +0.65 high implied team total and -0.45 low implied team total;
- +0.40 competitive high-total passing environment;
- +0.55 favorite RB and an additional +0.45 for favorite goal-line work;
- +0.45 underdog receiving role and -0.40 underdog early-down RB role;
- -0.35 extreme-favorite passing-volume risk;
- +0.35 source-backed red-zone involvement;
- +0.80 stable volume and -1.00 role uncertainty in Head-to-Head;
- +0.30 stable volume and -0.40 role uncertainty in Large GPP.

The canonical Head-to-Head profile then applies its existing `0.50` boost and
`0.65` penalty multipliers. Large-GPP uses the configured contributions. No
ownership adjustment is created when ownership evidence is absent.

## Audit and UI

`strategy_runtime.context_scoring` stores the library/profile versions,
processed and offensive-player counts, context-evaluable, market-ready,
opportunity-ready, fully contextualized, and actually adjusted counts, maximum
absolute adjustment, and trigger counts. `scored_count` remains a compatibility
alias for `context_evaluable_count`; it no longer means every processed row.
Every
player-pool row stores:

- `optimizer_context_adjustment`;
- `optimizer_context_reason_codes`;
- `context_rule_evaluation` with each magnitude and score contribution.

Every completed lineup also stores `lineup_context_summary`, including its
total adjustment and triggered-rule counts. Operations displays the adjustment
beside raw projection and P90; hovering it exposes the reason codes. The full
evaluation remains available in the downloadable player-pool JSON.

When a Large-GPP pool contains offensive players but zero cutoff-safe market
rows, status becomes `degraded` and `gpp_context_warning` explains that Vegas
and game-environment adjustments were not applied. The warning is visible in
Operations and does not block lineup generation.

## Deliberate limits

Phase 3 does not invent or infer unavailable weather, pace, offensive-line,
defensive-matchup, coaching, line-movement, or ownership signals. Those rules
remain disabled until cutoff-safe normalized inputs are part of the immutable
projection lineage and can be backtested. Material v1 weight changes require a
new library version and time-safe evaluation before promotion.
