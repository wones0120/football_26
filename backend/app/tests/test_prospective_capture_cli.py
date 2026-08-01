from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.capture_prospective_sources import (
    _aware_datetime,
    _discovered_draftkings_files,
)


def test_directory_discovery_requires_explicit_zero_padded_week_scope(
    tmp_path: Path,
) -> None:
    expected = tmp_path / "DKSalaries_2026_01_sunday_main.csv"
    expected.write_text("ID,Name\n", encoding="utf-8")
    (tmp_path / "DKSalaries.csv").write_text("ID,Name\n", encoding="utf-8")
    (tmp_path / "DKSalaries_2026_1_sunday_main.csv").write_text(
        "ID,Name\n",
        encoding="utf-8",
    )
    (tmp_path / "DKSalaries_2026_02_sunday_main.csv").write_text(
        "ID,Name\n",
        encoding="utf-8",
    )

    assert _discovered_draftkings_files(tmp_path, season=2026, week=1) == [expected]


def test_cli_timestamp_requires_offset_and_normalizes_to_utc() -> None:
    assert _aware_datetime("2026-09-13T13:00:00-04:00") == datetime(
        2026,
        9,
        13,
        17,
        0,
        tzinfo=UTC,
    )
    with pytest.raises(argparse.ArgumentTypeError):
        _aware_datetime("2026-09-13T13:00:00")
