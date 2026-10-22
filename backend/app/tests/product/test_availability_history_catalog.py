from copy import deepcopy
import pytest
from backend.app.tests.product.test_absence_return_opportunity import inputs,NOW
from backend.app.product_services.absence_return_opportunity import build_absence_return_opportunity
from backend.app.product_services.availability_history_catalog import build_availability_history,load_reviewed_return_input

def make():
 a,w,s=inputs();a['game_date']='2025-09-21';r=build_absence_return_opportunity(a,w,s,before_period=202507,cutoff=NOW);r['provenance']['actual_publication_at']='2026-10-20T02:00:00Z';return a,r,w

def run(a=None,r=None,w=None):
 aa,rr,ww=make();return build_availability_history(a or aa,r or rr,w or ww,cutoff=NOW)

def test_literal_inactive_history_and_measured_return_source_role():
 x=run();assert len(x['inactive_history_rows'])==1
 s=x['return_status_rows'][0];assert s['first_return_proven'] is True and s['observed_source_role_continuity'] is True
 assert s['latest_proven_participating_game']['week']==6
 assert s['health_recovery'] is None and x['inactive_history_rows'][0]['complete_inactive_history'] is None

def test_missing_return_chronology_not_false_or_recovered():
 a,w,s=inputs();a['game_date']='2025-09-21';w['rows']=[x for x in w['rows'] if x['week']!=4]
 r=build_absence_return_opportunity(a,w,s,before_period=202507,cutoff=NOW);r['provenance']['actual_publication_at']='2026-10-20T02:00:00Z'
 v=run(a,r,w)['return_status_rows'][0];assert v['first_return_proven'] is None and v['observed_source_role_continuity'] is None
 assert v['latest_proven_participating_game']['week']==6

def test_missing_preabsence_role_not_assumed_continuity():
 a,r,w=make();w['rows'][1]['source_position']=None
 assert run(a,r,w)['return_status_rows'][0]['observed_source_role_continuity'] is None

def test_known_source_role_change_is_false_not_unknown_health():
 a,r,w=make();r['rows'][0]['scheduled_postabsence_slots'][-1]['source_position']='WR'
 assert run(a,r,w)['return_status_rows'][0]['observed_source_role_continuity'] is False

def test_unresolved_ordinary_fact_preserved_without_inventing_history_zero():
 a,r,w=make();f=deepcopy(a['rows'][0]);f.update(source_row_key='unresolved',player_master_id=None,source_native_gsis_id=None,source_position='LB');a['rows'].append(f);r['provenance']['absence_source_provenance']=deepcopy(a['provenance'])
 x=run(a,r,w);assert len(x['inactive_history_rows'])==2 and x['inactive_history_rows'][1]['source_fact']['player_master_id'] is None

def test_dnp_and_emergency_not_inactive_history():
 a,r,w=make()
 for status in ('DID_NOT_PLAY','EMERGENCY_THIRD_QB_EXCEPTION'):
  f=deepcopy(a['rows'][0]);f.update(ordinary_absence_anchor=False,source_status=status,source_row_key=status);a['rows'].append(f)
 x=run(a,r,w);assert len(x['inactive_history_rows'])==1 and len(x['excluded_source_domains'])==2

@pytest.mark.parametrize('kind',['native','uuid','future','sourcepair','duplicate','wrongstatus'])
def test_binding_clock_scope_guards(kind):
 a,r,w=make()
 if kind=='native':r['rows'][0]['source_native_gsis_id']='00-0099999'
 if kind=='uuid':r['rows'][0]['player_master_id']=None
 if kind=='future':r['provenance']['actual_publication_at']='2026-10-21T01:00:00Z'
 if kind=='sourcepair':r['provenance']['absence_source_provenance']['extra']='different'
 if kind=='duplicate':a['rows'].append(deepcopy(a['rows'][0]))
 if kind=='wrongstatus':a['rows'][0]['source_status']='DID_NOT_PLAY'
 with pytest.raises(ValueError):run(a,r,w)

def test_no_source_history_does_not_synthesize_active_rows():
 a,r,w=make();a['rows']=[];r['rows']=[]
 x=run(a,r,w);assert x['inactive_history_rows']==[] and x['return_status_rows']==[]

def test_unmanaged_return_reader_rejects():
 with pytest.raises(ValueError):load_reviewed_return_input(dict(path='/tmp/no.json',sha256='a'*64,bytes=10),cutoff=NOW)

@pytest.mark.parametrize('latest_role,expected',[('WR',False),(None,None)])
def test_latest_proven_role_after_unknown_slot_never_omitted(latest_role,expected):
 a,w,s=inputs();a['game_date']='2025-09-21';w['rows']=[x for x in w['rows'] if x['week']!=5];w['rows'][-1]['source_position']=latest_role
 r=build_absence_return_opportunity(a,w,s,before_period=202507,cutoff=NOW);r['provenance']['actual_publication_at']='2026-10-20T02:00:00Z'
 v=run(a,r,w)['return_status_rows'][0]
 assert v['first_return_proven'] is True and v['first_verified_return']['week']==4
 assert v['latest_proven_participating_game']['week']==6
 assert v['observed_role_evidence_path']==['TE','TE',latest_role]
 assert v['observed_source_role_continuity'] is expected
