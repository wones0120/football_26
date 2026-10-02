from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
import pulp
import pytest
from backend.app.product_services import classic_small_field as service
from backend.app.product_services.classic_portfolio_policy import build_contract, validate_portfolio
from backend.app.product_services.pregame_context import risk_evidence_fields
from backend.app.product_services.classic_prospective import classify_availability, resolve_risk_policy
from backend.app.product_services.canonical_projection_inputs import apply_pregame_projection_context, PREGAME_LINEAGE_COLUMNS
from backend.app.tests.product.test_classic_small_field import _player
from backend.app.product_services.gpp_optimizer import build_large_gpp_config, SlateAnalysis


@pytest.mark.parametrize('requested,effective',[(4,4),(5,5),(6,6),(None,6)])
def test_explicit_and_default_overlap_reaches_actual_selection(requested,effective):
    players=[_player(str(i),'AAA','BBB',pos,4000,10,20) for i,pos in enumerate(['QB','RB','RB','WR','WR','WR','TE','WR','DST'])]
    pool=[{'player_id':p.player_id,'gpp_player':p} for p in players]
    controls={'policy':resolve_risk_policy(None),'classifications':{p.player_id:{'bucket':'normal'} for p in players},'candidate_caps':{},'core_classes':{p.player_id:'elite_high_confidence' for p in players}}
    config=build_large_gpp_config(SlateAnalysis(game_count=1,chalk_concentration=0,feature_games=[]),ownership_available=False)
    constraints={} if requested is None else {'max_lineup_overlap':requested}
    class Reached(Exception):pass
    def selection(*args,**kwargs):
        assert kwargs['max_lineup_overlap']==effective
        raise Reached
    with patch.object(service,'_admit_candidate_caps',side_effect=lambda c,l,*a:(c,l,{})),patch.object(service,'_select_global',side_effect=selection):
        with pytest.raises(Reached):service.analyze_small_field(SimpleNamespace(lineups=[players],config=config),pool_rows=pool,count=1,max_exposure=1,ownership_available=False,requested_candidate_count=1,production_controls=controls,portfolio_constraints=constraints)


def contract(count=2,maximums=None):
    return build_contract(requested={'max_lineup_overlap':4},count=count,max_exposure=1,maximums=maximums or {},minimums={},locked=set(),controls=None,minimum_qbs=1,minimum_stacks=1,tradeoffs=None)


def row(prefix):return {'player_ids':[prefix+str(i) for i in range(9)],'qb':{'player_id':prefix},'stack':{'type':'QB+1'}}


def test_final_validation_rejects_wrong_count_duplicate_and_exposure():
    a=row('a');b=row('b');assert validate_portfolio([a,b],contract())['status']=='verified'
    assert 'entry_count' in validate_portfolio([a],contract())['violations']
    assert 'duplicate_roster' in validate_portfolio([a,a],contract())['violations']
    assert 'exposure:a0' in validate_portfolio([a,b],contract(maximums={'a0':0}))['violations']
    assert validate_portfolio([a],contract(count=1))['status']=='verified'


def test_integer_incumbent_is_not_proven_selection(monkeypatch):
    def solve(model,solver):
        for v in model.variables():v.varValue=1
        model.sol_status=pulp.LpSolutionIntegerFeasible
        return pulp.LpStatusOptimal
    monkeypatch.setattr(pulp.LpProblem,'solve',solve)
    assert service._select_global([dict(row('a'),objective_score=1)],1,1,set(),{}, {})==[]


@pytest.mark.parametrize('source,status',[('Did Not Participate In Practice','DNP'),('Limited Participation in Practice','LIMITED'),('Full Participation in Practice','FULL')])
def test_nested_practice_consumed_without_inventing_full_workload(source,status):
    at='2026-10-02T12:00:00+00:00'
    fields=risk_evidence_fields({'practice_report':{'practice_status':source,'observed_at':at},'depth':{'role':'STARTER'}},at)
    assert fields['practice_participation']==status
    r=classify_availability({'player_status':'Q',**fields},datetime(2026,10,2,13,tzinfo=UTC))
    assert r['practice_status']==status and r['bucket']=='questionable_elevated'
    assert fields['expected_workload_status'] is None
    with pytest.raises(ValueError,match='later'):classify_availability({'player_status':'Q',**fields},datetime(2026,10,2,11,tzinfo=UTC))


def test_future_nested_timestamp_rejected():
    with pytest.raises(ValueError,match='later'):risk_evidence_fields({'practice_report':{'practice_status':'FULL','observed_at':'2026-10-03T12:00:00Z'}},'2026-10-02T12:00:00Z')


def test_context_feature_and_lineage_keep_practice():
    target=pd.DataFrame([{'player_id':'p','position':'WR','recent_team':'A','salary':5000,'player_games_history':3,'snap_share_mean_3':.8,'carry_share_mean_3':0,'target_share_mean_3':.2,'carries_mean_3':0,'targets_mean_3':5,'team_carries_mean_3':20,'team_targets_mean_3':30}])
    context=pd.DataFrame([{'player_master_id':'p','observed_at':'2026-10-02T12:00:00Z','evidence_json':{'practice_report':{'practice_status':'Limited Participation in Practice','observed_at':'2026-10-02T11:00:00Z'}}}])
    rows,_=apply_pregame_projection_context(target,pregame_context=context)
    assert rows.loc[0,'practice_participation']=='LIMITED'
    assert rows.loc[0,'practice_observed_at']=='2026-10-02T11:00:00Z'
    assert 'practice_participation' in PREGAME_LINEAGE_COLUMNS


def test_reporting_missing_team_volume_differs_from_measured_zero():
    assert service._evidence_number({'team_targets_mean_3':0,'team_targets_mean_3_available':False},'team_targets_mean_3') is None
    assert service._evidence_number({'team_targets_mean_3':0,'team_targets_mean_3_available':True},'team_targets_mean_3')==0


def test_practice_only_context_is_a_signal_without_numerical_availability():
    from backend.app.product_services.pregame_context import PregameContextService
    rows=PregameContextService._normalize_players([{'player_id':'p','evidence':{'practice_report':{'practice_status':'Did Not Participate In Practice'}}}],{'p':{'team':'A','position':'WR','player_name':'P'}})
    assert rows[0]['availability_probability'] is None
    assert rows[0]['injury_status'] is None
    with pytest.raises(ValueError,match='no pregame context signal'):
        PregameContextService._normalize_players([{'player_id':'p','evidence':{'depth':{'role':'STARTER'}}}],{'p':{'team':'A','position':'WR'}})


def test_team_report_hides_unavailable_sentinel_but_retains_measured_zero():
    p=_player('WR','AAA','BBB','WR',5000,10,20)
    missing=service._team_reconciliation([p],{p.player_id:{'team_targets_mean_3':0,'team_targets_mean_3_available':False}})
    measured=service._team_reconciliation([p],{p.player_id:{'team_targets_mean_3':0,'team_targets_mean_3_available':True}})
    assert missing[0]['lagged_team_targets_proxy'] is None
    assert measured[0]['lagged_team_targets_proxy']==0
