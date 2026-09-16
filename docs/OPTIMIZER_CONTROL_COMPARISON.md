# Matched optimizer controls (OPT-007)

New successful optimizer runs store `optimizer_matched_control_v1` in
`results[lineup_index][0].lineup_control_comparison`. The existing
`GET /api/optimizer/results/{job_id}` endpoint exposes it, and the normal
`target.lineup_player.player_json` persistence path retains it across restarts.
No schema migration is required. Historical runs without a saved comparison
remain unchanged and show an unavailable message in the UI.

## What is held fixed

The control copies the exact PuLP feasible region at each production selection
step. This preserves the selected candidate pool and ordering, salary cap,
identity and eligibility filtering, roster and team/game limits, locks,
FLEX-only controls, exposure remaining, minimum-exposure requirements,
previous-lineup exclusions, uniqueness, stack template, and hard Captain rules.
It changes only the objective: player context adjustments and shared correlation
and format-specific soft rules are removed. Base mean/floor/ceiling weights,
leverage scoring, Captain position priors, and Captain multipliers are retained.
GPP normalization denominators also stay fixed. Upstream candidate filtering is
not rerun: this measures scoring within the same candidate pool.

Each control is an alternative at that exact scored-portfolio step. Controls do
not update production exposure counts or subsequent selections, and must not be
combined or exported as a separately validated portfolio. The scored solve and
its selected values are not mutated by the control solve. A failed control solve
fails the run rather than publishing an unverified comparison.

## Reading the result

Open **Compare with rules disabled** beneath a result lineup. It includes:

- Canonical-ID player swaps and Captain/FLEX role changes.
- Scored and control mean, Individual Ceiling Sum, salary, ownership sum, and
  leverage sum, with deltas defined as scored minus control. Missing evidence is
  unavailable, not fabricated as zero. Captain mean, ceiling, and salary are
  counted at their already-scaled values; ownership is counted once per player.
- Base-objective opportunity cost: the control optimum minus the scored
  lineup's score under the same rules-disabled objective. These are strategy
  objective units, not necessarily fantasy points.
- Every triggered context/correlation rule's scored contribution, its hypothetical
  contribution if applied to the control, and their difference. Actual control
  soft-rule contributions are zero. GPP objective weights and normalization and
  Captain context multipliers are included in these contributions.
- `selection_effect`: unchanged, rules-preferred selection, or an alternate
  optimum when the scored objective does not strictly prefer the selected lineup.

This is a joint ablation. Per-rule contribution differences do not establish
that a single rule independently caused a swap. Individual Ceiling Sum is the
sum of marginal player ceilings, never a jointly simulated lineup quantile.

## Replay

Expand **Comparison JSON and reproducible solver inputs** for the full report.
The replay payload contains the control model's coefficients and constraints,
SHA-256 checksum, solver/PuLP version, variable-to-canonical-player/slot mapping,
and original solved values. Replay uses no database or current projections:

```python
from backend.app.product_services.optimizer_control import replay_control

replayed = replay_control(comparison["replay"])
# replayed["objective"], replayed["selected_players"]
```

The recorded selection is preserved in JSON. The same solver reproduces tested
selections; different solver versions may choose another equal optimum. The
checksum validates the saved model before replay. Every new lineup requires an
additional solve and additional stored JSON; large portfolios cost more time
and storage. Saved comparisons can be read without solving again.

## Verification

Regression coverage includes Classic swaps and no-op controls, exposure/lock and
previous-lineup constraints, Showdown cash/GPP and Captain-slot changes, GPP
portfolio-step constraints, replay/checksum validation, and persistence through
the existing results API. The actual comparison component is also rendered with
fixture data at desktop and 390px width for visual checks.
