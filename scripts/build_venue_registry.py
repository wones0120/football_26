from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.services.venue_registry import (
    DEFAULT_VENUE_REGISTRY_PATH,
    apply_venue_registry,
    assess_venue_registry,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and map versioned venues to nflverse schedules. Dry-run is the "
            "default; --apply persists registry versions, reviewed game overrides, and "
            "resolved or quarantined game mappings."
        )
    )
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument("--seed", default=str(DEFAULT_VENUE_REGISTRY_PATH))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output-json", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with SessionLocal() as session:
        assessment = assess_venue_registry(
            session,
            season_start=args.season_start,
            season_end=args.season_end,
            seed_path=args.seed,
        )
        report = assessment.report()
        report["mode"] = "apply" if args.apply else "dry_run"
        report["applied"] = False
        if args.apply:
            report["apply_result"] = apply_venue_registry(session, assessment)
            session.commit()
            report["applied"] = True
        report["status"] = (
            "completed" if report["acceptance_ready"] else "completed_with_quarantine"
        )

    rendered = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    print(rendered, end="")
    if args.output_json:
        output_path = Path(args.output_json).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
