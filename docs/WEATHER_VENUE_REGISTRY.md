# Weather Venue Registry

Date: 2026-08-01

Contract: `nfl_venue_registry_v1`

Migration: `0021_venue_registry.sql`

## Outcome

The weather pipeline now has a source-controlled, database-backed venue registry with stable
canonical venue IDs, immutable registry versions, effective seasons, latitude, longitude, IANA
timezone, default roof classification, source evidence, coordinate evidence, and review notes.

The registry does not match on stadium display name. Ordinary nflverse schedule rows resolve using
the embedded `stadium_id`, which nflfastR documents as a Pro Football Reference stadium ID. Display
names are retained only as diagnostic evidence because naming-rights changes are common.

The audited 2024–2025 result is:

| Measure | Games |
|---|---:|
| Latest nflverse schedule games | 570 |
| Resolved by PFR `stadium_id` | 555 |
| Resolved by reviewed game-ID override | 15 |
| Unresolved | 0 |
| Ambiguous | 0 |
| Neutral games without a reviewed override | 0 |

The registry contains 37 physical venues and 15 reviewed neutral-site decisions. Coordinates are
stored with a per-venue Wikidata evidence URI; source venue identities link to the corresponding
PFR stadium page where one exists.

## Storage contract

- `venue_registry_record` stores a stable `venue_id` plus immutable `registry_version`. Reapplying
  a changed definition under the same record ID fails and requires a new version.
- `venue_game_override` stores versioned, evidence-linked decisions for international, Super Bowl,
  and relocated games.
- `curated_game_venue` stores one latest mapping result per `game_id`, its exact raw schedule and
  ingest-run lineage, the mapping method, and the source evidence used.
- `unresolved` and `ambiguous` are first-class mapping statuses. Both require a null registry record
  and preserve candidate IDs plus a quarantine reason; no game is silently dropped.

Schedule ingestion rebuilds the selected season's game mappings in the same transaction as the raw
schedule refresh. A failure rolls back the schedule, mapping, and retrospective-weather rebuild
together.

## Neutral and international safeguards

Every nflverse row labeled `location=Neutral` in 2024–2025 has an explicit game-ID override. This
is necessary even when its PFR stadium ID happens to be correct: game identity is stronger evidence
than a nominal home-team association for one-off sites.

It also corrects a concrete source issue. The 2025 international schedule rows retain the nominal
home team's stadium ID and display name for Sao Paulo, Dublin, London, Berlin, and Madrid. Without
the overrides, a coordinate lookup would produce a valid-looking forecast for the wrong continent.
The registry corrects these seven rows to Neo Quimica Arena, Croke Park, Tottenham Hotspur Stadium,
Wembley Stadium, Olympiastadion Berlin, and Santiago Bernabeu Stadium.

The 2024 Vikings-Rams wild-card game relocated from Los Angeles to State Farm Stadium is likewise a
reviewed override. Super Bowls LIX and LX use explicit neutral-host records.

## Effective-season and roof rules

- A source venue ID resolves only when exactly one registry version is effective for the game
  season. Zero matches quarantine as `unresolved`; multiple matches quarantine as `ambiguous`.
- Roof defaults are physical classifications: `outdoor`, `fixed_indoor`, or `retractable`. They do
  not replace a captured game-level open/closed roof state.
- The 1973 Buffalo stadium ends after the 2025 season. Its adjacent 2026 replacement must receive a
  separate stable identity and reviewed coordinates before current-season Buffalo home forecasts
  can be accepted.
- The current Nashville stadium is effective through its planned 2026 final season; its replacement
  also requires a distinct registry identity.

## Operator workflow

Preview the complete acceptance report without writing:

```bash
python scripts/build_venue_registry.py
```

Apply migration `0021`, then persist registry records, overrides, and game mappings:

```bash
python scripts/apply_migrations.py
python scripts/build_venue_registry.py --apply
```

The command defaults to 2024–2025 and accepts `--season-start`, `--season-end`, `--seed`, and
`--output-json`. A run with quarantine records completes as `completed_with_quarantine` and reports
every affected game ID. `acceptance_ready=true` requires full coverage, no ambiguity, no source-ID
conflict, and reviewed overrides for every neutral game.

## Verification

- Venue-registry, historical-weather, and schema-drift tests: 15 passed.
- Full Python suite: 411 passed with two pre-existing `datetime.utcnow()` deprecation warnings.
- Development dry run: 570 of 570 games resolved; 15 of 15 neutral games used reviewed overrides.
- Migration `0021` applied once and no-op'd on its second pass; the three new PostgreSQL table
  signatures match ORM metadata with zero issues.
- Unresolved and overlapping effective-source-ID fixtures remain quarantined and visible.
