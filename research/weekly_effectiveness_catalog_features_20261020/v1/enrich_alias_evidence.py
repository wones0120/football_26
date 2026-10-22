from pathlib import Path
from datetime import datetime,UTC
import hashlib,json,subprocess,os
from sqlalchemy import text
from backend.app.db import engine
p=Path('artifacts/weekly_effectiveness_sources/43e3899269f55b49faa6f2c7822a262613e75bb38b8ebd0ff995153d5303931e.json');raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()==p.stem
v=json.loads(raw);now=datetime.now(UTC);keys=sorted({r['source_player_id'] for r in v['rows'] if r.get('source_player_id')});aliases={}
with engine.connect() as c:
 for a in c.execute(text("SELECT alias_id,source_key,source_system,player_master_id,created_at FROM public.player_alias WHERE source_system='nflreadpy' AND source_key=ANY(CAST(:keys AS text[])) AND created_at AT TIME ZONE 'UTC'<=:cutoff ORDER BY source_key,alias_id"),dict(keys=keys,cutoff=now)).mappings():
  a=dict(a);a['created_at']=a['created_at'].replace(tzinfo=UTC).isoformat();a['player_master_id']=str(a['player_master_id']);aliases.setdefault(a['source_key'],[]).append(a)
changed=0
for r in v['rows']:
 proof=aliases.get(r.get('source_player_id'),[]);ids={a['player_master_id'] for a in proof};pid=next(iter(ids)) if len(ids)==1 else None
 changed+=r['player_master_id']!=pid;r['player_master_id']=pid;r['native_alias_evidence']=proof
v['prior_raw_extract_ref']=dict(path=str(p.resolve()),sha256=p.stem,bytes=len(raw));v['actual_alias_evidence_read_at']=now.isoformat();v['alias_evidence_meaning']='Exact native persisted aliases known at actual enrichment; original raw import clocks unchanged, no historical availability claim';v['actual_extracted_at']=now.isoformat()
raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(raw).hexdigest();out=p.parent/(sha+'.json')
if not out.exists():
 with out.open('xb') as f:f.write(raw)
 out.chmod(0o444)
root=Path('research/weekly_effectiveness_catalog_features_20261020/v1');(root/'alias_evidence_receipt.json').write_text(json.dumps(dict(actual_read_at=now.isoformat(),source_ref=dict(path=str(out.resolve()),sha256=sha,bytes=len(raw)),prior_ref=v['prior_raw_extract_ref'],native_keys_with_proof=len(aliases),alias_rows=sum(map(len,aliases.values())),changed_canonical_attachments=changed,original_historical_availability=False),indent=2)+'\n')
subprocess.run(['.venv/bin/python',str(root/'derive_actual.py'),'--source',str(out)],check=True,env=dict(os.environ,PYTHONPATH='.'))
