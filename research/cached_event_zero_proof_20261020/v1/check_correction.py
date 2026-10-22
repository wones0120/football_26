from pathlib import Path
import json,hashlib
from datetime import datetime,UTC
R=Path(__file__).resolve().parent;old=json.loads((R/'prior_18test_revision/ACTUAL_RECEIPT.json').read_text());new=json.loads((R/'ACTUAL_RECEIPT.json').read_text())
def read(ref):
 b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];return json.loads(b)
a=read(old['full_ref'])['groups'];b=read(new['full_ref'])['groups'];assert len(a)==len(b)
oldzero={(r['game_id'],r['team'],p['source_player_id'],p['channel']):p['zero']for r in a for p in r['missing_candidate_proofs']};newzero={(r['game_id'],r['team'],p['source_player_id'],p['channel']):p['zero']for r in b for p in r['missing_candidate_proofs']};assert oldzero==newzero
conflicts=[]
for r in b:
 for channel,c in r['channels'].items():
  if r['history_achieved']and c['native_labels_complete_with_scoped_event_zero_proofs']and c['known_weekly_native_credit_compatibility']['status']=='CONTRADICTED':conflicts.append(dict(game_id=r['game_id'],team=r['team'],channel=channel,**c['known_weekly_native_credit_compatibility']))
result=dict(checked_at=datetime.now(UTC).isoformat(),prior_measurement_ref=old['full_ref'],current_measurement_ref=new['full_ref'],all_missing_candidate_zero_decisions_equal=True,decisions=len(newzero),actual_source_conflicts=conflicts,source_raw_rereads=0,fits=0)
(R/'CORRECTION_PARITY.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
