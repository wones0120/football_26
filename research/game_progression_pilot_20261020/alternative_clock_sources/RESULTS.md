# Alternative clock sources: bounded assessment

Investigated ESPN, the official gamebook, GSIS timing documentation and SportsDataIO's published schema. **No inspected source established the remaining physical play-end game clock or restart/enforcement observations.** This source-assessment task is complete; the data gaps remain unresolved.

Game-data scope stayed at `2023_06_NO_HOU`. Three public entities were captured once in **1.366 seconds** under a 45-second cap: ESPN summary, official gamebook and GSIS protocol documentation. The cached assessment took **0.578 seconds** under a separate 30-second cap. [CAPTURE.json](CAPTURE.json) preserves URLs, retrieval metadata, sizes and hashes; [ASSESSMENT.json](ASSESSMENT.json) binds findings and prior artifacts. No paid access, account changes or provider contact occurred.

| Source | Evidence inspected | Finding |
| --- | --- | --- |
| ESPN | One native event, 194 unique play records | All have a top-level clock. Their start/end objects contain field-position/down/distance data, with no end-clock field. No new restart/enforcement contract is established. |
| Official NFL/club gamebook | Same game's 18-page publication | Corroborates a runoff annotation on page 11; that annotation does not establish physical play-end clock or restart timing. |
| GSIS | Public legacy real-time clock protocol | Potential clock-stream category; archive availability and native event synchronization are unverified. Fallback clock values can be last-play-start values. |
| SportsDataIO | Public Play schema only | Documents play-occurrence time remaining and estimated/update timestamps; no distinct physical play-end/restart contract was identified in that schema. No provider sample was acquired. |

## ESPN: endpoint does not mean end clock

The captured [ESPN summary](https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event=401547477) is bound to native event `401547477`, 2023-10-15, home HOU (native team 34), away NO (native team 18). Its IDs remain in the ESPN namespace; game identity does not prove per-play NFL identity or independent data generation. No suffix-based or player-name join was applied.

The runoff example, ESPN play `4015474771890`, has a top-level clock of 1:09 and no clock within its end object. Its structured `end.distance` is 10, while the following play's `start.distance` is 20; `isPenalty` is false alongside penalty prose. This does not prove the schema is erroneous, because component/enforcement semantics are not documented here. It does show why those fields cannot be used as a fully adjudicated enforced terminal state without qualification. The saved example retains both endpoint and following-start fields; nothing is filled or repaired.

## Official gamebook: corroboration with limits

The [official publication](https://static.clubs.nfl.com/image/upload/saints/gtzghxres7u0a4bosnue.pdf) is bound by game date and both teams. Text extraction found the existing runoff annotation on page 11, but no new play-end or restart observation was qualified. Narrative agreement is useful corroboration; independence from the underlying NFL statistical feed remains unproven. No native NFL play-ID attachment or original publication chronology is inferred from that agreement. Text-only assessment did not make layout measurements or claim visual validation.

## GSIS: promising category, missing archive and synchronization

The public [GSIS protocol document](https://www.nflgsis.com/gsis/Documentation/Partners/Real-time%20Game%20Information.pdf) describes a partner clock stream and identifies source categories. Its fallback can substitute last-play-start values; nonnumeric game phases also limit clock interpretation. This legacy document was last saved in 2008. It does not establish current access, protocol compatibility or an archived 2023 stream. No feed registration or connection was attempted.

Even an available clock stream would need reliable receive timestamps, provenance/source flags, loss/duplicate accounting and links to native play-end and adjudication events. A repeated clock value alone cannot distinguish an actual stoppage from delay or fallback. Live clock capability is not historical play-end/restart evidence.

## SportsDataIO: no basis for purchasing from this inspection

The [published Play schema](https://sportsdata.io/developers/data-dictionary/nfl) identifies when a play occurred, estimates its field occurrence timestamp and records database timestamps. That inspected schema does not document the required separate end-clock/restart observations. This is a documentation-only limitation, not proof about all provider products or private feeds. No key, trial, subscription or outreach was used; the investigation does not recommend purchasing access on this evidence.

## Disposition and next evidence requirement

Stop repeating processed/static PBP lookups for these missing observations. The next useful acquisition gate is proof that an archived clock stream or separately charted timing source exists for one native game, with source semantics, completeness and synchronized play-end/control-event identity. A supplier capability statement or a game-level current-clock snapshot is insufficient. If no such source can be obtained, explicitly retain the data limitation rather than inventing timing or fitting away unknown mass.

No outreach, archive acquisition or manual charting was dispatched by this task. The separate 15-stop amendment remains intact; those observations do not resolve the central continuation gap. No new ledger rows, reconstruction, model fit, simulation, precision run or live change occurred. SCENARIO-05 remains gated.

Validation: **149 tests pass in 0.93 seconds**, including seven new source-schema/identity cases and the prior 142 focused cases. Tests reject incorrect date/home-away/event identity, duplicate/live-drive ambiguity and unsupported inference from endpoint/control field names or narrative mentions. All prior evidence and runtime hashes were verified; see [VALIDATION.json](VALIDATION.json). Primary-source interpretation references are saved in [PRIMARY_REVIEW.json](PRIMARY_REVIEW.json).
