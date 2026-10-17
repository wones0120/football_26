"""Bounded DST-only, chronological feature ablation; no live DB/model writes."""
from pathlib import Path
from datetime import datetime,UTC,timedelta
from zoneinfo import ZoneInfo
import json,hashlib,collections
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from backend.app.product_services.opponent_qb_context import QBContextIndex,FEATURE_COLUMNS as QB_FEATURES,dst_label_lower_bound_violation
from backend.app.product_services.canonical_projection_inputs import FEATURE_COLUMNS as BASE_FEATURES
from backend.app.product_services.predictions import blend_point_predictions,TARGET_COL
from backend.app.product_services.optimizer import _json_safe
from Database.dst import normalize_team
P=Path(__file__).resolve().parent
read=lambda n:json.load(open(P/(n+'.json')))['rows']
schedules=read('schedule');lookup={};period_start={}
for r in schedules:
 raw=r['raw_row_json'];date=raw.get('gameday');time=raw.get('gametime')
 if not date or not time:continue
 try:kick=datetime.fromisoformat(date+'T'+time).replace(tzinfo=ZoneInfo('America/New_York')).astimezone(UTC)
 except ValueError:continue
 period=(r['season'],r['week']);period_start[period]=min(period_start.get(period,kick),kick)
 for team in [r['home_team'],r['away_team']]:lookup[(r['season'],r['week'],normalize_team(team))]=(kick,r)
logs=[];unmatched=[]
for r in read('qb_logs'):
 game=lookup.get((r['season'],r['week'],normalize_team(r['team'])))
 if not game:unmatched.append(r['raw_nfl_weekly_stat_id']);continue
 raw=r['raw_row_json'];kick,_=game
 logs.append(dict(player_master_id=r['player_master_id'],source_player_id=r['source_player_id'],team=r['team'],season=r['season'],week=r['week'],completed_at=kick+timedelta(hours=24),available_at=r['created_at'],source_row_id=r['raw_nfl_weekly_stat_id'],attempts=raw.get('attempts'),sacks=raw.get('sacks_suffered'),interceptions=raw.get('passing_interceptions'),sack_fumbles_lost=raw.get('sack_fumbles_lost'),passing_yards=raw.get('passing_yards'),passing_epa=raw.get('passing_epa'),carries=raw.get('carries'),rushing_yards=raw.get('rushing_yards')))
index=QBContextIndex(logs);frames=[];audits=[];strict_coverage=collections.Counter();outcomes=collections.defaultdict(list)
for r in logs:outcomes[(r['season'],r['week'],normalize_team(r['team']))].append(r)
for r in read('dst_matrix'):
 game=lookup.get((r['season'],r['week'],normalize_team(r['team'])))
 if not game:continue
 kickoff,schedule=game;decision=period_start[(r['season'],r['week'])]-timedelta(days=1)
 ctx=index.context(opponent_team=r['opponent'],season=r['season'],week=r['week'],decision_at=decision,strict_source_clocks=False)
 strict=index.context(opponent_team=r['opponent'],season=r['season'],week=r['week'],decision_at=decision)
 strict_coverage['rows']+=1;strict_coverage['with_qb_history']+=int(strict['features']['opponent_qb_prior_games']>0)
 row=dict(r,decision_at=decision.isoformat(),kickoff_at=kickoff.isoformat(),recent_team=r['team'],opponent_team=r['opponent'],label_dk_total_points=r['dk_points'],**ctx['features'])
 row['is_home']=float(normalize_team(schedule['home_team'])==normalize_team(r['team']))
 for feature in BASE_FEATURES:
  if feature not in row:row[feature]=float(feature=='position_dst') if feature.startswith('position_') else 0.
 obs=outcomes[(r['season'],r['week'],normalize_team(r['opponent']))]
 for field,label in [('sacks','label_opponent_qb_sacks'),('interceptions','label_opponent_qb_interceptions')]:
  row[label]=sum(o[field] for o in obs) if obs and all(o[field] is not None for o in obs) else np.nan
 frames.append(row);audits.append(dict(matrix_row_id=r['player_game_feature_matrix_id'],season=r['season'],week=r['week'],team=r['team'],opponent=r['opponent'],source_created_at=r['created_at'],strict_context=strict,reconstructed_context=ctx))
f=pd.DataFrame(frames);f['period']=f.season*100+f.week
label_audit=[]
for rr in f.to_dict('records'):
 violation=dst_label_lower_bound_violation(rr[TARGET_COL],rr['label_opponent_qb_sacks'],rr['label_opponent_qb_interceptions'])
 if violation:label_audit.append({k:rr[k] for k in ['season','week','team','opponent','player_game_feature_matrix_id',TARGET_COL,'label_opponent_qb_sacks','label_opponent_qb_interceptions']})
# 33 impossible 2026 labels and whole-week zero clusters make the remaining
# unverified 2026 DK labels unusable as a held-out truth set. Do not repair them
# by assuming zero, or by reconstructing only some scoring components.
f.loc[f.season.eq(2026),TARGET_COL]=np.nan
(P/'dst_label_audit.json').write_text(json.dumps(dict(lower_bound_violations=label_audit,excluded_dk_seasons=[2026],policy='2026 DK evaluation withheld pending complete sourced label reconciliation; QB sack/INT proxy targets retained'),indent=2)+'\n')
# Predeclared cuts: each calibration and held-out block is strictly after fit.
folds=[('2025_holdout',202414,202501,202599),('2026_weeks1_3',202515,202601,202603),('2026_weeks4_5_inspected',202515,202604,202605)]
results=[];predictions=[];fits=0
for name,cal_start,test_start,test_end in folds:
 # 2026 folds share 2025 calibration; no 2026 inspected outcomes enter fitting.
 train=f.loc[f.period<cal_start].copy();cal=f.loc[(f.period>=cal_start)&(f.period<(202601 if test_start>=202601 else test_start))].copy();test=f.loc[(f.period>=test_start)&(f.period<=test_end)].copy()
 assert not train.empty and not cal.empty and not test.empty
 for target in [TARGET_COL,'label_opponent_qb_sacks','label_opponent_qb_interceptions']:
  tr=train.dropna(subset=[target]);ca=cal.dropna(subset=[target]);te=test.dropna(subset=[target]);assert len(tr)>=100
  if te.empty:continue
  for arm,columns in [('baseline',BASE_FEATURES),('plus_opponent_qb',BASE_FEATURES+QB_FEATURES)]:
   imputer=SimpleImputer(strategy='median',keep_empty_features=True)
   X=imputer.fit_transform(tr[columns].apply(pd.to_numeric,errors='coerce'));model=GradientBoostingRegressor(random_state=42);model.fit(X,tr[target]);fits+=1
   def predict(df):
    raw=model.predict(imputer.transform(df[columns].apply(pd.to_numeric,errors='coerce')))
    return blend_point_predictions(raw,tr,df) if target==TARGET_COL else np.maximum(0,raw)
   cp=predict(ca);tp=predict(te);actual=te[target].to_numpy();residual=ca[target].to_numpy()-cp;lo,hi=np.quantile(residual,[.1,.9]);error=tp-actual
   bins=[]
   for ix in np.array_split(np.argsort(tp),3):bins.append(dict(n=len(ix),predicted_mean=float(tp[ix].mean()),actual_mean=float(actual[ix].mean())))
   metric=dict(fold=name,target=target,arm=arm,train_n=len(tr),calibration_n=len(ca),heldout_n=len(te),train_through=int(tr.period.max()),calibration_periods=sorted(ca.period.unique().tolist()),test_periods=sorted(te.period.unique().tolist()),mae=float(np.abs(error).mean()),rmse=float(np.sqrt(np.mean(error**2))),bias=float(error.mean()),coverage80=float(((actual>=tp+lo)&(actual<=tp+hi)).mean()),interval_width80=float(hi-lo),calibration_bins=bins)
   results.append(metric)
   for rr,pr,act in zip(te.to_dict('records'),tp,actual):predictions.append(dict(fold=name,target=target,arm=arm,season=rr['season'],week=rr['week'],team=rr['team'],opponent=rr['opponent'],matrix_row_id=rr['player_game_feature_matrix_id'],prediction=float(pr),actual=float(act)))
   print(name,target,arm,'MAE',round(metric['mae'],4),'n',len(te),flush=True)
# Live/shadow context only: do not map these features into production projection.
news=json.load(open('research/sunday_hurts_refresh_20261015/v1/news_ingest.json'));live=json.load(open('research/sunday_hurts_refresh_20261015/v1/EVIDENCE.json'));cutoff=live['cutoff'];mckee=news['canonical_ids']['Tanner McKee']['player_id'];at=news['captures']['hurts_statement'];expected=dict(team='PHI',player_master_id=mckee,source_uri=at['uri'],evidence_tier='inferred',observed_at=at['observed_at'],received_at=at['received_at']);contexts={}
for label,evidence in [('panthers_expected_mckee',expected),('panthers_prior_primary_proxy',None)]:contexts[label]=index.context(opponent_team='PHI',season=2026,week=6,decision_at=cutoff,starter_evidence=evidence)
for starter in live['starting_qbs']:
 if starter['team']=='CHI':
  ev=starter['evidence_json'];contexts['atlanta_chi_provisional']=index.context(opponent_team='CHI',season=2026,week=6,decision_at=cutoff,starter_evidence=dict(team='CHI',player_master_id=starter['player_master_id'],source_uri=ev.get('source_uri'),evidence_tier=starter['evidence_tier'],observed_at=ev.get('observed_at'),received_at=starter.get('created_at')))
# Team explicitly leaves all three CHI quarterbacks unresolved. These are
# labeled conditional candidate contexts, never starter assertions/probabilities.
chi_news=news['captures']['chi_qb']
for name,pid in [('williams','0ad9dc76-9ee5-4940-9f07-ca9839134784'),('bagent','da2e3c42-0cbb-480f-9ced-ffa247122dd8'),('keenum','05515b3e-0b96-442f-ad12-e911d45f4bf1')]:
 contexts['chi_'+name+'_if_starts']=index.context(opponent_team='CHI',season=2026,week=6,decision_at=cutoff,starter_evidence=dict(team='CHI',player_master_id=pid,source_uri=chi_news['uri'],evidence_tier='inferred',observed_at=chi_news['observed_at'],received_at=chi_news['received_at'],conditional_scenario=True))
report=dict(contract='opponent_qb_context_shadow_ablation_v1',generated_at=datetime.now(UTC).isoformat(),live_activation=False,production_feature_columns_changed=False,fit_count=fits,features=QB_FEATURES,baseline_features=BASE_FEATURES,model='GradientBoostingRegressor(random_state=42), default parameters; DST-only training; same model/splits each arm; production mean/history blend for DK points',historical_source_clocks=dict(strict_coverage),historical_reconstruction=True,unmatched_qb_log_rows=len(unmatched),invalid_dst_label_count=len(label_audit),dk_2026_evaluation_withheld=True,matrix_rows=len(f),matrix_seasons=dict(collections.Counter(f.season)),results=results,current_contexts=contexts,limitations=['Chronologically held-out retrospective reconstruction; historical raw receipts postdate decisions. Not source-verified historical backtest or fresh outcome-blind validation.','2026 Week4/5 outcomes previously inspected; all experiment choices and results are retrospective.','Historical QB is previous completed team game primary-dropback QB, never actual target-game starter; starter-change/uncertainty benefit cannot be validated without archived pregame evidence.','DST-only ablation uses production baseline feature names/model family and point-history blend; not an exact replay of the pooled production model/calibration.','Sack/INT targets are sums of opposing QB logs, not full DST box scores; trick-play sacks/interceptions by non-QBs may differ.','Small historical salary-feature coverage; no hyperparameter tuning or live activation.','Game completion proxy is kickoff+24h and prior-week-only, not a claimed official completion timestamp.','No feature or bonus propagated to offense/team totals; team outlook lacks historical sourced starter context.'],source_hashes={n:hashlib.sha256((P/(n+'.json')).read_bytes()).hexdigest() for n in ['qb_logs','dst_matrix','schedule','starter_history']})
(P/'metrics.json').write_text(json.dumps(_json_safe(report),indent=2,allow_nan=False)+'\n');(P/'feature_audit.json').write_text(json.dumps(_json_safe(audits),indent=2,allow_nan=False)+'\n');(P/'heldout_predictions.json').write_text(json.dumps(predictions,indent=2,allow_nan=False)+'\n');f.drop(columns='period').to_csv(P/'reconstructed_feature_frame.csv',index=False);print('strict',dict(strict_coverage),'live',contexts,'fits',fits,flush=True)
