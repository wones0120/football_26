import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('contract',Path(__file__).with_name('contract.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def fixture():
 gs=[f'2023_{w:02}_BUF_NYJ'for w in range(1,5)]
 def row(g,sid,counts,pid='a'):
  return dict(game_id=g,source_id=g+sid,source_player_id=sid,player_master_id=pid,source_position='QB'if sid=='a'else None,counts=dict(zip(m.CHANNEL_FIELDS,counts)))
 actors={(g,'BUF'):[row(g,'a',[0,0,0])]for g in gs};teams={(g,'BUF'):dict(source_rows=1,values=dict(attempts=0,carries=0,targets=0))for g in gs}
 context=dict(game_id=gs[-1],team='BUF',period=202304,windows=dict(own=dict(game_ids=gs[:3])))
 return context,actors,teams,row

def test_prior_zero_allroles_kept_current_new_actor_disjoint_rest():
 c,a,t,row=fixture();g=c['game_id'];a[g,'BUF'].append(row(g,'new',[1,2,1],None));t[g,'BUF']['values']=dict(attempts=1,carries=2,targets=1)
 r=m.audit_group(c,a,t);assert r['candidate_count']==1 and r['candidate_prior_all_channels_zero']==1
 for ch in m.CHANNEL_FIELDS:assert r['channels'][ch]['native_source_complete_group'] and r['channels'][ch]['canonical_complete_group']
 assert r['channels']['targets']['known_outside_unresolved_sum']==1

def test_absent_candidate_unknown_despite_zero_compatible_source_budget():
 c,a,t,row=fixture();a[c['game_id'],'BUF']=[];t[c['game_id'],'BUF']['source_rows']=0
 r=m.audit_group(c,a,t)
 assert r['candidate_native_labels'][0]['counts']==dict.fromkeys(m.CHANNEL_FIELDS)
 assert all(not x['native_source_complete_group']and x['unknown_candidate_count']==1 for x in r['channels'].values())
 assert r['channels']['targets']['numeric_disjoint_outside_rest']==0

def test_unresolved_inside_not_rest_or_canonical_value():
 c,a,t,row=fixture()
 for rs in a.values():rs[0]['player_master_id']=None
 r=m.audit_group(c,a,t);x=r['channels']['targets']
 assert x['native_source_complete_group'] and not x['canonical_complete_group'] and x['known_outside_unresolved_sum']==0

def test_no_skip_missing_prior_unachieved_and_no_target_selection():
 c,a,t,row=fixture();del t[c['windows']['own']['game_ids'][1],'BUF']
 r=m.audit_group(c,a,t);assert not r['history_achieved']and r['candidate_count']==1
 assert not r['channels']['targets']['native_source_complete_group']

def test_unknown_budget_not_repaired_from_candidate_zero():
 c,a,t,row=fixture();t[c['game_id'],'BUF']['values']['targets']=None
 assert not m.audit_group(c,a,t)['channels']['targets']['native_source_complete_group']

def test_identity_collision_canonical_withheld_native_counts_kept():
 c,a,t,row=fixture();a[c['windows']['own']['game_ids'][0],'BUF'][0]['player_master_id']='b'
 x=m.audit_group(c,a,t);assert x['candidate_native_labels'][0]['canonical_prior_attachment_conflict']
 assert not x['channels']['targets']['canonical_complete_group']and x['channels']['targets']['native_source_complete_group']

@pytest.mark.parametrize('kind',['future','duplicate','otherseason'])
def test_prior_native_boundaries(kind):
 c,a,t,row=fixture()
 if kind=='future':c['windows']['own']['game_ids'][0]=c['game_id']
 elif kind=='duplicate':c['windows']['own']['game_ids'][0]=c['windows']['own']['game_ids'][1]
 else:c['windows']['own']['game_ids'][0]='2022_18_BUF_NYJ'
 with pytest.raises(ValueError):m.audit_group(c,a,t)
