from types import SimpleNamespace

import pytest

from scripts.run_model_001_ablation import (
    DstRecord,
    EFFICIENCY_FEATURES,
    HOLDOUT_START,
    MATCHUP_FEATURES,
    OFFENSE_BASELINE_FEATURES,
    OPPORTUNITY_FEATURES,
    ResearchRow,
    UsageRecord,
    _dst_features,
    _offense_features,
    evaluate_holdout,
    lock_hash,
    select_candidates,
    verify_lock,
)


def _usage(
    *,
    week: int,
    opportunity: float,
    carries: float = 0.0,
    targets: float = 0.0,
    share: float = 0.5,
) -> UsageRecord:
    return UsageRecord(
        season=2025,
        week=week,
        player_id="player-1",
        team="BUF",
        position="RB",
        dk_points=opportunity * 1.5,
        attempts=0.0,
        carries=carries,
        targets=targets,
        opportunity=opportunity,
        opportunity_share=share,
        carry_share=share,
        target_share=0.1,
    )


def test_offense_features_use_only_rows_before_target_week() -> None:
    matrix_row = SimpleNamespace(
        season=2025,
        week=3,
        position="RB",
        player_games_history=2,
        player_roll3_mean=12.0,
        player_roll8_mean=11.0,
        player_roll8_std=2.0,
        defense_pos_allowed_roll3=10.0,
        defense_pos_allowed_roll8=9.0,
        defense_pos_allowed_p90_roll8=18.0,
    )
    history = [
        _usage(week=1, opportunity=10.0, carries=8.0, targets=2.0),
        _usage(week=2, opportunity=20.0, carries=15.0, targets=5.0, share=0.7),
        _usage(week=3, opportunity=1000.0, carries=1000.0),
    ]

    features, role = _offense_features(matrix_row, history)

    assert features["opportunity_roll3"] == 15.0
    assert features["opportunity_roll8"] == 15.0
    assert features["efficiency_roll3"] == 1.5
    assert role == "LEAD"


def test_dst_features_use_prior_defense_and_opponent_history_only() -> None:
    matrix_row = SimpleNamespace(
        season=2025,
        week=3,
        team="BUF",
        opponent="MIA",
    )
    rows = [
        DstRecord(2025, 1, "BUF", "NYJ", 8.0, 3.0, 1.0, 1.0, 0.0, 4.0),
        DstRecord(2025, 2, "NE", "MIA", 6.0, 2.0, 0.0, 1.0, 0.0, 1.0),
        DstRecord(2025, 3, "BUF", "MIA", 40.0, 10.0, 4.0, 3.0, 2.0, 10.0),
    ]

    features = _dst_features(matrix_row, rows)

    assert features["dst_points_roll8"] == 8.0
    assert features["dst_sacks_roll8"] == 3.0
    assert features["opponent_dst_points_allowed_roll8"] == 6.0


def _synthetic_rows() -> list[ResearchRow]:
    rows: list[ResearchRow] = []
    positions = ("QB", "RB", "WR", "TE", "DST")
    for position in positions:
        for index in range(160):
            if index < 110:
                season, week = 2025, 7
            elif index < 135:
                season, week = 2025, 8
            else:
                season, week = HOLDOUT_START
            signal = float((index % 10) + 1)
            features = {
                name: 0.0
                for name in (
                    OFFENSE_BASELINE_FEATURES
                    + OPPORTUNITY_FEATURES
                    + EFFICIENCY_FEATURES
                    + MATCHUP_FEATURES
                )
            }
            features.update(
                {
                    "dst_points_roll8": 0.0,
                    "dst_sacks_roll8": 0.0,
                    "dst_takeaways_roll8": 0.0,
                    "dst_touchdowns_roll8": 0.0,
                    "dst_points_allowed_score_roll8": 0.0,
                    "opponent_dst_points_allowed_roll8": 0.0,
                    "opponent_sacks_allowed_roll8": 0.0,
                    "opponent_takeaways_allowed_roll8": 0.0,
                    "opponent_dst_touchdowns_allowed_roll8": 0.0,
                }
            )
            if position == "DST":
                features["dst_sacks_roll8"] = signal
                actual = 2.0 * signal
                role = "DEFENSE"
            else:
                features["opportunity_roll3"] = signal
                actual = 2.0 * signal
                role = {
                    "QB": "POCKET",
                    "RB": "LEAD",
                    "WR": "PRIMARY",
                    "TE": "SECONDARY",
                }[position]
            rows.append(
                ResearchRow(
                    season=season,
                    week=week,
                    player_id=f"{position}-{index}",
                    position=position,
                    role=role,
                    actual_points=actual,
                    features=features,
                )
            )
    return rows


def test_candidate_lock_is_selected_without_holdout_metrics_and_is_tamper_evident() -> None:
    candidate_lock = select_candidates(_synthetic_rows())

    assert candidate_lock["windows"]["holdout"]["metrics_read_during_selection"] is False
    assert candidate_lock["selections"]["RB"]["selected"] == "history_plus_opportunity"
    assert candidate_lock["selections"]["DST"]["selected"] == "dst_defense_form"
    assert candidate_lock["lock_hash"] == lock_hash(candidate_lock)

    tampered = dict(candidate_lock)
    tampered["ridge_alpha"] = 99.0
    with pytest.raises(ValueError, match="hash"):
        verify_lock(tampered)


def test_locked_candidates_are_evaluated_by_position_and_role() -> None:
    rows = _synthetic_rows()
    candidate_lock = select_candidates(rows)

    evidence = evaluate_holdout(rows, candidate_lock)

    assert evidence["status"] == "accepted"
    assert evidence["promotion_eligible"] is False
    assert evidence["overall"]["candidate"]["mae"] < evidence["overall"]["baseline"]["mae"]
    assert evidence["positions"]["RB"]["roles"]["LEAD"]["rows"] >= 5
    assert all(evidence["gates"].values())
