"""One cached amendment build, no source downloads or base-ledger mutation."""
from pathlib import Path
from collections import Counter
from datetime import datetime,UTC
import gzip,json,signal,time
from research.game_progression_pilot_20261020.v1.prepare_integrated import load,ref
from research.game_progression_pilot_20261020.raw_source_feasibility.linkage import table_records
from research.game_progression_pilot_20261020.clock_stop_amendment.amendment import build_records,VERSION

D=Path(__file__).resolve().parent

def main():
    start=time.monotonic();stamp=datetime.now(UTC).isoformat()
    with (D/'STARTED.json').open('x')as s:json.dump(dict(started_at=stamp,cap_seconds=30),s)
    def cap(*_):raise TimeoutError('30-second amendment cap; no retry')
    old=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,30)
    try:
        raw_dir=D.parent/'raw_source_feasibility'
        assessment_ref=ref(raw_dir/'CONTROL_ASSESSMENT.json');assessment=load(assessment_ref)
        inventory_ref=ref(raw_dir/'INVENTORY.json');inventory=load(inventory_ref)
        inspection=load(ref(raw_dir/'CACHED_INSPECTION.json'));root=load(assessment['decoded_ref'])
        game=root['data']['viewer']['gameDetail'];gid=inventory['game_id']
        assert inventory['game_uuid_matches_processed']and game['id']==[inventory['native_game_uuid']]
        raw_rows=table_records(game['plays'])
        base_manifest_ref=ref(D.parent/'observation_contract/MANIFEST.json');base_manifest=load(base_manifest_ref)
        base_ref=base_manifest['ledger_ref'];count=0;base_rows=[]
        # Verify the saved ledger bytes before using its source-native anchors.
        assert ref(base_ref['path'])==base_ref
        with gzip.open(base_ref['path'],'rt')as source:
            for line in source:
                row=json.loads(line);count+=1;key=row['provenance']['native_cycle_id']
                if isinstance(key,str)and key.startswith(gid+':'):base_rows.append(row)
        assert count==base_manifest['source_row_count']==49665 and len(base_rows)==183
        bindings=dict(game_id=gid,native_game_uuid=inventory['native_game_uuid'],
            raw_source_sha256=inspection['source_ref']['sha256'],decoded_sha256=assessment['decoded_ref']['sha256'],
            base_ledger_sha256=base_ref['sha256'],base_projection_sha256=base_manifest['input_refs'][2]['sha256'],assessment_sha256=assessment_ref['sha256'])
        inputs=[assessment_ref,inventory_ref,assessment['decoded_ref'],inspection['source_ref'],
            base_manifest_ref,base_ref,ref(raw_dir/'CACHED_INSPECTION.json'),ref(D/'RECIPE.md'),ref(D/'amendment.py'),ref(__file__)]
        preserved=inventory['preserved_refs']+inventory['source_refs']+[ref(raw_dir/n)for n in ('RESULTS.md','VALIDATION.json')]
        records=build_records(assessment['cases'],raw_rows,base_rows,bindings)
        assert len(records)==assessment['additional_control_records']==15
        assert {int(r['provenance']['play_id'])for r in records}==set(inventory['comparison']['raw_only_ids'])
        assert len({r['record_id']for r in records})==15
        output=D/'AMENDMENT.jsonl'
        with output.open('x')as s:
            for row in records:s.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')
        for r in inputs+preserved+inventory['current_runtime_refs']:assert ref(r['path'])['sha256']==r['sha256']
        report=dict(version=VERSION,started_at=stamp,elapsed_seconds=time.monotonic()-start,cap_seconds=30,
            amendment_ref=ref(output),base_ledger_ref=base_ref,base_ledger_rows=count,source_refs=inputs,preserved_refs=preserved,
            record_count=len(records),game_id=gid,cause_counts=dict(Counter(r['clock_stop']['reason']for r in records)),
            source_scope='ONE_NATIVE_GAME_ONLY;ADDITIONAL_SOURCE_OBSERVATIONS_NOT_NEW_TRAIN_CYCLES',
            omitted_unqualified_assessment_records=sum(r['status']!='SOURCE_TYPED_CLOCK_STOP_OBSERVATION'for r in assessment['cases']),
            base_rows_modified=0,base_native_collisions=0,source_downloads=0,rds_decodes=0,reconstruction_runs=0,simulation_runs=0,fits=0,
            runtime_consumer_added=False,generated_continuation_supported=False,current_runtime_refs=inventory['current_runtime_refs'],activation=False)
        with (D/'MANIFEST.json').open('x')as s:json.dump(report,s,indent=2);s.write('\n')
        print(json.dumps({k:report[k]for k in ('elapsed_seconds','record_count','cause_counts','base_rows_modified','omitted_unqualified_assessment_records')}))
    except Exception as exc:
        with (D/'FAILURE.json').open('x')as s:json.dump(dict(error=type(exc).__name__+': '+str(exc),seconds=time.monotonic()-start,no_retry=True),s)
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)

if __name__=='__main__':main()
