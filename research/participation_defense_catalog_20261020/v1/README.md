# Historical participation defense catalog

Feature-only candidates G14-M04/M05, pending independent review. G14-M01 remains an explicitly measured native pressure-field variant with catalog value null; the complete pressure event taxonomy is not established. No models, current2026 fallback, forward matchup probabilities or serving activation.

## Definitions

The physical opponent dropback is the union of official pass, sack, or official rush with scramble; count one event once, exclude explicit spikes, nullified plays and two-point attempts. All opposing passers remain in the native team-grain denominator. There is no canonical player, position, salary or role filter. Native missing eligibility/sides/flags is not a negative event. The same reviewed native live-class and administrative eligibility contract used in the fumble source adapter is applied to the retained original PBP rows, preserving absent versus explicitly null no_play.

G14-M04 is native MAN_COVERAGE dropbacks divided by CLASSIFIED eligible dropbacks; M05 is native ZONE_COVERAGE over the same classified denominator. The primary [participation dictionary](https://nflreadr.nflverse.com/articles/dictionary_participation.html) identifies the source man/zone field. An authenticated category scan found only those two literal values plus null/empty in these source vintages. Detailed COVER_x is never interpreted as man/zone. The producer also explicitly separates known mixed/other labels, unsupported category text and unclassified residuals; it does not define zone as one minus man. Known-classified-sample fractions are separate from exact classified fractions when class membership is uncertain. Full-eligible fractions use their own denominator and remain null under unclassified/missing/unknown exposure.

A present, explicitly unclassified label is outside the classified denominator and is retained in the residual. A missing native participation row, conflicting source team/phase, unsupported nonempty label or eligible-side uncertainty may hide classified membership, so exact classified rates are masked while known samples remain visible. The whole verified PBP cohort supplies exposure, not just the source's delivered rows. POST rows and nonprior periods are excluded explicitly.

Native was_pressure is counted once where known; missing values remain unknown. If a sourced sack has was_pressure=False, the two original fields remain visible and the qualified outcome is unknown, never repaired by OR-ing a sack into the source label. [FTN's source field catalog](https://ftnfantasy.com/ftn-data-nfl-catalog) labels quarterback pressure, but does not enumerate complete hurries/hits/sacks membership. The newer NFL NGS pressure-probability definition must not be transplanted onto FTN or older NGS flags. Consequently M01's catalog_value is deliberately null even if its named native-bool rate can be measured; it receives no full-ID promotion.

## Actual source and coverage

The High-reviewed participation source adapter independently verified four original immutable Parquets and all modern native game/play/phase/team joins. This package uses2023–25 only;2022 has no retained matching PBP and is not filled in. Each original PBP manifest's byte SHA/size is reverified; each indexed participation source is verified through SourceCapture and its normalized semantic digest must match the reviewed receipt. FTN2023+ participation is published after postseason under CC-BY-SA4.0. Actual capture/read/derive/publication clocks are2026 retrospective clocks; original contemporaneous information availability is unknown. Historical source rows never become current2026 input proof.

| Season | REG defense-games | Known nonspike dropbacks | Unknown eligibility | Classified (man/zone) | Unclassified | Exact classified rates per ID |
|---|---:|---:|---:|---:|---:|---:|
|2023|544|20,686|19|20,603 (8,493/12,110)|83|534|
|2024|544|20,107|17|20,063 (9,693/10,370)|44|534|
|2025|544|19,731|11|19,713 (6,072/13,641)|18|537|

Actual missing participation exposure rows5/4/6 remain unknown; zero source phase/team conflicts. Source pressure counts6,103/6,209/5,875 are named measured lower bounds after one sack/negative-pressure contradiction in2023 and one in2024 were withheld; this does not establish full pressure taxonomy. Each year has34 SF/WAS selected game-side rows. Immutable full/selected artifacts, sizes, semantic hashes and source references are in actual_receipt.json. No download, expanded event-parent load, database write, canonical alias change or model.

## Validation and remaining scope

11 tests cover class versus full-eligible denominators, explicit mixed/other/unclassified residuals, missing source versus present unclassified labels, no COVER_x inference, pressure taxonomy non-promotion, sack contradictions/original field preservation, scramble/sack union and exclusions, unknown eligibility/team, source phase/team conflicts, strict prior REG and full-passer inclusion, duplicate native keys, pooled counts and input-order invariance. Exact classification awaits High.

Concrete next supported historical paths: G13-M01 observed initial offensive-line identity continuity and X04-M05 personnel continuity can use aligned native C/G/T participant lists plus native PBP order/eligibility. This does not identify left/right tackle from generic T, establish pregame expected starters, individually assign blockers/routes, establish time-to-pressure, or measure block win rates. Those definitions and source gaps remain separate. Forecast, Analyst, optimizer, UI and model consumers are pending under the feature-only priority.
