# Forward opportunity shadow model

The production projection and optimizer remain unchanged. `backend/app/product_services/forward_opportunity.py` provides a read-only comparison path from football role to opportunity to component fantasy points.

## Forecast path

- Team pass attempts, rush attempts, and offensive touchdowns use a ridge model fit on strictly earlier team games. Offensive plays are a **pass-attempt plus rush-attempt proxy**; sacks and kneels are unavailable here.
- Player target and carry shares blend the prior eight games, prior three games, and last game. The numerical weights, source period, role multiplier, and confidence are retained per player. Measured role importance increases the opportunity allocation monotonically when other inputs are held fixed.
- Player allocations are bounded by forecast team target and carry budgets. Unassigned opportunities remain in explicit unallocated buckets.
- Passing, rushing, and receiving components use prior player efficiency shrunk toward position rates. Touchdowns come from a low-confidence team forecast and opportunity shares because red-zone and goal-line evidence is unavailable. The 50/50 hybrid mean combines the component mean with the existing direct mean; this coefficient is diagnostic and is **not** used in production.
- Missing player history, team volume, or touchdown split is reported as unavailable. The module does not fill absent current-year usage with invented values.

## Historical validation

Run `PYTHONPATH=. .venv/bin/python scripts/validate_forward_opportunity.py` to write `artifacts/forward-opportunity-shadow-2025.json`. The script joins raw weekly stats to canonical players through `player_alias` native NFL IDs. It evaluates selected 2025 weeks using only preceding games for each opportunity forecast and compares the hybrid with the current direct model on the same covered rows. It reports coverage, MAE, RMSE, bias, position and role slices, top-decile error, and a prior-week residual P90 proxy. That proxy is diagnostic; a comparable production ceiling model still needs validation.

Pass `--projection-run-id` and `--saved-optimizer-json` to apply the read-only current-slate diagnostic to another saved run. `--weeks` chooses the held-out historical weeks; the historical comparison currently targets 2025. The current-slate path includes any raw stats from the current season that existed at the saved projection cutoff and reports their coverage.

Historical raw files were ingested retrospectively. The evaluation prevents game-order leakage, but does not prove each source was available before each historical lock. Promotion requires stronger source-availability replay and competitive out-of-sample results. No optimizer strategy or production projection is changed by this workflow.
