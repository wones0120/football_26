# AI Showdown Selection Packet: Phase 1 implementation review

## Outcome and scope

The read-only exporter builds a versioned JSON packet and matching Markdown from a completed saved Showdown candidate pool. It does not call the optimizer or alter `showdown_gpp_portfolio_v3`. The existing selector remains the control. The packet applies a fixed 85% of best-mean **and** best-summed-P90-proxy quality floor, then combines small quality seeds with scenario, captain, split, and salary coverage; deterministic similarity metadata is included.

Changed files: `backend/app/product_services/ai_showdown_packet.py`, `backend/app/api/product_routes.py`, `backend/app/tests/product/test_ai_showdown_packet.py`, `ui/src/api.ts`, `ui/src/RecentOptimizerRuns.tsx`, `scripts/export_ai_showdown_packet.py`, the two schemas in `docs/product/`, `docs/AI_SHOWDOWN_SELECTION_PACKET_PLAN.md`, README, and release notes. The production selector module was not edited for this task.

Contracts: `ai_showdown_selection_packet_v1` and `ai_showdown_manual_selection_v1`. The latter validates packet hash, timestamp, finalist membership, unique selections, and requested size, and labels a choice made after kickoff as retrospective. No manual-selection database write or AI API is included.

## Frozen Week 4 validation

| | Thursday Night, PIT@CLE | Sunday Night, DET@CAR |
|---|---:|---:|
| Run ID | `ffb8acf8-2e31-414e-81da-417d6d82c584` | `dc21b3ab-c330-487c-bb88-766f9a71f04c` |
| Archived variants | 149 | 131 |
| Distinct physical rosters | 117 | 110 |
| Run created / kickoff (ET) | Oct 1, 3:08 p.m. / 8:15 p.m. | Oct 4, 10:08 p.m. / 8:20 p.m. |
| Replay-safe packet | **Generated** | **Rejected: run created after kickoff** |
| Quality-eligible distinct rosters | 101 | 104 in retrospective-only classification |
| Finalists | 20 | 20 in retrospective-only classification |

The verified Thursday packet is [Markdown](artifacts/ai_showdown_selection_packet/week4_thursday/database/AI_SHOWDOWN_SELECTION_PACKET_THURSDAY_NIGHT_ffb8acf8-2e31-414e-81da-417d6d82c584.md) and [JSON](artifacts/ai_showdown_selection_packet/week4_thursday/database/AI_SHOWDOWN_SELECTION_PACKET_THURSDAY_NIGHT_ffb8acf8-2e31-414e-81da-417d6d82c584.json). Its evidence hash is `9c85b323dccc257bb05b219595c2f84ac2c6def3149e0cb6c31bcf4bf46e435f`; its saved candidate-pool manifest hash is `37baedcf9e6ce6bc5da46adcfad672ebe400af65199a3c7fb77f05089d9819cd`. The frozen database archive and the exported reference JSON produced identical finalist ranks. The latter lacks the full configuration and saved pool manifest, so its packet hash differs and it is not the authoritative artifact.

Thursday finalist selector ranks: **1, 2, 3, 4, 5, 6, 7, 11, 13, 15, 28, 47, 51, 62, 79, 82, 85, 94, 95, 147**. The production control selected ranks 3, 11, 13, and 31. Captain archetypes: WR 10, QB 3, RB 3, TE 1, K 2, low-salary skill player 1. Team splits: 5–1 CLE 5, 4–2 CLE 6, 4–2 PIT 3, 5–1 PIT 2, 3–3 4. The finalists cover every scenario tag represented among quality-eligible candidates, including favorite/underdog pass and rush, competitive shootout, low-scoring, and defense/special teams constructions. There are 25 HIGH-similarity finalist pairs, which the packet exposes for portfolio review.

For Sunday, no replay-safe packet was emitted. A **retrospective diagnostic only** applied the frozen finalist rules to its saved pool while bypassing the creation-time gate in memory. This does not establish that the pool existed before lock. It produced 20 finalist ranks: 1, 3, 5, 6, 8, 11, 12, 19, 35, 44, 47, 54, 57, 70, 77, 91, 92, 99, 121, 129. Captain archetypes: WR 10, QB 4, RB 2, TE 2, K 2. Splits: 3–3 8, 4–2 DET 6, 4–2 CAR 3, 5–1 DET 2, 5–1 CAR 1. All scenario tags represented among its quality-eligible candidates appeared. This diagnostic must not be used as a historical prelock decision record.

## Post-slate check, performed after freezing finalist rules and the Thursday packet

The saved learning detail identifies Thursday's eventual best generated roster at **114.96 actual points, selector rank 72**. It was quality-eligible but **absent** from the 20 Thursday finalists. Sunday's best generated roster scored **167.04, rank 43**; it was **absent** from the retrospective-only finalist set. Neither was added by tuning the rule after seeing outcomes. These misses show that the first diversification policy has not demonstrated capture of the historical winners. They do not establish that qualitative AI portfolio selection succeeds or fails; the forward Thursday trial should measure that prospectively.

## Tests and limitations

- Targeted packet tests: **12 passed**. They cover the frozen Thursday contract, deterministic hash, chronological Sunday rejection, separate Sunday structural classification, postgame-field injection, future evidence, classification, similarity, manual selection, stable finalists under candidate reordering, API serialization and rejection, and request bounds.
- UI TypeScript/Vite build passed. Python compilation passed. The existing build reports its usual bundle-size warning.
- The archive's per-candidate player list lacks complete ownership and some player-level evidence. Of 117 distinct Thursday rosters, 114 have saved total ownership and 70 have complete player-level FLEX ownership through the saved run. The exporter fills values only from the same saved run's player pool or selected rows and otherwise uses null. That limits low-ownership counts and some risk flags for unselected candidates.
- Scenario labels are simple construction heuristics, not game outcome probabilities. A 5–1 stack can be tagged as a dominant-win construction but may win in another game flow. The 85% floor and one-best-per-family nominations can still admit similar finalists and miss a distinct winner, as Thursday shows.
- The export checks run creation, saved kickoff, source observation timestamps, canonical IDs, and the saved pool manifest. It does not prove that every upstream source was published when its local observation timestamp says it was. Preserve original source manifests for the forward test.

## Forward validation: upcoming Thursday slate

Before lock, complete a Showdown run and export both packet formats. Record the saved run ID, kickoff, cutoff, original pool hash, packet evidence hash, policy version, and manual AI choice under `ai_showdown_manual_selection_v1` **before lock**. After the game, compare the frozen AI choice with the production selector, best generated roster, projection-only baseline, and ceiling-only baseline on best-of-K actual, selection regret, and field-attainment thresholds. Report scenario coverage and thesis overlap separately. Do not revise the packet or finalist policy after observing results.
