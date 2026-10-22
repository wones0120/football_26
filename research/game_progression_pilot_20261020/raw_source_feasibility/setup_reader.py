"""One temporary reader setup; repository/application dependencies stay unchanged."""
from pathlib import Path
from datetime import datetime,UTC
import json,subprocess,sys,tempfile,time

D=Path(__file__).resolve().parent

def main():
    start=time.monotonic()
    with (D/'READER_STARTED.json').open('x')as s:json.dump(dict(started_at=datetime.now(UTC).isoformat(),cap_seconds=60),s)
    target=Path(tempfile.mkdtemp(prefix='scenario_raw_rds_reader_'))
    args=[sys.executable,'-m','pip','--isolated','install','--index-url','https://pypi.org/simple','--no-deps',
        '--only-binary=:all:','--no-cache-dir','--disable-pip-version-check','--retries','0','--timeout','10',
        '--target',str(target),'--report',str(D/'READER_INSTALL_REPORT.json'),'rdata==1.1.0','xarray==2025.1.2']
    result=subprocess.run(args,capture_output=True,text=True,timeout=60)
    (D/'READER_SETUP.log').write_text(result.stdout+result.stderr)
    report=dict(started_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,target=str(target),
        returncode=result.returncode,pins=['rdata==1.1.0','xarray==2025.1.2'],application_environment_unchanged=True)
    if result.returncode==0:
        sys.path.insert(0,str(target));import rdata,xarray,numpy,pandas
        report['versions']={m.__name__:m.__version__ for m in (rdata,xarray,numpy,pandas)}
    with (D/'READER.json').open('x')as s:json.dump(report,s,indent=2);s.write('\n')
    print(json.dumps(report))
    if result.returncode:raise RuntimeError('Reader setup failed; no retry')

if __name__=='__main__':main()
