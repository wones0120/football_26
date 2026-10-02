from backend.app.product_services.showdown_captain_optimality import (
    _qb_validation,
    add_shadow_qb_family_ranks,
    build_optimality_report,
    current_qb_analysis,
)


def _row(season, week, slate, name, team, position, carries, regret):
    return {
        "season": season, "week": week, "slate": slate,
        "player_id": name, "player_name": name, "team": team,
        "player_master_id": name,
        "position": position, "expected_carries": carries,
        "expected_targets": 5 if position == "WR" else None,
        "expected_pass_attempts": 30 if position == "QB" else None,
        "captain_regret": regret, "forced_captain_feasible": True,
        "captain_salary": 12000, "flex_salary": 8000,
        "actual_points": 20, "projected_mean": 15,
        "team_implied_total": 24, "team_spread": -2, "game_total": 46,
    }


def _slate(season, week, slate, teams, captain, position):
    return {"season": season, "week": week, "slate": slate,
            "optimal_score": 100.0,
            "optimal_lineup": [{"player_id": captain, "name": captain,
                                "team": teams[0], "position": position},
                               {"player_id": "other", "name": "Other",
                                "team": teams[1], "position": "RB"}]}


def test_deduplicates_matchup_and_keeps_position_and_qb_denominators_distinct():
    dataset = {
        "slates": [_slate(2024, 1, "a-original", ("AAA", "BBB"), "Rush QB", "QB"),
                   _slate(2024, 1, "z-duplicate", ("AAA", "BBB"), "Rush QB", "QB"),
                   _slate(2024, 2, "next", ("CCC", "DDD"), "Receiver", "WR")],
        "forced_captains": [
            _row(2024, 1, "a-original", "Rush QB", "AAA", "QB", 6, 0),
            _row(2024, 1, "a-original", "Pocket QB", "BBB", "QB", 1, 10),
            _row(2024, 1, "z-duplicate", "Rush QB", "AAA", "QB", 6, 0),
            _row(2024, 2, "next", "Receiver", "CCC", "WR", None, 0),
            _row(2024, 2, "next", "Mobile QB", "DDD", "QB", 3, 5),
        ],
    }
    report = build_optimality_report(dataset)
    assert report["slate_count"] == 2
    assert len(report["duplicates_removed"]) == 1
    assert report["latest_completed_period"] == [2024, 2]
    qb = next(row for row in report["positions"] if row["label"] == "QB")
    assert qb["optimal_count"] == 1
    assert qb["eligible_opportunities"] == 3
    assert qb["slate_optimal_share"] == 0.5
    assert report["prior_application"]["status"] == "shadow_only"


def test_current_qb_report_uses_recent_carries_and_never_invents_goal_line_role():
    report = {"qb_archetype_thresholds_recent_carries": [2.0, 4.0],
              "qb_archetypes": [{"label": "Pocket-oriented", "optimal_rate": 0.0,
                                 "optimal_count": 0, "eligible_opportunities": 30},
                                {"label": "High-rush / goal-line unverified",
                                 "optimal_rate": 0.1, "optimal_count": 6,
                                 "eligible_opportunities": 60}],
              "qb_buckets": {"recent_carries": [
                  {"label": "0–2", "optimal_rate": 0.0},
                  {"label": "4–6", "optimal_rate": 0.1}]},
              "prior_application": {"status": "shadow_only"}}
    rows = current_qb_analysis([
        {"name": "Rush QB", "position": "QB", "player_team": "AAA",
         "carries_mean_3": 5.5, "captain_objective_multiplier": 1.1},
        {"name": "Pocket QB", "position": "QB", "player_team": "BBB",
         "carries_mean_3": 1.2, "captain_objective_multiplier": 1.1},
    ], report, [{"captain_name": "Rush QB", "rank": 2, "mean": 80,
                "p90": 140, "selected": True}])
    assert rows[0]["archetype"] == "High-rush / goal-line unverified"
    assert rows[1]["archetype"] == "Pocket-oriented"
    assert rows[0]["goal_line_role"] is None
    assert rows[0]["best_family_rank"] == 2
    assert rows[0]["archetype_prior_adjustment"] == 0.0


def test_tied_optimal_captains_count_once_and_remain_visible():
    dataset = {
        "slates": [_slate(2024, 3, "tie", ("AAA", "BBB"), "Tight End", "TE")],
        "forced_captains": [
            _row(2024, 3, "tie", "Tight End", "AAA", "TE", None, 0),
            _row(2024, 3, "tie", "Running Back", "BBB", "RB", None, 0),
        ],
    }
    report = build_optimality_report(dataset)
    assert report["games_with_captain_ties"] == 1
    assert sum(row["optimal_count"] for row in report["positions"]) == 1
    assert next(row for row in report["positions"] if row["label"] == "TE")["optimal_count"] == 1
    assert {row["name"] for row in report["slates"][0]["co_optimal_captains"]} == {"Tight End", "Running Back"}


def test_starters_use_pregame_evidence_then_clear_salary_and_prior_volume():
    rows = [
        _row(2024, 1, "one", "Pocket Starter", "AAA", "QB", 1, 0),
        _row(2024, 1, "one", "Pocket Backup", "AAA", "QB", 0, 10),
        _row(2024, 1, "one", "Evidence Starter", "BBB", "QB", 5, 7),
        _row(2024, 1, "one", "Salary Leader", "BBB", "QB", 1, 8),
    ]
    rows[0]["flex_salary"] = 10000
    rows[1]["flex_salary"] = 7000
    rows[2]["flex_salary"] = 9000
    rows[3]["flex_salary"] = 10500
    report = build_optimality_report(
        {"slates": [_slate(2024, 1, "one", ("AAA", "BBB"), "Pocket Starter", "QB")],
         "forced_captains": rows},
        historical_inputs={"starter_evidence": [{"season": 2024, "week": 1, "slate": "one",
                                                  "team": "BBB", "player_master_id": "Evidence Starter",
                                                  "status": "active", "evidence_tier": "confirmed"}],
                           "qb_prior_features": [{"season": 2024, "week": 1, "slate": "one",
                                                  "player_master_id": "Pocket Starter",
                                                  "last_prior_game": [2023, 18],
                                                  "recent_rushing_yards": 4.0}]},
    )
    assert report["starter_identification"]["identified"] == 2
    assert report["starter_identification"]["complete_two_team_games"] == 1
    assert report["starter_identification"]["methods"] == {
        "salary_and_prior_pass_volume_inferred": 1, "pregame_confirmed": 1}
    assert report["starter_qb_overall"]["optimal_count"] == 1
    assert report["starter_qb_overall"]["eligible_opportunities"] == 2
    assert report["starter_qb_game_shares"][0]["optimal_count"] == 1
    assert next(row for row in report["qb_opportunities"] if row["player_name"] == "Pocket Starter")["recent_rushing_yards"] == 4.0


def test_shadow_rerank_does_not_edit_live_selector():
    families = {"ranked_metrics": [
        {"rank": 1, "captain_name": "Pocket", "selector": 100.0, "captain_objective_score": 20.0},
        {"rank": 2, "captain_name": "Receiver", "selector": 98.0, "captain_objective_score": 18.0}],
        "family_rows": [{"rank": 1, "captain_name": "Pocket", "selector": 100.0}]}
    history = {"starter_qb_overall": {"optimal_count": 2, "eligible_opportunities": 10},
               "starter_qb_archetypes": [{"label": "Pocket-oriented", "optimal_count": 0,
                                          "eligible_opportunities": 5}],
               "current_qbs": [{"qb": "Pocket", "archetype": "Pocket-oriented"}]}
    result = add_shadow_qb_family_ranks(families, history, prior_strength=0.35)
    assert result["status"] == "diagnostic_unvalidated"
    assert families["ranked_metrics"][0]["selector"] == 100.0
    assert families["family_rows"][0]["shadow_rank"] == 2


def test_validation_archetype_boundaries_use_training_period_only():
    rows = [
        {"season": 2024, "expected_carries": carries, "flex_salary": 8000,
         "projected_mean": 15, "team_implied_total": 24,
         "recent_rushing_tds": 0, "recent_passing_tds": 1,
         "recent_rushing_yards": 10, "recent_team_rushing_td_share": 0,
         "expected_pass_attempts": 30, "teammate_target_concentration": 0.4,
         "selected_optimal_captain": index == 0}
        for index, carries in enumerate((0, 2, 4, 6))
    ] + [
        {"season": 2025, "expected_carries": carries, "flex_salary": 8000,
         "projected_mean": 15, "team_implied_total": 24,
         "recent_rushing_tds": 0, "recent_passing_tds": 1,
         "recent_rushing_yards": 10, "recent_team_rushing_td_share": 0,
         "expected_pass_attempts": 30, "teammate_target_concentration": 0.4,
         "selected_optimal_captain": index == 0}
        for index, carries in enumerate((100, 110))
    ]
    report = _qb_validation(rows)
    assert report["validation_archetype_thresholds_recent_carries"] == [2.0, 4.0]
