"""Append known retrospective target outcomes only after the saved decision receipt."""
from pathlib import Path
import json,hashlib
from collections import Counter
from itertools import combinations
from backend.app.product_services.full_game_breadth_replay import read
from backend.app.product_services.scenario_breadth import signature
P=Path(__file__).parent;receipt=json.load(open(P/'decision_receipt.json'));r=read(receipt['replay_id']);assert r['artifact_sha256']==receipt['artifact_sha256']
actualpath=Path('/private/tmp/season_accuracy_20261018/actuals.json');actuals={x['player_id']:x['actual_points']for x in json.load(open(actualpath))if x['contest_id']=='196653899'};context=next(x for x in json.load(open('research/top_decile_lineup_model_20261018/v1/dataset_inventory_v2.json'))if x.get('contest_id')=='196653899');cutoff=context['points_cutoff']
def score(c):
 ids=[p['player_master_id']for p in c['roster']];return round(sum(actuals[p]for p in ids),2)if all(p in actuals for p in ids)else None

def evaluate(pool):
 values=[score(c)for c in pool];return {'rosters':len(pool),'scored':sum(v is not None for v in values),'top10':sum(v>=cutoff for v in values if v is not None),'best_actual':max((v for v in values if v is not None),default=None),'actuals':values}

def dependency(cs):
 counts=Counter(p['player_master_id']for c in cs for p in c['roster']);pair=Counter();triple=Counter()
 for c in cs:
  ids=sorted(p['player_master_id']for p in c['roster']);triple.update(combinations(ids,3))
  for t in {p['team']for p in c['roster']}:pair.update(combinations(sorted(p['player_master_id']for p in c['roster']if p['team']==t and p['position']in ['WR','TE']),2))
 return {'max_player':max(counts.values()),'max_shared_triple':max(triple.values()),'max_receiving_pair':max(pair.values()),'max_roster_overlap':max(len({p['player_master_id']for p in a['roster']}&{p['player_master_id']for p in b['roster']})for a,b in combinations(cs,2))}

a={signature(c)for c in r['saved_v1_candidates']};b={signature(c)for c in r['candidates']};out={'receipt':receipt,'actual_source_sha256':hashlib.sha256(actualpath.read_bytes()).hexdigest(),'context':context,'pool_before':evaluate(r['saved_v1_candidates']),'pool_after':evaluate(r['candidates']),'canonical_rosters_added':len(b-a),'canonical_rosters_removed':len(a-b),'comparisons':{arm:{name:{**evaluate(v['selected']),'mean_sum':v['summed_baseline_mean'],'status':v['selection']['solver_status'],'dependencies':dependency(v['selected'])}for name,v in r[key].items()}for arm,key in [('v1','saved_v1_comparisons'),('v2','comparisons')]},'retrospective_only':True,'new_fit':False,'selection_retuned':False};(P/'evaluation.json').write_text(json.dumps(out,indent=2)+'\n');print('cutoff',cutoff,'newremoved',out['canonical_rosters_added'],out['canonical_rosters_removed']);print('pools',[(k,{key:v for key,v in out[k].items()if key!='actuals'})for k in ['pool_before','pool_after']]);print(json.dumps(out['comparisons'],indent=2))
