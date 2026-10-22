from copy import deepcopy
import pandas as pd
import pytest
from backend.app.product_services.offensive_volume_features import build_player_matrix, digest, FEATURES

PID='11111111-1111-4111-8111-111111111111'
OTHER='22222222-2222-4222-8222-222222222222'
CUT='2026-10-20T01:00:00+00:00'


def inputs():
    weekly=pd.DataFrame([dict(player_master_id=pid,source_player_id='native-'+str(i),team='SF',position='RB',period=202600+w,
        pass_attempts=0.,rush_attempts=float(5+i),targets=float(i),source_id=100*w+i,imported_at='2026-10-19T19:00:00+00:00')
        for w in range(1,6) for i,pid in enumerate([PID,OTHER])])
    block=dict(version='player_opportunity_components_v1',before_period=202606,forecast=None,
        provenance={'decision_cutoff_at':'2026-10-19T20:00:00+00:00'},semantic_measurements_sha256='source-measurements',
        actor_game_rows=[dict(game_id=f'2026_{w:02d}_WAS_SF',team='SF',source_player_id='native-0',player_master_id=PID,
            metrics={'targets':{'exact_within_log_sum':float(w),'observed_outcome_sum':float(w)}},shares={}) for w in range(1,6)],
        team_denominators=[dict(game_id=f'2026_{w:02d}_WAS_SF',team='SF') for w in range(1,6)])
    actors=[dict(player_master_id=PID,team='SF',position='RB')]
    return weekly,block,actors


def run(weekly,block,actors,**kwargs):
    return build_player_matrix(weekly,block,actors=actors,before_period=202606,cutoff=CUT,**kwargs)


def row(matrix,period=202606,pid=PID):
    return next(r for r in matrix['rows'] if r['period']==period and r['player_master_id']==pid)


def test_same_fixed_order_time_safety_current_labels_unknown_and_full_source_shares():
    weekly,block,actors=inputs();matrix=run(weekly,block,actors);r=row(matrix)
    assert list(r['features'])==list(FEATURES)
    assert r['features']['event_targets_mean3']==4.
    assert r['features']['event_targets_known3']==3
    assert r['features']['event_targets_unknown8']==3
    assert r['features']['rush_attempts_share3']==pytest.approx(5/11)
    assert all(v is None for v in r['labels'].values())
    assert max(r['history_periods'])<r['period']
    assert len(matrix['rows'])==11  # Includes zero-target original actors; no flattering outcome filter.
    assert matrix['original_pregame_availability_proven'] is False


def test_target_label_and_same_game_measurements_do_not_enter_own_features():
    weekly,block,actors=inputs();base=run(weekly,block,actors)
    weekly.loc[(weekly.player_master_id==PID)&weekly.period.eq(202604),'rush_attempts']=99.
    block['actor_game_rows'][3]['metrics']['targets']['exact_within_log_sum']=99.
    changed=run(weekly,block,actors)
    assert row(base,202604)['features']==row(changed,202604)['features']
    assert row(base,202605)['features']!=row(changed,202605)['features']


def test_known_zero_and_unknown_lower_bound_are_distinct():
    weekly,block,actors=inputs();block['actor_game_rows'][-1]['metrics']['targets']['exact_within_log_sum']=0.
    r=row(run(weekly,block,actors));assert r['features']['event_targets_mean3']==pytest.approx(7/3)
    block['actor_game_rows'][-1]['metrics']['targets']['exact_within_log_sum']=None
    r=row(run(weekly,block,actors));assert r['features']['event_targets_mean3'] is None
    assert r['features']['event_targets_known3']==2 and r['features']['event_targets_unknown3']==1


def test_absent_actor_and_other_team_history_never_become_zero_or_transfer():
    weekly,block,actors=inputs();actors=[dict(player_master_id=PID,team='WAS',position='RB')]
    r=row(run(weekly,block,actors));assert r['features']['rush_attempts_mean3'] is None
    assert r['features']['event_targets_mean3'] is None
    assert r['features']['event_targets_unknown3']==3


def test_history_position_is_lagged_not_target_label_role():
    weekly,block,actors=inputs();weekly.loc[(weekly.player_master_id==PID)&weekly.period.eq(202604),'position']='QB'
    r=row(run(weekly,block,actors),202604)
    assert r['features']['position_RB']==1 and r['features']['position_QB']==0


@pytest.mark.parametrize('mutation',['duplicate','future_period','future_clock','native_conflict'])
def test_invalid_component_identity_or_chronology_rejected(mutation):
    weekly,block,actors=inputs()
    if mutation=='duplicate':block['actor_game_rows'].append(deepcopy(block['actor_game_rows'][0]))
    if mutation=='future_period':block['actor_game_rows'][0]['game_id']='2026_06_WAS_SF'
    if mutation=='future_clock':block['provenance']['decision_cutoff_at']='2026-10-21T00:00:00+00:00'
    if mutation=='native_conflict':
        item=deepcopy(block['actor_game_rows'][0]);item['player_master_id']=OTHER;block['actor_game_rows'].append(item)
    with pytest.raises(ValueError):run(weekly,block,actors)


def test_offline_postlock_availability_remains_actual_and_cannot_be_live():
    weekly,block,actors=inputs();block['provenance']={'retrospective_read':{'original_evidence_boundary_at':'2026-10-19T20:00:00+00:00',
        'actual_read_at':'2026-10-20T00:20:00+00:00','actual_derived_at':'2026-10-20T00:21:00+00:00'}}
    block.update(evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False)
    m=run(weekly,block,actors);assert m['usage']=='offline_retrospective_model_inputs'
    assert m['provenance']['component_provenance']==block['provenance']
    with pytest.raises(ValueError,match='Postlock'):run(weekly,block,actors,usage='current_inference')


def test_exact_team_input_contract_is_copied_without_team_labels():
    weekly,block,actors=inputs();tm=dict(version='fixture',feature_columns=['game_total_line'],target_columns=['pass_attempts'],
        rows=[dict(game_id='2026_06_WAS_SF',team='SF',period=202606,features={'game_total_line':52.5},labels={'pass_attempts':999},context_periods=[202605])])
    tm['matrix_sha256']=digest(tm)
    r=row(run(weekly,block,actors,team_matrix=tm));assert r['features']['team_game_total_line']==52.5
    assert r['labels']['pass_attempts'] is None
    tm['rows'][0]['context_periods']=[202606];tm['matrix_sha256']=digest({k:v for k,v in tm.items() if k!='matrix_sha256'})
    with pytest.raises(ValueError,match='leaks'):run(weekly,block,actors,team_matrix=tm)


def test_observed_player_window_skips_absence_without_inventing_event_evidence():
    weekly,block,actors=inputs()
    weekly=weekly.loc[~(weekly.player_master_id.eq(PID)&weekly.period.isin([202603,202604]))]
    block['actor_game_rows']=[r for r in block['actor_game_rows'] if r['game_id'] not in {'2026_03_WAS_SF','2026_04_WAS_SF'}]
    legacy=row(run(weekly,block,actors))
    active=row(run(weekly,block,actors,event_window='observed_player_games'))
    assert legacy['features']['event_targets_known3']==1
    assert active['features']['event_targets_known3']==3
    assert active['features']['event_targets_mean3']==pytest.approx(8/3)
    assert active['features']['targets_mean3']==legacy['features']['targets_mean3']
    assert max(active['history_periods'])<202606
    # A missing metric in an observed game is still unknown, never backfilled.
    block['actor_game_rows'][0]['metrics']['targets']['exact_within_log_sum']=None
    missing=row(run(weekly,block,actors,event_window='observed_player_games'))
    assert missing['features']['event_targets_mean3'] is None
    assert missing['features']['event_targets_known3']==2
    assert missing['features']['event_targets_unknown3']==1
