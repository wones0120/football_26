# football_26

Phase 1 foundation for a DFS data platform:

1. Multi-source ingestion (DraftKings/FanDuel CSVs + nflreadpy bootstrap).
2. Canonical player identity using `player_master_id`.
3. Deterministic matching + unresolved queue for manual repair.
4. Postgres-first schema with SQL migrations.
5. API layer to trigger loads and resolve issues.

## Quick Start

1. Create a virtualenv and install dependencies.
2. Copy `.env.example` to `.env` and set Postgres credentials.
3. Start PostgreSQL.
4. Run migrations.
5. Start API.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
./start_postgres.sh
python scripts/apply_migrations.py
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Fresh database reset (recommended when coming from legacy schemas):

```bash
python scripts/recreate_database.py
python scripts/apply_migrations.py
```

If you see `UndefinedTable` errors (`ingest_run` / `unresolved_player_queue`), the app is pointed at a DB without schema. Run migrations and restart API. In development, `AUTO_CREATE_TABLES=true` also auto-creates missing tables at startup.

If `POST /api/ingest/nflreadpy/bootstrap` fails with `No module named 'nflreadpy'`, re-activate the venv and reinstall dependencies:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

UI shell:

```bash
cd ui
npm install
npm run dev
```

## CSV Validation Gates

Salary and injury CSVs are validated before any existing curated slice is cleared or new raw/curated rows are written.

- Salary files require source player ID, player name, team, position, and a positive integer salary.
- Injury files require player name, team, position, and an injury-status column. Native player ID is used when present; otherwise identity validation uses normalized name plus team and position. Blank injury-status values are allowed for unlisted/healthy players.
- Team defenses normalize `D`, `DEF`, `Defense`, `D/ST`, and `DST` to `DST`. After an exact native source-ID match, defenses resolve only through a unique same-source team-defense alias or unique team DST master; defense display names are never used as a fallback.
- Duplicate player identities, missing required columns, blank required identity values, empty files, and invalid salaries fail the ingest with source CSV row numbers in the error.
- Failed validation remains traceable as a failed ingest run, while the last valid curated slice is preserved.

## Unresolved Queue Triage

- `GET /api/unresolved/triage` returns exact open and recent unresolved totals grouped by source system, source table, season, week, and slate.
- `lookback_hours` defines the trailing window for “new” unresolved records and defaults to 24 hours.
- The UI section `Automated Triage by Source / Week / Slate` refreshes after ingestion and resolution actions, ranking groups by recent count, open volume, and recency.
- The detailed repair queue remains available below the grouped report for create-or-link resolution.

## Data Freshness

- `GET /api/coverage/freshness` checks the selected source, season, week, and slate for curated salaries/injuries plus nflreadpy schedules/weekly stats.
- Each dataset reports its exact slice row count, latest load time, age in hours, staleness threshold, and `fresh`, `stale`, or `missing` status.
- Thresholds are 24 hours for salaries, 12 hours for injuries, and 168 hours for schedules and weekly stats.
- The UI section `Data Freshness` refreshes when the selected slice changes and after ingest actions.

## API Endpoints (Initial)

1. `POST /api/ingest/salaries`
2. `POST /api/ingest/injuries`
3. `POST /api/ingest/nflreadpy/bootstrap`
4. `POST /api/ingest/nflreadpy/schedules`
5. `POST /api/ingest/nflreadpy/weekly-stats`
6. `GET /api/ingest/runs`
7. `GET /api/coverage/season`
8. `GET /api/unresolved`
9. `POST /api/unresolved/{unresolved_id}/resolve`
10. `POST /api/player-master/upsert`
11. `GET /api/health`
12. `GET /api/model/defaults`
13. `GET /api/benchmarks/runs`
14. `POST /api/benchmarks/run-suite`
15. `GET /api/benchmarks/runs/{run_name}/artifacts/{artifact_name}`
16. `GET /api/unresolved/triage`
17. `GET /api/coverage/freshness`

## Migration Notes

Migrations live in `/migrations`. The migration runner tracks applied files in
`schema_migrations`.

With `DATABASE_URL` pointed at an empty PostgreSQL database, run the same
fresh-schema check used by CI:

```bash
python scripts/check_schema_drift.py \
  --apply-migrations \
  --require-empty \
  --verify-idempotency
```

The check validates contiguous migration names, the exact migration ledger, a
second no-op migration pass, and structural agreement between the 18 migrated
tables and SQLAlchemy metadata (columns, PostgreSQL types, nullability, primary
keys, unique constraints, foreign keys, and indexes). It does not use
`AUTO_CREATE_TABLES`.

`.github/workflows/schema-smoke.yml` runs this command against a fresh
PostgreSQL 16 service whenever migration- or schema-related files change.

## Critical-Path Integration Test

Run the deterministic ingestion-to-backtest check with:

```bash
PYTHONPATH=. python -m pytest -q \
  backend/app/tests/test_critical_path_integration.py
```

The test mocks only the external `nflreadpy` boundary. It uses one real
database session to bootstrap canonical players, ingest weekly stats, ingest a
DraftKings salary CSV into raw and curated layers, resolve both source identity
systems, and score a week-three backtest from week-one and week-two history.
Historical injury and ownership data are not required.

## Current Status

1. Phase 1 baseline is implemented.
2. Model defaults are exposed from the backend and consumed by the UI lineup backtest controls.
3. The UI now includes a Current Model Card plus benchmark-suite execution and recent benchmark artifact visibility.
4. Selected-slice data freshness is available through the API and ingestion control plane.
5. Classic walk-forward scoring learns from value-driver and game-environment lineup features.
6. See `/Users/wones/git/football_26/docs/phase_plan.md` for the build sequence.

## Benchmark Control Plane

- `Current Model Card` shows the active model paths and strengths plus metrics and artifact links from the latest successful benchmark with comparable metrics.
- New benchmark runs attach deterministic nonparametric percentile bootstrap intervals to classic/showdown mean and median gaps plus captain A/B win-rate and gap-lift metrics. Defaults are 2,000 samples at 95% confidence, with seed, sample count, standard error, and bounds stored in the artifacts.
- `--bootstrap-samples` and `--confidence-level` override the defaults for CLI runs; the benchmark API accepts matching fields and records them in `suite_manifest.json`.
- `Reset To Defaults` restores the backend-configured model settings listed in `.env.example`.
- `Run Benchmark Suite` runs the canonical classic/showdown stack and writes a unique folder under `docs/benchmarks`.
- `Analysis & Reports` opens the latest JSON/Markdown outputs and downloads a ZIP containing all available benchmark artifacts plus `suite_manifest.json` as the exact config snapshot.
- Benchmark run history defaults collapsed and can be filtered by source, status, overlapping season range, classic/showdown track, or any model-config value.
- Heavy operational tables default collapsed with compact summaries: unresolved triage/repair, curated salary slices, season coverage, recent ingest runs, and benchmark history. Simulation and backtest result tables remain directly available in horizontally scrollable containers.
- Benchmark execution currently runs synchronously through the API, so full-history suites can keep the request open for several minutes.

### Nightly Benchmark Automation

`.github/workflows/nightly-benchmarks.yml` runs the canonical DraftKings 2024-2025 suite every day at `09:17 UTC` and also supports manual dispatch with optional slate limits. It compares a successful run with the latest earlier successful manifest, uploads the complete run directory for 30 days, and applies local retention of 14 successful plus 7 failed nightly runs.

The job intentionally targets a self-hosted runner because meaningful benchmarks require the populated historical database. Before enabling the schedule:

1. Register a self-hosted Actions runner version `2.327.1` or newer with the `football-26-data` label.
2. Add the repository secret `NIGHTLY_DATABASE_URL` with read access to the benchmark database.
3. Keep the runner workspace persistent; checkout uses `clean: false` so prior nightly artifacts remain available for delta comparison and bounded cleanup.

Local cleanup is restricted to directories with a valid `.nightly-benchmark.json` workflow marker and a strict nightly run name. Manual and tracked benchmark directories, malformed markers, and symlinks are never selected. Preview the policy without deleting anything:

```bash
python scripts/manage_benchmark_retention.py prune \
  --keep-successful 14 \
  --keep-failed 7
```

The workflow supplies `--apply`; local operator use remains dry-run by default.

## Backtest Scripts

1. Classic slates:

```bash
source .venv/bin/activate
python scripts/run_optimal_vs_predicted_lineups.py \
  --source-system draftkings \
  --season-start 2024 \
  --season-end 2025 \
  --slate-type classic \
  --lineups-per-slate 600 \
  --training-window-slates 24 \
  --min-training-slates 2 \
  --min-training-rows 500 \
  --learned-only
```

2. Showdown slates:

```bash
source .venv/bin/activate
python scripts/run_optimal_vs_predicted_showdown.py \
  --source-system draftkings \
  --season-start 2024 \
  --season-end 2025 \
  --lineups-per-slate 600 \
  --training-window-slates 24 \
  --min-training-slates 2 \
  --min-training-rows 500 \
  --learned-only
```

3. Matchup outcome prior strength sweep:

```bash
source .venv/bin/activate
python scripts/run_matchup_outcome_prior_strength_sweep.py \
  --source-system draftkings \
  --season-start 2024 \
  --season-end 2025 \
  --lineups-per-slate 1000 \
  --training-window-slates 24 \
  --min-training-slates 2 \
  --min-training-rows 500 \
  --limit-slates 20 \
  --strengths 0.15,0.25,0.35,0.5,0.65
```

The latest 20-slate sweep selected `matchup_outcome_prior_strength=0.15`, improving mean actual-optimal gap by `5.47` points across 18 paired classic slates. Treat this as a backtested setting, not a hardcoded rule; rerun the sweep after changing feature logic, matchup intelligence, or lineup generation.

A higher-sample 5,000-lineup validation using the same `0.15` prior improved mean gap by `4.65` points across 18 paired classic slates. The UI classic lineup backtest controls expose the matchup outcome model path and prior strength so this setting can be tested without editing code.

4. Matchup prior help/hurt diagnostics:

```bash
source .venv/bin/activate
python scripts/analyze_matchup_prior_help.py \
  --input-json docs/matchup_outcome_prior_strength_sweep_20slates_5000.json \
  --source-system draftkings \
  --output-json docs/matchup_prior_help_diagnostics_20slates_5000.json \
  --report-md docs/matchup_prior_help_diagnostics_20slates_5000.md
```

The diagnostic report separates future-safe slate context, such as totals/spreads and salary-pool structure, from outcome-only explanations, such as actual low-salary breakouts. Only future-safe diagnostics should be considered for production gating.

5. Matchup prior gate training:

```bash
source .venv/bin/activate
python scripts/train_matchup_prior_gate.py \
  --diagnostics-json docs/matchup_prior_help_diagnostics_20slates_5000.json \
  --thresholds=-12,-8,-4,0,2,4,6,8,10,12 \
  --output-json docs/matchup_prior_gate_20slates_5000.json \
  --report-md docs/matchup_prior_gate_20slates_5000.md
```

The current-code 20-slate comparison has mean gaps of `133.46` with no matchup prior, `128.76` with always-on `0.15`, and `127.24` with the gated prior. The gate is experimental and should be validated on broader slates before treating it as production logic.

6. Classic learned-feature ablation:

```bash
source .venv/bin/activate
python scripts/run_classic_feature_ablation.py \
  --source-system draftkings \
  --season-start 2024 \
  --season-end 2025 \
  --lineups-per-slate 200 \
  --training-window-slates 8 \
  --min-training-slates 2 \
  --min-training-rows 200 \
  --limit-slates 12 \
  --output-json docs/classic_feature_ablation.json
```

Classic lineup models now learn nine pregame-only value-driver fields covering projected salary value, high-total exposure and coverage, RB spread/underdog context, and FLEX position. The existing game-environment group covers QB game totals, spreads, implied totals, and stack interactions; opponent-adjusted rolling context also feeds the player projection layer.

The ablation command reruns the same walk-forward slices and seed with each feature group disabled. Positive `mean_gap_contribution_points` means the full feature set produced a smaller actual-optimal gap. A 12-slate wiring validation produced 10 scored pairs with contributions of `+0.29` points for value drivers and `+2.26` for game environment. Treat those small-sample results as implementation validation, not production parameter evidence.

7. Classic parameter sweep:

```bash
source .venv/bin/activate
python scripts/run_classic_parameter_sweep.py \
  --source-system draftkings \
  --season-start 2024 \
  --season-end 2025 \
  --candidate-lineups 150,250 \
  --training-windows 4,8 \
  --top-target-percentiles 95,98 \
  --min-training-slates 2 \
  --min-training-rows 200 \
  --min-completed-rate 0.75 \
  --limit-slates 12 \
  --output-json docs/classic_parameter_sweep_12slates.json \
  --best-config-json docs/classic_best_config_12slates.json
```

The initial eight-configuration sweep selected `250` candidate lineups, a `4`-slate training window, and a `95th`-percentile top-lineup target. It completed 10 of 12 chronological slates with a `134.43` mean gap and `131.11` median gap. The compact best-config artifact includes the clean code revision, feature-set hash, seed, coverage requirement, and acceptance metrics. This is a provisional bounded result; rerun over broader history and larger candidate pools before adopting it as a production default.

## Showdown Availability Candidate

Showdown captain training can build an opt-in teammate-availability candidate without changing the baseline default:

```bash
source .venv/bin/activate
python scripts/train_showdown_captain_archetype_model.py \
  --source-system draftkings \
  --season-start 2024 \
  --season-end 2025 \
  --feature-set availability \
  --dataset-csv /tmp/showdown_availability_dataset.csv \
  --eval-json /tmp/showdown_availability_eval.json \
  --model-json /tmp/showdown_availability_model.json \
  --report-md /tmp/showdown_availability_report.md
```

The feature set includes active salary-pool skill-player counts and imbalance plus injury/out context when the selected historical slice contains an injury snapshot. The current 41-slate dataset has zero historical injury-report coverage. Its availability candidate scored `30.3%` top-1 and `51.5%` top-2 versus the current-code baseline at `33.3%` and `57.6%`, so the production captain artifact and baseline training default remain unchanged. The rejected candidate remains documented, but no historical injury ingestion is assumed.

Historical injury ingestion is no longer on the critical path. The injury-free replacement derives missing opportunity from prior carries/targets and current salary-pool membership:

```bash
source .venv/bin/activate
python scripts/train_showdown_captain_archetype_model.py \
  --source-system draftkings \
  --season-start 2024 \
  --season-end 2025 \
  --feature-set continuity \
  --dataset-csv docs/showdown_captain_continuity_dataset_2024_2025.csv \
  --eval-json docs/showdown_captain_continuity_eval_2024_2025.json \
  --model-json docs/showdown_captain_continuity_model_2024_2025.json \
  --report-md docs/showdown_captain_continuity_eval_2024_2025.md
```

The continuity candidate uses the prior four team games and suppresses missing-usage signals below 50% identity coverage. With unresolved current salary players included in the coverage denominator, it scored `27.3%` top-1 and `51.5%` top-2 versus the refreshed baseline at `33.3%` and `57.6%`. It remains available for research and role-shock scenarios but was rejected as a standalone captain feature set; production defaults are unchanged. Further injury/ownership-independent work is ranked in `docs/NEXT_IDEAS.md`.

## Showdown Captain Drift

Run season-segment captain-prior monitoring with:

```bash
source .venv/bin/activate
python scripts/analyze_showdown_captain_drift.py \
  --dataset-csv docs/showdown_captain_training_dataset_2024_2025.csv \
  --alert-threshold 0.25 \
  --min-segment-slates 5
```

The analyzer groups each season into early (weeks 1-6), mid (7-12), and late (13+) segments, then measures total variation in captain-position shares between consecutive populated segments. Alerts require both segments to meet the minimum sample size. The current report at `docs/showdown_captain_drift_2024_2025.md` found one alert: 2024 mid-to-late moved `0.480`, driven primarily by a 48.0-point drop in WR captain share.

## Showdown Role and Scenario Priors

```bash
source .venv/bin/activate
python scripts/analyze_showdown_captain_scenarios.py \
  --dataset-csv docs/showdown_captain_training_dataset_2024_2025.csv
```

The analyzer extends captain classes into salary-relative `premium`, `core`, and `value` roles within position. It groups future-safe pregame totals and absolute spreads into scenario cells, applies Laplace smoothing, and falls back to the global archetype distribution when a cell has fewer than five slates. The current 41-slate outputs are `docs/showdown_captain_scenarios_2024_2025.json` and `.md`; they are research priors and do not replace the production captain artifact.

## Projection Family and Calibration Validation

Compare rolling-history, ridge linear, regression-tree, and shallow-neural projection families with whole-week chronological splits:

```bash
source .venv/bin/activate
python scripts/compare_projection_model_families.py \
  --source-system draftkings \
  --season-start 2024 \
  --season-end 2025
```

The validation-selected regression tree achieved `2.610` MAE on the untouched 2025 W12-W18 test window, versus `3.044` for ridge and `2.901` for the shallow neural net. The result is persisted in `docs/projection_model_family_comparison_2024_2025.{json,md}` and does not automatically change production.

Track point-in-time simulation interval and tail-probability calibration with:

```bash
source .venv/bin/activate
python scripts/analyze_projection_calibration_drift.py \
  --source-system draftkings \
  --season-start 2024 \
  --season-end 2025 \
  --slate sunday_main \
  --iterations 1000
```

The current 15-slate, 2,856-player report observed P75/P90/P95 coverage of `76.4%` / `90.3%` / `94.7%`, a `+0.2` percentage-point 25+ tail-probability error, and no configured drift alerts. Historical backtest rows and the UI now expose mean, p75, p90, and p95 together.

Classic candidate generation hard-fails before scoring if any candidate or selected lineup violates roster size, uniqueness, position, salary-cap, or offense-versus-DST rules. Errors include the lineup index and exact violation codes.

## Durable Ultimate Candidate Checkpoints

Large ultimate-lineup runs can persist candidate progress to a transactional SQLite artifact. The checkpoint stores player UIDs, lineup order, adaptive-strategy state, attempt count, and the exact NumPy RNG state; it does not store player display names or observed outcomes.

Start a checkpointed 100k-candidate run with:

```bash
source .venv/bin/activate
python scripts/run_ultimate_lineups.py \
  --season 2025 \
  --week 18 \
  --slate sunday_main \
  --candidate-lineups 100000 \
  --allow-heuristics \
  --random-seed 42 \
  --checkpoint-path artifacts/checkpoints/2025-w18-ultimate.sqlite3
```

If the process is interrupted, repeat the same semantic arguments and add `--resume`:

```bash
python scripts/run_ultimate_lineups.py \
  --season 2025 \
  --week 18 \
  --slate sunday_main \
  --candidate-lineups 100000 \
  --allow-heuristics \
  --random-seed 42 \
  --checkpoint-path artifacts/checkpoints/2025-w18-ultimate.sqlite3 \
  --resume
```

Progress commits every `10000` generation attempts by default; override that with `--checkpoint-interval-attempts`. A signal between commits replays from the last committed attempt boundary, preserving the exact deterministic candidate sequence. Resume rejects changed request settings, generator or NumPy versions, sampling multipliers, or player-pool inputs. A completed checkpoint is reusable and skips candidate regeneration. Supplying an existing path without `--resume` starts a new run and replaces its prior checkpoint contents.

The `POST /api/lineups/ultimate` request exposes the same `checkpoint_path`, `resume_from_checkpoint`, and `checkpoint_interval_attempts` controls. Its response reports the normalized checkpoint path, resume flag, final status, and transaction write count.

## Contest-Specific Lineup Objectives

Ultimate classic lineup generation supports three transparent ranking profiles:

- `balanced` preserves the existing learned/heuristic composite exactly and remains the default.
- `cash` blends the base score (`0.25`), projected mean (`0.45`), and learned quality / one-minus-bust probability (`0.30`).
- `gpp` blends the base score (`0.25`), learned top-tail policy (`0.20`), learned ceiling probability (`0.25`), and projected p90 (`0.30`), then subtracts `0.15` of standardized pre-lock duplication-proxy risk.

Select a profile with:

```bash
source .venv/bin/activate
python scripts/run_ultimate_lineups.py \
  --season 2025 \
  --week 18 \
  --slate sunday_main \
  --contest-objective gpp \
  --candidate-lineups 2500 \
  --allow-heuristics
```

`POST /api/lineups/ultimate` accepts the same `contest_objective` value. API and
CLI output report the selected profile, exact fixed weights, pre-objective base
score, and final ranking score. An explicit `duplication_risk_penalty` is
applied after the profile; it remains zero by default.

These are pre-lock research profiles, not claims about historical cash lines,
field ownership, or payout structure. Until contest-level outcomes are
available, `balanced` remains the production default.

## Late Swap

Ultimate classic generation can preserve already-locked players while
re-optimizing the remaining slots. The caller supplies:

- a timezone-aware lock-assessment timestamp;
- the original lineup's nine source-native player IDs; and
- the teams whose games have started at that timestamp.

Example:

```bash
python scripts/run_ultimate_lineups.py \
  --season 2025 \
  --week 18 \
  --slate sunday_main \
  --contest-objective gpp \
  --candidate-lineups 100000 \
  --late-swap-as-of 2025-12-28T18:30:00-05:00 \
  --late-swap-original-source-player-keys \
dk-qb,dk-rb1,dk-rb2,dk-wr1,dk-wr2,dk-wr3,dk-te,dk-flex,dk-dst \
  --late-swap-locked-teams BUF,MIA
```

Players from the original lineup whose teams are locked are required in every
candidate and exempt from exposure caps. Every other player from a locked team
is excluded, so a late swap cannot add a player whose game already started.
All normal uniqueness, position, salary-cap, and offense-versus-DST checks
still hard-fail. Repeating the same request and seed is deterministic, and
checkpoint fingerprints include the lock constraints.

`POST /api/lineups/ultimate` accepts matching `late_swap_as_of`,
`late_swap_original_source_player_keys`, and `late_swap_locked_teams` fields.
The response records the normalized teams, locked source IDs, timestamp, and
an `is_locked` flag per player.

Lock state is deliberately caller-authoritative. The service does not infer a
live contest lock from historical schedule strings or display names.

## Popularity and Duplication Proxy

Ultimate classic lineup output now reports a `popularity_proxy` for each player and a `duplication_risk_score` for each lineup. These are explicitly not observed ownership. They use only pre-lock salary, projection, value, implied-total ranks, generated-candidate exposure, pair concentration, and salary usage.

Current rankings remain unchanged unless an explicit penalty is requested:

```bash
source .venv/bin/activate
python scripts/run_ultimate_lineups.py \
  --season 2025 \
  --week 18 \
  --slate sunday_main \
  --candidate-lineups 2500 \
  --allow-heuristics \
  --duplication-risk-penalty 0.25
```

Validate the risk/projection tradeoff historically with:

```bash
python scripts/analyze_popularity_proxy.py \
  --source-system draftkings \
  --season-start 2024 \
  --season-end 2025 \
  --candidate-lineups 2500 \
  --selected-lineups 20 \
  --penalties 0,0.25,0.5,0.75 \
  --limit-slates 12
```

Across the latest 12 eligible classic slates, penalty `0.25` reduced mean proxy risk by `1.1%` with a `0.2%` projected-blend cost and `0.28` fewer realized points. Penalty `0.75` reduced risk by `6.7%` but cost `5.0%` projection and `8.37` actual points. The default remains `0.0`; `0.25` is an opt-in research setting. Full evidence is in `docs/popularity_proxy_validation_2024_2025.{json,md}`.

## Manual Role-Shock Simulation

Projection simulation now supports manually triggered role shocks for RB/WR/TE players. A shock retains a caller-selected share of the target’s prior four-game carries/targets and reallocates removed opportunity to same-position teammates or all team skill players. Recipient projection changes use 65% elasticity versus opportunity changes and honor a caller-controlled multiplier cap.

Run and persist a scenario with:

```bash
source .venv/bin/activate
python scripts/run_role_shock_simulation.py \
  --season 2025 \
  --week 18 \
  --slate sunday_main \
  --player-name "Jahmyr Gibbs" \
  --retained-opportunity-share 0 \
  --reallocation-scope same_position \
  --random-seed 42
```

The Projection Simulation UI exposes the same workflow: run an unshocked baseline, select an eligible player, choose retained opportunity and reallocation scope, then rerun. Simulation runs default to seed `42` and persist the effective seed and full parameter JSON.

Measure downstream portfolio fragility with:

```bash
python scripts/analyze_role_shock_fragility.py \
  --season 2025 \
  --week 18 \
  --slate sunday_main \
  --player-name "Jahmyr Gibbs" \
  --retained-opportunity-share 0 \
  --iterations 3000 \
  --candidate-lineups 2500 \
  --selected-lineups 20 \
  --random-seed 42
```

In the stored Week 18 stress test, Gibbs exposure moved from `30%` to `0%`, Montgomery moved from `5%` to `25%`, top-lineup overlap was `70%`, and scenario reoptimization recovered `6.69` projected-blend points versus keeping the baseline portfolio. This is a hypothetical pre-lock stress test, not a claim that an injury or role change occurred historically. Evidence is in `docs/role_shock_fragility_2025_w18.{json,md}`.

### Point-in-Time Weather and News Shocks

Projection simulation also accepts manually entered weather or news shocks with
an explicit information cutoff. Each shock records:

- a timezone-aware `observed_at` timestamp and scenario-wide
  `scenario_as_of` cutoff;
- a descriptive label and `weather` or `news` type;
- either one or two teams plus affected positions, or stable canonical/source
  player IDs; and
- caller-controlled mean and volatility multipliers.

The service rejects naive timestamps, observations later than the cutoff,
mixed targeting modes, missing or ambiguous player identities, and unknown
teams. It never joins by a display name. Multiple shocks compound in request
order, the same seed and request reproduce the same result, and the complete
request is stored on `simulation_run.parameters_json`.

Run a team weather scenario with:

```bash
python scripts/run_point_in_time_shock_simulation.py \
  --season 2025 \
  --week 18 \
  --slate sunday_main \
  --shock-type weather \
  --scenario-as-of 2025-12-28T12:00:00-05:00 \
  --observed-at 2025-12-28T11:30:00-05:00 \
  --label "Strong crosswind" \
  --teams BUF,MIA \
  --positions QB,WR,TE,K \
  --mean-multiplier 0.90 \
  --volatility-multiplier 1.15 \
  --random-seed 42
```

`POST /api/simulate/week` exposes the same `scenario_as_of` and
`point_in_time_shocks` contract. The Projection Simulation UI provides a
default-off weather/team-news control and reports each affected player’s mean
and p90 movement. Use the existing identity-safe role shock for player news
that should reallocate carries or targets.

These are transparent pre-lock stress assumptions, not inferred live reports
or fabricated historical weather/news observations.

Late-2025 replay validation found and corrected a zero-floor edge case so the
realized post-floor mean now matches `mean_multiplier` exactly even when
volatility widens. Week 16, 17, and 18 replays completed without warnings,
target leakage, or negative outcomes; the Week 17 same-seed repeat was
byte-identical after run metadata was excluded. Evidence is in
`docs/point_in_time_shock_validation_2025_late_season.{json,md}`.

This acceptance covers projection stress behavior only. Ultimate lineup
generation does not yet consume a selected scenario simulation run.

## Online Weekly Residual Learning

The DraftKings research workflow can now learn shrinkage-adjusted weekly projection residuals from QB/RB/WR/TE history without injury or ownership feeds. It combines only point-in-time-safe player identity, team-position, opponent-position, salary bucket, projected-value bucket, and total/spread regime signals. Every target week uses residuals from strictly earlier completed weeks, and the shrinkage strength is selected on an earlier validation window before evaluation on an untouched later test.

Run the deterministic comparison with:

```bash
source .venv/bin/activate
python scripts/analyze_online_residual_learning.py
```

Across 3,342 observations from 15 Sunday-main slates, validation selected prior strength `5.0`. On the untouched 2025 W11-W18 test window, residual adjustment improved MAE from `4.818` to `4.602` (`+4.48%`) and RMSE from `6.551` to `6.389` (`+2.47%`). Every test slice and each eligible position improved. The research gate passed; production defaults remain unchanged because scoring integration is opt-in. Evidence is in `docs/online_residual_learning_2024_2025.{json,md}`.

The accepted learner is also available as a DraftKings-only, default-off simulation gate backed by immutable weekly snapshots. Build or reuse the historical snapshots with:

```bash
source .venv/bin/activate
python scripts/apply_migrations.py
python scripts/build_online_residual_snapshots.py
```

The 2024-2025 backfill persisted 15 completed snapshots containing 3,342 canonical QB/RB/WR/TE observations with zero failures; a second run reused all 15 snapshots. In the UI, keep `Online Residual Gate` off for baseline behavior or explicitly enable it for a DraftKings simulation. Scoring uses only strictly earlier compatible snapshots, requires at least four, and reports a visible fallback warning instead of changing projections when history is insufficient. Backfill lineage is in `docs/online_residual_snapshot_backfill_2024_2025.json`.

## Game-Regime Ensemble Research

The future-safe regime workflow compares the current global regression-tree research baseline with position-by-total/spread-regime specialists. Specialists use only pregame schedule context, are blended toward the global model by prior sample size, and fall back to the global prediction exactly for unknown or sparse cells.

```bash
source .venv/bin/activate
python scripts/analyze_game_regime_ensemble.py
```

Across 17,342 feature-matrix rows and 28 whole-week slices, canonical identity coverage was `79.7%` and pregame regime coverage was `100%`; identity is reported but is not a model feature or join in this comparison. Validation selected a 300-row minimum and prior strength `1000`. The candidate did not pass: validation MAE worsened `0.27%`, untouched-test MAE worsened `0.04%` (`2.573` to `2.574`), and only two of five test slices improved. WR improved on test but not validation, so enabling it would use test leakage. Production remains unchanged; evidence is in `docs/game_regime_ensemble_2024_2025.{json,md}`.

Architecture decisions and acceptance status are maintained in `docs/DECISIONS.md` and `docs/MODEL_REGISTRY.md`.
An empty-database environment can be reproduced using `docs/BOOTSTRAP_RUNBOOK.md`.
