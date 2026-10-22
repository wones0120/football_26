"""One exclusive, capped cached ledger build; no model/runtime consumers."""
from collections import Counter
from datetime import datetime,UTC
from pathlib import Path
import gzip,json,signal,time
from research.game_progression_pilot_20261020.v1.prepare_integrated import load,ref,ROOT
from research.game_progression_pilot_20261020.observation_contract.contract import (
    VERSION,MISSING_OBSERVATIONS,record,identity_census,validate_record)

D=Path(__file__).resolve().parent

def main():
    start=time.monotonic();stamp=datetime.now(UTC).isoformat()
    with (D/'STARTED.json').open('x')as s:json.dump(dict(started_at=stamp,cap_seconds=30),s)
    def cap(*_):raise TimeoutError('30-second observation build cap; no retry')
    previous=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,30)
    try:
        m_ref=ref(D.parent/'scenario_04/MANIFEST.json');m=load(m_ref);v3=load(m['original_manifest_ref'])
        source_ref=v3['source_projection_refs'][0];projection=load(source_ref);library=load(m['library_ref'])
        by={c['cycle_id']:c for c in library['cycles']};assert len(by)==len(library['cycles'])
        inputs=[m_ref,m['original_manifest_ref'],source_ref,m['library_ref'],ref(D/'RECIPE.md'),ref(D/'contract.py'),ref(__file__)]
        preserved=m['preserved_refs']+[ref(D.parent/'scenario_04'/n)for n in ('VALIDATION.json','changed_smoke_1/paths.jsonl','changed_smoke_1/results.jsonl','changed_smoke_1/SUMMARY.json')]
        for folder,names in [('source_state_followup',('AUDIT.json','VALIDATION.json','RESULTS.md','DEFERRED.json')),
                             ('continuation_followup',('AUDIT.json','VALIDATION.json','RESULTS.md','NEXT_EXPERIMENT.md'))]:
            preserved.extend(ref(D.parent/folder/n)for n in names)
        columns=projection['columns'];assert len(columns)==len(set(columns))
        assert all(len(r)==len(columns)for r in projection['rows'])
        raws=[dict(zip(columns,r))for r in projection['rows']];census=identity_census(raws)
        counts={name:Counter()for name in ('row_kind','identity_status','clock_status','timeout_status','score_status','source_certification','wait_kind')}
        linked=set();count=0;matched_timeout_pairs=0
        destination=D/'LEDGER.jsonl.gz'
        with destination.open('xb')as file:
            with gzip.GzipFile(filename='',mode='wb',fileobj=file,compresslevel=1,mtime=0)as sink:
                for ordinal,raw in enumerate(raws):
                    row=record(raw,ordinal,source_ref['sha256'],census,by);validate_record(row,ordinal,source_ref['sha256'])
                    p=row['provenance'];f=row['followup'];counts['row_kind'][row['row_kind']]+=1
                    counts['identity_status'][p['identity_status']]+=1
                    for name,path in [('clock','clock'),('timeout','timeouts'),('score','score')]:counts[name+'_status'][row['pre_event'][path]['status']]+=1
                    if p['identity_status']=='UNIQUE_CYCLE_MATCH':
                        linked.add(p['native_cycle_id']);counts['source_certification'][str(f['source_state_certified'])]+=1
                        counts['wait_kind'][f['wait']['kind']]+=1
                        matched_timeout_pairs+=int(row['pre_event']['timeouts']['status']=='SOURCE_PRE_EVENT_VALIDATED')
                    sink.write((json.dumps(row,separators=(',',':'),allow_nan=False)+'\n').encode());count+=1
        assert count==len(raws)==49665 and len(linked)==len(by)==43852
        for r in inputs+preserved:assert ref(r['path'])['sha256']==r['sha256']
        ledger_ref=ref(destination)
        report=dict(version=VERSION,started_at=stamp,elapsed_seconds=time.monotonic()-start,cap_seconds=30,
            recipe_ref=ref(D/'RECIPE.md'),input_refs=inputs,preserved_refs=preserved,ledger_ref=ledger_ref,
            source_lineage=projection['source_lineage'],source_row_count=count,linked_cycles=len(linked),
            matched_cycle_validated_timeout_pairs=matched_timeout_pairs,counts={k:dict(v)for k,v in counts.items()},
            missing_observations=MISSING_OBSERVATIONS,all_source_rows_retained=True,all_cycles_accounted_for=True,
            ledger_validated_during_write=True,original_pregame_availability_proven=False,
            current_runtime_refs=[ref(ROOT/p)for p in ('backend/app/product_services/event_boundary_progression.py','backend/app/product_services/game_progression_runtime.py','backend/app/product_services/game_state_reconstruction.py')],
            reconstruction_runs=0,simulation_runs=0,fits=0,continuation_supported=False,activation=False)
        with (D/'MANIFEST.json').open('x')as s:json.dump(report,s,indent=2);s.write('\n')
        print(json.dumps({k:report[k]for k in ('elapsed_seconds','source_row_count','linked_cycles','matched_cycle_validated_timeout_pairs','counts')}))
    except Exception as exc:
        with (D/'FAILURE.json').open('x')as s:json.dump(dict(error=type(exc).__name__+': '+str(exc),seconds=time.monotonic()-start,partial_ledger_may_exist=True,no_retry=True),s)
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)

if __name__=='__main__':main()
