from copy import deepcopy
from datetime import datetime, timezone
import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.app.product_services.workload_evidence import build_workload_evidence, CONTRACT_ID
from backend.app.product_services.optimizer_effectiveness import candidate_snapshot, evaluate_run
from backend.app.product_services.optimizer import OptimizerService, apply_showdown_opportunity_gate, CLASSIC_HEAD_TO_HEAD_STRATEGY_ID


def source(**extra):
    return {"player_id": "canonical-1", "position": "WR", "salary": 8000,
            "projection": 14.1, "predicted_p10": 2.3, "p90": 23.4,
            "snap_share_mean_3": 0.497, "targets_mean_3": 0,
            "projected_targets": 5.165, "pregame_expected_targets": None,
            "workload_feature_evidence": {"snap_share_mean_3_available": True,
                "targets_mean_3_available": True, "opportunity_history_window": [{"season": 2026, "week": 4}]},
            "workload_feature_run_id": "feature-1", "workload_feature_cutoff_at": "2026-10-10T12:00:00Z",
            "pregame_context_run_id": "context-1", "pregame_context_source": "official",
            "pregame_context_observed_at": "2026-10-10T11:00:00Z", **extra}


def test_history_zero_missing_and_unknown_coverage_are_distinct_and_json_safe():
    packet = build_workload_evidence(source())
    assert packet["historical"]["targets_mean_3"] == {"value": 0, "status": "observed", "available": True, "stored_value": 0}
    missing = build_workload_evidence(source(workload_feature_evidence={"targets_mean_3_available": False}))
    assert missing["historical"]["targets_mean_3"]["value"] is None
    assert missing["historical"]["targets_mean_3"]["stored_value"] == 0
    unknown = build_workload_evidence(source(workload_feature_evidence={}))
    assert unknown["historical"]["targets_mean_3"]["status"] == "coverage_unknown"
    assert unknown["historical"]["snap_share_mean_3"]["status"] == "coverage_unknown"
    json.dumps(build_workload_evidence(source(carries_mean_3=float("nan"))), allow_nan=False)


def test_availability_alone_does_not_establish_workload_and_proxies_never_fill_forecasts():
    row = {"player_id": "p", "position": "TE", "pregame_availability_probability": 1,
           "pregame_start_probability": 1, "pregame_role_label": "STARTER"}
    assert build_workload_evidence(row)["status"] == "unavailable"
    packet = build_workload_evidence(source())
    assert packet["derived_proxies"]["projected_targets"]["value"] == 5.165
    assert packet["explicit_pregame"]["pregame_expected_targets"]["value"] is None
    assert packet["historical_coverage"]["opportunity_history_window"] == [{"season": 2026, "week": 4}]
    assert packet["team_volume_proxies"]["team_targets_mean_3"]["value"] is None


def test_known_clocks_ids_and_existing_confidence_preserved_without_invented_chronology():
    cutoff = datetime(2026, 10, 10, 13, tzinfo=timezone.utc)
    packet = build_workload_evidence(source(offensive_role_confidence="medium"), projection_run_id="projection-1", cutoff=cutoff)
    assert packet["lineage"]["pregame_context_observed_at"] == "2026-10-10T11:00:00Z"
    assert packet["lineage"]["workload_feature_run_id"] == "feature-1"
    assert packet["lineage"]["projection_run_id"] == "projection-1"
    assert packet["lineage"]["pregame_context_row_id"] is None
    assert packet["existing_assessment"]["offensive_role_confidence"] == "medium"
    future = build_workload_evidence(source(pregame_expected_targets=7, pregame_context_observed_at="2026-10-11T00:00:00Z"), cutoff=cutoff)
    assert future["explicit_pregame"]["pregame_expected_targets"]["status"] == "after_cutoff"
    assert future["explicit_pregame"]["pregame_expected_targets"]["value"] is None
    future_history = build_workload_evidence(source(workload_feature_cutoff_at="2026-10-11T00:00:00Z"), cutoff=cutoff)
    assert future_history["historical"]["targets_mean_3"]["status"] == "after_cutoff"
    assert future_history["derived_proxies"]["projected_targets"]["value"] is None


def test_availability_refresh_does_not_renew_projection_time_workload_lineage():
    packet = build_workload_evidence(source(pregame_expected_targets=4,
        pregame_context_run_id="refreshed-context", pregame_context_observed_at="2026-10-10T12:00:00Z",
        availability_source_ids=["availability-row-1"], role_observed_at="2026-10-10T10:00:00Z",
        workload_feature_evidence={"pregame_context_run_id": "original-workload-context",
            "pregame_context_observed_at": "2026-10-09T11:00:00Z"}))
    assert packet["explicit_pregame_lineage"]["pregame_context_run_id"] == "original-workload-context"
    assert packet["explicit_pregame_lineage"]["pregame_context_observed_at"] == "2026-10-09T11:00:00Z"
    assert packet["lineage"]["availability_source_ids"] == ["availability-row-1"]
    assert packet["lineage"]["pregame_context_run_id"] == "refreshed-context"


@pytest.mark.parametrize("position,status", [("DST", "not_applicable"), ("K", "not_applicable"), ("", "unknown_position")])
def test_specialist_and_unknown_positions(position, status):
    packet = build_workload_evidence(source(position=position))
    assert packet["status"] == status
    assert packet["historical"]["targets_mean_3"]["value"] is None


def test_identical_context_has_exact_classic_and_captain_packet_parity():
    row = source()
    before = deepcopy(row)
    classic = build_workload_evidence({**row, "contest_format": "classic", "salary": 1600})
    captain = build_workload_evidence({**row, "contest_format": "showdown", "roster_position": "CPT", "salary": 12000})
    assert classic == captain
    assert row == before


def test_sql_preserves_measurement_flags_and_existing_clock_lineage_without_history_queries():
    service = OptimizerService.__new__(OptimizerService)
    service.engine = MagicMock()
    inspector = MagicMock()
    inspector.has_table.return_value = True
    inspector.get_columns.return_value = []
    with patch("backend.app.product_services.optimizer.inspect", return_value=inspector), patch(
        "backend.app.product_services.optimizer.pd.read_sql", return_value=pd.DataFrame()) as read_sql:
        service._load_target_player_pool(season=2025, week=11, slate="SUNDAY_MAIN", projection_run_id="projection-1")
    sql = str(read_sql.call_args.args[0])
    assert "AS workload_feature_evidence" in sql
    assert "'snap_share_mean_3_available'" in sql
    assert "'targets_mean_3_available'" in sql
    assert "'opportunity_history_window'" in sql
    assert "AS workload_feature_run_id" in sql
    assert "AS workload_feature_cutoff_at" in sql
    assert "curated_player_weekly_stats" not in sql


@pytest.mark.parametrize("fmt", ["classic", "showdown"])
def test_new_run_evidence_covers_all_salaries_and_selected_rows_reference_same_packet(fmt):
    positions = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "WR", "DST"] if fmt == "classic" else ["QB", "QB", "WR", "WR", "TE", "WR"]
    rows = [source(player_id=f"p{i}", name=f"Player {i}", position=pos, salary=1600 if i == 3 else 5000,
                   player_team="AAA" if i % 2 == 0 else "BBB", opponent_team="BBB" if i % 2 == 0 else "AAA", is_starting_qb=pos == "QB")
            for i, pos in enumerate(positions)]
    frame = pd.DataFrame(rows)
    service = OptimizerService.__new__(OptimizerService)
    service.engine = MagicMock()
    service._jobs = {}
    service._resolve_run_lineage = MagicMock(return_value=("projection-1", None, None))
    service._load_player_pool = MagicMock(return_value=frame)
    lineup = deepcopy(rows)
    if fmt == "showdown":
        for i, row in enumerate(lineup):
            row["roster_position"] = "CPT" if i == 2 else "FLEX"
            if i == 2:
                row["salary"] *= 1.5
                row["projection"] *= 1.5
                row["p90"] *= 1.5
    service._solve_lineup = MagicMock(return_value=lineup)
    service._lineups_satisfy_stack = MagicMock(return_value=(True, ""))
    service._validate_classic_lineups = MagicMock(return_value=(True, ""))
    service._validate_showdown_lineups = MagicMock(return_value=(True, ""))
    service._attach_symbolic_explanations = MagicMock()
    service._persist_optimizer_run = MagicMock(return_value=True)
    with patch("backend.app.product_services.showdown_data_readiness.is_live_slate", return_value=False):
        job = service.run_job(season=2025, week=11, slate="SUNDAY_MAIN" if fmt == "classic" else "THURSDAY_NIGHT",
            strategy=CLASSIC_HEAD_TO_HEAD_STRATEGY_ID if fmt == "classic" else "showdown_cash_baseline_v1",
            params={"num_lineups": 1, "enforce_single_te": False}, contest_format=fmt, objective="cash")
    assert job.status == "completed", job.message
    evidence_rows = job.params["strategy_runtime"]["player_pool"]["rows"]
    assert len(evidence_rows) == len(rows)
    assert all(row["workload_evidence"]["contract_id"] == CONTRACT_ID for row in evidence_rows)
    packets = {row["player_id"]: row["workload_evidence"] for row in evidence_rows}
    assert packets["p3"]["historical"]["snap_share_mean_3"] == packets["p5"]["historical"]["snap_share_mean_3"]
    assert packets["p3"]["explicit_pregame"]["pregame_expected_targets"]["value"] is None
    for selected in job.results[0]:
        assert selected["workload_evidence_ref"]["player_id"] in packets
    # Input distributions and gates are untouched by evidence serialization.
    pd.testing.assert_frame_equal(frame, pd.DataFrame(rows))


@pytest.mark.parametrize("fmt", ["classic", "showdown"])
def test_saved_candidates_share_packet_lineage_and_old_runs_are_not_backfilled(fmt):
    ids = [f"p{i}" for i in range(9 if fmt == "classic" else 6)]
    candidate = {"player_ids": ids} if fmt == "classic" else {"signature": [(pid, i == 0) for i, pid in enumerate(ids)]}
    config = {"strategy_runtime": {"single_lineup": {"all_candidates": [candidate]}, "player_pool": {"rows": [
        {"player_id": pid, "workload_evidence": build_workload_evidence(source(player_id=pid))} for pid in ids]}}}
    manifest = candidate_snapshot(config, fmt)
    assert manifest["workload_evidence"]["player_count"] == len(ids)
    run = {"optimizer_run_id": "run-1", "contest_format": fmt, "constraint_config_json": config}
    result = evaluate_run(run, [], [], {}, {})
    assert result["workload_evidence"]["status"] == "saved"
    assert result["candidates"][0]["pregame"]["workload_evidence_player_ids"] == ids
    old = deepcopy(config)
    old["strategy_runtime"]["player_pool"]["rows"] = [{"player_id": "p0", "snap_share_mean_3": 0}]
    assert "workload_evidence" not in candidate_snapshot(old, fmt)
    assert evaluate_run({**run, "constraint_config_json": old}, [], [], {}, {})["workload_evidence"]["status"] == "unavailable_in_saved_run"


@pytest.mark.parametrize("contest_type", ["classic", "captain"])
def test_solver_roster_scores_and_opportunity_gate_unchanged_by_evidence_columns(contest_type):
    positions = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "WR", "DST", "TE"]
    frame = pd.DataFrame([source(player_id=f"p{i}", name=f"Player {i}", position=pos,
        player_team=f"T{i % 4}", opponent_team=f"T{(i + 1) % 4}",
        salary=4000, projection=20-i, p90=30-i, optimizer_context_ceiling_score=30-i) for i, pos in enumerate(positions)])
    plain = frame.drop(columns=["workload_feature_evidence"])
    service = OptimizerService.__new__(OptimizerService)
    options = dict(score_col="optimizer_context_ceiling_score", contest_type=contest_type,
                   stack_params={"enabled": False}, include_control_comparison=False)
    before = service._solve_lineup(plain, **options)
    after = service._solve_lineup(frame, **options)
    keys = ("player_id", "roster_position", "projection", "p90", "salary")
    assert [{key: row.get(key) for key in keys} for row in before] == [{key: row.get(key) for key in keys} for row in after]
    assert apply_showdown_opportunity_gate(plain)[1] == apply_showdown_opportunity_gate(frame)[1]
    original = deepcopy(frame.to_dict("records"))
    for row in original:
        build_workload_evidence(row)
    assert original == frame.to_dict("records")
