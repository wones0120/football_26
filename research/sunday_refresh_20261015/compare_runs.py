from pathlib import Path
from collections import Counter
import json
P=Path(__file__).resolve().parent
runs={k:json.loads((P/(k+'_saved_result.json')).read_text()) for k in ['normal','contrarian']}
verification={};lines=['# Sunday Main — normal versus contrarian saved portfolios','']
for label,data in runs.items():
 run=data['run'];cfg=run['constraint_config_json'];lineups=data['lineups'];report=cfg.get('strategy_runtime',{}).get('football_analyst',{})
 exposure=Counter(p['player_id'] for l in lineups for p in l);names={p['player_id']:p['name'] for l in lineups for p in l};canonical={tuple(sorted(p['player_id'] for p in l)) for l in lineups}
 verification[label]=dict(run_id=run['optimizer_run_id'],status=run['status'],requested=cfg['num_lineups'],achieved=len(lineups),canonical_rosters=len(canonical),projection_run_id=run['projection_run_id'],ownership_run_id=cfg.get('ownership_run_id'),preliminary_report=cfg.get('preliminary_report'),analyst_handoff_applied=cfg.get('analyst_handoff_applied'),report=report,exposures=[dict(player_id=k,name=names[k],count=v,percent=100*v/len(lineups)) for k,v in exposure.most_common()])
 lines+=['## '+label.title(),'',str(run['optimizer_run_id'])+' · '+run['status']+f" · {len(lineups)}/{cfg['num_lineups']} · {len(canonical)} distinct canonical rosters",'', '| Player | Exposure |','|---|---:|']
 for k,v in exposure.most_common():lines.append(f"| {names[k]} | {v}/{len(lineups)} |")
 for i,l in enumerate(lineups,1):
  assert len(l)==9 and len({p['player_id'] for p in l})==9
  assert sum(p['salary'] for p in l)<=50000
  positions=Counter(p['position'] for p in l);assert positions['QB']==1 and positions['DST']==1 and positions['RB']>=2 and positions['WR']>=3 and positions['TE']==1 and positions['RB']+positions['WR']==6
  teams=Counter(p['player_team'] for p in l);assert max(teams.values())<=cfg.get('max_players_per_team',4)
  excluded=set((cfg.get('preliminary_report') or {})['assumption_manifest']['exclude_player_ids']);assert not excluded.intersection(p['player_id'] for p in l)
  lines+=['',f"### Lineup {i} — ${sum(p['salary'] for p in l):,}",'','| Slot | Player | Team | Salary | Base mean |','|---|---|---|---:|---:|']
  for p in l:lines.append(f"| {p['roster_position']} | {p['name']} | {p['player_team']} | ${p['salary']:,} | {p.get('projection')} |")
  qb=next(p for p in l if p['roster_position']=='QB');receivers=[p['name'] for p in l if p['player_team']==qb['player_team'] and p['position'] in ['WR','TE']];lines+=['','QB stack: '+qb['name']+' + '+(', '.join(receivers) or 'no receiver')+'.']
a,b=verification.values();assert a['projection_run_id']==b['projection_run_id'];assert a['ownership_run_id']==b['ownership_run_id'];assert a['preliminary_report']['snapshot_sha256']==b['preliminary_report']['snapshot_sha256'];assert a['analyst_handoff_applied']['source_packet_sha256']==b['analyst_handoff_applied']['source_packet_sha256']
assert a['analyst_handoff_applied']['checked_packet_sha256']!=b['analyst_handoff_applied']['checked_packet_sha256']
for x in [a,b]:assert x['preliminary_report']['entry_ready'] is False
lines+=['','Matched fresh salary/source/projection/ownership/snapshot inputs. Distinct generated candidate pools and conditional scoring policies: this is a generation experiment, not an identical-pool selector comparison. Final entry readiness remains false; no entry or export.']
(P/'verification.json').write_text(json.dumps(verification,indent=2)+'\n');(P/'LINEUP_COMPARISON.md').write_text('\n'.join(lines)+'\n');print('verified',a['run_id'],b['run_id'])
