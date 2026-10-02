from backend.app.product_services.rb_dst_diagnostics import build_rb_dst_diagnostics


def _candidate(rank, players, score, mean, p90, rules=None):
    return {"rank": rank, "player_ids": [p["player_id"] for p in players],
            "roster": players, "objective_score": score, "mean": mean,
            "p90": p90, "correlation_rules": rules or []}


def _player(player_id, name, team, position):
    return {"player_id": player_id, "name": name, "team": team,
            "position": position}


def test_same_team_underdog_rb_dst_is_warning_only_with_avoidance_cost():
    achane = _player("rb", "De'Von Achane", "MIA", "RB")
    dolphins = _player("dst", "Dolphins", "MIA", "DST")
    other_dst = _player("other_dst", "Commanders", "WAS", "DST")
    current = _candidate(1, [achane, dolphins], 5.25, 137, 239)
    alternate = _candidate(2, [achane, other_dst], 5.1, 136, 238)
    source = {"rb": {"position": "RB", "name": "De'Von Achane",
                     "player_team": "MIA", "salary": 6500, "projection": 16.47,
                     "p90": 26.9, "carries_mean_3": 10.16,
                     "targets_mean_3": 3.35, "target_share_mean_3": .139,
                     "team_spread_line": 11.5, "team_implied_total": 17,
                     "game_total_line": 45.5,
                     "market_context_point_in_time_safe": True,
                     "projection_model_version": "v4.2-role-opportunity"}}

    report = build_rb_dst_diagnostics([current, alternate], [0], source)

    flag = next(item for item in current["rb_dst_football_sanity_flags"]
                if item["kind"] == "same_team_rb_dst")
    assert flag["status"] == "informational"
    assert flag["production_impacting"] is False
    assert flag["correlation_selector_contribution"] == 0
    assert flag["strongest_candidate_without_flag"]["rank"] == 2
    assert flag["strongest_candidate_without_flag"]["mean_cost"] == 1
    assert report["player_why"][0]["model_version"] == "v4.2-role-opportunity"
    assert report["warning_only"] is True
    assert current["objective_score"] == 5.25


def test_low_team_total_avoidance_requires_fewer_than_two_offensive_players():
    rb = _player("rb", "RB", "MIA", "RB")
    wr = _player("wr", "WR", "MIA", "WR")
    dst = _player("dst", "DST", "WAS", "DST")
    current = _candidate(1, [rb, wr, dst], 5.0, 120, 210)
    still_flagged = _candidate(2, [rb, wr], 4.9, 119, 209)
    clean = _candidate(3, [rb, dst], 4.8, 118, 208)
    source = {"rb": {"position": "RB", "projection": 8,
                     "market_context_point_in_time_safe": True,
                     "team_implied_total": 17}}

    build_rb_dst_diagnostics([current, still_flagged, clean], [0], source)

    flag = next(item for item in current["rb_dst_football_sanity_flags"]
                if item["kind"] == "low_team_total_offense")
    assert flag["strongest_candidate_without_flag"]["rank"] == 3


def test_favorite_pair_surfaces_existing_positive_rule_without_rescoring():
    rb = _player("rb", "Favorite RB", "DET", "RB")
    dst = _player("dst", "Lions", "DET", "DST")
    candidate = _candidate(1, [rb, dst], 5.2, 130, 220, [{
        "reason_code": "same_team_running_back_dst",
        "objective_contribution": .01636,
        "players": [{"player_id": "rb"}, {"player_id": "dst"}],
    }])
    source = {"rb": {"position": "RB", "projection": 18,
                     "team_spread_line": -6.5, "team_implied_total": 27.5}}

    build_rb_dst_diagnostics([candidate], [0], source)

    flag = candidate["rb_dst_football_sanity_flags"][0]
    assert "favored by at least 6" in flag["label"]
    assert flag["correlation_selector_contribution"] == .01636
    assert candidate["objective_score"] == 5.2
