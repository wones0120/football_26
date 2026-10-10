# Current Classic GPP challenger protocol

Fixed before this experiment's outcome comparison: challenger
`classic_gpp_mean_guarded_upside_shadow_v1` retains candidates with at least 98%
of the highest projected total, then maximizes the sum of marginal player P90s.
Ties use projected total, then canonical roster hash. Missing or inconsistent P90
on any valid candidate makes the challenger unavailable. Export-invalid candidates
are excluded by the unchanged production validator. No new lineup is generated.

Hypothesis: allowing a small, fixed sacrifice in mean for upside may improve
paid finishes when the paid cutoff is above the projected mean. This is an
uncalibrated hypothesis; neither summed P90 nor the mean band estimates a paid
probability. No weights or thresholds will be optimized against these results.

Compare only `classic_large_gpp_v1` Sunday Main returned candidates. Freeze all
forecast-only choices before joining actuals, standings or entry history. Use the
most recent eligible run per slate as the primary descriptive comparison; list all
other runs separately as dependent sensitivity cases. Previously viewed Weeks 3
and 4 are not untouched holdouts. Missing scores, payout evidence or prelock clocks
remain exclusions/unknowns. Capture the upcoming Sunday Main choices separately,
with a timestamp and input hash; keep all live recommendations and optimizer
configuration unchanged. Runtime services must not import the shadow module.
