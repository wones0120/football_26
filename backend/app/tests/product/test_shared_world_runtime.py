from copy import deepcopy
import time
from uuid import UUID

import pulp
import pytest

from backend.app.product_services.analyst_shadow import digest
from backend.app.product_services.shared_world_selection import MEAN_CONTRACT, _roster, select_shared_world_portfolio
from backend.app.product_services.shared_world_runtime import completion_oracle, common_worlds, common_packet, generate_and_select

IDS = [str(UUID(int=i + 1)) for i in range(9)]
SCOPE = dict(contest_format="showdown", season=2026, week=6, slate="SYNTHETIC")
SHA = "a" * 64


def fixture():
    rows = [dict(player_id=p, position="WR", projection=10., p90=20., base_salary=5000., salary=5000.,
                 showdown_captain_shortlisted=i < 2) for i, p in enumerate(IDS)]
    rows[5]["projection"] = 30.; rows[6]["projection"] = 20.
    def candidate(i, captain=0):
        return dict(candidate_id=str(i), input_sha256=SHA, frozen_scope=SCOPE,
            roster=[dict(player_master_id=p, role="CPT" if j == captain else "FLEX", salary=7500. if j == captain else 5000.)
                    for j, p in enumerate(IDS[:5] + [IDS[i]])])
    candidates = [candidate(5), candidate(6), candidate(7, 1)]
    base = {r["player_id"]: r["projection"] for r in rows}
    worlds = [dict(world_id="expected", kind="baseline", source_refs=["verified_source"], mechanism="Expected path",
        mean_contract=MEAN_CONTRACT, likelihood="unknown", frozen_scope=SCOPE, input_sha256=SHA,
        player_means=base, anchor_basis="authored_EXPECTED_GAME")]
    contrary = deepcopy(worlds[0]); contrary.update(world_id="response", kind="contrary", mechanism="Opposing response")
    contrary["player_means"].update({IDS[5]: 0., IDS[6]: 40., IDS[7]: 20.})
    worlds.append(contrary)
    return rows, candidates, worlds


def test_actual_hard_model_completion_avoids_captain_dead_end():
    rows, candidates, worlds = fixture()
    oracle, sha = completion_oracle(candidates, rows, requested=2, params={"captain_max_exposure": .5}, fmt="SHOWDOWN")
    selected, report = select_shared_world_portfolio(candidates, worlds, base_player_means=worlds[0]["player_means"],
        requested=2, completion_feasible=oracle, anchor_world_id="expected")
    assert [x["variant_ids"] for x in selected] == [["5"], ["7"]]
    assert report["constraint_fingerprint"] == sha
    assert all(x["evidence"]["feasible_completion_size"] == 2 for x in report["oracle_calls"] if x["evidence"]["status"] == "feasible")


@pytest.mark.parametrize("params", [
    {"max_lineup_overlap": 4},
    {"maximum_exposure_by_player": {IDS[0]: .5}},
    {"minimum_exposure_by_player": {IDS[8]: 1.}},
    {"core_player_max_exposure": .5},
])
def test_exact_completion_retains_infeasible_user_controls(params):
    rows, candidates, _ = fixture()
    oracle, _ = completion_oracle(candidates, rows, requested=2, params=params, fmt="SHOWDOWN")
    ids = [digest(_roster(c, "showdown")[0]) for c in candidates]
    result = oracle(prefix_ids=[], remaining_ids=ids, requested=2, deadline=time.monotonic() + 2)
    assert result["status"] == "infeasible"
    assert result["target_size"] == 2 and result["proof"]["constraints_relaxed"] is False
    with pytest.raises(ValueError, match="size changed"):
        oracle(prefix_ids=[], remaining_ids=ids, requested=1, deadline=time.monotonic() + 2)


def test_generation_exact_anchor_mean_and_p90_invariance():
    rows, _, worlds = fixture()
    variables = {f"{role}_{i}": pulp.LpVariable(f"{role}_{i}", cat="Binary") for i in range(len(rows)) for role in ("captain", "flex")}
    mapping = {name: dict(player_master_id=IDS[int(name.split("_")[1])], role="CPT" if name.startswith("captain") else "FLEX") for name in variables}
    model = pulp.LpProblem("SyntheticShared", pulp.LpMaximize)
    model += pulp.lpSum(variables[f"captain_{i}"] for i in range(len(rows))) == 1
    model += pulp.lpSum(variables[f"flex_{i}"] for i in range(len(rows))) == 5
    for i in range(len(rows)):
        model += variables[f"captain_{i}"] + variables[f"flex_{i}"] <= 1
        if i >= 2: model += variables[f"captain_{i}"] == 0
    model += pulp.lpSum(variables[n] * rows[int(n.split("_")[1])]["p90"] for n in variables)
    snapshot = dict(model=model.toDict(), variable_players=mapping)
    selected, report = generate_and_select(snapshot, rows, worlds, anchor_world_id="expected", requested=2,
        params={"captain_max_exposure": .5}, fmt="SHOWDOWN", generation_seconds=5.)
    assert len(selected) == 2 and report["anchor_mean_optimality_proven"]
    assert [(a["world_id"], a["captain_player_master_id"]) for a in report["generation"][:2]] == [("expected", None), ("response", None)]
    assert all(w["status"] == "searched" for w in report["generation_world_coverage"])
    # Highest five FLEX plus Captain1 is95: Captain10*1.5 +30+20+10+10+10.
    assert report["selection_steps"][0]["anchor_conditional_mean_points"] == 95.
    altered = deepcopy(rows)
    altered[8]["p90"] = 99999.
    again, _ = generate_and_select(snapshot, altered, worlds, anchor_world_id="expected", requested=2,
        params={"captain_max_exposure": .5}, fmt="SHOWDOWN", generation_seconds=5.)
    assert [c["candidate_id"] for c in selected] == [c["candidate_id"] for c in again]


def test_unique_authored_anchor_and_ambiguous_explicit_base_fallback():
    rows, _, _ = fixture()
    packet = {"optimization_intents": {"EXPECTED_GAME": {"scenario_ids": ["authored"]}, "CONTRARIAN": {"scenario_ids": ["counter"]}}}
    scenes = [dict(scenario_id=s, label=s, hypothesis_ids=["source_hypothesis"], moments={r["player_id"]: {"mean": r["projection"]} for r in rows}) for s in ("authored", "counter")]
    _, anchor, reason = common_worlds(packet, scenes, rows, scope=SCOPE, input_sha256=SHA)
    assert anchor == "authored" and "Unique" in reason
    packet["optimization_intents"]["EXPECTED_GAME"]["scenario_ids"].append("another")
    scenes.append({**deepcopy(scenes[0]), "scenario_id": "another"})
    _, anchor, reason = common_worlds(packet, scenes, rows, scope=SCOPE, input_sha256=SHA)
    assert anchor == "base_model_expected" and "No unique" in reason


def test_personal_what_if_cannot_supply_automatic_contrary_coverage():
    p={"sources":[{"source_id":"s","coverage":"verified"}], "optimization_intents":{"contract_id":"analyst_optimization_intents_v1"},
       "scenario_assumptions":{"scenarios":[{"scenario_id":"a"},{"scenario_id":"b","explicit_user_what_if":True}]}}
    for intent,sid in (("EXPECTED_GAME","a"),("CONTRARIAN","b")):
        p["optimization_intents"][intent]=dict(scenario_ids=[sid],assessment="Sourced",supporting_evidence=["s"],counterevidence=["Risk"],unknowns=["Unknown"],source_ids=["s"])
    with pytest.raises(ValueError,match="non-personal contrary"):
        common_packet(p)


def authored_fixture():
    from scripts.run_merged_analyst_fixture import scenario_fixture
    p, snapshot = scenario_fixture("SHOWDOWN")
    p["optimization_intents"] = {"contract_id": "analyst_optimization_intents_v1"}
    for intent, sid in (("EXPECTED_GAME", "passing"), ("CONTRARIAN", "run_control")):
        p["optimization_intents"][intent] = dict(scenario_ids=[sid], assessment="Sourced synthetic " + intent,
            supporting_evidence=["synthetic"], counterevidence=["Shared failure"], unknowns=["Likelihood unknown"], source_ids=["synthetic"])
    return p, snapshot


def test_actual_capture_and_exact_replay_omit_legacy_stacks_keep_locks_and_unknown_tail():
    import pandas as pd
    from datetime import datetime, timezone
    from unittest.mock import patch
    from backend.app.product_services.optimizer import OptimizerService
    from backend.app.product_services.analyst_scenarios import run_merged
    from backend.app.product_services.shared_world_selection import POLICY
    p, snapshot = authored_fixture(); pool = pd.DataFrame(snapshot["players"])
    locked = snapshot["policy"]["locked_ids"][0]
    pool["showdown_captain_shortlisted"] = pool.position.eq("WR") & ~pool.player_id.eq(locked)
    pool["showdown_captain_p90"] = pool["p90"]
    pool["showdown_flex_mean"] = pool["projection"]
    pool.loc[pool.player_id.eq(locked), "p90"] = None
    banned_qbs = {str(r.player_id): 0 for _, r in pool[pool.position.eq("QB")].iterrows()}
    params = dict(analyst_strategy="MERGED_SCENARIOS", analyst_selection_policy=POLICY,
        analyst_optimization_intent="EXPECTED_GAME", max_exposure=1., captain_max_exposure=.5)
    kwargs = dict(contest_type="captain", score_col="p90", locked_player_ids={locked}, exposure_remaining=banned_qbs,
        stack_params={"enabled": False, "require_starting_qb": True, "hard_qb_correlations": True,
                      "require_qb_captain_receiver": True, "max_players_per_team": 4})
    service = OptimizerService.__new__(OptimizerService)
    now = datetime(2099,9,1,12,tzinfo=timezone.utc)
    with patch("backend.app.product_services.analyst_scenarios.datetime") as clock:
        clock.now.return_value = now
        lineups, report = run_merged(service, pool, params=params, packet=p, fmt="SHOWDOWN",
            season=2099, week=1, slate="SYNTHETIC_SHOWDOWN", requested=2, solve_kwargs=kwargs)
    assert len(lineups) == 2
    assert report["shared_world_selection"]["anchor_world_id"] == "passing"
    assert not report["projection_distribution_eligibility"]["excluded"]
    for lineup in lineups:
        assert locked in {r["player_id"] for r in lineup}
        assert all(r["position"] != "QB" for r in lineup)
        assert next(r for r in lineup if r["roster_position"] == "CPT")["position"] == "WR"
        assert next(r for r in lineup if r["player_id"] == locked)["base_p90"] is None or pd.isna(next(r for r in lineup if r["player_id"] == locked)["base_p90"])
    # Tail remains absent in the actual conditional input, rather than P90=mean.
    assert all(s["moments"][locked]["p90"] is None for s in report["scenario_definitions"])
    original = service._solve_lineup(pool, **kwargs)
    assert original is None  # Existing mandatory-starting-QB path is unchanged.


def test_recommendation_keeps_anchor_first_instead_of_original_fp_rank():
    from backend.app.product_services.shared_world_runtime import recommendation, RECOMMENDATION_POLICY
    from backend.app.product_services.shared_world_selection import POLICY
    lineups = [[{"shared_world_selection_rank": 1}], [{"shared_world_selection_rank": 2}]]
    old = dict(candidates=[dict(lineup_number=2, rank=1, projected_points=100), dict(lineup_number=1, rank=2, projected_points=90)])
    selection = dict(policy_id=POLICY, status="completed", requested=2, selection_steps=[
        dict(anchor_conditional_mean_points=110, maximum_incremental_gain_points=0),
        dict(anchor_conditional_mean_points=100, maximum_incremental_gain_points=20)])
    new = recommendation(old, lineups, selection)
    assert new["policy_id"] == RECOMMENDATION_POLICY and new["recommended"]["lineup_number"] == 1
    assert [c["lineup_number"] for c in new["candidates"]] == [1, 2]
    assert old["candidates"][0]["lineup_number"] == 2


def test_final_new_policy_validation_still_enforces_explicit_qb_and_leader_controls():
    from backend.app.product_services.optimizer import OptimizerService
    lineup=[dict(player_id=p,position="WR",roster_position="CPT" if i==0 else "FLEX",
        salary=7500 if i==0 else 5000,player_team="A" if i<3 else "B") for i,p in enumerate(IDS[:6])]
    def check(rows,**extra):
        return OptimizerService._validate_showdown_lineups([rows],requested_lineups=1,max_exposure=1.,
            portfolio_policy=True,strategy_stack_rules=False,**extra)
    assert check(lineup)[0]  # No mandatory starting QB or WR-CPT same-team QB.
    assert not check(lineup,required_team_leader_ids={IDS[8]})[0]
    assert not check(lineup,locked_player_ids={IDS[8]})[0]
    assert not check(lineup,captain_positions=["RB"])[0]
    with_qbs=deepcopy(lineup)
    for row in with_qbs[1:3]:
        row.update(position="QB",showdown_qb_eligible=True)
    assert check(with_qbs)[0]
    assert not check(with_qbs,no_two_qbs=True)[0]
    assert not check(with_qbs,no_qbs=True)[0]


def test_snapshot_unknown_tail_requires_explicit_mean_only_policy():
    from backend.app.product_services.analyst_shadow import validate_snapshot
    from backend.app.product_services.shared_world_selection import POLICY
    _, snapshot=authored_fixture()
    snapshot["players"][0]["p90"]=None
    snapshot["policy"].update(mean_only=True,selection_policy=POLICY)
    snapshot["sha256"]=digest({k:v for k,v in snapshot.items() if k!="sha256"})
    validate_snapshot(snapshot,mean_only=True)
    with pytest.raises((ValueError,TypeError)):
        validate_snapshot(snapshot)
    snapshot["policy"]["selection_policy"]="legacy"
    snapshot["sha256"]=digest({k:v for k,v in snapshot.items() if k!="sha256"})
    with pytest.raises((ValueError,TypeError)):
        validate_snapshot(snapshot,mean_only=True)


def test_roster_explanations_use_frozen_mechanisms_roles_and_actual_overlap():
    from backend.app.product_services.shared_world_runtime import explain_rosters
    rows, candidates, worlds=fixture()
    for row in rows:
        row.update(name="Native "+row["player_id"],team="A",canonical_role="WR2")
    rows[1].update(role_starter_evidence={"tier":"inferred"},role_source="canonical",role_source_ids=["source"],role_observed_at="2099-09-01T10:00:00Z",starter_qb_evidence_tier="inferred",role_confidence="limited")
    selected=[]
    for i,c in enumerate(candidates[:2]):
        selected.append(dict(rank=i+1,roster=c["roster"],salary=32500,target_world_ids=["response"],
            strongest_admissible_alternative=dict(roster=candidates[2]["roster"],salary=32000)))
    report=dict(anchor_world_id="expected",selection_steps=selected)
    before=deepcopy((rows,worlds))
    explain_rosters(report,worlds,rows)
    assert selected[0]["football_paths"][0]["world_id"]=="expected"
    assert selected[1]["football_paths"][0]["mechanism"]=="Opposing response"
    assert len(selected[0]["shared_actor_dependencies"])==5
    assert selected[0]["roster_roles"][0]["current_role"]=="WR2"
    assert selected[0]["roster_roles"][0]["role_evidence_status"]=="not_present_in_frozen_row"
    captured=selected[0]["roster_roles"][1]
    assert captured["role_evidence_status"]=="available_as_captured_not_upgraded"
    assert captured["role_evidence"]=={"tier":"inferred"}
    assert captured["role_source_lineage"]["role_confidence"]=="limited"
    alt=selected[0]["strongest_admissible_alternative"]
    assert alt["selected_minus_alternative_salary"]==500
    assert alt["entering_actors"][0]["player_master_id"]==IDS[5]
    assert alt["leaving_actors"][0]["player_master_id"]==IDS[7]
    assert (rows,worlds)==before


def test_public_binding_uses_authenticated_common_parent_not_expected_only(monkeypatch):
    from backend.app.product_services.analyst_preparation import bind_handoff
    from backend.app.product_services.shared_world_selection import POLICY
    p, _ = authored_fixture()
    h=dict(mode="AUTO",status="ready",scope=dict(season=2099,week=1,slate="SYNTHETIC",format="SHOWDOWN"),
        checked_packet_sha256="c"*64,source_packet_sha256="b"*64,checked_at="2099-09-01T12:00:00Z",
        research_decision_at="2099-09-01T11:00:00Z",active_features=[],preferred_strategy="MERGED_SCENARIOS",
        preferred_params={},research_coverage=dict(status="mechanisms_current",producer_loop_closed=True))
    h["compatibility_sha256"]=digest(h)
    result=dict(analyst_handoff=h,analyst_intent_handoffs={"EXPECTED_GAME":{"checked_packet_sha256":"wrong_scoped"}})
    monkeypatch.setattr("backend.app.product_services.analyst_packets.load_packet",lambda _key:p)
    payload=dict(season=2099,week=1,slate="SYNTHETIC",contest_format="showdown",objective="gpp",
        params=dict(analyst_selection_policy=POLICY,analyst_handoff_compatibility_sha256=h["compatibility_sha256"]))
    bind_handoff(payload,result)
    assert payload["params"]["analyst_packet_sha256"]=="c"*64
    assert payload["params"]["analyst_handoff_applied"]["common_checked_parent"] is True
    assert "analyst_intent_scenario_ids" not in payload["params"]
    bad=deepcopy(payload);bad["params"]["analyst_optimization_intent"]="CONTRARIAN"
    with pytest.raises(ValueError,match="Expected-anchor"):bind_handoff(bad,result)
    bad=deepcopy(payload);bad["params"]["analyst_handoff_compatibility_sha256"]="wrong"
    with pytest.raises(ValueError,match="receipt changed"):bind_handoff(bad,result)
    bad=deepcopy(payload);del bad["params"]["analyst_handoff_compatibility_sha256"]
    h["research_coverage"]["producer_loop_closed"]=False
    h["compatibility_sha256"]=digest({k:v for k,v in h.items() if k!="compatibility_sha256"})
    with pytest.raises(ValueError,match="producer closure"):bind_handoff(bad,result)


def test_optimizer_internal_preparation_calls_preserve_strict_mode_contract(monkeypatch):
    import ast
    import inspect
    import textwrap
    from sqlalchemy import create_engine
    from backend.app.product_services.optimizer import OptimizerService
    from backend.app.product_services import analyst_preparation, slate_preparation
    from backend.app.product_services.shared_world_selection import POLICY
    service=OptimizerService.__new__(OptimizerService)
    service.engine=create_engine("sqlite://")
    monkeypatch.setattr(analyst_preparation,"bind_saved_preparation",lambda *_:None)
    class ReachedValidatedBoundary(Exception): pass
    def check(session,payload):
        assert payload["objective"]=="gpp" and payload["strategy"]=="showdown_gpp_portfolio_v3"
        # Exercise the same strict mode guard, without any DB or solver work.
        with pytest.raises(ValueError,match="checked common-world Analyst parent"):
            analyst_preparation.bind_handoff(payload,{})
        raise ReachedValidatedBoundary
    monkeypatch.setattr(slate_preparation,"validate_prepared_optimizer",check)
    with pytest.raises(ReachedValidatedBoundary):
        service.run_job(season=2099,week=1,slate="SYNTHETIC",strategy="showdown_gpp_portfolio_v3",
            contest_format="showdown",objective="gpp",params=dict(prepared_input_job_id="prepared",
                analyst_selection_policy=POLICY,analyst_strategy="MERGED_SCENARIOS",analyst_packet_sha256="a"*64))
    # Both entry and final post-solve revalidation require the identical mode
    # contract. Inspect this call boundary without constructing a production DB.
    tree=ast.parse(textwrap.dedent(inspect.getsource(OptimizerService.run_job)))
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="validate_prepared_optimizer"]
    assert len(calls)==2
    for call in calls:
        payload=call.args[1]
        fields={key.value:value for key,value in zip(payload.keys,payload.values) if isinstance(key,ast.Constant)}
        for field in ("objective","strategy"):
            assert isinstance(fields[field],ast.Name) and fields[field].id==field


def test_count_component_world_retains_shared_mean_contract_and_separate_response_ancestry():
    rows,candidates,_=fixture()
    packet={'optimization_intents':{'EXPECTED_GAME':{'scenario_ids':['a']},'CONTRARIAN':{'scenario_ids':['b']}}}
    scenes=[dict(scenario_id=s,label=s,hypothesis_ids=[],count_component_response={'semantic_sha256':'count-proof'},moments={r['player_id']:{'mean':r['projection']} for r in rows}) for s in ('a','b')]
    worlds,anchor,_=common_worlds(packet,scenes,rows,scope=SCOPE,input_sha256=SHA)
    assert all(w['mean_contract']==MEAN_CONTRACT for w in worlds)
    assert worlds[1]['conditional_response_contract']=='frozen_base_plus_matched_linear_component_delta_v1'
    oracle,_=completion_oracle(candidates,rows,requested=2,params={'captain_max_exposure':.5},fmt='SHOWDOWN')
    selected,report=select_shared_world_portfolio(candidates,worlds,base_player_means={r['player_id']:r['projection'] for r in rows},requested=2,completion_feasible=oracle,anchor_world_id=anchor)
    assert len(selected)==2
