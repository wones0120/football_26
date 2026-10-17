# Showdown lineup preferences

Named Captain position exceptions bypass only the position filter for the selected canonical players. Saved app and readable reports show **Named exceptions may qualify** and **1 if a named QB is eligible** when the saved position filter otherwise excludes QBs; explicit **No QBs** or **No QB Captain** still shows **No** and zero. The Captain position summary retains the base positions and named-exception count. This wording does not certify any named player's availability or override other eligibility rules.

## Four lineups at 25% captain coverage

A Showdown request with `num_lineups: 4` and `captain_max_exposure: 0.25`
(or `25`) activates captain coverage. After injury, player-pool and user
eligibility filtering, it freezes the top four eligible pregame P90 players,
including QBs unless excluded by a captain/player preference. In the UI, choose
**Any position** to remove the default WR/RB captain restriction.

Each shortlisted captain is solved once in P90 order, selecting the best legal
FLEX combination using the existing role objective and 1.5× captain salary and
points. Salary, roster size, team limits, locks, QB correlations, other hard
constraints and remaining portfolio exposure limits still apply. FLEX may use
the same players across lineups when exposure limits allow it. Existing behavior
is unchanged for other lineup counts or captain caps.

The global quality floors (85% of reference mean and 90% of reference P90) are
**diagnostic warnings only**. The reference is the best role-objective lineup
before fixing a captain or consuming portfolio exposure. The saved
`showdown_captain_coverage` report and exported HTML show each lineup's mean and
P90 projection gap (reference minus lineup), plus the amount below either floor.
A negative gap means the lineup is above the reference on that metric. These
summed player P90s are not calibrated lineup outcome percentiles.

A failed captain is never replaced by the fifth-ranked player. Generation
continues for the other shortlisted captains; the report records underfill and
the conflicting hard constraints, with canonical player IDs in constraint
expressions. Fewer than four eligible captains also produces explicit underfill.
A fixed captain lock is retained and reported as a conflict for other captains.
No constraint is relaxed to fill the request. Solver failures are distinguished
from proven infeasibility. Reports remain available when no lineup is feasible.

## Top-four P90 captain shortlist

Captain candidates are the top four eligible players across both teams ranked by
unmultiplied pregame `p90`, descending, then canonical `player_id` ascending.
Captain-only preferences (position limits, No QB Captain, and FLEX-only players)
apply before ranking. Existing player-pool eligibility checks still apply.
With fewer than four eligible players, all qualify; an empty shortlist is
infeasible. A locked captain outside the shortlist is rejected explicitly.

Final validation independently checks each selected captain against the frozen shortlist before accepting results.

The shortlist is frozen before candidate generation. Exposure exhaustion,
scenario discovery and forced-captain solves cannot promote a fifth player.
Players outside the shortlist remain available at FLEX under the existing pool
and roster rules. Model projections, ownership and football assessments are
unchanged by preferences or the cutoff.

The solve objective is exactly **1.5 × captain pregame P90 + sum of FLEX means**.
Captain salary is **1.5 × base salary**; FLEX salary is unchanged. Existing
salary cap, one captain plus five FLEX, unique-player, team, user and portfolio
constraints remain in effect. Legacy captain-prior, context, correlation and
ownership adjustments do not enter this solve objective. Final single-lineup
ranking uses the same role-specific score; existing multi-entry portfolio
constraints and diversification policies remain in effect. This score is not
a calibrated lineup P90 or payout forecast.

Saved runtime and lineup metadata contain `showdown_captain_shortlist`, including
raw P90, model rank, eligible rank, the shortlist and captain-only exclusions.
The exported optimizer report displays these details. `outside_top_four_p90`
is an `optimizer_policy` reason; user restrictions remain `user_preference`
reasons, with model values retained. Missing/nonfinite P90 cannot qualify for
captain and is reported explicitly; it does not itself remove FLEX eligibility.


Operations → Portfolio optimizer shows the full **Optimizer options** form without
expanding a disclosure. Preparation and data tools (including Open Model and Run
Simulation) and Weekly pipeline remain collapsed by default.

In Showdown, the following independent checkboxes are available for Cash and every
GPP strategy. All default off and can be used together:

- **No QB Captain**: no player with natural position QB may occupy CPT. QBs remain
  eligible at FLEX, subject to existing starter and lineup eligibility rules.
- **No 2 QBs in the lineup**: at most one player with natural position QB may appear
  across CPT and FLEX. Existing strategy requirements for a starting QB still apply.
- **No QBs in the lineup**: zero QBs across Captain and FLEX. Takes precedence over
  the other QB options. Overrides the starting-QB requirement and hard QB-dependent
  stack/Captain construction requirements; WR/TE Captains and multiple pass catchers
  remain allowed. Scored football/correlation assessments remain unchanged.
  Team limits, salary, physical uniqueness, quality and exposure caps still apply.

**Captain position** applies to Cash and every Showdown GPP strategy:

- **WR/RB only (default)** permits WR or RB at Captain.
- **Any position** adds no position restriction.
- **WR/RB/TE only** permits any of those three positions at Captain.
- **WR only**, **RB only** or **TE only** requires that position at Captain in
  every generated lineup.

Other positions remain eligible at FLEX, subject to existing lineup preferences.
Direct and weekly requests submit `captain_positions`, a list containing WR, RB
and/or TE; an empty or omitted list is unrestricted. The API rejects unsupported
positions and enabled Classic restrictions. Incompatible locked Captains return
an explicit error. Candidate solves and independent final validation enforce the
restriction alongside all existing quality, exposure, salary and team limits.
Infeasible requests can underfill or fail; the optimizer never substitutes an
unrequested Captain position.

Saved runtime and lineup metadata include `showdown_captain_preferences`.
Captain-ineligible pool rows retain their model assessment and the
`user_captain_positions` preference reason while remaining FLEX eligible.
Result and exported reports show the saved choice and effective QB-Captain
eligibility. Projections, ownership and football context remain unchanged.

**Max players per team** is a separate dropdown for Cash and every GPP strategy:

- **4 — allows 4–2 and 3–3 (default)** prevents five players from either team.
- **3 — requires 3–3** forces an even split.
- **5 — allows 5–1** is available as an override.

Captain counts as one player together with the five FLEX players. Direct and weekly
runs submit `max_players_per_team`; the API accepts integers 3, 4 or 5. Omitted
values use 5. Conflicting team locks return an explicit error. Every candidate solve
and final validation enforce the limit; it does not alter football assessments.
Saved runtime and lineup metadata include `showdown_team_constraints`, the reason
`user_max_players_per_team`, and allowed splits. Result and exported reports show
the saved limit, independently of the current dropdown selection.

Reports distinguish requested-count cap compliance from final realized exposure.
An underfilled portfolio warns when its realized exposure exceeds the configured
percentage even though its requested-count appearance cap passed. Cap semantics
remain unchanged: appearance limits round up using the requested entry count.

The frozen QB/team-cap experiment, full-universe feasibility certificates and
comparisons are documented in
[Showdown controlled experiment](../SHOWDOWN_QB_POLICY_CONTROLLED_EXPERIMENT.md).

Direct optimizer runs and weekly runs submit boolean `no_qb_captain` and
`no_two_qbs` and `no_qbs` parameters. Enabled constraints require Showdown; non-boolean values
are rejected. A locked QB Captain conflicts with the first option, and locking
multiple QBs conflicts with the second. These conflicts return explicit errors.
Any locked QB (including Captain) conflicts with **No QBs in the lineup**.

The solver enforces the constraints before candidate selection, and final lineup
validation checks them independently. With the second option, five-lineup portfolio
shootout targets that require both QBs are replaced with best-available discovery
under the requested constraints. Existing quality and exposure limits still apply;
infeasible requests may produce fewer lineups or fail.

These preferences never change projections, ownership, football context, or model
assessments. Saved run parameters and `strategy_runtime.showdown_qb_preferences`
record all choices, effective QB limits, overridden construction requirements,
user preference reason codes and excluded script targets.
Generated lineup rows retain a preference report; QB pool rows retain their model
assessment and the Captain-only user exclusion reason while remaining FLEX eligible.
The result view displays active preferences and their Captain exclusions.
With **No QBs in the lineup**, QB audit rows are marked excluded by user preference
with reason `user_no_qbs`, retaining their projections and model assessment.

## Captain app defaults

New sessions require at least one season-average non-QB team leader at Captain or FLEX.
Home-team-only remains off. Leaders use each team's highest season DK points per participating game through the prior week
among RB/WR/TE/K before user exclusions. No current-week outcomes enter this average.
The team cap defaults to four, allowing 4–2 and 3–3. Old saved five-player caps migrate
to four once; later explicit overrides persist, and existing three-player caps remain.
Omitted API parameters and saved historical runs retain their existing semantics.

Captain team-leader preferences now use prior-week season averages instead of projections. Require at least one defaults on; home-team-only defaults off. The leader may be Captain or FLEX. Missing/ambiguous history remains unranked; missing team history or Week 1 fails explicitly without falling back to projections. Frozen run metadata records prior-game scores, averages, source lineage and tied leader IDs. Existing historical runs are unchanged.

After optimizer changes, restart both local API and durable worker before rerunning. Fresh preparation remains required; ESPN provider ID 100 accepts the display names DraftKings and Draft Kings without relaxing line validation.
