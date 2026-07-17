from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.app.config import Settings
from backend.app.schemas import BenchmarkSuiteRunRequest
from backend.app.services import benchmarks


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _benchmark_run_dir(root: Path, name: str) -> Path:
    run_dir = root / name
    run_dir.mkdir(parents=True, exist_ok=True)
    _write(
        run_dir / "suite_manifest.json",
        """
        {
          "status": "ok",
          "suite_started_at": "2026-06-07T10:00:00",
          "suite_finished_at": "2026-06-07T10:01:00",
          "config": {
            "source_system": "draftkings"
          },
          "artifacts": {
            "suite_summary_md": "%s",
            "run_log": "%s"
          }
        }
        """
        % (run_dir / "summary.md", run_dir / "run.log"),
    )
    _write(
        run_dir / "classic_backtest.json",
        """
        {
          "summary": {
            "mean_gap_points": 101.5,
            "median_gap_points": 99.0,
            "slates_completed": 12
          }
        }
        """,
    )
    _write(
        run_dir / "showdown_backtest_baseline.json",
        """
        {
          "summary": {
            "mean_gap_points": 45.25,
            "median_gap_points": 44.0,
            "slates_completed": 9
          }
        }
        """,
    )
    _write(
        run_dir / "showdown_captain_ab.json",
        """
        {
          "summary": {
            "captain_informed_win_rate": 0.625,
            "mean_gap_lift_points": 4.2,
            "paired_slates": 8
          }
        }
        """,
    )
    _write(run_dir / "summary.md", "# Summary\n")
    _write(run_dir / "run.log", "benchmark log\n")
    return run_dir


def _empty_benchmark_run_dir(root: Path, name: str) -> Path:
    run_dir = root / name
    run_dir.mkdir(parents=True, exist_ok=True)
    _write(run_dir / "suite_manifest.json", '{"status": "ok"}')
    for file_name in (
        "classic_backtest.json",
        "showdown_backtest_baseline.json",
        "showdown_captain_ab.json",
    ):
        _write(run_dir / file_name, '{"summary": {}}')
    return run_dir


def test_build_model_defaults_response() -> None:
    settings = Settings(
        showdown_captain_model_path="docs/showdown.json",
        showdown_captain_prior_strength=0.4,
        classic_value_driver_model_path="docs/classic.json",
        classic_value_driver_prior_strength=0.3,
        matchup_outcome_model_path="docs/matchup.json",
        matchup_outcome_prior_strength=0.2,
        matchup_prior_gate_model_path="docs/gate.json",
    )
    payload = benchmarks.build_model_defaults_response(settings)
    assert payload["showdown_captain_model_path"] == "docs/showdown.json"
    assert payload["showdown_captain_prior_strength"] == 0.4
    assert payload["matchup_prior_gate_model_path"] == "docs/gate.json"


def test_list_benchmark_runs_reads_manifest_and_metrics(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "benchmarks"
    older = _benchmark_run_dir(root, "20260302_120000")
    newer = _benchmark_run_dir(root, "20260303_120000")
    monkeypatch.setattr(benchmarks, "BENCHMARK_ROOT", root)

    rows = benchmarks.list_benchmark_runs(limit=10)

    assert [row["run_directory"] for row in rows] == [str(newer), str(older)]
    assert rows[0]["metrics"]["classic_mean_gap_points"] == 101.5
    assert rows[0]["metrics"]["showdown_mean_gap_points"] == 45.25
    assert rows[0]["metrics"]["captain_informed_win_rate"] == 0.625
    manifest_artifact = next(
        artifact for artifact in rows[0]["artifacts"] if artifact["name"] == "suite_manifest.json"
    )
    assert manifest_artifact["exists"] is True
    assert manifest_artifact["download_url"] == (
        "/api/benchmarks/runs/20260303_120000/artifacts/suite_manifest.json"
    )
    assert benchmarks.resolve_benchmark_artifact("20260303_120000", "summary.md") == (
        newer / "summary.md"
    )
    assert benchmarks.resolve_benchmark_artifact("../20260303_120000", "summary.md") is None
    assert benchmarks.resolve_benchmark_artifact("20260303_120000", "../summary.md") is None
    outside = tmp_path / "outside"
    _write(outside / "summary.md", "# Outside\n")
    (root / "linked-run").symlink_to(outside, target_is_directory=True)
    assert benchmarks.resolve_benchmark_artifact("linked-run", "summary.md") is None


def test_run_benchmark_suite_returns_latest_run(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "benchmarks"
    baseline_dir = _benchmark_run_dir(root, "20260303_120000")
    _empty_benchmark_run_dir(root, "20260304_120000")
    monkeypatch.setattr(benchmarks, "BENCHMARK_ROOT", root)

    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        calls.append(command)
        if "--output-dir" in command:
            output_dir = Path(command[command.index("--output-dir") + 1])
            _benchmark_run_dir(output_dir.parent, output_dir.name)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(benchmarks.subprocess, "run", fake_run)

    payload = benchmarks.run_benchmark_suite(
        BenchmarkSuiteRunRequest(
            source_system="draftkings",
            season_start=2024,
            season_end=2025,
            limit_slates=2,
            analysis_limit_slates=2,
            quiet_progress=True,
        )
    )

    assert payload["status"] == "ok"
    assert payload["run"] is not None
    run_dir = Path(payload["run"]["run_directory"])
    assert run_dir.parent == root
    assert run_dir != baseline_dir
    assert any("--limit-slates" in command for command in calls)
    assert len(calls) == 2
    assert calls[1][calls[1].index("--baseline-run-dir") + 1] == str(baseline_dir)
    assert calls[1][calls[1].index("--current-run-dir") + 1] == str(run_dir)


def test_run_benchmark_suite_failure_returns_attempted_run(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "benchmarks"
    previous_run = _benchmark_run_dir(root, "20260303_120000")
    monkeypatch.setattr(benchmarks, "BENCHMARK_ROOT", root)

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        output_dir = Path(command[command.index("--output-dir") + 1])
        _write(
            output_dir / "suite_manifest.json",
            '{"status": "failed", "error": "classic backtest failed"}',
        )
        _write(output_dir / "run.log", "classic backtest failed\n")
        return SimpleNamespace(returncode=1, stdout="", stderr="classic backtest failed")

    monkeypatch.setattr(benchmarks.subprocess, "run", fake_run)

    payload = benchmarks.run_benchmark_suite(BenchmarkSuiteRunRequest())

    assert payload["status"] == "failed"
    assert payload["error_message"] == "classic backtest failed"
    assert payload["run"] is not None
    assert payload["run"]["status"] == "failed"
    assert payload["run"]["run_directory"] != str(previous_run)
    run_log = next(artifact for artifact in payload["run"]["artifacts"] if artifact["name"] == "run.log")
    assert run_log["exists"] is True
