"""Probability-free shared-state portfolio research on an already frozen pool."""
from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
import re
from sqlalchemy import text

from .analyst_shadow import digest
from .scenario_breadth import select_pool
from .scenario_breadth_replay import read_replay,decorate,game_dependencies
from .scenario_allocation import dependence_audit
from . import full_game_breadth_replay as parent

ROOT=parent.REPO/'artifacts/joint_portfolio_replays'
PROTOCOL=parent.REPO/'research/joint_selection_role_support_20261018/v1/PROTOCOL.md'


def read(replay_id):return read_replay(replay_id,directory=ROOT)


def list_replays():
    rows=[]
    for path in ROOT.glob('*.json'):
        if not re.fullmatch(r'[a-f0-9]{64}',path.stem):continue
        result=read(path.stem);rows.append({k:result[k] for k in ['replay_id','source_optimizer_run_id','scope','created_at','status']})
    return {'rows':rows}


def build(session,parent_id):
    source=parent.read(parent_id)
    row=session.execute(text('SELECT constraint_config_json FROM target.optimizer_run WHERE optimizer_run_id=:id'),{'id':source['source_optimizer_run_id']}).mappings().first()
    if not row:raise LookupError('Original saved source config unavailable')
    config=row['constraint_config_json']
    if digest(config)!=source['input_identity']['source_config_sha256']:raise ValueError('Original source configuration changed')
    identity={'contract':'joint_worst_relative_coverage_research_v1','parent_replay_id':parent_id,'parent_artifact_sha256':source['artifact_sha256'],
        'protocol_sha256':digest(PROTOCOL.read_text()),'implementation_sha256':digest({n:(Path(__file__).parent/n).read_text() for n in ['analyst_scenarios.py','scenario_breadth.py','joint_portfolio_replay.py','joint_coverage_solver.py']})}
    replay_id=digest(identity);path=ROOT/(replay_id+'.json')
    if path.exists():return read(replay_id)
    report=config['strategy_runtime']['football_analyst'];snapshot=report['input_snapshot'];rows=snapshot['players'];plan=report['scenario_allocation_plan'];pool=deepcopy(source['candidates'])
    worlds=[w for w in report['scenario_definitions']if w['scenario_id']in{i['idea_id']for i in plan['ideas']}]
    states=json.loads((parent.ROOT/(parent_id+'.states.json')).read_text())['states']
    matrix={s['state_id']:[sum(s['points'][p['player_master_id']] for p in c['roster'])for c in pool] for s in states}
    selected,audit=select_pool(pool,worlds,rows,{**config,'data_cutoff_at':snapshot['decision_at']},config['num_lineups'],plan,
        objective='JOINT_WORST_REGRET',joint_state_scores=matrix)
    decorated=decorate(selected,rows);comparisons=deepcopy(source['comparisons'])
    comparisons['joint_worst_regret']={'selected':decorated,'selection':audit,'achieved':len(decorated),'requested':source['requested'],
        'summed_baseline_mean':sum(c['baseline_mean']for c in decorated),
        'dependencies':{**dependence_audit(decorated,rows,source['requested']),**game_dependencies(decorated,rows)},
        'joint_stress_best_roster_scores':{s['state_id']:max((sum(s['points'][p['player_master_id']] for p in c['roster'])for c in decorated),default=None)for s in states},
        'joint_score_meaning':'Worst relative best-roster coverage over a physical stress uncertainty set; no probabilities'}
    for comparison in comparisons.values():
        comparison['worst_relative_best_roster_coverage']=min(comparison['joint_stress_best_roster_scores'][sid]/max(values) for sid,values in matrix.items()) if comparison['achieved'] else None
    achieved=comparisons['joint_worst_regret']['worst_relative_best_roster_coverage']
    if audit.get('joint_worst_relative_coverage') is not None and achieved is not None and achieved+1e-6<audit['joint_worst_relative_coverage']:raise ValueError('Independent achieved joint-coverage audit failed')
    result={**source,'replay_id':replay_id,'input_identity':identity,'parent_replay_id':parent_id,'contract_id':identity['contract'],
        'created_at':datetime.now(timezone.utc).isoformat(),'status':'completed'if len(decorated)==source['requested']else'underfilled',
        'comparisons':comparisons,'generation':{'variants':0,'attempts':[],'source_generation_variants':source['generation']['variants'],'new_generation':False},
        'assumptions':source['assumptions']+['Selector-only: exact parent canonical pool and states; original four choices retained as frozen controls',
          'Probability-free worst-relative-coverage objective, then original mean tie-break; no calibrated expected value or joint P90',
          'Role-share transport temporal trial did not establish improvement; source states remain conditional uncalibrated stresses'],
        'outcomes_used':False,'live_promoted':False}
    result.pop('artifact_sha256',None);result['artifact_sha256']=digest(result);ROOT.mkdir(parents=True,exist_ok=True)
    with path.open('x')as f:json.dump(result,f,indent=2,allow_nan=False)
    return result
