# Next Ideas Without Vendor Historical Data

Last reviewed: 2026-07-18

The platform will not depend on unavailable historical injury or ownership feeds. New signals must be derivable from salary snapshots, nflreadpy history, schedules, or our own simulation/lineup outputs.

## 1. Usage-Weighted Roster Continuity — Implemented, Not Promoted

Estimate recent team opportunity from the prior four games:

- opportunity = carries + targets for RB/WR/TE;
- missing usage share = prior opportunity belonging to players absent from the current salary pool;
- available usage concentration = concentration of the remaining opportunity;
- identity coverage gates the signal to avoid treating unresolved aliases as absences.

With unresolved current salary players included in the identity-coverage denominator, the 41-slate walk-forward candidate scored `27.3%` top-1 and `51.5%` top-2 versus the current-code baseline at `33.3%` and `57.6%`. It was rejected as a standalone captain feature set. The time-safe signal remains useful as an input to manually triggered role-shock and lineup-fragility research.

## 2. Popularity and Duplication Proxy — Implemented

Build a transparent expected-popularity score from only pre-lock fields:

- salary rank and projected value;
- position scarcity;
- game total and implied team total;
- recent usage and volatility;
- stack popularity pressure;
- similarity/duplication risk across generated lineups.

Call this a `popularity_proxy`, never observed ownership. Validate it by lineup concentration, uniqueness, and historical actual-points tradeoffs rather than pretending to measure field ownership.

The ultimate classic lineup workflow now returns per-player proxy/candidate exposure and per-lineup duplication risk, with an opt-in risk penalty that defaults to zero. On 12 historical classic slates, penalty `0.25` reduced proxy risk `1.1%` with a `0.2%` projected-blend cost and `0.28` fewer actual points. Penalty `0.75` reduced risk `6.7%` but cost `5.0%` projection and `8.37` actual points. No nonzero default was promoted.

## 3. Role-Shock Simulation — Implemented

Create controlled scenarios that remove or reduce a player’s opportunity share and reallocate it within the team by position and recent role. Measure:

- projection and p90 movement;
- captain archetype movement;
- lineup exposure changes;
- fragility of the top portfolio across shocks.

This gives useful pre-lock stress testing even when the triggering news itself is entered manually.

The simulation API and UI now support a deterministic manual target, retained-opportunity share, same-position/all-skill reallocation, recipient cap, and separate opportunity/projection multipliers. Seeds and the complete request are stored on `simulation_run`. The Week 18 Gibbs zero-retention example moved target exposure from `30%` to `0%`, retained `70%` top-lineup overlap, and recovered `6.69` projected-blend points after scenario reoptimization.

## 4. Online Residual Learning — Implemented, Default-Off Integration

After each completed week, learn rolling residual adjustments by:

- player;
- team and position;
- opponent defense and position;
- salary/value bucket;
- game-total/spread regime.

Use shrinkage and strict prior-week cutoffs. Promote an adjustment only when it improves later-window calibration or MAE.

The deterministic walk-forward implementation combines canonical player, team-position, opponent-position, salary, projected-value, and pre-lock game-regime residuals over a rolling 12-slice window. Prior strength `5.0` was selected only on 2025 W05-W10. On the untouched 2025 W11-W18 test window, it improved MAE `4.818` to `4.602` (`+4.48%`) and RMSE `6.551` to `6.389` (`+2.47%`) across 1,205 observations. All five test slices and QB/RB/WR/TE improved.

The learner is integrated into DraftKings weekly simulation behind a default-off gate. Immutable snapshots preserve observations and model lineage, scoring reads only strictly prior compatible snapshots, and insufficient history visibly falls back to baseline. The initial backfill created 15 snapshots with 3,342 observations and zero failures; a repeat run reused all 15.

## 5. Game-Regime Ensemble

Cluster slates into future-safe regimes such as:

- high-total close game;
- low-total favorite;
- concentrated offense;
- depleted/low-continuity offense;
- volatile low-salary pool.

Train or weight projection/captain policies by regime and retain global fallback models for sparse cells.

## Acceptance Rules

1. Every feature must be available before the target slate locks.
2. Identity coverage must be reported and low-coverage signals suppressed.
3. New candidates run against the exact current-code baseline with the same slices and seed.
4. Top-1, top-2, gap, calibration, and stability tradeoffs are reported separately.
5. A candidate never replaces production automatically.
