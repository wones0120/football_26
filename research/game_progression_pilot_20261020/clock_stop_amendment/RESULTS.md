# Separate clock-stop observation-ledger amendment

Added exactly **15 source clock-stop records** to [AMENDMENT.jsonl](AMENDMENT.jsonl), without rewriting the existing observation ledger. The one cached build completed in **0.913 seconds** under a 30-second cap. [MANIFEST.json](MANIFEST.json) binds the amendment, base ledger, raw source, assessment, code and preservation hashes.

| Amendment result | Count |
| --- | ---: |
| New unique source-control observations | 15 |
| Source-reported two-minute warnings | 2 |
| Stops with unknown cause | 13 |
| Existing base-ledger rows modified | 0 |
| Native-key collisions with base ledger | 0 |
| Prior unqualified assessment marker records added | 0 of 4 |

This covers only `2023_06_NO_HOU`. It does not imply full-season raw-control coverage or add any training-kernel candidates.

## Record semantics and linkage

Every record uses `APPEND_SOURCE_OBSERVATION`, a distinct version/raw-source/native-game/play identity, and no replacement target. Provenance retains raw RDS and decoded-table hashes, native game UUID/play ID, raw table ordinal, assessment hash and base-ledger hash. Each stop links to actual preceding/following base record IDs and both sources' ordinals.

The build independently checks unique native IDs/order, absence from the base ledger, unchanged source type/deletion/review/clock/description fields, and agreement between each raw anchor and its validated base-ledger clock/order. All 15 are the same raw-only native IDs qualified by the prior feasibility assessment. Four unqualified marker cases stay in the prior assessment and are not silently promoted.

The observed quarter clock belongs to the **source control event**, not the preceding physical play's end. Half/game seconds are separately labeled arithmetic derivations from quarter and quarter clock. The two warning labels remain source-reported causes, not independent official adjudication. Other causes stay unknown.

Unknown fields remain explicit: possession, field, down/distance, scores, timeout team/budgets/debit, physical play-end clock, restart, runoff/corrections and untimed enforcement. No neighboring state, timeout charge, opportunity credit or scoring credit is copied into the new records. The amendment does not establish how long the clock remains stopped or what restarts it.

## Validation and preserved behavior

**142 tests pass in 1.10 seconds**, including 19 new amendment cases and the prior 123 focused cases. They check deterministic output, immutable inputs, exact base/native links, source conflict rejection, missing/duplicate/foreign identities, base collisions, clock/order brackets, exclusion of unqualified markers and preservation of unknown team/debit/state/policy fields. An initial test-fixture syntax error was corrected before this passing run; no production extraction had started.

Saved records and prior/runtime hashes are checked in [VALIDATION.json](VALIDATION.json). The base ledger remains 49,665 rows with its original bytes. All prior simulation results, source evidence and the 15 deferred source-state cases are preserved. No source request, RDS decode, reconstruction, fit, simulation, runtime consumer or live projection/settings change ran.

This completes the requested ledger amendment. Physical play-end clocks, restart/enforcement and generated continuation policy remain unresolved. SCENARIO-05 and live integration remain gated; adding these observations alone does not change any saved path result or justify a precision run.
