from scripts.build_showdown_oracle_dataset import _completion_evidence
from backend.app.services.lineup_learning import (
    ShowdownPlayerPoolRow, _apply_curated_showdown_actual_fallback,
)


def _player(uid: str, team: str, *, attempts: float = 0.0, carries: float = 0.0) -> ShowdownPlayerPoolRow:
    return ShowdownPlayerPoolRow(
        uid=uid,
        name=uid,
        team=team,
        opponent="BBB" if team == "AAA" else "AAA",
        position="QB",
        flex_salary=6000,
        captain_salary=9000,
        actual_points=10.0,
        actual_pass_attempts=attempts,
        actual_carries=carries,
    )


def test_completion_evidence_requires_two_teams_with_final_usage() -> None:
    incomplete = [
        _player("a", "AAA", attempts=30),
        _player("b", "BBB", attempts=8, carries=5),
    ]
    complete = [
        _player("a", "AAA", attempts=30),
        _player("b", "BBB", attempts=19, carries=4),
    ]

    assert not _completion_evidence(incomplete)["is_complete"]
    assert _completion_evidence(complete)["is_complete"]


def test_curated_actual_fallback_uses_canonical_id_and_preserves_raw_points() -> None:
    points = {"raw-id": 25.0}
    sources = {"raw-id": "raw_nfl_weekly_stat"}
    opportunity = {"raw-id": {"pass_attempts": 31.0}}
    _apply_curated_showdown_actual_fallback([
        {"player_master_id": "raw-id", "payload": {"position": "QB", "passing_tds": 0}},
        {"player_master_id": "fallback-id", "payload": {"position": "QB", "attempts": 30,
                                                       "passing_yards": 250, "passing_tds": 2,
                                                       "carries": 5}},
    ], points, sources, opportunity)
    assert points["raw-id"] == 25.0
    assert sources["raw-id"] == "raw_nfl_weekly_stat"
    assert points["fallback-id"] == 18.0
    assert opportunity["fallback-id"]["pass_attempts"] == 30.0
    assert sources["fallback-id"] == "curated_weekly_stats"
