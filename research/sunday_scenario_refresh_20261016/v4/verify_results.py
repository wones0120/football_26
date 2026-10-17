from pathlib import Path
from collections import Counter
from itertools import combinations
import json,hashlib
from backend.app.product_services.analyst_packets import validate,clock,load_packet
P=Path(__file__).resolve().parent
load=lambda p:json.loads(Path(p).read_text())
packet=load(P/'packet.json');assert not validate(packet)
assert len(packet['games'])==len(packet['analyst_assessments'])==len(packet['hypotheses'])==10
assert len({h['game_id'] for h in packet['hypotheses']})==10
assert all(clock(s['available_at'])<=clock(packet['decision_at']) for s in packet['sources'] if s['coverage']=='verified')
base=load('artifacts/preliminary_optimizer_snapshots/6d662321caa3a513bb7720d68f836aca4cad96581314757c5e35d7d794ae207a.json');byid={r['player_id']:r for r in base['pool']};baseline=load('research/sunday_accepted_defense_refresh_20261016/v2/saved_run.json');arms={};expected=load('research/sunday_accepted_defense_refresh_20261016/v2/saved_settings.json')['params']
for arm in ['old_scenarios_friday_eligibility','refreshed_scenarios']:
 A=P.parent/'v2' if arm=='old_scenarios_friday_eligibility' else P
 req=load(A/(arm+'_request.json'));job=load(A/(arm+'_saved_run.json'));snap=load(Path('artifacts/preliminary_optimizer_snapshots')/(req['snapshot_sha256']+'.json'));assert snap['pool']==base['pool'] and snap['pool_attrs']==base['pool_attrs'];assert snap['data_cutoff_at']==base['data_cutoff_at'];assert snap['entry_ready'] is False
 excluded=set(snap['assumption_manifest']['exclude_player_ids']);assert len(excluded)==46
 for key,value in expected.items():
  if key=='exclude_player_ids':
   assert req['optimizer']['params'].get(key)==value
   assert set(job['params'].get(key,[]))==set(value)|excluded
  else:assert job['params'].get(key)==value,(arm,key,value,job['params'].get(key))
 assert job['params']['analyst_joint_opportunity_enabled'] is False and job['params'].get('analyst_optimization_intent','MIXED')=='MIXED'
 assert job['projection_run_id']==base['projection_run_id'] and job['status']=='completed' and len(job['results'])==5
 assert job['params']['entry_readiness']['entry_ready'] is False
 ids=lambda rs:frozenset(r['player_id'] for r in rs)
 assert len({ids(rs) for rs in job['results']})==5
 for rs in job['results']:
  assert len(rs)==len(ids(rs))==9 and not ids(rs)&excluded
  counts=Counter(r['position'] for r in rs);assert counts['QB']==counts['TE']==counts['DST']==1 and counts['RB']>=2 and counts['WR']>=3 and counts['RB']+counts['WR']==6
  assert sum(r['salary'] for r in rs)<=50000
  assert max(Counter(r['player_team'] for r in rs).values())<=3
  assert max(Counter(r['canonical_game_id'] for r in rs).values())<=4
  assert all(r['opponent_team']!='DEN' and r['entry_ready'] is False for r in rs)
  dst=next(r for r in rs if r['position']=='DST');assert all(r['player_team']!=dst['opponent_team'] for r in rs if r['position']!='DST')
  for r in rs:
   assert all(r[k]==byid[r['player_id']][k] for k in ['projection','p90','salary','dk_player_id']),r['name']
  for pos in ['QB','RB','WR','TE']:
   eligible=job['params']['strategy_runtime']['season_ppg_rank_preference']['eligible_ids'][pos];assert all(r['player_id'] in eligible for r in rs if r['position']==pos)
 assert max(Counter(r['player_id'] for rs in job['results'] for r in rs).values())<=4
 assert max(len(ids(a)&ids(b)) for a,b in combinations(job['results'],2))<=5
 arms[arm]=dict(request=req,job=job,snapshot=snap)
a,b=arms.values();assert a['snapshot']['pool_sha256']==b['snapshot']['pool_sha256'];assert a['snapshot']['assumption_manifest']['exclude_player_ids']==b['snapshot']['assumption_manifest']['exclude_player_ids']
for key in expected:assert a['job']['params'].get(key)==b['job']['params'].get(key)
hand=load(P/'refreshed_scenarios_handoff.json');assert hand['source_packet_sha256']==load(P/'packet_receipt.json')['analyst_packet_sha256'];assert b['job']['params']['analyst_handoff_applied']['checked_packet_sha256']==hand['checked_packet_sha256'];assert hand['research_decision_at']==packet['decision_at']
result=dict(status='PASS',checks=['10 substantive canonical game hypotheses/assessments','all source availability clocks before authored decision','all frozen pool/attrs/projections/native IDs exact','both arms identical46source exclusions','exact saved user controls preserved','Mixed retained; no new Rams cap; joint prototype false','five distinct legal nine-player rosters','salary/team/game/exposure/overlap/DEN/Q/source eligibility','singleTE and no offense versus DST','top50historicalrank policy','saved checked packet actually applied','preliminary entry_ready=false'],authored_packet_sha256=hand['source_packet_sha256'],checked_packet_sha256=hand['checked_packet_sha256'],machine_review_status=hand['status'],saved_run_ids={arm:data['job']['job_id'] for arm,data in arms.items()},comparison_kind='matched generation experiment; candidate pools differ; no calibrated win probability',original_bebc_artifact_sha256=hashlib.sha256(Path('research/sunday_accepted_defense_refresh_20261016/v2/saved_run.json').read_bytes()).hexdigest())
(P/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
