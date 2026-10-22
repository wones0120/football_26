"""One fixed mechanics run; no successful-subset forecast or automatic retry."""
from pathlib import Path
from datetime import datetime,UTC
from collections import Counter
import json,hashlib,time,signal,os
import numpy as np
from research.game_progression_pilot_20261020.v1.prepare_integrated import load,ref
from backend.app.product_services.event_boundary_progression import rollout,index_library

D=Path(__file__).resolve().parent

def main():
    dest=D/'smoke_attempt_3'
    if dest.exists():raise ValueError('No retry/overwrite')
    dest.mkdir();start=time.monotonic();started_at=datetime.now(UTC).isoformat();rows=[];planned=[];error=None;status='RUNNING'
    def cap(*_):raise TimeoutError('Wholejob120second cap')
    old=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,120)
    with (dest/'paths.jsonl').open('x')as sink:
        def publish(row):
            row['production_scope']='FULL_GENERATED_PATH_ONLY_IF_COMPLETE_REGULATION;OTHERWISE_PARTIAL'
            sink.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n');sink.flush();os.fsync(sink.fileno());rows.append(row)
        try:
            mref=ref(D/'MANIFEST.json');m=load(mref)
            for r in m['runtime_refs']:
                if ref(r['path'])!=r:raise ValueError('Frozen implementation changed')
            games=load(m['games_ref']);planned=[(g['game_id'],p,a)for g in sorted(games,key=lambda g:g['game_id'])for p in range(32)for a in('contextual','control')]
            assert len(games)==5 and len(planned)==320
            library=index_library(load(m['library_ref']));openings=load(m['openings_ref']);deadline=start+120
            for game in sorted(games,key=lambda g:g['game_id']):
                for p in range(32):
                    seed=hashlib.sha256(f"progression_smoke_v1|17|{game['game_id']}|{p}".encode()).digest()
                    uniforms=np.random.default_rng(int.from_bytes(seed[:8],'big')).random(401).tolist()
                    stream_hash=hashlib.sha256(np.asarray(uniforms,dtype='<f8').tobytes()).hexdigest()
                    for arm in('contextual','control'):
                        result=rollout(library,openings,game['context_by_side'],uniforms,arm,deadline,time.monotonic)
                        publish(dict(game_id=game['game_id'],path=p,arm=arm,seed=17,uniform_stream_sha256=stream_hash,result=result))
            status='MECHANICS_EXECUTED_CHANGED_EVENT_ARCHITECTURE'
        except TimeoutError as exc:status='INCOMPLETE_TIME_CAP';error=str(exc)
        except Exception as exc:status='FAILED_NO_AUTOMATIC_RETRY';error=type(exc).__name__+': '+str(exc)
        finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
        seen={(r['game_id'],r['path'],r['arm'])for r in rows}
        for gid,p,arm in planned:
            if (gid,p,arm)not in seen:publish(dict(game_id=gid,path=p,arm=arm,seed=17,result=dict(status='NOT_RUN_AFTER_CAP_OR_FAILURE',full_law_known=False)))
    summary=dict(version='event_boundary_renewal_smoke_v3',status=status,error=error,started_at=started_at,completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,wholejob_cap_seconds=120,manifest_ref=ref(D/'MANIFEST.json'),runner_ref=ref(__file__),recipe_ref=ref(D/'RECIPE.md'),paths_ref=ref(dest/'paths.jsonl'),planned_paths=320,published_paths=len(rows),status_counts=dict(Counter(r['result']['status']for r in rows)),complete_state_paths=sum(r['result']['status']=='COMPLETE_REGULATION'for r in rows),complete_full_law_paths=sum(r['result']['full_law_known']for r in rows),all_paths_retained=True,changed_architecture_not_controlled_accuracy_experiment=True,larger_run=False,accuracy_assessed=False,fits=0,activation=False)
    (dest/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))

if __name__=='__main__':main()
