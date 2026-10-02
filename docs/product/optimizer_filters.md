# DraftKings NFL Classic Optimizer Filters

Classic small-field production honors `params.portfolio_constraints.max_lineup_overlap`
when explicitly supplied; 4, 5 and 6 remain those values. Omission retains six.
`distinct_qb_paths` and the per-lineup objective-loss setting also apply to the
all-entry core exposure alternative. New reports preserve `policy_contract` and
`policy_validation`, including requested values, defaults, automatic QB/stack
minima, selected exposure/risk limits, no implicit canonical-game cap, source labels
and actual achieved overlap. Candidate-admission caps are separate. The automatic
quality budget remains rate per entry multiplied by entry count (e.g. .10 × 5 = .50).
Unproven integer incumbents and underfilled portfolios do not satisfy a requested solve.

Sourced practice facts are normalized to FULL/LIMITED/DNP and retain observation
time through context, features and optimizer rows. Migration `0045_pregame_practice_signal.sql`
allows practice-only evidence; it does not assign availability or role. Full practice
alone cannot establish the existing full-workload risk exception. False availability
flags render team-volume sentinels as unavailable, while measured zeros remain zero.

The fresh [Sunday Main readiness report](../../WEEK4_SUNDAY_MAIN_LEARNING_APPLIED_AND_READINESS.md)
links an opt-in common-frame expanded preview and manual native-ID manifest. With
no saved contest assignments, five is a planning count and all rosters are UNASSIGNED.
Contest field size/profile is separate from user entry count and technical strategy.
The development API exposes import-time module fingerprints at `/api/runtime-code`.


Showdown requests require an explicit `params.enforce_single_te` boolean. With it
enabled, candidate generation and final validation reject double-TE lineups,
including the single-entry portfolio mode. The HTML report shows the saved value,
the numerical selector and nested-solver components, and low-cost opportunity
signals. Missing opportunity evidence is labeled unavailable; the existing salary,
mean, and P90 fallback thresholds are unchanged.

The optimizer uses one shared, lineage-scoped eligibility pool and three explicit
Classic contest strategies. Availability, active-roster, injury, identity,
salary, and projection checks happen before either strategy diverges.

The shared **Exclude questionable (Q) players** checkbox defaults off and applies
to all Classic and Showdown configurations, including weekly runs and standalone
long-shot solves. `params.exclude_questionable=true` removes `Q`/`QUESTIONABLE`
salary or effective injury designations before candidate discovery. The run audit
retains each player's projection, P90 and role with the explicit user preference
reason `user_excluded_questionable`; locks cannot override the exclusion.

Operations additionally treats selected player exclusions as assumed-out scenarios.
Before each **Run Optimizer**, features and projections rebuild with explicit
name/ID `availability_overrides` and `assume_questionable_out` when checked. The
new immutable projection run includes workload redistribution and zero participation
for assumed-out players; it is pinned to the optimizer request. Weekly runs request
`refresh_projections=true`. Exposure, overlap, Captain and opponent-team restrictions
remain lineup constraints. Direct optimizer API exclusions alone do not rebuild projections.

## Standalone long-shot lineup

- **Create one standalone long-shot lineup** is available for Classic and
  Showdown GPP runs and always requests exactly one lineup.
- It is a separate solve, so it does not replace or silently alter a normal
  recommended portfolio.
- With complete ownership, Classic uses 0.15 normalized mean + 0.30 P90 + 0.40
  direct low-ownership leverage + 0.15 correlation. Showdown uses its normal
  football/correlation score with a 0.35 Captain/FLEX ownership penalty and a
  contrarian game script.
- Projections and football-role inputs are unchanged. Hard legality, player
  exclusions, locks, single-TE, and offense-versus-DST controls still apply.
- Missing or partial ownership is never converted to zero. Showdown may use its
  contrarian game script and is marked `structural_contrarian_only`; Classic is
  marked `contrarian_evidence_unavailable` and retains the ordinary football
  objective. Ownership sum and contrarian confidence remain unavailable.

## Recovering optimizer results

**Operations → Run activity → Recent optimizer runs** lists the newest 20 saved
or queued runs for the selected season, week, slate, format, and Cash/GPP objective.
The row retains its actual strategy and discovery mode. **Open results** loads and
scrolls to the original saved lineup report and its existing export actions; it does not solve
again or apply current form settings to the saved output. The selected run ID is
stored before submission and restored after a browser refresh.

UI solves use `POST /api/optimizer/jobs`; the independent worker saves full
results in the existing optimizer lineage. Browser/API reloads do not own the
solve. Worker leases recover interrupted attempts using the same run ID and
pinned request; completed persisted runs are reused. **Watch run** reconnects and
opens the result when complete. Failed queue items show their error and offer
**Retry saved request**. Refreshing during the earlier preparation steps cannot
create optimizer results until a solve has actually been queued.

`GET /api/optimizer/runs` returns lightweight metadata; reports are fetched only
when opening results. Queue timestamps supply elapsed time while solving and
measured duration after completion.
Older runs without completion timestamps explicitly display **Unavailable**.
Refresh the API and worker after deploying orchestration changes.

## Saved contest details

Paste one or more DraftKings URLs into **Saved DraftKings contests** and click
**Save contests**. The saved list immediately shows the fetched contest type,
per-person entry limit (single entry, 3-max, 20-max, etc.), maximum field size,
current entries, entry fee, and prize pool. Structured ticket payout evidence
identifies ticket satellites and labels their pool as ticket value; mixed prizes
show total prize value. Known cash format names identify head-to-head, double-up,
and 50/50 contests. Unsupported or missing type evidence displays **Type unavailable**.

**Catalog category** is the user's grouping choice, separate from the fetched
contest type. Saving does not assign entries or choose an optimizer strategy.
Each row shows its observation time. Failed refreshes use a complete earlier
successful observation labeled **Saved snapshot** and retain the fetch error.
Fresh partial observations display unavailable fields without silently filling
them from older snapshots.

## Head-to-Head (`classic_head_to_head_v1`)

- Keeps every positive-projection, post-eligibility skill player and playable DST.
- Keeps only QBs with stored starting-QB evidence; backups are labeled
  `backup QB / zero expected snaps`.
- Uses 75% mean + 20% P90 + 5% P10 floor, with a small fragile-punt penalty and
  soft QB/receiver correlation bonus.
- Requires no stack, bring-back, ownership, or complete salary spend.
- Generates exactly the requested lineup count and reports mean, P90, P10
  floor/risk, salary, and realized stack. Operations suggests six by default
  when switching to H2H, but an explicitly entered count is authoritative.

## Large GPP (`classic_large_gpp_v1`)

- Uses the GPP thresholds below, but preserves stack-safety candidates.
- Uses normalized mean/P90/correlation/leverage weights. When ownership is absent,
  leverage is exactly zero and its weight moves to P90/correlation.
- Cycles QB+1/QB+2 templates with zero/one required bring-back, rather than
  imposing one construction on the whole portfolio.
- Supports requested lineup count, global and player-specific max exposure,
  player-specific minimum exposure, minimum uniqueness, team/game caps, and
  custom stack templates.
- Persists concrete exclusion reasons such as position value/ceiling threshold,
  positional cap, team cap, zero projection, and backup-QB status.

## Small-field GPP (`classic_small_field_gpp`)

- Uses the broader post-eligibility Classic pool and the existing Large GPP
  scorer, stack templates, and ownership caps. It does not retune football rules.
- Generates a target of 120 distinct candidates (100–250 configurable), validates
  each Classic roster, and globally selects the requested lineups. Production
  availability and candidate-core caps apply during candidate admission and
  refill; selected-lineup exposure controls apply to the final portfolio.
- Reports the top 20 candidates with mean, summed player ceiling, score terms,
  QB stack and bring-back, primary game, ownership, RB/receiver construction,
  cheap-player role evidence, and correlation contributions. Also reports QB,
  stack, game, family, and player-exposure summaries.
- Accepts one optional `params.contest_urls` DraftKings Classic URL. It reports
  available economics and missing fields without changing lineup scores or
  selecting the number of contest entries.
- `params.exclude_opponent_teams` is a hard pool exclusion, using NFL team
  codes such as `DEN`. The optimizer removes every player facing those teams
  before candidate generation and rejects any final lineup that
  violates the rule. The UI starts with `DEN` for the current Week 2 policy;
  the saved run and HTML report record the active codes.
- New Classic small-field runs default to `params.availability_risk_mode =
  "conservative"`. OUT and INACTIVE players are excluded; DOUBTFUL players
  require a saved, reasoned override. Elevated-questionable players are capped
  at 25% of candidates and 40% of selected lineups, with at most one per lineup
  and at most 60% of selected lineups containing one. Full-role questionable
  players require timestamped full-practice and unrestricted-workload evidence;
  their caps are 50% of candidates and 60% of selected lineups. Normal non-elite
  candidates have a 70% ceiling; healthy elite candidates have a 90% ceiling.
- Production selection limits pairwise overlap to six players, QB exposure to
  60%, and normal non-elite skill-player exposure to 80%. It requires at least
  two distinct QB paths for a multi-entry portfolio and considers a third path
  and an alternative stack family within a 0.10 selector-point-per-lineup
  quality tolerance. Ownership remains diagnostic, not a soft selector term.
- The report begins with **Entry readiness**. Missing sourced market lines or
  selected ownership produce `DEVELOPMENT_PREVIEW`; corrupt source identity,
  late evidence, candidate underfill, illegal lineups, or production cap
  violations produce `BLOCKED`. Only a fully checked run is `ENTRY_READY`.
  Market values without a captured source and observation time stay null.

The legacy filter details below remain relevant to the historical Classic cash
and GPP strategy IDs.

## Frozen small-field candidate and portfolio diagnostic

Classic small-field runs accept `classic_solver_backend` (`bundled`, `native`,
or `auto`) and `classic_candidate_workers` (1–4). `auto` uses a `cbc` executable
on `PATH` when present and otherwise keeps the bundled CBC. Independent
QB-family construction solves and fixed QB-group seed generation can run in
parallel; exact discovery and admission then follow. The local UI requests
`auto` and four workers. For five-lineup Sunday Main runs, it also requests
205 seeds and an exact 205-candidate production pool. Other slate and lineup
settings retain their existing target. Choosing Classic small-field defaults to
five lineups.
Parallel discovery uses four workers only when `PYTHONHASHSEED=0` was set before
the backend process started. Otherwise the run uses one worker and saves the
fallback reason in `strategy_runtime.classic_solver`. The local backend launcher
sets the seed for its own processes or the launchd-managed API and worker. The
solver backend and worker count alter runtime only; they do
not change player projections, objective weights, or portfolio constraints.

The Operations **DraftKings contest URL (optional, one URL, reporting only)**
field accepts one Classic contest URL. Multiple pasted URLs are rejected before
the optimizer starts. Direct API requests with invalid optional contest context
retain any generated lineups and record the contest error in the small-field
report; contest metadata does not affect lineup scoring.

`scripts/audit_sunday_main_portfolio_frontier.py` reads one persisted optimizer
run and its exact projection and ownership run IDs. It verifies the saved 120
candidate scores, retains frozen eligibility and context adjustments, then
injects global raw-quality and production-selector solves plus the best legal
starting-QB and QB+1/QB+2 constructions with and without a bring-back. Canonical
player IDs deduplicate lineups. Candidate discovery has no exposure cap.

Run discovery and analysis separately so the candidate universe remains saved:

```bash
PYTHONPATH=. .venv/bin/python scripts/audit_sunday_main_portfolio_frontier.py \
  <OPTIMIZER_RUN_ID> artifacts/classic-expanded-discovery.json --discover-only
PYTHONPATH=. .venv/bin/python scripts/audit_sunday_main_portfolio_frontier.py \
  <OPTIMIZER_RUN_ID> artifacts/classic-portfolio-frontier.json \
  --from-discovery artifacts/classic-expanded-discovery.json
```

The analysis reports candidate-level ownership completeness, the normal
ownership-enabled scoring profile only for complete candidates, context and
correlation shadows, 3/5/7-point mean governors, and production-score versus
worst-shadow-rank portfolio frontiers. Portfolio selection distinguishes paths
by QB, primary game, and stack family; it tests both 6- and 7-player overlap.
Missing ownership remains unavailable for that candidate. If optimal-lineup
probabilities are absent, leverage remains unavailable even when ownership is
complete. This is a diagnostic only; it does not write optimizer runs or change
production weights, projections, or user entry counts.

## Cash defaults (projection-weighted)
- QB: keep top 10 by projection; drop below 14 proj unless ceiling/$1k ≥ 2.6.
- RB: keep top 18; drop below 8.5 proj unless ceiling/$1k ≥ 3.0.
- WR: keep top 28; drop below 7 proj unless ceiling/$1k ≥ 3.3; value floor 2.8+/k.
- TE: keep top 14; drop below 6 proj unless ceiling/$1k ≥ 3.1; value floor 2.8+/k.
- DST: keep top 10; drop below 5 proj.
- Team caps: WR ≤3, TE ≤3, RB ≤3 per team.
- Global value screen: ceiling/$1k ≥ 2.6 (non-DST), WR/TE ≥ 2.8.

## GPP defaults (ceiling + leverage friendly)
- QB: keep top 14 by ceiling (p90); drop below 17 unless ceiling/$1k ≥ 3.0.
- RB: keep top 20; drop below 11 unless ceiling/$1k ≥ 3.0.
- WR: keep top 34; drop below 10 unless ceiling/$1k ≥ 3.4; always keep WR ≤4.5k with ceiling/$1k ≥ 3.4.
- TE: keep top 16; drop below 8 unless ceiling/$1k ≥ 3.4; keep TE ≤4.5k with ceiling/$1k ≥ 3.4.
- DST: keep top 12; drop below 6.
- Team caps: WR ≤4, TE ≤3, RB ≤2 per team.
- Global value screen: ceiling/$1k ≥ 3.0; WR/TE ≥ 3.4.

## Stack safeguards (applied after filters)
- Ensure each team keeps: 1 QB (best ceiling), top 2 pass-catchers (WR/TE), top bring-back from opponent (WR/TE/RB), and one ≤4k WR/TE relief option.
- Caps enforced before safeguards; safeguards re-add missing stack pieces.

## Stacking constraints (classic optimizer)
- Cash defaults to the versioned unconstrained replay baseline (`classic_cash_unconstrained_v1`), with no required QB pairing or bring-back.
- Cash candidates are `classic_cash_qb_pair_v1` (at least one same-team pass catcher) and `classic_cash_qb_pair_bringback_v1` (the same pairing plus an opposing WR/TE). These remain unvalidated until `DT-402` walk-forward replay is complete.
- GPP preserves the existing versioned legacy default (`classic_gpp_double_bringback_v1`): at least two same-team pass catchers with the QB and an opposing WR/TE bring-back.
- Pass-catcher set = WR/TE (optionally RB if `include_rb_in_stack=True`).
- Bring-back positions default to WR/TE (optional RB).
- If filtering removes too many stack mates, the per-QB min is relaxed to the available count (warns in logs); bring-back is skipped with a warning if no eligible opponent remains.

## Bonus ideas (not auto-applied; need extra data)
- Drop RBs with snap% < 35% unless ceiling/$1k ≥ 3.8.
- Drop WR/TE with routes < 18 or targets < 4 unless ceiling/$1k ≥ 3.6 or they’re part of a stack you keep.
- Prefer DST facing QBs/OL allowing ≥8% sack rate (keep top 8).

## Deterministic cash-policy replay

`classic_cash_stack_replay_v2` evaluates the three registry policies on one historical week or every available week for a slate. It requires one exact `projection_run_id`, verifies a prior-period-only training contract, rejects a timestamp after slate lock, content-hashes all salary/projection/actual/field inputs, and stores the complete `classic_cash_v1` objective plus solver contract in the returned artifact. Postgame actuals are loaded only after each lineup is solved. Complete normalized fields add median, quartile, percentile, winner, and policy-margin evidence. Aggregates report worst/P10/P25/median field margin, lower-quartile mean, below-field-median rate, and lower-tail deltas versus the unconstrained policy. Cash/double-up and ROI outputs remain unavailable unless contest type and payout tiers are verified; rank ties are reported separately and do not enter win-rate denominators.

Use `POST /api/replay/classic-cash/stack-policies` or:

```bash
PGDATABASE=football_26_dev .venv/bin/python scripts/replay_classic_cash_stack_policies.py \
  --database football_26_dev --season 2025 --slate SUNDAY_MAIN --pretty
```

Current 2025 target actuals cover all nine classic roster spots, including DST. Eleven source-backed standings files are normalized into 1,852,485 entry results, including six complete Sunday Main fields. The replay calculates exact field-relative margins for those weeks but retains `performance_claim_eligible: false` because historical salary rows have post-lock ingestion timestamps rather than proven pre-lock snapshots. It also retains `cash_performance_claim_eligible: false` because the generic legacy files do not prove cash contest type or payout tiers. These outputs are useful diagnostics, not evidence for promoting a stacking policy.

## Implementation notes
- Showdown **Single-entry contest portfolio** accepts `params.contest_urls` (1–50 DraftKings `/draft/contest/<id>` URLs), `contest_selection` (`auto` or `enter_all`), optional `maximum_total_entry_budget`, optional `maximum_contests_to_enter`, and optional `manual_contest_metadata` keyed by `contest_id`. `POST /api/optimizer/contests/preview` exposes parsed public contest facts and unavailable fields. At run time the page is refreshed and the full embedded `window.mvcVars.contests` cash payout ladder is checked against the prize pool. Contest and lineup scores remain separate. The contest profit proxy blends independent rank outcomes and a shared-percentile outcome 50/50, comparing total prizes with total entry fees; counts 1–3 use exact rank distributions and larger counts use 2,048 fixed rank scenarios. Best subsets are reported for every feasible count. Searches are exhaustive through 10 URLs, then use exact counts 1–3 and beam search above that. The report recomputes best subsets at shared-rank weights 0/25/50/75/100%, brackets count changes to about 0.1% weight, and labels the default count ROBUST, SENSITIVE, or NEAR TIE (within 0.5 percentage points). For selected multi-contest subsets, a pair similarity proxy uses 45% player overlap, 25% Captain match, 20% script match, and 10% team emphasis match. Adaptive shared-rank weight is 25% + 75% × pair proxy; the joint lineup heuristic adds its payout-proxy change versus all A to the existing diversification credit minus normalized quality loss. Placement favors differentiated lineups in contests with larger field size × top-10 prize share. These are not measured correlations, calibrated lineup win probabilities, or ROI. For guaranteed contests within two hours of lock, current entries drive the effective field size, rake, and overlay snapshot; the report flags if the selected count changes versus its full-field reference.
- Showdown **Small-max GPP** (`showdown_small_max_gpp`) accepts zero or one DraftKings contest URL. With a URL, it verifies a 2–5 per-user entry limit and complete payout ladder, then compares the best lineup set at each count using the existing uncalibrated uniform-rank payout proxy. Without a URL, `params.small_max_maximum_entries` sets a generic 2–5 entry limit (default 5); `params.entries_to_use=auto` returns the strongest single lineup, while an explicit count builds the strongest feasible set up to that count. Generic mode reports quality, diversity, exposure, overlap, and candidate coverage without inventing contest fees, payouts, field size, EV, or ROI. Both modes use the same 30–50 generated candidates, single-entry Showdown quality scoring, mean ≥85% and summed-P90 ≥90% candidate floors, and configurable Captain/core/starting-QB/cheap-punt exposure rates (all default 100%). Each count searches combinations of the top 20 qualified candidates. This is an uncalibrated ranking heuristic; the player projection model is unchanged. Legacy `showdown_3max_gpp` still requires one URL and a verified three-entry limit.
- The legacy `showdown_gpp_portfolio_v3` backend can still receive an attached five-entry contest URL, though Operations now routes new small-max selections through `showdown_small_max_gpp`. The backend `params.contest_urls` accepts one DraftKings contest URL and `manual_contest_metadata` for unavailable facts. The run verifies a complete payout ladder and `maximum_entries=5`; an observed DraftKings page limit cannot be overwritten by manual metadata. The report includes contest economics, payout ladder, requested cost, and actual generated-lineup cost. Candidate generation, exposure rules, lineup selection, and five-lineup target are unchanged; no 1–5 entry-count optimization or calibrated payout probability is implied. A saved URL can be reused through the contest library.
- `target.saved_dk_contest` stores a contest URL and its season/week/slate, format, and type. `target.saved_dk_contest_observation` appends raw embedded DraftKings payload, parsed facts, economics, source hash, observation time, and fetch errors on save, preview, and optimizer refresh. `GET/POST /api/optimizer/contests/saved` lists/saves catalog rows; `GET /api/optimizer/contests/saved/{contest_id}/observations` exposes dated history; `DELETE /api/optimizer/contests/saved/{contest_id}` archives without deleting history. The Operations contest library supports Classic and Showdown; in the Showdown single-entry mode, saved URLs can be added to the available pool. Catalog identity is DraftKings contest ID; reassignment to a different slate or format is rejected.
- In Showdown single-entry modes, `params.enforce_single_te` is applied to every generated candidate and checked again after portfolio assignment. The HTML metadata records the active value. Candidate reports decompose the weighted selector score and its nested solver score, then show mean, P90, chalk, and ownership-score trade-offs versus the best-quality candidate. Duplication and script have no direct selector weight; any effects through solver, correlation, or context remain visible in those components. The diagnostic flag for a ceiling sacrifice is descriptive and does not alter ranking.
- Operations defaults the optimizer to **Latest completed (automatic)** for the selected season, week, and slate, and lists older completed projection runs as explicit choices. It sends the exact chosen run ID, including the automatic latest, without moving the governed database active pointer. Optimizer preflight accepts multiple completed versions because that choice is deterministic; replay still requires an exact run selection. When automatic GPP ownership refresh is enabled, the UI labels missing ownership as pending and updates preflight after refresh. A Showdown starter-QB failure includes the selected projection ID and cutoff so stale snapshots can be identified.
- The explicit `contest_format` and `objective` request fields resolve the legacy solver mode; `params.contest_type` remains a compatibility fallback. Showdown (`captain`) skips classic filters.
- For classic cash, `params.stack_policy_id` selects one of the three registry policies exposed by `Operations` under `Cash Stacking Policy`. A versioned policy cannot be combined with legacy stack override fields. Explicit legacy overrides remain supported as `classic_cash_custom_v1` for compatibility and are labeled unvalidated.
- Classic cash uses `classic_cash_v1`: 25% mean + 35% median + 40% P10 floor + up to 1.25 role-certainty points - up to 3.0 times normalized median-to-floor fragility. Missing quantiles collapse to mean, preserving the previous projection score.
- The exact objective configuration is stored in `target.optimizer_run.objective_config_json`, while the exact stack policy is stored in `constraint_config_json`; player terms and repeated lineup policy live in `lineup_player.player_json`, and lineup aggregates are stored in `target.lineup` plus `cash_objective` and `stack_policy` explanation rows.
- In `football_26_dev`, the optimizer falls back to `public.curated_salary` for legal DraftKings positions/site IDs and `target.player_projection` for outcome distributions. Missing role/DST projection evidence remains zero and inspectable; it is not synthesized.
- Value metrics use `p90` as ceiling and `salary`/1k for rate-of-return comparisons.
- Classic strategy filters run only for classic slates; stack preservation ensures viable QB + pass-catcher + bring-back combos remain. Showdown retains every positive FLEX base salary, including values below the classic $2,000 floor, preserves the paired CPT site ID, includes kickers, and excludes non-`ACT` or roster-missing players whenever current weekly-roster evidence is available. Team defenses remain eligible without a player-level roster row.

## Market evidence and entry export

`scripts/capture_nflverse_markets.py` records each requested slate's current
nflverse game total and spread in `target.market_snapshot`, linked to immutable
source bytes and an ingest run. `--dry-run` checks coverage and game identity
before writing. The source `spread_line` is the expected home margin; the
normalized `home_spread` is its negative. The projection loader accepts only
fully sourced observations captured and ingested by its cutoff and before
kickoff. Historical schedule lines without an observation timestamp remain
training reconciliation evidence, not current market observations.

Classic readiness counts slate games with complete sourced market context,
reports oldest/newest observation and per-game age, and shows missing, aging,
stale, and invalid games. Defaults are fresh at six hours or less, aging through
24 hours, and stale beyond 24 hours. `market_fresh_hours`,
`market_stale_hours`, and `market_stale_policy` can change the thresholds and
stale warning/blocker policy. A stale line in the last six hours before first
kickoff blocks entry. Missing market evidence is a development preview; a
sourced but invalid line blocks entry. A new capture and projection/optimizer
run are needed for a later refresh; frozen runs retain their prior cutoff.

In a multi-entry `classic_small_field_gpp` run, every selected RB/WR/TE at 100%
requires a reasoned approval saved before first kickoff. This changes the
status to `ENTRY_READY_WITH_APPROVAL_REQUIRED` when all other checks pass.
The results view shows the original portfolio and the best comparable saved
candidate portfolio capped at 80%, including selector, mean, summed player
P90, overlap, and QB-path costs. Approval keeps the original; an 80% or lower
custom cap creates a new optimizer run. Approval and cap decisions are
append-only and tied to the originating run and player. The export gate checks
readiness and outstanding approvals. DST and QB do not use this approval gate.

## Classic small-field diagnostics

For `classic_small_field_gpp`, candidate discovery combines the normal sequential generator with exact legal global highest-mean, highest-P90, and highest-selector solves; best QB-family and exact QB+1, QB+1+bring-back, QB+2, and QB+2+bring-back solves for every viable starting QB are also injected. Canonical player IDs deduplicate lineups. Discovery proposes legal alternatives; production candidate admission enforces player and injury exposure caps, and refill searches additional stack templates without relaxing those caps. Final portfolio selection applies its own exposure constraints. The report identifies global raw-quality lineups absent from the sequential set.

For large Classic candidate pools, `classic_candidate_workers=2..4` with `PYTHONHASHSEED=0` generates the seed pool in deterministic QB groups. Each group applies the same roster, stack, injury, and candidate exposure controls; the groups merge in fixed order. `classic_candidate_pool_size` sets the seed count (100–250). The optional `classic_production_candidate_pool_size` sets an exact production target between the seed count and 250; without it, the expanded discovery count remains the target. Production admission chooses the largest jointly cap-feasible subset and then ranks it by selector score. If the subset is short, constrained refill runs across the same worker count and reports its attempts and elapsed time. The frozen input snapshot records the generation method, worker count, and both candidate targets. Locked players or too few starting QBs use the sequential seed generator with a recorded reason.

The optional `scripts/freeze_classic_thesis_shadow.py` analysis runs after a
completed Classic small-field optimizer run and before its saved first kickoff.
It reads only the frozen run's candidate pool, risk and market evidence. A
directional thesis groups by canonical game, canonical QB ID, pass-catcher
count, and bring-back presence; opposite QBs share the canonical game. The
shadow tests selector gaps of 0.05, 0.10, 0.15, and 0.20, reports conservative
Pareto dominance and family depth, and solves 1/3/5/10/20-entry portfolios
lexicographically for non-dominated thesis coverage, game coverage, and the
existing selector. It can widen beyond the 0.20 tolerance for larger portfolios
but reports that choice. The append-only `target.classic_dynamic_thesis_shadow_v3`
row records all candidate identities, family membership, portfolio allocations,
source hashes, and the pre-lock freeze time. Production projections, weights,
constraints, lineup selection, readiness, and export remain untouched.

The Week 4 completion adds an offline, separately hashed opportunity-cost
supplement through `scripts/complete_week4_thesis_analysis.py`. QB controls
preserve a WR+TE double stack, no bring-back, RB flex, and at least four
original non-QB players, with free-structure sensitivity solves. Required-player
diagnostics search the saved hard stack minimums and all exact templates;
restricting the latter alone can miss legal three-catcher constructions.
The 0.20 shadow quality criterion must not be reported as a production
rejection rule: saved joint admission uses candidate target, exposure/risk
constraints and selector competition, and its residual rejection counter is
not a player-specific cause log. `scripts/render_week4_thesis_completion.py`
reproduces the full report from saved evidence. Its correlation-aware Pareto
screen is diagnostic and does not change the frozen v3 joint portfolios.

The small-field football objective uses fixed mean/P90/correlation weights regardless of slate-wide ownership coverage. A player's missing ownership is retained as null, never scored as zero. A lineup receives ownership sum, log ownership, chalk, and leverage diagnostics only when all nine ownership values exist; optimal-lineup probability is additionally required for leverage. Lineups with missing ownership show ownership-derived aggregate terms as unavailable. The fixed profile has no soft ownership term or active ownership cap, so candidate coverage alone does not change selector score. Candidate diagnostics include global mean/P90 loss, weighted raw-quality sacrifice, context/correlation objective gain, sacrifice per positive bonus gain, and 3/4/5/6/7 mean and 3/5/7 P90 guard frontiers. These guards do not constrain production selection.

The report also includes ownership source and coverage, concentration and positional ranks, low-cost opportunity evidence, RB receiving usage from current pregame fields or labeled lagged three-game fields, bring-back rule outcomes, and game-environment raw and selector contributions. The raw opportunity-eligible count precedes the Classic strategy gate; the report labels that stage separately. Exact top-ten QB-family diagnostics run by default; set `classic_qb_family_diagnostics=false` to skip those additional solves. No stack/context weight or permanent quality-threshold change was made.

When the selected projection run contains v4.2 role lineage, the Classic small-field report also lists each skill player's measured offensive-role importance and confidence beside mean, P90, salary/value, ownership, candidate-pool appearances, and selected-lineup appearances. This is a diagnostic comparison; it adds no selection score or exposure rule. Missing role evidence is shown as unavailable.

Each Classic small-field candidate and selected lineup also receives a football sanity diagnostic: QB-stack game script, measured skill-player role, cheap-player opportunity support, omitted central players on represented offenses, and players whose measured role rank exceeds both team projection ranks. Central-player checks require medium or high role confidence. Omission explanations use candidate and selected counts; they do not assert that salary, ownership, or correlation was the causal blocker without a counterfactual solve. These checks do not change optimization weights or hard rules.

The Classic optimizer results view and downloaded report now include an RB player-why table, lineup football-sanity flags, and portfolio counts of flagged constructions. RB evidence includes frozen mean/P90, salary, measured role, lagged snap/carry/target trends, receiving-role strength, team market, model version, and saved one-feature role probes. The report explicitly labels missing same-slate external benchmarks and unavailable SHAP or market counterfactuals. Same-team RB+DST, multiple offensive players on a team implied below 20, and a 15+ mean RB on a team implied below 20 are informational flags only. The strongest alternative and mean/P90/selector cost are computed within the saved candidate universe and labeled with that scope. All diagnostic fields are stored in the Classic small-field report within each new optimizer run; previous runs retain their original report. No projection or optimizer score changes result from these flags.

The pregame role export `scripts/export_pregame_role_snapshot.py` reads a specified saved projection run and canonical-ID-linked weekly roster rows. It includes every salary-listed RB/WR/TE, even when role data is missing, and lists unavailable fields per player. The earlier exported Sunday Main snapshot reported 225 measured role scores among 425 salary skill players; its weekly roster supplied broad positions for 417, not ordinal depth ranks. At that snapshot, no Sunday pregame-context rows or route/red-zone counts existed locally. The fresh Week 4 context and practice coverage is documented in the readiness report linked above. Reports now show team target and RB-carry allocation proxies, missing role players by team, and exact QB+1, QB+2, QB+1+bring-back, and QB+2+bring-back diagnostics for the top ten QBs by mean/P90/value rank. Full pass/rush attempts remain unavailable rather than inferred from target/carry proxies. Candidate concentration displays overlapping projection/value ranks, salary-swap evidence, stack-boundary counts, role evidence, correlation-rule counts, and ownership when covered; it is not causal attribution. Exact QB-family diagnostics are enabled by default for new Classic small-field runs and can be disabled with `classic_qb_family_diagnostics=false` to avoid the additional solver calls.


### Optional Classic planning controls

The Small-field GPP diagnostic selector accepts **Max primary QB stacks per game**
(`portfolio_constraints.canonical_game_cap`) and **Max appearances per skill player**
(`portfolio_constraints.skill_max_appearances`), integer counts from one through
the requested entry count. The game cap combines both QB directions in a canonical
game; one-off players remain possible in other entries. Skill caps cover RB/WR/TE
and preserve tighter availability or explicit player caps. Conflicting locks/caps
fail validation. Blank controls preserve existing defaults.

**Expanded candidate discovery (slower)** (`classic_expanded_discovery=true`)
opts into the existing common-frame mandatory research sweeps, with at most fifty
rosters per eligible QB in its frontier enumeration. Final selection uses the full
known legal reference with ordinary selected exposure and availability controls;
candidate admission caps do not thin that opt-in reference. This is bounded
discovery, not exhaustive coverage or validated large-field performance. At one
entry, automatic multi-entry QB/core diversity caps are omitted; explicit caps and
the existing elevated-risk budget remain enforced. Counts must be re-solved, and
Game/Skill appearance controls must be cleared or adjusted when changing count.
Expanded-preview screens and readable exports qualify readiness as checks of saved
inputs and roster rules; contest assignments and final inactives still need review.

See [Week 4 Sunday contest decision](../../WEEK4_SUNDAY_CONTEST_PROFILES_AND_PORTFOLIO_DECISION.md)
for exact reproduction settings, reviewed manifests, and entry-specific clearance.
