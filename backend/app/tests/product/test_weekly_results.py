from copy import deepcopy
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.app.api import product_routes
from backend.app.product_services.weekly_results import WeeklyResultsService, build_weekly_results, financial_totals


def fixture():
    observed = [dict(contest_id='c1', entry_id='e1', slate='SUNDAY_MAIN', contest_name='Pylon', entry_fee=None),
                dict(contest_id='c1', entry_id='e2', slate='SUNDAY_MAIN', contest_name='Pylon', entry_fee=3)]
    history = [dict(contest_id='c1', entry_id='e1', sport='NFL', contest_name='Pylon',
                    entry_fee=3, cash_winnings=8, ticket_winnings=0),
               dict(contest_id='c1', entry_id='e2', sport='NFL', contest_name='Pylon',
                    entry_fee=3, cash_winnings=0, ticket_winnings=0)]
    reports = [dict(slate='SUNDAY_MAIN', report_id='saved-review', created_at='2026-10-13T12:00:00Z',
        entries=deepcopy(observed), missing_evidence=['entry:c1:e1:contest_entry_assignment',
                                           'entry:c1:e1:ambiguous_saved_lineup_matches'])]
    return observed, history, [], [dict(content_sha256='history-sha', entries_json=deepcopy(history))], reports


def build(parts):
    return build_weekly_results(*parts, season=2026, week=5, entry_user='wones0120', available_weeks=[5, 4])


def test_current_history_totals_drilldowns_and_saved_warnings():
    parts = fixture()
    before = deepcopy(parts)
    result = build(parts)
    assert result['summary']['fees'] == 6 and result['summary']['winnings'] == 8
    assert result['summary']['net_profit'] == 2
    assert result['summary']['roi'] == pytest.approx(1 / 3)
    assert result['summary']['cash_rate'] == .5
    assert result['summary']['financial_complete_entries'] == 2
    assert result['slates'][0]['missing_evidence'] == parts[-1][0]['missing_evidence']
    contest = result['slates'][0]['contests'][0]
    assert contest['summary'] == result['summary']
    assert [e['entry_id'] for e in contest['entries']] == ['e1', 'e2']
    assert all(e['source_hashes'] == ['history-sha'] for e in contest['entries'])
    assert parts == before


def test_missing_winnings_are_not_zero_and_known_subtotals_remain_visible():
    observed, history, conflicts, sources, reports = fixture()
    result = build((observed, history[:1], conflicts, sources, reports))
    s = result['summary']
    assert s['fees'] == 6 and s['known_fees'] == 6
    assert s['known_winnings'] == 8 and s['winnings'] is None
    assert s['net_profit'] is None and s['roi'] is None and s['cash_rate'] is None
    assert s['known_net_profit'] == 5 and s['financial_complete_entries'] == 1
    assert result['slates'][0]['contests'][0]['entries'][1]['cash_winnings'] is None
    assert 'zero winnings are not assumed' in result['warnings'][0]


def test_conflicts_withhold_finances_instead_of_reusing_old_report_or_contest_fee():
    observed, history, _, sources, reports = fixture()
    result = build((observed, history, [('c1', 'e2')], sources, reports))
    entry = result['slates'][0]['contests'][0]['entries'][1]
    assert entry['entry_fee'] is None and entry['cash_winnings'] is None
    assert result['summary']['roi'] is None
    assert any('Conflicting' in warning for warning in entry['warnings'])


def test_free_ticket_prizes_empty_weeks_and_zero_denominators():
    zero = financial_totals([dict(entry_fee=0, cash_winnings=2, ticket_winnings=10)])
    assert zero['net_profit'] == 2 and zero['roi'] is None
    assert zero['cash_rate'] == 1 and zero['known_free_entries'] == 1
    ticket = financial_totals([dict(entry_fee=1, cash_winnings=0, ticket_winnings=10)])
    assert ticket['net_profit'] == -1 and ticket['cash_rate'] == 0 and ticket['ticket_winnings'] == 10
    empty = build(([], [], [], [], []))
    assert empty['summary']['entries'] == 0 and empty['summary']['roi'] is None
    assert empty['summary']['fees'] is None and empty['summary']['cash_rate'] is None


def test_identical_rosters_and_entry_ids_in_different_contests_count_by_native_pair():
    observed, history, conflicts, sources, reports = fixture()
    observed += [dict(observed[0], contest_id='c2'), dict(observed[0])]
    history.append(dict(history[0], contest_id='c2'))
    result = build((observed, history, conflicts, sources, reports))
    assert result['summary']['entries'] == 3 and result['summary']['fees'] == 9
    assert len(result['slates'][0]['contests']) == 2
    assert any('absent from' in w for w in result['warnings'])


def test_overlap_provenance_deduplicates_and_missing_saved_review_is_explicit():
    observed, history, conflicts, sources, _ = fixture()
    sources += [deepcopy(sources[0]), dict(content_sha256='second-sha', entries_json=history)]
    result = build((observed, history, conflicts, sources, []))
    assert result['summary']['entries'] == 2 and result['summary']['fees'] == 6
    assert result['slates'][0]['contests'][0]['entries'][0]['source_hashes'] == ['history-sha', 'second-sha']
    assert any('Saved learning review unavailable' in w for w in result['warnings'])


def test_week_five_financial_regression_matches_16_entries_without_averaging_roi():
    data = [('THURSDAY_NIGHT', 'c1', [(3, 0)]), ('THURSDAY_NIGHT', 'c2', [(3, 0)]),
            ('THURSDAY_NIGHT', 'c3', [(1, 0)]), ('SUNDAY_MORNING', 'c4', [(1, 2)]),
            ('SUNDAY_EARLY', 'c5', [(1, 1.5)]), ('SUNDAY_MAIN', 'c6', [(3, 0)]),
            ('SUNDAY_LATE', 'c7', [(.5, 0)]), ('SUNDAY_LATE', 'c8', [(1, 1.5)]),
            ('SUNDAY_LATE_SF_SEA', 'c9', [(1, 1.5)]), ('SUNDAY_LATE_SF_SEA', 'c10', [(1, 0)]),
            ('SUNDAY_NIGHT', 'c11', [(3, 0)]), ('MONDAY_NIGHT', 'c12', [(3, 0)]),
            ('MONDAY_NIGHT', 'c13', [(1, 0)] * 4)]
    observed, history = [], []
    for slate, cid, amounts in data:
        for n, (fee, cash) in enumerate(amounts):
            observed.append(dict(contest_id=cid, entry_id=str(n), slate=slate, contest_name=cid))
            history.append(dict(contest_id=cid, entry_id=str(n), sport='NFL', contest_name=cid,
                                entry_fee=fee, cash_winnings=cash, ticket_winnings=0))
    result = build((observed, history, [], [], []))
    s = result['summary']
    assert s['entries'] == 16 and s['fees'] == 25.5 and s['winnings'] == 6.5
    assert s['net_profit'] == -19 and s['roi'] == pytest.approx(-19 / 25.5)
    assert s['cash_rate'] == .25
    assert sum(len(slate['contests']) for slate in result['slates']) == 13


def test_service_uses_only_reads_and_scopes_user_season_week_with_latest_saved_versions():
    observed, history, conflicts, sources, reports = fixture()
    engine = MagicMock()
    service = WeeklyResultsService(engine)
    service._rows = MagicMock(side_effect=[[{'week': 5}], observed, reports])
    with patch('backend.app.product_services.weekly_results.validate_target_schema'), \
         patch('backend.app.product_services.weekly_results.load_history', return_value=(history, conflicts, sources)):
        result = service.report(season=2026, week=5, entry_user=' wones0120 ')
    assert result['summary']['fees'] == 6
    engine.begin.assert_not_called()
    sql = [call.args[1] for call in service._rows.call_args_list]
    assert all(':entry_user' in q and ':season' in q for q in sql)
    assert 'contest.week=:week' in sql[1]
    assert 'DISTINCT ON (upper(report.slate))' in sql[2]
    assert 'created_at DESC' in sql[2] and 'candidate' not in sql[2]


def test_weekly_results_get_contract_and_validation():
    app = FastAPI(); app.include_router(product_routes.router)
    client = TestClient(app)
    with patch.object(product_routes, 'WeeklyResultsService') as service:
        service.return_value.report.return_value = build(fixture())
        response = client.get('/api/learning/results/weekly', params=dict(season=2026, week=5, entry_user='wones0120'))
        assert response.status_code == 200 and response.json()['summary']['cash_rate'] == .5
        service.return_value.report.assert_called_once_with(season=2026, week=5, entry_user='wones0120')
        assert client.get('/api/learning/results/weekly', params=dict(season=2026, week=26, entry_user='wones0120')).status_code == 422
        service.return_value.report.side_effect = ValueError('DraftKings username is required')
        assert client.get('/api/learning/results/weekly', params=dict(season=2026, week=5, entry_user=' ')).status_code == 422
