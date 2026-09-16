from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from backend.app.api.product_routes import (
    generate_slate_learning_report,
    get_latest_slate_learning_report,
)
from backend.app.product_schemas import SlateLearningReportRequest
from backend.app.product_services.slate_learning import build_slate_learning_report


NOW = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)


def complete_evidence():
    return {
        "contests": [{
            "contest_id": "contest-1", "contest_name": "NFL GPP", "contest_format": "showdown",
            "contest_type": "gpp", "entry_fee": 5, "field_size": 100, "observed_entries": 100,
            "field_complete": True, "winning_points": 120, "median_points": 75,
            "source_file_id": "source-1", "content_sha256": "abc",
        }],
        "entries": [{
            "contest_id": "contest-1", "entry_id": "entry-1", "entry_name": "wones0120",
            "rank": 10, "entry_points": 52.0, "lineup_text": "CPT Alpha One FLEX Beta Two",
            "source_file_id": "source-1", "ingested_at": NOW,
        }],
        "observations": [
            {"contest_id": "contest-1", "player_display_name": "Alpha One", "roster_position": "CPT",
             "player_id": "alpha", "resolution_status": "resolved", "actual_points": 30.0,
             "actual_ownership": 20.0, "observation_id": "obs-1"},
            {"contest_id": "contest-1", "player_display_name": "Beta Two", "roster_position": "FLEX",
             "player_id": "beta", "resolution_status": "resolved", "actual_points": 22.0,
             "actual_ownership": 15.0, "observation_id": "obs-2"},
        ],
        "lineup_players": [
            {"lineup_id": "lineup-1", "slot_index": 0, "player_id": "alpha", "roster_position": "CPT",
             "projection": 27.0, "optimizer_run_id": "optimizer-1", "projection_run_id": "projection-1",
             "rule_run_id": "rules-1", "strategy": "showdown_gpp_captain_informed_v2", "objective": "gpp",
             "optimizer_created_at": NOW, "data_cutoff_at": NOW,
             "player_json": {"lineup_control_comparison": {"contract": "optimizer_matched_control_v1"}}},
            {"lineup_id": "lineup-1", "slot_index": 1, "player_id": "beta", "roster_position": "FLEX",
             "projection": 20.0, "optimizer_run_id": "optimizer-1", "projection_run_id": "projection-1",
             "rule_run_id": "rules-1", "strategy": "showdown_gpp_captain_informed_v2", "objective": "gpp",
             "optimizer_created_at": NOW, "data_cutoff_at": NOW, "player_json": {}},
        ],
        "assignments": [{
            "contest_id": "contest-1", "entry_id": "entry-1", "lineup_id": "lineup-1",
            "portfolio_id": "portfolio-1", "assignment_id": "assignment-1",
        }],
        "portfolios": [{"portfolio_id": "portfolio-1", "portfolio_name": "Week 1 GPP"}],
        "exports": [{
            "export_id": "export-1", "portfolio_id": "portfolio-1", "validation_id": "validation-1",
            "file_name": "lineups.csv", "row_count": 1, "content_sha256": "export-hash",
            "validation_status": "passed", "errors_json": [], "warnings_json": [],
        }],
        "rule_applications": [{
            "rule_run_id": "rules-1", "player_id": "alpha", "rule_id": "rule-1",
            "rule_version": 2, "mean_before": 18.0, "mean_after": 20.0,
        }],
        "beliefs": [{
            "belief_id": "belief-1", "belief_version_id": "belief-version-1", "scope_type": "player",
            "season": 2026, "week": 1, "slate": "SUNDAY_NIGHT", "subject_id": "beta",
            "direction": "boost", "strength": 4, "confidence": 70,
            "thought_text": "Beta is underprojected", "is_retrospective": False,
            "created_at": datetime(2026, 9, 14, 11, tzinfo=timezone.utc),
        }],
        "payout_tiers": [{
            "contest_id": "contest-1", "min_rank": 1, "max_rank": 10, "payout": 10,
        }],
    }


def test_report_links_exact_lineage_and_scores_each_evidence_domain():
    report = build_slate_learning_report(
        season=2026, week=1, slate="sunday_night", entry_user="wones0120",
        evidence=complete_evidence(), generated_at=NOW,
    )

    assert report["status"] == "completed"
    assert report["summary"] == {
        "contests": 1,
        "entries": 1,
        "identity_complete_entries": 1,
        "matched_optimizer_entries": 1,
        "entries_with_opt_007": 1,
        "duplicate_entries": 0,
        "projection_player_observations": 2,
        "projection_mae": 2.5,
        "projection_rmse": pytest.approx((13 / 2) ** 0.5),
    }
    entry = report["entries"][0]
    assert entry["lineup_match_basis"] == "contest_entry_assignment"
    assert entry["projected_points"] == 47.0
    assert entry["financial"]["profit"] == 5.0
    assert entry["players"][0]["rule_evaluations"][0]["improved"] is True
    assert report["beliefs"][0]["evaluation"] == "supported"
    assert report["run_ids"]["optimizer_run_ids"] == ["optimizer-1"]
    assert report["run_ids"]["export_ids"] == ["export-1"]
    assert report["source_file_ids"] == ["source-1"]


def test_report_marks_missing_identity_lineage_and_financials_without_inference():
    evidence = complete_evidence()
    evidence["observations"] = []
    evidence["assignments"] = []
    evidence["beliefs"] = []
    evidence["payout_tiers"] = []

    first = build_slate_learning_report(
        season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=evidence, generated_at=NOW,
    )
    second = build_slate_learning_report(
        season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=evidence, generated_at=NOW,
    )

    assert first["status"] == "partial"
    assert first["report_id"] == second["report_id"]
    assert first["entries"][0]["lineup_id"] is None
    assert first["entries"][0]["projected_points"] is None
    assert "entry:contest-1:entry-1:canonical_lineup" in first["missing_evidence"]
    assert "slate:projection_evaluation" in first["missing_evidence"]
    assert "slate:beliefs" in first["missing_evidence"]


def test_report_detects_actual_duplicate_lineups_and_captain_exposure():
    evidence = complete_evidence()
    duplicate = dict(evidence["entries"][0])
    duplicate["entry_id"] = "entry-2"
    duplicate["rank"] = 12
    evidence["entries"].append(duplicate)

    report = build_slate_learning_report(
        season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=evidence, generated_at=NOW,
    )

    assert report["summary"]["duplicate_entries"] == 1
    assert report["portfolio_analysis"]["captain_exposure"][0] == {
        "player_display_name": "Alpha One", "entries": 2, "pct": 100.0,
    }


def test_retrospective_belief_is_retained_but_never_scored_as_predictive():
    evidence = complete_evidence()
    evidence["beliefs"][0]["is_retrospective"] = True

    report = build_slate_learning_report(
        season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=evidence, generated_at=NOW,
    )

    assert report["beliefs"][0]["timing_status"] == "retrospective"
    assert report["beliefs"][0]["evaluation"] == "unscored"


def test_learn_003_scores_approved_belief_and_agent_answer_against_outcome():
    evidence = complete_evidence()
    evidence["belief_impacts"] = [{
        "preview_id": "preview-1", "belief_id": "belief-1",
        "belief_version_id": "belief-version-1", "policy_id": "belief_impact_v1",
        "target_player_id": "beta", "baseline_json": {"projection_mean": 20.0},
        "proposed_json": {"projection_mean": 22.0}, "decision_id": "decision-1",
        "decision": "approved",
        "decided_at": datetime(2026, 9, 14, 11, 30, tzinfo=timezone.utc),
    }]
    evidence["agent_questions"] = [{
        "question_id": "question-1", "answer_id": "answer-1",
        "policy_id": "agent_question_voi_v1",
        "trigger_type": "model_human_disagreement",
        "subject_player_id": "beta", "subject_label": "Beta Two",
        "question_text": "Which view?", "answer": "support_human",
        "context_json": {"model_projection_mean": 20.0, "human_projection_mean": 22.0},
        "resulting_modifier_json": {"projection_multiplier": 1.1},
        "answered_at": datetime(2026, 9, 14, 11, 45, tzinfo=timezone.utc),
    }]

    report = build_slate_learning_report(
        season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=evidence, generated_at=NOW,
    )

    assert report["beliefs"][0]["evaluation"] == "supported"
    assert report["beliefs"][0]["outcome_effect"] == "helped"
    assert report["agent_questions"][0]["outcome_effect"] == "helped"
    assert report["agent_questions"][0]["error_delta"] == -2.0
    assert report["learning_outcomes"]["beliefs"]["helped"] == 1
    assert report["learning_outcomes"]["beliefs"]["by_scope"]["player"]["helped"] == 1
    assert report["learning_outcomes"]["beliefs"]["by_confidence_band"]["medium_50_74"]["supported"] == 1
    assert report["learning_outcomes"]["agent_answers"]["helped"] == 1
    assert report["run_ids"]["agent_answer_ids"] == ["answer-1"]


def test_learn_003_retains_rejected_no_change_and_late_decisions_without_hindsight():
    evidence = complete_evidence()
    evidence["belief_impacts"] = [{
        "belief_id": "belief-1", "belief_version_id": "belief-version-1",
        "baseline_json": {"projection_mean": 20.0},
        "proposed_json": {"projection_mean": 22.0}, "decision": "rejected",
        "decided_at": datetime(2026, 9, 14, 11, 30, tzinfo=timezone.utc),
    }]
    evidence["agent_questions"] = [
        {
            "question_id": "question-no-change", "answer_id": "answer-no-change",
            "policy_id": "agent_question_voi_v1", "trigger_type": "high_value_uncertainty",
            "subject_player_id": "beta", "subject_label": "Beta Two",
            "question_text": "Any lean?", "answer": "no_change",
            "context_json": {"model_projection_mean": 20.0},
            "resulting_modifier_json": {},
            "answered_at": datetime(2026, 9, 14, 11, 40, tzinfo=timezone.utc),
        },
        {
            "question_id": "question-late", "answer_id": "answer-late",
            "policy_id": "agent_question_voi_v1", "trigger_type": "high_value_uncertainty",
            "subject_player_id": "beta", "subject_label": "Beta Two",
            "question_text": "Any lean?", "answer": "lean_upside",
            "context_json": {"model_projection_mean": 20.0},
            "resulting_modifier_json": {"projection_multiplier": 1.1},
            "answered_at": datetime(2026, 9, 14, 12, 30, tzinfo=timezone.utc),
        },
    ]

    report = build_slate_learning_report(
        season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=evidence, generated_at=NOW,
    )

    assert report["beliefs"][0]["outcome_effect"] == "hurt"
    assert report["agent_questions"][0]["outcome_effect"] == "no_measurable_effect"
    assert report["agent_questions"][1]["timing_status"] == "created_after_decision"
    assert report["agent_questions"][1]["outcome_effect"] == "unscored"


def test_learning_routes_return_reports_and_actionable_errors():
    report = build_slate_learning_report(
        season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=complete_evidence(), generated_at=NOW,
    )
    service = MagicMock()
    service.generate.return_value = report
    service.latest.return_value = report

    response = generate_slate_learning_report(
        SlateLearningReportRequest(
            season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120"
        ),
        service,
    )
    assert response.report_id == report["report_id"]
    assert get_latest_slate_learning_report(2026, 1, "SUNDAY_NIGHT", "wones0120", service).status == "completed"

    service.generate.side_effect = ValueError("No normalized contest results exist for this slate")
    with pytest.raises(HTTPException) as failure:
        generate_slate_learning_report(
            SlateLearningReportRequest(
                season=2026, week=2, slate="SUNDAY_MAIN", entry_user="wones0120"
            ),
            service,
        )
    assert failure.value.status_code == 422
    assert "No normalized contest results" in failure.value.detail
