from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from backend.app.product_services.official_injuries import (
    HEADERS, _record_identity, observation_clock, parse_official_report, resolve_official_player,
)
from backend.app.product_services.showdown_player_context import compose_player_contexts

NOW = datetime(2026,10,8,1,10,tzinfo=UTC)


def report(status="Out"):
    header = "<thead><tr>"+"".join(f"<th>{h}</th>" for h in HEADERS)+"</tr></thead>"
    def table(name, position, designation):
        return (f'<table>{header}<tbody><tr><td><a href="/players/{name.lower().replace(" ","-")}/">{name}</a></td>'
                f'<td>{position}</td><td>Thumb</td><td>Did Not Participate In Practice</td><td>{designation}</td></tr></tbody></table>')
    return ('<select><option value="/injuries/league/2026/reg5" selected>Week 5</option></select>'
            '<section class="nfl-o-injury-report__unit">'
            '<span class="nfl-c-matchup-strip__team-abbreviation">TB</span>'
            '<span class="nfl-c-matchup-strip__team-abbreviation">DAL</span>'
            +table("Example Quarterback","QB",status)+table("Example Receiver","WR","")+"</section>")


def test_official_game_status_is_separate_from_practice_and_blank_status():
    rows = parse_official_report(report(),season=2026,week=5)
    assert rows[0]["team"] == "TB" and rows[0]["game_status"] == "OUT"
    assert rows[1]["team"] == "DAL" and rows[1]["game_status"] is None
    assert parse_official_report(report(""),season=2026,week=5)[0]["game_status"] is None


def test_unpublished_reports_for_other_games_do_not_block_selected_slate():
    html = report()+'<section class="nfl-o-injury-report__unit"><span class="nfl-c-matchup-strip__team-abbreviation">DEN</span></section>'
    assert len(parse_official_report(html,season=2026,week=5,slate_teams={"TB","DAL"})) == 2
    with pytest.raises(ValueError):parse_official_report(html,season=2026,week=5,slate_teams={"DEN"})


@pytest.mark.parametrize("html", [report().replace("reg5", "reg4"),
    report().replace("Game Status", "Other status"), report().replace('/players/example-quarterback/', '/other/')])
def test_wrong_scope_changed_columns_and_missing_native_keys_fail_closed(html):
    with pytest.raises(ValueError):parse_official_report(html,season=2026,week=5)


def test_identity_requires_team_position_and_normalized_name_then_retains_native_key():
    row = parse_official_report(report(),season=2026,week=5)[0]
    salary = dict(player_id="canonical",player_name=row["player_name"],full_name=row["player_name"],team="TB",position="QB")
    assert resolve_official_player(row,[salary],[]) == ("canonical","team_position_normalized_name")
    assert resolve_official_player(row,[dict(salary,team="DAL")],[])[0] is None
    assert resolve_official_player(row,[dict(salary,position="WR")],[])[0] is None
    assert resolve_official_player(row,[salary,dict(salary,player_id="duplicate")],[])[1] == "ambiguous"
    alias = dict(player_master_id="canonical",source_system="nfl_official",source_key=row["source_key"],alias_name="Old name")
    assert resolve_official_player(dict(row,player_name="Changed display"),[salary],[alias]) == ("canonical","source_native_id")
    assert resolve_official_player(row,[dict(salary,team="DAL")],[alias])[1] == "identity_conflict"


def test_observation_respects_cache_age_and_never_renews_a_stale_response():
    assert observation_clock({},NOW) == NOW
    assert observation_clock({"date":"Thu, 08 Oct 2026 01:10:00 GMT","age":"90000"},NOW) == NOW-timedelta(hours=25)
    assert observation_clock({"date":"Wed, 07 Oct 2026 00:00:00 GMT","age":"1"},NOW) == datetime(2026,10,7,tzinfo=UTC)
    with pytest.raises(ValueError):observation_clock({"age":"-1"},NOW)


def test_live_official_observation_resolves_expired_article_out_without_role_clock_laundering():
    salary = dict(player_id="canonical",team="TB",position="QB")
    def fact(kind,status,at,source):
        return dict(player_id="canonical",team="TB",position="QB",kind=kind,status=status,source=source,
                    observed_at=at.isoformat(),received_at=at.isoformat(),source_ids=[source])
    facts = [fact("game_status","OUT",NOW-timedelta(hours=25),"old_article"),
             fact("roster_status","ACT",NOW-timedelta(hours=1),"roster")]
    assert compose_player_contexts([salary],facts,cutoff=NOW,max_age_hours=24)[0]["evidence_json"]["availability_state"] == "UNKNOWN"
    facts.append(fact("game_status","OUT",NOW,"nfl_official"))
    context = compose_player_contexts([salary],facts,cutoff=NOW,max_age_hours=24)[0]
    assert context["evidence_json"]["availability_state"] == "UNAVAILABLE"
    assert context["evidence_json"]["availability_source"] == "nfl_official"
    assert context["evidence_json"]["source_facts"][0]["observed_at"] == (NOW-timedelta(hours=25)).isoformat()


def test_unresolved_identity_is_queued_and_resolved_mapping_is_persisted():
    row = parse_official_report(report(),season=2026,week=5)[0]
    connection = MagicMock()
    _record_identity(connection,row,None,"no_match",season=2026,week=5,slate="THURSDAY_NIGHT")
    assert "INSERT INTO target.identity_quarantine" in str(connection.execute.call_args.args[0])
    assert connection.execute.call_args.args[1]["source_key"] == row["source_key"]
    connection.reset_mock()
    _record_identity(connection,row,"canonical","team_position_normalized_name",season=2026,week=5,slate="THURSDAY_NIGHT")
    assert "INSERT INTO public.player_alias" in str(connection.execute.call_args_list[0].args[0])
    assert "status='resolved'" in str(connection.execute.call_args_list[1].args[0])


def test_concurrent_native_key_conflict_is_queued_instead_of_emitting_wrong_identity():
    row = parse_official_report(report(),season=2026,week=5)[0]
    connection = MagicMock()
    connection.execute.return_value.scalar_one_or_none.return_value = None
    assert not _record_identity(connection,row,"canonical","team_position_normalized_name",season=2026,week=5,slate="THURSDAY_NIGHT")
    assert "INSERT INTO target.identity_quarantine" in str(connection.execute.call_args.args[0])
    assert connection.execute.call_args.args[1]["reason"] == "identity_conflict"


def test_readiness_error_names_affected_player_and_preserves_machine_audit():
    from backend.app.product_services.showdown_data_readiness import ShowdownDataNotReady
    readiness = {"reason_codes":["player_status_stale"],"required_sources":{
        "player_status":{"status":"NOT_READY","reason_codes":["player_status_stale"]}},
        "player_pool_readiness":{"players":[dict(player="Example Quarterback",team="TB",canonical_id="canonical",disposition="unknown_availability")]}}
    error = ShowdownDataNotReady(readiness)
    assert "Example Quarterback (TB)" in str(error)
    assert "player_status_stale" not in str(error)
    assert error.readiness is readiness


def test_classic_partial_weekly_report_retains_observed_rows_without_clearing_missing_teams(monkeypatch):
    from types import SimpleNamespace
    from backend.app.product_services import official_injuries as official
    current=datetime.now(UTC)
    response=SimpleNamespace(text=report(),content=report().encode(),headers={},raise_for_status=lambda:None)
    monkeypatch.setattr(official.httpx,"get",lambda *a,**k:response)
    games=[dict(home_team="TB",away_team="DAL"),dict(home_team="NYG",away_team="WAS")]
    engine=MagicMock()
    capture=MagicMock();capture.capture_file.return_value.snapshot.snapshot_id="official-capture"
    monkeypatch.setattr(official,"SourceCaptureService",lambda _:capture)
    monkeypatch.setattr(official,"Session",MagicMock())
    salaries=[dict(player_id="qb",player_name="Example Quarterback",full_name="Example Quarterback",team="TB",position="QB"),
              dict(player_id="wr",player_name="Example Receiver",full_name="Example Receiver",team="DAL",position="WR")]
    connection=engine.connect.return_value.__enter__.return_value
    connection.execute.side_effect=[SimpleNamespace(mappings=lambda:salaries),SimpleNamespace(mappings=lambda:[])]
    monkeypatch.setattr(official,"_record_identity",lambda *a,**k:True)
    context=MagicMock();context.create_run.return_value={"context_run_id":"observed-context"}
    monkeypatch.setattr(official,"PregameContextService",lambda **k:context)
    with pytest.raises(ValueError,match="all slate teams"):
        official.refresh_official_injuries(engine,season=2026,week=5,slate="SUNDAY_MAIN",games=games,slate_lock_at=current+timedelta(days=2))
    capture.capture_file.assert_not_called()
    result=official.refresh_official_injuries(engine,season=2026,week=5,slate="SUNDAY_MAIN",games=games,
        slate_lock_at=current+timedelta(days=2),require_complete_team_coverage=False)
    assert result["missing_slate_teams"]==["NYG","WAS"] and result["complete_team_coverage"] is False
    assert result["blank_status_rows"]==1 and result["game_status_rows"]==1
    players=context.create_run.call_args.args[0]["players"]
    assert len(players)==2 and players[0]["injury_status"]=="OUT"
    assert players[1]["injury_status"] is None  # Practice never invents game clearance.
    assert players[1]["evidence"]["practice_report"]["practice_status"] == "Did Not Participate In Practice"
    assert result["practice_status_rows"] == 2
    assert capture.capture_file.call_args.kwargs["metadata"]["missing_slate_teams"]==["NYG","WAS"]


def test_arizona_provider_abbreviation_is_not_dropped_from_selected_slate():
    html = report().replace('>TB</span>', '>AZ</span>')
    rows = parse_official_report(html, season=2026, week=5, slate_teams={"ARI"})
    assert rows[0]["team"] == "ARI"
    assert rows[0]["practice_status"] == "Did Not Participate In Practice"


def test_official_suffix_match_is_scoped_unique_and_preserves_native_conflicts():
    row=dict(team="TB",position="WR",player_name="David Sills",source_key="/players/david-sills")
    salary=dict(player_id="canonical",team="TB",position="WR",player_name="David Sills V",full_name="David Sills V")
    assert resolve_official_player(row,[salary],[]) == ("canonical","team_position_normalized_name")
    assert resolve_official_player(row,[dict(salary,team="ATL")],[])[0] is None
    assert resolve_official_player(row,[dict(salary,position="TE")],[])[0] is None
    assert resolve_official_player(row,[salary,dict(salary,player_id="duplicate")],[])[1] == "ambiguous"
    alias=dict(player_master_id="foreign",source_system="nfl_official",source_key=row["source_key"],alias_name="David Sills")
    assert resolve_official_player(row,[salary],[alias])[1] == "identity_conflict"
