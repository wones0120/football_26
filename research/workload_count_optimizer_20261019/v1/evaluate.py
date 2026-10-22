import json,argparse,hashlib
from pathlib import Path
import pandas as pd,numpy as np
from backend.app.product_services.workload_count_forecast import forecast,fit_team_model,team_games
parser=argparse.ArgumentParser();parser.add_argument('--history',required=True);parser.add_argument('--output',required=True)
args=parser.parse_args();P=Path(args.output);P.mkdir(parents=True,exist_ok=True)
source=Path(args.history);f=pd.read_json(source); model=fit_team_model(team_games(f),before_period=202602)
results=[]; missing=[];team_results=[]
for period in [202602,202603,202604,202605]:
 past=f[f.period<period]; actual=f[f.period==period]; teams=set(actual.team)
 actors=past[past.player_master_id.notna()].sort_values('period').drop_duplicates('player_master_id',keep='last');actors=actors[actors.team.isin(teams)]
 actors=actors[['player_master_id','team','position']].to_dict('records')
 # Historical current-starter proof unavailable: largest prior team QB, last full-game share only; explicitly conditional proxy.
 q=past[past.position=='QB'].sort_values(['period','pass_attempts','player_master_id']).groupby('team').tail(1)
 starters=dict(zip(q.team,q.player_master_id))
 prediction=forecast(past,actors,before_period=period,starters=starters,model=model)
 observed_teams={r.team:r for r in team_games(actual).itertuples()}
 previous_teams=team_games(past)
 for team,point in prediction['teams'].items():
  observed=observed_teams.get(team)
  for channel in ['pass_attempts','rush_attempts','targets']:
   value=point.get(channel) if point else None
   actual_value=getattr(observed,channel) if observed else None
   previous=previous_teams[previous_teams.team==team].sort_values('period').tail(3)
   baseline=float(previous[channel].mean()) if len(previous)==3 and previous[channel].notna().all() else None
   team_results.append(dict(period=period,team=team,channel=channel,forecast=value,actual=actual_value,history=baseline))
 lookup={r.player_master_id:r for r in actual.itertuples()}
 for row in prediction['players']:
  observed=lookup.get(row['player_master_id'])
  for channel,value in row['counts'].items():
   if value is None: continue
   h=row['raw_history'][channel]; meaningful= h['mean'] >= (15 if channel=='pass_attempts' else 3)
   if observed is None or pd.isna(getattr(observed,channel)):
    missing.append(dict(period=period,player=row['player_master_id'],position=row['position'],channel=channel));continue
   y=float(getattr(observed,channel))
   results.append(dict(period=period,player=row['player_master_id'],position=row['position'],channel=channel,forecast=value,history=h['mean'],actual=y,meaningful=meaningful))
r=pd.DataFrame(results); report={};weekly={}
for role,g in r.groupby(['position','channel','meaningful']):
 report['/'.join(map(str,role))]={'n':len(g),'forecast_mae':float(abs(g.forecast-g.actual).mean()),'history_mae':float(abs(g.history-g.actual).mean()),'bias':float((g.forecast-g.actual).mean())}
for key,g in r.groupby(['period','position','channel','meaningful']):
 weekly['/'.join(map(str,key))]={'n':len(g),'forecast_mae':float(abs(g.forecast-g.actual).mean()),'history_mae':float(abs(g.history-g.actual).mean()),'bias':float((g.forecast-g.actual).mean())}
t=pd.DataFrame(team_results);team_metrics={}
for key,g in t.groupby(['period','channel']):
 matched=g.dropna(subset=['forecast','actual','history'])
 team_metrics['/'.join(map(str,key))]={'requested':len(g),'matched':len(matched),'missing_forecast':int(g.forecast.isna().sum()),'missing_actual':int(g.actual.isna().sum()),'forecast_mae':float(abs(matched.forecast-matched.actual).mean()),'history_mae':float(abs(matched.history-matched.actual).mean()),'bias':float((matched.forecast-matched.actual).mean())}
(P/'validation.json').write_text(json.dumps({'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_rows':len(f),'model':model,'metrics':report,'weekly_metrics':weekly,'team_metrics':team_metrics,'missing_actual_rows':len(missing),'missing_actual_by_position':pd.DataFrame(missing).groupby('position').size().to_dict(),'rows':len(r),'caveat':'revised sources; historical starter approximated from lagged QB role, not original starter receipt; conditional participation cohort, no DNP zero imputation'},indent=2))
r.to_csv(P/'validation_rows.csv',index=False)
t.to_csv(P/'team_validation_rows.csv',index=False)
print(json.dumps({'rows':len(r),'missing_actual_rows':len(missing),'meaningful':{k:v for k,v in report.items() if k.endswith('/True')}},indent=2))
