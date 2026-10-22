# NFL Tiers research

The separate Tiers workspace imports a native DraftKings Tiers salary CSV and the supplied NFL rules, then explicitly selects an existing frozen Sunday Main common-DK projection snapshot. It does not build or change projections, ownership, Classic/Showdown/Single Stat controls, or default slate state.

Native roster labels determine tier count/order. Choose exactly one distinct canonical player per tier and players representing at least two NFL games. There is no salary cap, position quota, team maximum or Captain multiplier. The initial verified Week6 file has 40 players across T1–T6; its public native group is154973. Rules and raw CSV are immutable per import, with source hashes, native IDs, canonical matches, ingest receipt and unresolved mapping queue. Retrying an equivalent import/run returns the original evidence; changed inputs create separate records.

The optimizer exactly ranks eligible cross-tier products by summed unchanged baseline mean (bounded at2million combinations), retaining requested/achieved counts and reporting infeasibility without relaxation. Questionable/manual exclusions affect eligibility only. Missing projections, known unavailable/doubtful players and unresolved identities are visible. Source age and original readiness remain explicit. There is no calibrated Tiers win/correlation objective; rare return/offensive fumble-recovery touchdown forecasts are unverified. Explicit research consent is required, and final entry readiness stays false.

## API and download

`/api/tiers` exposes projection-sources, immutable records, pool import, optimize, export-readiness and a saved report download. Ledger is `artifacts/tiers_ledger`; native source/rules, receipts and export provenance remain separately identifiable. Pool-scoped UI settings use `dfs-tiers-settings-v1` and `tiers:<pool_sha256>`.

A saved lineup can download automatically from its imported native IDs, with no per-slate template. The roster-only UTF8 CRLF CSV has exact native T1..Tn headers and one numeric ID per tier. The service rechecks canonical/native/tier linkage, legality, scoped exclusions and locks. **Download lineup CSV** needs no acknowledgment checkbox; saved coverage limitations remain visible. Export receipts retain pool/report/source CSV hash, roster IDs, schema and content hash. A separately supplied optional verified template remains supported by the API and preserves every non-roster instruction/reference cell; pool/ID/tier mismatches reject rather than substitute.

The observed native template and official DraftKings CSV guidance support the slot/ID layout. Actual DraftKings upload acceptance has not been exercised. Download is separate from entry assignment, upload, submission and final injury clearance; no contest entry is created.

## Validation

Run `PYTHONPATH=. .venv/bin/python -m pytest backend/app/tests/product/test_tiers.py -q`, `node --experimental-strip-types --test ui/tests/tiersReporting.test.ts`, and the UI build for changed UI/contracts. Tests cover canonical conflicts/unresolved queue, native rules/transforms, schedule/source scope, idempotency, exact ranking, locks/exclusions, API save/reopen, automatic native bytes and optional full-template roundtrip/rejection. Browser QA must download actual bytes and compare exact tier-ordered IDs with the saved roster and receipt, not infer success from a visible link.

The initial review and byte-verification evidence is in `research/tiers_2026w6_20261016/v4/`; Analyst Reports catalog ID `sunday-main-tiers-review-2026w6-v2` includes all40 players, per-tier cases/alternatives and full scenario rosters. Original and newer-source baseline records are preserved separately; narrative Analyst cases do not imply numeric model application.

Official injury refresh is available from a saved Tiers pool. It appends a new pool/status revision and preserves frozen model means, known OUT/Q/unknown gates and original failed readiness history. The NFL source records blank game designations/practice/omission separately; none clears a player. The David Sills/Sills V root cause is fixed through shared suffix normalization with unique team/position matching and native alias conflict guards. Source refresh success is separate from final game-day clearance.

CSV download errors now appear in the workspace instead of saving an API JSON error as a file. Successful responses are checked for CSV content and the correct roster headers before a `.csv` download is started.

Contest standings also load through [Learning folder imports](typed_contest_learning.md), separately from component actuals and financial Entry History. Typed weekly reports preserve observed score/rank and unresolved identity/component/forecast-origin evidence.
