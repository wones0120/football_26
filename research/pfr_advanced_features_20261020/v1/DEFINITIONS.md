# PFR weekly contact and pressure measurements v1

This feature-only package reads authenticated original PFR Parquet snapshots through the reviewed source adapter. Only weekly rushing and passing records enter these measures; annual, receiving and defense files remain separate. The native REG game period must precede 202606. Capture and alias availability are bounded by the actual extraction cutoff. These later revised downloads do not establish original historical availability or independent final-game completeness. Current artifacts are postlock descriptive, with no serving, model, forecast or optimizer consumption.

## Catalog definitions and limits

- **G07-M07**: original PFR weekly rushing yards before contact, with same-row carry exposure and a separately named per-carry value. Signed yardage is retained. This is the vendor's contact attribution, not a causal measurement.
- **G07-M08**: original PFR weekly rushing yards after contact under the same matched exposure contract.
- **G07-M09 partial variant**: PFR broken tackles. This does not establish all missed tackles forced.
- **G13-M03 partial variant**: the original per-passer PFR pressure fraction in native 0–1 units, with original pressure count. No rounded-fraction denominator inversion, percentage averaging or offensive-line causal attribution.
- **G15-M05/M06 partial variants**: opponent rushing contact-yard sums and matched per-carry values across the full retained PFR rusher source for each defense/game. This source universe is not independently certified as every NFL rusher or a complete final game. Unknown components mask exact source sums; known lower sums remain explicit.

## Identity and provenance

Only persisted `pfr` native player aliases available at the actual cutoff attach canonical UUIDs. Raw display names never resolve identity. Conflicting aliases and missing aliases retain native actors, source row/game references and explicit review requests. Unmapped actors remain in opponent source aggregates. Canonical/native collisions in one game are rejected. Alias IDs and creation clocks are frozen once in provenance; source references, code hashes and actual derivation times remain attached to the immutable output.

Missing/nonfinite source fields remain unknown; known zeros remain zero. Nonzero contact yardage with zero carries is flagged and unavailable rather than creating a per-carry rate. User preferences never filter this source universe. Identity review writes use stable native person keys and `ON CONFLICT DO NOTHING`, preserving existing decisions without guessing aliases or reopening resolved records.

## Actual coverage

The final receipt binds 19,212 native actor-games, including 18,698 canonical actor-games, and 4,412 observed defense-games. There are 115 distinct historical native PFR alias gaps, durably retained in the existing identity review queue. G07-M07/M08 values are known for 18,290/18,297 rows; broken tackles for 18,298; passer pressure fractions for 5,372. Observed defense source sums are known for 4,404/4,411 rows. Twenty-two annual or other-stat source files are excluded from this feature grain. Known-value coverage is not a completeness claim for all possible NFL participants.

The previous artifacts remain unchanged. See `actual_receipt.json` for the current content-addressed artifact and actual timestamp. The source package is independently High-approved; this derived package awaits its own feature-only review. No catalog promotion is claimed before that review.
