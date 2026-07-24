# Architecture and Model Decisions

This log records decisions that affect reproducibility, production defaults, or historical-model acceptance. The operational backlog remains in `docs/TODO.md`.

## 2026-07-24 — Make numbered migrations authoritative for target schema

- Decision: remove all `target` schema DDL from product services. Migrations `0013` and `0014` adopt the nine columns previously added opportunistically and record the exact migrated table, column/type/nullability, and constraint contract. Runtime services perform read-only compatibility validation against only the tables they use.
- Evidence: the static governance test rejects runtime `target` DDL, focused product-service and schema tests pass, and the canonical PostgreSQL target check reports 55 expected tables, 55 actual tables, and zero issues with an exact 14-file migration ledger.
- Rationale: idempotent `CREATE TABLE IF NOT EXISTS` and `ADD COLUMN IF NOT EXISTS` calls can hide missing deployments and structural drift. A migration-recorded catalog contract makes deployment history authoritative while preserving actionable runtime failures.
- Production impact: deployers must apply every numbered migration before starting product workflows. A missing or changed table, column/type, or constraint now fails compatibility validation instead of being silently created or altered by a request.

## 2026-07-21 — Persist async ultimate-lineup runs and checkpoint retries

- Decision: represent each UI-triggered ultimate-lineup comparison as an application-database run with a unique caller idempotency key, immutable request hash/payload, atomic queued-to-running claim, stage-local progress, terminal result/error, and attempt lineage. Assign a server-managed transactional candidate checkpoint when the caller does not provide one, and resume it on a compatible failed-run retry.
- Evidence: `backend/app/tests/test_ultimate_lineup_runs.py` proves exact idempotent reuse, different-request conflict, atomic worker completion/failure persistence, retry attempt lineage, checkpoint-resume selection, and create/get API behavior. The existing checkpoint test still proves resumed candidate UID order matches an uninterrupted sequence, simulation reoptimization tests now observe training/candidate/portfolio progress stages, and the production UI build passes.
- Rationale: candidate generation can outlive a normal browser request. Returning a run ID immediately makes the control plane responsive and observable, while persistent state prevents duplicate clicks and refreshes from silently launching different work. Keeping the candidate sequence in its existing SQLite checkpoint avoids storing hundreds of thousands of lineups in the application database.
- Production impact: the prior synchronous `POST /api/lineups/ultimate` remains available. The UI uses `POST /api/lineups/ultimate-runs`, polls the run, and can retry failed work. Run state is durable, but dispatch still occurs in the API process; multi-instance production should replace dispatch with a dedicated queue without changing the run schema or API contract.

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
