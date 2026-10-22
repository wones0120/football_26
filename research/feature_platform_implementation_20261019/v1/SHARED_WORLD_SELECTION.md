# B05.1 / I01 complete-lineup selection contract

Status: user-authorized implementation; isolated evaluator passed review and actual runtime/UI integration is in progress. B01 authored publication/public acceptance is verified. New-selector operational acceptance remains pending. This is an enabling slice of the existing320-candidate program, not a reduction of its scope or a new set of independent signals.

## Ownership and smallest path

- B owns only `backend/app/product_services/shared_world_selection.py` and its focused test. Publication work preempts this module when the actual request arrives.
- A owns serialized I01 world/candidate/constraint integration and visible saved-report/UI consumption. No competing optimizer edits. Existing B01 coverage rendering may proceed during authored research.
- High owns review and this contract/ledger. Parent coordinates runtime and one compute job. No old selection contest, broad fit or legacy head-to-head is a delivery prerequisite.

The public path remains Prepare → Optimize → reopen the saved result → verify native CSV. Current explicit settings, including Captain exposure, locks, exclusions, salaries, team limits and requested count, are retained without silent relaxation. Conditional scenario coverage is a visible selection policy; an explicitly requested mean-only mode retains its meaning.

The latest authorized policy has **no mandatory stacks**. Only this new named policy omits legacy strategy-owned QB/receiver stack predicates and mandatory starting-QB constraints that are not actual persisted user controls. A static historical `source=user_required` label is not evidence that those constructions remain a current user instruction. Preserve actual Captain cap, locks/exclusions, Q policy, team/QB limits and required non-QB leader settings; retain their origins in the saved legal model. Old modes keep their existing behavior. Report the new policy's omitted strategy predicates separately from explicit controls; this is declared policy semantics, not a concealed feasibility relaxation.

## Inputs and physical meaning

The evaluator consumes a CPT-aware canonical candidate union and one frozen world set. Each candidate carries canonical actor/format roles and all originating variant IDs. Each world carries a full canonical conditional **mean fantasy-point** map, game/scope/input lineage, mechanism, supporting/contrary evidence, unknowns and source ancestry. Baseline and genuinely contrary contexts must be identified; do not fabricate a contrary world merely to pass validation.

Source/role/count forecasts inform the world producer. They are not additional point bonuses or votes alongside FP. The same passing event can score for quarterback and receiver under fantasy rules, but remains one physical event. Captain multiplies scoring once and never creates physical opportunity. Full-source team budgets/residuals are computed before user eligibility; exclusions cannot donate opportunities. A world with incomplete actor scores is explicitly unsupported, never silently filled from base means. The selector does not certify physical validity from a vector of scores: the producer retains opportunity accounting, source/clock validation and its limitations.

The initial valid world producer may retain declared sensitivity assumptions while forward component models are unfinished. Those assumptions and unsupported quantities remain visible. Missing probabilities or calibrated joint draws do not justify inventing them. No selection method restores missing source coverage, establishes a causal injury effect or proves predictive superiority.

## Deterministic decision policy

For each world, score every complete roster by summing its conditional player means with CPT applied once. Do not use the existing `candidate_metric` marginal P90 sum or the dormant touch-tail penalty prototype. Duplicate canonical rosters retain variant lineage but receive one evaluation. Identical numeric candidate-score columns receive one optimization column, retaining every world alias and its semantic/source differences; repeated prose cannot multiply influence.

The caller supplies an explicit expected-game anchor world and its authored `EXPECTED_GAME` lineage. If that is unavailable, a base-model expected anchor can be explicitly declared with the limitation; never silently choose the first of several authored scenarios. The first roster is the highest conditional mean in that anchor among rosters admitting a complete feasible requested portfolio. Tie on original base expected points, then canonical signature. This chooses the strongest expected-game roster under the declared forecast; it does not claim best tournament finish probability.

For later entries, let `covered[w]` be the highest conditional score of an already selected roster in each common world. A candidate adds `gain[c,w] = max(0, score[c,w] - covered[w])`. Rank by its **largest positive gain in any world**, then anchor conditional mean, original base mean and canonical signature. Record the target world(s), every per-world gain and remaining opportunities. There is no invented likelihood weight, summed world vote or conservative worst-world veto. If all gains are zero, state that no incremental scenario coverage was added and choose the strongest remaining anchor roster under the same controls; do not fabricate variation. This is expected-game strength followed by incremental conditional upside/coverage, not an estimate of win probability. An extreme world can influence an additional entry; its support, assumptions and unknown likelihood remain visible.

All candidates retain complete favorable and contrary score vectors. Shared failure dependencies remain visible across the portfolio. Worst-gap/minimax can remain a separate diagnostic or explicitly selected alternate, but it is not the primary recommended policy: conservative stress robustness does not implement the user's request for strong upside and useful variation.

Every proposed prefix must have an actual feasible completion to the requested portfolio under unchanged hard controls. The required completion oracle returns explicit feasible/infeasible/timeout plus hard-model policy/constraint fingerprint and target-size semantics. A boolean or absent oracle is not sufficient. A greedy prefix must not make a required minimum or 50% Captain cap impossible. A bounded timeout is not proof of infeasibility, and it must not silently authorize skipping a stronger candidate. Distinguish a proven deterministic choice from incomplete bounded search; report requested/achieved size, solver status and any infeasibility evidence. Numerical tolerance is declared precision, not a preference weight.

This is a conditional design policy. It is not a calibrated expected-value-over-worlds objective, joint percentile, win probability or guaranteed improvement. Expected points in the anchor, role uncertainty and supported joint-tail measurements are accompanying evidence. When joint draws are absent, joint P90/total-tail is unavailable; conditional world ranges must not be labeled as a tail probability. Unknown likelihood cannot distinguish a rare world from a common world. No objective may clip legitimate player upside, invent rarity weights or silently impose a safety screen.

## Saved and visible evidence

Persist policy/version, exact candidate/world/input hashes, canonical roster and generation variants, world aliases, all candidate-by-world conditional scores, constraint fingerprints, oracle outcomes and bounded search status. For each selected lineup persist:

1. Full-roster football success path and credible contrary path, with source/assumption ancestry and unknown likelihood.
2. Strongest admissible alternative under the same prefix/controls, expected-points tradeoff and exact anchor or incremental-gain decision comparison.
3. Shared role/game failure dependencies; no invented risk percentage or arbitrary penalty.
4. Incremental conditional point gains, previously covered contexts and remaining gaps.
5. Components actually consumed and components unavailable; FP/count/Analyst ancestry scored once.

Render these in the actual saved-results app view and readable report. Saving dormant JSON alone is not visible consumer completion. Reopening must use the frozen evidence rather than silently rerunning a selector against fresh sources.

## Narrow acceptance

- Common-world evaluation includes contrary outcomes for every candidate, including candidates generated elsewhere; no self-world-only scoring.
- Candidate/world order, duplicate variants and duplicate numeric-world columns do not change selection; lineage remains inspectable.
- CPT applied once, missing/invalid conditional scores rejected, no additional workload/Analyst point bonus and no summed marginal P90.
- Deterministic anchor example: expected/contrary scores A=(100,20), B=(85,80), C=(30,100) select A first when completion-feasible; C adds 80 contrary-world points versus B adding 60, so C is the next coverage choice. All contrary exposure and mean tradeoffs are shown; minimax would choose B first and is explicitly not this policy.
- Completion-trap fixtures retain exact minimum/max exposure, Captain cap and overlap controls; absent/invalid oracle, timeout and underfill are explicit.
- A unique extreme-world fixture exposes its influence on additional-entry coverage and unknown likelihood; it cannot displace the strongest feasible expected-game anchor first choice. No hidden worst-case screen or player-upside clipping.
- Full-source opportunity/zone/residual accounting and pregame clocks are checked at the producer boundary, with actual canonical/source identity. User exclusions do not alter these quantities.
- Reviewed code reaches public Prepare/Optimize/reopen/native CSV with unchanged explicit preferences and saved visible reasons. Model-quality claims require appropriate actuals/calibration evidence, but no canceled old comparison is reinstated as a blocker.
