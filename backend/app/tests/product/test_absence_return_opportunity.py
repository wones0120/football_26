from copy import deepcopy
import pytest
from backend.app.product_services.absence_return_opportunity import build_absence_return_opportunity
from backend.app.product_services.official_absence_source import VERSION as AV
from backend.app.product_services.weekly_effectiveness_catalog_features import VERSION as WV
from backend.app.product_services.schedule_context_features import VERSION as SV
P='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';N='00-0031234';NOW='2026-10-20T09:00:00Z'

def inputs():
 a=dict(version=AV,pregame_serving_eligible=False,provenance=dict(actual_publication_at='2026-10-20T01:00:00Z'),rows=[dict(ordinary_absence_anchor=True,source_status='NOT_ACTIVE',source_position='TE',source_row_key='source1',season=2025,week=3,team='SF',native_game_id='2025_03_SF_WAS',source_native_gsis_id=N,player_master_id=P)])
 def row(week,target,rush=0):return dict(season=2025,week=week,season_type='REG',team='SF',source_player_id=N,player_master_id=P,native_game_id=f'2025_{week:02}_SF_WAS',source_position='TE',QB_scope_source_proven=False,metrics={'G09-M01':dict(denominator=target),'G07-M01':dict(denominator=rush)})
 w=dict(version=WV,before_period=202607,pregame_serving_eligible=False,provenance=dict(actual_derived_at='2026-10-20T01:00:00Z'),rows=[row(1,4),row(2,2),row(4,7),row(5,6),row(6,6)])
 s=dict(version=SV,pregame_serving_eligible=False,provenance={},game_rows=[dict(game_type='REG',season=2025,week=i,game_id=f'2025_{i:02}_SF_WAS',home_team='SF',away_team='WAS') for i in range(1,7)])
 return a,w,s

def run(a=None,w=None,s=None):
 aa,ww,ss=inputs();return build_absence_return_opportunity(a or aa,w or ww,s or ss,before_period=202507,cutoff=NOW)

def test_fixed_scheduled_baseline_and_three_actual_appearance_ordinals():
 r=run()['rows'][0];assert r['baseline']['targets']['mean_count']==3
 assert r['metrics']['X03-M01']['first_verified_active']['baseline_difference']['targets']==4
 assert r['metrics']['X03-M02']['second_verified_active']['baseline_difference']['targets']==3
 assert r['metrics']['X03-M02']['third_verified_active']['certified_active_ordinal']==3
 assert r['metrics']['X03-M02']['third_verified_active']['scheduled_game_offset']==3

def test_missing_earlier_slot_blocks_later_first_not_latest_positive_fallback():
 a,w,s=inputs();w['rows']=[r for r in w['rows'] if r['week']!=4]
 r=run(a,w,s)['rows'][0];assert r['metrics']['X03-M01']['first_verified_active'] is None
 assert all(v['certified_active_ordinal'] is None for v in r['scheduled_postabsence_slots'])
 assert r['scheduled_postabsence_slots'][1]['proven_active_appearance_lower_bound']==1

def test_all_zero_weekly_row_not_participation_or_dnp():
 a,w,s=inputs();w['rows'][2]['metrics']['G09-M01']['denominator']=0
 assert run(a,w,s)['rows'][0]['metrics']['X03-M01']['first_verified_active'] is None

def test_positive_rush_certifies_zero_target_response():
 a,w,s=inputs();w['rows'][2]['metrics']['G09-M01']['denominator']=0;w['rows'][2]['metrics']['G07-M01']['denominator']=1
 r=run(a,w,s)['rows'][0]['metrics']['X03-M01']['first_verified_active'];assert r['baseline_difference']['targets']==-3

def test_explicit_later_absence_skips_active_ordinal_but_retains_scheduled_slot():
 a,w,s=inputs();later=deepcopy(a['rows'][0]);later.update(week=4,native_game_id='2025_04_SF_WAS',source_row_key='source2');a['rows'].append(later);w['rows']=[r for r in w['rows'] if r['week']!=4]
 r=run(a,w,s)['rows'][0];assert r['metrics']['X03-M01']['first_verified_active']['week']==5
 assert r['metrics']['X03-M01']['first_verified_active']['scheduled_game_offset']==2

def test_unknown_after_certified_first_does_not_retroactively_erase_it():
 a,w,s=inputs();w['rows']=[r for r in w['rows'] if r['week']!=5]
 r=run(a,w,s)['rows'][0];assert r['metrics']['X03-M01']['first_verified_active']['week']==4
 assert r['metrics']['X03-M02']['second_verified_active'] is None

def test_missing_preabsence_fixed_slot_masks_baseline_no_active_lookback_fallback():
 a,w,s=inputs();w['rows']=[r for r in w['rows'] if r['week']!=2]
 r=run(a,w,s)['rows'][0];assert r['baseline']['targets']['mean_count'] is None
 assert r['metrics']['X03-M01']['first_verified_active']['baseline_difference']['targets'] is None

def test_short_preabsence_history_not_two_game_baseline():
 a,w,s=inputs();a['rows'][0].update(week=1,native_game_id='2025_01_SF_WAS');w['rows']=[r for r in w['rows'] if r['week']!=1]
 assert run(a,w,s)['rows'][0]['baseline']['targets']['mean_count'] is None

@pytest.mark.parametrize('kind',['DNP','emergency'])
def test_other_official_domains_not_ordinary_absence(kind):
 a,w,s=inputs();a['rows'][0].update(ordinary_absence_anchor=False,source_status='DID_NOT_PLAY' if kind=='DNP' else 'EMERGENCY_THIRD_QB_EXCEPTION')
 assert run(a,w,s)['rows']==[]

@pytest.mark.parametrize('kind',['weeklygame','absencegame','canonical','negative','future','duplicate','positiveabsence'])
def test_scope_identity_clock_count_and_contradiction_guards(kind):
 a,w,s=inputs()
 if kind=='weeklygame':w['rows'][2]['native_game_id']='2025_04_LA_SEA'
 if kind=='absencegame':a['rows'][0]['native_game_id']='2025_03_LA_SEA'
 if kind=='canonical':w['rows'][2]['player_master_id']='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
 if kind=='negative':w['rows'][2]['metrics']['G09-M01']['denominator']=-1
 if kind=='future':a['provenance']['actual_publication_at']='2026-10-21T01:00:00Z'
 if kind=='duplicate':w['rows'].append(deepcopy(w['rows'][2]))
 if kind=='positiveabsence':x=deepcopy(w['rows'][2]);x.update(week=3,native_game_id='2025_03_SF_WAS');w['rows'].append(x)
 with pytest.raises(ValueError):run(a,w,s)

def test_unresolved_native_anchor_never_certifies_active_identity():
 a,w,s=inputs();a['rows'][0]['player_master_id']=None
 assert run(a,w,s)['rows'][0]['metrics']['X03-M01']['first_verified_active'] is None

def test_source_qb_gate_and_other_team_no_transfer():
 a,w,s=inputs();w['rows'][2]['team']='WAS';w['rows'][2]['native_game_id']='2025_04_SF_WAS'
 assert run(a,w,s)['rows'][0]['metrics']['X03-M01']['first_verified_active'] is None

@pytest.mark.parametrize('value',[float('nan'),float('inf'),True,1.5])
def test_invalid_counts_not_opportunity_or_zero(value):
 a,w,s=inputs();w['rows'][2]['metrics']['G09-M01']['denominator']=value
 with pytest.raises(ValueError):run(a,w,s)

def test_pass_positive_requires_explicit_source_qb_proof():
 a,w,s=inputs();w['rows'][2]['metrics']['G09-M01']['denominator']=0;w['rows'][2]['metrics']['G04-M01']=dict(denominator=5)
 assert run(a,w,s)['rows'][0]['metrics']['X03-M01']['first_verified_active'] is None

def test_absence_reader_rejects_unmanaged_source():
 from backend.app.product_services.absence_return_opportunity import load_reviewed_absence_input
 with pytest.raises(ValueError):load_reviewed_absence_input(dict(path='/tmp/unmanaged.json',sha256='a'*64,bytes=10),cutoff=NOW)
