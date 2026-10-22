from copy import deepcopy
import pytest
from backend.app.product_services.weekly_effectiveness_catalog_features import build_weekly_effectiveness
P='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';Q='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';NOW='2026-10-20T03:00:00Z'
def row(**changes):
 r=dict(source_player_id='00-0031234',player_master_id=P,season=2025,week=1,team='LA',position='QB',source_id=1,ingest_run_id='raw-ingest',imported_at='2026-10-13T12:00:00',raw_row_json=dict(season_type='REG',season=2025,week=1,player_id='00-0031234',position='QB',attempts=20,completions=12,passing_yards=180,interceptions=1,passing_tds=2,carries=3,rushing_yards=-2,receptions=2,targets=4,receiving_yards=-1));r.update(changes);r['native_alias_evidence']=[dict(alias_id='native-alias',source_system='nflreadpy',source_key=r['source_player_id'],player_master_id=r['player_master_id'],created_at='2026-10-13T00:00:00Z')] if r['player_master_id'] else [];return r
def build(rows=None):return build_weekly_effectiveness(rows or [row()],before_period=202607,cutoff=NOW)
def test_same_row_official_ratios_signed_yards_native_QB_proof():
 x=build()['rows'][0];m=x['metrics']
 assert x['team']=='LAR' and x['QB_scope_source_proven']
 assert [m[k]['value'] for k in ('G04-M01','G04-M03','G04-M05','G04-M08','G04-M10')]==[.6,9,15,.05,.1]
 assert m['G07-M01']['value']==-2/3 and m['G09-M03']['value']==-.25 and m['G09-M04']['value']==-.5
def test_no_source_position_inference_from_positive_attempts_or_pooledzeros():
 x=row(position='WR');x['raw_row_json']['position']='WR'
 r=build([x])['rows'][0];assert not r['QB_scope_source_proven'] and not any(k.startswith('G04') for k in r['metrics'])
def test_native_position_conflict_masks_QB_only():
 x=row();x['raw_row_json']['position']='RB';r=build([x])['rows'][0]
 assert 'QB_role' in r['source_quality'] and 'G04-M01' not in r['metrics'] and r['metrics']['G07-M01']['value']==-2/3
def test_unknown_and_zero_exposures_not_zero_ratios():
 x=row();x['raw_row_json'].update(attempts=0,completions=0,interceptions=0,passing_tds=0,targets=None)
 m=build([x])['rows'][0]['metrics'];assert m['G04-M01']['value'] is None and m['G04-M01']['status']=='undefined_zero_exposure'
 assert m['G09-M01']['value'] is None and m['G09-M01']['denominator'] is None
def test_alias_field_conflicts_and_invalid_counts_unknown_not_clipped():
 x=row();x['raw_row_json'].update(passing_attempts=21,targets=-1)
 r=build([x])['rows'][0];assert r['metrics']['G04-M01']['denominator'] is None and r['metrics']['G09-M01']['value'] is None
 assert {'attempts','targets'}<=r['source_quality'].keys()
def test_impossible_counts_mask_only_affected_measurement():
 x=row();x['raw_row_json']['completions']=21;r=build([x])['rows'][0]
 assert r['metrics']['G04-M01']['value'] is None and r['metrics']['G04-M03']['value']==9
@pytest.mark.parametrize('change',[dict(week=7,season=2026),dict(imported_at='2026-10-21T00:00:00Z'),dict(ingest_run_id=None)])
def test_future_period_clock_or_missing_source_proof_rejected(change):
 with pytest.raises(ValueError):build([row(**change)])
def test_explicit_REG_phase_required_not_season_aggregate():
 x=row();x['raw_row_json']['season_type']='POST'
 with pytest.raises(ValueError,match='REG'):build([x])
def test_malformed_native_quarantine_and_unresolved_identity_rows_retained():
 x=row(source_player_id='Display Name');y=row(source_id=2,source_player_id='00-0031235',player_master_id=None);y['raw_row_json']['player_id']='00-0031235'
 r=build([x,y]);assert len(r['quarantined_source_rows'])==1 and len(r['rows'])==1 and len(r['identity_review_requests'])==2
 assert r['rows'][0]['metrics']['G04-M01']['value']==.6
def test_cross_native_canonical_collision_withheld_not_arbitrarily_chosen():
 x=row();y=row(source_id=2,source_player_id='00-0031235');y['raw_row_json']['player_id']='00-0031235'
 r=build([x,y]);assert all(v['player_master_id'] is None for v in r['rows']) and len(r['identity_review_requests'])==2
 assert len({v['source_player_id'] for v in r['rows']})==2
def test_source_recapture_clock_and_roworder_stability_actual_stat_change_invalidates():
 x=row();y=row(source_id=2,source_player_id='00-0031235',player_master_id=Q);y['raw_row_json']['player_id']='00-0031235'
 a=build([x,y]);x['imported_at']='2026-10-14T12:00:00';assert build([y,x])['semantic_sha256']==a['semantic_sha256']
 x['raw_row_json']['passing_yards']=181;assert build([x,y])['semantic_sha256']!=a['semantic_sha256']

def test_retrospective_only_no_serving_registration():
 from backend.app.product_services.weekly_effectiveness_catalog_features import require_feature_use
 x=build();assert require_feature_use(x,purpose='offline_descriptive') is x
 with pytest.raises(ValueError,match='cannot'):require_feature_use(x,purpose='forecast')

@pytest.mark.parametrize('field,value',[('game_season',2024),('game_week',2),('gsis_id','00-0039999')])
def test_explicit_native_alias_scope_contradictions_not_ignored(field,value):
 x=row();x['raw_row_json'][field]=value
 with pytest.raises(ValueError):build([x])

@pytest.mark.parametrize('team',['UNKNOWN',None])
def test_unknown_team_never_invented_but_native_player_measure_retained(team):
 x=build([row(team=team)])['rows'][0];assert x['team'] is None and x['metrics']['G04-M01']['value']==.6

def test_conflicting_raw_team_scope_withheld_not_latest_team_transfer():
 r=row();r['raw_row_json']['team']='BUF';x=build([r])['rows'][0]
 assert x['team'] is None and x['source_quality']['team_scope']

def test_persist_queue_native_person_and_frozen_row_keys_no_reopen(tmp_path):
 import json,hashlib
 from backend.app.product_services.weekly_effectiveness_catalog_features import persist_weekly_identity_requests
 source_rows=[row(source_player_id=None),row(source_id=2,player_master_id=None)]
 raw=json.dumps(dict(source_kind='actual_database_raw_weekly_revision_extract',before_period=202607,rows=source_rows)).encode();sha=hashlib.sha256(raw).hexdigest();path=tmp_path/(sha+'.json');path.write_bytes(raw)
 ref=dict(path=str(path),sha256=sha,bytes=len(raw))
 class DB:
  def __init__(self):self.rows={'nflreadpy-gsis:00-0031234':'resolved'}
  def execute(self,sql,params):
   assert 'DO NOTHING' in str(sql) and 'UPDATE' not in str(sql)
   self.rows.setdefault(params['key'],'open')
 db=DB();features=build(source_rows)
 result=persist_weekly_identity_requests(db,features,source_ref=ref,source_root=tmp_path)
 assert result['source_incidents']==result['distinct_queue_keys']==2
 assert db.rows['nflreadpy-gsis:00-0031234']=='resolved' and db.rows[f'weekly-extract:{sha}:0']=='open'
 assert persist_weekly_identity_requests(db,features,source_ref=ref,source_root=tmp_path)==result
 path.write_bytes(raw+b' ')
 with pytest.raises(ValueError,match='size'):persist_weekly_identity_requests(db,features,source_ref=ref,source_root=tmp_path)

def test_alias_conflict_queue_is_separate_from_resolved_person_key(tmp_path):
 import json,hashlib
 from backend.app.product_services.weekly_effectiveness_catalog_features import persist_weekly_identity_requests
 x=row();y=row(source_id=2,source_player_id='00-0031235');y['raw_row_json']['player_id']=y['source_player_id'];features=build([x,y])
 raw=json.dumps(dict(source_kind='actual_database_raw_weekly_revision_extract',before_period=202607,rows=[x,y])).encode();sha=hashlib.sha256(raw).hexdigest();p=tmp_path/(sha+'.json');p.write_bytes(raw)
 class DB:
  def execute(self,sql,params):assert params['key'].startswith('weekly-alias-conflict:') and params['candidates']==json.dumps([P])
 r=persist_weekly_identity_requests(DB(),features,source_ref=dict(path=str(p),sha256=sha,bytes=len(raw)),source_root=tmp_path)
 assert r['distinct_queue_keys']==2


def test_future_alias_or_unproven_attachment_rejected_conflict_unattached():
 x=row();x['native_alias_evidence'][0]['created_at']='2026-10-21T00:00:00Z'
 with pytest.raises(ValueError,match='alias'):build([x])
 x=row();x['native_alias_evidence']=[]
 with pytest.raises(ValueError,match='alias'):build([x])
 x=row();x['native_alias_evidence'].append(dict(x['native_alias_evidence'][0],alias_id='other',player_master_id=Q))
 with pytest.raises(ValueError,match='unique'):build([x])
 x['player_master_id']=None;assert build([x])['rows'][0]['player_master_id'] is None


def test_collision_implicates_native_keys_across_all_periods():
 x=row();y=row(source_id=2,source_player_id='00-0031235');y['raw_row_json']['player_id']=y['source_player_id']
 z=row(source_id=3,week=2);z['raw_row_json']['week']=2
 value=build([x,y,z]);assert all(r['player_master_id'] is None for r in value['rows'])
 assert len(value['identity_review_requests'])==3
