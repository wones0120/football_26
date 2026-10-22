from copy import deepcopy
import math
import pytest
from backend.app.product_services.scheduled_venue_displacement import (
    build_scheduled_venue_displacement as build, kickoff_utc, venue_for_game, great_circle_km)


def fixture():
    def venue(key, lat, lon, zone):
        return dict(registry_record_id=key+':v1', venue_id=key, source_system='pfr', source_venue_id=key,
            effective_from_season=2020, effective_to_season=None, latitude=lat, longitude=lon,
            timezone=zone, coordinate_source_uri='https://www.wikidata.org/wiki/Q1',
            source_evidence_uri='https://www.pro-football-reference.com/stadiums/'+key+'.htm')
    registry = dict(contract_id='nfl_venue_registry_v1', reviewed_at='2026-08-01',
        venues=[venue('WEST',34,-118,'America/Los_Angeles'),venue('EAST',40,-74,'America/New_York')],game_overrides=[])
    rows = [dict(game_id='2025_01_SF_LA',season='2025',week='1',game_type='REG',home_team='LA',away_team='SF',
        stadium_id='WEST',location='Home',gameday='2025-09-07',gametime='16:25'),
        dict(game_id='2025_03_SF_NYG',season='2025',week='3',game_type='REG',home_team='NYG',away_team='SF',
        stadium_id='EAST',location='Home',gameday='2025-09-21',gametime='13:00')]
    return rows, registry


def sf(result):
    return [r for r in result['game_rows'] if r['team']=='SF']


def test_declared_previous_scheduled_origin_crosses_bye_not_home_base():
    rows,reg=fixture(); value=sf(build(rows,reg))[1]
    assert value['prior_scheduled_game_id']=='2025_01_SF_LA'
    assert 3900<value['great_circle_km']<4000
    assert value['signed_destination_minus_origin_utc_offset_hours']==3
    assert sf(build(rows,reg))[0]['first_game_not_applicable']


def test_unknown_prior_is_not_skipped_to_earlier_known():
    rows,reg=fixture(); middle=dict(rows[0],game_id='2025_02_SF_LA',week='2',stadium_id=None,gameday='2025-09-14')
    rows.insert(1,middle); value=sf(build(rows,reg))[2]
    assert value['great_circle_km'] is None and value['prior_scheduled_game_id']==middle['game_id']
    assert build(rows,reg)['profiles'][-1]['total_displacement_km'] is None


def test_dst_change_at_identical_venue_does_not_fabricate_displacement():
    rows,reg=fixture(); rows[1].update(stadium_id='WEST',gameday='2025-11-09')
    value=sf(build(rows,reg))[1]
    assert value['great_circle_km']==0 and value['signed_destination_minus_origin_utc_offset_hours']==0


@pytest.mark.parametrize('day,time',[('2025-11-02','01:30'),('2025-03-09','02:30'),('2025-09-07','25:00'),(None,'13:00'),('2025-09-07','1:00')])
def test_ambiguous_missing_invalid_kickoff_unknown(day,time):
    assert kickoff_utc(day,time) is None


def test_eastern_time_converted_to_utc_and_sign_reversal():
    assert kickoff_utc('2025-09-21','13:00').isoformat()=='2025-09-21T17:00:00+00:00'
    rows,reg=fixture(); rows[0]['stadium_id']='EAST'; rows[1]['stadium_id']='WEST'
    assert sf(build(rows,reg))[1]['signed_destination_minus_origin_utc_offset_hours']==-3


@pytest.mark.parametrize('field,value',[('latitude',None),('longitude',float('nan')),('latitude',91),('timezone','Invalid/Zone'),('coordinate_source_uri',None)])
def test_unproven_registry_measurements_unknown(field,value):
    rows,reg=fixture(); reg['venues'][1][field]=value
    assert sf(build(rows,reg))[1]['great_circle_km'] is None


def test_overlapping_effective_registry_records_unknown():
    rows,reg=fixture(); reg['venues'].append(deepcopy(reg['venues'][0]))
    assert sf(build(rows,reg))[1]['great_circle_km'] is None


def test_expired_native_venue_unknown_no_name_fallback():
    rows,reg=fixture(); reg['venues'][0]['effective_to_season']=2024;rows[0]['stadium']='EAST'
    assert sf(build(rows,reg))[1]['great_circle_km'] is None


def test_neutral_requires_explicit_native_game_override():
    rows,reg=fixture(); rows[1]['location']='Neutral'
    assert sf(build(rows,reg))[1]['great_circle_km'] is None
    reg['game_overrides']=[dict(game_id=rows[1]['game_id'],registry_record_id='EAST:v1',evidence_uri='https://www.nfl.com/games/test')]
    assert sf(build(rows,reg))[1]['great_circle_km']>0


def test_override_can_correct_wrong_nominal_home_stadium():
    rows,reg=fixture(); rows[1]['stadium_id']='WEST'
    reg['game_overrides']=[dict(game_id=rows[1]['game_id'],registry_record_id='EAST:v1',evidence_uri='https://www.nfl.com/games/test')]
    assert sf(build(rows,reg))[1]['great_circle_km']>0


def test_duplicate_game_scope_rejected():
    rows,reg=fixture()
    with pytest.raises(ValueError):build(rows+[rows[0]],reg)
    rows[0]['home_team']='NYG'
    with pytest.raises(ValueError):build(rows,reg)


def test_duplicate_team_week_blocks_both_immediate_links():
    rows,reg=fixture(); rows.insert(1,dict(rows[0],game_id='2025_01_SF_NYG',home_team='NYG'))
    assert sf(build(rows,reg))[2]['great_circle_km'] is None


def test_missing_season_beginning_and_chronology_mask():
    rows,reg=fixture(); rows[0].update(game_id='2025_02_SF_LA',week='2')
    assert all(r['great_circle_km'] is None for r in sf(build(rows,reg)))
    rows,reg=fixture(); rows[1]['gameday']='2025-09-01'
    assert sf(build(rows,reg))[1]['great_circle_km'] is None


def test_great_circle_wraps_dateline_and_is_symmetric():
    a=dict(latitude=0,longitude=179);b=dict(latitude=0,longitude=-179)
    assert math.isclose(great_circle_km(a,b),222.390160467,rel_tol=1e-9)
    assert great_circle_km(a,b)==great_circle_km(b,a)


def test_prior_season_does_not_supply_origin():
    rows,reg=fixture(); old=dict(rows[0],season='2024',game_id='2024_18_SF_LA',week='18',gameday='2025-01-05')
    assert sf(build([old]+rows,reg))[-2]['first_game_not_applicable']


def test_international_venue_can_use_reviewed_game_identity_without_pfr_alias():
    rows,reg=fixture(); rows[1]['location']='Neutral'
    reg['venues'][1].update(source_system=None,source_venue_id=None,source_evidence_uri=None)
    reg['game_overrides']=[dict(game_id=rows[1]['game_id'],registry_record_id='EAST:v1',evidence_uri='https://www.nfl.com/games/test')]
    assert sf(build(rows,reg))[1]['great_circle_km']>0
