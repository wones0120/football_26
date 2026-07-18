# Architecture and Model Decisions

This log records decisions that affect reproducibility, production defaults, or historical-model acceptance. The operational backlog remains in `docs/TODO.md`.

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
