"""Immutable free nflverse/PFR source capture with separate week/season grains.

No statistic or identity is inferred from player display names. This source
adapter does not promote annual aggregates into historical weekly inputs.
"""
from datetime import UTC,datetime
import hashlib,io,re
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import Request,urlopen
import polars as pl
from .market_snapshots import canonical_team

VERSION='pfr_native_source_v1'
BASE='https://github.com/nflverse/nflverse-data/releases/download/pfr_advstats/'
ASSET=re.compile(r'advstats_(?:week_(pass|rush|rec|def)_(20\d{2})|season_(pass|rush|rec|def))\.parquet')


def asset_scope(name):
    match=ASSET.fullmatch(name)
    if not match:raise ValueError('Native PFR release asset name required')
    weekly=match[1] is not None
    return dict(stat_type=match[1] or match[3],summary_level='week' if weekly else 'season',season=int(match[2]) if weekly else None)


def _int(value):
    if isinstance(value,bool) or value is None:raise ValueError('Typed PFR integer required')
    integer=int(value)
    if float(value)!=integer:raise ValueError('Fractional PFR period')
    return integer


def validate_pfr_frame(frame,*,stat_type,summary_level,season=None,max_season=None):
    if stat_type not in {'pass','rush','rec','def'} or summary_level not in {'week','season'}:raise ValueError('Explicit PFR type/grain required')
    if not isinstance(frame,pl.DataFrame):raise ValueError('Original native Polars frame required')
    if frame.height>200000:raise ValueError('PFR native row bound exceeded')
    columns=set(frame.columns)
    native='pfr_player_id' if 'pfr_player_id' in columns else 'pfr_id' if 'pfr_id' in columns else None
    required={'season',native} if native else {'season','pfr_player_id_or_pfr_id'}
    if summary_level=='week':required|={'week','game_id','pfr_game_id','team','game_type'}
    if not required<=columns:raise ValueError('PFR native grain fields missing: '+','.join(sorted(required-columns)))
    years={};game_types={};seen=set();duplicates=[];unresolved=[];game_map={};pfr_map={}
    team_field='team' if 'team' in columns else 'tm' if 'tm' in columns else None
    for i,row in enumerate(frame.to_dicts()):
        year=_int(row['season'])
        if not 2018<=year<=2200 or season is not None and year!=season or max_season is not None and year>max_season:raise ValueError('Native season differs from asset scope')
        years[year]=years.get(year,0)+1
        pid=row.get(native)
        if {'pfr_id','pfr_player_id'}<=columns and row.get('pfr_id') is not None and row.get('pfr_player_id') is not None and row['pfr_id']!=row['pfr_player_id']:
            unresolved.append(dict(native_row=i,reason='conflicting_native_pfr_player_ids'));pid=None
        elif not isinstance(pid,str) or not pid.strip():
            unresolved.append(dict(native_row=i,reason='missing_native_pfr_player_id'))
            pid=None
        if summary_level=='week':
            week=_int(row['week']);kind=row['game_type'];gid=row['game_id']
            if not 1<=week<=25 or kind not in {'REG','POST','WC','DIV','CON','SB'} or kind=='REG' and week>18:raise ValueError('Invalid native PFR game period/type')
            parts=str(gid).split('_')
            if len(parts)!=4 or (_int(parts[0]),_int(parts[1]))!=(year,week) or not row.get('team'):raise ValueError('Native PFR game identity differs from period')
            if canonical_team(row['team']) not in {canonical_team(t) for t in parts[2:]}:raise ValueError('PFR team outside native game')
            pfr_game=row.get('pfr_game_id')
            if not isinstance(pfr_game,str) or not pfr_game:unresolved.append(dict(native_row=i,reason='missing_native_pfr_game_id'))
            else:
                if gid in game_map and game_map[gid]!=pfr_game or pfr_game in pfr_map and pfr_map[pfr_game]!=gid:raise ValueError('Native PFR game crosswalk conflicts')
                game_map[gid]=pfr_game;pfr_map[pfr_game]=gid
            game_types[kind]=game_types.get(kind,0)+1
            key=(gid,row['team'],pid)
        else:
            # Multi-team aggregate labels are retained literally, never mapped
            # to an NFL team or duplicated into every week of that season.
            key=(year,row.get(team_field) if team_field else None,pid)
        if pid is not None and key in seen:duplicates.append(dict(native_row=i,native_key=list(key)))
        seen.add(key)
    return dict(version=VERSION,stat_type=stat_type,summary_level=summary_level,native_player_id_field=native,
        row_count=frame.height,columns=frame.columns,dtypes={k:str(v) for k,v in frame.schema.items()},season_rows=years,
        game_type_rows=game_types,native_team_field=team_field,duplicate_native_rows=duplicates,identity_requests=unresolved,
        native_grain_valid=not duplicates and not unresolved,
        time_grain='player_game' if summary_level=='week' else 'player_season_aggregate',
        weekly_feature_use_allowed=summary_level=='week',
        current_serving_eligible=False,historical_pregame_reconstruction_eligible=False,
        original_historical_availability='Unknown: later revised provider release, actual receipt retained',
        canonical_identity='Native PFR ID retained; no canonical name-based mapping attempted',forecast=None)


def download_pfr_asset(asset,*,timeout=30,max_bytes=4*1024*1024):
    name=asset['name'];asset_scope(name)
    if asset['url']!=BASE+name:raise ValueError('Unexpected PFR provider URL')
    with urlopen(Request(asset['url'],headers={'Accept':'application/octet-stream','Cache-Control':'no-cache','User-Agent':'football-feature-source-capture'}),timeout=timeout) as response:
        data=response.read(max_bytes+1);headers=dict(response.headers)
    if len(data)>max_bytes:raise ValueError('PFR download byte bound exceeded')
    if asset.get('bytes') is not None and len(data)!=asset['bytes']:raise ValueError('PFR asset release size changed; refresh manifest explicitly')
    return data,headers


def capture_pfr_asset(service,asset,*,capture_season,fetch=download_pfr_asset,clock=lambda:datetime.now(UTC)):
    """One source asset exactly once; original remote Parquet bytes retained.

    For all-season files, capture_season is a storage/run scope only. Native
    season coverage remains in validation; no current-season-only claim occurs.
    Source capture does not normalize stats, write aliases or fit a model.
    """
    scope=asset_scope(asset['name']);data,headers=fetch(asset);received=clock()
    if len(data)>4*1024*1024:raise ValueError('PFR raw byte bound exceeded')
    frame=None;validation_error=None
    try:frame=pl.read_parquet(io.BytesIO(data))
    except Exception as exc:validation_error=type(exc).__name__+': '+str(exc)[:300]
    with TemporaryDirectory() as temp:
        path=Path(temp)/asset['name'];path.write_bytes(data)
        result=service.capture_file(path,source_system='nflverse_pfr',dataset='pfr_advstats_'+scope['summary_level']+'_'+scope['stat_type'],
            season=scope['season'] or capture_season,week=None,slate='feature_inventory',source_uri=asset['url'],
            source_license='Public nflverse PFR release; original provider attribution retained; redistribution terms not independently certified',
            media_type='application/vnd.apache.parquet',row_count=frame.height if frame is not None else None,
            effective_at=received,observation_basis='actual_provider_download_receipt_clock',
            metadata=dict(version=VERSION,**scope,storage_capture_season=capture_season,
                raw_remote_format='parquet_original_bytes',source_asset_updated_at=asset.get('updated_at'),
                source_publication_at=None,http_headers=headers,provider_cache_revalidation='Requested no-cache; upstream generation freshness unknown',
                evidence_use='revised_source_feature_inventory_not_original_historical_pregame',model_consumed=False))
    validation=None
    if frame is not None:
        try:validation=validate_pfr_frame(frame,**scope,max_season=capture_season)
        except (ValueError,TypeError,KeyError) as exc:validation_error=type(exc).__name__+': '+str(exc)[:300]
    snapshot=result.snapshot
    return dict(version=VERSION,asset_name=asset['name'],scope=scope,status='captured_validated' if validation and validation['native_grain_valid'] else 'captured_requires_review',
        source_snapshot_id=str(snapshot.snapshot_id),source_sha256=snapshot.content_sha256,raw_remote_sha256=hashlib.sha256(data).hexdigest(),
        source_bytes=len(data),actual_received_at=received.isoformat(),actual_captured_at=str(snapshot.captured_at),
        validation=validation,validation_error=validation_error,model_consumed=False,optimizer_consumed=False)


def select_prior_weekly_pfr(frame,*,stat_type,before_period):
    """Retrospective feature extraction only; annual input is always rejected."""
    validate_pfr_frame(frame,stat_type=stat_type,summary_level='week')
    if type(before_period) is not int or not 2000<=before_period//100<=2200 or not 1<=before_period%100<=18:raise ValueError('REG target period required')
    return frame.filter((pl.col('game_type')=='REG')&((pl.col('season')*100+pl.col('week'))<before_period))


def persist_pfr_native_requests(connection,snapshot):
    """Existing UI quarantine, keyed by immutable native row, never its name.

    No alias or canonical player is guessed. Repeated evidence is idempotent;
    a previously human-resolved record is not reopened by a source replay.
    """
    from sqlalchemy import text
    from backend.app.services.source_capture import verify_snapshot_artifact
    verify_snapshot_artifact(snapshot)
    name=Path(snapshot.artifact_path).name;scope=asset_scope(name)
    if snapshot.source_system!='nflverse_pfr' or snapshot.source_uri!=BASE+name:raise ValueError('Indexed native PFR source required')
    frame=pl.read_parquet(snapshot.artifact_path)
    validation=validate_pfr_frame(frame,**scope,max_season=snapshot.captured_at.year)
    rows=frame.to_dicts();keys=[]
    for request in validation['identity_requests']:
        index=request['native_row'];row=rows[index]
        key=f"pfr-row:{snapshot.content_sha256}:{index}"
        qid='pfr-native:'+hashlib.sha256(key.encode()).hexdigest()[:32]
        connection.execute(text("""
            INSERT INTO target.identity_quarantine
            (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,
             season,week,slate,source_player_key,display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
            VALUES (:qid,'player','public','source_snapshot',:key,'nflverse_pfr',
                    :season,:week,'FEATURE_INVENTORY',:key,:name,:team,:position,:reason,'[]'::jsonb,'open',now(),now())
            ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING
        """),dict(qid=qid,key=key,season=_int(row['season']),week=_int(row['week']) if scope['summary_level']=='week' else None,
            name=row.get('pfr_player_name') or row.get('player'),team=row.get(validation['native_team_field']) if validation['native_team_field'] else None,
            position=row.get('position') or row.get('pos'),reason=request['reason']))
        keys.append(dict(source_record_key=key,source_snapshot_id=str(snapshot.snapshot_id),source_sha256=snapshot.content_sha256,
            native_row=index,identity_quarantine_id=qid,reason=request['reason']))
    return dict(status='review_requests_persisted',requests=len(keys),records=keys,
        identity_resolution='None; original display name retained for UI only, never used as join key')
