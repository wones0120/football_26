# Showdown Captain Credibility Gate

Task: `OPT-CCG-001` · Priority: P1 · Status: Research

Added: 2026-10-01. This document specifies future research; no gate has been
validated, selected, implemented, or promoted to production.

## Core principle and scope

> A player cannot become Captain merely because his cheap CPT salary makes the
> other five FLEX positions stronger. Before lineup construction, the player must
> independently qualify as a credible candidate to be one of the highest-scoring
> players in the game.

Research only. Use frozen pregame PIT–CLE evidence and every trustworthy historical
Showdown slate with reconstructable pre-lock inputs. **Do not use tonight's PIT–CLE
realized results, including receiving results, to define, tune, or explain the
rule.** Do not change production code, defaults, projections, priors, weights,
ownership policy, or saved runs as part of this task.

Dependencies: verified pre-lock provenance, canonical player identities, historical
salary/slot contracts, reproducible candidate construction and portfolio selection,
and historical actuals isolated from pregame feature preparation. Missing evidence
must be reported; research proceeds on the trustworthy subset.

## 1. Separate CPT eligibility from lineup optimization

Desired decision order:

`PLAYER IS CREDIBLE CPT -> CPT CANDIDATE POOL -> BUILD BEST LINEUPS AROUND THOSE CPTS -> PORTFOLIO SELECTION`

The concern to investigate is the reverse order:

`CHEAP CPT CREATES GREAT SIX-MAN LINEUP -> THEREFORE CHEAP PLAYER BECOMES CPT`

- [ ] Specify a player-level credibility decision before salary construction around
  that player, with versioned evidence, pass/fail/insufficient-evidence status, and
  an explicit reason for each candidate.
- [ ] Preserve every player's model assessment. CPT exclusion does not imply FLEX
  exclusion or change forecasts. Keep user-preference exclusions separately labeled.
- [ ] Define research behavior when too few credible CPTs remain: retain the
  qualified families and report unmet diversity preferences rather than silently
  relax the gate. See section 9.

## 2. Define credible Captain evidence

- [ ] Inventory each feature's existing source, definition, units, cutoff, lineage,
  and coverage. Do not invent unavailable features or treat missing values as zero.
- [ ] Examine player projected mean, projected P90/ceiling, slate mean and P90 ranks,
  and slate mean and P90 percentiles.
- [ ] Examine expected targets, carries, QB pass attempts, recent opportunities,
  snap/route confidence, role confidence, team implied scoring, starting status,
  and injury/availability confidence. Include TD/scoring access only where supported
  by existing data.
- [ ] Examine historical CPT-position priors and individual best forced-CPT lineup
  quality. Compute historical priors from strictly earlier development data.
- [ ] For QBs also examine rushing attempts, rushing yards, mobile/pocket archetype,
  and salary opportunity cost, using supported pregame evidence.

Define the slate population, tie handling, rank direction, and percentile convention
before comparisons. Keep opportunity ranks position-aware where units differ;
targets, carries, and pass attempts are not interchangeable workloads.

Individual CPT frontier quality includes teammates and salary construction. Report
it separately from the player's own scoring credibility, and test whether its
apparent signal is explained by FLEX salary unlock. Salary opportunity cost and
lineup quality cannot independently create eligibility.

## 3. Determine long-shot exclusion historically

Do not impose an arbitrary rule such as “top five projection only.” Predeclare a
transparent development search over these candidate gates:

| Gate | Research candidate |
| --- | --- |
| A | Minimum P90 percentile. |
| B | Minimum mean OR P90 percentile. |
| C | Minimum individual CPT quality percentile; explicitly audit salary-unlock dependence and require independent player credibility. |
| D | Minimum opportunity/role confidence plus a ceiling requirement. |
| E | Position-aware thresholds with disclosed sample support. |
| F | Probability/ranking model trained only on pre-lock features and earlier labels. |
| G | Credible ceiling AND credible opportunity AND supported role. |

- [ ] Compare each gate with the unchanged, ungated candidate pool.
- [ ] Determine whether combinations identify players whose optimal-CPT chance is
  too remote to justify inclusion, while prioritizing retention of legitimate
  optimal CPTs. Declare the development selection criterion before holdout access.
- [ ] Report uncertainty and sample sizes. A removed candidate is not automatically
  a proven long shot; distinguish exclusions from supported long-shot findings.

## 4. Retain cheap but credible CPTs

Cheap does not mean bad. A low-priced WR/RB/TE can qualify through his own realistic
path to a top fantasy score. Distinguish `CHEAP BUT CREDIBLE CPT` from
`CHEAP LONG-SHOT CPT WHO ONLY LOOKS GOOD BECAUSE OF FLEX SALARY UNLOCK`.

- [ ] Report retained and excluded candidates by salary and position, with evidence
  explaining credible low-salary cases.
- [ ] Verify that improving the other five FLEX positions alone cannot turn an
  otherwise unsupported candidate into an eligible Captain.

Salary efficiency can improve lineup construction **after** eligibility.

## 5. Measure salary-unlock effect

- [ ] For every CPT, construct comparable research-only forced-CPT frontiers under
  identical inputs, salary cap, legality, scoring, and candidate-discovery scope.
- [ ] Record CPT-adjusted mean and P90, CPT player mean/P90 ranks, total lineup
  mean/P90, five-FLEX mean/P90, CPT salary, salary remaining for FLEX, and incremental
  FLEX quality versus stronger alternative CPTs.
- [ ] Define and report these diagnostics:

| Diagnostic | Required definition/interpretation |
| --- | --- |
| `captain_mean_share` | CPT-adjusted mean divided by total lineup mean; unavailable for an invalid denominator. |
| `captain_p90_share` | CPT-adjusted marginal P90 divided by summed lineup marginal P90; label this as a marginal-ceiling share. |
| `captain_mean_rank` | Player mean rank in the declared slate population. |
| `captain_p90_rank` | Player P90 rank in the same population. |
| `captain_opportunity_rank` | Rank under the declared, supported opportunity definition. |
| `captain_role_confidence` | Sourced role confidence with provenance and missingness. |
| `flex_quality_unlocked_by_cpt_salary` | Five-FLEX quality difference versus named stronger alternative CPTs, alongside salary differences. |
| `captain_quality_vs_flex_quality` | Separate CPT and five-FLEX contributions on the same scoring scale. |
| `salary_unlock_dependency` | Predeclared attribution from matched comparisons/ablations showing how much lineup advantage depends on FLEX improvement despite weaker CPT scoring evidence. |

Use the site's verified Captain scoring/salary multiplier. Distinguish summed
marginal P90 from a simulated joint lineup P90; a sum of player P90s is not a lineup
or portfolio percentile. If joint draws exist, preserve correlation assumptions
and seeds. Do not fabricate a joint percentile from marginal values.

Identify high-quality lineups driven primarily by a cheap CPT's FLEX group. Matched
comparisons must disclose changed teammates and construction constraints; salary
differences alone are not proof of causality.

## 6. Historical validation

- [ ] Inventory every candidate historical slate and record inclusion/exclusion
  reasons. Verify pre-lock salaries, projections, role evidence, source observation
  times, code/model provenance, and player/slot identity. Present-day reconstruction
  alone does not establish historical information availability or leakage safety.
- [ ] Join by `player_master_id` and verified source aliases/IDs, never raw display
  name alone. Quarantine unresolved identity or unproven provenance.
- [ ] Split development and chronological holdout where feasible. Fit models,
  thresholds, normalization, and priors on earlier data only; do not optimize on
  holdout. If trustworthy coverage is insufficient, report that limitation.
- [ ] Freeze each slate's features, gate decisions, configuration, code version,
  hashes, and seeds **before** joining actuals or identifying actual optimal CPTs.
- [ ] Then compute legal actual-optimal lineups under historical salaries and roster
  rules, preserving tied optimal CPTs. Report both any-optimal-CPT retention and
  all-optimal-CPT retention so ties cannot conceal false exclusions.
- [ ] Measure optimal-CPT pass rate, false exclusions, supported long shots removed,
  candidate-pool reduction, position/salary distributions, projection rank, P90
  rank, and opportunity rank. Show counts and denominators by split and gate.
- [ ] Inspect every false exclusion, especially legitimate low-salary CPTs. Report
  uncertainty and changes in portfolio feasibility alongside aggregate metrics.

Distinguish individual top-scorer plausibility from salary-constrained actual
optimal-CPT membership. Evaluate both concepts without allowing the latter's salary
advantage to replace independent pregame credibility.

## 7. PIT–CLE pregame replay and third-CPT attribution

Starting references, subject to provenance verification:

- [Final-lock report](WEEK4_THURSDAY_SHOWDOWN_FINAL_LOCK.md).
- [Frozen final inputs](artifacts/week4_thursday_showdown_final_lock/20261001T225120Z/final_inputs.json).
- [Frozen common universe](artifacts/week4_thursday_showdown_final_lock/20261001T225120Z/final_common_universe.json).
- [Saved A–E decisions](artifacts/week4_thursday_showdown_final_lock/20261001T225120Z/decision.json).
- [Production/research parity audit](WEEK4_SHOWDOWN_PRODUCTION_RESEARCH_PARITY.md).

Use only the frozen pregame inputs. Verify each referenced source's actual
observation cutoff; report-writing time is not evidence of pre-lock availability.
Do not refresh inputs or mix morning, afternoon, and final-lock bundles silently.

- [ ] Compare DK Metcalf, Deshaun Watson, Denzel Boston, Jaylen Warren, Quinshon
  Judkins, Jerry Jeudy, Aaron Rodgers, and every other viable CPT in that universe.
- [ ] For each show mean rank, P90 rank, opportunity/role rank, individual CPT
  frontier score, CPT salary, five-FLEX quality unlocked, and pass/fail/missing
  evidence under every proposed gate. Include canonical IDs in the outputs.
- [ ] Reproduce the saved third-CPT selection before attributing it. Answer:
  **Why did Jerry Jeudy become the third CPT?** Separate individual player quality,
  salary savings, FLEX quality unlocked, thesis diversity, overlap constraints,
  and Captain uniqueness through controlled comparisons and constraint ablations.
- [ ] Compare Jeudy CPT directly with Boston CPT under identical portfolio
  requirements, the same frozen universe and scoring, and equal discovery effort.
  Report best feasible portfolios, quality differences, changed rosters, and
  binding constraints; do not compare one player's unconstrained best lineup with
  another player's constrained selection.

No conclusion about Jeudy's credibility or selection cause is established by this
task document. Do not use tonight's receiving or fantasy results in this replay.

## 8. Test a two-stage CPT architecture

Shadow-test the eligibility/construction separation followed by portfolio selection:

1. **Stage 1 — CPT credibility:** generate an eligible CPT pool using only
   player-level pregame evidence.
2. **Stage 2 — lineup construction:** generate broad lineup families only for
   credible CPTs.
3. **Stage 3 — portfolio solve:** choose the best set from that CPT-qualified universe.

- [ ] Compare with the current architecture on identical frozen inputs and the
  same scoring, discovery effort, and portfolio settings except for the explicitly
  tested credibility gate and handling of unmet diversity preferences.
- [ ] Measure optimal-CPT historical recall, candidate count, portfolio selector,
  portfolio mean, portfolio P90, CPT diversity, thesis diversity, overlap, and salary
  usage. Label marginal-ceiling sums separately when joint portfolio P90 is unavailable.
- [ ] Freeze the shadow configurations and eligibility decisions before historical
  actuals are exposed. Preserve the unchanged control and disclose feasibility limits.

## 9. Portfolio diversity cannot create a long-shot CPT

Three distinct captains remains a **preference, not an absolute requirement**.
If only two players independently qualify, return two strong CPT families rather
than force a third long-shot Captain. This does not by itself prescribe two entries;
report entry count and distinct-CPT count separately.

- [ ] Permit the shadow portfolio solver to choose only among credible CPTs.
- [ ] Verify that CPT diversity, thesis diversity, overlap, and salary fit cannot
  promote an otherwise ineligible CPT.
- [ ] Report any unmet preference or infeasible hard construction constraint
  explicitly, retaining the eligible candidate pool and its evidence.

## 10. Shadow output for future optimizer reports

Specify research-only diagnostic output for each CPT; production report integration
remains a separate future task:

- `credible_captain = true/false`
- credibility reason
- mean percentile
- P90 percentile
- opportunity percentile
- role-confidence result
- salary-unlock dependency
- individual CPT quality
- historical gate evidence

Use explicit field definitions, gate version, canonical player ID, source references,
and evidence coverage. Preserve an insufficient-evidence status alongside the boolean
decision when needed; do not mislabel missing evidence as a measured long-shot result.

For a candidate rejected as a long shot, report:

`Excluded from CPT pool: long-shot captain under pregame credibility gate`

The player may remain fully eligible at FLEX. Preserve the model assessment and
distinguish credibility exclusions from user preferences and availability restrictions.

## 11. No production change yet

Historical and shadow validation come first. Do not change CPT weights, selector
weights, correlation, projections, ownership, exposure rules, scenario assumptions,
research portfolio policy, or the Classic optimizer. Preserve the current control
policy; evaluate the proposed architecture and diversity handling only as explicitly
versioned shadow alternatives. Any promotion requires a separate task and decision.

## 12. Required final answers in the research report

End the eventual research report with the following questions and answer formats.
These answers are pending research; do not infer them from tonight's results.

### Can the current optimizer promote a long-shot CPT because of salary unlock?

YES / NO / BORDERLINE

### Was Jerry Jeudy individually a credible CPT from the frozen pregame evidence?

YES / NO / BORDERLINE

### Was Denzel Boston individually a stronger pregame CPT candidate than Jeudy?

YES / NO / BORDERLINE

### How much of Jeudy's portfolio selection came from salary unlock versus player quality?

Report the controlled attribution, interactions, and any limits to quantifying it.

### What pregame signals best distinguish credible CPTs from long shots?

Report supported evidence and missing-feature limitations.

### What proposed credibility gate has the best historical holdout behavior?

Report the development-selected gate's untouched holdout behavior; do not select or
retune a gate using holdout results. State when trustworthy holdout evidence is insufficient.

### How many historically optimal CPTs would that gate incorrectly exclude?

Report counts, denominators, ties, splits, and the excluded candidates.

### Does the gate still allow legitimate cheap CPTs?

YES / NO

### Should CPT eligibility be determined before lineup construction?

YES / NO

### Should three-distinct-CPT portfolio logic ever override the credibility gate?

NO unless historical evidence clearly supports otherwise. An evidence-based proposal
to change this principle must be explicit and cannot authorize a production override.

### Production recommendation

PROMOTE / SHADOW LONGER / DO NOT USE

**Captain first has to be a credible top scorer. Only then may salary efficiency,
lineup construction, thesis diversity and portfolio optimization determine which
credible captain we use.**

## Deliverables and acceptance

- [ ] Feature/provenance inventory and trustworthy-slate inclusion ledger.
- [ ] Versioned research gate definitions and frozen per-player decisions.
- [ ] Salary-unlock diagnostics and historical development/holdout comparison,
  including every false exclusion and low-salary retention analysis.
- [ ] Frozen PIT–CLE candidate table, Jeudy selection attribution, and controlled
  Jeudy-versus-Boston portfolio comparison.
- [ ] Current-versus-staged architecture comparison, diversity-preference handling,
  and per-CPT shadow report diagnostics.
- [ ] Reproducible artifact manifest, configuration, code hashes, seeds, and checks
  proving post-lock evidence cannot enter candidate decisions.
- [ ] Recommendation to continue, reject, or pursue a separate promotion task,
  with all section 12 answers, evidence limits, and no automatic production change.

Acceptance requires auditable pregame-only decisions, transparent exclusion reasons,
reported optimal-CPT retention and false exclusions, preserved cheap-but-credible
candidates, and an independently evidenced separation between Captain credibility
and FLEX salary unlock. Research results and numerical thresholds remain pending.
