"""Offline Monday captain scenarios plus strictly chronological 2026 replay.

Run: .venv/bin/python -m scripts.research_captain_scenarios
No DB reads/writes during replay; immutable captures are separate tools.
"""
from pathlib import Path
from datetime import timezone
from collections import defaultdict,Counter
import argparse,gzip,hashlib,json,html,statistics
import numpy as np
from artifacts.all_games_captain_2026.backtest_lineups import prepare,dt,gamekey,team,SCALE
from backend.app.product_services.captain_scenario_research import research_game,role_keys,MODEL_ID
from backend.app.services.simulation import calculate_dk_points
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/all_games_captain_2026'
OUT=ROOT/'artifacts/captain_scenario_research'
FEATURES=OUT/'feature_inputs_selected_v2'

def utc(v):return dt(v).astimezone(timezone.utc).isoformat()
def read(path):return json.load(gzip.open(path))
def verify(folder):
 m=json.loads((folder/'manifest.json').read_text())
 for name,digest in m['files_sha256'].items():
  if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest:raise ValueError(f'Changed frozen input {folder/name}')

def points(raw,pos):
 x=dict(raw);x['kickoff_return_tds']=float(raw.get('special_teams_tds') or 0);x['punt_return_tds']=0;x['fumbles_lost']=float(raw.get('fumbles_lost_total') or 0)
 p=calculate_dk_points(x,floor_at_zero=False)+6*float(raw.get('fumble_recovery_tds') or 0)
 if pos=='K':p+=sum(float(raw.get(k) or 0)*v for k,v in [('fg_made_0_19',3),('fg_made_20_29',3),('fg_made_30_39',3),('fg_made_40_49',4),('fg_made_50_59',5),('fg_made_60_',5),('pat_made',1)])
 return round(p,2)

def availability():
 """Actual evidence must match canonical ID, exact week/matchup and base score."""
 aliases=defaultdict(set)
 for a in read(BASE/'inputs/aliases.json.gz'):aliases[(a['source_system'],str(a['source_key']))].add(a['player_master_id'])
 evidence=defaultdict(list)
 for s in read(BASE/'inputs/stats.json.gz'):
  ids=aliases[('nflreadpy',str(s['player_id']))]
  if len(ids)==1 and s['position'] in ('QB','RB','WR','TE','K'):
   evidence[(gamekey(s['game_id']),next(iter(ids)))].append((points(s['raw_row_json'],s['position']),utc(s['created_at'])))
 salaries={(s['ingest_run_id'],str(s['source_player_key'])):s for s in read(BASE/'inputs/salaries.json.gz')}
 for o in read(OUT/'inputs/observations.json.gz'):
  if o['resolution_status']!='resolved' or o['actual_points'] is None:continue
  for cand in o.get('evidence_json',{}).get('salary_candidates',[]):
   s=salaries.get((cand.get('ingest_run_id'),str(cand.get('source_player_key'))))
   if not s or not s.get('team') or not s.get('opponent'):continue
   key=(int(o['week']),frozenset([team(s['team']),team(s['opponent'])]))
   evidence[(key,o['player_id'])].append((round(float(o['actual_points'])/(1.5 if o['roster_position']=='CPT' else 1),2),utc(o['recorded_at'])))
 return evidence

def inputs():
 verify(OUT/'inputs');verify(FEATURES)
 games,skipped=prepare();models={m['model_run_id']:m for m in read(BASE/'pregame_inputs/model_runs.json.gz')}
 features={(f['feature_run_id'],gamekey(f['game_id']),f['player_id']):f for f in read(FEATURES/'features.json.gz')}
 old=json.loads((BASE/'report.json').read_text());oldmap={g['game']:g for g in old['games']}
 current=json.loads((OUT/'inputs/monday.json').read_text());schedules=read(OUT/'inputs/schedule.json.gz');ev=availability()
 final=defaultdict(list)
 for s in schedules:
  raw=s['raw_row_json']
  if raw.get('home_score') is not None and raw.get('away_score') is not None:
   final[gamekey(s['game_id'])].append(dict(home=team(raw['home_team']),scores=[float(raw['home_score']),float(raw['away_score'])],available_at=utc(s['created_at'])))
 def market(g,fid):
  fs=[f for (run,key,pid),f in features.items() if run==fid and key==gamekey(g['game'])]
  cutoff=g['cutoff']
  if not fs:raise ValueError('Missing exact saved pregame market features')
  for f in fs:
   if utc(f['created_at'])>cutoff or (f.get('training_cutoff') and utc(f['training_cutoff'])>cutoff):raise ValueError('Feature clock exceeds decision cutoff')
   obs=f['feature_json'].get('market_observed_at')
   if obs and utc(obs)>cutoff:raise ValueError('Market observation after decision cutoff')
   if not obs:g.setdefault('market_timestamp_notes',[]).append('Quote observation unavailable; line retained from immutable pregame feature row')
  bytm=defaultdict(list);homes=set()
  for p in g['players']:
   f=features.get((fid,gamekey(g['game']),p['id']))
   if not f:raise ValueError('Missing saved player feature')
   v=f['feature_json'];im=v.get('team_implied_total')
   if im is None or not np.isfinite(im):raise ValueError('Missing finite implied team total')
   bytm[p['team']].append(float(im))
   if v.get('is_home')==1:homes.add(p['team'])
   p['high_rushing']=float(v.get('carries_mean_3') or 0)>=5 or float(v.get('pregame_expected_carries') or 0)>=5 or float(v.get('pregame_carry_share') or 0)>=.2 or any(t in str(v.get('pregame_role_label') or '').upper() for t in ('RUSH','MOBILE','DUAL'))
  if len(homes)!=1 or len(bytm)!=2:raise ValueError('Ambiguous home/team market')
  g['home']=next(iter(homes));away=next(t for t in bytm if t!=g['home']);g['implied_scores']=[statistics.median(bytm[g['home']]),statistics.median(bytm[away])]
  for p in g['players']:
   if p['position']=='QB':
    own=[q for q in g['players'] if q['team']==p['team'] and q['position']=='QB']
    # Frozen pregame projection rank fallback for historical starter eligibility.
    top=max(own,key=lambda q:(q['projected_mean'],q['id']));p['is_starter']=p['id']==top['id']
  return fs
 enriched=[];blocks=[]
 for g in games:
  g['cutoff']=utc(g['projection_created_at']);g['kickoff']=utc(g['kickoff']);fid=models[g['model_run_id']]['feature_run_id']
  try:market(g,fid)
  except ValueError as e:skipped.append(dict(game=g['game'],phase='market',reason=str(e)));continue
  # Retain full pools for training role ranking, before research eligibility filters.
  keys=role_keys(g['players'],g['home']);errors={};times=[]
  for p in g['players']:
   actual=g['actuals'].get(p['id'])
   if actual is None:continue
   matches=[t for score,t in ev[(gamekey(g['game']),p['id'])] if abs(score-actual['points'])<.011]
   if not matches:continue
   times.append(min(matches));errors[keys[p['id']]]=actual['points']-p['projected_mean']
  finals=[s for s in final[gamekey(g['game'])] if s['home']==g['home']]
  if finals and errors:
   f=min(finals,key=lambda s:s['available_at'])
   blocks.append(dict(game=g['game'],kickoff=g['kickoff'],available_at=max([f['available_at']]+times),score_errors=[f['scores'][i]-g['implied_scores'][i] for i in (0,1)],role_errors=errors))
  # Historical constraint profile mirrors current per-lineup preferences.
  before=g['players'];minimum=current['constraints'].get('minimum_player_salary') or 0
  g['players']=[p for p in before if p['salary']>=minimum and (p['position']!='QB' or p.get('is_starter'))]
  leaders=[]
  if current['constraints'].get('require_team_leader'):
   for tm in sorted({p['team'] for p in before}):
    prior=[p for p in oldmap[g['game']]['players'] if p['team']==tm and p['position'] in ('RB','WR','TE','K') and p.get('prior_ppg') is not None]
    if prior:
     m=max(p['prior_ppg'] for p in prior);leaders.extend(p['id'] for p in prior if p['prior_ppg']==m)
   if not leaders:
    skipped.append(dict(game=g['game'],phase='leader_history',reason='No usable prior-week leader history under current preference'));continue
  g['rules']=dict(leader_ids=leaders,single_te=current['constraints'].get('enforce_single_te',False),no_two_qbs=current['constraints'].get('no_two_qbs',False),avoid_dst_opponents=current['constraints'].get('avoid_dst_opponents',False),qb_correlations=True,locked_ids=[])
  g['constraints_basis']='Current per-lineup preferences replayed; historical QB starter inferred from pregame mean; leaders from saved prior-week history in verified pools. Portfolio exposures not applicable to single-lineup comparisons.'
  enriched.append(g)
 # Monday: preserve saved included pool and explicit exclusions, override only captain QB restriction.
 ps=[];prices={s['player_master_id']:s['salary'] for s in current['source_salaries'] if s['roster_position']=='CPT'}
 for p in current['pool']:
  if not p['included']:continue
  pid=p['player_id'];ps.append(dict(id=pid,name=p['player_name'],team=team(p['team']),position=p['position'],salary=p['salary'],captain_salary=prices.get(pid,p['salary']*1.5),projected_mean=p['projection'],projected_p90=p['p90'],captain_excluded=pid in current['constraints'].get('flex_only_player_ids',[])))
 live=dict(game=current['games'][0]['game_id'],pricing='native',players=sorted(ps,key=lambda p:p['id']),cutoff=utc(current['projection_run']['created_at']),kickoff=utc(current['games'][0]['kickoff_at']),actuals={},projection_run_id=current['projection_run_id'],source_optimizer_run_id=current['optimizer_run_id'])
 # Validate model and forecast clocks, not just saved optimizer creation.
 clocks=[current['model'].get('created_at'),current['model'].get('data_cutoff_at'),current['model'].get('params_json',{}).get('training_cutoff')]
 clocks += [p.get(k) for p in current['projections'] for k in ('created_at','data_cutoff_at')]
 if any(t and utc(t)>=live['kickoff'] for t in clocks):raise ValueError('Monday forecast/model is not pregame')
 if live['cutoff']>=live['kickoff']:raise ValueError('Monday forecast created after kickoff')
 market(live,current['model']['feature_run_id'])
 leaders=current['leader_evidence']['team_leader_preference'].get('required_player_ids',[])
 live['rules']=dict(leader_ids=leaders,single_te=current['constraints'].get('enforce_single_te',False),no_two_qbs=current['constraints'].get('no_two_qbs',False),avoid_dst_opponents=current['constraints'].get('avoid_dst_opponents',False),qb_correlations=True,locked_ids=current['constraints'].get('locked_player_ids',[]))
 return live,enriched,blocks,skipped

def grade(result, actuals):
 for arm in ['baseline','simulation_baseline','selected']:
  l=result[arm];missing=[p['id'] for p in l['players'] if p['id'] not in actuals]
  l['missing_actual_ids']=missing;l['actual_score']=None if missing else sum(actuals[p['id']]['points']*(1.5 if p['slot']=='CPT' else 1) for p in l['players'])
 for c in result['captains']:
  if c['feasible']:
   for key in ['unrestricted_lineup','best_overall_lineup','strongest_scenario_lineup']:
    l=c.get(key)
    if l:l['actual_score']=None if any(p['id'] not in actuals for p in l['players']) else sum(actuals[p['id']]['points']*(1.5 if p['slot']=='CPT' else 1) for p in l['players'])

def summary(results):
 out={}
 for pricing in ['native','classic_hypothetical','monday_native_subset']:
  from zoneinfo import ZoneInfo
  rows=[g for g in results if g['pricing']==pricing] if pricing!='monday_native_subset' else [g for g in results if g['pricing']=='native' and dt(g['kickoff']).astimezone(ZoneInfo('America/New_York')).weekday()==0];scored=[g for g in rows if all(g[a]['actual_score'] is not None for a in ['baseline','simulation_baseline','selected'])]
  ds=[g['selected']['actual_score']-g['baseline']['actual_score'] for g in scored]
  avg=lambda vs:statistics.mean(vs) if vs else None
  out[pricing]=dict(evaluated_games=len(rows),scored_games=len(scored),unknown_actual_games=[g['game'] for g in rows if g not in scored],baseline_average=avg(g['baseline']['actual_score'] for g in scored),scenario_average=avg(g['selected']['actual_score'] for g in scored),average_delta=avg(ds),wins=sum(d>1e-7 for d in ds),losses=sum(d< -1e-7 for d in ds),ties=sum(abs(d)<=1e-7 for d in ds),changed_captains=sum(g['baseline']['captain_id']!=g['selected']['captain_id'] for g in scored),simulation_unrestricted_average=avg(g['simulation_baseline']['actual_score'] for g in scored),scenario_vs_simulation_unrestricted_delta=avg(g['selected']['actual_score']-g['simulation_baseline']['actual_score'] for g in scored),scenario_vs_simulation_unrestricted_wlt=[sum(g['selected']['actual_score']-g['simulation_baseline']['actual_score']>1e-7 for g in scored),sum(g['selected']['actual_score']-g['simulation_baseline']['actual_score']< -1e-7 for g in scored),sum(abs(g['selected']['actual_score']-g['simulation_baseline']['actual_score'])<=1e-7 for g in scored)])
 return out

def render(r):
 def pct(v):return 'Unknown' if v is None else f'{100*v:.1f}%'
 def num(v):return 'Unknown' if v is None else f'{v:.2f}'
 def table(headers,rows):return '<div class="scroll"><table><tr>'+''.join('<th>'+html.escape(str(v))+'</th>' for v in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</table></div>'
 live=r['monday'];body='<h1>Monday-night captain scenario research</h1><p>BUF @ LAR, October 12, 2026. Pregame research only. QBs eligible; top-four P90 captain candidates. Six unique players, $50,000 salary cap, exact 4–2 split, captain salary and actual points ×1.5.</p><p><b>Experimental empirical game-block model; probabilities are not calibrated forecasts or paid rates.</b> High scoring = 48+ combined points. Close/non-blowout = margin below 14; blowout = 14+. Winner direction distinguishes blowouts.</p>'
 body+=table(['Captain','Position','Base P90','Salary'],[(p['name'],p['position'],num(p['projected_p90']),p['salary']) for p in r['monday_pool'] if p['id'] in live['shortlist']])
 body+='<h2>Scenario probabilities</h2>'+table(['Scenario','Model probability','Evaluation draws','Supporting historical blocks'],[(s['scenario'],pct(s['probability']),s['samples'],live['captains'][0]['best_overall_lineup']['evaluation']['scenarios'][i]['historical_block_support']) for i,s in enumerate(live['scenario_probabilities'])])
 body+='<h2>Captain results on independent evaluation draws</h2>'+table(['Captain','Strongest scenario, chosen on selection sample','Scenario probability','Conditional high-finish rate','Overall high-finish rate'],[(c['name'],c['strongest_scenario']['scenario'] if c.get('strongest_scenario') else 'Insufficient samples',pct(c['strongest_scenario']['probability']) if c.get('strongest_scenario') else '—',pct(c['strongest_scenario']['high_finish_rate']) if c.get('strongest_scenario') else '—',pct(c['best_overall_lineup']['evaluation']['high_finish_rate'])) for c in live['captains'] if c['feasible']])
 body+='<p>Strongest-scenario results and overall results can refer to different frozen FLEX lineups; each is retained below and in JSON. High finish means meeting the 95th-percentile score of a fixed sampled legal comparison pool, not the contest field.</p>'
 body+='<h2>Unrestricted baseline versus scenario selection</h2>'+table(['Method','Captain','Evaluation mean','High-finish rate','Salary','Actual'],[(a,next(p['name'] for p in live[a]['players'] if p['slot']=='CPT'),num(live[a]['evaluation']['mean']),pct(live[a]['evaluation']['high_finish_rate']),live[a]['salary'],'Not available before game') for a in ['baseline','simulation_baseline','selected']])
 for label,l in [('Unrestricted FLEX baseline',live['baseline']),('Simulation-ranked unrestricted lineup',live['simulation_baseline']),('Scenario-selected lineup',live['selected'])]+[(c['name']+' — best overall',c['best_overall_lineup']) for c in live['captains'] if c['feasible']]+[(c['name']+' — strongest scenario',c['strongest_scenario_lineup']) for c in live['captains'] if c.get('strongest_scenario_lineup')]:
  body+='<h3>'+html.escape(label)+'</h3>'+table(['Slot','Player','Team','Salary charged','Base mean','Base P90'],[(p['slot'],p['name'],p['team'],p['captain_salary'] if p['slot']=='CPT' else p['salary'],num(p['projected_mean']),num(p['projected_p90'])) for p in l['players']])
 body+='<h2>Chronological actual-results backtest</h2>'+table(['Pricing','Evaluated','Scored','Unrestricted average','Scenario average','Difference','W/L/T'],[(k,v['evaluated_games'],v['scored_games'],num(v['baseline_average']),num(v['scenario_average']),num(v['average_delta']),f"{v['wins']}/{v['losses']}/{v['ties']}") for k,v in r['backtest_summary'].items()])
 body+='<h3>Separating simulation ranking from FLEX construction</h3>'+table(['Pricing','Simulation-ranked unrestricted average','Scenario minus simulation-unrestricted','W/L/T'],[(k,num(v['simulation_unrestricted_average']),num(v['scenario_vs_simulation_unrestricted_delta']),'/'.join(map(str,v['scenario_vs_simulation_unrestricted_wlt']))) for k,v in r['backtest_summary'].items()])
 body+=table(['Game','Training blocks available then','Baseline captain / actual','Scenario captain / actual'],[(g['game'],len(g['training_games']),next(p['name'] for p in g['baseline']['players'] if p['slot']=='CPT')+' / '+num(g['baseline']['actual_score']),next(p['name'] for p in g['selected']['players'] if p['slot']=='CPT')+' / '+num(g['selected']['actual_score'])) for g in r['backtests']])
 body+='<h2>Audit and limitations</h2><ul>'+''.join('<li>'+html.escape(v)+'</li>' for v in r['limitations'])+'</ul><p>Monday training blocks: '+str(len(live['training_games']))+'; comparison pool: '+str(live['benchmark_pool_count'])+'; draws per stream: '+str(live['draws_per_stream'])+'.</p>'
 body+='<h2>Skipped games</h2>'+table(['Game','Phase','Reason'],[(g.get('game'),g.get('phase','inputs'),g['reason']) for g in r['skipped']])
 return '<!doctype html><meta charset="utf-8"><title>Captain scenario research</title><style>body{font:15px/1.5 system-ui;max-width:1400px;margin:32px auto;padding:0 24px;color:#173047}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:8px;border-bottom:1px solid #ddd;text-align:left}th{background:#eef3f8}.scroll{overflow-x:auto}h2{margin-top:32px}</style>'+body

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--draws',type=int,default=2000);ap.add_argument('--seed',type=int,default=1212);ap.add_argument('--reference-limit',type=int,default=1000);args=ap.parse_args()
 if args.draws<100 or args.reference_limit<20:raise ValueError('Insufficient requested simulation or reference sample')
 live,games,blocks,skipped=inputs();results=[]
 for i,g in enumerate(sorted(games,key=lambda g:g['cutoff'])):
  train=[b for b in blocks if b['available_at']<g['cutoff'] and b['kickoff']<g['cutoff'] and b['game']!=g['game']]
  if len(train)<6:skipped.append(dict(game=g['game'],phase='chronological_training',reason=f'Only {len(train)} historical imported game blocks before cutoff; minimum six'));continue
  try:r=research_game(g,train,draws=args.draws,seed=args.seed+10*(i+1),reference_limit=args.reference_limit)
  except ValueError as e:skipped.append(dict(game=g['game'],phase='lineup',reason=str(e)));continue
  r['market_timestamp_notes']=g.get('market_timestamp_notes',[]);r['constraints_basis']=g['constraints_basis'];grade(r,g['actuals']);results.append(r);print(g['game'],len(train),r['baseline']['actual_score'],r['selected']['actual_score'],flush=True)
 train=[b for b in blocks if b['available_at']<live['cutoff'] and b['kickoff']<live['cutoff'] and b['game']!=live['game']]
 monday=research_game(live,train,draws=args.draws,seed=args.seed,reference_limit=args.reference_limit)
 monday['source_optimizer_run_id']=live['source_optimizer_run_id'];monday['projection_run_id']=live['projection_run_id']
 sources=[ROOT/'backend/app/product_services/captain_scenario_research.py',Path(__file__),BASE/'report.json',BASE/'lineup_backtest_score_supplement.json']
 report=dict(monday=monday,monday_pool=live['players'],backtests=results,backtest_summary=summary(results),skipped=skipped,parameters=vars(args),model_id=MODEL_ID,snapshot_manifests={str(p.relative_to(ROOT)):json.loads((p/'manifest.json').read_text()) for p in [OUT/'inputs',FEATURES,BASE/'inputs',BASE/'pregame_inputs']},code_and_input_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},limitations=[
 'Research only: production optimizer, user preferences, source projections and active run were not modified.',
 'Game-block residual bootstrap maps historical pregame team/position/mean ranks to current roles. It preserves empirical co-movement but does not conserve individual passing/receiving yards or generate coherent play-by-play events.',
 'Scenario probabilities are uncalibrated model estimates. Team scores use market-implied totals plus paired historical score residuals. Scores are rounded, floored at zero, and do not enforce football scoring increments.',
 'Development, selection and evaluation streams use distinct seeds; fixed lineups are never optimized on final evaluation outcomes or actual scores. All streams resample the same limited historical evidence, so this does not establish out-of-sample model validity.',
 'High scoring is 48+ combined points; close/non-blowout is margin below 14. Thresholds were fixed before this run and are research assumptions.',
 'High finish means score >= 95th-percentile score of a fixed sampled legal reference pool, including ties. This is not top 5% of all possible lineups, a contest field, or a payout estimate.',
 'Intervals measure Monte Carlo precision only. Repeated draws do not create new independent historical games or measure model uncertainty.',
 'Negative fantasy outcomes are retained; only team football scores are floored at zero. This residual model can produce imperfect football outcomes and is not an event simulator.',
 'Missing historical role residuals use zero error, retaining projected mean. Per-player missing-block counts are reported; no unknown actual is assumed zero.',
 'Historical training requires matching imported score evidence and final team-score records before the target forecast cutoff. Early games are skipped rather than trained on late-arriving results.',
 'Historical lineups retain current per-lineup preferences: minimum salary, season leader, QB correlations, DST avoidance and optional TE/QB limits, plus exact 4–2. Historical starters use pregame mean rank and leaders use prior-week history from verified-score pools; this is not an exact reproduction of every historical production run.',
 'Live Monday uses the saved included player pool, existing season-leader and QB-correlation constraints, and explicit FLEX-only preferences. The WR/RB-only captain preference is overridden in research so QBs qualify. Single-lineup comparisons do not enforce multi-entry exposure caps.',
 'Actual scores are attached only after historical lineup selection. Missing scores make a comparison unscorable; native and hypothetical Classic salaries stay separate.',
 'P90 controls captain shortlisting and the hybrid baseline. Simulated player uncertainty uses additive historical role forecast errors, not a rescaled P90 gap or a claim to preserve current marginal quantiles.',
 'Historical quote observation clocks are retained when available; otherwise market lines come from immutable pregame feature rows and quote publication freshness remains unknown.',
 'Scenario probability calibration could not be established from this snapshot; the report evaluates actual lineup points and leaves all probabilities experimental.',
 'No calibrated-probability promotion or automatic lineup recommendation. Historical forecast models vary across games; small samples require future validation.'
 ])
 (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');(OUT/'report.html').write_text(render(report));print(json.dumps(report['backtest_summary'],indent=2));print('Monday captains',[(c.get('name'),c.get('strongest_scenario')) for c in monday['captains']])
if __name__=='__main__':main()
