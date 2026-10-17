from copy import deepcopy

import pytest

from backend.app.product_services.analyst_shadow import digest, generate_shadow, validate_snapshot
from scripts.build_analyst_shadow_fixtures import fixture


def rehash(snapshot):
    snapshot['sha256'] = digest({k:v for k,v in snapshot.items() if k!='sha256'})


@pytest.mark.parametrize('fmt', ['CLASSIC','SHOWDOWN'])
def test_effect_repeatability_and_no_mutation(fmt):
    packet,snapshot = fixture(fmt)
    before = deepcopy((packet,snapshot))
    a = generate_shadow(packet,snapshot,seed=7)
    b = generate_shadow(packet,snapshot,seed=7)
    assert a == b
    assert (packet,snapshot) == before
    assert a['comparison']['shadow_new_distinct'] > 0
    assert a['baseline'] == generate_shadow(packet,snapshot,enabled=False,seed=7)['baseline']
    assert not a['final_portfolio_selected']
    by_id = {r['candidate_id']:r for r in a['shadow']}
    for thesis in a['theses']:
        for cid in thesis.get('candidate_ids',[]):
            roster = by_id[cid]['roster']; ids = {p['player_master_id'] for p in roster}
            assert len(ids) == (6 if fmt=='SHOWDOWN' else 9)
            assert by_id[cid]['salary'] <= 50000
            assert set(snapshot['policy']['locked_ids']) <= ids
            assert not set(snapshot['policy']['zero_remaining_exposure_ids']) & ids
            if thesis['construction']['type'] != 'diversify_away_from_game':
                assert {p for group in thesis['construction']['roles'].values() for p in group} <= ids
            if thesis['construction']['type'] == 'explicit_roles':
                for role,pids in thesis['construction']['roles'].items():
                    assert all(dict(player_master_id=p,role=role) in roster for p in pids)


@pytest.mark.parametrize('field,value,reason', [
    ('expires_at','2099-09-01T11:00:00Z','stale_thesis'),
    ('game_id','OTHER','wrong_slate_game'),
    ('analysis_at','2099-09-01T13:00:00Z','future_analysis')])
def test_bad_independent_thesis_does_not_block_others(field,value,reason):
    packet,snapshot = fixture('SHOWDOWN')
    packet['analyst_assessments'][0][field] = value
    result = generate_shadow(packet,snapshot,seed=7)
    assert reason in result['theses'][0]['reasons']
    assert result['comparison']['covered_theses'] >= 1


def test_hash_future_packet_and_wrong_format_fail_closed():
    packet,snapshot = fixture('SHOWDOWN')
    for field,value,reason in [('baseline_input_sha256','wrong','baseline_input_hash_mismatch'),('frozen_at','2099-09-01T13:00:00Z','packet_future_sourced')]:
        bad = deepcopy(packet); bad[field] = value
        result = generate_shadow(bad,snapshot)
        assert reason in result['packet_errors'] and not result['shadow']
    packet['analyst_assessments'][0]['construction_implications'][0]['format']='CLASSIC'
    assert 'wrong_format' in generate_shadow(packet,snapshot)['theses'][0]['reasons']


def test_duplicate_attribution_and_captain_identity():
    packet,snapshot = fixture('SHOWDOWN')
    duplicate = deepcopy(packet['analyst_assessments'][0]); duplicate['assessment_id']='also_breakout'
    packet['analyst_assessments'].append(duplicate)
    result = generate_shadow(packet,snapshot,seed=7)
    rows = [r for r in result['shadow'] if 'breakout:0' in r['thesis_ids']]
    assert all('also_breakout:0' in r['thesis_ids'] for r in rows)
    assert all(sum(p['role']=='CPT' for p in r['roster'])==1 for r in result['shadow'])
    assert all(next(p['player_master_id'] for p in r['roster'] if p['role']=='CPT') in {p['player_master_id'] for p in snapshot['players'] if p['showdown_captain_shortlisted']} for r in result['shadow'])


def test_screens_are_diagnostic_and_objective_unchanged():
    packet,snapshot = fixture('SHOWDOWN')
    baseline = deepcopy(snapshot['model']['objective'])
    snapshot['quality_screens']=[dict(id='strict_mean_fixture',sense='>=',threshold=10000,terms={n:1 for n in snapshot['variable_players']})]
    rehash(snapshot); packet['baseline_input_sha256']=snapshot['sha256']
    result = generate_shadow(packet,snapshot)
    assert result['shadow'] and all(r['eligibility_outcome']=='DIAGNOSTIC_ONLY' for r in result['shadow'])
    assert snapshot['model']['objective'] == baseline
    assert not result['relaxations']


def test_infeasible_and_unsupported_directives_abstain():
    packet,snapshot=fixture('SHOWDOWN')
    c=packet['analyst_assessments'][0]['construction_implications'][0]
    c['type']='arbitrary_prose'
    result=generate_shadow(packet,snapshot)
    assert 'unsupported_thesis_type' in result['theses'][0]['reasons']
    c['type']='player_emphasis'; pid=snapshot['policy']['zero_remaining_exposure_ids'][0]
    c['roles']={'PLAYER':[pid]}; packet['analyst_assessments'][0]['player_master_ids']=[pid]
    result=generate_shadow(packet,snapshot)
    assert result['theses'][0]['achieved']==0 and result['theses'][0]['solver_status']=='Infeasible'
    assert result['comparison']['covered_theses']>0


def test_snapshot_identity_scope_hash_budget():
    packet,snapshot=fixture('SHOWDOWN')
    broken=deepcopy(snapshot); broken['players'][0]['projection']+=1
    with pytest.raises(ValueError,match='hash_mismatch'): validate_snapshot(broken)
    broken=deepcopy(snapshot); broken['variable_players']['captain_0']['player_master_id']=broken['players'][1]['player_master_id']; rehash(broken)
    with pytest.raises(ValueError,match='identity'): validate_snapshot(broken)
    with pytest.raises(ValueError,match='budget'): generate_shadow(packet,snapshot,requested_per_thesis=101)
