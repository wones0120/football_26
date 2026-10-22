from copy import deepcopy
import pytest
from backend.app.tests.product.test_opportunity_events import play,SOURCE,CUTOFF
from backend.app.product_services.opportunity_events import build_event_evidence
from backend.app.product_services.sourcewide_post_fumble_workload import build_sourcewide_post_fumble,qualified_identity
from backend.app.product_services.fumble_event_components import VERSION
from backend.app.product_services.evaluation_record import digest

GID='2025_08_SF_WAS';A='00-0000001';Q='00-0000002';B='00-0000003';P='00-0000009'
def fixture():
 rs=[play(90,game_id=GID,posteam='SF',passer_player_id=Q,receiver_player_id=A),play(10,game_id=GID,posteam='SF',passer_player_id=Q,receiver_player_id=B)]
 e=build_event_evidence(rs,canonical_ids={A:'00000000-0000-0000-0000-000000000001',Q:'00000000-0000-0000-0000-000000000002',B:'00000000-0000-0000-0000-000000000003'},source_receipt=SOURCE,cutoff=CUTOFF)
 p=dict(version='validated_native_order_map_v1',before_period=202509,rows=[dict(game_id=GID,play_id=k,order_sequence=n,native_order_verified=True,is_control=k==50)for k,n in((90,1),(50,2),(10,3))],unknown_order_games=[])
 p['semantic_sha256']=digest(p);p.update(source_snapshot_id=SOURCE['snapshot_id'],source_byte_sha256=SOURCE['content_sha256'],event_receipt_sha256=e['sha256'])
 f=dict(version=VERSION,before_period=202509,event_basis=[dict(game_id=GID,play_id=str(k),eligible=True,fumble_play=k==50)for k in(90,50,10)],fumble_ledger=[dict(game_id=GID,play_id='50',reported_fumblers=[dict(slot=1,team='SF',native_id=A)])])
 return e,p,f

def run(x=None,edges=(),uncertain=()):
 e,p,f=x or fixture();return build_sourcewide_post_fumble(e,p,f,fumble_source_sha256=SOURCE['content_sha256'],identity_edges=edges,before_period=202509,cutoff=CUTOFF,uncertain_official_rows=uncertain)
def repin(p):p['semantic_sha256']=digest({k:p[k]for k in('version','before_period','rows','unknown_order_games')})
def test_standalone_special_anchor_provider_order_not_numeric_playid():
 r=run()['rows'][0];m=r['metrics']['targets']
 assert r['first_certified_anchor']['play_id']=='50' and r['exact_first_anchor'] is True
 assert m['before']['exact_share']==1 and m['after']['exact_share']==0 and m['after_minus_before']==-1

def test_special_only_native_actor_usage_undefined_not_zero():
 e,p,f=fixture();f['fumble_ledger'][0]['reported_fumblers'][0]['native_id']=P
 r=run((e,p,f))['rows'][0];assert r['observed_official_usage']is False
 assert r['metrics']['targets']['after']['exact_actor_count']is None
 assert r['metrics']['targets']['after_minus_before']is None
 assert len(run((e,p,f))['identity_review_requests'])==1

def test_two_native_fumblers_both_anchored_without_recovery_pairing():
 e,p,f=fixture();f['fumble_ledger'][0]['reported_fumblers'].append(dict(slot=2,team='SF',native_id=B))
 assert {r['source_player_id']for r in run((e,p,f))['rows']}=={A,B}

def test_anchor_event_itself_excluded_from_official_denominators():
 e,p,f=fixture();f['event_basis'][0]['fumble_play']=True;f['fumble_ledger'][0]['play_id']='90'
 r=run((e,p,f))['rows'][0];assert r['metrics']['targets']['before']['known_team_count']==0
 assert r['metrics']['targets']['before']['exact_share']is None
 assert r['metrics']['targets']['after']['known_team_count']==1

@pytest.mark.parametrize('native,team',[(None,'SF'),(A,None),(None,None),(A,'SF')])
def test_possible_earlier_anchor_masks_every_compatible_actor(native,team):
 e,p,f=fixture();f['event_basis'][0].update(eligible=None,fumble_play=True)
 f['fumble_ledger'].append(dict(game_id=GID,play_id='90',reported_fumblers=[dict(slot=1,team=team,native_id=native)]))
 r=next(r for r in run((e,p,f))['rows']if r['source_player_id']==A)
 assert r['exact_first_anchor']is False and r['possible_earlier_anchor_evidence']
 assert r['metrics']['targets']['after_minus_before']is None

def test_known_other_native_or_team_earlier_unknown_not_compatible():
 for native,team in((B,'SF'),(None,'WAS')):
  e,p,f=fixture();f['event_basis'][0].update(eligible=None,fumble_play=True);f['fumble_ledger'].append(dict(game_id=GID,play_id='90',reported_fumblers=[dict(slot=1,team=team,native_id=native)]))
  assert next(r for r in run((e,p,f))['rows']if r['source_player_id']==A)['exact_first_anchor']is True

def test_unknown_later_fumble_does_not_erase_known_first_anchor():
 e,p,f=fixture();f['event_basis'][2].update(eligible=None,fumble_play=True);f['fumble_ledger'].append(dict(game_id=GID,play_id='10',reported_fumblers=[]))
 assert run((e,p,f))['rows'][0]['exact_first_anchor']is True

def test_excluded_earlier_source_row_never_becomes_live_anchor():
 e,p,f=fixture();f['event_basis'][0].update(eligible=False,fumble_play=True);f['fumble_ledger'].append(dict(game_id=GID,play_id='90',reported_fumblers=[dict(slot=1,team='SF',native_id=A)]))
 x=run((e,p,f));assert x['rows'][0]['exact_first_anchor']is True and len(x['excluded_anchor_evidence'])==1

def test_ambiguous_source_without_native_identity_kept_global_possible():
 e,p,f=fixture();f['event_basis'][0].update(eligible=None,fumble_play=None)
 x=run((e,p,f));assert len(x['possible_anchor_evidence'])==1 and not x['rows'][0]['exact_first_anchor']

def test_unknown_order_masks_all_first_anchor_proofs():
 e,p,f=fixture();p['unknown_order_games']=[GID];p['rows'][0]['native_order_verified']=False;p['rows'][0]['order_sequence']=None;repin(p)
 assert run((e,p,f))['rows'][0]['exact_first_anchor']is False

@pytest.mark.parametrize('bad',['duplicateorder','missingrow','duplicateledger','sourcesha','semantic'])
def test_complete_native_source_event_order_binding(bad):
 e,p,f=fixture()
 if bad=='duplicateorder':p['rows'][1]['order_sequence']=1;repin(p)
 if bad=='missingrow':f['event_basis'].pop()
 if bad=='duplicateledger':f['fumble_ledger'].append(deepcopy(f['fumble_ledger'][0]))
 if bad=='sourcesha':p['source_byte_sha256']='b'*64
 if bad=='semantic':p['semantic_sha256']='b'*64
 with pytest.raises(ValueError):run((e,p,f))

def test_entire_global_collision_graph_includes_ambiguous_edges():
 x=qualified_identity([(A,'00000000-0000-0000-0000-000000000001'),(A,'00000000-0000-0000-0000-000000000002'),(B,'00000000-0000-0000-0000-000000000001'),(P,'00000000-0000-0000-0000-000000000003')])
 assert x[A]is None and x[B]is None and x[P]=='00000000-0000-0000-0000-000000000003'
 assert run(edges=[(A,'00000000-0000-0000-0000-000000000009')])['rows'][0]['player_master_id']is None


def test_possible_unscoped_official_row_masks_both_compatible_team_channels():
 e,p,f=fixture();p['rows'].append(dict(game_id=GID,play_id=30,order_sequence=4,native_order_verified=True,is_control=True));repin(p);f['event_basis'].append(dict(game_id=GID,play_id='30',eligible=None,fumble_play=False));x=run((e,p,f),uncertain=[dict(game_id=GID,play_id='30',possible_teams=['SF','WAS'],possible_channels=['targets'])])
 r=x['rows'][0];assert r['metrics']['targets']['after']['exact_share']is None
 assert r['metrics']['pass_attempts']['after']['exact_share']==0


def test_unknown_team_native_is_qualified_and_unresolved_request_retained():
 e,p,f=fixture();f['fumble_ledger'][0]['reported_fumblers'].append(dict(slot=2,team=None,native_id=P));x=run((e,p,f))
 assert P in x['potential_native_fumbler_ids']and x['identity_qualification'][P]is None
 assert any(q['source_player_id']==P and q['team']is None for q in x['identity_review_requests'])

def test_unattributed_official_channel_masks_actor_count_but_keeps_budget():
 e,p,f=fixture();e['events'][1]['opportunities'][-1]['source_player_id']=None
 from backend.app.tests.product.test_post_fumble_workload import rehash_e,rehash_p
 rehash_e(e);rehash_p(p,e);r=run((e,p,f))['rows'][0]
 assert r['metrics']['targets']['after']['exact_actor_count']is None
 assert r['metrics']['targets']['after']['exact_team_count']==1


def test_identity_persistence_append_only_idempotence_and_closed_case_preservation(tmp_path,monkeypatch):
 import json,hashlib
 from pathlib import Path
 from backend.app.product_services.sourcewide_post_fumble_workload import persist_sourcewide_identity_requests
 monkeypatch.chdir(tmp_path);e,p,f=fixture();f['fumble_ledger'][0]['reported_fumblers'][0]['native_id']=P;x=run((e,p,f))
 b=json.dumps(x).encode();sha=hashlib.sha256(b).hexdigest();p=Path('artifacts/sourcewide_post_fumble_workload')/(sha+'.json');p.parent.mkdir(parents=True);p.write_bytes(b);ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(b))
 class Fake:
  def __init__(self):self.rows={}
  def execute(self,sql,values):
   assert 'DO NOTHING'in str(sql)and 'UPDATE'not in str(sql)
   self.rows.setdefault(values['key'],dict(values,status='resolved',first_seen='original'))
 conn=Fake();a=persist_sourcewide_identity_requests(conn,x,artifact_ref=ref);before=deepcopy(conn.rows)
 assert a==persist_sourcewide_identity_requests(conn,x,artifact_ref=ref)and conn.rows==before
 assert len(a['records'])==1 and next(iter(conn.rows.values()))['status']=='resolved'
 x['model_consumed']=True
 with pytest.raises(ValueError):persist_sourcewide_identity_requests(conn,x,artifact_ref=ref)


def test_missing_opposing_official_log_never_certifies_zero_team_budget():
 e,p,f=fixture();f['fumble_ledger'][0]['reported_fumblers'][0].update(team='WAS',native_id=P)
 r=run((e,p,f))['rows'][0];assert r['observed_official_team_log']is False
 assert r['metrics']['targets']['before']['exact_team_count']is None
