from datetime import UTC, datetime, timedelta

import pytest

from backend.app.product_services.classic_official_context import parse_club_transactions
from backend.app.product_services.showdown_player_context import compose_player_contexts

NOW = datetime(2026, 10, 9, 17, tzinfo=UTC)
SALARY = dict(player_id="canonical", team="WAS", position="WR", player_name="Example Receiver", full_name="Example Receiver")


def register(*events, year=2026):
    return f'<select><option selected>{year}</option></select><table>' + ''.join(
        f'<tr><td>{date}</td><td>{text}</td></tr>' for date, text in events) + '</table>'


def parse(html, **kwargs):
    return parse_club_transactions(html, team="WAS", uri="https://example.test/team/transactions/2026",
                                   salaries=[SALARY], observed_at=NOW, **kwargs)


def test_latest_explicit_disposition_retains_event_date_and_source_text():
    rows = parse(register(("08/18", "Signed RB Other Player. Placed RB Other Back and WR Example Receiver on IR."),
                          ("07/29", "Signed WR Example Receiver.")))
    assert len(rows) == 1 and rows[0]["status"] == "IR"
    assert rows[0]["event_date"] == "2026-08-18"
    assert "Placed" in rows[0]["transaction_text"]
    assert rows[0]["source_key"].startswith("https://example.test/team/transactions/2026#")


@pytest.mark.parametrize("later", ["Signed WR Example Receiver.", "Designated WR Example Receiver to return to practice.",
                                    "Activated WR Example Receiver.", "Activated Example Receiver."])
def test_newer_positive_or_uncertain_event_prevents_old_unavailable_claim(later):
    assert not parse(register(("10/07", later), ("08/18", "Placed WR Example Receiver on IR.")))


def test_same_day_conflict_wrong_position_and_missing_name_do_not_certify():
    assert not parse(register(("10/07", "Released WR Example Receiver."), ("10/07", "Signed WR Example Receiver.")))
    assert not parse(register(("10/07", "Released RB Example Receiver.")))
    assert not parse(register(("10/07", "Released WR Another Receiver.")))
    assert not parse(register(("10/07", "Released WR Example Receiver-Smith.")))


@pytest.mark.parametrize("html", [register(("10/07", "Released WR Example Receiver."), year=2025),
                                   register(("10/10", "Released WR Example Receiver.")), "<table></table>"])
def test_wrong_year_future_and_missing_register_fail_closed(html):
    with pytest.raises(ValueError): parse(html)


def test_current_cut_fact_is_unavailable_and_later_roster_fact_can_supersede_it():
    def fact(status, at):
        return dict(player_id="canonical", team="WAS", position="WR", kind="roster_status", status=status,
                    source="nflreadpy_weekly_rosters", source_ids=[status], source_uri="fixture://roster",
                    observed_at=at.isoformat(), received_at=at.isoformat())
    facts = [fact("CUT", NOW - timedelta(hours=1))]
    context = compose_player_contexts([SALARY], facts, cutoff=NOW, max_age_hours=24)[0]
    assert context["evidence_json"]["availability_state"] == "UNAVAILABLE"
    assert context["availability_probability"] == 0
    facts.append(fact("ACT", NOW))
    assert compose_player_contexts([SALARY], facts, cutoff=NOW, max_age_hours=24)[0]["evidence_json"]["availability_state"] == "AVAILABLE"
    assert compose_player_contexts([SALARY], facts[:1], cutoff=NOW + timedelta(days=2), max_age_hours=24)[0]["evidence_json"]["availability_state"] == "UNKNOWN"


def test_commissioner_exempt_roster_is_unavailable_without_a_role():
    from backend.app.product_services.classic_official_context import parse_club_tables
    html = ('<h3>Commissioner Exempt</h3><table><tr><th>Player</th><th>Pos</th></tr>'
            '<tr><td><a href="/team/players-roster/example/">Example Receiver</a></td><td>WR</td></tr></table>')
    row = parse_club_tables(html, team='WAS', uri='https://example.test', kind='roster')[0]
    assert row['status'] == 'EXE'
    fact = dict(row, player_id='canonical', source='official_club_roster', source_ids=['snapshot'],
                observed_at=NOW.isoformat(), received_at=NOW.isoformat())
    context = compose_player_contexts([SALARY], [fact], cutoff=NOW, max_age_hours=24)[0]
    assert context['evidence_json']['availability_state'] == 'UNAVAILABLE'
    assert context['availability_probability'] == 0
    assert 'player_role_missing' not in context['evidence_json']['canonical_context_reason_codes']


def transfer_rows(team='MIA', at=NOW, status='ACT', position='WR'):
    return [dict(gsis_id='native-id', team=team, position=position, roster_status=status,
                 observed_at=at, received_at=at, snapshot_id='snapshot',
                 raw_nfl_weekly_roster_id='row', source_uri='fixture://rosters')]


def transfer_facts(rows, aliases=None):
    from backend.app.product_services.showdown_player_context import transferred_roster_facts
    return transferred_roster_facts(rows, aliases or {'native-id': {'canonical'}},
                                   {'canonical': SALARY}, cutoff=NOW)


def test_native_roster_transfer_excludes_old_team_and_preserves_evidence():
    facts = transfer_facts(transfer_rows())
    assert facts[0]['team'] == 'WAS' and facts[0]['current_team'] == 'MIA'
    assert facts[0]['source_ids'] == ['snapshot', 'row', 'native-id']
    assert compose_player_contexts([SALARY], facts, cutoff=NOW, max_age_hours=24)[0]['availability_probability'] == 0
    # Re-reading old evidence must not refresh its clock.
    assert compose_player_contexts([SALARY], facts, cutoff=NOW+timedelta(days=2), max_age_hours=24)[0]['evidence_json']['availability_state'] == 'UNKNOWN'


@pytest.mark.parametrize('rows', [transfer_rows('WAS'), transfer_rows(position='RB'),
    transfer_rows(status='UNKNOWN'), transfer_rows(at=NOW+timedelta(hours=1)),
    transfer_rows()+transfer_rows('WAS'),
    transfer_rows(at=NOW-timedelta(hours=1))+transfer_rows('WAS')])
def test_transfer_requires_unambiguous_latest_team_position_and_visible_evidence(rows):
    assert not transfer_facts(rows)


def test_ambiguous_native_alias_cannot_establish_transfer():
    assert not transfer_facts(transfer_rows(), {'native-id': {'canonical', 'another'}})


def test_supplement_envelope_includes_newer_practice_without_freshening_sources():
    from backend.app.product_services.classic_official_context import _retain_risk_evidence
    from backend.app.product_services.pregame_context import risk_evidence_fields
    old_status = NOW - timedelta(hours=2)
    practice_at = NOW - timedelta(hours=1)
    context = dict(observed_at=old_status, evidence_json={'availability_observed_at': old_status.isoformat()})
    evidence = dict(practice_report={'practice_status':'LIMITED', 'observed_at':practice_at.isoformat()})
    _retain_risk_evidence(context, evidence, cutoff=NOW)
    assert context['observed_at'] == practice_at
    assert context['evidence_json']['availability_observed_at'] == old_status.isoformat()
    assert risk_evidence_fields(context['evidence_json'],context['observed_at'])['practice_observed_at'] == practice_at.isoformat()
    evidence['practice_report']['observed_at'] = (NOW+timedelta(seconds=1)).isoformat()
    _retain_risk_evidence(context, evidence, cutoff=NOW)
    with pytest.raises(ValueError, match='later than its context observation'):
        risk_evidence_fields(context['evidence_json'],context['observed_at'])
