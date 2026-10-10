# Weekly Learning Memory Reduction TODO

## Purpose

Reduce the peak memory used while generating weekly post-slate learning reports
without losing reproducibility, canonical player identity, point-in-time safety,
or the ability to inspect the exact evidence behind a report.

The original Week 4 Sunday Main run provides the baseline: the loader selects 36
completed optimizer-run configurations for one slate. Those JSONB values total
about 212 MB in PostgreSQL storage, but expand into much larger Python objects.
The generated slate report serializes to about 20 MB. During generation, the API
process reached a 4.4 GB peak memory footprint and caused macOS swapping.

This is a processing and report-shape problem, not evidence that the optimizer
or projections themselves are incorrect.

## Guardrails

- Preserve the immutable saved candidate pools and the exact optimizer-run IDs
  used by learning calculations.
- Do not join player evidence by raw display name.
- Keep reports deterministic for identical persisted inputs and retain the
  existing point-in-time cutoff rules.
- Do not silently omit optimizer evidence. Any intentional scope reduction must
  be visible in the report with its reason and counts.
- Treat a changed report shape or storage representation as a versioned contract
  change, with a migration when persistence changes.

## Work Plan

| ID | Priority | Status | Work | Acceptance check |
| --- | --- | --- | --- | --- |
| LEARN-MEM-001 | P0 | Done | Add a repeatable memory benchmark for weekly learning generation. Capture peak RSS, serialized response bytes, selected optimizer-run count, total configuration bytes, candidate count, elapsed time, and swap/pageout deltas for the Week 4 Sunday Main fixture or an equivalent immutable fixture. | A focused test or benchmark command emits one machine-readable result per run and can compare the current implementation with a candidate implementation. |
| LEARN-MEM-002 | P0 | Done | Define the exact optimizer-evidence inclusion policy before changing queries. Distinguish entry-linked runs required for outcome evaluation, explicitly requested diagnostic runs, and historical runs needed only for aggregate calibration. Record why every included run was selected. | The policy is documented and tests prove that an entered lineup retains its linked run while unrelated completed runs are excluded or represented only by an explicit summary. |
| LEARN-MEM-003 | P0 | Done | Replace the all-at-once optimizer configuration load in `SlateLearningService._load_evidence` with a two-stage query: load lightweight run metadata first, then retrieve one needed configuration at a time or in a bounded batch. Avoid materializing all JSON configurations and their candidate pools in one evidence dictionary. | The Sunday Main benchmark never holds all 36 full configurations simultaneously; the produced learning conclusions and evidence hashes are deterministic for the declared report-contract version. |
| LEARN-MEM-004 | P0 | Done | Refactor optimizer-effectiveness evaluation to consume one saved candidate pool at a time and retain only the metrics, selected/entered evidence, and concise drilldown rows required by the report. Release per-run temporary data before evaluating the next run. | Peak RSS is at most 1.0 GB for the benchmark fixture, or the measured and justified platform floor if higher; selected-run scores, rankings, missing-evidence flags, and aggregate correlations match the approved baseline. |
| LEARN-MEM-005 | P1 | Done | Split the weekly report into a compact default result and an on-demand detailed candidate drilldown. Keep the report’s summary, completed run IDs, evidence hashes, and counts in the default response; fetch or export large candidate detail by run ID with pagination or a file download. | The default weekly-report response is no larger than 2 MB for the benchmark fixture, and every omitted detail has a stable retrieval path tied to the report ID and optimizer-run ID. |
| LEARN-MEM-006 | P1 | Done | Version the weekly-learning API/schema and persistence contract for the compact report. Add a migration if detailed candidate evidence moves out of the existing JSON report payload. Preserve read compatibility for already-stored `slate_learning_report_v1` records. | Existing reports still open, new reports identify their contract version, and a report can reconstruct or locate the exact detailed evidence without using mutable current-state data. |
| LEARN-MEM-007 | P1 | Conditional / deferred | Move weekly report generation onto the durable operational worker if it remains a long-running request after batching. The API should create a traceable, idempotent job and return status without retaining the report build in the request process. | Refreshing the UI neither duplicates a run nor loses progress; worker logs/status expose memory benchmark identifiers, report ID, source evidence, and actionable failures. |
| LEARN-MEM-008 | P1 | Done | Bound in-process optimizer-result retention and remove completed jobs from the in-memory cache after a configured limit or time-to-live. Persisted reload must remain the authoritative fallback. | A stress test opening many saved reports keeps cache size bounded and can reload an evicted completed run from persisted tables with equivalent results. |
| LEARN-MEM-009 | P2 | Done | Make preparation and status polling single-flight: do not start a new request while the previous request for the same scope is unfinished, and back off on slow or failed responses. | A delayed API fixture proves no concurrent requests accumulate for one component scope, timers are cleaned up on unmount, and normal refresh behavior remains intact. |
| LEARN-MEM-010 | P2 | Done | Add production observability for report size, candidate counts, load-stage timing, peak process memory where available, cache occupancy, and worker failures. Define alert thresholds from the benchmark budget. | A completed report records enough telemetry to identify whether a regression came from selection scope, candidate-pool size, serialization, cache retention, or polling. |

## Implementation Sequence

1. Complete `LEARN-MEM-001` and `LEARN-MEM-002`; they establish the baseline and
   decide which evidence the report is allowed to load.
2. Implement `LEARN-MEM-003` and `LEARN-MEM-004` together, with the existing
   Week 4 Sunday Main report as the comparison fixture.
3. Complete `LEARN-MEM-005` and `LEARN-MEM-006` if the compact processing path
   still produces a response too large for the browser or API process.
4. Complete `LEARN-MEM-007` through `LEARN-MEM-010` as operational safeguards.

## Validation Matrix

Before closing the work, verify all of the following:

- The weekly report preserves the same outcome conclusions for entered lineups
  and selected optimizer candidates under the approved inclusion policy.
- Candidate-pool provenance remains traceable to immutable optimizer runs and
  the source/evidence hashes remain reproducible.
- The benchmark fixture completes below the agreed 1.0 GB peak-RSS budget and
  does not increase swap usage under the normal local workload.
- Focused learning, optimizer-effectiveness, API-contract, and UI tests pass.
- The UI can view the compact report and retrieve detailed evidence without
  loading all candidate pools into browser memory.
- The post-slate learning runbook, API documentation, release notes, and the
  canonical backlog are updated when implementation begins or the contract
  changes.

## Relevant Code

- `backend/app/product_services/slate_learning.py` — current weekly loader and
  report construction.
- `backend/app/product_services/optimizer_effectiveness.py` — saved candidate
  pool evaluation and aggregate metrics.
- `backend/app/api/product_routes.py` — weekly-report API route.
- `backend/app/product_services/optimizer.py` — persisted run reload and
  in-process result cache.
- `ui/src/SlatePreparation.tsx` — preparation status polling.

## Implementation evidence — 2026-10-05

Builder `2026-10-05.3` produces `slate_learning_report_v2`,
`optimizer_effectiveness_v2`, and `weekly_learning_report_v2`. Migration
`0046_compact_learning_evidence.sql` is applied locally; apply it before deploying
this builder elsewhere. Existing v1 rows and optimizer configurations remain
unchanged. Immutable candidate and entered-lineup evidence moves into a separate
content-addressed table; both detail endpoints also read legacy embedded evidence.

Policy `entry_linked_and_explicit_diagnostics_v1` loads canonical entry-linked
runs plus explicitly requested completed diagnostic runs in the same slate.
Every other completed run has an ID, configuration hash, and exclusion reason.
Historical calibration uses only complete, entry-linked, predecision samples,
with the same numeric Pearson/Spearman inputs as v1. The loader checks the full
configuration SHA before decoding only the saved pools and selector provenance
needed for evaluation. It processes one run at a time. Default responses keep
metrics, counts, hashes, and a maximum of 20 candidate preview rows per run.
Full candidate pages (maximum 200) and full saved entry decisions/controls have
stable report-specific URLs. A missing frozen detail is an explicit error.

| Fresh-process Week 4 measurement | Peak app RSS | Response | Duration | Comparison |
| --- | --- | --- | --- | --- |
| Sunday Main default | 527 MB | 142 KB | 11.9 s | Entered-run conclusions match saved v1 baseline; no additional system swap |
| Full week, all three entered slates | 539 MB | 383 KB | 15.6 s | Exact numeric historical samples; no additional system swap/pageouts |
| Sunday Main with requested 775-candidate diagnostic | 557 MB | 224 KB | 15.7 s | Entered-run conclusions match saved v1 baseline |
| Sunday Night | 248 MB | 132 KB | 0.9 s | Entered-run conclusions match saved v1 baseline |

Artifacts: `artifacts/learning_memory/week4-weekly-bounded.json`,
`week4-sunday-main-diagnostic.json`, and `week4-sunday-night-bounded.json`.
The full week loads 3 required configurations; Sunday Main defaults to 1 of 32
currently completed configurations (the original baseline observed 36).
System swap/pageout counters cover the whole computer, not just the benchmark:
the diagnostic measurement observed increased system swap while the full weekly
measurement observed zero delta. RSS budgets refer to the Python build process;
PostgreSQL and browser memory are separate. Truncated construction-frequency
boundary ties now use canonical ordering; baseline parity compares tied counts
rather than arbitrary v1 representatives. Outcome scores and rankings are exact.

Repeat the full-week benchmark in a fresh process:

```bash
.venv/bin/python scripts/benchmark_weekly_learning_memory.py \
  --season 2026 --week 4 --entry-user wones0120 --weekly \
  --output artifacts/learning_memory/week4-weekly-bounded.json
```

For slate parity use `--slate SUNDAY_MAIN --compare-report-id
learning-report-ffba542e-b473-5ff1-a15d-9cb676403221` without `--weekly`;
optionally add `--diagnostic-run-id c442e072-db66-4214-b604-75d402449545`.
Benchmarks append/reuse immutable report evidence and refresh published stats
when `--weekly` is selected; they do not change projections or optimizer pools.

LEARN-MEM-007 remains conditional: the measured full-week request is below the
60-second duration threshold. Revisit durable dispatch if larger weeks or source
refreshes repeatedly exceed that threshold. The optimizer terminal-result cache
retains at most one persisted job by default, with 60-second lazy TTL eviction;
evicted jobs reload from persisted state. Cache occupancy is available at
`GET /api/optimizer/cache-status`. Preparation polling shares a single pending
request across timer/manual refresh, adapts to slow responses, backs off on errors,
and clears timers on unmount.

Report telemetry/logs expose load/build duration, selected configuration storage
bytes, completed configuration bytes, candidates, response size, and process
lifetime peak RSS. Weekly telemetry also exposes total duration. Alert budgets
are 1 GB fresh-process RSS, 2 MB default response, and 60 seconds weekly duration;
API lifetime RSS is a diagnostic indicator and requires a fresh benchmark before
attributing a regression to a particular build. Cache retention limits and TTL
are configurable in `.env.example`. Focused backend/API/cache and polling tests,
UI build, and live candidate pagination validate the bounded paths. Validation:
132 focused backend tests and 3 export/polling tests passed; the UI production
build passed. All 775 diagnostic candidate rows match legacy evidence after
normalizing equivalent cutoff timestamps to ISO 8601. The live app built Week 4
and navigated Sunday Night pages 1–100 and 101–131; the final next-page button
was disabled. Existing missing-evidence flags remain explicit. Local API and
idle worker were reloaded after migration and validation.
