# Week 4 Classic discovery, selection and application reconciliation

This audit separates discovery coverage, portfolio policy, and application execution. The saved control `33b94921-8a78-410e-9256-f312e10beb5d` is preserved. On its unchanged numerical frame, the 884-roster risk-legal union raises the proven five-entry selector optimum from **27.714209 to 27.721987**, while known-reference recall at .20 rises from **84/258 to 258/258**. Those are different improvements; neither establishes winning performance.

The existing dynamic thesis policy chooses .15 once denser CIN–JAX constructions make five entries feasible. That removes all 23 Brissett/ARI–NYG alternatives previously eligible at .20 and puts all five primary stacks in one canonical game. The current production branch also overrides an explicit overlap-four request with six. No policy default, model weight, risk cap or threshold was changed here.

A separate, newly captured Sunday preview was completed through the running optimizer API: `00905dcb-d397-4454-99cc-f913fe3345db`, policy **`current_production_205_conservative_sunday_preview_v1`**. It remains **NOT ENTRY READY**: no final Sunday inactive clearance, source/plumbing gaps remain, and Michael Wilson is in all five entries without an automatic exposure approval. The exact replay and saved application readback are verified below. All times include their timezone; UTC snapshots were captured on October 2, corresponding to late October 1 EDT.

## 1. Completed work, reuse and input compatibility

Read and reused:

- [Candidate frontier completeness](WEEK4_CANDIDATE_FRONTIER_COMPLETENESS.md): immutable discovery/admission results, 900 expanded raw rosters, 884 risk-legal rosters, original 205 and historical 286 raw attempts.
- [Dynamic thesis shadow](WEEK4_DYNAMIC_THESIS_PORTFOLIO_SHADOW.md): immutable v3 family definitions, tolerance ladder and exposure policy.
- [Expanded-discovery multi-slate validation](CLASSIC_EXPANDED_DISCOVERY_MULTI_SLATE_VALIDATION.md): an existing completed audit, **not a completed multi-slate certification**. It inventoried 75 saved runs across 40 season/week pairs; historical replay rejected 117/120 reconstructed old rosters, despite exact old-score replay. There is one provisional Week 3 experiment, **zero exact-certified historical slates and zero independent chronological holdout slates**. No aggregate certified performance distribution or production promotion is supported. This task did not recreate or rerun it.
- [Production hardening](WEEK4_CLASSIC_PRODUCTION_HARDENING.md), existing completeness/thesis/optimizer services and their saved solver inputs.

The old fixture is `8b5c114c-b0d2-419e-8f41-bdcbc2674c71`. The comparison uses the current control's frozen frame, not a new source refresh. [Input compatibility](artifacts/classic_reconciliation/20261002T022305Z/input_compatibility.json) records every option and field difference.

| Dimension | Earlier fixture → current control | Material effect on frozen comparison |
| --- | --- | --- |
| Salary/slate/identity | Same original 619-row salary ingest fd87e6d9-95a5-4267-a786-3645a358e21e; same canonical IDs, teams/opponents/salaries and 613 source records | No numerical or identity change |
| Eligible player frame | 466 → 466; full serialized Player values identical | Mean, marginal P90, football context and scoring denominators identical |
| Projection/cutoff | 9701cb0a… / 2026-09-30 01:33:59 UTC → 2659523d… / 2026-10-02 01:25:17 UTC | Run identity and observation time changed; eligible numeric predictions did not |
| Market | Observation timestamps changed in all 466 eligible rows and 538 projected source rows | Totals, spreads and implied totals identical on this frame |
| Ownership | e4bf7feb… → 0fedee65…; 601 source IDs / 458 eligible IDs changed | Numeric ownership identical; partial 458/466 coverage. Soft ownership terms remain disabled |
| Availability/role | Eligible risk classifications and compact role/availability fields identical | Old underlying missing-role evidence remains; pinned feature JSON audited separately |
| Locks/exclusions | No locked/player-excluded IDs; DEN opponent-team exclusion retained | Same lineup eligibility, one TE, DST opponent avoidance, max team 4 / game 5 |
| Normalization | Mean denominator 23.1511147212747; P90 35.29097569836991; selector frontier 5.606632302591656 | One fixed reference for both candidate universes |
| Generation | 205 target, four deterministic QB shards, bundled CBC configuration, minimum uniqueness 2 | Compatible saved discovery and admission reused; no discovery rerun |
| Portfolio | Earlier requested overlap 4 + distinct QBs + max exposure .80; current {} + max exposure 1.00 | Material selection-policy difference; separate labelled shadows |
| Model metadata | Both v4.2-market-corrected, GradientBoostingRegressor seed 42, 9,074 training rows, identical training dataset hash bd9a2732… | Model code hashes fe33410b… → d1f36afd… and serialized artifacts differ; do not claim byte-identical models. Outputs used here are identical |
| Solver/code metadata | Classic scoring/config hashes match. Earlier correlation hash d3f5a835… differs from current f4700514… | Existing disk change concerns Showdown favorite 5–1 evidence labels/conditions. Every saved roster is exactly rescored before reuse; old freeze hashes are not edited |

The compatible numerical frame and admission caps permit reuse. **1,105 saved roster descriptions** (900 expanded plus 205 control, including duplicates) replayed with zero mean, P90 or selector mismatch at 1e-9. Sixteen expanded rosters violate the unchanged per-lineup elevated-risk budget; the deduplicated legal union contains 884 and includes every control roster. No current-control roster adds an unseen expanded roster.

Model-run/artifact/code/dataset lineage is retained in [model_run_lineage.json](artifacts/classic_reconciliation/20261002T023356Z_sunday_preview/model_run_lineage.json). A matching code hash on disk is not proof of the modules loaded by a past service process. The earlier saved selected portfolio actually has overlap four; this audit does not invent why an older service honoured it while the current production call overrides it.

## 2. Requested settings versus effective settings

Trace: `ui/src/App.tsx` portfolio fields and `classicPortfolioParams` → request `params.portfolio_constraints` → saved optimizer parameters and `frozen_solver_snapshot.payload.options` → `analyze_small_field` / `_select_global` → `selected_portfolio.constraints` and overlap matrix. Blank overlap and an unchecked distinct-QB box serialize `{}`. The report prints that requested object; it does not enumerate implicit production constraints.

The current control requested `{}`. The five-entry fixed comparison freezes the **final accepted control policy** (three QBs, two stack types), instead of allowing a changed universe to rerun the policy's automatic quality-budget branches.

| Setting | Current saved request | Effective control solver value | Source / report consequence |
| --- | --- | --- | --- |
| Entry count | num_lineups=5 | Exactly 5 | UI → options.requested_lineups → equality constraint; five selected |
| Maximum overlap | Absent in {} | 6 shared players / 9 | Production branch hardcodes 6. Explicit request 4 is also overridden; real-call regression test confirms it |
| Distinct QB paths | Absent | False; repetition allowed | Forwarded requested flag defaults false. Explicit true reaches solver |
| Minimum QB directions | No user field/value | Baseline 2; final 3 | Third-QB cost .079616788 vs unchanged .10 × 5 = .50 budget; accepted |
| Canonical primary-game cap | Absent | None | Per-roster max_players_per_game=5 is a different constraint; no cap on entries sharing a primary game |
| Thesis allocation | Absent | Maximize summed selector, final ≥2 stack types | No thesis lexicographic reward in production. QB+2 versus QB+3 constructions are not independent football outcomes |
| Global player exposure | max_exposure=1.00 | ≤5/5 before specific caps | Ordinary skills ≤4/5; QBs ≤3/5; eligible elite skills/DST can reach 5/5 |
| Availability exposure | conservative, overrides=[] | Elevated Q ≤2/5; full-role Q ≤3/5; ≤1 elevated per roster; ≤3/5 entries containing any elevated | Unchanged production classifications/risk caps; no user approval inferred |
| Candidate admission caps | Not a selected exposure setting | Elite .90, ordinary .70, elevated .25, full-role .50 of admitted target | Admission and downstream selected exposure remain separate |
| Availability-risk mode | conservative | conservative | Same request/saved/report value; source completeness is a separate question |

Current selection's two-QB optimum is 27.793825871; the accepted three-QB optimum is 27.714209083. Adding the second stack type costs 0. The older requested policy is reconstructed below with overlap four, five distinct QBs and global .80 exposure; it is an explicit offline shadow, not a preference silently re-entered into production. Neither four nor six is presumed the user's new permanent preference.

Confirmed plumbing finding: `classic_small_field.py` uses `max_lineup_overlap=(6 if production_controls else requested_overlap)`; the main selected-portfolio report still says `Constraints: {}`. The UI forwards distinct-QB intent, but the production overlap override can contradict explicit user intent. No production plumbing fix was made here.

## 3. Pure discovery comparison on the identical control frame

Both solves use the same summed selector objective, denominators, legal roster definition, user exclusions, risk classifications, exposure caps, overlap six, at least three QBs, at least two stack types, no canonical-game cap and no individual selector-loss cutoff. Each expanded roster is rescored on the same full eligible player pool. The original saved five are a validated incumbent, a CBC warm start and a selector lower bound in the nested comparison.

The audit CBC solves use zero relative/absolute MIP gaps, one thread, fixed seeds and strict feasibility tolerances. Both LP status and integer solution status must certify optimality; a time-limited incumbent is labelled unproven. The audit makes no global optimality claim over all possible legal NFL rosters—only over the stated candidate universes.

| Universe | Risk-legal candidates | Known .20 recall | Proven selector optimum | Projected points sum | Summed marginal player P90 |
| --- | --- | --- | --- | --- | --- |
| Original control | 205 | 84/258 (32.56%) | 27.714209 | 656.416808 | 1134.184787 |
| Deduplicated original + expanded | 884 | 258/258 (100% of known reference) | 27.721987 | 653.197617 | 1137.689861 |

The objective lift is **0.007777510** (0.0281% of the selector). Projected-point change is -3.219191; summed marginal P90 change is 3.505074. A selector combines several terms, so more points in every component are not implied. The incumbent remains feasible and the expanded proven optimum is not lower. These percentages are **not win-probability changes**. Summed marginal P90 is **not a joint portfolio 90th percentile**.

| Selector gap from common frontier | Original discovery / known legal | Known-reference recall |
| --- | --- | --- |
| 0.05 | 20/38 | 52.63% |
| 0.10 | 49/111 | 44.14% |
| 0.15 | 75/205 | 36.59% |
| 0.20 | 84/258 | 32.56% |
| 0.30 | 98/397 | 24.69% |

Only the prior .05 frontier was exhaustively certified; the other denominators are known-reference lower bounds from recorded discoveries. Full-union recall is 100% against that finite reference by construction, not global completeness. No additional enumeration was run.

## 4. Dynamic tolerance and density mechanism

The existing v3 thesis policy uses global .80 exposure, minimum two QB directions, overlap six and the unchanged risk budgets. It lexicographically maximizes rewarded Pareto construction-thesis coverage, then canonical primary games, then summed selector. Its ladder is .05, .10, .15, .20, then unrestricted, stopping at the first feasible five-entry solve. It does not first maximize broad game coverage over a fixed .20 set.

| Experiment | Tolerance | Status | Selector | Point sum | P90 sum | Canonical primary games | Lexicographic reward/game/selector tuple |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Original old 205 / dynamic | .20 | optimal | 27.687854 | 649.227298 | 1131.943059 | ARI–NYG: 1; CIN–JAX: 4 | 2.0, 2.0, 27.687854307504555 |
| Expanded / fixed tolerance, v3 policy | .20 | optimal | 27.593920 | 651.267709 | 1134.265585 | ARI–NYG: 1; CIN–JAX: 4 | 3.0, 2.0, 27.593919906901597 |
| Expanded / dynamic | .15 | optimal | 27.643977 | 644.618733 | 1121.172577 | CIN–JAX: 5 | 1.0, 1.0, 27.64397737627836 |
| Old 205 + only near-frontier CIN–JAX additions | .15 | optimal | 27.643977 | 644.618733 | 1121.172577 | CIN–JAX: 5 | 1.0, 1.0, 27.64397737627836 |

Original .05/.10/.15 and expanded .05/.10 are proven infeasible under v3's caps. Expanded .15 is feasible and chosen. Adding **only already recorded CIN–JAX candidates inside .15** to the old pool reproduces the identical .15 objective and all-five CIN–JAX result; no new game family is needed to cause tightening. This is a controlled density intervention, not new discovery or threshold tuning.

Tightening .20 → .15 removes these 53 previously individually eligible risk-legal rosters:

| QB direction | Canonical game | Excluded rosters | Cause |
| --- | --- | --- | --- |
| Jacoby Brissett | ARI–NYG | 23 | Selector gap >.15 and ≤.20 |
| Joe Burrow | CIN–JAX | 11 | Selector gap >.15 and ≤.20 |
| Trevor Lawrence | CIN–JAX | 19 | Selector gap >.15 and ≤.20 |

All 23 Brissett constructions in the .20 reference disappear; their best selector gap is about .180867. Remaining removals are 19 Lawrence and 11 Burrow constructions. Construction-family IDs and all excluded roster hashes are in `comparison.json.dynamic_exclusions`. They were not reclassified as injuries or removed by admission.

The expanded fixed-.20 and dynamic-.15 comparison holds the expanded family reward definitions and risk/exposure policy fixed. Fixed .20 selects two games with reward tuple (3, 2, 27.593920); dynamic .15 selects one with (1, 1, 27.643977). The higher final selector in .15 does not outrank coverage under the lexicographic objective. Against the old original dynamic result, summed selector falls 27.687854 → 27.643977 because feasibility/eligibility and the family's rewarded Pareto membership change, not because the scalar fixed-policy nested optimum fell.

Even holding .20 does not justify comparing only the last selector coordinate to the old 27.687854: additional discoveries change Pareto family diagnostics/reward membership, and v3 prioritizes those rewards before selector. The pure scalar comparison in section 3 is the monotonicity test. The original/expanded v3 family dictionaries and policy/cap hashes are frozen separately.

**Product interpretation:** the result follows the implemented first-feasible quality ladder. If the intended objective includes preserving broad football-game alternatives, construction density can defeat that intention. Neither a new threshold to save Brissett nor forcing five weak games is justified here.

## 5. Real portfolio diversity and displaced rosters

Canonical primary game is the sorted team pair: JAX–CIN and CIN–JAX both map to CIN–JAX. A broad directional family is canonical game + canonical QB ID. A construction variant adds pass-catcher count and bring-back count. Different QBs can imply different offensive directions within one game; their outcomes remain dependent. Construction variants and minor player substitutions are not independent broad theses.

| Policy | QB directions / counts | Canonical games / counts | Broad directional families | Construction variants | Max overlap | All-five player core | Selector |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Saved/current original | Jacoby Brissett 1; Joe Burrow 1; Trevor Lawrence 3 | ARI–NYG: 1; CIN–JAX: 4 | 3 | 3 | 6 | Chase Brown, Dolphins | 27.714209 |
| Current effective / full union | Jacoby Brissett 1; Joe Burrow 1; Trevor Lawrence 3 | ARI–NYG: 1; CIN–JAX: 4 | 3 | 3 | 6 | Chase Brown, Parker Washington | 27.721987 |
| Earlier overlap-four/distinct-QB shadow | Jacoby Brissett 1; Joe Burrow 1; Kirk Cousins 1; Patrick Mahomes 1; Trevor Lawrence 1 | ARI–NYG: 1; CIN–JAX: 2; KC–LV: 2 | 5 | 5 | 4 | None | 27.202641 |
| Existing dynamic thesis / union | Joe Burrow 2; Trevor Lawrence 3 | CIN–JAX: 5 | 2 | 3 | 6 | None | 27.643977 |
| Current + canonical game max three shadow | Jacoby Brissett 1; Patrick Mahomes 1; Trevor Lawrence 3 | ARI–NYG: 1; CIN–JAX: 3; KC–LV: 1 | 3 | 3 | 6 | Chase Brown, Parker Washington | 27.559272 |

| Shadow against union current policy | Selector cost | Projected-point cost | P90 cost | Displaced roster hashes | Added roster hashes |
| --- | --- | --- | --- | --- | --- |
| Earlier overlap-four/distinct-QB shadow | 0.519345 | 10.714826 | 12.880517 | 3b5586ab1086, e64826e351e6, 2106a933cc68, f7e82cae4a9a, 67c545e95c44 | f3fd5fb16362, 75573a46575c, bba0223a9407, 1555d6e22a36, 7a506d743808 |
| Existing dynamic thesis / union | 0.078009 | 8.578884 | 16.517284 | 3b5586ab1086, e64826e351e6, 2106a933cc68, f7e82cae4a9a, 67c545e95c44 | f3fd5fb16362, d96520d9512f, bba0223a9407, d31bb0926cb6, d16c976af4b1 |
| Current + canonical game max three shadow | 0.162715 | 0.609050 | 6.865101 | 3b5586ab1086, e64826e351e6, 67c545e95c44 | 75573a46575c, afd5af85a44f, 1f78b6b33bc8 |

The earlier-settings shadow obtains five QBs across **three**, not five, canonical games: Lawrence/Burrow share CIN–JAX and Mahomes/Cousins share KC–LV. The canonical-game max-three shadow introduces Mahomes and removes Burrow; it still repeats the Brown/Washington core in all five. Costs refer to an unchanged finite universe, not independent outcome protection or contest ROI.

The following matrices use the exact row order shown in section 11. Diagonal nine is the roster's own size; only off-diagonal cells measure overlap.

### Saved/current original: pairwise overlap

| Roster hash | 2106a933 | afd5af85 | 67c545e9 | d96520d9 | 7a506d74 |
| --- | --- | --- | --- | --- | --- |
| 2106a933 | 9 | 6 | 5 | 5 | 4 |
| afd5af85 | 6 | 9 | 5 | 5 | 4 |
| 67c545e9 | 5 | 5 | 9 | 5 | 3 |
| d96520d9 | 5 | 5 | 5 | 9 | 3 |
| 7a506d74 | 4 | 4 | 3 | 3 | 9 |

### Current effective / full union: pairwise overlap

| Roster hash | 2106a933 | 3b5586ab | 67c545e9 | e64826e3 | f7e82cae |
| --- | --- | --- | --- | --- | --- |
| 2106a933 | 9 | 6 | 5 | 5 | 3 |
| 3b5586ab | 6 | 9 | 4 | 4 | 2 |
| 67c545e9 | 5 | 4 | 9 | 5 | 4 |
| e64826e3 | 5 | 4 | 5 | 9 | 4 |
| f7e82cae | 3 | 2 | 4 | 4 | 9 |

### Earlier overlap-four/distinct-QB shadow: pairwise overlap

| Roster hash | bba0223a | f3fd5fb1 | 7a506d74 | 75573a46 | 1555d6e2 |
| --- | --- | --- | --- | --- | --- |
| bba0223a | 9 | 4 | 2 | 3 | 3 |
| f3fd5fb1 | 4 | 9 | 3 | 3 | 4 |
| 7a506d74 | 2 | 3 | 9 | 2 | 3 |
| 75573a46 | 3 | 3 | 2 | 9 | 3 |
| 1555d6e2 | 3 | 4 | 3 | 3 | 9 |

### Existing dynamic thesis / union: pairwise overlap

| Roster hash | d16c976a | bba0223a | f3fd5fb1 | d96520d9 | d31bb092 |
| --- | --- | --- | --- | --- | --- |
| d16c976a | 9 | 5 | 4 | 5 | 5 |
| bba0223a | 5 | 9 | 4 | 3 | 5 |
| f3fd5fb1 | 4 | 4 | 9 | 6 | 2 |
| d96520d9 | 5 | 3 | 6 | 9 | 3 |
| d31bb092 | 5 | 5 | 2 | 3 | 9 |

### Current + canonical game max three shadow: pairwise overlap

| Roster hash | 2106a933 | 1f78b6b3 | afd5af85 | f7e82cae | 75573a46 |
| --- | --- | --- | --- | --- | --- |
| 2106a933 | 9 | 6 | 6 | 3 | 6 |
| 1f78b6b3 | 6 | 9 | 6 | 2 | 3 |
| afd5af85 | 6 | 6 | 9 | 4 | 4 |
| f7e82cae | 3 | 2 | 4 | 9 | 3 |
| 75573a46 | 6 | 3 | 4 | 3 | 9 |

### Player and shared-core exposure across policy shadows

| Player | Saved/current original | Current effective / full union | Earlier overlap-four/distinct-QB shadow | Existing dynamic thesis / union | Current + canonical game max three shadow |
| --- | --- | --- | --- | --- | --- |
| Brenton Strange | 1/5 | 1/5 | 1/5 | 3/5 | 2/5 |
| Brian Thomas Jr. | 1/5 | 1/5 | 1/5 | 2/5 | 0/5 |
| Cade Otton | 2/5 | 1/5 | 0/5 | 1/5 | 0/5 |
| Caleb Douglas | 1/5 | 0/5 | 0/5 | 0/5 | 1/5 |
| Chargers | 0/5 | 1/5 | 0/5 | 0/5 | 0/5 |
| Chase Brown | 5/5 | 5/5 | 4/5 | 4/5 | 5/5 |
| Colby Parkinson | 0/5 | 1/5 | 1/5 | 1/5 | 0/5 |
| Derrick Henry | 2/5 | 1/5 | 1/5 | 0/5 | 2/5 |
| Dolphins | 5/5 | 4/5 | 2/5 | 3/5 | 4/5 |
| Elic Ayomanor | 1/5 | 1/5 | 1/5 | 0/5 | 1/5 |
| Ja'Marr Chase | 4/5 | 4/5 | 3/5 | 4/5 | 4/5 |
| Jacoby Brissett | 1/5 | 1/5 | 1/5 | 0/5 | 1/5 |
| Jets | 0/5 | 0/5 | 1/5 | 1/5 | 0/5 |
| Joe Burrow | 1/5 | 1/5 | 1/5 | 2/5 | 0/5 |
| Kenneth Walker III | 1/5 | 1/5 | 3/5 | 2/5 | 1/5 |
| Kirk Cousins | 0/5 | 0/5 | 1/5 | 0/5 | 0/5 |
| Kyren Williams | 4/5 | 3/5 | 4/5 | 4/5 | 3/5 |
| Michael Mayer | 0/5 | 0/5 | 1/5 | 0/5 | 0/5 |
| Michael Wilson | 2/5 | 3/5 | 3/5 | 3/5 | 1/5 |
| Parker Washington | 4/5 | 5/5 | 4/5 | 4/5 | 5/5 |
| Patrick Mahomes | 0/5 | 0/5 | 1/5 | 0/5 | 1/5 |
| Puka Nacua | 2/5 | 2/5 | 2/5 | 2/5 | 2/5 |
| Rhamondre Stevenson | 1/5 | 0/5 | 0/5 | 2/5 | 0/5 |
| Tee Higgins | 1/5 | 1/5 | 1/5 | 2/5 | 0/5 |
| Titans | 0/5 | 0/5 | 2/5 | 1/5 | 1/5 |
| Travis Hunter | 1/5 | 1/5 | 1/5 | 0/5 | 2/5 |
| Travis Kelce | 1/5 | 1/5 | 1/5 | 0/5 | 2/5 |
| Tre Tucker | 0/5 | 0/5 | 1/5 | 0/5 | 0/5 |
| Trevor Lawrence | 3/5 | 3/5 | 1/5 | 3/5 | 3/5 |
| Trey McBride | 1/5 | 1/5 | 1/5 | 0/5 | 1/5 |
| Wan'Dale Robinson | 0/5 | 1/5 | 0/5 | 0/5 | 1/5 |
| Xavier Worthy | 0/5 | 0/5 | 1/5 | 0/5 | 1/5 |
| Zay Flowers | 0/5 | 1/5 | 0/5 | 1/5 | 1/5 |

All pair cores appearing in at least three entries, with canonical player IDs, are retained under each result's `cores_in_at_least_three`. For the unrestricted union solution shown here Brown/Washington appears 5/5; Brown/Chase, Brown/Dolphins and Washington/Chase appear 4/5. These dependencies persist despite three QB directions. Several equally optimal portfolios have identical scores/point/P90 sums but different DST exposure; policy tables and sensitivities identify the exact chosen rosters rather than claiming unique optima.

## 6. Admission versus discovery versus selection

The old 205/300/400/500 admitted pools are reused unchanged, then selected with exactly the current control's final downstream policy. The full risk-legal union uses identical per-lineup eligibility and selected portfolio constraints; admission caps are not reapplied to the union reference.

| Admitted target | Known .20 recall | Proven selector optimum | Cost versus full union | Projected-point sum | P90 sum |
| --- | --- | --- | --- | --- | --- |
| 205 | 74.81% | 27.714209 | 0.007778 | 656.416808 | 1134.184787 |
| 300 | 97.67% | 27.721987 | 0.000000 | 653.197617 | 1137.689861 |
| 400 | 100.00% | 27.721987 | 0.000000 | 653.197617 | 1137.689861 |
| 500 | 100.00% | 27.721987 | 0.000000 | 653.197617 | 1137.689861 |
| Full union 884 | 100% of known reference | 27.721987 | 0.000000 | 653.197617 | 1137.689861 |

The original control's 205 differs from the expanded admission target 205: its .20 recall is 32.56%, while the newly admitted 205's is 74.81%. Both happen to attain the same current-policy optimum. All three larger admitted targets attain the full-union objective here; exact roster identity can differ on ties. The earlier overlap-four/distinct-QB experiment found target 205 infeasible and target 300 below full. Thus its 400 recommendation was policy-specific; this audit does not promote a universal 300 or 400 default.

Attribution within the known 884 legal reference:

| Stage | Historical original discovery → current original admission | Expanded → admitted 205 | Expanded → admitted 300 | Expanded → admitted 400 | Expanded → admitted 500 |
| --- | --- | --- | --- | --- | --- |
| never_discovered | 614 | 0 | 0 | 0 | 0 |
| discovered_not_admitted | 65 | 679 | 584 | 484 | 384 |
| admitted_rejected_by_lineup_quality | 0 | 0 | 0 | 0 | 0 |
| eligible_not_selected | 200 | 200 | 295 | 395 | 495 |
| selected | 5 | 5 | 5 | 5 | 5 |

Historical generation yielded 286 unique raw rosters: 205 admitted + 65 risk-legal admission losses + 16 availability-risk failures. Among .20-competitive known rosters, 174 were never discovered and zero were discovered-but-not-admitted. The table's 614 never-discovered count covers the entire legal reference, not just .20. Risk rejection is a separate stage before the 884 reference; it is not labelled quality rejection. Current fixed selection has no individual selector-loss threshold, so no admission is quality-filtered. Dynamic tightening causes the 53 quality exclusions in section 4. Complete per-roster stage attribution is saved.

Zero player exposure requires mechanical analysis, not a presumption of a bug. Using the same union/current policy, the following proven portfolios require at least one appearance. No projection or player preference was altered:

| Forced player ≥1/5 | Selector cost | Projected-point cost | P90 cost | Mechanism |
| --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | 0.149011 | 3.466443 | 7.222328 | Feasible but displaces the unrestricted portfolio under joint salary, stack, overlap and exposure constraints |
| Justin Jefferson | 0.159414 | 5.577318 | 5.577318 | Feasible but displaces the unrestricted portfolio under joint salary, stack, overlap and exposure constraints |
| Bucky Irving | 0.063719 | 2.791758 | 1.129677 | Feasible but displaces the unrestricted portfolio under joint salary, stack, overlap and exposure constraints |
| Brock Bowers | 0.114497 | 2.241392 | 3.621359 | Feasible but displaces the unrestricted portfolio under joint salary, stack, overlap and exposure constraints |
| Lamar Jackson | 0.307322 | 4.389664 | 6.447807 | Feasible but displaces the unrestricted portfolio under joint salary, stack, overlap and exposure constraints |

Bucky Irving, Bowers and Jefferson were absent from the historical original raw discovery; JSN's original few rosters were weak. Expanded forced-player discovery adds legal alternatives, and these forced portfolio sensitivities remain below the best joint selector. That distinguishes missed competitive discovery from an eligible alternative losing selection; it does not establish a calibrated causal reason for every model projection. The forced artifacts contain the exact displaced/selected rosters.

## 7. Separate fresh Sunday source and role audit

Fresh capture occurred only after `comparison.json` was frozen. [Capture manifest](artifacts/classic_reconciliation/20261002T023356Z_sunday_preview/capture_manifest.json) ties the new observations to that comparison hash, source URIs, immutable raw paths, content checksums and normal ingest runs. HTTP success means a page was captured, not that every cell is current or every player is cleared.

Captured 84 public sources: native DK salary, all 24 slate clubs' roster/depth/injury pages, eight relevant club news pages, NFL injury information, the Bengals' week-specific practice report and market context. Existing source services also captured nflreadpy current-week roster/injury/depth evidence and **only prior Weeks 1–3** stats/snaps. The depth provider response contains 590,235 historical timestamped rows; that count is not 590,235 current-week facts. QB resolution uses the established current-depth helper plus provisional club expectations.

The official native DK lobby identified 12-game Sunday Main draft group **154078**. New salary snapshot `8ff049a8-65b6-51c8-b737-bf75be5c03f1` / ingest `b31b6816-92fb-57f3-bf44-3b57a42c89d2` has 629 rows versus 619, ten added native IDs, no removals and no salary-price changes. There are 39 status changes and two source team/game corrections: Dare Ogunbowale LV → HOU and Mitch Tinsley HOU → CIN. Eighteen salary records remain in the identity queue, not silently name-matched. The roster ingest has one additional unresolved record; prior snap ingest reports 148 unresolved rows. Those warnings remain explicit.

Native source IDs resolve where available. Depth cells require an unambiguous team + position + normalized-name/alias identity; 32 ambiguous/unmatched cells are preserved for review, including multi-player chart cells. The source audit joins prior-week measured stats through canonical GSIS aliases, then checks team and position. It never joins by raw display name alone.

Twelve Sunday-only market rows were refreshed through the existing pipeline at 2026-10-02 02:37:35 UTC. Source is nflverse schedule lines, not a claimed independent executable DK sportsbook quote. The captured DK market page is separate raw evidence. Compared with the control, 87 common eligible players have changed totals; no Thursday market or current Week 4 result was used to tune Sunday decisions.

The normal context service persisted 316 explicit depth expectation labels, no numerical routes/snaps/targets/carries and no authored availability/start probabilities. Expected QB service wrote 24 provisional/inferred rows. Twenty-one eligible club first-string overrides were available. GB's jersey-prefixed cell and HOU's absent HTML table use the existing provider helper. TB is a documented conflict: club depth lists Baker Mayfield first, but salary status excludes him; the established eligible resolver retained Jalon Daniels. This is not official starter confirmation.

The first starter attempt failed on that conflict; an invalid context field request failed before writes; projection training then blocked stale zero Week 3 outcomes. Failed requests/logs remain. The completed refresh reuses the corrected context request and rebuilds Weeks 3 and 4 through the existing feature pipeline after prior-week ingests. It trains the unchanged v4.2 model recipe with 9,844 rows instead of 9,074. There was no new opportunity model, manual adjustment or threshold tuning.

Fresh projection is `cf77fd72-5071-4dda-9e84-5529754f78e5`, cutoff **2026-10-02 02:46:29.725133 UTC** (October 1, 22:46:29 EDT): 389 prediction rows, 332 eligible solver players versus the old 538 / 466. Every common eligible mean/P90 changes after the normal fresh rebuild. Source rows are 611 resolved salary identities versus the control's 613 records. The fresh preview is a different input/model-output frame and cannot be interpreted as a pure discovery gain.

### Selected and major-dependency evidence

Every skill/QB below has a captured club unofficial depth-chart first-string expectation. That is affirmative expected-role evidence, **not** final game availability. For DSTs the composite team model is separate; no individual player target/carry claim applies. All selected players have null official availability status; roster ACT and modeled probability 1.0 do not supply independent confirmation.

The measured-usage column shows captured **prior-week facts**, with native-ID lineage. Lagged/model columns come from pinned feature JSON; reconciliation may overwrite fields named `targets_mean_3`/`carries_mean_3` with allocations. Consequently those feature values are labelled **lagged/reconciled model proxies**, not raw measured averages. A missing prior-week row is shown missing, never zero. No current Sunday usage is measured yet.

| Player | Preview exposure | Salary status | Current availability evidence | Expected role | Prior measured usage | Lagged/reconciled model proxy |
| --- | --- | --- | --- | --- | --- | --- |
| Caleb Douglas | 1/5 | Q | Did Not Participate In Practice; game report status missing | club first-string expectation | W1: tgt 7, rush 0; W2: tgt 3, rush 0 | targets 3.85; RB carries unavailable; lagged snap share 0.89 |
| Chase Brown | 4/5 | no designation | No mapped current practice row; final status missing | club first-string expectation | W1: tgt 6, rush 16; W2: tgt 5, rush 20; W3: tgt 2, rush 13 | targets 4.01; RB carries 15.72; lagged snap share 0.66 |
| Malik Washington | 1/5 | no designation | No mapped current practice row; final status missing | club first-string expectation | W1: tgt 8, rush 0; W2: tgt 5, rush 1; W3: tgt 10, rush 2 | targets 6.49; RB carries unavailable; lagged snap share 0.86 |
| Tee Higgins | 4/5 | no designation | No mapped current practice row; final status missing | club first-string expectation | W1: tgt 6, rush 0; W2: tgt 10, rush 0; W3: tgt 7, rush 0 | targets 7.04; RB carries unavailable; lagged snap share 0.79 |
| Dolphins | 3/5 | no designation | No mapped current practice row; final status missing | composite DST | Composite DST; player usage N/A | targets unavailable; RB carries unavailable; lagged snap share unavailable |
| Kyren Williams | 1/5 | no designation | No mapped current practice row; final status missing | club first-string expectation | W1: tgt 3, rush 11; W2: tgt 2, rush 12; W3: tgt 7, rush 15 | targets 2.68; RB carries 11.57; lagged snap share 0.63 |
| Kenneth Walker III | 4/5 | no designation | No mapped current practice row; final status missing | club first-string expectation | W1: tgt 6, rush 23; W2: tgt 10, rush 24; W3: tgt 2, rush 18 | targets 4.98; RB carries 18.26; lagged snap share 0.74 |
| Parker Washington | 4/5 | no designation | No mapped current practice row; final status missing | club first-string expectation | W1: tgt 6, rush 0; W2: tgt 12, rush 0; W3: tgt 5, rush 0 | targets 8.12; RB carries unavailable; lagged snap share 0.74 |
| James Cook III | 1/5 | no designation | No mapped current practice row; final status missing | club first-string expectation | W1: tgt 4, rush 13; W2: tgt 3, rush 21; W3: tgt 1, rush 24 | targets 2.30; RB carries 16.44; lagged snap share 0.71 |
| Javonte Williams | 1/5 | no designation | No mapped current practice row; final status missing | club first-string expectation | W1: tgt 5, rush 12; W2: tgt 4, rush 12; W3: tgt 3, rush 19 | targets 3.72; RB carries 12.49; lagged snap share 0.76 |
| Puka Nacua | 0/5 | Q | No mapped current practice row; final status missing | club first-string expectation | W1: tgt 9, rush 0 | targets 8.31; RB carries unavailable; lagged snap share 0.71 |
| Trevor Lawrence | 3/5 | no designation | No mapped current practice row; final status missing | club first-string expectation | W1: att 23, rush 2; W2: att 29, rush 2; W3: att 29, rush 4 | targets unavailable; RB carries unavailable; lagged snap share 0.94 |
| Michael Wilson | 5/5 | no designation | No mapped current practice row; final status missing | club first-string expectation | W1: tgt 7, rush 0; W2: tgt 7, rush 0; W3: tgt 17, rush 0 | targets 9.12; RB carries unavailable; lagged snap share 0.91 |
| Brenton Strange | 4/5 | no designation | No mapped current practice row; final status missing | club first-string expectation | W1: tgt 3, rush 0; W2: tgt 2, rush 0; W3: tgt 5, rush 0 | targets 3.61; RB carries unavailable; lagged snap share 0.76 |
| Trey McBride | 1/5 | no designation | No mapped current practice row; final status missing | club first-string expectation | W1: tgt 13, rush 0; W2: tgt 10, rush 0; W3: tgt 11, rush 0 | targets 10.92; RB carries unavailable; lagged snap share 0.86 |
| Jakobi Meyers | 2/5 | Q | Limited Participation in Practice; game report status missing | club first-string expectation | W1: tgt 2, rush 1; W2: tgt 1, rush 0; W3: tgt 8, rush 0 | targets 3.84; RB carries unavailable; lagged snap share 0.79 |
| Jacoby Brissett | 1/5 | no designation | No mapped current practice row; final status missing | club first-string expectation | W1: att 37, rush 6; W2: att 28, rush 1; W3: att 52, rush 4 | targets unavailable; RB carries unavailable; lagged snap share 1.00 |
| Joe Burrow | 1/5 | no designation | No mapped current practice row; final status missing | club first-string expectation | W1: att 35, rush 5; W2: att 31, rush 1; W3: att 37, rush 2 | targets unavailable; RB carries unavailable; lagged snap share 1.00 |
| Ja'Marr Chase | 2/5 | no designation | No mapped current practice row; final status missing | club first-string expectation | W1: tgt 4, rush 0; W2: tgt 9, rush 0; W3: tgt 12, rush 0 | targets 7.49; RB carries unavailable; lagged snap share 0.94 |
| Rams | 2/5 | no designation | No mapped current practice row; final status missing | composite DST | Composite DST; player usage N/A | targets unavailable; RB carries unavailable; lagged snap share unavailable |

The complete six-way separation—official evidence, expected role, measured prior usage, historical proxies, model-inferred outputs and missing fields—is in [source_role_audit_v2.json](artifacts/classic_reconciliation/20261002T023356Z_sunday_preview/source_role_audit_v2.json), including mean/P90, exact evidence URLs/snapshot IDs and consumed fields. Its first extraction (`source_role_audit.json`) incorrectly looked for legacy `recent_team` rather than the provider's `team` column and therefore reported empty measured-usage joins; it is preserved as a failed audit extraction and **must not be used**. V2 corrects the team-qualified native-ID join without changing model or source records.

For every selected player, current numeric expected routes/snaps/targets/carries are missing. Puka has only a captured Week 1 stat row; Weeks 2–3 are absent, not zero. Model allocations use lagged team-volume reconciliation/salary fallbacks; they are neither coach-authored workloads nor current measured facts. `outside_low_salary_gate` is an eligibility retention rule and contributes no affirmative role verification.

Fresh practice source says Caleb Douglas did not participate (ankle) and Jakobi Meyers was limited (thumb); game-status fields are missing. Both remain salary Q. Their captured practice facts are nested in context evidence, but the frozen optimizer's top-level `practice_participation`, `practice_observed_at` and expected-workload fields remain null. **Capture is verified; consumption by the existing risk classifier is not.** Existing classifications/caps were retained rather than claiming the newly captured evidence cleared them. Puka remains Q despite the [Rams' news page](https://www.therams.com/news/) carrying an expectation of play. The [Bengals' week-specific practice report](https://www.bengals.com/news/jaguars-bengals-injury-report-week-4-2026) supplies dated practice evidence for the CIN core, not final Sunday inactive clearance.

The application's Availability evidence PASS only checks its defined dated-questionable criterion. It does not certify these full source-to-consumption or final clearance requirements. The preview's entry_ready is false, ownership is still partial (329/332 eligible), 100% Michael Wilson requires review under existing reporting, and no exposure was approved in this task.

### LAR zero opportunity: cause and refreshed result

The old pinned feature run contains `team_targets_mean_3=0` / `team_carries_mean_3=0` with both availability flags **false** for LAR. Individual history exists for core players, but team-volume history was unavailable. Canonical projection input initialization uses zero sentinels with false flags; allocation respects those flags and remains unavailable. Team report aggregation reads the numeric feature and omits the availability flags, exposing 0.00 with empty allocations.

Therefore this is **an input-evidence gap plus a reporting semantics defect**, not a sum-of-player-allocation arithmetic error and not measured zero NFL opportunity. The compact optimizer freeze omits those availability flags, so the investigation uses the exact feature_run_id pinned through the saved projection/model run; it does not substitute latest mutable features.

After the normal prior-week refresh, the new pinned LAR feature flags are true: team targets **35.333333**, RB carries **23.666667**. Allocations are available (e.g. Puka model targets 8.314137; Kyren targets 2.678935 / carries 11.573543). LAR report role coverage rises .7222 → .9286; CJ Daniels still lacks measured-role evidence. Current expected pass attempts, rush attempts, routes and red-zone volume remain unavailable. The stale evidence gap is repaired in the new frame through the established pipeline; the old freeze and the general missing-value display defect remain preserved.

## 8. Brown and Dolphins exposure sensitivities on one common frame

All six solves below use the same 884-roster union, current final policy, scoring and availability rules. Unrestricted means a selected cap of five entries, not unconditional approval. Positive cost means the restricted portfolio gives up the stated model quantity; the quantities do not estimate contest win probabilities.

| Sensitivity | Selected Brown / Dolphins | Selector | Selector cost | Projected-point cost | P90 cost | All-five core |
| --- | --- | --- | --- | --- | --- | --- |
| chase_brown_max5 | 5/5; 3/5 | 27.721987 | 0.000000 | 0.000000 | 0.000000 | Chase Brown, Parker Washington |
| chase_brown_max4 | 4/5; 2/5 | 27.691778 | 0.030209 | 4.755744 | 5.891054 | Parker Washington |
| chase_brown_max3 | 3/5; 4/5 | 27.613720 | 0.108266 | 4.518148 | 17.997381 | Kyren Williams |
| dolphins_dst_max5 | 5/5; 3/5 | 27.721987 | 0.000000 | 0.000000 | 0.000000 | Chase Brown, Parker Washington |
| dolphins_dst_max4 | 5/5; 3/5 | 27.721987 | 0.000000 | 0.000000 | 0.000000 | Chase Brown, Parker Washington |
| dolphins_dst_max3 | 5/5; 3/5 | 27.721987 | 0.000000 | 0.000000 | 0.000000 | Chase Brown, Parker Washington |

| Sensitivity vs same unrestricted solve | Displaced hashes | Added hashes | Net player appearances / replacements |
| --- | --- | --- | --- |
| chase_brown_max4 | 67c545e95c44 | bba0223a9407 | Brenton Strange +1; Cade Otton -1; Chase Brown -1; Dolphins -1; Jets +1; Kyren Williams +1 |
| chase_brown_max3 | f3fd5fb16362, 3b5586ab1086, f7e82cae4a9a, 67c545e95c44 | 8ec71afb44bb, bba0223a9407, afd5af85a44f, 7a506d743808 | Brenton Strange +1; Cade Otton -1; Caleb Douglas +1; Chargers -1; Chase Brown -2; Colby Parkinson -1; Derrick Henry +1; Dolphins +1; Jets +1; Kyren Williams +2; Michael Wilson -1; Parker Washington -1; Rhamondre Stevenson +1; Titans -1; Travis Hunter +1; Trey McBride +1; Wan'Dale Robinson -1; Zay Flowers -1 |
| dolphins_dst_max4 | 3b5586ab1086 | 1f78b6b33bc8 | Chargers -1; Titans +1 |
| dolphins_dst_max3 | 3b5586ab1086 | 1f78b6b33bc8 | Chargers -1; Titans +1 |

Brown max-four replaces an appearance with Kyren among broader salary/stack rearrangements; max-three raises Kyren to all five and shifts several other players. Core dependence changes rather than vanishing. The three Dolphins sensitivities all attain the same optimum and select the same three-Dolphins/one-Chargers/one-Titans solution. This costs zero on this known expanded universe; it does not retroactively approve or condemn the control's 5/5 Dolphins exposure.

The section-3 unrestricted union solve is an equally optimal four-Dolphins/one-Chargers roster set, while the unrestricted exposure reference here selects three Dolphins, one Chargers and one Titans. Both have identical selector/point/P90 sums. This tie explains the different exposure representatives and why a max-three cap has no objective cost. Exact rosters, overlap matrices and exposure counts are saved for each solve. All sensitivities retain four primary CIN–JAX stacks and one ARI–NYG stack; their maximum overlap remains six. No result is an automatic exposure approval.

## 9. Reviewed fresh preview and execution path

**Named policy:** `current_production_205_conservative_sunday_preview_v1`. It uses the normal current 205-candidate production architecture, conservative availability risk, five entries, global max exposure 1.00 before specific caps, default six overlap, accepted ≥3 QB directions / ≥2 stack types, no distinct-QB requirement, no canonical-game portfolio cap, no individual quality-loss filter, no dynamic thesis lexicographic objective, the control's DEN exclusion and empty locks/overrides.

The new optimizer request carries that name and the control ID as diagnostic labels. They are audit metadata, not a new registered strategy. [application_request.json](artifacts/classic_reconciliation/20261002T023356Z_sunday_preview/application_request.json) explicitly pins the fresh projection and cutoff. It was sent to the already-running `POST http://127.0.0.1:8000/api/optimizer/run`; saved run ID **00905dcb-d397-4454-99cc-f913fe3345db**. The standard `GET /api/optimizer/results/{id}` returns the same immutable snapshot, full candidate universe and selected ranks. No service was restarted.

This intentionally uses the current application's policy instead of claiming the offline 884 universe or thesis selector has been promoted. The normal button does not substitute an unmentioned broader research policy.

| Fresh preview metric | Verified value |
| --- | --- |
| Projection / cutoff | cf77fd72-5071-4dda-9e84-5529754f78e5 / 2026-10-02T02:46:29.725133+00:00 |
| Candidate count / candidate digest | 205 / 77a032a2cd945920430ea628c930c32b765600802ed50ad10a18c2d4fb972fe3 |
| Input contract digest | b53e4802a733c6453f2c9f39c695c9482014d466d475c9e6bf192837f773024b |
| Selected ranks | [2, 3, 5, 48, 83] |
| Proven portfolio selector | 27.638089 |
| Projected-point sum / marginal P90 sum | 650.231804 / 1145.931797 |
| QBs / canonical primary games | Lawrence 3; Burrow 1; Brissett 1 / CIN–JAX 4; ARI–NYG 1 |
| Broad directional / construction families | 3 / 4 |
| Maximum overlap / all-five core | 6 / Michael Wilson |
| Readback and offline replay | Same snapshot, candidates, effective policy and exact five canonical rosters; proven optimal within saved 205 |
| Entry readiness | False; source/role gaps and approval-dependent 100% core remain |

The exact existing, read-only replay command is:

```sh
cd /Users/wones/git/football_26
PYTHONHASHSEED=0 .venv/bin/python -m scripts.run_classic_reconciliation_preview \
  artifacts/classic_reconciliation/20261002T023356Z_sunday_preview --replay
```

It performs no fetch, projection rebuild or optimizer write. It verifies snapshot code/input hashes, rescores every saved candidate, validates the five under the effective policy and proves the saved objective again. [execution_verification.json](artifacts/classic_reconciliation/20261002T023356Z_sunday_preview/execution_verification.json) records the API run/readback and [offline_replay_verification.json](artifacts/classic_reconciliation/20261002T023356Z_sunday_preview/offline_replay_verification.json) confirms a second replay selected the exact same rosters.

To retrieve the same application report without rerunning a decision:

```sh
curl --fail http://127.0.0.1:8000/api/optimizer/results/00905dcb-d397-4454-99cc-f913fe3345db
```

The actual creation command already executed was:

```sh
PYTHONHASHSEED=0 .venv/bin/python -m scripts.run_classic_reconciliation_preview \
  artifacts/classic_reconciliation/20261002T023356Z_sunday_preview \
  --control artifacts/classic_reconciliation/20261002T022305Z/control_inputs.json
```

It refuses to overwrite the completed preview. Do not remove that guard or rerun source creation into the saved directory. A new prospective preview requires a new timestamped capture; exact decision reproduction uses `--replay` or the saved GET.

**UI distinction:** the current checked-in Operations **Run Optimizer** path (`App.tsx:1223`) reconciles salaries, builds features, resolves expected QBs and rebuilds projections before posting to the same optimizer endpoint. It rejects an older pinned projection selection. A new click therefore creates fresh input/decision IDs; it is **not** a replay of this freeze. It keeps the current 205 architecture and default production overlap policy; explicit overlap-four still encounters the confirmed override. The API backend execution/readback and offline replay were verified; no assertion is made that this exact request was driven by a browser click or that the loaded frontend matches every newer on-disk change.

| Layer | Status |
| --- | --- |
| Expanded discovery / admission / dynamic thesis / canonical-game and exposure shadows | Existing offline research, reused; new fixed selection audit proven and saved |
| New reconciliation scripts and source extraction | Tested local task scripts; no production endpoint or public interface change |
| Sunday evidence refresh | Established source capture/ingest/context/starter/feature/prediction services; lineage persisted |
| Current 205 conservative preview | Actually completed in running optimizer API, normal saved result/report, exact readback verified |
| UI Run Optimizer orchestration | Checked-in path traced; fresh rebuild behaviour documented; no browser-execution equivalence claimed |
| Expanded or thesis default promotion | Not performed; certification/holdout requirements remain unmet |

## 10. Preservation, tests and reproducibility limits

Control before/after full-record digests both equal `334923b4d80f30d96dc2115a69760be7488ac00f2dbc7edbba421cc7599a231e`, including after the fresh application preview. Earlier expanded/thesis/control input files still match their saved SHA-256 values. No projection/P90/ownership/correlation/selector/risk/thesis parameter was tuned. Fresh numerical output changes result from the authorized normal new-source rebuild. No Thursday actuals were used: captured weekly stats/snaps contain only Weeks 1–3. Showdown captain-credibility research remains separate.

13 new targeted reconciliation tests pass, including the real production overlap/distinct-QB call, canonical games, score equality, incumbent preservation, fixed-policy superset monotonicity, rejection of unproven CBC status, dynamic exclusions/density, stage attribution, unavailable versus measured zero, immutable historical inputs, saved preview/readback/replay identity and prior-week-only fresh evidence. The final targeted suite passed **157 tests** across reconciliation, Classic small-field, thesis, prospective, optimizer mode and questionable-player preferences; its output is `final_tests.txt` in the preview bundle.

A broader 132-test run had **129 pass / 3 fail**. All three failures are legacy frozen-code assertions/guards expecting `lineup_correlation_scoring.py` hash d3f5a835… while the pre-existing working-tree Showdown change has f4700514…. They are documented, not repaired by altering historical freezes. The current control already records f4700514… and its exact scoring replay succeeds. No full-suite green claim is made.

The four added task scripts, this report, new evidence/tests and README/release-note links are the task changes; no production service code/settings changed. Existing unrelated working-tree edits were preserved. Immutable raw captures and derived decision artifacts are hashed in the final audit manifest. Failed refresh/extraction logs are retained so the successful path is not confused with an unexplained overwrite.

To re-run the frozen selection audit to a **new** output location (do not overwrite the saved comparison):

```sh
mkdir -p /tmp/classic-reconciliation-replay
PYTHONHASHSEED=0 .venv/bin/python -m scripts.reconcile_classic_discovery_selection \
  --control artifacts/classic_reconciliation/20261002T022305Z/control_inputs.json \
  --expanded artifacts/candidate_completeness/week4-8b5c114c-reviewed.json \
  --old-inputs artifacts/week4-thesis-frozen-analysis-inputs-8b5c114c.json \
  --thesis artifacts/week4-dynamic-thesis-shadow-8b5c114c.json \
  --output /tmp/classic-reconciliation-replay/comparison.json
```

Create the new parent directory first. Solver logs are written alongside the new output; the existing freezes are read-only inputs. The script asserts numerical compatibility and preserved admission caps before selecting, and refuses an existing output. Discovery generation is not restarted by that command.

Targeted test command:

```sh
PYTHONHASHSEED=0 .venv/bin/python -m pytest \
  backend/app/tests/product/test_classic_reconciliation.py -q
```

Evidence bundles:

- [Frozen comparison](artifacts/classic_reconciliation/20261002T022305Z/comparison.json), strict solver logs, requested/effective policies, all legal roster IDs/scores, recall, family diagnostics, stage attribution, overlaps and exposure caps.
- [Forced portfolio diagnostics](artifacts/classic_reconciliation/20261002T022305Z/forced_portfolios.json).
- [Fresh capture manifest](artifacts/classic_reconciliation/20261002T023356Z_sunday_preview/capture_manifest.json), [refresh lineage](artifacts/classic_reconciliation/20261002T023356Z_sunday_preview/refresh_lineage.json), [source/role audit v2](artifacts/classic_reconciliation/20261002T023356Z_sunday_preview/source_role_audit_v2.json).
- [Saved application preview](artifacts/classic_reconciliation/20261002T023356Z_sunday_preview/preview.json), request, readback, pinned projection features/model lineage, execution verification and offline replay.
- [Final content manifest](artifacts/classic_reconciliation/audit_manifest.json), including reproduction script hashes and untouched historical input hashes.

## 11. Exact selected rosters and displacement catalogue

Roster hash prefixes below identify the full canonical sorted-player-ID digest in the artifacts. Ranks are local to the stated universe, so rank alone is not a cross-universe identity. Mean/P90 below are summed marginal projections. Full nine-player member lists make the displaced rosters reviewable; canonical IDs and legal roster metadata remain in JSON.

### Saved/current original

| Local rank / roster hash | Primary game / QB | Mean | P90 sum | Selector | Nine players |
| --- | --- | --- | --- | --- | --- |
| 1 / 2106a933cc68 | CIN–JAX / Trevor Lawrence | 133.324782 | 225.604499 | 5.606632 | Chase Brown, Dolphins, Kyren Williams, Travis Kelce, Parker Washington, Puka Nacua, Trevor Lawrence, Travis Hunter, Ja'Marr Chase |
| 3 / afd5af85a44f | CIN–JAX / Trevor Lawrence | 130.237270 | 226.944249 | 5.586228 | Caleb Douglas, Chase Brown, Dolphins, Kyren Williams, Derrick Henry, Parker Washington, Trevor Lawrence, Brenton Strange, Ja'Marr Chase |
| 6 / 67c545e95c44 | CIN–JAX / Trevor Lawrence | 129.358762 | 228.241592 | 5.578487 | Chase Brown, Dolphins, Cade Otton, Brian Thomas Jr., Kenneth Walker III, Parker Washington, Trevor Lawrence, Michael Wilson, Ja'Marr Chase |
| 49 / d96520d9512f | CIN–JAX / Joe Burrow | 129.673010 | 222.068599 | 5.517096 | Chase Brown, Tee Higgins, Dolphins, Cade Otton, Kyren Williams, Parker Washington, Rhamondre Stevenson, Joe Burrow, Ja'Marr Chase |
| 83 / 7a506d743808 | ARI–NYG / Jacoby Brissett | 133.822985 | 231.325848 | 5.425765 | Chase Brown, Dolphins, Elic Ayomanor, Kyren Williams, Derrick Henry, Puka Nacua, Michael Wilson, Trey McBride, Jacoby Brissett |

Exact row-order roster hashes: 2106a933cc68, afd5af85a44f, 67c545e95c44, d96520d9512f, 7a506d743808.

### Current effective / full union

| Local rank / roster hash | Primary game / QB | Mean | P90 sum | Selector | Nine players |
| --- | --- | --- | --- | --- | --- |
| 1 / 2106a933cc68 | CIN–JAX / Trevor Lawrence | 133.324782 | 225.604499 | 5.606632 | Chase Brown, Dolphins, Kyren Williams, Travis Kelce, Parker Washington, Puka Nacua, Trevor Lawrence, Travis Hunter, Ja'Marr Chase |
| 3 / 3b5586ab1086 | CIN–JAX / Trevor Lawrence | 130.463208 | 228.607243 | 5.593442 | Chase Brown, Chargers, Kyren Williams, Parker Washington, Puka Nacua, Trevor Lawrence, Wan'Dale Robinson, Brenton Strange, Ja'Marr Chase |
| 11 / 67c545e95c44 | CIN–JAX / Trevor Lawrence | 129.358762 | 228.241592 | 5.578487 | Chase Brown, Dolphins, Cade Otton, Brian Thomas Jr., Kenneth Walker III, Parker Washington, Trevor Lawrence, Michael Wilson, Ja'Marr Chase |
| 96 / e64826e351e6 | CIN–JAX / Joe Burrow | 128.117752 | 224.420582 | 5.528690 | Chase Brown, Tee Higgins, Dolphins, Kyren Williams, Parker Washington, Colby Parkinson, Michael Wilson, Joe Burrow, Ja'Marr Chase |
| 244 / f7e82cae4a9a | ARI–NYG / Jacoby Brissett | 131.933115 | 230.815945 | 5.414734 | Chase Brown, Dolphins, Elic Ayomanor, Derrick Henry, Parker Washington, Michael Wilson, Trey McBride, Jacoby Brissett, Zay Flowers |

Exact row-order roster hashes: 2106a933cc68, 3b5586ab1086, 67c545e95c44, e64826e351e6, f7e82cae4a9a.

### Earlier overlap-four/distinct-QB shadow

| Local rank / roster hash | Primary game / QB | Mean | P90 sum | Selector | Nine players |
| --- | --- | --- | --- | --- | --- |
| 61 / bba0223a9407 | CIN–JAX / Trevor Lawrence | 124.603017 | 222.350538 | 5.548279 | Brian Thomas Jr., Kyren Williams, Kenneth Walker III, Parker Washington, Jets, Trevor Lawrence, Michael Wilson, Brenton Strange, Ja'Marr Chase |
| 97 / f3fd5fb16362 | CIN–JAX / Joe Burrow | 128.117752 | 224.420582 | 5.528690 | Chase Brown, Tee Higgins, Kyren Williams, Parker Washington, Colby Parkinson, Titans, Michael Wilson, Joe Burrow, Ja'Marr Chase |
| 230 / 7a506d743808 | ARI–NYG / Jacoby Brissett | 133.822985 | 231.325848 | 5.425765 | Chase Brown, Dolphins, Elic Ayomanor, Kyren Williams, Derrick Henry, Puka Nacua, Michael Wilson, Trey McBride, Jacoby Brissett |
| 325 / 75573a46575c | KC–LV / Patrick Mahomes | 126.630194 | 218.852823 | 5.358235 | Chase Brown, Dolphins, Patrick Mahomes, Kenneth Walker III, Travis Kelce, Parker Washington, Xavier Worthy, Travis Hunter, Ja'Marr Chase |
| 332 / 1555d6e22a36 | KC–LV / Kirk Cousins | 129.308843 | 227.859553 | 5.341671 | Chase Brown, Michael Mayer, Kyren Williams, Kirk Cousins, Kenneth Walker III, Parker Washington, Titans, Puka Nacua, Tre Tucker |

Exact row-order roster hashes: bba0223a9407, f3fd5fb16362, 7a506d743808, 75573a46575c, 1555d6e22a36.

### Existing dynamic thesis / union

| Local rank / roster hash | Primary game / QB | Mean | P90 sum | Selector | Nine players |
| --- | --- | --- | --- | --- | --- |
| 9 / d16c976af4b1 | CIN–JAX / Trevor Lawrence | 131.563826 | 226.262669 | 5.579999 | Chase Brown, Dolphins, Parker Washington, Puka Nacua, Trevor Lawrence, Rhamondre Stevenson, Michael Wilson, Brenton Strange, Ja'Marr Chase |
| 61 / bba0223a9407 | CIN–JAX / Trevor Lawrence | 124.603017 | 222.350538 | 5.548279 | Brian Thomas Jr., Kyren Williams, Kenneth Walker III, Parker Washington, Jets, Trevor Lawrence, Michael Wilson, Brenton Strange, Ja'Marr Chase |
| 97 / f3fd5fb16362 | CIN–JAX / Joe Burrow | 128.117752 | 224.420582 | 5.528690 | Chase Brown, Tee Higgins, Kyren Williams, Parker Washington, Colby Parkinson, Titans, Michael Wilson, Joe Burrow, Ja'Marr Chase |
| 107 / d96520d9512f | CIN–JAX / Joe Burrow | 129.673010 | 222.068599 | 5.517096 | Chase Brown, Tee Higgins, Dolphins, Cade Otton, Kyren Williams, Parker Washington, Rhamondre Stevenson, Joe Burrow, Ja'Marr Chase |
| 163 / d31bb0926cb6 | CIN–JAX / Trevor Lawrence | 130.661129 | 226.070188 | 5.469913 | Chase Brown, Dolphins, Brian Thomas Jr., Kyren Williams, Kenneth Walker III, Puka Nacua, Trevor Lawrence, Brenton Strange, Zay Flowers |

Exact row-order roster hashes: d16c976af4b1, bba0223a9407, f3fd5fb16362, d96520d9512f, d31bb0926cb6.

### Current + canonical game max three shadow

| Local rank / roster hash | Primary game / QB | Mean | P90 sum | Selector | Nine players |
| --- | --- | --- | --- | --- | --- |
| 1 / 2106a933cc68 | CIN–JAX / Trevor Lawrence | 133.324782 | 225.604499 | 5.606632 | Chase Brown, Dolphins, Kyren Williams, Travis Kelce, Parker Washington, Puka Nacua, Trevor Lawrence, Travis Hunter, Ja'Marr Chase |
| 4 / 1f78b6b33bc8 | CIN–JAX / Trevor Lawrence | 130.463208 | 228.607243 | 5.593442 | Chase Brown, Kyren Williams, Parker Washington, Titans, Puka Nacua, Trevor Lawrence, Wan'Dale Robinson, Brenton Strange, Ja'Marr Chase |
| 5 / afd5af85a44f | CIN–JAX / Trevor Lawrence | 130.237270 | 226.944249 | 5.586228 | Caleb Douglas, Chase Brown, Dolphins, Kyren Williams, Derrick Henry, Parker Washington, Trevor Lawrence, Brenton Strange, Ja'Marr Chase |
| 244 / f7e82cae4a9a | ARI–NYG / Jacoby Brissett | 131.933115 | 230.815945 | 5.414734 | Chase Brown, Dolphins, Elic Ayomanor, Derrick Henry, Parker Washington, Michael Wilson, Trey McBride, Jacoby Brissett, Zay Flowers |
| 325 / 75573a46575c | KC–LV / Patrick Mahomes | 126.630194 | 218.852823 | 5.358235 | Chase Brown, Dolphins, Patrick Mahomes, Kenneth Walker III, Travis Kelce, Parker Washington, Xavier Worthy, Travis Hunter, Ja'Marr Chase |

Exact row-order roster hashes: 2106a933cc68, 1f78b6b33bc8, afd5af85a44f, f7e82cae4a9a, 75573a46575c.

### Fresh application preview

| Local rank / roster hash | Primary game / QB | Mean | P90 sum | Selector | Nine players |
| --- | --- | --- | --- | --- | --- |
| 2 / 94bc4dd72e00 | CIN–JAX / Trevor Lawrence | 134.300470 | 229.713390 | 5.593077 | Chase Brown, Tee Higgins, Kyren Williams, Kenneth Walker III, Parker Washington, Trevor Lawrence, Michael Wilson, Brenton Strange, Rams |
| 3 / 63f0751e40f5 | CIN–JAX / Trevor Lawrence | 131.250648 | 233.035237 | 5.588119 | Chase Brown, Malik Washington, Dolphins, Kenneth Walker III, Parker Washington, Trevor Lawrence, Michael Wilson, Brenton Strange, Ja'Marr Chase |
| 5 / 8c14d93944d7 | CIN–JAX / Trevor Lawrence | 127.675380 | 226.309655 | 5.586366 | Tee Higgins, Dolphins, Kenneth Walker III, Parker Washington, James Cook III, Trevor Lawrence, Michael Wilson, Brenton Strange, Jakobi Meyers |
| 48 / ebafe33636c6 | CIN–JAX / Joe Burrow | 128.473310 | 227.107584 | 5.495931 | Caleb Douglas, Chase Brown, Tee Higgins, Dolphins, Kenneth Walker III, Michael Wilson, Brenton Strange, Joe Burrow, Ja'Marr Chase |
| 83 / 7ef0cc982a08 | ARI–NYG / Jacoby Brissett | 128.531995 | 229.765932 | 5.374596 | Chase Brown, Tee Higgins, Parker Washington, Javonte Williams, Michael Wilson, Trey McBride, Jakobi Meyers, Jacoby Brissett, Rams |

Exact row-order roster hashes: 94bc4dd72e00, 63f0751e40f5, 8c14d93944d7, ebafe33636c6, 7ef0cc982a08.

### Exposure-sensitivity additions relative to their unrestricted reference

| Sensitivity | Hash | Rank | QB | Mean | P90 | Selector | Nine players |
| --- | --- | --- | --- | --- | --- | --- | --- |
| chase_brown_max5 | 2106a933cc68 | 1 | Trevor Lawrence | 133.324782 | 225.604499 | 5.606632 | Chase Brown, Dolphins, Kyren Williams, Travis Kelce, Parker Washington, Puka Nacua, Trevor Lawrence, Travis Hunter, Ja'Marr Chase |
| chase_brown_max5 | 3b5586ab1086 | 3 | Trevor Lawrence | 130.463208 | 228.607243 | 5.593442 | Chase Brown, Chargers, Kyren Williams, Parker Washington, Puka Nacua, Trevor Lawrence, Wan'Dale Robinson, Brenton Strange, Ja'Marr Chase |
| chase_brown_max5 | 67c545e95c44 | 11 | Trevor Lawrence | 129.358762 | 228.241592 | 5.578487 | Chase Brown, Dolphins, Cade Otton, Brian Thomas Jr., Kenneth Walker III, Parker Washington, Trevor Lawrence, Michael Wilson, Ja'Marr Chase |
| chase_brown_max5 | f3fd5fb16362 | 97 | Joe Burrow | 128.117752 | 224.420582 | 5.528690 | Chase Brown, Tee Higgins, Kyren Williams, Parker Washington, Colby Parkinson, Titans, Michael Wilson, Joe Burrow, Ja'Marr Chase |
| chase_brown_max5 | f7e82cae4a9a | 244 | Jacoby Brissett | 131.933115 | 230.815945 | 5.414734 | Chase Brown, Dolphins, Elic Ayomanor, Derrick Henry, Parker Washington, Michael Wilson, Trey McBride, Jacoby Brissett, Zay Flowers |
| chase_brown_max4 | bba0223a9407 | 61 | Trevor Lawrence | 124.603017 | 222.350538 | 5.548279 | Brian Thomas Jr., Kyren Williams, Kenneth Walker III, Parker Washington, Jets, Trevor Lawrence, Michael Wilson, Brenton Strange, Ja'Marr Chase |
| chase_brown_max3 | afd5af85a44f | 5 | Trevor Lawrence | 130.237270 | 226.944249 | 5.586228 | Caleb Douglas, Chase Brown, Dolphins, Kyren Williams, Derrick Henry, Parker Washington, Trevor Lawrence, Brenton Strange, Ja'Marr Chase |
| chase_brown_max3 | 8ec71afb44bb | 217 | Joe Burrow | 126.691416 | 213.467346 | 5.446816 | Tee Higgins, Dolphins, Kyren Williams, Parker Washington, Travis Hunter, Rhamondre Stevenson, Trey McBride, Joe Burrow, Ja'Marr Chase |
| chase_brown_max3 | 7a506d743808 | 230 | Jacoby Brissett | 133.822985 | 231.325848 | 5.425765 | Chase Brown, Dolphins, Elic Ayomanor, Kyren Williams, Derrick Henry, Puka Nacua, Michael Wilson, Trey McBride, Jacoby Brissett |
| dolphins_dst_max4 | 1f78b6b33bc8 | 4 | Trevor Lawrence | 130.463208 | 228.607243 | 5.593442 | Chase Brown, Kyren Williams, Parker Washington, Titans, Puka Nacua, Trevor Lawrence, Wan'Dale Robinson, Brenton Strange, Ja'Marr Chase |

## Final answers

1. **What was already completed and reused?** The completeness discovery/admission artifact, v3 dynamic thesis shadow, old frozen inputs, production control and existing multi-slate audit. Discovery was not restarted. Historical certification remains N=0; provisional historical evidence is one Week 3 case with no independent holdout.
2. **What materially differs in the new run?** Old versus current control changes metadata/model artifact hashes, request overlap/distinct-QB/global exposure, but not the 466-player numerical scoring frame. The separate fresh preview changes salaries/status/team evidence, markets, expected roles, prior-week completeness, eligible pool (466 → 332), fitted artifact and all common mean/P90 outputs; it is not a pure expansion experiment.
3. **Does broader discovery improve the five-entry optimum under fixed policy?** Yes: 27.714209 → 27.721987, +.007777510 with a preserved feasible incumbent and proven solves. Coverage improves far more (32.56% → 100% of the .20 known reference); neither establishes improved winning performance.
4. **Does dynamic thesis filtering discard useful alternatives?** Yes. First feasibility at .15 removes 53 previously .20-eligible rosters, including all 23 Brissett/ARI–NYG alternatives. Adding only near-frontier CIN–JAX constructions reproduces the effect. It follows the implemented quality-first ladder, but can conflict with an intention to retain broad game alternatives.
5. **How much canonical-game and shared-core dependence remains?** Current/full/fresh policies still stack CIN–JAX in 4/5 entries; dynamic does so in 5/5. Overlap-four/distinct-QB yields five directions but only three games. The game max-three shadow costs .162715 selector and still shares Brown/Washington in all five. The fresh preview shares Michael Wilson 5/5 and several other players 4/5; constructions are not independent outcomes.
6. **Which requested settings actually reached the solver?** Five entries, exposure intent, distinct-QB flag, conservative availability and user exclusions/locks reached it. Current request omitted overlap, so production used six. A supplied four is overridden by the current production branch; the report shows requested `{}` rather than an effective contract. Accepted implicit minima are three QBs and two stack types; there is no canonical primary-game cap or dynamic thesis allocation in production.
7. **What source/role issues remain before Sunday?** Final inactive/starter evidence; Caleb Douglas DNP and Meyers limited with null game statuses; nested practice facts not reflected in top-level solver risk fields; Puka's missing prior-week rows and Q designation; the TB starter/salary conflict; 18 salary, one roster and 148 snap unresolved records; 32 unmatched/ambiguous depth cells; partial ownership; missing current numeric workloads/routes/red-zone evidence and review of the all-entry Wilson core. LAR's stale team-history gap is repaired only in the new frame; the general unavailable-as-zero reporting defect remains.
8. **Which exact policy and execution path produced the fresh preview?** `current_production_205_conservative_sunday_preview_v1`, pinned projection cf77fd72…, POST `/api/optimizer/run`, saved run 00905dcb…, verified GET `/api/optimizer/results/00905dcb-d397-4454-99cc-f913fe3345db` and the section-9 offline `--replay` command. All 205 candidates, policy, input digest and exact selected rosters match. A new UI click rebuilds inputs and is not this freeze's replay.
9. **What single implementation change should be considered next, and what evidence supports it?** Resolve and persist one requested/effective portfolio-policy contract, honour explicit user overlap before applying an absent-value default, and render that same contract in the report. Evidence: the real production call sends six despite requested four; saved/report constraints hide defaults; materially different labelled shadows quantify the choice. Regression-test that contract through request → solver → report before considering broader discovery/thesis promotion. No new permanent overlap preference or strategy default is prescribed here.
