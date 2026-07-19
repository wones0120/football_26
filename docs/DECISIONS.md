# Architecture and Model Decisions

This log records decisions that affect reproducibility, production defaults, or historical-model acceptance. The operational backlog remains in `docs/TODO.md`.

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
