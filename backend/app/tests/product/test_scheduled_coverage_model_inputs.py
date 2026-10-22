from copy import deepcopy
import pytest
from backend.app.product_services.scheduled_coverage_model_inputs import build_coverage_contexts,append_coverage_context,TEAM_COLUMNS,PLAYER_COLUMNS
from backend.app.product_services.scheduled_pressure_model_inputs import build_contexts,append_pressure_context
from backend.app.tests.product.test_scheduled_pressure_model_inputs import fixture as pressure_fixture
from backend.app.product_services.model_input_admission import admit_matrix
from backend.app.product_services.team_opportunity_matrix import FEATURES,VERSION
from backend.app.product_services.offensive_volume_features import digest


def fixture():
 p,s=pressure_fixture();rows=[]
 for r in p['game_rows']:
  rows.append(dict(game_id=r['game_id'],team=r['defense'],classified_dropbacks=10,man_dropbacks=2,zone_dropbacks=3,mixed_dropbacks=4,other_dropbacks=1,unclassified_dropbacks=5,known_eligible_dropbacks=15,unknown_eligible_dropbacks=0,unknown_classified_membership=0,metrics={'G14-M04':{'value':.2},'G14-M05':{'value':.3}}))
 return [dict(version='participation_defense_catalog_v1',season=2023,pregame_serving_eligible=False,team_game_rows=rows)],s


def latest(context):return next(r for r in context['rows']if r['team']=='BUF'and r['period']==202304)


def test_classified_denominator_includes_mixed_other_preserves_unclassified():
 sources,s=fixture();g=latest(build_coverage_contexts(sources,s));f=g['features']
 assert f['opponent_coverage3_man_rate']==.2 and f['opponent_coverage3_zone_rate']==.3
 assert f['opponent_coverage3_classified_dropbacks']==30 and f['opponent_coverage3_unclassified_dropbacks']==15
 assert f['opponent_coverage3_mixed_dropbacks']==12 and f['opponent_coverage3_other_dropbacks']==3
 assert g['window']['category_totals']['man_dropbacks']==6 and g['window']['full_eligible_fraction_proven']is False
 assert g['window']['contributing_periods']==[202301,202302,202303]

@pytest.mark.parametrize('mode',['missing','unknown_class','unknown_eligible','zero_one','zero_all'])
def test_membership_exposure_and_zero_guards(mode):
 sources,s=fixture();rs=sources[0]['team_game_rows']
 if mode=='missing':sources[0]['team_game_rows']=[r for r in rs if not(r['team']=='MIA'and r['game_id']=='2023_02_MIA_BUF')]
 if mode=='unknown_class':rs[0]['unknown_classified_membership']=1;rs[0]['metrics']['G14-M04']['value']=None;rs[0]['metrics']['G14-M05']['value']=None
 if mode=='unknown_eligible':rs[0]['unknown_eligible_dropbacks']=1
 if mode.startswith('zero'):
  for r in(rs if mode=='zero_all'else rs[:1]):
   for k in('classified_dropbacks','man_dropbacks','zone_dropbacks','mixed_dropbacks','other_dropbacks','unclassified_dropbacks','known_eligible_dropbacks'):r[k]=0
   for metric in r['metrics'].values():metric['value']=None
 g=latest(build_coverage_contexts(sources,s));f=g['features']
 if mode in('missing','unknown_class'):assert f['opponent_coverage3_man_rate']is None and f['opponent_coverage3_classified_dropbacks']is None and f['opponent_coverage3_unknown_games']==1
 elif mode=='zero_all':assert f['opponent_coverage3_classified_dropbacks']==0 and f['opponent_coverage3_man_rate']is None
 else:assert f['opponent_coverage3_man_rate']==.2
 if mode=='unknown_eligible':assert g['window']['full_eligible_fraction_proven']is False

@pytest.mark.parametrize('mode',['partition','negative','metric','duplicate','side'])
def test_native_counter_contracts(mode):
 sources,s=fixture();r=sources[0]['team_game_rows'][0]
 if mode=='partition':r['mixed_dropbacks']=0
 if mode=='negative':r['zone_dropbacks']=-1
 if mode=='metric':r['metrics']['G14-M04']['value']=.4
 if mode=='duplicate':sources[0]['team_game_rows'].append(r)
 if mode=='side':r['team']='NYJ'
 with pytest.raises(ValueError):build_coverage_contexts(sources,s)


def test_no_cross_year_or_absent_year_source():
 sources,s=fixture();s.append(dict(s[-1],game_id='2026_01_MIA_BUF',season=2026,week=1,game_date='2026-09-07'))
 g=next(r for r in build_coverage_contexts(sources,s)['rows']if r['period']==202601)
 assert g['features']['opponent_coverage3_man_rate']is None and g['features']['opponent_coverage3_unknown_games']==3


def test_both_consumer_versions_preserve_existing_columns_labels():
 from backend.app.product_services.team_opportunity_models import prepare_model_inputs,COVERAGE_VERSION as TV
 from backend.app.product_services.feature_block_model_inputs import prepare_player_inputs,COVERAGE_VERSION as PV
 from backend.app.product_services.offensive_volume_features import FEATURES as PF,VERSION as PVER
 sources,s=fixture();coverage=build_coverage_contexts(sources,s);pressure=build_contexts(pressure_fixture()[0],s)
 r=dict(game_id='2023_04_MIA_BUF',team='BUF',period=202304,legacy_feature_ready=True,context_periods=[],history_periods=[202301,202302,202303],features=dict.fromkeys(FEATURES,1),labels=dict(pass_attempts=20,rush_attempts=10))
 m=dict(version=VERSION,feature_columns=list(FEATURES),target_columns=['pass_attempts','rush_attempts'],rows=[r],before_period=202606,provenance={});m['matrix_sha256']=digest({k:v for k,v in m.items()if k!='provenance'})
 baseline,_=admit_matrix(m,grain='team',parent_ref={});p=append_pressure_context(baseline,pressure,grain='team',parent_refs={});before=deepcopy(p);out=append_coverage_context(p,coverage,grain='team',parent_refs={});prepared=prepare_model_inputs(out,train_before=202401,validation_before=202501)
 assert p==before and prepared['version']==TV and prepared['preprocessing']['columns']==list(TEAM_COLUMNS)
 assert prepared['matrix_provenance']['coverage_adapter']==out['coverage_adapter']
 r=deepcopy(r);r.update(player_master_id='00000000-0000-0000-0000-000000000001',position='QB',current_inference=False,features=dict.fromkeys([*PF,*(f'team_{k}'for k in FEATURES)],3),labels=dict(pass_attempts=20,rush_attempts=10,targets=0))
 m.update(version=PVER,feature_columns=list(r['features']),target_columns=['pass_attempts','rush_attempts','targets'],rows=[r],usage='test');m['matrix_sha256']=digest({k:v for k,v in m.items()if k not in{'provenance','matrix_sha256'}})
 baseline,_=admit_matrix(m,grain='player',parent_ref={});p=append_pressure_context(baseline,pressure,grain='player',parent_refs={});out=append_coverage_context(p,coverage,grain='player',parent_refs={});prepared=prepare_player_inputs(out,train_before=202401,validation_before=202501)
 assert prepared['version']==PV and prepared['preprocessing']['columns']==list(PLAYER_COLUMNS)and prepared['provenance']['coverage_adapter']==out['coverage_adapter']
