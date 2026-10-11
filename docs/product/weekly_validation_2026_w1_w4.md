# 2026 Weeks 1–4: projection and GPP lineup validation

Completed October 10, 2026. The reproducible read-only audit covers **251 completed
GPP optimizer runs** across Classic and Captain. **175 pass historical replay
screening**; repeated runs are not independent trials. This is an exploratory
comparison against imported actuals, not a certified walk-forward training study.
Live projections, recommendations, model settings and database rows are unchanged.

## What to improve first

1. **Shortlisting for a single recommended lineup, especially Captain.** Week 4
   Sunday Night's latest eligible Captain replay scored **111.37**, also the best
   of its five returned lineups. Its saved 136-candidate pool was fully scoreable
   and contained a **164.74** lineup, above both verified paid cutoffs (**130.05**
   and **130.63**). Generation found a paid candidate; shortlisting removed it.
   The pregame selector cannot use hindsight to identify that winner. Test the
   already-frozen expanded-shortlist challenger on untouched slates before promotion.
2. **Workload and uncertainty calibration for relevant players.** Full-pool error
   averages obscure larger errors for players projected for at least 10 base
   points. Validate workload estimates and interval coverage by position/role,
   using external prelock benchmarks and future outcomes. Do not apply blanket
   point increases or tune player-specific corrections to these weeks.
3. **Complete results and contest evidence.** Import Week 2 Sunday Main standings,
   Week 3/4 Monday Night standings, and missing paid-place/native-contest metadata.
   Add a reliable canonical player-game actuals feed for projected players absent
   from contest observations. Full payout ladders remain missing everywhere in
   this audit, preventing counterfactual dollar-return validation.

Increasing generation volume is not the first supported intervention. The clearest
paid-finish misses already had paid candidates in saved pools. Neither these
hindsight comparisons nor a higher projected mean justify a live policy change.

## Classic Sunday Main

Projection metrics use the latest eligible saved projection snapshot per slate,
selected by time before outcome scoring. MAE is mean absolute error in DraftKings
points; bias is forecast minus actual. Unmatched scores are unknown, never zero.

| Week | Matched / projection rows | MAE | Bias | MAE for forecast ≥10 | Primary GPP replay actual | Paid / known GPPs |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 360 / 368 | 4.23 | -0.70 | 8.90 | 202.10 | 1 / 1 |
| 2 | 0 / 426 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 3 | 363 / 591 | 4.12 | -0.04 | 6.01 | 117.60 | 0 / 3 |
| 4 | 347 / 392 | 4.19 | +0.12 | 7.18 | 153.90 | 3 / 3 |

The Week 3 primary run is **historical small-field**, not today's large-GPP path.
It returned at best 139.20 while its saved search pool contained a 157.00 candidate
that cleared all three paid cutoffs. Only 192/212 pool candidates have complete
actuals, so 157.00 is the best observed, not a certified pool maximum.
The latest eligible **large-GPP** Week 3 run scored **146.90**, clearing **2/3**
cutoffs. Do not attribute the small-field failure directly to the current strategy.
Week 4's large-GPP replay cleared every known GPP cutoff; its best returned
candidate scored 158.58, only 4.68 above the chosen roster.

For forecast ≥10 players, nominal P10–P90 coverage was **63.1%, 79.5%, and 71.6%**
in Weeks 1, 3 and 4 (65, 78 and 74 matched players). Nominal coverage is 80%.
These few correlated slate samples motivate calibration research, not proof of
systematic failure or a new interval width. Week 4 WR MAE was **5.10** across 123
matched WRs, versus **4.44** RB and **3.27** TE; positional scales differ.

Classic early-only has no saved/imported evaluation evidence in these weeks.
Late-only has projection snapshots for Weeks 1/2 but no same-slate contest actuals;
Weeks 3/4 have no saved/imported scope. The report does not claim those slates
were offered or played. An imported Week 2 Sunday Night contest has a Classic
format label; it remains isolated from Showdown rather than silently relabeled.

## Captain by week and slate

Player errors use unconditioned **base FLEX points**. Captain observations are
normalized to base points; lineup scoring applies 1.5 exactly once.

| Week / slate | Matched / projections | Base-point MAE | Replayed lineup forecast → actual | Paid / known GPPs |
|---|---:|---:|---:|---:|
| 1 Wednesday | 37 / 37 | 3.57 | 85.45 → 48.22 | unknown |
| 1 Sunday | 33 / 33 | 3.91 | no eligible pregame lineup run | unknown |
| 2 Thursday | 30 / 30 | 5.68 | 91.17 → 139.20 | unknown |
| 2 Sunday | 34 / 34 | 4.65 | 78.54 → 71.75 | unknown |
| 2 Monday | 33 / 33 | 5.15 | 85.80 → 122.53 | unknown |
| 3 Thursday | 44 / 47 | 3.06 | 78.87 → 130.17 | 3 / 3 |
| 3 Monday | 0 / 46 | unavailable | results missing | unknown |
| 4 Thursday | 41 / 41 | 2.67 | 65.62 → 106.73 | 2 / 2 |
| 4 Sunday | 43 / 44 | 3.63 | 102.60 → 111.37 | 0 / 2 |
| 4 Monday | 0 / 47 | unavailable | results missing | unknown |

Forecasts in the lineup column come from each saved replay roster; the separate
projection audit may select a later eligible projection snapshot. Strategies also
changed across these weeks, so this is not a single unchanged-policy performance
series. These are hypothetical policy replays, not the user's entered winnings.

Forecast ≥10 base-point player MAE is **9.08–11.73** across Week 2's three Captain
slates and **10.41** on Week 4 Sunday Night. Samples are only 7–10 players per
slate. Several show underprediction; Week 1 Wednesday instead overpredicts that
cohort. This argues for role/volume diagnosis and calibration, not uniform boosts.
Week 2 Sunday also shows a final-selection opportunity: the replay chose 71.75
actual points from a returned set containing 115.03. Missing paid-place evidence
prevents labeling that a paid-finish miss.

## Missing evidence and recovery

- `target.fact_player_game_actual` has no 2026 Weeks 1–4 records. Labels in this
  audit come from resolved imported contest observations. Conflicting scores are
  excluded; unused players and missing slates remain unscored. Coverage is not a
  random sample, so comparisons across slates need care.
- Week 2 Sunday Main and Week 3/4 Monday Night lack imported standings. Other
  absent early/late/night scopes appear in the full matrix; absent evidence does
  not establish that a contest was played.
- Earlier Captain contests often have synthetic contest IDs or generic names;
  account-history enrichment does not establish a paid cutoff for those records.
  Verify native contest linkage and classification before paid-finish claims.
- No imported contest in this audit has a complete, reconciled GPP payout ladder.
  Paid-cutoff comparisons are possible for selected contests, but dollar-return
  and expected-return superiority remain unestablished.
- Some historical lineups are postkickoff, have missing game evidence or fail
  current export validation. Each excluded run retains its reasons. Do not backdate
  or reconstruct a supposedly pregame choice from outcomes.
- Legacy projection game IDs sometimes reverse team order or use LA/LAR aliases.
  The audit recovers kickoff only through an unambiguous season/week/team-pair
  match to imported schedules, recording both IDs and the match basis. Native-ID
  conflicts remain excluded. It does not change stored identities or infer names.
- Historical model reproducibility and source availability are separate from
  comparing already-saved forecasts. This report does not certify full historical
  training provenance or authorize refitting on the evaluated weeks.

## Reproduction and validation

### QB Captain paid finishes and rushing touchdowns

A follow-up read-only audit of the 24 imported Captain contests found **470
resolved QB-captain entries wholly within the top 10% that are verified paid**
across seven contests with complete fields and account-history paid-place counts.
These represent six distinct QB/game performances, all with **zero rushing TDs**
in the imported NFL weekly stats:

| Week / slate | QB Captain | Verified paid top-10% entries | Rushing TDs |
|---|---|---:|---:|
| 3 Thursday | Michael Penix Jr. | 4 | 0 |
| 3 Thursday | Jordan Love | 72 | 0 |
| 4 Thursday | Aaron Rodgers | 232 | 0 |
| 4 Thursday | Deshaun Watson | 65 | 0 |
| 4 Sunday | Bryce Young | 71 | 0 |
| 4 Sunday | Jared Goff | 26 | 0 |

Entry counts include duplicate rosters and multiple contests in the same game;
they are not independent QB performances. There are 11,246 additional resolved
top-10% QB-captain entries with unknown paid status, 219 entries in tied groups
straddling the top-10% boundary, and eight unresolved top-decile-entry rosters.
Unknown paid status does not mean a loss. These counts cannot estimate the cash
rate of choosing a QB Captain: the sample is conditioned on top-10% finishes.

Standings identities are resolved within the source slate/game/team/position
salary pool. Week 3 Thursday salary identity is recovered from archived native
rows because the curated scope also contains other matchups. NFL rushing TDs join
through source-native player aliases and season/week/team/opponent; all six exact
stat rows were checked. Top-10% membership requires the entire tied rank group
to lie within `ceil(field_size * .10)`; paid membership similarly uses the whole
tie group and verified `Places_Paid`. Counts reconciled by player and contest.

The answer is descriptive: **a rushing touchdown was not required for these
observed paid QB-captain finishes**. It does not establish a QB-Captain advantage
over other positions or justify changing the live selector. Reproduce with
`PYTHONPATH=. .venv/bin/python scripts/audit_qb_captain_paid_rushing.py`;
details are in `artifacts/qb_captain_paid_rushing/report.json`.

```sh
PYTHONPATH=. .venv/bin/python scripts/audit_weekly_validation.py \
  --output-dir artifacts/weekly_validation_2026_w1_w4/new-audit
```

The output directory must be new. A repeatable-read, read-only transaction loads
projection/run records, compact saved candidate pools, account-history evidence,
contest histograms and actuals. No service restart or migration is required.

The final report is `artifacts/weekly_validation_2026_w1_w4/final/report.json`
with a full Markdown matrix beside it. It includes player-level comparisons,
position and forecast ≥10 cohorts, per-run selection and pool diagnostics,
input/choice hashes, contest evidence hashes, missing IDs and exclusion reasons.
Earlier `initial` and `validated` passes are superseded by `final`: the first
omitted Captain IDs from the reader, and the second lacked legacy game aliases.
Neither should be used for decisions.

**29 targeted tests passed**, covering historical replay/paid-cutoff behavior,
missing labels, Captain identity and multiplier handling, whole-slate timestamp
checks, deterministic time-based primary selection and unambiguous game aliases.
README/release notes document the audit; no configuration or production policy
changed. The report is available as files, not a new in-app dashboard.
