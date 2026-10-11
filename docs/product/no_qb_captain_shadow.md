# QB Captain paid-finish audit and shadow test

October 10, 2026. Live selections and projections remain unchanged.

## Historical evidence

Seven verified GPP fields across three slates; 32,498 entries, 162 unresolved full rosters excluded. Other imported contests lack verified paid-place evidence and are excluded from paid-rate comparisons.

Rates use all resolved entries of each Captain position, not only top-10% entries. Bounds treat ties crossing the paid cutoff as uncertain. Duplicate entries count separately. These are descriptive entry-weighted results, not independent trials or causal estimates. Weeks 1–4 were already inspected and are not holdouts.

| Captain position | Entries | Confirmed paid | Uncertain | Paid-rate bounds |
|---|---:|---:|---:|---:|
| DST | 1,357 | 63 | 0 | 4.64–4.64% |
| K | 635 | 68 | 4 | 10.71–11.34% |
| NON_QB | 27,206 | 6,620 | 358 | 24.33–25.65% |
| QB | 5,130 | 1,419 | 3 | 27.66–27.72% |
| RB | 11,725 | 2,666 | 319 | 22.74–25.46% |
| TE | 5,065 | 704 | 0 | 13.90–13.90% |
| WR | 8,424 | 3,119 | 35 | 37.03–37.44% |

| Slate | QB paid-rate bounds | Non-QB paid-rate bounds |
|---|---:|---:|
| Week 3 THURSDAY_NIGHT | 18.17–18.17% | 27.10–27.49% |
| Week 4 SUNDAY_NIGHT | 39.51–39.51% | 21.80–21.82% |
| Week 4 THURSDAY_NIGHT | 28.59–28.74% | 23.41–26.64% |

The sample does not support a blanket QB ban. WR Captain entries had the highest paid rate. QB results vary materially by slate; Week 4 Sunday Night also favored QBs over non-QBs collectively. Missing full payout ladders prevent expected-return estimates.

## Prospective test

Policy `no_qb_captain_shadow_v1`, 2026 Week 5 Sunday Night. Research-only restriction applied to the saved feasible candidate pool, preserving all existing eligibility, quality checks, forecasts and export checks. QB FLEX remains allowed. This tests shortlisting within available candidates, not fresh constrained candidate generation.

Three frozen arms separate the live incumbent from expanded shortlisting and the Captain-position restriction. Select by unchanged baseline mean, then marginal P90 for exact ties; this is not a calibrated paid-finish probability. No outcome data enters selection.

- **control**: 79.09 projected points. Drake London (CPT); Bijan Robinson (FLEX); Derrick Henry (FLEX); Michael Penix Jr. (FLEX); Matt Hibner (FLEX); Austin Hooper (FLEX).
- **no_qb_captain**: 80.18 projected points. Bijan Robinson (FLEX); Derrick Henry (CPT); Michael Penix Jr. (FLEX); Brian Robinson Jr. (FLEX); Matt Hibner (FLEX); Tyler Loop (FLEX).
- **unrestricted_shortlist**: 80.33 projected points. Bijan Robinson (FLEX); Drake London (FLEX); Derrick Henry (FLEX); Michael Penix Jr. (CPT); Matt Hibner (FLEX); Austin Hooper (FLEX).

Evaluate paid finishes first, then dollar returns only with verified payouts, and top-10%/top-1% placement. Existing result-import hooks refresh registered arms automatically; no automatic source download or live promotion. More independent slates are needed before changing production policy.

## Reproduction

```bash
PYTHONPATH=. .venv/bin/python scripts/audit_qb_captain_paid_rushing.py
PYTHONPATH=. .venv/bin/python scripts/shadow_single_gpp_shortlist.py --format showdown --source artifacts/single_gpp_shortlist_shadow/captain_input.json --output artifacts/no_qb_captain_shadow/new-shadow.json --no-qb-captain
```

The audit is read-only. The shadow CLI refuses overwrite and postlock freezing; it does not register automatically. Explicit registration uses `ShadowLearningService.register(snapshot)`. Artifacts are local research evidence, not runtime defaults.

Registration: `3cde9088d6ce36b8264546418446c694bfab05de8add3f5e4ee8b261eff18446`; status `pending_actuals`. Before/after hashes confirmed all Week 5 optimizer configurations and projection references unchanged. Validation: 27 focused tests passed; syntax and diff checks passed.

## WR/RB Captain follow-up

The user requested a separate `wr_rb_captain_shadow_v1` policy: only WR or RB at Captain; WR requires a same-team QB in FLEX; RB does not require any QB. Apply this with `--wr-rb-captain` instead of `--no-qb-captain` in the shadow CLI. The flags are mutually exclusive. All other frozen inputs and constraints remain unchanged.

On the same Week 5 Sunday Night candidate pool, this selects the same Henry-Captain roster as the previous no-QB challenger: Henry CPT; Bijan Robinson, Michael Penix Jr., Brian Robinson Jr., Matt Hibner and Tyler Loop FLEX. Salary $49,900; projected points 80.18. Live London Captain remains unchanged (79.09); unrestricted shortlist Penix Captain projects 80.33. These are baseline forecasts, not paid-finish probabilities. An identical roster across policies is not independent outcome evidence.

Artifacts: `artifacts/wr_rb_captain_shadow/shadow.json` and registration receipt. This is a shortlist test over saved candidates, not an exhaustive new generation pass. The registered comparison retains the live and unrestricted arms for postgame scoring through existing result imports. Focused validation: 29 tests passed, including same-team QB enforcement, opposing-QB rejection, and RB Captain without QB.

## Weeks 1–4 returned-shortlist replay

`scripts/replay_wr_rb_captain.py` uses the latest clock-eligible run per slate from the earlier weekly audit. It verifies saved roster hashes and baseline choice parity, filters the returned rosters using the WR/RB rule, and selects with the unchanged pregame projection ordering before loading outcome labels. Canonical IDs join actuals. No postgame generation, training or live changes.

Seven slates could be replayed. Six choices were unchanged. Week 4 Sunday Night changed from 111.37 actual points to 98.54; both missed both verified paid cutoffs. Week 3 Thursday remained 3/3 paid and Week 4 Thursday remained 2/2 paid. Total verified comparisons: 5/7 paid for both policies across three slates, not seven independent games. Week 1 Wednesday and Week 2 Thursday/Sunday/Monday have scoreable lineups but no verified paid evidence. Other scopes lack eligible pregame replay/results. Dollar-return improvement cannot be established without payout ladders.

This shows no paid-finish improvement within saved returned candidates. It does not answer whether fresh constrained generation or reconstructing hidden pools would improve results. Historical choices use the current projection-first selector on saved pregame candidates, not necessarily the lineups actually entered. Database timestamps do not independently certify immutable prelock capture. These previously inspected weeks are exploratory, not held-out validation.

Output: `artifacts/wr_rb_captain_shadow/historical.json`. Run: `PYTHONPATH=. .venv/bin/python scripts/replay_wr_rb_captain.py` (read-only database transaction).

## User-selected app default

At the user’s request, the Captain position dropdown now starts at `WR/RB only (default)` and submits `captain_positions: ["WR", "RB"]` for new Captain runs and the weekly pipeline. Other dropdown choices remain available. This is an explicit user preference, not a validated model promotion. Existing saved runs and API requests omitting the setting retain prior behavior. FLEX eligibility and model assessments are unchanged.

## RB Captain: QB optional

Live generation and final validation now exempt RB-Captain lineups from the minimum-starting-QB rule and the two-pass-catchers QB requirement. This permits zero, one or two QBs according to optimizer scoring and explicit user limits. WR/TE Captain continues to require its own starting QB unless the separate explicit No QBs override is enabled. Rule metadata uses `showdown_require_starting_qb_v2` and `showdown_multi_pass_catcher_qb_v2` with an RB-Captain exception. No forecasts or existing saved lineups are rewritten.

## Captain exposure control

`Max Captain exposure (%)` is visible in Lineup options beside lineup count. It uses the existing `captain_max_exposure` parameter, saved separately for Captain mode, with the unchanged 100% default. The UI displays the effective count using the existing round-up convention (40% of five = two). It limits each player at Captain only, not FLEX, though ordinary player caps still apply. No backend exposure semantics changed.

## Minimum player salary

Captain Lineup options now includes `Minimum player salary ($)`, stored per format and sent as `minimum_player_salary` (whole dollars, 0–50000). Blank omits the setting. The comparison is inclusive: base salary must be at least the entered minimum. $1,700 excludes base salaries of $1,600 or less, even if the Captain multiplier raises slot cost above the threshold. Selection filtering happens after model assessments; report exclusions use `user_minimum_player_salary` in the user-preference category. Locked players cannot bypass the floor. Final validation independently checks base salary (or slot salary divided by 1.5 for Captain when base is absent). Classic now supports the same API parameter but exempts DST, D and DEF positions; its UI label is `Minimum offensive player salary ($)`. Settings persist independently by format. No schema or projection changes.

Classic uses native salary without a Captain multiplier and checks all offensive players, including FLEX, in both candidate filtering and final validation. DST remains subject to existing platform/eligibility constraints but is exempt from this user floor. Locked offensive players cannot bypass the floor.

## Season-average team leader preferences

The app defaults `require_team_leader` to true and `require_home_team_leader` to false. Omitted API flags retain their false defaults. Home-only requires the first flag. Leaders are the highest prior-week season-average non-QB individual players (RB/WR/TE/K; DST excluded) on each team in the initial player pool, before user exclusions and salary restrictions. Any exact tied leader qualifies. No forecast is altered. Unambiguous native away@home game evidence identifies the home team; missing/conflicting evidence blocks home-only requests.

Each generated lineup must include at least one qualifying canonical player ID at Captain or FLEX; independent final validation enforces the same set. User exclusions never redefine leadership. If no leader remains eligible, the run fails with a preference conflict. These are user constraints, not validated predictions of actual scoring leaders. Saved run metadata under `strategy_runtime.team_leader_preference` records candidates, prior-game scores, season averages, required IDs, source lineage, home-team evidence and preference reason. Options are session controls and apply to both optimizer and weekly requests; they do not regenerate existing lineups.

## Classic positional salary controls

The app sends `minimum_qb_salary` and `minimum_rb_salary`, each defaulting to 4500 for Classic. Blank omits the parameter. Existing saved controls receive the defaults for missing fields; explicit null or custom values persist. Natural RB position includes FLEX. Candidate filtering and final validation enforce both the positional and overall minimum; locked-player conflicts fail. Exclusions retain `user_minimum_qb_salary` or `user_minimum_rb_salary` reasons and their original model assessment. These parameters are Classic-only; omitted API values impose no positional minimum.

## Classic season-average rank preferences

Classic dropdowns **Season-average QB/RB/WR/TE rank** default to QB/WR top 50% and RB/TE top 25%. Choices are 25, 50, 75, 100 (requires usable history), and No restriction. Missing saved fields acquire these defaults; explicit null/custom choices persist. API parameters `season_ppg_top_pct_qb`, `season_ppg_top_pct_rb`, `season_ppg_top_pct_wr`, and `season_ppg_top_pct_te` are optional and Classic-only; omission imposes no limit.

The league-wide universe includes players with at least one prior participating game in the selected season. Stat activity or positive offensive snaps establishes participation; snap-confirmed games with no stat row count as zero. Negative scores remain negative. Source native IDs resolve through canonical aliases; ambiguous identities, position conflicts, and conflicting scores remain unranked. Each position uses `ceil(N × percentage/100)` and includes ties. Rankings are computed before slate/user filtering, and natural-position limits apply at FLEX. DST is exempt. Players without usable history do not qualify under an enabled limit. Week 1, missing prior-week team coverage, or an empty position universe fails explicitly, with instructions to refresh inputs or choose No restriction. No constraint is relaxed to fill a request, including locked players.

`strategy_runtime.season_ppg_rank_preference` freezes per-player game scores, participating-game counts, averages, league counts/cutoffs, eligible canonical IDs, source ingest references, source hash, and coverage warnings before generation. Current historical imports can contain later source corrections; the period excludes current/future weeks but is not a reconstructed pregame data-vintage snapshot. This evidence is a user selection constraint, not model truth. Candidate filtering and independent final validation enforce it. Pool exclusions carry `user_season_ppg_rank_<position>` reasons while retaining model assessments. Both direct and weekly requests use the same controls.

Captain team-leader preferences now use prior-week season averages instead of projections. Require at least one defaults on; home-team-only defaults off. The leader may be Captain or FLEX. Missing/ambiguous history remains unranked; missing team history or Week 1 fails explicitly without falling back to projections. Frozen run metadata records prior-game scores, averages, source lineage and tied leader IDs. Existing historical runs are unchanged.
