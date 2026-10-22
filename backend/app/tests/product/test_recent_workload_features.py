from copy import deepcopy
import pandas as pd
import pytest

from backend.app.product_services.recent_workload_features import build_recent_workload_features

PID='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
OTHER='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
CUTOFF='2026-10-20T02:00:00+00:00'


def rows():
    return pd.DataFrame([dict(player_master_id=pid, source_player_id=pid, team='WAS', position='RB',
        period=202600+w, pass_attempts=0, rush_attempts=w, targets=0,
        source_id=w*10+i, imported_at='2026-10-19T20:00:00+00:00')
        for w in range(1,9) for i,pid in enumerate((PID,OTHER))])


def run(frame, actors=None):
    return build_recent_workload_features(frame, actors or [dict(player_master_id=PID,team='WAS')],
        before_period=202609,cutoff=CUTOFF)


def channel(result,mid='G22-M01',c='rush_attempts'):
    return result['actors'][0]['metrics'][mid]['channels'][c]


def test_declared_overlapping_windows_and_known_zero():
    result=run(rows()); value=channel(result)
    assert value['recent']['mean']==8
    assert value['reference']['mean']==4.5
    assert value['difference']==3.5
    assert channel(result,'G22-M02')['recent']['mean']==7
    assert channel(result,c='targets')['difference']==0
    assert channel(result,c='targets')['ratio'] is None
    assert channel(result,c='targets')['ratio_reason']=='zero_reference'


def test_missing_participant_is_unknown_not_zero_or_last_observed():
    frame=rows();frame=frame.loc[~(frame.player_master_id.eq(PID)&frame.period.eq(202608))]
    value=channel(run(frame))
    assert value['recent']['mean'] is None
    assert value['recent']['unknown_periods']==[202608]
    assert value['reference']['known_games']==7


def test_prior_season_and_other_team_do_not_fill_window():
    frame=rows();frame.loc[frame.player_master_id.eq(PID)&frame.period.lt(202605),'team']='SF'
    extra=deepcopy(frame.iloc[[0]]);extra['period']=202518
    value=channel(run(pd.concat([frame,extra])))
    assert value['reference']['mean'] is None
    assert value['reference']['unknown_periods']==[202601,202602,202603,202604]


def test_insufficient_team_periods_unknown_and_target_rows_excluded():
    frame=rows().loc[lambda f:f.period.ge(202607)].copy()
    assert channel(run(frame))['reference']['mean'] is None
    extra=deepcopy(frame.iloc[[0]]);extra['period']=202609;extra['rush_attempts']=999
    assert run(pd.concat([frame,extra]))['semantic_sha256']==run(frame)['semantic_sha256']


def test_null_channel_remains_unknown():
    frame=rows();frame.loc[frame.player_master_id.eq(PID)&frame.period.eq(202606),'targets']=None
    assert channel(run(frame),'G22-M02','targets')['difference'] is None


def test_source_recapture_provenance_does_not_change_values():
    frame=rows(); result=run(frame)
    frame['source_id']+=10000;frame['imported_at']='2026-10-20T01:00:00+00:00'
    changed=run(frame)
    assert result['semantic_sha256']==changed['semantic_sha256']
    assert result['provenance']!=changed['provenance']


def test_input_actor_and_source_row_order_are_not_semantic():
    actors=[dict(player_master_id=PID,team='WAS'),dict(player_master_id=OTHER,team='WAS')]
    assert run(rows(),actors)['semantic_sha256']==run(rows().iloc[::-1],actors[::-1])['semantic_sha256']


def test_missing_receipt_clock_cannot_establish_cutoff_bound_source():
    with pytest.raises(ValueError,match='receipt/import clock'):
        run(rows().drop(columns='imported_at'))


def test_duplicate_canonical_spelling_and_future_import_rejected():
    frame=rows();frame.loc[frame.player_master_id.eq(PID),'player_master_id']=PID.upper()
    extra=deepcopy(frame.iloc[[0]]);extra['player_master_id']=PID;extra['source_player_id']='other'
    with pytest.raises(ValueError,match='Duplicate canonical'):
        run(pd.concat([frame,extra]))
    frame=rows();frame['imported_at']='2026-10-21T01:00:00+00:00'
    with pytest.raises(ValueError,match='after decision cutoff'):run(frame)


@pytest.mark.parametrize('period',[True,202600,202619])
def test_invalid_scope(period):
    with pytest.raises(ValueError,match='REG'):
        build_recent_workload_features(rows(),[],before_period=period,cutoff=CUTOFF)
