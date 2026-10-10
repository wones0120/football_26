# One GPP recommendation per slate

Implemented 2026-10-10, starting live verification with Sunday Main.

After a successful GPP optimizer run, the application evaluates its returned candidates, freezes one provisional recommendation in the run's existing JSON parameters, and displays it above the result diagnostics. All alternatives remain in the saved run. The recommended-lineup download exports one lineup for reuse across the slate's contests. Contest saving is optional at this stage. Older runs are not retrospectively rewritten; run the optimizer again to create a recommendation.

## What the first policy can support

The goal is paid GPP finishes, with expected return and upside evaluated separately. The current app lacks a calibrated opponent-field model. Policy `gpp_projection_first_recommendation_v1` therefore uses a deliberately limited fallback: highest expected fantasy points among valid generated GPP candidates, then sum of marginal player P90s for exact ties, then a deterministic canonical-player/Captain identity hash. It does not invoke the existing cash single-lineup selector. It does not establish that maximizing expected points maximizes paid finishes.

The UI and saved report explicitly identify the result as provisional. Paid-finish probability and expected return are null, not zero or invented estimates. Summed player P90s are an upside diagnostic, not a lineup percentile. Showdown compares baseline forecasts across scenario-conditioned discoveries and does not multiply already weighted Captain forecasts again. Questionable/doubtful designations remain visible as review exceptions.

This layer compares the lineups returned by that run, not every possible roster or every internal discarded discovery candidate. Existing candidate count, GPP construction, exposure/overlap limits, exclusions, locks and projections remain intact. With five returned lineups it compares five and recommends one; it does not silently convert the user's settings into a larger search or a cash strategy. A single returned candidate offers no comparative search evidence. Internal-generation expansion, distributional candidate evaluation, calibrated paid-finish ranking and financial ranking remain outstanding work.

## Validation and saved evidence

Each candidate must pass the existing DraftKings native-ID, salary-cap, roster-slot and duplicate-player export validation and have finite projected points. Invalid candidates cannot win; no valid candidates produces an unavailable recommendation. Duplicate canonical rosters are compared once. Missing/inconsistent marginal upside is an explicit exception, not a zero estimate. Failed optimizer runs do not expose recommendations.

The saved report contains policy version, run ID, season/week/slate/format, projection ID/cutoff, candidate identities and original lineup numbers, ranking metrics, exceptions, rationale and limitations. It lives in the immutable optimizer decision's existing parameters; no new schema or migration is required. The API adds `gpp_recommendation` to optimizer responses. Downloading with `recommended_only=true` resolves the selection on the server and verifies the saved run, slate/format/projection and canonical roster before invoking the ordinary export validator. It never accepts an arbitrary client lineup index or enters contests.

The frontend also repairs an earlier shared-slate status-key mismatch: optimizer, projection and agent state writers again use the same slate key as their readers; simulation alone retains its paired slate/format key. This allows saved recommendations and previous results to display normally.

## Checks

- 30 candidate-policy/export tests passed: invalid and missing inputs, upside ties, candidate-order stability, duplicate rosters, Captain roles, unconditioned comparisons, missing financial evidence, exact one-row CSV, and wrong-scope/missing recommendation rejection.
- 130 optimizer, existing single-lineup and exposure checks passed. One unrelated existing exposure-route test failed because its hardcoded October 4 kickoff is now in the past; its real-clock fixture remains unresolved.
- All 144 UI unit tests and TypeScript/Vite build passed; the existing bundle-size advisory remains.
- The existing saved-result navigation browser test also passes for Classic/Captain on desktop/mobile after updating its obsolete Format selector label to Strategy.
- The new isolated browser test renders the built app, verifies the recommendation, review exception, alternatives and exact download query on desktop/mobile. The recommendation card fits; existing overflow elsewhere in the complete result view is separate.

Reproduce with `backend/app/tests/product/test_gpp_recommendation.py`, `backend/app/tests/product/test_draftkings_export.py`, and `ui/tests/gppRecommendation.e2e.mjs` (supports `PLAYWRIGHT_MODULE`). Live Sunday Main results are recorded separately under `artifacts/gpp_recommendation/`.

## Next performance gate

This delivers candidate comparison, a frozen primary choice and single-lineup export. It does **not** complete validated paid-finish optimization. Preserve a chronological GPP baseline, evaluate the chosen and rejected candidates against actual fields/payouts, and validate an opponent-field distribution before replacing the fallback with paid-finish ranking. Contest payout evidence is required for financial results, not for generating a slate-level candidate recommendation. Follow the [decision workflow](automated_decision_quality_workflow.md) and [GPP backlog](../TODO.md); no automatic retraining or model promotion is enabled.

## Live Sunday Main verification

API and durable worker reloaded after the queue was confirmed idle. Run `ddf86254-4a91-42d2-8309-cdbe9f2bd1b1` completed on 2026-10-10 with the last successful Sunday Main Classic GPP request's player and portfolio settings, using fresh prepared job `c957c15a-b95e-442d-bf7c-cc0cff9780a0` and projection `506c698c-a09c-4665-a79c-058c578de453`. Existing run IDs and saved decisions were not overwritten.

All five returned candidates were scoreable and export-valid; lineup #2 was selected provisionally (133.0740 projected points, 232.9586 sum of marginal player P90s). The API reloaded the persisted report, and `recommended_only=true` returned one CSV lineup whose native IDs exactly matched candidate #2. The verification did not enter any contest and is not final prelock clearance. Evidence: `artifacts/gpp_recommendation/sunday-main-live-verification.json`; verified CSV: `artifacts/gpp_recommendation/sunday-main-recommended.csv`.
