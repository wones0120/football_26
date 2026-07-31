# MODEL-001 Candidate Lock

- Contract: `model_001_opportunity_efficiency_ablation_v1`
- Lock hash: `73e4597af6352da4893be80355dd714527e1ae5c33c8d7625df0a28d346c4869`
- Production model changed: `no`
- Holdout metrics read during selection: `no`

| Position | Baseline | Selected | Validation MAE lift |
| --- | --- | --- | ---: |
| QB | history_baseline | opportunity_efficiency | +1.51% |
| RB | history_baseline | history_plus_efficiency | +1.02% |
| WR | history_baseline | history_plus_efficiency | +1.15% |
| TE | history_baseline | opportunity_efficiency | +4.69% |
| DST | dst_history_baseline | dst_history_baseline | +0.00% |

## Validation Ablations

### QB

| Candidate | Features | Validation MAE | Lift vs baseline |
| --- | ---: | ---: | ---: |
| history_baseline | 4 | 4.819 | +0.00% |
| history_plus_opportunity | 14 | 4.766 | +1.10% |
| history_plus_efficiency | 7 | 4.788 | +0.65% |
| opportunity_efficiency | 17 | 4.746 | +1.51% |
| full_internal_context | 20 | 4.767 | +1.08% |

### RB

| Candidate | Features | Validation MAE | Lift vs baseline |
| --- | ---: | ---: | ---: |
| history_baseline | 4 | 3.128 | +0.00% |
| history_plus_opportunity | 14 | 3.123 | +0.15% |
| history_plus_efficiency | 7 | 3.096 | +1.02% |
| opportunity_efficiency | 17 | 3.097 | +0.99% |
| full_internal_context | 20 | 3.117 | +0.35% |

### WR

| Candidate | Features | Validation MAE | Lift vs baseline |
| --- | ---: | ---: | ---: |
| history_baseline | 4 | 2.870 | +0.00% |
| history_plus_opportunity | 14 | 2.896 | -0.89% |
| history_plus_efficiency | 7 | 2.837 | +1.15% |
| opportunity_efficiency | 17 | 2.844 | +0.90% |
| full_internal_context | 20 | 2.852 | +0.63% |

### TE

| Candidate | Features | Validation MAE | Lift vs baseline |
| --- | ---: | ---: | ---: |
| history_baseline | 4 | 2.129 | +0.00% |
| history_plus_opportunity | 14 | 2.071 | +2.74% |
| history_plus_efficiency | 7 | 2.089 | +1.89% |
| opportunity_efficiency | 17 | 2.030 | +4.69% |
| full_internal_context | 20 | 2.037 | +4.35% |

### DST

| Candidate | Features | Validation MAE | Lift vs baseline |
| --- | ---: | ---: | ---: |
| dst_history_baseline | 1 | 4.128 | +0.00% |
| dst_defense_form | 5 | 4.149 | -0.50% |
| dst_opponent_allowed | 5 | 4.182 | -1.29% |
| dst_full_internal_context | 9 | 4.205 | -1.85% |

The lock was selected only from data through 2025 W11. Injury, market, and salary features are excluded because their historical observation time is not proven.
