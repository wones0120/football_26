# Opponent starting-QB context (shadow only)

`backend/app/product_services/opponent_qb_context.py` provides `QBContextIndex` and `FEATURE_COLUMNS` for isolated DST research. It is **not imported into the live canonical feature list or projection scorer**. No numerical backup-QB adjustment is active.

The input contract requires canonical player UUID, team, season/week, completion and source-availability clocks, source row ID and observed QB counts. Eight prior appearances supply sack, interception, sack-fumble-lost, passing-efficiency and rushing features, with sample counts/missing indicators. Dropbacks are attempts+sacks; QB rushing is not charted pressure escape. Missing values stay missing. Train-only imputation belongs to the fitting caller.

`context(..., strict_source_clocks=True)` rejects same/future periods, missing/later completion clocks and unavailable sources. Optional sourced starter evidence needs matching team/UUID, a URI and both observed/received clocks before the decision. Inferred starters stay uncertain. Without acceptable evidence, the historical proxy is the previous completed team game's primary-dropback QB; ties remain unknown. Actual target-game starters or post-decision inactives must never be supplied as pregame historical evidence. Caller must reconcile availability before supplying its expected starter.

Retrospective event-time mode is an explicit diagnostic opt-in, never a claim that later-ingested records existed before historical lock. The captured experiment uses conservative kickoff+24h completion boundaries and only prior weeks. Current starter scenarios can be evaluated separately without assigning invented probabilities.

`dst_label_lower_bound_violation` checks whether a DK DST total falls below opposing QB sacks +2×INTs −4. Missing inputs return unknown; passing is not completeness certification. It never rewrites outcomes.

The [October15 evidence and ablation](../../research/opponent_qb_context_20261015/v1/REVIEW.md) contains frozen inputs, source hashes, chronological splits, baseline/extended metrics, calibration and held-out predictions. The2025 total-point MAE did not improve;2026 DK labels include33 impossible totals and were withheld. Historical starter-change effects lack reliable archived pregame evidence. Activation is not justified. Offense/team-outlook propagation remains separate research.

Reproduce the frozen experiment:

```sh
PYTHONPATH=. .venv/bin/python research/opponent_qb_context_20261015/v1/validate_shadow.py
PYTHONPATH=. .venv/bin/python research/opponent_qb_context_20261015/v1/render_review.py
PYTHONPATH=. .venv/bin/python -m pytest backend/app/tests/product/test_opponent_qb_context.py -q
```

No config, migration or dependencies were added. Live model values and user settings are unchanged.

The subsequent [DST scoring reconciliation](dst_scoring_reconciliation.md) verified and versioned the affected labels, including neighboring seasons and duplicate slate copies. Its repeated matched comparison now includes corrected 2026 DK outcomes; the opponent-QB extension still does not improve point MAE. The original study and its withheld-label decision remain preserved.
