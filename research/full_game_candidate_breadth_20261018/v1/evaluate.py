"""Append retrospective observed labels ONLY after immutable public decisions exist."""
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,pathlib
from itertools import combinations
from backend.app.product_services.full_game_breadth_replay import read
from backend.app.product_services.analyst_shadow import digest
from backend.app.product_services.scenario_breadth import signature
P=pathlib.Path(__file__).resolve().parent
ID='941f74f4c02d56b76dc73133613b89d00eda832949168ea94ca470f1ddd59a75'
r=read(ID);artifact=pathlib.Path('artifacts/full_game_breadth_replays')/(ID+'.json')
# Explicit persisted decision receipt is written before loading outcome files below.
receipt={'replay_id':ID,'decision_artifact_sha256':r['artifact_sha256'],'decision_file_sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),'decision_created_at':r['created_at'],'evaluated_at':datetime.now(timezone.utc).isoformat(),'previously_inspected_outcomes':True,'new_model_fit':False,'retuned':False}
(P/'decision_receipt.json').write_text(json.dumps(receipt,indent=2))
actual_path=pathlib.Path('/private/tmp/season_accuracy_20261018/actuals.json');actuals={x['player_id']:x['actual_points'] for x in json.loads(actual_path.read_text()) if x['contest_id']=='196653899'}
context=next(c for c in json.load(open('research/top_decile_lineup_model_20261018/v1/dataset_inventory_v2.json'))if c.get('contest_id')=='196653899');cutoff=context['points_cutoff']
def score(c):
 ids=[p['player_master_id']for p in c['roster']]
 return round(sum(actuals[p]for p in ids),2)if all(p in actuals for p in ids)else None

def evaluate_pool(pool):
 distinct={signature(c):c for c in pool};scoreable=[c for c in distinct.values()if score(c)is not None];top=[c for c in scoreable if score(c)>=cutoff]
 return {'distinct_rosters':len(distinct),'scoreable':len(scoreable),'top10_rosters':len(top),'top10_ceiling_ignoring_conflicts':min(5,len(top)),
  'best_actual':max((score(c)for c in scoreable),default=None),'top_roster_ids':[c['candidate_id']for c in top],
  'all_rosters':[dict(candidate_id=c['candidate_id'],actual_points=score(c),top10=score(c)>=cutoff if score(c)is not None else None)for c in distinct.values()]}

def validate(cs):
 checks=[];counts=Counter(p['player_master_id']for c in cs for p in c['roster']);pairs=Counter();triples=Counter()
 for c in cs:
  ids=sorted(p['player_master_id']for p in c['roster']);positions=Counter(p['position']for p in c['roster']);teams=Counter(p['team']for p in c['roster']);games=Counter(p['game_id']for p in c['roster'])
  checks += [len(set(ids))==9,c['salary']<=50000,positions['QB']==1,positions['DST']==1,positions['TE']==1,positions['WR']>=3,positions['RB']>=2,max(teams.values())<=3,max(games.values())<=4]
  triples.update(combinations(ids,3))
  for group in combinations(c['roster'],2):
   if group[0]['team']==group[1]['team']and all(p['position']in['WR','TE']for p in group):pairs.update([tuple(sorted(p['player_master_id']for p in group))])
 checks += [max(counts.values(),default=0)<=4,max(triples.values(),default=0)<=3,max(pairs.values(),default=0)<=3]
 overlaps=[len({p['player_master_id']for p in a['roster']}&{p['player_master_id']for p in b['roster']})for a,b in combinations(cs,2)];checks += [max(overlaps,default=0)<=5]
 return {'passed':all(checks),'checks':len(checks),'max_player_appearances':max(counts.values(),default=0),'max_overlap':max(overlaps,default=0),'max_shared_triple':max(triples.values(),default=0),'max_receiving_pair':max(pairs.values(),default=0)}

def evaluation(cs):
 values=[score(c)for c in cs]
 return {'actual_scores':values,'hits':sum(v>=cutoff for v in values if v is not None),'total_actual':sum(v for v in values if v is not None),'constraints':validate(cs)}
old=json.load(open('research/scenario_candidate_breadth_20261018/v1/comparison.json'))
out={'receipt':receipt,'field_context':context,'actual_source_sha256':hashlib.sha256(actual_path.read_bytes()).hexdigest(),'original38':evaluate_pool(old['candidates']),'broader':evaluate_pool(r['candidates']),
 'comparisons':{name:evaluation(c['selected'])for name,c in r['comparisons'].items()},'original38_comparisons':{name:evaluation(c['selected'])for name,c in r['original38_comparisons'].items()}}
assert all(v['constraints']['passed']for group in ['comparisons','original38_comparisons']for v in out[group].values())
(P/'evaluation.json').write_text(json.dumps(out,indent=2))
print('pool', {k:v for k,v in out['broader'].items()if k!='all_rosters'})
for name,c in r['comparisons'].items():
 e=out['comparisons'][name];print(name,'mean',round(c['summed_baseline_mean'],3),'actual',e['actual_scores'],'hits',e['hits'],'valid',e['constraints'])
 for i,x in enumerate(c['selected']):print(i+1,int(x['salary']),round(x['baseline_mean'],3),'/'.join(p['name']for p in x['roster']))
