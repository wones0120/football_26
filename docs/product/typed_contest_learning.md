# Tiers and Single Stat contest results in Learning

Learning → Review & Imports → **Scan contest folder** recognizes T1…Tn lineups as Tiers and three FLEX slots as Single Stat. It never infers a Single Stat scoring variant from FLEX labels or a small score. Check only relevant files, assign season/week/slate, choose the verified metric and record the contest scope/scoring source reference. An optional exact saved native pool hash enables native-ID identity checks. A missing/ambiguous scope or variant needs explicit review; unrelated files stay unchecked. Unsupported formats are not treated as Classic.

**Load selected files** preserves the exact raw CSV or ZIP in a content-addressed immutable ledger (`artifacts/special_contest_results/<record_id>/source.bin`) before moving a successfully validated file to Processed through the existing batch workflow. Failed files remain recoverable. Source hashes, assignments, batch records, contest IDs, pool/Game Set IDs and correction lineage are retained. An equivalent retry returns the original result. Changed results for an existing contest require an explicit correction record ID; original records remain readable. The weekly report uses the correction's new evidence without changing older saved reports. Raw file name, app receipt time and provider observation time are separate; missing provider clocks remain unknown.

## Scoring and identity

| Format / variant | Observed units and contract |
|---|---|
| Tiers | Normal DraftKings fantasy points. Exactly one athlete per native tier; initial pool has T1–T6. No Captain multiplier. |
| Touchdowns | Touchdowns only. Rushing, receiving, kick return, missed-FG return, punt return, offensive fumble recovery and defensive TDs; passing TDs do not count. |
| Total yards | Rushing + receiving yards. No passing yards or reception/PPR bonus. |
| Passing yards | Passing yards only. |

The contest's `Points` and `Rank` are **observed source values**, not reconstructed NFL stat components or proof of final settlement. Missing component data, including rare TD types, remain unknown rather than zero. `TimeRemaining` is preserved per entry; the importer does not independently certify finality. Manual component actuals in the Single Stat workspace remain a separate immutable evidence flow governed by its full component contract.

Native IDs must resolve uniquely through the selected native pool and canonical player IDs. Wrong tier, duplicate canonical player and conflicting native scope fail validation. Tiers requires at least two games; Single Stat at least two teams when identities are resolved. Name-only standings are retained as unverified and never joined to canonical athletes by display name alone. Blank field rosters are counted as unavailable rather than fabricated or allowed to invalidate other complete entries. Partial malformed rosters still fail.

## Reopen and weekly reporting

**Saved Tiers / Single Stat results** reopens the immutable raw-backed result for the Learning username. **Build Week Learning Report** includes separate groups by format, variant, slate, contest and native pool, with the correct units and source rank/score. Saved weekly reports reopen original content; new corrections or evaluations create new versions with evidence lineage. Classic/Showdown metrics and denominators remain separate from typed standings.

A uniquely corresponding saved forecast can be compared only through exact native-pool/canonical role rosters and compatible units. Multiple correspondences stay ambiguous; roster equality never proves origin, assignment, submission or pre-lock chronology. Forecast objective/coverage are retained, so a partial TD forecast is not called complete actual-stat reconciliation. Name-only real standings can therefore be imported successfully while remaining unmatched to forecasts.

No fee, payout or ROI is invented from ranks or standings. Entry History remains authoritative for financial evidence across formats. Synthetic acceptance files use `fixture:` source references, `fixture_research` classification, clearly synthetic entries and a separate review username/year; they never become financial records. No contest entry or submission is created.

APIs: existing `POST /api/imports/draftkings/weekly-contests` adds explicit format/variant/source/pool/correction fields; `GET /api/learning/typed-results` and `GET /api/learning/typed-results/{record_id}?entry_user=…` reopen typed observations. Existing weekly-report/library APIs retain these groups without rebuilding on reopen.

Validation: focused typed-results, batch-import, slate-learning and weekly-library tests; UI TypeScript/Vite build; actual Scan → assign → Load → reopen → Build Week Learning Report → reopen saved report. Real Tiers/TD and isolated total/passing-yard acceptance evidence is in `research/typed_contest_results_20261018/v1/`.
