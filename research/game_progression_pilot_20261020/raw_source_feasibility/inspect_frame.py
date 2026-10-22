"""Changed cached inspection: handle the decoded dataframe, not a download retry."""
from pathlib import Path
from datetime import datetime,UTC
import json,signal,sys,time,warnings
from research.game_progression_pilot_20261020.v1.prepare_integrated import ref,load
from research.game_progression_pilot_20261020.raw_source_feasibility.bounds import expand,verify

D=Path(__file__).resolve().parent

def main():
    start=time.monotonic()
    with (D/'FRAME_INSPECTION_STARTED.json').open('x')as s:json.dump(dict(started_at=datetime.now(UTC).isoformat(),cap_seconds=30,reason='RDS parsed as DataFrame; prior stage failed only when generic JSON exporter rejected DataFrame. New inspection supports its actual container, no source refetch.'),s)
    def cap(*_):raise TimeoutError('30-second dataframe inspection cap; no retry')
    old=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,30)
    try:
        setup=load(ref(D/'READER.json'));sys.path.insert(0,setup['target']);import rdata,pandas as pd
        a=load(ref(D/'ACQUISITION.json'));raw=Path(a['source_ref']['path']).read_bytes();verify(raw,a['expected_sha256'])
        data=expand(raw,a['decoded_cap_bytes'])
        with warnings.catch_warnings(record=True)as captured:
            frame=rdata.conversion.convert(rdata.parser.parse_data(data))
        if not isinstance(frame,pd.DataFrame):raise ValueError('Observed DataFrame root required')
        encoded=frame.to_json(orient='split',date_format='iso',force_ascii=False).encode()
        if len(encoded)>a['decoded_cap_bytes']:raise ValueError('Decoded JSON byte cap exceeded')
        with (D/'FRAME.json').open('xb')as s:s.write(encoded)
        columns=[dict(name=str(c),dtype=str(frame[c].dtype),nonnull=int(frame[c].notna().sum()))for c in frame.columns]
        receipt=dict(status='CACHED_FRAME_INSPECTED',elapsed_seconds=time.monotonic()-start,
            source_ref=a['source_ref'],prior_export_failure_ref=ref(D/'DECODE.json'),
            reader_ref=ref(D/'READER.json'),reader_version=rdata.__version__,runner_ref=ref(__file__),
            serialization_bytes=len(data),frame_ref=ref(D/'FRAME.json'),rows=len(frame),columns=columns,
            warnings=[str(w.message)for w in captured],null_serialization='DataFrame missing values encoded as JSON null; original RDS retained',new_downloads=0)
        with (D/'FRAME_INSPECTION.json').open('x')as s:json.dump(receipt,s,indent=2);s.write('\n')
        print(json.dumps(receipt))
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)

if __name__=='__main__':main()
