import pytest

from backend.app.product_services.optimizer import OptimizerService
from backend.app.product_services.showdown_single_entry import select_single_entry_lineups


def lineup(captain="a", mean=100.0, solver=100.0):
    players = []
    for index, player_id in enumerate(("a", "b", "c", "d", "e", "f")):
        players.append({
            "player_id": player_id,
            "name": player_id,
            "player_team": "DET" if index < 3 else "GB",
            "position": "QB" if index in (0, 3) else "WR",
            "roster_position": "CPT" if player_id == captain else "FLEX",
            "projection": mean / 6,
            "p90": mean / 3,
            "salary": 7000,
            "ownership": 20.0,
            "showdown_qb_eligible": True,
        })
    players[0]["solver_objective_value"] = solver
    players[0]["lineup_correlation_summary"] = {"total_adjustment": 1.0}
    return players


def test_single_entry_portfolio_can_repeat_the_best_lineup():
    best = lineup()
    weak = lineup(captain="b", mean=80, solver=80)
    selected, report = select_single_entry_lineups([best, weak], num_contests=3)
    assert [row[0]["single_entry_assignment"]["candidate_rank"] for row in selected] == [1, 1, 1]
    assert report["unique_lineups"] == 1
    assert report["payout_metrics_status"] == "unavailable_without_field_and_payout_simulation"
    assert next(row for row in selected[0] if row["roster_position"] == "CPT")["single_entry_report"] == report
    valid, reason = OptimizerService._validate_showdown_lineups(
        selected, requested_lineups=3, max_exposure=1.0,
        portfolio_policy=True, allow_duplicate_lineups=True,
    )
    assert valid, reason


def test_close_alternate_may_cover_different_captain():
    best = lineup()
    alternate = lineup(captain="b", mean=99.8, solver=99.8)
    selected, report = select_single_entry_lineups([best, alternate], num_contests=3)
    assert len(selected) == 3
    assert report["unique_lineups"] == 2
    assert report["recommended_structure"] == "A / B / A"
    assert report["portfolio_comparisons"]["best_one_alternate"]["heuristic_delta_vs_aaa"] > 0
    assert any("different Captain" in row["reason"] for row in report["assignments"])
    alternate_report = report["top_alternates"]["different_captain_only"]
    assert alternate_report["shared_players_with_a"] == 6
    assert alternate_report["overlap_percentage_vs_a"] == 100.0
    assert alternate_report["jaccard_similarity_vs_a"] == 1.0
    assert alternate_report["diversification_benefit_vs_a"] > alternate_report["quality_loss_vs_a"]


def test_two_close_alternates_can_win_without_forcing_diversity():
    _, report = select_single_entry_lineups(
        [lineup(captain="a"), lineup(captain="b"), lineup(captain="c")],
        num_contests=3,
    )
    assert report["recommended_structure"] == "A / B / C"
    assert report["evaluated_portfolio_count"] == 6
    assert report["portfolio_comparisons"]["best_repeated_alternate"]["structure"] == "A / B / B"
    assert report["portfolio_comparisons"]["best_two_alternates"]["heuristic_delta_vs_aaa"] > report["portfolio_comparisons"]["best_one_alternate"]["heuristic_delta_vs_aaa"]


def test_featured_alternates_include_material_players_and_other_script():
    best = lineup()
    material = lineup(captain="b", mean=98)
    for row, replacement in zip(material[-2:], ("g", "h")):
        row["player_id"] = replacement
        row["name"] = replacement
    different_script = lineup(captain="a", mean=97)
    different_script[3]["position"] = "K"
    different_script[3]["player_id"] = "i"
    different_script[3]["name"] = "i"
    _, report = select_single_entry_lineups(
        [best, material, different_script], num_contests=3,
    )
    featured = report["top_alternates"]
    assert featured["different_captain_only"] is None
    assert featured["different_captain_material_players"]["player_changes_vs_a"] == 2
    assert featured["different_game_script"]["game_script"]["script_id"] != report["candidates"][0]["game_script"]["script_id"]


def test_contest_metadata_must_be_single_entry_and_match_count():
    with pytest.raises(ValueError, match="one item"):
        select_single_entry_lineups([lineup()], num_contests=3, contest_metadata=[{}])
    with pytest.raises(ValueError, match="exactly one"):
        select_single_entry_lineups([lineup()], num_contests=1, contest_metadata=[{"maximum_entries": 2}])


def test_more_than_three_contests_can_repeat_lineup_and_keep_assignment_ids():
    metadata = [{"contest_id": str(index), "name": f"Contest {index}", "maximum_entries": 1} for index in range(5)]
    selected, report = select_single_entry_lineups([lineup(), lineup(captain="b", mean=80, solver=80)], num_contests=5, contest_metadata=metadata)
    assert len(selected) == 5
    assert report["recommended_structure"] == "A / A / A / A / A"
    assert [row["contest_id"] for row in report["assignments"]] == ["0", "1", "2", "3", "4"]
