"""Immutable primary documents and reviewed native schedule -> explicit calling transition."""
from pathlib import Path
from datetime import datetime,UTC
import csv,json,hashlib,time
from backend.app.product_services.documented_playcaller_change import parse_primary_article,build_documented_playcaller_change
from backend.app.product_services.factual_designation import clock
ROOT=Path('research/documented_playcaller_change_20261020/v1');started=datetime.now(UTC);timer=time.monotonic()
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def read(r):
 b=Path(r['path']).read_bytes();assert len(b)==r['bytes']and hashlib.sha256(b).hexdigest()==r['sha256'];return b
receipt=json.loads((ROOT/'source_receipt.json').read_text());assert clock(receipt['actual_completed_at'])<=started
assert len(receipt['sources'])==2 and {s['kind']for s in receipt['sources']}=={'preview','confirmation'}
authority=dict(host='www.buffalobills.com',team_id='BUF',team_short_name='Bills');context=dict(opponent_id='NYJ',opponent_short_name='Jets',opponent_full_name='New York Jets',season=2023,week=11,outgoing_person='Ken Dorsey',incoming_person='Joe Brady');facts={};refs=[]
for s in receipt['sources']:
 raw=read(s);m=json.loads(Path(s['manifest_path']).read_text())
 assert m['snapshot_id']==s['snapshot_id']and m['source_uri']==s['source_uri']and m['content_sha256']==s['sha256']and m['byte_count']==s['bytes']
 assert m['source_system']=='official_team'and m['dataset']=='playcaller_announcement'and m['media_type']=='text/html'and m['metadata']['contract']=='official_team_playcaller_announcement_source_v1'and m['metadata']['team_id']=='BUF'and m['metadata']['document_kind']==s['kind']
 assert clock(m['captured_at'])==clock(s['captured_at'])and clock(m['observed_at'])==clock(s['observed_at'])and clock(m['effective_at'])==clock(s['snapshot_effective_at'])and s['employment_effective_at']is None
 facts[s['kind']]=parse_primary_article(raw,dict(s,team_id='BUF'),authority=authority,actual_cutoff=started);refs.append(dict(source_index=s,manifest_ref=ref(s['manifest_path'])))
parent=json.loads(Path('research/scheduled_venue_displacement_20261020/v1/actual_receipt.json').read_text())['full_ref'];p=json.loads(read(parent));schedule=p['provenance']['schedule_csv_ref'];rows=list(csv.DictReader(read(schedule).decode().splitlines()));games=[r for r in rows if r['game_id']=='2023_11_NYJ_BUF'];assert len(games)==1
game=games[0].copy();game['season']=int(game['season']);game['week']=int(game['week']);x=build_documented_playcaller_change(facts['preview'],facts['confirmation'],game,authority=authority,context=context)
x['provenance']=dict(source_refs=refs,approved_schedule_parent_ref=parent,schedule_csv_ref=schedule,native_schedule_row=games[0],authority=authority,context=context,actual_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_ref=ref('backend/app/product_services/documented_playcaller_change.py'),article_parser_helper_ref=ref('backend/app/product_services/documented_coordinator_change.py'),kickoff_helper_ref=ref('backend/app/product_services/scheduled_venue_displacement.py'),chronology='2023 publisher clocks are claims in captured 2026 revisions; original pregame receipt and exact employment handoff unknown. Snapshot effective capture fallback is not employment effective time.',models=0,database_reads=0,database_writes=0,parent_adapter_replays=0)
b=json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode();sha=hashlib.sha256(b).hexdigest();path=Path('artifacts/documented_playcaller_change')/(sha+'.json');path.parent.mkdir(exist_ok=True)
if path.exists():assert path.read_bytes()==b
else:
 with path.open('xb')as f:f.write(b)
 path.chmod(0o444)
out=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,full_ref=ref(path),semantic_sha256=x['semantic_sha256'],documented_transitions=1,measured_game_id=x['measured_effective_game_id'],source_observations=2,new_captures=0,database_reads=0,database_writes=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
