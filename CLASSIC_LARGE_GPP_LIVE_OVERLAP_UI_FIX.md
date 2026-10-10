# Classic Large-GPP live overlap investigation and submit guard

There is no evidence that the user is doing something wrong. The new job
`8863abc4-2f38-4627-8a26-7e971c957250` is a distinct, completed submission.
Its durable queued request explicitly contains `max_lineup_overlap: null`,
alongside 5 lineups, exposure 0.8 and primary-game cap 3. The backend therefore
received Strategy default, and correctly persisted null / 7 / strategy_default.
The earlier reports are not evidence against this new job.

The historical visible dropdown, summary and click-time React state were not
captured. The user confirmed URL `http://localhost:5173/` but did not confirm the
literal pre-submit summary. The original point of loss and cause remain unproven.
Neither user error nor an old loaded bundle is established by the saved report.
An unchanged effective strategy hash describes the saved default configuration;
it does not identify the browser build or prove a UI selection.

## Implemented changes

The six-row **Portfolio settings to submit** immediately above Run Optimizer
continues to render `nextLargeGppRequest.params`. `submittedClassicControls()`
returns the same object reference. The handler captures this before any await;
the API checks it against the exact JSON string passed to fetch. There is no
separate editable summary state. Diagnostic copies do not feed submissions.

The new click-time guard reads the actual native controls and compares them with
controlled React values, parent state and that shared request snapshot before
any identity/projection/ownership preparation write. A native dropdown showing 5
while React holds default now raises an explicit dropdown/state mismatch error.
The other five visible portfolio fields are also checked, with percentage units
normalized to rates. The serialized-body assertion then blocks missing, null,
string or different overlap when explicit 5 was captured. Both guards run in
production as well as development.

**Last submission diagnostics**, collapsed beneath the six-row summary, retains
the click trace in browser storage. The successful request carries the diagnostic
trace in params. The queue route stamps the parsed overlap from its own request
model; the saved-results route derives Requested from the actual saved contract.
A targeted API test verifies that client-supplied diagnostic values cannot
replace these server-derived values. Old jobs have no fabricated historical trace.
No database migration or dependency was added.

## Control and path inspection

- Presets use string option values 7/6/5/4 and convert with `Number`; default uses
  the explicit `default` sentinel, not an empty string. Custom inputs retain 0.
- The select is controlled by the parent's `largeGppControls.maxLineupOverlap`.
  Its only separate local state is whether Custom mode is active; it does not
  have a second numeric overlap state. Trace layer B records the controlled prop
  and separately records the Custom-mode flag.
- Saved preferences hydrate once, field by field; a malformed sibling cannot
  discard valid overlap. No overlap-reset effect or `value || null` normalization
  was found in this path. Existing mode/reload tests pass.
- The memo dependencies include controls, game cap, count, exposure and long-shot
  settings. The ordinary async click handler captures the snapshot before awaits.
- Large params use top-level `max_lineup_overlap`; Small Field has its separate
  policy. Default is explicit null in the actual App request. The API params dict
  preserves numeric 5. No schema alias or conditional omission was found for 5.

The confirmed defect in the previous guard was narrower than a demonstrated
historical cause: it compared two derived values and never read the actual native
control. A displayed value could disagree with React while summary and payload
both agreed on null. This gap is now blocked and covered by deliberate native
DOM fault injection; that test does not establish that the user's tab did this.

## Browser and backend evidence

The built-app regression serves unchanged `ui/dist/index.html` and its normal
main/App/Operations path, selects 5 / 80% / game 3 / overlap 5, checks the actual
dropdown and immediate pre-button summary, and clicks the real Run Optimizer
button. Playwright intercepts its actual POST JSON, which is forwarded unchanged
to the real FastAPI queue/parser and OptimizerService using synthetic players and
isolated SQLite persistence. The saved-results API reloads the persisted contract.
Upstream loaders and the application database adapter are fixtures. No live API
writes or user slate execution occur.

| Layer | Measured overlap |
| --- | --- |
| A. Native rendered dropdown | 5 |
| B. Controlled component value | 5 |
| C. Parent/form state | 5 |
| D. Shared summary snapshot | 5 |
| E. Click-handler snapshot | 5 |
| F. Builder input | 5 |
| G. Serialized request object | 5 |
| H. Actual outbound browser JSON | 5 |
| I. Backend parsed model | 5 |
| J. Persisted contract Requested | 5 |

The saved contract is Requested=5 / Effective=5 / Source=request. Achieved=5;
the production audit, frontend result guard and independent canonical-player
intersection recount each validate <=5.

The matrix also passes 4, 6 and explicit 7. Strategy default sends actual null,
saves Requested=null / Effective=7 / Source=strategy_default and achieves 7.
Negative browser tests reject native dropdown 5 vs React null, native exposure
60 vs React 80, overlap dropped at JSON serialization, and a corrupted returned
contract. Native-control mismatch blocks even upstream preparation writes;
serialization mismatch blocks the optimizer POST. Zero uncaught browser errors.

A separate fresh browser loads the actual running `localhost:5173` app, displays
5 and captures numeric network 5. All API calls are intercepted there and
optimizer execution is disabled. Backend/saved-contract proof comes from the
built-app synthetic fixture, not from a new live user job.

Validation: TypeScript/Vite build, full built-app browser matrix and negative
checks, fresh live browser capture, 15 targeted frontend tests, 40 existing backend
control tests plus the new API diagnostics test, mobile summary visual inspection,
and `git diff --check`. The existing bundle-size warning remains.

Evidence files:

- [Historical durable request](artifacts/classic_large_gpp_live_overlap/new-live-job/queued-request.json)
- [Ten-layer values](artifacts/classic_large_gpp_live_overlap/ten-layer-trace/ten-layer-values.json)
- [Built-app actual requests and fixture results](artifacts/classic_large_gpp_live_overlap/ten-layer-trace/browser-requests.json)
- [Live-server request capture](artifacts/classic_large_gpp_live_overlap/ten-layer-trace/live/browser-requests.json)
- [Deliberate dropdown mismatch trace](artifacts/classic_large_gpp_live_overlap/ten-layer-trace/dropdown-state-mismatch.json)
- [Serving/build/source hashes](artifacts/classic_large_gpp_live_overlap/ten-layer-trace/serving-evidence.json)

### Current served frontend build/hash

`http://localhost:5173/` serves Vite development modules with HMR, not `ui/dist`.
Source commit `098f30c58e3eb237d8aa8039108beaacf3d04644`, plus existing and new uncommitted changes.
Current served transformed module SHA-256 values:

- `App.tsx`: `7ff31e8a40c01db3b004b8c6bd2508fb37fd3d01a48163a81a1cc30c70d6b887`
- `api.ts`: `434e4054f5ef0c5c03269f799b5865f83005e158fb26c4f38e429577a397b0f5`
- `ClassicLargeGppPortfolioControls.tsx`: `773a47d06af821834728c421689a770ed7f7c1e0d40df01f1e7508efd3acb29a`
- `portfolioSubmissionTrace.ts`: `5848893573d86b6b8c933330b8bb5f6a95e80219593372dc90e1849e4640d723`
- `classicOverlapConsistency.ts`: `1f4ae845c29d2cd901830a58de40754978c15d41bacaea25a3fef88936687d9d`

Final production asset: `ui/dist/assets/index-aRq65aOw.js`.
SHA-256: `8c5a105fd78a5bf51a1f87594bd8024295c12f68e3210e9da52d868102d0a17c`. Browser-served production bytes match the on-disk file.
A fresh live load has no observed stale-code discrepancy. The earlier already-open
user tab could not be inspected because Computer Use was not approved for Chrome;
its historical in-memory build is unknown. This does not prevent isolated browser
validation. The API/worker were reloaded after verifying an empty active queue;
the live OpenAPI schema now includes the trace response field. No Vite restart.

### Does the visible pre-submit summary use the same state as the request?

YES. Same memoized params object, checked against the exact fetch body.

### Selecting overlap 5 displays 5 before submit?

YES. `Max shared players between lineups: 5`.

### Selecting overlap 5 sends network JSON value 5?

YES. Real click captured in the built app and fresh live localhost app.

### Does backend parse 5?

YES. Real route/parser in the isolated synthetic fixture.

### Does saved contract persist Requested=5 / Effective=5 / Source=request?

YES. Reopened through the real saved-results route with isolated persistence.

### Does achieved overlap validate <=5?

YES. Achieved 5, independently recounted from canonical IDs.

### What action does the user need before rerunning?

Hard refresh once at `http://localhost:5173/` using Command–Shift–R, then select
5 lineups / 80% exposure / primary game 3 / shared players 5. Confirm the
pre-submit summary literally reads `Max shared players between lineups: 5`.
The user personally makes the next optimizer submission.

### Exact first layer where overlap 5 was lost

Historical user job: unknown. The earliest durable evidence is the queued parsed
request with explicit null; there is no historical capture of A–H. In the deliberate
native-DOM regression only, A=5 and B/C=null, so the first mismatch is A→B;
the new guard blocks it. In the successful new browser run no layer loses 5.

### Exact root cause

Historical user job: unproven. Confirmed implementation gap: the previous guard
compared summary and serialized state without checking the actual native controls.
Do not assign the synthetic reproduction's trigger to the historical job.

### Visible dropdown value during failing path

Historical: unknown. Deliberate native-DOM regression: 5.

### Submit-handler value during failing path

Historical: unknown. Deliberate regression: null; submission is blocked.

### Serialized request value during failing path

Historical: not captured directly. Durable queued params contain explicit null.
Deliberate native-DOM regression: never serialized, because the guard blocks first.

### Actual network JSON value during failing path

Historical: no original browser network recording; queued request confirms received
null. Deliberate native-DOM regression: no request is sent.

### Backend parsed value during failing path

Historical: null, confirmed by durable queue request. Deliberate regression: no request.

### After fix: visible UI value

5, verified before clicking Run Optimizer.

### After fix: network JSON value

5, numeric, captured from the real click.

### After fix: backend parsed value

5, through the real route/parser in the synthetic fixture.

### After fix: saved contract requested/effective/source

5 / 5 / request, through isolated persistence and the real saved-results route.
Achieved 5 <=5.

### Does the app now block submission if explicit UI state and payload disagree?

YES. Native controls, React snapshot and exact serialized fetch body are checked.

### Does default still resolve to 7?

YES. Null / 7 / strategy_default.

### Does the user need a restart, rebuild, hard refresh or cache clear before rerunning?

Hard refresh once: Command–Shift–R at `http://localhost:5173/`. Verify summary 5.
No manual server restart, frontend rebuild or cache clear. Frontend build is complete;
API/worker reload is already complete. Refresh is recommended to replace the
uninspected existing tab state; stale cache was not proven as the original cause.

### Did Codex generate a new user portfolio?

NO. Only deterministic synthetic fixtures were executed. No Week 4 lineups.
