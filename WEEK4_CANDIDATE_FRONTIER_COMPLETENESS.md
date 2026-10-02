# Week 4 candidate frontier completeness

Frozen production run: `8b5c114c-b0d2-419e-8f41-bdcbc2674c71`. Analysis frozen **2026-09-30T16:52:31.708383+00:00**, before the saved first kickoff **2026-10-04T13:00:00-04:00**.

Evidence: [artifacts/candidate_completeness/week4-8b5c114c-reviewed.json](artifacts/candidate_completeness/week4-8b5c114c-reviewed.json); SHA-256 `ccdf58862a0c55c97c470246ab9f4212c538ce8d7b851cc73b8bb7118e9019b5`. Input SHA-256 `dd1e27f321b2758a963576700a3af018776279232f96489ea05e1ba664cbe502`. All findings use the saved pregame frame; no live projections, outcomes, or new market data were read.

## 1. Executive summary

**NO: the current 205 are not sufficiently complete.** Expanded discovery found **900 unique roster-legal candidates**, including **258 known risk-legal candidates inside 0.20**. The frozen 205 contain **84/258 (32.6%)** of that known competitive set. The historical raw 286 had generated **84/258 (32.6%)** before admission.

The four named near-frontier omissions and the Lamar negative control are evaluated below using canonical IDs. The algorithm uses pregame position leaders, coverage gaps, and systematic construction sweeps; these names appear only in the report and regression fixtures.

**Production remains unchanged:** target 205, saved selected ranks, projection/mean/P90 inputs, selector and correlation weights, ownership, exposure and injury policy, overlap=4, distinct-QB-path=true, thesis allocation, and exports. No API route, production solver/scorer, or database row was modified.

**Scope of the count claim:** exact roster cuts are implemented, but bounded enumeration is not an exhaustive count of the legal space. Every censored tolerance is reported as a lower bound. Recall means recall against this expanded known reference set; it is not a mathematical certificate of global recall.

## 2. Current generation architecture

The saved optimizer creates four QB shards containing 52/51/51/51 seed rosters. Each shard rotates the saved minimum stack templates and applies shard-level candidate caps and elevated-questionable limits. The saved uniqueness overlap=7 excludes rosters sharing eight or nine players with an earlier shard roster. Sharding also supplies a smaller pool to the normalized seed objective; final reports score against the full frozen pool. These are search restrictions, not exhaustive frontier enumeration.

Expansion adds global mean, P90, and selector optima, and one unrestricted plus four exact QB-family probes per starting QB. The saved exact templates are QB+1/QB+2 with zero/one bring-back. There is no exact QB+3 template sweep, partner-combination sweep, or systematic player coverage search in that expansion. Canonical roster deduplication produces 286 raw legal rosters. Joint admission maximizes cardinality up to 205, then selector sum under the saved candidate caps. Refill was not needed.

## 3. Exact raw → legal → admission lineage

Historical raw keys survive in `candidate_discovery.sources_by_lineup`, allowing exact scorer replay. All 205 saved accepted scores replay within 1e-9. The historical request ledger preserves 113 expansion requests and their legal/infeasible statuses; original seed timing and failed request details are not available. No missing historical log has been invented.

| Historical stage / terminal reason | Count |
| --- | --- |
| accepted_into_candidate_pool | 205 |
| admission_target_competition | 65 |
| injury_risk_rejected | 16 |

The legacy 65 `rejected_by_player_cap` records are split by a counterfactual: can the incoming roster participate in any cap-feasible pool of the same cardinality? If yes, its primary reason is admission-target competition. If no, its primary reason is a player-cap conflict. Direct insertion conflicts remain secondary evidence even when displacement is feasible. Injury, duplicate, family, and quality reasons have independent fields; no family or quality rule was added.

For each aggregate-cap conflict the artifact stores canonical player ID, exposure count/fraction, cap/count limit, one-roster swap feasibility, joint displacement feasibility, and a displaceable roster hash when available. Admission is a joint optimization: “before admission” is explicitly the chosen-pool baseline before counterfactual insertion, not an invented sequential history. Feasible displacement does not prove the swap would improve selector sum.

Every new solver event records its deterministic request, source, legal/unproven/infeasible status, runtime, canonical roster, and selector. Every unique raw candidate has an admission terminal reason at each tested target. Eligible player status is recorded for all frozen players. Roster-legal raw evidence includes the historical 16 risk failures; primary frontier recall excludes those failures.

The [request stage ledger](artifacts/candidate_completeness/week4-request-stage-lineage.json) materializes all ten stage statuses for every legal solve at every target, including duplicate rediscoveries against the initial raw universe. It distinguishes request-level duplicate rejection from the unique-roster admission ledger. Infeasible and unproven requests remain request failures and are never relabeled legal admission rejections.

## 4. Why Bucky Irving was missed

**Bucky Irving** (`a9f8d797-040e-4469-b9d5-bb39bf3792b2`): eligible=True; historical raw count=0; frozen admitted count=0; expanded raw count=4. Best legal selector **5.529723**, gap **0.076909**, equivalent frozen-205 rank **48**; QB **Trevor Lawrence**, **QB+2+bring-back**, salary **$49,900**.

**Confirmed generation omission:** no historical raw roster contains this player, so admission could not recover it.

Best-roster sources: `player_forced`. All containing sources: `player_forced, qb_direction, qb_frontier, stack_partner`. Target admitted counts (205/300/400/500): 2/2/2/2.

## 5. Why Brock Bowers was missed

**Brock Bowers** (`af2cef33-41db-4417-b880-13885bff6921`): eligible=True; historical raw count=0; frozen admitted count=0; expanded raw count=5. Best legal selector **5.481104**, gap **0.125528**, equivalent frozen-205 rank **52**; QB **Trevor Lawrence**, **QB+2+bring-back**, salary **$49,900**.

**Confirmed generation omission:** no historical raw roster contains this player, so admission could not recover it.

Best-roster sources: `player_forced`. All containing sources: `player_forced, stack_partner`. Target admitted counts (205/300/400/500): 1/1/1/3.

## 6. Why Justin Jefferson was missed

**Justin Jefferson** (`37b2e76d-353b-4b03-8a4a-652774647103`): eligible=True; historical raw count=0; frozen admitted count=0; expanded raw count=15. Best legal selector **5.447219**, gap **0.159414**, equivalent frozen-205 rank **82**; QB **Trevor Lawrence**, **QB+2+bring-back**, salary **$49,900**.

**Confirmed generation omission:** no historical raw roster contains this player, so admission could not recover it.

Best-roster sources: `player_forced`. All containing sources: `player_forced, qb_direction, stack_partner`. Target admitted counts (205/300/400/500): 0/1/1/1.

Jefferson retains the frozen elevated-questionable classification. Every new discovery solve limits elevated players to one per roster; admission keeps his 25% candidate cap and portfolio solving keeps his saved selected cap and the elevated-lineup budget.

## 7. Why Jaxon Smith-Njigba was missed

**Jaxon Smith-Njigba** (`1838dd60-35e8-4018-b307-39cde90e1f03`): eligible=True; historical raw count=3; frozen admitted count=0; expanded raw count=15. Best legal selector **5.429477**, gap **0.177156**, equivalent frozen-205 rank **83**; QB **Trevor Lawrence**, **QB+3+bring-back**, salary **$49,900**.

Historical best selector **5.054875**, gap **0.551758**. **Competitive construction was never generated:** weaker containing rosters existed but none was inside 0.20. Their admission rejection does not explain the missing strong construction.

Best-roster sources: `player_forced`. All containing sources: `player_forced, qb_construction:480d4188-7bf6-4684-b2b5-1d47f93d542a:2:1, qb_construction:b0a92b26-91ab-476d-9ef2-9242d9ac62d4:2:1, qb_direction, sequential, stack_partner`. Target admitted counts (205/300/400/500): 0/1/1/2.

QB+3 containing JSN inside 0.20: **1**. The exact triple-stack sweep is a general QB request, not a JSN special case.

## 8. Why Lamar differs

**Lamar Jackson** (`ccab2695-91ed-49ce-b78b-938f23f4739b`): eligible=True; historical raw count=4; frozen admitted count=0; expanded raw count=16. Best legal selector **5.119007**, gap **0.487626**, equivalent frozen-205 rank **200**; QB **Lamar Jackson**, **QB+1+bring-back**, salary **$50,000**.

Historical best selector **5.119007**, gap **0.487626**. Historical construction existed; admission dropped it through target competition. For Lamar its gap exceeds the competitive tolerance.

Best-roster sources: `player_forced, qb_construction:ccab2695-91ed-49ce-b78b-938f23f4739b:1:1, qb_direction, qb_family:ccab2695-91ed-49ce-b78b-938f23f4739b, qb_frontier, stack_partner`. All containing sources: `player_forced, qb_construction:ccab2695-91ed-49ce-b78b-938f23f4739b:1:0, qb_construction:ccab2695-91ed-49ce-b78b-938f23f4739b:1:1, qb_construction:ccab2695-91ed-49ce-b78b-938f23f4739b:2:0, qb_construction:ccab2695-91ed-49ce-b78b-938f23f4739b:2:1, qb_direction, qb_family:ccab2695-91ed-49ce-b78b-938f23f4739b, qb_frontier, stack_partner`. Target admitted counts (205/300/400/500): 0/0/0/0.

A legal Lamar construction is found automatically, but its saved pregame selector is outside 0.30. This is a quality explanation under the frozen model, not evidence that the model is outcome-correct.

## 9. Expanded discovery methodology

Capture the exact saved solver model once in an isolated offline process using a non-solving adapter; restore the adapter before real solves. No production code or frozen code hash changes. Preserve the full pool and normalization denominators. Fix ineligible players to zero. The raw research frontier uses saved salary, roster, team/game limits, DST opposition, tags, locks, starting-QB eligibility, stack minimums, and per-lineup injury control. Aggregate candidate exposure caps apply only after discovery.

Solve one global selector optimum, then partition the legal space by starting QB and enumerate up to **75** optima per direction using exact `sum(selected roster variables) <= 8` cuts. Stop a partition on a proven optimum outside 0.30, proven infeasibility, a safety maximum, or unproven/numerically inconsistent solver behavior. CBC uses one thread and fixed seeds, zero requested relative/absolute gaps, and tighter integer/primal/dual/cutoff tolerances. Each solve has a 30-second safety limit; a feasible incumbent is not accepted as a proof of optimality.

Complementary deterministic sources: all starting QBs × QB+1/2/3 × zero/one bring-back where frozen policy permits; primary/secondary/TE partner combinations up to triples; forced inclusion for pregame position leaders in mean, P90, role, salary value, ownership, and environment, plus underrepresented ceiling leaders; RB/WR FLEX, allowed TE FLEX, TE choices via player sweep, DST price tiers, stars-and-scrubs, and balanced builds. Single-TE policy remains enforced. No strong lineup is removed merely for high overlap.

The player screen uses the union of the top 12 per position for each measurable property, plus the top 24 ceiling players with at most one saved representation. QB probes cover all viable saved starters. Partner sweeps use three role/projection leaders plus a TE when absent. These bounded screens are prospective research hypotheses and still leave unsearched combinations.

Bucky, Bowers, Jefferson, and JSN are recovered by the automatic pregame screen without a manually supplied player list. Their best rosters in this bounded experiment come from the generic player-forced sweep. This does not claim that bounded unforced enumeration alone recovered them.

## 10. Frontier counts at .05/.10/.15/.20/.30

| Tolerance | Known risk-legal lineups | Count status |
| --- | --- | --- |
| 0.05 | 38 | exact |
| 0.10 | 111 | lower_bound |
| 0.15 | 205 | lower_bound |
| 0.20 | 258 | lower_bound |
| 0.30 | 397 | lower_bound |

These counts include the deduplicated union of historical and expanded discoveries. Exactness is certified only if every QB partition has proven exhaustion/boundary or has already crossed the tighter tolerance. A partition safety maximum means the unvisited remainder can contain additional competitive rosters. See the per-QB partition stopping records in the JSON.

## 11. Current pipeline frontier recall

| Tolerance | Normal raw generated / known | Normal generation recall | Frozen admitted / known | Frozen 205 recall |
| --- | --- | --- | --- | --- |
| 0.05 | 20/38 | 52.6% | 20/38 | 52.6% |
| 0.10 | 49/111 | 44.1% | 49/111 | 44.1% |
| 0.15 | 75/205 | 36.6% | 75/205 | 36.6% |
| 0.20 | 84/258 | 32.6% | 84/258 | 32.6% |
| 0.30 | 98/397 | 24.7% | 98/397 | 24.7% |

At 0.20, **174** known competitive lineups were never generated and **0** were generated but not admitted. Of the **174** known misses, generation accounts for **100.0%** and admission for **0.0%**. This decomposition is conditional on the known expanded universe.

## 12. Recall by QB

| Group | 0.05 | 0.10 | 0.15 | 0.20 | 0.30 |
| --- | --- | --- | --- | --- | --- |
| Patrick Mahomes | — | — | — | — | 2/40 (5%) |
| Kirk Cousins | — | — | — | — | 2/6 (33%) |
| Trevor Lawrence | 20/38 (53%) | 47/108 (44%) | 47/133 (35%) | 47/152 (31%) | 51/168 (30%) |
| Josh Allen | — | — | — | — | 1/13 (8%) |
| Jacoby Brissett | — | — | — | 2/23 (9%) | 6/81 (7%) |
| Joe Burrow | — | 2/3 (67%) | 28/72 (39%) | 35/83 (42%) | 36/89 (40%) |

## 13. Recall by game

| Group | 0.05 | 0.10 | 0.15 | 0.20 | 0.30 |
| --- | --- | --- | --- | --- | --- |
| ARI\|NYG | — | — | — | 2/23 (9%) | 6/81 (7%) |
| BUF\|NE | — | — | — | — | 1/13 (8%) |
| CIN\|JAX | 20/38 (53%) | 49/111 (44%) | 75/205 (37%) | 82/235 (35%) | 87/257 (34%) |
| KC\|LV | — | — | — | — | 4/46 (9%) |

## 14. Recall by stack family

| Group | 0.05 | 0.10 | 0.15 | 0.20 | 0.30 |
| --- | --- | --- | --- | --- | --- |
| Patrick Mahomes QB+2 BB0 | — | — | — | — | 1/37 (3%) |
| Patrick Mahomes QB+2 BB1 | — | — | — | — | 1/2 (50%) |
| Patrick Mahomes QB+3 BB0 | — | — | — | — | 0/1 (0%) |
| Kirk Cousins QB+2 BB0 | — | — | — | — | 1/1 (100%) |
| Kirk Cousins QB+2 BB1 | — | — | — | — | 1/5 (20%) |
| Trevor Lawrence QB+1 BB0 | — | — | — | — | 1/1 (100%) |
| Trevor Lawrence QB+1 BB1 | — | — | — | — | 3/4 (75%) |
| Trevor Lawrence QB+2 BB0 | — | — | — | 0/3 (0%) | 0/5 (0%) |
| Trevor Lawrence QB+2 BB1 | 17/29 (59%) | 40/93 (43%) | 40/116 (34%) | 40/128 (31%) | 40/135 (30%) |
| Trevor Lawrence QB+3 BB0 | — | — | — | 0/2 (0%) | 0/4 (0%) |
| Trevor Lawrence QB+3 BB1 | 3/9 (33%) | 7/15 (47%) | 7/17 (41%) | 7/19 (37%) | 7/19 (37%) |
| Josh Allen QB+2 BB0 | — | — | — | — | 1/11 (9%) |
| Josh Allen QB+3 BB0 | — | — | — | — | 0/2 (0%) |
| Jacoby Brissett QB+1 BB0 | — | — | — | — | 1/2 (50%) |
| Jacoby Brissett QB+2 BB0 | — | — | — | 2/23 (9%) | 4/77 (5%) |
| Jacoby Brissett QB+2 BB1 | — | — | — | — | 1/1 (100%) |
| Jacoby Brissett QB+3 BB0 | — | — | — | — | 0/1 (0%) |
| Joe Burrow QB+1 BB1 | — | — | — | — | 1/3 (33%) |
| Joe Burrow QB+2 BB0 | — | — | — | — | 0/3 (0%) |
| Joe Burrow QB+2 BB1 | — | 2/3 (67%) | 28/72 (39%) | 35/81 (43%) | 35/81 (43%) |
| Joe Burrow QB+3 BB1 | — | — | — | 0/2 (0%) | 0/2 (0%) |

## 15. Recall by player

| Group | 0.05 | 0.10 | 0.15 | 0.20 | 0.30 |
| --- | --- | --- | --- | --- | --- |
| Caleb Douglas | 3/5 (60%) | 4/7 (57%) | 7/10 (70%) | 11/18 (61%) | 12/24 (50%) |
| Erick All Jr. | — | — | 1/1 (100%) | 2/2 (100%) | 2/2 (100%) |
| Drew Sample | — | — | 7/11 (64%) | 9/14 (64%) | 9/14 (64%) |
| Ashton Jeanty | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Buccaneers | — | 0/1 (0%) | 1/2 (50%) | 1/2 (50%) | 1/2 (50%) |
| Chase Brown | 20/38 (53%) | 47/108 (44%) | 73/202 (36%) | 81/247 (33%) | 93/380 (24%) |
| Jeremiyah Love | — | — | — | — | 0/1 (0%) |
| Jake Ferguson | — | — | — | 0/1 (0%) | 0/1 (0%) |
| Bengals | — | — | — | — | 0/1 (0%) |
| Isaiah Williams | — | — | 1/1 (100%) | 1/1 (100%) | 1/3 (33%) |
| Jaxon Smith-Njigba | — | — | — | 0/1 (0%) | 0/1 (0%) |
| Tee Higgins | 1/1 (100%) | 9/19 (47%) | 25/81 (31%) | 28/88 (32%) | 29/91 (32%) |
| Tony Pollard | — | — | — | 0/1 (0%) | 0/1 (0%) |
| Dolphins | 11/16 (69%) | 26/49 (53%) | 42/93 (45%) | 48/124 (39%) | 61/187 (33%) |
| Cade Otton | 2/5 (40%) | 5/10 (50%) | 8/27 (30%) | 9/30 (30%) | 11/38 (29%) |
| Dalton Schultz | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Elic Ayomanor | — | 0/1 (0%) | 3/12 (25%) | 4/21 (19%) | 6/50 (12%) |
| Saquon Barkley | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Mason Taylor | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Brian Thomas Jr. | 5/14 (36%) | 10/23 (43%) | 10/29 (34%) | 10/36 (28%) | 10/42 (24%) |
| Cowboys | — | 0/1 (0%) | 0/2 (0%) | 0/2 (0%) | 0/2 (0%) |
| Seahawks | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Chargers | 1/5 (20%) | 3/11 (27%) | 3/19 (16%) | 3/23 (13%) | 3/38 (8%) |
| Michael Mayer | — | 0/1 (0%) | 0/2 (0%) | 0/2 (0%) | 2/8 (25%) |
| Kyren Williams | 15/30 (50%) | 32/80 (40%) | 51/152 (34%) | 57/193 (30%) | 66/288 (23%) |
| Christian Watson | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Kenyon Sadiq | — | — | — | — | 0/1 (0%) |
| Justin Jefferson | — | — | — | 0/1 (0%) | 0/1 (0%) |
| Patrick Mahomes | — | — | — | — | 2/40 (5%) |
| Ted Hurst III | — | — | 1/1 (100%) | 1/3 (33%) | 1/9 (11%) |
| Kirk Cousins | — | — | — | — | 2/6 (33%) |
| Zach Ertz | — | 1/1 (100%) | 4/8 (50%) | 4/8 (50%) | 6/13 (46%) |
| Texans | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Reggie Virgil | — | — | — | — | 0/1 (0%) |
| Nico Collins | — | — | — | — | 0/1 (0%) |
| Packers | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) | 0/3 (0%) |
| Derrick Henry | 2/3 (67%) | 10/20 (50%) | 11/26 (42%) | 13/38 (34%) | 17/66 (26%) |
| Gunnar Helm | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Kenneth Walker III | 12/22 (55%) | 20/43 (47%) | 24/60 (40%) | 27/78 (35%) | 37/158 (23%) |
| Devin Singletary | — | — | — | — | 1/1 (100%) |
| Aaron Jones Sr. | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Hunter Henry | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Cam Skattebo | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Mike Gesicki | — | — | 5/8 (62%) | 6/10 (60%) | 6/13 (46%) |
| Giants | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Travis Kelce | 4/6 (67%) | 7/10 (70%) | 11/21 (52%) | 11/23 (48%) | 13/64 (20%) |
| Patriots | 0/2 (0%) | 1/6 (17%) | 1/13 (8%) | 1/16 (6%) | 1/25 (4%) |
| Ryan Flournoy | — | 0/1 (0%) | 2/3 (67%) | 2/3 (67%) | 2/3 (67%) |
| Cooper Kupp | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/4 (25%) |
| Parker Washington | 20/38 (53%) | 49/111 (44%) | 75/204 (37%) | 82/247 (33%) | 94/357 (26%) |
| Bills | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) | 0/3 (0%) |
| Jaguars | — | — | — | 0/1 (0%) | 0/1 (0%) |
| Colby Parkinson | 1/2 (50%) | 2/4 (50%) | 4/14 (29%) | 5/16 (31%) | 7/18 (39%) |
| D'Andre Swift | — | 2/2 (100%) | 5/6 (83%) | 6/7 (86%) | 6/8 (75%) |
| Kenny Gainwell | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Bhayshul Tuten | — | — | — | — | 0/1 (0%) |
| Davante Adams | — | — | — | — | 0/1 (0%) |
| AJ Barner | — | 0/1 (0%) | 0/2 (0%) | 0/2 (0%) | 0/2 (0%) |
| James Cook III | 1/2 (50%) | 4/5 (80%) | 7/8 (88%) | 7/8 (88%) | 7/14 (50%) |
| Mark Andrews | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Javonte Williams | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Tucker Kraft | — | — | — | 0/1 (0%) | 0/1 (0%) |
| Chris Godwin Jr. | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Woody Marks | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Breece Hall | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Titans | 4/11 (36%) | 8/18 (44%) | 11/29 (38%) | 13/36 (36%) | 13/50 (26%) |
| Colston Loveland | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Jets | 1/1 (100%) | 4/6 (67%) | 6/13 (46%) | 6/15 (40%) | 6/24 (25%) |
| Puka Nacua | 9/21 (43%) | 14/39 (36%) | 18/55 (33%) | 19/74 (26%) | 26/130 (20%) |
| Greg Dulcich | — | — | — | 0/1 (0%) | 0/1 (0%) |
| Raiders | — | 1/3 (33%) | 1/6 (17%) | 1/7 (14%) | 1/9 (11%) |
| Bucky Irving | — | 0/1 (0%) | 0/2 (0%) | 0/2 (0%) | 0/2 (0%) |
| Kyle Monangai | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Carnell Tate | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Xavier Worthy | — | — | — | — | 2/40 (5%) |
| Broncos | — | 0/2 (0%) | 0/5 (0%) | 0/5 (0%) | 0/10 (0%) |
| Rashee Rice | — | — | 0/1 (0%) | 0/1 (0%) | 0/2 (0%) |
| Brock Bowers | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Trevor Lawrence | 20/38 (53%) | 47/108 (44%) | 47/133 (35%) | 47/152 (31%) | 51/168 (30%) |
| David Montgomery | — | — | — | 0/1 (0%) | 0/1 (0%) |
| Mack Hollins | 1/2 (50%) | 1/2 (50%) | 1/2 (50%) | 1/2 (50%) | 1/7 (14%) |
| Garrett Wilson | — | — | — | 0/1 (0%) | 0/1 (0%) |
| DeVonta Smith | — | — | — | 0/1 (0%) | 0/1 (0%) |
| Josh Allen | — | — | — | — | 1/13 (8%) |
| Khalil Shakir | — | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1/13 (8%) |
| Cole Kmet | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Travis Hunter | 4/6 (67%) | 11/23 (48%) | 11/28 (39%) | 12/33 (36%) | 13/43 (30%) |
| Keon Coleman | — | — | — | — | 0/1 (0%) |
| Rhamondre Stevenson | 2/4 (50%) | 7/13 (54%) | 14/37 (38%) | 17/44 (39%) | 19/54 (35%) |
| Tre Tucker | — | — | 0/1 (0%) | 0/1 (0%) | 3/9 (33%) |
| Vikings | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Isaiah Likely | — | — | — | 0/1 (0%) | 0/1 (0%) |
| Jack Endries | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Omarion Hampton | — | — | — | — | 0/1 (0%) |
| Michael Wilson | 5/7 (71%) | 19/47 (40%) | 24/77 (31%) | 29/113 (26%) | 39/201 (19%) |
| Wan'Dale Robinson | 3/5 (60%) | 8/15 (53%) | 16/35 (46%) | 16/44 (36%) | 18/66 (27%) |
| Brenton Strange | 13/25 (52%) | 29/70 (41%) | 29/85 (34%) | 29/97 (30%) | 29/107 (27%) |
| Trey McBride | — | 5/12 (42%) | 5/12 (42%) | 8/36 (22%) | 11/94 (12%) |
| Bears | — | 0/1 (0%) | 1/2 (50%) | 1/2 (50%) | 1/3 (33%) |
| T.J. Hockenson | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Ravens | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Jauan Jennings | — | 1/6 (17%) | 1/6 (17%) | 1/6 (17%) | 1/14 (7%) |
| Jakobi Meyers | 1/2 (50%) | 4/7 (57%) | 4/9 (44%) | 4/13 (31%) | 4/16 (25%) |
| Jacoby Brissett | — | — | — | 2/23 (9%) | 6/81 (7%) |
| CeeDee Lamb | — | — | — | 0/1 (0%) | 0/1 (0%) |
| Zay Flowers | 1/1 (100%) | 7/12 (58%) | 8/14 (57%) | 9/26 (35%) | 12/53 (23%) |
| Joe Burrow | — | 2/3 (67%) | 28/72 (39%) | 35/83 (42%) | 36/89 (40%) |
| Cardinals | — | 1/3 (33%) | 4/6 (67%) | 4/6 (67%) | 4/15 (27%) |
| Chiefs | — | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |
| Ja'Marr Chase | 14/26 (54%) | 33/75 (44%) | 56/152 (37%) | 63/176 (36%) | 64/193 (33%) |
| J.K. Dobbins | — | — | — | 0/1 (0%) | 0/1 (0%) |
| Dalton Kincaid | — | 0/1 (0%) | 1/4 (25%) | 1/4 (25%) | 2/9 (22%) |
| RJ Harvey | — | 0/1 (0%) | 0/1 (0%) | 1/2 (50%) | 1/3 (33%) |
| Rams | 3/3 (100%) | 5/5 (100%) | 5/6 (83%) | 6/10 (60%) | 7/17 (41%) |
| DJ Moore | — | — | 0/1 (0%) | 0/1 (0%) | 1/11 (9%) |
| Eagles | — | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |

The same grouped diagnostic is also stored by position, player salary tier (cheap ≤4000; star ≥7500; middle otherwise), and frozen role class. Each denominator counts rosters containing that group once; group membership is not mutually exclusive. Unclassified roles remain unclassified.

**position**

| Group | 0.20 admitted / known |
| --- | --- |
| DST | 84/258 |
| QB | 84/258 |
| RB | 84/258 |
| TE | 84/258 |
| WR | 84/258 |

**salary_tier**

| Group | 0.20 admitted / known |
| --- | --- |
| cheap | 84/258 |
| middle | 84/258 |
| star | 83/257 |

**role_class**

| Group | 0.20 admitted / known |
| --- | --- |
| unclassified | 84/258 |

## 16. Player coverage gaps

**37 warnings:** a known raw construction exists within 0.20, but the frozen admitted pool has zero representation.

| Player | Raw count | Admitted | Best raw | Equivalent rank | Mean/P90 | Role score | Salary | Reduction reasons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Jake Ferguson | 15 | 0 | 5.410 | 84 | 6.5/11.1 | 0.000 | 4300 | {"admission_target_competition": 15} |
| Jaxon Smith-Njigba | 15 | 0 | 5.429 | 83 | 20.0/32.8 | 0.000 | 9100 | {"admission_target_competition": 15} |
| Tony Pollard | 1 | 0 | 5.443 | 83 | 10.0/18.1 | 0.000 | 5400 | {"admission_target_competition": 1} |
| Saquon Barkley | 4 | 0 | 5.484 | 51 | 13.5/24.9 | 0.000 | 6800 | {"admission_target_competition": 3, "injury_risk_rejected": 1} |
| Mason Taylor | 7 | 0 | 5.480 | 52 | 5.2/12.3 | 0.000 | 2500 | {"admission_target_competition": 5, "injury_risk_rejected": 2} |
| Cowboys | 3 | 0 | 5.533 | 48 | 4.3/11.0 | 0.000 | 2700 | {"admission_target_competition": 3} |
| Seahawks | 1 | 0 | 5.495 | 50 | 5.4/12.2 | 0.000 | 3500 | {"admission_target_competition": 1} |
| Justin Jefferson | 15 | 0 | 5.447 | 82 | 14.3/27.2 | 0.000 | 7300 | {"admission_target_competition": 15} |
| Texans | 1 | 0 | 5.507 | 50 | 4.4/11.1 | 0.000 | 2900 | {"admission_target_competition": 1} |
| Gunnar Helm | 15 | 0 | 5.468 | 59 | 4.9/12.0 | 0.000 | 2800 | {"admission_target_competition": 15} |
| Aaron Jones Sr. | 5 | 0 | 5.496 | 50 | 11.9/23.3 | 0.000 | 6000 | {"admission_target_competition": 5} |
| Cam Skattebo | 2 | 0 | 5.510 | 50 | 14.6/22.6 | 0.000 | 6100 | {"admission_target_competition": 2} |
| Jaguars | 1 | 0 | 5.412 | 84 | 4.3/11.0 | 0.000 | 2600 | {"admission_target_competition": 1} |
| Kenny Gainwell | 1 | 0 | 5.483 | 51 | 8.8/16.8 | 0.000 | 4700 | {"admission_target_competition": 1} |
| Mark Andrews | 10 | 0 | 5.464 | 61 | 7.3/14.4 | 0.000 | 4200 | {"admission_target_competition": 10} |
| Javonte Williams | 1 | 0 | 5.498 | 50 | 13.7/25.1 | 0.000 | 6600 | {"admission_target_competition": 1} |
| Tucker Kraft | 9 | 0 | 5.432 | 83 | 7.8/14.9 | 0.000 | 4400 | {"admission_target_competition": 9} |
| Chris Godwin Jr. | 11 | 0 | 5.489 | 51 | 9.2/20.3 | 0.000 | 4900 | {"admission_target_competition": 11} |
| Woody Marks | 1 | 0 | 5.484 | 51 | 8.3/16.3 | 0.000 | 4700 | {"admission_target_competition": 1} |
| Breece Hall | 1 | 0 | 5.478 | 52 | 14.0/22.1 | 0.000 | 6200 | {"admission_target_competition": 1} |
| Colston Loveland | 1 | 0 | 5.482 | 51 | 9.1/17.4 | 0.000 | 4700 | {"admission_target_competition": 1} |
| Greg Dulcich | 11 | 0 | 5.443 | 83 | 5.7/12.8 | 0.000 | 3200 | {"admission_target_competition": 11} |
| Bucky Irving | 4 | 0 | 5.530 | 48 | 13.0/26.1 | 0.000 | 6000 | {"admission_target_competition": 4} |
| Kyle Monangai | 1 | 0 | 5.462 | 65 | 9.4/17.4 | 0.000 | 4900 | {"admission_target_competition": 1} |
| Carnell Tate | 16 | 0 | 5.547 | 33 | 8.5/21.3 | 0.000 | 4800 | {"admission_target_competition": 16} |
| Brock Bowers | 5 | 0 | 5.481 | 52 | 15.5/24.7 | 0.000 | 6900 | {"admission_target_competition": 5} |
| David Montgomery | 1 | 0 | 5.426 | 83 | 10.3/18.4 | 0.000 | 5700 | {"admission_target_competition": 1} |
| Garrett Wilson | 17 | 0 | 5.429 | 83 | 12.3/22.1 | 0.000 | 6800 | {"admission_target_competition": 17} |
| DeVonta Smith | 10 | 0 | 5.418 | 84 | 12.8/25.6 | 0.000 | 7100 | {"admission_target_competition": 10} |
| Cole Kmet | 1 | 0 | 5.463 | 64 | 4.7/11.8 | 0.000 | 2800 | {"admission_target_competition": 1} |
| Vikings | 7 | 0 | 5.485 | 51 | 5.5/12.2 | 0.000 | 4000 | {"admission_target_competition": 7} |
| Isaiah Likely | 12 | 0 | 5.457 | 76 | 8.7/15.8 | 0.000 | 4500 | {"admission_target_competition": 12} |
| Jack Endries | 1 | 0 | 5.458 | 76 | 1.8/8.2 | 0.000 | 2500 | {"admission_target_competition": 1} |
| T.J. Hockenson | 18 | 0 | 5.501 | 50 | 7.7/14.8 | 0.000 | 3300 | {"admission_target_competition": 16, "injury_risk_rejected": 2} |
| CeeDee Lamb | 17 | 0 | 5.409 | 85 | 15.7/25.6 | 0.000 | 7800 | {"admission_target_competition": 17} |
| J.K. Dobbins | 1 | 0 | 5.408 | 85 | 8.4/16.4 | 0.000 | 5300 | {"admission_target_competition": 1} |
| Eagles | 1 | 0 | 5.522 | 49 | 4.3/11.0 | 0.000 | 2700 | {"admission_target_competition": 1} |

The full [player audit CSV](artifacts/candidate_completeness/week4-player-coverage.csv) includes every frozen player, eligibility, raw frontier/total counts, admitted counts, best raw/admitted selectors, equivalent frozen rank, known-reference rank, mean/P90, role label/score, salary, and reduction reasons. Missing role labels are not inferred from name recognition.

For the frozen 205 comparison, expanded raw→saved-pool reasons describe a counterfactual insertion/displacement against the frozen pool. They are not claims that the historical pipeline requested or rejected newly discovered rosters. The historical 286 ledger is the actual generation/admission reconstruction; section 11 separates never-generated misses from admitted misses.

## 17. QB coverage gaps

| Starting QB | Game | Best legal | Equivalent rank | Raw within .05/.10/.15/.20/.30 | Admitted | Mean/P90 | Salary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Bo Nix | DEN\|SF | 5.234 | 156 | 0/0/0/0/0 | 2 | 16.8/27.5 | 5600 |
| Dak Prescott | DAL\|HOU | 5.186 | 177 | 0/0/0/0/0 | 0 | 15.7/26.6 | 6400 |
| Matthew Stafford | LAR\|PHI | 5.260 | 92 | 0/0/0/0/2 | 2 | 16.7/27.6 | 6200 |
| Patrick Mahomes | KC\|LV | 5.358 | 90 | 0/0/0/0/40 | 38 | 18.6/29.5 | 6500 |
| Kirk Cousins | KC\|LV | 5.342 | 93 | 0/0/0/0/6 | 4 | 14.9/25.5 | 5100 |
| Malik Willis | MIA\|MIN | 5.137 | 182 | 0/0/0/0/0 | 0 | 12.5/23.1 | 4900 |
| Sam Darnold | LAC\|SEA | 5.178 | 179 | 0/0/0/0/0 | 7 | 13.4/24.4 | 5500 |
| C.J. Stroud | DAL\|HOU | 5.285 | 113 | 0/0/0/0/0 | 7 | 16.0/26.9 | 5700 |
| Cam Ward | BAL\|TEN | 5.150 | 188 | 0/0/0/0/0 | 1 | 10.1/21.0 | 4700 |
| Drake Maye | BUF\|NE | 5.200 | 173 | 0/0/0/0/0 | 5 | 15.0/25.6 | 6000 |
| Jalen Hurts | LAR\|PHI | 5.169 | 181 | 0/0/0/0/0 | 2 | 16.5/27.2 | 6600 |
| Geno Smith | CHI\|NYJ | 5.101 | 200 | 0/0/0/0/0 | 0 | 10.8/21.4 | 5200 |
| Trevor Lawrence | CIN\|JAX | 5.607 | 1 | 38/108/133/153/169 | 51 | 19.5/30.4 | 5900 |
| Jalon Daniels | GB\|TB | 5.061 | 205 | 0/0/0/0/0 | 0 | 5.9/16.8 | 4400 |
| Justin Herbert | LAC\|SEA | 5.096 | 200 | 0/0/0/0/0 | 0 | 13.8/24.5 | 5400 |
| Josh Allen | BUF\|NE | 5.330 | 97 | 0/0/0/0/13 | 14 | 22.5/33.1 | 7700 |
| Kyler Murray | MIA\|MIN | 5.083 | 201 | 0/0/0/0/0 | 0 | 11.2/22.1 | 5300 |
| Lamar Jackson | BAL\|TEN | 5.119 | 200 | 0/0/0/0/0 | 0 | 16.9/27.6 | 7300 |
| Jameis Winston | ARI\|NYG | 5.214 | 165 | 0/0/0/0/0 | 21 | 12.7/23.6 | 4500 |
| Jordan Love | GB\|TB | 5.227 | 158 | 0/0/0/0/0 | 4 | 18.8/29.7 | 5800 |
| Jacoby Brissett | ARI\|NYG | 5.426 | 83 | 0/0/0/23/81 | 10 | 16.4/27.3 | 5000 |
| Joe Burrow | CIN\|JAX | 5.529 | 48 | 0/3/72/83/90 | 37 | 19.7/30.6 | 6800 |

Discovered exact stack families for every QB are retained in the [QB audit CSV](artifacts/candidate_completeness/week4-qb-coverage.csv). “Best legal” is the best proven construction found; an unproven request does not establish weakness.

## 18. 205 vs 300 vs 400 vs 500

All four targets admit from the identical expanded raw universe using the unchanged cardinality-first, selector-second joint admission and frozen caps. Generation cost is shared, so this is an admission sensitivity, not four independently generated universes. There is no refill or target-specific discovery.

| Target | Admitted | Recall .05/.10/.15/.20/.30 | Players | QBs | Games | Families | Mean overlap | Max exposure | QB HHI | Median selector | Admission seconds | Warnings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 205 | 205 | 100.0%/99.1%/86.3%/74.8%/49.9% | 78 | 3 | 2 | 8 | 4.311 | 89.8% | 0.521 | 5.522 | 0.967 | 24 |
| 300 | 300 | 100.0%/100.0%/100.0%/97.7%/72.3% | 109 | 5 | 4 | 14 | 4.124 | 90.0% | 0.402 | 5.475 | 0.794 | 0 |
| 400 | 400 | 100.0%/100.0%/100.0%/100.0%/91.9% | 123 | 10 | 6 | 28 | 3.846 | 90.0% | 0.284 | 5.459 | 0.804 | 0 |
| 500 | 500 | 100.0%/100.0%/100.0%/100.0%/97.0% | 141 | 18 | 12 | 56 | 3.596 | 90.0% | 0.203 | 5.410 | 0.793 | 0 |

Selector max/min/mean/median, exact roster duplication, all primary rejection counts, player/QB coverage, thesis depth, lineage runtime, and downstream five/twenty portfolios are retained for every target. Duplication in each admitted pool is zero. Serialization cost per admitted candidate is approximated below; it is not the solver working set.

**Smallest tested target recommendation: 400**, using explicit research acceptance criteria: at least 95% known roster recall inside 0.20, zero near-frontier player warnings, all qualified inside-0.20 direction/game/families, the same optimal saved-user-policy five-entry selector sum as the expanded universe, and the same expanded twenty-entry thesis allocation. Target 300 reaches 97.7% recall and zero player warnings, but loses the user-policy five-entry optimum (26.991746 versus 27.202641). Target 400 preserves it and the twenty-entry allocation. Target 500 adds wider 0.30 recall, without changing those portfolio results. This is the smallest of the four tested targets, not a proof that every intermediate target below 400 fails.

The expanded raw universe retains the exact canonical roster set of the best saved-user-policy five. Targets 400 and 500 attain the same optimal selector sum with alternative tied roster sets. Target 205 from the improved raw universe has only three QB directions, so it cannot satisfy the saved five-distinct-QB user contract. Target 300 is feasible but drops necessary weaker-QB alternatives and lowers the optimum. This shows why frontier recall alone is insufficient for admission research.

## 19. Search saturation curve

Requests are reduced in declared source/canonical-ID order after parallel solving. This curve is reproducible for a pinned solver build; it is not wall-clock completion order. Counts include unique legal candidates even when a terminal frontier-boundary probe falls outside the enumeration window.

| Solves | New unique | New players | New QBs | New families | New games | New within .05/.10/.15/.20 | Best new selector |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 50 | 50 | 36 | 6 | 9 | 5 | 1/1/1/1 | 5.607 |
| 100 | 49 | 22 | 7 | 8 | 5 | 37/40/40/40 | 5.593 |
| 150 | 50 | 12 | 3 | 4 | 1 | 0/34/34/34 | 5.555 |
| 200 | 50 | 11 | 5 | 5 | 1 | 0/0/0/23 | 5.426 |
| 250 | 50 | 3 | 1 | 1 | 0 | 0/3/21/21 | 5.529 |
| 300 | 50 | 6 | 0 | 0 | 0 | 0/0/50/50 | 5.475 |
| 350 | 26 | 9 | 0 | 7 | 0 | 0/0/1/4 | 5.457 |
| 400 | 36 | 6 | 0 | 8 | 0 | 0/0/0/0 | 5.289 |
| 450 | 30 | 7 | 0 | 9 | 0 | 0/0/0/0 | 5.297 |
| 500 | 33 | 4 | 0 | 15 | 0 | 0/0/0/0 | 5.282 |
| 550 | 38 | 4 | 0 | 8 | 0 | 0/0/0/0 | 5.197 |
| 600 | 42 | 6 | 0 | 7 | 0 | 0/0/0/0 | 5.081 |
| 650 | 37 | 3 | 0 | 9 | 0 | 0/2/4/10 | 5.540 |
| 700 | 45 | 3 | 0 | 9 | 0 | 0/0/0/0 | 5.296 |
| 750 | 35 | 6 | 0 | 10 | 0 | 0/0/0/0 | 5.295 |
| 800 | 42 | 5 | 0 | 10 | 0 | 0/0/0/0 | 5.226 |
| 850 | 35 | 7 | 0 | 10 | 0 | 0/1/2/5 | 5.539 |
| 900 | 27 | 6 | 0 | 0 | 0 | 0/11/19/23 | 5.541 |
| 950 | 24 | 9 | 0 | 0 | 0 | 0/3/16/23 | 5.542 |
| 963 | 5 | 2 | 0 | 0 | 0 | 0/3/4/5 | 5.524 |

## 20. Proposed dynamic stopping rule

The exploratory quiet-block detector first fires at solve **450**: no new unique construction inside 0.20 for two complete 50-solve blocks. This is a diagnostic only. An ordered QB batch can be quiet before a later stack/player sweep finds new information; this trigger must not prematurely stop mandatory source coverage.

Proposed promotion research: finish all viable QB/template probes, pregame player coverage probes, and structural sources; then continue incremental exact frontier/partner enumeration until two consecutive 50-solve blocks add no inside-0.20 candidates, players, viable QB/families, or games, with stable grouped coverage and known-reference recall; stop at a predeclared runtime/solve safety limit. Mark safety-limited runs incomplete and expose coverage warnings. Measure a holdout sweep before trusting saturation. No stopping rule is promoted here.

A flat empirical curve cannot prove completeness of unexplored legal space. Raw roster recall and meaningful directional diversity are separate targets; a fixed admitted count cannot establish either.

**Saturation was not reached.** Although the naive detector fires at 450, the final blocks ending at 850/900/950/963 add 56 further unique inside-0.20 candidates. Mandatory automatic player coverage probes arrive late in the declared schedule. This is direct evidence that quiet blocks alone would stop this slate too early.

## 21. Runtime / cost

| Measurement | Value |
| --- | --- |
| baseline_seed_rosters_match | True |
| children_peak_rss_native_units | 575389696 |
| current_saved_joint_admission_seconds | 0.323 |
| current_seed_replay_seconds | 257.697 |
| expanded_discovery_seconds | 5.904 |
| historical_lineage_seconds | 0.005 |
| model_build_seconds | 3.109 |
| original_expanded_discovery_seconds | 265.294 |
| parent_peak_rss_native_units | 471973888 |
| total_seconds | 26.312 |

| Source | Solves | Sum solver CPU/wall seconds across workers |
| --- | --- | --- |
| global_frontier | 1 | 2.120 |
| player_forced | 114 | 180.063 |
| qb_direction | 132 | 62.994 |
| qb_frontier | 303 | 600.485 |
| stack_partner | 406 | 138.127 |
| structure:balanced | 1 | 1.451 |
| structure:dst:0:2500 | 1 | 1.901 |
| structure:dst:2500:3500 | 1 | 2.587 |
| structure:dst:3500:6000 | 1 | 2.150 |
| structure:flex:RB | 1 | 2.377 |
| structure:flex:WR | 1 | 2.000 |
| structure:stars_scrubs | 1 | 1.649 |

Raw serialized candidates: **4,220,437 bytes**; average **4,689 bytes/candidate**. Approximate serialized pool costs at 300/400/500: 1.41 MB/1.88 MB/2.34 MB.

On this macOS host, `ru_maxrss` native units are bytes. Parent and child maxima are separately reported; a child maximum is not the simultaneous total of all four workers. JSON size is a storage proxy, not peak solver RAM. There is no metered cloud-compute charge or external API call in this experiment.

The original frozen production full run took **347.6 seconds**, including its prospective shadow (existing README/RELEASE_NOTES record). Its seed generation was independently replayed here in **257.7 seconds** with all 205 raw seed rosters matching exactly. Fresh expanded discovery took **265.3 seconds** on four processes; exact QB enumeration consumed **600.5 summed worker-seconds** and automatic player-forced probes **180.1 summed worker-seconds**. The initial complete experiment, including baseline replay and portfolio diagnostics, took **543.7 seconds**. The final artifact re-analyzes those immutable solve events to add the complete stage trace and keeps the original solve code hashes, evidence hash, and timings separate from re-analysis timings.

The initial global benchmark took roughly 2–5 seconds per fresh solve. Exhaustive frontier cost scales with the unknown roster count and growing cut set; bounded exact QB partitions plus deterministic complementary requests are the implemented practical alternative. Direction/partner/player requests and disjoint QB partitions are safely parallelizable in processes. Within a partition, enumeration is sequential. Admission remains a joint optimization. Fixed candidate targets reuse the same generation cost; their incremental costs are measured admission and portfolio solve time, not an invented linear generation estimate.

Deterministic reproduction requires identical frozen inputs/code, canonical order, CBC build/backend, one solver thread, fixed seeds, and declared result reduction order. A different backend or CBC version may choose a different tied optimum. Repeated actual solver tests verify canonical roster sequences on a small legal fixture; all full experiment input/code hashes are retained. Original seed replay equality is separately reported; a mismatch would limit interpretation of its runtime benchmark.

## 22. Thesis analysis: current vs expanded universe

The existing dynamic v3 thesis grouping, depth, Pareto screen, and lexicographic allocation are reused. Research thesis portfolios retain their existing overlap hypotheses (6 for five, then 6/7/8 for twenty) and at least two QB paths. A separate five-entry sensitivity below keeps the saved user overlap=4 and distinct-QB-path=true. Neither replaces production.

| Universe | Qualified families .20 | Pareto-frontier families .20 | QB directions .20 | Games .20 |
| --- | --- | --- | --- | --- |
| current | 4 | 2 | 3 | 2 |
| expanded | 7 | 3 | 3 | 2 |
| target_205 | 7 | 3 | 3 | 2 |
| target_300 | 7 | 3 | 3 | 2 |
| target_400 | 7 | 3 | 3 | 2 |
| target_500 | 7 | 3 | 3 | 2 |

New qualified families inside 0.20:

| QB | Game | Stack | Bring-back | Peak selector | Frontier gap | Depth within .20 |
| --- | --- | --- | --- | --- | --- | --- |
| Trevor Lawrence | JAX@CIN | QB+3 | False | 5.454 | 0.152 | 2 |
| Joe Burrow | JAX@CIN | QB+3 | True | 5.441 | 0.165 | 2 |
| Trevor Lawrence | JAX@CIN | QB+2 | False | 5.435 | 0.172 | 3 |

## 23. Five-entry shadow comparison

| Universe | Status | Entries | Selector sum | Mean sum | P90 sum | Tolerance | Overlap cap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| current | optimal | 5 | 27.688 | 649.227 | 1131.943 | 0.2 | 6 |
| expanded | optimal | 5 | 27.644 | 644.619 | 1121.173 | 0.15 | 6 |
| target_205 | optimal | 5 | 27.644 | 644.619 | 1121.173 | 0.15 | 6 |
| target_300 | optimal | 5 | 27.644 | 644.619 | 1121.173 | 0.15 | 6 |
| target_400 | optimal | 5 | 27.644 | 644.619 | 1121.173 | 0.15 | 6 |
| target_500 | optimal | 5 | 27.644 | 644.619 | 1121.173 | 0.15 | 6 |

**current allocation:** `{"ARI|NYG|e6f98d37-a335-4ae4-b58f-29c8ab1d106e|QB+2|BB0": 1, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+2|BB1": 2, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+3|BB1": 1, "CIN|JAX|eed8fc95-3591-4fa6-b7e6-4abb70a2885d|QB+2|BB1": 1}`

| Rank in this universe | QB | Game | Stack | Selector | Canonical roster |
| --- | --- | --- | --- | --- | --- |
| 1 | Trevor Lawrence | JAX@CIN | QB+2 | 5.607 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 6b49e50c-7ccb-40be-ab23-c836128c4ad3, 734de5e7-0dc0-4ded-8156-c4a0e9093012, a7d14336-632e-48c8-b0c1-45916b8476e4, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, c3d96a00-5572-4861-ac7a-2f6670a41525, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 6 | Trevor Lawrence | JAX@CIN | QB+2 | 5.578 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 1f90d290-afb4-48ae-8052-fa99040b8ddb, 2af6b6cb-8b3d-4895-9936-f22a63104487, 5169c450-ece6-4729-8952-ba040d3f64f2, 734de5e7-0dc0-4ded-8156-c4a0e9093012, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 31 | Trevor Lawrence | JAX@CIN | QB+3 | 5.548 | 2af6b6cb-8b3d-4895-9936-f22a63104487, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 5169c450-ece6-4729-8952-ba040d3f64f2, 734de5e7-0dc0-4ded-8156-c4a0e9093012, a3288879-cfb6-481c-89a0-131b2933754b, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, ddb43b49-94bf-4c9c-b875-99a2d8313797, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 48 | Joe Burrow | JAX@CIN | QB+2 | 5.529 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1bc5ea87-e6bb-4608-a110-2b657344f1ed, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 734de5e7-0dc0-4ded-8156-c4a0e9093012, 75ce51c3-50e5-41b2-b91f-25f0e54deefe, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, eed8fc95-3591-4fa6-b7e6-4abb70a2885d, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 83 | Jacoby Brissett | ARI@NYG | QB+2 | 5.426 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 223401ce-ee23-4964-a875-58c4ef414bb3, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 48932b42-a60a-4070-82a7-50475f27bbf2, a7d14336-632e-48c8-b0c1-45916b8476e4, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, e1116ce1-4b11-40ab-ad64-16d7479df145, e6f98d37-a335-4ae4-b58f-29c8ab1d106e |

**expanded allocation:** `{"CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+2|BB1": 2, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+3|BB1": 1, "CIN|JAX|eed8fc95-3591-4fa6-b7e6-4abb70a2885d|QB+2|BB1": 2}`

| Rank in this universe | QB | Game | Stack | Selector | Canonical roster |
| --- | --- | --- | --- | --- | --- |
| 9 | Trevor Lawrence | JAX@CIN | QB+2 | 5.580 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 734de5e7-0dc0-4ded-8156-c4a0e9093012, a7d14336-632e-48c8-b0c1-45916b8476e4, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, c706298f-d5e9-441e-83fa-71b468ddc5a4, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, ddb43b49-94bf-4c9c-b875-99a2d8313797, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 61 | Trevor Lawrence | JAX@CIN | QB+3 | 5.548 | 2af6b6cb-8b3d-4895-9936-f22a63104487, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 5169c450-ece6-4729-8952-ba040d3f64f2, 734de5e7-0dc0-4ded-8156-c4a0e9093012, a3288879-cfb6-481c-89a0-131b2933754b, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, ddb43b49-94bf-4c9c-b875-99a2d8313797, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 97 | Joe Burrow | JAX@CIN | QB+2 | 5.529 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1bc5ea87-e6bb-4608-a110-2b657344f1ed, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 734de5e7-0dc0-4ded-8156-c4a0e9093012, 75ce51c3-50e5-41b2-b91f-25f0e54deefe, 9773742a-50b2-42ad-a96a-3b20b2d25a5d, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, eed8fc95-3591-4fa6-b7e6-4abb70a2885d, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 107 | Joe Burrow | JAX@CIN | QB+2 | 5.517 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1bc5ea87-e6bb-4608-a110-2b657344f1ed, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 1f90d290-afb4-48ae-8052-fa99040b8ddb, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 734de5e7-0dc0-4ded-8156-c4a0e9093012, c706298f-d5e9-441e-83fa-71b468ddc5a4, eed8fc95-3591-4fa6-b7e6-4abb70a2885d, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 163 | Trevor Lawrence | JAX@CIN | QB+2 | 5.470 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 2af6b6cb-8b3d-4895-9936-f22a63104487, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 5169c450-ece6-4729-8952-ba040d3f64f2, a7d14336-632e-48c8-b0c1-45916b8476e4, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, ddb43b49-94bf-4c9c-b875-99a2d8313797, ecadd109-bcd3-46c5-b77e-60a6d3214d7f |

**target_205 allocation:** `{"CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+2|BB1": 2, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+3|BB1": 1, "CIN|JAX|eed8fc95-3591-4fa6-b7e6-4abb70a2885d|QB+2|BB1": 2}`

| Rank in this universe | QB | Game | Stack | Selector | Canonical roster |
| --- | --- | --- | --- | --- | --- |
| 9 | Trevor Lawrence | JAX@CIN | QB+2 | 5.580 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 734de5e7-0dc0-4ded-8156-c4a0e9093012, a7d14336-632e-48c8-b0c1-45916b8476e4, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, c706298f-d5e9-441e-83fa-71b468ddc5a4, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, ddb43b49-94bf-4c9c-b875-99a2d8313797, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 61 | Trevor Lawrence | JAX@CIN | QB+3 | 5.548 | 2af6b6cb-8b3d-4895-9936-f22a63104487, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 5169c450-ece6-4729-8952-ba040d3f64f2, 734de5e7-0dc0-4ded-8156-c4a0e9093012, a3288879-cfb6-481c-89a0-131b2933754b, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, ddb43b49-94bf-4c9c-b875-99a2d8313797, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 97 | Joe Burrow | JAX@CIN | QB+2 | 5.529 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1bc5ea87-e6bb-4608-a110-2b657344f1ed, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 734de5e7-0dc0-4ded-8156-c4a0e9093012, 75ce51c3-50e5-41b2-b91f-25f0e54deefe, 9773742a-50b2-42ad-a96a-3b20b2d25a5d, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, eed8fc95-3591-4fa6-b7e6-4abb70a2885d, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 107 | Joe Burrow | JAX@CIN | QB+2 | 5.517 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1bc5ea87-e6bb-4608-a110-2b657344f1ed, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 1f90d290-afb4-48ae-8052-fa99040b8ddb, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 734de5e7-0dc0-4ded-8156-c4a0e9093012, c706298f-d5e9-441e-83fa-71b468ddc5a4, eed8fc95-3591-4fa6-b7e6-4abb70a2885d, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 156 | Trevor Lawrence | JAX@CIN | QB+2 | 5.470 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 2af6b6cb-8b3d-4895-9936-f22a63104487, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 5169c450-ece6-4729-8952-ba040d3f64f2, a7d14336-632e-48c8-b0c1-45916b8476e4, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, ddb43b49-94bf-4c9c-b875-99a2d8313797, ecadd109-bcd3-46c5-b77e-60a6d3214d7f |

**target_300 allocation:** `{"CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+2|BB1": 2, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+3|BB1": 1, "CIN|JAX|eed8fc95-3591-4fa6-b7e6-4abb70a2885d|QB+2|BB1": 2}`

| Rank in this universe | QB | Game | Stack | Selector | Canonical roster |
| --- | --- | --- | --- | --- | --- |
| 9 | Trevor Lawrence | JAX@CIN | QB+2 | 5.580 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 734de5e7-0dc0-4ded-8156-c4a0e9093012, a7d14336-632e-48c8-b0c1-45916b8476e4, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, c706298f-d5e9-441e-83fa-71b468ddc5a4, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, ddb43b49-94bf-4c9c-b875-99a2d8313797, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 61 | Trevor Lawrence | JAX@CIN | QB+3 | 5.548 | 2af6b6cb-8b3d-4895-9936-f22a63104487, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 5169c450-ece6-4729-8952-ba040d3f64f2, 734de5e7-0dc0-4ded-8156-c4a0e9093012, a3288879-cfb6-481c-89a0-131b2933754b, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, ddb43b49-94bf-4c9c-b875-99a2d8313797, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 97 | Joe Burrow | JAX@CIN | QB+2 | 5.529 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1bc5ea87-e6bb-4608-a110-2b657344f1ed, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 734de5e7-0dc0-4ded-8156-c4a0e9093012, 75ce51c3-50e5-41b2-b91f-25f0e54deefe, 9773742a-50b2-42ad-a96a-3b20b2d25a5d, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, eed8fc95-3591-4fa6-b7e6-4abb70a2885d, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 107 | Joe Burrow | JAX@CIN | QB+2 | 5.517 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1bc5ea87-e6bb-4608-a110-2b657344f1ed, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 1f90d290-afb4-48ae-8052-fa99040b8ddb, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 734de5e7-0dc0-4ded-8156-c4a0e9093012, c706298f-d5e9-441e-83fa-71b468ddc5a4, eed8fc95-3591-4fa6-b7e6-4abb70a2885d, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 163 | Trevor Lawrence | JAX@CIN | QB+2 | 5.470 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 2af6b6cb-8b3d-4895-9936-f22a63104487, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 5169c450-ece6-4729-8952-ba040d3f64f2, a7d14336-632e-48c8-b0c1-45916b8476e4, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, ddb43b49-94bf-4c9c-b875-99a2d8313797, ecadd109-bcd3-46c5-b77e-60a6d3214d7f |

**target_400 allocation:** `{"CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+2|BB1": 2, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+3|BB1": 1, "CIN|JAX|eed8fc95-3591-4fa6-b7e6-4abb70a2885d|QB+2|BB1": 2}`

| Rank in this universe | QB | Game | Stack | Selector | Canonical roster |
| --- | --- | --- | --- | --- | --- |
| 9 | Trevor Lawrence | JAX@CIN | QB+2 | 5.580 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 734de5e7-0dc0-4ded-8156-c4a0e9093012, a7d14336-632e-48c8-b0c1-45916b8476e4, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, c706298f-d5e9-441e-83fa-71b468ddc5a4, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, ddb43b49-94bf-4c9c-b875-99a2d8313797, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 61 | Trevor Lawrence | JAX@CIN | QB+3 | 5.548 | 2af6b6cb-8b3d-4895-9936-f22a63104487, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 5169c450-ece6-4729-8952-ba040d3f64f2, 734de5e7-0dc0-4ded-8156-c4a0e9093012, a3288879-cfb6-481c-89a0-131b2933754b, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, ddb43b49-94bf-4c9c-b875-99a2d8313797, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 97 | Joe Burrow | JAX@CIN | QB+2 | 5.529 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1bc5ea87-e6bb-4608-a110-2b657344f1ed, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 734de5e7-0dc0-4ded-8156-c4a0e9093012, 75ce51c3-50e5-41b2-b91f-25f0e54deefe, 9773742a-50b2-42ad-a96a-3b20b2d25a5d, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, eed8fc95-3591-4fa6-b7e6-4abb70a2885d, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 107 | Joe Burrow | JAX@CIN | QB+2 | 5.517 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1bc5ea87-e6bb-4608-a110-2b657344f1ed, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 1f90d290-afb4-48ae-8052-fa99040b8ddb, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 734de5e7-0dc0-4ded-8156-c4a0e9093012, c706298f-d5e9-441e-83fa-71b468ddc5a4, eed8fc95-3591-4fa6-b7e6-4abb70a2885d, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 163 | Trevor Lawrence | JAX@CIN | QB+2 | 5.470 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 2af6b6cb-8b3d-4895-9936-f22a63104487, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 5169c450-ece6-4729-8952-ba040d3f64f2, a7d14336-632e-48c8-b0c1-45916b8476e4, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, ddb43b49-94bf-4c9c-b875-99a2d8313797, ecadd109-bcd3-46c5-b77e-60a6d3214d7f |

**target_500 allocation:** `{"CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+2|BB1": 2, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+3|BB1": 1, "CIN|JAX|eed8fc95-3591-4fa6-b7e6-4abb70a2885d|QB+2|BB1": 2}`

| Rank in this universe | QB | Game | Stack | Selector | Canonical roster |
| --- | --- | --- | --- | --- | --- |
| 9 | Trevor Lawrence | JAX@CIN | QB+2 | 5.580 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 734de5e7-0dc0-4ded-8156-c4a0e9093012, a7d14336-632e-48c8-b0c1-45916b8476e4, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, c706298f-d5e9-441e-83fa-71b468ddc5a4, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, ddb43b49-94bf-4c9c-b875-99a2d8313797, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 61 | Trevor Lawrence | JAX@CIN | QB+3 | 5.548 | 2af6b6cb-8b3d-4895-9936-f22a63104487, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 5169c450-ece6-4729-8952-ba040d3f64f2, 734de5e7-0dc0-4ded-8156-c4a0e9093012, a3288879-cfb6-481c-89a0-131b2933754b, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, ddb43b49-94bf-4c9c-b875-99a2d8313797, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 97 | Joe Burrow | JAX@CIN | QB+2 | 5.529 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1bc5ea87-e6bb-4608-a110-2b657344f1ed, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 734de5e7-0dc0-4ded-8156-c4a0e9093012, 75ce51c3-50e5-41b2-b91f-25f0e54deefe, 9773742a-50b2-42ad-a96a-3b20b2d25a5d, d0ae658e-ab5e-49ad-bec3-5ae2c19867f1, eed8fc95-3591-4fa6-b7e6-4abb70a2885d, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 107 | Joe Burrow | JAX@CIN | QB+2 | 5.517 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1bc5ea87-e6bb-4608-a110-2b657344f1ed, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 1f90d290-afb4-48ae-8052-fa99040b8ddb, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 734de5e7-0dc0-4ded-8156-c4a0e9093012, c706298f-d5e9-441e-83fa-71b468ddc5a4, eed8fc95-3591-4fa6-b7e6-4abb70a2885d, f816bdba-894a-40e6-adf6-a3c2c0d659cb |
| 163 | Trevor Lawrence | JAX@CIN | QB+2 | 5.470 | 0be06444-4cd6-41a4-98a5-877a9a5c42b2, 1f3ab2b3-189f-420b-a120-d0acec6b43d1, 2af6b6cb-8b3d-4895-9936-f22a63104487, 319a7e5c-7967-4405-90f9-36ddfea66dfd, 5169c450-ece6-4729-8952-ba040d3f64f2, a7d14336-632e-48c8-b0c1-45916b8476e4, af4cc0b8-e85c-4a6a-847b-d92fdd75ec80, ddb43b49-94bf-4c9c-b875-99a2d8313797, ecadd109-bcd3-46c5-b77e-60a6d3214d7f |

Saved user five-entry policy sensitivity (overlap=4, one lineup per distinct QB direction; unchanged exposure and elevated-lineup limits):

| Universe | Status | Entries | Selector sum | Runtime seconds |
| --- | --- | --- | --- | --- |
| current | optimal | 5 | 27.203 | 1.129 |
| expanded | optimal | 5 | 27.203 | 2.847 |
| target_205 | infeasible_or_unproven | 0 | 0 | 0.131 |
| target_300 | optimal | 5 | 26.992 | 1.726 |
| target_400 | optimal | 5 | 27.203 | 1.955 |
| target_500 | optimal | 5 | 27.203 | 2.098 |

## 24. Twenty-entry shadow comparison

| Universe | Status | Entries | Selector sum | Mean sum | P90 sum | Tolerance | Overlap cap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| current | optimal | 20 | 110.188 | 2603.391 | 4507.098 | None | 6 |
| expanded | optimal | 20 | 110.283 | 2592.025 | 4498.555 | 0.2 | 6 |
| target_205 | optimal | 20 | 110.226 | 2583.958 | 4489.923 | 0.2 | 6 |
| target_300 | optimal | 20 | 110.283 | 2592.025 | 4498.555 | 0.2 | 6 |
| target_400 | optimal | 20 | 110.283 | 2592.025 | 4498.555 | 0.2 | 6 |
| target_500 | optimal | 20 | 110.283 | 2592.025 | 4498.555 | 0.2 | 6 |

**current allocation:** `{"ARI|NYG|e6f98d37-a335-4ae4-b58f-29c8ab1d106e|QB+2|BB0": 4, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+2|BB1": 10, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+3|BB1": 2, "CIN|JAX|eed8fc95-3591-4fa6-b7e6-4abb70a2885d|QB+2|BB1": 4}`

**expanded allocation:** `{"ARI|NYG|e6f98d37-a335-4ae4-b58f-29c8ab1d106e|QB+2|BB0": 3, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+2|BB1": 9, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+3|BB0": 1, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+3|BB1": 2, "CIN|JAX|eed8fc95-3591-4fa6-b7e6-4abb70a2885d|QB+2|BB1": 4, "CIN|JAX|eed8fc95-3591-4fa6-b7e6-4abb70a2885d|QB+3|BB1": 1}`

**target_205 allocation:** `{"ARI|NYG|e6f98d37-a335-4ae4-b58f-29c8ab1d106e|QB+2|BB0": 2, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+2|BB1": 10, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+3|BB0": 1, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+3|BB1": 1, "CIN|JAX|eed8fc95-3591-4fa6-b7e6-4abb70a2885d|QB+2|BB1": 5, "CIN|JAX|eed8fc95-3591-4fa6-b7e6-4abb70a2885d|QB+3|BB1": 1}`

**target_300 allocation:** `{"ARI|NYG|e6f98d37-a335-4ae4-b58f-29c8ab1d106e|QB+2|BB0": 3, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+2|BB1": 9, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+3|BB0": 1, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+3|BB1": 2, "CIN|JAX|eed8fc95-3591-4fa6-b7e6-4abb70a2885d|QB+2|BB1": 4, "CIN|JAX|eed8fc95-3591-4fa6-b7e6-4abb70a2885d|QB+3|BB1": 1}`

**target_400 allocation:** `{"ARI|NYG|e6f98d37-a335-4ae4-b58f-29c8ab1d106e|QB+2|BB0": 3, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+2|BB1": 9, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+3|BB0": 1, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+3|BB1": 2, "CIN|JAX|eed8fc95-3591-4fa6-b7e6-4abb70a2885d|QB+2|BB1": 4, "CIN|JAX|eed8fc95-3591-4fa6-b7e6-4abb70a2885d|QB+3|BB1": 1}`

**target_500 allocation:** `{"ARI|NYG|e6f98d37-a335-4ae4-b58f-29c8ab1d106e|QB+2|BB0": 3, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+2|BB1": 9, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+3|BB0": 1, "CIN|JAX|af4cc0b8-e85c-4a6a-847b-d92fdd75ec80|QB+3|BB1": 2, "CIN|JAX|eed8fc95-3591-4fa6-b7e6-4abb70a2885d|QB+2|BB1": 4, "CIN|JAX|eed8fc95-3591-4fa6-b7e6-4abb70a2885d|QB+3|BB1": 1}`

## 25. Production impact if eventually promoted

Broader discovery would change the candidates available to the existing admission and portfolio solvers; it can change thesis breadth and selected rosters even with all weights and constraints fixed. Raw frontier rosters must remain auditable before caps. A larger admitted target consumes more memory and portfolio pair-constraint work and can improve roster recall without guaranteeing meaningful player/family retention.

Recommend promoting the observational request/raw/admission ledger and coverage warnings first, then a separate reviewed change for systematic QB+3/partner/player-gap discovery before unchanged cap admission. Keep the final candidate target and admission/selection policy unchanged until the measured gaps have a retention rule and runtime validation. This report does not authorize or perform promotion.

## 26. Files changed

- `backend/app/product_services/classic_candidate_completeness.py`: isolated model capture, exact roster enumeration, prospective validation, player-agnostic requests, lineage/counterfactuals, recall, diversity, saturation, target comparisons, coverage audits.
- `scripts/research_classic_candidate_completeness.py`: immutable frozen-fixture runner, process workers, deterministic reduction, request checkpoints, target/thesis/user-policy comparisons, runtime and hashes.
- `scripts/render_candidate_completeness.py`: report and complete player/QB CSV audits.
- `backend/app/tests/product/test_classic_candidate_completeness.py`: targeted behavior and Week 4 canonical-ID regression tests.
- `artifacts/candidate_completeness/week4-8b5c114c.json` (original solves), `week4-8b5c114c-complete.json` (stage-trace supplement), `week4-8b5c114c-reviewed.json` (final reviewed analysis), player/QB CSVs, this report, README, RELEASE_NOTES.

## 27. Tests

Run targeted validation after generating the fixture artifact:

```sh
PYTHONHASHSEED=0 .venv/bin/python -m pytest backend/app/tests/product/test_classic_candidate_completeness.py backend/app/tests/product/test_classic_frontier_diagnostic.py backend/app/tests/product/test_classic_thesis_shadow.py backend/app/tests/product/test_classic_prospective.py backend/app/tests/product/test_classic_small_field.py -q
```

Coverage: deterministic actual-solver enumeration, exact no-good uniqueness, inclusive tolerance boundary/safety censoring, all-QB templates, forced inclusion, partner singles/doubles/triples/TE, raw/admitted reasons and displacement, target reuse, saturation, canonical recall, diversity, leakage/cutoff/prelock guards, unchanged production hashes/rosters, and Bucky/Bowers/Jefferson/JSN/Lamar fixtures.

**Validation: 88 passed in 4.25s.** No skipped regression fixtures. Python compilation and focused documentation diff checks also passed. See [validation evidence](artifacts/candidate_completeness/week4-validation.json).

## 28. Remaining uncertainty

- The unenumerated remainder of safety-limited QB directions prevents exhaustive counts and a true global recall estimate.
- Player and partner screens are broad deterministic hypotheses, not proofs that all meaningful combinations were searched.
- Exact roster recall penalizes omitted near-duplicates; meaningful direction/game/player coverage must also be assessed.
- A quiet ordered batch is not proof of search saturation; a mandatory-source/holdout experiment remains needed for a stopping rule.
- Summed player P90 is not lineup P90; these frozen selector/thesis hypotheses are not outcome-calibrated.
- Original historical attempt chronology is unavailable; saved raw keys and final admission counterfactuals are exact reconstructions, not original event logs.
- Portfolio solver timeouts are explicitly unproven and cannot establish that a better portfolio does not exist.

## Required final answers

**Is the current 205-candidate universe sufficiently complete? NO.** The known legal near-frontier omissions and measured recall contradict completeness.

**Is the primary problem generation or admission?** At 0.20, generation misses **174** known risk-legal rosters; admission omits **0** of those historically generated. Generation is **100.0%** of known misses. The four named near-frontier regressions are classified individually above.

**How many legal candidates exist within each tolerance?** Known risk-legal counts (.05/.10/.15/.20/.30): 38/111/205/258/397. Count statuses: exact/lower_bound/lower_bound/lower_bound/lower_bound. Exact total cardinality is unavailable wherever enumeration is censored.

**What frontier recall does the current 205 achieve?** 52.6%/44.1%/36.6%/32.6%/24.7% against the expanded known risk-legal universe, in tolerance order.

**Does increasing the candidate target alone solve the problem? NO.** It cannot recover ungenerated rosters. On the expanded raw universe, target-only admission results are measured above; caps and selector competition can still leave coverage warnings.

**What is the smallest candidate target that preserves nearly all meaningful frontier diversity? 400 of the tested targets**, when preserving the saved-user-policy five-entry optimum and expanded twenty-entry allocation is part of the acceptance criteria. 300 is sufficient for 97.7% known inside-0.20 roster recall and zero player coverage warnings alone; it loses the best saved-policy five-entry construction. A globally minimum target is not established.

**Would a dynamic saturation-based stopping rule be better than a fixed 205 target?** It is a better research direction for raw discovery, conditional on mandatory-source coverage, grouped coverage checks, a holdout sweep, and hard safety limits. This experiment does not validate a production stopping rule.

**Does improved discovery materially change the thesis conclusions? YES for construction families, NO for competitive QB/game breadth.** Qualified families inside 0.20 expand from 4 to 7 and Pareto-frontier families from 2 to 3. The same three QB directions and two games remain competitive; no new KC/BUF/SEA/MIN/TB direction reaches 0.20 under the frozen model.

**Does improved discovery materially change the best five-lineup shadow?** The existing v3 dynamic thesis shadow changes from Lawrence/Burrow/Brissett = 3/1/1 to Lawrence/Burrow = 3/2, and its chosen tolerance tightens from 0.20 to 0.15. Its selector sum changes from 27.687854 to 27.643977 (−0.043877); the lower sum reflects a different adaptive eligible set, not evidence of degraded legal frontier quality. Under the identical saved user overlap=4/distinct-QB policy, the optimum remains 27.202641 with the exact same canonical roster set in the expanded raw universe. Targets 400/500 tie that score with alternative roster sets.

**Does improved discovery materially change the 20-lineup thesis allocation? YES, modestly.** Lawrence/Burrow/Brissett shifts from 12/4/4 to 12/5/3; qualified constructions broaden, selector sum rises from 110.187825 to 110.283352 (+0.095527), and the expanded twenty is feasible inside 0.20 instead of requiring the unrestricted tolerance fallback. Targets 300/400/500 reproduce this expanded allocation.

**What exact change should be promoted next?** Add the request/raw/admission lineage and near-frontier zero-coverage warning to the production report, then review the general QB+3/partner/player-gap discovery sweep as a separate promotion. Preserve all scoring and portfolio policy. Do not raise the production target merely to hide incomplete generation.
