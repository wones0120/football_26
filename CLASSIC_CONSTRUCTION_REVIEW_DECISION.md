# Classic construction review decision

For the user’s concentration concern, the validated exact-two-pass-catcher/one-bring-back replacement deserves consideration: Strange → Otton reduces JAX 4 → 3 and CIN–JAX 5 → 4. WR FLEX remains the highest-scoring captured choice; the three-RB replacement C does not reduce Jacksonville concentration. See the [app handoff](CLASSIC_CONSTRUCTION_REVIEW_APP_HANDOFF.md) and [complete app-generated evidence export](artifacts/classic_construction_review_live_fix/lower-concentration-evidence.html).

Run: `8a25b11e-cfae-442b-afd6-bf66042d9f2c` · Entry 1 · single TE **off**. Diagnostic request: `1d7fdac2-8c1b-4b50-8888-761b69caf00b`.

Only existing `live-review-response.json`, `live-rendered-review.txt`, and `CLASSIC_CONSTRUCTION_REVIEW_LIVE_FIX.md` were read for this decision. Controls: **5 entries; 80% global exposure; primary-game cap 3; overlap 5; team cap FOUR; within-lineup game cap 5**. Current shared builder on frozen saved inputs; `implementation_matches_saved=false`. These alternatives have not been selected or applied.

## Five distinct rosters

A = saved WR-FLEX baseline and the identical optimal WR-FLEX individual/replacement result. B = best captured individual three-RB result. C = best captured validated three-RB replacement. D = best captured individual two-TE result. E = best captured validated two-TE replacement. “Best” refers to the captured restricted solve, not every possible portfolio.

The membership table shows each player once; each letter defines one nine-player roster. Names, natural positions, teams and salaries are exactly as captured, including Kenneth Walker III’s KC team. Canonical UUIDs below preserve roster identity. Captured roster-slot assignments and persisted alternative lineup IDs are unavailable; no particular RB/WR/TE is arbitrarily assigned to FLEX.

| Player | Pos | Team | Salary | In rosters | Frozen elevated list |
| --- | --- | --- | ---: | --- | --- |
| Trevor Lawrence | QB | JAX | $5,900 | A, B, C, D, E | Not listed |
| Chase Brown | RB | CIN | $6,100 | B, D | Not listed |
| Javonte Williams | RB | DAL | $6,600 | A, B, C, D, E | Not listed |
| Kenneth Walker III | RB | KC | $8,200 | A, B, C, E | Not listed |
| Kyren Williams | RB | LAR | $5,900 | C | Not listed |
| Ja'Marr Chase | WR | CIN | $8,100 | D, E | Not listed |
| Jakobi Meyers | WR | JAX | $5,000 | A, B, C, E | Elevated |
| Michael Wilson | WR | ARI | $5,500 | A, B, D | Not listed |
| Parker Washington | WR | JAX | $6,500 | A, B, C, D, E | Not listed |
| Tee Higgins | WR | CIN | $6,100 | A, C | Not listed |
| Brenton Strange | TE | JAX | $3,200 | A, B, C, D, E | Not listed |
| Dalton Kincaid | TE | BUF | $5,300 | D | Not listed |
| Kenyon Sadiq | TE | NYJ | $4,000 | E | Elevated |
| Cardinals | DST | ARI | $2,500 | E | Not listed |
| Rams | DST | LAR | $2,600 | A, B, C, D | Not listed |

“Not listed” means absent from the frozen elevated-ID list, not injury-free or cleared now. A/B/C contain elevated Jakobi Meyers; D has no listed elevated player; E contains elevated Meyers **and Kenyon Sadiq**. Risk reasons, timestamps and detailed availability tiers are unavailable in this response. No classifications were inferred from names.

<details><summary>Canonical player identities (apply to every roster above)</summary>

- Brenton Strange: `ddb43b49-94bf-4c9c-b875-99a2d8313797`
- Cardinals: `f201e474-a7d5-47b7-8c20-f72440e2847b`
- Chase Brown: `0be06444-4cd6-41a4-98a5-877a9a5c42b2`
- Dalton Kincaid: `f962e756-c4f4-485a-8dc8-70c366239ebe`
- Ja'Marr Chase: `f816bdba-894a-40e6-adf6-a3c2c0d659cb`
- Jakobi Meyers: `e6f33396-aab8-4d70-bc70-2717b52aa86c`
- Javonte Williams: `893d01f0-9572-4d0c-a680-79fdf8276409`
- Kenneth Walker III: `5169c450-ece6-4729-8952-ba040d3f64f2`
- Kenyon Sadiq: `368e6709-83dc-41ac-9eac-a3e03f0e81a4`
- Kyren Williams: `319a7e5c-7967-4405-90f9-36ddfea66dfd`
- Michael Wilson: `d0ae658e-ab5e-49ad-bec3-5ae2c19867f1`
- Parker Washington: `734de5e7-0dc0-4ded-8156-c4a0e9093012`
- Rams: `fcbaad85-7f54-4df5-8678-0131e74c265f`
- Tee Higgins: `1bc5ea87-e6bb-4608-a110-2b657344f1ed`
- Trevor Lawrence: `af4cc0b8-e85c-4a6a-847b-d92fdd75ec80`

</details>

## Captured performance and score components

All deltas below use A, the same-frame baseline reported by the current builder. Metrics are rounded to six decimals; the captured JSON retains full precision. **Σ marginal P90 is a sum of player marginals, NOT a lineup percentile.** Objective differences are score units, not winning-probability differences.

| Roster | Salary | Mean | Δ mean | Σ marginal P90 | Δ ΣP90 | Objective | Δ objective |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | $49,600 | 129.973397 | +0.000000 | 228.607672 | +0.000000 | 5.419170 | +0.000000 |
| B | $49,600 | 132.572806 | +2.599408 | 233.201807 | +4.594135 | 5.413157 | -0.006013 |
| C | $50,000 | 130.829331 | +0.855934 | 224.667094 | -3.940578 | 5.382224 | -0.036946 |
| D | $49,800 | 132.809887 | +2.836490 | 229.018008 | +0.410337 | 5.365836 | -0.053334 |
| E | $50,000 | 129.747941 | -0.225456 | 224.380905 | -4.226767 | 5.346771 | -0.072399 |

Weighted objective contributions (already normalized; do not add raw mean/P90 to these):

| Contribution | A | B | C | D | E |
| --- | ---: | ---: | ---: | ---: | ---: |
| Projection / mean | 1.884062 | 1.921743 | 1.896470 | 1.925179 | 1.880794 |
| Ceiling / marginal P90 | 2.946939 | 3.006161 | 2.896141 | 2.952228 | 2.892452 |
| Context | 0.141211 | 0.135929 | 0.139883 | 0.144359 | 0.126566 |
| QB stack | 0.243579 | 0.243579 | 0.243579 | 0.162386 | 0.243579 |
| Bring-back | 0.032545 | 0.000000 | 0.032545 | 0.032545 | 0.032545 |
| Game environment | 0.039777 | 0.039777 | 0.039777 | 0.039777 | 0.039777 |
| Other correlation | 0.131058 | 0.065969 | 0.133830 | 0.109362 | 0.131058 |
| Base subtotal (projection + ceiling + context) | 4.972212 | 5.063832 | 4.932494 | 5.021766 | 4.899813 |

Leverage contributes 0 but is **unavailable** (“leverage evidence missing”). Ownership-chalk and duplication terms are **disabled**, with 0 contribution; ownership is diagnostic, not a soft selector term. Penalties and other residual are active-zero; recorded negative correlation is 0 in A–E. These statuses must not be read as evidence of low duplication or favorable leverage. The structural contributions above complete the base subtotal to the objective. Captured comparison component sums match the solver.

## Changes, stacks and concentration

| Roster | Added vs A | Removed vs A | Actual QB pass catchers / offensive bring-backs | JAX | CIN–JAX incl. DST |
| --- | --- | --- | --- | ---: | ---: |
| A | None | None | 3: Brenton Strange, Parker Washington, Jakobi Meyers / 1: Tee Higgins (WR) | 4 | 5 |
| B | Chase Brown | Tee Higgins | 3: Brenton Strange, Parker Washington, Jakobi Meyers / 1: Chase Brown (RB) | 4 | 5 |
| C | Kyren Williams | Michael Wilson | 3: Brenton Strange, Parker Washington, Jakobi Meyers / 1: Tee Higgins (WR) | 4 | 5 |
| D | Chase Brown, Dalton Kincaid, Ja'Marr Chase | Kenneth Walker III, Tee Higgins, Jakobi Meyers | 2: Brenton Strange, Parker Washington / 2: Chase Brown (RB), Ja'Marr Chase (WR) | 3 | 5 |
| E | Kenyon Sadiq, Ja'Marr Chase, Cardinals | Michael Wilson, Tee Higgins, Rams | 3: Brenton Strange, Parker Washington, Jakobi Meyers / 1: Ja'Marr Chase (WR) | 4 | 5 |

All five use Trevor Lawrence, primary game CIN–JAX, and no same-team RB with QB. A/B/C/E use four JAX players (QB + three WR/TE); D uses three JAX (QB + two WR/TE) but replaces that fourth JAX dependency with a second CIN bring-back. **All five still contain five CIN–JAX players.** C adds the Kyren Williams–Rams LAR RB/DST pairing (two LAR players), replacing the ARI offensive singleton; its captured RB/DST objective contribution is +0.002771484. E substitutes Cardinals DST but does not reduce the JAX or CIN–JAX counts.

## Replacement evidence and restrictions

WR replacement A, RB replacement C and TE replacement E are **verified, violations=[]**, with solver **Optimal / Optimal Solution Found / proven_optimal=true**. B and D also have optimal individual solves, but no portfolio-validation certificate. A’s baseline has no solver audit itself; its identical WR comparison supplies the captured solver result.

- The retained four entries, exposure budgets, overlap cap 5 and primary-game cap 3 constrain replacements. `required_player_ids=[]`, `blocked_primary_games=[]`. No extra minimum-player requirement or already-blocked primary game is recorded.
- **Chase Brown has zero remaining appearances**. This directly prevents B and D from being used unchanged as replacements. The capture does not prove that this alone explains every difference between individual and replacement optima.
- Remaining appearances for Javonte Williams, Brenton Strange, Parker Washington and Michael Wilson are each 1. All five rosters retain the first three and would exhaust their remaining budget; C/E omit Wilson. Remaining budgets also include Lawrence 2, Ja’Marr Chase 2, Cardinals 2, Meyers 3, Higgins 3, Rams 3, and Walker/Kyren/Kincaid/Sadiq 4 each. These are saved replacement budgets, not current risk assessments.
- All five reach the within-lineup game cap 5; A/B/C/E reach team cap 4, while D’s maximum team count is 3. C/E each have a captured salary of $50,000. Numeric saturation identifies tight limits, not a solver dual certificate or proof of a unique causal binding set.
- Single TE is off; no additional elevated-risk group constraint is recorded (`maximum_player_groups=null`). The frozen elevated classification remains visible despite eligibility. Exact pairwise overlap values, full other-entry rosters, minimal binding explanations and joint outcome dependence are unavailable in this response.

## Why the ordering changes

**A narrowly outranks B by 0.006013107.** Brown-for-Higgins increases raw mean by 2.599408 and ΣP90 by 4.594135. Weighted projection/ceiling improve by +0.096902516 together, but context drops 0.005281695 and structural rewards fall 0.097633929: the WR bring-back reward (-0.032544643) plus three opposing-pass-catcher pair rewards (-0.065089286). The QB stack and game-environment terms are unchanged. Projection and the structural bonuses pull in different directions.

**Fitting three RBs around the retained four changes the tradeoff materially.** C trails B by 0.030933010 objective, 1.743475 mean and 8.534713 ΣP90; the gap to A widens from 0.006013107 to 0.036946117. C keeps Higgins and replaces Wilson with Kyren: mean rises 0.855934 versus A, but ΣP90 falls 3.940578. Weighted mean (+0.012407404) and RB/DST correlation (+0.002771484) favor C; weighted ceiling (-0.050797246) and context (-0.001327759) favor A. C adds LAR script dependence while retaining the four-JAX/five-game concentration and the common player budgets.

**D reduces four-JAX dependence, but not five-game dependence.** Its weighted projection/ceiling/context gain of +0.049554271 is outweighed by losing one QB/pass-catcher contribution (-0.081192857) and one opposing-pass-catcher pair (-0.021696429), leaving objective -0.053334425 versus A. It removes elevated Meyers from this frozen roster but has no replacement certificate and Brown is already at the replacement appearance limit. E, the validated TE alternative, restores four JAX, retains Meyers, adds elevated Sadiq, and trails A by 0.072399094; projection, ceiling and context all decline while structural contributions equal A.

An optimal one-entry replacement is conditional on fixing the other four entries. It does not establish joint portfolio optimality. Neither the objective gaps nor ΣP90 support a winning-probability or lineup-percentile claim.

## Other captured families

Entry 1’s generation-template minimums are **one WR/TE with QB and zero bring-backs** (`active_template_minimums=[1,0]`). They are minima, not exact counts. The explicitly exact families below impose their own requested counts. All feasible cases below are solver Optimal; every feasible replacement has verified portfolio validation. Values are objective / mean / Σ marginal P90, with objective delta versus A.

| Family | Individual | Replacement |
| --- | --- | --- |
| Exactly one WR/TE with QB | 5.257616 (-0.161554) / 133.759 / 234.388 | 5.219301 (-0.199869) / 131.445 / 228.670 |
| Exactly two WR/TE with QB | 5.415412 (-0.003758) / 133.325 / 233.535 | 5.365537 (-0.053633) / 129.790 / 227.162 |
| No offensive bring-back | 5.297071 (-0.122099) / 131.271 / 230.009 | 5.297071 (-0.122099) / 131.271 / 230.009 |
| Exactly one offensive bring-back | A (same roster); 5.419170 (+0.000000) / 129.973 / 228.608 | A (same roster); 5.419170 (+0.000000) / 129.973 / 228.608 |
| Exactly two offensive bring-backs | 5.415412 (-0.003758) / 133.325 / 233.535 | 5.365537 (-0.053633) / 129.790 / 227.162 |
| QB + two WR/TE + one offensive bring-back | 5.352921 (-0.066249) / 133.330 / 235.534 | 5.328972 (-0.090199) / 130.065 / 231.299 |
| Opposing RB bring-back | 5.415412 (-0.003758) / 133.325 / 233.535 | 5.123946 (-0.295224) / 124.355 / 219.836 |
| QB with same-team RB and WR/TE | 5.277782 (-0.141388) / 131.135 / 231.448 | 5.223339 (-0.195831) / 128.219 / 225.128 |
| QB with same-team RB without WR/TE | Excluded; not searched | Excluded; not searched |
| True unrelated one-off | A (same roster); 5.419170 (+0.000000) / 129.973 / 228.608 | A (same roster); 5.419170 (+0.000000) / 129.973 / 228.608 |
| Secondary opposing mini-stack | 5.338152 (-0.081018) / 131.859 / 228.067 | 5.303126 (-0.116044) / 130.055 / 229.319 |

A is also the identical captured roster for **exactly one offensive bring-back** and **true unrelated one-off**, in both modes. Exactly two WR/TE and exactly two bring-backs share their returned rosters in both modes; the opposing-RB individual also matches that individual roster. Their distinct restrictions remain distinct comparisons.

The **QB + exactly two WR/TE + exactly one bring-back** case exists (`pc=2, bb=1`). Its individual is Lawrence + Strange/Washington with Brown as RB bring-back (JAX 3, CIN–JAX 4); its replacement is Lawrence + Washington/Meyers with Higgins as WR bring-back, and Cade Otton replaces Strange (JAX 3, CIN–JAX 4). It is feasible in both modes; replacement objective 5.328972, mean 130.064739, ΣP90 231.298675. This captured family offers a validated way to reduce the five-player game concentration, at a larger objective concession (-0.090198602 versus A); it has not been applied.

**Status separation:** 26 feasible searched cases (13 families × two modes); two **excluded-by-strategy-eligibility** cases for same-team RB without WR/TE. Those two were **not searched**, because RB cannot satisfy the minimum WR/TE stack. No independent not-searched family, template-based exclusion, infeasible solve, failed calculation or unavailable comparison is recorded. Do not convert exclusion into a solver failure.

## Decision and missing evidence

**Which alternative deserves consideration, and why?** For concentration, consider the validated exact-two-pass-catcher/one-bring-back replacement described above, not C. C remains the strongest captured validated RB/TE-FLEX replacement: a simple Wilson-to-Kyren change, +0.855934 mean, no newly listed elevated player, a verified conditional replacement, and objective only 0.036946117 below A. A still wins the captured composite score; C is a preference tradeoff, not an automatic improvement. If the actual goal is reducing JAX/game concentration, C does not accomplish it; the validated exact-two-pass-catcher/one-bring-back family above is the relevant captured comparison. D is informative for that question but cannot be applied unchanged.

**What evidence is missing before choosing it?** Current entry availability and the reasons/timing behind frozen elevated classifications; lineup/portfolio joint outcome and covariance evidence; calibrated contest-specific win/ROI/duplication evidence (leverage is unavailable and duplication scoring disabled); and joint portfolio comparison rather than fixing four entries. No new forecasts, risk classifications or current entry clearance were produced here.

New solves performed: **NONE**.
Scoring/default changes made: **NONE**. The subsequent handoff adds presentation/export of the existing diagnostic only; no backend or service changes.
Saved portfolio modified: **NO**.

## Focused scoring hypothesis (recorded, not implemented)

Do accumulated QB/pass-catcher, opposing-pass-catcher, and bring-back rewards assign an empirically defensible marginal value to additional pass catchers and game concentration? This is a validation hypothesis, not a confirmed double-counting defect. No RB bonus, correlation-weight cut, FLEX quota, or preferred-lineup tuning was implemented. Leverage remains unavailable and ownership-chalk/duplication objective terms remain disabled in this captured comparison.
