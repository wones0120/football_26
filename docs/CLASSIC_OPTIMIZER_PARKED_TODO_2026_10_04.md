# Classic optimizer TODO — parked while preparing Sunday Night Showdown
Date: October 4, 2026
Status: Classic development and strategy experiments are deferred. Sunday Night Showdown is the active priority. A material issue affecting tonight's inputs or lineup legality remains a tonight blocker; deferring Classic work does not waive it.

## Recorded progress — do not reopen without evidence of a regression

The latest handoff reports an application preparation workflow for immutable salary evidence, injury CSV evidence, sourced pregame context, starting-QB review, market/weather capture, and dependent feature/projection builds. Preparation does not generate lineups. Classic Large GPP consumes the verified prepared projection; other strategy paths retain their existing rebuild behavior.
Dependency checks run at optimizer enqueue and worker execution. Acceptance exercised the application, API, durable queue/worker, and isolated persistence using deterministic source/model fixtures. This establishes implementation behavior, not current live source freshness, prediction quality, or final entry clearance.
Source: CLASSIC_SLATE_PREPARATION_UI_HANDOFF.md, lines 3–16 and 24.

## Open TODOs


### C01 — Canonical injury evidence and final availability [P1]

- [ ] Make the distinction between injury CSV import and canonical pregame context explicit at the point of use. Implement or document a verified mapping path without confusing designation, practice, workload, starter status, and official inactives.
- [ ] Provide a timestamped, sourced final-availability check with precise unresolved-player reasons.
- Completion evidence: imported/sourced evidence can be traced into the actual selected player's eligibility/risk evaluation and saved report. Unknown clearance is never represented as passed.
- Tonight: use the existing supported sourced-evidence/manual-review path where needed; do not wait for broad automation or silently bypass a blocker.
- Source: handoff lines 6–8 and 18.

### C02 — Live unlocked-slate acceptance and format-specific preparation [P1]

- [ ] Demonstrate the implemented workflow with real inputs on an unlocked target, separately from fixture acceptance.
- [ ] Verify each format's normal UI → execution → consumed inputs → saved report path. Showdown is not certified by the Classic Large-GPP prepared-projection implementation.
- Completion evidence: native draft group, source timestamps, actual consumed source/feature/projection IDs, requested/effective controls, and honest preview/clearance status survive the normal application path.
- Tonight: check only the existing Showdown path and repair confirmed blockers narrowly; broader cross-format standardization stays deferred.
- Source: handoff lines 14, 16, and 24.

### C03 — Market and salary provenance [P2]

- [ ] Improve upstream observation/publication evidence where available; retain capture time as a separate clock.
- [ ] Preserve explicit unknown salary-publication and quote-publication freshness rather than clearing it with an import timestamp or a new filename.
- Completion evidence: freshness descriptions match source capabilities; unchanged newly observed values and recycled stale artifacts are distinguishable without weakening policy.
- Source: handoff lines 12 and 18.

### C04 — Weather review versus weather modeling [P2]

- [ ] Make it clear that weather capture is inspectable evidence but is not currently consumed by projections.
- [ ] Decide, through a separately validated change, whether weather stays a review input or becomes a model input; preserve venue/roof applicability and source terms.
- Completion evidence: reports say what was reviewed and what affected scoring, with no invented weather coefficients.
- Source: handoff lines 9 and 18.

### C05 — Reduce manual preparation friction [P2]

- [ ] Simplify supported salary/injury file selection and native draft-group confirmation.
- [ ] Keep unresolved identity and QB-starting-role decisions actionable and sourced; never silently resolve ambiguity.
- [ ] Clearly distinguish list reload, evidence capture, feature rebuild, and projection rebuild.
- Completion evidence: a user can prepare an unlocked slate through documented UI steps and understand any remaining manual action.
- Source: handoff lines 5–12 and 18.

### C06 — Contest assignment and entry-to-learning traceability [P2]

- [ ] Record actual contest profile, intended entry count, reviewed roster, intentional reuse, and submitted roster when verified.
- [ ] Reconcile actual entered lineups and results without treating an unknown submission or payout as verified.
- Completion evidence: next week's learning can distinguish generated, selected, intended, and actually entered lineups using saved identities and pregame rationale.
- Source: handoff line 18; retained follow-up from the earlier Week 3 learning discussion.

### C07 — Validate construction scoring, not historical quotas [P3 / research]

- [ ] Evaluate the accumulated marginal rewards for QB/pass-catcher pairs, opposing pass catchers, bring-backs, and game stacks on genuinely held-out slates.
- [ ] Keep RB/WR/TE FLEX alternatives, same-team QB/RB, opposing RB bring-backs, and lower-concentration constructions distinguishable.
- [ ] Broaden verified historical contests, contest metadata, pre-lock markets, and ownership/projection evidence before drawing stronger conclusions.
- Completion evidence: same-input comparisons, objective decomposition, slate-level uncertainty, and chronological validation. No bonus inferred directly from descriptive lift; no forced FLEX quota.
- Sources: CLASSIC_CONSTRUCTION_REVIEW_DECISION.md, lines 106–112 and 142; classic_historical_lineup_construction_study.md, lines 967–971.

### C08 — Portfolio dependence and selection quality [P3 / research]

- [ ] Evaluate actual game/player/core dependence, including secondary stacks, rather than relying on the QB-game label alone.
- [ ] Compare the existing sequential selection with supported joint-portfolio alternatives on common inputs and unchanged preferences.
- [ ] Validate forecast ownership and any future duplication/contest objective before treating it as an advantage.
- Completion evidence: measured tradeoffs and truthful limits; no automatic new game cap or scoring penalty and no claim of independent scenarios from captain/QB changes alone.
- Sources: CLASSIC_LARGE_GPP_READINESS.md, lines 19–29; CLASSIC_CONSTRUCTION_REVIEW_DECISION.md, lines 80, 112, and 142.

### C09 — Cross-format exclusion versus availability assumptions [P1 / parked]

- [ ] Check Classic UI, weekly-run, API and preparation consumption paths: **Exclude questionable** and **Exclude from lineups** must remain optimizer preferences and must not silently generate assume-out scenarios or redistribute football opportunity.
- [ ] Preserve independently selected explicit assumptions and sourced availability, with their source visible; do not reuse an old assumed-out projection as a verified baseline because it is latest.
- Completion evidence: focused cross-format fixtures distinguish selection-only exclusions from deliberate/sourced availability scenarios and retain model assessments, user-preference reasons and consumed lineage.
- Status: **not implemented here**. The October 4 correction was Showdown-specific; Classic implementation remains parked.
- Source: `SUNDAY_NIGHT_SHOWDOWN_FIRST_RUN_REVIEW.md`, accepted slate-identity follow-up.

## Preserve for later Classic work

The user's current planning choices are 5 lineups, 80% maximum player exposure, primary-game appearance cap 3, maximum overlap 5, maximum players per team 3, maximum players per game 5, and single TE off. These are preferences, not new universal defaults. Preserve explicit exclusions, locks, and risk choices.
The handoff's October 4, 1:36 p.m. Eastern check found Sunday Main's first lock had passed. Preserve the locked historical slate; do not backdate preparation or reinterpret a new build as a pre-lock decision. Use only applicable existing late-swap protections for actual locked entries.

## Active next task — Sunday Night Showdown

Confirm the correct native single-game slate and lock, current player-role/availability evidence, captain eligibility, and the normal application preparation path. Reuse existing Showdown policy and scenario work. Review competitive, Team A-control, and Team B-control possibilities only where supported, not as paid-entry quotas.
Captain candidates must have a credible major-scoring path, not merely unlock salary for other players. FLEX eligibility and captain eligibility remain separate. A game's highest raw scorer and the captain in its optimal salary-constrained lineup are not automatically the same question.
Do not carry Classic's team/game/overlap settings into Showdown. Do not select the user's lineup count or spending. The user initiates live preparation and optimizer runs in the UI; Codex may inspect, test, and repair verified blockers but does not privately generate or submit the portfolio.


## October 10 — Resume practical optimizer work after projection stabilization

Historical projection expansion is parked at the user's request. Retain `CLASSIC_PROJECTION_VALIDATION_REPORT.md` and its evidence for later improvement; do not make a perfect historical framework a prerequisite for focused fixes. Saved projection explanations now replay market corrections and disclose unsupported/partial/stale opportunity history. No scoring policy or production allocation default was changed.

The current C09 boundary check passes 97 optimizer-mode, Classic/Showdown questionable-preference and slate-preparation tests: preference exclusions retain projection/ceiling/role assessments and explicit user-preference reasons. This is fixture acceptance, not a claim that all UI/weekly/live consumption paths are certified. Resume remaining optimizer work from confirmed practical blockers; do not reopen individual-player projection studies without a new defect.
