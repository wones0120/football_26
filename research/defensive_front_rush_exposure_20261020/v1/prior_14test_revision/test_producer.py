from copy import deepcopy
import pytest
from backend.app.product_services.defensive_front_rush_exposure import build_defensive_front_rush_exposure
from backend.app.product_services.participation_source_components import normalize_participation_rows
from backend.app.tests.product.test_fumble_event_components import play
G='2023_01_BUF_MIA'
IDS=[f'00-{i:07d}'for i in range(1,12)]
POSITIONS=['DE','DT','NT','OLB','ILB','MLB','CB','CB','FS','SS','S']

def rush(n=1,**kw):
    return play(n,game_id=G,season=2023,week=1,play_type='run',play_type_nfl='RUSH',pass_attempt=0,rush_attempt=1,qb_kneel=0,run_location='left',run_gap='tackle',rushing_yards=4,epa=.2)|kw

def source(n=1,**kw):
    return dict(nflverse_game_id=G,play_id=n,possession_team='BUF',defense_players=';'.join(IDS),defense_positions=';'.join(POSITIONS),n_defense=11)|kw

def build(records,sources=None):
    block=normalize_participation_rows(sources if sources is not None else[source()],season=2023)
    return build_defensive_front_rush_exposure(block,records,before_period=202319)

def profile(out):return next(r for r in out['profiles']if r['offense']=='BUF')
def left(out):return next(c for c in profile(out)['cells']if c['direction']=='left')

def test_exact11_native_personnel_mapping_direction_signed_units():
    out=build([rush(rushing_yards=-4,epa=-.7)])
    cell=left(out)
    assert cell['personnel_counts']==dict(DL=3,LB=3,DB=5,OTHER=0)
    assert cell['exact_exposure_count']==1
    assert cell['outcomes']['rushing_yards']['exact_sum']==-4
    assert cell['outcomes']['epa']['exact_mean']==-.7
    assert out['event_basis'][0]['original_run_gap']=='tackle'
    assert out['pregame_serving_eligible']is False and out['forecast']is None

def test_known_zero_cell_sum_defined_mean_undefined_not_unknown():
    right=next(c for c in profile(build([rush()]))['cells']if c['direction']=='right')
    assert right['exact_exposure_count']==0
    assert right['outcomes']['epa']['exact_sum']==0 and right['outcomes']['epa']['exact_mean']is None

def test_unknown_tuple_or_direction_masks_exact_known_cell_but_not_sample():
    for change,sources in[(dict(run_location=None),[source(),source(2)]),({},[source()]),({},[source(),source(2,n_defense=10)])]:
        out=build([rush(),rush(2,**change)],sources)
        assert profile(out)['unknown_condition_membership']==1
        c=left(out)
        assert c['exact_exposure_count']is None and c['known_exposure_lower_bound']==1
        assert c['outcomes']['epa']['exact_sum']is None and c['outcomes']['epa']['known_outcome_sum']==.2

def test_unknown_outcome_does_not_mask_exposure_or_other_outcome():
    c=left(build([rush(epa=None)]))
    assert c['exact_exposure_count']==1
    assert c['outcomes']['epa']['exact_sum']is None
    assert c['outcomes']['rushing_yards']['exact_sum']==4

def test_known_false_eligibility_does_not_inflate_unknown_cells():
    rows=[rush(),rush(2,no_play=1),rush(3,two_point_attempt=1),rush(4,qb_kneel=1),rush(5,rush_attempt=0)]
    out=build(rows,[source(n)for n in range(1,6)])
    assert profile(out)['known_eligible_rushes']==1 and profile(out)['unknown_condition_membership']==0

def test_scramble_is_one_official_rush_not_designed_call_claim():
    out=build([rush(qb_scramble=1,qb_dropback=1)])
    assert left(out)['exact_exposure_count']==1
    assert 'including scramble once'in out['definition']['exposure']

def test_unknown_eligibility_and_unknown_offense_mask_candidate_sides():
    for change in(dict(no_play=None),dict(qb_kneel=None),dict(posteam=None),dict(defteam=None)):
        out=build([rush(),rush(2,**change)],[source(),source(2)])
        assert left(out)['exact_exposure_count']is None

def test_known_nondefensive_position_retained_other_not_guessed_edge():
    p=POSITIONS.copy();p[0]='TE'
    c=left(build([rush()],[source(defense_positions=';'.join(p))]))
    assert c['personnel_counts']==dict(DL=2,LB=3,DB=5,OTHER=1)

def test_duplicate_native_person_or_cross_side_conflict_not_certified():
    for change in(dict(defense_players=';'.join(IDS[:-1]+[IDS[0]])),dict(offense_players=IDS[0],offense_positions='QB',n_offense=1)):
        out=build([rush()],[source(**change)])
        assert profile(out)['unknown_condition_membership']==1 and profile(out)['cells']==[]

def test_native_phase_possession_conflict_and_missing_scope_unknown():
    for change in(dict(possession_team='MIA'),dict(possession_team=None),dict(season_type='POST'),dict(defense_positions=None)):
        out=build([rush()],[source(**change)])
        assert profile(out)['unknown_condition_membership']==1

def test_target_post_period_excluded_duplicate_and_mismatched_keys_rejected():
    out=build([rush(),rush(2,game_id='2023_19_BUF_MIA',week=19,season_type='POST')])
    assert len(out['event_basis'])==1
    with pytest.raises(ValueError,match='Duplicate native PBP'):build([rush(),rush()])
    with pytest.raises(ValueError,match='game/season/week'):build([rush(week=2)])

def test_order_independent_semantics_event_basis_native_keys_preserved():
    out=build([rush(),rush(2,run_location='right')],[source(),source(2)])
    reverse=build([rush(2,run_location='right'),rush()],[source(2),source()])
    assert out['semantic_sha256']==reverse['semantic_sha256']
    assert {e['play_id']for e in out['event_basis']}=={'1','2'}
    assert sum(c['known_exposure_lower_bound']for c in profile(out)['cells'])==2


def test_unknown_side_candidates_not_counted_as_known_team_rushes():
    out=build([rush(posteam=None)])
    for row in out['team_game_rows']:
        assert row['known_eligible_rushes']==0 and row['unknown_offense_membership']==1
        assert row['known_classified_rushes']==0


def test_nonfinite_provider_outcomes_and_unknown_position_not_zero():
    c=left(build([rush(epa=float('nan'),rushing_yards=float('inf'))]))
    assert c['outcomes']['epa']['exact_sum']is None
    assert c['outcomes']['rushing_yards']['known_outcome_exposures']==0
    positions=POSITIONS.copy();positions[0]='UNKNOWN'
    out=build([rush()],[source(defense_positions=';'.join(positions))])
    assert profile(out)['unknown_condition_membership']==1 and profile(out)['cells']==[]
