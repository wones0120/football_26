from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, List, Sequence

import pandas as pd

from .config import get_connection_string
from .data_sources import NFLDataSource, NFLDataset
from .operations import delete_from_postgres, insert_into_postgres


@dataclass(frozen=True)
class DatasetConfig:
    table_name: str
    supports_week_filter: bool = True


@dataclass(frozen=True)
class LoadResult:
    dataset: NFLDataset
    season: int
    week: int | None
    rows_written: int


class NFLIngestionService:
    """Coordinates pulls from nfl_data_py and writes to Postgres."""

    DEFAULT_SEASON_DATASETS: Sequence[NFLDataset] = (
        NFLDataset.SCHEDULES,
        NFLDataset.WEEKLY_ROSTERS,
        NFLDataset.WEEKLY_STATS,
    )

    DEFAULT_WEEK_DATASETS: Sequence[NFLDataset] = (
        NFLDataset.SCHEDULES,
        NFLDataset.WEEKLY_ROSTERS,
        NFLDataset.WEEKLY_STATS,
    )

    DATASET_CONFIG: dict[NFLDataset, DatasetConfig] = {
        NFLDataset.SCHEDULES: DatasetConfig(table_name="nfl_schedules"),
        NFLDataset.WEEKLY_ROSTERS: DatasetConfig(table_name="nfl_weekly_rosters"),
        NFLDataset.WEEKLY_STATS: DatasetConfig(table_name="nfl_weekly_data"),
    }

    def __init__(
        self,
        connection_string: str | None = None,
        data_source: NFLDataSource | None = None,
    ):
        self.connection_string = connection_string or get_connection_string()
        self.data_source = data_source or NFLDataSource()

    def load_season(
        self,
        season: int,
        datasets: Iterable[NFLDataset | str] | None = None,
    ) -> List[LoadResult]:
        """Download and persist a full season for the selected datasets."""
        normalized_datasets = self._normalize_datasets(
            datasets, self.DEFAULT_SEASON_DATASETS
        )
        results: List[LoadResult] = []

        for dataset in normalized_datasets:
            df = self.data_source.fetch(dataset, season)
            df = self._ensure_season(df, season)
            result = self._persist(dataset, df, season, week=None)
            if result:
                results.append(result)
        return results

    def load_week(
        self,
        season: int,
        week: int,
        datasets: Iterable[NFLDataset | str] | None = None,
    ) -> List[LoadResult]:
        """Download a single week for the selected datasets."""
        normalized_datasets = self._normalize_datasets(
            datasets, self.DEFAULT_WEEK_DATASETS
        )
        results: List[LoadResult] = []

        for dataset in normalized_datasets:
            df = self.data_source.fetch(dataset, season)
            df = self._filter_week(dataset, df, week)
            df = self._ensure_season(df, season)
            result = self._persist(dataset, df, season, week=week)
            if result:
                results.append(result)
        return results

    def _persist(
        self,
        dataset: NFLDataset,
        df: pd.DataFrame,
        season: int,
        week: int | None,
    ) -> LoadResult | None:
        if df.empty:
            logging.warning("No rows returned for %s", dataset.value)
            return LoadResult(dataset=dataset, season=season, week=week, rows_written=0)

        config = self.DATASET_CONFIG[dataset]
        logging.info(
            "Persisting %s rows for %s season=%s week=%s",
            len(df),
            dataset.value,
            season,
            week,
        )
        delete_from_postgres(
            connection_string=self.connection_string,
            table_name=config.table_name,
            season=season,
            week=week,
        )
        inserted = insert_into_postgres(
            df=df,
            connection_string=self.connection_string,
            table_name=config.table_name,
            season=season,
            week=week,
        )
        if not inserted:
            logging.error("Insert failed for %s season=%s week=%s", dataset, season, week)
            return None

        return LoadResult(dataset=dataset, season=season, week=week, rows_written=len(df))

    def _filter_week(
        self,
        dataset: NFLDataset,
        df: pd.DataFrame,
        week: int,
    ) -> pd.DataFrame:
        config = self.DATASET_CONFIG[dataset]
        if not config.supports_week_filter:
            return df
        if df.empty:
            return df
        if "week" not in df.columns:
            raise ValueError(f"{dataset.value} dataframe does not contain a week column")
        return df[df["week"] == week]

    @staticmethod
    def _ensure_season(df: pd.DataFrame, season: int) -> pd.DataFrame:
        if "season" not in df.columns:
            df = df.copy()
            df["season"] = season
        return df

    @staticmethod
    def _normalize_datasets(
        datasets: Iterable[NFLDataset | str] | None,
        default: Sequence[NFLDataset],
    ) -> List[NFLDataset]:
        if datasets is None:
            return list(default)
        normalized: List[NFLDataset] = []
        for dataset in datasets:
            normalized.append(NFLDataset(dataset))
        return normalized
