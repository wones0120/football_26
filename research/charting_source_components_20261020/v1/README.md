# Actual FTN source acquisition and validation

The user-authorized capture ran the installed `nflreadpy.load_ftn_charting` public nflverse provider sequentially for2023–26, then appended2022 without repeating downloads. The existing `SourceCaptureService` indexed immutable source artifacts/manifests. No paid FTN API, model fit or runtime activation was used.

`actual_validated_capture_receipt.json` is the final evidence receipt. Earlier per-year capture receipts and logs preserve the initial validation findings; they are not the final availability verdict.

| Season | Immutable provider rows | Validation and native join |
|---|---:|---|
|2022|41,643|Source hash, clocks, schema and normalized native uniqueness verified; PBP join unknown because no retained2022PBP descriptor exists|
|2023|48,225|All FTN native game/play keys match the retained byte-verified PBP source|
|2024|48,031|All FTN native game/play keys match the retained byte-verified PBP source|
|2025|47,316|All FTN native game/play keys match the retained byte-verified PBP source|
|2026|13,621|All FTN native game/play keys match the indexed PBP snapshot; all9,807 prior offensive play-type keys matched|

Source URLs are the installed provider's public Parquet URLs. Immutable raw captures contain the provider dataframe's native CSV serialization; the loader does not expose original remote Parquet bytes, so their bytehash is explicitly unavailable. Capture/observed clocks are actual2026-10-20 timestamps. Provider cache freshness and original historical pregame availability remain unknown. `date_pulled` is preserved as upstream FTN API retrieval time; it is not game-time publication evidence. Existing raw source files/manifests were not changed during revalidation.

The primary [FTN dictionary](https://nflreadr.nflverse.com/articles/dictionary_ftn_charting.html) supplies a versioned interpretation contract. Native `(nflverse_game_id,nflverse_play_id)` keys join directly to PBP game/play keys. Play IDs normalize integral spelling such as1.0, with duplicates rejected after normalization; fractional IDs, conflicting season/week, future aware provider clocks and malformed boolean values reject. No display names are joined. FTN rows can include postseason weeks; regular-season eligibility comes from the matched PBP's explicit phase, not inferred from FTN week alone.

All requested boolean/read/defender-count columns are present in these captures. Per-field missingness and read-code coverage are in each final validated receipt. Primary-read code0 is interpreted only for2023onward. The unrecorded2022 primary reads remain unknown; known nonprimary codes do not fill them. One2023 raw pass-rusher count44 and one2024 count45 are physically inconsistent, preserved verbatim and mapped to explicit unknown counts rather than clipped. Drop-versus-catchability label conflicts are also counted for conservative downstream handling.

These charting facts enable later precisely scoped feature derivations; this source package itself claims zero verified catalog feature IDs. Out-of-pocket is not designed rollout, blitz count is not pressure, and play-level motion does not identify the player in motion. Source-specific catchability/contested/drop tags are measurements rather than calibrated probabilities or universal football truth. All current outputs are retrospective/nonserving; no model/optimizer connection is claimed.

The15-test gate covers native IDs/duplicates, season-specific first-read semantics, zero/false/null, invalid defender counts with original values, source clocks, real Polars nullable and Pandas providers, immutable byte verification, tamper, provider/schema bounds and postlock capture. High review is required before promoting source-derived catalog claims.
