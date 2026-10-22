# One-game raw-source feasibility check

Authorized scope: only 2023_06_NO_HOU from the primary nflverse raw_pbp_2023 release. No season expansion, retries, model fitting, source repairs, simulation or live consumers. Preserve all prior results and runtime hashes.

Freeze URL and expected SHA256 from the primary release listing before fetching:

- URL: https://github.com/nflverse/nflverse-pbp/releases/download/raw_pbp_2023/2023_06_NO_HOU.rds
- Expected SHA256: abfdaf9b9a1025a565e76b3ee4365ef7811bc83c5ee80549301c7cb7d2c3fffc
- Listed updated time: 2026-03-27T13:21:05Z; displayed size 39.8 KB.
- Maximum compressed bytes: 1 MiB. Maximum decompressed serialization and decoded JSON bytes: 8 MiB each. Acquisition whole-job cap: 30 seconds; no retry, one HTTP request chain (redirects allowed).

Set up a temporary isolated Python reader using pinned rdata 1.1.0 and its missing xarray dependency 2025.1.2, retaining pip's wheel hashes and package versions in a receipt. Use existing numpy/pandas; do not alter repository dependencies or the application environment. Setup process cap 60 seconds, pip retries zero. Network access requires the host sandbox's reviewed escalation; this is not a request for a broader task. A metadata-only sandbox DNS failure before setup is not a game-data fetch.

Preserve original downloaded bytes with retrieval metadata and hash. Reject a differing hash without replacing or treating the source as the same revision. Bounded gzip expansion precedes RDS parsing. Parse R serialization as data using the isolated reader, not R execution. Record the decoded root type/schema before making assumptions about raw fields. Any subsequent cached schema/native-key inventory uses a separate 30-second cap and never refetches the game.

Inventory original paths/types and available clocks, stop/restart/runoff/correction/untimed fields. Compare native game/play IDs, order and the runoff record's surrounding context against the frozen processed game; retain mismatches and revisions explicitly. A start/snap game clock, a play-clock value or UTC timestamp cannot become play-end remaining game clock by renaming. A raw annotation or field name alone does not adjudicate enforcement. A passing gate needs native-linkage and semantic evidence for at least one genuinely missing observation type. Otherwise record the source as insufficient and stop, without increasing sample size.
