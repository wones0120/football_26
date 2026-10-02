from backend.app.product_services.classic_frontier_diagnostic import (
    candidate_ownership, lineup_key, select_portfolio,
)


def _candidate(ids, qb, score):
    return {"player_ids": ids, "qb": {"player_id": qb},
            "objective_score": score}


def test_ownership_is_unavailable_for_any_missing_player() -> None:
    candidate = _candidate(["a", "b"], "a", 1.0)
    missing = candidate_ownership(candidate, {"a": 20.0})
    assert missing["status"] == "unavailable"
    assert missing["ownership_sum"] is None
    assert missing["leverage_sum"] is None
    assert missing["missing_player_ids"] == ["b"]

    complete = candidate_ownership(candidate, {"a": 20.0, "b": 5.0})
    assert complete["ownership_sum"] == 25.0
    assert complete["leverage_sum"] is None
    assert complete["high_owned_count"] == 0


def test_lineup_key_uses_player_ids_not_names_or_order() -> None:
    assert lineup_key(_candidate(["b", "a"], "a", 1.0)) == ("a", "b")


def test_portfolio_prefers_quality_subject_to_qb_and_overlap_paths() -> None:
    candidates = [
        _candidate(["q1", "a", "b"], "q1", 10),
        _candidate(["q1", "a", "c"], "q1", 9),
        _candidate(["q2", "d", "e"], "q2", 8),
        _candidate(["q3", "f", "g"], "q3", 7),
    ]
    result = select_portfolio(candidates, 3, max_overlap=1,
                              max_same_qb=2, min_distinct_qbs=3)
    assert result["status"] == "optimal"
    assert result["indices"] == [0, 2, 3]


def test_portfolio_distinguishes_primary_paths_from_player_churn() -> None:
    candidates = [
        {**_candidate(["q1", "a", "b"], "q1", 10),
         "primary_game": "A-B", "stack": {"type": "QB+2"}},
        {**_candidate(["q1", "c", "d"], "q1", 9),
         "primary_game": "A-B", "stack": {"type": "QB+2"}},
        {**_candidate(["q2", "e", "f"], "q2", 8),
         "primary_game": "C-D", "stack": {"type": "QB+1"}},
    ]
    result = select_portfolio(candidates, 2, max_overlap=1,
                              distinct_primary_paths=True)
    assert result["indices"] == [0, 2]


def test_portfolio_can_stress_an_alternate_objective_without_losing_selector_sum() -> None:
    candidates = [
        _candidate(["q1", "a"], "q1", 10),
        _candidate(["q2", "b"], "q2", 8),
    ]
    result = select_portfolio(candidates, 1, max_overlap=1,
                              objective_values=[-10, -2])
    assert result["indices"] == [1]
    assert result["score_sum"] == 8
    assert result["optimized_objective_sum"] == -2
