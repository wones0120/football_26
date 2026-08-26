# Historical Fixed-Lead Weather Forecasts

Date: 2026-08-01

Contract: `weather_forecast_source_contract_v1`

Status: WTHR-003 complete for the 2024–2025 development cohort

## Outcome

Migration `0022_historical_weather_forecast.sql` and
`scripts/backfill_historical_weather_forecasts.py` implement the reviewed Open-Meteo Previous Runs
backfill. The development cohort contains 570 immutable snapshots for 570 expected games. All 570
are `available`, all six pinned variables are populated, every current venue mapping matches, and
the checksum/manifest audit reports zero issues.

The historical forecast table is separate from `curated_game_weather`, which remains retrospective
actual/result context. The forecast normalizer reads only the retained provider response; an actual
temperature or wind value cannot repair a missing forecast field.

## Operator workflow

Apply migrations, then preview the eligible game set without making network requests or writes:

```bash
.venv/bin/python scripts/apply_migrations.py
.venv/bin/python scripts/backfill_historical_weather_forecasts.py \
  --season-start 2024 \
  --season-end 2025
```

For local non-commercial evaluation with the keyless endpoint, the operator must explicitly
acknowledge the licence boundary:

```bash
.venv/bin/python scripts/backfill_historical_weather_forecasts.py \
  --season-start 2024 \
  --season-end 2025 \
  --apply \
  --allow-free-evaluation
```

Production must configure a Professional-or-higher customer endpoint and `OPEN_METEO_API_KEY`;
keyless apply mode is rejected when `APP_ENV` is `prod` or `production`. A single game can be
exercised with a repeated `--game-id GAME_ID`. Existing natural-key snapshots are verified and
reused without another provider request.

Recompute every stored SHA-256 and validate every manifest with:

```bash
.venv/bin/python scripts/backfill_historical_weather_forecasts.py \
  --season-start 2024 \
  --season-end 2025 \
  --verify-artifacts
```

The command exits without writes unless `--apply` is present. Apply mode exits nonzero when any
expected game is partial, missing, quarantined, or failed, after preserving a per-game result and
continuing the run.

## Request and normalization contract

Each request uses the resolved `registry_record_id` coordinates and pins:

- `models=ncep_gfs_seamless`;
- `timezone=GMT` and ISO-8601 time values;
- Celsius, metres per second, and millimetres;
- nearest grid-cell selection;
- the kickoff UTC calendar date;
- the six `*_previous_day1` variables named in
  `docs/WEATHER_FORECAST_SOURCE_CONTRACT.md`.

The selected valid time is the kickoff rounded down to the UTC hour, with no interpolation. The
snapshot retains requested and returned coordinates, returned elevation/timezone, returned units,
all normalized values, quality flags, the exact raw JSON, and a canonical manifest. API keys are
removed from the stored request URI and never written to the manifest or lineage result.

## Timing and leakage boundary

The fields deliberately mean different things:

- `valid_at`: selected forecast hour;
- `fixed_lead_hours=24`;
- `forecast_basis_at=valid_at-24h`, a derived lead-time basis;
- `forecast_basis_kind=provider_fixed_lead`;
- `provider_issued_at=NULL` and `provider_available_at=NULL` because Previous Runs does not supply
  those facts;
- `received_at`: actual 2026 server receipt time for the retained backfill response.

`historical_forecast_visible_at_cutoff` accepts the reviewed historical row only when its contract,
data kind, lead, basis kind, and null provider timing are intact and `forecast_basis_at <= cutoff`.
It does not relabel the derived basis as an observation or publication timestamp. WTHR-004 adds
separate live receipt-time versions to the same table; historical rows are still not wired into
projections, simulations, or optimizer inputs. WTHR-005 now exposes the cutoff-safe canonical slate
API; UI and end-to-end integration remain behind WTHR-006 and WTHR-007.

## Persistence and recovery

`weather_forecast_snapshot` has a natural uniqueness key across contract, game, venue registry
record, model, lead, and valid time. PostgreSQL rejects updates and deletes. Raw content is stored
below `WEATHER_FORECAST_SNAPSHOT_ROOT`, grouped by provider, season, week, game, snapshot ID, and raw
SHA-256. A new venue-registry version can therefore append corrected evidence without rewriting an
older record.

`weather_forecast_capture_result` links every attempted game to its `ingest_run`. Result states are
`captured`, `reused`, `partial`, `missing`, `error`, or `quarantined`, with a redacted request URI and
explicit reason where applicable. Each game commits independently. After interruption, rerun the
same command: verified snapshots are reused and only missing games call the provider.

## Development acceptance evidence

The 2026-08-01 acceptance run reported:

| Check | Result |
| --- | ---: |
| Expected schedule games | 570 |
| Eligible games | 570 |
| Stored and current-mapping-matched snapshots | 570 |
| Fully available six-variable snapshots | 570 |
| Partial, missing, error, or quarantined games | 0 |
| Provider issued/availability timestamps populated | 0 |
| Artifact checksum or manifest errors | 0 |
| Idempotency sample | 1 initial provider call, then reuse with 0 calls |

Targeted tests cover pinned requests, key redaction, exact-hour selection, missing-hour behavior,
content/manifest tamper detection, natural-key reuse, fixed-lead cutoff visibility, explicit
provider errors, and the prohibition on actual-weather substitution.

Weather data remain subject to Open-Meteo's CC BY 4.0 attribution requirement. Free endpoint use is
non-commercial evaluation only; see `docs/WEATHER_FORECAST_SOURCE_CONTRACT.md` for the cost,
licence, fallback, and production decision.
