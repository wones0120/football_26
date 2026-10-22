"""Two immutable original team documents -> scoped coordinator transition."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time
from backend.app.product_services.documented_coordinator_change import extract_coordinator_statement,build_documented_coordinator_change
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock
ROOT=Path('research/documented_coordinator_change_20261020/v1');started=datetime.now(UTC);timer=time.monotonic()
source_receipt=json.loads((ROOT/'source_receipt.json').read_text());assert clock(source_receipt['actual_completed_at'])<=started
assert len(source_receipt['sources'])==2 and {s['kind']for s in source_receipt['sources']}=={'departure','appointment'}
authority=dict(host='www.neworleanssaints.com',team_id='NO',team_name='New Orleans Saints');people={'departure':'Pete Carmichael','appointment':'Klint Kubiak'};facts={};refs=[]
for s in source_receipt['sources']:
 p=Path(s['path']);raw=p.read_bytes();assert len(raw)==s['bytes'] and hashlib.sha256(raw).hexdigest()==s['sha256']
 mp=Path(s['manifest_path']);mb=mp.read_bytes();m=json.loads(mb)
 assert m['snapshot_id']==s['snapshot_id'] and m['source_uri']==s['source_uri'] and m['content_sha256']==s['sha256'] and m['byte_count']==s['bytes']
 assert m['source_system']=='official_team' and m['dataset']=='coordinator_announcement' and m['media_type']=='text/html' and m['metadata']['contract']=='official_team_coordinator_announcement_source_v1' and m['metadata']['team_id']==authority['team_id']
 assert clock(m['observed_at'])==clock(s['observed_at']) and clock(m['captured_at'])==clock(s['captured_at']) and clock(m['effective_at'])==clock(s['snapshot_effective_at']) and s['employment_effective_at']is None
 index=dict(s,team_id=m['metadata']['team_id']);facts[s['kind']]=extract_coordinator_statement(raw,index,authority=authority,kind=s['kind'],person=people[s['kind']],role='offensive_coordinator',actual_cutoff=started)
 refs.append(dict(source_index=s,manifest_ref=dict(path=str(mp.resolve()),sha256=hashlib.sha256(mb).hexdigest(),bytes=len(mb))))
x=build_documented_coordinator_change(facts['departure'],facts['appointment']);x['provenance']=dict(source_refs=refs,authority=authority,coaches='Literal source-documented coach mentions; no player-master/name join or inferred coach canonical identity',actual_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/documented_coordinator_change.py').read_bytes()).hexdigest(),source_capture_code_sha256=hashlib.sha256(Path('backend/app/services/source_capture.py').read_bytes()).hexdigest(),chronology='Source-reported2024 publication/effective upper bounds and2026 capture distinct. No original pregame capture, exact employment, continuous vacancy or measured-game applicability claim.')
b=json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(b).hexdigest();p=Path('artifacts/documented_coordinator_change')/(sha+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==b
else:
 with p.open('xb')as f:f.write(b)
 p.chmod(0o444)
ref=dict(path=str(p.resolve()),sha256=sha,bytes=len(b));out=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,full_ref=ref,semantic_sha256=x['semantic_sha256'],native_team_id=x['team_id'],source_observations=2,documented_transitions=1,outgoing_article_id=x['outgoing']['source_article_id'],incoming_article_id=x['incoming']['source_article_id'],outgoing_announcement_at=x['outgoing']['reported_announcement_at'],incoming_announcement_at=x['incoming']['reported_announcement_at'],announcement_gap_seconds=x['announcement_interval_seconds'],actual_vacancy_duration=None,target_game_applicability=None,new_captures=0,database_reads=0,database_writes=0,player_aliases=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out),flush=True)
