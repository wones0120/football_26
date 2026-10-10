from copy import deepcopy

import pytest

from backend.app.product_services.showdown_portfolio_selection import select_showdown_portfolio, signature
from backend.app.product_services.optimizer import OptimizerService


def candidate(captain, flex, selector, *, scenario=False, mean=100, p90=150):
    rows = [{"player_id": pid, "name": pid, "player_team": "A" if i < (3 if scenario else 2) else "B",
             "roster_position": "CPT" if i == 0 else "FLEX", "salary": 5000,
             "projection": mean / 6, "p90": p90 / 6}
            for i, pid in enumerate([captain, *flex])]
    rows[0]["solver_objective_value"] = selector
    if scenario:
        rows[0].update(showdown_scenario_id="a_win", showdown_scenario={"conditioned_winner": "A"})
        for row in rows:
            row.update(conditioned_projection=mean / 6 * 1.1, conditioned_p90=p90 / 6 * 1.1)
    return rows


def pool():
    return [candidate("b1", ["shared1", "shared2", "shared3", "shared4", "x"], 100),
            candidate("b2", ["shared1", "shared2", "shared3", "shared4", "y"], 99),
            candidate("a", ["a1", "a2", "a3", "a4", "a5"], 98.5, scenario=True)]


def select(candidates, *, soft=True, requested=2, limits=None, captain_limit=2):
    return select_showdown_portfolio(candidates, requested=requested, player_limits=limits or {},
                                    captain_limit=captain_limit, soft_scenario_diversity=soft)


def test_small_opportunity_cost_earns_real_roster_and_captain_diversity():
    candidates = pool()
    ordinary, _ = select(deepcopy(candidates), soft=False)
    chosen, report = select(candidates)
    assert [l[0]["player_id"] for l in ordinary] == ["b1", "b2"]
    assert [l[0]["player_id"] for l in chosen] == ["b1", "a"]
    assert report["scenario_diversity_affected_portfolio"]
    witness = report["selected_scenario_credits"][0]
    assert witness["forced_baseline_portfolio_opportunity_cost"] == pytest.approx(0.5)
    assert 0.5 < witness["credit"] <= 1.99 + 1e-6
    assert report["baseline_portfolio_selector"] - report["selected_portfolio_selector"] <= witness["credit"]


def test_scenario_labels_cannot_replace_physical_diversity():
    candidates = pool()[:2]
    duplicate = deepcopy(candidates[0])
    duplicate[0].update(showdown_scenario_id="a_win", showdown_scenario={"conditioned_winner": "A"})
    for row in duplicate:
        row.update(conditioned_projection=row["projection"] * 1.2, conditioned_p90=row["p90"] * 1.2)
    chosen, report = select([*candidates, duplicate])
    assert {signature(l) for l in chosen} == {signature(l) for l in candidates}
    assert not report["scenario_diversity_affected_portfolio"]
    conditional = next(m for m in report["ranked_metrics"] if m["scenario_id"] == "a_win")
    assert conditional["scenario_value"]["credit"] == 0
    assert len({signature(l) for l in chosen}) == len(chosen)


@pytest.mark.parametrize("mean,p90,selector", [(90, 150, 98.5), (100, 135, 98.5), (100, 150, 90)])
def test_does_not_relax_quality_or_force_inferior_candidate(mean, p90, selector):
    candidates = pool()[:2] + [candidate("a", ["a1", "a2", "a3", "a4", "a5"], selector,
                                       scenario=True, mean=mean, p90=p90)]
    chosen, _ = select(candidates)
    assert [l[0]["player_id"] for l in chosen] == ["b1", "b2"]


def test_no_uplift_or_no_evidence_earns_no_reward():
    for missing in [True, False]:
        candidates = pool()
        for row in candidates[-1]:
            if missing:
                row.pop("conditioned_projection")
                row.pop("conditioned_p90")
            else:
                row.update(conditioned_projection=row["projection"], conditioned_p90=row["p90"])
        chosen, report = select(candidates)
        assert [l[0]["player_id"] for l in chosen] == ["b1", "b2"]
        assert not report["selected_scenario_credits"]


def test_nonfinite_conditional_evidence_fails_closed():
    candidates = pool()
    candidates[-1][0]["conditioned_p90"] = float("nan")
    chosen, report = select(candidates)
    assert [l[0]["player_id"] for l in chosen] == ["b1", "b2"]
    assert report["ranked_metrics"][-1]["scenario_value"]["reason"] == "conditional evidence unavailable"


def test_different_roster_without_winner_construction_gets_no_reward():
    candidates = pool()
    for row in candidates[-1]:
        row["player_team"] = "B"
    chosen, report = select(candidates)
    assert [l[0]["player_id"] for l in chosen] == ["b1", "b2"]
    assert report["ranked_metrics"][-1]["scenario_value"]["credit"] == 0


def test_hard_exposure_caps_win_over_credit_and_report_exact_survival():
    chosen, report = select(pool(), limits={"a1": 0}, captain_limit=1)
    assert [l[0]["player_id"] for l in chosen] == ["b1", "b2"]
    scenario = next(r for r in report["scenario_portfolio_accounting"] if r["scenario_id"] == "a_win")
    assert scenario["passing_baseline_quality"] == 1
    assert scenario["constraint_surviving_candidates"] == 0
    assert scenario["replacement_opportunity_cost"] is None
    assert "a1" in scenario["primary_rejection_reason"]


@pytest.mark.parametrize("requested", [1, 2, 3, 5, 10])
def test_portfolio_size_does_not_multiply_per_condition_reward(requested):
    candidates = pool()
    for i in range(requested):
        candidates.append(candidate(f"fill{i}", [f"{i}-{j}" for j in range(5)], 97))
    _, report = select(candidates, requested=requested, captain_limit=1)
    credits = report["selected_scenario_credits"]
    assert len(credits) <= 1
    if requested == 1:
        assert not credits
    else:
        assert sum(c["credit"] for c in credits) <= 2.0


def test_same_condition_multiple_candidates_get_only_one_credit():
    candidates = pool() + [candidate("a-other", [f"tail-{j}" for j in range(5)], 98.6, scenario=True)]
    _, report = select(candidates, requested=3)
    assert len(report["selected_scenario_credits"]) == 1


def test_legacy_quota_and_soft_policy_are_not_combinable():
    with pytest.raises(ValueError, match="mutually exclusive"):
        select_showdown_portfolio(pool(), requested=2, player_limits={}, captain_limit=2,
                                 soft_scenario_diversity=True, require_scenario_diversity=True)


@pytest.mark.parametrize("params,reason", [({"soft_scenario_diversity": "true"}, "explicit boolean"),
                                         ({"soft_scenario_diversity": True, "require_scenario_diversity": True}, "mutually exclusive")])
def test_invalid_api_policy_fails_before_loading_inputs(params, reason):
    service = OptimizerService.__new__(OptimizerService)
    with pytest.raises(ValueError, match=reason):
        service.run_job(season=2026, week=4, slate="MONDAY_NIGHT", strategy="showdown_gpp_portfolio_v3",
                        params=params, contest_format="showdown", objective="gpp")


def test_scoring_and_forecasts_remain_immutable():
    candidates = pool()
    before = deepcopy(candidates)
    select(candidates)
    fields = ["player_id", "projection", "p90", "conditioned_projection", "conditioned_p90", "solver_objective_value"]
    assert [[{k: row.get(k) for k in fields} for row in lineup] for lineup in candidates] == [
        [{k: row.get(k) for k in fields} for row in lineup] for lineup in before]
