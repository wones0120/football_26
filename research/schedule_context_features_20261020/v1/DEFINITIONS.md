# Native schedule context v1

The installed free nflreadpy loader returns one all-history schedule file. This package captures that returned CSV immutably through the existing SourceCaptureService, with actual clocks and provider URL, and verifies its bytes and indexed scope on every read. No per-season duplicate downloads, model fits or lineup actions occur. The native game ID, season/week/phase and both native teams must agree; games are unique and historical team aliases normalize consistently.

The [official schedule dictionary](https://raw.githubusercontent.com/nflverse/nflreadr/main/data-raw/dictionary_schedules.csv) documents game identity, literal roof state, surface, weather values and team-specific rest days. This package preserves the native measurements and does not infer stadium geography, a historical forecast issue time, rainfall, gusts or travel.

- **G20-M03** proposed exact native retractable-roof status: literal `open` or `closed`. `dome`, `outdoors` and missing values do not establish a retractable mechanism or its state, and remain unknown for this measure.
- **G20-M08** proposed exact native surface category, preserved without guessing a broader grass/turf classification.
- **G20-M09** proposed exact provider-reported team rest days, separately for home and away. No independent preceding-game completion proof is claimed.
- **G20-M04 partial variant**: native stadium temperature. The inspected schedule dictionary does not explicitly identify temperature units; values remain unconverted, with unit uncertainty retained.
- **G20-M05 partial variant**: native wind speed in miles per hour. The dictionary does not establish a sustained-wind averaging interval, so this is not relabeled certified sustained wind or gust speed.

Schedule roof/weather fields can reflect revised realized-game observations. A current historical download does not prove they were known before the game. Upcoming rows are retained as source schedule measurements, never certified pregame forecasts. Missing/invalid values remain unknown; known zero wind remains zero, negative temperature remains signed, negative wind/rest and nonintegral rest are unavailable. Current outputs are postlock descriptive and ineligible for pregame serving; models and optimizer consumers remain pending separately.

G20-M06 gusts, M07 precipitation and M10 travel/time-zone changes remain explicit source gaps. No weather forecast is invented from historical observations. Home/away and generic indoor/outdoor already have independent reviewed definitions and are not counted again here.

## Actual coverage

One all-history provider capture contains 7,548 unique native games across 1999–2026 (2,200,782 immutable CSV bytes). The derived artifact has 15,096 team-game contexts. Native retractable open/closed values are known for 1,526 team-games, temperature and wind each for 10,502, surface for 14,954, and source rest values for all 15,096. These are source-known counts, not original pregame availability claims. Future schedule rows and missing observed weather remain retained without inferring a forecast. See `actual_receipt.json` for hashes, source clocks and per-season counts.
