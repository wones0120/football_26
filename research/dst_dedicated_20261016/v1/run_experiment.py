"""Offline, frozen, DST-only comparison; no DB or live-serving writes."""
from pathlib import Path
from datetime import datetime, UTC
from contextlib import redirect_stdout
import hashlib
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from scipy.stats import spearmanr
from backend.app.product_services.dedicated_dst_model import FEATURES, checked_outcomes, build_features, choose_on_prior_weeks
from backend.app.product_services.dst_training_labels import read_verified_correction, select_corrected_dst_labels, TARGET, SCORING_CONTRACT
from backend.app.product_services.predictions import blend_point_predictions
from backend.app.product_services.model_artifacts import training_fingerprint, git_revision
from backend.app.product_services.classic_highest_projection import solve
from backend.app.product_services.optimizer import OptimizerService, _json_safe

P=Path(__file__).resolve().parent
PREVIOUS=Path('research/dst_retrain_20261016/v1')
SOURCE=Path('research/dst_scoring_repair_20261015/v1')
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(name,data): (P/name).write_text(json.dumps(_json_safe(data),indent=2,allow_nan=False)+'\n')

receipt=json.loads((SOURCE/'full_matrix_version_receipt.json').read_text())
correction=read_verified_correction(receipt['artifact_path'],expected_sha256=receipt['content_sha256'])
events=json.loads((SOURCE/'scored_games.json').read_text())
identities=json.loads((SOURCE/'canonical_dst_identity.json').read_text())
outcomes=checked_outcomes(events,identities)
incumbent=joblib.load(PREVIOUS/'incumbent.joblib')
original=incumbent['train'].copy()
fixed,label_audit=select_corrected_dst_labels(original,correction,target_season=2026,target_week=6)
assert label_audit['selected_rows']==804
original['period']=original.season*100+original.week
fixed['period']=fixed.season*100+fixed.week
dst=fixed[fixed.position.eq('DST')].copy()
x=build_features(dst,outcomes)
# Independently require every selected corrected label to equal its canonical event outcome.
for row in dst.itertuples():
    matched=outcomes[(outcomes.season==row.season)&(outcomes.week==row.week)&outcomes.player_master_id.eq(str(row.player_master_id))]
    assert len(matched)==1 and float(matched.iloc[0].points)==float(getattr(row,TARGET))
coverage={}
for column in incumbent['feature_columns']:
    v=pd.to_numeric(dst[column],errors='coerce')
    coverage[column]=dict(missing=int(v.isna().sum()),zero=int(v.eq(0).sum()),distinct=int(v.nunique()),
                          candidate_policy='retained_missing_as_nan' if column in FEATURES else 'excluded_or_rebuilt_from_verified_prior_outcomes')
source_audit=dict(created_at=datetime.now(UTC).isoformat(),criteria_sha256=sha(P/'CRITERIA.md'),label_selection=label_audit,
    outcome_rows=len(outcomes),canonical_dst_count=outcomes.player_master_id.nunique(),all_matrix_scores_match_events=True,
    incumbent_27_feature_audit=coverage,candidate_feature_columns=FEATURES,
    candidate_missing_counts=x.isna().sum().to_dict(),candidate_zero_counts=x.eq(0).sum().to_dict(),
    corrected_home_rows=int(x.dst_home_from_game.ne(dst.is_home).sum()),
    opponent_qb_features_excluded=True,history_cutoff='strictly smaller season/week; current week excluded',
    history_source='complete canonical event outcomes, not legacy zero-filled matrix histories',
    source_chronology='Original historical pregame capture clocks incomplete. Retrospective reconstruction; no fresh blind validation.',
    existing_missing_share_inputs='excluded: source completeness and zero semantics not established for DST',
    sources={str(p):sha(p) for p in [SOURCE/'scored_games.json',SOURCE/'canonical_dst_identity.json',SOURCE/'full_matrix_version_receipt.json',Path(receipt['artifact_path']),PREVIOUS/'incumbent.joblib',PREVIOUS/'prepared_incumbent.joblib']})
save('feature_source_audit.json',source_audit)

rows=[];selection=[]
windows=[(202414,202501,202599),(202515,202601,202605)]
for calstart,teststart,testend in windows:
    train=dst[dst.period<calstart]
    cal=dst[(dst.period>=calstart)&(dst.period<teststart)]
    test=dst[(dst.period>=teststart)&(dst.period<=testend)]
    dedicated,audit=choose_on_prior_weeks(train,x.loc[train.index],TARGET)
    audit.update(calibration_first_week=int(cal.period.min()),test_first_week=int(test.period.min()),outer_training_n=len(train))
    selection.append(audit)
    all_positions=original[original.period<calstart]
    old_model=clone(incumbent['model'])
    old_model.fit(all_positions[incumbent['feature_columns']].apply(pd.to_numeric,errors='coerce').fillna(0),all_positions[TARGET])
    for arm in ['incumbent_policy','dedicated_dst']:
        def predict(frame):
            if arm=='dedicated_dst': return dedicated.predict(x.loc[frame.index])
            raw=old_model.predict(frame[incumbent['feature_columns']].apply(pd.to_numeric,errors='coerce').fillna(0))
            return np.maximum(0,blend_point_predictions(raw,all_positions,frame))
        cp=predict(cal);prediction=predict(test)
        lo,hi=np.quantile(cal[TARGET].to_numpy()-cp,[.1,.9])
        for r,pred in zip(test.to_dict('records'),prediction):
            block='2025_retrospective' if r['season']==2025 else ('2026_w1_3_retrospective' if r['week']<=3 else '2026_w4_5_inspected')
            rows.append(dict(block=block,arm=arm,season=int(r['season']),week=int(r['week']),team=r['team'],
                player_master_id=str(r['player_master_id']),matrix_id=int(r['player_game_feature_matrix_id']),
                actual=float(r[TARGET]),prediction=float(pred),low80=float(pred+lo),high80=float(pred+hi),
                covered=bool(pred+lo<=r[TARGET]<=pred+hi),calibration_n=len(cal),train_n=len(train) if arm=='dedicated_dst' else len(all_positions)))
print('INNER',selection,flush=True)
save('inner_selection.json',selection)
f=pd.DataFrame(rows)
# Reproduce the prior study's exact incumbent predictions and cohort before comparing.
old=pd.DataFrame(json.loads((PREVIOUS/'heldout_predictions.json').read_text()))
prior=old[old.arm.eq('incumbent_policy')].set_index('matrix_id').sort_index()
new=f[f.arm.eq('incumbent_policy')].set_index('matrix_id').sort_index()
assert prior.index.equals(new.index)
assert np.max(np.abs(prior.prediction-new.prediction))<1e-10
assert np.max(np.abs(prior.actual-new.actual))==0

def metrics(frame):
    err=frame.prediction-frame.actual
    ranks=[]
    for _,group in frame.groupby(['season','week']):
        # Constant predictions/truth have no rank discrimination; record 0, never drop silently.
        ranks.append(float(spearmanr(group.prediction,group.actual).statistic) if group.prediction.nunique()>1 and group.actual.nunique()>1 else 0.)
    bins=[]
    for interval,group in frame.groupby(pd.cut(frame.prediction,[-np.inf,4,6,8,10,np.inf]),observed=True):
        bins.append(dict(bin=str(interval),n=len(group),mean_prediction=float(group.prediction.mean()),mean_actual=float(group.actual.mean())))
    return dict(n=len(frame),mae=float(abs(err).mean()),rmse=float(np.sqrt((err**2).mean())),bias=float(err.mean()),
        coverage80=float(frame.covered.mean()),interval_width=float((frame.high80-frame.low80).mean()),
        weekly_rank_correlation=float(np.mean(ranks)),week_clusters=len(ranks),calibration_bins=bins)

def paired(frame):
    wide=frame.pivot(index=['season','week','team'],columns='arm',values='prediction')
    truth=frame.drop_duplicates(['season','week','team']).set_index(['season','week','team']).actual
    difference=(wide.dedicated_dst-truth).abs()-(wide.incumbent_policy-truth).abs()
    grouped=difference.groupby(level=['season','week']).agg(['sum','size']);rng=np.random.default_rng(261016)
    bootstrap=[]
    for _ in range(3000):
        sample=grouped.iloc[rng.integers(0,len(grouped),len(grouped))]
        bootstrap.append(float(sample['sum'].sum()/sample['size'].sum()))
    return dict(mae_difference=float(difference.mean()),week_clusters=len(grouped),ci95=list(map(float,np.quantile(bootstrap,[.025,.975]))))

aggregate={arm:metrics(f[f.arm.eq(arm)]) for arm in ['incumbent_policy','dedicated_dst']}
blocks={name:dict(metrics={arm:metrics(group[group.arm.eq(arm)]) for arm in aggregate},paired=paired(group)) for name,group in f.groupby('block')}
uncertainty=paired(f)
current={arm:metrics(f[f.arm.eq(arm)&f.season.eq(2026)]) for arm in aggregate}
a,b=aggregate['incumbent_policy'],aggregate['dedicated_dst']
gates=dict(identity_scoring_cutoffs=True,mae_improvement=b['mae']<=a['mae']-.05,
    rmse=b['rmse']<=a['rmse']*1.02,current2026=current['dedicated_dst']['mae']<=current['incumbent_policy']['mae']+.1,
    bias=abs(b['bias'])<=1,coverage=.7<=b['coverage80']<=.9 and b['coverage80']>=a['coverage80']-.05,
    uncertainty=uncertainty['ci95'][1]<=.2,rank=b['weekly_rank_correlation']>=a['weekly_rank_correlation']-.1)
validation=dict(created_at=datetime.now(UTC).isoformat(),criteria_sha256=sha(P/'CRITERIA.md'),aggregate=aggregate,blocks=blocks,current2026=current,
    paired=uncertainty,gates=gates,statistical_pass=all(gates.values()),live_activation=False,prior_incumbent_exactly_reproduced=True,
    chronology=source_audit['source_chronology'])
save('validation.json',validation);save('heldout_predictions.json',rows)
print('VALIDATION',validation,flush=True)

# Full-history fit is solely for future shadow impact, never a heldout metric.
prepared=joblib.load(PREVIOUS/'prepared_incumbent.joblib')
full,label_full=select_corrected_dst_labels(prepared['train'],correction,target_season=2026,target_week=6)
full=full[full.position.eq('DST')].copy()
full_x=build_features(full,outcomes)
model,full_selection=choose_on_prior_weeks(full,full_x,TARGET)
target=prepared['target'];target=target[target.position.eq('DST')].copy()
target_x=build_features(target,outcomes)
prediction=model.predict(target_x)
ranking=pd.DataFrame(dict(player_id=target.player_id.to_numpy(),player_master_id=target.player_master_id.astype(str).to_numpy(),
    team=target.recent_team.to_numpy(),salary=target.salary.to_numpy(),incumbent=target.projection_after_scenario.to_numpy(),dedicated=prediction))
ranking['incumbent_rank']=ranking.incumbent.rank(ascending=False,method='min').astype(int)
ranking['dedicated_rank']=ranking.dedicated.rank(ascending=False,method='min').astype(int)
ranking=ranking.sort_values('dedicated_rank');ranking.to_csv(P/'sunday_defense_rankings.csv',index=False)
saved=json.loads(Path('research/sunday_hurts_refresh_20261015/v1/saved_run.json').read_text())
report=saved['params']['strategy_runtime']['highest_projection']
pool_before=pd.DataFrame(report['input_snapshot']['players']);pool=pool_before.copy(deep=True)
mask=pool.position.eq('DST');mapping=dict(zip(ranking.player_id,ranking.dedicated));pool.loc[mask,'projection']=pool.loc[mask,'player_id'].map(mapping)
assert pool.loc[mask,'projection'].notna().all()
assert pool.loc[~mask].equals(pool_before.loc[~mask])
assert pool.drop(columns='projection').equals(pool_before.drop(columns='projection'))
service=OptimizerService.__new__(OptimizerService);arms={}
with open(P/'shadow_solver.log','w') as handle,redirect_stdout(handle):
    for name,frame in [('incumbent',pool_before),('dedicated_dst_shadow',pool)]:
        lineups,audit=solve(service,frame,params=saved['params'],cutoff=datetime.fromisoformat('2026-10-15T19:17:26.763111+00:00'))
        assert audit['solver_status']=='Optimal'
        arms[name]=_json_safe(dict(lineups=lineups,audit=audit))
assert abs(arms['incumbent']['audit']['base_mean']-133.143015329788)<.001
save('matched_lineups.json',arms)
manifest=dict(version='dedicated-dst-research-v1-20261016',created_at=datetime.now(UTC).isoformat(),status='STATISTICAL_PASS_SHADOW_ONLY' if validation['statistical_pass'] else 'REJECTED_FOR_LIVE',
    live_activation=False,source_snapshot_id=receipt['snapshot_id'],source_content_sha256=receipt['content_sha256'],scoring_contract=SCORING_CONTRACT,
    training_rows=len(full),training_through='2026-W05',target='2026-W06',feature_columns=FEATURES,
    feature_hash=hashlib.sha256(json.dumps(FEATURES).encode()).hexdigest(),training_hash=training_fingerprint(full),
    full_selection=full_selection,selection_audit=label_full,criteria_sha256=sha(P/'CRITERIA.md'),
    model_parameters=str(model.get_params()),git_revision=git_revision(),
    baseline_saved_run=saved['job_id'],baseline_projection_run=saved['projection_run_id'],
    frozen_source_cutoff='2026-10-15T19:17:26.763111+00:00',non_dst_changes=0,rank_changes=int(ranking.incumbent_rank.ne(ranking.dedicated_rank).sum()),
    operational_status='Research artifact only; source chronology incomplete and serving/promotion integration not activated.',
    code_hashes={str(p):sha(p) for p in [Path(__file__),Path('backend/app/product_services/dedicated_dst_model.py'),Path('backend/app/product_services/dst_training_labels.py')]},
    source_hashes=source_audit['sources'])
joblib.dump(dict(model=model,training=full,features=full_x,target=target,target_features=target_x,metadata=manifest),P/'dedicated_dst.joblib',compress=3)
manifest['artifact_sha256']=sha(P/'dedicated_dst.joblib');save('candidate_manifest.json',manifest)
print('SHADOW',manifest['status'],'selected',full_selection['selected'],'rank changes',manifest['rank_changes'])
for arm,result in arms.items():print(arm,result['audit']['base_mean'],result['audit']['salary'],[(r['name'],r['projection']) for r in result['lineups'][0]])
