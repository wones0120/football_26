from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
DEFAULT_BENCHMARK_ROOT = REPO_ROOT / "docs" / "benchmarks"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the canonical benchmark suite (classic backtest, showdown baseline, "
            "showdown captain-informed A/B, and main-slate value-driver analysis)."
        )
    )
    parser.add_argument("--source-system", default="draftkings", choices=["draftkings", "fanduel"])
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)

    parser.add_argument("--lineups-per-slate-classic", type=int, default=1000)
    parser.add_argument("--lineups-per-slate-showdown", type=int, default=1000)
    parser.add_argument("--lineups-per-slate-showdown-ab", type=int, default=2500)

    parser.add_argument("--training-window-slates", type=int, default=24)
    parser.add_argument("--min-training-slates", type=int, default=4)
    parser.add_argument("--min-training-rows", type=int, default=2000)

    parser.add_argument("--ab-min-training-slates", type=int, default=2)
    parser.add_argument("--ab-min-training-rows", type=int, default=500)

    parser.add_argument("--learned-only", dest="learned_only", action="store_true")
    parser.add_argument("--allow-heuristics", dest="learned_only", action="store_false")
    parser.set_defaults(learned_only=True)

    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--confidence-level", type=float, default=0.95)
    parser.add_argument("--limit-slates", type=int, default=0)
    parser.add_argument("--showdown-captain-model-path", default="docs/showdown_captain_model_2024_2025.json")
    parser.add_argument("--showdown-captain-prior-strength", type=float, default=0.35)

    parser.add_argument("--main-slate-names", default="main,sunday_main,normal,sunday")
    parser.add_argument("--top-players-per-slate", type=int, default=15)
    parser.add_argument("--high-total-threshold", type=float, default=48.0)
    parser.add_argument("--analysis-limit-slates", type=int, default=0)

    parser.add_argument("--output-dir", default="")
    parser.add_argument("--quiet-progress", action="store_true")
    return parser.parse_args()


def _learned_only_flag(learned_only: bool) -> str:
    return "--learned-only" if learned_only else "--allow-heuristics"


def _append_limit_args(command: list[str], limit_slates: int) -> None:
    if limit_slates > 0:
        command.extend(["--limit-slates", str(limit_slates)])


def _run_step(step_name: str, command: list[str], log_file: Path) -> dict[str, Any]:
    started_at = time.monotonic()
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(f"\n=== STEP: {step_name} ===\n")
        handle.write("COMMAND: " + " ".join(command) + "\n\n")

        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            handle.write(line)
        return_code = process.wait()

    duration_seconds = time.monotonic() - started_at
    if return_code != 0:
        raise RuntimeError(f"Step failed ({step_name}) with exit code {return_code}")
    return {
        "step": step_name,
        "status": "ok",
        "duration_seconds": duration_seconds,
        "command": command,
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _format_number(value: Any, digits: int = 3) -> str:
    if isinstance(value, (int, float)):
        if isinstance(value, int):
            return str(value)
        return f"{value:.{digits}f}"
    return "n/a"


def _format_confidence_interval(summary: dict[str, Any], metric: str) -> str:
    confidence = summary.get("confidence_intervals", {})
    metrics = confidence.get("metrics", {}) if isinstance(confidence, dict) else {}
    interval = metrics.get(metric) if isinstance(metrics, dict) else None
    if not isinstance(interval, dict):
        return "n/a"
    return (
        f"[{_format_number(interval.get('lower'))}, {_format_number(interval.get('upper'))}] "
        f"(SE={_format_number(interval.get('standard_error'))}, "
        f"n={_format_number(interval.get('sample_size'), 0)})"
    )


def _confidence_label(summary: dict[str, Any]) -> str:
    confidence = summary.get("confidence_intervals", {})
    level = confidence.get("confidence_level") if isinstance(confidence, dict) else None
    return f"{float(level) * 100:.1f}%" if isinstance(level, (int, float)) else "confidence"


def _write_summary_markdown(
    *,
    output_path: Path,
    classic_json: Path,
    showdown_json: Path,
    captain_ab_json: Path,
    main_analysis_json: Path,
) -> None:
    classic = _load_json(classic_json)
    showdown = _load_json(showdown_json)
    captain_ab = _load_json(captain_ab_json)
    main_analysis = _load_json(main_analysis_json)

    classic_summary = classic.get("summary", {})
    showdown_summary = showdown.get("summary", {})
    captain_summary = captain_ab.get("summary", {})
    main_summary = main_analysis.get("summary", {})

    lines: list[str] = []
    lines.append("# Benchmark Suite Summary")
    lines.append("")
    lines.append("## Classic Backtest")
    lines.append(
        f"- Mean gap points: {_format_number(classic_summary.get('mean_gap_points'))}"
    )
    lines.append(
        f"- Mean gap {_confidence_label(classic_summary)} CI: "
        f"{_format_confidence_interval(classic_summary, 'mean_gap_points')}"
    )
    lines.append(
        f"- Median gap points: {_format_number(classic_summary.get('median_gap_points'))}"
    )
    lines.append(
        f"- Median gap {_confidence_label(classic_summary)} CI: "
        f"{_format_confidence_interval(classic_summary, 'median_gap_points')}"
    )
    lines.append(
        f"- Slates completed: {_format_number(classic_summary.get('slates_completed'), 0)}"
    )
    lines.append(
        f"- Slates failed/skipped: {_format_number(classic_summary.get('slates_failed_or_skipped'), 0)}"
    )
    lines.append("")
    lines.append("## Showdown Baseline")
    lines.append(
        f"- Mean gap points: {_format_number(showdown_summary.get('mean_gap_points'))}"
    )
    lines.append(
        f"- Mean gap {_confidence_label(showdown_summary)} CI: "
        f"{_format_confidence_interval(showdown_summary, 'mean_gap_points')}"
    )
    lines.append(
        f"- Median gap points: {_format_number(showdown_summary.get('median_gap_points'))}"
    )
    lines.append(
        f"- Median gap {_confidence_label(showdown_summary)} CI: "
        f"{_format_confidence_interval(showdown_summary, 'median_gap_points')}"
    )
    lines.append(
        f"- Slates completed: {_format_number(showdown_summary.get('slates_completed'), 0)}"
    )
    lines.append(
        f"- Slates failed/skipped: {_format_number(showdown_summary.get('slates_failed_or_skipped'), 0)}"
    )
    lines.append("")
    lines.append("## Showdown Captain-Informed A/B")
    lines.append(
        f"- Captain-informed win rate: {_format_number(captain_summary.get('captain_informed_win_rate'))}"
    )
    lines.append(
        f"- Captain win-rate {_confidence_label(captain_summary)} CI: "
        f"{_format_confidence_interval(captain_summary, 'captain_informed_win_rate')}"
    )
    lines.append(
        f"- Mean gap lift points: {_format_number(captain_summary.get('mean_gap_lift_points'))}"
    )
    lines.append(
        f"- Mean gap-lift {_confidence_label(captain_summary)} CI: "
        f"{_format_confidence_interval(captain_summary, 'mean_gap_lift_points')}"
    )
    lines.append(
        f"- Stability lift (stddev reduction): {_format_number(captain_summary.get('stability_lift_stddev_reduction'))}"
    )
    lines.append(
        f"- Paired slates: {_format_number(captain_summary.get('paired_slates'), 0)}"
    )
    lines.append("")
    lines.append("## Main-Slate Value Driver Analysis")
    lines.append(
        f"- Main slates analyzed: {_format_number(main_summary.get('main_slates_analyzed'), 0)}"
    )
    lines.append(
        f"- Classic slates considered: {_format_number(main_summary.get('classic_slates_considered'), 0)}"
    )
    lines.append(
        f"- Top players per slate: {_format_number(main_summary.get('top_players_per_slate'), 0)}"
    )
    lines.append(
        f"- High-total threshold: {_format_number(main_summary.get('high_total_threshold'))}"
    )
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    season_start = min(args.season_start, args.season_end)
    season_end = max(args.season_start, args.season_end)

    benchmark_root = DEFAULT_BENCHMARK_ROOT
    benchmark_root.mkdir(parents=True, exist_ok=True)

    if args.output_dir:
        run_dir = Path(args.output_dir).expanduser().resolve()
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = benchmark_root / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    classic_json = run_dir / "classic_backtest.json"
    showdown_json = run_dir / "showdown_backtest_baseline.json"
    captain_ab_json = run_dir / "showdown_captain_ab.json"
    main_analysis_json = run_dir / "main_slate_value_driver_analysis.json"
    main_analysis_md = run_dir / "main_slate_value_driver_analysis.md"
    suite_summary_md = run_dir / "summary.md"
    run_log = run_dir / "run.log"
    manifest_path = run_dir / "suite_manifest.json"

    steps: list[dict[str, Any]] = []
    suite_started = datetime.now().isoformat(timespec="seconds")

    classic_command = [
        sys.executable,
        str(SCRIPTS_DIR / "run_optimal_vs_predicted_lineups.py"),
        "--source-system",
        args.source_system,
        "--season-start",
        str(season_start),
        "--season-end",
        str(season_end),
        "--slate-type",
        "classic",
        "--lineups-per-slate",
        str(args.lineups_per_slate_classic),
        "--training-window-slates",
        str(args.training_window_slates),
        "--min-training-slates",
        str(args.min_training_slates),
        "--min-training-rows",
        str(args.min_training_rows),
        _learned_only_flag(args.learned_only),
        "--random-seed",
        str(args.random_seed),
        "--bootstrap-samples",
        str(args.bootstrap_samples),
        "--confidence-level",
        str(args.confidence_level),
        "--output-json",
        str(classic_json),
    ]
    _append_limit_args(classic_command, args.limit_slates)
    if args.quiet_progress:
        classic_command.append("--quiet-progress")

    showdown_command = [
        sys.executable,
        str(SCRIPTS_DIR / "run_optimal_vs_predicted_showdown.py"),
        "--source-system",
        args.source_system,
        "--season-start",
        str(season_start),
        "--season-end",
        str(season_end),
        "--lineups-per-slate",
        str(args.lineups_per_slate_showdown),
        "--training-window-slates",
        str(args.training_window_slates),
        "--min-training-slates",
        str(args.min_training_slates),
        "--min-training-rows",
        str(args.min_training_rows),
        _learned_only_flag(args.learned_only),
        "--random-seed",
        str(args.random_seed),
        "--bootstrap-samples",
        str(args.bootstrap_samples),
        "--confidence-level",
        str(args.confidence_level),
        "--output-json",
        str(showdown_json),
    ]
    _append_limit_args(showdown_command, args.limit_slates)
    if args.quiet_progress:
        showdown_command.append("--quiet-progress")

    captain_ab_command = [
        sys.executable,
        str(SCRIPTS_DIR / "run_showdown_captain_ab.py"),
        "--source-system",
        args.source_system,
        "--season-start",
        str(season_start),
        "--season-end",
        str(season_end),
        "--lineups-per-slate",
        str(args.lineups_per_slate_showdown_ab),
        "--training-window-slates",
        str(args.training_window_slates),
        "--min-training-slates",
        str(args.ab_min_training_slates),
        "--min-training-rows",
        str(args.ab_min_training_rows),
        _learned_only_flag(args.learned_only),
        "--random-seed",
        str(args.random_seed),
        "--bootstrap-samples",
        str(args.bootstrap_samples),
        "--confidence-level",
        str(args.confidence_level),
        "--showdown-captain-model-path",
        str(args.showdown_captain_model_path),
        "--showdown-captain-prior-strength",
        str(args.showdown_captain_prior_strength),
        "--output-json",
        str(captain_ab_json),
    ]
    _append_limit_args(captain_ab_command, args.limit_slates)
    if args.quiet_progress:
        captain_ab_command.append("--quiet-progress")

    analysis_command = [
        sys.executable,
        str(SCRIPTS_DIR / "analyze_main_slate_value_drivers.py"),
        "--source-system",
        args.source_system,
        "--season-start",
        str(season_start),
        "--season-end",
        str(season_end),
        "--main-slate-names",
        str(args.main_slate_names),
        "--top-players-per-slate",
        str(args.top_players_per_slate),
        "--high-total-threshold",
        str(args.high_total_threshold),
        "--output-json",
        str(main_analysis_json),
        "--output-md",
        str(main_analysis_md),
    ]
    _append_limit_args(analysis_command, args.analysis_limit_slates)

    try:
        steps.append(_run_step("classic_backtest", classic_command, run_log))
        steps.append(_run_step("showdown_backtest_baseline", showdown_command, run_log))
        steps.append(_run_step("showdown_captain_ab", captain_ab_command, run_log))
        steps.append(_run_step("main_slate_value_analysis", analysis_command, run_log))
    except Exception as exc:
        manifest = {
            "suite_started_at": suite_started,
            "suite_finished_at": datetime.now().isoformat(timespec="seconds"),
            "status": "failed",
            "error": str(exc),
            "run_dir": str(run_dir),
            "steps": steps,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        raise

    _write_summary_markdown(
        output_path=suite_summary_md,
        classic_json=classic_json,
        showdown_json=showdown_json,
        captain_ab_json=captain_ab_json,
        main_analysis_json=main_analysis_json,
    )

    manifest = {
        "suite_started_at": suite_started,
        "suite_finished_at": datetime.now().isoformat(timespec="seconds"),
        "status": "ok",
        "run_dir": str(run_dir),
        "artifacts": {
            "classic_backtest_json": str(classic_json),
            "showdown_backtest_baseline_json": str(showdown_json),
            "showdown_captain_ab_json": str(captain_ab_json),
            "main_slate_value_driver_json": str(main_analysis_json),
            "main_slate_value_driver_md": str(main_analysis_md),
            "suite_summary_md": str(suite_summary_md),
            "run_log": str(run_log),
        },
        "steps": steps,
        "config": {
            "source_system": args.source_system,
            "season_start": season_start,
            "season_end": season_end,
            "lineups_per_slate_classic": args.lineups_per_slate_classic,
            "lineups_per_slate_showdown": args.lineups_per_slate_showdown,
            "lineups_per_slate_showdown_ab": args.lineups_per_slate_showdown_ab,
            "training_window_slates": args.training_window_slates,
            "min_training_slates": args.min_training_slates,
            "min_training_rows": args.min_training_rows,
            "ab_min_training_slates": args.ab_min_training_slates,
            "ab_min_training_rows": args.ab_min_training_rows,
            "learned_only": args.learned_only,
            "random_seed": args.random_seed,
            "bootstrap_samples": args.bootstrap_samples,
            "confidence_level": args.confidence_level,
            "limit_slates": args.limit_slates,
            "analysis_limit_slates": args.analysis_limit_slates,
            "showdown_captain_model_path": args.showdown_captain_model_path,
            "showdown_captain_prior_strength": args.showdown_captain_prior_strength,
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\nBenchmark suite complete: {run_dir}")
    print(f"Manifest: {manifest_path}")
    print(f"Summary: {suite_summary_md}")


if __name__ == "__main__":
    main()
