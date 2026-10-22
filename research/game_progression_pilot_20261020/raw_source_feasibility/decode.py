"""Bounded cached RDS parse using a temporary data reader, never R execution."""
from pathlib import Path
from datetime import datetime,UTC
import json,signal,sys,time
from research.game_progression_pilot_20261020.v1.prepare_integrated import ref,load
from research.game_progression_pilot_20261020.raw_source_feasibility.bounds import expand,verify

D=Path(__file__).resolve().parent

def normalize(value):
    if hasattr(value,'tolist'):return value.tolist()
    if isinstance(value,bytes):return value.decode('utf8')
    raise TypeError('Unsupported decoded container '+type(value).__name__)

def main():
    start=time.monotonic()
    with (D/'DECODE_STARTED.json').open('x')as s:json.dump(dict(started_at=datetime.now(UTC).isoformat(),cap_seconds=30),s)
    def cap(*_):raise TimeoutError('30-second cached decode cap; no retry')
    old=signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,30)
    receipt={}
    try:
        setup=load(ref(D/'READER.json'));assert setup['returncode']==0
        sys.path.insert(0,setup['target']);import rdata
        acquired=load(ref(D/'ACQUISITION.json'));assert acquired['status']=='ACQUIRED_HASH_MATCHED'
        raw=Path(acquired['source_ref']['path']).read_bytes();verify(raw,acquired['expected_sha256'])
        serialized=expand(raw,acquired['decoded_cap_bytes'])
        parsed=rdata.parser.parse_data(serialized);value=rdata.conversion.convert(parsed)
        encoded=json.dumps(value,default=normalize,ensure_ascii=False,allow_nan=False).encode()
        if len(encoded)>acquired['decoded_cap_bytes']:raise ValueError('Decoded JSON byte cap exceeded')
        with (D/'DECODED.json').open('xb')as s:s.write(encoded)
        receipt.update(status='DECODED_AS_DATA',rdata_version=rdata.__version__,root_type=type(value).__name__,
            root_length=len(value)if hasattr(value,'__len__')else None,
            root_keys=list(value.keys())if isinstance(value,dict)else None,serialization_bytes=len(serialized),
            decoded_ref=ref(D/'DECODED.json'),source_ref=acquired['source_ref'],reader_ref=ref(D/'READER.json'),runner_ref=ref(__file__))
    except Exception as exc:
        receipt.update(status='FAILED_NO_RETRY',error=type(exc).__name__+': '+str(exc));raise
    finally:
        receipt['elapsed_seconds']=time.monotonic()-start
        with (D/'DECODE.json').open('x')as s:json.dump(receipt,s,indent=2);s.write('\n')
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
        print(json.dumps(receipt))

if __name__=='__main__':main()
