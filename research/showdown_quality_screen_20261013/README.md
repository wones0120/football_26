# Does the 95% screen remove football-aware upside?

Yes: it excludes pregame-supported Captain/stack structures as well as low-opportunity constructions. That does not establish reliable joint upside, and removing it did not consistently improve the fixed-size current-score portfolios. Defaults are unchanged. All outcomes were previously inspected: this is retrospective, with no genuinely blinded or held-out conclusion.

The four arms were frozen before new comparisons. Current scoring, top-four Captain eligibility, original preferences, canonical physical pool, requested-count caps and primary portfolio size stay identical. Both95 baseline exactly reproduces the prior current arm; all six historical physical portfolios/objectives also replay. `prepared.json` freezes annotations before new outcome evaluation, but known outcomes prevent real blindness.

## Fixed-size result

Entries are average / best actual. Thursday stays at its original achieved four; others stay five. All arms retain cap denominator five.

| Slate | Size | Both95 | Mean95 only | Marginal P90 95 only | Neither |
|---|---:|---:|---:|---:|---:|
| THURSDAY_NIGHT | 4 | 87.98 / 94.79 | 77.16 / 89.79 | 87.98 / 94.79 | 77.16 / 89.79 |
| SUNDAY_MORNING | 5 | 102.81 / 119.74 | 102.81 / 119.74 | 102.81 / 119.74 | 102.81 / 119.74 |
| SUNDAY_LATE_SF_SEA | 5 | 87.34 / 101.86 | 91.04 / 101.86 | 87.34 / 101.86 | 87.39 / 101.86 |
| SUNDAY_NIGHT | 5 | 91.10 / 104.80 | 91.10 / 104.80 | 91.10 / 104.80 | 91.10 / 104.80 |
| MONDAY_NIGHT | 5 | 123.41 / 131.42 | 123.41 / 131.42 | 123.41 / 131.42 | 123.41 / 131.42 |

P90-only changes none of the five selected portfolios. Neither changes one roster on Thursday (average −10.83) and one on SF–SEA (average +0.05); morning, Sunday night and Monday stay identical. Mean-only raises SF–SEA average by 3.70 and lowers Thursday by 10.83. These are five correlated, already inspected slates; they do not identify a general improvement.

## Coverage and fill

Eligibility below includes the fixed current Captain shortlist. Newly eligible counts relative to Both95 are in parentheses. Quality and Captain exclusions are separate in results/prepared. All original legal roster and saved preference checks pass.

| Slate | Unique | Both95 eligible | Mean95 | P90 95 | Neither | Max fill Both / Mean / P90 / Neither |
|---|---:|---:|---:|---:|---:|---|
| THURSDAY_NIGHT | 102 | 7 | 9 (+2) | 23 (+16) | 44 (+37) | 4 / 4 / 5 / 5 |
| SUNDAY_MORNING | 65 | 11 | 11 (+0) | 32 (+21) | 40 (+29) | 5 / 5 / 5 / 5 |
| SUNDAY_LATE_SF_SEA | 65 | 14 | 20 (+6) | 15 (+1) | 40 (+26) | 5 / 5 / 5 / 5 |
| SUNDAY_NIGHT | 69 | 8 | 13 (+5) | 13 (+5) | 34 (+26) | 5 / 5 / 5 / 5 |
| MONDAY_NIGHT | 57 | 7 | 7 (+0) | 15 (+8) | 27 (+20) | 5 / 5 / 5 / 5 |

Thursday fill capacity grows four→five when the mean gate is removed, with unchanged player/Captain caps. That is separate from the primary outcome comparison, which stays four. No changed-size outcome was computed. Whole-pool gate partition (both / mean-only / P90-only / neither) is TN10/5/22/65, AM12/0/26/27, SF16/10/6/33, SN18/6/13/32, MN32/0/13/12. Captain filtering then narrows these counts. Thus removing quality alone cannot recover a roster whose Captain is outside the unchanged shortlist.

## What football evidence supports

Every candidate has original canonical-ID-linked role/source/time, game markets, QB/receiver pairs, bring-backs, same-team RB and QB/RB TD dependencies and salary saver evidence in prepared.json. Participation support is deliberately weak: a positive saved projected or lagged workload is not proof of sufficient tournament upside. Null expected workload remains unknown. Backup status and opposing players are not automatic contradictions. No joint target/carry/TD budget can be certified from these snapshots.

Concrete examples were chosen by pregame current score among newly eligible rosters, not by actual score:

- **THURSDAY_NIGHT, original rank alias 28**: CeeDee Lamb CPT; Chase McLaughlin, Cade Otton, Dak Prescott, Ryan Flournoy, Brandon Aubrey. Baseline mean 90.10, marginal P90 sum 152.71; floors 88.83/153.49. Captain role is supported; same-team passing pair True. Salary-saver evidence: no FLEX saver <=$3,000. See exact IDs and sources in football_coverage.json.
- **SUNDAY_LATE_SF_SEA, original rank alias 25**: Jaxon Smith-Njigba CPT; Sam Darnold, Brandin Cooks, Jason Myers, Brock Purdy, Tory Horton. Baseline mean 74.93, marginal P90 sum 133.34; floors 73.57/134.92. Captain role is supported; same-team passing pair True. Salary-saver evidence: Brandin Cooks: projected targets 1.150800708439152, projected carries None (participation_supported); Tory Horton: projected targets 2.221810922315318, projected carries None (participation_supported). See exact IDs and sources in football_coverage.json.
- **MONDAY_NIGHT, original rank alias 68**: James Cook III CPT; Matthew Stafford, Konata Mumpfield, Josh Allen, Tyler Higbee, Keon Coleman. Baseline mean 101.82, marginal P90 sum 165.11; floors 102.15/162.19. Captain role is supported; same-team passing pair not applicable to RB CPT. Salary-saver evidence: Konata Mumpfield: projected targets 3.0545200246512327, projected carries None (participation_supported). See exact IDs and sources in football_coverage.json.
- **SUNDAY_MORNING, original rank alias 24**: Parker Washington CPT; Dallas Goedert, Dameon Pierce, Jalen Hurts, Trevor Lawrence, Brenton Strange. Baseline mean 75.13, marginal P90 sum 134.83; floors 75.76/134.55. Captain role is supported; same-team passing pair True. Salary-saver evidence: Dameon Pierce: projected targets 0.0, projected carries 0.7128507777690923 (participation_supported). See exact IDs and sources in football_coverage.json.

Thursday Lamb + Dak is a coherent passing core with opposing TB participation; it fails the marginal-P90 gate despite passing mean. SF–SEA JSN + Darnold is likewise coherent, with modest Cooks/Horton targets rather than verified large workloads. Monday Cook + Allen + Stafford + Coleman/Higbee has two-sided passing participation and a plausible RB-Captain outcome, but Cook competes with Allen/Ty Johnson for BUF TD paths in other variants; the snapshot has no verified joint budget. The morning Pierce saver has only 0.71 projected carries and zero targets: participation is technically supported but tournament ceiling evidence is thin. These distinctions matter more than calling all released rosters football-aware.

Supplemental structural coverage keeps current Captain eligibility fixed and groups supported Captain roles by own-team roster count and QB count. It is descriptive, added in response to user steering after the main study freeze; no subgroup treatment or outcome tuning. Original generation scenario labels are also preserved across all variants, rather than only the chosen dedup representative. A generated “decisive win” label is not itself evidence of football coherence.

| Slate | Supported structural families before screen | After Both95 | Completely removed families |
|---|---:|---:|---:|
| THURSDAY_NIGHT | 13 | 5 | 8 |
| SUNDAY_MORNING | 11 | 6 | 5 |
| SUNDAY_LATE_SF_SEA | 10 | 3 | 7 |
| SUNDAY_NIGHT | 12 | 6 | 6 |
| MONDAY_NIGHT | 9 | 4 | 5 |

## Contest thresholds

Counts mean reaching frozen field thresholds (ties included), not certified payouts. Full per-contest bands/cash/winner evidence remain in results.json. No cash line is available outside Thursday.

| Slate / contest | Top10 threshold | Both / Mean / P90 / Neither | Cash threshold | Cash counts |
|---|---:|---|---:|---|
| THURSDAY_NIGHT / 196438552 | 104.2 | 0 / 0 / 0 / 0 | 91.6 | 1 / 0 / 1 / 0 |
| THURSDAY_NIGHT / 196438575 | 103.36 | 0 / 0 / 0 / 0 | 89.54 | 2 / 1 / 2 / 1 |
| THURSDAY_NIGHT / 196438576 | 102.54 | 0 / 0 / 0 / 0 | 87.86 | 2 / 1 / 2 / 1 |
| SUNDAY_MORNING / 196458743 | 113.21 | 2 / 2 / 2 / 2 | None | None / None / None / None |
| SUNDAY_LATE_SF_SEA / 196484232 | 103.16 | 0 / 0 / 0 / 0 | None | None / None / None / None |
| SUNDAY_LATE_SF_SEA / 196649394 | 102.41 | 0 / 0 / 0 / 0 | None | None / None / None / None |
| SUNDAY_NIGHT / 196537722 | 101.90001 | 1 / 1 / 1 / 1 | None | None / None / None / None |
| MONDAY_NIGHT / 196537796 | 146.17 | 0 / 0 / 0 / 0 | None | None / None / None / None |
| MONDAY_NIGHT / 196537806 | 147.07 | 0 / 0 / 0 / 0 | None | None / None / None / None |

## Football awareness before quality screening

The user’s ordering hypothesis is sensible to test prospectively: first establish mathematical legality (salary, roster, canonical identities and user constraints), then certify projection/source reliability, then construct evidence-backed football scenarios and record the user thesis, and finally assess strategic selection tradeoffs. A generic 95% strategic filter should expose its scenario attrition so a coherent thesis is not silently erased. These are separate layers: user gut feel/scenario preferences must not rewrite the model forecast or claim an observed scenario is true.

Current Showdown code already constructs script/scenario candidates upstream of the final dual screen; discovery also applies earlier 85% mean/90% P90 and later 95% floors. This fixed-pool test establishes downstream attrition, not whether different scenario-first generation would improve results or create missing lineups. Monday SHOOTOUT fits saved ESPN/DK total54.5, LAR−3.5, implied29/25.5, observed pregame. Original 9c07a5bd Captain preference was WR/RB; current retrospective shortlist remains constrained by that saved preference. Later 06a274d6 Allen/Stafford/Puka/Kyren selections cannot be conflated with this original pool.

## Classic applicability

The tested dual95 selector is the Showdown portfolio path: optimizer.py defines portfolio_v3 from the Showdown strategy at line7173, applies earlier floors at7341 and calls select_showdown_portfolio at7620. Classic GPP branches at8462 through run_gpp_pipeline/execute_strategy_contract and classic_small_field at8734. Its own family/overlap/objective tradeoffs (classic_small_field.py1642, classic_portfolio_policy.py84) differ. The same strategic-filter concern can be investigated, but this Showdown effect cannot be assumed for Classic. Historical Classic pools have only five saved candidates/all selected, so they cannot estimate omitted candidate opportunity.

## Limits and next test

Keep defaults unchanged. Run a prospective pregame-certified comparison on uninspected slates, freezing candidate pool, source timestamps, model/code, preferences, scenario thesis, caps and size. Retain these four screen arms (or prechoose both95 versus neither if budget is limited); record scenario support/coverage before outcomes, unknown saver roles, underfill and contest attainment separately. A separate generation experiment would be needed to test scenario-first/gut-feel candidate construction. Missing contemporaneous executable hash and completion attestation, five inspected pools, correlated rosters and absent joint-opportunity budgets bound this study.

Commands (repo root):

```sh
.venv/bin/python -B -m research.showdown_quality_screen_20261013.study freeze
.venv/bin/python -B -m research.showdown_quality_screen_20261013.study evaluate
.venv/bin/python -B -m research.showdown_quality_screen_20261013.study evaluate
.venv/bin/python -B -m research.showdown_quality_screen_20261013.study validate
.venv/bin/python -B -m research.showdown_quality_screen_20261013.report
```

freeze.json pins original source/report/code hashes, prior harness, annotations/spec and CBC binary. study.py reuses verified prior harness without writing prior artifacts. validation.json records focused checks and repeated identical result bytes. Only this new research directory was written. No application tests or expensive simulation were needed for this offline analysis.
