# Automatic GPP shadow outcome tracking

Learning now includes **GPP shadow comparisons**. The registered 2026 Week 5
Sunday Main live/control and workload-shadow recommendations are frozen before
kickoff and currently show **pending actuals**. No live selection is changed.

## Operation

Successful normalized contest-standings imports and entry-history imports refresh
registered comparisons. The Learning card polls saved reports every 30 seconds;
**Retry comparison** reevaluates available evidence after a failed refresh or an
identity correction. Preview imports do not evaluate or save results. A duplicate
batch standings file can bypass ingestion; use Retry comparison in that case.

The application does not download account results, watch the CSV path, or run a
new timer after games. Import the usual standings and account-history files; the
comparison itself no longer needs a separate request or manual research script.

Reports preserve:

- Canonical player actuals and source observation/file IDs, including conflicting
  evidence that prevents a resolved score.
- Frozen player and lineup projection errors, with Captain scoring applied once.
- Paid GPP finishes, non-paid finishes and unknown outcomes separately.
- Conservative rank/return bounds and top-percentile outcomes where supported.
- Evidence hashes and immutable versions when input evidence changes.

Missing actuals remain pending, never zero. Unverified/cash contests are excluded
from GPP comparisons. Incomplete fields, boundary ties and missing payout evidence
remain explicit. Paid-place counts from matching entry history can establish paid
cutoffs without a full payout ladder; counterfactual dollar returns require adequate
payout evidence. These comparisons do not claim that the shadow was entered or
that imported standings are final. Partial/in-progress exports remain provisional
and update on later imports. Related contests are not independent validation trials.

Neither rankings nor candidate generation is rerun after outcomes arrive. Reports
cannot promote a model or mutate live projections. The full workload evidence,
projection and generation results remain in [the experiment report](sunday_workload_shadow.md).

## Persistence and interfaces

Migration `0049_gpp_shadow_learning.sql` adds append-only
`target.gpp_shadow_experiment` and `target.gpp_shadow_report`. Exact repeated
registrations and unchanged evaluations do not duplicate data. Changed evidence
appends a report; returning to an earlier evidence state also appends a new current
version. A per-experiment transaction lock serializes concurrent refreshes.

- `GET /api/learning/shadow-comparisons?season=2026&week=5` reads saved reports.
- `POST /api/learning/shadow-comparisons/refresh?season=2026&week=5` retries evaluation.
- `scripts/register_gpp_shadow.py --experiment <experiment.json> --label <label>`
  explicitly registers reviewed research artifacts. It verifies contracts and
  portfolio audits, canonical roster membership and prelock timing. Registration
  itself must precede kickoff; the app does not silently scan arbitrary artifacts.
  This runner uses Classic strategy-contract artifacts. Captain outcome scoring is
  tested, but an equivalent Captain experiment-registration adapter is not included.

A failed automatic refresh does not undo an already committed import. Its error
is logged, and the import response reports the failure. The Learning retry exposes
errors directly. New experiments need explicit prelock registration; current live
optimizer runs are not automatically enrolled as shadow experiments.

## Sunday Main readiness and Captain audit

The app's current-input assessment returned **READY** for the saved Sunday Main
projection on October 10. This validates current source/freshness checks; repeat
normal prelock preparation if evidence changes. It is not a final injury clearance.
The live recommendation still matches its frozen pre-experiment record.

Captain's existing paths passed 117 focused checks across simulation,
Captain salary/scoring multipliers, lineup recommendation, export, readiness and
preferences. The earlier simulation gap is covered by persisted Captain/FLEX
simulation results and deterministic role handling. These simulations remain
independent-marginal diagnostics, not calibrated opponent-field cashing or expected
return estimates. Production selection still uses the provisional projection-first
recommendation, with unavailable paid-finish/return estimates explicit.

Only Thursday-night projections exist for Week 5 in the inspected saved inventory;
Sunday-night and Monday-night projections are not prepared. This audit therefore
does not certify a live end-to-end run for either upcoming slate. The next Captain
task is to prepare Sunday night through the shared app path, verify its native
salary pool and role evidence, and freeze a prospective baseline before testing
selection changes. No Captain live-selection weights were changed here.

## Validation and activation

- 56 targeted Python checks cover missing/conflicting actuals, Captain normalization,
  player forecast errors, cash exclusion, incomplete fields, boundary ties,
  registration timing, API scope and import-trigger behavior.
- Local PostgreSQL registration and repeated refreshes pass idempotency checks;
  a parameter-type ambiguity found during initial registration was fixed with
  explicit SQL casts before activation.
- UI build and desktop/mobile browser fixtures pass pending/result views,
  unavailable returns and refresh wiring. Mobile screenshots were inspected.
- Migration applied locally. API and worker activated after verifying no queued or
  running jobs; live endpoint returns the registered pending comparison.

Artifacts are in `artifacts/sunday_main_followthrough/`. Existing bundle-size and
Pandas future-behavior warnings do not block these checks.
