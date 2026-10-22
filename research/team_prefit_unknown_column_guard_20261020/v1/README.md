# Team prefit entirely-unknown training-column guard

High P1 reproduction is corrected by matching the existing player-side transform rule: columns listed in entirely_missing_train_columns are forced to numerical unknown before train-median filling/missing-mask construction. Raw source dictionaries remain unchanged; columns observed in training still consume their measured values. Explicit legacy preprocessing without the metadata retains its prior contract.

The preexisting untracked module/test are preserved byte-for-byte under baseline/. Model version, estimator recipes, targets, feature order, training preparation, model/settings/lineup artifacts are unchanged. This patch runs no estimator fit, inference activation, source job or matrix expansion. Fifteen targeted tests pass, including two new holdout/inference regressions and existing no-implicit-fit checks. Concrete matrix/availability gates and High approval remain required before any new fit.
