"""Independent legality/identity and matched-input checks on saved real results."""
from collections import Counter
from pathlib import Path
from uuid import UUID
import json
import math
import hashlib

from backend.app.product_services.preliminary_optimizer import load_snapshot
from backend.app.product_services.classic_favored_preferences import is_favored

root=Path('research/sunday_main_merged_comparison_20261013')
receipt=json.loads((root/'preliminary_snapshot_receipt.json').read_text());snapshot=load_snapshot(receipt['snapshot_sha256'])
source={str(p['player_id']):p for p in snapshot['pool']}
results={arm:json.loads((root/filename).read_text()) for arm,filename in [('original','old_result_v2.json'),('merged','merged_result_v3.json')]}
checks=[]
for arm,result in results.items():
 assert result['lineage_persisted'] and result['status']=='completed' and len(result['results'])==5
 assert result['entry_readiness']['entry_ready'] is False and result['data_readiness']['status']=='ERROR'
 preliminary=result['preliminary_report']
 for key in ['snapshot_sha256','source_sha256','pool_sha256','assumption_manifest_sha256']:
  assert preliminary[key]==receipt[key]
 assert result['projection_run_id']==snapshot['projection_run_id']
 ids_by_lineup=[]
 for number,lineup in enumerate(result['results'],1):
  ids=[str(p['player_id']) for p in lineup]
  assert len(ids)==len(set(ids))==9
  for pid in ids:UUID(pid)
  positions=Counter(p['position'] for p in lineup)
  assert positions['QB']==positions['DST']==positions['TE']==1 and positions['RB']>=2 and positions['WR']>=3
  assert sum(float(p['salary']) for p in lineup)<=50000
  team=Counter(p['player_team'] for p in lineup);games=Counter(tuple(sorted([p['player_team'],p['opponent_team']])) for p in lineup)
  assert max(team.values())<=4 and max(games.values())<=5
  for p in lineup:
   raw=source[str(p['player_id'])]
   assert float(p['projection'])==float(raw['projection']) and float(p['p90'])==float(raw['p90'])
   assert float(p['salary'])==float(raw['salary'])
   assert math.isfinite(float(p['projection'])) and math.isfinite(float(p['p90']))
   assert p['preliminary_research'] is True and p['entry_ready'] is False
   assert str(p['player_id']) not in snapshot['assumption_manifest']['exclude_player_ids']
   assert str(raw.get('availability_status') or '').upper() not in {'Q','QUESTIONABLE','OUT','IR','PS','DEV','PUP'}
   if p['position'] in {'QB','RB'}:assert float(p['salary'])>=4500
   if p['position'] in {'RB','TE','DST'}:assert is_favored(p)
   if p['position']=='DST':assert not any(q['position']!='DST' and q['player_team']==p['opponent_team'] for q in lineup)
  for prior in ids_by_lineup:assert len(set(ids)&prior)<=7
  ids_by_lineup.append(set(ids));checks.append({'arm':arm,'lineup':number,'status':'PASS','canonical_players':ids,'salary':sum(float(p['salary']) for p in lineup)})
code_files=['backend/app/product_services/preliminary_optimizer.py','backend/app/product_services/analyst_scenarios.py','backend/app/product_services/gpp_optimizer.py','backend/app/product_services/optimizer.py']
report=dict(status='PASS',classification='PRELIMINARY_RESEARCH',entry_ready=False,checks=checks,
 source_snapshot_sha256=receipt['snapshot_sha256'],assumption_manifest_sha256=receipt['assumption_manifest_sha256'],
 code_sha256={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in code_files},
 preserved_failures=['Normal preparation readiness ERROR','Initial rank-preference prerequisite failures','Merged missing-distribution failure before bounded fix'])
(root/'independent_verification.json').write_text(json.dumps(report,indent=2)+'\n');print('PASS: both 5-lineup portfolios, exact shared source/assumption hashes, base projections/salaries, canonical IDs, all stated hard controls, final entry false')
