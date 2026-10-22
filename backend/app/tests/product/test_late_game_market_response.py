from copy import deepcopy
import pytest
from backend.app.product_services.late_game_market_response import build_late_game_market_response,project_late_market_source
from backend.app.product_services.workload_market_contexts import MARKET_VERSION
from backend.app.tests.product.test_late_half_possession_context import fixture
from backend.app.tests.product.test_drive_scoring_range import raw
GID='2026_01_SF_WAS'


def sources():
 rs,b=fixture()
 for r in rs:r.update(qtr=4,game_half='Half2',half_seconds_remaining=200,posteam_score=14,defteam_score=7,score_differential=7)
 m=dict(version=MARKET_VERSION,before_period=b['before_period'],pregame_serving_eligible=False,rows=[dict(game_id=GID,season=2026,week=1,team='SF',team_spread_line=-3),dict(game_id=GID,season=2026,week=1,team='WAS',team_spread_line=3)])
 return [rs,b,m]


def run(x=None):return build_late_game_market_response(*(x or sources()))
def cell(out,drive=False,market='favorite',score='ahead'):
 return next(c for c in out['game_rows'][0]['drive_cells'if drive else'play_cells']if c['market_group']==market and c['score_state']==score)


def test_native_preplay_score_and_signed_market_context_physical_vs_drive_units():
 out=run();p=cell(out);d=cell(out,True)
 assert p['known_opportunities']==1 and p['dropbacks_fraction']==1
 assert d['known_possessions']==1 and d['FG_fraction']==1 and d['TD_fraction']==0
 assert out['drive_basis'][0]['entry_preplay_score_state']=='ahead'


def test_per_play_score_changes_while_original_drive_context_stays_firstentry():
 x=sources();x[0][1].update(posteam_score=14,defteam_score=17,score_differential=-3)
 out=run(x);assert cell(out,True)['FG_fraction']==1
 assert cell(out,True,score='behind')['known_possessions']==0
 assert out['drive_basis'][0]['entry_preplay_score_state']=='ahead'

@pytest.mark.parametrize('clock,expected',[(0,1),(300,1),(301,0)])
def test_declared_five_minute_window_not_parent_two_minute(clock,expected):
 x=sources()
 for r in x[0]:r['half_seconds_remaining']=clock
 out=run(x);assert cell(out)['known_opportunities']==expected and cell(out,True)['known_possessions']==expected

@pytest.mark.parametrize('qtr,half',[(2,'Half1'),(5,'Overtime'),(4,'UNKNOWN')])
def test_q4_recognized_Half2_only(qtr,half):
 x=sources()
 for r in x[0]:r.update(qtr=qtr,game_half=half)
 out=run(x);assert cell(out)['known_opportunities']==0
 if qtr==4:assert cell(out)['unknown_membership']>0

@pytest.mark.parametrize('field,value',[('posteam_score',None),('defteam_score',None),('score_differential',0),('defteam','SF')])
def test_missing_or_conflicting_preplay_score_side_masks_all_compatible_scorecells(field,value):
 x=sources();x[0][0][field]=value;out=run(x)
 for state in('ahead','tied','behind'):assert cell(out,score=state)['unknown_membership']==1 and cell(out,score=state)['dropbacks_fraction']is None


def test_final_or_postplay_score_cannot_fill_missing_preplay_source_scores():
 x=sources();x[0][0].update(posteam_score=None,posteam_score_post=21,total_home_score=21,total_away_score=7)
 assert cell(run(x))['known_opportunities']==0


def test_unknown_first_entry_score_not_reassigned_to_later_known_FG_score():
 x=sources();x[0][0]['score_differential']=None;out=run(x)
 assert out['drive_basis'][0]['entry_preplay_score_state']is None
 assert all(c['known_possessions']==0 for c in out['game_rows'][0]['drive_cells'])
 assert cell(out,True)['unknown_membership']==1


def test_unknown_line_masks_all_possible_marketcells_not_discarded_completecase():
 x=sources();x[2]['rows'][0]['team_spread_line']=None;out=run(x)
 for group in('favorite','underdog','pickem'):assert cell(out,market=group)['unknown_membership']==1


def test_pickem_literalzero_not_unknown_or_favorite():
 x=sources();x[2]['rows'][0]['team_spread_line']=0;x[2]['rows'][1]['team_spread_line']=0
 assert cell(run(x),market='pickem')['dropbacks_fraction']==1


def test_kneel_is_official_rush_subtype_not_extra_physical_opportunity():
 x=sources();x[0][0].update(play_type='qb_kneel',play_type_nfl='RUSH',pass_attempt=0,rush_attempt=1,qb_dropback=0,qb_scramble=0,qb_kneel=1)
 c=cell(run(x));assert c['known_opportunities']==c['rushes']==c['kneels']==1 and c['kneel_fraction']==1


def test_scramble_and_sack_each_single_dropback_no_union_doublecount():
 for mode in('sack','scramble'):
  x=sources();x[0][0].update(sack=int(mode=='sack'),rush_attempt=int(mode=='scramble'),qb_scramble=int(mode=='scramble'),qb_dropback=1,pass_attempt=int(mode=='sack'))
  if mode=='scramble':x[0][0].update(play_type='run',play_type_nfl='RUSH')
  c=cell(run(x));assert c['known_opportunities']==1 and c['dropbacks']==1 and c['rushes']==0


def test_conflicting_official_pass_rush_flags_preserve_unknown_exposure():
 x=sources();x[0][0].update(rush_attempt=1,qb_scramble=0,qb_dropback=1)
 c=cell(run(x));assert c['known_opportunities']==0 and c['unknown_membership']==1 and c['dropbacks_fraction']is None


def test_drive_half_barrier_never_imports_earlier_half_paths_into_lateq4():
 x=sources();x[0][1].update(qtr=2,game_half='Half1',yardline_100=4,pass_touchdown=1)
 out=run(x);d=out['drive_basis'][0];assert d['live_FG_attempt']is None and d['offensive_TD']is None and d['continuity_barrier_play_ids']==[2]


def test_unassigned_original_drive_candidate_masks_drivecohort_while_physical_counts_stay_observed():
 x=sources();x[0][0]['drive']=None;out=run(x)
 assert cell(out)['known_opportunities']==1
 assert out['unassigned_drive_incidents']and cell(out,True)['unknown_membership']>0


def test_native_order_not_numeric_identity_freezes_context():
 x=sources();x[0][0]['play_id']=100;x[1]['game_rows'][0]['drives'][0]['source_first_play_id']=100
 x[0][1].update(posteam_score=7,defteam_score=14,score_differential=-7)
 assert run(x)['drive_basis'][0]['entry_preplay_score_state']=='ahead'


def test_known_zero_opportunities_empty_denominator_undefined():
 x=sources()
 for r in x[0]:r['half_seconds_remaining']=400
 c=cell(run(x));assert c['known_opportunities']==0 and c['dropbacks_fraction']is None


def test_actual_projection_retains_all_preplay_score_and_clock_fields():
 x=sources();r=project_late_market_source(x[0][0]);assert (r['posteam_score'],r['defteam_score'],r['score_differential'])==(14,7,7)
 assert r['half_seconds_remaining']==200 and r['qtr']==4

@pytest.mark.parametrize('bad',['duplicate','period','marketduplicate','version'])
def test_native_source_scope_rejects(bad):
 x=sources()
 if bad=='duplicate':x[0].append(deepcopy(x[0][0]))
 if bad=='period':x[0][0]['week']=2
 if bad=='marketduplicate':x[2]['rows'].append(deepcopy(x[2]['rows'][0]))
 if bad=='version':x[2]['version']='other'
 with pytest.raises(ValueError):run(x)


def test_unknown_dropback_type_preserves_known_physical_exposure():
 x=sources();x[0][0]['qb_dropback']=None
 c=cell(run(x));assert c['known_opportunities']==1 and c['unknown_type']==1 and c['dropbacks_fraction']is None


def test_bad_provider_order_masks_drive_sequence_without_blanket_downgrading_unordered_counts():
 x=sources();x[0][0]['order_sequence']=None;out=run(x)
 assert cell(out)['dropbacks_fraction']==1
 assert cell(out,True)['unknown_membership']>0


def test_missing_original_drive_cohort_not_zero_drive_exposures():
 x=sources();x[1]['game_rows'][0]['drives']=[];out=run(x)
 assert cell(out)['known_opportunities']==1
 assert cell(out,True)['unknown_membership']>0


def test_opposing_signed_teamspreads_not_independently_invented():
 x=sources();x[2]['rows'][1]['team_spread_line']=-3
 with pytest.raises(ValueError):run(x)
