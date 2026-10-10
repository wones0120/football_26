"""Exploratory offline Classic environment research, never production parameters.

Reads hash-verified study exports, rank archives and a read-only DB supplement.
Linear probability associations have no entry-level significance claims; report
whole-slate variation and leave-one-slate-out instability, never fitted strategy.
"""
from __future__ import annotations
import csv,gzip,hashlib,io,json,math,sys,zipfile
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.analyze_classic_historical_study import build_players,market_frame,SLOTS, norm

BASE=ROOT/'artifacts/classic_historical_study'
OUT=ROOT/'artifacts/classic_game_environment_review'
POPS=('field','top_10','top_5','top_1')
FEATURES=('offensive_game_total','offensive_team_implied','dst_opponent_implied','high_total_rb_count',
          'salary_thousands','mean_projection_sum','marginal_p90_sum','rb_count','te_count',
          'qb_pass_catchers','bring_backs','distinct_offensive_games','rb_salary_thousands','rb_mean_sum','rb_p90_sum')

def verified_json(name,manifest):
    path=BASE/name
    assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest[str(path.relative_to(ROOT))],name
    return json.loads(path.read_text())

def raw_top5(study,inventory,archives):
    sid=study['contest']['source_file_id'];source=next(s for s in inventory['sources'] if s['source_file_id']==sid)
    choices=[a for a in archives if sid in a['registered_source_ids'] and Path(a['path']).exists()]
    if not choices:return None,{'status':'unavailable','reason':'No hash-linked raw rank archive'}
    a=sorted(choices,key=lambda a:a['path'])[0]; path=Path(a['path'])
    assert hashlib.sha256(path.read_bytes()).hexdigest()==a['sha256']
    if path.suffix.lower()=='.zip':
        with zipfile.ZipFile(path) as z:raw=z.read(next(n for n in z.namelist() if n.lower().endswith('.csv')))
    else:raw=path.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==a['csv_sha256']==source['content_sha256']
    counts=Counter();top10=Counter();entries=0
    limit=math.ceil(study['contest']['field_size']*.05)
    for r in csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))):
        if not r.get('EntryId'):continue
        entries+=1
        rank=int(r['Rank'])
        if rank<=limit:counts[r['Lineup']]+=1
        if rank<=math.ceil(study['contest']['field_size']*.1):top10[r['Lineup']]+=1
    assert entries==study['contest']['field_size']
    return (counts,top10),{'status':'verified_raw_ranks','path':str(path),'sha256':a['sha256'],'csv_sha256':a['csv_sha256'],'raw_entries':entries,'top5_rank_cutoff':limit,'raw_top5_entries':sum(counts.values())}


def fit(items,env,adjusted,pop,weighting,balanced=False):
    # Standardize covariates to avoid scale-based rank truncation; report slopes
    # back in original units as percentage points, not production weights.
    columns=[FEATURES.index(env)]
    controls=('salary_thousands','mean_projection_sum','marginal_p90_sum','rb_count','te_count','qb_pass_catchers','bring_backs','distinct_offensive_games')
    if adjusted:columns += [FEATURES.index(c) for c in controls]
    if adjusted and env=='high_total_rb_count':
        controls += ('rb_salary_thousands','rb_mean_sum','rb_p90_sum','offensive_game_total')
        columns += [FEATURES.index(c) for c in controls[-4:]]
    xs=[];ys=[];ws=[];raw_weight=0
    slate_weights=Counter()
    for item in items:
        arr=item["matrix"];w=arr[:,len(FEATURES)] if weighting=="entry" else arr[:,-1]
        keep=(w>0)&np.isfinite(arr[:,columns]).all(axis=1)&np.isfinite(arr[:,len(FEATURES)+POPS.index(pop)])
        slate_weights[item["slate"]]+=w[keep].sum()
    for i,item in enumerate(items):
        arr=item['matrix']; y=arr[:,len(FEATURES)+POPS.index(pop)]
        w=arr[:,len(FEATURES)] if weighting=='entry' else arr[:,-1]
        keep=(w>0)&np.isfinite(arr[:,columns]).all(axis=1)&np.isfinite(y)
        x=arr[keep][:,columns]; w=w[keep];raw_weight+=w.sum()
        if balanced:w=w/slate_weights[item["slate"]]
        # entry y is cohort fraction; unique y is any occurrence in the cohort.
        y=y[keep]/arr[keep,len(FEATURES)] if weighting=='entry' else (y[keep]>0).astype(float)
        intercept=np.zeros((len(x),len(items)));intercept[:,i]=1
        xs.append(np.column_stack([x,intercept]));ys.append(y);ws.append(w)
    x=np.concatenate(xs);y=np.concatenate(ys);w=np.concatenate(ws)
    means=np.average(x[:,:len(columns)],axis=0,weights=w)
    scale=np.sqrt(np.average((x[:,:len(columns)]-means)**2,axis=0,weights=w));scale[scale<1e-12]=1
    x[:,:len(columns)]=(x[:,:len(columns)]-means)/scale
    xtw=x.T*w
    gram=xtw@x;rhs=xtw@y
    coef=np.linalg.lstsq(gram,rhs,rcond=1e-10)[0]
    return {'slope_percentage_points':float(100*coef[0]/scale[0]),'feature':env,'adjusted':adjusted,'controls':list(controls) if adjusted else [],'population':pop,'weighting':weighting,'classified_entries':int(raw_weight),'slate_balanced':balanced,'unique_roster_rows':int(len(w)),'matrix_rank':int(np.linalg.matrix_rank(gram)),'columns':len(gram)}


def main():
    manifest=json.loads((BASE/'manifest.json').read_text())['sha256']
    inventory=verified_json('inventory_snapshot.json',manifest)
    support=verified_json('support_snapshot.json',manifest)
    archives=json.loads((BASE/'linked_archive_inventory.json').read_text())
    supplement=json.loads((OUT/'historical_support.json').read_text())
    contests=[];input_proofs=[]
    for file in sorted((BASE/'contests').glob('*.json')):
        study=verified_json(str(file.relative_to(BASE)),manifest)
        if study.get('status')!='analyzed' or not study['market_inventory']['relative_ranks_available']:continue
        c=study['contest'];cid=c['contest_id'];week=str(c['week']);src=BASE/'inputs'/f'{cid}.json.gz'
        assert hashlib.sha256(src.read_bytes()).hexdigest()==manifest[str(src.relative_to(ROOT))]
        with gzip.open(src,'rt') as f:payload=json.load(f)
        raw5,rawproof=raw_top5(study,inventory,archives)
        print('Analyzing',cid,'week',week,'top5',rawproof['status'],flush=True)
        input_proofs.append({'contest':cid,'study_sha256':manifest[str(file.relative_to(ROOT))],'roster_input_sha256':manifest[str(src.relative_to(ROOT))],'rank_source':rawproof})
        salaries=[r for r in inventory['salaries'] if r['season']==c['season'] and r['week']==c['week'] and r['slate'].upper()==study['analysis_scope']]
        markets,market_audit=market_frame(salaries,c['season'],c['week'],support)
        assert len(markets)==study['market_inventory']['market_games']
        lock=datetime.fromisoformat(market_audit['lock'])
        projection=support['projections'][week]
        oldmeans={r['player_id']:r['mean'] for r in projection['players']}
        p90={}
        for p in supplement['projections'][week]:
            if (datetime.fromisoformat(p['created_at'])<lock and datetime.fromisoformat(p['data_cutoff_at'])<lock
                and p['player_id'] in oldmeans and p['mean']==oldmeans[p['player_id']] and p['p90'] is not None):p90[p['player_id']]=p['p90']
        latest={(norm(r['player_display_name']),r['roster_position']):r for r in payload['reviewed']}
        resolve,_=build_players(salaries,payload['observations']+list(latest.values()),oldmeans)
        distributions={pop:defaultdict(Counter) for pop in POPS};valid=Counter();mat=[];seen=set()
        projection_known=Counter()
        for r in payload['entries']:
            parsed=SLOTS.findall(r['lineup_text'] or '')
            if len(parsed)!=9 or Counter(s for s,n in parsed)!=Counter({'QB':1,'RB':2,'WR':3,'TE':1,'FLEX':1,'DST':1}):continue
            ps=[resolve(s,n) for s,n in parsed]
            if any(p is None for p in ps) or len({p['id'] for p in ps})!=9:continue
            if all(p['salary'] is not None for p in ps) and sum(p['salary'] for p in ps)>50000:continue
            w={'field':r['n'],'top_10':r['top_10'],'top_1':r['top_1'],'top_5':raw5[0][r['lineup_text']] if raw5 else None}
            if raw5:assert raw5[1][r['lineup_text']]==r['top_10']
            for pop,n in w.items():
                if n is None:continue
                valid[pop]+=n
                if not n:continue
                for p in ps:
                    m=markets[p['game']];rel='high' if m['percentile']>=.75 else 'low' if m['percentile']<=.25 else 'middle'
                    for group in [p['position']]+(['offense'] if p['position']!='DST' else []):
                        d=distributions[pop][group];d['n']+=n;d[rel]+=n;d['total_sum']+=n*m['total'];d['implied_sum']+=n*m['team_totals'][p['team']]
                        if p['position']=='DST':d['opponent_implied_sum']+=n*m['team_totals'][p['opponent']]
            offense=[p for p in ps if p['position']!='DST'];rb=[p for p in ps if p['position']=='RB'];qb=next(p for p in ps if p['position']=='QB');dst=next(p for p in ps if p['position']=='DST')
            if any(p['projection'] is None or p['id'] not in p90 or p['salary'] is None for p in ps):continue
            projection_known.update({pop:n for pop,n in w.items() if n is not None})
            sig=tuple(sorted(p['id'] for p in ps));unique=0 if sig in seen else 1;seen.add(sig)
            vals=[sum(markets[p['game']]['total'] for p in offense)/8,
                  sum(markets[p['game']]['team_totals'][p['team']] for p in offense)/8,
                  markets[dst['game']]['team_totals'][dst['opponent']],
                  sum(markets[p['game']]['percentile']>=.75 for p in rb),
                  sum(p['salary'] for p in ps)/1000,sum(p['projection'] for p in ps),sum(p90[p['id']] for p in ps),
                  len(rb),sum(p['position']=='TE' for p in ps),
                  sum(p['team']==qb['team'] and p['position'] in {'WR','TE'} for p in ps),
                  sum(p['team']==qb['opponent'] and p['position']!='DST' for p in ps),len({p['game'] for p in offense}),
                  sum(p['salary'] for p in rb)/1000,sum(p['projection'] for p in rb),sum(p90[p['id']] for p in rb)]
            mat.append(vals+[w[p] if w[p] is not None else float('nan') for p in POPS]+[unique])
        assert valid['field']==study['valid_population_entries']['field'] and valid['top_10']==study['valid_population_entries']['top_10']
        contests.append({'contest':cid,'slate':study['slate_key'],'valid_entries':dict(valid),'controlled_coverage':dict(projection_known),
            'distributions':{p:{g:dict(v) for g,v in groups.items()} for p,groups in distributions.items()},'matrix':np.asarray(mat,dtype=float)})
    slates=sorted({c['slate'] for c in contests})
    pooled={}
    for pop in POPS:
        pooled[pop]={}
        for group in ('offense','QB','RB','WR','TE','DST'):
            d=Counter()
            for c in contests:d.update(c['distributions'][pop][group])
            pooled[pop][group]={'selections':d['n'],**{k:d[k]/d['n'] for k in ('high','middle','low')},
                'mean_game_total':d['total_sum']/d['n'],'mean_team_implied':d['implied_sum']/d['n'],
                **({'mean_opponent_implied':d['opponent_implied_sum']/d['n']} if group=='DST' else {})}
    regressions=[]
    for pop in ('top_10','top_5','top_1'):
        for env in FEATURES[:4]:
            for weighting in ('entry','unique'):
                for adjusted in (False,True):
                    result=fit(contests,env,adjusted,pop,weighting)
                    result['slate_balanced_slope_percentage_points']=fit(contests,env,adjusted,pop,weighting,balanced=True)['slope_percentage_points']
                    result['by_slate']={s:fit([c for c in contests if c['slate']==s],env,adjusted,pop,weighting)['slope_percentage_points'] for s in slates}
                    result['leave_one_slate_out']={s:fit([c for c in contests if c['slate']!=s],env,adjusted,pop,weighting)['slope_percentage_points'] for s in slates}
                    regressions.append(result)
    result={'contract_id':'classic_environment_research_v1','label':'RESEARCH_ONLY / OBSERVATIONAL / NOT PRODUCTION VALIDATED',
        'source_proofs':input_proofs,'supplement_sha256':hashlib.sha256((OUT/'historical_support.json').read_bytes()).hexdigest(),
        'populations':pooled,'contests':[{k:v for k,v in c.items() if k!='matrix'} for c in contests],
        'adjusted_associations':regressions,'cash_outcomes':'Unavailable: no authentic payout rows for these archived contests.',
        'projected_ownership':{'timestamped_rows':{w:len(rows) for w,rows in supplement['ownership'].items()},
            'verified_input_lineage_rows':{w:sum(bool((r.get('metrics_json') or {}).get('input_provenance')) for r in rows) for w,rows in supplement['ownership'].items()},
            'used_as_control':False,'reason':'Week 1 unavailable; recovered Weeks 2–3 runs lack frozen input provenance, so realized ownership is never substituted.'},
        'method':'Descriptive weighted linear probability association with contest intercepts. Entry weights n, outcome cohort/n; unique weights one unordered canonical roster within contest. Controls: lineup salary, sum prelock means, sum marginal P90 (not lineup quantile), RB/TE counts, QB pass catchers, bring backs, distinct games. RB contrast additionally controls RB salary/mean/P90 and overall offensive game total. Whole-slate and leave-one-slate-out variation replaces entry-level significance claims. No tuning or promotion.',
        'limitations':['Only three independent slates; overlapping contests and shared player outcomes remain dependent.',
            'Means/P90 recovered from archived before-lock run/row clocks; recovered means exactly match hashed original export. These are archived model references, not calibrated player-quality controls.',
            'No verified ownership control; cannot establish an independent effect beyond ownership.',
            'Market captures were prelock but sometimes days/weeks old, not certified closing lines.',
            'Complete-case projection controls exclude some entries; convenience sample and unknown contest structures limit generalization.',
            'Roster deduplication occurs within contests; equal-slate and leave-one-slate-out diagnostics handle shared slates descriptively. No independent-entry confidence interval or cash claim.']}
    (OUT/'historical_results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Research complete:',{p:sum(c['valid_entries'].get(p,0) for c in contests) for p in POPS},flush=True)

if __name__=='__main__':main()
