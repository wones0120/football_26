"""Exclusive cached-parquet enrichment with source-key checks and a 30s cap."""
from collections import Counter
from pathlib import Path
from datetime import datetime,UTC
import gzip,json,signal,time
import pyarrow.parquet as pq
from research.game_progression_pilot_20261020.v1.prepare_integrated import ref,load
from research.game_progression_pilot_20261020.control_linkage.linkage import (
    VERSION,FIELDS,indexes,enrichment,native_key)

D=Path(__file__).resolve().parent

def main():
    start=time.monotonic()
    with (D/'STARTED.json').open('x')as s:json.dump(dict(started_at=datetime.now(UTC).isoformat(),cap_seconds=30),s)
    def cap(*_):raise TimeoutError('30-second control linkage cap; no retry')
    old=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,30)
    try:
        observation_ref=ref(D.parent/'observation_contract/MANIFEST.json');m=load(observation_ref)
        source=m['source_lineage']['original_source'];parquet_ref=ref(source['path'])
        assert parquet_ref['sha256']==source['sha256']and parquet_ref['bytes']==source['bytes']
        projection_ref=m['input_refs'][2];projection=load(projection_ref);library_ref=m['input_refs'][3];library=load(library_ref)
        inputs=[observation_ref,m['ledger_ref'],projection_ref,library_ref,parquet_ref,ref(D/'RECIPE.md'),ref(D/'SOURCE_SEMANTICS.json'),ref(D/'linkage.py'),ref(__file__)]
        preserved=m['preserved_refs']+[ref(D.parent/'observation_contract'/n)for n in ('VALIDATION.json','RESULTS.md','contract.py','build.py')]
        rows=pq.read_table(source['path'],columns=list(FIELDS)).to_pylist()
        assert len(rows)==len(projection['rows'])==49665
        columns=projection['columns'];identity_fields=('game_id','play_id','order_sequence','home_team','away_team')
        at={k:columns.index(k)for k in identity_fields}
        for raw,values in zip(rows,projection['rows']):assert all(raw[k]==values[at[k]]for k in identity_fields)
        census,unique,previous,order_ok=indexes(rows)
        markers={r['game_id']+':'+r['play_id']:r for r in library['source_marker_exclusions']}
        assert len(markers)==len(library['source_marker_exclusions'])
        for key,marker in markers.items():assert native_key(rows[marker['source_ordinal']])==key
        counts={k:Counter()for k in ('timeout_status','debit_status','clock_link_status','end_clock_format','native_marker_kind')}
        attached=dedicated=valid_debit=control_timeout_links=0;count=0
        path=D/'ENRICHMENT.jsonl.gz'
        with path.open('xb')as file:
            with gzip.GzipFile(filename='',mode='wb',fileobj=file,compresslevel=1,mtime=0)as sink:
                for ordinal,raw in enumerate(rows):
                    r=enrichment(raw,ordinal,projection_ref['sha256'],census,unique,previous,order_ok,markers)
                    timeout=r['timeout_use'];control=r['clock_control_link']
                    counts['timeout_status'][timeout['status']]+=1
                    if timeout['reported_flag']is True:counts['debit_status'][timeout['debit_status']]+=1
                    counts['clock_link_status'][control['status']]+=1;counts['end_clock_format'][r['end_clock_time_format']]+=1
                    if control['status']=='FROZEN_CERTIFIED_ADMIN_LINK':counts['native_marker_kind'][control['kind']]+=1
                    if timeout['status']=='REPORTED_TEAM_TIMEOUT':
                        dedicated+=int(timeout['attachment']=='DEDICATED_TIMEOUT_EVENT');attached+=int(timeout['attachment']=='ATTACHED_TO_NATIVE_PLAY')
                        valid_debit+=int(timeout['debit_status']=='CORROBORATED_SOURCE_BUDGET_DEBIT')
                    control_timeout_links+=int(control['timeout_stop_event_observed'])
                    assert r['play_end_game_clock']is None and not r['generated_policy_supported']and not r['continuation_supported']
                    sink.write((json.dumps(r,separators=(',',':'),allow_nan=False)+'\n').encode());count+=1
        assert count==len(rows)
        for r in inputs+preserved+m['current_runtime_refs']:assert ref(r['path'])['sha256']==r['sha256']
        report=dict(version=VERSION,elapsed_seconds=time.monotonic()-start,cap_seconds=30,input_refs=inputs,preserved_refs=preserved,
            enrichment_ref=ref(path),source_lineage=m['source_lineage'],rows=count,unique_native_keys=len(unique),
            native_game_order_counts=dict(Counter(order_ok.values())),counts={k:dict(v)for k,v in counts.items()},
            reported_timeout_dedicated=dedicated,reported_timeout_attached=attached,corroborated_timeout_debits=valid_debit,
            frozen_timeout_clock_links=control_timeout_links,
            old_budget_timing_label_amended_separately=True,old_observation_ledger_unchanged=True,
            current_runtime_refs=m['current_runtime_refs'],missing_observations=['play_end_remaining_game_clock','full_terminal_state_and_enforcement',
                'restart_runoff_correction_adjudication','generated_timeout_and_action_policy'],
            source_rows_retained=True,simulation_runs=0,reconstruction_runs=0,fits=0,activation=False)
        with (D/'MANIFEST.json').open('x')as s:json.dump(report,s,indent=2);s.write('\n')
        print(json.dumps({k:report[k]for k in ('elapsed_seconds','rows','native_game_order_counts','reported_timeout_dedicated','reported_timeout_attached','corroborated_timeout_debits','frozen_timeout_clock_links','counts')}))
    except Exception as exc:
        with (D/'FAILURE.json').open('x')as s:json.dump(dict(error=type(exc).__name__+': '+str(exc),seconds=time.monotonic()-start,partial_file_possible=True,no_retry=True),s)
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)

if __name__=='__main__':main()
