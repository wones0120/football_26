# War Room Weather

Date: 2026-08-02

API contract: `slate_game_weather_v1`

Status: WTHR-006 complete

## Outcome

The War Room requests `GET /api/weather/slate` whenever season, week, or slate changes. The Game
Pressure Matrix unions its projection-derived pressure rows with every canonical, unresolved, or
ambiguous matchup returned by the API; it does not truncate the weather contract to a fixed card
count. Projection context associates by canonical `game_id` first, with normalized team/opponent
identity as a fallback. Player display names are never used for game association.

Every matrix card shows one explicit weather state: `available`, `indoor`, `stale`, `missing`, or
`error`. A temporary `loading` badge is used only while the request is in flight. If the weather
request fails, projection-only matchups remain visible with `error`; if a projection matchup has no
canonical weather row, it remains visible with `missing`.

## Matchup detail

Selecting a matrix card opens `Matchup Weather Detail` with:

- temperature in Fahrenheit;
- sustained wind and gusts in miles per hour;
- precipitation in millimeters;
- the venue-registry roof default, explicitly labeled as a default rather than a captured roof
  observation;
- provider/model, forecast timestamp, valid time, and age at the effective cutoff;
- venue name plus readable game, venue, forecast, freshness, identity, and capture warnings.

Fixed-indoor games keep the explicit `indoor` state even when no forecast values apply. Missing or
partial fields remain `--`; retrospective actual conditions never fill them.

## Forecast and actual separation

The forecast metrics and lineage occupy the primary weather detail. The UI renders an actual
conditions section only when the API classifies the request as `historical` and supplies an actual
object. That section is visually isolated and labeled `Historical Actual · Replay-Ineligible`, and
states that observed values are never used as the forecast. Current-slate responses cannot expose
the section.

## Verification

- All 12 UI tests pass. Focused cases cover canonical matchup union, projection-only fallback,
  retention of more than eight games, unit and freshness formatting, quality warnings, and the
  historical-only actual display gate.
- `npm run build` passes with TypeScript contract checking and a production Vite bundle.
- The local app was rendered at 1440px and 390px. The fallback/error state has no page-level
  horizontal overflow and produced no browser console errors; matrix/detail grids collapse from
  multi-column desktop layouts to one/two columns at the declared mobile breakpoints.
- WTHR-007 subsequently rendered the real DraftKings 2025 Week 11 `SUNDAY_MAIN` response at both
  widths: all 11 games remained visible, with 9 `available` and 2 `indoor`, readable detail and
  replay-ineligible actual panels, no horizontal overflow, and no browser console errors. The exact
  evidence and remaining prospective-current gate are in `docs/WTHR-007_ACCEPTANCE.md`.
