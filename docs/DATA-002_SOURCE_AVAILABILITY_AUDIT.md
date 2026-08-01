# DATA-002 Source Availability Audit

Date: 2026-07-30

## Outcome

DATA-002 remains incomplete and explicitly blocked. The repository and development database
do not contain an approved historical Vegas, props, weather, depth-chart, injury, or role feed that
preserves when each value was observable before lock. No timestamps were inferred or backfilled.

The bounded safe change is `point_in_time_cutoff_v1`: projection-linked consumers now ignore an
injury snapshot unless both its `as_of` and the exact projection run's `data_cutoff_at` exist and the
snapshot was observed at or before that cutoff.

The prospective tooling is now ready through `prospective_source_snapshot_v1`. Migration `0019`
stores append-only source manifests and ingest links, and `scripts/capture_prospective_sources.py`
captures DraftKings salaries plus nflreadpy schedules, rosters, injuries, and snap counts using
server receipt time. Real 2026 observations have not yet been collected, so this does not change the
historical-source decision or unblock MODEL-001. See `docs/PROSPECTIVE_SOURCE_CAPTURE.md`.

## Local Evidence

| Dataset | Rows | Local load time | Historical observation time | Decision |
| --- | ---: | --- | --- | --- |
| `raw_injury_row` / `curated_injury` | 10,268 across 28 ingest runs | 2026-02-25 18:56:29–18:56:38 | None; all rows are FanDuel slate exports with injury indicators | Retrospective only; not replay eligible |
| `target.snapshot_injury_status` | 8,086 | Inherits the same 2026-02-25 adapter time | No separate source observation timestamp | Fail closed unless a future row has a proven cutoff-compatible `as_of` |
| Week 11 target injuries | 493 | 2026-02-25 18:56:33 | After the 2025 games | Excluded from the Week 11 baseline projection, whose cutoff is null |
| `raw_nfl_schedule` | 7,017, with total and spread values on every row | 2026-02-25 13:21:41–13:23:28 | None | Treat as historical/closing context, not cutoff-safe betting snapshots |
| Props, weather, depth-chart snapshot tables | 0 local tables | N/A | N/A | Source required |
| Role changes | Manual scenario support only | Explicit scenario time | Not an observed historical feed | Keep as scenario evidence, not historical fact |

The read-only Week 11 SUNDAY_MAIN smoke loaded 382 eligible salary/projection rows from
`baseline_rolling_dk_v0:projection:2025:11`. Its `data_cutoff_at` is null, so none of the 493
retrospective injury rows were eligible to remove a player or trigger an injury rule.

## Upstream Audit

The official [nflverse injury dictionary](https://nflreadr.nflverse.com/articles/dictionary_injuries.html)
documents native GSIS identity and a `date_modified` field described as the time injury information
was updated. The installed [nflreadpy loader](https://nflreadpy.nflverse.com/api/load_functions/)
successfully returned 6,068 rows for 2025, but its actual 16-column frame omitted `date_modified`.
Season/week and report status therefore cannot establish when the platform could have observed a
historical record.

The nflreadpy schedules loader downloads the current full games dataset. The local copy contains
totals and spreads but no observation history, so these values cannot be represented as a sequence
of pre-lock market snapshots.

## Implemented Guardrail

`backend/app/product_services/point_in_time.py` defines the shared contract:

1. Missing snapshot time is not visible.
2. Missing consuming-run cutoff is not visible.
3. Observation before or exactly at cutoff is visible.
4. Observation after cutoff is not visible.

The predicate is used by:

- slate simulation player-pool injury exclusions;
- optimizer player-pool injury exclusions;
- target symbolic injury rules.

Existing raw and target rows remain intact for audit. The guardrail changes only whether they are
eligible for a cutoff-scoped decision.

## Unblocking Decision

DATA-002 can resume through either route:

1. Select an authorized historical source that provides immutable observation timestamps and stable
   native IDs, then retain source payload, effective time, observed time, and ingest lineage.
2. Run the implemented prospective capture command for the 2026 season, using server receipt time
   as the non-backdatable observation time and source publication/effective time as separate
   metadata.

Vegas, props, weather, depth-chart, injury, and role sources must be approved independently. One
source's timestamp quality must not be generalized to another.

## Verification

- Focused point-in-time, simulation, optimizer, and symbolic-rule tests: 40 passed.
- Full Python suite: 383 passed with two pre-existing `datetime.utcnow()` deprecation warnings.
