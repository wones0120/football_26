from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from backend.app.services.lineup_learning import LineupLearningService
from backend.app.product_services.dst_scoring_reconciliation import DstScoringUnresolved


def game(home, away, day, scores=None):
    payload = dict(gameday=day, gametime='13:00', home_score=None, away_score=None)
    if scores is not None:
        payload.update(home_score=scores[0], away_score=scores[1])
    return SimpleNamespace(game_id=f'2026_06_{away}_{home}', home_team=home,
                           away_team=away, raw_row_json=payload)


def service(rows):
    obj = LineupLearningService.__new__(LineupLearningService)
    obj._dst_actual_cache = {}
    obj.session = MagicMock()
    schedule = MagicMock()
    schedule.scalars.return_value.all.return_value = rows
    weekly = MagicMock()
    weekly.all.return_value = []
    obj.session.execute.side_effect = lambda statement: schedule if 'raw_nfl_schedule' in str(statement) else weekly
    return obj


def test_future_slate_is_not_blocked_by_unrelated_completed_game_and_cache_is_scoped():
    obj = service([game('DEN', 'SEA', '2020-10-15'), game('PHI', 'CAR', '2099-10-18')])
    assert obj._compute_dst_actual_points(season=2026, week=6, teams={'PHI', 'CAR'}) == {}
    with pytest.raises(DstScoringUnresolved, match='refusing zero'):
        obj._compute_dst_actual_points(season=2026, week=6, teams={'SEA', 'DEN'})
    with pytest.raises(DstScoringUnresolved, match='refusing zero'):
        obj._compute_dst_actual_points(season=2026, week=6)


def test_requested_completed_game_still_requires_weekly_counters():
    obj = service([game('PHI', 'CAR', '2020-10-15', (21, 14))])
    with pytest.raises(DstScoringUnresolved, match='weekly-stat coverage'):
        obj._compute_dst_actual_points(season=2026, week=6, teams={'PHI', 'CAR'})


def test_requested_team_missing_schedule_is_explicit():
    obj = service([game('PHI', 'CAR', '2099-10-18')])
    with pytest.raises(ValueError, match='Missing schedule evidence.*LAR'):
        obj._compute_dst_actual_points(season=2026, week=6, teams={'LA'})


def test_pool_passes_canonical_salary_scope():
    obj = service([])
    obj.session.execute.return_value.scalars.return_value.all.return_value = [SimpleNamespace(team='LA'), SimpleNamespace(team='ARI')]
    obj.session.execute.side_effect = None
    obj._compute_dst_actual_points = MagicMock(side_effect=RuntimeError('scope checkpoint'))
    with pytest.raises(RuntimeError, match='scope checkpoint'):
        obj._fetch_slate_player_pool(source_system='draftkings', season=2026, week=6, slate='SUNDAY_MAIN')
    assert obj._compute_dst_actual_points.call_args.kwargs['teams'] == {'LAR', 'ARI'}
