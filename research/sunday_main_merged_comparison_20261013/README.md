# Actual preliminary Sunday Main comparison

[Readable comparison](LINEUP_COMPARISON.html) · [Full roster tables and assumptions](LINEUP_COMPARISON.md) · [Machine evidence](comparison.json) · [Independent verification](independent_verification.json)

Both portfolios saved **5/5 actual lineups** using the same 2026 Week 6 Sunday Main projection, ownership, salary/source pool and immutable injury-assumption manifest. These are **PRELIMINARY RESEARCH — NOT ENTRY CLEARED**. Ordinary optimization still rejects the failed preparation; preliminary entry reassessment stays false and contest CSV export returns 409.

- Original `CONSTRUCTION`: `114d36de-ef2e-4e2e-8dea-76dabf9b3132`.
- Merged `MERGED_SCENARIOS`: `37ac7ab5-8089-4070-81a0-91a272e95007`.
- Projection: `28f764f0-6fe9-4463-b55e-c6c93804848c`.
- Ownership: `2de85dc5-d62e-4bd8-b84c-50356ef9d2d3`.
- Analyst packet: `0ff53d55458993ab643c1dbf8cfed8255deb8e0a62724e5a3c686eb23de5e6b4`.
- Immutable preliminary snapshot: `1d4bd6796aac13a3fe2dcb0cc1262fce960cc2e47d8efc8c6e1a9a11d05daabe`.

Only one of five canonical rosters is identical. Original uses Stafford in every lineup; merged uses two Stafford, one Rodgers, one Allen and one Winston. Rams Puka/Higbee/Kyren remain in all five lineups in each portfolio. This exposes remaining concentration rather than claiming the scenario path fully diversifies every outcome.

Normal preparation and the first preliminary rank-preference failures remain saved. The matched reruns explicitly remove unavailable season-average rank restrictions (Week 5 snap coverage incomplete); all other shared settings remain identical. The merged live-data failure is preserved in `merged_trace.log`; its fix audits salary rows without finite model distributions rather than inventing zeros. The three affected rows after user/role filters were long snappers Rocco Underwood, Cal Adomitis and James Winchester. Selected base projections and salaries match the immutable source pool exactly.

The comparison preserves generation scenario overlap and rescales both selected portfolios under the identical conditional sensitivity metric. It does not compare incompatible solver objectives, assert calibrated probabilities, isolate a selector experiment, evaluate future performance, export contest CSVs or submit contests.

Validation: 59 affected backend tests, 26 UI request/report tests, TypeScript/Vite build, independent legality/canonical/source/assumption checks, unchanged saved-result reopen, normal gate rejection, entry-ready false and CSV guard rejection. No Chrome or visual browser validation was used. Working-tree code hashes in the verification file are explicitly observed review hashes, not a claim that all optional later modules were loaded during these runs.
