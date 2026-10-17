from copy import deepcopy

import pytest

from backend.app.product_services.analyst_shadow import digest
from backend.app.product_services.defense_kicker_analyst import (
    CONTRACT, DIMENSIONS, scan_specialists, validate_specialists, paired_flex_comparison,
)
from scripts.build_analyst_shadow_fixtures import fixture


def finding_fixture():
    packet, snapshot = fixture('SHOWDOWN')
    player = next(p for p in packet['players'] if p['position'] == 'DST')
    f = dict(finding_id='test-defense', player_master_id=player['player_master_id'],
        game_id=player['game_id'], team=player['team'], format='SHOWDOWN', status='watchlist', action='none',
        as_of=packet['decision_at'], expires_at=packet['games'][0]['kickoff_at'],
        mechanism='SYNTHETIC pressure opportunity', contrary_evidence=['SYNTHETIC pass efficiency'],
        uncertainty='Unknown sack conversion', what_changes_view=['Protection evidence'],
        model_accounting={'status':'unknown'}, opportunity_cost='Compare with skill FLEX',
        evidence={d:dict(status='unavailable',summary='Unmeasured',source_ids=[],value=None) for d in DIMENSIONS['DST']})
    packet['defense_kicker_analysis'] = dict(contract_id=CONTRACT, findings=[f])
    return packet, snapshot, f


def test_automatic_screen_covers_every_game_without_inventing_evidence():
    packet, snapshot = fixture('CLASSIC'); before = deepcopy(snapshot)
    report = scan_specialists(packet, snapshot['players'], fmt='CLASSIC')
    assert len(report['games']) == 3 and len(report['assessments']) == 6
    assert all(a['position']=='DST' and a['action']=='none' and a['missing_evidence'] for a in report['assessments'])
    assert snapshot == before


def test_canonical_role_format_clock_and_source_gates():
    packet, snapshot, f = finding_fixture()
    assert validate_specialists(packet) == []
    f['status']='supported_comparison'; f['action']='paired_flex_comparison'
    assert any('core opportunity' in e for e in validate_specialists(packet))
    f['evidence']['pressure']=dict(status='reviewed',summary='Fabricated',source_ids=['synthetic'])
    assert any('sourced assertion' in e for e in validate_specialists(packet))
    f['evidence']['pressure']['status']='unavailable'; f['evidence']['pressure']['value']=0
    assert any('measured zero' in e for e in validate_specialists(packet))
    f['as_of']='2099-09-03T12:00:00Z'
    assert any('clock' in e for e in validate_specialists(packet))
    packet['players'][7]['position']='K'; f['format']='CLASSIC'
    assert any('kicker illegal' in e for e in validate_specialists(packet))


def test_paired_exact_captain_legality_opportunity_cost_and_constraints():
    packet, snapshot = fixture('SHOWDOWN'); before=deepcopy(snapshot)
    specialist=next(p['player_id'] for p in snapshot['players'] if p['position']=='DST')
    captain=next(p['player_id'] for p in snapshot['players'] if p['position']=='WR')
    report=paired_flex_comparison(snapshot,specialist_id=specialist,captain_id=captain)
    assert report['achieved_lineup_count']==2 and report['relaxations']==[]
    for b in report['branches']:
        assert len(b['roster'])==6 and b['salary']<=50000
        assert len({r['player_master_id'] for r in b['roster']})==6
        assert next(r['player_master_id'] for r in b['roster'] if r['role']=='CPT')==captain
        ids={r['player_master_id'] for r in b['roster']}
        assert (specialist in ids)==b['included']
        assert set(snapshot['policy']['locked_ids'])<=ids
        assert not set(snapshot['policy']['zero_remaining_exposure_ids']) & ids
    assert report['opportunity_cost']['displaced_player_ids'] and snapshot==before
    variables, model = __import__('pulp').LpProblem.fromDict(deepcopy(snapshot['model']))
    name=next(n for n,l in snapshot['variable_players'].items() if l['player_master_id']==specialist and l['role']=='FLEX')
    model += variables[name]==0
    blocked=deepcopy(snapshot); blocked['model']=model.toDict(); blocked['sha256']=digest({k:v for k,v in blocked.items() if k!='sha256'})
    report=paired_flex_comparison(blocked,specialist_id=specialist,captain_id=captain)
    assert report['branches'][1]['solver_status']=='Infeasible'
    assert report['achieved_lineup_count']==1 and report['relaxations']==[]


def test_captain_and_hash_rejection():
    _,snapshot=fixture('SHOWDOWN'); specialist=snapshot['players'][7]['player_id']
    with pytest.raises(ValueError,match='separate fixed Captain'):
        paired_flex_comparison(snapshot,specialist_id=specialist,captain_id=specialist)
    snapshot['players'][0]['salary']=1
    with pytest.raises(ValueError,match='hash'):
        paired_flex_comparison(snapshot,specialist_id=specialist,captain_id=snapshot['players'][3]['player_id'])


def test_specialist_packet_lineage_and_idempotent_import(tmp_path):
    from backend.app.product_services.analyst_packets import import_packet, load_packet
    packet,_,_=finding_fixture()
    first=import_packet(packet,directory=tmp_path)
    assert import_packet(packet,directory=tmp_path)==first
    assert load_packet(first['analyst_packet_sha256'],directory=tmp_path)['defense_kicker_analysis']==packet['defense_kicker_analysis']
    packet['defense_kicker_analysis']['findings'][0]['uncertainty']='Revised research edition'
    second=import_packet(packet,directory=tmp_path)
    assert first['analyst_packet_sha256']!=second['analyst_packet_sha256']
    assert len(list(tmp_path.glob('*.json')))==2
