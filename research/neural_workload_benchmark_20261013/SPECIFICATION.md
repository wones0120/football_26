# Retrospective workload challenger specification — frozen before outcome evaluation

Frozen 2026-10-13. Previously inspected NFL outcomes are retrospective evidence. No pristine held-out claim, fantasy profitability claim, production promotion, or current Week 5 tuning is permitted. This specification is written before any prediction scores are computed.

## Question and population
Can a small shared player model improve next-game observed targets and carries over recent history and a tree using the same small football feature set? Fit separate targets and carries regressors. Include QB/RB/WR/TE with documented offensive participation in the label game (positive offensive snaps), positive identification via unique native-ID to canonical-ID mapping and valid game/team join. This is conditional workload among participants, not a pregame participation forecast. Do not treat absent stat rows or DNP as zero. Numeric zero in an observed stat record is zero. A participation row without a stat record remains an unobserved label and is reported, not silently filled.

## Fixed split and prerequisites
Use whole ordered (season, week) blocks: first blocks train, penultimate 4 validation, last 4 test, at least 12 train blocks and 1,000 training rows / 200 validation / 200 test per target. No random split or same week crossing splits. Validation is reported but no tuning; one fixed configuration per model. Every input version must carry a source ID and observed/imported clock after its completed source game and before the decision cutoff; the decision cutoff precedes target kickoff. Team and position must be documented before decision. Label sources may be postgame. Canonical mapping is a current deterministic identity aid, not a predictive feature; preserve any missing historical mapping chronology.

Past-season records first imported in 2026 do not prove they were available before 2025 game decisions. Do not run comparative performance if this audit fails. A retrospective reconstructed study, if desired later, requires its own clearly weaker specification rather than bypassing this gate.

## Small common feature set
Prior three measured games: mean targets, mean carries, last targets/carries, last-minus-mean trend, prior team skill targets/carries and player shares, prior offensive snap fraction (optional only when measured), history count and weeks since latest appearance. Position one-hot; no player ID, team ID, name, current-game outcomes, current/future standings, injury/news without historic clocks, routes guessed from targets, salaries, fantasy scores, or postgame adjustments. Team context follows the player's last documented team; flag or exclude unproven transfer context. All lags use source week < target week and source observation < cutoff. All statistics, imputers, scalers and position fallback priors fit train only.

## Fixed challengers
1. History: prior-three mean; train position mean for no history.
2. Tree: sklearn HistGradientBoostingRegressor, squared error, max_iter=100, max_leaf_nodes=15, learning_rate=0.05, l2_regularization=1, min_samples_leaf=30, early_stopping=False, random_state=261013.
3. Neural: sklearn MLPRegressor, (16,8) hidden units, relu, Adam, alpha=0.01, learning_rate_init=0.001, batch_size=128, max_iter=150, early_stopping=False, shuffle=False, random_state=261013. Standardize X and y using train only; zero-clamp final predictions for all models. Fixed thread count 1. No sweep. Abort after 120 seconds per target model and report incomplete fitting rather than a winner.

The tree is a suitable installed baseline, not a claim to reproduce the production fantasy-point tree. Shared weights learn role relationships across players; player identity is deliberately excluded.

## Predeclared metrics and diagnostics
Primary: targets MAE and carries MAE separately on the same test rows. Secondary: RMSE, mean signed error, position-specific MAE, sparse history (0–1 vs 2+), positive workload vs observed zero, role-shift cases (absolute next-minus-last workload >= 4) reported separately. Report test sample/week counts. Position/shift groups below 30 observations are descriptive only. Relative MAE reduction of >= 5% against BOTH baselines in BOTH targets and carries is the criterion for another neural experiment; below this is negative/inconclusive. No statistical certainty claim from a small single time window.

Sum point predictions by game/team across the documented conditional population and compare to its observed summed labels. This is a partial skill-player budget, not team pass/rush attempts. Perturb prior workload features +20% consistently, recompute associated shares/trends, report response and invalid input flags. No enforced redistribution. Residual quantiles are diagnostic, not calibrated joint intervals.

## Delivery if infeasible
Persist source SHA-256 hashes, source row counts and clocks, native/canonical ambiguity, zero/missing coverage, eligible week count, runnable benchmark and leakage/split/missingness/determinism tests. Report no NN improvement conclusion when no defensible comparison was run. Inputs required next: contemporaneous immutable weekly stats, offensive participation/snaps, versioned pregame roster/team/position, schedule and decision clocks covering the minimum split.
