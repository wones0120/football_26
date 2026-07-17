from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..config import Settings


REPO_ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_ROOT = REPO_ROOT / "docs" / "benchmarks"
RUN_BENCHMARK_SUITE_SCRIPT = REPO_ROOT / "scripts" / "run_benchmark_suite.py"
COMPARE_BENCHMARK_RUNS_SCRIPT = REPO_ROOT / "scripts" / "compare_benchmark_runs.py"

ARTIFACT_LABELS = {
    "classic_backtest_json": "classic_backtest.json",
    "showdown_backtest_baseline_json": "showdown_backtest_baseline.json",
    "showdown_captain_ab_json": "showdown_captain_ab.json",
    "main_slate_value_driver_json": "main_slate_value_driver_analysis.json",
    "main_slate_value_driver_md": "main_slate_value_driver_analysis.md",
    "suite_summary_md": "summary.md",
    "suite_manifest": "suite_manifest.json",
    "run_log": "run.log",
    "delta_report_md": "delta_vs_previous.md",
    "delta_report_json": "delta_vs_previous.json",
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _artifact_response(name: str, path: Path, run_dir: Path) -> dict[str, Any]:
    exists = path.is_file()
    download_url = (
        f"/api/benchmarks/runs/{quote(run_dir.name, safe='')}/artifacts/{quote(name, safe='')}"
        if resolve_benchmark_artifact(run_dir.name, name) is not None
        else None
    )
    return {
        "name": name,
        "path": str(path),
        "exists": exists,
        "download_url": download_url,
    }


def build_model_defaults_response(settings: Settings) -> dict[str, Any]:
    return {
        "showdown_captain_model_path": settings.showdown_captain_model_path,
        "showdown_captain_prior_strength": settings.showdown_captain_prior_strength,
        "classic_value_driver_model_path": settings.classic_value_driver_model_path,
        "classic_value_driver_prior_strength": settings.classic_value_driver_prior_strength,
        "matchup_outcome_model_path": settings.matchup_outcome_model_path,
        "matchup_outcome_prior_strength": settings.matchup_outcome_prior_strength,
        "matchup_prior_gate_model_path": settings.matchup_prior_gate_model_path,
    }


def _extract_metric_summary(run_dir: Path) -> dict[str, Any]:
    classic = _load_json(run_dir / "classic_backtest.json").get("summary", {})
    showdown = _load_json(run_dir / "showdown_backtest_baseline.json").get("summary", {})
    captain_ab = _load_json(run_dir / "showdown_captain_ab.json").get("summary", {})
    return {
        "classic_mean_gap_points": classic.get("mean_gap_points"),
        "classic_median_gap_points": classic.get("median_gap_points"),
        "classic_slates_completed": classic.get("slates_completed"),
        "showdown_mean_gap_points": showdown.get("mean_gap_points"),
        "showdown_median_gap_points": showdown.get("median_gap_points"),
        "showdown_slates_completed": showdown.get("slates_completed"),
        "captain_informed_win_rate": captain_ab.get("captain_informed_win_rate"),
        "captain_mean_gap_lift_points": captain_ab.get("mean_gap_lift_points"),
        "captain_paired_slates": captain_ab.get("paired_slates"),
    }


def _normalize_artifacts(run_dir: Path, manifest_artifacts: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    manifest_artifacts = manifest_artifacts or {}
    artifacts: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for key, file_name in ARTIFACT_LABELS.items():
        raw_path = manifest_artifacts.get(key)
        manifest_path = Path(raw_path) if isinstance(raw_path, str) and raw_path.strip() else None
        path = manifest_path if manifest_path is not None and manifest_path.exists() else run_dir / file_name
        if file_name in seen_names:
            continue
        artifacts.append(_artifact_response(file_name, path, run_dir))
        seen_names.add(file_name)
    return artifacts


def build_benchmark_run_response(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "suite_manifest.json"
    manifest = _load_json(manifest_path)
    artifacts_payload = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    artifacts = _normalize_artifacts(run_dir, artifacts_payload)
    return {
        "run_directory": str(run_dir),
        "status": manifest.get("status", "unknown"),
        "suite_started_at": manifest.get("suite_started_at"),
        "suite_finished_at": manifest.get("suite_finished_at"),
        "config": manifest.get("config") if isinstance(manifest.get("config"), dict) else {},
        "artifacts": artifacts,
        "metrics": _extract_metric_summary(run_dir),
    }


def list_benchmark_runs(limit: int = 10) -> list[dict[str, Any]]:
    if limit <= 0 or not BENCHMARK_ROOT.exists():
        return []
    candidates = sorted(
        [path for path in BENCHMARK_ROOT.iterdir() if path.is_dir() and (path / "suite_manifest.json").exists()],
        key=lambda path: path.name,
        reverse=True,
    )
    return [build_benchmark_run_response(path) for path in candidates[:limit]]


def resolve_benchmark_artifact(run_name: str, artifact_name: str) -> Path | None:
    if Path(run_name).name != run_name or artifact_name not in ARTIFACT_LABELS.values():
        return None
    root = BENCHMARK_ROOT.resolve()
    run_dir = (root / run_name).resolve()
    try:
        run_dir.relative_to(root)
    except ValueError:
        return None
    path = (run_dir / artifact_name).resolve()
    if path.parent != run_dir:
        return None
    return path if path.is_file() else None


def _allocate_run_directory() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for suffix in range(1000):
        name = timestamp if suffix == 0 else f"{timestamp}_{suffix:02d}"
        candidate = BENCHMARK_ROOT / name
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise RuntimeError(f"Unable to allocate benchmark run directory under {BENCHMARK_ROOT}")


def _latest_successful_run(*, exclude: Path) -> Path | None:
    candidates = sorted(
        [
            path
            for path in BENCHMARK_ROOT.iterdir()
            if path.is_dir()
            and path != exclude
            and _load_json(path / "suite_manifest.json").get("status") == "ok"
            and all(
                isinstance(_extract_metric_summary(path).get(metric), (int, float))
                for metric in (
                    "classic_mean_gap_points",
                    "showdown_mean_gap_points",
                    "captain_informed_win_rate",
                )
            )
        ],
        key=lambda path: path.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def run_benchmark_suite(request: Any) -> dict[str, Any]:
    BENCHMARK_ROOT.mkdir(parents=True, exist_ok=True)
    run_dir = _allocate_run_directory()

    command = [
        sys.executable,
        str(RUN_BENCHMARK_SUITE_SCRIPT),
        "--source-system",
        str(request.source_system),
        "--season-start",
        str(request.season_start),
        "--season-end",
        str(request.season_end),
        "--lineups-per-slate-classic",
        str(request.lineups_per_slate_classic),
        "--lineups-per-slate-showdown",
        str(request.lineups_per_slate_showdown),
        "--lineups-per-slate-showdown-ab",
        str(request.lineups_per_slate_showdown_ab),
        "--training-window-slates",
        str(request.training_window_slates),
        "--min-training-slates",
        str(request.min_training_slates),
        "--min-training-rows",
        str(request.min_training_rows),
        "--ab-min-training-slates",
        str(request.ab_min_training_slates),
        "--ab-min-training-rows",
        str(request.ab_min_training_rows),
        "--random-seed",
        str(request.random_seed),
        "--showdown-captain-model-path",
        str(request.showdown_captain_model_path),
        "--showdown-captain-prior-strength",
        str(request.showdown_captain_prior_strength),
        "--output-dir",
        str(run_dir),
    ]
    command.append("--learned-only" if request.learned_only else "--allow-heuristics")
    if request.limit_slates > 0:
        command.extend(["--limit-slates", str(request.limit_slates)])
    if request.analysis_limit_slates > 0:
        command.extend(["--analysis-limit-slates", str(request.analysis_limit_slates)])
    if request.quiet_progress:
        command.append("--quiet-progress")

    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    run = build_benchmark_run_response(run_dir)

    if completed.returncode == 0:
        baseline_run = _latest_successful_run(exclude=run_dir)
        if baseline_run is not None:
            compare = subprocess.run(
                [
                    sys.executable,
                    str(COMPARE_BENCHMARK_RUNS_SCRIPT),
                    "--baseline-run-dir",
                    str(baseline_run),
                    "--current-run-dir",
                    str(run_dir),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            if compare.returncode == 0:
                run = build_benchmark_run_response(run_dir)
        return {
            "status": "ok",
            "error_message": None,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "run": run,
        }

    error_message = completed.stderr.strip() or completed.stdout.strip() or "benchmark suite failed"
    return {
        "status": "failed",
        "error_message": error_message,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "run": run,
    }
