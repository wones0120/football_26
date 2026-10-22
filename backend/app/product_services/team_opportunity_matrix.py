"""Versioned retrospective/current team-count inputs, separate from FP and preferences.

Historical source verification preserves actual later acquisition clocks. Strict
lagged game periods are not a claim of original historical pregame availability.
"""
from __future__ import annotations
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re

import pandas as pd

from .factual_designation import clock
from .market_snapshots import canonical_team
from .opportunity_events import build_event_evidence
from .opportunity_history_evidence import source_history, team_history
from .workload_count_forecast import _features, FEATURES as LEGACY_FEATURES
from .defense_context_evidence import build_defense_context_evidence, _hash
from .environment_context_evidence import build_environment_context_evidence

VERSION='team_opportunity_matrix_v1'
RAW_FIELDS=('game_id','play_id','season','week','season_type','posteam','defteam','play_type',
    'pass_attempt','rush_attempt','sack','qb_dropback','qb_spike','qb_kneel','qb_scramble','two_point_attempt',
    'epa','yards_gained','yardline_100','rush_touchdown','fixed_drive','qtr','game_seconds_remaining',
    'score_differential','no_huddle','down','passer_player_id','rusher_player_id','receiver_player_id')
METRICS=(('own_pass_call','environment','G02-M01'),('own_neutral_pass','environment','G02-M02'),
    ('own_no_huddle','environment','G01-M06'),('own_clock_start_interval','environment','G01-M04'),
    ('own_redzone_pass','environment','G02-M07'),('opponent_dropback_epa','defense','dropback_epa_support'),
    ('opponent_dropback_success','defense','G14-M09'),('opponent_pass_net20','defense','G14-M07'),
    ('opponent_rush_epa','defense','G15-M02'),('opponent_rush_success','defense','G15-M01'),
    ('opponent_rush_stuff','defense','G15-M04'),('opponent_inside5_rush_td','defense','G15-M09'))
FEATURES=(*LEGACY_FEATURES,'game_total_line','team_spread_line','own_known_snaps_per_observed_log','own_context_games','opponent_context_games',
    *(name+suffix for name,_,_ in METRICS for suffix in ('_mean','_known_exposure','_unknown_eligibility','_unknown_outcomes')))
TARGETS=('pass_attempts','rush_attempts')


def _native(game_id,season,week,team=None,opponent=None):
    if float(season)!=int(season) or float(week)!=int(week):raise ValueError('Nonintegral native period')
    match=re.fullmatch(r'(\d{4})_(\d{2})_([A-Z]{2,3})_([A-Z]{2,3})',str(game_id))
    if not match or (int(match[1]),int(match[2]))!=(int(season),int(week)) or not 1<=int(week)<=18:
        raise ValueError('Native game/period conflict')
    pair={canonical_team(match[3]),canonical_team(match[4])}
    if len(pair)!=2 or (team is not None and team not in pair) or (opponent is not None and pair!={team,opponent}):
        raise ValueError('Native game/team/opponent conflict')
    return pair


def load_retrospective_context(descriptor, *, cutoff, canonical_ids=None, max_bytes=128*1024*1024,max_rows=200000):
    """Verify retained Parquet/manifest bytes, then measure once; no source fetch.

    Descriptor is explicit server-owned path + original manifest entry. Returned
    context is revised retrospective evidence, not a fabricated prelock Snapshot.
    """
    entry=descriptor['manifest'];path=Path(descriptor['path'])
    if not entry.get('url','').startswith('https://github.com/nflverse/nflverse-data/releases/download/pbp/'):
        raise ValueError('Unsupported original PBP source URI')
    if pd.Timestamp(entry['received_at']).tzinfo is None:raise ValueError('Original source receipt clock must be timezone-aware')
    if clock(entry['received_at'])>clock(cutoff):raise ValueError('Historical source acquired after decision')
    if path.stat().st_size>max_bytes or path.stat().st_size!=entry['bytes']:raise ValueError('Historical source byte bound/size mismatch')
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    if h.hexdigest()!=entry['sha256']:raise ValueError('Historical source hash mismatch')
    import pyarrow.parquet as pq
    file=pq.ParquetFile(path)
    if file.metadata.num_rows>max_rows:raise ValueError('Historical row bound exceeded')
    missing=set(RAW_FIELDS)-set(file.schema_arrow.names)
    if missing:raise ValueError('Historical source missing fields: '+','.join(sorted(missing)))
    # Explicit bounded columns; do not materialize unrelated wide provider data.
    columns=list(RAW_FIELDS)+[k for k in ('xpass','pass_oe','no_play','goal_to_go','quarter_end','desc') if k in file.schema_arrow.names]
    rows=file.read(columns=columns).to_pylist();events=[];controls=[];scoped=[];seen=set();seasons=set();excluded=0
    for row in rows:
        row={k:None if isinstance(v,float) and not math.isfinite(v) else v for k,v in row.items()}
        for field in ('passer_player_id','rusher_player_id','receiver_player_id'):
            if row[field] is not None and (not isinstance(row[field],str) or not re.fullmatch(r'00-\d{7}',row[field])):
                raise ValueError('Historical actor requires preserved native GSIS ID')
        if row['season_type']!='REG':excluded+=1;continue
        season=int(row['season']);week=int(row['week']);seasons.add(season)
        pair=_native(row['game_id'],row['season'],row['week'])
        play=Decimal(str(row['play_id']))
        if not play.is_finite() or play!=play.to_integral_value():raise ValueError('Nonintegral native play ID')
        row['play_id']=str(int(play));key=(row['game_id'],row['play_id'])
        if key in seen:raise ValueError('Duplicate native historical event')
        seen.add(key)
        for field in ('posteam','defteam'):
            if row[field] is not None:
                row[field]=canonical_team(row[field])
                if row[field] not in pair:raise ValueError('Historical team contradicts native game')
        if row['posteam'] is not None and row['posteam']==row['defteam']:raise ValueError('Historical offense/defense conflict')
        indicators=('pass_attempt','rush_attempt','sack','qb_dropback','qb_spike','qb_kneel','qb_scramble','two_point_attempt')
        # Retained NFL suspension/resumption bookends are administrative only
        # with the same quiet-indicator proof as quarter/game markers.
        suspension=row['posteam'] is None and (row.get('desc')=='The game has been suspended. Lightning in the area.' or bool(re.fullmatch(r'The game has resumed\. Total delay time of \d+ hours? and \d+ minutes?\.',str(row.get('desc') or ''))))
        administrative=row['play_type'] is None and (row.get('quarter_end')==1 or row.get('desc') in {'GAME','END GAME'} or suspension) and all(row.get(k) in (None,0,False) for k in indicators)
        if row['posteam'] is None:
            if row['play_type'] not in {'kickoff','extra_point','field_goal','punt','no_play'} and not administrative:
                raise ValueError('Unscoped historical offense')
            controls.append(row)
        elif administrative:scoped.append(row)
        else:events.append(row)
    if len(seasons)!=1:raise ValueError('Retrospective source must contain one explicit season')
    season=next(iter(seasons));source=dict(snapshot_id='retrospective:'+h.hexdigest(),content_sha256=h.hexdigest(),
        captured_at=entry['received_at'],received_at=entry['received_at'],source_uri=entry['url'],
        verification='snapshot_artifact_sha256_verified',verification_basis='Original retained Parquet manifest bytes independently hashed; not a historical operational Snapshot',
        full_game_coverage='unverified',game_completion='unverified',historical_availability='later revised capture; original pregame availability unknown')
    receipt=dict(event_evidence=build_event_evidence(events,canonical_ids=canonical_ids or {},source_receipt=source,cutoff=cutoff),
        unscoped_nonoffensive_rows=controls,scoped_administrative_rows=scoped)
    boundary=season*100+19
    return dict(season=season,status='verified_revised_retrospective_context',source=source,
        source_descriptor=deepcopy(descriptor),excluded_not_explicit_regular_rows=excluded,
        defense=build_defense_context_evidence(receipt,before_period=boundary,cutoff=cutoff),
        environment=build_environment_context_evidence(receipt,before_period=boundary,cutoff=cutoff))


def _pool(rows,metric):
    known=sum(r['metrics'][metric]['known_outcome_events'] for r in rows)
    total=sum(r['metrics'][metric]['observed_outcome_sum'] or 0 for r in rows)
    return (total/known if known else None,known,
        sum(r['metrics'][metric]['unknown_eligibility_events'] for r in rows),
        sum(r['metrics'][metric]['unknown_outcome_events'] for r in rows))


def build_team_matrix(weekly, target_games, contexts, *, before_period, cutoff, market_rows=()):
    """Full-source weekly labels + native target schedule + measured contexts.

    No salary pool/preferences accepted. Context acquisition/authentication is
    caller responsibility for current managed artifacts; historical loader above
    verifies retained files. Missing labels remain unscoreable, never zero.
    """
    weekly=source_history(weekly,before_period=before_period+1,cutoff=cutoff)
    games=team_history(weekly);lookup={};sources=[]
    for context in contexts:
        sources.append(deepcopy(context.get('source') or context['defense']['provenance']['source']))
        for kind,teamkey in (('defense','defense_team'),('environment','team')):
            for row in context[kind]['game_rows']:
                key=(kind,row['season'],row['week'],row[teamkey])
                if key in lookup:raise ValueError('Duplicate measured context team/game period')
                _native(row['game_id'],row['season'],row['week'],row[teamkey])
                lookup[key]=row
    market_rows=list(market_rows)
    rows=[];seen=set()
    for target in sorted(target_games,key=lambda r:(r['season'],r['week'],r['game_id'],r['team'])):
        _native(target['game_id'],target['season'],target['week'])
        season=int(target['season']);week=int(target['week']);period=season*100+week
        team=canonical_team(target['team']);opponent=canonical_team(target['opponent']);gid=target['game_id']
        _native(gid,season,week,team,opponent)
        if period>before_period:raise ValueError('Target after matrix forecast period')
        key=(gid,team)
        if key in seen:raise ValueError('Duplicate target team/game')
        seen.add(key)
        history=games.loc[games.team.eq(team)&games.period.lt(period)].sort_values('period')
        legacy=_features(history);features=dict(zip(LEGACY_FEATURES,legacy or [None]*4));selected={}
        for kind,club in (('environment',team),('defense',opponent)):
            selected[kind]=sorted([r for (k,s,w,t),r in lookup.items() if k==kind and s==season and s*100+w<period and t==club],key=lambda r:(r['season'],r['week']))[-8:]
        market=_market_for_target(target,market_rows,cutoff=cutoff,require_current=period==before_period)
        features.update(game_total_line=market['game_total_line'],team_spread_line=market['team_spread_line'])
        own=selected['environment'];opp=selected['defense']
        features.update(own_context_games=len(own),opponent_context_games=len(opp),
            own_known_snaps_per_observed_log=sum(r['known_offensive_snaps'] for r in own)/len(own) if own else None)
        for name,kind,metric in METRICS:
            for suffix,value in zip(('_mean','_known_exposure','_unknown_eligibility','_unknown_outcomes'),_pool(selected[kind],metric)):
                features[name+suffix]=value
        label=games.loc[games.team.eq(team)&games.period.eq(period)]
        if len(label)>1:raise ValueError('Ambiguous official team label')
        labels={k:float(label.iloc[0][k]) if len(label) and pd.notna(label.iloc[0][k]) else None for k in TARGETS}
        # Target-period labels are excluded from live inference even if an input
        # table unexpectedly already contains that period's observed outcomes.
        if period==before_period:labels=dict.fromkeys(TARGETS)
        periods=sorted({r['season']*100+r['week'] for rs in selected.values() for r in rs})
        if any(p>=period for p in periods):raise ValueError('Context leakage into target')
        rows.append(dict(game_id=gid,team=team,opponent=opponent,period=period,features={k:features[k] for k in FEATURES},
            labels=labels,label_status='observed_complete_channels' if all(v is not None for v in labels.values()) else 'unscoreable_or_forward',
            legacy_window='prior3/8 observed team games across seasons, unchanged v1 semantics',legacy_feature_ready=legacy is not None,
            context_window='current-season-only last<=8 observed prior logs',context_periods=periods,
            legacy_periods=history.tail(8).period.astype(int).tolist(),max_context_period=max(periods) if periods else None,
            context_game_ids={k:[r['game_id'] for r in v] for k,v in selected.items()},market_context=market,
            source_quality='revised historical/partial logs; full-game and original pregame availability unverified'))
    result=dict(version=VERSION,before_period=before_period,feature_columns=list(FEATURES),target_columns=list(TARGETS),rows=rows,
        limits=['Observed context is current-season only; legacy count lags preserve existing cross-season window',
            'Revised historical source does not establish original historical pregame availability',
            'Archived pregame/closing lines have revised-history capture, original decision availability unknown; current quotes require strict prelock clocks',
            'No calibrated probabilities/intervals, FP inputs, user preferences or injury role transfers'])
    result['matrix_sha256']=_hash(result)
    result['provenance']=dict(source_descriptors=sources,market_rows=deepcopy(market_rows),
        weekly_history_sha256=hashlib.sha256(weekly.to_json(orient='records').encode()).hexdigest(),
        weekly_source_ids=sorted(set(weekly.source_id.dropna().tolist())) if 'source_id' in weekly else [],actual_decision_cutoff_at=str(cutoff),
        producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    result['provenance']=json.loads(json.dumps(result['provenance'],default=str,allow_nan=False))
    return result


def load_retrospective_markets(descriptor, *, cutoff,max_bytes=8*1024*1024,max_rows=20000):
    """Verified archived nflverse pregame lines; never realized result/total.

    Source raw spread_line is expected HOME margin (positive home favored).
    Canonical home_spread is the conventional wager sign, its negative.
    """
    import pyarrow.parquet as pq
    from zoneinfo import ZoneInfo
    from datetime import datetime
    entry=descriptor['manifest'];path=Path(descriptor['path'])
    if not entry.get('url','').startswith('https://github.com/nflverse/nflverse-data/releases/download/schedules/'):
        raise ValueError('Unsupported archived schedule source')
    if pd.Timestamp(entry['received_at']).tzinfo is None or clock(entry['received_at'])>clock(cutoff):
        raise ValueError('Archived market receipt clock unavailable')
    if path.stat().st_size>max_bytes or path.stat().st_size!=entry['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
        raise ValueError('Archived schedule byte/hash bound mismatch')
    file=pq.ParquetFile(path)
    if file.metadata.num_rows>max_rows:raise ValueError('Archived schedule row bound')
    fields=['game_id','season','week','game_type','home_team','away_team','total_line','spread_line','gameday','gametime']
    if not set(fields)<=set(file.schema_arrow.names):raise ValueError('Archived schedule market schema absent')
    result=[]
    for row in file.read(columns=fields).to_pylist():
        if row['game_type']!='REG':continue
        home=canonical_team(row['home_team']);away=canonical_team(row['away_team'])
        _native(row['game_id'],row['season'],row['week'],home,away)
        parts=row['game_id'].split('_')
        if (canonical_team(parts[2]),canonical_team(parts[3]))!=(away,home):raise ValueError('Archived native home/away orientation conflict')
        total=_finite_line(row['total_line']);margin=_finite_line(row['spread_line'])
        kickoff=None
        if row['gameday'] and row['gametime']:
            kickoff=datetime.fromisoformat(str(row['gameday'])+'T'+str(row['gametime'])).replace(tzinfo=ZoneInfo('America/New_York')).isoformat()
        result.append(dict(game_id=row['game_id'],season=int(row['season']),week=int(row['week']),home_team=home,away_team=away,
            game_total=total,home_spread=-margin if margin is not None else None,kickoff_at=kickoff,
            market_kind='retrospective_archived_pregame_line',source='nflverse_schedules',source_sha256=entry['sha256'],
            actual_received_at=entry['received_at'],original_quote_at=None,
            availability='Later revised archived pregame line; original decision availability unknown',
            sign_transform='canonical home_spread=-source spread_line; source positive means home favored'))
    return result


def _finite_line(value):
    if value is None or isinstance(value,bool):return None
    try:value=float(value)
    except (ValueError,TypeError):return None
    return value if math.isfinite(value) else None


def _market_for_target(target, rows, *, cutoff, require_current=False):
    from .market_snapshots import utc_time
    gid=target['game_id'];team=canonical_team(target['team']);candidates=[]
    for row in rows:
        if row.get('game_id')!=gid:continue
        home=canonical_team(row['home_team']);away=canonical_team(row['away_team'])
        _native(gid,row['season'],row['week'],home,away)
        parts=gid.split('_')
        if (canonical_team(parts[2]),canonical_team(parts[3]))!=(away,home):raise ValueError('Market native home/away orientation conflict')
        if row.get('market_kind')=='retrospective_archived_pregame_line':
            if require_current:continue
            if clock(row['actual_received_at'])>clock(cutoff):raise ValueError('Archived line not acquired at matrix decision')
            if not row.get('source_sha256'):raise ValueError('Archived line lacks original source hash')
            order=clock(row['actual_received_at'])
        else:
            observed=utc_time(row['observed_at']);ingested=utc_time(row['ingested_at']);kickoff=utc_time(row['kickoff_at'])
            if not observed<=ingested<=utc_time(cutoff) or observed>=kickoff or (require_current and utc_time(cutoff)>=kickoff):
                raise ValueError('Current market not captured before decision/lock')
            if not row.get('source_snapshot_id') or not row.get('market_snapshot_id'):raise ValueError('Current market indexed source/snapshot identity missing')
            order=observed
        candidates.append((order,str(row.get('market_snapshot_id') or row.get('source_sha256')),row))
    if not candidates:return dict(status='missing',game_total_line=None,team_spread_line=None,definition='conventional team wager sign: favorite negative')
    row=max(candidates,key=lambda r:r[:2])[2];total=_finite_line(row.get('game_total'));spread=_finite_line(row.get('home_spread'))
    if total is not None and not 20<=total<=80:raise ValueError('Market total outside canonical source sanity bound')
    if spread is not None and abs(spread)>30:raise ValueError('Market spread outside canonical source sanity bound')
    return dict(status='sourced' if total is not None and spread is not None else 'missing_line_component',
        game_total_line=total,team_spread_line=spread if team==row['home_team'] else -spread if spread is not None else None,
        market_kind=row.get('market_kind','captured_pregame_snapshot'),
        definition='conventional team wager sign: favorite negative; no realized score/result input')
