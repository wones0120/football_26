# Classic opportunity projection repair

Research only. Default remains `legacy_v1`; **do not promote `team_window_v2` yet**. No server restart, active projection update, optimizer scoring change or database mutation was performed. Original Week 5 snapshots and the root-cause audit are unchanged.

The general allocation defect is confirmed and repaired behind an explicit opt-in policy. Frozen Week 5 results support 17.00 carries for Gibbs and 8.00 targets for Wilson. Available historical validation does **not** establish that the complete corrected projection pipeline is better. The restricted-source Week 4 comparison has worse MAE and opportunity errors despite a small RMSE improvement, but cannot isolate allocation quality because its original raw-input parity fails.

## Root cause and implementation

`canonical_projection_inputs.attach_lagged_opportunity_features` previously used each player’s last three appearances, including previous-team and stale workloads. `apply_pregame_projection_context` divided these incompatible shares by their pooled sum when above 1.0, then removed unavailable players’ assignments. Unavailable old-team history could also activate a team-wide opportunity anchor. `predictions.apply_opportunity_point_adjustment` then blended the distorted workload anchor into the historical/model mean at 55%. These are upstream projection paths; optimizer exclusions did not cause the defect.

The repair changes only `canonical_projection_inputs.py`, `predictions.py`, the new `opportunity_history.py` and the default-off configuration in `config.py`. It uses canonical IDs, current salary-team membership after the target-team override, normalized team abbreviations and one common last-three-team-game window strictly before the target period. Source revisions received after the cutoff are excluded before canonical deduplication. FB statistics join the RB denominator, matching DraftKings positions. Historical WR/QB carries cannot be translated into the RB pool.

Shares are aggregate same-team player counts divided by aggregate team counts over that common window. A player absent from a known team game contributes no observed workload for that game. No same-team rows at all remains missing evidence; its public projected count is unknown, not a confident zero. Explicit sourced current counts/shares can support new roles. Same-team observations after a trade are averaged over the shared window, without importing the former team’s role. Prior-season fallback remains possible when recent-season observations were not available; this is an important remaining freshness limitation.

Measured shares are not inflated to exhaust the eligible salary pool. Availability removes genuine same-team workload; stale or other-team history has zero vacated share. Explicit counts override supported player estimates; other estimates may be reduced to respect team capacity. Redistribution retains existing evidence/assumption requirements and is capped by both genuine vacated work and remaining capacity. No player-specific rules were added. Every team/opportunity audit includes historical shares, unrepresented volume, removed share, requested/actual redistribution, recipient support, allocated and unallocated volume.

Anchors activate for explicit current opportunity evidence or genuinely removed same-team work, and only for players with relevant measured or explicit workload evidence. A former-team ghost alone no longer activates them. The veteran 55% and low-history 70% coefficients, fitted isotonic anchors, model weights and residual calibration profiles are unchanged. No coefficient tuning was attempted.

Configuration: `PLAYER_OPPORTUNITY_ALLOCATION_POLICY=legacy_v1` is the default. `team_window_v2` is reserved for research. Production `load_inputs` records policy/window lineage; direct `prepare_inputs` callers retain their existing default unless explicitly opted in. Future opt-in training would rebuild opportunity-derived features; this experiment deliberately keeps fitted training data, weights and profiles fixed.

## Frozen replay and Gibbs/Wilson calculations

Projection run `f3a3b0d0-30e7-48fa-a968-9889cccf927f`; cutoff `2026-10-09T21:56:16.351300Z`; all 310 saved scoring players were replayed. All 1,486 archived baseline mean/P10/P90 outputs across the four fitted snapshots reproduce with maximum error **0.0**. Independently rebuilding Week 5 legacy historical carry/target counts and shares from the archived raw versions matches every saved base input with maximum error **0.0** (`source_replay_parity.json`). Only opportunity inputs and derived role importance/completeness change in model scoring; assertions hold every other fitted feature fixed. Original availability, markets, explicit context, model/training rows and residual profiles remain frozen. Market corrections are retained exactly.

| Player | Carries | Targets | RB carry share | Target share | Mean | P10 | P90 | New anchor | New weight |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Jahmyr Gibbs | 10.76 → 17.00 | 7.05 → 7.67 | 0.56 → 0.88 | 0.18 → 0.19 | 19.38 → 23.87 | 8.86 → 13.35 | 32.50 → 37.00 | ? | 0.00 |
| Garrett Wilson | ? → ? | 5.16 → 8.00 | 0.00 → 0.00 | 0.18 → 0.28 | 12.21 → 14.82 | 1.33 → 3.94 | 25.09 → 27.70 | 13.86 | 0.55 |


Gibbs: DET Week 2–4 carries total 51; current-team RB/FB carries total 58. Share = 51/58 = 87.93%; team volume = 58/3 = 19.33; expected carries = 17.00. His 23 targets yield 7.67 per game. Pacheco’s KC workload contributes nothing to DET’s denominator or vacated work. DET has no genuine removed RB workload in this window, so the phantom 55% anchor activation disappears. His unchanged pre-opportunity mean becomes his final mean.

Wilson: NYJ Week 2–4 targets total 24 out of 87, giving 27.59% × 29.00 = 8.00 targets. Genuine same-team unavailable history remains: 7.33 targets unallocated, versus 9.72 previously. The corrected workload anchor still receives 55%; the remaining difference from his pre-opportunity mean reflects this shared model mechanism, not historical denominator dilution. No unsupported targets were automatically redistributed to him.

## Full-pool impact and anomalies

234 players change mean: 182 increase and 52 decrease. Materiality means |Δmean| ≥ 1 point, |Δsupported projected carries/targets| ≥ 1, or withdrawal of a prior ≥1-count forecast because same-team evidence is missing. 150 players meet that rule. This does not claim that every increase is credible or every decrease is desirable.

The complete CSV includes canonical IDs, raw feature counts, projected counts, shares, availability, roles, history windows, means and quantiles. `?` in the table below means unavailable or inapplicable projected count. Stored zero allocation for missing evidence is bookkeeping only. An asterisk marks materiality; `missing` flags no same-team history. QB/DST means remain unchanged; their historical count features are not RB allocation forecasts.

Largest increases:

| Player | Role | Mean change | History |
| --- | --- | --- | --- |
| Darius Slayton | expected_backup | +5.60 | no_same_team_window_history |
| Sam LaPorta | expected_starter | +4.97 | same_team_common_window |
| Christian McCaffrey | expected_starter | +4.86 | same_team_common_window |
| Denzel Boston | expected_starter | +4.72 | same_team_common_window |
| Amon-Ra St. Brown | expected_starter | +4.59 | same_team_common_window |
| Jahmyr Gibbs | expected_starter | +4.50 | same_team_common_window |
| Chris Olave | expected_starter | +4.28 | same_team_common_window |
| Aaron Jones Sr. | expected_starter | +4.26 | same_team_common_window |


Largest decreases:

| Player | Role | Mean change | History |
| --- | --- | --- | --- |
| Austin Ekeler | expected_backup | -3.21 | same_team_common_window |
| Kevin Austin Jr. | expected_backup | -2.98 | same_team_common_window |
| Nico Collins | expected_starter | -2.92 | same_team_common_window |
| Justin Jefferson | expected_starter | -2.59 | same_team_common_window |
| Rico Dowdle | expected_backup | -2.45 | same_team_common_window |
| Devin Singletary | expected_backup | -2.21 | same_team_common_window |
| Drew Sample | expected_backup | -1.82 | same_team_common_window |
| Mike Gesicki | expected_starter | -1.54 | same_team_common_window |


Review flags are exported in `anomaly_flags.csv`: all missing-history players, materially changed backups and unavailable players. Darius Slayton is an especially important example: his mean increases after a previously unsupported low anchor is removed, while his workload becomes unknown. This restores the historical/model fallback but does not validate an expanded current role. Supported-backup reductions such as Austin Ekeler and Kevin Austin Jr. also require football review. No excluded unavailable player is reintroduced into the optimizer pool; excluded RB carries and skill targets remain zero.

Full comparison, sorted by absolute mean change:

| Player | Team/Pos | Salary | Carries | Targets | Carry share | Target share | Mean | Δmean | P10 | P90 | Flag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Darius Slayton* | IND/WR | 3300 | ? → ? | 3.08 → ? | 0.00 → 0.00 | 0.10 → 0.00 | 6.71 → 12.31 | +5.60 | 0.00 → 1.43 | 18.11 → 25.19 | missing |
| Sam LaPorta* | DET/TE | 4900 | ? → ? | 6.61 → 8.00 | 0.00 → 0.00 | 0.17 → 0.20 | 14.28 → 19.25 | +4.97 | 5.50 → 10.47 | 23.74 → 28.71 | expected_starter |
| Christian McCaffrey* | SF/RB | 8200 | 7.40 → 13.33 | 2.08 → 4.67 | 0.36 → 0.66 | 0.09 → 0.18 | 13.13 → 17.99 | +4.86 | 7.08 → 7.95 | 21.16 → 29.22 | expected_starter |
| Denzel Boston* | CLE/WR | 5200 | ? → ? | 3.70 → 6.00 | 0.00 → 0.00 | 0.12 → 0.19 | 10.04 → 14.76 | +4.72 | 0.23 → 4.95 | 21.44 → 26.16 | expected_starter |
| Amon-Ra St. Brown* | DET/WR | 7900 | ? → ? | 9.50 → 10.67 | 0.00 → 0.00 | 0.24 → 0.27 | 19.65 → 24.24 | +4.59 | 8.77 → 13.37 | 32.53 → 37.12 | expected_starter |
| Jahmyr Gibbs* | DET/RB | 9800 | 10.76 → 17.00 | 7.05 → 7.67 | 0.56 → 0.88 | 0.18 → 0.19 | 19.38 → 23.87 | +4.50 | 8.86 → 13.35 | 32.50 → 37.00 | expected_starter |
| Chris Olave* | NO/WR | 7700 | ? → ? | 7.14 → 11.67 | 0.00 → 0.00 | 0.18 → 0.29 | 15.26 → 19.54 | +4.28 | 4.38 → 8.67 | 28.14 → 32.42 | expected_starter |
| Aaron Jones Sr.* | MIN/RB | 6500 | 7.03 → 20.00 | 2.82 → 4.67 | 0.31 → 0.87 | 0.11 → 0.18 | 12.04 → 16.30 | +4.26 | 1.52 → 5.78 | 25.16 → 29.42 | expected_starter |
| Jeremiyah Love* | ARI/RB | 6100 | 5.58 → 14.67 | 2.02 → 3.00 | 0.27 → 0.72 | 0.05 → 0.08 | 9.07 → 13.25 | +4.18 | 3.02 → 3.21 | 17.10 → 24.48 | expected_starter |
| Harold Fannin Jr.* | CLE/TE | 4400 | ? → ? | 4.20 → 6.67 | 0.00 → 0.00 | 0.14 → 0.22 | 10.18 → 13.57 | +3.39 | 1.40 → 4.79 | 19.64 → 23.03 | expected_starter |
| Josh Downs* | IND/WR | 6000 | ? → ? | 4.31 → 8.00 | 0.00 → 0.00 | 0.14 → 0.26 | 9.49 → 12.86 | +3.37 | 0.00 → 1.98 | 22.37 → 25.74 | expected_starter |
| Mike Evans* | SF/WR | 6500 | ? → ? | 2.43 → 5.67 | 0.00 → 0.00 | 0.10 → 0.22 | 8.49 → 11.84 | +3.35 | 0.80 → 2.02 | 18.18 → 23.23 | expected_starter |
| George Kittle* | SF/TE | 5200 | ? → ? | 2.50 → 5.67 | 0.00 → 0.00 | 0.11 → 0.22 | 8.95 → 12.29 | +3.34 | 2.73 → 4.18 | 16.14 → 20.20 | expected_starter |
| Alvin Kamara* | NO/RB | 5400 | 5.23 → 8.33 | 2.89 → 4.67 | 0.26 → 0.41 | 0.07 → 0.12 | 7.78 → 11.03 | +3.24 | 1.73 → 4.98 | 15.81 → 19.06 | expected_starter |
| Michael Wilson* | ARI/WR | 6200 | ? → ? | 8.13 → 12.33 | 0.00 → 0.00 | 0.22 → 0.33 | 15.11 → 18.35 | +3.24 | 4.24 → 7.47 | 27.99 → 31.23 | expected_starter |
| Jacory Croskey-Merritt* | WAS/RB | 4900 | 8.65 → 13.33 | 1.17 → 2.00 | 0.38 → 0.58 | 0.04 → 0.06 | 7.77 → 10.99 | +3.22 | 1.72 → 0.95 | 15.80 → 22.22 | expected_starter |
| Cam Skattebo* | NYG/RB | 6000 | 11.82 → 16.67 | 2.22 → 3.00 | 0.46 → 0.65 | 0.08 → 0.11 | 11.49 → 14.71 | +3.22 | 1.46 → 4.67 | 22.72 → 25.94 | expected_starter |
| Austin Ekeler* | WAS/RB | 4400 | 6.03 → 1.33 | 1.73 → 0.67 | 0.26 → 0.06 | 0.05 → 0.02 | 7.02 → 3.81 | -3.21 | 0.97 → 0.00 | 15.05 → 11.84 | expected_backup |
| Xavier Hutchinson* | HOU/WR | 4000 | ? → ? | 3.83 → 6.67 | 0.00 → 0.00 | 0.11 → 0.20 | 7.13 → 10.18 | +3.05 | 0.00 → 2.49 | 16.82 → 19.87 | expected_backup |
| Kevin Austin Jr.* | NO/WR | 3000 | ? → ? | 3.85 → 0.33 | 0.00 → 0.00 | 0.10 → 0.01 | 4.88 → 1.90 | -2.98 | 0.69 → 0.00 | 10.37 → 4.44 | expected_backup |
| Nico Collins* | HOU/WR | 7500 | ? → ? | 4.98 → 2.67 | 0.00 → 0.00 | 0.15 → 0.08 | 13.38 → 10.46 | -2.92 | 5.69 → 2.78 | 23.07 → 20.16 | expected_starter |
| Christian Watson* | GB/WR | 6400 | ? → ? | 4.72 → 8.00 | 0.00 → 0.00 | 0.13 → 0.22 | 11.79 → 14.70 | +2.90 | 1.98 → 4.88 | 23.19 → 26.09 | expected_starter |
| Matthew Golden* | GB/WR | 5700 | ? → ? | 4.72 → 8.33 | 0.00 → 0.00 | 0.13 → 0.23 | 10.45 → 13.36 | +2.90 | 0.00 → 2.48 | 23.33 → 26.24 | expected_backup |
| Dalton Schultz* | HOU/TE | 4000 | ? → ? | 2.98 → 6.33 | 0.00 → 0.00 | 0.09 → 0.19 | 7.48 → 10.18 | +2.71 | 1.26 → 3.96 | 14.66 → 17.37 | expected_starter |
| Garrett Wilson* | NYJ/WR | 6600 | ? → ? | 5.16 → 8.00 | 0.00 → 0.00 | 0.18 → 0.28 | 12.21 → 14.82 | +2.61 | 1.33 → 3.94 | 25.09 → 27.70 | expected_starter |
| Justin Jefferson* | MIN/WR | 7300 | ? → ? | 4.60 → 2.67 | 0.00 → 0.00 | 0.18 → 0.10 | 11.14 → 8.55 | -2.59 | 3.45 → 0.86 | 20.83 → 18.24 | expected_starter |
| Jameson Williams* | DET/WR | 5900 | ? → ? | 4.55 → 5.33 | 0.00 → 0.00 | 0.11 → 0.13 | 10.55 → 13.09 | +2.54 | 0.74 → 3.28 | 21.95 → 24.49 | expected_backup |
| Rico Dowdle* | PIT/RB | 4700 | 5.59 → 2.33 | 2.47 → 0.67 | 0.29 → 0.12 | 0.07 → 0.02 | 6.88 → 4.43 | -2.45 | 0.83 → 0.00 | 14.91 → 12.46 | expected_backup |
| Quinshon Judkins* | CLE/RB | 5700 | 9.10 → 15.67 | 2.84 → 4.67 | 0.51 → 0.87 | 0.09 → 0.15 | 11.62 → 14.05 | +2.44 | 5.57 → 3.53 | 19.64 → 27.18 | expected_starter |
| Emanuel Wilson* | SEA/RB | 5300 | 9.05 → 17.00 | 1.87 → 1.67 | 0.33 → 0.61 | 0.06 → 0.05 | 9.61 → 11.95 | +2.34 | 3.56 → 1.91 | 17.64 → 23.18 | expected_starter |
| Tucker Kraft* | GB/TE | 4700 | ? → ? | 3.45 → 6.00 | 0.00 → 0.00 | 0.09 → 0.16 | 9.16 → 11.45 | +2.29 | 1.05 → 3.34 | 17.07 → 19.36 | expected_starter |
| Romeo Doubs* | NE/WR | 5000 | ? → ? | 3.87 → 5.67 | 0.00 → 0.00 | 0.13 → 0.20 | 8.97 → 11.20 | +2.24 | 1.28 → 3.52 | 18.66 → 20.90 | expected_starter |
| Devin Singletary* | NYG/RB | 4000 | 4.40 → 1.00 | 1.07 → 0.33 | 0.17 → 0.04 | 0.04 → 0.01 | 5.48 → 3.28 | -2.21 | 0.00 → 0.47 | 13.51 → 5.67 | expected_backup |
| Antonio Williams* | WAS/WR | 3800 | ? → ? | 2.98 → 5.00 | 0.00 → 0.00 | 0.09 → 0.15 | 5.87 → 8.03 | +2.16 | 1.67 → 3.84 | 11.36 → 13.52 | expected_backup |
| Wan'Dale Robinson* | TEN/WR | 4500 | ? → ? | 3.76 → 5.67 | 0.00 → 0.00 | 0.14 → 0.21 | 7.90 → 10.00 | +2.10 | 0.21 → 2.31 | 17.59 → 19.69 | expected_backup |
| Jonathan Taylor* | IND/RB | 7800 | 18.65 → 22.33 | 2.04 → 3.67 | 0.71 → 0.85 | 0.07 → 0.12 | 16.66 → 18.74 | +2.08 | 6.14 → 8.22 | 29.78 → 31.86 | expected_starter |
| Mitch Tinsley* | CIN/WR | 3300 | ? → ? | 0.00 → ? | 0.00 → 0.00 | 0.00 → 0.00 | 2.08 → 4.13 | +2.05 | 0.00 → 0.00 | 9.55 → 11.60 | missing |
| Ashton Jeanty* | LV/RB | 7200 | 15.51 → 18.33 | 4.15 → 6.00 | 0.65 → 0.73 | 0.12 → 0.17 | 16.72 → 18.74 | +2.03 | 6.20 → 8.23 | 29.84 → 31.87 | expected_starter |
| Courtland Sutton* | DEN/WR | 4600 | ? → ? | 4.09 → 5.67 | 0.00 → 0.00 | 0.13 → 0.17 | 7.55 → 9.53 | +1.98 | 0.00 → 0.00 | 18.94 → 20.93 | expected_backup |
| Tre Tucker* | LV/WR | 4800 | ? → ? | 4.42 → 6.33 | 0.00 → 0.00 | 0.13 → 0.18 | 9.22 → 11.16 | +1.94 | 1.54 → 3.48 | 18.92 → 20.86 | expected_starter |
| Deebo Samuel Sr.* | SF/WR | 5500 | ? → ? | 1.49 → 3.33 | 0.00 → 0.00 | 0.06 → 0.13 | 6.47 → 8.39 | +1.93 | 0.00 → 0.71 | 16.16 → 18.09 | expected_backup |
| Chase Brown* | CIN/RB | 6900 | 12.14 → 14.00 | 4.69 → 6.00 | 0.73 → 0.84 | 0.12 → 0.15 | 17.33 → 19.20 | +1.87 | 6.81 → 8.69 | 30.46 → 32.33 | expected_starter |
| Tyjae Spears* | TEN/RB | 4600 | 2.36 → 4.00 | 1.04 → 1.00 | 0.11 → 0.18 | 0.04 → 0.04 | 4.43 → 6.30 | +1.87 | 0.00 → 0.25 | 12.46 → 14.33 | expected_backup |
| Malik Nabers* | NYG/WR | 6300 | ? → ? | 4.13 → 5.67 | 0.00 → 0.00 | 0.15 → 0.21 | 11.12 → 12.98 | +1.87 | 3.43 → 5.29 | 20.81 → 22.67 | expected_starter |
| Omarion Hampton* | LAC/RB | 6000 | 12.82 → 15.67 | 1.15 → 1.67 | 0.51 → 0.62 | 0.04 → 0.06 | 10.88 → 12.73 | +1.85 | 4.83 → 2.69 | 18.91 → 23.96 | expected_starter |
| Tre' Harris* | LAC/WR | 4100 | ? → ? | 3.37 → 5.00 | 0.00 → 0.00 | 0.12 → 0.17 | 6.97 → 8.80 | +1.83 | 0.00 → 1.11 | 16.66 → 18.49 | expected_backup |
| Devaughn Vele* | NO/WR | 5200 | ? → ? | 4.48 → 7.33 | 0.00 → 0.00 | 0.11 → 0.18 | 10.95 → 12.77 | +1.83 | 1.14 → 2.96 | 22.34 → 24.17 | expected_backup |
| Drew Sample* | CIN/TE | 2600 | ? → ? | 2.45 → 0.67 | 0.00 → 0.00 | 0.06 → 0.02 | 4.09 → 2.27 | -1.82 | 0.40 → 0.00 | 8.62 → 6.80 | expected_backup |
| Keaton Mitchell* | LAC/RB | 4500 | 6.53 → 7.67 | 2.20 → 3.33 | 0.26 → 0.30 | 0.08 → 0.11 | 6.49 → 8.29 | +1.80 | 0.44 → 2.24 | 14.52 → 16.32 | expected_backup |
| Malik Washington* | MIA/WR | 4600 | ? → ? | 4.54 → 6.67 | 0.00 → 0.00 | 0.18 → 0.27 | 9.48 → 11.27 | +1.79 | 0.00 → 0.39 | 22.36 → 24.15 | expected_starter |
| Ollie Gordon II* | MIA/RB | 5300 | 7.93 → 9.67 | 1.16 → 1.67 | 0.40 → 0.49 | 0.05 → 0.07 | 7.32 → 9.09 | +1.77 | 1.27 → 3.04 | 15.35 → 17.12 | expected_starter |
| Jordan Addison* | MIN/WR | 5800 | ? → ? | 4.70 → 6.67 | 0.00 → 0.00 | 0.18 → 0.26 | 10.12 → 11.87 | +1.75 | 0.00 → 0.99 | 22.99 → 24.74 | expected_backup |
| Dohnte Meyers* | CIN/WR | 3500 | ? → ? | 3.74 → 5.00 | 0.00 → 0.00 | 0.09 → 0.12 | 5.78 → 7.53 | +1.75 | 1.58 → 3.33 | 11.27 → 13.02 | expected_backup |
| Robert Henry Jr.* | SEA/RB | 4000 | 0.00 → ? | 0.00 → ? | 0.00 → 0.00 | 0.00 → 0.00 | 1.79 → 3.52 | +1.73 | 0.00 → 0.00 | 7.40 → 9.13 | missing |
| Trey McBride* | ARI/TE | 6700 | ? → ? | 7.85 → 11.00 | 0.00 → 0.00 | 0.21 → 0.30 | 15.14 → 16.86 | +1.72 | 6.36 → 8.08 | 24.60 → 26.32 | expected_starter |
| Isaiah Likely* | NYG/TE | 4300 | ? → ? | 6.11 → 9.00 | 0.00 → 0.00 | 0.22 → 0.33 | 10.41 → 12.12 | +1.71 | 1.64 → 3.35 | 19.87 → 21.58 | expected_starter |
| Brock Bowers* | LV/TE | 7000 | ? → ? | 7.26 → 8.00 | 0.00 → 0.00 | 0.21 → 0.22 | 14.51 → 16.22 | +1.71 | 5.73 → 7.44 | 23.97 → 25.68 | expected_starter |
| Jared Wayne* | HOU/WR | 3000 | ? → ? | 2.04 → 3.67 | 0.00 → 0.00 | 0.06 → 0.11 | 3.45 → 5.09 | +1.64 | 0.00 → 0.00 | 8.69 → 10.32 | expected_backup |
| Michael Mayer* | LV/TE | 3500 | ? → ? | 3.66 → 5.67 | 0.00 → 0.00 | 0.10 → 0.16 | 8.89 → 10.46 | +1.57 | 0.78 → 2.35 | 16.80 → 18.37 | expected_backup |
| Kayshon Boutte* | HOU/WR | 3900 | ? → ? | 2.09 → 3.67 | 0.00 → 0.00 | 0.06 → 0.11 | 4.91 → 6.47 | +1.56 | 0.00 → 1.23 | 10.15 → 11.71 | expected_backup |
| Jerry Jeudy* | CLE/WR | 3700 | ? → ? | 1.94 → 1.33 | 0.00 → 0.00 | 0.06 → 0.04 | 4.51 → 6.07 | +1.55 | 0.00 → 0.83 | 9.75 → 11.30 | expected_backup |
| Mike Gesicki* | CIN/TE | 4100 | ? → ? | 4.23 → 2.67 | 0.00 → 0.00 | 0.10 → 0.07 | 8.72 → 7.17 | -1.54 | 5.48 → 3.93 | 14.62 → 13.08 | expected_starter |
| Juwan Johnson* | NO/TE | 4500 | ? → ? | 3.96 → 6.67 | 0.00 → 0.00 | 0.10 → 0.17 | 9.84 → 11.38 | +1.54 | 3.62 → 5.16 | 17.02 → 18.57 | expected_starter |
| Tyler Warren* | IND/TE | 5000 | ? → ? | 3.96 → 7.33 | 0.00 → 0.00 | 0.13 → 0.23 | 10.83 → 12.38 | +1.54 | 2.06 → 3.60 | 20.29 → 21.84 | expected_starter |
| Riley Nowakowski* | PIT/RB | 4000 | 0.00 → ? | 0.00 → ? | 0.00 → 0.00 | 0.00 → 0.00 | 1.60 → 3.09 | +1.48 | 0.00 → 0.28 | 4.00 → 5.48 | missing |
| Jaylin Noel* | HOU/WR | 3200 | ? → ? | 1.85 → 3.33 | 0.00 → 0.00 | 0.05 → 0.10 | 4.31 → 5.78 | +1.47 | 0.11 → 1.58 | 9.80 → 11.27 | expected_backup |
| Laquon Treadwell* | IND/WR | 3600 | ? → ? | 1.92 → 3.33 | 0.00 → 0.00 | 0.06 → 0.11 | 4.12 → 5.60 | +1.47 | 0.00 → 0.35 | 9.36 → 10.83 | expected_backup |
| Mason Taylor* | NYJ/TE | 2500 | ? → ? | 3.20 → ? | 0.00 → 0.00 | 0.11 → 0.00 | 5.48 → 6.95 | +1.47 | 0.00 → 0.73 | 12.66 → 14.14 | missing |
| Colston Loveland* | CHI/TE | 4600 | ? → ? | 4.38 → 5.33 | 0.00 → 0.00 | 0.14 → 0.17 | 9.75 → 11.22 | +1.47 | 1.65 → 3.11 | 17.66 → 19.13 | expected_starter |
| Teagan Quitoriano* | ARI/TE | 2500 | ? → ? | 0.26 → ? | 0.00 → 0.00 | 0.01 → 0.00 | 1.14 → 2.59 | +1.45 | 0.00 → 0.00 | 2.23 → 8.50 | missing |
| Kenyon Sadiq* | NYJ/TE | 3800 | ? → ? | 3.59 → 5.00 | 0.00 → 0.00 | 0.12 → 0.17 | 8.09 → 9.54 | +1.45 | 1.87 → 3.32 | 15.27 → 16.72 | expected_starter |
| Dyami Brown* | WAS/WR | 3100 | ? → ? | 2.15 → 3.67 | 0.00 → 0.00 | 0.07 → 0.11 | 4.00 → 5.45 | +1.45 | 0.00 → 0.21 | 9.24 → 10.69 | expected_backup |
| Skyy Moore* | GB/WR | 3200 | ? → ? | 2.15 → 4.00 | 0.00 → 0.00 | 0.06 → 0.11 | 3.57 → 5.02 | +1.45 | 0.00 → 0.82 | 9.06 → 10.51 | expected_backup |
| Tanner Arkin* | NE/TE | 2500 | ? → ? | 0.00 → ? | 0.00 → 0.00 | 0.00 → 0.00 | 1.51 → 2.95 | +1.44 | 0.00 → 0.00 | 7.42 → 8.86 | missing |
| Bam Knight* | ARI/RB | 4000 | 2.33 → 0.67 | 1.13 → 0.00 | 0.11 → 0.03 | 0.03 → 0.00 | 3.60 → 2.17 | -1.43 | 0.00 → 0.00 | 11.63 → 4.56 | expected_backup |
| Reggie Virgil* | ARI/WR | 3000 | ? → ? | 0.00 → ? | 0.00 → 0.00 | 0.00 → 0.00 | 1.81 → 3.24 | +1.43 | 0.00 → 0.00 | 9.28 → 10.71 | missing |
| Kendrick Bourne* | ARI/WR | 3400 | ? → ? | 3.25 → 2.00 | 0.00 → 0.00 | 0.09 → 0.05 | 5.56 → 4.16 | -1.40 | 0.00 → 0.00 | 15.26 → 9.40 | expected_backup |
| Kylen Granson* | TEN/TE | 2500 | ? → ? | 1.00 → ? | 0.00 → 0.00 | 0.04 → 0.00 | 1.48 → 2.88 | +1.40 | 0.00 → 0.00 | 7.38 → 8.78 | missing |
| MarShawn Lloyd* | GB/RB | 4800 | 3.43 → 5.67 | 2.06 → 3.33 | 0.23 → 0.38 | 0.06 → 0.09 | 6.01 → 7.39 | +1.38 | 0.00 → 1.34 | 14.04 → 15.42 | expected_starter |
| David Montgomery* | HOU/RB | 5800 | 4.88 → 9.00 | 0.75 → 1.33 | 0.32 → 0.59 | 0.02 → 0.04 | 6.78 → 8.16 | +1.38 | 0.73 → 0.00 | 14.81 → 19.39 | expected_starter |
| Marvin Harrison Jr.* | ARI/WR | 4400 | ? → ? | 2.10 → 3.33 | 0.00 → 0.00 | 0.06 → 0.09 | 5.19 → 6.56 | +1.37 | 0.00 → 0.00 | 14.89 → 16.26 | expected_backup |
| Marlin Klein* | HOU/TE | 2500 | ? → ? | 0.51 → ? | 0.00 → 0.00 | 0.02 → 0.00 | 1.28 → 2.61 | +1.33 | 0.00 → 0.49 | 2.37 → 3.70 | missing |
| Gunnar Helm* | TEN/TE | 2800 | ? → ? | 1.82 → 2.33 | 0.00 → 0.00 | 0.07 → 0.09 | 3.97 → 5.30 | +1.33 | 0.00 → 0.00 | 11.88 → 13.21 | expected_starter |
| T.J. Hockenson* | MIN/TE | 4800 | ? → ? | 4.46 → 7.00 | 0.00 → 0.00 | 0.17 → 0.27 | 9.89 → 11.21 | +1.32 | 3.67 → 2.43 | 17.07 → 20.67 | expected_starter |
| Marvin Mims Jr.* | DEN/WR | 3400 | ? → ? | 2.34 → 1.00 | 0.00 → 0.00 | 0.07 → 0.03 | 4.45 → 3.14 | -1.32 | 0.26 → 0.00 | 9.94 → 8.63 | expected_backup |
| Woody Marks* | HOU/RB | 4800 | 3.53 → 6.33 | 1.24 → 2.67 | 0.23 → 0.41 | 0.04 → 0.08 | 5.96 → 7.28 | +1.31 | 0.00 → 1.23 | 13.99 → 15.31 | expected_backup |
| Jalen Tolbert* | MIA/WR | 3000 | ? → ? | 1.85 → 0.33 | 0.00 → 0.00 | 0.07 → 0.01 | 3.04 → 1.75 | -1.29 | 0.00 → 0.00 | 8.53 → 7.25 | expected_backup |
| Raheim Sanders* | CLE/RB | 4700 | 1.00 → 1.67 | 1.69 → 2.67 | 0.06 → 0.09 | 0.06 → 0.09 | 3.96 → 5.24 | +1.29 | 0.00 → 0.00 | 11.99 → 13.27 | expected_backup |
| Elic Ayomanor* | TEN/WR | 3000 | ? → ? | 2.03 → 2.33 | 0.00 → 0.00 | 0.08 → 0.09 | 4.21 → 5.49 | +1.28 | 0.00 → 0.25 | 9.44 → 10.73 | expected_backup |
| Erick All Jr.* | CIN/TE | 2500 | ? → ? | 2.29 → 1.00 | 0.00 → 0.00 | 0.06 → 0.02 | 3.17 → 1.90 | -1.27 | 0.00 → 0.00 | 9.08 → 2.99 | expected_backup |
| Tyler Allgeier* | ARI/RB | 5100 | 2.02 → 5.00 | 1.77 → 2.67 | 0.10 → 0.25 | 0.05 → 0.07 | 5.79 → 7.06 | +1.27 | 0.00 → 1.01 | 13.81 → 15.09 | expected_backup |
| Kaleb Johnson* | GB/RB | 4600 | 3.89 → 6.67 | 0.41 → 1.00 | 0.26 → 0.44 | 0.01 → 0.03 | 4.34 → 5.61 | +1.27 | 0.00 → 0.00 | 12.37 → 13.64 | expected_backup |
| Kalif Raymond* | CHI/WR | 3900 | ? → ? | 3.77 → 4.67 | 0.00 → 0.00 | 0.12 → 0.15 | 7.30 → 8.57 | +1.26 | 0.00 → 0.88 | 17.00 → 18.26 | expected_backup |
| Calvin Ridley* | TEN/WR | 3500 | ? → ? | 1.48 → 1.67 | 0.00 → 0.00 | 0.06 → 0.06 | 3.45 → 4.71 | +1.26 | 0.00 → 0.00 | 8.69 → 9.95 | expected_backup |
| Michael Burton* | CLE/RB | 4000 | 0.00 → 0.00 | 0.00 → 0.33 | 0.00 → 0.00 | 0.00 → 0.01 | 1.58 → 2.83 | +1.25 | 0.00 → 0.03 | 3.97 → 5.23 | expected_starter |
| Oronde Gadsden II* | LAC/TE | 3600 | ? → ? | 2.88 → 4.33 | 0.00 → 0.00 | 0.10 → 0.15 | 6.04 → 7.29 | +1.24 | 2.80 → 4.05 | 11.95 → 13.19 | expected_backup |
| Dallen Bentley* | DEN/TE | 2500 | ? → ? | 0.00 → ? | 0.00 → 0.00 | 0.00 → 0.00 | 1.43 → 2.67 | +1.24 | 0.00 → 0.00 | 7.81 → 9.06 | missing |
| Bryce Lance* | NO/WR | 3000 | ? → ? | 1.70 → 3.00 | 0.00 → 0.00 | 0.04 → 0.08 | 3.38 → 4.57 | +1.20 | 0.00 → 0.00 | 8.61 → 9.81 | expected_backup |
| Evan Engram* | DEN/TE | 2800 | ? → ? | 1.80 → 2.67 | 0.00 → 0.00 | 0.06 → 0.08 | 3.40 → 4.58 | +1.18 | 0.00 → 0.89 | 7.93 → 9.11 | expected_starter |
| Luther Burden III* | CHI/WR | 4900 | ? → ? | 6.47 → 8.00 | 0.00 → 0.00 | 0.20 → 0.25 | 11.34 → 12.51 | +1.17 | 3.65 → 2.70 | 21.03 → 23.91 | expected_backup |
| Pierre Strong Jr.* | GB/RB | 4000 | 0.97 → ? | 1.26 → ? | 0.06 → 0.00 | 0.03 → 0.00 | 2.87 → 4.04 | +1.17 | 0.00 → 0.00 | 10.90 → 12.07 | missing |
| George Holani* | SEA/RB | 4500 | 2.63 → 4.67 | 1.56 → 2.33 | 0.09 → 0.17 | 0.05 → 0.08 | 4.68 → 5.85 | +1.17 | 0.00 → 0.00 | 12.71 → 13.88 | expected_backup |
| Jaxon Smith-Njigba* | SEA/WR | 8800 | ? → ? | 8.11 → 10.33 | 0.00 → 0.00 | 0.27 → 0.34 | 18.81 → 19.97 | +1.17 | 7.93 → 9.10 | 31.68 → 32.85 | expected_starter |
| Hunter Henry* | NE/TE | 3700 | ? → ? | 2.99 → 4.00 | 0.00 → 0.00 | 0.10 → 0.14 | 7.17 → 8.32 | +1.16 | 0.00 → 0.22 | 15.08 → 16.23 | expected_starter |
| Darnell Washington* | PIT/TE | 2900 | ? → ? | 3.16 → 3.67 | 0.00 → 0.00 | 0.09 → 0.10 | 6.13 → 7.28 | +1.15 | 0.00 → 1.06 | 13.32 → 14.47 | expected_starter |
| AJ Barner* | SEA/TE | 3200 | ? → ? | 3.05 → 4.33 | 0.00 → 0.00 | 0.10 → 0.14 | 7.12 → 8.27 | +1.15 | 0.00 → 0.16 | 15.03 → 16.18 | expected_starter |
| Jaylen Waddle* | DEN/WR | 6100 | ? → ? | 5.76 → 7.67 | 0.00 → 0.00 | 0.18 → 0.23 | 11.48 → 12.62 | +1.14 | 3.79 → 2.81 | 21.17 → 24.01 | expected_starter |
| Terry McLaurin* | WAS/WR | 5300 | ? → ? | 4.66 → 6.00 | 0.00 → 0.00 | 0.14 → 0.18 | 9.82 → 10.95 | +1.13 | 2.13 → 3.26 | 19.51 → 20.64 | expected_starter |
| Tony Pollard* | TEN/RB | 5600 | 9.76 → 15.67 | 2.15 → 3.00 | 0.44 → 0.71 | 0.08 → 0.11 | 10.55 → 11.68 | +1.13 | 4.50 → 1.64 | 18.58 → 22.91 | expected_starter |
| Tee Higgins* | CIN/WR | 7100 | ? → ? | 9.02 → 11.00 | 0.00 → 0.00 | 0.22 → 0.27 | 16.15 → 17.26 | +1.11 | 5.27 → 6.38 | 29.03 → 30.14 | expected_backup |
| Malachi Fields* | NYG/WR | 4300 | ? → ? | 2.45 → 3.67 | 0.00 → 0.00 | 0.09 → 0.13 | 6.07 → 7.18 | +1.11 | 0.00 → 0.00 | 15.77 → 16.87 | expected_backup |
| Chris Bell* | MIA/WR | 3600 | ? → ? | 2.39 → 3.67 | 0.00 → 0.00 | 0.10 → 0.15 | 4.50 → 5.61 | +1.11 | 0.00 → 0.00 | 14.19 → 15.30 | expected_backup |
| Keenan Allen* | IND/WR | 4300 | ? → ? | 3.61 → 4.67 | 0.00 → 0.00 | 0.12 → 0.15 | 7.46 → 8.57 | +1.11 | 0.00 → 0.88 | 17.15 → 18.26 | expected_backup |
| Cody White* | LV/WR | 3300 | ? → ? | 2.06 → 3.00 | 0.00 → 0.00 | 0.06 → 0.08 | 3.94 → 5.02 | +1.08 | 0.00 → 0.00 | 9.18 → 10.26 | expected_backup |
| Isaiah Williams* | NYJ/WR | 3700 | ? → ? | 2.65 → 3.67 | 0.00 → 0.00 | 0.09 → 0.13 | 6.29 → 7.36 | +1.07 | 0.00 → 0.00 | 15.99 → 17.05 | expected_backup |
| Jordan James* | SF/RB | 4000 | 2.75 → 1.33 | 0.20 → 0.00 | 0.14 → 0.07 | 0.01 → 0.00 | 3.11 → 2.04 | -1.07 | 0.00 → 0.00 | 11.14 → 4.44 | expected_backup |
| John Bates* | WAS/TE | 2500 | ? → ? | 1.60 → 0.33 | 0.00 → 0.00 | 0.05 → 0.01 | 2.83 → 1.78 | -1.05 | 0.00 → 0.00 | 8.74 → 7.69 | expected_backup |
| Kaelon Black* | SF/RB | 4700 | 3.10 → 5.67 | 0.14 → 0.33 | 0.15 → 0.28 | 0.01 → 0.01 | 3.63 → 4.67 | +1.04 | 0.00 → 0.00 | 11.66 → 12.70 | expected_backup |
| Drew Ogletree* | IND/TE | 2500 | ? → ? | 0.00 → ? | 0.00 → 0.00 | 0.00 → 0.00 | 1.34 → 2.38 | +1.04 | 0.00 → 0.00 | 7.72 → 8.76 | missing |
| Ja'Marr Chase* | CIN/WR | 8100 | ? → ? | 7.44 → 8.00 | 0.00 → 0.00 | 0.18 → 0.20 | 16.18 → 17.21 | +1.03 | 5.30 → 6.33 | 29.06 → 30.09 | expected_starter |
| Greg Dulcich* | MIA/TE | 3100 | ? → ? | 2.31 → 3.33 | 0.00 → 0.00 | 0.09 → 0.13 | 5.91 → 6.93 | +1.02 | 0.00 → 0.72 | 13.10 → 14.12 | expected_starter |
| Efton Chism III* | NE/WR | 3200 | ? → ? | 1.52 → 2.33 | 0.00 → 0.00 | 0.05 → 0.08 | 3.16 → 4.18 | +1.01 | 0.00 → 0.00 | 8.66 → 9.67 | expected_backup |
| Jaylen Warren* | PIT/RB | 6700 | 12.37 → 15.00 | 3.96 → 4.67 | 0.64 → 0.78 | 0.11 → 0.13 | 15.48 → 16.48 | +1.00 | 4.96 → 5.96 | 28.60 → 29.61 | expected_starter |
| D'Andre Swift* | CHI/RB | 6200 | 14.85 → 17.00 | 2.75 → 3.33 | 0.42 → 0.49 | 0.09 → 0.11 | 14.02 → 15.02 | +1.00 | 3.98 → 4.99 | 25.25 → 26.26 | expected_starter |
| Sione Vaki* | DET/RB | 4300 | 1.15 → 2.33 | 1.14 → 1.33 | 0.06 → 0.12 | 0.03 → 0.03 | 3.52 → 4.51 | +0.99 | 0.00 → 0.00 | 11.55 → 12.54 | expected_backup |
| Tory Horton | SEA/WR | 3000 | ? → ? | 2.22 → 1.33 | 0.00 → 0.00 | 0.07 → 0.04 | 4.91 → 3.93 | -0.98 | 0.72 → 0.00 | 10.40 → 9.42 | expected_backup |
| Rome Odunze* | CHI/WR | 4700 | ? → ? | 4.62 → 5.67 | 0.00 → 0.00 | 0.15 → 0.18 | 8.91 → 9.88 | +0.98 | 1.22 → 2.20 | 18.60 → 19.57 | expected_starter |
| Roman Wilson | PIT/WR | 3700 | ? → ? | 5.16 → 6.00 | 0.00 → 0.00 | 0.14 → 0.17 | 8.85 → 9.81 | +0.96 | 1.17 → 2.12 | 18.55 → 19.50 | expected_backup |
| Ladd McConkey* | LAC/WR | 5600 | ? → ? | 2.28 → 3.33 | 0.00 → 0.00 | 0.08 → 0.11 | 6.05 → 7.00 | +0.95 | 0.80 → 1.76 | 11.28 → 12.24 | expected_starter |
| Mo Alie-Cox* | IND/TE | 2500 | ? → ? | 1.45 → 0.33 | 0.00 → 0.00 | 0.05 → 0.01 | 2.72 → 1.77 | -0.95 | 0.00 → 0.00 | 8.63 → 2.86 | expected_backup |
| Jackson Meeks | DET/TE | 2500 | ? → ? | 0.00 → ? | 0.00 → 0.00 | 0.00 → 0.00 | 1.29 → 2.23 | +0.93 | 0.00 → 0.00 | 7.68 → 8.61 | missing |
| Adam Trautman* | DEN/TE | 2500 | ? → ? | 1.45 → 0.33 | 0.00 → 0.00 | 0.04 → 0.01 | 2.56 → 1.64 | -0.92 | 0.00 → 0.00 | 7.09 → 6.17 | expected_backup |
| Montorie Foster Jr. | SEA/WR | 3000 | ? → ? | 0.00 → ? | 0.00 → 0.00 | 0.00 → 0.00 | 1.52 → 2.43 | +0.92 | 0.00 → 0.00 | 6.75 → 7.67 | missing |
| Chig Okonkwo* | WAS/TE | 3300 | ? → ? | 2.45 → 1.33 | 0.00 → 0.00 | 0.07 → 0.04 | 5.48 → 4.57 | -0.90 | 0.00 → 0.89 | 12.66 → 9.10 | expected_starter |
| Mark Redman | GB/TE | 2500 | ? → ? | 1.40 → 0.67 | 0.00 → 0.00 | 0.04 → 0.02 | 2.34 → 1.44 | -0.90 | 0.22 → 0.00 | 3.43 → 2.53 | expected_backup |
| DeMario Douglas* | NE/WR | 3500 | ? → ? | 2.33 → 3.33 | 0.00 → 0.00 | 0.08 → 0.11 | 4.66 → 5.54 | +0.88 | 0.00 → 0.30 | 9.90 → 10.78 | expected_backup |
| Jahdae Walker* | CHI/WR | 3000 | ? → ? | 2.11 → ? | 0.00 → 0.00 | 0.07 → 0.00 | 3.40 → 4.26 | +0.85 | 0.00 → 0.06 | 8.90 → 9.75 | missing |
| Brandin Cooks | SF/WR | 3500 | ? → ? | 1.15 → 0.33 | 0.00 → 0.00 | 0.05 → 0.01 | 3.42 → 2.58 | -0.84 | 0.00 → 0.00 | 8.91 → 8.07 | expected_backup |
| Tyler Conklin* | DET/TE | 2500 | ? → ? | 1.75 → ? | 0.00 → 0.00 | 0.04 → 0.00 | 2.57 → 3.40 | +0.82 | 0.45 → 0.16 | 3.66 → 9.30 | missing |
| Kene Nwangwu* | NYJ/RB | 4000 | 2.45 → 0.00 | 0.29 → 0.00 | 0.14 → 0.00 | 0.01 → 0.00 | 2.20 → 1.38 | -0.82 | 0.00 → 0.00 | 10.23 → 3.78 | expected_backup |
| Rachaad White | WAS/RB | 5100 | 4.30 → 5.00 | 1.85 → 2.33 | 0.19 → 0.22 | 0.06 → 0.07 | 6.53 → 7.34 | +0.80 | 0.48 → 1.29 | 14.56 → 15.36 | expected_backup |
| Elijah Arroyo | SEA/TE | 2500 | ? → ? | 1.24 → 0.33 | 0.00 → 0.00 | 0.04 → 0.01 | 2.04 → 1.25 | -0.80 | 0.00 → 0.00 | 3.13 → 2.34 | expected_backup |
| Carnell Tate* | TEN/WR | 5300 | ? → ? | 6.67 → 8.67 | 0.00 → 0.00 | 0.25 → 0.32 | 12.37 → 13.15 | +0.78 | 1.49 → 2.27 | 25.24 → 26.03 | expected_starter |
| Cooper Kupp | SEA/WR | 3800 | ? → ? | 2.26 → 3.00 | 0.00 → 0.00 | 0.07 → 0.10 | 5.27 → 5.99 | +0.72 | 0.02 → 0.75 | 10.50 → 11.23 | expected_backup |
| Nick Kallerup | SEA/TE | 2500 | ? → ? | 0.00 → ? | 0.00 → 0.00 | 0.00 → 0.00 | 0.95 → 1.67 | +0.72 | 0.00 → 0.00 | 2.04 → 7.57 | missing |
| Jaleel McLaughlin | CLE/RB | 4100 | 1.15 → 0.67 | 0.68 → 0.33 | 0.06 → 0.04 | 0.02 → 0.01 | 2.30 → 2.96 | +0.66 | 0.00 → 0.16 | 4.70 → 5.36 | expected_backup |
| Darnell Mooney | NYG/WR | 3800 | ? → ? | 1.94 → 2.67 | 0.00 → 0.00 | 0.07 → 0.10 | 4.10 → 4.75 | +0.65 | 0.00 → 0.00 | 9.34 → 9.99 | expected_backup |
| DJ Giddens* | IND/RB | 4000 | 4.34 → ? | 0.20 → ? | 0.16 → 0.00 | 0.01 → 0.00 | 3.39 → 2.75 | -0.64 | 0.00 → 0.00 | 11.42 → 10.78 | missing |
| Jeremy Ruckert | NYJ/TE | 2500 | ? → ? | 1.49 → 2.33 | 0.00 → 0.00 | 0.05 → 0.08 | 2.87 → 3.51 | +0.64 | 0.00 → 0.27 | 8.78 → 9.41 | expected_backup |
| Kyle Williams | NE/WR | 3100 | ? → ? | 1.69 → 2.33 | 0.00 → 0.00 | 0.06 → 0.08 | 2.79 → 3.40 | +0.61 | 0.00 → 0.00 | 8.28 → 8.89 | expected_backup |
| Colson Yankoff | WAS/TE | 2500 | ? → ? | 0.83 → 1.33 | 0.00 → 0.00 | 0.03 → 0.04 | 1.44 → 2.04 | +0.60 | 0.00 → 0.00 | 2.53 → 3.13 | expected_backup |
| Nick Singleton | TEN/RB | 4000 | 2.04 → 2.33 | 0.00 → 0.00 | 0.09 → 0.11 | 0.00 → 0.00 | 1.98 → 2.58 | +0.60 | 0.00 → 0.00 | 4.37 → 4.97 | expected_backup |
| Thomas Fidone II | NYG/TE | 2500 | ? → ? | 0.00 → ? | 0.00 → 0.00 | 0.00 → 0.00 | 1.11 → 1.71 | +0.59 | 0.00 → 0.00 | 2.20 → 2.80 | missing |
| Marquez Valdes-Scantling | LAC/WR | 3300 | ? → ? | 1.48 → 0.67 | 0.00 → 0.00 | 0.05 → 0.02 | 3.17 → 2.59 | -0.58 | 0.00 → 0.00 | 8.41 → 7.82 | expected_backup |
| Jack Endries | CIN/TE | 2500 | ? → ? | 0.00 → ? | 0.00 → 0.00 | 0.00 → 0.00 | 1.14 → 1.73 | +0.58 | 0.00 → 0.00 | 2.24 → 2.82 | missing |
| Tyler Badie | DEN/RB | 4200 | 1.11 → 1.33 | 1.49 → 2.00 | 0.05 → 0.07 | 0.05 → 0.06 | 3.04 → 3.62 | +0.58 | 0.23 → 0.82 | 5.43 → 6.01 | expected_backup |
| Kimani Vidal | LAC/RB | 4300 | 1.76 → 2.00 | 1.31 → 2.00 | 0.07 → 0.08 | 0.05 → 0.07 | 3.65 → 4.23 | +0.58 | 0.85 → 1.43 | 6.04 → 6.62 | expected_backup |
| Seth McGowan | IND/RB | 4300 | 3.34 → 4.00 | 0.39 → 0.67 | 0.13 → 0.15 | 0.01 → 0.02 | 2.86 → 3.44 | +0.58 | 0.00 → 0.00 | 10.89 → 11.47 | expected_backup |
| Pat Freiermuth | PIT/TE | 3900 | ? → ? | 3.98 → 4.67 | 0.00 → 0.00 | 0.11 → 0.13 | 8.33 → 8.90 | +0.57 | 2.11 → 2.68 | 15.51 → 16.08 | expected_backup |
| Blake Whiteheart | CLE/TE | 2500 | ? → ? | 0.71 → 0.67 | 0.00 → 0.00 | 0.02 → 0.02 | 1.82 → 2.39 | +0.57 | 0.00 → 0.00 | 7.73 → 8.29 | expected_backup |
| Noah Fant | NO/TE | 3000 | ? → ? | 2.03 → 1.33 | 0.00 → 0.00 | 0.05 → 0.03 | 4.67 → 4.12 | -0.55 | 0.98 → 0.43 | 9.20 → 8.65 | expected_backup |
| Elijah Higgins | ARI/TE | 2700 | ? → ? | 0.97 → 1.67 | 0.00 → 0.00 | 0.03 → 0.05 | 2.25 → 2.80 | +0.55 | 0.00 → 0.00 | 8.16 → 8.71 | expected_backup |
| Foster Moreau | HOU/TE | 2500 | ? → ? | 1.49 → 2.33 | 0.00 → 0.00 | 0.04 → 0.07 | 2.90 → 3.40 | +0.50 | 0.00 → 0.16 | 8.80 → 9.30 | expected_backup |
| Seydou Traore | MIA/TE | 2500 | ? → ? | 0.00 → ? | 0.00 → 0.00 | 0.00 → 0.00 | 1.11 → 1.60 | +0.49 | 0.00 → 0.00 | 5.63 → 6.13 | missing |
| Jacob Cowing | SF/WR | 3000 | ? → ? | 0.42 → 1.00 | 0.00 → 0.00 | 0.02 → 0.04 | 1.44 → 1.93 | +0.49 | 0.00 → 0.00 | 6.93 → 7.42 | expected_backup |
| Germie Bernard | PIT/WR | 3400 | ? → ? | 3.04 → 3.67 | 0.00 → 0.00 | 0.09 → 0.10 | 5.10 → 5.59 | +0.49 | 0.91 → 1.40 | 10.59 → 11.08 | expected_backup |
| Treylon Burks | WAS/WR | 3200 | ? → ? | 1.20 → 2.00 | 0.00 → 0.00 | 0.04 → 0.06 | 3.20 → 3.69 | +0.48 | 0.00 → 0.00 | 8.70 → 9.18 | expected_backup |
| Alec Ingold* | LAC/RB | 4000 | 0.00 → 0.00 | 0.00 → 1.33 | 0.00 → 0.00 | 0.00 → 0.04 | 1.64 → 2.12 | +0.48 | 0.00 → 0.00 | 4.04 → 4.52 | expected_starter |
| Najee Harris* | NYG/RB | 4500 | 5.06 → 7.33 | 0.00 → 0.00 | 0.20 → 0.29 | 0.00 → 0.00 | 4.46 → 4.91 | +0.46 | 0.00 → 0.00 | 12.49 → 12.94 | expected_backup |
| Pat Bryant | DEN/WR | 4000 | ? → ? | 1.39 → 2.00 | 0.00 → 0.00 | 0.04 → 0.06 | 4.51 → 4.96 | +0.45 | 0.00 → 0.00 | 9.74 → 10.20 | expected_backup |
| Daniel Bellinger | TEN/TE | 2500 | ? → ? | 1.03 → 1.33 | 0.00 → 0.00 | 0.04 → 0.05 | 1.81 → 2.26 | +0.45 | 0.00 → 0.00 | 7.72 → 8.17 | expected_backup |
| Ian Thomas | LV/TE | 2500 | ? → ? | 1.21 → 1.00 | 0.00 → 0.00 | 0.03 → 0.03 | 2.54 → 2.10 | -0.45 | 0.00 → 0.00 | 8.45 → 8.00 | expected_backup |
| DK Metcalf* | PIT/WR | 5400 | ? → ? | 6.44 → 7.67 | 0.00 → 0.00 | 0.18 → 0.21 | 13.60 → 14.04 | +0.44 | 2.72 → 3.16 | 26.48 → 26.92 | expected_starter |
| Michael Carter* | TEN/RB | 4000 | 7.29 → ? | 1.98 → ? | 0.33 → 0.00 | 0.07 → 0.00 | 6.78 → 7.20 | +0.42 | 0.73 → 1.15 | 14.81 → 15.23 | missing |
| J. Michael Sturdivant | GB/WR | 3000 | ? → ? | 0.64 → 1.33 | 0.00 → 0.00 | 0.02 → 0.04 | 1.71 → 2.08 | +0.37 | 0.00 → 0.00 | 4.24 → 7.57 | expected_backup |
| Cole Kmet | CHI/TE | 2600 | ? → ? | 1.10 → 1.33 | 0.00 → 0.00 | 0.03 → 0.04 | 2.88 → 3.25 | +0.37 | 0.00 → 0.00 | 7.41 → 7.78 | expected_backup |
| Bo Melton | GB/WR | 3000 | ? → ? | 0.61 → 1.00 | 0.00 → 0.00 | 0.02 → 0.03 | 1.39 → 1.73 | +0.34 | 0.00 → 0.00 | 3.92 → 4.26 | expected_backup |
| Brock Wright | DET/TE | 2500 | ? → ? | 1.21 → 1.33 | 0.00 → 0.00 | 0.03 → 0.03 | 2.21 → 2.55 | +0.33 | 0.00 → 0.00 | 6.74 → 7.08 | expected_backup |
| Chimere Dike | TEN/WR | 3000 | ? → ? | 0.44 → 0.67 | 0.00 → 0.00 | 0.02 → 0.02 | 1.47 → 1.80 | +0.33 | 0.00 → 0.00 | 4.00 → 4.33 | expected_backup |
| Ben Sinnott | WAS/TE | 2500 | ? → ? | 1.11 → 0.67 | 0.00 → 0.00 | 0.03 → 0.02 | 2.09 → 1.77 | -0.32 | 0.00 → 0.00 | 6.62 → 6.29 | expected_backup |
| Colbie Young | CIN/WR | 3600 | ? → ? | 0.99 → 0.67 | 0.00 → 0.00 | 0.02 → 0.02 | 2.40 → 2.08 | -0.32 | 0.22 → 0.00 | 4.94 → 4.62 | expected_backup |
| Dareke Young | LV/WR | 3000 | ? → ? | 0.63 → 1.00 | 0.00 → 0.00 | 0.02 → 0.03 | 1.52 → 1.84 | +0.32 | 0.00 → 0.00 | 4.05 → 4.37 | expected_backup |
| Dare Ogunbowale* | HOU/RB | 4000 | 0.74 → ? | 1.59 → ? | 0.05 → 0.00 | 0.05 → 0.00 | 2.80 → 3.09 | +0.29 | 0.00 → 0.00 | 5.19 → 11.12 | missing |
| Tai Felton | MIN/WR | 3000 | ? → ? | 0.64 → 1.00 | 0.00 → 0.00 | 0.03 → 0.04 | 1.53 → 1.83 | +0.29 | 0.00 → 0.00 | 4.07 → 4.36 | expected_backup |
| Ryan Miller | MIA/WR | 3000 | ? → ? | 0.74 → 1.33 | 0.00 → 0.00 | 0.03 → 0.05 | 2.05 → 2.33 | +0.29 | 0.00 → 0.15 | 4.58 → 4.87 | expected_backup |
| Cade Stover | HOU/TE | 2500 | ? → ? | 0.83 → 0.33 | 0.00 → 0.00 | 0.02 → 0.01 | 1.66 → 1.39 | -0.27 | 0.00 → 0.00 | 7.57 → 2.48 | expected_backup |
| Myles Price | MIN/WR | 3000 | ? → ? | 0.66 → 1.00 | 0.00 → 0.00 | 0.03 → 0.04 | 1.55 → 1.82 | +0.27 | 0.00 → 0.00 | 4.08 → 4.35 | expected_backup |
| Jacob Saylors | DET/RB | 4000 | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.26 → 1.53 | +0.27 | 0.00 → 0.00 | 3.65 → 3.92 | expected_backup |
| DeeJay Dallas | MIN/RB | 4000 | 0.35 → 1.00 | 0.48 → 0.67 | 0.02 → 0.04 | 0.02 → 0.03 | 1.51 → 1.77 | +0.26 | 0.00 → 0.00 | 3.90 → 4.16 | expected_backup |
| Braelon Allen* | NYJ/RB | 5400 | 5.94 → 7.67 | 1.53 → 2.00 | 0.34 → 0.44 | 0.05 → 0.07 | 7.16 → 7.41 | +0.25 | 1.11 → 1.36 | 15.19 → 15.43 | expected_backup |
| Derius Davis | LAC/WR | 3100 | ? → ? | 0.46 → 0.67 | 0.00 → 0.00 | 0.02 → 0.02 | 1.45 → 1.68 | +0.23 | 0.00 → 0.00 | 3.98 → 4.21 | expected_backup |
| Luke McCaffrey | WAS/WR | 3000 | ? → ? | 0.66 → 0.00 | 0.00 → 0.00 | 0.02 → 0.00 | 2.07 → 1.84 | -0.22 | 0.00 → 0.00 | 4.60 → 4.38 | expected_backup |
| DJ Herman | MIA/RB | 4000 | 0.00 → 0.00 | 1.12 → 1.00 | 0.00 → 0.00 | 0.04 → 0.04 | 1.99 → 1.78 | -0.22 | 0.00 → 0.00 | 4.39 → 4.17 | expected_starter |
| Tanner Hudson | CIN/TE | 2500 | ? → ? | 1.13 → 1.00 | 0.00 → 0.00 | 0.03 → 0.02 | 1.72 → 1.51 | -0.21 | 0.00 → 0.00 | 2.81 → 2.60 | expected_backup |
| Josh Whyle* | GB/TE | 2500 | ? → ? | 1.28 → ? | 0.00 → 0.00 | 0.03 → 0.00 | 1.92 → 1.72 | -0.21 | 0.00 → 0.00 | 3.02 → 2.81 | missing |
| Brady Russell | SEA/RB | 4000 | 0.00 → 0.00 | 0.83 → 0.33 | 0.00 → 0.00 | 0.03 → 0.01 | 1.87 → 1.68 | -0.19 | 0.00 → 0.00 | 4.26 → 4.08 | expected_starter |
| Connor Heyward* | LV/RB | 4000 | 0.00 → 1.00 | 0.00 → 0.33 | 0.00 → 0.04 | 0.00 → 0.01 | 2.00 → 2.18 | +0.19 | 0.00 → 0.00 | 4.39 → 4.58 | expected_starter |
| Eric Saubert | SEA/TE | 2500 | ? → ? | 0.65 → 1.00 | 0.00 → 0.00 | 0.02 → 0.03 | 1.45 → 1.63 | +0.18 | 0.00 → 0.00 | 2.54 → 2.72 | expected_backup |
| Velus Jones Jr.* | SEA/RB | 4000 | 1.93 → ? | 0.00 → ? | 0.07 → 0.00 | 0.00 → 0.00 | 1.69 → 1.87 | +0.18 | 0.00 → 0.00 | 4.09 → 4.27 | missing |
| Kendre Miller | NO/RB | 4900 | 4.00 → 3.33 | 1.11 → 2.00 | 0.20 → 0.16 | 0.03 → 0.05 | 5.28 → 5.10 | -0.18 | 0.00 → 0.00 | 13.31 → 13.13 | expected_backup |
| Brevin Jordan | HOU/TE | 2500 | ? → ? | 0.83 → 0.33 | 0.00 → 0.00 | 0.02 → 0.01 | 1.99 → 1.81 | -0.18 | 0.00 → 0.00 | 6.52 → 6.34 | expected_backup |
| Roschon Johnson | CHI/RB | 4200 | 0.76 → 1.33 | 0.28 → 0.33 | 0.02 → 0.04 | 0.01 → 0.01 | 1.54 → 1.71 | +0.17 | 0.00 → 0.00 | 3.93 → 4.10 | expected_backup |
| CJ Donaldson | NO/RB | 4400 | 1.15 → 1.67 | 0.34 → 0.67 | 0.06 → 0.08 | 0.01 → 0.02 | 1.94 → 2.10 | +0.17 | 0.00 → 0.00 | 4.33 → 4.50 | expected_backup |
| Demond Claiborne* | MIN/RB | 4000 | 0.74 → 2.00 | 0.31 → 0.33 | 0.03 → 0.09 | 0.01 → 0.01 | 1.60 → 1.77 | +0.17 | 0.00 → 0.00 | 3.99 → 4.16 | expected_backup |
| Malik Benson | LV/WR | 3000 | ? → ? | 0.55 → 0.67 | 0.00 → 0.00 | 0.02 → 0.02 | 1.19 → 1.35 | +0.16 | 0.00 → 0.00 | 3.72 → 3.88 | expected_backup |
| Malachi Corley | CLE/WR | 3000 | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.32 → 1.47 | +0.15 | 0.00 → 0.00 | 3.85 → 4.00 | expected_backup |
| Tom Kennedy | DET/WR | 3000 | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.08 → 0.95 | -0.14 | 0.00 → 0.00 | 6.32 → 6.18 | expected_backup |
| Jonnu Smith | GB/TE | 2700 | ? → ? | 1.17 → 1.33 | 0.00 → 0.00 | 0.03 → 0.04 | 2.72 → 2.85 | +0.13 | 0.00 → 0.00 | 8.62 → 8.75 | expected_backup |
| Deion Burks | IND/WR | 3100 | ? → ? | 0.59 → 0.67 | 0.00 → 0.00 | 0.02 → 0.02 | 1.91 → 2.04 | +0.13 | 0.00 → 0.00 | 4.44 → 4.57 | expected_backup |
| Rashid Shaheed | SEA/WR | 4000 | ? → ? | 3.51 → 4.00 | 0.00 → 0.00 | 0.12 → 0.13 | 5.83 → 5.95 | +0.12 | 0.00 → 0.70 | 15.52 → 11.18 | expected_backup |
| David Martin-Robinson | TEN/TE | 2500 | ? → ? | 0.81 → ? | 0.00 → 0.00 | 0.03 → 0.00 | 1.05 → 0.94 | -0.11 | 0.00 → 0.00 | 2.14 → 2.03 | missing |
| Isaac TeSlaa | DET/WR | 3400 | ? → ? | 4.48 → 5.33 | 0.00 → 0.00 | 0.11 → 0.13 | 8.25 → 8.14 | -0.11 | 0.56 → 0.45 | 17.94 → 17.83 | expected_backup |
| Tay Martin | DET/WR | 3000 | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.28 → 1.39 | +0.10 | 0.00 → 0.00 | 3.82 → 3.92 | expected_backup |
| Charlie Kolar | LAC/TE | 2500 | ? → ? | 1.07 → 1.00 | 0.00 → 0.00 | 0.04 → 0.03 | 1.78 → 1.68 | -0.10 | 0.00 → 0.00 | 6.31 → 6.21 | expected_starter |
| Jelani Woods | NYJ/TE | 2500 | ? → ? | 0.80 → 0.67 | 0.00 → 0.00 | 0.03 → 0.02 | 1.69 → 1.60 | -0.09 | 0.00 → 0.00 | 7.60 → 2.69 | expected_backup |
| Eli Raridon | NE/TE | 2700 | ? → ? | 0.91 → 1.00 | 0.00 → 0.00 | 0.03 → 0.03 | 2.44 → 2.35 | -0.09 | 0.00 → 0.00 | 8.34 → 8.25 | expected_backup |
| Julius Chestnut | TEN/RB | 4000 | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.11 → 1.20 | +0.09 | 0.00 → 0.00 | 3.51 → 3.59 | expected_backup |
| Jauan Jennings | MIN/WR | 4100 | ? → ? | 0.90 → 1.00 | 0.00 → 0.00 | 0.03 → 0.04 | 3.78 → 3.86 | +0.08 | 0.00 → 0.00 | 9.02 → 9.10 | expected_backup |
| J.K. Dobbins* | DEN/RB | 5000 | 10.57 → 12.67 | 0.91 → 1.33 | 0.52 → 0.62 | 0.03 → 0.04 | 9.38 → 9.45 | +0.07 | 3.33 → 0.00 | 17.41 → 20.68 | expected_starter |
| Jordan Watkins | SF/WR | 3000 | ? → ? | 0.69 → 0.67 | 0.00 → 0.00 | 0.03 → 0.03 | 2.10 → 2.04 | -0.06 | 0.00 → 0.00 | 7.60 → 4.57 | expected_backup |
| Troy Franklin | DEN/WR | 3200 | ? → ? | 1.09 → 1.00 | 0.00 → 0.00 | 0.03 → 0.03 | 2.81 → 2.75 | -0.06 | 0.00 → 0.57 | 8.30 → 5.28 | expected_backup |
| Isaiah Bond | CLE/WR | 3000 | ? → ? | 1.01 → 0.67 | 0.00 → 0.00 | 0.03 → 0.02 | 2.05 → 1.99 | -0.06 | 0.00 → 0.00 | 4.58 → 4.52 | expected_backup |
| KC Concepcion Jr.* | CLE/WR | 4200 | ? → ? | 4.78 → 7.67 | 0.00 → 0.00 | 0.16 → 0.25 | 8.73 → 8.79 | +0.06 | 1.05 → 0.00 | 18.43 → 20.18 | expected_backup |
| Ben Skowronek | PIT/WR | 3000 | ? → ? | 1.12 → 1.33 | 0.00 → 0.00 | 0.03 → 0.04 | 2.19 → 2.24 | +0.05 | 0.01 → 0.06 | 4.72 → 4.78 | expected_backup |
| Theo Johnson | NYG/TE | 2600 | ? → ? | 1.23 → 1.67 | 0.00 → 0.00 | 0.04 → 0.06 | 3.12 → 3.17 | +0.05 | 0.00 → 0.00 | 9.02 → 9.08 | expected_backup |
| Tahj Brooks | CIN/RB | 4000 | 0.53 → 0.00 | 0.35 → 0.00 | 0.03 → 0.00 | 0.01 → 0.00 | 1.33 → 1.28 | -0.05 | 0.00 → 0.00 | 3.72 → 3.67 | expected_backup |
| Andrew Beck | NYJ/RB | 4000 | 0.00 → 0.00 | 0.57 → 0.00 | 0.00 → 0.00 | 0.02 → 0.00 | 1.78 → 1.73 | -0.05 | 0.00 → 0.00 | 4.18 → 4.13 | expected_starter |
| Kevin Coleman Jr. | MIA/WR | 3000 | ? → ? | 2.41 → 2.67 | 0.00 → 0.00 | 0.10 → 0.11 | 3.48 → 3.52 | +0.04 | 0.00 → 0.00 | 8.72 → 8.76 | expected_backup |
| Robert Tonyan | PIT/TE | 2500 | ? → ? | 0.56 → 0.33 | 0.00 → 0.00 | 0.02 → 0.01 | 1.03 → 0.99 | -0.04 | 0.00 → 0.00 | 2.12 → 2.08 | expected_backup |
| Chris Manhertz | NYG/TE | 2500 | ? → ? | 0.20 → 0.00 | 0.00 → 0.00 | 0.01 → 0.00 | 1.14 → 1.10 | -0.04 | 0.00 → 0.00 | 7.04 → 2.19 | expected_backup |
| Will Kacmarek | MIA/TE | 2500 | ? → ? | 0.92 → 1.00 | 0.00 → 0.00 | 0.04 → 0.04 | 1.51 → 1.54 | +0.04 | 0.00 → 0.00 | 7.41 → 7.45 | expected_backup |
| Sam Roush | CHI/TE | 2500 | ? → ? | 1.39 → 1.67 | 0.00 → 0.00 | 0.04 → 0.05 | 2.20 → 2.17 | -0.03 | 0.08 → 0.05 | 3.29 → 3.26 | expected_backup |
| Gavin Bartholomew | MIN/TE | 2500 | ? → ? | 0.53 → 0.33 | 0.00 → 0.00 | 0.02 → 0.01 | 1.14 → 1.11 | -0.03 | 0.00 → 0.00 | 2.23 → 2.20 | expected_backup |
| Nate Adkins | DEN/TE | 2500 | ? → ? | 1.33 → 1.67 | 0.00 → 0.00 | 0.04 → 0.05 | 2.71 → 2.72 | +0.02 | 0.00 → 0.00 | 8.62 → 8.63 | expected_backup |
| Jamaal Pritchett | NYJ/WR | 3000 | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.53 → 1.53 | +0.00 | 0.00 → 0.00 | 6.77 → 6.77 | expected_backup |
| Drake Maye | NE/QB | 6300 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 17.55 → 17.55 | +0.00 | 7.57 → 7.57 | 28.27 → 28.27 | expected_starter |
| Bears | CHI/DST | 2900 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 4.77 → 4.77 | +0.00 | 0.00 → 0.00 | 11.34 → 11.34 | missing |
| Caleb Williams | CHI/QB | 6200 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | +0.00 | 0.00 → 0.00 | 0.00 → 0.00 | expected_backup |
| Patriots | NE/DST | 3000 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 5.24 → 5.24 | +0.00 | 0.00 → 0.00 | 11.81 → 11.81 | missing |
| Lions | DET/DST | 3000 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 4.77 → 4.77 | +0.00 | 0.00 → 0.00 | 11.34 → 11.34 | missing |
| Tyler Shough | NO/QB | 6100 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 17.81 → 17.81 | +0.00 | 7.83 → 7.83 | 28.53 → 28.53 | expected_starter |
| Barion Brown | NO/WR | 3000 | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.16 → 1.16 | +0.00 | 0.00 → 0.00 | 3.69 → 3.69 | expected_backup |
| Jaylen Wright | MIA/RB | 4800 | 2.56 → 2.33 | 0.00 → 0.00 | 0.13 → 0.12 | 0.00 → 0.00 | 2.91 → 2.91 | +0.00 | 0.00 → 0.10 | 10.94 → 5.30 | expected_backup |
| Jayden Daniels | WAS/QB | 6000 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 14.93 → 14.93 | +0.00 | 4.95 → 5.38 | 25.65 → 25.76 | expected_starter |
| Commanders | WAS/DST | 2900 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 5.30 → 5.30 | +0.00 | 0.00 → 0.00 | 11.87 → 11.87 | missing |
| Anthony Gould | IND/WR | 3000 | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.11 → 1.11 | +0.00 | 0.00 → 0.00 | 3.64 → 3.64 | expected_backup |
| C.J. Stroud | HOU/QB | 5900 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 19.11 → 19.11 | +0.00 | 9.56 → 9.56 | 29.94 → 29.94 | expected_starter |
| Kaden Wetjen | PIT/WR | 3000 | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.17 → 1.17 | +0.00 | 0.00 → 0.00 | 6.41 → 6.41 | expected_backup |
| Sam Darnold | SEA/QB | 5800 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 15.29 → 15.29 | +0.00 | 5.74 → 5.74 | 26.12 → 26.12 | expected_starter |
| Charlie Jones | NYG/WR | 3000 | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.15 → 1.15 | +0.00 | 0.00 → 0.00 | 3.69 → 3.69 | expected_backup |
| Malik McClain | NYJ/WR | 3000 | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.59 → 1.59 | +0.00 | 0.00 → 0.00 | 6.82 → 6.82 | expected_backup |
| Colts | IND/DST | 2500 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 4.44 → 4.44 | +0.00 | 0.00 → 0.00 | 11.01 → 11.01 | missing |
| Browns | CLE/DST | 2800 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 5.15 → 5.15 | +0.00 | 0.00 → 0.00 | 11.72 → 11.72 | missing |
| Jordan Love | GB/QB | 5700 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 18.01 → 18.01 | +0.00 | 8.46 → 8.46 | 28.83 → 28.83 | expected_starter |
| Cardinals | ARI/DST | 2200 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 4.47 → 4.47 | +0.00 | 0.00 → 0.00 | 11.04 → 11.04 | missing |
| Chargers | LAC/DST | 2300 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 4.44 → 4.44 | +0.00 | 0.00 → 0.00 | 11.01 → 11.01 | missing |
| Hayden Rucci | LAC/TE | 2500 | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.18 → 1.18 | +0.00 | 0.00 → 0.00 | 2.27 → 2.27 | expected_backup |
| 49ers | SF/DST | 2400 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 4.47 → 4.47 | +0.00 | 0.00 → 0.00 | 11.04 → 11.04 | missing |
| Raiders | LV/DST | 2500 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 4.47 → 4.47 | +0.00 | 0.00 → 0.00 | 11.04 → 11.04 | missing |
| Brayden Willis | SF/TE | 2500 | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 0.90 → 0.90 | +0.00 | 0.00 → 0.00 | 1.99 → 1.99 | expected_backup |
| Luke Farrell | SF/TE | 2500 | ? → ? | 0.14 → 0.33 | 0.00 → 0.00 | 0.01 → 0.01 | 1.38 → 1.38 | +0.00 | 0.00 → 0.00 | 5.91 → 5.91 | expected_backup |
| Giants | NYG/DST | 2600 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 4.68 → 4.68 | +0.00 | 0.00 → 0.00 | 11.25 → 11.25 | missing |
| Joe Burrow | CIN/QB | 6900 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 24.04 → 24.04 | +0.00 | 14.49 → 14.49 | 34.87 → 34.87 | expected_starter |
| Saints | NO/DST | 2600 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 4.68 → 4.68 | +0.00 | 0.00 → 0.00 | 11.25 → 11.25 | missing |
| Jets | NYJ/DST | 2700 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 5.24 → 5.24 | +0.00 | 0.00 → 0.00 | 11.81 → 11.81 | missing |
| Packers | GB/DST | 2700 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 4.72 → 4.72 | +0.00 | 0.00 → 0.00 | 11.29 → 11.29 | missing |
| Jared Goff | DET/QB | 6600 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 26.19 → 26.19 | +0.00 | 16.65 → 16.65 | 37.02 → 37.02 | expected_starter |
| Seahawks | SEA/DST | 2800 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 5.05 → 5.05 | +0.00 | 0.00 → 0.00 | 11.62 → 11.62 | missing |
| Brock Purdy | SF/QB | 6500 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 24.29 → 24.29 | +0.00 | 14.31 → 14.31 | 35.01 → 35.01 | expected_starter |
| Devin Duvernay | ARI/WR | 3000 | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.02 → 1.02 | +0.00 | 0.00 → 0.00 | 6.26 → 6.26 | expected_backup |
| Simi Fehoko | ARI/WR | 3000 | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.02 → 1.02 | +0.00 | 0.00 → 0.00 | 3.55 → 3.55 | expected_backup |
| Tyson Bagent | CHI/QB | 4700 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 5.27 → 5.27 | +0.00 | 0.00 → 0.00 | 16.10 → 16.10 | expected_starter |
| Adam Prentice | DEN/RB | 4000 | 0.00 → 0.00 | 0.00 → 0.33 | 0.00 → 0.00 | 0.00 → 0.01 | 1.38 → 1.38 | +0.00 | 0.00 → 0.00 | 3.77 → 3.77 | expected_starter |
| Justin Herbert | LAC/QB | 5100 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 15.90 → 15.90 | +0.00 | 5.92 → 5.92 | 26.62 → 26.62 | expected_starter |
| Max Bredeson | MIN/RB | 4000 | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.72 → 1.72 | +0.00 | 0.00 → 0.00 | 4.12 → 4.12 | expected_starter |
| Travis Homer | PIT/RB | 4000 | 1.36 → 1.67 | 0.00 → 0.00 | 0.07 → 0.09 | 0.00 → 0.00 | 1.48 → 1.48 | +0.00 | 0.00 → 0.00 | 3.88 → 3.88 | expected_backup |
| Daniel Jones | IND/QB | 5000 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 14.81 → 14.81 | +0.00 | 5.26 → 5.26 | 25.64 → 25.64 | expected_starter |
| Geno Smith | NYJ/QB | 5000 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 17.10 → 17.10 | +0.00 | 7.55 → 7.55 | 27.93 → 27.93 | expected_starter |
| Patrick Ricard | NYG/RB | 4000 | 0.00 → 0.00 | 0.66 → 0.67 | 0.00 → 0.00 | 0.02 → 0.02 | 1.79 → 1.79 | +0.00 | 0.00 → 0.00 | 4.18 → 4.18 | expected_starter |
| TreVeyon Henderson | NE/RB | 5000 | 12.53 → 12.67 | 0.60 → 1.00 | 0.52 → 0.53 | 0.02 → 0.03 | 9.36 → 9.36 | +0.00 | 3.31 → 3.31 | 17.39 → 17.39 | expected_backup |
| Eli Heidenreich | PIT/RB | 4000 | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.60 → 1.60 | +0.00 | 0.00 → 0.00 | 4.00 → 4.00 | expected_backup |
| Treyton Welch | NO/TE | 2500 | ? → ? | 0.26 → 0.33 | 0.00 → 0.00 | 0.01 → 0.01 | 1.15 → 1.15 | +0.00 | 0.00 → 0.00 | 2.24 → 2.24 | expected_backup |
| Cam Ward | TEN/QB | 4900 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 15.66 → 15.66 | +0.00 | 6.11 → 6.11 | 26.48 → 26.48 | expected_starter |
| Isaiah Davis | NYJ/RB | 4200 | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.45 → 1.45 | +0.00 | 0.00 → 0.00 | 3.85 → 3.85 | expected_backup |
| Oscar Delp | NO/TE | 2500 | ? → ? | 0.37 → 0.33 | 0.00 → 0.00 | 0.01 → 0.01 | 1.19 → 1.19 | +0.00 | 0.00 → 0.00 | 2.28 → 2.28 | expected_backup |
| Mike Washington Jr. | LV/RB | 4200 | 4.79 → 5.67 | 0.63 → 1.00 | 0.20 → 0.23 | 0.02 → 0.03 | 4.34 → 4.34 | +0.00 | 0.00 → 0.00 | 12.37 → 12.37 | expected_backup |
| Samaje Perine | CIN/RB | 4400 | 2.60 → 2.67 | 1.47 → 1.67 | 0.16 → 0.16 | 0.04 → 0.04 | 4.41 → 4.41 | +0.00 | 0.00 → 0.00 | 12.44 → 12.44 | expected_backup |
| Jameis Winston | NYG/QB | 4800 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 12.37 → 12.37 | +0.00 | 2.82 → 2.82 | 23.20 → 23.20 | expected_starter |
| Malik Willis | MIA/QB | 4600 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 14.10 → 14.10 | +0.00 | 4.12 → 4.12 | 24.82 → 24.82 | expected_starter |
| Deshaun Watson | CLE/QB | 5100 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 17.28 → 17.28 | +0.00 | 7.30 → 7.30 | 28.00 → 28.00 | expected_starter |
| Corey Kiner | NE/RB | 4000 | 2.95 → 2.67 | 0.22 → 0.33 | 0.12 → 0.11 | 0.01 → 0.01 | 2.27 → 2.27 | +0.00 | 0.00 → 0.00 | 4.66 → 4.66 | expected_backup |
| Jalen Brooks | ARI/WR | 3000 | ? → ? | 0.17 → 0.33 | 0.00 → 0.00 | 0.00 → 0.01 | 1.08 → 1.08 | +0.00 | 0.00 → 0.00 | 3.62 → 3.62 | expected_backup |
| Steelers | PIT/DST | 3300 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 5.96 → 5.96 | +0.00 | 0.00 → 0.00 | 12.53 → 12.53 | missing |
| Bo Nix | DEN/QB | 5600 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 19.22 → 19.22 | +0.00 | 9.68 → 9.68 | 30.05 → 30.05 | expected_starter |
| Zavion Thomas | CHI/WR | 3000 | ? → ? | 0.25 → 0.33 | 0.00 → 0.00 | 0.01 → 0.01 | 1.12 → 1.12 | +0.00 | 0.00 → 0.00 | 3.65 → 3.65 | expected_backup |
| Vikings | MIN/DST | 3100 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 6.03 → 6.03 | +0.00 | 0.00 → 0.00 | 12.60 → 12.60 | missing |
| Jacoby Brissett | ARI/QB | 5500 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 26.38 → 26.38 | +0.00 | 16.83 → 16.83 | 37.21 → 37.21 | expected_starter |
| Rhamondre Stevenson* | NE/RB | 5500 | 8.52 → 8.67 | 2.25 → 3.33 | 0.35 → 0.36 | 0.08 → 0.11 | 10.38 → 10.38 | +0.00 | 4.33 → 4.33 | 18.41 → 18.41 | expected_starter |
| Broncos | DEN/DST | 3200 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 6.03 → 6.03 | +0.00 | 0.00 → 0.00 | 12.60 → 12.60 | missing |
| Kirk Cousins | LV/QB | 5400 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 19.44 → 19.44 | +0.00 | 9.90 → 9.90 | 30.27 → 30.27 | expected_starter |
| Cameron Latu | NE/TE | 2500 | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 0.87 → 0.87 | +0.00 | 0.00 → 0.00 | 1.96 → 1.96 | expected_backup |
| RJ Harvey* | DEN/RB | 5200 | 4.07 → 3.00 | 4.95 → 5.67 | 0.20 → 0.15 | 0.15 → 0.17 | 10.75 → 10.75 | +0.00 | 2.52 → 2.52 | 20.65 → 20.65 | expected_backup |
| Texans | HOU/DST | 3400 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 6.03 → 6.03 | +0.00 | 0.00 → 0.00 | 12.60 → 12.60 | missing |
| Aaron Rodgers | PIT/QB | 5300 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 20.14 → 20.14 | +0.00 | 10.60 → 10.60 | 30.97 → 30.97 | expected_starter |
| Bengals | CIN/DST | 3500 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 6.03 → 6.03 | +0.00 | 0.00 → 0.00 | 12.60 → 12.60 | missing |
| Titans | TEN/DST | 2100 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 4.36 → 4.36 | +0.00 | 0.00 → 0.00 | 10.93 → 10.93 | missing |
| Tyrone Tracy Jr. | NYG/RB | 4000 | 0.42 → 0.67 | 0.00 → 0.00 | 0.02 → 0.03 | 0.00 → 0.00 | 2.28 → 2.28 | +0.00 | 0.00 → 0.00 | 4.67 → 4.67 | expected_backup |
| Dylan Laube | LV/RB | 4000 | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | 1.18 → 1.18 | +0.00 | 0.00 → 0.00 | 3.58 → 3.58 | expected_backup |
| Kyler Murray | MIN/QB | 5200 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 12.51 → 12.51 | +0.00 | 2.96 → 2.96 | 23.34 → 23.34 | expected_starter |
| Dolphins | MIA/DST | 2000 | ? → ? | ? → ? | 0.00 → 0.00 | 0.00 → 0.00 | 4.36 → 4.36 | +0.00 | 0.00 → 0.00 | 10.93 → 10.93 | missing |


Separate opportunity-only comparisons for 227 allocation members outside the modeled pool are in `excluded_opportunity_comparison.csv`. They have no invented fantasy-point forecasts and remain outside optimizer eligibility. Original normalized prior/vacated/expected volumes and corrected historical/vacated/expected volumes are retained by canonical ID.

## Team reconciliation

All corrected team/opportunity rows satisfy assigned + unallocated = measured team volume within 1e-6. No assigned volume exceeds the budget. Team carries are the RB/FB pool; team targets are RB/FB/WR/TE. Other-position volume is outside those denominators. Unrepresented players and genuine unavailable workload remain unallocated unless current evidence supplies recipients. Corrected team volumes can differ from original RB-only volumes because FB classification is reconciled.
| Team | Work | Old budget | New budget | Old assigned | New assigned | Old unassigned | New unassigned | Genuine vacated | History unrepresented |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ARI | carry | 20.33 | 20.33 | 9.92 | 20.33 | 10.42 | 0.00 | 0.00 | 0.00 |
| CHI | carry | 35.00 | 35.00 | 15.61 | 18.33 | 19.39 | 16.67 | 16.67 | 0.00 |
| CIN | carry | 16.67 | 16.67 | 15.26 | 16.67 | 1.40 | 0.00 | 0.00 | 0.00 |
| CLE | carry | 18.00 | 18.00 | 11.25 | 18.00 | 6.75 | 0.00 | 0.00 | 0.00 |
| DEN | carry | 20.33 | 20.33 | 15.75 | 17.00 | 4.59 | 3.33 | 3.33 | 0.00 |
| DET | carry | 19.33 | 19.33 | 11.91 | 19.33 | 7.42 | 0.00 | 0.00 | 0.00 |
| GB | carry | 15.00 | 15.00 | 8.29 | 12.33 | 6.71 | 2.67 | 2.67 | 0.00 |
| HOU | carry | 15.33 | 15.33 | 9.16 | 15.33 | 6.18 | 0.00 | 0.00 | 0.00 |
| IND | carry | 26.33 | 26.33 | 26.33 | 26.33 | 0.00 | 0.00 | 0.00 | 0.00 |
| LAC | carry | 25.33 | 25.33 | 21.11 | 25.33 | 4.22 | 0.00 | 0.00 | 0.00 |
| LV | carry | 24.00 | 25.00 | 20.31 | 25.00 | 3.69 | 0.00 | 0.00 | 0.00 |
| MIA | carry | 19.67 | 19.67 | 10.49 | 12.00 | 9.18 | 7.67 | 7.67 | 0.00 |
| MIN | carry | 23.00 | 23.00 | 8.11 | 23.00 | 14.89 | 0.00 | 0.00 | 0.00 |
| NE | carry | 24.00 | 24.00 | 24.00 | 24.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| NO | carry | 20.33 | 20.33 | 10.38 | 13.33 | 9.95 | 7.00 | 7.00 | 0.00 |
| NYG | carry | 25.67 | 25.67 | 21.70 | 25.67 | 3.97 | 0.00 | 0.00 | 0.00 |
| NYJ | carry | 17.33 | 17.33 | 8.40 | 7.67 | 8.93 | 9.67 | 9.67 | 0.00 |
| PIT | carry | 19.33 | 19.33 | 19.33 | 19.00 | 0.00 | 0.33 | 0.00 | 0.33 |
| SEA | carry | 27.67 | 27.67 | 13.60 | 21.67 | 14.06 | 6.00 | 6.00 | 0.00 |
| SF | carry | 20.33 | 20.33 | 13.25 | 20.33 | 7.08 | 0.00 | 0.00 | 0.00 |
| TEN | carry | 22.00 | 22.00 | 21.45 | 22.00 | 0.55 | 0.00 | 0.00 | 0.00 |
| WAS | carry | 23.00 | 23.00 | 18.98 | 19.67 | 4.02 | 3.33 | 3.33 | 0.00 |
| ARI | target | 37.00 | 37.00 | 27.65 | 36.33 | 9.35 | 0.67 | 0.67 | 0.00 |
| CHI | target | 31.67 | 31.67 | 27.12 | 30.67 | 4.55 | 1.00 | 1.00 | 0.00 |
| CIN | target | 40.33 | 40.33 | 37.78 | 37.67 | 2.56 | 2.67 | 0.33 | 2.33 |
| CLE | target | 30.67 | 31.00 | 21.55 | 31.00 | 9.11 | 0.00 | 0.00 | 0.00 |
| DEN | target | 32.33 | 32.67 | 26.61 | 31.33 | 5.72 | 1.33 | 1.33 | 0.00 |
| DET | target | 40.00 | 40.00 | 36.30 | 39.67 | 3.70 | 0.33 | 0.00 | 0.33 |
| GB | target | 36.67 | 36.67 | 23.88 | 35.00 | 12.79 | 1.67 | 1.67 | 0.00 |
| HOU | target | 33.67 | 33.67 | 25.00 | 33.33 | 8.66 | 0.33 | 0.33 | 0.00 |
| IND | target | 31.33 | 31.33 | 21.56 | 28.67 | 9.77 | 2.67 | 2.33 | 0.33 |
| LAC | target | 28.33 | 29.67 | 16.21 | 23.33 | 12.13 | 6.33 | 6.33 | 0.00 |
| LV | target | 35.33 | 35.67 | 24.57 | 33.00 | 10.76 | 2.67 | 2.67 | 0.00 |
| MIA | target | 25.00 | 25.00 | 17.44 | 21.67 | 7.56 | 3.33 | 3.33 | 0.00 |
| MIN | target | 25.67 | 25.67 | 20.11 | 25.33 | 5.56 | 0.33 | 0.33 | 0.00 |
| NE | target | 29.00 | 29.00 | 16.38 | 23.33 | 12.62 | 5.67 | 5.67 | 0.00 |
| NO | target | 39.67 | 39.67 | 28.13 | 38.33 | 11.53 | 1.33 | 1.33 | 0.00 |
| NYG | target | 27.33 | 27.33 | 20.01 | 26.67 | 7.33 | 0.67 | 0.33 | 0.33 |
| NYJ | target | 29.00 | 29.00 | 19.28 | 21.67 | 9.72 | 7.33 | 7.33 | 0.00 |
| PIT | target | 35.67 | 35.67 | 29.89 | 32.67 | 5.78 | 3.00 | 3.00 | 0.00 |
| SEA | target | 30.33 | 30.33 | 25.30 | 28.67 | 5.03 | 1.67 | 1.67 | 0.00 |
| SF | target | 23.33 | 25.33 | 11.24 | 24.00 | 12.09 | 1.33 | 1.00 | 0.33 |
| TEN | target | 26.67 | 26.67 | 24.23 | 26.67 | 2.44 | 0.00 | 0.00 | 0.00 |
| WAS | target | 33.00 | 33.00 | 22.39 | 25.33 | 10.61 | 7.67 | 7.67 | 0.00 |


## Chronological historical validation

Only Week 4 has archived fitted Sunday-main models before Week 5: three prelock snapshots of the **same week**, producing identical metrics. They are cutoff sensitivity checks, not three independent holdout weeks. **Week 4 original raw-input parity fails:** 135 player carry counts, 234 target counts, 69 carry shares and 252 target shares differ from the saved historical inputs at each cutoff. The original fitted forecasts are reproducible, but the available raw-source archive does not certify an identical-input policy ablation. The restricted-source metrics below are not promotion-grade evidence and cannot attribute their error changes solely to allocation. Missing historical source versions, ingest timestamp provenance or historical identity changes need investigation before drawing causal conclusions. Models train through Week 3; each cutoff precedes every target game kickoff. Target Week 4 outcomes enter only evaluation after scoring and never feature rebuilding. Actual labels use the repository’s `Database.scoring.compute_dk_scoring`; missing outcome rows are excluded, not invented zeros. The current alias mapping is not a versioned historical snapshot, limiting identity provenance for rebuilt historical opportunity inputs.

236/307 RB/WR/TE players have usable outcomes; 71 have missing labels and are excluded. Many labeled players are low-volume participants. Opportunity accuracy uses the common subset where the corrected policy publishes a supported count: 43 RB carry rows and 141 target rows. Unknown workload coverage is reported rather than scored as zero. The Week 4 source window is predominantly 2025 games: available current-season raw versions have receipt timestamps after the prelock cutoff. The original saved features nevertheless contain different opportunity history. This mismatch is a source-provenance limitation; it does not by itself establish that the original live run leaked future data. Restricted-source rebuilding is time-filtered but has weak current-role evidence.

| Group | N | MAE | RMSE | Carry MAE | Target MAE | P10 CDF | P90 CDF | 10–90 coverage | Width |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all | 236 | 4.389 → 4.478 | 6.566 → 6.536 | 3.283 → 4.566 | 1.905 → 2.194 | 0.271 → 0.267 | 0.894 → 0.890 | 0.818 → 0.814 | 11.88 → 12.45 |
| position:RB | 70 | 4.388 → 4.457 | 6.536 → 6.549 | 3.283 → 4.566 | 1.512 → 1.752 | 0.186 → 0.186 | 0.900 → 0.886 | 0.843 → 0.829 | 12.61 → 13.31 |
| position:TE | 59 | 3.464 → 3.687 | 4.882 → 5.036 | nan → nan | 1.956 → 2.105 | 0.322 → 0.322 | 0.915 → 0.915 | 0.864 → 0.847 | 9.38 → 10.08 |
| position:WR | 107 | 4.900 → 4.928 | 7.349 → 7.223 | nan → nan | 2.145 → 2.545 | 0.299 → 0.290 | 0.879 → 0.879 | 0.776 → 0.785 | 12.79 → 13.19 |
| price_band:cheap_4500_or_less | 157 | 3.101 → 3.296 | 4.817 → 4.877 | 1.102 → 2.556 | 1.217 → 1.591 | 0.350 → 0.350 | 0.917 → 0.911 | 0.860 → 0.847 | 8.63 → 9.60 |
| price_band:expensive_7000_plus | 11 | 10.149 → 10.254 | 12.492 → 12.614 | 4.392 → 3.500 | 3.498 → 4.167 | 0.182 → 0.091 | 0.818 → 0.727 | 0.636 → 0.636 | 22.08 → 21.60 |
| price_band:middle | 68 | 6.431 → 6.272 | 8.416 → 8.222 | 4.942 → 6.492 | 2.794 → 2.851 | 0.103 → 0.103 | 0.853 → 0.868 | 0.750 → 0.765 | 17.73 → 17.55 |
| calibration_role:COMMITTEE | 53 | 3.816 → 3.878 | 6.108 → 6.078 | 2.686 → 3.931 | 1.054 → 1.276 | 0.245 → 0.245 | 0.906 → 0.906 | 0.830 → 0.830 | 9.74 → 10.98 |
| calibration_role:LEAD | 14 | 6.031 → 6.183 | 7.813 → 8.004 | 4.596 → 6.485 | 2.420 → 2.758 | 0.000 → 0.000 | 0.857 → 0.786 | 0.857 → 0.786 | 22.24 → 20.21 |
| calibration_role:PRIMARY | 34 | 6.629 → 6.474 | 8.565 → 8.388 | nan → nan | 3.362 → 3.609 | 0.059 → 0.059 | 0.853 → 0.912 | 0.794 → 0.853 | 20.19 → 19.73 |
| calibration_role:RECEIVING | 3 | 6.826 → 6.626 | 7.271 → 7.022 | 4.246 → 3.667 | 2.604 → 2.667 | 0.000 → 0.000 | 1.000 → 1.000 | 1.000 → 1.000 | 18.28 → 22.19 |
| calibration_role:ROTATION | 68 | 2.593 → 2.763 | 3.865 → 3.923 | nan → nan | 1.209 → 1.525 | 0.471 → 0.471 | 0.912 → 0.897 | 0.824 → 0.794 | 6.01 → 6.79 |
| calibration_role:SECONDARY | 64 | 5.108 → 5.262 | 7.577 → 7.541 | nan → nan | 1.838 → 2.194 | 0.266 → 0.250 | 0.891 → 0.875 | 0.797 → 0.797 | 12.91 → 13.65 |
| history_status:no_same_team_window_history | 95 | 3.860 → 4.054 | 6.034 → 5.914 | nan → nan | nan → nan | 0.337 → 0.337 | 0.926 → 0.926 | 0.842 → 0.832 | 10.01 → 11.50 |
| history_status:same_team_common_window | 141 | 4.745 → 4.764 | 6.902 → 6.923 | 3.283 → 4.566 | 1.905 → 2.194 | 0.227 → 0.220 | 0.872 → 0.865 | 0.801 → 0.801 | 13.14 → 13.08 |


The original and corrected intervals use unchanged historical residual profiles, so this tests propagation through the fixed calibrator rather than a newly calibrated model. Discrete zero outcomes and clipping explain elevated empirical P10 CDF. Expensive, cheap and role-group results are descriptive; small subgroup counts and one week cannot establish stability. There are no Week 5 outcomes in this evaluation and no independent evidence supporting a new shared anchor coefficient.

## Optimizer comparison

The original 121 eligible players, salary/ownership/context inputs, weights, correlation implementation, stack templates, exposure/overlap controls and selection logic are frozen. Only mean and P90 are replaced. Baseline replay reproduces all five original rosters under each configuration. Solver proof logs and score components are retained. Corrected score normalization maxima are recomputed by the existing strategy, so before/after objective values are not an absolute EV measure. Summed player P90 is an optimizer input summary, not a lineup P90.

### Tight: 2/team, 3/game

Natural corrected exposure: Gibbs 0/5; Wilson 0/5. Original exposure was zero for both. Required-player solves below are diagnostic only.

| Solve | Old objective | New objective | New required-player gap | Old mean | New mean | New salary | Corrected roster |
| --- | --- | --- | --- | --- | --- | --- | --- |
| best | 4.620258 | 5.039942 | 0.000000 | 131.94 | 148.54 | 50000 | Chase Brown, Jaylen Warren, Quinshon Judkins, Sam LaPorta, Michael Wilson, DK Metcalf, Denzel Boston, Bengals, Jacoby Brissett |
| forced_Gibbs | 4.456068 | 4.889608 | 0.150334 | 127.53 | 146.66 | 50000 | Jahmyr Gibbs, Chase Brown, Harold Fannin Jr., Michael Mayer, Michael Wilson, DK Metcalf, Denzel Boston, Vikings, Jacoby Brissett |
| forced_Wilson | 4.585577 | 5.005820 | 0.034122 | 129.89 | 148.14 | 50000 | Chase Brown, Aaron Jones Sr., Sam LaPorta, Michael Wilson, DK Metcalf, Garrett Wilson, Denzel Boston, Seahawks, Jacoby Brissett |

| Entry | Version | Mean | Salary | Objective | Projection term | Ceiling term | Context term | Leverage | Correlation | Players |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | before | 131.94 | 49800 | 4.620258 | 1.668449 | 2.746316 | 0.096464 | 0.000000 | 0.109029 | Chase Brown, Jaylen Warren, Michael Mayer, Amon-Ra St. Brown, Michael Wilson, DK Metcalf, Malik Washington, Vikings, Jacoby Brissett |
| 2 | before | 131.38 | 50000 | 4.591217 | 1.661353 | 2.723521 | 0.097315 | 0.000000 | 0.109029 | Chase Brown, Jonathan Taylor, Jaylen Warren, Sam LaPorta, Michael Wilson, DK Metcalf, Kalif Raymond, Jets, Jacoby Brissett |
| 3 | before | 130.30 | 50000 | 4.566801 | 1.647746 | 2.690737 | 0.107504 | 0.000000 | 0.120814 | Chase Brown, Jaylen Warren, Sam LaPorta, Michael Wilson, DK Metcalf, Devaughn Vele, Luther Burden III, Broncos, Jared Goff |
| 4 | before | 131.72 | 50000 | 4.555644 | 1.665578 | 2.684605 | 0.096432 | 0.000000 | 0.109029 | Chase Brown, Jaylen Warren, Sam LaPorta, Harold Fannin Jr., Jaxon Smith-Njigba, Michael Wilson, Roman Wilson, Commanders, Jacoby Brissett |
| 5 | before | 126.53 | 50000 | 4.421622 | 1.599995 | 2.626274 | 0.083424 | 0.000000 | 0.111929 | Jonathan Taylor, RJ Harvey, Trey McBride, Amon-Ra St. Brown, DK Metcalf, Malik Washington, Roman Wilson, Broncos, Jacoby Brissett |
| 1 | after | 148.54 | 50000 | 5.039942 | 1.878365 | 2.943953 | 0.087454 | 0.000000 | 0.130169 | Chase Brown, Jaylen Warren, Quinshon Judkins, Sam LaPorta, Michael Wilson, DK Metcalf, Denzel Boston, Bengals, Jacoby Brissett |
| 2 | after | 149.11 | 50000 | 5.026897 | 1.885603 | 2.947769 | 0.084496 | 0.000000 | 0.109029 | Chase Brown, Aaron Jones Sr., Harold Fannin Jr., Amon-Ra St. Brown, Michael Wilson, Malik Washington, Denzel Boston, Seahawks, Jacoby Brissett |
| 3 | after | 148.37 | 50000 | 5.015045 | 1.876199 | 2.939079 | 0.090738 | 0.000000 | 0.109029 | Chase Brown, Quinshon Judkins, Harold Fannin Jr., Amon-Ra St. Brown, Michael Wilson, DK Metcalf, Luther Burden III, Vikings, Jacoby Brissett |
| 4 | after | 148.91 | 50000 | 5.004642 | 1.883018 | 2.922770 | 0.089825 | 0.000000 | 0.109029 | Chase Brown, Jonathan Taylor, Sam LaPorta, Harold Fannin Jr., Michael Wilson, DK Metcalf, Matthew Golden, Broncos, Jacoby Brissett |
| 5 | after | 142.41 | 50000 | 4.828228 | 1.800872 | 2.812184 | 0.094357 | 0.000000 | 0.120814 | Jaylen Warren, Aaron Jones Sr., Trey McBride, Sam LaPorta, DK Metcalf, Denzel Boston, Luther Burden III, Vikings, Jared Goff |


### Broad: 4/team, 5/game

Natural corrected exposure: Gibbs 1/5; Wilson 0/5. Original exposure was zero for both. Required-player solves below are diagnostic only.

| Solve | Old objective | New objective | New required-player gap | Old mean | New mean | New salary | Corrected roster |
| --- | --- | --- | --- | --- | --- | --- | --- |
| best | 4.962530 | 5.408923 | 0.000000 | 131.02 | 151.27 | 49900 | Chase Brown, Aaron Jones Sr., Sam LaPorta, Harold Fannin Jr., Amon-Ra St. Brown, Michael Wilson, Isaac TeSlaa, Vikings, Jared Goff |
| forced_Gibbs | 4.772078 | 5.174532 | 0.234391 | 129.02 | 145.88 | 49900 | Jahmyr Gibbs, Chase Brown, Sam LaPorta, Harold Fannin Jr., Michael Wilson, Malik Washington, Isaac TeSlaa, Vikings, Jared Goff |
| forced_Wilson | 4.788303 | 5.220407 | 0.188516 | 124.65 | 143.02 | 49700 | Quinshon Judkins, Emanuel Wilson, Sam LaPorta, Amon-Ra St. Brown, Michael Wilson, Garrett Wilson, Isaac TeSlaa, Vikings, Jared Goff |

| Entry | Version | Mean | Salary | Objective | Projection term | Ceiling term | Context term | Leverage | Correlation | Players |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | before | 131.02 | 49900 | 4.962530 | 1.656736 | 2.716381 | 0.159646 | 0.000000 | 0.429767 | Chase Brown, Jaylen Warren, Sam LaPorta, Amon-Ra St. Brown, Michael Wilson, Malik Washington, Isaac TeSlaa, Jets, Jared Goff |
| 2 | before | 133.41 | 50000 | 4.896583 | 1.687047 | 2.744392 | 0.141124 | 0.000000 | 0.324020 | Chase Brown, Jaylen Warren, Sam LaPorta, Amon-Ra St. Brown, Michael Wilson, DK Metcalf, Kendrick Bourne, Vikings, Jacoby Brissett |
| 3 | before | 130.49 | 49900 | 4.871739 | 1.650060 | 2.632593 | 0.159319 | 0.000000 | 0.429767 | Chase Brown, RJ Harvey, Trey McBride, Sam LaPorta, Amon-Ra St. Brown, DK Metcalf, Isaac TeSlaa, Commanders, Jared Goff |
| 4 | before | 127.12 | 49900 | 4.848516 | 1.607523 | 2.653565 | 0.157662 | 0.000000 | 0.429767 | Chase Brown, Jonathan Taylor, Sam LaPorta, Michael Wilson, DK Metcalf, Jameson Williams, Isaac TeSlaa, Browns, Jared Goff |
| 5 | before | 129.60 | 49700 | 4.755957 | 1.638800 | 2.662134 | 0.131004 | 0.000000 | 0.324020 | Jaylen Warren, RJ Harvey, Trey McBride, Amon-Ra St. Brown, Michael Wilson, DK Metcalf, Isaac TeSlaa, Jets, Jacoby Brissett |
| 1 | after | 151.27 | 49900 | 5.408923 | 1.912877 | 2.913141 | 0.153137 | 0.000000 | 0.429767 | Chase Brown, Aaron Jones Sr., Sam LaPorta, Harold Fannin Jr., Amon-Ra St. Brown, Michael Wilson, Isaac TeSlaa, Vikings, Jared Goff |
| 2 | after | 146.78 | 50000 | 5.332696 | 1.856053 | 2.900574 | 0.146302 | 0.000000 | 0.429767 | Jaylen Warren, Quinshon Judkins, Sam LaPorta, Amon-Ra St. Brown, Michael Wilson, DK Metcalf, Isaac TeSlaa, Broncos, Jared Goff |
| 3 | after | 147.98 | 49900 | 5.319663 | 1.871302 | 2.854393 | 0.164201 | 0.000000 | 0.429767 | Chase Brown, Emanuel Wilson, Sam LaPorta, Michael Mayer, Amon-Ra St. Brown, Michael Wilson, Jameson Williams, Jets, Jared Goff |
| 4 | after | 151.16 | 50000 | 5.294118 | 1.911508 | 2.934486 | 0.124706 | 0.000000 | 0.323417 | Chase Brown, Quinshon Judkins, Sam LaPorta, Amon-Ra St. Brown, Michael Wilson, Denzel Boston, Roman Wilson, Commanders, Jared Goff |
| 5 | after | 134.65 | 50000 | 4.833633 | 1.702687 | 2.681676 | 0.137860 | 0.000000 | 0.311411 | Jahmyr Gibbs, Chase Brown, Trey McBride, Harold Fannin Jr., DK Metcalf, Isaac TeSlaa, Marvin Harrison Jr., Bengals, Jacoby Brissett |


The broad portfolio admits Gibbs naturally once the distorted forecast is repaired. Wilson’s corrected opportunity does not make him optimal at this salary relative to the rest of the corrected pool. Neither non-selection establishes a football projection error. No final lineup is forced or promoted.

## Regression protection and remaining weaknesses

Permanent tests cover a midseason transfer, old-team-only history, an unavailable old-team player, a current-team starter out, supported backup expansion, no same-team history, stale/overlapping histories, cutoff/future-week exclusion, numerical conservation, explicit overcommit rejection, redistribution capacity, fullback classification, salary-team override and missing public workload forecasts. Existing legacy allocation/calibration behavior remains covered. Test evidence:

```
........................................................................ [ 97%]
..                                                                       [100%]
74 passed in 2.53s
.......................                                                  [100%]
23 passed in 4.14s
```

Remaining weaknesses: common windows can be stale when ingestion lacks current-season statistics; absence from a game is not a forward role estimate; partial-window trades and injuries require confidence/freshness modeling; new-player historical-model fallbacks can remain too high for backups; actual vacated workload still needs sourced forward recipient counts; probabilistic availability is applied to allocated workload and subsequently to conditional fantasy means, whose joint calibration remains unvalidated; same-team membership can change within the window; fixed isotonic anchors and residual profiles were learned from legacy features; historical alias mappings are not frozen by effective date; 55% activation remains heuristic rather than validated intervention strength. Team budgets are prior averages, not an independently modeled current-week team-volume forecast.

**Recommendation: keep the default off.** The identity/window repair is mathematically and time-wise supported, but the combined forecasts have not passed a football-quality promotion gate. Require multiple independent prospective or archived prelock weeks, current-season source coverage, realistic backup/new-role forecasts, and position/price/role calibration checks. Refit and calibrate using corrected historical features only inside chronological folds before evaluating promotion. Any 55% coefficient adjustment needs its own independent out-of-time test. No production promotion is authorized by this report.

## Reproducibility

Research inputs and outputs are separate from the original audit under `artifacts/classic_opportunity_repair/`. Fitted `.joblib` bytes are checked against stored SHA-256, and raw saved predictions must reproduce on deserialization. Source/export scripts execute read-only database transactions. Offline replay commands:

```sh
.venv/bin/python scripts/validate_classic_opportunity_repair.py
.venv/bin/python scripts/backtest_classic_opportunity_repair.py
.venv/bin/python scripts/replay_classic_opportunity_optimizer.py
.venv/bin/python scripts/render_classic_opportunity_repair.py
```

The manifest hashes model files, frozen original inputs, repair code, scripts, comparisons and solver logs. Pre-task source copies in `baseline/` distinguish these changes from the existing dirty working tree. Do not rerun capture scripts to reproduce this frozen experiment: use the archived inputs.
