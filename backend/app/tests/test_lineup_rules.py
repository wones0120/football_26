import pytest

from backend.app.services.lineup_learning import (
    PlayerPoolRow,
    ShowdownLineup,
    ShowdownPlayerPoolRow,
    _classic_lineup_rule_violations,
    _lineup_satisfies_roster_rules,
    _showdown_lineup_satisfies_rules,
    _validate_classic_lineup_batch,
)


def _player(uid: str, position: str, team: str, opponent: str) -> PlayerPoolRow:
    return PlayerPoolRow(
        uid=uid,
        name=uid,
        team=team,
        opponent=opponent,
        position=position,
        salary=5000,
        actual_points=0.0,
        projected_mean_points=10.0,
        projected_p90_points=18.0,
    )


def test_lineup_rules_allow_valid_roster_shape_and_flex() -> None:
    lineup = [
        _player("qb1", "QB", "DAL", "NYG"),
        _player("rb1", "RB", "ATL", "NO"),
        _player("rb2", "RB", "PHI", "WAS"),
        _player("wr1", "WR", "SEA", "SF"),
        _player("wr2", "WR", "TB", "CAR"),
        _player("wr3", "WR", "MIA", "BUF"),
        _player("te1", "TE", "DET", "GB"),
        _player("flex1", "RB", "LV", "DEN"),
        _player("dst1", "DST", "NYJ", "NE"),
    ]
    assert _lineup_satisfies_roster_rules(lineup)


def test_lineup_rules_block_offense_against_selected_dst() -> None:
    lineup = [
        _player("qb1", "QB", "DAL", "NYG"),
        _player("rb1", "RB", "ATL", "NO"),
        _player("rb2", "RB", "KC", "BUF"),
        _player("wr1", "WR", "SEA", "SF"),
        _player("wr2", "WR", "TB", "CAR"),
        _player("wr3", "WR", "MIA", "BUF"),
        _player("te1", "TE", "DET", "GB"),
        _player("flex1", "WR", "LAR", "ARI"),
        _player("dst1", "DST", "BUF", "KC"),
    ]
    assert not _lineup_satisfies_roster_rules(lineup)


def test_lineup_rules_block_bad_slot_construction() -> None:
    lineup = [
        _player("qb1", "QB", "DAL", "NYG"),
        _player("qb2", "QB", "ATL", "NO"),
        _player("rb1", "RB", "PHI", "WAS"),
        _player("wr1", "WR", "SEA", "SF"),
        _player("wr2", "WR", "TB", "CAR"),
        _player("wr3", "WR", "MIA", "BUF"),
        _player("te1", "TE", "DET", "GB"),
        _player("flex1", "RB", "LV", "DEN"),
        _player("dst1", "DST", "NYJ", "NE"),
    ]
    assert not _lineup_satisfies_roster_rules(lineup)


def test_lineup_rule_violations_are_actionable() -> None:
    lineup = [
        _player("qb1", "QB", "DAL", "NYG"),
        _player("qb2", "QB", "ATL", "NO"),
        _player("rb1", "RB", "PHI", "WAS"),
        _player("wr1", "WR", "SEA", "SF"),
        _player("wr2", "WR", "TB", "CAR"),
        _player("wr3", "WR", "MIA", "BUF"),
        _player("te1", "TE", "DET", "GB"),
        _player("flex1", "RB", "LV", "DEN"),
        _player("dst1", "DST", "NYJ", "NE"),
    ]

    violations = _classic_lineup_rule_violations(lineup)

    assert "qb_count=2 expected=1" in violations


def test_lineup_batch_validation_hard_fails_with_context() -> None:
    lineup = [
        _player("qb1", "QB", "DAL", "NYG"),
        _player("qb1", "QB", "DAL", "NYG"),
    ]

    with pytest.raises(
        ValueError,
        match=r"validation failed \(unit-test\).*duplicate_player",
    ):
        _validate_classic_lineup_batch([lineup], context="unit-test")


def _showdown_player(uid: str, position: str, team: str, opponent: str) -> ShowdownPlayerPoolRow:
    return ShowdownPlayerPoolRow(
        uid=uid,
        name=uid,
        team=team,
        opponent=opponent,
        position=position,
        flex_salary=6000,
        captain_salary=9000,
        actual_points=10.0,
        projected_mean_points=12.0,
        projected_p90_points=20.0,
    )


def test_showdown_rules_allow_valid_shape() -> None:
    lineup = ShowdownLineup(
        captain=_showdown_player("p1", "QB", "DAL", "NYG"),
        flex_players=[
            _showdown_player("p2", "WR", "DAL", "NYG"),
            _showdown_player("p3", "RB", "DAL", "NYG"),
            _showdown_player("p4", "TE", "NYG", "DAL"),
            _showdown_player("p5", "K", "NYG", "DAL"),
            _showdown_player("p6", "DST", "NYG", "DAL"),
        ],
    )
    assert _showdown_lineup_satisfies_rules(lineup)


def test_showdown_rules_block_duplicate_player() -> None:
    shared = _showdown_player("p1", "QB", "DAL", "NYG")
    lineup = ShowdownLineup(
        captain=shared,
        flex_players=[
            shared,
            _showdown_player("p2", "WR", "DAL", "NYG"),
            _showdown_player("p3", "RB", "DAL", "NYG"),
            _showdown_player("p4", "TE", "NYG", "DAL"),
            _showdown_player("p5", "K", "NYG", "DAL"),
        ],
    )
    assert not _showdown_lineup_satisfies_rules(lineup)


def test_showdown_rules_block_six_from_same_team() -> None:
    lineup = ShowdownLineup(
        captain=_showdown_player("p1", "QB", "DAL", "NYG"),
        flex_players=[
            _showdown_player("p2", "WR", "DAL", "NYG"),
            _showdown_player("p3", "RB", "DAL", "NYG"),
            _showdown_player("p4", "TE", "DAL", "NYG"),
            _showdown_player("p5", "K", "DAL", "NYG"),
            _showdown_player("p6", "DST", "DAL", "NYG"),
        ],
    )
    assert not _showdown_lineup_satisfies_rules(lineup)
