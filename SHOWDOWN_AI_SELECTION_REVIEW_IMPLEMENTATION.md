# Showdown AI Selection Review implementation

## 1. Executive summary

Implemented `showdown_ai_selection_review_v1`, a research-only two-entry review integrated into **Operations → Recent optimizer runs → AI Candidate Review**, with prospective tracking under **Research Lab → Showdown research notes**.

The workflow preserves the existing deterministic finalists and complete quality-eligible universe, surfaces ten ceiling outsiders, compares physical-player overlap, offers deterministic lower-overlap alternatives, and saves explicit consideration, reasoning and selection revisions. It runs no AI service, solver or candidate generation. New decisions require frozen READY evidence and a server timestamp before kickoff.

Week 5 Thursday validates 75 eligible candidates, 20 finalists, ten outsiders, Ryan Flournoy-CPT rank 41 surfaced, and five shared players for the observed Dak/Bucky rosters. No historical AI decision was created. The generator and portfolio-selector modules were untouched; concurrent optimizer input-handling changes were preserved and separately identified.

## 2. UI changes and screenshots

The integrated panel contains **AI Candidate Review**, **Captain / Script Coverage**, **Two-Lineup Comparison**, **Alternative Portfolio**, and **Decision Record**. Candidate tables scroll, diagnostics collapse, exact IDs remain visible, and mobile form fields stack. The entire eligible universe can be opened independently of the attention shortlist. Candidate inspection and consideration have separate controls.

![Desktop replay and portfolio comparison](artifacts/showdown_ai_selection_review/review-desktop.png)

[Mobile screenshot](artifacts/showdown_ai_selection_review/review-mobile.png) and [browser verification](artifacts/showdown_ai_selection_review/browser-verification.json) cover the actual built app at 1440px and 390px, including recommendation import and simulated selection/approval revisions. All browser-test writes terminate at local mocks.

## 3. APIs, schemas and persistence

All paths below have the `/api` prefix. The review endpoints use the existing saved optimizer job; they never write production lineup, selection, projection or optimizer configuration records.

| Method | Resource | Behavior |
|---|---|---|
| GET | `/optimizer/results/{run}/selection-review` | Frozen review, content hash, immutable history and prelock availability |
| POST | `…/selection-review/compare` | Read-only diagnostics for two exact eligible IDs and the expected review hash |
| POST | `…/selection-review/decisions` | Append PROPOSED, SELECTED or USER_APPROVED |
| POST | `…/selection-review/execution` | Append ENTERED_CONFIRMED from imported canonical entry evidence |
| GET | `…/selection-review/download?format=json` | Prelock companion artifact; history/execution/outcomes excluded |
| GET | `…/selection-review/download?format=md` | Compact attention/review instructions |
| GET | `…/selection-review/decisions/download` | Immutable decision history, separately labeled |
| POST | `/learning/research/showdown-selection-review/{decision}/evaluate` | Join an existing frozen decision to a saved learning report after kickoff |
| GET | `/learning/research/showdown-selection-review?season=2026` | Research tracking, one observation per recorded run and overlap buckets |

Migration **0047_showdown_selection_review.sql** adds three research tables: `target.showdown_selection_review`, `target.showdown_selection_decision`, and `target.showdown_selection_outcome`. All have UPDATE/DELETE rejection triggers. Decision constraints enforce run/review lineage, unique idempotency keys, linked revisions, and prelock timestamps for selection states. A per-run advisory transaction lock prevents concurrent branches. Migration 0047 was applied to the local development database; other installations must apply it through the existing migration runner.

Contracts are documented in:

- `docs/product/showdown_two_lineup_review_v1.schema.json`
- `docs/product/showdown_selection_decision_request_v1.schema.json`
- `docs/product/showdown_selection_decision_v1.schema.json`
- `docs/product/showdown_selection_execution_request_v1.schema.json`

The existing packet schema gained optional canonical `players` and `variant_ranks` on universe rows. Candidate assessments also retain a physical QB-player count for coverage, independent of distinct QB teams. Existing archived packets and audit artifacts remain intact. New packet hashes reflect these additive fields.

## 4. Attention shortlist

Use the saved finalist list unchanged. Among eligible candidates outside that list, take at most ten using:

1. `ceiling_fraction` descending.
2. `selector_rank` ascending.
3. `candidate_id` ascending.

Groups are `DETERMINISTIC_FINALIST` and `RESEARCH_CEILING_OUTSIDER`. With the current 20-finalist policy, the shortlist has at most 30 distinct candidates. No actual results, new quality screen, market exclusion or rank cutoff participates. Every eligible candidate remains accessible in the complete universe.

Rows and expandable details include exact IDs, selector/projection/ceiling ranks, mean, summed marginal P90 proxy, normalized mean/ceiling quality, canonical CPT/FLEX rosters, Captain, team split, QB structure, primary script/thesis, market assessment/reasons, salary left, ownership availability and risk flags.

## 5. Captain/script coverage

Summaries cover Captain position, individual Captain, favorite/underdog side where known, zero/one/two QBs, 3–3/4–2/5–1 splits, football-script families, and WR/TE Captain pairing with the same-team QB. Each construction shows generated, eligible and finalist counts, plus its strongest ceiling nonfinalist when present.

Stages distinguish `NEVER_GENERATED`, `FAILED_QUALITY_ELIGIBILITY`, `QUALITY_ELIGIBLE_NOT_FINALIST`, and `INCLUDED_IN_COMPLETE_UNIVERSE`. Generated means present in the saved archive; absence does not prove infeasibility or a generator defect. No contest winner or historical construction frequency is consulted.

Ownership requires the existing frozen checklist's fresh, source-backed provenance. Missing total ownership is `UNAVAILABLE`, never zero. A sourced projected FLEX-core sum can be available while full lineup ownership remains unavailable because Captain ownership is missing.

## 6. Portfolio overlap diagnostics

Canonical physical-player IDs determine overlap independently of CPT/FLEX placement. The pair displays shared IDs/names, shared FLEX slots, Captain identities/positions/teams, script/thesis comparison, scenario intersection, team splits, QB structures, salaries, mean/P90 proxies and fractions, market compatibility, risks and available projected ownership concentration.

`unique_players_across_pair = 12 - shared_player_count`.

Two differently Captained versions of the same six physical players report six shared players. Five shared players display **“5/6 physical players shared — concentrated player core.”** This diagnostic does not reject or penalize a pair.

## 7. Lower-overlap alternatives

For a proposed pair with at least five shared players, enumerate pairs in the frozen eligible universe with four or fewer shared players. Rank using the audit's fixed method:

1. Maximum minimum of the four mean/ceiling fractions.
2. Maximum average of those four fractions.
3. Candidate IDs ascending.

Return up to three examples and the feasible-pair count. Each example retains Captain/script differences, market assessments, risk flags and sourced ownership evidence. Display current and alternative minimum mean/ceiling quality, signed opportunity cost, player changes and script changes. Negative cost means quality improved. No additional satisfaction threshold is invented. No eligible lower-overlap pair yields an explicit unavailable message; fewer than five shared players yields NOT_NEEDED.

Suggestions never modify form selections, production selection, exposure limits or an optimizer objective. A SELECTED high-overlap pair can be saved with a written deliberate-acceptance reason. Lower player overlap alone does not imply different football scripts.

## 8. Immutable decision-record contract

Every saved decision contains season/week/slate/game, optimizer/projection IDs, cutoff, frozen evidence hash and basis, candidate-pool hash, AI packet hash/contract/finalist/classifier versions, review policy, server timestamp with timezone, revision and prior decision ID.

Attention records distinguish automatically surfaced finalists/ceiling outsiders, other displayed candidates, and explicitly considered IDs. Proposed IDs, alternative-considered IDs and rejected IDs must belong to this frozen eligible universe. Proposed/rejected/alternative-considered IDs must be explicitly marked considered; rejected candidates require reasons and cannot also be proposed.

Exactly two proposed IDs, canonical Captain and roster identities, two football theses, reasoning, complementarity, overlap/quality, alternative comparisons, reviewer type/identity/model, approval status and accepted concentration exception are preserved. Reviewer identity is self-reported through the existing local app; it is not authenticated attribution. Manual reviews default to HUMAN with no model name. An explicit ChatGPT recommendation import fills AI_ASSISTED/ChatGPT, and the reviewer can correct those fields.

- PROPOSED saves a recommendation and does not claim a final selection.
- SELECTED records the chosen pair, including a deliberately accepted high-overlap exception when applicable.
- USER_APPROVED requires an existing SELECTED revision with the same ordered pair and explicit user action.
- ENTERED_CONFIRMED retains the frozen chosen pair and appends actual contest/entry identifiers and canonically resolved submitted rosters from a saved learning report. An execution mismatch is recorded honestly; an unrecognized eligible-universe candidate remains unidentified rather than fabricated.

New choices and approval append revisions; they never rewrite prior records. A changed choice resets approval. No request accepts a client decision timestamp. Retries retain the same idempotency key; reuse with a different payload fails. Records and frozen reviews are content-hashed and verified when read. Downloaded copies are review artifacts; the database record is authoritative.

## 9. ChatGPT-to-app workflow

**Export AI Selection Packet** with AI requested entries set to 2, or **Export compact review JSON**. The compact JSON includes the complete eligible candidate rows and canonical rosters, saved game/market context, attention groups, coverage, quality policy, hashes and explicit two-entry instructions. The Markdown packet includes the expanded shortlist/review instructions for a two-entry request.

Ask ChatGPT to return the recommendation JSON template shown under **Import ChatGPT recommendation**: two exact IDs, explicitly considered IDs, reasoning, two football theses, complementarity, alternative IDs actually considered, rejected IDs/reasons, and an accepted high-overlap exception if appropriate. Importing fills the form and makes no database decision. Compare the pair, review alternatives, then record the desired state explicitly.

The ordinary production DraftKings export still contains the optimizer's control lineups. For a research-selected pair, enter the exact Captain/FLEX rosters shown in candidate details or the downloaded decision record manually. This implementation does not redirect the production export to research picks.

## 10. Chronology and leakage safeguards

The prelock diagnostic builder imports no outcome/learning/research evaluator, reads only the validated frozen packet, verifies its hash and rejects nested actual/postgame/field-rank/winner/hindsight fields. No current source is queried for review. Exports omit decision history, actual execution and postgame results.

Selection persistence requires READY, complete, production frozen generation evidence; cutoff/creation/decision/kickoff chronology must be valid. Server/database time controls append operations. After kickoff, selections and approvals cannot be added or backdated. Historical panels remain replay displays. Legacy picks are `AI_SELECTION_UNKNOWN`.

Execution and evaluation are separate explicit operations. They check approval/freeze and postkickoff time before reading imported outcome evidence. Evaluations persist separately and preserve the chosen IDs/timestamps. Chosen-roster actuals and confirmed-entry performance have separate fields; entry performance remains unavailable without explicit execution confirmation. Week 4 Sunday is explicitly excluded from valid prelock studies in addition to chronology checks. No early outcomes tune attention, quality or overlap thresholds.

## 11. Test results

- **152 passed**: focused selection-review, packet/finalist, production portfolio parity, research isolation, soft-scenario/game-scenario and diversity-audit tests.
- **2 passed**: opt-in real PostgreSQL rollback tests for schema compatibility, immutable UPDATE/DELETE triggers, same-key retries, linked revisions, stale branches, research summary and prelock outcome-access blocking.
- **121 passed**: UI unit tests, including strict recommendation import and exact-ID validation.
- **UI build passed**: TypeScript and Vite. Existing bundle-size warning remains.
- **Browser checks passed**: actual built App at desktop/mobile widths; 30 shortlist rows, complete 75-candidate universe, rank41, pair/alternatives, consideration distinction, recommendation import, explicit selection/approval and existing research/checklist views. API writes were mocked.
- **Real local API verification passed**: Week5 review, read-only pair comparison, safe export and research summary; zero historical decisions created.
- **5 migration-coverage checks passed**. A pre-existing false failure was traced to the check's IF NOT EXISTS-only regex. A one-line test-parser fix recognizes both valid CREATE TABLE forms; existing migration 0046 was not changed.

Reproduction:

```sh
.venv/bin/python scripts/validate_showdown_selection_review.py
.venv/bin/python scripts/verify_showdown_selection_review_api.py
SHOWDOWN_REVIEW_DATABASE_TESTS=1 .venv/bin/python -m pytest backend/app/tests/product/test_showdown_selection_persistence.py -q
npm --prefix ui test
npm --prefix ui run build
PLAYWRIGHT_MODULE=/path/to/playwright node ui/tests/showdownSelectionReview.e2e.mjs
PLAYWRIGHT_MODULE=/path/to/playwright node ui/tests/showdownResearchReview.e2e.mjs
```

The API verifier and opt-in database tests require the local development database. Every decision inserted by persistence tests rolls back. The browser runner uses the installed/bundled Playwright module and Chrome.

## 12. Week 5 validation

Frozen run: `3a41af88-a28c-41b1-888c-462ddcd7d74d`.

| Diagnostic | Result |
|---|---|
| Quality eligible / finalists / ceiling outsiders | 75 / 20 / 10 |
| Ryan Flournoy-CPT rank41 | `…:dee93250fc131f45`, RESEARCH_CEILING_OUTSIDER |
| Observed Dak candidate | `…:beb41d478b13c469` |
| Observed Bucky candidate | `…:8e2120be4073304e` |
| Shared physical players / unique players | 5 / 7 |
| Lower-overlap alternatives shown | 3; strongest has 4 shared players |
| Current → alternative minimum mean | 96.8105% → 98.0786% |
| Current → alternative minimum ceiling | 96.9840% → 97.8175% |
| Original finalist and eligible membership | Unchanged |
| Original deterministic control | Unchanged |
| Historical AI selection / new decisions | AI_SELECTION_UNKNOWN / 0 |

The strongest alternative retains Dak Captain in both lineups and a shared favorite-pass script; its lower player overlap is not presented as independent script exposure. This is a display/replay validation of the user-requested observed pair, not a historical prelock recommendation.

Evidence: [validation results](artifacts/showdown_ai_selection_review/validation_results.json), [pair diagnostics](artifacts/showdown_ai_selection_review/week5_comparison.json), [real API verification](artifacts/showdown_ai_selection_review/database_api_verification.json).

## 13. Production regression comparison

The captured pre-task selector and current selector returned identical full lineups and diagnostics on a fixed three-candidate fixture. Its selected pair still shares five players, demonstrating that no overlap cap was added. [Before/after hashes](artifacts/showdown_ai_selection_review/production_regression_comparison.json) and [working baseline](artifacts/showdown_ai_selection_review/working_baseline.json) preserve the comparison.

`gpp_optimizer.py` and `showdown_portfolio_selection.py` match their task-start source hashes. Another concurrent task changed `optimizer.py` input handling during implementation; those edits were preserved, this task made no edits to that file, and the source difference is disclosed in validation evidence. Frozen Week5 finalist rows, complete universe membership, candidate-pool evidence and four deterministic control rows compare equal to the archived packet. No original audit, historical selection or Week5 decision was rewritten.

## 14. Known limitations and examples

- No genuine prospective decisions exist yet; real selection-outcome learning begins on future slates. Early observations remain descriptive, one slate per observation.
- Captain/script labels are the existing saved classifier's hypotheses; they do not estimate script probabilities.
- Summed marginal P90 is a ceiling proxy. Missing ownership/projections/results are not zero-imputed.
- Lower-overlap enumeration is quadratic in eligible candidates. Only three diagnostics are materialized; there is no universe truncation.
- Entry confirmation currently uses the existing postgame normalized result/learning workflow. It cannot verify a DraftKings submission before those imported records exist.
- Research picks are entered manually; native-ID research upload/export routing was not added.
- Reviewer identity/model are self-reported. No hidden AI call, automatic recommendation or threshold promotion was added.
- A pending PROPOSED revision does not become a final selection. Research summaries retain the latest actual chosen revision when present.
- The existing frontend bundle-size warning remains.

[Example exported compact review packet](artifacts/showdown_ai_selection_review/example_review_packet.json) and [Markdown packet](artifacts/showdown_ai_selection_review/example_review_packet.md) use frozen Week5 evidence and remain historical displays. [Example decision record](artifacts/showdown_ai_selection_review/example_decision_record.json) is explicitly synthetic, uses an example future identity, and was never persisted. It does not invent a Week5 AI decision.

## 15. Next live Showdown slate

1. Start/reload the updated backend and UI. Apply numbered migrations through 0047 on any environment where it is missing.
2. Run the existing live Showdown optimizer and wait for completion with frozen READY evidence.
3. In **Recent optimizer runs**, click **AI Candidate Review** for that exact run. This resets AI requested entries to 2.
4. Review finalists, ten ceiling outsiders and Captain/script coverage. Open **Complete eligible universe** when needed. Use **Inspect** for rosters and diagnostics; mark **Explicitly considered** only when actually considered.
5. Click **Export compact review JSON**. Share it with ChatGPT and request exactly two exact candidate IDs plus the displayed recommendation JSON contract.
6. Paste the recommendation into **Import ChatGPT recommendation**, click **Load recommendation into review**, then **Compare proposed pair**. Evaluate the shared core, script exposure, alternative quality and substitutions. No alternative is adopted automatically.
7. Complete reasoning, two theses, complementarity, explicit consideration and rejections. For a concentrated pair, write the deliberate high-overlap exception. Click **Record PROPOSED** if retaining a draft; click **Record SELECTED** for the actual chosen pair.
8. Check **I approve exactly this proposed pair**, then click **Record USER_APPROVED** before kickoff. Changes require another SELECTED revision and renewed approval. Download the decision history.
9. Enter the exact chosen Captain/FLEX rosters in DraftKings manually. Check them against the saved record. A recommendation or export does not count as entered.
10. After the game, import actual DraftKings results and generate the existing slate learning report. Reopen the run's review and expand **Confirm actual entries / join postgame learning**. Supply report ID and two contest/entry IDs, then click **Confirm ENTERED_CONFIRMED from imported evidence**.
11. Click **Join frozen decision to outcomes** using the saved learning report. View **Research Lab → Showdown research notes → Showdown prospective selection learning** and refresh. Unavailable actuals/fidelity remain explicit; no optimizer thresholds change.
