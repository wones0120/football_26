"""Out-of-time evaluation of archived prelock forecasts; labels never enter scoring."""
import gzip,json,sys
from pathlib import Path
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from Database.scoring import compute_dk_scoring
OUT=ROOT/'artifacts/classic_opportunity_repair'
weekly=pd.DataFrame(json.load(gzip.open(OUT/'weekly_stats.json.gz','rt')))
weekly=weekly[weekly.season.eq(2026)&weekly.week.eq(4)&weekly.player_master_id.notna()].sort_values(['created_at','raw_nfl_weekly_stat_id']).drop_duplicates(['player_master_id','team'],keep='last')
labels=pd.DataFrame(weekly.raw_row_json.tolist());labels=compute_dk_scoring(labels)
weekly['actual_points']=labels.dk_total_points.to_numpy()
lookup=weekly.set_index(['player_master_id','team'])
inventory=json.loads((OUT/'inventory.json').read_text());summary=[]
schedule=pd.DataFrame([r['raw_row_json'] for r in json.loads((OUT/'schedules.json').read_text())]);schedule=schedule[schedule.week.astype(int).eq(4)].drop_duplicates('game_id')
# Validate each player's actual game kickoff, not the week-wide Thursday kickoff.
for run in [r for r in inventory if r['week']==4]:
 rid=run['projection_run_id'];t=pd.read_pickle(OUT/(rid+'_corrected_features.pkl'));c=pd.read_csv(OUT/(rid+'_comparison.csv'))
 c['actual_points']=[lookup.loc[(pid,team),'actual_points'] if (pid,team) in lookup.index else np.nan for pid,team in zip(c.player_id,c.recent_team)]
 for stat in ['carries','targets']:c['actual_'+stat]=[lookup.loc[(pid,team),stat] if (pid,team) in lookup.index else np.nan for pid,team in zip(c.player_id,c.recent_team)]
 kickoffs=[]
 for game in t.game_id.unique():
  match=schedule[schedule.game_id.eq(game)]
  if len(match):
   row=match.iloc[0];kickoffs.append(pd.Timestamp(str(row.gameday)+' '+str(row.gametime),tz='America/New_York').tz_convert('UTC'))
 assert kickoffs and pd.Timestamp(run['data_cutoff_at']).tz_convert('UTC')<min(kickoffs)
 c['price_band']=np.where(c.salary>=7000,'expensive_7000_plus',np.where(c.salary<=4500,'cheap_4500_or_less','middle'))
 labeled=c[c.position.isin(['RB','WR','TE'])&c.actual_points.notna()].copy()
 labeled.to_csv(OUT/(rid+'_historical_labels.csv'),index=False)
 groups={'all':labeled}
 for col in ['position','price_band','calibration_role','history_status']:
  for label,group in labeled.groupby(col,dropna=False):groups[col+':'+str(label)]=group
 metrics={}
 for label,g in groups.items():
  entry={'n':len(g),'opportunity_carry_n':int((g.position.eq('RB')&g.after_projected_carries.notna()).sum()),'opportunity_target_n':int(g.after_projected_targets.notna().sum())}
  for version in ['before','after']:
   err=g[version+'_mean']-g.actual_points
   entry[version]={'mae':float(err.abs().mean()),'rmse':float(np.sqrt((err**2).mean())),'p10_observed':float((g.actual_points<=g[version+'_p10']).mean()),'p90_observed':float((g.actual_points<=g[version+'_p90']).mean()),'interval_coverage':float(((g.actual_points>=g[version+'_p10'])&(g.actual_points<=g[version+'_p90'])).mean()),'interval_width':float((g[version+'_p90']-g[version+'_p10']).mean()),'carry_mae':float((g.loc[g.position.eq('RB')&g.after_projected_carries.notna(),version+'_projected_carries']-g.loc[g.position.eq('RB')&g.after_projected_carries.notna(),'actual_carries']).abs().mean()),'target_mae':float((g.loc[g.after_projected_targets.notna(),version+'_projected_targets']-g.loc[g.after_projected_targets.notna(),'actual_targets']).abs().mean())}
  metrics[label]=entry
 summary.append({'source_input_parity_certified':False,'usable_for_promotion':False,'source_limit':'Saved fitted predictions reproduce, but archived raw sources do not reproduce the original opportunity inputs at the Week 4 cutoffs; the restricted-source comparison is not a same-input allocation ablation.','run':rid,'cutoff':run['data_cutoff_at'],'earliest_target_kickoff':str(min(kickoffs)),'eligible_skill_players':int(c.position.isin(['RB','WR','TE']).sum()),'labeled_skill_players':len(labeled),'missing_labels_excluded':int(c.position.isin(['RB','WR','TE']).sum())-len(labeled),'metrics':metrics})
 print(rid,metrics['all'],flush=True)
(OUT/'historical_validation.json').write_text(json.dumps(summary,indent=2)+'\n')
