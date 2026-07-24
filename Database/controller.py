from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from .data_sources import NFLDataset
from .ingestion import LoadResult, NFLIngestionService


@dataclass(frozen=True)
class LoadSummary:
    dataset: str
    season: int
    week: int | None
    rows_written: int


class NFLIngestionController:
    """High-level orchestration layer suited for CLI/UI consumption."""

    def __init__(self, service: NFLIngestionService | None = None):
        self.service = service or NFLIngestionService()

    def run_season(
        self, season: int, datasets: Iterable[NFLDataset | str] | None = None
    ) -> List[LoadSummary]:
        return self._summaries(
            self.service.load_season(season=season, datasets=datasets)
        )

    def run_week(
        self,
        season: int,
        week: int,
        datasets: Iterable[NFLDataset | str] | None = None,
    ) -> List[LoadSummary]:
        return self._summaries(
            self.service.load_week(season=season, week=week, datasets=datasets)
        )

    @staticmethod
    def _summaries(results: Sequence[LoadResult]) -> List[LoadSummary]:
        return [
            LoadSummary(
                dataset=result.dataset.value,
                season=result.season,
                week=result.week,
                rows_written=result.rows_written,
            )
            for result in results
        ]
