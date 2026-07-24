from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, List, Sequence
from urllib.error import HTTPError, URLError

import pandas as pd
import nfl_data_py as nfl
from datetime import datetime

try:  # optional dependency for live endpoints
    import nflreadpy as nflread
except ImportError:  # pragma: no cover - optional
    nflread = None

try:
    import polars as pl
except ImportError:  # pragma: no cover - optional
    pl = None

try:
    from requests import exceptions as requests_exceptions
except ImportError:  # pragma: no cover - optional
    requests_exceptions = None


class NFLDataset(str, Enum):
    """Datasets exposed by the providers that map to our tables."""

    SCHEDULES = "schedules"
    WEEKLY_ROSTERS = "weekly_rosters"
    WEEKLY_STATS = "weekly_stats"
    INJURIES = "injuries"


class DataProvider(str, Enum):
    NFL_DATA_PY = "nfl_data_py"
    NFL_READPY = "nflreadpy"


Fetcher = Callable[[List[int]], pd.DataFrame]


@dataclass(frozen=True)
class DatasetFetcher:
    dataset: NFLDataset
    fetcher: Fetcher


@dataclass(frozen=True)
class CurrentContext:
    season: int
    week: int


class NFLDataSource:
    """Thin wrapper around data providers so we can mock / swap sources later."""

    def __init__(
        self,
        custom_fetchers: Sequence[DatasetFetcher] | None = None,
        provider: DataProvider | str | None = None,
    ):
        default_provider = DataProvider.NFL_READPY if nflread is not None else DataProvider.NFL_DATA_PY
        provider_name = provider or os.getenv("NFL_DATA_PROVIDER", default_provider.value)
        self.provider = DataProvider(provider_name)
        self._fetch_map = self._build_fetch_map()

        if custom_fetchers:
            for spec in custom_fetchers:
                self._fetch_map[spec.dataset] = spec.fetcher

    def fetch(self, dataset: NFLDataset, seasons: Sequence[int] | int) -> pd.DataFrame:
        """Return a dataframe for the requested dataset and seasons."""
        normalized = self._normalize_seasons(seasons)
        fetcher = self._fetch_map[dataset]
        logging.info(
            "Requesting %s for seasons: %s with provider=%s",
            dataset.value,
            normalized,
            self.provider.value,
        )
        try:
            df = fetcher(normalized)
        except (HTTPError, URLError, ConnectionError) as exc:
            logging.warning(
                "Provider %s missing %s for seasons %s (%s)", self.provider.value, dataset.value, normalized, exc
            )
            return pd.DataFrame()
        except Exception as exc:
            if requests_exceptions and isinstance(exc, requests_exceptions.HTTPError):
                logging.warning(
                    "Provider %s missing %s for seasons %s (%s)", self.provider.value, dataset.value, normalized, exc
                )
                return pd.DataFrame()
            if requests_exceptions and isinstance(exc, requests_exceptions.ConnectionError):
                logging.warning(
                    "Provider %s connection error for %s seasons %s (%s)",
                    self.provider.value,
                    dataset.value,
                    normalized,
                    exc,
                )
                return pd.DataFrame()
            raise RuntimeError(
                f"Failed to fetch {dataset.value} for {normalized} using {self.provider.value}"
            ) from exc
        return self._ensure_pandas(df)

    def get_current_context(self) -> CurrentContext:
        if self.provider == DataProvider.NFL_READPY and nflread is not None:
            return CurrentContext(
                season=int(nflread.get_current_season()),
                week=int(nflread.get_current_week()),
            )

        # Fallback: approximate using current year and week 1
        now = datetime.utcnow()
        logging.warning(
            "Provider %s does not support current-week lookup; defaulting to season=%s week=1",
            self.provider.value,
            now.year,
        )
        return CurrentContext(season=now.year, week=1)

    def _build_fetch_map(self) -> dict[NFLDataset, Fetcher]:
        if self.provider == DataProvider.NFL_READPY:
            if nflread is None:
                raise ImportError("nflreadpy is not installed but provider nflreadpy was selected")
            return {
                NFLDataset.SCHEDULES: lambda seasons: nflread.load_schedules(seasons=seasons),
                NFLDataset.WEEKLY_ROSTERS: lambda seasons: nflread.load_rosters_weekly(seasons=seasons),
                NFLDataset.WEEKLY_STATS: lambda seasons: nflread.load_player_stats(
                    seasons=seasons, summary_level="week"
                ),
                NFLDataset.INJURIES: lambda seasons: nflread.load_injuries(seasons=seasons),
            }

        # default to nfl_data_py
        return {
            NFLDataset.SCHEDULES: nfl.import_schedules,
            NFLDataset.WEEKLY_ROSTERS: nfl.import_weekly_rosters,
            NFLDataset.WEEKLY_STATS: nfl.import_weekly_data,
            NFLDataset.INJURIES: nfl.import_injuries,
        }

    @staticmethod
    def _normalize_seasons(seasons: Sequence[int] | int) -> List[int]:
        if isinstance(seasons, int):
            return [seasons]
        if isinstance(seasons, Iterable):
            unique = sorted({int(season) for season in seasons})
            return unique
        raise TypeError("seasons must be an int or iterable of ints")

    @staticmethod
    def _ensure_pandas(df):
        if isinstance(df, pd.DataFrame):
            return df
        if pl is not None and isinstance(df, pl.DataFrame):
            return df.to_pandas()
        if hasattr(df, "to_pandas"):
            return df.to_pandas()
        raise TypeError("Unsupported dataframe type returned from provider")
