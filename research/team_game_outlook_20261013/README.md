# Fitted team/game outlook v1

Research-only optional Analyst evidence. Base player projections/defaults are unchanged. Revised historical sources lack contemporaneous provenance; earlier outcomes were inspected. W4/W5 diagnostics and2025 retrospective results do not become pristine validation. Current W6 forecasts are captured before games, but injury/QB uncertainty is unmodeled and no final entry clearance is implied.

The20-feature Ridge baseline uses own/opponent last-five completed games, scoring, plays, drives, EPA/success, target/carry fractions, rest and home status. Validation-only choice among alpha10/100 selected100. Paired home/away residual draws preserve limited observed game covariance; feasible volume budgets preserve targets+carries<=plays. No market multiplication or team identity feature.

| Retrospective set | Games | Points MAE | History MAE | Plays MAE | Drives MAE | Win-half-tie Brier |80%score coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
|2025W3-17|224|7.65|7.54|6.88|1.28|0.227|81.7%|
|2025 Sunday Main|161|7.70|7.56|6.80|1.24|0.222|81.4%|
|Known2026W4/W5|31|6.76|6.72|6.69|1.30|0.199|91.9%|

Scoring slightly trails simple history; this model is a transparent first outlook layer, not a proven projection upgrade. Probability reliability bins in results.json show material gaps (Sunday0.4–0.6 bin forecast51.3%, observed39.1%), despite pooled interval coverage near nominal. No calibrated forward probability claim. Score errors include defense/special teams. Plays/carries include QB and kneel opportunities; possessions are distinct offensive fixed drives represented in PBP, not a full kickoff-to-kickoff drive simulator.

## Saved W6 forecasts

Sunday Main includes the ten afternoon games. Thursday SEA–DEN is separately reusable for Captain. All14scheduled games are retained, including London/night games outside Main. Values below are statistical estimates without current injury/QB adjustments. Ties remain separate; table win adds half ties only for comparison.

| Game | Team | Points | Plays | Possessions | Targets | Carries | Win+half tie | Competitive scoring proxy |
|---|---|---:|---:|---:|---:|---:|---:|---:|
|2026_06_ARI_LA|LAR|26.3|65.1|10.7|33.9|27.6|65.0%|38.3%|
|2026_06_ARI_LA|ARI|20.3|62.8|10.7|33.2|25.3|35.0%|38.3%|
|2026_06_BAL_CLE|CLE|20.4|61.9|10.6|32.0|25.7|28.0%|36.1%|
|2026_06_BAL_CLE|BAL|24.5|62.2|10.7|28.7|30.0|72.0%|36.1%|
|2026_06_BUF_LV|LV|23.5|63.2|10.2|33.0|26.6|41.3%|42.7%|
|2026_06_BUF_LV|BUF|25.2|61.2|10.2|28.8|28.9|58.7%|42.7%|
|2026_06_CAR_PHI|PHI|21.9|62.1|10.8|31.3|26.2|46.6%|38.5%|
|2026_06_CAR_PHI|CAR|22.6|62.0|10.8|31.8|26.4|53.4%|38.5%|
|2026_06_CHI_ATL|ATL|23.6|62.1|10.7|28.6|29.5|54.2%|40.3%|
|2026_06_CHI_ATL|CHI|22.0|63.3|10.7|31.0|28.2|45.8%|40.3%|
|2026_06_DAL_GB|GB|23.7|62.9|10.5|34.6|24.5|45.6%|44.6%|
|2026_06_DAL_GB|DAL|24.4|62.6|10.5|34.1|25.0|54.4%|44.6%|
|2026_06_HOU_JAX|JAX|27.2|62.9|10.9|30.7|28.4|68.2%|33.9%|
|2026_06_HOU_JAX|HOU|19.2|61.7|10.8|33.0|24.2|31.8%|33.9%|
|2026_06_LAC_KC|KC|25.2|63.3|11.0|30.4|29.3|69.1%|29.9%|
|2026_06_LAC_KC|LAC|16.9|60.8|11.0|29.7|26.4|30.9%|29.9%|
|2026_06_NO_NYG|NYG|25.4|63.2|10.7|30.7|28.7|64.0%|36.2%|
|2026_06_NO_NYG|NO|20.6|62.5|10.7|32.9|25.5|36.0%|36.2%|
|2026_06_NYJ_NE|NE|24.1|62.8|10.9|30.6|28.2|60.6%|36.4%|
|2026_06_NYJ_NE|NYJ|20.2|61.4|10.9|30.6|26.4|39.4%|36.4%|
|2026_06_PIT_TB|TB|22.7|62.4|11.0|30.8|27.3|54.2%|36.4%|
|2026_06_PIT_TB|PIT|20.8|62.2|10.9|32.8|25.3|45.8%|36.4%|
|2026_06_SEA_DEN|DEN|21.2|61.2|10.8|31.6|25.5|45.5%|36.4%|
|2026_06_SEA_DEN|SEA|22.1|62.2|10.9|30.4|27.9|54.5%|36.4%|
|2026_06_TEN_IND|IND|23.9|63.3|10.7|31.2|28.3|60.6%|31.9%|
|2026_06_TEN_IND|TEN|19.9|60.4|10.7|30.5|25.6|39.4%|31.9%|
|2026_06_WAS_SF|SF|29.8|63.5|10.4|30.4|30.4|74.4%|35.2%|
|2026_06_WAS_SF|WAS|17.6|60.7|10.3|31.1|25.2|25.6%|35.2%|

## Analyst consumption

An optional embedded outlook validates hash/source/model/cutoff/kickoff and canonical game identity. Both formats retain shared saved context and conservation audits. Captain uses paired conditional budgets only when supported and within existing ratio bounds; otherwise explicitly retains the old sensitivity fallback. Conditional player fantasy elasticity, receiving concentration and portfolio weights remain design assumptions. Empirical game-event probabilities are neither individual ceilings nor lineup-win probabilities. Missing historical role measurements leave unallocated volume, never fabricated targets.

The real Sunday preview uses the saved513-player preliminary snapshot with its questionable-player exclusions; Captain uses dated SEA–DEN frozen projections. These previews write no database or live artifacts and do not certify readiness. See classic_preview.json/showdown_preview.json and the separately saved packets.

| Offline format | Status | Saved lineups |
|---|---|---:|
|CLASSIC|completed|2|
|SHOWDOWN|completed|2|

## Reproduction and validation

From repository root:

```sh
PYTHONPATH=. .venv/bin/python -m pytest backend/app/tests/product/test_team_game_outlook.py backend/app/tests/product/test_analyst_scenarios.py backend/app/tests/product/test_captain_analyst.py backend/app/tests/product/test_analyst_packet_routes.py -q
PYTHONPATH=. .venv/bin/python research/team_game_outlook_20261013/run.py
PYTHONPATH=. .venv/bin/python research/team_game_outlook_20261013/examples.py
PYTHONPATH=. .venv/bin/python research/team_game_outlook_20261013/report.py
```

Full replay should use a new versioned sibling study directory with run.py/SPECIFICATION.md copied there; keep existing outputs and source hashes. The immutable V3 sources remain unchanged. Model fitting/evaluation took 1.66s;4096 empirical draws/game, one20-feature model and two prior-validation choices. Test/model/packet hashes are in delivery_manifest.json. No dependencies installed.

Next: freeze actual forward predictions and current source clocks, evaluate calibration on new normal-week games, compare market-only and history baselines using captured market snapshots, and model injury/QB/role uncertainty separately. The initial score regression does not beat simple history, so no production promotion is justified.
