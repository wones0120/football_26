# Showdown upstream data completeness repair

## 1. Executive result

The normal, non-override TB@DAL attempt `38ec72e2-6966-4338-af2d-f5399deefd5b` is **NOT_READY**. Every native salary player has a disposition: 33 available, 19 explicitly unavailable, 0 unknown and 0 invalid. Current feature and projection IDs match the eligible set exactly. All native rows retain baseline game market context. The remaining blocker is the sourced role/position mismatch listed below. No solver, candidates, classifications, AI Review Universe or packet was produced.

Both protected records stayed unchanged: `9cb62307-8915-49ab-97e6-5510d9f8d1a5` and `2f8b72cb-395f-470f-a809-010293d6ed21`. Full before/after representations and SHA-256 comparisons are saved in the artifact directory. No strategy, portfolio/finalist policy, quality thresholds, ownership model or AI Review Universe policy changed.

## 2. Root causes found

1. The original target projection builder intentionally removed salary OUT/IR records. The optimizer loaded all 52 native salary players and incorrectly required projections for those excluded records.
2. Market fields were selected from `projection_feature.feature_json`; that feature joined through `p.model_run_id`, `p.game_id` and `p.player_id`. Missing player projections therefore erased valid game-level market evidence.
3. Current raw roster/depth evidence had no reliable normalized per-player context feeding the consumed optimizer dataframe.
4. UTC timestamps stored without timezone require an explicit UTC interpretation when compared with aware cutoffs under a New York PostgreSQL session. The new transform now uses `AT TIME ZONE 'UTC'` for salary, roster and QB receipt filters.
5. A previous UNKNOWN derived context could have a later wrapper observation timestamp than subsequently available original facts. Canonical transform versions now select by receipt time, while status/role freshness still uses each original fact clock.
6. Exact GSIS identity matches must precede provider position labels for person-level availability. Roles retain position validation and the established FB→RB/HB→RB/FL→WR/SE→WR aliases; LS→TE has no supported normalization.
7. Structured source evidence exposed a pandas object-assignment error in the existing role resolver. Allocating object columns fixes propagation without changing role policy.
8. Week 4 completed weekly stats were loaded while the training matrix still contained zero outcomes. The explicit prepared projection cutoff correctly prohibited automatic historical repair after freezing. The normal live refresh now repairs affected completed labels through the existing builder before selecting its new cutoff.

## 3. Files changed

- `backend/app/product_services/showdown_player_context.py`: canonical merge, provenance, current-source transform and player disposition diagnostics.
- `backend/app/product_services/showdown_data_readiness.py`: sourced eligibility before completeness, native audit retention, canonical live requirement and pre-cutoff training-label refresh.
- `backend/app/product_services/optimizer.py`: cutoff-aware native/context loading, projection-independent market propagation and persisted diagnostics.
- `backend/app/product_services/canonical_projection_inputs.py`: one canonical availability contract for model targets; retained source fields and exact scoring IDs.
- `backend/app/product_services/pregame_context.py`: correct canonical transform version selection.
- `backend/app/product_services/market_snapshots.py`: shared cutoff-safe game observations and game/team pool association.
- `backend/app/product_services/player_roles.py`: structured evidence storage only.
- `backend/app/services/source_capture.py`: publication-week/row metadata and actionable empty-week errors.
- `scripts/run_live_showdown.py`: per-attempt `SHOWDOWN_PLAYER_POOL_READINESS.json`.
- Tests: new `test_showdown_upstream_data.py`, updated readiness/source-capture expectations, explicitly offline fixtures in optimizer-mode/QB-preference/team-constraint tests.
- `README.md`, `RELEASE_NOTES.md`, readiness JSON schema, this report and the machine-readable diagnostic. No dependencies, migration, configuration defaults or UI changes.

## 4. Exact six-player diagnostic matrix

All six have a native FLEX salary row, a resolved canonical UUID and a current public feature-matrix scaffold. The corrected scaffold query uses `player_master_id`, not the matrix’s native `player_id`. All six were absent from both the target feature set and projection set behind `cc840626-bf4c-420d-b122-bb24834b00d7`. These are different layers.

| Player | Native salary row | Canonical UUID | Team/position | Original salary status | Current sourced status | Role evidence / starter relevance |
|---|---:|---|---|---|---|---|
| Jalen McMillan | 30541 | `277beb1a-8cf5-4ac1-8e85-ef6bef47c861` | TB WR | IR | RES — nflreadpy_weekly_rosters | expected_backup; No QB starter dependency |
| David Sills V | 30542 | `6bd6e435-af33-4d13-b8da-fc4296bfc7d4` | TB WR | IR | IR — draftkings_salary_status | uncertain; No QB starter dependency |
| Baker Mayfield | 30464 | `ab96444d-bab3-41d2-b4a9-b5d16fed57ff` | TB QB | OUT | OUT — draftkings_salary_status | expected_starter; QB1 depth listing; explicit slate starter relationship remains independently resolved; unavailable QB is excluded |
| Princeton Fant | 30550 | `f02234e9-51a0-4f0b-9d18-595682dee106` | DAL TE | IR | RES — nflreadpy_weekly_rosters | expected_backup; No QB starter dependency |
| Malik Davis | 30538 | `f433daaa-31db-4612-8e40-8d5589bc7414` | DAL RB | IR | RES — nflreadpy_weekly_rosters | expected_backup; No QB starter dependency |
| DJ Rogers | 30551 | `f4908421-09b5-40cd-98e6-2dcebadfc7d8` | DAL TE | IR | RES — nflreadpy_weekly_rosters | expected_backup; No QB starter dependency |

| Player | Status source/clock | Market in original consumed row → repaired native audit | Target feature/projection, original → current | Stage/reason and expected treatment |
|---|---|---|---|---|
| Jalen McMillan | nflreadpy_weekly_rosters / `2026-10-07T01:11:28.751896+00:00`; IDs `1f00c392-c96d-511e-99b1-83674d4834f0, 923534` | Missing → present | Absent/absent → correctly absent/absent | Projection eligibility filter originally removed this player; player-specific projection join erased market. Current roster RES confirms unavailable salary IR; depth may remain listed despite reserve status. Explicitly exclude before completeness; preserve native audit. |
| David Sills V | draftkings_salary_status / `2026-10-06T01:38:22.671786+00:00`; IDs `30542, 5836f40d-d633-445c-8ef0-bf240b71906b` | Missing → present | Absent/absent → correctly absent/absent | Projection eligibility filter originally removed this player; player-specific projection join erased market. Current native IR remains the only affirmative unavailable source; missing role is not needed for exclusion. Explicitly exclude before completeness; preserve native audit. |
| Baker Mayfield | draftkings_salary_status / `2026-10-06T01:38:22.671756+00:00`; IDs `30464, 5836f40d-d633-445c-8ef0-bf240b71906b` | Missing → present | Absent/absent → correctly absent/absent | Projection eligibility filter originally removed this player; player-specific projection join erased market. Current DK OUT overrides generic active-roster presence; QB depth listing does not clear availability. Explicitly exclude before completeness; preserve native audit. |
| Princeton Fant | nflreadpy_weekly_rosters / `2026-10-07T01:11:28.751896+00:00`; IDs `1f00c392-c96d-511e-99b1-83674d4834f0, 923153` | Missing → present | Absent/absent → correctly absent/absent | Projection eligibility filter originally removed this player; player-specific projection join erased market. Current roster RES confirms unavailable salary IR; depth may remain listed despite reserve status. Explicitly exclude before completeness; preserve native audit. |
| Malik Davis | nflreadpy_weekly_rosters / `2026-10-07T01:11:28.751896+00:00`; IDs `1f00c392-c96d-511e-99b1-83674d4834f0, 922904` | Missing → present | Absent/absent → correctly absent/absent | Projection eligibility filter originally removed this player; player-specific projection join erased market. Current roster RES confirms unavailable salary IR; depth may remain listed despite reserve status. Explicitly exclude before completeness; preserve native audit. |
| DJ Rogers | nflreadpy_weekly_rosters / `2026-10-07T01:11:28.751896+00:00`; IDs `1f00c392-c96d-511e-99b1-83674d4834f0, 924045` | Missing → present | Absent/absent → correctly absent/absent | Projection eligibility filter originally removed this player; player-specific projection join erased market. Current roster RES confirms unavailable salary IR; depth may remain listed despite reserve status. Explicitly exclude before completeness; preserve native audit. |

The salary import is `5836f40d-d633-445c-8ef0-bf240b71906b`. Native status clocks remain the original import/capture clocks; rebuilding contexts does not refresh them. David Sills V has no mapped current roster/depth fact in the selected source set; Baker Mayfield has ACT roster evidence and QB1 depth evidence but is explicitly OUT in the native source. McMillan, Fant, Davis and Rogers have current RES roster evidence. Original absence of curated injuries/pregame context for these six is retained in `upstream_before.json`.

## 5. Salary-pool disposition design

`native DraftKings salary pool → canonical identity → sourced availability → eligible model pool → feature/projection completeness → frozen input → existing strategy filters`

Every native row receives exactly one disposition: `generation_eligible`, `explicitly_unavailable`, `unknown_availability` or `invalid_salary_or_identity`. Only fresh, cutoff-safe affirmative unavailable facts permit exclusion. UNKNOWN and invalid records hard-fail. The availability-defined eligible set includes players whose role still needs resolution; existing backup-QB, kicker and user-preference selection rules remain downstream and unchanged.

Feature/projection/market/ownership completeness uses the eligible set. Status assessment still covers every individual native player. Team DST records use the existing team-defense exception, not an invented individual injury designation. READY freezes retain `native_player_pool` for excluded model assessments and source reasons, while `player_pool` contains precisely the eligible input passed to generation. Failed attempts persist the complete disposition diagnostic without freezing or generating.

## 6. Canonical player-context design

`canonical_showdown_player_context_v1` uses canonical UUIDs and native GSIS aliases; no raw display-name join is added. Facts retain team, native/provider position, kind, source URI/IDs, observation clock and receipt clock. Availability and role clocks are independent. The existing append-only context service persists the transform; JSON evidence requires no schema migration.

Only observations and receipts at or before cutoff are visible. Current same-kind facts supersede older facts; equal-clock contradictions fail deterministically. A current game-specific OUT overrides generic ACT roster membership. Reserve/practice-squad status remains unavailable unless a newer authoritative activation resolves it. A stale game-specific OUT cannot be cleared by generic roster presence. Empty injury reports and probability defaults never establish ACTIVE.

Role evidence comes from current depth facts or the independent explicit starting-QB relationship. Source position conflicts without an existing normalization are recorded and block role readiness. Original manual workload/risk context is retained with provenance and is not refreshed by the derived wrapper. Repeated captures/context builds retain original source clocks. Canonical versions select by receipt, then all original field clocks are validated before freeze.

## 7. Status/role provider findings

Installed nflreadpy is 0.1.5. The application calls `load_rosters_weekly(seasons=[2026])` and filters the requested season/week. The fresh provider inspection contained 13,004 season rows, weeks 1–5 and 2,392 Week 5 rows. The normal collector curated 2,391 rows. This demonstrates that the earlier empty Week 5 result was not a persistent query/schema bug. The most likely explanation is a publication gap; the exact upstream publication time cannot be reconstructed from the earlier error alone. Provider metadata now preserves available weeks and pre-filter row counts. [Weekly roster API](https://nflreadr.nflverse.com/reference/load_rosters_weekly.html), [nflreadpy loaders](https://nflreadpy.nflverse.com/api/load_functions/).

Injury inspection contained 1,052 records, weeks 1–4, and no Week 5 reports. Empty injury capture supplies no ACTIVE evidence. Depth inspection contained 613,196 rows; the selected TB/DAL observation was `2026-10-06T14:08:49Z`. Depth has source GSIS IDs and position/rank columns; current roster ACT establishes pregame eligibility rather than game-day clearance. [Depth dictionary](https://nflreadr.nflverse.com/articles/dictionary_depth_charts.html). The current observations and raw snapshots are saved in the artifacts.

## 8. Market propagation root cause and repair

The previously successful baseline capture `5c8ee189-d355-58af-8dd8-e1ffd3359d29` was valid; loss happened through the player projection/feature join. The shared canonical market loader now filters completed ingest observations by original observation and receipt clocks. The pool adapter matches canonical season/week, teams and native kickoff; it reuses the projection market transform before readiness and freeze.

Final baseline: total 47.5, DAL spread -8.5, TB spread 8.5, implied totals DAL 28.0 / TB 19.5. DAL is favorite, TB underdog. This is the latest source observation, not a copied value from the old capture. All 52 native rows and all 33 eligible rows have baseline context before readiness. A missing projection or unrelated bad player join cannot erase it.

## 9. Projection completeness root cause and repair

The original 46/52 count reflects the six native OUT/IR exclusions, rather than six missing identities. Current sourced roster evidence adds development/practice-squad exclusions, so the correct denominator is now 33. The canonical projection loader overlays current source status, excludes affirmative unavailable states, rejects UNKNOWN, and retains the exact eligibility/scoring IDs in feature lineage. It does not create zero projections to fill missing rows.

The final completed projection run is `3f5cb036-03b2-49d8-80b7-5bbb81953b71` with feature run `6da0c308-c739-4e5c-a7c1-7206765c37b2`. DB verification proves the 33 feature UUIDs, 33 projection UUIDs and the availability-defined eligible set are identical. No unavailable player has a required model row. The live pre-cutoff training refresh rebuilt 787 completed Week 4 rows; the existing outcome/leakage guard and explicit historical-cutoff protection remain enabled. Current Week 5 rows are never training labels.

## 10. Tests/results

Final validation: **363 passed** across upstream-disposition, readiness, canonical projection, source capture, packet, finalist audit, role evidence, preparation, optimizer modes, production/research parity, QB preferences, soft scenarios and team constraints. See `validation_final.txt` for the complete command result. Python compilation passed for all changed runtime modules/scripts.

Coverage includes ACTIVE/OUT/inactive/IR/PS, missing injury not ACTIVE, stale/future clocks, deterministic conflicts, every native disposition, no projection requirement for excluded players, eligible projection/feature failures, native GSIS matching, independent market propagation, exact model target IDs, structured role evidence, independent QB/ownership checks, pre-cutoff training-label refresh and no solver call while unresolved. Older synthetic strategy fixtures are explicitly offline; live tests exercise the actual gate. No thresholds or solver expectations were relaxed.

## 11. Latest TB@DAL pipeline result

Attempt `38ec72e2-6966-4338-af2d-f5399deefd5b`; readiness **NOT_READY**; evidence cutoff `2026-10-07T01:27:58.034508+00:00`; `ai_requested_entries=2`; original scope/strategy/user controls retained. All source refreshes completed, including current projections and ownership. Solver called: **false**; candidate count: **0**; AI Review Universe count: **0**; packet/export count: **0**. This failed readiness audit is saved as a new local optimizer record.

Current projection `3f5cb036-03b2-49d8-80b7-5bbb81953b71`; feature `6da0c308-c739-4e5c-a7c1-7206765c37b2`; ownership `2f8e8728-6c98-41a1-968e-ff7a1c4051bc` (`slate_aware_ownership_v2_prelock`, 104 CPT/FLEX rows). QB readiness is READY for two sourced provisional selections. No failed source report is mistaken for a completed refreshed build.

Intermediate attempts and their logs are retained. They exposed the structured-evidence assignment, timezone/context-version propagation and stale training-label issues; the final result supersedes them.

## 12. New successful optimizer run ID if READY

None. The new attempt is a failed readiness audit, not a generated optimizer portfolio. No frozen READY snapshot or AI packet is claimed.

## 13. Remaining blockers if NOT_READY

Global reason codes: `player_role_missing, player_role_position_conflict, player_status_missing`. `player_status` is the existing combined availability/role source group; its `player_status_missing` code in this result is caused by the missing compatible role clock, not UNKNOWN availability. Individual diagnostics distinguish these facts.

| Player | Canonical ID | Current availability | Native position | Current provider depth position | Missing resolution |
|---|---|---|---|---|---|
| Evan Deckers | `b5fc6b3b-4041-47e5-bdf8-6190ee80ee2f` | ACT from nflreadpy_weekly_rosters | TE | LS | Compatible current role/source clock or authoritative native position correction; do not fabricate an offensive role or silently exclude |

Hunter Luepke’s FB listing is compatible with native RB under the existing identity normalization and now carries a sourced starter role. Evan Deckers’ LS listing has no established TE-role interpretation. The underlying source facts exist; the unresolved fact is a compatible, sourced fantasy-position role. A corrected authoritative native/canonical position or an explicitly sourced canonical role is required before READY. This is not a failed market fetch, QB identity failure or missing eligible projection.

## 14. Player-pool readiness summary

| Stage | Count |
|---|---:|
| canonical_resolved | 52 |
| explicitly_unavailable | 19 |
| feature_rows_present | 33 |
| generation_eligible | 33 |
| invalid_salary_or_identity | 0 |
| market_rows_present | 33 |
| native_salary_players | 52 |
| projection_rows_present | 33 |
| projection_rows_required | 33 |
| unknown_availability | 0 |

Additional checks: baseline market present for 52/52 native rows; CPT/FLEX ownership present for 52/52; public scoring scaffold contains all 52 native canonical players; exactly 33 current target features/projections. The 33 eligible assessment rows include two team defenses. The remaining available role conflict blocks readiness even though that player has a valid numeric projection.

## 15. Exact normal workflow after the repair

Use **Run Optimizer** for the live Showdown slate. The central job handler now performs native identity repair → baseline market → weekly roster/injury captures → independent QB evidence → canonical player contexts → completed training-label refresh → frozen-source preparation/current projections → ownership → exact consumed pool assessment → persist READY freeze → unchanged generator/classifier → AI Review Universe export. Any unresolved required fact stops before freeze/generation. A repeat refresh creates a new attempt.

```sh
PYTHONPATH=. .venv/bin/python scripts/run_live_showdown.py \
  --from-run 9cb62307-8915-49ab-97e6-5510d9f8d1a5 \
  --ai-requested-entries 2
```

No incomplete-evidence option was used. The API/worker were restarted only when the operational queue was idle, and health was verified. The existing request-entry count remains independent of optimizer lineup count.

## 16. Known limitations

- Current roster ACT is affirmative pregame roster eligibility, not final inactive-list/game-day clearance. Week 5 injury reports were still absent at inspection.
- Observation time for roster/native salary evidence can be capture/import time when the provider supplies no publication clock. Source clocks are preserved; repeated builds cannot renew them.
- Source-specific role/position conflicts require authoritative resolution. No LS→TE mapping, synthetic role, fake projection or policy exclusion was added.
- The real result did not reach freeze/generation, so candidate football classifications cannot be inspected on a new packet. Market/favorite/implied-total and projection inputs were verified directly before the gate; READY end-to-end freeze/packet paths remain covered by tests.
- No migrations, new dependencies, default age changes or UI changes were required. Earlier unrelated checkout changes remain untouched. No commits or remote publication were requested.

Artifacts: [new player diagnostic](SHOWDOWN_PLAYER_POOL_READINESS.json), [final attempt](artifacts/showdown_upstream_repair/20261007T005459Z/confirmed_result/pipeline_attempt.json), [exact model-pool proof](artifacts/showdown_upstream_repair/20261007T005459Z/final_model_pool_proof.json), [protected-run proof](artifacts/showdown_upstream_repair/20261007T005459Z/protected_run_preservation.json), [tests](artifacts/showdown_upstream_repair/20261007T005459Z/validation_final.txt).
