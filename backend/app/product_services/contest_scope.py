"""Verify imported contest dates against saved account and schedule evidence."""
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from .entry_history import load_history


def verify_history_scope(history, schedules, *, contest_id, season, week):
    dates = {row['contest_date_est'] for row in history if row['contest_id'] == str(contest_id) and row['sport'] == 'NFL'}
    if len(dates) != 1:
        return {'status': 'missing' if not dates else 'conflict', 'reason': 'unique_contest_date_unavailable'}
    date = next(iter(dates))
    # DraftKings labels this EST, including daylight time. Interpret as New York.
    lock = datetime.fromisoformat(date).replace(tzinfo=ZoneInfo('America/New_York'))
    matches = [row for row in schedules if str(row.get('game_date')) == date[:10]]
    scopes = {(int(row['season']), int(row['week'])) for row in matches}
    if len(scopes) != 1:
        return {'status': 'missing' if not scopes else 'conflict', 'reason': 'unique_schedule_week_unavailable', 'contest_date': date}
    verified = next(iter(scopes))
    return {'status': 'verified' if verified == (season, week) else 'conflict',
            'season': verified[0], 'week': verified[1], 'lock_at': lock.isoformat(),
            'basis': 'entry_history_native_contest_id_and_saved_schedule_date',
            'schedule_game_ids': sorted({r['game_id'] for r in matches})}


def saved_history_scope(connection, contest_id, season, week):
    history, _, _ = load_history(connection)
    schedules = [dict(r) for r in connection.execute(text('''SELECT DISTINCT season,week,game_id,
        raw_row_json->>'gameday' AS game_date FROM public.raw_nfl_schedule WHERE season=:season'''),
        {'season': season}).mappings()]
    return verify_history_scope(history, schedules, contest_id=contest_id, season=season, week=week)
