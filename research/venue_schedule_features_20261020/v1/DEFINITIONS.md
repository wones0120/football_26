# Native venue and home/away features

`native_venue_schedule_features_v1` covers G20-M01 (canonical home/away) and G20-M02 (provider indoor/outdoor venue classification). Actual native event ID, exact canonical home/away teams and kickoff must match the verified pregame scoreboard. Display names never supply identity. A nonempty native venue ID and a boolean `venue.indoor` are required for classification; absent/string/number flags remain unknown. Home/away remains independent of bookmaker odds and weather fields.

The actual indexed SourceSnapshot bytes/manifest, exact season/week ESPN URI, native REG season/week, original capture/receipt/cutoff and pre-kickoff pregame status are checked. ORM UTC timestamps are interpreted as server-owned records; provider timestamps require timezone markers. Ambiguous native events, late observations or source integrity mismatches reject rather than choosing an arbitrary match.

Indoor/outdoor is the provider's venue classification, not a retractable-roof observation or game-time weather forecast. This source does not supply roof position, validated weather forecasts, surface material, last actually played-game chronology or a travel itinerary. G20-M03–M10 stay explicit source gaps in this package; neither realized PBP weather nor a team's usual home stadium fills them.

Actual SF/WAS source e924c4a1... has native venue4738, Levi's Stadium, indoor=false. Both teams receive outdoor classification, SF home/WAS away. New derivation is after lock and descriptive/non-serving, with original pre-lock source clocks preserved. No models, forecasts, source writes, saved lineups or settings changes occur.
