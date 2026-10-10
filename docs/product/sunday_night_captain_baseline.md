# Sunday-night Captain baseline — 2026 Week 5

The two bounded tasks are complete: prepare Sunday night through the app, then
validate and freeze the existing-policy baseline. No selection weights or
production code changed. No contests were entered. Further experiments are deferred.

## Preparation

- Imported `/Users/wones/NFL/DKSalaries_2026_5_SUNDAY_NIGHT.csv` through the app.
  Native draft group **154487** was verified from the file's original macOS download
  metadata; original URL and file SHA are saved in the artifacts.
- The initial attempt correctly blocked on Matt Hibner's two native salary IDs.
  Verified the Matt/Matthew variant with the [Ravens roster](https://www.baltimoreravens.com/team/players-roster/)
  and [NFL roster](https://amp.nfl.com/teams/baltimore-ravens/roster): BAL, TE, No. 88.
  Used the app's resolution service to link CPT `44446771` and FLEX `44446719`
  to canonical `9bbbe3d4-5e67-4d5c-bc57-83d6d7cabe7c` (nflreadpy `00-0040879`).
  The source aliases and evidence notes are persisted, preventing repeat matching.
- All **104 salary rows / 52 canonical players** now resolve.
- Retried preparation job `7a1ab015-66d1-4094-a453-f3d3925294a4` completed **READY**.
  Projection: `b2cb7c1f-3777-49c1-a4ab-3251db063dce`.
  Ownership: `8b0f6fb4-bfd7-4910-a38f-dbb02389bf96`.
  Information cutoff: `2026-10-10T14:22:58.128091Z`.

## Frozen baseline

Optimizer run `e2d12880-844d-4f90-852d-50fbac0d7559` uses the existing
`showdown_gpp_portfolio_v3` policy with five requested lineups. It generated 174
distinct internal candidates and returned five. The app's separate provisional
projection-first recommendation compares those five on unconditioned forecasts.

Recommended lineup 1: **Drake London CPT**, with Bijan Robinson, Derrick Henry,
Michael Penix Jr., Matt Hibner and Austin Hooper at FLEX. Salary **$49,900**;
projected points **79.09**. No saved availability exception appears on this
recommended lineup. Another returned candidate includes questionable Zay Flowers;
this does not affect the frozen baseline recommendation.

Role ownership remained diagnostic: the existing optimizer disabled its selector
term uniformly because the evidence was incomplete or not explicitly approved.
No override or new weight was introduced. Paid-finish probability and expected
return remain unavailable; the projection-first choice is not validated GPP edge
or final prelock injury clearance.

## Validation and tracking

All five rosters passed unique-player, one-Captain, both-team and salary-cap checks.
Native slot salaries and DraftKings IDs match the imported pool. Scoring checks
confirm the Captain multiplier is applied once. Export validation passed, and
re-evaluating saved candidates reproduces the saved recommendation exactly.

Simulation `8d83e408-cd0e-4021-9545-e2f70492f49e` completed **100/100 draws** with
seed 502. Persisted rows exactly match the returned rows. This is a workflow
smoke test of `independent_quantile_showdown_v1`, not a calibrated opponent-field
or paid-finish simulation.

Registered the verified baseline through the existing outcome service as
`925d513aa4f210232750bff3b83d85bee3edfa92f0185c227d803e186516b878`.
It is visible in **Learning → GPP shadow comparisons** and awaits imported results.
Only the control arm exists so far. The registered player forecasts use the same
unconditioned, slot-weighted baseline as the recommendation; scenario discovery
scores are retained separately. Captain actuals are normalized and weighted once
by the postgame scorer.

Sunday Main's saved recommendation, projection reference and strategy contract
were compared against the prior frozen record and remain unchanged.

Artifacts and the checked registration script are under
`artifacts/sunday_night_captain_baseline/`. All operational jobs in this pass have
completed; no additional experiments or recurring tasks were scheduled.

## Next work, deferred to conserve usage

Review Captain candidate coverage and ranking in shadow mode, prioritizing GPP
paid finishes, with return and upside separate. Keep the current baseline frozen
and use fresh prelock preparation for any actual entry decision. Monday-night
preparation remains outstanding; it was outside this two-task pass.
