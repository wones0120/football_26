# Observed opponent team real-point distribution — X06-M10

Feature-only candidate, pending independent High review. No model, probability calibration, optimizer, Analyst, or current-serving promotion.

The measurement is `opponent_team_reported_final_score`: the other native game team's entire final scoreboard score, including its offense, defense and special teams. It is not defensive-unit-only points conceded and does not apply DST fantasy deductions. Same-season/team empirical integer-score histograms, means and population variances use one observed completed game once. Known-sample statistics are separate; any unproven game masks the complete observed-cohort statistics. Zero points are valid; unknown is never zero.

## Completion and identity contract

The original ESPN competition must explicitly report `state=post`, `completed=true`, `name=STATUS_FINAL`, with a past scheduled date, unique digit native event ID, consistent event/competition status, and exactly two native home/away team IDs. Abbreviations use the existing canonical team alias normalizer, never a player/name join. Native season/REG/week and opponent orientation must match the authenticated schedule. Nonnegative integer scores must agree with three independently retained fields: the indexed schedule pair, the indexed PBP native final-score pair and its unique native-order quiet END_GAME terminal pair. A later positive-offense row invalidates terminal corroboration. END_GAME or numeric agreement alone never establishes completion. Suspended/live/canceled/missing/conflicting statuses remain unknown. Final OT games are admitted by the same completion contract without assuming four quarters.

All completed revisions must agree; a conflict masks exactness. Equivalent repeated source facts are not extra game votes. A source game absent from the expected native schedule cohort is an error; missing expected scoreboard games remain explicit unknown scaffolds.

## Actual source and coverage

The pre-existing immutable W5 ESPN envelope was authenticated and preserved. It lacked completion for Monday, so five missing/completion result snapshots for weeks1–5 were captured sequentially through the existing SourceCaptureService. Original HTTP JSON bytes are retained for the five new captures, with real capture clocks around 2026-10-20T06:22:18–19Z. The old W5 source remains a normalized CSV envelope and is labeled separately. Publication clocks are unknown; capture is observation, not original historical publication. See `actual_receipt.json` for all indexed snapshot IDs, raw SHA/size and URI values.

Actual output: 79/79 native games completed and corroborated, 32 same-season/team observed distributions, ten games touching SF/WAS and two selected team profiles. No failed capture or normalization. Source job 2.45 seconds; zero expanded-parent loads and zero models. Full immutable artifact f1630e2e… is164,508 bytes; selected f05746ef… is21,796 bytes. Sources and outputs remain postlock descriptive, not pregame/current serving evidence; Monday's locked game itself is outside the strict prior202606 scope.

PBP source: indexed79230705-26c3-5cbd-af43-b26c9bb4e1bb (SHA56e4d82e…), schedule6a346947-eca2-5c0d-abf0-95e52ac72e5b (SHAdfc18cfa…). Both actual immutable files are verified before use. Native play IDs and native order_sequence uniqueness are validated; numeric play IDs do not establish chronology.

## Validation and remaining state

31 targeted tests pass. They cover completion/status contradictions, absent games, wrong period/identity, score types, zero/OT, independent corroboration failures, later native-order offense, conflicting revisions, equivalent recapture semantics, exact HTTP-byte capture and authenticated indexed readers. The code and immutable source/output hashes are pinned in receipt.json. Source-independent final review is pending. Historical completeness outside this observed source cohort, original historical information availability, forward probabilities and all model/app consumers remain unclaimed.
