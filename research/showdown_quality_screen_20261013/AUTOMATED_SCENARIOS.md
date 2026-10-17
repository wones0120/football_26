# Proposed prospective test: infer football scenarios automatically

This is a design proposal responding to user steering after the main study freeze.
It changes no experiment treatment, application defaults, model forecast or data.

The workflow should infer plausible football stories from point-in-time data and
AI, with no required per-game user input. Sunday Main Classic needs slate-wide
automatic prioritization; Showdown can optionally accept a user view such as
SHOOTOUT. An optional view is a scenario preference, not a new projection truth.

Separate three layers before strategic quality selection:
1. Mathematical validity: canonical identity, format roles, salary, team/roster
   restrictions and explicitly saved user constraints.
2. Evidence reliability: cutoff-safe source timestamps, availability, expected
   role, lagged participation, workload uncertainty, projections and market context.
3. Football scenario construction: automatically infer pass-led, balanced,
   run-control, comeback and low-scoring possibilities only where data support
   them. AI can organize and explain these hypotheses; attach canonical player
   IDs, source identifiers, evidence timestamps, confidence and unknowns to each.
   Preserve alternatives and contradictory evidence. No fabricated targets,
   carries, snap shares or joint TD budgets; no invented narrative score bonuses.

Then expose how strategic 95% mean/marginal-P90 screening changes each supported
scenario's coverage. A narrative is not a joint probability model. To claim joint
upside requires a separately validated joint model or simulator with observed
role/usage budgets and dependency evidence. Summed individual P90 is insufficient.
Scenario labels and prose must not certify independent evidence or calibrate
portfolio risk merely by sounding plausible.

Existing frozen W5 Showdown evidence supports automated initial hypotheses:
original total/spread/implied scores with source/time, canonical Captain roles,
starting-QB status, lagged snaps/targets/carries, projected opportunity where
present, same-team QB/receiver partners and opposing bring-backs. Monday's original
54.5 total and 29/25.5 implied scores support considering two-sided scoring, with
Cook/Allen TD competition and modest supporting-player roles marked explicitly.
Actual expected targets/carries/routes/snaps and joint TD budgets often remain
null. Backups may participate; low observed opportunity is not ineligibility.

For Classic, aggregate these data across the slate, identify high-supported
passing environments, role-driven alternatives and salary tradeoffs, and output
a manageable ranked set of candidate hypotheses with evidence/unknowns. Rank by
a predeclared data policy; use AI explanations without arbitrary added optimizer
bonuses. Do not ask the user to label every game. This study cannot validate the
Classic hypothesis engine: its saved Classic pools have no expanded candidate
coverage and the Showdown selection screen is a separate code path.

A prospective test should freeze the automatic hypothesis engine version, source
cutoffs, candidate generator, scenario provenance, user overrides (if any), pool,
scoring, preferences, caps and primary portfolio size before kickoff. Compare
screen arms within the same pool; compare scenario-first candidate generation in
an explicitly separate experiment with pool changes recorded. Evaluate evidence
coverage and saver-role unknowns before outcomes, then actual contest attainment,
calibration and fill after outcomes on genuinely uninspected slates. Defaults stay
unchanged until evidence supports a reviewable policy change.
