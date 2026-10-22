"""Independent first-G2 join and reviewed native rush outcomes; no PBP reload."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,gc
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.participation_source_components import load_participation_snapshot
from backend.app.product_services.guard_interior_response import build_guard_interior_response,persist_guard_identity_requests
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock
root=Path('research/guard_interior_response_20261020/v1');started=datetime.now(UTC);start=time.monotonic();first=[];rush=[];parts=[];inputs=[]
centers=json.loads(Path('research/center_sack_response_20261020/v1/actual_receipt.json').read_text())['source_inputs']
rushers={r['season']:r for r in json.loads(Path('research/defensive_front_rush_exposure_20261020/v1/actual_receipt.json').read_text())['outputs']}
g16=json.loads(Path('research/coverage_receiver_performance_20261020/v1/actual_receipt.json').read_text())
paths=[Path('backend/app/product_services/'+name+'.py')for name in('guard_interior_response','center_sack_response','defensive_front_rush_exposure','offensive_line_participation','participation_source_components','coverage_receiver_performance')]
code={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in paths}
def load(ref,folder,external_flags=False):
 p=Path(ref['path']);assert p.resolve().parent==Path('artifacts',folder).resolve();raw=p.read_bytes();assert len(raw)==ref['bytes']and hashlib.sha256(raw).hexdigest()==ref['sha256'];value=json.loads(raw)
 exclude={'semantic_sha256','provenance'}|({'evidence_use','pregame_serving_eligible','forecast'}if external_flags else set())
 assert digest({k:v for k,v in value.items()if k not in exclude})==value['semantic_sha256'];assert value['pregame_serving_eligible']is False
 return value

def save(value):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=32*1024*1024
 sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/guard_interior_response')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb')as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
identity_ref=g16['outputs'][0]['full_ref'];identity_source=load(identity_ref,'coverage_receiver_performance',external_flags=True)
cutoff=clock(identity_source['provenance']['actual_alias_cutoff_at']);assert cutoff<=started
assert clock(identity_source['provenance']['actual_publication_at'])<=started
assert identity_source['provenance']['producer_code_hashes']['backend/app/product_services/coverage_receiver_performance.py']==code['backend/app/product_services/coverage_receiver_performance.py']
universe=set(identity_source['native_identity_receipts']);alias_rows=[row for receipt in identity_source['native_identity_receipts'].values()for row in receipt['original_alias_evidence']]
assert len(alias_rows)==len({(row['alias_id'],row['source_key'])for row in alias_rows})
with Session(engine)as session:
 for entry in centers:
  season=entry['season'];r=rushers[season];f=load(entry['center_ref'],'center_sack_response');response=load(r['full_ref'],'defensive_front_rush_exposure');read=datetime.now(UTC)
  assert clock(f['provenance']['actual_publication_at'])<=read and clock(response['provenance']['actual_publication_at'])<=read
  assert f['provenance']['producer_code_sha256']==code['backend/app/product_services/center_sack_response.py']and response['provenance']['producer_code_sha256']==code['backend/app/product_services/defensive_front_rush_exposure.py']
  snapshot=session.get(SourceSnapshot,r['native_source_snapshot_id']);p=load_participation_snapshot(snapshot,actual_read_at=read)
  assert p['semantic_sha256']==f['provenance']['participation_semantic_sha256']
  first.append(f);rush.append(response);parts.append(p);inputs.append(dict(season=season,firstsnap_ref=entry['center_ref'],rush_ref=r['full_ref'],participation_snapshot_id=str(snapshot.snapshot_id),participation_sha256=snapshot.content_sha256,actual_read_at=read.isoformat()))
result=build_guard_interior_response(first,rush,parts,alias_rows,cutoff=cutoff,identity_universe=universe)
assert result['native_identity_receipts']==identity_source['native_identity_receipts']
result['provenance']=dict(source_inputs=inputs,frozen_identity_source_ref=identity_ref,frozen_alias_cutoff_at=cutoff.isoformat(),actual_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_hashes=code,
 identity_policy='Recomputed global source-native identities from the exact previously reviewed frozen alias receipts; no current alias DB read, no claim of refreshed identity state',original_pregame_availability='unknown; source postseason/revised historical capture, never backdated')
full=save(result);selected={k:v for k,v in result.items()if k not in('starting_guard_units','game_rows','profiles','prior_windows','event_basis','identity_review_requests','semantic_sha256','provenance')}
for key in('starting_guard_units','game_rows','profiles','prior_windows','identity_review_requests'):selected[key]=[r for r in result[key]if r['team']in{'SF','WAS'}]
gids={r['game_id']for r in selected['game_rows']};selected['event_basis']=[e for e in result['event_basis']if e['game_id']in gids];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
with engine.begin()as connection:queue=persist_guard_identity_requests(connection,result,source_refs=[full])
if queue['records']:
 with engine.connect()as connection:
  queue['durable_readback_records']=[dict(r)for r in connection.execute(text("SELECT identity_quarantine_id,source_table,source_record_key,source_player_key,status,first_seen_at,updated_at FROM target.identity_quarantine WHERE source_schema='public' AND source_record_key=ANY(CAST(:keys AS text[]))"),dict(keys=[r['source_record_key']for r in queue['records']])).mappings()]
 assert len(queue['durable_readback_records'])==queue['requests']
per_season={year:dict(expected_sides=sum(u['season']==year for u in result['starting_guard_units']),known_first_G2=sum(u['season']==year and u['source_proven_guard_pair']for u in result['starting_guard_units']),
 known_classes={k:sum(r['season']==year and r['guard_class']==k for r in result['game_rows'])for k in('same','changed')},unknown_classes=sum(r['season']==year and r['comparison_applicable']and r['guard_class']is None for r in result['game_rows']),
 defined_profile_contrasts={k:sum(p['season']==year and p[k]is not None for p in result['profiles'])for k in('same_minus_changed_yards','same_minus_changed_EPA')},
 defined_prior_contrasts={k:sum(p['season']==year and p[k]is not None for p in result['prior_windows'])for k in('same_minus_changed_yards','same_minus_changed_EPA')})for year in sorted(rushers)}
r=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,source_inputs=inputs,frozen_identity_source_ref=identity_ref,frozen_alias_cutoff_at=cutoff.isoformat(),full_ref=full,selected_ref=sel,global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],per_season=per_season,queue=queue,
 source_fetches=0,PBP_reads=0,parent_inflates=0,new_alias_reads=0,models=0,alias_mutations=0,evidence_use=result['evidence_use'],pregame_serving_eligible=False)
(root/'actual_receipt.json').write_text(json.dumps(r,indent=2,default=str)+'\n');print(json.dumps(dict(stage='END',elapsed_seconds=r['elapsed_seconds'],per_season=per_season,queue_requests=queue['requests'])),flush=True)
