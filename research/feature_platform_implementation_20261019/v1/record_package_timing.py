"""Append a first-party timestamp at the actual package stage; never backfill starts."""
from datetime import datetime,UTC
from pathlib import Path
import argparse,json,os
p=argparse.ArgumentParser();p.add_argument('--package',required=True);p.add_argument('--agent',required=True);p.add_argument('--stage',required=True,choices=['package_start','review_ready','high_start','approval','rework_start','rework_end','source_start','source_end','timing_adopted','wait_start','wait_end']);p.add_argument('--evidence',default='');p.add_argument('--notes',default='');a=p.parse_args()
aliases=json.loads(Path(__file__).with_name('PACKAGE_TIMING_ALIASES.json').read_text())
evidence_index=json.loads(Path(__file__).with_name('PACKAGE_TIMING_EVIDENCE_INDEX.json').read_text())
canonical=evidence_index.get(a.evidence,{}).get('canonical_package',aliases.get(a.package,a.package))
row=dict(package=canonical,agent=a.agent,stage=a.stage,timestamp=datetime.now(UTC).isoformat(),clock_basis='recorded_at_stage_by_owning_agent_UTC',evidence=a.evidence,notes=a.notes)
raw=(json.dumps(row,separators=(',',':'))+'\n').encode();assert len(raw)<=4096
fd=os.open(Path(__file__).with_name('PACKAGE_TIMINGS.jsonl'),os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o644)
try:assert os.write(fd,raw)==len(raw)
finally:os.close(fd)
print(json.dumps(row))
