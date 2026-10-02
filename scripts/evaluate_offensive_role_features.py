"""Time-ordered comparison of compact offensive-role model feature sets.

Example: PYTHONPATH=. .venv/bin/python scripts/evaluate_offensive_role_features.py
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sqlalchemy import create_engine

from Database.config import get_connection_string
from backend.app.product_services.canonical_projection_inputs import (
    BASE_FEATURE_COLUMNS, POSITION_FEATURE_COLUMNS, load_inputs,
)
from backend.app.product_services.predictions import TARGET_COL, blend_point_predictions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--week", type=int, default=2)
    parser.add_argument("--slate", default="THURSDAY_NIGHT")
    parser.add_argument("--validation-season", type=int, default=2025)
    parser.add_argument("--first-week", type=int, default=10)
    parser.add_argument("--last-week", type=int, default=18)
    parser.add_argument("--cutoff", default=None, help="UTC ISO timestamp; defaults to now")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    cutoff = datetime.fromisoformat(args.cutoff) if args.cutoff else datetime.now(timezone.utc)
    if cutoff.tzinfo is None:
        parser.error("--cutoff must include a timezone")

    engine = create_engine(get_connection_string())
    train, _, sources = load_inputs(
        engine, season=args.season, week=args.week, slate=args.slate, cutoff=cutoff,
    )
    baseline = [*BASE_FEATURE_COLUMNS, "snap_share_mean_3", *POSITION_FEATURE_COLUMNS]
    options = {
        "baseline": [],
        "raw_shares": ["carry_share_mean_3", "target_share_mean_3"],
        "raw_counts": ["carries_mean_3", "targets_mean_3"],
        "role_score": ["offensive_role_importance", "offensive_role_completeness"],
        "raw_shares_plus_role": ["carry_share_mean_3", "target_share_mean_3",
                                  "offensive_role_importance", "offensive_role_completeness"],
        "raw_counts_plus_role": ["carries_mean_3", "targets_mean_3",
                                  "offensive_role_importance", "offensive_role_completeness"],
        "all_role_inputs": ["carry_share_mean_3", "target_share_mean_3",
                            "carries_mean_3", "targets_mean_3",
                            "offensive_role_importance", "offensive_role_completeness"],
    }
    result = {
        "cutoff": cutoff.isoformat(), "target": [args.season, args.week, args.slate],
        "validation": [args.validation_season, args.first_week, args.last_week],
        "training_source": sources["source"],
        "policy": "Each held-out week trains only on earlier seasons/weeks; same 80/20 point blend",
        "models": {},
    }
    for label, extra in options.items():
        predicted: list[float] = []
        actual: list[float] = []
        salaries: list[float] = []
        periods = []
        for week in range(args.first_week, args.last_week + 1):
            validation = train.loc[
                (train.season == args.validation_season) & (train.week == week)
            ]
            if validation.empty:
                continue
            prior = train.loc[
                (train.season < args.validation_season)
                | ((train.season == args.validation_season) & (train.week < week))
            ]
            if len(prior) < 100:
                continue
            columns = baseline + extra
            model = GradientBoostingRegressor(random_state=42)
            model.fit(
                prior[columns].apply(pd.to_numeric, errors="coerce").fillna(0.0),
                prior[TARGET_COL],
            )
            raw = model.predict(
                validation[columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
            )
            predicted.extend(blend_point_predictions(raw, prior, validation))
            actual.extend(validation[TARGET_COL])
            salaries.extend(pd.to_numeric(validation.salary, errors="coerce").fillna(0))
            periods.append({"season": args.validation_season, "week": week,
                            "rows": len(validation)})
        prediction, outcome, salary = map(np.asarray, (predicted, actual, salaries))
        if not len(prediction):
            raise ValueError("No held-out rows available for evaluation")
        high = salary >= 6000
        result["models"][label] = {
            "features": columns, "rows": len(prediction), "periods": periods,
            "mae": float(np.mean(np.abs(prediction - outcome))),
            "rmse": float(np.sqrt(np.mean((prediction - outcome) ** 2))),
            "salary_6000_plus_rows": int(high.sum()),
            "salary_6000_plus_mae": (
                float(np.mean(np.abs(prediction[high] - outcome[high])))
                if high.any() else None
            ),
        }
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    print(output)


if __name__ == "__main__":
    main()
