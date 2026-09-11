import pandas as pd

from backend.app.product_services.optimizer import OptimizerService


def _service() -> OptimizerService:
    return OptimizerService.__new__(OptimizerService)


def test_classic_solver_keeps_locked_canonical_player() -> None:
    positions = [
        ("qb-a", "QB", 30),
        ("qb-b", "QB", 20),
        ("rb-a", "RB", 25),
        ("rb-b", "RB", 24),
        ("rb-c", "RB", 23),
        ("wr-a", "WR", 22),
        ("wr-b", "WR", 21),
        ("wr-c", "WR", 20),
        ("wr-d", "WR", 19),
        ("wr-e", "WR", 18),
        ("wr-locked", "WR", 1),
        ("te-a", "TE", 17),
        ("te-b", "TE", 16),
        ("dst-a", "DST", 15),
        ("dst-b", "DST", 14),
    ]
    pool = pd.DataFrame(
        [
            {
                "player_id": player_id,
                "name": player_id,
                "position": position,
                "salary": 5000,
                "p90": score,
                "projection": score,
                "player_team": f"T{index % 6}",
                "opponent_team": f"T{(index + 1) % 6}",
            }
            for index, (player_id, position, score) in enumerate(positions)
        ]
    )

    lineup = _service()._solve_lineup(
        pool,
        contest_type="classic",
        stack_params={"enabled": False},
        locked_player_ids={"wr-locked"},
    )

    assert lineup is not None
    assert "wr-locked" in {row["player_id"] for row in lineup}


def test_showdown_solver_keeps_locked_canonical_player_in_one_slot() -> None:
    pool = pd.DataFrame(
        [
            {
                "player_id": f"player-{index}",
                "name": f"Player {index}",
                "position": "QB" if index < 2 else "WR",
                "salary": 5000,
                "p90": 30 - index if index < 7 else 1,
                "projection": 30 - index if index < 7 else 1,
                "player_team": "SEA" if index % 2 == 0 else "SF",
                "opponent_team": "SF" if index % 2 == 0 else "SEA",
            }
            for index in range(8)
        ]
    )

    lineup = _service()._solve_lineup(
        pool,
        contest_type="captain",
        stack_params={"enabled": False},
        locked_player_ids={"player-7"},
    )

    assert lineup is not None
    selected = [row for row in lineup if row["player_id"] == "player-7"]
    assert len(selected) == 1
    assert selected[0]["roster_position"] in {"CPT", "FLEX"}
