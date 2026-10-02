# Sunday Main pre-lock priority workflow

Until the Week 2 Sunday Main slate locks, development and validation should stay
on `classic_small_field_gpp`. Showdown retrospective work and projection
architecture changes are deferred.

## Pre-lock sequence

1. Load the newest injury, roster, and participation evidence.
2. After results ingestion, rebuild the completed week's player-game feature
   matrix so pregame placeholder outcomes cannot become training labels.
3. Build a new Sunday projection. Preserve its run ID and cutoff. Projection
   lineage must show a valid completed-training-outcome audit.
4. Refresh slate-aware ownership with `POST /api/ownership/run`. Ownership is
   diagnostic until its coverage, timestamp, matching, and historical metrics
   pass review.
5. Run `classic_small_field_gpp` with 120 candidates. The report must retain all
   candidates in `all_candidates`.
6. Regenerate the calibrated football-core handoff for the selected projection.
7. Run `scripts/audit_sunday_main_priority.py` with the current and prior
   optimizer/core artifacts.

The audit reports complete Week 1 targets, carries, shares, snaps, roster and
injury status, role confidence, stale evidence, candidate-impacting eligibility
flags, ownership coverage, full-pool concentration, top-20 role construction,
underrepresented core players, the selected lineup, five closest alternatives,
and changes from the prior run.

## Commands

```bash
PYTHONPATH=. .venv/bin/python scripts/validate_offensive_centrality.py \
  --projection-run-id PROJECTION_RUN_ID \
  --output artifacts/sunday-football-core-current-2026w2.json

PYTHONPATH=. .venv/bin/python scripts/audit_sunday_main_priority.py \
  --optimizer artifacts/sunday-main-current-full-2026w2.json \
  --core artifacts/sunday-football-core-current-2026w2-optimizer-shadow.json \
  --previous-optimizer artifacts/sunday-football-sanity-source-full-2026w2.json \
  --previous-core artifacts/sunday-football-core-2026w2-optimizer-shadow.json \
  --output artifacts/sunday-main-priority-readiness-2026w2.json

PYTHONPATH=. .venv/bin/python scripts/validate_sunday_candidate_exploration.py \
  --optimizer artifacts/sunday-main-current-full-2026w2.json \
  --core artifacts/sunday-football-core-current-2026w2-optimizer-shadow.json \
  --readiness artifacts/sunday-main-priority-readiness-2026w2.json \
  --variants-per-family 2 \
  --output artifacts/sunday-main-candidate-exploration-2026w2.json

PYTHONPATH=. .venv/bin/python scripts/validate_espn_projection_sanity.py \
  --espn-html artifacts/espn-mike-clay-week2-dk-2026.html \
  --optimizer artifacts/sunday-main-current-full-2026w2.json \
  --exploration artifacts/sunday-main-candidate-exploration-2026w2.json \
  --output artifacts/sunday-main-espn-projection-sanity-2026w2.json

PYTHONPATH=. .venv/bin/python scripts/validate_sunday_projection_robustness.py \
  --comparison artifacts/sunday-main-espn-projection-sanity-2026w2.json \
  --exploration artifacts/sunday-main-candidate-exploration-2026w2.json \
  --optimizer artifacts/sunday-main-current-full-2026w2.json \
  --core artifacts/sunday-football-core-current-2026w2.json \
  --output artifacts/sunday-main-projection-robustness-2026w2.json

PYTHONPATH=. .venv/bin/python scripts/validate_sunday_full_robustness_resolve.py \
  --projection-run-id 8a516c2e-7394-4cad-8e58-759e708dc790 \
  --espn artifacts/sunday-main-espn-projection-sanity-2026w2.json \
  --core artifacts/sunday-football-core-current-2026w2-optimizer-shadow.json \
  --prior-candidates artifacts/sunday-main-candidate-exploration-2026w2.json \
  --global-variants-per-family 3 \
  --qb-variants-per-family 1 \
  --output artifacts/sunday-main-full-robustness-resolve-2026w2.json
```

The candidate-exploration command is a local, read-only shadow. It follows the
production pool-safety, player-context, strategy-gate, and opponent-exclusion
order; verifies that the saved production leader and objective decomposition are
reproduced; then retains constrained candidates for the top ten QB families,
four stack shapes, competitive core players, and named with/without tests. It
does not change production projections, P90, role evidence, selector weights, or
the saved optimizer result.

The Week 2 bounded run produced 227 distinct legal candidates from 247 exact
solves. Per-family exact solves made the requested 500-candidate target
impractical for a pre-lock refresh, so the artifact states the achieved scope.
Ownership is complete for all 227 candidates; Kirk Cousins and Malik Willis are
explicitly missing from the source ownership run but do not enter these retained
lineups. Injury flags resolve from current pregame status before generic status.

The ESPN sanity command compares the frozen local projection and 120-candidate
pool with a versioned Mike Clay DraftKings value-sheet snapshot. It reports every
deterministically matched player, exact match method, unmatched rows, value per
$1,000, candidate exposure, material projection gaps, zero-exposure Great values,
and QB-family coverage from the existing exploration artifact. It is read-only:
it neither blends the external projections nor generates or selects lineups.
ESPN's published table omits players it projects below four DK points, so coverage
is explicitly partial. A 2.5-point difference is the diagnostic materiality
threshold; no production rule follows automatically from a flag.

The robustness command rescales means only inside the serialized 227-candidate
shadow. P90, context inputs, correlation rules, ownership, and production data
remain unchanged. It reports one-player 25%/50% ESPN shrinkage, simultaneous
25%/50%/100% diagnostic stress, top-20 representation, QB-family movement,
serious-lineup ranks, model risk for shortlist ranks 1/6/12/19, and truncated
calibration summaries. A player absent from the frozen universe is explicitly
reported as unidentifiable; the command does not imply that changing his mean
could make an unavailable lineup selectable.

The full robustness re-solve regenerates candidates independently for control,
25% ESPN shrinkage, and 50% ESPN shrinkage. Each stress level has a mean-only
ceiling treatment and a spread-preserving treatment where the local P90-minus-mean
spread is retained. Diagnostic QB eligibility is the union of leading local,
scenario, and external value and raw-mean ranks plus QBs within the configured
value gap; this affects search breadth only. The bounded pre-lock run keeps one
best lineup per exact QB stack family and three global variants per stack family.
It separately marks prior shortlist lineups that were rescored but not recreated,
and measures robust-frontier regret against the best evaluated serious lineup so
generator misses cannot produce negative regret. Production projections, saved
candidates, selector weights, and contest logic remain unchanged.

## Stable candidate archive and Sunday final decision

Week 2 Sunday Main now uses a persistent canonical-ID candidate archive at
`artifacts/sunday_main_candidate_archive/2026w2/archive.json`. Every refresh also
writes an immutable snapshot beneath its `snapshots/` directory. Candidate
discoveries retain the source path, JSON path, SHA-256, source rank, and first/last
seen timestamps. Later generators add to this union and cannot silently delete a
previous legal lineup.

The corrected baseline union contains 352 unique archived lineups and all 352 pass
the current hard rules. The earlier archive-only validator incorrectly rejected 90
otherwise legal lineups because they lacked a bring-back. Bring-back remains a
stack classification and correlation input, but it is not a Classic legality rule.
The complete union rescoring reproduces A/B/C at ranks 1/6/7. The baseline report
is `artifacts/sunday-main-final-decision-baseline-2026w2.json`; the pre-fix report is
retained as `artifacts/sunday-main-final-decision-baseline-2026w2-before-legality-fix.json`.

Sunday morning is one gated process:

1. Refresh official inactives, starting-QB evidence, injuries, weather, markets,
   ownership, and role/opportunity inputs through their existing app or provider
   workflows.
2. Run production projections and generate the current production and expanded
   candidate artifacts.
3. Copy `artifacts/sunday-main-refresh-manifest-2026w2-template.json`, record each
   domain's exact refresh timestamp, run ID, and source, and set its status to
   `refreshed` only after that step succeeds.
   Version 2 treats operator/news statements as claims until they have a source,
   observation time, and `verified` state. A source that was checked but had no
   usable data is `verified_unavailable`; missing evidence is never converted to
   zero. The required roster-mapping preflight reconciles the DraftKings team,
   current roster team, opponent, and starting-QB evidence before selection.
   Preserve the controlled pass order in the manifest so a market-only delta is
   not attributed to injury or opportunity changes.
4. Run the command below. `--require-complete-refresh`, `--refresh-after`, and
   `--require-lineage-match` fail before final selection if evidence is missing,
   stale, or points to a different projection/ownership run.
   Add `--require-official-inactives` and `--require-confirmed-starting-qbs` near
   lock when those evidence standards are required. A prelock snapshot must say
   `not_yet_official` or `mixed_inferred_confirmed`; it cannot masquerade as
   official evidence.

```bash
PYTHONPATH=. .venv/bin/python scripts/run_sunday_main_final_decision.py \
  --projection-run-id <LATEST_PROJECTION_RUN_ID> \
  --current-artifact artifacts/<LATEST_PRODUCTION_CANDIDATES>.json \
  --current-artifact artifacts/<LATEST_EXPANDED_CANDIDATES>.json \
  --historical-artifact artifacts/sunday-main-current-full-2026w2.json \
  --historical-artifact artifacts/sunday-main-candidate-exploration-2026w2.json \
  --historical-artifact artifacts/sunday-main-full-robustness-resolve-2026w2.json \
  --archive artifacts/sunday_main_candidate_archive/2026w2/archive.json \
  --board artifacts/sunday-main-final-board-2026w2.json \
  --core artifacts/<LATEST_CORE_HANDOFF>.json \
  --refresh-manifest artifacts/<SUNDAY_REFRESH_MANIFEST>.json \
  --require-complete-refresh \
  --require-lineage-match \
  --require-roster-preflight \
  --refresh-after 2026-09-20T08:00:00-04:00 \
  --baseline-report artifacts/sunday-main-final-decision-baseline-2026w2.json \
  --entry-count <ACTUAL_CONTEST_ENTRIES> \
  --refresh-id sunday-final-2026-09-20 \
  --output artifacts/sunday-main-final-decision-2026w2.json
```

This command revalidates salary, roster positions, current eligibility,
inactive/injury removals, the single-TE rule, Denver-opponent exclusion, team/game
limits, QB stacks, and DST conflicts. It records bring-back presence for stack and
correlation diagnostics without requiring one. It then rescales no projections
and changes no selector weights: it uses the requested production projection run,
rescoring the entire legal archive with current selector, football-sanity, and
ownership/chalk inputs. The report contains the top 10, serious-consideration
rows, A/B/C movement, player-input deltas, lineup-metric deltas, and the nine
Sunday decision questions. Contest assignment remains pending unless the actual
entry count is supplied.

## Correlation and one-off shadow audit

Use the command below to test whether soft large-GPP construction rewards are
crowding one-off players out of the small-field search. It never updates the
production configuration.

```bash
PYTHONPATH=. .venv/bin/python scripts/audit_sunday_correlation_oneoffs.py \
  --projection-run-id <CURRENT_SUNDAY_MAIN_RUN_ID> \
  --variants-per-qb 5 \
  --output artifacts/sunday-main-correlation-oneoff-audit-2026w2.json
```

The audit solves control, no bring-back reward, half incremental pass-catcher
reward, zero incremental pass-catcher reward, and QB+1-only soft-construction
universes. Each QB receives independent solves, and tracked players plus leading
values from DAL-WAS, CHI-MIN, and DEN-JAX receive explicit containing-lineup
counterfactuals. Opponents of Denver remain optimizer-ineligible while their
unchanged model rows remain visible in the game audit.

If a salary file was ingested before current weekly rosters, re-ingest that same
immutable salary source through the standard ingest service after the roster
refresh. This permits deterministic current-team aliases to resolve previously
null salary identities. Rebuild the affected feature slice before projections;
the projection completeness gate must continue to fail rather than silently omit
newly resolved players.

## Decision rules

- Fix inactive, practice-squad, or otherwise ineligible players upstream.
- Prioritize missing role evidence only when the player enters viable candidates.
- Missing evidence remains missing; it is never converted to zero opportunity.
- A completed period with positive recorded opportunities and all-zero feature
  matrix outcomes is a configuration error. Rebuild the matrix; do not train.
- Ownership diagnostics may be shown before ownership affects feasibility or
  scoring. No weight changes follow automatically from an ownership refresh.
- Core/opportunity evidence is a sanity layer. It does not force familiar players
  into lineups or reward additional centrality after a lineup is already sound.
- Every refresh records projection, eligibility, role, ownership, candidate
  exposure, and selected-lineup changes.
- Pairwise ownership intersections are not selector transitions. The ownership
  shadow reports the exact piecewise-linear winner envelope and keeps pairwise
  base intersections only as supporting diagnostics.
