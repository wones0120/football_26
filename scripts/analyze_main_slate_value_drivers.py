from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.services.lineup_learning import LineupLearningService, PlayerPoolRow


DEFAULT_MAIN_SLATE_NAMES = {
    "main",
    "sunday_main",
    "sunday_all",
    "sunday",
    "normal",
    "1pm_slate",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze classic MAIN slate value drivers by position and game context "
            "(spread/total) from historical actuals."
        )
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument(
        "--main-slate-names",
        type=str,
        default=",".join(sorted(DEFAULT_MAIN_SLATE_NAMES)),
        help="Comma-separated slate names treated as MAIN.",
    )
    parser.add_argument("--top-players-per-slate", type=int, default=15)
    parser.add_argument("--high-total-threshold", type=float, default=48.0)
    parser.add_argument("--limit-slates", type=int, default=0)
    parser.add_argument(
        "--output-json",
        type=str,
        default="docs/main_slate_value_driver_analysis_2024_2025.json",
    )
    parser.add_argument(
        "--output-md",
        type=str,
        default="docs/main_slate_value_driver_analysis_2024_2025.md",
    )
    return parser.parse_args()


def _is_main_slate(name: str, allowed: set[str]) -> bool:
    slate = name.strip().lower()
    if slate in allowed:
        return True
    # Keep rule narrow: include obvious *main* labels only.
    return "main" in slate and "monday" not in slate


def _safe_value(points: float, salary: int) -> float:
    if salary <= 0:
        return 0.0
    return float(points / (salary / 1000.0))


def _total_band(total: float | None) -> str:
    if total is None or not math.isfinite(total):
        return "unknown"
    if total < 40:
        return "<40"
    if total < 45:
        return "40-44.9"
    if total < 50:
        return "45-49.9"
    return "50+"


def _spread_abs_band(spread: float | None) -> str:
    if spread is None or not math.isfinite(spread):
        return "unknown"
    abs_spread = abs(spread)
    if abs_spread <= 2.5:
        return "close_<=2.5"
    if abs_spread <= 6.5:
        return "mid_2.6_6.5"
    return "wide_>=6.6"


def _spread_role_bucket(spread: float | None) -> str:
    if spread is None or not math.isfinite(spread):
        return "unknown"
    # Convention in this pipeline: negative spread means favorite.
    if spread <= -7:
        return "big_favorite"
    if spread <= -3:
        return "favorite"
    if spread < 3:
        return "close"
    if spread < 7:
        return "underdog"
    return "big_underdog"


def _agg_new() -> dict[str, float]:
    return {
        "count": 0.0,
        "points_sum": 0.0,
        "value_sum": 0.0,
        "salary_sum": 0.0,
        "hit_3x": 0.0,
        "hit_4x": 0.0,
    }


def _agg_add(agg: dict[str, float], *, points: float, salary: int) -> None:
    value = _safe_value(points, salary)
    agg["count"] += 1.0
    agg["points_sum"] += float(points)
    agg["value_sum"] += float(value)
    agg["salary_sum"] += float(salary)
    if value >= 3.0:
        agg["hit_3x"] += 1.0
    if value >= 4.0:
        agg["hit_4x"] += 1.0


def _agg_finalize(name: str, agg: dict[str, float]) -> dict[str, Any]:
    count = int(agg["count"])
    if count <= 0:
        return {
            "name": name,
            "count": 0,
            "avg_points": None,
            "avg_value": None,
            "avg_salary": None,
            "hit_3x_rate": None,
            "hit_4x_rate": None,
        }
    return {
        "name": name,
        "count": count,
        "avg_points": float(agg["points_sum"] / count),
        "avg_value": float(agg["value_sum"] / count),
        "avg_salary": float(agg["salary_sum"] / count),
        "hit_3x_rate": float(agg["hit_3x"] / count),
        "hit_4x_rate": float(agg["hit_4x"] / count),
    }


def _counter_mix(counter: Counter[str]) -> list[dict[str, Any]]:
    total = float(sum(counter.values()))
    rows: list[dict[str, Any]] = []
    for key, count in counter.most_common():
        rows.append(
            {
                "key": key,
                "count": int(count),
                "share": (float(count) / total) if total > 0 else 0.0,
            }
        )
    return rows


def _corr(x_values: list[float], y_values: list[float]) -> float | None:
    if len(x_values) < 3 or len(y_values) < 3 or len(x_values) != len(y_values):
        return None
    x_arr = np.asarray(x_values, dtype=float)
    y_arr = np.asarray(y_values, dtype=float)
    if float(np.std(x_arr)) < 1e-9 or float(np.std(y_arr)) < 1e-9:
        return None
    return float(np.corrcoef(x_arr, y_arr)[0, 1])


def _render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    top_totals = payload["high_point_total_analysis"]
    rb = payload["rb_spread_analysis"]

    lines: list[str] = []
    lines.append("# Main Slate Value Driver Analysis")
    lines.append("")
    lines.append(
        f"- Source: `{summary['source_system']}`  "
        f"Seasons: `{summary['season_start']}-{summary['season_end']}`  "
        f"Main slates analyzed: `{summary['main_slates_analyzed']}`"
    )
    lines.append("")
    lines.append("## Key Answers")
    lines.append("")
    lines.append(
        f"- High-point players from high totals (`>= {top_totals['high_total_threshold']}`): "
        f"`{top_totals['high_players_high_total_share'] * 100:.1f}%` "
        f"vs baseline player-pool share `{top_totals['baseline_high_total_share'] * 100:.1f}%` "
        f"(lift `{top_totals['high_total_share_lift']:.2f}x`)."
    )
    lines.append(
        f"- RB average points (favorite buckets combined): `{rb['rb_avg_points_favorites']:.2f}` "
        f"vs underdog buckets: `{rb['rb_avg_points_underdogs']:.2f}`."
    )
    lines.append(
        f"- RB average value (favorite buckets combined): `{rb['rb_avg_value_favorites']:.2f}x` "
        f"vs underdog buckets: `{rb['rb_avg_value_underdogs']:.2f}x`."
    )
    lines.append(
        f"- RB high-point share in underdog buckets: "
        f"`{rb['rb_high_point_underdog_share'] * 100:.1f}%` "
        f"vs baseline RB underdog share `{rb['rb_baseline_underdog_share'] * 100:.1f}%`."
    )
    if rb["rb_spread_to_points_correlation"] is not None:
        lines.append(
            "- RB spread-to-points correlation (negative means stronger favorite improves points): "
            f"`{rb['rb_spread_to_points_correlation']:.3f}`."
        )
    lines.append("")
    lines.append("## Position Value Summary")
    lines.append("")
    lines.append("| Position | Rows | Avg Pts | Avg Value (x) | Avg Salary | 3x Rate | 4x Rate |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for row in payload["position_value_summary"]:
        lines.append(
            f"| {row['name']} | {row['count']} | {row['avg_points']:.2f} | "
            f"{row['avg_value']:.2f} | {row['avg_salary']:.0f} | "
            f"{row['hit_3x_rate'] * 100:.1f}% | {row['hit_4x_rate'] * 100:.1f}% |"
        )
    lines.append("")
    lines.append("## RB by Spread Role")
    lines.append("")
    lines.append("| Bucket | Rows | Avg Pts | Avg Value (x) | 3x Rate | 4x Rate |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in rb["rb_by_spread_role"]:
        lines.append(
            f"| {row['name']} | {row['count']} | {row['avg_points']:.2f} | "
            f"{row['avg_value']:.2f} | {row['hit_3x_rate'] * 100:.1f}% | {row['hit_4x_rate'] * 100:.1f}% |"
        )
    lines.append("")
    lines.append("## High-Point Player Mix by Total Band")
    lines.append("")
    lines.append("| Band | High-Point Share | Baseline Share | Share Lift |")
    lines.append("|---|---:|---:|---:|")
    high_mix = {row["key"]: row for row in top_totals["high_point_total_band_mix"]}
    base_mix = {row["key"]: row for row in top_totals["baseline_total_band_mix"]}
    for band in ["50+", "45-49.9", "40-44.9", "<40", "unknown"]:
        high = high_mix.get(band, {"share": 0.0})
        base = base_mix.get(band, {"share": 0.0})
        lift = (high["share"] / base["share"]) if base["share"] > 0 else None
        lines.append(
            f"| {band} | {high['share'] * 100:.1f}% | {base['share'] * 100:.1f}% | "
            f"{'-' if lift is None else f'{lift:.2f}x'} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)
    allowed_main_names = {token.strip().lower() for token in args.main_slate_names.split(",") if token.strip()}

    position_agg: dict[str, dict[str, float]] = defaultdict(_agg_new)
    position_by_total_agg: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(_agg_new))
    position_by_spread_role_agg: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(_agg_new))
    position_total_points_for_corr: dict[str, list[float]] = defaultdict(list)
    position_total_line_for_corr: dict[str, list[float]] = defaultdict(list)
    rb_spread_for_corr: list[float] = []
    rb_points_for_corr: list[float] = []

    baseline_total_band_counter: Counter[str] = Counter()
    high_point_total_band_counter: Counter[str] = Counter()
    high_point_position_counter: Counter[str] = Counter()
    selected_slate_counter: Counter[str] = Counter()

    optimal_flex_counter: Counter[str] = Counter()
    optimal_lineup_position_counter: Counter[str] = Counter()

    total_classic_slices = 0
    selected_main_slices = 0

    with SessionLocal() as session:
        service = LineupLearningService(session)
        slices = service._fetch_available_slate_slices(
            source_system=args.source_system,
            season_start=season_start,
            season_end=season_end,
            slate_filter=None,
        )
        classic_slices = service._filter_slices_by_slate_type(
            source_system=args.source_system,
            slices=slices,
            slate_type="classic",
        )
        total_classic_slices = len(classic_slices)

        selected_slices = [
            (season, week, slate)
            for season, week, slate in classic_slices
            if _is_main_slate(slate, allowed_main_names)
        ]
        if args.limit_slates > 0:
            selected_slices = selected_slices[: args.limit_slates]

        for season, week, slate in selected_slices:
            selected_main_slices += 1
            selected_slate_counter[slate] += 1
            pool = service._fetch_slate_player_pool(
                source_system=args.source_system,
                season=season,
                week=week,
                slate=slate,
            )
            if not pool:
                continue

            valid_pool = [
                row
                for row in pool
                if row.salary > 0 and math.isfinite(float(row.actual_points))
            ]
            if not valid_pool:
                continue

            for row in valid_pool:
                total_band = _total_band(row.game_total_line)
                spread_role = _spread_role_bucket(row.team_spread_line)
                baseline_total_band_counter[total_band] += 1
                _agg_add(position_agg[row.position], points=float(row.actual_points), salary=int(row.salary))
                _agg_add(
                    position_by_total_agg[row.position][total_band],
                    points=float(row.actual_points),
                    salary=int(row.salary),
                )
                _agg_add(
                    position_by_spread_role_agg[row.position][spread_role],
                    points=float(row.actual_points),
                    salary=int(row.salary),
                )

                if row.game_total_line is not None and math.isfinite(float(row.game_total_line)):
                    position_total_line_for_corr[row.position].append(float(row.game_total_line))
                    position_total_points_for_corr[row.position].append(float(row.actual_points))
                if row.position == "RB" and row.team_spread_line is not None and math.isfinite(float(row.team_spread_line)):
                    rb_spread_for_corr.append(float(row.team_spread_line))
                    rb_points_for_corr.append(float(row.actual_points))

            top_rows = sorted(valid_pool, key=lambda row: float(row.actual_points), reverse=True)[
                : max(1, args.top_players_per_slate)
            ]
            for row in top_rows:
                high_point_total_band_counter[_total_band(row.game_total_line)] += 1
                high_point_position_counter[row.position] += 1

            optimal = service.optimize_actual_lineup(players=valid_pool)
            if optimal is not None:
                lineup, _points, _salary = optimal
                counts = Counter(player.position for player in lineup)
                for position, count in counts.items():
                    optimal_lineup_position_counter[position] += count
                # FLEX is whichever of RB/WR/TE appears above fixed minimum (RB2/WR3/TE1).
                if counts.get("RB", 0) > 2:
                    optimal_flex_counter["RB"] += 1
                elif counts.get("WR", 0) > 3:
                    optimal_flex_counter["WR"] += 1
                elif counts.get("TE", 0) > 1:
                    optimal_flex_counter["TE"] += 1
                else:
                    optimal_flex_counter["unknown"] += 1

    position_rows = [
        _agg_finalize(position, agg)
        for position, agg in position_agg.items()
    ]
    position_rows = [row for row in position_rows if row["count"] > 0]
    position_rows.sort(key=lambda row: (row["avg_value"], row["avg_points"]), reverse=True)

    baseline_high_total_count = 0
    baseline_total_count = 0
    high_player_high_total_count = 0
    high_player_total_count = 0
    rb_high_point_spread_counter: Counter[str] = Counter()
    rb_baseline_spread_counter: Counter[str] = Counter()

    with SessionLocal() as session:
        service = LineupLearningService(session)
        slices = service._fetch_available_slate_slices(
            source_system=args.source_system,
            season_start=season_start,
            season_end=season_end,
            slate_filter=None,
        )
        classic_slices = service._filter_slices_by_slate_type(
            source_system=args.source_system,
            slices=slices,
            slate_type="classic",
        )
        selected_slices = [
            (season, week, slate)
            for season, week, slate in classic_slices
            if _is_main_slate(slate, allowed_main_names)
        ]
        if args.limit_slates > 0:
            selected_slices = selected_slices[: args.limit_slates]

        for season, week, slate in selected_slices:
            pool = service._fetch_slate_player_pool(
                source_system=args.source_system,
                season=season,
                week=week,
                slate=slate,
            )
            valid_pool = [
                row
                for row in pool
                if row.salary > 0 and math.isfinite(float(row.actual_points))
            ]
            for row in valid_pool:
                baseline_total_count += 1
                if row.game_total_line is not None and float(row.game_total_line) >= float(args.high_total_threshold):
                    baseline_high_total_count += 1
                if row.position == "RB":
                    rb_baseline_spread_counter[_spread_role_bucket(row.team_spread_line)] += 1

            top_rows = sorted(valid_pool, key=lambda row: float(row.actual_points), reverse=True)[
                : max(1, args.top_players_per_slate)
            ]
            for row in top_rows:
                high_player_total_count += 1
                if row.game_total_line is not None and float(row.game_total_line) >= float(args.high_total_threshold):
                    high_player_high_total_count += 1
                if row.position == "RB":
                    rb_high_point_spread_counter[_spread_role_bucket(row.team_spread_line)] += 1

    baseline_high_total_share = (
        float(baseline_high_total_count / baseline_total_count) if baseline_total_count > 0 else 0.0
    )
    high_players_high_total_share = (
        float(high_player_high_total_count / high_player_total_count) if high_player_total_count > 0 else 0.0
    )

    rb_bucket_rows = [
        _agg_finalize(bucket, agg)
        for bucket, agg in position_by_spread_role_agg["RB"].items()
    ]
    rb_bucket_rows = [row for row in rb_bucket_rows if row["count"] > 0]
    rb_bucket_rows.sort(key=lambda row: row["count"], reverse=True)

    rb_favorites = [
        row for row in rb_bucket_rows if row["name"] in {"big_favorite", "favorite"}
    ]
    rb_underdogs = [
        row for row in rb_bucket_rows if row["name"] in {"underdog", "big_underdog"}
    ]
    rb_high_total = float(sum(rb_high_point_spread_counter.values()))
    rb_base_total = float(sum(rb_baseline_spread_counter.values()))
    rb_high_underdog_share = (
        float(
            (rb_high_point_spread_counter["underdog"] + rb_high_point_spread_counter["big_underdog"])
            / rb_high_total
        )
        if rb_high_total > 0
        else 0.0
    )
    rb_base_underdog_share = (
        float(
            (rb_baseline_spread_counter["underdog"] + rb_baseline_spread_counter["big_underdog"])
            / rb_base_total
        )
        if rb_base_total > 0
        else 0.0
    )

    def _weighted_mean(rows: list[dict[str, Any]], key: str) -> float:
        total = sum(row["count"] for row in rows)
        if total <= 0:
            return 0.0
        return float(sum(row["count"] * float(row[key]) for row in rows) / total)

    total_line_correlations = {
        position: _corr(position_total_line_for_corr[position], position_total_points_for_corr[position])
        for position in sorted(position_total_line_for_corr.keys())
    }

    optimal_lineup_total_rows = float(sum(optimal_lineup_position_counter.values()))
    optimal_lineup_position_mix = [
        {
            "position": position,
            "count": int(count),
            "share": (float(count) / optimal_lineup_total_rows) if optimal_lineup_total_rows > 0 else 0.0,
        }
        for position, count in optimal_lineup_position_counter.most_common()
    ]
    optimal_flex_total = float(sum(optimal_flex_counter.values()))
    optimal_flex_mix = [
        {
            "position": position,
            "count": int(count),
            "share": (float(count) / optimal_flex_total) if optimal_flex_total > 0 else 0.0,
        }
        for position, count in optimal_flex_counter.most_common()
    ]

    payload: dict[str, Any] = {
        "summary": {
            "source_system": args.source_system,
            "season_start": season_start,
            "season_end": season_end,
            "classic_slates_considered": total_classic_slices,
            "main_slates_analyzed": selected_main_slices,
            "top_players_per_slate": args.top_players_per_slate,
            "high_total_threshold": args.high_total_threshold,
            "selected_main_slate_names": sorted(allowed_main_names),
            "selected_slate_breakdown": [
                {"slate": slate, "count": int(count)}
                for slate, count in selected_slate_counter.most_common()
            ],
        },
        "position_value_summary": position_rows,
        "high_point_total_analysis": {
            "top_players_per_slate": args.top_players_per_slate,
            "high_total_threshold": args.high_total_threshold,
            "baseline_high_total_share": baseline_high_total_share,
            "high_players_high_total_share": high_players_high_total_share,
            "high_total_share_lift": (
                (high_players_high_total_share / baseline_high_total_share)
                if baseline_high_total_share > 0
                else None
            ),
            "baseline_total_band_mix": _counter_mix(baseline_total_band_counter),
            "high_point_total_band_mix": _counter_mix(high_point_total_band_counter),
            "high_point_position_mix": _counter_mix(high_point_position_counter),
        },
        "rb_spread_analysis": {
            "rb_by_spread_role": rb_bucket_rows,
            "rb_avg_points_favorites": _weighted_mean(rb_favorites, "avg_points"),
            "rb_avg_points_underdogs": _weighted_mean(rb_underdogs, "avg_points"),
            "rb_avg_value_favorites": _weighted_mean(rb_favorites, "avg_value"),
            "rb_avg_value_underdogs": _weighted_mean(rb_underdogs, "avg_value"),
            "rb_spread_to_points_correlation": _corr(rb_spread_for_corr, rb_points_for_corr),
            "rb_high_point_spread_mix": _counter_mix(rb_high_point_spread_counter),
            "rb_baseline_spread_mix": _counter_mix(rb_baseline_spread_counter),
            "rb_high_point_underdog_share": rb_high_underdog_share,
            "rb_baseline_underdog_share": rb_base_underdog_share,
        },
        "total_line_point_correlations_by_position": total_line_correlations,
        "optimal_main_lineup_mix": {
            "position_mix": optimal_lineup_position_mix,
            "flex_position_mix": optimal_flex_mix,
        },
    }

    json_path = Path(args.output_json).expanduser().resolve()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    md_path = Path(args.output_md).expanduser().resolve()
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(_render_markdown(payload), encoding="utf-8")

    print(
        json.dumps(
            {
                "source_system": args.source_system,
                "season_start": season_start,
                "season_end": season_end,
                "main_slates_analyzed": selected_main_slices,
                "output_json": str(json_path),
                "output_md": str(md_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
