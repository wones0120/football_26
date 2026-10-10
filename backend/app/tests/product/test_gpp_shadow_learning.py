from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest
from backend.app.product_services.gpp_shadow_learning import evaluate_snapshot, ShadowLearningService, refresh_after_import


def fixture(fmt='classic'):
    roster=[dict(player_id=str(i),roster_position='CPT' if fmt=='showdown' and i==0 else 'FLEX') for i in range(6 if fmt=='showdown' else 9)]
    snap=dict(contest_format=fmt,arms={'control':dict(roster=roster,forecast_points=100)})
    obs=[dict(player_id=p['player_id'],actual_points=15 if p['roster_position']=='CPT' else 10,roster_position=p['roster_position'],resolution_status='resolved') for p in roster]
    contest=dict(contest_id='x',contest_name='GPP',contest_type='gpp',field_size=3,places_paid=2,paid_places_source='draftkings_entry_history',entry_fee=5)
    histogram=[dict(entry_points=100,entries=1),dict(entry_points=50,entries=1),dict(entry_points=20,entries=1)]
    return snap,obs,[contest],{'x':histogram},{'x':[]}


def test_paid_finishes_without_fabricated_returns():
    result=evaluate_snapshot(*fixture())
    a=result['arms'][0]
    assert result['status']=='evaluated_from_imports'
    assert a['actual_points']==90 and a['known_paid_finishes']==1
    assert a['contests'][0]['net_return_bounds'] is None
    assert not result['live_selection_changed']


def test_captain_points_are_normalized_and_multiplied_exactly_once():
    assert evaluate_snapshot(*fixture('showdown'))['arms'][0]['actual_points']==65


def test_missing_or_conflicting_identity_never_becomes_zero():
    data=list(fixture()); data[1]=data[1][1:]
    assert evaluate_snapshot(*data)['status']=='pending_actuals'
    data=list(fixture());data[1].append(dict(data[1][0],actual_points=11))
    assert evaluate_snapshot(*data)['arms'][0]['missing_player_ids']==['0']


def test_incomplete_field_and_boundary_ties_remain_unknown():
    data=list(fixture());data[3]['x'].pop()
    assert evaluate_snapshot(*data)['status']=='pending_contest_evidence'
    data=list(fixture());data[3]['x'][1]['entry_points']=90
    assert evaluate_snapshot(*data)['arms'][0]['contests'][0]['paid_finish'] is None


def test_cash_contests_are_excluded():
    data=list(fixture());data[2][0].update(contest_type='cash',contest_name='Double Up')
    assert evaluate_snapshot(*data)['arms'][0]['contests']==[]


def test_registration_rejects_postlock_and_future_completion():
    service=ShadowLearningService(MagicMock())
    snap=fixture()[0]
    snap['first_kickoff_at']=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError,match='precede the first kickoff'):service.register(snap)
    snap['first_kickoff_at']=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    snap['arms']['control']['completed_at']=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError,match='precede registration'):service.register(snap)


def test_import_reports_refresh_failure_without_reversing_import():
    engine=MagicMock();engine.begin.side_effect=RuntimeError('unavailable')
    assert 'failed' in refresh_after_import(engine)


def test_api_contract_lists_and_retries_same_week():
    from unittest.mock import patch
    from backend.app.api.product_routes import get_shadow_comparisons, refresh_shadow_comparisons
    with patch('backend.app.product_services.gpp_shadow_learning.ShadowLearningService') as factory:
        service=factory.return_value
        service.latest.return_value=[{'experiment_id':'frozen','report_json':{'status':'pending_actuals'}}]
        assert get_shadow_comparisons(2026,5)['experiments'][0]['experiment_id']=='frozen'
        service.refresh.assert_not_called()
        assert refresh_shadow_comparisons(2026,5)==get_shadow_comparisons(2026,5)
        service.refresh.assert_called_once_with(season=2026,week=5)


def test_entry_history_import_refreshes_but_preview_does_not(tmp_path):
    from unittest.mock import patch
    from backend.app.tests.product.test_entry_history import csv_bytes
    from backend.app.product_services.entry_history import EntryHistoryService
    path=tmp_path/'history.csv';path.write_bytes(csv_bytes())
    service=EntryHistoryService(engine=MagicMock())
    service._ensure_schema=MagicMock();service.report=MagicMock(return_value={})
    with patch('backend.app.product_services.gpp_shadow_learning.refresh_after_import',return_value='refreshed') as refresh:
        service.import_file(path,2026,dry_run=True)
        refresh.assert_not_called()
        assert service.import_file(path,2026)['shadow_comparison_status']=='refreshed'
        refresh.assert_called_once_with(service.engine)


def test_individual_projection_errors_preserve_captain_slot_weighting():
    data=list(fixture('showdown'))
    data[0]['arms']['control']['roster'][0]['projection']=18
    result=evaluate_snapshot(*data)
    player=next(p for p in result['arms'][0]['player_projection_errors'] if p['captain'])
    assert player['actual_points']==15 and player['error']==-3
