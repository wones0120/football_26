from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.services.lineup_learning import LineupLearningService, ShowdownPlayerPoolRow


POSITION_ORDER = ["QB", "RB", "WR", "TE", "K", "DST"]
FEATURE_NAMES = [
    "game_total_line",
    "game_spread_abs",
    "max_team_implied_total",
    "min_team_implied_total",
    "implied_total_diff",
    "has_vegas_line",
    "pool_size",
    "team_count",
    "team1_player_count",
    "team2_player_count",
    "qb_count",
    "rb_count",
    "wr_count",
    "te_count",
    "k_count",
    "dst_count",
    "top_qb_proj_mean",
    "top_rb_proj_mean",
    "top_wr_proj_mean",
    "top_te_proj_mean",
    "top_k_proj_mean",
    "top_dst_proj_mean",
    "top_qb_salary",
    "top_rb_salary",
    "top_wr_salary",
    "top_te_salary",
    "top_k_salary",
    "top_dst_salary",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train/evaluate a matchup-aware showdown captain archetype model (captain position target)."
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--training-window-slates", type=int, default=24)
    parser.add_argument("--min-training-slates", type=int, default=8)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--limit-slates", type=int, default=0)
    parser.add_argument(
        "--dataset-csv",
        type=str,
        default="docs/showdown_captain_training_dataset_2024_2025.csv",
    )
    parser.add_argument(
        "--eval-json",
        type=str,
        default="docs/showdown_captain_model_eval_2024_2025.json",
    )
    parser.add_argument(
        "--model-json",
        type=str,
        default="docs/showdown_captain_model_2024_2025.json",
    )
    parser.add_argument(
        "--report-md",
        type=str,
        default="docs/showdown_captain_model_eval_2024_2025.md",
    )
    return parser.parse_args()


def _safe_median(values: list[float], default: float = 0.0) -> float:
    clean = [value for value in values if math.isfinite(value)]
    if not clean:
        return float(default)
    return float(statistics.median(clean))


def _max_or_zero(values: list[float]) -> float:
    clean = [value for value in values if math.isfinite(value)]
    if not clean:
        return 0.0
    return float(max(clean))


def _softmax(scores: np.ndarray) -> np.ndarray:
    shifted = scores - np.max(scores, axis=1, keepdims=True)
    exp = np.exp(shifted)
    denom = np.sum(exp, axis=1, keepdims=True)
    denom = np.where(denom <= 0, 1.0, denom)
    return exp / denom


def _train_softmax(
    x_train: np.ndarray,
    y_idx: np.ndarray,
    num_classes: int,
    *,
    seed: int,
    steps: int = 1200,
    lr: float = 0.07,
    l2: float = 0.001,
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    n_rows, n_features = x_train.shape
    w = rng.normal(loc=0.0, scale=0.01, size=(n_features, num_classes))
    b = np.zeros(num_classes, dtype=float)
    y_onehot = np.zeros((n_rows, num_classes), dtype=float)
    y_onehot[np.arange(n_rows), y_idx] = 1.0

    for _ in range(steps):
        probs = _softmax((x_train @ w) + b)
        error = probs - y_onehot
        grad_w = (x_train.T @ error) / n_rows + (l2 * w)
        grad_b = np.mean(error, axis=0)
        w -= lr * grad_w
        b -= lr * grad_b
    return w, b


def _position_features(pool: list[ShowdownPlayerPoolRow], position: str) -> tuple[int, float, float]:
    rows = [row for row in pool if row.position == position]
    count = len(rows)
    top_proj = _max_or_zero([row.projected_mean_points for row in rows])
    top_salary = _max_or_zero([float(row.flex_salary) for row in rows])
    return count, top_proj, top_salary


def _build_features(pool: list[ShowdownPlayerPoolRow]) -> dict[str, float]:
    by_team: dict[str, list[ShowdownPlayerPoolRow]] = {}
    for row in pool:
        if row.team:
            by_team.setdefault(row.team, []).append(row)

    team_counts = sorted([len(rows) for rows in by_team.values()], reverse=True)
    team1_count = float(team_counts[0]) if len(team_counts) >= 1 else 0.0
    team2_count = float(team_counts[1]) if len(team_counts) >= 2 else 0.0

    team_implied_values: list[float] = []
    for rows in by_team.values():
        values = [float(row.team_implied_total) for row in rows if row.team_implied_total is not None]
        if values:
            team_implied_values.append(_safe_median(values))

    game_totals = [float(row.game_total_line) for row in pool if row.game_total_line is not None]
    spread_abs_values = [
        abs(float(row.team_spread_line))
        for row in pool
        if row.team_spread_line is not None and math.isfinite(float(row.team_spread_line))
    ]
    has_vegas_line = 1.0 if game_totals and spread_abs_values else 0.0

    features = {
        "game_total_line": _safe_median(game_totals),
        "game_spread_abs": _safe_median(spread_abs_values),
        "max_team_implied_total": _max_or_zero(team_implied_values),
        "min_team_implied_total": min(team_implied_values) if team_implied_values else 0.0,
        "implied_total_diff": (
            (_max_or_zero(team_implied_values) - min(team_implied_values))
            if team_implied_values
            else 0.0
        ),
        "has_vegas_line": has_vegas_line,
        "pool_size": float(len(pool)),
        "team_count": float(len(by_team)),
        "team1_player_count": team1_count,
        "team2_player_count": team2_count,
    }

    for pos in POSITION_ORDER:
        count, top_proj, top_salary = _position_features(pool, pos)
        features[f"{pos.lower()}_count"] = float(count)
        features[f"top_{pos.lower()}_proj_mean"] = float(top_proj)
        features[f"top_{pos.lower()}_salary"] = float(top_salary)

    return features


def _write_dataset_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    field_names = [
        "season",
        "week",
        "slate",
        "captain_position",
        "captain_name",
        "captain_team",
        "captain_salary",
        "captain_actual_points_base",
        "optimal_lineup_points",
        *FEATURE_NAMES,
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=field_names)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in field_names})


def _report_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    class_rows = payload["class_distribution"]
    lines: list[str] = []
    lines.append("# Showdown Captain Archetype Model (Initial)")
    lines.append("")
    lines.append(
        f"- Source: `{summary['source_system']}`  "
        f"Seasons: `{summary['season_start']}-{summary['season_end']}`  "
        f"Total slates: `{summary['slates_total']}`  "
        f"Evaluated: `{summary['slates_evaluated']}`"
    )
    lines.append("")
    lines.append("## Walk-Forward Metrics")
    lines.append("")
    lines.append(f"- Model Top-1 Accuracy: `{summary['model_top1_accuracy']:.3f}`")
    lines.append(f"- Model Top-2 Accuracy: `{summary['model_top2_accuracy']:.3f}`")
    lines.append(f"- Baseline Top-1 Accuracy: `{summary['baseline_top1_accuracy']:.3f}`")
    lines.append(f"- Accuracy Lift (Top-1): `{summary['top1_accuracy_lift']:.3f}`")
    lines.append("")
    lines.append("## Captain Position Distribution")
    lines.append("")
    lines.append("| Position | Slates | Share |")
    lines.append("|---|---:|---:|")
    for row in class_rows:
        lines.append(f"| {row['position']} | {row['count']} | {row['share'] * 100:.1f}% |")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- This is an initial archetype model using matchup/pool context features only.")
    lines.append("- Next step is adding teammate-availability context and richer game-state priors.")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)
    rng = np.random.default_rng(args.random_seed)

    dataset_rows: list[dict[str, Any]] = []

    with SessionLocal() as session:
        service = LineupLearningService(session)
        slices = service._fetch_available_slate_slices(
            source_system=args.source_system,
            season_start=season_start,
            season_end=season_end,
            slate_filter=None,
        )
        slices = service._filter_slices_by_slate_type(
            source_system=args.source_system,
            slices=slices,
            slate_type="showdown",
        )
        if args.limit_slates > 0:
            slices = slices[: args.limit_slates]

        for season, week, slate in slices:
            projection_lookup, dst_projection_lookup = service._compute_player_projection_lookup(
                source_system=args.source_system,
                season=season,
                week=week,
                slate=slate,
            )
            pool = service._fetch_showdown_player_pool(
                source_system=args.source_system,
                season=season,
                week=week,
                slate=slate,
                projection_lookup=projection_lookup,
                dst_projection_lookup=dst_projection_lookup,
            )
            optimal = service.optimize_actual_showdown_lineup(players=pool)
            if optimal is None:
                continue
            lineup, optimal_points, _optimal_salary = optimal
            captain = lineup.captain
            feature_map = _build_features(pool)
            row = {
                "season": int(season),
                "week": int(week),
                "slate": str(slate),
                "captain_position": captain.position,
                "captain_name": captain.name,
                "captain_team": captain.team,
                "captain_salary": int(captain.captain_salary),
                "captain_actual_points_base": float(captain.actual_points),
                "optimal_lineup_points": float(optimal_points),
            }
            row.update({name: float(feature_map.get(name, 0.0)) for name in FEATURE_NAMES})
            dataset_rows.append(row)

    if not dataset_rows:
        raise ValueError("No showdown slates available to build captain archetype dataset.")

    x = np.asarray([[float(row[name]) for name in FEATURE_NAMES] for row in dataset_rows], dtype=float)
    y_labels = np.asarray([str(row["captain_position"]) for row in dataset_rows], dtype=object)
    classes = sorted({str(value) for value in y_labels})
    class_to_idx = {label: idx for idx, label in enumerate(classes)}
    y_idx = np.asarray([class_to_idx[str(label)] for label in y_labels], dtype=int)

    prediction_rows: list[dict[str, Any]] = []
    evaluated = 0
    model_hits_top1 = 0
    model_hits_top2 = 0
    baseline_hits_top1 = 0

    for idx in range(len(dataset_rows)):
        train_start = max(0, idx - max(1, args.training_window_slates))
        train_indices = list(range(train_start, idx))
        if len(train_indices) < args.min_training_slates:
            prediction_rows.append(
                {
                    "season": dataset_rows[idx]["season"],
                    "week": dataset_rows[idx]["week"],
                    "slate": dataset_rows[idx]["slate"],
                    "actual_position": str(y_labels[idx]),
                    "status": "warmup",
                }
            )
            continue

        x_train = x[train_indices]
        y_train = y_idx[train_indices]
        x_mean = np.mean(x_train, axis=0)
        x_std = np.std(x_train, axis=0)
        x_std = np.where(x_std < 1e-6, 1.0, x_std)
        x_train_norm = (x_train - x_mean) / x_std

        w, b = _train_softmax(
            x_train_norm,
            y_train,
            num_classes=len(classes),
            seed=int(rng.integers(1_000_000_000)),
        )
        x_test = ((x[idx : idx + 1] - x_mean) / x_std)
        probs = _softmax((x_test @ w) + b)[0]
        top_order = np.argsort(-probs)
        pred_top1 = classes[int(top_order[0])]
        pred_top2 = classes[int(top_order[1])] if len(top_order) > 1 else pred_top1
        actual = str(y_labels[idx])
        majority = Counter([str(y_labels[j]) for j in train_indices]).most_common(1)[0][0]

        hit_top1 = int(pred_top1 == actual)
        hit_top2 = int(actual in {pred_top1, pred_top2})
        base_hit = int(majority == actual)

        evaluated += 1
        model_hits_top1 += hit_top1
        model_hits_top2 += hit_top2
        baseline_hits_top1 += base_hit

        prediction_rows.append(
            {
                "season": dataset_rows[idx]["season"],
                "week": dataset_rows[idx]["week"],
                "slate": dataset_rows[idx]["slate"],
                "actual_position": actual,
                "predicted_top1_position": pred_top1,
                "predicted_top2_position": pred_top2,
                "baseline_majority_position": majority,
                "predicted_top1_prob": float(probs[int(top_order[0])]),
                "actual_position_prob": float(probs[class_to_idx[actual]]),
                "top1_hit": bool(hit_top1),
                "top2_hit": bool(hit_top2),
                "baseline_hit": bool(base_hit),
                "status": "evaluated",
                "probabilities": {classes[class_idx]: float(prob) for class_idx, prob in enumerate(probs)},
            }
        )

    model_top1_accuracy = (model_hits_top1 / evaluated) if evaluated > 0 else 0.0
    model_top2_accuracy = (model_hits_top2 / evaluated) if evaluated > 0 else 0.0
    baseline_top1_accuracy = (baseline_hits_top1 / evaluated) if evaluated > 0 else 0.0

    # Train final model on all rows for downstream scoring use.
    x_all_mean = np.mean(x, axis=0)
    x_all_std = np.std(x, axis=0)
    x_all_std = np.where(x_all_std < 1e-6, 1.0, x_all_std)
    x_all_norm = (x - x_all_mean) / x_all_std
    w_all, b_all = _train_softmax(
        x_all_norm,
        y_idx,
        num_classes=len(classes),
        seed=int(rng.integers(1_000_000_000)),
    )

    class_counts = Counter([str(label) for label in y_labels])
    class_distribution = [
        {
            "position": position,
            "count": int(class_counts.get(position, 0)),
            "share": (class_counts.get(position, 0) / len(y_labels)),
        }
        for position in sorted(class_counts.keys(), key=lambda key: class_counts[key], reverse=True)
    ]

    summary = {
        "source_system": args.source_system,
        "season_start": season_start,
        "season_end": season_end,
        "slates_total": len(dataset_rows),
        "slates_evaluated": evaluated,
        "slates_warmup": len(dataset_rows) - evaluated,
        "training_window_slates": args.training_window_slates,
        "min_training_slates": args.min_training_slates,
        "model_top1_accuracy": model_top1_accuracy,
        "model_top2_accuracy": model_top2_accuracy,
        "baseline_top1_accuracy": baseline_top1_accuracy,
        "top1_accuracy_lift": model_top1_accuracy - baseline_top1_accuracy,
        "classes": classes,
        "features": FEATURE_NAMES,
    }

    eval_payload = {
        "summary": summary,
        "class_distribution": class_distribution,
        "predictions": prediction_rows,
    }
    model_payload = {
        "summary": summary,
        "model": {
            "classes": classes,
            "feature_names": FEATURE_NAMES,
            "x_mean": x_all_mean.tolist(),
            "x_std": x_all_std.tolist(),
            "weights": w_all.tolist(),
            "bias": b_all.tolist(),
        },
    }

    dataset_path = Path(args.dataset_csv).expanduser().resolve()
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    _write_dataset_csv(dataset_path, dataset_rows)

    eval_json_path = Path(args.eval_json).expanduser().resolve()
    eval_json_path.parent.mkdir(parents=True, exist_ok=True)
    eval_json_path.write_text(json.dumps(eval_payload, indent=2), encoding="utf-8")

    model_json_path = Path(args.model_json).expanduser().resolve()
    model_json_path.parent.mkdir(parents=True, exist_ok=True)
    model_json_path.write_text(json.dumps(model_payload, indent=2), encoding="utf-8")

    report_path = Path(args.report_md).expanduser().resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_report_markdown(eval_payload), encoding="utf-8")

    print(
        json.dumps(
            {
                "source_system": args.source_system,
                "season_start": season_start,
                "season_end": season_end,
                "slates_total": len(dataset_rows),
                "slates_evaluated": evaluated,
                "model_top1_accuracy": round(model_top1_accuracy, 4),
                "model_top2_accuracy": round(model_top2_accuracy, 4),
                "baseline_top1_accuracy": round(baseline_top1_accuracy, 4),
                "top1_accuracy_lift": round(model_top1_accuracy - baseline_top1_accuracy, 4),
                "dataset_csv": str(dataset_path),
                "eval_json": str(eval_json_path),
                "model_json": str(model_json_path),
                "report_md": str(report_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
