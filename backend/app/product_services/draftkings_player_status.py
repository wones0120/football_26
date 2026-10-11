"""Capture current native slate statuses; a blank status never proves availability."""
from datetime import UTC, datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from sqlalchemy.orm import Session

from Database.dst import normalize_team
from Database.player_identity import normalize_position
from ..services.source_capture import SourceCaptureService
from .official_injuries import observation_clock
from .player_roles import UNAVAILABLE
from .salary_eligibility import normalize_salary_status
from .slate_preparation import aware

LOBBY_URI = 'https://www.draftkings.com/lobby/getcontests?sport=NFL'


def game_key(name, kickoff):
    teams = str(name).split(' @ ')
    if len(teams) != 2:
        raise ValueError('Native DraftKings competition lacks an explicit away/home matchup')
    return (normalize_team(teams[0]), normalize_team(teams[1]), aware(kickoff))


def parse_native_statuses(payload, salaries, games):
    """Verify the full game set and imported native IDs before using any statuses."""
    expected = {(normalize_team(g['away_team']), normalize_team(g['home_team']), aware(g['kickoff_at'])) for g in games}
    rows = payload.get('draftables') or []
    actual = {game_key(r['competition']['name'], r['competition']['startTime']) for r in rows}
    if actual != expected:
        raise ValueError('Native DraftKings slate games do not match the imported slate')
    by_id = {}
    for row in rows:
        key = str(row['draftableId'])
        if key in by_id:
            raise ValueError('Duplicate native DraftKings draftable ID')
        by_id[key] = row
    imported = {str(s['source_player_key']) for s in salaries}
    if not imported or not imported <= by_id.keys():
        raise ValueError('Native DraftKings player IDs do not cover the imported salary pool')
    identities = {}
    for salary in salaries:
        identities.setdefault(str(salary['source_player_key']), set()).add(str(salary['player_id']))
    facts, discrepancies = [], []
    for salary in salaries:
        key = str(salary['source_player_key'])
        row = by_id[key]
        if len(identities[key]) != 1:
            raise ValueError('Imported DraftKings ID has conflicting canonical identities')
        if (normalize_team(row['teamAbbreviation']) != normalize_team(salary['team'])
                or normalize_position(row['position']) != normalize_position(salary['position'])):
            discrepancies.append(dict(player_id=str(salary['player_id']), native_id=key,
                reason='native_team_or_position_changed', imported_team=salary['team'], current_team=row['teamAbbreviation']))
            continue
        status = normalize_salary_status(row.get('status'))
        if status not in UNAVAILABLE:
            continue
        facts.append(dict(player_id=str(salary['player_id']), team=salary['team'], position=salary['position'],
            source_position=row['position'], kind='game_status', status=status,
            source='draftkings_current_slate_status', native_id=key,
            observation_basis='current_native_slate_designation', identity_match='native_draftable_id'))
    return facts, discrepancies


def refresh_native_statuses(engine, *, salaries, games, season, week, slate, lock):
    """Discover Classic by schedule, then require exact native ID membership.

    Preserve the complete public responses and HTTP/cache clocks. This refresh
    neither replaces the imported salaries nor interprets missing/blank status.
    """
    captures = []
    def capture(client, uri, dataset):
        response = client.get(uri)
        response.raise_for_status()
        received = datetime.now(UTC)
        observed = observation_clock(dict(response.headers), received)
        if received >= lock:
            raise ValueError('Native DraftKings status source received after slate lock')
        payload = response.json()
        envelope = dict(source_uri=str(response.url), headers=dict(response.headers),
                        observed_at=observed.isoformat(), received_at=received.isoformat(), body=payload)
        with TemporaryDirectory() as tmp, Session(engine) as session:
            path = Path(tmp)/f'{dataset}.json'
            path.write_text(json.dumps(envelope, sort_keys=True))
            result = SourceCaptureService(session).capture_file(path, source_system='draftkings',
                dataset=dataset, season=season, week=week, slate=slate, source_uri=str(response.url),
                slate_lock_at=lock, source_license='Public DraftKings slate status retained for source audit',
                effective_at=observed, observation_basis='http_response_clock', media_type='application/json',
                metadata={'publication_clock_available': False})
            snapshot_id = result.snapshot.snapshot_id
        captures.append(dict(kind=dataset, snapshot_id=snapshot_id, observed_at=observed.isoformat()))
        return payload, observed, received, snapshot_id

    with httpx.Client(timeout=30, follow_redirects=True, headers={'Cache-Control': 'no-cache'}) as client:
        lobby, _, _, lobby_id = capture(client, LOBBY_URI, 'native_status_lobby')
        candidates = {int(g['DraftGroupId']) for g in lobby.get('DraftGroups', [])
            if g.get('Sport') == 'NFL' and g.get('GameTypeId') == 1 and g.get('GameCount') == len(games)
            and aware(g['StartDate']) == lock}
        if not candidates or len(candidates) > 8:
            raise ValueError('No bounded set of matching native Classic slates in the current lobby')
        matches, rejected = [], []
        for group in sorted(candidates):
            uri = f'https://api.draftkings.com/draftgroups/v1/draftgroups/{group}/draftables'
            payload, observed, received, snapshot_id = capture(client, uri, 'native_slate_status')
            try:
                facts, discrepancies = parse_native_statuses(payload, salaries, games)
            except (ValueError, KeyError, TypeError) as exc:
                rejected.append(str(exc))
                continue
            for fact in facts:
                fact.update(observed_at=observed.isoformat(), received_at=received.isoformat(),
                    source_uri=uri, source_ids=[snapshot_id, lobby_id, fact['native_id']], native_draft_group=group)
            matches.append((facts, discrepancies))
        if len(matches) != 1:
            raise ValueError(f'Native slate status match is not unique ({len(matches)} matches): {rejected}')
        facts, discrepancies = matches[0]
        return facts, captures, discrepancies
