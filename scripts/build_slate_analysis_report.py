from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a combined professional report for showdown + regular slate analysis."
    )
    parser.add_argument(
        "--docs-dir",
        type=str,
        default="docs",
    )
    parser.add_argument(
        "--output-md",
        type=str,
        default="docs/slate_analysis_report_2024_2025.md",
    )
    parser.add_argument(
        "--output-html",
        type=str,
        default="docs/slate_analysis_report_2024_2025.html",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def _num(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    md = []
    md.append("| " + " | ".join(headers) + " |")
    md.append("|" + "|".join(["---" for _ in headers]) + "|")
    for row in rows:
        md.append("| " + " | ".join(row) + " |")
    return "\n".join(md)


def _build_markdown(
    *,
    generated_at: str,
    showdown_desc: dict[str, Any],
    showdown_model: dict[str, Any],
    showdown_ab: dict[str, Any],
    showdown_sweep: dict[str, Any],
    main_slate: dict[str, Any],
    classic_backtest: dict[str, Any],
) -> str:
    ssum = showdown_ab["summary"]
    msum = main_slate["summary"]
    csum = classic_backtest["summary"]
    model_summary = showdown_model["summary"]

    captain_rows = showdown_desc["captain_position_summary"]
    captain_mix_table = _table(
        ["Captain Pos", "Slates", "Share", "Top Overall Rate", "Avg Captain Pts"],
        [
            [
                str(r["position"]),
                str(r["slates"]),
                _pct(float(r["share"])),
                _pct(float(r["top_overall_rate"])),
                _num(float(r["avg_captain_points"]), 2),
            ]
            for r in captain_rows
        ],
    )

    def _band_table(metric: str) -> str:
        rows = showdown_desc["band_summaries"][metric]
        return _table(
            ["Band", "Slates", "Top Captain Pos", "Position Mix"],
            [
                [
                    str(r["band"]),
                    str(r["slates"]),
                    str(r["top_captain_position"]),
                    ", ".join(f"{item['position']}:{item['count']}" for item in r["position_mix"]),
                ]
                for r in rows
            ],
        )

    sweep_rows = showdown_sweep["ranked_results"]
    sweep_table = _table(
        ["Strength", "Mean Gap Lift", "Median Gap Lift", "Win Rate", "Paired Slates"],
        [
            [
                _num(float(r["strength"]), 2),
                _num(r.get("mean_gap_lift_points"), 3),
                _num(r.get("median_gap_lift_points"), 3),
                _pct(r.get("captain_informed_win_rate")),
                str(r.get("paired_slates", "-")),
            ]
            for r in sweep_rows
        ],
    )

    position_value_table = _table(
        ["Position", "Rows", "Avg Points", "Avg Value (x)", "3x Rate", "4x Rate"],
        [
            [
                str(r["name"]),
                str(r["count"]),
                _num(r.get("avg_points"), 2),
                _num(r.get("avg_value"), 2),
                _pct(r.get("hit_3x_rate")),
                _pct(r.get("hit_4x_rate")),
            ]
            for r in main_slate["position_value_summary"]
        ],
    )

    rb_spread_table = _table(
        ["Spread Bucket", "Rows", "Avg Points", "Avg Value (x)", "3x Rate", "4x Rate"],
        [
            [
                str(r["name"]),
                str(r["count"]),
                _num(r.get("avg_points"), 2),
                _num(r.get("avg_value"), 2),
                _pct(r.get("hit_3x_rate")),
                _pct(r.get("hit_4x_rate")),
            ]
            for r in main_slate["rb_spread_analysis"]["rb_by_spread_role"]
        ],
    )

    flex_mix_table = _table(
        ["Flex Position", "Count", "Share"],
        [
            [str(r["position"]), str(r["count"]), _pct(float(r["share"]))]
            for r in main_slate["optimal_main_lineup_mix"]["flex_position_mix"]
        ],
    )

    lines: list[str] = []
    lines.append("# Football_26 Slate Intelligence Report (2024-2025)")
    lines.append("")
    lines.append(f"_Generated: {generated_at}_")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(
        f"- Showdown captain-informed construction reduced mean gap by "
        f"`{_num(ssum['mean_gap_lift_points'], 2)}` points "
        f"(`{_num(ssum['baseline_mean_gap_points'], 2)}` -> `{_num(ssum['captain_informed_mean_gap_points'], 2)}`) "
        f"with win rate `{_pct(ssum['captain_informed_win_rate'])}`."
    )
    lines.append(
        f"- Best showdown captain prior strength at production scale (`lineups_per_slate={ssum['lineups_per_slate']}`): "
        f"`{_num(showdown_sweep['best_strength_result']['strength'], 2)}`."
    )
    lines.append(
        f"- On regular main slates, high-point players are concentrated in high-total games "
        f"(share lift `{_num(main_slate['high_point_total_analysis']['high_total_share_lift'], 2)}x`)."
    )
    lines.append(
        f"- RB performance in this sample was stronger in underdog buckets than favorite buckets "
        f"(avg points `{_num(main_slate['rb_spread_analysis']['rb_avg_points_underdogs'], 2)}` vs "
        f"`{_num(main_slate['rb_spread_analysis']['rb_avg_points_favorites'], 2)}`)."
    )
    lines.append("")
    lines.append("## Data Scope")
    lines.append("")
    lines.append(
        _table(
            ["Domain", "Scope"],
            [
                ["Showdown descriptive sample", f"{showdown_desc['slates_analyzed']} slates"],
                ["Showdown model eval sample", f"{model_summary['slates_total']} slates"],
                ["Showdown A/B paired sample", f"{ssum['paired_slates']} slates"],
                ["Main-slate value analysis sample", f"{msum['main_slates_analyzed']} slates"],
                ["Classic backtest sample", f"{csum['slates_completed']}/{csum['slates_total']} completed slates"],
            ],
        )
    )
    lines.append("")
    lines.append("## Showdown Analysis")
    lines.append("")
    lines.append("### 1) Historical Winning Captain Archetypes")
    lines.append("")
    lines.append(captain_mix_table)
    lines.append("")
    lines.append("By Total Band")
    lines.append("")
    lines.append(_band_table("total_line_band"))
    lines.append("")
    lines.append("By Spread Band")
    lines.append("")
    lines.append(_band_table("spread_abs_band"))
    lines.append("")
    lines.append("By Team Implied Total Band")
    lines.append("")
    lines.append(_band_table("team_implied_band"))
    lines.append("")
    lines.append("### 2) Captain Archetype Model Quality")
    lines.append("")
    lines.append(
        _table(
            ["Metric", "Value"],
            [
                ["Top-1 Accuracy", _num(model_summary["model_top1_accuracy"], 3)],
                ["Top-2 Accuracy", _num(model_summary["model_top2_accuracy"], 3)],
                ["Baseline Top-1 Accuracy", _num(model_summary["baseline_top1_accuracy"], 3)],
                ["Top-1 Lift", _num(model_summary["top1_accuracy_lift"], 3)],
            ],
        )
    )
    lines.append("")
    lines.append("### 3) Showdown A/B Backtest (Captain-Informed vs Baseline)")
    lines.append("")
    lines.append(
        _table(
            ["Metric", "Value"],
            [
                ["Baseline Mean Gap", _num(ssum["baseline_mean_gap_points"], 3)],
                ["Captain-Informed Mean Gap", _num(ssum["captain_informed_mean_gap_points"], 3)],
                ["Mean Gap Lift", _num(ssum["mean_gap_lift_points"], 3)],
                ["Median Gap Lift", _num(ssum["median_gap_lift_points"], 3)],
                ["Captain-Informed Win Rate", _pct(ssum["captain_informed_win_rate"])],
                ["Gap StdDev Reduction", _num(ssum["stability_lift_stddev_reduction"], 3)],
            ],
        )
    )
    lines.append("")
    lines.append("### 4) Captain Prior Strength Sweep")
    lines.append("")
    lines.append(sweep_table)
    lines.append("")
    lines.append(
        f"Selected production setting: `showdown_captain_prior_strength={_num(showdown_sweep['best_strength_result']['strength'], 2)}`."
    )
    lines.append("")
    lines.append("## Regular Slate (Main/Classic) Analysis")
    lines.append("")
    lines.append("### 1) Baseline Classic Backtest Context")
    lines.append("")
    lines.append(
        _table(
            ["Metric", "Value"],
            [
                ["Completed Slates", f"{csum['slates_completed']}/{csum['slates_total']}"],
                ["Mean Gap", _num(csum["mean_gap_points"], 2)],
                ["Median Gap", _num(csum["median_gap_points"], 2)],
                ["Best Gap", _num(csum["best_case_gap_points"], 2)],
                ["Worst Gap", _num(csum["worst_case_gap_points"], 2)],
            ],
        )
    )
    lines.append("")
    lines.append("### 2) Position Value Drivers")
    lines.append("")
    lines.append(position_value_table)
    lines.append("")
    lines.append("### 3) Over/Under Concentration")
    lines.append("")
    lines.append(
        _table(
            ["Metric", "Value"],
            [
                ["High-Point Players in High Totals", _pct(main_slate["high_point_total_analysis"]["high_players_high_total_share"])],
                ["Baseline High-Total Player Share", _pct(main_slate["high_point_total_analysis"]["baseline_high_total_share"])],
                ["High-Total Share Lift", _num(main_slate["high_point_total_analysis"]["high_total_share_lift"], 2) + "x"],
            ],
        )
    )
    lines.append("")
    lines.append("### 4) RB Performance vs Spread")
    lines.append("")
    lines.append(rb_spread_table)
    lines.append("")
    lines.append(
        _table(
            ["RB Spread Summary", "Value"],
            [
                ["Avg Points (Favorite Buckets)", _num(main_slate["rb_spread_analysis"]["rb_avg_points_favorites"], 2)],
                ["Avg Points (Underdog Buckets)", _num(main_slate["rb_spread_analysis"]["rb_avg_points_underdogs"], 2)],
                ["Avg Value (Favorite Buckets)", _num(main_slate["rb_spread_analysis"]["rb_avg_value_favorites"], 2) + "x"],
                ["Avg Value (Underdog Buckets)", _num(main_slate["rb_spread_analysis"]["rb_avg_value_underdogs"], 2) + "x"],
                ["RB Spread->Points Correlation", _num(main_slate["rb_spread_analysis"]["rb_spread_to_points_correlation"], 3)],
                ["RB High-Point Underdog Share", _pct(main_slate["rb_spread_analysis"]["rb_high_point_underdog_share"])],
                ["RB Baseline Underdog Share", _pct(main_slate["rb_spread_analysis"]["rb_baseline_underdog_share"])],
            ],
        )
    )
    lines.append("")
    lines.append("### 5) Optimal Main-Lineup FLEX Tendencies")
    lines.append("")
    lines.append(flex_mix_table)
    lines.append("")
    lines.append("## Lineup Construction Implications")
    lines.append("")
    lines.append("- Continue using captain-informed showdown generation at prior strength `0.35` as default.")
    lines.append("- In regular main slates, increase exposure to high-total game environments as a learned prior.")
    lines.append("- Do not hard-code RB-favorite assumptions; current sample shows underdog RB buckets outperforming.")
    lines.append("- Keep FLEX policy adaptive with RB/WR priority and TE as conditional leverage.")
    lines.append("")
    lines.append("## Artifact Index")
    lines.append("")
    lines.append("- `docs/showdown_captain_descriptive_2024_2025.json`")
    lines.append("- `docs/showdown_captain_model_eval_2024_2025.json`")
    lines.append("- `docs/optimal_vs_predicted_showdown_captain_ab_2024_2025.json`")
    lines.append("- `docs/showdown_captain_strength_sweep_2024_2025_2500.json`")
    lines.append("- `docs/main_slate_value_driver_analysis_2024_2025.json`")
    lines.append("- `docs/optimal_vs_predicted_2024_2025_classic_tightened_v2.json`")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def _build_html(markdown_report: str) -> str:
    # Keep a deterministic single-file, presentation-ready artifact.
    escaped = (
        markdown_report
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    # Basic markdown-ish rendering via pre-wrap for portability.
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Football_26 Slate Intelligence Report</title>
  <style>
    :root {{
      --bg:#0b1320;
      --panel:#111d31;
      --ink:#e8f1ff;
      --muted:#9db4d4;
      --line:#274266;
      --accent:#24d1ff;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
      color:var(--ink);
      background: radial-gradient(circle at 20% -10%, #1c3f66 0%, transparent 35%), var(--bg);
      padding: 28px;
    }}
    .wrap {{
      max-width: 1120px;
      margin: 0 auto;
      background: linear-gradient(165deg, #13233a, #0f1b2d);
      border:1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 20px 40px rgba(0,0,0,.35);
      padding: 26px 28px;
    }}
    h1 {{
      margin:0 0 14px 0;
      letter-spacing:.02em;
      font-size: 34px;
      color:#f4fbff;
    }}
    .note {{
      color:var(--muted);
      margin:0 0 20px 0;
    }}
    pre {{
      white-space: pre-wrap;
      margin:0;
      line-height:1.45;
      color:var(--ink);
      font-size:14px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Football_26 Slate Intelligence Report</h1>
    <p class="note">Professional summary for showdown and regular slate analysis.</p>
    <pre>{escaped}</pre>
  </div>
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    docs_dir = Path(args.docs_dir).expanduser().resolve()

    showdown_desc = _load_json(docs_dir / "showdown_captain_descriptive_2024_2025.json")
    showdown_model = _load_json(docs_dir / "showdown_captain_model_eval_2024_2025.json")
    showdown_ab = _load_json(docs_dir / "optimal_vs_predicted_showdown_captain_ab_2024_2025.json")
    showdown_sweep = _load_json(docs_dir / "showdown_captain_strength_sweep_2024_2025_2500.json")
    main_slate = _load_json(docs_dir / "main_slate_value_driver_analysis_2024_2025.json")
    classic_backtest = _load_json(docs_dir / "optimal_vs_predicted_2024_2025_classic_tightened_v2.json")

    generated_at = datetime.now(timezone.utc).isoformat()
    markdown = _build_markdown(
        generated_at=generated_at,
        showdown_desc=showdown_desc,
        showdown_model=showdown_model,
        showdown_ab=showdown_ab,
        showdown_sweep=showdown_sweep,
        main_slate=main_slate,
        classic_backtest=classic_backtest,
    )
    html = _build_html(markdown)

    output_md = Path(args.output_md).expanduser().resolve()
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(markdown, encoding="utf-8")

    output_html = Path(args.output_html).expanduser().resolve()
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html, encoding="utf-8")

    print(
        json.dumps(
            {
                "output_md": str(output_md),
                "output_html": str(output_html),
                "generated_at": generated_at,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
