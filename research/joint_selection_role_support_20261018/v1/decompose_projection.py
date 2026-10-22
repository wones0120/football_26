"""Descriptive component reconciliation; total FP forecasts cannot identify causal components."""
from collections import defaultdict,Counter
from pathlib import Path
import json,math,statistics
from backend.app.product_services.full_game_breadth import strict_dk
P=Path(__file__).resolve().parent;features={(f['projection_run_id'],f['player_id'],f['game_id']):f for f in json.load(open('research/top_decile_lineup_model_20261018/v1/historical_features_v2.json'))}
forecast=json.load(open('research/season_projection_accuracy_20261018/v1/player_games.json'));raw=json.load(open(P/'actual_component_rows.json'));groups=defaultdict(list)
for r in raw:groups[r['game_id'],r['player_master_id']].append(r)
rows=[];exceptions=Counter();conflicts=[]
for r in forecast:
 if r['week']not in[2,3,5]or r['position']not in['QB','RB','WR','TE']or r['mean']<5:continue
 key=r['game_id'],r['player_id'];actuals=groups[key]
 if len(actuals)!=1:exceptions['actual_component_missing_or_duplicate']+=1;continue
 s=actuals[0]
 try:dk=strict_dk(s)
 except ValueError:exceptions['actual_component_unknown']+=1;continue
 f=features.get((r['projection_run_id'],*reversed(key)))
 # Feature key is projection/player/game, never a display-name join.
 if f is None:f=features.get((r['projection_run_id'],r['player_id'],r['game_id']))
 error=r['mean']-r['actual'];mismatch=abs(dk-r['actual'])>.025
 td=4*s['passing_tds']+6*(s['rushing_tds']+s['receiving_tds']+s['special_teams_tds']+s['fumble_recovery_tds'])
 channel='carries'if r['position']in['QB','RB']else'targets';proxy=(f or{}).get(channel+'_mean_3');observed=s[channel]
 row={**r,'native_stat_player_id':s['player_id'],'component_reconstructed_dk':dk,'component_matches_observed_dk':not mismatch,'error':error,'workload_channel':channel,'recorded_workload_proxy':proxy,'actual_workload':observed,'workload_proxy_error':proxy-observed if type(proxy)in(int,float)else None,
  'actual_td_fp':td,'actual_non_td_fp':dk-td,'actual_targets':s['targets'],'actual_carries':s['carries'],'actual_receptions':s['receptions'],'actual_receiving_yards':s['receiving_yards'],'actual_rushing_yards':s['rushing_yards'],'actual_passing_yards':s['passing_yards'],'feature_role':(f or{}).get('pregame_role_label'),'feature_injury_status':(f or{}).get('pregame_injury_status')}
 rows.append(row)
 if mismatch:conflicts.append(row)
def metrics(rs):
 return {'n':len(rs),'games':len({r['game_id']for r in rs}),'mae':statistics.mean(abs(r['error'])for r in rs)if rs else None,'bias':statistics.mean(r['error']for r in rs)if rs else None,'workload_proxy_mae':statistics.mean(abs(r['workload_proxy_error'])for r in rs if r['workload_proxy_error']is not None)if any(r['workload_proxy_error']is not None for r in rs)else None}
def correlation(rs,x,y):
 pairs=[(r[x],r[y])for r in rs if type(r.get(x))in(int,float)and type(r.get(y))in(int,float)]
 if len(pairs)<3:return None
 xs,ys=zip(*pairs);mx=statistics.mean(xs);my=statistics.mean(ys);den=math.sqrt(sum((x-mx)**2 for x in xs)*sum((y-my)**2 for y in ys))
 return sum((x-mx)*(y-my)for x,y in pairs)/den if den else None
trusted=[r for r in rows if r['component_matches_observed_dk']]
out={'parent_diagnosis_sha256':__import__('hashlib').sha256((P/'projection_component_diagnosis.json').read_bytes()).hexdigest(),'cohort':'Unique canonical player-games with stored-pregame mean>=5, QB/RB/WR/TE; source component weeks2,3,5 only','scoring_contract':'draftkings_nfl_typed_v2_lost_fumble_minus_one','actual_component_rows':len(raw),'forecast_covered':len(rows),'component_matches':len(trusted),'exceptions':dict(exceptions),'exact_expected_fp_component_decomposition':'Not identifiable: original forecasts save total FP and workload proxies, not expected TD/efficiency/yardage components','all_covered':metrics(rows),'reconciled_only':metrics(trusted),'by_position':{p:{'metrics':metrics([r for r in trusted if r['position']==p]),'workload_error_fp_error_correlation':correlation([r for r in trusted if r['position']==p],'workload_proxy_error','error'),'observed_td_fp_error_correlation':correlation([r for r in trusted if r['position']==p],'actual_td_fp','error')}for p in ['QB','RB','WR','TE']},'component_conflicts':conflicts,'largest_reconciled_errors':sorted(trusted,key=lambda r:abs(r['error']),reverse=True)[:15], 'rows':rows,'interpretation':'Associations and observed components are descriptive, not causal error attribution; allocated workload proxies are not calibrated forecasts; no feature/default changes'}
with (P/'projection_component_diagnosis_v2.json').open('x')as f:json.dump(out,f,indent=2)
print('covered',len(rows),'reconciled',len(trusted),'exceptions',dict(exceptions));print('positions',out['by_position']);print('conflicts',[(r['name'],r['week'],r['actual'],r['component_reconstructed_dk'])for r in conflicts[:5]])
