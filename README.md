# football_26 Decision OS

Canonical repository for the DFS data, modeling, simulation, Digital Twin, and contest-delivery platform:

1. Multi-source ingestion (DraftKings/FanDuel CSVs + nflreadpy stats, schedules, rosters, and snaps).
2. Canonical player identity using `player_master_id`.
3. Deterministic matching + unresolved queue for manual repair.
4. Postgres-first `public` and `target` schemas with numbered SQL migrations.
5. Leakage-safe projections, ownership, simulations, optimizers, and replay contracts.
6. Digital Twin, War Room, Model Workbench, Operations, Contest Delivery, and Research Lab workspaces.
7. Persistent portfolio assignment, DraftKings validation/export, and guarded human-belief learning.

## Quick Start

1. Create a virtualenv and install dependencies.
2. Copy `.env.example` to `.env` and set Postgres credentials.
3. Start PostgreSQL.
4. Run migrations.
5. Start API and the dedicated operational worker in separate terminals.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
./start_postgres.sh
python scripts/apply_migrations.py
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

In a second activated terminal, start the durable worker queue consumer:

```bash
python -m backend.app.worker
```

The API only records long-running work. At least one worker must be running to execute queued
benchmark, projection, research-simulation, slate-simulation, and ultimate-lineup jobs. Use
`python -m backend.app.worker --help` for worker identity, polling, lease, and one-job options.

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

The control plane keeps a sticky `Workspace` jump bar above the panels. Use it to reach `Ingestion`,
`Simulation`, `Portfolio Comparison`, `Analysis`, `Lineup Backtests`, `Unresolved Queue`, `Salary Slices`,
`Coverage`, or `Recent Runs` without scrolling through the long simulation form and result tables.

The primary application opens in `Digital Twin`. Use the product rail for `Models`, `War Room`, `Research Lab`,
`Delivery`, `Intelligence`, and `Operations`. `Research Lab` hosts the prior Data Ops control plane in an isolated
style boundary, preserving role/news/weather shocks, historical backtests, simulation-run selection, asynchronous
ultimate-lineup progress, and baseline-versus-shock portfolio comparison without leaking its CSS into the product shell.
Season, week, and slate form one active shell context across these workspaces. Projection, simulation, baseline,
and optimizer run choices are retained per compatible slate, shown in the shell, and restored when returning to that
slate; Research Lab converts the shared canonical slate ID to its lowercase API form at its boundary.

At startup, the shared season and week default to the earliest locally ingested regular-season week
that still has a future kickoff. The selection stays on the current week until its final scheduled
game begins, then advances to the next week. If no future local schedule is available, the app falls
back to the provider's current-season/current-week lookup and finally to its compiled fallback.

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
- `scripts/product/audit_salary_identities.py` performs a read-only reassessment of every unresolved legacy salary identity. It reports newly deterministic matches, stored/current reason drift, missing quarantine records, unresolved DSTs, and the accepted `ambiguous`/`no_match` quarantine totals; any blocker returns a nonzero exit status.
- Slate readiness exposes resolved, ambiguous, no-match, accepted-quarantine, unaccepted-quarantine, and untracked counts. Untracked or unaccepted rows fail every input gate, while accepted quarantine rows remain excluded from target salary snapshots plus optimizer and replay salary inputs.

## Data Freshness

- `GET /api/coverage/freshness` checks the selected source, season, week, and slate for curated salaries/injuries plus nflreadpy schedules, weekly stats, weekly rosters, and snap counts.
- Each dataset reports its exact slice row count, latest load time, age in hours, staleness threshold, and `fresh`, `stale`, or `missing` status.
- Thresholds are 24 hours for salaries, 12 hours for injuries, and 168 hours for schedules, weekly stats, weekly rosters, and snap counts.
- The UI section `Data Freshness` refreshes when the selected slice changes and after ingest actions.

## Player Participation and Availability

Migration `0018` adds immutable weekly-roster and snap-count Bronze snapshots, canonical
player-game participation, and lagged team/opponent availability features for both offense and
defense. A zero is classified as `did_not_play` only with an official inactive status or confirmed
team-game snap coverage; missing source coverage remains `unknown`. Weekly box-score activity can
prove participation when snaps are unavailable.

The Gold features shift inferred snap-share losses forward one team game. A target week can see its
team's and opponent's prior offensive and defensive losses, but never participation from the target
game itself. Load all available history and rebuild the standard player-game matrix with:

```bash
python scripts/load_nflreadpy_participation.py --season-start 2002 --season-end 2025
python scripts/reassess_participation_identities.py
python scripts/reassess_participation_identities.py --apply
python scripts/build_player_game_feature_matrix.py --season-start 2024 --season-end 2025
```

nflreadpy player-registry reassessment is dry-run by default. Apply mode accepts only an existing
PFR alias, a unique PFR-to-GSIS registry chain ending at an existing canonical alias, or an exact
unique name+team+position match for an ID-less roster row. Conflicting or ambiguous identities stay
quarantined. The August 2026 audit resolved 399 queue rows, preserved the 125-row registry evidence
subset as an immutable source snapshot, and left 37 nondeterministic rows open.

nflverse weekly rosters cover 2002–2025; the snap-count endpoint begins with 2013. Exact schema,
classification, lineage, feature definitions, and local audits are documented in
`docs/PARTICIPATION_AVAILABILITY_PIPELINE.md` and
`docs/PARTICIPATION_IDENTITY_REASSESSMENT.md`.

## Historical Game Weather

Migration `0020` standardizes the temperature, wind, roof, surface, stadium, and kickoff context
already embedded in nflverse schedules. Preview and rebuild the curated 2000–2025 table with:

```bash
python scripts/build_historical_game_weather.py
python scripts/build_historical_game_weather.py --apply
```

The local archive produces 7,017 game rows, including complete temperature and wind for 5,009
games and 1,752 indoor games where those values are not applicable. These are retrospective
game-result conditions, not archived pre-lock forecasts. A database constraint requires
`observed_at IS NULL` and `replay_eligible = false`, so the table is available for descriptive
analysis and forecast calibration but cannot silently enter historical projection or lineup
replay. Source evaluation and the ranked pre-lock forecast plan are documented in
`docs/HISTORICAL_WEATHER_DATA.md`.

## Weather Venue Registry And Forecast Source

Migration `0021` adds `nfl_venue_registry_v1`: 37 versioned physical venues with stable venue IDs,
effective seasons, coordinates, IANA timezones, roof defaults, evidence, and review notes. It maps
ordinary schedules by their PFR `stadium_id`, never by the stadium display name, and uses reviewed
game-ID overrides for every neutral-site event. The 2024–2025 acceptance audit resolves all 570
games: 555 by source ID and 15 by override, with no unresolved or ambiguous rows.

Preview or persist the registry and mapping audit with:

```bash
python scripts/build_venue_registry.py
python scripts/build_venue_registry.py --apply
```

Migration `0022` completes the 2024–2025 Open-Meteo Previous Runs backfill at the pinned 24-hour lead
and model contract. The development cohort contains 570 immutable, fully available forecasts for
570 expected games. Raw JSON and canonical manifests retain checksums, resolved venue records,
requested/returned coordinates, units, values, redacted source URIs, and ingest-run lineage. The
audit verifies all 570 artifacts with zero gaps or integrity issues.

Preview coverage, apply local non-commercial evaluation, or verify retained evidence with:

```bash
.venv/bin/python scripts/backfill_historical_weather_forecasts.py
.venv/bin/python scripts/backfill_historical_weather_forecasts.py \
  --apply \
  --allow-free-evaluation
.venv/bin/python scripts/backfill_historical_weather_forecasts.py \
  --verify-artifacts
```

The free endpoint is evaluation-only; production requires Professional-or-higher access, a customer
endpoint, and `OPEN_METEO_API_KEY`. Previous Runs does not provide a historical publication
timestamp, so every row preserves `provider_issued_at` and `provider_available_at` as null and labels
`forecast_basis_at=valid_at-24h` only as a derived fixed-lead basis. Retrospective actual weather
remains in a different table and cannot fill a forecast field. Registry details are in
`docs/WEATHER_VENUE_REGISTRY.md`, implementation and recovery are in
`docs/HISTORICAL_WEATHER_FORECASTS.md`, and the source, cost/licence, attribution, fallback, and
leakage decisions are in `docs/WEATHER_FORECAST_SOURCE_CONTRACT.md`.

## Current Weather Forecast Capture

Migration `0023` extends the same immutable weather snapshot table for live Forecast API receipts.
Every refresh appends a new `current_forecast_capture` version keyed by canonical game and venue
identity plus its actual `received_at`; it never overwrites an earlier response. Live rows have no
invented fixed lead or provider publication time: `fixed_lead_hours` remains null and
`forecast_basis_at=received_at` is labeled `server_received_at`. Cutoff selection returns only the
newest version actually received by the requested time, so a post-lock refresh is retained but
cannot replace the pre-lock view.

Preview one current slate with explicit canonical nflverse game IDs:

```bash
.venv/bin/python scripts/capture_current_weather_forecasts.py \
  --season 2026 \
  --week 1 \
  --slate WEDNESDAY_NIGHT \
  --slate-lock-at 2026-09-09T20:20:00-04:00 \
  --game-id 2026_01_NE_SEA
```

Add `--apply --allow-free-evaluation` for a one-time local non-commercial capture, or add `--watch`
to repeat complete-slate refreshes every `WEATHER_FORECAST_REFRESH_INTERVAL_MINUTES` until lock.
Production requires `OPEN_METEO_API_KEY` and the customer Forecast API endpoint. Requests are spaced
by `OPEN_METEO_MIN_REQUEST_INTERVAL_SECONDS`; freshness reports classify an otherwise available row
as stale after `WEATHER_FORECAST_STALE_AFTER_MINUTES`. Every run records per-game success, partial,
missing, quarantine, or provider-error evidence and prints both current and as-of-lock coverage.
Operational details and recovery behavior are in `docs/CURRENT_WEATHER_FORECASTS.md`.

Before the first live capture, set `SOURCE_SNAPSHOT_ROOT` and
`WEATHER_FORECAST_SNAPSHOT_ROOT` in `.env` to absolute paths on backed-up durable storage. The
repository-local defaults are suitable for development only; database checksums cannot reconstruct
lost raw evidence.

## Slate Game Weather API

`GET /api/weather/slate` exposes `slate_game_weather_v1`, the read-only canonical matchup contract
for WTHR-005. It resolves salary team/opponent pairs to nflverse `game_id`, unions canonically keyed
current-capture lineage, and returns unresolved or ambiguous matchup rows explicitly instead of
dropping them. Slate names are matched case-insensitively and no player display-name join is used.

```bash
curl --get http://127.0.0.1:8000/api/weather/slate \
  --data-urlencode source_system=draftkings \
  --data-urlencode season=2025 \
  --data-urlencode week=11 \
  --data-urlencode slate=sunday_main
```

The effective cutoff cannot exceed server time or the earliest slate kickoff. Current views expose
only receipt-timed current captures eligible at that cutoff. Historical views reconstruct the
newest cutoff-safe forecast as of lock and return retrospective actual conditions only in a
separately labeled object that remains `replay_eligible=false`. Every game reports kickoff, venue,
roof basis, forecast source/age/values, one of `available`, `indoor`, `stale`, `missing`,
or `error`, and explicit quality flags. The full contract and acceptance evidence are in
`docs/SLATE_GAME_WEATHER_API.md`.

The War Room consumes the same contract in its `Game Pressure Matrix`. Every matchup card carries
an explicit weather state and compact temperature, wind, and precipitation values. Selecting a card
opens `Matchup Weather Detail` with gusts, the venue-registry roof default, forecast source and
timestamp, cutoff-relative freshness, and readable warnings. For completed historical games,
retrospective conditions appear only in a separate `Historical Actual · Replay-Ineligible` panel;
they never replace a forecast value. UI behavior and validation evidence are in
`docs/WAR_ROOM_WEATHER.md`. The real 2025 Week 11 historical acceptance run and the still-blocked
prospective-current gate are recorded in `docs/WTHR-007_ACCEPTANCE.md`.

## Point-In-Time Input Safety

Historical injury context uses the `point_in_time_cutoff_v1` contract. A snapshot is visible only
when both `snapshot_injury_status.as_of` and the selected projection's `data_cutoff_at` exist and the
snapshot was observed at or before that cutoff. Simulation pools, optimizer pools, and target
symbolic injury rules all use the same predicate. Missing timestamps fail closed, so retrospective
imports cannot silently influence replay.

The current 2024–2025 FanDuel injury indicators and nflverse schedule betting fields are not approved
as historical pre-lock inputs: they were loaded on February 25, 2026, and do not preserve when those
values were first available. DATA-002 remains blocked until a source supplies trustworthy observation
timestamps or the platform begins prospective capture. See
`docs/DATA-002_SOURCE_AVAILABILITY_AUDIT.md` for exact coverage and source decisions.

Migration `0019` and `scripts/capture_prospective_sources.py` provide the prospective 2026 capture
path. Every observation is copied before downstream use into the content-addressed directory set by
`SOURCE_SNAPSHOT_ROOT`, accompanied by a canonical JSON manifest containing source, license,
server receipt time, effective time, slate lock, SHA-256, byte/row counts, and source metadata.
PostgreSQL rejects updates or deletes of snapshot rows. Repeated identical captures reuse the first
artifact and manifest; changed content creates a new immutable version.

For a weekly capture, rename a downloaded salary file to include the explicit season/week for safe
directory discovery (for example `DKSalaries_2026_01_sunday_main.csv`) and run:

```bash
python scripts/capture_prospective_sources.py \
  --season 2026 \
  --week 1 \
  --slate sunday_main \
  --slate-lock-at 2026-09-13T13:00:00-04:00 \
  --draftkings-directory ~/Downloads \
  --nflreadpy-datasets schedules weekly_rosters injuries snap_counts
```

The Research Lab's `Load Schedules` action applies the same evidence contract to a full-season
nflreadpy schedule refresh. It captures the fetched frame as an immutable CSV first, ingests from
that exact artifact with a deterministic run ID, records the artifact checksum on the ingest run,
and links the snapshot to the run. Repeating the action with unchanged upstream content reuses the
existing snapshot and completed ingest instead of replacing rows without new lineage.

A generic `DKSalaries.csv` is accepted only with an explicit `--draftkings-path`, preventing a
scheduled directory scan from labeling an old download as a new week. DraftKings salary ingestion
reads the preserved copy and links its deterministic ingest run to the snapshot. A post-lock salary
download is archived but receives no ingest run and is excluded from cutoff-scoped selection. See
`docs/PROSPECTIVE_SOURCE_CAPTURE.md` for the contract, operations, and recovery checks.

## MODEL-001 Feature Ablation

`scripts/run_model_001_ablation.py` separates strictly prior QB/RB/WR/TE opportunity and efficiency
features and formal DST defense-form and opponent-allowed groups. Run `--phase select` first to choose
per-position candidates using data through 2025 W11 and write a content-addressed lock; only then run
`--phase holdout` to score the reserved W12-W18 window. Injury, historical market, and salary values
are excluded as model features because their observation times are not proven.

The locked candidate was rejected: its 2,734-row holdout MAE was `2.978` versus `2.976` for the
history baseline. RB improved `0.35%`, while QB, WR, and TE regressed slightly; DST component groups
did not beat the validation baseline. Production remains unchanged. The exact validation ablations,
role calibration, lock hash, and holdout gates are in `docs/MODEL-001_CANDIDATE_LOCK.md` and
`docs/MODEL-001_HOLDOUT_EVIDENCE.md`. A prospectively captured 2026 cohort is still required before
this research can support a promotion decision.

## API Families

The single FastAPI application exposes 116 non-conflicting route contracts. Primary families are:

- `/api/ingest`, `/api/coverage`, `/api/unresolved`, and `/api/player-master` for the canonical data foundation.
- `/api/predict`, `/api/model-governance`, `/api/features`, `/api/ownership`, `/api/simulate`, and `/api/simulations` for model evaluation, approved active-run changes, and scenario runs.
- `/api/lineups`, `/api/optimizer`, `/api/portfolios`, and `/api/exports` for lineup generation and contest delivery.
- `/api/slate/readiness` and `/api/data/quality` for point-in-time operational gates and durable quality history.
- `/api/digital-twin` for beliefs, thought capture, guarded impact previews, and immutable model/human variants.
- `/api/news-monitor` and `/api/agent` for live intelligence, feedback, symbolic rules, and learning evaluation.
- `/api/benchmarks` for reproducible classic/showdown model evaluation and artifact access.
- `/api/jobs` for durable worker status, progress, results, errors, and retry.
- `/api/weekly-runs` for resumable ingest-to-export workflow dispatch, stage inspection, and retry.
- `/api/weather` for canonical slate-game weather, cutoff-safe forecast selection, and explicitly
  separate replay-ineligible historical actuals.

## Classic GPP Optimizer Strategies

Operations exposes `Classic GPP strategy` whenever the selected mode is classic
GPP. `Legacy baseline · v1` (`classic_gpp_baseline_v1`) remains the default.
`Slate-aware GPP · v1` (`classic_gpp_slate_aware_v1`) explicitly runs the
advanced ownership-template, correlation, leverage, uniqueness, and exposure
engine against the exact live projection pool. The selected version is returned
by the optimizer API, stored on the optimizer run, included in each lineup's
persisted explanation, and restored with persisted results. The advanced engine
never silently falls back to the baseline when execution or lineup validation
fails.

## Persistent Showdown Optimizer Modes

Operations sends explicit `showdown_cash_baseline_v1` and
`showdown_gpp_baseline_v1` strategy contracts for Showdown cash and GPP.
Both currently use the declared basic P90 captain ILP: one CPT at 1.5x salary
and P90 objective score plus five FLEX slots under the $50,000 salary cap and
five-player team limit. Player mean and P90 values remain separate in the
persisted result. Before a run can complete, an independent validator checks canonical
player IDs, slot shape, salary, team and exposure limits, and duplicate lineups.
The optimizer persists successful lineups with normalized slot indexes and
CPT/FLEX roles; failed status, messages, selected objective, strategy, projection
and rule lineage, and cutoff also reload after an application restart. Separate
cash-stability and GPP-payout optimization remains future `DT-605` research.

## Durable Operational Worker Queue

Migration `0015_operational_job_queue.sql` adds the `operational_job` table. Long-running API calls
now return `202 Accepted` with a durable job instead of running CPU/database work in FastAPI:

- `POST /api/benchmarks/run-suite`
- `POST /api/predict/run`
- `POST /api/simulate/week`
- `POST /api/simulations/run`
- `POST /api/lineups/ultimate-runs` (the existing ultimate-run response contract is unchanged)

The first four responses contain `created` and `job`; their unchanged former result payload is
stored as `job.result` after completion. The application UI queues and polls automatically, so its
completed benchmark, projection, and simulation views retain their existing result shapes.

Callers that may retry a dispatch should send the same `Idempotency-Key` header. Reusing a key with
the exact request returns the original job and stable underlying run ID; reusing it with different
inputs returns `409 Conflict`. Jobs are inspectable through `GET /api/jobs` and
`GET /api/jobs/{job_id}`. Failed jobs can be requeued with `POST /api/jobs/{job_id}/retry`; failed
ultimate-lineup work should normally use its existing checkpoint-aware retry endpoint.

Workers claim jobs with expiring leases and heartbeat while work is active. A worker restart can
reclaim an expired job without changing its job/run identity. Automatic attempts are bounded, the
final expired lease becomes a visible failure, and ultimate candidate generation retains its
transactional SQLite checkpoint behavior. Operations → Run activity shows recent queue status,
stage, progress, attempts, and run IDs. Restart worker processes after deploying code so newly
registered job types and handlers are loaded.

## Resumable Weekly Runs

Migration `0016_weekly_orchestrator.sql` adds `weekly_run` and `weekly_run_stage`. Queue a complete
decision chain with `POST /api/weekly-runs` and an `Idempotency-Key`. The request fixes the active
season, week, slate, cutoff, contest mode, simulation seed, optimizer parameters, and optional
DraftKings directory/template or exact `projection_run_id`. The worker executes these separately
inspectable stages:

`ingest → readiness → predict → adjust → simulate → optimize → validate → export`

Use `GET /api/weekly-runs`, `GET /api/weekly-runs/{weekly_run_id}`, and
`POST /api/weekly-runs/{weekly_run_id}/retry` to inspect or resume work. Each stage reports its
attempt count, logs, row/iteration counts, warnings, errors, result summary, and artifact IDs.
For prediction, the orchestrator reuses a completed exact requested run or the readiness-selected
active immutable run before dispatching a new build. New-write artifact IDs are allocated before
execution. On retry, completed stages are skipped and the first incomplete stage reuses its IDs, so
a worker interruption does not repeat completed writes. If no entry template is supplied or
ingested, validation stops with an explicit operator-action error and export remains pending. The
Operations workspace exposes the same launcher, eight-stage report, and `Resume Failed Stage`
action.

## Model Promotion Governance

Migration `0017_model_promotion_governance.sql` adds immutable challenger evaluations and approval
decisions. A completed prediction run initializes an active pointer only when that slate has no
champion; later runs remain challengers. `POST /api/model-governance/evaluations` accepts only
completed champion and challenger runs from the same season/week/slate and records ordered,
non-overlapping training/validation/test windows, exact persisted feature hashes, declared code
hashes, comparable metric gates, evaluator identity, and an evidence URI. At least one gate must
require a strict positive improvement, and every declared gate must pass before promotion.

`POST /api/model-governance/evaluations/{evaluation_id}/promote` requires a named approver and
reason, verifies that the evaluated champion is still active, records a content-addressed approval,
and changes the pointer in the same transaction. Rollback uses
`POST /api/model-governance/decisions/{promotion_decision_id}/rollback`; it records a second approval
and atomically restores the exact prior run. `POST /api/predict/active` is now read-only confirmation
of the run selected by a currently applied promotion or rollback decision; it no longer accepts an
arbitrary selection reason or changes a pointer itself.

## Migration Notes

Migrations live in `/migrations`. The migration runner tracks applied files in
`schema_migrations`.

With `DATABASE_URL` pointed at an empty PostgreSQL database, run the same
fresh-schema check used by CI:

```bash
python scripts/check_schema_drift.py \
  --schema target \
  --apply-migrations \
  --require-empty \
  --verify-idempotency
python scripts/check_schema_drift.py
```

The checks validate contiguous migration names, the exact migration ledger, a
second no-op migration pass, the migration-recorded table/column/constraint
contract for all 57 `target` tables, and structural agreement between the 22
migrated `public` tables and SQLAlchemy metadata. Product services only validate
the recorded `target` contract; they never create or alter those tables at
runtime. Neither check uses `AUTO_CREATE_TABLES`.

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

1. `football_26` is the canonical combined repository; `football_opt` is a read-only reference until parity gates pass.
2. The Digital Twin product shell and the full Data Ops/Simulation Research Lab run from one Vite application.
3. The backend exposes both product and research API families through one FastAPI process without route collisions.
4. All 57 product `target` tables are migration-owned through `0017`; migrations `0015` and `0016` own the durable public queue and weekly-stage checkpoints, while `0017` owns model evaluation and promotion decisions. Runtime services fail on incompatible target schema drift instead of repairing it.
5. Benchmarks, projection builds, both simulation families, baseline-versus-shock portfolio generation, and the eight-stage weekly decision chain run through a standalone persisted worker queue with idempotency, leases, progress polling, retry, and checkpoint resume.
6. The Operations workspace can queue and inspect ingest, readiness, prediction, adjustment, simulation, optimization, validation, and export as one resumable weekly run.
7. See `docs/CONSOLIDATION.md` for the ownership contract, parity gates, and archival policy.

Detailed product architecture and the imported Digital Twin roadmap are retained under `docs/product/`.

## Planning And Status

- `docs/TODO.md` is the single authoritative backlog for active work, including priority, status, dependencies, and acceptance checks.
- `docs/phase_plan.md` is the compact executive roadmap and points into the canonical backlog by task ID.
- `RELEASE_NOTES.md` records completed implementation history; `docs/DECISIONS.md` and `docs/MODEL_REGISTRY.md` preserve durable architecture and model decisions.
- Documents under `docs/product/` are imported design references and do not override the canonical backlog.

## Benchmark Control Plane

- `Current Model Card` shows the active model paths and strengths plus metrics and artifact links from the latest successful benchmark with comparable metrics.
- New benchmark runs attach deterministic nonparametric percentile bootstrap intervals to classic/showdown mean and median gaps plus captain A/B win-rate and gap-lift metrics. Defaults are 2,000 samples at 95% confidence, with seed, sample count, standard error, and bounds stored in the artifacts.
- `--bootstrap-samples` and `--confidence-level` override the defaults for CLI runs; the benchmark API accepts matching fields and records them in `suite_manifest.json`.
- `Reset To Defaults` restores the backend-configured model settings listed in `.env.example`.
- `Run Benchmark Suite` queues the canonical classic/showdown stack on the operational worker and writes a unique folder under `docs/benchmarks`.
- `Analysis & Reports` opens the latest JSON/Markdown outputs and downloads a ZIP containing all available benchmark artifacts plus `suite_manifest.json` as the exact config snapshot.
- Benchmark run history defaults collapsed and can be filtered by source, status, overlapping season range, classic/showdown track, or any model-config value.
- Heavy operational tables default collapsed with compact summaries: unresolved triage/repair, curated salary slices, season coverage, recent ingest runs, and benchmark history. Simulation and backtest result tables remain directly available in horizontally scrollable containers.
- Benchmark execution survives API restarts because FastAPI records the job and the standalone worker owns execution.

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

## Persistent Async Ultimate-Lineup Runs

The Projection Simulation UI uses persistent asynchronous runs instead of keeping a long HTTP request open:

- `POST /api/lineups/ultimate-runs` accepts an `idempotency_key` plus the existing ultimate-lineup request and immediately returns a queued run.
- Reusing the same key with the exact same request returns the existing run; reusing it with different inputs returns `409 Conflict`.
- `GET /api/lineups/ultimate-runs/{id}` exposes queued/running/completed/failed status, training/candidate/portfolio stage progress, attempt count, checkpoint location, error text, and the final response.
- `POST /api/lineups/ultimate-runs/{id}/retry` retries failed runs. Server-managed checkpoints under `artifacts/checkpoints/ultimate-runs/` are reused when compatible, so candidate generation resumes deterministically rather than starting over.

The UI polls the run, renders stage-local progress, reuses completed idempotent results, and offers `Retry From Checkpoint` after failure. Run metadata and results are stored in the application database; candidate state remains in the transactional SQLite checkpoint artifact. The standalone operational worker now owns dispatch, while the ultimate-run schema and API contract remain unchanged.

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

Ultimate lineup generation can consume any completed simulation for the same
source, season, week, and slate. The run's persisted mean and p90 outcomes
override only players matched by `player_master_id` or `source_player_key`;
display names are never used. Candidate generation stays on the baseline
projection pool, then the same candidate set is rescored and exposure-capped
under baseline and scenario projections so the comparison isolates
reoptimization instead of candidate-sampling drift.

```bash
python scripts/run_ultimate_lineups.py \
  --season 2025 \
  --week 18 \
  --slate sunday_main \
  --simulation-run-id <completed-simulation-run-id> \
  --baseline-simulation-run-id <compatible-unshocked-run-id> \
  --candidate-lineups 2500 \
  --output-lineups 20 \
  --allow-heuristics \
  --random-seed 42
```

`POST /api/lineups/ultimate` accepts the same optional `simulation_run_id`
and `baseline_simulation_run_id`. A paired baseline must be completed,
unshocked, slice-matched, and compatible with the scenario's iterations,
seed, history, prior, noise, and residual-learning settings. The scenario
must contain a role or point-in-time shock. The response records loaded and
matched outcome counts plus a
`portfolio_comparison` with lineup overlap, the baseline portfolio scored
under baseline and scenario projections, scenario reoptimization lift,
objective-score lift, and identity-safe exposure deltas. Missing, incomplete,
empty, or mismatched runs fail explicitly. Legacy runs that omit the
then-default-false residual flag are normalized to `false`. Omitting
`baseline_simulation_run_id` retains the lineup-default-versus-scenario
comparison; omitting `simulation_run_id` preserves prior lineup behavior and
returns no portfolio comparison.

The Projection Simulation UI exposes this workflow under `Baseline vs Shock
Portfolio`. `Shock Simulation Run` lists completed shocked runs for the active
source/season/week/slate, and `Compatible Baseline Run` lists only completed,
unshocked runs that pass the same server-side reproducibility checks used by
lineup generation. The newest compatible baseline is selected automatically;
`Lineup-default projection (unpaired)` remains available when no persisted pair
exists. `Compare Baseline vs Shock` displays stable-ID override counts, shared
candidate count, lineup overlap, the held baseline before and under the shock,
reoptimized projected-blend and objective lift, and per-player exposure deltas.

A bounded end-to-end replay used completed Week 18 role-shock run
`821c7b46-aad1-458d-a63d-055ea775c92b`: all `663` outcomes matched by stable
ID, `944` shared candidates produced two 20-lineup portfolios with `25%`
overlap, and reoptimization improved the scenario projected blend from
`136.33` to `146.52` (`+10.18`) while improving the scenario objective score
by `+0.886`. The shocked target's exposure moved from `15%` to `0%`. This is a
hypothetical pre-lock sensitivity result, not a claim that the role change
occurred historically.

The stricter paired replay used unshocked run
`50307558-da9d-490a-9e2c-7265e56bd3b4` against the same role-shock run. Both
runs matched all `663` players. From `332` shared candidates, the two
20-lineup portfolios overlapped `80%`; the shock reduced the retained
baseline portfolio from `142.34` baseline projected-blend points to `138.10`
under the scenario, and reoptimization recovered it to `141.38` (`+3.28`).
The shocked target's exposure moved from `20%` to `0%`.

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
