from __future__ import annotations

import sys
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.app.models import (
    Base,
    CuratedPlayerGameParticipation,
    IngestRun,
    RawNflSchedule,
    RawNflSnapCount,
    RawNflWeeklyRoster,
    TeamGameAvailabilityFeature,
)
from backend.app.schemas import NflReadPySeasonRequest
from backend.app.services.ingest import IngestService
from backend.app.services.lineup_learning import (
    PLAYER_MATCHUP_MODEL_FEATURE_NAMES,
    LineupLearningService,
)
from backend.app.services.participation import (
    build_lagged_availability_rows,
    infer_participation_status,
)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, future=True)()


def test_participation_status_requires_positive_evidence_for_dnp() -> None:
    assert infer_participation_status(
        total_snaps=0,
        box_score_activity=False,
        roster_status="ACT",
        team_has_snap_coverage=False,
    ) == ("unknown", "no_participation_evidence")
    assert infer_participation_status(
        total_snaps=0,
        box_score_activity=False,
        roster_status="INA",
        team_has_snap_coverage=False,
    ) == ("did_not_play", "inactive_roster_status")
    assert infer_participation_status(
        total_snaps=12,
        box_score_activity=False,
        roster_status="ACT",
        team_has_snap_coverage=True,
    ) == ("played_confirmed", "snap_count")


def test_availability_features_shift_both_teams_forward_one_game() -> None:
    schedule_rows = [
        {
            "season": 2025,
            "week": week,
            "game_id": f"game-{week}",
            "team": team,
            "opponent": opponent,
        }
        for week in (1, 2, 3)
        for team, opponent in (("AAA", "BBB"), ("BBB", "AAA"))
    ]
    participation_rows = [
        {
            "season": 2025,
            "week": week,
            "game_id": f"game-{week}",
            "player_master_id": "offense-a",
            "team": "AAA",
            "participation_status": "played_confirmed" if week == 1 else "did_not_play",
            "offense_snap_share": 0.80 if week == 1 else 0.0,
            "defense_snap_share": 0.0,
        }
        for week in (1, 2)
    ] + [
        {
            "season": 2025,
            "week": week,
            "game_id": f"game-{week}",
            "player_master_id": "defense-b",
            "team": "BBB",
            "participation_status": "played_confirmed" if week == 1 else "did_not_play",
            "offense_snap_share": 0.0,
            "defense_snap_share": 0.70 if week == 1 else 0.0,
        }
        for week in (1, 2)
    ]

    features = build_lagged_availability_rows(participation_rows, schedule_rows)
    by_week_team = {(row["week"], row["team"]): row for row in features}

    # Week 2 cannot see its own DNP outcomes.
    assert by_week_team[(2, "AAA")]["team_offense_missing_share_lag1"] == 0.0
    assert by_week_team[(2, "AAA")]["opponent_defense_missing_share_lag1"] == 0.0
    # Week 3 receives only the losses observed in Week 2, including the opponent side.
    assert by_week_team[(3, "AAA")]["team_offense_missing_share_lag1"] == pytest.approx(0.80)
    assert by_week_team[(3, "AAA")]["opponent_defense_missing_share_lag1"] == pytest.approx(0.70)
    assert by_week_team[(3, "AAA")]["team_source_week"] == 2
    assert by_week_team[(3, "AAA")]["opponent_source_week"] == 2


def test_availability_signals_are_wired_into_matchup_model_vector() -> None:
    vector = LineupLearningService(session=None)._player_matchup_feature_vector_from_values(  # type: ignore[arg-type]
        salary=6000,
        is_home=True,
        game_total_line=48.0,
        team_spread_line=-2.0,
        team_implied_total=25.0,
        opponent_implied_total=23.0,
        player_games_history=8,
        player_roll3_mean=15.0,
        player_roll8_mean=13.0,
        player_roll8_std=4.0,
        player_vs_opp_roll4=14.0,
        defense_pos_allowed_roll3=16.0,
        defense_pos_allowed_roll8=15.0,
        defense_pos_allowed_p90_roll8=24.0,
        player_injury_status="active",
        team_skill_out_count=1,
        team_position_out_count=1,
        team_offense_missing_share_lag1=0.20,
        team_defense_missing_share_lag1=0.30,
        opponent_offense_missing_share_lag1=0.40,
        opponent_defense_missing_share_lag1=0.50,
        kickoff_bucket="early",
    )

    by_name = dict(zip(PLAYER_MATCHUP_MODEL_FEATURE_NAMES, vector, strict=True))
    assert by_name["team_offense_missing_share_lag1"] == pytest.approx(0.20)
    assert by_name["team_defense_missing_share_lag1"] == pytest.approx(0.30)
    assert by_name["opponent_offense_missing_share_lag1"] == pytest.approx(0.40)
    assert by_name["opponent_defense_missing_share_lag1"] == pytest.approx(0.50)


def test_nflreadpy_roster_and_snap_ingest_builds_standard_layers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session()
    schedule_run = IngestRun(
        ingest_run_id="schedule-run",
        source_system="nflreadpy",
        source_table="nfl_schedule",
        status="completed",
    )
    session.add(schedule_run)
    for week in (1, 2, 3):
        session.add(
            RawNflSchedule(
                ingest_run_id=schedule_run.ingest_run_id,
                source_system="nflreadpy",
                season=2025,
                week=week,
                game_id=f"game-{week}",
                home_team="AAA",
                away_team="BBB",
                game_type="REG",
                raw_row_json={"game_type": "REG"},
            )
        )
    session.commit()

    roster_rows = []
    players = (
        ("Offense A", "aaa-off", "pfr-aaa-off", "AAA", "WR"),
        ("Backup A", "aaa-backup", "pfr-aaa-backup", "AAA", "WR"),
        ("Defense B", "bbb-def", "pfr-bbb-def", "BBB", "LB"),
        ("Backup B", "bbb-backup", "pfr-bbb-backup", "BBB", "LB"),
    )
    for week in (1, 2, 3):
        for name, gsis_id, pfr_id, team, position in players:
            inactive = week == 2 and name in {"Offense A", "Defense B"}
            roster_rows.append(
                {
                    "season": 2025,
                    "week": week,
                    "game_type": "REG",
                    "full_name": name,
                    "team": team,
                    "position": position,
                    "depth_chart_position": position,
                    "status": "INA" if inactive else "ACT",
                    "gsis_id": gsis_id,
                    "pfr_id": pfr_id,
                }
            )
    snap_rows = [
        {
            "season": 2025,
            "week": 1,
            "game_type": "REG",
            "game_id": "game-1",
            "pfr_game_id": "pfr-game-1",
            "pfr_player_id": pfr_id,
            "player": name,
            "team": team,
            "opponent": "BBB" if team == "AAA" else "AAA",
            "position": position,
            "offense_snaps": 50 if name == "Offense A" else 10 if team == "AAA" else 0,
            "offense_pct": 0.80 if name == "Offense A" else 0.20 if team == "AAA" else 0.0,
            "defense_snaps": 45 if name == "Defense B" else 15 if team == "BBB" else 0,
            "defense_pct": 0.70 if name == "Defense B" else 0.30 if team == "BBB" else 0.0,
            "st_snaps": 0,
            "st_pct": 0.0,
        }
        for name, _gsis_id, pfr_id, team, position in players
    ] + [
        {
            "season": 2025,
            "week": 2,
            "game_type": "REG",
            "game_id": "game-2",
            "pfr_game_id": "pfr-game-2",
            "pfr_player_id": pfr_id,
            "player": name,
            "team": team,
            "opponent": "BBB" if team == "AAA" else "AAA",
            "position": position,
            "offense_snaps": 60 if team == "AAA" else 0,
            "offense_pct": 1.0 if team == "AAA" else 0.0,
            "defense_snaps": 60 if team == "BBB" else 0,
            "defense_pct": 1.0 if team == "BBB" else 0.0,
            "st_snaps": 0,
            "st_pct": 0.0,
        }
        for name, _gsis_id, pfr_id, team, position in players
        if name in {"Backup A", "Backup B"}
    ]
    fake_nflreadpy = SimpleNamespace(
        load_rosters_weekly=lambda seasons: pd.DataFrame(roster_rows),
        load_snap_counts=lambda seasons: pd.DataFrame(snap_rows),
    )
    monkeypatch.setitem(sys.modules, "nflreadpy", fake_nflreadpy)

    service = IngestService(session)
    roster_result = service.ingest_nflreadpy_weekly_rosters(
        NflReadPySeasonRequest(season=2025)
    )
    snap_result = service.ingest_nflreadpy_snap_counts(
        NflReadPySeasonRequest(season=2025)
    )

    assert roster_result.status == "completed"
    assert snap_result.status == "completed"
    assert session.query(RawNflWeeklyRoster).count() == len(roster_rows)
    assert session.query(RawNflSnapCount).count() == len(snap_rows)
    dnp_rows = session.query(CuratedPlayerGameParticipation).filter_by(
        season=2025,
        week=2,
        participation_status="did_not_play",
    ).all()
    assert {row.player_name for row in dnp_rows} == {"Offense A", "Defense B"}
    week_three_aaa = session.query(TeamGameAvailabilityFeature).filter_by(
        season=2025,
        week=3,
        team="AAA",
    ).one()
    assert week_three_aaa.team_offense_missing_share_lag1 == pytest.approx(0.80)
    assert week_three_aaa.opponent_defense_missing_share_lag1 == pytest.approx(0.70)
    assert week_three_aaa.team_source_week == 2
    assert week_three_aaa.opponent_source_week == 2

    # Reingestion versions Bronze while Silver remains a single deterministic view.
    second_roster_result = service.ingest_nflreadpy_weekly_rosters(
        NflReadPySeasonRequest(season=2025)
    )
    assert second_roster_result.status == "completed"
    assert session.query(RawNflWeeklyRoster).count() == 2 * len(roster_rows)
    assert session.query(CuratedPlayerGameParticipation).count() == 12
