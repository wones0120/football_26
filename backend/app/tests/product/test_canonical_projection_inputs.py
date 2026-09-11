from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd
import pytest
from sqlalchemy import create_engine

from backend.app.models import CuratedSalary, PlayerGameFeatureMatrix
from backend.app.product_services.canonical_projection_inputs import (
    FEATURE_COLUMNS,
    POSITION_FEATURE_COLUMNS,
    add_position_features,
    apply_pregame_projection_context,
    attach_lagged_opportunity_features,
    prepare_inputs,
)
from backend.app.product_services.predictions import (
    PredictionsService,
    TARGET_COL,
    derive_calibration_roles,
)


CUTOFF = datetime(2026, 9, 6, 13, tzinfo=timezone.utc)


def inputs():
    base = dict.fromkeys(FEATURE_COLUMNS, 1.0)
    base.update(source_system="draftkings", player_master_id="canonical-1", player_id="source-1",
                player_name="Same Name", team="A", opponent="B", position="WR", dk_points=20.0,
                slate="NIGHT", game_id="game", created_at="2026-09-06T12:00:00Z")
    matrix = pd.DataFrame([
        {**base, "season": 2025, "week": 18, "player_game_feature_matrix_id": 1},
        {**base, "season": 2026, "week": 1, "player_game_feature_matrix_id": 2, "dk_points": 99999},
        {**base, "season": 2026, "week": 2, "player_game_feature_matrix_id": 3, "dk_points": 99999},
    ])
    salary = dict(source_system="draftkings", season=2026, week=1, slate="NIGHT",
                  player_master_id="canonical-1", source_player_key="dk-flex", position="WR",
                  roster_position="FLEX", salary=5000, player_name="Same Name", team="A",
                  opponent="B", created_at="2026-09-06T12:00:00Z", curated_salary_id=1,
                  ingest_run_id="ingest-1")
    salaries = pd.DataFrame([salary, {**salary, "roster_position": "CPT", "salary": 7500,
                                    "curated_salary_id": 2, "source_player_key": "dk-cpt"}])
    return matrix, salaries


def prepare(matrix, salaries, **kwargs):
    return prepare_inputs(matrix, salaries, season=2026, week=1, slate="night", cutoff=CUTOFF, **kwargs)


def test_cutoff_identity_deduplication_and_label_allowlist():
    matrix, salaries = inputs()
    train, target, metadata = prepare(matrix, salaries)
    assert train[TARGET_COL].tolist() == [20.0]
    assert target[TARGET_COL].isna().all()
    assert target["player_id"].tolist() == ["canonical-1"]
    assert target["salary"].tolist() == [5000]
    assert not {"dk_points", TARGET_COL, "player_game_feature_matrix_id"} & set(FEATURE_COLUMNS)
    assert metadata["salary_row_ids"] == [1]
    assert target["position_wr"].tolist() == [1.0]
    assert target[POSITION_FEATURE_COLUMNS].sum(axis=1).tolist() == [1.0]


def test_all_supported_positions_receive_exactly_one_model_indicator():
    positions = ["QB", "RB", "WR", "TE", "K", "DST"]

    rows = add_position_features(pd.DataFrame({"position": positions}))

    assert rows[POSITION_FEATURE_COLUMNS].sum(axis=1).tolist() == [1.0] * 6
    for index, position in enumerate(positions):
        assert rows.iloc[index][f"position_{position.lower()}"] == 1.0


def test_week_one_opportunity_features_carry_prior_season_forward_only():
    matrix = pd.DataFrame(
        [
            {
                "season": 2026,
                "week": 1,
                "player_master_id": "runner-1",
                "team": "SEA",
            }
        ]
    )
    weekly_stats = pd.DataFrame(
        [
            {
                "season": 2025,
                "week": 17,
                "player_master_id": "runner-1",
                "team": "SEA",
                "position": "RB",
                "carries": 8,
                "targets": 2,
                "created_at": "2026-09-06T11:00:00Z",
                "raw_nfl_weekly_stat_id": 1,
            },
            {
                "season": 2025,
                "week": 18,
                "player_master_id": "runner-1",
                "team": "SEA",
                "position": "RB",
                "carries": 12,
                "targets": 4,
                "created_at": "2026-09-06T11:00:00Z",
                "raw_nfl_weekly_stat_id": 2,
            },
            {
                "season": 2026,
                "week": 1,
                "player_master_id": "runner-1",
                "team": "SEA",
                "position": "RB",
                "carries": 99,
                "targets": 99,
                "created_at": "2026-09-06T11:00:00Z",
                "raw_nfl_weekly_stat_id": 3,
            },
            {
                "season": 2025,
                "week": 17,
                "player_master_id": "departed-runner",
                "team": "SEA",
                "position": "RB",
                "carries": 10,
                "targets": 1,
                "created_at": "2026-09-06T11:00:00Z",
                "raw_nfl_weekly_stat_id": 4,
            },
            {
                "season": 2025,
                "week": 18,
                "player_master_id": "departed-runner",
                "team": "SEA",
                "position": "RB",
                "carries": 8,
                "targets": 2,
                "created_at": "2026-09-06T11:00:00Z",
                "raw_nfl_weekly_stat_id": 5,
            },
        ]
    )

    rows, metrics = attach_lagged_opportunity_features(
        matrix,
        weekly_stats,
        cutoff=pd.Timestamp(CUTOFF),
    )

    assert rows["carries_mean_3"].tolist() == [10.0]
    assert rows["targets_mean_3"].tolist() == [3.0]
    assert rows["team_carries_mean_3"].tolist() == [19.0]
    assert rows["team_targets_mean_3"].tolist() == [4.5]
    assert metrics["rows_with_lagged_carries"] == 1
    assert metrics["rows_with_lagged_team_carries"] == 1


def test_pregame_context_zeros_backup_qb_and_redistributes_team_opportunity():
    target = pd.DataFrame(
        [
            {
                "player_id": "qb-start",
                "position": "QB",
                "recent_team": "SEA",
                "salary": 10000,
                "player_games_history": 20,
                "snap_share_mean_3": 1.0,
                "carry_share_mean_3": 0.0,
                "target_share_mean_3": 0.0,
                "carries_mean_3": 3.0,
                "targets_mean_3": 0.0,
            },
            {
                "player_id": "qb-backup",
                "position": "QB",
                "recent_team": "SEA",
                "salary": 6000,
                "player_games_history": 10,
                "snap_share_mean_3": 0.5,
                "carry_share_mean_3": 0.0,
                "target_share_mean_3": 0.0,
                "carries_mean_3": 2.0,
                "targets_mean_3": 0.0,
            },
            {
                "player_id": "rb-veteran",
                "position": "RB",
                "recent_team": "SEA",
                "salary": 7000,
                "player_games_history": 20,
                "snap_share_mean_3": 0.6,
                "carry_share_mean_3": 0.75,
                "target_share_mean_3": 0.15,
                "carries_mean_3": 15.0,
                "targets_mean_3": 3.0,
                "team_carries_mean_3": 24.0,
                "team_targets_mean_3": 5.0,
            },
            {
                "player_id": "rb-rookie",
                "position": "RB",
                "recent_team": "SEA",
                "salary": 5000,
                "player_games_history": 0,
                "snap_share_mean_3": 0.0,
                "carry_share_mean_3": 0.0,
                "target_share_mean_3": 0.0,
                "carries_mean_3": 0.0,
                "targets_mean_3": 0.0,
                "team_carries_mean_3": 24.0,
                "team_targets_mean_3": 5.0,
            },
        ]
    )
    starting_qbs = pd.DataFrame(
        [
            {
                "team": "SEA",
                "player_master_id": "qb-start",
                "source": "draftkings_unique_top_salary",
                "evidence_tier": "inferred",
            }
        ]
    )
    context = pd.DataFrame(
        [
            {
                "player_master_id": "rb-veteran",
                "availability_probability": 0.0,
                "expected_snaps": 12.0,
                "expected_carries": 4.0,
                "red_zone_share": 0.20,
                "injury_status": "OUT",
                "evidence_json": {
                    "role_uncertain": True,
                    "newly_assigned_role": True,
                    "depth_chart_conflict": True,
                },
                "context_run_id": "context-1",
                "pregame_player_context_id": 1,
                "source": "practice-report",
                "observed_at": CUTOFF,
            }
        ]
    )

    rows, metrics = apply_pregame_projection_context(
        target,
        starting_qbs=starting_qbs,
        pregame_context=context,
    )
    by_id = rows.set_index("player_id")

    assert by_id.loc["qb-start", "pregame_start_probability"] == 1.0
    assert by_id.loc["qb-backup", "pregame_start_probability"] == 0.0
    assert by_id.loc["rb-veteran", "carry_share_mean_3"] == 0.0
    assert by_id.loc["rb-rookie", "carry_share_mean_3"] == 1.0
    assert by_id.loc["rb-rookie", "carries_mean_3"] == 24.0
    assert by_id.loc["rb-rookie", "target_share_mean_3"] == 1.0
    assert by_id.loc["rb-veteran", "pregame_expected_snaps"] == 12.0
    assert by_id.loc["rb-veteran", "pregame_expected_carries"] == 4.0
    assert by_id.loc["rb-veteran", "pregame_red_zone_share"] == 0.20
    assert by_id.loc["rb-veteran", "pregame_injury_status"] == "OUT"
    assert bool(by_id.loc["rb-veteran", "pregame_role_uncertain"]) is True
    assert bool(by_id.loc["rb-veteran", "pregame_newly_assigned_role"]) is True
    assert bool(by_id.loc["rb-veteran", "pregame_depth_chart_conflict"]) is True
    assert metrics["allocations"][0]["team_volume_source"] == "lagged_full_team_volume"
    assert metrics["context_run_ids"] == ["context-1"]


def test_multiple_active_qbs_require_starting_evidence():
    target = pd.DataFrame(
        [
            {
                "player_id": player_id,
                "position": "QB",
                "recent_team": "SEA",
                "salary": salary,
                "player_games_history": 10,
                "snap_share_mean_3": 0.5,
                "carry_share_mean_3": 0.0,
                "target_share_mean_3": 0.0,
                "carries_mean_3": 2.0,
                "targets_mean_3": 0.0,
            }
            for player_id, salary in (("qb-1", 10000), ("qb-2", 6000))
        ]
    )

    with pytest.raises(ValueError, match="Starting-QB evidence is required"):
        apply_pregame_projection_context(target)


def test_effective_context_shares_cannot_exceed_one_across_runs():
    target = pd.DataFrame(
        [
            {
                "player_id": player_id,
                "position": "WR",
                "recent_team": "SEA",
                "salary": salary,
                "player_games_history": 10,
                "snap_share_mean_3": 0.5,
                "carry_share_mean_3": 0.0,
                "target_share_mean_3": 0.5,
                "carries_mean_3": 0.0,
                "targets_mean_3": 5.0,
            }
            for player_id, salary in (("wr-1", 10000), ("wr-2", 8000))
        ]
    )
    context = pd.DataFrame(
        [
            {
                "player_master_id": "wr-1",
                "target_share": 0.60,
                "context_run_id": "context-1",
            },
            {
                "player_master_id": "wr-2",
                "target_share": 0.50,
                "context_run_id": "context-2",
            },
        ]
    )

    with pytest.raises(ValueError, match="Effective target share exceeds 1.0"):
        apply_pregame_projection_context(target, pregame_context=context)


def test_historical_nonparticipants_are_excluded_and_snap_share_is_prior_only():
    matrix, salaries = inputs()
    prior = {
        **matrix.iloc[0].to_dict(),
        "season": 2025,
        "week": 17,
        "dk_points": 12.0,
        "player_game_feature_matrix_id": 4,
    }
    matrix = pd.concat([matrix, pd.DataFrame([prior])], ignore_index=True)
    participation = pd.DataFrame(
        [
            {
                "season": 2025,
                "week": 17,
                "player_master_id": "canonical-1",
                "participation_status": "played_confirmed",
                "offense_snap_share": 0.90,
                "created_at": "2026-09-06T11:00:00Z",
                "curated_player_game_participation_id": 1,
            },
            {
                "season": 2025,
                "week": 18,
                "player_master_id": "canonical-1",
                "participation_status": "did_not_play",
                "offense_snap_share": None,
                "created_at": "2026-09-06T11:00:00Z",
                "curated_player_game_participation_id": 2,
            },
            {
                "season": 2026,
                "week": 1,
                "player_master_id": "canonical-1",
                "participation_status": "unknown",
                "offense_snap_share": 0.01,
                "created_at": "2026-09-06T11:00:00Z",
                "curated_player_game_participation_id": 3,
            },
        ]
    )

    train, target, metadata = prepare(
        matrix,
        salaries,
        participation=participation,
    )

    assert train[["season", "week", TARGET_COL]].to_dict(orient="records") == [
        {"season": 2025, "week": 17, TARGET_COL: 12.0}
    ]
    assert target["snap_share_mean_3"].tolist() == [0.90]
    assert derive_calibration_roles(target).tolist() == ["PRIMARY"]
    assert metadata["participation_filter"]["training_rows_before_filter"] == 2
    assert metadata["participation_filter"]["training_rows_after_filter"] == 1
    assert metadata["participation_filter"]["excluded_training_rows"] == 1


def test_missing_canonical_identity_never_matches_by_name_or_broadens_slate():
    matrix, salaries = inputs()
    salaries["player_master_id"] = "different-canonical-id"
    with pytest.raises(ValueError, match="Missing canonical features"):
        prepare(matrix, salaries)
    salaries["slate"] = "OTHER"
    with pytest.raises(ValueError, match="No canonical salaries"):
        prepare(matrix, salaries)


def test_late_inputs_rejected_and_exclusions_recorded():
    matrix, salaries = inputs()
    late = {**salaries.iloc[0].to_dict(), "curated_salary_id": 3, "salary": 9999,
            "created_at": "2026-09-06T14:00:00Z"}
    unknown = {**salaries.iloc[0].to_dict(), "curated_salary_id": 4,
               "player_master_id": None, "source_player_key": "unresolved"}
    unsupported = {**salaries.iloc[0].to_dict(), "curated_salary_id": 5, "position": "P"}
    _, target, metadata = prepare(matrix, pd.concat([salaries, pd.DataFrame([late, unknown, unsupported])]))
    assert target["salary"].tolist() == [5000]
    assert metadata["unresolved_salary_source_keys"] == ["unresolved"]
    assert metadata["excluded_positions"] == ["P"]
    matrix.loc[matrix["season"] == 2026, "created_at"] = "2026-09-06T14:00:00Z"
    with pytest.raises(ValueError, match="Missing canonical features"):
        prepare(matrix, salaries)


def test_unavailable_salary_statuses_are_excluded_and_recorded_in_lineage():
    matrix, salaries = inputs()
    unavailable_matrix = matrix.copy()
    unavailable_matrix["player_master_id"] = "canonical-out"
    unavailable_matrix["player_id"] = "source-out"
    unavailable_matrix["player_name"] = "Unavailable Receiver"
    unavailable_matrix["player_game_feature_matrix_id"] += 10
    matrix = pd.concat([matrix, unavailable_matrix], ignore_index=True)

    unavailable_salaries = salaries.copy()
    unavailable_salaries["player_master_id"] = "canonical-out"
    unavailable_salaries["source_player_key"] = ["dk-out-flex", "dk-out-cpt"]
    unavailable_salaries["player_name"] = "Unavailable Receiver"
    unavailable_salaries["player_status"] = "OUT"
    unavailable_salaries["curated_salary_id"] += 10
    salaries["player_status"] = None

    _, target, metadata = prepare(
        matrix,
        pd.concat([salaries, unavailable_salaries], ignore_index=True),
    )

    assert target["player_id"].tolist() == ["canonical-1"]
    status_policy = metadata["salary_status_policy"]
    assert status_policy["excluded_player_count"] == 1
    assert status_policy["excluded_row_count"] == 2
    assert status_policy["excluded_players"] == [
        {
            "player_master_id": "canonical-out",
            "player_name": "Unavailable Receiver",
            "team": "A",
            "position": "WR",
            "status": "OUT",
            "ingest_run_id": "ingest-1",
        }
    ]


def test_current_roster_ineligible_players_are_not_scored():
    matrix, salaries = inputs()
    development_matrix = matrix.copy()
    development_matrix["player_master_id"] = "canonical-dev"
    development_matrix["player_id"] = "source-dev"
    development_matrix["player_name"] = "Development Receiver"
    development_matrix["player_game_feature_matrix_id"] += 20
    matrix = pd.concat([matrix, development_matrix], ignore_index=True)

    development_salaries = salaries.copy()
    development_salaries["player_master_id"] = "canonical-dev"
    development_salaries["source_player_key"] = ["dk-dev-flex", "dk-dev-cpt"]
    development_salaries["player_name"] = "Development Receiver"
    development_salaries["curated_salary_id"] += 20
    participation = pd.DataFrame(
        [
            {
                "season": 2025,
                "week": 18,
                "player_master_id": player_id,
                "team": "A",
                "roster_status": "ACT",
                "participation_status": "played_confirmed",
                "offense_snap_share": 0.75,
                "created_at": "2026-09-06T11:00:00Z",
                "curated_player_game_participation_id": row_id,
            }
            for player_id, row_id in (
                ("canonical-1", 1),
                ("canonical-dev", 2),
            )
        ]
        + [
            {
                "season": 2026,
                "week": 1,
                "player_master_id": "canonical-1",
                "team": "A",
                "roster_status": "ACT",
                "participation_status": "unknown",
                "offense_snap_share": None,
                "created_at": "2026-09-06T11:00:00Z",
                "curated_player_game_participation_id": 3,
            },
            {
                "season": 2026,
                "week": 1,
                "player_master_id": "canonical-dev",
                "team": "A",
                "roster_status": "DEV",
                "participation_status": "unknown",
                "offense_snap_share": None,
                "created_at": "2026-09-06T11:00:00Z",
                "curated_player_game_participation_id": 4,
            },
        ]
    )

    _, target, metadata = prepare(
        matrix,
        pd.concat([salaries, development_salaries], ignore_index=True),
        participation=participation,
    )

    assert target["player_id"].tolist() == ["canonical-1"]
    roster_policy = metadata["roster_eligibility_policy"]
    assert roster_policy["available"] is True
    assert roster_policy["excluded_player_count"] == 1
    assert roster_policy["excluded_row_count"] == 2
    assert roster_policy["excluded_players"][0]["roster_status"] == "DEV"


def test_canonical_prediction_runs_without_any_legacy_tables(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'canonical.sqlite'}")
    matrix, salaries = inputs()
    # Use SQL tables with the real column contracts, but no legacy products.
    for frame, model in ((matrix, PlayerGameFeatureMatrix), (salaries, CuratedSalary)):
        frame["created_at"] = pd.to_datetime(frame["created_at"], utc=True).dt.tz_localize(None)
        for column in model.__table__.columns:
            if column.name not in frame:
                frame[column.name] = None
    matrix.to_sql(PlayerGameFeatureMatrix.__tablename__, engine, index=False)
    salaries.to_sql(CuratedSalary.__tablename__, engine, index=False)
    service = PredictionsService(str(engine.url))
    with patch.object(service, "_persist_target_prediction_run", return_value=True) as persist:
        result = service.train_and_predict(season=2026, week=1, slate="night", data_cutoff_at=CUTOFF)
    assert len(result.records) == 1
    assert result.target_persisted
    assert result.records[0].player_id == "canonical-1"
    assert result.records[0].predicted_p10 <= result.records[0].predicted_p50 <= result.records[0].predicted_p90
    assert persist.call_args.kwargs["source_versions"]["source"] == "public.player_game_feature_matrix"
    assert persist.call_args.kwargs["train_df"]["season"].tolist() == [2025]
