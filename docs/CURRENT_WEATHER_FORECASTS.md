# Current Weather Forecast Capture

Last validated: 2026-08-26

Contract: `weather_forecast_source_contract_v1`

Status: WTHR-004 complete

## Outcome

Migration `0023_current_weather_forecast.sql`,
`backend/app/services/current_weather_forecast.py`, and
`scripts/capture_current_weather_forecasts.py` add append-only current-game capture through the
Open-Meteo Forecast API. Repeated refreshes retain separate raw responses, manifests, normalized
snapshots, receipt times, and per-run results. They do not update or delete earlier evidence.

The focused acceptance fixture retains three timestamped versions for one current-slate game. An
as-of-lock lookup returns the newest pre-lock version and excludes the retained post-lock version.
Separate tests cover freshness, stale classification, provider failures, request spacing, pinned
model/variables, key redaction, and artifact verification. A real prospective 2026 slate is still
required by DATA-002 and the WTHR-007 end-to-end acceptance task; the test fixture does not claim
that future production evidence has already been captured.

## Storage and timing contract

Historical and current forecasts share `weather_forecast_snapshot` but remain distinguishable:

| Field | Historical fixed-lead row | Current capture row |
| --- | --- | --- |
| `data_kind` | `historical_fixed_lead_forecast` | `current_forecast_capture` |
| `provider` | `open_meteo_previous_runs` | `open_meteo_forecast` |
| Variables | six `*_previous_day1` fields | corresponding six live hourly fields |
| `fixed_lead_hours` | `24` | `NULL` |
| `forecast_basis_kind` | `provider_fixed_lead` | `server_received_at` |
| `forecast_basis_at` | `valid_at - 24h` | actual `received_at` |
| Provider issued/available time | `NULL` | `NULL` |
| Cutoff rule | derived fixed-lead basis at/before cutoff | actual receipt at/before cutoff |

PostgreSQL check constraints enforce these combinations. A partial unique index retains one
historical natural-key row, while a separate current index includes `received_at` and permits many
versions per game. The existing database trigger continues to reject snapshot updates and deletes.

`select_current_forecast_at_cutoff` requires the canonical `game_id`, optionally constrains the
current `registry_record_id`, rejects rows outside the pinned contract, and returns the newest
eligible receipt. Retrospective `curated_game_weather` is never consulted.

## Operator workflow

Apply migrations, then preview an explicitly identified slate without network calls or writes:

```bash
.venv/bin/python scripts/apply_migrations.py
.venv/bin/python scripts/capture_current_weather_forecasts.py \
  --season 2026 \
  --week 1 \
  --slate WEDNESDAY_NIGHT \
  --slate-lock-at 2026-09-09T20:20:00-04:00 \
  --game-id 2026_01_NE_SEA
```

Game IDs are required and repeatable. The command does not parse matchup display names or infer
slate membership from salary text. A game with no schedule row, resolved venue mapping, registry
record, or kickoff is rejected or explicitly quarantined.

For a one-time local non-commercial evaluation capture:

```bash
.venv/bin/python scripts/capture_current_weather_forecasts.py \
  --season 2026 \
  --week 1 \
  --slate WEDNESDAY_NIGHT \
  --slate-lock-at 2026-09-09T20:20:00-04:00 \
  --game-id 2026_01_NE_SEA \
  --apply \
  --allow-free-evaluation
```

Production rejects keyless capture and requires the customer Forecast API endpoint plus
`OPEN_METEO_API_KEY`. API keys are removed from persisted request URIs, manifests, errors, and
ingest lineage.

`WEATHER_FORECAST_SNAPSHOT_ROOT` defaults to the ignored repository-local
`artifacts/weather_forecasts` directory for development. Before live-season capture, override it
with an absolute path on backed-up durable storage. The database retains checksums and lineage, but
it cannot reconstruct a lost raw response or manifest.

## Scheduled refresh and provider limits

Add `--watch` to the apply command to repeat a full slate refresh until the declared lock:

```bash
.venv/bin/python scripts/capture_current_weather_forecasts.py \
  --season 2026 \
  --week 1 \
  --slate WEDNESDAY_NIGHT \
  --slate-lock-at 2026-09-09T20:20:00-04:00 \
  --game-id 2026_01_NE_SEA \
  --apply \
  --allow-free-evaluation \
  --watch
```

The default refresh interval is 60 minutes. Calls within a refresh are separated by at least 0.11
seconds, keeping one process below the documented free-tier minute rate; both values are
configurable. Watch mode requires a future lock and stops at lock. A one-shot command may still be
run after lock: that response is retained as evidence, while cutoff selection excludes it from the
pre-lock view.

Run only one watcher for a slate. Process supervision and host-level mutual exclusion remain an
operator responsibility; WTHR-004 does not install or mutate host scheduler state.

## Freshness, failures, and recovery

Each command reports coverage before capture, after capture, and reconstructed as of slate lock.
Every expected game receives one of `available`, `partial`, `missing`, `stale`, or `error` in the
freshness report. Available forecasts become `stale` after 120 minutes by default. The report also
includes snapshot/receipt identity, age, source, latest attempt time/status, and the latest explicit
failure reason.

Every refresh creates an `ingest_run`; `weather_forecast_capture_result.capture_kind=current_refresh`
separates it from historical backfill attempts and retains slate plus declared lock context.
Provider errors do not erase the last successful forecast. Rerun the one-shot command or leave watch
mode running: a successful later receipt appends a new version and becomes newest only for cutoffs
at or after that receipt.

Use `--verify-artifacts` to recompute the checksum and compare the canonical manifest for every
cutoff-selected snapshot. Any mismatch becomes an explicit error state.

Weather data remain subject to Open-Meteo's CC BY 4.0 attribution requirement. Free endpoint use is
non-commercial evaluation only; see `docs/WEATHER_FORECAST_SOURCE_CONTRACT.md` for the full source,
cost, licence, fallback, and production decision.
