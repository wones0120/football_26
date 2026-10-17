# Shared-opportunity construction review — evidence-first checkpoint

Recorded 2026-10-16T14:33:44.148591+00:00. **Recommendation: keep the prototype inactive. No production objective, model, projection, current setting or entry was changed.**

## What the audit found

Exact highest-baseline-mean selection correctly sums individual means: expectation is additive even when outcomes are dependent. Its objective and optional-stack contract must remain intact. Summing individual player P90 values is not a lineup P90. Existing Analyst generation does condition means/spreads on sourced team opportunities, but then adds mean +0.35×individual spread; its shared outcome design is not a fitted joint scoring distribution. Existing possession/play research pairs passing/receiving events and conserves touchdowns, but is explicitly offline and uses unfitted efficiency/pace assumptions. It is not validated for immediate production ranking.

## Why the isolated prototype is not ready

The opt-in prototype tested a complete legal roster under each existing scenario, allowing upside credit to compete for normalized team targets/carries. No teammate-count penalty, total threshold or new same-team restriction was added. QB passing and receiver targets share one physical event; Captain affects fantasy scoring only. Source opportunity budgets and missing measurements are retained. It uses unit-elastic touch demand as a deterministic sensitivity, with no calibrated probability claim.

**The key validation failed:** in three treatment rosters Henry is the sole BAL player yet only about76–82% of his individual-tail credit is retained. Taylor/Hubbard are also clipped alone in another roster. A high-usage RB can reach a real fantasy ceiling through touchdowns or efficiency without proportional touches. The proxy therefore conflates marginal scoring behavior with teammate competition. Conservation alone does not establish a coherent joint fantasy distribution. Lower summed mean or changed rosters do not show improved probability of lineup success. This behavior is not recommended for activation.

Production `run_merged` rejects an enabled prototype parameter unless a research-only internal keyword is passed. No API route supplies that keyword. The UI control is disabled and labeled inactive pending evidence review. No restart or live optimizer run was requested for this prototype. Existing forecasts and exact-mean mode remain unchanged.

## Matched Sunday generation experiment

Both arms use the same513-row frozen source (projection b2ae485d-f436-470b-a52c-fa53095bbd4d; cutoff **October15 19:17UTC**), same packet, prior-week rank eligibility, source exclusions, scenario priorities, seed7, solver configuration and user settings. Five requested, five achieved, no relaxation. User controls:80% exposure, team3/game4, top50% prior-week QB/RB/WR/TE rank, QB/RB $4500 minimum, Q exclusion, singleTE, no offense against DST, DEN-opponent exclusion, no locks, favored-position requirements off. Internal existing Analyst story/dependence constraints are retained, not introduced as this treatment.

These are separate generated candidate pools because only the objective treatment changes. This is a generation experiment, not a frozen-pool selector comparison, outcome validation or final-entry recommendation. Current normal preparation is blocked by missing/stale current player evidence; no healthy/unknown fallback is created. The original saved highest-mean f84e75db… uses older one-lineup controls (including four Rams) and is preserved as background, not presented as the matched control.

The frozen source still records Flowers ACT; the later native Tiers file records Q. Treatment slot5 below therefore also needs current Q eligibility review before any use. Neither arm is represented as a current injury-cleared portfolio.

| Slot / primary success path | Control mean | Prototype mean | Salary control / prototype | Roster changed |
|---|---:|---:|---:|---|
| 1: Carolina productive passing | 128.85 | 128.85 | $50,000 / $50,000 | No |
| 2: Baltimore run control | 131.60 | 130.99 | $50,000 / $50,000 | Yes |
| 3: Pittsburgh productive passing | 127.34 | 127.34 | $50,000 / $50,000 | No |
| 4: Arizona passing response | 123.67 | 122.88 | $50,000 / $50,000 | Yes |
| 5: Indianapolis rushing control | 122.31 | 121.37 | $50,000 / $49,900 | Yes |

Average means 126.7545 → 126.2887 (-0.4659). Two slots unchanged, three changed; all ten generated rosters are canonically distinct within their respective portfolios.

## Full rosters and constructive success cases

### 1. Carolina productive passing

Bryce Young/Coker connect repeatedly while Kyren/Puka access a productive Rams offense; Henry supplies independent Baltimore scoring. Countercase: Carolina can lead against backup McKee and require fewer passes, or protection/efficiency can fail. The full lineup still needs Otton/Tate/Odunze roles to produce at their salaries.

| Role | Control player | Salary | Mean | Prototype player | Salary | Mean |
|---|---|---:|---:|---|---:|---:|
| TE / TE | Cade Otton | $3,300 | 8.40 | Cade Otton | $3,300 | 8.40 |
| DST / DST | Chargers | $2,100 | 3.95 | Chargers | $2,100 | 3.95 |
| WR / WR | Jalen Coker | $5,900 | 12.78 | Jalen Coker | $5,900 | 12.78 |
| RB / RB | Kyren Williams | $6,800 | 19.78 | Kyren Williams | $6,800 | 19.78 |
| RB / RB | Derrick Henry | $8,200 | 18.81 | Derrick Henry | $8,200 | 18.81 |
| QB / QB | Bryce Young | $5,700 | 20.57 | Bryce Young | $5,700 | 20.57 |
| WR / WR | Puka Nacua | $8,100 | 21.81 | Puka Nacua | $8,100 | 21.81 |
| WR / WR | Carnell Tate | $5,000 | 11.20 | Carnell Tate | $5,000 | 11.20 |
| WR / WR | Rome Odunze | $4,900 | 11.53 | Rome Odunze | $4,900 | 11.53 |

### 2. Baltimore run control

Henry benefits from sustained Ravens rushing/goal-line opportunities; the Las Vegas QB choice needs Buffalo to sustain two-sided offense. Puka/Kyren can both benefit from Rams drives but compete for finishing touchdowns. Prototype reinvests Hubbard/Wan’Dale/DST salary into Irving/Tate/DST; this is a full-roster tradeoff, not proof one TEN receiver is preferable.

| Role | Control player | Salary | Mean | Prototype player | Salary | Mean |
|---|---|---:|---:|---|---:|---:|
| RB / TE | Chuba Hubbard | $6,300 | 14.57 | Cade Otton | $3,300 | 8.40 |
| TE / DST | Cade Otton | $3,300 | 8.40 | Chargers | $2,100 | 3.95 |
| RB / RB | Kyren Williams | $6,800 | 19.78 | Kyren Williams | $6,800 | 19.78 |
| QB / QB | Kirk Cousins | $5,400 | 21.76 | Kirk Cousins | $5,400 | 21.76 |
| RB / RB | Derrick Henry | $8,200 | 18.81 | Derrick Henry | $8,200 | 18.81 |
| DST / WR | Panthers | $2,500 | 4.61 | Puka Nacua | $8,100 | 21.81 |
| WR / RB | Puka Nacua | $8,100 | 21.81 | Bucky Irving | $6,200 | 13.74 |
| WR / WR | Wan'Dale Robinson | $4,500 | 10.32 | Carnell Tate | $5,000 | 11.20 |
| WR / WR | Rome Odunze | $4,900 | 11.53 | Rome Odunze | $4,900 | 11.53 |

### 3. Pittsburgh productive passing

Rodgers and Metcalf share passing-yard/TD events; Otton is an opposing response with a different team target budget. Kyren/Puka add Rams drive exposure. Countercase: Pittsburgh finishes through the run or injury support fails to produce efficient passing. Both arms keep this roster.

| Role | Control player | Salary | Mean | Prototype player | Salary | Mean |
|---|---|---:|---:|---|---:|---:|
| TE / TE | Cade Otton | $3,300 | 8.40 | Cade Otton | $3,300 | 8.40 |
| RB / RB | Kyren Williams | $6,800 | 19.78 | Kyren Williams | $6,800 | 19.78 |
| RB / RB | Derrick Henry | $8,200 | 18.81 | Derrick Henry | $8,200 | 18.81 |
| DST / DST | Panthers | $2,500 | 4.61 | Panthers | $2,500 | 4.61 |
| WR / WR | Puka Nacua | $8,100 | 21.81 | Puka Nacua | $8,100 | 21.81 |
| WR / WR | Carnell Tate | $5,000 | 11.20 | Carnell Tate | $5,000 | 11.20 |
| WR / WR | Rome Odunze | $4,900 | 11.53 | Rome Odunze | $4,900 | 11.53 |
| WR / WR | DK Metcalf | $5,700 | 10.87 | DK Metcalf | $5,700 | 10.87 |
| QB / QB | Aaron Rodgers | $5,500 | 20.32 | Aaron Rodgers | $5,500 | 20.32 |

### 4. Arizona passing response

Brissett/Wilson benefit together if Arizona must sustain productive passing; Rams Puka/Kyren provide opposing offensive exposure. Prototype changes several supporting salaries/roles, adding Tampa rushing/receiving exposure. A bringback is a conditional shared-environment story, not an unconditional positive correlation or forced team stack.

| Role | Control player | Salary | Mean | Prototype player | Salary | Mean |
|---|---|---:|---:|---|---:|---:|
| RB / DST | Chuba Hubbard | $6,300 | 14.57 | Buccaneers | $2,600 | 4.81 |
| DST / RB | Chargers | $2,100 | 3.95 | Kyren Williams | $6,800 | 19.78 |
| RB / WR | Kyren Williams | $6,800 | 19.78 | Puka Nacua | $8,100 | 21.81 |
| WR / RB | Puka Nacua | $8,100 | 21.81 | Bucky Irving | $6,200 | 13.74 |
| WR / WR | Carnell Tate | $5,000 | 11.20 | Michael Wilson | $6,700 | 14.40 |
| WR / WR | Michael Wilson | $6,700 | 14.40 | Wan'Dale Robinson | $4,500 | 10.32 |
| WR / TE | Devaughn Vele | $5,100 | 10.69 | Harold Fannin Jr. | $4,100 | 8.87 |
| TE / QB | Harold Fannin Jr. | $4,100 | 8.87 | Jacoby Brissett | $5,800 | 18.38 |
| QB / WR | Jacoby Brissett | $5,800 | 18.38 | Emeka Egbuka | $5,200 | 10.77 |

### 5. Indianapolis rushing control

Taylor leads the primary rushing case; Stafford/Higbee share Rams passing events while Hubbard is another rushing-volume route. Prototype drops Henry and changes receiver/DST support, including a stale-status Flowers selection. Its lower baseline and marginal-RB clipping are reasons to withhold promotion, not to call it a superior full-lineup path.

| Role | Control player | Salary | Mean | Prototype player | Salary | Mean |
|---|---|---:|---:|---|---:|---:|
| DST / RB | Buccaneers | $2,600 | 4.81 | Jonathan Taylor | $8,000 | 15.54 |
| RB / RB | Jonathan Taylor | $8,000 | 15.54 | Chuba Hubbard | $6,300 | 14.57 |
| RB / DST | Chuba Hubbard | $6,300 | 14.57 | Chargers | $2,100 | 3.95 |
| QB / QB | Matthew Stafford | $6,400 | 25.22 | Matthew Stafford | $6,400 | 25.22 |
| RB / WR | Derrick Henry | $8,200 | 18.81 | Carnell Tate | $5,000 | 11.20 |
| WR / TE | Carnell Tate | $5,000 | 11.20 | Tyler Higbee | $3,400 | 9.86 |
| TE / WR | Tyler Higbee | $3,400 | 9.86 | Michael Wilson | $6,700 | 14.40 |
| WR / WR | Rome Odunze | $4,900 | 11.53 | Rome Odunze | $4,900 | 11.53 |
| WR / WR | Emeka Egbuka | $5,200 | 10.77 | Zay Flowers | $7,100 | 15.09 |

## Relationships that must be modeled rather than prohibited

- **Two same-team WRs (Tate/Robinson):** can both succeed through team passing volume or efficient scoring. Shared QB/targets create dependency; they do not prove incompatibility. Their saved Tennessee market context was44.5 total and18.75 implied team points, so a shootout is not assumed. A low/moderate total does not make concentrated receiving production impossible.
- **Puka/Kyren:** productive Rams drives can support both; passing TDs, rushing finishes, catches and goal-line allocation determine whether they rise together. Individual ceiling sums alone do not resolve that tradeoff.
- **WR/TE and QB/receiver:** receiving options compete for target allocation, while QB and receiver fantasy points can come from the same completed pass/TD. A physical TD cannot be allocated twice among receivers; fantasy QB/receiver scoring both count by rule.
- **Two RBs:** carries, receiving work and goal-line opportunities can compete; rotation, receiving roles and a run-heavy game can also support both. A common budget should reflect those conditional paths, not a blanket two-RB ban.
- **Opposing bringbacks:** sustained two-sided possessions can support multiple roles, but a lead/runout, turnovers or defensive scoring can change workload. Matchup total alone is not a calibrated joint probability.
- **Captain/FLEX:** canonical players get physical opportunities once;1.5× scales the Captain fantasy score, not attempts or touches. Synthetic full-roster end-to-end tests cover both Classic and Showdown, including distinct canonical identity and salary legality. No new live Showdown portfolio was activated.

## Empirical check and next evidence needed

The independent [near-P90 paired study](../../joint_p90_20261016/v1/REPORT.md) finds matched WR/WR near-P90 rates1.86% versus1.70% in different games, with a confidence interval spanning zero; richer matching gives1.77% versus1.77%. QB/WR and RB/RB relationships differ, and all rich-match difference intervals include zero. Four matched week clusters, scoring-version/source-publication gaps and model variation prevent a calibrated production penalty or probability. These are retrospective diagnostics, not an optimizer treatment effect. The Thursday actual-path audit is separate and still being reviewed.

Next required work is evidence-driven: a marginal-consistent joint outcome representation with shared plays, pass/rush split, targets, yards and TD allocation; sourced role uncertainty; game/possession dependence; and time-safe validation of complete-lineup ranking. It must retain positive shared environments, preserve every player marginal before evaluating dependence, and compare full salary-constrained portfolios against unchanged exact mean and current Analyst controls. No automatic pair penalty or new scoring weight is justified here.

## Evidence

- [Manifest/settings/source hashes](manifest.json), [control full outputs](control.json), [prototype full outputs](opportunity_supported.json), [exact-mean comparison](exact_mean.json).
- [Validation assessment](validation_assessment.json), [original saved roster capacity stress](original_roster_capacity_stress.json).
- [Current normal readiness/source blockers](../../sunday_normal_refresh_20261016/v1/REVIEW.md), [dated ten-game Analyst research](../../sunday_refresh_20261015/v2/RESEARCH.md).
- Tests cover normalized budget conservation, shared passing-event accounting, explicit unknowns, retained teammate combinations even with44.5total, positive shared-environment response, opposing roles, Captain multipliers, exact-mode regression, and rejection of production activation. Tests establish implementation behavior, not forecast validity.

## Same-world objective reconciliation

Each slot below uses identical conditional player moments, source opportunity data and scoring treatment for both full rosters. These are research proxy values, not probabilities or outcomes. Generation changes the candidate pool; original-objective and prototype-objective columns must not be cross-compared as if they were the same metric.

| Slot | Control roster: original objective | Prototype roster: original objective | Control roster: capacity-stress objective | Prototype roster: capacity-stress objective |
|---|---:|---:|---:|---:|
| 1 | 166.438 | 166.438 | 165.354 | 165.354 |
| 2 | 170.377 | 170.369 | 168.120 | 169.464 |
| 3 | 167.231 | 167.231 | 166.147 | 166.147 |
| 4 | 162.418 | 160.220 | 161.066 | 160.220 |
| 5 | 161.268 | 160.303 | 157.033 | 157.152 |

[Common-world input hashes and reconciliation](common_world_evaluation.json). A proxy objective increase only establishes mathematical selection under that unvalidated proxy. It does not justify promotion.

## Domain acceptance review

Applied [Football Awareness First](../../../skills/football-awareness/SKILL.md): “Reject promotion when the mechanism contradicts evidence or football accounting, even if aggregate metrics improve.” This rejection follows the observed lone-RB clipping failure, not a generic preference against correlated players. The same-world slot4 prototype roster has lower capacity-stress value than the control roster because previous changed selections alter remaining portfolio exposure capacity; it is not claimed to dominate every slot. The user-requested evidence-first hold remains.
