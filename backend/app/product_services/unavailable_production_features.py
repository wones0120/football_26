"""Historical production held by unavailable actors; never replacement donation."""
from uuid import UUID
import math

from .evaluation_record import digest
from .factual_designation import clock
from .market_snapshots import canonical_team
from .opportunity_history_evidence import source_history
from .player_role_features import VERSION as ROLE_VERSION, KNOWN_POSITIONS

VERSION='unavailable_observed_production_v1'
CHANNELS=('pass_attempts','rush_attempts','targets','receptions','passing_yards','rushing_yards','receiving_yards')
GROUPS={'G17-M09':{'QB','RB','FB','WR','TE'},'G18-M08':{'RB','FB','WR','TE'},'G18-M09':{'RB','FB'}}


def _number(value):
    if value is None or isinstance(value,bool):return None
    try:value=float(value)
    except (ValueError,TypeError):return None
    return value if math.isfinite(value) else None


def build_unavailable_production_features(weekly,roles,*,before_period,cutoff):
    """Three prior observed team games, same team and season, by native units.

    Current unavailability is supplied by the reviewed role-feature contract.
    A historical stat row is not proof of an active full-game role. Values are
    observed reference means, not an OUT player's forecast or recipient volume.
    """
    if type(before_period) is not int or not 2000<=before_period//100<=2200 or not 1<=before_period%100<=18:
        raise ValueError('REG target period required')
    if clock(cutoff) is None:raise ValueError('Actual source cutoff required')
    if (roles.get('version')!=ROLE_VERSION or roles.get('season')*100+roles.get('week')!=before_period
        or clock(roles.get('provenance',{}).get('decision_cutoff_at'))!=clock(cutoff)):
        raise ValueError('Same scoped availability feature boundary required')
    if 'imported_at' not in weekly or weekly.loc[weekly.period<before_period,'imported_at'].isna().any():
        raise ValueError('Original row receipt clocks required')
    rows=source_history(weekly,before_period=before_period,cutoff=cutoff)
    rows=rows.loc[rows.period.ge(before_period//100*100)].copy()
    if any(not 1<=int(p)%100<=18 for p in rows.period):raise ValueError('REG source period required')
    rows['team']=rows.team.map(canonical_team)
    rows['canonical_id']=rows.player_master_id.map(lambda v:str(UUID(str(v))) if v is not None and str(v) not in {'nan','None'} else None)
    if rows.loc[rows.canonical_id.notna()].duplicated(['canonical_id','period']).any():raise ValueError('Duplicate canonical history')
    actors=[];seen=set()
    for actor in roles['players']:
        pid=str(UUID(str(actor['player_master_id'])))
        if pid in seen:raise ValueError('Duplicate canonical role actor')
        if actor['availability_state'] not in {'AVAILABLE','UNAVAILABLE','UNKNOWN'}:raise ValueError('Canonical factual availability state required')
        seen.add(pid);team=actor['team'];team_rows=rows.loc[rows.team.eq(team)]
        periods=sorted(int(p) for p in team_rows.period.unique())[-3:]
        player=team_rows.loc[team_rows.canonical_id.eq(pid)].set_index('period')
        values={};known={}
        for c in CHANNELS:
            nums=[_number(player.loc[p,c]) if p in player.index and c in player else None for p in periods]
            if c=='receptions' and any(v is not None and v<0 for v in nums):raise ValueError('Negative observed reception count')
            complete=len(periods)==3 and all(v is not None for v in nums)
            values[c]=sum(nums)/3 if complete else None
            known[c]=dict(known_games=sum(v is not None for v in nums),unknown_periods=[p for p,v in zip(periods,nums) if v is None])
        actors.append(dict(player_master_id=pid,team=team,position=actor['position'],
            availability_state=actor['availability_state'],reference_periods=periods,
            unavailable_reference=values if actor['availability_state']=='UNAVAILABLE' else None,
            reference_coverage=known if actor['availability_state']=='UNAVAILABLE' else None,
            reference_kind='same_team_prior_observed_counts_not_out_forecast',forecast=None))
    teams=[]
    for team in sorted({a['team'] for a in actors}):
        source_team=next((t for t in roles['teams'] if t['team']==team),{})
        members=[a for a in actors if a['team']==team];metrics={}
        for mid,positions in GROUPS.items():
            selected=[a for a in members if a['position'] in positions]
            unavailable=[a for a in selected if a['availability_state']=='UNAVAILABLE']
            unknown=sum(a['availability_state']=='UNKNOWN' for a in selected)
            unknown_position=sum(a['position'] not in KNOWN_POSITIONS for a in members)
            channels={}
            for c in CHANNELS:
                nums=[a['unavailable_reference'][c] for a in unavailable]
                lower=sum(v for v in nums if v is not None)
                complete=source_team.get('roster_complete') is True and not unknown and not unknown_position and all(v is not None for v in nums)
                channels[c]=dict(exact_unavailable_reference_mean=lower if complete else None,
                    known_actor_reference_sum=lower,known_unavailable_actors=len(nums),
                    missing_unavailable_actor_windows=sum(v is None for v in nums),unknown_current_status_actors=unknown,
                    unknown_position_actors=unknown_position)
            metrics[mid]=dict(channels=channels,variant='same_team_last3_original_weekly_channels',
                unsupported_channels=['routes','touchdowns','scoring_role'],forecast=False)
        teams.append(dict(team=team,metrics=metrics,roster_complete=source_team.get('roster_complete') is True))
    semantic=dict(version=VERSION,before_period=before_period,actors=sorted(actors,key=lambda a:(a['team'],a['player_master_id'])),teams=teams,
        G17_M09_definition='Unavailable actors retain their own historical opportunity reference; no recipient transfer or user exclusion',
        unassigned_opportunity='Reference volume is not automatically donated or assumed fully vacated')
    return {**semantic,'semantic_sha256':digest(semantic),'forecast':None,
        'provenance':dict(decision_cutoff_at=str(cutoff),role_feature_semantic_sha256=roles.get('semantic_measurements_sha256'),
            history_source_ids=sorted(str(v) for v in rows.source_id) if 'source_id' in rows else [],
            original_historical_availability='Not established by current revised sources')}
