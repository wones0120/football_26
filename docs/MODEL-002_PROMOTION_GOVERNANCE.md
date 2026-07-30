# MODEL-002 Promotion Governance Evidence

Date: 2026-07-30

## Outcome

`MODEL-002` is complete. An existing projection champion cannot be displaced by completion of a new
run or by an arbitrary active-run request. Evaluation evidence and the approval that changes the
pointer are separate immutable records, and every promotion has an exact approval-gated rollback.

## Acceptance Mapping

| Requirement | Enforced contract |
| --- | --- |
| Declared data window | `model_challenger_evaluation_v1` requires ordered, non-overlapping training, validation, and test season/week boundaries. |
| Feature lineage | Both completed same-scope projection runs must resolve to persisted, non-empty feature-set hashes. |
| Code lineage | Both code hashes are required; any hash already persisted on the model run must match the declaration. New prediction runs persist the SHA-256 code hash automatically. |
| Comparable gates | Metric name and minimize/maximize direction are unique per gate; champion/challenger values and required improvement are finite; at least one gate requires a strict positive improvement; all gates must pass. |
| Approval | Promotion requires `approved_by` and `approval_reason`, persisted in `model_promotion_decision_v1`. A stale or non-active declared champion blocks the transaction. |
| Reversible pointer | The promotion stores previous and selected run IDs. Rollback requires a second named approval tied to that promotion and atomically restores the exact previous run. |
| No silent activation | Prediction persistence uses insert-on-empty semantics for `active_projection_run`; conflicts do nothing. `/api/predict/active` validates a currently applied decision and is read-only. |

## API Contract

- `POST /api/model-governance/evaluations`
- `GET /api/model-governance/evaluations/{evaluation_id}`
- `POST /api/model-governance/evaluations/{evaluation_id}/promote`
- `POST /api/model-governance/decisions/{promotion_decision_id}/rollback`

The combined application exposes 114 unique method/path contracts after these four routes.

## PostgreSQL Evidence

Migration `0017_model_promotion_governance.sql` applied successfully to the development database.
The migration runner's second pass applied no files. Target schema validation with idempotency
verification reported:

- migration ledger: 17 files;
- expected target tables: 57;
- actual target tables: 57;
- drift issues: zero.

The existing Week 11 default-slate champion was preserved exactly:

- projection run: `baseline_rolling_dk_v0:projection:2025:11`;
- model run: `baseline_rolling_dk_v0:run:2025:11`;
- feature run: `baseline_rolling_dk_v0:features:2025:11`;
- feature-set hash: `rolling_player_position_history_v0+dst_context_v1`;
- selection reason: `schema_backfill_latest`;
- row count: 564.

No promotion record was created merely to demonstrate a successful path. The development database
currently has no second completed Week 11 default-slate projection and no legacy
`predictive_features` source table from which to train a truthful challenger. Fabricated improvement
metrics would violate the time-safe registry contract. The database therefore retains zero
challenger evaluations and decisions until real comparable evidence exists; focused tests exercise
both successful and blocked transactions.

## Verification

- Focused governance, route, prediction-lineage, app-smoke, and migration-coverage tests: 22 passed.
- Product service suite: 237 passed with two pre-existing `datetime.utcnow()` deprecation warnings.
- Full backend suite: 378 passed with the same two warnings.
- Target schema drift plus idempotency check: passed, 57/57 tables, zero issues.
