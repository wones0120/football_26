from backend.app.services.lineup_learning import (
    SHOWDOWN_CAPTAIN_AVAILABILITY_FEATURE_NAMES,
    SHOWDOWN_CAPTAIN_BASE_FEATURE_NAMES,
    SHOWDOWN_CAPTAIN_CONTEXT_FEATURE_NAMES,
    LineupLearningService,
    ShowdownPlayerPoolRow,
)
from scripts.train_showdown_captain_archetype_model import (
    FEATURE_NAMES as TRAINING_FEATURE_NAMES,
    _build_features,
)


def _player(
    uid: str,
    position: str,
    team: str,
    *,
    injury_status: str,
    team_skill_out_count: int,
    team_position_out_count: int,
) -> ShowdownPlayerPoolRow:
    opponent = "NYG" if team == "DAL" else "DAL"
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
        game_total_line=48.0,
        team_spread_line=-2.0 if team == "DAL" else 2.0,
        team_implied_total=25.0 if team == "DAL" else 23.0,
        opponent_implied_total=23.0 if team == "DAL" else 25.0,
        player_injury_status=injury_status,
        team_skill_out_count=team_skill_out_count,
        team_position_out_count=team_position_out_count,
    )


def test_showdown_availability_features_match_training_and_scoring() -> None:
    pool = [
        _player(
            "dal_qb",
            "QB",
            "DAL",
            injury_status="active",
            team_skill_out_count=2,
            team_position_out_count=0,
        ),
        _player(
            "dal_rb",
            "RB",
            "DAL",
            injury_status="questionable",
            team_skill_out_count=2,
            team_position_out_count=1,
        ),
        _player(
            "dal_wr",
            "WR",
            "DAL",
            injury_status="active",
            team_skill_out_count=2,
            team_position_out_count=1,
        ),
        _player(
            "nyg_qb",
            "QB",
            "NYG",
            injury_status="unknown",
            team_skill_out_count=0,
            team_position_out_count=0,
        ),
        _player(
            "nyg_wr",
            "WR",
            "NYG",
            injury_status="out",
            team_skill_out_count=0,
            team_position_out_count=0,
        ),
        _player(
            "nyg_te",
            "TE",
            "NYG",
            injury_status="probable",
            team_skill_out_count=0,
            team_position_out_count=0,
        ),
    ]

    scoring_features = LineupLearningService(  # type: ignore[arg-type]
        session=None
    )._showdown_captain_context_features(pool)
    training_features = _build_features(pool)

    assert TRAINING_FEATURE_NAMES == SHOWDOWN_CAPTAIN_CONTEXT_FEATURE_NAMES
    assert not (
        set(SHOWDOWN_CAPTAIN_BASE_FEATURE_NAMES)
        & set(SHOWDOWN_CAPTAIN_AVAILABILITY_FEATURE_NAMES)
    )
    assert {
        name: training_features[name]
        for name in SHOWDOWN_CAPTAIN_CONTEXT_FEATURE_NAMES
    } == {
        name: scoring_features[name]
        for name in SHOWDOWN_CAPTAIN_CONTEXT_FEATURE_NAMES
    }
    assert scoring_features["max_team_skill_out_count"] == 2.0
    assert scoring_features["team_skill_out_count_diff"] == 2.0
    assert scoring_features["max_team_position_out_count"] == 1.0
    assert scoring_features["injury_report_coverage"] == 5.0 / 6.0
    assert scoring_features["questionable_or_worse_count"] == 2.0
    assert scoring_features["rb_position_out_max"] == 1.0
    assert scoring_features["wr_position_out_max"] == 1.0
    assert scoring_features["te_position_out_max"] == 0.0
    assert scoring_features["max_team_available_skill_count"] == 3.0
    assert scoring_features["team_available_skill_count_diff"] == 1.0
