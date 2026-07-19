from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from backend.app.schemas import UltimateLineupRequest
from backend.app.services.candidate_checkpoint import CandidateCheckpointStore
from backend.app.services.lineup_learning import LineupLearningService, PlayerPoolRow


def _player(
    uid: str,
    *,
    position: str,
    index: int,
) -> PlayerPoolRow:
    return PlayerPoolRow(
        uid=uid,
        name=uid,
        team=f"T{index:02d}",
        opponent=None,
        position=position,
        salary=5000,
        actual_points=0.0,
        projected_mean_points=10.0 + index / 10.0,
        projected_p90_points=16.0 + index / 10.0,
    )


def _player_pool() -> list[PlayerPoolRow]:
    positions = [
        ("QB", 3),
        ("RB", 8),
        ("WR", 10),
        ("TE", 5),
        ("DST", 4),
    ]
    players: list[PlayerPoolRow] = []
    index = 0
    for position, count in positions:
        for position_index in range(count):
            players.append(
                _player(
                    f"{position.lower()}-{position_index}",
                    position=position,
                    index=index,
                )
            )
            index += 1
    return players


def _lineup_uids(
    lineups: list[list[PlayerPoolRow]],
) -> list[list[str]]:
    return [[player.uid for player in lineup] for lineup in lineups]


def test_candidate_checkpoint_resume_matches_uninterrupted_sequence(tmp_path) -> None:
    service = LineupLearningService(session=None)  # type: ignore[arg-type]
    players = _player_pool()
    context = {"season": 2025, "week": 18, "random_seed": 42}
    baseline = service._generate_candidate_lineups_adaptive(
        players=players,
        requested_lineups=120,
        min_salary_floor=43000,
        rng=np.random.default_rng(42),
        checkpoint_context=context,
    )

    checkpoint_path = tmp_path / "ultimate-candidates.sqlite3"
    interrupted = False

    def interrupt_after_first_flush(attempts: int, candidate_count: int) -> None:
        nonlocal interrupted
        assert attempts >= 25
        assert candidate_count > 0
        if not interrupted:
            interrupted = True
            raise RuntimeError("simulated interruption")

    with pytest.raises(RuntimeError, match="simulated interruption"):
        service._generate_candidate_lineups_adaptive(
            players=players,
            requested_lineups=120,
            min_salary_floor=43000,
            rng=np.random.default_rng(42),
            checkpoint_path=checkpoint_path,
            checkpoint_interval_attempts=25,
            checkpoint_context=context,
            checkpoint_progress_callback=interrupt_after_first_flush,
        )

    partial = CandidateCheckpointStore(checkpoint_path).load()
    assert partial is not None
    assert partial.status == "interrupted"
    assert partial.attempts == 25
    assert 0 < len(partial.candidate_uids) < 120

    resumed = service._generate_candidate_lineups_adaptive(
        players=players,
        requested_lineups=120,
        min_salary_floor=43000,
        rng=np.random.default_rng(999),
        checkpoint_path=checkpoint_path,
        resume_from_checkpoint=True,
        checkpoint_interval_attempts=25,
        checkpoint_context=context,
    )

    assert _lineup_uids(resumed) == _lineup_uids(baseline)
    completed = CandidateCheckpointStore(checkpoint_path).load()
    assert completed is not None
    assert completed.status == "completed"
    assert len(completed.candidate_uids) == 120
    assert completed.write_count >= 4

    reused = service._generate_candidate_lineups_adaptive(
        players=players,
        requested_lineups=120,
        min_salary_floor=43000,
        rng=np.random.default_rng(123456),
        checkpoint_path=checkpoint_path,
        resume_from_checkpoint=True,
        checkpoint_interval_attempts=25,
        checkpoint_context=context,
        checkpoint_progress_callback=lambda _attempts, _count: pytest.fail(
            "completed checkpoint should not regenerate candidates"
        ),
    )
    assert _lineup_uids(reused) == _lineup_uids(baseline)


def test_candidate_checkpoint_rejects_changed_request(tmp_path) -> None:
    service = LineupLearningService(session=None)  # type: ignore[arg-type]
    players = _player_pool()
    checkpoint_path = tmp_path / "ultimate-candidates.sqlite3"
    service._generate_candidate_lineups_adaptive(
        players=players,
        requested_lineups=100,
        min_salary_floor=43000,
        rng=np.random.default_rng(42),
        checkpoint_path=checkpoint_path,
        checkpoint_interval_attempts=100,
        checkpoint_context={"season": 2025, "week": 18},
    )

    with pytest.raises(
        ValueError,
        match="does not match the current generation request or player pool",
    ):
        service._generate_candidate_lineups_adaptive(
            players=players,
            requested_lineups=101,
            min_salary_floor=43000,
            rng=np.random.default_rng(42),
            checkpoint_path=checkpoint_path,
            resume_from_checkpoint=True,
            checkpoint_interval_attempts=100,
            checkpoint_context={"season": 2025, "week": 18},
        )


def test_resume_request_requires_checkpoint_path() -> None:
    with pytest.raises(ValidationError, match="checkpoint_path is required"):
        UltimateLineupRequest(
            season=2025,
            week=18,
            resume_from_checkpoint=True,
        )
