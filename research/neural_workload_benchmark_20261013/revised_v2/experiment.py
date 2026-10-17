"""Revised-data retrospective workload/PPR benchmark; offline and isolated."""
from __future__ import annotations
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import argparse, ast, gzip, hashlib, json, signal, time, warnings
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SOURCE=ROOT/'artifacts/classic_opportunity_repair/weekly_stats.json.gz'
SEED=261013
TARGETS=['targets','carries','fantasy_points_ppr']
BASE=['targets_mean3','carries_mean3','fantasy_points_ppr_mean3','targets_last','carries_last',
      'fantasy_points_ppr_last','targets_trend','carries_trend','target_share','carry_share',
      'team_targets_mean3','team_carries_mean3','history_count','weeks_since_last']
PRODUCTION=['receptions','receiving_yards','receiving_tds','rushing_yards','rushing_tds',
            'attempts','passing_yards','passing_tds','passing_interceptions','receiving_air_yards']
EXTRA=[x+'_mean3' for x in PRODUCTION]+['catch_rate','receiving_yards_per_target','rushing_yards_per_carry',
       'passing_yards_per_attempt','team_attempts_mean3','team_pass_fraction_proxy',
       'opponent_position_ppr_mean3','opponent_position_targets_mean3','opponent_position_carries_mean3']
VARIANTS={'baseline':BASE,'enriched':BASE+EXTRA}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def number(value):
    try:return float(value) if value is not None and np.isfinite(float(value)) else np.nan
    except (ValueError,TypeError):return np.nan

def team(value):return {'LA':'LAR','SD':'LAC','OAK':'LV'}.get(value,value)
def period(row):return int(row['season']),int(row['week'])
def mean(rows,key):
    vals=[number(r.get(key)) for r in rows]
    vals=[v for v in vals if np.isfinite(v)]
    return float(np.mean(vals)) if vals else np.nan

def ratio(rows,numerator,denominator):
    pairs=[(number(r.get(numerator)),number(r.get(denominator))) for r in rows]
    pairs=[(n,d) for n,d in pairs if np.isfinite(n) and np.isfinite(d)]
    denominator_total=sum(d for _,d in pairs)
    return sum(n for n,_ in pairs)/denominator_total if denominator_total>0 else np.nan


def normalized_rows(raw):
    selected={};ids=defaultdict(set);rejected=Counter()
    for r in raw:
        if r['season'] not in (2023,2024,2025) or r['position'] not in {'QB','RB','WR','TE'} or r['raw_row_json'].get('season_type')!='REG':continue
        if r.get('player_master_id'):ids[r['source_player_id']].add(r['player_master_id'])
    for r in raw:
        if r['season'] not in (2023,2024,2025) or r['position'] not in {'QB','RB','WR','TE'} or r['raw_row_json'].get('season_type')!='REG':continue
        if not r.get('player_master_id') or len(ids[r['source_player_id']])!=1:
            rejected['unresolved_or_ambiguous_native_identity']+=1;continue
        v=r['raw_row_json']
        source_team=v.get('team',v.get('recent_team'))
        if team(source_team)!=team(r['team']):rejected['team_mismatch']+=1;continue
        k=(r['player_master_id'],r['season'],r['week'])
        version=(r['created_at'],r['raw_nfl_weekly_stat_id'])
        if k in selected and version<=selected[k][0]:continue
        row=dict(player_master_id=r['player_master_id'],source_player_id=r['source_player_id'],
                 raw_source_id=r['raw_nfl_weekly_stat_id'],source_imported_at=r['created_at'],
                 season=r['season'],week=r['week'],team=team(r['team']),position=r['position'],
                 opponent=team(v.get('opponent_team')),game_id=v.get('game_id'),
                 name=v.get('player_display_name') or v.get('player_name') or r['source_player_id'])
        for key in TARGETS+PRODUCTION:row[key]=number(v.get(key))
        # Source extracted workload fields remain authoritative, preserve NaN instead of fill.
        row['targets']=number(r['targets']);row['carries']=number(r['carries'])
        selected[k]=(version,row)
    return sorted((r for _,r in selected.values()),key=lambda r:(period(r),r['player_master_id'])),dict(rejected)


def build_matrix(rows):
    """Append ALL source histories only after completing each week’s features."""
    player_hist=defaultdict(list);team_hist=defaultdict(list);opponent_hist=defaultdict(list)
    blocks=defaultdict(list)
    for r in rows:blocks[period(r)].append(r)
    matrix=[]
    for block in sorted(blocks):
        current=blocks[block]
        for r in current:
            h=player_hist[r['player_master_id']][-3:]
            historical_team=h[-1]['team'] if h else None
            th=team_hist[historical_team][-3:] if historical_team else []
            oh=opponent_hist[(r['opponent'],r['position'])][-3:]
            prior=[*h,*th,*oh]
            assert all(period(q)<block for q in prior),'Same/future-week source reached features'
            out={key:r[key] for key in ['player_master_id','source_player_id','raw_source_id','source_imported_at','season','week','team','opponent','position','game_id','name',*TARGETS]}
            out['history_count']=len(player_hist[r['player_master_id']])
            out['weeks_since_last']=(r['season']-h[-1]['season'])*52+r['week']-h[-1]['week'] if h else np.nan
            out['prior_team']=historical_team
            out['team_changed_diagnostic']=bool(h and r['team']!=historical_team)
            out['max_source_season']=max((q['season'] for q in prior),default=None)
            out['max_source_week']=max((q['week'] for q in prior if q['season']==out['max_source_season']),default=None)
            out['source_ids_json']=json.dumps(sorted({int(i) for q in prior for i in q.get('source_ids',[q.get('raw_source_id')]) if i is not None}))
            for key in TARGETS:
                out[key+'_mean3']=mean(h,key)
                out[key+'_last']=number(h[-1].get(key)) if h else np.nan
            for key in ['targets','carries']:out[key+'_trend']=out[key+'_last']-out[key+'_mean3']
            for key in ['targets','carries','attempts']:out['team_'+key+'_mean3']=mean(th,key)
            for key,share in [('targets','target_share'),('carries','carry_share')]:
                # Player workload share is observed in each prior player's actual game/team.
                out[share]=mean(h,share)
            for key in PRODUCTION:out[key+'_mean3']=mean(h,key)
            for key,n,d in [('catch_rate','receptions','targets'),('receiving_yards_per_target','receiving_yards','targets'),
                            ('rushing_yards_per_carry','rushing_yards','carries'),('passing_yards_per_attempt','passing_yards','attempts')]:out[key]=ratio(h,n,d)
            attempts=out['team_attempts_mean3'];carries=out['team_carries_mean3']
            out['team_pass_fraction_proxy']=attempts/(attempts+carries) if attempts+carries>0 else np.nan
            for key,label in [('fantasy_points_ppr','ppr'),('targets','targets'),('carries','carries')]:out['opponent_position_'+label+'_mean3']=mean(oh,key)
            out['split']='test' if block==(2025,18) else 'validation' if block[0]==2025 and 13<=block[1]<=17 else 'train'
            matrix.append(out)
        # Group aggregates are from completed previous blocks only for future predictions.
        tg=defaultdict(list);og=defaultdict(list)
        for r in current:
            tg[r['team']].append(r);og[(r['opponent'],r['position'])].append(r)
        for club,members in tg.items():
            aggregate=dict(season=block[0],week=block[1],source_ids=[m['raw_source_id'] for m in members])
            for key in TARGETS+['attempts']:
                v=[m[key] for m in members if np.isfinite(m[key])]
                aggregate[key]=sum(v) if v else np.nan
            team_hist[club].append(aggregate)
            for m in members:
                for key,share in [('targets','target_share'),('carries','carry_share')]:
                    m[share]=m[key]/aggregate[key] if aggregate[key]>0 else np.nan
        for key,members in og.items():
            aggregate=dict(season=block[0],week=block[1],source_ids=[m['raw_source_id'] for m in members])
            for label in TARGETS:
                vals=[m[label] for m in members if np.isfinite(m[label])]
                aggregate[label]=sum(vals) if vals else np.nan
            opponent_hist[key].append(aggregate)
        for r in current:player_hist[r['player_master_id']].append(r)
    return pd.DataFrame(matrix)


def frame_hash(frame,columns):return hashlib.sha256(frame[columns].to_csv(index=False,float_format='%.10g').encode()).hexdigest()

def prepare():
    started=time.perf_counter()
    with gzip.open(SOURCE,'rt') as f:raw=json.load(f)
    rows,rejected=normalized_rows(raw)
    coverage=Counter(period(r) for r in rows)
    chosen=max(block for block,n in coverage.items() if block[0]<2026 and block[1]==18 and n>=200)
    if chosen!=(2025,18):raise ValueError('Coverage changed: new specification required before scoring')
    matrix=build_matrix(rows)
    matrix.to_csv(HERE/'feature_matrix.csv',index=False,float_format='%.10g')
    coverage_report={'retrospective_revised_data':True,'test_week':list(chosen),'rejected':rejected,
        'rows':len(matrix),'sample_counts':matrix.groupby('split').size().to_dict(),
        'weeks':{s:sorted(set(zip(g.season.astype(int),g.week.astype(int)))) for s,g in matrix.groupby('split')},
        'coverage':{key:float(matrix[key].notna().mean()) for key in BASE+EXTRA},
        'observed_zeros':{t:int((matrix[t]==0).sum()) for t in TARGETS},
        'missing_labels':{t:int(matrix[t].isna().sum()) for t in TARGETS},
        'matrix_hashes':{name:frame_hash(matrix,columns+['position']) for name,columns in VARIANTS.items()},
        'sources':{str(SOURCE.relative_to(ROOT)):sha(SOURCE)},'matrix_file_sha256':sha(HERE/'feature_matrix.csv'),
        'spec_sha256':sha(HERE/'SPECIFICATION.md'),'adapter_sha256':sha(Path(__file__)),
        'prepare_seconds':time.perf_counter()-started}
    (HERE/'input_manifest.json').write_text(json.dumps(coverage_report,indent=2)+'\n')
    print(json.dumps({k:coverage_report[k] for k in ['test_week','sample_counts','rejected','prepare_seconds']}))


def model(kind,columns):
    pre=ColumnTransformer([('numeric',make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),StandardScaler()),columns),
                          ('position',OneHotEncoder(handle_unknown='ignore',sparse_output=False),['position'])])
    if kind=='tree':est=HistGradientBoostingRegressor(max_iter=100,max_leaf_nodes=15,learning_rate=.05,l2_regularization=1,min_samples_leaf=30,early_stopping=False,random_state=SEED)
    else:est=TransformedTargetRegressor(regressor=MLPRegressor(hidden_layer_sizes=(16,8),activation='relu',solver='adam',alpha=.01,learning_rate_init=.001,batch_size=128,max_iter=150,early_stopping=False,shuffle=False,random_state=SEED),transformer=StandardScaler())
    return make_pipeline(pre,est)


def metrics(y,pred):
    d=pred-y
    return {'n':len(y),'descriptive_only':len(y)<30,'mae':float(np.mean(np.abs(d))),'rmse':float(np.sqrt(np.mean(d*d))),
            'bias':float(np.mean(d)),'residual_quantiles':{str(q):float(np.quantile(-d,q)) for q in (.1,.5,.9)}}


def diagnostic(sample,target,pred):
    y=sample[target].to_numpy();result=metrics(y,pred)
    groups={'position':sample.position,'sparse_history':sample.history_count<=1,'observed_zero':sample[target]==0,
            'high_opportunity':sample[target]>=dict(targets=6,carries=10,fantasy_points_ppr=15)[target],
            'team_changed':sample.team_changed_diagnostic,
            'workload_shift':(sample[target]-sample[target+'_last']).abs()>=4}
    for name,labels in groups.items():
        result[name]={str(value):metrics(y[labels.to_numpy()==value],pred[labels.to_numpy()==value]) for value in labels.unique()}
    ag=sample.assign(prediction=pred).groupby(['season','week','team'])[[target,'prediction']].sum()
    result['partial_team_aggregate']=metrics(ag[target].to_numpy(),ag.prediction.to_numpy())
    return result


def run():
    started=time.perf_counter();manifest=json.loads((HERE/'input_manifest.json').read_text())
    for path,key in [('feature_matrix.csv','matrix_file_sha256'),('SPECIFICATION.md','spec_sha256'),('experiment.py','adapter_sha256')]:
        if sha(HERE/path)!=manifest[key]:raise ValueError('Frozen input/spec/adapter changed: '+path)
    matrix=pd.read_csv(HERE/'feature_matrix.csv')
    results={};predictions=matrix[matrix.split=='test'][['player_master_id','name','position','team','opponent','history_count','team_changed_diagnostic',*TARGETS]].copy()
    fitted_meta={}
    for target in TARGETS:
        usable=matrix[target].notna();train=matrix[(matrix.split=='train')&usable]
        priors=train.groupby('position')[target].mean()
        for part in ['validation','test']:
            sample=matrix[(matrix.split==part)&usable]
            pred=sample[target+'_mean3'].fillna(sample.position.map(priors)).fillna(train[target].mean()).to_numpy()
            if target!='fantasy_points_ppr':pred=np.maximum(0,pred)
            results[target+'/'+part+'/history']=diagnostic(sample,target,pred)
            if part=='test':predictions.loc[sample.index,target+'_history']=pred
        for variant,columns in VARIANTS.items():
            X=train[columns+['position']]
            for kind in ['tree','neural']:
                signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120-second model limit')))
                signal.alarm(120);fitstart=time.perf_counter()
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter('always')
                    try:
                        with threadpool_limits(limits=1):fitted=model(kind,columns).fit(X,train[target])
                    finally:signal.alarm(0)
                fitmeta={'fit_seconds':time.perf_counter()-fitstart,'warnings':[str(w.message) for w in caught],
                         'train_rows':len(train),'input_matrix_sha256':frame_hash(train,columns+['position']),
                         'train_label_sha256':frame_hash(train,[target]),'iterations':int(fitted[-1].regressor_.n_iter_ if kind=='neural' else fitted[-1].n_iter_)}
                fitted_meta[target+'/'+variant+'/'+kind]=fitmeta
                for part in ['validation','test']:
                    sample=matrix[(matrix.split==part)&usable]
                    pred=fitted.predict(sample[columns+['position']])
                    if target!='fantasy_points_ppr':pred=np.maximum(0,pred)
                    key=target+'/'+part+'/'+variant+'/'+kind
                    results[key]=diagnostic(sample,target,pred)
                    # Sensitivity perturbs supported prior usage values consistently, not actual labels.
                    probe=sample[columns+['position']].copy()
                    for c in ['targets_mean3','targets_last','targets_trend','target_share','carries_mean3','carries_last','carries_trend','carry_share']:
                        if c in probe:probe[c]*=1.2
                    if variant=='enriched':
                        probe['catch_rate']/=1.2;probe['receiving_yards_per_target']/=1.2;probe['rushing_yards_per_carry']/=1.2
                    response=fitted.predict(probe)
                    if target!='fantasy_points_ppr':response=np.maximum(0,response)
                    results[key]['prior_usage_plus20pct_mean_prediction_change']=float(np.mean(response-pred))
                    results[key]['perturbed_share_above_one']=int(((probe.target_share>1)|(probe.carry_share>1)).sum())
                    if part=='test':predictions.loc[sample.index,target+'_'+variant+'_'+kind]=pred
                print(target,variant,kind,'fit_seconds',round(fitmeta['fit_seconds'],2),flush=True)
    predictions.to_csv(HERE/'player_predictions_2025w18.csv',index=False,float_format='%.6f')
    result={'study':'revised-data retrospective; conditional recorded-player population','test_week':[2025,18],
            'metrics':results,'fit_metadata':fitted_meta,'run_seconds':time.perf_counter()-started,
            'neural_followup_criterion_met':all(results[t+'/test/enriched/neural']['mae']<=.95*min(results[t+'/test/history']['mae'],results[t+'/test/enriched/tree']['mae']) for t in ['targets','carries']),
            'test_selection':'latest prior-season week18 with >=200 rows; coverage only','spec_sha256':manifest['spec_sha256'],'matrix_sha256':manifest['matrix_file_sha256']}
    (HERE/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Complete',round(result['run_seconds'],2),'seconds')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--run',action='store_true');a=p.parse_args()
    if a.prepare:prepare()
    elif a.run:run()
    else:p.error('Choose --prepare (freeze evidence) or --run (evaluate frozen evidence)')
