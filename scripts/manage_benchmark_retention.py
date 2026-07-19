from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK_ROOT = REPO_ROOT / "docs" / "benchmarks"
NIGHTLY_MARKER_NAME = ".nightly-benchmark.json"
NIGHTLY_RUN_NAME_PATTERN = re.compile(
    r"^\d{8}_\d{6}_nightly(?:_[A-Za-z0-9._-]+)?$"
)


@dataclass(frozen=True)
class ManagedBenchmarkRun:
    path: Path
    status: str


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _validate_run_name(run_name: str) -> str:
    if Path(run_name).name != run_name or not NIGHTLY_RUN_NAME_PATTERN.fullmatch(
        run_name
    ):
        raise ValueError(
            "Nightly benchmark run name must match "
            "YYYYMMDD_HHMMSS_nightly[_identifier]."
        )
    return run_name


def register_nightly_run(
    *,
    benchmark_root: Path,
    run_name: str,
    workflow_run_id: str | None = None,
    workflow_run_attempt: str | None = None,
) -> Path:
    validated_name = _validate_run_name(run_name)
    root = benchmark_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    candidate = root / validated_name
    if candidate.exists() or candidate.is_symlink():
        raise FileExistsError(
            f"Nightly benchmark run directory already exists: {candidate}"
        )
    run_dir = candidate.resolve()
    if run_dir.parent != root:
        raise ValueError("Nightly benchmark run directory escapes benchmark root.")
    run_dir.mkdir(parents=False)
    marker = run_dir / NIGHTLY_MARKER_NAME
    marker.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "managed_by": "nightly-benchmark-workflow",
                "registered_at": datetime.now(UTC).isoformat(),
                "workflow_run_id": workflow_run_id,
                "workflow_run_attempt": workflow_run_attempt,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return run_dir


def discover_managed_runs(benchmark_root: Path) -> list[ManagedBenchmarkRun]:
    root = benchmark_root.expanduser().resolve()
    if not root.exists():
        return []
    runs: list[ManagedBenchmarkRun] = []
    for candidate in root.iterdir():
        if (
            candidate.is_symlink()
            or not candidate.is_dir()
            or not NIGHTLY_RUN_NAME_PATTERN.fullmatch(candidate.name)
        ):
            continue
        marker = candidate / NIGHTLY_MARKER_NAME
        if marker.is_symlink() or not marker.is_file():
            continue
        marker_payload = _load_json(marker)
        if (
            marker_payload.get("schema_version") != 1
            or marker_payload.get("managed_by") != "nightly-benchmark-workflow"
        ):
            continue
        manifest = _load_json(candidate / "suite_manifest.json")
        status = str(manifest.get("status", "unknown"))
        runs.append(
            ManagedBenchmarkRun(
                path=candidate.resolve(),
                status=status,
            )
        )
    return sorted(runs, key=lambda run: run.path.name, reverse=True)


def benchmark_retention_plan(
    *,
    benchmark_root: Path,
    keep_successful: int,
    keep_failed: int,
    protected_run_names: set[str] | None = None,
) -> list[ManagedBenchmarkRun]:
    if keep_successful < 0 or keep_failed < 0:
        raise ValueError("Benchmark retention counts must be non-negative.")
    protected = protected_run_names or set()
    runs = discover_managed_runs(benchmark_root)
    successful = [run for run in runs if run.status == "ok"]
    unsuccessful = [run for run in runs if run.status != "ok"]
    candidates = successful[keep_successful:] + unsuccessful[keep_failed:]
    return [
        run
        for run in sorted(candidates, key=lambda item: item.path.name)
        if run.path.name not in protected
    ]


def apply_benchmark_retention(
    *,
    benchmark_root: Path,
    runs_to_delete: list[ManagedBenchmarkRun],
) -> list[Path]:
    root = benchmark_root.expanduser().resolve()
    deleted: list[Path] = []
    for run in runs_to_delete:
        path = run.path.resolve()
        marker = path / NIGHTLY_MARKER_NAME
        if (
            path.parent != root
            or path.is_symlink()
            or not NIGHTLY_RUN_NAME_PATTERN.fullmatch(path.name)
            or marker.is_symlink()
            or not marker.is_file()
        ):
            raise ValueError(f"Refusing to prune unsafe benchmark path: {path}")
        marker_payload = _load_json(marker)
        if (
            marker_payload.get("schema_version") != 1
            or marker_payload.get("managed_by") != "nightly-benchmark-workflow"
        ):
            raise ValueError(f"Refusing to prune unmanaged benchmark path: {path}")
        shutil.rmtree(path)
        deleted.append(path)
    return deleted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Register and safely retain workflow-managed benchmark runs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    register = subparsers.add_parser(
        "register",
        help="Create a workflow-managed nightly run directory and marker.",
    )
    register.add_argument(
        "--benchmarks-root",
        default=str(DEFAULT_BENCHMARK_ROOT),
    )
    register.add_argument("--run-name", required=True)
    register.add_argument("--workflow-run-id", default=None)
    register.add_argument("--workflow-run-attempt", default=None)

    prune = subparsers.add_parser(
        "prune",
        help="Plan or apply retention to workflow-managed nightly runs only.",
    )
    prune.add_argument(
        "--benchmarks-root",
        default=str(DEFAULT_BENCHMARK_ROOT),
    )
    prune.add_argument("--keep-successful", type=int, default=14)
    prune.add_argument("--keep-failed", type=int, default=7)
    prune.add_argument("--protect-run", action="append", default=[])
    prune.add_argument(
        "--apply",
        action="store_true",
        help="Delete planned directories; without this flag the command is a dry run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    benchmark_root = Path(args.benchmarks_root)
    if args.command == "register":
        run_dir = register_nightly_run(
            benchmark_root=benchmark_root,
            run_name=args.run_name,
            workflow_run_id=args.workflow_run_id,
            workflow_run_attempt=args.workflow_run_attempt,
        )
        print(json.dumps({"registered_run_directory": str(run_dir)}, indent=2))
        return

    protected = {_validate_run_name(name) for name in args.protect_run}
    plan = benchmark_retention_plan(
        benchmark_root=benchmark_root,
        keep_successful=args.keep_successful,
        keep_failed=args.keep_failed,
        protected_run_names=protected,
    )
    deleted = (
        apply_benchmark_retention(
            benchmark_root=benchmark_root,
            runs_to_delete=plan,
        )
        if args.apply
        else []
    )
    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry_run",
                "planned": [str(run.path) for run in plan],
                "deleted": [str(path) for path in deleted],
                "keep_successful": args.keep_successful,
                "keep_failed": args.keep_failed,
                "protected_run_names": sorted(protected),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
