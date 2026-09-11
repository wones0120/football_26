from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.schemas import NflReadPySeasonRequest
from backend.app.services.source_capture import (
    NFLREADPY_DATASETS,
    PostLockSnapshotError,
    SourceCaptureService,
    capture_nflreadpy_datasets,
)


DEFAULT_DK_LICENSE = (
    "User-authorized DraftKings download; use remains subject to the user's "
    "DraftKings account and platform terms."
)
DEFAULT_NFLREADPY_LICENSE = (
    "nflverse data accessed through nflreadpy; downstream use remains subject "
    "to the applicable upstream dataset terms."
)


def _aware_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO-8601 timestamp: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone offset")
    return parsed.astimezone(UTC)


def _discovered_draftkings_files(directory: Path, *, season: int, week: int) -> list[Path]:
    pattern = re.compile(
        rf"^DKSalaries_{season}_{week:02d}(?:[^.]*)\.csv$",
        re.IGNORECASE,
    )
    if not directory.is_dir():
        return []
    return sorted(
        (
            path.resolve()
            for path in directory.iterdir()
            if path.is_file() and pattern.match(path.name)
        ),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    )


def _snapshot_payload(result: Any) -> dict[str, Any]:
    snapshot = result.snapshot
    return {
        "snapshot_id": snapshot.snapshot_id,
        "source_system": snapshot.source_system,
        "dataset": snapshot.dataset,
        "created": result.created,
        "pre_lock": result.pre_lock,
        "observed_at": snapshot.observed_at.isoformat(),
        "slate_lock_at": (
            snapshot.slate_lock_at.isoformat() if snapshot.slate_lock_at else None
        ),
        "content_sha256": snapshot.content_sha256,
        "row_count": snapshot.row_count,
        "artifact_path": snapshot.artifact_path,
        "manifest_path": snapshot.manifest_path,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Capture immutable, content-addressed pre-lock evidence for a 2026 DFS slate. "
            "DraftKings salary captures are ingested from the preserved copy."
        )
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--slate", default="sunday_main")
    parser.add_argument("--slate-lock-at", type=_aware_datetime, required=True)
    parser.add_argument(
        "--draftkings-path",
        action="append",
        default=[],
        help="Explicit DraftKings salary CSV; repeat for more than one file.",
    )
    parser.add_argument(
        "--draftkings-directory",
        default="",
        help=(
            "Discover DKSalaries_SEASON_WEEK*.csv files. Generic DKSalaries.csv files "
            "must be passed explicitly to prevent accidental week mislabeling."
        ),
    )
    parser.add_argument(
        "--nflreadpy-datasets",
        nargs="*",
        choices=NFLREADPY_DATASETS,
        default=[],
        help="Capture one or more nflreadpy datasets for the same week.",
    )
    parser.add_argument("--snapshot-root", default="")
    parser.add_argument("--draftkings-license", default=DEFAULT_DK_LICENSE)
    parser.add_argument("--nflreadpy-license", default=DEFAULT_NFLREADPY_LICENSE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.season < 2000 or not 1 <= args.week <= 25:
        raise SystemExit("season must be >= 2000 and week must be between 1 and 25")

    draftkings_paths = {
        Path(path).expanduser().resolve(): None for path in args.draftkings_path
    }
    if args.draftkings_directory:
        draftkings_paths.update(
            dict.fromkeys(
                _discovered_draftkings_files(
                    Path(args.draftkings_directory).expanduser().resolve(),
                    season=args.season,
                    week=args.week,
                )
            )
        )
    ordered_draftkings_paths = sorted(
        draftkings_paths,
        key=lambda path: (
            path.stat().st_mtime_ns if path.is_file() else -1,
            path.name,
        ),
    )
    if not ordered_draftkings_paths and not args.nflreadpy_datasets:
        raise SystemExit(
            "No sources selected. Pass --draftkings-path, --draftkings-directory, "
            "or --nflreadpy-datasets."
        )

    output: dict[str, Any] = {
        "contract_id": "prospective_source_snapshot_v1",
        "season": args.season,
        "week": args.week,
        "slate": args.slate,
        "slate_lock_at": args.slate_lock_at.isoformat(),
        "draftkings": [],
        "nflreadpy": [],
        "errors": [],
    }
    with SessionLocal() as session:
        service = SourceCaptureService(
            session,
            snapshot_root=args.snapshot_root or None,
        )
        for path in ordered_draftkings_paths:
            try:
                result = service.capture_and_ingest_draftkings_salary(
                    path,
                    season=args.season,
                    week=args.week,
                    slate=args.slate,
                    slate_lock_at=args.slate_lock_at,
                    source_license=args.draftkings_license,
                    source_uri="https://www.draftkings.com/",
                )
                payload = _snapshot_payload(result.capture)
                payload["ingest"] = result.ingest.model_dump(mode="json")
                output["draftkings"].append(payload)
            except PostLockSnapshotError as exc:
                payload = _snapshot_payload(exc.capture)
                payload["ingest"] = {
                    "status": "excluded_post_lock",
                    "error_message": str(exc),
                }
                output["draftkings"].append(payload)
                output["errors"].append(str(exc))
            except Exception as exc:  # noqa: BLE001
                output["errors"].append(f"{path}: {exc}")

        for dataset in dict.fromkeys(args.nflreadpy_datasets):
            try:
                if dataset == "weekly_rosters":
                    result = service.capture_and_ingest_nflreadpy_weekly_rosters(
                        NflReadPySeasonRequest(
                            season=args.season,
                            weeks=[args.week],
                        ),
                        source_license=args.nflreadpy_license,
                        slate=args.slate,
                        slate_lock_at=args.slate_lock_at,
                    )
                    payload = _snapshot_payload(result.capture)
                    payload["ingest"] = result.ingest.model_dump(mode="json")
                    output["nflreadpy"].append(payload)
                    if result.ingest.status == "failed":
                        output["errors"].append(
                            result.ingest.error_message
                            or "nflreadpy weekly-roster ingest failed"
                        )
                else:
                    captures = capture_nflreadpy_datasets(
                        service,
                        [dataset],
                        season=args.season,
                        week=args.week,
                        slate=args.slate,
                        slate_lock_at=args.slate_lock_at,
                        source_license=args.nflreadpy_license,
                    )
                    output["nflreadpy"].extend(
                        _snapshot_payload(result) for result in captures
                    )
            except Exception as exc:  # noqa: BLE001
                output["errors"].append(f"nflreadpy {dataset}: {exc}")

    output["status"] = "failed" if output["errors"] else "completed"
    print(json.dumps(output, indent=2, default=str))
    if output["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
