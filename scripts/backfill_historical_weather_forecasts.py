from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import get_settings
from backend.app.db import SessionLocal
from backend.app.services.weather_forecast_backfill import (
    WEATHER_FORECAST_FIXED_LEAD_HOURS,
    WEATHER_FORECAST_MODEL,
    WEATHER_FORECAST_PROVIDER,
    HistoricalForecastBackfillService,
    OpenMeteoPreviousRunsClient,
    assess_historical_forecast_backfill,
    audit_historical_forecast_coverage,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run or apply the immutable WTHR-003 Open-Meteo Previous Runs "
            "historical fixed-24-hour forecast backfill."
        )
    )
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument(
        "--game-id",
        action="append",
        default=[],
        help="Restrict apply to one game ID; repeat to select multiple games.",
    )
    parser.add_argument("--snapshot-root", default="")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Fetch, retain, and persist forecasts. Without this flag, no writes occur.",
    )
    parser.add_argument(
        "--verify-artifacts",
        action="store_true",
        help="Recompute every stored raw checksum and validate its manifest.",
    )
    parser.add_argument(
        "--allow-free-evaluation",
        action="store_true",
        help=(
            "Acknowledge that keyless Open-Meteo access is local non-commercial "
            "evaluation only."
        ),
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="Print apply progress to stderr every N games.",
    )
    return parser.parse_args()


def _validate_contract_settings() -> None:
    settings = get_settings()
    expected = {
        "WEATHER_FORECAST_PROVIDER": (
            settings.weather_forecast_provider,
            WEATHER_FORECAST_PROVIDER,
        ),
        "OPEN_METEO_MODEL": (settings.open_meteo_model, WEATHER_FORECAST_MODEL),
        "OPEN_METEO_FIXED_LEAD_HOURS": (
            settings.open_meteo_fixed_lead_hours,
            WEATHER_FORECAST_FIXED_LEAD_HOURS,
        ),
    }
    drift = [
        f"{name}={actual!r} (expected {required!r})"
        for name, (actual, required) in expected.items()
        if actual != required
    ]
    if drift:
        raise SystemExit(
            "Configured weather source differs from the approved v1 contract: "
            + "; ".join(drift)
        )


def main() -> None:
    args = parse_args()
    if args.season_start > args.season_end:
        raise SystemExit("season-start must be less than or equal to season-end")
    if args.timeout_seconds <= 0:
        raise SystemExit("timeout-seconds must be positive")
    if args.progress_every <= 0:
        raise SystemExit("progress-every must be positive")
    _validate_contract_settings()
    settings = get_settings()

    if args.apply and not settings.open_meteo_api_key:
        if settings.app_env.lower() in {"prod", "production"}:
            raise SystemExit(
                "Production historical API use requires OPEN_METEO_API_KEY and a "
                "Professional-or-higher customer endpoint."
            )
        if not args.allow_free_evaluation:
            raise SystemExit(
                "Keyless access is local non-commercial evaluation only. Pass "
                "--allow-free-evaluation to acknowledge that boundary."
            )

    with SessionLocal() as session:
        assessment = assess_historical_forecast_backfill(
            session,
            season_start=args.season_start,
            season_end=args.season_end,
        )
        output = assessment.report()
        output["mode"] = "apply" if args.apply else "dry_run"
        output["selected_game_ids"] = sorted(set(args.game_id)) or None
        output["stored_coverage_before"] = audit_historical_forecast_coverage(
            session,
            assessment,
            verify_artifacts=args.verify_artifacts,
        )
        if args.apply:
            client = OpenMeteoPreviousRunsClient(
                base_url=settings.open_meteo_base_url,
                api_key=settings.open_meteo_api_key,
                timeout_seconds=args.timeout_seconds,
            )

            def progress(index: int, total: int, game_id: str, status: str) -> None:
                if index % args.progress_every == 0 or index == total:
                    print(
                        f"weather forecast backfill {index}/{total}: "
                        f"{game_id} {status}",
                        file=sys.stderr,
                        flush=True,
                    )

            service = HistoricalForecastBackfillService(
                session,
                client=client,
                snapshot_root=args.snapshot_root or None,
            )
            output["apply"] = service.run(
                assessment,
                game_ids=set(args.game_id) or None,
                progress=progress,
            )
            output["stored_coverage_after"] = audit_historical_forecast_coverage(
                session,
                assessment,
                verify_artifacts=args.verify_artifacts,
            )
    print(json.dumps(output, indent=2, default=str))
    if args.apply and output["apply"]["rows_unresolved"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
