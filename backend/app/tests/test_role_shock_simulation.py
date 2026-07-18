import pytest

from backend.app.models import CuratedSalary, RawNflWeeklyStat
from backend.app.schemas import RoleShockRequest, SimulateWeekRequest
from backend.app.services.simulation import (
    SimulationService,
    _role_shock_projection_multiplier,
)


def _salary(
    master_id: str,
    *,
    source_key: str,
    name: str,
    team: str,
    position: str,
) -> CuratedSalary:
    return CuratedSalary(
        source_system="draftkings",
        season=2025,
        week=5,
        slate="sunday_main",
        source_player_key=source_key,
        player_master_id=master_id,
        player_name=name,
        normalized_name=name.lower(),
        team=team,
        position=position,
        roster_position=position,
        salary=6000,
    )


def test_role_shock_reallocates_recent_opportunity_by_scope() -> None:
    target = _salary(
        "target",
        source_key="dk-target",
        name="Target RB",
        team="DAL",
        position="RB",
    )
    rb_two = _salary(
        "rb-two",
        source_key="dk-rb-two",
        name="Second RB",
        team="DAL",
        position="RB",
    )
    rb_three = _salary(
        "rb-three",
        source_key="dk-rb-three",
        name="Third RB",
        team="DAL",
        position="RB",
    )
    receiver = _salary(
        "receiver",
        source_key="dk-receiver",
        name="Receiver",
        team="DAL",
        position="WR",
    )
    service = SimulationService(session=None)  # type: ignore[arg-type]

    multipliers, roles, warnings = service._role_shock_multipliers(
        salary_rows=[target, rb_two, rb_three, receiver],
        opportunity_by_master={
            "target": 10.0,
            "rb-two": 6.0,
            "rb-three": 4.0,
            "receiver": 10.0,
        },
        role_shocks=[
            RoleShockRequest(
                player_master_id="target",
                retained_opportunity_share=0.5,
                reallocation_scope="same_position",
            )
        ],
    )

    assert warnings == []
    assert multipliers["target"] == 0.5
    assert multipliers["rb-two"] == pytest.approx(1.5)
    assert multipliers["rb-three"] == pytest.approx(1.5)
    assert multipliers["receiver"] == 1.0
    assert roles == {
        "target": {"target"},
        "rb-two": {"recipient"},
        "rb-three": {"recipient"},
    }


def test_recent_opportunity_uses_only_latest_team_weeks() -> None:
    target = _salary(
        "target",
        source_key="dk-target",
        name="Target RB",
        team="DAL",
        position="RB",
    )
    history_rows = [
        RawNflWeeklyStat(
            ingest_run_id="run",
            source_system="nflreadpy",
            season=2025,
            week=week,
            player_id="nfl-target",
            player_name="Target RB",
            team="DAL",
            position="RB",
            raw_row_json={"carries": 100 if week == 1 else 1, "targets": 0},
        )
        for week in range(1, 6)
    ]
    service = SimulationService(session=None)  # type: ignore[arg-type]

    opportunities = service._recent_opportunity_by_master(
        history_rows=history_rows,
        player_id_to_masters={"nfl-target": {"target"}},
        salary_rows=[target],
        history_weeks=4,
    )

    assert opportunities == {"target": 4.0}


def test_recipient_projection_boost_is_dampened() -> None:
    assert _role_shock_projection_multiplier(2.0, {"recipient"}) == pytest.approx(1.65)
    assert _role_shock_projection_multiplier(0.0, {"target"}) == 0.0


def test_role_shock_requires_canonical_or_source_identity() -> None:
    with pytest.raises(ValueError, match="player_master_id or source_player_key"):
        RoleShockRequest()


def test_simulation_run_persists_seed_and_role_shock_parameters() -> None:
    class FakeSession:
        def add(self, _row: object) -> None:
            return None

        def commit(self) -> None:
            return None

    request = SimulateWeekRequest(
        season=2025,
        week=5,
        random_seed=123,
        role_shocks=[
            RoleShockRequest(
                source_player_key="dk-target",
                retained_opportunity_share=0.0,
                reallocation_scope="skill_players",
            )
        ],
    )

    run = SimulationService(FakeSession())._new_run(request)  # type: ignore[arg-type]

    assert run.random_seed == 123
    assert run.parameters_json is not None
    assert run.parameters_json["role_shocks"][0]["source_player_key"] == "dk-target"
    assert run.parameters_json["role_shocks"][0]["retained_opportunity_share"] == 0.0
