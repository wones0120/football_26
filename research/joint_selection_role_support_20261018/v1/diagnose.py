"""No new model fits; frozen feature support and revised historical role inputs."""
from collections import defaultdict,Counter
from pathlib import Path
import gzip,hashlib,json,math,statistics
from backend.app.product_services.scenario_allocation import measurement,team
from backend.app.product_services.full_game_breadth import role_universe
from backend.app.product_services.lineup_top_decile_research import lineup_features
P=Path(__file__).resolve().parent;T=Path('research/top_decile_lineup_model_20261018/v1');F=Path('research/full_game_candidate_breadth_20261018/v1')
lib=json.load(open(F/'historical_templates_v2.json'));raw=json.load(open('research/joint_portfolio_selection_20261018/v1/historical_stats.json'));groups=defaultdict(list)
norm=lambda t:'LAR'if t=='LA'else t
for r in raw:groups[norm(r['team'])].append(r)
# Full team production denominators, not surviving current-game actors only.
for g in lib['games']:
 for side in g['sides']:
  rs=groups[side['team']];prior_games=sorted({(r['week'],r['game_id'])for r in rs if r['week']<g['week']})[-3:];prior_ids={gid for _,gid in prior_games}
  prior=[r for r in rs if r['game_id']in prior_ids];n=len(prior_ids)
  if n!=3:raise ValueError('Three prior complete team games required')
  side['prior_team_volume']={k:sum(float(r['raw_row_json'][k])for r in prior)/n for k in ['targets','carries','attempts']}
  side['prior_team_game_ids']=sorted(prior_ids)
lib['parent_sha256']=hashlib.sha256((F/'historical_templates_v2.json').read_bytes()).hexdigest();lib['contract_id']='physical_paired_game_role_templates_v3'
with (P/'historical_templates_v3.json').open('x')as f:json.dump(lib,f)
config=next(r['constraint_config_json']for r in json.load(open('/private/tmp/sunday_actual_review_20261018/stored_run_configs.json'))if r['optimizer_run_id'].startswith('398efe88'));snap=config['strategy_runtime']['football_analyst']['input_snapshot'];full=config['strategy_runtime']['player_pool']['rows'];universe,_=role_universe(full,snap['players'])
current={}
for t in {team(r)for r in full}:
 vals={}
 for channel in ['targets','carries']:
  obs=[]
  for r in full:
   if team(r)!=t:continue
   v=(r.get('workload_evidence')or{}).get('team_volume_proxies',{}).get('team_'+channel+'_mean_3',{})
   if type(v.get('value'))in(int,float)and v.get('status')not in['unavailable','after_cutoff','coverage_unknown']:obs.append(v['value'])
  if not obs:raise ValueError('Unknown current whole-team denominator')
  if max(obs)-min(obs)>1e-6:raise ValueError('Conflicting current whole-team denominator')
  vals[channel]=obs[0]
 current[t]=vals
with (P/'current_team_denominators.json').open('x')as f:json.dump(current,f,indent=2)
# Classifier support, deduplicated canonical training rosters (context variants retained explicitly).
records={}
for path in sorted((T/'contests_v2').glob('*.json.gz')):
 with gzip.open(path,'rt')as f:d=json.load(f)
 c=d['context']
 if c['contest_format']!='classic'or c['week']>=6:continue
 for row in d['rosters']:records.setdefault((c['week'],row['roster_key']),row['features'])
xs=list(records.values());model=json.load(open(T/'models/classic_core_train_before_w6.json'));names=model['features']
def quantile(a,p):
 a=sorted(a);return a[int((len(a)-1)*p)]
reference={name:{'min':min(v[j]for v in xs),'p01':quantile([v[j]for v in xs],.01),'p99':quantile([v[j]for v in xs],.99),'max':max(v[j]for v in xs)}for j,name in enumerate(names)}
r=json.load(open('artifacts/full_game_breadth_replays/941f74f4c02d56b76dc73133613b89d00eda832949168ea94ca470f1ddd59a75.json'));feature=json.load(open(F/'frozen_predictor_inputs.json'))['rows'];support=[]
for c in r['candidates']:
 x=lineup_features([feature[p['player_master_id']]for p in c['roster']],'classic');terms=[(n,(v-m)/s,k*((v-m)/s))for n,v,m,s,k in zip(names,x,model['mean'],model['scale'],model['coefficients'])]
 support.append({'candidate_id':c['candidate_id'],'baseline_mean':c['baseline_mean'],'salary':c['salary'],'outside_01_99':[n for n,v in zip(names,x)if v<reference[n]['p01']or v>reference[n]['p99']], 'largest_negative_logit_terms':sorted(terms,key=lambda z:z[2])[:5]})
folds=json.load(open(T/'metrics.json'));weekly=[]
for week in [4,5,6]:
 for rich in [False,True]:
  cs=[v for v in folds if v['format']=='classic'and v['week']==week and v['rich']==rich]
  weekly.append({'week':week,'rich':rich,'contests':len(cs),'mean_auc':statistics.mean(v['roc_auc']for v in cs),'model_hits':sum(v['model_top5_hits']for v in cs),'mean_hits':sum(v['baseline_mean_top5_hits']for v in cs),'overlapping_fields_not_independent':True})
out={'training_distinct_canonical_rosters':len(xs),'training_features':reference,'candidate_support':support,'temporal_folds':weekly,'new_training':False,'interpretation':'Model support/associations do not establish causal reasons or forward win probabilities'}
with (P/'classifier_support.json').open('x')as f:json.dump(out,f,indent=2)
print('training salary',reference['salary_used'],'generated outside p01 salary',sum(c['salary']<reference['salary_used']['p01']for c in support))
for c in support:
 if c['candidate_id'].endswith(('favored_stalled:2026_06_NYJ_NE','favored_stalled:2026_06_TEN_IND')):print(c)
print('complete current denominators',len(current));print('folds',weekly)
