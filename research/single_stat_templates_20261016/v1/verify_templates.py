"""Verify user templates against the existing saved reports; never assign entries."""
from datetime import UTC,datetime
from pathlib import Path
import csv,hashlib,io,json,requests
ROOT=Path(__file__).resolve().parent
PRIOR=ROOT.parents[1]/'single_stat_real_20261016'/'v1'
rows=[]
for variant,suffix in [('touchdowns','tds'),('total_yards','yards')]:
    source=Path('/Users/wones/NFL')/f'draftkings_single_stat_template_{suffix}.csv';raw=source.read_bytes();copy=ROOT/source.name
    if copy.exists() and copy.read_bytes()!=raw:raise ValueError('Original template snapshot conflict')
    if not copy.exists():copy.write_bytes(raw)
    report=json.loads((PRIOR/(variant+'_saved_report.json')).read_text())
    payload=dict(pool_sha256=report['pool_sha256'],source_name=source.name,source_reference=str(source),source_observed_at=datetime.fromtimestamp(source.stat().st_mtime,UTC).isoformat(),template_csv=raw.decode('utf-8'))
    response=requests.post('http://127.0.0.1:8000/api/single-stat/templates',json=payload,timeout=30)
    entry=dict(variant=variant,source=str(source),source_sha256=hashlib.sha256(raw).hexdigest(),report_sha256=report['sha256'],pool_sha256=report['pool_sha256'],template_http_status=response.status_code,template_result=response.json())
    if response.ok:
        verified=response.json();r=requests.get(f'http://127.0.0.1:8000/api/single-stat/records/{report["sha256"]}/download',params=dict(template_sha256=verified['sha256'],accept_research='true'),timeout=30);r.raise_for_status();(ROOT/f'{variant}_verified_download.csv').write_bytes(r.content)
        actual=list(csv.reader(io.StringIO(r.content.decode())));original=list(csv.reader(io.StringIO(raw.decode())));ids=actual[1][:3];assert ids==[p['source_player_id'] for p in report['players']];actual[1][:3]=['','',''];assert actual==original
        entry.update(download_sha256=hashlib.sha256(r.content).hexdigest(),native_roster_ids=ids,receipt_sha256=r.headers['X-Single-Stat-Export-Receipt'],preserved_template_cells=True,entry_ready=r.headers['X-Single-Stat-Entry-Ready'])
    print(variant,response.status_code,entry.get('native_roster_ids') or response.json()['detail'],flush=True);rows.append(entry)
(ROOT/'verification.json').write_text(json.dumps(rows,indent=2))
