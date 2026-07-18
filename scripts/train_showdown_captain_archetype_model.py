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
from backend.app.services.lineup_learning import (
    SHOWDOWN_CAPTAIN_BASE_FEATURE_NAMES,
    SHOWDOWN_CAPTAIN_CONTINUITY_FEATURE_NAMES,
    SHOWDOWN_CAPTAIN_CONTEXT_FEATURE_NAMES,
    LineupLearningService,
    ShowdownPlayerPoolRow,
    _injury_status_score,
)


POSITION_ORDER = ["QB", "RB", "WR", "TE", "K", "DST"]
FEATURE_NAMES = list(SHOWDOWN_CAPTAIN_CONTEXT_FEATURE_NAMES)


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
        "--feature-set",
        choices=["baseline", "availability", "continuity"],
        default="baseline",
        help=(
            "Availability uses injury snapshots; continuity uses only prior usage and the "
            "current salary pool. Both remain opt-in."
        ),
    )
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
    team_skill_out_values = [
        max(int(row.team_skill_out_count) for row in rows)
        for rows in by_team.values()
        if rows
    ]
    team_position_out_values = [
        int(row.team_position_out_count)
        for row in pool
        if row.position in {"QB", "RB", "WR", "TE"}
    ]
    injury_report_rows = [
        row
        for row in pool
        if (row.player_injury_status or "unknown").strip().lower() != "unknown"
    ]
    team_missing_usage_shares = [
        max(float(row.team_missing_usage_share) for row in rows)
        for rows in by_team.values()
        if rows
    ]
    team_available_usage_concentrations = [
        max(float(row.team_available_usage_concentration) for row in rows)
        for rows in by_team.values()
        if rows
    ]
    team_usage_identity_coverages = [
        max(float(row.team_usage_identity_coverage) for row in rows)
        for rows in by_team.values()
        if rows
    ]

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
        "max_team_skill_out_count": _max_or_zero(
            [float(value) for value in team_skill_out_values]
        ),
        "team_skill_out_count_diff": (
            float(max(team_skill_out_values) - min(team_skill_out_values))
            if team_skill_out_values
            else 0.0
        ),
        "max_team_position_out_count": _max_or_zero(
            [float(value) for value in team_position_out_values]
        ),
        "injury_report_coverage": (
            float(len(injury_report_rows) / len(pool))
            if pool
            else 0.0
        ),
        "questionable_or_worse_count": float(
            sum(1 for row in pool if _injury_status_score(row.player_injury_status) >= 0.5)
        ),
        "max_team_missing_usage_share": _max_or_zero(team_missing_usage_shares),
        "team_missing_usage_share_diff": (
            float(max(team_missing_usage_shares) - min(team_missing_usage_shares))
            if team_missing_usage_shares
            else 0.0
        ),
        "max_team_available_usage_concentration": _max_or_zero(
            team_available_usage_concentrations
        ),
        "team_available_usage_concentration_diff": (
            float(
                max(team_available_usage_concentrations)
                - min(team_available_usage_concentrations)
            )
            if team_available_usage_concentrations
            else 0.0
        ),
        "min_team_usage_identity_coverage": (
            float(min(team_usage_identity_coverages))
            if team_usage_identity_coverages
            else 0.0
        ),
    }
    team_available_skill_counts = [
        sum(
            1
            for row in rows
            if row.position in {"QB", "RB", "WR", "TE"}
            and _injury_status_score(row.player_injury_status) < 0.8
        )
        for rows in by_team.values()
    ]
    features.update({
        "max_team_available_skill_count": _max_or_zero(
            [float(value) for value in team_available_skill_counts]
        ),
        "team_available_skill_count_diff": (
            float(max(team_available_skill_counts) - min(team_available_skill_counts))
            if team_available_skill_counts
            else 0.0
        ),
    })

    for pos in POSITION_ORDER:
        count, top_proj, top_salary = _position_features(pool, pos)
        features[f"{pos.lower()}_count"] = float(count)
        features[f"top_{pos.lower()}_proj_mean"] = float(top_proj)
        features[f"top_{pos.lower()}_salary"] = float(top_salary)
    for pos in ("RB", "WR", "TE"):
        features[f"{pos.lower()}_position_out_max"] = _max_or_zero(
            [
                float(row.team_position_out_count)
                for row in pool
                if row.position == pos
            ]
        )

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
    if summary["feature_set"] == "availability":
        lines.append("- The model uses matchup, pool, and point-in-time teammate-availability context.")
        lines.append("- Availability features come from the selected season/week/slate injury snapshot.")
    elif summary["feature_set"] == "continuity":
        lines.append("- The model uses matchup, pool, and injury-free usage-continuity context.")
        lines.append(
            "- Missing usage is derived only from prior carries/targets and current salary-pool identity."
        )
    else:
        lines.append("- The model uses the established matchup and salary-pool context feature set.")
        lines.append("- Use `--feature-set availability` only after validating historical injury coverage.")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)
    rng = np.random.default_rng(args.random_seed)
    if args.feature_set == "availability":
        selected_feature_names = [
            *SHOWDOWN_CAPTAIN_BASE_FEATURE_NAMES,
            *[
                name
                for name in SHOWDOWN_CAPTAIN_CONTEXT_FEATURE_NAMES
                if name not in SHOWDOWN_CAPTAIN_BASE_FEATURE_NAMES
                and name not in SHOWDOWN_CAPTAIN_CONTINUITY_FEATURE_NAMES
            ],
        ]
    elif args.feature_set == "continuity":
        selected_feature_names = [
            *SHOWDOWN_CAPTAIN_BASE_FEATURE_NAMES,
            *SHOWDOWN_CAPTAIN_CONTINUITY_FEATURE_NAMES,
        ]
    else:
        selected_feature_names = list(SHOWDOWN_CAPTAIN_BASE_FEATURE_NAMES)

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

    x = np.asarray(
        [[float(row[name]) for name in selected_feature_names] for row in dataset_rows],
        dtype=float,
    )
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
        "feature_set": args.feature_set,
        "model_top1_accuracy": model_top1_accuracy,
        "model_top2_accuracy": model_top2_accuracy,
        "baseline_top1_accuracy": baseline_top1_accuracy,
        "top1_accuracy_lift": model_top1_accuracy - baseline_top1_accuracy,
        "classes": classes,
        "features": selected_feature_names,
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
            "feature_names": selected_feature_names,
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
                "feature_set": args.feature_set,
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
