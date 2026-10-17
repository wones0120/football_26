# Unlocked highest-projection Sunday lineup

**Stafford earns the QB spot without a lock.** With stacks and bringbacks optional and all player locks removed, the exact baseline-mean solver selects **133.18 projected points for $49,800**. It voluntarily keeps Puka and Kyren. Locking those two produces the **same nine-player roster and projection**, so removing their locks costs nothing under this build.

The actual UI-generated and reopened saved run is **`fa65082d-ca23-45e0-9edf-b45b79de86e5`**. In [the app](http://127.0.0.1:5173/), choose Operations → Sunday Main → Recent optimizer runs → **Highest baseline projection · optional stacks**, run `fa65082d`. The [saved API result](http://127.0.0.1:8000/api/optimizer/results/fa65082d-ca23-45e0-9edf-b45b79de86e5) provides the same persisted result. The earlier direct-workflow verification run `bea31422-0e90-46fd-98fb-98a2824f94be` is preserved separately.

| Slot | Unlocked winner | Puka + Kyren locked, QB free | Best without Stafford |
|---|---|---|---|
| QB | Stafford $6,400 | Stafford $6,400 | Cousins $5,400 |
| RB | Kyren $6,800 | Kyren $6,800 | Kyren $6,800 |
| RB | Henry $8,200 | Henry $8,200 | Henry $8,200 |
| WR | Puka $8,100 | Puka $8,100 | Puka $8,100 |
| WR | Odunze $4,900 | Odunze $4,900 | Odunze $4,900 |
| WR | Tate $5,000 | Tate $5,000 | Wan’Dale $4,500 |
| TE | Higbee $3,400 | Higbee $3,400 | Otton $3,300 |
| FLEX | Wan’Dale $4,500 | Wan’Dale $4,500 | Hubbard $6,300 |
| DST | Panthers $2,500 | Panthers $2,500 | Panthers $2,500 |
| Salary / unused | **$49,800 / $200** | **$49,800 / $200** | **$50,000 / $0** |
| Unchanged base projection | **133.1786** | **133.1786** | **131.6756** |
| Gap against unlocked | — | **0.00** | **−1.5030** |

All six final-build solves finished **Optimal**: the saved unlocked run, its exact replay, Puka/Kyren locked, Stafford/Puka/Kyren locked, Stafford alone required, and every QB except Stafford allowed. The explicit research locks and exclusions for each control remain visible in [full canonical rosters](FULL_ROSTERS.md); only the main unlocked result was saved through the UI as an actual optimizer run.

**What the cheaper QB buys:** Cousins saves $1,000. Together with the winner's unused $200 and Higbee→Otton saving $100, that funds Tate→Hubbard (+$1,300), moving a third RB into FLEX. The rest of the roster stays the same. Those changes recover about 1.95 projected points elsewhere, but Stafford's unchanged 25.22 mean exceeds Cousins' 21.76 by about 3.46, leaving the whole alternative **1.50 points behind**. This comparison covers every other eligible QB, rather than assuming a particular replacement. Allen has a higher raw QB mean, but his extra salary does not beat Stafford's full-roster fit under these rules.

The winner is also **identical to our earlier Wan’Dale/Henry/Higbee mean-optimal Puka/Kyren construction**. Against the original saved normal lineup 1 at 131.57, it replaces Wilson with Wan’Dale, Hubbard with Henry, and Otton with Higbee: +1.60 unchanged base points with $200 unspent. No improvement is attributed to removing locks that the optimum would have chosen anyway.

**The correlation is voluntary.** Stafford has Puka and Higbee plus receiving back Kyren; Arizona is absent. Four Rams cost $24,700 (**49.4%** of the salary cap), while Tate/Wan’Dale add a second same-team receiving pair. This remains concentrated despite removing the rules. It is the highest sum of baseline means under the remaining controls, not a fitted covariance, payout or blowout-risk optimum. The [prior Stafford/stack review](../../sunday_stack_requirements_study_20261015/v1/REVIEW.md) retains the football case and passing-versus-runout uncertainty. No new probability, projection adjustment or correlation bonus was added here.

**The new app mode is reproducible.** Select **Classic selection objective → Highest baseline projection · optional stacks**. It submits one unlocked lineup, independent of Analyst scenario objectives. Existing saved lineup-count and player-lock preferences are not overwritten; this mode's request explicitly uses one lineup and no locks. Returning to Analyst scenarios restores that separate workflow. The highest-projection mode bypasses both the user/strategy QB-stack inequalities and generated scenario QB/team/receiver/bringback pins. No stack is banned.

Other rules are retained: current canonical identity/role and injury exclusions, questionable exclusions, minimum QB/RB $4,500, favored RB/DST with TE not required favored, single TE, four/team, five/game, no offense against DST and the DEN opponent exclusion. Max player exposure remains 100%. The prior explicit **no season-average rank restriction for this research run only** was repeated; stored QB/WR 50% and RB/TE 25% preferences were not changed. No additional offensive salary floor or player lock was introduced. Thursday Captain settings and named exceptions are outside this mode and remain isolated.

The final UI run uses frozen preliminary snapshot `f59b024c978e49d8dd12ad4a62b02603a316a7a839fd0b29017f65e3b834d0fa`, projection `7460c58b-219e-4099-a2a3-72ddaf1d7fc6` and ownership `db8e4815-e554-4be0-818b-685ae3484a40`. No source refresh or model fit was needed. Its canonical salary/position/team/opponent/mean input set is numerically identical to the initial verification build; all reported controls were nevertheless rerun on the final UI run's **same frozen 202-player finite-mean pool**. Four other rows lacked finite means and were excluded explicitly, not scored as zero. No highest-across-excluded-players claim is made.

The saved legal model has 348 constraints, 202 player variables and exactly the original mean as each player's objective coefficient. It has **zero auxiliary objective bonuses and zero single-player forced equalities**; the public request and runtime lock lists are empty. The runtime records optional QB stacks, optional opponent bringbacks and no generated scenario constraints. Canonical UUID, DK native ID, position, team and salary were checked against the captured salary rows for every selected control player. Source projections and the original saved normal portfolios remain unchanged.

**This is preliminary research, not final injury clearance.** The original official-player-status-refresh failure remains explicit; `entry_ready=false` and existing contest export blocking remain in force. The model's current role assumptions, Rams concentration and touchdown allocation uncertainty still matter before Sunday. No entry or contest CSV export occurred.

Validation: **46 targeted backend tests**, **19 UI tests** and the TypeScript/Vite production build passed. Chrome at localhost verified the objective selector, retained controls, submission, completed persisted result, reopened objective label and all nine displayed slots including WR FLEX. Desktop screenshots are below; mobile layout was not separately checked. The local API/worker were restarted only after confirming the durable queue was idle; an initial Python-environment restart issue was corrected, and the queued UI run then completed successfully.

[Machine validation](VALIDATION.json) · [saved request/result](ui_saved_run.json) · [API reopen](ui_api_response.json) · [same-build controls](ui_matched_comparisons.json) · [full canonical rosters](FULL_ROSTERS.md) · [mode documentation](../../../docs/product/classic_highest_projection.md).

![Reopened highest-projection result](ui_reopened.jpg)

![Nine saved roster slots](ui_roster.jpg)
