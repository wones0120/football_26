from copy import deepcopy
import pytest
from backend.app.product_services.drive_scoring_range import build_drive_scoring_range
from backend.app.product_services.original_drive_field_context import VERSION
from backend.app.product_services.explosive_touchdown_features import VERSION as EV
from backend.app.product_services.fumble_event_components import VERSION as FV
from backend.app.product_services.scoreboard_result_features import VERSION as SV
GID='2026_01_SF_WAS'

def raw(pid,kind='pass',**changes):
 native={'pass':'PASS','field_goal':'FIELD_GOAL','run':'RUSH','punt':'PUNT','extra_point':'XP_KICK','quarter_end':'END_QUARTER'}[kind]
 r=dict(game_id=GID,play_id=pid,season=2026,week=1,season_type='REG',posteam='SF',defteam='WAS',drive=1,order_sequence=pid,
  game_half='Half1',qtr=1,half_seconds_remaining=800,game_seconds_remaining=2600,no_play=0,two_point_attempt=0,play_type=kind,play_type_nfl=native,
  pass_attempt=int(kind=='pass'),rush_attempt=int(kind=='run'),sack=0,qb_dropback=int(kind=='pass'),qb_scramble=0,qb_spike=0,qb_kneel=0,
  interception=0,fumble=0,fumble_lost=0,touchdown=0,return_touchdown=0,punt_attempt=int(kind=='punt'),punt_blocked=0,
  field_goal_attempt=int(kind=='field_goal'),field_goal_result='made' if kind=='field_goal' else None,extra_point_attempt=int(kind=='extra_point'),kickoff_attempt=0,
  fourth_down_failed=0,down=4 if kind in {'field_goal','punt'} else 1,yardline_100=35,drive_end_yard_line='WAS 35',drive_end_transition='FIELD_GOAL')
 return r|changes

def inputs():
 records=[raw(1,yardline_100=50),raw(2,'field_goal')]
 d=dict(original_drive_id=1,source_first_play_id=1,source_last_play_id=2,raw_end_transitions=['FIELD_GOAL'])
 o=dict(version=VERSION,pregame_serving_eligible=False,source_event_sha256='source',before_period=202606,game_rows=[dict(game_id=GID,team='SF',season=2026,week=1,unknown_original_drive_events=0,drives=[d])])
 s=dict(version=EV,before_period=202606,pregame_serving_eligible=False,source_event_sha256='source',game_rows=[dict(game_id=GID,team='SF',events=[dict(play_id=1,channels=[dict(channel='pass',official_eligibility=True,touchdown=False)])])])
 return records,o,s,dict(version=FV,before_period=202606,pregame_serving_eligible=False,fumble_ledger=[]),dict(version=SV,before_period=202606,pregame_serving_eligible=False,game_rows=[])

def run(*args):return build_drive_scoring_range(*(args or inputs()))['game_rows'][0]

def terminal(kind,**kwargs):
 x=list(inputs());x[1]['game_rows'][0]['drives'][0]['raw_end_transitions']=[kind]
 for r in x[0]:r['drive_end_transition']=kind
 x[0][-1].update(kwargs);return x

def test_nominal35_boundary_is_declared_source_predecision_site():
 r=run();assert r['metrics']['exact_observed_game_count']==1
 assert r['drives'][0]['terminal_predecision_site_yardline100']==35

@pytest.mark.parametrize('site,expected',[(0,1),(35,1),(36,0),(50,0)])
def test_boundary_fields(site,expected):
 x=list(inputs())
 for r in x[0]:r['drive_end_yard_line']='MIDFIELD' if site==50 else f'WAS {site}'
 x[0][-1]['yardline_100']=site
 assert run(*x)['metrics']['exact_observed_game_count']==expected

def test_return_landing_or_unknown_field_not_donated_as_kick_site():
 x=list(inputs());x[0][-1]['yardline_100']=45
 assert run(*x)['metrics']['exact_observed_game_count'] is None
 assert run(*x)['drives'][0]['classification_basis'].startswith('Source end field unknown')

def test_punt_and_downs_explicit_predecision_cohorts():
 x=terminal('PUNT',play_type='punt',play_type_nfl='PUNT',field_goal_attempt=0,field_goal_result=None,punt_attempt=1)
 assert run(*x)['metrics']['exact_observed_game_count']==1
 x=terminal('DOWNS',play_type='run',play_type_nfl='RUSH',field_goal_attempt=0,field_goal_result=None,rush_attempt=1,pass_attempt=0,sack=0,fourth_down_failed=1,down=4)
 assert run(*x)['metrics']['exact_observed_game_count']==1

def test_scoring_td_excluded_without_borrowing_try_as_terminal_decision_site():
 x=terminal('TOUCHDOWN');x[0][1]=raw(2,drive_end_transition='TOUCHDOWN',touchdown=1)
 x[0].append(raw(3,'extra_point',drive_end_transition='TOUCHDOWN',yardline_100=15));x[1]['game_rows'][0]['drives'][0]['source_last_play_id']=3
 x[2]['game_rows'][0]['events'].append(dict(play_id=2,channels=[dict(channel='pass',official_eligibility=True,touchdown=True)]))
 r=run(*x);assert r['metrics']['exact_observed_game_count']==0
 assert r['drives'][0]['source_last_play_id']==3 and r['drives'][0]['last_physical_snap_play_id']==2
 assert r['drives'][0]['terminal_predecision_site_yardline100'] is None

def test_td_label_without_offensive_scoring_proof_is_unknown_not_zero():
 x=terminal('TOUCHDOWN');assert run(*x)['metrics']['exact_observed_game_count'] is None

def test_original_official_interception_is_excluded_not_a_postreturn_site():
 x=terminal('INTERCEPTION',play_type='pass',play_type_nfl='INTERCEPTION',pass_attempt=1,field_goal_attempt=0,field_goal_result=None,interception=1)
 x[2]['game_rows'][0]['events'].append(dict(play_id=2,channels=[dict(channel='pass',official_eligibility=True,touchdown=False)]))
 assert run(*x)['metrics']['exact_observed_game_count']==0

def test_typed_original_offense_loss_required_for_fumble_exclusion():
 x=terminal('FUMBLE',play_type='pass',play_type_nfl='FUMBLE_RECOVERED_BY_OPPONENT',pass_attempt=1,field_goal_attempt=0,fumble=1,fumble_lost=1)
 assert run(*x)['metrics']['exact_observed_game_count'] is None
 x[3]['fumble_ledger']=[dict(game_id=GID,play_id=2,eligible=True,fumble_play=True,lost_from_fumbler_team=True,reported_fumblers=[dict(team='SF')])]
 assert run(*x)['metrics']['exact_observed_game_count']==0
 x[3]['fumble_ledger'][0]['reported_fumblers'][0]['team']='WAS'
 assert run(*x)['metrics']['exact_observed_game_count'] is None

def test_half_end_requires_native_control_zero_clock_and_half_binding():
 x=terminal('END_HALF');x[0][1]=raw(2,'quarter_end',posteam=None,qtr=2,half_seconds_remaining=0,drive_end_transition='END_HALF')
 assert run(*x)['metrics']['exact_observed_game_count']==0
 x[0][1]['half_seconds_remaining']=1
 assert run(*x)['metrics']['exact_observed_game_count'] is None

def test_final_game_requires_independent_completed_source_and_zero_clock():
 x=terminal('END_GAME')
 for r in x[0]:r['game_half']='Half2'
 x[0][1]=raw(2,'quarter_end',play_type_nfl='END_GAME',posteam='SF',qtr=4,game_half='Half2',game_seconds_remaining=0,drive_end_transition='END_GAME')
 assert run(*x)['metrics']['exact_observed_game_count'] is None
 x[4]['game_rows']=[dict(game_id=GID,exact_completed_score=[20,17])]
 assert run(*x)['metrics']['exact_observed_game_count']==0

@pytest.mark.parametrize('field',['qb_dropback','qb_scramble','qb_spike','qb_kneel'])
def test_positive_live_control_never_silently_skipped(field):
 x=terminal('END_HALF');x[0][1]=raw(2,'quarter_end',posteam=None,qtr=2,half_seconds_remaining=0,drive_end_transition='END_HALF',**{field:1})
 assert run(*x)['metrics']['exact_observed_game_count'] is None

@pytest.mark.parametrize('kind',['order','half','site','terminal','cohort'])
def test_unknown_source_parts_mask_full_count_known_lower_bound_retained(kind):
 x=list(inputs())
 if kind=='order':x[0][0]['order_sequence']=None
 if kind=='half':x[0][-1]['game_half']='Half2'
 if kind=='site':x[0][-1]['drive_end_yard_line']='unknown'
 if kind=='terminal':x[0][-1]['field_goal_result']=None
 if kind=='cohort':x[1]['game_rows'][0]['unknown_original_drive_events']=1
 assert run(*x)['metrics']['exact_observed_game_count'] is None

@pytest.mark.parametrize('kind',['eventpair','native','duplicate','metadata'])
def test_immutable_source_scope_contradictions_reject(kind):
 x=list(inputs())
 if kind=='eventpair':x[2]['source_event_sha256']='different'
 if kind=='native':x[0][0]['week']=2
 if kind=='duplicate':x[0].append(deepcopy(x[0][0]))
 if kind=='metadata':x[0][0]['drive_end_transition']='OTHER'
 with pytest.raises(ValueError):run(*x)

def test_unassigned_raw_possible_physical_cohort_masks_known_game_count():
 x=list(inputs());x[0].append(raw(3,drive=None))
 r=run(*x);assert r['metrics']['exact_observed_game_count'] is None
 assert r['metrics']['unassigned_source_physical_candidate_rows']==[3]
 assert r['metrics']['known_in_range_terminal_decisions_lower_bound']==1

@pytest.mark.parametrize('kind',['period','serving','version'])
def test_source_component_scope_use_guards(kind):
 x=list(inputs())
 if kind=='period':x[3]['before_period']=202607
 if kind=='serving':x[4]['pregame_serving_eligible']=True
 if kind=='version':x[2]['version']='not-reviewed'
 with pytest.raises(ValueError):run(*x)

def test_unmanaged_reviewed_component_rejects_before_read():
 from backend.app.product_services.drive_scoring_range import load_reviewed_range_component
 with pytest.raises(ValueError):load_reviewed_range_component(dict(path='/tmp/no.json',sha256='a'*64,bytes=12),'original_drive_field_context',cutoff='2026-10-20T09:00:00Z')

@pytest.mark.parametrize('change',[None,'bytes','semantic','producer','future','serving','version'])
def test_managed_component_reader_binds_source_bytes_producer_clocks(tmp_path,monkeypatch,change):
 from pathlib import Path
 import json,hashlib
 from backend.app.product_services import original_drive_field_context
 from backend.app.product_services.drive_scoring_range import load_reviewed_range_component
 from backend.app.product_services.evaluation_record import digest
 monkeypatch.chdir(tmp_path);x=inputs()[1];x['definitions']={};x['semantic_sha256']=digest({k:x[k] for k in ('version','before_period','game_rows','source_event_sha256','definitions')})
 x['provenance']=dict(producer_sha256=hashlib.sha256(Path(original_drive_field_context.__file__).read_bytes()).hexdigest(),actual_publication_at='2026-10-19T01:00:00Z')
 if change=='semantic':x['game_rows'][0]['week']=2
 if change=='producer':x['provenance']['producer_sha256']='b'*64
 if change=='future':x['provenance']['actual_publication_at']='2026-10-21T01:00:00Z'
 if change=='serving':x['pregame_serving_eligible']=True
 if change=='version':x['version']='changed'
 b=json.dumps(x,sort_keys=True).encode();h=hashlib.sha256(b).hexdigest();p=Path('artifacts/original_drive_field_context')/(h+'.json');p.parent.mkdir(parents=True);p.write_bytes(b)
 ref=dict(path=str(p.resolve()),sha256=h,bytes=len(b))
 if change=='bytes':p.write_bytes(b+b' ')
 if change:
  with pytest.raises(ValueError):load_reviewed_range_component(ref,'original_drive_field_context',cutoff='2026-10-20T09:00:00Z')
 else:assert load_reviewed_range_component(ref,'original_drive_field_context',cutoff='2026-10-20T09:00:00Z')['semantic_sha256']==x['semantic_sha256']

def test_intermediate_physical_half_conflict_masks_even_when_first_last_match():
 x=list(inputs());x[0][-1]['play_id']=4;x[0][-1]['order_sequence']=4;x[1]['game_rows'][0]['drives'][0]['source_last_play_id']=4
 x[0].append(raw(2,game_half='Half2'))
 assert run(*x)['metrics']['exact_observed_game_count'] is None
