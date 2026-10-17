# Showdown fixed-pool comparison — retrospective

All six historical physical portfolios and selector totals reproduced. Five Week 5
slates support the three-arm comparison. W4 Sunday night remains descriptive only:
explicitly zoned original pregame generation timing is unverified. This research
wrote only this directory and temporary status snapshots; source queries were
read-only. It changed no production code, live data, defaults or external systems,
and generated no candidates or simulations. No held-out slate was designated;
all outcomes had been inspected.

## Verified findings and corrections

1. Historical scoring was FLEX(P90 + context) summed across players, plus
   1.5 × Captain(P90 + context) × saved Captain-position prior, plus solver lineup
   adjustments. All six priors used the same historical-position fallback at
   strength 0.35. Ownership estimates existed but explicit Showdown selector
   approval was absent; ownership was disabled. Direct simulation leverage applied
   to Classic, not these Showdown runs. Current scoring is exactly 1.5 × Captain
   base P90 + sum(FLEX base means), with four eligible Captains ranked by base P90.
   Ownership, leverage, context, correlation and position-prior objective terms are
   zero in the current role-specific objective.
2. The joint quality screen requires both baseline mean and summed marginal P90
   at least 95% of their separate original full-pool maxima. These maxima need not
   come from the same roster. Fill dominates selector score; player caps, Captain
   caps and physical roster uniqueness follow. Scenario coverage was disabled in
   all six runs. This path has no pairwise overlap cap or required Captain count.
   Every hindsight-best roster fails the recorded screen; that does not establish
   that the eventual best roster was predictable or that the screen should change.
3. Original selections replay exactly as physical rosters, count and objective.
   Tied variants change replay ranks in Monday and Sunday night without changing
   entries. Original five Week 5 candidate hashes match the supplied report.
   Deduplication preserves Captain identity, canonical IDs and six physical
   players; FLEX order is irrelevant. The variant rule is maximum saved baseline
   selector, then baseline scenario, scenario ID and original rank. Baseline
   forecasts/salary agree across all variants. No actuals determine representatives.
4. **Correction to the earlier incomplete-component claim:** empty report columns
   are partly field-name mismatches. Moreover, the correlation summary scales
   positive count-construction bonuses by QB evidence players, while the solver
   scales by required/Captain indexes. The count-only 3–3/4–2/favorite-5–1 bonuses
   therefore differ between summary and solver. Undoing that reporting-only scaling
   reconstructs every saved aggregate historical selector within 1e-7; maximum
   uncorrected residual is 0.0593 points. Raw trigger-level evidence for every
   candidate remains absent. This experiment corrects its research decomposition;
   it does not change any production rule or summary.
5. Current scoring is reconstructable for every candidate from saved pregame means,
   P90s and Captain identity. Its top-four shortlist is computed from **all
   historically included players**, not only Captains appearing in candidates,
   with saved Captain preferences/FLEX-only exclusions and canonical-ID tiebreak.
   The same shortlist applies to every comparison arm. User preferences remain
   eligibility constraints; saved model forecasts/assessments are unchanged.
6. Thursday requested five but could fill only four. Its core cap remains
   ceil(5 × 0.8)=4, eligible starting-QB cap five, cheap-punt cap ceil(5 × 0.4)=2,
   and Captain cap ceil(5 × 0.6)=3. None uses realized denominator four.

## Per-slate comparison

Cells are **portfolio average actual / best actual**. Historical selection is an
observational reference with different Captain eligibility, not a fourth controlled
scoring arm. All three arms share exact eligibility, original quality thresholds,
preferences, integer caps and fixed feasible size. Pool best is a hindsight coverage
diagnostic, not an achievable baseline.

| Slate | Size | Historical reference | Current | Mean | Marginal P90 | Hindsight pool best |
|---|---:|---:|---:|---:|---:|---:|
| W5 THURSDAY_NIGHT | 4 | 86.31 / 89.54 | 87.98 / 94.79 | 85.14 / 88.36 | 87.62 / 94.79 | 120.84 |
| W5 SUNDAY_MORNING | 5 | 100.36 / 119.74 | 102.81 / 119.74 | 102.81 / 119.74 | 98.65 / 117.04 | 122.34 |
| W5 SUNDAY_LATE_SF_SEA | 5 | 82.25 / 95.76 | 87.34 / 101.86 | 87.34 / 101.86 | 83.38 / 95.76 | 118.51 |
| W5 SUNDAY_NIGHT | 5 | 82.94 / 90.50 | 91.10 / 104.80 | 90.98 / 104.80 | 91.10 / 104.80 | 107.74 |
| W5 MONDAY_NIGHT | 5 | 119.12 / 123.17 | 123.41 / 131.42 | 123.41 / 131.42 | 123.41 / 131.42 | 153.27 |
| W4 SUNDAY_NIGHT | excluded | 108.40 / 111.37 | excluded | excluded | excluded | 167.04 |

Current and mean select identical portfolios on Sunday morning, SF–SEA and Monday.
Sunday night differs by one roster (+0.12 average actual for current); Thursday
differs by two (+2.84 average actual). Current and marginal-P90 tie on Sunday night
and Monday. Improvement versus historical mixes scoring and Captain eligibility:
this comparison does not identify the cause of that difference.

## Candidate counts, exclusions and constraint checks

Exclusions below are sequential: original quality rejection, then current Captain
exclusion among quality survivors. Whole-pool Captain exclusions overlap quality
exclusions; their separate totals are retained in results.json.

| Slate | Variants | Unique | Quality rejected | Quality survivors | Captain rejected after quality | Common eligible | Requested | Feasible size | CPT cap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| W5 THURSDAY_NIGHT | 131 | 102 | 92 | 10 | 3 | 7 | 5 | 4 | 3 |
| W5 SUNDAY_MORNING | 88 | 65 | 53 | 12 | 1 | 11 | 5 | 5 | 3 |
| W5 SUNDAY_LATE_SF_SEA | 88 | 65 | 49 | 16 | 2 | 14 | 5 | 5 | 4 |
| W5 SUNDAY_NIGHT | 87 | 69 | 51 | 18 | 10 | 8 | 5 | 5 | 4 |
| W5 MONDAY_NIGHT | 71 | 57 | 25 | 32 | 25 | 7 | 5 | 5 | 4 |
| W4 SUNDAY_NIGHT | 131 | 110 | 95 | 15 | unverified | unverified | 5 | unverified | 3 |

All 15 alternative portfolios pass exact size, canonical roster uniqueness,
current Captain eligibility, original dual screen and player/Captain caps. The three
arms have identical per-slate constraint hashes. Original candidate legality is
retained; explicit saved included-player, Captain-position, QB, lock/exclusion,
salary and team-count preferences were additionally checked. No new football
constraints were invented. No conflicting/missing actuals remain in any of six pools.

## Contest attainment

Each contest appears once, without treating repeated contests as independent
selection evidence. Counts reach the reported score threshold, including ties;
they do not establish payout. Cash evidence is unavailable outside Thursday.
Cells are **current / mean / P90**. Historical reference and other bands are in
results.json.

| Slate | Contest | Top 10% threshold | Top 10% counts | Top 1% counts | Cash threshold | Cash counts |
|---|---|---:|---|---|---:|---|
| W5 THURSDAY_NIGHT | 196438552 | 104.20 | 0 / 0 / 0 | 0 / 0 / 0 | 91.60 | 1 / 0 / 1 |
| W5 THURSDAY_NIGHT | 196438575 | 103.36 | 0 / 0 / 0 | 0 / 0 / 0 | 89.54 | 2 / 0 / 1 |
| W5 THURSDAY_NIGHT | 196438576 | 102.54 | 0 / 0 / 0 | 0 / 0 / 0 | 87.86 | 2 / 1 / 2 |
| W5 SUNDAY_MORNING | 196458743 | 113.21 | 2 / 2 / 1 | 0 / 0 / 0 | — | — / — / — |
| W5 SUNDAY_LATE_SF_SEA | 196484232 | 103.16 | 0 / 0 / 0 | 0 / 0 / 0 | — | — / — / — |
| W5 SUNDAY_LATE_SF_SEA | 196649394 | 102.41 | 0 / 0 / 0 | 0 / 0 / 0 | — | — / — / — |
| W5 SUNDAY_NIGHT | 196537722 | 101.90 | 1 / 1 / 1 | 0 / 0 / 0 | — | — / — / — |
| W5 MONDAY_NIGHT | 196537796 | 146.17 | 0 / 0 / 0 | 0 / 0 / 0 | — | — / — / — |
| W5 MONDAY_NIGHT | 196537806 | 147.07 | 0 / 0 / 0 | 0 / 0 / 0 | — | — / — / — |

## Within-slate ranking

Historical correlations below deduplicate rosters, preserving Captain identity.
They are descriptive dependent observations, not independent lineup trials.
W4 remains descriptive only. No pooled correlations or promotion claim.

| Slate | Unique N | Mean Spearman | Marginal P90 Spearman | Selector Spearman |
|---|---:|---:|---:|---:|
| W5 THURSDAY_NIGHT | 102 | 0.102 | 0.241 | -0.044 |
| W5 SUNDAY_MORNING | 65 | 0.229 | 0.288 | 0.546 |
| W5 SUNDAY_LATE_SF_SEA | 65 | 0.232 | 0.057 | -0.012 |
| W5 SUNDAY_NIGHT | 69 | -0.229 | 0.015 | 0.064 |
| W5 MONDAY_NIGHT | 57 | -0.357 | -0.187 | -0.095 |
| W4 SUNDAY_NIGHT | 110 | 0.089 | 0.065 | -0.362 |

Sunday morning's stronger historical ranking remains after deduplication. Its 60%
Captain cap versus 80% on the other Sunday/Monday runs is a plausible diversity
difference, not an established causal explanation. Its best selected actual was
119.74, versus matched entered actual 112.44. Entry choices are a separate stage:
signature matches do not establish what the user saw, considered, approved or intended.
Report matched-entered values are retained separately in results.json.

## Availability and unverifiable claims

Five Week 5 original input snapshots have verified hashes and explicitly zoned
pre-kickoff freeze/cutoff times. Included means/P90s agree with those snapshots.
Exact selected projection-run IDs have pre-kickoff creation/cutoff metadata, and
saved model artifact/code/training hashes are retained. No latest-data lookup or
new projection was used. Model training was not rerun or revalidated.

Preferences come from the exact saved optimizer parameters; there is no separately
timestamped preference revision. A generation-input freeze is not an independently
timestamped attestation of final candidate-generation completion. Saved candidate
manifests link pools to these runs, but an exact contemporaneous optimizer executable
hash is absent. Archived code and saved coefficients/library labels support numerical
reconstruction without certifying the entire original executable. Today's scoring
code is pinned at experiment time; it is applied retrospectively, not claimed to have
existed pregame. These limits preclude held-out/prospective conclusions.

W4 Sunday night's saved run time is after kickoff and no original explicitly zoned
generation freeze exists. Its pre-kickoff projection cutoff alone is insufficient.
Do not infer a UTC correction or substitute current data. Historical descriptive
replay is supported; current Captain eligibility and alternative outcomes remain
blocked for that slate.

## Recommendation

Keep projected mean as a cheap control; current scoring's advantage over it is
limited to two slates here. Do not change defaults from this retrospective sample.
A separate quality-screen experiment is warranted because original screening
removes 25–92 distinct Week 5 rosters and Thursday underfills, not because hindsight
best should have been picked. Predeclare one comparison: 95% screen versus no screen,
with current scoring/shortlist, candidate pools, preferences and caps held constant.
Use the same prechosen portfolio size in both arms; measure feasible fill/coverage
separately from outcome performance. Do not optimize a threshold grid on these
outcomes. Use genuinely uninspected, pregame-certified slates for held-out conclusions.
This experiment does not validate today's candidate generator or future improvement.

## Code and saved-evidence citations

- [Historical objective](/Users/wones/git/football_26/artifacts/showdown_qb_construction/audited_code/optimizer.py.0bbba8146455.txt:5282).
- [Current objective](/Users/wones/git/football_26/backend/app/product_services/optimizer.py:5473).
- [Current Captain eligibility](/Users/wones/git/football_26/backend/app/product_services/showdown_captain_shortlist.py:30).
- [Dual screen and portfolio constraints](/Users/wones/git/football_26/backend/app/product_services/showdown_portfolio_selection.py:125).
- [Requested-count caps](/Users/wones/git/football_26/backend/app/product_services/optimizer.py:7251).
- [Candidate metrics](/Users/wones/git/football_26/backend/app/product_services/showdown_portfolio_selection.py:19).
- [Reporting field extraction](/Users/wones/git/football_26/backend/app/product_services/optimizer_effectiveness.py:488).
- [Solver QB term scaling](/Users/wones/git/football_26/artifacts/showdown_qb_construction/audited_code/optimizer.py.0bbba8146455.txt:1526).
- [Summary QB scaling](/Users/wones/git/football_26/backend/app/product_services/optimizer.py:1645).
- [Count-construction evidence indexes](/Users/wones/git/football_26/backend/app/product_services/lineup_correlation_scoring.py:1246).
- [Count-construction weights](/Users/wones/git/football_26/backend/app/product_services/lineup_correlation_scoring.py:530).
- [Ownership promotion gate](/Users/wones/git/football_26/backend/app/product_services/showdown_ownership_policy.py:5).
- [W4 timing caveat](/Users/wones/git/football_26/artifacts/showdown_selection_diversity_audit/prelock_policy_freeze.json:54026).
- [Thursday recorded exclusion](</Users/wones/Downloads/week-learning-2026-w05-wones0120 (2).md:25554>).
- [Monday recorded exclusion](</Users/wones/Downloads/week-learning-2026-w05-wones0120 (2).md:4782>).
- [SF–SEA recorded exclusion](</Users/wones/Downloads/week-learning-2026-w05-wones0120 (2).md:15071>).
- [Sunday-night recorded exclusion](</Users/wones/Downloads/week-learning-2026-w05-wones0120 (2).md:22578>).
- [Sunday-morning recorded exclusion](</Users/wones/Downloads/week-learning-2026-w05-wones0120 (2).md:20669>).

The dedicated input exports retain the exact six saved configurations, selected
lineups/players, projection metadata and original frozen frames. verification.json
records original rank aliases, physical replay, thresholds, omission reasons,
preferences, counts and reconstruction residuals. prepared.json pins that evidence
and feasible sizes before outcome evaluation. results.json includes every candidate,
selected canonical roster ID, actual, constraint check and contest threshold.

## Exact commands and provenance

Run from `/Users/wones/git/football_26`. Source exports use REPEATABLE READ / READ ONLY
transactions. Existing immutable evidence rejects differing overwrites. `verify`
and `freeze` are pre-evaluation phases; after freeze, repeat offline tests/evaluation
against the saved files. A new independent capture belongs in another directory.

```sh
.venv/bin/python -B -m research.showdown_fixed_pool_20261013.capture pregame
.venv/bin/python -B -m research.showdown_fixed_pool_20261013.experiment verify
.venv/bin/python -B -m unittest research.showdown_fixed_pool_20261013.test_experiment -v
.venv/bin/python -B -m research.showdown_fixed_pool_20261013.experiment freeze
.venv/bin/python -B -m research.showdown_fixed_pool_20261013.capture outcomes
.venv/bin/python -B -m research.showdown_fixed_pool_20261013.experiment evaluate
```

The final offline evaluation was repeated unchanged and the immutable writer
confirmed identical result bytes. Eleven focused tests cover Captain-aware
deduplication, variant consistency, role scoring, source objective, fixed
size/infeasibility, requested denominator, historical replay, objective
reconstruction, tie stability and canonical actual conflicts.

Git HEAD: `3bae3ff4aac9ac4963859a388d907ab934921666`. Working-tree bytes, including uncommitted edits, are separately pinned. Current policy: `showdown_top_four_p90_v1`. Historical profile: `showdown_large_gpp_v1`, context library `v2`, Captain prior strength `0.35`; exact original optimizer executable version unavailable. Saved projection model version: `v4.2-market-corrected` (per-run hashes in results.json).

PuLP `3.3.0`; CBC single thread, `randomSeed 0`; solver SHA-256 `9eeb33c515945620d89dfc2efef9c6740b559e14a6603153a156c6e288a5765b`. Freeze saved at `2026-10-13T13:03:17.124180+00:00` before separate outcome capture/evaluation.

| Artifact | SHA-256 |
|---|---|
| [SPECIFICATION.md](</Users/wones/git/football_26/research/showdown_fixed_pool_20261013/SPECIFICATION.md>) | `56e4e662ffadfef275aa14b4b6aa93264fc647fed5fb56c0996b6cfc863852ba` |
| [prepared.json](</Users/wones/git/football_26/research/showdown_fixed_pool_20261013/prepared.json>) | `fcea1d48f7035fe6d778224f7f1028396aee4bcd3d9580261a47fb4d0972b8bf` |
| [freeze.json](</Users/wones/git/football_26/research/showdown_fixed_pool_20261013/freeze.json>) | `9ab2ff7ee33d8acb512b11432f4630b82bebb5be99ddb6c2290ba40355b97433` |
| [input_manifest.json](</Users/wones/git/football_26/research/showdown_fixed_pool_20261013/input_manifest.json>) | `50bbdccf0383982bae91e7c803aa26e1e9beb1753c2d5b64ea0211b0cf4b10d7` |
| [results.json](</Users/wones/git/football_26/research/showdown_fixed_pool_20261013/results.json>) | `80f153fc6e486d4c6b72f2d8c811e9477fcd083fbd83e360f8056fc2b5a7d960` |

| Run | Source export SHA-256 | Original pool SHA-256 |
|---|---|---|
| 3a41af88-a28c-41b1-888c-462ddcd7d74d | `462326350b776163f2d9dff38f0416e8d011e658182cf2f425fd00240e1ccad5` | `f0d42555f4be40a171d35f057226322b62bab67bb15eb280ce350aa7bdc7f16c` |
| a07b5a67-f041-49e0-ad51-4001ba04fb79 | `07a6f822f848822b1c6fbc9e5507546669143f39367d0ed982d37b1c87ec241b` | `c453b10693353dfd43c66eca8d44561e54d7aac8104d71c9be8c290724ba2f47` |
| 17212766-52eb-40ed-9544-e599d7bfb8bd | `6449c3b0a0dd77fe11ae069f790e463061e82e353c59fbf61e8a0f06d884961d` | `a0b8283fd26bc29bda6e0a31eafb20748e87d9ba6bad54eea28fd799cb2c5162` |
| 442dd04c-7c8c-46f6-80c5-273924e7c655 | `b67cd49112d7f2eee918a332795354c17fa1be4913121800fe7334206125850f` | `732483e85a4ccb792cc51dd20837a85f685ce0f40afb9e5f431f6676f10b40f5` |
| 9c07a5bd-11ac-42b1-a0d0-7e6b3a30fb4f | `29588130fe7c00b94f5b8a1e7402df6517b50ed0af4edc56cd308f20d86c5d12` | `2dd773a0a7ac960234de49b93b243a85596ef1f95c8af5e62cec940d4dd49a5f` |
| dc21b3ab-c330-487c-bb88-766f9a71f04c | `8a356f7d768c89e6fe8f5fb84ca82fd2fbad20a84a94ab1ee8a2d21083129c66` | `abb295a8f2119721be45685ebdb96e201dccfb3486e0ac40a99f0faaa4039f28` |

| Source/code path | SHA-256 |
|---|---|
| artifacts/showdown_qb_construction/audited_code/optimizer.py.0bbba8146455.txt | `0bbba8146455ff03a66332baa0c14a2da9039d6d46e1fa0620ef16cbf3d14c3a` |
| artifacts/showdown_qb_construction/audited_code/showdown_portfolio_selection.py.4bdbc82c5f83.txt | `4bdbc82c5f838280ae3126aee6297a0be8d2f1304b67831ef604b5ba4e7e68c5` |
| backend/app/product_services/lineup_correlation_scoring.py | `f4700514a4a2a3e002353dbec43bdeedeff65150538163ffd35fdc16d5344eb4` |
| backend/app/product_services/optimizer.py | `d1d5fc74dda4f5bad93b768eda82cf9928f7b3fe34df06d999b86c64106264ff` |
| backend/app/product_services/optimizer_effectiveness.py | `f4ffbb50c92255d5b0c3cf0df77cb76a1f8af4e71d3b1743a106ab5129600c20` |
| backend/app/product_services/player_context_scoring.py | `82ea698aab60ce4c9f0b559863f91c3c6518fdbb2bc77a61bb502c4e43d0fa02` |
| backend/app/product_services/showdown_candidate_comparison.py | `6c805f8cefd33111eb45834e369fdb647ff37226aedc35335053634ad8d5fc34` |
| backend/app/product_services/showdown_captain_preferences.py | `e72b3669ae6f2cd88b036c3cbab1aa3e682a3ab633d1ecaf301319b8fdfedd18` |
| backend/app/product_services/showdown_captain_shortlist.py | `26050893d057c825b23826a2964a36f4fb1e75b3de6bd473fdc2290fe22d50c4` |
| backend/app/product_services/showdown_ownership_policy.py | `1dfef06228e0cbc053f8a9a092306d677bd5c186cc944cb96b703202e6a0d055` |
| backend/app/product_services/showdown_portfolio_selection.py | `15e8b08eca2ffa2042ed6a1061b4abee17ba64f54629ebaf9f8514959783d2ec` |

| Research code | SHA-256 |
|---|---|
| capture.py | `b5194fa3e76381b019ed7c6cb658bd4a13a5b745899764521dbd80c41ebb889e` |
| experiment.py | `9f47b41726f3805c0fce5bf4f885a9e96ae7e39ddfe088cdcf01c036c256a2d1` |
| test_experiment.py | `b4bc67e149415f2bd937759ae9fd995a196ca66ef3dc40b6b34c5a83d933ee48` |

Artifact map: SPECIFICATION.md and freeze.json establish the plan; input_manifest.json
pins source/code hashes; inputs/code contains the captured working-tree and archived
code; verification.json records historical reproduction; prepared.json pins common
inputs and feasible sizes; outcomes contains separately captured actuals and report
thresholds; results.json contains detailed comparisons; test_experiment.py is the
focused suite; replay_output.txt captures repeated evaluation; validation.json and
validation_output.txt record final checks. workspace_before.json hashes all
preexisting tracked files. Eight files changed outside this task during research
(including slate_learning.py, job_handlers.py, agents.md and repository docs);
their paths are disclosed in validation.json. They were left untouched. All pinned
experiment inputs, scoring dependencies and frozen research code remained unchanged.
