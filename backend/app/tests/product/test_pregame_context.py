from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from backend.app.product_services.pregame_context import (
    PregameContextService,
    _filter_salary_player_pool,
    load_current_pregame_context,
)
from backend.app.product_schemas import PregamePlayerContextInput


def test_context_requires_exact_canonical_salary_identity():
    salaries = {
        "canonical-1": {
            "player_name": "Example Receiver",
            "team": "SEA",
            "position": "WR",
        }
    }

    rows = PregameContextService._normalize_players(
        [
            {
                "player_id": "canonical-1",
                "team": "SEA",
                "position": "WR",
                "target_share": 0.30,
                "expected_snaps": 58.0,
                "expected_routes": 34.0,
                "expected_targets": 8.5,
                "red_zone_share": 0.25,
                "role_label": "PRIMARY",
            }
        ],
        salaries,
    )

    assert rows[0]["player_master_id"] == "canonical-1"
    assert rows[0]["player_name"] == "Example Receiver"
    assert rows[0]["expected_snaps"] == 58.0
    assert rows[0]["expected_targets"] == 8.5
    with pytest.raises(ValueError, match="not in the selected salary slate"):
        PregameContextService._normalize_players(
            [{"player_id": "unknown", "target_share": 0.20}],
            salaries,
        )
    with pytest.raises(ValueError, match="does not match canonical salary identity"):
        PregameContextService._normalize_players(
            [{"player_id": "canonical-1", "team": "NE", "target_share": 0.20}],
            salaries,
        )


def test_explicit_team_shares_cannot_exceed_one():
    with pytest.raises(ValueError, match="Explicit target_share exceeds 1.0"):
        PregameContextService._validate_probability_sums(
            [
                {"team": "SEA", "position": "WR", "target_share": 0.60},
                {"team": "SEA", "position": "TE", "target_share": 0.50},
            ]
        )


def test_current_context_query_is_observed_and_received_by_cutoff():
    connection = MagicMock()
    result = connection.execute.return_value
    result.mappings.return_value = [
        {
            "player_master_id": "canonical-1",
            "context_run_id": "context-1",
        }
    ]
    cutoff = datetime(2026, 9, 8, 12, tzinfo=UTC)

    rows = load_current_pregame_context(
        connection,
        season=2026,
        week=1,
        slate="WEDNESDAY_NIGHT",
        cutoff=cutoff,
    )

    sql = str(connection.execute.call_args.args[0])
    params = connection.execute.call_args.args[1]
    assert "run.observed_at <= :cutoff" in sql
    assert "run.received_at <= :cutoff" in sql
    assert "context.expected_snaps" in sql
    assert "context.goal_line_share" in sql
    assert params["cutoff"] == cutoff
    assert rows == [
        {
            "player_master_id": "canonical-1",
            "context_run_id": "context-1",
        }
    ]


def test_salary_player_pool_applies_status_and_current_roster_gate():
    rows = [
        {
            "player_id": "receiver-1",
            "player_display_name": "Active Receiver",
            "team": "sea",
            "position": "WR",
            "player_status": "Q",
            "roster_status": "ACT",
        },
        {
            "player_id": "back-1",
            "player_display_name": "Unavailable Back",
            "team": "SEA",
            "position": "RB",
            "player_status": "OUT",
            "roster_status": "ACT",
        },
        {
            "player_id": "quarterback-1",
            "player_display_name": "Development QB",
            "team": "SEA",
            "position": "QB",
            "player_status": None,
            "roster_status": "DEV",
        },
        {
            "player_id": "defense-1",
            "player_display_name": "Seahawks",
            "team": "SEA",
            "position": "D/ST",
            "player_status": None,
            "roster_status": None,
        },
    ]

    pool = _filter_salary_player_pool(rows)

    assert [row["player_id"] for row in pool] == ["defense-1", "receiver-1"]
    assert pool[0]["position"] == "DST"
    assert pool[1]["player_status"] == "Q"


def test_context_schema_validates_expected_opportunity_fields():
    context = PregamePlayerContextInput(
        player_id="canonical-1",
        expected_snaps=42.0,
        expected_routes=27.0,
        expected_carries=3.5,
        expected_targets=6.0,
        red_zone_share=0.30,
        goal_line_share=0.10,
    )

    assert context.expected_routes == 27.0
    with pytest.raises(ValueError):
        PregamePlayerContextInput(
            player_id="canonical-1",
            expected_targets=-1.0,
        )
    with pytest.raises(ValueError):
        PregamePlayerContextInput(
            player_id="canonical-1",
            goal_line_share=1.1,
        )
