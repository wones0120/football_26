# Construction review app handoff

The relevant concentration alternative is now fully visible in the retained real application review and its HTML/JSON downloads. No new diagnostic or user portfolio was generated. Run `8a25b11e-cfae-442b-afd6-bf66042d9f2c`, Entry 1, single TE off; diagnostic `1d7fdac2-8c1b-4b50-8888-761b69caf00b` is unchanged.

## Inspect the existing alternative

In **Ops → Run activity → Classic construction summary**, find **Validated lower-concentration alternative on saved inputs** above the comparison table. It displays all nine players with canonical identities, natural positions, teams, salaries, swaps, score components and frozen elevated-ID membership. Expand **Structural contributions, restrictions and replacement budgets** for exact structural rewards, saved controls, remaining budgets and portfolio-validation result. The comparison remains **QB + two WR/TE + one offensive bring-back → Replacement preserving other entries**.

Click **Download construction review evidence** for the complete HTML export, or **Download captured construction review JSON** for the original parsed response. Both real buttons were verified; JSON content equals the existing captured response. The original artifact's byte SHA256 remains `1ef64f741f5c8a63a2adacc4404574c424c037245f1aff6d1fd9007e716e9999`. The app-generated [HTML export](artifacts/classic_construction_review_live_fix/lower-concentration-evidence.html) also retains every captured comparison. No report refresh is required in the retained tab. Review state is transient: reopening/reloading clears it; use the retained tab or exported evidence to avoid another solve.

| Player | Natural position | Team | Salary |
| --- | --- | --- | ---: |
| Trevor Lawrence | QB | JAX | $5,900 |
| Kenneth Walker III | RB | KC | $8,200 |
| Javonte Williams | RB | DAL | $6,600 |
| Parker Washington | WR | JAX | $6,500 |
| Michael Wilson | WR | ARI | $5,500 |
| Tee Higgins | WR | CIN | $6,100 |
| Jakobi Meyers | WR | JAX | $5,000 |
| Cade Otton | TE | TB | $3,400 |
| Rams | DST | LAR | $2,600 |

Salary **$49,800**. Mean **130.064739**, summed marginal P90 **231.298675 (NOT a lineup percentile)**, objective **5.328972**. Versus A: **+0.091341 mean, +2.691003 summed P90, −0.090199 objective**. Strange out/Otton in; Lawrence + Washington/Meyers + Higgins WR bring-back; JAX **3**, CIN–JAX **4**. Meyers is the only member of the captured elevated-ID list; others are “not listed,” not cleared now. Risk reasons/timestamps and alternative slot assignments are unavailable. Portfolio validation **verified**, violations **none**, solver **Optimal**. Other four entries were fixed; joint portfolio optimality and empirical tournament performance are unproven.

Projection contributions improve while context, QB-stack and correlation contributions fall: weighted mean **1.885386**, P90 **2.981628**, context **0.117888**, QB-stack **0.162386**, bring-back **0.032545**, game environment **0.039777**, correlation **0.109362**. Components reconcile with the solver. Leverage is **UNAVAILABLE**; ownership-chalk/duplication are **DISABLED**; penalties/residual are active zero. Absent scoring evidence does not establish differentiation. The alternative retains eight baseline players and the same QB game; it reduces within-lineup concentration, not portfolio primary-game appearances, and adds an Otton dependency in GB–TB.

## Preserve A versus B

Higgins → Brown is the same $6,100 salary, **+2.599408 mean**, **+4.594135 summed marginal P90**, **−0.006013 objective**. Brown remains an offensive RB bring-back; zero WR/TE bring-back reward does not mean no bring-back. Projection gains oppose the smaller context and structural contributions. B (individual three RBs) and D (individual two TEs) cannot replace Entry 1 unchanged because Brown has **zero remaining appearance budget**. Exposure limits were not relaxed. Individual formula quality, conditional portfolio feasibility and empirical tournament performance remain separate; objective gaps are not winning-probability losses.

Recorded follow-up only: **Do accumulated QB/pass-catcher, opposing-pass-catcher, and bring-back rewards assign an empirically defensible marginal value to additional pass catchers and game concentration?** This is a hypothesis, not a confirmed double-counting defect. No scoring intervention was implemented.

## Readiness handoff — BLOCKED

The prior **Integrate Sunday Main readiness** task and its tests implemented Small-field/expanded preview readiness. Current source calls `classic_entry_readiness` only inside `if small_field`; the UI `SkillExposureApprovalPanel` and readable export consume `classic_small_field_report.entry_readiness`. The evaluator additionally assumes a retained candidate pool of at least 100, whereas current Large GPP saves sequential selected entries. Copying it into Large GPP would introduce incorrect candidate-pool blockers. This is an integration gap requiring a strategy-appropriate readiness contract, not an API reload repair.

The running UI exposes source loading, **Latest completed (automatic)**, ownership refresh, and chosen portfolio controls. The user-triggered **Run Optimizer** path reconciles identities, builds features, loads starting QBs, rebuilds projections with availability/exclusions, optionally refreshes ownership, then checks slate preflight and submits preserved controls. It does **not** fetch fresh markets/weather or injury/practice evidence automatically. **Refresh projections** only reloads the list of saved projection runs. Generic slate preflight checks data coverage; it does not certify Large-GPP entry readiness or material freshness/current availability. Its UI also shows at most three attention items. The live saved report has no detailed Entry readiness panel. Current player clearance was not queried or refreshed.

Therefore: control preservation **verified by existing tests and live controls**; rebuild path **present in source, not executed this turn**; comprehensive material refresh/current blockers and preview-versus-entry readiness for Large GPP **BLOCKED**. Existing focused tests pass: 27 slate-readiness/Sunday-contract tests plus one preview/blocker/ready test; UI construction/control checks passed and build passed. No backend change/restart was made. These findings use current wiring and the actual UI, not the old report's unevaluated status alone.

## User's next run

1. Keep the captured review/export for reference. In **Ops → Portfolio optimizer**, choose **Classic → Large GPP** and the intended season/week/slate.
2. Set **Number of lineups 5**, **Max player exposure (%) 80**, **Max lineups per primary game 3**, **Max shared players between lineups 5**, **Max players / team 3**, **Max players / game 5**, and leave **Enforce single TE** unchecked. Keep all explicit exclusions (including the visible opponent-team DEN exclusion), locks, availability assumptions, No offense vs DST and chosen elevated-risk preferences. Do not replace them with blanket assumptions.
3. When ready, request fresh salary/injury inputs through **Load Salaries / Load Injuries** and verify the intended files; material market/weather/practice freshness and Large-GPP entry-readiness integration remain the blocker above. Keep **Optimizer projection → Latest completed (automatic)** and review the ownership-refresh choice. A rebuild changes the input frame; it is not a same-frame experiment.
4. Inspect **Portfolio settings to submit** and the team/game/single-TE controls. Only the user clicks **Run Optimizer** to initiate a new planning portfolio. Review achieved constraints afterward; solver legality/preflight success is not entry clearance. Resolve readiness/current availability and contest/entry assignments before actual entry.

These are user planning choices, not permanent defaults. The diagnostic used team cap **FOUR**, not three; this one-entry validated alternative does not certify the other four saved entries under a new team cap of three.

Scoring/default changes: **NONE**. Replacement applied: **NO**. New user portfolio generated: **NO**. Inputs refreshed: **NO**. Services restarted: **NO**. Only existing-evidence UI presentation/export and this handoff were changed.
