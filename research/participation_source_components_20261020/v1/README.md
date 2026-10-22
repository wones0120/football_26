# Historical participation source adapter

Source-only package, zero catalog IDs promoted. Model, forecast, Analyst, optimizer and current-serving integration remain paused. The purpose is to replace unsupported source-absence assumptions with measured historical availability, not to claim that a field header completes a feature.

## Provider and chronology

The installed nflreadpy.load_participation0.1.5 provider uses the original nflverse release path `pbp_participation/pbp_participation_{season}.parquet`. Its installed historical bound rejects2026. Four original HTTP Parquet files for2022–25 were captured sequentially through SourceCaptureService in9.87seconds. Existing indexed source-URI inventory is checked before downloading; no prior matching snapshot existed. HTTP Date/Last-Modified/ETag/Content-Length, actual capture clocks, original bytes/SHA and loader version are retained. Network observation is not original publication or guaranteed upstream generation freshness.

The [primary provider reference](https://nflreadr.nflverse.com/reference/load_participation.html) attributes2022/earlier participation to NFL NextGenStats via nflverse and2023/onward to FTN Data via nflverse, under CC-BY-SA4.0. FTN participation is released after postseason. Current2026 is not supplied by this source contract; no historical source becomes a current fallback. Original historical publication times are unknown; these are revised post-season sources observed now.

The [primary field dictionary](https://nflreadr.nflverse.com/articles/dictionary_participation.html) describes native game/play identifiers, source possession team, personnel, participant GSIS lists and aligned source positions, pressure, throw duration, primary receiver route and coverage labels. These are different measurements: throw duration is not time to pressure; primary receiver route is not every actor's route count; personnel grouping is not an individually observed blocking assignment. The legacy NGS air-yard field is described as unavailable from2024 onward; missing source measurements remain null.

## Native validation

Native nflverse_game_id and integral play_id must be unique; supplied season/week and possession team must agree with the native game. Team alias normalization preserves original native team text. GSIS lists are parsed independently of names, reject malformed or duplicated identifiers, and produce a positional proof only when native player/position cardinality matches and any supplied participant count agrees. A player simultaneously listed on both sides invalidates both role proofs. Unknown or mismatched lists keep their original strings/lists plus explicit issues. No player alias/UUID attachment or mutation occurs here; individual canonical linkage is a later source-backed feature step.

Pressure booleans preserve true/false versus unknown; invalid counts/nonfinite measurements are not clipped or zero-filled. Normalized semantic digests omit provider row ordinal, while raw ordinal and original source fields remain available. Field presence and actual non-null measurement counts are distinct.

Source rows are not assumed REG or eligible physical snaps. For2023–25, the original retained PBP Parquet manifests/SHA/size are independently verified, and native game/play/season/week/possession checks join all participation rows exactly. PBP phase provides explicit REG/POST classification. Missing2022 PBP means its join/phase/official-eligibility remains unverified, not zero. Future metric derivation must include missing eligible PBP plays in unknown exposure and must not use all source rows as a pass/coverage denominator.

## Actual inventory

| Season | Native rows | Raw bytes | Aligned offensive/defensive position rows | Qualified PBP REG/POST |
|---|---:|---:|---:|---:|
|2022|50,150|2,941,018|0/0|unverified, no retained matching PBP|
|2023|46,168|4,700,238|46,168/46,168|44,057/2,111|
|2024|45,919|4,644,767|45,918/45,918|43,866/2,053|
|2025|45,184|4,741,443|45,184/45,183|43,049/2,135|

Actual known pressure rows by season:18,943/46,168/45,905/45,175; time-to-throw18,943/20,306/19,733/19,378; primary route18,176/19,616/19,110/18,871; man/zone and detailed coverage18,975/22,916/22,408/22,055. These are source measurement counts, not denominator-qualified catalog rates.2022 has no aligned positional proofs; missing source positions are not guessed.2024 has two side-list issue records (one offensive and one defensive proof withheld);2025 has one defensive-list issue.2023–25 have zero native game/play/phase/team join failures. Every actual snapshot ID, raw path, SHA, HTTP metadata, field count, native issue count and digest is retained in actual_receipt.json.

The original Parquet is the immutable reusable source. A compact validation receipt is published rather than duplicating every participant list into a second large JSON. Replay normalizes those verified bytes with the pinned producer. No original raw source is mutated; zero model jobs and zero alias/name joins.

## Tests and concrete next feature paths

25 targeted tests cover native scope and duplicate keys; GSIS alignment/cardinality/cross-side conflicts; unknown booleans; signed measurements; source byte/clock/hash/count contract; exact original Parquet capture/license; preservation of schema-invalid downloaded originals; current-season rejection; and exact PBP native join with phase/team/missing-key failures. Independent High source review is pending.

Concrete historical candidates now have data paths: G14-M01 native pressure on PBP-qualified dropbacks, G14-M04/M05 native man/zone coverage on declared classified coverage exposures, and X04/G13 personnel/line-continuity parents from aligned native participant positions. Each needs its own definition, unknown denominator, canonical mapping where applicable, targeted tests and actual derivation/review. G13-M05 time-to-pressure, block win rates, route/block assignment, current2026 participation and player alignment-specific matchups are not completed or proxied by these fields. No catalog count increases from this adapter alone.
