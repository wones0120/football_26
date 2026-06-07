from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

import numpy as np
from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.models import PlayerGameFeatureMatrix

POSITIONS = {"QB", "RB", "WR", "TE", "DST"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build matchup-outcome intelligence from player-game matrix rows, "
            "including factor effect sizes and matchup cells."
        )
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--min-group-count", type=int, default=80)
    parser.add_argument("--min-matchup-count", type=int, default=8)
    parser.add_argument(
        "--output-json",
        type=str,
        default="docs/matchup_outcome_intelligence_2024_2025.json",
    )
    parser.add_argument(
        "--output-md",
        type=str,
        default="docs/matchup_outcome_intelligence_2024_2025.md",
    )
    return parser.parse_args()


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _canonical_team(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().upper()
    if not text:
        return None
    aliases = {
        "JAX": "JAC",
        "WSH": "WAS",
        "LA": "LAR",
        "STL": "LAR",
        "SD": "LAC",
        "OAK": "LV",
    }
    return aliases.get(text, text)


def _total_band(total: float | None) -> str:
    if total is None:
        return "unknown"
    if total < 42.0:
        return "<42"
    if total < 47.0:
        return "42-46.9"
    if total < 51.0:
        return "47-50.9"
    return "51+"


def _spread_role(spread: float | None) -> str:
    if spread is None:
        return "unknown"
    if spread <= -7.0:
        return "big_favorite"
    if spread <= -3.0:
        return "favorite"
    if spread < 3.0:
        return "close"
    if spread < 7.0:
        return "underdog"
    return "big_underdog"


def _spread_abs_band(spread: float | None) -> str:
    if spread is None:
        return "unknown"
    abs_spread = abs(spread)
    if abs_spread <= 2.5:
        return "close_<=2.5"
    if abs_spread <= 6.5:
        return "mid_2.6_6.5"
    return "wide_>=6.6"


def _salary_tier(position: str, salary: int) -> str:
    if position == "QB":
        if salary < 5800:
            return "cheap"
        if salary < 7200:
            return "mid"
        return "premium"
    if position in {"RB", "WR", "TE"}:
        if salary < 5000:
            return "cheap"
        if salary < 7000:
            return "mid"
        return "premium"
    if position == "DST":
        if salary < 2800:
            return "cheap"
        if salary < 3400:
            return "mid"
        return "premium"
    return "unknown"


def _injury_bucket(status: str | None) -> str:
    if status is None:
        return "unknown"
    text = status.strip().lower()
    if not text:
        return "unknown"
    if any(token in text for token in ("out", "injured reserve", "ir", "suspended")):
        return "out"
    if "doubt" in text:
        return "doubtful"
    if "question" in text or text == "q":
        return "questionable"
    if "probable" in text:
        return "probable"
    return "active"


def _teammate_out_band(value: int) -> str:
    if value <= 0:
        return "0"
    if value == 1:
        return "1"
    if value == 2:
        return "2"
    return "3+"


def _variance_effect_ratio(rows: list[dict[str, Any]], factor_key: str) -> float | None:
    if len(rows) < 30:
        return None
    y = np.asarray([float(row["dk_points"]) for row in rows], dtype=float)
    if y.shape[0] < 30:
        return None
    total_mean = float(np.mean(y))
    total_ss = float(np.sum((y - total_mean) ** 2))
    if total_ss <= 1e-9:
        return None

    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        buckets[str(row[factor_key])].append(float(row["dk_points"]))
    if len(buckets) < 2:
        return None

    between_ss = 0.0
    for values in buckets.values():
        if not values:
            continue
        mean_v = float(np.mean(values))
        between_ss += float(len(values) * ((mean_v - total_mean) ** 2))
    return float(between_ss / total_ss)


def _agg_new() -> dict[str, float]:
    return {
        "n": 0.0,
        "points_sum": 0.0,
        "value_sum": 0.0,
        "hit3x": 0.0,
        "hit4x": 0.0,
        "over_roll8_sum": 0.0,
        "over_roll8_n": 0.0,
    }


def _agg_add(agg: dict[str, float], row: dict[str, Any]) -> None:
    points = float(row["dk_points"])
    value_x = float(row["value_x"])
    agg["n"] += 1.0
    agg["points_sum"] += points
    agg["value_sum"] += value_x
    if value_x >= 3.0:
        agg["hit3x"] += 1.0
    if value_x >= 4.0:
        agg["hit4x"] += 1.0
    if row["over_roll8"] is not None:
        agg["over_roll8_sum"] += float(row["over_roll8"])
        agg["over_roll8_n"] += 1.0


def _safe_rate(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return float(num / den)


def _finalize_agg(key_name: str, agg: dict[str, float]) -> dict[str, Any]:
    n = int(agg["n"])
    return {
        "name": key_name,
        "count": n,
        "avg_points": float(agg["points_sum"] / max(1.0, agg["n"])),
        "avg_value": float(agg["value_sum"] / max(1.0, agg["n"])),
        "hit3x_rate": _safe_rate(agg["hit3x"], agg["n"]),
        "hit4x_rate": _safe_rate(agg["hit4x"], agg["n"]),
        "avg_over_roll8": (
            float(agg["over_roll8_sum"] / agg["over_roll8_n"]) if agg["over_roll8_n"] > 0 else None
        ),
    }


def _fit_defense_buckets(rows: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    by_position: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = row["defense_pos_allowed_roll8"]
        if value is None:
            continue
        by_position[row["position"]].append(float(value))

    thresholds: dict[str, tuple[float, float]] = {}
    for position, values in by_position.items():
        if len(values) < 40:
            continue
        arr = np.asarray(values, dtype=float)
        q33 = float(np.percentile(arr, 33))
        q66 = float(np.percentile(arr, 66))
        thresholds[position] = (q33, q66)
    return thresholds


def _defense_bucket(value: float | None, thresholds: tuple[float, float] | None) -> str:
    if value is None or thresholds is None:
        return "unknown"
    q33, q66 = thresholds
    if value <= q33:
        return "tough"
    if value >= q66:
        return "favorable"
    return "neutral"


def _load_rows(source_system: str, season_start: int, season_end: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with SessionLocal() as session:
        query = (
            select(PlayerGameFeatureMatrix)
            .where(PlayerGameFeatureMatrix.source_system == source_system)
            .where(PlayerGameFeatureMatrix.season >= season_start)
            .where(PlayerGameFeatureMatrix.season <= season_end)
            .order_by(
                PlayerGameFeatureMatrix.season,
                PlayerGameFeatureMatrix.week,
                PlayerGameFeatureMatrix.game_id,
            )
        )
        rows = session.execute(query).scalars().all()

    for row in rows:
        position = (row.position or "").upper().strip()
        if position not in POSITIONS:
            continue
        salary = _safe_int(row.salary)
        points = _safe_float(row.dk_points)
        if salary is None or salary <= 0 or points is None:
            continue
        value_x = float(points / (salary / 1000.0))
        team = _canonical_team(row.team)
        opponent = _canonical_team(row.opponent)
        over_roll8: float | None = None
        if row.player_roll8_mean is not None:
            over_roll8 = float(points - float(row.player_roll8_mean))
        out.append(
            {
                "season": int(row.season),
                "week": int(row.week),
                "game_id": row.game_id or "unknown_game",
                "player_id": row.player_id,
                "player_name": row.player_name or "unknown",
                "position": position,
                "team": team or "UNK",
                "opponent": opponent or "UNK",
                "salary": salary,
                "dk_points": float(points),
                "value_x": value_x,
                "is_home": (
                    "home" if row.is_home is True else ("away" if row.is_home is False else "unknown")
                ),
                "kickoff_bucket": (row.kickoff_bucket or "unknown").strip().lower() or "unknown",
                "game_total_line": _safe_float(row.game_total_line),
                "team_spread_line": _safe_float(row.team_spread_line),
                "team_implied_total": _safe_float(row.team_implied_total),
                "opponent_implied_total": _safe_float(row.opponent_implied_total),
                "player_roll8_mean": _safe_float(row.player_roll8_mean),
                "defense_pos_allowed_roll8": _safe_float(row.defense_pos_allowed_roll8),
                "player_injury_status": row.player_injury_status,
                "team_skill_out_count": int(row.team_skill_out_count or 0),
                "over_roll8": over_roll8,
            }
        )
    return out


def _top_signal_rows(
    rows: list[dict[str, Any]],
    *,
    key_fields: tuple[str, ...],
    baseline_hit4x_by_pos: dict[str, float],
    min_count: int,
    shrink_prior: float,
    top_n: int,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[tuple[str, ...], dict[str, float]] = defaultdict(_agg_new)
    for row in rows:
        key = tuple(str(row[field]) for field in key_fields)
        _agg_add(grouped[key], row)

    scored_rows: list[dict[str, Any]] = []
    for key, agg in grouped.items():
        n = int(agg["n"])
        if n < min_count:
            continue
        position = key[0] if key else "UNK"
        baseline = float(baseline_hit4x_by_pos.get(position, 0.0))
        group = _finalize_agg("|".join(key), agg)
        raw_hit = float(group["hit4x_rate"])
        alpha = float(agg["n"] / (agg["n"] + shrink_prior))
        adj_hit = ((alpha * raw_hit) + ((1.0 - alpha) * baseline))
        lift = float(adj_hit - baseline)
        group["position"] = position
        group["key_values"] = {name: key[idx] for idx, name in enumerate(key_fields)}
        group["baseline_hit4x_rate"] = baseline
        group["adjusted_hit4x_rate"] = adj_hit
        group["adjusted_hit4x_lift"] = lift
        group["signal_score"] = float(abs(lift) * math.sqrt(max(1.0, agg["n"])))
        scored_rows.append(group)

    scored_rows.sort(key=lambda row: row["adjusted_hit4x_lift"], reverse=True)
    positive = scored_rows[:top_n]
    negative = list(reversed(scored_rows[-top_n:])) if scored_rows else []
    return {"positive": positive, "negative": negative}


def _matchup_cell_rows(
    rows: list[dict[str, Any]],
    *,
    baseline_hit4x_by_pos: dict[str, float],
    min_count: int,
    shrink_prior: float,
    top_n: int,
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str], dict[str, float]] = defaultdict(_agg_new)
    for row in rows:
        key = (row["position"], row["team"], row["opponent"])
        _agg_add(grouped[key], row)

    cells: list[dict[str, Any]] = []
    for (position, team, opponent), agg in grouped.items():
        n = int(agg["n"])
        if n < min_count:
            continue
        baseline = float(baseline_hit4x_by_pos.get(position, 0.0))
        group = _finalize_agg(f"{position}:{team}_vs_{opponent}", agg)
        raw_hit = float(group["hit4x_rate"])
        alpha = float(agg["n"] / (agg["n"] + shrink_prior))
        adj_hit = ((alpha * raw_hit) + ((1.0 - alpha) * baseline))
        lift = float(adj_hit - baseline)
        group["position"] = position
        group["team"] = team
        group["opponent"] = opponent
        group["baseline_hit4x_rate"] = baseline
        group["adjusted_hit4x_rate"] = adj_hit
        group["adjusted_hit4x_lift"] = lift
        group["signal_score"] = float(abs(lift) * math.sqrt(max(1.0, agg["n"])))
        cells.append(group)

    cells.sort(key=lambda row: row["adjusted_hit4x_lift"], reverse=True)
    positive = cells[:top_n]
    negative = list(reversed(cells[-top_n:])) if cells else []
    return {"positive": positive, "negative": negative}


def _render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines: list[str] = []
    lines.append("# Matchup Outcome Intelligence")
    lines.append("")
    lines.append(
        f"- Source: `{summary['source_system']}`  "
        f"Seasons: `{summary['season_start']}-{summary['season_end']}`  "
        f"Rows analyzed: `{summary['rows_analyzed']}`"
    )
    lines.append("")
    lines.append("## Score Drivers (Effect Size)")
    lines.append("")
    lines.append("| Position | Factor | Effect Ratio |")
    lines.append("|---|---|---:|")
    for row in payload["factor_effect_sizes"]:
        lines.append(
            f"| {row['position']} | {row['factor']} | {row['effect_ratio']:.3f} |"
        )
    lines.append("")
    lines.append("## Strongest Positive Context Signals (4x Hit Lift)")
    lines.append("")
    lines.append("| View | Key | Count | Adj 4x Lift | Avg Pts | Avg Value |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for view_name, view in payload["top_context_signals"].items():
        for row in view["positive"][:8]:
            lines.append(
                f"| {view_name} | {row['name']} | {row['count']} | "
                f"{row['adjusted_hit4x_lift'] * 100:.2f}pp | {row['avg_points']:.2f} | {row['avg_value']:.2f}x |"
            )
    lines.append("")
    lines.append("## Strongest Negative Context Signals (4x Hit Lift)")
    lines.append("")
    lines.append("| View | Key | Count | Adj 4x Lift | Avg Pts | Avg Value |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for view_name, view in payload["top_context_signals"].items():
        for row in view["negative"][:8]:
            lines.append(
                f"| {view_name} | {row['name']} | {row['count']} | "
                f"{row['adjusted_hit4x_lift'] * 100:.2f}pp | {row['avg_points']:.2f} | {row['avg_value']:.2f}x |"
            )
    lines.append("")
    lines.append("## Team-vs-Opponent Matchup Cells")
    lines.append("")
    lines.append("| Direction | Cell | Count | Adj 4x Lift | Avg Pts | Avg Value |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for row in payload["matchup_cells"]["positive"][:15]:
        lines.append(
            f"| Positive | {row['name']} | {row['count']} | {row['adjusted_hit4x_lift'] * 100:.2f}pp | "
            f"{row['avg_points']:.2f} | {row['avg_value']:.2f}x |"
        )
    for row in payload["matchup_cells"]["negative"][:15]:
        lines.append(
            f"| Negative | {row['name']} | {row['count']} | {row['adjusted_hit4x_lift'] * 100:.2f}pp | "
            f"{row['avg_points']:.2f} | {row['avg_value']:.2f}x |"
        )
    lines.append("")
    lines.append("## Position Baselines")
    lines.append("")
    lines.append("| Position | Count | Avg Pts | Avg Value | 3x Hit | 4x Hit |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in payload["position_baselines"]:
        lines.append(
            f"| {row['position']} | {row['count']} | {row['avg_points']:.2f} | {row['avg_value']:.2f}x | "
            f"{row['hit3x_rate'] * 100:.1f}% | {row['hit4x_rate'] * 100:.1f}% |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)
    rows = _load_rows(args.source_system, season_start, season_end)
    if not rows:
        raise RuntimeError(
            f"No player-game rows found for {args.source_system} seasons {season_start}-{season_end}."
        )

    defense_thresholds = _fit_defense_buckets(rows)
    for row in rows:
        row["total_band"] = _total_band(row["game_total_line"])
        row["spread_role"] = _spread_role(row["team_spread_line"])
        row["spread_abs_band"] = _spread_abs_band(row["team_spread_line"])
        row["salary_tier"] = _salary_tier(row["position"], int(row["salary"]))
        row["injury_bucket"] = _injury_bucket(row["player_injury_status"])
        row["teammate_out_band"] = _teammate_out_band(int(row["team_skill_out_count"]))
        row["defense_bucket"] = _defense_bucket(
            row["defense_pos_allowed_roll8"],
            defense_thresholds.get(row["position"]),
        )

    baseline_agg: dict[str, dict[str, float]] = defaultdict(_agg_new)
    rows_by_position: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        _agg_add(baseline_agg[row["position"]], row)
        rows_by_position[row["position"]].append(row)

    position_baselines: list[dict[str, Any]] = []
    baseline_hit4x_by_pos: dict[str, float] = {}
    for position, agg in baseline_agg.items():
        row = _finalize_agg(position, agg)
        row["position"] = position
        position_baselines.append(row)
        baseline_hit4x_by_pos[position] = float(row["hit4x_rate"])
    position_baselines.sort(key=lambda row: row["position"])

    factor_keys = [
        "total_band",
        "spread_role",
        "spread_abs_band",
        "defense_bucket",
        "salary_tier",
        "teammate_out_band",
        "kickoff_bucket",
        "is_home",
        "injury_bucket",
    ]
    factor_effect_rows: list[dict[str, Any]] = []
    for position in sorted(rows_by_position.keys()):
        pos_rows = rows_by_position[position]
        for factor in factor_keys:
            effect = _variance_effect_ratio(pos_rows, factor)
            if effect is None:
                continue
            factor_effect_rows.append(
                {
                    "position": position,
                    "factor": factor,
                    "effect_ratio": effect,
                }
            )
    factor_effect_rows.sort(key=lambda row: row["effect_ratio"], reverse=True)

    top_context_signals = {
        "position_x_defense_bucket": _top_signal_rows(
            rows,
            key_fields=("position", "defense_bucket"),
            baseline_hit4x_by_pos=baseline_hit4x_by_pos,
            min_count=max(30, int(args.min_group_count * 0.60)),
            shrink_prior=120.0,
            top_n=20,
        ),
        "position_x_total_band_x_spread_role": _top_signal_rows(
            rows,
            key_fields=("position", "total_band", "spread_role"),
            baseline_hit4x_by_pos=baseline_hit4x_by_pos,
            min_count=args.min_group_count,
            shrink_prior=140.0,
            top_n=20,
        ),
        "position_x_salary_tier_x_teammate_out_band": _top_signal_rows(
            rows,
            key_fields=("position", "salary_tier", "teammate_out_band"),
            baseline_hit4x_by_pos=baseline_hit4x_by_pos,
            min_count=args.min_group_count,
            shrink_prior=140.0,
            top_n=20,
        ),
    }

    matchup_cells = _matchup_cell_rows(
        rows,
        baseline_hit4x_by_pos=baseline_hit4x_by_pos,
        min_count=args.min_matchup_count,
        shrink_prior=20.0,
        top_n=25,
    )

    payload: dict[str, Any] = {
        "summary": {
            "source_system": args.source_system,
            "season_start": season_start,
            "season_end": season_end,
            "rows_analyzed": len(rows),
            "positions": sorted(rows_by_position.keys()),
            "min_group_count": int(args.min_group_count),
            "min_matchup_count": int(args.min_matchup_count),
        },
        "position_baselines": position_baselines,
        "factor_effect_sizes": factor_effect_rows,
        "top_context_signals": top_context_signals,
        "matchup_cells": matchup_cells,
    }

    out_json = Path(args.output_json).expanduser().resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    out_md = Path(args.output_md).expanduser().resolve()
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(_render_markdown(payload), encoding="utf-8")

    print(
        json.dumps(
            {
                "source_system": args.source_system,
                "season_start": season_start,
                "season_end": season_end,
                "rows_analyzed": len(rows),
                "output_json": str(out_json),
                "output_md": str(out_md),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
