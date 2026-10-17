from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy import create_engine

from backend.app.models import CuratedSalary, PlayerGameFeatureMatrix
from backend.app.product_services.canonical_projection_inputs import (
    FEATURE_COLUMNS,
    POSITION_FEATURE_COLUMNS,
    add_position_features,
    apply_player_availability_overrides,
    apply_latest_market_context,
    reconcile_training_market_context,
    apply_pregame_projection_context,
    attach_lagged_opportunity_features,
    attach_lagged_participation_features,
    prepare_inputs,
    load_inputs,
    StaleTrainingOutcomeError,
    validate_completed_training_outcomes,
)
from backend.app.product_services.predictions import (
    PredictionsService,
    TARGET_COL,
    derive_calibration_roles,
)
from backend.app.product_services.offensive_role import attach_offensive_role, rank_team_roles


CUTOFF = datetime(2026, 9, 6, 13, tzinfo=timezone.utc)


def test_latest_captured_market_changes_both_offenses_without_imputation():
    target = pd.DataFrame([
        {"recent_team": "CHI", "opponent_team": "PHI", "game_total_line": 44.5,
         "team_spread_line": 3.0, "team_implied_total": 20.75,
         "opponent_implied_total": 23.75},
        {"recent_team": "PHI", "opponent_team": "CHI", "game_total_line": 44.5,
         "team_spread_line": -3.0, "team_implied_total": 23.75,
         "opponent_implied_total": 20.75},
    ])
    market = pd.DataFrame([{
        "raw_nfl_schedule_id": 12, "source_system": "public_market",
        "home_team": "CHI", "away_team": "PHI",
        "kickoff": "2026-10-04T17:00:00Z", "created_at": "2026-09-28T18:00:01Z",
        "raw_row_json": {"total_line": 41.5, "spread_line": -3.5,
                         "observed_at": "2026-09-28T18:00:00Z"},
    }])
    updated, audit = apply_latest_market_context(target, market, cutoff=datetime(2026, 9, 29, tzinfo=timezone.utc))
    assert updated["team_implied_total"].tolist() == [19.0, 22.5]
    assert updated["team_spread_line"].tolist() == [3.5, -3.5]
    assert updated["market_context_updated_from_matrix"].tolist() == [True, True]
    assert len(audit) == 2
    assert {row["source_system"] for row in audit} == {"public_market"}
    unchanged, missing_audit = apply_latest_market_context(target, pd.DataFrame())
    assert unchanged["team_implied_total"].isna().all()
    assert unchanged["game_total_line"].isna().all()
    assert unchanged["team_spread_line"].isna().all()
    assert missing_audit == []
    newer_matrix = target.assign(created_at="2026-09-28T19:30:00Z")
    older_market = market.assign(created_at="2026-09-28T18:00:00Z")
    preserved, _ = apply_latest_market_context(newer_matrix, older_market,
                                                cutoff=datetime(2026, 9, 29, tzinfo=timezone.utc))
    assert preserved["team_implied_total"].tolist() == [19.0, 22.5]
    late, ignored = apply_latest_market_context(target, market.assign(created_at="2026-09-30T18:00:00Z"),
                                                 cutoff=datetime(2026, 9, 29, tzinfo=timezone.utc))
    assert late["team_implied_total"].isna().all()
    assert {row["status"] for row in ignored} == {"market_timestamp_not_predecision"}


def test_historical_market_reconciliation_corrects_reversed_favorite():
    train = pd.DataFrame([
        {"season": 2025, "week": 18, "team": "ARI", "opponent": "LAR",
         "game_id": "game-1", "game_total_line": 49.5,
         "team_spread_line": -14.5, "team_implied_total": 32.0,
         "opponent_implied_total": 17.5},
    ])
    market = pd.DataFrame([{
        "season": 2025, "week": 18, "home_team": "LA", "away_team": "ARI",
        "raw_row_json": {"total_line": 49.5, "spread_line": 14.5},
    }])
    corrected, audit = reconcile_training_market_context(train, market)
    assert corrected.loc[0, "team_spread_line"] == 14.5
    assert corrected.loc[0, "team_implied_total"] == 17.5
    assert corrected.loc[0, "opponent_implied_total"] == 32.0
    assert audit["corrected_players"] == 1
    assert audit["corrected_games"] == 1


def test_market_snapshot_assigns_canonical_game_id_to_dst_feature_without_one():
    target = pd.DataFrame([{"recent_team": "TB", "opponent_team": "GB",
                            "game_id": None, "position": "DST",
                            "game_total_line": 0.0, "team_spread_line": 0.0,
                            "team_implied_total": 0.0, "opponent_implied_total": 0.0}])
    market = pd.DataFrame([{"raw_nfl_schedule_id": "snapshot-1", "source_system": "nflverse_schedules",
                            "home_team": "TB", "away_team": "GB", "game_id": "2026_04_GB_TB",
                            "kickoff": "2026-10-04T17:00:00Z", "created_at": "2026-09-29T21:22:12Z",
                            "raw_row_json": {"total_line": 39.5, "spread_line": -3.5,
                                             "observed_at": "2026-09-29T21:22:11Z"}}])
    updated, audit = apply_latest_market_context(target, market,
                                                  cutoff=datetime(2026, 9, 30, tzinfo=timezone.utc))
    assert updated.loc[0, "game_id"] == "2026_04_GB_TB"
    assert updated.loc[0, "team_implied_total"] == 18.0
    assert len(audit) == 1


def test_showdown_market_refresh_orders_observations_by_instant_across_timezones():
    target = pd.DataFrame([{"slate": "THURSDAY_NIGHT", "recent_team": "CLE",
                            "opponent_team": "PIT", "game_id": "2026_04_PIT_CLE",
                            "game_total_line": 0.0, "team_spread_line": 0.0,
                            "team_implied_total": 0.0, "opponent_implied_total": 0.0}])
    rows = pd.DataFrame([
        {"raw_nfl_schedule_id": "new", "source_system": "nflverse_schedules",
         "home_team": "CLE", "away_team": "PIT", "game_id": "2026_04_PIT_CLE",
         "kickoff": "2026-10-02T00:15:00Z", "created_at": "2026-09-30T01:22:12Z",
         "raw_row_json": {"total_line": 38.5, "spread_line": -2.5,
                          "observed_at": "2026-09-29T21:22:11-04:00"}},
        {"raw_nfl_schedule_id": "old", "source_system": "nflverse_schedules",
         "home_team": "CLE", "away_team": "PIT", "game_id": "2026_04_PIT_CLE",
         "kickoff": "2026-10-02T00:15:00Z", "created_at": "2026-09-30T00:00:01Z",
         "raw_row_json": {"total_line": 37.5, "spread_line": -1.5,
                          "observed_at": "2026-09-30T00:00:00Z"}},
    ])
    updated, _ = apply_latest_market_context(target, rows,
                                             cutoff=datetime(2026, 9, 30, 2, tzinfo=timezone.utc))
    assert updated.loc[0, "slate"] == "THURSDAY_NIGHT"
    assert updated.loc[0, "market_snapshot_row_id"] == "new"
    assert updated.loc[0, "game_total_line"] == 38.5
    assert updated.loc[0, "team_implied_total"] == 18.0


def test_projection_overlay_consumes_normalized_market_snapshot_columns():
    target = pd.DataFrame([{"season": 2026, "week": 4, "recent_team": "CLE",
                            "opponent_team": "PIT", "game_id": "2026_04_PIT_CLE",
                            "game_total_line": 0.0, "team_spread_line": 0.0,
                            "team_implied_total": 0.0, "opponent_implied_total": 0.0}])
    normalized = pd.DataFrame([{"market_snapshot_id": "capture-1",
                                "source": "nflverse_schedules", "season": 2026, "week": 4,
                                "home_team": "CLE", "away_team": "PIT",
                                "game_id": "2026_04_PIT_CLE",
                                "kickoff_at": "2026-10-02T00:15:00Z",
                                "observed_at": "2026-09-30T01:22:11Z",
                                "ingested_at": "2026-09-30T01:22:12Z",
                                "game_total": 38.5, "home_spread": 2.5}])
    updated, audit = apply_latest_market_context(target, normalized,
                                                  cutoff=datetime(2026, 9, 30, 2, tzinfo=timezone.utc))
    assert updated.loc[0, "game_total_line"] == 38.5
    assert updated.loc[0, "team_spread_line"] == 2.5
    assert updated.loc[0, "team_implied_total"] == 18.0
    assert updated.loc[0, "market_snapshot_row_id"] == "capture-1"
    assert audit[0]["source_system"] == "nflverse_schedules"


def test_prior_season_market_cannot_fill_missing_dst_game_id():
    target = pd.DataFrame([{"season": 2026, "week": 4, "recent_team": "CLE",
                            "opponent_team": "PIT", "game_id": None,
                            "game_total_line": 0.0, "team_spread_line": 0.0,
                            "team_implied_total": 0.0, "opponent_implied_total": 0.0}])
    prior = pd.DataFrame([{"season": 2025, "week": 4,
                           "raw_nfl_schedule_id": "old", "source_system": "nflverse_schedules",
                           "home_team": "CLE", "away_team": "PIT", "game_id": "2025_04_PIT_CLE",
                           "kickoff": "2025-10-02T00:15:00Z",
                           "created_at": "2025-09-30T00:00:01Z",
                           "raw_row_json": {"total_line": 38.5, "spread_line": -2.5,
                                            "observed_at": "2025-09-30T00:00:00Z"}}])
    updated, _ = apply_latest_market_context(target, prior,
                                             cutoff=datetime(2026, 9, 30, 2, tzinfo=timezone.utc))
    assert pd.isna(updated.loc[0, "game_total_line"])
    assert updated.loc[0, "game_id"] is None


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


def test_unresolved_canonical_availability_names_player_and_recovery_action():
    from backend.app.product_services.showdown_player_context import CONTEXT_CONTRACT, PlayerContextUnresolved
    matrix, salaries = inputs()
    context = pd.DataFrame([{
        "player_master_id": "canonical-1", "position": "WR",
        "evidence_json": {"canonical_context_contract": CONTEXT_CONTRACT, "availability_state": "UNKNOWN"},
    }])
    with pytest.raises(PlayerContextUnresolved, match="Same Name.*refresh roster, injury and depth-chart evidence"):
        prepare(matrix, salaries, pregame_context=context)


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


def test_completed_training_outcome_audit_rejects_pregame_zero_placeholders():
    train = pd.DataFrame(
        [
            {"season": 2026, "week": 1, "player_id": "p1", TARGET_COL: 0.0},
            {"season": 2026, "week": 1, "player_id": "p2", TARGET_COL: 0.0},
        ]
    )
    weekly_stats = pd.DataFrame(
        [
            {
                "season": 2026,
                "week": 1,
                "player_master_id": "p1",
                "carries": 12,
                "targets": 3,
            }
        ]
    )

    with pytest.raises(
        StaleTrainingOutcomeError,
        match="Rebuild the player-game feature matrix",
    ) as error:
        validate_completed_training_outcomes(train, weekly_stats)
    assert error.value.periods == ((2026, 1),)


def test_completed_training_outcome_audit_accepts_scored_period():
    train = pd.DataFrame(
        [
            {"season": 2026, "week": 1, "player_id": "p1", TARGET_COL: 14.5},
            {"season": 2026, "week": 1, "player_id": "p2", TARGET_COL: 0.0},
        ]
    )
    weekly_stats = pd.DataFrame(
        [
            {
                "season": 2026,
                "week": 1,
                "player_master_id": "p1",
                "carries": 12,
                "targets": 3,
            }
        ]
    )

    audit = validate_completed_training_outcomes(train, weekly_stats)

    assert audit == {
        "status": "valid",
        "periods_checked": 1,
        "zero_label_periods": [],
    }


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
    assert rows["carry_share_mean_3_available"].tolist() == [True]


def test_role_trends_compare_last_game_with_prior_three_without_future_leakage():
    matrix = pd.DataFrame([{"season": 2026, "week": 5, "player_master_id": "runner", "team": "SEA", "position": "RB"}])
    participation = pd.DataFrame([
        {"season": 2026, "week": week, "player_master_id": "runner",
         "participation_status": "played_confirmed", "offense_snap_share": share}
        for week, share in enumerate((0.4, 0.5, 0.6, 0.8, 0.1), 1)
    ])
    snaps, _ = attach_lagged_participation_features(
        matrix, participation, cutoff=pd.Timestamp(CUTOFF))
    assert snaps.loc[0, "snap_share_last"] == 0.8
    assert snaps.loc[0, "snap_share_prior3"] == 0.5
    assert snaps.loc[0, "snap_share_trend"] == pytest.approx(0.3)
    weekly = pd.DataFrame([
        {"season": 2026, "week": week, "player_master_id": player,
         "team": "SEA", "position": "RB", "carries": carries, "targets": targets}
        for week, pair in enumerate(((4, 1), (5, 2), (6, 3), (8, 4), (100, 100)), 1)
        for player, carries, targets in (("runner", pair[0], pair[1]), ("other", 10 - min(pair[0], 10), 5 - min(pair[1], 5)))
    ])
    usage, _ = attach_lagged_opportunity_features(matrix, weekly, cutoff=pd.Timestamp(CUTOFF))
    assert usage.loc[0, "rush_share_last"] == pytest.approx(0.8)
    assert usage.loc[0, "target_share_last"] == pytest.approx(0.8)
    assert usage.loc[0, "rush_share_trend"] > 0
    assert usage.loc[0, "target_share_trend"] > 0

    receiver = matrix.assign(position="WR")
    receiver_usage, _ = attach_lagged_opportunity_features(
        receiver, weekly, cutoff=pd.Timestamp(CUTOFF))
    assert pd.isna(receiver_usage.loc[0, "rush_share_trend"])


def test_missing_raw_opportunity_is_not_reinterpreted_as_zero():
    matrix = pd.DataFrame([{"season": 2026, "week": 2,
                            "player_master_id": "runner", "team": "A"}])
    weekly = pd.DataFrame([{"season": 2026, "week": 1,
                            "player_master_id": "runner", "team": "A",
                            "position": "RB", "carries": None, "targets": 0}])
    with pytest.raises(ValueError, match="unavailable carries"):
        attach_lagged_opportunity_features(matrix, weekly, cutoff=pd.Timestamp(CUTOFF))


def test_offensive_role_uses_measured_opportunity_and_never_salary():
    rows = pd.DataFrame([
        {"position": "RB", "team": "A", "salary": 1000,
         "carry_share_mean_3": 0.7, "target_share_mean_3": 0.2,
         "snap_share_mean_3": 0.8,
         "carry_share_mean_3_available": True,
         "target_share_mean_3_available": True,
         "snap_share_mean_3_available": True},
        {"position": "RB", "team": "A", "salary": 9000,
         "carry_share_mean_3": 0.0, "target_share_mean_3": 0.0,
         "snap_share_mean_3": 0.0,
         "carry_share_mean_3_available": False,
         "target_share_mean_3_available": False,
         "snap_share_mean_3_available": False},
    ])
    scored = attach_offensive_role(rows)
    assert scored.loc[0, "offensive_role_class"] == "offensive centerpiece"
    assert pd.isna(scored.loc[1, "offensive_role_importance"])
    assert scored.loc[1, "offensive_role_class"] is None
    changed_salary = rows.copy()
    changed_salary["salary"] = [10000, 100]
    assert attach_offensive_role(changed_salary)["offensive_role_importance"].equals(
        scored["offensive_role_importance"]
    )
    ranked = rank_team_roles(scored)
    assert ranked.iloc[0]["offensive_role_rank"] == 1


def test_measured_zero_role_is_distinct_from_missing_role():
    rows = pd.DataFrame([
        {"position": "WR", "target_share_mean_3": 0.0,
         "target_share_mean_3_available": True,
         "snap_share_mean_3": 0.0, "snap_share_mean_3_available": True},
        {"position": "WR", "target_share_mean_3": 0.0,
         "target_share_mean_3_available": False,
         "snap_share_mean_3": 0.0, "snap_share_mean_3_available": False},
    ])
    scored = attach_offensive_role(rows)
    assert scored.loc[0, "offensive_role_importance"] == 0.0
    assert pd.isna(scored.loc[1, "offensive_role_importance"])


def test_current_expected_counts_activate_reconciled_role_adjustment():
    target = pd.DataFrame([
        {"player_id": "lead", "position": "RB", "recent_team": "A",
         "salary": 7000, "player_games_history": 10,
         "snap_share_mean_3": 0.6, "carry_share_mean_3": 0.5,
         "target_share_mean_3": 0.1, "carries_mean_3": 10.0,
         "targets_mean_3": 2.0, "team_carries_mean_3": 20.0,
         "team_targets_mean_3": 20.0},
        {"player_id": "backup", "position": "RB", "recent_team": "A",
         "salary": 3000, "player_games_history": 10,
         "snap_share_mean_3": 0.4, "carry_share_mean_3": 0.5,
         "target_share_mean_3": 0.1, "carries_mean_3": 10.0,
         "targets_mean_3": 2.0, "team_carries_mean_3": 20.0,
         "team_targets_mean_3": 20.0},
    ])
    context = pd.DataFrame([{"player_master_id": "lead", "expected_carries": 16.0}])
    rows, metrics = apply_pregame_projection_context(target, pregame_context=context)
    assert rows["carries_mean_3"].tolist() == pytest.approx([16.0, 4.0])
    assert rows.loc[0, "pregame_effective_carry_share"] == pytest.approx(0.8)
    assert rows.loc[0, "pregame_effective_carry_share_source"] == (
        "expected_count_divided_by_lagged_team_volume"
    )
    assert rows["pregame_opportunity_context_applied"].all()
    carries = [a for a in metrics["allocations"] if a["opportunity"] == "carry"]
    assert carries[0]["unallocated_volume"] == pytest.approx(0.0)
    assert metrics["team_pass_attempts"] is None
    inconsistent = pd.DataFrame([{"player_master_id": "lead",
                                  "expected_carries": 16.0, "carry_share": 0.4}])
    with pytest.raises(ValueError, match="share and expected count conflict"):
        apply_pregame_projection_context(target, pregame_context=inconsistent)


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
    # No observed opportunity or sourced promotion: salary cannot manufacture
    # a full workload for the rookie after the veteran is removed.
    assert by_id.loc["rb-rookie", "carry_share_mean_3"] == 0.0
    assert by_id.loc["rb-rookie", "carries_mean_3"] == 0.0
    assert by_id.loc["rb-rookie", "target_share_mean_3"] == 0.0
    assert by_id.loc["rb-veteran", "pregame_expected_snaps"] == 12.0
    assert by_id.loc["rb-veteran", "pregame_expected_carries"] == 4.0
    assert by_id.loc["rb-veteran", "pregame_red_zone_share"] == 0.20
    assert by_id.loc["rb-veteran", "pregame_injury_status"] == "OUT"
    assert bool(by_id.loc["rb-veteran", "pregame_role_uncertain"]) is True
    assert bool(by_id.loc["rb-veteran", "pregame_newly_assigned_role"]) is True
    assert bool(by_id.loc["rb-veteran", "pregame_depth_chart_conflict"]) is True
    assert metrics["allocations"][0]["team_volume_source"] == "lagged_full_team_volume"
    assert metrics["context_run_ids"] == ["context-1"]


@pytest.mark.parametrize("use_questionable_checkbox", [False, True])
def test_assume_out_uses_generic_team_opportunity_redistribution(use_questionable_checkbox):
    target = pd.DataFrame(
        [
            {
                "player_id": "receiver-1", "player_display_name": "Primary Receiver",
                "position": "WR", "recent_team": "LAR", "salary": 9000,
                "player_games_history": 10, "snap_share_mean_3": 0.9,
                "carry_share_mean_3": 0.0, "target_share_mean_3": 0.6,
                "carries_mean_3": 0.0, "targets_mean_3": 12.0,
                "team_carries_mean_3": 20.0, "team_targets_mean_3": 20.0,
            },
            {
                "player_id": "receiver-2", "player_display_name": "Second Receiver",
                "position": "WR", "recent_team": "LAR", "salary": 6000,
                "player_games_history": 10, "snap_share_mean_3": 0.8,
                "carry_share_mean_3": 0.0, "target_share_mean_3": 0.4,
                "carries_mean_3": 0.0, "targets_mean_3": 8.0,
                "team_carries_mean_3": 20.0, "team_targets_mean_3": 20.0,
            },
        ]
    )
    context = pd.DataFrame(
        [{
            "player_master_id": "receiver-1", "injury_status": "QUESTIONABLE",
            "availability_probability": 0.75, "expected_routes": 30.0,
        }]
    )

    scenario_context, audit = apply_player_availability_overrides(
        target,
        context,
        [] if use_questionable_checkbox else [{"player_name": "Primary Receiver", "availability": "assume_out"}],
        assume_questionable_out=use_questionable_checkbox,
    )
    rows, _ = apply_pregame_projection_context(
        target,
        pregame_context=scenario_context,
    )
    by_id = rows.set_index("player_id")

    assert audit == [{
        "player_id": "receiver-1",
        "player_name": "Primary Receiver",
        "team": "LAR",
        "official_availability_status": "QUESTIONABLE",
        "availability_override": "assume_out",
        "model_availability_used": 0.0,
        "opportunity_redistributed": True,
    }]
    assert by_id.loc["receiver-1", "pregame_availability_probability"] == 0.0
    assert by_id.loc["receiver-1", "pregame_expected_routes"] == 0.0
    assert by_id.loc["receiver-1", "pregame_expected_targets"] == 0.0
    assert by_id.loc["receiver-1", "targets_mean_3"] == 0.0
    assert by_id.loc["receiver-2", "target_share_mean_3"] == 1.0
    assert by_id.loc["receiver-2", "targets_mean_3"] == 20.0


def test_partial_injury_redistribution_preserves_unallocated_targets():
    target = pd.DataFrame([
        {"player_id": "out", "player_display_name": "Out", "position": "WR",
         "recent_team": "GB", "salary": 9000, "player_games_history": 3,
         "snap_share_mean_3": 0.9, "carry_share_mean_3": 0.0,
         "target_share_mean_3": 0.6, "carries_mean_3": 0.0,
         "targets_mean_3": 12.0, "team_carries_mean_3": 20.0,
         "team_targets_mean_3": 20.0},
        {"player_id": "active", "player_display_name": "Active", "position": "WR",
         "recent_team": "GB", "salary": 6000, "player_games_history": 3,
         "snap_share_mean_3": 0.8, "carry_share_mean_3": 0.0,
         "target_share_mean_3": 0.4, "carries_mean_3": 0.0,
         "targets_mean_3": 8.0, "team_carries_mean_3": 20.0,
         "team_targets_mean_3": 20.0},
    ])
    context = pd.DataFrame([{
        "player_master_id": "out", "availability_probability": 1.0,
        "evidence_json": {"target_redistribution_fraction": 0.75},
    }])
    scenario, _ = apply_player_availability_overrides(
        target, context, [{"player_id": "out", "availability": "assume_out"}]
    )
    rows, metrics = apply_pregame_projection_context(
        target, pregame_context=scenario
    )
    by_id = rows.set_index("player_id")
    target_audit = next(row for row in metrics["allocations"] if row["opportunity"] == "target")
    assert by_id.loc["out", "targets_mean_3"] == 0.0
    assert by_id.loc["active", "targets_mean_3"] == pytest.approx(17.0)
    assert target_audit["unallocated_volume"] == pytest.approx(3.0)


def test_assume_active_cannot_override_confirmed_inactive_without_debug_mode():
    target = pd.DataFrame([{
        "player_id": "receiver-1", "player_display_name": "Primary Receiver",
        "position": "WR", "recent_team": "LAR",
    }])
    context = pd.DataFrame([{
        "player_master_id": "receiver-1", "injury_status": "OUT",
        "availability_probability": 0.0,
    }])

    with pytest.raises(ValueError, match="cannot override confirmed inactive"):
        apply_player_availability_overrides(
            target,
            context,
            [{"player_id": "receiver-1", "availability": "assume_active"}],
        )


def test_questionable_checkbox_uses_salary_and_injury_designations_without_mutating_sources():
    target = pd.DataFrame([
        {"player_id": "salary-q", "player_display_name": "Salary Q", "recent_team": "GB", "player_status": " q "},
        {"player_id": "injury-q", "player_display_name": "Injury Q", "recent_team": "GB", "player_status": None},
        {"player_id": "healthy", "player_display_name": "Healthy", "recent_team": "GB", "player_status": None},
        {"player_id": "doubtful", "player_display_name": "Doubtful", "recent_team": "GB", "player_status": "D"},
    ])
    context = pd.DataFrame([
        {"player_master_id": "injury-q", "injury_status": "Questionable", "availability_probability": 0.75},
        {"player_master_id": "healthy", "injury_status": "ACTIVE", "availability_probability": 1.0},
    ])
    original_target, original_context = target.copy(deep=True), context.copy(deep=True)
    unchanged, audit = apply_player_availability_overrides(target, context, [])
    pd.testing.assert_frame_equal(unchanged, original_context)
    assert audit == []
    scenario, audit = apply_player_availability_overrides(
        target, context,
        [{"player_name": "Salary Q", "availability": "assume_out"},
         {"player_id": "salary-q", "availability": "assume_out"}],
        assume_questionable_out=True,
    )
    assert {row["player_id"] for row in audit} == {"salary-q", "injury-q"}
    assert len(audit) == 2
    assert {row["official_availability_status"] for row in audit} == {"Q", "QUESTIONABLE"}
    assert all(row["availability_override"] == "assume_out" for row in audit)
    assert scenario.set_index("player_master_id").loc["injury-q", "availability_probability"] == 0.0
    assert scenario.set_index("player_master_id").loc["healthy", "availability_probability"] == 1.0
    pd.testing.assert_frame_equal(target, original_target)
    pd.testing.assert_frame_equal(context, original_context)
    with pytest.raises(ValueError, match="Conflicting availability overrides"):
        apply_player_availability_overrides(target, context, [
            {"player_id": "salary-q", "availability": "assume_active"},
        ], assume_questionable_out=True)


def test_questionable_scenario_changes_only_target_availability_not_historical_training():
    matrix, salaries = inputs()
    salaries["player_status"] = "QUESTIONABLE"
    teammate_matrix = matrix.copy()
    teammate_matrix["player_master_id"] = "canonical-2"
    teammate_matrix["player_id"] = "teammate-source"
    teammate_matrix["player_game_feature_matrix_id"] += 10
    teammate_salaries = salaries.copy()
    teammate_salaries["player_master_id"] = "canonical-2"
    teammate_salaries["player_name"] = "Teammate"
    teammate_salaries["source_player_key"] = ["teammate-flex", "teammate-cpt"]
    teammate_salaries["curated_salary_id"] += 10
    teammate_salaries["player_status"] = None
    matrix = pd.concat([matrix, teammate_matrix], ignore_index=True)
    salaries = pd.concat([salaries, teammate_salaries], ignore_index=True)
    base_train, base_target, _ = prepare(matrix, salaries)
    train, target, metadata = prepare(matrix, salaries, assume_questionable_out=True)
    pd.testing.assert_frame_equal(train, base_train)
    assert base_target["pregame_availability_probability"].tolist() == [1.0, 1.0]
    by_id = target.set_index("player_id")
    assert by_id.loc["canonical-1", "pregame_availability_probability"] == 0.0
    assert by_id.loc["canonical-2", "pregame_availability_probability"] == 1.0
    assert by_id.loc["canonical-1", "availability_override"] == "assume_out"
    assert by_id.loc["canonical-2", "availability_override"] == "default"
    assert metadata["availability_scenario"]["assume_questionable_out"] is True
    assert metadata["availability_scenario"]["overrides"][0]["player_id"] == "canonical-1"


@pytest.mark.parametrize("cleared", [False, True])
def test_questionable_snapshot_selection_uses_cutoff_and_effective_status(cleared):
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    inspector = MagicMock()
    inspector.has_table.side_effect = lambda name, **kwargs: name in {
        "snapshot_injury_status", "pregame_player_context",
    }
    salaries = pd.DataFrame([{"slate": "NIGHT", "player_master_id": "canonical-1"}])
    snapshots = pd.DataFrame([
        {"snapshot_injury_id": 42, "player_id": "canonical-1", "injury_status": "Q",
         "as_of": CUTOFF, "source": "official"},
        {"snapshot_injury_id": 43, "player_id": "other-slate", "injury_status": "Q",
         "as_of": CUTOFF, "source": "official"},
    ])
    def prepare_loaded(*args, **kwargs):
        matrix, scoring_salaries = inputs()
        return prepare(matrix, scoring_salaries, pregame_context=args[5],
            injury_statuses=kwargs["injury_statuses"], assume_questionable_out=True,
            availability_overrides=kwargs["availability_overrides"])
    with (
        patch("backend.app.product_services.canonical_projection_inputs.inspect", return_value=inspector),
        patch("backend.app.product_services.canonical_projection_inputs.pd.read_sql",
              side_effect=[salaries, pd.DataFrame(), snapshots]) as read_sql,
        patch("backend.app.product_services.canonical_projection_inputs.prepare_inputs", side_effect=prepare_loaded) as prepare_mock,
        patch("backend.app.product_services.pregame_context.load_current_pregame_context", return_value=[
            {"player_master_id": "canonical-1", "injury_status": "ACTIVE" if cleared else None},
        ]),
    ):
        _, _, metadata = load_inputs(engine, season=2026, week=1, slate="NIGHT",
                                     cutoff=CUTOFF, assume_questionable_out=True)
    snapshot_call = read_sql.call_args_list[2]
    assert "as_of <= :cutoff" in str(snapshot_call.args[0])
    assert snapshot_call.kwargs["params"]["cutoff"] == CUTOFF.replace(tzinfo=None)
    pd.testing.assert_frame_equal(prepare_mock.call_args.kwargs["injury_statuses"], snapshots)
    assert bool(metadata["availability_scenario"]["overrides"]) is not cleared
    rows = metadata["availability_scenario"]["injury_snapshot_rows"]
    assert [row["snapshot_injury_id"] for row in rows] == ([] if cleared else [42])


@pytest.mark.parametrize("exclusion", ["salary_status", "roster", "position"])
def test_automatic_questionable_snapshot_only_applies_to_scoring_players(exclusion):
    matrix, salaries = inputs()
    excluded_matrix = matrix.assign(player_master_id="excluded", player_name="Excluded Receiver",
                                    player_game_feature_matrix_id=matrix["player_game_feature_matrix_id"] + 10)
    excluded_salaries = salaries.assign(player_master_id="excluded", player_name="Excluded Receiver",
                                       curated_salary_id=salaries["curated_salary_id"] + 10,
                                       player_status="OUT" if exclusion == "salary_status" else "Q")
    if exclusion == "position":
        excluded_salaries["position"] = "TE"
        excluded_matrix["position"] = "TE"
    participation = pd.DataFrame([
        {"season": season, "week": week, "player_master_id": pid, "team": "A",
         "roster_status": "DEV" if exclusion == "roster" and season == 2026 and pid == "excluded" else "ACT",
         "participation_status": "played_confirmed", "offense_snap_share": 0.75,
         "created_at": "2026-09-06T11:00:00Z", "curated_player_game_participation_id": i}
        for i, (season, week, pid) in enumerate([(2025, 18, "canonical-1"), (2025, 18, "excluded"),
                                               (2026, 1, "canonical-1"), (2026, 1, "excluded")], 1)
    ])
    snapshots = pd.DataFrame([
        {"player_id": pid, "injury_status": "Q"} for pid in ["canonical-1", "excluded", "another-slate"]
    ])
    originals = [frame.copy(deep=True) for frame in (matrix, salaries, participation, snapshots)]
    train, target, metadata = prepare(pd.concat([matrix, excluded_matrix]),
        pd.concat([salaries, excluded_salaries]), participation=participation,
        injury_statuses=snapshots, assume_questionable_out=True, positions=["WR"])
    assert target["player_id"].tolist() == ["canonical-1"]
    assert target["availability_override"].tolist() == ["assume_out"]
    assert target["pregame_availability_probability"].tolist() == [0.0]
    assert [r["player_id"] for r in metadata["availability_scenario"]["overrides"]] == ["canonical-1"]
    if exclusion == "roster":
        assert metadata["roster_eligibility_policy"]["excluded_players"][0]["roster_status"] == "DEV"
    elif exclusion == "salary_status":
        assert metadata["salary_status_policy"]["excluded_players"][0]["status"] == "OUT"
    else:
        assert metadata["excluded_positions"] == ["TE"]
    assert train["season"].eq(2025).all()
    for original, frame in zip(originals, (matrix, salaries, participation, snapshots), strict=True):
        pd.testing.assert_frame_equal(original, frame)


@pytest.mark.parametrize("reference", [{"player_id": "another-slate"}, {"player_name": "Missing Player"}])
def test_explicit_out_of_pool_availability_assumptions_still_fail(reference):
    matrix, salaries = inputs()
    with pytest.raises(ValueError, match="was not found in the selected slate"):
        prepare(matrix, salaries, assume_questionable_out=True,
                availability_overrides=[{**reference, "availability": "assume_out"}])


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
    with pytest.raises(ValueError, match="Resolve 1 salary identities before projections"):
        prepare(matrix, pd.concat([salaries, pd.DataFrame([late, unknown, unsupported])]))
    _, target, metadata = prepare(matrix, pd.concat([salaries, pd.DataFrame([late, unsupported])]))
    assert target["salary"].tolist() == [5000]
    assert metadata["unresolved_salary_source_keys"] == []
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
    salaries["team"] = "LAR"
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
    development_salaries["team"] = "LAR"
    development_salaries["curated_salary_id"] += 20
    participation = pd.DataFrame(
        [
            {
                "season": 2025,
                "week": 18,
                "player_master_id": player_id,
                "team": "LA",
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
                "team": "LA",
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
                "team": "LA",
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


@pytest.mark.parametrize("covered_team", ["CAR", "LA"])
def test_other_slate_roster_coverage_does_not_exclude_target_players(covered_team):
    matrix, salaries = inputs()
    salaries["team"] = "DET"
    participation = pd.DataFrame([
        {
            "season": 2026, "week": 1, "player_master_id": "other-slate-player",
            "team": covered_team, "roster_status": "ACT",
            "participation_status": "unknown",
            "created_at": "2026-09-06T11:00:00Z",
        },
        {
            "season": 2025, "week": 18, "player_master_id": "canonical-1",
            "team": "A", "roster_status": "ACT",
            "participation_status": "played_confirmed",
            "created_at": "2026-09-06T11:00:00Z",
        },
    ])

    _, target, metadata = prepare(matrix, salaries, participation=participation)

    assert target["player_id"].tolist() == ["canonical-1"]
    policy = metadata["roster_eligibility_policy"]
    assert policy["excluded_player_count"] == 0
    assert policy["missing_teams"] == ["DET"]
    assert policy["covered_teams"] == (["LAR"] if covered_team == "LA" else ["CAR"])


def test_missing_canonical_player_on_a_covered_team_remains_ineligible():
    matrix, salaries = inputs()
    salaries["team"] = "LAR"
    participation = pd.DataFrame([{
        "season": 2026, "week": 1, "player_master_id": "different-canonical-id",
        "team": "LA", "roster_status": "ACT",
        "participation_status": "unknown",
        "created_at": "2026-09-06T11:00:00Z",
    }])
    with pytest.raises(ValueError, match="No roster-eligible canonical salaries"):
        prepare(matrix, salaries, participation=participation)


def test_roster_coverage_loaded_after_cutoff_does_not_exclude_players():
    matrix, salaries = inputs()
    participation = pd.DataFrame([{
        "season": 2026, "week": 1, "player_master_id": "different-canonical-id",
        "team": "A", "roster_status": "ACT",
        "participation_status": "unknown",
        "created_at": "2026-09-06T14:00:00Z",
    }])
    _, target, metadata = prepare(matrix, salaries, participation=participation)
    assert target["player_id"].tolist() == ["canonical-1"]
    assert metadata["roster_eligibility_policy"]["available"] is False


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


def test_explicit_preliminary_unknown_exclusion_preserves_facts_training_and_known_player_features():
    from copy import deepcopy
    from backend.app.product_services.showdown_player_context import CONTEXT_CONTRACT, PlayerContextUnresolved
    matrix, salaries = inputs()
    matrix = pd.concat([matrix, matrix.assign(player_master_id="canonical-2", player_id="source-2", player_game_feature_matrix_id=matrix.player_game_feature_matrix_id + 10)], ignore_index=True)
    salaries = salaries[salaries.roster_position == 'FLEX'].copy()
    known = salaries.iloc[0].to_dict()
    known.update(player_master_id='canonical-2', curated_salary_id=3, source_player_key='dk-known', player_name='Known Player')
    salaries = pd.concat([salaries, pd.DataFrame([known])],ignore_index=True)
    context = pd.DataFrame([{'player_master_id':pid,'position':'WR','evidence_json':{'canonical_context_contract':CONTEXT_CONTRACT,'availability_state':state}}
                           for pid,state in [('canonical-1','UNKNOWN'),('canonical-2','AVAILABLE')]])
    before=deepcopy(context.to_dict('records'))
    with patch('backend.app.product_services.canonical_projection_inputs.assess_availability',side_effect=lambda row,**kw:(row['availability_state'],[])), patch('backend.app.product_services.classic_player_pool.assess_pool_player',return_value={'role_exclusion_policy':None,'quarantine':False,'role_current':True}):
        with pytest.raises(PlayerContextUnresolved):prepare(matrix,salaries,pregame_context=context)
        train,target,audit=prepare(matrix,salaries,pregame_context=context,preliminary_exclude_unknown=True)
        baseline_train,baseline,_=prepare(matrix,salaries.iloc[[1]],pregame_context=context.iloc[[1]])
    assert target.player_id.tolist()==['canonical-2']
    assert audit['preliminary_research']['exclude_player_ids']==['canonical-1']
    assert audit['preliminary_research']['entry_ready'] is False
    assert context.to_dict('records')==before
    pd.testing.assert_frame_equal(train,baseline_train)
    pd.testing.assert_frame_equal(target[FEATURE_COLUMNS],baseline[FEATURE_COLUMNS],check_dtype=False)
    assert audit['canonical_player_pool']['explicitly_unavailable_player_ids']==[]
