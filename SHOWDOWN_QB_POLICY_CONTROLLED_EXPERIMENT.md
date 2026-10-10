# Showdown QB policy controlled experiment

> Superseded for ATL–NO kicker eligibility. This archived experiment allowed backup
> Charlie Smyth as a primary kicker. The corrected replay and production rebuild
> are in [SHOWDOWN_KICKER_ROLE_AUDIT.md](SHOWDOWN_KICKER_ROLE_AUDIT.md).
> A/B now select the same portfolio; C/D remain underfilled because Olave alone is
> mandatory under their quality screen. The Smyth-dependent conclusions and
> numerical relaxation thresholds below must not guide current portfolio changes.

| Policy | QB CPT Allowed | Max QBs | Generated / Requested | Avg Mean | Avg P90 | Unique CPTs | QB CPT Exposure | Two-QB Exposure | Avg Roster Overlap | Max Player Exposure | Fixed-Control Quality | Primary Limitation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | Yes | 2 | 5 / 5 | 90.272 | 151.595 | 2 | 40.00% | 40.00% | 3.700 | 100.00% | 95.11% | Fixed exposure capacities |
| B | Yes | 1 | 5 / 5 | 90.398 | 151.855 | 2 | 60.00% | 0.00% | 3.800 | 100.00% | 94.90% | Fixed exposure capacities |
| C | No | 2 | 4 / 5 | 90.685 | 152.349 | 2 | 0.00% | 25.00% | 4.667 | 100.00% | 95.57% | Olave + Smyth mandatory; each cap 4 |
| D | No | 1 | 4 / 5 | 90.596 | 151.600 | 2 | 0.00% | 0.00% | 4.500 | 100.00% | 95.19% | Olave + Smyth mandatory; each cap 4 |
| E | Yes | 2 | 5 / 5 | 89.657 | 152.269 | 2 | 60.00% | 60.00% | 3.800 | 100.00% | 93.61% | Max 4/team user preference |
| F | Yes | 2 | 5 / 5 | 84.914 | 147.203 | 2 | 0.00% | 80.00% | 4.000 | 100.00% | 89.74% | 3–3 only; fixed-A quality falls |

E and F are separately authorized team-cap challengers: **E = max 4/team**, **F = max 3/team**, with both QB constructions allowed. A–D retain max 5/team and change only the two QB controls. The UI now offers 3, 4 and the existing default 5. No default, projection or exposure-cap change was made.

## QB CONSTRUCTION POLICY

| Policy | QB Captain allowed | Maximum starting QBs | Requested size | Effective QB-Captain lineup limit | Effective starting-QB lineup limit | Team maximum |
| --- | --- | --- | --- | --- | --- | --- |
| A | Yes | 2 | 5 | 1 | 2 | 5 |
| B | Yes | 1 | 5 | 1 | 1 | 5 |
| C | No | 2 | 5 | 0 | 2 | 5 |
| D | No | 1 | 5 | 0 | 1 | 5 |
| E | Yes | 2 | 5 | 1 | 2 | 4 |
| F | Yes | 2 | 5 | 1 | 2 | 3 |

The effective Captain limit above is per lineup. The unchanged portfolio Captain cap is 60% × 5 requested entries = 3 appearances per Captain. Core cap 80% = 4 appearances; starting QB cap 100% = 5; cheap punt cap 40% = 2. Quality is the joint 95% screen on baseline mean and summed marginal P90. P90 is a lineup ceiling proxy, not a measured joint 90th percentile.

## Frozen-input proof

Earlier observational runs used separate projection runs:

| Policy | Original optimizer run | Projection run |
| --- | --- | --- |
| A | 2771d4f1-baa0-46d5-8c27-7e4e86ed0282 | f7ffb4d0-9398-425d-a0c4-dd0d5bff007f |
| B | 65ec0562-8e75-4d61-9649-2d84d5e677bc | cfdb4e29-3c3f-4a67-a1e9-0d61d0c5b82a |
| C | 631e89a3-8dce-4b96-a347-a6bd50ce00d5 | b115797d-cfdd-43a4-9d38-746f81b84248 |
| D | 49a5f1c7-0a8a-4337-bd9b-ae169fa695ac | 14524ab5-0a69-4d43-b724-741cb2ec0c0a |

Prepared football SHA-256: `c6a94b8f412dc00cc82bf371f16cdcf3933f7819ae4a9d2cf9f044805895b94e`. Prepared envelope SHA-256: `5d97e68dca6b83af5ed584ed9910fe0890967596768283052582b7baad49e50a`. All six executions asserted the same complete prepared 20-player frame, including starter/availability, salary, market, projection, P90, ownership and Captain multipliers. Source projection: `f7ffb4d0-9398-425d-a0c4-dd0d5bff007f`. Seed: `20261005`; single-thread CBC with fixed solver seeds. No projection refresh/refit or database optimizer/lineup write occurred.

The source read-only freeze captured 55 raw player rows at 2026-10-05 19:34:45 UTC, before the Monday kickoff at 2026-10-06 00:15 UTC. Preparation was frozen once into the serialized production MILP (97 binary variables, 211 constraints). Replays load the same raw freeze, apply deterministic production preparation, and assert an identical prepared frame. Fixed source metadata and code checksums are retained. Completed preparation-job IDs and presentation/runtime fields were omitted only from the offline request to avoid querying nonexistent live workflow tables; their original evidence remains in `recent-A.json`.

The two QB switches are independent. A–D use unchanged generation breadth, questionable exclusions, quality/exposure limits, script settings (required and soft scenario diversity both off), requested five entries, objective and rules. E/F change only the team-count constraint relative to A. E/F run after the additive UI/backend team-limit feature; its execution source hash is recorded, and legacy max-5 behavior was validated.

## Generation, feasibility and exposure

| Policy | Scenario candidates | Physical signatures | Quality scenario / physical | Player-cap support | Captain-cap support | Unique support | Full-universe quality signatures | Final |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 142 | 115 | 23 / 17 | 17 | 17 | 17 | 27 | 5/5 |
| B | 136 | 109 | 22 / 18 | 18 | 18 | 18 | 28 | 5/5 |
| C | 126 | 102 | 17 / 13 | 13 | 13 | 13 | 19 | 4/5 |
| D | 120 | 97 | 13 / 10 | 10 | 10 | 10 | 14 | 4/5 |
| E | 143 | 114 | 17 / 12 | 12 | 12 | 12 | 19 | 5/5 |
| F | 132 | 104 | 24 / 17 | 17 | 17 | 17 | 22 | 5/5 |

Support means a candidate can participate in a joint portfolio of the **achieved size** (five for A/B/E/F, four for C/D). Exposure is a joint constraint, so these are support counts rather than independent per-row filters. Physical uniqueness is enforced from the first support solve. For C/D, support in any requested five-entry portfolio is **zero**. Scenario copies of one Captain plus six canonical identities count as one physical signature; rediscovery never adds another entry.

The exhaustive audit considered 216,178 salary/team-legal Captain/roster signatures, retained 4,484 for exact certification under a valid selector upper bound or fixed-A quality ≥88%, and checked every retained signature against every frozen MILP constraint. Binary interval propagation resolves the auxiliary variables; unresolved cases use CBC. The rank cutoff covers every selected lineup. Omitted signatures cannot reach a 95% policy quality screen; omitted-quality bounds were also checked against the diagnostic quality-only optimum. Every selected baseline selector matches its independently certified frozen-model value.

The full universe contains additional qualifying rosters that the candidate generator did not discover, but its globally optimal portfolio selector equals each production-selected portfolio to numerical tolerance. Expanding discovery therefore cannot fill C/D or improve these selected portfolios under their exact constraints.

**Exact C/D bottleneck:** every joint-quality-eligible roster contains Charlie Smyth and Chris Olave. Each has an appearance cap of four. Five entries would require five appearances of both, which contradicts those caps. Shough is also universal but its five-appearance starting-QB cap is compatible with five entries. Juwan Johnson appears in all four selected entries but is not mathematically mandatory in every qualifying roster. Captain eligibility and the joint quality screen create this restricted universe; salary and correlations are already included in the certificate. Captain uniqueness, the Captain cap and scenario discovery are not independent fixes.

| C/D diagnostic only | Five entries? | Exact requirement / result |
| --- | --- | --- |
| Expand generation only | No | Exhaustive universe still infeasible |
| Increase Captain cap 3→4 | No | Olave/Smyth player caps remain binding |
| Increase only Smyth + Olave player caps 4→5 | Yes | Both must change; minimum two player-cap relaxations |
| Increase all core caps 4→5 | Yes | Broader than necessary |
| Reduce joint quality floor only | Yes | 95% → 94.443492% |
| Allow only Shough as additional QB Captain | Yes | Keep all player/Captain caps and 95% screen |
| Allow only Penix as additional QB Captain | No | Does not resolve this universe |

These alternatives were solved separately and never applied to A–F. Because the existing cap semantics use `ceil(requested × rate)`, an appearance cap of five begins at any rate strictly above 80% (81% if the UI accepts integer percentages), not necessarily 100%. Exactly 80% still permits only four. The minimum quality-only change is 0.556508 percentage points; CBC and the native CBC cross-check agree.

### REQUESTED-PORTFOLIO CAP COMPLIANCE

Caps retain denominator five. C/D: Smyth, Olave and Juwan each appear four times and pass the 80% requested-count cap. Olave Captain appears three times and passes the 60% requested-count Captain cap.

### FINAL-PORTFOLIO REALIZED EXPOSURE

Those players are 4/4 = **100%** realized exposure; Olave Captain is 3/4 = **75%**. Each carries: **UNDERFILLED PORTFOLIO — requested-count cap passed, but realized final exposure exceeds configured percentage.** Starting-QB 100% is within its configured 100%. No cheap punt ≤$1,000 appears. Required scenario coverage and soft scenario reward are off; there is no additional active percentage-based portfolio constraint in this experiment. The backend and report export now expose the warning without changing cap semantics.

## Fixed and policy-specific quality

| Policy | Policy mean / P90 maximum | Minimum policy quality | Minimum fixed-A quality | Selected passing fixed-A 95% |
| --- | --- | --- | --- | --- |
| A | 93.778 / 156.432 | 95.11% | 95.11% | 5 / 5 |
| B | 93.778 / 154.089 | 95.33% | 94.90% | 4 / 5 |
| C | 93.778 / 153.680 | 95.57% | 95.57% | 4 / 4 |
| D | 93.778 / 153.680 | 95.19% | 95.19% | 4 / 4 |
| E | 92.091 / 156.432 | 95.00% | 93.61% | 4 / 5 |
| F | 87.655 / 151.678 | 95.00% | 89.74% | 0 / 5 |

Quality is the minimum of mean/max-mean and P90/max-P90; maxima may come from different rosters. All selected entries pass their normal policy-specific joint screen. B uses a lower P90 benchmark than A; C/D also use a lower P90 benchmark. E reduces the available mean maximum; F reduces both. A lower policy maximum can make an entry pass its policy screen while failing fixed A.

Native CBC independently confirmed all C/D/E/F raw maxima. The initial F bundled audit returned a mean of 87.087727 while a fixed-roster witness and independent solves prove 87.654936; the preserved initial diagnostic is superseded by `feasibility-verification.json`. The production F benchmark was already 87.654936, so this diagnostic discrepancy changed no generated lineup or reported threshold.

## Selected entries and skipped alternatives

Global rank is before portfolio exposures, the two QB restrictions and team-cap preferences, across the full legal A universe. It is not merely rank within discovered candidates. Ties share a rank. The JSON includes every higher-ranked alternate and its concrete replacement blockers against the other selected entries. The compact tables below summarize those blockers; conditional scenario scores never determine this baseline rank.

### Policy A

| Entry | Global rank | Baseline selector | Mean | P90 | Captain | QBs | Primary selection reason | Higher-ranked skip blockers (counts overlap) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 176.323 | 90.266 | 153.680 | Chris Olave | 1 | raw selector strength | No higher-ranked alternate |
| 2 | 2 | 175.753 | 89.621 | 152.715 | Chris Olave | 2 | raw selector strength | physical roster already selected (1); player exposure (1) |
| 3 | 3 | 174.873 | 91.181 | 152.783 | Chris Olave | 1 | raw selector strength | physical roster already selected (2) |
| 4 | 525 | 159.431 | 90.407 | 150.018 | Tyler Shough | 1 | Captain diversification | joint quality screen (509); not discovered by this production candidate generator (474); Captain exposure (336); player exposure (188) |
| 5 | 721 | 157.298 | 89.882 | 148.777 | Tyler Shough | 2 | Captain diversification | player exposure (817); joint quality screen (699); not discovered by this production candidate generator (663); Captain exposure (412) |

### Policy B

| Entry | Global rank | Baseline selector | Mean | P90 | Captain | QBs | Primary selection reason | Higher-ranked skip blockers (counts overlap) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 176.323 | 90.266 | 153.680 | Chris Olave | 1 | raw selector strength | No higher-ranked alternate |
| 2 | 3 | 174.873 | 91.181 | 152.783 | Chris Olave | 1 | raw selector strength | physical roster already selected (1); QB construction (1); not discovered by this production candidate generator (1) |
| 3 | 302 | 162.470 | 89.973 | 153.434 | Tyler Shough | 1 | Captain diversification | joint quality screen (290); not discovered by this production candidate generator (267); QB construction (127); player exposure (99) |
| 4 | 507 | 159.631 | 91.175 | 150.927 | Tyler Shough | 1 | Captain diversification | joint quality screen (491); not discovered by this production candidate generator (469); player exposure (434); QB construction (218) |
| 5 | 719 | 157.310 | 89.395 | 148.450 | Tyler Shough | 1 | Captain diversification | joint quality screen (696); not discovered by this production candidate generator (678); player exposure (634); QB construction (321) |

### Policy C

| Entry | Global rank | Baseline selector | Mean | P90 | Captain | QBs | Primary selection reason | Higher-ranked skip blockers (counts overlap) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 176.323 | 90.266 | 153.680 | Chris Olave | 1 | raw selector strength | No higher-ranked alternate |
| 2 | 2 | 175.753 | 89.621 | 152.715 | Chris Olave | 2 | raw selector strength | physical roster already selected (1) |
| 3 | 3 | 174.873 | 91.181 | 152.783 | Chris Olave | 1 | raw selector strength | physical roster already selected (2) |
| 4 | 58 | 168.232 | 91.672 | 150.219 | Devaughn Vele | 1 | exposure diversification | Captain exposure (50); joint quality screen (50); not discovered by this production candidate generator (25); physical roster already selected (3) |

### Policy D

| Entry | Global rank | Baseline selector | Mean | P90 | Captain | QBs | Primary selection reason | Higher-ranked skip blockers (counts overlap) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 176.323 | 90.266 | 153.680 | Chris Olave | 1 | raw selector strength | No higher-ranked alternate |
| 2 | 3 | 174.873 | 91.181 | 152.783 | Chris Olave | 1 | raw selector strength | physical roster already selected (1); QB construction (1); not discovered by this production candidate generator (1) |
| 3 | 9 | 172.360 | 89.267 | 149.717 | Chris Olave | 1 | exposure diversification | joint quality screen (5); QB construction (4); not discovered by this production candidate generator (4); physical roster already selected (2) |
| 4 | 58 | 168.232 | 91.672 | 150.219 | Devaughn Vele | 1 | exposure diversification | Captain exposure (50); joint quality screen (50); QB construction (29); not discovered by this production candidate generator (29) |

### Policy E

| Entry | Global rank | Baseline selector | Mean | P90 | Captain | QBs | Primary selection reason | Higher-ranked skip blockers (counts overlap) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2 | 175.753 | 89.621 | 152.715 | Chris Olave | 2 | raw selector strength | team-count user preference (1); not discovered by this production candidate generator (1) |
| 2 | 18 | 171.654 | 89.377 | 148.616 | Chris Olave | 2 | exposure diversification | player exposure (11); joint quality screen (11); team-count user preference (8); not discovered by this production candidate generator (8) |
| 3 | 129 | 165.863 | 90.328 | 156.432 | Tyler Shough | 2 | Captain diversification | joint quality screen (118); not discovered by this production candidate generator (96); team-count user preference (50); physical roster already selected (2) |
| 4 | 327 | 162.067 | 87.786 | 152.654 | Tyler Shough | 1 | Captain diversification | joint quality screen (312); not discovered by this production candidate generator (283); player exposure (130); team-count user preference (111) |
| 5 | 507 | 159.631 | 91.175 | 150.927 | Tyler Shough | 1 | Captain diversification | joint quality screen (487); not discovered by this production candidate generator (460); player exposure (434); team-count user preference (165) |

### Policy F

| Entry | Global rank | Baseline selector | Mean | P90 | Captain | QBs | Primary selection reason | Higher-ranked skip blockers (counts overlap) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 35 | 169.736 | 84.888 | 147.986 | Chris Olave | 1 | team-count user preference and exposure diversification | team-count user preference (29); not discovered by this production candidate generator (29); joint quality screen (9) |
| 2 | 41 | 169.316 | 84.156 | 149.463 | Devaughn Vele | 2 | team-count user preference and exposure diversification | Captain exposure (38); team-count user preference (33); not discovered by this production candidate generator (33); player exposure (16) |
| 3 | 60 | 168.138 | 85.840 | 149.476 | Devaughn Vele | 2 | team-count user preference and exposure diversification | player exposure (59); Captain exposure (51); team-count user preference (49); not discovered by this production candidate generator (49) |
| 4 | 72 | 167.751 | 84.386 | 144.993 | Chris Olave | 2 | team-count user preference and exposure diversification | team-count user preference (58); not discovered by this production candidate generator (58); joint quality screen (23); physical roster already selected (3) |
| 5 | 103 | 166.573 | 85.301 | 144.096 | Chris Olave | 2 | team-count user preference and exposure diversification | team-count user preference (85); not discovered by this production candidate generator (85); player exposure (41); joint quality screen (39) |

A’s Olave Captains occupy ranks 1–3; Shough Captains are ranks 525 and 721. B’s Olave Captains are ranks 1 and 3; Shough Captains are ranks 302, 507 and 719. QB Captain helps complete an exposure-compliant portfolio after higher-scoring non-QB families consume core/Captain capacity. This does not mean QB Captain receives the strongest raw selector in this slate. In C/D, the fourth Vele Captain is rank 58 and the Olave Captain capacity is saturated at three; no legal fifth survives the mandatory-player caps. No scenario coverage requirement selected any entry.

## A → B roster and salary substitution

Correspondence fixes the original Captain, maximizes retained canonical player identities, then maximizes baseline selector over the exhaustively certified universe. The original two-QB entries both have non-QB Captains: two QBs plus four other players **including Captain**, not Captain plus six further players. These replacements are diagnostics, not necessarily the globally selected B entry.

| A entry / Captain | Original six players | Removed QB / added player | One-QB remaining QB | Salary change | Mean change | P90 change | Selector change |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | Charlie Smyth, Tyler Shough, Michael Penix Jr., Juwan Johnson, Jahan Dotson, Chris Olave (CPT) | Michael Penix Jr. → Devaughn Vele | Tyler Shough | $-1,200 | +0.645 | +0.965 | +0.570 |
| 5 | Charlie Smyth, Bijan Robinson, Tyler Shough (CPT), Bryce Lance, Michael Penix Jr., Devaughn Vele | Michael Penix Jr. → Juwan Johnson | Tyler Shough | $-1,600 | +1.338 | -2.343 | -2.381 |

| Metric | A | B |
| --- | --- | --- |
| QB Captain exposure | 40% | 60% |
| Shough total exposure | 100% | 100% |
| Two-QB exposure | 40% | 0% |
| Average RB per entry | 0.60 | 0.80 |
| Average K per entry | 0.80 | 0.80 |
| Average WR per entry | 2.20 | 2.60 |
| Average TE per entry | 1.00 | 0.80 |
| Punts ≤$3,000 per entry | 0.6 | 0.8 |
| Same-team WR/TE per selected QB | 2.000 | 2.800 |

B increases average mean by 0.126 and P90 proxy by 0.260, but portfolio selector drops 13.071 (1.55%). It removes two-QB entries while raising Shough Captain exposure by 20 percentage points and increasing five-NO entries from two to three. It does not solve team concentration. The punt diagnostic uses $3,000 for construction description; the actual cheap-punt exposure class remains ≤$1,000.

## Diversity diagnostics and effects of removing QB Captain

| Policy | Unique players | CPT positions | Shared avg / min / max | Avg Jaccard | Players in every entry / distinct selected players | Core in every entry | Team splits | Roster-script classes | Portfolio selector |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 11 | {'QB': 2, 'WR': 3} | 3.700 / 2 / 5 | 0.468 | 9.09% | Tyler Shough | {'ATL 1/NO 5': 2, 'ATL 2/NO 4': 3} | {'NO passing concentration': 5} | 843.678 |
| B | 10 | {'QB': 3, 'WR': 2} | 3.800 / 3 / 5 | 0.476 | 10.00% | Tyler Shough | {'ATL 1/NO 5': 3, 'ATL 2/NO 4': 2} | {'NO passing concentration': 5} | 830.606 |
| C | 9 | {'WR': 4} | 4.667 / 4 / 5 | 0.643 | 44.44% | Chris Olave, Charlie Smyth, Tyler Shough, Juwan Johnson | {'ATL 1/NO 5': 3, 'ATL 2/NO 4': 1} | {'NO passing concentration': 4} | 695.180 |
| D | 10 | {'WR': 4} | 4.500 / 4 / 5 | 0.607 | 40.00% | Chris Olave, Charlie Smyth, Tyler Shough, Juwan Johnson | {'ATL 1/NO 5': 4} | {'NO passing concentration': 4} | 691.787 |
| E | 10 | {'QB': 3, 'WR': 2} | 3.800 / 2 / 5 | 0.480 | 10.00% | Tyler Shough | {'ATL 2/NO 4': 5} | {'NO passing concentration': 5} | 834.967 |
| F | 9 | {'WR': 5} | 4.000 / 3 / 5 | 0.510 | 11.11% | Tyler Shough | {'ATL 3/NO 3': 5} | {'balanced competitive': 5} | 841.513 |

A→C overlap rises 3.70→4.67; B→D rises 3.80→4.50. Both no-QB-Captain portfolios have four universal core players instead of one and only WR Captains. The unique Captain count stays two, so Captain count alone hides the concentration. D is entirely NO 5–ATL 1. Portfolio-selector totals for four versus five entries are not directly comparable without also showing entry count/average; the JSON preserves both scoring proxies and counts. Pairwise score correlation is unavailable because no joint simulation draw matrix was frozen. Roster overlap is not score correlation. Structural script classes are descriptive diagnostics, not scenario-credit objectives.

## Team-cap challengers preferred by the user

**Max 4/team (E)** directly prevents five-NO entries and filled 5/5, all NO 4–ATL 2 in this frozen slate. Relative to A, average mean changes −0.614 (−0.68%), P90 +0.674 (+0.44%), and portfolio selector −8.710 (−1.03%). QB Captain and two-QB exposures both rise to 60%; a team cap should not be interpreted as a QB cap.

**Max 3/team (F)** filled 5/5 with every entry 3–3. Relative to A, mean changes −5.357 (−5.93%) and P90 −4.392 (−2.90%). Four of five entries have both QBs. All five pass their policy screen, but fixed-A quality makes the lower scoring level visible. Both options are available; max 4 is the less restrictive starting preference for avoiding 5–1 constructions. These one-slate results do not establish tournament success.

## Historical replay

One usable frozen PIT/CLE Thursday Week 4 archive was found. It has 533 prelock baseline-scored physical rosters and an immutable source-input checksum. Candidate archive timestamp: 2026-10-01T15:40:13.500469+00:00; lock 2026-10-02T00:15:00+00:00. A and B use identical stored scores, salaries, canonical identities and player/Captain exposure settings; B filters two-QB rosters. Actuals are joined afterward using canonical player IDs and validated CPT/FLEX base-score consistency. No postgame information was used to construct or rescore the candidates.

| Policy | Generated | Best selected actual / best portfolio oracle | Portfolio total actual | Mean actual | Global DK oracle | Regret | Optimal-Captain entries | Top-1 / 5 / 10 capture | Overlap | Two-QB / QB-CPT |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 4 | 99.77 | 369.53 | 92.38 | 120.74 | 20.97 | 0 | {'1': 0, '10': 0, '5': 0} | 4.667 | 0.00% / 0.00% |
| B | 4 | 99.77 | 369.53 | 92.38 | 120.74 | 20.97 | 0 | {'1': 0, '10': 0, '5': 0} | 4.667 | 0.00% / 0.00% |

A/B select the same four entries here and no QB Captain or two-QB entry. This is a time-safe **selection-only replay of archived coverage**, not unrestricted historical regeneration; it does not distinguish the QB hypotheses. “Best portfolio oracle” means the maximum actual score among selected entries; the table separately reports sum and average. Top-N capture counts selected scores meeting the Nth highest legal-oracle score, including ties. The oracle uses all resolved frozen salary-pool IDs and DK roster legality; it excludes model quality, projections and user restrictions. This is actual-score optimality, not real-contest top-10% performance. More frozen slates and paired full generation replays remain necessary.

## Answers and recommendation

1. **Were the earlier four runs comparable?** No: four different projection run IDs were used. The earlier outputs are observational comparisons, not isolated QB effects. The controlled A–D replay reproduces the same 5/5, 5/5, 4/5, 4/5 pattern.

2. **What caused 4-of-5?** An exact interaction of no-QB Captain eligibility, the joint 95% quality screen and the four-appearance caps on Smyth and Olave. Full legal-universe feasibility is infeasible at five and feasible at four. It is not an undiscovered fifth candidate.

3. **Does single-QB materially hurt lineup quality?** Here mean/P90 proxies slightly improve, while selector falls 1.55% and fixed-A versus policy-specific quality must be distinguished. One slate does not establish a general result.

4. **Does single-QB increase QB-Captain exposure?** Yes, 40%→60%, with Shough total exposure still 100%. It shifts construction rather than removing dependence on the favorite QB.

5. **Does removing QB Captain increase concentration?** Yes here: overlap rises, four players appear in every entry, and D has only one team split. Unique Captain count remains two but both become WRs.

6. **Are exposure caps behaving as intended under underfill?** Their requested-count rounding behaves as configured. The old PASS label could obscure realized exposure above the configured rate; reports now distinguish the denominators and warn without changing caps.

7. **Is A still the control?** Yes. It preserves both QB constructions and existing max-5 team legality. It filled five and establishes the fixed quality benchmark.

8. **Is B still the primary challenger?** It remains the clean challenger for the isolated one-QB research question. The user’s subsequent preference makes max-4/team E the primary practical challenger; F offers the stricter 3–3 choice. Do not combine changes when attributing effects.

9. **Enough evidence to change the live default today?** No tournament-success evidence supports a QB default change or permanent penalty. The requested team caps are optional controls; the existing default 5 and QB eligibility remain unchanged.

10. **What real-standings evidence remains?** Complete contest entry lineups, canonical CPT/FLEX identities, ranks/scores, payouts, entry limits and tie handling across independent games. Measure field frequency separately from top-10%, top-1%, winning Captain and conditional success distributions; stratify QB count, team split, salary and contest size. Join each frozen optimizer decision to actual contest performance, account for duplication and rake, and report game-clustered uncertainty. Actual-score oracle Captain correctness is not a substitute.

## Artifacts and validation

Machine-readable result: [`experiment-verified.json`](artifacts/showdown_qb_policy_controlled/2026w4-monday-2771d4f1/experiment-verified.json). It contains six policy results, exposure rows, exact per-lineup global ranks, higher-ranked skip blockers, A→B substitutions, A→C/B→D/team-cap comparisons, feasibility/relaxation witnesses and historical replay. Individual source freezes, candidate pools, full-universe LPs, logs, checksum envelopes and independent verification remain in the same directory.

Validation: 125 targeted backend tests plus 23 team-limit/parity checks passed; UI TypeScript/Vite build and four reporting tests passed. Browser verification selected 3 and 4 and confirmed the visible split descriptions. Local API and idle worker were reloaded successfully. The frozen selected portfolios match globally optimal selector portfolios under their exact quality/exposure constraints. No new dependency, migration, projection refit, permanent QB penalty or automatic relaxation was introduced.
