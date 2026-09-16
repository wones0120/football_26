# Classic Optimizer Contest Strategy TODO

Last updated: 2026-09-10

## Completed in this implementation

- [x] Add explicit `classic_head_to_head_v1` and `classic_large_gpp_v1` contracts.
- [x] Keep roster, injury, identity, salary, projection, and pregame-availability
  preprocessing shared before strategy selection.
- [x] Use a broad positive-opportunity H2H pool and remove backup QBs with a
  concrete reason.
- [x] Use a mean-dominant H2H objective with secondary P90/P10 evidence, a
  fragile-punt penalty, and soft rather than mandatory correlation.
- [x] Return the requested number of H2H lineups; Operations may suggest six,
  but an explicit caller count is authoritative.
- [x] Add a ceiling-led Large GPP objective that assigns zero ownership/leverage
  weight when ownership evidence is absent.
- [x] Diversify GPP portfolios with minimum uniqueness, max exposure, optional
  player-specific min/max exposure, team/game caps, and rotating QB stack
  templates with optional bring-backs.
- [x] Persist selected strategy, objective/config, pool audit, realized stack,
  and lineup-level mean/P90/floor where applicable.
- [x] Replace `strategy_candidate_filter` for the two current Classic strategies
  with concrete backup-QB, projection, value, ceiling, positional-cap, and
  team-cap reasons.
- [x] Add the Operations `Contest Strategy` selector and make the selected mode,
  eligible/included/excluded counts, lineup distribution, and stack visible.
- [x] Validate both modes on projection run
  `d05884f8-934d-492f-9b2b-65914d97c6b8` for 2026 Week 1 Sunday Main.

## P0 — required before trusting entry decisions

- [ ] Audit the current Sunday Main player/team/role mapping behind the generated
  lineups. Confirm every selected player's canonical team, opponent, active-roster
  status, and expected role against the newest source snapshot; repair source-ID
  mappings rather than player display names.
  - Acceptance: every selected row has source-backed team/opponent/role evidence,
    and a mismatch creates a visible identity/data-quality issue instead of entering
    optimization.
- [ ] Load a complete point-in-time injury/availability snapshot for Sunday Main
  and rerun projections before using the output for entries.
  - Acceptance: readiness no longer warns that the injury snapshot is incomplete;
    unavailable-player opportunity redistribution is present in projection lineage.
- [ ] Backtest both new objectives on time-safe historical Classic slates before
  treating their suggested weights as performance-validated defaults.
  - H2H metrics: mean actual score, opponent win rate when contest evidence exists,
    weekly-high-score rate, P10 downside, and regret versus max projected mean.
  - GPP metrics: top 1%/0.1% rate, duplication proxy, payout/ROI only where payout
    evidence exists, portfolio overlap, and exposure stability.
  - Acceptance: promote/tune/reject decisions are versioned; current v1 contracts
    remain reproducible.

## P1 — operational completeness

- [ ] Extend the player-pool audit to include rows rejected inside the upstream SQL
  eligibility query (OUT, IR/PUP, inactive roster, unresolved identity, and missing
  active-roster evidence), not only rows that reach post-query candidate selection.
  - Acceptance: the downloadable audit reconciles DraftKings rows → ineligible →
    eligible → strategy-excluded → included without silent row loss.
  - Phase 2 progress: status, cutoff-safe injury, roster, and missing-roster
    decisions now occur in the explainable safety gate and remain in the audit.
    Unresolved salary rows are still blocked by the canonical salary query and
    must be reconciled from the unresolved identity queue to close this item.
- [ ] Add a UI exposure editor for player-specific minimum and maximum GPP exposure.
  The backend contract already accepts `minimum_exposure_by_player` and
  `maximum_exposure_by_player` keyed by canonical player ID and fails on unknown or
  conflicting IDs.
  - Acceptance: users can search canonical candidates, set percentages, see required
    lineup counts, and receive a clear infeasibility message before export.
- [ ] Expose allowed GPP stack templates in the UI instead of only the default
  `(1,0), (1,1), (2,0), (2,1)` portfolio cycle.
  - Acceptance: selected templates persist with the optimizer run and every lineup
    states which template it satisfied.
- [ ] Add explicit H2H alternate-lineup controls (minimum uniqueness or "next best"
  mode) so users can choose between near-identical optimal alternatives and broader
  contingency builds.
- [ ] Add focused API tests that reload both new strategies after process restart and
  verify objective/config, pool reasons, distribution summaries, and realized-stack
  explanations survive persistence unchanged.

## P2 — model and decision quality

- [ ] Replace projection-positive as the final H2H role proxy with source-backed
  route, snap, carry, target, and depth-chart evidence once those fields have stable
  prospective coverage. Keep the policy soft for legitimate cheap roles.
- [ ] Upgrade GPP from summed marginal player P90 to joint game/player simulations
  and expected top-percentile/payout optimization (`DT-503` through `DT-505`).
- [ ] Calibrate RB/DST and negative-correlation rewards from historical outcomes
  rather than retaining heuristic v1 bonuses.
- [ ] Add per-lineup objective attribution: mean, ceiling, correlation, leverage,
  value, and diversification contribution, plus the binding constraints.
- [ ] Add automated regression fixtures for known broad-pool examples such as
  Omarion Hampton, Brian Thomas Jr., Rome Odunze, and Dalton Kincaid. The assertion
  should verify eligibility/candidate policy, not force lineup selection.

## Current live acceptance evidence

- Projection: `d05884f8-934d-492f-9b2b-65914d97c6b8`
- H2H UI run: `d7f1ad0f-425e-4f92-b103-de6a33cb5a15`
  - Eligible: 373; included: 331; excluded: 42; completed six lineups.
- Large GPP UI run: `90355834-6940-475a-8008-d5aa52dee37f`
  - Eligible: 373; included: 136; excluded: 237; completed five lineups.
- Omarion Hampton, Brian Thomas Jr., Rome Odunze, and Dalton Kincaid were all
  available to H2H and were not manually forced into any lineup.
- Automated verification: all 493 backend tests, 52 focused backend tests, 14 UI
  tests, and the UI production build pass.
