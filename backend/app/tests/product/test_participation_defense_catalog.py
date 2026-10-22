from copy import deepcopy
import pytest
from backend.app.product_services.participation_defense_catalog import build_participation_defense_catalog
from backend.app.product_services.participation_source_components import normalize_participation_rows
from backend.app.tests.product.test_fumble_event_components import play
G='2023_01_BUF_MIA'

def pbp(number=1,**kw):return play(number,game_id=G,season=2023)|kw

def part(number=1,**kw):return dict(nflverse_game_id=G,play_id=number,possession_team='BUF',was_pressure=True,defense_man_zone_type='MAN_COVERAGE')|kw

def build(records,source):
    b=normalize_participation_rows(source,season=2023)
    return build_participation_defense_catalog(b,records,before_period=202319)

def defense(out):return next(r for r in out['team_game_rows']if r['team']=='MIA')

def test_direct_classified_denominator_mixed_other_and_unclassified_not_complements():
    records=[pbp(n)for n in range(1,6)]
    sources=[part(n,defense_man_zone_type=c)for n,c in enumerate(['MAN_COVERAGE','ZONE_COVERAGE','MIXED','OTHER',None],1)]
    r=defense(build(records,sources));a=r['metrics']['G14-M04'];b=r['metrics']['G14-M05']
    assert a['value']==b['value']==.25
    assert a['classified_denominator']==4 and a['full_eligible_denominator']==5
    assert a['unclassified_residual']==1 and a['mixed_classified_residual']==a['other_classified_residual']==1
    assert a['full_eligible_dropback_fraction']is None

def test_pressure_bool_is_measured_variant_not_falsely_completed_catalog_taxonomy():
    out=build([pbp(),pbp(2)],[part(),part(2,was_pressure=False)])
    p=defense(out)['native_pressure_variant']
    assert p['value']==.5 and p['catalog_value']is None
    assert 'pending_provider_event_taxonomy'in p['catalog_definition_status']
    assert out['pregame_serving_eligible']is False and out['forecast']is None

def test_physical_sack_and_scramble_once_spike_kneel_2pt_no_play_excluded():
    records=[pbp(sack=1),pbp(2,rush_attempt=1,qb_scramble=1),pbp(3,qb_spike=1),pbp(4,play_type='qb_kneel',play_type_nfl='RUSH',pass_attempt=0,rush_attempt=1,qb_kneel=1),pbp(5,two_point_attempt=1),pbp(6,no_play=1)]
    r=defense(build(records,[part(n)for n in range(1,7)]))
    assert r['known_eligible_dropbacks']==2 and r['source_pressure_count']==2

def test_false_native_pressure_on_sack_masks_outcome_without_overwriting_flag():
    out=build([pbp(sack=1)],[part(was_pressure=False)])
    r=defense(out)
    assert r['sack_pressure_conflicts']==1 and r['unknown_pressure_outcomes']==1
    assert r['native_pressure_variant']['value']is None
    assert out['event_basis'][0]['pressure_sack_conflict']is True
    assert out['event_basis'][0]['original_native_pressure']is False

def test_missing_participation_not_same_as_present_unclassified_label():
    r=defense(build([pbp(),pbp(2)],[part()]))
    assert r['metrics']['G14-M04']['known_classified_sample_fraction']==1
    assert r['metrics']['G14-M04']['value']is None and r['missing_participation_rows']==1
    r=defense(build([pbp(),pbp(2)],[part(),part(2,defense_man_zone_type=None)]))
    assert r['metrics']['G14-M04']['value']==1
    assert r['metrics']['G14-M04']['full_eligible_dropback_fraction']is None

def test_no_coverage_inference_from_detail_or_unsupported_label():
    r=defense(build([pbp(),pbp(2)],[part(),part(2,defense_man_zone_type='COVER_1',defense_coverage_type='COVER_1')]))
    assert r['metrics']['G14-M04']['value']is None
    assert r['man_dropbacks']==1 and r['unknown_classified_membership']==1

def test_unknown_nonspike_and_native_side_masks_classified_membership():
    for change in (dict(qb_spike=None),dict(defteam=None),dict(no_play=None)):
        r=defense(build([pbp(),pbp(2,**change)],[part(),part(2)]))
        assert r['unknown_eligible_dropbacks']==1
        assert r['metrics']['G14-M04']['value']is None

def test_source_phase_team_conflict_is_preserved_unknown_not_arbitrary_join():
    for change in (dict(season_type='POST'),dict(possession_team='MIA')):
        r=defense(build([pbp()],[part(**change)]))
        assert r['source_join_conflicts']==1 and r['metrics']['G14-M04']['value']is None

def test_post_and_target_period_excluded_all_passers_retained():
    records=[pbp(),pbp(2,game_id='2023_19_BUF_MIA',week=19,season_type='POST'),pbp(3,game_id='2023_18_BUF_MIA',week=18)]
    src=[part(),part(3,nflverse_game_id='2023_18_BUF_MIA')]
    out=build(records,src)
    assert len(out['event_basis'])==2
    assert {r['game_id']for r in out['event_basis']}=={G,'2023_18_BUF_MIA'}

def test_duplicate_native_keys_invalid_year_and_team_rejected():
    with pytest.raises(ValueError,match='Duplicate'):build([pbp(),pbp(play_id=1.0)],[part()])
    with pytest.raises(ValueError):build([pbp(season=2024)],[part()])
    with pytest.raises(ValueError):build([pbp(defteam='GB')],[part()])

def test_row_order_invariant_pooled_counts_and_undefined_empty_denominator():
    p=[pbp(),pbp(2)];s=[part(),part(2,defense_man_zone_type='ZONE_COVERAGE')]
    assert build(p,s)['semantic_sha256']==build(p[::-1],s[::-1])['semantic_sha256']
    out=build([pbp(pass_attempt=0,qb_dropback=0,rush_attempt=1,play_type='run',play_type_nfl='RUSH')],[part()])
    assert defense(out)['metrics']['G14-M04']['value']is None
