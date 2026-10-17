# Frozen retrospective fixed-candidate-pool experiment

This specification is saved and hashed before alternative selections are evaluated
against outcomes. All six named slates were inspected previously. No held-out claim.

1. First verify saved candidate hashes, dual 95% eligibility, exposure budgets,
   maximum cardinality, historical objective optimum and persisted physical rosters.
   Tied historical variants may differ; physical roster/objective discrepancies must
   be disclosed and investigated before outcomes. Historical reference is the saved
   portfolio, not a reselected portfolio under new Captain eligibility.
2. Deduplicate using (canonical Captain ID, sorted six canonical player IDs).
   Select the variant with largest recorded baseline selector; equal scores prefer
   baseline, then scenario ID and recorded rank. Require identical baseline mean,
   marginal P90 sum and salary across variants. Never use actuals to choose a variant.
3. Reconstruct current scoring exactly as 1.5 * Captain base P90 + sum(FLEX base
   means). No Captain prior, ownership, leverage, context or correlation contributions.
   Current top-four Captain eligibility uses every historically included player,
   historical pregame P90, saved Captain preferences/FLEX-only exclusions, and
   canonical-ID tiebreak. Missing reconstructable evidence blocks that slate.
4. Every comparison arm uses the same distinct canonical rosters, current Captain
   eligibility, historical user/model eligibility and historical player/Captain caps.
   Retain the ORIGINAL dual thresholds: 95% of separate full original-pool maxima.
   Do not recompute thresholds after Captain filtering. No quality-screen ablation.
   Retain historical generation legality; verify explicit saved player/role/team
   preferences. No candidate regeneration, new projections, simulations or latest data.
5. Establish maximum common feasible size with a count-only ILP BEFORE outcomes.
   All arms must choose exactly that size. Caps use original requested count (five),
   including Thursday underfill; do not retighten to realized size. Empty feasible
   portfolios are reported, not relaxed. No extra overlap/diversity constraints.
6. Arms: current role-specific score, total projected mean with CPT multiplied 1.5,
   summed marginal player P90 with CPT multiplied 1.5. Maximize portfolio sum.
   Quantize scores to nearest 1e-6 (Decimal half-even), maximize integer total, then
   prefer lexicographically earliest canonical rosters among tied optimal portfolios.
   Single-thread CBC with randomSeed 0. Save chosen IDs and verify constraint parity.
7. Freeze specification, prepared inputs and research/code hashes before separately
   capturing/evaluating outcomes. Canonical actuals require resolved IDs and agreement
   across contests; undo CPT multiplication before applying it once to each roster.
   Never impute missing/conflicting scores. Use report's frozen field thresholds.
8. Per slate: average actual, best actual, and number reaching each contest threshold.
   Show contest-specific thresholds separately; no repeated-contest weighting or pooled
   lineup correlations. Use one slate observation for comparisons. Pool-best actual is
   a hindsight coverage diagnostic, not an achievable benchmark. Entry choice remains
   separate. Report deduplicated within-slate historical metric correlations.
9. Exclude W4 Sunday night from chronological validation unless explicitly zoned
   original pregame generation evidence is established. Reproduce its historical saved
   portfolio descriptively but do not evaluate alternatives without that evidence.
   No uninspected slate has been designated; no held-out or future-improvement claims.
10. Exact contemporaneous historical optimizer executable/version attestation is
    absent. Stored scoring inputs, coefficients, library labels and full selectors
    support selection replay. Aggregate historical reconstruction explicitly undoes
    the summary-only QB scaling of positive count-construction terms, verified
    against every saved selector. Raw per-candidate trigger breakdown is absent.
    This experiment does not validate today's generator or production defaults.
