from copy import deepcopy
import pytest
from backend.app.product_services.scheduled_pressure_model_inputs import build_contexts,append_pressure_context,TEAM_COLUMNS,PLAYER_COLUMNS
from backend.app.product_services.model_input_admission import admit_matrix
from backend.app.product_services.team_opportunity_matrix import FEATURES,VERSION
from backend.app.product_services.offensive_volume_features import digest


def fixture():
 schedule=[];rows=[]
 for w in range(1,5):
  gid=f'2023_{w:02d}_MIA_BUF';schedule.append(dict(game_id=gid,season=2023,week=w,game_type='REG',home_team='BUF',away_team='MIA',game_date=f'2023-09-{w*7:02d}'))
  for off,defense,n,d in [('BUF','MIA',w,10),('MIA','BUF',w*2,20)]:
   rows.append(dict(game_id=gid,season=2023,week=w,offense=off,defense=defense,known_source_pressure_sum=n,known_dropbacks=d,full_observed_cohort_proven=True,unknown_or_incompatible_reasons=[],pressure_rate=n/d))
 return dict(version='pfr_pressure_catalog_v1',pregame_serving_eligible=False,game_rows=rows),schedule


def test_exact_pool_prior_three_no_target_and_warmup():
 p,s=fixture();r=build_contexts(p,s)['rows'];g=next(r for r in r if r['team']=='BUF'and r['period']==202304)
 assert g['features']['pressure3_own_allowed_pressures']==6
 assert g['features']['pressure3_own_allowed_dropbacks']==30
 assert g['features']['pressure3_own_allowed_rate']==.2
 assert g['features']['pressure3_opponent_generated_pressures']==6
 assert g['axes']['own_allowed']['contributing_game_ids']==[f'2023_{w:02d}_MIA_BUF'for w in range(1,4)]
 assert r[0]['features']['pressure3_own_allowed_rate']is None and r[0]['features']['pressure3_own_allowed_unknown_games']==3
 p['game_rows'][-2]['known_source_pressure_sum']=10;p['game_rows'][-2]['pressure_rate']=1
 assert next(x for x in build_contexts(p,s)['rows']if x['period']==202304 and x['team']=='BUF')['features']==g['features']

@pytest.mark.parametrize('mode',['missing','incompatible','zero'])
def test_unknown_cohort_masks_full_no_skipping_and_zero_undefined(mode):
 p,s=fixture()
 if mode=='missing':p['game_rows'].pop(2)
 elif mode=='incompatible':p['game_rows'][2].update(full_observed_cohort_proven=False,unknown_or_incompatible_reasons=['pct_gap'],pressure_rate=None)
 else:
  for r in p['game_rows']:r.update(known_source_pressure_sum=0,known_dropbacks=0,pressure_rate=None)
 g=next(r for r in build_contexts(p,s)['rows']if r['team']=='BUF'and r['period']==202304)
 assert g['features']['pressure3_own_allowed_rate']is None
 if mode!='zero':assert g['features']['pressure3_own_allowed_pressures']is None and g['features']['pressure3_own_allowed_unknown_games']==1
 else:assert g['features']['pressure3_own_allowed_pressures']==0

@pytest.mark.parametrize('mode',['duplicate','side','period','count','rate','date'])
def test_native_shape_guards(mode):
 p,s=fixture()
 if mode=='duplicate':p['game_rows'].append(p['game_rows'][0])
 if mode=='side':p['game_rows'][0]['defense']='NYJ'
 if mode=='period':p['game_rows'][0]['week']=2
 if mode=='count':p['game_rows'][0]['known_dropbacks']=-1
 if mode=='rate':p['game_rows'][0]['pressure_rate']=.9
 if mode=='date':s[1]['game_date']=s[0]['game_date']
 with pytest.raises(ValueError):build_contexts(p,s)


def test_unsupported_year_no_prior_season_borrow():
 p,s=fixture();s.append(dict(s[-1],game_id='2024_01_MIA_BUF',season=2024,week=1,game_date='2024-09-07'))
 c=next(r for r in build_contexts(p,s)['rows']if r['period']==202401)
 assert c['features']['pressure3_own_allowed_known_games']==0 and c['features']['pressure3_own_allowed_rate']is None


def test_both_consumer_versions_order_and_train_only_unknown():
 from backend.app.product_services.team_opportunity_models import prepare_model_inputs,PRESSURE_VERSION as TV
 from backend.app.product_services.feature_block_model_inputs import prepare_player_inputs,PRESSURE_VERSION as PV
 from backend.app.product_services.offensive_volume_features import FEATURES as PF,VERSION as PVER
 p,s=fixture();contexts=build_contexts(p,s)
 r=dict(game_id='2023_04_MIA_BUF',team='BUF',period=202304,legacy_feature_ready=True,context_periods=[],legacy_periods=[],history_periods=[202301,202302,202303],features=dict.fromkeys(FEATURES,1),labels=dict(pass_attempts=20,rush_attempts=10))
 m=dict(version=VERSION,feature_columns=list(FEATURES),target_columns=['pass_attempts','rush_attempts'],rows=[r],before_period=202606,provenance={});m['matrix_sha256']=digest({k:v for k,v in m.items()if k!='provenance'})
 base,_=admit_matrix(m,grain='team',parent_ref={});before=deepcopy(base);extended=append_pressure_context(base,contexts,grain='team',parent_refs={})
 prepared=prepare_model_inputs(extended,train_before=202401,validation_before=202501)
 assert prepared['matrix_provenance']['pressure_adapter']==extended['pressure_adapter']
 assert base==before and prepared['version']==TV and prepared['preprocessing']['columns']==list(TEAM_COLUMNS)
 r=deepcopy(r);r.update(player_master_id='00000000-0000-0000-0000-000000000001',position='QB',current_inference=False,features=dict.fromkeys([*PF,*(f'team_{k}'for k in FEATURES)],3),labels=dict(pass_attempts=20,rush_attempts=10,targets=0))
 m.update(version=PVER,feature_columns=list(r['features']),target_columns=['pass_attempts','rush_attempts','targets'],rows=[r],usage='test');m['matrix_sha256']=digest({k:v for k,v in m.items()if k not in{'provenance','matrix_sha256'}})
 base,_=admit_matrix(m,grain='player',parent_ref={});extended=append_pressure_context(base,contexts,grain='player',parent_refs={})
 prepared=prepare_player_inputs(extended,train_before=202401,validation_before=202501)
 assert prepared['provenance']['pressure_adapter']==extended['pressure_adapter']
 assert prepared['version']==PV and prepared['preprocessing']['columns']==list(PLAYER_COLUMNS)


def test_bye_is_not_missing_game_and_schedule_gap_is_not_skipped():
 p,s=fixture();s[2].update(game_id='2023_04_MIA_BUF',week=4);s[3].update(game_id='2023_05_MIA_BUF',week=5)
 for r in p['game_rows']:
  if r['week']>=3:r.update(game_id=f"2023_{r['week']+1:02d}_MIA_BUF",week=r['week']+1)
 g=next(r for r in build_contexts(p,s)['rows']if r['team']=='BUF'and r['period']==202305)
 assert g['axes']['own_allowed']['contributing_periods']==[202301,202302,202304]
 assert g['features']['pressure3_own_allowed_known_games']==3
 p['game_rows']=[r for r in p['game_rows']if not(r['offense']=='BUF'and r['week']==2)]
 g=next(r for r in build_contexts(p,s)['rows']if r['team']=='BUF'and r['period']==202305)
 assert g['features']['pressure3_own_allowed_rate']is None
