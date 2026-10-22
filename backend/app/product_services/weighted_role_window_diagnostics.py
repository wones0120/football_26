"""Source-log recency weights and effective game support, without a role forecast."""
from copy import deepcopy
import math
from .active_workload_distributions import VERSION as INPUT_VERSION,ROLES
from .evaluation_record import digest
VERSION='observed_weighted_role_window_support_v1'
CHANNELS=('pass_attempts','rush_attempts','targets')
WINDOW=8
HALF_LIFE_LOGS=4


def _summary(values):
    total=sum(values);squares=sum(v*v for v in values)
    return dict(sum_weights_or_weighted_exposure=total,sum_squares=squares,kish_effective_games=total*total/squares if squares>0 else None)


def build_weighted_role_window_diagnostics(parent,*,before_period):
    if parent.get('version')!=INPUT_VERSION or parent.get('before_period')!=before_period or parent.get('pregame_serving_eligible') is not False or parent.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving':raise ValueError('Reviewed retrospective active-workload contract required')
    rows=[];seen=set()
    missing=parent['positive_participants_missing_weekly_rows']
    for actor in parent['rows']:
        season,team,native,pid,role=(actor[k] for k in ('season','team','source_player_id','player_master_id','source_position'))
        key=(season,team,native,role)
        if key in seen:raise ValueError('Duplicate source role-window scope')
        seen.add(key);logs=sorted(actor['logs'],key=lambda r:r['week']);weeks=set();games=set()
        for log in logs:
            week=log['week'];gid=log['native_game_id']
            if type(season)is not int or type(week)is not int or not 1<=week<=18 or season*100+week>=before_period:raise ValueError('Role source logs must be strictly prior REG')
            if week in weeks or gid in games:raise ValueError('Duplicate role-window observed game')
            weeks.add(week);games.add(gid)
        positive_logs=[r for r in logs if r['positive_offensive_participation_proven'] is True][-WINDOW:]
        boundary=positive_logs[0]['week'] if len(positive_logs)==WINDOW else 1
        uncertain=[r for r in logs if r['positive_offensive_participation_proven'] is not True and r['week']>=boundary]
        selected=sorted(positive_logs+uncertain,key=lambda r:r['week']);n=len(selected)
        ranks={r['week']:len(positive_logs)-1-i for i,r in enumerate(positive_logs)}
        unobserved=[m for m in missing if m['season']==season and m['team']==team and m['player_master_id']==pid and pid is not None and m['week']>=boundary and season*100+m['week']<before_period]
        weighted=[]
        for log in selected:
            positive=log['positive_offensive_participation_proven']
            if type(positive)is not bool:raise ValueError('Explicit participation proof required')
            age=ranks.get(log['week']);weight=2**(-age/HALF_LIFE_LOGS) if age is not None else None
            counts={}
            for channel in CHANNELS:
                count=log['counts'][channel]
                if count is not None and (isinstance(count,bool) or not isinstance(count,(int,float)) or not math.isfinite(count) or count<0 or int(count)!=count):raise ValueError('Known official exposure must be nonnegative integer')
                counts[channel]=count
            weighted.append(dict(week=log['week'],native_game_id=log['native_game_id'],known_positive_sample_game_age=age,weight=weight,positive_offensive_participation_proven=positive,counts=counts))
        unknown_participation=sum(not r['positive_offensive_participation_proven'] for r in weighted)
        positive=[r for r in weighted if r['positive_offensive_participation_proven']]
        known_game=_summary([r['weight'] for r in positive]);scope=role in ROLES and team is not None and not unknown_participation and not unobserved
        metrics={}
        for channel in CHANNELS:
            applicable=role in ROLES and (channel!='pass_attempts' or role=='QB')
            values=[r['weight']*r['counts'][channel] for r in positive if r['counts'][channel] is not None]
            unknown_counts=sum(r['counts'][channel] is None for r in positive)
            sample=_summary(values)
            exact=scope and applicable and not unknown_counts
            metrics[channel]=dict(applicable=applicable,known_positive_count_logs=len(values),unknown_count_logs=unknown_counts,
                known_sample=sample if applicable else None,weighted_exposure=sample['sum_weights_or_weighted_exposure'] if exact else None,
                exposure_concentration_effective_games=sample['kish_effective_games'] if exact else None)
        rows.append(dict(season=season,team=team,source_player_id=native,player_master_id=pid,source_position=role,selected_logs=weighted,
            observed_source_logs=n,proven_positive_logs=len(positive),unknown_participation_logs=unknown_participation,
            positive_participant_missing_weekly_rows=deepcopy(unobserved),known_sample_game_support=known_game,
            full_window_sum_weights=known_game['sum_weights_or_weighted_exposure'] if scope else None,full_window_sum_squared_weights=known_game['sum_squares'] if scope else None,
            game_effective_sample_size=known_game['kish_effective_games'] if scope else None,metrics=metrics))
    basis=dict(version=VERSION,candidate_id='X08-M03',before_period=before_period,window_logs=WINDOW,recency_half_life_observed_active_games=HALF_LIFE_LOGS,
        definition='Kish effective positive-participation games and channel exposure-concentration game equivalents under fixed observed-active-game-rank recency weights, same team/season/source role',rows=rows)
    return basis|dict(semantic_sha256=digest(basis),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,
        inherited_unresolved_participation_rows=len(parent.get('unresolved_participation_rows',[])),
        identity_review_requests=deepcopy(parent['identity_review_requests']),participation_identity_review_requests=deepcopy(parent['participation_identity_review_requests']),
        limitations=['Weights predeclared, not fitted; active-game rank differs from elapsed calendar/team games; uncertain dated slots mask full ranks while known-positive sample ranks remain separately described','Positive snaps establish observed participation, not stable role/full game or future participation','Effective game equivalents are concentration diagnostics, not independent attempts or confidence interval sample size','Unknown participation/missing weekly source masks exact support; known samples retained, no DNP zeros','Empty or zero exposure has undefined exposure-concentration ESS; exact zero weighted exposure remains zero'],forecast=None,model_consumed=False,optimizer_consumed=False)


def load_weighted_role_window_diagnostics(ref,*,actual_read_at):
    import hashlib,json
    from pathlib import Path
    from datetime import datetime,UTC
    from .factual_designation import clock
    from . import active_workload_distributions
    actual=clock(actual_read_at)
    if actual is None or actual>datetime.now(UTC):raise ValueError('Actual nonfuture read clock required')
    path=Path(ref['path']).resolve()
    if path.parent!=Path('artifacts/active_workload_distributions').resolve() or ref['bytes']>24*1024*1024:raise ValueError('Managed active-role source path/size required')
    raw=path.read_bytes()
    if len(raw)!=ref['bytes'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Active role source bytes differ')
    parent=json.loads(raw);provenance=parent['provenance'];published=clock(provenance.get('actual_publication_at'))
    if published is None or published>actual:raise ValueError('Active role source publication unavailable/future')
    if provenance.get('producer_code_sha256')!=hashlib.sha256(Path(active_workload_distributions.__file__).read_bytes()).hexdigest():raise ValueError('Reviewed active role producer differs')
    result=build_weighted_role_window_diagnostics(parent,before_period=parent['before_period'])
    result['provenance']=dict(input_ref=deepcopy(ref),original_parent_provenance=deepcopy(provenance),actual_read_at=actual.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result


def require_feature_use(value,*,purpose):
    if value.get('version')!=VERSION or value.get('pregame_serving_eligible') is not False or purpose!='offline_descriptive':raise ValueError('Effective source-window support cannot serve forecasts/models/optimizer')
    return value
