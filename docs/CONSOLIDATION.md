# Repository Consolidation Contract

## Decision

`football_26` is the canonical repository. The `football_opt` repository remains a read-only
reference until the parity gates below pass; it must not be deleted or archived earlier.

The combined application keeps the `football_26` migration ledger, canonical identity layer,
ingestion lineage, benchmark evidence, simulations, and lineup research. It adopts the product
shell and end-to-end workflows developed in `football_opt`: Digital Twin, War Room, Model
Workbench, Contest Delivery, slate readiness, ownership, portfolios, DraftKings exports, news,
and guarded human-belief learning.

## Non-Negotiable Contracts

1. `public.player_master.player_master_id` remains the canonical player key.
2. `target.dim_player.player_id` is the same identifier serialized as text; it is not a second
   identity system.
3. Source records continue to resolve through native IDs, deterministic aliases, or an explicit
   unresolved/quarantine workflow. Display names are never join keys.
4. Existing `public` tables remain the immutable ingestion and curated-data foundation.
5. Product-facing model, projection, simulation, optimizer, portfolio, belief, and export artifacts
   live in the `target` schema with exact run IDs and point-in-time cutoffs.
6. Every `target` table is created by a numbered SQL migration. Runtime `_ensure_schema` methods
   may validate compatibility but may not become the authoritative DDL path.
7. Existing simulation and lineup APIs remain stable while product APIs are added under the same
   `/api` application.

## Capability Ownership

| Capability | Canonical implementation |
|---|---|
| Raw/curated ingestion, canonical identity, unresolved repair | `football_26` |
| Formal migrations and schema-drift checks | `football_26` |
| Benchmark suite, residual learning, showdown research | `football_26` |
| Role/news/weather shocks, late swap, candidate checkpoints | `football_26` |
| Async ultimate-lineup jobs and baseline/shock comparison | `football_26` |
| Product shell, Digital Twin, War Room, Model Workbench | port from `football_opt` |
| Slate readiness and persistent data-quality history | port from `football_opt` |
| Ownership, contest evidence, portfolio assignment, DK export | port from `football_opt` |
| Human beliefs, impact previews, raw thought inbox, variants | port from `football_opt` |
| News monitoring and feedback | port from `football_opt` |

## Parity Gates

- One command installs runtime and test dependencies on a fresh Python environment.
- All numbered migrations apply to an empty PostgreSQL database and a second run is a no-op.
- ORM/migration drift validation covers `public`, and static migration coverage requires every
  product-created `target` table to appear in the numbered migration ledger.
- Existing `football_26` tests remain green.
- Ported `football_opt` service tests run from this repository and remain green.
- The production UI build passes and exposes Digital Twin, War Room, Model Workbench, Operations,
  Contest Delivery, and the simulation/portfolio comparison workflow.
- A smoke workflow can ingest a slate, build projections, create a simulation, compare baseline and
  shock portfolios, generate/validate an export, and reload every artifact by its persisted run ID.
- No runtime imports or filesystem references point at `/Users/wones/git/football_opt`.

## Archival Gate

Only after every parity gate passes may `football_opt` be made read-only or archived. Deletion is
not part of this consolidation and requires a separate explicit decision.

## Verification Status

The combined repository installs and imports cleanly, applies all migrations idempotently, exposes
103 API contracts without collisions, passes 339 combined tests, and produces a successful Vite
production build. Live API checks reloaded a completed 1,000-iteration Week 11 simulation with 382
player rows and its persisted optimizer lineup/lineage. Runtime scans contain no reference to the
old repository.

Fresh-database parity was reverified on 2026-07-24 with `AUTO_CREATE_TABLES=false`. A disposable
empty PostgreSQL database applied all 12 numbered migrations in exact ledger order, the second pass
applied nothing, all 19 ORM-managed `public` tables matched without structural drift, and all 55
product-created `target` tables were present and covered by numbered migrations. The exact commands
and counts are recorded in `docs/CON-003_SCHEMA_PARITY.md`.

The canonical database does not yet contain a DraftKings entry template. Import one real template,
then create, validate, download, and reload a portfolio export before archiving `football_opt`.
