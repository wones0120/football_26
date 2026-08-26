from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import get_settings
from backend.app.db import SessionLocal
from backend.app.services.current_weather_forecast import (
    CURRENT_WEATHER_FORECAST_PROVIDER,
    CurrentForecastCaptureService,
    OpenMeteoForecastClient,
    assess_current_forecast_capture,
    audit_current_forecast_capture,
)
from backend.app.services.weather_forecast_backfill import WEATHER_FORECAST_MODEL


def _aware_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid ISO-8601 timestamp: {value}"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone offset")
    return parsed.astimezone(UTC)


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description=(
            "Preview or capture append-only WTHR-004 current-game weather forecasts. "
            "Watch mode repeats refreshes until the declared slate lock."
        )
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--slate", required=True)
    parser.add_argument("--slate-lock-at", type=_aware_datetime, required=True)
    parser.add_argument(
        "--game-id",
        action="append",
        required=True,
        help=(
            "Canonical nflverse game ID in the slate; repeat for each game. "
            "Explicit IDs prevent display-name slate joins."
        ),
    )
    parser.add_argument("--snapshot-root", default="")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument(
        "--request-interval-seconds",
        type=float,
        default=settings.open_meteo_min_request_interval_seconds,
        help="Minimum delay between provider requests within one refresh.",
    )
    parser.add_argument(
        "--refresh-interval-minutes",
        type=int,
        default=settings.weather_forecast_refresh_interval_minutes,
        help="Watch-mode delay between complete slate refreshes.",
    )
    parser.add_argument(
        "--stale-after-minutes",
        type=int,
        default=settings.weather_forecast_stale_after_minutes,
        help="Age threshold used by the coverage/freshness report.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Call the provider and append snapshots. Without this flag, no writes occur.",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Refresh repeatedly until slate lock; requires --apply.",
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
        "--verify-artifacts",
        action="store_true",
        help="Verify the cutoff-selected raw artifact and manifest for every game.",
    )
    return parser.parse_args()


def _validate_args(args: argparse.Namespace) -> None:
    if args.season < 2000 or not 1 <= args.week <= 25:
        raise SystemExit("season must be >= 2000 and week must be between 1 and 25")
    if args.timeout_seconds <= 0:
        raise SystemExit("timeout-seconds must be positive")
    if args.request_interval_seconds < 0:
        raise SystemExit("request-interval-seconds must be non-negative")
    if args.refresh_interval_minutes <= 0:
        raise SystemExit("refresh-interval-minutes must be positive")
    if args.stale_after_minutes <= 0:
        raise SystemExit("stale-after-minutes must be positive")
    if args.watch and not args.apply:
        raise SystemExit("--watch requires --apply")
    if len(set(args.game_id)) != len(args.game_id):
        raise SystemExit("game-id values must be unique")


def _validate_contract_settings() -> None:
    settings = get_settings()
    expected = {
        "CURRENT_WEATHER_FORECAST_PROVIDER": (
            settings.current_weather_forecast_provider,
            CURRENT_WEATHER_FORECAST_PROVIDER,
        ),
        "OPEN_METEO_MODEL": (settings.open_meteo_model, WEATHER_FORECAST_MODEL),
    }
    drift = [
        f"{name}={actual!r} (expected {required!r})"
        for name, (actual, required) in expected.items()
        if actual != required
    ]
    if drift:
        raise SystemExit(
            "Configured current weather source differs from the approved v1 contract: "
            + "; ".join(drift)
        )


def _validate_access(args: argparse.Namespace) -> None:
    settings = get_settings()
    if not args.apply or settings.open_meteo_api_key:
        return
    if settings.app_env.lower() in {"prod", "production"}:
        raise SystemExit(
            "Production current Forecast API use requires OPEN_METEO_API_KEY and a "
            "Professional-or-higher customer endpoint."
        )
    if not args.allow_free_evaluation:
        raise SystemExit(
            "Keyless access is local non-commercial evaluation only. Pass "
            "--allow-free-evaluation to acknowledge that boundary."
        )


def _run_once(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    with SessionLocal() as session:
        assessment = assess_current_forecast_capture(
            session,
            season=args.season,
            week=args.week,
            slate=args.slate,
            slate_lock_at=args.slate_lock_at,
            game_ids=set(args.game_id),
        )
        now = datetime.now(UTC)
        output = assessment.report()
        output["mode"] = "apply" if args.apply else "dry_run"
        output["game_ids"] = sorted(set(args.game_id))
        output["stored_status_now_before"] = audit_current_forecast_capture(
            session,
            assessment,
            cutoff_at=now,
            stale_after=timedelta(minutes=args.stale_after_minutes),
            verify_artifacts=args.verify_artifacts,
        )
        if args.apply:
            client = OpenMeteoForecastClient(
                base_url=settings.open_meteo_forecast_base_url,
                api_key=settings.open_meteo_api_key,
                timeout_seconds=args.timeout_seconds,
            )

            def progress(index: int, total: int, game_id: str, status: str) -> None:
                print(
                    f"current weather refresh {index}/{total}: {game_id} {status}",
                    file=sys.stderr,
                    flush=True,
                )

            output["apply"] = CurrentForecastCaptureService(
                session,
                client=client,
                snapshot_root=args.snapshot_root or None,
                request_interval_seconds=args.request_interval_seconds,
            ).run(assessment, progress=progress)
            completed_at = datetime.now(UTC)
            output["stored_status_now_after"] = audit_current_forecast_capture(
                session,
                assessment,
                cutoff_at=completed_at,
                stale_after=timedelta(minutes=args.stale_after_minutes),
                verify_artifacts=args.verify_artifacts,
            )
            output["stored_status_as_of_lock"] = audit_current_forecast_capture(
                session,
                assessment,
                cutoff_at=args.slate_lock_at,
                stale_after=timedelta(minutes=args.stale_after_minutes),
                verify_artifacts=args.verify_artifacts,
            )
        return output


def main() -> None:
    args = parse_args()
    _validate_args(args)
    _validate_contract_settings()
    _validate_access(args)
    if args.watch and datetime.now(UTC) >= args.slate_lock_at:
        raise SystemExit("--watch requires a future slate-lock-at")
    completed_refresh = False
    while True:
        if (
            args.watch
            and completed_refresh
            and datetime.now(UTC) >= args.slate_lock_at
        ):
            return
        output = _run_once(args)
        completed_refresh = True
        print(json.dumps(output, indent=2, default=str), flush=True)
        if not args.watch:
            if args.apply and output["apply"]["rows_unresolved"]:
                raise SystemExit(1)
            return
        remaining_seconds = (
            args.slate_lock_at - datetime.now(UTC)
        ).total_seconds()
        if remaining_seconds <= 0:
            return
        time.sleep(
            min(args.refresh_interval_minutes * 60, remaining_seconds)
        )


if __name__ == "__main__":
    main()
