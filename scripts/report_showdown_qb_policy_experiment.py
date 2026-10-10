"""Assemble controlled results, exact rankings and constraint-driven comparisons."""
from pathlib import Path
from collections import Counter
from itertools import combinations
from statistics import mean
import math
import pulp
from scripts.run_showdown_qb_policy_experiment import read,write,solver,POLICIES,TEAM_LIMITS
from scripts.audit_showdown_qb_policy_feasibility import diversity,exposure_report,finite_joint
from backend.app.product_services.showdown_portfolio_selection import candidate_metrics,signature

D=Path('artifacts/showdown_qb_policy_controlled/2026w4-monday-2771d4f1')

def build():
    snapshot=read(D/'prepared_input.json');universe=read(D/'ranked-universe.json');players={str(r['player_id']):r for r in snapshot['player_pool']}
    runs={l:read(D/f'controlled-{l}.json') for l in POLICIES};control=runs['A']['selection_report'];snapshot['control_raw_maxima']={'mean':control['best_mean'],'p90':control['best_p90']}
    rows=universe['rows'];lookup={(r['captain_player_id'],tuple(r['player_ids'])):r for r in rows};policies={}
    for label,run in runs.items():
        report=run['selection_report'];limits=run['selection_kwargs']['player_limits'];captain_limit=run['selection_kwargs']['captain_limit'];selected=run['selected'];n=len(selected)
        thresholds={'mean':report['best_mean'],'p90':report['best_p90']};allow,maximum=POLICIES[label]
        def allowed(row):return (allow or row['captain_position']!='QB') and row['qb_count']<=maximum and max(row['team_counts'].values())<=TEAM_LIMITS.get(label,5)
        def quality(row):return min(row['mean']/thresholds['mean'],row['p90']/thresholds['p90'])
        global_eligible=[r for r in rows if allowed(r) and quality(r)>=.95-1e-8]
        bysig={signature(l) for l in run['candidates']};picked=[]
        for i,lineup in enumerate(selected):
            metrics=candidate_metrics(lineup);row=lookup[signature(lineup)];others=[l for j,l in enumerate(selected) if i!=j]
            counts=Counter(pid for l in others for pid in signature(l)[1]);captains=Counter(signature(l)[0] for l in others);sigs={signature(l) for l in others};skipped=[]
            for alternate in rows:
                if alternate['selector']<=row['selector']+1e-6:continue
                blockers=[]
                if not allow and alternate['captain_position']=='QB':blockers.append('QB construction: Captain forbidden')
                if alternate['qb_count']>maximum:blockers.append('QB construction: too many QBs')
                if max(alternate['team_counts'].values())>TEAM_LIMITS.get(label,5):blockers.append('team-count user preference')
                if quality(alternate)<.95-1e-8:blockers.append('joint quality screen')
                sig=(alternate['captain_player_id'],tuple(alternate['player_ids']))
                if sig in sigs:blockers.append('physical roster already selected')
                for pid in alternate['player_ids']:
                    if counts[pid]+1>limits[pid]:blockers.append('player exposure: '+players[pid]['name'])
                if captains[alternate['captain_player_id']]+1>captain_limit:blockers.append('Captain exposure: '+players[alternate['captain_player_id']]['name'])
                if sig not in bysig:blockers.append('not discovered by this production candidate generator')
                if not blockers:blockers.append('available replacement: inspect joint selector optimization/tolerance')
                skipped.append({'global_rank':alternate['global_rank'],'selector':alternate['selector'],'captain':players[alternate['captain_player_id']]['name'],'blockers':blockers})
            category='raw selector strength' if row['global_rank']<=3 else 'Captain diversification' if row['captain_position']=='QB' else 'exposure diversification'
            if label=='F':category='team-count user preference and exposure diversification'
            picked.append({'entry':i+1,'global_rank':row['global_rank'],'rank_basis':'entire legal A lineup universe before portfolio exposures and policy restrictions',
                **metrics,'captain':players[row['captain_player_id']]['name'],'qb_count':row['qb_count'],
                'players':[{k:r.get(k) for k in ['player_id','name','position','roster_position','player_team','salary','projection','p90']} for r in lineup],
                'policy_quality_fraction':quality(row),'fixed_control_quality_fraction':min(row['mean']/control['best_mean'],row['p90']/control['best_p90']),
                'primary_selection_classification':category,'selection_reason':'Highest portfolio objective from generated qualifying candidates under requested-count player/Captain capacities and physical uniqueness. Scenario coverage disabled.',
                'higher_ranked_skipped':skipped,'production_candidate_rank':next(m['rank'] for m in report['ranked_metrics'] if m['captain_player_id']==row['captain_player_id'] and sorted(x['player_id'] for x in m['players'])==row['player_ids'])})
        # Stage survivors are support in an n-entry portfolio, not standalone filters.
        discovered={signature(l):l for l in run['candidates']};qual=[]
        for sig,l in discovered.items():
            m=candidate_metrics(l)
            if m['baseline_mean']>=.95*thresholds['mean']-1e-8 and m['baseline_p90']>=.95*thresholds['p90']-1e-8:qual.append((sig,l,m))
        def supports(player_caps,cap_cap):
            m=pulp.LpProblem('StageSupport',pulp.LpMaximize);x=[pulp.LpVariable(f'c{i}',cat='Binary') for i in range(len(qual))];m+=pulp.lpSum(x)==n
            for pid in players:
                m+=pulp.lpSum(v for v,(sig,l,metric) in zip(x,qual) if pid in sig[1])<=player_caps.get(pid,n)
                m+=pulp.lpSum(v for v,(sig,l,metric) in zip(x,qual) if pid==sig[0])<=cap_cap
            support=0
            for v in x:
                test=m.copy();test+=v==1
                if test.solve(solver())==pulp.LpStatusOptimal:support+=1
            return support
        stages={'requested':5,'generated':n,'distinct_scenario_candidates':report['candidate_count'],'distinct_physical_signatures':len(discovered),
            'scenario_candidates_passing_quality':report['quality_eligible_count'],'physical_signatures_passing_quality':len(qual),
            'physical_candidates_supported_under_player_exposure':supports(limits,n),
            'physical_candidates_supported_under_player_and_captain_exposure':supports(limits,captain_limit),
            'physical_candidates_supported_with_uniqueness':supports(limits,captain_limit),'survival_portfolio_size_basis':n,
            'full_universe_physical_signatures_passing_quality':len(global_eligible),'final_portfolio_size':n}
        feasible,model=finite_joint(universe,snapshot,label,thresholds,limits,captain_limit,count=n)
        # Optimize rather than just find a feasible witness for this diagnostic.
        exact_model=pulp.LpProblem('GlobalQualityPortfolioSelector',pulp.LpMaximize);x=[pulp.LpVariable(f'x{i}',cat='Binary') for i in range(len(global_eligible))];exact_model+=pulp.lpSum(x)==n
        for pid in players:
            exact_model+=pulp.lpSum(v for v,r in zip(x,global_eligible) if pid in r['player_ids'])<=limits[pid]
            exact_model+=pulp.lpSum(v for v,r in zip(x,global_eligible) if pid==r['captain_player_id'])<=captain_limit
        exact_model+=pulp.lpSum(v*r['selector'] for v,r in zip(x,global_eligible));assert exact_model.solve(solver())==pulp.LpStatusOptimal
        exact_selector=pulp.value(exact_model.objective)
        d=diversity(selected,snapshot);d.update(min_policy_quality=min(r['policy_quality_fraction'] for r in picked),min_fixed_control_quality=min(r['fixed_control_quality_fraction'] for r in picked),fixed_A_95_pass_count=sum(r['fixed_control_quality_fraction']>=.95-1e-8 for r in picked))
        policies[label]={'qb_construction_policy':{'allow_qb_captain':allow,'max_starting_qbs_per_lineup':maximum,'requested_portfolio_size':5,'effective_qb_captain_lineup_limit':1 if allow else 0,'effective_starting_qb_lineup_limit':maximum,'max_players_per_team':TEAM_LIMITS.get(label,5)},
            'football_sha256':run['football_sha256'],'prepared_snapshot_sha256':run['prepared_snapshot_sha256'],'projection_run_id':run['projection_run_id'],'seed':run['seed'],
            'diversity':d,'stage_counts':stages,'selected_lineups':picked,'exposures':exposure_report(selected,snapshot,limits,captain_limit),
            'feasibility':read(D/f'feasibility-{label}.json'),'full_universe_optimal_portfolio_selector':exact_selector,'candidate_coverage_selector_gap':exact_selector-d['portfolio_selector']}
        print(label,stages,'coveragegap',policies[label]['candidate_coverage_selector_gap'],flush=True)
    substitutions=[]
    for selected in policies['A']['selected_lineups']:
        if selected['qb_count']!=2:continue
        source=lookup[(selected['captain_player_id'],tuple(sorted(r['player_id'] for r in selected['players'])))];ids=set(source['player_ids'])
        # Exact same-Captain correspondence, maximize preserved player identities before baseline selector.
        eligible=[r for r in rows if r['qb_count']<=1 and r['captain_player_id']==source['captain_player_id']]
        best=max(eligible,key=lambda r:(len(ids&set(r['player_ids'])),r['selector']))
        substitutions.append({'original':selected,'replacement':best,'method':'same Captain; maximize retained canonical players, then baseline selector over exhaustive ranked universe',
            'removed':[players[p]['name'] for p in ids-set(best['player_ids'])],'added':[players[p]['name'] for p in set(best['player_ids'])-ids],
            'salary_delta':best['salary']-source['salary'],'mean_delta':best['mean']-source['mean'],'p90_delta':best['p90']-source['p90'],'selector_delta':best['selector']-source['selector'],
            'remaining_qb':[players[p]['name'] for p in best['player_ids'] if players[p]['position']=='QB']})
    def construction(run):
        n=len(run['selected']);counts=Counter(r['position'] for l in run['selected'] for r in l)
        return {'positions_per_entry':{p:counts[p]/n for p in ['QB','RB','WR','TE','K','DST']},'punts_3000_or_less_per_entry':sum(float(r.get('base_salary',r['salary']))<=3000 for l in run['selected'] for r in l)/n,
            'same_team_pass_catchers_per_qb':mean(sum(r['player_team']==qb['player_team'] and r['position'] in ['WR','TE'] for r in l) for l in run['selected'] for qb in l if qb['position']=='QB')}
    output={'contract_id':'showdown_qb_policy_controlled_experiment_v1','source_freeze':str(D/'input_freeze.json'),'prepared_snapshot':str(D/'prepared_input.json'),
        'prepared_snapshot_sha256':runs['A']['prepared_snapshot_sha256'],'football_sha256':snapshot['football_sha256'],
        'policies':policies,'comparisons':{'A_to_B_substitutions':substitutions,'A_construction':construction(runs['A']),'B_construction':construction(runs['B']),
        **{f'{a}_to_{b}':{k:policies[b]['diversity'][k]-policies[a]['diversity'][k] for k in ['avg_mean','avg_p90','avg_shared_players','unique_players','unique_captains','max_player_exposure','qb_captain_exposure','two_qb_exposure']} for a,b in [('A','B'),('A','C'),('B','D'),('A','E'),('A','F')]}},
        'historical_replay':read(D/'historical-replay.json'),'universe_method':universe['method'],'feasibility_cross_check':read(D/'feasibility-verification.json')}
    write(D/'experiment.json',output);return output

if __name__=='__main__':build()
