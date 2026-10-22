"""Verified retained team-only PBP contexts for descriptive market interactions."""
from copy import deepcopy
from datetime import datetime,UTC
from decimal import Decimal
import hashlib,math,re
from pathlib import Path
from .factual_designation import clock
from .market_snapshots import canonical_team
from .team_opportunity_matrix import RAW_FIELDS,_native
from .opportunity_events import build_event_evidence
from .environment_context_evidence import build_environment_context_evidence
from .official_workload_components import build_official_workload_components
from .team_context_interaction_bins import build_team_context_interaction_bins,_summary
from .evaluation_record import digest

VERSION='historical_team_interaction_context_v1'
INDICATORS=('pass_attempt','rush_attempt','sack','qb_dropback','qb_spike','qb_kneel','qb_scramble','two_point_attempt')


def load_historical_team_interaction_context(descriptor,*,before_period,cutoff,max_bytes=128*1024*1024,max_rows=200000):
    """Exact immutable retained bytes, native teams, no player attachment or fit."""
    entry=descriptor['manifest'];path=Path(descriptor['path']);read=clock(cutoff)
    match=re.fullmatch(r'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_(\d{4})\.parquet',entry.get('url',''))
    if not match or read is None or type(before_period)is not int or not 4<before_period%100<=18 or int(match[1])!=before_period//100:
        raise ValueError('Explicit same-season bounded prior REG source required')
    received=clock(entry['received_at'])
    if received is None or received>read or read>datetime.now(UTC):raise ValueError('Actual source receipt/read clocks required')
    if path.stat().st_size!=entry['bytes'] or path.stat().st_size>max_bytes:raise ValueError('Historical source byte size/bound differs')
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    if h.hexdigest()!=entry['sha256']:raise ValueError('Historical retained source hash differs')
    import pyarrow.parquet as pq
    file=pq.ParquetFile(path);available=set(file.schema_arrow.names)
    if file.metadata.num_rows>max_rows or not set(RAW_FIELDS)<=available:raise ValueError('Historical native schema/row bound differs')
    columns=list(RAW_FIELDS)+[k for k in ('no_play','goal_to_go','quarter_end','desc','xpass','pass_oe') if k in available]
    events=[];controls=[];seen=set();excluded_phase=excluded_period=0
    for row in file.read(columns=columns).to_pylist():
        row={k:None if isinstance(v,float) and not math.isfinite(v) else v for k,v in row.items()}
        if row['season_type']!='REG':excluded_phase+=1;continue
        if row['season']!=int(match[1]):raise ValueError('Native source season contradicts original URI')
        pair=_native(row['game_id'],row['season'],row['week'])
        play=Decimal(str(row['play_id']))
        if not play.is_finite() or play!=play.to_integral_value():raise ValueError('Integral native play key required')
        row['play_id']=str(int(play));key=(row['game_id'],row['play_id'])
        if key in seen:raise ValueError('Duplicate native historical event')
        seen.add(key)
        for field in ('posteam','defteam'):
            if row[field]is not None:
                row['native_'+field]=row[field];row[field]=canonical_team(row[field])
                if row[field]not in pair:raise ValueError('Native team contradicts source game')
        if row['posteam']is not None and row['posteam']==row['defteam']:raise ValueError('Offense and defense conflict')
        for field in ('passer_player_id','rusher_player_id','receiver_player_id'):
            if row[field]is not None and (not isinstance(row[field],str) or not re.fullmatch(r'00-\d{7}',row[field])):
                raise ValueError('Native actor ID required; no names')
        if row['season']*100+row['week']>=before_period:excluded_period+=1;continue
        suspension=row['posteam']is None and (row.get('desc')=='The game has been suspended. Lightning in the area.' or bool(re.fullmatch(r'The game has resumed\. Total delay time of \d+ hours? and \d+ minutes?\.',str(row.get('desc')or''))))
        admin=row['play_type']is None and (row.get('quarter_end')==1 or row.get('desc')in {'GAME','END GAME'} or suspension) and all(row.get(k)in (None,0,False) for k in INDICATORS)
        if row['posteam']is None:
            if row['play_type']not in {'kickoff','extra_point','field_goal','punt','no_play'} and not admin:raise ValueError('Unknown unscoped historical offense')
            controls.append(row)
        elif admin:controls.append(row)
        else:events.append(row)
    source=dict(snapshot_id='retained_manifest:'+h.hexdigest(),content_sha256=h.hexdigest(),captured_at=received.isoformat(),received_at=received.isoformat(),
        source_uri=entry['url'],verification='snapshot_artifact_sha256_verified',verification_basis='Original retained Parquet/manifest bytes verified, not historical operational Snapshot',
        full_game_coverage='unverified',game_completion='unverified',historical_availability='later revised capture; original pregame availability unknown')
    evidence=build_event_evidence(events,canonical_ids={},source_receipt=source,cutoff=read)
    parent=dict(event_evidence=evidence,unscoped_nonoffensive_rows=controls)
    env=build_environment_context_evidence(parent,before_period=before_period,cutoff=read)
    official=build_official_workload_components(parent,before_period=before_period,cutoff=read,position_evidence=())
    official.update(evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False)
    proof=dict(original_source_descriptor=deepcopy(descriptor),actual_read_at=read.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),
        loader_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),source_rows=file.metadata.num_rows,
        scoped_event_rows=len(events),retained_controls=len(controls),excluded_not_REG_rows=excluded_phase,excluded_at_or_after_period=excluded_period,
        control_rows_sha256=digest(controls),identity_scope='Native team-grain metrics; no individual canonical player attachment attempted; all native/unmapped actors retained in team budgets',
        source_scope='Explicit REG games strictly before boundary; not all season games or proof of complete logs')
    return dict(version=VERSION,before_period=before_period,environment=env,official=official,provenance=proof,
        evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False)


def compose_historical_team_interactions(context,markets,*,reference_before_period):
    if context.get('version')!=VERSION or context.get('pregame_serving_eligible')is not False:raise ValueError('Verified offline team context required')
    result=build_team_context_interaction_bins(context['environment'],context['official'],markets,
        before_period=context['before_period'],reference_before_period=reference_before_period)
    for row in result['rows']:
        for mid,field,channel in (('X01-M01','total','physical_snaps'),('X01-M02','signed_spread','called_pass_fraction'),('X01-M03','implied_points','official_carries')):
            logs=[]
            for raw in row['logs']:
                log=deepcopy(raw);log['implied_points']=(log['total']-log['signed_spread'])/2 if log['total']is not None and log['signed_spread']is not None else None
                log['condition_value']=log[field];logs.append(log)
            row['metrics'][mid]=dict(condition_field=field,response_channel=channel,observed_response=_summary(logs,channel),
                interpretation='Observed continuous paired moments only, not a fitted response function or pregame predictor')
    result['version']='historical_team_market_responses_v1'
    result['definitions']['continuous_observed_responses']={
        'X01-M01':dict(condition='intended total',response='observed physical snaps',unit='physical_snaps_x_market_points'),
        'X01-M02':dict(condition='signed team spread',response='observed per-game called-pass fraction',unit='called_pass_fraction_x_signed_market_points'),
        'X01-M03':dict(condition='team implied points',response='observed official full-team carries',unit='official_carries_x_market_points')}
    result['provenance'].update(historical_context=deepcopy(context['provenance']))
    result['semantic_sha256']=digest({k:v for k,v in result.items() if k not in {'provenance','semantic_sha256'}})
    return result
