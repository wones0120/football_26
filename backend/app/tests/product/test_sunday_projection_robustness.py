from types import SimpleNamespace

from scripts.validate_sunday_projection_robustness import (
    classify_reason,
    rescore_candidates,
)


def _candidate(rank, player_id, mean, objective):
    return {
        "shadow_rank": rank,
        "objective_score": objective,
        "mean": mean,
        "p90": 20.0,
        "components": {"mean": 0.35 * mean / 10.0, "p90": 0.48 * 20.0 / 20.0, "context": 0.0},
        "roster": [{"player_id": player_id, "name": player_id}],
    }


def test_rescore_changes_only_requested_mean_and_preserves_p90() -> None:
    players = [
        SimpleNamespace(player_id="a", projection=10.0, optimizer_context_adjustment=0.0),
        SimpleNamespace(player_id="b", projection=9.0, optimizer_context_adjustment=0.0),
    ]
    candidates = [_candidate(1, "a", 10.0, 0.83), _candidate(2, "b", 9.0, 0.80)]

    rescored = rescore_candidates(candidates, players, {"a": 5.0})

    assert rescored[0]["shadow_rank"] == 2
    changed = next(row for row in rescored if row["shadow_rank"] == 1)
    unchanged = next(row for row in rescored if row["shadow_rank"] == 2)
    assert changed["stressed_mean"] == 5.0
    assert unchanged["stressed_mean"] == 9.0
    assert changed["p90"] == 20.0


def test_zero_qb_projection_is_classified_as_starter_role_when_probability_zero() -> None:
    compared = {"position": "QB", "signed_difference": -17.2, "our_mean": 0.0, "espn_mean": 17.2}
    feature = {"pregame_start_probability": 0.0, "pregame_point_mean_before_opportunity": 11.73}

    categories, reason = classify_reason(
        compared, feature, None, None, None,
        [{"player_name": "Cooper Rush"}],
    )

    assert categories == ["E. player-status / starter-role issue"]
    assert "11.73" in reason
    assert "Cooper Rush" in reason
