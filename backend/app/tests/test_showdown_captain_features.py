import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import (
    Base,
    CuratedSalary,
    IngestRun,
    PlayerAlias,
    PlayerMaster,
    RawNflWeeklyStat,
)
from backend.app.services.lineup_learning import (
    SHOWDOWN_CAPTAIN_AVAILABILITY_FEATURE_NAMES,
    SHOWDOWN_CAPTAIN_BASE_FEATURE_NAMES,
    SHOWDOWN_CAPTAIN_CONTINUITY_FEATURE_NAMES,
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
    team_missing_usage_share: float = 0.0,
    team_available_usage_concentration: float = 0.0,
    team_usage_identity_coverage: float = 0.0,
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
        team_missing_usage_share=team_missing_usage_share,
        team_available_usage_concentration=team_available_usage_concentration,
        team_usage_identity_coverage=team_usage_identity_coverage,
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
            team_missing_usage_share=0.30,
            team_available_usage_concentration=0.62,
            team_usage_identity_coverage=0.90,
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
            team_missing_usage_share=0.10,
            team_available_usage_concentration=0.40,
            team_usage_identity_coverage=0.80,
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
    assert not (
        set(SHOWDOWN_CAPTAIN_BASE_FEATURE_NAMES)
        & set(SHOWDOWN_CAPTAIN_CONTINUITY_FEATURE_NAMES)
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
    assert scoring_features["max_team_missing_usage_share"] == 0.30
    assert scoring_features["team_missing_usage_share_diff"] == pytest.approx(0.20)
    assert scoring_features["max_team_available_usage_concentration"] == 0.62
    assert scoring_features["team_available_usage_concentration_diff"] == pytest.approx(0.22)
    assert scoring_features["min_team_usage_identity_coverage"] == 0.80


def test_showdown_usage_continuity_counts_unresolved_salary_players_in_coverage() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session: Session = factory()
    try:
        session.add(
            IngestRun(
                ingest_run_id="stats-run",
                source_system="nflreadpy",
                source_table="weekly_stats",
                status="completed",
            )
        )
        session.add(
            PlayerMaster(
                player_master_id="mapped-player",
                full_name="Mapped Player",
                normalized_name="mapped player",
                primary_team="DAL",
                position="RB",
            )
        )
        session.add(
            PlayerAlias(
                player_master_id="mapped-player",
                source_system="nflreadpy",
                source_key="nfl-mapped",
                alias_name="Mapped Player",
                normalized_alias="mapped player",
                team="DAL",
                position="RB",
            )
        )
        session.add_all(
            [
                RawNflWeeklyStat(
                    ingest_run_id="stats-run",
                    source_system="nflreadpy",
                    season=2025,
                    week=4,
                    player_id="nfl-mapped",
                    player_name="Mapped Player",
                    team="DAL",
                    position="RB",
                    raw_row_json={"carries": 8, "targets": 0},
                ),
                RawNflWeeklyStat(
                    ingest_run_id="stats-run",
                    source_system="nflreadpy",
                    season=2025,
                    week=4,
                    player_id="nfl-missing",
                    player_name="Missing Player",
                    team="DAL",
                    position="WR",
                    raw_row_json={"carries": 0, "targets": 2},
                ),
                RawNflWeeklyStat(
                    ingest_run_id="stats-run",
                    source_system="nflreadpy",
                    season=2025,
                    week=5,
                    player_id="future-player",
                    player_name="Future Player",
                    team="DAL",
                    position="WR",
                    raw_row_json={"carries": 0, "targets": 100},
                ),
            ]
        )
        session.commit()

        salary_rows = [
            CuratedSalary(
                source_system="draftkings",
                season=2025,
                week=5,
                slate="DAL-NYG",
                source_player_key="dk-mapped",
                player_master_id="mapped-player",
                player_name="Mapped Player",
                normalized_name="mapped player",
                team="DAL",
                position="RB",
                roster_position="FLEX",
                salary=8000,
            ),
            CuratedSalary(
                source_system="draftkings",
                season=2025,
                week=5,
                slate="DAL-NYG",
                source_player_key="dk-unresolved",
                player_name="Unresolved Player",
                normalized_name="unresolved player",
                team="DAL",
                position="WR",
                roster_position="FLEX",
                salary=6000,
            ),
        ]

        continuity = LineupLearningService(session)._showdown_usage_continuity(
            source_system="draftkings",
            season=2025,
            week=5,
            slate="DAL-NYG",
            salary_rows=salary_rows,
        )
    finally:
        session.close()

    assert continuity["DAL"]["identity_coverage"] == 0.5
    assert continuity["DAL"]["missing_usage_share"] == pytest.approx(0.2)
    assert continuity["DAL"]["available_usage_concentration"] == 1.0
