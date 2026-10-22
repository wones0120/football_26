"""Native schedule venue/weather/rest measurements, never invented forecasts."""
from datetime import datetime,UTC
from decimal import Decimal,InvalidOperation
import math
from .market_snapshots import canonical_team
from .factual_designation import clock
from .evaluation_record import digest

VERSION='native_schedule_context_features_v1'
SOURCE_URL='https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet'
FIELDS=('roof','surface','temp','wind','home_rest','away_rest')


def _integer(v):
    if v is None or isinstance(v,bool):raise ValueError('Integer native scope required')
    try:d=Decimal(str(v))
    except InvalidOperation as e:raise ValueError('Invalid native scope') from e
    if not d.is_finite() or d!=d.to_integral_value():raise ValueError('Nonintegral native scope')
    return int(d)


def _value(v,nonnegative=False,integer=False):
    if v is None or v=='' or isinstance(v,bool):return None
    try:n=float(v)
    except (TypeError,ValueError):return None
    if not math.isfinite(n) or nonnegative and n<0 or integer and not n.is_integer():return None
    return n


def normalize_schedule_context(records,*,cutoff,max_rows=50000):
    cutoff=clock(cutoff)
    if cutoff is None:raise ValueError('Actual cutoff required')
    rows=[];seen=set()
    for index,r in enumerate(records):
        if index>=max_rows:raise ValueError('Schedule row bound exceeded')
        season,week=_integer(r.get('season')),_integer(r.get('week'));phase=r.get('game_type')
        if not 1999<=season<=cutoff.year or phase not in {'REG','WC','DIV','CON','SB'} or not 1<=week<=25:raise ValueError('Native schedule scope invalid')
        home,away=canonical_team(r.get('home_team')),canonical_team(r.get('away_team'))
        gid=r.get('game_id');parts=str(gid).split('_')
        if not home or not away or home==away or len(parts)!=4 or _integer(parts[0])!=season or _integer(parts[1])!=week or canonical_team(parts[2])!=away or canonical_team(parts[3])!=home:raise ValueError('Native game/team identity mismatch')
        if gid in seen:raise ValueError('Duplicate native game')
        seen.add(gid)
        roof=r.get('roof');roof=roof if roof in {'dome','outdoors','open','closed'} else None
        retractable=roof if roof in {'open','closed'} else None
        surface=r.get('surface') or None
        if surface is not None and not isinstance(surface,str):surface=None
        team_rows=[]
        for team,role in ((home,'home'),(away,'away')):
            rest=_value(r.get(role+'_rest'),nonnegative=True,integer=True)
            metrics={
                'G20-M03':dict(value=retractable,unit='source_roof_state',unknown_reason=None if retractable else 'No explicit retractable open/closed state'),
                'G20-M04':dict(value=_value(r.get('temp')),unit='provider_temperature_native_units'),
                'G20-M05':dict(value=_value(r.get('wind'),nonnegative=True),unit='source_wind_mph'),
                'G20-M08':dict(value=surface,unit='source_surface_category'),
                'G20-M09':dict(value=rest,unit='source_reported_days_since_previous_game')}
            team_rows.append(dict(team=team,home_away=role,metrics=metrics))
        rows.append(dict(game_id=gid,season=season,week=week,game_type=phase,game_date=r.get('gameday'),
            home_team=home,away_team=away,source_roof=roof,team_rows=team_rows,
            measurement_kind='provider_schedule_measurement_not_verified_pregame_forecast',source_row=index))
    rows.sort(key=lambda r:r['game_id'])
    semantic=[{k:v for k,v in r.items() if k!='source_row'} for r in rows]
    return dict(version=VERSION,game_rows=rows,semantic_sha256=digest(dict(version=VERSION,game_rows=semantic)),
        source_gaps={'G20-M06':'No gust field established','G20-M07':'No precipitation field established','G20-M10':'No exact travel/time-zone source joined'},
        limitations=['Schedule temperature/wind and roof can be revised realized-game observations; not pregame weather forecasts',
            'Vendor rest values retained without claiming independent prior-game completion verification',
            'Schedule dictionary does not explicitly state temperature units; native values retained without conversion',
            'Unspecified retractable-roof state remains unknown; outdoors/dome do not prove retractable mechanism'],
        forecast=None,model_consumed=False,optimizer_consumed=False)


def capture_schedule_context(service,*,season,week,slate,slate_lock_at,nfl_module=None):
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from backend.app.services.source_capture import DEFAULT_NFLREADPY_LICENSE,verify_snapshot_artifact
    import hashlib
    if nfl_module is None:import nflreadpy as nfl_module
    if type(season) is not int or season!=datetime.now(UTC).year or type(week) is not int or not 1<=week<=18 or not slate or clock(slate_lock_at) is None:raise ValueError('Explicit capture scope required')
    frame=nfl_module.load_schedules(seasons=True)
    required={'game_id','season','week','game_type','home_team','away_team'}
    if not required.issubset(frame.columns) or not 0<len(frame)<=50000:raise ValueError('Schedule schema or row bound invalid')
    payload=frame.write_csv().encode()
    if len(payload)>32*1024*1024:raise ValueError('Schedule byte bound exceeded')
    with TemporaryDirectory(prefix='football_schedule_') as tmp:
        p=Path(tmp)/'games_all_provider_seasons.csv';p.write_bytes(payload)
        result=service.capture_file(p,source_system='nflreadpy',dataset='schedule_context',season=season,week=week,slate=slate,
            source_license=DEFAULT_NFLREADPY_LICENSE,source_uri=SOURCE_URL,slate_lock_at=clock(slate_lock_at),observation_basis='capture_clock',
            media_type='text/csv',row_count=len(frame),metadata=dict(contract=VERSION,loader='load_schedules',loader_seasons=True,
                raw_representation='Installed-provider returned CSV, not original remote Parquet',provider_csv_sha256=hashlib.sha256(payload).hexdigest(),
                columns=list(frame.columns),remote_cache_freshness='Unverified',original_historical_availability='Unknown revised source'))
    verify_snapshot_artifact(result.snapshot)
    return result


def load_schedule_context(snapshot,*,cutoff):
    from pathlib import Path
    import csv
    from backend.app.services.source_capture import verify_snapshot_artifact
    verify_snapshot_artifact(snapshot);cutoff=clock(cutoff)
    if snapshot.source_system!='nflreadpy' or snapshot.dataset!='schedule_context' or snapshot.source_uri!=SOURCE_URL or snapshot.media_type!='text/csv':raise ValueError('Indexed schedule source contract differs')
    observed,captured=clock(snapshot.observed_at),clock(snapshot.captured_at)
    if cutoff is None or observed is None or captured is None or not observed<=captured<=cutoff:raise ValueError('Schedule source unavailable at cutoff')
    if not 0<snapshot.byte_count<=32*1024*1024:raise ValueError('Schedule byte bound exceeded')
    with Path(snapshot.artifact_path).open(newline='') as f:
        reader=csv.DictReader(f);fields=reader.fieldnames or [];result=normalize_schedule_context(reader,cutoff=cutoff)
    if len(result['game_rows'])!=snapshot.row_count:raise ValueError('Indexed schedule row count differs')
    result['provenance']=dict(snapshot_id=str(snapshot.snapshot_id),sha256=snapshot.content_sha256,observed_at=observed.isoformat(),captured_at=captured.isoformat(),actual_read_cutoff=cutoff.isoformat(),field_availability={field:field in fields for field in FIELDS})
    result.update(evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False)
    return result
