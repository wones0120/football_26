# Participation Identity Reassessment

Date: 2026-08-01

Contract: `participation_identity_reassessment_v1`

Registry snapshot: `c0c90497-802a-501a-ae4d-3cc7764f754c`

## Outcome

The development participation queue fell from 436 open rows to 37 without joining a snap-count
record by display name alone. The repair resolved 399 rows, rebuilt every affected season from 2013
through 2025, and refreshed the standard 2024–2025 player-game feature matrix.

| Decision | Identity keys | Queue rows |
|---|---:|---:|
| Existing PFR alias | 29 | 62 |
| Unique PFR → GSIS registry chain | 96 | 332 |
| Unique exact name + team + position for an ID-less roster row | 5 | 5 |
| **Total repaired** | **130** | **399** |

The source evidence contains the 125 relevant official registry rows used for the PFR decisions.
Its normalized evidence SHA-256 is
`a68a31ff2260223af52ff28be8d2ca5737b15e82a69ec4bffd91b93de5fec67e`; the immutable CSV artifact
SHA-256 is `6b513ba3497fe5dc63b03e7064ec3e3faa55cc3ae4629dca54f972899052c5d8`.

## Deterministic rules

The assessor considers open `snap_counts` and `weekly_rosters` queue rows only. Its order is:

1. Reuse an existing `pfr` source-key alias.
2. Otherwise require exactly one official-registry GSIS ID for the PFR ID, then require that GSIS ID
   to have an existing `nflreadpy` alias to one canonical `player_master_id`.
3. For a weekly-roster row with neither GSIS nor PFR ID, require normalized name, team, and position
   to select exactly one `player_master` record.

If an existing PFR alias disagrees with the registry-to-GSIS alias chain, the entire apply is
blocked. Multiple GSIS IDs, missing downstream aliases, ambiguous semantic matches, and all
name-only candidates stay open. Before writing, apply mode also verifies that every assessed queue
row is still open; concurrent queue changes force a fresh dry run.

## Traceability and repeatability

Dry run is the default:

```bash
python scripts/reassess_participation_identities.py
```

The initial dry run reported 399 deterministic rows, zero conflicts, and 37 remaining rows. Apply
mode first captures the relevant registry subset through `prospective_source_snapshot_v1`, then
upserts PFR aliases, resolves queue rows with actor, timestamp, reason, GSIS ID, and registry
snapshot ID, and rebuilds all affected participation seasons in one database transaction:

```bash
python scripts/reassess_participation_identities.py --apply
```

A post-apply dry run reports `no_changes`, zero deterministic rows, zero conflicts, and the same 37
residual rows. Raw roster and snap snapshots remain immutable.

## Post-repair data audit

| Measure | Before | After | Change |
|---|---:|---:|---:|
| Open participation identities | 436 | 37 | -399 |
| Curated player-game participation | 769,113 | 769,411 | +298 |
| Gold team-game availability | 12,446 | 12,446 | 0 |
| 2024–2025 player-game feature matrix | 16,985 | 16,985 | Rebuilt |

The difference between 399 queue resolutions and 298 new Silver rows is expected: queue rows can be
duplicate observations or can resolve to a player-game already represented by another source row.
The feature rebuild completed all 88 discovered slates and wrote 16,985 rows with zero failures.

## Residual quarantine

The remaining 37 rows are intentionally unresolved:

- 26 weekly-roster rows have no native player ID and no unique exact name+team+position master.
- 11 snap-count rows cover eight PFR IDs absent from the official registry subset:
  `BrowJo03`, `CoopBu00`, `CudjYa00`, `McCrRo00`, `MeadNa00`, `OkoyCJ00`, `ShenJo00`, and
  `TaylAl02`.

These rows remain visible in `unresolved_player_queue` for an evidence-backed manual resolution or a
future registry update. They are not silently dropped or inferred from display name.
