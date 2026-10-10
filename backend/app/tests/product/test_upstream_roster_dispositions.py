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
