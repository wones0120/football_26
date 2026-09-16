from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from backend.app.api.product_routes import answer_agent_question, generate_agent_questions
from backend.app.product_schemas import AgentQuestionAnswerRequest, AgentQuestionGenerateRequest
from backend.app.product_services.agent_questions import (
    QUESTION_POLICY_ID,
    build_agent_questions,
)


NOW = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)


def variant_set():
    return {
        "variant_set_id": "variants-1",
        "projection_run_id": "projections-1",
        "season": 2026,
        "week": 2,
        "slate": "SUNDAY_MAIN",
        "created_at": NOW,
    }


def artifacts():
    return {
        "model_only": {
            "players": [
                {
                    "player_id": "alpha",
                    "player_label": "Alpha One",
                    "projection_mean": 20.0,
                    "projection_p10": 9.0,
                    "projection_p90": 33.0,
                },
                {
                    "player_id": "beta",
                    "player_label": "Beta Two",
                    "projection_mean": 15.0,
                    "projection_p10": 7.0,
                    "projection_p90": 25.0,
                },
                {
                    "player_id": "low",
                    "player_label": "Low Value",
                    "projection_mean": 3.0,
                    "projection_p10": 1.0,
                    "projection_p90": 6.0,
                },
            ]
        },
        "human_only": {
            "players": [
                {
                    "player_id": "alpha",
                    "projection_multiplier": 1.08,
                    "approved_inputs": [{"decision_id": "decision-1"}],
                }
            ]
        },
    }


def test_voi_policy_only_asks_high_value_replayable_questions():
    questions = build_agent_questions(variant_set=variant_set(), artifacts=artifacts())

    assert [row["trigger_type"] for row in questions] == [
        "model_human_disagreement",
        "high_value_uncertainty",
    ]
    assert questions[0]["subject_player_id"] == "alpha"
    assert questions[0]["policy_id"] == QUESTION_POLICY_ID
    assert questions[0]["context"]["answer_modifiers"]["support_human"][
        "projection_multiplier"
    ] == 1.08
    assert questions[1]["subject_player_id"] == "beta"
    assert questions[1]["context"]["answer_modifiers"]["lean_upside"][
        "status"
    ] == "recorded_not_applied"
    assert all(row["subject_player_id"] != "low" for row in questions)


def test_question_identity_is_deterministic_and_policy_versioned():
    first = build_agent_questions(variant_set=variant_set(), artifacts=artifacts())
    second = build_agent_questions(variant_set=variant_set(), artifacts=artifacts())

    assert [row["question_id"] for row in first] == [row["question_id"] for row in second]
    assert [row["evidence_hash"] for row in first] == [row["evidence_hash"] for row in second]


def test_questions_are_not_created_for_small_or_incomplete_signals():
    rows = artifacts()
    rows["human_only"]["players"][0]["projection_multiplier"] = 1.01
    rows["model_only"]["players"][1]["projection_p90"] = None

    assert build_agent_questions(variant_set=variant_set(), artifacts=rows) == []


def test_question_routes_return_results_and_actionable_errors():
    service = MagicMock()
    list_result = {
        "policy_id": QUESTION_POLICY_ID,
        "policy": {"policy_id": QUESTION_POLICY_ID},
        "rows": [],
        "summary": {"total": 0, "pending": 0, "answered": 0},
    }
    service.generate.return_value = list_result
    response = generate_agent_questions(
        AgentQuestionGenerateRequest(season=2026, week=2, slate="SUNDAY_MAIN"), service
    )
    assert response.policy_id == QUESTION_POLICY_ID

    service.answer.side_effect = ValueError("Agent question not found: missing")
    with pytest.raises(HTTPException) as failure:
        answer_agent_question(
            "missing", AgentQuestionAnswerRequest(answer="no_change"), service
        )
    assert failure.value.status_code == 404
