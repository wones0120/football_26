# Monday Night — refreshed saved optimizer portfolio

Actual app workflow completed: current controls→Prepare→RunOptimizer→reopen saved result→CheckUploadReadiness→publicCSVresponse validation. No browser download, contest entry, manual packet or research-selector promotion occurred. The four fresh saved rosters are preliminary for final inactives.

Run **8a4a1d21-4b13-4ed0-baf4-b48d95da967e** completed4/4; workerjob4b997938-bcf5-4861-b83f-a723ee88b169. Preparationjob1823d85a-dc23-4210-9745-b885cf4c1889 produced projectionf7cc2ef6-812d-4d38-91aa-fa5b60754f05, cutoff**2026-10-19T13:49:47.743907UTC**, prepared13:50:59.738168UTC. Native salary120rows/60CPT-FLEXpairs confirm exactly oneWAS@SFgame tonight20:15ET. No secondgame belongs to this slate.

## Recommendation and complete portfolio

The app recommends **#4**, highest mean among this run’s four saved candidates. It is the same canonical roster as oldrun3cefbcab’s#2, not a hand-picked substitution. FreshQB/context predictions lowered its mean77.640→76.345. All four prior canonical rosters remain in the fresh portfolio, with a different order. This is a current refresh, not demonstrated selector improvement.

|Saved order|Captain|Five FLEX players|Salary|Current mean|
|---|---|---|---:|---:|
|1|Brock Purdy|Drew Stevens, Jordan Watkins, Jayden Daniels, Christian McCaffrey, Antonio Williams|$49,200|75.651|
|2|Jayden Daniels|Drew Stevens, Brock Purdy, Dyami Brown, Christian McCaffrey, Antonio Williams|$49,400|75.595|
|3|Jayden Daniels|Drew Stevens, Brock Purdy, Chig Okonkwo, Dyami Brown, Christian McCaffrey|$49,800|76.289|
|4 · recommended|Brock Purdy|Drew Stevens, Jordan Watkins, Jayden Daniels, Chig Okonkwo, Christian McCaffrey|$49,600|76.345|

Recommended native slot IDs: **CPT44533136; FLEX44533091,44533103,44533077,44533092,44533075** (Purdy;Stevens,Watkins,Daniels,Okonkwo,McCaffrey). CanonicalIDs and native IDs/roles in monday_optimizer.json and the CSV validation receipt were compared to the unchanged local native salary source. RecommendedCSV has1row, AllCSV4rows, bothHTTP200; all slots match saved rosters, salaries≤$50,000 and every baseFLEXsalary≥$1,700.

## Settings, workload and what was actually considered

The two immutable UI request receipts differ only in four normal derived preparation/checked-Analyst fields. All other user and strategy parameters match exactly: fourlineups,player100%,Captain50%,basefloor1700,WR/RBdefault plus namedKittle/Daniels/Purdyexceptions,max4/team,nonQBseasonleaderrequired,Qexcluded/noQoverrides,twoQBsallowed,nooffenseversusopposingDST,DENopponentexclusion,ExpectedGame/AUTO; no added overlap/risk cap. Settings digest (excluding only those four derived receipt keys): **d12cdc9e24a8a895e869d5e6d74130127d47a6dfdaf8f38ee9ff623f123e3cd4**. Full definition and actual params are in settings_verification.json, source receipts in monday_ui_requests.json.

Actual Captain counts arePurdy2/4 andDaniels2/4, each50%. Both pass sourced-starting-QB qualification with1.00latest snap share; observations are not guaranteed game participation. Kittle is allowed, passed workload qualification and had2real supporting candidates. His original6.333recent targets/24.54%targetshare/92%latest snaps—not the allocated2.945targetproxy—support eligibility. No new target forecast was invented. His best generated Captain roster isKittleCPT/Watkins/Daniels/Purdy/Dyami/CMC,$49,500,mean69.391; the Cowing support alternative is$49,700,mean68.867. Those complete alternatives sacrifice Stevens/Okonkwo production and force cheaper receivers while bothQBs/CMC remain; salary savings do not establish that KittleCPT beats the saved mean. CMC also has2supported Captain candidates. Named eligibility does not force their selection; Antonio remains rejected at Captain by the unchanged workload gate and eligible at FLEX.

## Football case and shared failure

Recommended#4 succeeds through Purdy scoring, a Washington response led byDaniels, usefulCMCproduction and enough receptions forOkonkwo/Watkins, withStevens converting scoring drives. It uses$800more than#1 to replaceAntonio withOkonkwo for+0.694mean; compared with#3, the modelmeanedge is only0.056FP, far too small to describe as certainty. The twoDanielCaptain variants emphasizeWashingtonQB scoring, whilePurdyCaptain emphasizesSFpassing—but all four still sharePurdy,Daniels,CMC andStevens. This is concentrated game-path exposure, not four independent bets.

SFcontrolling viaCMC rushing TDs remains a credible contrary path and can reduce Purdy’s passing payoff. Washington offensive collapse can hurtDaniels,Stevens and cheapWASreceivers together; BosaOUT is a counterpoint to assuming that collapse. DeeboOUT does not automatically give Kittle/Watkins all vacated targets, and currentWatkins/Dyami/Antonio receiving volume is uncertain. CMC’s currentmodelmean12.283 is preserved, not raised to fit a blowout story. Neither mean nor summed marginalP90 is a calibrated lineup win/cash probability. The recommendation is provisional within generated candidates, not global tournament optimality.

## Current source assumptions and clearance

Fresh primary-page review and supportedPrepare ingest retainCroskey-MerrittOUT/MariotaOUT,DeeboOUT/BosaOUT;Evans/Kirk/DiggsremainQ and excluded under current policy. Washington’s coach describesWhite/Ekeler as a combination, withMcNicholsactivationpending; no arbitrary carries/targets transferred. The saved pool showsWhite/EkelerofficialACTbutnativeplayer_statusQ, so the unchanged userQexclusion still excludes them with explicit preference reasons; this is not anOUT assumption or model removal. The$200McNicholsnativebase is below theuserfloor regardless of activation; his potential opportunity does not become another player’s automatically. Current source links/publication limits are retained in monday_primary_sources.json.

Prepare consumed33projectionrows, currentavailabilityrowIDs and both canonicalstarterIDs; freshmarketcapture13:48:52UTC is not independent proof of sportsbookquote publication time. AutomaticcheckedAnalystreceipt was used, preserving researchdecision01:14:47UTC; its compatibilitycheck at13:51:19 does not renew authored research. Recorded contradictions/missing checks remain visible, not erased.

Saved roster-scoped uploadcheck **evaluation-74a9ce9f6a078c8d389e3b32ce4023ccb9e41ced391ad3f6d2e0ce97ff982b30** passed at2026-10-19T13:53:27.557527+00:00 until**2026-10-19T14:23:27.557527+00:00**, statusUPLOAD_READY_PENDING_INACTIVES. All selected players passed that separate check; entry_ready/final_active_confirmed remainfalse. Final official inactives are expected~18:45ET(22:45UTC),90minutesbeforekickoff. Downloads are enabled for the saved checked run during this temporary window; a later download may require another supported check. No game dressing or contest acceptance is certified.

After the uploadcheck appended fresh official/context captures, the generic Operations generation preflight displayedRiverCracraftmissingrole/status and marked the prior preparation no longercurrent. Riveris outside the$1,700legalpool; this raw-pool/preparation display is separate from the successful savedroster check and validatedCSV. Do not claim the entire future-generation preflight remained green, bypass it, or regenerate just to hide the warning. A new operational generation must complete its own currentPrepare; the saved preliminary portfolio remains independently reviewed. The issue is recorded as a follow-up, not resolved by this report.

## Evidence/runtime

CurrentAPI and worker were aligned by an idle managedrestart after publicrunning/queued lists wereempty; the script’s shorthealthwindow expired, but follow-upconfirmedAPIhealth and workerPID29731/API29734. NormalPrepare performed its standardmodelrebuild; no extra researchfitting/selector was invoked. Saved modelartifact219ba613-c209-40d1-9bd6-683ddffeea9c and sourcecutoff belong to this normalworkflow. No allocator/selector default was changed. monday_recommended.png and monday_reopened_and_upload_checked.txt are actualbrowserproof. monday_prepare_job.json, monday_optimizer.json, clearance/request/settings/CSVreceipts retain exactlineage. Earlier saved/entered runs remain preserved.
