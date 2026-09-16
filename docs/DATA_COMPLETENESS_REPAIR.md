# Historical actuals and ownership identity repair

## Result

The 2026 Week 1 audit found that target historical actuals were sourced from
`player_game_feature_matrix`. That table covers feature-building slices, not every
archived player game. The archive backfill retained **155,412 new player-game rows**
from 2000–2025, including **3,682 from 2025**. It covers archived QB/RB/FB/WR/TE/K
records; individual defensive players and team-defense scoring are outside this repair.
Existing actuals were not overwritten or rescored. Raw data and saved projections
were unchanged.

CeeDee Lamb now has 2025 Weeks 18, 17 and 16 available in target history:
**1.4, 9.6 and 11.1 points**, averaging **7.3667**. His missing Weeks 14–17 were
backfilled. The displayed history can now agree with his saved 7.37 model feature.

**38 salary records** were linked to existing canonical players, with DraftKings
native-ID aliases persisted to make the repair reusable. Reconciliation resolved
**80 additional ownership observations**:

| Contest | Resolved | Remaining review |
|---|---:|---:|
| 193391018 | 105 | 3 |
| 193028191 | 397 | 2 |
| 193028206 | 1,049 | 39 |
| Total | 1,551 | 44 |

Of the 44 remaining observations, 39 have zero reported ownership. The nonzero
observations are Mitch Van Vooren, Nick Vannett, Nick Singleton and Matt Hibner
(Vannett appears in two slots). Missing current roster evidence, missing canonical
identity, or position conflicts prevent automatic resolution. These remain in the
contest `review/*_unresolved.json` files. No ownership model was retrained.

## Evidence rules and limits

Historical rows require a native nflreadpy source-ID alias, a unique canonical
identity in both directions among archived source players, and verified schedule
context. Old rows that name their own relocated franchise as the opponent can use
a unique season/week/team schedule match; the original source is preserved.
Conflicting source snapshots or existing game keys remain in review.

The audit exposed **27 legacy canonical identities shared by distinct source
players**. The initial backfill's uniqueness checks surfaced overlapping games;
3,198 newly inserted affected rows were then reversed and preserved in a quarantine
artifact. No pre-existing rows were removed. The final planner rejects these
collisions before writing, even when the players never appear in the same game.
The current review set contains **3,266 source rows** for identity collisions and
**two existing game conflicts**: Adam Thielen (2025 Week 1) and Isaiah Hodgins
(2025 Week 11). Of these, 41 identity-review rows and both game conflicts are in
2025. These require a separate canonical split/game-provenance repair; existing
records are not assumed correct simply because they were preserved.

Salary repair uses an existing DraftKings native alias first, then exact
season/week/team/position plus normalized roster alias linked through GSIS ID,
then a unique persisted alias with matching team and position. It never joins on
display name alone or creates a new canonical player from a name.

New actual scores retain negative points and do not deduct missed-kick penalties,
consistent with [DraftKings' published offense and kicker scoring](https://dknetwork.draftkings.com/2020/12/08/how-to-play-classic-and-showdown-nfl-snake-drafts-on-draftkings/).
Legacy model callers retain their existing scoring defaults; this repair does not
retrain models or rewrite previous predictions. Historical actuals are reconstructed
from archived stat fields, not certified contest results.

## Repeatable workflow

Audit first; omission of `--apply` means no database writes:

```sh
python scripts/product/repair_data_completeness.py \
  --through-season 2025 --salary-season 2026 --salary-week 1 \
  --output artifacts/data_completeness
```

Add `--apply` to insert missing, unambiguous actuals and fill null salary identities.
The script saves a content-addressed plan before its transaction, then records the
inserted raw IDs and repaired salary IDs. These identify the exact changed keys
and original ingest runs for review or a scoped reversal. Keep the evidence directory.
The historical cutoff must precede the current salary season. No schema migration
is required for this repair.

After salary repairs, run the existing [ownership reconciliation workflow](CONTEST_OWNERSHIP_RECONCILIATION.md).
Old unresolved audit observations remain immutable; use the newly generated
`review/summary.json` and `*_unresolved.json` files for the current state.

The final apply rerun inserted **zero actuals** and repaired **zero salaries**.
The original 936,661 contest standings entries and null projected-ownership values
were verified. The retained backfill, collision reversal, and final audit are in:

- `artifacts/data_completeness/c1480e9b195e32b2e8c8a06d756f201ab72a907de3ce4592f097739734989c9f/`
- `artifacts/data_completeness/5fb63239bd7fcc7bec3a81a2c2fbf8c1459fe5cbb2adcf6317e6d9a327bf6b7b/`
- `artifacts/data_completeness/verification.json`

This command is an explicit archive reconciliation tool. The older feature-matrix
adapter is still incomplete as a standalone source of historical coverage; rerun
this audit after new archives are ingested.

## Validation

594 backend tests passed, including native-ID collisions, source conflicts, roster
team/week/position checks, negative actual scores, and missed-kick handling. The final
apply rerun was idempotent, and `git diff --check` passed.
