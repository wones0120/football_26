"""Bounded rolling DST ranking investigation; local research writes only."""
from pathlib import Path
from datetime import datetime, UTC
from contextlib import redirect_stdout
import hashlib
import json
import platform
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from backend.app.product_services.dst_rank_policy import fit_policies, rank_metrics
from backend.app.product_services.dst_feature_pipeline import prepare_candidate_frames
from backend.app.product_services.dst_training_labels import read_verified_correction, select_corrected_dst_labels, TARGET
from backend.app.product_services.predictions import blend_point_predictions
from backend.app.product_services.classic_highest_projection import solve
from backend.app.product_services.optimizer import OptimizerService, _json_safe
P=Path(__file__).resolve().parent;OLD=Path('research/dst_retrain_20261016/v1');PIPE=Path('research/dst_pipeline_repair_20261016/v1');S=Path('research/dst_scoring_repair_20261015/v1')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(name,data):(P/name).write_text(json.dumps(_json_safe(data),indent=2,allow_nan=False)+'\n')
def fingerprint(frame):return hashlib.sha256(frame.to_json(orient='split',double_precision=15,default_handler=str).encode()).hexdigest()
bundle=joblib.load(PIPE/'candidate_models.joblib');ctx=bundle['context'];columns=bundle['metadata']['dedicated_columns'];inc=joblib.load(OLD/'incumbent.joblib');original=inc['train'].copy();inc_cols=inc['feature_columns']
receipt=json.loads((S/'full_matrix_version_receipt.json').read_text());correction=read_verified_correction(receipt['artifact_path'],expected_sha256=receipt['content_sha256'])
fixed,label_audit=select_corrected_dst_labels(original,correction,target_season=2026,target_week=6);repaired,_,audit=prepare_candidate_frames(fixed,fixed,ctx)
for frame in [original,repaired]:frame['period']=frame.season*100+frame.week
assert repaired.position.eq('DST').sum()==804
assert not any('qb' in c.lower() for c in columns)
ARMS=['incumbent','flat','existing_mae_policy','ensemble','rank_selector']
rows=[];inner=[];fit_count=0

def run_origin(test_period,*,reference=False):
    global fit_count
    previous=repaired[repaired.position.eq('DST') & (repaired.period<test_period)]
    cal_periods=sorted(previous.period.unique())[-3:]
    fit_cutoff=202414 if reference else min(cal_periods)
    train=repaired[repaired.position.eq('DST') & (repaired.period<fit_cutoff)]
    cal=repaired[repaired.position.eq('DST') & (repaired.period>=fit_cutoff) & (repaired.period<test_period)]
    test=repaired[repaired.position.eq('DST') & (repaired.season.eq(2025) if reference else repaired.period.eq(test_period))]
    policies=fit_policies(train,columns,target=TARGET);fit_count+=4
    inner.append(dict(origin='2025_reference' if reference else int(test_period),fit_cutoff=int(fit_cutoff),calibration_periods=sorted(map(int,cal.period.unique())),calibration_n=len(cal),test_n=len(test),**policies.audit))
    if reference:
        old_rows=pd.DataFrame(json.loads((OLD/'heldout_predictions.json').read_text()));lookup=old_rows[old_rows.arm.eq('incumbent_policy') & old_rows.season.eq(2025)].set_index('matrix_id')
        assert set(lookup.index)==set(test.player_game_feature_matrix_id)
        # Reuse exact prior chronological incumbent predictions/interval evidence.
        old_metrics=json.loads((OLD/'validation.json').read_text());block=next(x for x in old_metrics['metrics'] if x['arm']=='incumbent_policy' and x['block']=='2025_retrospective')
        old_predictions=lookup.loc[test.player_game_feature_matrix_id,'prediction'].to_numpy()
        prior_rows=pd.DataFrame(json.loads((PIPE/'heldout_predictions.json').read_text()));prior_rows=prior_rows[prior_rows.arm.eq('incumbent') & prior_rows.season.eq(2025)].set_index('matrix_id')
    else:
        itrain=original[original.period<fit_cutoff];model=clone(inc['model']).fit(itrain[inc_cols].apply(pd.to_numeric,errors='coerce').fillna(0),itrain[TARGET]);fit_count+=1
        def incumbent_predict(frame):
            frozen=original.loc[frame.index]
            raw=model.predict(frozen[inc_cols].apply(pd.to_numeric,errors='coerce').fillna(0))
            return blend_point_predictions(raw,itrain,frozen)
        cp=incumbent_predict(cal);old_predictions=incumbent_predict(test);old_q=np.quantile(cal[TARGET].to_numpy()-cp,[.1,.9])
    predictions={name:policies.predict(test,policy='median' if name=='flat' else name) for name in ARMS if name!='incumbent'}
    predictions['incumbent']=old_predictions
    for arm in ARMS:
        if arm=='incumbent' and reference:
            low=prior_rows.loc[test.player_game_feature_matrix_id,'low80'].to_numpy();high=prior_rows.loc[test.player_game_feature_matrix_id,'high80'].to_numpy()
        else:
            if arm=='incumbent':q=old_q
            else:
                cp=policies.predict(cal,policy='median' if arm=='flat' else arm)
                q=np.quantile(cal[TARGET].to_numpy()-cp,[.1,.9])
            low=predictions[arm]+q[0];high=predictions[arm]+q[1]
        assert np.isfinite(predictions[arm]).all()
        for r,p,lo,hi in zip(test.to_dict('records'),predictions[arm],low,high):
            rows.append(dict(block='2025_reference' if reference else '2026_recent_rolling',arm=arm,season=int(r['season']),week=int(r['week']),team=r['team'],player_master_id=str(r['player_master_id']),matrix_id=int(r['player_game_feature_matrix_id']),actual=float(r[TARGET]),prediction=float(p),low80=float(lo),high80=float(hi),covered=bool(lo<=r[TARGET]<=hi)))
    return policies

run_origin(202501,reference=True)
for week in range(1,6):run_origin(202600+week)
f=pd.DataFrame(rows)
assert len(f)==446*len(ARMS)
week_rows=[]
for (block,season,week,arm),g in f.groupby(['block','season','week','arm']):
    e=g.prediction-g.actual
    week_rows.append(dict(block=block,season=int(season),week=int(week),arm=arm,supported=len(g)>=10,**rank_metrics(g.actual,g.prediction),mae=float(abs(e).mean()),rmse=float(np.sqrt((e**2).mean())),bias=float(e.mean()),coverage80=float(g.covered.mean())))
w=pd.DataFrame(week_rows)

def metrics(frame):
    e=frame.prediction-frame.actual
    supported=w[w.arm.eq(frame.arm.iloc[0]) & w.block.eq(frame.block.iloc[0]) & w.supported]
    bins=[dict(bin=str(interval),n=len(g),mean_prediction=float(g.prediction.mean()),mean_actual=float(g.actual.mean())) for interval,g in frame.groupby(pd.cut(frame.prediction,[-np.inf,4,6,8,10,np.inf]),observed=True)]
    return dict(n=len(frame),mae=float(abs(e).mean()),rmse=float(np.sqrt((e**2).mean())),bias=float(e.mean()),coverage80=float(frame.covered.mean()),width80=float((frame.high80-frame.low80).mean()),supported_weeks=len(supported),pairwise_accuracy=float(supported.pairwise_accuracy.mean()),spearman=float(supported.spearman.mean()),top5_actual=float(supported.top5_actual.mean()),top5_regret=float(supported.top5_regret.mean()),calibration_bins=bins)
summary={block:{arm:metrics(g[g.arm.eq(arm)]) for arm in ARMS} for block,g in f.groupby('block')}

def paired_rank(block,arm,baseline,metric):
    subset=w[w.block.eq(block) & w.supported];wide=subset.pivot(index=['season','week'],columns='arm',values=metric);difference=wide[arm]-wide[baseline];rng=np.random.default_rng(261016)
    boot=[float(difference.iloc[rng.integers(0,len(difference),len(difference))].mean()) for _ in range(3000)]
    return dict(mean_difference=float(difference.mean()),ci95=list(map(float,np.quantile(boot,[.025,.975]))),weeks=len(difference),improved=int((difference>1e-12).sum()) if metric!='top5_regret' else int((difference< -1e-12).sum()),worsened=int((difference< -1e-12).sum()) if metric!='top5_regret' else int((difference>1e-12).sum()),tied=int((abs(difference)<=1e-12).sum()))
uncertainty={arm:{baseline:{metric:paired_rank('2026_recent_rolling',arm,baseline,metric) for metric in ['pairwise_accuracy','spearman','top5_regret']} for baseline in ['incumbent','flat']} for arm in ['existing_mae_policy','ensemble','rank_selector']}
gates={}
for arm in ['ensemble','rank_selector']:
    recent=summary['2026_recent_rolling'];reference=summary['2025_reference'];candidate=recent[arm];baseline=recent['incumbent'];u=uncertainty[arm]
    gates[arm]=dict(source_parity=True,pairwise_level=candidate['pairwise_accuracy']>=.55 and candidate['pairwise_accuracy']>=baseline['pairwise_accuracy']+.02,
        pairwise_uncertainty=u['incumbent']['pairwise_accuracy']['ci95'][0]>0 and u['flat']['pairwise_accuracy']['ci95'][0]>0,
        consistency=u['incumbent']['pairwise_accuracy']['improved']>=4,top5_regret=candidate['top5_regret']<=baseline['top5_regret']-.25,
        mae=candidate['mae']<=baseline['mae']+.15,rmse=candidate['rmse']<=baseline['rmse']*1.03,bias=abs(candidate['bias'])<=1,
        coverage=.7<=candidate['coverage80']<=.9 and candidate['coverage80']>=baseline['coverage80']-.05,
        historical_consistency=reference[arm]['pairwise_accuracy']>=reference['incumbent']['pairwise_accuracy']-.02 and reference[arm]['mae']<=reference['incumbent']['mae']+.15)
validation=dict(created_at=datetime.now(UTC).isoformat(),criteria_sha256=sha(P/'CRITERIA.md'),summary=summary,uncertainty=uncertainty,gates=gates,passed={arm:all(g.values()) for arm,g in gates.items()},chronology=ctx.chronology,previously_inspected_outcomes=True,live_activation=False)
save('validation.json',validation);save('row_predictions.json',rows);save('weekly_metrics.json',week_rows);save('selection_audits.json',inner)
print('SUMMARY',summary,flush=True);print('GATES',gates,flush=True)

# Full-history future shadow follows the frozen policy; it is never validation.
full=bundle['training'];dst=full[full.position.eq('DST')];target=bundle['target'];targets=target[target.position.eq('DST')]
policies=fit_policies(dst,columns,target=TARGET);fit_count+=4
future={arm:policies.predict(targets,policy='median' if arm=='flat' else arm) for arm in ARMS if arm!='incumbent'}
ranking=pd.DataFrame(dict(player_id=targets.player_id.to_numpy(),team=targets.recent_team.to_numpy(),salary=targets.salary.to_numpy(),incumbent=targets.projection_after_scenario.to_numpy(),**future))
for arm in ARMS:ranking[arm+'_rank']=ranking[arm].rank(ascending=False,method='min').astype(int)
ranking.to_csv(P/'sunday_defense_rankings.csv',index=False)
saved=json.loads(Path('research/sunday_hurts_refresh_20261015/v1/saved_run.json').read_text());pool0=pd.DataFrame(saved['params']['strategy_runtime']['highest_projection']['input_snapshot']['players']);service=OptimizerService.__new__(OptimizerService);solver={}
with open(P/'solver.log','w') as handle,redirect_stdout(handle):
    for arm in ARMS:
        pool=pool0.copy(deep=True);mask=pool.position.eq('DST')
        if arm!='incumbent':pool.loc[mask,'projection']=pool.loc[mask,'player_id'].map(dict(zip(ranking.player_id,ranking[arm])))
        assert pool.loc[~mask].equals(pool0.loc[~mask]) and pool.drop(columns='projection').equals(pool0.drop(columns='projection'))
        lineups,audit=solve(service,pool,params=saved['params'],cutoff=datetime.fromisoformat('2026-10-15T19:17:26.763111+00:00'))
        assert audit['solver_status']=='Optimal' and not audit['constraints_relaxed']
        solver[arm]=dict(lineups=lineups,audit=audit)
save('matched_lineups.json',solver)
assert fit_count<=45
manifest=dict(version='dst_rank_stability_research_v1',created_at=datetime.now(UTC).isoformat(),criteria_sha256=sha(P/'CRITERIA.md'),fit_count=fit_count,columns=columns,source_hashes=dict(events=ctx.source_sha256,identities=ctx.identities_sha256,labels=receipt['content_sha256']),training_features_sha256=fingerprint(dst[columns]),target_features_sha256=fingerprint(targets[columns]),full_selection=policies.audit,passed=validation['passed'],live_activation=False,source_snapshot_id=receipt['snapshot_id'],scoring_contract=correction['contract_id'],chronology=ctx.chronology,shadow_saved_run=saved['job_id'],shadow_projection_run=saved['projection_run_id'],non_dst_cells_changed=0,rank_changes={arm:int(ranking[arm+'_rank'].ne(ranking.incumbent_rank).sum()) for arm in future},environment=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,sklearn=sklearn.__version__),code_sha256={str(path):sha(path) for path in [Path(__file__),Path('backend/app/product_services/dst_rank_policy.py'),Path('backend/app/product_services/dst_feature_pipeline.py'),Path('backend/app/product_services/dedicated_dst_model.py')]})
joblib.dump(dict(policies=policies,context=ctx,training=dst,target=targets,metadata=manifest),P/'ranking_candidate.joblib',compress=3);manifest['artifact_sha256']=sha(P/'ranking_candidate.joblib');save('candidate_manifest.json',manifest)
print('FITS',fit_count,'FULL SELECTION',policies.audit,flush=True);print('SHADOW',[(arm,x['audit']['base_mean'],x['audit']['salary'],[(r['name'],r['projection']) for r in x['lineups'][0]]) for arm,x in solver.items()],flush=True)
