# Classic Large-GPP live source readiness

Weekly contest-result imports now accept custom slate identifiers such as `SUNDAY_LATE_SF_SEA`, allowing those results into week learning reports. Custom salary filenames participate in scope checks; an explicitly selected custom folder is not mistaken for its Sunday Late prefix. Conflicting saved contest scope and ambiguous salary evidence remain checked.

The Slate menu now discovers imported DraftKings salary slates for the selected season/week directly from the server, even without a saved contest or browser custom-name entry. Imported data does not by itself certify readiness.

The custom slate name field uses the standard readable dark-theme text styling. Use **Add a custom slate** in Slate files to select a separate game such as `SUNDAY_LATE_SF_SEA`. Custom names stay in the Slate menu for that season/week in this browser. Then select **Captain GPP** for CPT/FLEX salaries, load the actual salary CSV, prepare inputs, and run. Creating a name does not import data or establish readiness.

Canonical QB roles now resolve the latest team starter across all salary QBs. A newer starter observation supersedes an older retained assignment, including evidence shared from Sunday Main to Early/Late. Original source clocks and IDs remain auditable; conflicting same-time reports and future evidence cannot establish a starter.

**Strategy** defaults to Classic GPP for Sunday Main, Sunday Early and Sunday Late, and Captain GPP for Thursday Night, Sunday Morning, Sunday Night and Monday Night. The default applies on app startup and when switching slates. Manual strategy selection remains available; lineup controls retain their saved values. Sunday Morning restores Captain by default so its CPT/FLEX salary pool is not assessed as Classic after a reload or slate switch. Other slates retain the Classic default. Existing saved runs remain available after lock; new pregame preparation is still blocked.

**Exclude questionable (Q) players** now defaults on in both Classic and Captain. You can turn it off independently per format during the session. This controls lineup eligibility only; preparation does not treat those players as out or alter their projections.

Preflight now uses the same currently verified preparation as **Run Optimizer**. A ready prepared build shows its exact projection run instead of a contradictory older general source report; changed inputs, failed preparation and expired evidence still block through the existing preparation checks.

## Current sportsbook source

Classic and Captain preparation fetch DraftKings lines through ESPN's public NFL scoreboard. No API key is required. The collector matches canonical home/away teams and kickoff (within 60 seconds), checks regular-season/week scope and pregame state, and requires two-sided current spreads and matching over/under totals for every selected game. Opening lines are never substituted. Sunday Main, Early, Late and Captain use their own salary-derived game scope.

The existing immutable market snapshot path stores the full response, retrieval clock, ESPN event ID and sportsbook attribution. Projections must consume those exact normalized snapshot IDs. A failed refresh blocks the new preparation; there is no silent fallback to nflverse or old market rows. Existing six-hour maximum observation-age checks still apply at optimization. A new preparation refreshes the feed again.

ESPN's response does not expose a sportsbook quote-update timestamp. Retrieval freshness therefore means the app just fetched ESPN's displayed lines, not that their exact upstream age is certified. This public endpoint can change or become unavailable; coverage/schema failures are surfaced as preparation errors. The legacy `scripts/capture_nflverse_markets.py` remains available for research; application preparation explicitly passes `--provider espn`. A read-only live check is:

```bash
PYTHONPATH=. .venv/bin/python scripts/capture_nflverse_markets.py --season 2026 --week 5 --slate SUNDAY_MAIN --provider espn --dry-run
```


Normal live Classic and Showdown requests use a durable upstream
`POST /api/slate/preparation/jobs` action `prepare` with explicit `contest_format`.
**Prepare slate for optimization** repairs identities, refreshes sources, rebuilds
verified projections and ownership, and evaluates the exact resulting runs. A
failed attempt keeps source checks in its checkpoint and supersedes older builds.

**Run Optimizer** supplies `projection_run_id` and `params.prepared_input_job_id`.
The API, worker and direct service validate persisted preparation rather than
trusting client readiness claims. The optimizer never invokes source refresh.
Repeated solves reuse the prepared inputs; source changes, failed/newer preparation,
expired evidence, lock, or changed availability assumptions require preparation
again. User exclusions and lineup preferences remain selection-only.

The weekly workflow executes the same durable preparation job inside its existing
readiness stage, with worker heartbeats and persisted source checks. Its prediction
stage selects that prepared projection, and optimization receives the prepared job ID.

Source checks run before enqueue and again on worker execution. Generation still
freezes exact evidence and solver inputs, and revalidates preparation on completion.
Final entry clearance remains separate from data readiness. Internal historical
preview paths retain their explicit incomplete-evidence contract.

Every required refresh stage must complete even when cached rows independently
pass freshness checks. Failures retain `<stage>_refresh_failed` and stop generation;
provider errors produce ERROR, unresolved evidence produces NOT_READY. The raw
injury CSV collector is informational because the current projection proof says
`injury_csv_consumed=false`; official injury, roster and canonical context refreshes
remain required. Every native salary row must have an assessment, including
quarantined identities omitted by the loaded pool.

The contract records season/week/slate, evaluation time, information cutoff,
kickoff window, required/optional checks, source row/run/snapshot IDs, independent
observation clocks and freshness results, affected canonical player IDs, exact
reason codes, and refresh outcomes. `classic_evidence_snapshot` stores the certified
generation pool, full `audited_salary_pool`, and canonical source manifest. `classic_final_input_proof` links it to
`classic_run_input_snapshot` and records final projection coverage. Persistence
failure blocks generation. A frozen interrupted run requires a new run ID;
reopening a completed run never refreshes or rewrites its historical evidence.

## Required sources

- **Salary:** one verified immutable canonical DraftKings import, source checksum,
  snapshot clocks or authenticated original import receipt clocks, verified native pool provenance,
  UUID identity, site ID, team/opponent, supported position, salary, eligibility,
  and canonical game/kickoff association. Positive salary alone cannot pass.
- **Projection:** completed same-scope feature/model/projection dependencies,
  verified consumption of the canonical salary/market/context source selection,
  complete mean/P90 and feature inputs for every usable player, model lineage,
  current information cutoff and creation timestamp. Derivation can occur after
  its information cutoff; future input evidence cannot.
- **Availability and roles:** current affirmative canonical source evidence.
  Missing or conflicting evidence stays UNKNOWN. Material or unassessable
  uncertainty blocks; fresh sourced existing role exclusions can quarantine it. Available,
  questionable/elevated, doubtful, unavailable and unresolved remain distinct.
  Unavailable players remain audited and need no projection. Expected starters
  require sourced role evidence; a default availability probability never clears
  the gate. Explicit game-active/inactive evidence is tracked separately from
  roster membership and practice reports. Final entry clearance is separate.
- **Questionable usage:** a fresh, cutoff-safe FULL/LIMITED/DNP practice observation is required unless affirmative final game-active evidence exists. A missing workload forecast stays explicitly unconfirmed in the risk assessment (`evidence_gap=true`, `questionable_elevated`); it does not manufacture normal workload or clearance. If a workload forecast is supplied, its clock must also be present, fresh and cutoff-safe. Existing risk limits and the user's questionable-player selection preference remain unchanged.
- **Markets:** sourced spread and total for every native slate game,
  matching canonical game identity, source snapshot, original observation and
  ingestion clocks, and correctly derived team implied totals. Zero spread is
  valid; absent markets with neutral numeric defaults are not. Provider capture
  freshness is checked; unavailable sportsbook quote publication time remains
  explicitly UNKNOWN, without being described as verified quote currency.
- **Ownership:** the live Large-GPP path rebuilds ownership from the same new
  projection and cutoff, limited to players actually scored by that new run.
  The saved ownership lineage must name that projection. Missing or stale ownership blocks instead of silently
  changing to the strategy's projection-only weight configuration. A failed
  projection build cannot trigger ownership fallback to an older projection.

Defaults use the existing six-hour market fresh band, 24-hour projection,
availability/role and ownership windows, and the weekly 168-hour salary lifecycle.
They are independently configurable with `CLASSIC_*_MAX_AGE_HOURS`; these are data
policies, not strategy parameters. All source clocks must be visible by cutoff
and evaluation, and the pregame path blocks after the first slate kickoff.

## Refresh and operator recovery

Run Optimizer reuses canonical salary identity repair/import, market capture,
weekly roster, injury, official NFL report, starter, depth/context, training label,
feature/projection and ownership services. It then re-reads persisted canonical
inputs and verifies their actual projection consumption. Source failures remain
observable and never manufacture fresh observations. A partial official weekly
report retains its observed Classic players and explicitly reports missing teams;
missing teams and blank game designations never become ACTIVE. Showdown retains
its complete-team collector requirement.

The application has an existing **file-based DraftKings salary importer**, not an
automatic DraftKings download connector. Refresh validates the original file
against its import SHA256, complete immutable raw rows, normalized curated rows,
native row IDs, counts and original import timestamps. It does not replay an
import or create a snapshot/observation clock. A valid legacy import can use its
original receipt clocks without a newer snapshot; these are labeled
`original_import_receipt_clock`, with provider observation/publication unknown.
A missing native draft-group ID does not block generation when the original CSV is authenticated against the stored checksum and every existing identity/game check passes. Candidate native player IDs must exactly match their source rows. Without authenticated original provenance, `salary_native_draft_group_missing` still blocks. A group ID is never inferred or invented; contest-entry compatibility is separate. A verified
existing file does not need a replacement upload. Hash/row/clock failures retain
their exact reason codes. Importing an unchanged file cannot renew its clock.

## Certified pool and quarantine

`pool_populations` reports native salary rows, canonically resolved salary rows,
confirmed unavailable players, role-ineligible players, unresolved blocking
players, explicit quarantines and certified generation-eligible players. Row
counts and player disposition counts are named separately. Projection and
ownership coverage use `certified_generation_pool`; unresolved evidence remains
independently blocking and quarantines remain visible with their source proof.

`quarantined_unresolved_evidence` preserves unknown football status and missing
facts. It requires fresh, cutoff-safe, unambiguous proof of an **existing**
unsupported non-scoring specialist role or backup QB without a sourced expected
package. It does not use price, names, point-estimate floors or user exclusions.
Backup RB/WR/TE roles can be material and cannot authorize quarantine. Stale,
conflicting, missing role evidence or an expected QB package keeps NOT_READY.
The projection builder independently applies the same proof before looking up
features. The frozen solver pool includes only certified IDs, while the full
salary assessment/source facts remain available for audit.

Quarantine is recomputed each build from fresh facts. No saved exclusion feeds a
future assessment: new roster, role, package, injury or final-active evidence can
restore eligibility or create a material blocker. Official club roster/depth
tables supplement missing canonical evidence via native profile IDs or unique
team/position/canonical-name matches, preserving HTTP cache, observation and
receipt clocks. Absence from a table is never an unavailable fact. Official NFL
blank game designations are normal before final reports and remain distinct from
missing independent roster/role or questionable usage evidence. A missing team's
injury rows do not establish ACTIVE or automatically invalidate corroborated
baseline availability. Final inactive/entry clearance remains separate.

Refresh Status is read-only and assesses saved inputs with the same contract.
Classic Large GPP preflight says **Blocked — source refresh required**,
**Blocked — evidence check failed**, **Unverified — readiness required**, or
**Ready for generation**. Generic coverage scores do not certify generation.
Other Classic strategies retain their existing gates and strategy behavior.

## October 9 overblocking repair verification

New optimizer `5e51be99-6567-4e85-b1ea-992a475f5eac` remains **NOT_READY**;
the prior `3e332175-5321-4e4b-a7e6-b89d941ef621` record is unchanged. All 587
native rows were assessed: 582 canonical identities, 213 unavailable, 44
role-ineligible, 53 unresolved blockers, zero unresolved football quarantines,
and 277 certified generation-eligible players. Projection/ownership coverage is
**0/277**, with no saved-run fallback; all **11/11 markets** passed.

Official roster/depth evidence resolved five original cases: Tinsley, Ogletree
and Meeks retain potentially material active-roster backup roles; Miller and
Nichols have explicit practice-squad evidence. Smith-Marsette remains unknown.
River Cracraft also lacks current role evidence, and 47 Q cases retain missing
practice/workload requirements. The original salary file/hash/raw/curated rows
are authenticated without reimport, but its native draft-group ID and five
salary identities remain unresolved. No evidence was frozen and no solver ran.
The repair passed 342 backend tests, six UI checks and the production UI build.
See [the complete repair audit](../../CLASSIC_GPP_READINESS_OVERBLOCKING_REPAIR.md)
for exact player facts, source clocks, populations and recovery actions.

## Weather decision

Weather is `NOT_REQUIRED_BY_CURRENT_MODEL`. The current Classic projection and
ceiling inputs, ownership design, optimizer player-context adjustment,
correlation/format objective, and eligibility code have no material weather
consumer. Merely capturing weather or showing it in a saved-input report does
not create a scoring dependency. No weather collector runs for this gate and
weather cannot block READY. A future material weather feature must update this
contract and its tests before being used in production.
A lineage proof claiming material weather consumption without that source
contract fails closed with `material_weather_evidence_unverified`.

## Generation versus entry clearance

READY certifies baseline generation inputs. It does not certify final inactives,
contest assignment, submission, calibration promotion, or strategy quality. New
live reports show generation readiness separately from entry readiness and use
`ENTRY_CLEARANCE_PENDING` when only entry checks remain. Informational weather
and unknown quote publication clocks are described honestly. Archived baseline
reports retain their original DEVELOPMENT_PREVIEW status. The only bypass is an
explicit internal/offline `allow_incomplete_evidence=True` preview; public JSON
cannot supply it or a frozen readiness proof. It never establishes READY.

New preview decisions retain exact source blockers, `source_status`,
`override_used=true` and `solver_called`. Normal decisions record these flags and
the frozen evidence timestamp, optimizer snapshot ID and SHA256. The effective
strategy contract is also persisted before the first candidate invocation.
Reports display this information first and suppress production lineup sections
for NOT_READY or ERROR normal runs.

## Diagnostic correlation audit

Baseline optimizer `7f1a28a6-a8fe-4718-a199-c66eb91c35b1` and preparation
`2ad26207-f314-4274-9fbb-391758e93158` are preserved in
`artifacts/classic_live_pipeline_integrity/`. Its 136 frozen solver rows represented
11 games and had no market evidence. The new source contract rejects that case
before generation, even though mean/P90 and ownership coverage were complete.

The saved effective weights were projection 0.35, ceiling 0.45, leverage 0.05,
correlation 0.15, with correlation bonus 1.0. The audit constructed the actual ILP
without solving and verified all 64 pair coefficients equal
`0.15 × rule adjustment`. A diagnostic zero-correlation model had the same
feasible region and a different objective. There were also 42 format terms.
All 64 pair terms were defensive/opponent penalties; missing markets suppressed
positive environment-dependent QB/pass-catcher and bring-back terms. The five
saved lineups had zero realized correlation contribution, which does not imply
that the objective omitted the configured penalties.

Large GPP uses sequential exposure-aware ILPs: accepted candidates form the
portfolio. It has no separate portfolio reranking objective. Stack templates,
overlap, exposure, primary-game and team/game caps remain constraints. No weights,
thresholds, templates or caps were tuned in this repair. See
`correlation_audit.json` and its reproducible read-only audit script for actual
coefficients and per-lineup scoring.

`precompute_correlation_terms=false` constructs the same pair and format terms
inside each `_build_lineup`; it does not disable correlation or skip preparation.
New solver steps include `objective_components`, also saved on each lineup as
`lineup_objective_components`. Projection, ceiling and leverage use full-pool
normalization; context is separated from those adjusted values. Correlation
includes pair, format and extra-stack adjustments. Their sum must reconcile with
the actual solver objective within `rel_tol=1e-9, abs_tol=1e-7`, before any control
comparison can change solver variable values. Stack/exposure constraints remain
separate from soft objective terms. The report renders the actual contribution.

## Earlier live verification

The final normal verification retained the baseline controls (5 entries, 80%
exposure, overlap 5, team 4, game 5, primary game 3, single TE off, DEN opponent
exclusion). Optimizer `25d3223b-0066-49e7-b5d1-24d6ac89b631`, queued job
`2c61cdf9-d006-4e5e-9eb0-9286f94b46c5`, refreshed all **11/11 markets** and
generated **zero candidates or lineups**, with terminal readiness **NOT_READY**:
projections correctly refused six players with no affirmative current roster or
role evidence: Mitch Tinsley, Ihmir Smith-Marsette, Drew Ogletree, Scotty Miller,
Lew Nichols and Jackson Meeks. Five additional salary identities remain
quarantined (three unmatched and two ambiguous). The legacy salary import also
lacks native snapshot/draft-group provenance. The official collector retained
249 observed rows with blank game designations and reported ARI as absent;
neither blank designations nor an absent team establish ACTIVE. Ownership did
not fall back to an older projection after the new build was blocked.

Those are required source repairs; the gate does not invent availability,
identity mappings or a draft-group ID. Source reports and the failed run are
saved alongside the immutable diagnostic baseline. READY-path tests use a
complete synthetic evidence fixture and the real ILP, through the public queued
API and durable worker. They prove both evidence freezes precede generation;
they do not establish that the current live slate is READY. The final checks
passed 350 backend tests, 18 UI tests and the production UI build.

For live Large GPP, the Q exclusion checkbox affects eligibility. An explicit
Assume Out scenario remains a separate projection input; excluding Q players
alone does not assert an injury fact or redistribute football opportunity.

Preflight source loading no longer copies the entire canonical source-audit
payload on every dataframe operation. A same-scope local measurement improved
from about 72 seconds to 10 seconds without changing source facts or scoring.

## Completion verification

The latest unchanged-control Week 5 run is optimizer
`3e332175-5321-4e4b-a7e6-b89d941ef621`, queue
`1e2340b7-6aae-4114-8c16-2388bab4959b`. It refreshed 11/11 markets and correctly
returned NOT_READY with solver called **no**, override **no** and zero production
lineups. Salary provenance/identity, current availability and questionable usage
context remain unresolved; projection/ownership rebuilding could not complete.
The original five-lineup run and preparation are unchanged.

The completion checks passed 476 broader Classic/optimizer tests with four
documented pre-existing assertions deselected, 20 UI/report tests, and the UI
production build. See [the complete readiness and correlation audit](../../CLASSIC_GPP_DATA_READINESS_AND_CORRELATION_AUDIT.md)
for exact blockers, validation limits, files and normal commands. Its exported
NOT_READY HTML report is saved in `artifacts/classic_live_pipeline_integrity/completion/`.

## Upstream roster disposition recovery

Current nflverse `CUT` evidence means unavailable for that team, per the
[nflverse roster-status dictionary](https://nflreadr.nflverse.com/articles/dictionary_roster_status.html).
Unknown/ambiguous statuses remain unresolved. Current official club roster/depth
facts take priority; absent unresolved players can be supplemented from the
club's current-year transaction register. Only explicit latest release, IR or
practice-squad dispositions are used. A newer unparsed/positive event or conflicting
same-day events prevents reusing an older exclusion. Positive transaction text
never establishes current active status or game-day clearance.

The immutable capture retains the complete register, source URI, HTTP observation
clock, receipt time, original event date and transaction text. The current register
observation and historical event date are separate fields. Resolution still requires
team, position and canonical identity; no player-specific overrides are added.

## Upstream status reporting

Operations separates **Load files**, **Prepare slate**, and **Optimize**. Imported rows are not labeled usable merely because storage succeeded. Unresolved counts appear beside the upload, and current unresolved salary identities remain visible after reloading the page. Projection cards with unresolved salary records say **Completed with warnings** and direct users to preparation. A failed saved preparation is labeled as a prior attempt; changed inputs require a new assessment. These UI changes do not waive unresolved identities or unavailable source facts.

Live preparation builds current-slate features before auditing historical labels because the audit loads canonical inputs for the selected slate. Historical repairs finish before the projection cutoff is frozen. Audit failure stops the projection stage instead of leaving a failed preliminary check alongside a successful later projection.

The earlier October 9 follow-up live check was **not ready**: five unresolved salary identities and player availability/usage evidence gaps remained. `artifacts/upstream_optimization/readiness_followup_audit.json` preserves that failed attempt. The shared-resolver verification below supersedes that result.

## Shared identity resolution and canonical ownership inputs

Imports and preparation call `backend.app.services.matching.find_player_master_id`. Source-native mappings take precedence, followed by scoped aliases and normalized team/position/name evidence. Accent, punctuation and suffix variants use sourced aliases before master rows. Conflicting vendor aliases remain ambiguous unless at least two roster-identity source systems corroborate one candidate and none supports a competing candidate. Salary labels never overwrite canonical football positions. Preparation saves newly resolved source aliases and closes the corresponding open ingest queue entries.

The exact nickname `Hollywood Brown` also supplies `Marquise Brown` name evidence through `Database.player_identity._name_keys`. This lets current roster aliases corroborate the canonical identity when legacy vendor aliases point to duplicate nickname masters. It does not allow substring nickname matching or bypass team/position and conflict checks. Existing native source-ID mappings retain precedence; historical resolved salaries and player masters are not rewritten by unresolved-salary reconciliation.

Preparation refreshes roster identities, reconciles salaries, and stops on unresolved identities before feature/projection/ownership builds. Direct projections also reject unresolved salaries. Ownership for an explicit projection reads current canonical salaries with original cutoff-safe import clocks; historical ownership training keeps its historical salary snapshots. NFL.com's `AZ` abbreviation normalizes to `ARI`, preserving Arizona's current practice evidence.

Verified source snapshots and the five saved identity mappings are in `artifacts/shared_identity_pipeline/verified_identity_mappings.json`; the read-only replay of all 587 salary rows is recorded in `reimport_resolution_check.json`. No salary re-import was used to renew source clocks.

### October 9 live acceptance

For 2026 week 5 `SUNDAY_MAIN`, preparation `6aeb3b8e-a165-4a01-8afb-c0d8511ce3bc` completed **READY**, with zero blockers. Projection `2df98875-02f3-45ab-91c1-06f50664b89c` and ownership `30cae7c0-b6c8-4c68-b5f9-c94e9fed730c` include the repaired canonical inputs. Cash optimization `c2fea93c-28c4-4ab9-ada7-c1843b15e1b8` selected five legal lineups from 120 candidates, with questionable players excluded and no readiness override. Salary totals were $49,900–$50,000.

The acceptance script and saved requests/results are in `artifacts/shared_identity_pipeline/`. It checks canonical identities and original DraftKings IDs/salaries, legal roster composition, team/game caps, questionable exclusions, unchanged projection/ownership IDs and source run counts. The targeted regression suite passed 278 tests. Preparation readiness remains distinct from final game-day clearance; missing workload forecasts retain elevated uncertainty and never imply full workload.

Repeat optimization `a758712d-08a7-4650-b863-573f9555a6f7` also selected five legal lineups from 120 candidates using that same prepared build. `artifacts/shared_identity_pipeline/acceptance_report.json` records **PASS** for both runs. Source snapshot, ingest, projection and ownership run counts remained unchanged across both optimizations. Neither run used a readiness override.


## Restored GPP defaults

Normal Operations runs submit `classic_large_gpp_v1` / `gpp` for Classic and `showdown_gpp_portfolio_v3` / `gpp` for Captain/Showdown. New lineup controls default to five; saved counts and user constraints remain intact. Weekly API omission selects the same tournament strategies and five lineups. Explicit historical Cash requests and saved results retain their original semantics.

The main preparation action explicitly requires ownership. The optimizer consumes the resulting prepared build and preserves the upstream source gate. Earlier Cash acceptance above verifies source integrity only; it is not tournament-strategy validation. Actual GPP verification artifacts are saved separately in `artifacts/gpp_default_verification/`.

Live GPP acceptance passed for 2026 week 5 `SUNDAY_MAIN`: preparation `454b1f4d-e6a4-4d75-ac42-7f637e18a149` completed READY, followed by optimization `22dd1841-a95d-4213-8041-ad80dd93e9a9` using `classic_large_gpp_v1`, `objective=gpp`, and the `large_gpp_portfolio` engine. It generated five distinct legal tournament lineups. Independent checks passed for salary/native identities, prepared projection and ownership lineage, QB stacks, team/game limits, single TE, DST opponent avoidance, questionable exclusion and the effective seven-player maximum overlap. Source/ingest/projection/ownership run counts did not change during optimization. See `artifacts/gpp_default_verification/acceptance_report.json` and `five_gpp_lineups.md`. Validation: 73 targeted backend tests, 16 targeted UI tests, production build and browser request/layout checks passed.


The disabled Run Optimizer button now has an adjacent live status describing the saved-readiness check, active preparation job, pending action, failed check/retry, lock, or required preparation. Loading uses an indeterminate progress indicator, not an invented percentage. The initial check does not rebuild sources; readiness gates remain unchanged.


Optimizer queue submission checks the saved prepared build, scope and availability scenario before returning its durable receipt. Current source hashing, artifact verification, projection lineage and readiness checks run on the worker before generation, with an input-validation progress stage. Enqueue does not issue trusted evidence. A lost receipt retries the identical run ID once; the queue returns the existing job. Regression coverage ensures expensive audits never run before the receipt and modified dependencies still fail the worker without invoking the solver.

## Native status refresh and roster transfers

Classic preparation captures the public DraftKings lobby and current draftables
response. It selects Classic groups by kickoff and game count, then requires the
full away/home/kickoff set and every imported native draftable ID to match exactly.
Only explicit unavailable statuses supplement player context. Blank, unknown,
questionable or active labels do not certify availability or clear an older OUT.
HTTP observation/cache age and receipt clocks, both source snapshots and the native
ID remain attached to each fact. Source failure falls back to existing evidence;
unresolved players still block preparation. This does not replace salary imports.

Current nflverse EXE and the official Commissioner Exempt roster section map to
unavailable. A unique native-ID assignment to another team's active roster records
an exclusion for the old salary-file team. Conflicting assignments, positional
mismatches, future evidence or ambiguous aliases cannot establish a transfer.
A changed native DraftKings team/position is reported rather than silently updating
the salary row; a corrected salary import is needed to select that player for the
new team. No player names or specific slate IDs are hardcoded.

When combining status and practice evidence, the derived context observation covers
the latest retained fact. Each fact keeps its original freshness clock; evidence
after the preparation cutoff still fails validation.

Preparation status filters job history by slate in SQL and loads only job metadata
unless the current build or a failed checkpoint is needed. The UI receives a compact
build/consumption summary and links to full saved job audits. Validation still reads
the full persisted manifest and readiness evidence; saved audit records are unchanged.

## Shared Sunday injury evidence

Sunday Early and Sunday Late consume their own injury evidence plus the same
season/week's Sunday Main injury import. The app defaults their injury filename
to `FanDuel_injuries_<season>_<week>_SUNDAY_MAIN.csv` and loads it under Main.
No separate Early/Late injury file or duplicate import is required. Salary files
and model/optimizer runs remain scoped to the selected slate.

Canonical IDs and salary-team membership restrict inherited rows; unresolved
identities remain visible only for teams in the selected subset. Projection,
optimizer and simulation injury lookups retain their decision-cutoff checks.
Shared rows retain their original source slate, ingest IDs and observation clocks;
reading them for another slate never makes stale evidence fresh. The load-age
indicator recognizes both DraftKings and FanDuel injury imports. Captain slates
do not inherit Sunday Main injury evidence.

Sunday subsets also reuse Main’s original canonical player source facts (including depth-chart roles), filtered by canonical player ID, team and position. Derived Main projections and workload assessments are not copied. Original observation and receipt timestamps remain unchanged, so stale or future facts cannot satisfy current readiness.

## Sunday Morning scope

`SUNDAY_MORNING` is a separate built-in slate option, including weekly contest-folder discovery and persisted run selection. It does not inherit Sunday Main injury evidence. For single-game CPT/FLEX salaries, use Captain format and the actual file path even when the filename has a different label. The selected scope and native salary game identities determine preparation; the label alone does not certify a slate.

A separate Morning injury CSV is not a prerequisite for the existing **Prepare slate** source refresh: it collects roster, official injury and canonical player-context evidence. Missing or stale coverage remains a blocker, and final active status is not inferred from a blank salary status. This menu addition does not certify a new live Morning preparation or change existing user controls.

## Favored-team position preferences

Classic controls `force_favored_qb`, `force_favored_rb`, `force_favored_wr`, `force_favored_te`, and `force_favored_dst` accept booleans or 0/1. The UI defaults RB/TE/DST on and QB/WR off, with a one-time saved-settings migration; subsequent overrides persist. Omitted API controls remain off for compatibility with existing callers. They apply to every player at each selected natural position, including FLEX. Eligibility requires finite `team_spread_line < 0` from prepared inputs; pick’em and missing/invalid spreads are excluded. Home-team status is not used as a substitute.

Filtering occurs after the model evidence snapshot and records `user_favored_team_<position>` exclusions. Final lineup validation enforces the same requirement. Locks conflicting with the filter fail explicitly; the optimizer never relaxes it. The options persist in Classic UI settings and are omitted from Captain requests. No market, projection, ownership or historical labels are altered. A changed forecast requires preparation again, not a preference toggle.

## Mandatory market readiness

Preparation and optimizer revalidation already require sourced spread/game-total coverage for every Classic game and both Captain teams, internally consistent team implied totals, and observations within `classic_market_max_age_hours` / `showdown_market_max_age_hours` (both default six hours). The preparation UI now states this requirement explicitly. Missing, stale, future or inconsistent evidence blocks optimization. This uses provider observation/capture clocks, not verified upstream sportsbook quote publication time. Moneyline prices and betting juice are not required inputs in the current model; they are not certified by READY.
