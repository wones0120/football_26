# Showdown Specialist Role Resolution

## 1. Implementation summary

Implemented the narrow, sourced specialist disposition. DraftKings eligibility stays separate from canonical football role; fresh LS depth evidence establishes `long_snapper` without an LS-to-TE normalization. Available unsupported specialists are explicitly excluded before generation completeness. All other readiness, freshness, identity and solver gates remain intact.

The normal TB@DAL attempt evaluated at **2026-10-07 07:07:48 EDT** remains **NOT_READY** for two availability gaps, one also missing role evidence. **Solver called: false.** The specialist blocker is resolved; no incomplete-evidence override was used.

## 2. Files changed

- `backend/app/product_services/showdown_player_context.py`: sourced role classification, shared specialist predicate, separate DFS/source positions and native-pool disposition/counts.
- `backend/app/product_services/canonical_projection_inputs.py`: remove affirmative available specialists before feature lookup; retain separate specialist exclusion metadata instead of recording them as unavailable.
- `backend/app/product_services/showdown_data_readiness.py`: evaluate generation completeness over available non-specialists; continue validating availability and role clocks across native players.
- `docs/product/showdown_data_readiness_v1.schema.json`: additive specialist disposition and semantic fields.
- `backend/app/tests/product/test_showdown_specialist_roles.py`: 31 specialist, lineage, completeness, offensive-mapping and fail-closed regression cases.
- `backend/app/tests/product/test_optimizer_questionable_preference.py`: isolate its synthetic preference-only fixture from live source readiness.
- `README.md`, `RELEASE_NOTES.md`: operator semantics and report link.
- `SHOWDOWN_PLAYER_POOL_READINESS.json`, this report: refreshed live outcome.

Evidence and the task-only patch are under `artifacts/showdown_specialist_role_resolution/`. Existing unrelated workspace edits were preserved. No dependencies, migrations, projection formulas, ownership model, v3 generator, finalist/universe policy, quality thresholds or portfolio-selection rules were changed.

## 3. Specialist-role model

The deliberately narrow source-position registry currently supports only `LS → long_snapper`. This is a football-role classification, not a DFS position alias. Additional roles require affirmative source support and explicit tests.

Exclusion requires canonical sourced context, `canonical_role=long_snapper`, `role_source_position=LS`, role source/IDs and a current cutoff-safe role observation, with no role conflict or uncertainty. Availability is assessed separately; UNKNOWN status cannot authorize exclusion, and an unavailable player retains the unavailable disposition. A valid native salary row and canonical identity are required for the specialist disposition.

`disposition=explicitly_excluded_specialist`, `generation_eligible=false`, and `exclusion_reason=unsupported_non_scoring_specialist_role` are independent of injury/unavailable, identity and projection failures. Names, salary and low projections never establish this role.

## 4. DFS-position versus football-role semantics

`position` and `dfs_position` preserve native salary eligibility. `canonical_role` stores the sourced football role, while `role_source_position` retains the provider's original position. Role source IDs, observation clocks and original facts remain in append-only canonical context evidence.

Projection preparation and readiness use the same specialist predicate. Specialists need no feature/projection or required ownership row for generation completeness. Every native salary player stays visible in the diagnostic, and successful freezes retain all native rows separately from the consumed generation pool. Existing compatible FB/HB→RB and FL/SE→WR mappings are unchanged; all other unsupported/unknown role conflicts still block.

## 5. Evan Deckers disposition

| Field | Actual refreshed evidence |
| --- | --- |
| Canonical ID | `b5fc6b3b-4041-47e5-bdf8-6190ee80ee2f` |
| Native salary row | `30553` |
| DK FLEX / CPT IDs | `44395162` / `44395214` |
| DFS position | `TE` |
| Canonical football role / source position | `long_snapper` / `LS` |
| Availability | `AVAILABLE` / `ACT` |
| Disposition | `explicitly_excluded_specialist` |
| Exclusion reason | `unsupported_non_scoring_specialist_role` |
| Role source | `nflreadpy_depth_charts` |
| Role observed at | `2026-10-07T06:02:29+00:00` |
| Role source IDs | `6ca8fa14-f4c3-5848-ab85-90331fc6222e, 00-0038817` |
| Status observed at | `2026-10-07T11:06:43.072770+00:00` |
| Status source IDs | `877431f0-6ee2-5c50-a537-b7dc7180a47c, 925578` |
| Generation eligible / blockers | `false` / none |

The full database UUID ends in `ee2f`; the request's UUID text omitted its final `f`. Identity resolution used canonical/native source keys, never the player's name. Previously saved projection/ownership rows remain auditable but are not required or consumed for this specialist.

## 6. Tests and results

- Pre-change upstream/readiness baseline: **61 passed**.
- Initial specialist/upstream/readiness/canonical projection checks: **125 passed**.
- Final relevant suites: **488 passed**, with two existing PuLP deprecation warnings, in 63.77 seconds.
- Coverage includes missing/stale/future/conflicting role facts, future receipts, unavailable/unknown status, invalid identity, native audit retention, projection/feature/required-ownership omission for specialists, ordinary/low-projection TE eligibility, compatible offensive mappings, arbitrary names, and solver ordering across remaining projection/role/market/QB blockers.

The initial wider run found two pre-existing preference-test failures. Both reproduced against the saved pre-change source (`preexisting_test_failure.txt`). That fixture now explicitly models an offline synthetic pool; production readiness is unchanged. Final output is in `validation_tests.txt`.

Command:

```sh
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  backend/app/tests/product/test_showdown*.py \
  backend/app/tests/product/test_ai_showdown*.py \
  backend/app/tests/product/test_optimizer*.py \
  backend/app/tests/product/test_canonical_projection_inputs.py \
  backend/app/tests/product/test_pregame_context.py \
  backend/app/tests/product/test_player_roles.py
```

## 7. Latest TB@DAL player-pool counts

| Disposition / coverage | Refreshed count |
| --- | ---: |
| Native salary players | 52 |
| Canonical resolved | 52 |
| Explicitly unavailable | 17 |
| Explicitly excluded specialist | 1 |
| Generation eligible | 32 |
| Unknown availability | 2 |
| Invalid salary / identity | 0 |
| Projection rows required / present | 32 / 32 |
| Feature rows present | 32 |
| Market rows present | 32 |

The unavailable count changed from 19 to 17 because two previously accepted native status observations aged beyond the unchanged 24-hour status limit. Counts were not forced to match the earlier audit. The projection rebuild was blocked; the 32 present projection/feature rows are older saved evidence from run `3f5cb036-03b2-49d8-80b7-5bbb81953b71`, not a certified new build. The separate blocked-refresh gate prevents reuse for generation.

## 8. Readiness result

**NOT_READY.** Global reasons: `player_context_unresolved, player_role_missing, player_status_missing, player_status_stale`.

Salary identity, baseline market, starting-QB evidence and ownership pass their unchanged checks. Status/role and projection refresh remain blocked. The refreshed baseline is DAL **-8.5**, game total **47.5**, implied totals DAL **28.0** / TB **19.5**; DAL is the favorite and TB the underdog. Ownership is complete and fresh, optional under the existing strategy. These are diagnostic observations, not frozen READY inputs.

## 9. Solver-called status

**False.** The normal pipeline stopped before evidence freeze and candidate generation. The new persisted run is `failed` and contains no `showdown_evidence_snapshot`.

## 10. New optimizer run

New failed attempt ID: `926f88ef-c3c5-4212-8861-e247d7887fec`. No successful optimizer run was produced.

The unchanged reference scope is 2026 Week 5 `THURSDAY_NIGHT`, strategy `showdown_gpp_portfolio_v3`, with `ai_requested_entries=2`. Execution:

```sh
PYTHONPATH=. .venv/bin/python scripts/run_live_showdown.py \
  --from-run 9cb62307-8915-49ab-97e6-5510d9f8d1a5 \
  --ai-requested-entries 2 \
  --output-dir artifacts/showdown_specialist_role_resolution/live_attempt
```

Full before/after database-row checksums prove all three protected runs unchanged: `9cb62307-8915-49ab-97e6-5510d9f8d1a5`, `2f8b72cb-395f-470f-a809-010293d6ed21`, and `38ec72e2-6966-4338-af2d-f5399deefd5b`. See `protected_runs_unchanged.json`.

## 11. Candidate count

**0 generated** in this attempt; the solver was not called. No candidate classifications were manually tuned.

## 12. AI Review Universe count

**0 generated** in this attempt. Existing universe and finalist policies were not changed.

## 13. Export paths

No Markdown/JSON AI packet was exported because readiness failed. Saved diagnostics:

- `SHOWDOWN_PLAYER_POOL_READINESS.json`
- `artifacts/showdown_specialist_role_resolution/live_attempt/SHOWDOWN_PLAYER_POOL_READINESS.json`
- `artifacts/showdown_specialist_role_resolution/live_attempt/pipeline_attempt.json`
- `artifacts/showdown_specialist_role_resolution/live_attempt/failed_run.json`
- `artifacts/showdown_specialist_role_resolution/blocker_source_evidence.json`
- `artifacts/showdown_specialist_role_resolution/live_validation.json`

## 14. Remaining blockers and exact missing facts

| Player / canonical ID | Hard-source gap | Required source fact |
| --- | --- | --- |
| David Sills V / `6bd6e435-af33-4d13-b8da-fc4296bfc7d4` | Availability UNKNOWN; role missing | Current affirmative ACT/available or IR/reserve/inactive status keyed to canonical/native identity. If available, also a current sourced offensive role. A current unavailable fact alone can authorize exclusion. |
| Baker Mayfield / `ab96444d-bab3-41d2-b4a9-b5d16fed57ff` | Availability UNKNOWN despite fresh ACT roster membership | Current authoritative game-specific availability resolving the expired OUT report; generic roster ACT and an injury row with empty report status do not clear it. Current depth-role evidence already exists. |

Sills's only retained status evidence is native DK **IR**, observed `2026-10-06T01:38:22.671786Z`, salary row `30542`, ingest `5836f40d-d633-445c-8ef0-bf240b71906b`. No matched current roster/depth fact establishes his status or role.

Mayfield's retained native DK **OUT** was observed `2026-10-06T01:38:22.671756Z`, salary row `30464`, same ingest. Fresh roster **ACT** is observed `2026-10-07T11:06:43.072770Z`, snapshot `877431f0-6ee2-5c50-a537-b7dc7180a47c`, row `924720`. The injury fact in snapshot `0193c1da-44aa-5327-890d-440b0103d3e7` has an empty report status, so it supplies no affirmative game-availability resolution. The existing stale-OUT safeguard correctly fails closed.

Projection refresh is blocked by those same unresolved canonical availability IDs (`player_context_unresolved`); this is not a specialist projection failure. No independent market, salary identity, starting-QB or ownership-required blocker remains.

## 15. Known limitations

Only long-snapper specialization is supported in this patch. Unknown or unusual offensive roles are not automatically excluded. Native salary and source evidence retain their original clocks; elapsed time can legitimately invalidate an earlier unavailable disposition. No fresh projection run, frozen READY packet or live generator result can be certified until the two source gaps are resolved. No overrides or further architectural changes were made to force readiness.

Runtime follow-up, 2026-10-07 07:17 EDT: the API and worker were still running imports loaded before this patch, causing the UI's `NON_SCORING_SPECIALIST_ROLES` import error. With zero running/queued jobs, both local services were restarted. Their runtime fingerprints now match the current projection/context source, API health is OK, and the saved optimizer-result endpoint returns HTTP 200 with the same fail-closed NOT_READY evidence. See `artifacts/showdown_specialist_role_resolution/runtime_reload_validation.json`. No additional application-code changes or optimizer runs were needed.
