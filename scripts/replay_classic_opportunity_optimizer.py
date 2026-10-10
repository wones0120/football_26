"""Research optimizer comparison; preserves all original controls except projections."""
import json,sys
from pathlib import Path
from copy import deepcopy
from dataclasses import asdict
from collections import Counter
import pandas as pd
import pulp
from sqlalchemy import create_engine
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.app.product_services import gpp_optimizer as g
from backend.app.product_services.classic_strategy_contract import config_from_dict
OUT=ROOT/'artifacts/classic_opportunity_repair';OLD=ROOT/'artifacts/classic_gibbs_wilson_audit';(OUT/'solver_logs').mkdir(exist_ok=True)
corrected=pd.read_csv(OUT/'f3a3b0d0-30e7-48fa-a968-9889cccf927f_corrected_predictions.csv').set_index('player_id')
label='';counter=0

def solver(backend):
 global counter
 counter+=1
 return pulp.PULP_CBC_CMD(msg=False,logPath=str(OUT/'solver_logs'/f'{label}_{counter:03d}.log'))
g.make_cbc_solver=solver
results={}
for key in ['139d5544','bd990e1b']:
 e=json.loads((OLD/(key+'_run.json')).read_text())['constraint_config_json']['effective_strategy_contract']['effective'];cfg=config_from_dict(e['resolved_config']);entry={}
 for version in ['before','after']:
  players=[g.Player(**{**p,'tags':set(p['tags'])}) for p in e['players']]
  if version=='after':
   for p in players:
    p.projection=float(corrected.loc[p.player_id,'mean']);p.ceiling=float(corrected.loc[p.player_id,'p90'])
  # Explicitly prove ownership, eligibility, salary, football context and tags unchanged.
  for p,original in zip(players,e['players']):
   for field,value in asdict(p).items():
    if field not in {'projection','ceiling','tags'}:assert value==original[field],field
  label=key+'_'+version;options=deepcopy(e['pipeline_options'])
  portfolio=g.run_gpp_pipeline(players=players,engine=create_engine('sqlite://'),effective_config=deepcopy(cfg),**options)
  data={'status':portfolio.status,'lineups':[],'exposures':dict(Counter(p.name for row in portfolio.lineups for p in row)),'selection_trace':portfolio.selection_trace,'single_entry':{}}
  for lineup in portfolio.lineups:data['lineups'].append({'players':[p.name for p in lineup],'player_ids':[p.player_id for p in lineup],'mean':sum(p.projection for p in lineup),'p90_sum':sum(p.ceiling for p in lineup),'salary':sum(p.salary for p in lineup)})
  if version=='before':
   # Compare original sequential solves proven in the root-cause audit.
   prior=json.loads((OLD/'results.json').read_text())['sequential'][key]
   assert len(data["lineups"])==len(prior)
   assert all(set(lineup["player_ids"])==set(step["original"]["player_ids"]) for lineup,step in zip(data["lineups"],prior))
   data["original_roster_parity"]=True
  ids={p.name:p.player_id for p in players};g.tag_players(players,cfg.tag_thresholds)
  for name,required in [('best',set()),('forced_Gibbs',{ids['Jahmyr Gibbs']}),('forced_Wilson',{ids['Garrett Wilson']})]:
   label=key+'_'+version+'_'+name;a={};ix=g._build_lineup(players,deepcopy(cfg),None,[],required_player_ids=required,avoid_dst_opponents=options['avoid_dst_opponents'],enforce_single_te=options['enforce_single_te'],solve_audit=a)
   assert ix is not None and a['solver_status']=='Optimal'
   lineup=[players[i] for i in ix];data['single_entry'][name]={'players':[p.name for p in lineup],'player_ids':[p.player_id for p in lineup],'salary':sum(p.salary for p in lineup),'mean':sum(p.projection for p in lineup),'p90_sum':sum(p.ceiling for p in lineup),'objective':a['objective_score'],'objective_components':a['objective_components']}
  entry[version]=data;results[key]=entry
  (OUT/'optimizer_comparison.json').write_text(json.dumps(results,default=str,indent=2)+'\n');print(key,version,data['exposures'],flush=True)
