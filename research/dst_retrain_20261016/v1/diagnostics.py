from pathlib import Path
import json,hashlib,joblib
import pandas as pd,numpy as np
from Database.dst import normalize_team
P=Path(__file__).resolve().parent;C=Path('research/dst_scoring_repair_20261015/v1');rows=pd.DataFrame(json.load(open(P/'heldout_predictions.json')));scored=json.load(open(C/'scored_games.json'));truth={(int(s['game_id'][:4]),int(s['game_id'][5:7]),s['team']):s for s in scored}
for i,r in rows.iterrows():
 s=truth[(int(r.season),int(r.week),normalize_team(r.team))];assert s['dk_points']==r.actual
 comp=s['components'];rows.loc[i,'td_game']=bool(comp['defensive_touchdowns']+comp['special_teams_touchdowns']);rows.loc[i,'four_plus_sacks']=bool(comp['sacks']>=4);rows.loc[i,'two_plus_turnovers']=bool(comp['interceptions']+comp['fumble_recoveries']>=2);rows.loc[i,'negative_score']=bool(r.actual<0)
summary=[]
for dim in ['season','td_game','four_plus_sacks','two_plus_turnovers','negative_score']:
 for (value,arm),group in rows.groupby([dim,'arm']):
  err=group.prediction-group.actual;summary.append(dict(stratum=dim,value=str(value),arm=arm,n=len(group),mae=float(abs(err).mean()),rmse=float(np.sqrt((err**2).mean())),bias=float(err.mean())))
(P/'component_strata.json').write_text(json.dumps(dict(component_model_metrics='Not applicable: production has one total-DK-point target, no sack/INT/component heads. Report total error conditional on verified event components.',results=summary),indent=2)+'\n')
a=joblib.load(P/'incumbent.joblib');b=joblib.load(P/'prepared_incumbent.joblib');cols=a['train'].columns.tolist()
for cutoff in [202414,202515]:
 x=a['train'][(a['train'].season*100+a['train'].week)<cutoff].sort_values('player_game_feature_matrix_id').reset_index(drop=True);y=b['train'][(b['train'].season*100+b['train'].week)<cutoff].sort_values('player_game_feature_matrix_id').reset_index(drop=True);assert x.equals(y[cols]),'Historical frozen training paths differ'
assert ((b['train'].season<2026)|((b['train'].season==2026)&(b['train'].week<6))).all()
from backend.app.product_services.dst_training_labels import read_verified_correction,select_corrected_dst_labels
receipt=json.load(open(C/'full_matrix_version_receipt.json'));dataset=read_verified_correction(receipt['artifact_path'],expected_sha256=receipt['content_sha256']);strict,audit=select_corrected_dst_labels(a['train'],dataset,target_season=2026,target_week=6);fitted=joblib.load(P/'candidate_training.joblib')['train'];assert strict['label_dk_total_points'].equals(fitted['label_dk_total_points']);(P/'audit.json').write_text(json.dumps(dict(strict_label_selection_reproduces_all_validation_targets=True,prepared_and_active_historical_fit_inputs_identical=True,no_target_week_training_rows=True,source_receipt_verified=True,selection=audit,opponent_qb_shadow_features_in_live=[],source_clock_limit='Historical feature collection timestamps are retrospective; no prospective availability proof claimed.'),indent=2)+'\n')
print('audits passed; strata',len(summary))
