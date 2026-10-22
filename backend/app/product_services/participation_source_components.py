"""Historical post-season participation source; never current pregame evidence."""
from collections import Counter
from copy import deepcopy
from datetime import datetime,UTC
from decimal import Decimal,InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import Request,urlopen
import hashlib,io,re
import polars as pl
from .evaluation_record import digest
from .factual_designation import clock
from .market_snapshots import canonical_team

VERSION='participation_source_components_v1'
URL='https://github.com/nflverse/nflverse-data/releases/download/pbp_participation/pbp_participation_{season}.parquet'
DICTIONARY='https://nflreadr.nflverse.com/articles/dictionary_participation.html'
REFERENCE='https://nflreadr.nflverse.com/reference/load_participation.html'
FIELDS=('offense_formation','offense_personnel','defenders_in_box','defense_personnel','number_of_pass_rushers','players_on_play','offense_players','defense_players','n_offense','n_defense','ngs_air_yards','time_to_throw','was_pressure','route','defense_man_zone_type','defense_coverage_type','offense_positions','defense_positions')
NUMBERS={'defenders_in_box':(0,11),'number_of_pass_rushers':(0,11),'n_offense':(0,12),'n_defense':(0,12),'time_to_throw':(0,None),'ngs_air_yards':(None,None)}
MAX_BYTES=64*1024*1024


def _int(v):
    if v is None or isinstance(v,bool):raise ValueError('Integral native key required')
    try:n=Decimal(str(v))
    except InvalidOperation as exc:raise ValueError('Invalid native key')from exc
    if not n.is_finite()or n!=int(n):raise ValueError('Integral native key required')
    return int(n)


def _tokens(v,*,ids):
    if v in (None,''):return None
    values=v if isinstance(v,(list,tuple))else re.split(r'[;,\s]+',v.strip())if isinstance(v,str)else None
    if values is None:return None
    if any(not isinstance(x,str)or not x for x in values):return None
    if ids and (any(not re.fullmatch(r'00-\d{7}',x)for x in values)or len(set(values))!=len(values)):return None
    return list(values)


def _measurement(v,name):
    if v in (None,''):return None,None
    if name=='was_pressure':
        if type(v)is bool:return v,None
        if isinstance(v,str)and v.lower()in {'true','false'}:return v.lower()=='true',None
        try:n=Decimal(str(v))
        except InvalidOperation:return None,'invalid_native_pressure_flag'
        if n.is_finite()and n in (0,1):return bool(n),None
        return None,'invalid_native_pressure_flag'
    if name in NUMBERS:
        if isinstance(v,bool):return None,'boolean_numeric_measurement'
        try:n=Decimal(str(v))
        except InvalidOperation:return None,'unparseable_native_measurement'
        lo,hi=NUMBERS[name]
        if not n.is_finite()or lo is not None and n<lo or hi is not None and n>hi:return None,'invalid_native_measurement'
        if name not in {'time_to_throw','ngs_air_yards'}and n!=int(n):return None,'fractional_native_count'
        return float(n)if name in {'time_to_throw','ngs_air_yards'}else int(n),None
    return deepcopy(v),None


def normalize_participation_rows(records,*,season,max_rows=100000):
    if type(season)is not int or not 2016<=season:raise ValueError('Declared historical season required')
    rows=[];seen=set();coverage=Counter();unknown=Counter();position_issues=[]
    for ordinal,raw in enumerate(records):
        if ordinal>=max_rows:raise ValueError('Participation row bound exceeded')
        gid=raw.get('nflverse_game_id');parts=gid.split('_')if isinstance(gid,str)else []
        if len(parts)!=4 or parts[0]!=str(season)or not parts[1].isdigit()or not 1<=int(parts[1])<=22 or canonical_team(parts[2])==canonical_team(parts[3]):raise ValueError('Native season/game identity differs')
        play=_int(raw.get('play_id'));key=(gid,str(play))
        if play<0 or key in seen:raise ValueError('Duplicate/negative native game-play key')
        seen.add(key)
        if raw.get('season')is not None and _int(raw['season'])!=season:raise ValueError('Supplied native season contradicts game')
        if raw.get('week')is not None and _int(raw['week'])!=int(parts[1]):raise ValueError('Supplied native week contradicts game')
        team=raw.get('possession_team')or None
        if team is not None:
            team=canonical_team(team)
            if team not in {canonical_team(t)for t in parts[2:]}:raise ValueError('Native possession team contradicts game')
        measures={};issues={}
        for name in FIELDS:
            value,error=_measurement(raw.get(name),name)
            if value is not None:coverage[name]+=1
            else:unknown[name]+=1
            measures[name]=value
            if error:issues[name]=error
        scopes={}
        for side in ('offense','defense'):
            ids=_tokens(raw.get(side+'_players'),ids=True);positions=_tokens(raw.get(side+'_positions'),ids=False)
            count=measures['n_'+side]
            valid_ids=ids is not None and (count is None or len(ids)==count)
            proof=valid_ids and positions is not None and len(positions)==len(ids)
            scopes[side]=dict(native_player_ids=ids if valid_ids else None,native_positions=positions if proof else None,
                position_by_native_id=dict(zip(ids,positions))if proof else None,
                status='aligned_native_position_list'if proof else 'unknown_or_mismatched_native_positions',original_player_list=deepcopy(raw.get(side+'_players')),original_position_list=deepcopy(raw.get(side+'_positions')))
            if not valid_ids or positions is not None and not proof:position_issues.append(dict(game_id=gid,play_id=str(play),side=side,reason=scopes[side]['status']))
        left=scopes['offense']['native_player_ids'];right=scopes['defense']['native_player_ids']
        if left is not None and right is not None and set(left)&set(right):
            for side in ('offense','defense'):
                scopes[side].update(native_positions=None,position_by_native_id=None,status='conflicting_cross_side_native_identity')
                position_issues.append(dict(game_id=gid,play_id=str(play),side=side,reason='conflicting_cross_side_native_identity'))
        rows.append(dict(game_id=gid,play_id=str(play),season=season,week=int(parts[1]),native_phase=raw.get('season_type'),
            possession_team=team,original_possession_team=raw.get('possession_team'),measurements=measures,measurement_issues=issues,participant_scopes=scopes,source_row_ordinal=ordinal,
            original_native_fields={k:deepcopy(raw[k])for k in ('nflverse_game_id','old_game_id','play_id','season','week','season_type')if k in raw}))
    rows.sort(key=lambda r:(r['game_id'],int(r['play_id'])))
    basis=dict(version=VERSION,season=season,rows=rows,known_measurement_rows=dict(coverage),unknown_measurement_rows=dict(unknown),native_list_issues=sorted(position_issues,key=lambda r:(r['game_id'],int(r['play_id']),r['side'])))
    semantic={**basis,'rows':[{k:v for k,v in r.items()if k!='source_row_ordinal'}for r in rows]}
    return dict(**basis,semantic_sha256=digest(semantic),evidence_use='historical_postseason_revised_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,
        source_gaps=['Field presence is not non-null coverage; source generations may expose different measurements','2023+FTN participation is published after postseason, not evidence available before those plays','No current2026 participation fallback; native phase/official eligibility require independent PBP join','Native positional lists describe source-reported play participation; no healthy/starter/route assignment inference','No player name joins or canonical attachment in this source adapter'])


def capture_participation_source(service,*,season,slate_lock_at,fetcher=None,max_bytes=MAX_BYTES):
    import nflreadpy
    from nflreadpy.utils_date import get_current_season
    maximum=get_current_season(roster=True)-1
    if type(season)is not int or not 2016<=season<=maximum:raise ValueError('Only installed-provider historical completed seasons supported')
    url=URL.format(season=season)
    headers={}
    if fetcher is None:
        with urlopen(Request(url,headers={'User-Agent':'nflverse/nflreadpy participation feature verification','Accept':'application/octet-stream','Cache-Control':'no-cache'}),timeout=30)as response:
            data=response.read(max_bytes+1);headers={k:response.headers.get(k)for k in ('Date','Last-Modified','ETag','Content-Length')if response.headers.get(k)is not None}
    else:data=fetcher(url)
    if not isinstance(data,bytes)or not 0<len(data)<=max_bytes:raise ValueError('Bounded original Parquet bytes required')
    frame=None;validation_error=None
    try:
        frame=pl.read_parquet(io.BytesIO(data),n_rows=100001)
        if frame.height>100000 or not {'nflverse_game_id','play_id','possession_team'}<=set(frame.columns):validation_error='Native participation schema/row bound differs'
    except Exception as exc:validation_error=type(exc).__name__+': '+str(exc)[:300]
    with TemporaryDirectory()as directory:
        path=Path(directory)/f'pbp_participation_{season}.parquet';path.write_bytes(data)
        return service.capture_file(path,source_system='nflverse_participation',dataset='play_participation',season=season,week=None,slate='historical_feature_sources',
            source_license='CC-BY-SA4.0; FTN Data via nflverse for2023onward; NFL NextGenStats via nflverse for2022earlier',source_uri=url,
            slate_lock_at=slate_lock_at,observation_basis='capture_clock',media_type='application/vnd.apache.parquet',row_count=frame.height if frame is not None and frame.height<=100000 else None,
            metadata=dict(contract_id=VERSION,installed_loader='nflreadpy.load_participation',nflreadpy_version=getattr(nflreadpy,'__version__','unknown'),original_remote_parquet_bytes=True,http_headers=headers,remote_generation_freshness='Unknown; network observation is not original event publication',
                original_sha256=hashlib.sha256(data).hexdigest(),source_columns=frame.columns if frame is not None else [],initial_validation_error=validation_error,provider_generation='FTN'if season>=2023 else 'NFL_NGS',
                publication_policy='2023onward released after postseason; historical original publication clock unknown',dictionary=DICTIONARY,reference=REFERENCE,
                source_snapshot_scope='Full native season including all source phases; not a weekly/pregame snapshot'))


def load_participation_snapshot(snapshot,*,actual_read_at,max_rows=100000,max_bytes=MAX_BYTES):
    from backend.app.services.source_capture import verify_snapshot_artifact
    read=clock(actual_read_at);metadata=snapshot.metadata_json or {}
    if read is None or not read<=datetime.now(UTC):raise ValueError('Actual nonfuture source read required')
    if snapshot.source_system!='nflverse_participation'or snapshot.dataset!='play_participation'or snapshot.media_type!='application/vnd.apache.parquet'or snapshot.source_uri!=URL.format(season=snapshot.season)or metadata.get('contract_id')!=VERSION or metadata.get('installed_loader')!='nflreadpy.load_participation'or metadata.get('original_remote_parquet_bytes')is not True or metadata.get('provider_generation')!=('FTN'if snapshot.season>=2023 else 'NFL_NGS')or metadata.get('original_sha256')!=snapshot.content_sha256:raise ValueError('Indexed native participation source contract differs')
    if not 0<snapshot.byte_count<=max_bytes or clock(snapshot.observed_at)is None or clock(snapshot.captured_at)is None or not clock(snapshot.observed_at)<=clock(snapshot.captured_at)<=read:raise ValueError('Source byte/availability boundary differs')
    verify_snapshot_artifact(snapshot);frame=pl.read_parquet(snapshot.artifact_path)
    if frame.height!=snapshot.row_count or frame.height>max_rows:raise ValueError('Indexed native source row count differs')
    value=normalize_participation_rows(frame.iter_rows(named=True),season=snapshot.season,max_rows=max_rows)
    value['provenance']=dict(snapshot_id=str(snapshot.snapshot_id),source_sha256=snapshot.content_sha256,source_uri=snapshot.source_uri,source_captured_at=clock(snapshot.captured_at).isoformat(),
        source_observed_at=clock(snapshot.observed_at).isoformat(),actual_read_at=read.isoformat(),original_publication_at=None,metadata=deepcopy(metadata),source_columns=frame.columns,
        actual_derived_at=datetime.now(UTC).isoformat(),producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return value


def audit_native_participation_join(block,pbp_rows,*,season):
    """Native game/play match only; unmatched/conflicting rows stay unqualified."""
    if block.get('version')!=VERSION or block.get('season')!=season:raise ValueError('Exact participation source season required')
    pbp={}
    for row in pbp_rows:
        gid=row['game_id'];parts=gid.split('_');play=_int(row['play_id'])
        if len(parts)!=4 or parts[0]!=str(season)or _int(row['season'])!=season or _int(row['week'])!=int(parts[1]):raise ValueError('Native PBP season/game/week contradict')
        key=(gid,str(play))
        if key in pbp:raise ValueError('Duplicate native PBP game/play join')
        team=row.get('posteam')or None
        if team is not None:
            team=canonical_team(team)
            if team not in {canonical_team(t)for t in parts[2:]}:raise ValueError('PBP native possession team contradicts game')
        pbp[key]=dict(native_phase=row.get('season_type'),possession_team=team)
    counts=Counter();issues=[];phase=Counter();matched=[]
    for row in block['rows']:
        key=(row['game_id'],row['play_id']);p=pbp.get(key)
        reason=None
        if p is None:reason='missing_native_PBP_game_play'
        elif p['native_phase']not in {'REG','POST'}:reason='PBP_native_phase_unverified'
        elif row['native_phase']is not None and row['native_phase']!=p['native_phase']:reason='native_phase_conflict'
        elif row['possession_team']is not None and p['possession_team']is not None and row['possession_team']!=p['possession_team']:reason='native_possession_team_conflict'
        if reason:
            counts[reason]+=1;issues.append(dict(game_id=key[0],play_id=key[1],reason=reason))
        else:
            counts['qualified_native_game_play_matches']+=1;phase[p['native_phase']]+=1;matched.append(key)
    return dict(season=season,participation_rows=len(block['rows']),pbp_rows=len(pbp),counts=dict(counts),qualified_phase_counts=dict(phase),
        qualified_native_keys_sha256=digest(sorted(matched)),issues=issues,
        meaning='Exact native key/phase/team consistency only; this does not establish original pregame availability or official physical snap eligibility')
