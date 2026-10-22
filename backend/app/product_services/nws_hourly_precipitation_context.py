"""Explicit-unit NWS kickoff-hour precipitation probability, not observed rainfall."""
from datetime import datetime, UTC
import math
import re
from .evaluation_record import digest
from .market_snapshots import canonical_team

VERSION='nws_hourly_precipitation_context_v1'
MAX_FORECAST_AGE_HOURS=24


def _time(value):
    try:
        result=datetime.fromisoformat(value.replace('Z','+00:00')) if isinstance(value,str) else value
        return result.astimezone(UTC) if isinstance(result,datetime) and result.tzinfo is not None else None
    except (TypeError,ValueError):
        return None


def _number(value,limit):
    if value is None or isinstance(value,bool):return None
    try:value=float(value)
    except (TypeError,ValueError):return None
    return value if math.isfinite(value) and abs(value)<=limit else None


def _ring(point,ring):
    """Return boundary, inside, or outside. Invalid/nonclosed native rings unknown."""
    if not isinstance(ring,list) or not 4<=len(ring)<=100 or ring[0]!=ring[-1]:return None
    vertices=[]
    for vertex in ring:
        if not isinstance(vertex,list) or len(vertex)!=2:return None
        x,y=_number(vertex[0],180),_number(vertex[1],90)
        if x is None or y is None:return None
        vertices.append((x,y))
    area=sum(a*d-c*b for (a,b),(c,d) in zip(vertices,vertices[1:]))
    if len(set(vertices))<3 or abs(area)<1e-12 or max(v[0] for v in vertices)-min(v[0] for v in vertices)>180:return None
    x,y=point;inside=False
    for (a,b),(c,d) in zip(vertices,vertices[1:]):
        if abs((x-a)*(d-b)-(y-b)*(c-a))<=1e-12 and min(a,c)-1e-12<=x<=max(a,c)+1e-12 and min(b,d)-1e-12<=y<=max(b,d)+1e-12:
            return 'boundary'
        if (b>y)!=(d>y) and x<(c-a)*(y-b)/(d-b)+a:inside=not inside
    return 'inside' if inside else 'outside'


def point_in_geometry(longitude,latitude,geometry):
    """GeoJSON Polygon only; exact boundary included, holes excluded."""
    x,y=_number(longitude,180),_number(latitude,90)
    if x is None or y is None or not isinstance(geometry,dict) or geometry.get('type')!='Polygon':return None
    rings=geometry.get('coordinates')
    if not isinstance(rings,list) or not rings:return None
    values=[_ring((x,y),ring) for ring in rings]
    if None in values:return None
    if values[0]=='outside':return False
    if values[0]=='boundary' or 'boundary' in values[1:]:return True
    return not any(value=='inside' for value in values[1:])


def build_nws_hourly_precipitation(payload,source,game,venue,*,actual_cutoff):
    """Native unique game/venue input is authenticated separately; no city/name match."""
    parts=str(game.get('game_id')).split('_')
    if (len(parts)!=4 or parts[:2]!=[str(game.get('season')),f"{game.get('week'):02d}"]
            or canonical_team(parts[2])!=game.get('away_team') or canonical_team(parts[3])!=game.get('home_team')
            or not game.get('home_team') or game['home_team']==game.get('away_team')):
        raise ValueError('Native unique game/team scope required')
    if (source.get('source_system'),source.get('dataset'))!=('nws','showdown_weather_hourly') or not re.fullmatch(r'https://api\.weather\.gov/gridpoints/[A-Z]{3}/\d+,\d+/forecast/hourly',str(source.get('source_uri'))):
        raise ValueError('Original NWS hourly source contract required')
    if (source.get('season'),source.get('week'))!=(game['season'],game['week']):raise ValueError('Native forecast/game scope mismatch')
    reasons=[];kickoff=_time(game.get('kickoff_at'));capture=_time(source.get('captured_at'));observed=_time(source.get('observed_at'));lock=_time(source.get('slate_lock_at'));cutoff=_time(actual_cutoff)
    if any(t is None for t in (kickoff,capture,observed,lock,cutoff)) or not observed<=capture<kickoff or not capture<lock or capture>cutoff:
        reasons.append('original_source_capture_or_game_chronology_unknown')
    props=payload.get('properties')
    if not isinstance(props,dict):props={};reasons.append('missing_native_forecast_properties')
    generated=_time(props.get('generatedAt'));updated=_time(props.get('updateTime'))
    if (generated is None or updated is None or capture is None or kickoff is None or generated>capture or updated>capture
            or generated<updated or not 0<=(kickoff-generated).total_seconds()/3600<=MAX_FORECAST_AGE_HOURS
            or props.get('forecastGenerator')!='HourlyForecastGenerator'):
        reasons.append('unknown_or_stale_hourly_forecast_publication')
    within=point_in_geometry(venue.get('longitude'),venue.get('latitude'),payload.get('geometry'))
    if within is not True or not venue.get('registry_record_id'):
        reasons.append('native_venue_not_proven_inside_source_grid_polygon')
    periods=props.get('periods');matches=[];invalid_intervals=False
    if not isinstance(periods,list) or len(periods)>500:reasons.append('bounded_hourly_periods_required');periods=[]
    for period in periods:
        if not isinstance(period,dict):invalid_intervals=True;continue
        start,end=_time(period.get('startTime')),_time(period.get('endTime'))
        if start is None or end is None or end<=start:
            invalid_intervals=True;continue
        if kickoff is not None and start<=kickoff<end:matches.append((period,start,end))
    # An unlocatable interval could be a competing kickoff observation.
    if invalid_intervals:reasons.append('unlocated_or_invalid_forecast_interval')
    selected=None;percent=None
    if len(matches)!=1:reasons.append('missing_or_ambiguous_kickoff_interval')
    else:
        selected,start,end=matches[0]
        if (end-start).total_seconds()!=3600:reasons.append('not_one_hour_forecast_interval')
        field=selected.get('probabilityOfPrecipitation')
        if not isinstance(field,dict):field={}
        percent=_number(field.get('value'),100)
        if field.get('unitCode')!='wmoUnit:percent' or percent is None or percent<0:
            reasons.append('missing_or_invalid_explicit_percent_probability')
    exact=percent if not reasons else None
    basis=dict(version=VERSION,candidate_ids=['G20-M07'],game_id=game['game_id'],season=game['season'],week=game['week'],
        home_team=game['home_team'],away_team=game['away_team'],kickoff_at=game.get('kickoff_at'),venue_record_id=venue.get('registry_record_id'),
        grid_contains_venue=within,geometry_boundary_convention='Polygon boundary included; hole interiors excluded; malformed geometry unknown',
        native_period=selected,probability_percent=exact,probability_fraction=exact/100 if exact is not None else None,
        unknown_reasons=reasons,forecast_maximum_age_hours=MAX_FORECAST_AGE_HOURS,
        original_forecast_generated_at=generated.isoformat() if generated else None,
        original_forecast_updated_at=updated.isoformat() if updated else None,
        source_capture_at=capture.isoformat() if capture else None,source_snapshot_id=source.get('snapshot_id'))
    return dict(**basis,semantic_sha256=digest(basis),evidence_use='source_reported_hourly_forecast_not_observed_rainfall_or_calibrated_probability',
        probability_unit='percent; fraction=percent/100',model_consumed=False,optimizer_consumed=False,pregame_serving_eligible=False,
        chronology_limitation='Original forecast receipt clocks separate from later revised native schedule/registry binding; not all-input original-pregame proof')
