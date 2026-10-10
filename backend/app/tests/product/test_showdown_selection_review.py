from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.product_services.ai_showdown_packet import build_packet, digest, _classify
from backend.app.product_services.showdown_selection_review import (
    attention_shortlist, build_review, compare_pair, lower_overlap_alternatives, reject_outcomes, review_comparison,
)
from backend.app.product_services.showdown_selection_records import (
    DecisionRequest, ExecutionRequest, make_decision, make_execution, review_hash, verify_record,
)
from backend.app.product_services.showdown_selection_learning import evaluate_decision, valid_prelock_decision
from backend.app.tests.product.test_ai_showdown_packet import universe_source

ROOT = Path(__file__).resolve().parents[4]
WEEK5 = "3a41af88-a28c-41b1-888c-462ddcd7d74d"
OBSERVED_IDS = [WEEK5 + ":beb41d478b13c469", WEEK5 + ":8e2120be4073304e"]


def fixture_packet():
    return build_packet(universe_source(), ai_requested_entries=2, allow_incomplete_evidence=True)


def live_review():
    r = build_review(fixture_packet())
    r["data_readiness"].update(status="READY", incomplete_evidence=False, non_production_override=False)
    r["run_identity"].update(frozen_source_hash_basis="generation_snapshot", frozen_source_evidence_hash="test-frozen-source-hash")
    return r


def request_for(r, status="SELECTED", previous=None):
    ids = [c["candidate_id"] for c in r["candidates"][:2]]
    return DecisionRequest(idempotency_key="request-1", previous_decision_id=previous["decision_id"] if previous else None,
                           review_hash=review_hash(r), status=status, proposed_candidate_ids=ids,
                           explicitly_considered_ids=ids, reasoning="Saved fixture reasoning",
                           football_theses=["First script", "Second script"], complementarity_reason="Different paths with common exposure",
                           accepted_high_overlap_exception="Deliberately retain quality and this player core")


def prelock_now(r):
    return datetime.fromisoformat(r["run_identity"]["created_at"]) + timedelta(minutes=1)


def test_top10_order_ties_underfill_and_no_membership_mutation():
    packet = fixture_packet()
    before = deepcopy(packet)
    shortlist = attention_shortlist(packet)
    finalists = {c["candidate_id"] for c in packet["finalists"]}
    eligible = packet["ai_review_universe"]["candidates"]
    expected = sorted([c for c in eligible if c["candidate_id"] not in finalists],
                      key=lambda c: (-c["quality_eligibility"]["ceiling_fraction"], c["metrics"]["selector_rank"], c["candidate_id"]))[:10]
    assert shortlist["ceiling_outsider_candidate_ids"] == [c["candidate_id"] for c in expected]
    assert len(shortlist["rows"]) == 30
    assert not shortlist["is_universe_filter"]
    assert packet == before
    packet["ai_review_universe"]["candidates"].reverse()
    assert attention_shortlist(packet) == shortlist
    for c in packet["ai_review_universe"]["candidates"]:
        c["quality_eligibility"]["ceiling_fraction"] = .95
        c["metrics"]["selector_rank"] = 5
    assert attention_shortlist(packet)["ceiling_outsider_candidate_ids"] == sorted(c["candidate_id"] for c in eligible if c["candidate_id"] not in finalists)[:10]
    packet["ai_review_universe"]["candidates"] = [c for c in eligible if c["candidate_id"] in finalists] + expected[:1]
    assert len(attention_shortlist(packet)["ceiling_outsider_candidate_ids"]) == 1


def test_canonical_overlap_same_six_different_captains():
    r = live_review()
    a, b = deepcopy(r["candidates"][0]), deepcopy(r["candidates"][0])
    b["candidate_id"] = "different-captain"
    cpt = next(p for p in b["players"] if p["slot"] == "CPT")
    other = next(p for p in b["players"] if p["slot"] == "FLEX")
    cpt["slot"], other["slot"] = "FLEX", "CPT"
    b["construction"] = _classify(b["players"], {"favorite": "AAA", "underdog": "BBB"}, 49500, None)
    result = compare_pair(a, b)
    assert result["shared_player_count"] == 6
    assert result["unique_players_across_pair"] == 6
    assert result["shared_flex_player_count"] == 4
    assert not result["same_captain"]
    assert "concentrated player core" in result["overlap_message"]


def test_quality_eligible_alternatives_are_deterministic_and_nonbinding():
    r = live_review()
    # The compact universe fixture varies only one FLEX. Add a deterministic
    # two-player variation so a <=4 diagnostic can exist in this test.
    variation = deepcopy(r["candidates"][0])
    variation["candidate_id"] += "-lower-overlap-fixture"
    for i, player in enumerate([p for p in variation["players"] if p["slot"] == "FLEX"][:2]):
        player["player_id"] = f"canonical-alternative-fixture-{i}"
    r["candidates"].append(variation)
    before = deepcopy(r)
    ids = [c["candidate_id"] for c in r["candidates"][:2]]
    comparison = review_comparison(r, ids)
    assert comparison["proposed_pair"]["candidate_ids"] == ids
    alt = comparison["alternative_portfolio"]
    assert alt["alternatives"]
    assert all(p["shared_player_count"] <= 4 for p in alt["alternatives"])
    assert all(set(p["candidate_ids"]) <= {c["candidate_id"] for c in r["candidates"]} for p in alt["alternatives"])
    reverse = lower_overlap_alternatives(list(reversed(r["candidates"])), comparison["proposed_pair"])
    assert reverse == alt
    assert r == before
    assert not alt["automatic_selection"]
    candidates = deepcopy(r["candidates"])
    for c in candidates[2:]: c["quality_eligibility"]["eligible"] = False
    assert lower_overlap_alternatives(candidates, comparison["proposed_pair"])["status"] == "NO_ELIGIBLE_LOWER_OVERLAP_PAIR"


@pytest.mark.parametrize("key", ["actual_points", "actual_lineup_points", "actual_ownership", "field_rank", "winning_captain", "postgame_construction_frequencies", "hindsight_label"])
def test_outcomes_rejected_recursively_and_before_hash_validation(key):
    p = fixture_packet()
    p["ai_review_universe"]["candidates"][0]["players"][0][key] = 999
    with pytest.raises(ValueError, match="Postgame"):
        build_review(p)
    with pytest.raises(ValueError, match="Postgame"):
        reject_outcomes({"nested": [{key: 1}]})


def test_missing_ownership_is_unavailable_and_original_packet_unmodified():
    p = fixture_packet()
    before = deepcopy(p)
    for c in p["ai_review_universe"]["candidates"]:
        c["metrics"]["projected_total_ownership"] = 123
    p["evidence_hash"] = digest({k:v for k,v in p.items() if k not in {"evidence_hash","generated_at"}})
    r = build_review(p)
    assert all(c["ownership_availability"] == "UNAVAILABLE" and c["metrics"]["projected_total_ownership"] is None for c in r["candidates"])
    assert all(p["flex_ownership"] is None for c in r["candidates"] for p in c["players"])
    assert before["run"] == p["run"]


def test_hash_and_foreign_candidate_guards():
    p = fixture_packet(); p["ai_review_universe"]["candidates"].pop()
    with pytest.raises(ValueError, match="hash mismatch"): build_review(p)
    r = live_review()
    with pytest.raises(ValueError, match="Exactly two"): review_comparison(r, ["other-run", r["candidates"][0]["candidate_id"]])


def test_record_identity_displayed_not_considered_not_entered_and_high_overlap_accepted():
    r = live_review(); req = request_for(r)
    req.other_displayed_candidate_ids = [r["candidates"][4]["candidate_id"]]
    record = make_decision(r, req, now=prelock_now(r))
    assert record["run_identity"] == r["run_identity"]
    assert record["attention"]["explicitly_considered_ids"] == req.explicitly_considered_ids
    assert req.other_displayed_candidate_ids[0] not in record["attention"]["explicitly_considered_ids"]
    assert record["execution"] is None and record["status"] == "SELECTED"
    assert record["user_approval_status"] == "NOT_APPROVED"
    assert record["proposed_pair"]["shared_player_count"] >= 5
    verify_record(record)


def test_revisions_preserve_prior_choice_and_reset_approval():
    r = live_review(); first = make_decision(r, request_for(r), now=prelock_now(r))
    before = deepcopy(first)
    approved = make_decision(r, request_for(r, "USER_APPROVED", first), previous=first, now=prelock_now(r) + timedelta(minutes=1))
    req = request_for(r, "SELECTED", approved)
    req.proposed_candidate_ids = [r["candidates"][2]["candidate_id"], r["candidates"][3]["candidate_id"]]
    req.explicitly_considered_ids = req.proposed_candidate_ids
    changed = make_decision(r, req, previous=approved, now=prelock_now(r) + timedelta(minutes=2))
    assert first == before
    assert approved["revision"] == 2 and changed["revision"] == 3
    assert changed["previous_decision_id"] == approved["decision_id"]
    assert changed["user_approval_status"] == "NOT_APPROVED"
    req.previous_decision_id = first["decision_id"]
    with pytest.raises(ValueError, match="Stale"): make_decision(r, req, previous=approved, now=prelock_now(r))


def test_cannot_backdate_or_select_after_kickoff_or_approve_without_selection():
    r = live_review(); req = request_for(r)
    with pytest.raises(ValidationError): DecisionRequest(**{**req.model_dump(), "decision_timestamp": "2026-10-01T12:00:00-04:00"})
    with pytest.raises(ValueError, match="prelock"): make_decision(r, req, now=datetime.fromisoformat(r["run_identity"]["kickoff_at"]))
    with pytest.raises(ValueError, match="User approval"): make_decision(r, request_for(r, "USER_APPROVED"), now=prelock_now(r))
    req.explicitly_considered_ids = []
    with pytest.raises(ValueError, match="explicitly marked"): make_decision(r, req, now=prelock_now(r))
    with pytest.raises(ValueError, match="complete frozen"): make_decision(build_review(fixture_packet()), request_for(build_review(fixture_packet())), now=prelock_now(r))


def test_executed_rosters_require_imported_canonical_evidence_and_preserve_selection_freeze():
    r = live_review(); selected = make_decision(r, request_for(r), now=prelock_now(r))
    approved = make_decision(r, request_for(r, "USER_APPROVED", selected), previous=selected, now=prelock_now(r))
    req = ExecutionRequest(idempotency_key="execute", previous_decision_id=approved["decision_id"], learning_report_id="learning-fixture",
                           entries=[{"contest_id":"1","entry_id":"11"},{"contest_id":"1","entry_id":"12"}])
    report = {"report_id":"learning-fixture", "season":r["run_identity"]["season"], "week":r["run_identity"]["week"],
              "slate":r["run_identity"]["slate"], "evidence_hash":"outcome-fixture", "entries":[
                  {"contest_id":"1","entry_id":str(11+i),"identity_complete":True,"players":c["players"]}
                  for i,c in enumerate(r["candidates"][:2])]}
    now = datetime.fromisoformat(r["run_identity"]["kickoff_at"]) + timedelta(hours=4)
    entered = make_execution(approved,r,req,report,now=now)
    assert entered["status"] == "ENTERED_CONFIRMED" and entered["execution"]["matches_approved_pair"]
    assert entered["proposed_candidate_ids"] == selected["proposed_candidate_ids"]
    assert entered["selection_frozen_at"] == approved["selection_frozen_at"]
    assert valid_prelock_decision(entered)
    report["entries"][1]["players"] = r["candidates"][3]["players"]
    assert not make_execution(approved,r,req,report,now=now)["execution"]["matches_approved_pair"]
    report["entries"][0]["identity_complete"] = False
    with pytest.raises(ValueError,match="unresolved canonical"): make_execution(approved,r,req,report,now=now)
    with pytest.raises(ValueError,match="USER_APPROVED"): make_execution(selected,r,req,report,now=now)


def test_postgame_evaluation_is_separate_and_week4_sunday_is_excluded():
    r = live_review(); record = make_decision(r,request_for(r),now=prelock_now(r)); before=deepcopy(record)
    report = {k:r["run_identity"][k] for k in ("season","week","slate")}
    report.update(report_id="research-report",evidence_hash="report-hash")
    outcomes=[{"players":c["players"],"postgame":{"actual_points":100-i}} for i,c in enumerate(r["candidates"])]
    with pytest.raises(ValueError,match="before kickoff"): evaluate_decision(record,r,report,outcomes,now=prelock_now(r))
    result=evaluate_decision(record,r,report,outcomes,now=datetime.fromisoformat(r["run_identity"]["kickoff_at"])+timedelta(hours=4))
    assert result["final_selection_regret"]==0 and result["candidate_scores_complete"]
    assert result["best_chosen_candidate_actual"]==100 and result["best_entry_performance"] is None
    assert result["entry_execution_fidelity"] is None and record==before
    outcomes.pop()
    result=evaluate_decision(record,r,report,outcomes,now=datetime.fromisoformat(r["run_identity"]["kickoff_at"])+timedelta(hours=4))
    assert result["final_selection_regret"] is None
    record["run_identity"].update(season=2026,week=4,slate="SUNDAY_NIGHT")
    assert not valid_prelock_decision(record)


def test_week5_frozen_targets_and_production_outputs_preserved():
    path=ROOT/"artifacts/showdown_selection_diversity_audit"/f"{WEEK5}-source.json"
    if not path.exists():pytest.skip("Saved Week5 source unavailable")
    source=json.loads(path.read_text()); before=deepcopy(source)
    packet=build_packet(source,ai_requested_entries=2);r=build_review(packet)
    assert r["counts"]=={"quality_eligible":75,"finalists":20,"ceiling_outsiders":10}
    rank41=next(c for c in r["candidates"] if c["metrics"]["selector_rank"]==41)
    assert rank41["construction"]["captain_player_name"]=="Ryan Flournoy"
    assert rank41["candidate_id"] in r["attention_shortlist"]["ceiling_outsider_candidate_ids"]
    old=json.loads((ROOT/"artifacts/showdown_selection_diversity_audit/week5_packet.json").read_text())
    assert packet["finalists"] == old["finalists"]
    assert {c["candidate_id"] for c in r["candidates"]} == {c["candidate_id"] for c in old["ai_review_universe"]["candidates"]}
    assert packet["control_selection"]==old["control_selection"]
    pair=review_comparison(r,OBSERVED_IDS)
    assert pair["proposed_pair"]["shared_player_count"]==5
    assert pair["proposed_pair"]["unique_players_across_pair"]==7
    assert pair["alternative_portfolio"]["alternatives"][0]["shared_player_count"]<=4
    assert r["selection_status"]=="AI_SELECTION_UNKNOWN"
    assert source==before


def test_prelock_builder_has_no_outcome_or_research_import():
    import ast
    tree=ast.parse((ROOT/"backend/app/product_services/showdown_selection_review.py").read_text())
    modules=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert not any("learning" in m or "audit" in m or "optimizer" in m for m in modules if m)


def test_registered_api_contract_preserves_read_only_review_and_export(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.api import showdown_selection_routes as routes
    from backend.app.product_dependencies import get_optimizer_service
    from types import SimpleNamespace
    r=live_review()
    class FakeStore:
        def __init__(self, engine):pass
        def history(self, run):return []
    monkeypatch.setattr(routes,"SelectionDecisionStore",FakeStore)
    monkeypatch.setattr(routes,"run_review",lambda run,service:r)
    app=FastAPI();app.include_router(routes.router,prefix="/api")
    app.dependency_overrides[get_optimizer_service]=lambda:SimpleNamespace(engine=object())
    client=TestClient(app)
    base='/api/optimizer/results/frozen-run/selection-review'
    view=client.get(base);assert view.status_code==200
    assert view.json()['selection_status']=='AI_SELECTION_UNKNOWN'
    ids=[c['candidate_id'] for c in r['candidates'][:2]]
    compared=client.post(base+'/compare',json={'review_hash':review_hash(r),'candidate_ids':ids})
    assert compared.status_code==200
    assert client.post(base+'/compare',json={'review_hash':'changed','candidate_ids':ids}).status_code==422
    assert client.post(base+'/decisions',json={**request_for(r).model_dump(),'decision_timestamp':'pretend-prelock'}).status_code==422
    exported=client.get(base+'/download').json()
    assert set(exported)=={'review','review_hash'}
    assert not {'decision_history','execution','outcomes'} & exported.keys()


def test_review_diagnostics_do_not_change_fixed_production_selection_or_add_overlap_cap():
    from backend.app.product_services.showdown_portfolio_selection import select_showdown_portfolio, signature
    from backend.app.tests.product.test_showdown_portfolio_selection import lineup
    candidates=[lineup('c1',['a','b','c','d','e'],80,140,100),
                lineup('c2',['a','b','c','d','e'],79,139,99),
                lineup('c3',['f','g','h','i','j'],78,138,98)]
    limits={p['player_id']:2 for c in candidates for p in c}
    before=select_showdown_portfolio(deepcopy(candidates),requested=2,player_limits=limits,captain_limit=2)
    r=live_review();review_comparison(r,[c['candidate_id'] for c in r['candidates'][:2]])
    after=select_showdown_portfolio(deepcopy(candidates),requested=2,player_limits=limits,captain_limit=2)
    assert after==before
    assert len(set(p['player_id'] for p in after[0][0]) & set(p['player_id'] for p in after[0][1]))==5


def test_qb_coverage_counts_players_even_when_two_qbs_share_a_team():
    from backend.app.product_services.showdown_selection_review import construction_coverage
    p=fixture_packet()
    c=deepcopy(next(c for c in p['ai_review_universe']['candidates'] if sum(x['position']=='QB' for x in c['players'])==2))
    for player in c['players']:
        if player['position']=='QB':player['team']=c['construction']['captain_team']
    c['construction']=_classify(c['players'],p['game'],c['metrics']['salary_used'],None)
    c['ownership_availability']='UNAVAILABLE'
    p['ai_review_universe']['candidates']=[c];p['finalists']=[c]
    p['pool_summary']['candidate_assessments']=[{**c,'qb_player_count':2}]
    rows={row['family']:row for row in construction_coverage(p)['qb_count']}
    assert rows['2']['generated']==rows['2']['quality_eligible']==rows['2']['finalists']==1
    assert rows['1']['quality_eligible']==0
