# Large-GPP overlap regression

The full application regression uses the normal built index/main/App entry point,
Operations navigation and Run Optimizer handler (not `overlapHarness.html`):

```sh
npm --prefix ui run test:e2e:overlap
```

Requires the repository Python venv, Playwright and installed Google Chrome.
If Playwright is supplied by a bundled runtime, set `PLAYWRIGHT_MODULE` to its
absolute module directory; no repository dependency is added. The test serves
`ui/dist` on an ephemeral loopback port, intercepts all `/api` traffic, and passes
the captured optimizer JSON unchanged to the isolated Python fixture. Upstream
preparation responses are synthetic; no production API/database writes occur.
It verifies 5/80/game3/overlap5, 4/6/7/default, persistence and control independence,
backend parsing, saved contracts, canonical intersections, served asset hashes,
all six **Portfolio settings to submit** immediately above Run Optimizer,
explicit null for Strategy default, a serialization fault rejected before any
optimizer network request, and a visible error for a corrupted returned contract. The SQLite
persistence adapter replaces the application PostgreSQL adapter.
It records dropdown/controlled prop/parent/summary/handler/builder/serialized body,
actual browser network JSON, backend parsing and saved contract in one run. Native
DOM fault injection (without change events) verifies dropdown 5 vs React null and
exposure 60 vs React 80 block before any upstream write. These synthetic failures
do not establish the cause of any historical user submission.

For a live-development capture without executing even the synthetic optimizer:
set `OVERLAP_APP_URL=http://localhost:5173` and `OVERLAP_CAPTURE_ONLY=1` when running
`node ui/tests/classicLiveOverlap.e2e.mjs` from the repository root. API requests
still fail closed into fixtures. Use `OVERLAP_BROWSER_EVIDENCE` for a separate
output directory to preserve the production-build evidence.

Results are documented in
[live overlap verification](../../CLASSIC_LARGE_GPP_LIVE_OVERLAP_UI_FIX.md).
The older harness and serializer regressions below remain supplemental coverage.

Automated frontend/backend regression (requires the repository Python venv):

```sh
npm --prefix ui test
```

`classicOverlapPropagation.test.ts` passes the production frontend serializer's
JSON to the actual FastAPI queue endpoint, reloads the queued request from isolated
SQLite, runs the real OptimizerService/contract/solver/audit with 72 synthetic
players, persists the report through a test SQLite adapter, and reopens it through
the actual saved-results API. It checks 5, 4, 6, 7 and omitted overlap. The
application database adapter and upstream data loaders are replaced; strategy,
scoring, constraints, solver and validation are unchanged. Removing overlap fails
the frontend payload assertion and saved requested/effective assertions.

Browser E2E uses the real production React controls and production serializer:

```sh
PYTHONPATH=. .venv/bin/python backend/app/tests/product/overlap_ui_fixture.py --serve
npm --prefix ui run dev
```

Open `http://localhost:5173/tests/overlapHarness.html` using the supported browser
tools. Select Classic Large GPP; set entries 5, exposure 80, primary game 3, overlap
5. Click **Submit synthetic fixture**. The saved API JSON must contain
`max_lineup_overlap: 5`; the saved table must show Requested 5 / Effective 5 /
Source request / Achieved <=5. During submission the controls are disabled.
Changing overlap to 6 afterward must leave the saved table at 5.
The synthetic server rejects seasons other than 2000/week 1 and all non-Large
strategies. It never loads current players or writes the application database.
Stop the fixture server after testing.

Also verify the actual application form without clicking Run Optimizer:
overlap 5 survives an unrelated team-limit edit, reload, Small-field -> Large and
Showdown -> Classic. The next-request preview must show 5 / 80% / 3 / 5.

Browser E2E was executed through CUA; the JSON/solver regression is automated.
Screenshots and assertions are recorded under
`artifacts/classic_large_gpp_overlap_ui_propagation/`.
