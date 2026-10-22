import json,pathlib,hashlib,collections,datetime,math
import pandas as pd
from Database.dst import normalize_team,deterministic_dst_player_id
from backend.app.product_services.dst_scoring_reconciliation import REQUIRED,score_game
root=pathlib.Path('research/joint_portfolio_selection_20261018/v1');src=pathlib.Path('research/neural_workload_benchmark_20261013/expanded_v3/sources');manifest=json.loads((src/'manifest.json').read_text())
for n in ['games.parquet','pbp_2025.parquet']:
 if hashlib.sha256((src/n).read_bytes()).hexdigest()!=manifest[n]['sha256']:raise ValueError('changed source')
stats=json.loads((root/'historical_stats.json').read_text());group=collections.defaultdict(list)
for r in stats:group[r['game_id']].append(r)
games=pd.read_parquet(src/'games.parquet');games=games[(games.season==2025)&(games.game_type=='REG')].sort_values(['gameday','gametime','game_id'])
pbp=pd.read_parquet(src/'pbp_2025.parquet',columns=sorted(REQUIRED));events={gid:g.to_dict('records')for gid,g in pbp.groupby('game_id')};history=collections.defaultdict(list);library=[];rejected=collections.Counter()
for g in games.to_dict('records'):
 gid=g['game_id'];members=group[gid];teams=[normalize_team(g['home_team']),normalize_team(g['away_team'])];sides=[];bad=None
 try:
  dst=score_game(events.get(gid,[]),expected_game_id=gid,expected_teams=teams,canonical_player_ids={t:deterministic_dst_player_id(t)for t in teams},expected_score={teams[0]:g['home_score'],teams[1]:g['away_score']})
 except ValueError as err:bad='dst:'+str(err).split(':')[0];dst=[]
 for t in teams:
  ps=[]
  for r in members:
   if normalize_team(r['team'])!=t:continue
   s=r['raw_row_json'];past=history[t,r['player_id']][-3:];prior={k:sum(float(p.get(k,0))for p in past)/len(past)if past else None for k in ['targets','carries']}
   ps.append(dict(source_player_id=r['player_id'],position='RB'if r['position']=='FB'else r['position'],prior=prior,stats=s))
  if not ps:bad='missing team stat rows'
  # Full native source must reconcile passing/receiving mechanics before role mapping.
  for passing,receiving in [('passing_yards','receiving_yards'),('passing_tds','receiving_tds'),('completions','receptions')]:
   if abs(sum(float(p['stats'].get(passing,0))for p in ps)-sum(float(p['stats'].get(receiving,0))for p in ps))>.01:bad='passing_receiving_'+passing
  qbs=[p for p in ps if p['position']=='QB'];qbhist=[(p['prior']['carries'] or 0)for p in qbs if p['prior']['carries'] is not None]
  sides.append(dict(team=t,players=ps,qb_prior_carries=max(qbhist)if qbhist else None,dst=next((d['dk_points']for d in dst if d['team']==t),None)))
 if g['week']>=4:
  if bad:rejected[bad]+=1
  elif all(s['qb_prior_carries']is not None for s in sides) and math.isfinite(float(g['total_line'])) and math.isfinite(float(g['spread_line'])):
   library.append(dict(game_id=gid,week=int(g['week']),home_total_line=float(g['total_line']),home_margin_line=float(g['spread_line']),sides=sides,final_score=[float(g['home_score']),float(g['away_score'])]))
  else:rejected['missing pregame matching evidence']+=1
 for r in members:history[normalize_team(r['team']),r['player_id']].append(r['raw_row_json'])
result=dict(contract_id='historical_paired_game_role_templates_v1',source_capture=max(manifest[n]['received_at']for n in ['games.parquet','pbp_2025.parquet']),source_hashes={n:manifest[n]['sha256']for n in ['games.parquet','pbp_2025.parquet']},weekly_stat_source_sha256=hashlib.sha256((root/'historical_stats.json').read_bytes()).hexdigest(),weekly_max_received_at=max(r['created_at']for r in stats),source_status='Revised historical sources captured before target Week6decision, not contemporaneous2025receipts',rejected=dict(rejected),games=library)
(root/'historical_templates.json').write_text(json.dumps(result,allow_nan=False,default=str));print('accepted',len(library),'rejected',dict(rejected),'bytes',(root/'historical_templates.json').stat().st_size)
