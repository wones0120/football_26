"""Inspect nested decoded tables after preserving both failed export assumptions."""
from pathlib import Path
from datetime import datetime,UTC
import json,signal,sys,time,warnings
from research.game_progression_pilot_20261020.v1.prepare_integrated import ref,load
from research.game_progression_pilot_20261020.raw_source_feasibility.bounds import expand,verify
from research.game_progression_pilot_20261020.raw_source_feasibility.containers import plain

D=Path(__file__).resolve().parent

def main():
    start=time.monotonic()
    with (D/'CACHED_INSPECTION_STARTED.json').open('x')as s:json.dump(dict(started_at=datetime.now(UTC).isoformat(),cap_seconds=30,
        reason='Fix export handling for nested DataFrame containers, not assumed root DataFrame; prior RDS parses succeeded. No download, cap increase, or model retry.'),s)
    def cap(*_):raise TimeoutError('30-second cached inspection cap; no retry')
    old=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,30)
    try:
        setup=load(ref(D/'READER.json'));sys.path.insert(0,setup['target']);import rdata
        a=load(ref(D/'ACQUISITION.json'));raw=Path(a['source_ref']['path']).read_bytes();verify(raw,a['expected_sha256'])
        data=expand(raw,a['decoded_cap_bytes'])
        with warnings.catch_warnings(record=True)as captured:
            root=rdata.conversion.convert(rdata.parser.parse_data(data))
        value=plain(root);encoded=json.dumps(value,ensure_ascii=False,allow_nan=False).encode()
        if len(encoded)>a['decoded_cap_bytes']:raise ValueError('Decoded JSON byte cap exceeded')
        with (D/'CACHED_DECODED.json').open('xb')as s:s.write(encoded)
        tables=[]
        def walk(v,path):
            if isinstance(v,dict):
                if v.get('__r_container__')=='DataFrame':tables.append(dict(path=path,rows=len(v['data']),columns=v['columns']))
                for key,item in v.items():walk(item,path+'.'+key)
            elif isinstance(v,list):
                for i,item in enumerate(v):walk(item,path+f'[{i}]')
        walk(value,'$')
        report=dict(status='DECODED_NESTED_TABLES_INSPECTED',elapsed_seconds=time.monotonic()-start,
            root_type=type(root).__name__,root_keys=list(root)if isinstance(root,dict)else None,
            tables=tables,serialization_bytes=len(data),decoded_ref=ref(D/'CACHED_DECODED.json'),source_ref=a['source_ref'],
            reader_ref=ref(D/'READER.json'),rdata_version=rdata.__version__,warnings=[str(w.message)for w in captured],
            runner_ref=ref(__file__),container_ref=ref(D/'containers.py'),prior_export_failure_ref=ref(D/'DECODE.json'),
            prior_root_assumption_failure_ref=ref(D/'FRAME_INSPECTION_STARTED.json'),new_downloads=0)
        with (D/'CACHED_INSPECTION.json').open('x')as s:json.dump(report,s,indent=2);s.write('\n')
        print(json.dumps(report))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)

if __name__=='__main__':main()
