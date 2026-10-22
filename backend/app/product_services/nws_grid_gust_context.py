"""Native NWS maximum-gust interval containing kickoff; not observed stadium wind."""
from datetime import datetime,UTC,timedelta
import math,re
from .nws_hourly_precipitation_context import _time,_number,point_in_geometry
from .market_snapshots import canonical_team
from .evaluation_record import digest
VERSION='nws_grid_gust_context_v1'
UNITS={'wmoUnit:km_h-1':1/3.6,'wmoUnit:m_s-1':1.,'wmoUnit:km_h':1/3.6,'wmoUnit:m_s':1.,'wmoUnit:kn':1852/3600,'wmoUnit:mi_h':.44704}

def interval(value):
    if not isinstance(value,str)or value.count('/')!=1:return None
    a,b=value.split('/');start=_time(a)
    if start is None:return None
    if b.startswith('P'):
        m=re.fullmatch(r'P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?',b)
        if not m or not any(m.groups()):return None
        try:end=start+timedelta(days=int(m[1]or 0),hours=int(m[2]or 0),minutes=int(m[3]or 0),seconds=float(m[4]or 0))
        except OverflowError:return None
    else:end=_time(b)
    return (start,end)if end is not None and 0<(end-start).total_seconds()<=14*86400 else None

def build_nws_grid_gust(payload,source,points,points_source,game,venue,*,actual_cutoff):
    if not isinstance(payload,dict)or not isinstance(points,dict):raise ValueError('Native JSON objects required')
    parts=str(game.get('game_id')).split('_');week=game.get('week');season=game.get('season')
    if not isinstance(week,int)or isinstance(week,bool)or len(parts)!=4 or parts[:2]!=[str(season),f'{week:02d}']or canonical_team(parts[2])!=game.get('away_team')or canonical_team(parts[3])!=game.get('home_team')or game.get('home_team')==game.get('away_team'):raise ValueError('Unique native game scope required')
    uri=str(source.get('source_uri'));m=re.fullmatch(r'https://api\.weather\.gov/gridpoints/([A-Z]{3})/(\d+),(\d+)',uri)
    if not m or(source.get('source_system'),source.get('dataset'))!=('nws','grid_gust_forecast')or(source.get('season'),source.get('week'))!=(season,week):raise ValueError('Native NWS grid/game source contract required')
    pm=re.fullmatch(r'https://api\.weather\.gov/points/(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)',str(points_source.get('source_uri')))
    if not pm or(points_source.get('source_system'),points_source.get('dataset'))!=('nws','grid_point_mapping'):raise ValueError('Native NWS point mapping required')
    reasons=[];props=payload.get('properties')if isinstance(payload,dict)else None;props=props if isinstance(props,dict)else {};pp=points.get('properties')if isinstance(points,dict)else None;pp=pp if isinstance(pp,dict)else {}
    if pp.get('forecastGridData')!=uri or(props.get('gridId'),str(props.get('gridX')),str(props.get('gridY')))!=(m[1],m[2],m[3]):reasons.append('point_grid_native_link_unknown')
    lat=_number(venue.get('latitude'),90);lon=_number(venue.get('longitude'),180)
    if not venue.get('registry_record_id')or lat is None or lon is None or abs(float(pm[1])-lat)>1e-4 or abs(float(pm[2])-lon)>1e-4:reasons.append('point_native_venue_binding_unknown')
    within=point_in_geometry(venue.get('longitude'),venue.get('latitude'),payload.get('geometry'))
    if within is not True:reasons.append('venue_outside_or_unknown_grid_geometry')
    kickoff=_time(game.get('kickoff_at'));capture=_time(source.get('captured_at'));obs=_time(source.get('observed_at'));pc=_time(points_source.get('captured_at'));po=_time(points_source.get('observed_at'));cutoff=_time(actual_cutoff);updated=_time(props.get('updateTime'))
    if any(v is None for v in(kickoff,capture,obs,pc,po,cutoff,updated))or cutoff>datetime.now(UTC)or not(po<=pc<=capture<=cutoff and obs<=capture<kickoff and updated<=capture):reasons.append('forecast_point_capture_update_chronology_unknown')
    if updated and capture and not 0<=(capture-updated).total_seconds()<=86400:reasons.append('stale_at_capture_update')
    bounds=interval(props.get('validTimes'))
    if bounds is None or kickoff is None or not bounds[0]<=kickoff<bounds[1]:reasons.append('kickoff_outside_product_validity')
    field=props.get('windGust');field=field if isinstance(field,dict)else {};values=field.get('values');matches=[];bad=False
    if not isinstance(values,list)or len(values)>500:values=[];bad=True
    for row in values:
        span=interval(row.get('validTime'))if isinstance(row,dict)else None
        if span is None:bad=True;continue
        if bounds and not bounds[0]<=span[0]<span[1]<=bounds[1]:bad=True
        if kickoff and span[0]<=kickoff<span[1]:matches.append((row,span))
    if bad:reasons.append('unlocated_or_invalid_gust_interval')
    selected=None;raw=None
    if len(matches)!=1:reasons.append('missing_or_ambiguous_kickoff_gust_interval')
    else:
        selected,span=matches[0];raw=selected.get('value')
        if not isinstance(raw,(int,float))or isinstance(raw,bool)or not math.isfinite(raw)or raw<0:reasons.append('missing_or_invalid_gust_value')
    factor=UNITS.get(field.get('uom'))
    if factor is None:reasons.append('unknown_explicit_gust_unit')
    value=float(raw)if not reasons else None
    core=dict(version=VERSION,candidate_ids=['G20-M06'],game_id=game['game_id'],kickoff_at=game.get('kickoff_at'),venue_record_id=venue.get('registry_record_id'),grid_contains_venue=within,native_gust_interval=selected,native_unit=field.get('uom'),maximum_gust_native=value,maximum_gust_m_s=value*factor if value is not None else None,unknown_reasons=reasons,source_snapshot_id=source.get('snapshot_id'),point_snapshot_id=points_source.get('snapshot_id'),source_updated_at=updated.isoformat()if updated else None,source_capture_at=capture.isoformat()if capture else None,original_issuance_at=None,height_m=None,averaging_seconds=None,interval_selection='unique start<=kickoff<end; source interval retained, not forced to one hour',definition='NWS source-reported maximum forecast wind gust for native grid valid interval containing kickoff; not observed wind, hourly mean or guaranteed stadium interior conditions')
    return dict(**core,semantic_sha256=digest(core),model_consumed=False,optimizer_consumed=False,pregame_serving_eligible=False,chronology_limitation='Original point/grid receipts separate from revised native schedule/venue attribution; original issuance unknown, product update retained')
