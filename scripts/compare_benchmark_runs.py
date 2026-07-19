from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK_ROOT = REPO_ROOT / "docs" / "benchmarks"


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    higher_is_better: bool


METRICS: list[MetricSpec] = [
    MetricSpec("classic.mean_gap_points", "Classic mean gap points", higher_is_better=False),
    MetricSpec("classic.median_gap_points", "Classic median gap points", higher_is_better=False),
    MetricSpec("showdown.mean_gap_points", "Showdown baseline mean gap points", higher_is_better=False),
    MetricSpec("showdown.median_gap_points", "Showdown baseline median gap points", higher_is_better=False),
    MetricSpec("captain_ab.captain_informed_win_rate", "Captain-informed win rate", higher_is_better=True),
    MetricSpec("captain_ab.mean_gap_lift_points", "Captain-informed mean gap lift", higher_is_better=True),
    MetricSpec("captain_ab.stability_lift_stddev_reduction", "Captain-informed stability lift", higher_is_better=True),
    MetricSpec("captain_ab.captain_informed_mean_gap_points", "Captain-informed mean gap points", higher_is_better=False),
    MetricSpec("main.main_slates_analyzed", "Main slates analyzed", higher_is_better=True),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare one benchmark run directory to another and emit a delta report."
    )
    parser.add_argument("--benchmarks-root", default=str(DEFAULT_BENCHMARK_ROOT))
    parser.add_argument("--baseline-run-dir", default="")
    parser.add_argument("--current-run-dir", default="")
    parser.add_argument("--output-md", default="")
    parser.add_argument("--output-json", default="")
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _extract(run_dir: Path) -> dict[str, float]:
    classic = _load_json(run_dir / "classic_backtest.json").get("summary", {})
    showdown = _load_json(run_dir / "showdown_backtest_baseline.json").get("summary", {})
    captain_ab = _load_json(run_dir / "showdown_captain_ab.json").get("summary", {})
    main = _load_json(run_dir / "main_slate_value_driver_analysis.json").get("summary", {})

    values: dict[str, float] = {}
    for key, value in {
        "classic.mean_gap_points": classic.get("mean_gap_points"),
        "classic.median_gap_points": classic.get("median_gap_points"),
        "showdown.mean_gap_points": showdown.get("mean_gap_points"),
        "showdown.median_gap_points": showdown.get("median_gap_points"),
        "captain_ab.captain_informed_win_rate": captain_ab.get("captain_informed_win_rate"),
        "captain_ab.mean_gap_lift_points": captain_ab.get("mean_gap_lift_points"),
        "captain_ab.stability_lift_stddev_reduction": captain_ab.get("stability_lift_stddev_reduction"),
        "captain_ab.captain_informed_mean_gap_points": captain_ab.get("captain_informed_mean_gap_points"),
        "main.main_slates_analyzed": main.get("main_slates_analyzed"),
    }.items():
        if isinstance(value, (int, float)):
            values[key] = float(value)
    return values


def _resolve_runs(benchmarks_root: Path, baseline_arg: str, current_arg: str) -> tuple[Path, Path]:
    if baseline_arg and current_arg:
        baseline = Path(baseline_arg).expanduser().resolve()
        current = Path(current_arg).expanduser().resolve()
        return baseline, current
    if current_arg:
        current = Path(current_arg).expanduser().resolve()
        candidates = sorted(
            [
                path
                for path in benchmarks_root.iterdir()
                if path.is_dir()
                and path.resolve() != current
                and path.name < current.name
                and _load_json(path / "suite_manifest.json").get("status") == "ok"
            ],
            key=lambda path: path.name,
        )
        if not candidates:
            raise ValueError(
                "Need an earlier successful benchmark run for comparison."
            )
        return candidates[-1], current

    candidates = sorted(
        [path for path in benchmarks_root.iterdir() if path.is_dir() and (path / "suite_manifest.json").exists()],
        key=lambda path: path.name,
    )
    if len(candidates) < 2:
        raise ValueError("Need at least two benchmark run directories with suite_manifest.json.")
    return candidates[-2], candidates[-1]


def _trend(delta: float, higher_is_better: bool, tolerance: float = 1e-9) -> str:
    if abs(delta) <= tolerance:
        return "FLAT"
    improved = delta > 0 if higher_is_better else delta < 0
    return "UP" if improved else "DOWN"


def _fmt(value: float | None, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def _build_markdown(
    *,
    baseline_dir: Path,
    current_dir: Path,
    baseline_values: dict[str, float],
    current_values: dict[str, float],
) -> str:
    lines: list[str] = []
    lines.append("# Benchmark Delta Report")
    lines.append("")
    lines.append(f"- Baseline run: `{baseline_dir}`")
    lines.append(f"- Current run: `{current_dir}`")
    lines.append("")
    lines.append("| Metric | Baseline | Current | Delta | Trend |")
    lines.append("|---|---:|---:|---:|---|")

    for spec in METRICS:
        before = baseline_values.get(spec.key)
        after = current_values.get(spec.key)
        if before is None or after is None:
            lines.append(f"| {spec.label} | {_fmt(before)} | {_fmt(after)} | n/a | MISSING |")
            continue
        delta = after - before
        lines.append(
            f"| {spec.label} | {_fmt(before)} | {_fmt(after)} | {_fmt(delta)} | {_trend(delta, spec.higher_is_better)} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    benchmarks_root = Path(args.benchmarks_root).expanduser().resolve()
    if not benchmarks_root.exists():
        raise ValueError(f"Benchmarks root does not exist: {benchmarks_root}")

    baseline_dir, current_dir = _resolve_runs(benchmarks_root, args.baseline_run_dir, args.current_run_dir)
    baseline_values = _extract(baseline_dir)
    current_values = _extract(current_dir)

    comparison_rows: list[dict[str, Any]] = []
    for spec in METRICS:
        before = baseline_values.get(spec.key)
        after = current_values.get(spec.key)
        if before is None or after is None:
            comparison_rows.append(
                {
                    "metric": spec.key,
                    "label": spec.label,
                    "higher_is_better": spec.higher_is_better,
                    "baseline": before,
                    "current": after,
                    "delta": None,
                    "trend": "MISSING",
                }
            )
            continue
        delta = after - before
        comparison_rows.append(
            {
                "metric": spec.key,
                "label": spec.label,
                "higher_is_better": spec.higher_is_better,
                "baseline": before,
                "current": after,
                "delta": delta,
                "trend": _trend(delta, spec.higher_is_better),
            }
        )

    markdown = _build_markdown(
        baseline_dir=baseline_dir,
        current_dir=current_dir,
        baseline_values=baseline_values,
        current_values=current_values,
    )
    print(markdown)

    output_md = (
        Path(args.output_md).expanduser().resolve()
        if args.output_md
        else current_dir / "delta_vs_previous.md"
    )
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(markdown, encoding="utf-8")

    output_json = (
        Path(args.output_json).expanduser().resolve()
        if args.output_json
        else current_dir / "delta_vs_previous.json"
    )
    payload = {
        "baseline_run_dir": str(baseline_dir),
        "current_run_dir": str(current_dir),
        "rows": comparison_rows,
    }
    output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"\nWrote markdown: {output_md}")
    print(f"Wrote json: {output_json}")


if __name__ == "__main__":
    main()
