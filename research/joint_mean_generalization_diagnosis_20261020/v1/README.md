# Saved-artifact mechanism diagnosis

No fit or optimizer call was made. The numerical check took 0.698 seconds using saved TRAIN/2024 tensors and model parameters; it did not evaluate 2025 again. Previous versions remain intact.

Rush has both a budget generalization problem (TRAIN MAE 1.04, validation 10.53 versus constant 6.16) and an allocation problem: giving it the actual budget diagnostically still leaves validation actor MAE 1.57 versus the saved tree 1.28. Low-use historical actors accumulate positive bias while RB/QB counts are underpredicted. This does not justify declaring their future workloads zero.

Target derivatives remain correct but the cap leaves original gradient 1.87e-5 above 1e-5. Competing budget/cell gradients and uneven common-versus-allocation curvature are measured; a unique inner-solver failure cause is not proved. Another cap increase is not proposed.

`REPAIR_CONTRACT.json` freezes a proposed explicit affine group-budget head and jointly trained normalized mean-allocation head. Budget losses cannot directly inflate every actor score. It is a grounded architectural hypothesis, not demonstrated improvement. Preserve the same source cohorts, labels, raw-count loss/scales, exact solver tolerances and prior-only inputs. Review new formulas/arrays before root dispatches one fit per channel. No live activation.

2025 has already been inspected. Verified 2026 week/matchup evaluation requires B's chronology/census audit, explicit cold-start exclusions and dated injury/replacement proof; mathematical accounting is not evidence of predictive accuracy.
