# DATA-002 Source Availability Audit

Date: 2026-08-01

## Outcome

DATA-002 remains incomplete and explicitly blocked. The repository and development database
do not contain an approved historical Vegas, props, depth-chart, injury, or role feed that
preserves when each value was observable before lock. No timestamps were inferred or backfilled.

Historical weather is now split correctly. `historical_game_weather_actual_v1` standardizes the
retrospective temperature and wind already present in nflverse schedule results, but every row is
structurally replay-ineligible. `nfl_venue_registry_v1` resolves every 2024–2025 game, and
`weather_forecast_source_contract_v1` now retains a separate fixed-24-hour Open-Meteo Previous Runs
cohort: 570 fully available forecasts for all 570 expected 2024–2025 games, with verified raw
artifacts and manifests. The historical API does not expose provider publication time, so the
implementation preserves that fact as null rather than treating the derived lead basis as observed
availability.

WTHR-005 now exposes those contracts through `slate_game_weather_v1`. The endpoint fails closed at
server time and slate lock, selects only receipt-eligible rows for current slates, reconstructs the
newest eligible pre-lock evidence for historical slates, and returns retrospective actuals only as
a separately labeled replay-ineligible object. Missing or ambiguous slate-game identity remains
visible instead of being silently dropped. This closes the weather API layer but does not supply the
real prospective 2026 evidence or non-weather sources required to unblock DATA-002.

The bounded safe change is `point_in_time_cutoff_v1`: projection-linked consumers now ignore an
injury snapshot unless both its `as_of` and the exact projection run's `data_cutoff_at` exist and the
snapshot was observed at or before that cutoff.

The prospective tooling is now ready through `prospective_source_snapshot_v1`. Migration `0019`
stores append-only source manifests and ingest links, and `scripts/capture_prospective_sources.py`
captures DraftKings salaries plus nflreadpy schedules, rosters, injuries, and snap counts using
server receipt time. Real 2026 observations have not yet been collected, so this does not change the
historical-source decision or unblock MODEL-001. See `docs/PROSPECTIVE_SOURCE_CAPTURE.md`.

## Local Evidence

| Dataset | Rows | Local load time | Historical observation time | Decision |
| --- | ---: | --- | --- | --- |
| `raw_injury_row` / `curated_injury` | 10,268 across 28 ingest runs | 2026-02-25 18:56:29–18:56:38 | None; all rows are FanDuel slate exports with injury indicators | Retrospective only; not replay eligible |
| `target.snapshot_injury_status` | 8,086 | Inherits the same 2026-02-25 adapter time | No separate source observation timestamp | Fail closed unless a future row has a proven cutoff-compatible `as_of` |
| Week 11 target injuries | 493 | 2026-02-25 18:56:33 | After the 2025 games | Excluded from the Week 11 baseline projection, whose cutoff is null |
| `raw_nfl_schedule` | 7,017, with total and spread values on every row | 2026-02-25 13:21:41–13:23:28 | None | Treat as historical/closing context, not cutoff-safe betting snapshots |
| `curated_game_weather` | 7,017 games; 5,009 complete temperature/wind rows; 1,752 indoor-not-applicable | Rebuilt 2026-08-01 from versioned schedules | None; values describe game-result context | Retrospective analysis only; database requires null `observed_at` and false `replay_eligible` |
| `weather_forecast_snapshot` | 570 fully available 2024–2025 game forecasts | Captured 2026-08-01 with raw response and manifest | Provider-defined exact 24-hour lead; provider issued/available times remain null | Eligible only through `provider_fixed_lead`; not relabeled as observed time |
| Props and depth-chart snapshot tables | 0 local tables | N/A | N/A | Source required |
| Role changes | Manual scenario support only | Explicit scenario time | Not an observed historical feed | Keep as scenario evidence, not historical fact |

The read-only Week 11 SUNDAY_MAIN smoke loaded 382 eligible salary/projection rows from
`baseline_rolling_dk_v0:projection:2025:11`. Its `data_cutoff_at` is null, so none of the 493
retrospective injury rows were eligible to remove a player or trigger an injury rule.

## Upstream Audit

The official [nflverse injury dictionary](https://nflreadr.nflverse.com/articles/dictionary_injuries.html)
documents native GSIS identity and a `date_modified` field described as the time injury information
was updated. The installed [nflreadpy loader](https://nflreadpy.nflverse.com/api/load_functions/)
successfully returned 6,068 rows for 2025, but its actual 16-column frame omitted `date_modified`.
Season/week and report status therefore cannot establish when the platform could have observed a
historical record.

The nflreadpy schedules loader downloads the current full games dataset. The local copy contains
totals and spreads but no observation history, so these values cannot be represented as a sequence
of pre-lock market snapshots.

The same schedule payload contains documented stadium temperature and wind for outdoor/open-roof
games. Local coverage is 5,008 of 5,264 exposed games with both fields (95.1%); one closed-roof game
also carries weather values. The curated weather contract preserves all values and flags two wind
readings above 45 mph plus the indoor anomaly. Because the source does not preserve when these
conditions became known, exact game-time values remain ineligible as target-game features.

The official Open-Meteo Previous Runs API documents `_previous_day1` as the value predicted 24
hours before valid time and says most model archives begin in January 2024. Evaluation requests for
the same Buffalo coordinate returned the six approved temperature, humidity, precipitation,
wind-speed, wind-direction, and gust fields for 2024 and 2025; a 2023 request did not provide the
complete cohort. The pinned GFS seamless model is therefore the approved 2024+ provider. Free
access is limited to non-commercial evaluation; commercial historical APIs require Professional or
higher, and CC BY 4.0 attribution remains required. Exact request, timing, cost, fallback, and
production decisions are in `docs/WEATHER_FORECAST_SOURCE_CONTRACT.md`.

## Implemented Guardrails

`backend/app/product_services/point_in_time.py` defines the shared contract:

1. Missing snapshot time is not visible.
2. Missing consuming-run cutoff is not visible.
3. Observation before or exactly at cutoff is visible.
4. Observation after cutoff is not visible.

The predicate is used by:

- slate simulation player-pool injury exclusions;
- optimizer player-pool injury exclusions;
- target symbolic injury rules.

Existing raw and target rows remain intact for audit. The guardrail changes only whether they are
eligible for a cutoff-scoped decision.

`backend/app/services/weather_forecast_backfill.py` separately applies the reviewed historical
weather contract. It requires the exact contract, data kind, 24-hour lead, fixed-lead basis, null
provider timing, and `forecast_basis_at <= cutoff`. Forecast normalization never reads
`curated_game_weather`, so retrospective actuals cannot repair a missing forecast variable.

`backend/app/services/slate_weather.py` composes the two weather datasets without weakening either
contract. Current responses reject historical fixed-lead rows, historical responses keep actuals in
their own replay-ineligible object, and the effective selection cutoff cannot exceed the earliest
slate kickoff or server current time.

## Unblocking Decision

DATA-002 can resume through either route:

1. Select an authorized historical source that provides immutable observation timestamps and stable
   native IDs, then retain source payload, effective time, observed time, and ingest lineage.
2. Run the implemented prospective capture command for the 2026 season, using server receipt time
   as the non-backdatable observation time and source publication/effective time as separate
   metadata.

Vegas, props, weather, depth-chart, injury, and role sources must be approved independently. One
source's timestamp quality must not be generalized to another.

## Verification

- Focused point-in-time, simulation, optimizer, and symbolic-rule tests: 40 passed.
- WTHR-003 audit: 570/570 available and registry-matched; 570/570 raw checksums and manifests
  verified; zero timing, variable, secret-URI, or artifact issues.
- WTHR-005 focused slate/current/historical weather tests: 17 passed.
- Full Python suite: 428 passed with two pre-existing `datetime.utcnow()` deprecation warnings.
