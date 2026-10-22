from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,csv,time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.product_services.offensive_environment_catalog import load_reviewed_environment_context
from backend.app.product_services.game_clock_pace_catalog import native_order_proof,build_game_clock_pace_catalog,build_native_game_clock_context,build_native_redzone_drives,validated_native_order_map,IDS
from backend.app.product_services.evaluation_record import digest
from backend.app.services.source_capture import verify_snapshot_artifact
root=Path('research/game_clock_pace_catalog_20261020/v1');start=time.monotonic();actual=datetime.now(UTC)
r=json.loads(Path('research/environment_context_evidence_20261019/v1/actual_combined_receipt.json').read_text())
with Session(engine) as session:
 snapshot=session.get(SourceSnapshot,r['parent_artifact_ref']['source_snapshot_id']);intake=load_reviewed_environment_context(r['full_context'],snapshot,actual_read_at=actual)
 with Path(snapshot.artifact_path).open() as file:proof=native_order_proof(csv.DictReader(file),before_period=intake['context']['before_period'])
 verify_snapshot_artifact(snapshot)
from backend.app.product_services.opportunity_source_capture import load_event_artifact
from backend.app.product_services.factual_designation import clock
parent_ref=r['parent_artifact_ref'];original=clock(parent_ref['decision_cutoff_at']);lock=clock(snapshot.slate_lock_at)
if not original<lock<=actual:raise ValueError('Explicit retrospective original-boundary/current-read proof required')
parent=load_event_artifact(parent_ref,snapshot,before_period=parent_ref['before_period'],cutoff=original)
native_context=build_native_game_clock_context(parent,before_period=parent_ref['before_period'],cutoff=actual)
native_drives=build_native_redzone_drives(parent,before_period=parent_ref['before_period'],cutoff=actual)
order_map=validated_native_order_map(parent,before_period=parent_ref['before_period'],cutoff=actual)
retrospective=dict(original_evidence_boundary_at=original.isoformat(),source_lock_at=lock.isoformat(),actual_read_at=actual.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),meaning='Original cutoff verifies frozen bytes only; actual new derivation is postlock and nonserving',parent_ref=parent_ref)
for value in (native_context,native_drives):value['provenance']['retrospective_read']=retrospective
result=build_game_clock_pace_catalog(native_context,proof,before_period=native_context['before_period']);result['provenance'].update(verified_intake=intake['provenance'],actual_read_at=actual.isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),original_context_ref=r['full_context'],producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/game_clock_pace_catalog.py').read_bytes()).hexdigest())
def save(v):
 raw=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(raw)<=4*1024*1024;sha=hashlib.sha256(raw).hexdigest();p=Path('artifacts/game_clock_pace_catalog')/(sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:f.write(raw)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(raw))
native_context_ref=save(native_context);native_drives_ref=save(native_drives);order_map_ref=save(order_map)
old_ref=json.loads(Path('research/defensive_catalog_features_20261020/v1/actual_receipt.json').read_text())['extension_ref'];old_bytes=Path(old_ref['path']).read_bytes();assert hashlib.sha256(old_bytes).hexdigest()==old_ref['sha256'];old=json.loads(old_bytes);old_games={(g['game_id'],g['defense_team']):g for g in old['game_rows']}
changes=[]
for game in native_drives['game_rows']:
 prior=old_games[(game['game_id'],game['defense_team'])]
 old_drives={d['drive_id']:set(d['terminal_play_ids']) for d in prior['drive_quality']['drive_outcomes']};new_drives={d['drive_id']:set(d['terminal_play_ids']) for d in game['drive_quality']['drive_outcomes']}
 if old_drives!=new_drives:raise ValueError('Native chronology adapter lost or invented original physical terminal play evidence')
 fields=['eligible_events','known_outcome_events','unknown_outcome_events','unknown_eligibility_events','observed_outcome_sum','all_eligible_mean'];delta={f:dict(prior=prior['metrics']['G14-M10'][f],native=game['metrics']['G14-M10'][f]) for f in fields if prior['metrics']['G14-M10'][f]!=game['metrics']['G14-M10'][f]}
 if delta:changes.append(dict(game_id=game['game_id'],defense_team=game['defense_team'],changes=delta))
audit=dict(prior_extension_ref=old_ref,native_redzone_source_ref=native_drives_ref,actual_read_at=actual.isoformat(),all_entered_drives=sum(len(g['drive_quality']['observed_redzone_drive_ids']) for g in native_drives['game_rows']),native_verified_entered_drives=sum(d['native_order_verified'] for g in native_drives['game_rows'] for d in g['drive_quality']['drive_outcomes']),native_before_entry_terminals=sum(d['terminal_precedes_entry'] for g in native_drives['game_rows'] for d in g['drive_quality']['drive_outcomes']),game_metric_changes=changes)
(root/'redzone_chronology_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
full=save(result);selected={k:v for k,v in result.items() if k not in {'game_rows','team_windows','provenance','semantic_sha256'}};selected['game_rows']=[row for row in result['game_rows'] if row['team'] in {'SF','WAS'}];selected['team_windows']=[row for row in result['team_windows'] if row['team'] in {'SF','WAS'}];selected['selected_semantic_sha256']=digest(selected);selected['provenance']={**result['provenance'],'full_ref':full};sel=save(selected)
receipt=dict(actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,full_ref=full,selected_ref=sel,context_ref=r['full_context'],native_order_proof=proof,native_source_byte_sha256=snapshot.content_sha256,native_context_ref=native_context_ref,native_redzone_source_ref=native_drives_ref,native_order_map_ref=order_map_ref,chronology_audit=audit,game_rows=len(result['game_rows']),selected_rows=len(selected['game_rows']),team_windows=len(result['team_windows']),coverage={mid:dict(known_exact=sum(row['metrics'][mid]['value'] is not None for row in result['game_rows']),unknown_or_zero=sum(row['metrics'][mid]['value'] is None for row in result['game_rows'])) for mid in IDS},global_semantic_sha256=result['semantic_sha256'],selected_semantic_sha256=selected['selected_semantic_sha256'],source_fetches=0,models=0,parent_inflates=1,evidence_use=result['evidence_use'])
(root/'actual_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k!='native_order_proof'}))
