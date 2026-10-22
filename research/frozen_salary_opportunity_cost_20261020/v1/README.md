# Frozen salary opportunity cost

Candidate G24-M07, actual arithmetic PASS, awaiting High review. This package validates previously stored complete Showdown roster alternatives, including canonical Captain identity/role. It does not run or import an optimizer, forecast, model, database, or source capture.

`frozen_salary_opportunity_cost.validate_comparison(snapshot, comparison)` checks semantic hashes, frozen canonical model/pool mapping, binary bounds, every captured linear constraint, fixed Captain and specialist include/omit treatment, six unique physical actors, 1 CPT/5 FLEX, salary and frozen projection sum (CPT 1.5 once), exact captured objective, complete branch counts/status, no relaxations, and canonical displaced/added actors and deltas. The source snapshot's entire policy/settings/provenance are retained; both branches bind that same immutable model. Display names never join identities.

The scope is eight stored research comparisons (two fixed Captains by four DST/K specialists), not current recommendations or a new lineup save. The frozen source uses its own game/slate keys; no PBP native-game equivalence is inferred. Salary dollars, baseline projection points and captured linear objective units are distinct. Historical recorded Optimal status is retained; plain arithmetic establishes feasibility and reported utility, not a new independent optimality proof. Missing source chronology remains explicit; a later analyst comparison does not restore historical outcome blindness or original availability at the earlier model cutoff.

Inputs: original `defense_kicker_analysts_20261014/v2` manifest/packet/report and the manifest-pinned `analyst_shadow_lineups_20261013/real_capture_v4/snapshot.json`. Manifest packet SHA is a canonical semantic JSON hash; snapshot file SHA is a byte hash. The separate Sunday preliminary model is not used by these Showdown comparisons and is not read.

Narrow validation: `PYTHONPATH=. .venv/bin/python -m pytest backend/app/tests/product/test_frozen_salary_opportunity_cost.py -q` (18 tests).

Actual run: 8 comparisons / 16 complete rosters, 24-player canonical pool, 48 mapped binary variables and 66 captured constraints per roster (1,056 constraint evaluations). All source semantic/byte bindings and full roster/salary/mean/objective/treatment/displacement checks passed. Execution 0.053s is source transformation time, not package build time. No new solver/model/DB/source capture. See actual_receipt.json and QA_SUMMARY.json.
