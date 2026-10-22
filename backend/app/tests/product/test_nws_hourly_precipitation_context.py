from copy import deepcopy
import pytest
from backend.app.product_services.nws_hourly_precipitation_context import build_nws_hourly_precipitation as build, point_in_geometry


def fixture():
    payload=dict(type='Feature',geometry=dict(type='Polygon',coordinates=[[[-82,41],[-81,41],[-81,42],[-82,42],[-82,41]]]),
        properties=dict(forecastGenerator='HourlyForecastGenerator',generatedAt='2026-10-01T22:46:36Z',updateTime='2026-10-01T19:46:50Z',
        periods=[dict(startTime='2026-10-01T20:00:00-04:00',endTime='2026-10-01T21:00:00-04:00',probabilityOfPrecipitation=dict(unitCode='wmoUnit:percent',value=30))]))
    source=dict(source_system='nws',dataset='showdown_weather_hourly',source_uri='https://api.weather.gov/gridpoints/CLE/83,65/forecast/hourly',
        season=2026,week=4,snapshot_id='native',observed_at='2026-10-01T23:45:49Z',captured_at='2026-10-01T23:45:49Z',slate_lock_at='2026-10-02T00:15:00Z')
    game=dict(game_id='2026_04_BAL_CLE',season=2026,week=4,home_team='CLE',away_team='BAL',kickoff_at='2026-10-02T00:15:00Z')
    venue=dict(registry_record_id='native:v1',latitude=41.5,longitude=-81.7)
    return payload,source,game,venue


def run(parts):return build(*parts,actual_cutoff='2026-10-20T13:00:00Z')


def test_exact_explicit_percentage_and_fraction():
    value=run(fixture());assert value['probability_percent']==30 and value['probability_fraction']==0.3 and not value['unknown_reasons']


@pytest.mark.parametrize('value',[None,-1,101,float('nan'),True,'not-a-number'])
def test_missing_invalid_probability_is_not_zero(value):
    args=fixture();args[0]['properties']['periods'][0]['probabilityOfPrecipitation']['value']=value
    assert run(args)['probability_percent'] is None


def test_known_zero_and_one_hundred_valid():
    for value in (0,100):
        args=fixture();args[0]['properties']['periods'][0]['probabilityOfPrecipitation']['value']=value
        assert run(args)['probability_percent']==value


def test_wrong_unit_no_precip_amount_substitution():
    args=fixture();args[0]['properties']['periods'][0]['probabilityOfPrecipitation']['unitCode']='wmoUnit:mm'
    assert run(args)['probability_percent'] is None


def test_exact_interval_end_excluded_next_start_included():
    args=fixture();props=args[0]['properties'];p=props['periods'][0];p['endTime']='2026-10-02T00:15:00Z'
    assert run(args)['probability_percent'] is None
    p['startTime']='2026-10-02T00:15:00Z';p['endTime']='2026-10-02T01:15:00Z'
    assert run(args)['probability_percent']==30


def test_ambiguous_or_unlocatable_competing_period_masks():
    args=fixture();periods=args[0]['properties']['periods'];periods.append(deepcopy(periods[0]))
    assert run(args)['probability_percent'] is None
    periods.pop();periods.append(dict(startTime=None,endTime=None))
    assert run(args)['probability_percent'] is None


@pytest.mark.parametrize('field,value',[('captured_at','2026-10-02T00:16:00Z'),('observed_at','2026-10-01T23:50:00Z'),('slate_lock_at','2026-10-01T23:00:00Z'),('captured_at','2026-10-01T23:45:00')])
def test_original_clock_proof_required(field,value):
    args=fixture();args[1][field]=value
    assert run(args)['probability_percent'] is None


@pytest.mark.parametrize('field,value',[('generatedAt','2026-10-01T23:50:00Z'),('updateTime','2026-10-01T23:50:00Z'),('generatedAt','2026-09-29T22:00:00Z'),('updateTime',None)])
def test_postcapture_or_stale_forecast_unknown(field,value):
    args=fixture();args[0]['properties'][field]=value
    assert run(args)['probability_percent'] is None


def test_native_source_scope_required():
    args=fixture();args[1]['week']=5
    with pytest.raises(ValueError):run(args)
    args=fixture();args[1]['source_uri']='https://example.test/weather'
    with pytest.raises(ValueError):run(args)
    args=fixture();args[2]['home_team']='SF'
    with pytest.raises(ValueError):run(args)


def test_geo_boundary_included_outside_unknown_no_city_fallback():
    args=fixture();args[3]['longitude']=-82
    assert run(args)['probability_percent']==30
    args[3]['longitude']=-83;args[3]['city']='Cleveland'
    assert run(args)['probability_percent'] is None
    args[3]['longitude']=None
    assert run(args)['probability_percent'] is None


def test_malformed_ring_and_hole_interiors():
    args=fixture();geo=args[0]['geometry'];geo['coordinates'].append([[-81.9,41.1],[-81.1,41.1],[-81.1,41.9],[-81.9,41.9],[-81.9,41.1]])
    assert point_in_geometry(-81.7,41.5,geo) is False
    assert point_in_geometry(-81.9,41.5,geo) is True
    geo['coordinates'][0].pop()
    assert point_in_geometry(-81.7,41.5,geo) is None


def test_nonhourly_and_malformed_typed_field_unknown():
    args=fixture();p=args[0]['properties']['periods'][0];p['endTime']='2026-10-01T22:00:00-04:00'
    assert run(args)['probability_percent'] is None
    args=fixture();args[0]['properties']['periods'][0]['probabilityOfPrecipitation']=7
    assert run(args)['probability_percent'] is None
