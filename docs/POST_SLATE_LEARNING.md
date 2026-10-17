# Post-slate learning reports

## Weekly Results

Open **Learning → Weekly Results**, enter the **Results username**, and select
**Results week**. Learning has its own **Season**, **Week** and **Review slate**
controls, persisted as `football-26-learning-context` in browser storage. On first
visit it starts with the active season/week and **All slates**; subsequent review
changes do not alter the app's active context, selected runs or optimizer format.
Both Learning subtabs share this review context. **All slates** shows whole-week
financial totals; a specific slate shows its existing totals, contests and entries
without averaging ROIs or hiding missing-evidence warnings. Week-wide warnings
are labeled separately. Available weeks come from that user's imported standings.
**Refresh results** performs a read only: it does not ingest files, refresh public stats, rebuild reports, change
assignments or run an optimizer. **Review & Imports** keeps the existing import
and learning-review workflow.

Review report details and shadow comparisons follow **Review slate**. Building
or downloading a **Week Learning Report** still covers the whole review week;
its summary and download are labeled as such when details are filtered. Folder
scans use the review season/week as defaults; verified per-file scopes remain
authoritative and the slate filter never assigns a file to a contest. Annual
entry history uses the review season and remains explicitly calendar-year scoped.

`GET /api/learning/results/weekly?season=2026&week=5&entry_user=wones0120`
joins current normalized standings to deduplicated entry history by native
contest and entry IDs, and reads the latest saved review per slate. It creates
no records and needs no schema changes. Financial scope is imported standings
for the selected user, not proven account-wide coverage; history entries without
matching standings are outside these totals. Source hashes appear in entry
drilldowns. Saved learning warnings retain their report ID/date and remain
separate from current financial coverage, including missing intent and ambiguous
origin warnings. Entries absent from a saved review are explicitly flagged.

ROI is `(cash winnings - recorded fees) / recorded fees`, using summed amounts
rather than averaging entry or slate ROIs. Cash rate is the fraction of entries
with positive cash winnings; ticket prizes do not count as cash. Known zero-fee
entries remain included and ticket prizes are reported separately. A zero fee
does not establish ticket funding. Zero-fee ROI is N/A. Refunds, credits, actual
funding sources and settlement state remain unmodeled; deposits and withdrawals
are outside contest performance.

Missing history winnings stay unknown; payout tiers are not substituted for
realized personal winnings. Stored contest fees can supply known fees when
history is missing. Conflicting history versions withhold the entry's financial
amounts. Incomplete weeks show known fees, known winnings and the net subtotal
for entries with both amounts, while complete-week net/ROI remain unknown.
Cash rate remains unknown until every entry's cash payout is known. Empty weeks
remain unknown, and each slate/contest shows its own evidence coverage. Changing
week/user clears the prior result and ignores late responses from the old scope.

Browser validation: after `npm --prefix ui run build`, run
`PLAYWRIGHT_MODULE=/path/to/playwright node ui/tests/weeklyResults.e2e.mjs`
with installed Chrome and Playwright. The fixture intercepts every API request,
checks desktop/mobile and GET-only behavior, and writes screenshots to a fresh
temporary directory. No live data is changed.

Learning entry details and downloaded reports show **Intended / Exported / Observed evidence**.
Intended means an explicit contest/entry assignment; its stored timestamp does not
establish original submission timing. Exported includes portfolio artifacts and
existing direct-download ledger records, with artifact IDs, recorded times, export
rows and saved-roster links where available. A portfolio-only or run-only link is
labeled; direct roster equality does not create an entry-specific export link.
Observed means the imported standings entry and canonical roster, keyed by contest
and entry ID. FLEX reordering can preserve roster equality while exact slots differ;
Captain differences prevent equality. Multiple matching saved lineups are listed,
including matches across optimizer runs; a newest run is not selected as proven origin.
Missing assignment and lineage warnings remain. Exports, roster equality and standings
do not prove original submission intent or timing, and a saved-versus-entered score
difference alone is not an execution error. Newly built reports freeze this evidence
and include it in entry drilldowns and hashes. Older immutable reports stay unchanged;
their existing portfolio exports remain readable, with unavailable details explicit.
No migration, submission workflow or historical backfill is required.

For the proposed automatic outcome-registration, settlement, and controlled model-improvement workflow, see [Automated decision, quality control, and learning](product/automated_decision_quality_workflow.md). That architecture is not yet implemented; the behavior below describes the existing report/import workflow.

For preserved Showdown observations, open **Research Lab → Showdown Research**.
The 2026 Captain Contest Consistency study is available through the read-only
`GET /api/learning/research/showdown` endpoint and the checked-in
[`showdown_research_notes_v1` metadata](product/showdown_research_notes.json).
Each finding records its sample period, comparison baseline and limitations
and carries `RESEARCH_ONLY / OBSERVATIONAL / NOT PRODUCTION VALIDATED`.
This metadata is separate from live optimizer inputs, football projections,
eligibility, candidate scoring and selection. The existing
[selection-regret and portfolio-diversity audit](../SHOWDOWN_SELECTION_REGRET_AND_PORTFOLIO_DIVERSITY_AUDIT.md)
remains the source for that retrospective audit; this addition does not repeat it.
See [app examples and isolation validation](../SHOWDOWN_RESEARCH_NOTES_AND_REVIEW_CHECKLIST.md).

For a cross-slate ownership calibration and Classic correlation/portfolio
review after Week 3, see [the Week 3 audit](WEEK3_OWNERSHIP_CORRELATION_PORTFOLIO_AUDIT.md).
The saved-pool versus selection and entry analysis is in the
[Week 3 optimizer effectiveness review](WEEK3_OPTIMIZER_EFFECTIVENESS.md).
The [frozen-pool selector and generation coverage audit](WEEK3_SELECTOR_AND_GENERATION_COVERAGE_AUDIT.md)
compares saved Classic candidates across fixed shadow selectors and checks where
pregame construction coverage narrows. It labels missing actuals, excluded
historical runs, and unavailable generator replays explicitly.
The [Week 4 prospective structural-coverage plan](WEEK4_PROSPECTIVE_STRUCTURAL_COVERAGE_PLAN.md)
defines one unchanged production arm, one pre-lock structural/risk generation
shadow, and one overlap≤6 shadow selected from the original candidates. New
Classic small-field runs freeze a hashed solver snapshot and these three arms
only when saved kickoff evidence proves the run preceded lock. After Classic
player actuals and field standings are imported, preview and append the
separate postgame comparison with
`PYTHONPATH=. .venv/bin/python scripts/finalize_classic_prospective_experiment.py OPTIMIZER_RUN_ID --dry-run`
and then the same command without `--dry-run`. Migration `0039` is applied to
the local development database; other environments need it before their next
Classic run. The pre-lock snapshot is never rewritten after scoring.

`LEARN-001` turns normalized DraftKings contest results into immutable,
user-specific slate reviews. In Learning, select the season and week, enter the
DraftKings username under **Week learning report**, and select **Build Week
Learning Report**. The username is retained locally in the browser. The weekly
report discovers every imported slate with that user's entries and includes its
slate reviews. A successful **Load Ownership (Past Slate)** in Operations or
**Load selected files** in Learning refreshes the report automatically when
a username is present.
Before building the slate reviews, each weekly report pulls published nflreadpy
player stats for the selected season and week once. It archives an immutable,
content-addressed CSV and ingests that snapshot into `raw_nfl_weekly_stat` with
source-native player IDs. Exact repeats reuse the snapshot and ingest run;
updated source data creates a new archived version. Other weeks are preserved.
The report displays the number of stats records pulled and includes the snapshot
hash, observation time, and ingest run in `summary.weekly_stats` and its evidence
hash. Downloaded reports include the count and lineage. A failed fetch, failed
ingest, or week with no published stats blocks report generation with a visible
error; retry after the source is available. This pulls available published data;
upstream publication delays and existing contest/identity evidence gaps still
apply.
An analysis failure is shown separately and never changes a successful result
import into a failed import.

Builder `2026-10-13.1` produces compact v2 slate and weekly reports. It first
loads run metadata, then decodes the required saved candidate pools one run at a
time. Decision snapshots, full controls, and evaluated candidates are stored as
immutable content-addressed evidence by migration `0046_compact_learning_evidence.sql`.
Apply that migration before deploying the builder. Previously saved v1 reports
remain readable and their embedded candidate detail can use the same API.
Candidate field ranks use binary search with the existing tie tolerance.

The default optimizer policy evaluates canonically entry-linked runs. A slate
request can additionally specify `diagnostic_run_ids` (at most 20), restricted
to completed runs in the requested slate. Every excluded completed run retains
its ID, configuration hash, and reason in `optimizer_effectiveness.inclusion_policy`.
Historical calibration retains complete entry-linked predecision numeric samples.
The weekly evidence hash includes the historical report IDs and correlations.
Scores and rankings are unchanged; tied construction frequencies have deterministic
canonical ordering. Evidence gaps still appear explicitly.

In each slate review, expand **Inspect saved candidate details** to retrieve one run page
at a time. The default report holds at most 20 preview candidates per run,
including the best scoreable candidate. Full evidence is frozen to the report:

```text
GET /api/learning/reports/{report_id}/optimizer-runs/{run_id}/candidates?offset=0&limit=100
GET /api/learning/reports/{report_id}/entries/{entry_id}/evidence?contest_id={contest_id}
GET /api/optimizer/cache-status
```

Candidate pages accept `limit` 1–200 and nonnegative offsets. Entry links open
the original saved decision and full control evidence. Neither endpoint rescores
mutable current data; missing frozen evidence fails explicitly.

The full Week 4 benchmark now measures 539 MB peak Python RSS, 383 KB response,
and 15.6 seconds, with zero additional system swap/pageouts in that measurement.
See [the memory work plan](WEEKLY_LEARNING_MEMORY_REDUCTION_TODO.md) for commands,
baseline parity, artifacts, and measurement limits. Durable worker dispatch is
conditional on repeated duration above 60 seconds and is deferred for this fixture.
Telemetry records timings, configuration sizes, candidate counts, response size,
and process lifetime peak RSS. Warning budgets are 2 MB responses, 60 seconds
weekly duration, and 1 GB process RSS (confirm RSS attribution with a fresh benchmark).
`OPTIMIZER_RESULT_CACHE_MAX_ENTRIES=1` and
`OPTIMIZER_RESULT_CACHE_TTL_SECONDS=60` bound completed persisted-result retention;
TTL is checked on access. Zero disables completed-result retention. Active jobs
remain available and evictions reload from persisted state. Preparation polling
allows one pending refresh per scope and backs off on slow or failed responses.

Select **Download report for ChatGPT** after building a week report to save a
Markdown file locally. The file includes week and slate summaries, entry and
player comparisons, the captain 1.5 scoring explanation, evidence gaps, and
the compact structured report JSON and stable full-evidence links.
The links require the running app; v2 downloads do not embed every raw candidate
or full decision/control payload. Upload it to ChatGPT yourself for deeper
analysis. The export does not change or promote any model.

## Optimizer effectiveness

The downloaded report puts **Optimizer effectiveness** before the detailed entry
sections and JSON. Each canonically matched optimizer run identifies its saved
candidate-pool source and SHA-256 digest, scores every candidate with available
canonical player actuals, and compares generated, selected, and matched entered
lineups. Classic uses each player's base DK score; Showdown multiplies the
captain's base score by 1.5 exactly once. Pregame metrics remain in `pregame`;
actual scores, ranks, and field results appear only in `postgame`. New optimizer
runs persist a deterministic `strategy_runtime.candidate_pool_manifest` beside
the existing complete candidate rows when those rows are available. A missing
historical pool is labeled `candidate_pool_unavailable`, never reconstructed as
an original pool. Historical replay requires separately verified point-in-time
inputs and is not attempted by this report.
Explicit diagnostic requests evaluate additional completed runs in the slate;
`run_scope` distinguishes them from entry-linked decisions. Excluded run IDs and
reasons remain visible. The concise week table uses entry-linked decisions.
Scenario variants of the same Showdown roster remain separate saved candidates;
the manifest also records the distinct-roster count, and saved selected ranks
identify the chosen variant.

The report includes best, median, P90/P95/P99 scoreable generated scores, selected
and entered best scores, observed regret, selector top-K capture, and Pearson and
Spearman correlations for saved pregame metrics. If any candidate player actual
is unresolved, the best scoreable candidate is a lower bound on the true pool
best, actual ranks are bounds, and correlations use only scoreable candidates.
The missing canonical player IDs and candidate count are explicit. Selected
lineups are matched by canonical IDs and captain slot; entered lineups require
the same canonical signature. An entered lineup without run lineage still
contributes to the slate's best entered result and remains visibly unmatched.

Field thresholds use the full imported standings for each contest and include
all entries tied at a threshold. A contest with fewer scored entries than its
declared field size has `complete_scored_field_not_imported` status. Payout tiers
are needed only for the cash line; winner, median, and top 0.1/1/5/10/20%
thresholds remain available without payout data. Top-of-field construction
summaries require contest-scoped resolved identities; salary and game context
also require a DraftKings salary snapshot no later than the matched optimizer
cutoff. Coverage counts show how many top lineups support each summary.

The weekly export's multi-week table reads the latest saved slate reports. It
retains separate Classic/Showdown and contest-strategy rows, showing field
percentiles, observed regret, selector Spearman, and attainment rates where
evidence is complete. A single week is descriptive evidence, not a rule or
weight change. Pooled selector correlations require at least two complete
candidate pools of the same format whose saved run creation and data cutoff both
precede their saved kickoff evidence; otherwise the aggregate stays unavailable.

## Loading a week from a folder

Put downloaded DraftKings contest standings CSV or ZIP files in `~/NFL` (or
another folder you enter in **Contest results folder**). In Learning, choose
the season and week, select **Scan contest folder**, check the files to import,
review their season, week, and slate, then select **Load selected files**. The scan
shows recognized contest standings in subfolders. Loading processes only checked
files and records a durable batch and per-file status in `target.import_batch` and
`target.import_batch_file`. It identifies exact repeats by content hash and
season/week/slate, including files previously loaded through Ownerships. A
changed file is a new source version and is processed again. A saved contest
identity can supply its actual season, week, and slate even when the Learning
screen is set to another week. The selected week applies only to a file whose
slate is explicitly labeled but whose week has no stronger evidence.

After a successful normalized load, newly imported and previously imported selected
standings move to `Processed` inside the selected folder. Slate subfolders are
preserved there, and an existing archive filename is never overwritten. Scanning
does not move files. Unselected, failed, skipped, and staged files remain in place. Future
weekly scans ignore `Processed`; the per-file ledger records the original path
and the archive destination in its message.

DraftKings standings downloads contain a contest ID in their filename but no
season, week, or slate column in the CSV. The importer uses saved contest
metadata when available. Otherwise, it compares every observed contest player
with same-week DraftKings salary files in the selected folder. A unique complete
match fills in the slate automatically and records the salary filename and
content hash in the batch ledger. A partial or ambiguous match remains **Needs
slate** so its scope can be reviewed before loading.
The folder import API can still stage unresolved raw downloads in
`target.dk_contest_staged_file`. Staged files have no normalized entries or
ownership and do not enter weekly learning. A selected scope that conflicts
with saved contest metadata or a filename label is reported as `failed` for
review. A changed file is rejected after scanning so it can be scanned again.
Keep the archived ZIP/CSV files for source lineage.

The API equivalents are:

```http
POST /api/learning/reports
{"season": 2026, "week": 1, "slate": "SUNDAY_NIGHT", "entry_user": "example_user"}

GET /api/learning/reports/latest?season=2026&week=1&slate=SUNDAY_NIGHT&entry_user=example_user

POST /api/imports/draftkings/weekly-contests
{"directory": "~/NFL", "season": 2026, "week": 1, "dry_run": true}

POST /api/imports/draftkings/weekly-contests
{"directory":"~/NFL","season":2026,"week":1,"dry_run":false,"selected_files":[{"path":"/Users/example/NFL/contest-standings-123.zip","source_file_id":"dk_file_<hash from scan>","season":2026,"week":1,"slate":"SUNDAY_MAIN"}]}

POST /api/learning/reports/weekly
{"season": 2026, "week": 1, "entry_user": "example_user"}

POST /api/learning/outcome-events
{"season":2026,"week":2,"slate":"MONDAY_NIGHT","player_id":"canonical-uuid","tag":"NORMAL_VARIANCE","evidence":"Completed-game participation reviewed against the source","source_url":"https://source.example/game","observed_at":"2026-09-22T03:00:00Z"}
```

Each `slate_learning_report_v1` records the exact contest and source-file IDs,
the user's normalized entry results, canonical player identities, actual points
and ownership, projection errors, symbolic-rule comparisons, relevant belief
versions, lineup and optimizer run IDs, entry assignments, portfolios, export
validations, and available OPT-007 controls. Showdown actuals and projections
retain their roster-slot weighting, so the captain multiplier is not applied a
second time. In the Learning tab, captain rows show the base projection and
actual score multiplied by 1.5, followed by the slot-weighted values used in the
lineup total and prediction error. A belief is scored as predictive only when its
immutable creation time is at or before the earliest matched optimizer decision
cutoff. Retrospective,
late, or missing-timestamp beliefs remain visible and unscored.

Optimizer runs now store a `decision_snapshot` in `constraint_config_json` with
the pregame cutoff, selected lineups, user exclusions, availability overrides,
captain prior, ownership and market inputs, and matched control summaries.
Callers can pass `params.decision_context` for major hypotheses, injury scenarios,
ownership observation time, important alternatives, and the selection reason.
Missing context stays empty or null; old runs are not rewritten from hindsight.

OPT-007 outcomes include actual DK points and observation IDs for every selected
and control player, including unrostered controls. A missing or conflicting
control actual leaves the delta unscored and appears in `missing_evidence`.
The report keeps the exact swap, both projected means, individual ceiling sums,
ownership sums, actual totals, and the selected-minus-control score.

Each entry includes contest type, field size, fee, payout, profit, ROI, rank,
percentile, and the cash line when payout tiers and paid-entry scores exist.
Slate and week summaries report entered and returned amounts, net profit, ROI,
cash count, and observed net-positive slate frequency only when all relevant
financial evidence is complete. This observed frequency is not a forecast.
Portfolio review groups recorded lineup structures and bankroll by lineup and
structure family; different lineups do not receive credit merely for being different.

The V2.1 report uses `lineup_structure_family` for constructions such as
`two_sided_pass_stack` and `run_control`. Its separate `game_environment` contains
only saved, point-in-time-safe market inputs: total, spread, and implied team
totals. Pace and pass expectations are null when unavailable. A two-sided pass
stack does not imply a football shootout. The optimizer's legacy `shootout`
script ID remains an internal portfolio target; its visible label is
**Two-sided pass stack**. This cleanup does not change solver constraints or
production weights.

Entry-weighted MAE/RMSE remain available alongside unique slate-player projection
metrics. The latter deduplicate repeated entries and CPT/FLEX exposures by
canonical player, projection run, and base projection. Postgame outcome tags come
only from explicit, source-backed `target.player_outcome_event` rows. An untagged
residual is `UNKNOWN`; a disruption-tagged residual is excluded from training
eligibility and thesis scoring. Migration `0036_player_outcome_events.sql` adds
that append-only evidence table. A single slate supports a hypothesis, not a
production rule change; chronological multi-slate validation remains required.

`UNKNOWN` means the outcome has not been adjudicated and is training ineligible.
An operator can record `NORMAL_VARIANCE` through the source-backed outcome-event
API after reviewing a routine completed game. It is training eligible only when
a projection residual exists. Disruption tags remain ineligible. Reports show
entry-weighted and unique-player counts by tag and training eligibility.
Weekly `net_positive_slates` and `net_positive_slate_frequency` are null when
any included slate lacks complete financial evidence.

New completed optimizer runs must persist their decision snapshot and lineup
lineage; a persistence failure returns a failed run. The snapshot is captured
with the run and stores `params.decision_context` when supplied. Historical
runs with no snapshot or prelock beliefs remain explicit gaps.

Entry assignments are the strongest lineup provenance. When an assignment is
absent, the report may associate an entry with a saved lineup only when its
canonical player IDs and captain assignment match exactly. This association is
labeled `canonical_lineup_signature`; it proves that the application generated
the same construction but does not prove which saved run was uploaded.

Reports are content addressed. Repeating a run with identical evidence returns
the same report ID for the recorded builder version. New contest files, identity
decisions, saved lineups, rule applications, beliefs, portfolios, or exports
produce a new evidence hash and a new immutable report. A report-logic change
increments the builder version and also creates a new report without rewriting
earlier output. The `partial` status is expected whenever evidence is missing.
`missing_evidence` identifies the exact entry, lineup, contest, or slate gap
instead of filling it from hindsight. Fees and payout tiers are required for
profit and ROI; old optimizer runs without matched controls keep OPT-007
unavailable.

The week response has a deterministic ID derived from the included immutable
slate report IDs. It counts imported contests and entries, summarizes evidence
coverage, and shows per-slate entries with actual versus projected points and
player-level misses where lineup provenance exists. Its projection MAE/RMSE is weighted by
entered lineup players for review; repeated players across entries are not
independent training labels. The child slate reports remain persisted, so a new
result file or resolved identity generates a new weekly ID without rewriting the
old reports.

Observed outcomes are diagnostic. Contest results provide actual ownership
evidence. Player projection training also needs canonical weekly football results
and a chronological feature rebuild. **Run projections** can refresh completed
weeks whose loaded stats have not yet rebuilt their training labels. A single
report does not promote or retune a model, ownership forecast, or symbolic rule;
those changes still require their declared time-safe evaluation and promotion
gates.

## Weekly reading order

1. Check evidence coverage. `partial` describes missing evidence, not poor DFS
   performance. Resolve identity and lineup lineage first; fees and payouts are
   needed only for financial evaluation.
2. Read each entry's `top_percent`: smaller is better. Compare Classic with
   Classic and Showdown with Showdown, while accounting for field size and contest
   type.
3. Track projection MAE across several comparable slates. It is the average
   player-level miss in DraftKings points, so lower is better, but one slate is
   too noisy to justify a model change.
4. Check matched optimizer entries. A result can explain projections, rules,
   OPT-007 controls, and portfolio lineage only when it matches a saved lineup.
5. Review duplicate lineups and captain exposure separately from player outcomes.
   These measure construction and diversification decisions even when a player
   outcome was unusually good or bad.
6. Review predecision beliefs. `supported` and `contradicted` score the thesis;
   `helped`, `hurt`, and `no measurable effect` compare an exact selected
   intervention with its stored counterfactual. Retrospective and late evidence
   remains unscored.

LEARN-002 uses the next slate's frozen model/human bundle to ask only high-value
questions. LEARN-003 connects those answers and guarded belief decisions to later
outcomes. See `docs/HUMAN_OUTCOME_LEARNING.md` for timing and scoring rules.

Migration `0032_slate_learning_reports.sql` creates
`target.slate_learning_report` and refreshes the governed target-schema contract.


## Evaluation evidence and recovery

Apply `0050_evaluation_record.sql` before running the updated services. The
append-only `target.evaluation_record` ledger stores content-addressed evidence;
updates and deletes are rejected. Existing raw observations and learning reports
remain intact. This changes evidence capture and evaluation, not projections,
optimizer rules, or selection weights.

Completed optimizer runs automatically retain their full original candidate pool,
configuration, projection rows from the original projection run, saved lineups,
cutoff, and available saved kickoff evidence. Sequential Classic runs explicitly
save the accepted portfolio as their complete generated pool; recovery does not
invent rejected candidates. A missing original pool or timing proof remains
unavailable. Historical naive UTC database timestamps are retained; an original
explicitly zoned frozen-input timestamp can establish prelock timing. New writes
preserve UTC timezone information.

Identifiers have separate meanings:

- **Candidate ID**: `<optimizer_run_id>:candidate:<ordinal>`, scoped to the original
  pool. Original source IDs and Showdown AI review IDs are retained as mappings.
- **Lineup ID**: the persisted saved lineup identifier. **Saved lineup number** is
  its display number within that run; multiple candidate variants can map to it.
- **Selector rank**: only the explicitly saved selector rank. Generation order is
  not silently converted into rank.

App output, existing Showdown review decisions, portfolio entry assignments,
lineup downloads, portfolio exports, and imported submissions are recorded at
those actions. Export records include exact content and roster mappings; download
or export alone does not confirm submission. Standings imports retain a submission
snapshot and verify season/week against native contest-ID account history plus
saved schedule evidence when available. Conflicts are rejected, and absent date
proof is marked missing.

Additional explicit app/AI/user recommendations can be recorded with
`POST /api/optimizer/results/{job_id}/evaluation-recommendations`, using `actor`,
`source_reference`, and `candidate_ids`. Optional `assignments` require a
recommended candidate plus native `contest_id` and `entry_id`; any supplied
`lineup_id` must match. Repeated identical requests reuse the content-addressed
record. Server recording time is authoritative. Recommendation assignments
received after the saved lock, or without lock proof, cannot establish prelock
execution intent. Read complete evidence through
`GET /api/evaluation-records/{record_id}`; compact learning reports link ledger
record IDs rather than embedding all candidate inputs.

Execution diagnostics compare the recorded intended roster with the submitted
roster for the **same contest and entry**, using canonical identity and Captain
slot. Without intent, execution is unassessable. A higher score in another saved
lineup is a **hindsight gap**, evaluated separately for each contest. An exact
submitted-roster match to an unsaved candidate proves candidate lineage only;
it does not create a saved lineup, export, or recommendation.

For evidence-only historical repair, use:

```sh
.venv/bin/python scripts/product/repair_evaluation_records.py \
  --season 2026 --week 5 --entry-user wones0120 \
  --output artifacts/week5_evaluation_repair --apply
```

Omit `--apply` for a dry run. `--reviews PATH` optionally accepts an operator-reviewed
JSON list linking retained conversation files to unique run prefixes and saved
lineup numbers. Conditional reviews remain conditional. The command preserves
source archives, appends identity resolutions, corrects proven contest scope,
recovers original candidate lineage and regenerates reports from saved actuals.
It does not rerun optimization or fetch current projections. Missing final intent,
export receipts, account fees/winnings, or timing evidence remain explicit.
