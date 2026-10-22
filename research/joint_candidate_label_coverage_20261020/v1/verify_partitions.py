"""Small derived-output check only; no approved source cache reread."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib
R=Path(__file__).resolve().parent;receipt=json.loads((R/'ACTUAL_RECEIPT.json').read_text());ref=receipt['full_ref'];b=Path(ref['path']).read_bytes();assert len(b)==ref['bytes']and hashlib.sha256(b).hexdigest()==ref['sha256'];groups=json.loads(b)['groups'];counts={}
for season in(2023,2024,2025,2026):
 rs=[r for r in groups if r['period']//100==season and r['history_achieved']];channels={}
 for c in('pass_attempts','rush_attempts','targets'):
  known=[r for r in rs if r['channels'][c]['source_observed_budget']is not None]
  for r in known:assert r['channels'][c]['source_known_candidate_plus_outside_sum']==r['channels'][c]['source_observed_budget']
  channels[c]=dict(known_budget_partition_identities=len(known),still_unknown_candidate_groups=sum(r['channels'][c]['unknown_candidate_count']>0 for r in known))
 counts[season]=channels
(R/'PARTITION_CHECK.json').write_text(json.dumps(dict(checked_at=datetime.now(UTC).isoformat(),full_ref=ref,counts=counts,meaning='Identity over RETAINED current source rows passes; it does not prove absent-candidate actualzero or independent complete budget census',fits=0),indent=2)+'\n')
