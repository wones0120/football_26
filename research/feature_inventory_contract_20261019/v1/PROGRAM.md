# Full feature-platform coverage program

## Current implementation direction (2026-10-19 user update)

Implementation is now authorized and tracked in [the live ledger](../../feature_platform_implementation_20261019/v1/LEDGER.md). Prioritize new source/features → actual projection/Analyst/lineup consumers → reviewed app activation. Historical lineup/projection comparisons, broad ablations and tree-versus-NN tournaments are not prerequisites to delivery. Both model families remain desired useful implementations, with bounded chronological actuals/calibration checks appropriate to their claims. Preserve prior artifacts/settings/entered lineups and reversible activation, while allowing validated new-feature changes; no blind activation of incomplete/fabricated fields. The original staged coverage design below remains a record of dependencies, not an instruction to block new work on comparison exercises. Historical audits are unchanged.

All 240 catalog IDs remain in scope. The 80 [extension candidates](EXTENSIONS.md) add explicit contextual/statistical variants for review, bringing the planning library to 320 IDs; this is not a claim of 320 independent measured or useful model features. No implementation, training, purchase or source acquisition is authorized by this document.

The [per-ID roadmap](COVERAGE_ROADMAP.csv) is the authoritative coverage list. It preserves each unchanged label and owning workstream, all nine audited layers, time/quality limitations, existing variants, source/definition disposition, dependencies, proposed implementation wave and acceptance tests. Every row is planned or has an existing variant to preserve; none is silently omitted. An implemented historical or heuristic variant is not marked as a completed exact forward predictor.

## Dispositions

- `existing_measurement_or_variant`: verified local source value or existing path; the exact forward feature/consumer can still have gaps.
- `derivable`: the audit verified relevant local components, with denominator/identity/time rules still to implement or resolve.
- `source_verification_or_acquisition_needed`: local exact measurement/access is unknown. Verify existing files/products first; acquire only an identified available source under later authorization. This is not a claim that a paid vendor is required.
- `definition_needed`: intended quantity has alternatives, proxies or incomplete grain/exposure semantics. Resolve while preserving the catalog ID.
- `audit_gap`: unverified canonical coverage, consumer, clocks, samples or validation remains. Scope each gap; it is not an excuse to halt the whole program.

These dispositions can coexist. The roadmap's `existing_implemented_variant` describes code/artifact evidence and is never an end-to-end completion badge. Availability and measurement status stay separate from model quality. No metric is classified as globally/vendor-unavailable merely because the local audit did not find it.

## Workstream coverage and ownership

| Owner | All retained groups / count | Planned front-to-back scope |
|---|---|---|
| Game environment | G01,G02,G19,G20,G21 / 50 | Pace/plays/decisions, market snapshots, venue/weather and schedule, every situational split; distinguish retrospective splits from pregame conditions. |
| Quarterbacks | G03–G05 / 30 | All passing workload/effectiveness and designed/scramble/kneel rushing; exact event taxonomy and team-budget linkage. |
| Rushing and protection | G06,G07,G13 / 30 | All workload/splits, efficiency/contact and full line/protection metrics, with source-backed starters/units. |
| Receiving | G08–G10 / 30 | All target/route/air-yard opportunities, efficiency/catchability and alignment/motion/depth/contested deployment. |
| Scoring opportunities | G11,G12,G23 / 30 | Every disjoint zone count, separate goal-to-go, TD/conversion/expected scoring opportunity, kicker distance/attempts/stalls and DST opportunity channels. |
| Defense and matchups | G14–G16 / 30 | All pass/run defense components and matchup assignments/interactions; measured charting separate from broad FP proxy. |
| Availability and role changes | G17,G18,G22 / 30 | Full-team personnel/status history, verified gaps/return/replacement/restriction, form and coaching/play-caller events. Not limited to salary-listed offensive players. |
| Lineup integration | G24 / 10 | All shared events/competition/opponent response/salary/role dependence/portfolio exposure and joint ceiling estimates, with honest probability status. |

Shared foundations and definitions are owned once. For example, receiving and QB consumers reuse the same team pass/target event universe; G17/G22 reuse one snap-trend record; G13/G18 share starter identity. Related IDs remain visible but are not manufactured independent signals.

## Program waves and parallel batches

| Wave | Coverage and dependency | Deliverable and acceptance |
|---|---|---|
| **W0 — common contract and broad source/definition resolution** | Applies to every ID. Begin advanced-source checks in parallel, not after all easy features. | Canonical identity/game/team and five-clock mapping; exact formulas/units/exposures/windows; raw/curated coverage; explicit unknown/zero/proxy/conditional semantics. Each source-dependent ID gets an access/definition decision and owner, with costs/license unknown unless verified. No purchases or broad ingestion without later authorization. |
| **W1 — core opportunity, personnel and existing consumer closure** | Core pace/play/decision/pass/rush/target, current depth/status/return history, market/home and personnel continuity. Every relevant group retains advanced variants for W3/W4. | Full source universe and residuals, verified-gap/current-role count adapter, preserved original history/proxies, common evidence into standard/count paths; actual authored Analyst producer and dependent refresh through existing packet import/Prepare. Public saved result and full-roster explanation. Keep original FP/count controls. |
| **W2 — all locally supported event efficiency/scoring/defense derivations** | G04,G07,G09,G11,G12,G14,G15,G23 as supported by verified sources; counts/identity from W0/W1. Source-dependent variants remain assigned to W3, not discarded. | All specified derivable quantities with exact denominators and sample/coverage; zones and goal-to-go conserved; small yard/TD/scoring components under later modeling approval; K/DST component opportunities distinctly tracked. Each block reaches a declared forecast/Analyst/report/selection interface, or is explicitly descriptive-only pending model evaluation. |
| **W3 — advanced measurement and deployment** | Routes/first reads/alignment/motion/coverage/pressure/contact/protection/personnel packages and matchup assignments. Starts source investigation in W0; implementation follows verified access/definitions. | Extend collectors/derivations for every identified available source, with native/canonical identity, event definitions, immutable lineage, access/license receipts and coverage tests. Where genuinely blocked, retain precise blocked reason, source alternative and user decision; no invented route/pressure proxy or unauthorized fee. Complete the relevant catalog IDs, not just an exploratory source memo. |
| **W4 — context families and full-lineup integration** | Every G21 split, G20 weather/venue/schedule context, relevant role/coach changes and every G24 relationship; also extension families. Depends on available pregame conditions and earlier event/scoring blocks. | Continuous condition features plus train-defined high/low bins/interactions with shrinkage/samples; shared FP/count/Analyst world inputs; canonical candidate union; all-roster and combined-portfolio outcome assessment; final saved recommendation/policy/conflicts/alternative. All signals have one scoring ancestry; no naive vote/additive FP+count double count. Claims of calibrated joint probability require separately demonstrated calibration. |
| **W5 — model selection, validation and continuous improvement** | All available blocks, in chronological batches as they become ready. Runs alongside later coverage work under one compute-job constraint, not as a final all-or-nothing gate. | Feature-block ablations, regularization/hierarchical shrinkage, time-safe preprocessing, conditioning/role cohorts, uncertainty/calibration, source/missingness drift and complete-roster comparisons. Keep the full feature library even when a particular model excludes a redundant/unhelpful column. Record model/version/activation/rollback and explicit standard control. |

After the user's review, use at most two Medium implementation workers in parallel when operational work is idle. Split by independent ownership/output paths, not two workers editing the optimizer at once. A practical sequence is: (A) source/opportunity/availability and (B) research producer/report contract; then scoring/efficiency and defense/environment; then advanced receiving/protection/matchup acquisition adapters. One integration owner edits shared schemas/Prepare/selection sequentially after component review. High reviews definitions, source/consumer boundaries and cross-workstream conflicts. One training/compute job at a time; parallel source/code work need not create simultaneous fits.

Wave numbers are a proposed dependency order, not deadlines or evidence that later metrics are lower scope. The per-ID roadmap assigns every metric a wave and specific owner. Each wave must finish at an actual declared consumer with frozen lineage and a saved result; no permanent pile of dormant feature names.

## Coverage completion versus model inclusion

An ID is complete for the platform when its definition is resolved; source measurement or derivation and coverage are proven; current/historical availability is documented; raw/curated/feature contracts and tests exist where applicable; actual descriptive/forecast/Analyst/optimizer/report use is explicit; and its limitations are shown. A source blocked by cost/access cannot be truthfully marked implemented; keep the blocked ID and decision visible.

A candidate's **model inclusion** is a separate versioned decision. Test coherent groups and a few predeclared interactions with training-only transformations, chronological holdouts and regularization. Assess coverage and meaningful role cohorts; sparse-route/zone/returner estimates need shrinkage rather than hundreds of unconstrained weights. Revised historical sources and previously inspected outcomes remain labeled retrospective. The platform can make an honestly limited optional feature available without claiming it beats standard; default-model promotion and calibrated-probability claims need the corresponding evidence.

Every implementation wave records canonical input/source/code hashes, actual consumed fields/model/packet versions, sample/coverage/unknowns, tests, current default/opt-in policy, rollout scope and rollback. Public acceptance is Prepare → Optimize → reopen → valid native CSV plus visible full-roster assumptions/exclusions/conflicts. Existing user preferences never alter forecasts/football facts or donate excluded opportunities.
