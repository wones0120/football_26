from copy import deepcopy
import pytest
from backend.app.product_services.observed_depth_changes import build_observed_depth_changes
P='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

def source(day,rank='1',**row):
 return dict(snapshot_id=str(day),season=2026,week=6,teams=['SF'],observed_at=f'2026-10-{day:02}T10:00:00Z',captured_at=f'2026-10-{day:02}T11:00:00Z',rows=[dict(team='SF',gsis_id='00-0031234',pos_abb='KR',pos_slot='5',pos_rank=rank,dt=f'2026-10-{day:02}T09:00:00Z',**row)])
def build(sources,aliases=None):return build_observed_depth_changes(sources,aliases or {'00-0031234':P},season=2026,week=6,cutoff='2026-10-20T10:00:00Z')

def test_literal_rank_and_special_unit():
 r=build([source(17),source(18,'3')]);v=r['comparisons'][0]['matched_roles'][0]
 assert (v['rank_delta'],v['unit'],v['source_slot'])==(2,'special_teams','5')
 assert r['forecast'] is False

def test_missing_not_demotion():
 s=source(18);s['rows'][0]['gsis_id']='00-0035555'
 c=build([source(17),s])['comparisons'][0]
 assert not c['matched_roles'] and len(c['newly_observed_roles'])==len(c['not_observed_roles'])==1

def test_position_slot_not_cross_joined():
 s=source(18);s['rows'][0]['pos_abb']='WR'
 assert not build([source(17),s])['comparisons'][0]['matched_roles']

def test_null_rank_unknown():assert build([source(17),source(18,'')])['comparisons'][0]['matched_roles'][0]['rank_delta'] is None

def test_native_unresolved_retained():
 r=build([source(17)],{'00-0031234':[P,'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb']})
 assert len(r['identity_review_requests'])==1

@pytest.mark.parametrize('mutation',[lambda s:s.update(week=7),lambda s:s.update(captured_at='2026-10-21T11:00:00Z'),lambda s:s['rows'][0].update(dt='2026-10-21T10:00:00Z'),lambda s:s['rows'].append(deepcopy(s['rows'][0]))])
def test_guards(mutation):
 s=source(18);mutation(s)
 with pytest.raises(ValueError):build([s])

def test_no_cross_universe_comparison():
 a=source(17);b=source(18);b['teams']=['WAS'];b['rows'][0]['team']='WAS'
 assert not build([a,b])['comparisons']

def test_document_regression_rejected():
 a=source(17);b=source(18);b['rows'][0]['dt']='2026-10-16T09:00:00Z'
 with pytest.raises(ValueError):build([a,b])

def test_latest_document_only():
 s=source(18);old=deepcopy(s['rows'][0]);old['dt']='2026-10-17T09:00:00Z';s['rows'].append(old)
 assert len(build([source(17),s])['comparisons'][0]['matched_roles'])==1


def test_missing_native_quarantined_not_name_joined():
 s=source(18);s['rows'][0]['gsis_id']='';r=build([source(17),s])
 assert len(r['unkeyed_source_roles'])==1 and r['identity_review_requests'][0]['source_player_id']==''
 assert not r['comparisons'][0]['matched_roles']

def test_append_only_frozen_attachment_incidents(tmp_path):
 import json,hashlib
 from backend.app.product_services.observed_depth_changes import persist_depth_identity_requests
 s=source(17);s['content_sha256']='a'*64;r=build([s],{'00-0031234':[]})
 raw=json.dumps(r).encode();sha=hashlib.sha256(raw).hexdigest();p=tmp_path/(sha+'.json');p.write_bytes(raw);ref=dict(path=str(p),sha256=sha,bytes=len(raw))
 class C:
  def __init__(self):self.calls=[]
  def execute(self,query,args):self.calls.append((str(query),args))
 c=C();out=persist_depth_identity_requests(c,r,artifact_ref=ref,source_root=tmp_path)
 assert len(out['records'])==1 and len(c.calls)==1
 assert 'DO NOTHING' in c.calls[0][0] and not out['aliases_changed'] and not out['resolved_issues_reopened']
 p.write_text('{}')
 with pytest.raises(ValueError):persist_depth_identity_requests(c,r,artifact_ref=ref,source_root=tmp_path)
