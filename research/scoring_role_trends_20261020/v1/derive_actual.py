"""Compose reviewed immutable zone counts; never inflate the event parent."""
from datetime import datetime, UTC
from pathlib import Path
import hashlib, json, time
from sqlalchemy.orm import Session
from backend.app.db import engine
from backend.app.models import SourceSnapshot
from backend.app.services.source_capture import verify_snapshot_artifact
from backend.app.product_services.scoring_role_trends import build_scoring_role_trends
from backend.app.product_services import player_scoring_zone_components as producer
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock

root = Path('research/scoring_role_trends_20261020/v1')
start = time.monotonic(); now = datetime.now(UTC)
r = json.loads(Path('research/player_scoring_zone_components_20261020/v1/actual_derivation_receipt.json').read_text())
ref = r['full_ref']; path = Path(ref['path']).resolve(); raw = path.read_bytes()
assert path.parent == Path('artifacts/player_scoring_zone_components').resolve()
assert path.name == ref['sha256'] + '.json' and len(raw) == ref['bytes'] <= 8*1024*1024
assert hashlib.sha256(raw).hexdigest() == ref['sha256']
source = json.loads(raw); provenance = source['provenance']
assert provenance['producer_code_sha256'] == hashlib.sha256(Path(producer.__file__).read_bytes()).hexdigest()
assert datetime.fromisoformat(provenance['actual_publication_at']) <= now
parent = provenance['retrospective_read']['parent_artifact_ref']
parentpath = Path(parent['path']).resolve()
assert parentpath.parent == Path('artifacts/opportunity_events').resolve()
assert parentpath.name == parent['artifact_sha256'] + '.json.gz' and parentpath.stat().st_size == parent['compressed_bytes']
h = hashlib.sha256()
with parentpath.open('rb') as f:
    for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
assert h.hexdigest() == parent['artifact_sha256']
with Session(engine) as session:
    snapshot = session.get(SourceSnapshot, parent['source_snapshot_id'])
    verify_snapshot_artifact(snapshot)
    assert snapshot.content_sha256 == parent['source_sha256'] == provenance['source']['content_sha256']
    assert str(snapshot.snapshot_id) == provenance['source']['snapshot_id']
    assert parent['event_receipt_sha256'] == provenance['event_receipt_sha256']
    assert source['before_period'] == parent['before_period']
    assert clock(snapshot.observed_at) <= clock(snapshot.captured_at) <= clock(parent['decision_cutoff_at']) <= clock(provenance['actual_publication_at']) <= now
    assert clock(parent['decision_cutoff_at']) == clock(provenance['retrospective_read']['original_evidence_boundary_at'])
result = build_scoring_role_trends(source, before_period=source['before_period'])
result['provenance'].update(immutable_input_ref=ref, actual_composition_read_at=now.isoformat(),
                          actual_publication_at=datetime.now(UTC).isoformat(),
                          catalog_producer_code_sha256=hashlib.sha256(Path('backend/app/product_services/scoring_role_trends.py').read_bytes()).hexdigest())

def save(value):
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    assert len(payload) <= 16*1024*1024
    sha = hashlib.sha256(payload).hexdigest(); path = Path('artifacts/scoring_role_trends') / (sha + '.json')
    path.parent.mkdir(exist_ok=True)
    if path.exists(): assert path.read_bytes() == payload
    else:
        with path.open('xb') as f: f.write(payload)
        path.chmod(0o444)
    return dict(path=str(path.resolve()), sha256=sha, bytes=len(payload))

full = save(result)
selected = {k: v for k, v in result.items() if k not in {'actor_trends', 'provenance', 'semantic_sha256'}}
selected['actor_trends'] = [r for r in result['actor_trends'] if r['season'] == 2026 and r['team'] in {'SF', 'WAS'}]
selected['selected_semantic_sha256'] = digest(selected)
selected['provenance'] = result['provenance'] | dict(full_ref=full)
sel = save(selected)
receipt = dict(actual_read_at=now.isoformat(), actual_completed_at=datetime.now(UTC).isoformat(),
               elapsed_seconds=time.monotonic()-start, full_ref=full, selected_ref=sel, input_ref=ref,
               actor_team_profiles=len(result['actor_trends']), selected_profiles=len(selected['actor_trends']),
               known_changes={mid: sum(row['metrics'][mid]['share_change'] is not None for row in result['actor_trends']) for mid in next(iter(result['actor_trends']))['metrics']},
               global_semantic_sha256=result['semantic_sha256'], selected_semantic_sha256=selected['selected_semantic_sha256'],
               parent_inflated=False, source_fetches=0, database_writes=0, models=0, evidence_use=result['evidence_use'])
(root/'actual_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
print(json.dumps(receipt))
