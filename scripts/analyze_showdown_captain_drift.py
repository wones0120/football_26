from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

CAPTAIN_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")


def _season_segment(week: int) -> str:
    if week <= 6:
        return "early"
    if week <= 12:
        return "mid"
    return "late"


def _distribution(rows: list[dict[str, Any]]) -> dict[str, float]:
    counts = Counter(str(row["captain_position"]).upper() for row in rows)
    total = len(rows)
    return {
        position: (float(counts.get(position, 0) / total) if total else 0.0)
        for position in CAPTAIN_POSITIONS
    }


def _compare_segments(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    alert_threshold: float,
    min_segment_slates: int,
) -> dict[str, Any]:
    left_distribution = left["distribution"]
    right_distribution = right["distribution"]
    deltas = {
        position: float(right_distribution[position] - left_distribution[position])
        for position in CAPTAIN_POSITIONS
    }
    total_variation = 0.5 * sum(abs(value) for value in deltas.values())
    enough_data = (
        int(left["slates"]) >= min_segment_slates
        and int(right["slates"]) >= min_segment_slates
    )
    return {
        "from_segment": left["segment_id"],
        "to_segment": right["segment_id"],
        "from_slates": int(left["slates"]),
        "to_slates": int(right["slates"]),
        "total_variation_distance": float(total_variation),
        "position_share_deltas": deltas,
        "largest_position_shift": max(
            CAPTAIN_POSITIONS,
            key=lambda position: abs(deltas[position]),
        ),
        "enough_data": enough_data,
        "alert": bool(enough_data and total_variation >= alert_threshold),
    }


def _report_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Showdown Captain Prior Drift",
        "",
        f"- Alert threshold (total variation): `{payload['alert_threshold']:.3f}`",
        f"- Minimum slates per segment: `{payload['min_segment_slates']}`",
        f"- Alerts: `{payload['alert_count']}`",
        "",
        "## Segment Priors",
        "",
        "| Segment | Slates | QB | RB | WR | TE | K | DST |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["segments"]:
        distribution = row["distribution"]
        lines.append(
            f"| {row['segment_id']} | {row['slates']} | "
            + " | ".join(
                f"{distribution[position] * 100:.1f}%"
                for position in CAPTAIN_POSITIONS
            )
            + " |"
        )
    lines.extend([
        "",
        "## Consecutive Segment Drift",
        "",
        "| From | To | TV Distance | Largest Shift | Alert |",
        "|---|---|---:|---|---|",
    ])
    for row in payload["comparisons"]:
        lines.append(
            f"| {row['from_segment']} | {row['to_segment']} | "
            f"{row['total_variation_distance']:.3f} | "
            f"{row['largest_position_shift']} | "
            f"{'YES' if row['alert'] else 'no'} |"
        )
    lines.extend([
        "",
        "Total variation measures how much captain-position probability mass moved between segments. "
        "Alerts require both segments to meet the minimum sample size.",
    ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect season-segment drift in showdown captain-position priors.",
    )
    parser.add_argument(
        "--dataset-csv",
        default="docs/showdown_captain_training_dataset_2024_2025.csv",
    )
    parser.add_argument("--alert-threshold", type=float, default=0.25)
    parser.add_argument("--min-segment-slates", type=int, default=5)
    parser.add_argument(
        "--output-json",
        default="docs/showdown_captain_drift_2024_2025.json",
    )
    parser.add_argument(
        "--report-md",
        default="docs/showdown_captain_drift_2024_2025.md",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 0.0 <= args.alert_threshold <= 1.0:
        raise ValueError("--alert-threshold must be between 0 and 1.")
    if args.min_segment_slates < 1:
        raise ValueError("--min-segment-slates must be positive.")

    dataset_path = Path(args.dataset_csv).expanduser().resolve()
    with dataset_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = {}
    segment_order = {"early": 0, "mid": 1, "late": 2}
    for row in rows:
        season = int(row["season"])
        segment = _season_segment(int(row["week"]))
        grouped.setdefault((season, segment), []).append(row)

    segments = [
        {
            "segment_id": f"{season}_{segment}",
            "season": season,
            "segment": segment,
            "slates": len(segment_rows),
            "distribution": _distribution(segment_rows),
        }
        for (season, segment), segment_rows in sorted(
            grouped.items(),
            key=lambda item: (item[0][0], segment_order[item[0][1]]),
        )
    ]
    comparisons = [
        _compare_segments(
            segments[index - 1],
            segments[index],
            alert_threshold=args.alert_threshold,
            min_segment_slates=args.min_segment_slates,
        )
        for index in range(1, len(segments))
    ]
    payload = {
        "dataset_csv": str(dataset_path),
        "alert_threshold": float(args.alert_threshold),
        "min_segment_slates": int(args.min_segment_slates),
        "segment_definition": {
            "early": "weeks 1-6",
            "mid": "weeks 7-12",
            "late": "weeks 13+",
        },
        "segments": segments,
        "comparisons": comparisons,
        "alert_count": sum(1 for row in comparisons if row["alert"]),
        "alerts": [row for row in comparisons if row["alert"]],
    }
    output_path = Path(args.output_json).expanduser().resolve()
    report_path = Path(args.report_md).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report_path.write_text(_report_markdown(payload), encoding="utf-8")
    print(json.dumps({
        "segments": len(segments),
        "comparisons": len(comparisons),
        "alert_count": payload["alert_count"],
        "output_json": str(output_path),
        "report_md": str(report_path),
    }, indent=2))


if __name__ == "__main__":
    main()
