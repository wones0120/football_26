# Historical first-snap offensive-line continuity

Candidate catalog ID: G13-M01. Feature-only review pending. Models, optimizer and serving remain pending and paused.

The measure is the number of unchanged native GSIS players in the same reported C/G/T family divided by five, comparing consecutive scheduled same-team games within a season. It describes observed first-snap membership, not pregame expected starters, health, blocking assignments or left/right alignment. Both units must be proven from the native beginning timeline and contain exactly eleven unique offensive participants and exactly C1/G2/T2. Generic source G/T roles do not imply side.

Native order_sequence, never numerical play_id, determines the first physical offensive snap after a unique quiet GAME_START. Earlier possible/nullified offensive snaps, unknown offense or missing order prevent certification. A missing first participation row cannot be skipped to a later unit. Missing scheduled games remain in the comparison sequence; the builder never substitutes the latest known unit. First season games have undefined continuity.

Native continuity and complete canonical qualification are separate fields. Exact GSIS aliases and player-master creation clocks must both precede the real extraction cutoff. The complete three-season native universe is checked before attachment; conflicting aliases are withheld across all periods. Unmapped actors remain native observations, not zeros. Two evidence-specific alias conflicts were durably appended to the existing identity review UI with readback; existing aliases, canonical records and resolved incidents were unchanged. No name joins occur.

Sources are the reviewed original participation Parquets for 2023–25, authenticated retained PBP manifests/native orders and the indexed native schedule. FTN participation is published after each postseason; these 2026 captures and derivations do not establish original pregame availability. Actual source-read, alias, derivation, publication and queue-readback clocks are retained. Every artifact is explicitly historical_postseason_revised_descriptive_not_pregame_or_serving, pregame_serving_eligible=false. No current 2026 participation fallback exists.

| Season | Expected game sides | Proven first C/G/T units | Defined continuity | Fully canonical comparisons |
|---|---:|---:|---:|---:|
| 2023 | 544 | 362 | 276 | 276 |
| 2024 | 544 | 280 | 215 | 215 |
| 2025 | 544 | 368 | 280 | 280 |

Uncertified units remain unknown: earlier possible snap/order concerns 16/22/21, non-C1/G2/T2 reported units 166/242/155. No five-player selection shortcut is used. There are 352 native line keys, 350 uniquely attached and two conflicting keys withheld. SF/WAS slices retain all 34 expected game-side rows per season, including unknowns. Initial boundary scan independently found one GAME_START and no missing/duplicate native orders for every one of 272 REG games per season.

The 7.64-second serial materialization loaded each original source once, performed one bounded alias read, published immutable content-addressed full and selected artifacts, then appended/read back two review incidents. It used no provider fetch, expanded parent inflate, model, alias repair or operational lineup action. Exact refs, semantics and clocks are in actual_receipt.json; tests.txt records 20 passing focused tests. Tests include earlier penalty/nullified snaps, missing first participation, jumbo units, missing intervening games, alias clocks/collisions, identity rebind parity and append-only persistence.
