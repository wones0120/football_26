# Weather Forecast Source Contract

Date: 2026-08-01

Decision: `weather_forecast_source_contract_v1`

Status: implemented for WTHR-003 and WTHR-004

## Decision

Use [Open-Meteo Previous Runs](https://open-meteo.com/en/docs/previous-runs-api) as the primary
2024+ historical fixed-lead source. Pin `models=ncep_gfs_seamless`; do not use `best_match`, whose
underlying model selection can change by location or over time. Use the same pinned model family
through the live Forecast API for prospective capture.

Use exactly a 24-hour lead. For historical backfill, request only `*_previous_day1` fields. The
provider defines those fields as values predicted 24 hours before valid time and says most model
archives begin in January 2024. Coverage is therefore verified per game rather than inferred from
the advertised archive boundary.

Direct NOAA HRRR is the fallback for CONUS games only. It is not a global substitute, and fallback
rows with a different actual lead must remain distinguishable from exact-24-hour primary rows.

## Primary request contract

Endpoint for non-commercial evaluation:

`https://previous-runs-api.open-meteo.com/v1/forecast`

Production uses the customer endpoint issued through the Open-Meteo dashboard and an API key. The
key must never appear in logs, stored request URIs, manifests, or raw-response metadata.

Required request parameters:

| Parameter | Value |
|---|---|
| `models` | `ncep_gfs_seamless` |
| `timezone` | `GMT` |
| `timeformat` | `iso8601` |
| `temperature_unit` | `celsius` |
| `wind_speed_unit` | `ms` |
| `precipitation_unit` | `mm` |
| `cell_selection` | `nearest` |
| date range | the game kickoff's UTC calendar date |

Select `floor(kickoff_at_utc, one hour)` as the valid hour without interpolation. Preserve the
requested registry coordinates and the returned grid coordinates, elevation, timezone, and units.

Required hourly variables are:

- `temperature_2m_previous_day1`;
- `relative_humidity_2m_previous_day1`;
- `precipitation_previous_day1`;
- `wind_speed_10m_previous_day1`;
- `wind_direction_10m_previous_day1`;
- `wind_gusts_10m_previous_day1`.

Temperature, humidity, wind speed, and direction are instantaneous at the valid hour. The
[GFS/HRRR variable definitions](https://open-meteo.com/en/docs/gfs-api) define precipitation as a
preceding-hour sum and gust as a preceding-hour maximum. Precipitation probability, rain/snow
splits, and weather code are not part of v1 because evaluation responses did not provide complete
2024 coverage for them.

## Timing and leakage contract

Previous Runs exposes a fixed lead, not an individual model-run identity. It does not return a
historical provider publication timestamp. The provider directs consumers needing initialization
identity to Single Runs; the [Single Runs documentation](https://open-meteo.com/en/docs/single-runs-api)
also warns that initialization time is not public availability time.

WTHR-003 must therefore store:

- `valid_at`: the selected UTC forecast hour;
- `fixed_lead_hours=24`;
- `forecast_basis_at=valid_at - 24 hours`;
- `forecast_basis_kind=provider_fixed_lead`;
- `provider_issued_at=NULL` and `provider_available_at=NULL` unless the response supplies direct
  source evidence in a future contract version;
- `received_at`: the actual server receipt time of this backfill request;
- the immutable raw response, checksum, redacted canonical source URI, model, variables, units,
  registry record, game ID, and ingest-run lineage.

`forecast_basis_at` is derived semantics, not a claim that the response was published or observed
at that instant. Code, schemas, and docs must not relabel it as `observed_at`, `issued_at`, or
`available_at`. Missing provider timing remains null rather than fabricated.

For live capture, eligibility requires the actual captured `received_at <= slate_lock_at`. Later
responses are retained as append-only evidence but are excluded from pre-lock consumers. Under no
circumstance may retrospective actual weather populate a forecast field or repair a missing
forecast variable.

## Cost, rate, licence, and retention

The [current pricing matrix](https://open-meteo.com/en/pricing) allows the free endpoint only for
non-commercial use and limits it to 600 calls/minute, 5,000/hour, 10,000/day, and 300,000/month with
no uptime guarantee. Standard does not include historical APIs. Production or commercial use of
Previous Runs requires Professional or higher; Open-Meteo's May 2026
[product announcement](https://openmeteo.substack.com/p/single-runs-api) states that Professional
starts at EUR 99/month. Professional currently includes 5 million calls/month, no minute/hour/day
limit, a customer key and endpoint, and a 99.9% uptime target. Reconfirm price and terms at purchase
and deployment time.

Open-Meteo data are [CC BY 4.0](https://open-meteo.com/en/licence). The product must credit the
provider, link the licence, indicate unit conversions or other changes, and avoid implied
endorsement. Any UI that displays these values must show a nearby link such as “Weather data by
Open-Meteo.com.” The [service terms](https://open-meteo.com/en/terms) provide no accuracy or
availability warranty and may change.

No provider archive-retention guarantee is published. Retain each acquired raw response, checksum,
and normalized snapshot locally under the repository's immutable source-retention policy. Never
depend on a later re-fetch to reproduce a run.

Required WTHR-003 and WTHR-004 configuration names:

- `WEATHER_FORECAST_SNAPSHOT_ROOT=artifacts/weather_forecasts`;
- `WEATHER_FORECAST_PROVIDER=open_meteo_previous_runs`;
- `OPEN_METEO_BASE_URL` set to the customer endpoint in production;
- `CURRENT_WEATHER_FORECAST_PROVIDER=open_meteo_forecast`;
- `OPEN_METEO_FORECAST_BASE_URL` set to the customer Forecast API endpoint in production;
- `OPEN_METEO_API_KEY`, secret and blank only for local non-commercial evaluation;
- `OPEN_METEO_MODEL=ncep_gfs_seamless`;
- `OPEN_METEO_FIXED_LEAD_HOURS=24`;
- `OPEN_METEO_MIN_REQUEST_INTERVAL_SECONDS=0.11`;
- `WEATHER_FORECAST_REFRESH_INTERVAL_MINUTES=60`;
- `WEATHER_FORECAST_STALE_AFTER_MINUTES=120`.

These keys are runtime settings and `.env.example` entries. Both weather commands remain dry-run by
default; keyless network traffic requires both `--apply` and `--allow-free-evaluation`. The current
capture command requires explicit canonical game IDs and can run scheduled refreshes with `--watch`
until the declared slate lock.

## NOAA HRRR fallback

The [NOAA HRRR open archive](https://registry.opendata.aws/noaa-hrrr-pds/) is available from 2014 in
`s3://noaa-hrrr-bdp-pds` through unsigned access, with no API key or source fee. HRRR is a 3 km,
hourly CONUS model. International venues produce `fallback_out_of_domain`; adding a global NOAA GFS
fallback requires a separate reviewed contract.

For a kickoff valid hour, select the latest 00/06/12/18 UTC extended run whose initialization is at
or before `valid_at - 24 hours` and whose forecast hour covers the valid time. Persist the exact run
initialization, forecast hour, lead, model version where available, object URI, and checksum. This
normally yields a 24–29-hour lead, so downstream modeling must not treat it as the primary exact-24
hour cohort without an explicit lead feature or normalization rule.

Use HRRR `wrfsfc` fields for 2 m temperature and humidity, 10 m U/V wind components, surface gust,
and accumulated precipitation. Derive wind speed and direction from U/V and record that
transformation. Prefer the AWS archive. If NOMADS is used for current fallback, follow its
[scripted-download guidance](https://nomads.ncep.noaa.gov/info.php?page=gribfilter), including the
10-second request interval, and treat its short retention and delivery timing as non-guaranteed.

NOAA/NWS data are public and have no fee or credential requirement; retain source attribution and
do not imply NOAA endorsement.

## Production boundary

1. Free Open-Meteo access is local non-commercial evaluation only.
2. Production/commercial deployment requires an active Professional-or-higher subscription and
   configured secret key.
3. WTHR-003 historical coverage, WTHR-004 live capture, and the WTHR-005 canonical slate API gates
   have passed, but no weather row enters features, projections, simulations, or optimizer inputs
   until the WTHR-006 UI and WTHR-007 end-to-end integration contracts are implemented.
4. Historical forecasts and retrospective actuals remain different tables and API objects.
5. Historical primary rows are eligible only through the documented fixed-24-hour basis. Live rows
   are eligible only through actual pre-lock receipt.
6. Provider gaps, null variables, rate failures, out-of-domain fallbacks, and stale captures produce
   explicit missing/error states rather than actual-weather substitution.

This decision closed WTHR-002 and governs the completed WTHR-003 through WTHR-005 implementations. It
does not itself authorize a paid subscription purchase or production traffic.
