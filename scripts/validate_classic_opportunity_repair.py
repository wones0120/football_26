"""Frozen-model, read-only opportunity repair experiment. Never writes database state."""
import gzip,json,sys
from pathlib import Path
from hashlib import sha256
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.app.product_services.model_artifacts import deserialize_artifact
from backend.app.product_services.canonical_projection_inputs import attach_lagged_opportunity_features,apply_pregame_projection_context
from backend.app.product_services.offensive_role import attach_offensive_role
from backend.app.product_services.predictions import blend_point_predictions,apply_opportunity_point_adjustment,derive_calibration_roles,apply_residual_calibration
OUT=ROOT/'artifacts/classic_opportunity_repair'
def save(name,value):
 (OUT/name).write_text(json.dumps(value,default=str,indent=2,allow_nan=True)+'\n')

def forecasts(a,t):
 raw=a['model'].predict(t[a['feature_columns']].apply(pd.to_numeric,errors='coerce').fillna(0))
 means=blend_point_predictions(raw,a['train'],t)
 means,details=apply_opportunity_point_adjustment(means,a['train'],t)
 means+=t['market_team_point_adjustment'].fillna(0).to_numpy()
 roles=derive_calibration_roles(t);result=[]
 for i,row in t.iterrows():
  pos=row['position'];role=row.get('pregame_role_label');role=role if role in {'LEAD','COMMITTEE','PRIMARY','SECONDARY','ROTATION'} else roles.iloc[i]
  key=f'{pos}|{role}';split=a['calibration'].get('importance_splits_by_role',{}).get(key)
  if split is not None and pd.notna(row['offensive_role_importance']):key+='|importance_'+('high' if row['offensive_role_importance']>=split else 'low')
  p=a['profiles'].get(key,a['profiles'].get(f'{pos}|{role}',a['profiles'].get(pos,a['profiles']['__ALL__'])))
  prob=float(row['pregame_availability_probability']);prob*=float(row['pregame_start_probability']) if pos=='QB' else 1
  q=apply_residual_calibration(max(0,float(means[i])),p)
  result.append({'player_id':str(row.player_id),'mean':max(0,float(means[i]))*prob,'p10':q['p10']*prob,'p90':q['p90']*prob,'calibration_role':role,'profile':key,**details.iloc[i].to_dict()})
 return pd.DataFrame(result)

def corrected(a,r,weekly):
 original=a['target'].copy().reset_index(drop=True);t=original.copy();meta=r['params_json']['pregame_context'];known=set(t.player_id.astype(str));extras={}
 roles={x['player_id']:x for x in meta.get('role_availability_audit',{}).get('players',[])}
 for allocation in meta['allocations']:
  for player in allocation.get('players',[]):
   pid=player['player_id']
   if pid in known:continue
   extra=extras.setdefault(pid,{'player_id':pid,'player_master_id':pid,'recent_team':allocation['team'],'team':allocation['team'],'position':roles.get(pid,{}).get('position','RB' if allocation['opportunity']=='carry' else 'WR'),'season':r['season'],'week':r['week'],'availability_probability':1.0})
   if player['prior_volume']>0:extra['availability_probability']=min(extra['availability_probability'],1-player['vacated_volume']/player['prior_volume'])
 if extras:t=pd.concat([t,pd.DataFrame(extras.values())],ignore_index=True)
 # Rebuild only opportunity inputs using source versions actually received by cutoff.
 t,source=attach_lagged_opportunity_features(t,weekly,cutoff=pd.Timestamp(r['data_cutoff_at']).tz_convert('UTC'),policy='team_window_v2')
 context=[]
 for _,row in t.iterrows():
  c={'player_id':str(row.player_id)}
  for source_name in ['availability_probability','start_probability','carry_share','target_share','role_label','injury_status','expected_snaps','expected_routes','expected_carries','expected_targets','red_zone_share','goal_line_share']:
   value=row.get('pregame_'+source_name)
   if pd.isna(value):value=row.get(source_name)
   if pd.notna(value):c[source_name]=value
  context.append(c)
  qb=original[['recent_team','team_starting_qb_player_id']].dropna().drop_duplicates('recent_team').rename(columns={'recent_team':'team','team_starting_qb_player_id':'player_master_id'})
 t,allocation=apply_pregame_projection_context(t,pregame_context=pd.DataFrame(context),starting_qbs=qb)
 excluded=t.iloc[len(original):].copy();t=t.iloc[:len(original)].copy()
 # All non-opportunity context is frozen. Only allocation outputs replace originals.
 replace_columns=[x for x in t if x.startswith('opportunity_') or x in {'carries_mean_3','targets_mean_3','carry_share_mean_3','target_share_mean_3','team_carries_mean_3','team_targets_mean_3'} or x.endswith('_mean_3_available') and x!='snap_share_mean_3_available' or x.startswith(('pregame_base_','pregame_effective_')) or x=='pregame_opportunity_context_applied']
 for col in replace_columns:original[col]=t[col]
 role_inputs=original.copy()
 for kind in ('carry','target'):
  share=kind+'_share_mean_3';explicit='pregame_effective_'+kind+'_share'
  role_inputs[share]=original[explicit].where(original[explicit].notna(),original['pregame_base_'+share]);role_inputs[share+'_available']=original[share+'_available']|original[explicit].notna()
 refreshed=attach_offensive_role(role_inputs)
 for col in ['offensive_role_importance','offensive_role_completeness','offensive_role_evidence','offensive_role_class','offensive_role_reason','offensive_role_confidence','offensive_role_source']:original[col]=refreshed[col]
 allowed={'offensive_role_importance','offensive_role_completeness'}
 for col in a['feature_columns']:
  if col not in allowed:pd.testing.assert_series_equal(a['target'][col].reset_index(drop=True),original[col].reset_index(drop=True))
 for allocation_row in allocation['allocations']:
  assert allocation_row['player_projected_volume_sum']<=allocation_row['team_volume']+1e-6
  assert abs(allocation_row['player_projected_volume_sum']+allocation_row['unallocated_volume']-allocation_row['team_volume'])<1e-6
 assert (excluded['carries_mean_3'].fillna(0)[excluded.pregame_availability_probability.eq(0)&excluded.position.eq('RB')]==0).all()
 assert (excluded['targets_mean_3'].fillna(0)[excluded.pregame_availability_probability.eq(0)]==0).all()
 for kind,count,positions in [("carry","carries",{"RB"}),("target","targets",{"RB","WR","TE"})]:
  supported=original[count+"_mean_3_available"]|original["pregame_effective_"+kind+"_share"].notna()
  original["projected_"+count]=original[count+"_mean_3"].where(supported & original.position.isin(positions),np.nan)
 original["projected_opportunity_source"]=np.where(original.position.isin({"RB","WR","TE"}),np.where(original.projected_carries.notna()|original.projected_targets.notna(),"same_team_common_window_with_evidence_supported_context","unavailable_same_team_history"),"not_applicable")
 return original,allocation,excluded,source

def main():
 weekly=pd.DataFrame(json.load(gzip.open(OUT/'weekly_stats.json.gz','rt')));inventory=json.loads((OUT/'inventory.json').read_text());stored=pd.DataFrame(json.loads((OUT/'original_projections.json').read_text()));summary=[]
 for r in inventory:
  run=r['projection_run_id'];a=deserialize_artifact((OUT/(run+'.joblib')).read_bytes(),r['artifact_sha256']);t=a['target'].reset_index(drop=True);base=forecasts(a,t)
  for count,positions in [('carries',{'RB'}),('targets',{'RB','WR','TE'})]:
   t['projected_'+count]=t[count+'_mean_3'].where(t.position.isin(positions),np.nan)
  orig=stored[stored.projection_run_id.eq(run)].set_index('player_id');difference=max(float(np.max(np.abs(base[k].to_numpy()-base.player_id.map(orig[k]).to_numpy()))) for k in ['mean','p10','p90'])
  assert difference<1e-7,(run,difference)
  new,allocation,excluded,source=corrected(a,r,weekly);after=forecasts(a,new)
  comparison=t[['player_id','player_display_name','position','recent_team','salary']].copy()
  for name,before,changed in [('mean',base,after),('p10',base,after),('p90',base,after),('projected_carries',t,new),('projected_targets',t,new),('carries_mean_3',t,new),('targets_mean_3',t,new),('carry_share_mean_3',t,new),('target_share_mean_3',t,new),('pregame_opportunity_point_weight',base,after)]:
   comparison['before_'+name]=before[name];comparison['after_'+name]=changed[name];comparison['delta_'+name]=changed[name]-before[name]
  comparison['calibration_role']=base.calibration_role;comparison['after_calibration_role']=after.calibration_role
  comparison['history_status']=new.opportunity_history_status;comparison['history_window']=new.opportunity_history_window;comparison['expected_depth_role']=t.get('expected_depth_role');comparison['availability']=t.pregame_availability_probability
  comparison['material']=comparison.delta_mean.abs().ge(1)|comparison.delta_projected_carries.abs().ge(1)|comparison.delta_projected_targets.abs().ge(1)|((comparison.after_projected_carries.isna()&comparison.before_projected_carries.abs().ge(1))|(comparison.after_projected_targets.isna()&comparison.before_projected_targets.abs().ge(1)))
  comparison=comparison.loc[comparison.delta_mean.abs().sort_values(ascending=False).index]
  comparison.to_csv(OUT/(run+'_comparison.csv'),index=False);save(run+'_allocation.json',allocation);excluded.to_json(OUT/(run+'_excluded.json'),orient='records',indent=2);new.to_pickle(OUT/(run+'_corrected_features.pkl'));after.to_csv(OUT/(run+'_corrected_predictions.csv'),index=False)
  summary.append({'run':run,'week':r['week'],'cutoff':str(r['data_cutoff_at']),'pool':len(t),'baseline_max_error':difference,'material_players':int(comparison.material.sum()),'mean_changed':int(comparison.delta_mean.abs().gt(1e-9).sum()),'mean_increases':int(comparison.delta_mean.gt(1e-9).sum()),'mean_decreases':int(comparison.delta_mean.lt(-1e-9).sum()),'no_same_team_history':int(new.opportunity_history_status.eq('no_same_team_window_history').sum()),'training_latest_period':int((a['train'].season*100+a['train'].week).max()),'source':source})
  print(run,summary[-1],flush=True)
 save('replay_summary.json',summary)
if __name__=='__main__':main()
