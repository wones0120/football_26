# Monday named Captains — actual saved app portfolio

The optimizer saved four valid lineups under the user's named Kittle/Daniels/Purdy Captain exceptions, preserving WR/RB defaults and the supported-workload gate. **Use its provisional recommendation #2**, not a hand-selected replacement. Purdy Captain appears2/4 and Daniels Captain2/4: each exactly50%. Kittle was eligible and searched, not forced. No contest entry or browser download occurred.

## Saved lineups

|Lineup|Captain|FLEX|Salary|Mean|
|---|---|---|---:|---:|
|#1|Brock Purdy $16,200|Drew Stevens $5,000; Jordan Watkins $2,000; Jayden Daniels $10,000; Christian McCaffrey $11,800; Antonio Williams $4,200|$49,200|76.946|
|#2 — recommended|Brock Purdy $16,200|Drew Stevens $5,000; Jordan Watkins $2,000; Jayden Daniels $10,000; Chig Okonkwo $4,600; Christian McCaffrey $11,800|$49,600|77.640|
|#3|Jayden Daniels $15,000|Drew Stevens $5,000; Brock Purdy $10,800; Dyami Brown $2,600; Christian McCaffrey $11,800; Antonio Williams $4,200|$49,400|76.674|
|#4|Jayden Daniels $15,000|Drew Stevens $5,000; Brock Purdy $10,800; Chig Okonkwo $4,600; Dyami Brown $2,600; Christian McCaffrey $11,800|$49,800|77.368|


Recommendation #2 has the highest mean among this run's valid generated GPP candidates. It exchanges Antonio for Okonkwo relative to #1, using $400 more and adding0.694 mean. The four-entry selector first maximizes feasible size, then best-roster coverage and conditional upside across the checked reference world; the standalone recommendation uses projection-first ranking. Eight distinct full candidate rosters were generated. This is bounded generation, not a proof of the best roster across every legal combination. Sums of marginal P90s are **not joint lineup P90 or win probabilities**. Paid-finish probability/expected return are unavailable.

## Football case and risk

Purdy Captain needs San Francisco passing production to earn the premium: McCaffrey can contribute through receiving and rushing, Watkins supplies a cheap current depth-chart receiving path, and Washington's response runs through Daniels and Okonkwo. Stevens can score on Washington drives that stall, alongside successful touchdowns elsewhere; the construction does not require every drive to finish identically. #1 substitutes Antonio's receiving production for Okonkwo. Daniels Captain in #3/#4 needs his passing and/or rushing output to lead Washington, with Antonio or Okonkwo and low-cost Dyami Brown benefiting from the response. Purdy and McCaffrey preserve San Francisco scoring exposure.

The shared core in all four is **Purdy/Daniels/McCaffrey/Stevens**. All four depend on both starting QBs producing enough for their salaries. Cheap Watkins (model2.115mean) or Dyami (2.534mean) saves the salary needed for those stars; depth opportunity is not a supported large target forecast. A failed cheap-support role, Washington offensive collapse or McCaffrey rushing touchdowns displacing Purdy passing touchdowns can hurt multiple entries together. Stevens and Washington receiving supports also compete for touchdown-versus-field-goal drive endings. No automatic teammate penalty, target transfer or invented probability was applied.

Fresh prepared market evidence is SF−7.5,total52.5 (implied SF30/WAS22.5), observed2026-10-19T01:23:16UTC. It supports an SF-favored setting; it does not prove a blowout. A ground-dominant SF win is a useful counter-scenario, and it is less favorable to four lineups sharing both QBs. The current user's settings and model were retained rather than forcing that scenario.

## Supported Captain workload and alternatives

Purdy and Daniels qualify through sourced QB1 role evidence, observed2026-10-18T12:02:37UTC, corroborated by current official team depth charts; each has100% latest observed snaps. Historical recent carries are5.667 and7.0 respectively, not authored next-game forecasts. Kittle qualifies with original pre-allocation6.333targets/game,24.54%target share and92%latest snaps. McCaffrey qualifies with13.667carries/game,71.69%carry share and82%latest snaps. Antonio remains excluded at Captain for insufficient supported workload, while retaining unchanged FLEX assessment.

Kittle's allocated `projected_targets` proxy is2.945; it is not an independently calibrated expected-target forecast and was not used to certify workload. Missing routes/explicit next-game workload remain unknown. The same distinction applies to McCaffrey's allocated carry proxy. The operational gate is a conservative role policy, not a calibrated Captain-success probability.

These full alternatives already existed in the **same eight UI-generated candidates**, but were unselected. They are shown diagnostically, not as additional saved lineup records or a portfolio satisfying exposure:

|Lineup|Captain|FLEX|Salary|Mean|
|---|---|---|---:|---:|
|George Kittle CPT — unselected candidate|George Kittle $12,300|Jordan Watkins $2,000; Jayden Daniels $10,000; Brock Purdy $10,800; Dyami Brown $2,600; Christian McCaffrey $11,800|$49,500|70.340|
|Christian McCaffrey CPT — unselected candidate|Christian McCaffrey $17,700|Drew Stevens $5,000; Jordan Watkins $2,000; Jayden Daniels $10,000; Brock Purdy $10,800; Antonio Williams $4,200|$49,700|73.149|


Kittle Captain provides a direct high-volume receiving touchdown path, but paying him while retaining both QBs and the required non-QB leader forces two cheap receiving supports. McCaffrey Captain expresses SF ground/receiving control, but the same star salaries still require Watkins/Antonio and Stevens. The saved optimizer preferred the QB-Captain candidates under its present reference objective. This is an objective/construction tradeoff, not evidence those other football paths are impossible or less likely by a measured percentage. Named exceptions change eligibility only; they never force selection or change model projections.

## Current injury/role sources

Fresh captured [Washington injury report](https://www.commanders.com/team/injury-report/) lists Daniels full Thursday/Friday/Saturday, Croskey-Merritt OUT, Mariota OUT and Diggs QUESTIONABLE. The [SF injury report](https://www.49ers.com/team/injury-report/) lists Evans QUESTIONABLE and Deebo OUT; McCaffrey is full after rest. UNSPECIFIED/blank designation is not affirmative health proof. [Washington depth](https://www.commanders.com/team/depth-chart) lists Daniels QB1, OkonkwoTE1 and StevensK; [SF depth](https://www.49ers.com/team/depth-chart) lists PurdyQB1,KittleTE1,McCaffreyRB1 and Watkins/Cowing receiving depth. These public pages were captured and semantically reviewed01:12–01:14UTC; exact source clocks and citations are in sources.json. No unsupported numeric workload transfer was authored.

The first actual UI preparation ac49f176-dd3b-4cd2-87c6-d04aa3548ac6 failed because old Oct17 native status facts for Cracraft/Aiyuk expired. The current exact-ID-bound [Monday native source](https://api.draftkings.com/draftgroups/v1/draftgroups/154960/draftables) affirms Cracraft FLEX44533119 Q and Aiyuk FLEX44533134 OUT. The narrow fix extends the existing Classic immutable native collector to Showdown GameType96 and explicit Q, matched to the exact game/kickoff and native imported identities. Blank status never clears injury; Cracraft's missing role stays unknown and he remains excluded by Q/base salary. It does not label low-salary players OUT, lower the $1700floor or bypass model input checks. Preparation captured native sources01:23:22/23UTC with no identity discrepancies; availability unknown count became0, while unresolved roles remained explicit.

## Actual workflow and export evidence

Actual UI Prepare **95e6797d-56b8-4273-9a9f-c7844f8f55b9** completed01:25:20UTC, showing Ready—prepared inputs verified. Projection **ed6021d1-066a-459b-b84e-c2572a120c67**, cutoff **2026-10-19T01:24:00.863594UTC**. Actual Run Optimizer saved **3cefbcab-4581-4e6e-b580-4f8d2425de7e**, operational job528f7593-f6f1-437b-9e1f-746397402aff, completed01:26:54UTC. Clicked Reopen results, then Check upload readiness. The UI says **Upload ready pending inactives**, valid until **2026-10-19T01:57:58.899920UTC**. Immutable clearance record evaluation-54099f79d76d31281b90c52fc05012e6b1749fe21af942256165daf5a296ef29.

Public recommended/all download responses returnedHTTP200 with valid CPT+fiveFLEX headers and exactly1/4rosters; every native ID matches the saved corresponding roster, including Captain-specific IDs. No browser CSV download occurred. Clearance expires and can be rechecked in the saved run. The frozen consumed-input entry-readiness report remains unevaluated/blocked on raw-pool issues and final facts; it is preserved separately from the newer, selected-roster upload clearance. Neither report proves final dressing, contest assignment or submission.

Exact user settings are in ui_request_audit.json and verification.json:4entries,100%player,50%Captain,$1700baseFLEXminimum,max4/team,WR/RB plus exactly Kittle/Daniels/Purdy named exceptions,leaderrequired,Qexcluded,noavailabilityexceptions,noQBbans,twoQBsallowed,nooffensevopposingDST. Canonical optimizer-params SHA256 **aeb9312c71a7c3608734c00ea5203e9e39091904a1a6f043279079cdf44b113b**; durable optimizer request hash d1729e56a6c50d5d843e56758d69d63859c4024502b99a74fc8f2ffda999132e. Analyst reference was refreshed and checked by normal Prepare; no numerical boost was authored. Its historical findings include weakened/contradicted conditions, explicitly visible in the handoff; those are not relabelled as verified forecasts.

Prior Monday fca1714e and failed8ae12f6f remain preserved; Sunday ee5d9a9f-b712-47cb-96c7-b1826843bd16 fresh-read remains completed. No Morning/Main/Tiers/Single Stat lineups were changed. Learning Tiers/Single Stat implementation was safely checkpointed and resumes after this acceptance.

24targeted native-status/context tests passed, plus62focused Captain/QB preference tests from the named-exception reporting repair. Managed API/worker reload followed a fresh empty running/queued check; no active job was interrupted. No broad tests, independent training sweep, global preference/default change or hand-written lineup DB insertion occurred.
