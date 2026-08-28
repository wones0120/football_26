# WTHR-007 Weather Acceptance

Date: 2026-08-28

Status: historical acceptance passed; prospective current acceptance in progress

## Outcome

The real-data historical half of WTHR-007 passes for DraftKings 2025 Week 11 `SUNDAY_MAIN` across
the database, `slate_game_weather_v1`, and the War Room. The focused acceptance suite also proves
the current-capture mechanics with deterministic fixtures, including same-receipt reuse, append-only
versions, stale/error reporting, and post-lock exclusion.

The full 2026 schedule and the real DraftKings Week 1 Sunday Main salary slate are now retained as
immutable prospective evidence. All 12 salary matchups resolve to canonical schedule games without
quarantine. WTHR-007 is therefore active rather than calendar-blocked, but it is not complete: the
development database still has no successful real `current_forecast_capture` row. A real response
cannot be backdated or replaced with a fixture without violating the receipt-time contract.

## Real 2026 preflight

Command:

```bash
.venv/bin/python scripts/capture_current_weather_forecasts.py \
  --season 2026 \
  --week 1 \
  --slate WEDNESDAY_NIGHT \
  --slate-lock-at 2026-09-09T20:20:00-04:00 \
  --game-id 2026_01_NE_SEA
```

Observed result:

| Check | Result |
| --- | --- |
| Mode | Dry run; no provider request and no writes |
| Schedule rows / latest-season games | 272 / 272 |
| Expected / eligible / quarantined games | 1 / 1 / 0 |
| Canonical game | `2026_01_NE_SEA` |
| Stored current state | `missing`, as expected before the first real receipt |

This proves the retained schedule, canonical game ID, venue mapping, kickoff, and capture contract
are ready for a real receipt. It does not satisfy the prospective acceptance gate by itself.

## Real 2026 Sunday Main salary and weather gate

The source-authorized Week 1 Sunday Main salary file was captured at
`2026-08-28T07:37:56.614169-04:00`, before the 2026-09-13 `13:00:00-04:00` lock.

| Check | Result |
| --- | --- |
| Salary snapshot / ingest run | `d893bd08-475f-50b2-8b29-235670d3805d` / `ab38816d-9b5d-5f7e-8f24-ca60ee1d3f8d` |
| Salary SHA-256 | `39f7d4669ba4d45c711ae8b135468ce01180c5b181d1f77076c75258a72287a6` |
| Salary rows | 719 raw and 719 curated |
| Player identities | 531 resolved; 188 retained in the review queue; 0 unresolved DSTs |
| Expected / resolved games | 12 / 12 |
| Weather dry-run eligibility | 12 eligible; 0 quarantined |
| Pre-attempt API states | 4 indoor; 8 missing |
| Artifact and retry checks | Salary artifact verified; identical rerun reused the same snapshot and ingest run |

The first real provider attempt is retained under current-refresh ingest run
`a7168ada-224a-4590-9f62-f9535131a255`. It made 12 requests, retained 12 error results, and created
zero forecast snapshots. A direct diagnostic response identified the exact boundary: on August 28,
the provider accepted `start_date` only through September 12, while every Sunday Main game is on
September 13. The post-attempt API therefore truthfully reports 12 `error` states with
`forecast_capture_error` and `forecast_missing`; no forecast values were fabricated. The earliest
valid retry is August 29.

## Real historical acceptance slice

Request:

```bash
curl --get http://127.0.0.1:8000/api/weather/slate \
  --data-urlencode source_system=draftkings \
  --data-urlencode season=2025 \
  --data-urlencode week=11 \
  --data-urlencode slate=SUNDAY_MAIN \
  --data-urlencode cutoff_at=2025-11-16T13:00:00-05:00
```

Observed result:

| Check | Result |
| --- | --- |
| Contract / request kind | `slate_game_weather_v1` / `historical` |
| Requested, effective, and lock cutoff | `2025-11-16T18:00:00Z` |
| Salary rows | 556 |
| Expected / resolved / returned games | 11 / 11 / 11 |
| Identity states | 11 resolved; no identity quality flag |
| Weather states | 9 available; 2 indoor |
| Venue roof defaults | 7 outdoor; 2 retractable; 2 fixed indoor |
| Forecast bases after cutoff | 0 |
| Actual rows marked replay eligible | 0 |

The two retractable-default games remain forecast-exposed; the two fixed-indoor games retain the
explicit `indoor` state. The source cohort reports actual roof values as `closed`, `dome`, or
`outdoors`, so this run does not invent a captured `open` roof observation. The venue registry
default remains clearly distinct from result-time actual roof metadata.

An adversarial request with `cutoff_at=2026-01-01T00:00:00Z` returned the same lock-safe view,
clamped `cutoff_at` to `2025-11-16T18:00:00Z`, and added
`cutoff_clamped_to_slate_lock`. No actual row became replay eligible.

## Real historical UI acceptance

The War Room was rendered against the running API with the same Week 11 Sunday Main slice.

| Viewport | Result |
| --- | --- |
| 1440 × 1000 | 11 cards; 9 available and 2 indoor; no page or card overflow |
| 390 × 844 | 11 cards; 9 available and 2 indoor; no page, card, detail, or actual-panel overflow |

The selected detail showed forecast provider/model, 24-hour basis timestamp, valid time, freshness,
venue, roof default, and quality state. Selecting `CHI @ MIN` showed `Fixed indoor`, U.S. Bank
Stadium, and a separate `Historical Actual · Replay-Ineligible` panel with `Indoor Not Applicable`.
The browser reported zero console errors.

## Reproducible scenario coverage

The focused suite covers the acceptance branches that cannot all occur on one real slate:

| Scenario | Evidence |
| --- | --- |
| Historical immutable/idempotent capture | A repeated fixed-lead run reuses one verified snapshot and makes no second provider request. |
| Current refresh idempotency | Repeating the same receipt time and response reuses the existing snapshot while retaining a separate run result. |
| Current append-only knowledge timeline | Three receipt-timed versions remain stored; pre-lock selection returns the newest eligible version and excludes the retained post-lock version. |
| Missing venue/kickoff and unresolved matchup | Capture quarantines missing canonical venue evidence; the API retains unresolved salary matchups instead of dropping them. |
| Neutral/international games | Reviewed game-ID overrides select Dublin, Berlin, Madrid, and the remaining versioned neutral-site records without display-name joins. |
| Indoor/retractable/outdoor behavior | Fixed-indoor games are explicit; retractable defaults remain forecast-exposed; actual roof metadata remains separate. |
| Stale and provider-error states | Age changes state without mutating the snapshot, and the newest provider failure remains visible without erasing prior evidence. |
| Forecast/actual leakage | Actual conditions never repair a missing forecast; post-lock current versions are excluded; retrospective actuals remain `replay_eligible=false`. |
| Decision-input boundary | `test_weather_decision_boundary.py` fails if weather snapshot tables, weather services, or `slate_game_weather_v1` enter production projection, simulation, or optimizer modules. |

Validation commands:

```bash
PYTHONPATH=. .venv/bin/pytest -q \
  backend/app/tests/test_weather_decision_boundary.py \
  backend/app/tests/test_weather_forecast_backfill.py \
  backend/app/tests/test_current_weather_forecast.py \
  backend/app/tests/test_slate_weather_api.py \
  backend/app/tests/test_venue_registry.py \
  backend/app/tests/test_historical_weather.py
npm --prefix ui test
npm --prefix ui run build
PYTHONPATH=. .venv/bin/pytest -q
```

Results on 2026-08-26: 19 targeted GPP/weather/schedule/API tests passed, the full backend suite
passed 433 tests without warnings, all 12 UI tests passed, and the production UI type-check/build
passed. The migration-owned `target` schema also passed at 57/57 tables with zero issues. The
current development `public` schema has separate legacy drift tracked by `ENG-003`; none of the
weather tables appeared in that drift report.

On 2026-08-28, the focused source-capture, current-weather, and slate-weather suite passed 15 tests
after the real salary capture and retained provider-horizon attempt.

## Remaining current-slate gate

The 2026-08-28 development inventory is:

- `current_forecast_capture` snapshots: 0;
- `current_refresh` capture results: 12, all retained provider-horizon errors;
- 2026 Week 1 Sunday Main curated salary rows: 719;
- salary identity coverage: 531 resolved, 188 open review rows, 0 unresolved DSTs;
- 2026 schedule rows: 272;
- 2026 prospective source snapshots: 3 (`schedules`, the retained player-registry crosswalk, and
  the Week 1 salary slate).

To close WTHR-007, retry the current weather capture once September 13 is inside the provider
horizon, retain at least two successful pre-lock refreshes, and rerun the API/UI checks before
lock. A post-lock refresh must then be retained and shown to be excluded from the reconstructed lock
view. The 188 player-identity reviews are tracked separately because game-level salary identity is
already 12/12; they remain required before complete projection and optimizer use. Until the weather
evidence exists, the ticket remains in progress but incomplete.
