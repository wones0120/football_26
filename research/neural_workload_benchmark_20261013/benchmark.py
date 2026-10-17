"""Offline only: audit local snapshots; benchmark a separately validated packet.

Run from repository root: .venv/bin/python research/neural_workload_benchmark_20261013/benchmark.py
The default audits immutable local artifacts and never connects to the database.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import gzip
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import time

for _key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[_key] = '1'
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SEED = 261013
NUMERIC = ['targets_mean3', 'carries_mean3', 'targets_last', 'carries_last',
           'targets_trend', 'carries_trend', 'team_targets_mean3', 'team_carries_mean3',
           'target_share', 'carry_share', 'snap_fraction', 'history_count', 'weeks_since_last']
FEATURES = NUMERIC + ['position']


def team_code(value):
    """Recorded nflreadpy LA and canonical LAR identify the same franchise."""
    return 'LAR' if value == 'LA' else value


def read(path):
    if path.suffix == '.gz':
        with gzip.open(path, 'rt') as f:
            return json.load(f)
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=65536)
def timestamp(value):
    clock = pd.Timestamp(value)
    return clock.tz_localize('UTC') if clock.tzinfo is None else clock.tz_convert('UTC')


def valid_history(row, target):
    """Same-season earlier-week measured source, with independent source clock."""
    return (row['season'] == target['season'] and row['week'] < target['week']
            and timestamp(row['source_game_completed_at']) <= timestamp(row['observed_at'])
            < timestamp(target['decision_cutoff_at']) < timestamp(target['kickoff_at']))


def lag_features(history, target):
    rows = sorted((r for r in history if valid_history(r, target)
                   and r['player_master_id'] == target['player_master_id']
                   and r['team'] == target['team']), key=lambda r: r['week'])[-3:]
    result = {k: np.nan for k in NUMERIC}
    result.update(position=target['position'], history_count=len(rows))
    if not rows:
        return result
    result['weeks_since_last'] = target['week'] - rows[-1]['week']
    for metric in ('targets', 'carries'):
        # A missing observation never becomes a zero and does not count as measured.
        values = [float(r[metric]) for r in rows if r.get(metric) is not None]
        result[metric + '_mean3'] = np.mean(values) if values else np.nan
        last = rows[-1].get(metric)
        result[metric + '_last'] = float(last) if last is not None else np.nan
        result[metric + '_trend'] = result[metric + '_last'] - result[metric + '_mean3']
        key = 'team_' + metric
        totals = [float(r[key]) for r in rows if r.get(key) is not None]
        mean = np.mean(totals) if totals else np.nan
        result[key + '_mean3'] = mean
        result['target_share' if metric == 'targets' else 'carry_share'] = result[metric + '_mean3']/mean if mean > 0 else np.nan
    fractions = [r['snap_fraction'] for r in rows if r.get('snap_fraction') is not None]
    result['snap_fraction'] = np.mean(fractions) if fractions else np.nan
    return result


def split_weeks(frame, enforce_minimum=True):
    blocks = sorted(set(zip(frame.season.astype(int), frame.week.astype(int))))
    if len(blocks) < (20 if enforce_minimum else 9):
        raise ValueError('Need at least 12 train + 4 validation + 4 test whole-week blocks')
    labels = {b: 'train' if i < len(blocks)-8 else 'validation' if i < len(blocks)-4 else 'test'
              for i, b in enumerate(blocks)}
    return pd.Series([labels[(int(s), int(w))] for s, w in zip(frame.season, frame.week)], index=frame.index)


def validate_packet(frame):
    required = {'player_master_id', 'team', 'season', 'week', 'position', 'targets', 'carries',
                'offensive_snaps', 'label_source_id', 'label_observed_at', 'kickoff_at',
                'decision_cutoff_at', 'pregame_context_observed_at', 'pregame_context_source_id',
                'history_source_evidence', *FEATURES}
    missing = required - set(frame)
    if missing:
        raise ValueError('Missing packet fields: ' + ', '.join(sorted(missing)))
    if frame.duplicated(['player_master_id', 'season', 'week']).any():
        raise ValueError('Duplicate canonical player/week')
    for _, row in frame.iterrows():
        if not row['player_master_id'] or row['position'] not in {'QB','RB','WR','TE'}:
            raise ValueError('Unsupported canonical identity/position')
        if not row['pregame_context_source_id'] or not row['team']:
            raise ValueError('Missing pregame context source/team')
        if any(pd.notna(row[k]) and row[k] < 0 for k in ('targets','carries')):
            raise ValueError('Workload labels must be nonnegative or missing')
        cutoff = timestamp(row['decision_cutoff_at'])
        if not timestamp(row['pregame_context_observed_at']) < cutoff < timestamp(row['kickoff_at']):
            raise ValueError('Unproven pregame team/position chronology')
        if row['offensive_snaps'] <= 0 or pd.isna(row['offensive_snaps']):
            raise ValueError('Conditional participant population requires measured positive snaps')
        if not row['label_source_id'] or timestamp(row['label_observed_at']) < timestamp(row['kickoff_at']) + pd.Timedelta(hours=8):
            raise ValueError('Unproven postgame measured label')
        evidence = row['history_source_evidence']
        if isinstance(evidence, str):
            evidence = json.loads(evidence)
        if not isinstance(evidence, list):
            raise ValueError('History evidence must be a source row list')
        if any(not e.get('source_id') or not valid_history(e, row) for e in evidence):
            raise ValueError('Same-week/future/unclocked history source')
        if any(e.get('player_master_id') != row['player_master_id'] or e.get('team') != row['team'] for e in evidence):
            raise ValueError('Unproven player/team history join')
        for e in evidence:
            for metric in ('team_targets', 'team_carries', 'snap_fraction'):
                if e.get(metric) is None:
                    continue
                if not e.get(metric+'_source_ids') or not e.get(metric+'_observed_at'):
                    raise ValueError('Unclocked team/snap context: ' + metric)
                clock = timestamp(e[metric+'_observed_at'])
                if not timestamp(e['source_game_completed_at']) <= clock < cutoff:
                    raise ValueError('Future team/snap context: ' + metric)
        expected = lag_features(evidence, row)
        for key in NUMERIC:
            left, right = row[key], expected[key]
            if not (pd.isna(left) and pd.isna(right)) and not np.isclose(float(left), float(right), equal_nan=True):
                raise ValueError('Feature does not replay from clocked history: ' + key)
    return frame


def model_factory(kind):
    numeric = make_pipeline(SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True), StandardScaler())
    pre = ColumnTransformer([('numeric', numeric, NUMERIC), ('position', OneHotEncoder(handle_unknown='ignore', sparse_output=False), ['position'])])
    if kind == 'neural':
        reg = TransformedTargetRegressor(regressor=MLPRegressor(hidden_layer_sizes=(16,8), activation='relu',
                solver='adam', alpha=.01, learning_rate_init=.001, batch_size=128,
                max_iter=150, early_stopping=False, shuffle=False, random_state=SEED), transformer=StandardScaler())
    else:
        reg = HistGradientBoostingRegressor(max_iter=100, max_leaf_nodes=15, learning_rate=.05,
                  l2_regularization=1, min_samples_leaf=30, early_stopping=False, random_state=SEED)
    return make_pipeline(pre, reg)


def metrics(y, pred):
    return dict(n=len(y), descriptive_only=len(y)<30, mae=float(mean_absolute_error(y,pred)),
                rmse=float(np.sqrt(mean_squared_error(y,pred))), bias=float(np.mean(pred-y)),
                residual_quantiles={str(q):float(np.quantile(y-pred,q)) for q in (.1,.5,.9)})


def fit_comparison(frame, enforce_minimum=True):
    split = split_weeks(frame, enforce_minimum)
    result, predictions = {}, []
    for target in ('targets','carries'):
        observed = frame[target].notna()
        train = frame[(split=='train') & observed]
        if enforce_minimum and len(train) < 1000:
            raise ValueError('Insufficient measured training labels')
        prior = train.groupby('position')[target].mean()
        fitted = {}
        for name in ('tree','neural'):
            start = time.perf_counter()
            import signal
            previous_handler = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('120-second model bound')))
            signal.alarm(120)
            with threadpool_limits(limits=1):
                try:
                    model = model_factory(name).fit(train[FEATURES], train[target])
                finally:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, previous_handler)
            elapsed = time.perf_counter()-start
            if elapsed > 120:
                raise TimeoutError('Model exceeded 120 seconds')
            fitted[name] = (model,elapsed)
        for subset in ('validation','test'):
            sample = frame[(split==subset) & observed].copy()
            if enforce_minimum and len(sample) < 200:
                raise ValueError('Insufficient measured evaluation labels')
            history = sample[target+'_mean3'].fillna(sample.position.map(prior)).fillna(train[target].mean()).to_numpy()
            values = {'history':(None,0,history), **{k:(m,t,np.maximum(0,m.predict(sample[FEATURES]))) for k,(m,t) in fitted.items()}}
            for name,(model,elapsed,pred) in values.items():
                residual = sample.assign(prediction=pred)
                key = target+'/'+subset+'/'+name
                result[key] = metrics(sample[target].to_numpy(),pred) | {'fit_seconds':elapsed,
                    'by_position':{p:metrics(g[target].to_numpy(),g.prediction.to_numpy()) for p,g in residual.groupby('position')},
                    'sparse_history':{str(s):metrics(g[target].to_numpy(),g.prediction.to_numpy()) for s,g in residual.groupby(residual.history_count<=1)},
                    'observed_zero':{str(s):metrics(g[target].to_numpy(),g.prediction.to_numpy()) for s,g in residual.groupby(residual[target]==0)},
                    'workload_shift':{str(s):metrics(g[target].to_numpy(),g.prediction.to_numpy()) for s,g in residual.groupby((residual[target]-residual[target+'_last']).abs()>=4)}}
                groups = residual.groupby(['season','week','team'])[[target,'prediction']].sum()
                result[key]['conditional_team_aggregate'] = metrics(groups[target].to_numpy(),groups.prediction.to_numpy())
                if model is not None:
                    perturbed=sample[FEATURES].copy()
                    for field in ('targets_mean3','carries_mean3','targets_last','carries_last','targets_trend','carries_trend','target_share','carry_share'):
                        perturbed[field] *= 1.2
                    changed=np.maximum(0,model.predict(perturbed))
                    result[key]['prior_usage_plus20pct_mean_prediction_change']=float(np.mean(changed-pred))
                    result[key]['perturbation_share_above_one']=int(((perturbed.target_share>1)|(perturbed.carry_share>1)).sum())
                for index,p in zip(sample.index,pred):
                    predictions.append({'row':int(index),'target':target,'split':subset,'model':name,'prediction':float(p)})
    return result,predictions


def audit():
    start=time.perf_counter()
    source=ROOT/'artifacts/classic_opportunity_repair/weekly_stats.json.gz'
    capture=source.parent/'capture_inputs.py'
    schedule_path=source.parent/'schedules.json'
    current=ROOT/'artifacts/all_games_captain_2026/inputs/stats.json.gz'
    paths=[source,capture,schedule_path,current,OUT/'SPECIFICATION.md']
    raw=read(source)
    eligible=[r for r in raw if r['position'] in {'QB','RB','WR','TE'}
              and r.get('raw_row_json',{}).get('season_type') == 'REG']
    native=defaultdict(set)
    for r in eligible:
        if r.get('player_master_id'):
            native[r['source_player_id']].add(r['player_master_id'])
    ambiguous={k for k,v in native.items() if len(v)!=1}
    # Source snapshot joins native source_key; independently reject multiple canonical mappings.
    unique={}
    for r in eligible:
        if not r.get('player_master_id') or r['source_player_id'] in ambiguous:
            continue
        k=(r['season'],r['week'],r['player_master_id'])
        version=(timestamp(r['created_at']),int(r['raw_nfl_weekly_stat_id']))
        if k not in unique or version < unique[k][0]:
            unique[k]=(version,r)
    schedules={}
    for r in read(schedule_path):
        v=r['raw_row_json']
        if not v.get('gameday') or not v.get('gametime') or v.get('game_type')!='REG':
            continue
        # All game clocks are Eastern local as recorded by the source.
        kickoff=pd.Timestamp(v['gameday']+' '+v['gametime'],tz='America/New_York').tz_convert('UTC')
        for team in (v.get('home_team'),v.get('away_team')):
            key=(int(r['season']),int(r['week']),team_code(team))
            item={'kickoff':kickoff,'schedule_observed_at':timestamp(r['created_at'])}
            if key not in schedules or item['schedule_observed_at']<schedules[key]['schedule_observed_at']:
                schedules[key]=item
    per_season={}
    for season in sorted(set(r['season'] for _,r in unique.values())):
        rows=[r for _,r in unique.values() if r['season']==season]
        clocks=[timestamp(r['created_at']) for r in rows]
        per_season[str(season)]={'unique_skill_player_weeks':len(rows),'weeks':sorted(set(r['week'] for r in rows)),
            'earliest_import_at':str(min(clocks)),'latest_first_import_at':str(max(clocks)),
            'missing_targets':sum(r.get('targets') is None for r in rows),
            'missing_carries':sum(r.get('carries') is None for r in rows),
            'observed_zero_targets':sum(r.get('targets')==0 for r in rows),
            'observed_zero_carries':sum(r.get('carries')==0 for r in rows)}
    lag_audit=Counter()
    for _,r in unique.values():
        if r['season']!=2026:
            continue
        previous=schedules.get((2026,r['week'],r['team']))
        next_game=schedules.get((2026,r['week']+1,r['team']))
        if not previous or not next_game:
            lag_audit['missing_source_or_next_schedule']+=1
        elif timestamp(r['created_at']) < previous['kickoff']+pd.Timedelta(hours=8):
            lag_audit['import_before_completed_source_window']+=1
        elif timestamp(r['created_at']) >= next_game['kickoff']:
            lag_audit['first_import_after_next_game_kickoff']+=1
        elif next_game['schedule_observed_at'] >= next_game['kickoff']:
            lag_audit['next_schedule_first_import_after_kickoff']+=1
        else:
            lag_audit['clock_eligible_for_next_week_before_kickoff_only']+=1
    current_rows=read(current)
    result={'study_status':'infeasible_for_chronology_verified_comparison','retrospective':True,
      'raw_snapshot_rows':len(raw),'skill_source_rows':len(eligible),'canonical_unique_player_weeks':len(unique),
      'unresolved_skill_source_rows':sum(not r.get('player_master_id') for r in eligible),
      'native_payload_missing_team_rows':sum(r.get('raw_row_json',{}).get('team') is None for r in eligible),
      'team_native_payload_mismatch_rows':sum(r.get('raw_row_json',{}).get('team') is not None and r['raw_row_json']['team'] != r['team'] for r in eligible),
      'team_code_normalization':{'LA':'LAR'},
      'team_mismatch_after_normalization':sum(team_code(r['raw_row_json'].get('team')) != team_code(r['team']) for r in eligible),
      'ambiguous_native_ids':len(ambiguous),'per_season':per_season,
      'current_snapshot_weeks':sorted(set(r['week'] for r in current_rows)),
      'current_snapshot_rows':len(current_rows),'2026_next_week_clock_audit':dict(lag_audit),
      'performance_evaluated':False,'nn_improves':None,
      'reason':['Past-season imports cannot prove contemporaneous pregame source availability.',
                'At most five current-season weeks, below the 20-week minimum; the canonical workload snapshot ends week 4.',
                'No historical positive offensive-participation population or pregame roster/team clocks in this workload snapshot.',
                'Kickoff-only source eligibility is weaker than exact historical decision-cutoff evidence.'],
      'runtime_seconds':time.perf_counter()-start,
      'manifest':{str(p.relative_to(ROOT)): {'sha256':digest(p),'bytes':p.stat().st_size} for p in paths}}
    (OUT/'data_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('study_status','raw_snapshot_rows','canonical_unique_player_weeks','2026_next_week_clock_audit','runtime_seconds')},indent=2))
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--packet',type=Path,help='validated evidence JSON list; audited local data are not substituted')
    args=parser.parse_args()
    if args.packet is None:
        audit();return
    frame=validate_packet(pd.DataFrame(read(args.packet)))
    results,predictions=fit_comparison(frame)
    (OUT/'benchmark_results.json').write_text(json.dumps({'retrospective':True,'packet_sha256':digest(args.packet),'metrics':results,'predictions':predictions},indent=2)+'\n')

if __name__=='__main__':
    main()
