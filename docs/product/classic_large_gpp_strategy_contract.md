# Classic Large-GPP effective strategy and replay

`classic_large_gpp_v1` uses `classic_large_gpp_effective_strategy_v1` in
`classic_strategy_contract.py`. It serializes ordered canonical Player inputs,
eligible IDs and ranking policy, generation options, resolved runtime config,
requested/effective game cap and source, metadata, implementation/CBC hashes,
execution mode, declared research deviations, and checksums. App runs and
production/parity replays execute the same contract. Saved optimizer-run JSON
already supports this payload; no database schema or environment change is needed.

The service now checks an explicit overlap against the constructed contract's
Requested, Effective, Source and resolved solver overlap before execution.
The browser compares the returned saved contract/report with its submitted
snapshot and independently recounts intersections using canonical player IDs;
a mismatch raises an error instead of accepting a defaulted result.
Operations displays all six **Portfolio settings to submit** immediately above
Run Optimizer from that same request snapshot. Before fetch, the API client
compares the exact serialized body with the snapshot; a mismatch blocks submission.
Before preparing inputs, the click handler also compares actual native controls
with controlled React values and the snapshot. The collapsed **Last submission
diagnostics** retains the trace locally; queued params preserve it and the API
adds server-derived parsed and saved-contract requested values. These diagnostics
do not affect projections, player assessments, or optimizer constraints.
The [live overlap verification](../../CLASSIC_LARGE_GPP_LIVE_OVERLAP_UI_FIX.md)
records full-app production-build browser evidence and historical limitations.

The contract resolves existing ownership/leverage fallbacks, small-slate team
caps and standalone long-shot configuration using the same runtime helper as
execution. Neither the nominal generic rule profile nor a legacy stack-description
field overrides the executed configuration. Eligibility thresholds and initial
candidate/team caps share `classic_candidate_policy.py`; stack safety addbacks
can exceed initial caps. The full ordered final frame remains the replay input.

Production generation is sequential exposure-aware ILP. Accepted candidates are
the selected portfolio. The serialized template cycle, legality, tag/ownership
caps, objective and normalization, player limits, and overlap determine each
next candidate region. The trace retains region/objective coefficient hashes,
remaining exposures, prior rosters, template, blocked primary games and solver
status. An Optimal lineup solve does not prove a joint portfolio optimum.

The default template cycle is filtered against the selected per-lineup team and
game maximums before the configuration is frozen. The QB counts toward both:
`max_players_per_team=2` allows `(1, 0)` and `(1, 1)`, but excludes QB + two
teammates. A game maximum of two permits only `(1, 0)`. Maximums do not require
that many selected players. Explicit stack templates that conflict with either
maximum fail clearly instead of being weakened. Caps too small for the common
QB + one teammate floor also fail clearly.

Lineup options accepts 1–500 entries. Above 50 entries, Classic generation reuses
the same full-frame correlation terms and captures the matched control LP only
for the first lineup to keep bulk runs' diagnostic memory and solve count bounded.
The frozen effective contract records `control_comparison_scope`; all lineups
retain their production objective/feasible-region hashes, selection trace, and
independent exposure/overlap/game validation. Ranking weights are unchanged.

`max_lineups_per_primary_game` is omitted/null for no cap or a positive integer.
A canonical sorted uppercase QB team/opponent pair is independent of QB direction
and of per-lineup player/game counts. Each accepted primary game consumes one
budget unit; when full, all QBs from both teams are blocked in the next solve.
Player caps are unchanged, and infeasible selection never relaxes the cap.
Small-field selection and its independent final audit use the same identity.

## Execution modes

- `PRODUCTION`: exact named strategy with requested user constraints.
- `PARITY`: same production path, frozen frame and configuration; no deviations.
- `RESEARCH_SHADOW`: explicit deviations required. Sequential cap sensitivities
  replay through the shared pipeline. Expanded discovery has a separate labelled
  research command, generation trace, full finite candidate pool and selector
  contract. Production replay rejects an expanded generation plan.

Every saved contract checks its content, effective configuration and current
implementation/solver fingerprints. Code/platform/solver drift requires a new
explicit parity check; it is never silently treated as exact replay.

## Frozen fixture

The first fixture is app run `d0e2ff8f-96cd-4fc0-ac7e-8297d4504701`, 2026 Week 4
Sunday Main, five entries and 80% max exposure. Its legacy snapshot freezes 154
final solver rows and its immutable eligibility ledger confirms the same IDs.
The old run did not retain complete historical upstream raw inputs or a broad
candidate pool. Replay starts at this documented final-frame boundary, uses no
current database reads, and compares saved per-step feasible models and captured
primary coefficients to the new shared execution.

```sh
.venv/bin/python scripts/audit_classic_large_gpp_parity.py
.venv/bin/python scripts/replay_classic_strategy_contract.py \
  --contract artifacts/classic_large_gpp_parity/d0e2ff8f/A_no_cap_contract.json \
  --output /tmp/classic-large-gpp-replay.json
.venv/bin/python scripts/research_classic_large_gpp_discovery.py
```

The first command verifies fixture checksums, IDs and all projections/P90, ledger,
resolved config, five accepted roster sets, region/coefficient fingerprints and
primary/report scores. A mismatch is classified and stops later research. It
then evaluates no cap and caps 4/3/2 at the same five entries/80% exposure.
The third command requires parity PASS, uses the same eligible frame/scoring and
five template slots, and labels its broader generation and finite joint selection
as `classic_large_gpp_v1 + expanded_discovery`.

Local evidence is under `artifacts/classic_large_gpp_parity/d0e2ff8f/`; the compressed
archive and SHA-256 manifest preserve the full fixture, original source capture,
contracts, traces and finite candidate pool. Extract it at repository root before
rerunning on the matching implementation/solver. The exact selected portfolios,
exposures, risk buckets and decision costs are in
[the comparison report](../../CLASSIC_LARGE_GPP_APP_CODEX_PARITY_AND_GAME_CAP.md).


## Optional UI portfolio controls

See [Classic Large-GPP UI portfolio controls](../../CLASSIC_LARGE_GPP_UI_PORTFOLIO_CONTROLS.md).
`max_lineup_overlap` (0–8) overrides the existing seven-player overlap default.
`elevated_player_max_exposure` (rate 0–1) caps each existing `questionable_elevated`
player at floor(requested entries × rate), intersecting stricter player/global caps.
`max_elevated_players_per_lineup` (0–9) independently limits elevated-player counts.
Omitted/null controls add no policy. The application freezes the existing cutoff-safe
classifications in the same contract; risk controls never import Small-field defaults.

`portfolio_controls_report` exposes independently counted achieved values, six
requested/effective/source rows, active constraints and saturated budgets. Underfilled
reports remain failed and can be reopened from recent history. No limits are relaxed.
The immutable d0e2ff8f fixture regression compares the current shared executor with
original roster sets, five LP feasible regions/objective coefficients and scores.


## Overlap UI propagation and recovery

The two UI launch paths snapshot `classicOptimizerControlParams` using the submitted
strategy before any await. Large-GPP writes explicit overlap as a top-level
`params.max_lineup_overlap`; the application request snapshot sends explicit null
for Strategy default, resolving to 7. Older helper-only fixtures also cover omission.
Small-field retains
its separate `portfolio_constraints.max_lineup_overlap` and minimum uniqueness;
Showdown receives neither Classic control set.

Large optional preferences use `football-26-classic-large-gpp-controls`. Overlap
remains separate from Small-field form state and survives strategy switches/reload.
Invalid saved sibling fields now fall back individually. The next-request preview
is form information; it never supplies Requested in a saved report. Large controls
and mode selection lock during request preparation so later edits cannot be
mistaken for the captured request. Returning from Showdown restores Large volume.

See [propagation investigation](../../CLASSIC_LARGE_GPP_OVERLAP_UI_PROPAGATION_FIX.md)
and [reproducible regression workflow](../../ui/tests/OVERLAP_E2E.md). Production
strategy/scoring/defaults were unchanged in this fix. The historical run evidence
establishes omission before API processing; it does not record historical React
state or prove a specific browser event caused it.


## Construction research application

`enforce_single_te` is now explicit in newly saved Requested/Source metadata and
portfolio settings. The UI persists its existing checkbox, default on. Off allows
TE FLEX and removes only the single-TE inequality; all other constraints remain.
GET results derives an actual-roster `construction_summary` without solving. Old
requests and contracts are not rewritten.

`POST /api/optimizer/results/{job_id}/construction-review?entry=1` is an explicit
user action. It verifies saved checksums and uses frozen eligible Players, resolved
config and full-frame normalization with the shared production `_build_lineup`.
It uses the current explicit choice from the existing single-TE checkbox, labels any
difference from the saved choice, and retains every other pinned setting. It retains
the selected step's minimum template and labels conflicts rather than
silently lowering it. Exact counts are diagnostic restrictions, never allocation
quotas. Individual and replacement solves are distinct; replacement retains all
other entries, risk/exposure/overlap/game budgets and minimums. No outputs become
an optimized portfolio. Old implementation differences are labelled current
production on frozen inputs; standard replay still requires matching hashes.

Named `missing_pass_catcher_*` and `missing_bring_back_*` guards exclude QBs that
cannot meet positive step minimums. No other original constraints or objective
coefficients change. See [application audit](../../CLASSIC_CONSTRUCTION_RESEARCH_APPLICATION.md)
for reachability, taxonomy, evidence limitations and the next user-initiated steps.
