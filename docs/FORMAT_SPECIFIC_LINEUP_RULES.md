# Format-Specific Lineup Rules

## Direct lineup downloads

`GET /api/optimizer/results/{job_id}/draftkings/download` exports all lineups from a
completed saved run without contest-entry assignments. Classic columns are
`QB,RB,RB,WR,WR,WR,TE,FLEX,DST`; Showdown columns are
`CPT,FLEX,FLEX,FLEX,FLEX,FLEX`. Captain cells use saved `dk_captain_id` values.
Downloads validate IDs, roster composition, salaries and duplicates before
returning a CSV, or a ZIP of CSVs for runs exceeding 500 lineups. The result-card
button is **Download all N lineups for DraftKings**. Matching entry templates
remain necessary only for the separate export that updates existing entries.
For Classic saved lineups, an explicit `FLEX` roster slot is exported using the
player's underlying RB, WR, or TE position when validating the nine-player roster.

## Contract

Showdown cash player scoring uses `showdown_cash_distribution_v1`: the declared
profile's mean, median, P10 and P90 weights plus context. The Captain solver
applies 1.5 to that score. Missing quantiles fall back to mean; existing lineup
correlation terms remain separate. Saved runs retain component explanations and
weights. Showdown GPP continues using its context-adjusted ceiling objective.

Phase 5 advanced the active `optimizer_lineup_correlation` library to v2. Phase
5A advances it to v3 by context-weighting positive stack terms and removing
structural correlation floors. The active v4 adds Classic H2H variance controls
without changing lineup feasibility. It retains the configured maximum weights
and higher-order construction terms for Classic and Showdown. The same term
builder and exact binary linearization run in the baseline optimizer and
advanced Classic GPP engine.

These are objective preferences, not eligibility gates. They do not alter
DraftKings roster or salary rules, user locks, exposure controls, or explicit
strategy-owned stack requirements. A legal lineup that triggers a penalty can
still win when its projections justify it.

## Classic rules

Classic construction rules include:

- a GPP-only naked-QB penalty of up to `-1.10`, reduced continuously by the
  quarterback's source-backed rushing-role strength and eliminated at maximum
  rushing strength;
- a GPP-only QB double-stack bonus of up to `+0.65`, multiplied by a
  cutoff-safe game-total, implied-team-total, competitiveness, opponent-push,
  and blowout-risk score; missing context contributes zero;
- a Classic H2H-only `-0.85` QB variance penalty before profile scaling when a
  quarterback is paired with at least two same-team WR/TE players;
- a Classic H2H-only `-0.55` concentration penalty before profile scaling when
  three or more QB/RB/WR/TE players come from one team;
- a penalty of `-0.75` before profile scaling when three or more RB/WR/TE
  players from one team appear without that team's quarterback;
- a GPP-only full-game-stack bonus of up to `+0.55` when at least four
  offensive players span both teams in a cutoff-safe competitive shootout.
- a contradiction penalty of up to `-0.90` when a meaningful favorite's
  early-down RB appears with the opposing DST and multiple pass catchers from
  that underdog.

The existing pair rules still score QB + WR/TE, receiving RB stacks,
bring-backs, RB/DST combinations, mini-correlations, and DST conflicts. In H2H,
the higher-order variance terms reduce the appeal of concentrated offense when
individual objective scores are similar. They remain soft, so a sufficient
projection advantage or a user lock can still select the same-team build. DST
is excluded from the offensive concentration count, preserving the RB/DST
benefit.

## Showdown rules

Showdown v2 adds:

- up to `+0.90` for a QB Captain with at least two same-team WR/TE partners,
  multiplied by the same cutoff-safe stack-environment score;
- `-0.80` for a WR/TE Captain without his quarterback;
- up to `+0.60` in large-field GPP for a 5-1 build led by a meaningful favorite;
- up to `-1.10` for a 5-1 build led by a meaningful underdog;
- up to `+0.35` for a competitive 3-3 build and `+0.20` for a competitive 4-2;
- up to `+0.65` for a favorite RB Captain with source-backed rushing volume;
- a sub-$1,000 no-role punt penalty of `-0.90` in H2H and `-0.35` in GPP before
  canonical profile scaling.

A cheap RB/WR/TE avoids the punt penalty when current evidence supplies a
positive snaps, routes, carries, targets, usage-share, red-zone, goal-line, or
specialty-role path. Missing evidence is never fabricated. Pick'em or missing
spread data does not create a favorite/underdog 5-1 contribution.

For `showdown_gpp_portfolio_v3` portfolios of up to five entries, every viable
Captain receives a forced-CPT legal solve before global portfolio selection.
The candidate pool also includes ordinary and prior sequential solves, script
constructions, and the legal highest-mean and highest-P90 rosters. Identical
Captain/FLEX player sets are deduplicated by canonical player ID. Discovery
also probes lineups without frequently shared non-QB players, without removing
those players from the slate. A lineup must
reach 95% of both raw-quality maxima to enter the portfolio selector; the
selector does not relax that screen to fill an entry. CPT/core/starting-QB/cheap-
punt exposure rates remain 60/80/100/40%. The saved report records rank, raw
quality and selector losses, Captain-family coverage, and binding constraints.
Favorite 4-2, 5-1, RB-control, DST-control, and RB+DST-control constructions
are explicitly solved into the candidate pool; none is forced into the final
portfolio. Positive QB-linked soft rewards use a 0.4–1.0 multiplier based on
that QB's projected mean relative to the slate's highest projected QB mean.
This multiplier does not edit projections. Showdown no longer limits lineups
to one tight end.

### Game-script scenario discovery (`market_margin_role_conditioning_v1`)

The market baseline uses the unchanged, cutoff-safe player distributions.
When both teams have consistent market totals and implied scores, the candidate
generator also conditions on each team winning by at least the configured
margin (default 14 points; valid 7–35). It holds the game total fixed and
sets the conditional team scores to the least extreme implied-score split that
satisfies the margin. If the market is missing, inconsistent, or marked unsafe,
only baseline candidates are generated and the coverage report says why.

The temporary conditioning pool changes team implied totals and role-sensitive
mean/P90 values, then runs the normal Showdown solver. Winning early-down RBs
receive a bounded rush-volume sensitivity; winning QB/WR/TE lose late pass
volume; winner DST gets a sack/turnover sensitivity. Trailing QB/WR/TE and
receiving RBs receive a pass-volume sensitivity, while early-down RBs and DST
lose opportunity. Kicker sensitivity follows team scoring and trailing
fourth-down behavior. A scoring component responds to the change in team
implied total. The component is capped at ±12%; combined player adjustments
are capped at 0.78–1.22× baseline. P90 uses the same factor, preserving the
original player spread ratio. Ownership, salary, eligibility, Captain prior,
user preferences, and the baseline distribution do not change. There is no
winner-team objective bonus and no mandatory lineup team count. This is an
explainable sensitivity model, not a calibrated conditional probability or a
joint simulated lineup percentile. The saved candidate and selected-lineup
audits record every adjustment, reason, market input, method version, and
selection reason. The HTML report displays scenario coverage and baseline
versus conditioned player values.

`require_scenario_diversity` is off by default. When on, the portfolio selector
maximizes feasible entry count, then distinct scenario-family coverage, then
its existing selector score. It never relaxes the 95% joint quality screen or
Captain/player exposure caps to fill a family. The report records which
lineups differ from the normal selection and why a family is missing.

The method is validated by deterministic tests for market conservation,
two-sided role responses, adjustment bounds, unchanged baseline, quality-floor
retention, and duplicate-roster prevention. Historical calibration of
conditional player outcomes is not yet available; do not interpret the
factors as estimated effects. A future joint-game simulator can replace
`condition_player_pool` with conditional sample filtering while retaining the
scenario IDs, candidate generators, and portfolio selection interface.
The **Historical Captain Optimality** report uses legal actual-score Showdown
oracles, not tournament winners. It deduplicates one repeated historical game,
leaving 45 completed games. One game has two tied optimal Captains; position
shares count the oracle's deterministic selection once, while preserving both
co-optimal Captains in the saved slate record. It shows position shares separately from rates
per legal Captain opportunity, both for all eligible QBs and a pregame-identified
starter subset. Starter evidence uses an archived pre-kickoff identity record
when available; otherwise a clear salary and strictly prior passing-volume
leader is labeled inferred. Ambiguous teams are excluded from starter rates.
QB archetypes use carry-volume terciles; prior-three rushing yards and TDs are
observed pregame proxies, while historical projected rushing-yard/TD components
and goal-line/design/scramble evidence are unavailable. The high-rush label
does not assert a measured goal-line role. Wilson intervals and small-sample
labels accompany the rates. Archetype boundaries for chronological validation
are fitted on the 2024 training period only, which has three optimal-QB events.
No archetype-specific production score adjustment is enabled. The report retains
the existing Captain-position prior and shows hypothetical QB-CPT score
adjustments and ranks separately from actual selection.
Historical actual field CPT ownership and full prelock candidate-pool replay
are unavailable; saved ownership projections are not field outcomes.
The lineup report shows team counts, saved spread and implied totals, and the
projection run's direct versus calibrated market response. The team-market
projection adjustment is applied before optimizer scoring and does not add a
separate game-total bonus. It describes an aggregate team response; QB-specific
efficiency, explosive rate, touchdown rate, and play-volume changes are not
individually identified by the current fitted model.
If the slate pool lacks complete role ownership, the ownership objective is
disabled for all candidates. Per-lineup ownership, chalk, and ownership product
are shown only when every selected slot has role ownership; the product is a
relative signal, not a duplication probability.

Operations also supports the Showdown-only
**Exclude from Captain (FLEX still allowed; comma-separated names)** control. It resolves each supplied
name to an unambiguous canonical ID inside the selected slate, constrains that
player's Captain variable to zero,
and leaves the FLEX variable eligible. FLEX-only is independent of a player
lock: using both means the player is required in FLEX, while FLEX-only by itself
does not require selection. The canonical IDs and supplied names are retained
in `strategy_runtime.player_controls`, and completed-lineup validation rejects
any FLEX-only player returned at CPT.

## Exact activation and audit

Higher-order terms use binary indicators for all required conditions:

- selected anchor or Captain;
- minimum and maximum selected counts;
- required team representation;
- absence of a specific partner such as the quarterback.

Both positive and negative indicators are constrained in both directions, so
the solver cannot hide a penalty by setting an optional helper variable to
zero. Completed lineups are recomputed from their selected players and persist
the same contribution in `lineup_correlation_summary`. Each format-specific
entry includes `construction_kind`, involved players, source evidence, raw
rule contribution, and effective objective contribution.

Operations already renders these entries under `Correlation rules`, so older
runs remain compatible and v4 runs require no new UI control. Runtime metadata
stores the library and profile versions used for the solve.

## Current limits

The v4 weights are an `initial_policy_unvalidated` prior. Team splits and
construction labels are explainable heuristics, not estimated game-script
probabilities. Phase 6A now computes experimental joint lineup median/P75/P90 and generic score-threshold probabilities through `joint_game_factor_research_v1`; see `docs/PHASE_6A_JOINT_SIMULATION.md`. Learned joint outcomes and tournament thresholds still require point-in-time-safe simulation/field evidence before any production promotion claim.

Until joint lineup simulation is implemented, completed lineups expose
`Individual Ceiling Sum`, the sum of selected player P90 values. That metric is
explicitly marked `is_joint_quantile: false` and must not be presented as a
lineup P90.
