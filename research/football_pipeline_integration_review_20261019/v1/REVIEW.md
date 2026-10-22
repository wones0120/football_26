# Football pipeline integration review — 2026-10-19

Read-only diagnosis and implementation handoff. No operational jobs, training, settings changes, new lineups, source writes or application edits were performed. This document describes the saved Monday run `8a4a1d21-4b13-4ed0-baf4-b48d95da967e`, before the separately requested new FanDuel injury import. Extensive existing uncommitted work was inspected and preserved. Football-awareness review applied; no Extra High escalation is needed.

## Main finding

The public path is wired to consume structured football research, but the actual Monday Expected Game packet supplies **one neutral reference world and no authored role, Captain, specialist or game-outlook analysis**. Automatic preparation validates and selects published research; it does not produce missing football reasoning. Improving the research producer and its freshness binding is necessary. Adding another selector, blanket kicker restriction or teammate penalty does not fix this gap.

There is also an independent factual eligibility bug: stale salary Q can keep a player excluded even when stronger current evidence clears the designation. Fixing only source collection cannot fix its downstream OR-based eligibility binding.

## Exact executing path and saved evidence

| Step | Executing code | What it actually does |
|---|---|---|
| Public Prepare | `slate_preparation.py:649–696` | Refresh source services, build an explicit projection/ownership pair, assess readiness, load canonical prepared rows, then prepare Analyst handoff. |
| Source refresh | `showdown_data_readiness.py:413–428, 486–582` | Capture injuries, refresh NFL official report and starters, compose canonical context, then rebuild from a frozen cutoff. Imported injury CSV is retained evidence; the source manifest also includes curated injuries. |
| Availability composition | `showdown_player_context.py:95–184, 469–547` | Combine separately clocked salary, roster, injury, native status, depth and starter facts. Select latest current nonunknown game/injury designation; preserve ACT roster separately. |
| Analyst AUTO | `analyst_preparation.py:175–231` | Choose newest usable published packet for exact game/kickoff/format, scope to intent, revalidate, and save a new checked artifact. No research agent runs here. |
| Public optimizer binding | `slate_preparation.py:410–489`; `analyst_preparation.py:238–269` | Require matching preparation, source/feature/projection hashes and availability controls; bind the exact checked intent packet. Changed source inputs require a new preparation. |
| Scenario generation | `optimizer.py:8449–8486`; `analyst_scenarios.py:179–228, 293–328` | Capture the existing legal model, build conditional moments, solve candidates under unchanged hard controls, and select a portfolio. Exact replay restores base projection fields. |
| Selection | `analyst_scenarios.py:432–567` | Enforce user exposures/overlap and maximize feasible count plus conditional coverage/utility. This is not a calibrated lineup-win model. |

The authoritative saved response is `research/sunday_night_results_monday_refresh_20261019/v1/monday_optimizer.json`, with preparation in `monday_prepare_job.json` and preserved settings in `settings_verification.json`.

- Source packet: `98249d1a82086f9143e59cecd8a868f6df55f3802ae4e5981e5cff0cb35c2cf1`, ID `20261018_MONDAY_WAS_SF_named_captains_reference_v2`.
- Checked Expected Game packet: `a2e078d40075abfe1f810ccfc23fe6253bb3f2b7a4baea4ecb6b34975d0e21d1`.
- Authored decision: `2026-10-19T01:14:47.310099+00:00`; separate compatibility check: `13:51:19.723746+00:00`.
- Active features: only `scenario_assumptions`. Expected Game scenario: `monday_reference`, “Fresh prepared reference; no opportunity adjustment”; SF passing factor **1.0**, elasticity **0.6**. All conditional moments therefore equal their base inputs.
- No `captain_analysis`, `team_game_outlook`, `weekly_role_review`, `defense_kicker_analysis` or `discovery` block exists in the checked packet. The generated specialist report is a default watchlist with missing drive/stall evidence. Weekly scan reports zero reviewed candidates and unavailable prior-week history. These are honest missing reports, not completed football analysis.
- The saved selector reports **one distinct shared outcome**, **two initial candidates**, **eight expanded candidates**, and **four selected rosters**, with no relaxed constraints. Captain coverage expansion changes search breadth; it does not create a new football mechanism.
- The effective candidate objective is `mean + 0.35 * (P90 - mean)`, with Captain multiplier. The final recommendation chooses highest base mean among the saved portfolio. This explains why refreshed facts can leave the same roster set.

## Confirmed defects and nondefects

### 1. Factual designation is not resolved consistently

`official_injuries.py:93–96` converts a blank official Game Status cell to `None`. `:212–216` preserves its practice evidence without expressing a cleared final designation. A blank generic source must remain unknown; a verified final team report explicitly showing no game designation is a different typed fact. The current parser does not distinguish them.

`showdown_player_context.py:125–132` chooses latest nonunknown status by observation time without final-report authority semantics. More decisively, `player_pool_safety.py:576–579` excludes Q if **salary Q OR injury Q**, regardless of a stronger resolved status. `canonical_projection_inputs.py:192–197` similarly ORs salary Q when applying explicit Assume Questionable Out. Merely importing a newer FanDuel file or adding official ACTIVE context cannot reliably supersede old salary Q throughout these consumers.

The recorded McLaurin case is a regression fixture, not a new live clearance claim: the captured final team report and older salary Q disagree. ACT roster membership alone cannot resolve it. Preserve both original observations and the user’s exclude-Q policy; repair the factual designation that policy evaluates. A new injury CSV requires scope/identity/status/clock validation and a new Prepare before any downstream effect can be claimed.

### 2. Absence evidence does not identify a replacement role

Real injury context deliberately defaults redistribution to zero (`canonical_projection_inputs.py:1204–1236`). Sourced recipient roles or explicit supported allocation are required. This is appropriate: Deebo OUT does not establish Watkins targets. The saved Watkins role is backup, without verified expansion. His 1.667 historical targets average means last observed records across seasons, not recent current-season games; `canonical_projection_inputs.py:798–826` implements this behavior. Original observations and allocation proxies are now separated by `workload_evidence_v2`; that semantic repair does not create a new forecast.

Existing scenario transfers are also not an injured-donor mechanism: revalidation treats the donor as required and suppresses the scenario when he is OUT (`analyst_preparation.py:117–120`), while scenario construction uses legal eligible rows and requires positive measured donor/recipient amounts (`analyst_scenarios.py:127–147, 214–217`). A valid active-player concentration sensitivity should keep its current contract; an absence-conditioned mechanism needs a distinct reference population and explicit dependency semantics.

### 3. Fresh source checks do not refresh semantic mechanisms

Revalidation explicitly records `semantic_research_refreshed=False` (`analyst_preparation.py:149–155`). It suppresses typed contradictions/expiry and logs changed baseline values, but does not investigate replacements, coaching intent, opponent response or salary tradeoffs. Any change can produce `needs_review`; a usable checked packet still executes. That broad status is too weak to tell “checked reference-only research” from “fresh football mechanisms with complete supporting evidence.” This is a producer/coverage gap, not evidence that an LLM call is needed inside each solver.

### 4. Kicker selection follows inputs, budget and controls

The legal saved pool has 15 players after current safety/preferences. Drew Stevens costs $5,000 with mean 8.32/P90 14.881; Eddy Pineiro costs $5,200 with mean 6.65/P90 13.211. The neutral scenario does not model drive stalls or competing touchdowns. There is no evidence in this run that a specialist football mechanism selected them.

The matched full-roster enumeration in `research/monday_creative_alternatives_20261019/v1/REVIEW.md` reproduces the saved highest-mean roster exactly. Purdy CPT/Stevens/Watkins/Daniels/Okonkwo/CMC costs $49,600, mean 76.345. The saved Daniels CPT/Stevens/Purdy/Okonkwo/Dyami/CMC alternative costs $49,800, mean 76.289. Removing the specific Watkins concern costs only 0.056 base mean here, but replaces it with another uncertain cheap role.

Kittle FLEX or conditional McLaurin FLEX under the preserved non-QB leader requirement loses Purdy and uses two kickers; the recorded means are 71.258 and 71.720. That is a whole-roster salary/constraint tradeoff, not proof that two kickers are better football. Kittle/CMC need productive SF opportunities; Washington must respond for Daniels/receivers, while kicker FG success needs some drives to stall. Those branches can coexist, but likelihood is uncalibrated and all production cannot be treated as independent. Keep credible kicker alternatives and show their costs; do not ban kickers or force replacements.

## Smallest coherent implementation sequence

### A. Resolve factual status once, then bind all consumers

Add a shared designation resolver used by canonical composition, Q preference eligibility, readiness and explicit Q availability scenarios. Return effective designation, evidence class, original source IDs/clocks, superseded facts and unresolved conflicts. Separate final game designation, game dressing, roster membership and practice participation. Verified final no-designation can supersede older Q without implying confirmed game activation or workload health; missing/blank generic feeds cannot. Later authoritative OUT/inactive facts and unresolved contemporaneous contradictions remain explicit. Do not use ingestion recency to manufacture publication recency. Preserve raw sources and user policy.

Fixtures: McLaurin captured final-report/no-designation versus old native Q; current Q; later OUT; ACT-only; blank native; mismatched slate/player; conflicting authoritative reports; stale recaptured article; new FanDuel import whose status is unchanged. Assert identical factual resolution at preparation, Q gating and saved report. Projection means stay unchanged unless the existing explicit projection availability path is intentionally exercised and validated separately.

### B. Connect a bounded research producer to the existing packet consumer

Reuse immutable capture, packet validation/import and prepared handoff. Produce one small material-change research request keyed by canonical game scope, factual injury/role/workload/market dependency digest, producer version and prior packet. Retries are idempotent. Content hashes alone are insufficient: bind effective semantic facts and original observation clocks so repeated retrieval does not force repeated research or renew old evidence.

Use an existing scheduled/event-driven Codex research worker to consume that queue, investigate only affected games/roles using current primary evidence and publish a new typed packet through the normal import path. No new paid API, secrets or Python-side autonomous agent dependency is required. The worker must finish the loop: request → evidence → typed findings/conditions/counterevidence → validator → publication → new checked Prepare receipt. A queue that only reports “needs review” is incomplete. If no such worker is installed, the implementation must include and verify that bounded scheduled producer, not silently claim automation.

Expose `reference_only`, `mechanisms_current`, `mechanisms_partial`, `refresh_pending` and failed/unknown reasons separately from ordinary source readiness. Retain valid unaffected mechanisms while refreshing affected branches; do not relabel a neutral factor-1 packet as completed football research. Preserve explicit baseline/reference mode and the prior immutable packet. No requirement that every injury generates a favorable action.

### C. Make replacement mechanisms executable without inventing opportunity

Add optional typed conditions distinguishing required-active from required-absent and role-expansion evidence. Read factual vacated **same-team** workload from the frozen pre-exclusion reference pool; score only eligible recipients. Record measured/unknown removed volume, named supported recipients, already-incorporated model inputs, transferred and unallocated amounts. An excluded-by-user Q player creates no vacancy. Do not transfer absent work twice when base projections already incorporate it. Missing recipient history remains unknown; a validated explicit forward role can support a zero-history player without dividing by a fabricated historical count.

Until a projection response is independently validated, these actions remain clearly labeled conditional sensitivities/candidate constructions; base model means do not change. Preserve active-player transfer semantics and old packets. Watkins without expansion evidence remains no-action/watchlist. This distinguishes a successful detection of missing evidence from an automatic boost.

### D. Complete the feedback loop in the actual saved result

For every selected canonical roster, save and display: complete success path; shared target/carry/scoring dependencies and contrary path; each cheap role’s evidence; binding user controls; a legal matched full-roster alternative with salary reinvestment/base-mean/conditional differences; facts versus model estimates versus conditional assumptions; and missing likelihood evidence. Attribute actual changed scenarios/candidates/selection or explicitly no effect. Cover Expected and Contrarian shared risk together. Existing per-player tables, watchlists and scenario names alone do not provide this.

Use a versioned artifact and existing report/UI surfaces; no need for a new service, model or migration unless durable request storage cannot use the existing operational job system. Restrict initial implementation to these consumer/producer interfaces and focused regression fixtures, rather than modifying the large optimizer’s objectives.

## Acceptance and improvement standard

1. Run narrow unit/API tests for status resolution and packet/condition semantics with isolated fixtures. Preserve legacy packet outputs and unrelated projection fields. Include invariants for no future evidence, no name-only join, no user-created vacancy, conserved physical opportunities, no double counting, and explicit infeasibility/underfill.
2. Run a frozen end-to-end fixture through the real Prepare → optimizer binding → generation → saved-report logic. Show an evidence-supported role change updates the dependency digest, produces a new published/checked packet, and reaches its intended scenario/candidate/report. Show an unsupported injury updates facts but produces no forced role/mean change. Repeating the same semantic inputs must reuse work. Material changes must invalidate incompatible artifacts.
3. With the installed local API/worker aligned and only one operational job active, verify the same public browser Prepare → Run Optimizer → reopen saved result, current saved settings, saved-run CSV response and displayed explanation. A private enumeration or report alone is not operational acceptance. Preserve previous runs and entries. The new FanDuel file is a natural source-precedence case after validated ingestion, not an excuse to bypass Prepare.
4. Factual correctness and reliable automatic propagation are immediate meaningful improvements even if selected rosters remain identical. Different rosters, more candidates, a better narrative or one winning slate are not selector improvement evidence.
5. For scoring/selection changes, freeze comparisons across representative chronological weeks, including current known-failure fixtures and unseen future receipts. Separate candidate-generation experiments from same-pool selector comparisons. Record code/policy version, source availability proof, seed, constraints, variant versus distinct roster count and solver status. Preserve baseline/highest-mean controls. Compare opportunity/FP calibration and whole-lineup outcomes with slate-level uncertainty; do not chase previously inspected winners.
6. Keep `team_window_v2`, count-model alternatives, joint-opportunity and research selectors unpromoted until their own football/accounting and empirical gates pass. Existing W5 opportunity improvements with worse FP error are contradictory evidence, not permission to activate. Activation is an explicit versioned choice with the old configuration retained for rollback; factual parser/resolver correctness does not authorize a new projection policy.

Only this new review file was written. A bounded read-only artifact assertion verified exact neutral-scenario input moment parity for all 15 legal players, the single-world/candidate counts, and the absence of the optional authored football blocks. Application tests and browser validation were intentionally not run during this design handoff. The separate FanDuel ingest and any subsequent code/runtime changes require their own receipt and validation.
