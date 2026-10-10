# Classic Game Total Research and Review

Date: October 9, 2026.

**RESEARCH_ONLY / OBSERVATIONAL / NOT PRODUCTION VALIDATED**

## 1. Executive summary

Implemented a read-only Research Lab note and expandable Classic Game Environment Review for the primary recommended lineup, including its readable HTML export. The review uses the existing checksummed generation snapshot. No optimizer, Captain policy, projection, ownership calculation, correlation, eligibility, stacking, readiness or selection code was changed.

Higher-total games are overrepresented among top-decile offensive selections in this sample. The adjusted pooled association remains positive, but it is not stable across three independent slates. The RB signal shrinks under controls and changes sign by slate. Team-implied and DST-opponent patterns change when the slates receive equal weight. Independent predictive value and a cashing benefit remain unestablished.

## 2. Verification of the original findings

Independently reproduced the original analysis from archived roster exports and salary identities; verified all roster-input SHA-256 values, inventory/support/contest-result manifest hashes, and every analyzed contest denominator. The extended analysis reproduced the original player-selection shares exactly.

Original inputs: `artifacts/classic_historical_study/inputs/*.json.gz`, `inventory_snapshot.json`, `support_snapshot.json`, `manifest.json` and contest JSONs. Original analysis: `artifacts/classic_game_total_analysis/analyze.py` and `results.json`. Reproduction log: `artifacts/classic_game_environment_review/original_reproduction.log`.

Eight contests, three Sunday Main slates (2026 Weeks 1–3), 929,532 classified full-field entries and 93,218 top-10% entries. Top-10% membership uses rank <= ceil(full stored field × 0.10), with boundary ties. Full field includes the top finishers. There are 745,744 top-decile offensive selections and 7,436,256 field offensive selections. Each valid roster supplies eight offensive slots; FLEX is assigned its actual position and DST is separate.

| Slate-total tier | Top 10% offense | Field offense |
| --- | --- | --- |
| Highest quarter | 45.9% | 40.0% |
| Middle half | 38.1% | 41.0% |
| Lowest quarter | 16.0% | 19.0% |


High-total offensive players per lineup: 3.67 versus 3.20. Average offensive game O/U: 46.53 versus 46.15, a 0.38-point difference.

The 50+ selection share is below field in Weeks 1 and 3, above field in Week 2. Historical sources are verified prelock captures but some are days/weeks old; they are not certified closing lines and would not qualify as fresh live-review inputs.

## 3. Historical game-total analysis by position

| Position | Field high-total share | Top 10% | Top 5% | Top 1% |
| --- | --- | --- | --- | --- |
| QB | 42.2% | 47.6% | 48.8% | 50.0% |
| RB | 41.4% | 51.7% | 52.6% | 53.1% |
| WR | 42.0% | 45.0% | 45.5% | 46.1% |
| TE | 30.0% | 35.2% | 35.9% | 38.0% |


| Population | Offensive selections | Highest quarter | Middle half | Lowest quarter |
| --- | --- | --- | --- | --- |
| field | 7,436,256 | 40.0% | 41.0% | 19.0% |
| top_10 | 745,744 | 45.9% | 38.1% | 16.0% |
| top_5 | 373,288 | 46.6% | 38.3% | 15.1% |
| top_1 | 75,040 | 47.5% | 39.2% | 13.2% |


Recovered top-5% membership directly from hash-linked authentic rank CSVs/ZIPs, retaining raw rank ties and verifying field counts and original top-10% counts. Classified top-5% entries: 46,661. Top-1% entries: 9,380. Cohorts are nested; they are not independent populations.

| Slate | Top-10% high-total offense | Field high-total offense |
| --- | --- | --- |
| 2026-W01-SUNDAY_MAIN | 45.8% | 40.0% |
| 2026-W02-SUNDAY_MAIN | 53.0% | 44.3% |
| 2026-W03-SUNDAY_MAIN | 39.5% | 34.8% |


## 4. Team-implied-total analysis

| Position | Field mean implied points | Top 10% | Top 5% | Top 1% |
| --- | --- | --- | --- | --- |
| offense | 23.79 | 23.72 | 23.70 | 23.70 |
| QB | 24.26 | 23.51 | 23.34 | 23.03 |
| RB | 24.02 | 24.46 | 24.54 | 24.70 |
| WR | 23.80 | 23.47 | 23.41 | 23.34 |
| TE | 22.93 | 23.08 | 23.10 | 23.16 |


The selected RBs have higher average team implied totals among top finishers, but the full offensive average is slightly lower. A high game total and high selected-team implied total are different exposures. Team implied points reflect both total and spread.

## 5. DST opponent-implied-total analysis

| Population | Mean DST game O/U | Mean opponent implied points | DST from lowest quarter |
| --- | --- | --- | --- |
| field | 42.76 | 20.44 | 48.8% |
| top_10 | 42.39 | 20.19 | 52.9% |
| top_5 | 42.35 | 20.16 | 52.9% |
| top_1 | 42.25 | 20.03 | 53.8% |


Pooled top-decile defenses face a slightly lower opponent implied total. The adjusted association reverses under equal-slate weighting, so these results do not validate a defensive selection rule.

## 6. Controlled comparison results and limitations

Descriptive weighted linear probability association with contest intercepts. Entry weights n, outcome cohort/n; unique weights one unordered canonical roster within contest. Controls: lineup salary, sum prelock means, sum marginal P90 (not lineup quantile), RB/TE counts, QB pass catchers, bring backs, distinct games. RB contrast additionally controls RB salary/mean/P90 and overall offensive game total. Whole-slate and leave-one-slate-out variation replaces entry-level significance claims. No tuning or promotion.

Complete-case controls cover 745,863/929,532 classified field entries and 82,585/93,218 top-decile entries. Missing controls are not filled with outcomes or zeros.

The archived P90 supplement was exported using an enforced READ ONLY, REPEATABLE READ transaction. Every retained row has creation and data-cutoff clocks before slate lock, and its mean exactly matches the original hashed prelock reference. Sum of marginal P90 is a control for roster upside proxies; it is not a calibrated lineup P90.

| Exposure | Adjusted pooled slope | Equal-slate slope | Week 1 | Week 2 | Week 3 |
| --- | --- | --- | --- | --- | --- |
| offensive_game_total | +1.43 | +1.70 | +1.24 | +4.04 | -0.06 |
| offensive_team_implied | -0.97 | +0.53 | -1.64 | +3.17 | -2.13 |
| dst_opponent_implied | -0.40 | +0.15 | -0.49 | +0.62 | +0.71 |
| high_total_rb_count | +2.57 | +0.98 | +2.96 | -4.09 | +4.43 |


Units are percentage points of observed top-decile membership per one point of average game/team/opponent total, or per additional high-total RB. These are descriptive partial linear regression slopes, not probability forecasts, strategy weights or causal effects. Environment variables are compared in separate adjusted models. They are not mutually controlled in a joint environment model.

Salary and mean/P90 controls plus lineup structure reduce the pooled high-total RB slope from +6.39 to +2.57 percentage points per additional RB. The adjusted RB slope is +2.96 in Week 1, −4.09 in Week 2 and +4.43 in Week 3; removing Week 1 makes its pooled slope −0.94. This finding is not stable enough for a production inference.

Roster deduplication counts each unordered canonical roster once within contest. The adjusted unique-roster game-total slope is +1.36 (entry-weighted +1.43); high-total RB +2.64 (+2.57). Equal-slate weighting pools contests inside each slate then gives each slate equal weight. Full per-slate and leave-one-slate-out results for all three cohorts and both weighting schemes are preserved in `historical_results.json`.

Millions of selections share the same football results. All modeling is at the whole-lineup level and includes QB/pass-catcher and bring-back counts; no slot or entry is treated as an independent experiment for uncertainty. Shared games, overlapping contests and entrant skill remain confounders. Game-by-slate fixed effects would absorb the very market values being compared; a three-slate sample cannot identify a general effect by simply adding those effects. No independent-entry p-values or confidence intervals are reported.

Prelock ownership recovery: Week 1 has zero rows; Weeks 2–3 have timestamped rows but no verified input-provenance records. They were excluded, and realized contest ownership was never used as a control. Therefore the relationship beyond projected ownership cannot be established.

- Only three independent slates; overlapping contests and shared player outcomes remain dependent.
- Means/P90 recovered from archived before-lock run/row clocks; recovered means exactly match hashed original export. These are archived model references, not calibrated player-quality controls.
- No verified ownership control; cannot establish an independent effect beyond ownership.
- Market captures were prelock but sometimes days/weeks old, not certified closing lines.
- Complete-case projection controls exclude some entries; convenience sample and unknown contest structures limit generalization.
- Roster deduplication occurs within contests; equal-slate and leave-one-slate-out diagnostics handle shared slates descriptively. No independent-entry confidence interval or cash claim.

## 7. Top-decile versus actual cashing

No authentic payout tiers exist for the analyzed contests in either the original inventory or the fresh read-only database audit. Actual paid-position outcomes and cash rates are **Unavailable**. Rank thresholds 10%, 5% and 1% are not paid-position cutoffs. Current contest payout facts cannot be applied retrospectively to archived fields.

## 8. App research-note implementation

Research Lab → Classic Game Environment uses GET `/api/learning/research/classic-game-environment`, following the existing Showdown research-note interface. The note is stored in `docs/product/classic_game_environment_research.json` with reproduction status, success definition, denominators, source hash, observations and limitations. The note reader has no production optimizer consumer.

The run/result response adds an optional `classic_game_environment_review` field for completed `classic_single_lineup_v1` results. It is calculated only after selection, from the existing frozen snapshot and primary lineup. Saved legacy strategies retain their original report presentation. Missing or incompatible saved evidence produces Unavailable; no collectors, database backfills or diagnostic solves occur in reporting.

The review reuses the saved readiness freshness limits and generation clock, original provider observation/ingestion clocks, canonical player/game IDs and frozen checksum. A later historical report continues to describe its saved prelock evidence; it is not current entry clearance. Source timestamps and unknown quote-publication clocks are visible. Ownership requires frozen model-run input lineage and a pre-cutoff observation. Unknown/postgame fields are ignored by a whitelist.

## 9. Example Game Environment Review

The running local API serves the new research endpoint (HTTP 200); a read-only current Week 5 scope check found no completed single-lineup Classic run. No new production lineup was requested or generated.

The example is a **synthetic, legal, frozen test fixture**, not a new live recommendation. The production legality validator passes. It uses three games, eight offensive slots (QB 1, RB 3 including FLEX, WR 3, TE 1) plus DST. No live run was generated.

| Player | Position/slot | Team | Opponent | O/U | Team spread | Team implied | Tier | Projection | Projected ownership |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AAA QB 0 | QB/QB | ARI | BUF | 40.0 | -6.0 | 23.0 | lowest_quarter | 30.00 | 10.0% |
| EEE RB 0 | RB/RB | DEN | DET | 56.0 | 0.0 | 28.0 | highest_quarter | 12.80 | 10.0% |
| BBB RB 0 | RB/RB | BUF | ARI | 40.0 | 6.0 | 17.0 | lowest_quarter | 12.20 | 10.0% |
| CCC WR 0 | WR/WR | CHI | DAL | 48.0 | 4.0 | 22.0 | middle_half | 12.40 | 10.0% |
| DDD WR 0 | WR/WR | DAL | CHI | 48.0 | -4.0 | 26.0 | middle_half | 12.60 | 10.0% |
| EEE WR 0 | WR/WR | DEN | DET | 56.0 | 0.0 | 28.0 | highest_quarter | 12.80 | 10.0% |
| FFF TE 0 | TE/TE | DET | DEN | 56.0 | -0.0 | 28.0 | highest_quarter | 13.00 | 10.0% |
| CCC RB 0 | RB/FLEX | CHI | DAL | 48.0 | 4.0 | 22.0 | middle_half | 12.40 | 10.0% |
| BBB DST 0 | DST/DST | BUF | ARI | 40.0 | 6.0 | 17.0 | lowest_quarter | 12.20 | 10.0% |


Composition: 3 highest-quarter, 3 middle-half, 2 lowest-quarter offensive players; average O/U 49.00; 3 distinct offensive games. DST opponent implied points: 23.0.

Rank games in the complete salary slate by tie-aware midrank percentile: (number of lower totals + half the number of equal totals) / number of games. Highest quarter >= .75; lowest quarter <= .25; otherwise middle half. Equal totals always receive the same tier; tier sizes can differ from 25%. Any unavailable game total makes slate-relative tiers unavailable.

Selected team spread: negative = favorite, positive = underdog; implied points = (total - team spread) / 2.

For example, a home favorite at −6 with O/U 40 has 23 implied points; the away underdog at +6 has 17. Their implied totals sum to 40. A selected away DST faces the home team, so its opponent implied points are 23. Missing spreads leave implied totals Unavailable while a verified total can still display. Any missing slate game total disables all slate-relative tiers.

Observations report counts, average totals and projected-point concentration. They make no advantage/disadvantage judgment and do not require three high-total players.

## 10. Screenshots and sample output

Actual App/Vite build checked at 1440 and 390 pixels. All APIs were mocked; network writes were blocked. Research panels have no optimizer controls, the review is collapsed initially, tables scroll on mobile, one primary Classic recommendation remains visible, and the readable report includes the review.

![Classic research desktop](artifacts/classic_game_environment_review/research-desktop.png)

![Classic review desktop](artifacts/classic_game_environment_review/review-desktop.png)

Mobile captures: [research](artifacts/classic_game_environment_review/research-mobile.png), [review](artifacts/classic_game_environment_review/review-mobile.png). [Sample readable report](artifacts/classic_game_environment_review/sample_lineup_report.html). Browser verification: `artifacts/classic_game_environment_review/browser-verification.json`.

## 11. Files modified

- Added backend report/note services: `classic_game_environment.py`, `classic_environment_research.py`. Added the response field in `product_schemas.py` and read-only serialization/note routing in `api/product_routes.py`.
- Added UI helper `classicGameEnvironment.ts` and `research/ClassicEnvironmentResearch.tsx`; integrated through `singleLineupReport.ts`, `api.ts` and `research/ControlPlane.tsx`. Existing readable reports reuse the same renderer.
- Added capture, analysis, note/report render scripts; JSON note and preserved evidence under `artifacts/classic_game_environment_review`.
- Added backend and UI unit/API/preservation tests plus actual-App browser fixture. Fixed the existing offline worker fixture to use its in-memory SessionLocal; production readiness remains unchanged.
- Updated `README.md`, `RELEASE_NOTES.md` and this requested report. No config keys, dependencies or migrations were introduced.

## 12. Tests and production preservation

Final validation: 135 targeted backend tests and all 136 UI tests pass; TypeScript/Vite build and actual-App desktop/mobile/export checks pass. The original historical report renders byte-identically in an isolated temporary directory. See `backend_tests.log`, `ui_tests_verified.log`, `ui_build.log`, `browser_test.log` and `production_preservation.json` in the evidence directory for final results. Tests cover canonical game association, home/away spread signs, implied-total sums, current-slate/tied tiers, eight offensive slots, DST opponent values, missing/stale/post-cutoff evidence, projection/ownership clocks, outcome isolation, API serialization, legacy rendering and unchanged frozen selection.

A baseline was captured before implementation from 120 archived Week 3 Classic candidates. The current selector returns exactly the same primary roster, candidate diagnostics and report as the saved baseline; objective score 127.23057367322389. Adversarial research metadata cannot alter the selected IDs or score. Optimizer and single-lineup selection source hashes match their task-start values. No live solve, strategy weights or production defaults were changed.

The first broad UI run exposed an older offline fixture reaching the application DB through the preparation worker; the fixture now explicitly uses its SQLite session. A concurrent salary-readiness wording mismatch also appeared; the final suite uses the current code and expectations. Final checks do not depend on application DB access.

## 13. Additional data needed for statistical confidence

- Many more independently dated slates across seasons, with complete field results and official contest metadata.
- Authentic historical payout ladders, fees and entry limits, linked to each contest.
- Immutable timely market quotes with verified spread convention, observation/receipt clocks and ideally quote-publication clocks.
- Frozen player mean/ceiling projections and ownership forecasts with training/input lineage and known creation/cutoff clocks.
- Full candidate and chosen-lineup archives, source hashes, actual entrant/roster duplication facts, and postgame outcomes stored separately.

## 14. Recommendations for future research

Hypothesis: game environment may add information beyond projections and salary, with position-specific effects. That hypothesis remains unvalidated. Preregister contrasts and cash outcomes before later slates, freeze all inputs, hold out entire later slates, and evaluate calibration/coverage and cash results using official payouts. Compare total versus team implied points jointly, account for shared games and entrants, and report whole-slate/game uncertainty when enough independent clusters exist.

Keep this reporting layer informational. Any proposed production rule requires separate prospective validation and explicit user approval. No promotion recommendation is made.
