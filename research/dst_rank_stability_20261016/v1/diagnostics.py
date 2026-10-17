"""Additional uncertainty and score strata, without new fits or selection."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
P=Path(__file__).resolve().parent
f=pd.DataFrame(json.loads((P/'row_predictions.json').read_text()))
result={}
for block,frame in f.groupby('block'):
    result[block]={}
    for arm in ['existing_mae_policy','ensemble','rank_selector']:
        result[block][arm]={}
        for baseline in ['incumbent','flat']:
            candidate=frame[frame.arm.eq(arm)].copy();control=frame[frame.arm.eq(baseline)].copy()
            weeks=sorted(candidate[['season','week']].drop_duplicates().itertuples(index=False,name=None))
            def sums(data):
                rows=[]
                for season,week in weeks:
                    g=data[(data.season==season)&(data.week==week)];e=g.prediction-g.actual
                    rows.append([len(g),abs(e).sum(),(e**2).sum(),e.sum(),g.covered.sum()])
                return np.asarray(rows,float)
            a,b=sums(candidate),sums(control);rng=np.random.default_rng(261016);samples=[]
            def metrics(s):return np.array([s[1]/s[0],np.sqrt(s[2]/s[0]),s[3]/s[0],s[4]/s[0]])
            for _ in range(3000):
                indices=rng.integers(0,len(weeks),len(weeks));samples.append(metrics(a[indices].sum(axis=0))-metrics(b[indices].sum(axis=0)))
            interval=np.quantile(samples,[.025,.975],axis=0);delta=metrics(a.sum(axis=0))-metrics(b.sum(axis=0))
            result[block][arm][baseline]={name:dict(difference=float(delta[i]),ci95=list(map(float,interval[:,i])),week_clusters=len(weeks)) for i,name in enumerate(['mae','rmse','bias','coverage80'])}
strata={}
recent=f[f.block.eq('2026_recent_rolling')]
for name,mask in [('negative_actual',recent.actual<0),('verified_zero',recent.actual==0),('actual_15_plus',recent.actual>=15),('actual_under_15',recent.actual<15)]:
    strata[name]={}
    for arm,g in recent[mask].groupby('arm'):
        e=g.prediction-g.actual;strata[name][arm]=dict(n=len(g),mae=float(abs(e).mean()),bias=float(e.mean()))
(P/'point_uncertainty_and_strata.json').write_text(json.dumps(dict(paired_point_uncertainty=result,recent_strata=strata),indent=2)+'\n')
print('Paired week-cluster point uncertainty and all-arm score strata recorded without refitting')
