from __future__ import annotations

from datetime import UTC, datetime
from itertools import combinations

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import (
    Base,
    SimulatedPlayerOutcome,
    SimulationRun,
)
from backend.app.schemas import UltimateLineupRequest
from backend.app.services.lineup_learning import (
    LineupLearningService,
    PlayerPoolRow,
)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        future=True,
    )
    return factory()


def _player(
    uid: str,
    position: str,
    *,
    mean_points: float = 5.0,
) -> PlayerPoolRow:
    return PlayerPoolRow(
        uid=uid,
        name=uid,
        team=None,
        opponent=None,
        position=position,
        salary=5000,
        actual_points=0.0,
        projected_mean_points=mean_points,
        projected_p90_points=mean_points,
        player_master_id=f"master-{uid}",
        source_player_key=f"source-{uid}",
    )


def _candidate_pool() -> tuple[
    list[PlayerPoolRow],
    list[list[PlayerPoolRow]],
]:
    quarterback = _player("qb", "QB")
    running_backs = [_player("rb-1", "RB"), _player("rb-2", "RB")]
    tight_end = _player("te", "TE")
    defense = _player("dst", "DST")
    baseline_receiver = _player(
        "baseline-receiver",
        "WR",
        mean_points=30.0,
    )
    scenario_receiver = _player(
        "scenario-receiver",
        "WR",
        mean_points=1.0,
    )
    common_receivers = [
        _player(f"common-wr-{index}", "WR")
        for index in range(5)
    ]
    players = [
        quarterback,
        *running_backs,
        tight_end,
        defense,
        baseline_receiver,
        scenario_receiver,
        *common_receivers,
    ]

    fixed = [quarterback, *running_backs, tight_end, defense]
    candidates = [
        [*fixed, special_receiver, *receiver_group]
        for special_receiver in (
            baseline_receiver,
            scenario_receiver,
        )
        for receiver_group in combinations(common_receivers, 3)
    ]
    return players, candidates


def _persist_simulation(
    session: Session,
    *,
    simulation_run_id: str,
    shocked: bool = True,
    random_seed: int = 42,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    baseline_receiver_points = 1.0 if shocked else 30.0
    scenario_receiver_points = 30.0 if shocked else 1.0
    session.add(
        SimulationRun(
            simulation_run_id=simulation_run_id,
            source_system="draftkings",
            season=2025,
            week=18,
            slate="sunday_main",
            iterations=1000,
            random_seed=random_seed,
            parameters_json={
                "iterations": 1000,
                "random_seed": random_seed,
                "min_history_games": 4,
                "prior_weight": 12.0,
                "noise_scale": 0.12,
                "use_residual_learning": False,
                "role_shocks": (
                    [{"source_player_key": "source-baseline-receiver"}]
                    if shocked
                    else []
                ),
                "point_in_time_shocks": [],
            },
            players_considered=2,
            players_simulated=2,
            status="completed",
            started_at=now,
            completed_at=now,
        )
    )
    session.add_all(
        [
            SimulatedPlayerOutcome(
                simulation_run_id=simulation_run_id,
                player_master_id="master-baseline-receiver",
                source_player_key="source-baseline-receiver",
                player_name="baseline-receiver",
                team=None,
                position="WR",
                salary=5000,
                history_games=4,
                mean_points=baseline_receiver_points,
                median_points=baseline_receiver_points,
                p75_points=baseline_receiver_points,
                p90_points=baseline_receiver_points,
                p95_points=baseline_receiver_points,
                ceiling_prob_20=0.0 if shocked else 1.0,
                ceiling_prob_25=0.0 if shocked else 1.0,
            ),
            SimulatedPlayerOutcome(
                simulation_run_id=simulation_run_id,
                player_master_id=None,
                source_player_key="source-scenario-receiver",
                player_name="scenario-receiver",
                team=None,
                position="WR",
                salary=5000,
                history_games=4,
                mean_points=scenario_receiver_points,
                median_points=scenario_receiver_points,
                p75_points=scenario_receiver_points,
                p90_points=scenario_receiver_points,
                p95_points=scenario_receiver_points,
                ceiling_prob_20=1.0 if shocked else 0.0,
                ceiling_prob_25=1.0 if shocked else 0.0,
            ),
        ]
    )
    session.commit()


def test_selected_simulation_run_reoptimizes_same_candidate_portfolio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    simulation_run_id = "simulation-run-2025-w18"
    baseline_simulation_run_id = "baseline-run-2025-w18"
    session = _session()
    _persist_simulation(
        session,
        simulation_run_id=simulation_run_id,
    )
    _persist_simulation(
        session,
        simulation_run_id=baseline_simulation_run_id,
        shocked=False,
    )
    players, candidates = _candidate_pool()
    service = LineupLearningService(session)
    generation_projection_snapshots: list[dict[str, float]] = []

    monkeypatch.setattr(
        service,
        "_collect_training_lineup_chunks",
        lambda **_kwargs: ([], [], 0, 0),
    )
    monkeypatch.setattr(
        service,
        "_compute_player_projection_lookup",
        lambda **_kwargs: (
            {
                player.player_master_id: (
                    player.projected_mean_points,
                    player.projected_p90_points,
                )
                for player in players
                if player.player_master_id is not None
            },
            {},
        ),
    )
    monkeypatch.setattr(
        service,
        "_fetch_slate_player_pool",
        lambda **_kwargs: players,
    )
    def candidate_lineups_for_pool(
        **kwargs: object,
    ) -> list[list[PlayerPoolRow]]:
        candidate_players = kwargs["players"]
        assert isinstance(candidate_players, list)
        generation_projection_snapshots.append(
            {
                player.uid: player.projected_mean_points
                for player in candidate_players
                if isinstance(player, PlayerPoolRow)
            }
        )
        return candidates

    monkeypatch.setattr(
        service,
        "_generate_candidate_lineups_adaptive",
        candidate_lineups_for_pool,
    )

    baseline_result = service.build_ultimate_lineups(
        UltimateLineupRequest(
            source_system="draftkings",
            season=2025,
            week=18,
            slate="sunday_main",
            candidate_lineups=1000,
            output_lineups=10,
            learned_only=False,
            max_player_exposure=1.0,
            max_qb_exposure=1.0,
            max_dst_exposure=1.0,
            random_seed=42,
        )
    )
    assert baseline_result.simulation_run_id is None
    assert baseline_result.simulation_outcomes_loaded == 0
    assert baseline_result.simulation_projection_overrides == 0
    assert baseline_result.portfolio_comparison is None
    baseline_source_keys = {
        player.source_player_key
        for row in baseline_result.rows
        for player in row.players
    }
    assert "source-baseline-receiver" in baseline_source_keys
    assert "source-scenario-receiver" not in baseline_source_keys

    progress_events: list[tuple[str, int, int, str]] = []
    result = service.build_ultimate_lineups(
        UltimateLineupRequest(
            source_system="draftkings",
            season=2025,
            week=18,
            slate="sunday_main",
            simulation_run_id=simulation_run_id,
            candidate_lineups=1000,
            output_lineups=10,
            learned_only=False,
            max_player_exposure=1.0,
            max_qb_exposure=1.0,
            max_dst_exposure=1.0,
            random_seed=42,
        ),
        progress_hook=lambda stage, current, total, message: progress_events.append(
            (stage, current, total, message)
        ),
    )

    assert result.simulation_run_id == simulation_run_id
    assert result.simulation_outcomes_loaded == 2
    assert result.simulation_projection_overrides == 2
    assert result.portfolio_comparison is not None
    comparison = result.portfolio_comparison
    assert comparison.shared_candidate_lineups == 20
    assert comparison.lineup_overlap_count == 0
    assert comparison.lineup_overlap_rate == 0.0
    assert comparison.projected_blend_reoptimization_lift == pytest.approx(
        29.0
    )
    assert comparison.objective_reoptimization_lift > 0.0
    assert progress_events[0][0] == "training"
    assert any(event[0] == "candidate_generation" for event in progress_events)
    assert progress_events[-1][:3] == ("portfolio_selection", 3, 3)

    selected_source_keys = {
        player.source_player_key
        for row in result.rows
        for player in row.players
    }
    assert "source-scenario-receiver" in selected_source_keys
    assert "source-baseline-receiver" not in selected_source_keys

    exposure_changes = {
        row.source_player_key: row
        for row in comparison.exposure_changes
    }
    assert (
        exposure_changes["source-baseline-receiver"].exposure_rate_delta
        == -1.0
    )
    assert (
        exposure_changes["source-scenario-receiver"].exposure_rate_delta
        == 1.0
    )

    paired_result = service.build_ultimate_lineups(
        UltimateLineupRequest(
            source_system="draftkings",
            season=2025,
            week=18,
            slate="sunday_main",
            simulation_run_id=simulation_run_id,
            baseline_simulation_run_id=baseline_simulation_run_id,
            candidate_lineups=1000,
            output_lineups=10,
            learned_only=False,
            max_player_exposure=1.0,
            max_qb_exposure=1.0,
            max_dst_exposure=1.0,
            random_seed=42,
        )
    )

    assert (
        generation_projection_snapshots[-1]["baseline-receiver"]
        == 30.0
    )
    assert (
        generation_projection_snapshots[-1]["scenario-receiver"]
        == 1.0
    )
    assert (
        paired_result.baseline_simulation_run_id
        == baseline_simulation_run_id
    )
    assert paired_result.baseline_simulation_outcomes_loaded == 2
    assert paired_result.baseline_simulation_projection_overrides == 2
    assert paired_result.portfolio_comparison is not None
    assert (
        paired_result.portfolio_comparison.baseline_simulation_run_id
        == baseline_simulation_run_id
    )
    assert (
        paired_result.portfolio_comparison
        .projected_blend_reoptimization_lift
        == pytest.approx(29.0)
    )


def test_simulation_run_must_be_completed_and_match_target_slice() -> None:
    session = _session()
    now = datetime.now(UTC).replace(tzinfo=None)
    session.add(
        SimulationRun(
            simulation_run_id="wrong-slice",
            source_system="draftkings",
            season=2025,
            week=17,
            slate="sunday_main",
            iterations=1000,
            players_considered=0,
            players_simulated=0,
            status="completed",
            started_at=now,
            completed_at=now,
        )
    )
    session.add(
        SimulationRun(
            simulation_run_id="still-running",
            source_system="draftkings",
            season=2025,
            week=18,
            slate="sunday_main",
            iterations=1000,
            players_considered=0,
            players_simulated=0,
            status="running",
            started_at=now,
        )
    )
    session.commit()
    service = LineupLearningService(session)

    with pytest.raises(ValueError, match="targets draftkings 2025-W17"):
        service._load_simulation_projection_overrides(
            simulation_run_id="wrong-slice",
            source_system="draftkings",
            season=2025,
            week=18,
            slate="sunday_main",
        )
    with pytest.raises(ValueError, match="is not completed"):
        service._load_simulation_projection_overrides(
            simulation_run_id="still-running",
            source_system="draftkings",
            season=2025,
            week=18,
            slate="sunday_main",
        )


def test_paired_simulation_runs_require_compatible_unshocked_baseline() -> None:
    with pytest.raises(
        ValidationError,
        match="simulation_run_id is required",
    ):
        UltimateLineupRequest(
            season=2025,
            week=18,
            baseline_simulation_run_id="baseline-only",
        )
    with pytest.raises(
        ValidationError,
        match="must differ",
    ):
        UltimateLineupRequest(
            season=2025,
            week=18,
            simulation_run_id="same-run",
            baseline_simulation_run_id="same-run",
        )

    session = _session()
    _persist_simulation(
        session,
        simulation_run_id="baseline-compatible",
        shocked=False,
    )
    _persist_simulation(
        session,
        simulation_run_id="scenario-compatible",
    )
    _persist_simulation(
        session,
        simulation_run_id="scenario-wrong-seed",
        random_seed=7,
    )
    service = LineupLearningService(session)
    baseline = session.get(SimulationRun, "baseline-compatible")
    scenario = session.get(SimulationRun, "scenario-compatible")
    wrong_seed = session.get(SimulationRun, "scenario-wrong-seed")
    assert baseline is not None
    assert scenario is not None
    assert wrong_seed is not None

    service._validate_paired_simulation_runs(
        baseline_run=baseline,
        scenario_run=scenario,
    )
    legacy_scenario_parameters = dict(scenario.parameters_json or {})
    legacy_scenario_parameters.pop("use_residual_learning")
    scenario.parameters_json = legacy_scenario_parameters
    service._validate_paired_simulation_runs(
        baseline_run=baseline,
        scenario_run=scenario,
    )
    with pytest.raises(ValueError, match="random_seed"):
        service._validate_paired_simulation_runs(
            baseline_run=baseline,
            scenario_run=wrong_seed,
        )
    with pytest.raises(ValueError, match="must not contain"):
        service._validate_paired_simulation_runs(
            baseline_run=scenario,
            scenario_run=wrong_seed,
        )
    with pytest.raises(ValueError, match="must contain at least one"):
        service._validate_paired_simulation_runs(
            baseline_run=baseline,
            scenario_run=baseline,
        )
