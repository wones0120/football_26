95% PORTFOLIO — **2 of 5 entries generated** (CURRENT CONTROL).

94% PORTFOLIO — **5 of 5 entries generated** (DIAGNOSTIC FINAL-CANDIDATE SET, human review).

| Comparison | 95% control | 94% diagnostic |
| --- | --- | --- |
| Generated / requested | 2 / 5 | 5 / 5 |
| Joint-screen eligible physical lineups | 23 | 48 |
| Lineups failing 95% | 0 | 4 |
| Captain choices | Chris Olave, Tyler Shough | Chris Olave, Devaughn Vele, Tyler Shough |
| Unique players | 8 | 13 |
| One-QB / two-QB entries | 1 / 1 | 2 / 3 |
| ATL 2–NO 4 / ATL 3–NO 3 entries | 1 / 1 | 4 / 1 |
| Average projected mean | 84.129664 | 81.712198 |
| Average summed marginal P90 | 148.669466 | 145.082617 |
| Average selector | 163.709053 | 158.332801 |
| Average pairwise overlap | 4.00 / 6 | 3.30 / 6 |
| Production default | 95% retained | 95% retained; 94% applies only to this saved candidate set |

**The sacrifice is larger than adding one marginal fifth lineup.** The fresh evidence supports only two entries at 95%. All 23 qualifying lineups require Kevin Austin Jr., and his existing cheap-player cap is **2 appearances across the requested five entries**. The 94% set retains control entry 1, replaces control entry 2 (the maximum-mean/maximum-P90 roster), and admits four sub-95% constructions to reach five.

The average per-entry mean falls by 2.417466 fantasy points; average summed marginal P90 falls by 3.586849. These comparisons involve different portfolio sizes; they do not establish a change in win probability or portfolio risk.

## Frozen inputs and unchanged construction

2026 Week 4 ATL–NO, kickoff October 5 at 8:15 p.m. EDT. Accepted projection run: `b06fd9d9-a31a-4589-bfe6-15988abe66eb`; input cutoff **October 05, 2026 06:59:20 PM EDT**; immutable freeze **07:00:23 PM EDT**. The same 55-player canonical input pool yields 23 optimizer-eligible players for both versions.

QB Captain allowed; maximum two starting QBs; maximum four players per team; five requested entries. Existing correlation, QB, premium-player, opportunity, team-balance and exposure policies are unchanged. No player, Captain, team preference, 3–3 split or QB count was forced. Player caps stay QB **5**, core/non-punt **4**, existing cheap-player category **2**; Captain cap **3**. Caps remain counts based on five requested entries even when the control underfills. Exposure percentages below use actual generated entries.

No model refitting: the saved fitted model, saved training data, residual profiles and workload labels were reused. Available players’ opportunity units matched the saved units exactly, so saved anchor evaluations were reused. Kamara remains **LEAD** and Miller **COMMITTEE**. Fant is inactive and scores zero. Receiving-history windows are unchanged. Only the latest captured market observation for each team is used in the existing reconciliation function; superseded observations remain in the saved source audit.

Full enumeration certifies **43,806** legal max-four/team Captain/roster signatures against every saved production MILP bound and constraint. Both floors use the same independent maxima: **mean 86.111642993191**, **summed marginal P90 150.902376467675**. The production portfolio selector maximizes fill first and summed selector second with unchanged exposure caps. Physical identity is Captain UUID plus the six canonical player UUIDs.

Mean and summed marginal P90 include 1.5× Captain fantasy points. Summed marginal P90 is not a joint lineup P90. Selector is the existing objective including context, Captain weighting and correlation terms; it is not projected fantasy points or expected payout. Selector ranks below are competition ranks across the entire legal universe before quality/exposure screening.

## 95% PORTFOLIO

**2 entries generated.** Captain plus the five listed FLEX players are all six roster members.

| Entry | Captain | Five FLEX players | Team split | QBs | Salary | Mean | Marginal P90 sum | Selector | Selector rank |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Chris Olave | Bijan Robinson; Tyler Shough; Brian Robinson Jr.; Kevin Austin Jr.; Devaughn Vele | ATL 2/NO 4 | 1 | $50,000 | 82.147686 | 146.436555 | 166.515318 | 4 |
| 2 | Tyler Shough | Bijan Robinson; Michael Penix Jr.; Jahan Dotson; Chris Olave; Kevin Austin Jr. | ATL 3/NO 3 | 2 | $49,800 | 86.111643 | 150.902376 | 160.902789 | 54 |

Pairwise overlap: shared canonical players out of six, irrespective of Captain slot.

| Entry | 1 | 2 |
| --- | --- | --- |
| 1 | — | 4 |
| 2 | 4 | — |

## 94% PORTFOLIO

**5 entries generated.** Captain plus the five listed FLEX players are all six roster members.

| Entry | Captain | Five FLEX players | Team split | QBs | Salary | Mean | Marginal P90 sum | Selector | Selector rank |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Chris Olave | Bijan Robinson; Tyler Shough; Brian Robinson Jr.; Kevin Austin Jr.; Devaughn Vele | ATL 2/NO 4 | 1 | $50,000 | 82.147686 | 146.436555 | 166.515318 | 4 |
| 2 | Devaughn Vele | Bijan Robinson; Tyler Shough; Michael Penix Jr.; Alvin Kamara; Kevin Austin Jr. | ATL 2/NO 4 | 2 | $49,900 | 81.131283 | 146.062414 | 162.863062 | 21 |
| 3 | Tyler Shough | Bijan Robinson; Bryce Lance; Jahan Dotson; Chris Olave; Devaughn Vele | ATL 2/NO 4 | 1 | $49,600 | 81.590310 | 146.458584 | 155.615253 | 303 |
| 4 | Tyler Shough | Michael Penix Jr.; Juwan Johnson; Charlie Woerner; Chris Olave; Devaughn Vele | ATL 2/NO 4 | 2 | $50,000 | 81.391371 | 143.903276 | 154.117706 | 445 |
| 5 | Tyler Shough | Bijan Robinson; Bryce Lance; Michael Penix Jr.; Chris Olave; Olamide Zaccheaus | ATL 3/NO 3 | 2 | $49,800 | 82.300340 | 142.552253 | 152.552665 | 637 |

Pairwise overlap: shared canonical players out of six, irrespective of Captain slot.

| Entry | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |
| 1 | — | 4 | 4 | 3 | 3 |
| 2 | 4 | — | 3 | 3 | 3 |
| 3 | 4 | 3 | — | 3 | 4 |
| 4 | 3 | 3 | 3 | — | 3 |
| 5 | 3 | 3 | 4 | 3 | — |

## Player and Captain exposures

| Player | Player cap / 5 requested | 95% player exposure | 94% player exposure | 95% Captain exposure | 94% Captain exposure |
| --- | --- | --- | --- | --- | --- |
| **Alvin Kamara** | 4 | 0 (0%) | 1 (20%) | 0 (0%) | 0 (0%) |
| **Bijan Robinson** | 4 | 2 (100%) | 4 (80%) | 0 (0%) | 0 (0%) |
| **Chris Olave** | 4 | 2 (100%) | 4 (80%) | 1 (50%) | 1 (20%) |
| **Daniel Carlson** | 4 | 0 (0%) | 0 (0%) | 0 (0%) | 0 (0%) |
| **Kevin Austin Jr.** | 2 | 2 (100%) | 2 (40%) | 0 (0%) | 0 (0%) |
| **Michael Penix Jr.** | 5 | 1 (50%) | 3 (60%) | 0 (0%) | 0 (0%) |
| **Nick Folk** | 4 | 0 (0%) | 0 (0%) | 0 (0%) | 0 (0%) |
| **Tyler Shough** | 5 | 2 (100%) | 5 (100%) | 1 (50%) | 3 (60%) |
| Austin Hooper | 4 | 0 (0%) | 0 (0%) | 0 (0%) | 0 (0%) |
| Barion Brown | 4 | 0 (0%) | 0 (0%) | 0 (0%) | 0 (0%) |
| Brian Robinson Jr. | 4 | 1 (50%) | 1 (20%) | 0 (0%) | 0 (0%) |
| Bryce Lance | 4 | 0 (0%) | 2 (40%) | 0 (0%) | 0 (0%) |
| Charlie Woerner | 2 | 0 (0%) | 1 (20%) | 0 (0%) | 0 (0%) |
| Devaughn Vele | 4 | 1 (50%) | 4 (80%) | 0 (0%) | 1 (20%) |
| Drake London | 4 | 0 (0%) | 0 (0%) | 0 (0%) | 0 (0%) |
| Falcons | 4 | 0 (0%) | 0 (0%) | 0 (0%) | 0 (0%) |
| Jahan Dotson | 4 | 1 (50%) | 1 (20%) | 0 (0%) | 0 (0%) |
| Juwan Johnson | 4 | 0 (0%) | 1 (20%) | 0 (0%) | 0 (0%) |
| Kendre Miller | 4 | 0 (0%) | 0 (0%) | 0 (0%) | 0 (0%) |
| Kyle Pitts Sr. | 4 | 0 (0%) | 0 (0%) | 0 (0%) | 0 (0%) |
| Olamide Zaccheaus | 4 | 0 (0%) | 1 (20%) | 0 (0%) | 0 (0%) |
| Saints | 4 | 0 (0%) | 0 (0%) | 0 (0%) | 0 (0%) |
| Zachariah Branch | 4 | 0 (0%) | 0 (0%) | 0 (0%) | 0 (0%) |

All Captain caps remain three appearances. Folk and Carlson each have **0 exposure in both versions**; this is the selector’s result, not an exclusion. Bijan is 2/2 → 4/5, Kamara 0/2 → 1/5, Shough 2/2 → 5/5, Penix 1/2 → 3/5, Olave 2/2 → 4/5, and Austin 2/2 → 2/5.

## Exact 94% concessions versus the 95% screen

95% thresholds: mean **81.806060843532** and summed marginal P90 **143.357257644292**. Percentages are lineup value ÷ the same frozen legal maximum × 100. Figures below retain 12 decimal places; full floating-point values and canonical IDs are in the machine-readable artifact.

| 94% entry | Mean % of maximum | P90 % of maximum | Fails 95% | Shortfall below 95% (percentage points) | Shortfall in fantasy points | Selector rank |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | 94.216392354988% | 96.792653578927% | mean | 0.783607645012 | 0.674777417740 | 21 |
| 3 | 94.749451857381% | 97.055187266724% | mean | 0.250548142619 | 0.215751122099 | 303 |
| 4 | 94.518428067490% | 95.361835313954% | mean | 0.481571932510 | 0.414689503278 | 445 |
| 5 | 95.573997757989% | 94.466539624159% | P90 | 0.533460375841 | 0.805004384657 | 637 |

- **Entry 2 (selector rank 21):** Adds Devaughn Vele Captain and the portfolio’s only Kamara exposure; two QBs, no Olave. This keeps Olave within four entries while using Austin’s second and final allowed appearance.
- **Entry 3 (selector rank 303):** Adds a Shough-Captain one-QB lineup without Austin; Bryce Lance and Jahan Dotson supply cheaper receiving exposure. It helps reach five while preserving Austin’s two-entry cap.
- **Entry 4 (selector rank 445):** Adds a two-QB Shough-Captain lineup without Bijan or Austin, with Juwan Johnson and Charlie Woerner. It supplies the portfolio’s Bijan omission needed to respect his four-entry cap.
- **Entry 5 (selector rank 637):** Adds a 3–3, two-QB Shough-Captain lineup without Austin or Vele, using Bryce Lance and Olamide Zaccheaus. It supplies the Vele omission needed to respect his four-entry cap; the P90 concession is 0.805004384657 fantasy points below the 95% threshold.

**Why the control cannot simply be kept and three lineups appended:** every 94%-eligible roster contains Austin or Olave. Their appearance caps sum to six (2 + 4). Both control entries contain both players, so retaining both in a five-entry portfolio would require at least seven combined Austin/Olave appearances. At least one control entry must therefore be replaced to fill five. The selector retains the Olave-Captain control roster and replaces the maximum-projection Shough-Captain roster.

## Authoritative pregame evidence

Both complete official lists were captured at **06:53:14 PM EDT**. Availability was reconciled against official roster sections; roster placement alone was not used as final dressing clearance.

- [Atlanta official inactives](https://www.atlantafalcons.com/news/atlanta-falcons-week-4-inactives-vs-new-orleans-saints-on-monday-night-football): Cooper Rush (emergency third QB), Jack Strand, Malcom Dewalt IV, Roger Longerbeam, Jared Ivey and Ethan Onianwa. Divine Deablo and Samson Ebukam are available.
- [New Orleans official inactives](https://www.neworleanssaints.com/news/new-orleans-saints-inactives-atlanta-falcons-2026-nfl-week-4-gameday): Zach Wilson (designated third QB), Decamerion Richardson, Anfernee Jennings, Christen Miller, Kaden Elliss, Noah Fant and Carl Granderson. **Christen Miller is a defensive lineman; Kendre Miller is active.**
- [ATL depth chart](https://www.atlantafalcons.com/news/atlanta-falcons-week-4-depth-chart-vs-new-orleans-saints) and [NO depth chart](https://www.neworleanssaints.com/team/depth-chart): expected QBs Penix/Shough; primary kickers Folk/Carlson. Kamara, Kendre Miller, both QBs, Olave, Austin and both kickers are on their active rosters and absent from their complete inactive lists.
- [Final injury report](https://www.neworleanssaints.com/news/injury-report-atlanta-falcons-vs-new-orleans-saints-2026-nfl-week-4-saturday): Fant’s questionable designation is definitively resolved to inactive and he is excluded. Brown has no final game designation. The captured complete inactive lists resolve the earlier defensive questionable statuses; no still-questionable individual is selected.
- [Saints backfield evidence](https://www.neworleanssaints.com/news/new-orleans-saints-running-back-depth-being-tested-early): Kamara/Miller share the expanded backfield; Donaldson retains a short-yardage/pass-protection role. No authoritative numerical snap, carry, target or goal-line split is supplied.
- [Saints elevations](https://www.neworleanssaints.com/news/new-orleans-saints-roster-moves-announced-transactions-2026-nfl-week-4-elevations): Fadil Diggs and Jackson Sirmon. [Falcons elevation](https://www.atlantafalcons.com/news/falcons-elevate-jammie-robinson-for-saints-game): Jammie Robinson. No offensive elevation clears the remaining practice-squad salary players.
- [Current DraftKings market](https://dknetwork.draftkings.com/moneyline-total-spread/), captured 06:52:44 PM EDT: **NO −1.5 / ATL +1.5, total 47.5, implied NO 24.5 / ATL 23.0**. Source observation is current; upstream quote-publication time is not supplied.

[NO roster](https://www.neworleanssaints.com/team/players-roster/) and [ATL roster](https://www.atlantafalcons.com/team/players-roster/) confirm salary-pool IR: NO Etienne, Chandler, Moliki Matavao and Jordyn Tyson; ATL Beaux Collins and Trey Sermon. Mason Tipton is PUP. Practice-squad players remain excluded, including Smyth and Zamir White; the full 13-player PS list is retained in the context artifact. Austin’s active-roster status is verified; no new projection bonus was added.

Retained DraftKings evidence: **112 native CPT/FLEX salary rows, 55 resolved canonical players plus unresolved Cal Adomitis**. File SHA256 `cbaa10b29e0bfe24adeaf779faa2b444426fbe18064104e0a8085ca1d1983ad1`; all 42 selected slot occurrences across both portfolios match canonical UUID, native DK ID, CPT/FLEX slot and exact salary. Native draft group and a fresh official salary download remain unverified.

## Saved artifacts and validation

Accepted input freeze SHA256 `9a4727c8c5d0f10b98c8f3f70e32643136b551f09d85db77faec543896a4a9c1`; prepared snapshot SHA256 `03d1e2d4906c4418290580aa3cafbc6e26f2ae7a772b7ff5dddb1909afe5f7af`. Fitted-model source artifact SHA256 `4bc43d84c3b6f13217d19b2a8b67f102235bb28e6ba227c754d9e766b809d665`. Verification passes all legality, quality, exposure, uniqueness, official-active and native-salary checks; **752 production/source file hashes are unchanged**, including every prohibited implementation/default area.

- [Accepted immutable input freeze](/Users/wones/git/football_26/artifacts/atl_no_prelock_final/20261005T225137Z/final/input_freeze.json)
- [Both portfolios, exact metrics, exposures and overlap](/Users/wones/git/football_26/artifacts/atl_no_prelock_final/20261005T225137Z/final/final_candidates.json)
- [Prepared production solver/input snapshot](/Users/wones/git/football_26/artifacts/atl_no_prelock_final/20261005T225137Z/final/prepared_input.json)
- [Verification and preservation checks](/Users/wones/git/football_26/artifacts/atl_no_prelock_final/20261005T225137Z/final/verification.json)
- [Current source lineage and latest-market selection](/Users/wones/git/football_26/artifacts/atl_no_prelock_final/20261005T225137Z/final/scored_source_versions.json)
- [Salary verification](/Users/wones/git/football_26/artifacts/atl_no_prelock_final/20261005T225137Z/final/salary_verification.json)

## PRE-LOCK WARNINGS

- **Candidate sets only; true entry-ready certification is incomplete.** Native draft-group/contest assignment and authenticated entry-file mapping were not verified. The retained salary input was checked, but no fresh official DK salary download was obtained; the public draft-group lookup returned HTTP 400. No entries were uploaded or submitted.
- **RB workload split remains estimated.** Kamara/Miller carry redistribution and numerical opportunity allocation are the prior corrected model assumptions, not confirmed snap/route/red-zone workloads. Kamara remains LEAD and Miller COMMITTEE; no role redesign was performed.
- **Kevin Austin’s history-window concern remains unresolved.** His saved receiving records include 2025 W17/W18 and 2026 W2, while recent participation records cover 2026 W1–W3. His roster/game availability is cleared; forecast currency was not investigated or changed. He is required in every 95%-eligible roster and reaches his two-entry cap in both sets.
- **Full salary-pool identity coverage is incomplete.** Cal Adomitis has two native salary slots without a canonical mapping; Zach Wood’s salary TE versus official LS position mismatch remains quarantined. Neither appears in either portfolio. Unmatched official-source rows remain in the saved identity-review artifact.
- **Model limits remain unchanged.** Summed marginal P90 is not a joint ceiling or a portfolio-risk estimate; selector is not calibrated EV. Role-specific ownership is incomplete/diagnostic and its selector term stays disabled uniformly. The existing calibration limitations, including sparse kicker residual evidence, were not repaired.
- **Use the accepted frozen artifacts for review.** The live active-projection selection/defaults were not switched to this candidate report. Evidence is valid as observed at the recorded clocks; later changes after the freeze are not certified. Work stops with this report; no continuing research, fitting or refresh is scheduled.
