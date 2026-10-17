"""Offline candidate pipeline evaluation. No DB or serving writes."""
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
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from scipy.stats import spearmanr
from backend.app.product_services.dst_feature_pipeline import DstFeatureContext, repair_dst_frame, prepare_candidate_frames, shrunk_history_prediction, REPAIRED_COLUMNS
from backend.app.product_services.dedicated_dst_model import MARKETS, choose_on_prior_weeks
from backend.app.product_services.dst_training_labels import read_verified_correction, select_corrected_dst_labels, TARGET
from backend.app.product_services.predictions import blend_point_predictions
from backend.app.product_services.classic_highest_projection import solve
from backend.app.product_services.optimizer import OptimizerService, _json_safe
P=Path(__file__).resolve().parent;PREV=Path('research/dst_retrain_20261016/v1');S=Path('research/dst_scoring_repair_20261015/v1')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(name,data):(P/name).write_text(json.dumps(_json_safe(data),indent=2,allow_nan=False)+'\n')
def fingerprint(frame):return hashlib.sha256(frame.to_json(orient='split',double_precision=15,default_handler=str).encode()).hexdigest()
prior_manifest=json.loads(Path('research/dst_dedicated_20261016/v1/candidate_manifest.json').read_text())
ctx=DstFeatureContext.read(S/'scored_games.json',S/'canonical_dst_identity.json',expected_events_sha256=prior_manifest['source_hashes'][str(S/'scored_games.json')],expected_identities_sha256=prior_manifest['source_hashes'][str(S/'canonical_dst_identity.json')])
receipt=json.loads((S/'full_matrix_version_receipt.json').read_text());correction=read_verified_correction(receipt['artifact_path'],expected_sha256=receipt['content_sha256'])
a=joblib.load(PREV/'incumbent.joblib');original=a['train'].copy();oldcols=a['feature_columns']
fixed,label_audit=select_corrected_dst_labels(original,correction,target_season=2026,target_week=6)
repaired,_,pipeline_audit=prepare_candidate_frames(fixed,fixed,ctx)
for frame in [original,fixed,repaired]:frame['period']=frame.season*100+frame.week
mask=fixed.position.eq('DST');assert mask.sum()==804
assert original.loc[~mask,oldcols].equals(repaired.loc[~mask,oldcols])
dedcols=[*MARKETS,*[c for c in REPAIRED_COLUMNS if c!='game_id']]
assert len(dedcols)==14 and not any('qb' in c.lower() for c in dedcols)
features_audit=dict(label_selection=label_audit,pipeline=pipeline_audit,all_offense_cells_unchanged=True,
    home_ones=int(repaired.loc[mask,'is_home'].sum()),history_nonzero=int(repaired.loc[mask,'player_games_history'].gt(0).sum()),
    repaired_training_features_sha256=fingerprint(repaired[oldcols]),dedicated_columns=dedcols,
    repaired_columns=REPAIRED_COLUMNS,source_sha256=ctx.source_sha256,identities_sha256=ctx.identities_sha256,
    chronology=ctx.chronology,criteria_sha256=sha(P/'CRITERIA.md'))
save('pipeline_audit.json',features_audit)
rows=[];inner=[];offense=[]
for calstart,teststart,testend in [(202414,202501,202599),(202515,202601,202605)]:
    t0=original[original.period<calstart];tf=fixed[fixed.period<calstart];tr=repaired[repaired.period<calstart]
    cal=repaired[(repaired.period>=calstart)&(repaired.period<teststart)&repaired.position.eq('DST')]
    test=repaired[(repaired.period>=teststart)&(repaired.period<=testend)&repaired.position.eq('DST')]
    models={}
    for name,train in [('incumbent',t0),('corrected_shared',tf)]:
        models[name]=clone(a['model']).fit(train[oldcols].apply(pd.to_numeric,errors='coerce').fillna(0),train[TARGET])
    models['repaired_shared']=Pipeline([('missing',SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)),('model',clone(a['model']))]).fit(tr[oldcols],tr[TARGET])
    dst_train=tr[tr.position.eq('DST')]
    models['repaired_dedicated'],selection=choose_on_prior_weeks(dst_train,dst_train[dedcols],TARGET)
    inner.append(dict(calstart=calstart,**selection))
    def predict(name,frame):
        if name=='history_baseline':return shrunk_history_prediction(frame,ctx)
        if name=='repaired_dedicated':return models[name].predict(frame[dedcols])
        if name=='repaired_shared':return blend_point_predictions(models[name].predict(frame[oldcols]),tr,frame)
        train=t0 if name=='incumbent' else tf
        frozen=original.loc[frame.index] if name=='incumbent' else fixed.loc[frame.index]
        return blend_point_predictions(models[name].predict(frozen[oldcols].apply(pd.to_numeric,errors='coerce').fillna(0)),train,frozen)
    for name in ['incumbent','corrected_shared','repaired_shared','repaired_dedicated','history_baseline']:
        cp=predict(name,cal);tp=predict(name,test);assert np.isfinite(cp).all() and np.isfinite(tp).all()
        lo,hi=np.quantile(cal[TARGET].to_numpy()-cp,[.1,.9])
        for r,p in zip(test.to_dict('records'),tp):
            block='2025_retrospective' if r['season']==2025 else ('2026_w1_3_retrospective' if r['week']<=3 else '2026_w4_5_inspected')
            rows.append(dict(arm=name,block=block,season=int(r['season']),week=int(r['week']),team=r['team'],player_master_id=str(r['player_master_id']),matrix_id=int(r['player_game_feature_matrix_id']),actual=float(r[TARGET]),prediction=float(p),low80=float(p+lo),high80=float(p+hi),covered=bool(p+lo<=r[TARGET]<=p+hi)))
    ot=repaired[(repaired.period>=teststart)&(repaired.period<=testend)&~repaired.position.eq('DST')]
    old=predict('incumbent',ot);new=predict('repaired_shared',ot)
    for position,group in ot.groupby('position'):
        indices=ot.index.get_indexer(group.index);truth=group[TARGET].to_numpy()
        offense.append(dict(test_start=teststart,position=position,n=len(group),incumbent_mae=float(abs(old[indices]-truth).mean()),repaired_shared_mae=float(abs(new[indices]-truth).mean())))
    offense.append(dict(test_start=teststart,position='ALL',n=len(ot),incumbent_mae=float(abs(old-ot[TARGET]).mean()),repaired_shared_mae=float(abs(new-ot[TARGET]).mean())))
f=pd.DataFrame(rows)
previous=pd.DataFrame(json.loads((PREV/'heldout_predictions.json').read_text()))
for current,oldname in [('incumbent','incumbent_policy'),('corrected_shared','corrected_labels')]:
    before=previous[previous.arm.eq(oldname)].set_index('matrix_id').sort_index();now=f[f.arm.eq(current)].set_index('matrix_id').sort_index()
    assert before.index.equals(now.index) and np.max(abs(before.prediction-now.prediction))<1e-10 and np.max(abs(before.actual-now.actual))==0

def metrics(g):
    e=g.prediction-g.actual;ranks=[]
    for _,week in g.groupby(['season','week']):ranks.append(float(spearmanr(week.prediction,week.actual).statistic) if week.prediction.nunique()>1 and week.actual.nunique()>1 else 0.)
    bins=[dict(bin=str(interval),n=len(x),mean_prediction=float(x.prediction.mean()),mean_actual=float(x.actual.mean())) for interval,x in g.groupby(pd.cut(g.prediction,[-np.inf,4,6,8,10,np.inf]),observed=True)]
    return dict(n=len(g),mae=float(abs(e).mean()),rmse=float(np.sqrt((e**2).mean())),bias=float(e.mean()),coverage80=float(g.covered.mean()),width80=float((g.high80-g.low80).mean()),weekly_rank_correlation=float(np.mean(ranks)),week_clusters=len(ranks),calibration_bins=bins)
def paired(g,arm,baseline):
    w=g.pivot(index=['season','week','team'],columns='arm',values='prediction');truth=g.drop_duplicates(['season','week','team']).set_index(['season','week','team']).actual
    d=abs(w[arm]-truth)-abs(w[baseline]-truth);clusters=d.groupby(level=['season','week']).agg(['sum','size']);rng=np.random.default_rng(261016);boot=[]
    for _ in range(3000):
        sample=clusters.iloc[rng.integers(0,len(clusters),len(clusters))];boot.append(float(sample['sum'].sum()/sample['size'].sum()))
    return dict(mae_difference=float(d.mean()),ci95=list(map(float,np.quantile(boot,[.025,.975]))),weeks=len(clusters))
arms=list(f.arm.unique());agg={arm:metrics(f[f.arm.eq(arm)]) for arm in arms};current={arm:metrics(f[f.arm.eq(arm)&f.season.eq(2026)]) for arm in arms}
blocks={name:{arm:metrics(group[group.arm.eq(arm)]) for arm in arms} for name,group in f.groupby('block')}
uncertainty={arm:dict(vs_corrected_shared=paired(f,arm,'corrected_shared'),vs_incumbent=paired(f,arm,'incumbent'),blocks={name:paired(group,arm,'corrected_shared') for name,group in f.groupby('block')}) for arm in arms if arm not in ['incumbent','corrected_shared']}
gates={}
for arm in uncertainty:
    old,control,new=agg['incumbent'],agg['corrected_shared'],agg[arm]
    gates[arm]=dict(source_parity=True,mae_improves_corrected=new['mae']<=control['mae']-.05,mae_incumbent_noninferior=new['mae']<=old['mae']+.05,rmse=new['rmse']<=old['rmse']*1.02,current2026=current[arm]['mae']<=current['incumbent']['mae']+.10,bias=abs(new['bias'])<=1,coverage=.7<=new['coverage80']<=.9 and new['coverage80']>=old['coverage80']-.05,uncertainty=uncertainty[arm]['vs_corrected_shared']['ci95'][1]<=.2,rank=new['weekly_rank_correlation']>=old['weekly_rank_correlation']-.1)
validation=dict(created_at=datetime.now(UTC).isoformat(),criteria_sha256=sha(P/'CRITERIA.md'),aggregate=agg,current2026=current,blocks=blocks,uncertainty=uncertainty,gates=gates,passed={arm:all(g.values()) for arm,g in gates.items()},offense=offense,original_and_corrected_shared_exactly_reproduced=True,live_activation=False,chronology=ctx.chronology)
save('validation.json',validation);save('heldout_predictions.json',rows);save('inner_selection.json',inner)
print('AGGREGATE',agg,flush=True);print('GATES',gates,flush=True)

# Future impact only: same model definitions refitted after the validation is complete.
prepared=joblib.load(PREV/'prepared_incumbent.joblib');full,_=select_corrected_dst_labels(prepared['train'],correction,target_season=2026,target_week=6)
full,target,parity=prepare_candidate_frames(full,prepared['target'],ctx)
dst=full[full.position.eq('DST')];targets=target[target.position.eq('DST')]
models={}
models['repaired_shared']=Pipeline([('missing',SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)),('model',clone(a['model']))]).fit(full[oldcols],full[TARGET])
models['repaired_dedicated'],choice=choose_on_prior_weeks(dst,dst[dedcols],TARGET)
future=dict(repaired_shared=blend_point_predictions(models['repaired_shared'].predict(targets[oldcols]),full,targets),repaired_dedicated=models['repaired_dedicated'].predict(targets[dedcols]),history_baseline=shrunk_history_prediction(targets,ctx))
ranking=pd.DataFrame(dict(player_id=targets.player_id.to_numpy(),team=targets.recent_team.to_numpy(),salary=targets.salary.to_numpy(),incumbent=targets.projection_after_scenario.to_numpy(),**future))
for arm in ['incumbent',*future]:ranking[f'{arm}_rank']=ranking[arm].rank(ascending=False,method='min').astype(int)
ranking.to_csv(P/'sunday_defense_rankings.csv',index=False)
saved=json.loads(Path('research/sunday_hurts_refresh_20261015/v1/saved_run.json').read_text());pool0=pd.DataFrame(saved['params']['strategy_runtime']['highest_projection']['input_snapshot']['players']);solver={};service=OptimizerService.__new__(OptimizerService)
with open(P/'solver.log','w') as handle,redirect_stdout(handle):
    for arm in ['incumbent',*future]:
        pool=pool0.copy(deep=True);m=pool.position.eq('DST')
        if arm!='incumbent':pool.loc[m,'projection']=pool.loc[m,'player_id'].map(dict(zip(ranking.player_id,ranking[arm])))
        assert pool.loc[~m].equals(pool0.loc[~m]) and pool.drop(columns='projection').equals(pool0.drop(columns='projection'))
        lineups,audit=solve(service,pool,params=saved['params'],cutoff=datetime.fromisoformat('2026-10-15T19:17:26.763111+00:00'))
        assert audit['solver_status']=='Optimal' and not audit['constraints_relaxed']
        solver[arm]=dict(lineups=lineups,audit=audit)
save('matched_lineups.json',solver)
manifest=dict(created_at=datetime.now(UTC).isoformat(),version='dst_feature_pipeline_candidate_v1',criteria_sha256=sha(P/'CRITERIA.md'),source_snapshot_id=receipt['snapshot_id'],scoring_contract=correction['contract_id'],label_source_sha256=receipt['content_sha256'],events_sha256=ctx.source_sha256,identities_sha256=ctx.identities_sha256,full_dedicated_selection=choice,feature_columns=oldcols,dedicated_columns=dedcols,training_features_sha256=fingerprint(full[oldcols]),target_features_sha256=fingerprint(target[oldcols]),training_rows=len(full),dst_training_rows=len(dst),parity_audit=parity,passed=validation['passed'],live_activation=False,shadow_saved_run=saved['job_id'],shadow_projection_run=saved['projection_run_id'],non_dst_cell_changes=0,rank_changes={arm:int(ranking[f'{arm}_rank'].ne(ranking.incumbent_rank).sum()) for arm in future},environment=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,sklearn=sklearn.__version__),code_sha256={str(path):sha(path) for path in [Path(__file__),Path('backend/app/product_services/dst_feature_pipeline.py'),Path('backend/app/services/lineup_learning.py'),Path('backend/app/product_services/canonical_projection_inputs.py'),Path('backend/app/product_services/dedicated_dst_model.py')]})
joblib.dump(dict(models=models,training=full,target=target,context=ctx,metadata=manifest),P/'candidate_models.joblib',compress=3);manifest['artifact_sha256']=sha(P/'candidate_models.joblib');save('candidate_manifest.json',manifest)
print('FULL SELECTION',choice,flush=True);print('SHADOW',[(arm,rows['audit']['base_mean'],rows['audit']['salary'],[(r['name'],r['projection']) for r in rows['lineups'][0]]) for arm,rows in solver.items()],flush=True)
