import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from backend.app.product_services.gpp_optimizer import Player
from backend.app.product_services.sunday_candidate_archive import (
    extract_candidates,
    lineup_key,
    merge_discoveries,
    new_archive,
    validate_candidate,
)
from scripts.run_sunday_main_final_decision import (
    _changes,
    _movement_reason,
    _refresh_manifest,
    _roster_mapping_preflight,
)


def _players():
    specs = [
        ("qb", "QB", "AAA", "BBB", 5000),
        ("rb1", "RB", "AAA", "BBB", 7000),
        ("rb2", "RB", "CCC", "DDD", 6500),
        ("wr1", "WR", "AAA", "BBB", 6000),
        ("wr2", "WR", "BBB", "AAA", 5500),
        ("wr3", "WR", "CCC", "DDD", 5000),
        ("wr4", "WR", "EEE", "FFF", 4000),
        ("te", "TE", "AAA", "BBB", 4500),
        ("dst", "DST", "EEE", "FFF", 2500),
    ]
    return [Player(
        player_id=pid, name=pid, team=team, opponent=opponent, position=position,
        salary=salary, projection=10.0, ceiling=20.0, ownership=0.0,
        game_id="AAA_BBB" if team in {"AAA", "BBB"} else f"{team}_{opponent}",
    ) for pid, position, team, opponent, salary in specs]


def test_candidate_extraction_and_merge_are_canonical_and_persistent():
    ids = [player.player_id for player in _players()]
    payload = {"top": [{"player_ids": ids}, {"lineup_key": list(reversed(ids))}]}
    discoveries = extract_candidates(payload, source="run", source_sha256="abc")
    assert len(discoveries) == 2
    assert discoveries[0]["lineup_key"] == discoveries[1]["lineup_key"]

    archive = new_archive(season=2026, week=2, slate="SUNDAY_MAIN")
    counts = merge_discoveries(archive, discoveries, observed_at="2026-09-19T12:00:00Z")
    assert counts["new_archive_candidates"] == 1
    assert counts["duplicates_removed"] == 1
    assert len(archive["candidates"]) == 1

    merge_discoveries(archive, [], observed_at="2026-09-20T12:00:00Z")
    assert lineup_key(ids) in archive["candidates"]


def test_revalidation_rejects_missing_inactive_and_denver_opponent():
    players = _players()
    by_id = {player.player_id: player for player in players}
    pool = {player.player_id: {} for player in players}
    valid = validate_candidate(
        by_id, players_by_id=by_id, pool_by_id=pool,
        excluded_opponents={"DEN"}, max_from_game=9,
    )
    assert valid["legal"] is True

    pool["wr4"] = {"pregame_injury_status": "OUT"}
    inactive = validate_candidate(
        by_id, players_by_id=by_id, pool_by_id=pool,
        excluded_opponents={"DEN"}, max_from_game=9,
    )
    assert any(reason == "inactive:wr4" for reason in inactive["reasons"])

    den = {**by_id, "wr4": Player(**{**by_id["wr4"].__dict__, "opponent": "DEN"})}
    excluded = validate_candidate(
        den, players_by_id=den, pool_by_id={player_id: {} for player_id in den},
        excluded_opponents={"DEN"}, max_from_game=9,
    )
    assert any(reason.startswith("excluded_opponent:wr4") for reason in excluded["reasons"])


def test_revalidation_allows_no_bring_back_by_default_but_can_audit_strict_mode():
    players = _players()
    no_bring_back = []
    for player in players:
        if player.player_id == "wr2":
            player = Player(**{
                **player.__dict__, "team": "CCC", "opponent": "DDD", "game_id": "CCC_DDD",
            })
        no_bring_back.append(player)
    by_id = {player.player_id: player for player in no_bring_back}
    pool = {player.player_id: {} for player in no_bring_back}

    normal = validate_candidate(
        by_id, players_by_id=by_id, pool_by_id=pool, max_from_game=9,
    )
    assert normal["legal"] is True
    assert normal["checks"]["qb_stack_present"] is True
    assert normal["checks"]["bring_back_present"] is False
    assert normal["checks"]["bring_back_required"] is False

    strict_audit = validate_candidate(
        by_id, players_by_id=by_id, pool_by_id=pool, max_from_game=9,
        require_bring_back=True,
    )
    assert strict_audit["legal"] is False
    assert strict_audit["reasons"] == ["bring_back_missing"]


def test_refresh_manifest_fails_loudly_when_domains_are_missing(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"domains": {"injuries": {"status": "complete"}}}))
    with pytest.raises(ValueError, match="refresh evidence is incomplete"):
        _refresh_manifest(path, require_complete=True)


def test_refresh_manifest_rejects_stale_domains(tmp_path):
    domains = {
        name: {"status": "complete", "refreshed_at": "2026-09-20T08:00:00-04:00"}
        for name in (
            "official_inactives", "starting_qbs", "injuries", "weather", "markets",
            "ownership", "role_opportunity", "projections", "new_candidates",
        )
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"domains": domains}))
    with pytest.raises(ValueError, match="stale:official_inactives"):
        _refresh_manifest(
            path, require_complete=True,
            refresh_after=datetime.fromisoformat("2026-09-20T09:00:00-04:00"),
        )


def test_refresh_manifest_distinguishes_prelock_from_official_evidence(tmp_path):
    domains = {
        name: {"status": "current_prelock_status", "refreshed_at": "2026-09-20T08:00:00-04:00"}
        for name in (
            "official_inactives", "starting_qbs", "injuries", "weather", "markets",
            "ownership", "role_opportunity", "projections", "new_candidates",
        )
    }
    domains["official_inactives"]["evidence_state"] = "not_yet_official"
    domains["starting_qbs"]["evidence_state"] = "mixed_inferred_confirmed"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"domains": domains}))

    prelock = _refresh_manifest(path, require_complete=True)
    assert prelock["status"] == "complete"
    with pytest.raises(ValueError, match="evidence:official_inactives:not_yet_official"):
        _refresh_manifest(path, require_complete=True, require_official_inactives=True)
    with pytest.raises(ValueError, match="evidence:starting_qbs:mixed_inferred_confirmed"):
        _refresh_manifest(path, require_complete=True, require_confirmed_starting_qbs=True)


def test_v2_refresh_manifest_requires_verified_sourced_domains(tmp_path):
    domains = {
        name: {
            "status": "current", "verification_state": "verified",
            "refreshed_at": "2026-09-20T08:00:00-04:00", "source": "source",
        }
        for name in (
            "official_inactives", "starting_qbs", "roster_mapping", "injuries",
            "weather", "markets", "ownership", "role_opportunity", "projections",
            "new_candidates",
        )
    }
    domains["markets"]["verification_state"] = "unverified"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({
        "contract_id": "sunday_main_refresh_manifest_v2", "domains": domains,
    }))
    with pytest.raises(ValueError, match="verification:markets:unverified"):
        _refresh_manifest(path, require_complete=True)


def test_roster_mapping_preflight_rejects_team_mismatch_and_nonstarter_qb():
    players = [
        SimpleNamespace(player_id="qb", name="Quarterback", position="QB", team="ATL"),
        SimpleNamespace(player_id="wr", name="Receiver", position="WR", team="CAR"),
    ]
    result = _roster_mapping_preflight(players, {
        "qb": {"player_team": "MIN", "is_starting_qb": False},
        "wr": {"player_team": "CAR"},
    })
    assert result["status"] == "failed"
    assert result["conflict_count"] == 1
    assert result["conflicts"][0]["reasons"] == [
        "team_mismatch:ATL:MIN", "eligible_qb_not_marked_starter",
    ]


def test_change_report_tracks_player_and_lineup_metrics():
    baseline = {
        "player_inputs": {"p": {"player": "P", "projection": 10, "p90": 20}},
        "ranked_candidates": [{
            "lineup_key": "k", "rank": 1, "selector_objective": 5,
            "mean": 100, "p90": 180, "relative_chalk": 50,
            "football_sanity_deficit": 0,
        }],
    }
    current = {
        "player_inputs": {"p": {"player": "P", "projection": 11, "p90": 20}},
        "ranked_candidates": [{
            "lineup_key": "k", "rank": 2, "selector_objective": 4.9,
            "mean": 101, "p90": 180, "relative_chalk": 45,
            "football_sanity_deficit": 0,
        }],
    }
    result = _changes(current, baseline)
    assert result["player_input_changes"][0]["fields"]["projection"] == {"before": 10, "after": 11}
    assert result["lineup_changes"][0]["fields"]["rank"] == {"before": 1, "after": 2}


def test_change_report_marks_invalidated_prior_lineup():
    baseline = {
        "player_inputs": {},
        "ranked_candidates": [{"lineup_key": "old", "rank": 4}],
    }
    result = _changes({"player_inputs": {}, "ranked_candidates": []}, baseline)
    assert result["lineup_changes"] == [{
        "lineup_key": "old", "change": "invalidated_or_removed", "previous_rank": 4,
    }]


def test_movement_reason_accepts_internal_sanity_shape():
    current = {
        "mean": 101, "p90": 180, "relative_chalk": 50,
        "sanity": {"total_football_sanity_deficit": 0},
    }
    previous = {
        "mean": 100, "p90": 180, "relative_chalk": 50,
        "football_sanity_deficit": 0,
    }
    assert _movement_reason(current, previous) == "mean +1.00"
