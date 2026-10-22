from copy import deepcopy
import pytest
from backend.app.product_services.field_goal_decision_context import build_field_goal_decision_context,project_context_source,_time_band
from backend.app.product_services.third_down_decision_context import VERSION

GID='2026_01_SF_WAS'
def raw(play=1,**kwargs):
 r=dict(game_id=GID,play_id=play,season=2026,week=1,season_type='REG',posteam='SF',defteam='WAS',game_half='Half1',qtr=2,half_seconds_remaining=100,yardline_100=30,posteam_score=7,defteam_score=0,score_differential=7)
 return dict(r,**kwargs)
def parent(anchors=None,possible=None):
 return dict(version=VERSION,candidate_id='X05-M08',pregame_serving_eligible=False,before_period=202606,game_rows=[dict(native_game_id=GID,team='SF',season=2026,week=1,third_failure_anchors=anchors or [anchor()],unknown_possible_anchor_rows=possible or [])],unbound_native_offense_sides=[])
def anchor(play=1,outcome='field_goal_attempt'):
 return dict(native_game_id=GID,anchor_play_id=play,recognized_half='Half1',outcome_category=outcome,original_drive_id=1)
def cell(x,band='nominal_inside35',time='late_regulation_half_120',score='ahead',profile=False):
 return next(c for c in x['profiles' if profile else 'game_rows'][0]['cells'] if (c['nominal_field_site'],c['clock_band'],c['preanchor_score_state'])==(band,time,score))
def test_full_opportunity_denominator_keeps_competing_outcomes():
 p=parent([anchor(),anchor(2,'typed_possession_end_before_next_decision')]);x=build_field_goal_decision_context([raw(),raw(2)],p);c=cell(x)
 assert c['all_anchor_denominator']==2 and c['all_anchor_frequencies']['field_goal_attempt']==.5
 assert c['choice_only_sample_frequencies']['field_goal_attempt']==1
 assert sum(c['all_anchor_frequencies'].values())==1

def test_unknown_outcome_retains_known_samples_and_masks_full():
 x=build_field_goal_decision_context([raw(),raw(2)],parent([anchor(),anchor(2,None)]));c=cell(x)
 assert c['all_anchor_denominator']==2 and c['all_anchor_frequencies'] is None
 assert c['known_outcome_sample_frequencies']['field_goal_attempt']==1
 assert c['unknown_outcomes']==1

@pytest.mark.parametrize('field',['yardline_100','half_seconds_remaining','score_differential'])
def test_missing_context_only_masks_compatible_cells(field):
 x=build_field_goal_decision_context([raw(**{field:None})],parent())
 assert cell(x)['all_anchor_denominator'] is None
 assert cell(x,score='behind')['unknown_membership']==(1 if field=='score_differential' else 0)
 assert all(c['all_anchor_frequencies'] is None for c in x['game_rows'][0]['cells'])

def test_unknown_anchor_membership_and_unbound_sides_not_zero():
 p=parent(possible=[dict(native_game_id=GID,play_id=2)]);p['unbound_native_offense_sides']=[(GID,'WAS')]
 x=build_field_goal_decision_context([raw(),raw(2)],p)
 assert cell(x)['unknown_membership']==1
 was=next(r for r in x['profiles'] if r['team']=='WAS')
 assert all(c['all_anchor_denominator'] is None for c in was['cells'])

def test_missing_raw_anchor_is_unknown_not_silently_dropped():
 c=cell(build_field_goal_decision_context([],parent()))
 assert c['unknown_membership']==1 and c['known_anchor_members']==0

def test_matched_range_contrast_and_empty_not_zero():
 x=build_field_goal_decision_context([raw(),raw(2,yardline_100=36)],parent([anchor(),anchor(2,'punt_attempt')]))
 contrast=x['game_rows'][0]['contrasts'][0]
 assert contrast['all_anchor_frequency_differences']['field_goal_attempt']==1
 assert contrast['all_anchor_frequency_differences']['punt_attempt']==-1
 assert cell(x,time='earlier_regulation_half')['empty_observed_cell'] is True
 assert cell(x,time='earlier_regulation_half')['all_anchor_frequencies'] is None

def test_anchor_context_not_later_decision_score_or_site():
 x=build_field_goal_decision_context([raw(),raw(99,yardline_100=90,posteam_score=0,defteam_score=14,score_differential=-14)],parent())
 assert cell(x)['known_anchor_members']==1 and cell(x,score='behind')['known_anchor_members']==0

@pytest.mark.parametrize('change',[dict(posteam_score=6),dict(defteam='SF'),dict(posteam_score=-1),dict(posteam_score=7.5)])
def test_preplay_score_requires_corroborated_nonnegative_integer_pair(change):
 assert cell(build_field_goal_decision_context([raw(**change)],parent()))['unknown_membership']==1

@pytest.mark.parametrize('qtr,half,seconds,expected',[(2,'Half1',120,'late_regulation_half_120'),(2,'Half1',121,'earlier_regulation_half'),(1,'Half1',100,None),(2,'Half1',901,None),(5,'Overtime',None,'overtime'),(2,'UNKNOWN',100,None)])
def test_clock_boundaries_and_no_ot_regulation_substitution(qtr,half,seconds,expected):
 assert _time_band(raw(qtr=qtr,game_half=half,half_seconds_remaining=seconds))==expected

def test_source_projection_preserves_null_versus_absent():
 r=project_context_source(dict(raw(),yardline_100='',unused=1));assert r['yardline_100'] is None and 'unused' not in r
 r=raw();del r['score_differential'];assert 'score_differential' not in project_context_source(r)

@pytest.mark.parametrize('bad',['duplicate','period','offense','half','parent','outcome'])
def test_native_binding_and_parent_contract_reject(bad):
 rs=[raw()];p=parent()
 if bad=='duplicate':rs.append(raw())
 if bad=='period':rs[0]['week']=2
 if bad=='offense':rs[0]['posteam']='WAS'
 if bad=='half':rs[0].update(game_half='Half2',qtr=4)
 if bad=='parent':p['pregame_serving_eligible']=True
 if bad=='outcome':p['game_rows'][0]['third_failure_anchors'][0]['outcome_category']='made_up'
 with pytest.raises(ValueError):build_field_goal_decision_context(rs,p)

def test_pool_counts_before_division_not_mean_ratios():
 p=parent();p['game_rows'].append(dict(native_game_id='2026_02_SF_WAS',team='SF',season=2026,week=2,third_failure_anchors=[dict(anchor(i),native_game_id='2026_02_SF_WAS') for i in (2,3,4)],unknown_possible_anchor_rows=[]))
 for a in p['game_rows'][1]['third_failure_anchors']:a['outcome_category']='punt_attempt'
 rs=[raw()]+[dict(raw(i),game_id='2026_02_SF_WAS',week=2) for i in (2,3,4)]
 c=cell(build_field_goal_decision_context(rs,p),profile=True)
 assert c['all_anchor_frequencies']['field_goal_attempt']==.25

@pytest.mark.parametrize('change',[None,'bytes','semantic','producer','future','serving'])
def test_reader_binds_managed_source_semantics_producer_and_publication(tmp_path,monkeypatch,change):
 import hashlib,json
 from pathlib import Path
 from backend.app.product_services import third_down_decision_context
 from backend.app.product_services.field_goal_decision_context import load_reviewed_third_failure_context
 from backend.app.product_services.evaluation_record import digest
 monkeypatch.chdir(tmp_path);x=parent();x.update(team_profiles=[],unknown_native_anchor_incidents=[],definitions={},forecast=None)
 x['semantic_sha256']=digest({k:x[k] for k in ('version','candidate_id','before_period','game_rows','team_profiles','unknown_native_anchor_incidents','unbound_native_offense_sides','definitions')})
 x['provenance']=dict(producer_code_sha256=hashlib.sha256(Path(third_down_decision_context.__file__).read_bytes()).hexdigest(),actual_publication_at='2026-10-19T00:00:00Z')
 if change=='semantic':x['game_rows'][0]['week']=2
 if change=='producer':x['provenance']['producer_code_sha256']='b'*64
 if change=='future':x['provenance']['actual_publication_at']='2026-10-21T00:00:00Z'
 if change=='serving':x['pregame_serving_eligible']=True
 b=json.dumps(x).encode();sha=hashlib.sha256(b).hexdigest();p=Path('artifacts/third_down_decision_context')/(sha+'.json');p.parent.mkdir(parents=True);p.write_bytes(b)
 ref=dict(path=str(p.resolve()),bytes=len(b),sha256=sha)
 if change=='bytes':p.write_bytes(b+b' ')
 if change:
  with pytest.raises(ValueError):load_reviewed_third_failure_context(ref,cutoff='2026-10-20T00:00:00Z')
 else:assert load_reviewed_third_failure_context(ref,cutoff='2026-10-20T00:00:00Z')['semantic_sha256']==x['semantic_sha256']
