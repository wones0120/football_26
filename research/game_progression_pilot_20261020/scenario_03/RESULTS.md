# SCENARIO-03 — official regulation-count labels

Completed 2026-10-21. Independent official team-count evidence now supports all ten fixed-smoke team sides for pass attempts, carries, targets and physical offensive plays. This is an actual-label result; it changes no forecast or source-transition support.

## Counts and scope

| Game | Team | Pass attempts | Carries | Targets | Physical plays |
| --- | --- | ---: | ---: | ---: | ---: |
| 2026_01_DEN_KC | KC | 27 | 38 | 25 | 67 |
| 2026_01_DEN_KC | DEN | 28 | 15 | 27 | 47 |
| 2026_02_MIN_CHI | CHI | 35 | 31 | 30 | 70 |
| 2026_02_MIN_CHI | MIN | 20 | 28 | 19 | 51 |
| 2026_03_SEA_WAS | WAS | 31 | 32 | 30 | 65 |
| 2026_03_SEA_WAS | SEA | 46 | 18 | 45 | 64 |
| 2026_04_LA_PHI | PHI | 27 | 27 | 25 | 58 |
| 2026_04_LA_PHI | LAR | 51 | 25 | 50 | 77 |
| 2026_05_MIN_NO | NO | 25 | 17 | 24 | 43 |
| 2026_05_MIN_NO | MIN | 30 | 36 | 29 | 68 |

Known side-label coverage increased from 6/10 passing, 6/10 rushing, 4/10 targets and 6/10 physical plays to 10/10 in each channel. DEN–KC and SEA–WAS now have independent final-team counts despite their retained PBP replay masks. MIN–CHI team targets are explicitly published as MIN 19 / CHI 30; no recipient was guessed for native plays 115 or 1713. The two unaffected matchups retain their prior v3 labels by lineage.

Three official NFL gamebooks already captured on 2026-10-15 supply the new labels. PDF hashes match their original capture receipts. Document date/team headings, original native gamecenter links and frozen schedule identity bind each to the correct game. Complete native periods 1–4, no unknown periods or overtime rows, and independently certified regulation final scores establish the regulation scope. The empty schedule overtime field and template OT score column alone were not used as proof.

Final team ATT/rushing/offensive-play counts and final individual TAR totals were inspected; receiving-table row sums match each published TAR Total, and passes+carries+sacks match physical plays. No player name was joined to any native or canonical identity. The current [evidence annotations](GAMEBOOK_EVIDENCE.json) retain PDF/source/capture/page references; [reconciliation](RECONCILIATION.json) retains both sources, original masks and native scope proofs.

## Validation and limits

33 narrow unit tests passed in 0.05s. They cover native identity/date/period mismatches, overtime, incomplete evidence, duplicate unresolved IDs, missing/nonintegral counts, conservation, PBP/official disagreement and preservation of event-level unknowns. One cached reconciliation took 0.106s under a 60s cap; it made no source requests, simulation, fit, database mutation or accuracy evaluation. See [validation receipt](VALIDATION.json) and [frozen recipe](RECIPE.md).

The alternative label record is separately identified. Original v3 manifests/checkpoint/results and all 320 smoke records are hash-verified unchanged. Original PBP event counts and replay/recipient masks are not rewritten. Official team totals do not establish unique target recipients, a post-review physical transition, any injury replacement role, simulation precision or better predictions. Source observations remain retrospective/reconstructed, not original-pregame validation.

The previously reviewed weekly component was not substituted: it explicitly masks these team aggregates because of missing-positive participant evidence. The retained FTN rows for the four remaining native plays do not supply the missing event-level proof; is_throw_away=false is not converted to a positive target.

SCENARIO-04 is the next TODO item. A later changed smoke must have a new manifest/output, declared bounds and a substantive reason, retain old records and skip unchanged known failures. SCENARIO-02 still has 140 recorded source stops and 72 censored stops unresolved; no supported full-game or accuracy claim follows from these better actual labels. High/monitors and live settings remain unchanged.
