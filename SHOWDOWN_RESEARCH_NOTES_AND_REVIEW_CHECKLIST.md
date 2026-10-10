# Showdown research notes and prelock review checklist

Implemented October 9, 2026. The 2026 Captain Contest Consistency study is
preserved for human/AI research review in **Research Lab → Showdown Research**.
**Operations → Recent optimizer runs → Prelock review checklist** reads the
existing frozen AI packet and shows a compact, nonbinding construction review.
Markdown and JSON packet exports contain the same checklist.

## Research record

Every finding has the exact label
`RESEARCH_ONLY / OBSERVATIONAL / NOT PRODUCTION VALIDATED`, its sample period,
comparison baseline and limitations. The application record is
[`docs/product/showdown_research_notes.json`](docs/product/showdown_research_notes.json),
served by the read-only `GET /api/learning/research/showdown` endpoint. It records
the SHA-256 and capture timestamp of the existing study's `analysis.json`.
It contains no account names or account-ranking feature data.

The sample covers **September 9 through October 8, 2026**, captured October 9:
10 imported games, 30 contests and 690,212 entries, with 2,933 unresolved entries.
Four other primetime games are absent. Success is a contest top-decile finish;
boundary ties count in the descriptive success subsets, while period/holdout
hit-rate comparisons use fractional credit at the boundary.

| Preserved observation | Comparison baseline | Main limitation |
|---|---|---|
| WR/TE Captain successes paired with their own QB: **88.9% watchlist / 81.1% reference field** | 104/117 versus 26,289/32,418 successful WR/TE account-game rosters; roster copies deduplicated within account/game | The 19-account watchlist was screened retrospectively on the same sample; this is not a causal pairing requirement. |
| One-QB/two-QB performance varies by period | Largest imported contest per game, first six versus later four: one QB **11.9% → 9.2%**; two QBs **7.6% → 12.3%** tie-adjusted hit rates | Small, different game environments and entrant populations; no universal QB count follows. |
| 5–1 versus 3–3/4–2 performance varies; no universal preferred split | Same period comparison: 5–1 **15.0% → 6.8%**, 3–3 **8.4% → 11.8%**, 4–2 **9.2% → 10.2%** | Composition and game conditions confound the comparison; no quota or split preference is promoted. |
| Successful watchlist and field rosters both had about **$400 median unused salary** | 230 known-salary watchlist successes versus 66,590 known-salary field successes | A median is not a target; eight successful field rosters lack salary, and there is no controlled salary experiment. |
| Early-selected accounts did not outperform the later field collectively: **9.7% / 10.0%** | Later-four-game tie-adjusted entry rates: 9.6778% for the cohort versus 9.9974% field; select on the first six games only, 95 accounts selected, 89 later participants | Short holdout, dependent entries, unequal volume, participation bias; handles are accounts rather than verified people. |

The app's expandable findings retain the exact denominators, early selection
criteria and per-finding limitations. These observations support future review,
not projections, scoring, eligibility, production validation or ROI claims.

## Frozen prelock checklist

The checklist is built **after** the existing packet quality assessments,
deterministic finalists and production control have been established. It reads
only their allowlisted saved fields and frozen source provenance. It never
queries a current player, market, projection, contest outcome or account ranking.

| Review prompt | Display and evidence |
|---|---|
| Captain archetypes represented | Existing classifier counts for generated, quality-eligible, finalist and saved-proposal scopes |
| Zero-, one- and two-QB coverage | Counts for those same four scopes |
| Why plausible QB families are absent | Separate zero-QB, one-QB by team and two-QB rows: generated, eligible, finalist and proposal counts; generation absence versus existing quality reasons versus finalist omission |
| WR/TE Captain with own QB | With/without pairing counts by scope, using roster position/team evidence |
| 3–3, 4–2 and 5–1 coverage | Saved team-count construction counts by scope |
| Salary left and sourced projected ownership | Saved salary left; projected total ownership only when frozen ownership is fresh, has sources/run IDs and a timezone-aware observation at/before cutoff; otherwise `Unavailable` |
| Proposed two-entry physical-player overlap | Reuses the existing canonical-player similarity calculation for an exactly two-entry saved production control; Captain/FLEX swaps still count as the same player |

An absent generated family is labeled `not_present_in_saved_generated_pool`
with `generation_reason_unavailable` when the archive provides no explanation.
This does not assert infeasibility. An entirely quality-screened family instead
retains the existing quality reason codes. Eligible families omitted from the
deterministic finalist control remain available in the full AI Review Universe.
No family quota, salary target or overlap cap is introduced.

The saved optimizer proposal is identified as the control; an actual AI choice
is never inferred. For a proposed AI pair, the JSON's
`prelock_review_checklist.candidate_details.physical_player_ids` supports a
canonical ID intersection across all eligible candidates. There is no new
decision persistence or selection action. If the saved control contains other
than two entries, its two-entry overlap is explicitly unavailable.

Runs created at/after kickoff still follow the existing retrospective diagnostic
workflow, but receive **no prelock checklist** because prelock generation is
unverified. Historical prelock archives lacking frozen readiness provenance
remain explicitly incomplete diagnostic evidence. Live packet export retains
the existing frozen-readiness requirement. A frontend/backend version mismatch
shows an explicit unsupported-checklist message instead of a stale display.

## Production and audit preservation

- Research storage is a separate, read-only JSON artifact. Its loader has no
  production solver, projection or selector consumer.
- No weights, thresholds, caps, strategy versions, finalist policy, classifier
  version, candidate generation or production selection logic changed.
- The existing `ai_showdown_finalists_v2` and `ai_showdown_construction_v2`
  settings are retained. Before/after Week 4 packet comparison confirms all
  **12 existing non-hash/timestamp fields are identical**, including candidates,
  quality eligibility, metrics, ordering, finalists, similarity and controls.
- Adding the display checklist changes the new packet's evidence hash; manual
  reviews should cite the hash of their actual export. Earlier packet artifacts
  and decisions were not rewritten.
- The existing [selection-regret and portfolio-diversity audit](SHOWDOWN_SELECTION_REGRET_AND_PORTFOLIO_DIVERSITY_AUDIT.md),
  its JSON, scripts and tests are preserved. The checklist reuses packet
  classifications and canonical overlap rather than implementing another
  retrospective audit.

Task-specific baseline copies and a focused patch are saved in
[`artifacts/showdown_research_review`](artifacts/showdown_research_review).
This separates this addition from the substantial changes already present in
the working tree.

## Validation

**106 targeted backend tests passed.** The command was:

```sh
.venv/bin/python -m pytest \
  backend/app/tests/product/test_showdown_research_review.py \
  backend/app/tests/product/test_ai_showdown_packet.py \
  backend/app/tests/product/test_ai_showdown_finalist_audit.py \
  backend/app/tests/product/test_showdown_production_research_parity.py \
  backend/app/tests/product/test_showdown_portfolio_selection.py \
  tests/test_showdown_selection_diversity_audit.py -q
```

The new tests verify:

- Every research finding has the required label, period, baseline and limitations;
  its source checksum matches the saved analysis when that archive is installed.
- Replacing research metadata with arbitrary weights, a salary target and account
  rankings leaves the production solver input DataFrame, all solver arguments
  and resulting canonical selections unchanged. The orchestration test captures
  the solver call with a mocked solve; the GPP portfolio test exercises the
  actual production selector and confirms identical selection and audit reports.
- Research tags and irrelevant account/outcome metadata do not enter the AI
  packet, quality assessments, review universe or checklist.
- Checklist construction is pure; generation absence and quality filtering are
  distinct; Captain/FLEX swaps preserve physical-player overlap.
- Missing, stale, unsourced and after-cutoff ownership remain unavailable.
  After-kickoff generated runs cannot receive a prelock checklist.
- Existing packet Markdown/schema and policy contracts remain supported.

`npm run build` passed (TypeScript and Vite). The existing bundle-size advisory
remains; no dependency was introduced. `git diff --check` passed.

The actual built App passed
[`ui/tests/showdownResearchReview.e2e.mjs`](ui/tests/showdownResearchReview.e2e.mjs)
at **1440px and 390px**, using the existing Playwright runtime. It verifies app
navigation, research labels, read-only controls, frozen checklist content,
canonical overlap, mobile horizontal scrolling, graceful old-packet handling,
no page errors and **GET requests only**. Set `PLAYWRIGHT_MODULE` to an existing
Playwright installation when it is not available on the normal module path:

```sh
cd ui
npm run build
node tests/showdownResearchReview.e2e.mjs
```

The browser check uses intercepted frozen responses and the real production
App build. It makes no live backend/source requests, production solves or writes.
The screenshots are a display example, not a new optimizer recommendation.

## App screenshots and examples

Research card, with the pairing and early-account holdout findings expanded:

![Research card at desktop width](/Users/wones/git/football_26/artifacts/showdown_research_review/research-desktop.png)

The checklist example uses a **two-entry display subset** of the original
four-entry archived Week 4 Thursday control. The full control was preserved in
the before/after comparison. This reference has incomplete readiness/ownership
provenance, so the app explicitly displays diagnostic status and unavailable
ownership. Example coverage is 117 generated / 93 quality eligible / 20
deterministic finalists; zero-QB generation count is 0. The display subset has
one one-QB and one two-QB entry, $700 left in each and **3 of 6 shared physical
players**. These numbers do not originate from the historical study findings.

![Frozen checklist at desktop width](/Users/wones/git/football_26/artifacts/showdown_research_review/checklist-desktop.png)

Mobile captures retain readable prose and horizontal table scrolling:
[research](artifacts/showdown_research_review/research-mobile.png) and
[checklist](artifacts/showdown_research_review/checklist-mobile.png).

Machine-readable/readable examples and verification:

- [Updated complete-control packet JSON](artifacts/showdown_research_review/packet_after.json)
  and [Markdown](artifacts/showdown_research_review/packet_after.md)
- [Packet preservation comparison](artifacts/showdown_research_review/packet_preservation.json)
- [Browser verification](artifacts/showdown_research_review/browser-verification.json)
- [Task files](artifacts/showdown_research_review/task_files.json) and
  [focused patch](artifacts/showdown_research_review/task_changes.patch)

Normal application rollout must load the updated backend routes and frontend
build together. No database migration, source refresh or production run is
needed for the research notes themselves.
