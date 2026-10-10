# Showdown scenario selection: frozen Week 4 study

Implemented as an opt-in experiment. Baseline selection remains the default.
No live imports, projection rebuilds, user optimizer runs, or submissions were
performed for this study. The offline replay changes selection of retained
candidates only. It does not generate a replacement entry file.

## Reference and root cause

Reference: Monday run `2599724c-4ecd-4b0f-8dda-e5a289754dd2`, projection
`6696a65a-8ffc-441d-82ba-7bd89e1e61ed`, ATL@NO, Week 4, 2026.
Immutable report copies and SHA-256 fingerprints are in
[`artifacts/showdown_scenario_selection`](../artifacts/showdown_scenario_selection).
The market observation remains **2026-09-30 01:22:11.632067+00:00**;
copying/replaying the report does not refresh that evidence or make entries ready.

1. Discovery solves each generic team decisive-win condition: highest selector,
   highest mean/ceiling, every eligible Captain, 5-1/4-2/3-3 winner constructions,
   and RB/DST control constructions. It inherits the filtered eligible pool.
2. Every conditional roster is re-solved with its six canonical IDs and exact
   Captain locked on the original baseline pool. This validates legality and
   restores the production selector and forecasts. Conditional evidence is
   retained separately. Ownership is disabled uniformly on this saved slate.
3. The joint screen requires baseline mean >= **88.875155** and summed marginal
   P90 >= **148.396731**, 95% of independent baseline maxima 93.552795 and
   156.207085. Only **23/142** scenario variants (17 physical rosters) pass.
4. Final selection for this path is a **global binary portfolio solve**. Entry
   count dominates; baseline selector is next. It is not greedy sequential
   selection. Earlier exposure-aware sequential discovery supplies witnesses,
   but does not determine final portfolio membership.
5. Player limits: starting QBs 5, core players 4, cheap punts 2; Captain limit
   3. A physical signature is exact Captain plus six canonical IDs, independent
   of row order. Scenario variants of that signature cannot be repeated.
   There is no additional pairwise shared-player cap in this selector.

| Scenario | Generated | Pass joint screen | Can fit a full capped portfolio | Selected |
|---|---:|---:|---:|---:|
| Baseline | 99 | 17 | 17 | 5 |
| ATL decisive win | 21 | 2 | 2 | 0 |
| NO decisive win | 22 | 4 | 4 | 0 |

Constraint survival means a forced-candidate full-portfolio feasibility solve,
not permission to append the candidate to the existing five entries.

## Best decisive candidates and binding terms

| Discovery scenario / candidate | Baseline rank / selector | Baseline mean / P90 proxy | Conditional mean / P90 proxy | Exact first rejection |
|---|---|---|---|---|
| ATL: Olave CPT, Shough, Penix, Brian Robinson, Dotson, Vele; 3 ATL / 3 NO; $49,400 | #7 / 174.3511 | 81.6442 / 151.0058 | 82.4837 / 154.1931 | Mean short 7.2310; ceiling passes |
| NO: Olave CPT, Smyth, Shough, Juwan Johnson, Dotson, Vele; 1 ATL / 5 NO; $48,800 | #2 / 176.0199 | 90.0043 / 153.4182 | 93.0297 / 158.3372 | Exact physical duplicate of selected baseline #1; extra label has zero coverage value |

The ATL #7 conditional evidence adds **0.8396 mean / 3.1873 ceiling points**;
the old final evaluation uses **none** of that uplift. Its baseline selector is
only 1.6688 (0.948%) below the top selector, but its mean is 87.2707% of the
baseline maximum. A high selector does not compensate for failing the hard
joint quality screen. Its Olave Captain prior contributes 17.8827 selector
points and baseline correlation 2.2503; these existing terms were not tuned.

The two eligible ATL variants are both NO-led:

- #68 Shough CPT, Smyth, Bijan, Juwan, Brian Robinson, Vele: baseline
  91.9394 / 149.8793, conditional 93.9319 / 154.3246, selector 158.0299.
  The cheapest **single-slot** replacement is #5 at a cost of 16.5403.
  An exact global forced replay instead changes #5/#70 to #41/#68 and loses
  **7.8945** selector points. It adds no winner Captain coverage and differs
  by only one player from an ordinary selected roster, so soft credit is zero.
- #114 Smyth CPT: selector 145.7180; minimum full-portfolio cost **28.8522**.
  It likewise has no meaningful additional ATL construction credit.

Core caps on Smyth, Juwan, Vele and Olave are saturated at four; Olave Captain
is saturated at three. Forcing #68 while retaining the other four entries
would exceed Vele's cap; removing #70 still leaves Juwan above four, whereas
removing #5 is feasible. This explains why the single-slot and full-portfolio
costs differ. Shough at 5/5 is permitted by the starting-QB cap, not mandated.

NO #4 also duplicates selected baseline #3. NO #42 Shough CPT passes the
screen, but the full-portfolio opportunity cost is 6.4448 (single-slot 8.9268).
NO #104 Juwan CPT has some real new Captain/roster value, but its credit is
only **0.1062** against **26.5967** replacement cost. Caps are always hard;
all eligible scenario candidates can fit some full portfolio, but their
scores/coverage do not justify displacing the optimum.

## ATL-led constructions

| Candidate | Baseline mean / P90 | Conditional mean / P90 | Selector | Baseline screen |
|---|---|---|---:|---|
| #50 London CPT; 3 ATL / 3 NO (best ATL Captain selector) | 77.5608 / 143.9587 | 79.5183 / 148.9472 | 163.5703 | Mean short 11.3144, ceiling short 4.4380 |
| #43 Olave CPT; 4 ATL / 2 NO (best ATL-majority selector) | 80.8464 / 143.9441 | 86.1258 / 154.1400 | 165.5668 | Mean short 8.0288, ceiling short 4.4526 |
| #79 London CPT; 5 ATL / 1 NO | 69.9506 / 134.6206 | 76.5483 / 147.3625 | 152.2701 | Mean short 18.9246, ceiling short 13.7761 |
| #95 Bijan CPT; 3 ATL / 3 NO | 82.3572 / 144.0304 | 88.6422 / 155.5535 | 150.0427 | Mean short 6.5180, ceiling short 4.3663 |
| #98 Penix CPT; 4 ATL / 2 NO | 76.4280 / 141.0193 | 81.7988 / 150.4882 | 148.8936 | Mean short 12.4472, ceiling short 7.3774 |

The architecture does categorically exclude these tails under the current
baseline screen. This is more restrictive than simply requiring a modest
selector opportunity cost, but these saved forecasts also show material
individual baseline-quality deficits. No evidence here establishes tournament
value sufficient to admit them. The fix permits strong *eligible* tail
constructions to compete on marginal coverage rather than baseline score alone;
it does not claim to have solved baseline-miscalibration or justify bypassing
the screen for this slate. No ATL exposure was forced.

## Exact soft mechanism

API parameter: `params.soft_scenario_diversity`, explicit boolean, default
`false`. UI: **Optimizer options → Soft scenario diversity (experimental)**.
Legacy `require_scenario_diversity` remains accepted for old API clients but
is mutually exclusive; it previously prioritized scenario labels
lexicographically above the selector and is no longer offered by the UI.

First solve the unchanged baseline optimum O. All candidates must pass the
unchanged joint baseline screen. For an eligible nonbaseline candidate i:

```
q = min(conditional_mean_i / max_conditional_mean_in_same_condition,
        conditional_P90_i / max_conditional_P90_in_same_condition)
u = max(0, conditional_P90_i / baseline_P90_i - 1)
d = minimum count of changed canonical players against any roster in O
c = new Captain identity relative to O, on the conditioned winning team
w = winning-team slot weight (CPT 1.5, FLEX 1)
shift = w_i - maximum winning-team slot weight in O
S = 0.02 * max(0, median baseline selector in O)
```

Credit is zero for a single entry, missing conditional/winner evidence,
q < 0.95, u <= 0, or insufficient meaningful differentiation. Differentiation
requires d >= 2, or a new winning-team Captain with d >= 1. Construction must
add a new winning-team Captain with at least three winning-team players, or
increase winner slot weight above O by at least 0.5.

```
strength = clip((q - 0.95) / 0.05, 0, 1)
uplift   = min(1, u / 0.10)
novelty  = min(1, (d + 0.5 * c) / 3)
coherence = 1 if c and winner_count >= 3 else min(1, shift / 2)
credit_i = S * strength * uplift * novelty * coherence
```

Maximize entry count first, then **sum baseline selector + sum coverage
credits**, paying at most the greatest selected credit per condition.
Binary credit witnesses must also be selected; witness sums per condition
are <=1. There are no minimum scenario counts. Player/Captain caps and exact
physical uniqueness remain hard. The baseline opportunity cost cannot exceed
the total incremental reward earned. Two conditions bound reward to 4% of
one median lineup's selector, about 0.8% of a comparable five-entry portfolio.
The reward does not multiply with portfolio size or scenario duplicates.

The 2% bound, conditional frontier, novelty and uplift discounts are conservative
research policy constants, not fitted win probabilities or calibrated EV.
Positive uplift alone cannot earn credit. Only selected witness credits are
reported as paid, even when other selected entries share a condition.

The selector itself supports different entry counts and was tested at
1/2/3/5/10. Live explicit scenario discovery currently exists only in the
one-to-five-entry v3 path without a locked Captain. Unsupported opt-in requests
fail explicitly; expansion of large-portfolio candidate discovery is not part
of this change.

## A/B/C evidence and limitations

- **A:** original baseline selector and 95% screen.
- **B:** mostly baseline with 20% conditional marginal-ceiling uplift. Saved
  reports did not retain full conditioned selectors, so this is a labeled
  quality-proxy experiment, not an invented full-selector replay. Future
  accounting retains actual conditioned selectors when available.
- **C:** implemented bounded marginal portfolio value, same baseline screen.
- Forced one-per-scenario quotas and lexicographic label coverage were rejected:
  they can reward duplicates or override the dominant selector without a bounded
  opportunity cost. Broad 90%/85% floors were researched offline, not promoted.

| Frozen slate | Variant | Mean sum | Sum marginal P90 proxy | Baseline selector sum | Physical change |
|---|---|---:|---:|---:|---|
| Monday ATL@NO | A | 450.1959 | 756.8107 | 842.3918 | Reference |
| Monday ATL@NO | B | 450.1959 | 756.8107 | 842.3918 | None; two NO labels replace baseline labels |
| Monday ATL@NO | C | 450.1959 | 756.8107 | 842.3918 | None |
| Sunday CAR@DET | A | 500.1160 | 798.1943 | 875.7439 | Reference |
| Sunday CAR@DET | B | 500.1160 | 798.1943 | 875.7439 | None; three scenario labels replace baseline labels |
| Sunday CAR@DET | C | 500.1160 | 798.1943 | 875.7439 | None |

Monday before/after: ranks **1, 3, 5, 61, 70**, three Olave Captains/two Shough
Captains, two 1-5 and three 2-4 ATL/NO constructions, Shough 5/5,
Olave/Smyth/Juwan/Vele 4/5. Average pairwise shared players **3.7/6**.
Worst mean fraction **95.6821%**; worst ceiling fraction **95.0473%**.
Sunday remains three unique Captains, five 3-3 constructions, maximum player
concentration 5/5, average shared players 4.0/6, worst mean 95.2623%,
worst ceiling 98.3050%. No real scenario coverage improvement in either slate.

| Monday rank | Captain | FLEX (before and after identical) |
|---|---|---|
| 1 | Olave | Smyth, Shough, Juwan, Dotson, Vele |
| 3 | Olave | Smyth, Shough, Penix, Juwan, Dotson |
| 5 | Olave | Smyth, Shough, Juwan, Brian Robinson, Vele |
| 61 | Shough | Juwan, Brian Robinson, Olave, Pitts, Vele |
| 70 | Shough | Smyth, Bijan, Bryce Lance, Penix, Vele |

The older Thursday Week 4 report lacks common-baseline restoration; its
conditional and baseline selectors are incomparable, so it is retained but
excluded from the A/B cohort. Monday Week 3 lacks retained candidate roster
identities, so it cannot be honestly replayed. Available historical oracle
studies do not match these scenario candidate sets. **No historical oracle,
top-percentile, payout, or GPP-win improvement is established.**

Entry-count sensitivity (1/3/5/10) and research-only 90%/85% joint floors are
included in `ab.json`. At relaxed floors, labels can again change without
useful differentiation; this is not evidence to relax live quality policy.
Synthetic acceptance tests establish useful behavior for a strongly conditioned,
different winning-team Captain/roster with only a 0.50 selector opportunity
cost, and rejection when quality, caps, evidence, or opportunity cost are poor.

## Accounting, reproduction, and delivery

The app and HTML export show generated counts, baseline screen pass counts,
best baseline/conditional selector or explicit unavailable value, conditional
ceiling proxy, exact full-portfolio constraint survivors, selected counts,
best rejection/reason, minimum full-portfolio replacement cost, best eligible
rejection cost, and maximum available soft credit. Paid witnesses explain
conditional uplift, canonical player changes, new winner Captain and portfolio
selector opportunity cost, including added/replaced ranks. Physical selection
changes are compared with the ordinary optimum, not label counts.

```
.venv/bin/python -m scripts.replay_showdown_scenario_selection
.venv/bin/python -m pytest backend/app/tests/product/test_showdown_soft_scenarios.py \
  backend/app/tests/product/test_showdown_portfolio_selection.py \
  backend/app/tests/product/test_showdown_game_scenarios.py \
  backend/app/tests/product/test_showdown_production_research_parity.py -q
cd ui
npm test
npm run build
PLAYWRIGHT_MODULE=/path/to/playwright node tests/scenarioAccounting.e2e.mjs
```

Changed implementation: `showdown_portfolio_selection.py`, new
`showdown_scenario_value.py`, the optimizer parameter/call wiring, runtime
fingerprint, UI option, scoped table styling and shared accounting component/export helper; new
behavior/report tests, isolated browser fixture, replay script and these docs.
No schema migration, dependency, forecast, Captain prior, availability, Q
preference, backup-QB package rule, or low-opportunity-filter changes.

**Recommendation: keep the new behavior off by default.** The architecture can
retain defensible differentiated tails, but these two saved slates do not
establish superior tournament outcomes or justify admitting weaker baseline
constructions. A broader point-in-time scenario candidate archive plus realized
joint outcomes is needed before changing defaults or adding a narrowly governed
tail-specific quality exception.

Validation: 71 relevant backend tests and 104 UI tests passed, production build
passed, desktop/mobile isolated browser checks passed. The idle local API and
worker were reloaded; loaded module hashes match disk and the saved Monday
results/projection are unchanged. No queued jobs were created. See
`artifacts/showdown_scenario_selection/deployment-verification.json`.
