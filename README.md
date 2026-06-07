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

## Migration Notes

Migrations live in `/migrations`. The migration runner tracks applied files in `schema_migrations`.

## Current Status

1. Phase 1 baseline is implemented.
2. See `/Users/wones/git/football_26/docs/phase_plan.md` for the build sequence.

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
