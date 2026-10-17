# Predeclared retrospective quality screen ablation

This separate study reuses five W5 frozen historical pools and reconstructed current
scoring from showdown_fixed_pool_20261013. All outcomes have been inspected before;
there is no true blindness, held-out evidence, or prospective validation. No defaults,
production files, live data, candidate generator, projections or simulations change.
W4 Sunday night is excluded for unresolved original generation chronology.

Arms are exactly both95, mean95, marginal_p9095, neither. Both95 requires original
baseline mean and summed marginal player P90 >= 95% of their separate ORIGINAL
FULL-POOL maxima, with +1e-8 tolerance. Other arms remove only the named gate;
maxima are never recomputed after Captain eligibility. High marginal P90 sum is
not joint lineup P90. Candidate generation may itself have applied floors; this
study only measures downstream screening inside the saved pools.

All arms hold current role score (1.5*CPT P90 + FLEX means), current top-four
shortlist reconstructed with saved preferences, original legality and user
preferences, and requested-count integer exposure caps fixed. Preserve Captain
identity in canonical roster deduplication. Reuse prior outcome-independent variant
rule: largest saved baseline selector, then baseline scenario, scenario ID and rank.
Reproduce prior both95 current portfolio before alternatives. Primary comparison
uses original actual portfolio size: Thursday 4, other slates 5. Fail/report if any
arm cannot fill; do not relax constraints. Separate fill-capacity analysis uses
count-only solve <= original requested five, with caps still denominated on five;
no outcome comparison at changed sizes. Scores quantized at 1e-6 half-even; same
single-thread CBC seed0 and canonical lexicographic tie policy as prior harness.

Football annotations are generated and frozen before NEW outcome comparisons,
using only canonical-ID-linked original pregame player snapshots. Existing outcomes
were known; this procedural separation cannot restore genuine outcome blindness.
No new football penalties or eligibility rules are applied. All candidates receive:
- Captain role support: starting QB or saved centerpiece/primary/major secondary
  role supports plausible central upside; other/missing evidence remains unknown.
- Passing support: same-team QB with WR/TE Captain, receiver partners for QB
  Captain, each QB's receiver partners; absence is an unsupported passing stack,
  not proof of contradiction or automatic rejection. Record opposing bring-backs.
- Workload/TD competition: list same-team RB pairs and QB/RB co-occurrence;
  observed competition is a conditional dependency, not automatic contradiction.
  Target/carry/TD budgets and joint outcomes are unverified if missing.
- Salary saver opportunity: descriptive saver cutoff FLEX salary <=3000 (does
  not change exposure cheap-punt cutoff <=1000). Record projected targets/carries,
  lagged targets/carries/snaps, role/source/time and expected workload. Positive
  saved role/workload evidence supports participation; low/zero evidence is thin,
  not ineligible. Kicker/DST specialists are recorded separately. Null remains null.
- Game context: original total/spread/implied totals, source/time and point-in-time
  safety. Monday's user SHOOTOUT expectation is supplemental context, not a new
  generation treatment. Do not mix later Monday runs with original 9c07a5bd.

Report support in separate dimensions; no composite quality score or invented
carry/target/snap budgets. Pregame examples are chosen deterministically: top two
newly eligible rosters by current score then canonical signature for each arm,
plus all actually selected rosters. All candidate annotations remain available,
so examples do not silently imply all relaxed candidates have strong roles.

Evaluate unique coverage, quality vs Captain exclusions, new eligible roster counts,
maximum fill and unchanged integer caps; fixed-size actual average/best and original
contest thresholds. Keep missing cash evidence explicit. No pooled independent
lineup inference or generalization from five correlated pools. Bound Classic
applicability by source inspection only: no Classic expanded pools or simulations.

Freeze specification, prepared annotations, source/code hashes before evaluation.
Focused checks: boundary tolerance, gate decomposition, dedup/variant consistency,
prior baseline reproduction, exact shared preferences/caps, solver optimality,
fixed sizes, cap denominator, no outcomes in annotations, repeated stable bytes.
