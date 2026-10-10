"""Supplement unresolved Classic facts from current official club tables."""
from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urljoin

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from Database.player_identity import normalize_player_name, normalize_position
from .official_injuries import _Document, observation_clock, resolve_official_player, _record_identity
from .pregame_context import PregameContextService, load_current_pregame_context
from .showdown_player_context import compose_player_contexts, CONTEXT_CONTRACT, retained_workload_context
from .slate_preparation import SlatePreparationRequest, slate_games, require_prelock
from ..config import get_settings
from ..services.source_capture import SourceCaptureService

# Official club source endpoints, independent of slate/player selections.
CLUBS = dict(ARI='azcardinals', ATL='atlantafalcons', BAL='baltimoreravens', BUF='buffalobills',
    CAR='panthers', CHI='chicagobears', CIN='bengals', CLE='clevelandbrowns', DAL='dallascowboys',
    DEN='denverbroncos', DET='detroitlions', GB='packers', HOU='houstontexans', IND='colts',
    JAX='jaguars', KC='chiefs', LV='raiders', LAC='chargers', LAR='therams', MIA='miamidolphins',
    MIN='vikings', NE='patriots', NO='neworleanssaints', NYG='giants', NYJ='newyorkjets',
    PHI='philadelphiaeagles', PIT='steelers', SF='49ers', SEA='seahawks', TB='buccaneers',
    TEN='tennesseetitans', WAS='commanders')


def parse_club_tables(html, *, team, uri, kind):
    """Require explicit roster sections or depth columns; absence proves nothing."""
    document = _Document(html).root
    section = ''
    result = []
    def walk(node):
        nonlocal section
        if node.tag in {'h2', 'h3', 'h4'}:
            section = node.content().lower()
        if node.tag == 'table':
            header = [n.content() for n in node.find('th')]
            for tr in node.find('tr'):
                cells = list(tr.find('td'))
                if not cells or len(cells) != len(header):
                    continue
                if kind == 'roster' and 'Player' in header and 'Pos' in header:
                    status = ('PS' if 'practice squad' in section else 'IR' if 'injured' in section else
                        'PUP' if 'physically' in section else 'NFI' if 'non-football' in section else
                        'SUSP' if 'suspend' in section else 'ACT' if section == 'active' else None)
                    if not status:
                        continue
                    cell = cells[header.index('Player')]
                    pos = normalize_position(cells[header.index('Pos')].content())
                    # Clubs link both the portrait and name to the same profile.
                    links = sorted({urljoin(uri, a.attrs['href']) for a in cell.find('a')
                             if '/team/players-roster/' in a.attrs.get('href', '')})
                    if len(links) == 1:
                        result.append(dict(team=team, player_name=cell.content(), position=pos,
                            source_key=links[0].rstrip('/'), kind='roster_status', status=status))
                elif kind == 'depth' and header[0] == 'Position':
                    pos = normalize_position(cells[0].content().replace('PK', 'K'))
                    if pos not in {'QB','RB','WR','TE','K','LS'}:
                        continue
                    for rank, cell in enumerate(cells[1:], 1):
                        for a in cell.find('a'):
                            if '/team/players-roster/' not in a.attrs.get('href', ''):
                                continue
                            result.append(dict(team=team, player_name=a.content(), position=pos,
                                source_key=urljoin(uri, a.attrs['href']).rstrip('/'), kind='role',
                                role='long_snapper' if pos == 'LS' else 'expected_starter' if rank == 1 else 'expected_backup'))
            return
        for child in node.children:
            if hasattr(child, 'tag'):
                walk(child)
    walk(document)
    if not result:
        raise ValueError('Official club table structure or explicit evidence unavailable')
    return result


def parse_club_transactions(html, *, team, uri, salaries, observed_at):
    """Read latest explicit roster disposition, never infer status from absence.

    The captured current-year transaction register is the source observation;
    retain each original event date/text separately. Any newer unparsed mention
    or conflicting same-day event prevents using an older negative disposition.
    Positive transactions alone never establish current active/game clearance.
    """
    document = _Document(html).root
    years = {n.content().strip() for n in document.find('option') if 'selected' in n.attrs}
    if years != {str(observed_at.year)}:
        raise ValueError('Official transaction register is not explicitly the current calendar year')
    entries = []
    for table in document.find('table'):
        for tr in table.find('tr'):
            cells = list(tr.find('td'))
            if len(cells) != 2 or not re.fullmatch(r'\d{2}/\d{2}', cells[0].content().strip()):
                continue
            event = datetime.strptime(f'{observed_at.year}/{cells[0].content().strip()}', '%Y/%m/%d').date()
            if event > observed_at.date():
                raise ValueError('Official transaction register contains future events')
            entries.append((event, ' '.join(cells[1].content().split())))
    if not entries:
        raise ValueError('Official transaction table is unavailable')
    result = []
    verbs = r'(?:release(?:d)?|waive(?:d)?|place(?:d)?|sign(?:ed)?|activate(?:d)?|promote(?:d)?|elevate(?:d)?|designate(?:d)?|revert(?:s|ed)?|trade(?:d)?)'
    for salary in salaries:
        if salary['team'] != team:
            continue
        # Team + explicit source position + normalized player name; the caller
        # additionally resolves the canonical ID through the normal identity API.
        names = {str(salary.get(k) or '').strip() for k in ('player_name', 'full_name')} - {''}
        mentions = []
        for event, body in entries:
            for name in names:
                pattern = r'\b' + re.escape(salary['position']) + r'\s+' + re.escape(name) + r'(?![\w-])'
                match = re.search(pattern, body, re.I)
                if not match:
                    if re.search(r'(?<![\w-])' + re.escape(name) + r'(?![\w-])', body, re.I):
                        mentions.append((event, None, body, name))
                        break
                    continue
                clauses = re.split(r'[.;]\s+(?=' + verbs + r'\b)|,\s*(?=' + verbs + r'\b)', body, flags=re.I)
                clause = next((c for c in clauses if re.search(pattern, c, re.I)), '')
                action = re.search(r'\b(' + verbs + r')\b', clause, re.I)
                action = action.group(1).lower() if action else ''
                status = None
                if action.startswith(('release', 'waive')):
                    status = 'CUT'
                elif action.startswith('place') and re.search(r'\bIR\b|injured reserve|reserve/injured', clause, re.I):
                    status = 'IR'
                elif action.startswith(('sign', 'revert')) and re.search(r'(?:to|reverts? to) (?:the )?practice squad', clause, re.I):
                    status = 'PS'
                mentions.append((event, status, body, name))
                break
        if not mentions:
            continue
        newest = max(row[0] for row in mentions)
        latest = [row for row in mentions if row[0] == newest]
        statuses = {row[1] for row in latest}
        if len(statuses) != 1 or None in statuses:
            continue
        event, status, body, name = latest[0]
        identity = f'{team}:{salary["position"]}:{normalize_player_name(name)}:{event}:{body}'
        result.append(dict(team=team, player_name=name, position=salary['position'],
            source_key=uri.rstrip('/')+'#'+hashlib.sha256(identity.encode()).hexdigest(),
            kind='roster_status', status=status, event_date=event.isoformat(), transaction_text=body,
            observation_basis='latest_disposition_in_current_official_transaction_register'))
    return result


def _retain_risk_evidence(context, evidence):
    """Roster/depth supplementation must not erase independently sourced risk facts.

    Preserve the original fact clocks. The consumer still validates freshness
    and cutoff, and roster membership never establishes full workload.
    """
    context['evidence_json']['workload_context'] = retained_workload_context(evidence.get('workload_context') or {})
    for key in ('role_uncertain', 'newly_assigned_role', 'depth_chart_conflict',
                'practice_report', 'practice_participation', 'practice_observed_at',
                'practice_trend', 'expected_workload_status', 'expected_workload_observed_at',
                'expected_qb_package', 'role_change'):
        if key in evidence:
            context['evidence_json'][key] = deepcopy(evidence[key])


def supplement_unresolved_context(engine, *, season, week, slate):
    params = dict(season=season, week=week, slate=slate)
    with Session(engine) as session:
        games = slate_games(session, SlatePreparationRequest(**params, action='rebuild'))
        lock = require_prelock(games)
        contexts = load_current_pregame_context(session, **params, cutoff=datetime.now(UTC))
        salaries = [dict(r) for r in session.execute(text('''
            SELECT s.player_master_id AS player_id,s.player_name,s.team,s.position,m.full_name,
                   s.curated_salary_id AS salary_source_row_id
            FROM public.curated_salary s JOIN public.player_master m USING(player_master_id)
            WHERE s.season=:season AND s.week=:week AND UPPER(s.slate)=UPPER(:slate) AND s.source_system='draftkings'
        '''), params).mappings()]
        aliases = [dict(r) for r in session.execute(text("SELECT * FROM public.player_alias WHERE player_master_id=ANY(:ids) OR source_system='nfl_official'"),
            {'ids': [s['player_id'] for s in salaries]}).mappings()]
    by_id = {str(c['player_master_id']): c for c in contexts}
    wanted = [s for s in salaries if (by_id.get(str(s['player_id']), {}).get('evidence_json') or {}).get('availability_state') != 'UNAVAILABLE'
        and ((by_id.get(str(s['player_id']), {}).get('evidence_json') or {}).get('availability_state') == 'UNKNOWN'
             or not (by_id.get(str(s['player_id']), {}).get('evidence_json') or {}).get('canonical_role'))]
    facts = defaultdict(list)
    captures, errors, identity_failures = [], [], []
    for team in sorted({s['team'] for s in wanted}):
        for kind, suffix in [('roster', 'players-roster/'), ('depth', 'depth-chart'), ('transactions', f'transactions/{datetime.now(UTC).year}')]:
            uri = f'https://www.{CLUBS[team]}.com/team/{suffix}'
            try:
                response = httpx.get(uri, follow_redirects=True, timeout=30, headers={'Cache-Control': 'no-cache'})
                response.raise_for_status()
                received = datetime.now(UTC)
                observed = observation_clock(dict(response.headers), received)
                if received >= lock:
                    raise ValueError('Club source received after lock')
                parse_error = None
                try:
                    if kind == 'transactions':
                        # Current explicit roster/depth facts take precedence over
                        # historical transactions. Fetch only unresolved absences.
                        candidates = [s for s in wanted if s['team'] == team and not facts[str(s['player_id'])]]
                        rows = parse_club_transactions(response.text, team=team, uri=str(response.url),
                            salaries=candidates, observed_at=observed)
                    else:
                        rows = parse_club_tables(response.text, team=team, uri=str(response.url), kind=kind)
                except ValueError as exc:
                    rows, parse_error = [], str(exc)
                envelope = dict(source_uri=str(response.url), observed_at=observed.isoformat(), received_at=received.isoformat(),
                    headers=dict(response.headers), body=response.text)
                with TemporaryDirectory() as tmp, Session(engine) as session:
                    path = Path(tmp)/f'{team}_{kind}.json'
                    path.write_text(json.dumps(envelope, sort_keys=True))
                    capture = SourceCaptureService(session).capture_file(path, source_system='nfl_official',
                        dataset=f'official_club_{kind}', **params, source_uri=str(response.url), slate_lock_at=lock,
                        source_license='Official club public table retained for source audit', effective_at=observed,
                        observation_basis='http_response_clock', media_type='application/json', row_count=len(rows),
                        metadata={'body_sha256': hashlib.sha256(response.content).hexdigest(), 'team':team,
                                  'publication_clock_available':False, 'parse_error':parse_error})
                    snapshot_id = capture.snapshot.snapshot_id
                captures.append(dict(team=team, kind=kind, snapshot_id=snapshot_id, observed_at=observed.isoformat(), rows=len(rows)))
                if parse_error:
                    raise ValueError(f'{parse_error}; captured snapshot {snapshot_id}')
                for r in rows:
                    pid, reason = resolve_official_player(r, salaries, aliases)
                    if not pid:
                        if any(normalize_player_name(r['player_name']) == normalize_player_name(s['player_name']) and s['team'] == team for s in wanted):
                            with engine.begin() as connection:
                                _record_identity(connection, r, None, reason, **params)
                            identity_failures.append(dict(row=r, reason=reason))
                        continue
                    with engine.begin() as connection:
                        if not _record_identity(connection, r, pid, reason, **params):
                            identity_failures.append(dict(row=r, reason='identity_conflict'))
                            continue
                    facts[pid].append(dict(player_id=pid, team=team, position=r['position'], source_position=r['position'],
                        kind=r['kind'], source='official_club_'+kind, status=r.get('status'), role=r.get('role'),
                        observed_at=observed.isoformat(), received_at=received.isoformat(), source_uri=str(response.url),
                        source_ids=[snapshot_id, r['source_key']], identity_match=reason,
                        **{k:r[k] for k in ('event_date', 'transaction_text', 'observation_basis') if k in r}))
            except (httpx.HTTPError, ValueError, OSError) as exc:
                errors.append(dict(team=team, kind=kind, reason=str(exc)[:500]))
    # Supplement original facts, preserving injury and workload clocks. ACT is
    # roster membership; it cannot clear a game-specific OUT or final inactives.
    service = PregameContextService(engine=engine)
    runs = []
    for salary in wanted:
        pid = str(salary['player_id'])
        if not facts[pid]:
            continue
        old = by_id.get(pid, {})
        evidence = old.get('evidence_json') or {}
        original_facts = evidence.get('source_facts', [])
        combined = list({json.dumps(f, sort_keys=True, default=str): f for f in original_facts + facts[pid]}.values())
        context = compose_player_contexts([salary], combined, cutoff=datetime.now(UTC),
            max_age_hours=get_settings().classic_player_status_max_age_hours)[0]
        _retain_risk_evidence(context, evidence)
        run = service.create_run(dict(**params, source=CONTEXT_CONTRACT, source_uri=context['source_uri'],
            observed_at=context['observed_at'], players=[dict(player_id=pid, injury_status=context['injury_status'],
                availability_probability=context['availability_probability'],
                role_label=context['role_label'], evidence=context['evidence_json'])]))
        runs.append(run['context_run_id'])
    return dict(context_run_ids=runs, captured_sources=captures, source_errors=errors,
        identity_failures=identity_failures, requested_players=len(wanted), supplemented_players=len(runs))
