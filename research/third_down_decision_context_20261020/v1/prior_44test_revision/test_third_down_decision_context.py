from copy import deepcopy
import pytest
from backend.app.product_services.third_down_decision_context import build_third_down_decisions,_failure,load_reviewed_decision_boundary
from backend.app.product_services.drive_scoring_range import build_drive_scoring_range
from backend.app.tests.product.test_drive_scoring_range import inputs,raw,GID


def fixture():
 x=list(inputs());x[0][0].update(down=3,third_down_failed=1,third_down_converted=0,first_down_pass=0,first_down_rush=0,first_down_penalty=0,pass_touchdown=0,rush_touchdown=0)
 x[0][1]['third_down_failed']=0
 return x[0],build_drive_scoring_range(*x)


def run(records=None,boundary=None):
 if records is None:records,boundary=fixture()
 return build_third_down_decisions(records,boundary)['game_rows'][0]


def test_field_goal_anchor_unit_not_drive_count_and_choice_denominator():
 r=run();assert r['third_failure_anchors'][0]['outcome_category']=='field_goal_attempt'
 assert r['metrics']['all_anchor_categorical_frequencies']=={'field_goal_attempt':1}
 assert r['metrics']['exact_choice_only_frequencies']['field_goal_attempt']==1

@pytest.mark.parametrize('kind',['punt','run','pass'])
def test_next_physical_fourth_or_punt(kind):
 rs,b=fixture();rs[1]=raw(2,kind,down=4,third_down_failed=0)
 a=run(rs,b)['third_failure_anchors'][0]
 assert a['outcome_category']==('punt_attempt' if kind=='punt' else 'physical_fourth_down_attempt')


def test_provider_order_not_numeric_id_chronology():
 rs,b=fixture();rs[0]['play_id']=100;rs[0]['order_sequence']=1;b['game_rows'][0]['drives'][0]['source_first_play_id']=100
 assert run(rs,b)['third_failure_anchors'][0]['next_decision_play_id']==2

@pytest.mark.parametrize('field,value',[('no_play',1),('no_play',None),('two_point_attempt',1),('play_type_nfl','UNSPECIFIED'),('game_half','UNKNOWN')])
def test_uncertain_or_excluded_next_event_masks_full_not_zero(field,value):
 rs,b=fixture();rs[1][field]=value;r=run(rs,b)
 assert r['metrics']['all_anchor_categorical_frequencies'] is None
 assert r['metrics']['known_eligible_third_failure_anchors']==1


def test_quiet_timeout_only_skips_when_all_live_indicators_quiet():
 rs,b=fixture();r=raw(3);r.update(play_type='no_play',play_type_nfl='TIMEOUT',order_sequence=1.5,pass_attempt=0,qb_dropback=0,third_down_failed=0)
 rs.append(r);assert run(rs,b)['third_failure_anchors'][0]['outcome_category']=='field_goal_attempt'
 r['qb_scramble']=1;assert run(rs,b)['third_failure_anchors'][0]['outcome_category'] is None

@pytest.mark.parametrize('field,value',[('drive',2),('posteam','WAS'),('order_sequence',None),('game_half','Half2')])
def test_unknown_or_reset_prevents_stale_decision(field,value):
 rs,b=fixture();rs[1][field]=value
 assert run(rs,b)['third_failure_anchors'][0]['outcome_category'] is None


def test_each_failed_series_anchor_is_retained_in_same_original_drive():
 rs,b=fixture();rs[1]['order_sequence']=4;rs[1]['play_id']=4;b['game_rows'][0]['drives'][0]['source_last_play_id']=4
 rs.extend([raw(2,down=1,third_down_failed=0),raw(3,down=3,third_down_failed=1)])
 r=run(rs,b);assert len(r['third_failure_anchors'])==2
 assert r['metrics']['all_anchor_categorical_frequencies']=={'field_goal_attempt':.5,'observed_new_or_repeated_down':.5}
 assert r['metrics']['exact_choice_only_frequencies']['field_goal_attempt']==1

@pytest.mark.parametrize('field',['third_down_converted','first_down_pass','first_down_rush','first_down_penalty','pass_touchdown','rush_touchdown'])
def test_failed_converted_or_td_conflict_unknown_membership(field):
 rs,b=fixture();rs[0][field]=1;r=run(rs,b)
 assert not r['third_failure_anchors'] and r['metrics']['unknown_possible_anchor_rows']==1
 assert r['metrics']['all_anchor_denominator'] is None


def test_unknown_failed_flag_masks_but_explicit_nonfailure_does_not():
 rs,b=fixture();rs[0]['third_down_failed']=None
 assert run(rs,b)['metrics']['all_anchor_denominator'] is None
 rs[0]['third_down_failed']=0;assert run(rs,b)['metrics']['empty_anchor_cohort'] is True


def test_anchor_outside_parent_native_first_last_never_inherits_terminal():
 rs,b=fixture();b['game_rows'][0]['drives'][0]['source_first_play_id']=2
 assert run(rs,b)['third_failure_anchors'][0]['outcome_category'] is None


def test_verified_possession_and_clock_ends_remain_competing_outcomes():
 for kind,category in [('INTERCEPTION','typed_possession_end_before_next_decision'),('END_GAME','verified_clock_end_before_next_decision')]:
  rs,b=fixture();rs.pop();d=b['game_rows'][0]['drives'][0];d['source_last_play_id']=1;d['verified_terminal_class']=kind
  r=run(rs,b);assert r['third_failure_anchors'][0]['outcome_category']==category
  assert r['metrics']['exact_choice_only_frequencies'] is None
  d['verified_terminal_class']=None;assert run(rs,b)['third_failure_anchors'][0]['outcome_category'] is None


def test_penalty_new_series_retained_and_nonquiet_unknown_penalty_blocks():
 rs,b=fixture();rs[1].update(first_down_penalty=1,no_play=1)
 assert run(rs,b)['third_failure_anchors'][0]['outcome_category']=='explicit_penalty_new_series'
 rs[1]['first_down_penalty']=0;assert run(rs,b)['third_failure_anchors'][0]['outcome_category'] is None


def test_unbound_offense_not_fabricated_team_qualified_anchor():
 rs,b=fixture();rs[0]['posteam']=None;x=build_third_down_decisions(rs,b)
 assert not x['game_rows'][0]['third_failure_anchors']
 assert x['unknown_native_anchor_incidents'][0]['possible_offense_teams']==['SF','WAS']
 assert x['unbound_native_offense_sides']==[(GID,'WAS')]

@pytest.mark.parametrize('bad',['duplicate','period','version','serving'])
def test_scope_or_native_identity_conflicts_reject(bad):
 rs,b=fixture()
 if bad=='duplicate':rs.append(deepcopy(rs[0]))
 if bad=='period':rs[0]['week']=2
 if bad=='version':b['version']='other'
 if bad=='serving':b['pregame_serving_eligible']=True
 with pytest.raises(ValueError):run(rs,b)


def test_unmanaged_boundary_rejects_before_read():
 with pytest.raises(ValueError):load_reviewed_decision_boundary(dict(path='/tmp/not.json',sha256='a'*64,bytes=100),cutoff='2026-10-20T10:00:00Z')

@pytest.mark.parametrize('change',[None,'bytes','semantic','producer','future','serving','version'])
def test_boundary_reader_authenticates_bytes_semantics_current_producer_and_clocks(tmp_path,monkeypatch,change):
 import hashlib,json
 from pathlib import Path
 from backend.app.product_services import drive_scoring_range
 from backend.app.product_services.evaluation_record import digest
 monkeypatch.chdir(tmp_path);_,x=fixture()
 x['provenance']=dict(producer_code_sha256=hashlib.sha256(Path(drive_scoring_range.__file__).read_bytes()).hexdigest(),actual_publication_at='2026-10-19T01:00:00Z')
 if change=='semantic':x['game_rows'][0]['week']=2
 if change=='producer':x['provenance']['producer_code_sha256']='b'*64
 if change=='future':x['provenance']['actual_publication_at']='2026-10-21T00:00:00Z'
 if change=='serving':x['pregame_serving_eligible']=True
 if change=='version':x['version']='other'
 raw=json.dumps(x,sort_keys=True).encode();sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/drive_scoring_range')/(sha+'.json');p.parent.mkdir(parents=True);p.write_bytes(raw)
 ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
 if change=='bytes':p.write_bytes(raw+b' ')
 if change:
  with pytest.raises(ValueError):load_reviewed_decision_boundary(ref,cutoff='2026-10-20T09:00:00Z')
 else:assert load_reviewed_decision_boundary(ref,cutoff='2026-10-20T09:00:00Z')['semantic_sha256']==x['semantic_sha256']

@pytest.mark.parametrize('side,category',[('SF','explicit_penalty_new_series'),(None,None),('WAS',None)])
def test_material_first_down_penalty_on_named_timeout_never_skipped(side,category):
 rs,b=fixture();r=raw(3);r.update(play_type='no_play',play_type_nfl='TIMEOUT',order_sequence=1.5,posteam=side,pass_attempt=0,qb_dropback=0,third_down_failed=0,first_down_penalty=1)
 rs.append(r);a=run(rs,b)['third_failure_anchors'][0]
 assert a['outcome_category']==category and a['next_decision_play_id']==3

@pytest.mark.parametrize('flag',['pass_touchdown','rush_touchdown'])
def test_actual_projection_retains_offensive_TD_contradiction_source_fields(flag):
 from backend.app.product_services.third_down_decision_context import project_decision_source
 rs,b=fixture();rs[0][flag]='1.0'
 projected=[project_decision_source(r)for r in rs]
 assert projected[0][flag]=='1.0'
 r=run(projected,b);assert r['metrics']['unknown_possible_anchor_rows']==1 and not r['third_failure_anchors']
