# Historical Weather Data

Date: 2026-08-01

Actual-weather contract: `historical_game_weather_actual_v1`

Migration: `0020_historical_game_weather.sql`

## Outcome

Historical game weather is now available as a standard curated dataset without weakening the
point-in-time rules. The source is the temperature, wind, roof, surface, stadium, date, and kickoff
context already retained in nflverse schedule rows.

| Measure | Rows |
|---|---:|
| Games, 2000–2025 | 7,017 |
| Temperature and wind present | 5,009 |
| Indoor, weather not applicable | 1,752 |
| Exposed roof with incomplete weather | 256 |
| Quality-flagged rows | 259 |
| Replay-eligible rows | 0 |

The official [nflverse games documentation](https://github.com/nflverse/nfldata/blob/master/DATASETS.md#games)
defines `temp` as stadium temperature and `wind` as wind speed in miles per hour for outdoor and
open-roof games. It also documents game date plus kickoff time in Eastern time, regardless of the
stadium's local zone. The curator converts that date/time pair to a timezone-aware UTC kickoff.

## Storage and pipeline behavior

`curated_game_weather` stores one latest-source row per `game_id` with:

- season, week, game type, home/away teams, stadium, and UTC kickoff;
- roof and surface;
- temperature in Fahrenheit and wind in mph;
- weather completeness status and quality flags;
- source system, ingest run, and exact raw schedule-row lineage.

Schedule ingestion rebuilds the curated weather season automatically. Historical refresh is also
available as a dry-run-first command:

```bash
python scripts/build_historical_game_weather.py
python scripts/build_historical_game_weather.py --apply
```

Apply mode replaces only the requested curated season range. Raw schedules remain the rebuildable
source evidence.

## Leakage boundary

These values describe conditions associated with the completed game. The schedule archive does not
prove when the exact temperature or wind became observable. They therefore must not be treated as a
forecast that was available before DFS lock.

The boundary is enforced three ways:

1. `data_kind` is `retrospective_game_observation`.
2. `observed_at` is always null and `replay_eligible` is always false.
3. A database check constraint rejects any row with a non-null observation time or true replay flag.

This dataset is suitable for descriptive analysis, outcome normalization, and comparing archived
forecasts with realized conditions. It is not wired into the player feature matrix, simulations,
or optimizer.

## Quality findings

The source values are preserved rather than silently corrected. The initial build flags:

- 256 exposed games missing temperature or wind;
- `2008_02_TEN_CIN` at 70 mph and `2016_13_NYG_PIT` at 71 mph for extreme-wind review;
- `2025_10_ATL_IND`, a closed-roof game with temperature and wind values.

These flags do not discard rows. Any correction needs independent evidence and explicit lineage.

## Ranked pre-lock forecast sources

### 1. Open-Meteo Previous Runs — preferred for 2024+

The [Previous Runs API](https://open-meteo.com/en/docs/previous-runs-api) exposes fixed lead-time
variables: `_previous_day1` is the forecast for a valid hour produced 24 hours earlier. Most model
archives begin in January 2024; GFS 2 m temperature has longer coverage. Evaluation calls using
`gfs_seamless` returned temperature, humidity, precipitation probability/amount, wind, and gusts for
2024 and 2025. The same 2023 probe returned only temperature, so the proposed full-variable boundary
is 2024.

This is the best fit because the 24-hour lead is explicit, the response is hourly, GFS is stable for
U.S. and international games, and one game needs only a small request. The approved contract pins
`ncep_gfs_seamless` and six core variables. The initial backfill must store the raw response, model,
valid hour, 24-hour lead, derived forecast-basis time, null provider issued/availability times,
server receipt time, units, coordinates, source URI, and attribution. The fixed-lead basis must not
be mislabeled as source-observed availability.

The [Open-Meteo pricing page](https://open-meteo.com/en/pricing) permits free non-commercial
evaluation but requires the Professional plan or higher for commercial historical API access.
Weather data requires CC BY 4.0 attribution. The exact approved request, timing, cost, attribution,
retention, fallback, and production boundaries are recorded in
`docs/WEATHER_FORECAST_SOURCE_CONTRACT.md`.

### 2. NOAA HRRR archive — free, exact runs, higher engineering cost

NOAA documents an hourly 3 km HRRR model and [public archives since
2014](https://registry.opendata.aws/noaa-hrrr-pds/). Exact run and forecast-hour files make strict
cutoff reconstruction possible. The tradeoff is GRIB2/Zarr processing, larger storage and transfer,
coordinate extraction, version changes, and separate handling for international games outside the
CONUS grid. This is the fallback if Open-Meteo cost or licensing is unacceptable.

### 3. Open-Meteo reanalysis or WeatherAPI history — actuals only

[Open-Meteo Historical Weather](https://open-meteo.com/en/docs/historical-weather-api) provides
long-running reanalysis, useful for filling actual-condition gaps but not for reconstructing a
pregame forecast. WeatherAPI states that its history is forecast data archived after midnight for
the previous day; without the exact as-issued run visible before lock, it is not the preferred
replay source. Neither should be written to a pre-lock snapshot table without stronger timestamp
evidence.

## Fixed-lead forecast implementation

The reviewed `nfl_venue_registry_v1` registry resolves all 570 games from 2024–2025, including 15
neutral-site decisions, without matching on stadium display name. WTHR-003 has retained the 570-game
GFS `_previous_day1` cohort in a separate immutable snapshot table with verified raw artifacts.
Those forecasts remain separate from `curated_game_weather`, and no weather is yet wired into model
features. See `docs/HISTORICAL_WEATHER_FORECASTS.md` for implementation and acceptance evidence and
`docs/WEATHER_FORECAST_SOURCE_CONTRACT.md` for the source contract.

## Verification

- Historical-weather, venue, forecast, schedule-ingest, source-capture, and schema-drift tests pass
  in the 418-test Python suite.
- Full Python suite: 405 passed with two pre-existing `datetime.utcnow()` deprecation warnings.
- Migration `0020` applied to the development database and a second migration pass applied nothing.
- Two consecutive 2000–2025 rebuilds each wrote the same 7,017 rows with zero replay-eligible rows.
