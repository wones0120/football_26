from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import Mock

import pandas as pd

from Database import curated_ingest


def test_unmatched_table_always_includes_slice_and_source_columns(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def capture_columns(_engine, table_name: str, frame: pd.DataFrame) -> None:
        captured["table_name"] = table_name
        captured["columns"] = set(frame.columns)

    connection = Mock()
    engine = Mock()
    engine.begin.return_value = nullcontext(connection)
    monkeypatch.setattr(curated_ingest, "ensure_table_columns", capture_columns)

    curated_ingest._ensure_unmatched_table(
        engine,
        pd.DataFrame(columns=["Name", "Position"]),
    )

    assert captured["table_name"] == "curated_unmatched"
    assert {
        "source",
        "season",
        "week",
        "slate",
        "add_to_player_master",
    }.issubset(captured["columns"])
    connection.execute.assert_called()
