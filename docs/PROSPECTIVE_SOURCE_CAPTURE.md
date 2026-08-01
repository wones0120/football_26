# Prospective Source Capture

Date: 2026-07-31

Contract: `prospective_source_snapshot_v1`

Migration: `0019_prospective_source_snapshots.sql`

## Outcome

The repository is ready to preserve the first 2026 observations before slate lock. This closes the
capture-tooling portion of DATA-002; DATA-002 itself remains blocked until real prospective weeks
and source-specific usage approvals exist.

The capture path supports:

- a manually downloaded DraftKings salary CSV, ingested only from its preserved copy;
- nflreadpy schedules, weekly rosters, injuries, and snap counts serialized as observed CSV
  snapshots;
- repeated polling without duplicate files or ingest runs;
- cutoff selection that excludes an observation made after slate lock.

## Evidence Contract

Each `source_snapshot` row and adjacent `manifest.json` records:

- source system, dataset, season, week, and slate;
- server receipt time (`observed_at`) and capture time (`captured_at`);
- source/effective time when supplied; otherwise `effective_at` equals the observed time;
- slate lock time and whether the observation preceded it;
- SHA-256, byte count, row count, media type, and immutable artifact path;
- source URI, source-license statement, observation basis, and source-specific metadata.

The snapshot ID is deterministic for source, dataset, slate scope, and content hash. Identical
content in the same scope reuses the original observation; changed content appends a new version.
PostgreSQL has a trigger that rejects `UPDATE` and `DELETE` on `source_snapshot`. The separate
append-only `source_snapshot_ingest_run` table links preserved evidence to downstream ingest runs
without mutating the snapshot.

## Weekly Command

For safe directory polling, rename the DraftKings download with its season and zero-padded week:

```text
DKSalaries_2026_01_sunday_main.csv
```

Then run before the first game in the slate:

```bash
python scripts/capture_prospective_sources.py \
  --season 2026 \
  --week 1 \
  --slate sunday_main \
  --slate-lock-at 2026-09-13T13:00:00-04:00 \
  --draftkings-directory ~/Downloads \
  --nflreadpy-datasets schedules weekly_rosters injuries snap_counts
```

Use `--draftkings-path ~/Downloads/DKSalaries.csv` when retaining DraftKings' generic filename.
Directory discovery deliberately ignores that generic name because a scheduled run cannot prove
which week an old generic file belongs to.

`SOURCE_SNAPSHOT_ROOT` defaults to `artifacts/source_snapshots`, which is excluded from Git. Set it
to durable local or mounted storage before the season if repository-local artifacts are not backed
up. The command prints the absolute artifact/manifest paths, checksum, observation time, pre-lock
decision, row counts, and ingest result as JSON. A nonzero exit means one or more requested sources
failed or a salary observation arrived after lock.

## DraftKings Ingest Safety

The command captures the source bytes first. Only a snapshot with `observed_at <= slate_lock_at`
can enter salary ingestion. The ingest service receives the read-only captured file path, and its
existing checksum must equal the snapshot checksum. Canonical matching and unresolved-queue rules
remain unchanged. The ingest run ID is derived from the snapshot ID, so retrying the same capture
returns the same completed run.

A post-lock download remains valuable audit evidence, so it is retained. It is intentionally not
linked to an ingest run and is absent from `eligible_snapshots(cutoff_at=...)` for that lock.

## nflreadpy Boundaries

The command captures exactly the tabular frame returned by the installed nflreadpy version after
season/week filtering and records that package version. These are Bronze observations. Existing
roster/snap ingestion and canonical identity rules remain the Silver/Gold path; this change does
not treat current injury or schedule values as historical pre-lock evidence.

The default license strings are provenance reminders, not a grant of rights. Replace them with an
approved source-specific statement when required. Paid or separately licensed sources should use
the same capture service only after their terms and allowed storage/use are recorded.

## Verification And Recovery

Focused tests prove:

1. capture files and manifests are content-addressed and idempotent;
2. modifying the original download does not alter preserved evidence;
3. DraftKings ingestion uses the preserved checksum and resolves canonical identity normally;
4. a post-lock salary capture creates no ingest run and is excluded by cutoff selection;
5. nflreadpy frames are week-filtered and retain loader-version lineage.

`verify_snapshot_artifact` re-hashes an artifact and validates its manifest. A missing or mismatched
artifact is an integrity failure; the service will not silently reconstruct or overwrite it.

Focused capture/CLI validation passes 6 tests, and the full Python suite passes 401 tests with two
pre-existing `datetime.utcnow()` deprecation warnings.
