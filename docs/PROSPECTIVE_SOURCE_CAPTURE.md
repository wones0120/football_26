# Prospective Source Capture

Last validated: 2026-08-28

Contract: `prospective_source_snapshot_v1`

Migration: `0019_prospective_source_snapshots.sql`

## Outcome

The repository has preserved the first full-season 2026 schedule observation and the first real
DraftKings Week 1 `SUNDAY_MAIN` salary observation before their games: 272 regular-season games
with 272 unique canonical game IDs, plus 719 salary rows covering all 12 Sunday Main games. This
closes the schedule and salary portions of the capture-tooling gate. DATA-002 itself remains
incomplete until the other approved pre-lock observations are retained.

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
to an absolute path on backed-up durable local or mounted storage before the first live salary
capture. Repository-local ignored files are not a backup. The command prints the absolute
artifact/manifest paths, checksum, observation time, pre-lock decision, row counts, and ingest
result as JSON. A nonzero exit means one or more requested sources failed or a salary observation
arrived after lock.

## UI Schedule Ingest

In `Research Lab` > `Ingestion`, select the season and choose `Load Schedules`. The API fetches the
nflreadpy schedule once, preserves the full selected season or week slice as an immutable CSV, then
reads that captured artifact into `raw_nfl_schedule`. The ingest run stores the artifact path and
checksum and receives a deterministic ID derived from the snapshot; `source_snapshot_ingest_run`
links both records. An unchanged repeat reuses the verified snapshot and completed ingest run.

This route intentionally has no slate lock because the NFL schedule is season-level fixture data,
not a DFS salary observation. Any later upstream schedule change creates a new content-addressed
snapshot and ingest run before replacing the selected database rows.

## DraftKings Ingest Safety

The command captures the source bytes first. Only a snapshot with `observed_at <= slate_lock_at`
can enter salary ingestion. The ingest service receives the read-only captured file path, and its
existing checksum must equal the snapshot checksum. Canonical matching and unresolved-queue rules
remain unchanged. The ingest run ID is derived from the snapshot ID, so retrying the same capture
returns the same completed run.

A post-lock download remains valuable audit evidence, so it is retained. It is intentionally not
linked to an ingest run and is absent from `eligible_snapshots(cutoff_at=...)` for that lock.

## Real Week 1 Salary Capture

The source-authorized `DKSalaries_2026_1_SUNDAY_MAIN.csv` file was captured on 2026-08-28 at
`07:37:56.614169-04:00`, before the declared 2026-09-13 `13:00:00-04:00` slate lock.

| Check | Result |
| --- | --- |
| Snapshot ID | `d893bd08-475f-50b2-8b29-235670d3805d` |
| SHA-256 | `39f7d4669ba4d45c711ae8b135468ce01180c5b181d1f77076c75258a72287a6` |
| Ingest run ID | `ab38816d-9b5d-5f7e-8f24-ca60ee1d3f8d` |
| Raw / curated rows | 719 / 719 |
| Canonical games | 12 |
| Resolved / unresolved player identities | 531 / 188 |
| Unresolved DST identities | 0 |
| Artifact verification | Passed at the configured durable snapshot root outside the repository |
| Identical rerun | Reused the same snapshot and completed ingest run; no duplicate artifact or rows |

The 188 unresolved player rows remain in the explicit review queue; none were silently dropped or
joined by display name alone. Those identities must be resolved or accepted under the governed
quarantine rules before the full salary pool can enter projections or optimization.

## nflreadpy Boundaries

The command captures exactly the tabular frame returned by the installed nflreadpy version after
season/week filtering and records that package version. These are Bronze observations. The UI
schedule action ingests from those same captured bytes and records the snapshot-to-run link.
Existing roster/snap ingestion and canonical identity rules remain the Silver/Gold path; this
change does not treat current injury or schedule values as historical pre-lock evidence.

The default license strings are provenance reminders, not a grant of rights. Replace them with an
approved source-specific statement when required. Paid or separately licensed sources should use
the same capture service only after their terms and allowed storage/use are recorded.

## Verification And Recovery

Focused tests prove:

1. capture files and manifests are content-addressed and idempotent;
2. modifying the original download does not alter preserved evidence;
3. DraftKings ingestion uses the preserved checksum and resolves canonical identity normally;
4. a post-lock salary capture creates no ingest run and is excluded by cutoff selection;
5. nflreadpy frames are week-filtered and retain loader-version lineage;
6. UI schedule loads ingest from the captured artifact, record its checksum and lineage link, and
   reuse an unchanged completed run.

`verify_snapshot_artifact` re-hashes an artifact and validates its manifest. A missing or mismatched
artifact is an integrity failure; the service will not silently reconstruct or overwrite it.

Focused source-capture, current-weather, and slate-weather validation passes 15 tests. The full
backend suite passes 433 tests without warnings; all 12 UI tests and the production UI build pass.
