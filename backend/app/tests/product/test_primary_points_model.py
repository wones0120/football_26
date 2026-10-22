from copy import deepcopy
import pytest
from backend.app.product_services.primary_points_model import points,fit_and_predict,FEATURES


def records():
    rows=[]
    for week in range(1,17):
        for position in ('QB','RB','WR','TE','K'):
            for actor in range(8):
                counts=[20.+actor+week if position=='QB' else 0.,float(actor+week%3),float(actor+week%4) if position not in {'QB','K'} else 0.]
                if position=='K':counts=[0.,0.,0.]
                rows.append(dict(pid=position+str(actor),team='BUF',position=position,period=202500+week,counts=counts,
                    points=4+.4*counts[0]+.6*counts[1]+1.4*counts[2]+week*.1,source_id=len(rows)))
    return rows


def test_complete_score_heads_never_consume_incumbent_means_and_replay_exactly():
    actors=[dict(player_master_id=p+'0',team='BUF',position=p,counts=dict(pass_attempts=28.,rush_attempts=6.,targets=7.)) for p in ('QB','RB','WR','TE','K')]
    budgets={'BUF':dict(pass_attempts=32.,rush_attempts=25.)}
    out=fit_and_predict(records(),actors,budgets,before_period=202601)
    changed=deepcopy(actors)
    for a in changed:a['projection']=99999.
    assert out==fit_and_predict(records(),changed,budgets,before_period=202601)
    assert not out['incumbent_projection_consumed']
    for actor in actors:
        row=out['players'][actor['player_master_id']];model=out['models'][actor['position']]
        values=[row['features'][k] for k in FEATURES]
        extended=values+[float(values[i] is None) for i in model['indicator_columns']]
        extended=[model['medians'][i] if v is None and i<len(values) else v for i,v in enumerate(extended)]
        score=sum((v-c)/s*w for v,c,s,w in zip(extended,model['center'],model['scale'],model['coefficients']))+model['intercept']
        assert row['mean']==pytest.approx(max(0.,score))
        assert model['training_max_period']<202601
        assert 'NOT end-to-end' in model['conditional_head_validation']['interpretation']


def test_unknown_count_never_borrows_an_old_projection_and_future_labels_block():
    actors=[dict(player_master_id='WR0',team='BUF',position='WR',projection=30.,counts=dict(pass_attempts=None,rush_attempts=None,targets=8.))]
    out=fit_and_predict(records(),actors,{'BUF':dict(pass_attempts=30.,rush_attempts=25.)},before_period=202601)
    assert out['players']['WR0']['mean'] is None
    with pytest.raises(ValueError,match='future'):fit_and_predict(records(),actors,{},before_period=202510)


def test_complete_dk_target_scores_td_bonus_returns_fumbles_and_kicking():
    raw={k:0. for k in ('passing_yards','rushing_yards','receiving_yards','receptions','passing_tds','rushing_tds','receiving_tds','passing_interceptions',
        'fumbles_lost_total','passing_2pt_conversions','rushing_2pt_conversions','receiving_2pt_conversions','special_teams_tds','fumble_recovery_tds')}
    raw.update(passing_yards=300,rushing_yards=100,receiving_yards=100,receptions=5,passing_tds=2,rushing_tds=1,receiving_tds=1,fumbles_lost_total=1,special_teams_tds=1,fumble_recovery_tds=1)
    assert points(raw,'QB')==pytest.approx(77.)
    kick={k:0. for k in ('fg_made_0_19','fg_made_20_29','fg_made_30_39','fg_made_40_49','fg_made_50_59','fg_made_60_','pat_made')}
    kick.update(fg_made_50_59=1,pat_made=2,fg_missed=3)
    assert points(kick,'K')==7
    with pytest.raises(ValueError,match='Unknown scoring'):points({},'QB')


def test_primary_pool_preserves_unknown_baseline_without_fallback():
    from backend.app.product_services.primary_model_forecast import pool_scores
    rows=[dict(player_id='unknown',position='WR',projection=None),dict(player_id='known',position='RB',projection=7.)]
    result=pool_scores(rows,{'known':{'mean':11.}},[],{})
    assert result[0]['baseline_mean'] is None
    assert result[0]['conditional_mean'] is None
    assert result[0]['missing_evidence']
    assert result[1]['conditional_mean']==11.
    assert result[1]['delta']==4.


def test_primary_evidence_distinguishes_factual_zero_dst_and_learned_head():
    from backend.app.product_services.primary_model_forecast import pool_scores
    rows=[dict(player_id='inactive',position='WR',projection=8.),dict(player_id='dst',position='DST',projection=6.),dict(player_id='rb',position='RB',projection=7.)]
    heads={'rb':dict(mean=10.)};actors=[dict(player_master_id='inactive',world_activity=False,counts=dict(targets=0.)),dict(player_master_id='rb',player_model_components=dict(counts=dict(rush_attempts=8.)))]
    result=pool_scores(rows,heads,actors,dict(selection_sha256='verified'))
    assert result[0]['supported_components']==['factual_unavailable_zero']
    assert result[0]['new_model_evidence']['position']=='WR'
    assert result[1]['supported_components']==['explicit_selected_dst_expert']
    assert result[2]['supported_components']==['complete_dk_score_head']
    assert result[2]['new_model_evidence']['count_evidence']['player_model_components']['counts']['rush_attempts']==8.
    assert heads=={'rb':dict(mean=10.)}


def test_missing_dst_score_remains_unknown_without_crashing_or_old_score_substitution():
    from backend.app.product_services.primary_model_forecast import pool_scores
    r=pool_scores([dict(player_id='dst',position='DST',projection=None)],{},[],dict(selection_sha256='verified'))[0]
    assert r['conditional_mean'] is None and r['supported_components']==[]
    assert r['missing_evidence']==['Selected DST expert score unavailable']
