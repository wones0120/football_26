"""Explicit NWS native prevailing/sustained hourly product, not observed wind."""
import math,re
from copy import deepcopy
from .nws_hourly_precipitation_context import VERSION as PARENT_VERSION
from .evaluation_record import digest

VERSION='nws_hourly_wind_context_v1'
# Exact length/time conversions; source units remain independently visible.
TEXT_UNITS={'mph':0.44704,'km/h':1/3.6,'kph':1/3.6,'m/s':1.,'knots':1852/3600}
QUANT_UNITS={'wmoUnit:mi_h-1':0.44704,'wmoUnit:km_h-1':1/3.6,'wmoUnit:m_s-1':1.,'wmoUnit:kn':1852/3600}
PATTERN=re.compile(r'(\d+(?:\.\d+)?)\s*(?:to\s+(\d+(?:\.\d+)?))?\s+(mph|km/h|kph|m/s|knots)')


def parse_native_wind(value):
    reasons=[];unit=None;low=high=scalar=None;factor=None;is_range=False
    if isinstance(value,str):
        m=PATTERN.fullmatch(value.strip())
        if m:
            low=float(m[1]);high=float(m[2])if m[2]is not None else low;unit=m[3];factor=TEXT_UNITS[unit];is_range=m[2]is not None
        else:reasons.append('unrecognized_explicit_wind_text')
    elif isinstance(value,dict):
        unit=value.get('unitCode');factor=QUANT_UNITS.get(unit);n=value.get('value')
        try:numeric=float(n)if type(n)in(int,float)else None
        except (ValueError,TypeError,OverflowError):numeric=None
        if numeric is not None and math.isfinite(numeric):low=high=numeric
        else:reasons.append('missing_or_invalid_native_numeric_wind')
        if factor is None:reasons.append('unsupported_explicit_wind_unit')
    else:reasons.append('missing_native_wind_field')
    if low is not None and (not math.isfinite(low)or not math.isfinite(high)or low<0 or high<low):reasons.append('invalid_native_wind_bounds')
    if not reasons and not is_range:scalar=low
    valid=not reasons
    return dict(raw_native_wind=deepcopy(value),native_unit=unit,native_scalar=scalar,native_lower=low if valid else None,native_upper=high if valid else None,
        native_is_range=is_range if valid else None,scalar_meters_per_second=scalar*factor if scalar is not None else None,
        lower_meters_per_second=low*factor if valid else None,upper_meters_per_second=high*factor if valid else None,unknown_reasons=reasons)


def build_nws_hourly_wind(parent):
    if parent.get('version')!=PARENT_VERSION or parent.get('candidate_ids')!=['G20-M07'] or parent.get('pregame_serving_eligible')is not False or parent.get('model_consumed')is not False:raise ValueError('Reviewed nonserving NWS hourly binding required')
    reasons=[r for r in parent['unknown_reasons']if r!='missing_or_invalid_explicit_percent_probability']
    period=parent.get('native_period');parsed=parse_native_wind(period.get('windSpeed')if isinstance(period,dict)else None)
    reasons+=parsed['unknown_reasons'];exact=not reasons
    if not exact:
        for field in('native_scalar','native_lower','native_upper','scalar_meters_per_second','lower_meters_per_second','upper_meters_per_second'):parsed[field]=None
    core=dict(version=VERSION,candidate_ids=['G20-M05'],game_id=parent['game_id'],season=parent['season'],week=parent['week'],home_team=parent['home_team'],away_team=parent['away_team'],kickoff_at=parent['kickoff_at'],venue_record_id=parent['venue_record_id'],
        source_snapshot_id=parent['source_snapshot_id'],native_period=deepcopy(period),wind=parsed,unknown_reasons=reasons,
        original_forecast_generated_at=parent['original_forecast_generated_at'],original_forecast_updated_at=parent['original_forecast_updated_at'],source_capture_at=parent['source_capture_at'],
        interpretation='NWS source-native prevailing/sustained HOURLY product via official DWML-to-hourly API chain; not inferred from magnitude',
        averaging_duration=None,forecast_height_meters=None,forecast_interval_is_wind_averaging_duration=False,
        gust_field_present=isinstance(period,dict)and'windGust'in period,gust_value_not_substituted=True,
        range_convention='Preserve explicit bounds; no scalar/midpoint is inferred from a textual range',
        chronology_limitation=parent['chronology_limitation'])
    return dict(**core,semantic_sha256=digest(core),model_consumed=False,optimizer_consumed=False,pregame_serving_eligible=False,evidence_use='source_reported_native_hourly_wind_forecast_not_observed_or_calibrated')


def load_reviewed_nws_hourly_parent(ref,*,cutoff):
    from pathlib import Path
    from datetime import datetime,UTC
    import json,hashlib
    from . import nws_hourly_precipitation_context
    from .factual_designation import clock
    p=Path(ref['path']).resolve();actual=clock(cutoff)
    if p.parent!=Path('artifacts/nws_hourly_precipitation_context').resolve()or p.name!=ref['sha256']+'.json'or not 0<ref['bytes']<=1024*1024:raise ValueError('Managed bounded NWS parent required')
    b=p.read_bytes()
    if len(b)!=ref['bytes']or hashlib.sha256(b).hexdigest()!=ref['sha256']:raise ValueError('NWS parent bytes differ')
    x=json.loads(b);pub=clock(x['provenance']['actual_publication_at'])
    if actual is None or actual>datetime.now(UTC)or pub is None or pub>actual:raise ValueError('NWS parent publication unavailable')
    if x['provenance']['producer_code_sha256']!=hashlib.sha256(Path(nws_hourly_precipitation_context.__file__).read_bytes()).hexdigest():raise ValueError('Reviewed NWS parent producer differs')
    keys=('version','candidate_ids','game_id','season','week','home_team','away_team','kickoff_at','venue_record_id','grid_contains_venue','geometry_boundary_convention','native_period','probability_percent','probability_fraction','unknown_reasons','forecast_maximum_age_hours','original_forecast_generated_at','original_forecast_updated_at','source_capture_at','source_snapshot_id')
    if digest({k:x[k]for k in keys})!=x['semantic_sha256']:raise ValueError('NWS parent semantic binding differs')
    return x
