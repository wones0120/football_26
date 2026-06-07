from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Train an auditable, future-safe gate for deciding when to apply the "
            "classic matchup-outcome prior."
        )
    )
    parser.add_argument(
        "--diagnostics-json",
        default="docs/matchup_prior_help_diagnostics_20slates_5000.json",
    )
    parser.add_argument("--base-prior-strength", type=float, default=0.15)
    parser.add_argument("--min-rule-support", type=int, default=3)
    parser.add_argument("--min-positive-rule-mean-lift", type=float, default=2.0)
    parser.add_argument("--max-positive-rule-hurt-rate", type=float, default=0.35)
    parser.add_argument("--min-negative-rule-mean-lift", type=float, default=-1.0)
    parser.add_argument("--min-negative-rule-hurt-rate", type=float, default=0.20)
    parser.add_argument(
        "--thresholds",
        default="-2,0,2,4,6,8,10,12",
        help="Comma-separated gate score thresholds to evaluate.",
    )
    parser.add_argument(
        "--output-json",
        default="docs/matchup_prior_gate_20slates_5000.json",
    )
    parser.add_argument(
        "--report-md",
        default="docs/matchup_prior_gate_20slates_5000.md",
    )
    return parser.parse_args()


def _mean(values: list[float]) -> float | None:
    return float(statistics.mean(values)) if values else None


def _median(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _parse_thresholds(raw: str) -> list[float]:
    values: list[float] = []
    for token in raw.split(","):
        token = token.strip()
        if token:
            values.append(float(token))
    if not values:
        raise ValueError("At least one threshold is required.")
    return sorted(set(values))


def _eligible_rules(
    diagnostics: list[dict[str, Any]],
    *,
    min_support: int,
    min_positive_mean_lift: float,
    max_positive_hurt_rate: float,
    min_negative_mean_lift: float,
    min_negative_hurt_rate: float,
) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for row in diagnostics:
        slates = int(row.get("slates") or 0)
        mean_lift = row.get("mean_gap_lift_points")
        hurt_rate = row.get("hurt_rate")
        if mean_lift is None or hurt_rate is None:
            continue
        if slates < min_support:
            continue
        mean_lift_float = float(mean_lift)
        hurt_rate_float = float(hurt_rate)
        is_positive_rule = (
            mean_lift_float >= min_positive_mean_lift
            and hurt_rate_float <= max_positive_hurt_rate
        )
        is_negative_rule = (
            mean_lift_float <= min_negative_mean_lift
            and hurt_rate_float >= min_negative_hurt_rate
        )
        if not is_positive_rule and not is_negative_rule:
            continue
        rules.append(
            {
                "bucket_name": str(row["bucket_name"]),
                "bucket_value": str(row["bucket_value"]),
                "weight": mean_lift_float,
                "slates": slates,
                "help_rate": float(row.get("help_rate") or 0.0),
                "hurt_rate": hurt_rate_float,
                "direction": "positive" if is_positive_rule else "negative",
            }
        )
    return sorted(rules, key=lambda item: item["weight"], reverse=True)


def _gate_score(row: dict[str, Any], rules: list[dict[str, Any]], *, exclude_self: bool = False) -> float:
    buckets = (row.get("buckets") or {}).get("future_safe") or {}
    matched: list[float] = []
    for rule in rules:
        if buckets.get(rule["bucket_name"]) != rule["bucket_value"]:
            continue
        if exclude_self and int(rule["slates"]) <= 1:
            continue
        matched.append(float(rule["weight"]))
    if not matched:
        return 0.0
    return float(sum(matched))


def _score_rows(rows: list[dict[str, Any]], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for row in rows:
        scored.append(
            {
                **row,
                "gate_score": _gate_score(row, rules),
            }
        )
    return scored


def _evaluate_threshold(rows: list[dict[str, Any]], *, threshold: float) -> dict[str, Any]:
    gated_rows: list[dict[str, Any]] = []
    for row in rows:
        active = float(row["gate_score"]) >= threshold
        baseline_gap = float(row["baseline_gap_points"])
        informed_gap = float(row["matchup_informed_gap_points"])
        selected_gap = informed_gap if active else baseline_gap
        gated_rows.append(
            {
                "season": row["season"],
                "week": row["week"],
                "slate": row["slate"],
                "active": active,
                "gate_score": float(row["gate_score"]),
                "baseline_gap_points": baseline_gap,
                "always_on_gap_points": informed_gap,
                "gated_gap_points": selected_gap,
                "gated_lift_vs_baseline_points": baseline_gap - selected_gap,
                "gated_lift_vs_always_on_points": informed_gap - selected_gap,
            }
        )

    baseline_gaps = [float(row["baseline_gap_points"]) for row in gated_rows]
    always_on_gaps = [float(row["always_on_gap_points"]) for row in gated_rows]
    gated_gaps = [float(row["gated_gap_points"]) for row in gated_rows]
    active_rows = [row for row in gated_rows if row["active"]]
    gated_lifts = [float(row["gated_lift_vs_baseline_points"]) for row in gated_rows]
    return {
        "threshold": float(threshold),
        "paired_slates": len(gated_rows),
        "active_slates": len(active_rows),
        "active_rate": (len(active_rows) / len(gated_rows)) if gated_rows else None,
        "baseline_mean_gap_points": _mean(baseline_gaps),
        "always_on_mean_gap_points": _mean(always_on_gaps),
        "gated_mean_gap_points": _mean(gated_gaps),
        "gated_mean_lift_vs_baseline_points": _mean(
            [base - gated for base, gated in zip(baseline_gaps, gated_gaps, strict=True)]
        ),
        "gated_mean_lift_vs_always_on_points": _mean(
            [always - gated for always, gated in zip(always_on_gaps, gated_gaps, strict=True)]
        ),
        "gated_median_lift_vs_baseline_points": _median(gated_lifts),
        "gated_win_rate_vs_baseline": (
            sum(1 for value in gated_lifts if value > 0) / len(gated_lifts)
            if gated_lifts
            else None
        ),
        "rows": gated_rows,
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Matchup Prior Gate")
    lines.append("")
    lines.append(
        f"- Source diagnostics: `{payload['config']['diagnostics_json']}`  "
        f"Base prior strength: `{payload['config']['base_prior_strength']}`"
    )
    lines.append(
        f"- Selected threshold: `{payload['selected_threshold']}`  "
        f"Rules: `{len(payload['rules'])}`"
    )
    lines.append("")
    lines.append("## Threshold Evaluation")
    lines.append("")
    lines.append(
        "| Threshold | Active Slates | Active Rate | Gated Mean Gap | "
        "Lift vs Baseline | Lift vs Always On | Win Rate |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|---:|")
    for row in payload["threshold_results"]:
        lines.append(
            f"| {row['threshold']:.2f} | {row['active_slates']} | "
            f"{_fmt((row['active_rate'] or 0) * 100, 1)}% | "
            f"{_fmt(row['gated_mean_gap_points'])} | "
            f"{_fmt(row['gated_mean_lift_vs_baseline_points'])} | "
            f"{_fmt(row['gated_mean_lift_vs_always_on_points'])} | "
            f"{_fmt((row['gated_win_rate_vs_baseline'] or 0) * 100, 1)}% |"
        )
    lines.append("")
    lines.append("## Rules")
    lines.append("")
    lines.append("| Bucket | Value | Weight | Support | Help Rate | Hurt Rate |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for rule in payload["rules"]:
        lines.append(
            f"| {rule['bucket_name']} | {rule['bucket_value']} | "
            f"{_fmt(rule['weight'])} | {rule['slates']} | "
            f"{_fmt(rule['help_rate'] * 100, 1)}% | "
            f"{_fmt(rule['hurt_rate'] * 100, 1)}% |"
        )
    lines.append("")
    lines.append("## Selected Gate Rows")
    lines.append("")
    selected = payload["selected_threshold_result"]
    lines.append("| Season | Week | Slate | Active | Score | Baseline Gap | Always-On Gap | Gated Gap |")
    lines.append("|---:|---:|---|---|---:|---:|---:|---:|")
    for row in sorted(selected["rows"], key=lambda item: float(item["gate_score"]), reverse=True):
        lines.append(
            f"| {row['season']} | {row['week']} | {row['slate']} | "
            f"{'yes' if row['active'] else 'no'} | "
            f"{_fmt(row['gate_score'])} | "
            f"{_fmt(row['baseline_gap_points'])} | "
            f"{_fmt(row['always_on_gap_points'])} | "
            f"{_fmt(row['gated_gap_points'])} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    diagnostics_path = Path(args.diagnostics_json).expanduser().resolve()
    diagnostics_payload = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    rules = _eligible_rules(
        diagnostics_payload.get("future_safe_bucket_diagnostics") or [],
        min_support=args.min_rule_support,
        min_positive_mean_lift=args.min_positive_rule_mean_lift,
        max_positive_hurt_rate=args.max_positive_rule_hurt_rate,
        min_negative_mean_lift=args.min_negative_rule_mean_lift,
        min_negative_hurt_rate=args.min_negative_rule_hurt_rate,
    )
    scored_rows = _score_rows(diagnostics_payload.get("slate_rows") or [], rules)
    threshold_results = [
        _evaluate_threshold(scored_rows, threshold=threshold)
        for threshold in _parse_thresholds(args.thresholds)
    ]
    ranked = sorted(
        threshold_results,
        key=lambda row: (
            row["gated_mean_lift_vs_baseline_points"]
            if row["gated_mean_lift_vs_baseline_points"] is not None
            else -999999.0,
            row["gated_mean_lift_vs_always_on_points"]
            if row["gated_mean_lift_vs_always_on_points"] is not None
            else -999999.0,
            -(row["active_slates"]),
        ),
        reverse=True,
    )
    selected = ranked[0] if ranked else None
    if selected is None:
        raise ValueError("No threshold evaluation rows produced.")

    output_payload = {
        "model_type": "matchup_prior_gate_v1",
        "config": {
            "diagnostics_json": str(diagnostics_path),
            "base_prior_strength": float(args.base_prior_strength),
            "min_rule_support": args.min_rule_support,
            "min_positive_rule_mean_lift": args.min_positive_rule_mean_lift,
            "max_positive_rule_hurt_rate": args.max_positive_rule_hurt_rate,
            "min_negative_rule_mean_lift": args.min_negative_rule_mean_lift,
            "min_negative_rule_hurt_rate": args.min_negative_rule_hurt_rate,
        },
        "base_prior_strength": float(args.base_prior_strength),
        "selected_threshold": float(selected["threshold"]),
        "rules": rules,
        "threshold_results": threshold_results,
        "selected_threshold_result": selected,
    }

    output_json = Path(args.output_json).expanduser().resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    report_md = Path(args.report_md).expanduser().resolve()
    report_md.parent.mkdir(parents=True, exist_ok=True)
    report_md.write_text(_render_markdown(output_payload), encoding="utf-8")

    print(
        json.dumps(
            {
                "rules": len(rules),
                "selected_threshold": selected["threshold"],
                "active_slates": selected["active_slates"],
                "gated_mean_gap_points": selected["gated_mean_gap_points"],
                "gated_mean_lift_vs_baseline_points": selected[
                    "gated_mean_lift_vs_baseline_points"
                ],
                "gated_mean_lift_vs_always_on_points": selected[
                    "gated_mean_lift_vs_always_on_points"
                ],
                "output_json": str(output_json),
                "report_md": str(report_md),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
