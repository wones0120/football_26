from dataclasses import replace
from datetime import UTC, datetime, timedelta

from backend.app.product_services.market_snapshots import (
    MarketSnapshot, canonical_team, parse_nflverse_schedules, select_market_snapshots,
)


DECISION = datetime(2026, 9, 30, 12, tzinfo=UTC)
KICKOFF = datetime(2026, 10, 4, 17, tzinfo=UTC)
GAME = {"season": 2026, "week": 4, "game_id": "2026_04_GB_TB",
        "home_team": "TB", "away_team": "GB", "kickoff_at": KICKOFF}


def line(**changes):
    return replace(MarketSnapshot(
        season=2026, week=4, game_id=GAME["game_id"], home_team="TB", away_team="GB",
        kickoff_at=KICKOFF, game_total=45.5, home_spread=-3.5,
        source="nflverse_schedules", source_game_id=GAME["game_id"],
        observed_at=DECISION - timedelta(hours=5),
        ingested_at=DECISION - timedelta(hours=5), snapshot_id="one",
    ), **changes)


def test_nflverse_parser_matches_canonical_game_and_home_margin_sign():
    events = [{"season": 2026, "week": 4, "game_id": GAME["game_id"],
               "home_team": "TB", "away_team": "GB", "total_line": 45.5,
               "spread_line": 3.5}]
    parsed, rejected = parse_nflverse_schedules(events, schedule=[GAME], season=2026,
                                                  week=4, captured_at=DECISION)
    assert not rejected
    assert len(parsed) == 1
    assert parsed[0].home_spread == -3.5
    assert parsed[0].home_implied_total == 24.5
    assert parsed[0].away_implied_total == 21
    assert parsed[0].home_implied_total + parsed[0].away_implied_total == 45.5
    assert parsed[0].home_implied_total - parsed[0].away_implied_total == 3.5
    assert canonical_team("Los Angeles Rams") == "LAR"
    wrong, rejected = parse_nflverse_schedules([{**events[0], "game_id": "wrong"}],
                                                schedule=[GAME], season=2026, week=4,
                                                captured_at=DECISION)
    assert not wrong and "game ID" in rejected[0]["reason"]


def test_latest_predecision_observation_and_game_coverage():
    old = line(snapshot_id="old", observed_at=DECISION - timedelta(hours=25),
               ingested_at=DECISION - timedelta(hours=25), game_total=44)
    new = line(snapshot_id="new", observed_at=DECISION - timedelta(hours=2),
               ingested_at=DECISION - timedelta(hours=2))
    post_decision = line(snapshot_id="future", observed_at=DECISION + timedelta(hours=1),
                         ingested_at=DECISION + timedelta(hours=1))
    post_lock = line(snapshot_id="postlock", observed_at=KICKOFF,
                     ingested_at=KICKOFF)
    wrong_team = line(snapshot_id="wrong", home_team="NYG")
    result = select_market_snapshots([GAME], [old, new, post_decision, post_lock, wrong_team],
                                     decision_at=DECISION)
    assert result["selected"] == [new]
    assert result["sourced_games"] == result["total_games"] == 1
    assert result["games"][0]["status"] == "fresh"
    assert len(result["rejected"]) == 3
    assert select_market_snapshots([GAME], [old], decision_at=DECISION)["stale_games"] == 1
    assert select_market_snapshots([GAME], [], decision_at=DECISION)["missing_games"] == 1


def test_invalid_and_late_ingestion_never_become_market_evidence():
    invalid = line(game_total=0)
    too_late = line(ingested_at=DECISION + timedelta(seconds=1))
    assert invalid.sanity_errors()
    result = select_market_snapshots([GAME], [invalid, too_late], decision_at=DECISION)
    assert result["sourced_games"] == 0
    assert result["missing_games"] == 1
    assert len(result["rejected"]) == 2


def test_same_snapshot_loads_for_showdown_without_classic_rules():
    result = select_market_snapshots([GAME], [line()], decision_at=DECISION)
    assert result["selected"][0].home_implied_total == 24.5
    assert "approval" not in result
