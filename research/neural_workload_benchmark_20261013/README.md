# Small neural workload challenger: feasibility result

**No reliable neural improvement conclusion is available.** We audited the existing local historical archive and declined to calculate comparative errors from chronologically unproven inputs. This is retrospective research; outcomes have already been inspected. There are no new application defaults, live writes, dependencies, or fantasy-point adjustments.

The installed sklearn 1.9.0 supports a modest (16, 8) shared MLP. Separate targets and carries models can share learning across players through lagged workload, team share, trend, position and measured snaps without player identity features. The history and installed HistGradientBoosting baselines use the same population, lagged inputs, and whole-week training window. This is computationally feasible: actual MLP and tree fits were exercised by deterministic synthetic tests. Those test fits are engineering checks, not football prediction evidence. Both synthetic MLP fits reached the fixed 150-iteration budget; convergence warnings are retained in the test log.

The workload source archive has 463,766 raw rows and 139,859 unique regular-season skill-player weeks after native/canonical checks. The captured native-ID alias join had no unresolved or ambiguous skill-player identities. The 47 native/canonical team-code differences are all LA → LAR normalization; none remain after that explicit mapping. Native payload missingness is preserved. No joins use display names. The archive includes complete 18-week 2024 and 2025 regular-season workload labels (5,848 and 6,043 skill-player weeks), but their first imports were February 25, 2026. That is evidence of later reconstruction, not proof that those exact versions were available before historical decisions.

The canonical current-season workload archive has 1,436 skill-player weeks across Weeks 1–4. Its earliest imports were October 4–6, 2026. A separate raw archive includes Week 5 labels but does not repair the missing input chronology. For consecutive current-season games, 942 source rows first arrived after the next kickoff, 24 lack a required source/next schedule, and 470 pass a weaker kickoff-only clock check. The 470 do not establish exact decision cutoffs, pregame roster/team evidence, or enough independent weeks. These archive first-import clocks do not prove no earlier source existed elsewhere; they show that this archive cannot demonstrate it.

Numeric observed zeros are retained. In the current workload snapshot, 414 targets and 940 carries are observed zeros; no present skill-player row has a missing targets/carries value. Missing player rows and DNP cannot be inferred from this table. A historical offensive-participation population and versioned pregame roster are required so evaluation does not reward a model for silently selecting only players with recorded workload. No current news, availability, guessed routes, or postgame fantasy context was added.

The fixed design requires 12 training weeks, 4 validation weeks and 4 test weeks, plus adequate measured rows per target. Current verified history falls far short. No overall/by-position MAE, workload-shift result, team-budget comparison, calibrated uncertainty, or fantasy profitability claim was manufactured. Neural-versus-history/tree performance remains **unknown**. No model winner was promoted.

Another experiment is worth running only after obtaining versioned historical weekly workloads and offensive participation, immutable pregame roster/team/position evidence, complete schedule clocks, and exact historical decision cutoffs covering the predefined split. An explicitly reconstructed retrospective comparison could assess numerical model capacity sooner, but it needs a separately approved scope and must retain its weaker chronology; it would not establish a trustworthy pregame edge.

## Reproduction

Run from repository root:

```sh
.venv/bin/python research/neural_workload_benchmark_20261013/benchmark.py
PYTHONPATH=. .venv/bin/python -m pytest research/neural_workload_benchmark_20261013/test_benchmark.py -q
```

The default command reads existing local snapshots and writes only `data_audit.json` here. Sources remain untouched. Runtime, source SHA-256 hashes, byte sizes, missingness, canonical join counts and clocks are persisted in that audit. The specification was saved before any prediction outcome scoring.

An evidence packet can later be passed as `--packet packet.json`. It must include per-row `player_master_id`, `team`, `season`, `week`, `position`, numeric workload labels, positive measured `offensive_snaps`, label source ID/observation clock, target kickoff and decision cutoff, pregame context source ID/clock, the small feature columns, and `history_source_evidence` as a JSON list. Each history member needs canonical ID, same-season prior week, team, source ID, source completion clock, observation clock and observed workload values. Team totals/snap fraction need their own source-ID lists and clocks. Features are replayed from evidence; mismatches and future clocks fail closed. The packet is supplied as evidence, never automatically reconstructed from the current database. Historical identity alias chronology remains a documented limitation because the existing native/canonical mapping is current.

Only positive offensive participants with measured labels are evaluated; the runner is not a participation model. Both targets have separate missing-label populations, but every model shares the exact sample within each target. Whole-week split and training-only preprocessing are enforced. Models have one fixed seed/configuration and a 120-second fitting alarm each. Results include validation/test errors, position, sparse-history, zero and workload-shift diagnostics; residual quantiles are descriptive. Summed team predictions refer only to the conditional skill-player population. +20% prior-usage perturbation recomputes derived shares/trends and flags shares above one; it does not allocate a team budget.

## Files

- `SPECIFICATION.md`: frozen football scope, split, fixed configurations and metrics.
- `benchmark.py`: offline source audit and guarded comparison runner.
- `data_audit.json`: actual data feasibility findings and source hashes.
- `test_benchmark.py`, `test_results.txt`: lagging, future-clock rejection, missingness, transfer exclusion, whole-week split, feature replay, train-only transforms and deterministic fitted-model checks.
- `delivery_manifest.json`: code/config hashes, installed libraries and validation state.
