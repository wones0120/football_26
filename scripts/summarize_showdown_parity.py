"""Compare fixed-universe selection semantics without changing any weights."""
from collections import Counter, defaultdict
from copy import deepcopy
from itertools import combinations
from pathlib import Path
import argparse
import json

from backend.app.product_services.showdown_portfolio_selection import candidate_metrics, select_showdown_portfolio
from backend.app.product_services.showdown_single_entry import select_single_entry_lineups
from scripts.audit_showdown_production_parity import read, write
from scripts.compare_showdown_parity_shadows import summary
from scripts.research_showdown_prelock import signature, thesis, joint_portfolio


def live(lineup):
    result=deepcopy(lineup)
    for r in result:r['ownership']=r['diagnostic_ownership']
    result[0]['solver_ownership_weight']=.08
    result[0]['solver_objective_value']-=.08*sum(r['ownership'] for r in result)
    return result


def local_quality(candidates):
    groups=defaultdict(list)
    for l in candidates:groups[l[0].get('showdown_scenario_id') or 'baseline'].append(l)
    return [l for ls in groups.values() for l in ls if
            candidate_metrics(l)['mean']>=.95*max(candidate_metrics(x)['mean'] for x in ls)-1e-8 and
            candidate_metrics(l)['p90']>=.95*max(candidate_metrics(x)['p90'] for x in ls)-1e-8]


def baseline_variants(candidates, common, masked):
    out=[]
    for old in candidates:
        key=signature(old)
        if key not in common:continue
        l=deepcopy(common[key]['baseline'])
        if not masked:l=live(l)
        for r in l:
            r['showdown_scenario_id']=old[0]['showdown_scenario_id']
            r['conditioned_projection']=next(x['projection'] for x in old if x['player_id']==r['player_id'])
            r['conditioned_p90']=next(x['p90'] for x in old if x['player_id']==r['player_id'])
        out.append(l)
    return out


def main(p,research_dir,common_name='common_scored_universe.json',output_name='shadow_comparisons.json'):
    production=read(p/'production_replay.json');common_data=read(p/common_name)
    common={tuple(tuple(x) for x in r['signature']):r['worlds'] for r in common_data['records']}
    research=read(research_dir/'quality_shadow.json')
    ns={};exec(compile((p/'original_showdown_portfolio_selection.py.txt').read_text(),'frozen_legacy_selector','exec'),ns)
    legacy=ns['select_showdown_portfolio']
    kwargs=production['selection_kwargs'];candidates=production['candidates'];results={}
    def solve(label,cs,kw=kwargs,select=legacy):
        chosen,report=select(deepcopy(cs),**kw);results[label]={**summary(chosen),'report':report};return chosen
    solve('A_current',candidates)
    solve('B_baseline_live',baseline_variants(candidates,common,False),select=select_showdown_portfolio)
    solve('B_baseline_masked',baseline_variants(candidates,common,True),select=select_showdown_portfolio)
    local=local_quality(candidates)
    solve('C_scenario_local_then_baseline',baseline_variants(local,common,True),{**kwargs,'quality_fraction':0},select=select_showdown_portfolio)
    # One relaxation per arm, all relative to the exact current five-entry run.
    expanded_worlds=[live(l) for worlds in common.values() for l in worlds.values()]
    solve('relax_universe_only',expanded_worlds)
    solve('relax_quality_floor_only',candidates,{**kwargs,'quality_fraction':0})
    masked=[]
    for l in candidates:
        x=deepcopy(l);own=sum(r.get('ownership') or 0 for r in x)
        x[0]['solver_objective_value']+=x[0]['solver_ownership_weight']*own;x[0]['solver_ownership_weight']=0
        for r in x:r['diagnostic_ownership']=r['ownership'];r['ownership']=None
        masked.append(x)
    solve('relax_ownership_only',masked)
    solve('relax_exposure_caps_only',candidates,{**kwargs,'player_limits':{},'captain_limit':5})
    solve('relax_scenario_restrictions_only',candidates,{**kwargs,'require_scenario_diversity':False})
    # Same common canonical rosters for every three-entry arm. Each arm is
    # scored once on its own fixed world/ownership semantics; no weight tuning.
    fragile={str(r['player_id']) for r in research['prepared_pool'] if
             (r.get('pregame_role_uncertain') and float(r.get('snap_share_mean_3') or 0)<.10) or float(r['salary'])<=1000}
    # Named unresolved watch-list players have no verified offensive role in
    # this immutable morning evidence; they cannot enter the final shadow.
    fragile|={str(r['player_id']) for r in research['prepared_pool'] if
              r['name'] in {'Travis Homer','Jaleel McLaughlin','Germie Bernard','Eli Heidenreich','Blake Whiteheart'}}
    limits={r['player_id']:(3 if r['position']=='QB' else 2 if r['salary']<=1000 else 3) for r in research['prepared_pool']}
    def three(label,cs,normalized=False,quality=True):
        ranked={}
        for l in cs:
            if set(r['player_id'] for r in l)&fragile:continue
            key=signature(l)
            if key not in ranked or candidate_metrics(l)['selector']>candidate_metrics(ranked[key])['selector']:ranked[key]=l
        ls=list(ranked.values());bm=max(candidate_metrics(l)['mean'] for l in ls);bp=max(candidate_metrics(l)['p90'] for l in ls)
        if quality:ls=[l for l in ls if candidate_metrics(l)['mean']>=.95*bm-1e-8 and candidate_metrics(l)['p90']>=.95*bp-1e-8]
        if normalized:
            _,report=select_single_entry_lineups(deepcopy(ls),num_contests=1,report_candidate_limit=None)
            bykey={signature(l):l for l in ls}
            rs=report['all_candidates'];ls=[bykey[tuple(tuple(x) for x in r['signature'])] for r in rs]
            for r,l in zip(rs,ls):r['research_thesis']=thesis(l)
            best=rs[0]['single_entry_score'];pairs=[(r,l) for r,l in zip(rs,ls) if best-r['single_entry_score']<=.10+1e-8]
            rs=[x[0] for x in pairs];ls=[x[1] for x in pairs]
        else:rs=[{'captain_id':candidate_metrics(l)['captain_player_id'],'single_entry_score':candidate_metrics(l)['selector'],'research_thesis':thesis(l)} for l in ls]
        chosen=joint_portfolio(rs,ls,3,different_captains=True,different_theses=True,max_shared=4,exposure_limits=limits)
        results[label]={**summary([ls[i] for i in chosen]),'joint_objective':sum(rs[i]['single_entry_score'] for i in chosen),'eligible_count':len(ls),'quality_screen':quality,'normalized_selector':normalized}
    three('three_current_common',expanded_worlds)
    three('three_masked_conditional_common',[l for ws in common.values() for l in ws.values()])
    three('three_baseline_live_common',[live(ws['baseline']) for ws in common.values()])
    three('three_corrected_common',[ws['baseline'] for ws in common.values()])
    three('three_research_reference_common',[ws['baseline'] for ws in common.values()],normalized=True,quality=False)
    three('three_corrected_production_universe',baseline_variants(candidates,common,True))
    rp={signature(l) for l in research['raw_lineups']};pp={signature(l) for l in candidates}
    source_stats={}
    for r,l in zip(research['all_candidates'],research['raw_lineups']):
        families={s.split(':')[0] for s in r['discovery_sources']}
        for f in families:
            st=source_stats.setdefault(f,{'rosters':0,'research_only':0,'frontier_10':0,'exclusive_10':0,'seconds':0})
            st['rosters']+=1;st['research_only']+=signature(l) not in pp
            if r['quality_loss_vs_a']<=.10+1e-8:
                st['frontier_10']+=1;st['exclusive_10']+=families=={f}
    for a in research['original_attempts']+research['conditional_attempts']:
        source_stats[a['source'].split(':')[0]]['seconds']+=a['seconds']
    write(p/output_name,{'results':results,'source_contributions':source_stats,
        'universe':{'production_scenario_variants':149,'production_rosters':len(pp),'research_rosters':len(rp),'both':len(pp&rp),'production_only':len(pp-rp),'research_only':len(rp-pp),'common_legal':len(common),'rejected':len(common_data['rejected'])},
        'fragile_excluded_ids':sorted(fragile)})
    print(json.dumps({k:{z:v for z,v in r.items() if z in ['count','captains','selector','mean','p90','baseline_mean','baseline_p90','overlap','scenarios','joint_objective','eligible_count']} for k,r in results.items()},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);parser.add_argument('research_dir',type=Path)
    parser.add_argument('--common-name',default='common_scored_universe.json');parser.add_argument('--output-name',default='shadow_comparisons.json')
    a=parser.parse_args();main(a.directory,a.research_dir,a.common_name,a.output_name)
