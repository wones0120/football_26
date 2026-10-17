from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend.app.product_services.analyst_packets import packet_digest,load_packet
from backend.app.product_services.analyst_preparation import prepare_handoff,bind_handoff
from scripts.run_merged_analyst_fixture import scenario_fixture


def inputs(fmt='CLASSIC'):
    packet,snapshot=scenario_fixture(fmt)
    teams={'AAA':'BUF','BBB':'NYJ','CCC':'SEA','DDD':'DEN','EEE':'LA','FFF':'ARI'}
    def remap(value):
        if isinstance(value,dict):return {k:remap(v) for k,v in value.items()}
        if isinstance(value,list):return [remap(v) for v in value]
        return teams.get(value,value) if isinstance(value,str) else value
    packet=remap(packet);snapshot=remap(snapshot)
    for g in packet['games']:g.update(season=2099,week=1)
    rows=deepcopy(snapshot['players'])
    for row in rows:row['official_availability_status']='ACTIVE'
    request=SimpleNamespace(season=2099,week=1,slate='SYNTHETIC',contest_format=fmt.lower(),analyst_mode='AUTO',analyst_strategy='MERGED_SCENARIOS',analyst_packet_sha256=None)
    result=dict(source_sha256='1'*64,projection_run_id='projection',source_manifest=dict(games=[dict(game_id=g['game_id'],teams=g['teams'],kickoff_at=g['kickoff_at']) for g in packet['games']]))
    return packet,rows,request,result


def test_exact_scope_latest_usable_selection_no_backdating_and_immutable_original(tmp_path):
    p,rows,request,result=inputs();before=deepcopy(p)
    wrong=deepcopy(p);wrong['packet_id']='wrong-week'
    for g in wrong['games']:g['week']=2
    wrong['decision_at']='2099-09-01T13:00:00Z';wrong['frozen_at']=wrong['decision_at']
    report=prepare_handoff(request=request,result=result,rows=rows,checked_at='2099-09-01T14:00:00Z',packets={packet_digest(p):p,packet_digest(wrong):wrong},directory=tmp_path)
    assert report['source_packet_sha256']==packet_digest(p) and report['checked_packet_sha256']
    assert any('different_season_week_format' in c['reasons'] for c in report['selection_candidates'])
    checked=load_packet(report['checked_packet_sha256'],directory=tmp_path)
    assert checked['decision_at']==p['decision_at'] and checked['frozen_at']==p['frozen_at']
    assert checked['preparation_compatibility']['checked_at']=='2099-09-01T14:00:00Z' and p==before
    again=prepare_handoff(request=request,result=result,rows=rows,checked_at='2099-09-01T14:00:00Z',packets={packet_digest(p):p},directory=tmp_path)
    assert again['checked_packet_sha256']==report['checked_packet_sha256']


def test_future_scope_wrong_format_and_hash_rejected(tmp_path):
    p,rows,request,result=inputs()
    future=deepcopy(p);future.update(decision_at='2099-09-01T16:00:00Z',frozen_at='2099-09-01T16:00:00Z')
    report=prepare_handoff(request=request,result=result,rows=rows,checked_at='2099-09-01T14:00:00Z',packets={packet_digest(future):future},directory=tmp_path)
    assert report['status']=='unavailable' and report['checked_packet_sha256'] is None
    with pytest.raises(ValueError,match='hash mismatch'):
        prepare_handoff(request=request,result=result,rows=rows,checked_at='2099-09-01T14:00:00Z',packets={'0'*64:p},directory=tmp_path)
    request.contest_format='showdown'
    report=prepare_handoff(request=request,result=result,rows=rows,checked_at='2099-09-01T14:00:00Z',packets={packet_digest(p):p},directory=tmp_path)
    assert report['status']=='unavailable'


def test_fresh_out_suppresses_affected_construction_preserves_other_scenarios(tmp_path):
    p,rows,request,result=inputs()
    # Only the first game's hypothesis is contradicted; other games survive.
    p['hypotheses'][0]['required_active_player_ids']=[rows[0]['player_id']]
    p['scenario_assumptions']['scenarios'].append(dict(scenario_id='unaffected',label='Other-game branch',hypothesis_ids=[p['hypotheses'][1]['hypothesis_id']],assumptions=[dict(kind='passing_volume',game_id=p['games'][1]['game_id'],team=p['games'][1]['teams'][0],factor=1.2,elasticity=.6)]))
    rows[0]['official_availability_status']='OUT'
    report=prepare_handoff(request=request,result=result,rows=rows,checked_at='2099-09-01T14:00:00Z',packets={packet_digest(p):p},directory=tmp_path)
    assert any(c['kind']=='contradicted' for c in report['changes'])
    assert any(c['kind']=='suppressed_scenario' for c in report['changes'])
    assert p['hypotheses'][0]['status']=='research_only'


def test_canonical_mismatch_hard_error_and_missing_evidence_experimental(tmp_path):
    p,rows,request,result=inputs();rows[0]['position']='WR'
    with pytest.raises(ValueError,match='canonical team/position mismatch'):
        prepare_handoff(request=request,result=result,rows=rows,checked_at='2099-09-01T14:00:00Z',packets={packet_digest(p):p},directory=tmp_path)
    report=prepare_handoff(request=request,result=result,rows=[],checked_at='2099-09-01T14:00:00Z',packets={packet_digest(p):p},directory=tmp_path)
    assert report['status']=='needs_review' and report['checked_packet_sha256']
    assert report['missing_checks']


def test_auto_optimizer_binding_exact_receipt_preserves_focus_and_explicit_flags(tmp_path):
    p,rows,request,result=inputs('SHOWDOWN')
    handoff=prepare_handoff(request=request,result=result,rows=rows,checked_at='2099-09-01T14:00:00Z',packets={packet_digest(p):p},directory=tmp_path)
    payload=dict(objective='gpp',params=dict(analyst_scenario_focus_mode='SELECTED_ONLY',analyst_scenario_focus_ids=['passing'],analyst_challenger_enabled=False))
    bind_handoff(payload,dict(analyst_handoff=handoff))
    assert payload['params']['analyst_packet_sha256']==handoff['checked_packet_sha256']
    assert payload['params']['analyst_strategy']=='MERGED_SCENARIOS'
    assert payload['params']['analyst_scenario_focus_ids']==['passing'] and payload['params']['analyst_challenger_enabled'] is False
    payload['params']['analyst_handoff_compatibility_sha256']='0'*64
    with pytest.raises(ValueError,match='receipt changed'):bind_handoff(payload,dict(analyst_handoff=handoff))


def test_manual_override_baseline_and_no_packet_are_explicit(tmp_path):
    p,rows,request,result=inputs();request.analyst_mode='MANUAL';request.analyst_packet_sha256=packet_digest(p)
    handoff=prepare_handoff(request=request,result=result,rows=rows,checked_at='2099-09-01T14:00:00Z',packets={packet_digest(p):p},directory=tmp_path)
    with pytest.raises(ValueError,match='differs from prepared'):
        bind_handoff(dict(objective='gpp',params=dict(analyst_packet_sha256='0'*64)),dict(analyst_handoff=handoff))
    payload=dict(objective='cash',params=dict(analyst_handoff_mode='BASELINE',analyst_packet_sha256=packet_digest(p)))
    bind_handoff(payload,dict(analyst_handoff=handoff))
    assert 'analyst_packet_sha256' not in payload['params']
    request.analyst_mode='AUTO'
    missing=prepare_handoff(request=request,result=result,rows=rows,checked_at='2099-09-01T14:00:00Z',packets={},directory=tmp_path)
    with pytest.raises(ValueError,match='baseline-only explicitly'):bind_handoff(dict(params={}),dict(analyst_handoff=missing))
    legacy=dict(params={});bind_handoff(legacy,{})
    assert legacy==dict(params={})


def test_preliminary_snapshot_freezes_disjoint_classic_intent_handoffs(tmp_path, monkeypatch):
    from backend.app.product_services import analyst_preparation as service
    p, rows, request, result = inputs()
    first = p['scenario_assumptions']['scenarios'][0]
    alternate = deepcopy(first); alternate['scenario_id'] = 'alternate_classic'
    p['scenario_assumptions']['scenarios'].append(alternate)
    p['optimization_intents'] = {'contract_id': 'analyst_optimization_intents_v1'}
    for intent, sid in [('EXPECTED_GAME', first['scenario_id']), ('CONTRARIAN', alternate['scenario_id'])]:
        p['optimization_intents'][intent] = dict(scenario_ids=[sid], assessment=intent,
            supporting_evidence=['Synthetic supported scenario'], counterevidence=['Other world'],
            unknowns=['Future outcome'], source_ids=[p['sources'][0]['source_id']])
    monkeypatch.setattr(service, 'published_packets', lambda **kwargs: {packet_digest(p): p})
    real_prepare = service.prepare_handoff
    def at_synthetic_clock(**kwargs):
        kwargs.update(checked_at='2099-09-01T14:00:00Z', directory=tmp_path)
        return real_prepare(**kwargs)
    monkeypatch.setattr(service, 'prepare_handoff', at_synthetic_clock)
    snapshot = {'sha256': 'e' * 64, 'pool': rows}
    receipt = service.save_snapshot_handoff(snapshot, request, result, directory=tmp_path)
    reopened = service.load_snapshot_handoff(snapshot['sha256'], directory=tmp_path)
    assert reopened == receipt
    expected, contrarian = (receipt['analyst_intent_handoffs'][i] for i in ('EXPECTED_GAME', 'CONTRARIAN'))
    assert expected['checked_packet_sha256'] != contrarian['checked_packet_sha256']
    assert expected['projection_run_id'] == contrarian['projection_run_id'] == result['projection_run_id']
    assert expected['preliminary_snapshot_sha256'] == contrarian['preliminary_snapshot_sha256'] == snapshot['sha256']
    payload = dict(season=2099, week=1, slate='SYNTHETIC', contest_format='classic', objective='gpp',
        params={'analyst_optimization_intent': 'CONTRARIAN', 'analyst_handoff_mode': 'AUTO'})
    service.bind_handoff(payload, {'analyst_handoff': receipt, 'analyst_intent_handoffs': receipt['analyst_intent_handoffs']})
    assert payload['params']['analyst_packet_sha256'] == contrarian['checked_packet_sha256']
    assert payload['params']['analyst_intent_scenario_ids'] == ['alternate_classic']
    with pytest.raises(ValueError, match='no mixed or baseline fallback'):
        service.bind_handoff(payload, {'analyst_handoff': receipt})
