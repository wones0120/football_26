# Shared Classic and Captain path audit

Date: 2026-10-10. Immediate live priority: **2026 Week 5 Sunday Main GPP**.

The application uses one Classic path and one Captain/Showdown path. Main, early-only and late-only are Classic slate inputs; Thursday, Sunday and Monday night are single-game Captain slate inputs. GPP strategy defaults and optimizer objective weights were preserved. This work repairs the shared workflow; it does not establish improved GPP paid-finish rates, expected returns or upside.

## Findings and repairs

| Finding | Repair |
| --- | --- |
| Weekly orchestration explicitly rejected Showdown at simulation | Both formats dispatch through the same durable simulation stage |
| The simulator assumed nine Classic slots and excluded kickers/low-salary Captain players | Added a versioned Showdown model with one CPT, five FLEX, six unique canonical players, both teams from one verified game, and native slot salaries; all positive Showdown salaries are allowed |
| CPT/FLEX could not be simulated or replayed as the same physical player | Sample each player's distribution once per iteration; apply 1.5 points only to the Captain assignment; persist/reload separate CPT/FLEX counts and the exact Captain salary through existing JSON evidence |
| Salary selection could pick an arbitrary slot and use data after the forecast cutoff | Select FLEX salary rows for Showdown and natural roster positions for Classic; use canonical positions, site/slate filters and salary clocks no later than the projection cutoff; Classic does not execute the Captain-salary lookup |
| Showdown ownership slot semantics would be ambiguous | Sum predicted CPT and FLEX percentages for physical-player any-slot comparison; do not substitute legacy ownership without supported slot semantics |
| A supplied simulation ID could return another scope's completed result | Require matching season/week/slate/format, seed, sample count, cap and explicitly supplied source-run IDs before idempotent reuse |
| Weekly projection reuse checked the week but not its slate | Include slate identity in the completed-projection summary and reject another/unknown slate; explicit legacy `DEFAULT` projection scope remains compatible |
| Simulation could ignore newly prepared ownership | Prefer the ownership run frozen by weekly preparation over an older request value |
| Run Simulation was disabled for Captain | Enable both formats; separate in-session result displays by slate and format; expose the meaning of simulation frequencies |
| Browser storage and menus discarded labels outside a fixed weekday list | Accept validated distinct identifiers, discover saved-contest scopes for the selected week, and retain the selected scope across navigation/reload; keep standard options available |
| Individual preparation actions omitted the selected format | Forward Classic/Showdown with those actions |

Native contest/draft-group compatibility, fresh source readiness, user constraints and export validation remain required. Merely naming a custom slate does not verify it. New labels must point to the correct imported/native salary/game set; reusing the same label for two different offerings is not supported. This change does not introduce a new native draft-group primary-key migration or automatic lobby discovery.

## Evidence matrix

| Slate | Format | Verified by fixtures | Live source clearance |
| --- | --- | --- | --- |
| Sunday Main | Classic GPP | Default strategy, workflow simulation through export-stage completion, actual SQL pool/persistence/replay, UI prepare/optimizer/simulation dispatch | Live preparation completed READY after preserving official practice evidence; 100/100 live simulations persisted and reloaded; final entry clearance remains separate |
| Sunday early-only | Classic GPP | Same checks through the shared Classic dispatch | Requires actual selected slate inputs and fresh preparation |
| Sunday late-only | Classic GPP | Same checks through the shared Classic dispatch | Requires actual selected slate inputs and fresh preparation |
| Thursday night | Captain GPP | Default strategy, actual Captain simulation/SQL/persistence/replay, workflow continuation, UI dispatch | Requires actual selected game inputs and fresh preparation |
| Sunday night | Captain GPP | Same checks through the shared Captain dispatch | Requires actual selected game inputs and fresh preparation |
| Monday night | Captain GPP | Same checks through the shared Captain dispatch | Requires actual selected game inputs and fresh preparation |
| Additional same-day game label | Captain GPP | Separate SQL pools/results and saved UI context; discovered option survives reload | Requires verified saved contest and matching imported salary scope |

The browser fixture uses the real built UI and isolated API responses; it checks requests rather than placing entries. Workflow-chain fixtures use synthetic source/other stages with the real default simulation stage and MILP. PostgreSQL fixtures execute real schema, queries, simulation, persistence and immutable replay in a disposable database. Existing optimizer and export suites validate roster construction, Captain multipliers, native slot IDs and rejection of illegal exports. These are complementary contract tests, not a claim that external data is already available for every future slate.

### Sunday Main protection

A read-only comparison of the pre-change and updated simulation loaders used saved projection `f3a3b0d0-30e7-48fa-a968-9889cccf927f` for 2026 Week 5 Sunday Main:

- Both returned 307 eligible players; no additions or removals.
- Salaries and projected means matched exactly by canonical player ID.
- The existing browser regression retained `classic_large_gpp_v1`, GPP objective, five requested lineups and the exact prepared projection/job linkage.
- The initial parity audit was read-only. The subsequent authorized activation below created fresh projection, ownership and simulation runs through the app.

This parity check certifies loader behavior against that saved build, not freshness of its evidence. The initial 15-second preparation read timed out; the subsequent live activation used a longer timeout and exposed stale evidence, as recorded below.

## Validation

- 167 focused Python tests passed across simulation, joint-research isolation, weekly orchestration, preparation, optimizer routing, projection calibration and exports.
- 6 projection-job repair tests passed after the completed-run summary gained slate identity.
- 8 isolated PostgreSQL integration tests passed, including native slot salaries, low-salary/kicker retention, ownership, exact replay, run metadata and rejection of salary snapshots after cutoff.
- 143 UI unit tests passed. Two pre-existing source assertions still named the retired `singleLineupParams` helper; they were corrected to the existing `optimizerParams` helper without changing runtime behavior.
- The new seven-slate browser fixture and existing Sunday Main preparation/optimizer browser fixture passed, including narrow viewport overflow checks.
- UI type-check/build, Python compilation of touched modules and documentation/diff whitespace checks passed. Vite retains its existing large-bundle advisory.

Reproduction:

```sh
.venv/bin/python -m pytest backend/app/tests/product/test_simulations.py backend/app/tests/product/test_showdown_simulations.py backend/app/tests/test_weekly_orchestrator.py backend/app/tests/product/test_draftkings_export.py backend/app/tests/product/test_slate_preparation.py backend/app/tests/product/test_optimizer_mode.py backend/app/tests/product/test_prediction_calibration.py backend/app/tests/product/test_joint_simulations.py backend/app/tests/test_projection_job_repair.py -q
npm --prefix ui test
npm --prefix ui run build
node ui/tests/sharedSlates.e2e.mjs
node ui/tests/preparedOptimizer.e2e.mjs
```

Browser scripts accept `PLAYWRIGHT_MODULE` when Playwright comes from a bundled runtime. Database integration is opt-in: point `SHARED_SLATE_TEST_DATABASE_URL` at an **empty disposable PostgreSQL database**, then run `backend/app/tests/product/test_shared_simulations_postgres.py`. It refuses an existing target schema and does not connect to application data by default. The database test provisions the existing target migrations and checks the schema contract; no product migration is required by this repair.

## GPP interpretation and remaining work

`independent_quantile_lineup_v1` (Classic) and `independent_quantile_showdown_v1` (Captain) describe optimal-roster frequencies under independently sampled player marginals. They do **not** simulate an opponent field or provide calibrated paid-finish probabilities, expected payout or ROI. Captain simulation remains diagnostic; this repair does not automatically wire its frequencies into production selection weights. Joint game-script simulation and contest-field calibration remain research gates.

The next performance work remains GPP-specific: validate projection quality, candidate coverage and selection against real tournament fields and full payout ladders, measuring paid finishes, expected/realized return and upside separately. Keep overlapping Main/early/late and single-game contests in the same game/time partition during validation. Automatic postgame reporting and model learning remain in the broader [decision workflow](automated_decision_quality_workflow.md).

## Live activation and Sunday Main follow-through

On 2026-10-10, the local API and durable worker were restarted after confirming both running and queued job lists were empty. The running UI serves the shared simulation controls, and live OpenAPI exposes Captain role fields. Other already-saved workspace changes are also loaded by this restart.

The first fresh Sunday Main preparation (`94af9064-0cbb-49f1-8312-c51c3ebc296b`) saved new projections and ownership but correctly stopped before lineup generation. Investigation found that the official roster/depth supplement dropped the top-level practice report while retaining it inside source lineage. Chris Manhertz therefore appeared to lack practice evidence even though the captured official report recorded full participation.

The supplement now retains independently sourced practice/risk evidence and its original clocks. It does not clear questionable designations, infer full workload, renew stale evidence or waive readiness. The new live context retains `Q`, `FULL` practice and unknown expected workload.

Repaired preparation `c957c15a-b95e-442d-bf7c-cc0cff9780a0` completed with source readiness `READY`, projection `506c698c-a09c-4665-a79c-058c578de453`, ownership `f28f226d-9126-47f8-a08e-e0bbc2c7d8c7`, and cutoff `2026-10-10T12:06:57.469934Z`. Live simulation `c166b113-9bd1-4b8a-94a5-99edb8f604b7` completed 100/100 iterations for 307 players; persisted API retrieval exactly matched its returned player rows. This is a workflow smoke test, not a calibrated GPP performance experiment. No optimizer lineup or contest entry was created during activation. Final availability and native entry compatibility still require prelock review.

The targeted repair checks passed 122 tests across Classic readiness, official injuries and preparation, including missing/stale/future practice cases. One existing salary-provenance test (`test_valid_legacy_import_does_not_need_a_new_snapshot_but_missing_draft_group_blocks`) failed because its expected `salary_native_draft_group_missing` reason was absent. It does not exercise the changed supplement; it was excluded from the passing targeted run and remains unresolved. Compile and whitespace checks passed.

The user's immediate preference is one recommended lineup per slate, reused across its GPP contests. Saving specific contests is deferred and is not a prerequisite for lineup generation. Contest-specific expected-return and realized-payout evaluation will need contest evidence later. Existing runtime lineup-count controls were not changed by this activation.
