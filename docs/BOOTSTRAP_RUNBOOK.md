# Empty-Database Bootstrap Runbook

This runbook creates a local football_26 environment from an empty PostgreSQL database without relying on prior application state.

## Prerequisites

- Python 3.13-compatible runtime
- PostgreSQL reachable from the application host
- Node.js/npm for the control-plane UI
- DraftKings/FanDuel source CSVs for salary or injury ingestion

## 1. Install and configure

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set the local PostgreSQL values in `.env`. Never put credentials in committed files or command output.

## 2. Start PostgreSQL and apply every migration

```bash
./start_postgres.sh
python scripts/apply_migrations.py
```

Expected result: every file under `migrations/` is listed in `schema_migrations`. Rerunning the command must report the migrations as already applied.

Verify the migration-owned product schema and the ORM-managed public schema:

```bash
python scripts/check_schema_drift.py --schema target
python scripts/check_schema_drift.py
```

The target check must report 55 expected and actual tables with no issues.
Product services do not create or alter `target` tables; a compatibility error
means the numbered migrations are incomplete or the database has drifted.

For an intentionally disposable local database only, the reset path is:

```bash
python scripts/recreate_database.py
python scripts/apply_migrations.py
```

Do not use the reset command against a database containing data that must be preserved.

## 3. Start and verify the API

```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

In another terminal:

```bash
curl -sS http://127.0.0.1:8000/api/health
curl -sS http://127.0.0.1:8000/api/model/defaults
```

Both endpoints should return JSON without a database-schema error.

## 4. Load historical NFL data

Use the UI nflreadpy bootstrap action, or call the documented ingest endpoints for schedules and weekly stats. Run history must show row counts and an `ok` status before continuing.

The primary UI now opens in `Digital Twin`. Use `Operations` for product ingestion/readiness workflows and
`Research Lab` for the original Data Ops simulation, backtest, and baseline-versus-shock tools. During Vite
development, `/api` is proxied to `http://127.0.0.1:8000`; production remains same-origin.

Verify:

- `GET /api/coverage/season` shows schedule and weekly-stat seasons.
- `GET /api/coverage/freshness` shows the selected target data as present.
- Repeating the same ingest does not create duplicate curated facts.

## 5. Load salaries and injuries

Start with dry, known source files and use the UI upload/discovery controls. Validation failures must leave the last valid curated slice unchanged.

Verify:

- The salary slice appears in curated salary coverage.
- Open identity failures appear in the unresolved queue.
- DST rows resolve through team-defense identity rules, not display-name fallback.
- Any manual resolution persists an alias and disappears from the open queue.

## 6. Build historical learning inputs

```bash
source .venv/bin/activate
python scripts/build_player_game_feature_matrix.py \
  --source-system draftkings \
  --season-start 2024 \
  --season-end 2025
```

Then build and train historical top-lineup policy inputs as needed:

```bash
python scripts/build_actual_top_lineups.py \
  --source-system draftkings \
  --season-start 2024 \
  --season-end 2025

python scripts/train_actual_top_lineup_model.py \
  --source-system draftkings \
  --season-start 2024 \
  --season-end 2025
```

All training/evaluation windows must remain chronological and point-in-time safe.

## 7. Build online residual snapshots

After salary slices, weekly stats, and canonical identities are available, build the immutable DraftKings residual history:

```bash
python scripts/build_online_residual_snapshots.py \
  --season-start 2024 \
  --season-end 2025 \
  --slate sunday_main
```

The command is idempotent: matching snapshots are reused, while an existing slice with different parameters is rejected rather than overwritten. Verify the JSON summary reports zero failures before enabling the default-off residual gate.

## 8. Run the smoke benchmark

Use `Run Benchmark Suite` in the UI with a small slate limit, or:

```bash
python scripts/run_benchmark_suite.py \
  --source-system draftkings \
  --season-start 2024 \
  --season-end 2025 \
  --limit-slates 2 \
  --lineups-per-slate-classic 100 \
  --lineups-per-slate-showdown 100 \
  --lineups-per-slate-showdown-ab 100
```

Expected artifacts are written under a new `docs/benchmarks/<timestamp>/` directory. Confirm `suite_manifest.json`, `summary.md`, JSON backtests, and `run.log` are present. The UI Analysis area should open them and download a ZIP bundle containing the config manifest.

## 9. Final acceptance

```bash
PYTHONPATH=. .venv/bin/pytest -q backend/app/tests
cd ui
npm run build
```

Acceptance requires:

1. Migrations apply idempotently.
2. Historical source rows and curated slices have non-zero coverage.
3. Unresolved identities are visible and repairable.
4. Feature/policy builds use only prior information.
5. A smoke benchmark completes and is visible in Analysis & Reports.
6. Backend tests and UI production build pass.

## Recovery notes

- `UndefinedTable` or a target-schema compatibility error: rerun `python scripts/apply_migrations.py` against the database configured in `.env`, then run both drift checks above. Runtime services will not repair `target` schema.
- Empty simulation/backtest: confirm mapped salary players have earlier weekly-stat history.
- High unresolved count: use grouped triage before manual row-by-row repair.
- Missing report links: confirm the run contains `suite_manifest.json` and listed artifacts remain under its own benchmark directory.
