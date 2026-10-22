# Offensive opportunity centrality

## Shared workload evidence

New optimizer executions serialize `workload_evidence_v2` under `strategy_runtime.player_pool.rows[*].workload_evidence` for both Classic and Captain/Showdown. The same canonical player context yields the same packet regardless of salary or CPT/FLEX assignment. QB/RB/WR/TE receive explicit evidence status; K/DST are not applicable, and unknown positions remain explicit.

Version 2 records historical target/carry counts and shares from the original `pregame_base_*` fields, with their original coverage flags. Post-allocation `targets_mean_3`/`carries_mean_3` values remain separately typed `allocated_*` proxies; they cannot certify an observed role. Missing original base fields return `original_history_unavailable`, never a made-up observed zero. `source_field` and `evidence_kind` identify every measurement. Archived v1 packets remain readable as originally stored, with their original contract ID and semantics; they are never relabeled or backfilled.

The packet separates `historical` snap/count/share values and trends, `historical_coverage` (existing policy, window and sample count), `derived_proxies` (existing projected target/carry allocations), `explicit_pregame` inputs, `availability_depth`, and `lineage`. `explicit_pregame_lineage` preserves projection-time workload attribution independently of a later availability/depth refresh; known availability/role source IDs and clocks remain separate. Existing role confidence is copied under `existing_assessment`; no new confidence score is estimated. Availability flags determine whether historical values are measured. A measured zero retains `observed`; a false flag returns `unavailable` and preserves the zero-fill separately as `stored_value`; absent flags return `coverage_unknown`. Non-null values alone do not establish measurement coverage.

Known projection/feature/context IDs and clocks are retained. Historical source row IDs, exact windows/sample counts and observation clocks absent from the saved inputs remain unavailable. The existing point-in-time input loader remains authoritative; packets suppress workload values with known clocks after the execution cutoff. A cutoff alone does not prove source chronology. Skill-player target and RB carry aggregates remain incomplete team-volume proxies, not pass/rush attempts or red-zone totals. Historical participation and derived allocations never populate explicit expected snaps/routes/targets/carries.

Selected lineup players carry `workload_evidence_ref` to the shared pool. The saved `candidate_pool_manifest` records the shared evidence hash, count and canonical linkage, without duplicating packets in every candidate variant. Learning evaluations expose saved packets once and candidate player-ID references, including missing-player IDs. Read paths do not reconstruct or backfill old snapshots. Exported optimizer HTML shows shared evidence across all pool salaries; the existing low-cost eligibility diagnostic remains a separate policy explanation.

Mean/P10/P90, physical allocation, Captain qualification, eligibility, exposures, user preferences and configuration defaults remain unchanged. Analyst measurement consumers now share version-aware selection and trace the original observation, explicit producer input or allocated proxy. Attributed explicit inputs precede observed history; un-attributed values cannot silently become producer forecasts. New v2 proxy-only values can support labeled conditional sensitivity, but cannot certify observed usage or a receiving role. Original v1 consumer behavior is retained for archived comparisons. These are corrected evidence semantics, not validation of a new allocator, model or tournament selector.

`offensive_opportunity_centrality` is a diagnostic of who receives an offense's opportunities. It does not use fantasy points, fantasy projections, ceilings, salary, ownership, DFS value, or optimizer results.

## Dimensions

Receiving centrality is anchored to target share. Route participation and snap share can modestly confirm the target evidence when available. Rushing centrality is independently anchored to carry share; snap and red-zone or goal-line evidence can confirm it. Participation by itself is capped at a low-confidence 20% fallback, and a measured zero carry share remains zero even when snap share is high.

Before combining the dimensions, each is normalized independently against the highest receiving or rushing centrality within that offense. A lead receiver and lead rusher can therefore both be central; a naturally larger carry share cannot overwhelm a smaller but team-leading target share solely because the raw scales differ.

## Football core membership

Core membership preserves four flags:

- `receiving_core`: calibrated receiving score and within-team rank.
- `rushing_core`: calibrated rushing score and within-team rank.
- `dual_threat_core`: calibrated receiving and rushing score pair.
- `overall_core`: the union of those flags and a separately calibrated combined-score flag.

Historical selection evaluates score thresholds from 0.50 through 0.90 and team-rank caps from one through three. Receiving, rushing, and combined rules maximize a transparent objective of 40% next-game top-1 recall, 40% next-game top-2 recall, and 20% precision against the next-game top two. Dual-threat thresholds maximize F1 for players with at least 15% of both next-game targets and carries. Reports retain all candidate precision, recall, false-core, and cores-per-team results instead of presenting only the selected rule.

The final football classification is derived from the independent flags. A player can therefore be a core receiving player even when the combined score ranks below multiple running backs. No player names, fantasy projections, salaries, ownership, or optimizer results participate in threshold selection.

The validation compares three overall formulations:

- `max_dimension`: the larger of receiving and rushing centrality.
- `max_plus_dual`: the larger dimension plus 20% of the smaller dimension.
- `monotonic_fitted`: a positive-coefficient linear model trained to predict next-game opportunity involvement from receiving, rushing, and dual-threat centrality.

The fitted target is `max(next-game target share, next-game carry share) + 0.20 × min(...)`. It contains no fantasy scoring.

## Point-in-time validation

For each team game, the eligible population is the union of skill players seen on that team's preceding three observed rosters. Features use only opportunity shares from earlier games. Players absent from the next game receive zero next-game opportunity; a debuting player is not retroactively inserted into the prediction population.

Run:

```bash
PYTHONPATH=. .venv/bin/python scripts/validate_offensive_centrality.py
```

The command writes JSON and Markdown reports under `artifacts/`. It compares within-team Spearman rank correlation, top-1/2/3 recall, receiving and rushing leader recall, dual-threat recognition, false-core rate, prior-roster coverage, and threshold precision/recall alternatives. The current-slate report verifies Week 1 targets, carries, shares, snaps, and Week 2 roster status for every Sunday team. Players without current usage remain explicitly labeled `stale_2025_primary`.

`artifacts/sunday-football-core-2026w2-optimizer-shadow.json` is the versioned `football_core_shadow_v1` handoff. It contains canonical player IDs, the three centrality scores, ranks, flags, union membership, classification, confidence, and evidence. It contains no optimizer weight and is not consumed by production lineup selection yet.

## Selector-only shadow experiment

Run the diagnostic against the candidates already serialized by a saved Classic
small-field optimizer result:

```bash
PYTHONPATH=. .venv/bin/python scripts/validate_selector_centrality_shadow.py
```

The script does not invoke candidate generation. It averages continuous
`overall_centrality` across RB/WR/TE lineup slots and gives positive influence
only to `high_current` evidence. Stale evidence is excluded from both the signal
numerator and denominator, so it contributes no bonus and receives no penalty.
The signal is standardized across the persisted pool,
then evaluated as `base selector objective + lambda * football_z` with exact
winner crossover points and reference lambda values.

The Week 2 saved optimizer report declares 120 candidates but serializes only its
top 50. The shadow output is exact for those 50 and explicitly does not claim a
full-pool crossover result for the 70 candidates that were not persisted. See
`artifacts/sunday-selector-centrality-shadow-2026w2.md` for the source hash,
lineup trades, player changes, top-20 movement, and decision table.

This signal remains disconnected from production projections and optimization.

## Penalty-only football sanity shadow

`scripts/validate_football_sanity_guardrail.py` evaluates the bounded alternative
to the positive centrality experiment. Core and meaningful-secondary players
receive no selector reward or penalty. Complementary and peripheral players
receive bounded deficits, while stale or unknown evidence remains unpenalized and
is reported as uncertainty. Mild Classic team-context deficits and a separate
Showdown team offensive coverage deficit are reported independently.

The shadow objective is `existing selector objective - lambda × standardized
football sanity deficit`. Deficits are scaled by the candidate-pool standard
deviation without mean-centering, so a sound lineup always receives exactly zero
penalty. The production selector is unchanged.

Classic, Showdown single-entry, and small-max reports now retain the complete
ranked candidate pool in `all_candidates` while keeping `candidates` as the
bounded presentation view. Diagnostics enforce `generated candidate count ==
serialized candidate count == analyzed count`.

The Week 2 audit is in
`artifacts/football-sanity-guardrail-shadow-2026w2.md`. The 120-candidate Sunday
Classic control lineup has zero deficit and remains selected at every requested
lambda. The original 30-candidate DET-BUF single-entry pool has materially more
known role deficits and one crossover at lambda 0.01934193. That crossover
removes a known peripheral player but introduces a player with stale/unknown role
evidence, so it is not treated as a verified football upgrade. The report also
keeps the later 40-candidate small-max pool as a supplemental comparison.
