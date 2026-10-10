# ATL NO corrected projection landscape audit

The corrected forecasts produce a narrow 95% quality universe through **a combination of projection and salary structure, the joint quality screen, and exposure caps**. The full enumeration reproduces A/B/C/D/E/F maximum fills of **3/2/2/2/4/2**. Candidate discovery is not the cause. No live optimizer rule, projection, default, exposure cap, or persisted lineup was changed.

Kevin Austin Jr. has the strongest salary efficiency, but his receiving history comes from a different time window than his recent snaps. His mean rises principally through the opportunity anchor; neither a roster-promotion bonus nor sparse-history fallback explains it. This is a concrete forecast-validation concern, not proof that his projection is incorrect. Shough has the highest absolute mean and P90, costs less than several stars, and enables Saints passing constructions. His universality survives a 90% screen.

Policy A fills five at a diagnostic 93% joint floor, E at 94%, and one-QB B at 92%. Those results support investigating the screen and usage currency before any permanent rule decision. They do not validate a new default or a football projection adjustment.

## Baseline and method

Baseline: 2026 Week 4 ATL–NO Monday Night, corrected projection `023ae6d0-a700-4608-95fd-453029585d94`. The fitted artifact was reloaded by checksum and every eligible player’s mean/P90 reproduced to 1e-6. The 23-player prepared pool and saved production MILP supply legality and selector scoring. No earlier ATL–NO projection run was substituted.

A permits QB Captain and up to two starting QBs, with max five from one team. B keeps QB Captain but permits at most one QB. C permits two QBs and forbids QB Captain; D forbids QB Captain and permits one QB. E follows A with max four from one team; F follows A with max three.

A physical signature is Captain UUID plus the six canonical player UUIDs. FLEX order creates no new roster. Raw mean and summed marginal P90 use 1.5× Captain fantasy points. Selector is the objective of the saved MILP and separately includes context, Captain weighting, format rules, and correlation rewards. Selector ranks are computed before the quality screen and exposure constraints.

Enumeration covers 605,682 six-player/Captain assignments: 583,690 pass salary/team prefilters, and 61,396 satisfy every saved MILP constraint. The 583,690 figure is a prefilter count, not the final legal universe. The earlier rank-pruned universe was sufficient for 95% feasibility but insufficient for whole-universe percentile frequencies; this audit enumerates all legal signatures.

Quality maxima are recalculated within each policy, as in the existing experiment. Each floor holds that policy’s independent mean maximum and P90 maximum fixed. Exposure caps remain integers derived from the requested five entries: QB 5, core/non-punt player 4, salary ≤$1,000 player 2, Captain 3. Underfilled portfolios do not renormalize those caps. Portfolio solves maximize count up to five first, then summed selector. Pairwise overlap counts shared canonical players; it is not simulated fantasy-score correlation.

## Part 1 Projection construction for every eligible player

The fitted gradient-boosting tree consumes salary, market, prior fantasy history, opponent history, prior snaps, and offensive-role features. Exact tree-path contributions and consumed features are retained in `projection_bridge.json`. These are additive explanations of the raw tree, not causal claims. The tree alone does not explicitly forecast routes or snaps.

For non-kickers, base point mean = 0.80 × raw tree + 0.20 × history anchor. History anchor = 0.60 × prior-three-record fantasy mean + 0.40 × prior-eight-record fantasy mean, provided at least three history records exist; otherwise it is the position training mean. When team opportunity context applies, WR/TE opportunity units are modeled targets and RB units are carries + 1.75 × targets. A monotonic isotonic curve fit on prior position data gives the opportunity anchor. The blend weight is 0.55 with at least three records and 0.70 otherwise. QB/DST bypass this opportunity anchor.

Final conditional mean = post-opportunity point mean + the stored market residual adjustment. Availability multiplies the final mean and quantiles; QB participation also multiplies starter probability. All 23 eligible baseline players have participation 1.0. P90 = final conditional mean + the selected walk-forward residual P90, with nonnegative/monotonic quantile enforcement. Residual calibration does not add a separate bonus to mean.

Kicker mean bypasses the tree and uses its own 60/40 history blend. Folk and Carlson both have history; neither uses a peer fallback. The fitted DST point blend uses the position training mean as its history fallback. Barion Brown’s two-record history uses the WR position baseline for the 20% history term and the 70% opportunity weight. Everyone else in this eligible pool has at least three records.

### Prior inputs and current opportunity estimates

Targets and carries show prior three available player-stat records → current allocator volume. Snap share is the mean of the last three available participation records. Those windows need not cover the same games. Expected snaps and routes are unavailable for every eligible player; historical snap share is not an expected snap-count forecast.

| Player | Role | History records | FP prior 3 / 8 | Targets prior → modeled | Carries prior → modeled | Prior snap share |
| --- | --- | --- | --- | --- | --- | --- |
| Falcons | team_defense | 0 | 0.000 / 0.000 | 0.000 → unavailable | 0.000 → unavailable | 0.0% |
| Nick Folk | expected_starter | 266 | 7.000 / 7.000 | 0.000 → unavailable | 0.000 → unavailable | 0.0% |
| Michael Penix Jr. | expected_starter | 15 | 11.640 / 14.250 | 0.000 → unavailable | 1.333 → unavailable | 87.3% |
| Bijan Robinson | expected_starter | 54 | 26.900 / 25.200 | 5.333 → 5.192 | 22.000 → 17.170 | 66.7% |
| Brian Robinson Jr. | expected_backup | 66 | 7.600 / 3.900 | 0.667 → 0.451 | 10.000 → 8.127 | 33.3% |
| Austin Hooper | expected_backup | 161 | 5.367 / 4.312 | 3.000 → 2.022 | 0.000 → unavailable | 29.7% |
| Charlie Woerner | expected_starter | 52 | 0.433 / 1.600 | 0.667 → 0.438 | 0.000 → unavailable | 57.3% |
| Kyle Pitts Sr. | expected_starter | 81 | 1.333 / 12.713 | 2.000 → 1.653 | 0.000 → unavailable | 53.3% |
| Drake London | expected_starter | 65 | 15.267 / 15.000 | 6.333 → 5.641 | 0.667 → unavailable | 84.3% |
| Jahan Dotson | expected_starter | 64 | 2.700 / 2.588 | 3.333 → 2.919 | 0.000 → unavailable | 68.0% |
| Olamide Zaccheaus | expected_starter | 97 | 1.900 / 3.675 | 2.000 → 1.653 | 0.000 → unavailable | 35.7% |
| Zachariah Branch | expected_backup | 3 | 1.700 / 1.700 | 1.333 → 1.059 | 0.000 → unavailable | 22.7% |
| Saints | team_defense | 0 | 0.000 / 0.000 | 0.000 → unavailable | 0.000 → unavailable | 0.0% |
| Daniel Carlson | expected_starter | 133 | 7.000 / 6.375 | 0.000 → unavailable | 0.000 → unavailable | 0.0% |
| Tyler Shough | expected_starter | 14 | 26.127 / 23.315 | 0.000 → unavailable | 4.667 → unavailable | 100.0% |
| Alvin Kamara | expected_starter | 135 | 5.267 / 7.125 | 3.000 → 2.271 | 7.000 → 10.002 | 25.0% |
| Kendre Miller | expected_backup | 22 | 4.533 / 5.475 | 1.000 → 0.657 | 4.667 → 5.957 | 17.3% |
| Juwan Johnson | expected_starter | 82 | 16.433 / 12.825 | 6.333 → 4.029 | 0.000 → unavailable | 66.3% |
| Barion Brown | expected_starter | 2 | 0.150 / 0.150 | 0.000 → 0.000 | 0.500 → unavailable | 5.5% |
| Bryce Lance | expected_backup | 3 | 3.000 / 3.000 | 2.667 → 1.606 | 0.000 → unavailable | 73.3% |
| Chris Olave | expected_starter | 58 | 25.500 / 23.300 | 12.000 → 7.780 | 0.000 → unavailable | 84.7% |
| Devaughn Vele | expected_starter | 26 | 12.733 / 11.200 | 7.333 → 4.750 | 0.000 → unavailable | 91.7% |
| Kevin Austin Jr. | expected_backup | 14 | 8.200 / 5.037 | 5.000 → 4.218 | 0.000 → unavailable | 9.0% |

### Exact numerical bridge

Opportunity Δ is post-opportunity minus base mean, not a measured promotion effect. Kicker override is shown separately because its tree blend is unused. Market Δ below is the additional team-response reconciliation after market features have already entered the tree; it is not the tree’s total market contribution.

| Player | Raw tree | History anchor | Base blend | Opportunity anchor / weight | Opportunity Δ | Market Δ | Kicker override Δ | FLEX mean | P90 residual | FLEX P90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Falcons | 4.974 | 5.261 | 5.031 | unavailable / 0.00 | 0.000 | 0.000 | 0 | 5.031 | 6.763 | 11.795 |
| Nick Folk | 3.957 | 7.000 | 4.566 | unavailable / 0.00 | 0.000 | 0.000 | 2.434 | 7.000 | 5.644 | 12.644 |
| Michael Penix Jr. | 13.196 | 12.684 | 13.093 | unavailable / 0.00 | 0.000 | -0.303 | 0 | 12.790 | 10.812 | 23.602 |
| Bijan Robinson | 16.730 | 26.220 | 18.628 | 17.108 / 0.55 | -0.836 | -0.412 | 0 | 17.380 | 10.035 | 27.415 |
| Brian Robinson Jr. | 3.529 | 6.120 | 4.047 | 6.226 / 0.55 | 1.198 | -0.122 | 0 | 5.124 | 7.910 | 13.034 |
| Austin Hooper | 2.323 | 4.945 | 2.848 | 3.120 / 0.55 | 0.150 | -0.069 | 0 | 2.928 | 5.868 | 8.796 |
| Charlie Woerner | 1.694 | 0.900 | 1.535 | 0.893 / 0.55 | -0.353 | -0.027 | 0 | 1.154 | 4.643 | 5.798 |
| Kyle Pitts Sr. | 9.856 | 5.885 | 9.062 | 2.334 / 0.55 | -3.700 | -0.124 | 0 | 5.237 | 4.643 | 9.881 |
| Drake London | 12.059 | 15.160 | 12.680 | 10.131 / 0.55 | -1.402 | -0.261 | 0 | 11.016 | 12.707 | 23.723 |
| Jahan Dotson | 3.212 | 2.655 | 3.100 | 4.755 / 0.55 | 0.910 | -0.093 | 0 | 3.918 | 9.722 | 13.640 |
| Olamide Zaccheaus | 1.625 | 2.610 | 1.822 | 2.998 / 0.55 | 0.647 | -0.057 | 0 | 2.412 | 5.426 | 7.838 |
| Zachariah Branch | 1.005 | 1.700 | 1.144 | 2.062 / 0.55 | 0.505 | -0.038 | 0 | 1.611 | 5.426 | 7.037 |
| Saints | 5.025 | 5.261 | 5.072 | unavailable / 0.00 | 0.000 | 0.000 | 0 | 5.072 | 6.763 | 11.836 |
| Daniel Carlson | 5.274 | 6.750 | 5.570 | unavailable / 0.00 | 0.000 | 0.000 | 1.180 | 6.750 | 5.644 | 12.394 |
| Tyler Shough | 20.146 | 25.002 | 21.117 | unavailable / 0.00 | 0.000 | 0.541 | 0 | 21.658 | 10.726 | 32.384 |
| Alvin Kamara | 7.717 | 6.010 | 7.376 | 9.508 / 0.55 | 1.173 | 0.219 | 0 | 8.768 | 11.235 | 20.003 |
| Kendre Miller | 5.641 | 4.910 | 5.495 | 4.601 / 0.55 | -0.491 | 0.128 | 0 | 5.132 | 7.910 | 13.042 |
| Juwan Johnson | 13.599 | 14.990 | 13.877 | 7.349 / 0.55 | -3.591 | 0.264 | 0 | 10.550 | 7.130 | 17.680 |
| Barion Brown | 0.480 | 6.499 | 1.684 | 1.213 / 0.70 | -0.330 | 0.035 | 0 | 1.389 | 2.586 | 3.974 |
| Bryce Lance | 3.021 | 3.000 | 3.017 | 2.776 / 0.55 | -0.133 | 0.074 | 0 | 2.958 | 5.184 | 8.142 |
| Chris Olave | 16.771 | 24.620 | 18.341 | 12.499 / 0.55 | -3.213 | 0.388 | 0 | 15.515 | 12.707 | 28.222 |
| Devaughn Vele | 13.457 | 12.120 | 13.189 | 8.749 / 0.55 | -2.442 | 0.275 | 0 | 11.022 | 11.132 | 22.154 |
| Kevin Austin Jr. | 1.337 | 6.935 | 2.456 | 7.257 / 0.55 | 2.640 | 0.131 | 0 | 5.227 | 5.426 | 10.653 |

### Shares and residual calibration

Shares are allocator outputs. Historical role importance remains a historical feature rather than being rewritten by user preferences or by current allocation. STARTER/BACKUP depth labels are distinct from residual calibration roles. The residual scorer recognizes explicit LEAD/COMMITTEE/PRIMARY/SECONDARY/ROTATION; STARTER/BACKUP falls through to measured historical workload classification.

| Player | Target share | RB carry share | Calibration group | Residual sample size | History fallback | Residual shrinkage |
| --- | --- | --- | --- | --- | --- | --- |
| Falcons | 0.0% | 0.0% | DST / DEFENSE | 716 | True | none at selected group size |
| Nick Folk | 0.0% | 0.0% | K / KICKER | 14 | False | parent shrinkage |
| Michael Penix Jr. | 0.0% | 0.0% | QB / POCKET | 559 | False | none at selected group size |
| Bijan Robinson | 21.3% | 53.7% | RB / RECEIVING | 69 | False | none at selected group size |
| Brian Robinson Jr. | 1.9% | 25.4% | RB / COMMITTEE / importance_high | 782 | False | none at selected group size |
| Austin Hooper | 8.3% | 0.0% | TE / ROTATION / importance_high | 527 | False | none at selected group size |
| Charlie Woerner | 1.8% | 0.0% | TE / SECONDARY / importance_low | 371 | False | none at selected group size |
| Kyle Pitts Sr. | 6.8% | 0.0% | TE / SECONDARY / importance_low | 371 | False | none at selected group size |
| Drake London | 23.2% | 0.0% | WR / PRIMARY / importance_high | 498 | False | none at selected group size |
| Jahan Dotson | 12.0% | 0.0% | WR / SECONDARY / importance_high | 538 | False | none at selected group size |
| Olamide Zaccheaus | 6.8% | 0.0% | WR / ROTATION / importance_high | 660 | False | none at selected group size |
| Zachariah Branch | 4.4% | 0.0% | WR / ROTATION / importance_high | 660 | False | none at selected group size |
| Saints | 0.0% | 0.0% | DST / DEFENSE | 716 | True | none at selected group size |
| Daniel Carlson | 0.0% | 0.0% | K / KICKER | 14 | False | parent shrinkage |
| Tyler Shough | 0.0% | 0.0% | QB / MOBILE | 304 | False | none at selected group size |
| Alvin Kamara | 5.5% | 46.2% | RB / LEAD / importance_low | 283 | False | none at selected group size |
| Kendre Miller | 1.6% | 27.5% | RB / COMMITTEE / importance_high | 782 | False | none at selected group size |
| Juwan Johnson | 9.7% | 0.0% | TE / SECONDARY / importance_high | 371 | False | none at selected group size |
| Barion Brown | 0.0% | 0.0% | WR / ROTATION / importance_low | 659 | True | none at selected group size |
| Bryce Lance | 3.9% | 0.0% | WR / SECONDARY / importance_low | 537 | False | none at selected group size |
| Chris Olave | 18.8% | 0.0% | WR / PRIMARY / importance_high | 498 | False | none at selected group size |
| Devaughn Vele | 11.5% | 0.0% | WR / PRIMARY / importance_low | 497 | False | none at selected group size |
| Kevin Austin Jr. | 10.2% | 0.0% | WR / ROTATION / importance_high | 660 | False | none at selected group size |

The selected non-kicker position/role/importance groups have full empirical weight at their group size. The kicker residual group has 14 observations: its role profile shrinks toward the position profile at weight 14/50, and that position profile shrinks toward the global profile at weight 14/30. Kicker mean still uses own history. Position shrinkage reaches full weight at 30 rows, role at 50, and importance-bin shrinkage at 100. The historical calibration promotion gate is blocked because not every position has 30 residual rows. Its overall position/role empirical coverage is not independent validation of this current corrected allocator.

### Recent usage and source windows

Each row shows the last three raw stat records and the last three participation records available before the frozen cutoff, with duplicate captures resolved by their latest record. Blank source windows do not negate the fitted artifact’s separately retained fantasy history. The last target and snap shares are measured historical values, not current expected shares. QB carries in the fitted feature matrix are historical features; the allocator supplies an explicit projected carry count only for RBs.

| Player | Last three stat periods | Last three snap periods | Latest target share | Latest snap share | Target share trend | Snap share trend |
| --- | --- | --- | --- | --- | --- | --- |
| Falcons | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| Nick Folk | 2026 W1, 2026 W2, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.000 | 0.000 | 0.000 | 0.000 |
| Michael Penix Jr. | 2025 W10, 2025 W11, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.000 | 1.000 | 0.000 | 0.127 |
| Bijan Robinson | 2026 W1, 2026 W2, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.087 | 0.720 | -0.165 | 0.013 |
| Brian Robinson Jr. | 2026 W1, 2026 W2, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.000 | 0.270 | -0.034 | -0.020 |
| Austin Hooper | 2025 W22, 2026 W2, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.087 | 0.230 | -0.006 | -0.127 |
| Charlie Woerner | 2025 W16, 2025 W17, 2026 W2 | 2026 W1, 2026 W2, 2026 W3 | 0.032 | 0.610 | 0.006 | 0.220 |
| Kyle Pitts Sr. | 2026 W1, 2026 W2, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.087 | 0.590 | -0.063 | -0.053 |
| Drake London | 2026 W1, 2026 W2, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.435 | 0.930 | 0.222 | 0.083 |
| Jahan Dotson | 2026 W1, 2026 W2, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.130 | 0.660 | 0.025 | -0.113 |
| Olamide Zaccheaus | 2026 W1, 2026 W2, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.087 | 0.340 | 0.021 | 0.060 |
| Zachariah Branch | 2026 W1, 2026 W2, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.087 | 0.180 | 0.055 | -0.070 |
| Saints | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| Daniel Carlson | 2026 W1, 2026 W2, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.000 | 0.000 | 0.000 | 0.000 |
| Tyler Shough | 2026 W1, 2026 W2, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.000 | 1.000 | 0.000 | 0.000 |
| Alvin Kamara | 2025 W12, 2026 W2, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.025 | 0.320 | -0.091 | -0.033 |
| Kendre Miller | 2025 W7, 2026 W1, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.075 | 0.190 | 0.062 | -0.050 |
| Juwan Johnson | 2026 W1, 2026 W2, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.200 | 0.620 | 0.064 | -0.087 |
| Barion Brown | 2026 W1, 2026 W2 | 2026 W1, 2026 W2 | 0.000 | 0.030 | 0.000 | -0.050 |
| Bryce Lance | 2026 W1, 2026 W2, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.075 | 0.720 | 0.021 | -0.020 |
| Chris Olave | 2026 W1, 2026 W2, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.325 | 0.840 | 0.002 | -0.030 |
| Devaughn Vele | 2026 W1, 2026 W2, 2026 W3 | 2026 W1, 2026 W2, 2026 W3 | 0.150 | 0.880 | -0.045 | 0.073 |
| Kevin Austin Jr. | 2025 W17, 2025 W18, 2026 W2 | 2026 W1, 2026 W2, 2026 W3 | 0.031 | 0.140 | -0.140 | -0.227 |

### Football changes and vacated opportunity

Unavailable players retain their football lineage while receiving zero participation. Lost targets stay unallocated unless source-supported recipients and an explicit redistribution assumption identify them. Kevin Austin receives zero vacated targets. Kamara and Miller receive Etienne carry opportunity in proportion to measured prior carries, a committee allocation assumption rather than a sourced numerical split. No automatic Fant-to-Juwan transfer, generic injury fantasy-point transfer, or depth-rank point bonus is applied.

| Team | Opportunity | Lagged team volume | Projected volume | Unallocated volume | Redistributed share |
| --- | --- | --- | --- | --- | --- |
| ATL | carry | 32.000 | 25.297 | 6.703 | 0.000 |
| NO | carry | 21.667 | 16.924 | 4.742 | 0.318 |
| ATL | target | 24.333 | 21.868 | 2.466 | 0.000 |
| NO | target | 41.333 | 28.695 | 12.639 | 0.000 |

| Supported recipient | Opportunity | Own normalized prior volume | Received vacated volume | Expected volume |
| --- | --- | --- | --- | --- |
| Kendre Miller | carry | 3.383 | 2.574 | 5.957 |
| Alvin Kamara | carry | 5.680 | 4.322 | 10.002 |

Only Kamara and Miller receive vacated volume in this freeze: 4.321639 and 2.574189 carries respectively. Every other optimizer-eligible player receives zero vacated targets/carries. No separately identified point bonus is attributed to roster promotion or demotion; the numerical opportunity delta above combines the pooled volume anchor and team allocation, so a causal promotion-only point effect would require an additional counterfactual.

The anchor decreases Olave, Vele, Juwan, Pitts, London, Bijan, Miller, Lance, and Woerner relative to their base blends; it raises Austin, Kamara, Brian Robinson, Dotson, Zaccheaus, Hooper, and Branch. Thus the correction is not a general upward shift. Shough’s mean is 20.146 tree → 21.117 history blend → 21.658 market reconciliation; his source role is QB1. His 32.384 P90 adds 10.726 from the QB residual distribution. Kamara’s 8.768 mean adds 1.173 through the carry/target anchor and 0.219 market adjustment; his LEAD residual group contributes 11.235 to P90. None of these observations by itself proves overprojection.

## Part 2 Kevin Austin Jr diagnostic

### Origin of the 4.218 targets

Austin’s prior targets average 5.000 from **2025 Week 17: 5; 2025 Week 18: 9; 2026 Week 2: 1**. Those source records resolve to canonical UUID `b9c707f4-67b9-425a-a357-7c1e039582df` through nflreadpy source ID `00-0037231`. The raw-row IDs are 472457, 473493, and 498896. His prior target-share average is (5/27 + 9/34 + 1/32)/3 = 0.160380356.

The allocator’s sum of NO prior player target shares is 1.571700113. It normalizes Austin’s prior share to 0.160380356 / 1.571700113 = 0.102042594. Multiplying that by the latest full-team three-game target volume, 41.333333333, gives **4.217760535**. This is a share-times-team-volume estimate, not a new observation of four targets. The normalization lowers his modeled targets below his prior average of five.

There are no 2026 Week 1 or Week 3 receiving stat rows for Austin in the cutoff-safe source slice. Missing rows are not assumed to be measured zero. His fantasy three-record mean is (15.2 + 7.7 + 1.7)/3 = 8.2, and his eight-record mean is 5.0375. His history anchor is therefore 6.935. He has 14 history records and does not use the sparse-player position baseline.

His participation window is different: 2026 Weeks 1–3 have 5/5/10 offensive snaps and shares 6%/7%/14%, yielding **9%** mean snap share. His latest measured target share is **3.125%**; its stored trend versus the preceding three stat records is **−13.999 percentage points**. Late-2025 receiving usage is therefore being carried into a forecast whose recent participation is materially lower.

### Mean and ceiling mechanisms

Raw tree 1.336695589 and history anchor 6.935 produce base mean **2.456356471**. Because team opportunity context is active, the WR isotonic curve maps his 4.217760535 targets to a **7.256994576** opportunity anchor. A 55% blend gives 0.45×2.456356471 + 0.55×7.256994576 = **5.096707429**, a **+2.640350958** adjustment. Market reconciliation adds **0.130590425**, giving **5.227297853**.

His prior offensive-role importance 0.142785267 exceeds the WR ROTATION median split 0.083703704. The selected high-importance ROTATION group has **660 residual observations**, no sparse-bin shrinkage, and residual P90 **5.426010822**. Final P90 is **5.227297853 + 5.426010822 = 10.653308676**. The residual increment is 50.93% of that marginal P90 level. It is not a separable causal share of tail probability. Using the parent ROTATION profile would add 4.036100470 instead; the selected group adds 1.389910353 more. That comparison describes calibration selection and does not authorize changing his profile.

Residuals are learned from chronological tree/history point predictions. The current opportunity-anchor and market-reconciliation stages are not applied by `generate_walk_forward_residuals`. Consequently, historical residual coverage does not directly establish calibration of the full current corrected bridge. This applies to the model generally and is not an Austin-only sparse-history issue.

### Answers to the ten individual questions

1. **Target origin:** normalized own prior target share × full-team prior volume, as shown above.
2. **Own measured usage:** yes, but the last three available receiving records span late 2025 and 2026 Week 2.
3. **Inherited unavailable-player work:** zero received targets, zero redistribution. Unavailable teammates can activate team context and the anchor, which is an indirect model-stage effect, not inherited volume.
4. **October 1 active-roster promotion:** it establishes roster availability and eligibility. It supplies no numeric targets, routes, snaps, or promotion bonus.
5. **Roster membership versus offensive role:** represented separately in source facts and depth labels. Numeric receiving workload nevertheless remains based on measured history; BACKUP is not mapped to a new target cap or reduction. `pregame_newly_assigned_role` is false.
6. **Consistency with expected backup:** not logically impossible, since backups can receive targets. It is insufficiently supported as a current expectation because it combines older receiving usage with 9% recent snaps and a latest one-target record. Forecast validity remains unresolved.
7. **Routes/snaps support:** no projected routes or expected snap counts are supplied. Recent measured snaps do not independently validate 4.218 targets.
8. **P90 usage versus calibration:** usage anchor adds 2.640 to the point mean; market adds 0.131; the residual profile adds 5.426 above final mean.
9. **Fallback inflation:** no player-history fallback, peer-copying, or sparse residual fallback applies to Austin. The opportunity curve is a position-level peer relationship blended at 55%; the residual group is also pooled. Those mechanisms, plus stale usage, merit scrutiny.
10. **Analogues:** current and archived examples follow below; older archives are contextual comparisons and never replace this corrected baseline.

### Current and archived cheap-player analogues

Current sourced backups Lance, Branch, Hooper, and Brian Robinson retain positive football assessments, but none is near-mandatory at 95%. Austin’s $800 price is unusual relative to his forecast. Charlie Woerner is $600 and has P90 5.798, but is a sourced expected starter, not a backup; low salary alone is insufficient for universality.

| Current player | Salary | Mean | P90 | A joint95 frequency | A top1 selector frequency |
| --- | --- | --- | --- | --- | --- |
| Bryce Lance | 1800 | 2.958 | 8.142 | 9.1% | 17.9% |
| Charlie Woerner | 600 | 1.154 | 5.798 | 4.5% | 11.2% |
| Brian Robinson Jr. | 3800 | 5.124 | 13.034 | 18.2% | 24.1% |
| Kevin Austin Jr. | 800 | 5.227 | 10.653 | 95.5% | 35.3% |
| Zachariah Branch | 2400 | 1.611 | 7.037 | 0.0% | 8.6% |
| Austin Hooper | 2800 | 2.928 | 8.796 | 9.1% | 10.9% |

Archived 2026 Week 2 KC–IND selects Brashard Smith ($400, mean 2.701, P90 10.726) in 2/5 production entries. The Week 3 ATL–GB freeze selects Josh Whyle in 1/5 and Chris Brooks in 1/5. These demonstrate that inexpensive secondary players can matter structurally. Their official backup designation and exhaustive historical 95% mandatory frequency are not established by those archives. The Week 2 DET–BUF role audit also has Tay Martin ($800, rotational, mean 2.029/P90 4.560), Jackson Hawes ($600, rotational, 1.813/6.947), Keleki Latu ($200, rotational, 1.541/6.675), and Skyler Bell ($200, missing role evidence, 2.429/9.719). That prior run used the superseded salary-fallback allocator and is not evidence that current corrected ceilings are validated. A systematic historical cohort of officially sourced backups is still needed to establish prevalence and calibration of the mechanism.

## Part 3 Football strength and salary relief

Near-mandatory means ≥75% of that policy’s joint95 universe, a descriptive cutoff used only in this audit. Across A–F the near/mandatory set is Shough, Austin, Bijan, Olave, and Penix. Austin is the only inexpensive backup in that set. Full per-policy top 1/5/10/25% frequencies for all eligible players are saved in `player_rank_frequencies.csv`.

### Efficiency and whole-universe selector ranks

The following percentile columns refer to A’s **entire 61,396 legal roster universe**. Rankings include ties at each boundary. Roster frequencies are unweighted counts, not probabilities that a lineup is optimal, and not selected portfolio exposures.

| Player | Salary | Mean | P90 | Mean / $1k | P90 / $1k | A joint95 | A top1% | A top5% | A top10% | A top25% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Kevin Austin Jr. | 800 | 5.227 | 10.653 | 6.534 | 13.317 | 95.5% | 35.3% | 30.8% | 29.6% | 27.4% |
| Tyler Shough | 9600 | 21.658 | 32.384 | 2.256 | 3.373 | 100.0% | 100.0% | 99.0% | 96.4% | 89.4% |
| Charlie Woerner | 600 | 1.154 | 5.798 | 1.924 | 9.663 | 4.5% | 11.2% | 11.6% | 11.7% | 13.0% |
| Bryce Lance | 1800 | 2.958 | 8.142 | 1.643 | 4.523 | 9.1% | 17.9% | 20.5% | 22.3% | 22.7% |
| Bijan Robinson | 11800 | 17.380 | 27.415 | 1.473 | 2.323 | 72.7% | 27.0% | 29.3% | 32.6% | 37.0% |
| Chris Olave | 10800 | 15.515 | 28.222 | 1.437 | 2.613 | 95.5% | 87.1% | 67.8% | 57.4% | 42.9% |
| Juwan Johnson | 7400 | 10.550 | 17.680 | 1.426 | 2.389 | 22.7% | 21.7% | 25.5% | 25.5% | 26.6% |
| Michael Penix Jr. | 9000 | 12.790 | 23.602 | 1.421 | 2.622 | 50.0% | 58.1% | 53.8% | 53.6% | 56.6% |
| Devaughn Vele | 7800 | 11.022 | 22.154 | 1.413 | 2.840 | 40.9% | 51.1% | 49.6% | 46.2% | 38.6% |
| Daniel Carlson | 4800 | 6.750 | 12.394 | 1.406 | 2.582 | 13.6% | 13.8% | 17.6% | 18.4% | 20.6% |
| Falcons | 3600 | 5.031 | 11.795 | 1.398 | 3.276 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| Brian Robinson Jr. | 3800 | 5.124 | 13.034 | 1.348 | 3.430 | 18.2% | 24.1% | 23.5% | 24.6% | 25.9% |
| Jahan Dotson | 3000 | 3.918 | 13.640 | 1.306 | 4.547 | 13.6% | 26.1% | 22.4% | 21.8% | 22.3% |
| Nick Folk | 5400 | 7.000 | 12.644 | 1.296 | 2.341 | 4.5% | 12.7% | 17.9% | 18.8% | 20.9% |
| Alvin Kamara | 7000 | 8.768 | 20.003 | 1.253 | 2.858 | 31.8% | 30.1% | 28.5% | 30.5% | 31.5% |
| Saints | 4200 | 5.072 | 11.836 | 1.208 | 2.818 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| Olamide Zaccheaus | 2000 | 2.412 | 7.838 | 1.206 | 3.919 | 4.5% | 11.7% | 12.8% | 13.5% | 15.2% |
| Barion Brown | 1200 | 1.389 | 3.974 | 1.157 | 3.312 | 0.0% | 7.8% | 13.1% | 14.9% | 17.2% |
| Drake London | 10000 | 11.016 | 23.723 | 1.102 | 2.372 | 9.1% | 24.6% | 26.1% | 27.5% | 27.9% |
| Austin Hooper | 2800 | 2.928 | 8.796 | 1.046 | 3.141 | 9.1% | 10.9% | 12.5% | 12.9% | 14.7% |
| Kendre Miller | 5000 | 5.132 | 13.042 | 1.026 | 2.608 | 4.5% | 15.8% | 18.5% | 20.4% | 23.1% |
| Kyle Pitts Sr. | 5800 | 5.237 | 9.881 | 0.903 | 1.704 | 0.0% | 4.1% | 8.2% | 9.8% | 12.7% |
| Zachariah Branch | 2400 | 1.611 | 7.037 | 0.671 | 2.932 | 0.0% | 8.6% | 11.0% | 11.7% | 13.9% |

### Frequency under every 95% policy

| Player | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| Saints | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| Bijan Robinson | 72.7% | 100.0% | 90.9% | 100.0% | 86.2% | 100.0% |
| Falcons | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| Drake London | 9.1% | 12.5% | 3.0% | 3.4% | 13.8% | 0.0% |
| Nick Folk | 4.5% | 0.0% | 0.0% | 3.4% | 6.9% | 16.7% |
| Tyler Shough | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| Bryce Lance | 9.1% | 12.5% | 12.1% | 6.9% | 13.8% | 0.0% |
| Michael Penix Jr. | 50.0% | 0.0% | 51.5% | 0.0% | 55.2% | 100.0% |
| Juwan Johnson | 22.7% | 31.2% | 27.3% | 20.7% | 17.2% | 0.0% |
| Charlie Woerner | 4.5% | 0.0% | 6.1% | 0.0% | 3.4% | 0.0% |
| Brian Robinson Jr. | 18.2% | 25.0% | 12.1% | 20.7% | 17.2% | 16.7% |
| Barion Brown | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| Jahan Dotson | 13.6% | 12.5% | 12.1% | 24.1% | 20.7% | 16.7% |
| Chris Olave | 95.5% | 87.5% | 84.8% | 93.1% | 79.3% | 66.7% |
| Kyle Pitts Sr. | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| Alvin Kamara | 31.8% | 25.0% | 18.2% | 31.0% | 10.3% | 0.0% |
| Olamide Zaccheaus | 4.5% | 6.2% | 9.1% | 6.9% | 6.9% | 16.7% |
| Kevin Austin Jr. | 95.5% | 100.0% | 100.0% | 100.0% | 93.1% | 100.0% |
| Devaughn Vele | 40.9% | 56.2% | 54.5% | 65.5% | 51.7% | 33.3% |
| Zachariah Branch | 0.0% | 0.0% | 3.0% | 6.9% | 3.4% | 16.7% |
| Austin Hooper | 9.1% | 6.2% | 6.1% | 10.3% | 6.9% | 16.7% |
| Kendre Miller | 4.5% | 6.2% | 3.0% | 3.4% | 3.4% | 0.0% |
| Daniel Carlson | 13.6% | 18.8% | 6.1% | 3.4% | 10.3% | 0.0% |

Austin has only 5.227 football points of mean, but **6.534 mean and 13.317 P90 per $1,000**, both the highest in the pool. He costs $800 versus Lance $1,800, Zaccheaus $2,000, Hooper $2,800, and Dotson $3,000. Those alternatives generally either cost more or lose point mean/ceiling. Woerner costs $200 less but loses 4.073 mean and 4.856 P90; it is not an equivalent cheap replacement.

Removing the salary constraint while holding football forecasts, all other saved policy legality, and the **original dollar-constrained maxima** fixed makes Austin-free ≥95% lineups possible under every policy. That isolates his essential salary-relief value. This diagnostic does not claim salary-neutral lineups are legal entries.

| Policy | Best joint fraction without Austin | Without Austin and without salary cap | Austin-free joint95 signatures | Austin cap + free signatures | Certified max fill |
| --- | --- | --- | --- | --- | --- |
| A | 95.0061% | 113.3686% | 1 | 2 + 1 | 3 |
| B | 94.9614% | 111.3567% | 0 | 2 + 0 | 2 |
| C | 93.4814% | 114.3906% | 0 | 2 + 0 | 2 |
| D | 94.9624% | 112.0086% | 0 | 2 + 0 | 2 |
| E | 95.6505% | 114.1897% | 2 | 2 + 2 | 4 |
| F | 94.6927% | 114.1897% | 0 | 2 + 0 | 2 |

The Austin bound is exact: A has one qualifying signature without Austin, E has two, B/C/D/F have none. Since every signature can be used at most once and Austin may appear twice, fills cannot exceed 3/4/2 respectively; each bound has a feasible witness. In B/D/F, Bijan is also universal and his four-appearance cap becomes relevant if Austin’s cap alone is relaxed. Other caps can still bind after one restriction is lifted.

Austin universality is particularly close to the cutoff in B and D: their best Austin-free joint fractions miss 95% by only **0.0386 and 0.0376 percentage points**. A’s only Austin-free qualifying signature clears it by just **0.0061 percentage points**. In B, Austin-free rosters can independently clear either 95% mean or 95% P90, but no single Austin-free roster clears both. Mandatory status therefore depends on the exact intersection, not only on a large individual-projection gap. All decisions use full precision; rounding these fractions to one decimal place would hide the distinction.

Shough’s **21.658 mean and 32.384 P90** are the pool’s absolute maxima, and his $9,600 salary is below Olave ($10,800), Bijan ($11,800), and London ($10,000). Penix is only $600 cheaper but loses 8.868 mean and 8.782 P90. Bijan and Olave are near-mandatory because they supply premium raw points; they are not cheap relief. Penix becomes universal in F because the balanced six-player construction plus two-QB scoring and its tighter policy maxima constrain alternatives. It is not universally required under A–E.

## Part 4 Shough universality

Both quality dimensions independently exclude every Shough-free A roster at 95%. The best Shough-free mean is 71.047 against 83.513838125, a **12.466813041** deficit. The best Shough-free summed marginal P90 is 136.456 against 145.548896481, a **9.092690836** deficit. Those best values occur in different rosters. The best common quality fraction without Shough is only **80.8186%**, so relaxing to 90% does not remove his universality.

### A best legal lineups with and without Shough

“Best” depends on the objective. Each row below is the exact independent maximum for its criterion. The maximum-selector Shough lineup itself fails the 95% mean floor; selector strength is distinct from joint screen qualification.

| Condition / objective | Captain | Mean | Summed marginal P90 | Selector | Salary | Split | Roster |
| --- | --- | --- | --- | --- | --- | --- | --- |
| With Shough / mean | Tyler Shough | 87.909 | 144.940 | 153.949 | 50000.000 | ATL 1/NO 5 | Bijan Robinson, Tyler Shough, Juwan Johnson, Chris Olave, Kevin Austin Jr., Daniel Carlson |
| With Shough / p90 | Tyler Shough | 85.810 | 153.209 | 162.994 | 49800.000 | ATL 1/NO 5 | Tyler Shough, Michael Penix Jr., Chris Olave, Alvin Kamara, Kevin Austin Jr., Devaughn Vele |
| With Shough / selector | Chris Olave | 82.478 | 148.579 | 170.220 | 49200.000 | ATL 2/NO 4 | Bijan Robinson, Tyler Shough, Jahan Dotson, Chris Olave, Kevin Austin Jr., Devaughn Vele |
| Without Shough / mean | Bijan Robinson | 71.047 | 131.141 | 135.681 | 49900.000 | ATL 3/NO 3 | Bijan Robinson, Michael Penix Jr., Charlie Woerner, Chris Olave, Alvin Kamara, Daniel Carlson |
| Without Shough / p90 | Jahan Dotson | 67.702 | 136.456 | 148.021 | 49900.000 | ATL 5/NO 1 | Bijan Robinson, Drake London, Michael Penix Jr., Brian Robinson Jr., Jahan Dotson, Chris Olave |
| Without Shough / selector | Drake London | 62.640 | 134.086 | 151.290 | 48600.000 | ATL 4/NO 2 | Drake London, Michael Penix Jr., Brian Robinson Jr., Jahan Dotson, Chris Olave, Alvin Kamara |

The best mean with Shough uses Shough CPT, Bijan, Juwan, Olave, Austin, Carlson (ATL 1/NO 5, $50,000). The best mean without him uses Bijan CPT, Penix, Woerner, Olave, Kamara, Carlson (3/3, $49,900). This replaces Shough/Juwan/Austin with Penix/Woerner/Kamara and moves Captain to Bijan. It is a legal construction change, not a one-for-one projection perturbation.

The saved lineup constraints require at least one QB. A Saints WR/TE Captain requires the Saints QB; selecting more than one Saints receiver also requires Shough. Shough CPT requires at least two same-team pass catchers. These rules reduce the options without Shough and are held fixed. In the mean-max Shough roster he correlates with Juwan, Olave, and Austin; the mean-max Shough-free roster has Penix paired with Woerner. The selector separately awards saturated stacks and format/correlation bonuses. The P90-max Shough roster includes Penix without an ATL WR/TE, which is allowed by the saved constraints. No frozen joint score-draw matrix exists, so a numeric fantasy-score correlation is unavailable; these are construction correlations.

| Policy | Mean95 floor | Best no-Shough mean | Mean gap | P90 95 floor | Best no-Shough P90 | P90 gap | Best no-Shough joint fraction |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | 83.514 | 71.047 | -12.467 | 145.549 | 136.456 | -9.093 | 80.8% |
| B | 83.514 | 71.047 | -12.467 | 143.127 | 136.456 | -6.671 | 80.8% |
| C | 81.447 | 71.047 | -10.400 | 141.150 | 136.456 | -4.694 | 82.9% |
| D | 79.768 | 71.047 | -8.721 | 141.150 | 136.456 | -4.694 | 84.6% |
| E | 82.951 | 71.047 | -11.904 | 144.502 | 135.917 | -8.585 | 81.4% |
| F | 82.951 | 71.047 | -11.904 | 144.502 | 135.277 | -9.225 | 81.4% |

Shough’s universality is mathematically justified **conditional on the frozen projections, salaries, and saved correlation legality**. It is not an independent empirical validation of his football forecast or those correlation rules. His point mean is not unusually inflated by the new opportunity mechanism: that mechanism does not apply to QBs. Removing salary alone still leaves Shough-free A below 95% (best 92.321%). This audit supplies no evidence-based reason to reduce him just because he is universal.

## Part 5 Joint quality floor sensitivity

Each universe table reports all quality-eligible physical signatures. Each portfolio table reports the exact count-first, selector-second solution under the unchanged requested-five caps. The separate frequency table shows both denominators to prevent confusing structural frequency with final allocation. Lower-floor solutions can contain higher-scoring portfolios without raising every average; summed selector is not directly comparable across different portfolio sizes.

### Policy A quality universe

| Joint floor | Legal physical rosters | Quality signatures | Captains | Players | Pairwise overlap | Average mean | Average P90 | Team splits | QB counts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 95.0% | 61396 | 22 | 3 | 18 | 3.931 | 85.142 | 147.684 | ATL 1/NO 5: 6; ATL 2/NO 4: 13; ATL 3/NO 3: 3 | 1: 11; 2: 11 |
| 94.0% | 61396 | 44 | 5 | 19 | 3.924 | 84.627 | 146.554 | ATL 1/NO 5: 9; ATL 2/NO 4: 25; ATL 3/NO 3: 10 | 1: 21; 2: 23 |
| 93.0% | 61396 | 88 | 6 | 21 | 3.674 | 83.518 | 145.539 | ATL 1/NO 5: 18; ATL 2/NO 4: 52; ATL 3/NO 3: 18 | 1: 44; 2: 44 |
| 92.0% | 61396 | 148 | 7 | 21 | 3.489 | 82.875 | 144.459 | ATL 1/NO 5: 30; ATL 2/NO 4: 86; ATL 3/NO 3: 32 | 1: 74; 2: 74 |
| 90.0% | 61396 | 404 | 12 | 21 | 3.217 | 81.366 | 142.055 | ATL 1/NO 5: 86; ATL 2/NO 4: 215; ATL 3/NO 3: 99; ATL 4/NO 2: 4 | 1: 211; 2: 193 |

### Policy A maximum feasible portfolio

| Joint floor | Entries | Captains | Players | Pairwise overlap | Average mean | Average P90 | Portfolio selector | Team splits | QB counts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 95.0% | 3 | 2 | 10 | 3.667 | 84.338 | 149.071 | 489.049 | ATL 1/NO 5: 1; ATL 2/NO 4: 2 | 1: 1; 2: 2 |
| 94.0% | 4 | 2 | 12 | 3.333 | 83.306 | 146.594 | 650.671 | ATL 2/NO 4: 3; ATL 3/NO 3: 1 | 1: 2; 2: 2 |
| 93.0% | 5 | 2 | 12 | 3.300 | 82.453 | 146.978 | 807.906 | ATL 1/NO 5: 1; ATL 2/NO 4: 3; ATL 3/NO 3: 1 | 1: 2; 2: 3 |
| 92.0% | 5 | 3 | 12 | 3.400 | 82.424 | 147.806 | 808.805 | ATL 1/NO 5: 1; ATL 2/NO 4: 4 | 1: 1; 2: 4 |
| 90.0% | 5 | 3 | 12 | 3.400 | 81.008 | 145.961 | 822.704 | ATL 2/NO 4: 3; ATL 3/NO 3: 2 | 1: 3; 2: 2 |

### Policy A player frequencies

Each cell is quality-universe frequency / selected-portfolio frequency.

| Joint floor | Tyler Shough | Kevin Austin Jr. | Bijan Robinson | Alvin Kamara | Michael Penix Jr. | Chris Olave |
| --- | --- | --- | --- | --- | --- | --- |
| 95.0% | 100.0% / 100.0% | 95.5% / 66.7% | 72.7% / 33.3% | 31.8% / 33.3% | 50.0% / 66.7% | 95.5% / 100.0% |
| 94.0% | 100.0% / 100.0% | 93.2% / 50.0% | 84.1% / 75.0% | 18.2% / 0.0% | 52.3% / 50.0% | 81.8% / 100.0% |
| 93.0% | 100.0% / 100.0% | 83.0% / 40.0% | 75.0% / 60.0% | 19.3% / 20.0% | 50.0% / 60.0% | 83.0% / 80.0% |
| 92.0% | 100.0% / 100.0% | 77.0% / 40.0% | 71.6% / 40.0% | 20.9% / 60.0% | 50.0% / 80.0% | 77.0% / 80.0% |
| 90.0% | 100.0% / 100.0% | 64.9% / 40.0% | 68.3% / 80.0% | 22.3% / 20.0% | 47.8% / 40.0% | 73.0% / 80.0% |

### Policy E quality universe

| Joint floor | Legal physical rosters | Quality signatures | Captains | Players | Pairwise overlap | Average mean | Average P90 | Team splits | QB counts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 95.0% | 43806 | 29 | 4 | 19 | 3.919 | 84.716 | 146.788 | ATL 2/NO 4: 23; ATL 3/NO 3: 6 | 1: 13; 2: 16 |
| 94.0% | 43806 | 58 | 5 | 21 | 3.689 | 83.739 | 145.891 | ATL 2/NO 4: 43; ATL 3/NO 3: 15 | 1: 29; 2: 29 |
| 93.0% | 43806 | 98 | 6 | 21 | 3.491 | 83.043 | 144.821 | ATL 2/NO 4: 71; ATL 3/NO 3: 27 | 1: 44; 2: 54 |
| 92.0% | 43806 | 165 | 8 | 21 | 3.367 | 82.487 | 143.672 | ATL 2/NO 4: 117; ATL 3/NO 3: 48 | 1: 78; 2: 87 |
| 90.0% | 43806 | 415 | 14 | 21 | 3.142 | 80.961 | 141.410 | ATL 2/NO 4: 278; ATL 3/NO 3: 128; ATL 4/NO 2: 9 | 1: 199; 2: 216 |

### Policy E maximum feasible portfolio

| Joint floor | Entries | Captains | Players | Pairwise overlap | Average mean | Average P90 | Portfolio selector | Team splits | QB counts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 95.0% | 4 | 2 | 11 | 3.500 | 83.442 | 146.670 | 650.428 | ATL 2/NO 4: 4 | 1: 2; 2: 2 |
| 94.0% | 5 | 3 | 12 | 3.500 | 82.571 | 147.393 | 806.872 | ATL 2/NO 4: 4; ATL 3/NO 3: 1 | 1: 2; 2: 3 |
| 93.0% | 5 | 3 | 12 | 3.400 | 82.263 | 147.434 | 807.498 | ATL 2/NO 4: 4; ATL 3/NO 3: 1 | 1: 1; 2: 4 |
| 92.0% | 5 | 2 | 12 | 3.400 | 81.536 | 147.263 | 810.673 | ATL 2/NO 4: 3; ATL 3/NO 3: 2 | 1: 1; 2: 4 |
| 90.0% | 5 | 2 | 12 | 3.300 | 80.483 | 144.736 | 824.266 | ATL 2/NO 4: 3; ATL 3/NO 3: 2 | 1: 2; 2: 3 |

### Policy E player frequencies

Each cell is quality-universe frequency / selected-portfolio frequency.

| Joint floor | Tyler Shough | Kevin Austin Jr. | Bijan Robinson | Alvin Kamara | Michael Penix Jr. | Chris Olave |
| --- | --- | --- | --- | --- | --- | --- |
| 95.0% | 100.0% / 100.0% | 93.1% / 50.0% | 86.2% / 75.0% | 10.3% / 0.0% | 55.2% / 50.0% | 79.3% / 100.0% |
| 94.0% | 100.0% / 100.0% | 81.0% / 40.0% | 81.0% / 60.0% | 12.1% / 20.0% | 50.0% / 60.0% | 82.8% / 80.0% |
| 93.0% | 100.0% / 100.0% | 72.4% / 40.0% | 77.6% / 40.0% | 15.3% / 40.0% | 55.1% / 80.0% | 74.5% / 80.0% |
| 92.0% | 100.0% / 100.0% | 70.9% / 40.0% | 77.6% / 40.0% | 16.4% / 20.0% | 52.7% / 80.0% | 69.7% / 80.0% |
| 90.0% | 100.0% / 100.0% | 57.8% / 40.0% | 73.3% / 80.0% | 16.4% / 20.0% | 52.0% / 60.0% | 68.2% / 60.0% |

### Policy B quality universe

| Joint floor | Legal physical rosters | Quality signatures | Captains | Players | Pairwise overlap | Average mean | Average P90 | Team splits | QB counts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 95.0% | 44602 | 16 | 3 | 15 | 4.292 | 85.091 | 146.642 | ATL 1/NO 5: 6; ATL 2/NO 4: 10 | 1: 16 |
| 94.0% | 44602 | 29 | 5 | 18 | 4.126 | 84.211 | 145.771 | ATL 1/NO 5: 7; ATL 2/NO 4: 21; ATL 3/NO 3: 1 | 1: 29 |
| 93.0% | 44602 | 66 | 5 | 19 | 3.777 | 83.235 | 143.967 | ATL 1/NO 5: 15; ATL 2/NO 4: 44; ATL 3/NO 3: 7 | 1: 66 |
| 92.0% | 44602 | 103 | 7 | 19 | 3.714 | 82.697 | 143.017 | ATL 1/NO 5: 27; ATL 2/NO 4: 68; ATL 3/NO 3: 8 | 1: 103 |
| 90.0% | 44602 | 262 | 9 | 20 | 3.462 | 81.175 | 140.826 | ATL 1/NO 5: 75; ATL 2/NO 4: 157; ATL 3/NO 3: 30 | 1: 262 |

### Policy B maximum feasible portfolio

| Joint floor | Entries | Captains | Players | Pairwise overlap | Average mean | Average P90 | Portfolio selector | Team splits | QB counts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 95.0% | 2 | 2 | 7 | 5.000 | 84.617 | 149.316 | 329.661 | ATL 2/NO 4: 2 | 1: 2 |
| 94.0% | 4 | 2 | 10 | 4.167 | 83.215 | 146.205 | 646.514 | ATL 2/NO 4: 3; ATL 3/NO 3: 1 | 1: 4 |
| 93.0% | 4 | 2 | 9 | 4.500 | 83.031 | 147.475 | 652.147 | ATL 2/NO 4: 3; ATL 3/NO 3: 1 | 1: 4 |
| 92.0% | 5 | 2 | 11 | 3.500 | 82.249 | 145.394 | 797.473 | ATL 2/NO 4: 4; ATL 3/NO 3: 1 | 1: 5 |
| 90.0% | 5 | 2 | 13 | 3.200 | 79.566 | 142.479 | 811.763 | ATL 1/NO 5: 1; ATL 2/NO 4: 3; ATL 3/NO 3: 1 | 1: 5 |

### Policy B player frequencies

Each cell is quality-universe frequency / selected-portfolio frequency.

| Joint floor | Tyler Shough | Kevin Austin Jr. | Bijan Robinson | Alvin Kamara | Michael Penix Jr. | Chris Olave |
| --- | --- | --- | --- | --- | --- | --- |
| 95.0% | 100.0% / 100.0% | 100.0% / 100.0% | 100.0% / 100.0% | 25.0% / 0.0% | 0.0% / 0.0% | 87.5% / 100.0% |
| 94.0% | 100.0% / 100.0% | 82.8% / 50.0% | 100.0% / 100.0% | 17.2% / 0.0% | 0.0% / 0.0% | 93.1% / 100.0% |
| 93.0% | 100.0% / 100.0% | 78.8% / 50.0% | 95.5% / 100.0% | 19.7% / 0.0% | 0.0% / 0.0% | 81.8% / 100.0% |
| 92.0% | 100.0% / 100.0% | 74.8% / 40.0% | 92.2% / 80.0% | 21.4% / 20.0% | 0.0% / 0.0% | 81.6% / 80.0% |
| 90.0% | 100.0% / 100.0% | 65.3% / 40.0% | 85.9% / 80.0% | 23.7% / 20.0% | 0.0% / 0.0% | 77.5% / 80.0% |

A’s eligible signatures increase 22 → 404 between 95% and 90%; E 29 → 415; B 16 → 262. A reaches five at 93%, E at 94%, B at 92%. All still contain Shough. Austin’s universe frequency drops from 95.5% to 64.9% in A, 93.1% to 57.8% in E, and 100% to 65.3% in B. This is screen sensitivity rather than a forecast change.

## Part 6 Which quality dimension binds

Mean-only rejection means mean is below the chosen floor while P90 passes it; P90-only is the converse; both means both fail. The next tables classify **every roster in the fixed joint90 universe** at each higher threshold. This is a consistent cohort, so the categories sum to the 90% count on every row. `analysis_v2.json` also reports all-legal rejection counts and the broader cohort where either dimension clears 90%. Per-signature classifications for the broader cohort are saved in `rejection_band_A.csv.gz` through F.

### Policy A rejection distribution from the joint90 cohort

| Floor | Mean only | P90 only | Both | Pass both |
| --- | --- | --- | --- | --- |
| 95.0% | 36 | 31 | 315 | 22 |
| 94.0% | 52 | 38 | 270 | 44 |
| 93.0% | 69 | 63 | 184 | 88 |
| 92.0% | 85 | 65 | 106 | 148 |
| 90.0% | 0 | 0 | 0 | 404 |

### Policy E rejection distribution from the joint90 cohort

| Floor | Mean only | P90 only | Both | Pass both |
| --- | --- | --- | --- | --- |
| 95.0% | 42 | 29 | 315 | 29 |
| 94.0% | 60 | 47 | 250 | 58 |
| 93.0% | 83 | 71 | 163 | 98 |
| 92.0% | 100 | 63 | 87 | 165 |
| 90.0% | 0 | 0 | 0 | 415 |

### Policy B rejection distribution from the joint90 cohort

| Floor | Mean only | P90 only | Both | Pass both |
| --- | --- | --- | --- | --- |
| 95.0% | 41 | 8 | 197 | 16 |
| 94.0% | 62 | 15 | 156 | 29 |
| 93.0% | 79 | 21 | 96 | 66 |
| 92.0% | 82 | 25 | 52 | 103 |
| 90.0% | 0 | 0 | 0 | 262 |

The screen is a restrictive intersection for A and E. Among A’s 404 joint90 signatures, the 95% floor rejects 315 on both, 36 on mean only, and 31 on P90 only; 22 pass. B is more mean-led: 41 fail mean only versus eight P90 only, with 197 failing both. C’s mean-only universe still has a two-entry capacity, so P90 is not the sole cause of underfill there.

| Policy | 95% mean only | 95% P90 only | 95% both | Reduction vs mean only | Reduction vs P90 only | Same independent maximizing signature |
| --- | --- | --- | --- | --- | --- | --- |
| A | 54 | 71 | 22 | 59.3% | 69.0% | False |
| B | 24 | 84 | 16 | 33.3% | 81.0% | False |
| C | 48 | 199 | 33 | 31.2% | 83.4% | False |
| D | 70 | 86 | 29 | 58.6% | 66.3% | False |
| E | 58 | 83 | 29 | 50.0% | 65.1% | True |
| F | 16 | 24 | 6 | 62.5% | 75.0% | True |

A’s independent mean maximum (87.909303) has P90 **144.940106**, below the P90 floor **145.548896** by **0.608790**. Its independent P90 maximum (153.209365) has mean 85.809833 and passes the mean floor. This is a real competing-maximum effect, but the intersection is not empty. E’s independent mean/P90 maxima come from the same roster; nevertheless its intersection falls from 58 mean-only or 83 P90-only signatures to 29. A narrow intersection can therefore occur even without different maximizing rosters.

### Exposure and screen diagnostics at 95%

These are counterfactual research solves. All nonvaried rules and player projections stay fixed; none is a live change.

| Policy | Current joint95 | Mean screen only | P90 screen only | Only Austin cap relaxed | All player caps relaxed | Captain caps relaxed |
| --- | --- | --- | --- | --- | --- | --- |
| A | 3 | 5 | 5 | 5 | 5 | 3 |
| B | 2 | 4 | 5 | 4 | 5 | 2 |
| C | 2 | 2 | 5 | 5 | 5 | 2 |
| D | 2 | 4 | 5 | 4 | 5 | 2 |
| E | 4 | 5 | 5 | 5 | 5 | 4 |
| F | 2 | 4 | 5 | 3 | 3 | 2 |

Relaxing only Captain caps never improves current 95% capacity. Removing all player caps allows five in each policy. Relaxing only Austin permits five in A/C/E, four in B/D, and three in F. Thus cheap-player exposure is the immediate universal-player bottleneck, while other player caps and construction constraints become relevant after it is lifted. In A/E, a single quality dimension is enough for five under unchanged caps; in B the mean-only screen still limits fill to four.

## Part 7 Mathematical design review

The supplied request stops after “Evaluate whether the current quality screen is mathematically”. The review here addresses the screen’s mathematical interpretation and observed behavior; any missing requested comparison or acceptance criterion remains unspecified.

The joint screen is mathematically well-defined as min(mean/max_mean, summed_marginal_P90/max_summed_marginal_P90) ≥ α. It places a rectangular admissible region in two objective dimensions, with maxima found independently. It is feasible here, reproducible, and sufficient to explain underfill with exposure caps. It does not guarantee a diverse or fillable portfolio, nor do its coordinate maxima incorporate portfolio constraints.

**Summed marginal P90 is not a lineup P90.** Quantiles do not generally add. Summing six player 90th-percentile fantasy outcomes, including the Captain multiplier, aligns marginal tail levels without a joint score distribution. Perfectly aligned monotone outcomes are a special case where they do add; realistic shared targets, touchdowns, team volume, and opponent interactions do not establish that condition. Existing correlation selector terms do not turn the sum into a jointly calibrated 90th percentile. Therefore “95% ceiling quality” is a marginal-tail proxy threshold, not a demonstrated guarantee about lineup ceiling or contest EV.

This proxy can reward pooled residual variance separately from modeled opportunity. Austin’s modest raw tree mean is raised by the opportunity curve and then receives a pooled tail increment; Dotson’s 13.640 P90 versus 3.918 mean is another large residual contribution. Requiring both near-max point mean and near-max sum of residual-based ceilings favors a small set of high-point stars plus efficient salary relief, then exposure caps prohibit repeating that relief often enough.

The separate policy reference maxima mean E and A use different numerical floors: E’s lower constrained maxima partially explain why E admits 29 signatures at 95% versus A’s 22, despite stricter team balance. E’s quality universe need not be a subset of A’s when each is normalized to its own maximum. This is not proof that max-four improves underlying football quality or EV.

A sensible next design experiment would compare a calibrated joint lineup-draw measure, a validated EV/selector regret floor, and the current two-coordinate proxy on historical slates, with portfolio capacity and forecast error reported together. A Pareto or composite-score floor changes the tradeoff and would require explicit validation. The observed 93%/94% fill breakpoints are diagnostics, not justified production defaults. Current player forecast currency should be resolved before attributing every effect to the screen.

## Findings that justify follow-up

The projection arithmetic and optimizer feasibility are confirmed. The current forecasts are not independently established as correct football expectations. Austin’s mismatch between receiving and participation windows is the clearest individual concern. The team allocator normalizes shares from player-specific last-available-record windows, so stale individual windows can also affect the denominator and other receivers. The opportunity curve is a pooled usage anchor, not a route-based player forecast, and the residual calibration has not been walk-forward evaluated through the complete corrected opportunity/market bridge.

Priorities are to verify current receiving-stat coverage through Week 3, distinguish true measured zeros from missing/inactive records, preserve the actual observation periods in role diagnostics, and evaluate the full corrected bridge on time-safe historical replay. Source-confirmed snaps/routes or explicit expected target evidence would clarify whether Austin’s backup role supports four targets. These are proposed future investigations; no forecast correction is asserted or applied here.

The results support **combination** as the answer to the five-way diagnostic: projection/salary structure establishes Austin and Shough value, the joint95 screen makes alternative signatures scarce, and the requested-five player caps convert scarcity into underfill. The evidence does not establish that one aggressive forecast alone caused the problem, and it does not support reducing Shough solely for universality.

## Validation and reproducibility

All six policy raw maxima, 95% signature counts, maximum portfolio counts, and optimal selectors match the earlier independent corrected certificates within 1e-6. Every previously retained signature score agrees with the full enumeration, and 101 deterministic full-universe legal samples agree with the scalar certifier. An additional 151 samples of the entire assignment space verify both acceptance and rejection (17 accepted, 134 rejected). All 23 fitted-artifact mean/P90 bridges reproduce the saved corrected forecasts within 1e-6. Each selected research portfolio satisfies unique signatures and the original player/Captain caps.

The two existing tests in `backend/app/tests/product/test_showdown_policy_audit.py` pass. Both new research scripts compile, and `git diff --check` passes. Delivery/source checksums, 23 decomposition rows, 138 policy/player rank rows, 30 threshold/denominator rows, all rejection partitions, and selected-witness quality thresholds were independently checked.

No application or optimizer source was edited in this task. Database source reads ran in explicitly read-only transactions. The audit added research scripts, immutable/checksummed JSON artifacts, compressed full-universe arrays, diagnostic CSVs, and this report. The broad working-tree changes already present in the repository belong to earlier work and are not part of this audit.

Run `.venv/bin/python -m scripts.audit_atl_no_projection_landscape --stage capture` to reproduce fitted-artifact/source reads, then `.venv/bin/python -m scripts.audit_atl_no_projection_landscape` for enumeration/analysis and `.venv/bin/python -m scripts.render_atl_no_projection_landscape` for supporting diagnostics and report tables. Existing JSON artifacts are immutable; use a fresh output directory or matching existing captures for a new run. The fitted artifact and local database are required only for the capture stage.

Supporting artifacts: `projection_bridge.json` (all inputs and exact stages), `prior_usage.json` (canonical raw stat/participation evidence), `analysis_v2.json` (all A–F threshold and rank results), `supplementary.json` (single-dimension/cap diagnostics), `full_universe.npz` (all certified signatures), `player_efficiency.csv`, `player_rank_frequencies.csv`, `projection_decomposition.csv`, `threshold_metrics.csv`, and per-policy compressed rejection files. Data and code hashes are retained in JSON/manifest files.
