# Salary, stacking and workload — completed controlled research

No tested replacement is ready for live promotion. The salary/stacking ablations and a genuinely joint, probability-free portfolio objective all failed to select either of the two observed top-decile rosters available in the same broader Week 6 pool. Relative-role transport did not consistently improve historical workload accuracy. Small proxy-calibration fits also failed their predeclared across-position/two-fold success criterion. Original projections, user settings and operational lineups remain unchanged.

## What was actually executed

Public app research artifact `1765c389aad769bef4311f4d22b6e2c3ac3c4e2a0fb403f9e19058d4bb46cdc3` was built through **Analyst Reports → Frozen scenario candidate research replay → Compare retrained salary and stacking ablations**, then selected from **Saved scenario research comparison** and visibly reopened as **Research only · completed**. It contains 13 full five-lineup comparisons on exactly 76 canonical rosters / 79 source variants. This is persisted research, not a new optimizer run, CSV, entry or upload clearance. The live Monday context shown beside the research report is not its source slate.

The corrected full-game parent is `77282e4a9128ca1bce3de38b226ff0c5c4eb84985be323851bf52ddfde20fcde`; joint selector parent `43e7ba899b7fc93434c22272886e9e8a72486bb8fe395274dc7c4241d7109150`. Original source optimizer `398efe88-a871-47fa-a4f1-4d3e9924a825`, projection `c8869a96-440c-4c36-aead-3614d6ef4d97`, saved decision 2026-10-17T03:52:23.077047Z, source player cutoff 2026-10-16T14:58:29.446687Z. Research freezing/evaluation occurred afterward; source-clock/code certification remains incomplete. Previously inspected outcomes make every Week 6 comparison retrospective.

Settings remain five entries, 80% player exposure, maximum overlap five, one TE, maximum three per team/four per game, original position/salary/season-PPG and availability preferences. No new teammate caps, forced stacks or probability assumptions were introduced. The original frozen legal model contains 137 eligible players; the complete model opportunity universe retains 513 actors including preference exclusions. Original entered/saved artifacts are preserved.

## Mandatory research scoring correction

The earlier research-only joint scorer incorrectly charged −2 for a lost fumble. DraftKings NFL uses −1. Production scoring and original FP projections already used the correct definition; they were not changed. The corrected helper reconciles all 323 component-covered observed player-games. Old artifacts and reports remain immutable with an [erratum](../../full_game_candidate_breadth_20261018/v1/ERRATUM.md). This report uses `draftkings_nfl_typed_v2_lost_fumble_minus_one` throughout. The original `941f74…` generation/joint scores must not be treated as the corrected baseline.

## Retrained feature ablations across weeks

24 fixed single-thread logistic fits: core/rich × original/remove-salary/remove-stacking/remove-both × train-before-Week4/5/6. C=0.1 and the original training/deduplication/weighting policy remain fixed. All six retrained original controls reproduce stored controls within 1e−9. Models and manifest were saved before evaluation. No coefficient-zeroing substitute, hyperparameter search or evaluation-week labels entered fitting.

Salary removal drops salary used, minimum base salary and base-salary standard deviation. Stacking removal drops team/game concentration, maximum team/game count and QB/receiver relationship features. Remaining projections and workload/game features carry correlated salary/team information; this is feature-group sensitivity, not a causal experiment proving salary or stacking good/bad.

Numbers below are sampled-field ranking diagnostics: five unique canonical rosters per contest, boundary ties included as positive labels. These are not constrained operational portfolios. Week4 has four overlapping fields from one Main slate; Week5 has four fields across Early/Late/Main with shared games; Week6 one Main field. Only three week blocks exist, and previously inspected results are not fresh blind validation.

|Family|Week|Treatment|Top-decile hits / selections|Mean-control hits|Mean contest AUC|Mean Brier|
|---|---:|---|---:|---:|---:|---:|
|core|4|original|1/20|6/20|0.545|0.1212|
|core|4|remove_salary|2/20|6/20|0.513|0.1205|
|core|4|remove_stacking|1/20|6/20|0.547|0.1192|
|core|4|remove_both|2/20|6/20|0.503|0.1171|
|core|5|original|1/20|0/20|0.624|0.0759|
|core|5|remove_salary|1/20|0/20|0.600|0.0747|
|core|5|remove_stacking|0/20|0/20|0.566|0.0746|
|core|5|remove_both|1/20|0/20|0.515|0.0742|
|core|6|original|1/5|0/5|0.577|0.0952|
|core|6|remove_salary|2/5|0/5|0.565|0.0952|
|core|6|remove_stacking|0/5|0/5|0.564|0.0953|
|core|6|remove_both|1/5|0/5|0.542|0.0954|
|rich|4|original|1/20|6/20|0.546|0.1216|
|rich|4|remove_salary|3/20|6/20|0.528|0.1208|
|rich|4|remove_stacking|1/20|6/20|0.552|0.1202|
|rich|4|remove_both|4/20|6/20|0.533|0.1192|
|rich|5|original|2/20|0/20|0.645|0.0731|
|rich|5|remove_salary|2/20|0/20|0.630|0.0733|
|rich|5|remove_stacking|2/20|0/20|0.629|0.0734|
|rich|5|remove_both|1/20|0/20|0.621|0.0740|
|rich|6|original|1/5|0/5|0.552|0.0960|
|rich|6|remove_salary|2/5|0/5|0.528|0.0964|
|rich|6|remove_stacking|0/5|0/5|0.551|0.0957|
|rich|6|remove_both|1/5|0/5|0.520|0.0961|

Removing salary improves a few extreme-tail selections, especially Week4, but reduces AUC in every family/week fold. Removing stacking does not consistently help. Neither treatment dominates the original or mean control across weeks. The rich no-salary constrained portfolio is exactly unchanged. This evidence does not justify changing live salary or stack behavior.

## Same corrected pool, original constraints

All 13 comparisons achieve five entries and pass independently checked constraints; the eight new model solves are Optimal. Legacy finite-pool search is complete. Its sequential construction/objective is adapted faithfully to the frozen finite pool and reproduces the original ordered five on the original source universe; it does not recreate missing original candidate-generation searches on other weeks.

|Policy|Achieved|Summed original mean|Observed top10 hits|Best observed FP|Rams-offense rosters|
|---|---:|---:|---:|---:|---:|
|legacy_sequential_adapted|5/5|643.65|0/5|134.80|5/5|
|highest_mean|5/5|647.61|0/5|133.98|5/5|
|top10_core|5/5|618.24|0/5|130.22|5/5|
|top10_rich|5/5|636.84|0/5|134.80|5/5|
|joint_worst_regret|5/5|551.61|0/5|134.10|5/5|
|core_original|5/5|618.24|0/5|130.22|5/5|
|core_remove_salary|5/5|617.40|0/5|130.22|5/5|
|core_remove_stacking|5/5|641.07|0/5|130.88|5/5|
|core_remove_both|5/5|637.22|0/5|134.80|5/5|
|rich_original|5/5|636.84|0/5|134.80|5/5|
|rich_remove_salary|5/5|636.84|0/5|134.80|5/5|
|rich_remove_stacking|5/5|640.01|0/5|134.80|5/5|
|rich_remove_both|5/5|623.92|0/5|130.22|5/5|

The pool contains 76 scoreable canonical lineups, two reaching the observed contest-196653899 top10 boundary of 150.20 FP. The candidate-coverage ceiling is therefore two distinct hits in a five-lineup selection before considering simultaneous portfolio feasibility; every policy selects zero. This is evidence of selection failure on this retrospective pool, not proof those two hindsight lineups were predictable. Actuals were appended after the decision receipt; no fee/payout/ROI or origin/submission inference is made.

The joint control optimizes the worst, across shared physical states, ratio of the best selected roster score to the best pool score in that state. It does not sum marginal P90 or average invented equal scenario probabilities. Coverage increases from legacy 0.317 to 0.556, but original expected-score sum falls 643.65→551.61, a 92.04-point portfolio cost. Neither observed hit count nor removal of shared Rams dependency improves. Better coverage of an uncalibrated, role-mismatched stress library is not demonstrated football or tournament improvement.

## Full-lineup football review

The mean/legacy path spends on supported Stafford–Puka passing and Kyren rushing production alongside Chuba and cheaper receivers/TE. A passing TD may correctly score both QB and receiver; Kyren also needs separate rush/receiving opportunities. It can succeed in a productive Rams environment with other value roles delivering. It shares substantial exposure to that environment and to cheap supporting roles. The original exposure caps limit individual players but do not guarantee distinct paths to success.

The joint portfolio has materially different complete constructions: an Allen lineup with Puka/Kyren plus Mayer; Stafford with Puka, Waller, Jeanty and Skattebo; Maye with London/Nabers/Tucker and Kyren; Winston with Nabers/Tucker plus Bijan/Skattebo/Corum/Otton; Cousins with Bijan/Kyren/Skattebo and Gunnar Helm. These cover differing QB environments and rushing/pass-catching distributions while relying on different low-salary supporting players. Yet every one still contains Rams offense. Backup/low-history roles in conditional analogs require real workload support; a historical same-position rank and salary savings do not establish it. Thus these are not recommended replacements merely because the names or modeled stress coverage differ.

A single shared game appearance is not a measured correlation or a required failure; individual players can succeed when team efficiency disappoints. The failure diagnosis is the combination of concentrated modeled dependence, uncertain current-role transport and weak temporal ranking—not a rule that Rams players or teammates must be penalized.

## Workload representation tests

The first context-plus-role-distance test on 18 earlier diagnostic games did not improve TE or WR count MAE. Its failure was retained rather than tuning distance weights. The next protocol was frozen before evaluation: transfer each source role’s realized share / its own prior share onto the current prior share, reconcile all actors and residual to the complete team count budget. Zero-prior historical expansion stays residual; it cannot establish expansion for an unrelated current player. Unknown roles fail explicitly. User exclusions retain their opportunities; no teammate inherits them.

The 36 remaining accepted 2025 target games use only earlier-week source analogs and prior-three-game role inputs. Current roles are selected from the complete prior roster, not target-game receivers. Two roles lacking explicit active/stat evidence are unscoreable rather than zero. Revised historical sources, healthy-role conditioning and previous inspection make this retrospective chronological feature separation, not fresh source-certified validation.

|Role/count|Scoreable roles|Absolute-rank MAE|Relative-shock MAE|Raw lagged-three MAE|Relative P90 exceed|Relative central80 coverage|
|---|---:|---:|---:|---:|---:|---:|
|TE|71|2.143|2.370|2.174|8.5%|80.3%|
|WR|71|2.447|2.449|2.239|7.0%|80.3%|
|RB|72|4.629|4.467|4.477|11.1%|76.4%|

All 8,258 allocations conserve counts including residual (maximum numerical error 1.4e-14); mean residual share is 11.92%. This fixes an accounting/role-level mechanism in a standalone prototype but **does not establish better workload predictions**: TE error worsens, WR is unchanged, RB improves modestly and barely beats raw lagged counts. No full event/TD/yard allocation or corrected Week6 generation is activated from it.

## Original 2026 workload-proxy diagnostic

The saved `targets_mean_3` field can be an allocated fractional proxy, not a raw recent-target mean or calibrated expected targets. W2/W3/W5 provide 323 unique component-covered regular-role player-games; all reconcile to observed DK points under corrected scoring. Saved total-FP outputs lack predicted TD/yard components, so an exact causal workload-versus-efficiency/TD decomposition is not identifiable. WR/TE workload error and FP error correlate, but that association alone does not establish a corrected point forecast.

An already-predeclared eight-fit one-feature Poisson calibration compares W2→W3 and W2+3→W5. Training-only transforms, alpha=1, fixed iteration cap and no search. The same canonical cohort is used for unchanged proxy, calibrated proxy and training-position mean controls. This diagnostic is not a jointly conserving team model.

|Test week|Position|Rows|Proxy MAE|Calibrated MAE|Position-mean MAE|Game-cluster 95% ΔMAE vs proxy|
|---:|---|---:|---:|---:|---:|---|
|3|QB|24|1.944|1.938|2.264|[-0.363, 0.367]|
|3|RB|39|4.854|4.463|6.487|[-0.823, 0.066]|
|3|WR|59|3.063|2.888|2.915|[-0.498, 0.097]|
|3|TE|23|2.936|2.854|2.870|[-1.122, 0.965]|
|5|QB|26|2.045|2.327|2.731|[-0.095, 0.634]|
|5|RB|37|5.338|4.752|5.802|[-1.453, 0.079]|
|5|WR|52|3.045|2.924|2.873|[-0.474, 0.267]|
|5|TE|26|2.312|2.347|2.385|[-0.697, 0.872]|

The success criterion fails: Week5 QB and TE regress; Week5 WR calibration does not beat the position-mean control; every clustered confidence interval versus the original proxy crosses zero. No blanket workload raises or model promotion follow.

## Decision and next evidence

Completed: corrected baseline reconciliation, 24 retrained ablations, constrained public same-pool comparison/reopen, exact bounded joint solver, 36-game role-relative counts test, eight small chronological proxy-calibration fits and focused invariants. No costly job remains running.

Further tuning against the same inspected outcomes would not supply independent validation. 432 earlier optimizer records lack the complete frozen legal-model plus opportunity-universe snapshots needed for faithful old-vs-new operational replays; none is silently reconstructed as original. The next useful prerequisite is a source-certified prospective set of complete player/team opportunity inputs and frozen candidate/decision receipts, with expected count/yard/TD components and observed complete results. A later chronological season/block can validate a full event allocator; it must preserve passing/receiving and scoring conservation and compare the same frozen pool. Until then keep current defaults, expose uncertainty and retain every negative result. More thresholds, forced diversity or another uncalibrated weighting sweep are not supported.

## All complete portfolios

These are frozen unsaved research rosters; FP means are original summed marginal means, not joint P90. Actual FP is observed retrospective scoring. Roster display order below is position order, not proof of native DraftKings slot assignment. Canonical identities and source candidate IDs remain in the immutable app artifact.

### legacy_sequential_adapted

|#|Full roster|Salary|Original mean|Observed FP|
|---:|---|---:|---:|---:|
|1|QB Matthew Stafford / RB Chuba Hubbard / RB Kyren Williams / WR Carnell Tate / WR Michael Wilson / WR Puka Nacua / WR Rome Odunze / TE Cade Otton / DST Panthers|$50,000|133.483|101.18|
|2|QB Aaron Rodgers / RB Jaylen Warren / RB Kenneth Walker III / RB Kyren Williams / WR Laquon Treadwell / WR Puka Nacua / WR Rome Odunze / TE Cade Otton / DST Panthers|$49,900|129.010|97.82|
|3|QB Bryce Young / RB Chuba Hubbard / RB Derrick Henry / RB Kyren Williams / WR Puka Nacua / WR Rome Odunze / WR Wan'Dale Robinson / TE Cade Otton / DST Jets|$50,000|130.994|89.14|
|4|QB Josh Allen / RB Chuba Hubbard / RB Kyren Williams / WR Carnell Tate / WR Emeka Egbuka / WR Khalil Shakir / WR Puka Nacua / TE Michael Mayer / DST Panthers|$49,900|126.198|134.80|
|5|QB Matthew Stafford / RB Chuba Hubbard / RB Derrick Henry / RB Jonathan Taylor / WR Carnell Tate / WR Emeka Egbuka / WR Rome Odunze / TE Tyler Higbee / DST Panthers|$49,900|123.966|119.98|

### highest_mean

|#|Full roster|Salary|Original mean|Observed FP|
|---:|---|---:|---:|---:|
|1|QB Matthew Stafford / RB Ashton Jeanty / RB Chuba Hubbard / RB D'Andre Swift / WR Carnell Tate / WR Emeka Egbuka / WR Puka Nacua / TE Cade Otton / DST Panthers|$50,000|125.822|133.98|
|2|QB Matthew Stafford / RB James Cook III / RB Kenneth Walker III / RB Kyren Williams / WR Carnell Tate / WR Emeka Egbuka / WR Rome Odunze / TE Cade Otton / DST Panthers|$50,000|128.623|130.88|
|3|QB Bryce Young / RB Chuba Hubbard / RB Derrick Henry / RB Kyren Williams / WR Puka Nacua / WR Rome Odunze / WR Wan'Dale Robinson / TE Cade Otton / DST Jets|$50,000|130.994|89.14|
|4|QB Matthew Stafford / RB Chuba Hubbard / RB Kyren Williams / WR Carnell Tate / WR Michael Wilson / WR Puka Nacua / WR Rome Odunze / TE Cade Otton / DST Browns|$50,000|132.374|106.18|
|5|QB Aaron Rodgers / RB Ashton Jeanty / RB Chuba Hubbard / RB Kyren Williams / WR Carnell Tate / WR Puka Nacua / WR Rome Odunze / TE Pat Freiermuth / DST Panthers|$50,000|129.799|111.62|

### top10_core

|#|Full roster|Salary|Original mean|Observed FP|
|---:|---|---:|---:|---:|
|1|QB Tyler Shough / RB Chuba Hubbard / RB Kyren Williams / WR Devaughn Vele / WR Malik Nabers / WR Puka Nacua / WR Rome Odunze / TE Harold Fannin Jr. / DST Panthers|$49,900|126.278|124.26|
|2|QB Patrick Mahomes / RB Derrick Henry / RB Kyren Williams / WR Carnell Tate / WR Puka Nacua / WR Rome Odunze / WR Xavier Worthy / TE Cade Otton / DST Panthers|$49,900|127.929|86.78|
|3|QB Aaron Rodgers / RB Jaylen Warren / RB Kenneth Walker III / RB Kyren Williams / WR Carnell Tate / WR Malik Nabers / WR Rome Odunze / TE Cade Otton / DST Panthers|$50,000|125.895|130.22|
|4|QB Aaron Rodgers / RB Chuba Hubbard / RB Derrick Henry / WR Carnell Tate / WR Davante Adams / WR Puka Nacua / WR Rome Odunze / TE Darnell Washington / DST Panthers|$50,000|126.204|108.42|
|5|QB Geno Smith / RB Kyren Williams / RB Omarion Hampton / RB Rhamondre Stevenson / WR Drake London / WR Garrett Wilson / WR Malik Nabers / TE Tyler Higbee / DST Steelers|$50,000|111.933|101.48|

### top10_rich

|#|Full roster|Salary|Original mean|Observed FP|
|---:|---|---:|---:|---:|
|1|QB Tyler Shough / RB Jaylen Warren / RB Kyren Williams / WR Devaughn Vele / WR Malik Nabers / WR Puka Nacua / WR Rome Odunze / TE Cade Otton / DST Panthers|$49,800|126.375|111.46|
|2|QB Patrick Mahomes / RB Derrick Henry / RB Kyren Williams / WR Carnell Tate / WR Puka Nacua / WR Rome Odunze / WR Xavier Worthy / TE Cade Otton / DST Panthers|$49,900|127.929|86.78|
|3|QB Matthew Stafford / RB Chuba Hubbard / RB Kyren Williams / WR Carnell Tate / WR Michael Wilson / WR Puka Nacua / WR Rome Odunze / TE Cade Otton / DST Browns|$50,000|132.374|106.18|
|4|QB Josh Allen / RB Chuba Hubbard / RB Kyren Williams / WR Carnell Tate / WR Emeka Egbuka / WR Khalil Shakir / WR Puka Nacua / TE Michael Mayer / DST Panthers|$49,900|126.198|134.80|
|5|QB Matthew Stafford / RB Chuba Hubbard / RB Derrick Henry / RB Jonathan Taylor / WR Carnell Tate / WR Emeka Egbuka / WR Rome Odunze / TE Tyler Higbee / DST Panthers|$49,900|123.966|119.98|

### joint_worst_regret

|#|Full roster|Salary|Original mean|Observed FP|
|---:|---|---:|---:|---:|
|1|QB Josh Allen / RB Chuba Hubbard / RB Kyren Williams / WR Carnell Tate / WR Khalil Shakir / WR Puka Nacua / WR Rome Odunze / TE Michael Mayer / DST Panthers|$49,600|126.938|123.90|
|2|QB Matthew Stafford / RB Ashton Jeanty / RB Braelon Allen / RB Cam Skattebo / WR Jahan Dotson / WR Puka Nacua / WR Rome Odunze / TE Darren Waller / DST Colts|$47,900|113.988|85.68|
|3|QB Drake Maye / RB Kyren Williams / RB Tony Pollard / WR DeMario Douglas / WR Drake London / WR Malik Nabers / WR Tre Tucker / TE Juwan Johnson / DST Eagles|$48,700|105.192|134.10|
|4|QB Jameis Winston / RB Bijan Robinson / RB Blake Corum / RB Cam Skattebo / WR Malik Nabers / WR Romeo Doubs / WR Tre Tucker / TE Cade Otton / DST Rams|$47,900|96.761|103.58|
|5|QB Kirk Cousins / RB Bijan Robinson / RB Cam Skattebo / RB Kyren Williams / WR Keenan Allen / WR Michael Wilson / WR Tre Tucker / TE Gunnar Helm / DST Buccaneers|$47,700|108.733|96.62|

### core_original

|#|Full roster|Salary|Original mean|Observed FP|
|---:|---|---:|---:|---:|
|1|QB Tyler Shough / RB Chuba Hubbard / RB Kyren Williams / WR Devaughn Vele / WR Malik Nabers / WR Puka Nacua / WR Rome Odunze / TE Harold Fannin Jr. / DST Panthers|$49,900|126.278|124.26|
|2|QB Patrick Mahomes / RB Derrick Henry / RB Kyren Williams / WR Carnell Tate / WR Puka Nacua / WR Rome Odunze / WR Xavier Worthy / TE Cade Otton / DST Panthers|$49,900|127.929|86.78|
|3|QB Aaron Rodgers / RB Jaylen Warren / RB Kenneth Walker III / RB Kyren Williams / WR Carnell Tate / WR Malik Nabers / WR Rome Odunze / TE Cade Otton / DST Panthers|$50,000|125.895|130.22|
|4|QB Aaron Rodgers / RB Chuba Hubbard / RB Derrick Henry / WR Carnell Tate / WR Davante Adams / WR Puka Nacua / WR Rome Odunze / TE Darnell Washington / DST Panthers|$50,000|126.204|108.42|
|5|QB Geno Smith / RB Kyren Williams / RB Omarion Hampton / RB Rhamondre Stevenson / WR Drake London / WR Garrett Wilson / WR Malik Nabers / TE Tyler Higbee / DST Steelers|$50,000|111.933|101.48|

### core_remove_salary

|#|Full roster|Salary|Original mean|Observed FP|
|---:|---|---:|---:|---:|
|1|QB Tyler Shough / RB Chuba Hubbard / RB Kyren Williams / WR Devaughn Vele / WR Malik Nabers / WR Puka Nacua / WR Rome Odunze / TE Harold Fannin Jr. / DST Panthers|$49,900|126.278|124.26|
|2|QB Patrick Mahomes / RB Derrick Henry / RB Kyren Williams / WR Carnell Tate / WR Puka Nacua / WR Rome Odunze / WR Xavier Worthy / TE Cade Otton / DST Panthers|$49,900|127.929|86.78|
|3|QB Aaron Rodgers / RB Jaylen Warren / RB Kenneth Walker III / RB Kyren Williams / WR Carnell Tate / WR Malik Nabers / WR Rome Odunze / TE Cade Otton / DST Panthers|$50,000|125.895|130.22|
|4|QB Aaron Rodgers / RB Chuba Hubbard / RB Derrick Henry / WR Carnell Tate / WR Davante Adams / WR Puka Nacua / WR Rome Odunze / TE Darnell Washington / DST Panthers|$50,000|126.204|108.42|
|5|QB Bryce Young / RB Bijan Robinson / RB Cam Skattebo / RB Kyren Williams / WR John Metchie III / WR Tetairoa McMillan / WR Tre Tucker / TE Colston Loveland / DST Giants|$49,300|111.091|102.04|

### core_remove_stacking

|#|Full roster|Salary|Original mean|Observed FP|
|---:|---|---:|---:|---:|
|1|QB Aaron Rodgers / RB D'Andre Swift / RB Jaylen Warren / RB Kyren Williams / WR Carnell Tate / WR Devaughn Vele / WR Puka Nacua / TE Cade Otton / DST Panthers|$50,000|127.323|105.12|
|2|QB Matthew Stafford / RB James Cook III / RB Kenneth Walker III / RB Kyren Williams / WR Carnell Tate / WR Emeka Egbuka / WR Rome Odunze / TE Cade Otton / DST Panthers|$50,000|128.623|130.88|
|3|QB Patrick Mahomes / RB Derrick Henry / RB Kyren Williams / WR Carnell Tate / WR Puka Nacua / WR Rome Odunze / WR Xavier Worthy / TE Cade Otton / DST Panthers|$49,900|127.929|86.78|
|4|QB Bryce Young / RB Chuba Hubbard / RB Derrick Henry / RB Kyren Williams / WR Puka Nacua / WR Rome Odunze / WR Wan'Dale Robinson / TE Cade Otton / DST Jets|$50,000|130.994|89.14|
|5|QB Aaron Rodgers / RB Chuba Hubbard / RB Derrick Henry / WR Carnell Tate / WR Davante Adams / WR Puka Nacua / WR Rome Odunze / TE Darnell Washington / DST Panthers|$50,000|126.204|108.42|

### core_remove_both

|#|Full roster|Salary|Original mean|Observed FP|
|---:|---|---:|---:|---:|
|1|QB Patrick Mahomes / RB Derrick Henry / RB Kyren Williams / WR Carnell Tate / WR Puka Nacua / WR Rome Odunze / WR Xavier Worthy / TE Cade Otton / DST Panthers|$49,900|127.929|86.78|
|2|QB Bryce Young / RB Chuba Hubbard / RB Derrick Henry / RB Kyren Williams / WR Puka Nacua / WR Rome Odunze / WR Wan'Dale Robinson / TE Cade Otton / DST Jets|$50,000|130.994|89.14|
|3|QB Aaron Rodgers / RB Jaylen Warren / RB Kenneth Walker III / RB Kyren Williams / WR Carnell Tate / WR Malik Nabers / WR Rome Odunze / TE Cade Otton / DST Panthers|$50,000|125.895|130.22|
|4|QB Aaron Rodgers / RB Chuba Hubbard / RB Derrick Henry / WR Carnell Tate / WR Davante Adams / WR Puka Nacua / WR Rome Odunze / TE Darnell Washington / DST Panthers|$50,000|126.204|108.42|
|5|QB Josh Allen / RB Chuba Hubbard / RB Kyren Williams / WR Carnell Tate / WR Emeka Egbuka / WR Khalil Shakir / WR Puka Nacua / TE Michael Mayer / DST Panthers|$49,900|126.198|134.80|

### rich_original

|#|Full roster|Salary|Original mean|Observed FP|
|---:|---|---:|---:|---:|
|1|QB Tyler Shough / RB Jaylen Warren / RB Kyren Williams / WR Devaughn Vele / WR Malik Nabers / WR Puka Nacua / WR Rome Odunze / TE Cade Otton / DST Panthers|$49,800|126.375|111.46|
|2|QB Patrick Mahomes / RB Derrick Henry / RB Kyren Williams / WR Carnell Tate / WR Puka Nacua / WR Rome Odunze / WR Xavier Worthy / TE Cade Otton / DST Panthers|$49,900|127.929|86.78|
|3|QB Matthew Stafford / RB Chuba Hubbard / RB Kyren Williams / WR Carnell Tate / WR Michael Wilson / WR Puka Nacua / WR Rome Odunze / TE Cade Otton / DST Browns|$50,000|132.374|106.18|
|4|QB Josh Allen / RB Chuba Hubbard / RB Kyren Williams / WR Carnell Tate / WR Emeka Egbuka / WR Khalil Shakir / WR Puka Nacua / TE Michael Mayer / DST Panthers|$49,900|126.198|134.80|
|5|QB Matthew Stafford / RB Chuba Hubbard / RB Derrick Henry / RB Jonathan Taylor / WR Carnell Tate / WR Emeka Egbuka / WR Rome Odunze / TE Tyler Higbee / DST Panthers|$49,900|123.966|119.98|

### rich_remove_salary

|#|Full roster|Salary|Original mean|Observed FP|
|---:|---|---:|---:|---:|
|1|QB Tyler Shough / RB Jaylen Warren / RB Kyren Williams / WR Devaughn Vele / WR Malik Nabers / WR Puka Nacua / WR Rome Odunze / TE Cade Otton / DST Panthers|$49,800|126.375|111.46|
|2|QB Patrick Mahomes / RB Derrick Henry / RB Kyren Williams / WR Carnell Tate / WR Puka Nacua / WR Rome Odunze / WR Xavier Worthy / TE Cade Otton / DST Panthers|$49,900|127.929|86.78|
|3|QB Matthew Stafford / RB Chuba Hubbard / RB Kyren Williams / WR Carnell Tate / WR Michael Wilson / WR Puka Nacua / WR Rome Odunze / TE Cade Otton / DST Browns|$50,000|132.374|106.18|
|4|QB Josh Allen / RB Chuba Hubbard / RB Kyren Williams / WR Carnell Tate / WR Emeka Egbuka / WR Khalil Shakir / WR Puka Nacua / TE Michael Mayer / DST Panthers|$49,900|126.198|134.80|
|5|QB Matthew Stafford / RB Chuba Hubbard / RB Derrick Henry / RB Jonathan Taylor / WR Carnell Tate / WR Emeka Egbuka / WR Rome Odunze / TE Tyler Higbee / DST Panthers|$49,900|123.966|119.98|

### rich_remove_stacking

|#|Full roster|Salary|Original mean|Observed FP|
|---:|---|---:|---:|---:|
|1|QB Kirk Cousins / RB Ashton Jeanty / RB James Cook III / RB Kyren Williams / WR Carnell Tate / WR Puka Nacua / WR Rome Odunze / TE Cade Otton / DST Panthers|$49,900|130.717|117.62|
|2|QB Bryce Young / RB Chuba Hubbard / RB Derrick Henry / RB Kyren Williams / WR Puka Nacua / WR Rome Odunze / WR Wan'Dale Robinson / TE Cade Otton / DST Jets|$50,000|130.994|89.14|
|3|QB Aaron Rodgers / RB Jaylen Warren / RB Kenneth Walker III / RB Kyren Williams / WR Carnell Tate / WR Malik Nabers / WR Rome Odunze / TE Cade Otton / DST Panthers|$50,000|125.895|130.22|
|4|QB Aaron Rodgers / RB Chuba Hubbard / RB Derrick Henry / WR Carnell Tate / WR Davante Adams / WR Puka Nacua / WR Rome Odunze / TE Darnell Washington / DST Panthers|$50,000|126.204|108.42|
|5|QB Josh Allen / RB Chuba Hubbard / RB Kyren Williams / WR Carnell Tate / WR Emeka Egbuka / WR Khalil Shakir / WR Puka Nacua / TE Michael Mayer / DST Panthers|$49,900|126.198|134.80|

### rich_remove_both

|#|Full roster|Salary|Original mean|Observed FP|
|---:|---|---:|---:|---:|
|1|QB Kirk Cousins / RB Ashton Jeanty / RB James Cook III / RB Kyren Williams / WR Carnell Tate / WR Puka Nacua / WR Rome Odunze / TE Cade Otton / DST Panthers|$49,900|130.717|117.62|
|2|QB Matthew Stafford / RB Chuba Hubbard / RB Kyren Williams / WR Carnell Tate / WR Michael Wilson / WR Puka Nacua / WR Rome Odunze / TE Cade Otton / DST Browns|$50,000|132.374|106.18|
|3|QB Aaron Rodgers / RB Jaylen Warren / RB Kenneth Walker III / RB Kyren Williams / WR Carnell Tate / WR Malik Nabers / WR Rome Odunze / TE Cade Otton / DST Panthers|$50,000|125.895|130.22|
|4|QB Aaron Rodgers / RB Chuba Hubbard / RB Derrick Henry / WR Carnell Tate / WR Davante Adams / WR Puka Nacua / WR Rome Odunze / TE Darnell Washington / DST Panthers|$50,000|126.204|108.42|
|5|QB Kirk Cousins / RB Bijan Robinson / RB Cam Skattebo / RB Kyren Williams / WR Keenan Allen / WR Michael Wilson / WR Tre Tucker / TE Gunnar Helm / DST Buccaneers|$47,700|108.733|96.62|

## Reproducibility and evidence

- Frozen protocols: `PROTOCOL.md`, `../joint_selection_role_support_20261018/v1/WORKLOAD_MATCHING_V2_PROTOCOL.md`, `WORKLOAD_CALIBRATION_PROTOCOL.md`.
- Models/metrics: `model_manifest.json`, `retained_proxy_audit.json`, `temporal_metrics.json`, `decision_receipt.json`, `saved_pool_evaluation.json`.
- Workload outputs: `relative_transport_validation.json`, `workload_calibration.json`, `projection_component_diagnosis_v2.json`; original failed distance validation remains preserved.
- UI proof: `app_acceptance.png`. Public research reopen was visibly verified, with all 13 comparison sections and completed research status.
- Targeted tests cover frozen feature contracts/routes, exact joint objective/timeout handling, scenario constraints, source scoring, and relative-role conservation/unknown/duplicate/expansion behavior. Final check counts are recorded separately in `validation.json`.
