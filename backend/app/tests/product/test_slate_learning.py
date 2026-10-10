from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from backend.app.api.product_routes import (
    generate_slate_learning_report,
    generate_weekly_learning_report,
    get_latest_slate_learning_report,
    record_player_outcome_event,
)
from backend.app.product_schemas import (
    PlayerOutcomeEventRequest, SlateLearningReportRequest, WeeklyLearningReportRequest,
)
from backend.app.product_services.slate_learning import (
    build_slate_learning_report,
    build_weekly_learning_report,
    SlateLearningService,
)


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
             "player_json": {"lineup_control_comparison": {
                 "contract": "optimizer_matched_control_v1",
                 "control_lineup": [
                     {"player_id": "alpha", "roster_position": "CPT"},
                     {"player_id": "beta", "roster_position": "FLEX"},
                 ],
                 "scored_metrics": {"mean": 47, "individual_ceiling_sum": 60, "ownership_sum": 35},
                 "control_metrics": {"mean": 47, "individual_ceiling_sum": 60, "ownership_sum": 35},
             }}},
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


def test_report_uses_run_level_decision_snapshot_without_repeating_candidate_pool():
    evidence = complete_evidence()
    snapshot = {"contract_id": "decision_snapshot_v1", "source_file_ids": ["source-1"]}
    config = {"decision_snapshot": snapshot, "strategy_runtime": {"small_max": {
        "all_candidates": [{"players": [
            {"player_id": "alpha", "slot": "CPT"},
            *[{"player_id": player_id, "slot": "FLEX"}
              for player_id in ("beta", "gamma", "delta", "epsilon", "zeta")],
        ]}],
    }}}
    evidence["optimizer_runs"] = [{
        "optimizer_run_id": "optimizer-1", "contest_format": "showdown",
        "strategy": "showdown_gpp_captain_informed_v2", "constraint_config_json": config,
        "optimizer_created_at": NOW, "data_cutoff_at": NOW,
    }]
    baseline = deepcopy(evidence)
    for row in baseline["lineup_players"]:
        row["constraint_config_json"] = config

    report = build_slate_learning_report(
        season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=evidence, generated_at=NOW,
    )
    old_layout = build_slate_learning_report(
        season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=baseline, generated_at=NOW,
    )
    assert report["entries"][0]["decision_snapshot"] == snapshot
    assert report["entries"] == old_layout["entries"]
    assert report["optimizer_effectiveness"] == old_layout["optimizer_effectiveness"]
    assert report["optimizer_effectiveness"]["runs"][0]["candidate_pool"]["status"] == "original_candidate_pool"
    changed = deepcopy(evidence)
    changed["optimizer_runs"][0]["constraint_config_json"]["decision_snapshot"]["source_file_ids"] = ["source-2"]
    updated = build_slate_learning_report(
        season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=changed, generated_at=NOW,
    )
    assert updated["evidence_hash"] != report["evidence_hash"]


def test_evidence_loader_fetches_full_optimizer_configuration_only_per_run():
    service = SlateLearningService(engine=MagicMock())
    service._rows = MagicMock(side_effect=lambda connection, sql, params: (
        [{"contest_id": "contest-1"}] if "FROM target.dfs_contest c" in sql else []
    ))
    service._load_evidence(
        MagicMock(), season=2026, week=4, slate="SUNDAY_MAIN", entry_user="wones0120",
    )
    queries = [call.args[1] for call in service._rows.call_args_list]
    run_query = next(sql for sql in queries if "FROM target.optimizer_run\n" in sql)
    player_query = next(sql for sql in queries if "JOIN target.lineup_player player" in sql)
    assert "constraint_config_json" in run_query
    assert "constraint_config_json" not in player_query


def test_report_links_exact_lineage_and_scores_each_evidence_domain():
    report = build_slate_learning_report(
        season=2026, week=1, slate="sunday_night", entry_user="wones0120",
        evidence=complete_evidence(), generated_at=NOW,
    )

    assert report["status"] == "partial"
    assert report["optimizer_effectiveness"]["runs"][0]["status"] == "candidate_pool_unavailable"
    assert {key: report["summary"][key] for key in (
        "contests", "entries", "identity_complete_entries", "matched_optimizer_entries",
        "entries_with_opt_007", "duplicate_entries", "projection_player_observations",
        "projection_mae", "projection_rmse",
    )} == {
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
    assert entry["players"][0]["projected_points"] == 27.0
    assert entry["players"][0]["projected_base_points"] == 18.0
    assert entry["players"][0]["actual_points"] == 30.0
    assert entry["players"][0]["actual_base_points"] == 20.0
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
    assert report["summary"]["projection_player_observations"] == 4
    assert report["summary"]["unique_projection_observations"] == 2
    assert report["summary"]["total_amount_entered"] == 10
    assert report["summary"]["total_returned"] == 10
    assert report["summary"]["net_positive"] is False


def test_control_requires_every_players_actual_and_preserves_swap():
    evidence = complete_evidence()
    comparison = evidence["lineup_players"][0]["player_json"]["lineup_control_comparison"]
    comparison["control_lineup"][1] = {"player_id": "tracy", "roster_position": "FLEX"}
    comparison["selected_only"] = [{"player_id": "beta", "name": "Darnell Mooney"}]
    comparison["control_only"] = [{"player_id": "tracy", "name": "Tyrone Tracy Jr."}]
    report = build_slate_learning_report(
        season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=evidence, generated_at=NOW,
    )
    outcome = report["entries"][0]["opt_007_outcome"]
    assert outcome["status"] == "missing_player_actuals"
    assert outcome["control_actual_score"] is None
    assert outcome["missing_control_player_ids"] == ["tracy"]
    assert outcome["selected_only"][0]["name"] == "Darnell Mooney"
    assert "lineup:lineup-1:opt_007_control_actuals" in report["missing_evidence"]
    evidence["observations"].append({
        "contest_id": "contest-1", "player_display_name": "Tyrone Tracy Jr.",
        "roster_position": "FLEX", "player_id": "tracy", "resolution_status": "resolved",
        "actual_points": 12.0, "actual_ownership": 10.0,
    })
    rescored = build_slate_learning_report(
        season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=evidence, generated_at=NOW,
    )["entries"][0]["opt_007_outcome"]
    assert rescored["status"] == "complete"
    assert rescored["selected_actual_score"] == 52
    assert rescored["control_actual_score"] == 42
    assert rescored["actual_selected_minus_control"] == 10


def test_disruption_tag_requires_evidence_and_blocks_training_residual():
    evidence = complete_evidence()
    evidence["outcome_events"] = [{"player_id": "alpha", "tag": "IN_GAME_INJURY"}]
    report = build_slate_learning_report(
        season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=evidence, generated_at=NOW,
    )
    assert report["entries"][0]["players"][0]["outcome_tag"] == "UNKNOWN"
    evidence["outcome_events"][0]["evidence"] = "Official play-by-play event"
    report = build_slate_learning_report(
        season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=evidence, generated_at=NOW,
    )
    assert report["entries"][0]["players"][0]["outcome_tag"] == "IN_GAME_INJURY"
    assert report["entries"][0]["players"][0]["training_eligible_residual"] is False


def test_normal_variance_requires_explicit_evidence_and_counts_unique_training_labels():
    evidence = complete_evidence()
    extra = dict(evidence["entries"][0], entry_id="entry-2")
    evidence["entries"].append(extra)
    evidence["outcome_events"] = [{"player_id": "alpha", "tag": "NORMAL_VARIANCE",
                                    "evidence": "Completed game reviewed; ordinary participation.",
                                    "source_url": "https://example.org/game"}]
    report = build_slate_learning_report(
        season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=evidence, generated_at=NOW,
    )
    assert report["entries"][0]["players"][0]["training_eligible_residual"] is True
    assert report["entries"][0]["players"][1]["outcome_tag"] == "UNKNOWN"
    assert report["entries"][0]["players"][1]["training_eligible_residual"] is False
    assert report["summary"]["unique_outcome_counts"]["by_tag"]["NORMAL_VARIANCE"] == 1
    assert report["summary"]["unique_outcome_counts"]["by_tag"]["UNKNOWN"] == 1
    assert report["summary"]["unique_outcome_counts"]["training_eligible"] == 1
    assert report["summary"]["entry_weighted_outcome_counts"]["training_eligible"] == 2


def test_lineup_structure_does_not_claim_market_shootout():
    evidence = complete_evidence()
    player_json = evidence["lineup_players"][0]["player_json"]
    player_json["portfolio_game_script"] = {
        "script_id": "shootout", "kind": "shootout", "label": "Shootout",
        "reason_codes": ["both_teams_qb_pass_catcher"],
    }
    player_json.update({"market_context_point_in_time_safe": True,
                        "game_total_line": 42.5, "team_spread_line": -3.5,
                        "team_implied_total": 23.0, "player_team": "AAA"})
    report = build_slate_learning_report(
        season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=evidence, generated_at=NOW,
    )
    entry = report["entries"][0]
    assert entry["lineup_structure_family"]["family_id"] == "two_sided_pass_stack"
    assert entry["game_environment"]["game_totals"] == [42.5]
    assert entry["game_environment"]["team_spreads"] == {"AAA": -3.5}
    assert "label" not in entry["game_environment"]
    player_json["portfolio_game_script"] = {
        "script_id": "AAA_pass_led", "kind": "pass_led", "team": "AAA",
    }
    favorite = build_slate_learning_report(
        season=2026, week=1, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=evidence, generated_at=NOW,
    )["entries"][0]
    assert favorite["lineup_structure_family"]["family_id"] == "favorite_onslaught"


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
    assert get_latest_slate_learning_report(2026, 1, "SUNDAY_NIGHT", "wones0120", service).status == "partial"

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

    service.record_outcome_event.return_value = "event-1"
    result = record_player_outcome_event(PlayerOutcomeEventRequest(
        season=2026, week=2, slate="MONDAY_NIGHT", player_id="alpha",
        tag="NORMAL_VARIANCE", evidence="Completed-game review",
        source_url="https://example.org/game", observed_at=NOW,
    ), service)
    assert result == {"event_id": "event-1"}
    assert service.record_outcome_event.call_args.kwargs["tag"] == "NORMAL_VARIANCE"


def test_weekly_report_combines_discovered_slates_with_exact_child_lineage():
    first = build_slate_learning_report(
        season=2026, week=2, slate="THURSDAY_NIGHT", entry_user="wones0120",
        evidence=complete_evidence(), generated_at=NOW,
    )
    second_evidence = complete_evidence()
    second_evidence["contests"][0]["contest_id"] = "contest-2"
    second_evidence["entries"][0]["contest_id"] = "contest-2"
    second_evidence["entries"][0]["entry_id"] = "entry-2"
    second_evidence["contests"][0]["source_file_id"] = "source-2"
    second_evidence["entries"][0]["source_file_id"] = "source-2"
    for observation in second_evidence["observations"]:
        observation["contest_id"] = "contest-2"
    for tier in second_evidence["payout_tiers"]:
        tier["contest_id"] = "contest-2"
    second = build_slate_learning_report(
        season=2026, week=2, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=second_evidence, generated_at=NOW,
    )

    weekly = build_weekly_learning_report(
        season=2026, week=2, entry_user="wones0120",
        slate_reports=[first, second], generated_at=NOW,
    )
    reversed_order = build_weekly_learning_report(
        season=2026, week=2, entry_user="wones0120",
        slate_reports=[second, first], generated_at=NOW,
    )

    assert weekly["report_id"] == reversed_order["report_id"]
    assert weekly["summary"]["slates"] == 2
    assert weekly["summary"]["contests_entered"] == 2
    assert weekly["summary"]["entries"] == 2
    assert weekly["summary"]["entry_weighted_projection_observations"] == 4
    assert weekly["summary"]["entry_weighted_projection_mae"] == 2.5
    assert weekly["summary"]["net_positive_slates"] == 2
    assert weekly["summary"]["net_positive_slate_frequency"] == 1.0
    assert weekly["source_file_ids"] == ["source-1", "source-2"]
    assert {report["report_id"] for report in weekly["slate_reports"]} == {
        first["report_id"], second["report_id"],
    }
    service = MagicMock()
    service.generate_week.return_value = weekly
    response = generate_weekly_learning_report(
        WeeklyLearningReportRequest(season=2026, week=2, entry_user="wones0120"),
        service,
    )
    assert response.summary["contests_entered"] == 2


def test_multiweek_optimizer_rows_keep_format_strategy_and_evidence_status():
    current = build_slate_learning_report(
        season=2026, week=2, slate="SUNDAY_MAIN", entry_user="wones0120",
        evidence=complete_evidence(), generated_at=NOW,
    )
    current["optimizer_effectiveness"]["runs"] = [{
        "optimizer_run_id": "classic-run", "contest_format": "classic",
        "strategy": "classic_small_field_gpp", "status": "complete",
        "generated_count": 2, "selected_count": 1, "selected_scored_count": 1,
        "selection_regret_observed": 10,
        "correlations": {"objective_score": {"spearman": .2}},
        "field": {"contest-1": {
            "best_generated_field_rank": {"top_percent_conservative": 1},
            "best_selected_field_rank": {"top_percent_conservative": 10},
            "best_entered_field_rank": {"top_percent_conservative": 20},
            "attainment": {"cash": {"generated_scored": 1},
                           "top_10_percent": {"generated_scored": 1, "selected_scored": 1},
                           "top_1_percent": {"generated_scored": 1, "selected_scored": 0}},
        }},
    }]
    past = deepcopy(current)
    past["week"] = 1
    past["slate"] = "THURSDAY_NIGHT"
    past["optimizer_effectiveness"]["runs"][0].update(
        optimizer_run_id="showdown-run", contest_format="showdown",
        strategy="showdown_gpp_portfolio_v3", status="candidate_pool_unavailable",
    )
    weekly = build_weekly_learning_report(
        season=2026, week=2, entry_user="wones0120", slate_reports=[current],
        historical_slate_reports=[past], generated_at=NOW,
    )
    table = weekly["optimizer_effectiveness_history"]
    assert [(row["week"], row["contest_format"], row["strategy"]) for row in table] == [
        (1, "showdown", "showdown_gpp_portfolio_v3"),
        (2, "classic", "classic_small_field_gpp"),
    ]
    assert table[0]["candidate_cash_rate_scored"] is None
    assert table[1]["candidate_cash_rate_scored"] == .5
    assert table[1]["selected_top_1_rate_scored"] == 0


def test_aggregate_correlations_require_two_complete_predecision_slates():
    current = build_slate_learning_report(
        season=2026, week=2, slate="SUNDAY_MAIN", entry_user="wones0120",
        evidence=complete_evidence(), generated_at=NOW,
    )
    candidate_rows = [{"pregame": {"mean": value, "p90": value + 10,
                                   "objective_score": value / 10},
                       "postgame": {"actual_points": value * 2}}
                      for value in (1, 2, 3)]
    current["optimizer_effectiveness"]["runs"] = [{
        "optimizer_run_id": "run-current", "status": "complete", "contest_format": "classic",
        "chronological_validation": {"status": "predecision"},
        "candidates": candidate_rows, "field": {},
    }]
    past = deepcopy(current)
    past["week"] = 1
    past["optimizer_effectiveness"]["runs"][0]["optimizer_run_id"] = "run-past"
    weekly = build_weekly_learning_report(
        season=2026, week=2, entry_user="wones0120", slate_reports=[current],
        historical_slate_reports=[past], generated_at=NOW,
    )
    aggregate = weekly["optimizer_correlation_aggregate"]["classic"]
    assert aggregate["status"] == "available"
    assert aggregate["slates"] == 2
    assert aggregate["correlations"]["objective_score"]["n"] == 6
    past["optimizer_effectiveness"]["runs"][0]["chronological_validation"]["status"] = "unavailable"
    one = build_weekly_learning_report(
        season=2026, week=2, entry_user="wones0120", slate_reports=[current],
        historical_slate_reports=[past], generated_at=NOW,
    )
    assert one["optimizer_correlation_aggregate"]["classic"]["status"] == "insufficient_chronologically_valid_slates"

def test_weekly_net_positive_counts_are_null_without_complete_financial_evidence():
    evidence = complete_evidence()
    evidence["payout_tiers"] = []
    partial = build_slate_learning_report(
        season=2026, week=2, slate="SUNDAY_NIGHT", entry_user="wones0120",
        evidence=evidence, generated_at=NOW,
    )
    weekly = build_weekly_learning_report(
        season=2026, week=2, entry_user="wones0120", slate_reports=[partial],
        generated_at=NOW,
    )
    assert weekly["summary"]["net_positive_slates"] is None
    assert weekly["summary"]["net_positive_slate_frequency"] is None


def test_weekly_report_requires_imported_user_entries():
    with pytest.raises(ValueError, match="No imported contest results"):
        build_weekly_learning_report(
            season=2026, week=2, entry_user="wones0120", slate_reports=[],
        )
    service = MagicMock()
    service.generate_week.side_effect = ValueError(
        "No imported contest results exist for this user and week"
    )
    with pytest.raises(HTTPException) as failure:
        generate_weekly_learning_report(
            WeeklyLearningReportRequest(season=2026, week=2, entry_user="wones0120"),
            service,
        )
    assert failure.value.status_code == 422


def test_weekly_report_refreshes_requested_stats_once_before_all_slates():
    service = SlateLearningService(engine=MagicMock())
    service._ensure_schema = MagicMock()
    service._rows = MagicMock(side_effect=[
        [{"slate": "THURSDAY_NIGHT"}, {"slate": "SUNDAY_NIGHT"}], [],
    ])
    stats = {"status": "completed", "season": 2026, "week": 2, "rows_raw": 600,
             "snapshot_id": "stats-snapshot", "ingest_run_id": "stats-ingest",
             "content_sha256": "stats-hash"}
    service._refresh_weekly_stats = MagicMock(return_value=stats)
    service.generate = MagicMock(side_effect=lambda **scope: build_slate_learning_report(
        **scope, evidence=complete_evidence(), generated_at=NOW,
    ) | {"telemetry": {"loaded_configuration_count": 1, "candidate_count": 0}})
    calls = MagicMock()
    calls.attach_mock(service._refresh_weekly_stats, "refresh")
    calls.attach_mock(service.generate, "generate")

    report = service.generate_week(season=2026, week=2, entry_user=" wones0120 ")

    assert [call[0] for call in calls.mock_calls] == ["refresh", "generate", "generate"]
    service._refresh_weekly_stats.assert_called_once_with(season=2026, week=2)
    assert all(call.kwargs["week"] == 2 for call in service.generate.call_args_list)
    assert report["summary"]["weekly_stats"] == stats
    assert report["run_ids"]["weekly_stats_ingest"] == ["stats-ingest"]
    assert report["run_ids"]["source_snapshot"] == ["stats-snapshot"]
    response = generate_weekly_learning_report(
        WeeklyLearningReportRequest(season=2026, week=2, entry_user="wones0120"),
        MagicMock(generate_week=MagicMock(return_value=report)),
    )
    assert response.summary["weekly_stats"] == stats
    corrected_stats = {**stats, "content_sha256": "corrected-hash"}
    corrected = build_weekly_learning_report(
        season=2026, week=2, entry_user="wones0120",
        slate_reports=report["slate_reports"], weekly_stats=corrected_stats,
    )
    assert corrected["evidence_hash"] != report["evidence_hash"]


@pytest.mark.parametrize("entry_user", ["", "wones0120"])
def test_weekly_report_does_not_fetch_stats_without_valid_entries(entry_user):
    service = SlateLearningService(engine=MagicMock())
    service._ensure_schema = MagicMock()
    service._rows = MagicMock(return_value=[])
    service._refresh_weekly_stats = MagicMock()
    with pytest.raises(ValueError):
        service.generate_week(season=2026, week=2, entry_user=entry_user)
    service._refresh_weekly_stats.assert_not_called()


def test_weekly_stats_refresh_failure_blocks_report_and_returns_actionable_error():
    service = SlateLearningService(engine=MagicMock())
    service._ensure_schema = MagicMock()
    service._rows = MagicMock(return_value=[{"slate": "SUNDAY_MAIN"}])
    service._refresh_weekly_stats = MagicMock(side_effect=ValueError(
        "Weekly stats refresh failed for season 2026, week 2: source unavailable"
    ))
    service.generate = MagicMock()
    with pytest.raises(HTTPException) as failure:
        generate_weekly_learning_report(
            WeeklyLearningReportRequest(season=2026, week=2, entry_user="wones0120"),
            service,
        )
    assert failure.value.status_code == 422
    assert "week 2: source unavailable" in failure.value.detail
    service.generate.assert_not_called()
