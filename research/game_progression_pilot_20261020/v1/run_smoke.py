"""Root-dispatched mechanics smoke only. No execution on import."""
from pathlib import Path
from datetime import datetime, UTC
from collections import Counter
import argparse, json, os, signal, time
from research.game_progression_pilot_20261020.v1.prepare_integrated import OUT, ref, load
from backend.app.product_services.game_progression_runtime import mechanics_smoke

def planned_keys(games):
    if len(games) != 5 or len({g['game_id'] for g in games}) != 5:
        raise ValueError('Exactly five frozen games required')
    return [(g['game_id'], p, a) for g in sorted(games,key=lambda x:x['game_id']) for p in range(32) for a in ('contextual','control')]

def complete_capped_rows(rows, keys):
    """Unfinished paths have unknown output, never zero production or success."""
    seen = {(r['game_id'],r['path'],r['arm']) for r in rows}
    if len(seen) != len(rows) or not seen.issubset(set(keys)):
        raise ValueError('Duplicate/unplanned published path')
    return [dict(game_id=g,path=p,arm=a,seed=17,result=dict(status='NOT_FINISHED_HARD_JOB_CAP',full_law_known=False)) for g,p,a in keys if (g,p,a) not in seen]

def run(output):
    output = Path(output)
    if output.exists(): raise ValueError('Do not overwrite/retry a smoke attempt')
    output.mkdir(parents=True)
    started = time.monotonic(); start_at = datetime.now(UTC).isoformat(); rows=[]; keys=[]; status='FAILED_BEFORE_INPUT_VALIDATION'; error=None
    def cap(*_): raise TimeoutError('120 second WHOLE JOB cap including managed input reads')
    old = signal.signal(signal.SIGALRM,cap); signal.setitimer(signal.ITIMER_REAL,120)
    manifest_ref=ref(OUT/'INTEGRATED_MANIFEST.json')
    with (output/'paths.jsonl').open('x') as sink:
        def publish(row):
            key=(row['game_id'],row['path'],row['arm'])
            if key not in keys or any((r['game_id'],r['path'],r['arm']) == key for r in rows): raise ValueError('Unplanned/duplicate path')
            sink.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n');sink.flush();os.fsync(sink.fileno());rows.append(row)
        try:
            manifest=load(manifest_ref)
            # Generation inputs contain TRAIN library + target pregame context only.
            selection=load(manifest['selection_ref'])
            keys=planned_keys(selection['selected'])
            policy=load(manifest['policy_ref']);openings=load(manifest['openings_ref']);games=load(manifest['games_ref'])
            if {g['game_id'] for g in games} != {g['game_id'] for g in selection['selected']} or manifest['scope']['planned_paths']!=320: raise ValueError('Frozen scope differs')
            result=mechanics_smoke(policy,openings,games,publish_path=publish)
            status=result['status']
        except TimeoutError as exc:
            status='INCOMPLETE_HARD_JOB_CAP';error=str(exc)
        except Exception as exc:
            status='FAILED_NO_AUTOMATIC_RETRY';error=type(exc).__name__+': '+str(exc)
        finally:
            signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
        if status=='INCOMPLETE_HARD_JOB_CAP':
            for row in complete_capped_rows(rows,keys): publish(row)
    summary=dict(version='integrated_mechanics_smoke_runner_v1',status=status,error=error,started_at=start_at,completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-started,hard_whole_job_seconds=120,
        manifest_ref=manifest_ref,runner_ref=ref(__file__),paths_ref=ref(output/'paths.jsonl'),planned_paths=320,published_paths=len(rows),status_counts=dict(Counter(r['result']['status'] for r in rows)),complete_sampled_paths=sum(r['result']['status']=='COMPLETE_REGULATION' for r in rows),complete_full_law_paths=sum(r['result']['status']=='COMPLETE_REGULATION' and r['result']['full_law_known'] for r in rows),
        quality_assessed=False,tail_precision_assessed=False,accuracy_assessed=False,unknown_mass='RETAINED_NO_SUCCESS_FILTERING',larger_run_automatic=False,simulator_calls=1 if keys else 0,fits=0,activation=False)
    (output/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();run(a.output)
