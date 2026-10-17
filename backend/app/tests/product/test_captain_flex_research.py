from copy import deepcopy
import json

import numpy as np
import pytest

from backend.app.product_services.captain_flex_research import (
    compare, digest, factor_model, role, score_candidates, Z90,
)
from scripts.research_captain_flex import actual_map, attach_actuals, clock, read


def pool():
    return [dict(player_id=str(i), name=f"Player {i}", position=pos, team=team,
                 mean=10., p90=20., projected_carries=carries, projected_targets=targets)
            for i, (pos, team, carries, targets) in enumerate([
                ("WR", "A", 0, 8), ("QB", "A", 0, 0), ("WR", "A", 0, 7),
                ("RB", "A", 18, 0), ("DST", "B", 0, 0), ("WR", "B", 0, 8),
                ("QB", "B", 6, 0), ("DST", "A", 0, 0)])]


def lineup(players, ids=(0, 1, 2, 3, 4, 5), captain=0):
    result = []
    for i in ids:
        p = players[i]; mult = 1.5 if i == captain else 1.
        result.append(dict(player_id=p["player_id"], name=p["name"], position=p["position"],
            player_team=p["team"], roster_position="CPT" if i == captain else "FLEX",
            projection=mult*p["mean"], p90=mult*p["p90"], salary=mult*5000))
    result[0]["solver_objective_value"] = 100.
    return result


def test_receiver_success_helps_qb_and_competes_with_receiver_and_opposing_dst():
    players = pool()
    scored = score_candidates(players, [lineup(players)])[0]
    flex = {p["player_id"]: p for p in scored["flex"]}
    assert flex["1"]["conditional_lift"] > 0
    assert flex["2"]["conditional_lift"] < 0
    assert flex["4"]["conditional_lift"] < 0
    assert any(k.startswith("receiving_competition") and v < 0
               for k, v in flex["2"]["factor_contributions"].items())
    assert scored["captain_flex"] == pytest.approx(scored["ceiling_only"] + sum(
        p["conditional_lift"] for p in scored["flex"]))


def test_rushing_qb_has_less_receiver_support_and_rushing_competition():
    players = pool()
    pocket = score_candidates(players, [lineup(players, captain=1)])[0]
    players[1]["projected_carries"] = 6.
    rushing = score_candidates(players, [lineup(players, captain=1)])[0]
    def lift(row, pid):
        return next(p["conditional_lift"] for p in row["flex"] if p["player_id"] == pid)
    assert lift(rushing, "0") < lift(pocket, "0")
    rb = next(p for p in rushing["flex"] if p["player_id"] == "3")
    assert any(k.startswith("rushing_competition") and v < 0 for k,v in rb["factor_contributions"].items())


def test_receiving_rb_and_early_down_rb_have_different_partners():
    players = pool()
    early = score_candidates(players, [lineup(players, ids=(0,1,2,3,5,7), captain=3)])[0]
    players[3].update(projected_carries=0, projected_targets=8)
    receiving = score_candidates(players, [lineup(players, ids=(0,1,2,3,5,7), captain=3)])[0]
    get = lambda r, pid: next(p["conditional_lift"] for p in r["flex"] if p["player_id"] == pid)
    assert get(receiving,"1") > get(early,"1")
    assert get(early,"7") > get(receiving,"7")


def test_conditional_formula_matches_independent_seeded_factor_simulation():
    players = pool(); factors, _ = factor_model(players)
    keys = sorted({k for f in factors.values() for k in f})
    rng = np.random.default_rng(47)
    shared = rng.normal(size=(200_000, len(keys)))
    draws = []
    for p in players:
        weights = np.array([factors[p["player_id"]].get(k, 0) for k in keys])
        z = shared @ weights + np.sqrt(1-weights@weights)*rng.normal(size=len(shared))
        draws.append(p["mean"] + (p["p90"]-p["mean"])/Z90*z)
    event = draws[0] >= players[0]["p90"]
    totals = 1.5*draws[0] + sum(draws[1:6])
    analytic = score_candidates(players, [lineup(players)])[0]["captain_flex"]
    assert abs(totals[event].mean()-analytic) < .5


def test_unknown_role_is_explicit_zero_workload_is_not_missing_and_no_names_used():
    p = pool()[1]
    assert not role(p)["unknown"]
    assert role(p)["rushing"] == 0
    p.pop("projected_carries")
    assert role(p)["unknown"] and role(p)["rushing"] == .5
    p["name"] = "Famous Rushing Quarterback"
    assert role(p)["rushing"] == .5


def test_zero_spread_and_negative_means_are_not_silently_repaired():
    players=pool(); players[0].update(mean=-1., p90=-1.)
    scored=score_candidates(players,[lineup(players)])[0]
    assert scored["tail_event_degenerate"]
    assert scored["captain_tail_mean_points_proxy"] == -1.5
    assert scored["flex_conditional_lift"] == 0
    players[0]["p90"]=-2.
    with pytest.raises(ValueError,match="mean <= P90"):
        score_candidates(players,[lineup(players)])


def test_identity_and_slots_fail_closed():
    players=pool(); roster=lineup(players)
    roster[1]["player_id"]=roster[0]["player_id"]
    with pytest.raises(ValueError,match="distinct"):
        score_candidates(players,[roster])
    with pytest.raises(ValueError,match="duplicates"):
        score_candidates(players,[lineup(players),lineup(players)])
    players[1]["player_id"]=players[0]["player_id"]
    with pytest.raises(ValueError,match="canonical"):
        factor_model(players)


def test_same_quality_gates_and_caps_outcome_blindness_and_no_mutation():
    players=pool()
    players[6].update(mean=0., p90=1.)
    candidates=[lineup(players),lineup(players,captain=1),lineup(players,ids=(0,1,2,3,5,6),captain=6)]
    before=deepcopy((players,candidates))
    controls=dict(requested=2,player_limits={p["player_id"]:2 for p in players},captain_limit=1)
    result=compare(players,candidates,**controls)
    assert (players,candidates)==before
    assert len({v["quality_eligible_count"] for v in result["variants"].values()})==1
    by_id={r["candidate_id"]:r for r in result["rows"]}
    weak=next(r for r in result["rows"] if r["captain_id"]=="6")
    assert not weak["quality_eligible"]
    for v in result["variants"].values():
        assert v["selected_count"]==2
        assert len({by_id[i]["captain_id"] for i in v["selected_ids"]})==2
        assert weak["candidate_id"] not in v["selected_ids"]
    for p in players:
        p.update(actual_points=999999, actual_ownership=100)
    assert compare(players,candidates,**controls)==result
    assert score_candidates(players[::-1],candidates)==score_candidates(players,candidates)


def test_actual_labels_captain_multiplier_once_conflicts_and_scope():
    spec=dict(season=2026,week=4,slate="MONDAY_NIGHT")
    payload={**spec,"observations":[
        dict(player_id="a",actual_points=30,roster_position="CPT",resolution_status="resolved"),
        dict(player_id="a",actual_points=20,roster_position="FLEX",resolution_status="resolved"),
        dict(player_id="b",actual_points=0,roster_position="FLEX",resolution_status="resolved"),
        dict(player_id="c",actual_points=2,roster_position="FLEX",resolution_status="unresolved")]}
    actuals,conflicts=actual_map(payload,spec)
    assert actuals=={"a":20.,"b":0.} and conflicts==[]
    payload["observations"][1]["actual_points"]=19
    assert actual_map(payload,spec)==({"b":0.},["a"])
    with pytest.raises(ValueError,match="scope"):
        actual_map(payload,{**spec,"week":5})


def test_missing_outcomes_never_imputed_or_used_to_change_selections():
    players=pool(); candidates=[lineup(players)]
    result=compare(players,candidates,requested=1,player_limits={p["player_id"]:1 for p in players},captain_limit=1)
    selected=deepcopy({k:v["selected_ids"] for k,v in result["variants"].items()})
    attach_actuals(result,candidates,{"0":100.})
    assert not result["actual_coverage"]["complete_candidate_labels"]
    for k,v in result["variants"].items():
        assert v["selected_ids"]==selected[k]
        assert v["actual_evaluation"]["mean"] is None
        assert v["actual_evaluation"]["retained_candidate_regret"] is None


def test_source_checksums_and_aware_clocks(tmp_path):
    payload={"safe":"frozen"}; path=tmp_path/"source.json"
    path.write_text(json.dumps({"payload":payload,"sha256":digest(payload)}))
    assert read(path)==payload
    path.write_text(json.dumps({"payload":payload,"sha256":"wrong"}))
    with pytest.raises(ValueError,match="checksum"):
        read(path)
    assert clock("2026-10-04T22:08:01-04:00") > clock("2026-10-05T00:20:00+00:00")
    with pytest.raises(ValueError,match="Timezone"):
        clock("2026-10-04T22:08:01")
