"""Offline research: exact frozen Large-GPP objectives; no database writes or outcomes."""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pulp
from backend.app.product_services import gpp_optimizer as g
from backend.app.product_services.classic_strategy_contract import config_from_dict, implementation_fingerprints, validate_strategy_contract
OUT=ROOT/'artifacts/classic_gibbs_wilson_audit'
OUT.mkdir(exist_ok=True)
(OUT/'solver_logs').mkdir(exist_ok=True)
KEYS=('bd990e1b','139d5544')
runs={k:json.loads((OUT/(k+'_run.json')).read_text()) for k in KEYS}
params={k:v['constraint_config_json'] for k,v in runs.items()}
base=params['139d5544']['effective_strategy_contract']['effective']
validate_strategy_contract(params['139d5544']['effective_strategy_contract'])
players=[g.Player(**{**p,'tags':set(p['tags'])}) for p in base['players']]
config=config_from_dict(base['resolved_config'])
g.tag_players(players,config.tag_thresholds)
lookup={p.player_id:p for p in players}
ids={p.name:p.player_id for p in players}
G=ids['Jahmyr Gibbs']; W=ids['Garrett Wilson']
result={'scope':'RESEARCH_SHADOW; no outcomes; frozen 139d5544 unless labelled otherwise',
 'input_hashes':{k:sha256((OUT/(k+'_run.json')).read_bytes()).hexdigest() for k in KEYS},
 'implementation':implementation_fingerprints(), 'saved_implementation':{k:params[k]['effective_strategy_contract']['implementation'] for k in KEYS},
 'original_contract_hashes':{k:params[k]['effective_strategy_contract']['sha256'] for k in KEYS},
 'identical_ordered_players':params[KEYS[0]]['effective_strategy_contract']['effective']['players']==base['players'],
 'original_configs':{k:params[k]['effective_strategy_contract']['effective']['resolved_config'] for k in KEYS},
 'original_options':{k:params[k]['effective_strategy_contract']['effective']['pipeline_options'] for k in KEYS},
 'solves':{},'sequential':{},'controls':{},'ablations':{}}
# Use the same bundled CBC, additionally retaining its proof and timing log.
current_label=''
def solver(backend):
 assert backend=='bundled'
 return pulp.PULP_CBC_CMD(msg=False,logPath=str(OUT/'solver_logs'/(current_label+'.log')))
g.make_cbc_solver=solver

def solve(label,required=(),cfg=None,remaining=None,excluded=(),template=None,dst=True,extra=None):
 global current_label
 current_label=label
 cfg=deepcopy(cfg or config)
 rules=cfg.stack_rules
 if template is not None: rules=replace(rules,min_pass_catchers=template[0],min_bring_backs=template[1])
 audit={}; start=time.monotonic()
 indexes=g._build_lineup(players,cfg,remaining,[{i for i,p in enumerate(players) if p.player_id in s} for s in excluded],
  stack_rules=rules,required_player_ids=set(required),avoid_dst_opponents=dst,
  enforce_single_te=base['pipeline_options']['enforce_single_te'],solve_audit=audit,**(extra or {}))
 audit['wall_seconds']=time.monotonic()-start
 if indexes is not None:
  roster=[players[i] for i in indexes]; audit['players']=[asdict(p)|{'tags':sorted(p.tags)} for p in roster]
  audit.update(player_ids=[p.player_id for p in roster],salary=sum(p.salary for p in roster),mean=sum(p.projection for p in roster),
   ceiling=sum(p.ceiling for p in roster),ownership=sum(p.ownership or 0 for p in roster),
   team_counts=dict(Counter(p.team for p in roster)),game_counts=dict(Counter(p.game_id for p in roster)))
  assert len(roster)==9 and len(set(audit['player_ids']))==9 and audit['salary']<=50000
  pos=Counter(p.position for p in roster)
  assert pos['QB']==pos['DST']==1 and pos['RB']>=2 and pos['WR']>=3 and pos['TE']>=1
  assert abs(audit['objective_components']['reconciliation_delta'])<1e-7
 else: audit['player_ids']=[]
 result['solves'][label]=audit
 (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
 print(label,audit.get('solver_status'),round(audit.get('objective_score',0),6),flush=True)
 return audit

for key in KEYS:
 saved=params[key]['strategy_runtime']['strategy_contract_audit']['solver_steps']; cfg=config_from_dict(result['original_configs'][key]); steps=[]
 for step in saved:
  label=f'{key}_step{step["step"]}'
  a=solve(label,cfg=cfg,remaining=step['exposure_remaining'],excluded=step['excluded_rosters'],template=step['stack_template'])
  parity={f:a.get(f)==step.get(f) for f in ('feasible_region_sha256','objective_sha256','player_ids')}
  # Player order can differ only in serialization; compare canonical sets separately.
  parity['roster_set']=set(a['player_ids'])==set(step['player_ids'])
  parity['objective_delta']=a.get('objective_score',0)-step['objective_score']
  forced={}
  for name,pid in [('Gibbs',G),('Wilson',W)]:
   b=solve(label+'_'+name,[pid],cfg,step['exposure_remaining'],step['excluded_rosters'],step['stack_template'])
   forced[name]={'solve':label+'_'+name,'gap':a['objective_score']-b['objective_score'] if b['player_ids'] else None}
  steps.append({'step':step['step'],'template':step['stack_template'],'parity':parity,'forced':forced,
    'blocked_players':[lookup[pid].name for pid,n in step['exposure_remaining'].items() if n<=0],
    'original':step})
 result['sequential'][key]=steps

for label,required in [('A',()),('B',(G,)),('C',(W,)),('D',(G,W))]: solve(label,required)
# Every ablation differs from frozen tight-cap A by only its stated rule.
variants={}
def cfg_variant(name,**changes):
 c=deepcopy(config)
 for path,value in changes.items():
  obj,attr=path.split('__'); setattr(getattr(c,obj),attr,value)
 variants[name]=c
cfg_variant('team_cap4',stack_rules__max_from_team=4)
cfg_variant('game_cap5',stack_rules__max_from_game=5)
cfg_variant('no_mandatory_stack',stack_rules__min_pass_catchers=0)
cfg_variant('no_correlation',objective_weights__correlation=0)
cfg_variant('no_ownership_cap',tag_caps__max_total_ownership=None)
cfg_variant('no_chalk_cap',tag_caps__max_chalk=9)
cfg_variant('no_punt_cap',tag_caps__max_punts=9)
for name,cfg in variants.items():
 result['ablations'][name]={}
 for suffix,required in [('A',()),('B',(G,)),('C',(W,))]:
  label=name+'_'+suffix; solve(label,required,cfg); result['ablations'][name][suffix]=label
solve('dst_allowed_A',dst=False);solve('dst_allowed_B',[G],dst=False)
# Disable environmental objective additions uniformly; projection truth is unchanged.
original_context=[p.optimizer_context_adjustment for p in players]
for p in players:p.optimizer_context_adjustment=0
solve('no_context_A');solve('no_context_B',[G]);solve('no_context_C',[W])
for p,v in zip(players,original_context):p.optimizer_context_adjustment=v
# Research-only continuation: retain overlap restriction, lift global exposure, or keep exposures and lift overlap.
for variant in ['fixed_template','no_exposure','no_overlap']:
 used=Counter();excluded=[]; portfolio=[]
 for step in range(5):
  cfg=deepcopy(config)
  if variant=='no_overlap':cfg.uniqueness_overlap=8
  remaining={p.player_id:(5 if variant=='no_exposure' else 4)-used[p.player_id] for p in players}
  template=(1,0) if variant=='fixed_template' else config.stack_templates[step%len(config.stack_templates)]
  a=solve(f'{variant}_step{step+1}',cfg=cfg,remaining=remaining,excluded=excluded,template=template)
  if not a['player_ids']:break
  used.update(a['player_ids']);excluded.append(set(a['player_ids']));portfolio.append(f'{variant}_step{step+1}')
 result['ablations'][variant]=portfolio
# Small control group chosen from prelock mean and archived exposure only.
freq=Counter(pid for s in result['sequential']['139d5544'] for pid in s['original']['player_ids'])
controls=[]
for pos in ['RB','WR']:
 ranked=sorted((p for p in players if p.position==pos),key=lambda p:p.projection,reverse=True)
 controls += [p for p in ranked if freq[p.player_id]==0][:2]
controls += [lookup[pid] for pid,n in freq.most_common(4)]
controls += [p for p in sorted(players,key=lambda p:p.projection,reverse=True) if 4500<=p.salary<=7000 and freq[p.player_id]<=1][:2]
for p in {p.player_id:p for p in controls}.values():
 label='control_'+p.player_id
 a=solve(label,[p.player_id]); result['controls'][p.name]={'salary':p.salary,'mean':p.projection,'ceiling':p.ceiling,'frequency':freq[p.player_id],'solve':label,'gap':result['solves']['A']['objective_score']-a['objective_score'] if a['player_ids'] else None}
# Positional diagnostics; modeled additive value excludes lineup-dependent correlation.
mp=max(p.projection+p.optimizer_context_adjustment for p in players); mc=max(p.ceiling+p.optimizer_context_adjustment for p in players)
def additive(p):return .35*(p.projection+p.optimizer_context_adjustment)/mp+.45*(p.ceiling+p.optimizer_context_adjustment)/mc
result['player_diagnostics']=[]
for p in players:
 peers=[q for q in players if q.position==p.position]
 result['player_diagnostics'].append(asdict(p)|{'tags':sorted(p.tags),'frequency':freq[p.player_id], 'mean_rank':1+sum(q.projection>p.projection for q in peers),
 'ceiling_rank':1+sum(q.ceiling>p.ceiling for q in peers),'additive_rank':1+sum(additive(q)>additive(p) for q in peers),
 'additive_score':additive(p),'additive_per_k':additive(p)/(p.salary/1000)})
result['calibration_offsets']={pos:dict(Counter(round(p.ceiling-p.projection,8) for p in players if p.position==pos)) for pos in ['QB','RB','WR','TE','DST']}
(OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
