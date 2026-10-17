# Experimental Analyst generation in the app

## Prepare → Optimize

For normal prepared generation, **Prepare slate for optimization** checks the latest published Analyst research against that build's exact scope and fresh player inputs. The preparation receipt records the original and checked versions, research and check clocks, active tools, changed/contradicted findings and missing checks. The app carries the checked packet into **Run Optimizer** automatically; no packet hash entry is required.

An existing explicit packet/strategy or baseline choice remains an override. Selecting a different packet requires preparation with that override. Focus IDs and optional controls survive when still compatible; suppressed or unavailable stories produce a visible error rather than resetting to mixed mode. **Use automatic checked Analyst on next preparation** returns to automatic mode deliberately.

`needs_review` with a checked packet remains usable experimental research, with unknowns shown. No checked packet, a mismatched override or failed metadata load blocks the Analyst request; refreshing research or explicitly choosing baseline are the available next steps. This compatibility check does not perform new semantic research or turn model proxies into observed football facts. Entry readiness stays separate.

For an explicit manual Analyst override, use **Operations → Slate files / lineup generation**, select the season/week/slate and **Classic** format, then open **Wones Football Analyst**. Choose an available imported experimental packet and **Merged Analyst + math scenarios** to use scenario-first allocation. Original construction and **Clear Analyst · run baseline** remain available. Optional blind-spot and cheaper-teammate research controls are separate choices.

## Selected football stories

In **Wones Football Analyst**, refresh available packets and active metadata, select a compatible experimental packet and **Merged Analyst + math scenarios**, then choose **Only selected football stories**. Select supported stories from that packet. An empty selection or an unsupported story blocks generation; there is no generic fallback. **Mixed football portfolio** remains available.

This choice works with ordinary prepared Showdown generation and preliminary Classic generation. Current locks, exclusions, exposure limits and uniqueness requirements still apply. Selected-only mode excludes blind-spot and cheaper-teammate branches that could introduce another story; saved cheaper actions are disabled until you explicitly change focus mode.

After a run finishes or is reopened, its Analyst summary displays the saved focus, scenario IDs, construction requirements and passed/failed/unavailable lineup checks. A Denver 40-point story is an explicit user what-if, not a predicted score or a low-ownership claim. Story compliance verifies construction, not future accuracy or entry clearance.

## Preliminary Classic flow

When official injury/practice or role evidence is incomplete, use **Preliminary Classic research generation**. Its explicit preparation builds fresh research inputs while preserving failed normal readiness.

1. Click **Prepare preliminary research inputs** to refresh markets, build new projections/ownership, and automatically freeze the checked Analyst snapshot with conservative unknown exclusions. You may also choose an existing compatible **Frozen research inputs** snapshot for this slate. Its original projection/ownership IDs and normal-readiness reasons remain visible. A discovery packet must match the snapshot it investigated.
2. Inspect **Immutable injury assumptions and canonical exclusions**. Enable the existing **Exclude questionable players** preference; Q exclusion is not a fact that the player will miss the game.
3. If prior-week stats/snap history is incomplete, explicitly select **No season-average rank restriction for this research run only**. This removes only the rank filters in the submitted research request and records that choice. Saved normal-run settings are unchanged. All other locks, salary floors, exclusions, exposures, uniqueness and roster rules remain binding.
4. Select **Use the displayed preliminary assumptions; keep final entry readiness false**, then **Generate preliminary research lineups**.
5. The durable worker reports progress. Reopen the run through **Recent optimizer runs** if the connection is interrupted. Saved research results display their assumptions and retain CSV export blocking.

If no frozen input exists, use **Prepare preliminary research inputs**. A previously finished Classic preparation with still-verified sources can alternatively be selected under **Freeze a finished preparation as new research inputs**. The server requires saved projection/ownership and source proof; unsupported blockers remain failures. Freezing creates a new assumption receipt, so an older discovery packet must continue using its original snapshot unless separately investigated against the new one. The UI never hardcodes a week, preparation ID, projection or snapshot hash.

The scoped snapshot GET API serves bounded metadata and assumptions, not the player pool or arbitrary paths. Invalid/hash-mutated/symlink-escaped snapshots are rejected. The local ledger scan is capped at fifty files and 128 MiB of aggregate scan work, with a 64 MiB per-snapshot limit for full frozen lineage. Truncation is explicit.

## Cheaper branch into generation

A saved run that includes cheaper-teammate research shows **Cheaper teammate opportunity cost** above the Analyst report. The table retains every screened/rejected pair, salary savings, full-roster base and conditional differences, reasons and possible replacement slots. Expand an evaluated pair for complete legal rosters, break-even secondary points and 10/15-point what-ifs.

**Use cheaper branch with original Analyst inputs** stages an eligible saved pair and selects its original packet with merged strategy. It does not generate a lineup immediately. Return to the preliminary controls, review the original frozen assumptions and submit the next research run. **Clear cheaper branch** removes that staged choice.

The request links `source_optimizer_run_id`, `pair_id` and `branch: cheaper`. The server reruns the pair under the current hard user controls, requires compatible source/packet/snapshot/projection lineage and tests a complete portfolio replacement. An infeasible choice is rejected explicitly without fallback. A negative full-roster cost is allowed only through this deliberate choice; salary savings alone never automatically promote a backup.

Chicago Q/salary exclusions remain visible and cannot be bypassed from the paired table. Captain/Showdown teammate application is outside this Classic workflow. Research assumptions and conditional player scores do not change base projection truth or establish game-day clearance.

## Validation

The targeted snapshot API tests use an isolated ledger; existing preliminary contract tests verify final-entry false and immutable assumptions. UI tests cover scope, Q/readiness guards, request-only rank changes, actual paired-report React rendering, negative-cost deliberate selection and Chicago rejection. TypeScript/Vite build validates app wiring. No browser visual check or contest submission is implied.

## Fresh preliminary preparation with missing availability

In **Preliminary Classic research generation**, click **Prepare preliminary research inputs**. This captures fresh market inputs and builds new projections/ownership for a conservative research pool. Players with unknown or stale availability or role evidence are excluded; their canonical source facts stay unchanged and missing checks remain in the saved normal-readiness report. The preparation freezes a new snapshot and exact checked Analyst packet automatically, without manual packet selection. Review the visible per-player assumption table and explicitly accept it before **Generate preliminary research lineups**. If prior-week history is incomplete, **No season-average rank restriction for this research run only** removes those filters solely from the research request. Other user constraints remain in force.

Saved results retain the snapshot, assumption, source, projection and Analyst compatibility hashes. Reopen them through Recent optimizer runs. Research never establishes final availability or entry clearance and cannot export contest CSVs. Wrong-slate or older preparation status replies cannot replace newer scoped readiness; a Showdown leader-history failure identifies its actual checkbox instead of suggesting a Classic-only rank option.
