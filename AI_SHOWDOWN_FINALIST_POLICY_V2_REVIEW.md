# AI Showdown finalist policy v2 review

## 1. Result and the v1 problem

V2 is implemented and both 20-lineup sets are frozen and audited. It improves prelock quality and some structural coverage, but **does not meet the overall historical tail-retention acceptance criteria**. Neither Thursday’s rank-72 best generated roster nor Sunday’s rank-43 best generated roster survives naturally. No parameters were changed to force either into the packet. Keep AI/manual selection trials pending.

V1 could satisfy broad scenario, captain-position and split buckets while missing a meaningful joint football bet. Its joint 85% mean/ceiling floor also lacked independent-dimension eligibility. The Thursday best was already v1-quality-eligible: its omission was not caused by the 85% floor.

## 2. Files and scope

| File | Change |
|---|---|
| `backend/app/product_services/ai_showdown_packet.py` | V2 classifier, signatures, quality, market compatibility, finalist selection, coverage, similarity, Markdown and explicitly separate retrospective entry point |
| `backend/app/product_services/ai_showdown_finalist_audit.py` | Separate frozen-packet post-slate scoring and regret/tail audit |
| `scripts/export_ai_showdown_packet.py` | Configurable quality fractions and explicit retrospective CLI mode |
| `scripts/audit_ai_showdown_finalists.py` | Audit frozen JSON with separate canonical actuals; optional universe benchmark and manual selection |
| `backend/app/tests/product/test_ai_showdown_packet.py`, `test_ai_showdown_finalist_audit.py` | Behavioral, deterministic, chronology, leakage, coverage and diagnostic tests |
| `docs/product/ai_showdown_selection_packet_v1.schema.json` | Conditional additive v2 requirements; historical v1 properties preserved |
| `docs/product/ai_showdown_finalist_set_audit_v1.schema.json` | New post-slate diagnostic contract |
| `README.md`, `RELEASE_NOTES.md`, `docs/AI_SHOWDOWN_SELECTION_PACKET_PLAN.md` | Behavior, reproduction and pending acceptance criteria |
| `artifacts/ai_showdown_selection_packet/policy_v2/` | Saved database sources, frozen packets, manifests, canonical actuals, audits, original v1 code and comparison evidence |

No production selector, optimizer, database schema, API route or UI source was changed by this revision. `showdown_portfolio_selection.py` remains at SHA-256 `4bdbc82c5f838280ae3126aee6297a0be8d2f1304b67831ef604b5ba4e7e68c5`. No solver, LLM or external API participates in finalist construction.

## 3. Contracts and compatibility

`ai_showdown_selection_packet_v1` and `ai_showdown_manual_selection_v1` remain the contract IDs. The classifier is `ai_showdown_construction_v2`; the finalist policy is `ai_showdown_finalists_v2`. Existing fields and canonical candidate IDs remain. `scenario_tags` / `scenario_reason_codes` now alias football scenarios only: downstream readers must use `construction_attributes` for `non_qb_captain` and punt/mechanical tags.

Each finalist and each pool `candidate_assessments` row exposes primary/all signatures, signature reasons, clean construction, multidimensional eligibility and market compatibility/reasons. The pool exposes `finalist_coverage`, algorithm settings and uncovered eligible primary theses. `quality_floor_fraction` now identifies the minimum safety band; consumers must read `quality_policy` for the full rule.

`ai_showdown_finalist_set_audit_v1` is separate. It validates the frozen packet hash, saved optimizer ID and original pool hash before scoring. It does not call the builder. Canonical player IDs and CPT identity define each distinct roster; duplicate scenario variants cannot inflate retention counts.

Normal `build_packet` and the existing download API still reject creation after kickoff. `build_retrospective_packet` / CLI `--retrospective` retain the real clock and all evidence checks, but visibly label generation unverified. This path is absent from the download API.

## 4. Exact deterministic finalist algorithm

1. Validate a completed saved Showdown run, canonical six-player rosters, source timestamps and pool manifest. Copy only named prelock fields. Deduplicate by six canonical player IDs plus CPT identity, retaining the smallest original selector rank and every variant rank.
2. Classify every candidate, derive primary/all theses, and rank distinct rosters independently by baseline mean and baseline summed marginal P90. `selector_pool_rank` is the ordinal selector rank among distinct rosters; `selector_rank` remains the archived variant rank.
3. Apply the quality eligibility rule below. Seed the top three independently from eligible selector rank, mean and ceiling. Overlap reduces the number of distinct seed slots but retains every applicable reason.
4. For every eligible primary thesis and every eligible captain-side/archetype/split/QB combination, nominate its best representative by descending average normalized mean and ceiling, then descending best individual fraction, then ascending archived selector rank and canonical candidate ID.
5. Until three slots remain, greedily choose an unselected nomination that adds a primary thesis or captain combination. Order by descending `4 * new_primary_thesis + 3 * new_captain_combination`; then fewer HIGH-similarity pairs with current selections; then more new football scenarios; then the representative quality key. Salary/ownership bucket changes do not create novel theses.
6. Reserve up to three slots for eligible unselected candidates with a new primary thesis or captain combination and `selector_pool_rank > max(10, ceil(distinct_rosters / 4))`. Choose by the same coverage key. No selector-rank screen applies to other thesis nominees. Slots are released if no qualified novel outliers exist.
7. Fill remaining capacity from eligible candidates by that same key, labeling novelty as thesis coverage and otherwise quality coverage fill. Underfill if too few qualify; never force an ineligible bucket. Return at most the requested count, sorted by archived selector rank and candidate ID.

The packet size remains configurable from 15 to 30 (default 20); requested final portfolio size remains 2–5. Market compatibility is descriptive and is neither a screen nor a ranking bonus. Captain-side combinations are explicitly nominated but are **not hard quotas**; this is a material limitation demonstrated below.

## 5. Quality eligibility

Let `m = baseline_mean / pool_max_baseline_mean` and `c = baseline_P90 / pool_max_baseline_P90`. Eligibility is:

```text
finite saved mean and ceiling
AND min(m, c) >= minimum_fraction        # default 0.80
AND (m >= strong_fraction               # default 0.90
     OR c >= strong_fraction
     OR original_selector_rank <= 3)
```

Both maxima must be positive. Each eligible reason is recorded separately. The configurable fractions satisfy `0 < minimum <= strong <= 1`; configuration is serialized into the evidence hash. This permits a candidate excellent in one dimension and acceptable in the other. It is not a Pareto-frontier implementation; independent seeds and OR eligibility provide that preservation without introducing a separate dominance optimizer.

This is not a strict relaxation of v1: a candidate at 89% in both dimensions passes the old 85% joint rule and fails the new strong-dimension requirement unless it is selector top three. Thursday eligibility changes from 101 to 93; Sunday from 104 to 110. Neither known best is eliminated by either quality floor.

Thursday’s rank-72 saved variant has scenario-adjusted mean/P90 **64.9078 / 136.5139**, matching the request’s approximate values. Its baseline mean/P90 is **62.0827 / 130.4810**, objective **129.0205**, mean/ceiling fractions **0.9140 / 0.9154**. V1 and v2 use the saved baseline metrics for quality, rather than mixing hypothetical scenario adjustments into model quality.

## 6. Thesis definition and classifier

```text
football_scenario|captain_archetype|normalized_team_split|qb_structure
```

Examples: `competitive_shootout|QB|3-3|both_qbs`, `competitive_shootout|WR|3-3|both_qbs`, and `favorite_rush_win|RB|4-2_favorite|both_qbs`.

Football rules: K/DST captain adds defense/special teams; two K/DST slots add low scoring; 3–3 adds balanced competition and, with both QBs, shootout. A majority-team QB or QB-supported WR/TE captain adds that side’s pass-win thesis; majority-team RB captain adds rush-win. Five from the favorite adds dominant win, five from the underdog adds upset. Minority-side QB/receiving captain with its QB adds that side’s trailing-comeback thesis. With no directional evidence, add balanced competition with an explicit fallback reason.

Primary scenario priority is fixed: defense/special teams, low scoring, favorite dominant, underdog upset, favorite comeback, underdog comeback, favorite pass, favorite rush, underdog pass, underdog rush, shootout, balanced competition. All applicable signatures and reasons remain. Captain archetypes are saved positions, except skill captains with CPT salary <= $1,500 become `punt_skill`. Construction separately contains captain side, QB/non-QB, normalized team counts and QB structure, punt/K/DST attributes, salary-left and complete-ownership buckets. Missing ownership remains null.

Signatures intentionally do not identify the captain’s team or individual player. `captain_script_combination` supplements them with captain side. Similarity also tracks individual captain identity. These heuristics describe plausible paths, not calibrated probabilities.

## 7. Market compatibility

The baseline quote retained in the saved scenario definitions takes precedence over selected-row spreads/implied totals, which can be scenario-conditioned. Conflicting baseline quotes, missing baseline observation timestamps, or observations after the cutoff are rejected. The packet exposes favorite/underdog, total, spread/implied totals by team, observation clocks, source and baseline basis.

| Primary script | Deterministic compatibility |
|---|---|
| Low scoring / defense-special teams | HIGH at total <=42; LOW at total >=48; otherwise MEDIUM |
| Shootout / balanced competition | LOW at absolute spread >=10, or shootout with total <=42; HIGH at spread <7 and either balanced script or total >=48; otherwise MEDIUM |
| Underdog win / upset | LOW at spread >=7; otherwise MEDIUM |
| Favorite dominant win | HIGH at spread >=7; otherwise MEDIUM |
| Favorite pass/rush win | HIGH when saved baseline market is complete |
| Trailing comeback | MEDIUM, with contrarian-path reason |
| Incomplete baseline market | MEDIUM with explicit unavailable-evidence reason |

Thursday’s actual saved baseline market is **PIT -2.5, total 38.5, implied PIT 20.5 / CLE 18.0**. The selected-row PIT -14 / 26.25 quote is hypothetical conditioned evidence, not the baseline. Sunday’s saved baseline is **DET -3.5, total 51.5, implied DET 27.5 / CAR 24.0**. No current market lookup occurs.

## 8. Similarity

Expose player overlap count, captain match, primary scenario match, team split match, QB structure match, signature match, categorical similarity and a numeric score. Legacy overlap fields remain.

```text
numeric_score = .30 * overlap / 6
              + .25 * captain_match
              + .20 * primary_scenario_match
              + .10 * team_split_match
              + .10 * qb_structure_match
              + .05 * thesis_signature_match
```

HIGH requires >=5 shared players and the same individual captain, primary scenario, normalized split and QB structure. Otherwise MEDIUM requires >=4 shared players or the same captain plus scenario overlap; the remainder is LOW. Numeric score is explanatory; the categorical rule controls selection redundancy. A different captain/QB/scenario prevents a five-player overlap alone from becoming HIGH. Roster similarity is not outcome covariance.

## 9. Validation and freeze chronology

**37 targeted tests passed** across packet, retrospective audit and existing production portfolio-selection tests. Tests cover independent dimensions, OR quality and safety/configuration, deeper novel outliers, underfill, scenario/construction separation, all signatures/reasons, meaningful overlap differences, baseline-conditioned market separation, missing market context, real retrospective clocks, API chronology rejection, canonical source lineage, future/postgame injection, repeatability, decision invariance under input reordering, additive schema requirements, packet/pool hash rejection, missing/conflicting actuals, CPT normalization, regret decomposition, tail cutoff ties, complete-field requirements and packet immutability. Python compilation and whitespace checks pass. No frontend source changed, so a UI build was unnecessary. Schema checks parse JSON and verify required contract fields; a full external JSON Schema validator was not installed.

Finalist freeze: `2026-10-06T12:06:13.739109+00:00`. First postgame read: `2026-10-06T12:07:32.548177+00:00`. [Freeze manifest](artifacts/ai_showdown_selection_packet/policy_v2/policy_freeze.json) and [postgame read manifest](artifacts/ai_showdown_selection_packet/policy_v2/postgame_read_manifest.json) record the ordering and policy hashes. The separate audit gained contest-field diagnostics after packet freeze but **before** the first postgame read; the read manifest records that audit revision. Finalist policy code and packet hashes remained unchanged.

## 10–11. Frozen Thursday and Sunday packet coverage

### Thursday Night

Run `ffb8acf8-2e31-414e-81da-417d6d82c584` · `prelock_saved_run`.
[Markdown packet](artifacts/ai_showdown_selection_packet/policy_v2/thursday/AI_SHOWDOWN_SELECTION_PACKET_THURSDAY_NIGHT_ffb8acf8-2e31-414e-81da-417d6d82c584.md) · [JSON packet](artifacts/ai_showdown_selection_packet/policy_v2/thursday/AI_SHOWDOWN_SELECTION_PACKET_THURSDAY_NIGHT_ffb8acf8-2e31-414e-81da-417d6d82c584.json)

Packet hash `8a07d37775b399a2770ff67631094de7657428a14452ce6e5f8b90c85fe66914`; candidate pool hash `37baedcf9e6ce6bc5da46adcfad672ebe400af65199a3c7fb77f05089d9819cd`.

149 variants, 117 distinct/scoreable generated rosters, 93 quality eligible, 20 finalists. 17 primary theses, 12 football scenarios, 4 archetypes, 5 splits, 2 QB structures, 17 captain combinations. 16 eligible primary theses remain uncovered.

Captain archetypes: `{'K': 2, 'QB': 4, 'RB': 7, 'WR': 7}`. Splits: `{'3-3': 3, '4-2_favorite': 3, '4-2_underdog': 9, '5-1_favorite': 2, '5-1_underdog': 3}`. QBs: `{'both_qbs': 8, 'underdog_qb_only': 12}`. Market counts: `{'HIGH': 7, 'LOW': 2, 'MEDIUM': 11}`.

Selector ranks: `[1, 2, 3, 5, 11, 28, 29, 47, 55, 56, 59, 67, 68, 71, 76, 77, 82, 85, 125, 147]` (median 57.5).

Mean ranks: `[1, 2, 3, 5, 6, 7, 8, 9, 13, 15, 16, 17, 19, 20, 21, 29, 34, 35, 49, 53]` (median 15.5).

Ceiling ranks: `[1, 2, 3, 7, 8, 9, 12, 16, 19, 20, 23, 29, 31, 32, 35, 38, 63, 71, 74, 103]` (median 21.5).

| Selection mechanism | Distinct origin count | Overlapping reason count |
|---|---:|---:|
| ceiling_preservation | 3 | 3 |
| mean_preservation | 3 | 3 |
| outlier_preservation | 3 | 3 |
| quality_coverage_fill | 0 | 0 |
| selector_quality_preservation | 3 | 3 |
| thesis_coverage | 8 | 8 |

Origin counts sum to 20; reason counts can overlap when a seed leads several dimensions.

### Sunday Night (retrospective only)

Run `dc21b3ab-c330-487c-bb88-766f9a71f04c` · `retrospective_unverified_generation`.
[Markdown packet](artifacts/ai_showdown_selection_packet/policy_v2/sunday/AI_SHOWDOWN_SELECTION_PACKET_SUNDAY_NIGHT_dc21b3ab-c330-487c-bb88-766f9a71f04c_RETROSPECTIVE.md) · [JSON packet](artifacts/ai_showdown_selection_packet/policy_v2/sunday/AI_SHOWDOWN_SELECTION_PACKET_SUNDAY_NIGHT_dc21b3ab-c330-487c-bb88-766f9a71f04c_RETROSPECTIVE.json)

Packet hash `cb4126270ad0e80aa31a99430c669daa3f0609517b9d17f2e6c2be0bb0720592`; candidate pool hash `abb295a8f2119721be45685ebdb96e201dccfb3486e0ac40a99f0faaa4039f28`.

131 variants, 110 distinct/scoreable generated rosters, 110 quality eligible, 20 finalists. 17 primary theses, 12 football scenarios, 5 archetypes, 5 splits, 1 QB structures, 17 captain combinations. 6 eligible primary theses remain uncovered.

Captain archetypes: `{'K': 2, 'QB': 5, 'RB': 3, 'TE': 3, 'WR': 7}`. Splits: `{'3-3': 8, '4-2_favorite': 6, '4-2_underdog': 4, '5-1_favorite': 1, '5-1_underdog': 1}`. QBs: `{'both_qbs': 20}`. Market counts: `{'HIGH': 10, 'LOW': 2, 'MEDIUM': 8}`.

Selector ranks: `[1, 3, 5, 11, 35, 44, 49, 54, 56, 57, 70, 75, 77, 86, 91, 92, 99, 118, 121, 129]` (median 63.5).

Mean ranks: `[1, 2, 3, 4, 6, 12, 13, 17, 19, 20, 23, 29, 30, 31, 35, 46, 47, 50, 62, 71]` (median 21.5).

Ceiling ranks: `[1, 2, 3, 4, 6, 8, 10, 12, 16, 17, 18, 21, 25, 33, 44, 59, 64, 70, 94, 96]` (median 17.5).

| Selection mechanism | Distinct origin count | Overlapping reason count |
|---|---:|---:|
| ceiling_preservation | 2 | 3 |
| mean_preservation | 3 | 3 |
| outlier_preservation | 3 | 3 |
| quality_coverage_fill | 0 | 0 |
| selector_quality_preservation | 3 | 3 |
| thesis_coverage | 9 | 9 |

Origin counts sum to 20; reason counts can overlap when a seed leads several dimensions.


**Sunday chronology limitation:** the saved run was created at 10:08 p.m. ET, after its 8:20 p.m. kickoff. Its cutoff was 6:07 p.m. ET and source quotes predate cutoff, but that does not prove the candidate pool existed at lock. The normal exporter still rejects it. The provided Sunday packet is useful for a deterministic retrospective policy comparison only.

## 12–13. Post-slate finalist-set audits

All 117 Thursday and 110 Sunday distinct rosters have resolved canonical actuals; every finalist is scoreable. No missing scores were imputed. Top tails below are **within the distinct generated pool**, `ceil(N * pct/100)` with all cutoff ties included. Complete contest-field tails follow separately.

| Metric | Thursday | Sunday retrospective |
|---|---:|---:|
| best_generated_actual_score | 114.96 | 167.04 |
| best_finalist_actual_score | 111.43 | 148.07 |
| finalist_selection_regret | 3.53 | 18.97 |
| eventual_best_generated_candidate_included | False | False |
| best_generated_selector_rank | 72 | 43 |
| selector_rank_of_best_finalist | 2 | 70 |
| Generated top-1% retained | 0/2 (0.0%) | 0/2 (0.0%) |
| Generated top-5% retained | 1/6 (16.7%) | 0/6 (0.0%) |
| Generated top-10% retained | 2/12 (16.7%) | 1/11 (9.1%) |

THURSDAY_NIGHT: [audit JSON](artifacts/ai_showdown_selection_packet/policy_v2/thursday/AI_SHOWDOWN_SELECTION_PACKET_THURSDAY_NIGHT_ffb8acf8-2e31-414e-81da-417d6d82c584_POST_SLATE_AUDIT.json) · [audit Markdown](artifacts/ai_showdown_selection_packet/policy_v2/thursday/AI_SHOWDOWN_SELECTION_PACKET_THURSDAY_NIGHT_ffb8acf8-2e31-414e-81da-417d6d82c584_POST_SLATE_AUDIT.md). Actual-rank distribution among generated rosters: `[4, 10, 14, 15, 17, 19, 23, 25, 26, 39, 43, 47, 54, 55, 62, 73, 77, 81, 85, 92]`.

SUNDAY_NIGHT: [audit JSON](artifacts/ai_showdown_selection_packet/policy_v2/sunday/AI_SHOWDOWN_SELECTION_PACKET_SUNDAY_NIGHT_dc21b3ab-c330-487c-bb88-766f9a71f04c_RETROSPECTIVE_POST_SLATE_AUDIT.json) · [audit Markdown](artifacts/ai_showdown_selection_packet/policy_v2/sunday/AI_SHOWDOWN_SELECTION_PACKET_SUNDAY_NIGHT_dc21b3ab-c330-487c-bb88-766f9a71f04c_RETROSPECTIVE_POST_SLATE_AUDIT.md). Actual-rank distribution among generated rosters: `[11, 12, 22, 25, 26, 30, 32, 33, 43, 51, 52, 53, 61, 62, 64, 68, 79, 87, 95, 108]`.

Regret decomposition is explicit: candidate-generation regret is null because no complete physical-universe oracle was supplied; filtering regret is 3.53 / 18.97; AI/manual selection regret is null because no frozen AI/manual final selection was supplied. The best observed field score is not substituted for a complete universe oracle.

## 14–15. Did the historical bests survive naturally?

**Thursday: no.** Rank 72 (`Aaron Rodgers` CPT) is quality eligible and has thesis `competitive_shootout|QB|3-3|both_qbs`, captain combination `favorite|QB|3-3|both_qbs`. The finalists contain that primary thesis via rank 68, an underdog QB captain, but no favorite-QB/3–3 combination. The bounded nomination/slot competition can still erase a meaningful captain-side difference even though the signature bucket appears covered.

**Sunday: no.** Rank 43 (`Tetairoa McMillan` CPT) is quality eligible through its 94.9% ceiling fraction; its mean is 85.7% of maximum. Its thesis is `competitive_shootout|WR|3-3|both_qbs`, captain combination `underdog|WR|3-3|both_qbs`. The set contains three favorite-WR finalists with that primary thesis but no underdog-WR/3–3 combination. Broad thesis counts therefore still overstate preservation of meaningful winning paths.

These findings were obtained only after both finalist sets were frozen. They identify a policy weakness, not a justification for retroactively adding known winners.

## 16. Complete contest-field top-tail retention

Every listed contest has the full reported field of scored entries. Top percent uses conservative worst tied field rank, including saved-score tolerance; retain/count is a subset of distinct generated candidates, not total entries. Do not aggregate across contests: the same generated roster is evaluated in each field.

| Slate | Contest / entries | Tail | v1 retained/generated | v2 retained/generated |
|---|---|---|---|
| SUNDAY_NIGHT | 196285052 / 47562 | 1% | 0/4 | 0/4 |
| SUNDAY_NIGHT | 196285052 / 47562 | 5% | 0/7 | 0/7 |
| SUNDAY_NIGHT | 196285052 / 47562 | 10% | 2/12 | 2/12 |
| SUNDAY_NIGHT | 196285061 / 3567 | 1% | 0/1 | 0/1 |
| SUNDAY_NIGHT | 196285061 / 3567 | 5% | 0/7 | 0/7 |
| SUNDAY_NIGHT | 196285061 / 3567 | 10% | 2/12 | 2/12 |
| SUNDAY_NIGHT | 196285072 / 3963 | 1% | 0/4 | 0/4 |
| SUNDAY_NIGHT | 196285072 / 3963 | 5% | 0/10 | 0/10 |
| SUNDAY_NIGHT | 196285072 / 3963 | 10% | 2/12 | 2/12 |
| SUNDAY_NIGHT | 196285073 / 4756 | 1% | 0/4 | 0/4 |
| SUNDAY_NIGHT | 196285073 / 4756 | 5% | 0/10 | 0/10 |
| SUNDAY_NIGHT | 196285073 / 4756 | 10% | 2/12 | 2/12 |
| THURSDAY_NIGHT | 196187076 / 99088 | 1% | 0/3 | 0/3 |
| THURSDAY_NIGHT | 196187076 / 99088 | 5% | 3/10 | 2/10 |
| THURSDAY_NIGHT | 196187076 / 99088 | 10% | 5/21 | 6/21 |
| THURSDAY_NIGHT | 196187096 / 5945 | 1% | 0/3 | 0/3 |
| THURSDAY_NIGHT | 196187096 / 5945 | 5% | 2/9 | 1/9 |
| THURSDAY_NIGHT | 196187096 / 5945 | 10% | 5/22 | 6/22 |
| THURSDAY_NIGHT | 196187097 / 5945 | 1% | 0/3 | 0/3 |
| THURSDAY_NIGHT | 196187097 / 5945 | 5% | 2/9 | 1/9 |
| THURSDAY_NIGHT | 196187097 / 5945 | 10% | 5/22 | 6/22 |
| THURSDAY_NIGHT | 196272912 / 2378 | 1% | 0/3 | 0/3 |
| THURSDAY_NIGHT | 196272912 / 2378 | 5% | 3/13 | 2/13 |
| THURSDAY_NIGHT | 196272912 / 2378 | 10% | 5/24 | 7/24 |

Thursday field top-10% retention improves from five to six candidates in every field, while field top-5% retention decreases and top-1% remains zero. Sunday field-tail counts are unchanged. Generated-pool top-10% retention falls on Thursday and is unchanged Sunday. There is no demonstrated consistent top-tail improvement.

## 17. V1 versus v2 quality and diversity

V1 was reproduced from a [pre-edit source snapshot](artifacts/ai_showdown_selection_packet/policy_v2/comparison/ai_showdown_packet_v1.py.txt). Thursday’s archived v1 packet is reproduced directly. For Sunday’s archived-v1 comparison only, its creation-time gate is bypassed in the diagnostic runner while retaining the real timestamp and an explicit retrospective label; the production gate and input clocks are never changed. For comparable diversity measurements only, both frozen sets are classified with v2 rules. Classification cannot change membership.

| Measure | Thursday v1 | Thursday v2 | Sunday v1 | Sunday v2 |
|---|---:|---:|---:|---:|
| distinct_primary_theses | 17 | 17 | 14 | 17 |
| distinct_captain_script_combinations | 17 | 17 | 14 | 17 |
| distinct_football_scenarios | 11 | 12 | 11 | 12 |
| unique_captains | 12 | 8 | 9 | 12 |
| average_projected_mean | 63.9906 | 65.7215 | 96.2204 | 96.9652 |
| average_ceiling_proxy | 134.8296 | 135.5841 | 156.9793 | 157.0647 |
| average_objective_score | 137.1889 | 133.9851 | 172.6693 | 169.1661 |
| minimum_mean_fraction | 0.8898 | 0.9278 | 0.8710 | 0.8898 |
| minimum_ceiling_fraction | 0.8735 | 0.8735 | 0.9446 | 0.9446 |
| high_similarity_pairs | 0 | 1 | 4 | 2 |
| average_shared_players | 3.7421 | 3.8211 | 3.7947 | 3.7368 |

| Generated tail | Thursday v1 → v2 | Sunday v1 → v2 |
|---|---|---|
| 1% | 0/2 → 0/2 | 0/2 → 0/2 |
| 5% | 1/6 → 1/6 | 0/6 → 0/6 |
| 10% | 3/12 → 2/12 | 1/11 → 1/11 |

[Machine-readable comparison](artifacts/ai_showdown_selection_packet/policy_v2/comparison/comparison.json) includes both v1/v2 audits, rank sets and the historical bests’ prelock assessments. Native v1 HIGH-similarity counts cannot be compared directly with v2 because the definition changed; the table uses the same v2 rule for both sets.

## 18. Weaknesses, overfitting risks and next decision

- Finite 20-slot competition still omits explicitly nominated captain-side combinations. The favorite QB + 3–3 and underdog WR + 3–3 examples show a failure of this layer despite adequate quality eligibility. The v2 signature intentionally omits captain side; the supplementary combination can lose priority to globally higher-quality novelty.
- Independent seeds can retain several members of one thesis; novelty elsewhere can outweigh an unrepresented important side/archetype. Simple counts cannot establish football value, and this revision has not demonstrated reduced redundancy on Thursday under a consistent definition.
- Average normalized mean/ceiling for representatives still compresses two quality dimensions. Only global top-three seeds have independent preservation; other within-thesis tradeoffs can disappear.
- The 80%/90% quality bands, scenario priority, market thresholds and novelty weights are predeclared heuristics, not empirically calibrated. V2 is not universally a looser floor. Do not optimize them against these two observed winners.
- Classification does not establish win probability. The fallback balanced-script label can occur in uneven constructions with weak directional evidence. Marginal P90 sums do not describe joint lineup ceiling; similarity does not estimate covariance. Ownership/role evidence is incomplete for some unselected rosters.
- All Sunday candidates here contain both QBs. A finalist builder cannot create missing QB structures or repair candidate-generation limitations. Sunday also cannot certify historical prelock generation.
- Two historical slates are too small for acceptance or parameter selection. Any next variant should be declared before scoring a separate validation set, and must test important captain-side coverage and within-thesis alternative retention. AI/manual selector evaluation remains pending.

## Reproduction

Use the saved database source JSONs under `artifacts/ai_showdown_selection_packet/policy_v2/`. Regenerate into a **new** output directory so the archived packets/manifests remain frozen. Exporting calls no solver or actuals reader:

```sh
.venv/bin/python -m scripts.export_ai_showdown_packet \
  artifacts/ai_showdown_selection_packet/policy_v2/ffb8acf8-2e31-414e-81da-417d6d82c584-source.json \
  /tmp/showdown-v2-replay/thursday
.venv/bin/python -m scripts.export_ai_showdown_packet \
  artifacts/ai_showdown_selection_packet/policy_v2/dc21b3ab-c330-487c-bb88-766f9a71f04c-source.json \
  /tmp/showdown-v2-replay/sunday --retrospective
```

After freezing the generated packet, audit with `python -m scripts.audit_ai_showdown_finalists PACKET.json MATCHING_SOURCE.json ACTUALS.json OUTPUT_DIR`. `ACTUALS.json` may contain resolved observations or canonical base `actual_points_by_player`; supplied season/week/slate must match. Optional `--universe-best-score` and `--manual-selection` complete the other regret terms when those independent benchmarks exist. Existing snapshots contain the complete contest fields for the additional field-tail audit.

```sh
.venv/bin/python -m pytest \
  backend/app/tests/product/test_ai_showdown_packet.py \
  backend/app/tests/product/test_ai_showdown_finalist_audit.py \
  backend/app/tests/product/test_showdown_portfolio_selection.py -q
```

The comparison runner and read-only database export scripts are archived under `policy_v2/comparison/` for traceability. Re-running their database extraction is unnecessary for the offline reproduction and can overwrite evidence; use the supplied snapshots.
