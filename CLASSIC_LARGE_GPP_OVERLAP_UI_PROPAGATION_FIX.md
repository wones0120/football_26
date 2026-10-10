# Classic Large-GPP overlap UI propagation fix

2026-10-03. Scope: frontend serialization, preference restoration, submission
consistency, and deterministic regression evidence. No optimizer strategy,
scoring, default, or production backend behavior was changed for this fix.
Existing uncommitted portfolio-control work predates this investigation.

## Saved application evidence

Read both application runs and their durable queue requests without executing them.
The queue request is the API model's saved JSON; its `params` dictionary preserves
explicit overlap unchanged, as verified independently through the queue endpoint.

| Evidence | Prior `94172747-3596-4b6a-82b4-a29326db2904` | Newest `dc0e1bb7-8cca-4b48-b3f2-00ccbc1409dd` |
|---|---|---|
| Queued strategy | classic_large_gpp_v1 | classic_large_gpp_v1 |
| API requested entries / exposure | 5 / 0.8 | 5 / 0.8 |
| API requested primary-game cap | 3 | 3 |
| API `max_lineup_overlap` | **omitted** | **omitted** |
| Saved optimizer options overlap | omitted | omitted |
| Contract Requested | null / Strategy default | null / Strategy default |
| Contract Effective / Source | 7 / strategy_default | 7 / strategy_default |
| Independently Achieved | 7 | 7 |

Queue job IDs: `95210f8e-3dc6-4323-9814-73d93a924f59` and
`a4406f82-dcd1-4e1f-9f6d-319e8ac7b510`.
Request hashes: `504bcf268faf53a8250ed728f2d56b6de7459c4e29dc974329da9abbe162007f`
and `99a6e16462e224820cb92b185c19528136c470761d88a3086c5118d24032c90b`.

[Saved request/report evidence](artifacts/classic_large_gpp_overlap_ui_propagation/saved_run_evidence.json)
contains the original queue JSON and compact saved report extracts. Neither
historical run nor its table was altered.

**The first observable loss is before API processing: the frontend submitted an
omitted overlap, not an explicit 5.** The backend did not replace a received 5.
Historical React state/local-storage contents and click timing were not recorded,
so the exact event at which an intended 5 disappeared cannot be proved from
these saved runs. This limitation must not be turned into an invented backend or
Small-field-conditional diagnosis.

Earlier UI verification selected 5 temporarily and restored the prior Strategy
default afterward; the previous UI-controls report documents that restoration.
That screenshot demonstrated a supported combination, not a persisted choice
for the next user run. Whether that was the browser/session used for the newest
application run is unrecorded.

## Trace and findings

| Layer | Code / verified behavior |
|---|---|
| Large UI control | `ClassicLargeGppPortfolioControls.tsx`: optional dropdown 5 maps to numeric 5; Strategy default maps to null. Separate overlap and per-lineup risk controls. |
| React state | `App.tsx`: `largeGppControls.maxLineupOverlap`. Updates now merge against current state using functional setters, preserving sibling choices. |
| Persisted preferences | `classicLargeGppControls.ts` and App persistence effect: key `football-26-classic-large-gpp-controls`. A reproducible previous bug reset **all** controls if any sibling preference was invalid. Example: overlap 5 plus saved elevated-exposure 101 restored overlap null. Now only the invalid field falls back. |
| Mode-specific state | Large controls are separate from Small-field `classicMaxLineupOverlap`. Switching modes leaves Large overlap intact. Returning from Showdown also restores saved Large entry count/exposure instead of persisting Showdown volume into Large preferences. |
| Classic builder | New `classicOptimizerControlParams` selects solely by the **submitted strategy**. Both `runOptimizerJob` and `launchWeeklyRun` construct the same immutable numeric control snapshot before their first await and spread it into their params. |
| Submission consistency | Previously the form remained editable during asynchronous identity/features/projection/ownership preparation, while the handler retained its earlier React closure. A later visible 5 could therefore differ from the already captured default. Large controls and mode selectors now lock while an action is pending; a next-request preview exposes the selected values. This hazard is established by code, not attributed conclusively to either historical run. |
| API JSON | `api.ts`: `runOptimizer` -> `startOptimizerAndRecover` -> `postJson` uses JSON.stringify; no overlap filtering. Weekly run receives the same control snapshot in `optimizer_params`. |
| Backend model/queue | `OptimizerRunRequest` validates params without discarding overlap. `queue_optimizer` saves model_dump into OperationalJob.request_json. The regression posts real frontend JSON to this endpoint. |
| Saved optimizer options | Real `OptimizerService.run_job` retains explicit params; the production adapter writes them to `target.optimizer_run.constraint_config_json`. Regression replaces only the database adapter and upstream loaders, retaining production request-to-contract logic. |
| Effective contract | Service copies non-null control keys into generation options; `build_strategy_contract` saves Requested from params, Effective from resolved config, Source request for explicit values. |
| Solver | Existing `apply_large_gpp_controls` sets uniqueness_overlap to the explicit cap; existing ILP constraints bound each new lineup's intersection with every earlier lineup by that value. |
| Independent validation | Existing `portfolio_audit` recalculates canonical-ID intersections and fails when any pair exceeds the cap. The regression separately recounts intersections from saved API lineup results as well. |
| Report table | `portfolioSettingsRows` reads saved report settings only. Changing current form overlap to 6 after the fixture run left Requested 5 / Effective 5 / Achieved 5 unchanged. |

The pre-fix working tree already included a Large-specific serialization spread
in both handlers. There was no demonstrated Small-field-only conditional dropping
5 in that tree. Consolidating the builder removes duplicate routing and adds a
real request/contract regression, rather than falsely naming that conditional
as the historical cause.

## Mode and preference behavior

Large explicit overlap is a top-level `params.max_lineup_overlap`.
Small-field uses its existing nested `portfolio_constraints.max_lineup_overlap`;
Large values and risk controls cannot leak into it. Showdown receives no Classic
control set. Explicit zero is serialized as zero, never converted through
truthiness. Null/default omits the optional field and preserves effective 7.

Large preferences persist within the same browser/origin. Small-field overlap
remains separate session form state. The existing primary-game preference remains
shared between Classic modes; this fix does not redesign that preference.

Actual application UI checks, without clicking Run Optimizer:

- Selected overlap 5, entries 5, exposure 80%, primary-game cap 3.
- Changed an unrelated team limit and restored it: overlap remained visibly 5.
- Reloaded: overlap remained 5, preview showed 5 / 80% / 3 / 5.
- Switched Small-field -> Large and Showdown -> Classic: same Large choices returned.
- Development reload also preserved those choices.
- No production optimizer submission occurred.

[Recorded application form](artifacts/classic_large_gpp_overlap_ui_propagation/application_form.txt).

## Deterministic frontend/backend regression

`ui/tests/classicOverlapPropagation.test.ts` creates JSON using the production
serializer, posts through the real FastAPI queue endpoint, reloads its saved JSON,
executes the real optimizer service/contract/solver/audit with 72 fake canonical
players, saves through an isolated SQLite adapter, and reopens through the real
saved-results API. No current salary/projection/ownership data is loaded.
The production PostgreSQL adapter is not exercised by this fixture.

The frontend asserts payload overlap **5 before invoking the backend**; the
saved request, saved options, Requested/Effective, source, report row and independent
intersections are asserted afterward. Omitting overlap fails this regression.
Tests additionally cover field-by-field malformed-preference restoration,
zero serialization, mode isolation and captured snapshots.

| UI selection | Saved Requested | Effective | Source | Achieved in fixture | Independent validation |
|---|---:|---:|---|---:|---|
| Strategy default | null | 7 | strategy_default | 7 | verified |
| 7 | 7 | 7 | request | 7 | verified |
| 6 | 6 | 6 | request | 6 | verified |
| 5 | 5 | 5 | request | 5 | verified |
| 4 | 4 | 4 | request | 4 | verified |

[Round-trip evidence](artifacts/classic_large_gpp_overlap_ui_propagation/roundtrip_results.json).

Browser E2E was also executed through the production React control component and
serializer in `ui/tests/overlapHarness.html`: select Large, set 5/80/3/5,
submit **synthetic fixture**, observe queue JSON overlap 5 and saved contract/table
5/5/request/5. Pending controls were visibly disabled. Changing current overlap
afterward did not alter the saved table.
[Reproduction workflow](ui/tests/OVERLAP_E2E.md).
The JSON/backend regression is automated; browser interaction was performed through
CUA and recorded, rather than claiming an automated browser runner was installed.

![Synthetic UI/API/solver saved report](artifacts/classic_large_gpp_overlap_ui_propagation/browser_e2e.png)

Validation:

- **64 frontend tests passed**, including the new frontend/backend regression.
- **196 targeted backend tests passed**, including explicit overlap 4/5/6/7,
  infeasible/no-relaxation checks, independent violation detection, Small-field
  policy, existing scoring, contract/API behavior and history recovery.
- Frozen omitted-control parity reproduced the original archived rosters,
  configuration and feasible-region/objective fingerprints. Archive SHA-256:
  `fbfb1cceb3fa0c6d08b66478523cfb5ae6c6fe544530571a8a7a842327a2707a`.
  This is the existing frozen baseline acceptance test, not a new Week 4 portfolio.
- TypeScript/Vite build passed; existing bundle-size warning remains.
- `git diff --check` passed.

No schema/config/dependency changes. No optimizer strategy or scoring edits were
made for this investigation. The fixture server was stopped after verification.
The user will personally run the next actual 5 / 80% / game3 / overlap5 portfolio.
Historical Requested values remain truthful and unchanged.

### Root cause

Confirmed: both historical frontend requests omitted overlap, causing the backend
to resolve the legitimate strategy default 7. An explicit 5 was never saved as
a request. Historical UI state is unavailable, so the precise browser trigger
remains unproven. Prior verification restored the UI default; the investigation
also reproduced all-or-nothing preference restoration discarding valid 5 and
identified the editable-form/earlier-request-snapshot mismatch. Those frontend
weaknesses are corrected, with shared strategy-specific serialization and an
end-to-end fixture proving explicit 5 survives. A backend reset or Small-field-only
conditional is not supported by the evidence.

### Did an explicit UI value of 5 previously reach the API request?

NO — neither supplied run's saved API request contains it.

### Does it now reach the API request?

YES — explicit 5 is verified through the real queue endpoint from frontend JSON
and the synthetic browser E2E.

### Does the saved strategy contract show Requested=5 / Effective=5?

YES — deterministic persisted fixture; the historical omitted requests remain unchanged.

### Does the solver honor it?

YES — production solver fixture achieved 5; 4, 6 and 7 also honored.

### Does independent validation require Achieved <=5?

YES — saved audit and separate canonical-ID pairwise recount both enforce it.

### Does omitted overlap still preserve strategy default 7?

YES — default fixture and frozen parity pass.

### Did Codex generate a new user portfolio?

NO
