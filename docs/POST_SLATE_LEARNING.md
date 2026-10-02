# Post-slate learning reports

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

Select **Download report for ChatGPT** after building a week report to save a
Markdown file locally. The file includes week and slate summaries, entry and
player comparisons, the captain 1.5 scoring explanation, evidence gaps, and
the complete structured report JSON. Upload it to ChatGPT yourself for deeper
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
The structured report also evaluates every other completed run on the slate
with a complete saved pool. `run_scope` separates those research runs from
entry-linked decisions; completed runs without a saved pool are listed as
unavailable. The concise week table uses entry-linked decisions.
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
