"""One capped cached-TRAIN source audit. No simulation, fit or outcome scoring."""
from pathlib import Path
from collections import Counter
from datetime import datetime,UTC
import argparse,gc,json,signal,time
from backend.app.product_services.game_state_reconstruction import reconstruct_game_transitions,build_original_drive_blocks
from backend.app.product_services.event_boundary_progression import compile_cycles
from backend.app.product_services.game_progression_source_adapter import prior_contexts
from research.game_progression_pilot_20261020.v1.prepare_integrated import load,ref,ROOT

D=Path(__file__).resolve().parent

def main(*,output_name='AUDIT.json',change_reason='Initial frozen cached-source audit'):
    if Path(output_name).name!=output_name:raise ValueError('Local receipt basename required')
    destination=D/output_name
    if destination.exists():raise ValueError('No overwrite or unchanged rerun')
    start=time.monotonic();stamp=datetime.now(UTC).isoformat()
    def cap(*_):raise TimeoutError('60-second cached TRAIN audit cap; no automatic retry')
    previous=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,60)
    try:
        v3=D.parent/'v3';manifest_path=v3/'MANIFEST.json';m=json.loads(manifest_path.read_text())
        preserved=[ref(p)for p in (manifest_path,v3/'CHECKPOINT.json',v3/'RESULTS.json',v3/'smoke_attempt_3/SUMMARY.json',v3/'smoke_attempt_3/paths.jsonl')]
        original_paths=[json.loads(line)for line in (v3/'smoke_attempt_3/paths.jsonl').read_text().splitlines()]
        stopped_ids={r['result']['trace'][-1]['cycle_id']for r in original_paths if r['result']['status'].startswith('UNKNOWN')}
        recipe_ref=ref(D/'RECIPE.md')
        prior=load(m['prior_manifest_ref']);contexts=prior_contexts(load(prior['input_refs']['prior_contexts'])['team_contexts'])
        projection=load(m['source_projection_refs'][0]);columns=projection['columns']
        raw=[dict(zip(columns,values))for values in projection['rows']]
        t=time.monotonic();reconstruction=reconstruct_game_transitions(raw,source_lineage=projection['source_lineage'])
        reconstruction_seconds=time.monotonic()-t
        source_input_rows=len(raw);del raw,projection;gc.collect()
        evidence=[];failure_sources={}
        for g in reconstruction['games']:
            for r in g['rows']:
                cid=g['game_id']+':'+r['play_id']
                if cid in stopped_ids:
                    failure_sources[cid]=dict(source_ordinal=r['source_ordinal'],raw=r['raw'],prestate=r['state_before'],
                        successor=r['transition_endpoint'],remaining_barriers=r['state_transition_barriers'],proofs=r['source_transition_proofs'])
                if r['source_transition_proofs']:
                    evidence.append(dict(cycle_id=g['game_id']+':'+r['play_id'],source_ordinal=r['source_ordinal'],proofs=r['source_transition_proofs'],
                        event_barriers_retained=r['event']['barriers'],remaining_transition_barriers=r['transition_barriers'],
                        source_state_certified=r['state_transition_certified'],raw=r['raw']))
        blocks=build_original_drive_blocks(reconstruction)
        assert sum(b['source_row_count']for b in blocks['blocks'])+len(blocks['deterministic_admin_markers'])+len(blocks['explicit_overtime_rows'])+len(reconstruction['quarantine'])==source_input_rows
        changed=compile_cycles(reconstruction,blocks,contexts)
        del reconstruction,blocks;gc.collect()
        original=load(m['library_ref'])
        assert len(changed['cycles'])==len(original['cycles'])==43852
        assert changed['threats']==original['threats']
        assert changed['boundaries']==original['boundaries']
        assert changed['source_marker_exclusions']==original['source_marker_exclusions']
        assert changed['explicit_OT_exclusions']==original['explicit_OT_exclusions']
        allowed={'state_certified','barriers','source_transition_proofs'}
        newly_known=[];partially_repaired=[]
        for old,new in zip(original['cycles'],changed['cycles']):
            assert {k:v for k,v in old.items()if k not in allowed}=={k:v for k,v in new.items()if k not in allowed}
            assert not old['state_certified']or new['state_certified']
            assert set(new['barriers'])<=set(old['barriers'])
            if not old['state_certified']and new['state_certified']:newly_known.append(new['cycle_id'])
            if new['source_transition_proofs']and not new['state_certified']:partially_repaired.append(new['cycle_id'])
        old_by={c['cycle_id']:c for c in original['cycles']};new_by={c['cycle_id']:c for c in changed['cycles']}
        dispositions=[];unknown_barriers=Counter();remaining_barriers=Counter()
        for row in original_paths:
            result=row['result'];status=result['status'];trace=result.get('trace',[])
            item={k:row[k]for k in ('game_id','path','arm','seed')};item['original_status']=status
            if status=='UNKNOWN_SOURCE_STATE':
                cid=trace[-1]['cycle_id'];old=old_by[cid];new=new_by[cid]
                unknown_barriers.update(set(old['barriers']));remaining_barriers.update(set(new['barriers']))
                item.update(cycle_id=cid,original_source_barriers=old['barriers'],changed_source_barriers=new['barriers'],
                    source_transition_proofs=new['source_transition_proofs'],changed_source_certified=new['state_certified'],
                    disposition='SOURCE_TRANSITION_NOW_PROVEN_NOT_A_COMPLETED_PATH'if new['state_certified']else'SOURCE_EVIDENCE_STILL_REQUIRED')
            elif status=='UNKNOWN_CENSORED_SUCCESSOR':
                cid=trace[-1]['cycle_id'];c=old_by[cid];followup=c['wait']['seconds'];deadline=trace[-1]['pre_remaining']
                assert c['wait']['kind']=='RIGHT_CENSORED'and deadline>followup
                assert not new_by[cid]['source_transition_proofs']
                item.update(cycle_id=cid,source_followup_seconds=followup,generated_deadline_seconds=deadline,unobserved_followup_seconds=deadline-followup,
                    disposition='CONDITIONAL_WAIT_AND_SUCCESSOR_UNIDENTIFIED_REQUIRE_OBSERVATIONS',full_law_known=False)
            else:item['disposition']='ORIGINAL_RECORD_UNCHANGED_NO_RERUN'
            dispositions.append(item)
        assert preserved==[ref(r['path'])for r in preserved]and recipe_ref==ref(D/'RECIPE.md')
        report=dict(version='scenario_02_source_and_censor_audit_v1',started_at=stamp,completed_at=datetime.now(UTC).isoformat(),
            change_reason=change_reason,
            elapsed_seconds=time.monotonic()-start,whole_job_cap_seconds=60,reconstruction_seconds=reconstruction_seconds,
            manifest_ref=ref(manifest_path),source_projection_ref=m['source_projection_refs'][0],original_library_ref=m['library_ref'],recipe_ref=recipe_ref,
            source_input_rows=source_input_rows,train_cycles=len(changed['cycles']),prior_state_certified=sum(c['state_certified']for c in original['cycles']),
            changed_state_certified=sum(c['state_certified']for c in changed['cycles']),newly_source_certified_cycles=newly_known,
            partially_repaired_cycles=partially_repaired,proof_kind_counts=dict(Counter(p['kind']for e in evidence for p in e['proofs'])),
            kernel_inputs_and_production_unchanged=True,all_unknown_candidates_retained=True,all_source_rows_partitioned=True,
            source_evidence_ledger=evidence,original_status_counts=dict(Counter(r['original_status']for r in dispositions)),
            recorded_source_stop_disposition_counts=dict(Counter(r['disposition']for r in dispositions if r['original_status']=='UNKNOWN_SOURCE_STATE')),
            recorded_source_stop_original_barrier_path_counts=dict(unknown_barriers),recorded_source_stop_remaining_barrier_path_counts=dict(remaining_barriers),
            remaining_train_barrier_cycle_counts=dict(Counter(b for c in changed['cycles']if not c['state_certified']for b in set(c['barriers']))),
            path_dispositions=dispositions,preserved_evidence_refs=preserved,
            saved_terminal_source_evidence=failure_sources,
            censored_terminal_native_kind_path_counts=dict(Counter(failure_sources[r['cycle_id']]['raw'].get('play_type')for r in dispositions if r['original_status']=='UNKNOWN_CENSORED_SUCCESSOR')),
            implementation_refs=[ref(ROOT/p)for p in ('backend/app/product_services/game_state_reconstruction.py','backend/app/product_services/event_boundary_progression.py')],runner_ref=ref(__file__),
            simulations=0,fits=0,new_accuracy_metrics=False,new_complete_path_claim=False,activation=False,
            censored_continuation='NOT_IDENTIFIED;OBSERVATION_REQUIREMENTS_DOCUMENTED;NO_FITTED_MODEL',
            limitation='Static source certification audit only. Historical paths are neither rerun nor relabeled complete; natural censoring and unresolved source law remain.')
        with destination.open('x')as sink:sink.write(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:report[k]for k in ('elapsed_seconds','reconstruction_seconds','train_cycles','prior_state_certified','changed_state_certified','proof_kind_counts','recorded_source_stop_disposition_counts','remaining_train_barrier_cycle_counts')}))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-name',default='AUDIT.json')
    parser.add_argument('--change-reason',default='Initial frozen cached-source audit')
    args=parser.parse_args();main(output_name=args.output_name,change_reason=args.change_reason)
