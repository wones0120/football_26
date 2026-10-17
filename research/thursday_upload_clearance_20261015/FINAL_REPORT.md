# Thursday upload readiness and verified downloads

**All eight saved Thursday lineups are provisionally upload-ready. Both saved-run Download Recommended and Download All actions were exercised in Chrome, and all four actual files were parsed and matched to immutable saved rosters and export receipts. Final official inactive reconciliation remains pending.**

| Portfolio / run | Download Recommended | Download All | Clearance checked / expires (UTC) |
|---|---|---|---|
| Normal `706ae9ad-0327-4b76-8254-6585adc073ef` | [1 row, saved #1](normal_recommended.csv) | [4 rows, saved #1–4](normal_all.csv) | 2026-10-15T14:41:18.247813+00:00 / 2026-10-15T15:11:18.247813+00:00 |
| Contrarian `5cf2ed29-824f-4ef7-84d1-cf770b5e0142` | [1 row, saved #3](contrarian_recommended.csv) | [4 rows, saved #1–4](contrarian_all.csv) | 2026-10-15T14:51:58.203479+00:00 / 2026-10-15T15:21:58.203479+00:00 |

The two All files contain the requested eight lineups. The Recommended files are subsets of those same saved lineups; adding them would duplicate existing rosters. Contrarian’s actual frozen recommendation is #3, demonstrating that Recommended does not assume the first row. Normal’s is #1. Original Chrome downloads are also in `/Users/wones/Downloads/`; [VERIFIED_DOWNLOADS.json](VERIFIED_DOWNLOADS.json) records exact filenames, SHA-256 hashes, receipt IDs, selected numbers and salaries.

Every file has `CPT,FLEX,FLEX,FLEX,FLEX,FLEX`, numeric native IDs, the Captain-specific native ID in CPT and base IDs in FLEX. All rosters have six distinct canonical players and salary at most $50,000. Native identities, salaries, game timestamps and roles agree with current completed local salary ingests and immutable consumed native CSV hash. All eight original rosters, projections and preferences are unchanged: 50% Captain cap, four per intent, named JSN research eligibility and Darnold Captain exception; DEN exclusion off. No optimizer rerun was necessary.

The old `DEVELOPMENT_PREVIEW`/`entry_ready=false` consumed-input reports remain untouched. Separate append-only `saved_showdown_upload_clearance_v1` records bind each saved run, scope, projection, exact roster/model/preparation and current evidence semantics. Current NFL weekly reports were genuinely captured, source hashes verified, both SEA/DEN teams covered and identities resolved. Official supplements are composed with existing roster/depth evidence before evaluating canonical roles. JSN retains raw source Q where present; only his existing canonical named exception plus official full practice/no game designation clears that discrepancy. This does not declare him dressed.

Each download revalidates expiry, source freshness/hash and the semantic binding. A meaningful change in availability, role, native ID, salary, slate, roster or consumed input blocks subsequent downloads and requests another check. Checks last 30 minutes or until lock. Equivalent genuine source recaptures do not invalidate another run merely because observation IDs/clocks changed. The first live check’s missing canonical role failure is preserved as separate historical evidence; the corrected passing checks did not overwrite it.

**Before tonight’s lock (18:15 MDT / 20:15 EDT): reconcile final official inactives and review any late changes. These files are uploadable preliminary rosters, not final active confirmation.** The app does not yet certify final inactive lists through this contract. Live DraftKings draft-group publication and site acceptance have not been verified; the CSV contract and IDs are verified against the imported native salary evidence. No DraftKings site, login, upload, entry or purchase occurred.

The readiness records remain `UPLOAD_READY_PENDING_INACTIVES`, `entry_ready=false`, `final_active_confirmed=false`. Export receipts link the exact clearance record, exact bytes/hash and saved lineup IDs, with `submission_confirmed=false`. There is no assignment or submission inference. A later download needs a fresh Check upload readiness after expiry/reload; the downloaded bytes remain structurally valid but do not attest to later availability.

Validation: 81 targeted backend tests and five UI unit tests passed; TypeScript/Vite build passed (existing bundle-size advisory only); Python compilation and diff checks passed. Negative cases cover absent/forged/false/expired/wrong-run checks, wrong scopes, current OUT/Q/unknown availability, stale/future evidence, incomplete report teams, missing/changed native IDs, salary/game/role/file changes, absent named exception/proof, model/projection lineage and failed/preliminary runs. Classic/Showdown CSV and frozen recommendation regressions were included. No broad suite or new optimizer run was needed.

After final activation, all four live local download endpoints were also rechecked: each returned HTTP 200 with bytes identical to its Chrome-created file, retaining the same idempotent receipt. The final guard also explicitly checks saved raw Q flags when the current native salary row has a blank status; named eligibility plus official proof remains mandatory.

Chrome download-event automation stalled after successfully creating the normal recommended file; the tab was recovered and the existing file/receipt were inspected before proceeding. Actual local files and matching immutable receipts—not the browser toast alone—establish successful downloads.

![Verified per-run actions](download_buttons_verified.jpg)
