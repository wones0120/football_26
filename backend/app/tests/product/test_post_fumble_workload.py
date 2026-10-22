from copy import deepcopy
import pytest
from backend.app.tests.product.test_opportunity_events import play,build,CUTOFF
from backend.app.product_services.post_fumble_workload import build_post_fumble_workload
from backend.app.product_services.evaluation_record import digest


def inputs():
    rows=[play(30,order_sequence=1,receiver_player_id='w'),play(20,order_sequence=2,fumble=1,fumbled_1_player_id='w',fumbled_1_team='SF'),play(10,order_sequence=3,receiver_player_id='r')]
    for r in rows:r.update(game_id='2025_08_SF_WAS',posteam='SF')
    evidence=build(rows)
    proof=dict(version='validated_native_order_map_v1',before_period=202509,rows=[dict(game_id=r['game_id'],play_id=r['play_id'],order_sequence=r['order_sequence'],is_control=False,native_order_verified=True) for r in rows],unknown_order_games=[])
    proof['semantic_sha256']=digest(proof);proof.update(source_snapshot_id=evidence['source']['snapshot_id'],source_byte_sha256=evidence['source']['content_sha256'],event_receipt_sha256=evidence['sha256'])
    return evidence,proof


def run(e=None,p=None):
    a,b=inputs();return build_post_fumble_workload(e or a,p or b,before_period=202509,cutoff=CUTOFF)


def rehash_e(e):
    import json,hashlib
    e.pop('sha256');e['sha256']=hashlib.sha256(json.dumps(e,sort_keys=True,allow_nan=False).encode()).hexdigest()


def rehash_p(p,e):
    p['semantic_sha256']=digest({k:p[k] for k in ('version','before_period','rows','unknown_order_games')});p['event_receipt_sha256']=e['sha256']


def test_provider_order_anchor_excluded_signed_share_change():
    r=run()['rows'][0];m=r['metrics']['targets']
    assert r['anchor_play_id']=='20' and r['anchor_order_sequence']==2
    assert m['before']['known_team_opportunities']==m['after']['known_team_opportunities']==1
    assert m['before']['exact_share']==1 and m['after']['exact_share']==0 and m['after_minus_before']==-1
    assert run()['forecast'] is None and run()['pregame_serving_eligible'] is False


def test_unknown_eligibility_masks_not_fake_zero_after_use():
    e,p=inputs();e['events'][2]['unknown_channels'].append('targets');rehash_e(e);rehash_p(p,e)
    m=run(e,p)['rows'][0]['metrics']['targets']
    assert m['after']['exact_share'] is None and m['after_minus_before'] is None


def test_empty_denominator_undefined_and_no_fantasy_or_lost_fumble_inference():
    r=run()['rows'][0]
    assert r['metrics']['rush_attempts']['before']['exact_share'] is None
    assert r['metrics']['rush_attempts']['after_minus_before'] is None
    assert 'fumble_lost' not in r and 'fantasy_points' not in r


def test_unknown_fumbler_team_and_actor_retained():
    e,p=inputs();e['events'][1]['raw_flags']['fumbled_1_team']=None;rehash_e(e);rehash_p(p,e)
    x=run(e,p);assert not x['rows'] and len(x['unknown_anchor_evidence'])==1
    e,p=inputs();e['events'][1]['raw_flags']['fumbled_1_player_id']=None;rehash_e(e);rehash_p(p,e)
    assert run(e,p)['unknown_anchor_evidence'][0]['reason']=='Known fumble native actor absent'


def test_unmapped_native_anchor_is_not_name_guessed():
    e,p=inputs();e['events'][1]['raw_flags']['fumbled_1_player_id']='native-unresolved';rehash_e(e);rehash_p(p,e)
    r=run(e,p);assert r['rows'][0]['player_master_id'] is None and len(r['identity_review_requests'])==1


def test_first_known_fumble_per_actor_not_numeric_play_id():
    e,p=inputs();e['events'][2]['raw_flags'].update(fumble=1,fumbled_1_player_id='w',fumbled_1_team='SF');rehash_e(e);rehash_p(p,e)
    r=run(e,p);assert len(r['rows'])==1 and r['rows'][0]['anchor_play_id']=='20'


def test_two_fumblers_not_assumed_same_actor_or_lost_likelihood():
    e,p=inputs();e['events'][1]['raw_flags'].update(fumbled_2_player_id='r',fumbled_2_team='SF');rehash_e(e);rehash_p(p,e)
    assert {r['source_player_id'] for r in run(e,p)['rows']}=={'w','r'}


@pytest.mark.parametrize('kind',['hash','source','missing','duplicate'])
def test_order_authentication_guards(kind):
    e,p=inputs()
    if kind=='hash':p['rows'][0]['order_sequence']=9
    if kind=='source':p['source_byte_sha256']='other'
    if kind=='missing':p['rows'].pop();rehash_p(p,e)
    if kind=='duplicate':p['rows'].append(deepcopy(p['rows'][0]));rehash_p(p,e)
    with pytest.raises(ValueError):run(e,p)


def test_nonserving_and_unknown_native_order_cannot_be_used():
    from backend.app.product_services.post_fumble_workload import require_feature_use
    x=run();assert require_feature_use(x,purpose='offline_descriptive') is x
    with pytest.raises(ValueError):require_feature_use(x,purpose='forecast')
    e,p=inputs()
    for r in p['rows']:r['native_order_verified']=False
    p['unknown_order_games']=['2025_08_SF_WAS'];rehash_p(p,e)
    x=run(e,p);assert not x['rows'] and len(x['unknown_anchor_evidence'])==3


def test_append_only_frozen_attachment_issue_and_tamper_guard(tmp_path):
    import json,hashlib
    from backend.app.product_services.post_fumble_identity import persist_identity_requests
    e,p=inputs();e['events'][1]['raw_flags']['fumbled_1_player_id']='00-0031234';rehash_e(e);rehash_p(p,e);x=run(e,p)
    raw=json.dumps(x,sort_keys=True,separators=(',',':')).encode();sha=hashlib.sha256(raw).hexdigest();path=tmp_path/(sha+'.json');path.write_bytes(raw);ref=dict(path=str(path),sha256=sha,bytes=len(raw))
    class DB:
        def __init__(self):self.rows={}
        def execute(self,sql,params):
            assert 'DO NOTHING' in str(sql) and 'UPDATE' not in str(sql)
            self.rows.setdefault(params['key'],'open')
    db=DB();a=persist_identity_requests(db,x,artifact_ref=ref,source_root=tmp_path)
    assert a['requests']==1 and not a['aliases_changed']
    key=a['records'][0]['source_record_key'];db.rows[key]='resolved'
    assert persist_identity_requests(db,x,artifact_ref=ref,source_root=tmp_path)==a and db.rows[key]=='resolved'
    path.write_bytes(raw+b' ')
    with pytest.raises(ValueError):persist_identity_requests(db,x,artifact_ref=ref,source_root=tmp_path)


def test_retrospective_wrapper_preserves_original_vs_actual_clocks(monkeypatch):
    from types import SimpleNamespace
    from backend.app.product_services.post_fumble_workload import derive_retrospective_post_fumble
    import backend.app.product_services.opportunity_source_capture as source
    import backend.app.product_services.game_clock_pace_catalog as ordering
    e,p=inputs();calls=[]
    def load(ref,snapshot,**kwargs):calls.append(kwargs);return {'event_evidence':e}
    monkeypatch.setattr(source,'load_event_artifact',load)
    monkeypatch.setattr(ordering,'validated_native_order_map',lambda parent,**kw:p)
    ref=dict(decision_cutoff_at=CUTOFF,before_period=202509);snapshot=SimpleNamespace(slate_lock_at='2025-09-02T00:00:00Z')
    x=derive_retrospective_post_fumble(ref,snapshot,actual_read_at='2026-10-20T05:00:00Z')
    assert calls[0]['cutoff'].isoformat()=='2025-09-01T00:00:00+00:00'
    assert x['provenance']['original_evidence_boundary_at']!=x['provenance']['actual_read_at']
    with pytest.raises(ValueError):derive_retrospective_post_fumble(ref,snapshot,actual_read_at='2025-09-01T01:00:00Z')
