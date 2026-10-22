from copy import deepcopy
import pytest
from backend.app.product_services.nws_grid_gust_context import build_nws_grid_gust,interval

def fixture():
 p={'geometry':{'type':'Polygon','coordinates':[[[-82,41],[-81,41],[-81,42],[-82,42],[-82,41]]]},'properties':{'gridId':'CLE','gridX':10,'gridY':20,'updateTime':'2026-01-02T10:00:00Z','validTimes':'2026-01-02T10:00:00Z/P7D','windGust':{'uom':'wmoUnit:km_h','values':[{'validTime':'2026-01-03T12:00:00Z/PT3H','value':36}]}}}
 s={'source_uri':'https://api.weather.gov/gridpoints/CLE/10,20','source_system':'nws','dataset':'grid_gust_forecast','season':2025,'week':18,'observed_at':'2026-01-02T10:30:00Z','captured_at':'2026-01-02T10:30:01Z','snapshot_id':'grid'}
 points={'properties':{'forecastGridData':s['source_uri']}}
 ps={'source_uri':'https://api.weather.gov/points/41.5,-81.5','source_system':'nws','dataset':'grid_point_mapping','observed_at':'2026-01-02T10:29:00Z','captured_at':'2026-01-02T10:29:01Z','snapshot_id':'point'}
 g={'game_id':'2025_18_PIT_CLE','season':2025,'week':18,'home_team':'CLE','away_team':'PIT','kickoff_at':'2026-01-03T13:00:00Z'};v={'registry_record_id':'native','latitude':41.5,'longitude':-81.5}
 return p,s,points,ps,g,v

def build(args):return build_nws_grid_gust(*args,actual_cutoff='2026-01-02T12:00:00Z')

def test_maximum_native_interval_not_hourly_mean():
 r=build(fixture());assert r['maximum_gust_m_s']==10 and not r['unknown_reasons'];assert r['native_gust_interval']['validTime'].endswith('PT3H');assert r['height_m']is None and r['averaging_seconds']is None and r['original_issuance_at']is None;assert not r['model_consumed']and not r['pregame_serving_eligible']

@pytest.mark.parametrize('unit,value,expected',[('wmoUnit:m_s',0,0),('wmoUnit:kn',10,1852/360),('wmoUnit:mi_h',10,4.4704)])
def test_explicit_units_zero_observed(unit,value,expected):
 a=fixture();a[0]['properties']['windGust'].update(uom=unit);a[0]['properties']['windGust']['values'][0]['value']=value;assert build(a)['maximum_gust_m_s']==pytest.approx(expected)

@pytest.mark.parametrize('value',[None,True,-1,float('nan'),float('inf'),'36'])
def test_missing_invalid_no_zero_fill(value):
 a=fixture();a[0]['properties']['windGust']['values'][0]['value']=value;assert build(a)['maximum_gust_m_s']is None

@pytest.mark.parametrize('change',['unit','duplicate','bad_interval','outside','unknown_geometry','clock','stale','grid_link','grid_id','point','missing_venue','future_capture','naive_time','outside_product'])
def test_exactness_guards(change):
 a=fixture();p,s,points,ps,g,v=a
 if change=='unit':p['properties']['windGust']['uom']='mph'
 if change=='duplicate':p['properties']['windGust']['values']*=2
 if change=='bad_interval':p['properties']['windGust']['values'].append({'validTime':'unknown','value':1})
 if change=='outside':v['longitude']=-80
 if change=='unknown_geometry':p['geometry']=None
 if change=='clock':p['properties']['updateTime']='2026-01-02T11:00:00Z'
 if change=='stale':p['properties']['updateTime']='2026-01-01T09:00:00Z'
 if change=='grid_link':points['properties']['forecastGridData']+='0'
 if change=='grid_id':p['properties']['gridId']='BOU'
 if change=='point':ps['source_uri']='https://api.weather.gov/points/41.51,-81.5'
 if change=='missing_venue':v['latitude']=None
 if change=='future_capture':s['captured_at']='2026-01-04T10:00:00Z'
 if change=='naive_time':s['observed_at']='2026-01-02T10:30:00'
 if change=='outside_product':p['properties']['validTimes']='2026-01-02T10:00:00Z/PT1H'
 assert build(a)['maximum_gust_m_s']is None and build(a)['unknown_reasons']

def test_interval_boundary_and_aware_duration():
 a=fixture();a[4]['kickoff_at']='2026-01-03T15:00:00Z';assert build(a)['maximum_gust_m_s']is None
 assert interval('2026-01-01T00:00:00-05:00/PT1H')is not None
 for bad in ['2026-01-01T00:00:00/PT1H','2026-01-01T00:00:00Z/PT0H','2026-01-01T00:00:00Z/P1M','2026-01-01T00:00:00Z/P15D']:assert interval(bad)is None

def test_native_scope_and_authority():
 for index,key,value in [(4,'game_id','2025_18_CLE_PIT'),(1,'dataset','hourly'),(3,'source_uri','https://example.com/points/41.5,-81.5')]:
  a=fixture();a[index][key]=value
  with pytest.raises(ValueError):build(a)


def test_native_grid_wmo_unit_and_overall_calendar_span():
 a=fixture();a[0]['properties']['validTimes']='2026-01-02T10:00:00Z/P7DT17H';a[0]['properties']['windGust']['uom']='wmoUnit:km_h-1';assert build(a)['maximum_gust_m_s']==10
