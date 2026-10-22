"""Bounded immutable pool-evidence experiment; no operational lineup writes/fitting."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import hashlib
from sqlalchemy import text
from . import full_game_breadth_replay as full
from .analyst_shadow import digest, validate_snapshot
from .full_game_breadth import build_states, generate, legacy_select, role_universe
from .scenario_breadth import signature, select_pool
from .scenario_breadth_replay import decorate, game_dependencies, read_replay
from .scenario_allocation import dependence_audit
from .lineup_top_decile_research import lineup_features, predict_artifact

EXPERIMENT=full.REPO/'research/workload_evidence_semantics_20261019/generation_v1'
OLD='77282e4a9128ca1bce3de38b226ff0c5c4eb84985be323851bf52ddfde20fcde'


def build_from_config(run_id, config, *, directory=None):
    manifest=json.loads((EXPERIMENT/'inputs_manifest.json').read_text())
    if run_id!=manifest['source_optimizer_run_id']:raise ValueError('No reviewed workload experiment for this source')
    for ref in manifest['files'].values():
        path=(full.REPO/ref['path']).resolve()
        if not path.is_relative_to(full.REPO/'research') or hashlib.sha256(path.read_bytes()).hexdigest()!=ref['sha256']:raise ValueError('Workload research input hash mismatch')
    old=full.read(OLD)
    if digest(config)!=old['input_identity']['source_config_sha256']:raise ValueError('Workload baseline source config mismatch')
    _,inputs=full.load_inputs(run_id)
    report=config['strategy_runtime']['football_analyst'];snapshot=report['input_snapshot'];validate_snapshot(snapshot)
    evidence=json.loads((full.REPO/manifest['files']['v2_evidence']['path']).read_text())
    identity={'contract':'workload_original_history_generator_v1','source_optimizer_run_id':run_id,'source_config_sha256':digest(config),'old_replay_id':OLD,'old_artifact_sha256':old['artifact_sha256'],'manifest_sha256':digest(manifest),'seed':7,'state_budget':32,'generation_seconds':2,'selection_seconds':5,'threads':1,'implementation_sha256':digest({n:(Path(__file__).parent/n).read_text() for n in ['workload_semantics_replay.py','full_game_breadth.py','analyst_scenarios.py','scenario_allocation.py','workload_evidence.py']})}
    replay_id=digest(identity);root=Path(directory)if directory else full.ROOT;path=root/(replay_id+'.json')
    if path.exists():return read_replay(replay_id,directory=root)
    rows=deepcopy(snapshot['players']);original_full=deepcopy(config['strategy_runtime']['player_pool']['rows']);corrected=deepcopy(original_full)
    if set(evidence)!={r['player_id']for r in corrected} or len(corrected)!=513:raise ValueError('Full workload opportunity universe mismatch')
    for row in corrected:row['workload_evidence']=deepcopy(evidence[row['player_id']])
    oldstates,oldaudit=build_states(inputs['library'],original_full,rows,seed=7)
    old_evidence=json.loads((full.ROOT/(OLD+'.states.json')).read_text())
    if digest(oldstates)!=digest(old_evidence['states']):raise ValueError('Original physical states not exactly reproduced; no baseline reuse')
    newstates,newaudit=build_states(inputs['library'],corrected,rows,seed=7)
    if [s['state_id']for s in oldstates]!=[s['state_id']for s in newstates]:raise ValueError('State identity/budget drift')
    chosen_ids={s['state_id']for s in oldstates[:32]}
    baseline=[deepcopy(c)for c in old['candidates']if c.get('generation_state_id')in chosen_ids]
    statuses={a['state_id']:a['solver_status']for a in old['generation']['attempts']}
    if len(baseline)!=32 or any(statuses[s]!='Optimal'for s in chosen_ids):raise ValueError('Exact optimal baseline candidates unavailable')
    # No missing feature actor can acquire a skill role through another actor.
    recovered=json.loads((full.REPO/manifest['files']['recovered_features']['path']).read_text());missing=set(evidence)-{r['player_id']for r in recovered['rows']}
    universe,_=role_universe(corrected,rows);mapped={r['player_id']for values in universe.values()for r,_,_ in values}
    if any(r['player_id']in mapped and r['player_id']in missing and r['position']in {'QB','RB','WR','TE'}for r in corrected):raise ValueError('Unknown workload role leaked into mapped opportunity')
    params={**config,'data_cutoff_at':snapshot['decision_at']};requested=config['num_lineups'];plan=report['scenario_allocation_plan'];worlds=[w for w in report['scenario_definitions']if w['scenario_id']in{i['idea_id']for i in plan['ideas']}]
    reproduced,reproduction=legacy_select(deepcopy(report['candidates']),worlds,rows,params,requested,plan)
    if [signature(c)for c in reproduced]!=[signature(c)for c in report['candidates']]:raise ValueError('Legacy original ordered controls not reproduced')
    fresh,generation=generate(snapshot,newstates[:32],params,research_solver_seconds=2)
    fixed=deepcopy(inputs['original_control']['candidates'])
    def pool(extra):
        groups={}
        for c in deepcopy(fixed)+extra:groups.setdefault(signature(c),[]).append(c)
        result=[]
        for variants in groups.values():
            c=deepcopy(variants[0]);c['source_candidate_ids']=[v['candidate_id']for v in variants];result.append(c)
        return result
    oldpool,newpool=pool(baseline),pool(fresh)
    def summarize(cs,audit):
        decorated=decorate(cs,rows)
        return {'selected':decorated,'selection':audit,'achieved':len(cs),'requested':requested,'summed_baseline_mean':sum(c['baseline_mean']for c in decorated),'dependencies':{**dependence_audit(cs,rows,requested),**game_dependencies(cs,rows)},'joint_stress_best_roster_scores':{arm+':'+s['state_id']:max((sum(s['points'][p['player_master_id']]for p in c['roster'])for c in cs),default=None)for arm,states in [('v1',oldstates),('v2',newstates)]for s in states}}
    def compare(candidates):
        result={};cs,audit=legacy_select(candidates,worlds,rows,params,requested,plan);result['legacy_sequential_adapted']=summarize(cs,audit)
        cs,audit=select_pool(deepcopy(candidates),worlds,rows,params,requested,plan,objective='BASELINE_MEAN',research_solver_seconds=5);result['highest_mean']=summarize(cs,audit)
        for name,rich in [('core',False),('rich',True)]:
            model=inputs[name+'_model']
            if max(model['train_weeks'])>=snapshot['scope']['week']:raise ValueError('Frozen model includes evaluation week')
            features=inputs['features']['rows'];values=[predict_artifact(model,lineup_features([features[p['player_master_id']]for p in c['roster']],'classic',rich=rich))for c in candidates]
            cs,audit=select_pool(deepcopy(candidates),worlds,rows,params,requested,plan,objective='EXTERNAL_LINEUP_SCORE',candidate_utilities=values,research_solver_seconds=5);result['top10_'+name]=summarize(cs,audit)
        return result
    before=compare(oldpool);after=compare(newpool)
    result={'replay_id':replay_id,'input_identity':identity,'source_optimizer_run_id':run_id,'scope':snapshot['scope'],'created_at':datetime.now(timezone.utc).isoformat(),'status':'completed'if len(fresh)==32 and all(v['achieved']==requested for v in after.values())else'underfilled','research_only':True,'entry_clearance':False,'outcomes_used':False,'outcomes_previously_inspected':True,'live_promoted':False,'source_data_cutoff':snapshot['decision_at'],'settings_sha256':old['settings_sha256'],'requested':requested,'chronology_status':'Original source config and physical v1 states reproduced; v2 uses recovered original features as separately versioned research child; independent pregame provider/code chronology not certified','generation':generation,'candidate_variant_count':len(fixed)+len(fresh),'distinct_canonical_roster_count':len(newpool),'original_distinct_roster_count':len(fixed),'candidates':decorate(newpool,rows),'original_selected':decorate(report['candidates'],rows),'comparisons':after,'saved_v1_comparisons':before,'saved_v1_candidates':decorate(oldpool,rows),'legacy_reproduction':reproduction,'state_audit':newaudit,'state_design':[{k:v for k,v in s.items()if k!='games'}for s in newstates],'baseline_reuse':{'exact_states_reproduced':True,'solver_status':'Optimal','candidates':len(baseline),'candidate_state_ids':sorted(chosen_ids)},'evidence_audit':{'actors':len(corrected),'eligible':len(rows),'excluded':sum(not r['included']for r in corrected),'missing_original_features':len(missing),'unknown_skill_not_mapped':True,'model_preferences_unchanged':[{k:v for k,v in r.items()if k!='workload_evidence'}for r in corrected]==[{k:v for k,v in r.items()if k!='workload_evidence'}for r in original_full]},'assumptions':newaudit['limitations']+['Only full opportunity pool evidence changed; actual Analyst packet, saved scenario worlds and trained lineup feature inputs unchanged','32 deterministic original-order generation states per arm, plus same original38controls; at most38new bounded solver calls total','Observed history determines rank/context, never authored future count forecasts','Both arms selectors compare same canonical pool within arm; differing generation pools are a separate treatment','Stress outcomes not calibrated probabilities; old adapted finite-pool policy is not original ILP search','Known Week6 outcomes retrospective; no target actuals accepted by builder; no live model/default/lineup changes']}
    state_receipt={'input_identity':identity,'states':newstates,'old_states':oldstates,'state_audit':newaudit};result['state_evidence_sha256']=digest(state_receipt);result['artifact_sha256']=digest(result);root.mkdir(parents=True,exist_ok=True)
    with(root/(replay_id+'.states.json')).open('x')as handle:handle.write(json.dumps(state_receipt,allow_nan=False))
    with path.open('x')as handle:handle.write(json.dumps(result,indent=2,allow_nan=False))
    return result


def build(session,run_id):
    row=session.execute(text('SELECT constraint_config_json FROM target.optimizer_run WHERE optimizer_run_id=:id'),{'id':run_id}).mappings().first()
    if not row:raise LookupError('Saved optimizer run not found')
    # Explicit immutable correction of the completed decision, not regeneration.
    # The only correction is source-control variants versus canonical rosters.
    parent_id='ceff554721d1896b36343eba49fbec0f9a4ba2069d30dbaa2c648c70b39c578d'
    if (full.ROOT/(parent_id+'.json')).exists():
        parent=full.read(parent_id)
        manifest=json.loads((EXPERIMENT/'inputs_manifest.json').read_text())
        if parent['input_identity']['source_config_sha256']!=digest(row['constraint_config_json']) or parent['input_identity']['manifest_sha256']!=digest(manifest):
            raise ValueError('Metadata correction source lineage mismatch')
        _,inputs=full.load_inputs(run_id)
        corrected_count=len({signature(c)for c in inputs['original_control']['candidates']})
        identity={**parent['input_identity'],'contract':'workload_generator_control_count_erratum_v1','parent_replay_id':parent_id,'parent_artifact_sha256':parent['artifact_sha256'],'correction':{'original_distinct_roster_count':corrected_count},'decision_reused_without_new_solves':True}
        replay_id=digest(identity);path=full.ROOT/(replay_id+'.json')
        if path.exists():return full.read(replay_id)
        result=deepcopy(parent);result.update(replay_id=replay_id,input_identity=identity,created_at=datetime.now(timezone.utc).isoformat(),original_distinct_roster_count=corrected_count,original_control_variant_count=len(inputs['original_control']['candidates']),metadata_erratum=identity)
        receipt=json.loads((full.ROOT/(parent_id+'.states.json')).read_text());receipt['input_identity']=identity
        result['state_evidence_sha256']=digest(receipt);result['artifact_sha256']=digest({k:v for k,v in result.items()if k!='artifact_sha256'})
        with (full.ROOT/(replay_id+'.states.json')).open('x')as handle:handle.write(json.dumps(receipt,allow_nan=False))
        with path.open('x')as handle:handle.write(json.dumps(result,indent=2,allow_nan=False))
        return result
    return build_from_config(run_id,row['constraint_config_json'])
