"""Offline strategy audit. Imports production scorers, never runs jobs or writes DB.

Historical reconstruction is explicitly STRUCTURAL REPLAY. Missing actual labels
remain missing in confirmed metrics; archive-zero results are diagnostic only.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess
from statistics import mean, median
import numpy as np
import pandas as pd
import pulp
from backend.app.product_services.optimizer import (build_showdown_captain_prior,
    apply_showdown_opportunity_gate, _is_high_rushing_qb, _showdown_qb_correlation_multipliers,
    _scale_showdown_qb_bonus_terms, _SATURATED_SHOWDOWN_RULE_IDS, _json_safe,
    OptimizerService, _saturated_showdown_correlation_summary)
from backend.app.product_services.player_context_scoring import score_player_context
from backend.app.product_services.lineup_correlation_scoring import (
    build_lineup_correlation_terms, build_format_specific_terms, score_lineup_correlations)
from backend.app.product_services.rule_library import resolve_strategy_profile
from backend.app.product_services.showdown_game_scenarios import define_game_scenarios, condition_player_pool

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/showdown_strategy_audit'
SOURCE=ROOT/'artifacts/showdown-oracle-dataset-2026-09-28-v2.json'
PROFILE=resolve_strategy_profile(contest_format='showdown',objective='gpp')
VARIANTS=['current','no_prior','weak_prior','mobile_qb_neutral_prior','no_correlation',
          'no_first_catcher','no_additional_catchers','no_bringback','no_concentration','no_script_format',
          'scenario_a','scenario_b']
DTYPE=np.dtype({'names':['ids','cap','teammax','qbs','cpos','gate','strict','mean','p90','scores'],
 'formats':[('u1',6),'u1','u1','u1','u1','u1','u1','<f8','<f8',('<f8',12)],
 'offsets':[0,6,7,8,9,10,11,16,24,32],'itemsize':128})

def read(path):
    d=json.loads(Path(path).read_text());return d.get('payload',d) if isinstance(d,dict) else d
def write(path,d):
    Path(path).write_text(json.dumps(_json_safe(d),indent=2,sort_keys=True,allow_nan=False)+'\n')
def mask(indices):
    v=sum(1<<int(i) for i in indices);return f'{v&((1<<64)-1)} {v>>64}'

def prepare(rows):
    frame=pd.DataFrame([dict(player_id=r['player_id'],name=r['player_name'],position=r['position'],
     player_team=r['team'],opponent_team=r['opponent'],salary=r['flex_salary'],
     projection=r['projected_mean'],p90=r['projected_p90'],game_total_line=r['game_total'],
     team_spread_line=r['team_spread'],team_implied_total=r['team_implied_total'],
     market_context_point_in_time_safe=True, # STRUCTURAL use only; archived market lacks observed-at proof.
     pregame_expected_carries=r['expected_carries'],pregame_expected_targets=r['expected_targets'],
     pregame_expected_snaps=r['expected_snaps'],pregame_expected_routes=r['expected_routes'],
     pregame_role_label='UNKNOWN',pregame_newly_assigned_role=False,
     carries_mean_3=r['expected_carries'],targets_mean_3=r['expected_targets'],
     actual_points=r['actual_points'],actual_source=r['actual_source'],captain_salary=r['captain_salary']) for r in rows])
    assert frame.player_id.is_unique and frame.player_team.nunique()==2
    frame['showdown_qb_eligible']=frame.position!='QB'
    for team,group in frame[frame.position=='QB'].groupby('player_team'):
        top=group[group.salary==group.salary.max()]
        if len(top)==1:frame.loc[top.index,'showdown_qb_eligible']=True
    frame=score_player_context(frame,profile=PROFILE).scored_pool
    _,excluded=apply_showdown_opportunity_gate(frame)
    frame['audit_gate']=~frame.player_id.isin(excluded)
    # A stricter current-role challenger cannot be reconstructed; prior usage is
    # only a proxy and is never claimed to be verified current role.
    frame['audit_strict']=~((frame.salary<=2000)&frame.position.isin(['RB','WR','TE'])&
        (frame.pregame_expected_targets.fillna(0)+frame.pregame_expected_carries.fillna(0)<=0))
    # Production computes its prior after the opportunity/role filters and
    # before the explicit starter filter. Missing historical role filters stay
    # unknown; the reproducible opportunity filter must still precede the prior.
    _,prior=build_showdown_captain_prior(frame.loc[frame.audit_gate].copy(),
        model_path='docs/showdown_captain_model_2024_2025.json',strength=.35)
    probs=prior['position_probabilities']
    frame['captain_position_probability']=frame.position.map(probs).fillna(0)
    frame['captain_objective_multiplier']=.65+.35*np.maximum(.05,frame.captain_position_probability*len(probs))
    multipliers=_showdown_qb_correlation_multipliers(frame)
    frame['qb_correlation_multiplier']=frame.player_id.map(multipliers).fillna(1)
    return frame,prior

def export(frame,path):
    n=len(frame);players=frame.to_dict('records');teams=sorted(frame.player_team.unique())
    scenarios=define_game_scenarios(frame)
    conditioned=[score_player_context(condition_player_pool(frame,s),profile=PROFILE).scored_pool for s in scenarios[1:]]
    while len(conditioned)<2:conditioned.append(frame)
    pair=np.zeros((n,n));cp=pair.copy();cu=np.zeros(n)
    terms=build_lineup_correlation_terms(players,profile=PROFILE)
    terms=[t for t in terms if not any(r.rule_id in _SATURATED_SHOWDOWN_RULE_IDS for r in t.evaluation.triggered_rules)]
    for t in _scale_showdown_qb_bonus_terms(frame,terms):
        if t.kind=='pair':pair[t.left_index,t.right_index]+=t.adjustment;pair[t.right_index,t.left_index]+=t.adjustment
        elif t.kind=='captain_unary':cu[t.left_index]+=t.adjustment
        elif t.kind=='captain_left':cp[t.left_index,t.right_index]+=t.adjustment
        elif t.kind=='captain_right':cp[t.right_index,t.left_index]+=t.adjustment
    fmt=build_format_specific_terms(players,profile=PROFILE)
    fmt=_scale_showdown_qb_bonus_terms(frame,[t for t in fmt if t.kind!='showdown_fragile_punt'])
    with path.open('w') as f:
        f.write(str(n)+'\n')
        for i,r in enumerate(players):
            values=[r['salary'],r['captain_salary'],teams.index(r['player_team']),['QB','RB','WR','TE','K','DST'].index(r['position']),
                round(r['actual_points']*100),int(r['showdown_qb_eligible']),int(r['audit_gate']),int(r['audit_strict']),
                int(_is_high_rushing_qb(r)),r['projection'],r['p90'],r['optimizer_context_ceiling_score'],
                r['captain_objective_multiplier'],r['qb_correlation_multiplier'],
                conditioned[0].iloc[i]['p90'],conditioned[1].iloc[i]['p90']]
            f.write(' '.join(str(v) for v in values)+'\n')
        for arr in [pair,cp,cu]:f.write(' '.join(str(v) for v in arr.flatten())+'\n')
        f.write(str(len(fmt))+'\n')
        for t in fmt:
            group=3 if t.kind in ('showdown_four_two','showdown_five_one') else 4
            f.write(f'{mask(t.required_indexes)} {mask(t.captain_indexes)} {mask(t.absent_indexes)} {t.adjustment} {group} {len(t.count_conditions)} ')
            for ids,lo,hi in t.count_conditions:f.write(f'{mask(ids)} {lo} {hi if hi is not None else n} ')
            f.write('\n')

def pareto_indices(a,idx):
    order=idx[np.lexsort((-a['p90'][idx],-a['mean'][idx]))];keep=[];best=-math.inf
    for i in order:
        if a['p90'][i]>best+1e-8:keep.append(i);best=a['p90'][i]
        elif abs(a['p90'][i]-best)<1e-8 and keep and abs(a['mean'][i]-a['mean'][keep[-1]])<1e-8:keep.append(i)
    return np.array(keep,dtype=int)

def select(a,idx,n,frame,scorecol=0,caps='none',captains=False,overlap=None,soft=False):
    if not len(idx):return [],{'selection_count':0,'pool_truncated':False}
    scores=a['scores'][idx,scorecol]
    idx=idx[np.argsort(-scores,kind='stable')]
    truncated=len(idx)>5000
    if truncated:
        # Retain high ranks and every Captain's strong witnesses. Explicitly report
        # this finite research bound; no unrestricted portfolio-optimality claim.
        chosen=set(idx[:4000]);
        for cap in np.unique(a['cap'][idx]):chosen.update(idx[a['cap'][idx]==cap][:50])
        idx=np.array(sorted(chosen),dtype=int)
    if caps=='none' and not captains and overlap is None and not soft:
        order=idx[np.argsort(-a['scores'][idx,scorecol],kind='stable')][:n]
        return list(map(int,order)),{'selection_count':len(order),'pool_truncated':truncated}
    model=pulp.LpProblem('offline_showdown_audit',pulp.LpMaximize)
    x={int(i):pulp.LpVariable(f'x{i}',cat='Binary') for i in idx}
    score={i:float(a['scores'][i,scorecol]) for i in x}
    penalties=[];counts={j:[i for i in x if j in a['ids'][i]] for j in range(len(frame))}
    for j,indices in counts.items():
        if not indices:continue
        r=frame.iloc[j];cls='qb' if r.position=='QB' else 'punt' if r.salary<=1000 else 'core'
        rate={'qb':1,'punt':.4,'core':.8}[cls]
        if caps=='all' or caps==cls:model+=pulp.lpSum(x[i] for i in indices)<=max(1,math.ceil(n*rate))
        if soft:
            # Pairwise repeat cost proportional to uncertainty, discounted when a
            # high-mean player's removal has high mean replacement regret.
            alternative=frame[(frame.position==r.position)&(frame.player_id!=r.player_id)].projection.max()
            regret=max(0,float(r.projection)-float(alternative if pd.notna(alternative) else 0))
            cost=.05*max(0,float(r.p90)-float(r.projection))/(1+regret)
            for k in range(2,n+1):
                y=pulp.LpVariable(f'repeat{j}_{k}',cat='Binary')
                model+=pulp.lpSum(x[i] for i in indices)<=k-1+n*y
                penalties.append(cost*(k-1)*y)
    for c in np.unique(a['cap'][idx]):
        limit=1 if captains else max(1,math.ceil(n*.6)) if caps in ('all','captain') else n
        model+=pulp.lpSum(x[i] for i in x if a['cap'][i]==c)<=limit
    if overlap is not None:
        for q,i in enumerate(idx):
            for j in idx[q+1:]:
                if len(set(a['ids'][i])&set(a['ids'][j]))>overlap:model+=x[int(i)]+x[int(j)]<=1
    span=2*(sum(abs(v) for v in score.values())+10000)
    model+=span*pulp.lpSum(x.values())+pulp.lpSum(score[i]*x[i] for i in x)-pulp.lpSum(penalties)
    model+=pulp.lpSum(x.values())<=n
    status=model.solve(pulp.PULP_CBC_CMD(msg=False,threads=1,options=['randomSeed 20261005']))
    assert status==pulp.LpStatusOptimal
    selected=sorted((i for i in x if x[i].value()>.5),key=lambda i:-score[i])
    return selected,{'selection_count':len(selected),'pool_truncated':truncated}

def metrics(a,indices,frame,h):
    lineups=[];hist=np.array(h['histogram']);cum=np.cumsum(hist[:,1]);den=h['physical_count'];opt=h['oracle']
    for i in indices:
        ids=list(map(int,a['ids'][i]));cap=int(a['cap'][i]);r=frame.iloc[ids]
        confirmed=all(s!='unavailable' for s in r.actual_source)
        score=float(r.actual_points.sum()+.5*frame.iloc[cap].actual_points)
        # Denominator uses explicitly labeled zero-imputed archive, never a verified DK field.
        pos=np.searchsorted(hist[:,0],score-1e-7,side='left');pct=100*(cum[pos-1] if pos else 0)/den
        lineups.append({'record_index':int(i),'player_ids':list(r.player_id),'captain_id':frame.iloc[cap].player_id,
         'captain_name':frame.iloc[cap]['name'],'captain_position':frame.iloc[cap].position,
         'qb_count':int(a['qbs'][i]),'team_split':dict(Counter(r.player_team)),
         'selector':float(a['scores'][i,0]),'mean':float(a['mean'][i]),'marginal_p90_sum':float(a['p90'][i]),
         'actual_score':score if confirmed else None,'archive_zero_imputed_score':score,
         'missing_label_ids':list(r[r.actual_source=='unavailable'].player_id),
         'archive_zero_imputed_percentile':pct,'verified_physical_percentile':None,
         'archive_regret':opt-score,'actual_optimal_captain_archive':cap in h['optimal_captains']})
    rosters=[set(l['player_ids']) for l in lineups]
    overlap=[len(a&b) for j,a in enumerate(rosters) for b in rosters[j+1:]]
    scores=[r['archive_zero_imputed_score'] for r in lineups]
    return {'generated':len(lineups),'confirmed_lineups':sum(l['actual_score'] is not None for l in lineups),
     'best_archive_score':max(scores) if scores else None,'mean_archive_score':mean(scores) if scores else None,
     'median_archive_regret':median([r['archive_regret'] for r in lineups]) if lineups else None,
     'best_archive_regret':opt-max(scores) if scores else None,'mean_archive_regret':opt-mean(scores) if scores else None,
     'average_shared_identities':mean(overlap) if overlap else None,
     'distinct_captains':len(set(l['captain_id'] for l in lineups)),
     **{f'archive_top_{k}_rate':mean(int(l['archive_zero_imputed_percentile']>=100-k) for l in lineups) if lineups else None for k in [10,5,1]},
     'lineups':lineups}

def structural(slates=None):
    data=read(SOURCE);by=defaultdict(list)
    for r in data['forced_captains']:by[r['season'],r['week'],r['slate']].append(r)
    results=[];seen=set()
    for si,s in enumerate(data['slates']):
        if slates and si>=slates:break
        key=(s['season'],s['week'],s['slate'])
        gamekey=(s['season'],s['week'],tuple(sorted({r['team'] for r in by[key]})))
        if gamekey in seen:continue
        seen.add(gamekey)
        stem='_'.join(map(str,key));dest=OUT/stem;dest.mkdir(exist_ok=True)
        if (dest/'results.json').exists():
            saved=read(dest/'results.json')
            if 'mean_ranker_joint' not in saved['experiments']:
                frame=pd.DataFrame(read(dest/'prepared.json')['players'])
                a=np.fromfile(dest/'universe.bin',dtype=DTYPE);h=read(dest/'histogram.json')
                base=np.flatnonzero((a['gate']==1)&(a['teammax']<=4))
                joint=base[(a['mean'][base]>=.95*h['max_mean'][4]-1e-7)&(a['p90'][base]>=.95*h['max_p90'][4]-1e-7)]
                for name,column in [('mean_ranker_joint','mean'),('p90_ranker_joint','p90')]:
                    chosen=[int(joint[np.argmax(a[column][joint])])]
                    saved['experiments'][name]={**metrics(a,chosen,frame,h),'requested':1,'selection_count':1,
                        'pool_truncated':False,'eligible_retained':len(joint)}
                write(dest/'results.json',saved)
            results.append(saved);continue
        frame,prior=prepare(by[key]);write(dest/'prepared.json',{'players':frame.to_dict('records'),'prior':prior})
        export(frame,dest/'enumeration.txt')
        if not (dest/'universe.bin').exists():subprocess.run([str(OUT/'enumerator'),str(dest/'enumeration.txt'),str(dest/'universe.bin'),str(dest/'histogram.json')],check=True)
        a=np.fromfile(dest/'universe.bin',dtype=DTYPE);h=read(dest/'histogram.json');assert h['record_bytes']==DTYPE.itemsize and len(a)==h['retained_count']
        assert abs(h['oracle']-s['optimal_score'])<.021,(key,h['oracle'],s['optimal_score'])
        base=np.flatnonzero((a['gate']==1)&(a['teammax']<=4))
        k=4;bm=h['max_mean'][k];bp=h['max_p90'][k];joint=base[(a['mean'][base]>=.95*bm-1e-7)&(a['p90'][base]>=.95*bp-1e-7)]
        experiments={}
        def run(label,idx,n=1,col=0,**kwargs):
            selected,extra=select(a,idx,n,frame,scorecol=col,**kwargs)
            experiments[label]={**metrics(a,selected,frame,h),**extra,'eligible_retained':len(idx),'requested':n}
        for t in [5,4,3]:
            for pol in range(4):
                ix=(t-3)*4+pol;idx=np.flatnonzero((a['gate']==1)&(a['teammax']<=t)&((a['qbs']<=1) if pol&1 else True)&((a['cpos']!=0) if pol&2 else True))
                idx=idx[(a['mean'][idx]>=.95*h['max_mean'][ix]-1e-7)&(a['p90'][idx]>=.95*h['max_p90'][ix]-1e-7)]
                run(f'team{t}_qbpolicy{pol}',idx)
        screens={'joint95':joint,'mean95':base[a['mean'][base]>=.95*bm-1e-7],
         'p90_95':base[a['p90'][base]>=.95*bp-1e-7],
         'composite95':base[(a['mean'][base]/bm+a['p90'][base]/bp)/2>=.95-1e-7],
         'pareto':pareto_indices(a,base),'selector_regret95':base[a['scores'][base,0]>=.95*h['max_selector'][k]-1e-7]}
        for fraction in [.94,.93]:screens[f'joint{round(fraction*100)}']=base[(a['mean'][base]>=fraction*bm-1e-7)&(a['p90'][base]>=fraction*bp-1e-7)]
        for name,idx in screens.items():
            for n in [1,2,5]:run(f'screen_{name}_n{n}',idx,n)
        run('mean_ranker_joint',np.array([joint[np.argmax(a['mean'][joint])]]))
        run('p90_ranker_joint',np.array([joint[np.argmax(a['p90'][joint])]]))
        for col,name in enumerate(VARIANTS[:10]):run(f'objective_{name}',joint,col=col)
        # Exposure classes are isolated; 100% QB cap is the no-cap control.
        for n in [1,2,5]:
            for caps in ['none','all','core','punt','qb','captain']:run(f'exposure_{caps}_n{n}',joint,n,caps=caps)
            run(f'exposure_soft_n{n}',joint,n,soft=n>1)
        run('two_different_captains',joint,2,captains=True)
        run('two_different_captains_max4shared',joint,2,captains=True,overlap=4)
        nogate=np.flatnonzero(a['teammax']<=4);nogate=nogate[(a['mean'][nogate]>=.95*bm-1e-7)&(a['p90'][nogate]>=.95*bp-1e-7)]
        run('gate_removed_fixed_benchmark',nogate)
        run('gate_prior_usage_proxy',joint[a['strict'][joint]==1])
        # Discovery breadth is controlled research, not a claim to reproduce the
        # complete run_job generation scheduler from missing historical snapshots.
        baseline=set(base[np.argsort(-a['scores'][base,0])][:25])
        for cap in np.unique(a['cap'][base]):
            fam=base[a['cap'][base]==cap];baseline.add(int(fam[np.argmax(a['scores'][fam,0])]))
        with_scenarios=set(baseline)
        for col in [10,11]:with_scenarios.update(base[np.argsort(-a['scores'][base,col])][:25])
        for label,candidates in [('baseline_discovery',baseline),('scenario_discovery',with_scenarios)]:
            idx=np.array(sorted(set(joint)&candidates),dtype=int)
            for n in [1,2,5]:run(f'{label}_n{n}',idx,n,caps='all')
        result={'key':key,'evidence_class':'STRUCTURAL REPLAY','input_players':len(frame),
         'missing_actual_labels':int((frame.actual_source=='unavailable').sum()),'physical_count':h['physical_count'],
         'structural_count':h['structural_count'],'retained_count':len(a),'oracle_archive':h['oracle'],
         'historical_oracle_match':True,'captain_multipliers':{p:float(g.captain_objective_multiplier.iloc[0]) for p,g in frame.groupby('position')},
         'experiments':experiments}
        write(dest/'results.json',result);results.append(result)
        print(stem,'experiments',len(experiments),'retained',len(a),flush=True)
    write(OUT/'structural_results.json',results)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--limit',type=int);args=parser.parse_args();OUT.mkdir(exist_ok=True);structural(args.limit)
