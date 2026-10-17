"""Read-only same-input incumbent DST forecasts from a combined fitted artifact.
No model fit, setting switch, pointer mutation, fake projection or persistence.
"""
import numpy as np
import pandas as pd
from backend.app.product_services.predictions import (
    CALIBRATION_QUANTILES, apply_residual_calibration, blend_point_predictions,
    derive_calibration_roles,
)


def incumbent_dst_counterfactual(payload):
    target=payload['target'];train=payload['train'];columns=payload['feature_columns']
    # Shared model/frames stay legacy by explicit artifact contract. Score the
    # full saved batch so floating-point evaluation matches production ordering.
    raw=payload['model'].predict(target[columns].apply(pd.to_numeric,errors='coerce').fillna(0.))
    means=blend_point_predictions(raw,train,target)
    roles=derive_calibration_roles(target)
    profiles=payload['profiles'];metrics=payload['calibration']
    rows=[]
    for index,row in target.iterrows():
        if str(row['position']).upper()!='DST':continue
        # Production opportunity and market reconciliation only allocate to
        # skill positions; DST never receives those additive adjustments.
        role=str(roles.iloc[index]);explicit=str(row.get('pregame_role_label') or '').upper()
        if explicit in {'LEAD','COMMITTEE','PRIMARY','SECONDARY','ROTATION'}:role=explicit
        key=f'DST|{role}';split=metrics.get('importance_splits_by_role',{}).get(key)
        importance=pd.to_numeric(row.get('offensive_role_importance'),errors='coerce')
        if split is not None and pd.notna(importance):key+=('|importance_high' if float(importance)>=split else '|importance_low')
        profile=profiles.get(key,profiles.get(f'DST|{role}',profiles.get('DST',profiles['__ALL__'])))
        mean=max(0.,float(means[index]));prob=float(row.get('pregame_availability_probability',1.) or 0.)
        quantiles=apply_residual_calibration(mean,profile)
        result=dict(player_id=str(row.player_id),player_master_id=str(row.player_master_id),
            team=str(row.get('recent_team')),game_id=str(row.get('game_id')),salary=float(row.salary),
            mean=mean*prob,predicted_mean=mean*prob,adj_mean=mean*prob,
            calibration_method=profile.source,calibration_sample_size=profile.sample_size,
            scoring='same-input legacy DST component only; all non-DST pool cells held fixed')
        for name in CALIBRATION_QUANTILES:result['predicted_'+name]=quantiles[name]*prob
        result['p90']=result['predicted_p90'];result['projection']=result['mean']
        rows.append(result)
    return pd.DataFrame(rows)
