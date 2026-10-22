"""Complete conditional DK score head; never consumes an incumbent projection.

Historical opportunity counts condition training labels. Current inputs must be
new-model forecasts. Conditional-head validation is not end-to-end forecast skill.
"""
import math
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text
from .evaluation_record import digest

VERSION='new_opportunity_complete_dk_points_v1'
COUNTS=('pass_attempts','rush_attempts','targets')
FEATURES=[*COUNTS,'team_pass_attempts','team_rush_attempts','prior_points3','prior_points8','prior_games']


def points(raw,position):
    """DK PPR including bonuses, returns, conversions and lost fumbles.

    Kicking has no missed-FG deduction. Structural zeros must be source reported.
    """
    def n(key,*aliases):
        value=next((raw[k] for k in (key,*aliases) if k in raw and raw[k] is not None),None)
        if value is None or not math.isfinite(float(value)):raise ValueError('Unknown scoring field: '+key)
        return float(value)
    if position=='K':
        return sum(n(k)*w for k,w in [('fg_made_0_19',3),('fg_made_20_29',3),('fg_made_30_39',3),
            ('fg_made_40_49',4),('fg_made_50_59',5),('fg_made_60_',5),('pat_made',1)])
    py,ry,cy=n('passing_yards'),n('rushing_yards'),n('receiving_yards')
    score=.04*py+.1*(ry+cy)+n('receptions')+4*n('passing_tds')+6*(n('rushing_tds')+n('receiving_tds'))
    score-=n('passing_interceptions','interceptions')
    score-=n('fumbles_lost_total') if raw.get('fumbles_lost_total') is not None else sum(n(k) for k in ('sack_fumbles_lost','rushing_fumbles_lost','receiving_fumbles_lost'))
    score+=2*sum(n(k) for k in ('passing_2pt_conversions','rushing_2pt_conversions','receiving_2pt_conversions'))
    score+=6*(n('special_teams_tds')+n('fumble_recovery_tds'))
    return score+3*(int(py>=300)+int(ry>=100)+int(cy>=100))


def load_rows(engine,*,season,week,cutoff):
    with engine.connect() as connection:
        rows=connection.execute(text('''WITH aliases AS (
            SELECT source_key,MIN(player_master_id::text) AS player_master_id FROM player_alias
            WHERE source_system='nflreadpy' GROUP BY source_key HAVING COUNT(DISTINCT player_master_id)=1)
            SELECT DISTINCT ON (r.player_id,r.season,r.week)
            a.player_master_id,r.player_id AS native_id,r.season,r.week,r.team,r.position,r.raw_row_json,
            r.raw_nfl_weekly_stat_id AS source_id,r.created_at
            FROM raw_nfl_weekly_stat r LEFT JOIN aliases a ON a.source_key=r.player_id WHERE r.season BETWEEN :start AND :season
            AND (r.season<:season OR r.week<:week) AND r.week<=18 AND r.created_at<=:cutoff
            AND r.raw_row_json->>'season_type'='REG' AND r.position IN ('QB','RB','FB','WR','TE','K')
            ORDER BY r.player_id,r.season,r.week,r.created_at DESC,r.raw_nfl_weekly_stat_id DESC'''),
            dict(start=season-3,season=season,week=week,cutoff=cutoff)).mappings().all()
    from .market_snapshots import canonical_team
    records=[];unknown=[]
    for r in rows:
        raw=r['raw_row_json'];position='RB' if r['position']=='FB' else r['position']
        try:y=points(raw,position)
        except ValueError as exc:unknown.append(dict(source_id=r['source_id'],reason=str(exc)));y=None
        values=[]
        for key,aliases in [('attempts',('passing_attempts',)),('carries',('rushing_attempts',)),('targets',())]:
            v=next((raw[k] for k in (key,*aliases) if raw.get(k) is not None),None)
            values.append(float(v) if v is not None and math.isfinite(float(v)) else np.nan)
        records.append(dict(pid=str(r['player_master_id']) if r['player_master_id'] else None,team=canonical_team(r['team']),
            position=position,period=r['season']*100+r['week'],points=y,source_id=int(r['source_id']),counts=values))
    return records,unknown


def features(counts,budget,history):
    return [*counts,budget.get('pass_attempts'),budget.get('rush_attempts'),
        np.mean([r['points'] for r in history[-3:]]) if history else np.nan,
        np.mean([r['points'] for r in history[-8:]]) if history else np.nan,len(history)]


def fit_and_predict(records,actors,budgets,*,before_period):
    if any(r['period']>=before_period for r in records):raise ValueError('Scoring-head training contains target/future results')
    if len({(r['pid'],r['period']) for r in records if r['pid']})!=sum(bool(r['pid']) for r in records):
        raise ValueError('Ambiguous canonical scoring training rows')
    by_period={};history={};training={p:[] for p in ('QB','RB','WR','TE','K')}
    for r in records:by_period.setdefault((r['team'],r['period']),[]).append(r)
    for r in sorted(records,key=lambda r:(r['period'],r['team'],r['pid'] or '')):
        peers=by_period[r['team'],r['period']]
        budget={k:sum(p['counts'][i] for p in peers) if all(math.isfinite(p['counts'][i]) for p in peers) else np.nan
                for i,k in enumerate(COUNTS)}
        key=(r['pid'],r['team']);prior=history.get(key,[])
        if r['pid'] and prior and r['points'] is not None:
            training[r['position']].append(dict(x=features(r['counts'],budget,prior),y=r['points'],period=r['period'],source_id=r['source_id']))
        if r['pid'] and r['points'] is not None:history.setdefault(key,[]).append(r)
    outputs={};receipts={}
    for position,rows in training.items():
        if len(rows)<100:raise ValueError('Insufficient complete DK training labels for '+position)
        x=np.asarray([r['x'] for r in rows],float);y=np.asarray([r['y'] for r in rows],float)
        last=max(r['period'] for r in rows);train=np.asarray([r['period']<last for r in rows]);held=~train
        def model():return make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),StandardScaler(),Ridge(alpha=30.))
        validation=model().fit(x[train],y[train]);pred=validation.predict(x[held])
        fitted=model().fit(x,y)
        selected=[a for a in actors if a['position']==position]
        for actor in selected:
            counts=[actor['counts'].get(k) for k in COUNTS]
            if position=='K':counts=[0.,0.,0.] # K scoring domain contains only kicking.
            else:
                # Nonapplicable channels are not unknown role forecasts.
                for i,k in enumerate(COUNTS):
                    if (position=='QB' and k=='targets') or (position!='QB' and k=='pass_attempts'):counts[i]=0.
            if any(v is None or not math.isfinite(float(v)) for v in counts):
                outputs[actor['player_master_id']]=dict(mean=None,reason='Unknown required new-model opportunity forecast');continue
            past=history.get((actor['player_master_id'],actor['team']),[])
            vector=features(counts,budgets[actor['team']],past)
            mean=float(fitted.predict(np.asarray([vector]))[0])
            outputs[actor['player_master_id']]=dict(mean=max(0.,mean),unfloored_mean=mean,features=dict(zip(FEATURES,[None if pd.isna(v) else float(v) for v in vector])),
                history_source_ids=[r['source_id'] for r in past[-8:]],position=position)
        receipts[position]=dict(training_rows=len(rows),training_max_period=max(r['period'] for r in rows),
            training_sha256=digest([dict(source_id=r['source_id'],period=r['period'],target=r['y'],features=[None if pd.isna(v) else float(v) for v in r['x']]) for r in rows]),
            coefficients=fitted[-1].coef_.tolist(),intercept=float(fitted[-1].intercept_),
            medians=fitted[0].statistics_.tolist(),indicator_columns=fitted[0].indicator_.features_.tolist(),
            center=fitted[1].mean_.tolist(),scale=fitted[1].scale_.tolist(),
            conditional_head_validation=dict(period=last,rows=int(held.sum()),mae=float(np.mean(abs(pred-y[held]))),
                interpretation='Conditions on observed historical counts; NOT end-to-end forecast validation'))
    return dict(version=VERSION,before_period=before_period,players=outputs,models=receipts,feature_columns=FEATURES,
        incumbent_projection_consumed=False,definition='Full DK score target, including TD/bonus/return/fumble contributions; fixed prior-only conditional Ridge heads',
        limitations=['New point approximation; no calibrated win probability or demonstrated forecast superiority',
            'Scoring-head training conditions on observed counts; current inference consumes forecast counts, whose error is additional',
            'Predicted scores have a declared nonnegative serving floor; negative game outcomes remain in training'])
