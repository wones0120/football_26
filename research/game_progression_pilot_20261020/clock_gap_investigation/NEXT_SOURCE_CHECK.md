# One-game raw-source feasibility gate

Proposed next bounded task; not dispatched by this investigation.

1. Use only `2023_06_NO_HOU.rds` from the primary nflverse raw 2023 release. Freeze current URL, asset metadata and expected hash before fetching; reject a changed hash or record it as a separately identified source revision. Preserve original bytes with retrieval time and lineage. Maximum one game, one request chain, 1 MiB compressed / 8 MiB decoded, 30-second acquisition cap, no automatic retry or bulk season fetch.
2. Use an isolated data reader for RDS. The current task environment lacks one; selecting/installing an isolated reader is part of that future task, not a reason to change repository dependencies or execute provider R code. Save parser/version and parse outcome. Missing tooling or a decode failure leaves the gate unmet.
3. Inventory original field paths/types and native game/play IDs. Determine whether any field actually represents remaining game clock at physical play end, clock running/stopped status and cause, restart/runoff/correction enforcement or required untimed action. Retain UTC timestamps as wall time. A differently named start/snap clock is not a new end-clock observation.
4. Compare the raw native key and ordering for the runoff annotation and surrounding source records to the frozen processed game. Preserve revisions, duplicates, contradictions and unmatched IDs explicitly. Do not repair the 15 deferred source cases or tune a continuation model during this feasibility check.
5. Pass only if there are source-semantic and native-linkage grounds for at least one missing observation type. Passing one type does not establish a full successor law or calibrated policy. If the raw source repeats the same snap clocks/wall timestamps or lacks enforcement, stop: record it as insufficient and specify a different source requirement. Do not increase sample size to compensate for absent fields.

No simulation, fit, precision run, live activation or settings change belongs to this gate. A later implementation must preserve unknown mass and undergo separate chronological whole-game validation before claiming continuation support.
