from copy import deepcopy
import pytest
from backend.app.tests.product.test_defensive_event_distributions import build,play
from backend.app.product_services.defensive_opportunity_catalog import build_defensive_opportunities as _build,load_reviewed_defensive_events

def src(rows):
 x=build(rows);x.update(pregame_serving_eligible=False,forecast=None);x['_test_spikes']=[dict(game_id=r['game_id'],play_id=r['play_id'],qb_spike=r.get('qb_spike')) for r in rows];return x

def build_defensive_opportunities(x):return _build(x,spike_records=x['_test_spikes'])

def defense(x):return next(r for r in x['game_rows'] if r['defense_team']=='MIA')

def test_physical_dropback_union_once_and_official_pass_channel_separate():
 x=build_defensive_opportunities(src([play(1),play(2,sack=1,pass_attempt=0),play(3,qb_spike=1),play(4,play_type='run',pass_attempt=0,rush_attempt=1,qb_scramble=1)]))
 r=defense(x);assert r['metrics']['G23-M07']['exact_observed_opportunities']==3
 assert 'G23-M08' not in r['metrics']

def test_missing_outcome_does_not_erase_known_eligible_exposure():
 x=build_defensive_opportunities(src([play(1,interception=None)]))
 assert defense(x)['metrics']['G23-M07']['exact_observed_opportunities']==1

def test_no_opponent_offense_log_not_zero_opportunities():
 x=build_defensive_opportunities(src([play(1)]));r=next(r for r in x['game_rows'] if r['defense_team']=='BUF')
 assert r['metrics']['G23-M07']['exact_observed_opportunities'] is None

def test_all_rush_known_zero_pass_exposure_requires_actual_source_log():
 x=build_defensive_opportunities(src([play(1,play_type='run',pass_attempt=0,rush_attempt=1,qb_dropback=0,qb_scramble=0)]))
 assert defense(x)['metrics']['G23-M07']['exact_observed_opportunities']==0

def test_unknown_eligibility_not_zero_knownsample_preserved():
 x=src([play(1),play(2,pass_attempt=None,sack=None)]);r=defense(build_defensive_opportunities(x))
 assert r['metrics']['G23-M07']['exact_observed_opportunities'] is None
 assert r['metrics']['G23-M07']['known_eligible_exposures_lower_bound']==1

@pytest.mark.parametrize('kind',['duplicateevent','duplicateside','missing_side','native','counter','tristate','futureperiod','serving'])
def test_native_scope_budget_and_source_contract_guards(kind):
 x=src([play(1)])
 if kind=='duplicateevent':x['event_basis'].append(deepcopy(x['event_basis'][0]))
 if kind=='duplicateside':x['game_rows'].append(deepcopy(x['game_rows'][0]))
 if kind=='missing_side':x['game_rows']=x['game_rows'][1:]
 if kind=='native':x['game_rows'][0]['offense_team']='SEA'
 if kind=='counter':x['game_rows'][1]['metrics']['X06-M06']['known_exposure']+=1
 if kind=='tristate':x['event_basis'][0]['dropback']=1
 if kind=='futureperiod':x['before_period']=202601
 if kind=='serving':x['pregame_serving_eligible']=True
 with pytest.raises(ValueError):build_defensive_opportunities(x)

def test_unmanaged_reader_rejects_without_source_access():
 with pytest.raises(ValueError):load_reviewed_defensive_events(dict(path='/tmp/no.json',sha256='a'*64,bytes=10),None,cutoff='2026-10-20T09:00:00Z')

@pytest.mark.parametrize('change',[None,'bytes','semantic','producer','clock','event','compressed','source'])
def test_indexed_reader_binds_original_bytes_event_clocks_and_no_inflation(tmp_path,monkeypatch,change):
 from types import SimpleNamespace
 from pathlib import Path
 import json,hashlib
 from backend.app.product_services import defensive_event_distributions
 from backend.app.services import source_capture
 monkeypatch.chdir(tmp_path)
 x=src([play(1)]);v=x['provenance'];v.update(actual_publication_at='2026-10-19T05:00:00Z',producer_code_sha256=hashlib.sha256(Path(defensive_event_distributions.__file__).read_bytes()).hexdigest())
 b=b'opaque compressed bytes; do not inflate';h=hashlib.sha256(b).hexdigest();q=Path('artifacts/opportunity_events')/(h+'.json.gz');q.parent.mkdir(parents=True);q.write_bytes(b)
 snap=SimpleNamespace(byte_count=123,snapshot_id='source',content_sha256='a'*64,season=2026,week=6,source_system='nflreadpy',dataset='play_by_play',media_type='text/csv',source_uri='nflreadpy://pbp/2026',metadata_json=dict(contract_id='operational_opportunity_source_v1'),observed_at='2026-10-19T01:00:00Z',captured_at='2026-10-19T01:00:00Z',slate_lock_at='2026-10-19T03:00:00Z')
 v['source'].update(snapshot_id='source',content_sha256='a'*64)
 v['retrospective_read']=dict(original_evidence_boundary_at='2026-10-19T02:00:00Z',source_lock_at=snap.slate_lock_at,actual_read_at='2026-10-19T04:00:00Z',actual_derived_at='2026-10-19T04:00:00Z',parent_artifact_ref=dict(path=str(q.resolve()),artifact_sha256=h,compressed_bytes=len(b),source_snapshot_id='source',source_sha256='a'*64,event_receipt_sha256=v['event_receipt_sha256'],before_period=202606,decision_cutoff_at='2026-10-19T02:00:00Z',source_captured_at=snap.captured_at))
 if change=='semantic':x['game_rows'][0]['week']=4
 if change=='producer':v['producer_code_sha256']='b'*64
 if change=='clock':v['retrospective_read']['actual_read_at']='2026-10-19T02:00:00Z'
 if change=='event':v['retrospective_read']['parent_artifact_ref']['event_receipt_sha256']='b'*64
 if change=='compressed':q.write_bytes(b'changed')
 if change=='source':v['source']['snapshot_id']='different'
 raw=json.dumps(x,sort_keys=True).encode();h=hashlib.sha256(raw).hexdigest();p=Path('artifacts/defensive_event_distributions')/(h+'.json');p.parent.mkdir(parents=True);p.write_bytes(raw)
 ref=dict(path=str(p.resolve()),sha256=h,bytes=len(raw));called=[]
 monkeypatch.setattr(source_capture,'verify_snapshot_artifact',lambda s:called.append(s.snapshot_id))
 if change=='bytes':p.write_bytes(raw+b' ')
 if change:
  with pytest.raises(ValueError):load_reviewed_defensive_events(ref,snap,cutoff='2026-10-20T09:00:00Z')
 else:
  result=load_reviewed_defensive_events(ref,snap,cutoff='2026-10-20T09:00:00Z');assert result['event_basis']==x['event_basis'] and called==['source']

@pytest.mark.parametrize('spike,expected',[(None,None),(1,0),(0,1)])
def test_explicit_spike_eligibility_unknown_not_zero(spike,expected):
 x=src([play(1,qb_spike=spike)]);r=defense(build_defensive_opportunities(x))
 assert r['metrics']['G23-M07']['exact_observed_opportunities']==expected

def test_known_spike_sack_conflict_masks_exposure_not_arbitrary_precedence():
 x=src([play(1,sack=1,pass_attempt=0,qb_spike=1)])
 assert defense(build_defensive_opportunities(x))['metrics']['G23-M07']['exact_observed_opportunities'] is None

def test_source_exclusion_precedes_positive_spike_sack_flags():
 x=src([play(1),play(2,no_play=1,sack=1,pass_attempt=0,qb_spike=1)])
 assert defense(build_defensive_opportunities(x))['metrics']['G23-M07']['exact_observed_opportunities']==1

def test_missing_or_duplicate_raw_spike_gameplay_proof_rejects():
 x=src([play(1)])
 with pytest.raises(ValueError):_build(x,spike_records=[])
 with pytest.raises(ValueError):_build(x,spike_records=x['_test_spikes']*2)

def test_native_numeric_play_identity_normalizes_representation_never_order():
 x=src([play(1)]);x['_test_spikes'][0]['play_id']='1.0'
 assert defense(build_defensive_opportunities(x))['metrics']['G23-M07']['exact_observed_opportunities']==1

@pytest.mark.parametrize('raw,expected',[('0.0',1),('1.0',0),('',None),('1.5',None)])
def test_csv_flag_representation_is_parsed_without_zero_filling(raw,expected):
 x=src([play(1)]);x['_test_spikes'][0]['qb_spike']=raw
 assert defense(build_defensive_opportunities(x))['metrics']['G23-M07']['exact_observed_opportunities']==expected
