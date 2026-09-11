# Projection pipeline repair — 2026-09-06

## Objective

Repair queued projections against this repository's canonical database, preserving player identity, slate scope, and time-safe training. Validate stored outputs and retry the failed run after deploying the fix locally.

## Checklist

- [x] Diagnose initial worker failure: legacy `curated_salaries` does not exist; canonical inputs are `public.curated_salary` and `target.snapshot_salary`.
- [x] Trace worker, scoring, feature generation, prediction inputs, and existing canonical adapters; inspect local data readiness.
- [x] Implement canonical salary reads and required field/identity mappings without silently broadening slate scope.
- [x] Resolve downstream incompatibilities on the actual projection path; preserve cutoff and lineage guarantees.
- [x] Add regression coverage and run targeted validation.
- [x] Restart affected local processes and retry the failed projection job; verify persisted results or record concrete remaining data prerequisites.
- [x] Update README/release notes and review focused diff.

## Resume context

- Repository: `/Users/wones/git/football_26`.
- Failed job: `be9694f0-9bd2-4d86-9819-b591474a65e5`.
- Projection run: `4c2f69d0-16ad-4e44-8aa0-61a71767ecfe`.
- Requested slice: season 2026, week 1, `WEDNESDAY_NIGHT`.
- Initial failure: `_projection_handler` in `backend/app/services/job_handlers.py` queries obsolete `curated_salaries`.
- Further legacy reads exist in `Database/features.py` and `backend/app/product_services/predictions.py`; a one-line table rename is insufficient.
- Existing worktree contains user changes and prior persisted-status implementation; preserve them.
- User has authorized this repair, worker restart, and retry. Do not infer permission to download external datasets or weaken identity/time-safety checks.

## Validation / findings

- Focused canonical/job tests: 9 passed.
- Full backend suite: 456 passed.
- The failed job's original cutoff yields 15,968 historical training rows and 63 scoring rows in a read-only dry run.
- The dry run produced 63 QB/RB/WR/TE/DST projections without any legacy salary, weekly-stat, or predictive-feature table.
- Six unresolved DraftKings salary entries and kicker rows are excluded and disclosed by the result contract.
- Job `be9694f0-9bd2-4d86-9819-b591474a65e5` completed on attempt 4 with its original run ID and cutoff.
- Target verification: `projection_run.row_count = 63`, 63 unique persisted player projections, and source lineage `public.player_game_feature_matrix`.
- Models pipeline status reports `Completed` with 63 rows and identifies this run as the latest successful selected projection.
- Continuous worker restarted with the repaired code.
