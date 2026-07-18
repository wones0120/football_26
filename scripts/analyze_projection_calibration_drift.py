from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import and_, select

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.models import CuratedSalary
from backend.app.schemas import BacktestWeekRequest
from backend.app.services.simulation import SimulationService


def _value(row: Any, field: str) -> Any:
    if isinstance(row, dict):
        return row.get(field)
    return getattr(row, field)


def coverage_metrics(rows: list[Any]) -> dict[str, Any]:
    if not rows:
        raise ValueError("At least one backtest player row is required.")
    p75_hits = sum(
        1 for row in rows if float(_value(row, "actual_points")) <= float(_value(row, "predicted_p75_points"))
    )
    p90_hits = sum(
        1 for row in rows if float(_value(row, "actual_points")) <= float(_value(row, "predicted_p90_points"))
    )
    p95_hits = sum(
        1 for row in rows if float(_value(row, "actual_points")) <= float(_value(row, "predicted_p95_points"))
    )
    actual_ceiling_hits = sum(1 for row in rows if float(_value(row, "actual_points")) >= 25.0)
    predicted_ceiling_sum = sum(
        float(_value(row, "predicted_ceiling_prob_25"))
        for row in rows
    )
    mean_error_sum = sum(
        float(_value(row, "predicted_mean_points")) - float(_value(row, "actual_points"))
        for row in rows
    )
    players = len(rows)
    return {
        "players": players,
        "p75_hits": p75_hits,
        "p75_coverage": p75_hits / players,
        "p75_calibration_error": (p75_hits / players) - 0.75,
        "p90_hits": p90_hits,
        "p90_coverage": p90_hits / players,
        "p90_calibration_error": (p90_hits / players) - 0.90,
        "p95_hits": p95_hits,
        "p95_coverage": p95_hits / players,
        "p95_calibration_error": (p95_hits / players) - 0.95,
        "actual_ceiling_25_hits": actual_ceiling_hits,
        "actual_ceiling_25_rate": actual_ceiling_hits / players,
        "predicted_ceiling_25_sum": predicted_ceiling_sum,
        "predicted_ceiling_25_rate": predicted_ceiling_sum / players,
        "ceiling_25_calibration_error": (
            (predicted_ceiling_sum / players) - (actual_ceiling_hits / players)
        ),
        "mean_error_sum": mean_error_sum,
        "mean_error": mean_error_sum / players,
    }


def _aggregate_slice_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    players = sum(int(row["players"]) for row in rows)
    if players <= 0:
        raise ValueError("Calibration drift aggregation requires evaluated players.")
    payload: dict[str, Any] = {
        "slates": len(rows),
        "players": players,
    }
    for percentile, expected in (("p75", 0.75), ("p90", 0.90), ("p95", 0.95)):
        hits = sum(int(row[f"{percentile}_hits"]) for row in rows)
        coverage = hits / players
        payload[f"{percentile}_hits"] = hits
        payload[f"{percentile}_coverage"] = coverage
        payload[f"{percentile}_calibration_error"] = coverage - expected
    ceiling_hits = sum(int(row["actual_ceiling_25_hits"]) for row in rows)
    predicted_ceiling_sum = sum(float(row["predicted_ceiling_25_sum"]) for row in rows)
    payload.update({
        "actual_ceiling_25_hits": ceiling_hits,
        "actual_ceiling_25_rate": ceiling_hits / players,
        "predicted_ceiling_25_rate": predicted_ceiling_sum / players,
        "ceiling_25_calibration_error": (
            (predicted_ceiling_sum / players) - (ceiling_hits / players)
        ),
        "mean_error": sum(float(row["mean_error_sum"]) for row in rows) / players,
    })
    return payload


def calibration_drift_summary(
    slice_rows: list[dict[str, Any]],
    *,
    calibration_alert_threshold: float,
    drift_alert_threshold: float,
    minimum_players: int,
) -> dict[str, Any]:
    if len(slice_rows) < 2:
        raise ValueError("At least two evaluated slates are required for drift analysis.")
    midpoint = max(1, len(slice_rows) // 2)
    early = _aggregate_slice_metrics(slice_rows[:midpoint])
    late = _aggregate_slice_metrics(slice_rows[midpoint:])
    overall = _aggregate_slice_metrics(slice_rows)
    alerts: list[dict[str, Any]] = []

    for percentile in ("p75", "p90", "p95"):
        calibration_error = float(overall[f"{percentile}_calibration_error"])
        if overall["players"] >= minimum_players and abs(calibration_error) >= calibration_alert_threshold:
            alerts.append({
                "type": "interval_miscalibration",
                "metric": f"{percentile}_coverage",
                "observed": overall[f"{percentile}_coverage"],
                "expected": int(percentile[1:]) / 100.0,
                "delta": calibration_error,
            })
        drift = float(late[f"{percentile}_coverage"] - early[f"{percentile}_coverage"])
        if (
            early["players"] >= minimum_players
            and late["players"] >= minimum_players
            and abs(drift) >= drift_alert_threshold
        ):
            alerts.append({
                "type": "coverage_drift",
                "metric": f"{percentile}_coverage",
                "early": early[f"{percentile}_coverage"],
                "late": late[f"{percentile}_coverage"],
                "delta": drift,
            })

    ceiling_error = float(overall["ceiling_25_calibration_error"])
    if overall["players"] >= minimum_players and abs(ceiling_error) >= calibration_alert_threshold:
        alerts.append({
            "type": "tail_probability_miscalibration",
            "metric": "ceiling_25_rate",
            "predicted": overall["predicted_ceiling_25_rate"],
            "actual": overall["actual_ceiling_25_rate"],
            "delta": ceiling_error,
        })
    return {
        "overall": overall,
        "early_window": early,
        "late_window": late,
        "alerts": alerts,
    }


def _report_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    drift = payload["drift"]
    lines = [
        "# Player Projection Calibration Drift",
        "",
        f"- Evaluated slates: `{summary['slates_evaluated']}` / `{summary['slates_attempted']}`",
        f"- Evaluated players: `{drift['overall']['players']}`",
        f"- Simulation iterations per slate: `{summary['iterations']}`",
        f"- Alerts: `{len(drift['alerts'])}`",
        "",
        "## Overall Calibration",
        "",
        "| Metric | Predicted / Expected | Observed | Error |",
        "|---|---:|---:|---:|",
    ]
    for percentile, expected in (("p75", 0.75), ("p90", 0.90), ("p95", 0.95)):
        lines.append(
            f"| {percentile.upper()} coverage | {expected:.1%} | "
            f"{drift['overall'][f'{percentile}_coverage']:.1%} | "
            f"{drift['overall'][f'{percentile}_calibration_error']:+.1%} |"
        )
    lines.append(
        "| 25+ point tail probability | "
        f"{drift['overall']['predicted_ceiling_25_rate']:.1%} | "
        f"{drift['overall']['actual_ceiling_25_rate']:.1%} | "
        f"{drift['overall']['ceiling_25_calibration_error']:+.1%} |"
    )
    lines.extend([
        "",
        "## Window Drift",
        "",
        "| Metric | Early | Late | Delta |",
        "|---|---:|---:|---:|",
    ])
    for percentile in ("p75", "p90", "p95"):
        early = drift["early_window"][f"{percentile}_coverage"]
        late = drift["late_window"][f"{percentile}_coverage"]
        lines.append(
            f"| {percentile.upper()} coverage | {early:.1%} | {late:.1%} | {late - early:+.1%} |"
        )
    lines.append(
        "| Mean prediction error | "
        f"{drift['early_window']['mean_error']:+.2f} | "
        f"{drift['late_window']['mean_error']:+.2f} | "
        f"{drift['late_window']['mean_error'] - drift['early_window']['mean_error']:+.2f} |"
    )
    lines.extend([
        "",
        "## Alerts",
        "",
    ])
    if not drift["alerts"]:
        lines.append("- None at the configured sample and drift thresholds.")
    else:
        for alert in drift["alerts"]:
            lines.append(f"- `{alert['type']}` on `{alert['metric']}`: `{alert['delta']:+.3f}`.")
    lines.extend([
        "",
        "All simulation calibration lookups are point-in-time safe: only factors from weeks before "
        "the evaluated target are eligible. The report is observational and does not mutate stored factors.",
    ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure historical p75/p90/p95 and tail-probability calibration drift.",
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--slate", default="sunday_main")
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--min-history-games", type=int, default=4)
    parser.add_argument("--prior-weight", type=float, default=12.0)
    parser.add_argument("--noise-scale", type=float, default=0.12)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--limit-slates", type=int, default=0)
    parser.add_argument("--calibration-alert-threshold", type=float, default=0.10)
    parser.add_argument("--drift-alert-threshold", type=float, default=0.08)
    parser.add_argument("--minimum-players", type=int, default=100)
    parser.add_argument(
        "--output-json",
        default="docs/projection_calibration_drift_2024_2025.json",
    )
    parser.add_argument(
        "--report-md",
        default="docs/projection_calibration_drift_2024_2025.md",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.iterations < 500:
        raise ValueError("--iterations must be at least 500.")
    if not 0.0 < args.calibration_alert_threshold < 1.0:
        raise ValueError("--calibration-alert-threshold must be between 0 and 1.")
    if not 0.0 < args.drift_alert_threshold < 1.0:
        raise ValueError("--drift-alert-threshold must be between 0 and 1.")
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)

    with SessionLocal() as session:
        filters = [
            CuratedSalary.source_system == args.source_system,
            CuratedSalary.season >= season_start,
            CuratedSalary.season <= season_end,
        ]
        if args.slate:
            filters.append(CuratedSalary.slate == args.slate)
        slices = session.execute(
            select(CuratedSalary.season, CuratedSalary.week, CuratedSalary.slate)
            .where(and_(*filters))
            .group_by(CuratedSalary.season, CuratedSalary.week, CuratedSalary.slate)
            .order_by(CuratedSalary.season, CuratedSalary.week, CuratedSalary.slate)
        ).all()
        if args.limit_slates > 0:
            slices = slices[-args.limit_slates :]
        if len(slices) < 2:
            raise ValueError("At least two curated salary slices are required.")

        service = SimulationService(session)
        slice_rows: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for index, (season, week, slate) in enumerate(slices):
            request = BacktestWeekRequest(
                source_system=args.source_system,
                season=int(season),
                week=int(week),
                slate=str(slate),
                iterations=args.iterations,
                min_history_games=args.min_history_games,
                prior_weight=args.prior_weight,
                noise_scale=args.noise_scale,
                random_seed=args.random_seed + index,
            )
            try:
                result = service._backtest_week_internal(
                    request,
                    use_calibration=True,
                    persist_calibration=False,
                    include_rows=True,
                )
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                failures.append({
                    "season": int(season),
                    "week": int(week),
                    "slate": str(slate),
                    "error": str(exc),
                })
                continue
            metrics = coverage_metrics(result.rows)
            slice_rows.append({
                "season": int(season),
                "week": int(week),
                "slate": str(slate),
                **metrics,
            })

    if len(slice_rows) < 2:
        raise ValueError("Fewer than two historical slates produced calibration rows.")
    drift = calibration_drift_summary(
        slice_rows,
        calibration_alert_threshold=args.calibration_alert_threshold,
        drift_alert_threshold=args.drift_alert_threshold,
        minimum_players=args.minimum_players,
    )
    payload = {
        "summary": {
            "source_system": args.source_system,
            "season_start": season_start,
            "season_end": season_end,
            "slate": args.slate,
            "iterations": args.iterations,
            "random_seed": args.random_seed,
            "slates_attempted": len(slices),
            "slates_evaluated": len(slice_rows),
            "slates_failed": len(failures),
            "point_in_time_calibration": True,
            "mutates_calibration_factors": False,
            "calibration_alert_threshold": args.calibration_alert_threshold,
            "drift_alert_threshold": args.drift_alert_threshold,
            "minimum_players": args.minimum_players,
        },
        "drift": drift,
        "slices": slice_rows,
        "failures": failures,
    }
    output_path = Path(args.output_json).expanduser().resolve()
    report_path = Path(args.report_md).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report_path.write_text(_report_markdown(payload), encoding="utf-8")
    print(json.dumps({
        **payload["summary"],
        "players": drift["overall"]["players"],
        "alerts": len(drift["alerts"]),
        "output_json": str(output_path),
        "report_md": str(report_path),
    }, indent=2))


if __name__ == "__main__":
    main()
