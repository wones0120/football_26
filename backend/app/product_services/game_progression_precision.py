"""Pure numerical MC precision checks, never forecast-quality acceptance."""
import hashlib
import numpy as np

VERSION='regulation_progression_mc_precision_v1'
SEEDS=(17,731)
BATCHES=(256,1024,4096)
TOLERANCES={'official_pass_attempts':.5,'official_carries':.5,'official_targets':.5,'physical_plays':.75,'team_real_points':.5,'passing_yards':5.,'rushing_yards':5.,'passing_TD':.05,'rushing_TD':.05,'possessions':.15}


def select_precision_games(finalized_games):
    """One minhash native key/week, before outcomes; never replace unsupported."""
    byweek={w:set()for w in range(1,6)}
    for g in finalized_games:
        gid=g['game_id'];parts=gid.split('_')
        if len(parts)!=4 or parts[0]!='2026'or int(parts[1])!=g['week']:raise ValueError('Exact2026native game/week required')
        if g.get('independently_finalized')is True and g['week']in byweek:byweek[g['week']].add(gid)
    return [dict(week=w,game_id=min(ids,key=lambda gid:hashlib.sha256(('pilot_precision_v1|'+gid).encode()).hexdigest())if ids else None,status='SELECTED_NO_SUBSTITUTION'if ids else'NO_INDEPENDENT_FINAL_KEY')for w,ids in byweek.items()]


def evaluate_precision(draws,statuses):
    """Arrays are paired [path,team,metric] under the fixed ordered keys.

    Every path must complete with known full-law support. Unknown paths cannot
    be discarded or replaced by zeros to obtain a smaller standard error.
    """
    arrays={};counts=set();unknown=[]
    for seed in SEEDS:
        arrays[seed]={}
        for arm in('contextual','control'):
            x=np.asarray(draws[seed][arm],float);st=statuses[seed][arm]
            if x.ndim!=3 or x.shape[1:]!=(2,len(TOLERANCES))or len(st)!=len(x):raise ValueError('Exact paired path/team/metric arrays and statuses required')
            counts.add(len(x));arrays[seed][arm]=x
            unknown.extend(dict(seed=seed,arm=arm,path=i,status=s['status'])for i,s in enumerate(st)if s['status']!='COMPLETE_REGULATION'or s['full_law_known']is not True)
    if len(counts)!=1 or next(iter(counts))not in BATCHES:raise ValueError('Equal fixed cumulative batches required')
    n=next(iter(counts));base=dict(version=VERSION,n_per_seed_arm=n,seeds=list(SEEDS),ordered_metrics=list(TOLERANCES),forecast_quality_assessed=False,tail_calibration_assessed=False,activation=False)
    if unknown:return dict(**base,status='UNKNOWN_INCOMPLETE_OR_FULL_LAW_SUPPORT',unknown_paths=unknown,precision_pass=False)
    if any(not np.isfinite(x).all()for a in arrays.values()for x in a.values()):raise ValueError('Nonfinite generated metric')
    previous=None if n==256 else 256 if n==1024 else 1024;checks={};all_pass=n>=1024
    for arm in('contextual','control','paired_context_minus_control'):
        xs={s:arrays[s][arm]if arm!='paired_context_minus_control'else arrays[s]['contextual']-arrays[s]['control']for s in SEEDS}
        for side in(0,1):
            for j,(metric,tolerance)in enumerate(TOLERANCES.items()):
                stats={};passing=True
                for seed,x in xs.items():
                    values=x[:,side,j];mean=float(values.mean());halfwidth=float(1.96*values.std(ddof=1)/np.sqrt(n));change=None if previous is None else float(abs(mean-values[:previous].mean()))
                    passed=halfwidth<=tolerance and(change is None or change<=tolerance);passing &= passed
                    stats[str(seed)]=dict(mean=mean,mc95_halfwidth=halfwidth,previous_batch=previous,previous_mean_change=change,pass_seed_mc_and_batch=passed)
                difference=abs(stats['17']['mean']-stats['731']['mean']);passing &= difference<=tolerance;all_pass &= passing
                checks[f'{arm}|team{side}|{metric}']=dict(tolerance=tolerance,seeds=stats,cross_seed_mean_difference=difference,pass_numeric_checks=passing)
    return dict(**base,status='MC_MEAN_PRECISION_PASS_NOT_FORECAST_QUALITY'if all_pass else'PRECISION_NOT_ESTABLISHED',precision_pass=bool(all_pass),minimum1024_achieved=n>=1024,checks=checks,next_fixed_batch=BATCHES[BATCHES.index(n)+1]if not all_pass and n<4096 else None,interval_interpretation='Approximate MonteCarlo standard-error only; not predictive interval calibration')
