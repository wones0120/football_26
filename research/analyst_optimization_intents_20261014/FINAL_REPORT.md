# Expected Game / Contrarian implementation and Chrome acceptance

**Complete: both actual Chrome intent flows save and reopen 4/4 from one matched Prepare.**

- Expected Game: `2ab7a4ee-9b6e-4898-a97c-2191b5c946a9`; only `expected_competitive_reference` / `expected_sea_drive_upside`.
- Contrarian: `6a822f1f-1871-4ecc-bacf-9c4197fad2fa`; only `contrarian_den_breakout`, with typed DEN QB + two WR/TE requirements and no Captain-team forcing.
- One shared Prepare: `bd681f04-f75f-4064-9754-615425544053`. Projection `817d8fa9-1d36-4896-aab3-7999ff4902e9`, ownership `4f636d8e-8398-44c8-bb63-3d4aa1327611`, source SHA `01cc5aa4bb2b74f020f7ca67fb26869a7281fc9465e23765c268171dbfb401f6`.

The app now separates these intents, freezes automatic scoped packets and compatibility receipts during Prepare, persists intent/scenario lineage in saved runs/results, labels recent runs and provides a persistent side-by-side roster/salary/scenario/exposure comparison. Missing authored classification or mismatched intent/packet/scenario receipts block without mixed/baseline fallback. Expected Game explicitly excludes user what-ifs. A new source-backed primary/alternate research decision preserves predecessor packets and original source clocks; no expiry was merely extended. Source/model truth and user settings are unchanged.

All 30 asserted user-control values match the prior authorized Thursday research request (DEN opponent exclusion OFF, all other controls retained). The opponent exclusion edit is now scoped/persisted for the active context so an app refresh cannot silently restore DEN for this comparison or change another slate's setting. Final entry readiness stays false.

Exact validation: selected intent receipt equals prepared receipt in frozen optimizer evidence, runtime expanded compatibility and applied handoff; checked/scoped/authoring hashes trace immutably; lineup tags and generation worlds contain only the chosen intent. Shared salary/source/projection/ownership, base legal model and prepared player rows match. Distinct candidate pools are disclosed as generation experiments. Each intent achieved four unique Captains at 25% without constraint relaxation, with canonical leader, salary, QB pairing, team-count and Q-exclusion assertions. One role-relevant roster overlaps between portfolios; three differ. Full player-level comparison and honest story limitations are in `SIDE_BY_SIDE_REVIEW.md`.

Verification found an initial audit-report link still pointed to the parent mixed receipt although the correct scoped packet drove generation. The evidence return path was repaired to carry the selected intent receipt; the final saved runs above pass full receipt equality checks. Earlier first-pass records `d5e9a158…` / `29e16a8e…` remain intact as historical evidence and are not the final acceptance runs.

Validation: 87 affected backend tests and 8 UI tests passed; the audit-return correction also passed the 30 affected preparation/intent tests. TypeScript/Vite build, Python compilation and diff whitespace checks passed. Desktop Chrome visual checks confirmed readable two-column rosters and persistent comparison after reload. Idle managed API/worker restarts loaded the feature and audit fix without interrupting active jobs. No dependency/config/schema/default projection changes or contest actions were made. Existing dirty work and all old artifacts were preserved.

Implementation: `analyst_intents.py` and focused tests; extensions to packet validation, preparation, binding, scenario generation, request validation and saved history; `analystIntent.ts`, `AnalystIntentComparison.tsx/.css`, App selection/wiring, recent-run labels and API types; README, RELEASE_NOTES, and product intent/preparation docs.

Evidence: `FINAL_COMPARISON.json`, `expected_final_job.json`, `contrarian_final_job.json`, `preparation.json`, `packet.json` / `packet_receipt.json`, final reopened/reloaded DOM captures, `final_comparison_text.txt`, `comparison_view.jpg`, `comparison_lineups_view.jpg`. The full user review is `SIDE_BY_SIDE_REVIEW.md`.
