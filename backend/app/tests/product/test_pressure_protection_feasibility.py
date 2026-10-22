from research.pressure_protection_feasibility_20261020.v1.assess import _pool,_bin,_compatible,_contrast_count


def test_missing_scheduled_prior_is_not_skipped_from_pressure_pool():
    a=dict(full_observed_cohort_proven=True,known_dropbacks=10,known_source_pressure_sum=2)
    assert _pool([a])==.2
    assert _pool([a,None])is None
    assert _pool([a,dict(a,full_observed_cohort_proven=False)])is None


def test_reference_labels_are_unavailable_early_or_with_degenerate_cutpoints():
    assert _bin(.2,(.1,.3),False)is None
    assert _bin(.2,(.2,.2),True)is None
    assert _bin(.1,(.1,.3),True)=='low'
    assert _bin(.3,(.1,.3),True)=='high'


def test_unknown_axis_masks_only_compatible_personnel_pressure_cells():
    assert _compatible(('unchanged_five',None,'high'),('unchanged_five','low','high'))
    assert not _compatible(('changed_native_CGT_members',None,'high'),('unchanged_five','low','high'))
    assert not _compatible(('unchanged_five',None,'high'),('unchanged_five','low','low'))


def test_actual_contrast_requires_both_opponent_axes_within_same_personnel_own_context():
    rows=[dict(condition=('unchanged_five','low','low'),response_known=True,pressure_sum=2,dropbacks=10),dict(condition=('unchanged_five','low','high'),response_known=True,pressure_sum=8,dropbacks=20)]
    assert _contrast_count(rows)==1
    assert _contrast_count(rows+[dict(condition=('unchanged_five',None,'high'),response_known=True,pressure_sum=1,dropbacks=5)])==0
    assert _contrast_count(rows+[dict(condition=('changed_native_CGT_members',None,'high'),response_known=True,pressure_sum=1,dropbacks=5)])==1
    assert _contrast_count([rows[0]])==0


def test_actual_normalized_schedule_shape_and_immediate_prior_unit_are_consumed():
    from research.pressure_protection_feasibility_20261020.v1.assess import assess
    import pytest
    games=[dict(game_id=f'2023_{week:02d}_BUF_MIA',season=2023,week=week,game_type='REG',game_date=day,home_team='MIA',away_team='BUF')for week,day in ((1,'2023-09-10'),(4,'2023-10-01'))]
    rows=[dict(game_id=g['game_id'],season=2023,week=g['week'],offense=t,defense=o,full_observed_cohort_proven=True,known_dropbacks=10,known_source_pressure_sum=2 if t=='BUF'else 6)for g in games for t,o in (('BUF','MIA'),('MIA','BUF'))]
    line=dict(continuity_rows=[dict(game_id=g['game_id'],team=t,previous_same_season_game_id=games[0]['game_id']if g['week']==4 else None,canonical_qualified_value=1 if g['week']==4 else None)for g in games for t in ('BUF','MIA')])
    r=assess(dict(game_rows=rows),[line],games)
    assert all(None in x['condition']for x in r['game_contexts']if x['week']==1)
    assert all(None not in x['condition']for x in r['game_contexts']if x['week']==4)
    assert r['catalog_ids_completed']==[]
    line['continuity_rows'][-1]['previous_same_season_game_id']='2023_02_OTHER_UNKNOWN'
    with pytest.raises(ValueError,match='No skip'):
        assess(dict(game_rows=rows),[line],games)
