# Direct coverage-family-conditioned historical deep passing

Candidate **G16-M05**, feature-only exact-definition checkpoint admitted by High. Completed implementation, actual artifacts and targeted tests are ready for independent source review; no catalog promotion before that verdict.

The primary [nflreadr participation dictionary](https://nflreadr.nflverse.com/articles/dictionary_participation.html) defines `defense_coverage_type` as the reported coverage type on a play, with ten literal values: `COVER_0`, `COVER_1`, `COVER_2`, `2_MAN`, `COVER_3`, `COVER_4`, `COVER_6`, `COVER_9`, `COMBO`, `BLOWN`. All ten remain distinct; no label is converted to a safety count, individual assignment, deep-zone responsibility or generic MAN/ZONE. Unknown/malformed/unsupported labels remain residual uncertainty, not another family.

The declared deep threshold is **source `air_yards >=20` on official nonspike pass attempts**. Negative and19.99air yards are nondeep; unknown/nonfinite depth stays unknown. Within each reported family, the producer measures deep-attempt opportunity fraction over that family's official attempts, same-play source completion fraction and provider target-play EPA per deep attempt. The comparison baseline pools the **other explicit classified families**, then computes family-minus-other completion/EPA. Counts/outcomes are pooled before rates in same-season/team observed profiles. This materially conditions actual deep response on observed defensive classification; no outcome-strength label substitutes for coverage.

Outputs keep offensive and opposing defensive views of the same physical event. These are two indexed perspectives, not two pass attempts. Team grain retains all native passers/receivers without canonical/player-position filtering or name joins. Missing offense/defense preserves both native game-side candidates where applicable.

Unknown membership is local to compatible cells: unknown coverage can belong to any family or its complement; unknown depth within a known family masks that family's deep response and other families' complement. Known nondeep events cannot add deep-outcome uncertainty but can still make opportunity denominators uncertain under unknown coverage/eligibility. Completion and EPA missingness are separate. Exact full-cell values/contrasts remain null under applicable uncertainty; known-depth and known-outcome samples are separately named. Missing native-source games retain explicit cohort uncertainty. Empty/deep-zero cells have undefined response ratios, not zero efficiency. Residual category uncertainty enters each selected/complement comparison ONCE, not once per possible family.

## Source and chronology

The serial runner authenticates the current High-reviewed native official-attempt parent, its managed byte/semantic hashes, producer/helper ancestry and actual creation/publication bound. Native game/play/season/week/possession keys join the same original retained PBP bytes and indexed original participation Parquets. The additional PBP projection contains only native keys/period/sides/air depth; it does not reconstruct eligibility or replace the reviewed nonspike attempt definition. Every possible attempt in that parent has exactly one matching PBP depth row. Existing nonattempt rows are outside the declared parent universe, not silently missing attempts.

Some participation rows omit native phase; the exact same-key authenticated PBP supplies explicit REG. Source POST conflicts remain unknown, with raw participation phase retained. The reader never treats absent phase alone as REG. Expected games and response periods remain strictly before the inherited202607boundary.

Per the primary [source reference](https://nflreadr.nflverse.com/reference/load_participation.html),2023–25participation is FTN Data via nflverse under CC-BY-SA4.0, released after postseason. The actual source captures/read clocks are2026; original historical pregame availability is unknown. No current2026participation fallback, historical contemporaneous-input claim, future-coverage selection, trained model, calibration, causal advantage or full-game-completeness claim is made. Provider EPA is revised historical model output; its original model-vintage availability is not established.

## Actual measured coverage

One serial existing-source job completed in9.009seconds. Each season contains544native REGteam-games/32team profiles:

| Season | Known classified deep events | Unknown possible deep events | Exact offensive game/family EPA and completion contrasts | Exact observed team/family contrasts | Known-sample game EPA contrasts |
|---|---:|---:|---:|---:|---:|
|2023|2,139|42|1,188|88|1,297|
|2024|2,029|21|1,117|142|1,169|
|2025|1,998|17|1,228|153|1,257|

These are **family-cell contrasts**, not that many independent games or new catalog IDs. Missing/empty families remain visible; rare `BLOWN` coverage is not fabricated in2025. Full artifacts are approximately27–28MB/season; SF/WAS selected artifacts are exact native team slices with independently identified semantics. Actual refs, byte hashes, source snapshots/manifests, known-family counts and coverage are in `actual_receipt.json` and each artifact's provenance.

Nineteen focused tests pass. They cover20/19.99/negative/missing depth, all literal categories includingCOMBO/BLOWN, unsupported labels, exact versus sample cells and complement masks, unknown eligibility, distinct outcome missingness, empty/zero exposure, missing participation/game/side, native phase/period/key/side consistency, duplicate/missing measurements, count-pooled multi-game responses and immutable-parent/future-publication guards.

There were zero source downloads, parent inflations, alias reads/updates, database writes, fits or model/optimizer/serving changes. Existing source and feature modules remain pinned and unchanged.
