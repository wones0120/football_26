from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


POSITION_NAMES = ("QB", "RB", "WR", "TE", "K", "DST")
BASE_FEATURES = (
    "projected_mean",
    "projected_p90",
    "captain_salary_k",
    "game_total",
    "team_implied_total",
    "spread_abs",
    *(f"position_{position}" for position in POSITION_NAMES),
)
VOLUME_FEATURES = (
    "expected_pass_attempts",
    "expected_carries",
    "expected_targets",
    "expected_routes",
    "expected_snaps",
    "carry_share",
    "target_share",
    "red_zone_share",
    "goal_line_share",
    "primary_volume",
    "primary_volume_team_percentile",
    "volume_available",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Walk-forward Showdown Captain volume-ranker diagnostic.")
    parser.add_argument("--dataset-json", default="artifacts/showdown-oracle-dataset.json")
    parser.add_argument("--min-training-slates", type=int, default=8)
    parser.add_argument("--ridge", type=float, default=2.0)
    parser.add_argument("--output-json", default="artifacts/showdown-captain-volume-ranker.json")
    parser.add_argument("--output-md", default="artifacts/showdown-captain-volume-ranker.md")
    return parser.parse_args()


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _slate_key(row: dict[str, Any]) -> tuple[int, int, str]:
    return int(row["season"]), int(row["week"]), str(row["slate"])


def _primary_volume(row: dict[str, Any]) -> float | None:
    position = str(row.get("position") or "").upper()
    attempts = _number(row.get("expected_pass_attempts"))
    carries = _number(row.get("expected_carries"))
    targets = _number(row.get("expected_targets"))
    if position == "QB":
        return None if attempts is None and carries is None else (attempts or 0.0) + (0.75 * (carries or 0.0))
    if position == "RB":
        return None if carries is None and targets is None else (carries or 0.0) + (1.5 * (targets or 0.0))
    if position in {"WR", "TE"}:
        return targets
    return None


def _prepare(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        row["primary_volume"] = _primary_volume(row)
        row["volume_available"] = 1.0 if row["primary_volume"] is not None else 0.0
    groups: dict[tuple[int, int, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (*_slate_key(row), str(row.get("team") or ""))
        groups.setdefault(key, []).append(row)
    for group in groups.values():
        known = sorted(
            value
            for row in group
            if (value := _number(row.get("primary_volume"))) is not None
        )
        for row in group:
            value = _number(row.get("primary_volume"))
            if value is None or not known:
                row["primary_volume_team_percentile"] = None
            else:
                row["primary_volume_team_percentile"] = sum(item <= value for item in known) / len(known)


def _features(row: dict[str, Any], names: tuple[str, ...]) -> list[float | None]:
    position = str(row.get("position") or "").upper()
    values: dict[str, float | None] = {
        "projected_mean": _number(row.get("projected_mean")),
        "projected_p90": _number(row.get("projected_p90")),
        "captain_salary_k": (_number(row.get("captain_salary")) or 0.0) / 1000.0,
        "game_total": _number(row.get("game_total")),
        "team_implied_total": _number(row.get("team_implied_total")),
        "spread_abs": abs(_number(row.get("team_spread")) or 0.0),
        **{f"position_{name}": float(position == name) for name in POSITION_NAMES},
        **{name: _number(row.get(name)) for name in VOLUME_FEATURES},
    }
    return [values[name] for name in names]


def _matrix(rows: list[dict[str, Any]], names: tuple[str, ...], medians: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    raw = np.asarray(
        [[np.nan if value is None else value for value in _features(row, names)] for row in rows],
        dtype=float,
    )
    if medians is None:
        medians = np.asarray(
            [
                float(np.median(column[np.isfinite(column)]))
                if np.isfinite(column).any()
                else 0.0
                for column in raw.T
            ],
            dtype=float,
        )
    return np.where(np.isnan(raw), medians, raw), medians


def _fit(train: list[dict[str, Any]], names: tuple[str, ...], target: str, ridge: float) -> dict[str, Any]:
    x, medians = _matrix(train, names)
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    std = np.where(std > 1e-8, std, 1.0)
    z = (x - mean) / std
    design = np.column_stack([np.ones(len(z)), z])
    y = np.asarray([float(row[target]) for row in train], dtype=float)
    penalty = np.eye(design.shape[1]) * ridge
    penalty[0, 0] = 0.0
    coef = np.linalg.solve(design.T @ design + penalty, design.T @ y)
    return {"medians": medians, "mean": mean, "std": std, "coef": coef}


def _predict(model: dict[str, Any], rows: list[dict[str, Any]], names: tuple[str, ...]) -> np.ndarray:
    x, _ = _matrix(rows, names, model["medians"])
    z = (x - model["mean"]) / model["std"]
    return np.column_stack([np.ones(len(z)), z]) @ model["coef"]


def _evaluate(rows: list[dict[str, Any]], names: tuple[str, ...], min_slates: int, ridge: float) -> dict[str, Any]:
    keys = sorted({_slate_key(row) for row in rows})
    predictions: list[dict[str, Any]] = []
    for index, key in enumerate(keys):
        if index < min_slates:
            continue
        train_keys = set(keys[:index])
        train = [row for row in rows if _slate_key(row) in train_keys]
        test = [row for row in rows if _slate_key(row) == key]
        regret_model = _fit(train, names, "negative_regret", ridge)
        bust_model = _fit(train, names, "actual_below_5_float", ridge)
        scores = _predict(regret_model, test, names)
        bust = np.clip(_predict(bust_model, test, names), 0.0, 1.0)
        selected_index = int(np.argmax(scores))
        selected = test[selected_index]
        baseline = max(test, key=lambda row: float(row.get("projected_p90") or 0.0))
        predictions.append(
            {
                "season": key[0],
                "week": key[1],
                "slate": key[2],
                "selected_player": selected["player_name"],
                "selected_position": selected["position"],
                "selected_regret": selected["captain_regret"],
                "selected_actual_below_5": selected["actual_below_5"],
                "predicted_bust_probability": float(bust[selected_index]),
                "baseline_player": baseline["player_name"],
                "baseline_regret": baseline["captain_regret"],
                "baseline_actual_below_5": baseline["actual_below_5"],
            }
        )
    def metrics(prefix: str) -> dict[str, Any]:
        regrets = [float(row[f"{prefix}_regret"]) for row in predictions]
        busts = [bool(row[f"{prefix}_actual_below_5"]) for row in predictions]
        return {
            "slates": len(predictions),
            "mean_regret": float(np.mean(regrets)) if regrets else None,
            "median_regret": float(np.median(regrets)) if regrets else None,
            "within_1_rate": float(np.mean(np.asarray(regrets) <= 1.0)) if regrets else None,
            "within_3_rate": float(np.mean(np.asarray(regrets) <= 3.0)) if regrets else None,
            "within_5_rate": float(np.mean(np.asarray(regrets) <= 5.0)) if regrets else None,
            "sub_5_selection_rate": float(np.mean(busts)) if busts else 0.0,
        }
    return {"ranker": metrics("selected"), "p90_baseline": metrics("baseline"), "slates": predictions}


def _serialize_model(model: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    return {
        "feature_names": list(names),
        "medians": model["medians"].tolist(),
        "mean": model["mean"].tolist(),
        "std": model["std"].tolist(),
        "coefficients": model["coef"].tolist(),
    }


def main() -> None:
    args = parse_args()
    dataset = json.loads(Path(args.dataset_json).read_text(encoding="utf-8"))
    rows = [row for row in dataset["forced_captains"] if row["forced_captain_feasible"]]
    for row in rows:
        row["negative_regret"] = -float(row["captain_regret"])
        row["actual_below_5_float"] = float(bool(row["actual_below_5"]))
    _prepare(rows)

    base_names = tuple(BASE_FEATURES)
    volume_names = tuple((*BASE_FEATURES, *VOLUME_FEATURES))
    base_eval = _evaluate(rows, base_names, args.min_training_slates, args.ridge)
    volume_eval = _evaluate(rows, volume_names, args.min_training_slates, args.ridge)
    regret_model = _fit(rows, volume_names, "negative_regret", args.ridge)
    bust_model = _fit(rows, volume_names, "actual_below_5_float", args.ridge)
    payload = {
        "status": "shadow_only",
        "dataset": args.dataset_json,
        "training_slates": len({_slate_key(row) for row in rows}),
        "training_rows": len(rows),
        "method": "within-slate Captain ranking using ridge models for negative regret and sub-5 risk",
        "base_walk_forward": base_eval,
        "volume_walk_forward": volume_eval,
        "regret_model": _serialize_model(regret_model, volume_names),
        "bust_model": _serialize_model(bust_model, volume_names),
    }
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    base = base_eval["ranker"]
    volume = volume_eval["ranker"]
    baseline = volume_eval["p90_baseline"]
    output_md.write_text(
        "\n".join(
            [
                "# Showdown Captain Volume Ranker",
                "",
                "Status: **shadow only**",
                "",
                "| Method | Mean regret | Median regret | Within 5 | Sub-5 selected |",
                "|---|---:|---:|---:|---:|",
                f"| P90 baseline | {baseline['mean_regret']:.2f} | {baseline['median_regret']:.2f} | {baseline['within_5_rate']:.1%} | {baseline['sub_5_selection_rate']:.1%} |",
                f"| Projection/context ranker | {base['mean_regret']:.2f} | {base['median_regret']:.2f} | {base['within_5_rate']:.1%} | {base['sub_5_selection_rate']:.1%} |",
                f"| Volume ranker | {volume['mean_regret']:.2f} | {volume['median_regret']:.2f} | {volume['within_5_rate']:.1%} | {volume['sub_5_selection_rate']:.1%} |",
                "",
                "The volume model adds expected pass attempts, carries, targets, routes, snaps, shares, and team volume percentile. Actual usage and fantasy points are labels only.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps({"json": str(output_json), "report": str(output_md), "volume": volume, "baseline": baseline}, indent=2))


if __name__ == "__main__":
    main()
