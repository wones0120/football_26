# Stafford and stack requirements — matched Sunday research

**Stafford remains a reasonable $6,400 play here, but he should earn the quarterback slot rather than inherit it from the Rams scenario.** In the frozen inputs, the solver still chooses him when all 17 eligible quarterbacks can compete and both QB stacking and Arizona bringbacks are optional. The measurable restriction is **the mandatory Arizona receiver**, not the QB stack floor: removing Arizona's requirement improves the same conditional objective by **1.30**; removing the QB stack floor improves it by **0.00** in this test.

That does **not** prove forced stacking is broadly harmless. Puka and Kyren remain locked from your prior request, so any Stafford lineup is already stacked. It also does not prove Stafford is safe against a blowout: the strongest genuinely unstacked alternative is only **0.85 conditional-objective units** behind. That small gap is not calibrated evidence of payout superiority.

**What was actually hard-required:**

| Layer | Actual rule | Effect on this review |
|---|---|---|
| Saved user/strategy stack policy | Selected QB must have ≥1 same-team skill player; **RB counts**, alongside WR/TE. Opponent bringback=false. | Seventeen exact hard inequalities in the frozen model, one per eligible QB. Stafford already satisfies it with either Puka or Kyren. |
| Generated normal LAR idea | Stafford is the only eligible primary QB; ≥1 LAR WR/TE; ≥1 supported ARI receiver. Secondary offenses ≤2 players per team. | This secretly makes “QB free” meaningless unless its separate LAR-only QB pin is removed. The scenario inferred the Arizona response; it was not a saved user requirement. |
| Actual normal scenario objective | Sum of each player's frozen conditional mean +0.35×(p 90−mean). | Captured legacy objective contained 512 auxiliary correlation coefficients, but the normal scenario **replaces that objective**. Those bonuses contribute zero to these actual solves. Conditional moments still favor the LAR passing branch. |

The exact 17 coefficient-pattern matches and source audit are in [RESULTS.json](RESULTS.json). Original code paths are [QB stack construction](../../../backend/app/product_services/optimizer.py:4453) and [scenario construction](../../../backend/app/product_services/scenario_allocation.py:159). No QB was recovered from an upstream stack filter: all 17 QBs in the original source pool were already present in the frozen legal model.

**Matched factorial results:** all use the identical frozen salary/projection/ownership pool and normal LAR-passing moments. Puka/Kyren stay fixed. In every QB-free row, the generated LAR-only QB pin is explicitly removed; otherwise all other constraints, including secondary-team limits, remain intact.

| Hard QB stack | Mandatory ARI receiver | QB held / QB allowed to vary | Base mean | Conditional mean | Same conditional objective |
|---|---|---|---:|---:|---:|
| Required | Required | Stafford / **Stafford chosen** |131.57 |131.60 |168.67 |
| Required | Optional | Stafford / **Stafford chosen** |131.76 |133.25 |169.97 |
| Optional | Required | Stafford / **Stafford chosen** |131.57 |131.60 |168.67 |
| Optional | Optional | Stafford / **Stafford chosen** |131.76 |133.25 |169.97 |

Each paired row summarizes two separate optimal solves with the same result; [all eight rows](FACTORIAL.md) retain the individual evidence. “Optional stack” permits useful correlation. It neither bans stacks nor requires an unstacked lineup. In the winning fully optional lineup, Stafford voluntarily keeps Puka, Adams and receiving back Kyren; Arizona disappears.

**Stafford's football case and the blowout concern:** the [Rams' official game log](https://www.therams.com/team/players-roster/matthew-stafford/) confirms 55/51/54 attempts in the last three games. Those games were competitive; they do not establish 50-plus attempts against Arizona. The same log offers a useful counterexample to automatically rejecting a big favorite: in the Week 2 28–6 win, Stafford threw only 31 times but produced 327 yards and four passing touchdowns. Passing production can build the lead before the second-half runout. Conversely, his 51-attempt Week 4 win produced zero passing TDs. Volume and team victory alone do not determine quarterback value.

The latest [primary DraftKings event page](https://sportsbook.draftkings.com/event/ari-cardinals-%40-la-rams/34118080), checked October 15, agrees with the frozen LAR−12.5/51.5 market. The resulting 32 implied team points support scoring opportunity; they are **not 32 quarterback points or an implied number of passing TDs**. If Kyren finishes the early drives on the ground, or defensive/short-field scores build the lead, Stafford can lose both passing TDs and late attempts. He has just 21 rushing yards and zero rushing TDs through five games, so his own rushing does little to rescue that branch. Alaric Jackson's suspension and short Rams rest are further protection/efficiency considerations from the existing research, not newly quantified deductions.

Puka's receptions/yards can still justify his individual score without buying Stafford. Adding Stafford concentrates the lineup on passing TDs and yardage; it does not increase Puka's forecast. Kyren's receiving can connect to Stafford, but his rushing scores can bypass him. An Arizona bringback is useful only if its own role/price earns the slot or one deliberately wants the competitive-response story. A Rams win by many points does not require an Arizona player to score well.

**Best legal full rosters under the tested choices:**

| Slot | Original saved rules/story | Both optional, QB free | Best genuinely unstacked QB |
|---|---|---|---|
| QB | Stafford $6,400 | Stafford $6,400 | Cousins $5,400 |
| RB | Hubbard $6,300 | Hubbard $6,300 | Hubbard $6,300 |
| RB | Kyren $6,800 | Kyren $6,800 | Kyren $6,800 |
| WR | Puka $8,100 | Puka $8,100 | Puka $8,100 |
| WR | Wilson $6,700 | Adams $6,600 | Adams $6,600 |
| WR | Tate $5,000 | Tate $5,000 | Tate $5,000 |
| TE | Otton $3,300 | Otton $3,300 | Higbee $3,400 |
| FLEX | Odunze $4,900 | Odunze $4,900 | Odunze $4,900 |
| DST | Panthers $2,500 | Panthers $2,500 | Patriots $3,500 |
| Salary | **$50,000** | **$49,900** | **$50,000** |
| Unchanged base mean | **131.57** | **131.76** | **130.81** |
| Same conditional mean |131.60 |133.25 |133.29 |
| Same conditional objective |168.67 |169.97 |169.12 |

Cousins' $1,000 discount plus the existing $100 unused salary buys Otton→Higbee (+$100) and Panthers→Patriots (+$1,000). The full conditional mean is fractionally higher but its conditional objective is 0.85 lower because the modeled upper-tail spread differs. There are **no Raiders WR/TE/RB partners** in that roster. This is a legal unstacked quarterback construction, yet it still holds four Rams skill players: removing the QB stack requirement does not, by itself, diversify Rams exposure or validate Cousins' actual availability. His base mean 21.76 and the other role assumptions are inherited unchanged from the preliminary snapshot.

Every eligible QB was also forced once under both-optional rules. Cousins was the strongest alternative; Allen ($7,500) reached 130.49 base/167.58 objective and Rodgers ($5,500)129.25/167.56. The solver did not replace Stafford with either once salary was redistributed. [All 17 QB comparisons](QB_COMPARISONS.md). A separate explicitly labeled base-mean optimization still voluntarily picked Stafford, using the prior Wan’Dale/Henry/Higbee roster at 133.18 base; its chosen objective differs, so it is not mixed into the conditional factorial ranking.

**My policy recommendation is optional QB stacks and optional opponent bringbacks for this research, with both constructions allowed to compete.** Retain correlation as a construction to consider; do not turn a projected Rams lead into an automatic Stafford exclusion. Under today's frozen assumptions, Stafford earns the slot narrowly. If your central football opinion is that this game ends with a long runout and insufficient passing TDs, the current experiment has not calibrated that opinion: it uses the same LAR-passing sensitivity everywhere, not a fitted blowout mixture. The correct remaining uncertainty is the reliability of that passing/TD premise, not whether a hard stack rule secretly forced this particular winning lineup.

This report changes no defaults. It made 31 deterministic CBC solves (seed 7;12-second cap each), all Optimal, with 19 distinct canonical research rosters. It preserved exact source hashes, salary cap, oneTE, QB/RB minima, exclusions, favored RB/DST, team/game caps and no offense against DST. Stack requirements and scenario pins were changed only in their declared diagnostic arms. The original normal generator explored six candidates to save five; this is a new bounded generation experiment, not an exhaustive portfolio comparison or forward validation. With Puka/Kyren locked, Stafford cannot be genuinely unstacked; no claim about a completely unlocked Rams core is made. No new blowout probability, model fit, injury clearance, production run, export or entry was created.

[Full canonical rosters](FULL_ROSTERS.md) · [machine results/constraint audit](RESULTS.json) · [primary-source checks](SOURCES.json) · [validation](VALIDATION.json) · [reproduction script](run_study.py).
