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
