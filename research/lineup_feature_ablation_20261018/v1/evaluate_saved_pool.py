"""Outcome append after public model/portfolio artifacts are immutable."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
from itertools import combinations
import hashlib,json
from backend.app.product_services.lineup_ablation_replay import read
P=Path(__file__).resolve().parent;ID='1765c389aad769bef4311f4d22b6e2c3ac3c4e2a0fb403f9e19058d4bb46cdc3';r=read(ID)
receipt={'replay_id':ID,'decision_sha256':r['artifact_sha256'],'model_manifest_sha256':hashlib.sha256((P/'model_manifest.json').read_bytes()).hexdigest(),'decision_at':r['created_at'],'evaluation_at':datetime.now(timezone.utc).isoformat(),'retrospective':True,'new_fit_after_evaluation':False}
with(P/'decision_receipt.json').open('x')as f:json.dump(receipt,f,indent=2)
actuals={a['player_id']:a['actual_points']for a in json.load(open('/private/tmp/season_accuracy_20261018/actuals.json'))if a['contest_id']=='196653899'}
context=next(c for c in json.load(open('research/top_decile_lineup_model_20261018/v1/dataset_inventory_v2.json'))if c.get('contest_id')=='196653899');cutoff=context['points_cutoff']
def score(c):
 ids=[p['player_master_id']for p in c['roster']]
 return round(sum(actuals[pid]for pid in ids),2)if all(pid in actuals for pid in ids)else None

def audit(cs):
 counts=Counter(p['player_master_id']for c in cs for p in c['roster']);pairs=Counter();triples=Counter();checks=[]
 for c in cs:
  ps=c['roster'];ids=sorted(p['player_master_id']for p in ps);pos=Counter(p['position']for p in ps);teams=Counter(p['team']for p in ps);games=Counter(p['game_id']for p in ps)
  checks.extend([len(set(ids))==9,c['salary']<=50000,pos['QB']==1,pos['DST']==1,pos['TE']==1,pos['RB']>=2,pos['WR']>=3,max(teams.values())<=3,max(games.values())<=4]);triples.update(combinations(ids,3))
  for a,b in combinations(ps,2):
   if a['team']==b['team']and a['position']in['WR','TE']and b['position']in['WR','TE']:pairs.update([tuple(sorted([a['player_master_id'],b['player_master_id']]))])
 overlaps=[len({p['player_master_id']for p in a['roster']}&{p['player_master_id']for p in b['roster']})for a,b in combinations(cs,2)]
 checks.extend([max(counts.values(),default=0)<=4,max(triples.values(),default=0)<=3,max(pairs.values(),default=0)<=3,max(overlaps,default=0)<=5])
 return {'passed':all(checks),'requested':5,'achieved':len(cs),'max_player_appearances':max(counts.values(),default=0),'max_shared_triple':max(triples.values(),default=0),'max_receiving_pair':max(pairs.values(),default=0),'max_overlap':max(overlaps,default=0)}
policies={}
for name,c in r['comparisons'].items():
 cs=c['selected'];values=[score(x)for x in cs];policies[name]={'actual_scores':values,'scoreable':sum(v is not None for v in values),'top10_hits':sum(v>=cutoff for v in values if v is not None),'summed_baseline_mean':c['summed_baseline_mean'],'constraints':audit(cs),'solver_status':c['selection']['solver_status'],'rams_offense_appearances':sum(any(p['team']=='LAR'and p['position']!='DST'for p in x['roster'])for x in cs)}
 assert policies[name]['constraints']['passed']
values=[score(c)for c in r['candidates']];out={'receipt':receipt,'field_context':context,'pool_distinct':len(r['candidates']),'scoreable':sum(v is not None for v in values),'pool_top10_candidates':sum(v>=cutoff for v in values if v is not None),'policies':policies}
with(P/'saved_pool_evaluation.json').open('x')as f:json.dump(out,f,indent=2)
for name,x in policies.items():print(name,'mean',round(x['summed_baseline_mean'],3),'actuals',x['actual_scores'],'hits',x['top10_hits'],'Rams',x['rams_offense_appearances'],'status',x['solver_status'])
