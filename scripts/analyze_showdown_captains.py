from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.services.lineup_learning import LineupLearningService, ShowdownLineup, ShowdownPlayerPoolRow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Descriptive analysis of historical winning captain patterns on showdown slates."
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--limit-slates", type=int, default=0)
    parser.add_argument(
        "--output-json",
        type=str,
        default="docs/showdown_captain_descriptive_2024_2025.json",
    )
    parser.add_argument(
        "--output-md",
        type=str,
        default="docs/showdown_captain_descriptive_2024_2025.md",
    )
    return parser.parse_args()


def _band_total_line(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "unknown"
    if value < 40:
        return "<40"
    if value < 45:
        return "40-44.9"
    if value < 50:
        return "45-49.9"
    return "50+"


def _band_spread_abs(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "unknown"
    if value <= 3:
        return "<=3"
    if value <= 7:
        return "3.1-7"
    return ">7"


def _band_implied_total(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "unknown"
    if value < 18:
        return "<18"
    if value < 22:
        return "18-21.9"
    if value < 26:
        return "22-25.9"
    return "26+"


def _to_table_rows(counter: Counter[str], total: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, count in sorted(counter.items(), key=lambda item: item[1], reverse=True):
        pct = (count / total) if total > 0 else 0.0
        rows.append({"key": key, "count": int(count), "pct": pct})
    return rows


def _lineup_row(
    season: int,
    week: int,
    slate: str,
    lineup: ShowdownLineup,
    pool: list[ShowdownPlayerPoolRow],
    optimal_points: float,
    optimal_salary: int,
) -> dict[str, Any]:
    captain = lineup.captain
    all_points = [row.actual_points for row in pool if math.isfinite(row.actual_points)]
    team_points = [
        row.actual_points
        for row in pool
        if row.team == captain.team and math.isfinite(row.actual_points)
    ]
    top_overall = max(all_points) if all_points else None
    top_team = max(team_points) if team_points else None
    captain_points = float(captain.actual_points)
    is_top_overall = bool(top_overall is not None and captain_points >= (top_overall - 1e-9))
    is_top_team = bool(top_team is not None and captain_points >= (top_team - 1e-9))
    spread_abs = abs(captain.team_spread_line) if captain.team_spread_line is not None else None
    return {
        "season": season,
        "week": week,
        "slate": slate,
        "captain_name": captain.name,
        "captain_position": captain.position,
        "captain_team": captain.team,
        "captain_salary": int(captain.captain_salary),
        "captain_actual_points_base": captain_points,
        "captain_actual_points_captain": 1.5 * captain_points,
        "captain_projected_mean_base": float(captain.projected_mean_points),
        "captain_projected_p90_base": float(captain.projected_p90_points),
        "captain_is_top_scorer_overall": is_top_overall,
        "captain_is_top_scorer_team": is_top_team,
        "optimal_lineup_points": float(optimal_points),
        "optimal_salary_used": int(optimal_salary),
        "game_total_line": captain.game_total_line,
        "game_spread_abs": spread_abs,
        "captain_team_implied_total": captain.team_implied_total,
        "captain_opp_implied_total": captain.opponent_implied_total,
        "total_line_band": _band_total_line(captain.game_total_line),
        "spread_abs_band": _band_spread_abs(spread_abs),
        "team_implied_band": _band_implied_total(captain.team_implied_total),
    }


def _build_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Showdown Captain Descriptive Analysis")
    lines.append("")
    lines.append(
        f"- Source: `{summary['source_system']}`  "
        f"Seasons: `{summary['season_start']}-{summary['season_end']}`  "
        f"Slates analyzed: `{summary['slates_analyzed']}`"
    )
    lines.append("")

    lines.append("## Captain Position Mix")
    lines.append("")
    lines.append("| Position | Slates | Share | Top Overall Rate | Top Team Rate | Avg Captain Pts | Avg Optimal Lineup Pts |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for row in summary["captain_position_summary"]:
        lines.append(
            f"| {row['position']} | {row['slates']} | {row['share'] * 100:.1f}% | "
            f"{row['top_overall_rate'] * 100:.1f}% | {row['top_team_rate'] * 100:.1f}% | "
            f"{row['avg_captain_points']:.2f} | {row['avg_optimal_lineup_points']:.2f} |"
        )
    lines.append("")

    for metric in ("total_line_band", "spread_abs_band", "team_implied_band"):
        lines.append(f"## Captain Mix by `{metric}`")
        lines.append("")
        lines.append("| Band | Slates | Top Captain Pos | Position Mix |")
        lines.append("|---|---:|---|---|")
        for row in summary["band_summaries"][metric]:
            mix_text = ", ".join([f"{item['position']}:{item['count']}" for item in row["position_mix"]])
            lines.append(
                f"| {row['band']} | {row['slates']} | {row['top_captain_position']} | {mix_text} |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)

    slice_rows: list[dict[str, Any]] = []
    by_position: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_band_position: dict[str, dict[str, Counter[str]]] = {
        "total_line_band": defaultdict(Counter),
        "spread_abs_band": defaultdict(Counter),
        "team_implied_band": defaultdict(Counter),
    }

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
            lineup, optimal_points, optimal_salary = optimal
            row = _lineup_row(season, week, slate, lineup, pool, optimal_points, optimal_salary)
            slice_rows.append(row)
            by_position[row["captain_position"]].append(row)
            by_band_position["total_line_band"][row["total_line_band"]][row["captain_position"]] += 1
            by_band_position["spread_abs_band"][row["spread_abs_band"]][row["captain_position"]] += 1
            by_band_position["team_implied_band"][row["team_implied_band"]][row["captain_position"]] += 1

    position_summary: list[dict[str, Any]] = []
    total_slates = len(slice_rows)
    for position, rows in sorted(by_position.items(), key=lambda item: len(item[1]), reverse=True):
        slates = len(rows)
        top_overall_rate = sum(1 for row in rows if row["captain_is_top_scorer_overall"]) / slates
        top_team_rate = sum(1 for row in rows if row["captain_is_top_scorer_team"]) / slates
        avg_captain_points = statistics.mean(row["captain_actual_points_base"] for row in rows)
        avg_optimal_lineup_points = statistics.mean(row["optimal_lineup_points"] for row in rows)
        avg_captain_salary = statistics.mean(row["captain_salary"] for row in rows)
        position_summary.append(
            {
                "position": position,
                "slates": slates,
                "share": (slates / total_slates) if total_slates else 0.0,
                "top_overall_rate": top_overall_rate,
                "top_team_rate": top_team_rate,
                "avg_captain_points": avg_captain_points,
                "avg_optimal_lineup_points": avg_optimal_lineup_points,
                "avg_captain_salary": avg_captain_salary,
            }
        )

    band_summaries: dict[str, list[dict[str, Any]]] = {}
    for metric, buckets in by_band_position.items():
        rows: list[dict[str, Any]] = []
        for band, counter in sorted(buckets.items(), key=lambda item: sum(item[1].values()), reverse=True):
            slates = int(sum(counter.values()))
            mix = [
                {"position": position, "count": int(count), "share": (count / slates) if slates > 0 else 0.0}
                for position, count in counter.most_common()
            ]
            rows.append(
                {
                    "band": band,
                    "slates": slates,
                    "top_captain_position": mix[0]["position"] if mix else "NA",
                    "position_mix": mix,
                }
            )
        band_summaries[metric] = rows

    summary = {
        "source_system": args.source_system,
        "season_start": season_start,
        "season_end": season_end,
        "slates_analyzed": total_slates,
        "captain_position_summary": position_summary,
        "band_summaries": band_summaries,
        "slice_rows": slice_rows,
    }

    output_json = Path(args.output_json).expanduser().resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    output_md = Path(args.output_md).expanduser().resolve()
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_build_markdown(summary), encoding="utf-8")

    print(
        json.dumps(
            {
                "source_system": args.source_system,
                "season_start": season_start,
                "season_end": season_end,
                "slates_analyzed": total_slates,
                "output_json": str(output_json),
                "output_md": str(output_md),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
