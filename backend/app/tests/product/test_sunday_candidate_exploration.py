from scripts.validate_sunday_candidate_exploration import (
    injury_status,
    pareto_frontier,
    relative_percentiles,
    report_from_payload,
    selector_transition_crossovers,
)


def candidate(rank, objective, mean, p90, chalk, deficit):
    return {
        "shadow_rank": rank,
        "objective_score": objective,
        "mean": mean,
        "p90": p90,
        "relative_chalk": chalk,
        "sanity": {"total_football_sanity_deficit": deficit},
    }


def test_relative_percentiles_treat_higher_log_ownership_as_chalkier():
    assert relative_percentiles([-20.0, -15.0, -10.0]) == [0.0, 50.0, 100.0]


def test_pareto_frontier_removes_candidate_worse_on_every_dimension():
    best = candidate(1, 5.0, 140.0, 245.0, 60.0, 0.0)
    lower_chalk = candidate(2, 4.98, 139.8, 244.5, 30.0, 0.0)
    dominated = candidate(3, 4.90, 138.0, 240.0, 70.0, 0.2)

    frontier = pareto_frontier([best, lower_chalk, dominated])

    assert [row["shadow_rank"] for row in frontier] == [1, 2]


def test_report_lookup_finds_nested_complete_candidate_report():
    expected = {"all_candidates": [{"rank": 1}]}

    assert report_from_payload({"results": [[{"classic_small_field_report": expected}]]}) is expected


def test_injury_status_prefers_current_pregame_designation_and_preserves_missing():
    assert injury_status({"pregame_injury_status": "Q", "player_status": "ACT"}) == "Q"
    assert injury_status({"player_status": "D"}) == "D"
    assert injury_status({"injury_status": "OUT"}) == "OUT"
    assert injury_status({}) == ""


def test_selector_crossovers_follow_actual_winner_envelope():
    candidates = [
        {**candidate(1, 1.00, 100, 200, 90, 0), "standardized_chalk": 1.0},
        {**candidate(2, 0.96, 99, 199, 50, 0), "standardized_chalk": 0.0},
        {**candidate(3, 0.86, 98, 198, 10, 0), "standardized_chalk": -2.0},
        # This line intersects the leader but never wins the envelope.
        {**candidate(4, 0.90, 97, 197, 70, 0), "standardized_chalk": 0.5},
    ]

    transitions = selector_transition_crossovers(candidates)

    assert [row["candidate_rank"] for row in transitions] == [2, 3]
    assert [round(row["lambda"], 3) for row in transitions] == [0.04, 0.05]
