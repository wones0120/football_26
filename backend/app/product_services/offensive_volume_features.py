"""Prior-only player count inputs from original weekly counts and event measures.

No fit, inference, identity inference or user eligibility filtering occurs here.
The source caller authenticates managed bytes; later-revised evidence remains
retrospective rather than original historical pregame evidence.
"""
from copy import deepcopy
import hashlib
import json
import math
from uuid import UUID

from .factual_designation import clock
from .market_snapshots import canonical_team
from .opportunity_history_evidence import source_history, team_history, CHANNELS
from .player_opportunity_components import VERSION as COMPONENT_VERSION, DEFINITIONS

VERSION = 'player_opportunity_matrix_v1'
ACTIVE_VERSION = 'player_opportunity_matrix_active_games_v2'
METRICS = tuple(sorted(DEFINITIONS))
SHARES = ('target_share','nonkneel_carry_share','signed_air_yard_share','average_target_depth')
WINDOWS = (3,8)
LEGACY_FEATURES = tuple(f'{c}_{s}' for c in CHANNELS for s in ('last','mean3','mean8','share3','known3'))
COMPONENT_FEATURES = tuple(f'event_{m}_{s}{n}' for m in (*METRICS,*SHARES)
    for n in WINDOWS for s in ('mean','known','unknown'))
FEATURES = (*LEGACY_FEATURES,*COMPONENT_FEATURES,'position_QB','position_RB','position_WR','position_TE','position_unknown')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def finite(value):
    if value is None or isinstance(value,bool):return None
    try:value=float(value)
    except (ValueError,TypeError):return None
    return value if math.isfinite(value) else None


def period(game):
    parts=str(game).split('_')
    if len(parts)!=4 or len(parts[0])!=4 or len(parts[1])!=2:
        raise ValueError('Player component native game identity required')
    season,week=int(parts[0]),int(parts[1])
    if not 1<=week<=18 or len({canonical_team(parts[2]),canonical_team(parts[3])})!=2:
        raise ValueError('Invalid player component REG game scope')
    return season*100+week


def _component_index(block, *, cutoff, before_period, usage, consumer_contract=None):
    if block.get('version')!=COMPONENT_VERSION or block.get('forecast') is not None:
        raise ValueError('Original player measurement contract required, not forecast/proxy')
    provenance=block.get('provenance') or {}
    if usage not in {'offline_retrospective_model_inputs','current_inference'}:
        raise ValueError('Explicit player matrix usage required')
    if usage=='current_inference':
        from .player_opportunity_components import require_component_use
        require_component_use(block,purpose='forecast',consumer_contract=consumer_contract)
    retrospective=provenance.get('retrospective_read') or {}
    derived=clock(retrospective.get('actual_derived_at') or provenance.get('actual_derived_at') or provenance.get('decision_cutoff_at'))
    if derived is None or derived>clock(cutoff):raise ValueError('Player measurements unavailable at matrix cutoff')
    if block.get('before_period') is None or block['before_period']>before_period:
        raise ValueError('Component period contains later source scope')
    actors={};games={};native={}
    for row in block['actor_game_rows']:
        p=period(row['game_id']);team=canonical_team(row['team'])
        if p>=block['before_period']:raise ValueError('Component actor contains target/future period')
        if team not in {canonical_team(v) for v in row['game_id'].split('_')[2:]}:
            raise ValueError('Player component team contradicts native game')
        pid=row.get('player_master_id')
        if pid is None:continue  # Full source budgets remain in team rows/provenance.
        pid=str(UUID(str(pid)));key=(pid,team,p)
        if key in actors:raise ValueError('Duplicate canonical player/team/period component')
        nkey=(row['game_id'],team,str(row['source_player_id']))
        if nkey in native and native[nkey]!=pid:raise ValueError('Native player aliases conflict')
        native[nkey]=pid;actors[key]=row
    for row in block['team_denominators']:
        p=period(row['game_id']);team=canonical_team(row['team']);key=(team,p)
        if p>=block['before_period']:raise ValueError('Component team contains target/future period')
        if key in games:raise ValueError('Multiple team component games in one REG week')
        games[key]=row['game_id']
    return actors,games


def _measured(row, metric):
    if row is None:return None
    if metric in SHARES:return finite((row.get('shares') or {}).get(metric))
    # A known attributed lower bound is not a complete observation.
    return finite(((row.get('metrics') or {}).get(metric) or {}).get('exact_within_log_sum'))


def _features(weekly, budgets, component_index, game_index, actor, target_period, *, event_window='team_games'):
    pid=str(UUID(str(actor['player_master_id'])));team=canonical_team(actor['team'])
    prior=weekly.loc[(weekly.player_master_id.astype(str)==pid)&weekly.team.eq(team)&(weekly.period<target_period)].sort_values('period')
    values={};periods=set()
    for channel in CHANNELS:
        for n in WINDOWS:
            subset=prior.tail(n);nums=[finite(v) for v in subset[channel]]
            values[f'{channel}_mean{n}']=sum(nums)/len(nums) if len(nums)==n and all(v is not None for v in nums) else None
            if n==3:
                values[f'{channel}_known3']=sum(v is not None for v in nums)
                ratios=[]
                for row in subset.itertuples():
                    total=budgets.get((team,int(row.period)),{}).get(channel);v=finite(getattr(row,channel))
                    ratios.append(v/total if v is not None and total is not None and total>0 else None)
                values[f'{channel}_share3']=sum(ratios)/3 if len(ratios)==3 and all(v is not None for v in ratios) else None
        values[f'{channel}_last']=finite(prior.iloc[-1][channel]) if len(prior) else None
    team_periods=(sorted(int(p) for p in prior.period) if event_window=='observed_player_games'
        else sorted(p for t,p in game_index if t==team and p<target_period))
    for n in WINDOWS:
        selected=team_periods[-n:];periods.update(selected)
        for metric in (*METRICS,*SHARES):
            measured=[_measured(component_index.get((pid,team,p)),metric) for p in selected]
            known=[v for v in measured if v is not None]
            # Absent team periods and absent actors are unknown, never zero/DNP.
            values[f'event_{metric}_mean{n}']=sum(known)/n if len(selected)==n and len(known)==n else None
            values[f'event_{metric}_known{n}']=len(known)
            values[f'event_{metric}_unknown{n}']=n-len(known)
    feature_position=(actor.get('position') if actor.get('current_inference') else (prior.iloc[-1]['position'] if len(prior) else None))
    positions={p:int(feature_position==p) for p in ('QB','RB','WR','TE')}
    values['position_unknown']=int(feature_position not in positions)
    values.update({f'position_{k}':v for k,v in positions.items()})
    periods.update(int(v) for v in prior.tail(8).period)
    return {k:values[k] for k in FEATURES},sorted(periods)


def build_player_matrix(weekly, components, *, before_period, cutoff, actors=(), team_matrix=None,
                        usage='offline_retrospective_model_inputs',consumer_contract=None,include_historical=True,
                        event_window='team_games'):
    """Build same ordered historical/current inputs; labels never enter features.

    The full weekly universe supplies denominators before any salary/user filter.
    Source rows absent in a game remain unknown. No positive-outcome filtering.
    An optional already-built team matrix contributes its exact prior-only
    numeric features (including sourced markets); its labels are not copied.
    """
    if event_window not in {'team_games','observed_player_games'}:
        raise ValueError('Unknown player event window')
    if isinstance(before_period,bool) or not isinstance(before_period,int) or not 1<=before_period%100<=18:
        raise ValueError('REG forecast period required')
    weekly=source_history(weekly,before_period=before_period,cutoff=cutoff)
    weekly['team']=weekly.team.map(canonical_team)
    if any(not 1<=int(p)%100<=18 for p in weekly.period):raise ValueError('Invalid original REG week')
    ci,gi=_component_index(components,cutoff=cutoff,before_period=before_period,usage=usage,consumer_contract=consumer_contract)
    budgets={(r['team'],int(r['period'])):{c:finite(r[c]) for c in CHANNELS}
             for r in team_history(weekly).to_dict('records')}
    teams={};team_columns=[]
    if team_matrix is not None:
        material={k:v for k,v in team_matrix.items() if k not in {'matrix_sha256','provenance'}}
        if digest(material)!=team_matrix.get('matrix_sha256'):raise ValueError('Team matrix hash mismatch')
        team_columns=list(team_matrix['feature_columns'])
        for row in team_matrix['rows']:
            key=(canonical_team(row['team']),int(row['period']))
            if key in teams:raise ValueError('Duplicate team matrix key')
            if any(p>=row['period'] for p in row.get('context_periods',[])+row.get('legacy_periods',[])):
                raise ValueError('Team context leaks target game')
            teams[key]=row
    rows=[];seen=set()
    targets=[]
    for row in (weekly.loc[weekly.player_master_id.notna()].to_dict('records') if include_historical else []):
        targets.append(dict(player_master_id=str(row['player_master_id']),team=row['team'],position=row['position'],
            period=int(row['period']),labels={c:finite(row[c]) for c in CHANNELS},source_id=row.get('source_id')))
    for actor in actors:
        targets.append({**actor,'period':before_period,'labels':dict.fromkeys(CHANNELS),'source_id':None,'current_inference':True})
    for actor in sorted(targets,key=lambda a:(a['period'],a['team'],a['player_master_id'])):
        pid=str(UUID(str(actor['player_master_id'])));team=canonical_team(actor['team']);p=actor['period'];key=(pid,p)
        if key in seen:raise ValueError('Duplicate canonical target player-game')
        seen.add(key);features,history=_features(weekly,budgets,ci,gi,actor,p,event_window=event_window)
        context=teams.get((team,p));context_periods=[]
        if team_matrix is not None:
            features.update({f'team_{k}':context['features'][k] if context else None for k in team_columns})
            context_periods=sorted(set((context or {}).get('context_periods',[])+(context or {}).get('legacy_periods',[])))
        if any(v>=p for v in history+context_periods):raise ValueError('Player context leaks target game')
        rows.append(dict(player_master_id=pid,team=team,position=actor['position'],period=p,
            game_id=(context or {}).get('game_id') or gi.get((team,p)),features=features,
            labels=actor['labels'],history_periods=history,context_periods=context_periods,
            label_source_id=actor['source_id'],current_inference=p==before_period))
    result=dict(version=ACTIVE_VERSION if event_window=='observed_player_games' else VERSION,before_period=before_period,usage=usage,original_pregame_availability_proven=False,feature_columns=[*FEATURES,*(f'team_{k}' for k in team_columns)],
        target_columns=list(CHANNELS),rows=rows,cohort='All canonical source weekly actors with explicit labels; no positive-outcome/DNP filtering; missing participants remain missing',
        unknown_policy='Original missing measurements stay null; later preprocessing may impute only with explicit train-fitted masks',
        chronology='Strict prior-period features from later-revised source; original historical pregame availability not established')
    result['matrix_sha256']=digest(result)
    result['provenance']=dict(component_semantic_sha256=components.get('semantic_measurements_sha256'),
        component_provenance=deepcopy(components.get('provenance')),
        team_matrix_sha256=team_matrix.get('matrix_sha256') if team_matrix else None,
        actual_matrix_cutoff=clock(cutoff).isoformat(),producer_code_sha256=hashlib.sha256(__import__('pathlib').Path(__file__).read_bytes()).hexdigest())
    return result
