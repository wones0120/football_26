# Week 1 contest postmortem — wones0120

**Follow-up:** Lamb’s missing historical games have now been backfilled and ownership
review has fallen from 124 to 44 observations. See the
[data completeness repair](DATA_COMPLETENESS_REPAIR.md) for current coverage and
remaining identity conflicts. Counts below describe the original postmortem run.

Analysis uses the three archived DraftKings exports, reviewed canonical salary identities, and persisted pregame projections. Results cover four entries. Fees, contest names/types, and payouts were not supplied, so profit, cash rate, and ROI are unknown.

The later Sunday Night imports expand the complete Week 1 review to 11 entries:
two opening Showdown, two Sunday Main, and seven Sunday Night. All 11 lineups
resolve canonically and 10 match saved optimizer lineups. LEARN-003 reports no
scored human interventions because Week 1 predates prospective beliefs and
LEARN-002 answers.

## Week 2 adjustments from the complete review

- Keep the current projection and optimizer scoring parameters. Sunday Main's
  8.06 player MAE includes large positive misses from Henry, Gibbs, Shough,
  Olave, and Vele in a lineup that finished top 1.54%; this one slate does not
  show that mean retuning would improve decisions.
- Submit one distinct saved lineup per paid entry. Sunday Night repeated the
  same Pickens-captain lineup twice, raising realized Pickens CPT exposure beyond
  the unique optimizer portfolio and consuming one entry without a new outcome.
- Broaden Showdown captain allocation as a prospective risk-control experiment.
  The five unique Sunday Night GPP lineups used only Pickens and Lamb at captain,
  while the seven-entry slate report shows 57% Pickens, 29% Lamb, and 14% Dart
  after including cash. For Week 2 multi-entry Showdown, use at least three
  captain choices and avoid submitting the same lineup twice; record the policy
  before lock so LEARN-003 can evaluate it.
- Preserve Classic GPP correlation construction. The Shough–Olave–Vele stack
  contributed to the top-1.54% finish, but it remains one favorable outcome and
  does not justify increasing stack weights yet.
- Capture fees, payout tiers, exact entry assignments, and final exports. These
  fill the remaining financial and submission-lineage gaps; new OPT-007 runs
  will then support direct matched-control evaluation.

## Results

| Contest / entry | Finish | Top % | Actual | Saved/reference mean | Actual − mean | Projection basis |
|---|---:|---:|---:|---:|---:|---|
| 193391018 / 5248381863 | 62,758 / 95,124 | 65.97% | 58.95 | 77.23 | -18.28 | Latest prelock reference |
| 193391018 / 5248381862 | 80,416 / 95,124 | 84.54% | 48.22 | 85.45 | -37.23 | Matching saved lineup |
| 193028191 / 5253998485 | 2,663 / 9,195 | 28.96% | 153.70 | 137.94 | +15.76 | Matching saved lineup |
| 193028206 / 5253039364 | 12,854 / 832,342 | 1.54% | 204.40 | 131.65 | +72.75 | Matching saved lineup |

A matching saved lineup establishes that the optimizer generated those players and captain assignment. It does not prove which run was exported. When several runs match, the comparison uses the latest saved match before slate kickoff; all matches remain in the JSON. The Kupp-captain entry has no exact saved match and uses a reference projection, not a claimed original optimizer decision.

## What the results tell us

- **Sunday large field:** Henry, Gibbs, Olave, Shough, and Vele exceeded their means by a combined 77.92 points. The Shough–Olave–Vele stack paid off in this outcome; one result cannot establish its expected value or validate the correlation rules.
- **Sunday 9,195-entry field:** Henry exceeded his mean by 19.24 points; Barkley missed by 7.72. This entry matches `classic_head_to_head_v1` output using a September 9 projection run. Contest classification is unknown, so verify the actual contest type before judging whether that strategy was appropriate.
- **A.J. Brown captain:** Brown missed his captain-weighted mean by 11.70, Doubs by 11.04, and Kupp by 5.22. All six players scored below their means. This is an observed projection shortfall, not proof of an optimizer defect.
- **Kupp captain:** Smith-Njigba exceeded the reference mean by 14.91, offsetting some of the Doubs, Brown, Kupp and Shaheed misses. No exact generated lineup was found.
- These runs predate matched OPT-007 controls. The rules-disabled alternative and the causal effect of optimizer scoring are unavailable. Keep the present scoring configuration until prospective controls and more contest observations support a change.

## Per-player reconciliation

Export FPTS is already captain-weighted for CPT rows. It is used once; projected base points are multiplied by 1.5 only for a reference CPT projection. Player totals reconcile to each entry score within 0.02 points. Classic FLEX ownership comes from the player’s natural-position observation.

### 193391018 — entry 5248381863

Projection run: `4dc8026d-071f-4c7b-86ec-14ecf1f30804`. Strategy: `unavailable`.

| Slot | Player | Mean | Actual | Difference | Actual ownership |
|---|---|---:|---:|---:|---:|
| CPT | Cooper Kupp | 16.08 | 8.25 | -7.83 | 1.92% |
| FLEX | Jaxon Smith-Njigba | 14.29 | 29.20 | +14.91 | 55.60% |
| FLEX | A.J. Brown | 13.40 | 5.60 | -7.80 | 40.97% |
| FLEX | Rhamondre Stevenson | 14.95 | 14.50 | -0.45 | 45.75% |
| FLEX | Romeo Doubs | 11.04 | 0.00 | -11.04 | 23.22% |
| FLEX | Rashid Shaheed | 7.47 | 1.40 | -6.07 | 18.14% |

### 193391018 — entry 5248381862

Projection run: `4dc8026d-071f-4c7b-86ec-14ecf1f30804`. Strategy: `showdown_gpp_captain_informed_v2`.

| Slot | Player | Mean | Actual | Difference | Actual ownership |
|---|---|---:|---:|---:|---:|
| CPT | A.J. Brown | 20.10 | 8.40 | -11.70 | 9.12% |
| FLEX | Drake Maye | 16.58 | 12.82 | -3.76 | 58.25% |
| FLEX | Rhamondre Stevenson | 14.95 | 14.50 | -0.45 | 45.75% |
| FLEX | Romeo Doubs | 11.04 | 0.00 | -11.04 | 23.22% |
| FLEX | Jason Myers | 12.05 | 7.00 | -5.05 | 26.11% |
| FLEX | Cooper Kupp | 10.72 | 5.50 | -5.22 | 15.04% |

### 193028191 — entry 5253998485

Projection run: `d05884f8-934d-492f-9b2b-65914d97c6b8`. Strategy: `classic_head_to_head_v1`.

| Slot | Player | Mean | Actual | Difference | Actual ownership |
|---|---|---:|---:|---:|---:|
| DST | Jaguars | 7.02 | 13.00 | +5.98 | 24.89% |
| FLEX | Derrick Henry | 19.06 | 38.30 | +19.24 | 2.19% |
| QB | Trevor Lawrence | 20.06 | 26.10 | +6.04 | 2.51% |
| RB | Chase Brown | 19.15 | 18.80 | -0.35 | 3.65% |
| RB | Saquon Barkley | 16.72 | 9.00 | -7.72 | 8.52% |
| TE | Sam LaPorta | 13.21 | 9.80 | -3.41 | 2.95% |
| WR | Parker Washington | 15.11 | 19.30 | +4.19 | 3.14% |
| WR | Michael Wilson | 15.42 | 10.60 | -4.82 | 0.75% |
| WR | Wan'Dale Robinson | 12.18 | 8.80 | -3.38 | 1.07% |

### 193028206 — entry 5253039364

Projection run: `9a67a70d-e9a1-4bd1-ada3-c7fcd9c3016c`. Strategy: `classic_large_gpp_v1`.

| Slot | Player | Mean | Actual | Difference | Actual ownership |
|---|---|---:|---:|---:|---:|
| DST | Jets | 5.60 | 9.00 | +3.40 | 12.47% |
| FLEX | Jahmyr Gibbs | 17.68 | 37.60 | +19.92 | 38.58% |
| QB | Tyler Shough | 18.87 | 29.20 | +10.33 | 8.88% |
| RB | Chase Brown | 19.15 | 18.80 | -0.35 | 9.78% |
| RB | Derrick Henry | 19.06 | 38.30 | +19.24 | 8.03% |
| TE | Sam LaPorta | 13.21 | 9.80 | -3.41 | 5.82% |
| WR | Chris Olave | 14.28 | 31.20 | +16.92 | 23.65% |
| WR | Michael Wilson | 15.42 | 10.60 | -4.82 | 3.73% |
| WR | Devaughn Vele | 8.39 | 19.90 | +11.51 | 7.88% |

## Lamb history discrepancy

Lamb’s canonical identity is `ea3f9527-a8b6-42c1-9607-5043fd3cf7c5`; its nflreadpy source ID is `00-0036358`. The raw weekly history has 2025 Week 18 = 1.4, Week 17 = 9.6, and Week 16 = 11.1 DK points. Their mean is 7.3667, consistent with the saved `player_roll3_mean` of 7.37.

The target actuals table lacks Weeks 14–17 for this player, making its latest three available records Weeks 18, 13, and 12: 1.4, 27.2, and 11.5 (mean 13.3667). The display combined these records with the model’s fuller-history average. The display now calculates its average from the displayed records; saved feature inputs and predictions are unchanged. The subsequent audited backfill restored these missing games; see the follow-up above. Do not increase Lamb’s projection to compensate for this display discrepancy.

## Ownership repair

| Contest | Resolved observations | Review observations |
|---|---:|---:|
| 193391018 | 105 | 3 |
| 193028191 | 378 | 21 |
| 193028206 | 988 | 100 |
| Total | 1,471 | 124 |

Identity evidence is restricted to the exact season/week/slate salary pool, normalized alias, compatible position/slot, unique canonical identity, DraftKings source ID, and team/opponent context. Missing or conflicting evidence never creates a new player. Many review rows have salary records whose canonical ID is still null. Counts are observations, not distinct players.

All 1,595 decisions are preserved in the append-only `target.contest_ownership_observation` table. The 1,471 resolved labels are in `dk_ownership` with actual ownership only. CPT and FLEX are separate; observed labels cannot enter the simulation’s projected-ownership fallback. No ownership model was retrained. The original 936,661 standings rows and archived ZIPs remain intact.

## Evidence and follow-up

- `artifacts/source_snapshots/contest_results/2026_week1/postmortem.json`: all entry/player comparisons and matching lineup IDs.
- `artifacts/source_snapshots/contest_results/2026_week1/review/*_unresolved.json`: review records with salary-candidate evidence.
- `artifacts/source_snapshots/contest_results/2026_week1/review/database_verification.json`: idempotency counts and original standings counts.
- Supply contest names, fees, and winnings to complete the financial result.
- Resolve remaining salary identities with native-ID or team/position evidence, then rerun reconciliation.
- Audit and backfill target historical actuals before relying on the displayed last-three history.
- For the next slate, save final prelock projections, export provenance, and OPT-007 controls so optimizer effects can be measured directly.

## Validation

584 backend tests passed. Reconciliation was rerun without duplicate audit observations
or resolved labels; all original standings entry counts were unchanged. The installed
target schema matches the migration contract, and the repository diff has no whitespace errors.
