# Football Analyst construction input

An imported `wones_football_analyst_v1` packet can now supply typed construction opinions to normal lineup generation. The input is optional; clearing the selected packet runs the existing baseline workflow. Opinion strength never becomes a fantasy-point bonus, ownership adjustment, forecast, or probability.

Import the JSON through the Optimizer Analyst control or `POST /api/optimizer/analyst-packets` with `{"packet": {...}}`. The response contains `analyst_packet_sha256`. Supply that hash in optimizer `params`, with optional `analyst_candidates_per_thesis` (1–10, default 2). Packets are validated and stored immutably under `artifacts/football_analyst_packets/<sha256>.json`. Reimporting identical content returns the same identity. The source packet retains its analysis/freeze time; a generation model binds the packet hash to its exact prepared inputs and current decision time. A newer opinion is not misrepresented as information available at an older projection cutoff.

Supported `construction_implications` types and exact role keys are:

| Type | Roles | Construction |
|---|---|---|
| `player_emphasis` | `PLAYER` | Include all explicitly linked canonical players |
| `qb_receiver_bringback` | `QB`, `RECEIVER`, `BRINGBACK` | One QB, same-team WR/TE and opposing RB/WR/TE |
| `rb_dst_scenario` | `RB`, `DST` | Same-team RB and defense |
| `diversify_away_from_game` | `AVOID` | Generate elsewhere, excluding that scoped game |
| `explicit_roles` | Showdown `CPT`/`FLEX`; Classic `SELECTED` | Require the declared canonical identities in those roles |

The action remains `shadow_comparison_only` in the version-1 source contract: this means construction-only influence without transforming subjective judgment into model truth. The normal consumer now includes those generated alternatives in the existing candidate/selection workflow. It records `mode=ANALYST_CONSTRUCTION` so this is not mislabeled as an offline shadow run. Conditions in prose describe the hypothetical branch; they are not executable rules and do not assert game-day clearance.

Each thesis is generated independently under the existing legal model, injury/player eligibility, Captain shortlist, user locks/restrictions and exposure constraints. Unsupported types, expired/future-sourced opinions, wrong games/formats, unresolved/ineligible canonical identities and infeasible combinations retain explicit reasons. Missing workload measurements alone do not reject a scoped subjective opinion. Names are display fields; joins use canonical IDs and Showdown Captain identity.

For Showdown single-entry/small-max and five-entry portfolio generation, additional candidates merge by canonical roster plus Captain before the existing selector. The five-entry portfolio keeps its existing joint 95% mean/P90 screen and player/Captain caps; screened rosters remain diagnostic, and infeasible requested sizes are not filled through silent relaxation. Single-entry uses its existing selector, which does not apply that separate 95% portfolio screen. An empty quality-screen list means not separately evaluated.

Classic Small-field merges generated alternatives before its existing quality and portfolio selection. Classic Large-GPP evaluates per-thesis alternatives at each sequential generation step against the exact same remaining exposure, stack-template, overlap, game-cap and minimum/lock model. Its unrestricted baseline optimum normally scores at least as well as constrained thesis alternatives. The audit records this result honestly; the integration does not force a lower-scoring opinion lineup or claim a joint portfolio optimum. This creates usable, scored alternatives without a scoring-policy overhaul.

Inspect `strategy_runtime.football_analyst` for requested/generated/selected counts, per-thesis reasons, model/input hashes, canonical rosters and selector outcomes. Selected roster metadata includes `analyst_packet_sha256` and many-to-many `analyst_thesis_ids`; an existing baseline roster can also satisfy a thesis, so attribution does not establish a unique generation origin.

## Reproducible local tests

The current real Thursday SEA–DEN read-only source capture and normal offline pipeline test are in `research/analyst_shadow_lineups_20261013/`. This test uses the actual prepared production solver and selectors against exported inputs with in-memory checkpoints; it makes no live optimizer writes or contest submissions. It remains an incomplete-evidence preview, not a claim that the app's live readiness gate has passed.

```sh
PYTHONPATH=. .venv/bin/python scripts/run_analyst_normal_offline.py \
  --source research/analyst_shadow_lineups_20261013/real_capture_v4/source.json \
  --packet research/pregame_ai_packet_20261013/packet.json \
  --strategy showdown_gpp_portfolio_v3 --count 5 \
  --output /private/tmp/analyst-normal-thursday-new
```

The separate `scripts/run_analyst_shadow.py` command remains available for frozen numeric-model comparisons. Synthetic Classic/Showdown fixtures demonstrate all supported construction types without pretending to be Sunday NFL research. A real Sunday generation still requires the actual current salary/projection slate; Thursday evidence is never applied to Sunday Main.


## Live activation on October 13, 2026

The local API and durable worker now serve the normal Analyst import/generation path. Fresh Thursday preparation `42bfc75a-570e-4fd7-8880-33887c2cea6c` produced verified projection `563946a2-32b6-467e-a2e9-2c3ad7569927`. Actual live baseline and Analyst jobs completed and persisted without a readiness override; the final Analyst run is `6b2f7acd-dec5-4fcf-9cd8-6508d2a256ba`.

See [the live lineup review](../../research/analyst_live_activation_20261013/LINEUP_REVIEW.md) for all Captain/FLEX names, salaries, means, saved lineup IDs, constraints and source/entry-readiness distinctions. Four generated Analyst candidates pass the existing 95% screen; three selected rosters overlap their theses. Baseline and final Analyst retain the same 59 scenario variants and selected roster set. A completed intermediate run that collapsed variants remains preserved and is explicitly superseded in that review.

Generation is READY from current consumed sources. Entry clearance remains DEVELOPMENT_PREVIEW: final game-day availability, native draft-group confirmation and publication/assignment checks are separate. Four of five requested lineups fit the existing exposure constraints. Caps use five requested lineups; realized exposure in the achieved four can exceed the nominal percentages, and the existing underfill warnings remain visible.

The Analyst summary now appears for Classic as well as Showdown. The current Sunday Main packet has ten scoped salary games, no completed full research reviews and one preliminary KC opinion; it is partial coverage. Thursday opinions never become Sunday constraints. Sunday remains the primary ongoing research target; complete the game checklist and produce selective cross-slate typed opinions with factual gaps disclosed before running a real Sunday generation.


A separate post-run public DraftKings verification uniquely matched native Showdown group `154947` to all 112 imported native Captain/FLEX IDs, teams, positions and salaries. None of its 16 unavailable designations conflicts with generation eligibility or selected rosters. This later read-only check is retained separately; it does not backdate source availability or modify the original salary import. The saved entry assessment's missing native-group metadata remains honest, while future salary imports can carry the verified group ID.


## Explicit merged Analyst + math strategy

The Analyst controls now offer **Original construction comparison** (default, existing behavior) and **Merged Analyst + math scenarios**. The chosen `analyst_strategy` is persisted in optimizer params and remembered with the selected packet by slate context. Clearing the packet runs the original optimizer. A merged request requires an imported packet with `scenario_assumptions.contract_id = analyst_scenarios_v1`; legacy packets retain their original interpretation.

Select a GPP strategy before using the merged option; cash objectives are rejected explicitly. The merged branch captures the complete prepared legal solver model, replaces its objective before any scenario candidate generation, and selects a portfolio globally across all declared coherent outcomes. Each scenario may contain assumptions for several Sunday Main games. Captain/Showdown uses canonical CPT/FLEX roles and the 1.5 salary/point multiplier. Legacy low-opportunity candidate pruning is bypassed, while current role/availability eligibility still applies. All eligible Captains that pass user preferences participate; the original top-four P90 shortlist remains intact for the original strategies.

**There is no 95% mean/P90 quality screen, baseline objective approval or baseline veto anywhere in merged generation or selection.** The same captured model is solved once with its original objective solely to save a comparison roster. That comparison does not become a candidate or affect scenario selection. Base projections, ownership and football context remain unchanged in output rosters. The conditional values live only in the saved scenario report.

### Packet assumptions

Keep the existing v1 packet, hypothesis/source clocks, canonical linkage and narrative evidence. Add an optional block such as this sensitivity example; use actual canonical references and game IDs from the packet:

```json
{
  "scenario_assumptions": {
    "contract_id": "analyst_scenarios_v1",
    "scenarios": [{
      "scenario_id": "passing_concentrated",
      "label": "Conditional concentrated passing outcome",
      "hypothesis_ids": ["existing-hypothesis-id"],
      "assumptions": [{
        "kind": "passing_volume",
        "game_id": "existing-game-id",
        "team": "AAA",
        "factor": 1.2,
        "elasticity": 0.5
      }]
    }]
  }
}
```

These numbers are declared sensitivity parameters, not factual football forecasts or calibrated probabilities. A packet may contain 1–12 scenarios, each with 1–24 assumptions and a descriptive label. Each assumption links to a known game/team and a hypothesis for that game. Every assumption requires a finite `elasticity` between 0 and 1. Extra assumption fields, scenario probabilities and fantasy bonuses are rejected.

Supported types:

| Kind | Parameters | Mathematical effect |
| --- | --- | --- |
| `passing_volume` | `factor` from 0.5–1.5 | Common opportunity ratio for the team's QB, RB, WR and TE, linking their conditional response. Elasticity explicitly controls how much of total fantasy production responds to passing volume. |
| `rushing_volume` | `factor` from 0.5–1.5 | Common opportunity ratio for the team's RB and QB. |
| `target_concentration` | `player_master_ids`, `share_delta` from −0.15–0.15 | Move the stated fraction of the measured team target total into/out of the canonical target group; proportionally redistribute the remainder. Conserves the eligible measured skill-player target total. |
| `workload_transfer` | `workload` (`targets` or `carries`), `from_player_master_id`, `to_player_master_id`, `fraction` from 0–0.5 | Transfer the stated fraction of the donor's baseline opportunities to the receiver, conserving the specified workload. Does not change eligibility or assert an injury occurred. |

Concentration and transfers require complete measured or explicitly attributed proxy workload for eligible team skill players. The engine prefers existing explicit pregame inputs, measured historical means, then existing allocated proxies, recording the exact group and field. Missing coverage cannot become zero. Positive receiver workload and available redistribution mass are required. Opportunity ratios and the combined fantasy response must remain within 0–2; infeasible or contradictory parameters fail explicitly. Workload clocks after the decision are rejected, while missing clocks remain disclosed as unverified chronology.

For each player, conditional mean equals `base_mean × product(1 + elasticity × (opportunity_ratio − 1))`. Conditional P90 equals conditional mean plus the nonnegative baseline `P90 − mean` spread multiplied by the square root of that response. This is an auditable Poisson-style uncertainty sensitivity proxy, not a fitted scoring-efficiency model, estimated causal injury effect, or simulated joint fantasy distribution. Relationships are represented through shared team volume and conserved opportunity redistribution; the implementation does not claim calibrated pairwise covariance.

Candidate generation maximizes conditional mean plus `0.35 × conditional P90 spread`. The 0.35 coefficient is a versioned research design choice. `analyst_candidates_per_thesis` retains its existing request name and means candidates per declared scenario on this branch (1–10). CBC uses fixed random seeds of 7. The report saves the full frozen legal model, packet hash, scenario moments and lineage, distinct canonical candidate rosters, generation solver statuses, scenario scores and selected roster reasons.

The explicit compatibility mode `analyst_portfolio_mode=CONDITIONAL_COVERAGE` (and current Showdown branch) first maximizes the feasible requested count, then the sum of best-selected-roster normalized upside coverage for each scenario plus average conditional upside. Scenarios have equal design weights; these are **uncalibrated**, and repeated alternative outcomes are not independent probability events. Canonical roster dedup preserves all generating scenario IDs. Exposure caps, explicit per-player minimums/maxima, elevated-risk limits, Captain/core/QB/punt caps, locks, uniqueness, team/game limits and Classic primary-game caps remain hard constraints. Constraints are never relaxed. Underfill/infeasibility and requested/achieved sizes are explicit; a small generated pool can underfill even if an undiscovered legal portfolio exists.

The normal source/identity/availability preparation gates and cutoff proof still run before this branch. Partial Analyst evidence may support explicitly labeled hypotheses, but selecting this strategy cannot override missing required live projection/eligibility evidence. This work does not add a new ingestion system or claim live Sunday Main readiness.

### Saved verification examples

Run `PYTHONPATH=. .venv/bin/python -m scripts.run_merged_analyst_fixture --output <fresh-directory>`. The [saved synthetic Sunday Main and Captain examples](../../research/merged_analyst_scenarios_20261013/fixed_seed/README.md) include two opposing joint scenarios, unchanged base projections, frozen legal-model comparison and selected rosters. Classic covers three games; Showdown preserves Captain identity. These are research fixtures with fictitious teams/players, not NFL analysis or historical performance evidence. Targeted tests include selection of a below-95%-mean-and-P90 candidate, deterministic replay, both formats, legal rosters, locked/excluded identities, finite bounds, conservation, chronology and original-path regression.

## Captain-specific Analyst and supporting FLEX

An imported packet with `captain_analysis.contract_id = captain_analysis_v1` activates Captain-specific analysis when **Merged Analyst + math scenarios** is selected for Showdown. The import/read metadata exposes `captain_analysis_contract`, and the Analyst control identifies its activation. Original construction comparison, legacy merged packets and Classic retain their existing behavior. This contract adds no new Captain shortlist expansion: it consumes the shortlist in the captured prepared legal model, or the explicitly locked Captain within that shortlist. The already selectable merged strategy's all-eligible Captain policy remains its existing policy.

For every current Captain, the engine asks what shared passing, concentrated receiving or rushing completion could support a high-end outcome, then fixes that canonical player in CPT while optimizing the five supporting FLEX slots. A QB's shared passing path changes the available receivers' conditional opportunities; a receiver's concentration path also links to the team QB and redistributes teammates' measured targets when complete positive measurements exist. RB paths emphasize rushing completion and the passing/run opportunity cost. Missing concentration measurements remain a disclosed limitation, with shared passing sensitivity only. K/DST and explicitly unsupported mechanisms remain `unmodeled_scoring_path`; the engine does not invent their high-end scoring cause or assert every eligible Captain is justified.

The opponent assessment distinguishes `competitive_scoring`, `trailing_productive_passing`, `drive_stall_runout`, and `unknown`. These are qualitative judgments, not probabilities. A required competitive story alone is never evidence of competitive ability. Supported assessments require separately reviewed quarterback, offense, opposing defense, availability/role, and pace/drive evidence, with verified source references, canonical QB/role identities and the packet's existing source clocks. Supporting evidence, contrary evidence, unknowns, known Showdown hypothesis IDs, expiry and at least one distinct alternative capability are required. A missing opponent assessment stays unknown and retains all three competing sensitivity branches.

The recurring Football Analyst should author this block from its existing game research, without requesting a gut verdict from the user. Research the current QB and supporting offense, its opponent's defense, availability/roles and sustainable pace/drive effectiveness; describe evidence for scoring competitiveness separately from trailing passing productivity. Attach source capture IDs/clocks and canonical player IDs. Record disconfirmation and recheck triggers in linked hypotheses. Use `unknown` when categories are unavailable, preserve at least one alternative, and optionally assess individual Captains as `supported`, `unknown` or `unsupported`. Reimport updated evidence as a new packet; existing immutable packets retain their provenance. No external LLM dependency, automatic source fabrication or new scheduler is introduced. Future team/game projection evidence can be referenced in these same source/evidence dimensions; the current contract does not manufacture an independent game probability.

The minimal opt-in block is:

```json
{"captain_analysis":{"contract_id":"captain_analysis_v1","opponents":[],"captains":[]}}
```

This explicitly leaves all opponent and Captain-specific research unknown. Add opponent entries under `opponents` using this shape (replace illustrative identifiers with actual packet references):

```json
{
  "game_id": "packet-game-id", "team": "OPP",
  "capability": "competitive_scoring",
  "alternative_capabilities": ["drive_stall_runout"],
  "hypothesis_ids": ["known-showdown-hypothesis"],
  "expires_at": "2026-10-16T00:15:00Z",
  "supporting_evidence": ["Sourced scoring-capability evidence"],
  "contrary_evidence": ["Sourced reason the offense may stall"],
  "unknowns": ["Unresolved availability or matchup evidence"],
  "evidence": {
    "quarterback": {"status":"reviewed","summary":"Sourced QB assessment","source_ids":["capture-id"],"player_master_ids":["canonical-opponent-qb-uuid"]},
    "offense": {"status":"reviewed","summary":"Sourced offense assessment","source_ids":["capture-id"]},
    "opposing_defense": {"status":"reviewed","summary":"Sourced defense assessment","source_ids":["capture-id"]},
    "availability_role": {"status":"reviewed","summary":"Sourced availability and role assessment","source_ids":["capture-id"],"player_master_ids":["canonical-role-player-uuid"]},
    "pace_drives": {"status":"reviewed","summary":"Sourced drive/pace/effectiveness assessment","source_ids":["capture-id"]}
  }
}
```

`unknown` entries may use `unavailable` evidence categories with explicit summaries. Optional `captains` entries use `player_master_id`, `mechanism_status`, `high_end_path`, and the same evidence/narrative/hypothesis/expiry fields. These assessments cannot alter eligibility or user preferences. Their high-end path is a conditional explanation; likelihood remains unknown. Unsupported mechanisms use neutral/unmodeled Captain completion, not a fabricated scoring story.

The versioned design sensitivities are fixed and disclosed: opponent passing/rushing factors are 1.15/1.05 for competitive scoring, 1.25/0.75 for trailing productive passing, and 0.65/0.75 for stalled drives. Captain-team passing/rushing factors are 1.15/0.95, 1.05/1.15 and 0.85/1.25 respectively; passing or rushing Captain completion uses at least 1.20 for its applicable channel. Elasticity is 0.60; measured receiver concentration moves 0.08 of team targets, conserving their total. These numbers are analyst sensitivity design parameters, **not fitted team projections, forecasts, causal estimates or calibrated probabilities**. They replace this game's volume channels while retaining explicitly declared concentration/transfers, whose bounds and conservation checks still apply. Duplicate resulting branches merge their source-scenario lineage rather than gain extra coverage weight. Unknown and unsupported Captain mechanisms remain explicit.

Every generated scenario includes canonical Captain identity, capability branch, source-scenario/hypothesis linkage, moments and workload lineage. Generation reports solver status for each Captain/branch; expensive or unsupported salary/role combinations can produce low conditional FLEX scores or be infeasible. A roster with a different Captain receives zero coverage for that Captain's scenario. Existing global portfolio coverage and conditional scores determine allocation, retaining hard locks/exposures/legality and explicit underfill; no preference is changed. Alternatives have equal design weights, including disconfirming paths. No automatic opponent QB, receiver or skill-position bringback is imposed; DraftKings' both-team roster requirement and existing user rules still apply.

Saved `strategy_runtime.football_analyst.captain_analysis` includes every assessed Captain's evidence, unknowns, mechanism, scenario IDs, original fixed-Captain FLEX comparison, generated/selected counts and infeasibility. Candidates record actual added/removed canonical FLEX identities relative to that comparison. CPT output metadata preserves `analyst_captain_assessment` and `analyst_captain_flex_comparison`; normal status/results expose the complete report, and the UI displays the per-Captain assessment summary. Base projection fields are unchanged and baseline comparison never vetoes a scenario.

Run `PYTHONPATH=. .venv/bin/python -m scripts.run_captain_analyst_fixture --output <fresh-directory>` for fictitious competitive, trailing-passing and stalled-drive end-to-end examples. Add `--real-source research/analyst_shadow_lineups_20261013/real_capture_v4/source.json` to demonstrate the dated SEA–DEN frozen-input pipeline with capability still unknown. [Saved verification](../../research/captain_analyst_20261013/verification/README.md) labels the synthetic evidence and later reconstructed real preview independently; it does not certify current live preparation, outcome validation or entry readiness. Existing old packets and saved production runs are unchanged. Activating this feature for an actual slate requires importing a packet with this block and selecting the merged strategy.

## Explicit preliminary Sunday Main comparisons

`POST /api/optimizer/preliminary/snapshots` accepts a finished Classic `preparation_job_id` and the typed `injury_policy: exclude_current_questionable`. It requires freshly verified salary, market, projection and ownership evidence, original artifact/lineage checks and prelock timing. It can retain the specific normal blockers for unpublished official injury coverage and missing current practice/usage of questionable players. Other identity, market, projection or role blockers remain rejected. The source ERROR/NOT_READY assessments remain unchanged.

The server saves an immutable `preliminary_optimizer_snapshot_v1` ledger artifact with the exact projection/ownership/source hashes, full source pool, original readiness failures and a separately hashed injury-assumption manifest. Questionable unresolved players are excluded; no player is declared healthy or newly assumed available. Other players retain sourced roster/role facts and unchanged base projections, explicitly without a game-day dressing or injury clearance claim.

`POST /api/optimizer/preliminary/jobs` accepts `snapshot_sha256` and an ordinary nested `optimizer` request, currently restricted to `classic_large_gpp_v1`, Classic GPP and `exclude_questionable: true`. Both `CONSTRUCTION` and `MERGED_SCENARIOS` consume the same frozen pool. Availability projection overrides, alternate projection/ownership IDs, conflicting locks and ordinary prepared-input readiness claims are rejected. The worker uses the existing internal research solver capability only through this deliberately scoped handler; the normal optimizer endpoints still require READY preparation.

Saved preliminary runs remain `PRELIMINARY_RESEARCH`, retain normal readiness failures, and force `entry_ready: false` on every saved lineup player and final entry assessment. The app displays **Preliminary research · not entry cleared**. Reassessing a saved preliminary run cannot upgrade its classification, and contest CSV download is blocked. A subsequent normal prepared run is a separate record; the historical preliminary snapshot cannot be silently promoted.

For the first Week 6 Sunday Main comparison, normal preparation produced fresh projections and ownership but lacked an applicable official Week 6 injury report and current practice evidence for 25 material questionable players. Both initial preliminary attempts preserved a separate season-rank prerequisite failure (Week 5 snap coverage missing). The matched reruns use an explicit shared **No restriction** setting for season-average ranks, with five lineups and the remaining shared controls. Those changed research settings do not rewrite a saved user preference or normal optimizer default. See [the actual preliminary comparison artifacts](../../research/sunday_main_merged_comparison_20261013/).

## Fitted team/game outlook (optional)

An optional `team_game_outlook.contract_id = team_game_outlook_v1` embeds an immutable saved outlook in a new Analyst packet. Packet import validates its hash, canonical game/team scope, kickoff, source receipt and generation clocks, fitted/calibration cutoff lineage, finite probabilities and feasible opportunity budgets. Native schedule IDs can bind to packet game IDs only through an exact season/week, canonical team pair and kickoff match. Original packet and saved outlook remain independently identified; legacy packets and construction strategy are unchanged.

`team_game_outlook.py` provides a modest fitted Ridge model with train-only preprocessing, prior completed-game offense/opponent history and paired game residual draws. It saves team score, total, home margin, plays, offensive possessions, target/carry budgets, win/loss/tie estimates and lead/trail/competitive scripts. Ties are separate; the explicitly labeled win-half-tie estimate adds half the tie probability. Scores include defensive/special-teams scoring. Possessions count offensive fixed drives represented by scrimmage plays, and carries include QB/kneel plays. Those definitions differ from DFS skill-player-only opportunity. No market or injury adjustment is added to player means.

Capabilities are descriptive proxy events, with documented precedence: competitive scoring (both teams at least20 points, margin within14), productive trailing passing (else trailing by more than7, at least14 points and30 identified targets), stalled drives (else below14 points and1.4 points/possession), then other. They do not establish injury clearance, QB certainty or that a team needing to score can score. Conditional team budgets retain targets+carries no greater than plays. Canonical historical player shares allocate only measured roles; missing measurements and absent eligible players leave explicit unallocated budget, preserving measured zeros.

Merged Classic reports attach shared outlook context and conditional budget audits. Optional `team_game_branch` scenarios use declared budget sensitivities. Captain conditioning can use both teams' conditional volumes from the **same opponent branch draw set**, replacing fixed numerical volume responses only when both fitted ratios fall within the existing0.5–1.5 contract. Missing, sparse or extreme branches explicitly fall back to the prior design. Captain mechanism/concentration and legal FLEX solving remain separate assumptions. Portfolio weights remain uncalibrated design weights: an empirical game-event probability is not a Captain ceiling or lineup-win probability. Saved normal reports retain the full embedded outlook and scenario provenance; base projections remain unchanged.

The first saved study is `research/team_game_outlook_20261013/`. Sunday2025 evaluation covers161 games: score MAE7.70/team versus simple history7.56, plays MAE6.80 and possessions MAE1.24. Win-half-tie Brier is0.222 and empirical80% score interval coverage81.4%; reliability bins reveal material gaps, so probabilities remain empirical estimates with **unproven forward calibration**. Historical revised imports and previously inspected outcomes prevent a contemporaneous or pristine-holdout claim. W4/W5 are diagnostics; future W6 onward should be evaluated from saved pregame outputs. Offline real Sunday and dated SEA–DEN previews are preliminary, do not alter live jobs, and do not clear normal entry gates.

The first actual preliminary comparison completed five lineups in each arm: [saved review and machine evidence](../../research/sunday_main_merged_comparison_20261013/README.md). One canonical roster overlapped; the merged portfolio changed QB allocation while retaining the common Rams core. Missing finite model forecasts are separately audited before scenario calculation, including fresh salary rows for non-fantasy long-snapping roles; no unavailable forecast becomes a measured zero.


## Classic scenario-first allocation

Classic MERGED_SCENARIOS defaults to `analyst_portfolio_mode=SCENARIO_FIRST`. CONSTRUCTION remains unchanged; `CONDITIONAL_COVERAGE` reproduces the previous merged generation/coverage branch. Before any roster solve, the planner freezes `scenario_allocation_plan_v1` and persists it in the durable job checkpoint, then retains the same planning snapshot/hash in the saved report.

Single-game sourced volume ideas are ranked by projected legal role capability, measured opportunity coverage, source support and ordinal analyst preference. A declared strongest alternative can create a contrary passing/run branch with reduced credibility. Weak/unmeasured branches are rejected; composite multigame sensitivities do not masquerade as distinct primary construction ideas. Priorities are design scores, not probabilities. Repeat game/idea penalties and new-script credit allocate slots before player optimization; every repeated slot records its next credible alternative and justification. Feasibility feedback records all attempts and uses the same overlap-adjusted priority for alternatives. No generic fallback or constraint relaxation occurs.

Passing ideas require their eligible primary QB plus supported receiver; run ideas require their primary RB, exclude their primary QB and limit primary receivers to one. Opponent receivers are required only with explicit two-sided passing evidence plus projected QB and observed receiver capability. Every other team defaults to at most two offensive players per roster. Same-team receiving pairs and canonical triples default to at most ceil(0.6 × requested size) appearances, with explicit all-player locks taking priority. Saved reports independently audit construction counts, shared pairs/triples, heavy offensive team counts and actual idea assignments. Different scenario names do not constitute diversity.

Typed `scenario_allocation_controls` exposes bounded `opportunity_shift` (0.12), `secondary_offense_limit` (2), `receiving_core_max_fraction`/`shared_triple_max_fraction` (0.6), `game_repeat_penalty` (0.65), `idea_repeat_penalty` (0.85), `new_script_credit` (0.18), `minimum_credibility` (0.35), and `passing_receivers` (1). These affect only the new path. The normalized 100-unit skill opportunity budget moves 12 units between targets and carries, conserving their sum. Complete measured eligible skill workload supplies the initial split; incomplete coverage uses a disclosed 55/45 design prior. This is an opportunity sensitivity budget, not a forecast of 100 NFL plays or attempts. Means use a bounded 0.7 response elasticity and conditional spread uses its square root; actual persisted player projections remain base truth. Sequential legal construction can underfill even when an undiscovered global portfolio exists.

The saved three-way Sunday research comparison preserves old/prior merged runs and reuses the exact frozen preliminary snapshot: [scenario-first review](../../research/scenario_first_sunday_main_20261014/LINEUP_COMPARISON.md). Final entry readiness remains blocked; this does not clear missing injury evidence or enable contest CSV export.

## Outlier discovery before scenarios

`python -m scripts.build_analyst_discovery_scan --packet <immutable-packet> --snapshot <preliminary-snapshot> --output <new-scan.json>` scans every confirmed Classic game and every canonical frozen player row, including low projections and unavailable players. Candidate screens include share/participation changes, role flags and opportunity/salary disagreement. The saved scan is deterministic and immutable; candidates are **statistical outliers**, never automatic favorable matchup facts or projection bonuses. Game capability and missing defender alignment/protection evidence are explicit. Present lineage/context fields do not prove direct fitted-feature inclusion, calibration or causal impact.

A research-agent workflow investigates all games using the scan, immutable source captures and canonical identity. It contrasts current projection/context inputs, mechanism, opponent keep-pace/protection path, counterevidence and unknowns. It returns optional `discovery.contract_id=analyst_discovery_v1`, the immutable `scan_snapshot_sha256`, all confirmed `scanned_game_ids`, and typed findings. Findings retain `finding_id`, game/canonical players, source IDs and `as_of`; `classification` separates statistical outliers from hypothesized model blindspots. `status` is supported_provisional/watchlist/rejected. Supported provisional findings require verified pre-decision sources, finite editorial `evidence_strength`, partial/unmodeled accounting with distinct `delta_fields`, mechanism/counterevidence/unknowns and a supported bounded action. Source capture clocks must not be backdated to an earlier projection snapshot; later research evidence is explicitly a different information state.

Actions reference a credible `idea_id`, one or two `required_player_ids`, and optional `opportunity_share_transfer` (`channel: targets|carries`, recipient ID and share). Unsupported efficiency/coverage actions are rejected rather than silently applied; preserve them as no-action research watchlists. `analyst_discovery_controls` defaults to one reserved slot, maximum20% of requested portfolio, minimum strength0.6 and maximum opportunity transfer0.08. Reservation occurs before roster solves, after source/model-delta/eligibility checks. Watchlists, already-accounted signals and unknown model deltas receive no action. `analyst_discovery_enabled=false` is an explicit reproducible comparison treatment using the same packet and inputs.

Target transfer conserves attributed eligible skill target shares; carry transfer conserves eligible RB carry shares. Donor reductions are proportional, recipient must have positive measured/attributed baseline budget, and ratios stay0.5–2. Fantasy responses use declared0.7 elasticity weighted by the player's projected target/carry component mix; base projections remain unchanged. This is a conditional opportunity sensitivity, not a measured new forecast. A player's exclusion by user Q policy is never evidence that he is actually absent, and excluded-player workload is not silently donated. Locks, salary/roles/exclusions/exposures and feasibility remain hard constraints. A reserved finding that cannot construct is recorded as infeasible/displaced, with fallback attempts and no relaxation.

Reports expose all scanned games/candidates and investigated supported/watchlist/rejected findings, source/model delta, reserved idea/slot, actual canonical roster digest, scenario IDs, binding controls and actual influence. The job checkpoint freezes the discovery-informed plan before generation. Packet import is idempotent, and saved results/UI retain its chain. Existing packets without discovery screen without action; Showdown/Captain and original CONSTRUCTION behavior remain unchanged. Scenario packets now permit up to24 bounded scenarios so new sourced branches need not overwrite frozen original assumptions.

The actual Week6 study uses a new official Oct13 capture after the original projection snapshot: conditional NE carry concentration if Henderson is absent and Stevenson retains his role. Missing game-day confirmation stays unknown; the5-point eligible-RB share sensitivity comes from eligible donors, not an assumed Henderson redistribution. Other games remain watchlist when trends/context are already represented or matchup evidence is missing. [Saved discovery study](../../research/analyst_outlier_discovery_20261014/) preserves matched on/off research results; final entry clearance remains blocked.

## Optional bounded blind-spot hunter

Classic scenario-first MERGED_SCENARIOS supports explicit opt-in `analyst_challenger_enabled=true` (checkbox in the Analyst control, persisted with packet selection). It defaults off; CONSTRUCTION, conditional-coverage compatibility mode and Showdown cannot activate it. The first usable implementation requires a complete Classic portfolio of at most20 lineups. Captain-aware canonical roster dedup is tested; Captain search itself is not implemented and an explicit unsupported request is rejected.

After the initial scenario-first candidate pool, `analyst_challenger_v1` audits actual common players, expensive RB groups, central-mean dependence and sourced contrary scripts. It distinguishes a generation gap (no suitable counter roster), selection gap (existing unselected roster can be reused without solving), already-covered state, unsupported counter idea and unavoidable locked dependence. A QB plus receiver or two receivers can represent a passing response; labels/identical names alone do not establish outcome coverage. Already-covered states remain in the reallocation audit so a new challenger cannot silently discard their protection.

Default controls: `max_failure_modes=3` (maximum6), `max_solver_calls=2` (maximum3), `max_seconds=20` (1–60), `max_portfolio_size=20`, `expensive_rb_salary_threshold=6500`, `dependence_fraction=0.8`, `opportunity_shift=0.2`, `minimum_credibility=0.45`, `minimum_coverage_gain=0.02`, `counter_world_weight=0.25`. All are bounded design choices, not calibrated event probabilities. Targeted searches copy the same frozen legal model and use fixed CBC seeds7. Opposite-script normalized skill budgets conserve targets plus carries. The shared core is tested realizing its existing saved modeledP10 endpoint; that explicit downside stress is a point scenario, not a newly fitted conditional distribution, absence/injury claim or guaranteed percentile event.

A challenger must be role/salary legal, canonically novel and improve its own credible stress-condition best-roster coverage by the configured minimum. There is no95%mean/P90baseline veto. It is not forced if unsupported, infeasible, duplicate or unhelpful. A bounded portfolio comparison assesses the initial pool plus at most3 new candidates across the same conditional metrics, retains all hard exposure/minimum/uniqueness/primary-game/shared-core controls and feasible discovery reservations, and records an explicit revised allocation only when coverage improves. Initial allocation, pool variants, canonical roster identities, selected/discarded rosters, source/counterevidence, central mean cost and remaining dependence are retained separately. Search/selector budget exhaustion stays explicit.

[The actual saved Sunday comparison](../../research/analyst_blindspot_hunter_20261014/LINEUP_COMPARISON.md) uses one targeted solve to cover a missing Puka-downside/Ramsrun state. Kyren-air response was already selected, so no regeneration; the unsupported Jaylen counter remains a disclosed gap. One new candidate expands the pool5→6 and replaces the New Orleans passing slot, an explicit opportunity cost. The discovery-conditioned Stevenson slot stays selected. Final entry readiness remainsfalse; no submission/export occurs. Scores/coverage weights do not establish future profit or calibrated joint lineup outcomes.

## Live experimental build and cheaper-teammate alternatives

In **Operations → Optimizer → Wones Football Analyst**, choose **Use available experimental Analyst tools**. It selects the latest imported packet for the active season/week/format and explicitly enables Classic scenario-first discovery, downside hunter and cheaper-teammate research. **CONSTRUCTION** remains selectable. For Sunday, use the **Preliminary research** snapshot chooser: it shows the frozen assumptions, excludes current questionable players and keeps `entry_ready=false`. Its research-only season-rank control does not overwrite saved ordinary preferences. A packet tied to a discovery snapshot requires that exact snapshot. Showdown uses normal refreshed preparation and its Captain-specific packet; Classic-only hunter/teammate controls are omitted.

`analyst_teammate_opportunity_v1` scans every packet game for canonical starter/secondary RB pairs. A sourced run-control or receiving-back path, positive measured workload proxy, legal availability/salary and minimum savings are required. Default limits are three pairs/six solves, at most30 seconds of search, minimum$500 savings and a10-percentage-point conserved eligible-back share transfer (maximum15). Each pair fixes the primary or cheaper back under the same game branch and legal model, preserving locks and user controls. It records both full rosters, reinvestment, base-forecast cost, conditional mean/selector-score difference, secondary break-even and counterevidence. Point checks such as Corum10/15 DK points are labeled user what-ifs; they never enter the optimization objective.

Paired alternatives do not automatically replace selected lineups. The saved results table's **Use this cheaper alternative** action stages `{source_optimizer_run_id,pair_id,branch:"cheaper"}` for the next preliminary build. The source must be completed and match the exact packet, projection and full source-row digest. The engine re-solves under current controls and admits one chosen lineup only after full portfolio exposure, uniqueness and discovery-reservation checks. Conflicts fail explicitly without relaxation or generic fallback; a negative opportunity cost remains visible and requires this explicit choice. Base forecasts and final-entry gates remain unchanged.

The active combined Sunday packet also uses saved team/game outlook ratios to tilt the conditional pass/run mix, renormalized to100 skill-opportunity units. This is an unproven model sensitivity, not calibrated lineup probability or automatic base-model promotion. Automatic DST/K screens attach dimension coverage and sourced/watchlist findings for both formats; current missing pressure/protection/drive evidence remains watchlist and adds no invented boost. Existing eligible specialists can still be selected through normal controls and Captain/FLEX construction.

Actual all-feature Sunday source and explicit Ty Johnson apply results are in `research/analyst_teammate_opportunity_20261014/LINEUP_COMPARISON.md`. The earlier frozen precheck used the preceding packet and is preserved separately. **Analyst Reports** presents the human-readable saved studies; Operations contains the build/apply controls.

## Contrarian reports and selected-story construction

`contrarian_analysis_v1` distinguishes a source-supported conditional football hypothesis, an explicit user what-if and a watchlist requiring research. Every finding binds a canonical game/team and existing typed scenario, source clocks, mechanism, conditions, counterevidence and unknowns. A team-points target is permitted only as a bounded user what-if (maximum60), never a calibrated forecast or point bonus. The deterministic scan covers every scoped game and current canonical player pool; existing starter/target evidence alone does not prove protection improvements, opponent competitiveness or an overlooked edge. Football contrarian and low ownership are separate claims.

Choose **Football scenario focus → Only selected football stories**, then select one or more single-game scenarios. `analyst_scenario_focus_mode=SELECTED_ONLY` and `analyst_scenario_focus_ids` persist with the job. Every lineup requires the chosen team QB+receiver for passing or an own RB for running; Showdown additionally requires a relevant Captain from that team. Opponent bringbacks are not automatically required. Classic can fill the other slots from complementary games. Existing salary, identity, availability, locks, exposure and uniqueness controls remain hard. Composite stress worlds and unsupported/watchlist constructions fail explicitly; no generic fallback, unselected hunter/teammate branch or95% approval screen can enter this mode. Mixed portfolio mode and CONSTRUCTION remain available. Explicit user what-ifs are inactive in the mixed default.

Selected stories use the shared conserved100-unit skill-opportunity mix, component-weighted0.7 response and square-root spread sensitivity; optional saved outlook ratios can tilt the mix before renormalization. A Denver40-point what-if is a condition requiring successful drives and finishing efficiency, not a model promise to produce40 points. The current engine does not fit score-target-conditioned touchdowns or calibrated tail probability. Saved focus reports disclose that limit and actual roster compliance.

Captain correction: legal eligibility alone no longer authorizes an automatically invented high-end story. A supported Captain opinion or sourced primary role with positive relevant opportunity permits a provisional sensitivity; missing/secondary/zero-workload roles remain assessed with suppression reasons. An explicit user Captain lock remains a labeled what-if. Every roster is scored under every shared conditional football world; other Captain identities are not assigned zero. Numerically identical worlds count once, preventing self-normalized per-Captain coverage votes from rewarding unsupported cheap Captains. This is a math/evidence correction, not a salary ban or legacy95% gate. The original flawed Thursday result remains saved separately.

Explicit unchecked Classic hunter/teammate choices are serialized as false so automatic preparation defaults cannot silently re-enable them. Unspecified choices remain distinct; selected-only mode omits incompatible branch tools. Saved comparison exposure and Captain-authority tables retain contiguous Markdown rows for the app report reader.
