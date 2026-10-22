"""One explicitly root-dispatched frozen joint-mean recipe; never a grid."""
from pathlib import Path
from datetime import datetime,UTC
from collections import defaultdict
from io import BytesIO
import argparse,hashlib,json,signal,time
import numpy as np
from backend.app.product_services import joint_rush_conditional_means as rush
from backend.app.product_services import joint_target_pass_conditional_means as target

p=argparse.ArgumentParser();p.add_argument('--channel',choices=['rush','target'],required=True);p.add_argument('--saved-model',required=True);a=p.parse_args()
R=Path(__file__).resolve().parent;out=R/(a.channel+'.json')
if out.exists():raise ValueError('Existing experiment preserved; no automatic retry')
module=rush if a.channel=='rush'else target
package='joint_rush_conditional_means_20261020'if a.channel=='rush'else'joint_target_pass_conditional_means_20261020'
P=Path('research',package,'v1');GATE=P/'HIGH_REVIEW.json';gate=json.loads(GATE.read_text())
if not gate['status'].startswith('FINAL_PASS'):raise ValueError('Exact prefit review required')
repair_gate_path=Path('research/joint_mean_exact_residual_solver_20261020/v3/HIGH_REVIEW.json')
repair_gate=json.loads(repair_gate_path.read_text());assert repair_gate['status'].startswith('FINAL_PASS')
repair_evidence=json.loads(repair_gate_path.with_name('EVIDENCE.json').read_text())
for pin in repair_evidence['pins']:
    b=Path(pin['path']).read_bytes();assert len(b)==pin['bytes']and hashlib.sha256(b).hexdigest()==pin['sha256']
manifest=json.loads((P/'MANIFEST.json').read_text());evidence=json.loads((P/'EVIDENCE.json').read_text())
for pin in evidence['pins']:
    b=Path(pin['path']).read_bytes();assert len(b)==pin['bytes']and hashlib.sha256(b).hexdigest()==pin['sha256']
def read(ref):
    b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];return b
def save(value,kind):
    b=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(b).hexdigest();path=Path('artifacts',kind,sha+'.json');path.parent.mkdir(exist_ok=True)
    if path.exists():assert path.read_bytes()==b
    else:
        with path.open('xb')as f:f.write(b)
        path.chmod(0o444)
    return dict(path=str(path.resolve()),sha256=sha,bytes=len(b))
metadata=json.loads(read(manifest['group_metadata_ref']));arrays=np.load(BytesIO(read(manifest['tensor_ref'])),allow_pickle=False)
raw=arrays['raw_inputs'];offsets=arrays['offsets'];columns=manifest['feature_columns'];groups=[]
for g,lo,hi in zip(metadata,offsets[:-1],offsets[1:]):
    group={**g,'cells':[]}
    for c,x in zip(g['cells'],raw[lo:hi]):group['cells'].append({**c,'features':{k:None if np.isnan(v)else float(v)for k,v in zip(columns,x)}})
    groups.append(group)
started=datetime.now(UTC);timer=time.monotonic()
def timeout(*_):raise TimeoutError('Fixed300second cap; no retry')
saved_path=Path(a.saved_model);saved_bytes=saved_path.read_bytes();assert hashlib.sha256(saved_bytes).hexdigest()==saved_path.stem
model=json.loads(saved_bytes);assert model['status']=='completed'and model['channel']==a.channel and model['native_status']==1 and model['original_gradient_inf']<=1e-5
model_ref=save(model,'joint_conditional_mean_v3_models')
base=dict(channel=a.channel,started_at=None,completed_at=None,elapsed_seconds=None,recovery_started_at=started.isoformat(),recovery_completed_at=datetime.now(UTC).isoformat(),recovery_elapsed_seconds=time.monotonic()-timer,fit_timing='Originalprecisefitclockslostinpostreportassert;durablestage/storageclocksretained',evaluation_only_recovery=True,
          status=model['status'],model_ref=model_ref,gate_path=str(GATE.resolve()),gate_sha256=hashlib.sha256(GATE.read_bytes()).hexdigest(),
          manifest_path=str((P/'MANIFEST.json').resolve()),manifest_sha256=hashlib.sha256((P/'MANIFEST.json').read_bytes()).hexdigest(),
          repair_gate_path=str(repair_gate_path.resolve()),repair_gate_sha256=hashlib.sha256(repair_gate_path.read_bytes()).hexdigest(),
          objective_recipe=model['objective_recipe'],effective_optimizer_options=model['effective_optimizer_options'],fresh_original_seed_start=model['fresh_original_seed_start'],initial_parameters_sha256=model['initial_parameters_sha256'],
          recipe=model['recipe'],nfev=model.get('nfev'),njev=model.get('njev'),native_status=model.get('native_status'),
          native_optimality=model.get('native_optimality'),native_cost=model.get('native_cost'),residual_cost=model.get('residual_cost'),
          original_objective=model.get('original_objective'),original_gradient_inf=model.get('original_gradient_inf'),solver_counters=model.get('solver_counters'),optimizer_message=model['optimizer_message'],
          fits_attempted=0,original_fit_attempts=1,retries=0,hard_cap_seconds=300,activation=False,settings_changes=0,lineup_changes=0,
          scope='Retrospective selected source-observed compatible groups; 2025 repeatedly inspected; not complete NFL roster or original-pregame backtest')
base['reporting_status']='PENDING'if model['status']=='completed'else'SKIPPED_FAILED'
out.write_text(json.dumps(base,indent=2,allow_nan=False)+'\n')
if model['status']!='completed':
    out.write_text(json.dumps(base,indent=2)+'\n');print(json.dumps(base));raise SystemExit(2)
predictions=module.predict(model,groups);records=[]
for i,(g,pred)in enumerate(zip(groups,predictions)):
    lo,hi=offsets[i:i+2];y=arrays['labels'][lo:hi];mu=np.asarray(pred['cell_means'])
    assert np.isfinite(mu).all()and(mu>=0).all()
    if a.channel=='rush':assert np.isclose(pred['budget_mean'],sum(pred['cell_means']),rtol=1e-12,atol=1e-12)
    else:assert np.isclose(pred['target_mean'],sum(pred['cell_means'][:-1]),rtol=1e-12,atol=1e-12)and np.isclose(pred['pass_mean'],pred['target_mean']+pred['cell_means'][-1],rtol=1e-12,atol=1e-12)
    records.append(dict(group_index=i,game_id=g['game_id'],team=g['team'],period=g['period'],
                        cells=[{**c,'prediction':float(v)}for c,v in zip(g['cells'],mu)],
                        budget_labels={k:v for k,v in g.items()if k.endswith('budget_label')},
                        predicted={k:v for k,v in pred.items()if k not in('game_id','team','cell_means')}))

def metrics(pairs):
    if not pairs:return dict(rows=0,mae=None,rmse=None,bias=None)
    y,p=np.asarray(pairs,dtype=float).T;e=p-y
    return dict(rows=len(y),mae=float(abs(e).mean()),rmse=float(np.sqrt((e**2).mean())),bias=float(e.mean()),observed_mean=float(y.mean()),predicted_mean=float(p.mean()))
traincells=[c for r in records if r['period']//100==2023 for c in r['cells']]
constant={kind:float(np.mean([c['label']for c in traincells if c['kind']==kind]))for kind in{c['kind']for c in traincells}}
budget_fields={'budget':'budget_label'}if a.channel=='rush'else{'target_budget':'target_budget_label','pass_budget':'pass_budget_label'}
budget_constants={name:float(np.mean([g[field]for g in groups if g['period']//100==2023]))for name,field in budget_fields.items()}
summary={};role_errors={};zero_positive={};deciles={};history={}
for year in(2023,2024,2025):
    rows=[r for r in records if r['period']//100==year];buckets=defaultdict(list);roles=defaultdict(list);zeros=defaultdict(list);hist=[]
    for r in rows:
        i=r['group_index'];g=groups[i]
        for j,c in enumerate(r['cells']):
            pair=c['label'],c['prediction'];buckets[c['kind']].append(pair);zeros[c['kind']+('_zero'if c['label']==0 else'_positive')].append(pair)
            buckets[c['kind']+'_train_constant'].append((c['label'],constant[c['kind']]))
            if c['kind']=='candidate':
                flags=[role for role in('QB','RB','WR','TE','FB','other')if g['cells'][j]['features']['latest_prior_role_'+role]==1]
                roles[flags[0]if flags else'UNKNOWN_PRIOR_ROLE'].append(pair)
                feature='scheduled3_rush_attempts_mean'if a.channel=='rush'else'scheduled3_targets_mean'
                h=g['cells'][j]['features'][feature]
                if h is not None:hist.append((c['label'],h))
        if a.channel=='rush':
            buckets['budget'].append((g['budget_label'],r['predicted']['budget_mean']))
        else:
            buckets['target_budget'].append((g['target_budget_label'],r['predicted']['target_mean']))
            buckets['pass_budget'].append((g['pass_budget_label'],r['predicted']['pass_mean']))
        for name,field in budget_fields.items():
            buckets[name+'_train_constant'].append((g[field],budget_constants[name]))
            history_field='weekly3_own_'+('rush_attempts'if name=='budget'else'targets'if name=='target_budget'else'pass_attempts')+'_mean'
            prior=g['cells'][0]['features'][history_field]
            if prior is not None:buckets[name+'_history3'].append((g[field],prior))
    summary[str(year)]={k:metrics(v)for k,v in buckets.items()};role_errors[str(year)]={k:metrics(v)for k,v in roles.items()};zero_positive[str(year)]={k:metrics(v)for k,v in zeros.items()};history[str(year)]=metrics(hist)
    deciles[str(year)]={}
    for k,v in buckets.items():
        if k.endswith('_train_constant'):continue
        ordered=sorted(v,key=lambda pair:pair[1]);parts=np.array_split(np.asarray(ordered,dtype=float),min(10,len(ordered)))
        deciles[str(year)][k]=[metrics(part.tolist())for part in parts if len(part)]
matched={};saved=json.loads(read(manifest['saved_baseline_matches_ref']))
for name,matches in saved.items():
    byyear=defaultdict(lambda:dict(new=[],saved=[]))
    for row in matches:
        i,j=row['group_index'],row['cell_index'];year=str(groups[i]['period']//100);actual=records[i]['cells'][j]['label'];assert actual==row['actual']
        byyear[year]['new'].append((actual,records[i]['cells'][j]['prediction']));byyear[year]['saved'].append((actual,row['saved_prediction']))
    matched[name]={year:{k:metrics(v)for k,v in comparisons.items()}for year,comparisons in byyear.items()}
if a.channel=='target':
    savedteam=json.loads(read(manifest['team_pass_baseline_matches_ref']));team_matches={}
    for name,part in savedteam.items():
        byyear=defaultdict(lambda:dict(new=[],saved=[]))
        for row in part['matches']:
            i=row['group_index'];year=str(groups[i]['period']//100);actual=groups[i]['pass_budget_label'];assert actual==row['actual']
            byyear[year]['new'].append((actual,records[i]['predicted']['pass_mean']));byyear[year]['saved'].append((actual,row['saved_prediction']))
        team_matches[name]={y:{k:metrics(v)for k,v in c.items()}for y,c in byyear.items()}
    base['matched_team_pass_baselines']=team_matches
base.update(reporting_status='COMPLETED',prediction_ref=save(records,'joint_conditional_mean_v3_predictions'),evaluation=summary,prior_role_errors=role_errors,
            zero_positive_errors=zero_positive,history3_candidate_control=history,train_constants=constant,train_budget_constants=budget_constants,
            descriptive_mean_deciles=deciles,matched_saved_candidate_baselines=matched,
            accounting=dict(groups=len(records),nonnegative=True,mean_budget_identities=True,known_rest_separate=True,unknown_NFL_census='UNKNOWN'),
            attribution='Changed candidate cohort/loss/features and selected source-completeness population; no isolated feature benefit or live promotion claim')
out.write_text(json.dumps(base,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:base[k]for k in('channel','status','elapsed_seconds','nfev','njev','native_status','original_gradient_inf','evaluation','matched_saved_candidate_baselines')},indent=2))
