from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.app.product_services.projection_audit import capture_benchmark


def _benchmark():
    return {
        "source_name": "Example source",
        "source_url": "https://example.org/week3",
        "season": 2026, "week": 3, "slate_id": "SUNDAY_MAIN",
        "captured_at": datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc).isoformat(),
        "players": [{"player_id": "canonical-1", "projection": 20.5,
                     "value": 3.2, "classification": "Good"}],
    }


def test_benchmark_capture_requires_canonical_ids_and_is_idempotent():
    connection = MagicMock()
    connection.execute.return_value.scalars.return_value = ["canonical-1"]
    payload = _benchmark()
    first = capture_benchmark(connection, payload)
    second = capture_benchmark(connection, payload)
    assert first == second
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert any("ON CONFLICT (benchmark_id) DO NOTHING" in sql for sql in statements)
    assert any("ON CONFLICT (benchmark_id, player_id) DO NOTHING" in sql for sql in statements)


def test_benchmark_capture_rejects_unverified_or_imputed_values():
    connection = MagicMock()
    payload = _benchmark()
    payload["players"][0]["player_id"] = ""
    with pytest.raises(ValueError, match="canonical"):
        capture_benchmark(connection, payload)
    unavailable = {**_benchmark(), "status": "unavailable", "players": [],
                   "unavailable_reason": "Source inaccessible"}
    capture_benchmark(connection, unavailable)
    unavailable["players"] = [{"player_id": "canonical-1", "projection": 0}]
    with pytest.raises(ValueError, match="no player values"):
        capture_benchmark(connection, unavailable)
