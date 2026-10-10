# Showdown data readiness implementation

## Projection rerun after an injury import

The October 8 Models projection job `1a64a04f-fb4c-463d-b2af-b1d48152220e`
failed on 47 stale canonical availability records after FanDuel ingest
`a7c37cf0-8efe-4e7a-a9d3-34feb8569176` completed with 51 resolved rows and no
unresolved identities. The direct projection handler refreshed only starters;
it did not compose the imported injury rows or collect current roster evidence.
Blank injury indicators correctly supplied no affirmative availability facts.

Live native Showdown **Run projections** now shares the optimizer's roster,
raw injury, official NFL status, starter and canonical-context collectors.
The worker saves a JSON-safe refresh report and freezes the projection cutoff
after those reads. Explicit cutoff runs skip collection, and Classic and locked
historical slices retain their existing path. Fresh saved evidence is still
required after provider outages; source clocks and freshness limits are unchanged.
Unresolved official identities or a failed context transform stop before scoring.

UI acceptance: projection run `f877d45e-2ee8-4014-8c8f-90e03f1c688a`
(job `6279ccbc-f699-4715-8e90-a588bb625327`) completed with 32 persisted
projections. All five player refresh stages completed; 52 canonical contexts
resolved to 33 available and 19 unavailable, with zero unknowns and one existing
non-scoring specialist exclusion. Saved feature lineage consumed every refreshed
context ID, including the uploaded file's seven explicit injury facts. The
projection request and original failed audit were preserved. Validation: 135
targeted tests passed; see `artifacts/projection_injury_refresh_repair/validation_summary.json`
and `completed_projection_ui.png`. This verifies projection generation, not the
separate model calibration or final entry-clearance gates.

## Evening recurrence and automatic official reports

The morning service-level validation did not establish a durable repair. The
user's October 7 evening UI run `b7f8870a-e342-44b9-a53b-6035340bf7d1` failed
after the Mayfield article's publication crossed the 24-hour limit. The freshly
requested nflverse injury payload still had no game designation, so canonical
availability correctly remained unknown. The failure and original clocks are
preserved under `artifacts/showdown_preflight_repair/ui_recurrence/`.

Live Showdown refresh now captures `https://www.nfl.com/injuries/league/{season}/reg{week}`
before composing canonical contexts. The collector requires the selected
season/week and both slate teams, reads explicit game designations separately
from practice participation, and ignores unpublished reports for other games.
Blank game designations never become ACTIVE. Raw response body, HTTP headers,
receipt/observation clocks and body checksum are retained as an immutable source
snapshot. The live-table observation respects upstream HTTP Date/Age; it does not
renew the publication clock of an archived article or change the freshness limit.

New profile keys require a unique normalized name plus matching canonical team
and position. Successful keys persist in `player_alias`; later reads use that
source key. Conflicts and unresolved mappings enter `target.identity_quarantine`
and stop projection rebuilding. The canonical composer retains the original
source facts. Readiness exceptions name affected players while the saved report
retains machine reason codes and per-source diagnostics.

The end-to-end acceptance run `ccb5ab65-426f-4293-bb58-391182f1cb33` was submitted
through **Run Optimizer** and completed on the durable worker. It passed READY,
captured official status itself, preserved all failed-request controls, and saved
four lineups. The fifth remains prevented by the existing quality/exposure caps.
Its frozen checksum, 32 complete eligible-player inputs, unchanged failed audit,
legal saved lineups and zero unknown availability records were verified. All 168
targeted backend tests pass. The result and validation are recorded in
`artifacts/showdown_preflight_repair/ui_recurrence/validation_summary.json`.

## Current saved-input preflight

`/api/slate/readiness` now uses the optimizer's native player-pool loader and
`showdown_data_readiness_v1` for live native Showdown slates. It assesses the
latest completed projection alongside saved canonical contexts and market inputs
at the current observation cutoff, without source refresh, rebuild, solve or
evidence freeze. Required source failures add blocking checks to both Showdown
gates, with original clocks, affected canonical IDs, player names and remediation.
An assessment read failure blocks rather than falling back to a coverage-only READY.
Classic/prediction/replay gates and historical coverage behavior remain unchanged.

The response adds `showdown_data_readiness`. Operations labels its successful
assessment **Saved inputs ready** and shows the assessment time; absent assessment
shows **Generation readiness unchecked**. **Refresh Status** works before any
optimizer run, and attempts recheck preflight after source refresh or failure.
Run Optimizer still owns the final refreshed assessment and immutable generation
freeze. Saved-input readiness never certifies final entry clearance.

The October 7 status supplement captures the [official current TB Reserve/Injured
roster](https://www.buccaneers.com/team/players-roster/) for David Sills V and the
[Week 5 team article](https://www.buccaneers.com/news/buccaneers-cowboys-top-storylines-key-matchups-week-five)
stating Baker Mayfield remains out. It appends sourced pregame facts by the affected canonical UUIDs with native
DraftKings identity proof. The roster retains its capture observation clock;
the article retains its publication clock. Original native OUT/IR observations,
prior optimizer records and source snapshots remain intact. Audit files and the
new normal run outcome are under `artifacts/showdown_preflight_repair/`.

Canonical refresh reads visible source history before deduplicating original
facts and composing the per-player assessment. This prevents an earlier-published,
newly received game-status report from being hidden by a derived context with a
newer role clock. Other consumers continue to read the newest composed context.
Retained database observation/receipt timestamps serialize to ISO strings in
workload evidence, preserving their original values through the JSON write.

The new normal run `47f539f5-6e09-499f-a550-bb5d0af84bed` completed with
generation **READY**, persisted lineage and a verified frozen evidence checksum,
without an incomplete-input override. Its native pool contains 52 resolved
players: 19 sourced unavailable, one sourced non-scoring specialist, and 32
generation-eligible players with complete features, projections and markets.
Four of the requested five lineups passed the saved quality/exposure controls;
the saved underfill audit attributes the fifth to player/captain exposure caps.
The original failed run is unchanged. Current preflight is 97/100 with no blocking
checks and one separate `injury_snapshot` warning. Entry clearance remains a
separate assessment. Validation: 160 targeted backend tests, 22 focused UI tests,
TypeScript/production build, persisted API audit, and mobile/desktop rendering.

Implemented and activated locally on October 6, 2026. Normal live Showdown runs now follow:

`refresh sources → validate readiness → persist frozen evidence → generate candidates → classify candidates → export AI Review Universe`

The initial October 6 Week 5 TB@DAL attempt was **NOT_READY** and stopped before generation. It produced no candidate universe or packet. The October 7 repair above resolves its source blockers in a new run. Required evidence, rather than a user judgment or warning acknowledgement, controls this decision.

## 1. Files changed

These are this task's changes; the checkout already contained substantial unrelated work.

| Files | Change |
| --- | --- |
| `backend/app/product_services/showdown_data_readiness.py` (new) | Deterministic readiness assessment, source refresh orchestration, actionable failures, evidence freeze and checksum verification. |
| `backend/app/product_services/optimizer.py` | Source clocks/IDs on the consumed pool; central live gate before every Showdown generator; persist the freeze before solving; retain readiness and frozen evidence in decision snapshots. |
| `backend/app/config.py`, `.env.example` | Configurable positive source age limits. |
| `backend/app/product_schemas.py`, `backend/app/api/product_routes.py` | Readiness on optimizer responses, validated ownership/AI entry controls, ordinary API override rejection and gated packet export. |
| `backend/app/services/job_handlers.py` | Report refresh, readiness and freeze progress through the durable worker. |
| `backend/app/product_services/ai_showdown_packet.py` | Frozen readiness in packets, live export enforcement, frozen baseline/player provenance, unavailable ownership suppression, independent requested portfolio size and valid pick'em handling. |
| `backend/app/product_services/ai_showdown_finalist_audit.py` | Propagate readiness and the generation evidence checksum into finalist audits. |
| `scripts/export_ai_showdown_packet.py` | Explicit diagnostic override and independent `--ai-requested-entries` export parameter. |
| `scripts/run_live_showdown.py` (new) | Reproduce the normal workflow using a saved run's scope/controls and a new run ID; preserve and verify the source run. |
| `ui/src/App.tsx`, `ui/src/RecentOptimizerRuns.tsx`, `ui/src/api.ts` | Worker owns Showdown refresh/gating; display generation readiness; export portfolio-size selector independent of optimizer lineup count. |
| `backend/app/tests/product/test_showdown_data_readiness.py` (new) | Readiness, refresh order, freeze, solver exclusion, overrides, exports and independent entry-count regression tests. |
| `backend/app/tests/product/test_optimizer_mode.py`, `backend/app/tests/product/test_ai_showdown_packet.py` | Explicit offline override for synthetic future-slate fixtures; sourced ownership in the ownership objective fixture. |
| `docs/product/showdown_data_readiness_v1.schema.json` (new), `docs/product/ai_showdown_selection_packet_v1.schema.json` | Readiness contract and packet fields. |
| `README.md`, `RELEASE_NOTES.md`, `docs/AI_SHOWDOWN_SELECTION_PACKET_PLAN.md` | Updated operational and export behavior. |
| This report and `artifacts/showdown_data_readiness/` | Reproduction evidence, original-run audit, pipeline attempts and live API/UI verification. |

No dependency or database migration was added. Existing optimizer constraint JSONB stores the readiness/freeze, alongside the existing source, ingest, feature, projection and ownership lineage tables. Selection objectives, finalist policy and portfolio rules are unchanged.

## 2. Readiness contract

`showdown_data_readiness_v1` is evaluated against the actual raw player-pool rows and resolved role evidence that generation will consume, before user selection filters and solver execution. Its assessment is deterministic for fixed rows, clocks, configuration and refresh results.

It exposes `slate_identifier`, `matchup`, `kickoff_at`, `evaluated_at`, `evidence_cutoff`, `status`, `reason_codes`, `required_sources`, `optional_sources`, explicit `ownership` semantics, `baseline_market` and `refresh` outcomes. Each source check carries readiness, reason codes, original observation clocks, source IDs/names, affected canonical player IDs, maximum age and a remediation action.

Overall status is `READY`, `NOT_READY` or `ERROR`. Only `READY` can reach normal live generation. Market-derived favorite, underdog and implied totals are recorded; a zero spread is explicitly represented as pick'em.

Current/future season runs fail closed, including missing/unparseable slate identity. Future kickoff dates in a prior NFL season also use the live gate, covering January's calendar boundary. Historical replay keeps its existing handling; explicit offline runs can use the diagnostic override.

## 3. Hard and optional requirements

| Source | Normal live requirement |
| --- | --- |
| Salary/slate pool | One known future game, exactly two teams, at least six distinct resolved canonical IDs, valid positions, positive salaries, native FLEX/CPT IDs, salary row lineage and current source clock. |
| Projections | Every pool row belongs to the refreshed selected projection run and has finite nonnegative mean/P90, model lineage and a fresh cutoff. Presence is checked before legacy P90/default fallbacks can conceal missing raw inputs. |
| Player availability/roles | Every individual player has sourced, cutoff-safe, current pregame availability and role evidence. Unavailable players retain their model assessment. Team defense has no individual injury designation. A default availability probability of `1` does not establish evidence. |
| Starting QBs | Exactly one sourced, fresh QB per team, consistent with projection feature QB identity where recorded. Existing inferred/provisional depth-chart resolution remains usable; current individual availability is separately required. |
| Baseline market | Every consumed row retains cutoff-safe sourced spread, total, timestamp and implied total. Team quotes must agree, spreads oppose, totals match and implied totals equal `(total − team spread) / 2`. |
| Ownership | Hard when `ownership_required=true` or `use_role_ownership=true`; otherwise optional. Required ownership needs complete CPT/FLEX values, model-run/source lineage and freshness. |

Ownership reports `ownership_available`, `ownership_attempted`, `ownership_source`, `ownership_observed_at` and `ownership_fresh` separately. Missing optional ownership is `OPTIONAL_MISSING`; available but stale optional ownership is `OPTIONAL_STALE`. Neither blocks a projection-only strategy. Unusable ownership is removed from downstream scoring/classification inputs, so packets do not invent chalk or leverage conclusions. The assessment and source IDs remain frozen. Obtaining later ownership requires a new run.

## 4. Freshness rules

| Environment setting | Default maximum age |
| --- | ---: |
| `SHOWDOWN_MARKET_MAX_AGE_HOURS` | 6 hours |
| `SHOWDOWN_PROJECTION_MAX_AGE_HOURS` | 24 hours |
| `SHOWDOWN_PLAYER_STATUS_MAX_AGE_HOURS` | 24 hours |
| `SHOWDOWN_STARTING_QB_MAX_AGE_HOURS` | 24 hours |
| `SHOWDOWN_SALARY_POOL_MAX_AGE_HOURS` | 168 hours |
| `SHOWDOWN_OWNERSHIP_MAX_AGE_HOURS` | 24 hours |

The market default follows the existing preparation freshness band. Other limits are explicit configurable defaults; weekly salaries have a longer lifecycle than current status/projections. All settings must be positive, and the evaluated limits are retained in the readiness result.

Freshness uses source observation clocks, not the time a rerun copied a record. Salary snapshots use their original observed clock where linked, otherwise the original salary import clock. QB evidence uses the observation embedded in the original evidence. Projection and ownership clocks use their recorded input cutoff. Evidence after the evaluation time or cutoff fails even when it is recent. Missing clocks fail required-source checks.

## 5. Automatic refresh workflow

The central optimizer service performs this sequence for every normal live Showdown strategy:

1. Resolve the current slate/game and verify prelock scope.
2. Reuse salary identity repair against the already imported native salary pool.
3. Disable the provider cache and capture baseline markets through existing slate preparation/source capture.
4. Invoke the existing weekly-roster capture/ingest and raw injury collector.
5. Refresh sourced starting-QB resolution through `StartingQBService`.
6. Reuse slate preparation to verify source artifacts and rebuild features/model/projections with new dependency lineage.
7. Refresh ownership when configured, and always when hard-required.
8. Re-read the saved pool, resolve roles and evaluate the exact consumed inputs.
9. Persist a checksum-protected evidence freeze only when normal readiness is `READY`.
10. Give generation an independent copy of those persisted rows, then export/classify from that same evidence.

Collector failures and downstream row counts are retained in readiness and worker progress. A collector success alone cannot certify readiness; the saved consumed inputs must pass. A failed projection rebuild produces `ERROR` with `projection_refresh_failed` and cannot fall back to an older run to clear the gate.

The application already requires a native salary CSV to identify the contest pool. This change repairs/re-reads that import rather than inventing an external salary feed. Likewise, raw injury collection is not a canonical pregame status/role transform. Existing sourced pregame context must be available to the feature builder. The current collectors cannot manufacture affirmative status/role facts for an entire slate when providers return no records. This limitation is exposed as a blocker, not hidden behind default probabilities.

## 6. Failure behavior

Missing/stale hard inputs raise `ShowdownDataNotReady` before generator/solver execution. The failed attempt retains a readiness audit with source actions and affected IDs. The worker/UI displays the exact reasons; no candidate universe, generic live market classification or AI packet is produced.

Example from the real attempt:

```text
Showdown slate is not data-ready: market_missing, player_status_missing, projection_missing.
```

Per-source actions explain that projections must be rebuilt with complete mean/P90 lineage, current sourced player availability/roles must be loaded and consumed projections must retain the fresh baseline market. Other reasons include `market_stale`, `projection_stale`, `player_status_stale`, `starting_qb_unresolved`, `starting_qb_stale`, `salary_pool_missing`, `salary_pool_stale`, `ownership_missing_required` and cutoff violations. Optional ownership reasons remain in its own check.

Failure to persist the evidence freeze also blocks generation. A saved attempt ID with failed status and zero lineups is an audit record, not a successful candidate run. Generation readiness is displayed separately from the existing final entry/player-clearance checks.

## 7. Override behavior

Internal `OptimizerService.run_job(..., allow_incomplete_evidence=True)` and CLI `--allow-incomplete-evidence` are explicit non-production paths and default false. They record the incomplete assessment and label the resulting run/output. Offline generation skips automatic external refresh so synthetic fixtures/forensic work remain reproducible.

Ordinary request JSON rejects the override; it cannot assert its own readiness or frozen evidence. Ordinary UI/API packet export also rejects an incomplete or override-generated freeze. CLI diagnostic packet files include `INCOMPLETE_EVIDENCE` in their name and a prominent content label. Retrospective handling remains diagnostic. Older past-kickoff runs without the new freeze can still be inspected/exported as explicitly unverified historical evidence.

## 8. Evidence freeze and AI entry count

`showdown_frozen_evidence_v1` stores the run ID, freeze timestamp, cutoff, readiness, original raw player pool, role context, override flag and SHA-256. The rows retain salary/source, market, projection, status, QB and ownership identities/clocks. The service persists this object before any generator call and reconstructs the generation dataframe from it. Decision snapshots retain a copy.

Completed-run retries return the saved run without refresh. Interrupted/failed runs that already have a freeze cannot reuse that ID for new evidence. Refreshing requires a new optimizer run. Packet export validates the checksum/run/cutoff, reads baseline/player context from the freeze and rejects normal live selected/candidate players outside its canonical pool. Finalist audits propagate readiness and `generation_evidence_sha256`.

Packets include a concise `data_readiness` section plus frozen time/checksum and unmistakable incomplete-evidence labeling where applicable. The live normal export endpoint rejects a run without successful frozen readiness.

`ai_requested_entries` is independent of `params.num_lineups` and archived optimizer count. Export accepts integers 2–5 through the API query, saved request parameter or CLI flag. Explicit export value takes precedence; absent one, the saved AI value or independent compatibility default of 5 is used. The UI defaults its export selector to **2** for the current manual experiment, and offers 2, 3, 4 and 5. Two is not hardcoded as a global backend requirement. Legacy `entries`/`--entries` aliases remain compatible.

## 9. Tests and activation results

- **215 backend tests passed** across readiness, optimizer mode, packet, finalist audit, production/research parity, slate preparation, current roles, starters and kicker roles.
- The new readiness module has **34 tests**, including successful live generation; missing market/projection/status/QB evidence; stale hard inputs; optional/required ownership; refresh-before-check and freeze-before-solve ordering; failed freeze persistence; generator exclusion on failure; refresh errors; explicit override/public rejection; saved-run immutability; live export rejection; frozen packet propagation; independent entry count; raw fallback masking; pick'em and season calendar boundary behavior.
- **110 UI tests passed**. `npm run build` passed TypeScript and Vite compilation; the existing bundle-size warning remains.
- Python compilation, JSON syntax checks and `git diff --check` passed. A JSON Schema validation library was not installed; no dependency was added solely for that check.
- Browser validation confirmed the Showdown automatic-refresh copy, one independent entry selector with value 2/options 2–5, the final failed run's zero saved lineups and readable source errors at desktop width. Existing responsive table/label styles were inspected; no separate mobile browser session was run.
- API/worker were idle before loading the updated backend. Local restart completed; `/api/health` returned 200. OpenAPI exposes `data_readiness` and `ai_requested_entries`.
- The old live run's normal export returned **422**, `frozen_readiness_missing`.
- The final failed attempt's results endpoint returned **200**, status `failed`, readiness `NOT_READY` and the three recorded reason codes.
- Historical run `ffb8acf8-2e31-414e-81da-417d6d82c584` exported successfully with both requested-entry fields equal to **2** and its historical evidence explicitly marked incomplete.

Reproduction commands:

```sh
.venv/bin/python -m pytest backend/app/tests/product/test_showdown_data_readiness.py backend/app/tests/product/test_ai_showdown_packet.py backend/app/tests/product/test_ai_showdown_finalist_audit.py backend/app/tests/product/test_showdown_production_research_parity.py backend/app/tests/product/test_optimizer_mode.py backend/app/tests/product/test_slate_preparation.py backend/app/tests/product/test_current_role_evidence.py backend/app/tests/product/test_player_roles.py backend/app/tests/product/test_starters.py backend/app/tests/product/test_kicker_roles.py -q --disable-warnings --maxfail=2
```

Run `npm test` and `npm run build` from `ui/`.

## 10. Why the old TB@DAL run would fail

Original run: **`9cb62307-8915-49ab-97e6-5510d9f8d1a5`**, 2026 Week 5 `THURSDAY_NIGHT`, `showdown_gpp_portfolio_v3`, kickoff October 8 at 8:15 PM Eastern.

Its saved candidate manifest confirms **98 distinct rosters**. Its saved baseline has:

```json
{
  "favorite": null,
  "underdog": null,
  "total": null,
  "market_by_team": {},
  "market_source": null,
  "market_basis": "saved_baseline",
  "market_unavailable_reason": "saved_baseline_market_missing"
}
```

Those values definitively fail the new hard market requirement before generation. The read-only reconstructed assessment also treats missing archived provenance fields as unverified; it does not claim current refreshed facts existed at the original cutoff. The source run was copied for inspection and never updated to appear ready. Its persisted before/after digest is unchanged.

## 11. Refreshed TB@DAL pipeline attempt

The normal, non-override workflow was exercised through the same optimizer service used by the worker:

```sh
PYTHONPATH=. .venv/bin/python scripts/run_live_showdown.py --from-run 9cb62307-8915-49ab-97e6-5510d9f8d1a5 --ai-requested-entries 2
```

Final attempt artifacts: [pipeline attempt](artifacts/showdown_data_readiness/20261006T134523Z/pipeline_attempt.json), [original readiness audit](artifacts/showdown_data_readiness/20261006T134523Z/old_readiness_audit.json), [unaltered original run](artifacts/showdown_data_readiness/20261006T134523Z/old_run_unchanged.json), [live API verification](artifacts/showdown_data_readiness/20261006T134523Z/activation_verification.json), [live UI screenshot](artifacts/showdown_data_readiness/20261006T134523Z/live_ui_readiness.jpg).

| Refresh/input | Observed result |
| --- | --- |
| Salary pool | 52 resolved canonical pool rows; salary readiness `READY`. Original import clock approximately `2026-10-06T01:38:22Z`. |
| Baseline market capture | Completed, snapshot `5c8ee189-d355-58af-8dd8-e1ffd3359d29`, observed `2026-10-06T13:45:25.012299Z`. Six consumed salary rows still lack linked market fields. |
| Weekly-roster availability capture | Provider returned no records: `RuntimeError: nflreadpy weekly rosters returned no records.` |
| Raw injury capture | Completed, snapshot `8e07fbb6-f49b-56ab-ad71-e892366dd463`; raw capture alone does not clear pregame status/role readiness. |
| Starting QBs | Two sourced provisional choices written; depth-chart snapshot `2c3a20da-cc78-5ac0-9d8f-14881f20dbc0`, original observation `2026-10-06T06:02:22Z`; QB check `READY`. |
| Projection build | Completed, run `cc840626-bf4c-420d-b122-bb24834b00d7`, **46 projection rows** for the 52-player salary pool; cutoff `2026-10-06T13:45:38.757163Z`. |
| Ownership build | Completed, **104 CPT/FLEX rows**, run `5f90dd3e-c42a-473c-994e-c465fde4a24e`, model `slate_aware_ownership_v2_prelock`; fresh optional ownership `READY`. |

Final required-source failures are **`market_missing`, `player_status_missing`, `projection_missing`**. Fifty individual players lack sourced current pregame availability/role proof. The six players without projection rows and linked feature market fields are Jalen McMillan, David Sills V, Baker Mayfield, Princeton Fant, Malik Davis and DJ Rogers; their canonical IDs are in the readiness artifact.

Successful market capture is therefore not sufficient to certify the exact generation pool. The gate correctly blocked the incomplete consumed rows and did not infer player clearance from projection defaults or raw injury files.

Earlier verification attempts are retained in separate timestamped directories. The first exposed an ownership-source SQL column mismatch, which was corrected and exercised successfully against the actual database on the later attempts. None of these attempts generated a new candidate universe.

## 12. New optimizer run ID

**No successful new optimizer run ID exists**, because readiness did not succeed. The final failed readiness audit ID is **`2f8b72cb-395f-470f-a809-010293d6ed21`**; it has zero generated lineups. `new_optimizer_run_id` is null, `solver_called` is false and `old_run_unchanged` is true in the saved attempt.

After current sourced status/role facts and the missing projection/linked-market rows are available, a new normal run will repeat refresh/readiness and only then freeze, generate and export. The required gate was not bypassed to obtain a demonstration packet.

## 13. Exact normal user workflow

1. In **Operations**, select season/week and the Showdown slate. Load its native salary CSV if it has not already been imported; retain the intended contest, availability scenario and lineup preferences.
2. Choose **Showdown**, strategy and optimizer lineup count, then click **Run Optimizer**. No separate manual market, projection, status or ownership readiness decision is required.
3. The durable worker automatically refreshes existing source paths, rebuilds projections, re-reads saved inputs and evaluates required freshness/completeness. Progress reports each stage.
4. When `READY`, the service persists the evidence freeze before generating candidates. When blocked, **Recent optimizer runs → Error details** gives the missing/stale sources and remediation; no candidate universe is created. Fresh source facts must resolve those blockers before a new run can succeed.
5. Open the completed run and inspect **Showdown data readiness**. Generation readiness and final entry/player-clearance reports remain separate.
6. In **Recent optimizer runs**, set **AI requested entries** to the desired 2–5 value; use **2** for this manual experiment. This does not change the saved optimizer lineup count.
7. Click **Export AI Selection Packet** or **Export packet JSON**. Normal live export requires the run's successful frozen readiness and uses that run's baseline/player evidence.
8. To incorporate later market, status, projection or ownership observations, click **Run Optimizer** for a new run and export from it. Saved runs retain their original evidence identity.

The architecture and gate are implemented and active. The live TB@DAL data remains insufficient for normal generation; the stored evidence identifies exactly why.
