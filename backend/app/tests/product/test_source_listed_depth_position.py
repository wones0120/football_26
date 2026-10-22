from copy import deepcopy
import pytest
from backend.app.tests.product.test_observed_depth_changes import source,build,P
from backend.app.product_services.source_listed_depth_position import build_source_listed_depth_position,load_reviewed_depth_parent

CUTOFF='2026-10-20T12:00:00Z'
def fixture():
 ss=[source(17),source(18,'2'),source(19,'3')]
 for s in ss:s['source_uri']='nflreadpy://depth_charts/2026'
 return build(ss)
def run(x=None):return build_source_listed_depth_position(x or fixture(),cutoff=CUTOFF)

def test_latest_capture_source_rank_and_role_current_at_document_only():
 x=run();r=x['role_facts'][0]
 assert r['source_snapshot_id']=='19'and r['source_depth_order']==3 and r['document_at']=='2026-10-19T09:00:00+00:00'
 assert r['source_listed_role']==dict(literal_position='KR',literal_slot='5',listed_order=3)
 assert r['effective_season_week']is None and r['target_game_applicability']is None
 assert r['primary_offense_starter']is None and r['expected_workload_share']is None
 assert x['capture_scope']['week']==6 and x['model_consumed']is False

@pytest.mark.parametrize('position,unit',[('KR','special_teams'),('PR','special_teams'),('QB','non_special_teams'),('RDT','non_special_teams')])
def test_rank1_is_literal_chart_order_not_primary_offense_starter(position,unit):
 x=fixture();r=x['comparisons'][-1]['matched_roles'][0];r.update(source_position=position,rank=1,unit=unit)
 r=run(x)['role_facts'][0];assert r['unit']==unit and r['source_depth_order']==1 and r['primary_offense_starter']is None

def test_null_rank_remains_unknown_not_zero():
 x=fixture();x['comparisons'][-1]['matched_roles'][0]['rank']=None
 assert run(x)['role_facts'][0]['source_depth_order']is None

def test_newly_observed_roles_included_not_just_intersection():
 x=fixture();r=x['comparisons'][-1]['matched_roles'].pop();x['comparisons'][-1]['newly_observed_roles'].append(r)
 assert len(run(x)['role_facts'])==1

def test_unresolved_native_and_unkeyed_source_rows_retained_no_persistence():
 x=fixture();x['comparisons'][-1]['matched_roles'][0]['player_master_id']=None
 q=dict(team='SF',source_snapshot_id='19',source_row=2,source_player_id='NOT-GSIS',reason='incomplete_native_depth_role_key');x['unkeyed_source_roles'].append(q);x['identity_review_requests'].append(q)
 out=run(x);assert out['role_facts'][0]['player_master_id']is None and out['unknown_source_roles']==[q]
 assert out['inherited_identity_requests']==x['identity_review_requests']

def test_first_only_frame_unreconstructible_not_empty_depth_chart():
 s=source(17);s['source_uri']='nflreadpy://depth_charts/2026';x=build([s]);out=run(x)
 assert not out['role_facts']and out['unknown_source_roles'][0]['reason']=='latest_frame_not_reconstructible_from_reviewed_comparison'

def test_unknown_capture_tie_never_arbitrarily_selects_role():
 x=fixture();s=deepcopy(x['provenance']['sources'][-1]);s['snapshot_id']='other';x['provenance']['sources'].append(s)
 assert not run(x)['role_facts']and run(x)['unknown_source_roles'][0]['reason']=='ambiguous_simultaneous_latest_capture'

@pytest.mark.parametrize('change',['futurecapture','futuredocument','duplicate','mixedlatest','unit','negative','captureweek','sourceuri'])
def test_scope_clock_role_and_document_guards(change):
 x=fixture();r=x['comparisons'][-1]['matched_roles'][0]
 if change=='futurecapture':x['provenance']['sources'][-1]['captured_at']='2026-10-21T00:00:00Z'
 if change=='futuredocument':r['document_at']='2026-10-21T00:00:00Z'
 if change=='duplicate':x['comparisons'][-1]['newly_observed_roles'].append(deepcopy(r))
 if change=='mixedlatest':
  q=deepcopy(r);q.update(source_player_id='00-0039999',document_at='2026-10-18T09:00:00Z');x['comparisons'][-1]['newly_observed_roles'].append(q)
 if change=='unit':r['unit']='non_special_teams'
 if change=='negative':r['rank']=0
 if change=='captureweek':x['provenance']['sources'][-1]['week']=7
 if change=='sourceuri':x['provenance']['sources'][-1]['source_uri']=None
 with pytest.raises(ValueError):run(x)

@pytest.mark.parametrize('change',[None,'bytes','semantic','producer','future'])
def test_parent_reader_authenticates_immutable_semantics_producer_actual_clock(tmp_path,monkeypatch,change):
 import json,hashlib
 from pathlib import Path
 from backend.app.product_services import observed_depth_changes
 monkeypatch.chdir(tmp_path);x=fixture();x['provenance'].update(producer_sha256=hashlib.sha256(Path(observed_depth_changes.__file__).read_bytes()).hexdigest(),actual_derived_at='2026-10-20T01:00:00Z')
 if change=='semantic':x['comparisons'][-1]['matched_roles'][0]['rank']=10
 if change=='producer':x['provenance']['producer_sha256']='b'*64
 if change=='future':x['provenance']['actual_derived_at']='2026-10-21T00:00:00Z'
 b=json.dumps(x).encode();sha=hashlib.sha256(b).hexdigest();p=Path('artifacts/observed_depth_changes')/(sha+'.json');p.parent.mkdir(parents=True);p.write_bytes(b);ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(b))
 if change=='bytes':p.write_bytes(b+b' ')
 if change:
  with pytest.raises(ValueError):load_reviewed_depth_parent(ref,cutoff=CUTOFF)
 else:assert load_reviewed_depth_parent(ref,cutoff=CUTOFF)['semantic_sha256']==x['semantic_sha256']
