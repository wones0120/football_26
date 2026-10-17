"""Append-only, roster-scoped CSV upload checks; never final participation clearance.

The consumed research assessment remains immutable. This separate contract allows
an operationally valid upload before final inactives, without claiming entry,
contest assignment, strategy calibration, or confirmed game dressing.
"""
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

from .draftkings_export import DraftKingsExportService
from .evaluation_record import append_record, digest
from .official_injuries import parse_official_report, resolve_official_player
from .pregame_context import load_current_pregame_context
from .replay import parse_slate_lock
from .slate_preparation import aware

CONTRACT = 'saved_showdown_upload_clearance_v1'
KIND = 'draftkings_upload_clearance'
MAX_OFFICIAL_AGE = timedelta(hours=6)
MAX_CONTEXT_AGE = timedelta(hours=24)
VALID_FOR = timedelta(minutes=30)


def validate_inputs(job, evidence, now):
    """Pure validation of trusted, scope-bound current evidence and frozen rosters."""
    now = aware(now)
    errors = []
    rows = [r for lineup in job.results or [] for r in lineup]
    scope = dict(season=job.season, week=job.week, slate=job.slate.upper(), contest_format=job.contest_format)
    if job.status != 'completed' or job.contest_format != 'showdown' or not rows:
        errors.append('Requires a completed saved Showdown run with lineups.')
    if job.params.get('preliminary_report'):
        errors.append('Explicit preliminary research report remains blocked.')
    if evidence.get('scope') != scope:
        errors.append('Current evidence scope does not match the saved run.')
    prepared = job.params.get('prepared_input_evidence') or {}
    snapshot = (job.params.get('strategy_runtime') or {}).get('football_analyst', {}).get('input_snapshot')
    if not prepared or not snapshot:
        errors.append('Authenticated consumed preparation/model snapshot is missing.')
    else:
        from .analyst_shadow import validate_snapshot
        try:
            validate_snapshot(snapshot)
            expected = dict(season=job.season, week=job.week, slate_id=job.slate.upper(), format='SHOWDOWN')
            if any(snapshot['scope'].get(k) != v for k, v in expected.items()):
                raise ValueError('snapshot scope mismatch')
            if len(snapshot['scope']['game_ids']) != 1:
                raise ValueError('upload check requires one canonical game')
            if any(r.get('player_id') not in {p['player_master_id'] for p in snapshot['players']} or
                   r.get('canonical_game_id') not in snapshot['scope']['game_ids'] or
                   str(r.get('projection_run_id')) != str(job.projection_run_id) for r in rows):
                raise ValueError('saved roster projection/game lineage mismatch')
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(f'Consumed model validation failed: {exc}')
    lock = parse_slate_lock(r.get('game_id') for r in rows)
    if lock is None or now >= aware(lock):
        errors.append('Saved native game lock is missing or has passed.')
    official = evidence.get('official') or {}
    try:
        observed, received = aware(official['observed_at']), aware(official['received_at'])
        if not (timedelta(0) <= now-observed <= MAX_OFFICIAL_AGE) or received > now:
            raise ValueError('stale or future official observation')
        teams = {r.get('player_team') for r in rows}
        if not teams or not teams.issubset(set(official['teams'])) or not official.get('source_sha256'):
            raise ValueError('incomplete team report or unauthenticated source')
    except (KeyError, ValueError, TypeError) as exc:
        errors.append(f'Official availability evidence invalid: {exc}')
    current = evidence.get('players') or {}
    salary_sources = evidence.get('salary_sources') or {}
    exceptions = set(job.params.get('questionable_eligible_player_ids') or [])
    player_checks = []
    for pid in sorted({str(r.get('player_id')) for r in rows}):
        selected = [r for r in rows if str(r.get('player_id')) == pid]
        name = selected[0].get('name', pid)
        p = current.get(pid) or {}
        reasons = []
        try:
            UUID(pid)
            if p.get('availability_state') != 'AVAILABLE' or p.get('availability_status') not in {'ACT', 'ACTIVE', 'AVAILABLE'}:
                raise ValueError('current canonical availability is unknown or unavailable')
            if p.get('canonical_role') not in {'expected_starter', 'expected_backup', 'rotational', 'committee'}:
                raise ValueError('current canonical role is unresolved')
            for field in ('availability_observed_at', 'role_observed_at'):
                age = now-aware(p[field])
                if age < timedelta(0) or age > MAX_CONTEXT_AGE:
                    raise ValueError('stale/future canonical availability or role')
            if p.get('official_status') not in {None, '', 'ACTIVE'}:
                raise ValueError(f"current official designation {p['official_status']}")
            for r in selected:
                role = r.get('roster_position')
                native = (p.get('salaries') or {}).get(role) or {}
                native_id = r.get('dk_captain_id') if role == 'CPT' else r.get('dk_player_id')
                if not str(native_id or '').isdigit() or str(native.get('native_id')) != str(native_id):
                    raise ValueError(f'{role} native DraftKings ID missing or changed')
                if float(native.get('salary', -1)) != float(r['salary']) or native.get('game_info') != r.get('game_id'):
                    raise ValueError('current native salary/game differs from consumed roster; re-prepare and regenerate')
                if native.get('team') != r.get('player_team') or native.get('position') != r.get('position'):
                    raise ValueError('current canonical salary identity differs')
                if p.get('canonical_role') != r.get('canonical_role'):
                    raise ValueError('role changed since generation; review and regenerate')
                status = str(native.get('status') or '').upper()
                if status not in {'', 'ACT', 'ACTIVE', 'Q', 'QUESTIONABLE'}:
                    raise ValueError(f'native salary status {status} is not cleared')
                if status in {'Q', 'QUESTIONABLE'} or any(str(r.get(k) or '').upper() in {'Q', 'QUESTIONABLE'} for k in ('player_status','injury_status')):
                    if pid not in exceptions or not p.get('official_listed') or p.get('official_practice') != 'Full Participation in Practice' or p.get('official_status'):
                        raise ValueError('native questionable flag lacks this named exception and official full-practice/no-designation evidence')
                checksum = r.get('salary_source_checksum')
                if not checksum or salary_sources.get(r.get('salary_source_path')) != checksum:
                    raise ValueError('consumed native salary file missing or checksum changed')
        except (ValueError, KeyError, TypeError) as exc:
            reasons.append(str(exc)); errors.append(f'{name}: {exc}')
        player_checks.append(dict(player_id=pid, name=name, passed=not reasons, reasons=reasons,
                                  named_questionable_exception=pid in exceptions, current=p))
    try:
        DraftKingsExportService.build_lineup_download(contest_format='showdown', lineups=job.results or [], run_id=job.job_id)
    except ValueError as exc:
        errors.append(f'Native CSV roster validation failed: {exc}')
    # New captures renew evidence only through their real clocks. Equivalent
    # source recaptures do not invalidate another run; semantic status/native
    # changes do. Every download independently rechecks source freshness/hash.
    semantic_players = {pid:{**{k:p.get(k) for k in ('availability_state','availability_status',
        'canonical_role','official_listed','official_status','official_practice','official_player_key')},
        'salaries':{role:{k:s.get(k) for k in ('native_id','salary','team','position','game_info','status')}
                    for role,s in (p.get('salaries') or {}).items()}}
        for pid,p in current.items()}
    basis = dict(scope=scope, optimizer_run_id=job.job_id, projection_run_id=job.projection_run_id,
                 selected_rosters=job.results, consumed_preparation=prepared,
                 current_semantics=dict(players=semantic_players, salary_sources=salary_sources,
                    official_teams=official.get('teams'),official_source=official.get('source_uri')))
    return dict(contract=CONTRACT, optimizer_run_id=job.job_id, scope=scope,
        upload_ready=not errors, entry_ready=False, final_active_confirmed=False,
        status='BLOCKED' if errors else 'UPLOAD_READY_PENDING_INACTIVES',
        checked_at=now.isoformat(), valid_until=min(now+VALID_FOR, aware(lock)).isoformat() if lock else now.isoformat(),
        lock_at=aware(lock).isoformat() if lock else None, input_basis_sha256=digest(basis),
        reasons=errors, player_checks=player_checks,
        limitations=['Final official inactive reconciliation is pending; roster membership and no injury designation do not confirm game dressing.',
                     'Native IDs, roles, salary and slate are verified against the latest locally ingested DraftKings salary rows and immutable consumed file; live DraftKings draft-group publication is not verified.',
                     'No contest assignment, upload acceptance, submission, strategy EV or outcome is asserted.'],
        source_evidence=evidence)


def current_evidence(connection, job, now):
    scope = dict(season=job.season, week=job.week, slate=job.slate.upper(), contest_format=job.contest_format)
    args = dict(season=job.season, week=job.week, slate=job.slate, cutoff=now)
    salaries = [dict(r) for r in connection.execute(text('''SELECT DISTINCT ON (player_master_id,roster_position)
        player_master_id AS player_id,source_player_key AS native_id,roster_position,salary,team,position,game_info,
        player_status AS status,curated_salary_id,ingest_run_id FROM public.curated_salary
        WHERE season=:season AND week=:week AND upper(slate)=upper(:slate) AND source_system='draftkings'
        AND created_at AT TIME ZONE 'UTC' <= :cutoff
        AND EXISTS (SELECT 1 FROM public.ingest_run ir WHERE ir.ingest_run_id=curated_salary.ingest_run_id AND ir.status='completed')
        ORDER BY player_master_id,roster_position,created_at DESC,curated_salary_id DESC'''), args).mappings()]
    contexts = load_current_pregame_context(connection, **args)
    source = connection.execute(text('''SELECT * FROM public.source_snapshot WHERE season=:season AND week=:week
        AND upper(slate)=upper(:slate) AND dataset='official_injuries' AND source_system='nfl_official'
        AND observed_at<=:cutoff AND captured_at<=:cutoff ORDER BY captured_at DESC LIMIT 1'''), args).mappings().first()
    official, mapped = {}, {}
    if source:
        body = Path(source['artifact_path']).read_bytes()
        if hashlib.sha256(body).hexdigest() != source['content_sha256']:
            raise ValueError('Official report source hash mismatch')
        envelope = json.loads(body)
        if envelope.get('source_uri') != f'https://www.nfl.com/injuries/league/{job.season}/reg{job.week}':
            raise ValueError('Official report source scope mismatch')
        teams = {r.get('player_team') for lineup in job.results for r in lineup}
        report = parse_official_report(envelope['body'], season=job.season, week=job.week, slate_teams=teams)
        aliases = [dict(r) for r in connection.execute(text('''SELECT player_master_id,source_system,source_key,alias_name
            FROM public.player_alias WHERE source_system='nfl_official' ''' )).mappings()]
        identities = [{**r, 'player_name': '', 'full_name': ''} for r in salaries]
        # Resolve from canonical salary IDs + team/position/name, never display name alone.
        names = {str(c['player_master_id']):c['player_name'] for c in contexts}
        for r in identities: r['player_name'] = names.get(str(r['player_id']), '')
        for r in report:
            pid, method = resolve_official_player(r, identities, aliases)
            if pid: mapped[str(pid)] = {**r, 'identity_match': method}
            elif r['position'] in {'QB','RB','WR','TE','K'}:
                raise ValueError('Official offensive identity unresolved: '+r['source_key'])
        official = dict(snapshot_id=str(source['snapshot_id']), source_sha256=source['content_sha256'],
            source_uri=source['source_uri'], observed_at=envelope['observed_at'], received_at=envelope['received_at'],
            teams=sorted({r['team'] for r in report}), artifact_path=source['artifact_path'])
    players = {}
    for c in contexts:
        pid = str(c['player_master_id']); e = c.get('evidence_json') or {}; o = mapped.get(pid) or {}
        players[pid] = {k:e.get(k) for k in ('availability_state','availability_status','availability_observed_at',
            'canonical_role','role_observed_at','availability_source_ids','role_source_ids')}
        players[pid].update(context_run_id=str(c['context_run_id']), official_listed=pid in mapped,
            official_status=o.get('game_status'), official_practice=o.get('practice_status'),
            official_player_key=o.get('source_key'), official_identity_match=o.get('identity_match'),
            salaries={r['roster_position']:{k:str(v) if k in {'player_id','ingest_run_id'} else v for k,v in r.items()}
                      for r in salaries if str(r['player_id']) == pid})
    selected_ids = {str(r['player_id']) for lineup in job.results for r in lineup}
    paths = {r.get('salary_source_path') for lineup in job.results for r in lineup}
    checksums = {path:hashlib.sha256(Path(path).read_bytes()).hexdigest() if path and Path(path).is_file() else None for path in paths}
    return dict(scope=scope, official=official, players={k:v for k,v in players.items() if k in selected_ids}, salary_sources=checksums)


def assess(engine, job, *, refresh=False, now=None):
    now = aware(now or datetime.now(UTC))
    if refresh:
        from .official_injuries import refresh_official_injuries
        teams = sorted({r.get('player_team') for l in job.results or [] for r in l})
        lock = parse_slate_lock(r.get('game_id') for l in job.results or [] for r in l)
        if job.contest_format != 'showdown' or len(teams) != 2 or lock is None or now >= aware(lock):
            raise ValueError('Requires a pre-lock, single-game saved Showdown run')
        refresh_official_injuries(engine, season=job.season, week=job.week, slate=job.slate,
            games=[dict(home_team=teams[0],away_team=teams[1])], slate_lock_at=aware(lock))
        # The official supplement is not a complete canonical role context.
        # Compose it with existing immutable roster/depth evidence before reading
        # the latest player context; otherwise a blank designation hides roles.
        from .showdown_player_context import refresh_canonical_context
        refresh_canonical_context(engine, season=job.season, week=job.week, slate=job.slate)
        now = datetime.now(UTC)
    with engine.connect() as connection:
        evidence = current_evidence(connection, job, now)
    return validate_inputs(job, evidence, now)


def issue_clearance(engine, job):
    value = assess(engine, job, refresh=True)
    with engine.begin() as connection:
        record_id = append_record(connection, KIND, value, run_id=job.job_id,
            source={'operation':'check_saved_upload_readiness','contract':CONTRACT})
    return {**value, 'record_id':record_id}


def require_clearance(engine, job):
    if engine is None:
        raise ValueError('Check upload readiness for this saved run before downloading.')
    with engine.connect() as connection:
        row = connection.execute(text('''SELECT record_id,record_json FROM target.evaluation_record
            WHERE optimizer_run_id=:id AND kind=:kind ORDER BY recorded_at DESC,record_id DESC LIMIT 1'''),
            dict(id=job.job_id,kind=KIND)).mappings().first()
    if not row:
        raise ValueError('Check upload readiness for this saved run before downloading.')
    if row['record_id'] != 'evaluation-'+digest(row['record_json']):
        raise ValueError('Upload clearance artifact hash mismatch')
    stored = row['record_json']['payload']; now = datetime.now(UTC)
    if stored.get('contract') != CONTRACT or stored.get('optimizer_run_id') != job.job_id or stored.get('upload_ready') is not True or aware(stored['valid_until']) <= now:
        raise ValueError('Saved upload check is blocked or expired. Check upload readiness again.')
    current = assess(engine, job, now=now)
    if not current['upload_ready'] or stored.get('input_basis_sha256') != current['input_basis_sha256']:
        raise ValueError('Saved inputs or current evidence changed; check upload readiness again. '+ '; '.join(current['reasons']))
    return row['record_id']
