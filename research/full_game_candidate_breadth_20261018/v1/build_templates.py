"""Historical physical paired games; native active roles and verified event zeros."""
from collections import Counter,defaultdict
import hashlib,json,math,pathlib
import pandas as pd
from Database.dst import normalize_team,deterministic_dst_player_id
from backend.app.product_services.dst_scoring_reconciliation import REQUIRED,score_game
P=pathlib.Path(__file__).resolve().parent;S=pathlib.Path('research/neural_workload_benchmark_20261013/expanded_v3/sources');M=json.loads((S/'manifest.json').read_text())
names=['games.parquet','pbp_2025.parquet','players.parquet','snaps_2025.parquet']
for n in names:
 if hashlib.sha256((S/n).read_bytes()).hexdigest()!=M[n]['sha256']:raise ValueError('Changed frozen source '+n)
stats=json.loads(pathlib.Path('research/joint_portfolio_selection_20261018/v1/historical_stats.json').read_text());group=defaultdict(list)
for r in stats:group[r['game_id']].append(r)
players=pd.read_parquet(S/'players.parquet',columns=['gsis_id','pfr_id']);cross=defaultdict(set)
for r in players.to_dict('records'):
 if pd.notna(r['pfr_id'])and pd.notna(r['gsis_id']):cross[r['pfr_id']].add(r['gsis_id'])
snaps=pd.read_parquet(S/'snaps_2025.parquet');snapgroups={gid:g.to_dict('records')for gid,g in snaps.groupby('game_id')}
actions=['passer_player_id','receiver_player_id','rusher_player_id','td_player_id','fumbled_1_player_id','fumbled_2_player_id','fumble_recovery_1_player_id','fumble_recovery_2_player_id','lateral_receiver_player_id','lateral_rusher_player_id','kickoff_returner_player_id','punt_returner_player_id']
cols=sorted(REQUIRED|set(actions)|{'fixed_drive','pass_attempt','rush_attempt'})
pbp=pd.read_parquet(S/'pbp_2025.parquet',columns=cols);events={gid:g.to_dict('records')for gid,g in pbp.groupby('game_id')}
games=pd.read_parquet(S/'games.parquet');schedule=games[games.season==2026][['game_id','home_team','away_team','gameday','gametime']].to_dict('records');games=games[(games.season==2025)&(games.game_type=='REG')].sort_values(['gameday','gametime','game_id'])
team_past=defaultdict(list);library=[];reject=Counter();zero_count=0;history={}
scorekeys=['passing_yards','passing_tds','passing_interceptions','rushing_yards','rushing_tds','receptions','receiving_yards','receiving_tds','passing_2pt_conversions','rushing_2pt_conversions','receiving_2pt_conversions','special_teams_tds','fumble_recovery_tds','rushing_fumbles_lost','receiving_fumbles_lost','sack_fumbles_lost','targets','carries','attempts','completions','pat_made','fg_made_0_19','fg_made_20_29','fg_made_30_39','fg_made_40_49','fg_made_50_59','fg_made_60_']
for g in games.to_dict('records'):
 gid=g['game_id'];teams=[normalize_team(g['home_team']),normalize_team(g['away_team'])];native=group[gid];ev=events.get(gid,[]);bad=None
 try:dst=score_game(ev,expected_game_id=gid,expected_teams=teams,canonical_player_ids={t:deterministic_dst_player_id(t)for t in teams},expected_score={teams[0]:g['home_score'],teams[1]:g['away_score']})
 except ValueError as err:bad='dst:'+str(err).split(':')[0];dst=[]
 action_ids={str(r[k])for r in ev for k in actions if r.get(k)is not None and pd.notna(r[k])}
 sides=[]
 for team in teams:
  ps={r['player_id']:dict(source_player_id=r['player_id'],position='RB'if r['position']=='FB'else r['position'],stats=r['raw_row_json'],zero_basis=None)for r in native if normalize_team(r['team'])==team}
  active=set()
  for r in snapgroups.get(gid,[]):
   if normalize_team(r['team'])!=team or r['position']not in['QB','RB','FB','WR','TE']or not r['offense_snaps']>0:continue
   ids=cross.get(r['pfr_player_id'],set())
   if len(ids)!=1:bad='ambiguous_active_native_identity';continue
   pid=next(iter(ids));active.add(pid)
   if pid not in ps:
    if pid in action_ids:bad='active_event_actor_missing_weekly_stats';continue
    ps[pid]=dict(source_player_id=pid,position='RB'if r['position']=='FB'else r['position'],stats={k:0 for k in scorekeys},zero_basis='native_PFR_GSIS_positive_offense_snaps_and_no_relevant_complete_PBP_event');zero_count+=1
  # Native actual activity is independent evidence when the snap provider lacks a row.
  for pid,p in ps.items():
   if any(float(p['stats'].get(k)or 0)!=0 for k in ['attempts','carries','targets','receptions']):active.add(pid)
  previous=team_past[team][-3:]
  historical={pid:p for old in previous for pid,p in history[old,team].items()}
  def prior(pid,key):
   return sum(float(history[old,team].get(pid,{}).get('stats',{}).get(key)or 0)for old in previous)/len(previous)if previous else None
  for p in ps.values():p['prior']={k:prior(p['source_player_id'],k)for k in ['targets','carries','attempts']}
  # Do not turn a leading role's absence into a healthy player's zero or promotion.
  for pos in ['QB','RB','WR','TE']:
   members=[pid for pid,p in historical.items()if p['position']==pos]
   if not members:continue
   key='attempts'if pos=='QB'else 'carries'if pos=='RB'else'targets'
   lead=max(members,key=lambda pid:(prior(pid,key)or 0,pid))
   if (prior(lead,key)or 0)>0 and lead not in active:bad='leading_role_inactive_or_unknown'
  ps={pid:p for pid,p in ps.items()if pid in active or p['position']=='K'}
  for a,b in [('passing_yards','receiving_yards'),('passing_tds','receiving_tds'),('completions','receptions')]:
   if abs(sum(float(p['stats'].get(a)or 0)for p in ps.values())-sum(float(p['stats'].get(b)or 0)for p in ps.values()))>.01:bad='passing_receiving_'+a
  qb=max((p for p in ps.values()if p['position']=='QB'),key=lambda p:(p['prior']['attempts']or 0,p['source_player_id']),default=None)
  plays=[r for r in ev if normalize_team(r.get('posteam'))==team and(r.get('pass_attempt')==1 or r.get('rush_attempt')==1)]
  drives={r.get('fixed_drive')for r in plays if pd.notna(r.get('fixed_drive'))}
  sides.append(dict(team=team,players=list(ps.values()),qb_prior_carries=qb['prior']['carries']if qb else None,dst=next((d['dk_points']for d in dst if d['team']==team),None),budget=dict(plays=len(plays),drives=len(drives),targets=sum(float(p['stats'].get('targets')or 0)for p in ps.values()),carries=sum(float(p['stats'].get('carries')or 0)for p in ps.values()),points=float(g['home_score']if team==teams[0]else g['away_score']))))
  history[gid,team]={r['player_id']:dict(position='RB'if r['position']=='FB'else r['position'],stats=r['raw_row_json'])for r in native if normalize_team(r['team'])==team}
 if g['week']>=4:
  if bad:reject[bad]+=1
  elif all(s['qb_prior_carries']is not None and s['budget']['drives']>0 for s in sides)and all(math.isfinite(float(g[k]))for k in['total_line','spread_line']):
   library.append(dict(game_id=gid,week=int(g['week']),total_line=float(g['total_line']),home_margin_line=float(g['spread_line']),sides=sides))
  else:reject['missing_pregame_matching_or_pace_evidence']+=1
 for team in teams:team_past[team].append(gid)
result=dict(contract_id='physical_paired_game_role_templates_v2',source_capture=max(M[n]['received_at']for n in names),source_hashes={n:M[n]['sha256']for n in names},weekly_stat_source_sha256=hashlib.sha256(pathlib.Path('research/joint_portfolio_selection_20261018/v1/historical_stats.json').read_bytes()).hexdigest(),weekly_max_received_at=max(r['created_at']for r in stats),source_status='revised historical sources received before frozenWeek6decision; not contemporaneous2025receipts',rejected=dict(reject),verified_active_zero_rows=zero_count,target_schedule=schedule,games=library)
(P/'historical_templates_v2.json').write_text(json.dumps(result,allow_nan=False,default=str));print('accepted',len(library),'rejected',dict(reject),'verified active zeros',zero_count)
