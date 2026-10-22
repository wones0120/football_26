"""Explicit root-dispatched saved-v4 scoring after exact 2026 array gate; no fit."""
from pathlib import Path
from datetime import datetime,UTC
from io import BytesIO
from collections import defaultdict
import json,hashlib,time
import numpy as np
from backend.app.product_services.joint_group_budget_allocation import forward
R=Path(__file__).resolve().parent

def read(ref):
 b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];return b

def metric(pairs):
 if not pairs:return dict(n=0,mae=None,rmse=None,bias=None)
 y,p=np.asarray(pairs,float).T;e=p-y
 return dict(n=len(y),mae=float(abs(e).mean()),rmse=float(np.sqrt((e*e).mean())),bias=float(e.mean()))

def save(v,kind):
 b=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(b).hexdigest();p=Path('artifacts',kind,sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==b
 else:
  with p.open('xb')as f:f.write(b)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(b))

def main():
 if(R/'RESULTS.json').exists():raise ValueError('Preserve existing score publication; no automatic repeat')
 gate=json.loads((R/'HIGH_REVIEW.json').read_text());assert gate['status'].startswith('FINAL_PASS')
 evidence=json.loads((R/'EVIDENCE.json').read_text())
 for pin in evidence['pins']:read(pin)
 m=json.loads((R/'MANIFEST.json').read_text());started=datetime.now(UTC);timer=time.monotonic();channels={}
 for channel,c in m['channels'].items():
  groups=json.loads(read(c['group_ref']));data=dict(np.load(BytesIO(read(c['tensor_ref'])),allow_pickle=False));model=json.loads(read(c['converged_model_ref']));fit=json.loads(read(c['fit_receipt_ref']))
  assert model['status']=='completed'and model['native_status']==1 and model['original_gradient_inf']<=1e-5 and model['channel']==channel
  assert model['preprocessing']==c['cell_preprocessing']and model['group_preprocessing']==c['group_preprocessing']
  state=forward(np.asarray(model['parameters']),data,channel=channel);mu=state['mu'];heads=state['heads'];assert np.isfinite(mu).all()and(mu>=0).all()and np.isfinite(heads).all()
  rows=[];buckets=defaultdict(list);week=defaultdict(list);matchup=defaultdict(list);controls=defaultdict(list)
  for gi,(g,lo,hi)in enumerate(zip(groups,data['offsets'][:-1],data['offsets'][1:])):
   w=g['period']%100;opp=next(t for t in g['game_id'].split('_')[-2:]if t!=g['team']and not(t=='LA'and g['team']=='LAR'))
   # Native source/canonical LA mapping is retained in the frozen group key; present cohort contains no LA.
   means=mu[lo:hi];assert np.isclose(means.sum(),heads[gi].sum(),rtol=1e-12,atol=1e-12)
   if channel=='target':assert np.isclose(means[:-1].sum(),heads[gi,0],rtol=1e-12,atol=1e-12)
   r=dict(game_id=g['game_id'],team=g['team'],opponent=opp,week=w,cells=[],predicted_heads=heads[gi].tolist(),labels={k:v for k,v in g.items()if k.endswith('budget_label')})
   for ci,(cell,pred)in enumerate(zip(g['cells'],means)):
    kind=cell['kind'];pair=(cell['label'],float(pred));tags=[kind]
    if kind=='candidate':
     tags+=['candidate_zero'if cell['label']==0 else'candidate_positive'];role=next((role for role in('QB','RB','FB','WR','TE','other')if cell['features']['latest_prior_role_'+role]==1),'UNKNOWN');tags+=['prior_role_'+role]
     hf='scheduled3_rush_attempts_mean'if channel=='rush'else'scheduled3_targets_mean';history=cell['features'][hf]
     if history is not None:controls['candidate_history3'].append((cell['label'],history))
    for tag in tags:buckets[tag].append(pair);week[f'{w}|{tag}'].append(pair);matchup[f"{g['game_id']}|{g['team']}|{tag}"].append(pair)
    controls[kind+'_train_constant'].append((cell['label'],fit['train_constants'][kind]))
    r['cells'].append({k:v for k,v in cell.items()if k!='features'}|dict(prediction=float(pred)))
   budget_names=[('budget',g['budget_label'],heads[gi,0],'rush_attempts')]if channel=='rush'else[('target_budget',g['target_budget_label'],heads[gi,0],'targets'),('pass_budget',g['pass_budget_label'],heads[gi].sum(),'pass_attempts')]
   for name,label,pred,hist in budget_names:
    pair=(label,float(pred));buckets[name].append(pair);week[f'{w}|{name}'].append(pair);matchup[f"{g['game_id']}|{g['team']}|{name}"].append(pair)
    controls[name+'_train_constant'].append((label,fit['train_budget_constants'][name]));prior=g['cells'][0]['features']['weekly3_own_'+hist+'_mean']
    if prior is not None:controls[name+'_history3'].append((label,prior))
   rows.append(r)
  matched={}
  for name,old in json.loads(read(c['saved_baseline_matches_ref'])).items():
   pairs=[];saved=[];wk=defaultdict(lambda:dict(new=[],saved=[]));games=defaultdict(lambda:dict(new=[],saved=[]))
   for o in old:
    gi=o['group_index'];ci=o['cell_index'];g=groups[gi];r=rows[gi]
    if ci is None:new=float(heads[gi].sum());label=g['budget_label'if channel=='rush'else'pass_budget_label']
    else:new=r['cells'][ci]['prediction'];label=g['cells'][ci]['label']
    assert label==o['actual'];p=(label,new);q=(label,o['saved_prediction']);pairs.append(p);saved.append(q)
    wk[str(g['period']%100)]['new'].append(p);wk[str(g['period']%100)]['saved'].append(q);key=g['game_id']+'|'+g['team'];games[key]['new'].append(p);games[key]['saved'].append(q)
   matched[name]=dict(new=metric(pairs),saved=metric(saved),by_week={k:{v:metric(z)for v,z in d.items()}for k,d in wk.items()},by_team_opponent={k:{v:metric(z)for v,z in d.items()}for k,d in games.items()})
  channels[channel]=dict(groups=len(rows),predictions_ref=save(rows,'joint_group_budget_2026_predictions'),population_metrics={k:metric(v)for k,v in buckets.items()},by_week={k:metric(v)for k,v in week.items()},by_team_opponent={k:metric(v)for k,v in matchup.items()},train_only_and_prior_controls={k:metric(v)for k,v in controls.items()},matched_saved_baselines=matched,all_means_nonnegative=True,budgets_exactly_conserved_with_FP_tolerance=True,baseline_coverage=c['baseline_coverage'])
 result=dict(version='v4_reconstructed2026_saved_model_evaluation',started_at=started.isoformat(),completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,channels=channels,scope=m['scope'],availability=m['availability'],all214_schedule_status_ref=m['all214_schedule_status_ref'],fits=0,optimizer_calls=0,model_repairs=0,activation=False,injury_replacement_result_cases=0,interpretation='Tiny selected source-compatible reconstructedW4–5 cohort only; no complete2026 or original-vintage/wholeNFL/live claim; matched baselines sparse and separate.')
 (R/'RESULTS.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps({k:v['population_metrics']for k,v in channels.items()},indent=2))
if __name__=='__main__':main()
