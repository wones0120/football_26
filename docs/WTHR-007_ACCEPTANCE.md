# WTHR-007 Weather Acceptance

Date: 2026-08-26

Status: historical acceptance passed; prospective current acceptance in progress

## Outcome

The real-data historical half of WTHR-007 passes for DraftKings 2025 Week 11 `SUNDAY_MAIN` across
the database, `slate_game_weather_v1`, and the War Room. The focused acceptance suite also proves
the current-capture mechanics with deterministic fixtures, including same-receipt reuse, append-only
versions, stale/error reporting, and post-lock exclusion.

The full 2026 schedule is now retained as immutable prospective evidence. On 2026-08-26, a
non-network preview of the September 9 opener resolved its canonical schedule and venue evidence
without quarantine. WTHR-007 is therefore active rather than calendar-blocked, but it is not
complete: the development database still has no real `current_forecast_capture` row and no 2026
salary slate. A real response cannot be backdated or replaced with a fixture without violating the
receipt-time contract.

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

## Remaining current-slate gate

The 2026-08-26 development inventory is:

- `current_forecast_capture` snapshots: 0;
- `current_refresh` capture results: 0;
- 2026-or-later curated salary rows: 0;
- 2026 schedule rows: 272;
- 2026 prospective source snapshots: 2 (`schedules` plus the retained player-registry crosswalk).

To close WTHR-007, capture the first source-authorized 2026 salary slate and resolved canonical game
set, start the current weather watcher while those kickoffs are inside the provider horizon, retain
at least two pre-lock refreshes, and rerun the API/UI checks before lock. A post-lock refresh must
then be retained and shown to be excluded from the reconstructed lock view. Until that evidence
exists, the ticket remains in progress but incomplete.
