# Next Gen Stats source capture

Three installed nflreadpy all-history calls, one per family, were captured through the existing immutable SourceCaptureService. Actual source rows cover 2016–2026. Indexed season/week identifies capture context; it does not filter source rows. Weekly REG, weekly POST and week-0 season summaries remain distinct. No game ID is fabricated from player/week, and no raw-name join is used. Exact persisted nflreadpy GSIS aliases attach canonical UUIDs; ambiguous or absent aliases emit identity review requests.

Provider reference: https://nflreadr.nflverse.com/reference/load_nextgen_stats.html
Dictionary: https://nflreadr.nflverse.com/articles/dictionary_nextgen_stats.html
The provider selects players above minimum attempts; the reference does not specify numeric thresholds. Missing players are unknown, never zero. Full-team opportunity denominators cannot be inferred from this selected cohort. Tracking expectations and CPOE/RYOE are vendor-derived measurements with unknown model vintages, not independently calibrated forecasts.

Native CSV serialization is immutable and byte-hashed; the installed loader does not expose original remote parquet bytes. Capture time is not original publication, and provider cache freshness is unknown. Actual captures are postlock descriptive and are not registered as current serving evidence. Receiving source exposes avg_intended_air_yards but not avg_air_distance/max_air_distance; those absent fields remain null instead of being silently renamed.

`actual_capture_receipt.json` retains per-family indexed snapshots, hashes, exact columns, per-year/grain counts, per-field missingness and canonical coverage. Immutable normalized artifacts preserve rows and diagnostics. Source adapter completion claims zero catalog IDs; metric derivation is a separate package. No model, optimizer or app activation is included.
