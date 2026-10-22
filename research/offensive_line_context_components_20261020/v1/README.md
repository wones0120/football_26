# G13 measured team protection/run-result context

This isolated B04 package implements four explicitly defined team-result measurements from authenticated prior PBP. It does not estimate individual blocker ability or attribute causality to the offensive line.

| ID | Definition |
|---|---|
| G13-M04 | Source sacks divided by official passing attempts plus sacks. Official attempts include spikes; sacks count once; scrambles do not enter this denominator. |
| G13-M08 | First_down_rush OR rushing_TD divided by nonkneel official rushes with known preplay ydstogo<=2. QB scrambles remain legitimate rushes. |
| G13-M09 | Native play net yards<0 divided by nonkneel official rushes. Zero-yard stuffs are not classified behind the line. |
| G13-M10 | ProviderEPA>0 success fraction by native run_location left/middle/right. Unknown direction is a separate residual and masks complete rates for potentially affected known directions. |

Grain is canonical source team/native game; every native period is before the target. Per-game known/unknown eligibility/outcome denominators are retained. Trailing windows pool known exposures across the lastN observed games rather than average game rates; they do not imply certified complete logs. Missing data produces null complete rates, with explicitly named known-sample rates remaining available. Unknown ydstogo on a possible rush remains unknown, while known outside the short-yard subset is false rather than an unknown exposure.

Native `run_gap` is retained in semantic source ancestry but is not a defensive-front or blocking-assignment inference. Pressure, time-to-pressure and vendor win-rate fields are absent in the verified current PBP header; alternate-source availability is unresolved. Historical starting-line continuity and missing-line availability are outside this PBP-result package; A owns the separate availability/depth source features (including G13-M02). No global source-blocked claim follows.

The actual reader validates the immutable indexed snapshot/parent at the original evidence boundary, preserves actual postlock read/derive/publication clocks, and marks outputs nonserving. Normal current/forecast/scenario use rejects them. No model fit, FP bonus, user-filtered denominator, source fetch or database mutation occurs.

Tests cover physical attempt+sack conservation, spike/scramble/kneel distinctions, short-yard and strict negative-yard definitions, native directions/unknown residuals, missing data, pooled exposure windows, prior periods, excluded rows, source revision/recapture semantics and postlock rejection. Actual artifacts and coverage are in `actual_derivation_receipt.json`; exact selected slice/hash and current-use checks are in `actual_QA.json`.
