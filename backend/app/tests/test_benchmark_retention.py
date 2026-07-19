from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.compare_benchmark_runs import _resolve_runs
from scripts.manage_benchmark_retention import (
    NIGHTLY_MARKER_NAME,
    apply_benchmark_retention,
    benchmark_retention_plan,
    discover_managed_runs,
    register_nightly_run,
)


def _write_manifest(run_dir: Path, status: str) -> None:
    (run_dir / "suite_manifest.json").write_text(
        json.dumps({"status": status}),
        encoding="utf-8",
    )


def _managed_run(root: Path, name: str, status: str) -> Path:
    run_dir = register_nightly_run(
        benchmark_root=root,
        run_name=name,
        workflow_run_id=name,
        workflow_run_attempt="1",
    )
    _write_manifest(run_dir, status)
    return run_dir


def test_retention_only_prunes_marked_nightly_runs(tmp_path: Path) -> None:
    root = tmp_path / "benchmarks"
    success_names = [
        "20260710_090000_nightly_10",
        "20260711_090000_nightly_11",
        "20260712_090000_nightly_12",
        "20260713_090000_nightly_13",
    ]
    failed_names = [
        "20260714_090000_nightly_14",
        "20260715_090000_nightly_15",
        "20260716_090000_nightly_16",
    ]
    for name in success_names:
        _managed_run(root, name, "ok")
    for name in failed_names:
        _managed_run(root, name, "failed")

    manual = root / "20260701_090000"
    manual.mkdir()
    _write_manifest(manual, "ok")
    unmarked_nightly = root / "20260702_090000_nightly_manual"
    unmarked_nightly.mkdir()
    _write_manifest(unmarked_nightly, "ok")

    plan = benchmark_retention_plan(
        benchmark_root=root,
        keep_successful=2,
        keep_failed=1,
    )

    assert [run.path.name for run in plan] == [
        "20260710_090000_nightly_10",
        "20260711_090000_nightly_11",
        "20260714_090000_nightly_14",
        "20260715_090000_nightly_15",
    ]
    deleted = apply_benchmark_retention(
        benchmark_root=root,
        runs_to_delete=plan,
    )
    assert [path.name for path in deleted] == [
        "20260710_090000_nightly_10",
        "20260711_090000_nightly_11",
        "20260714_090000_nightly_14",
        "20260715_090000_nightly_15",
    ]
    assert manual.is_dir()
    assert unmarked_nightly.is_dir()
    assert not (root / success_names[0]).exists()
    assert (root / success_names[-1]).is_dir()
    assert (root / failed_names[-1]).is_dir()


def test_retention_preserves_protected_run_and_ignores_symlink(
    tmp_path: Path,
) -> None:
    root = tmp_path / "benchmarks"
    protected = _managed_run(
        root,
        "20260710_090000_nightly_protected",
        "failed",
    )
    _managed_run(root, "20260711_090000_nightly_newer", "failed")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / NIGHTLY_MARKER_NAME).write_text(
        '{"schema_version":1,"managed_by":"nightly-benchmark-workflow"}',
        encoding="utf-8",
    )
    (root / "20260709_090000_nightly_link").symlink_to(
        outside,
        target_is_directory=True,
    )

    discovered = discover_managed_runs(root)
    plan = benchmark_retention_plan(
        benchmark_root=root,
        keep_successful=0,
        keep_failed=1,
        protected_run_names={protected.name},
    )

    assert {run.path.name for run in discovered} == {
        protected.name,
        "20260711_090000_nightly_newer",
    }
    assert plan == []
    assert outside.is_dir()


def test_register_rejects_unsafe_or_non_nightly_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must match"):
        register_nightly_run(
            benchmark_root=tmp_path,
            run_name="../escape",
        )
    with pytest.raises(ValueError, match="must match"):
        register_nightly_run(
            benchmark_root=tmp_path,
            run_name="manual-run",
        )
    run_name = "20260710_090000_nightly_collision"
    register_nightly_run(
        benchmark_root=tmp_path,
        run_name=run_name,
    )
    with pytest.raises(FileExistsError, match="already exists"):
        register_nightly_run(
            benchmark_root=tmp_path,
            run_name=run_name,
        )


def test_compare_current_run_uses_latest_earlier_success(tmp_path: Path) -> None:
    root = tmp_path / "benchmarks"
    root.mkdir()
    older = root / "20260710_090000"
    failed = root / "20260711_090000"
    newest = root / "20260712_090000_nightly_12"
    for run_dir, status in (
        (older, "ok"),
        (failed, "failed"),
        (newest, "ok"),
    ):
        run_dir.mkdir()
        _write_manifest(run_dir, status)

    baseline, current = _resolve_runs(
        root,
        baseline_arg="",
        current_arg=str(newest),
    )

    assert baseline == older
    assert current == newest.resolve()
