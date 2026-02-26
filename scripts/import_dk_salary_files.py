from __future__ import annotations

import re
import sys
from pathlib import Path

from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.schemas import SalaryIngestRequest
from backend.app.services.ingest import IngestService


FILE_RE = re.compile(
    r"^DKSalaries_(?P<season>\d{4})_(?P<week>\d{1,2})(?P<suffix>[^.]*)\.csv$",
    re.IGNORECASE,
)
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _parse_slate(suffix: str) -> str:
    cleaned = suffix.strip().lower()
    if cleaned.startswith("_") or cleaned.startswith("-"):
        cleaned = cleaned[1:]
    if not cleaned:
        return "main"
    slug = NON_ALNUM_RE.sub("_", cleaned).strip("_")
    return slug or "main"


def _discover_files(download_dir: Path) -> list[tuple[Path, int, int, str]]:
    rows: list[tuple[Path, int, int, str]] = []
    for path in sorted(download_dir.glob("DKSalaries_*.csv")):
        match = FILE_RE.match(path.name)
        if not match:
            continue
        season = int(match.group("season"))
        week = int(match.group("week"))
        if week < 1 or week > 25:
            continue
        slate = _parse_slate(match.group("suffix") or "")
        rows.append((path.resolve(), season, week, slate))
    return rows


def main() -> None:
    download_dir = Path("/Users/wones/Downloads")
    files = _discover_files(download_dir)

    if not files:
        print("No DKSalaries files found with parseable season/week pattern.")
        return

    success = 0
    failed = 0
    session: Session = SessionLocal()
    service = IngestService(session)
    try:
        for path, season, week, slate in files:
            request = SalaryIngestRequest(
                source_system="draftkings",
                season=season,
                week=week,
                slate=slate,
                path=str(path),
            )
            result = service.ingest_salaries(request)
            if result.status == "completed":
                success += 1
            else:
                failed += 1
            print(
                f"{result.status.upper():9s} | {path.name} | "
                f"season={season} week={week} slate={slate} "
                f"curated={result.rows_curated} unresolved={result.rows_unresolved} "
                f"{'error=' + result.error_message if result.error_message else ''}"
            )
    finally:
        session.close()

    print("-" * 120)
    print(f"Files attempted: {len(files)} | completed: {success} | failed: {failed}")


if __name__ == "__main__":
    main()
