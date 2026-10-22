"""Public same-pool frozen-model feature-ablation comparison; research only."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,re
from pathlib import Path
from sqlalchemy import text
from . import full_game_breadth_replay as full
from . import joint_portfolio_replay as joint
from .analyst_shadow import digest
from .lineup_ablation_research import predict
from .lineup_top_decile_research import lineup_features
from .scenario_breadth import select_pool,signature
from .scenario_breadth_replay import read_replay,decorate,game_dependencies
from .scenario_allocation import dependence_audit

ROOT=full.REPO/'artifacts/lineup_ablation_replays'
EXPERIMENT=full.REPO/'research/lineup_feature_ablation_20261018/v1'


def read(replay_id):return read_replay(replay_id,directory=ROOT)


def list_replays():
    rows=[]
    for path in ROOT.glob('*.json'):
        if not re.fullmatch(r'[a-f0-9]{64}',path.stem):continue
        result=read(path.stem);rows.append({k:result[k]for k in ['replay_id','source_optimizer_run_id','scope','created_at','status']})
    return {'rows':rows}


def build(session,parent_id):
    try:source=joint.read(parent_id);root=full.read(source['parent_replay_id'])
    except LookupError:source=full.read(parent_id);root=source
    if root['generation'].get('scoring_contract')!='draftkings_nfl_typed_v2_lost_fumble_minus_one':raise ValueError('Requires corrected DraftKings-scored full-game baseline')
    row=session.execute(text('SELECT constraint_config_json FROM target.optimizer_run WHERE optimizer_run_id=:id'),{'id':source['source_optimizer_run_id']}).mappings().first()
    if not row:raise LookupError('Frozen source optimizer configuration missing')
    config=row['constraint_config_json']
    if digest(config)!=root['input_identity']['source_config_sha256']:raise ValueError('Original source configuration changed')
    manifest=json.loads((EXPERIMENT/'model_manifest.json').read_text());refs=[r for r in manifest['models']if r['test_week']==source['scope']['week']]
    if len(refs)!=8:raise ValueError('Complete frozen Classic ablation models unavailable')
    models=[]
    for ref in refs:
        path=(full.REPO/ref['path']).resolve()
        if not path.is_relative_to(EXPERIMENT) or hashlib.sha256(path.read_bytes()).hexdigest()!=ref['sha256']:raise ValueError('Ablation model source/hash mismatch')
        model=json.loads(path.read_text())
        if max(model['train_weeks'])>=source['scope']['week']:raise ValueError('Evaluation-week training leakage')
        models.append(model)
    identity={'contract':'lineup_feature_ablation_same_pool_v1','parent_replay_id':parent_id,'parent_artifact_sha256':source['artifact_sha256'],'manifest_sha256':digest(manifest),
        'implementation_sha256':digest({n:(Path(__file__).parent/n).read_text()for n in ['lineup_ablation_research.py','lineup_ablation_replay.py','analyst_scenarios.py','scenario_breadth.py']})}
    replay_id=digest(identity);path=ROOT/(replay_id+'.json')
    if path.exists():return read(replay_id)
    report=config['strategy_runtime']['football_analyst'];snapshot=report['input_snapshot'];rows=snapshot['players'];plan=report['scenario_allocation_plan'];pool=deepcopy(source['candidates']);comparisons=deepcopy(source['comparisons'])
    worlds=[w for w in report['scenario_definitions']if w['scenario_id']in{i['idea_id']for i in plan['ideas']}]
    _,inputs=full.load_inputs(source['source_optimizer_run_id']);feature=inputs['features']['rows']
    for model in models:
        name=model['family']+'_'+model['treatment'];values=[predict(model,lineup_features([feature[p['player_master_id']]for p in c['roster']],'classic',rich=model['family']=='rich'))for c in pool]
        selected,audit=select_pool(deepcopy(pool),worlds,rows,{**config,'data_cutoff_at':snapshot['decision_at']},source['requested'],plan,
            objective='EXTERNAL_LINEUP_SCORE',candidate_utilities=values,research_solver_seconds=30)
        score={c['candidate_id']:v for c,v in zip(pool,values)}
        for c in selected:c['research_lineup_model_score']=score[c['candidate_id']]
        cs=decorate(selected,rows)
        comparisons[name]={'selected':cs,'selection':audit,'achieved':len(cs),'requested':source['requested'],'summed_baseline_mean':sum(c['baseline_mean']for c in cs),
            'dependencies':{**dependence_audit(cs,rows,source['requested']),**game_dependencies(cs,rows)},'model_id':model['model_id'],'cohort_sha256':model['cohort_sha256'],'candidate_scores':score,
            'base_control_correspondence':{'same_selected_rosters':{signature(c)for c in cs}=={signature(c)for c in source['comparisons']['top10_'+model['family']]['selected']}}if model['treatment']=='original'else None}
    result={**source,'replay_id':replay_id,'input_identity':identity,'parent_replay_id':parent_id,'contract_id':identity['contract'],'created_at':datetime.now(timezone.utc).isoformat(),
        'comparisons':comparisons,'status':'completed'if all(c['achieved']==source['requested']for c in comparisons.values())else'underfilled',
        'generation':{'variants':0,'attempts':[],'new_generation':False},'assumptions':source['assumptions']+['24models frozen before evaluation; six retrained original controls reproduced existing coefficients',
          'Salary/stack-group ablations are retrained; correlated projection/workload/market proxies remain, so feature effects are not causal',
          'Exact corrected canonical candidate pool/settings shared by every policy; no new candidate generation or projection changes'],
        'outcomes_used':False,'live_promoted':False}
    result.pop('artifact_sha256',None);result['artifact_sha256']=digest(result);ROOT.mkdir(parents=True,exist_ok=True)
    with path.open('x')as f:json.dump(result,f,indent=2,allow_nan=False)
    return result
