import numpy as np
import pytest
from backend.app.product_services.game_progression_precision import SEEDS,TOLERANCES,evaluate_precision,select_precision_games


def fixture(n):
    draws={s:{arm:np.zeros((n,2,len(TOLERANCES)))for arm in('contextual','control')}for s in SEEDS}
    statuses={s:{a:[dict(status='COMPLETE_REGULATION',full_law_known=True)for _ in range(n)]for a in('contextual','control')}for s in SEEDS}
    return draws,statuses


def test_minimum1024_and_never_forecast_quality():
    d,s=fixture(256);r=evaluate_precision(d,s);assert not r['precision_pass']and r['next_fixed_batch']==1024
    d,s=fixture(1024);r=evaluate_precision(d,s);assert r['precision_pass']and not r['forecast_quality_assessed']and not r['tail_calibration_assessed']


def test_unknown_path_cannot_be_dropped_or_zero_filled():
    d,s=fixture(1024);s[17]['contextual'][4]['full_law_known']=False
    r=evaluate_precision(d,s);assert not r['precision_pass']and len(r['unknown_paths'])==1
    d[17]['contextual']=d[17]['contextual'][:-1]
    with pytest.raises(ValueError):evaluate_precision(d,s)


def test_cross_seed_batch_and_paired_mc_precision_are_distinct():
    d,s=fixture(1024);d[731]['contextual'][:,:,0]=1
    r=evaluate_precision(d,s);assert not r['precision_pass']and r['checks']['contextual|team0|official_pass_attempts']['cross_seed_mean_difference']==1
    d,s=fixture(1024)
    for seed in SEEDS:d[seed]['contextual'][256:,:,0]=2
    r=evaluate_precision(d,s);assert r['checks']['contextual|team0|official_pass_attempts']['seeds']['17']['previous_mean_change']==1.5 and not r['precision_pass']
    d,s=fixture(1024);v=np.tile([-1.,1.],512)*10
    for seed in SEEDS:
        d[seed]['contextual'][:,:,0]=10+v[:,None];d[seed]['control'][:,:,0]=10-v[:,None]
    r=evaluate_precision(d,s)
    assert not r['checks']['paired_context_minus_control|team0|official_pass_attempts']['pass_numeric_checks']


def test_minhash_selection_deduplicates_sides_and_does_not_substitute():
    rows=[dict(game_id=f'2026_0{w}_{a}_B',week=w,independently_finalized=True)for w in range(1,6)for a in('A','C')]
    selected=select_precision_games(rows+rows);assert len(selected)==5 and selected==select_precision_games(list(reversed(rows)))
    for g in selected:g['unsupported']=True
    assert [r['game_id']for r in selected]==[r['game_id']for r in select_precision_games(rows)]
