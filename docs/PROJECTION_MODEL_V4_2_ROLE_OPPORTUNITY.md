# Projection model v4.2: measured offensive role

## Fitted-model auditability

New projection runs store an immutable, run-specific fitted tree artifact in
`target.model_artifact`, including the training and scoring frames, feature schema,
training fingerprint, cutoff, code hash and Git revision, and residual/P90 calibration.
The artifact bytes have a SHA-256 checksum. Projection persistence first reloads
the bytes and verifies identical raw model predictions; the audit endpoint checks
that the saved model-run URI and checksum still match before producing an explanation.
Historical runs without fitted bytes remain marked unavailable. A current registry
entry cannot substitute for a missing run-specific artifact.

`GET /api/predict/audit/{projection_run_id}` reports artifact status. The player
endpoint at `/api/predict/audit/{projection_run_id}/player/{player_id}` returns
saved inputs, exact tree-path attribution of the raw fitted regressor, and
one-feature market and role counterfactuals when reloading succeeds. Tree-path
attribution is not SHAP and neither it nor a counterfactual is a causal claim.
The **Model disagreement** panel compares separately captured external means
with saved projection means. External values never blend into the model.

The frozen Week 3 Sunday Main run `d150bb2a-91a8-46b6-9aa6-eaa9f0229bde`
has model metadata but no fitted bytes. Its neutral-spread and average-total
rescores cannot be reconstructed exactly. ESPN's original Week 3 DraftKings
article was captured on September 26, 2026; all 198 published players,
including all 44 RBs, matched canonical frozen salary IDs. The structured
snapshot and RB comparison are saved in `artifacts/week3-espn-benchmark-2026.json`
and `.md`; benchmark ID `bbd90510-a231-42da-bd22-2af46322096a`.

The canonical projection path now calculates `offensive_role_importance` for RB, WR,
and TE from cutoff-safe, prior-three-game opportunity shares. RB weights are 55%
RB carry share, 25% target share, and 20% offensive snap share. WR/TE weights
are 75% target share and 25% snap share. Available weights are renormalized;
the score is `null` when no input is available. Salary and player identity do not
enter the calculation. `offensive_role_completeness` records the available input
weight. The saved role class, reason, source, and confidence make the diagnostic
auditable. Explicit current shares replace historical shares when supplied.

The regressor adds only `offensive_role_importance` and
`offensive_role_completeness` to the previous feature list. Raw carries, targets,
and their shares remain in lineage and in the explicit current-role adjustment,
but are excluded from the regressor because the combined raw feature sets
regressed in historical evaluation. Missing scores are represented as `null` in
lineage and imputed to zero only in the numeric model matrix, where completeness
distinguishes missing from measured zero.
The weekly source must carry numeric carry and target fields. A missing raw field
fails input preparation rather than being silently recoded as a measured zero;
the existing historical source was checked and has both fields for every row.

## Historical validation

Chronological evaluation on the available 2025 Weeks 10–18 yielded 2,106
held-out player games. The same 80% model / 20% prior-history blend was used in
both models. Each validation week was trained only on earlier games.

| Feature set | MAE | MAE, salary $6,000+ |
|---|---:|---:|
| Previous feature list | 4.1365 | 6.6780 |
| Role score + completeness | 4.1237 | 6.6606 |
| Raw shares + counts + role score | 4.1481 | 6.7371 |

The improvements are small and are not proof of improved lineup returns. This
comparison differs from the older v4 raw-opportunity experiment: the retained
feature is a measured, compact role summary.
The full feature ablation is saved in
`artifacts/role-feature-walk-forward-2025w10-18.json`; rerun it with
`PYTHONPATH=. .venv/bin/python scripts/evaluate_offensive_role_features.py`.

## Current role and ceiling

Expected current carries or targets can become explicit team shares only when a
team-volume estimate exists. Supplied shares or availability evidence activate
the pre-existing position-specific opportunity adjustment. With no such evidence,
the adjustment stays inactive. The base mean, opportunity anchor, weight, and
adjusted mean are saved for each player.
The derived share and its source are also used by the role score, so a count-only
context update does not leave the role diagnostic stale. Contradictory share and
count evidence is rejected rather than silently choosing one.

Projected carries and targets are lagged team-volume allocations. Their source
and unallocated volume are recorded. They are not independently forecast pass
attempts, all-position carries, red-zone opportunities, receptions, yards, or
touchdowns. Those quantities remain unavailable when there is no source.

The P90 residual calibration may split a position/role group by measured role
score. Each half must have at least 50 historical walk-forward residuals; sparse
groups keep the prior position/role profile. The conditional quantiles are
estimated from those residuals, without a fixed bonus for a role label. Team
importance, mean, and P90 ranks are saved and large disagreements among the
top three skill roles are flagged for review.
The Thursday run had eight sufficiently populated position/role groups for an
importance split; the actual threshold and sample sizes are saved in the model
run calibration metadata.

No optimizer strategy or lineup weight was changed.

## Role validation diagnostics

New projection runs save a diagnostic grid for each measured RB/WR/TE role:
importance at the observed value and nearby values, plus completeness at 0.50,
0.75, and 1.00. All other model inputs are held fixed. Importance scenarios are
bounded by the historical 5th and 95th percentiles for that position, except that
an observed value outside the range remains the baseline. The grid reports the
pre-opportunity point-model mean and never changes the saved projection. Tree
responses can be non-monotonic; they are conditional model sensitivity, not a
causal estimate of playing time.

Historical calibration is grouped by measured role class and by position and
class. Each group reports actual mean, signed mean error (predicted minus actual),
MAE, RMSE, and an evaluable ceiling-hit rate. The ceiling threshold is the held-out
point prediction plus the 90th-percentile residual from *earlier* periods, with a
position/global fallback for sparse groups. It is a time-safe P90 proxy, not an
exact replay of the production shrinkage-calibrated P90.

Role trend compares the last observed game with the preceding three observed
games for snap, target, and RB rush share. Missing prior games remain unavailable.
The target/carry comparison explicitly labels current allocated counts as lagged
proxies and records whether separate pregame opportunity context was applied.
The Classic report flags high-confidence team role leaders with low projection,
value, or candidate-exposure ranks across the full eligible pool. Omission
explanations compare the selected lineup with the best generated candidate
containing that player. The objective gap is a complete-lineup difference; it
cannot isolate one player's causal effect.

To audit an existing saved Sunday run without writing production projections or
running the optimizer, use:

```bash
PYTHONPATH=. .venv/bin/python scripts/validate_role_diagnostics.py \
  artifacts/sunday-main-role-validation-2026w2.json \
  artifacts/sunday-role-diagnostic-2026w2.json
```

The Week 2 findings and rendered report are saved as
`artifacts/sunday-role-diagnostic-2026w2.md` and
`artifacts/sunday-role-diagnostic-2026w2.html`. This audit found that the three
high-role RB examples have lagged target/carry allocation proxies equal to their
recent three-game means, with no separately recorded matchup adjustment to the
counts. It also found mean overprediction of 1.10 points for the held-out
offensive-centerpiece bucket; review sample composition and the production P90
calibration before changing model weights.
