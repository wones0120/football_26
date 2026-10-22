"""Explicit retrained feature-group ablations; not a live selection policy."""
import math
from .lineup_top_decile_research import CORE_FEATURES,RICH_FEATURES

CONTRACT='complete_lineup_feature_ablation_v1'
SALARY={'salary_used','min_base_salary','base_salary_std'}
STACKING={'team_roster_herfindahl','game_roster_herfindahl','max_team_count','max_game_count','qb_receiver_pairs','opposing_qb_receiver_pairs'}
TREATMENTS={'original':set(),'remove_salary':SALARY,'remove_stacking':STACKING,'remove_both':SALARY|STACKING}


def active_indices(base_names,treatment):
    if base_names not in[CORE_FEATURES,CORE_FEATURES+RICH_FEATURES]or treatment not in TREATMENTS:raise ValueError('Unknown ablation feature contract')
    return [i for i,name in enumerate(base_names)if name not in TREATMENTS[treatment]]


def predict(artifact,full_values):
    if artifact.get('contract_id')!=CONTRACT:raise ValueError('Unknown ablation model contract')
    indices=active_indices(artifact['base_features'],artifact['treatment'])
    if artifact['features']!=[artifact['base_features'][i]for i in indices]or len(full_values)!=len(artifact['base_features']):raise ValueError('Ablation feature identity mismatch')
    values=[full_values[i]for i in indices];arrays=[artifact[k]for k in ['mean','scale','coefficients']]
    if any(len(a)!=len(values)for a in arrays)or not all(math.isfinite(float(v))for a in arrays+[values]for v in a)or any(v<=0 for v in artifact['scale']):raise ValueError('Nonfinite/malformed ablation model')
    logit=float(artifact['intercept'])+sum((v-m)/s*c for v,m,s,c in zip(values,*arrays))
    return 1/(1+math.exp(-max(-700,min(700,logit))))
