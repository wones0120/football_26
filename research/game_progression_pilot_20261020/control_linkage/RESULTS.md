# Timeout-use and clock-control linkage

Added a separately identified [enrichment ledger](ENRICHMENT.jsonl.gz), preserving the original observation-contract ledger and every prior result. One cached extraction took **2.060 seconds** under a 30-second cap. All 49,665 source rows remain in original projection order; native order is unique and verified in all 285 source games. Source parquet/projection identity and hashes agree.

| Linked source evidence | Count |
| --- | ---: |
| Reported team-timeout uses with valid native team/identity and undeleted/resolved source status | 2,132 |
| Dedicated native TIMEOUT events | 2,053 |
| Timeouts attached to native plays, including upheld challenges | 79 |
| Reported timeout uses with corroborating source-budget debit | 2,089 |
| Reported uses with debit still unknown/uncorroborated | 43 |
| Frozen certified TIMEOUT clock links | 1,949 |
| All frozen certified administrative links reused | 3,308 |
| end_clock_time values that are wall timestamps | 41,918 |
| Missing end_clock_time values | 7,747 |

These are source observations and internal consistency checks, not independent official adjudication or validated generated policy. Dedicated events and attached events are mutually exclusive; budget and clock-link counts overlap them.

## Evidence and timing amendment

The immutable parquet contains structured `timeout` and `timeout_team` fields omitted from the minimal projection. No names or narrative parsing are used to establish a timeout. A timeout flag/team without unique identity, resolved source status or coherent native teams remains unknown. A count drop alone cannot invent a timeout event.

**Correction to observation-contract v1:** its generic pre-event timeout-budget label is unsafe on timeout-bearing rows. The provider computes remaining budgets after accumulating the current row's reported use. The new layer labels these snapshots `AFTER_CURRENT_REPORTED_DEBIT`; v1 remains unchanged as historical evidence. This convention is supported by the [provider timeout transformation](https://github.com/nflverse/nflfastR/blob/master/R/helper_add_nflscrapr_mutations.R) and corroborated case by case against adjacent native-order budget snapshots. Current upstream code does not prove the exact historical build version. See [SOURCE_SEMANTICS.json](SOURCE_SEMANTICS.json).

A debit requires the same regulation half, coherent source teams/clocks, undeleted/resolved previous row and exactly one unit removed from the reported team's observed budget. No first-row budget or halftime reset is filled. Of the 43 uncorroborated cases, 17 are overtime; 17 other cases lack a qualified prior snapshot, and nine have a conflicting budget difference. All are retained without claiming a debit. Generated timeout budgets are never reset from historical snapshots.

## What the clock links establish

The enrichment reuses only existing frozen certified administrative proofs, with unique referenced native IDs and agreement between the native event clock and the proof. This provides available preceding/following native references for 3,308 records: 272 GAME_START, 1,949 TIMEOUT, 828 END_QUARTER and 259 END_GAME. Historical half boundaries stay explicit. No general next-action identity is inferred from adjacency alone.

Of 2,053 dedicated timeout events, 104 lack a qualifying frozen timeout clock link and remain unlinked. A linked native timeout event clock is not the preceding play's end clock. Attached challenge timeouts do not use the original snap clock as the timeout clock. Observed clock gaps do not become an enforced runoff/restart rule.

The [provider field dictionary](https://nflfastr.com/reference/fast_scraper.html) describes `end_clock_time` as an end-of-play time, but every nonmissing value in this cached dataset is an ISO wall timestamp. None supplies remaining game-clock time at play end. `play_clock` and `out_of_bounds` are retained as reported fields, without inferring clock-running or restart behavior.

## Validation and remaining boundary

**98 tests pass in 0.84 seconds**, including 23 new linkage cases and 75 observation-contract/continuation/event-boundary cases. They cover native order versus play ID, contradictory flags/team/budgets, deleted/unresolved replay, attached challenges, half resets, duplicate identities/orders, missing clock links, wall timestamps and immutability. [MANIFEST.json](MANIFEST.json) binds all inputs and prior artifacts; [VALIDATION.json](VALIDATION.json) records saved-output checks and unchanged runtime hashes.

No new source download, reconstruction, fit, simulation, runtime integration or live setting/projection change ran. The 15 deferred source cases remain deferred. Missing play-end remaining game clock, complete terminal/enforcement state, restart/runoff/corrections and generated timeout/action policy remain unknown. **Continuation is not solved.**

The next evidence boundary is a source with explicitly bound remaining game-clock and restart/enforcement observations. This cache now supports reported timeout events and narrow historical control links, but cannot supply that remaining game-clock state through field renaming or UTC arithmetic. Do not repeat this extraction, fit a marginal wait curve or increase simulation precision to bypass missing support. SCENARIO-05 remains gated.
