"""Separate official pass/rush/target goal-to-go allocation on matched source windows."""
from copy import deepcopy
import math
from .player_scoring_zone_components import VERSION as INPUT_VERSION,CHANNELS
from .evaluation_record import digest
from .market_snapshots import canonical_team
VERSION='observed_goal_to_go_channel_allocation_v1'


def _count(n):
    if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) or n<0 or int(n)!=n:raise ValueError('Nonnegative known source count required')
    return int(n)


def build_goal_to_go_allocation(parent,*,before_period):
    if parent.get('version')!=INPUT_VERSION or parent.get('before_period')!=before_period or parent.get('pregame_serving_eligible') is not False or parent.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving':raise ValueError('Matched retrospective scoring-zone source required')
    teams={};actors={};groups={}
    for row in parent['full_team_denominators']:
        gid,team=row['game_id'],row['team'];parts=gid.split('_')
        if len(parts)!=4:raise ValueError('Native source game key required')
        try:season,week=int(parts[0]),int(parts[1]);sides={canonical_team(p) for p in parts[2:]}
        except (ValueError,TypeError):raise ValueError('Native source game scope unknown')
        if not 1<=week<=18 or season*100+week>=before_period or team not in sides:raise ValueError('Strict prior native team-game required')
        key=(gid,team)
        if key in teams:raise ValueError('Duplicate native source team-game')
        teams[key]=row;groups.setdefault((season,team),[]).append((week,gid))
    for row in parent['actor_game_rows']:
        key=(row['game_id'],row['team'],row['source_player_id'])
        if key[:2] not in teams or key in actors or not key[2]:raise ValueError('Duplicate/unbound native actor')
        actors[key]=row
    windows=[]
    for (season,team),timeline in sorted(groups.items()):
        timeline=sorted(timeline)
        if len({w for w,_ in timeline})!=len(timeline):raise ValueError('Duplicate source team period')
        for limit in (1,3,8):
            selected=timeline[-limit:];games=[gid for _,gid in selected]
            natives=sorted({native for gid,t,native in actors if t==team and gid in games})
            team_channels={}
            for ch in CHANNELS:
                counters=[teams[(gid,team)]['channels'][ch]['goal_to_go'] for gid in games]
                ds=[_count(c['exact_within_log_count']) if c['exact_within_log_count'] is not None else None for c in counters]
                team_channels[ch]=dict(known_full_team_count=sum(_count(c['counted_lower_bound']) for c in counters),
                    exact_full_team_count=sum(ds) if all(v is not None for v in ds) else None,
                    unknown_eligibility_events=sum(_count(c['unknown_eligibility_events']) for c in counters),
                    known_unattributed_eligible_events=sum(_count(c['unattributed_eligible_events']) for c in counters))
            output=[]
            for native in natives:
                source_rows=[actors.get((gid,team,native)) for gid in games]
                pids={r['player_master_id'] for r in source_rows if r is not None and r['player_master_id'] is not None}
                if len(pids)>1:raise ValueError('Native canonical identity varies within source window')
                metrics={}
                for ch in CHANNELS:
                    evidence=[(r or {}).get('goal_to_go_channel_shares',{}).get(ch) for r in source_rows]
                    counts=[_count(v['numerator']['exact_within_log_count']) if v is not None and v['numerator']['exact_within_log_count'] is not None else None for v in evidence]
                    n=sum(counts) if all(v is not None for v in counts) else None
                    lower=sum(_count(v['numerator']['counted_lower_bound']) for v in evidence if v is not None)
                    denominator=team_channels[ch]['exact_full_team_count']
                    if lower>team_channels[ch]['known_full_team_count'] or (n is not None and denominator is not None and n>denominator):raise ValueError('Actor GTG count exceeds full-team channel budget')
                    metrics[ch]=dict(known_observed_actor_count=lower,exact_actor_count=n,missing_actor_channel_games=[gid for gid,v in zip(games,evidence) if v is None],
                        full_team_denominator=deepcopy(team_channels[ch]),share=n/denominator if n is not None and denominator is not None and denominator>0 else None,
                        zero_denominator=denominator==0)
                output.append(dict(source_player_id=native,player_master_id=next(iter(pids)) if pids else None,channels=metrics))
            for ch in CHANNELS:
                if sum(r['channels'][ch]['known_observed_actor_count'] for r in output)>team_channels[ch]['known_full_team_count']:raise ValueError('Native actor allocation exceeds all-native source budget')
            windows.append(dict(season=season,team=team,window_max_observed_games=limit,observed_games=len(games),native_game_ids=games,latest_observed_week=selected[-1][0],team_channels=team_channels,actors=output))
    basis=dict(version=VERSION,candidate_id='G11-M10',before_period=before_period,windows=windows,
        definition='Separate official pass/rush/target native actor goal-to-go counts over identical observed games divided by compatible all-native team channel GTG counts; pool counts before division')
    return basis|dict(semantic_sha256=digest(basis),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,
        identity_review_requests=deepcopy(parent['identity_review_requests']),
        limitations=['Three-channel family is one feature; no common cross-channel opportunity denominator','Pass and receiver target may represent one physical play; shares never added across channels','Up to1/3/8 source-observed games, not certified complete NFL game history','Missing actor/channel counts unknown, not inactive or zero; known lower counts retained','Unknown eligibility/native attribution masks exact shares; no unallocated donation','GTG overlaps field zones and is not a fourth disjoint zone; no forecast or role-transfer probability'],forecast=None,model_consumed=False,optimizer_consumed=False)


def load_goal_to_go_allocation(ref,*,actual_read_at):
    import hashlib,json
    from pathlib import Path
    from datetime import datetime,UTC
    from .factual_designation import clock
    from . import player_scoring_zone_components as module
    decision=clock(actual_read_at);path=Path(ref['path']).resolve()
    if decision is None or decision>datetime.now(UTC):raise ValueError('Actual nonfuture composition clock required')
    if path.parent!=Path('artifacts/player_scoring_zone_components').resolve() or path.name!=ref['sha256']+'.json' or ref['bytes']>16*1024*1024:raise ValueError('Reviewed managed scoring-zone input required')
    raw=path.read_bytes()
    if len(raw)!=ref['bytes'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Scoring-zone source bytes differ')
    parent=json.loads(raw);p=parent['provenance'];published=clock(p.get('actual_publication_at'))
    if published is None or published>decision:raise ValueError('Scoring-zone publication unavailable/future')
    if p.get('producer_code_sha256')!=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest():raise ValueError('Reviewed scoring-zone producer differs')
    result=build_goal_to_go_allocation(parent,before_period=parent['before_period'])
    result['provenance']=dict(input_ref=deepcopy(ref),original_parent_provenance=deepcopy(p),actual_read_at=decision.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result


def require_feature_use(value,*,purpose):
    if value.get('version')!=VERSION or value.get('pregame_serving_eligible') is not False or purpose!='offline_descriptive':raise ValueError('GTG observed allocation cannot serve forecasts/models/optimizer')
    return value
