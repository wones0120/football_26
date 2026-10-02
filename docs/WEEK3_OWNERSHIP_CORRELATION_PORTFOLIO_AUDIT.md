# Week 3 ownership, correlation, and portfolio audit

This audit uses saved runs and resolved historical outcomes. It does not retune
any player, ownership, or correlation weight to fit Week 3.

## Ownership: source and lineage

The frozen Week 3 run used `slate_aware_ownership_v1`. Future refreshes use
`slate_aware_ownership_v2_prelock` to identify the changed historical feature
provenance in persisted run lineage. Both fit a Huber gradient-boosting regressor on contest
ownership from strictly earlier season/weeks. Inputs include salary, projection,
value, player/slot/format prior ownership, slate size, position, roster slot,
and Classic versus Showdown. It does **not** model contest type, field size,
entry limit, or late-news role changes as separate features. Historical
contest-slot observations are averaged per player/slot/slate, so different
contests are pooled. The optimizer reads `target.ownership_projection` from a
pinned `ownership_run_id` when provided; Classic sums non-CPT projected slots.
There is one shared model, not separate fits by slate type or contest format:
Classic/Showdown and roster position are categorical inputs, position is
categorical, and salary, salary percentile, projection percentile, and value
are numeric inputs. Sunday Main versus Thursday is represented only indirectly
through slate size and format. The optimizer does not translate an overall
slate forecast into a particular contest's field ownership.
Late news can influence the ownership estimate only through updated
projection inputs; there is no explicit news, role-change, or time-to-lock
feature in this model.
The prediction is already in percentage-point units, clipped to `[0, 100]`
and passed to the optimizer without a second scale conversion. No factor-of-100
output bug was found.

The saved Week 3 Sunday Main optimizer run
`2ef9ee7e-d2a1-4cc4-bf88-b89e5f40a2c5` pinned ownership run
`2757c7cd-0e27-42bd-bb60-487ae77f3e44`. Its selected player values match
that run exactly. For example, Kenneth Walker III was 6.65%, Denzel Boston
1.74%, and Jalen Coker 4.46%. This rules out a stale ownership run as the
cause of those three values. The selected contest observations put Walker at
roughly 44–47% in RB plus another 3% in FLEX, Boston at 14–16% in WR plus
roughly 1–2% in FLEX, and Coker at 11–14% in WR plus roughly 1% in FLEX.
The frozen model run records 4,238 training rows from prior season/weeks.

Run `PYTHONPATH=. .venv/bin/python scripts/audit_ownership_calibration.py`
to rebuild [the full calibration artifact](../artifacts/ownership-calibration-historical.json).
The script selects the latest saved ownership run strictly before the slate's
first weekday kickoff, matches canonical player IDs within each contest, and
sums position and FLEX ownership for Classic players. It covers every local
slate with both a saved pre-lock forecast and resolved contest ownership:
2026 W2 Monday/Thursday and W3 Sunday Main/Thursday (9 contests, 1,328
contest-player observations). Historical slates without saved pre-lock
forecasts cannot be evaluated as live forecasts.

| Scope | Rows | MAE | RMSE | Bias, projected − actual | Correlation |
| --- | ---: | ---: | ---: | ---: | ---: |
| All matched observations | 1,328 | 3.69 | 7.18 | +0.18 | 0.68 |
| 2026 W3 Sunday Main | 900 | 2.16 | 4.83 | −0.77 | 0.56 |

Across all nine contests, 1,039 observations were projected below 5%; 71
actually exceeded 10%, 14 exceeded 20%, and 2 exceeded 30%. In Sunday Main
alone the corresponding counts were 55, 12, and 2 of 816 projected below 5%.
For actual ownership 30–50%, the mean forecast was 19.92% against 39.44%
actual (28 observations). Conversely, the highest *projected* bucket overpredicted
on average. This is evidence of tail compression and ranking misses; overall
bias alone hides them. The JSON also contains projected and actual bucket
calibration, top-ten projected players per contest, position, salary tier,
slate, format, contest type, field-size slices, and individual matched values.
Contest type is recorded as `unknown` for all nine matched contests, so its
slice cannot establish format-specific calibration.

The model's saved 2.78-point walk-forward MAE is not a valid promotion gate
for the current features: many active 2025 projection runs were created in
2026, after those games. Historical projection features now require both a
recorded data cutoff and creation time before their own game kickoff, with
the cutoff no later than creation, and must match the historical slate. A read-only
shadow with that provenance guard had 3.17-point walk-forward MAE, versus
2.78 for the prior reconstruction and 4.21 for the prior-player baseline.
On the frozen W3 Sunday contest, the guarded shadow had 2.42 MAE versus 2.11
for the saved run. This safety correction does not claim an accuracy gain.
New runs record eligible historical projection-feature coverage under
`model_metrics.input_provenance`.
No calibration layer was promoted. Additional genuinely pre-lock weeks are
needed to compare candidates chronologically, particularly for high-owned
players and contest-specific ownership.

To verify a new run, read its model version and run ID in Operations after
**Run Ownership Model** or an automatic refresh. The version must be
`slate_aware_ownership_v2_prelock`; the run must report rows written and
persisted target lineage. This confirms which code and forecast the optimizer
used, not that the forecast is accurate. After contests resolve, rerun the
calibration audit and inspect the high-ownership tail, position/slate slices,
and individual misses before considering the model repaired for decisions.

## Strategy and correlation

`classic_small_field_gpp` deliberately uses the existing Classic GPP candidate
solver and its `classic_large_gpp_v1` rule profile. The resolver, player-pool
safety check, correlation term builder, candidate score reconstruction, and
global portfolio selector all use that generic profile. No validated
small-field-specific correlation profile exists. The mismatch is now an
explicit `borrowed_unvalidated` warning in strategy resolution, run lineage,
and the optimizer report. Unexpected policy IDs fail fast. No stack or
bring-back weight changed.
The frozen small-field solver uses 35% normalized mean, 48% summed player
ceiling, 17% correlation, and no soft ownership contribution. It generates
the requested candidate pool, expands legal quality/QB families, then chooses
the final portfolio by summed selector score under active constraints. The
borrowed profile's `initial_policy_unvalidated` status remains visible.

The [historical stack artifact](../artifacts/classic-stack-outcomes-historical.json)
uses saved Classic Sunday Main GPP lineups created before the first kickoff,
deduplicates identical rosters within a slate, and joins resolved contest
actuals in W1/W3 or canonical feature-matrix actuals in W2. It has 64 fully
scored unique lineups across W1–W3. The mean actual scores are 125.80 for
QB+1 (8 lineups), 131.44 for QB+1 with a bring-back (2), 129.85 for QB+2
(21), and 150.87 for QB+2 with a bring-back (19). QB+3 variants are also in
the artifact. Naked QB was not generated by the current pass-catcher rule.
The artifact separates game total, implied team total, spread, slate, and
available contest size. Only one lineup has a stored contest field size;
most Week 1 market context is unavailable. These are selected-lineup
observations, not a randomized or payout-adjusted comparison. They do not
support a small-field versus large-field weight change. The earlier
[Week 2 correlation shadow](../artifacts/sunday-main-correlation-oneoff-audit-2026w2.md)
shows the second-pass-catcher reward materially changes construction on one
slate, but one replay is not sufficient to promote a new policy.

## Portfolio controls and reports

Classic small-field runs now accept `params.portfolio_constraints` with optional
`max_lineup_overlap` (0–8 shared players), `distinct_qb_paths` (boolean), and
`max_objective_loss` (nonnegative difference from the best candidate's selector
score). These are applied jointly in the exact final portfolio selection.
The UI exposes the same controls; all are off by default because the limited
historical replay does not establish a universal threshold. Infeasible
combinations return no selected portfolio and an explicit error. Strong plays
can remain heavily exposed unless the user configures a constraint that
prevents it.

The Classic small-field report now shows the requested strategy and applied
correlation profile, active portfolio controls, player and game exposure,
QB stack families, pairwise overlap, core and unique players, construction
archetype, summed projected mean and player ceiling, ownership, leverage
proxy, and a selection reason for each lineup. The ceiling and leverage
values are proxies, not calibrated first-place probabilities or payout EV.
