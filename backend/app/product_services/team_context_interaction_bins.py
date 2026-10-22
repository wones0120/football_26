"""Observed conditional team responses; no predictive fit or causal interpretation."""
from copy import deepcopy
import math
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .team_market_interactions import build_team_market_interactions,_key
from .offensive_environment_catalog import _count
from .team_decision_catalog_features import _measure

VERSION='team_context_interaction_bins_v1'
CHANNELS=('physical_snaps','called_pass_fraction','official_carries')


def _quantile(values,q):
    if not values:return None
    xs=sorted(values);at=(len(xs)-1)*q;lo=math.floor(at);hi=math.ceil(at)
    return xs[lo]+(xs[hi]-xs[lo])*(at-lo)


def _summary(logs,channel):
    pairs=[(r['condition_value'],r['response'][channel]) for r in logs
        if r['condition_value']is not None and r['response'][channel]is not None]
    n=len(pairs);unknown=len(logs)-n
    mx=math.fsum(x for x,y in pairs)/n if n else None
    my=math.fsum(y for x,y in pairs)/n if n else None
    cross=math.fsum((x-mx)*(y-my) for x,y in pairs) if n else None
    ss=math.fsum((x-mx)**2 for x,y in pairs) if n else None
    return dict(observed_logs=len(logs),known_paired_logs=n,unknown_pairs=unknown,
        known_sample_mean_condition=mx,known_sample_mean_response=my,
        known_sample_centered_cross_sum=cross,known_sample_condition_square_sum=ss,
        known_sample_population_covariance=cross/n if n>=2 else None,
        mean_response=my if not unknown else None,
        population_covariance=cross/n if n>=2 and not unknown else None,
        response_unit='called_pass_fraction' if channel=='called_pass_fraction' else channel,
        condition_unit='market_points',predictive_fit=False)


def _membership(summary,unknown):
    for value in summary.values():
        value['unknown_condition_membership_logs']=unknown
        if unknown:
            value['mean_response']=None
            value['population_covariance']=None
    return summary


def _contrast(a,b):
    av,bv=a['mean_response'],b['mean_response']
    return av-bv if av is not None and bv is not None else None


def build_team_context_interaction_bins(environment,official,markets,*,before_period,reference_before_period):
    # Reuse strict parent/native/time contracts, not its products as a second vote.
    base=build_team_market_interactions(environment,official,markets,before_period=before_period,
        reference_before_period=reference_before_period)
    reference_keys={tuple(k) for k in base['reference']['target_game_team_keys']}
    reference_rows=[r for r in markets['rows'] if (r['game_id'],r['team']) in reference_keys]
    totals=[r['game_total_line'] for r in reference_rows if r['game_total_line']is not None]
    spreads=[abs(r['team_spread_line']) for r in reference_rows if r['team_spread_line']is not None]
    cuts=dict(total_low_q25=_quantile(totals,.25),total_high_q75=_quantile(totals,.75),
        close_abs_spread_q50=_quantile(spreads,.5),quantile_method='linear interpolation at (n-1)*q',
        total_known_reference_rows=len(totals),spread_known_reference_rows=len(spreads),
        reference_before_period=reference_before_period,reference_sha256=base['reference']['sha256'])
    cuts['sha256']=digest(cuts)
    env={(r['game_id'],r['team']):r for r in environment['game_rows']}
    carries={(r['game_id'],r['team']):r['measurements']['official_carries'] for r in official['full_team_denominators']}
    profiles={}
    for row in base['game_rows']:
        gid,team,season,week=_key(row,before_period);native=gid.split('_')
        source=env.get((gid,team));carry=carries.get((gid,team))
        call=_measure(source['metrics']['G02-M01']) if source else None
        response=dict(physical_snaps=float(_count(source['known_offensive_snaps'])) if source and not source['unknown_snap_eligibility'] else None,
            called_pass_fraction=call['value'] if call else None,
            official_carries=float(_count(carry['exact_within_log_count'])) if carry and carry['exact_within_log_count']is not None else None)
        total=row['parents']['game_total_line'];spread=row['parents']['team_spread_line']
        low=total<=cuts['total_low_q25'] if total is not None and cuts['total_low_q25']is not None else None
        high=total>=cuts['total_high_q75'] if total is not None and cuts['total_high_q75']is not None else None
        close=abs(spread)<=cuts['close_abs_spread_q50'] if spread is not None and cuts['close_abs_spread_q50']is not None else None
        log=dict(game_id=gid,period=row['period'],home=team==canonical_team(native[3]),total=total,signed_spread=spread,
            favorite_state='favorite' if spread is not None and spread<0 else 'underdog' if spread is not None and spread>0 else 'pickem' if spread==0 else None,
            high_total=high,low_total=low,close_spread=close,response=response,
            physical_call_exposure=deepcopy(call),official_carry_exposure=deepcopy(carry),
            source_log_present=source is not None,source_parent_before_period=base['parent_before_period'])
        profiles.setdefault((season,team),[]).append(log)
    rows=[]
    for (season,team),logs in sorted(profiles.items()):
        def summarize(items,field):
            mapped=[{**r,'condition_value':r[field]} for r in items]
            return {ch:_summary(mapped,ch) for ch in CHANNELS}
        home=summarize([r for r in logs if r['home']],'total');away=summarize([r for r in logs if not r['home']],'total')
        home_alloc=summarize([r for r in logs if r['home']],'signed_spread');away_alloc=summarize([r for r in logs if not r['home']],'signed_spread')
        metrics={
            'X01-M04':dict(condition='native home/away × continuous intended total',home=home,away=away,
                home_minus_away_covariance={ch:home[ch]['population_covariance']-away[ch]['population_covariance'] if home[ch]['population_covariance']is not None and away[ch]['population_covariance']is not None else None for ch in CHANNELS}),
            'X01-M05':dict(condition='native home/away × continuous signed team spread',home=home_alloc,away=away_alloc,
                home_minus_away_covariance={ch:home_alloc[ch]['population_covariance']-away_alloc[ch]['population_covariance'] if home_alloc[ch]['population_covariance']is not None and away_alloc[ch]['population_covariance']is not None else None for ch in CHANNELS})}
        for mid,flag in (('X01-M06','high_total'),('X01-M07','low_total')):
            groups={state:_membership(summarize([r for r in logs if r[flag]is True and r['favorite_state']==state],'signed_spread'),
                sum((r[flag]is None and r['favorite_state']in {state,None}) or (r[flag]is True and r['favorite_state']is None) for r in logs)) for state in ('favorite','underdog','pickem')}
            unknown=sum(r[flag]is None or r[flag]is True and r['favorite_state']is None for r in logs)
            metrics[mid]=dict(condition=flag+' × signed favorite/underdog',groups=groups,unknown_condition_logs=unknown,
                favorite_minus_underdog_mean={ch:_contrast(groups['favorite'][ch],groups['underdog'][ch]) if not unknown else None for ch in CHANNELS})
        close=summarize([r for r in logs if r['close_spread']is True],'signed_spread')
        large=summarize([r for r in logs if r['close_spread']is False],'signed_spread')
        unknown=sum(r['close_spread']is None for r in logs)
        close=_membership(close,unknown);large=_membership(large,unknown)
        metrics['X01-M08']=dict(condition='absolute signed spread <= frozen reference median vs larger; signed lines retained',
            close=close,large=large,unknown_condition_logs=unknown,
            close_minus_large_mean={ch:_contrast(close[ch],large[ch]) if not unknown else None for ch in CHANNELS})
        rows.append(dict(season=season,team=team,observed_target_game_slots=len(logs),logs=logs,metrics=metrics))
    basis=dict(version=VERSION,before_period=before_period,reference_before_period=reference_before_period,
        parent_before_period=base['parent_before_period'],cutpoints=cuts,reference=base['reference'],rows=rows,
        definitions=dict(response='Observed same-team/season physical snaps, called-pass fraction, official carries',
            eligible_evaluation='Reference boundary <= target period < before_period; missing target log stays unknown',
            total_bins='high >= reference q75; low <= reference q25; ties may meet both independently declared bins',
            context_parents='G19-M01 total; G19-M04 signed spread; native home/away',
            response_parents='G01-M01 physical plays; G02-M01 called-pass decision fraction; official_workload_components.full_team_denominators.official_carries (all rushers)'))
    return dict(**basis,semantic_sha256=digest(basis),source_semantic_hashes=base['source_semantic_hashes'],
        provenance=deepcopy(base['provenance']),evidence_use='postlock_descriptive_not_pregame_or_serving',
        pregame_serving_eligible=False,forecast=None,
        limitations=['Observed conditional summaries, not learned or causal effects or next-game predictions',
            'Small/empty/constant groups may have undefined covariances; no fabricated shrinkage/calibration',
            'Target workload is an observed historical response, never a pregame predictor',
            'Revised archived lines original publication/decision availability unknown; original game completeness unknown'],
        consumer_status='Feature-only observed response; shrinkage/predictive validation/calibration/models/serving pending')
