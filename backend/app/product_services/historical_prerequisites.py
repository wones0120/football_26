"""Download only missing prior-week participation evidence before slate builds."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from Database.dst import normalize_team
from backend.app.schemas import NflReadPySeasonRequest
from backend.app.services.ingest import IngestService
from backend.app.services.source_capture import (SourceCaptureService,
    capture_nflreadpy_datasets, DEFAULT_NFLREADPY_LICENSE, _ingest_run_id)


def coverage(engine, *, season, week):
    args = dict(season=season, week=week)
    with engine.connect() as connection:
        schedule = connection.execute(text('SELECT week, home_team, away_team FROM raw_nfl_schedule WHERE season=:season AND week>=1 AND week<:week AND game_type=\'REG\''), args).mappings().all()
        stats = connection.execute(text('SELECT week, team, raw_row_json FROM raw_nfl_weekly_stat WHERE season=:season AND week>=1 AND week<:week'), args).mappings().all()
        snaps = connection.execute(text('SELECT week, team, game_type FROM raw_nfl_snap_count WHERE season=:season AND week>=1 AND week<:week'), args).mappings().all()
    result = {}
    for prior in range(1, week):
        expected = {normalize_team(row[key]) for row in schedule if row['week'] == prior for key in ('home_team', 'away_team') if row[key]}
        stat_teams = {normalize_team(row['team']) for row in stats if row['week'] == prior and row['raw_row_json'].get('season_type', 'REG') == 'REG'}
        snap_teams = {normalize_team(row['team']) for row in snaps if row['week'] == prior and row['game_type'] in ('REG', None)}
        result[prior] = dict(expected_teams=sorted(expected), missing_stats=sorted(expected-stat_teams), missing_snaps=sorted(expected-snap_teams))
        if not expected:
            raise ValueError(f'Prior-week history has no regular-season schedule for Week {prior}; refresh the schedule first')
    return result


def refresh_history(engine, *, season, week, slate, lock):
    before = coverage(engine, season=season, week=week)
    captured = []
    for prior, status in before.items():
        datasets = [dataset for dataset, key in [('weekly_stats', 'missing_stats'), ('snap_counts', 'missing_snaps')] if status[key]]
        for dataset in datasets:
            with Session(engine) as session:
                service = SourceCaptureService(session)
                capture = capture_nflreadpy_datasets(service, [dataset], season=season,
                    week=prior, slate=slate, slate_lock_at=lock,
                    source_license=DEFAULT_NFLREADPY_LICENSE)[0]
                # Ingest precisely the immutable captured payload, not a second fetch.
                import pandas as pd
                frame = pd.read_csv(capture.snapshot.artifact_path, low_memory=False)
                if frame.empty:
                    raise ValueError(f'nflverse {dataset} has no Week {prior} records yet; retry Prepare when the provider publishes them')
                team_column = 'recent_team' if 'recent_team' in frame.columns else 'team'
                published = {normalize_team(value) for value in frame[team_column].dropna()}
                missing = set(status['expected_teams']) - published
                if missing:
                    raise ValueError(f'nflverse {dataset} Week {prior} still lacks teams {sorted(missing)}; captured evidence retained, retry after publication')
                importer = getattr(IngestService(session), f'ingest_nflreadpy_{dataset}')
                ingest = importer(NflReadPySeasonRequest(season=season, weeks=[prior]),
                    source_frame=frame, source_path=capture.snapshot.artifact_path,
                    ingest_run_id=_ingest_run_id(capture.snapshot.snapshot_id))
                service.link_ingest_run(capture.snapshot.snapshot_id, ingest.ingest_run_id)
                if ingest.status != 'completed':
                    raise ValueError(f'Week {prior} {dataset} ingest failed: {ingest.error_message}')
                captured.append(dict(week=prior, dataset=dataset,
                    snapshot_id=str(capture.snapshot.snapshot_id), ingest_run_id=str(ingest.ingest_run_id),
                    rows=ingest.rows_raw, unresolved_rows=ingest.rows_unresolved))
    after = coverage(engine, season=season, week=week)
    missing = {prior: status for prior, status in after.items() if status['missing_stats'] or status['missing_snaps']}
    if missing:
        raise ValueError(f'Prior-week nflverse coverage remains incomplete after automatic refresh: {missing}; retry Prepare after source publication or review ingest identities')
    return dict(before=before, after=after, captures=captured, through_week=week-1)
