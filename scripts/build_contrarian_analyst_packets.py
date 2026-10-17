"""Version new weekly/focus packets; preserve all prior live packet inputs."""
import json,hashlib
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone
from backend.app.product_services.analyst_packets import validate,packet_digest,clock
from backend.app.product_services.scenario_allocation import build_ideas,AllocationControls
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'research/analyst_contrarian_focus_20261014';OUT.mkdir(exist_ok=True)
weekly=json.loads((ROOT/'research/weekly_role_review_20261014/v1/packet.json').read_text());now=datetime.now(timezone.utc).isoformat()
manifest={}
for fmt,filename in [('CLASSIC','classic_packet'),('SHOWDOWN','showdown_packet')]:
 p=json.loads((ROOT/f'research/analyst_live_build_20261014/{filename}.json').read_text());parent=packet_digest(p);gids={g['game_id'] for g in p['games']};pids={r['player_master_id'] for r in p['players']};mapping={g['game_id']:next((b['game_id'] for b in p['games'] if set(b['teams'])==set(g['teams']) and clock(b['kickoff_at'])==clock(g['kickoff_at'])),None) for g in weekly['games']}
 p['packet_id']=p['packet_id']+'-weekly-contrarian-v1';p.update(decision_at=now,frozen_at=now)
 source_map={s['source_id']:'weekly_v1:'+s['source_id'] for s in weekly['sources']}
 def map_sources(value):
  if isinstance(value,dict):return {k:map_sources(v) for k,v in value.items()}
  if isinstance(value,list):return [map_sources(v) for v in value]
  return source_map.get(value,value) if isinstance(value,str) else value
 for source in weekly['sources']:
  copy=map_sources(source);copy['original_source_id']=source['source_id'];p['sources'].append(copy)
 block=map_sources(weekly['weekly_role_review']);block['observations']=[o for o in block['observations'] if o['player_master_id'] in pids];block['findings']=[f for f in block['findings'] if mapping.get(f['game_id']) in gids and fmt in f['formats']]
 for f in block['findings']:f['original_authoring_game_id']=f['game_id'];f['game_id']=mapping[f['game_id']]
 p['weekly_role_review']=block;findings=[]
 if fmt=='SHOWDOWN':
  g=p['games'][0];sid='user_what_if_DEN_scoring_breakout';base=p['scenario_assumptions']['scenarios'][0];refs=sorted({r for h in p['hypotheses'] for r in h['source_ids']});p['scenario_assumptions']['scenarios'].append(dict(scenario_id=sid,label='User what-if: Denver offense clicks, roughly40 points',hypothesis_ids=base['hypothesis_ids'],assumptions=[dict(kind='passing_volume',game_id=g['game_id'],team='DEN',factor=1.3,elasticity=.6),dict(kind='rushing_volume',game_id=g['game_id'],team='DEN',factor=.7,elasticity=.6)]))
  findings.append(dict(scenario_id=sid,game_id=g['game_id'],team='DEN',script='passing',status='user_what_if',team_points_target=40,opportunity_shift=.18,source_ids=refs,as_of=now,mechanism='Explicit user hypothesis: Denver sustains drives and passing TD opportunities; sourced current roster/outlook provide context, not confirmation of40 points.',conditions=['Protection and QB decision-making sustain multiple successful drives','Receivers convert opportunities and offense finishes touchdowns','Roughly40 points needs several scoring drives; this engine does not fit or guarantee that target'],counterevidence=['No sourced new protection/coverage change establishing a breakout was captured','Current team/game outlook is unproven and does not calibrate40-point tail likelihood'],unknowns=['Scoring efficiency and exact TD allocation under this what-if','Opponent keep-pace is unknown; no automatic bringback'],user_authorization='Explicit user Denver40-point scenario request; not a reported football fact'))
 else:
  snap=json.loads((ROOT/'artifacts/preliminary_optimizer_snapshots/1d4bd6796aac13a3fe2dcb0cc1262fce960cc2e47d8efc8c6e1a9a11d05daabe.json').read_text());rows=[r for r in snap['pool'] if r.get('availability_status')!='Q' and r.get('projection') is not None and r.get('p90') is not None]
  ideas,rejected=build_ideas(p,rows,AllocationControls())
  for game in p['games']:
   choices=[i for i in ideas if i['game_id']==game['game_id'] and i['derived_alternative']]
   if not choices:continue
   idea=max(choices,key=lambda i:(i['credibility_score'],i['idea_id']));sid='conditional_alternative:'+idea['idea_id'];kind='passing_volume' if idea['script']=='passing' else 'rushing_volume'
   p['scenario_assumptions']['scenarios'].append(dict(scenario_id=sid,label='Conditional alternative: '+idea['team']+' '+idea['script'],hypothesis_ids=idea['hypothesis_ids'],assumptions=[dict(kind=kind,game_id=game['game_id'],team=idea['team'],factor=1.2,elasticity=.6)]))
   findings.append(dict(scenario_id=sid,game_id=game['game_id'],team=idea['team'],script=idea['script'],status='supported_hypothesis',opportunity_shift=.12,source_ids=idea['verified_source_ids'],as_of=now,mechanism='Existing sourced game hypothesis with current positive role/workload supports an explicit contrary '+idea['script']+' opportunity branch; not a discovered scoring-efficiency edge.',conditions=['Current eligible primary role retained','Game opportunities favor this channel under the declared mix sensitivity'],counterevidence=['Current strongest alternative may occur instead','Missing current practice and incomplete workload evidence remain explicit; user Q exclusion is not an absence fact'],unknowns=['Exact game script and finishing efficiency','Forward likelihood uncalibrated'],ordinal_strength=idea['credibility_score'],ownership_status='No claim of low ownership'))
 p['contrarian_analysis']=dict(contract_id='contrarian_analysis_v1',findings=findings,authoring_protocol='Automatic all-game sourced opportunity candidate screening; semantic edges require separate evidence. User what-if kept distinct.');errors=validate(p)
 if errors:raise ValueError(errors)
 (OUT/f'{filename}.json').write_text(json.dumps(p,indent=2));manifest[fmt]=dict(parent_packet_sha256=parent,weekly_packet_sha256=packet_digest(weekly),packet_sha256=packet_digest(p),decision_at=now,game_mapping=mapping,findings=len(findings),baseline_mutation=False)
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2));print(manifest)
