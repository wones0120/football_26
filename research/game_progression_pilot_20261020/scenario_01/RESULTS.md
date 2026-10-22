# SCENARIO-01 — exact physical-key indexing

Completed 2026-10-21. Research runtime only; no live activation or new simulation.

`index_library(library)` builds one in-memory bucket per exact `physical_key`: field and phase, plus down/distance for scrimmage. Every source occurrence and its original order remain; uncertified candidates are retained. Context filtering, the >=8 hierarchy, cycle-ID stable sort, unknown mass and uniform selection are unchanged. No new random draws occur. `rollout` accepts existing plain libraries and indexes them once per call. Multi-path callers should index once at load and reuse that object; the v3 runner now does so. Plain `choose` retains the scan for compatibility. Treat indexed source libraries as immutable; construct a fresh index after edits. The serialized TRAIN library and recipe version are unchanged.

## Validation

- 198 targeted parser, source and event-boundary tests passed in 0.69 seconds. This also reruns the final source-metadata regression outstanding in the previous handoff.
- Tests cover all contextual tiers and control, the seven/eight threshold, stable ordering and duplicate occurrences, unknown candidate mass, special phases, missing context, unsupported keys, fixed-seed draws, full rollout equality and no subsequent full-library iteration.
- One saved-library check: 43,852 cycles, 5,011 physical keys; 256 seed-17 queries covering both arms matched the frozen pre-index scan exactly, including selected cycle, tier, pool size and unknown mass.
- Index construction: 0.0204 seconds. Scan queries: 3.7629 seconds. Indexed queries: 0.0262 seconds. Lookup speedup: 143.6x; including construction: 80.7x. Whole check: 4.127 seconds under a 60-second cap. This is a selector microbenchmark, not measured full-game throughput.

Evidence: [timing receipt](TIMING.json), [test and implementation receipt](VALIDATION.json), [bounded checker](check_index.py), [frozen scan reference](scan_reference.py). Implementation/validation elapsed time is recorded from the source baseline snapshot; initial handoff reading precedes that measured window.

## Preserved limitations and next work

Original v3 manifest, checkpoint, results, smoke summary and all 320 path records are hash-verified unchanged. The 270 finished records and 50 cap/failure placeholders remain original evidence. Old implementation hashes in the v3 manifest are intentionally preserved; its runner will reject changed code and existing outputs. Any later changed smoke needs separately identified inputs/code bindings and outputs; do not rewrite that manifest or rerun the old smoke command.

No source support, continuation model, labels, accuracy, calibration, live projections, settings or saved lineups changed. Complete supported joint-law paths remain zero in the historical smoke. SCENARIO-02 is next: investigate source-state and censored-continuation gaps using saved traces. High, monitors and paused automation remain off.
