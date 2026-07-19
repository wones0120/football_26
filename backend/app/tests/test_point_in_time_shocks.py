from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from pydantic import ValidationError

from backend.app.models import CuratedSalary
from backend.app.schemas import PointInTimeShockRequest, SimulateWeekRequest
from backend.app.services.simulation import (
    SimulationService,
    _apply_point_in_time_shock,
)


def _salary(
    master_id: str,
    *,
    source_key: str,
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
        player_name=master_id,
        normalized_name=master_id,
        team=team,
        position=position,
        roster_position=position,
        salary=6000,
    )


def _observed_at() -> datetime:
    return datetime(2025, 10, 5, 11, 30, tzinfo=UTC)


def test_projection_shock_changes_mean_and_volatility_deterministically() -> None:
    draws = np.asarray([10.0, 20.0, 30.0], dtype=float)

    adjusted = _apply_point_in_time_shock(
        draws,
        mean_multiplier=0.8,
        volatility_multiplier=1.5,
    )

    assert adjusted.tolist() == pytest.approx([1.0, 16.0, 31.0])
    assert _apply_point_in_time_shock(
        draws,
        mean_multiplier=0.8,
        volatility_multiplier=1.5,
    ).tolist() == pytest.approx(adjusted.tolist())


def test_point_in_time_shocks_target_teams_positions_or_stable_player_ids() -> None:
    service = SimulationService(session=None)  # type: ignore[arg-type]
    salary_rows = [
        _salary("buf-qb", source_key="dk-buf-qb", team="BUF", position="QB"),
        _salary("buf-rb", source_key="dk-buf-rb", team="BUF", position="RB"),
        _salary("mia-qb", source_key="dk-mia-qb", team="MIA", position="QB"),
    ]
    weather = PointInTimeShockRequest(
        shock_type="weather",
        observed_at=_observed_at(),
        label="Strong crosswind",
        teams=["buf", "MIA"],
        positions=["QB"],
        mean_multiplier=0.9,
        volatility_multiplier=1.1,
    )
    news = PointInTimeShockRequest(
        shock_type="news",
        observed_at=_observed_at(),
        label="Workload limitation",
        source_player_keys=["dk-buf-rb"],
        mean_multiplier=0.75,
    )

    targets = service._point_in_time_shock_targets(
        salary_rows=salary_rows,
        shocks=[weather, news],
    )

    assert [(index, shock.label) for index, shock in targets["buf-qb"]] == [
        (1, "Strong crosswind")
    ]
    assert [(index, shock.label) for index, shock in targets["mia-qb"]] == [
        (1, "Strong crosswind")
    ]
    assert [(index, shock.label) for index, shock in targets["buf-rb"]] == [
        (2, "Workload limitation")
    ]

    missing = news.model_copy(
        update={"source_player_keys": ["dk-missing"]}
    )
    with pytest.raises(ValueError, match="source-native player ID was not found"):
        service._point_in_time_shock_targets(
            salary_rows=salary_rows,
            shocks=[missing],
        )


def test_point_in_time_contract_enforces_cutoff_and_explicit_target_mode() -> None:
    observed_at = _observed_at()
    shock = PointInTimeShockRequest(
        shock_type="weather",
        observed_at=observed_at,
        label="Heavy wind",
        teams=["BUF", "MIA"],
        mean_multiplier=0.85,
    )
    request = SimulateWeekRequest(
        season=2025,
        week=5,
        scenario_as_of=observed_at + timedelta(minutes=30),
        point_in_time_shocks=[shock],
    )
    assert request.scenario_as_of is not None

    with pytest.raises(ValidationError, match="later than scenario_as_of"):
        SimulateWeekRequest(
            season=2025,
            week=5,
            scenario_as_of=observed_at - timedelta(minutes=1),
            point_in_time_shocks=[shock],
        )

    with pytest.raises(ValidationError, match="scenario_as_of must include"):
        SimulateWeekRequest(
            season=2025,
            week=5,
            scenario_as_of=datetime(2025, 10, 5, 12, 0),
            point_in_time_shocks=[shock],
        )

    with pytest.raises(ValidationError, match="timezone offset"):
        PointInTimeShockRequest(
            shock_type="news",
            observed_at=datetime(2025, 10, 5, 11, 30),
            label="Naive timestamp",
            teams=["BUF"],
            mean_multiplier=0.9,
        )

    with pytest.raises(ValidationError, match="label must not be blank"):
        PointInTimeShockRequest(
            shock_type="news",
            observed_at=observed_at,
            label=" ",
            teams=["BUF"],
            mean_multiplier=0.9,
        )

    with pytest.raises(ValidationError, match="exactly one target mode"):
        PointInTimeShockRequest(
            shock_type="news",
            observed_at=observed_at,
            label="Ambiguous target",
            teams=["BUF"],
            player_master_ids=["buf-qb"],
            mean_multiplier=0.9,
        )

    with pytest.raises(ValidationError, match="weather shocks must target"):
        PointInTimeShockRequest(
            shock_type="weather",
            observed_at=observed_at,
            label="Invalid player weather target",
            player_master_ids=["buf-qb"],
            mean_multiplier=0.9,
        )


def test_simulation_run_persists_point_in_time_cutoff_and_shock() -> None:
    class FakeSession:
        def add(self, _row: object) -> None:
            return None

        def commit(self) -> None:
            return None

    observed_at = _observed_at()
    request = SimulateWeekRequest(
        season=2025,
        week=5,
        random_seed=123,
        scenario_as_of=observed_at + timedelta(minutes=30),
        point_in_time_shocks=[
            PointInTimeShockRequest(
                shock_type="news",
                observed_at=observed_at,
                label="Offensive line downgrade",
                teams=["BUF"],
                positions=["QB", "RB"],
                mean_multiplier=0.9,
                volatility_multiplier=1.2,
            )
        ],
    )

    run = SimulationService(FakeSession())._new_run(request)  # type: ignore[arg-type]

    assert run.random_seed == 123
    assert run.parameters_json is not None
    assert run.parameters_json["scenario_as_of"] == "2025-10-05T12:00:00Z"
    assert run.parameters_json["point_in_time_shocks"][0]["shock_type"] == "news"
    assert (
        run.parameters_json["point_in_time_shocks"][0]["observed_at"]
        == "2025-10-05T11:30:00Z"
    )
