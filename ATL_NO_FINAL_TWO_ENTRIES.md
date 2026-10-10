# ATL–NO: final two-entry portfolio

October 5, 2026. **Recommend pair D: the strongest eligible primary plus the best distinct-Captain pair with at most three shared identities. Exactly two final entries are designated below; A–C and the Austin-free checks are comparison candidates only.**

## FINAL ENTRY 1 — PRIMARY

**Captain: Chris Olave.** FLEX: Bijan Robinson, Tyler Shough, Brian Robinson Jr., Kevin Austin Jr., Devaughn Vele.

**Salary $50,000; ATL 2 / NO 4; 1 QB; mean 82.147685604; summed marginal P90 146.436555241; selector 166.515317615.**

Construction: Olave-led Saints passing concentration, Shough with Olave/Vele/Austin, and both Atlanta running backs as the return. This is the highest-selector lineup that passes both quality floors; its winning path favors Saints receiving production with Atlanta scoring through its backfield.

## FINAL ENTRY 2 — DIVERSIFIED

**Captain: Tyler Shough.** FLEX: Michael Penix Jr., Drake London, Chris Olave, Kevin Austin Jr., Daniel Carlson.

**Salary $49,800; ATL 2 / NO 4; 2 QBs; mean 82.414615901; summed marginal P90 145.798168500; selector 155.441973479.**

Construction: QB-led competitive game, Shough with Olave/Austin, Penix with London, and Carlson covering Saints field-goal production. Relative to Entry 1, Penix/London/Carlson replace Bijan/Brian Robinson/Vele; the Captain also changes from Olave to Shough.

**Shared identities: 3 — Tyler Shough, Chris Olave, Kevin Austin Jr.** Both entries have distinct Captains.

I prefer D because it preserves the strongest eligible primary while the second entry changes three player identities and moves from Atlanta backfield exposure to a Penix–London passing stack with Carlson. That broader construction costs only 1.667842% of total selector versus the two highest-selector eligible lineups, while both entries still clear the fixed 95% mean and P90 floors. A already offers useful diversification, but D reduces shared identities from four to three and leaves Bijan exposure in one entry rather than both.

## Frozen inputs and selection method

Projection run: `1d46230e-d73a-459c-8d80-5512c93d5604`. Projection cutoff: **6:54:22 p.m. ET**; immutable pool freeze: **6:58:06 p.m. ET**. Market snapshot `02297e76-e131-5d33-aa56-5b96dc2d2f67` was captured at **6:52:44 p.m. ET**: NO −1.5, game total 47.5, NO implied 24.5, ATL implied 23.0. The prepared pool contains 23 eligible players with current corrected role/availability inputs.

QB Captain is allowed, up to two starting QBs are allowed, and each lineup has at most four players from a team. Salary, slots, canonical-identity uniqueness, availability, opportunity gates, and every saved production MILP correlation constraint remain in force. No named player was locked, excluded, or given a score adjustment. Role ownership remains uniformly disabled in the saved selector because the ownership input is incomplete.

The exhaustive saved universe contains **43,806 legal physical Captain/roster assignments**. Independent legal maxima are mean **86.111642993** and summed marginal P90 **150.902376468**; every recommended lineup must independently meet mean **81.806060844** AND P90 **143.357257644**. These denominators stay fixed for every comparison, including Austin-free diagnostics.

Twenty-one physical lineups pass the joint 95% screen, giving 210 unordered two-entry pairs. All pairs were compared directly by summed existing selector; there are no rounded percentage exposure caps, no five-entry fill objective, and no forced diversity bonus. Every screened roster was independently certified against the saved MILP, and each prepared mean/P90 was checked against this fresh projection run by canonical player ID.

Mean and P90 include the 1.5× Captain multiplier. **P90 here is the sum of player marginal P90s, not a simulated lineup or portfolio 90th percentile.** Pair totals sum the two lineup metrics; overlap measures shared identities, not score correlation. The game-script descriptions are construction interpretations, not newly conditioned forecasts or fitted simulations.

## Required candidate-pair comparison

| Entry | Captain and all six players | Salary | Team split | QBs | Mean | Summed marginal P90 | Selector |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| A1 | Chris Olave (CPT); Bijan Robinson; Tyler Shough; Brian Robinson Jr.; Kevin Austin Jr.; Devaughn Vele | $50,000 | ATL 2/NO 4 | 1 | 82.147685604 | 146.436555241 | 166.515317615 |
| A2 | Tyler Shough (CPT); Bijan Robinson; Michael Penix Jr.; Jahan Dotson; Chris Olave; Kevin Austin Jr. | $49,800 | ATL 3/NO 3 | 2 | 86.111642993 | 150.902376468 | 160.902788589 |
| B1 | Chris Olave (CPT); Bijan Robinson; Tyler Shough; Brian Robinson Jr.; Kevin Austin Jr.; Devaughn Vele | $50,000 | ATL 2/NO 4 | 1 | 82.147685604 | 146.436555241 | 166.515317615 |
| B2 | Tyler Shough (CPT); Bijan Robinson; Michael Penix Jr.; Jahan Dotson; Chris Olave; Kevin Austin Jr. | $49,800 | ATL 3/NO 3 | 2 | 86.111642993 | 150.902376468 | 160.902788589 |
| C1 | Chris Olave (CPT); Bijan Robinson; Tyler Shough; Brian Robinson Jr.; Kevin Austin Jr.; Devaughn Vele | $50,000 | ATL 2/NO 4 | 1 | 82.147685604 | 146.436555241 | 166.515317615 |
| C2 | Tyler Shough (CPT); Bijan Robinson; Michael Penix Jr.; Jahan Dotson; Chris Olave; Kevin Austin Jr. | $49,800 | ATL 3/NO 3 | 2 | 86.111642993 | 150.902376468 | 160.902788589 |
| D1 | Chris Olave (CPT); Bijan Robinson; Tyler Shough; Brian Robinson Jr.; Kevin Austin Jr.; Devaughn Vele | $50,000 | ATL 2/NO 4 | 1 | 82.147685604 | 146.436555241 | 166.515317615 |
| D2 | Tyler Shough (CPT); Drake London; Michael Penix Jr.; Chris Olave; Kevin Austin Jr.; Daniel Carlson | $49,800 | ATL 2/NO 4 | 2 | 82.414615901 | 145.798168500 | 155.441973479 |

**A — highest-selector pair without additional diversity rules:** A1 + A2. Different Captains arise naturally; four shared identities are Bijan Robinson, Tyler Shough, Chris Olave, Kevin Austin Jr. A1 is the Olave/Saints receiving + Atlanta-backfield path; A2 is Shough Captain with both QBs, Penix–Dotson, and Bijan in a balanced 3–3 construction.

**B — best different-Captain pair:** identical to A. The distinct-Captain requirement adds no cost; the shared players and game scripts are exactly those of A.

**C — best different-Captain pair with at most four shared identities:** identical to A and B. The four-shared limit adds no cost; the shared players and game scripts are exactly those of A.

**D — best different-Captain pair with at most three shared identities:** D1 + D2, the recommended final pair. Shared identities are Shough, Olave, Austin. D1 is the Olave/Saints receiving + Atlanta-backfield path; D2 is Shough Captain with Penix–London and Carlson. This is the best selector at the three-shared limit across all 210 pairs, and it retains the strongest primary.

The comparison frontier contains A and D: no other screened pair improves selector, Captain distinction, overlap, and Austin exposure together. There is no feasible two-shared pair or screened pair with Austin in only one entry. D is my preferred breadth/quality tradeoff; the existing selector does not establish that D has higher simulated portfolio EV or lower score covariance than A.

| Pair | Total mean | Total marginal P90 | Total selector | Shared identities |
| --- | ---: | ---: | ---: | ---: |
| A | 168.259328598 | 297.338931709 | 327.418106204 | 4 |
| B | 168.259328598 | 297.338931709 | 327.418106204 | 4 |
| C | 168.259328598 | 297.338931709 | 327.418106204 | 4 |
| D — final | 164.562301506 | 292.234723741 | 321.957291094 | 3 |

Costs below are **A total minus alternative total**, calculated from unrounded metrics. Positive means a loss; negative means a gain. Full-precision values are retained in the linked evidence.

| Pair | Mean cost vs A | P90 cost vs A | Selector cost vs A | Mean / P90 / selector cost (%) |
| --- | ---: | ---: | ---: | --- |
| B | 0.000000000 | 0.000000000 | 0.000000000 | 0.000000% / 0.000000% / 0.000000% |
| C | 0.000000000 | 0.000000000 | 0.000000000 | 0.000000% / 0.000000% / 0.000000% |
| D — final | 3.697027092 | 5.104207968 | 5.460815111 | 2.197220% / 1.716630% / 1.667842% |

For D, the primary is unchanged, so all absolute costs occur in Entry 2. Average per-entry losses are half those totals: mean 1.848513546, P90 2.552103984, selector 2.730407555.

| Final entry | Mean / legal maximum | P90 / legal maximum | Joint quality |
| --- | ---: | ---: | ---: |
| 1 | 95.396723% | 97.040589% | 95.396723% |
| 2 | 95.706705% | 96.617543% | 95.706705% |

## Named-player exposures

Each appearance is 50% of this two-entry portfolio; exposures count identity in either slot.

| Player | A | B | C | D — final | Final Captain exposure |
| --- | --- | --- | --- | --- | --- |
| Alvin Kamara | 0/2 (0%) | 0/2 (0%) | 0/2 (0%) | 0/2 (0%) | 0/2 (0%) |
| Bijan Robinson | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 1/2 (50%) | 0/2 (0%) |
| Chris Olave | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 1/2 (50%) |
| Kevin Austin Jr. | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 0/2 (0%) |
| Michael Penix Jr. | 1/2 (50%) | 1/2 (50%) | 1/2 (50%) | 1/2 (50%) | 0/2 (0%) |
| Tyler Shough | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 1/2 (50%) |

Bijan is present in the primary, so the conditional request for a best Bijan-containing alternative if both entries omit him does not arise. Kamara remains model-eligible with fresh mean 8.471194137 and P90 16.381390880; no Kamara-containing lineup clears both fixed 95% floors, so his zero exposure is not a user exclusion.

## Kevin Austin Jr.: exact removal cost

Austin remains eligible as a sourced backup, with fresh FLEX mean **5.076085813** and P90 **10.502096635** at $800. His modeled 4.217760535 targets retain the older receiving window (2025 W17, 2025 W18, 2026 W2), while recent 2026 W1–W3 snaps average 9%; this is the documented usage-currency concern. No forecast correction or exclusion is applied here.

**All 21 jointly screened lineups include Austin. Removing him from one final entry is infeasible at the required 95% floor.** The following saved-model-legal replacements keep the final primary and remove Austin from the second lineup; all are diagnostics, and none is recommended. The existing floor is not lowered.

| Entry | Captain and all six players | Salary | Team split | QBs | Mean | Summed marginal P90 | Selector |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| Retained primary | Chris Olave (CPT); Bijan Robinson; Tyler Shough; Brian Robinson Jr.; Kevin Austin Jr.; Devaughn Vele | $50,000 | ATL 2/NO 4 | 1 | 82.147685604 | 146.436555241 | 166.515317615 |
| X — closest joint floor | Tyler Shough (CPT); Bijan Robinson; Bryce Lance; Jahan Dotson; Chris Olave; Devaughn Vele | $49,600 | ATL 2/NO 4 | 1 | 81.590309721 | 146.458584071 | 155.615253312 |
| Y — best selector with mean ≥95% | Tyler Shough (CPT); Bijan Robinson; Bryce Lance; Michael Penix Jr.; Chris Olave; Olamide Zaccheaus | $49,800 | ATL 3/NO 3 | 2 | 82.300339744 | 142.552253260 | 152.552665381 |
| Z — best selector, no quality screen | Chris Olave (CPT); Tyler Shough; Michael Penix Jr.; Brian Robinson Jr.; Jahan Dotson; Devaughn Vele | $49,400 | ATL 3/NO 3 | 2 | 76.211375594 | 145.572990152 | 167.055495406 |

X has four shared identities with the retained primary: Bijan, Shough, Olave, Vele. It changes to Shough Captain with Lance/Dotson replacing Austin/Brian Robinson; it reaches **94.749451857% mean and 97.055187267% P90**, missing the mean floor by **0.215751122 points**, or **0.250548143 percentage points** of the legal maximum. This is the maximum joint quality achievable without Austin anywhere in the exhaustive legal universe.

Y has three shared identities: Bijan, Shough, Olave. It uses two QBs, Penix–Zaccheaus and Shough–Olave/Lance; mean is 95.573997758% but P90 is **94.466539624%**, missing the P90 floor by **0.805004385 points**. It is the highest-selector Austin-free lineup that preserves the 95% mean requirement.

Z has four shared identities: Shough, Brian Robinson, Olave, Vele, and repeats Olave Captain. It uses Penix–Dotson plus Shough–Olave/Vele, omits Bijan, and reaches only **88.502986292% mean**, despite 96.468321811% P90; its higher selector cannot compensate for failing the required mean floor.

| Diagnostic pair: retained primary + replacement | Mean cost vs A | P90 cost vs A | Selector cost vs A | Mean cost vs final D | P90 cost vs final D | Selector cost vs final D |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| X — closest joint floor | 4.521333272 | 4.443792397 | 5.287535278 | 0.824306180 | -0.660415571 | -0.173279833 |
| Y — best selector with mean ≥95% | 3.811303250 | 8.350123208 | 8.350123208 | 0.114276158 | 3.245915240 | 2.889308098 |
| Z — best selector, no quality screen | 9.900267399 | 5.329386316 | -6.152706817 | 6.203240307 | 0.225178348 | -11.613521928 |

X would lose 0.824306180 mean versus final D, gain 0.660415571 marginal P90 and 0.173279833 selector, but fail the fixed mean floor. Thus the obstacle to reducing Austin exposure is a specific quality-screen failure, not a lack of a high-selector legal alternative. A direct one-player Austin replacement in final Entry 2 has only $1,000 of available salary. Woerner is the only eligible alternative within that amount, but substituting him leaves Shough Captain with only one same-team WR/TE (Olave), violating the saved QB-Captain minimum of two. In Entry 1, Austin → Woerner is legal but loses mean 3.951141320, P90 4.733917707, selector 4.387935564 and fails both floors.

| Player | Primary + X | Primary + Y | Primary + Z |
| --- | --- | --- | --- |
| Alvin Kamara | 0/2 (0%) | 0/2 (0%) | 0/2 (0%) |
| Bijan Robinson | 2/2 (100%) | 2/2 (100%) | 1/2 (50%) |
| Chris Olave | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) |
| Kevin Austin Jr. | 1/2 (50%) | 1/2 (50%) | 1/2 (50%) |
| Michael Penix Jr. | 0/2 (0%) | 1/2 (50%) | 1/2 (50%) |
| Tyler Shough | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) |

The final pair retains common Austin forecast risk. Distinct Captains and three shared identities broaden construction coverage, but do not remove that shared model dependency.

## Verification and immutable evidence

Application, model, projection, and optimizer code were unchanged relative to the fresh snapshot code manifest. Analysis used saved JSON/NPZ artifacts only; no projection fit, rescore, market refresh, live optimizer write, lineup submission, or optimizer-setting change was performed for this two-entry decision. Final entries were checked for six distinct canonical identities, one Captain/five FLEX, salary ≤$50,000, two-team representation, max-four/team, permitted starting QBs, saved correlation legality, and both quality floors.

Prepared-input digest: `4066bf262d91e156112df6b4ceddc1d58e912adb916b9a7497c9423efcd4cd8e`.

- [Fresh prepared input](/Users/wones/git/football_26/artifacts/atl_no_prelock_final/20261005T225137Z/prepared_input.json)
- [Exhaustive two-entry comparison and full-precision costs](/Users/wones/git/football_26/artifacts/atl_no_prelock_final/20261005T225137Z/two_entry_comparison.json)
- [Austin-free diagnostic evidence](/Users/wones/git/football_26/artifacts/atl_no_prelock_final/20261005T225137Z/two_entry_austin_diagnostic.json)
- [Fresh market capture](/Users/wones/git/football_26/artifacts/atl_no_prelock_final/20261005T225137Z/market_result.json)
- [Projection snapshot](/Users/wones/git/football_26/artifacts/atl_no_prelock_final/20261005T225137Z/projection_result.json)
