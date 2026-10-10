# AI Showdown Selection Packet: Phase 1 plan

**Nonbinding review checklist:** the existing frozen packet now includes
`prelock_review_checklist` (`showdown_prelock_review_checklist_v1`). The app's
**Prelock review checklist** action reads the same JSON export endpoint without
running a solve. It shows generated, quality-eligible, finalist and saved-proposal
coverage; generation gaps versus existing quality exclusions; WR/TE Captain/QB
pairings; 3–3/4–2/5–1 counts; salary left; fresh sourced projected ownership;
and canonical physical-player overlap when the saved proposal has exactly two
entries. Missing generation explanations and ownership remain unavailable.
The saved proposal is the optimizer control, not an inferred AI decision.
For an AI-proposed pair, `candidate_details.physical_player_ids` supports a
canonical ID intersection across the full eligible universe. Historical study
notes and account outcomes are excluded from this packet. Existing V2 quality,
finalists, review-universe ordering and production selection are unchanged.

The experimental exporter reads the original completed Showdown candidate archive. It does not solve new lineups or change `showdown_gpp_portfolio_v3`. JSON is the versioned source of truth; Markdown is a rendering for manual ChatGPT review. Manual review uses every distinct V2 quality-eligible roster in the AI Review Universe. The production selector and deterministic 20-finalist set remain controls.

Live slates now require the frozen `showdown_data_readiness_v1` result saved
before candidate generation. Normal live export rejects legacy runs with no
readiness proof, even if their candidate generation succeeded. Packet JSON and
Markdown include `data_readiness`, source clocks and the generation evidence
hash; the finalist audit retains that hash. Archived past-slate packets without
the new contract remain explicitly labeled incomplete/unverified diagnostics.
The internal/CLI `--allow-incomplete-evidence` override never appears in the
ordinary API/UI. Export `ai_requested_entries` (2–5) is independent of archived
`num_lineups`; the app's **AI requested entries** control starts at 2.
See [readiness implementation and actual TB@DAL attempt](../SHOWDOWN_DATA_READINESS_IMPLEMENTATION.md).

## Phased checklist

- [x] Verify saved archive, run metadata, cutoff, and source hashes for both Week 4 runs; document unavailable historical fields. Sunday is post-kickoff and cannot certify a prelock packet.
- [x] Build a pure packet builder with canonical roster IDs, explicit point-in-time field allowlists, stable hashes, and versioned JSON plus manual-selection contracts.
- [x] Add deterministic construction, scenario/reason, risk, and finalist-similarity classification.
- [x] Select about 20 distinct finalists by quality and meaningful scenario coverage, with stable tie breaks and exact inclusion reasons.
- [x] Render a readable Markdown packet and expose Markdown/JSON downloads for completed Showdown runs in the app; add a CLI for frozen reference artifacts.
- [x] Add targeted unit and API tests, including postgame and future-evidence leakage tests; pass the UI build and leave the production selector untouched.
- [x] Generate the replay-safe Week 4 Thursday packet and reject Sunday after its chronology check; then compare frozen finalist rules with actual results in `AI_SHOWDOWN_SELECTION_PACKET_IMPLEMENTATION_REVIEW.md`.
- [x] Update README and release notes, run appropriate checks, and review the final diff without disturbing existing uncommitted changes.
- [x] Export all quality-eligible distinct candidates, compact candidate rows, deterministic family indexes/summaries, and a Markdown AI Review Universe; remove the finalist-only manual-review restriction.
- [ ] Complete the prospective upcoming Thursday test: freeze packet and manual choices before lock, then score them after the slate.

## Design and acceptance

1. Require an original, complete saved candidate pool and valid canonical six-player/CPT signatures. Archive variants stay intact; classification, quality assessment, the review universe and finalists use distinct physical rosters. Reject missing or mismatched essential lineage rather than rebuilding from current data.
2. Require prelock run and source evidence before calling an export replay-safe. Unknown optional fields remain null with an availability reason. Live required inputs must have frozen READY evidence. Only explicit prelock fields may enter the JSON contract. Export timestamp is excluded from the deterministic evidence hash.
3. Scenario tags describe construction, not outcome probabilities. Every tag has rule version and reason codes; unsupported favorite, role, ownership, injury, or game-script facts produce no inferred tag.
4. Finalist policy version, quotas, quality floors, near-duplicate thresholds, and tie breaks are frozen before consulting outcomes. Requested entry count is separate from finalist count (default 20, configurable 15–30). Underfill and uncovered families are reported.
5. JSON contract `ai_showdown_selection_packet_v1` contains run/game/pool/control/finalists/similarity, source and policy hashes, player names and IDs, metrics, construction, tags, risks, inclusion reasons, and `ai_review_universe`. `ai_showdown_manual_selection_v1` records packet hash, selection time, requested size, candidate IDs, model and reasoning fields for later import. Validation accepts eligible universe IDs; archived packets without a universe retain finalist-only validation.
6. Markdown includes the run identity, game and pool overview, AI instructions, a compact universe summary, six family tables, one row per eligible candidate, control finalist blocks, and high-similarity summary. Summed marginal P90 is labeled a ceiling proxy.
7. Tests must cover classification, stable finalist inclusion, serialization, rendering, historical missing data, deliberate injection of postgame/future fields, and no calls to the production solver. Both Week 4 runs are regression fixtures; their known actual results must not affect packet generation.

## Known integration points

- `backend/app/product_services/optimizer_effectiveness.py` already extracts and hashes saved original candidate pools.
- `backend/app/product_services/showdown_portfolio_selection.py` defines physical-roster identity and the existing selector; it is read-only for this task.
- `backend/app/api/product_routes.py` serves completed optimizer results and downloads.
- Saved reference reports are `artifacts/showdown_scenario_selection/reference/sunday-week4.json` and `thursday-week4.json`; their run IDs are `dc21b3ab-c330-487c-bb88-766f9a71f04c` and `ffb8acf8-2e31-414e-81da-417d6d82c584`.

## Finalist policy v2 revision

- [x] Separate football scenarios and construction attributes; define primary/all thesis signatures and deterministic reasons.
- [x] Use saved baseline quotes for descriptive HIGH/MEDIUM/LOW market compatibility. Selected scenario rows can contain hypothetical spreads.
- [x] Replace v1's joint 85% floor with both dimensions at least 80% of maxima and either at least 90%, or selector top three within the safety floor. Expose configurable fractions and exact eligibility reasons.
- [x] Preserve the top three independently by selector, baseline mean, and summed marginal P90. Nominate thesis/captain-side representatives and reserve three slots below the selector's top quarter for structural novelty.
- [x] Expose coverage, rank distributions, selection origins/reasons, and thesis-aware similarity while preserving the packet v1 contract and download/API infrastructure.
- [x] Freeze both Week 4 candidate sets before loading actuals; Sunday remains a labeled retrospective diagnostic because the run was created after kickoff.
- [x] Add a separate immutable-packet audit, complete-field tail comparisons, archived-v1 comparison, and reproducible Markdown/JSON artifacts.
- [ ] Demonstrate improved tail retention and adequate captain-side coverage on a predeclared validation set. Neither known best survives these two regressions; do not count this criterion as complete.
- [x] Replace the finalist-only trial restriction with complete quality-eligible universe review. V2 finalist retention remains a measured control rather than a prerequisite for manual AI review.

## AI Review Universe: Phase 1 extension

`ai_review_universe` uses contract `ai_showdown_review_universe_v1` inside the existing packet v1. The schema permits archived packets without this field. New exports always include it, and its complete contents participate in the frozen evidence hash. Adding it changes the packet hash; an older manual choice remains attached to its original packet. Export requires saved human-readable names for every eligible player rather than silently presenting UUIDs as names.

An entirely empty saved baseline market definition is optional missing context: export keeps favorite, underdog and total null, marks `game.market_unavailable_reason` as `saved_baseline_market_missing`, and uses the existing V2 incomplete-market compatibility reason. It never replaces that absence with current or conditioned selected-row markets. Existing quotes still require an observation timestamp at or before the cutoff. In Recent optimizer runs, export progress, download requests, and failures appear beside the clicked buttons and persist across automatic list refreshes.

- `candidates`: one compact row per distinct roster where the existing `quality_eligibility.eligible` is true. Rows reuse `metrics` and `construction` field names, including original `selector_rank`, distinct-pool `selector_pool_rank`, mean `projection_rank`, `ceiling_proxy_rank`, named captain and side, normalized split, all scenarios/theses/reasons, salary remaining, and risk flags. `flex_player_names` supplies all five FLEX names. Market reasons/basis, quality fractions/reasons, `is_deterministic_finalist`, and nullable `deterministic_finalist_inclusion_origin` complete the row. Incomplete projected total ownership stays null.
- `family_indexes`: maps each group to its complete ordered candidate ID list under `primary_thesis`, `captain_script_combination`, `football_scenario`, `captain_archetype`, `team_split`, and `qb_structure`. Captain-script keys retain captain side; splits retain the V2 notation (`4-2_favorite`, for example). Scenario membership includes every assigned scenario and can overlap.
- `family_summaries`: matching groups expose count, top three navigation IDs, captain-side and market distributions, mean/P90/objective/ownership ranges with available/unavailable counts, finalist count, distinct captain names/splits, and risk-flag counts.
- `summary`: generated distinct, eligible, deterministic-finalist, quality-excluded, and all six family counts. Every family and row uses the existing representative ordering: descending average normalized mean/ceiling, descending best fraction, ascending selector rank, then candidate ID. Top three representatives do not restrict family membership or selection.

Manual review first reasons about the game, identifies relevant football families, examines those candidates, and chooses the requested 2–5 entries from the full universe. The 20 finalists remain reference/control evidence. No new selector, LLM integration, persisted decision-import UI, or broader learning audit is added here. The existing finalist audit remains unchanged and accepts manual choices within its finalist control; universe/AI-considered/entered-result learning is a subsequent step.

Reproduce from the saved sources into a fresh output directory:

```sh
python -m scripts.export_ai_showdown_packet artifacts/showdown_scenario_selection/reference/thursday-week4.json OUTPUT_DIR --season 2026 --week 4 --slate THURSDAY_NIGHT
python -m scripts.export_ai_showdown_packet artifacts/showdown_scenario_selection/reference/sunday-week4.json OUTPUT_DIR --season 2026 --week 4 --slate SUNDAY_NIGHT --retrospective
```

Thursday exports all 93 eligible rosters from 117 distinct generated candidates; Sunday exports all 110 from 110 only through the labeled retrospective diagnostic. Each retains the same 20 V2 finalists. These are coverage checks from saved prelock assessments, not a new result-driven selection policy.

Generated review examples: [Thursday Markdown](../artifacts/ai_showdown_selection_packet/review_universe_v1/thursday/AI_SHOWDOWN_SELECTION_PACKET_THURSDAY_NIGHT_ffb8acf8-2e31-414e-81da-417d6d82c584.md) and [Sunday retrospective Markdown](../artifacts/ai_showdown_selection_packet/review_universe_v1/sunday/AI_SHOWDOWN_SELECTION_PACKET_SUNDAY_NIGHT_dc21b3ab-c330-487c-bb88-766f9a71f04c_RETROSPECTIVE.md), each with companion JSON in the same directory.

The exact algorithm, quality/market/similarity rules, reproduction commands,
packet links and historical measurements are in
[`AI_SHOWDOWN_FINALIST_POLICY_V2_REVIEW.md`](../AI_SHOWDOWN_FINALIST_POLICY_V2_REVIEW.md).
`scripts.audit_ai_showdown_finalists` accepts only an already frozen packet,
matching saved source, and separately supplied canonical actuals. It never
regenerates finalists. Missing scores are unavailable; no zero imputation occurs.
Generated-pool tails include cutoff ties; complete-field tails use conservative
worst tied ranks. Generation and AI/manual regret remain null without their
respective universe benchmark and frozen selection.
