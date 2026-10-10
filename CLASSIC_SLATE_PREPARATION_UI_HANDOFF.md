# Classic slate preparation UI handoff

Operations → **Preparation and data tools** → Data + feature build → **Prepare slate inputs** now offers:

- **Import DraftKings salary evidence**: enter the Salary file path under **Slate files** above and confirm its native draft-group ID. Uses existing immutable capture and canonical ingest, rather than the legacy Raw loader tables.
- **Import injury CSV evidence**: enter the Injury file path and select its supported DraftKings/FanDuel source.
- **Load sourced pregame evidence**: manual JSON through the existing pregame-context API, with canonical player IDs, source URL and original observation time. Keep designation, practice, workload and starter evidence distinct.
- **Review starting-QB evidence**: existing starter loader and candidate-resolution controls; ambiguous teams require sourced operator review.
- **Capture nflverse markets** and **Capture current weather**: durable jobs invoke the established collectors with their actual interfaces and server-derived canonical games/lock. Weather retains existing venue/roof applicability and access terms; keyless local evaluation requires the displayed acknowledgment.
- **Rebuild slate features and projections**: durable orchestration through the normal feature and projection handlers. **Reload preparation status** and **Reload projection list** perform reads only.

Status shows source clocks separately from import/capture clocks, coverage, unresolved identities, existing import-age/market/weather freshness, current consumption, jobs, errors, checksums and next steps. Failed first imports remain visible even when no usable salary scope exists. New market capture bypasses the nflreadpy cache; unchanged values may be newly observed. `capture_clock` never becomes a verified sportsbook quote-publication time.

Dependency evidence is persisted in the preparation job and its newly allocated `feature_generation_run.source_versions_json`; existing model/projection IDs link the consumed immutable scoring frame. Actual salary IDs, market IDs, pregame context IDs and starter IDs are compared with the intended inputs. Source and projection-lineage SHA256 checks run again at optimizer enqueue and worker execution. Running/failed/newer preparation, changed sources or availability choices, mixed salary imports, mismatched/older projections and passed lock block reuse. Explicit cutoff preserves time safety; stale prior-week training labels require a separate normal feature rebuild, never current-week realized labels.

**Preparation never generates or selects lineups.** For Classic Large GPP, **Run Optimizer** now queues and waits for a fresh preparation rebuild with the selected availability scenario, verifies it, and uses that exact prepared projection ID with current user-selected constraints. Its existing optional ownership action follows verification. Other strategy paths retain their existing rebuild behavior. Saved-input validation remains read-only and separate from new evidence. Reference run `1fdbb3c7-53a4-42c3-a277-c56db54c783c` and its readiness were not overwritten.

Remaining manual/unsupported steps: correct DraftKings download/draft-group confirmation; supported injury CSV or sourced pregame JSON; unresolved identity and QB review. Injury CSV imports do not automatically enter canonical pregame context. Final official game clearance remains unverified. Upstream quote publication and salary publication freshness remain unknown. Weather capture is inspectable evidence but is **not consumed by projections**; no coefficients or scoring policy changed. Contest assignment and entry submission verification remain outside preparation.

User sequence for an **unlocked** target: import/review evidence → capture markets/weather → resolve errors → inspect evidence and remaining limitations → expand **Optimizer options** and confirm **Classic Large GPP / 5 entries / 80% / primary game 3 / overlap 5 / team 3 / game 5 / single TE off**, preserving all exclusions, locks and risk choices → initiate Run Optimizer. These are user choices, not defaults; preparation never changes team cap 4 to 3.

Live read-only check on October 4 at **1:36 p.m. Eastern** found Sunday Main's first lock at **1:00 p.m.**: new pregame preparation is blocked for that slate. Use existing late-swap protections for locked entries; do not backdate inputs. No live capture/import/rebuild, user optimization, portfolio replacement or submission was executed.

Acceptance: 43 focused backend checks, 84 frontend checks and TypeScript/Vite build; real App → API → durable queue/worker → isolated SQLite persistence/reopen/browser acceptance. Source/model I/O is deterministic fixture data; the production orchestrator and dependency checks run normally. Fixture acceptance establishes implementation behavior, **not live Sunday freshness or entry clearance**. Local API and worker were reloaded only after zero queued/running jobs and optimizer records; new live GET routes passed. Browser evidence: `artifacts/slate_preparation_fixture/`.

Sunday Night projection follow-up: Week 4 CAR/DET canonical salaries were present,
but the starter gate incorrectly applied Sunday Main's loaded roster coverage to
every team that week. Both starter resolution and canonical projection inputs now
scope that gate to the player's canonical team. Covered teams still require an
active canonical roster match; uncovered teams remain unknown and are recorded
in projection input metadata. A read-only query finds all six Sunday Night QB
candidates. The 64 focused starter, projection-input, job-repair, pipeline and
preparation checks pass. Existing failed attempts remain saved history; the user
must initiate a new projection run to obtain a new result.

The separate failed Sunday Night injury preparation job reflects missing
canonical schedule coverage: no Week 4 CAR/DET row exists in `raw_nfl_schedule`.
Preparation needs that schedule and its kickoff before its prelock checks can
pass. Zero saved pregame-context records remain a source-evidence gap. Neither
gap was filled or marked ready by the roster-scope correction.

## Basic path and configuration

Operations puts **Slate files** and **Portfolio optimizer** first. Load the downloaded
salary and injury CSVs using their local paths, choose format, strategy and lineup
count, then click **Run Optimizer**. Existing loaded rows are shown for the selected
slate. Basic loading uses the existing canonical DraftKings salary and FanDuel injury
endpoints; it does not manufacture native draft-group provenance, sourced pregame
availability, quote publication times, or final entry clearance.

**Optimizer options** keeps all existing exposure, construction, Captain, player,
contest and diagnostic controls available. Closed sections retain their values and
remain mounted for submission validation. Readiness, pending progress and run errors
stay beside **Run Optimizer**. Both automatic preparation paths first apply the existing
salary identity reconciler after prelock verification and pending imports complete.
Supported matches resolve; remaining rows retain explicit exclusion/review records.
The new prepared snapshot is taken only after this step succeeds. Preflight names
unresolved players instead of showing only a count. The automatic Classic Large GPP rebuild preserves
its existing questionable-player scenario semantics; Showdown keeps Q exclusions
as lineup preferences and explicit availability overrides as independent assumptions.

Markets, weather and manual evidence imports remain explicit actions in
**Preparation and data tools**. Automatic rebuilding uses stored evidence and does
not refresh its original observation time. Genuine identity, source and lock failures
still stop a run. The UI improvement neither changes scoring nor submits entries.

Validation uses `ui/tests/slatePreparation.e2e.mjs` and
`ui/tests/sundayShowdownHandoff.e2e.mjs` with synthetic sources, an in-memory SQLite
fixture and a durable worker. The tests validate the pinned optimizer enqueue without
executing a solver or touching live app data. Desktop/mobile evidence for the basic
workflow is under `artifacts/basic_optimizer_workflow/`.

Format changes retain the optimizer form's scroll position. Compatible saved reports
may restore in Run activity, but only an explicit **Open results** / **Reopen results**
action scrolls to them. `ui/tests/optimizerNavigation.e2e.mjs` verifies both formats
using synthetic saved reports with all API writes and external traffic blocked.
