# Showdown lineup preferences

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
