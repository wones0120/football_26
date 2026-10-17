import json,hashlib
from pathlib import Path
from datetime import UTC,datetime
from backend.app.product_services.analyst_packets import import_packet,packet_digest,validate
root=Path(__file__).resolve().parent
old=json.loads(Path('research/analyst_optimization_intents_20261014/packet.json').read_text());p=json.loads(json.dumps(old));now=datetime.now(UTC).isoformat();captures=json.loads((root/'primary_source_captures.json').read_text())
p.update(packet_id='THURSDAY_JSN_official_clearance_'+now.replace(':','-'),decision_at=now,frozen_at=now,predecessor={'packet_sha256':packet_digest(old),'reason':'Official JSN final-report clearance reviewed; named research eligibility and Darnold Captain permission remain user controls separate from source truth.'})
for i,c in enumerate(captures):
 p['sources'].append(dict(source_id='jsn_official_'+str(i+1),uri=c['source_uri'],coverage='verified',observed_at=c['observed_at'],available_at=c['received_at'],capture_sha256=hashlib.sha256((root/f'official_source_{i+1}.html').read_bytes()).hexdigest(),capture_kind='immutable_official_team_http_capture',source_snapshot_id=c['snapshot_id'],limitation='Final injury report has no JSN game designation; this is not the later game-day inactive list. Native salary Q remains stored separately.'))
h=p['hypotheses'][0];h['supporting_evidence'].append('Seahawks official final report: JSN full Wednesday practice, no game designation, explicitly good to go. Captured '+captures[0]['received_at'])
h['unknowns']=['Game-day inactive list is not yet published; finishing efficiency, calibrated scenario likelihood and full opponent matchup context remain unknown.','Raw salary-native Q remains preserved. Named JSN eligibility is a user research preference; no model projection or source status is overwritten.']
p['optimization_intents']['EXPECTED_GAME']['supporting_evidence']=h['supporting_evidence'];p['optimization_intents']['EXPECTED_GAME']['unknowns']=h['unknowns'];p['optimization_intents']['EXPECTED_GAME']['source_ids']+=['jsn_official_1','jsn_official_2']
p['revision_notes']=['Reviewed newly captured official JSN clearance; unchanged primary/alternate scenario factors, original clocks and baseline projections. Named eligibility controls are separate user preferences. CONSTRUCTION comparison uses this same Expected Game evidence and frozen input build, with original generation/scoring policy.']
assert not validate(p),validate(p)
(root/'packet.json').write_text(json.dumps(p,indent=2)+'\n');receipt=import_packet(p);(root/'packet_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(receipt)
