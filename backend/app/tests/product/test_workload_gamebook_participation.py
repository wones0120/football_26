from datetime import UTC, datetime, timedelta

import pytest

from backend.app.product_services.workload_gamebook_participation import parse_not_active, resolve_roster_identity
from backend.app.product_services.workload_count_forecast import verified_current_role, forecast
from backend.app.tests.product.test_workload_count_forecast import history, actors, MODEL


def page():
    return "\n".join([
        "Date: Sunday, 10/4/2026 Indianapolis Colts at Washington Commanders",
        "Not Active".center(90)+"Not Active".center(90),
        "WR 10 K.Allen, QB 15 R.Leonard".ljust(90)+"RB 1 R.White, QB 5 J.Daniels, WR 17 T.McLaurin",
        "Field Goals (made & missed)","VISITOR: Indianapolis Colts"])


GAME=dict(game_id="2026_04_IND_WAS",season=2026,week=4,gameday="2026-10-04",away_team="IND",home_team="WAS")


def test_parser_only_explicit_inactive_exact_scope_and_no_fg_pollution():
    rows=parse_not_active(page(),GAME)
    assert [(r["team"],r["jersey"],r["player_name"]) for r in rows if r["team"]=="WAS"] == [
        ("WAS",1,"R.White"),("WAS",5,"J.Daniels"),("WAS",17,"T.McLaurin")]
    with pytest.raises(ValueError,match="date"):
        parse_not_active(page(),{**GAME,"gameday":"2026-10-11"})
    with pytest.raises(ValueError,match="matchup"):
        parse_not_active(page(),{**GAME,"away_team":"SEA"})
    with pytest.raises(ValueError,match="Not Active"):
        parse_not_active(page().replace("Not Active","Did Not Play"),GAME)


def test_native_jersey_team_position_and_exact_week_not_name_only():
    row=next(r for r in parse_not_active(page(),GAME) if r["player_name"]=="J.Daniels")
    source=dict(season=2026,week=4,team="WAS",position="QB",player_name="Jayden Daniels",
        player_master_id="canonical-daniels",raw_nfl_weekly_roster_id=17,raw_row_json=dict(jersey_number=5))
    assert resolve_roster_identity(row,[source])[:2] == ("canonical-daniels",[17])
    for changed in [dict(week=5),dict(team="IND"),dict(position="WR"),dict(raw_row_json=dict(jersey_number=6))]:
        assert resolve_roster_identity(row,[{**source,**changed}])[0] is None
    assert resolve_roster_identity(row,[source,{**source,"player_master_id":"other"}])[0] is None


def test_current_role_clock_and_canonical_identity_are_required():
    cutoff=datetime(2026,10,19,15,tzinfo=UTC)
    evidence=dict(player_id="p",team="WAS",position="WR",role="expected_starter",source_ids=[1],source_uri="nflreadpy://depth_charts/2026",
        observed_at=(cutoff-timedelta(hours=1)).isoformat(),received_at=cutoff.isoformat())
    source=dict(player_id="p",player_team="WAS",position="WR",canonical_role="expected_starter",role_availability="rostered",
        role_optimizer_eligible=True,role_starter_evidence=evidence)
    assert verified_current_role(source,cutoff=cutoff)==evidence
    for changed in [dict(player_id="wrong"),dict(team="SF"),dict(position="RB"),
                    dict(observed_at=(cutoff+timedelta(hours=1)).isoformat()),
                    dict(observed_at=(cutoff-timedelta(days=5)).isoformat())]:
        assert verified_current_role({**source,"role_starter_evidence":{**evidence,**changed}},cutoff=cutoff) is None


def test_verified_inactive_gap_bridges_active_counts_without_zero_or_donation():
    h=history();h=h.loc[~(h.player_master_id.eq("Aq")&h.period.eq(202507))]
    a=actors();a[0]["current_role_evidence"]=dict(source_ids=[1],source_uri="nflreadpy://depth_charts/2025")
    missing=forecast(h,a,before_period=202509,starters={"A":"Aq"},model=MODEL)
    assert missing["players"][0]["counts"]["pass_attempts"] is None
    proof=dict(kind="official_gamebook_not_active_v1",player_master_id="Aq",team="A",period=202507)
    fixed=forecast(h,a,before_period=202509,starters={"A":"Aq"},model=MODEL,verified_gaps=[proof])
    q=fixed["players"][0]
    assert q["counts"]["pass_attempts"]==40
    assert q["raw_history"]["pass_attempts"]["periods"]==[202505,202506,202508]
    assert q["raw_history"]["pass_attempts"]["values"]==[30,30,30]
    assert q["verified_inactive_gaps"]==[proof]
    assert fixed["players"][1]["counts"]["rush_attempts"]<=missing["players"][1]["counts"]["rush_attempts"]
    unknown=forecast(h,a,before_period=202509,starters={"A":"Aq"},model=MODEL,verified_gaps=[{**proof,"kind":"roster_without_snap"}])
    assert unknown["players"][0]["counts"]["pass_attempts"] is None


def test_gamecenter_uses_nfl_nicknames_not_club_domains():
    from backend.app.product_services.workload_gamebook_participation import gamecenter_uri
    assert gamecenter_uri(dict(away_team='PHI',home_team='CHI',season=2026,week=3))=='https://www.nfl.com/games/eagles-at-bears-2026-reg-3?tab=recap'
    assert gamecenter_uri(dict(away_team='CHI',home_team='GB',season=2026,week=5))=='https://www.nfl.com/games/bears-at-packers-2026-reg-5?tab=recap'


def test_three_inactive_games_require_all_proofs_and_preserve_observed_counts():
    h=history();h=h.loc[~(h.player_master_id.eq('Aq')&h.period.isin([202505,202506,202507]))].copy()
    original=h.copy(deep=True);a=actors()
    a[0]['current_role_evidence']=dict(source_ids=['current-native-role'],source_uri='nflreadpy://depth_charts/2025')
    proofs=[dict(kind='official_gamebook_not_active_v1',player_master_id='Aq',team='A',period=p) for p in [202505,202506,202507]]
    missing=forecast(h,a,before_period=202509,starters={'A':'Aq'},model=MODEL,verified_gaps=proofs[:-1])
    assert missing['players'][0]['counts']['pass_attempts'] is None
    full=forecast(h,a,before_period=202509,starters={'A':'Aq'},model=MODEL,verified_gaps=proofs)
    q=full['players'][0]
    assert q['counts']['pass_attempts']==40.
    assert q['raw_history']['pass_attempts']['periods']==[202503,202504,202508]
    assert q['raw_history']['pass_attempts']['values']==[30.,30.,30.]
    assert q['verified_inactive_gaps']==proofs
    import pandas as pd
    pd.testing.assert_frame_equal(h,original)
    for channel in ('pass_attempts','rush_attempts','targets'):
        known=sum(p['counts'][channel] for p in full['players'] if p['counts'][channel] is not None)
        if full['teams']['A'][channel] is not None:
            assert known<=full['teams']['A'][channel]+1e-8
