from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _role_bucket(captain_salary: float, top_position_flex_salary: float) -> str:
    if top_position_flex_salary <= 0:
        return "unknown"
    salary_ratio = captain_salary / (1.5 * top_position_flex_salary)
    if salary_ratio >= 0.90:
        return "premium"
    if salary_ratio >= 0.70:
        return "core"
    return "value"


def _total_band(total: float) -> str:
    if total <= 0:
        return "unknown_total"
    if total < 42:
        return "low_total"
    if total < 48:
        return "mid_total"
    return "high_total"


def _spread_band(spread_abs: float) -> str:
    if spread_abs < 0:
        return "unknown_spread"
    if spread_abs <= 3:
        return "close"
    if spread_abs <= 7:
        return "moderate"
    return "wide"


def _scenario_key(total: float, spread_abs: float) -> str:
    return f"{_total_band(total)}__{_spread_band(spread_abs)}"


def _smoothed_priors(
    counts: Counter[str],
    archetypes: list[str],
    *,
    alpha: float,
) -> dict[str, float]:
    denominator = float(sum(counts.values()) + (alpha * len(archetypes)))
    if denominator <= 0:
        return {archetype: 0.0 for archetype in archetypes}
    return {
        archetype: float((counts.get(archetype, 0) + alpha) / denominator)
        for archetype in archetypes
    }


def _report_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Showdown Captain Role and Scenario Analysis",
        "",
        f"- Slates: `{payload['summary']['slates']}`",
        f"- Captain archetypes: `{payload['summary']['archetypes']}`",
        f"- Scenario cells: `{payload['summary']['scenario_cells']}`",
        "",
        "## Captain Role Archetypes",
        "",
        "| Archetype | Slates | Share |",
        "|---|---:|---:|",
    ]
    for row in payload["archetype_distribution"]:
        lines.append(
            f"| {row['archetype']} | {row['count']} | {row['share'] * 100:.1f}% |"
        )
    lines.extend([
        "",
        "## Scenario Priors",
        "",
        "| Scenario | Slates | Prior Source | Leading Archetype | Probability |",
        "|---|---:|---|---|---:|",
    ])
    for row in payload["scenario_priors"]:
        lines.append(
            f"| {row['scenario']} | {row['slates']} | {row['prior_source']} | "
            f"{row['leading_archetype']} | "
            f"{row['leading_probability'] * 100:.1f}% |"
        )
    lines.extend([
        "",
        "Role is based on captain salary relative to the highest flex salary at that position: "
        "premium >=90%, core 70-90%, and value <70%. Scenario priors use Laplace smoothing and "
        "pregame total/spread context, so they can be applied to future slates.",
    ])
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze showdown captain role archetypes by game scenario.",
    )
    parser.add_argument(
        "--dataset-csv",
        default="docs/showdown_captain_training_dataset_2024_2025.csv",
    )
    parser.add_argument("--smoothing-alpha", type=float, default=1.0)
    parser.add_argument("--min-scenario-slates", type=int, default=5)
    parser.add_argument(
        "--output-json",
        default="docs/showdown_captain_scenarios_2024_2025.json",
    )
    parser.add_argument(
        "--report-md",
        default="docs/showdown_captain_scenarios_2024_2025.md",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.smoothing_alpha <= 0:
        raise ValueError("--smoothing-alpha must be positive.")
    if args.min_scenario_slates < 1:
        raise ValueError("--min-scenario-slates must be positive.")
    dataset_path = Path(args.dataset_csv).expanduser().resolve()
    with dataset_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    enriched: list[dict[str, Any]] = []
    for row in rows:
        position = str(row["captain_position"]).upper()
        top_salary = float(row.get(f"top_{position.lower()}_salary") or 0.0)
        role = _role_bucket(float(row["captain_salary"]), top_salary)
        archetype = f"{position}:{role}"
        scenario = _scenario_key(
            float(row.get("game_total_line") or 0.0),
            float(row.get("game_spread_abs") or -1.0),
        )
        enriched.append({
            "season": int(row["season"]),
            "week": int(row["week"]),
            "slate": str(row["slate"]),
            "captain_position": position,
            "captain_role": role,
            "captain_archetype": archetype,
            "scenario": scenario,
        })

    archetype_counts = Counter(row["captain_archetype"] for row in enriched)
    archetypes = sorted(archetype_counts)
    global_priors = _smoothed_priors(
        archetype_counts,
        archetypes,
        alpha=float(args.smoothing_alpha),
    )
    scenario_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in enriched:
        scenario_counts[row["scenario"]][row["captain_archetype"]] += 1

    scenario_priors: list[dict[str, Any]] = []
    for scenario, counts in sorted(scenario_counts.items()):
        priors = _smoothed_priors(
            counts,
            archetypes,
            alpha=float(args.smoothing_alpha),
        )
        scenario_slates = int(sum(counts.values()))
        use_scenario_prior = scenario_slates >= args.min_scenario_slates
        recommended_priors = priors if use_scenario_prior else global_priors
        leading_archetype = max(recommended_priors, key=recommended_priors.get)
        scenario_priors.append({
            "scenario": scenario,
            "slates": scenario_slates,
            "observed_counts": dict(sorted(counts.items())),
            "smoothed_archetype_priors": priors,
            "recommended_archetype_priors": recommended_priors,
            "prior_source": "scenario" if use_scenario_prior else "global_fallback",
            "leading_archetype": leading_archetype,
            "leading_probability": recommended_priors[leading_archetype],
        })

    total = len(enriched)
    payload = {
        "summary": {
            "dataset_csv": str(dataset_path),
            "slates": total,
            "archetypes": len(archetypes),
            "scenario_cells": len(scenario_priors),
            "smoothing_alpha": float(args.smoothing_alpha),
            "min_scenario_slates": int(args.min_scenario_slates),
            "future_safe_context": ["game_total_line", "game_spread_abs"],
        },
        "role_definition": {
            "premium": "captain salary >= 90% of position maximum",
            "core": "captain salary >= 70% and < 90% of position maximum",
            "value": "captain salary < 70% of position maximum",
        },
        "scenario_definition": {
            "total": {"low": "<42", "mid": "42-47.9", "high": "48+"},
            "spread_abs": {"close": "<=3", "moderate": "3-7", "wide": ">7"},
        },
        "archetype_distribution": [
            {
                "archetype": archetype,
                "count": int(count),
                "share": float(count / total) if total else 0.0,
            }
            for archetype, count in archetype_counts.most_common()
        ],
        "scenario_priors": scenario_priors,
        "rows": enriched,
    }
    output_path = Path(args.output_json).expanduser().resolve()
    report_path = Path(args.report_md).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report_path.write_text(_report_markdown(payload), encoding="utf-8")
    print(json.dumps({
        "slates": total,
        "archetypes": len(archetypes),
        "scenario_cells": len(scenario_priors),
        "output_json": str(output_path),
        "report_md": str(report_path),
    }, indent=2))


if __name__ == "__main__":
    main()
