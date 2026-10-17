import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

spec=importlib.util.spec_from_file_location('neural_benchmark',Path(__file__).with_name('benchmark.py'))
b=importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def target():
    return dict(player_master_id='canonical-a',team='ATL',season=2026,week=4,position='RB',
                decision_cutoff_at='2026-10-04T12:00:00Z',kickoff_at='2026-10-04T17:00:00Z')


def history(week=2, **changes):
    row=dict(player_master_id='canonical-a',team='ATL',season=2026,week=week,
             source_game_completed_at='2026-09-21T02:00:00Z',observed_at='2026-09-22T12:00:00Z',
             source_id='source-a',targets=0,carries=12,team_targets=30,team_carries=30,snap_fraction=.5)
    return row|changes


def test_lagging_excludes_same_week_future_source_and_other_identity():
    rows=[history(),history(week=4,targets=99),history(observed_at='2026-10-05T12:00:00Z',targets=99),
          history(player_master_id='canonical-b',targets=99)]
    result=b.lag_features(rows,target())
    assert result['history_count']==1
    assert result['targets_mean3']==0
    assert result['carries_mean3']==12


def test_zero_missing_and_transfer_do_not_become_same_label():
    assert b.team_code('LA') == b.team_code('LAR')
    assert b.team_code('NO') != b.team_code('LAR')
    result=b.lag_features([history(targets=None)],target())
    assert np.isnan(result['targets_mean3'])
    assert b.lag_features([history()],target())['targets_mean3']==0
    assert b.lag_features([history(team='NO')],target())['history_count']==0


def test_completion_clock_required():
    assert not b.valid_history(history(observed_at='2026-09-20T12:00:00Z'),target())


def test_splits_are_ordered_disjoint_whole_weeks():
    frame=pd.DataFrame([dict(season=2026,week=w) for w in range(1,21) for _ in range(4)])
    split=b.split_weeks(frame)
    weeks={part:set(frame[split==part].week) for part in ('train','validation','test')}
    assert max(weeks['train'])<min(weeks['validation'])
    assert max(weeks['validation'])<min(weeks['test'])
    assert [len(weeks[p]) for p in weeks]==[12,4,4]
    with pytest.raises(ValueError):b.split_weeks(frame[frame.week<=5])


def test_packet_rejects_unclocked_sources():
    with pytest.raises(ValueError,match='Missing packet fields'):
        b.validate_packet(pd.DataFrame([target()]))


def packet():
    h=history()
    for metric in ('team_targets','team_carries','snap_fraction'):
        h[metric+'_source_ids']=['measured-'+metric]
        h[metric+'_observed_at']=h['observed_at']
    t=target()
    return t|b.lag_features([h],t)|dict(targets=0,carries=10,offensive_snaps=35,
        label_source_id='label-a',label_observed_at='2026-10-05T08:00:00Z',
        pregame_context_source_id='roster-a',pregame_context_observed_at='2026-10-03T12:00:00Z',
        history_source_evidence=[h])


def test_packet_replays_features_and_requires_team_context_clocks():
    p=packet()
    b.validate_packet(pd.DataFrame([p]))
    tampered=p|dict(targets_mean3=99)
    with pytest.raises(ValueError,match='does not replay'):
        b.validate_packet(pd.DataFrame([tampered]))
    p['history_source_evidence'][0]['team_targets_observed_at']='2026-10-05T08:00:00Z'
    with pytest.raises(ValueError,match='Future team/snap'):
        b.validate_packet(pd.DataFrame([p]))


def test_deterministic_model_and_train_only_preprocessing():
    rng=np.random.default_rng(3)
    train=pd.DataFrame(rng.normal(size=(140,len(b.NUMERIC))),columns=b.NUMERIC)
    train['position']='RB'
    y=np.maximum(0,4+train.targets_mean3.to_numpy())
    for kind in ('tree','neural'):
        m=b.model_factory(kind).fit(train,y)
        m2=b.model_factory(kind).fit(train,y)
        probe=train.iloc[:10].copy()
        assert np.array_equal(m.predict(probe),m2.predict(probe))
        scaler=m[0].named_transformers_['numeric'][1]
        mean_before=scaler.mean_.copy()
        probe['targets_mean3']=100000
        m.predict(probe)
        assert np.array_equal(scaler.mean_,mean_before)
