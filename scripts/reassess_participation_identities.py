from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.services.participation_identity import (
    PARTICIPATION_IDENTITY_CONTRACT_ID,
    apply_participation_identity_repairs,
    assess_participation_identities,
)
from backend.app.services.source_capture import SourceCaptureService


DEFAULT_REGISTRY_LICENSE = (
    "nflverse player registry accessed through nflreadpy; downstream use remains "
    "subject to the applicable upstream dataset terms."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reassess open weekly-roster and snap-count identities. Dry-run is the "
            "default; --apply persists only deterministic native-ID or exact semantic matches."
        )
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--snapshot-root", default="")
    parser.add_argument("--registry-license", default=DEFAULT_REGISTRY_LICENSE)
    parser.add_argument("--output-json", default="")
    return parser.parse_args()


def _load_registry():
    try:
        import nflreadpy
    except ModuleNotFoundError as exc:  # pragma: no cover - environment-specific
        raise RuntimeError("nflreadpy is required for participation identity reassessment") from exc
    frame = nflreadpy.load_players()
    if hasattr(frame, "to_pandas"):
        frame = frame.to_pandas()
    return frame, str(getattr(nflreadpy, "__version__", "unknown"))


def main() -> None:
    args = parse_args()
    registry_frame, nflreadpy_version = _load_registry()
    with SessionLocal() as session:
        assessment = assess_participation_identities(session, registry_frame)
        report = assessment.report()
        report["mode"] = "apply" if args.apply else "dry_run"
        report["nflreadpy_version"] = nflreadpy_version
        report["applied"] = False

        if args.apply:
            if assessment.conflicts:
                report["status"] = "blocked_conflict"
            elif not assessment.decisions:
                report["status"] = "no_changes"
            else:
                snapshot = SourceCaptureService(
                    session,
                    snapshot_root=args.snapshot_root or None,
                ).capture_dataframe(
                    assessment.relevant_registry_rows,
                    artifact_name="nflreadpy_player_registry_participation_crosswalk.csv",
                    source_system="nflreadpy",
                    dataset="player_registry_crosswalk",
                    season=datetime.now(UTC).year,
                    week=None,
                    slate=None,
                    source_license=args.registry_license,
                    source_uri="nflreadpy://players",
                    metadata={
                        "capture_mode": "participation_identity_reassessment",
                        "contract_id": PARTICIPATION_IDENTITY_CONTRACT_ID,
                        "nflreadpy_version": nflreadpy_version,
                        "registry_rows": assessment.registry_rows,
                        "relevant_registry_rows": len(
                            assessment.relevant_registry_rows
                        ),
                        "registry_evidence_sha256": assessment.registry_evidence_sha256,
                    },
                )
                report["registry_snapshot"] = {
                    "snapshot_id": snapshot.snapshot.snapshot_id,
                    "created": snapshot.created,
                    "artifact_path": snapshot.snapshot.artifact_path,
                    "manifest_path": snapshot.snapshot.manifest_path,
                    "content_sha256": snapshot.snapshot.content_sha256,
                }
                report["apply_result"] = apply_participation_identity_repairs(
                    session,
                    assessment,
                    registry_snapshot_id=snapshot.snapshot.snapshot_id,
                )
                report["applied"] = True
                report["status"] = "completed"
        else:
            if assessment.conflicts:
                report["status"] = "blocked_conflict"
            elif assessment.decisions:
                report["status"] = "ready"
            else:
                report["status"] = "no_changes"

    rendered = json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
    print(rendered, end="")
    if args.output_json:
        output_path = Path(args.output_json).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    if assessment.conflicts:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
