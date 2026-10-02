import pytest

from backend.app.product_services.centrality_shadow import (
    crossover_points,
    lineup_football_metrics,
    prepare_candidates,
    ranked_at_lambda,
)


def _candidate(player_ids, objective):
    return {
        "player_ids": player_ids,
        "objective_score": objective,
        "roster": [
            {"player_id": player_id, "name": player_id, "position": "WR"}
            for player_id in player_ids
        ],
    }


def test_stale_centrality_gets_no_positive_selector_influence():
    candidate = _candidate(["current", "stale"], 1.0)
    core = {
        "current": {"overall_centrality": 0.8, "overall_core": True,
                    "current_evidence_confidence": "high_current",
                    "football_classification": "core receiving player"},
        "stale": {"overall_centrality": 1.0, "overall_core": True,
                  "current_evidence_confidence": "stale_2025_primary",
                  "football_classification": "core receiving player"},
    }
    result = lineup_football_metrics(candidate, core)
    assert result["football_centrality"] == pytest.approx(0.8)
    assert result["average_overall_centrality"] == pytest.approx(0.9)
    assert result["stale_evidence_count"] == 1

    current_only = lineup_football_metrics(_candidate(["current"], 1.0), core)
    assert result["football_centrality"] == current_only["football_centrality"]


def test_standardized_signal_and_lambda_ranking():
    candidates, stats = prepare_candidates(
        [_candidate(["low"], 1.0), _candidate(["high"], 0.9)],
        {"low": {"overall_centrality": 0.2, "current_evidence_confidence": "high_current"},
         "high": {"overall_centrality": 0.8, "current_evidence_confidence": "high_current"}},
    )
    assert stats["mean"] == pytest.approx(0.5)
    assert stats["std"] == pytest.approx(0.3)
    assert ranked_at_lambda(candidates, 0.0)[0]["player_ids"] == ["low"]
    assert ranked_at_lambda(candidates, 0.1)[0]["player_ids"] == ["high"]


def test_crossover_is_analytic_upper_envelope():
    candidates, _ = prepare_candidates(
        [_candidate(["control"], 1.0), _candidate(["middle"], 0.95),
         _candidate(["high"], 0.8)],
        {"control": {"overall_centrality": 0.2, "current_evidence_confidence": "high_current"},
         "middle": {"overall_centrality": 0.5, "current_evidence_confidence": "high_current"},
         "high": {"overall_centrality": 0.9, "current_evidence_confidence": "high_current"}},
    )
    changes = crossover_points(candidates)
    assert changes[0]["candidate"]["player_ids"] == ["control"]
    assert changes[-1]["candidate"]["player_ids"] == ["high"]
    assert all(changes[index]["lambda"] <= changes[index + 1]["lambda"]
               for index in range(len(changes) - 1))
