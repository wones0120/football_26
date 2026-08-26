# Slate Game Weather API

Date: 2026-08-02

Contract: `slate_game_weather_v1`

Forecast contract: `weather_forecast_source_contract_v1`

Status: WTHR-005 complete

## Outcome

`GET /api/weather/slate` returns one explicit weather row for every matchup that can be identified
from the selected source, season, week, and slate. The response is keyed by canonical nflverse
`game_id` after deterministic team/opponent-to-schedule reconciliation; it never joins players or
games through player display names. Current-capture lineage is also unioned by canonical game ID so
a weather attempt cannot disappear merely because a salary slice is missing or incomplete.

When salary matchup evidence cannot resolve to exactly one schedule game, the endpoint retains an
`unresolved` or `ambiguous` row with candidate IDs and quality flags instead of silently omitting the
matchup. Missing schedules, kickoffs, venue mappings, registry records, forecasts, and completed-game
actuals are likewise response-visible.

## Request

```text
GET /api/weather/slate
  ?source_system=draftkings
  &season=2025
  &week=11
  &slate=sunday_main
  &cutoff_at=2025-11-16T13:00:00-05:00
```

Parameters:

- `source_system`: `draftkings` by default; `fanduel` is also accepted.
- `season`, `week`, and `slate`: required selected-slate identity.
- `cutoff_at`: optional timezone-aware reconstruction time. Naive timestamps fail with `422`.

Slate matching is case-insensitive. Team aliases are canonicalized for known nflverse/DraftKings
differences such as `JAC`/`JAX`, `WSH`/`WAS`, and legacy franchise abbreviations.

## Cutoff and request-kind rules

The service derives `slate_lock_at` as the earliest known kickoff in the selected slate. The
effective `cutoff_at` is the earliest of server current time, caller cutoff when supplied, and slate
lock. A future or post-lock caller timestamp therefore cannot make a later receipt eligible.
Response flags state whether the requested cutoff was clamped to current time or lock.

The response classifies the slate as:

- `current` while any selected game has not kicked off. Only `current_forecast_capture` rows actually
  received by the effective cutoff are eligible, and retrospective actuals are not returned.
- `historical` once every selected game has kicked off. The newest cutoff-safe forecast is selected
  across retained fixed-lead and receipt-timed evidence, and any available retrospective actual is
  returned in a separate `actual` object.

Historical `received_at` is artifact-retrieval lineage, not invented provider availability. The
fixed-lead eligibility predicate remains `forecast_basis_at=valid_at-24h <= cutoff`; current capture
eligibility remains actual `received_at <= cutoff`.

## Response contract

Top-level fields include the selected slice, `request_kind`, effective cutoff, slate lock, salary
row count, expected/resolved game counts, state and identity summaries, and report-level quality
flags. Each game includes:

- canonical game identity, teams, kickoff, and schedule status;
- versioned venue identity, physical venue name, timezone, country, and explicitly labeled registry
  roof default;
- weather state: `available`, `indoor`, `stale`, `missing`, or `error`;
- latest eligible forecast identity, kind, provider/model, valid/basis/receipt times, age, six
  normalized values, units, and quality flags;
- latest capture failure status/reason when applicable;
- separately labeled retrospective actual conditions with `replay_eligible=false`;
- game-level missing, mapping, freshness, and source-quality flags.

Fixed-indoor venues return `weather_state=indoor`. Retractable roof is a venue default only and is
not represented as a captured open/closed game-level roof observation. Current available receipts
become `stale` after `WEATHER_FORECAST_STALE_AFTER_MINUTES`; the historical fixed-24-hour contract is
not misclassified by that live freshness threshold. A partial provider snapshot remains visible in
the `forecast` object, reports `weather_state=missing`, and carries `forecast_partial` so consumers
cannot mistake incomplete core values for fully available weather.

## Guardrails

1. Player display names are never used for slate-game identity.
2. A forecast must match the selected game and resolved venue-registry version.
3. Current views reject historical fixed-lead rows and post-cutoff receipts.
4. Historical actuals remain a different object, retain `replay_eligible=false`, and never repair a
   missing forecast value.
5. Missing or ambiguous game identity is returned explicitly rather than dropped.
6. Request and response schemas are read-only; WTHR-005 adds no data mutation or provider traffic.

## Verification

- Focused slate API plus historical/current forecast tests: 17 passed.
- Full Python suite: 428 passed with two pre-existing `datetime.utcnow()` deprecation warnings.
- Fixtures cover historical as-of-lock selection, post-lock exclusion, separate actual labels,
  current cutoff clamping, stale current capture, fixed-indoor state, alias reconciliation, naive
  cutoff rejection, and unresolved-matchup retention.

WTHR-006 now consumes this endpoint in the War Room Game Pressure Matrix and selectable matchup
detail. Forecast and actual display rules are recorded in `docs/WAR_ROOM_WEATHER.md`. WTHR-007 still
requires one real past-slate and one prospectively captured current-slate data/API/UI acceptance run.
