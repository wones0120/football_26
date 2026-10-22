from copy import deepcopy
import pytest
from backend.app.product_services.weekly_effectiveness_catalog_features import build_weekly_effectiveness
from backend.app.product_services.model_weekly_workload_components import project_weekly_components
from backend.app.product_services.scheduled_workload_efficiency_model_inputs import build_workload_efficiency_contexts,_pool

A='00000000-0000-0000-0000-000000000001';B='00000000-0000-0000-0000-000000000002';D='00000000-0000-0000-0000-000000000004'
CUTOFF='2026-10-20T18:00:00+00:00'
def fixture():
 records=[];schedule=[]
 profiles=[('BUF','QB',1,A,10,6,100,2,8,0,0,0),('BUF','P',2,B,1,1,3,0,0,0,0,0),('BUF','WR',4,D,0,0,0,1,2,8,5,50),('MIA','QB',3,'00000000-0000-0000-0000-000000000003',15,10,150,2,8,0,0,0),('MIA','WR',5,'00000000-0000-0000-0000-000000000005',0,0,0,2,10,12,8,100)]
 for w in range(1,5):
  gid=f'2023_{w:02d}_MIA_BUF';schedule.append(dict(game_id=gid,season=2023,week=w,game_type='REG',home_team='BUF',away_team='MIA',game_date=f'2023-09-{w*7:02d}'))
  for team,pos,n,pid,pa,co,py,ca,ry,ta,re,yd in profiles:
   native=f'00-{n:07d}';sid=w*10+n
   raw=dict(season_type='REG',season=2023,week=w,team=team,position=pos,player_id=native,attempts=pa,completions=co,passing_yards=py,passing_tds=int(pa>1),interceptions=int(pa>1),carries=ca,rushing_yards=ry,targets=ta,receptions=re,receiving_yards=yd)
   records.append(dict(source_id=sid,ingest_run_id='frozen-run',imported_at='2026-10-20T17:00:00+00:00',source_player_id=native,player_master_id=pid,season=2023,week=w,team=team,position=pos,game_id=gid,raw_row_json=raw,native_alias_evidence=[dict(alias_id='alias-'+str(n),source_key=native,source_system='nflreadpy',player_master_id=pid,created_at='2026-10-20T16:00:00+00:00')]))
 return records,schedule

def source(records,schedule):
 w=build_weekly_effectiveness(records,before_period=202305,cutoff=CUTOFF)
 return project_weekly_components(w,dict(before_period=202305,actual_read_at=CUTOFF,rows=records),schedule)

def test_full_native_source_includes_punter_and_unresolved_counts():
 records,s=fixture();records[1].update(player_master_id=None,native_alias_evidence=[]);x=source(records,s)
 g=next(r for r in x['team_game_rows']if r['game_id']=='2023_01_MIA_BUF'and r['team']=='BUF')
 assert g['values']['attempts']==11 and g['values']['completions']==7 and g['participant_census']=='UNKNOWN'
 assert next(r for r in x['actor_rows']if r['source_id']=='12')['player_master_id']is None


def test_same3_pooled_all_passer_team_and_source_QB_actor_scope():
 records,s=fixture();x=source(records,s);contexts=build_workload_efficiency_contexts(x,s);g=next(r for r in contexts['team_contexts']if r['period']==202304 and r['team']=='BUF')
 assert g['features']['weekly3_own_completion_fraction']==21/33
 assert g['features']['weekly3_own_pass_attempts_mean']==11
 actor=[contexts['actor_index'][(f'2023_{w:02d}_MIA_BUF','BUF',A)]for w in(1,2,3)]
 assert _pool(actor,actor=True)['completion_fraction']==.6
 p=[contexts['actor_index'][(f'2023_{w:02d}_MIA_BUF','BUF',B)]for w in(1,2,3)]
 assert _pool(p,actor=True)['completion_fraction']is None and _pool(p,actor=True)['pass_attempts_mean']==1
 wr=[contexts['actor_index'][(f'2023_{w:02d}_MIA_BUF','BUF',D)]for w in(1,2,3)]
 assert _pool(wr,actor=True)['receiving_yards_per_target']==150/24

@pytest.mark.parametrize('mode',['missing','null_count','role_conflict','negative_signed_yards','zero_exposure'])
def test_unknown_role_missing_zero_and_signed_source_outcomes(mode):
 records,s=fixture()
 if mode=='missing':records=[r for r in records if r['source_id']!=21]
 if mode=='null_count':records[0]['raw_row_json']['attempts']=None
 if mode=='role_conflict':records[0]['raw_row_json']['pos']='WR'
 if mode=='negative_signed_yards':records[0]['raw_row_json']['rushing_yards']=-8
 if mode=='zero_exposure':
  for r in records:
   if r['source_player_id']=='00-0000001':r['raw_row_json'].update(attempts=0,completions=0,passing_yards=0,passing_tds=0,interceptions=0)
 x=source(records,s);idx={(r['game_id'],r['team'],r['player_master_id']):r for r in x['actor_rows']if r['player_master_id']};rs=[idx.get((f'2023_{w:02d}_MIA_BUF','BUF',A))for w in(1,2,3)];values=_pool(rs,actor=True)
 if mode in('missing','null_count','role_conflict','zero_exposure'):assert values['completion_fraction']is None
 if mode=='missing':assert values['pass_attempts_mean']is None and values['known_source_games']==2
 if mode=='negative_signed_yards':assert values['rushing_yards_per_carry']==8/6
 if mode=='zero_exposure':assert values['attempts_exposure']==0


def test_duplicate_native_actor_conflict_is_unknown_not_double_counted():
 records,s=fixture();weekly=build_weekly_effectiveness(records,before_period=202305,cutoff=CUTOFF);duplicate=deepcopy(records[0]);duplicate['source_id']=999;records.append(duplicate)
 x=project_weekly_components(weekly,dict(before_period=202305,actual_read_at=CUTOFF,rows=records),s)
 g=next(r for r in x['team_game_rows']if r['game_id']=='2023_01_MIA_BUF'and r['team']=='BUF');assert g['values']['attempts']is None
 assert len(x['unscoped_contributions'])==2


def test_positive_missing_only_supplied_scope_masks_not_historical_census_claim():
 records,s=fixture();weekly=build_weekly_effectiveness(records,before_period=202305,cutoff=CUTOFF)
 p=dict(season=2023,week=1,team='BUF',native_game_id='2023_01_MIA_BUF',offense_snaps=1)
 x=project_weekly_components(weekly,dict(before_period=202305,actual_read_at=CUTOFF,rows=records),s,positive_missing=[p]);g=next(r for r in x['team_game_rows']if r['game_id']==p['native_game_id']and r['team']=='BUF')
 assert g['values']['attempts']is None and g['participant_census']=='BOUNDED_SOURCE_EVIDENCE_ONLY'
 assert next(r for r in x['team_game_rows']if r['game_id']=='2023_02_MIA_BUF'and r['team']=='BUF')['participant_census']=='UNKNOWN'

@pytest.mark.parametrize('mode',['raw_hash','native_period','import_future','source_duplicate','native_game'])
def test_frozen_native_revision_guards(mode):
 records,s=fixture();weekly=build_weekly_effectiveness(records,before_period=202305,cutoff=CUTOFF)
 if mode=='raw_hash':records[0]['raw_row_json']['passing_yards']=999
 if mode=='native_period':records[0]['raw_row_json']['week']=2
 if mode=='import_future':records[0]['imported_at']='2026-10-21T00:00:00+00:00'
 if mode=='source_duplicate':records.append(deepcopy(records[0]))
 if mode=='native_game':records[0]['game_id']='2023_02_MIA_BUF'
 if mode=='native_game':
  x=project_weekly_components(weekly,dict(before_period=202305,actual_read_at=CUTOFF,rows=records),s);assert x['unscoped_contributions'];return
 with pytest.raises(ValueError):project_weekly_components(weekly,dict(before_period=202305,actual_read_at=CUTOFF,rows=records),s)


def test_new_matrix_team_label_scope_player_pooledshare_and_versions():
 from backend.app.product_services.scheduled_workload_efficiency_model_inputs import append_workload_efficiency,BASE_TEAM,BASE_PLAYER,BASE_TEAM_VERSION,BASE_PLAYER_VERSION,TEAM_COLUMNS,PLAYER_COLUMNS
 from backend.app.product_services.team_opportunity_models import prepare_model_inputs,WORKLOAD_VERSION as TV
 from backend.app.product_services.feature_block_model_inputs import prepare_player_inputs,WORKLOAD_VERSION as PV
 from backend.app.product_services.evaluation_record import digest
 records,s=fixture();src=source(records,s);ctx=build_workload_efficiency_contexts(src,s)
 r=dict(game_id='2023_04_MIA_BUF',team='BUF',period=202304,legacy_feature_ready=True,context_periods=[],legacy_periods=[],history_periods=[202301,202302,202303],features=dict.fromkeys(BASE_TEAM,1),labels=dict(pass_attempts=10,rush_attempts=2))
 m=dict(version=BASE_TEAM_VERSION,before_period=202606,feature_columns=list(BASE_TEAM),target_columns=list(r['labels']),rows=[r],provenance={},pressure_adapter={'version':'scheduled_pressure_model_inputs_v1'},coverage_adapter={'version':'scheduled_coverage_model_inputs_v1'});m['matrix_sha256']=digest({k:v for k,v in m.items()if k!='provenance'});before=deepcopy(m)
 out=append_workload_efficiency(m,ctx,src,grain='team',parent_refs={});p=prepare_model_inputs(out,train_before=202401,validation_before=202501)
 assert m==before and out['rows'][0]['labels']==dict(pass_attempts=11,rush_attempts=3)and out['rows'][0]['previous_role_filtered_labels']==r['labels']
 assert p['version']==TV and p['preprocessing']['columns']==list(TEAM_COLUMNS)
 r=deepcopy(r);r.update(player_master_id=A,position='QB',current_inference=False,features=dict.fromkeys(BASE_PLAYER,3),labels=dict(pass_attempts=10,rush_attempts=2,targets=0))
 m.update(version=BASE_PLAYER_VERSION,feature_columns=list(BASE_PLAYER),target_columns=list(r['labels']),rows=[r],usage='offline_retrospective_model_inputs');m['matrix_sha256']=digest({k:v for k,v in m.items()if k not in{'matrix_sha256','provenance'}})
 out=append_workload_efficiency(m,ctx,src,grain='player',parent_refs={});p=prepare_player_inputs(out,train_before=202401,validation_before=202501);f=out['rows'][0]['features']
 assert f['scheduled3_pass_attempts_pooled_share']==30/33 and f['scheduled3_rush_attempts_pooled_share']==6/9
 assert f['scheduled3_targets_pooled_share']==0 and f['scheduled3_completion_fraction']==.6
 assert f['latest_prior_role_QB']==1 and f['scheduled3_role_consistent']==1
 assert p['version']==PV and p['preprocessing']['columns']==list(PLAYER_COLUMNS)
 assert p['provenance']['label_contract']==out['label_contract']
 # Changing target-game source response or target diagnostic role cannot alter
 # ANY new prior-only input (labels remain separate measured outcomes).
 changed=deepcopy(records)
 for rr in changed:
  if rr['week']==4 and rr['source_player_id']=='00-0000001':rr['raw_row_json'].update(attempts=30,passing_yards=900,position='WR');rr['position']='WR'
 nextsrc=source(changed,s);nextctx=build_workload_efficiency_contexts(nextsrc,s);again=append_workload_efficiency(m,nextctx,nextsrc,grain='player',parent_refs={})
 assert again['rows'][0]['features']==out['rows'][0]['features']
 assert again['rows'][0]['labels']['pass_attempts']is None # mismatched raw revision not silently substituted


def test_same_native_actor_conflicting_game_sides_masks_both_contributions():
 records,s=fixture();r=deepcopy(records[0]);r.update(source_id=999,team='MIA');r['raw_row_json']['team']='MIA';records.append(r)
 x=source(records,s)
 for team in('BUF','MIA'):
  g=next(g for g in x['team_game_rows']if g['game_id']=='2023_01_MIA_BUF'and g['team']==team)
  assert g['values']['attempts']is None
