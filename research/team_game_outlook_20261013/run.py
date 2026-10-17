"""Reproducible offline fit/evaluation and saved 2026W6 team/game outlook."""
import hashlib,json,time
from pathlib import Path
import joblib,numpy as np,pandas as pd
from sklearn.metrics import mean_absolute_error,mean_squared_error
from backend.app.product_services.team_game_outlook import TeamGameModel,FEATURES,TARGETS,HISTORY,CONTRACT,SEED,digest,budgets
from Database.dst import normalize_team
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SOURCES=ROOT/'research/neural_workload_benchmark_20261013/expanded_v3/sources'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def serial(x):
 if isinstance(x,np.generic):return x.item()
 raise TypeError(type(x).__name__)

def prepare():
 manifest=json.loads((SOURCES/'manifest.json').read_text());names=['games.parquet']+['pbp_'+str(y)+'.parquet' for y in range(2023,2027)]
 for n in names:
  if sha(SOURCES/n)!=manifest[n]['sha256']:raise ValueError('source changed '+n)
 games=pd.read_parquet(SOURCES/'games.parquet');games=games[(games.season>=2023)&(games.season<=2026)&(games.game_type=='REG')].copy()
 facts={}
 cols=['game_id','posteam','fixed_drive','rush_attempt','pass_attempt','receiver_player_id','epa','success']
 for y in range(2023,2027):
  pbp=pd.read_parquet(SOURCES/('pbp_'+str(y)+'.parquet'),columns=cols)
  pbp=pbp[(pbp.rush_attempt==1)|(pbp.pass_attempt==1)].copy();pbp['posteam']=pbp.posteam.map(normalize_team)
  for (gid,team),r in pbp.groupby(['game_id','posteam']):
   plays=len(r);facts[(gid,team)]={'plays':plays,'drives':int(r.fixed_drive.nunique()),'epa':float(r.epa.mean()),'success':float(r.success.mean()),'target_fraction':float(((r.pass_attempt==1)&r.receiver_player_id.notna()).sum()/plays),'carry_fraction':float((r.rush_attempt==1).sum()/plays)}
 rows=[];history={};rejected=[]
 for g in games.sort_values(['gameday','gametime','game_id']).to_dict('records'):
  if pd.isna(g['gametime']):continue
  kickoff=pd.Timestamp(str(g['gameday'])+' '+str(g['gametime']),tz='America/New_York').tz_convert('UTC')
  cutoff=kickoff-pd.Timedelta(hours=1);teams=[normalize_team(g['home_team']),normalize_team(g['away_team'])]
  complete=not pd.isna(g['home_score']) and not pd.isna(g['away_score'])
  for side,team in enumerate(teams):
   opp=teams[1-side];past=[r for r in history.get(team,[]) if r['completed_at']<cutoff and (r['season'],r['week'])<(int(g['season']),int(g['week']))][-5:]
   opposing=[r for r in history.get(opp,[]) if r['completed_at']<cutoff and (r['season'],r['week'])<(int(g['season']),int(g['week']))][-5:]
   row={'game_id':g['game_id'],'season':int(g['season']),'week':int(g['week']),'team':team,'opponent':opp,'home':1-side,'kickoff_at':kickoff.isoformat(),'cutoff_at':cutoff.isoformat(),'last_history_completed_at':max([r['completed_at'] for r in past+opposing]).isoformat() if past+opposing else None,'sunday_main':g['weekday']=='Sunday' and '13:00'<=g['gametime']<='16:30','rest_days':(cutoff-past[-1]['completed_at']).total_seconds()/86400 if past else np.nan,'history_count':len(past),'opponent_history_count':len(opposing)}
   for prefix,prior in [('own',past),('opponent',opposing)]:
    for field in HISTORY:row[prefix+'_'+field+'_mean5']=float(np.mean([r[field] for r in prior])) if prior else np.nan
   fact=facts.get((g['game_id'],team));row.update({k:np.nan for k in TARGETS})
   if complete and fact and fact['drives']>0:
    points=float(g['home_score'] if side==0 else g['away_score']);against=float(g['away_score'] if side==0 else g['home_score'])
    row.update({**fact,'points':points})
   elif complete:rejected.append({'game_id':g['game_id'],'team':team,'reason':'missing PBP; labels unavailable, never zero'})
   rows.append(row)
  # Both game rows constructed before appending either side's outcomes.
  if complete:
   for side,team in enumerate(teams):
    fact=facts.get((g['game_id'],team))
    if fact and fact['drives']>0:history.setdefault(team,[]).append({**fact,'points':float(g['home_score'] if side==0 else g['away_score']),'points_against':float(g['away_score'] if side==0 else g['home_score']),'season':int(g['season']),'week':int(g['week']),'completed_at':kickoff+pd.Timedelta(hours=8)})
 frame=pd.DataFrame(rows)
 if frame[['game_id','team']].duplicated().any():raise ValueError('canonical team-game collision')
 return frame,{n:manifest[n] for n in names},rejected


def evaluate(model,frame):
 pred=model.predict(frame);result={}
 for i,t in enumerate(TARGETS[:3]):result[t]={'mae':float(mean_absolute_error(frame[t],pred[:,i])),'rmse':float(np.sqrt(mean_squared_error(frame[t],pred[:,i])))}
 baseline=(frame.own_points_mean5+frame.opponent_points_against_mean5)/2
 good=baseline.notna();result['history_points_mae']=float(mean_absolute_error(frame.loc[good,'points'],baseline[good]))
 gamepred=[];prob=[];events=[];interval=[]
 for gid,r in frame.groupby('game_id'):
  if len(r)!=2:continue
  outlook=model.game(r);home=r[r.home==1].iloc[0];away=r[r.home==0].iloc[0];actualhome=float(home.points);actualaway=float(away.points)
  p=outlook['teams'][home.team]['win_half_tie_probability'];actual=float(actualhome>actualaway)+.5*float(actualhome==actualaway)
  prob.append(p);events.append(actual);gamepred.append((outlook['total_points'],actualhome+actualaway,outlook['home_margin'],actualhome-actualaway))
  for row in [home,away]:
   lo,hi=outlook['teams'][row.team]['score_interval_80'];interval.append(lo<=row.points<=hi)
 values=np.asarray(gamepred);result.update(n_team_rows=len(frame),n_games=len(gamepred),total_mae=float(np.abs(values[:,0]-values[:,1]).mean()),margin_mae=float(np.abs(values[:,2]-values[:,3]).mean()),win_half_tie_brier=float(np.mean((np.asarray(prob)-events)**2)),score_interval80_coverage=float(np.mean(interval)))
 result['reliability_bins']=[]
 for lo,hi in [(0,.2),(.2,.4),(.4,.6),(.6,.8),(.8,1.000001)]:
  mask=(np.asarray(prob)>=lo)&(np.asarray(prob)<hi)
  result['reliability_bins'].append({'lo':lo,'hi':min(hi,1),'n':int(mask.sum()),'mean_probability':float(np.asarray(prob)[mask].mean()) if mask.any() else None,'observed_win_half_tie':float(np.asarray(events)[mask].mean()) if mask.any() else None})
 return result


def main():
 started=time.perf_counter();frame,sources,rejected=prepare();frame.to_csv(HERE/'feature_matrix.csv',index=False)
 complete=frame.dropna(subset=TARGETS);counts=complete.groupby('game_id').size();complete=complete[complete.game_id.isin(counts[counts==2].index)]
 train=complete[complete.season==2023];val=complete[(complete.season==2024)&(complete.week<=8)];cal=complete[(complete.season==2024)&(complete.week>=9)]
 choices=[];models={}
 for alpha in [10,100]:
  m=TeamGameModel(alpha).fit(train);models[alpha]=m;choices.append({'alpha':alpha,'validation_points_mae':float(mean_absolute_error(val.points,m.predict(val)[:,0]))})
 alpha=min(choices,key=lambda r:r['validation_points_mae'])['alpha'];(HERE/'frozen_selection.json').write_text(json.dumps({'choices':choices,'chosen_alpha':alpha,'spec_sha256':sha(HERE/'SPECIFICATION.md')},indent=2)+'\n')
 historical=models[alpha].calibrate(cal)
 test=complete[(complete.season==2025)&complete.week.between(3,17)]
 results={'retrospective_2025_normal_weeks':evaluate(historical,test),'retrospective_2025_sunday_main':evaluate(historical,test[test.sunday_main]),'frozen_choices':choices,'selected_alpha':alpha,'train_rows':len(train),'validation_rows':len(val),'calibration_rows':len(cal),'label_gaps':rejected}
 finaltrain=complete[complete.season<=2025];finalcal=complete[(complete.season==2026)&(complete.week<=3)];final=TeamGameModel(alpha).fit(finaltrain).calibrate(finalcal)
 diagnostic=complete[(complete.season==2026)&complete.week.isin([4,5])];results['already_inspected_2026w4_w5']=evaluate(final,diagnostic)
 source_clock=max(s['received_at'] for s in sources.values());generated=pd.Timestamp.now(tz='UTC').isoformat()
 metadata={'model_version':'ridge_paired_residual_v1','alpha':alpha,'features':FEATURES,'feature_sha256':digest(FEATURES),'matrix_sha256':sha(HERE/'feature_matrix.csv'),'training_window':'2023W1-2025W18','training_rows':len(finaltrain),'max_training_completed_at':(pd.to_datetime(finaltrain.kickoff_at).max()+pd.Timedelta(hours=8)).isoformat(),'max_calibration_completed_at':(pd.to_datetime(finalcal.kickoff_at).max()+pd.Timedelta(hours=8)).isoformat(),'calibration_window':'2026W1-W3','calibration_games':len(final.residual_pairs),'evaluation':results,'code_sha256':sha(ROOT/'backend/app/product_services/team_game_outlook.py'),'revised_data_caveat':'Historical source imports later than games; prior outcomes inspected. No contemporaneous backtest or pristine holdout claim.','injuries':'not modeled; no injury certainty or final-entry readiness','markets':'excluded from fit/scenario means; existing player market adjustments not added again'}
 current=frame[(frame.season==2026)&(frame.week==6)];outlooks=[final.game(r) for _,r in current.groupby('game_id') if len(r)==2]
 block={'contract_id':CONTRACT,'run_id':'team_game_outlook_20261013_v1','generated_at':generated,'source_available_at':source_clock,'source_hashes':{n:s['sha256'] for n,s in sources.items()},'model_metadata':metadata,'games':outlooks,'seed':SEED,'draws':4096,'baseline_mutation':False,'event_definitions':{'competitive_scoring':'both scores>=20 and abs margin<=14','trailing_productive_passing':'else trailing>7, points>=14 and identified targets>=30','drive_stall_runout':'else points<14 and points/drive<1.4','other':'remaining outcomes','note':'descriptive mutually exclusive proxy events; no injury or QB availability conditioning'}};block['sha256']=digest(block)
 (HERE/'outlook_2026w6.json').write_text(json.dumps(block,indent=2,default=serial,allow_nan=False)+'\n');joblib.dump(final,HERE/'fitted_model.joblib')
 results['runtime_seconds']=time.perf_counter()-started;results['current_games']=len(outlooks);results['feature_count']=len(FEATURES);results['model_sha256']=sha(HERE/'fitted_model.joblib')
 (HERE/'results.json').write_text(json.dumps(results,indent=2,default=serial,allow_nan=False)+'\n');print(json.dumps(results,default=serial))
if __name__=='__main__':main()
