# Classic construction review live fix

Completed October 4, 2026 against the user-confirmed saved run
`8a25b11e-cfae-442b-afd6-bf66042d9f2c`, Entry 1,
`enforce_single_te=false`. The real application button completed and rendered
meaningful construction comparisons. No new user portfolio was created.

| Verification | Result | Evidence |
| --- | --- | --- |
| API ROUTE VERIFIED | **PASS** | API-only reload performed; health OK; live OpenAPI advertises the POST route; real button request returned HTTP 200. |
| SAVED INPUTS VERIFIED | **PASS** | Normal saved-report GET returned the identified completed run; both frozen contract checksums validate; 154 frozen players and five nine-player rosters available. |
| LIVE UI REVIEW VERIFIED | **PASS** | Approved Codex in-app browser opened the explicit report; Entry 1 and single TE off; one diagnostic click rendered 14 families, including feasible RB/WR/TE FLEX individual and replacement comparisons. |

## Confirmed failure and runtime correction

The original API log contained this real failing request (line 125645):

```text
INFO:     127.0.0.1:54944 - "POST /api/optimizer/results/8a25b11e-cfae-442b-afd6-bf66042d9f2c/construction-review?entry=1&enforce_single_te=false HTTP/1.1" 404 Not Found
```

The original live OpenAPI had no construction-review route, while current source
registered it on the mounted `/api` product router. This was a stale serving API;
route matching failed before saved-job lookup. The original raw response body and
request body were not retained in the access log. The user's displayed “Not Found”
is preserved as a UI observation, not claimed as a raw network capture.

The confirmed target was then verified through its normal read-only GET, without
requiring access to the previously open Chrome tab. Before reload, the running
operational-job query was empty, target optimizer records had no queued/running
runs, and the API had no child solver process. The prepared command
`scripts/restart_local_backend.sh reload-api` was executed through approved shell
permissions. It reported `Launchd-managed api restarted; API is healthy.`

API PID changed from **10658** to **96992**, started October 4 at **10:54:06 EDT**.
Worker PID **10655** and its October 3 **21:06:03 EDT** start time were unchanged
before reload, after reload, and after the review. No stale PID was used to kill a
process. The established command targeted the live launchd API service only.

Live health at **14:54:09 UTC** returned `status=ok`, `app_env=development`.
Live OpenAPI now includes POST
`/api/optimizer/results/{job_id}/construction-review`. The serving process is
Uvicorn on `127.0.0.1:8000`, working directory this repository, API version
**0.1.0**. The frontend is the real Vite development application at
`http://localhost:5173`, UI version **0.1.0**, Vite **7.3.1**, served by PID
**5199**. The served frontend's `/api` base uses the normal Vite proxy to this API;
no API-base override or authorization bypass was introduced.

## Saved inputs and preserved controls

Both the full contract SHA256 and effective-frame SHA256 validate. The saved
eligible-player frame contains **154 players**. All **five** saved entries have
**nine** distinct canonical players backed by that frame, and the saved resolved
configuration deserializes successfully. The projection reference is
`7a2b7684-9a00-4e0c-9cd8-7f8058e618d1`; no current projection was substituted.

Verified from the saved contract and again from the returned diagnostic:
**5 entries / 80% global exposure / primary-game cap 3 / overlap 5 / team cap 4 /
within-lineup game cap 5 / single TE off**. The diagnostic reports
`changed_settings={}` and the saved contract checksum
`ca46257a4cba94cd6becf528398939a7cda6f030781475b9e4d7f593fd800a86`.
No earlier team-cap-three reference was used.

The UI correctly discloses `implementation_matches_saved=false`. Saved and
current source fingerprints differ; solver/adapter fingerprints are retained in
the saved contract and exported response. This is the current shared builder on
frozen saved inputs, not a claim of exact historical replay. The current response
records PuLP **3.3.0** and the CBC executable SHA256.

## Real browser action and response

Chrome's earlier access denial was not bypassed. An approved Codex in-app browser
opened the existing application. Its initially displayed report was a different
run; the target was explicitly opened from **Recent optimizer runs** and its full
Job ID verified in the UI. The app was reloaded after the API restart, then the
same target was reopened. Entry 1 was selected and the existing single-TE control
was set to the user's explicit off choice in this verification browser. No other
preference or saved setting was changed.

The only calculation action was **Review construction tradeoffs**. It displayed
“Reviewing constructions…” while CBC worked, then meaningful results. The
matching server access-log entry (line 130456) is:

```text
INFO:     127.0.0.1:55581 - "POST /api/optimizer/results/8a25b11e-cfae-442b-afd6-bf66042d9f2c/construction-review?entry=1&enforce_single_te=false HTTP/1.1" 200 OK
```

The browser request URL was the same path on `http://localhost:5173`, proxied to
the API. The served request helper sends body `{}`. Body evidence is the served
helper rather than a raw HAR: this browser exposes no network/HAR capture API.
The complete **parsed response received by the real UI** was exported from its
existing **Pinned inputs, active limits and full review** details. No substitute
request or private solver script produced the exported comparisons.

Returned request ID: **`1d7fdac2-8c1b-4b50-8888-761b69caf00b`**.
Returned status: **completed**, Entry **1**, single TE **false**, **14 families**.
The request ID is captured from the actual response JSON; the Uvicorn access-log
format records URL/status, not this response ID. This task made one live review
POST after reload. Raw response headers/bytes were not captured; the exported
parsed response and rendered results are the acceptance evidence.

| FLEX construction | Individual objective | Replacement objective | Result |
| --- | ---: | ---: | --- |
| RB / three RBs | 5.413157 | 5.382224 | Both feasible, Optimal; replacement validation verified. |
| WR / four WRs | 5.419170 | 5.419170 | Both feasible, Optimal; matches saved Entry 1. |
| TE / two TEs | 5.365836 | 5.346771 | Both feasible, Optimal; replacement validation verified. |

Component sums match solver objectives for these alternatives. Replacement
calculations retain the other four entries and saved exposure, overlap and
primary-game constraints. The same-team-RB-without-WR/TE family correctly shows
`excluded_by_strategy_eligibility`, with its minimum pass-catcher reason and
`Not searched`. These are diagnostic alternatives, not a new recommended portfolio.

## Preservation, exports and remaining action

Read-only full-row SHA256 snapshots before and after are identical for all
**348** `target.optimizer_run` rows, **914** lineup rows, **6624** lineup-player
rows, and **15** optimizer operational-job rows. The target's complete saved
results and effective contract are identical before/after. No new optimizer job
or portfolio record appeared. There was no Run Optimizer, source/ownership/
feature/projection refresh, saved-run overwrite, contest submission, worker
restart, strategy-weight change or default change.

Evidence directory: `artifacts/classic_construction_review_live_fix/`.

- `live-review-response.json`: full diagnostic response for review.
- `live-rendered-review.txt` and `live-review.jpg`: rendered comparison evidence.
- `live-acceptance.json`: request/response metadata and verification results.
- `target-report-before.json`, `target-report-after.json`,
  `target-input-verification.json`: saved inputs and preservation.
- `persistence-before.json`, `persistence-after.json`: immutable record hashes.
- `reload-evidence.json`, health/OpenAPI responses and
  `review-request-access-log.txt`: runtime and HTTP evidence.
- Earlier source/served-module fingerprints and original failure evidence remain.

The verified in-app tab is retained with the results. No permission or runtime
blocker remains for the requested review. To use the original Chrome tab, reload
it once, reopen this same saved run if necessary, retain Entry 1 and single TE
off, and click **Review construction tradeoffs**. No additional backend restart
or optimizer run is needed. Opening/reopening a report does not compute a review.

## Validation

The prior fix's **25 backend tests**, **79 UI tests**, production build, reload
script syntax and diff checks passed. This completion changed no application
code, so those suites were not repeated. The prepared API-only command, live
route, saved-input availability, actual UI calculation and rendering, worker
continuity and database preservation are now verified on the real services.
