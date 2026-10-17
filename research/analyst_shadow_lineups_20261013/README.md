# Analyst construction generation evidence

This work began as an offline shadow harness and was extended, by explicit user authorization, to opt-in normal lineup generation. The current normal consumer is in `analyst_generation.py` / `optimizer.py`; imported packets use the immutable `artifacts/football_analyst_packets` ledger.

Current evidence:

- `normal_thursday_portfolio_final/REPORT.md`: real SEA–DEN packet imported and consumed by normal generation plus the unchanged 95% quality/exposure selector. Four generated thesis rosters, three selected with explicit attribution, four of five requested selected without relaxing caps. The baseline already contained the same candidate rosters, so this is ingestion/provenance/selection evidence rather than a claimed performance improvement.
- `normal_thursday_portfolio_final/with_analyst.json`, `without_analyst.json`, `manifest.json`: actual normal-pipeline outputs, separately identified arms, retained input/code hashes.
- `real_capture_v4/source.json`, `prepared.json`, `snapshot.json`: real read-only projection/salary join and production-prepared pool. The baseline projection cutoff is older than the analyst opinion; capture and current decision clocks remain separate.
- `fixtures_final`, `classic_demo_final`, `showdown_demo_final`: synthetic examples, not actual Sunday NFL research. They exercise player emphasis, QB/receiver/bringback, RB/DST, alternative-game and exact Captain-role construction.
- Earlier directories preserve intermediate experiments and failed capture/serialization attempts. Use the `*_final` normal report as current evidence. Original artifacts were not deleted or overwritten.

The real test uses in-memory evidence checkpoints and makes no live optimizer persistence or entries. Existing readiness still reports `market_missing` and `salary_pool_missing`; this test does not turn an incomplete-evidence preview into live READY. The source display's reversed venue and opposing-DST coherence concerns are called out in the final report. No separate 95% screen was applied in the initial `real_thursday_demo`; the final normal portfolio test does apply the existing 95% selector.

Focused verification: 15 new Analyst tests, 44 combined new/related selector/contract tests, and 75 existing Classic Large-GPP control/Small-field tests passed. No UI files are owned by this implementation agent; the companion app integration owns UI/API validation.

Usage and supported policies are documented in `docs/product/football_analyst_generation.md`.
