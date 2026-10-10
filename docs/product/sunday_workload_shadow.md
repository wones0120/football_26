# Sunday Main workload evidence shadow — 2026 Week 5

## Result and promotion decision

The current-team workload repair changes all five candidates and the recommended
lineup on the frozen Sunday Main snapshot. It remains **research only**. Better
workload accounting is demonstrated; better GPP paid-finish performance is not.
The live recommendation, strategy contract and all 310 stored projection values
were verified unchanged after the experiment.

This work reuses the existing default-off `team_window_v2` repair rather than
introducing another allocation formula. It adds a reproducible current-slate
experiment and player-level evidence review. It does not add new external snaps,
routes, red-zone or goal-line observations, fill missing evidence with invented
values, or change the app UI. The live policy remains unchanged.

## Evidence improvement

The repair uses a common window of the last three team games, canonical player
IDs and current-team membership. It removes former-team/stale role contamination,
respects team opportunity capacity and leaves unsupported workload unallocated.
Derived carries/targets remain separate from explicit pregame estimates.

The evidence report records player identity, team, source method, history window,
number of observed games, missing explicit fields and review reasons. Among the
121 frozen eligible players, 21 skill players have partial current-team windows
and two lack current-team history. Across all 310 projection rows, 82 skill
players have partial windows and 27 lack current-team history. No audited window
uses prior-season games. Neither recommended roster has these history exceptions
among its skill players; missing explicit pregame forecasts remain a limitation.

One important exception: Darius Slayton's mean rises by 5.60 points while his target
estimate changes from 3.08 to unknown. Removing an unsupported opportunity anchor
restores a model fallback; it does not establish an expanded role. He is not in
either recommended roster. The report preserves this case instead of treating
every increased mean as an improvement.

## Controlled comparison

Source optimizer run: `eb324261-7630-492a-ad78-cad5f72bb43b`.
Projection run: `506c698c-a09c-4665-a79c-058c578de453`.

- The fitted model exactly reproduces all 310 saved mean/P10/P90 projections.
- Archived source versions reproduce all four original historical workload
  inputs within the strict parity checks. Source receipt times and game periods
  are checked against the original cutoff and target week before scoring.
- Training periods precede the target week. Current canonical aliases were used;
  historical alias availability is not independently reconstructed.
- The control reproduces the exact ordered five saved lineups and recommendation.
- The shadow freezes fitted model/training/calibration, availability, markets,
  ownership, salaries, eligible player IDs, tags, user constraints, generation
  weights and the projection-first final selector. It rebuilds workload and
  associated role-importance inputs through the existing repair.
- Both portfolios pass independent constraints. Completion timestamps precede
  the saved October 11, 13:00 EDT kickoff. No target outcomes were used.

Mean changes affect 234 of 310 projection rows and 86 of 121 solver players.
Upstream eligibility/pruning remains frozen; this is not an end-to-end test of
how changed projections would alter the initial candidate pool.

| Recommended roster | Original model mean | Workload shadow mean | Salary |
| --- | ---: | ---: | ---: |
| Live/control | 133.07 | 146.97 | $49,900 |
| Shadow | 129.60 | 150.31 | $49,800 |

The appropriate within-shadow comparison is **150.31 versus 146.97**. Comparing
150.31 directly with the original 133.07 conflates model and roster changes.
The original model favors the live roster by 3.48 points; the shadow favors its
roster by 3.35. Neither difference is a measured cashing advantage.

Shadow roster: Jacoby Brissett, Chase Brown, Jonathan Taylor, Sam LaPorta,
Harold Fannin Jr., Michael Wilson, DK Metcalf, Denzel Boston and Bengals DST.
Live roster remains Jacoby Brissett, Chase Brown, Jaylen Warren, Michael Mayer,
Amon-Ra St. Brown, Michael Wilson, DK Metcalf, Luther Burden III and Commanders DST.

Summed marginal P90 is 250.03 for the shadow recommendation and 232.96 for the
control under their respective models. These are neither comparable calibrated
lineup-tail estimates nor paid-finish probabilities. Expected return and
paid-finish probability remain explicitly unavailable.

## Validation and next gate

31 targeted tests pass: immutable shadow inputs and hashes, invalid forecast
rejection, canonical-ID matching, missing/partial evidence reporting, same-team
window allocation, conservation, cutoff handling and the earlier projection audit.
No production modules, configuration defaults, workers or active data were edited.

Next, evaluate the frozen recommendations against the same verified GPP paid
cutoffs and actual player scores after games finish. Paid finishes are the primary
metric; evaluate net return when complete payout evidence supports it, and top
finishes/upside separately. This script does not install an automatic postgame
job. Prior exploratory historical repair tests did not establish promotion; a
single prospective slate also cannot establish reliable improvement. Require
additional untouched slates and acceptable workload/projection calibration before
changing live selections.

## Reproduction

Artifacts: `artifacts/sunday_workload_shadow/` contains the fitted artifact,
original projections, raw weekly evidence versions, capture script and before/after
live readback. `results/` contains both exact contracts, predictions, workload
review records, team allocations, rosters, solver traces, cross-model scores,
prelock timestamps and input hashes. No outcome labels are loaded.

```sh
PYTHONPATH=. .venv/bin/python scripts/shadow_sunday_workload.py \
  --inputs artifacts/sunday_workload_shadow \
  --source artifacts/sunday_projection_generation/replay_source.json \
  --output /tmp/sunday-workload-shadow-replay
```

The output directory must not exist. Replay requires matching recorded code and
solver fingerprints. A later replay records its actual completion time and does
not acquire the original run's prelock status. Stored fitted artifacts are trusted
application-generated files; do not substitute untrusted model files.
