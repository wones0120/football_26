# Remaining play-end clock and restart/enforcement investigation

Completed one **0.755-second** cached evidence inventory under a 30-second cap, plus primary-source documentation/release inspection. **No new supported play-end game-clock or restart/enforcement observations were identified.** The investigation is complete; the underlying continuation gaps remain unresolved.

| Inspected evidence | Result |
| --- | --- |
| Cached TRAIN2023 rows | 49,665; full schema recorded |
| time_of_day | 48,203 ISO wall timestamps; 1,462 missing |
| end_clock_time | 41,918 ISO wall timestamps; 7,747 missing |
| play_clock | Reported zero in every row |
| Description candidates under frozen patterns | Three runoff mentions, one clock-reset instruction, zero restart matches |
| Candidate matches to saved censored terminal draws | Zero of 72 original; zero of 32 changed records, reported separately |

The descriptions identify these candidate native plays:

- `2023_06_NO_HOU:1890`: intentional-grounding play with a reported 10-second runoff.
- `2023_10_WAS_SEA:2401`: intentional-grounding play with a runoff and end-of-half annotation.
- `2023_19_PIT_BUF:2201`: injury/extra-timeout annotation mentioning a runoff.
- `2023_09_MIA_KC:4092`: punt/scoreboard comment instructing a clock reset to the snap time.

Original text, match spans, native IDs, source ordinals and finality flags are retained in [INVENTORY.json](INVENTORY.json). These are narrative candidates, not newly adjudicated enforcement. No seconds, restart policy or play-end game clock was filled. A reset-to-snap instruction does not measure the instant the original play became dead. Absence of pattern matches is not proof that all possible narrative phrasing was exhausted.

## Source semantics and historical correction

The [provider dictionary](https://nflfastr.com/reference/fast_scraper.html) distinguishes UTC play time from the play-clock reading at the snap. Neither supplies remaining game clock at play end. The [cleaning documentation](https://nflfastr.com/reference/clean_pbp.html) describes out_of_bounds as a description-derived field; it is not an adjudicated restart signal. Actual cached formats take precedence over interpreting an ambiguous field name.

An older preserved [native-clock receipt](../../native_clock_coverage_20261020/v1/receipt.json) calls end_clock_time game clock despite its own ISO timestamp examples. This interpretation is amended in the new [source review](SOURCE_REVIEW.json); the old receipt is unchanged. Its semantic label must not be used as proof of remaining game-clock coverage. The prior timeout-budget timing amendment also remains in force.

## Next source: candidate, not established support

The [nflverse raw 2023 release](https://github.com/nflverse/nflverse-pbp/releases/tag/raw_pbp_2023) has per-game RDS assets. The [asset listing](https://github.com/nflverse/nflverse-pbp/releases/expanded_assets/raw_pbp_2023) includes `2023_06_NO_HOU.rds` (displayed 39.8 KB), a useful one-game feasibility candidate because the processed cache contains an explicit runoff annotation for that game. Release availability does not establish the required schema or play linkage. Its contents were **not downloaded or decoded** in this pass.

No Rscript, rdata or pyreadr reader is installed in the task environment. No dependency was installed. The [next-source gate](NEXT_SOURCE_CHECK.md) bounds acquisition, decoding and acceptance to one game; do not repeat the processed-cache inventory or bulk-fetch a season before that gate passes. A currently obtained historical source remains reconstructed evidence, not original-vintage pregame data.

## Validation and disposition

**114 tests pass in 0.84 seconds**, including 16 new probe cases and 98 prior linkage/observation/continuation/event-boundary cases. Tests preserve negation, reversed rulings and narrative ambiguity, validate text spans and prohibit promoting wall timestamps or zero play-clock values into game-clock facts. [VALIDATION.json](VALIDATION.json) records hashes and case checks.

All prior results, ledgers, deferred cases and runtime hashes were preserved. No game-data download, reconstruction, fit, simulation, live projection or setting change ran. SCENARIO-05 remains gated. The next useful work is the one-game raw-source feasibility check; absent usable evidence there, continuation requires a different timing/enforcement source rather than more parser passes over this cache.
