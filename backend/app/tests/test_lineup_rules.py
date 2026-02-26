from backend.app.services.lineup_learning import PlayerPoolRow, _lineup_satisfies_roster_rules


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
