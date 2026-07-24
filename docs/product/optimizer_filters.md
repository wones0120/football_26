# DraftKings NFL Classic Optimizer Filters

Practical, conservative filters that trim the player pool before PuLP runs while keeping common stack pieces and value outs. These defaults are implemented in `backend/services/optimizer.py` via `_apply_pool_filters`.

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
- The explicit `contest_format` and `objective` request fields resolve the legacy solver mode; `params.contest_type` remains a compatibility fallback. Showdown (`captain`) skips classic filters.
- For classic cash, `params.stack_policy_id` selects one of the three registry policies exposed by `Operations` under `Cash Stacking Policy`. A versioned policy cannot be combined with legacy stack override fields. Explicit legacy overrides remain supported as `classic_cash_custom_v1` for compatibility and are labeled unvalidated.
- Classic cash uses `classic_cash_v1`: 25% mean + 35% median + 40% P10 floor + up to 1.25 role-certainty points - up to 3.0 times normalized median-to-floor fragility. Missing quantiles collapse to mean, preserving the previous projection score.
- The exact objective configuration is stored in `target.optimizer_run.objective_config_json`, while the exact stack policy is stored in `constraint_config_json`; player terms and repeated lineup policy live in `lineup_player.player_json`, and lineup aggregates are stored in `target.lineup` plus `cash_objective` and `stack_policy` explanation rows.
- In `football_26_dev`, the optimizer falls back to `public.curated_salary` for legal DraftKings positions/site IDs and `target.player_projection` for outcome distributions. Missing role/DST projection evidence remains zero and inspectable; it is not synthesized.
- Value metrics use `p90` as ceiling and `salary`/1k for rate-of-return comparisons.
- Filters run only for classic slates; stack preservation ensures viable QB + pass-catcher + bring-back combos remain.
