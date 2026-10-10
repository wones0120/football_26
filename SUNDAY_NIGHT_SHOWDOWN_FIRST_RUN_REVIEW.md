# Sunday Night Showdown first-run review

Review date: October 4, 2026 (America/New_York). Scope: immutable application run
`686307e6-77ca-461e-aa22-9da69e10211d`, strategy `showdown_gpp_portfolio_v3`.
Original report: `/Users/wones/Downloads/optimizer-report-2026-w4-sunday_night-686307e6.html`.

Current UI update: Showdown portfolio v3 **Run Optimizer** now builds and verifies
preparation automatically before queuing the solve. Manual rebuilding remains available;
it is no longer required before the button. See the final section for this later change.
The earlier review and its dated evidence remain accepted.

## Outcome and evidence boundary

Confirmed input/UI defects were corrected; strategy tuning and Classic work remain parked.
No user slate solve, projection refresh, source capture, replacement, or entry submission was
performed. The original saved response compares exactly equal before/after the local service
reload; the original HTML checksum is unchanged. Tests use synthetic inputs in isolated
SQLite fixtures. A corrected **rendering of existing saved records**, not a new portfolio,
is in `artifacts/sunday_night_first_run_review/reviewed-saved-report-686307e6.html`.

Evidence copies, hashes, test output, native salary checks, captain-family summaries and
saved-constraint checks are in `artifacts/sunday_night_first_run_review/`.
The original readiness remains null/unevaluated. Current preparation/readiness evidence
is dated separately and does not prove today's player clearance.

## 1. Coker: confirmed source B, not an explicit independent override

The persisted queue request and optimizer constraints both contain:

```json
{"availability_overrides":[],"exclude_questionable":true,
 "exclusions_assumed_out":true,"exclude_players":[],"exclude_player_ids":[]}
```

The consumed feature generation's `source_versions_json.availability_scenario` contains
`assume_questionable_out=true` and a generated canonical-ID Coker assume-out record.
It records official status Q, model availability 0, and opportunity redistribution.
There are no sourced pregame context run IDs in that projection's model metadata.
The UI Run Optimizer and weekly-run handlers supplied
`assume_questionable_out: excludeQuestionable`. Thus the saved trace confirms **B**:
the questionable-exclusion preference triggered the assume-out scenario. It does not
support A or C. Historical DOM state and a separate intent statement were not retained;
we cannot infer that the user separately intended an availability assumption from a checked
exclusion. Existing explicit availability choices remain supported and are not erased.

Coker's retained before-scenario mean is `14.53634211980695`, final mean/P90 0/0.
CAR target allocation retained removed and redistributed share `0.1959202662748712`,
team target-volume proxy 36, and no explicit target-share context. These are allocation
records, **not a causal estimate of Coker's net effect on every player's projection**.
The before/after fields on receivers include the model's opportunity anchoring step;
they are not a controlled Coker-in/Coker-out comparison. No such new comparison was run.

For Showdown, name/ID exclusions and the per-player exclusion checkbox now remain
selection preferences. They generate no availability overrides and no Q assume-out flag.
An independently selected Assume Out still changes the football scenario before the
projection build; labels now distinguish this from Exclude from lineups. Classic wiring
and existing explicit/sourced API scenario inputs retain their behavior.

### Consumed projection lineage

- Projection: `938f1ad1-ae78-472c-b3f4-8e60b6abd156`, 44 rows.
- Model: `0af5ff58-24d2-4068-bb3c-c1fdb6374026`,
  `gradient_boosting_challenger_v4_2_market_corrected`, version `v4.2-market-corrected`.
- Immutable target feature run: `42d026b2-2a28-45b9-8f4a-35d73865d156`.
- Cutoff: October 4, 2026, 2:02:55.855663 PM Eastern (`18:02:55.855663Z`).
- Training rows 9,846; seed 42; saved training dataset SHA256
  `c365f31b66dc7a53a76a2e0061e1d508303ded615ea0df06e6560b93c8e3f914`.
- Serialized model artifact reference and checksum are retained in model metadata.
  Feature vectors below come from `target.feature_player_game`, not a newly built matrix.

The point estimate is 80% gradient boosting and 20% history anchor;
anchor = 60% prior-three mean + 40% prior-eight mean when history >=3 games.
QB opportunity-point adjustment weight is zero here, model availability is 1, and
explicit market-point reconciliation adjustment is 0 for both. Market levels are still
inputs to the fitted model; a zero reconciliation delta does not mean market is ignored.

| QB | Prior-three mean | Prior-eight mean | History anchor | Saved final mean | Marginal P90 | Calibration |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Bryce Young | 24.72 | 19.5725 | 22.661 | 26.21520063746307 | 37.026853479052356 | QB/POCKET, 559 samples |
| Jared Goff | 22.86 | 21.505 | 22.318 | 19.810318665521713 | 30.621971507111 | QB/POCKET, 559 samples |

Young's defense-position allowed means are 33.3533333333 / 23.1475 (3/8 games),
50 history games, prior snap share 0.9466666667, prior carries 1, salary 9800,
CAR implied 23.5, spread +3.5, game total 50.5. Goff's corresponding values are
7.5666666667 / 13.7975, 164 games, snap share 1, carries 3, salary 10000,
DET implied 27, spread -3.5, total 50.5. The historical archetype diagnostic calls
Goff Mobile, while the projection residual calibration uses POCKET; these are separate
classifications. The QB archetype shadow remains unpromoted.

Algebraically recovering the raw-model term from the saved blend gives Young
27.103750796828837 and Goff 19.18339833190214. These are **derived from saved values**,
not newly scored predictions or retained per-tree attributions. Tree/SHAP feature
contributions and current-week pass-attempt, rushing-yard/TD forecasts are unavailable
in these saved player records. The complete fitted feature list and retained vectors
are in the evidence JSON; no coefficient-based explanation is invented.

CAR pass catchers use the retained prior-training isotonic opportunity curve with
55% opportunity-anchor weight for these veteran rows. Availability is 1, and market
reconciliation delta 0. The following before/anchor/after values are actual retained
model components, not the size of the Coker intervention.

| Player | Prior-three / prior-eight DK | Snap share | Allocated target proxy | Before opportunity anchor | Opportunity point anchor | Final FLEX mean | Marginal P90 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Tetairoa McMillan | 11.100000 / 10.525000 | 0.856667 | 9.122547 | 10.626563439 | 14.585339634 | 12.803890346 | 25.510598415 |
| Darren Waller | 11.066667 / 9.525000 | 0.433333 | 4.692998 | 7.851367347 | 8.414041521 | 8.160838143 | 14.028563012 |
| Tommy Tremble | 4.666667 / 4.812500 | 0.533333 | 4.169691 | 3.150620592 | 7.348613861 | 5.459516890 | 10.102751325 |
| Ja'Tavion Sanders | 3.800000 / 4.225000 | 0.373333 | 2.250618 | 2.572649709 | 3.353408048 | 3.002066795 | 8.869791664 |
| Mitchell Evans | 3.600000 / 2.400000 | 0.416667 | 2.209385 | 2.316219006 | 3.311210208 | 2.863464167 | 8.731189036 |
| John Metchie III | 4.966667 / 5.425000 | 0.460000 | 4.115913 | 5.017065260 | 6.680881055 | 5.932163947 | 11.115817531 |
| David Moore | 0.900000 / 3.637500 | 0.346667 | 1.221449 | 1.854165040 | 2.190432865 | 2.039112343 | 7.465123166 |

Expected current snaps/routes, target-share evidence, goal-line/red-zone evidence and
sourced current workload remain unavailable. Allocated targets are lagged team-volume
proxies, not independently forecast complete pass volume. Optimizer context bonuses
and CPT prior multipliers change selector scores, not these means.

### Captain scaling: no defect found

Native salary pairs were joined by canonical player ID and roster position.
All 30 selected slot records match the actual native salary row and satisfy salary,
mean and P90 = FLEX base × 1.5 for CPT, ×1 for FLEX, with unrounded values and
1e-12 relative tolerance. Examples: Young 9800→14700 and
26.21520063746307→39.322800956194605; Goff 10000→15000 and
19.810318665521713→29.71547799828257; St. Brown 11000→16500 and
17.982959024979134→26.9744385374687. The solver uses the FLEX pool and one 1.5
coefficient; result serialization applies the same multiplier to the base fields,
not to an already-scaled projection. The positional prior is an objective multiplier,
not another fantasy-point multiplier. Display rounding is not evidence of a defect.

## 2. Separate Captain credibility policy

`SHOWDOWN_CAPTAIN_CREDIBILITY_GATE.md` (October 1, OPT-CCG-001) explicitly says:
“no gate has been validated, selected, implemented, or promoted to production.”
`docs/TODO.md` retains it as Research. The October 4 parked-work handoff reiterates
credible-CPT intent but supplies no approved rule. No proven propagation defect of an
approved **separate CPT credibility gate** was found. It is absent in generation and
final selection; a new cutoff, salary floor, positional ban or blacklist was not added.

Active controls are the shared role/opportunity **player-pool** gate, canonical starter-QB
filter, user CPT restrictions (FLEX-only/locked CPT), hard correlations, legal roster rules,
per-candidate quality screen, and portfolio exposure/uniqueness. The low-opportunity skill
gate is `showdown_low_opportunity_skill_gate_v2`: without a current opportunity signal,
legacy salary<=1000 AND mean<3 AND P90<10, or fallback salary<=2000 AND mean<2 AND P90<8.
This is shared eligibility, not a distinct CPT scoring-credibility decision.
Sanders' mean `3.002066795484674`, P90 `8.869791664396239`, salary 200 survives its
strict thresholds; unavailable current role evidence does not become zero opportunity.

Sanders #69 is an actual production candidate passing the common quality screen.
It was selectable under applicable constraints, not diagnostic-only, and lost on selector
cost. Its CPT mean is about 4.5031, while the strong five-FLEX group supports a lineup
mean 101.9967. That lineup quality does **not** establish individual CPT credibility.
Acceptable FLEX value remains separate. The existing supported UI control is
**Exclude from Captain (FLEX still allowed; comma-separated names)**, applying to every
generated lineup. The user may choose it; this review did not enter any player into it.

## 3. The unchanged 95% screen and corrected captain families

References are independent maxima in the retained discovery candidate set, after exact
roster baseline rescoring, including the saved availability scenario above:

- Mean `105.13866698387272`, baseline rank #54 (Young CPT).
- Summed marginal P90 `167.6815721235587`, #43 baseline and #44 CAR-condition
  provenance of the same role-aware roster (Young CPT).
- Required mean `99.88173363467908`; required summed marginal P90
  `159.29749351738076`; tolerance 1e-8.

Both floors apply to **each candidate**, before the portfolio chooses entries. They are
not averages over the portfolio, a win probability, or simulated joint lineup P90.
The selector then maximizes filled count and selector within existing exposure and
roster-uniqueness constraints. Scenario diversity is off; no scenario quota applies.

145 scenario/roster records = 101 baseline + 22 CAR decisive + 22 DET decisive.
There are 119 unique canonical role-aware rosters, with 26 repeated scenario provenance
records. 21 records pass, representing 16 role-aware rosters (15 baseline / 1 CAR / 5 DET).
Selected ranks: #4, #45, #50, #51, #54. St. Brown CPT appears once, Young CPT three times,
Goff CPT once. Both starting QBs appear in every passing candidate, not only the five
selected entries. Production requires a starting QB, not both QBs; high saved means,
ceilings, salary construction and stack terms yield this frontier. Missing ownership
was uniformly disabled, so ownership/chalk is not an explanation of QB inclusion.

Higher-selector WR rows fail raw-quality checks despite their WR positional prior and
correlation rewards: St. Brown #1 mean 97.5966891411 (short 2.2850444936),
Jameson #11 mean 98.5546851554 (short 1.3270484792), McMillan #18 mean
93.1423903634 (short 6.7393432713). St. Brown nevertheless has eligible #4;
Jameson and McMillan have no passing retained family candidate.

“Best” below means highest baseline selector among **retained** records, not a new or
exhaustive oracle. All rows already passed generation legality/user CPT controls;
“passing” adds the two 95% floors. No separate credibility gate exists. Family selection
and selection of its best eligible row are distinct: Young's family is selected, but #43
is not. Explanations now inspect all family records instead of only the best unscreened row.

| Captain | Best before screen: rank; mean / summed P90 | Best passing: rank; mean / summed P90 | Family in portfolio? | Best passing selection/nonselection reason (or no passing reason) |
| --- | --- | --- | --- | --- |
| Amon-Ra St. Brown | #1; 97.59669 / 162.70007 | #4; 100.54990 / 159.50415 | Yes | Selected candidate |
| Jameson Williams | #11; 98.55469 / 163.62924 | None retained | No | No family candidate passed the joint screen. Joint quality screen: mean short 1.33; P90 short 0.00 |
| Tetairoa McMillan | #18; 93.14239 / 162.06013 | None retained | No | No family candidate passed the joint screen. Joint quality screen: mean short 6.74; P90 short 0.00 |
| Bryce Young | #43; 103.08299 / 167.68157 | #43; 103.08299 / 167.68157 | Yes | Captain exposure; player exposure Ja'Tavion Sanders; player exposure Sam LaPorta |
| Jared Goff | #51; 101.53993 / 166.03497 | #51; 101.53993 / 166.03497 | Yes | Selected candidate |
| John Metchie III | #61; 97.53095 / 158.52792 | None retained | No | No family candidate passed the joint screen. Joint quality screen: mean short 2.35; P90 short 0.77 |
| Jahmyr Gibbs | #67; 98.90555 / 162.86151 | #68; 102.14050 / 162.72483 | No | Replacing selected rank #51 would lose 6.84 selector points |
| Ja'Tavion Sanders | #69; 101.99672 / 166.01452 | #69; 101.99672 / 166.01452 | No | Replacing selected rank #51 would lose 6.90 selector points |
| David Moore | #71; 92.13827 / 158.86513 | None retained | No | No family candidate passed the joint screen. Joint quality screen: mean short 7.74; P90 short 0.43 |
| Isaac TeSlaa | #78; 94.96086 / 156.06036 | None retained | No | No family candidate passed the joint screen. Joint quality screen: mean short 4.92; P90 short 3.24 |
| Chuba Hubbard | #80; 97.08256 / 161.89286 | None retained | No | No family candidate passed the joint screen. Joint quality screen: mean short 2.80; P90 short 0.00 |
| Brycen Tremayne | #86; 94.36433 / 156.14440 | None retained | No | No family candidate passed the joint screen. Joint quality screen: mean short 5.52; P90 short 3.15 |
| Sam LaPorta | #94; 100.70881 / 165.25315 | #94; 100.70881 / 165.25315 | No | Replacing selected rank #51 would lose 10.83 selector points |
| Sione Vaki | #99; 93.22290 / 158.72925 | None retained | No | No family candidate passed the joint screen. Joint quality screen: mean short 6.66; P90 short 0.57 |
| Tommy Tremble | #102; 98.93123 / 160.69273 | None retained | No | No family candidate passed the joint screen. Joint quality screen: mean short 0.95; P90 short 0.00 |
| AJ Dillon | #103; 93.13840 / 158.22518 | None retained | No | No family candidate passed the joint screen. Joint quality screen: mean short 6.74; P90 short 1.07 |
| Darren Waller | #109; 98.80735 / 160.93296 | None retained | No | No family candidate passed the joint screen. Joint quality screen: mean short 1.07; P90 short 0.00 |
| Mitchell Evans | #112; 91.80221 / 158.77207 | None retained | No | No family candidate passed the joint screen. Joint quality screen: mean short 8.08; P90 short 0.53 |
| Ryan Fitzgerald | #134; 98.22864 / 159.91606 | None retained | No | No family candidate passed the joint screen. Joint quality screen: mean short 1.65; P90 short 0.00 |
| Jake Bates | #139; 95.07864 / 156.76606 | None retained | No | No family candidate passed the joint screen. Joint quality screen: mean short 4.80; P90 short 2.53 |

Gibbs #67 fails mean, but #68 **passes**, mean `102.14050058828055`, summed marginal
P90 `162.7248273030809`. Saved constraints are: five entries; CPT max .6→3;
core .8→4; starting QB 1→5; cheap punt salary<=1000 .4→2; no named locks,
no player exclusions except Q, no FLEX-only CPT restrictions, avoid offense against
opposing DST, team maximum five, exact role-aware roster uniqueness, scenario diversity off.
No Classic overlap/game/team quotas are imported.

Read-only counting of saved players confirms #68 can replace #51 under those constraints
and loses `6.841746874310644` selector points. Replacing #4/#50/#54 exceeds Sanders'
cap; replacing #45 exceeds LaPorta's. #68's saved player list is Gibbs CPT, LaPorta,
Sanders, Young, Fitzgerald and Goff FLEX. This is a verified feasibility explanation
of an existing record, **not an applied replacement or a newly solved portfolio**.
Sanders #69 similarly can replace #51 and loses `6.899975885318952`; other swaps
hit saved exposure limits. The detailed counted blockers are retained in
`saved_constraint_checks.json`.

## 4. Conditioning is effective discovery; the display used the wrong scoring frame

Trace: market total/implied values → `define_game_scenarios` →
`condition_player_pool` → exact conditioned solves →
`baseline_rescore_discovery` of the same canonical roster/CPT → common-baseline selector
and screen → saved candidate metrics → UI/HTML.

The existing method `market_margin_role_conditioning_v1` uses bounded scoring plus
role-volume components, preserving each player's marginal spread ratio. These are
sensitivity/discovery assumptions, not conditional probabilities from a calibrated
joint simulation. CAR baseline implied 23.5 and DET 27; CAR 14+ condition uses
32.25/18.25, DET 14+ uses CAR 18.25/DET 32.25. No new multipliers were invented.

Identical baseline→conditioned columns were a **persistence/display field-selection
problem**, not proof the condition was ineffective: `mean`/`p90` in ranked records
were intentionally baseline comparison sums. Player `conditioned_projection`/
`conditioned_p90` survived rescoring, and the archived candidate player adjustments
also retained conditional mean/P90, even though candidate-level conditional totals
were omitted. New metrics retain those totals; rendering older runs reconstructs them
only when all six saved player adjustments exist, otherwise it says Unavailable.

Saved examples (already CPT-adjusted, no rescaling):

| Record | Baseline mean → discovery-conditioned mean | Baseline summed marginal P90 → discovery-conditioned sum |
| --- | ---: | ---: |
| #6 CAR decisive | 96.54666506794827 → 98.64365194454528 | 159.87326391613263 → 163.134901472952 |
| #2 DET decisive | 97.59668914105542 → 102.17967842305914 | 162.70007070313488 → 170.4996192014225 |

In #2, Young changes by only -0.0139442557 because losing-team volume +.10 almost
cancels scoring -.1005319149; no requirement exists that every player move visibly.
Baseline stays unchanged, zero-availability distributions stay zero, and a favorite
already beyond the decisive margin may have unchanged conditional team scoring.
Fixtures verify baseline/zero cases, effective decisive changes and exact-roster rescoring.
No decisive-condition roster is selected with diversity off; baseline comparison makes
that legitimate. Max mean, max P90, and max selector in summaries can belong to different
rosters; both app and HTML now label them as independent maxima, with captain/team/salary
attached to the maximum-selector roster.

## 5. Actual Showdown preparation/readiness handoff

### Frozen run inputs

- Native salary CSV `/Users/wones/NFL/DKSalaries_2026_4_SUNDAY_NIGHT.csv`, import
  `b3583807-1822-4e33-8479-561ce1173c10`, 100 rows: 50 FLEX and 50 CPT pairs.
  Original and current file SHA256 matches
  `845bd366b643a7586843016e7228585802b32dc05d2979a9ef66486c15c701b2`.
- Native game text `DET@CAR 10/04/2026 08:20PM ET`; salary-derived lock is October 4
  at 8:20 PM Eastern. This confirms the imported file's game/lock, not a verified
  current native contest assignment or canonical schedule match.
- Native draft-group ID was **not retained/confirmed** in a source snapshot for this
  import. Do not derive it from player IDs. Reimport via salary-evidence action after
  operator verification of the native draft group if using the preparation handoff.
- Exact consumed market snapshot `f74c860d-0eb6-5ea5-9ff3-4d8dc5b5804f` is in
  `target.market_snapshot`, game `2026_04_DET_CAR`, source `nflverse_schedules`,
  observed `2026-09-30T01:22:11.632067Z` (Sept 29, 9:22:11 PM Eastern), source
  snapshot `275c194b-c913-5416-9194-53778bc2435f`. Total 50.5, home CAR +3.5,
  implied CAR23.5/DET27. Its observation is ~112.68h old at projection cutoff.
  The saved summary's `public.raw_nfl_schedule` source label is inaccurate for this
  normalized snapshot; new summaries identify cutoff-safe market observations and
  defer to retained source/ID records. The original record is not rewritten.
- Frozen availability scenario and missing current role evidence are described above.
  Neither a native salary designation nor an inferred starter proves final clearance.
- Frozen projection lineage is explicit above. Role CPT/FLEX ownership is missing:
  every selected slot has unavailable selector ownership. The requested ownership run
  exists, but does not establish complete approved role ownership. The selector term
  stays disabled uniformly. No Classic substitution or missing-as-zero was introduced.

### Current application evidence, separate from the saved run

Read-only checks around 2:16 PM Eastern on October 4 showed:

| Check | Observed status | User action / limitation |
| --- | --- | --- |
| Preparation game/schedule match | BLOCKER: salary games do not uniquely match canonical schedule with kickoff | Review native game/year/week/slate, use the corrected canonical schedule load in the identity addendum below; resolve any disagreement rather than bypass it |
| Verified prepared feature/projection build | Missing; no preparation build | After source/identity/lock blockers resolve, use Rebuild slate features and projections |
| Native draft group | Unevaluated/unretained | Verify it in DraftKings, enter ID, Import DraftKings salary evidence |
| Basic Showdown GPP gate | WARN, 96; no blocking basic check | Basic coverage is not final entry readiness |
| Injury CSV snapshot | Missing: 0 identity-linked rows | Import supported CSV evidence; this alone does not feed canonical availability scenario or establish clearance |
| Current sourced role/availability/practice/workload | Missing in consumed saved players | Load sourced pregame evidence JSON with canonical IDs and original observation times, review starting QBs, rebuild |
| Consumed market age | Stale saved observation | Capture nflverse markets and rebuild as a user action; upstream quote publication time remains unknown |
| Projection | Latest completed points to frozen 938f1ad1…; not a verified preparation | Rebuild through preparation; do not assume list reload refreshes inputs |
| Basic ownership count | 98 rows reported PASS | This generic row-count check does not certify CPT/FLEX ownership; missing role ownership remains missing and disabled |
| Final availability, current quote publication, weather clearance, salary publication freshness, contest/submission verification | Not evaluated | Independently verify before entry; not changed to PASS by a build or service reload |

Preparation cannot currently capture markets/weather or rebuild because canonical
schedule/lock matching fails. The basic Showdown gate's positive player/game coverage
uses native salary text and has weaker checks; its warning is not inconsistent with
that stricter preparation blocker. Current schedule inspection found no CAR/DET
2026-week4 rows in `public.raw_nfl_schedule`. No feed was fetched during this review.

Normal Run Optimizer previously rebuilt features/projections directly and bypassed
preparation for Showdown. It now reuses the existing preparation component for v3,
pins its exact projection and preparation IDs, and validates unchanged source/scenario
lineage at API, worker/service start, and after execution. Q exclusions no longer
invalidate a baseline preparation; changing an explicit availability assumption does.
The preparation scenario check retains contest format through both service checkpoints.
This imports preparation/identity/lock checks, **no Classic lineup construction rules**.
The separate weekly-run action still rebuilds its own inputs; its Showdown exclusion
wiring is corrected too, but it is not represented as a verified preparation consumer.

New v3 results save a reporting-only consumed-input readiness assessment, exposed in
app/HTML with MISSING, stale WARNING, and UNEVALUATED separated. It preserves
`entry_ready=false` for unavailable final clearance. Old saved runs stay unevaluated.
The existing saved-input validation POST is Classic-only; it was not called on this run.

Timestamp limitation: the optimizer API's original `created_at` carries
`2026-10-04T18:04:13.324768-04:00`, whereas worker/runtime logs and projection creation
place execution around 2:04 PM Eastern. The service historically creates a naive UTC
optimizer timestamp. This review does not rewrite historical timestamps or infer current
clearance from them; market ages above use the explicit projection cutoff. New consumed
readiness records have an explicit UTC assessment timestamp.

## 6. Fixes, runtime, validation and exact next actions

Narrow changes: Showdown-only exclusion/scenario separation and labels; v3 prepared
input consumption and format propagation; family-wide eligible-row explanations;
retained conditional totals and correctly framed app/HTML displays; independent maxima
labels; consumed-input readiness/provenance; accurate market source wording; import
fingerprints for touched Showdown modules. Existing Classic changes were preserved.
No scoring weights, CPT priors, exposure defaults, quality fraction, ownership policy,
QB shadow promotion, family forcing, or player blacklist changed.

Validation: **78 backend tests passed, 18 UI/report tests passed, UI build/type check passed,
and the isolated real UI/API/preparation-worker browser fixture passed**. Evidence is in
`backend-tests.txt`, `ui-tests.txt`, `ui-build.txt`, `ui-e2e.txt` and `ui_fixture/`. Focused fixtures cover exclusions/explicit assumptions, unchanged
model assessment, baseline/decisive conditioning and legitimate zero changes,
exact canonical roster rescoring, family alternatives, missingness, source/scenario
hash rejection, normal v3 service start/end validation, and real UI→API→durable
preparation worker→pinned optimizer request. The browser fixture stops before the
optimizer executes. A separate synthetic six-player v3 service fixture exercises the
solver and selection; no user inputs enter it. Desktop/mobile screenshots were inspected.
The build has the existing bundle-size warning; no build/type error remains.

The local API and worker were read before edits: API PID40645, worker PID40640,
both loaded October 4 at 1:58 PM Eastern. The queue was confirmed empty before a
local reload; no source capture or slate job was queued. Post-change runtime evidence
is in `runtime-after.json` and `worker-runtime-after.json`: API/worker import hashes
match one another and the relevant disk modules. Final API PID 52092 loaded
`2026-10-04T18:41:10.983386+00:00`; worker PID 52089 loaded `2026-10-04T18:41:10.886800+00:00`. Saved run/report preservation was
checked again after reload. Browser development assets use the updated source; production
assets were rebuilt. No live-input end-to-end run was performed.

Next run is exclusively the user's app action:

1. Refresh the app view, select **2026 / Week 4 / SUNDAY_NIGHT**, **Format: Showdown**,
   **Objective: GPP**, the existing `showdown_gpp_portfolio_v3` strategy. Open the saved
   run by its ID for reference; leave its report immutable.
2. In **Operations → Prepare slate inputs**, first review game identity/lock. Resolve
   the canonical schedule blocker with **Load Historical Game Data** (start/end season
   **2026**) under **Bulk and historical ingestion**, then **Reload preparation status**.
   **Load Raw Season** writes legacy tables that preparation does not read. If source schedule and native game disagree, correct
   the selected native file/scope; do not treat an unsupported pairing as cleared.
3. Verify the actual native DraftKings draft group, enter its ID and the correct salary
   file path, then **Import DraftKings salary evidence**. Inspect counts, unresolved
   identities and source checksums. The original immutable import is not overwritten.
4. Use **Import injury CSV evidence**, **Review starting-QB evidence**, and **Load sourced
   pregame evidence** where supported. Keep original observation times and canonical
   identities; distinguish designation, practice, workload and final status.
5. **Capture nflverse markets** and review observation age/unknown quote-publication
   freshness. Use **Capture current weather** if needed; weather is evidence, not an
   input secretly added to projections.
6. Review **Player decisions**: **Exclude questionable (Q) players** and **Exclude from
   lineups** are preferences. Only deliberately selected **Availability → Assume Out**
   changes the scenario. Do not automatically remove an intentional explicit assumption.
   Use **Exclude from Captain (FLEX still allowed; comma-separated names)** only if the
   user wants that supported CPT restriction. No validated separate credibility gate is
   available, and this review provides no mandatory player exclusions.
7. Click **Rebuild slate features and projections**. Wait for completed preparation,
   exact source→feature→projection consumption and **Verified current prepared projection**.
   Changing an availability scenario afterward requires another user-invoked rebuild.
   **Reload projection list** only reloads stored choices.
8. Preserve/review the user's entry count, exposure limits, no-offense-vs-DST choice,
   CPT controls and scenario-diversity-off choice. Leave **Optimizer projection** at
   **Latest completed (automatic)**, then initiate **Run Optimizer** yourself. This v3
   action now uses the verified preparation ID, not an untracked input refresh.
9. Review consumed-input readiness, eligible captain families, baseline selector and
   separate discovery assumptions. Resolve remaining final-clearance/contest blockers
   independently before entry. Downloads/submission remain user actions.

No additional research project was created. Remaining limitations are explicit evidence
and policy gaps, not hidden eligibility fixes: unapproved CPT credibility research,
unresolved current canonical schedule/native draft group, absent final clearance and
unknown upstream quote-publication freshness.


## Accepted findings — slate identity follow-up (October 4, 2026)

The completed findings above are accepted. Classic implementation and further Showdown
strategy research remain parked. This follow-up only diagnoses the preparation blocker;
no application source import/capture, feature/projection refresh, optimizer execution,
replacement, or submission was performed. Original run `686307e6-77ca-461e-aa22-9da69e10211d`
and its saved HTML are preserved. Evidence: `artifacts/sunday_night_slate_identity/`.

### Confirmed identity and native scope

- **2026 / Week 4 / SUNDAY_NIGHT / Showdown: DET away at CAR**, Bank of America
  Stadium, Sunday October 4, **8:20 p.m. EDT** (`2026-10-05T00:20:00Z`). The
  [Panthers game center](https://www.panthers.com/gameday/2026/week4) and
  [Lions schedule](https://www.detroitlions.com/schedule/) independently agree.
- Read-only public embedded metadata from the user-supplied
  [contest 196285050](https://www.draftkings.com/draft/contest/196285050) confirms
  **draft group 154098**, native game **6176180**, `DET @ CAR`, and the same UTC
  kickoff. Contest name: **NFL Showdown $200K Play-Action [20 Entry Max] (DET @ CAR)**,
  state Upcoming at the 19:14:31Z observation. The contest maximum is not a request
  to change the user's saved five entries or any exposures/preferences.
- These web/native observations are external verification, **not new ingested
  application evidence**. The salary import remains `b3583807…`, season 2026/week 4/
  SUNDAY_NIGHT, 100 rows (50 CPT / 50 FLEX), only DET/CAR. The existing artifact
  checksum still matches `845bd366…`; every row has the expected game/date/time.
  Current unresolved salary identities: zero (the ingest originally recorded two).
  No linked source snapshot or draft-group/contest field exists for that original
  import. Native contest metadata confirms the intended group but cannot retroactively
  establish which group produced the old file. Verify/download salary evidence from
  this contest/group before entering **154098** for the next app import. Do not infer
  identity from player IDs or the filename.

### Proven blocker: A — incomplete local canonical schedule evidence

Read-only database checks at 19:14Z show only **12** nflreadpy Week 4 rows in
`public.raw_nfl_schedule`, all from ingest `ae9a1757-6f4f-5605-abcd-494da4784ede`.
None includes DET or CAR. `target.dim_game` also has no `2026_04_DET_CAR` row.

The immutable full-season September 22 snapshot `6157e829…` (ingest `d8934934…`)
contains all 16 Week 4 games, including `2026_04_DET_CAR`, away DET/home CAR,
`gameday=2026-10-04`, `gametime=20:20`. Its SHA256 matches the saved ingest checksum.
Both October 2 Sunday Main snapshots contain only 12 Week 4 games and omit this target;
the latest is `d0058eb0…`, SHA256 `540a7cac…`, also verified against ingest lineage.
`scripts/prepare_sunday_readiness.py` filters schedules to Sunday Main salary pairs,
then calls the schedule ingest with `weeks=[4]`. The ingest clears that source's entire
requested week before inserting the slice. This accounts for the missing night game;
the source's complete retained snapshot did contain it.

Preparation selects season/week and source `nflreadpy`, deduplicates schedule game IDs,
then requires one canonical team-pair match with a parseable kickoff. For this target it
fails because there is no row, before kickoff parsing. DET/CAR aliases are consistent;
Eastern conversion correctly yields October 5 UTC, not October 4 UTC. The matcher uses
salary team/opponent pairs, not the native game text as an independent kickoff comparison;
the file/native/source agreement here was verified separately. No target-specific parsing,
timezone or alias defect is demonstrated; no incompatible data was relabeled or inserted.

**Correction to the earlier UI instruction:** **Load Raw Season** populates legacy
`raw_schedules` / `curated_schedules`; preparation reads `public.raw_nfl_schedule`.
Those legacy tables are currently absent. The existing canonical UI action is
**Operations → Bulk and historical ingestion → Start season 2026 / End season 2026 →
Load Historical Game Data**. It calls the traced nflreadpy schedule capture/ingest
(and also loads weekly stats). The user performs this action. Then click **Reload
preparation status** for 2026 / Week 4 / SUNDAY_NIGHT. Expected match:
`2026_04_DET_CAR`, DET away/CAR home, `2026-10-05T00:20:00Z`.
Verify this returned identity/lock; stop if the new source disagrees or omits it.

No runtime code change/restart was needed. An isolated in-memory fixture using the
retained source row reproduced missing-schedule rejection, verified the expected unique
match with both abbreviations and full-name aliases, and confirmed rejection at lock.
No live source row was loaded by that check. The focused preparation/handoff backend
suite passed **14 tests**, and UI scenario separation passed **4 tests**. Final read-only
hash checks confirm the saved optimizer record and original HTML are unchanged; salary
resolution, schedule rows and checked snapshot lineage also remain unchanged.
Broad ingest changes are outside this task;
slate-filtered snapshots must not be treated as complete week schedule evidence.

### Short app sequence after the canonical load

1. Keep **2026 / Week 4 / SUNDAY_NIGHT / Showdown / GPP / portfolio v3**. Perform
   the canonical load above and verify its returned game/lock. The app's current browser
   selection was not independently read; the saved run's scope was checked.
2. Verify the salary download in contest **196285050 / draft group 154098**, use its
   local path, enter **154098**, and click **Import DraftKings salary evidence**.
   Inspect identity resolution, native scope and checksums; the old import is not
   proof of salary-publication freshness.
3. Load supported **injury CSV evidence**, **sourced pregame evidence** with canonical
   IDs/original observation times, and **Review starting-QB evidence**. Injury CSV alone
   does not feed canonical availability. **Capture nflverse markets**; capture/review
   relevant current weather and venue/roof evidence. Weather is review evidence,
   not a projection input; quote-publication time remains unknown.
4. Review **Player decisions** before **Rebuild slate features and projections**.
   **Exclude questionable / Exclude from lineups** affect selection only. Independently
   selected **Assume Out** remains selected and must be reviewed by the user; retain
   its explicit source, and review sourced context provenance separately in preparation
   and consumed scenario evidence. An exclusion alone must not generate Coker-out.
   The old `938f1ad1…` assumed-out projection is not a verified baseline merely because
   it is the latest completed run. Wait for **Verified current prepared projection**
   and inspect exact source → feature → projection consumption. Scenario changes require
   another user-invoked rebuild.
5. Review **Exclude from Captain (FLEX still allowed)** and the saved Showdown entry
   count, captain/player/QB/punt exposures, exclusions, locks, correlations and scenario
   diversity; preserve them unless the user deliberately changes them. Then the user
   initiates **Run Optimizer**, which consumes the verified preparation. Import no Classic
   controls. A separate automatic **CPT credibility gate is NOT implemented**; the
   lineup-quality screen is not equivalent protection. No new CPT cutoffs/bans were added.

Preparation completion verifies dependency consumption, **not final player/contest
clearance**. Official final availability, salary-publication freshness, quote-publication
freshness, relevant weather clearance, role ownership and final contest/submission review
remain distinct. The native contest observation is dated; recheck it before entry.
All live preparation and optimizer execution remain user actions. The cross-format
exclusion-versus-assume-out check is recorded as parked Classic task C09.


### Later user-authorized salary evidence import — October 4, 3:35 p.m. Eastern

After the user loaded canonical schedules in Operations, preparation matched
`2026_04_DET_CAR` at `2026-10-05T00:20:00Z`. The user then explicitly authorized
verification and salary-evidence import. A fresh native download from draft group
154098 was byte-identical to the original artifact (100 rows, 50 CPT / 50 FLEX).
The app preparation job `496585ea-c376-49fc-bdb1-d151a1170cc7` completed; ingest
`e89921e9-dbbf-57af-8464-3906b66c0597` links snapshot
`b0458c5f-7f4b-5241-acec-b85606c70a56`, with native draft group 154098 recorded.
The import reopened Lawrence Keys III's two native slot identities because their
DraftKings aliases were absent. The exact pre-import canonical assignments were
restored through the app resolution endpoint and persisted as source-ID aliases.
All 100 canonical assignments and salary fields compare equal to before import;
zero salary rows remain unresolved. Original saved run/report hashes are unchanged.
No other sources were captured, no features/projections rebuilt and no optimizer run.
Preparation still has no verified build; player/contest final clearance remains
unverified. Evidence is in
`artifacts/sunday_night_slate_identity/authorized_salary_20261004T193212Z/`.


### Later user-requested automatic preparation from Run Optimizer

The user reported the missing-prepared-build error after resolving schedule/salary
identity and requested that the optimizer perform the necessary preparation itself.
Showdown portfolio v3 now snapshots the selected explicit availability choices, awaits
in-progress source preparation, and queues a fresh durable **rebuild** job from the normal
**Run Optimizer** button. It waits for completion, reloads preparation status, verifies
that the exact queued job is the current prepared build with complete lineage, and
continues using that projection/preparation ID. Each click builds the selected scenario;
the latest old assumed-out projection cannot substitute for a baseline. Q/name/ID lineup
exclusions remain selection-only. All saved exposures, CPT restrictions, entry count,
correlations and scenario diversity continue through the unchanged request construction.

Identity/lock/source-artifact/consumption rejection still blocks; failed preparation
surfaces its actual error and never queues an optimizer. A source change, superseding
build or lock during preparation is rejected. This build does not fetch new source
availability/markets/weather or change assumptions. Final player/contest clearance
remains unverified, and the separate automatic CPT credibility gate remains absent.
Classic's manual preparation requirement and implementation remain parked/unchanged.

Validation: **12 UI unit tests**, **14 backend preparation/handoff tests**, UI build/type
check, and the isolated real App → API → durable preparation worker → verified pinned
optimizer enqueue fixture passed. The fixture starts with no prepared build and stops
before optimizer execution; it verifies button disabling, preserved Q/lineup/CPT-only
preferences and exact IDs. Desktop/mobile optimizer status text was inspected. The UI
build retains the existing bundle-size warning. No backend code was changed or service
restart needed. No live feature/projection build or user optimizer was initiated by Codex.
The user can refresh the app and click **Run Optimizer** for the configured Showdown v3
slate; manual **Rebuild slate features and projections** is optional. Evidence and rendered
fixture screenshots: `artifacts/sunday_night_auto_preparation/`.


### Later preparation storage-access repair — October 4, 4:10 p.m. Eastern

The user's automatic rebuild `ced35105-547c-4c7b-8ab6-aa038e4f5f6a` failed before
feature generation: the launchd worker received `EPERM` reading the existing
iCloud-backed market artifact. The canonical DET/CAR match and native draft group
154098 remain correct. Codex could read the artifact and verified its recorded
checksum; a read-only launchd probe reproduced blocked original access and passed
verification using an exact local replica. This proves a process-dependent storage
access blocker; it does not identify which macOS permission mechanism denied access.

Preparation now resolves an already provisioned replica only after `EPERM`, `EACCES`
or file-provider deadlock. It binds the copy to the DB snapshot's original path and
checksum, checks bytes/size/full manifest/clocks/storage lineage, and records its use
in newly prepared build lineage. Readable corrupt or missing originals still fail.
No capture, clock backdating, database snapshot-path rewrite, or relaxed validation
occurs. Exact market snapshot `275c194b-c913-5416-9194-53778bc2435f` and salary
snapshot `b0458c5f-7f4b-5241-acec-b85606c70a56` copies were provisioned in the
existing `data/source_snapshot_replicas` store. Source-manifest hash, immutable
snapshot rows and original saved run/report hashes remain unchanged.

Validation: 40 focused source-capture/preparation/Showdown-handoff tests passed,
including access-error recovery, absent replica, corruption, timestamp alteration,
lineage mismatch, and retained rejection of corrupt/missing originals. After
confirming the operational queue idle, the established restart procedure reloaded
API and worker. No live build or optimizer was initiated by Codex. The next user
**Run Optimizer** click performs the configured preparation and solve; no second
schedule load is needed for this access error. The latest failed job remains in
history; only a successful new preparation can become current.

This repairs file access only. The market observation remains September 29; quote
publication/currentness, current availability/starter evidence, relevant weather
and final player/contest clearance still require review. Exclusions remain separate
from explicit assumptions and preferences remain unchanged. An automatic CPT
credibility gate is still **not implemented**; use **Exclude from Captain (FLEX
still allowed)** for interim review. Classic work remains parked. Storage repair
and read-only background proof: `artifacts/sunday_night_auto_preparation/storage_access_repair/`.


### Current input and preference handoff — saved run 468d9236

Read-only review of `468d9236-580d-4c6f-bcd8-431aee2c206c` and its original
`optimizer-report-2026-w4-sunday_night-468d9236.html` accepts draft group 154098,
preparation `d47a26aa-0495-4f79-a3f4-73f01e804519`, projection
`94ebab11-398f-4b61-bc5c-4edf88d45428`, and dependency-lineage PASS. That PASS
proves which records were consumed, not completeness/currentness or entry clearance.

**Coker eligibility:** requested and effective `exclude_questionable=false`;
`exclude_players=[]`, `exclude_player_ids=[]`, `flex_only_players=[]`, effective
`flex_only_player_ids=[]`, `availability_overrides=[]`, and
`exclusions_assumed_out=false`. Preparation separately saved
`assume_questionable_out=false`. His included/non-FLEX-only pool row retained
`player_status="Q"` from the exact salary import's native `Status` column
(FLEX source row 30036, native ID 44358453; CPT native ID 44358503). This is a
dated salary-file designation, not verified current Q status. The salary snapshot
was captured October 4 at 19:32:59Z; upstream salary publication time is unknown.

The eligibility gate independently checks salary status and the first nonblank
designation from projection `pregame_injury_status`, then cutoff-safe
`target.snapshot_injury_status.injury_status`. Both injury/context fields were null
here. Confirmed unavailability remains a hard exclusion; Q is excluded only when
the Q preference is enabled. The saved audit records `included=true`, no exclusion
reason, and warnings `current_week_context_missing` and
`injury_information_not_incorporated`. His `availability_override="default"` and
model availability 1.0 are model defaults, **not active/healthy/cleared evidence**.
No propagation or identity/status-join defect is proven. The new request allowed
him; canonical availability evidence was missing. The previous accepted run's
checkbox-to-assume-out coupling explains its different scenario and remains removed.

The user confirmed that the unchecked Q preference was unintended and explicitly
requested a default change. Showdown now starts with **Exclude questionable (Q)
players** checked. A manual uncheck is retained across format switching in that
session. The default change does not alter saved requests, individual exclusions,
explicit assumptions, or projections; Classic's existing default stays unchanged.
No intent question remains pending.

**Existing versus missing evidence:** this saved preparation has
`availability_row_ids=[]`, `injury_csv_consumed=false`, no Sunday Night canonical
pregame context or supported injury import, and no current weather forecast.
Existing full nflreadpy injury snapshots filed under Sunday Main contain Coker
by canonical native alias `00-0039491`: October 1 DNP, October 2 LIMITED practice;
both have blank `report_status`. They are dated practice facts, not an official
game designation or final clearance, and were not consumed by Sunday Night.
Their snapshot observation clocks are capture clocks; upstream practice-report
publication time is not retained. Do not carry a historical designation forward.

Young/Goff starter IDs were consumed, but their existing starter evidence is
`inferred`, source `provisional_nflverse_depth_chart_qb1`, original observation
October 4 13:09:16Z, snapshot capture 18:00:20Z, stored receipt 19:43:34Z.
The stored `active` label is provisional starter selection, not official clearance.

Consumed market `f74c860d-0eb6-5ea5-9ff3-4d8dc5b5804f` is total 50.5 / CAR +3.5,
observed and captured September 30 01:22:11Z (September 29 9:22 p.m. Eastern),
about 114.9 hours old at this run. A newer canonical schedule snapshot
`564298a2-2201-54cb-a351-9fe5921b40c6`, observed/captured October 4 19:25:19Z,
contains DET/CAR total 51.5; it was loaded as schedule evidence and was not
promoted to the explicit market-snapshot input this run consumed. No newer
DET/CAR market-snapshot row exists at inspection. Other slate captures cannot
substitute. Upstream sportsbook quote publication freshness remains unknown.

**Next app actions, selected scope 2026 / Week 4 / SUNDAY NIGHT / Showdown:**

1. Refresh the app and verify the Q checkbox is checked. Review individual
   **Exclude from lineups** choices and **Exclude from Captain (FLEX still
   allowed; comma-separated names)**. No Coker exclusion was entered on the
   user's behalf. Requested controls remain inspectable in
   `GET /api/jobs/bdfc26b1-b248-455b-865c-48c96916451c`; effective controls and
   Coker's included/FLEX-only/reason audit are persisted in optimizer constraints
   and the saved results/player-pool API. Targeted comparison is saved below.
2. In **Operations → Prepare slate inputs → Load sourced pregame availability
   evidence (manual JSON)**, load current, applicable evidence using canonical
   IDs, source URI, and the original observation time. Use the built-in example
   or schema below. Fill only independently supported designation/practice/
   workload fields; do not invent availability probabilities or infer clearance.
   An available supported CSV can separately go through **Injury file**, matching
   **Injury CSV source**, then **Import injury CSV evidence**. DraftKings columns:
   `ID,Name,TeamAbbrev,Position,Status,Injury Details`; FanDuel columns:
   `Id,Nickname,Team,Position,Injury Indicator,Injury Details`. Resolve native IDs
   through canonical ingest. CSV import is not the canonical pregame-context
   consumption proven by `availability_row_ids`.
3. Use **Review starting-QB evidence** / **Load Starting QBs** where confirmation
   is needed, retaining sourced versus provisional labels. Click **Capture
   nflverse markets** and **Capture current weather**; wait for completed jobs
   and inspect observations separately from captures/receipts. A weather capture
   remains evidence only, outside the current projection feature contract.
4. After changing evidence, use **Rebuild slate features and projections**, then
   **Reload preparation status** to inspect exact source → feature → projection
   consumption. Verify canonical availability row IDs and the selected market
   observation changed as intended. Alternatively the next user **Run Optimizer**
   click performs that build/verification automatically before solving. Rebuilding
   unchanged inputs will not fill missing evidence. Review saved exposures, CPT
   limits, exclusions and independent assumptions before that user-initiated run.

Manual JSON schema example — replace bracketed placeholders with verified facts;
this is a template, not a claim about Coker's current status:

```json
{
  "source": "official_team_report",
  "source_uri": "<actual report URL>",
  "observed_at": "<original observation timestamp with timezone>",
  "players": [{
    "player_id": "2fa43876-8b80-4de0-a467-82bfa150f042",
    "injury_status": "<verified game designation>",
    "evidence": {
      "practice_participation": "<FULL, LIMITED or DNP when sourced>",
      "practice_observed_at": "<original practice observation timestamp>"
    }
  }]
}
```

The UI supplies selected season/week/slate. Omit unsourced fields, including
`injury_status` when the source contains practice only. The loader assigns its
separate receipt time. For retained local snapshot evidence, keep its ID and
capture-clock basis in `evidence`; do not substitute receipt time for observation
or manufacture an upstream publication time.

The separate automatic CPT credibility gate is **not implemented**; the 95%
whole-lineup screen is separate protection. Amon-Ra candidate **#9** has **98.41
mean / 158.36 summed marginal P90**, close to the mean floor **98.49451**; this
does not prove a portfolio replacement or justify a threshold change. Historical
position percentages are not individual captain-winning probabilities. Existing
quality fraction, priors, weights, exposures, diversity and roster defaults are
unchanged; corrected baseline/discovery reporting is accepted. Classic/strategy
research remains parked.

Validation: UI build/type check, 12 UI scenario/preparation unit tests, 8 existing
synthetic Q-eligibility cases, and the isolated real UI/API/worker fixture passed.
The fixture verifies Showdown's checked default, retained explicit uncheck,
unchanged Classic default, submitted Q preference, and absence of generated
assume-out overrides; its solver is never executed. The only new behavior is the
user-authorized checkbox default and per-format session choice retention. No
backend scoring/status-join change or runtime restart is required. No sources
were privately fetched, live inputs rebuilt, portfolio generated or submitted.
Evidence completeness/final player availability, quote publication freshness,
salary publication freshness, weather clearance, ownership approval and contest
assignment remain preview-only/unevaluated. A later app preparation appeared
during inspection; it still consumes no availability rows and the same old market,
and is distinct from this saved run's accepted lineage. Evidence and preservation
hashes: `artifacts/sunday_night_input_preference_handoff/`.


### Repeated storage blocker after successful user captures — October 4, 5 p.m. Eastern

The user completed market capture `99c14bf2-d7a6-45c2-aeba-a010abe7f819`
(snapshot `a92b365b-cc17-554f-82b2-a453343e0281`, observed/captured 20:54:41Z,
total 51.5 / CAR +3.5) and FanDuel injury import
`f2cd5029-6df3-43b1-a85d-1b81faa82e81` (snapshot
`67417ed3-0077-5c7d-a811-9a6689c3b010`, observed/captured 20:59:11Z,
51 curated rows, zero unresolved). Subsequent rebuild
`613d6eee-4915-44ac-9740-1f5a31618f02` failed on source storage access. The earlier
exact-copy repair covered old evidence; live storage configuration still wrote new
captures into the on-disk iCloud Drive folder, where the background worker encountered
another access failure with a newly captured market artifact.

The local application's `.env` source/weather roots now use existing defaults
`artifacts/source_snapshots` / `artifacts/weather_forecasts` for future user captures.
Existing immutable snapshot paths and dates were not rewritten. Exact current
market/injury storage copies were provisioned and verified through the established
replica mechanism; source-manifest hash and both reviewed saved runs remain unchanged.
Background write/read probes pass for both local working folders, and read-only
verification of current source artifacts passes. These probes use temporary synthetic
files and never capture a live source or execute a preparation/optimizer job.

Retries of identical legacy captured content now handle OS permission denial as
well as file-provider deadlock through the existing checksum-verified replica path.
The same snapshot's original observation/capture time is retained. A readable corrupt
original still fails; no fallback hides a checksum mismatch or missing evidence.
Focused synthetic source-capture and preparation/handoff tests cover the retry.
API/worker reload uses the established procedure only after the queue is idle.

The next user action is **refresh the app → Run Optimizer** for the already selected
Showdown scope; automatic preparation verifies/rebuilds the changed input set. No
repeat salary/injury import or market capture is needed for this storage error.
This is still a preview workflow: the imported FanDuel designation is distinct from
canonical pregame-context consumption and final availability clearance. Upstream quote
publication time remains unknown. Weather capture failed because the required keyless
evaluation acknowledgment was not selected; that remains a visible user-controlled
source prerequisite, and weather remains outside the projection feature contract.
No provider acknowledgment, assumptions, individual exclusions, exposures, priors,
quality fraction, scoring or saved portfolios were changed by this storage repair.
Classic/strategy work stays parked. Evidence:
`artifacts/sunday_night_input_preference_handoff/storage_followup/`.

Storage wording clarification: the user confirms their files are local to their
drive. The artifacts were also readable and checksum-verifiable from Codex. References
to iCloud describe the configured **folder location** under
`/Users/wones/Library/Mobile Documents/com~apple~CloudDocs/football_26_evidence/`,
not proof that files were cloud-only, absent, or needed downloading. The confirmed
fault is a process-dependent OS access denial; its exact macOS permission mechanism
remains unproven. The repair changes where the app stores its generated snapshots
and retains exact copies for existing evidence. Original upload files under
`/Users/wones/NFL/` were not moved, and source dates/settings/saved runs were not changed.
