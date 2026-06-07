from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Explain when matchup-outcome prior backtests helped or hurt by joining "
            "paired slate results to player-game feature context."
        )
    )
    parser.add_argument(
        "--input-json",
        default="docs/matchup_outcome_prior_strength_sweep_20slates.json",
    )
    parser.add_argument("--strength", type=float, default=None)
    parser.add_argument("--source-system", default="draftkings")
    parser.add_argument(
        "--output-json",
        default="docs/matchup_prior_help_diagnostics_20slates.json",
    )
    parser.add_argument(
        "--report-md",
        default="docs/matchup_prior_help_diagnostics_20slates.md",
    )
    return parser.parse_args()


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _mean(values: list[float]) -> float | None:
    return float(statistics.mean(values)) if values else None


def _median(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def _pct(numerator: int, denominator: int) -> float | None:
    return float(numerator / denominator) if denominator else None


def _total_bucket(value: float | None) -> str:
    if value is None:
        return "unknown_total"
    if value < 42:
        return "low_total"
    if value < 47:
        return "mid_total"
    if value < 51:
        return "high_total"
    return "shootout_total"


def _implied_bucket(value: float | None) -> str:
    if value is None:
        return "unknown_implied"
    if value < 21:
        return "low_implied"
    if value < 24:
        return "mid_implied"
    if value < 27:
        return "high_implied"
    return "elite_implied"


def _share_bucket(value: float | None, prefix: str) -> str:
    if value is None:
        return f"{prefix}_unknown"
    if value < 0.25:
        return f"{prefix}_low"
    if value < 0.50:
        return f"{prefix}_medium"
    if value < 0.75:
        return f"{prefix}_high"
    return f"{prefix}_very_high"


def _count_bucket(value: int, prefix: str) -> str:
    if value <= 0:
        return f"{prefix}_none"
    if value == 1:
        return f"{prefix}_one"
    if value <= 3:
        return f"{prefix}_few"
    return f"{prefix}_many"


def _salary_bucket(value: float | None) -> str:
    if value is None:
        return "unknown_salary"
    if value < 4000:
        return "sub_4k"
    if value < 5500:
        return "4k_5_5k"
    if value < 7000:
        return "5_5k_7k"
    return "7k_plus"


def _status(lift: float) -> str:
    if lift > 0.001:
        return "helped"
    if lift < -0.001:
        return "hurt"
    return "neutral"


def _load_strength_result(payload: dict[str, Any], strength: float | None) -> dict[str, Any]:
    results = payload.get("ranked_results") or []
    if strength is None:
        best = payload.get("best_strength_result")
        if isinstance(best, dict):
            return best
        if results:
            return results[0]
        raise ValueError("No strength results found in input JSON.")

    for result in results:
        if abs(float(result.get("strength", -999.0)) - float(strength)) < 1e-9:
            return result
    raise ValueError(f"Strength {strength} was not found in input JSON.")


def _fetch_slate_feature_rows(
    *,
    source_system: str,
    season: int,
    week: int,
    slate: str,
) -> list[dict[str, Any]]:
    query = text(
        """
        SELECT
            position,
            salary,
            dk_points,
            game_total_line,
            team_spread_line,
            team_implied_total,
            opponent_implied_total,
            is_home,
            kickoff_bucket
        FROM player_game_feature_matrix
        WHERE source_system = :source_system
          AND season = :season
          AND week = :week
          AND slate = :slate
        """
    )
    with SessionLocal() as session:
        rows = session.execute(
            query,
            {
                "source_system": source_system,
                "season": season,
                "week": week,
                "slate": slate,
            },
        ).mappings().all()
    return [dict(row) for row in rows]


def _summarize_slate_features(rows: list[dict[str, Any]]) -> dict[str, Any]:
    skill_positions = {"QB", "RB", "WR", "TE"}
    skill_rows = [row for row in rows if str(row.get("position") or "").upper() in skill_positions]
    salaries = [_safe_float(row.get("salary")) for row in rows]
    salaries = [value for value in salaries if value is not None]
    skill_salaries = [_safe_float(row.get("salary")) for row in skill_rows]
    skill_salaries = [value for value in skill_salaries if value is not None]
    points = [_safe_float(row.get("dk_points")) for row in rows]
    points = [value for value in points if value is not None]
    totals = [_safe_float(row.get("game_total_line")) for row in rows]
    totals = [value for value in totals if value is not None]
    implied = [_safe_float(row.get("team_implied_total")) for row in rows]
    implied = [value for value in implied if value is not None]
    spreads = [_safe_float(row.get("team_spread_line")) for row in rows]
    spreads = [value for value in spreads if value is not None]
    abs_spreads = [abs(value) for value in spreads]

    low_salary_skill = [
        row
        for row in skill_rows
        if (salary := _safe_float(row.get("salary"))) is not None and salary <= 4500
    ]
    low_salary_breakouts = [
        row
        for row in low_salary_skill
        if (points_value := _safe_float(row.get("dk_points"))) is not None and points_value >= 15
    ]
    value_breakouts = []
    for row in skill_rows:
        salary = _safe_float(row.get("salary"))
        points_value = _safe_float(row.get("dk_points"))
        if salary is None or salary <= 0 or points_value is None:
            continue
        if points_value >= 15 and (points_value / (salary / 1000.0)) >= 3.5:
            value_breakouts.append(row)

    high_total_skill = [
        row
        for row in skill_rows
        if (total := _safe_float(row.get("game_total_line"))) is not None and total >= 48
    ]
    close_spread_rows = [
        row
        for row in rows
        if (spread := _safe_float(row.get("team_spread_line"))) is not None and abs(spread) < 3
    ]
    favorite_skill = [
        row
        for row in skill_rows
        if (spread := _safe_float(row.get("team_spread_line"))) is not None and spread <= -3
    ]
    big_favorite_skill = [
        row
        for row in skill_rows
        if (spread := _safe_float(row.get("team_spread_line"))) is not None and spread <= -7
    ]
    underdog_skill = [
        row
        for row in skill_rows
        if (spread := _safe_float(row.get("team_spread_line"))) is not None and spread >= 3
    ]

    top_row = None
    if rows:
        top_row = max(rows, key=lambda row: _safe_float(row.get("dk_points")) or -999.0)
    top_salary = _safe_float(top_row.get("salary")) if top_row else None

    return {
        "player_rows": len(rows),
        "skill_player_rows": len(skill_rows),
        "avg_salary": _mean(salaries),
        "median_skill_salary": _median(skill_salaries),
        "max_actual_points": max(points) if points else None,
        "top_actual_position": str(top_row.get("position")) if top_row else None,
        "top_actual_salary": top_salary,
        "top_actual_salary_bucket": _salary_bucket(top_salary),
        "low_salary_skill_count": len(low_salary_skill),
        "low_salary_skill_share": _pct(len(low_salary_skill), len(skill_rows)),
        "low_salary_breakout_count": len(low_salary_breakouts),
        "value_breakout_count": len(value_breakouts),
        "vegas_player_share": _pct(len(totals), len(rows)),
        "max_game_total_line": max(totals) if totals else None,
        "avg_game_total_line": _mean(totals),
        "max_team_implied_total": max(implied) if implied else None,
        "avg_abs_spread": _mean(abs_spreads),
        "close_spread_player_share": _pct(len(close_spread_rows), len(rows)),
        "high_total_skill_share": _pct(len(high_total_skill), len(skill_rows)),
        "favorite_skill_share": _pct(len(favorite_skill), len(skill_rows)),
        "big_favorite_skill_share": _pct(len(big_favorite_skill), len(skill_rows)),
        "underdog_skill_share": _pct(len(underdog_skill), len(skill_rows)),
    }


def _bucketize_future_safe(row: dict[str, Any]) -> dict[str, str]:
    return {
        "slate": str(row["slate"]),
        "max_total_bucket": _total_bucket(row.get("max_game_total_line")),
        "max_implied_bucket": _implied_bucket(row.get("max_team_implied_total")),
        "high_total_skill_share_bucket": _share_bucket(
            row.get("high_total_skill_share"), "high_total_skill"
        ),
        "close_spread_share_bucket": _share_bucket(
            row.get("close_spread_player_share"), "close_spread"
        ),
        "favorite_skill_share_bucket": _share_bucket(
            row.get("favorite_skill_share"), "favorite_skill"
        ),
        "low_salary_skill_share_bucket": _share_bucket(
            row.get("low_salary_skill_share"), "low_salary_skill"
        ),
    }


def _bucketize_outcome_explanation(row: dict[str, Any]) -> dict[str, str]:
    return {
        "low_salary_breakout_bucket": _count_bucket(
            int(row.get("low_salary_breakout_count") or 0), "low_salary_breakout"
        ),
        "value_breakout_bucket": _count_bucket(
            int(row.get("value_breakout_count") or 0), "value_breakout"
        ),
        "top_actual_position": str(row.get("top_actual_position") or "unknown_position"),
        "top_actual_salary_bucket": str(row.get("top_actual_salary_bucket") or "unknown_salary"),
    }


def _bucketize(row: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {
        "future_safe": _bucketize_future_safe(row),
        "outcome_explanation": _bucketize_outcome_explanation(row),
    }


def _summarize_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    lifts = [float(row["gap_lift_points"]) for row in rows]
    helped = sum(1 for value in lifts if value > 0.001)
    hurt = sum(1 for value in lifts if value < -0.001)
    return {
        "slates": len(rows),
        "mean_gap_lift_points": _mean(lifts),
        "median_gap_lift_points": _median(lifts),
        "help_rate": helped / len(rows) if rows else None,
        "hurt_rate": hurt / len(rows) if rows else None,
        "min_gap_lift_points": min(lifts) if lifts else None,
        "max_gap_lift_points": max(lifts) if lifts else None,
    }


def _group_diagnostics(enriched_rows: list[dict[str, Any]], *, bucket_group: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in enriched_rows:
        for bucket_name, bucket_value in row["buckets"].get(bucket_group, {}).items():
            grouped[(bucket_name, bucket_value)].append(row)

    diagnostics: list[dict[str, Any]] = []
    for (bucket_name, bucket_value), rows in grouped.items():
        if len(rows) < 2:
            continue
        diagnostics.append(
            {
                "bucket_name": bucket_name,
                "bucket_value": bucket_value,
                **_summarize_group(rows),
            }
        )
    return sorted(
        diagnostics,
        key=lambda row: (
            row["mean_gap_lift_points"] if row["mean_gap_lift_points"] is not None else -999.0,
            row["slates"],
        ),
        reverse=True,
    )


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    summary = payload["summary"]
    lines.append("# Matchup Prior Help Diagnostics")
    lines.append("")
    lines.append(
        f"- Source: `{payload['config']['source_system']}`  "
        f"Strength: `{payload['config']['strength']}`  "
        f"Paired slates: `{summary['paired_slates']}`"
    )
    lines.append(
        f"- Mean gap lift: `{_fmt(summary['mean_gap_lift_points'])}`  "
        f"Help rate: `{_fmt((summary['help_rate'] or 0) * 100, 1)}%`  "
        f"Hurt rate: `{_fmt((summary['hurt_rate'] or 0) * 100, 1)}%`"
    )
    lines.append("")

    lines.append("## Strongest Future-Safe Help Buckets")
    lines.append("")
    lines.append("| Bucket | Value | Slates | Mean Lift | Help Rate | Hurt Rate |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for row in payload["future_safe_bucket_diagnostics"][:10]:
        lines.append(
            f"| {row['bucket_name']} | {row['bucket_value']} | {row['slates']} | "
            f"{_fmt(row['mean_gap_lift_points'])} | "
            f"{_fmt((row['help_rate'] or 0) * 100, 1)}% | "
            f"{_fmt((row['hurt_rate'] or 0) * 100, 1)}% |"
        )
    lines.append("")

    lines.append("## Strongest Future-Safe Hurt Buckets")
    lines.append("")
    lines.append("| Bucket | Value | Slates | Mean Lift | Help Rate | Hurt Rate |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for row in list(reversed(payload["future_safe_bucket_diagnostics"]))[:10]:
        lines.append(
            f"| {row['bucket_name']} | {row['bucket_value']} | {row['slates']} | "
            f"{_fmt(row['mean_gap_lift_points'])} | "
            f"{_fmt((row['help_rate'] or 0) * 100, 1)}% | "
            f"{_fmt((row['hurt_rate'] or 0) * 100, 1)}% |"
        )
    lines.append("")

    lines.append("## Outcome Explanation Buckets")
    lines.append("")
    lines.append(
        "These buckets use actual outcomes, so they explain what happened but must not be used directly for future scoring."
    )
    lines.append("")
    lines.append("| Bucket | Value | Slates | Mean Lift | Help Rate | Hurt Rate |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for row in payload["outcome_bucket_diagnostics"][:10]:
        lines.append(
            f"| {row['bucket_name']} | {row['bucket_value']} | {row['slates']} | "
            f"{_fmt(row['mean_gap_lift_points'])} | "
            f"{_fmt((row['help_rate'] or 0) * 100, 1)}% | "
            f"{_fmt((row['hurt_rate'] or 0) * 100, 1)}% |"
        )
    lines.append("")

    lines.append("## Slate Details")
    lines.append("")
    lines.append(
        "| Season | Week | Slate | Status | Lift | Baseline Gap | Informed Gap | "
        "Max Total | Max Implied | Low Salary Breakouts | Value Breakouts | Top Actual |"
    )
    lines.append("|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for row in sorted(payload["slate_rows"], key=lambda item: float(item["gap_lift_points"]), reverse=True):
        top_actual = (
            f"{row.get('top_actual_position') or '-'} "
            f"{_fmt(row.get('max_actual_points'))} pts "
            f"({_fmt(row.get('top_actual_salary'), 0)})"
        )
        lines.append(
            f"| {row['season']} | {row['week']} | {row['slate']} | {row['result_status']} | "
            f"{_fmt(row['gap_lift_points'])} | "
            f"{_fmt(row['baseline_gap_points'])} | "
            f"{_fmt(row['matchup_informed_gap_points'])} | "
            f"{_fmt(row.get('max_game_total_line'))} | "
            f"{_fmt(row.get('max_team_implied_total'))} | "
            f"{row.get('low_salary_breakout_count')} | "
            f"{row.get('value_breakout_count')} | {top_actual} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_json).expanduser().resolve()
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    strength_result = _load_strength_result(payload, args.strength)
    strength = float(strength_result["strength"])

    enriched_rows: list[dict[str, Any]] = []
    for paired_row in strength_result.get("paired_rows", []):
        season = int(paired_row["season"])
        week = int(paired_row["week"])
        slate = str(paired_row["slate"])
        feature_rows = _fetch_slate_feature_rows(
            source_system=args.source_system,
            season=season,
            week=week,
            slate=slate,
        )
        feature_summary = _summarize_slate_features(feature_rows)
        enriched = {
            **paired_row,
            **feature_summary,
            "feature_rows_found": len(feature_rows),
            "result_status": _status(float(paired_row["gap_lift_points"])),
        }
        enriched["buckets"] = _bucketize(enriched)
        enriched_rows.append(enriched)

    overall = _summarize_group(enriched_rows)
    output_payload = {
        "config": {
            "input_json": str(input_path),
            "source_system": args.source_system,
            "strength": strength,
        },
        "summary": {
            **overall,
            "paired_slates": len(enriched_rows),
            "helped_slates": sum(1 for row in enriched_rows if row["result_status"] == "helped"),
            "hurt_slates": sum(1 for row in enriched_rows if row["result_status"] == "hurt"),
            "neutral_slates": sum(1 for row in enriched_rows if row["result_status"] == "neutral"),
        },
        "future_safe_bucket_diagnostics": _group_diagnostics(
            enriched_rows,
            bucket_group="future_safe",
        ),
        "outcome_bucket_diagnostics": _group_diagnostics(
            enriched_rows,
            bucket_group="outcome_explanation",
        ),
        "slate_rows": enriched_rows,
    }
    output_payload["bucket_diagnostics"] = (
        output_payload["future_safe_bucket_diagnostics"]
        + output_payload["outcome_bucket_diagnostics"]
    )

    output_json = Path(args.output_json).expanduser().resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    report_md = Path(args.report_md).expanduser().resolve()
    report_md.parent.mkdir(parents=True, exist_ok=True)
    report_md.write_text(_render_markdown(output_payload), encoding="utf-8")

    print(
        json.dumps(
            {
                "strength": strength,
                "paired_slates": output_payload["summary"]["paired_slates"],
                "mean_gap_lift_points": output_payload["summary"]["mean_gap_lift_points"],
                "help_rate": output_payload["summary"]["help_rate"],
                "hurt_rate": output_payload["summary"]["hurt_rate"],
                "output_json": str(output_json),
                "report_md": str(report_md),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
