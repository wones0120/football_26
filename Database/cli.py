from __future__ import annotations

import argparse
import logging
from typing import Iterable, List

from .controller import NFLIngestionController, LoadSummary
from .data_sources import NFLDataset


def _parse_datasets(raw: str | None) -> List[NFLDataset] | None:
    if not raw:
        return None
    tokens = [token.strip() for token in raw.split(",") if token.strip()]
    return [NFLDataset(token) for token in tokens] if tokens else None


def _format_summary(summary: LoadSummary) -> str:
    scope = f"week {summary.week}" if summary.week is not None else "entire season"
    return f"{summary.dataset:<20} season={summary.season} {scope:<14} rows={summary.rows_written}"


def _run_season(args: argparse.Namespace) -> None:
    controller = NFLIngestionController()
    datasets = _parse_datasets(args.datasets)
    summaries = controller.run_season(season=args.season, datasets=datasets)
    _print_results(summaries)


def _run_week(args: argparse.Namespace) -> None:
    controller = NFLIngestionController()
    datasets = _parse_datasets(args.datasets)
    summaries = controller.run_week(
        season=args.season, week=args.week, datasets=datasets
    )
    _print_results(summaries)


def _print_results(summaries: Iterable[LoadSummary]) -> None:
    if not summaries:
        print("No rows persisted. Check logs for details.")
        return
    print("Dataset summary:")
    for summary in summaries:
        print(" -", _format_summary(summary))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load NFL data from nfl_data_py into Postgres."
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    season_parser = subparsers.add_parser("season", help="Load an entire season")
    season_parser.add_argument("--season", type=int, required=True)
    season_parser.add_argument(
        "--datasets",
        type=str,
        help="Comma-separated datasets (schedules,weekly_rosters,weekly_stats,injuries)",
    )
    season_parser.set_defaults(func=_run_season)

    week_parser = subparsers.add_parser("week", help="Load a single week")
    week_parser.add_argument("--season", type=int, required=True)
    week_parser.add_argument("--week", type=int, required=True)
    week_parser.add_argument(
        "--datasets",
        type=str,
        help="Comma-separated datasets (schedules,weekly_rosters,weekly_stats,injuries)",
    )
    week_parser.set_defaults(func=_run_week)
    return parser


def main(argv: List[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level))
    args.func(args)


if __name__ == "__main__":
    main()
