"""TIME-SAFE selection-only experiment on a complete saved pre-lock universe.

No generation/refit, live database, or production defaults are changed.
"""
from collections import defaultdict, Counter
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import gzip
import json
import numpy as np
import pandas as pd
from scripts.audit_showdown_strategy import OUT, DTYPE, read, write, select, metrics, pareto_indices
from backend.app.product_services.showdown_portfolio_selection import candidate_metrics
from backend.app.product_services.classic_prospective import digest_payload

SOURCE=Path('artifacts/week4_showdown_production_research_parity/20261001T153239Z')
ACTUAL=Path('artifacts/showdown_qb_policy_controlled/2026w4-monday-2771d4f1/historical-actuals.json')

def main():
    dest=OUT/'time_safe_2026_4_thursday';dest.mkdir(exist_ok=True)
    frozen=read(SOURCE/'production_input_freeze.json');universe=read(SOURCE/'common_scored_universe.json');job=read(SOURCE/'production_job.json')
    kickoff=datetime.fromisoformat('2026-10-02T00:15:00+00:00')
    assert digest_payload(frozen)==universe['input_sha256']
    assert datetime.fromisoformat(job['created_at'])<kickoff
    assert datetime.fromtimestamp((SOURCE/'common_scored_universe.json').stat().st_mtime,timezone.utc)<kickoff
    vals=defaultdict(set)
    for r in read(ACTUAL)['observations']:
        if r['resolution_status']=='resolved' and r['player_id'] and r['actual_points'] is not None:
            vals[r['player_id']].add(round(float(r['actual_points'])/(1.5 if r['roster_position']=='CPT' else 1),5))
    actual={pid:next(iter(v)) for pid,v in vals.items() if len(v)==1}
    frame=pd.DataFrame(frozen['player_pool']).drop_duplicates('player_id').reset_index(drop=True)
    assert set(frame.player_id)<=actual.keys()
    frame['actual_points']=frame.player_id.map(actual);frame['actual_source']='resolved_dk_observation'
    frame['captain_salary']=frame.salary*1.5
    ids={pid:i for i,pid in enumerate(frame.player_id)};teams=sorted(frame.player_team.unique());n=len(frame)
    # Only the DK salary/identity/score denominator is enumerated here.
    with (dest/'enumeration.txt').open('w') as f:
        f.write(str(n)+'\n')
        for _,r in frame.iterrows():
            v=[int(r.salary),int(r.captain_salary),teams.index(r.player_team),['QB','RB','WR','TE','K','DST'].index(r.position),
               round(r.actual_points*100),0,0,0,0,0,0,0,1,1,0,0]
            f.write(' '.join(str(x) for x in v)+'\n')
        for size in [n*n,n*n,n]:f.write(' '.join(['0']*size)+'\n')
        f.write('0\n')
    if not (dest/'histogram.json').exists():
        subprocess.run([str(OUT/'enumerator'),str(dest/'enumeration.txt'),str(dest/'universe.bin'),str(dest/'histogram.json')],check=True)
    h=read(dest/'histogram.json')
    a=np.zeros(len(universe['records']),dtype=DTYPE)
    labels=[]
    for i,record in enumerate(universe['records']):
        lineup=record['worlds']['baseline'];m=candidate_metrics(lineup);cap=next(r for r in lineup if r['roster_position']=='CPT')
        indexes=sorted(ids[r['player_id']] for r in lineup);assert len(indexes)==6 and len(set(indexes))==6
        a['ids'][i]=indexes;a['cap'][i]=ids[cap['player_id']];a['teammax'][i]=max(Counter(r['player_team'] for r in lineup).values())
        a['qbs'][i]=sum(r['position']=='QB' for r in lineup);a['cpos'][i]=['QB','RB','WR','TE','K','DST'].index(cap['position'])
        a['gate'][i]=1;a['strict'][i]=1;a['mean'][i]=m['baseline_mean'];a['p90'][i]=m['baseline_p90']
        groups=[0.0]*5
        for t in (lineup[0].get('lineup_correlation_summary') or {}).get('triggered_rules',[]):
            rule=t['rule_id'];g=0 if 'saturated_1' in rule else 1 if 'saturated_2' in rule or 'saturated_3' in rule else 2 if 'bring_back_team_once' in rule else 3 if t.get('construction_kind') in ['showdown_four_two','showdown_five_one'] else 4
            groups[g]+=float(t.get('objective_contribution') or 0)
        assert abs(sum(groups)-m['correlation'])<1e-5
        score=m['selector'];prior=m['captain_position_prior_contribution']
        a['scores'][i,:10]=[score,score-prior,score-prior*(1-.15/.35),score,score-m['correlation'],score-groups[0],score-groups[1],score-groups[2],score-groups[3],score-groups[3]-groups[4]]
        labels.append(record['research_sources'])
    experiments={}
    def run(label,ix,n=1,col=0,**kwargs):
        selected,extra=select(a,ix,n,frame,scorecol=col,**kwargs);res=metrics(a,selected,frame,h)
        for l in res['lineups']:
            l['verified_physical_percentile']=l.pop('archive_zero_imputed_percentile')
            l['actual_optimal_captain']=l.pop('actual_optimal_captain_archive')
        res['best_actual_score']=res['best_archive_score'];res['mean_actual_score']=res['mean_archive_score']
        res['best_regret']=res['best_archive_regret'];res['mean_regret']=res['mean_archive_regret']
        experiments[label]={**res,**extra,'eligible':len(ix),'requested':n,'selector_sum':float(sum(a['scores'][j,col] for j in selected))}
    base=np.flatnonzero(a['teammax']<=4);bm=max(a['mean'][base]);bp=max(a['p90'][base]);joint=base[(a['mean'][base]>=.95*bm-1e-7)&(a['p90'][base]>=.95*bp-1e-7)]
    for t in [5,4,3]:
        for pol in range(4):
            ix=np.flatnonzero((a['teammax']<=t)&((a['qbs']<=1) if pol&1 else True)&((a['cpos']!=0) if pol&2 else True))
            if len(ix):
                ix=ix[(a['mean'][ix]>=.95*max(a['mean'][ix])-1e-7)&(a['p90'][ix]>=.95*max(a['p90'][ix])-1e-7)]
            run(f'team{t}_qbpolicy{pol}',ix)
    screens={'joint95':joint,'mean95':base[a['mean'][base]>=.95*bm-1e-7],'p90_95':base[a['p90'][base]>=.95*bp-1e-7],
     'joint94':base[(a['mean'][base]>=.94*bm-1e-7)&(a['p90'][base]>=.94*bp-1e-7)],
     'joint93':base[(a['mean'][base]>=.93*bm-1e-7)&(a['p90'][base]>=.93*bp-1e-7)],
     'composite95':base[(a['mean'][base]/bm+a['p90'][base]/bp)/2>=.95-1e-7],
     'pareto':pareto_indices(a,base),'selector_regret95':base[a['scores'][base,0]>=.95*max(a['scores'][base,0])-1e-7]}
    for name,ix in screens.items():
        for n in [1,2,5]:run(f'screen_{name}_n{n}',ix,n)
    run('mean_ranker_joint',np.array([joint[np.argmax(a['mean'][joint])]]))
    run('p90_ranker_joint',np.array([joint[np.argmax(a['p90'][joint])]]))
    for col,label in enumerate(['current','no_prior','weak_prior','unfitted_mobile_adjustment','no_correlation','no_first_catcher','no_additional_catchers','no_bringback','no_concentration','no_script_format']):
        if col!=3:run('objective_'+label,joint,col=col)
    for n in [1,2,5]:
        for caps in ['none','all','core','punt','qb','captain']:run(f'exposure_{caps}_n{n}',joint,n,caps=caps)
        run(f'exposure_soft_n{n}',joint,n,soft=n>1)
    run('two_different_captains',joint,2,captains=True)
    run('two_different_captains_max4shared',joint,2,captains=True,overlap=4)
    production=np.array([i for i,r in enumerate(universe['records']) if r['production']],dtype=int)
    baseline=np.array([i for i,s in enumerate(labels) if any(not ('scenario' in str(x) or 'decisive' in str(x) or str(x).startswith('conditional_exact:')) for x in s)],dtype=int)
    for label,ix in [('production_archive',production),('research_baseline_archive',baseline),('all_discovery_archive',np.arange(len(a)))]:
        # Fixed common benchmarks isolate discovery coverage from changing screens.
        ix=np.array(sorted(set(ix)&set(joint)),dtype=int)
        for n in [1,2,5]:run(f'{label}_n{n}',ix,n,caps='all')
    from backend.app.product_services.showdown_portfolio_selection import select_showdown_portfolio, signature
    candidates=[universe['records'][i]['worlds']['baseline'] for i in base]
    limits={r.player_id:max(1,__import__('math').ceil(5*(1 if r.position=='QB' else .4 if r.salary<=1000 else .8))) for _,r in frame.iterrows()}
    selected,report=select_showdown_portfolio(candidates,requested=5,player_limits=limits,captain_limit=3)
    actualsignatures={signature(l) for l in selected}
    expected={(r['captain_id'],tuple(sorted(r['player_ids']))) for r in experiments['exposure_all_n5']['lineups']}
    assert actualsignatures==expected,'Research portfolio selector must match production'
    # The single-entry blend is a distinct production selector; compare it on
    # exactly the same archived candidates, without claiming generation parity.
    from backend.app.product_services.showdown_single_entry import select_single_entry_lineups
    blended,_=select_single_entry_lineups([universe['records'][i]['worlds']['baseline'] for i in joint],num_contests=1)
    target=signature(blended[0]);bi=next(i for i in joint if signature(universe['records'][i]['worlds']['baseline'])==target)
    run('single_entry_blend_joint',np.array([bi]))
    field=[]
    for path in Path('artifacts/showdown_qb_construction/inputs').glob('*.json.gz'):
        standings=json.load(gzip.open(path,'rt'));contest=standings['contest']
        if (contest.get('season'),contest.get('week'),contest.get('slate_id'))!=(2026,4,'THURSDAY_NIGHT'):continue
        points=[(float(r['entry_points']),int(r['n'])) for r in standings['entries'] if r['entry_points'] is not None]
        count=sum(n for s,n in points)
        field.append({'contest_id':contest['contest_id'],'loaded_entries':count,'reported_field_size':contest['field_size'],
         'score_percentiles':{k:[100*sum(n for score,n in points if score<l['actual_score']-1e-7)/count for l in experiments[k]['lineups']]
          for k in ['objective_current','objective_no_prior','two_different_captains_max4shared','mean_ranker_joint','p90_ranker_joint','single_entry_blend_joint']}})
    from scipy.stats import spearmanr
    actual_scores=np.array([sum(actual[frame.iloc[int(j)].player_id]*(1.5 if j==row['cap'] else 1) for j in row['ids']) for row in a])
    rank_correlations={key:float(spearmanr(values[base],actual_scores[base]).statistic)
       for key,values in {'mean':a['mean'],'p90_sum':a['p90'],'selector':a['scores'][:,0],'selector_no_prior':a['scores'][:,1]}.items()}
    write(dest/'results.json',{'evidence_class':'TIME-SAFE','scope':'selection-only; saved prelock generation; historical numeric objective ablations',
     'season':2026,'week':4,'slate':'THURSDAY_NIGHT','matchup':'PIT/CLE','candidate_count':len(a),'input_players':len(frame),
     'actual_labels_complete':True,'physical_count':h['physical_count'],'oracle':h['oracle'],
     'prelock_job_created_at':job['created_at'],'kickoff':kickoff.isoformat(),'input_sha256':universe['input_sha256'],
     'candidate_sha256':hashlib.sha256((SOURCE/'common_scored_universe.json').read_bytes()).hexdigest(),
     'production_selector_parity':True,'rank_correlations':rank_correlations,
     'mean_p90_spearman':float(spearmanr(a['mean'][base],a['p90'][base]).statistic),
     'observed_field_percentiles':field,'experiments':experiments})
    print('TIME-SAFE',len(a),'physical',h['physical_count'],'oracle',h['oracle'],flush=True)

if __name__=='__main__':main()
