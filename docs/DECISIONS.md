# Architecture and Model Decisions

This log records decisions that affect reproducibility, production defaults, or historical-model acceptance. The operational backlog remains in `docs/TODO.md`.

## 2026-08-02 — Accept the historical half of WTHR-007 without fabricating current evidence

- Decision: accept the real DraftKings 2025 Week 11 `SUNDAY_MAIN` database/API/UI run as the historical half of WTHR-007, add a regression boundary that keeps weather tables and services out of production projection, simulation, and optimizer modules, and leave WTHR-007 blocked until an actual prospectively received 2026 current slate is captured.
- Evidence: the API resolved all 11 expected games from 556 salary rows, returned 9 available and 2 indoor states plus 2 retractable venue defaults, selected no forecast basis after lock, and exposed no replay-eligible actual. Desktop and 390px War Room renders retained all games without overflow or console errors. The focused backend suite passes 28 tests, the full backend suite passes 429 tests, all 12 UI tests pass, and the production UI build passes. Exact evidence: `docs/WTHR-007_ACCEPTANCE.md`.
- Rationale: on 2026-08-02 the development database has zero current forecast snapshots, zero current refresh results, zero 2026 salary rows, and no locally ingested 2026 schedule. The official 2026 games begin outside the provider's current forecast horizon. Backdating a live response or relabeling a fixture as prospective would invalidate the receipt-time contract.
- Production impact: weather remains read-only decision-support context. The historical acceptance gap is closed, but WTHR-007 and DATA-002 remain blocked on the first real source-authorized, in-horizon 2026 slate with multiple pre-lock captures and a retained post-lock exclusion check.

## 2026-08-02 — Keep War Room forecast and actual weather visually separate

- Decision: consume `slate_game_weather_v1` directly in the War Room and retain every API matchup in the Game Pressure Matrix. Associate projection pressure by canonical `game_id` first and normalized team pair only as a fallback; never associate through player display names. Treat the matrix weather state as explicit decision context, and put retrospective completed-game actuals in a separate replay-ineligible panel rather than using them to repair or decorate forecast fields.
- Evidence: focused UI tests cover canonical matchup union, non-truncation, the five weather states, unit/freshness presentation, readable warnings, and the historical-only actual display gate. The production build passes, and rendered desktop plus 390px fallback/error states have no page overflow or browser diagnostics. UI behavior and the remaining live-data boundary are recorded in `docs/WAR_ROOM_WEATHER.md`.
- Rationale: weather must be visible for every selected-slate matchup without weakening the WTHR-005 identity or cutoff contracts, and forecast inputs must remain visually unmistakable from result-time actual conditions.
- Production impact: WTHR-006 is complete. Weather remains decision-support context only and does not enter projections, simulations, or optimizer inputs. WTHR-007 remains blocked on reproducible past-slate and prospectively captured current-slate API/UI acceptance evidence.

## 2026-08-02 — Compose weather through canonical slate-game identity

- Decision: expose historical fixed-lead forecasts, receipt-timed current captures, versioned venues, and retrospective actuals through the read-only `slate_game_weather_v1` API. Reconcile source salary team/opponent pairs to canonical nflverse schedule IDs, use explicitly slate-labeled current capture rows as additional membership evidence, and retain unresolved or ambiguous matchup rows instead of dropping them. Clamp selection to server time and earliest slate kickoff; keep actuals in a separate replay-ineligible object.
- Evidence: focused tests cover historical as-of-lock selection, retained post-lock exclusion, current receipt-only selection, stale and indoor states, actual/forecast separation, team aliases, timezone enforcement, and unresolved-matchup retention. The complete API contract is in `docs/SLATE_GAME_WEATHER_API.md`; the full Python suite passes 428 tests.
- Rationale: the War Room needs one complete matchup contract without weakening forecast timing, treating artifact receipt as provider publication, joining player display names, or visually/structurally confusing actual conditions with forecasts.
- Production impact: WTHR-005 and WTHR-006 are complete. No weather row enters projections, simulations, or optimizer inputs until the WTHR-007 end-to-end gates pass. A real prospectively captured 2026 slate remains required for DATA-002 and WTHR-007.

## 2026-08-02 — Use receipt time for append-only current weather forecasts

- Decision: capture current Open-Meteo Forecast API responses as immutable `current_forecast_capture` versions in the existing weather snapshot contract. Keep fixed lead and provider issued/availability times null, set `forecast_basis_at=received_at` with `server_received_at`, and allow cutoff selection only when the actual receipt is at or before the requested cutoff. Require explicit canonical game IDs for slate membership.
- Evidence: focused tests retain three versions for one current-slate game, select the newest pre-lock value at lock, retain but exclude a post-lock value, detect stale and failed refresh states, verify immutable artifacts, redact keys, pin the model/variables, and prove per-request spacing. Operations and remaining prospective acceptance are in `docs/CURRENT_WEATHER_FORECASTS.md`.
- Rationale: a live response has a trustworthy local receipt time but no provider publication timestamp or stable fixed lead. Appending every refresh preserves the knowledge timeline and prevents a later forecast from rewriting what was known before lock.
- Production impact: WTHR-004 is complete. Production capture still requires an authorized Professional-or-higher customer endpoint and secret key. A real 2026 slate remains required for DATA-002 and WTHR-007; no weather row enters projections, simulations, or optimizer inputs yet.

## 2026-08-01 — Accept the fixed-lead historical weather cohort

- Decision: accept the 570-row 2024–2025 Open-Meteo Previous Runs cohort as the WTHR-003 historical forecast evidence set. Keep it in immutable `weather_forecast_snapshot` rows and raw artifacts, separate from retrospective `curated_game_weather`; do not yet wire it into projections, simulations, or optimizer inputs.
- Evidence: all 570 expected games resolve through the current venue registry and have all six pinned variables. The independent audit recomputed all 570 raw checksums, matched every manifest and registry record, found no redacted-URI or timing issues, and reproduced one snapshot through an idempotent zero-request rerun. Targeted tests cover exact-hour normalization, cutoff basis, null provider timing, provider failures, tampering, and actual-weather non-substitution. Evidence and operations are in `docs/HISTORICAL_WEATHER_FORECASTS.md`.
- Rationale: the cohort now satisfies the source contract without inventing publication timing or mixing actual outcomes into forecast features. Immutable per-game results make gaps visible and interrupted runs resumable.
- Production impact: WTHR-003 is done and WTHR-004 is ready. Historical visibility uses the reviewed `provider_fixed_lead` basis; live forecasts will require actual pre-lock receipt. Production provider traffic still requires Professional-or-higher Open-Meteo access and a secret customer key.

## 2026-08-01 — Pin fixed-lead weather forecasts and preserve unknown provider timing

- Decision: use Open-Meteo Previous Runs for the 2024+ historical weather cohort at exactly 24 hours (`*_previous_day1`) with `ncep_gfs_seamless` and six pinned temperature, humidity, precipitation, wind-speed, wind-direction, and gust variables. Use the same model family for prospective capture. Use direct NOAA HRRR only as a CONUS fallback, with its exact run and actual 24–29-hour lead preserved. Do not use `best_match`.
- Evidence: Open-Meteo documents `_previous_day1` as predicted 24 hours before valid time and most model archives from January 2024. It also states that Previous Runs does not expose individual run initialization; Single Runs separately documents that initialization is not public availability. The free endpoint is non-commercial and rate-limited, while historical commercial use requires Professional or higher; CC BY 4.0 attribution is mandatory. The exact evidence and operating contract are in `docs/WEATHER_FORECAST_SOURCE_CONTRACT.md`.
- Rationale: one fixed lead and pinned model make 2024–2025 comparisons reproducible across U.S. and international venues. Preserving `provider_issued_at` and `provider_available_at` as null is safer than inventing observation lineage from a derived lead offset. Direct HRRR provides exact-run fallback evidence but is not globally available or lead-equivalent.
- Production impact: WTHR-003 implements immutable backfill with `forecast_basis_at=valid_at-24h`, `forecast_basis_kind=provider_fixed_lead`, actual `received_at`, and null provider timing. Free Open-Meteo is evaluation-only; production requires an active Professional-or-higher subscription and secret key. The cohort remains unwired from model inputs pending WTHR-004 through WTHR-007, and retrospective actuals may never fill forecast fields.

## 2026-08-01 — Resolve games through versioned venue identity, not stadium name

- Decision: maintain stable physical `venue_id` identities with immutable versions, effective seasons, reviewed coordinates/timezones/roof defaults, PFR source IDs, and game-ID overrides for every neutral-site event. Quarantine zero or multiple effective matches instead of falling back to display-name matching.
- Evidence: `nfl_venue_registry_v1` maps all 570 latest 2024–2025 nflverse games: 555 through PFR `stadium_id` and 15 through reviewed overrides, with zero unresolved, ambiguous, conflicting, or unreviewed-neutral games. Seven 2025 international rows otherwise point to the nominal home venue in the wrong city or country. Evidence and operator workflow are in `docs/WEATHER_VENUE_REGISTRY.md`.
- Rationale: naming-rights strings are unstable, and valid-looking home-stadium metadata is unsafe for international and relocated games. Stable source IDs plus explicit game decisions make coordinate selection deterministic and reviewable.
- Production impact: migration `0021` adds the registry, override, and curated mapping tables. Schedule ingestion rebuilds mappings transactionally, and forecast capture must use the resolved registry record. Buffalo's replacement stadium requires a new 2026 identity before its first accepted home forecast.

## 2026-07-31 — Reject the locked opportunity/efficiency projection candidate

- Decision: retain the existing production projection model. Do not promote the per-position MODEL-001 opportunity/efficiency candidates or the DST defense-form/opponent-allowed groups. Preserve the content-addressed selection lock and holdout evidence, and repeat the contract only on a prospectively captured 2026 cohort.
- Evidence: validation through 2025 W11 selected opportunity plus efficiency for QB/TE, efficiency for RB/WR, and the history baseline for DST. The locked 2,734-row W12-W18 holdout produced `2.978` MAE versus `2.976` for the history baseline, a `0.04%` regression. RB improved `0.35%`; QB, WR, and TE regressed `0.11%`, `0.19%`, and `0.19%`; DST additions had already reduced validation quality by `0.50%` to `1.85%`. Position and lagged-role interval coverage remain recorded in `docs/MODEL-001_HOLDOUT_EVIDENCE.md`.
- Rationale: validation lift did not generalize, and several high-opportunity roles remain materially under-calibrated. The historical salary cohort also lacks preserved pre-lock observation timestamps, so it cannot authorize a production promotion even if aggregate error had improved.
- Production impact: none. `model_001_opportunity_efficiency_ablation_v1` is research-only, the active projection pointer is unchanged, and any future 2026 challenger must pass the existing MODEL-002 evaluation and named-approval workflow.

## 2026-07-30 — Fail closed when snapshot observation time is not proven

- Decision: expose an injury snapshot to simulations, optimizers, or symbolic rules only when both its `as_of` timestamp and the selected projection's `data_cutoff_at` exist and `as_of <= data_cutoff_at`. Do not backdate retrospective imports from season/week labels, file names, game dates, or undocumented assumptions.
- Evidence: all 10,268 local 2024–2025 FanDuel injury rows were loaded on February 25, 2026; all 8,086 target injury snapshots inherit that date. Week 11 alone has 493 such rows. All 7,017 nflverse schedule records and their total/spread values were also loaded after the historical games. The official nflverse injury dictionary documents `date_modified`, but nflreadpy 0.1.5 delivered a 6,068-row 2025 frame with 16 columns and no modification timestamp. Focused tests prove pre-cutoff visibility, equality at cutoff, post-cutoff exclusion, missing-time exclusion, and the shared SQL predicate in every projection-linked consumer.
- Rationale: a correct historical value is still leakage if the platform cannot prove it was known by the decision cutoff. Failing closed preserves honest replay metrics while allowing prospectively captured or genuinely timestamped data later.
- Production impact: historical projection runs with null cutoffs no longer use injury snapshots to remove players or apply injury rules. DATA-002 is blocked until a timestamped, authorized source is selected or prospective capture begins; existing rows remain stored for audit and live descriptive use.

## 2026-07-30 — Require persisted evaluation and approval before changing a projection champion

- Decision: treat a completed run as a challenger whenever its season/week/slate already has an active projection. Persist the champion/challenger pair, ordered non-overlapping training/validation/test windows, exact feature and code hashes, comparable metric gates, evaluator, and evidence before review. Require at least one strict positive-improvement gate and every gate to pass. Change the pointer only in the same transaction as a named promotion approval, and restore the exact prior run only in the same transaction as a named rollback approval.
- Evidence: migration `0017` adds content-addressed evaluation and decision tables with immutable projection-run foreign keys and promotion/rollback constraints. Focused service and API tests prove invalid windows and non-improving evaluations block, new completed runs do not overwrite an existing pointer, stale-champion compare-and-set checks fail, and promotion plus rollback move the pointer in opposite directions. The development database reports 57 expected and 57 actual target tables with zero drift; its existing `baseline_rolling_dk_v0:projection:2025:11` champion remains selected.
- Rationale: an append-only prediction registry is not safe if any completed run or arbitrary API caller can silently become active. Separating evaluation evidence from a human approval decision makes model quality reviewable, keeps concurrent changes safe, and gives every promotion an exact reversal target.
- Production impact: apply migration `0017` before deploying. Existing pointers are preserved. New projection runs remain inactive challengers after completion. Callers use `/api/model-governance/evaluations`, the evaluation promotion route, or the decision rollback route; `/api/predict/active` only confirms the active run named by the currently applied approval decision.

## 2026-07-27 — Reuse immutable projections before rebuilding a weekly run

- Decision: let the weekly predict stage consume a caller-selected completed `projection_run_id`, otherwise reuse the completed active projection selected by readiness, and dispatch a new projection build only when neither exists. Record both the planned write ID and the actual selected projection lineage when an active run is reused. Surface unavailable symbolic injury and matchup inputs as stage warnings rather than leaving them only in worker logs.
- Evidence: regression coverage proves active-run selection preserves the exact projection, feature, and model IDs. Development run `aeb1e82f-ab0d-4ffe-a38b-88db355e7f3e` resumed at predict without repeating completed ingest/readiness writes, selected `baseline_rolling_dk_v0:projection:2025:11`, evaluated 473 projections, persisted a 25-iteration/382-player simulation and optimizer run `799904e9-003e-4bfd-9fa2-48ed4d75b9e4`, then stopped at validation because no real DraftKings entry template exists.
- Rationale: immutable active projection lineage is already the product source of truth. Reusing it avoids unnecessary model writes, makes a weekly run executable on the consolidated target schema, and remains explicit in stage artifacts; the workflow must never fabricate an upload template to force validation/export success.
- Production impact: restart standalone workers after deploying new handler code. An operator may pass an exact projection ID or rely on the readiness-selected active run. Validation/export remain intentionally blocked until a same-scope DraftKings entry template is ingested.

## 2026-07-26 — Checkpoint the weekly decision chain by durable stage

- Decision: represent one weekly workflow as a leased `operational_job`, one `weekly_run`, and eight ordered `weekly_run_stage` checkpoints: ingest, readiness, predict, adjust, simulate, optimize, validate, and export. Allocate downstream artifact IDs before execution, mark a stage complete only after its durable service write exists, skip completed stages on retry, and reuse the same IDs for the first incomplete stage.
- Evidence: `backend/app/tests/test_weekly_orchestrator.py` proves the job and all stage checkpoints become visible atomically, interrupts simulation after four completed checkpoints, resumes the same run, proves those completed calls are not repeated, and verifies stable artifacts plus accumulated logs and errors. API tests cover caller idempotency and all eight stage records. The complete backend suite passes 353 tests, the Vite production build passes, and Operations was checked at 1280px and 390px without page overflow.
- Rationale: a single opaque job cannot show which decision-chain artifacts exist or resume safely after a process failure. Stage-local status and telemetry make the failure boundary explicit, while preallocated IDs let services distinguish recovery from duplicate work.
- Production impact: apply migrations `0015` and `0016`, run `python -m backend.app.worker`, and use `/api/weekly-runs` or Operations → Resumable decision chain to dispatch and inspect work. Current persisted slate simulation supports classic contests only, so a showdown weekly run stops explicitly at simulation instead of silently switching behavior.

## 2026-07-25 — Run long operations through a leased database queue

- Decision: persist benchmark, projection, research-simulation, slate-simulation, and ultimate-lineup dispatch in one `operational_job` table, then execute it only from the standalone worker. Scope idempotency by job type and caller key, claim with expiring leases, heartbeat active work, preserve a stable underlying run ID/checkpoint across attempts, and store terminal result/error payloads for polling. Keep the specialized ultimate-lineup run and checkpoint API intact, with the generic queue owning only dispatch.
- Evidence: `backend/app/tests/test_job_queue.py` proves exact reuse and mismatch rejection, API/session restart survival, persisted progress/results, expired-lease recovery with the same run ID, exhausted-lease failure, manual retry identity, and projection dispatch/status API behavior. `backend/app/tests/test_ultimate_lineup_runs.py` proves the API now creates one durable queue item rather than an in-process background task. The complete backend suite passes 349 tests and the Vite production build passes.
- Rationale: FastAPI background tasks disappear with the API process and synchronous CPU/database work ties job survival to an HTTP request. The application database already owns run lineage, so a small leased queue adds durable at-least-once dispatch without another service dependency while leaving result and checkpoint contracts inspectable.
- Production impact: apply migration `0015`, start at least one `python -m backend.app.worker` process separately from FastAPI, and monitor `GET /api/jobs` or Operations → Run activity. The first four long-running endpoints now return `202` job envelopes; their former result payloads are available unchanged in `job.result`. Callers should retain and reuse `Idempotency-Key` across transport retries.

## 2026-07-24 — Make numbered migrations authoritative for target schema

- Decision: remove all `target` schema DDL from product services. Migrations `0013` and `0014` adopt the nine columns previously added opportunistically and record the exact migrated table, column/type/nullability, and constraint contract. Runtime services perform read-only compatibility validation against only the tables they use.
- Evidence: the static governance test rejects runtime `target` DDL, focused product-service and schema tests pass, and the canonical PostgreSQL target check reports 55 expected tables, 55 actual tables, and zero issues with an exact 14-file migration ledger.
- Rationale: idempotent `CREATE TABLE IF NOT EXISTS` and `ADD COLUMN IF NOT EXISTS` calls can hide missing deployments and structural drift. A migration-recorded catalog contract makes deployment history authoritative while preserving actionable runtime failures.
- Production impact: deployers must apply every numbered migration before starting product workflows. A missing or changed table, column/type, or constraint now fails compatibility validation instead of being silently created or altered by a request.

## 2026-07-21 — Persist async ultimate-lineup runs and checkpoint retries

- Decision: represent each UI-triggered ultimate-lineup comparison as an application-database run with a unique caller idempotency key, immutable request hash/payload, atomic queued-to-running claim, stage-local progress, terminal result/error, and attempt lineage. Assign a server-managed transactional candidate checkpoint when the caller does not provide one, and resume it on a compatible failed-run retry.
- Evidence: `backend/app/tests/test_ultimate_lineup_runs.py` proves exact idempotent reuse, different-request conflict, atomic worker completion/failure persistence, retry attempt lineage, checkpoint-resume selection, and create/get API behavior. The existing checkpoint test still proves resumed candidate UID order matches an uninterrupted sequence, simulation reoptimization tests now observe training/candidate/portfolio progress stages, and the production UI build passes.
- Rationale: candidate generation can outlive a normal browser request. Returning a run ID immediately makes the control plane responsive and observable, while persistent state prevents duplicate clicks and refreshes from silently launching different work. Keeping the candidate sequence in its existing SQLite checkpoint avoids storing hundreds of thousands of lineups in the application database.
- Production impact: the prior synchronous `POST /api/lineups/ultimate` remains available. The UI uses `POST /api/lineups/ultimate-runs`, polls the run, and can retry failed work. As of `OPS-001`, dispatch runs through the standalone operational worker without changing this run schema or API contract.

## 2026-07-20 — Pair compatible simulation runs to isolate shock sensitivity

- Decision: allow a scenario lineup request to name an optional `baseline_simulation_run_id`. The baseline must be completed, unshocked, and compatible with the scenario's slice, iterations, non-null seed, history minimum, prior weight, noise scale, and residual-learning setting; the scenario must contain a role or point-in-time shock. A missing legacy residual flag is interpreted as its historical default, `false`.
- Evidence: targeted tests prove paired baseline projections are applied before candidate generation, source-native and canonical overrides work, incompatible seeds and shocked baselines fail, unshocked scenarios fail, and no-run/single-run behavior remains intact. The 118-test backend suite passes. A paired Week 18 replay matched `663/663` outcomes in both runs, produced `80%` overlap between two 20-lineup portfolios from `332` shared candidates, and recovered `+3.28` scenario projected-blend points after the shocked target's exposure moved from `20%` to `0%`.
- Rationale: the original single-run comparison measures the complete difference between lineup-default and scenario projections. A same-seed, same-parameter simulated baseline isolates the shock from simulation-method differences while retaining the same candidate-pool and exposure-cap controls.
- Production impact: API/CLI callers may add `baseline_simulation_run_id`; responses expose both run IDs and loaded/matched counts. Omitting it preserves the existing single-run comparison, and omitting both run IDs preserves default lineup generation.

## 2026-07-19 — Reoptimize one shared lineup pool from persisted simulation runs

- Decision: let ultimate classic lineup requests select one completed, matching `simulation_run_id`; overlay its persisted mean/p90 outcomes by canonical or source-native player ID after baseline candidate generation, then independently rescore and exposure-cap baseline and scenario portfolios from that shared candidate set.
- Evidence: `backend/app/tests/test_simulation_lineup_reoptimization.py` proves completed-run lookup, exact slice validation, stable-ID overrides, a controlled `0%` lineup overlap, `-100%`/`+100%` target exposure movement, and a `+29.0` scenario projected-blend reoptimization lift. A bounded replay of completed Week 18 role-shock run `821c7b46-aad1-458d-a63d-055ea775c92b` matched all `663` outcomes, produced `25%` overlap across two 20-lineup portfolios from `944` shared candidates, recovered `+10.18` scenario projected-blend points, and improved the scenario objective score by `+0.886`. The complete 117-test backend suite passes.
- Rationale: generating candidates once isolates projection sensitivity and reoptimization from random candidate-pool drift. Persisted simulation lineage keeps the shock assumptions reproducible, while stable IDs preserve the canonical identity contract.
- Production impact: `POST /api/lineups/ultimate` and `scripts/run_ultimate_lineups.py` accept optional `simulation_run_id`. Responses report loaded/matched outcomes, lineup overlap, projected-blend and objective lifts, and stable-ID exposure deltas. Missing, incomplete, empty, or wrong-slice runs fail explicitly; omitting the field preserves prior behavior.

## 2026-07-19 — Keep weather/news shocks caller-authoritative and point-in-time

- Decision: accept opt-in weather/news shocks with timezone-aware observed and scenario-cutoff timestamps, explicit team/position or stable player-ID targeting, and caller-supplied mean/volatility multipliers. Shocks compound in request order after baseline, residual, and role adjustments.
- Evidence: `backend/app/tests/test_point_in_time_shocks.py` proves deterministic distribution transforms, exact team/position and source-ID targeting, missing-ID failure, timestamp cutoff enforcement, post-floor mean preservation, and persisted parameters. `docs/point_in_time_shock_validation_2025_late_season.{json,md}` records warning-free W16-W18 replays, zero unexpected targets, exact requested aggregate mean multipliers, and an exact same-seed repeat.
- Rationale: the platform can stress-test current information without pretending unavailable historical weather/news feeds exist or embedding unvalidated causal effect sizes. Stable identities and explicit multipliers keep every assumption reviewable.
- Production impact: ordinary simulation is unchanged when `point_in_time_shocks` is empty. Requests and effective seed remain stored on `simulation_run`; responses expose the cutoff and sequential player impacts. Shock means are guaranteed after the nonnegative floor; a completed matching run can be selected explicitly for ultimate lineup reoptimization.

## 2026-07-19 — Make late-swap lock state explicit and identity-safe

- Decision: late swap accepts the original nine source-native player IDs, a timezone-aware as-of timestamp, and caller-confirmed locked teams. Original players on those teams are required in every candidate and exempt from exposure caps; all other players on locked teams are excluded.
- Evidence: constrained-generation tests preserve every locked player, exclude every started-game alternative, reproduce the exact candidate sequence for the same seed, reject missing source IDs and invalid original rosters, and reject naive timestamps. Candidate checkpoint fingerprints include required and excluded player IDs.
- Rationale: source-native IDs honor deterministic identity rules, while explicit locked teams avoid guessing live lock state from incomplete or date-only historical schedule strings. Reapplying the same request is deterministic and auditable.
- Production impact: late swap is opt-in through `POST /api/lineups/ultimate` or `scripts/run_ultimate_lineups.py`. Default generation is unchanged. Responses report the lock timestamp, normalized teams, locked source IDs, and per-player lock flags.

## 2026-07-19 — Keep contest objectives explicit and balanced by default

- Decision: expose caller-selected `balanced`, `cash`, and `gpp` ultimate-lineup profiles with fixed response-visible weights. Cash combines base score `0.25`, projected mean `0.45`, and learned quality / one-minus-bust probability `0.30`. GPP combines base `0.25`, top-tail policy `0.20`, ceiling probability `0.25`, and projected p90 `0.30`, then subtracts `0.15` of standardized pre-lock duplication-proxy risk.
- Evidence: targeted tests prove balanced returns the prior composite bit-for-bit, cash ranks stable mean/quality above a volatile ceiling-only candidate, GPP ranks equal-ceiling candidates by lower proxy duplication risk, and malformed shapes/profile names fail explicitly.
- Rationale: cash and GPP require different risk preferences, but unavailable historical ownership, field results, cash lines, and payout structures do not justify opaque fitted contest claims. Fixed weights make the current research assumptions reproducible and easy to replace when better data arrives.
- Production impact: `balanced` remains the default and preserves prior ranking. API/CLI callers may opt into `cash` or `gpp`; output records the profile, exact weights, pre-objective score, and final score. The separate duplication penalty remains default-off and is applied afterward.

## 2026-07-19 — Make migrations and ORM metadata agree in PostgreSQL CI

- Decision: treat the ordered SQL migrations as the PostgreSQL deployment history and require SQLAlchemy metadata to describe the resulting schema exactly. Use dialect variants so production compiles identity columns as `BIGINT` and document payloads as `JSONB`, while fast SQLite tests retain `INTEGER` autoincrement and portable `JSON`.
- Evidence: fresh-database validation applied all nine migrations and compared 18 application tables. It found and closed identity type, document type, and calibration-index drift; the second migration pass applied nothing and left the schema unchanged.
- Rationale: migration success alone cannot detect runtime ORM disagreement, and metadata-only table creation can hide migration defects. Comparing both representations on a real PostgreSQL service catches either class of drift without weakening existing SQLite unit coverage.
- Production impact: `.github/workflows/schema-smoke.yml` now gates schema-related changes using PostgreSQL 16 with `AUTO_CREATE_TABLES=false`. Runtime APIs and migration history are unchanged.

## 2026-07-19 — Use transactional SQLite artifacts for large candidate checkpoints

- Decision: persist ultimate classic candidate progress in a caller-selected SQLite artifact, committing only at complete generation-attempt boundaries and storing lineup UIDs, adaptive-stage state, attempt count, and full NumPy RNG state.
- Evidence: interruption tests resume with a different fresh RNG object and reproduce the uninterrupted candidate UID sequence exactly; the full 93-test backend suite passes.
- Rationale: incremental SQLite transactions avoid repeatedly rewriting a potentially 500k-lineup JSON snapshot, recover cleanly from partial writes, and require no new dependency or application-database migration.
- Production impact: checkpointing remains opt-in. Resume rejects a changed semantic request, player pool, sampling weights, generator version, or NumPy version; completed checkpoints skip regeneration. A mid-attempt interruption replays from the previous committed boundary instead of persisting a half-consumed RNG state.

## 2026-07-18 — Keep the global projection model over regime specialists

- Decision: reject the standalone position-by-total/spread-regime specialist ensemble and retain the global regression-tree research baseline.
- Evidence: across 17,342 feature-matrix rows and 28 whole-week slices, validation selected a 300-row cell minimum and prior strength `1000`. MAE worsened `0.27%` on validation and `0.04%` on the untouched test (`2.573` to `2.574`); only two of five test slices improved.
- Rationale: the global tree already consumes continuous total and spread features. The specialist layer added partition variance without stable incremental signal. WR improved `0.73%` on test but regressed `0.41%` on validation, so selecting WR after opening the test window would be leakage.
- Production impact: none. Unknown and sparse cells demonstrably fall back to the global prediction, and the rejected candidate is retained only as reproducible evidence.

## 2026-07-18 — Integrate residual learning behind a default-off gate

- Decision: retain prior strength `5.0` as the validation-selected online residual-learning candidate, using a 12-slice rolling window, sample-size shrinkage, and a six-point adjustment cap.
- Evidence: across 1,205 untouched-test observations from 2025 W11-W18, MAE improved `4.818` to `4.602` (`+4.48%`), RMSE improved `6.551` to `6.389` (`+2.47%`), every test slice improved, and QB/RB/WR/TE each improved.
- Rationale: the learner uses only strictly earlier completed weeks and canonical/source identities; validation chooses shrinkage strength before the later test is opened.
- Production impact: DraftKings weekly simulation can explicitly enable the learner, but the gate defaults off and FanDuel remains unsupported. Immutable source/season/week/slate snapshots store exact canonical observations, parameters, feature hash, and code version. Scoring requires at least four strictly prior compatible snapshots and visibly falls back to baseline otherwise. The initial backfill created 15 snapshots containing 3,342 observations with zero failures, and its idempotency rerun reused all 15.

## 2026-07-18 — Treat role shocks as explicit stress tests

- Decision: accept manual RB/WR/TE role shocks as scenario inputs, reallocate prior four-game carries/targets, damp recipient projection changes to 65% of opportunity changes, default simulation seed to `42`, and persist the effective seed plus full request.
- Evidence: the Week 18 Gibbs zero-retention scenario changed top-lineup overlap to `70%`, moved Gibbs exposure `30%` to `0%`, moved Montgomery `5%` to `25%`, and produced a `+6.69` projected-blend reoptimization lift.
- Rationale: manual controls let us respond to current news without fabricating historical injury data. Damping keeps fantasy-point changes from scaling one-for-one with opportunity.
- Production impact: no automatic shock is inferred; baseline behavior is unchanged when `role_shocks` is empty.

## 2026-07-18 — Keep duplication-risk penalty opt-in

- Decision: expose the pre-lock `popularity_proxy`, generated-candidate exposure, and lineup duplication risk, but keep `duplication_risk_penalty=0.0` by default.
- Evidence: across 12 historical classic slates, penalty `0.25` reduced proxy risk `1.1%` with a `0.2%` projected-blend cost and `0.28` fewer actual points. Penalty `0.75` reduced risk `6.7%` but cost `5.0%` projection and `8.37` actual points.
- Rationale: the proxy is useful for explicit GPP diversification, but it is not observed ownership and stronger settings sacrifice too much lineup quality.
- Production impact: response observability is enabled; ranking changes only when the caller supplies a nonzero penalty.

## 2026-07-18 — Remove unavailable injury and ownership feeds from the critical path

- Decision: derive latent availability from usage-weighted roster continuity and pursue a clearly labeled popularity/duplication proxy instead of observed ownership.
- Evidence: honest identity coverage includes unresolved current salary players. Under that accounting, the continuity candidate scored `27.3%` top-1 and `51.5%` top-2 versus the current-code baseline at `33.3%` and `57.6%`.
- Rationale: prior carries/targets, current salary pools, projections, and generated lineups are reproducible inputs we control. We will not fabricate unavailable injury or ownership history.
- Production impact: none; continuity was rejected as a standalone captain feature set and remains research-only for role-shock scenarios.

## 2026-07-18 — Keep rejected availability candidate out of production

- Decision: retain the baseline showdown captain feature set and production prior strength `0.35`.
- Evidence: the opt-in availability candidate had no historical injury-report coverage and regressed to `30.3%` top-1 / `51.5%` top-2 versus the current-code baseline at `33.3%` / `57.6%`.
- Rationale: active salary-pool counts are not a substitute for point-in-time injury status. Reevaluate only after historical injury snapshots are ingested.

## 2026-07-18 — Treat showdown role/scenario priors as research inputs

- Decision: persist position-plus-role archetypes and sample-gated scenario priors without changing the current production captain model.
- Evidence: `docs/showdown_captain_scenarios_2024_2025.json` covers 41 slates, 11 archetypes, and seven total/spread cells.
- Rationale: Laplace smoothing and a five-slate minimum make the priors usable for future-safe analysis, but several cells still fall back to global priors.

## 2026-07-18 — Do not auto-promote the projection-family winner

- Decision: keep the current player projection blend while recording the regression-tree research result.
- Evidence: the tree was selected on 2025 W08-W11 validation and achieved `2.610` MAE on the untouched 2025 W12-W18 test window, ahead of ridge (`3.044`) and the shallow neural net (`2.901`).
- Rationale: one strict split is a promotion candidate, not enough evidence to replace the existing per-position walk-forward gate.

## 2026-07-18 — Use empirical interval coverage as the uncertainty gate

- Decision: expose mean, p75, p90, p95, and 25+ point tail probability in historical backtest rows and track their empirical coverage.
- Evidence: 15/15 Sunday-main slates and 2,856 players produced P75/P90/P95 coverage of `76.4%` / `90.3%` / `94.7%`, with zero configured alerts.
- Rationale: point-estimate MAE alone cannot validate simulation uncertainty or tail behavior.

## 2026-07-17 — Keep the classic sweep result provisional

- Decision: record but do not hardcode the bounded winner of 250 candidates, four training slates, and a 95th-percentile label.
- Evidence: 10/12 slates completed with `134.428` mean and `131.110` median actual-optimal gap.
- Rationale: the grid and history window were intentionally small implementation validation.

## 2026-06-07 — Centralize model defaults

- Decision: backend settings and `GET /api/model/defaults` are the source of product model paths and strengths.
- Rationale: CLI, UI, and benchmark workflows must share exact defaults while preserving explicit overrides.
