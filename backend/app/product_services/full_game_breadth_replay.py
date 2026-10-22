"""Public immutable full-game research comparison; no optimizer writes or outcomes."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import re
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

from .analyst_shadow import digest,validate_snapshot
from .full_game_breadth import CONTRACT,build_states,generate,legacy_select
from .lineup_top_decile_research import lineup_features,predict_artifact
from .scenario_allocation import dependence_audit
from .scenario_breadth import signature,select_pool
from .scenario_breadth_replay import decorate,game_dependencies,read_replay

REPO=Path(__file__).resolve().parents[3]
EXPERIMENT=REPO/'research/full_game_candidate_breadth_20261018/v1'
ROOT=REPO/'artifacts/full_game_breadth_replays'


def read(replay_id):
    result=read_replay(replay_id,directory=ROOT)
    evidence=json.loads((ROOT/(replay_id+'.states.json')).read_text())
    if digest(evidence)!=result['state_evidence_sha256']:raise ValueError('Full-game state evidence integrity mismatch')
    return result


def list_replays():
    rows=[]
    for path in ROOT.glob('*.json'):
        if not re.fullmatch(r'[a-f0-9]{64}',path.stem):continue
        result=read(path.stem)
        rows.append({k:result[k] for k in ['replay_id','source_optimizer_run_id','scope','created_at','status']})
    return {'rows':rows}


def load_inputs(run_id):
    manifest=json.loads((EXPERIMENT/'inputs_manifest.json').read_text())
    if manifest['source_optimizer_run_id']!=run_id:raise ValueError('No frozen, reviewed experiment inputs registered for this source run')
    inputs={}
    for key,ref in manifest['files'].items():
        path=(REPO/ref['path']).resolve()
        if not path.is_relative_to(REPO/'research') or hashlib.sha256(path.read_bytes()).hexdigest()!=ref['sha256']:raise ValueError('Frozen research source hash mismatch')
        inputs[key]=path.read_text() if key=='protocol' else json.loads(path.read_text())
    return manifest,inputs


def build_from_config(run_id,config,*,directory=None):
    UUID(run_id);manifest,inputs=load_inputs(run_id)
    report=config['strategy_runtime']['football_analyst'];snapshot=report['input_snapshot'];validate_snapshot(snapshot)
    if snapshot['scope']['format']!='CLASSIC' or report['portfolio_mode']!='SCENARIO_FIRST':raise ValueError('Requires frozen Classic scenario-first legal model')
    code_names=['full_game_breadth.py','full_game_breadth_replay.py','scenario_breadth.py','scenario_allocation.py','analyst_scenarios.py','lineup_top_decile_research.py']
    identity={'contract':CONTRACT,'source_optimizer_run_id':run_id,'source_config_sha256':digest(config),
        'snapshot_sha256':snapshot['sha256'],'inputs_manifest':manifest,'implementation_sha256':digest({n:(Path(__file__).parent/n).read_text() for n in code_names}),
        'settings_sha256':digest({k:v for k,v in config.items() if k!='strategy_runtime'}),'seed':7}
    replay_id=digest(identity);root=Path(directory) if directory else ROOT
    if (root/(replay_id+'.json')).exists():return read_replay(replay_id,directory=root)
    rows=deepcopy(snapshot['players']);plan=report['scenario_allocation_plan'];params={**config,'data_cutoff_at':snapshot['decision_at']};requested=config['num_lineups']
    worlds=[w for w in report['scenario_definitions'] if w['scenario_id'] in {i['idea_id'] for i in plan['ideas']}]
    original=deepcopy(report['candidates']);old=inputs['original_control']
    if old['source_optimizer_run_id']!=run_id or old['settings_sha256']!=identity['settings_sha256']:raise ValueError('Original control scope/settings mismatch')
    # Fail before new generation if the declared old adaptation cannot reproduce the original five.
    reproduced,reproduction=legacy_select(original,worlds,rows,params,requested,plan)
    if [signature(c) for c in reproduced]!=[signature(c) for c in original]:raise ValueError('Legacy adaptation does not reproduce original saved ordered portfolio')
    states,state_audit=build_states(inputs['library'],config['strategy_runtime']['player_pool']['rows'],rows)
    fresh,generation=generate(snapshot,states,params)
    variants=deepcopy(old['candidates'])+fresh
    # Preserve all source variants, select once per canonical roster.
    groups={}
    for c in variants:groups.setdefault(signature(c),[]).append(c)
    pool=[]
    for variants_for_roster in groups.values():
        candidate=deepcopy(variants_for_roster[0]);candidate['source_candidate_ids']=[c['candidate_id'] for c in variants_for_roster];pool.append(candidate)
    def summarize(cs,audit):
        decorated=decorate(cs,rows)
        # Sensitivities are full joint scores. Designed states have no calibrated frequencies.
        state_scores={s['state_id']:[sum(s['points'][p['player_master_id']] for p in c['roster']) for c in decorated] for s in states}
        return {'selected':decorated,'selection':audit,'achieved':len(cs),'requested':requested,
            'summed_baseline_mean':sum(c['baseline_mean'] for c in decorated),
            'dependencies':{**dependence_audit(cs,rows,requested),**game_dependencies(cs,rows)},
            'joint_stress_best_roster_scores':{k:max(v,default=None) for k,v in state_scores.items()},
            'joint_stress_scores':state_scores,'joint_score_meaning':'Conditional complete-game scores, not lineup P90 or probabilities'}
    def compare(candidates):
        result={}
        selected,audit=legacy_select(candidates,worlds,rows,params,requested,plan);result['legacy_sequential_adapted']=summarize(selected,audit)
        selected,audit=select_pool(deepcopy(candidates),worlds,rows,params,requested,plan,objective='BASELINE_MEAN');result['highest_mean']=summarize(selected,audit)
        for name,rich in [('core',False),('rich',True)]:
            model=inputs[name+'_model']
            if max(model['train_weeks'])>=snapshot['scope']['week']:raise ValueError('Evaluation-week data in frozen model')
            feature_rows=inputs['features']['rows'];values=[predict_artifact(model,lineup_features([feature_rows[p['player_master_id']] for p in c['roster']],'classic',rich=rich)) for c in candidates]
            selected,audit=select_pool(deepcopy(candidates),worlds,rows,params,requested,plan,objective='EXTERNAL_LINEUP_SCORE',candidate_utilities=values)
            scores={c['candidate_id']:v for c,v in zip(candidates,values)}
            for c in selected:c['research_lineup_model_score']=scores[c['candidate_id']]
            result['top10_'+name]=summarize(selected,audit);result['top10_'+name]['model_scores']=scores
        return result
    # Both comparison decisions are completed and persisted before any evaluation labels are loaded.
    control_pool=list({signature(c):c for c in old['candidates']}.values())
    controls=compare(control_pool);comparisons=compare(pool)
    result={'replay_id':replay_id,'input_identity':identity,'source_optimizer_run_id':run_id,'scope':snapshot['scope'],
        'created_at':datetime.now(timezone.utc).isoformat(),'status':'completed' if all(c['achieved']==requested for c in comparisons.values()) else 'underfilled',
        'research_only':True,'entry_clearance':False,'outcomes_used':False,'outcomes_previously_inspected':True,'live_promoted':False,
        'source_data_cutoff':snapshot['decision_at'],'settings_sha256':identity['settings_sha256'],'requested':requested,
        'chronology_status':'Frozen stored inputs and revised historical captures; independent original source/code chronology not certified; retrospective only',
        'generation':generation,'candidate_variant_count':len(variants),'distinct_canonical_roster_count':len(pool),
        'original_distinct_roster_count':len(control_pool),'candidates':decorate(pool,rows),'original_selected':decorate(original,rows),
        'comparisons':comparisons,'original38_comparisons':controls,'legacy_reproduction':reproduction,
        'state_audit':state_audit,'state_design':[{k:v for k,v in s.items() if k!='games'} for s in states],
        'assumptions':state_audit['limitations']+['No actuals/ranks/field cutoff accepted by build service',
          'Top10 model scores are uncalibrated research propensities, not cash or win probabilities',
          'Old policy adapted to finite candidates; challenger/teammate generation not re-run',
          'All selectors retain the existing hard portfolio controls; legacy also retains its story-construction rules',
          'No live default, saved optimizer lineup, settings or projection changed']}
    # Retain complete actor accounting separately, not in the public roster payload.
    evidence={'input_identity':identity,'states':states,'state_audit':state_audit};result['state_evidence_sha256']=digest(evidence)
    result['artifact_sha256']=digest(result);root.mkdir(parents=True,exist_ok=True)
    evidence_path=root/(replay_id+'.states.json');path=root/(replay_id+'.json')
    if evidence_path.exists():
        if digest(json.loads(evidence_path.read_text()))!=result['state_evidence_sha256']:raise ValueError('Existing state evidence differs; not overwritten')
    else:
        with evidence_path.open('x') as handle:handle.write(json.dumps(evidence,allow_nan=False))
    with path.open('x') as handle:handle.write(json.dumps(result,indent=2,allow_nan=False))
    return result


def build(session,run_id):
    UUID(run_id)
    row=session.execute(text('SELECT constraint_config_json FROM target.optimizer_run WHERE optimizer_run_id = :id'),{'id':run_id}).mappings().first()
    if not row:raise LookupError('Saved optimizer run not found')
    return build_from_config(run_id,row['constraint_config_json'])
