# PFR weekly defender measurements v1

This package authenticates existing weekly defense snapshots and attaches UUIDs only through native PFR aliases available at the actual extraction cutoff. Annual files are rejected, and REG game periods must strictly precede the target period. Duplicate native defender/game rows are rejected. When distinct native actors share one canonical UUID in a game, every implicated native key is quarantined across this extraction batch: canonical attachment becomes unknown, native measurements and original alias proofs remain, and stable native review requests are retained. Existing aliases are never changed or guessed. Unresolved identities remain explicit; display names never join records.

**G15-M07 is a partial variant:** the source-reported individual defender missed-tackle fraction, in native 0–1 units. It is not a certified team missed-tackle rate. Source missed-tackle and combined-tackle counts are retained separately; the rounded fraction is never inverted to fabricate its denominator. Tackles and pressure involvements can overlap across defenders, so no sum of percentages, unique team pressure counts, pressure rate, or offensive-line causality is inferred.

Supplemental source counts retain pressures, missed tackles, combined tackles, targets, completions allowed and sacks. These are not additional catalog completions. Half-sacks are valid fractional source credits; negative/nonfinite counts are unavailable. Unknown source values remain unknown and known zeros remain zero.

The authenticated wrapper verifies each indexed artifact's bytes, source URL, source system, weekly defense dataset, season and capture clocks. Exactly one selected source revision per season is required. The pure builder's caller-supplied rows alone are not an artifact-verification claim.

Current derivations are revised, postlock descriptive evidence. Original historical availability and complete final-game coverage are unproven. There is no model, forecast, scenario, optimizer or current-serving consumer. Identity review requests are emitted; persistence is reported separately and never implied by their existence.

A native-key missing-alias request uses the existing stable PFR person review key. A newly discovered contradiction between existing aliases uses a separate evidence-specific conflict key, so an earlier resolved person decision remains unchanged while new contradictory evidence becomes independently reviewable. Equivalent extraction retries reuse that conflict key. No source-native participant or numerical source fact is discarded by identity quarantine.

## Actual source coverage

The authenticated prior-REG extraction contains 61,848 native defender-games and 57,882 canonical defender-games across retained 2018–2026 weekly files. Native source missed-tackle fractions are known for 58,747 rows. There are 370 durable native identity review requests; source facts remain present despite unresolved or contradictory mappings. The final artifact is 39,889,721 bytes and its full reference and actual extraction time are in `actual_receipt.json`. This is coverage of the retained source, not certification of complete NFL participation or a unique team denominator.
