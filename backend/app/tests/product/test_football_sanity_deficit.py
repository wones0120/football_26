import pytest

from backend.app.product_services.football_sanity_deficit import (
    deficit_crossover_points,
    lineup_sanity_deficit,
    player_deficit,
    prepare_deficit_candidates,
    rank_with_deficit,
    role_bucket,
)


def core(classification, centrality, *, confidence="high_current", overall_core=False):
    return {
        "football_classification": classification,
        "overall_centrality": centrality,
        "current_evidence_confidence": confidence,
        "overall_core": overall_core,
    }


def player(player_id, team="AAA", *, salary=5000, projection=10):
    return {"player_id": player_id, "name": player_id, "team": team,
            "position": "WR", "salary": salary, "projection": projection}


def test_core_is_capped_and_stale_is_neither_rewarded_nor_penalized():
    low_core = core("core receiving player", .55, overall_core=True)
    high_core = core("offensive centerpiece", 1.0, overall_core=True)
    stale = core("peripheral", .05, confidence="stale_2025_primary")
    assert role_bucket(low_core) == role_bucket(high_core) == "strong_core"
    assert player_deficit(low_core) == player_deficit(high_core) == 0
    assert role_bucket(stale) == "stale_or_unknown"
    assert player_deficit(stale) == 0


def test_weak_roles_and_team_coverage_create_bounded_deficits():
    roster = [player("weak"), player("peripheral")]
    cores = {
        "weak": core("complementary", .30),
        "peripheral": core("peripheral", .10),
        "team-core": core("core receiving player", .70, overall_core=True),
    }
    pool = [*roster, player("team-core", salary=5300, projection=11)]
    result = lineup_sanity_deficit(roster, core_by_id=cores, player_pool=pool)
    assert result["complementary_count"] == 1
    assert result["peripheral_count"] == 1
    assert result["teams_with_multiple_skill_players_no_core"] == ["AAA"]
    assert result["classic_team_context_deficit"] == pytest.approx(.25)
    assert result["comparable_core_alternative_deficit"] == pytest.approx(.15)
    assert 0 < result["player_deficit"] <= 2

    showdown = lineup_sanity_deficit(
        roster, core_by_id=cores, player_pool=pool, showdown=True
    )
    assert showdown["showdown_team_coverage_deficit"] == pytest.approx(1.0)


def test_zero_deficit_gets_no_bonus_and_penalty_can_change_winner():
    candidates = [
        {"rank": 1, "objective_score": 1.0, "roster": [player("weak")]},
        {"rank": 2, "objective_score": .95, "roster": [player("core")]},
    ]
    cores = {
        "weak": core("peripheral", .1),
        "core": core("core receiving player", .7, overall_core=True),
    }
    prepared, stats = prepare_deficit_candidates(
        candidates, core_by_id=cores, player_pool=[player("weak"), player("core")]
    )
    assert stats["candidate_count"] == 2
    assert prepared[1]["standardized_deficit"] == 0
    assert rank_with_deficit(prepared, 0)[0]["saved_rank"] == 1
    assert rank_with_deficit(prepared, .1)[0]["saved_rank"] == 2
    crossovers = deficit_crossover_points(prepared)
    assert crossovers[0]["candidate"]["saved_rank"] == 1
    assert crossovers[-1]["candidate"]["saved_rank"] == 2
