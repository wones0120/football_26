import importlib.util
from copy import deepcopy
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
s=importlib.util.spec_from_file_location('revised_experiment',Path(__file__).with_name('experiment.py'))
e=importlib.util.module_from_spec(s);s.loader.exec_module(e)


def row(pid='a',week=1,targets=0,carries=8,**kw):
    r={k:0.0 for k in e.PRODUCTION+e.TARGETS}
    r.update(player_master_id=pid,source_player_id='native-'+pid,raw_source_id=week*10+(1 if pid=='a' else 2),source_imported_at='2026-02-25',
             season=2025,week=week,team='ATL',opponent='NO',position='RB',game_id='game-'+str(week),name=pid,targets=targets,carries=carries,fantasy_points_ppr=4)
    return r|kw


def test_no_same_week_or_future_game_inputs():
    rows=[row(week=1),row(week=2),row(pid='b',week=2,targets=50),row(week=3,targets=60)]
    f=e.build_matrix(deepcopy(rows));changed=deepcopy(rows)
    changed[1]['targets']=999;changed[2]['targets']=999;changed[3]['targets']=999
    g=e.build_matrix(changed)
    cols=e.BASE+e.EXTRA
    pd.testing.assert_frame_equal(f[f.week==2][cols],g[g.week==2][cols])
    assert (f[f.week==2].max_source_week==1).all()


def test_missing_observation_vs_zero_and_bye_gap():
    f=e.build_matrix([row(week=1,targets=np.nan),row(week=3,targets=0),row(week=4,targets=3)])
    assert np.isnan(f.iloc[1].targets_mean3)
    assert f.iloc[1].weeks_since_last==2
    assert f.iloc[2].targets_mean3==0
    assert f.iloc[2].history_count==2


def test_transfer_uses_prior_team_and_no_identity_model_features():
    f=e.build_matrix([row(week=1),row(week=2,team='CAR')])
    assert f.iloc[1].prior_team=='ATL'
    assert f.iloc[1].team_changed_diagnostic
    for cols in e.VARIANTS.values():
        assert not set(cols)&{'player_master_id','name','team','opponent','raw_source_id','targets','carries','fantasy_points_ppr'}


def test_canonical_native_ambiguity_rejected_and_team_codes_normalized():
    assert e.team('LA')==e.team('LAR')
    raw=[]
    for master in ['a','b']:
        r=dict(season=2025,week=1,position='RB',player_master_id=master,source_player_id='native',team='ATL',created_at='2026',raw_nfl_weekly_stat_id=1,targets=0,carries=1,
               raw_row_json={'season_type':'REG','team':'ATL'})
        raw.append(r)
    rows,rejected=e.normalized_rows(raw)
    assert rows==[]
    assert rejected['unresolved_or_ambiguous_native_identity']==2


def test_whole_week_splits_and_opponent_shift():
    rows=[row(week=w) for w in [1,12,13,17,18]]
    f=e.build_matrix(rows)
    assert list(f.split)==['train','train','validation','validation','test']
    a=row(week=1,opponent='NO');b=row(week=2,opponent='NO')
    f=e.build_matrix([a,b])
    assert f.iloc[1].opponent_position_ppr_mean3==4


def test_baseline_enriched_parity_and_train_only_determinism():
    rng=np.random.default_rng(261013)
    f=pd.DataFrame(rng.normal(size=(180,len(e.BASE+e.EXTRA))),columns=e.BASE+e.EXTRA)
    f['position']='RB';y=np.maximum(0,f.targets_mean3+5)
    for variant,cols in e.VARIANTS.items():
        tree=e.model('tree',cols);nn=e.model('neural',cols)
        assert tree[0].transformers[0][2]==nn[0].transformers[0][2]==cols
        assert e.frame_hash(f,cols+['position'])==e.frame_hash(f.copy(),cols+['position'])
        models=[e.model('neural',cols).fit(f,y) for _ in range(2)]
        assert np.array_equal(models[0].predict(f.iloc[:8]),models[1].predict(f.iloc[:8]))
        mean=models[0][0].named_transformers_['numeric'][1].mean_.copy()
        probe=f.iloc[:8].copy();probe.iloc[:,:len(cols)]=500
        models[0].predict(probe)
        assert np.array_equal(mean,models[0][0].named_transformers_['numeric'][1].mean_)
