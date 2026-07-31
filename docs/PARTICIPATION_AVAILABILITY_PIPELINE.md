# Player Participation and Availability Pipeline

## Outcome

The standard data pipeline now covers individual offensive and defensive participation without a
paid feed. It combines nflverse weekly rosters, PFR snap counts delivered by nflreadpy, existing
weekly box scores, schedules, and canonical player aliases.

This dataset supports two distinct facts:

1. Whether a rostered player played in a specific game.
2. How much expected offensive or defensive snap share was absent or lost in that game.

The second fact is shifted forward one game before becoming a model feature. Historical target-game
outcomes never enter that same game's feature row.

## Source coverage

| Source | Available seasons | Local rows | Use |
|---|---:|---:|---|
| nflverse weekly rosters | 2002–2025 | 906,378 | Team membership, official status, GSIS/PFR crosswalk |
| PFR snap counts through nflreadpy | 2013–2025 | 324,611 | Offense, defense, and special-teams snaps/shares |
| nflverse weekly player stats | 2000–2025 | Existing source | Box-score proof, including individual defense |
| nflverse schedules | 2000–2025 | Existing source | Game/team/opponent mapping and chronological shift |

The nflreadpy snap-count call returns an empty frame for 2012, so the supported snap range begins in
2013. The loader defaults to that verified boundary.

## Layer contract

Bronze tables retain every source snapshot and its `ingest_run_id`:

- `raw_nfl_weekly_roster`
- `raw_nfl_snap_count`

The complete source row remains in `raw_row_json`; commonly queried identity, game, team, position,
status, and snap fields are typed. Reingestion adds another traceable snapshot instead of deleting
the prior one.

Silver table `curated_player_game_participation` resolves every included row to
`player_master_id`. GSIS aliases use source `nflreadpy`; PFR aliases use source `pfr`. A record that
cannot resolve is added to `unresolved_player_queue`, never silently joined by display name or
dropped as if resolved.

Gold table `features_team_game_availability` stores one row per team-game with team and opponent
values plus source-game lineage. The four model inputs also flow into
`player_game_feature_matrix`:

- `team_offense_missing_share_lag1`
- `team_defense_missing_share_lag1`
- `opponent_offense_missing_share_lag1`
- `opponent_defense_missing_share_lag1`

## Participation classification

Classification follows positive evidence in this order:

1. Any offense, defense, or special-teams snap: `played_confirmed` / `snap_count`.
2. Any relevant offensive, kicking, special-teams, or individual-defense box-score activity:
   `played_inferred` / `box_score_activity`.
3. Official inactive/reserve/developmental/suspended roster status: `did_not_play` /
   `inactive_roster_status`.
4. Rostered with zero snaps while other players prove team-game snap coverage: `did_not_play` /
   `roster_without_snap`.
5. Otherwise: `unknown` / `no_participation_evidence`.

This prevents a missing snap file from manufacturing hundreds of false injuries.

## Feature calculation and time safety

For each player, team, and side of the ball, expected share before game `g` is the mean of up to four
earlier actual snap shares. The game impact is:

```text
missing_share(g) = max(expected_share_before_g - actual_share(g), 0)
```

A missing-player count is also recorded when expected share is at least 25% and actual share is at
most 1%. Player impacts are summed separately for team offense and team defense.

Those game-`g` impacts are written only onto the team's next scheduled game, along with the prior
`game_id` and week. Both teams in a game read their prior state before either is advanced, so the
opponent values cannot accidentally see the current game. Tests explicitly prove that a Week 2 DNP
does not alter Week 2 features and first appears for both team and opponent in Week 3.

These columns are now available to the guarded player-matchup model family and historical feature
matrix. Their presence does not promote a model: the existing time-split validation and model
promotion governance still decide whether a trained candidate can become active.

## Local audit after the initial load

| Layer/status | Rows |
|---|---:|
| Raw weekly rosters | 906,378 |
| Raw snap counts | 324,611 |
| Curated player-game participation | 769,113 |
| Gold team-game availability | 12,446 |
| `played_confirmed` | 181,144 |
| `played_inferred` | 175,917 |
| `did_not_play` | 298,987 |
| `unknown` | 113,065 |
| Open roster identities | 31 |
| Open snap-count identities | 405 |

Every snap-covered season has nonzero availability features. The early roster-only seasons remain
useful for membership and box-score participation, but correctly have zero snap-loss features.

## Operations

Load or refresh all available history:

```bash
python scripts/apply_migrations.py
python scripts/load_nflreadpy_participation.py \
  --season-start 2002 \
  --season-end 2025
```

Load one season through the API:

```text
POST /api/ingest/nflreadpy/weekly-rosters
POST /api/ingest/nflreadpy/snap-counts
```

Both accept `NflReadPySeasonRequest` with `season` and optional `weeks`. Coverage and freshness are
visible through `GET /api/coverage/season` and `GET /api/coverage/freshness`. Resolve the 436 open
identities through the existing unresolved-player workflow; a later rebuild will consume the
persisted aliases.
