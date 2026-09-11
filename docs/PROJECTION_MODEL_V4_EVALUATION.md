# Projection Model V4 Opportunity-Context Evaluation

Date: 2026-09-08

## Outcome

The opportunity-context implementation is complete as a challenger path, but it
is **not approved for promotion**. It fixes eligibility, backup-QB, identity,
input-lineage, opportunity-reallocation, kicker-coverage, and optimizer-audit
failures. It does not manufacture current depth-chart or injury facts, and the
active Wednesday slate currently has no stored pregame context rows.

The full-pool challenger projection run is
`c5955864-6df5-493f-bfa7-5ca557bc1382`. The governed active run remains
`3868cdda-7380-4e99-83a9-80f14894b5b0`.

## Model decision

Adding lagged opportunity columns directly to the shared gradient-boosting
feature set was tested and rejected:

| Candidate | 2025 W10-W18 overall MAE | Salary $6,000+ MAE |
| --- | ---: | ---: |
| Existing v3 feature contract | 4.1530 | 6.6525 |
| Opportunity-feature training candidate | 4.1543 | 6.7065 |

The training candidate regressed both declared cohorts, so v4 retains the
validated v3 training feature contract. Prior opportunity and current pregame
evidence instead operate as an explicit, cutoff-safe scoring context: team carry
and target opportunity is allocated before scoring, and the adjusted prior-only
player history is passed to the existing point model. This avoids promoting a
worse historical feature set while making current role assumptions visible.

## Implemented contracts

- Current evidence is append-only and selected only when both `observed_at` and
  `received_at` are at or before the projection cutoff.
- Every player reference is a canonical `player_master_id`; no context or
  opportunity join uses a raw display name.
- Current unavailable players lose opportunity before scoring; remaining team
  opportunity is redistributed by explicit shares when supplied, otherwise by
  strictly lagged shares with a disclosed DraftKings-salary fallback for players
  without prior NFL opportunity.
- Confirmed/inferred starting-QB evidence produces one full-probability QB per
  team and zero projection for backups. Ambiguous multi-QB slates fail closed.
- Projection API rows expose the exact feature and context lineage used.
- Kicker scoring requires prior canonical game history and temporarily uses a
  60% roll-three / 40% roll-eight history anchor. The shared gradient-boosting
  model is not extrapolated to an unseen position.
- Optimizer runs retain the initial, included, and excluded pools plus a reason
  for each excluded player.

## Current-slate evidence

The challenger contains all 37 eligible salary players. Its persisted optimizer
smoke run `4f9a6f4d-1a8f-46a6-a6a2-a4e5c7ed3139` completed with 33 included
players and four excluded backup quarterbacks. The four backups have zero mean
and P90. Both kickers have nonzero, history-anchored projections, and all player
UUIDs resolve to names.

The structural results are therefore working. The football-role result is not
yet trustworthy: there are zero current pregame context rows, so the challenger
still uses lagged opportunity and salary fallback for players such as Mack
Hollins, DeMario Douglas, Rashid Shaheed, Jadarian Price, and George Holani.
Henderson's questionable status also has no stored availability decision.

## Promotion requirements

1. Store cited, timestamped role/share and injury evidence for the active slate.
2. Rerun projections and inspect the complete 37-player pool and lineage.
3. Validate role-sensitive players and both kickers against an agreed football
   expectation or historical gate.
4. Record a named governance evaluation and promotion decision. Do not move the
   active pointer merely because the challenger is newer.

## Verification

- Backend: 478 tests passed.
- UI: 13 tests passed.
- UI type-check and production build passed.
- `git diff --check` passed.
