from collections import Counter

import pytest
import pandas as pd

from backend.app.product_schemas import OptimizerRunRequest
from backend.app.product_services.optimizer import (
    OptimizerService, place_small_max_metadata_on_captain, resolve_optimizer_strategy,
)
from backend.app.product_services.showdown_three_max import (
    select_generic_small_max_lineups, select_small_max_lineups, select_three_max_lineups,
    validate_small_max_contest, validate_three_max_contest,
)
from backend.app.product_services.showdown_contests import validate_entry_limit_contest

from .test_showdown_single_entry import lineup


def contest(maximum_entries=3):
    return {
        "contest_id": "example-3max", "name": "Example 3-max", "slate": "DET @ BUF",
        "draft_group_id": 1, "entry_fee": 3, "capacity": 100,
        "current_entries": 80, "prize_pool": 200, "paid_places": 20,
        "payout_ladder": [
            {"from": 1, "to": 1, "cash": 100},
            {"from": 2, "to": 10, "cash": 10},
            {"from": 11, "to": 20, "cash": 1},
        ],
        "maximum_entries": maximum_entries, "lock_time": "2027-09-17T20:15:00Z",
        "state": "Upcoming", "unavailable_fields": [],
    }


def candidates():
    first = lineup(captain="a", mean=100)
    same_captain = lineup(captain="a", mean=99)
    same_captain[-1]["player_id"] = "g"
    same_captain[-1]["name"] = "g"
    alternate = lineup(captain="b", mean=98)
    alternate[-2]["player_id"] = "h"
    alternate[-2]["name"] = "h"
    return [first, same_captain, alternate]


def test_three_max_is_a_separate_showdown_strategy_with_multiple_te_allowed():
    resolved = resolve_optimizer_strategy(contest_format="showdown", objective="gpp", strategy="showdown_3max_gpp")
    assert resolved["engine"] == "global_three_max_candidate_selector"
    request = OptimizerRunRequest.model_validate({
        "season": 2026, "week": 2, "slate": "THURSDAY_NIGHT",
        "strategy": "showdown_3max_gpp", "contest_format": "showdown", "objective": "gpp",
        "params": {"enforce_single_te": True, "contest_urls": ["https://www.draftkings.com/draft/contest/123"]},
    })
    assert request.params["enforce_single_te"] is False
    default = OptimizerRunRequest.model_validate({
        "season": 2026, "week": 2, "slate": "THURSDAY_NIGHT",
        "strategy": "showdown_3max_gpp", "contest_format": "showdown", "objective": "gpp",
        "params": {},
    })
    assert default.params["enforce_single_te"] is False


def test_global_three_max_selects_unique_lineups_and_reports_all_counts():
    selected, report = select_three_max_lineups(candidates(), contest=contest(), entries_to_use=3)
    assert len(selected) == 3
    assert len({tuple(sorted((row["player_id"], row["roster_position"]) for row in lineup_rows)) for lineup_rows in selected}) == 3
    assert [row is not None for row in report["count_comparisons"]] == [True, True, True]
    assert report["selected"]["total_entry_fees"] == 9
    assert len(report["selected"]["pairwise"]) == 3
    assert max(Counter(next(row["player_id"] for row in lineup_rows if row["roster_position"] == "CPT") for lineup_rows in selected).values()) <= 2
    assert len(report["leave_one_out"]) == 3
    assert report["leave_one_out"][0]["objective_change_if_removed"] == pytest.approx(
        -report["leave_one_out"][0]["contribution_to_selected_objective"]
    )
    assert selected[0][0]["three_max_report"] == report
    valid, reason = OptimizerService._validate_showdown_lineups(
        selected, requested_lineups=3, max_exposure=1.0,
        portfolio_policy=True,
        portfolio_exposure_rates={"captain": 2 / 3, "core": 1.0, "starting_qb": 1.0, "cheap_punt": 2 / 3},
        enforce_single_te=True,
    )
    assert valid, reason


def test_auto_count_can_choose_less_than_three_and_never_fabricates_lineups():
    selected, report = select_three_max_lineups(candidates()[:2], contest=contest(), entries_to_use="auto")
    assert len(selected) <= 2
    assert report["count_comparisons"][2] is None
    assert report["selected_count"] == len(selected)
    assert report["selected"]["portfolio_objective"] == max(row["portfolio_objective"] for row in report["count_comparisons"] if row)
    forced, forced_report = select_three_max_lineups(candidates()[:2], contest=contest(), entries_to_use=3)
    assert len(forced) == 2
    assert forced_report["selected_count"] == 2


def test_three_max_rejects_wrong_contest_entry_limit():
    with pytest.raises(ValueError, match="expected 3-max"):
        validate_three_max_contest(contest(maximum_entries=5))
    five = validate_entry_limit_contest(contest(maximum_entries=5), maximum_entries=5)
    assert five["maximum_entries"] == 5
    assert five["economics"]["paid_percentage"] == pytest.approx(.2)
    disguised = {**contest(maximum_entries=5), "source_payload": {"contestDetail": {"maximumEntriesPerUser": 1}}}
    with pytest.raises(ValueError, match="DraftKings page allows 1"):
        validate_entry_limit_contest(disguised, maximum_entries=5)


def test_small_max_reads_five_entry_limit_and_compares_every_count():
    resolved = resolve_optimizer_strategy(contest_format="showdown", objective="gpp", strategy="showdown_small_max_gpp")
    assert resolved["engine"] == "global_small_max_candidate_selector"
    request = OptimizerRunRequest.model_validate({
        "season": 2026, "week": 2, "slate": "THURSDAY_NIGHT",
        "strategy": "showdown_small_max_gpp", "contest_format": "showdown", "objective": "gpp",
        "params": {"contest_urls": ["https://www.draftkings.com/draft/contest/123"]},
    })
    assert request.params["enforce_single_te"] is False
    five = validate_small_max_contest(contest(maximum_entries=5))
    pool = []
    for index, mean in enumerate((100, 98, 96, 94, 91)):
        candidate = lineup(captain="a", mean=mean, solver=mean)
        candidate[-1]["player_id"] = f"value-{index}"
        candidate[-1]["name"] = f"value-{index}"
        pool.append(candidate)
    selected, report = select_small_max_lineups(pool, contest=five, entries_to_use="auto")
    assert len(report["count_comparisons"]) == 5
    assert all(row is not None for row in report["count_comparisons"])
    assert report["searched_candidate_count"] == 5
    assert report["exposure_rates"]["core"] == 1.0
    assert report["count_marginals"][4]["entry_count"] == 5
    assert report["count_marginals"][4]["added_lineups"][0]["mean"] == pytest.approx(91)
    assert len(selected) == report["selected_count"] <= 5
    assert selected[0][0]["small_max_report"] == report
    with pytest.raises(ValueError, match="1 through 5"):
        select_small_max_lineups(pool, contest=five, entries_to_use=6)


def test_generic_small_max_auto_selects_best_single_lineup_without_contest_economics():
    selected, report = select_generic_small_max_lineups(candidates(), maximum_entries=3)
    assert len(selected) == report["selected_count"] == 1
    assert report["contest_mode"] == "generic"
    assert report["contest"] is None
    assert report["selection_mode"] == "auto"
    assert report["selected"]["candidate_ranks"] == [1]
    assert len(report["count_comparisons"]) == 3
    assert all("payout_proxy" not in row and "total_entry_fees" not in row
               for row in report["count_comparisons"] if row)
    assert selected[0][0]["small_max_report"] == report


def test_generic_small_max_configured_entries_respect_exposure_and_limit():
    selected, report = select_generic_small_max_lineups(
        candidates(), maximum_entries=3, entries_to_use=3,
        exposure_rates={"captain": .5},
    )
    assert len(selected) == report["selected_count"] == 3
    assert report["configured_entry_count"] == 3
    assert report["selected"]["captain_exposures"]["a"] == pytest.approx(2 / 3)
    with pytest.raises(ValueError, match="2 through 5"):
        select_generic_small_max_lineups(candidates(), maximum_entries=1)
    with pytest.raises(ValueError, match="1 through 3"):
        select_generic_small_max_lineups(candidates(), maximum_entries=3, entries_to_use=4)


def test_auto_chooses_best_count_and_forced_count_is_reported_separately(monkeypatch):
    from backend.app.product_services import showdown_three_max as selector

    def decreasing_proxy(subset):
        value = .6 - .08 * len(subset)
        return {"independent_rank_proxy": value, "shared_percentile_proxy": value}

    monkeypatch.setattr(selector, "_profit_proxy", decreasing_proxy)
    pool = []
    for index in range(5):
        candidate = lineup(captain="a", mean=100 - index, solver=100 - index)
        candidate[-1]["player_id"] = f"value-{index}"
        candidate[-1]["name"] = f"value-{index}"
        pool.append(candidate)
    auto, auto_report = select_small_max_lineups(pool, contest=contest(maximum_entries=5), entries_to_use="auto")
    objectives = [row["portfolio_objective"] for row in auto_report["count_comparisons"]]
    assert all(left > right for left, right in zip(objectives, objectives[1:]))
    assert len(auto) == auto_report["selected_count"] == auto_report["auto_recommended_count"] == 1
    assert auto_report["selection_mode"] == "auto"
    assert auto_report["candidate_count"] == auto_report["serialized_candidate_count"]
    assert len(auto_report["all_candidates"]) == auto_report["candidate_count"]
    forced, forced_report = select_small_max_lineups(pool, contest=contest(maximum_entries=5), entries_to_use=5)
    assert len(forced) == forced_report["selected_count"] == forced_report["configured_entry_count"] == 5
    assert forced_report["auto_recommended_count"] == 1
    assert forced_report["selection_mode"] == "configured"


def test_candidate_chalk_survives_captain_sorting():
    candidate = lineup(captain="b")
    selected, report = select_small_max_lineups([candidate], contest=contest(maximum_entries=5))
    selected[0].sort(key=lambda row: 0 if row["roster_position"] == "CPT" else 1)
    place_small_max_metadata_on_captain(selected[0])
    assert selected[0][0]["roster_position"] == "CPT"
    assert selected[0][0]["lineup_duplication_risk"]["relative_chalk_score"] == pytest.approx(
        report["selected"]["lineups"][0]["relative_chalk"]
    )
    assert selected[0][0]["small_max_report"] == report


def test_count_deltas_name_added_and_removed_candidates_for_non_nested_optima(monkeypatch):
    from backend.app.product_services import showdown_three_max as selector

    original_summary = selector._summary

    def prefer_non_nested_sets(rows, contest_row, proxy, reference_score):
        summary = original_summary(rows, contest_row, proxy, reference_score)
        ranks = {row["rank"] for row in rows}
        if ranks == {1} or ranks == {2, 3}:
            summary["portfolio_objective"] += 1
        return summary

    monkeypatch.setattr(selector, "_summary", prefer_non_nested_sets)
    selected, report = select_small_max_lineups(candidates(), contest=contest(), entries_to_use="auto")
    assert report["count_comparisons"][0]["candidate_ranks"] == [1]
    assert report["count_comparisons"][1]["candidate_ranks"] == [2, 3]
    comparison = report["count_marginals"][1]
    assert comparison["from_count"] == 1
    assert comparison["entry_count"] == 2
    assert comparison["added_candidate_ranks"] == [2, 3]
    assert comparison["removed_candidate_ranks"] == [1]
    assert comparison["fee_delta"] == pytest.approx(contest()["entry_fee"])
    assert len(report["leave_one_out"]) == len(selected)


def test_three_max_uses_existing_multiple_te_candidate_and_final_validation():
    positions = ("QB", "TE", "TE", "WR", "WR", "RB", "WR")
    pool = pd.DataFrame([
        {"player_id": f"te-p{index}", "name": f"Player {index}", "position": position,
         "player_team": "DET" if index < 4 else "BUF", "opponent_team": "BUF" if index < 4 else "DET",
         "salary": 5000, "projection": 12.0, "p90": 23.0,
         "showdown_qb_eligible": position == "QB", "ownership": 10.0}
        for index, position in enumerate(positions)
    ])
    service = OptimizerService.__new__(OptimizerService)
    candidate = service._solve_lineup(pool, contest_type="captain", enforce_single_te=False,
                                      include_control_comparison=False)
    assert candidate is not None
    selected, _ = select_three_max_lineups([candidate], contest=contest(), entries_to_use=3)
    assert len(selected) == 1
    assert sum(row["position"] == "TE" for row in selected[0]) == 2
    valid, reason = service._validate_showdown_lineups(
        selected, requested_lineups=3, max_exposure=1.0,
        enforce_single_te=False,
    )
    assert valid, reason
