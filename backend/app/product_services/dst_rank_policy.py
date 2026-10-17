"""Research-only temporal DST policies with tie-aware ranking diagnostics.

No live Prepare, model pointer or serving route imports this module. The median
remains a valid fallback; prediction dispersion never counts as rank evidence.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .dedicated_dst_model import learner

ORDER = ('median', 'ensemble', 'ridge', 'regularized_tree')


def rank_metrics(actual, prediction, *, top_k=5):
    actual, prediction = np.asarray(actual, dtype=float), np.asarray(prediction, dtype=float)
    if (actual.ndim != 1 or prediction.shape != actual.shape or not len(actual)
            or not np.isfinite(actual).all() or not np.isfinite(prediction).all()):
        raise ValueError('Finite aligned DST actuals and forecasts required')
    i, j = np.triu_indices(len(actual), 1)
    truth = np.sign(actual[i] - actual[j])
    usable = truth != 0
    forecast = np.sign(prediction[i] - prediction[j])
    accuracy = float(np.where(forecast[usable] == 0, .5, forecast[usable] == truth[usable]).mean()) if usable.any() else .5
    k = min(top_k, len(actual))
    boundary = np.sort(prediction)[-k]
    above, tied = prediction > boundary, prediction == boundary
    fraction = (k - int(above.sum())) / int(tied.sum())
    top_actual = float((actual[above].sum() + fraction * actual[tied].sum()) / k)
    oracle = float(np.sort(actual)[-k:].mean())
    correlation = float(spearmanr(prediction, actual).statistic) if np.ptp(prediction)>0 and np.ptp(actual)>0 else 0.
    return dict(n=len(actual), pairwise_pairs=int(usable.sum()), pairwise_accuracy=accuracy,
                spearman=correlation, top5_actual=top_actual, top5_regret=oracle-top_actual,
                top5_oracle=oracle, prediction_std=float(np.std(prediction)), distinct_predictions=len(np.unique(prediction)))


@dataclass
class TemporalDstPolicies:
    columns: list[str]
    models: dict
    median: float
    mae_choice: str
    rank_choice: str
    audit: dict

    def predictions(self, features):
        return combine_predictions(self.median, self.models['ridge'].predict(features[self.columns]),
                                   self.models['regularized_tree'].predict(features[self.columns]))

    def predict(self, features, *, policy):
        predictions = self.predictions(features)
        if policy == 'existing_mae_policy':
            return predictions[self.mae_choice]
        if policy == 'rank_selector':
            return predictions[self.rank_choice]
        if policy in predictions:
            return predictions[policy]
        raise ValueError('Unknown frozen DST ranking policy')


def combine_predictions(median, ridge, tree):
    ridge, tree = np.asarray(ridge, dtype=float), np.asarray(tree, dtype=float)
    if ridge.shape != tree.shape:
        raise ValueError('Aligned DST base forecasts required')
    return dict(median=np.full(len(ridge), float(median)), ridge=ridge,
                regularized_tree=tree, ensemble=.5*float(median)+.25*ridge+.25*tree)


def fit_policies(frame, columns, *, target):
    """Fit two frozen learners twice; reuse them for all temporal policy arms."""
    period = frame.season*100+frame.week
    weeks = sorted(period.unique())
    if len(weeks)<6:
        raise ValueError('At least six training weeks required')
    inner = period>=weeks[-3]
    prefix, validation = frame.loc[~inner], frame.loc[inner]
    prefix_models={name:learner(name).fit(prefix[columns],prefix[target]) for name in ['ridge','regularized_tree']}
    median=float(prefix[target].median())
    predictions=combine_predictions(median,prefix_models['ridge'].predict(validation[columns]),prefix_models['regularized_tree'].predict(validation[columns]))
    scores=[]
    for name, prediction in predictions.items():
        week_scores=[]
        for key, indices in validation.groupby(['season','week']).indices.items():
            score=rank_metrics(validation.iloc[indices][target],prediction[indices])
            week_scores.append(dict(season=int(key[0]),week=int(key[1]),supported=score['n']>=10,**score))
        supported=[score['pairwise_accuracy'] for score in week_scores if score['supported']]
        scores.append(dict(name=name,mae=float(abs(prediction-validation[target].to_numpy()).mean()),
                           pairwise_accuracy=float(np.mean(supported)) if supported else .5,
                           supported_weeks=len(supported),weeks=week_scores))
    by_name={score['name']:score for score in scores}
    mae_choice=min(['median','ridge','regularized_tree'],key=lambda name:(by_name[name]['mae'],['median','ridge','regularized_tree'].index(name)))
    eligible=[name for name in ORDER if name!='median' and by_name[name]['supported_weeks']>0
              and by_name[name]['mae']<=by_name['median']['mae']+.15
              and by_name[name]['pairwise_accuracy']>=.52]
    rank_choice=min(eligible,key=lambda name:(-by_name[name]['pairwise_accuracy'],ORDER.index(name))) if eligible else 'median'
    models={name:learner(name).fit(frame[columns],frame[target]) for name in ['ridge','regularized_tree']}
    audit=dict(training_n=len(frame),inner_prefix_n=len(prefix),inner_n=len(validation),
               training_last_week=int(period.max()),inner_prefix_last_week=int(period.loc[~inner].max()),
               inner_first_week=int(period.loc[inner].min()),mae_choice=mae_choice,rank_choice=rank_choice,
               scores=scores,fits=4,rank_eligible=eligible,live_enabled=False)
    return TemporalDstPolicies(list(columns),models,float(frame[target].median()),mae_choice,rank_choice,audit)
