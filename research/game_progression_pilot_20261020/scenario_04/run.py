"""One new targeted <=30s mechanics dispatch, never an old-run continuation."""
from datetime import datetime,UTC
from pathlib import Path
import json,os,signal,time
from backend.app.product_services.event_boundary_progression import rollout,index_library
from research.game_progression_pilot_20261020.v1.prepare_integrated import load,ref
from research.game_progression_pilot_20261020.scenario_04.common import key,uniforms,prefix_check,assemble,summarize,read_journal,DISPATCH,REPAIRED,RUN_ID

D=Path(__file__).resolve().parent

def execute(manifest_path,destination):
    if destination.exists():raise ValueError('No run retry or overwrite')
    destination.mkdir();start=time.monotonic();stamp=datetime.now(UTC).isoformat()
    finished=[];started=[];error=None;status='RUNNING';plan=[];manifest_ref=ref(manifest_path)
    # Only the frozen local manifest is read before arming its declared cap.
    m=load(manifest_ref);plan=m['plan'];bound=m['bounds'];deadline=start+bound['whole_run_seconds']
    if m['run_id']!=RUN_ID or bound!=dict(preparation_seconds=30,whole_run_seconds=30,max_dispatched_paths=106,max_actions_per_path=400,uniforms_per_path=401):raise ValueError('Fixed bounded dispatch required')
    if sum(r['disposition']in DISPATCH for r in plan)>bound['max_dispatched_paths']:raise ValueError('Path dispatch cap exceeded')
    def cap(*_):raise TimeoutError('30-second whole changed-smoke cap')
    previous=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,max(.001,deadline-time.monotonic()))
    with (destination/'attempts.jsonl').open('x')as attempts,(destination/'results.jsonl').open('x')as results:
        def durable(sink,row):
            sink.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n');sink.flush();os.fsync(sink.fileno())
        try:
            for r in [*m['code_refs'],m['recipe_ref'],*m['preserved_refs']]:
                if ref(r['path'])!=r:raise ValueError('Frozen code/recipe/prior evidence differs')
            baseline_ref=m['baseline_paths_ref']
            if ref(baseline_ref['path'])!=baseline_ref:raise ValueError('Original paths binding differs')
            prior={key(r):r for r in [json.loads(line)for line in Path(baseline_ref['path']).read_text().splitlines()]}
            games={g['game_id']:g for g in load(m['games_ref'])}
            library=index_library(load(m['library_ref']));openings=load(m['openings_ref'])
            for item in plan:
                if item['disposition']not in DISPATCH:continue
                if time.monotonic()>=deadline:raise TimeoutError('Declared deadline reached before next dispatch')
                k=key(item);values,stream_hash=uniforms(item['game_id'],item['path'])
                if item['disposition']==REPAIRED and stream_hash!=prior[k]['uniform_stream_sha256']:raise ValueError('Original uniform stream differs')
                durable(attempts,dict(record_id=item['record_id'],game_id=k[0],path=k[1],arm=k[2],started_at=datetime.now(UTC).isoformat()))
                started.append(k)
                result=rollout(library,openings,games[k[0]]['context_by_side'],values,k[2],deadline,time.monotonic)
                checked=prefix_check(prior[k],result)if item['disposition']==REPAIRED else'NO_DURABLE_PRIOR_RESULT_PREFIX_TO_COMPARE'
                row=dict(game_id=k[0],path=k[1],arm=k[2],seed=17,uniform_stream_sha256=stream_hash,prefix_check=checked,result=result,
                    production_scope='FULL_PATH_ONLY_IF_COMPLETE_REGULATION;OTHERWISE_PARTIAL;NO_MIXED_VERSION_FORECAST')
                durable(results,row);finished.append(row)
            status='TARGETED_CHANGED_MECHANICS_DISPATCH_FINISHED'
        except TimeoutError as exc:status='INCOMPLETE_TIME_CAP';error=str(exc)
        except Exception as exc:status='FAILED_NO_AUTOMATIC_RETRY';error=type(exc).__name__+': '+str(exc)
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
    compute_seconds=time.monotonic()-start
    # A signal may arrive after a write but before an in-memory append. The
    # persisted journals, including any partial final write, own completion.
    finished,partial_result=read_journal(destination/'results.jsonl')
    start_records,partial_start=read_journal(destination/'attempts.jsonl')
    started=[key(r)for r in start_records];rows=assemble(plan,finished,started)
    with (destination/'paths.jsonl').open('x')as sink:
        for row in rows:sink.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')
    preserved=m['preserved_refs'];preservation_ok=all(ref(r['path'])==r for r in preserved)
    summary=dict(summarize(rows),version='scenario04_targeted_changed_mechanics_v1',run_id=RUN_ID,status=status,error=error,started_at=stamp,completed_at=datetime.now(UTC).isoformat(),
        compute_elapsed_seconds=compute_seconds,whole_job_elapsed_seconds=time.monotonic()-start,compute_cap_seconds=bound['whole_run_seconds'],
        post_compute_publication_seconds=time.monotonic()-start-compute_seconds,manifest_ref=manifest_ref,paths_ref=ref(destination/'paths.jsonl'),
        partial_result_journal_tail=partial_result,partial_start_journal_tail=partial_start,
        attempts_ref=ref(destination/'attempts.jsonl'),results_ref=ref(destination/'results.jsonl'),preserved_evidence_unchanged=preservation_ok,
        original_finished_records_preserved=sum(r['original_status']!='NOT_RUN_AFTER_CAP_OR_FAILURE'for r in plan),
        original_cap_failure_placeholders_preserved=sum(r['original_status']=='NOT_RUN_AFTER_CAP_OR_FAILURE'for r in plan),original_run_extended=False,
        source_threats_retained=library['threats']if 'library'in locals()else None,
        unknown_opening_count=sum(not o['certified']for o in openings)if 'openings'in locals()else None,
        fits=0,actual_labels_loaded=False,source_requests=0,activation=False)
    summary['whole_job_elapsed_seconds']=time.monotonic()-start
    summary['post_compute_publication_seconds']=summary['whole_job_elapsed_seconds']-compute_seconds
    with (destination/'SUMMARY.json').open('x')as sink:sink.write(json.dumps(summary,indent=2)+'\n')
    return summary

if __name__=='__main__':
    summary=execute(D/'MANIFEST.json',D/'changed_smoke_1')
    print(json.dumps({k:summary[k]for k in ('status','compute_elapsed_seconds','whole_job_elapsed_seconds','newly_finished_paths','new_status_counts','new_complete_states','complete_supported_joint_law_paths','execution_counts','preserved_evidence_unchanged')}))
