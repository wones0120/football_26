# CON-003 Fresh-Database Schema Parity

Verified: 2026-07-24

## Scope

CON-003 required the combined repository to apply every numbered migration to
an empty PostgreSQL database, prove that a second pass is a no-op, match the
`public` SQLAlchemy schema without runtime table creation, and cover every
product-created `target` table in the migration ledger.

The check used a disposable PostgreSQL 14.13 cluster and an empty database with
`APP_ENV=test` and `AUTO_CREATE_TABLES=false`. The cluster was isolated from the
development database and removed after validation.

## Commands

With `DATABASE_URL` pointed at the disposable empty database:

```bash
APP_ENV=test AUTO_CREATE_TABLES=false \
  .venv/bin/python scripts/check_schema_drift.py \
  --apply-migrations \
  --require-empty \
  --verify-idempotency

PYTHONPATH=. AUTO_CREATE_TABLES=false \
  .venv/bin/python -m pytest -q \
  backend/app/tests/test_schema_drift.py \
  backend/app/tests/test_target_schema_migration_coverage.py
```

A read-only PostgreSQL catalog query independently counted the migration ledger
and both schemas after the migration run.

## Results

| Check | Result |
| --- | --- |
| Empty-schema precondition | Passed |
| Numbered migration files | 12, contiguous from `0001` through `0012` |
| First-pass ledger | All 12 files applied in exact filename order |
| Second migration pass | `second_pass_applied: []` |
| ORM-managed `public` tables | 19 expected, 19 migrated |
| `public` structural drift | 0 issues |
| PostgreSQL `public` catalog count | 20 tables, including `schema_migrations` |
| PostgreSQL migration-ledger count | 12 rows |
| PostgreSQL `target` catalog count | 55 tables |
| Product-code target migration coverage | 55 of 55 tables |
| Targeted tests | 6 passed |
| Runtime auto-create fallback | Disabled |

The schema validator returned `status: ok`, all 12 migration filenames in
`newly_applied`, no filenames in `second_pass_applied`, and an empty `issues`
list. CON-003 therefore satisfies its acceptance check without relying on
`AUTO_CREATE_TABLES` or pre-existing database state.
