from copy import deepcopy
import pytest
from backend.app.product_services.observed_opening_qb_availability import build_observed_opening_qb_availability,load_reviewed_first_snap_component
from backend.app.product_services.center_sack_response import UNIT_VERSION
from backend.app.product_services.evaluation_record import digest
GID='2023_01_SF_WAS';QB='00-0000001';PID='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

def fixture():
 pos={f'00-{i:07d}':p for i,p in enumerate(['QB','C','G','G','T','T','WR','WR','TE','RB','FB'],1)}
 proof=dict(unique_quiet_native_GAME_START=True,native_beginning_play_id='100',first_physical_play_id='1',first_physical_native_order='9',no_earlier_possible_offense=True,earlier_possible_play_ids=[],eleven_unique_aligned_positions=True,original_first_snap_position_by_native_id=pos)
 u=dict(game_id=GID,team='SF',season=2023,week=1,game_date='2023-09-10',proof=proof,source_proven_center=False,unknown_reason='Unrelated center failure must not drive QB derivation')
 c=dict(version=UNIT_VERSION,season=2023,before_period=202607,units=[u],evidence_use='historical_postseason_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False)
 c['semantic_sha256']=digest(c)
 g=dict(game_id=GID,season=2023,week=1,game_type='REG',game_date='2023-09-10',home_team='WAS',away_team='SF',home_qb_id='00-0000099',away_qb_id=QB)
 aliases={QB:dict(status='unique_native_alias',player_master_id=PID,original_alias_evidence=[])}
 source=dict(game_id=GID,play_id='1',season=2023,week=1,native_phase=None,possession_team='SF',participant_scopes=dict(offense=dict(status='aligned_native_position_list',exact_eleven_native_proven=True,exact_eleven_positions_proven=True,position_by_native_id=deepcopy(pos))))
 return [c],[g],aliases,[source]

def run(args=None):return build_observed_opening_qb_availability(*(args or fixture()))
def row(x):return next(r for r in x['game_rows']if r['team']=='SF')

def test_actual_opening_participation_and_reported_native_starter_corroborate():
 x=run();r=row(x)
 assert r['observed_opening_available']is True and r['canonical_opening_QB_id']==PID
 assert r['native_observed_opening_presence']is True and r['source_opening_QB_GSIS']==QB
 assert r['pregame_confirmed_available']is None and r['health_status']is None and r['upcoming_starting_role_confirmed']is None
 assert x['model_consumed']is False
 assert next(r for r in x['game_rows']if r['team']=='WAS')['opening_status']=='unknown'

@pytest.mark.parametrize('field,value',[('unique_quiet_native_GAME_START',False),('no_earlier_possible_offense',False),('earlier_possible_play_ids',['2']),('first_physical_native_order',None),('first_physical_native_order','nan'),('first_physical_play_id',None),('first_physical_play_id','100'),('eleven_unique_aligned_positions',False)])
def test_incomplete_beginning_or_possible_prior_snap_never_available_false(field,value):
 c,g,a,p=fixture();c[0]['units'][0]['proof'][field]=value;r=row(run((c,g,a,p)))
 assert r['observed_opening_available']is None and r['opening_status']=='unknown'

@pytest.mark.parametrize('kind',['missingposition','unknownposition','nonstringposition','extraQB','noQB','invalidnative'])
def test_exact11_all_known_roles_and_sole_QB_required(kind):
 c,g,a,p=fixture();pos=c[0]['units'][0]['proof']['original_first_snap_position_by_native_id']
 if kind=='missingposition':pos.pop('00-0000011')
 if kind=='unknownposition':pos['00-0000011']=None
 if kind=='nonstringposition':pos['00-0000011']={}
 if kind=='extraQB':pos['00-0000011']='QB'
 if kind=='noQB':pos[QB]='RB'
 if kind=='invalidnative':pos['wrong']=pos.pop('00-0000011')
 assert row(run((c,g,a,p)))['observed_opening_available']is None

@pytest.mark.parametrize('reported',[None,'NotGSIS','00-0000002'])
def test_scheduled_name_or_conflicting_native_starter_does_not_prove_opening_QB(reported):
 c,g,a,p=fixture();g[0]['away_qb_id']=reported
 assert row(run((c,g,a,p)))['observed_opening_available']is None

def test_unknown_global_identity_keeps_native_presence_and_withholds_canonical():
 c,g,a,p=fixture();a[QB]['status']='unresolved_native_key';a[QB]['player_master_id']=None
 x=run((c,g,a,p));r=row(x)
 assert r['native_observed_opening_presence']is True and r['observed_opening_available']is None
 assert x['affected_identity_native_ids']==[QB]

def test_all_edge_conflict_from_outside_selected_actor_blocks_QB_UUID():
 c,g,a,p=fixture();other='00-0000098';a[other]=dict(status='canonical_native_conflict',player_master_id=None,original_alias_evidence=[dict(player_master_id=PID),dict(player_master_id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb')])
 x=run((c,g,a,p));assert row(x)['observed_opening_available']is None and QB in x['global_identity_withheld_native_ids']

def test_missing_first_snap_side_retains_scheduled_slot_unknown():
 c,g,a,p=fixture();c[0]['units']=[];x=run((c,g,a,p))
 assert len(x['game_rows'])==2 and all(r['observed_opening_available']is None for r in x['game_rows'])

@pytest.mark.parametrize('bad',['duplicateunit','duplicategame','nativeperiod','date','sourceextra','version'])
def test_native_game_period_pair_and_component_scope_guards(bad):
 c,g,a,p=fixture()
 if bad=='duplicateunit':c[0]['units'].append(deepcopy(c[0]['units'][0]))
 if bad=='duplicategame':g.append(deepcopy(g[0]))
 if bad=='nativeperiod':g[0]['week']=2
 if bad=='date':g[0]['game_date']='2023-09-11'
 if bad=='sourceextra':c[0]['units'][0]['game_id']='2023_02_SF_WAS'
 if bad=='version':c[0]['version']='other'
 with pytest.raises(ValueError):run((c,g,a,p))

@pytest.mark.parametrize('change',[None,'bytes','semantic','producer','future'])
def test_component_reader_bound_to_original_proof_helpers_and_publication(tmp_path,monkeypatch,change):
 import hashlib,json
 from pathlib import Path
 from backend.app.product_services import center_sack_response,offensive_line_participation,participation_source_components
 monkeypatch.chdir(tmp_path);c=fixture()[0][0];c['provenance']=dict(actual_publication_at='2026-10-20T01:00:00Z',**{k:hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()for k,m in(('producer_code_sha256',center_sack_response),('firstsnap_helper_sha256',offensive_line_participation),('source_adapter_sha256',participation_source_components))})
 if change=='semantic':c['units'][0]['proof']['no_earlier_possible_offense']=False
 if change=='producer':c['provenance']['producer_code_sha256']='b'*64
 if change=='future':c['provenance']['actual_publication_at']='2026-10-21T00:00:00Z'
 b=json.dumps(c).encode();sha=hashlib.sha256(b).hexdigest();p=Path('artifacts/center_sack_response')/(sha+'.json');p.parent.mkdir(parents=True);p.write_bytes(b);ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(b))
 if change=='bytes':p.write_bytes(b+b' ')
 if change:
  with pytest.raises(ValueError):load_reviewed_first_snap_component(ref,cutoff='2026-10-20T12:00:00Z')
 else:assert load_reviewed_first_snap_component(ref,cutoff='2026-10-20T12:00:00Z')['semantic_sha256']==c['semantic_sha256']

@pytest.mark.parametrize('change',['missing','team','phase','season','week','play','map','exact11','status'])
def test_independent_same_native_first_snap_participation_binding(change):
 c,g,a,p=fixture();r=p[0]
 if change=='missing':p=[]
 if change=='team':r['possession_team']='WAS'
 if change=='phase':r['native_phase']='POST'
 if change=='season':r['season']=2024
 if change=='week':r['week']=2
 if change=='play':r['play_id']='2'
 if change=='map':r['participant_scopes']['offense']['position_by_native_id'][QB]='RB'
 if change=='exact11':r['participant_scopes']['offense']['exact_eleven_positions_proven']=False
 if change=='status':r['participant_scopes']['offense']['status']='conflicting_cross_side_native_identity'
 assert row(run((c,g,a,p)))['observed_opening_available']is None

def test_duplicate_participation_key_rejected_instead_of_selecting_row():
 c,g,a,p=fixture();p.append(deepcopy(p[0]))
 with pytest.raises(ValueError):run((c,g,a,p))

@pytest.mark.parametrize('phase',[None,'REG'])
def test_explicit_REG_or_absent_participation_phase_corroborated_by_same_REG_first_snap(phase):
 c,g,a,p=fixture();p[0]['native_phase']=phase
 assert row(run((c,g,a,p)))['observed_opening_available']is True
