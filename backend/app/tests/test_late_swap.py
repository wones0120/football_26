from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest
from pydantic import ValidationError

from backend.app.schemas import UltimateLineupRequest
from backend.app.services.lineup_learning import LineupLearningService, PlayerPoolRow


def _player(
    uid: str,
    *,
    position: str,
    team: str,
    index: int,
) -> PlayerPoolRow:
    return PlayerPoolRow(
        uid=uid,
        name=uid,
        team=team,
        opponent=None,
        position=position,
        salary=5000,
        actual_points=0.0,
        projected_mean_points=10.0 + (index / 10.0),
        projected_p90_points=16.0 + (index / 10.0),
        player_master_id=f"master-{uid}",
        source_player_key=f"source-{uid}",
    )


def _pool() -> list[PlayerPoolRow]:
    specs = [
        ("qb-0", "QB", "BUF"),
        ("qb-1", "QB", "BUF"),
        ("qb-2", "QB", "MIA"),
        ("qb-3", "QB", "KC"),
        ("rb-0", "RB", "BUF"),
        ("rb-1", "RB", "MIA"),
        ("rb-2", "RB", "KC"),
        ("rb-3", "RB", "BUF"),
        ("rb-4", "RB", "NYJ"),
        ("rb-5", "RB", "DAL"),
        ("wr-0", "WR", "BUF"),
        ("wr-1", "WR", "MIA"),
        ("wr-2", "WR", "NYJ"),
        ("wr-3", "WR", "BUF"),
        ("wr-4", "WR", "KC"),
        ("wr-5", "WR", "DAL"),
        ("wr-6", "WR", "NE"),
        ("te-0", "TE", "NE"),
        ("te-1", "TE", "BUF"),
        ("te-2", "TE", "MIA"),
        ("te-3", "TE", "KC"),
        ("dst-0", "DST", "DAL"),
        ("dst-1", "DST", "BUF"),
        ("dst-2", "DST", "MIA"),
        ("dst-3", "DST", "KC"),
    ]
    return [
        _player(uid, position=position, team=team, index=index)
        for index, (uid, position, team) in enumerate(specs)
    ]


def _original_source_keys() -> list[str]:
    return [
        "source-qb-0",
        "source-rb-0",
        "source-rb-1",
        "source-wr-0",
        "source-wr-1",
        "source-wr-2",
        "source-te-0",
        "source-rb-2",
        "source-dst-0",
    ]


def _lineup_uids(
    lineups: list[list[PlayerPoolRow]],
) -> list[list[str]]:
    return [[player.uid for player in lineup] for lineup in lineups]


def test_late_swap_requires_locked_players_and_excludes_started_alternates() -> None:
    service = LineupLearningService(session=None)  # type: ignore[arg-type]
    players = _pool()
    required, excluded, locked_teams, locked_source_keys = (
        service._late_swap_constraints(
            players=players,
            original_source_player_keys=_original_source_keys(),
            locked_teams=["buf"],
        )
    )

    assert locked_teams == ["BUF"]
    assert required == {"qb-0", "rb-0", "wr-0"}
    assert locked_source_keys == [
        "source-qb-0",
        "source-rb-0",
        "source-wr-0",
    ]
    assert {"qb-1", "rb-3", "wr-3", "te-1", "dst-1"}.issubset(excluded)

    first = service._generate_candidate_lineups_adaptive(
        players=players,
        requested_lineups=80,
        min_salary_floor=0,
        rng=np.random.default_rng(42),
        required_player_uids=required,
        excluded_player_uids=excluded,
    )
    second = service._generate_candidate_lineups_adaptive(
        players=players,
        requested_lineups=80,
        min_salary_floor=0,
        rng=np.random.default_rng(42),
        required_player_uids=required,
        excluded_player_uids=excluded,
    )

    assert len(first) == 100
    assert _lineup_uids(first) == _lineup_uids(second)
    for lineup in first:
        lineup_ids = {player.uid for player in lineup}
        assert required.issubset(lineup_ids)
        assert not lineup_ids & excluded


def test_late_swap_rejects_missing_source_ids_and_invalid_original_lineup() -> None:
    service = LineupLearningService(session=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="absent from the selected salary slice"):
        service._late_swap_constraints(
            players=_pool(),
            original_source_player_keys=[
                *_original_source_keys()[:-1],
                "source-missing",
            ],
            locked_teams=["BUF"],
        )

    with pytest.raises(ValueError, match="original lineup is invalid"):
        service._late_swap_constraints(
            players=_pool(),
            original_source_player_keys=[
                "source-qb-0",
                "source-qb-1",
                *_original_source_keys()[2:],
            ],
            locked_teams=["BUF"],
        )


def test_late_swap_request_requires_complete_timezone_aware_contract() -> None:
    valid = UltimateLineupRequest(
        season=2025,
        week=18,
        late_swap_as_of=datetime(2025, 12, 28, 18, 30, tzinfo=UTC),
        late_swap_original_source_player_keys=_original_source_keys(),
        late_swap_locked_teams=["BUF"],
    )
    assert valid.late_swap_as_of is not None

    parsed_from_cli_text = UltimateLineupRequest(
        season=2025,
        week=18,
        late_swap_as_of="2025-12-28T18:30:00-05:00",  # type: ignore[arg-type]
        late_swap_original_source_player_keys=_original_source_keys(),
        late_swap_locked_teams=["BUF"],
    )
    assert parsed_from_cli_text.late_swap_as_of is not None
    assert parsed_from_cli_text.late_swap_as_of.utcoffset() is not None

    with pytest.raises(ValidationError, match="timezone offset"):
        UltimateLineupRequest(
            season=2025,
            week=18,
            late_swap_as_of=datetime(2025, 12, 28, 18, 30),
            late_swap_original_source_player_keys=_original_source_keys(),
            late_swap_locked_teams=["BUF"],
        )

    with pytest.raises(ValidationError, match="exactly nine"):
        UltimateLineupRequest(
            season=2025,
            week=18,
            late_swap_as_of=datetime(2025, 12, 28, 18, 30, tzinfo=UTC),
            late_swap_original_source_player_keys=_original_source_keys()[:-1],
            late_swap_locked_teams=["BUF"],
        )


def test_late_swap_constraints_are_checkpoint_fingerprinted(tmp_path) -> None:
    service = LineupLearningService(session=None)  # type: ignore[arg-type]
    players = _pool()
    required, excluded, _teams, _keys = service._late_swap_constraints(
        players=players,
        original_source_player_keys=_original_source_keys(),
        locked_teams=["BUF"],
    )
    checkpoint_path = tmp_path / "late-swap.sqlite3"
    created = service._generate_candidate_lineups_adaptive(
        players=players,
        requested_lineups=100,
        min_salary_floor=0,
        rng=np.random.default_rng(42),
        checkpoint_path=checkpoint_path,
        checkpoint_interval_attempts=100,
        checkpoint_context={"late_swap": True},
        required_player_uids=required,
        excluded_player_uids=excluded,
    )
    reused = service._generate_candidate_lineups_adaptive(
        players=players,
        requested_lineups=100,
        min_salary_floor=0,
        rng=np.random.default_rng(999),
        checkpoint_path=checkpoint_path,
        resume_from_checkpoint=True,
        checkpoint_interval_attempts=100,
        checkpoint_context={"late_swap": True},
        required_player_uids=required,
        excluded_player_uids=excluded,
    )
    assert _lineup_uids(reused) == _lineup_uids(created)

    with pytest.raises(
        ValueError,
        match="does not match the current generation request or player pool",
    ):
        service._generate_candidate_lineups_adaptive(
            players=players,
            requested_lineups=100,
            min_salary_floor=0,
            rng=np.random.default_rng(42),
            checkpoint_path=checkpoint_path,
            resume_from_checkpoint=True,
            checkpoint_interval_attempts=100,
            checkpoint_context={"late_swap": True},
            required_player_uids={*required, "rb-1"},
            excluded_player_uids=excluded,
        )
