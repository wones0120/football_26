"""Two bounded identical prefix refits diagnose inner-loss instability, not tuning."""
from pathlib import Path
import json
import joblib
import numpy as np
from backend.app.product_services.dedicated_dst_model import learner
from backend.app.product_services.dst_rank_policy import combine_predictions, rank_metrics
P=Path(__file__).resolve().parent
bundle=joblib.load(P/'ranking_candidate.joblib');frame=bundle['training'];columns=bundle['policies'].columns
period=frame.season*100+frame.week;first=sorted(period.unique())[-3];prefix=frame[period<first];validation=frame[period>=first];target='label_dk_total_points'
models={name:learner(name).fit(prefix[columns],prefix[target]) for name in ['ridge','regularized_tree']}
predictions=combine_predictions(float(prefix[target].median()),models['ridge'].predict(validation[columns]),models['regularized_tree'].predict(validation[columns]))
weekly=[];rows=[];paired={}
for name,forecast in predictions.items():
    for (season,week),indices in validation.groupby(['season','week']).indices.items():
        group=validation.iloc[indices];error=forecast[indices]-group[target].to_numpy()
        weekly.append(dict(model=name,season=int(season),week=int(week),mae=float(abs(error).mean()),**rank_metrics(group[target],forecast[indices])))
    for record,prediction in zip(validation.to_dict('records'),forecast):
        rows.append(dict(model=name,season=int(record['season']),week=int(record['week']),player_master_id=str(record['player_master_id']),actual=float(record[target]),prediction=float(prediction)))
for name in ['ridge','regularized_tree','ensemble']:
    difference=abs(predictions[name]-validation[target].to_numpy())-abs(predictions['median']-validation[target].to_numpy())
    groups=[]
    for _,indices in validation.groupby(['season','week']).indices.items():groups.append([float(difference[indices].sum()),len(indices)])
    groups=np.asarray(groups,float);rng=np.random.default_rng(261016);samples=[]
    for _ in range(3000):
        drawn=groups[rng.integers(0,len(groups),len(groups))];samples.append(float(drawn[:,0].sum()/drawn[:,1].sum()))
    paired[name]=dict(mae_difference_vs_median=float(difference.mean()),ci95=list(map(float,np.quantile(samples,[.025,.975]))),week_clusters=len(groups))
full_forecasts=bundle['policies'].predictions(bundle['target'])
future_dispersion={name:dict(min=float(values.min()),max=float(values.max()),std=float(values.std()),distinct=len(np.unique(values))) for name,values in full_forecasts.items()}
(P/'inner_loss_diagnostics.json').write_text(json.dumps(dict(diagnostic_fits=4,total_experiment_fits=37,prefix_n=len(prefix),inner_n=len(validation),weekly=weekly,paired=paired,future_dispersion=future_dispersion,note='Exact original prefix/models replayed only for diagnosis; no selection,parameter,weight or outcome gate changed.'),indent=2)+'\n')
(P/'inner_row_predictions.json').write_text(json.dumps(rows,indent=2)+'\n')
print('Inner paired MAE',paired)
