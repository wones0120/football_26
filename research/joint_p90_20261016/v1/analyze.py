"""Frozen-input retrospective joint ceiling audit; no database writes."""
from pathlib import Path
from collections import defaultdict,Counter
from datetime import datetime,UTC
from zoneinfo import ZoneInfo
from itertools import combinations
import hashlib,json,math,random
P=Path(__file__).resolve().parent
THRESHOLDS=(1.,.9,.8)
ORDER={'QB':0,'RB':1,'WR':2,'TE':3}
PAIRS={'WR-WR','WR-TE','RB-RB','RB-WR','QB-WR','QB-TE'}
def clock(value):
 d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
 # Conservative legacy timestamp interpretation; never shift a stored aware value.
 return d.replace(tzinfo=ZoneInfo('America/New_York')) if d.tzinfo is None else d

def eligible_forecast(r,kickoff):
 return bool(kickoff and r.get('run_status')=='completed' and all(r.get(k) for k in ['created_at','run_created','data_cutoff_at']) and max(clock(r['created_at']),clock(r['run_created']))<kickoff and clock(r['data_cutoff_at'])<=clock(r['created_at']))

def dk_score(s):
 required=['passing_yards','passing_tds','passing_interceptions','rushing_yards','rushing_tds','receptions','receiving_yards','receiving_tds','passing_2pt_conversions','rushing_2pt_conversions','receiving_2pt_conversions','special_teams_tds','fumble_recovery_tds','fumbles_lost_total']
 if any(k not in s or s[k] is None for k in required):return None
 n=lambda k:float(s[k]);py,ry,cy=(n(k) for k in ['passing_yards','rushing_yards','receiving_yards'])
 return .04*py+4*n('passing_tds')-n('passing_interceptions')+.1*(ry+cy)+6*(n('rushing_tds')+n('receiving_tds')+n('special_teams_tds')+n('fumble_recovery_tds'))+n('receptions')+2*sum(n(k) for k in ['passing_2pt_conversions','rushing_2pt_conversions','receiving_2pt_conversions'])-n('fumbles_lost_total')+3*sum([py>=300,ry>=100,cy>=100])

def relation(a,b):
 if a['id']==b['id']:raise ValueError('Same canonical player cannot form a pair')
 return 'same_team' if a['game']==b['game'] and a['team']==b['team'] else 'opposing_same_game' if a['game']==b['game'] else 'different_game'

def pair_type(a,b):return '-'.join(sorted([a['pos'],b['pos']],key=ORDER.get))
def hit(r,t):return r['actual']>=t*r['p90']
def load(name):return json.loads((P/(name+'.json')).read_text())
def summarize(pairs,t):
 if not pairs:return None
 n=len(pairs);ma=sum(hit(a,t) for a,b in pairs)/n;mb=sum(hit(b,t) for a,b in pairs)/n;j=sum(hit(a,t) and hit(b,t) for a,b in pairs)/n
 by=defaultdict(lambda:[0,0]);games=set()
 for a,b in pairs:
  by[a['week']][0]+=int(hit(a,t) and hit(b,t));by[a['week']][1]+=1;games.update([a['game'],b['game']])
 weeks=sorted(by);rng=random.Random(20261016);bs=[]
 if len(weeks)>=2:
  for _ in range(1000):
   sample=[by[rng.choice(weeks)] for _ in weeks];bs.append(sum(x[0] for x in sample)/sum(x[1] for x in sample))
  bs.sort()
 return dict(pairs=n,games=len(games),weeks=len(weeks),joint=j,marginal_a=ma,marginal_b=mb,empirical_independent_product=ma*mb,lift=j/(ma*mb) if ma*mb else None,week_bootstrap_95=[bs[25],bs[974]] if bs else None,mean_salary=sum(a['salary']+b['salary'] for a,b in pairs)/n,mean_actual_points=sum(a['actual']+b['actual'] for a,b in pairs)/n,mean_expected_points=sum(a['mean']+b['mean'] for a,b in pairs)/n,weekly_counts={w:v for w,v in by.items()})

def paired_difference(a,b):
 if not a or not b:return None
 weeks=sorted(set(a['weekly_counts'])|set(b['weekly_counts']));rng=random.Random(20261016);delta=[]
 for _ in range(1000):
  picked=[rng.choice(weeks) for _ in weeks]
  def rate(s):
   v=[s['weekly_counts'].get(w,[0,0]) for w in picked];n=sum(x[1] for x in v);return sum(x[0] for x in v)/n if n else 0
  delta.append(rate(a)-rate(b))
 delta.sort();return {'difference':a['joint']-b['joint'],'week_cluster_bootstrap_95':[delta[25],delta[974]],'clusters':len(weeks)}

def main():
 exclusions=Counter();schedules={};schedule_meta={}
 for r in load('schedule'):
  s=r['raw_row_json']
  try:k=datetime.fromisoformat(s['gameday']+'T'+s['gametime']).replace(tzinfo=ZoneInfo('America/New_York'))
  except (KeyError,TypeError,ValueError):exclusions['schedule_clock_missing']+=1;continue
  schedules[r['game_id']]=k;schedule_meta[r['game_id']]=r
 aliases=defaultdict(set)
 for r in load('aliases'):aliases[r['source_key']].add(r['player_master_id'])
 stats={}
 for r in load('stats'):
  ids=aliases[r['player_id']]
  if len(ids)!=1:exclusions['outcome_alias_ambiguous_or_missing']+=1;continue
  key=(next(iter(ids)),r['game_id'])
  if key in stats:exclusions['outcome_multiple_native_ids']+=1;stats[key]=None
  else:stats[key]=r
 part={(r['player_master_id'],r['game_id']):r for r in load('participation')}
 salary=defaultdict(list)
 for r in load('salaries'):salary[(r['player_master_id'],r['week'])].append(r)
 features={(r['projection_run_id'],r['player_id'],r['game_id']):r for r in load('features')}
 forecasts=load('forecasts');latest={}
 for r in forecasts:
  kickoff=schedules.get(r['game_id']);f=features.get((r['projection_run_id'],r['player_id'],r['game_id']))
  if not f or not kickoff or any(not f.get(k) or clock(f[k])>=kickoff for k in ['model_created','feature_created','feature_run_created']) or (f.get('training_cutoff') and clock(f['training_cutoff'])>=kickoff) or (f.get('pregame_context_observed_at') and clock(f['pregame_context_observed_at'])>clock(r['created_at'])):
   exclusions['forecast_model_or_feature_chronology_missing_or_postkick']+=1;continue
  if not eligible_forecast(r,kickoff):exclusions['forecast_postkick_or_missing_chronology']+=1;continue
  key=(r['player_id'],r['game_id'])
  if key not in latest or (clock(r['created_at']),r['projection_run_id'])>(clock(latest[key]['created_at']),latest[key]['projection_run_id']):latest[key]=r
 rows=[]
 for key,r in latest.items():
  st=stats.get(key);pa=part.get(key);sal=[s for s in salary[(key[0],r['week'])] if clock(s['created_at'])<=clock(r['created_at']) and s['position'] in ORDER]
  if not sal:exclusions['player_no_pregame_offensive_salary']+=1;continue
  sa=max(sal,key=lambda x:clock(x['created_at']));pos=sa['position']
  if not r.get('p90') or r['p90']<5:exclusions['player_p90_below_5']+=1;continue
  if st is None:
   if pa and pa['participation_status']=='did_not_play':actual=0.;actualsrc='confirmed_did_not_play'
   else:exclusions['player_actual_unknown']+=1;continue
  else:
   if st['team'].replace('LA','LAR')!=sa['team'].replace('LA','LAR'):exclusions['player_outcome_team_conflict']+=1;continue
   actual=dk_score(st['raw_row_json']);actualsrc=st['ingest_run_id']
   if actual is None:exclusions['player_incomplete_scoring_components']+=1;continue
  f=features[(r['projection_run_id'],r['player_id'],r['game_id'])]
  feature_strata={k:f.get(k) for k in ['targets_mean_3','carries_mean_3','pregame_target_share','pregame_carry_share','target_share_mean_3','carry_share_mean_3','pregame_injury_status','pregame_role_label','pregame_availability_probability','team_implied_total','game_total_line','team_spread_line']}
  rows.append(dict(**feature_strata,id=key[0],game=key[1],week=r['week'],team=sa['team'],pos=pos,mean=r['mean'],p90=r['p90'],salary=sa['salary'],actual=actual,forecast_run=r['projection_run_id'],forecast_created=r['created_at'],kickoff=schedules[key[1]].isoformat(),actual_source=actualsrc,participation=pa['participation_status'] if pa else 'unknown',availability='source_version_incomplete; original_feature_status_retained',opportunity='original_model_input_proxy'))
 grouped=defaultdict(list);byweek=defaultdict(list)
 for r in rows:byweek[r['week']].append(r)
 for week,rr in byweek.items():
  for a,b in combinations(sorted(rr,key=lambda r:(ORDER[r['pos']],r['id'])),2):
   if a['pos']==b['pos'] and (a['mean'],a['salary'],a['id'])>(b['mean'],b['salary'],b['id']):a,b=b,a
   typ=pair_type(a,b)
   if max(clock(a['forecast_created']),clock(b['forecast_created']))>=min(clock(a['kickoff']),clock(b['kickoff'])):
    exclusions['pair_not_jointly_available_before_first_kickoff']+=1;continue
   if typ in PAIRS:grouped[(relation(a,b),typ)].append((a,b))
 # Outcome-blind matching on week, exact positional order, $1000 salary and 5-point mean bins.
 def matchkey(a,b):return (a['week'],a['pos'],b['pos'],int(a['mean']//5),int(b['mean']//5),a['salary']//1000,b['salary']//1000)
 controls=defaultdict(list)
 for (rel,typ),pairs in grouped.items():
  if rel=='different_game':
   for a,b in pairs:controls[matchkey(a,b)].append((a,b))
 matched={};matchcoverage={}
 for typ in sorted(PAIRS):
  treatment=[];control=[]
  for a,b in grouped.get(('same_team',typ),[]):
   choices=controls.get(matchkey(a,b),[])
   if choices:
    # One deterministic comparator per treatment; reuse recorded, no false IID claim.
    choices=sorted(choices,key=lambda p:hashlib.sha256((a['id']+b['id']+p[0]['id']+p[1]['id']).encode()).hexdigest());treatment.append((a,b));control.append(choices[0])
  matched[typ]={'same_team':{str(t):summarize(treatment,t) for t in THRESHOLDS},'different_game':{str(t):summarize(control,t) for t in THRESHOLDS}}
  matchcoverage[typ]=dict(same_team_pairs=len(grouped.get(('same_team',typ),[])),matched=len(treatment),unique_control_pairs=len({(a['id'],b['id'],a['week']) for a,b in control}))
 def richkey(a,b):
  def one(r):
   opportunity=r.get('carries_mean_3') if r['pos']=='RB' else r.get('targets_mean_3') if r['pos']!='QB' else None
   return (str(r.get('pregame_injury_status') or 'UNKNOWN'),int(float(opportunity)//(5 if r['pos']=='RB' else 2)) if opportunity is not None else 'UNKNOWN')
  return matchkey(a,b)+(one(a),one(b))
 richcontrols=defaultdict(list)
 for (rel,typ),pairs in grouped.items():
  if rel=='different_game':
   for a,b in pairs:richcontrols[richkey(a,b)].append((a,b))
 richmatched={}
 for typ in sorted(PAIRS):
  treatment=[];control=[]
  for a,b in grouped.get(('same_team',typ),[]):
   choices=richcontrols.get(richkey(a,b),[])
   if choices:
    choice=min(choices,key=lambda p:hashlib.sha256((a['id']+b['id']+p[0]['id']+p[1]['id']).encode()).hexdigest());treatment.append((a,b));control.append(choice)
  richmatched[typ]={'matched':len(treatment),'same_team':{str(t):summarize(treatment,t) for t in THRESHOLDS},'different_game':{str(t):summarize(control,t) for t in THRESHOLDS}}
 totals=sorted(r['team_implied_total'] for r in rows if isinstance(r.get('team_implied_total'),(int,float)))
 median_total=totals[len(totals)//2] if totals else None
 strata={}
 if median_total is not None:
  for typ in sorted(PAIRS):
   for label,predicate in [('below_pregame_median',lambda a:a.get('team_implied_total') is not None and a['team_implied_total']<median_total),('at_or_above_pregame_median',lambda a:a.get('team_implied_total') is not None and a['team_implied_total']>=median_total)]:
    strata[typ+'|'+label]=summarize([(a,b) for a,b in grouped.get(('same_team',typ),[]) if predicate(a)],.9)
 for resultset in [matched,richmatched]:
  for group in resultset.values():
   group['paired_differences']={str(t):paired_difference(group['same_team'][str(t)],group['different_game'][str(t)]) for t in THRESHOLDS}
 feature_coverage={k:sum(r.get(k) is not None for r in rows) for k in ['team_implied_total','team_spread_line','game_total_line','targets_mean_3','carries_mean_3','pregame_injury_status','pregame_availability_probability','pregame_role_label']}
 result=dict(feature_coverage=feature_coverage,richmatched=richmatched,implied_total_median=median_total,implied_total_strata=strata,scoring_version='research_dk_offense_unfloored_v1',forecast_rows=len(forecasts),unique_pregame_player_games=len(latest),analysis_player_games=len(rows),independent_games=len({r['game'] for r in rows}),weeks=sorted(byweek),exclusions=dict(exclusions),marginals={pos:{str(t):dict(n=len(rr),hits=sum(hit(r,t) for r in rr),rate=sum(hit(r,t) for r in rr)/len(rr)) for t in THRESHOLDS} for pos in ORDER if (rr:=[r for r in rows if r['pos']==pos])},pairs={rel+'|'+typ:{str(t):summarize(pairs,t) for t in THRESHOLDS} for (rel,typ),pairs in grouped.items()},matched=matched,matchcoverage=matchcoverage,participation=dict(Counter(r['participation'] for r in rows)),availability='Original feature labels/probabilities retained; missing source proof is not inferred from postgame status',input_hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in P.glob('*.json') if f.stem in ['forecasts','schedule','stats','aliases','salaries','participation','features']})
 (P/'analysis_players.json').write_text(json.dumps(rows,indent=2)+'\n');(P/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['forecast_rows','unique_pregame_player_games','analysis_player_games','independent_games','weeks','exclusions','marginals','matchcoverage']},indent=2))
if __name__=='__main__':main()
