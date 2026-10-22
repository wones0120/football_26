# Source-state followup

The 36 source stops were a real progression limitation. Evidence-supported parser repairs now certify the recorded source transition for **21 of 36 path stops**, representing 20 distinct native plays. The remaining **15** require more source evidence. These are static dispositions of historical source records, not new completed simulation results.

Across all 65 SCENARIO-04 source stops, 31 terminal source transitions are now certified and 34 remain unresolved. The one cached audit took **10.474 seconds** under a 60-second cap. All 43,852 TRAIN cycles, their order, selection contexts, starting states, waiting observations, endpoints and unscopable threats were preserved. Certified source transitions increased from 43,197 to 43,433 (+236); previously certified states stayed certified. No simulations, fits, accuracy comparisons or live changes ran. Frozen prior results and receipts retain their hashes.

## Repairs and football accounting

- Single native fumble recoveries can prove final possession using native actor/team IDs, explicit lost status, a single-recovery census and the observed successor. Retained teammate recoveries, qualified punt muffs and a successor that is a penalty/no-play state no longer cause avoidable state failures.
- Qualified aborted plays with a single recovery can establish the endpoint while yard credit stays unknown. Actual reported lateral actors or conflicting chains remain barriers.
- A coherent native fake punt pass/rush or field-goal-formation punt can qualify an `UNSPECIFIED` provider class. Fourth down, explicit formation text, action flags, native actor ID, no deletion/penalty and resolved replay must agree. Raw native class and bytes stay unchanged; qualification is separately recorded.

The +236 transitions comprise 157 single-recovery cases, 62 aborted-single-recovery cases and 17 special-formation cases. Production changed in 146 cycles: unproven rushing yards were masked in 87, passing and receiving yards in 19 each. Sixteen special-formation cycles gained proven official/physical and associated production counts. Another qualified punt already had those production counts. Unknown yardage is not zero; reported source production is retained independently. No extra pass, rush or target opportunity is created by a recovery.

## Remaining 15 selected stops

| Cases | Remaining evidence needed |
| --- | --- |
| 6 replay reversals | Independently bound final adjudication, retained native play identity, final flags and applicable scoreboard/penalty agreement. A description containing both original and reversed rulings does not itself independently certify every channel. |
| 3 fumbles described as out of bounds | Structured or independently adjudicated out-of-bounds termination, retained possession and field location; do not invent a recovery actor from a missing ID. |
| 1 interception followed by fumble | Full ordered possession chain and final recovery, beyond a single offensive fumbler rule. |
| 4 lateral/multiple-player chains | Explicit actor sequence, final possession and separately supported yard/scoring attribution. Includes center-to-quarterback aborted recoveries, a lateral return touchdown and a lateral reception. |
| 1 offsetting no-play | Bound final cancellation/penalty adjudication resolving NULL lateral, scoring and penalty flags. |

Native play IDs, raw records, qualification proofs, production changes and path dispositions are in [AUDIT.json](AUDIT.json). Barrier counts overlap and must not be summed as distinct paths.

## Validation and next step

297 focused reconstruction, event-boundary, source-adapter and runtime tests pass in 0.80 seconds, including a block-to-cycle check that known possession and official carry counts preserve unknown recovery yardage. [VALIDATION.json](VALIDATION.json) binds current code/tests and the saved audit. An initial added integration fixture omitted required season metadata; the fixture was corrected before the passing run.

SCENARIO-05 remains gated. The 21 repaired recorded stops can encounter downstream source or censored-support gaps, and masking yardage does not establish a complete joint law. Obtain the evidence above before another changed experiment. Keep SCENARIO-04 results intact; no higher path count, successful-subset accuracy calculation or live promotion follows from this audit.
