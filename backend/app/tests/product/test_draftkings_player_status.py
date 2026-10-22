from copy import deepcopy
from datetime import UTC, datetime

import pytest

from backend.app.product_services.draftkings_player_status import parse_native_statuses
from backend.app.product_services.showdown_player_context import compose_player_contexts

GAMES = [dict(away_team='SF', home_team='SEA', kickoff_at='2026-10-11T20:25:00Z')]
SALARIES = [dict(player_id='canonical', source_player_key='123', team='SF', position='WR')]
PAYLOAD = dict(draftables=[dict(draftableId=123, position='WR', teamAbbreviation='SF', status='OUT',
    competition=dict(name='SF @ SEA', startTime='2026-10-11T20:25:00Z'))])


def test_exact_native_identity_and_game_match_provides_current_negative_evidence():
    facts, discrepancies = parse_native_statuses(PAYLOAD, SALARIES, GAMES)
    assert not discrepancies
    assert facts[0]['player_id'] == 'canonical' and facts[0]['status'] == 'OUT'
    now = datetime(2026, 10, 10, 22, tzinfo=UTC)
    facts[0].update(source_ids=['snapshot', '123'], observed_at=now.isoformat(), received_at=now.isoformat())
    context = compose_player_contexts(SALARIES, facts, cutoff=now, max_age_hours=24)[0]
    assert context['availability_probability'] == 0


@pytest.mark.parametrize('status', ['None', '', None, 'Q', 'ACTIVE', 'unexpected'])
def test_blank_or_nonnegative_status_cannot_clear_injury_or_assert_availability(status):
    payload = deepcopy(PAYLOAD)
    payload['draftables'][0]['status'] = status
    assert not parse_native_statuses(payload, SALARIES, GAMES)[0]


@pytest.mark.parametrize('change', ['native_id', 'game', 'kickoff', 'duplicate', 'ambiguous_identity'])
def test_wrong_slate_ids_or_conflicting_identity_fail_closed(change):
    payload, salaries = deepcopy(PAYLOAD), deepcopy(SALARIES)
    row = payload['draftables'][0]
    if change == 'native_id': row['draftableId'] = 456
    if change == 'game': row['competition']['name'] = 'SF @ ARI'
    if change == 'kickoff': row['competition']['startTime'] = '2026-10-18T20:25:00Z'
    if change == 'duplicate': payload['draftables'].append(deepcopy(row))
    if change == 'ambiguous_identity': salaries.append(dict(salaries[0], player_id='other'))
    with pytest.raises(ValueError): parse_native_statuses(payload, salaries, GAMES)


@pytest.mark.parametrize('field,value', [('teamAbbreviation', 'SEA'), ('position', 'RB')])
def test_native_team_or_position_changes_are_reported_not_applied_to_old_salary(field, value):
    payload = deepcopy(PAYLOAD)
    payload['draftables'][0][field] = value
    facts, discrepancies = parse_native_statuses(payload, SALARIES, GAMES)
    assert not facts
    assert discrepancies[0]['reason'] == 'native_team_or_position_changed'


@pytest.mark.parametrize("contest_format,game_type", [("classic", 1), ("showdown", 96)])
def test_refresh_captures_native_sources_and_preserves_http_observation(monkeypatch, contest_format, game_type):
    from types import SimpleNamespace
    from backend.app.product_services import draftkings_player_status as native
    saved = []
    class Session:
        def __init__(self, engine): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class Capture:
        def __init__(self, session): pass
        def capture_file(self, path, **kwargs):
            import json
            saved.append((json.loads(path.read_text()), kwargs))
            return SimpleNamespace(snapshot=SimpleNamespace(snapshot_id=f'snapshot-{len(saved)}'))
    class Client(Session):
        def __init__(self, **kwargs): pass
        def get(self, uri):
            payload = dict(DraftGroups=[dict(DraftGroupId=99, Sport='NFL', GameTypeId=game_type,
                GameCount=1, StartDate=GAMES[0]['kickoff_at'])]) if uri == native.LOBBY_URI else PAYLOAD
            return SimpleNamespace(url=uri, headers={'date':'Sat, 10 Oct 2026 20:00:00 GMT'},
                                   raise_for_status=lambda: None, json=lambda: deepcopy(payload))
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return datetime(2026, 10, 10, 20, 1, tzinfo=UTC)
    monkeypatch.setattr(native, 'datetime', Clock)
    monkeypatch.setattr(native, 'Session', Session)
    monkeypatch.setattr(native, 'SourceCaptureService', Capture)
    monkeypatch.setattr(native.httpx, 'Client', Client)
    facts, captures, discrepancies = native.refresh_native_statuses(None, salaries=SALARIES, games=GAMES,
        season=2026, week=5, slate='SUNDAY_MAIN', lock=datetime(2026,10,11,20,25,tzinfo=UTC), contest_format=contest_format)
    assert len(saved) == len(captures) == 2 and not discrepancies
    assert saved[1][0]['body'] == PAYLOAD
    assert saved[1][1]['source_system'] == 'draftkings'
    assert facts[0]['source_ids'] == ['snapshot-2', 'snapshot-1', '123']
    assert facts[0]['observed_at'] == '2026-10-10T20:00:00+00:00'
    assert facts[0]['received_at'] == '2026-10-10T20:01:00+00:00'
    saved.clear()
    with pytest.raises(ValueError, match='after slate lock'):
        native.refresh_native_statuses(None, salaries=SALARIES, games=GAMES,
            season=2026, week=5, slate='SUNDAY_MAIN', lock=datetime(2026,10,10,20,tzinfo=UTC))
    assert not saved


def test_showdown_questionable_is_explicit_designation_not_healthy_or_role():
    payload = deepcopy(PAYLOAD)
    payload['draftables'][0]['status'] = 'Q'
    facts, discrepancies = parse_native_statuses(payload, SALARIES, GAMES, contest_format='showdown')
    now = datetime(2026, 10, 10, 22, tzinfo=UTC)
    facts[0].update(source_ids=['snapshot', '123'], observed_at=now.isoformat(), received_at=now.isoformat())
    context = compose_player_contexts(SALARIES, facts, cutoff=now, max_age_hours=24)[0]
    assert context['injury_status'] == 'Q'
    assert context['availability_probability'] is None
    assert context['evidence_json']['canonical_role'] is None
    assert 'player_role_missing' in context['evidence_json']['canonical_context_reason_codes']
    payload['draftables'][0]['status'] = ''
    assert not parse_native_statuses(payload, SALARIES, GAMES, contest_format='showdown')[0]
