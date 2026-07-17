# Next Steps Implementation Plan

Created: 2026-06-07

## Purpose

This plan is written for a lower-cost implementation pass. Code until every goal below is complete, then stop and report the final status. Keep changes minimal and preserve existing repository style.

## Repo Guardrails

- Do not join player records by raw display name alone.
- Do not change lineup, ingest, or identity behavior outside the tasks below unless required by tests.
- Do not introduce new dependencies.
- Prefer narrow API helpers, typed response models, and existing UI patterns in `ui/src/App.tsx`.
- Keep generated benchmark artifacts under `docs/benchmarks/<timestamp>/`.
- Update documentation only where it helps future runs understand the new workflow.

## Current State Summary

- `scripts/run_benchmark_suite.py` already runs the canonical benchmark stack and writes timestamped artifacts.
- `scripts/compare_benchmark_runs.py` already writes `delta_vs_previous.md` and `delta_vs_previous.json`.
- Backend lineup backtests already accept:
  - `showdown_captain_model_path`
  - `showdown_captain_prior_strength`
  - `classic_value_driver_model_path`
  - `classic_value_driver_prior_strength`
  - `matchup_outcome_model_path`
  - `matchup_outcome_prior_strength`
  - `matchup_prior_gate_model_path`
- UI state currently hardcodes several model paths and prior strengths in `ui/src/App.tsx`.
- `docs/TODO.md` lists the immediate open work:
  - productionize showdown defaults
  - one-click benchmark suite
  - current model card
  - report/artifact access from UI

## Definition Of Complete

The implementation is complete when:

1. Normal showdown backtests use the captain model default path and `0.35` prior strength without manual user entry.
2. Normal classic backtests use the current classic value/matchup defaults without manual user entry, while still allowing overrides.
3. The UI can trigger the canonical benchmark suite and show completion status plus artifact links/paths.
4. The UI lists recent benchmark/report artifacts from `docs/benchmarks`.
5. The UI has a compact Current Model Card summarizing active defaults, latest benchmark metrics, and artifact locations.
6. Targeted backend tests and UI build pass.

## Goal 1: Centralize Model Defaults

### Objective

Move product defaults out of ad hoc UI state and into one backend-visible configuration source.

### Implementation Targets

- `backend/app/config.py`
- `.env.example`
- `backend/app/schemas.py`
- `backend/app/api/routes.py`
- `ui/src/api.ts`
- `ui/src/App.tsx`

### Required Defaults

- `showdown_captain_model_path`: `docs/showdown_captain_model_2024_2025.json`
- `showdown_captain_prior_strength`: `0.35`
- `classic_value_driver_model_path`: `docs/main_slate_value_driver_analysis_2024_2025.json`
- `classic_value_driver_prior_strength`: `0.45`
- `matchup_outcome_model_path`: `docs/matchup_outcome_intelligence_2024_2025.json`
- `matchup_outcome_prior_strength`: `0.15`
- `matchup_prior_gate_model_path`: `docs/matchup_prior_gate_20slates_5000.json`

### Suggested Shape

- Add settings fields in `Settings`.
- Add a response model such as `ModelDefaultsResponse`.
- Add a read-only API endpoint such as `GET /api/model/defaults`.
- Load defaults in the UI on startup and use them to initialize lineup controls.
- Keep override controls visible, but add a simple reset-to-defaults action.

### Acceptance Criteria

- `GET /api/model/defaults` returns all default paths and strengths.
- A showdown run submitted from the UI includes captain model path and `0.35` prior strength by default.
- A classic run submitted from the UI includes classic value, matchup outcome, and gate defaults by default.
- Empty default paths do not crash the UI; they should disable the corresponding prior payload cleanly.

## Goal 2: Add Benchmark Suite API

### Objective

Let the control plane run the existing benchmark suite without leaving the UI.

### Implementation Targets

- `backend/app/schemas.py`
- `backend/app/api/routes.py`
- A new small service module is acceptable, for example `backend/app/services/benchmarks.py`.
- `scripts/run_benchmark_suite.py` should remain the source of truth for benchmark execution.

### Suggested Shape

- Add request/response schemas:
  - `BenchmarkSuiteRunRequest`
  - `BenchmarkSuiteRunResponse`
  - `BenchmarkArtifactResponse`
- Add `POST /api/benchmarks/run-suite`.
- The endpoint should invoke `scripts/run_benchmark_suite.py` with `subprocess.run`.
- Use `sys.executable` and `Path(__file__).resolve()` style path construction.
- Capture stdout/stderr and return a failed response instead of exposing a raw traceback.
- Include the run directory and known artifact paths in the response.
- After a successful suite run, run `scripts/compare_benchmark_runs.py` for the latest two benchmark folders when possible.

### Default Request Values

- `source_system`: `draftkings`
- `season_start`: `2024`
- `season_end`: `2025`
- `lineups_per_slate_classic`: `1000`
- `lineups_per_slate_showdown`: `1000`
- `lineups_per_slate_showdown_ab`: `2500`
- `training_window_slates`: `24`
- `min_training_slates`: `4`
- `min_training_rows`: `2000`
- `ab_min_training_slates`: `2`
- `ab_min_training_rows`: `500`
- `learned_only`: `true`
- `random_seed`: `42`
- `limit_slates`: `0`
- `quiet_progress`: `true`

### Acceptance Criteria

- Calling the endpoint with a smoke request using small limits creates a new `docs/benchmarks/<timestamp>/` folder.
- Response includes status, run directory, summary markdown path, manifest path, log path, and any delta report paths.
- Failed subprocess runs return `status="failed"` and include a readable error message plus log path if available.
- Existing CLI behavior still works.

## Goal 3: List Benchmark Artifacts

### Objective

Expose recent benchmark and report artifacts so the UI can show what exists without manual filesystem navigation.

### Implementation Targets

- `backend/app/schemas.py`
- `backend/app/api/routes.py`
- Benchmark service module if created in Goal 2
- `ui/src/api.ts`
- `ui/src/App.tsx`

### Suggested Shape

- Add `GET /api/benchmarks/runs?limit=10`.
- Scan `docs/benchmarks` for folders containing `suite_manifest.json`.
- Return newest folders first.
- Include status, started/finished timestamps when present, config, and artifact paths from the manifest.
- Include whether these files exist:
  - `summary.md`
  - `delta_vs_previous.md`
  - `classic_backtest.json`
  - `showdown_backtest_baseline.json`
  - `showdown_captain_ab.json`
  - `main_slate_value_driver_analysis.md`
  - `run.log`

### Acceptance Criteria

- UI can list at least the existing folders under `docs/benchmarks`.
- Missing files display as unavailable, not as broken links.
- The latest run is easy to identify.

## Goal 4: Add Current Model Card

### Objective

Give the operator a single at-a-glance summary of current model defaults and latest benchmark quality.

### Implementation Targets

- `ui/src/App.tsx`
- `ui/src/styles.css`
- `ui/src/api.ts`
- Backend artifact/default endpoints from prior goals

### UI Content

Show a compact section near the lineup backtest controls with:

- Active source system.
- Active season range.
- Showdown captain model path and prior strength.
- Classic value model path and prior strength.
- Matchup model path, prior strength, and gate model path.
- Latest benchmark run folder.
- Latest classic mean/median gap when available.
- Latest showdown mean/median gap when available.
- Latest captain A/B win rate and mean gap lift when available.
- Links or path labels for summary, delta, and run log artifacts.

### Acceptance Criteria

- The card renders with existing benchmark fixtures already in `docs/benchmarks`.
- If no benchmark folders exist, it renders an empty state without crashing.
- Values update after running the benchmark suite from the UI.

## Goal 5: Add UI Benchmark Controls

### Objective

Make one-click benchmark execution possible from the control plane while preserving existing manual lineup backtest controls.

### Implementation Targets

- `ui/src/App.tsx`
- `ui/src/api.ts`
- `ui/src/styles.css`

### Suggested UI Behavior

- Add a benchmark section near `Lineup Backtests (Optimal vs Predicted)`.
- Include a "Run Benchmark Suite" button.
- Include optional smoke controls:
  - `limit_slates`
  - classic lineups per slate
  - showdown lineups per slate
  - showdown A/B lineups per slate
- Disable the button while running.
- Show status, errors, run directory, and artifact paths after completion.
- Refresh the benchmark run list after a successful run.

### Acceptance Criteria

- Button calls `POST /api/benchmarks/run-suite`.
- UI displays success/failure and artifact paths.
- UI remains usable during long runs and does not lose existing lineup backtest results.

## Goal 6: Tests And Validation

### Required Checks

Run the narrowest checks first:

```bash
source .venv/bin/activate
pytest backend/app/tests
```

```bash
cd ui
npm run build
```

For benchmark endpoint smoke validation, use a tiny run to avoid long execution:

```bash
source .venv/bin/activate
python scripts/run_benchmark_suite.py \
  --source-system draftkings \
  --season-start 2024 \
  --season-end 2025 \
  --lineups-per-slate-classic 120 \
  --lineups-per-slate-showdown 120 \
  --lineups-per-slate-showdown-ab 150 \
  --limit-slates 2 \
  --analysis-limit-slates 2 \
  --quiet-progress
```

Then compare latest benchmark folders if at least two exist:

```bash
source .venv/bin/activate
python scripts/compare_benchmark_runs.py
```

### Validation Expectations

- Existing backend tests pass.
- UI TypeScript build passes.
- Benchmark smoke run writes a manifest, summary, run log, and JSON outputs.
- Latest benchmark list endpoint sees the smoke run.
- Current Model Card shows latest smoke metrics.

## Suggested Implementation Order

1. Add backend settings and `GET /api/model/defaults`.
2. Wire UI defaults loading and reset-to-defaults behavior.
3. Add benchmark service helpers for path scanning and subprocess execution.
4. Add `POST /api/benchmarks/run-suite`.
5. Add `GET /api/benchmarks/runs`.
6. Add UI API types and functions for defaults and benchmark endpoints.
7. Add Current Model Card.
8. Add Benchmark Suite UI controls and recent artifact list.
9. Run backend tests.
10. Run UI build.
11. Run benchmark smoke validation if local data and runtime are available.
12. Update `README.md`, `docs/TODO.md`, and `RELEASE_NOTES.md` only after behavior is implemented.

## Do Not Do In This Pass

- Do not retrain models.
- Do not alter lineup scoring math.
- Do not change player identity matching rules.
- Do not add new database tables unless a clear persistence requirement emerges.
- Do not add authentication or background job infrastructure.
- Do not refactor the whole UI into multiple components unless the file becomes unworkable.

## Final Report Requirements For Implementing Model

When implementation is complete, report:

- Files changed.
- Which goals are complete.
- Which validation commands passed.
- Whether benchmark smoke validation was run.
- Any remaining risks, especially long-running benchmark behavior or unavailable local data.
