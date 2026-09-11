# Projection Model Quality Repair

Goal: replace the all-position, inactive-player-biased projection mean with a
time-safe position-aware model for QB, RB, WR, TE, and DST. Existing projection
runs remain immutable; validation must create a new run.

## Diagnosis

- [x] Trace the displayed JSN projection to its persisted projection run.
- [x] Reproduce `9.4410544065` from the saved model inputs and scoring formula.
- [x] Confirm that historical nonparticipants dominate the current shrinkage
  baseline (59.3% zero labels; all-player mean 3.78).
- [x] Confirm that the feature matrix lacks the lagged usage input needed by the
  receiver role classifier.

## Implementation

- [x] Join historical participation evidence by canonical player identity.
- [x] Exclude known `did_not_play` skill-position rows from model fitting and
  residual calibration while retaining genuine zero-point games.
- [x] Derive a strictly lagged three-game offensive snap-share feature.
- [x] Add explicit QB/RB/WR/TE/DST indicators to the shared point model; this
  outperformed five isolated models on the declared validation evidence.
- [x] Select any point-estimate shrinkage or player-history blend from historical
  holdout evidence, not from the desired result for one player.
- [x] Persist the position model, participation filter, role inputs, and metrics
  in model-run lineage.

## Tests and validation

- [x] Cover participation filtering without future-week leakage.
- [x] Cover lagged snap-share calculation and primary receiver classification.
- [x] Cover position-specific model inputs, including DST.
- [x] Run targeted projection tests and the full backend suite.
- [x] Build a new 2026 Week 1 Wednesday-night projection run.
- [x] Inspect projection distributions and named starters across all positions.
- [x] Confirm the optimizer consumes the new projection run.

## Documentation

- [x] Update the projection data-model documentation.
- [x] Update README usage/behavior notes.
- [x] Add a concise release note.
