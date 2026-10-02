# Week 4 Sunday contest profiles and portfolio decision

Reviewed October 2, 2026. **Recommendation: policy D, joint maximum three primary QB stacks per canonical game and maximum four appearances per skill player, preserving stricter existing caps.** Five remains an **UNASSIGNED planning count**. The independently solved smaller-contest recommendation is Lawrence / Brown / Javonte / Higgins / Washington / Wilson / Strange / Lamb / Dolphins. No contest entry, reservation, purchase, or upload occurred.

The user supplied two contest URLs. The smaller contest is a **ticket satellite**, which changes how its payoff should be understood. The current scoring recipe is a high-score heuristic, not a calibrated satellite qualification or large-field winning model. The preferred policy is an explicit recommendation; permanent defaults and saved strategy preferences were not changed.

## Contest intent and assignments

| Intended use | Contest | Native draft group | Field capacity / captured entries | Per-user limit | Payout | Count / spend |
| --- | --- | --- | --- | --- | --- | --- |
| Larger-field GPP | [196151358: NFL $700K Play-Action](https://www.draftkings.com/draft/contest/196151358) | 154078 | 277,447 / 52,933 | 20 | $700,000; $50,000 first, $30,000 second, $20,000 third; 68,927 paid; $5 minimum | Unassigned / not supplied |
| Smaller-contest use | [196170715: NFL SUPERSat to $20 NFL Fantasy Football Millionaire, 25x](https://www.draftkings.com/draft/contest/196170715) | 154078 | 198 / 66 | 5 | Top 25 each receive one $20 Millionaire ticket; $500 total ticket value | Unassigned / not supplied |
| Friends/private single | No actual private contest supplied | 154078 assumed for preview | Unknown | Unknown | Unknown; not assumed double-up | One-lineup preview only |
| Larger-field one-lineup use | Optional one entry in Play-Action | 154078 | Same 277,447 capacity | Within 20-max | Same Play-Action ladder; no protected single-entry field | Conditional preview only |

Both supplied contests cost $3 per entry and native metadata permits late swap. Lock is October 4 at 1:00 PM EDT, with the latest game group at 4:25 PM EDT. Counts are snapshots at 14:31 UTC October 2, not predictions of the final field. The full native payout ladder, contest type, and source hashes are in [contest_profiles.json](/Users/wones/git/football_26/artifacts/week4_sunday_decision/20261002T143300Z/contest_profiles.json). The generic parser calls ticket face value “cash”; the native `tierPayoutDescriptions.Ticket` controls the satellite interpretation. No fees, rake, or ticket face-value conversion is being treated as expected cash return.

No current Sunday entry template, assignment, or explicit saved portfolio policy was found in the database inventory. Five does not establish a $15 budget or a commitment to either contest. Actual entry counts, contest assignment, intended reuse, budget, and ticket preference remain user decisions. The optional twenty-entry shadow was not run: twenty is a contest limit, not an approved paid-entry count. A different actual count requires a new solve, not truncation.

## Frozen comparison and decision

The controlled comparison uses the prior 757 known legal rosters and their admitted 400, with the same projections, normalization, family definitions, eligibility, role/risk classifier, ownership behavior, and scoring. It completed before the new source snapshot. At five entries the unchanged baseline permits six shared players, requires the saved three QB directions and two stack types, retains its automatic quality budget, and caps elevated-risk entries at three with at most one elevated player per roster. Meyers remains capped at two appearances. These are Classic constraints; Showdown CPT rules were not imported.

| Policy | Full reference selector / status | Admitted selector / status | Mean sum | Marginal P90 sum | Primary games | Max / average overlap | Elevated / uncertain skill entries |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | 28.094218181 / optimal | 28.094218181 / optimal | 658.097 | 1150.101 | {'CIN|JAX': 4, 'DAL|HOU': 1} | 6 / 4.6 | 2 / 2 |
| B | 27.982473615 / optimal | 27.982473615 / optimal | 660.776 | 1156.642 | {'ARI|NYG': 1, 'CIN|JAX': 3, 'DAL|HOU': 1} | 6 / 4.8 | 2 / 1 |
| C | 28.023978067 / optimal | 28.023978067 / optimal | 655.375 | 1148.569 | {'CIN|JAX': 4, 'DAL|HOU': 1} | 6 / 3.6 | 2 / 1 |
| D | 27.912233501 / optimal | 27.912233501 / optimal | 658.054 | 1155.110 | {'ARI|NYG': 1, 'CIN|JAX': 3, 'DAL|HOU': 1} | 6 / 3.7 | 2 / 0 |
| E | 27.724217244 / unproven | 27.784719644 / unproven | 658.198 | 1156.382 | {'ARI|NYG': 1, 'CIN|JAX': 3, 'DAL|HOU': 1} | 4 / 3.3 | 3 / 1 |

A is unchanged. B adds game max-three; C adds skill max-four; D applies both together; E adds overlap-four to D. For A–D, full and admitted solves are proven optimal at identical objectives, so admission preserves those optima. E is a feasible sensitivity with **unproven** optimization: full-run incumbent 27.724217244, upper bound 27.857097; admitted incumbent 27.784719644, upper bound 27.843940. The admitted incumbent is also feasible in the full reference, so the full best-known lower bound is at least 27.784719644. This does not prove that admission preserved the E optimum. Solver logs and bounds are in [solver_bounds.json](/Users/wones/git/football_26/artifacts/week4_sunday_decision/20261002T143300Z/solver_bounds.json). The table’s E point/exposure summaries describe the admitted incumbent; the distinct full incumbent is retained in the roster appendix and JSON. No time-limited integer incumbent is presented as an optimal production recommendation.

**Choose D** because it buys a third strong primary game while removing all universal skill cores. Relative to A it costs 0.181984679 selector (0.648%), changes projected sum by −0.043542, and adds 5.009220 summed marginal P90. Average overlap falls 4.6 → 3.7; maximum remains six. D was solved jointly, not estimated by adding independent cap costs. B retains all three universal cores; C keeps four primary stacks in CIN–JAX. E introduces a larger score cost, an extra elevated-risk entry in its admitted incumbent, and uncertain role exposure without a proof of optimum. D provides the measured compromise that matches several supported scoring paths without forcing five weak games or five distinct quarterbacks.

These sums alone neither establish superiority nor justify dismissing diversification. **Policy preference**: D best fits the stated goal. **Software correctness**: legal rosters, exact rescoring, exposure constraints and full/admitted equality are verified. **Empirical evidence**: contest-specific winning, duplication, qualification, and payout performance remain unvalidated.

### Why the concentrated baseline wins its composite

| Component | B − A | C − A | D − A | E admitted − A |
| --- | --- | --- | --- | --- |
| bring_back | -0.073767857 | -0.019671429 | -0.093439286 | -0.093439286 |
| context | -0.027681034 | -0.016516317 | -0.044197351 | -0.100172255 |
| correlation | -0.075146071 | -0.026228571 | -0.101374643 | -0.147412199 |
| duplication | +0.000000000 | +0.000000000 | +0.000000000 | +0.000000000 |
| game_environment | +0.000000000 | -0.024042857 | -0.024042857 | -0.069123214 |
| leverage | +0.000000000 | +0.000000000 | +0.000000000 | +0.000000000 |
| mean | +0.038830927 | -0.039462107 | -0.000631180 | +0.001456560 |
| other_residual | +0.000000000 | +0.000000000 | +0.000000000 | +0.000000000 |
| ownership_chalk | +0.000000000 | +0.000000000 | +0.000000000 | +0.000000000 |
| p90 | +0.089939470 | -0.021061690 | +0.068877779 | +0.086369000 |
| penalties | +0.000000000 | +0.000000000 | +0.000000000 | +0.000000000 |
| qb_stack | -0.063920000 | +0.076742857 | +0.012822857 | +0.012822857 |

B gains +0.038830927 in normalized mean and +0.089939470 in P90 terms. A retains +0.027681034 football context, +0.073767857 bring-back, +0.075146071 general correlation and +0.063920000 QB-stack contribution relative to B; game-environment contribution is unchanged. Those bonus differences outweigh the point terms, leaving B lower by 0.111744566. The scoring weights are unchanged; the lower point and marginal-P90 sums in A are compatible with its larger composite.

The saved Washington-only max-four alternative costs just 0.0061576167 selector while adding 1.061103715 mean and marginal P90. It replaces one Washington and one Schultz appearance with one Strange and one Chase. Its component changes are mean +0.015381498, P90 +0.014590388, context +0.009224069, bring-back −0.019671429, correlation −0.001639286 and environment −0.024042857; QB-stack is unchanged. It still allocates four primary stacks to CIN–JAX, leaves Javonte and Wilson universal, and increases Strange to four. That is a player-specific concentration change, not a game-level diversification policy.

### Meyers avoidance and replacement dependencies

| Shadow | Selector | Mean sum | Marginal P90 sum | Max / average overlap | Risk | New concern |
| --- | --- | --- | --- | --- | --- | --- |
| A_no_Meyers | 28.049353131 | 660.044 | 1150.698 | 6 / 4.5 | 0 | Washington/Wilson universal |
| D_no_Meyers | 27.878860468 | 665.609 | 1158.823 | 6 / 4.6 | 0 | Strange and Chase 4/5; Kalif Raymond uncertain role in 2 |

D without Meyers is proven feasible and costs 0.033373033 selector against D, with +7.555288 mean and +3.712628 marginal P90. It removes elevated risk but raises average overlap to 4.6 and moves dependency toward Strange/Chase and two uncertain-role Raymond appearances. Keep it as a measured contingency, not a silently applied exclusion. The existing classifier, projection and football assessment of Meyers remain intact. Correctly allowing two appearances is not proof that the maximum is desirable. No preference exclusion has been promoted or confused with a model injury fact.

## Individual audit of the seven portfolio drivers

The table uses pinned individual mean and marginal P90. Ranks are within the eligible same-position frame: mean, P90, P90 per $1,000, mean per $1,000. “Model targets/carries” are inferred allocations, not externally confirmed Sunday workloads. Raw prior targets/carries and actual snap counts are separate. Final numeric expected routes, targets, carries and snaps were absent for all seven; no absence was filled with a zero.

| Player / salary | Mean / P90 | Position ranks: mean / P90 / P90 value / mean value | Model role / confidence | Full / admitted candidates | Selected A / D |
| --- | --- | --- | --- | --- | --- |
| Parker Washington / $6,500 | 16.493 / 29.200 | 6 / 5 / 12 / 5 | primary option / high | 520/757 / 301/400 | 5/5 / 4/5 |
| Javonte Williams / $6,600 | 17.859 / 30.985 | 3 / 3 / 2 / 3 | offensive centerpiece / high | 605/757 / 346/400 | 5/5 / 4/5 |
| Michael Wilson / $5,500 | 15.119 / 27.825 | 10 / 9 / 3 / 1 | primary option / high | 549/757 / 345/400 | 5/5 / 4/5 |
| Jakobi Meyers / $5,000 | 11.025 / 22.156 | 20 / 21 / 14 / 16 | major secondary option / high | 145/757 / 100/400 | 2/5 / 2/5 |
| Brenton Strange / $3,200 | 8.300 / 15.430 | 12 / 13 / 4 / 1 | major secondary option / high | 264/757 / 183/400 | 3/5 / 3/5 |
| Mike Gesicki / $3,300 | 8.117 / 13.984 | 14 / 19 / 9 / 6 | regular contributor / high | 43/757 / 41/400 | 1/5 / 0/5 |
| Ryan Flournoy / $3,800 | 8.994 / 18.717 | 32 / 37 / 6 / 10 | major secondary option / high | 107/757 / 93/400 | 1/5 / 2/5 |

| Player | Measured targets W1 / W2 / W3 | Measured carries W1 / W2 / W3 | Measured offensive snaps W1 / W2 / W3 | Model targets / carries | Practice / availability consumed |
| --- | --- | --- | --- | --- | --- |
| Parker Washington | 6 / 12 / 5 | 0 / 0 / 0 | 35 (61%) / 48 (81%) / 50 (81%) | 8.121 / missing | No injury/practice row consumed; final clearance missing |
| Javonte Williams | 5 / 4 / 3 | 12 / 12 / 19 | 41 (71%) / 44 (80%) / 56 (76%) | 3.716 / 12.487 | No injury/practice row consumed; final clearance missing |
| Michael Wilson | 7 / 7 / 17 | 0 / 0 / 0 | 64 (85%) / 47 (94%) / 81 (93%) | 9.124 / missing | No injury/practice row consumed; final clearance missing |
| Jakobi Meyers | 2 / 1 / 8 | 1 / 0 / 0 | 37 (65%) / 53 (90%) / 50 (81%) | 3.840 / missing | DK Q; LIMITED thumb; questionable_elevated; cap 2/5 |
| Brenton Strange | 3 / 2 / 5 | 0 / 0 / 0 | 39 (68%) / 49 (83%) / 48 (77%) | 3.614 / missing | No injury/practice row consumed; final clearance missing |
| Mike Gesicki | 7 / MISSING / 3 | 0 / MISSING / 0 | 21 (33%) / 21 (35%) / 29 (51%) | 3.475 / missing | No injury/practice row consumed; final clearance missing |
| Ryan Flournoy | 4 / 6 / 8 | 0 / 0 / 0 | 41 (71%) / 42 (76%) / 49 (66%) | 5.282 / missing | No injury/practice row consumed; final clearance missing |

Raw Gesicki Week 2 stats are missing, despite an independently present Week 2 snap row. The other six have all three measured stat rows. First-string depth is an unofficial club expectation, not a supplied numeric workload. Model confidence reflects prior evidence, not certainty about Sunday. The role flag used for portfolio diagnostics is **skill players explicitly uncertain, BACKUP, or missing current role label**; DST is excluded from this role diagnostic. Frozen D has zero such skill entries. This is separate from injury-elevated risk: Meyers has a high prior-role confidence but uncertain current workload due to his thumb/practice evidence.

**Parker Washington.** Top-six WR mean and the best inexpensive competing alternatives in this frame support inclusion. The Lawrence-stack correlation contribution involving him is 0.236453; Burrow bring-back 0.131143; Dak one-off 0. None of the baseline salary slack (0–400) admits a same-position peer nonworse on both mean and P90. He is a high-projection option at $6,500, not a generic punt.

| Best legal solve | Selector | Mean | Marginal P90 | Exact construction / stable hash |
| --- | --- | --- | --- | --- |
| avoiding | 5.617278446 | 132.167 | 230.801 | Trevor Lawrence, Chase Brown, Javonte Williams, Michael Wilson, Jakobi Meyers, Zay Flowers, Brenton Strange, Ja'Marr Chase, Rams; `dfaa320c8061c2dfebd709dd384b67619ba0f405262f6c18fb42c13c976f4476` |
| containing | 5.680238848 | 133.544 | 233.753 | Trevor Lawrence, Chase Brown, Javonte Williams, Tee Higgins, Parker Washington, Michael Wilson, Brenton Strange, CeeDee Lamb, Dolphins; `92bbd4f894074fe06411750eab2075e6d3ec5fe21728d4b034bcc650beeb9785` |

**Javonte Williams.** RB mean/P90 rank three and strong value support frequent use; carries and snaps were sustained across three games. His contribution is usually independent of QB-stack bonuses (zero in the non-Dak baseline rosters; 0.024043 with Dak). No same-position nonworse player fits the measured slack.

| Best legal solve | Selector | Mean | Marginal P90 | Exact construction / stable hash |
| --- | --- | --- | --- | --- |
| avoiding | 5.644709926 | 132.670 | 231.471 | Trevor Lawrence, Chase Brown, Kenneth Walker III, Ryan Flournoy, Parker Washington, Michael Wilson, Brenton Strange, Ja'Marr Chase, Rams; `cfdf2a38b37934c60508ed1c1038c48eae14f4ebe59fe6ba47eb4383d1611a0f` |
| containing | 5.680238848 | 133.544 | 233.753 | Trevor Lawrence, Chase Brown, Javonte Williams, Tee Higgins, Parker Washington, Michael Wilson, Brenton Strange, CeeDee Lamb, Dolphins; `92bbd4f894074fe06411750eab2075e6d3ec5fe21728d4b034bcc650beeb9785` |

**Michael Wilson.** WR mean rank ten, P90 rank nine, and strong value are supported by targets and 85–94% snaps. He is a one-off in every baseline roster with zero player-involving correlation contribution, so this universal dependency is principally projection/value, not stacked bonus accumulation.

| Best legal solve | Selector | Mean | Marginal P90 | Exact construction / stable hash |
| --- | --- | --- | --- | --- |
| avoiding | 5.650444839 | 129.416 | 226.641 | Trevor Lawrence, Kenneth Walker III, Javonte Williams, Ryan Flournoy, Parker Washington, Jakobi Meyers, Brenton Strange, Ja'Marr Chase, Rams; `0bf47c00186f5d96438820dbe6b77080378c6845f99bf81fb7e960ac5a4c489c` |
| containing | 5.680238848 | 133.544 | 233.753 | Trevor Lawrence, Chase Brown, Javonte Williams, Tee Higgins, Parker Washington, Michael Wilson, Brenton Strange, CeeDee Lamb, Dolphins; `92bbd4f894074fe06411750eab2075e6d3ec5fe21728d4b034bcc650beeb9785` |

**Jakobi Meyers.** Prior targets were 2, 1, then 8: the latest game alone should not be promoted to a guaranteed full role. Lawrence correlation contribution is 0.236453 and Burrow 0.131143, so his selected use is meaningfully stack-dependent. LIMITED thumb practice was captured October 2 at 13:24:40 UTC and refreshed without a semantic change; no final inactive designation or current numeric workload was supplied. Golden/Burden can fit some baseline slack on raw point comparisons, but a full legal stack-aware re-solve is required.

| Best legal solve | Selector | Mean | Marginal P90 | Exact construction / stable hash |
| --- | --- | --- | --- | --- |
| avoiding | 5.680238848 | 133.544 | 233.753 | Trevor Lawrence, Chase Brown, Javonte Williams, Tee Higgins, Parker Washington, Michael Wilson, Brenton Strange, CeeDee Lamb, Dolphins; `92bbd4f894074fe06411750eab2075e6d3ec5fe21728d4b034bcc650beeb9785` |
| containing | 5.679441267 | 129.966 | 228.600 | Trevor Lawrence, Kenneth Walker III, Javonte Williams, Tee Higgins, Parker Washington, Michael Wilson, Brenton Strange, Jakobi Meyers, Rams; `7bd263e0905c0b73753160ff073be549ac62b9d4d3c3a49cac6946cbf6a1f7bf` |

**Brenton Strange.** $3,200 provides real salary relief and the best TE mean value in this frame, supported by high snaps. Lawrence-stack contribution is 0.236453; some baseline slack admits Otton/Mayer nonworse on mean/P90, but changes to team and stack structure must be solved, not asserted as free swaps.

| Best legal solve | Selector | Mean | Marginal P90 | Exact construction / stable hash |
| --- | --- | --- | --- | --- |
| avoiding | 5.642702531 | 131.434 | 234.243 | Trevor Lawrence, Chase Brown, Javonte Williams, Parker Washington, Michael Wilson, Jakobi Meyers, Cade Otton, Ja'Marr Chase, Rams; `0bc3c835551692d06ad356fc38c3233ce23273f46e2b61dbdb174f46e718a5c6` |
| containing | 5.680238848 | 133.544 | 233.753 | Trevor Lawrence, Chase Brown, Javonte Williams, Tee Higgins, Parker Washington, Michael Wilson, Brenton Strange, CeeDee Lamb, Dolphins; `92bbd4f894074fe06411750eab2075e6d3ec5fe21728d4b034bcc650beeb9785` |

**Mike Gesicki.** $3,300 helps the Burrow construction; baseline player-involving correlation contribution 0.272047 is substantial. His 33–51% snaps and missing Week 2 stats limit the workload argument despite first-string depth. Strange/Hockenson can be affordable on individual comparisons but change stack relationships. D does not select him.

| Best legal solve | Selector | Mean | Marginal P90 | Exact construction / stable hash |
| --- | --- | --- | --- | --- |
| avoiding | 5.680238848 | 133.544 | 233.753 | Trevor Lawrence, Chase Brown, Javonte Williams, Tee Higgins, Parker Washington, Michael Wilson, Brenton Strange, CeeDee Lamb, Dolphins; `92bbd4f894074fe06411750eab2075e6d3ec5fe21728d4b034bcc650beeb9785` |
| containing | 5.630144277 | 132.382 | 231.749 | Trevor Lawrence, Chase Brown, Kenneth Walker III, Parker Washington, Michael Wilson, Jakobi Meyers, Mike Gesicki, Javonte Williams, Rams; `54653cab0ffcf873824464cbb24185e27fa5b2524d10ee6c76272380ee4b8536` |

**Ryan Flournoy.** $3,800 is genuine salary relief, with 4→6→8 targets and 66–76% snaps. Dak-stack contribution 0.176254 supports his use. An individually nonworse affordable Kalif Raymond does not provide a clean role-equivalent replacement; Raymond has explicit uncertainty. A modest projection alone does not make this Classic value a bad play.

| Best legal solve | Selector | Mean | Marginal P90 | Exact construction / stable hash |
| --- | --- | --- | --- | --- |
| avoiding | 5.680238848 | 133.544 | 233.753 | Trevor Lawrence, Chase Brown, Javonte Williams, Tee Higgins, Parker Washington, Michael Wilson, Brenton Strange, CeeDee Lamb, Dolphins; `92bbd4f894074fe06411750eab2075e6d3ec5fe21728d4b034bcc650beeb9785` |
| containing | 5.650444839 | 129.416 | 226.641 | Trevor Lawrence, Kenneth Walker III, Javonte Williams, Ryan Flournoy, Parker Washington, Jakobi Meyers, Brenton Strange, Ja'Marr Chase, Rams; `0bf47c00186f5d96438820dbe6b77080378c6845f99bf81fb7e960ac5a4c489c` |

Containing/avoiding results are independent optimal legal lineup solves on the frozen eligible player model, with the unchanged per-lineup elevated limit. They are not the stricter zero-elevated one-entry recommendation and do not imply the feasibility of five copies. Exact slots, native IDs, salaries, components and solver events for all fourteen are in [player_audits.json](/Users/wones/git/football_26/artifacts/week4_sunday_decision/20261002T143300Z/player_audits.json). Salary-affordable peers are diagnostics, not certified unconditional replacements.

For the three universal baseline cores, reducing the model’s role-importance feature alone by 0.2 changes the stored pre-opportunity mean by −0.266973 Washington, −0.315950 Javonte, and −0.266973 Wilson. This is a one-feature sensitivity with fixed distributions, not a realistic injury/usage simulation or a joint outcome quantile. The observed roles support substantial exposure but do not authorize 100% cores. One-fewer-appearance portfolio solves cost 0.006157617, 0.030014686 and 0.028248404 respectively; those remain game-concentrated. D caps all skill players together and reveals the remaining near-cores instead of merely renaming a universal dependency.

## Separate single-lineup decisions

The friends/smaller preview was independently globally solved with the existing Classic composite and conservative zero-elevated one-entry budget. It was also checked against count-one pool selection; it was not chosen by taking the first portfolio roster. The assumed objective is existing high-scoring GPP construction (0.35 mean / 0.48 ceiling / 0.17 correlation, leverage zero), not mean alone or a satellite qualification probability. Before UI integration the automatic multi-entry QB/core caps rounded a one-entry QB cap to zero; the corrected UI now omits only those automatic multi-entry diversity caps at count one. Explicit user caps and injury/risk caps remain effective.

### Preferred friends / smaller satellite single

**Preferred friends / smaller satellite single 1:** $49,700; mean 133.544; summed marginal P90 233.753; selector 5.680238848; gap from common individual frontier 0.000000000. Stable canonical roster hash `92bbd4f894074fe06411750eab2075e6d3ec5fe21728d4b034bcc650beeb9785`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | CeeDee Lamb | 44312566 | $7,800 |
| DST | Dolphins | 44313331 | $2,000 |

### Closest legal runner-up

**Closest legal runner-up 1:** $49,800; mean 133.497; summed marginal P90 233.706; selector 5.678915711; gap from common individual frontier 0.001323137. Stable canonical roster hash `6c276c4e8c19e65489ad3732b1022dd7fe10cea9075ff4811599acc9a739cfd0`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | CeeDee Lamb | 44312566 | $7,800 |
| DST | Titans | 44313330 | $2,100 |

### Credible different-QB alternative

**Credible different-QB alternative 1:** $50,000; mean 126.511; summed marginal P90 222.367; selector 5.562477252; gap from common individual frontier 0.117761595. Stable canonical roster hash `77232f3f33c35749c18231ae0a40236307b32cc74a819634e3a0ffe3fae5a586`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Joe Burrow | 44312199 | $6,800 |
| RB | Javonte Williams | 44312288 | $6,600 |
| RB | Rhamondre Stevenson | 44312328 | $5,100 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Mike Gesicki | 44313052 | $3,300 |
| FLEX | Ja'Marr Chase | 44312564 | $8,100 |
| DST | Dolphins | 44313331 | $2,000 |

The different-QB alternative buys the Burrow side of the high-total CIN–JAX game with Higgins/Gesicki/Chase and Washington as the return. It is lower by 0.117761595 selector and has Gesicki role uncertainty. The closest runner-up differs only at DST; it is evidence of a small defensive distinction, not another independent football path. For one entry in Play-Action, the same independently solved preferred construction is a conditional high-score recommendation. No actual dedicated single-entry contest was supplied, and its duplication/field suitability has not been validated. Neither supplied contest is technically single-entry.

## Recommended five-entry GPP planning portfolio after refresh

The refresh re-earned the same D roster hashes and scores: full/admitted equality holds again at 27.912233501. The five paths comprise three Lawrence variants, a Brissett/McBride Cardinals stack, and a Dak/Pickens/Flournoy/Lamb Cowboys stack. This keeps three QB directions and three primary games; there is no forced weak fifth game. Each additional entry contributes a construction conditional on specific player outcomes rather than an independent lottery ticket.

### D larger-field planning

**D larger-field planning 1:** $49,800; mean 133.497; summed marginal P90 233.706; selector 5.678915711; gap from common individual frontier 0.001323137. Stable canonical roster hash `6c276c4e8c19e65489ad3732b1022dd7fe10cea9075ff4811599acc9a739cfd0`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | CeeDee Lamb | 44312566 | $7,800 |
| DST | Titans | 44313330 | $2,100 |

**D larger-field planning 2:** $49,800; mean 135.221; summed marginal P90 232.209; selector 5.676047750; gap from common individual frontier 0.004191098. Stable canonical roster hash `0cf73b654437c9700d8cc5ac35acdaac99567943251489bb84a2ea56e64c43bc`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Kyren Williams | 44312308 | $5,900 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| WR | Ja'Marr Chase | 44312564 | $8,100 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Javonte Williams | 44312288 | $6,600 |
| DST | Dolphins | 44313331 | $2,000 |

**D larger-field planning 3:** $49,900; mean 129.416; summed marginal P90 226.641; selector 5.650444839; gap from common individual frontier 0.029794009. Stable canonical roster hash `0bf47c00186f5d96438820dbe6b77080378c6845f99bf81fb7e960ac5a4c489c`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Ryan Flournoy | 44312678 | $3,800 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Jakobi Meyers | 44312618 | $5,000 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Ja'Marr Chase | 44312564 | $8,100 |
| DST | Rams | 44313323 | $2,600 |

**D larger-field planning 4:** $49,900; mean 129.948; summed marginal P90 231.181; selector 5.460866395; gap from common individual frontier 0.219372453. Stable canonical roster hash `7ef0cc982a08600f075367ee99661ed8f45bd947ea6b666573bffe2546eed37a`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Jacoby Brissett | 44312217 | $5,000 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Trey McBride | 44313020 | $6,500 |
| FLEX | Jakobi Meyers | 44312618 | $5,000 |
| DST | Rams | 44313323 | $2,600 |

**D larger-field planning 5:** $50,000; mean 129.972; summed marginal P90 231.372; selector 5.445958807; gap from common individual frontier 0.234280040. Stable canonical roster hash `dda137c4a28c1fbf2383e2ee9ec2846a3d3f501981c68516b894414d5f027c97`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Dak Prescott | 44312203 | $6,400 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| WR | George Pickens | 44312590 | $6,300 |
| WR | Ryan Flournoy | 44312678 | $3,800 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Cade Otton | 44313048 | $3,400 |
| FLEX | CeeDee Lamb | 44312566 | $7,800 |
| DST | Cardinals | 44313325 | $2,500 |

Entry 1 pairs the JAX pass stack with Higgins and a Lamb one-off; entry 2 expresses Brown plus Chase and Kyren; entry 3 uses Walker, Flournoy and Meyers around the Lawrence/Strange/Chase construction. Entry 4 changes the primary engine to Brissett/McBride while retaining CIN/DAL skill value; entry 5 changes it to Dak with three Dallas pass catchers and Walker/Otton. All remain model-supported high-scoring constructions; this is a several-family planning portfolio using existing scoring, not a newly calibrated large-field strategy.

| Player | Appearances |
| --- | --- |
| Chase Brown | 4/5 |
| Javonte Williams | 4/5 |
| Michael Wilson | 4/5 |
| Parker Washington | 4/5 |
| Brenton Strange | 3/5 |
| Trevor Lawrence | 3/5 |
| CeeDee Lamb | 2/5 |
| Ja'Marr Chase | 2/5 |
| Jakobi Meyers | 2/5 |
| Kenneth Walker III | 2/5 |
| Rams | 2/5 |
| Ryan Flournoy | 2/5 |
| Tee Higgins | 2/5 |
| Cade Otton | 1/5 |
| Cardinals | 1/5 |
| Dak Prescott | 1/5 |
| Dolphins | 1/5 |
| George Pickens | 1/5 |
| Jacoby Brissett | 1/5 |
| Kyren Williams | 1/5 |
| Titans | 1/5 |
| Trey McBride | 1/5 |

| Canonical game | Primary QB stacks | Any-player entries | Player appearances |
| --- | --- | --- | --- |
| ARI|NYG | 1 | 4 | 7 |
| BAL|TEN | 0 | 1 | 1 |
| CIN|JAX | 3 | 5 | 20 |
| DAL|HOU | 1 | 5 | 10 |
| GB|TB | 0 | 1 | 1 |
| KC|LV | 0 | 2 | 2 |
| LAR|PHI | 0 | 3 | 3 |
| MIA|MIN | 0 | 1 | 1 |

**Remaining dependencies:** Washington, Javonte, Wilson and Brown each appear four times; Lawrence and Strange three. CIN–JAX and DAL–HOU have at least one player in all five entries even though their primary-QB allocation is only three and one. ARI–NYG appears in four through one-offs/Brissett. Thus a game cap limits primary stack engines, not all exposure to the game. Meyers appears twice, hitting the existing two-entry limit. No skill player is universal, but four near-cores remain.

| Shared pair in at least three entries | Entries |
| --- | --- |
| Chase Brown + Michael Wilson | 4 |
| Parker Washington + Javonte Williams | 4 |
| Chase Brown + Parker Washington | 3 |
| Chase Brown + Javonte Williams | 3 |
| Parker Washington + Trevor Lawrence | 3 |
| Parker Washington + Michael Wilson | 3 |
| Parker Washington + Brenton Strange | 3 |
| Javonte Williams + Trevor Lawrence | 3 |
| Javonte Williams + Michael Wilson | 3 |
| Javonte Williams + Brenton Strange | 3 |
| Trevor Lawrence + Brenton Strange | 3 |

| Shared triple in at least three entries | Entries |
| --- | --- |
| Chase Brown + Parker Washington + Javonte Williams | 3 |
| Chase Brown + Parker Washington + Michael Wilson | 3 |
| Chase Brown + Javonte Williams + Michael Wilson | 3 |
| Parker Washington + Javonte Williams + Trevor Lawrence | 3 |
| Parker Washington + Javonte Williams + Michael Wilson | 3 |
| Parker Washington + Javonte Williams + Brenton Strange | 3 |
| Parker Washington + Trevor Lawrence + Brenton Strange | 3 |
| Javonte Williams + Trevor Lawrence + Brenton Strange | 3 |

Every pair/triple with at least two appearances, and each policy’s individual lineup gaps/components, complete exposure table, any-player game counts and overlap matrix, are saved in [all_shared_dependencies.json](/Users/wones/git/football_26/artifacts/week4_sunday_decision/20261002T143300Z/all_shared_dependencies.json) and [decision.json](/Users/wones/git/football_26/artifacts/week4_sunday_decision/20261002T143300Z/decision.json). No pairwise independence is assumed.

## Source refresh, model lineage and remaining clearance

The controlled comparison was sealed before new capture [capture_manifest.json](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/capture_manifest.json). Eighty-four approved public sources were fetched successfully, alongside the official starter/venue evidence. Native salaries and prior Week 1–3 statistics were unchanged. Selected/core ARI/DAL/JAX/CIN depth and injury tables had no semantic change; dynamic HTML hashes may differ. Meyers remains LIMITED with a thumb injury. Other audited players still lack a consumed current practice/inactive row; absence does not mean FULL or cleared.

**TB:** the club’s October 1 preview explicitly names Jalon Daniels starting against Green Bay and describes Mayfield’s thumb rehabilitation/missed games. Daniels is now confirmed in the canonical starter mechanism, while Mayfield remains OUT; no current numeric workload was invented. The independent best legal Daniels alternative has selector 5.048196853, mean 121.039900 and marginal P90 223.848993, with a 0.632041995 gap from the preferred single. It does not earn a forced family in D. [Official Buccaneers preview](https://www.buccaneers.com/news/2026-game-preview-packers-buccaneers-week-4), [club starter interview](https://www.buccaneers.com/news/jalon-daniels-baker-mayfield-told-me-to-just-be-myself).

**NE–BUF:** the retired physical venue ended in 2025. A distinct `venue-us-buf-highmark-2026:v1` and explicit `2026_04_NE_BUF:v1` game mapping now use the official stadium map center (42.773124779088, −78.790935606096), an approximate venue coordinate rather than a surveyed field point. Only that reviewed game mapping was updated; the old venue and unrelated maps were retained. Existing approved Open-Meteo/NCEP GFS capture now succeeds for all twelve games. Forecast provider issue time is absent; server receipt time is the availability basis. This is October 2 weather evidence, not Sunday clearance. [Official Bills stadium/map](https://www.buffalobills.com/stadium/), [official Week 4 game announcement](https://www.buffalobills.com/news/what-bills-fans-can-expect-at-highmark-stadium-for-week-4-vs-patriots). Details: [venue_resolution.json](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/venue_resolution.json), [weather_refresh.json](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/weather_refresh.json).

**Markets:** the approved nflverse Sunday schedule capture was retrieved at 14:40:10 UTC. Spread and total values are unchanged across all twelve games. LA–PHI moneylines changed −180/+150 → −185/+154, which is recorded separately; no change in selector-used spread/total was claimed. The provider supplied no underlying price observation/update times. Feature `market_observed_at` is a capture-based timestamp and cannot prove the line itself was updated then. No live sportsbook price was manufactured or substituted. [market_value_comparison.json](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/market_value_comparison.json) preserves exact compared values and paths.

**Identity:** At the separately captured source-preparation stage, 629 native salary rows had 611 resolved identities and 18 quarantined rows with queue provenance. The later existing UI reconciliation resolved eleven more: current readback has 622 resolved and seven still unresolved. The fresh UI projection has 392 players versus 389 in the earlier reviewed frame; those stages are not conflated. None is a reviewed selected player or one of the seven audit targets. Native IDs and canonical UUIDs drive joins. This limits global claims to the eligible resolved model; no unresolved identity was joined by raw name or dropped silently. [preparation.json](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/preparation.json) retains the earlier identities; [ui_identity_readback.json](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/ui_identity_readback.json) records the current unresolved set and eleven newly resolved canonical IDs.

Final refreshed projection `849d0a36-ecc4-49c3-a0ce-40e2d31733d0`; model `79aa20eb-5e92-4d78-bcbc-8c7d8a0616ff`; feature run `4a4c3de0-0a81-4e01-a587-73ed455f58fc`; model recipe `gradient_boosting_challenger_v4_2_market_corrected`; cutoff `2026-10-02T14:45:01.097759Z`. Model-code hash `a0b1f30e4ccf72167c6d6e8955dd2520b3d6ed660e48fc0b7f7d2512c2b18510` is unchanged. The newly captured training dataset and fitted artifact hashes differ, and are recorded rather than called identical: dataset `c365f31b66dc7a53a76a2e0061e1d508303ded615ea0df06e6560b93c8e3f914`, artifact `c3fec090e55904dcae8cd546e5a899e31d23f776dd560ef761a1811f4856782e`. Prior model readback matches; reviewed selected-player predictions and all preferred roster scores/hashes remain equal. Source context `5b49488f-991b-4569-b0b3-f3ae109172c6` confirms TB. Details: [model_comparison.json](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/model_comparison.json).

Existing discovery reran 640 mandatory requests, with QB enumeration bounded at fifty and common baseline rescoring. The refreshed union again contains 757 known legal rosters and an admitted 400. Refreshed application control `0859b9a1-2e34-430d-bf13-2b9f1b57ab4c`; discovery preview `b86d1852-6a5b-4576-b82e-a01598aa19ea`; reviewed recommendation digest `881c1cc3e7f24aef8ebc679f9d27c0438461372adc9aef60a1df4fb0cb74501e`. This reference is not exhaustive over all legal portfolios. No simulator was built or activated.

### Ownership and duplication

Available ownership is `slate_aware_ownership_v2_prelock`, run `0fedee65-ed06-45b9-87cf-2aa925d48b8b`, created October 2 at 01:26:15 UTC, cutoff 01:26:12 UTC. Coverage was 329/332 in the frozen eligible frame. Its historical walk-forward diagnostics cover 4,533 rows from 4,908 training rows, MAE 3.102756 versus 4.109226 baseline, rank correlation 0.713624; promotion checks passed as diagnostics. Classic DST rank correlation was only 0.1677 and FLEX bias +1.12124. These checks do not validate ownership or whole-roster duplication in the current 277,447-player Play-Action or 198-entry satellite. The unchanged approved selector has ownership/leverage unavailable or disabled at weight zero; missing is not zero ownership. Player ownership may appear in diagnostics, but neither a sum nor product supplies a calibrated roster duplication probability. No validated joint contest-field model was used; win probability, expected payout and joint lineup P90 are unavailable.

## UI runbook and acceptance evidence

The original scripts were insufficient to guarantee UI reproduction. The added controls are opt-in, reuse the existing discovery/selection/scoring mechanisms, and do not change permanent defaults. In **Operations → Portfolio optimizer**, select **2026 / Week 4 / SUNDAY MAIN / Classic / Small-field GPP · diagnostic baseline**. For reviewed D set Lineups 5, Max Exposure 100%, Max primary QB stacks per game 3, Max appearances per skill player 4, Max shared players 6, and enable Expanded candidate discovery (slower). Leave Different QB in each lineup unchecked and selector loss blank. Keep single TE and no offense vs DST enabled. Retain the saved DEN opponent exclusion for the frozen comparison; clear only additional exclusions/locks outside that frame. This is a user preference applied to eligibility, with model assessments retained. The added controls are per-run preferences and reset with a page reload; reapply these settings after reopening the UI. The reporting URL can be Play-Action; it does not purchase or assign entries. “Large GPP” is a different technical strategy and will not silently inherit this reviewed small-field composite.

For the single preview, request one lineup, clear the primary-game/skill-count caps, and use expanded discovery under the same diagnostic strategy. The zero-elevated risk budget remains active. Actual count changes are re-solved by the UI. Run Optimizer performs identity reconciliation, feature rebuild, starter resolution, current projection generation, readiness, candidate discovery, selection and saved readback. New source or availability choices can legitimately change the result; exact historical replay uses the saved frozen manifests instead.

The first browser run exposed iCloud `EDEADLK` on a starter raw snapshot. A verified local storage replica now permits recapture/readback of the identical snapshot ID and bytes without changing the immutable database row, original raw file, observation time or hash. Integrity mismatches remain errors. Manifest `storage_replica_of` and [qb_snapshot_storage_recovery.json](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/qb_snapshot_storage_recovery.json) record provenance. The database rejected an attempted pointer relocation, which rolled back; the final implementation uses a detached storage view and never modifies the immutable row.

Actual browser five-lineup run `c442e072-db66-4214-b604-75d402449545` completed with projection `58ff8543-09f8-469c-a833-47a984de8cf2` and fitted model artifact `a4f01862-df0f-4379-9fca-0ee168977e2a`. Its saved requested/effective contract independently verified game cap 3, skill cap 4, overlap 6 and five legal rosters. The canonical roster set equals reviewed D. This UI test accidentally cleared DEN and therefore used a broader pool (348 eligible players, 775 known legal rosters, 659 mandatory requests); its numerical scores are not the controlled frozen comparison. DEN was restored afterward. Evidence: [ui_five_validation.json](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/ui_five_validation.json), [ui_five_readback.json](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/ui_five_readback.json).

Saved UI solver inputs also include all seven audit targets and confirmed TB starter Daniels, joined by canonical ID: [ui_consumed_source_evidence.json](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/ui_consumed_source_evidence.json).

The independent one-lineup browser run `9d529171-4062-4b79-9422-6719d81e675c` completed using projection `8b2588bd-b6e4-4c47-8a61-5b8cf7e2052d`, with fitted model artifact `81f74c1c-3231-43da-b8ae-2c5141b512d1`, DEN retained and appearance/game-count preferences cleared. It selected the same preferred nine-player roster, canonical hash `92bbd4f894074fe06411750eab2075e6d3ec5fe21728d4b034bcc650beeb9785`, salary $49,700. Its current selector is 5.680455902385179, equal to its independently proven global legal frontier; mean 133.551585 and summed marginal P90 233.761017. The saved pool has 675 legal rosters from 637 mandatory requests and 334 eligible players. This is a fresh UI solve, not truncation of five. [ui_single_validation.json](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/ui_single_validation.json) retains the exact metrics and requested/effective contract. Expanded-preview screens and readable exports distinguish saved-input readiness from contest assignment, final inactives and unvalidated large-field performance.

Both native download endpoints returned HTTP 200 and their CSV rows matched the saved native IDs: [single CSV](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/ui_single_draftkings_download.csv), [five CSV](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/ui_five_draftkings_download.csv). These are unassigned review copies, not submitted entries. The actual UI report renderer also produced both saved readable reports with the planning qualification: [single HTML](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/ui_single_readable.html), [five HTML](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/ui_five_readable.html). UI buttons were clicked; browser automation did not return the readable download file path before its event timed out, so that path is not claimed verified. The native endpoint output and readable renderer were checked separately. Ownership refresh was disabled only for these verification runs to retain the prior ownership evidence, then its original checked preference was restored.

![Completed single-lineup UI run](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/ui_single_completed.jpg)

Validation completed: 53 focused source/storage/Sunday/starter tests, 47 selection/reconciliation tests, 19 current candidate-discovery contracts, 41 UI tests and the TypeScript/Vite build. Two older candidate-discovery fixture tests reject changed runtime hashes (`classic_prospective.py`); they are not counted as passing and their immutable historical fixtures were not rewritten. The preserved Sunday runtime separately replayed all 62 rosters and verified all 443 prior bundle files. Prior application readback retains the exact saved report and roster fields; its response adds only 45 slot-index fields. [preservation_readback.json](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/preservation_readback.json).

## Exact saved outputs and retrieval

Reviewed planning outputs from the separately frozen source-refresh frame: [reviewed_recommendations.json](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/execution/reviewed_recommendations.json). Frozen A–E comparison: [decision.json](/Users/wones/git/football_26/artifacts/week4_sunday_decision/20261002T143300Z/decision.json). Frozen digest `3314b7ea94e678164982ad624d298498e8329847bfa53d47eee59932990b6610`. Native roster manifest: [reviewed_native_manifest.json](/Users/wones/git/football_26/artifacts/week4_sunday_source_update/20261002T143712Z/execution/reviewed_native_manifest.json). Every native slot ID is verified against draft group 154078. This is a review manifest, not an uploaded entry file.

```sh
# Read the actual reviewed current recommendations
cat artifacts/week4_sunday_source_update/20261002T143712Z/execution/reviewed_recommendations.json
# Replay the preserved pre-integration runtime without changing its freeze
PYTHONPATH=. PYTHONHASHSEED=0 .venv/bin/python artifacts/week4_sunday_decision/20261002T143300Z/verify_frozen_runtime.py
```

The prior opt-in preview `13f26f3d-6555-4225-9291-23693b4f547a`, application control `709df965-1b74-42b2-a9d4-7e5e86d9028b`, projection `6bc7a78c-3cb7-4a6e-98db-369c5b8dd384`, and all 443 files in `artifacts/week4_sunday_readiness/20261002T132342Z` remain preserved. The archived runtime permits their exact code-hash replay after additive UI integration. Current preferences are explicit per-run controls; no scoring/ownership/model recipe/injury threshold was promoted.

## Frozen roster appendix

Each A–D full/admitted optimum has the same objective and construction in this run; their JSONs retain separate solves. E retains both distinct unproven incumbents. Appendix scores always use the controlled prior frame. Shared-pair/triple and exposure data for every row below remain in the companion JSON; these are measured alternatives, not selected entry assignments.

### A_full757

**A_full757 1:** $49,600; mean 129.966; summed marginal P90 228.600; selector 5.679441267; gap from common individual frontier 0.000797580. Stable canonical roster hash `7bd263e0905c0b73753160ff073be549ac62b9d4d3c3a49cac6946cbf6a1f7bf`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Jakobi Meyers | 44312618 | $5,000 |
| DST | Rams | 44313323 | $2,600 |

**A_full757 2:** $49,800; mean 133.497; summed marginal P90 233.706; selector 5.678915711; gap from common individual frontier 0.001323137. Stable canonical roster hash `6c276c4e8c19e65489ad3732b1022dd7fe10cea9075ff4811599acc9a739cfd0`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | CeeDee Lamb | 44312566 | $7,800 |
| DST | Titans | 44313330 | $2,100 |

**A_full757 3:** $49,800; mean 135.221; summed marginal P90 232.209; selector 5.676047750; gap from common individual frontier 0.004191098. Stable canonical roster hash `0cf73b654437c9700d8cc5ac35acdaac99567943251489bb84a2ea56e64c43bc`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Kyren Williams | 44312308 | $5,900 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| WR | Ja'Marr Chase | 44312564 | $8,100 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Javonte Williams | 44312288 | $6,600 |
| DST | Dolphins | 44313331 | $2,000 |

**A_full757 4:** $50,000; mean 127.269; summed marginal P90 224.641; selector 5.572610961; gap from common individual frontier 0.107627887. Stable canonical roster hash `324fe63f76ce6e16c502418f9dc9ca78fb247e64421bafed9970dd76f20447cc`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Joe Burrow | 44312199 | $6,800 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Mike Gesicki | 44313052 | $3,300 |
| FLEX | Jakobi Meyers | 44312618 | $5,000 |
| DST | Dolphins | 44313331 | $2,000 |

**A_full757 5:** $50,000; mean 132.144; summed marginal P90 230.945; selector 5.487202492; gap from common individual frontier 0.193036356. Stable canonical roster hash `da077dcf1cf6484127ab66e7ca49d329e0dcad959b395bf2cfb7c05ac08c08e6`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Dak Prescott | 44312203 | $6,400 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Ryan Flournoy | 44312678 | $3,800 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Dalton Schultz | 44313028 | $4,800 |
| FLEX | CeeDee Lamb | 44312566 | $7,800 |
| DST | Cardinals | 44313325 | $2,500 |

| Player | Appearances |
| --- | --- |
| Javonte Williams | 5/5 |
| Michael Wilson | 5/5 |
| Parker Washington | 5/5 |
| Brenton Strange | 3/5 |
| Chase Brown | 3/5 |
| Tee Higgins | 3/5 |
| Trevor Lawrence | 3/5 |
| CeeDee Lamb | 2/5 |
| Dolphins | 2/5 |
| Jakobi Meyers | 2/5 |
| Kenneth Walker III | 2/5 |
| Cardinals | 1/5 |
| Dak Prescott | 1/5 |
| Dalton Schultz | 1/5 |
| Ja'Marr Chase | 1/5 |
| Joe Burrow | 1/5 |
| Kyren Williams | 1/5 |
| Mike Gesicki | 1/5 |
| Rams | 1/5 |
| Ryan Flournoy | 1/5 |
| Titans | 1/5 |

| Canonical game | Primary QB stacks | Any-player entries | Player appearances |
| --- | --- | --- | --- |
| ARI|NYG | 0 | 5 | 6 |
| BAL|TEN | 0 | 1 | 1 |
| CIN|JAX | 4 | 5 | 22 |
| DAL|HOU | 1 | 5 | 10 |
| KC|LV | 0 | 2 | 2 |
| LAR|PHI | 0 | 2 | 2 |
| MIA|MIN | 0 | 2 | 2 |

### B_full757

**B_full757 1:** $49,600; mean 129.966; summed marginal P90 228.600; selector 5.679441267; gap from common individual frontier 0.000797580. Stable canonical roster hash `7bd263e0905c0b73753160ff073be549ac62b9d4d3c3a49cac6946cbf6a1f7bf`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Jakobi Meyers | 44312618 | $5,000 |
| DST | Rams | 44313323 | $2,600 |

**B_full757 2:** $49,800; mean 133.497; summed marginal P90 233.706; selector 5.678915711; gap from common individual frontier 0.001323137. Stable canonical roster hash `6c276c4e8c19e65489ad3732b1022dd7fe10cea9075ff4811599acc9a739cfd0`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | CeeDee Lamb | 44312566 | $7,800 |
| DST | Titans | 44313330 | $2,100 |

**B_full757 3:** $49,800; mean 135.221; summed marginal P90 232.209; selector 5.676047750; gap from common individual frontier 0.004191098. Stable canonical roster hash `0cf73b654437c9700d8cc5ac35acdaac99567943251489bb84a2ea56e64c43bc`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Kyren Williams | 44312308 | $5,900 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| WR | Ja'Marr Chase | 44312564 | $8,100 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Javonte Williams | 44312288 | $6,600 |
| DST | Dolphins | 44313331 | $2,000 |

**B_full757 4:** $50,000; mean 132.144; summed marginal P90 230.945; selector 5.487202492; gap from common individual frontier 0.193036356. Stable canonical roster hash `da077dcf1cf6484127ab66e7ca49d329e0dcad959b395bf2cfb7c05ac08c08e6`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Dak Prescott | 44312203 | $6,400 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Ryan Flournoy | 44312678 | $3,800 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Dalton Schultz | 44313028 | $4,800 |
| FLEX | CeeDee Lamb | 44312566 | $7,800 |
| DST | Cardinals | 44313325 | $2,500 |

**B_full757 5:** $49,900; mean 129.948; summed marginal P90 231.181; selector 5.460866395; gap from common individual frontier 0.219372453. Stable canonical roster hash `7ef0cc982a08600f075367ee99661ed8f45bd947ea6b666573bffe2546eed37a`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Jacoby Brissett | 44312217 | $5,000 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Trey McBride | 44313020 | $6,500 |
| FLEX | Jakobi Meyers | 44312618 | $5,000 |
| DST | Rams | 44313323 | $2,600 |

| Player | Appearances |
| --- | --- |
| Javonte Williams | 5/5 |
| Michael Wilson | 5/5 |
| Parker Washington | 5/5 |
| Chase Brown | 4/5 |
| Brenton Strange | 3/5 |
| Tee Higgins | 3/5 |
| Trevor Lawrence | 3/5 |
| CeeDee Lamb | 2/5 |
| Jakobi Meyers | 2/5 |
| Rams | 2/5 |
| Cardinals | 1/5 |
| Dak Prescott | 1/5 |
| Dalton Schultz | 1/5 |
| Dolphins | 1/5 |
| Ja'Marr Chase | 1/5 |
| Jacoby Brissett | 1/5 |
| Kenneth Walker III | 1/5 |
| Kyren Williams | 1/5 |
| Ryan Flournoy | 1/5 |
| Titans | 1/5 |
| Trey McBride | 1/5 |

| Canonical game | Primary QB stacks | Any-player entries | Player appearances |
| --- | --- | --- | --- |
| ARI|NYG | 1 | 5 | 8 |
| BAL|TEN | 0 | 1 | 1 |
| CIN|JAX | 3 | 5 | 21 |
| DAL|HOU | 1 | 5 | 10 |
| KC|LV | 0 | 1 | 1 |
| LAR|PHI | 0 | 3 | 3 |
| MIA|MIN | 0 | 1 | 1 |

### C_full757

**C_full757 1:** $49,700; mean 133.544; summed marginal P90 233.753; selector 5.680238848; gap from common individual frontier 0.000000000. Stable canonical roster hash `92bbd4f894074fe06411750eab2075e6d3ec5fe21728d4b034bcc650beeb9785`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | CeeDee Lamb | 44312566 | $7,800 |
| DST | Dolphins | 44313331 | $2,000 |

**C_full757 2:** $49,900; mean 135.174; summed marginal P90 232.162; selector 5.674724613; gap from common individual frontier 0.005514235. Stable canonical roster hash `0fc7614d892132e5d277fe10575d75947008ae5935f19186037b7c2d2f4fe2af`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Kyren Williams | 44312308 | $5,900 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| WR | Ja'Marr Chase | 44312564 | $8,100 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Javonte Williams | 44312288 | $6,600 |
| DST | Titans | 44313330 | $2,100 |

**C_full757 3:** $49,900; mean 129.416; summed marginal P90 226.641; selector 5.650444839; gap from common individual frontier 0.029794009. Stable canonical roster hash `0bf47c00186f5d96438820dbe6b77080378c6845f99bf81fb7e960ac5a4c489c`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Ryan Flournoy | 44312678 | $3,800 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Jakobi Meyers | 44312618 | $5,000 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Ja'Marr Chase | 44312564 | $8,100 |
| DST | Rams | 44313323 | $2,600 |

**C_full757 4:** $50,000; mean 127.269; summed marginal P90 224.641; selector 5.572610961; gap from common individual frontier 0.107627887. Stable canonical roster hash `324fe63f76ce6e16c502418f9dc9ca78fb247e64421bafed9970dd76f20447cc`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Joe Burrow | 44312199 | $6,800 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Mike Gesicki | 44313052 | $3,300 |
| FLEX | Jakobi Meyers | 44312618 | $5,000 |
| DST | Dolphins | 44313331 | $2,000 |

**C_full757 5:** $50,000; mean 129.972; summed marginal P90 231.372; selector 5.445958807; gap from common individual frontier 0.234280040. Stable canonical roster hash `dda137c4a28c1fbf2383e2ee9ec2846a3d3f501981c68516b894414d5f027c97`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Dak Prescott | 44312203 | $6,400 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| WR | George Pickens | 44312590 | $6,300 |
| WR | Ryan Flournoy | 44312678 | $3,800 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Cade Otton | 44313048 | $3,400 |
| FLEX | CeeDee Lamb | 44312566 | $7,800 |
| DST | Cardinals | 44313325 | $2,500 |

| Player | Appearances |
| --- | --- |
| Javonte Williams | 4/5 |
| Michael Wilson | 4/5 |
| Parker Washington | 4/5 |
| Brenton Strange | 3/5 |
| Chase Brown | 3/5 |
| Kenneth Walker III | 3/5 |
| Trevor Lawrence | 3/5 |
| CeeDee Lamb | 2/5 |
| Dolphins | 2/5 |
| Ja'Marr Chase | 2/5 |
| Jakobi Meyers | 2/5 |
| Ryan Flournoy | 2/5 |
| Tee Higgins | 2/5 |
| Cade Otton | 1/5 |
| Cardinals | 1/5 |
| Dak Prescott | 1/5 |
| George Pickens | 1/5 |
| Joe Burrow | 1/5 |
| Kyren Williams | 1/5 |
| Mike Gesicki | 1/5 |
| Rams | 1/5 |
| Titans | 1/5 |

| Canonical game | Primary QB stacks | Any-player entries | Player appearances |
| --- | --- | --- | --- |
| ARI|NYG | 0 | 4 | 5 |
| BAL|TEN | 0 | 1 | 1 |
| CIN|JAX | 4 | 5 | 21 |
| DAL|HOU | 1 | 5 | 10 |
| GB|TB | 0 | 1 | 1 |
| KC|LV | 0 | 3 | 3 |
| LAR|PHI | 0 | 2 | 2 |
| MIA|MIN | 0 | 2 | 2 |

### D_full757

**D_full757 1:** $49,800; mean 133.497; summed marginal P90 233.706; selector 5.678915711; gap from common individual frontier 0.001323137. Stable canonical roster hash `6c276c4e8c19e65489ad3732b1022dd7fe10cea9075ff4811599acc9a739cfd0`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | CeeDee Lamb | 44312566 | $7,800 |
| DST | Titans | 44313330 | $2,100 |

**D_full757 2:** $49,800; mean 135.221; summed marginal P90 232.209; selector 5.676047750; gap from common individual frontier 0.004191098. Stable canonical roster hash `0cf73b654437c9700d8cc5ac35acdaac99567943251489bb84a2ea56e64c43bc`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Kyren Williams | 44312308 | $5,900 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| WR | Ja'Marr Chase | 44312564 | $8,100 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Javonte Williams | 44312288 | $6,600 |
| DST | Dolphins | 44313331 | $2,000 |

**D_full757 3:** $49,900; mean 129.416; summed marginal P90 226.641; selector 5.650444839; gap from common individual frontier 0.029794009. Stable canonical roster hash `0bf47c00186f5d96438820dbe6b77080378c6845f99bf81fb7e960ac5a4c489c`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Ryan Flournoy | 44312678 | $3,800 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Jakobi Meyers | 44312618 | $5,000 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Ja'Marr Chase | 44312564 | $8,100 |
| DST | Rams | 44313323 | $2,600 |

**D_full757 4:** $49,900; mean 129.948; summed marginal P90 231.181; selector 5.460866395; gap from common individual frontier 0.219372453. Stable canonical roster hash `7ef0cc982a08600f075367ee99661ed8f45bd947ea6b666573bffe2546eed37a`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Jacoby Brissett | 44312217 | $5,000 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Trey McBride | 44313020 | $6,500 |
| FLEX | Jakobi Meyers | 44312618 | $5,000 |
| DST | Rams | 44313323 | $2,600 |

**D_full757 5:** $50,000; mean 129.972; summed marginal P90 231.372; selector 5.445958807; gap from common individual frontier 0.234280040. Stable canonical roster hash `dda137c4a28c1fbf2383e2ee9ec2846a3d3f501981c68516b894414d5f027c97`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Dak Prescott | 44312203 | $6,400 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| WR | George Pickens | 44312590 | $6,300 |
| WR | Ryan Flournoy | 44312678 | $3,800 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Cade Otton | 44313048 | $3,400 |
| FLEX | CeeDee Lamb | 44312566 | $7,800 |
| DST | Cardinals | 44313325 | $2,500 |

| Player | Appearances |
| --- | --- |
| Chase Brown | 4/5 |
| Javonte Williams | 4/5 |
| Michael Wilson | 4/5 |
| Parker Washington | 4/5 |
| Brenton Strange | 3/5 |
| Trevor Lawrence | 3/5 |
| CeeDee Lamb | 2/5 |
| Ja'Marr Chase | 2/5 |
| Jakobi Meyers | 2/5 |
| Kenneth Walker III | 2/5 |
| Rams | 2/5 |
| Ryan Flournoy | 2/5 |
| Tee Higgins | 2/5 |
| Cade Otton | 1/5 |
| Cardinals | 1/5 |
| Dak Prescott | 1/5 |
| Dolphins | 1/5 |
| George Pickens | 1/5 |
| Jacoby Brissett | 1/5 |
| Kyren Williams | 1/5 |
| Titans | 1/5 |
| Trey McBride | 1/5 |

| Canonical game | Primary QB stacks | Any-player entries | Player appearances |
| --- | --- | --- | --- |
| ARI|NYG | 1 | 4 | 7 |
| BAL|TEN | 0 | 1 | 1 |
| CIN|JAX | 3 | 5 | 20 |
| DAL|HOU | 1 | 5 | 10 |
| GB|TB | 0 | 1 | 1 |
| KC|LV | 0 | 2 | 2 |
| LAR|PHI | 0 | 3 | 3 |
| MIA|MIN | 0 | 1 | 1 |

### E_full757

**E_full757 1:** $49,900; mean 132.670; summed marginal P90 231.471; selector 5.644709926; gap from common individual frontier 0.035528921. Stable canonical roster hash `cfdf2a38b37934c60508ed1c1038c48eae14f4ebe59fe6ba47eb4383d1611a0f`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| WR | Ryan Flournoy | 44312678 | $3,800 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Ja'Marr Chase | 44312564 | $8,100 |
| DST | Rams | 44313323 | $2,600 |

**E_full757 2:** $50,000; mean 132.010; summed marginal P90 230.644; selector 5.608409210; gap from common individual frontier 0.071829638. Stable canonical roster hash `d492cb4f545b31d6137f67723d4208d56f08e1e5596a967022b9dcbbb4e477c9`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Christian Watson | 44312582 | $6,700 |
| WR | Parker Washington | 44312586 | $6,500 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Zay Flowers | 44312578 | $6,900 |
| DST | Dolphins | 44313331 | $2,000 |

**E_full757 3:** $50,000; mean 132.613; summed marginal P90 227.606; selector 5.564272906; gap from common individual frontier 0.115965942. Stable canonical roster hash `f2712f87a21667d5968711045783f5f2505257d3b4aca0b9722d5eadf98e0dd0`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Kyren Williams | 44312308 | $5,900 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Michael Wilson | 44312606 | $5,500 |
| WR | Jakobi Meyers | 44312618 | $5,000 |
| WR | CeeDee Lamb | 44312566 | $7,800 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Ja'Marr Chase | 44312564 | $8,100 |
| DST | Dolphins | 44313331 | $2,000 |

**E_full757 4:** $49,900; mean 129.948; summed marginal P90 231.181; selector 5.460866395; gap from common individual frontier 0.219372453. Stable canonical roster hash `7ef0cc982a08600f075367ee99661ed8f45bd947ea6b666573bffe2546eed37a`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Jacoby Brissett | 44312217 | $5,000 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Trey McBride | 44313020 | $6,500 |
| FLEX | Jakobi Meyers | 44312618 | $5,000 |
| DST | Rams | 44313323 | $2,600 |

**E_full757 5:** $50,000; mean 129.972; summed marginal P90 231.372; selector 5.445958807; gap from common individual frontier 0.234280040. Stable canonical roster hash `dda137c4a28c1fbf2383e2ee9ec2846a3d3f501981c68516b894414d5f027c97`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Dak Prescott | 44312203 | $6,400 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| WR | George Pickens | 44312590 | $6,300 |
| WR | Ryan Flournoy | 44312678 | $3,800 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Cade Otton | 44313048 | $3,400 |
| FLEX | CeeDee Lamb | 44312566 | $7,800 |
| DST | Cardinals | 44313325 | $2,500 |

| Player | Appearances |
| --- | --- |
| Chase Brown | 4/5 |
| Michael Wilson | 4/5 |
| Brenton Strange | 3/5 |
| Javonte Williams | 3/5 |
| Parker Washington | 3/5 |
| Trevor Lawrence | 3/5 |
| CeeDee Lamb | 2/5 |
| Dolphins | 2/5 |
| Ja'Marr Chase | 2/5 |
| Jakobi Meyers | 2/5 |
| Kenneth Walker III | 2/5 |
| Rams | 2/5 |
| Ryan Flournoy | 2/5 |
| Tee Higgins | 2/5 |
| Cade Otton | 1/5 |
| Cardinals | 1/5 |
| Christian Watson | 1/5 |
| Dak Prescott | 1/5 |
| George Pickens | 1/5 |
| Jacoby Brissett | 1/5 |
| Kyren Williams | 1/5 |
| Trey McBride | 1/5 |
| Zay Flowers | 1/5 |

| Canonical game | Primary QB stacks | Any-player entries | Player appearances |
| --- | --- | --- | --- |
| ARI|NYG | 1 | 4 | 7 |
| BAL|TEN | 0 | 1 | 1 |
| CIN|JAX | 3 | 5 | 19 |
| DAL|HOU | 1 | 5 | 9 |
| GB|TB | 0 | 2 | 2 |
| KC|LV | 0 | 2 | 2 |
| LAR|PHI | 0 | 3 | 3 |
| MIA|MIN | 0 | 2 | 2 |

### E_admitted400

**E_admitted400 1:** $49,900; mean 131.388; summed marginal P90 234.197; selector 5.641405123; gap from common individual frontier 0.038833725. Stable canonical roster hash `daee44f655b9adbd7610af4736877927d3afc2964b27040c61a7223ca2748454`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| WR | Jakobi Meyers | 44312618 | $5,000 |
| TE | Cade Otton | 44313048 | $3,400 |
| FLEX | Ja'Marr Chase | 44312564 | $8,100 |
| DST | Buccaneers | 44313318 | $2,800 |

**E_admitted400 2:** $50,000; mean 130.829; summed marginal P90 224.667; selector 5.639653588; gap from common individual frontier 0.040585260. Stable canonical roster hash `e1e468c97ae595f2b1e7d291be999018bfce9a9020c3fefd838bc68791849379`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Kyren Williams | 44312308 | $5,900 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Jakobi Meyers | 44312618 | $5,000 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Javonte Williams | 44312288 | $6,600 |
| DST | Rams | 44313323 | $2,600 |

**E_admitted400 3:** $50,000; mean 132.132; summed marginal P90 230.451; selector 5.611143049; gap from common individual frontier 0.069095799. Stable canonical roster hash `44d37ff4fee1d3a02900b5209b8367b45a437f51ce3d456b2e7f05ec0f91ebd5`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | D'Andre Swift | 44312292 | $6,400 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | CeeDee Lamb | 44312566 | $7,800 |
| DST | Cardinals | 44313325 | $2,500 |

**E_admitted400 4:** $50,000; mean 133.876; summed marginal P90 235.696; selector 5.446559077; gap from common individual frontier 0.233679770. Stable canonical roster hash `07d7efc8de662ee99f1aa0f523f1ee26c14a90f0fdbbde81c36a0dc6c04d0c98`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Jacoby Brissett | 44312217 | $5,000 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Kalif Raymond | 44312686 | $3,600 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Trey McBride | 44313020 | $6,500 |
| FLEX | Javonte Williams | 44312288 | $6,600 |
| DST | Dolphins | 44313331 | $2,000 |

**E_admitted400 5:** $50,000; mean 129.972; summed marginal P90 231.372; selector 5.445958807; gap from common individual frontier 0.234280040. Stable canonical roster hash `dda137c4a28c1fbf2383e2ee9ec2846a3d3f501981c68516b894414d5f027c97`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Dak Prescott | 44312203 | $6,400 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| WR | George Pickens | 44312590 | $6,300 |
| WR | Ryan Flournoy | 44312678 | $3,800 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Cade Otton | 44313048 | $3,400 |
| FLEX | CeeDee Lamb | 44312566 | $7,800 |
| DST | Cardinals | 44313325 | $2,500 |

| Player | Appearances |
| --- | --- |
| Chase Brown | 4/5 |
| Michael Wilson | 4/5 |
| Parker Washington | 4/5 |
| Javonte Williams | 3/5 |
| Kenneth Walker III | 3/5 |
| Trevor Lawrence | 3/5 |
| Brenton Strange | 2/5 |
| Cade Otton | 2/5 |
| Cardinals | 2/5 |
| CeeDee Lamb | 2/5 |
| Jakobi Meyers | 2/5 |
| Tee Higgins | 2/5 |
| Buccaneers | 1/5 |
| D'Andre Swift | 1/5 |
| Dak Prescott | 1/5 |
| Dolphins | 1/5 |
| George Pickens | 1/5 |
| Ja'Marr Chase | 1/5 |
| Jacoby Brissett | 1/5 |
| Kalif Raymond | 1/5 |
| Kyren Williams | 1/5 |
| Rams | 1/5 |
| Ryan Flournoy | 1/5 |
| Trey McBride | 1/5 |

| Canonical game | Primary QB stacks | Any-player entries | Player appearances |
| --- | --- | --- | --- |
| ARI|NYG | 1 | 4 | 8 |
| CHI|NYJ | 0 | 2 | 2 |
| CIN|JAX | 3 | 5 | 18 |
| DAL|HOU | 1 | 5 | 8 |
| GB|TB | 0 | 2 | 3 |
| KC|LV | 0 | 3 | 3 |
| LAR|PHI | 0 | 1 | 2 |
| MIA|MIN | 0 | 1 | 1 |

### A_no_Meyers

**A_no_Meyers 1:** $49,800; mean 133.497; summed marginal P90 233.706; selector 5.678915711; gap from common individual frontier 0.001323137. Stable canonical roster hash `6c276c4e8c19e65489ad3732b1022dd7fe10cea9075ff4811599acc9a739cfd0`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | CeeDee Lamb | 44312566 | $7,800 |
| DST | Titans | 44313330 | $2,100 |

**A_no_Meyers 2:** $49,800; mean 135.221; summed marginal P90 232.209; selector 5.676047750; gap from common individual frontier 0.004191098. Stable canonical roster hash `0cf73b654437c9700d8cc5ac35acdaac99567943251489bb84a2ea56e64c43bc`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Kyren Williams | 44312308 | $5,900 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| WR | Ja'Marr Chase | 44312564 | $8,100 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Javonte Williams | 44312288 | $6,600 |
| DST | Dolphins | 44313331 | $2,000 |

**A_no_Meyers 3:** $49,900; mean 132.670; summed marginal P90 231.471; selector 5.644709926; gap from common individual frontier 0.035528921. Stable canonical roster hash `cfdf2a38b37934c60508ed1c1038c48eae14f4ebe59fe6ba47eb4383d1611a0f`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| WR | Ryan Flournoy | 44312678 | $3,800 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Ja'Marr Chase | 44312564 | $8,100 |
| DST | Rams | 44313323 | $2,600 |

**A_no_Meyers 4:** $50,000; mean 126.511; summed marginal P90 222.367; selector 5.562477252; gap from common individual frontier 0.117761595. Stable canonical roster hash `77232f3f33c35749c18231ae0a40236307b32cc74a819634e3a0ffe3fae5a586`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Joe Burrow | 44312199 | $6,800 |
| RB | Javonte Williams | 44312288 | $6,600 |
| RB | Rhamondre Stevenson | 44312328 | $5,100 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Mike Gesicki | 44313052 | $3,300 |
| FLEX | Ja'Marr Chase | 44312564 | $8,100 |
| DST | Dolphins | 44313331 | $2,000 |

**A_no_Meyers 5:** $50,000; mean 132.144; summed marginal P90 230.945; selector 5.487202492; gap from common individual frontier 0.193036356. Stable canonical roster hash `da077dcf1cf6484127ab66e7ca49d329e0dcad959b395bf2cfb7c05ac08c08e6`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Dak Prescott | 44312203 | $6,400 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Ryan Flournoy | 44312678 | $3,800 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Dalton Schultz | 44313028 | $4,800 |
| FLEX | CeeDee Lamb | 44312566 | $7,800 |
| DST | Cardinals | 44313325 | $2,500 |

| Player | Appearances |
| --- | --- |
| Michael Wilson | 5/5 |
| Parker Washington | 5/5 |
| Chase Brown | 4/5 |
| Javonte Williams | 4/5 |
| Brenton Strange | 3/5 |
| Ja'Marr Chase | 3/5 |
| Trevor Lawrence | 3/5 |
| CeeDee Lamb | 2/5 |
| Dolphins | 2/5 |
| Ryan Flournoy | 2/5 |
| Tee Higgins | 2/5 |
| Cardinals | 1/5 |
| Dak Prescott | 1/5 |
| Dalton Schultz | 1/5 |
| Joe Burrow | 1/5 |
| Kenneth Walker III | 1/5 |
| Kyren Williams | 1/5 |
| Mike Gesicki | 1/5 |
| Rams | 1/5 |
| Rhamondre Stevenson | 1/5 |
| Titans | 1/5 |

| Canonical game | Primary QB stacks | Any-player entries | Player appearances |
| --- | --- | --- | --- |
| ARI|NYG | 0 | 5 | 6 |
| BAL|TEN | 0 | 1 | 1 |
| BUF|NE | 0 | 1 | 1 |
| CIN|JAX | 4 | 5 | 22 |
| DAL|HOU | 1 | 5 | 10 |
| KC|LV | 0 | 1 | 1 |
| LAR|PHI | 0 | 2 | 2 |
| MIA|MIN | 0 | 2 | 2 |

### D_no_Meyers

**D_no_Meyers 1:** $49,800; mean 132.622; summed marginal P90 227.615; selector 5.666707025; gap from common individual frontier 0.013531823. Stable canonical roster hash `532cc035f5a6819b5e33b82030666c6442602d0da3ec70ffbc54be0aa1593169`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Kyren Williams | 44312308 | $5,900 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Tee Higgins | 44312594 | $6,100 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Ja'Marr Chase | 44312564 | $8,100 |
| DST | Dolphins | 44313331 | $2,000 |

**D_no_Meyers 2:** $49,900; mean 132.670; summed marginal P90 231.471; selector 5.644709926; gap from common individual frontier 0.035528921. Stable canonical roster hash `cfdf2a38b37934c60508ed1c1038c48eae14f4ebe59fe6ba47eb4383d1611a0f`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| WR | Ryan Flournoy | 44312678 | $3,800 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Ja'Marr Chase | 44312564 | $8,100 |
| DST | Rams | 44313323 | $2,600 |

**D_no_Meyers 3:** $49,800; mean 133.235; summed marginal P90 232.035; selector 5.639839564; gap from common individual frontier 0.040399283. Stable canonical roster hash `0fc1466f8472a83d224366c0872d5aac1b7020bfbba07fe2fe1f854f79c0b689`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Trevor Lawrence | 44312207 | $5,900 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Kalif Raymond | 44312686 | $3,600 |
| WR | CeeDee Lamb | 44312566 | $7,800 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Ja'Marr Chase | 44312564 | $8,100 |
| DST | Dolphins | 44313331 | $2,000 |

**D_no_Meyers 4:** $50,000; mean 133.205; summed marginal P90 232.006; selector 5.481044875; gap from common individual frontier 0.199193972. Stable canonical roster hash `d77b3f11c35d56f986e4764f78ce34f1cb28708b616be32ab9b2f49871497748`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Dak Prescott | 44312203 | $6,400 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Javonte Williams | 44312288 | $6,600 |
| WR | Ryan Flournoy | 44312678 | $3,800 |
| WR | Michael Wilson | 44312606 | $5,500 |
| WR | CeeDee Lamb | 44312566 | $7,800 |
| TE | Brenton Strange | 44313056 | $3,200 |
| FLEX | Ja'Marr Chase | 44312564 | $8,100 |
| DST | Cardinals | 44313325 | $2,500 |

**D_no_Meyers 5:** $50,000; mean 133.876; summed marginal P90 235.696; selector 5.446559077; gap from common individual frontier 0.233679770. Stable canonical roster hash `07d7efc8de662ee99f1aa0f523f1ee26c14a90f0fdbbde81c36a0dc6c04d0c98`.

| Slot | Player | Native DK ID | Salary |
| --- | --- | --- | --- |
| QB | Jacoby Brissett | 44312217 | $5,000 |
| RB | Chase Brown | 44312302 | $6,100 |
| RB | Kenneth Walker III | 44312278 | $8,200 |
| WR | Parker Washington | 44312586 | $6,500 |
| WR | Kalif Raymond | 44312686 | $3,600 |
| WR | Michael Wilson | 44312606 | $5,500 |
| TE | Trey McBride | 44313020 | $6,500 |
| FLEX | Javonte Williams | 44312288 | $6,600 |
| DST | Dolphins | 44313331 | $2,000 |

| Player | Appearances |
| --- | --- |
| Brenton Strange | 4/5 |
| Chase Brown | 4/5 |
| Ja'Marr Chase | 4/5 |
| Javonte Williams | 4/5 |
| Michael Wilson | 4/5 |
| Parker Washington | 4/5 |
| Dolphins | 3/5 |
| Trevor Lawrence | 3/5 |
| CeeDee Lamb | 2/5 |
| Kalif Raymond | 2/5 |
| Kenneth Walker III | 2/5 |
| Ryan Flournoy | 2/5 |
| Cardinals | 1/5 |
| Dak Prescott | 1/5 |
| Jacoby Brissett | 1/5 |
| Kyren Williams | 1/5 |
| Rams | 1/5 |
| Tee Higgins | 1/5 |
| Trey McBride | 1/5 |

| Canonical game | Primary QB stacks | Any-player entries | Player appearances |
| --- | --- | --- | --- |
| ARI|NYG | 1 | 4 | 7 |
| CHI|NYJ | 0 | 2 | 2 |
| CIN|JAX | 3 | 5 | 20 |
| DAL|HOU | 1 | 5 | 9 |
| KC|LV | 0 | 2 | 2 |
| LAR|PHI | 0 | 2 | 2 |
| MIA|MIN | 0 | 3 | 3 |

## Required closing answers

- **What is active from prior learning?** Explicit overlap precedence, canonical identity/legality checks, source-to-risk practice propagation, missingness preservation, unchanged scoring/ownership controls, and immutable source/model/preview lineage.
- **Which lineup is preferred for friends/smaller use?** The independent Lawrence/Brown/Javonte/Higgins/Washington/Wilson/Strange/Lamb/Dolphins construction; the supplied smaller contest is a ticket satellite.
- **Which larger-field portfolio and why?** D: jointly game max-three and skill max-four, with three supported primary games and lower average overlap for 0.648% selector cost.
- **Which dependencies remain?** Four near-core skills at 80%, Lawrence/Strange at 60%, CIN–JAX and DAL–HOU present in every entry, and Meyers at two entries.
- **What is known versus unvalidated?** Exact legality, scores, cap feasibility, source provenance and A–D admission preservation are verified. Current contest winning, duplication, qualification and payout performance are unvalidated; marginal P90 sums are not joint quantiles.
- **What needs approval, assignment or kickoff clearance?** Actual paid counts/budget, contest assignments/reuse, accepting the proposed caps and Meyers contingency; final inactives/starters, new practice/role evidence, current weather/market timing and native entry-template matching before entry. No unattended Sunday work was scheduled.
