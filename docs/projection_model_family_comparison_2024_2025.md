# Player Projection Model Family Comparison

- Rows: `17342`
- Features: `26`
- Validation-selected family: `regression_tree`
- Selected validation MAE: `2.791`
- Untouched test MAE: `2.610`
- Production model changed: `no`

## Strict Time Split

| Split | Rows | Week slices | Start | End |
|---|---:|---:|---|---|
| train | 12008 | 19 | 2024-W04 | 2025-W07 |
| validation | 2600 | 4 | 2025-W08 | 2025-W11 |
| test | 2734 | 5 | 2025-W12 | 2025-W18 |

## Results

| Family | Validation MAE | Test MAE | Test RMSE | Test R² |
|---|---:|---:|---:|---:|
| rolling_mean_baseline | 4.577 | 4.483 | 6.141 | 0.083 |
| ridge_linear | 3.176 | 3.044 | 5.080 | 0.372 |
| regression_tree | 2.791 | 2.610 | 4.823 | 0.434 |
| shallow_neural_net | 3.066 | 2.901 | 4.944 | 0.405 |

The winner is selected only on the validation window; the later test window is untouched until final evaluation. This comparison is a research gate and does not automatically replace the production projection blend.
