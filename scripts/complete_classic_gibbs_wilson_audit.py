"""Additional research-only scoring reconciliations and fixed-snapshot cap diagnostics."""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict,replace
from hashlib import sha256
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import pulp
from backend.app.product_services import gpp_optimizer as g
from backend.app.product_services.classic_strategy_contract import config_from_dict
from backend.app.product_services.lineup_correlation_scoring import score_lineup_correlations
OUT=ROOT/'artifacts/classic_gibbs_wilson_audit'
r=json.loads((OUT/'results.json').read_text()); saved=json.loads((OUT/'139d5544_run.json').read_text())['constraint_config_json']
e=saved['effective_strategy_contract']['effective'];cfg=config_from_dict(e['resolved_config']);players=[g.Player(**{**p,'tags':set(p['tags'])}) for p in e['players']];g.tag_players(players,cfg.tag_thresholds)
ids={p.name:p.player_id for p in players};G=ids['Jahmyr Gibbs'];W=ids['Garrett Wilson'];Q=ids['Jared Goff'];S=ids['Amon-Ra St. Brown']
label=''
def solver(backend):return pulp.PULP_CBC_CMD(msg=False,logPath=str(OUT/'solver_logs'/(label+'.log')))
g.make_cbc_solver=solver

def solve(name,required=(),config=None,**extra):
 global label
 label=name; c=config or deepcopy(cfg);a={}
 ix=g._build_lineup(players,c,None,[],required_player_ids=set(required),avoid_dst_opponents=True,solve_audit=a,**extra)
 a['player_ids']=[] if ix is None else [players[i].player_id for i in ix]
 if ix is not None:
  roster=[players[i] for i in ix];a.update(players=[asdict(p)|{'tags':sorted(p.tags)} for p in roster],salary=sum(p.salary for p in roster),mean=sum(p.projection for p in roster),ceiling=sum(p.ceiling for p in roster),ownership=sum(p.ownership or 0 for p in roster))
 r['solves'][name]=a;print(name,a.get('solver_status'),a.get('objective_score'),flush=True)
 return a
broad=deepcopy(cfg);broad.stack_rules=replace(broad.stack_rules,max_from_team=4,max_from_game=5)
for name,req in [('broad_A',()),('broad_B',(G,)),('broad_C',(W,)),('broad_D',(G,W))]:solve(name,req,broad)
solve('tight_Goff_Gibbs',[Q,G]);solve('team4_Goff_Gibbs',[Q,G],replace(deepcopy(cfg),stack_rules=replace(cfg.stack_rules,max_from_team=4)))
solve('tight_Goff_Gibbs_StBrown',[Q,G,S]);solve('broad_Goff_Gibbs_StBrown',[Q,G,S],broad)
# Single-rule scoring controls for the broad region, all with original tight-snapshot players.
for name in ['broad_no_correlation','broad_no_mandatory_stack']:
 c=deepcopy(broad)
 if 'correlation' in name:c.objective_weights=replace(c.objective_weights,correlation=0)
 else:c.stack_rules=replace(c.stack_rules,min_pass_catchers=0)
 solve(name,config=c)
# Independent original-score evaluation, fixed original denominators even for scoring ablations.
mp=max(p.projection+p.optimizer_context_adjustment for p in players);mc=max(p.ceiling+p.optimizer_context_adjustment for p in players)
lookup={p.player_id:p for p in players};profile=g.resolve_strategy_profile(contest_format='classic',objective='gpp')
for name,a in r['solves'].items():
 if not a['player_ids']:continue
 roster=[lookup[pid] for pid in a['player_ids']]
 corr=score_lineup_correlations(roster,profile=profile,objective_multiplier=.15)
 # Complete diagnostics use production term activations and same frozen market/role inputs.
 value=sum(.35*(p.projection+p.optimizer_context_adjustment)/mp+.45*(p.ceiling+p.optimizer_context_adjustment)/mc for p in roster)+corr['total_adjustment']
 a['original_objective_rescore']=value;a['correlation_explanation']=corr
 if not any(t in name for t in ['no_correlation','no_context']):assert abs(value-a['objective_score'])<1e-7,(name,value,a['objective_score'])
# Original features contain upstream means omitted by the UI pool adapter.
lineage=json.loads((OUT/'projection_lineage.json').read_text());feature_lookup={p['player_id']:p['feature_json'] for p in lineage['features']};rows=e['players'];frozen={p['player_id']:p for p in saved['strategy_runtime']['classic_run_input_snapshot']['payload']['final_solver_rows']}
r['upstream_evidence']={}
for name in ['Jahmyr Gibbs','Garrett Wilson','Chase Brown','Jaylen Warren','DK Metcalf','Amon-Ra St. Brown','Michael Wilson','Isaac TeSlaa']:
 pid=ids[name];feat=feature_lookup[pid]
 fields=['player_games_history','player_roll3_mean','carries_mean_3','targets_mean_3','carry_share_mean_3','target_share_mean_3','team_carries_mean_3','team_targets_mean_3','snap_share_mean_3','pregame_base_carry_share_mean_3','pregame_base_target_share_mean_3','pregame_point_mean_before_opportunity','pregame_opportunity_point_anchor','pregame_opportunity_point_weight','pregame_point_mean_after_opportunity','market_team_point_adjustment','offensive_role_importance','offensive_role_reason','pregame_expected_routes','pregame_expected_targets','pregame_expected_carries','pregame_availability_probability','pregame_role_label','calibration_method','calibration_role','calibration_sample_size','receiving_yards_mean_3','receptions_mean_3','projected_carries','projected_targets']
 r['upstream_evidence'][name]={'player_id':pid,'features':{k:feat.get(k) for k in fields},'frozen_pool':{k:frozen[pid].get(k) for k in fields},'available_feature_keys':sorted(feat)}
r['projection_lineage_hash']=sha256((OUT/'projection_lineage.json').read_bytes()).hexdigest()
source_dir=OUT/'source';source_dir.mkdir(exist_ok=True)
paths=list((ROOT/'backend/app/product_services').glob('*.py'))
needed=set(r['implementation']['source_sha256'])|{'optimizer.py','predictions.py','canonical_projection_inputs.py','cbc_solver.py','rule_library.py','player_context_scoring.py'}
r['source_files']={}
for path in paths:
 if path.name in needed:
  raw=path.read_bytes();(source_dir/path.name).write_bytes(raw);r['source_files'][path.name]=sha256(raw).hexdigest()
# Earlier frozen prelock evidence only; no postgame files are read.
prior=ROOT/'artifacts/classic_discovery_multi_slate/week3_archived_control_check/inputs.json'
if prior.exists():
 data=json.loads(prior.read_text());offsets=Counter((p['position'],round(float(p['p90'])-float(p['projection']),6)) for p in data['eligible_rows'] if p.get('included') and p.get('p90') is not None)
 r['earlier_prelock_control']={'path':str(prior.relative_to(ROOT)),'sha256':sha256(prior.read_bytes()).hexdigest(),'cutoff':data.get('cutoff_at'),'offset_counts':[{'position':pos,'offset':v,'count':n} for (pos,v),n in offsets.items()],'limitation':'Descriptive saved prelock offsets only; no historical solve parity or outcome analysis.'}
(OUT/'results.json').write_text(json.dumps(r,indent=2)+'\n')
