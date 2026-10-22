from copy import deepcopy
from uuid import UUID
import pytest
from backend.app.product_services.model_input_admission import admit_matrix,cohort_manifest,MASKED_TEAM_COLUMNS,fold
from backend.app.product_services.team_opportunity_matrix import FEATURES,VERSION
from backend.app.product_services.offensive_volume_features import digest

def matrix():
 r=dict(game_id='2023_04_MIA_BUF',team='BUF',period=202304,history_periods=[202303],features=dict.fromkeys(FEATURES,1),labels=dict(pass_attempts=30,rush_attempts=20))
 m=dict(version=VERSION,feature_columns=list(FEATURES),target_columns=['pass_attempts','rush_attempts'],rows=[r],before_period=202606);m['matrix_sha256']=digest(m);return m

def test_explicit_masks_raw_preserved_order_bound_recipe():
 m=matrix();before=deepcopy(m);v,stats=admit_matrix(m,grain='team',parent_ref={'sha256':'original'});assert m==before and v['feature_columns']==list(FEATURES)
 assert len(MASKED_TEAM_COLUMNS)==18 and all(v['rows'][0]['features'][k]is None for k in MASKED_TEAM_COLUMNS);assert v['rows'][0]['features']['pass_mean3']==1;assert stats['games']==1
 assert v['matrix_sha256']!=m['matrix_sha256']and v['admission_policy']['new_catalog_adapters']is False

@pytest.mark.parametrize('change',['checksum','order','future','native','duplicate','periodtype'])
def test_time_identity_schema_guards(change):
 m=matrix()
 if change=='checksum':m['rows'][0]['features']['pass_mean3']=2
 else:
  m.pop('matrix_sha256')
  if change=='order':m['feature_columns']=list(reversed(m['feature_columns']))
  if change=='future':m['rows'][0]['history_periods']=[202304]
  if change=='native':m['rows'][0]['game_id']='2024_04_MIA_BUF'
  if change=='duplicate':m['rows']*=2
  if change=='periodtype':m['rows'][0]['period']=None
  m['matrix_sha256']=digest(m)
 with pytest.raises(ValueError):admit_matrix(m,grain='team',parent_ref={})

def test_known_zero_retained_unknown_excluded_per_head_and_fold():
 p=dict(target_columns=['pass_attempts','rush_attempts'],splits={'train':dict(keys=[dict(game_id='2023_04_MIA_BUF',period=202304)],x=[[1]],labels=[dict(pass_attempts=0,rush_attempts=None)])})
 v=cohort_manifest(p,grain='player')['train']['head_cohorts'];assert v['pass_attempts']['known_zero_rows']==1 and v['rush_attempts']['unknown_excluded']==1
 p['splits']['train']['keys'][0]['period']=202601
 with pytest.raises(ValueError):cohort_manifest(p,grain='player')

def test_test_and_inspected_diagnostic_separate():
 assert fold(202501)=='retrospective_test'and fold(202601)=='inspected_later_diagnostic'and fold(202606)=='forward_only'


def test_player_shared_view_masks_only_team_vintage_fields():
 from backend.app.product_services.offensive_volume_features import FEATURES as PF,VERSION as PV
 from backend.app.product_services.team_opportunity_matrix import FEATURES as TF
 m=matrix();m.pop('matrix_sha256');m['version']=PV;m['feature_columns']=[*PF,*(f'team_{k}'for k in TF)];m['target_columns']=['pass_attempts','rush_attempts','targets']
 m['rows'][0].update(player_master_id='00000000-0000-0000-0000-000000000001',features=dict.fromkeys(m['feature_columns'],1),labels={'pass_attempts':0,'rush_attempts':0,'targets':3})
 m['matrix_sha256']=digest(m);v,stats=admit_matrix(m,grain='player',parent_ref={})
 assert v['rows'][0]['features']['event_targets_mean3']==1
 assert all(v['rows'][0]['features']['team_'+k]is None for k in MASKED_TEAM_COLUMNS)
 assert m['rows'][0]['features']['team_game_total_line']==1
