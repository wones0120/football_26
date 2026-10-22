# Source representation verification

- Primary snap dictionary: https://nflreadr.nflverse.com/articles/dictionary_snap_counts.html — offense_pct describes offensive snap participation; position is the reported player position, game_id is the native game key.
- Primary producing parser: https://raw.githubusercontent.com/nflverse/nflverse-pfr/master/R/game_snaps.R — lines75–90 select offense_pct, remove the percent character and divide percentage fields by100. This confirms the resulting fraction scale.
- Actual frozen retained revision706735c7-e1c2-5e98-a662-52021f0406b3:8,955 numeric offense_pct values, all in[0,1],3,537 positive. No conversion inferred solely from observed numeric range.

Primary documentation inspected2026-10-20. Documentation inspection time is not historical source availability. The retained DB freeze does not claim to be the original provider HTTP capture.
