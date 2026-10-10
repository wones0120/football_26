# Classic GPP data readiness and correlation audit

## 1. Executive result

Normal live Classic Large-GPP generation requires
`classic_large_gpp_data_readiness_v1: READY` before any candidate engine or solver.
Required refresh failures, incomplete source lineage, unresolved availability and
missing markets fail closed. Explicit internal previews retain the exact blockers
and cannot establish entry readiness. No GPP strategy settings were tuned.

The requested new 2026 Week 5 Sunday Main run is **NOT_READY**:

- Optimizer run: `3e332175-5321-4e4b-a7e6-b89d941ef621`.
- Durable job: `1e2340b7-6aae-4114-8c16-2388bab4959b`.
- Evaluated October 9, 2026, **6:57:24 a.m. EDT**; information cutoff
  **6:56:58 a.m. EDT**.
- Refreshed market coverage: **11/11 games, READY**.
- Solver called: **no**. Override used: **no**. Candidates/production lineups: **0**.
- Evidence was not frozen for generation because readiness failed.

The configured **0.15 correlation weight was already reaching the solver**.
The original five lineups correctly realized zero correlation contribution;
missing markets suppressed positive environment-dependent signals, while 64
defensive/opponent penalty terms remained in the objective. This repair adds
actual objective-component diagnostics and reconciliation without changing scoring.

## 2. Files changed

This completion pass extended the existing uncommitted readiness repair in place:

| File | Change |
| --- | --- |
| `backend/app/product_services/classic_data_readiness.py` | Enforce required refresh outcomes, native-pool assessment coverage, questionable usability facts; audit dispositions, coverage and unexpected material weather consumption. |
| `backend/app/product_services/optimizer.py` | Preserve detailed preview blockers; persist effective strategy before solving; record solver/override/freeze diagnostics; attach actual objective components. |
| `backend/app/product_services/gpp_optimizer.py` | Reconcile weighted components against the actual ILP objective before control replay. No coefficient/formula change. |
| `backend/app/tests/product/test_classic_data_readiness.py` | Add refresh, source-clock, pool, risk, weather, preview, freeze, user-preference and actual-solver regressions. |
| `backend/app/tests/product/overlap_ui_fixture.py` | Fix constructor-patch leakage between test modules without changing production behavior. |
| `ui/src/classicReadinessReport.ts` | Lead reports with generation status, solver/override flags, required coverage and freeze identifiers. |
| `ui/src/optimizerReport.ts` | Render actual objective contributions; suppress production lineup sections when generation is blocked. |
| `ui/tests/optimizerReport.test.ts` | Verify blocked and explicit-preview reporting and actual correlation rendering. |
| `docs/product/classic_live_data_readiness.md` | Document the source contract, required/optional refreshes, risk semantics and objective diagnostics. |
| `README.md`, `RELEASE_NOTES.md` | Update operator behavior and link this audit. |
| This document | Record investigation, tests, rerun, limitations and exact workflow. |

Retained prior repair wiring covers API/worker gating, source refresh orchestration,
canonical player context, preflight, config defaults and checksum-protected JSON
snapshots. Its isolated file list and patch remain in
`artifacts/classic_live_pipeline_integrity/task_diff_summary.json` and `repair.patch`.
This pass's starting files and patch are under `completion/start/` and
`completion/completion.patch`. Unrelated workspace changes were preserved.
Existing JSON persistence is reused; no migration or new dependency was needed.

## 3. Prior pipeline behavior

Diagnostic optimizer `7f1a28a6-a8fe-4718-a199-c66eb91c35b1` consumed preparation
`2ad26207-f314-4274-9fbb-391758e93158`, feature run
`ed525af6-99a0-45d3-bc79-e3802cadec90`, projection run
`336c510e-5e5f-4a71-aca8-6c6526586516`, and salary ingest
`5dd55a4b-b108-433b-bfaf-125c636a1705`.

It produced five lineups before reporting DEVELOPMENT_PREVIEW / ENTRY READY: NO.
Its final solver frame had 136/136 projection coverage and ownership coverage,
but 0/11 market games and unresolved freshness/current-clearance facts.
Post-generation reporting did not stop generation. The existing repair introduced
the pre-generation gate; this pass closed cached-refresh, questionable-context,
preview-diagnostic and strategy-freeze gaps found during review.

## 4. New normal workflow

1. Identify the canonical Sunday Main salary scope and schedule/kickoff window.
2. Refresh/verify salaries through existing import and identity services.
3. Refresh existing market, roster, injury, official availability, starter and
   canonical role/context paths.
4. Refresh necessary training/features/projections, then required ownership.
5. Re-read canonical persisted rows and verify the projection's actual dependency
   consumption. Evaluate required source freshness and every native player.
6. Persist the decision. NOT_READY/ERROR stop here with zero production lineups.
7. If READY, persist source evidence, eligible IDs and original source clocks.
8. Apply existing football eligibility, strategy thresholds and user preferences;
   persist the exact final solver frame and effective strategy contract.
9. Generate with frozen inputs, reconcile objective components, validate the
   requested portfolio and export the report.

Both public enqueue/worker and direct normal service calls use this gate. An old
UI preparation ID cannot replace the fresh worker build. Public request JSON
cannot supply a readiness proof or enable the incomplete-evidence bypass.

## 5. Classic readiness contract

`classic_large_gpp_data_readiness_v1` records season/week/slate, evaluation timestamp,
information cutoff, kickoff window, required/optional checks, freshness policies,
source row/run/snapshot IDs, observation clocks, exact reason codes, affected
canonical IDs, player dispositions, coverage and refresh outcomes.

Normal terminal statuses are READY, NOT_READY and ERROR. READY certifies baseline
generation evidence; final entry clearance remains separate. Explicit internal
preview calls record DEVELOPMENT_PREVIEW, the underlying `source_status`, all
blockers, `override_used=true` and whether the solver was called. The internal
keyword `allow_incomplete_evidence` defaults to false and is rejected in public
request parameters.

On success, `classic_large_gpp_frozen_evidence_v1` preserves source facts, the
native pool and role evidence with a checksum. `classic_final_input_proof` links
the source SHA256, final solver-input SHA256, effective strategy SHA256 and
projection coverage. Persistence failure prevents generation. A completed run
reopens without refresh; an interrupted frozen run requires a new run ID.

## 6. Required versus optional evidence

| Evidence | Requirement |
| --- | --- |
| Salary/slate pool | Verified immutable DraftKings source, native draft group, canonical identity, team/opponent/position/salary/game/kickoff/eligibility and source freshness. |
| Projection | Completed same-scope feature/model/projection lineage; proven consumed source selection; mean and P90 coverage and valid clocks. |
| Availability/role | Affirmative current canonical source facts; UNKNOWN/conflicting evidence blocks. Questionable usability facts use the existing risk classifier. |
| Markets | Sourced spread/total and canonical game identity for every represented potentially usable game, fresh under the source policy. |
| Ownership | Current coverage from the verified new projection; failure cannot silently switch objective weights. |
| Weather | NOT_REQUIRED_BY_CURRENT_MODEL. An unexpected material consumption claim without a verified contract blocks. |
| Final game-day entry clearance | Separate recorded check; baseline roster/practice evidence never becomes final inactive clearance. |
| Raw injury CSV collector | Informational under the current `injury_csv_consumed=false` projection proof. Official injury/roster/canonical context refreshes remain required. |

All required refresh stages must complete even when cached evidence looks valid.
Provider errors produce ERROR; unresolved required source facts produce NOT_READY.

## 7. Market refresh and freshness behavior

The existing `capture_nflverse_markets.py` path runs automatically before
readiness. Canonical normalized snapshots retain spread, total, source identity,
game ID, immutable artifact hash, source snapshot, observation and ingestion clocks.
Team implied totals derive from the same frozen baseline. Neutral defaults and a
recent projection timestamp cannot substitute for absent market provenance.

The current provider exposes a capture observation clock, not verified sportsbook
quote publication time. The six-hour source-capture freshness policy is explicit;
upstream quote-publication freshness remains UNKNOWN. A successful recent download
is never reported as proof that the underlying quote was newly published. A stale
source observation with a new ingestion time still fails. Missing one required
game or all games fails before solving.

The rerun created market source snapshot `daa9d638-4426-51d0-9ab5-2b996ca9c432` and
passed all eleven represented games. Detailed row/snapshot IDs and clocks are in
`completion/rerun_readiness.json`.

## 8. Availability and current-clearance behavior

Canonical facts distinguish available, questionable/elevated, doubtful, unavailable
and unresolved. Salary presence, default availability probabilities, an omitted
injury designation and blank official game status do not establish ACTIVE.
Explicitly unavailable and sourced unsupported specialists remain audited and do
not require projections for generation. Missing native assessments block instead
of disappearing from the pool.

The existing `classify_availability` predicate marks missing questionable practice/
workload context as an evidence gap. The gate now requires resolved, fresh,
cutoff-safe facts before exposure controls operate. LIMITED practice and LIMITED
workload can still generate as `questionable_elevated` under unchanged caps.
There are no named-player exceptions and no automatic blanket Q exclusion.
Current affirmative final game-active evidence can independently establish
usability without erasing the saved risk bucket; final evidence is recorded
separately from practice/roster facts.

The current collectors can refresh roster membership, official report designations,
depth/starter evidence and canonical context. Practice/workload fields are retained
from independently sourced context when supplied; this run did not obtain those
facts for 48 questionable players. Ashton Jeanty, Cam Skattebo, D'Andre Swift and
Carnell Tate all retain `questionable_elevated` and
`questionable_usage_context_unresolved`. The full affected list and canonical IDs
are in the saved readiness decision. Exposure parameters were not changed.

User preferences are applied after this football assessment. Excluding an opponent
such as DEN cannot clear UNKNOWN availability; the regression explicitly proves
that it still blocks generation. Existing model assessments and user-preference
reason fields remain separate in the player-pool reports.

## 9. Salary freshness behavior

Defaults are `CLASSIC_SALARY_POOL_MAX_AGE_HOURS=168`, market 6 hours, and projection,
player-status and ownership 24 hours. These are source-readiness policies, not GPP
strategy settings; this pass did not change them.

The app has an existing file-based DraftKings importer, with no automated salary
download connector. Normal refresh repairs canonical mappings, verifies the
immutable source artifact, and idempotently replays a tracked manual-file import
when its native draft-group provenance exists. An unchanged file retains its
original clock; neither a positive salary nor re-importing an old file establishes
currency. Legacy records with lineage but no observation/native snapshot remain
NOT_READY. Recovery requires a real current CSV and confirmed native draft group
through Operations → Prepare slate inputs → salary import, plus identity review.

## 10. Weather requirement decision

Inspection found no material weather consumer in the current Classic projections,
ceilings, ownership, player-context scoring, correlation/format terms or eligibility.
Weather is **NOT_REQUIRED_BY_CURRENT_MODEL** and no weather refresh is added to
this flow. Informational weather does not block READY. The regression also proves
that a lineage claiming material weather consumption without an implemented
readiness proof cannot borrow this exemption. A future weather-consuming model
must implement its source contract and refresh path before production use.

## 11. Correlation trace from configuration to solver

1. `classic_strategy_contract.build_strategy_contract` serializes the unchanged
   resolved Large-GPP configuration and pipeline options.
2. `execute_strategy_contract` restores that configuration and invokes the existing
   `run_gpp_pipeline` / `generate_portfolio` path.
3. `build_lineup_correlation_terms` constructs canonical player-pair rule terms;
   `build_format_specific_terms` constructs existing lineup-format terms.
4. `_build_lineup` linearizes the terms with binary selection/activation variables.
5. The actual objective includes
   `weights.correlation * correlation_bonus * (pair + format + extra_stack)`.
6. Sequential exposure-aware ILPs accept candidates into the requested portfolio.
   This strategy has no separate portfolio reranking objective.
7. Solver-step decomposition is persisted on each selected lineup and rendered
   alongside the existing triggered-rule explanation.

`precompute_correlation_terms=false` means terms are constructed dynamically in
each `_build_lineup`, rather than cached once in `generate_portfolio`. It does
**not** disable correlation or omit a required preparation stage. Tests verify
identical selection/components for true and false.

Stack templates, team/game limits, player exposure, primary-game caps and overlap
are constraints. They are not substitutes for correlation objective scoring.

## 12. Root cause of `Correlation: +0.00`

The saved effective weights are projection 0.35, ceiling 0.45, leverage 0.05 and
correlation 0.15, with correlation bonus 1.0. Current construction of the actual
baseline ILP verifies all **64 pair coefficients equal `0.15 × adjustment`**, plus
42 format terms. The pair terms were 9 DST/opposing early-down-back penalties,
44 DST/opposing-pass-catcher penalties and 11 QB/opposing-DST penalties.

All 136 frozen solver rows lacked markets. That suppressed positive
environment-dependent QB/pass-catcher and bring-back scoring. Each of the five
saved lineups realized zero total correlation adjustment. The report's original
field was correct for those lineups; no missing wiring or wrong rendering field
was found. The 0.15 value is a coefficient, not a promise that every selected
lineup contributes 15% of its realized score through correlation.

A diagnostic zero-correlation model has an identical feasible-region hash and a
different objective hash. Both audit models were constructed without solving.
This establishes objective wiring, not a claim that removing correlation would
necessarily change these particular five selected lineups.

## 13. Correlation code changes

No correlation model, weight, rule, threshold or selection formula was changed.
The added diagnostics capture actual weighted components from the solved model
before control comparisons can overwrite variable values. The report uses those
actual contributions when available, with the existing summary for archived runs.

## 14. Objective reconciliation tests

The deterministic fixture exposes projection, ceiling, leverage, context,
correlation, total, solver objective, reconciliation delta, normalization scales,
weights and pair/format/extra-stack subtotals. Projection and ceiling are separated
from context while retaining the existing full-pool adjusted denominators.
Their sum must match the actual solver objective within
`rel_tol=1e-9, abs_tol=1e-7`.

Tests verify weights, actual pair coefficients, non-zero feasible correlated
construction, dynamic/cached term parity, selected-lineup rule-score agreement,
manual normalized components and HTML rendering. They do not require all lineups
to have positive correlation. The real solver runs through the public queued API
and durable-worker synthetic READY fixture after all three persistence stages.

## 15. Readiness tests and validation

- **310 backend tests passed** across readiness, strategy contract, Large-GPP
  controls/reports, correlation/template scoring, optimizer modes/controls/Q
  preferences, preparation, Showdown compatibility and official injury ingestion.
- **One additional user-exclusion regression passed** after the broader run.
- **20 UI/report tests passed** and the TypeScript/Vite production build passed.
- `git diff --check` passed. Vite's existing large-bundle warning remains.

The unrestricted broader Classic/optimizer run initially reported 465 passes and
15 failures. Eleven failures were caused by an existing test harness patching
inherited `object.__new__`; restoring that descriptor polluted later service
construction. The fixture now patches the service call instead.

Four assertions already failed before this completion pass and remain explicitly
excluded from the clean broader regression run:

- `test_classic_candidate_completeness::test_no_postgame_or_postdecision_leakage_and_prelock_guard`
  and `::test_production_unchanged_and_historical_lineage_totals`.
- `test_classic_discovery_validation::test_production_code_still_matches_frozen_week4_hashes`.
- `test_classic_contest_preference::test_invalid_preferences_rejected_before_discovery[6-canonical_game_cap]`.

The first three pin an older `classic_prospective.py` hash that already differs
from the task-start implementation. That module was not edited here. The fourth
expects a positive game cap of six to be rejected by existing small-field code;
its current contract accepts it. Neither archived hashes nor cap behavior was
changed to make these assertions pass. Logs retain the unrestricted failures and
the explicitly deselected regression command/result.
After the test-isolation repair, **476 broader Classic/optimizer regressions
passed, four pre-existing assertions were deselected**, with six existing
transaction warnings. All readiness and objective-component tests passed together
with the construction and optimizer regression modules.

Coverage includes missing/all-game markets, stale source versus recent fetch,
fresh markets, salary clocks/provenance, omitted native players, incomplete mean/
P90 and ownership, unresolved availability, unavailable/specialist dispositions,
questionable context, non-consuming/material weather, required refresh failures,
refresh ordering, no solver on failure, explicit previews, both evidence freezes,
strategy persistence, completed-run idempotency and new-run snapshot independence.
The synthetic READY fixture is not evidence that the live slate is READY.

Logs: `completion/backend_tests.txt`, `user_exclusion_test.txt`, `ui_tests.txt` and
`ui_build.txt`. Source and strategy hashes/coefficients are in
`completion/correlation_audit.json`.
Broader logs are `completion/classic_regressions.txt` and
`completion/classic_regressions_verified.txt`.

## 16. Week 5 Sunday Main rerun result

The new normal queued workflow retained five entries, 80% player exposure,
overlap 5, team cap 4, game cap 5, primary-game appearances 3, single-TE off,
DST-opponent avoidance on and the DEN-opponent user exclusion. No elevated cap,
template, threshold, positional cap or objective weight was tuned.

| Required source | Result |
| --- | --- |
| Market | READY, 11/11 games refreshed. |
| Salary | NOT_READY: legacy native snapshot/draft group/observation provenance and canonical identity issues. |
| Availability/roles | NOT_READY: unresolved current players/roles and 48 questionable usage-context gaps. |
| Projection | NOT_READY: new build refused six unresolved players and its required dependency refresh was blocked. |
| Ownership | NOT_READY: new projection absent; no fallback to an older ownership build. |
| Weather | NOT_REQUIRED_BY_CURRENT_MODEL. |

Saved cached numeric coverage is 320/332 potential projection rows and 326/332
ownership rows before strategy filters. These numbers do not constitute complete
current-set lineage or readiness. The original final solver's 136/136 projection
coverage remains preserved and unchanged.

## 17. New run/job IDs

The NOT_READY attempt has optimizer run
`3e332175-5321-4e4b-a7e6-b89d941ef621` and durable queue job
`1e2340b7-6aae-4114-8c16-2388bab4959b`. No READY generation snapshot was created.
The local API/worker were restarted while idle before this run.

## 18. Solver-called status and export

**Solver called: no. Override used: no. Zero generated production lineups.**
The exported HTML uses the same application report renderer:
`artifacts/classic_live_pipeline_integrity/completion/WEEK5_SUNDAY_MAIN_NOT_READY.html`.
It leads with generation status, source checks, exact blockers, absent freeze
identifiers and solver/override flags, and contains no production lineup sections.

## 19. Remaining blockers

Exact terminal codes:

```text
historical_training_features_refresh_failed
ownership_missing
ownership_refresh_failed
ownership_timestamp_missing
player_availability_unknown
player_role_unknown
player_status_canonical_evidence_missing
player_status_missing
player_status_timestamp_missing
projection_dependency_lineage_unverified
projection_inputs_missing_or_invalid
projection_refresh_failed
projection_timestamp_missing
questionable_usage_context_unresolved
salary_identity_or_game_invalid
salary_native_source_unverified
salary_pool_timestamp_missing
```

Projection rebuilding refused Mitch Tinsley, Ihmir Smith-Marsette, Drew Ogletree,
Scotty Miller, Lew Nichols and Jackson Meeks. Five additional unresolved salary
identities remain auditable; the current unknown-availability list also includes
AJ Henning, Al-Jay Henderson, Audric Estime, Cal Adomitis and Nick Singleton.
The official refresh retained 249 observed rows but blank game designations
cannot supply affirmative clearance. Required source repairs must use canonical
facts and existing identity/context workflows; this task does not invent them.

`completion/rerun_readiness.json` contains the full affected game/player/source
lists, row IDs, original clocks and refresh outcomes. `rerun_progress.json`
contains the terminal operational error. `preservation_check.json` confirms the
original optimizer row, preparation row, API report and five lineups are unchanged.

## 20. Known limitations

There is no automatic DraftKings salary download connector. Upstream market quote
publication time is not exposed. Current refreshed sources cannot resolve every
native player's availability or every Q player's practice/workload context.
Final game-day inactives, contest assignment and submission remain separate
entry checks. Live generation must stay blocked until real source evidence is
repaired; portfolio concentration/performance comparison must wait for a valid set.

The existing historical training-label refresh also propagated the same canonical
availability blocker in this attempt. Its exact failure is retained; no cached
success is substituted. Existing saved source/strategy evidence and the previous
development-preview run remain immutable. No model/strategy quality claim follows
from synthetic READY tests or the correlation wiring audit.
The four pre-existing regression assertions described above remain separate
maintenance work; the broad suite is not reported as universally green.

## 21. Exact normal production command/workflow

In the UI: Operations → Prepare slate inputs imports a current native DraftKings
CSV and resolves source/identity issues. Select 2026 Week 5 Sunday Main, Classic,
Large GPP, five entries and the original controls, then **Run Optimizer**. The
worker refreshes required sources, evaluates readiness and freezes only READY
inputs. **Refresh Status** assesses saved evidence without generating lineups.

The normal API workflow uses `POST /api/optimizer/jobs`; no bypass parameter is
accepted. This repeatable command creates a new run ID with the exact saved
validation controls, then queues the normal worker path:

```bash
.venv/bin/python - <<'PY'
import json, uuid
from pathlib import Path
p = json.loads(Path('artifacts/classic_live_pipeline_integrity/completion/rerun_request.json').read_text())
p['optimizer_run_id'] = str(uuid.uuid4())
Path('/tmp/classic-week5-request.json').write_text(json.dumps(p))
PY
curl --fail-with-body -H 'Content-Type: application/json' \
  --data-binary @/tmp/classic-week5-request.json \
  http://127.0.0.1:8000/api/optimizer/jobs
```

Keep that new request file for idempotent retry; a later source refresh must use
another new ID. Poll `GET /api/jobs/{queue_job_id}`, then read
`GET /api/optimizer/results/{optimizer_run_id}` and export the saved report.
Expected current outcome remains NOT_READY with no solver call until the source
blockers above are resolved.
