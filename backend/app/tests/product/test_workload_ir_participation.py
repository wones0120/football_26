import pandas as pd
import pytest

from backend.app.product_services.workload_ir_participation import parse_ir_return
from backend.app.product_services.workload_count_forecast import forecast
from backend.app.tests.product.test_workload_count_forecast import history, actors, MODEL


ACTOR = dict(team='NE', position='WR', player_name='A.J. Brown')
HTML = '''<div class="nfl-c-article__dates">Oct 17, 2026 at 04:00 PM</div>
<p>The New England Patriots announced today that WR A.J. Brown has been activated to the 53-man roster.
He was placed on injured reserve on September 12 following the season-opener.</p>'''


def test_closed_ir_interval_requires_explicit_placement_return_and_identity():
    assert parse_ir_return(HTML, ACTOR) == dict(entered_at='2026-09-12', returned_at='2026-10-17')
    for changed in [dict(team='CHI'), dict(position='RB'), dict(player_name='Ben Brown')]:
        with pytest.raises(ValueError, match='identity|team/position/name'):
            parse_ir_return(HTML, {**ACTOR, **changed})
    for changed in [HTML.replace('September 12', 'October 18'), HTML.replace('injured reserve', 'the roster'),
                    HTML.replace('Oct 17, 2026 at 04:00 PM', '')]:
        with pytest.raises(ValueError):
            parse_ir_return(changed, ACTOR)


def sparse_history():
    frame = history()
    return frame.loc[~(frame.player_master_id.eq('Aw') & frame.period.between(202502, 202507))].copy()


def test_two_game_return_keeps_original_counts_requires_every_gap_and_current_role():
    frame = sparse_history(); original = frame.copy(deep=True)
    people = actors(); people[2]['current_role_evidence'] = dict(source_ids=['official-role'], source_uri='https://club.example/depth')
    proofs = [dict(kind='official_ir_interval_v1', player_master_id='Aw', team='A', period=p)
              for p in range(202502, 202508)]
    for evidence in [[], proofs[:-1], [{**p, 'team':'B'} for p in proofs], [{**p, 'kind':'roster_blank'} for p in proofs]]:
        result = forecast(frame, people, before_period=202509, model=MODEL, verified_gaps=evidence)
        assert result['players'][2]['counts']['targets'] is None
    result = forecast(frame, people, before_period=202509, model=MODEL, verified_gaps=proofs)
    receiver = result['players'][2]
    assert receiver['history_window_status'] == 'sparse_two_active_games_across_verified_inactive_gaps'
    assert receiver['raw_history']['targets']['periods'] == [202501, 202508]
    assert receiver['raw_history']['targets']['values'] == [20., 20.]
    assert receiver['counts']['targets'] is not None
    assert 'Sparse two-game' in receiver['reasons'][0]
    assert receiver['verified_inactive_gaps'] == proofs
    assert result['history_evidence']['actors'][2]['role_window']['observed_game_count'] == 2
    assert forecast(frame, actors(), before_period=202509, model=MODEL, verified_gaps=proofs)['players'][2]['counts']['targets'] is None
    one = frame.loc[~(frame.player_master_id.eq('Aw') & frame.period.eq(202501))]
    assert forecast(one, people, before_period=202509, model=MODEL, verified_gaps=proofs)['players'][2]['counts']['targets'] is None
    pd.testing.assert_frame_equal(frame, original)
    for team, budget in result['teams'].items():
        for channel in ('pass_attempts', 'rush_attempts', 'targets'):
            assert sum(p['counts'][channel] for p in result['players'] if p['team']==team and p['counts'][channel] is not None) <= budget[channel]+1e-8


def test_two_contiguous_games_without_absence_do_not_relax_regular_history_gate():
    frame = history().loc[lambda f: ~f.player_master_id.eq('Aw') | f.period.ge(202507)]
    assert forecast(frame, actors(), before_period=202509, model=MODEL)['players'][2]['counts']['targets'] is None


def test_prepared_receipt_retains_real_raw_ir_and_derived_gamebook_source_ids(monkeypatch):
    from datetime import UTC, datetime
    from backend.app.product_services import workload_count_forecast as service
    frame=history();frame['source_id']=range(len(frame));frame['source_player_id']=frame.player_master_id
    frame['team']=frame.team.map({'A':'NE','B':'CHI'})
    monkeypatch.setattr(service,'load_history',lambda *a,**k:frame)
    monkeypatch.setattr(service,'fit_team_model',lambda *a,**k:MODEL)
    monkeypatch.setattr('backend.app.product_services.workload_gamebook_participation.load_verified_gaps',lambda *a,**k:[
        dict(kind='official_ir_interval_v1',player_master_id='Aw',team='NE',period=202507,source_snapshot_id='ir-raw'),
        dict(kind='official_gamebook_not_active_v1',player_master_id='Aq',team='NE',period=202507,source_snapshot_id='pdf-raw',derived_snapshot_id='gamebook-derived')])
    result=service.prepare_receipt(None,[dict(player_id='Aw',player_team='NE',position='WR')],season=2025,week=9,
        cutoff=datetime(2025,11,1,tzinfo=UTC),projection_run_id='projection-fixture')
    assert result['verified_gap_source_ids']==['gamebook-derived','ir-raw']
    assert next(p for p in result['players'] if p['player_master_id']=='Aw')['counts']['targets'] is not None
