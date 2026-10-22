"""Frozen targeted-smoke planning/reporting; no source requests or live consumers."""
from collections import Counter
from copy import deepcopy
import hashlib,json
import numpy as np
from backend.app.product_services.game_progression_runtime import STATS

RUN_ID='scenario04_changed_mechanics_v1'
ARM_ORDER=('contextual','control')
REPAIRED='DISPATCH_CHANGED_SOURCE_TRANSITION'
UNFINISHED='DISPATCH_PRIOR_CAP_OR_FAILURE'
SKIP_SOURCE='SKIP_UNCHANGED_SOURCE_UNKNOWN'
SKIP_CENSOR='SKIP_UNCHANGED_CENSORED_UNKNOWN'
SKIP_COMPLETE='SKIP_ORIGINAL_COMPLETE'
DISPATCH={REPAIRED,UNFINISHED}

def key(row):return row['game_id'],row['path'],row['arm']

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def apply_audit(library,audit):
    """Copy only documented changes from the all-TRAIN source audit."""
    if not audit['kernel_inputs_and_production_unchanged']or not audit['all_unknown_candidates_retained']:raise ValueError('Lossless audited kernel required')
    out=deepcopy(library);lookup={c['cycle_id']:c for c in out['cycles']}
    if len(lookup)!=len(out['cycles']):raise ValueError('Unique native cycles required')
    proofs=audit['source_evidence_ledger'];ids=[r['cycle_id']for r in proofs]
    if len(set(ids))!=len(ids)or set(ids)!=set(audit['newly_source_certified_cycles'])or audit['partially_repaired_cycles']:raise ValueError('Exact fully certified audit set required')
    for row in proofs:
        c=lookup[row['cycle_id']]
        discharged={p['discharges']for p in row['proofs']}
        if c['state_certified']or not row['source_state_certified']or not row['proofs']or not set(c['barriers'])<=discharged:raise ValueError('Explicit matching source proof required')
        if any(p['game_id']+':'+p['play_id']!=c['cycle_id']for p in row['proofs']):raise ValueError('Native proof identity differs')
        c.update(state_certified=True,barriers=[],source_transition_proofs=deepcopy(row['proofs']))
    if sum(c['state_certified']for c in out['cycles'])!=audit['changed_state_certified']:raise ValueError('Audited certified cardinality differs')
    return out

def plan_paths(prior,dispositions,games,paths_per_game=32):
    expected={(g['game_id'],p,a)for g in games for p in range(paths_per_game)for a in ARM_ORDER}
    old={key(r):r for r in prior};audit={key(r):r for r in dispositions}
    if len(old)!=len(prior)or len(audit)!=len(dispositions)or set(old)!=expected or set(audit)!=expected:raise ValueError('Exact unique original and audit population required')
    plan=[]
    for k in sorted(expected,key=lambda k:(k[0],k[1],ARM_ORDER.index(k[2]))):
        row=old[k];status=row['result']['status'];a=audit[k]
        if status!=a['original_status']:raise ValueError('Audit and original status differ')
        if status=='UNKNOWN_SOURCE_STATE':
            if a.get('cycle_id')!=row['result']['trace'][-1]['cycle_id']:raise ValueError('Audit terminal native cycle differs')
            proven=a['disposition']=='SOURCE_TRANSITION_NOW_PROVEN_NOT_A_COMPLETED_PATH'
            if proven and (not a['changed_source_certified']or not a['source_transition_proofs']or a['changed_source_barriers']):raise ValueError('New source proof required before redispatch')
            if not proven and a['disposition']!='SOURCE_EVIDENCE_STILL_REQUIRED':raise ValueError('Unknown source disposition')
            disposition=REPAIRED if proven else SKIP_SOURCE
        elif status=='NOT_RUN_AFTER_CAP_OR_FAILURE':disposition=UNFINISHED
        elif status=='UNKNOWN_CENSORED_SUCCESSOR':disposition=SKIP_CENSOR
        elif status=='COMPLETE_REGULATION':disposition=SKIP_COMPLETE
        else:raise ValueError('Undeclared original result class')
        plan.append(dict(game_id=k[0],path=k[1],arm=k[2],disposition=disposition,original_status=status,original_record_sha256=digest(row),record_id=RUN_ID+'|'+k[0]+'|'+str(k[1])+'|'+k[2]))
    return plan

def uniforms(game_id,path):
    seed=hashlib.sha256(f'progression_smoke_v1|17|{game_id}|{path}'.encode()).digest()
    values=np.random.default_rng(int.from_bytes(seed[:8],'big')).random(401)
    return values.tolist(),hashlib.sha256(np.asarray(values,dtype='<f8').tobytes()).hexdigest()

def prefix_check(original,result):
    before=original['result']['trace'];after=result.get('trace',[])
    for a,b in zip(before,after):
        if any(a[f]!=b[f]for f in ('cycle_id','tier','pool_size','pre_remaining')):raise ValueError('Original selected-source prefix changed')
    if len(after)<len(before):
        if result['status']not in ('INCOMPLETE_TIME_CAP','INCOMPLETE_EVENT_CAP','INCOMPLETE_UNIFORM_STREAM'):raise ValueError('Changed path stopped before original source failure')
        return 'INCOMPLETE_BEFORE_ORIGINAL_STOP'
    if after[len(before)-1]['status']!='TRANSFERRED':raise ValueError('Audited source stop did not transfer')
    return 'ORIGINAL_PREFIX_MATCHED_AND_REPAIRED_STOP_TRANSFERRED'

def assemble(plan,finished,started):
    """No skipped or unfinished result is a zero or a completed forecast."""
    keys={key(r)for r in plan};done={key(r):r for r in finished};started=set(started)
    if len(done)!=len(finished)or not set(done)<=keys or not started<=keys:raise ValueError('Unique planned result/start keys required')
    rows=[]
    for item in plan:
        k=key(item);row=dict(item,run_id=RUN_ID,attempted=k in started)
        if item['disposition']not in DISPATCH:
            if k in done or k in started:raise ValueError('An unchanged/skipped path was dispatched')
            row.update(execution_status='SKIPPED_BY_FROZEN_PLAN',result=None)
        elif k in done:
            if k not in started:raise ValueError('Result lacks durable dispatch start')
            row.update(done[k],execution_status='NEW_RESULT')
        else:row.update(execution_status='NOT_FINISHED_CAP_OR_FAILURE',result=None)
        rows.append(row)
    return rows

def read_journal(path):
    """Keep a partial final write explicit; never infer completion from a start."""
    lines=path.read_text().splitlines(keepends=True);rows=[];partial=False
    for i,line in enumerate(lines):
        try:rows.append(json.loads(line))
        except json.JSONDecodeError:
            if i!=len(lines)-1 or line.endswith('\n'):raise ValueError('Malformed durable journal record')
            partial=True
    return rows,partial

def summarize(rows,paths_per_group=32):
    done=[r for r in rows if r['execution_status']=='NEW_RESULT']
    complete=[r for r in done if r['result']['status']=='COMPLETE_REGULATION']
    channels={f:sum(all(s[f]is not None for s in r['result']['team_stats'])for r in complete)for f in STATS}
    groups={(r['game_id'],r['arm'])for r in rows};group_reports=[]
    for gid,arm in sorted(groups):
        members=[r for r in rows if (r['game_id'],r['arm'])==(gid,arm)]
        completed=[r for r in members if r['execution_status']=='NEW_RESULT'and r['result']['status']=='COMPLETE_REGULATION']
        forecasts={f:len(members)==len(completed)==paths_per_group and all(all(s[f]is not None for s in r['result']['team_stats'])for r in completed)for f in STATS}
        group_reports.append(dict(game_id=gid,arm=arm,new_complete_states=len(completed),complete_channel_forecasts=forecasts,
            supported_joint_forecast=len(members)==len(completed)==paths_per_group and all(r['result']['full_law_known']for r in completed)))
    return dict(original_scope_rows=len(rows),selected_dispatch=sum(r['disposition']in DISPATCH for r in rows),
        disposition_counts=dict(Counter(r['disposition']for r in rows)),execution_counts=dict(Counter(r['execution_status']for r in rows)),
        newly_finished_paths=len(done),started_unfinished=sum(r['attempted']and r['execution_status']=='NOT_FINISHED_CAP_OR_FAILURE'for r in rows),
        undispatched_selected=sum(not r['attempted']and r['execution_status']=='NOT_FINISHED_CAP_OR_FAILURE'for r in rows),
        new_status_counts=dict(Counter(r['result']['status']for r in done)),new_complete_states=len(complete),complete_channel_paths=channels,
        prefix_check_counts=dict(Counter(r.get('prefix_check','UNAVAILABLE')for r in done)),
        complete_supported_joint_law_paths=sum(r['result']['full_law_known']for r in complete),groups=group_reports,
        complete_channel_forecast_groups={f:sum(g['complete_channel_forecasts'][f]for g in group_reports)for f in STATS},
        accuracy_assessed=False,accuracy_n=0,mixed_old_new_forecast=False,activation=False)
