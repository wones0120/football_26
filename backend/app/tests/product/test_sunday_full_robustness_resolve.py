from backend.app.product_services.gpp_optimizer import Player
from scripts.validate_sunday_full_robustness_resolve import (
    candidate_player_ids,
    eligible_qb_ids,
    scenario_players,
)


def player(name: str, projection: float, ceiling: float, salary: int, player_id: str = "p") -> Player:
    return Player(
        player_id=player_id,
        name=name,
        team="AAA",
        opponent="BBB",
        position="QB",
        salary=salary,
        projection=projection,
        ceiling=ceiling,
        ownership=0.0,
        value_per_k=projection / (salary / 1000),
        ceiling_per_k=ceiling / (salary / 1000),
    )


def test_projection_stress_preserves_or_shifts_ceiling_as_requested():
    baseline = player("Quarterback", 16.0, 28.0, 5000)
    espn = {"p": {"espn_mean": 24.0}}

    mean_only, changes = scenario_players(
        [baseline], espn, blend=0.5, ceiling_treatment="mean_only"
    )
    shifted, _ = scenario_players(
        [baseline], espn, blend=0.5, ceiling_treatment="spread_preserving"
    )

    assert mean_only[0].projection == 20.0
    assert mean_only[0].ceiling == 28.0
    assert shifted[0].projection == 20.0
    assert shifted[0].ceiling == 32.0
    assert changes["p"]["stressed_mean"] == 20.0


def test_nonmaterial_projection_difference_is_not_stressed():
    baseline = player("Quarterback", 16.0, 28.0, 5000)
    stressed, changes = scenario_players(
        [baseline], {"p": {"espn_mean": 18.0}}, blend=0.5,
        ceiling_treatment="spread_preserving",
    )
    assert stressed[0].projection == 16.0
    assert stressed[0].ceiling == 28.0
    assert changes == {}


def test_qb_eligibility_unions_control_and_stressed_value_views():
    control = [
        player("Control leader", 20.0, 30.0, 5000, "a"),
        player("Stress leader", 10.0, 20.0, 5000, "b"),
        player("Outside", 8.0, 18.0, 5000, "c"),
    ]
    stressed = [
        player("Control leader", 12.0, 22.0, 5000, "a"),
        player("Stress leader", 22.0, 32.0, 5000, "b"),
        player("Outside", 8.0, 18.0, 5000, "c"),
    ]

    selected, audit = eligible_qb_ids(
        control, stressed, top_n=1, top_mean_n=0, value_gap=0.0
    )

    assert selected == {"a", "b"}
    assert {row["qb"] for row in audit if row["selected"]} == {
        "Control leader", "Stress leader"
    }


def test_qb_eligibility_includes_high_raw_mean_despite_low_value():
    control = [
        player("Value QB", 18.0, 28.0, 5000, "a"),
        player("High mean QB", 24.0, 34.0, 9000, "b"),
        player("Outside", 10.0, 20.0, 8000, "c"),
    ]
    selected, _ = eligible_qb_ids(
        control, control, top_n=1, top_mean_n=1, value_gap=0.0
    )
    assert selected == {"a", "b"}


def test_qb_eligibility_always_includes_external_source_leaders():
    control = [
        player("Local leader", 20.0, 30.0, 5000, "a"),
        player("External leader", 10.0, 20.0, 8000, "b"),
        player("Outside", 9.0, 19.0, 7000, "c"),
    ]
    selected, audit = eligible_qb_ids(
        control, control, top_n=1, top_mean_n=1, value_gap=0.0,
        external_means={"a": 12.0, "b": 28.0, "c": 10.0},
    )
    assert selected == {"a", "b"}
    external = next(row for row in audit if row["qb"] == "External leader")
    assert external["external_mean_rank"] == 1


def test_prior_concise_candidate_reads_ids_from_roster():
    assert candidate_player_ids({
        "roster": [{"player_id": "a"}, {"player_id": "b"}]
    }) == ["a", "b"]
