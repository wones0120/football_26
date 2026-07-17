import numpy as np

from backend.app.services.lineup_learning import (
    CLASSIC_FEATURE_ABLATION_GROUPS,
    CLASSIC_VALUE_DRIVER_FEATURE_NAMES,
    FEATURE_NAMES,
    PATTERN_FEATURE_INDEX,
    LineupLearningService,
    PlayerPoolRow,
)


def _player(
    uid: str,
    position: str,
    team: str,
    opponent: str,
    *,
    total: float | None,
    spread: float | None,
) -> PlayerPoolRow:
    return PlayerPoolRow(
        uid=uid,
        name=uid,
        team=team,
        opponent=opponent,
        position=position,
        salary=5000,
        actual_points=0.0,
        projected_mean_points=10.0,
        projected_p90_points=18.0,
        game_total_line=total,
        team_spread_line=spread,
        team_implied_total=(total - spread) / 2.0 if total is not None and spread is not None else None,
        opponent_implied_total=(total + spread) / 2.0 if total is not None and spread is not None else None,
    )


def test_classic_value_driver_findings_are_model_features() -> None:
    lineup = [
        _player("qb", "QB", "DAL", "NYG", total=50.0, spread=-2.0),
        _player("rb1", "RB", "ATL", "NO", total=49.0, spread=4.0),
        _player("rb2", "RB", "PHI", "WAS", total=47.0, spread=-4.0),
        _player("rb3", "RB", "LV", "DEN", total=48.0, spread=8.0),
        _player("wr1", "WR", "SEA", "SF", total=51.0, spread=1.0),
        _player("wr2", "WR", "TB", "CAR", total=44.0, spread=-3.0),
        _player("wr3", "WR", "MIA", "BUF", total=46.0, spread=2.0),
        _player("te", "TE", "DET", "GB", total=45.0, spread=-1.0),
        _player("dst", "DST", "NYJ", "NE", total=None, spread=None),
    ]

    features = LineupLearningService(session=None)._lineup_features(lineup)  # type: ignore[arg-type]

    assert len(features) == len(FEATURE_NAMES)
    assert np.all(np.isfinite(features))
    assert set(CLASSIC_VALUE_DRIVER_FEATURE_NAMES).issubset(PATTERN_FEATURE_INDEX)
    assert features[PATTERN_FEATURE_INDEX["lineup_projected_value"]] == 2.0
    assert features[PATTERN_FEATURE_INDEX["high_total_offense_share"]] == 0.5
    assert features[PATTERN_FEATURE_INDEX["offense_vegas_coverage"]] == 1.0
    assert np.isclose(features[PATTERN_FEATURE_INDEX["rb_avg_team_spread"]], 8.0 / 3.0)
    assert np.isclose(features[PATTERN_FEATURE_INDEX["rb_underdog_share"]], 2.0 / 3.0)
    assert features[PATTERN_FEATURE_INDEX["rb_spread_coverage"]] == 1.0
    assert features[PATTERN_FEATURE_INDEX["flex_is_rb"]] == 1.0
    assert features[PATTERN_FEATURE_INDEX["flex_is_wr"]] == 0.0
    assert features[PATTERN_FEATURE_INDEX["flex_is_te"]] == 0.0


def test_classic_value_driver_features_distinguish_missing_vegas_data() -> None:
    lineup = [
        _player("qb", "QB", "DAL", "NYG", total=None, spread=None),
        _player("rb1", "RB", "ATL", "NO", total=None, spread=None),
        _player("rb2", "RB", "PHI", "WAS", total=None, spread=None),
        _player("wr1", "WR", "SEA", "SF", total=None, spread=None),
        _player("wr2", "WR", "TB", "CAR", total=None, spread=None),
        _player("wr3", "WR", "MIA", "BUF", total=None, spread=None),
        _player("wr4", "WR", "LAR", "ARI", total=None, spread=None),
        _player("te", "TE", "DET", "GB", total=None, spread=None),
        _player("dst", "DST", "NYJ", "NE", total=None, spread=None),
    ]

    features = LineupLearningService(session=None)._lineup_features(lineup)  # type: ignore[arg-type]

    assert features[PATTERN_FEATURE_INDEX["high_total_offense_share"]] == 0.0
    assert features[PATTERN_FEATURE_INDEX["offense_vegas_coverage"]] == 0.0
    assert features[PATTERN_FEATURE_INDEX["rb_avg_team_spread"]] == 0.0
    assert features[PATTERN_FEATURE_INDEX["rb_underdog_share"]] == 0.0
    assert features[PATTERN_FEATURE_INDEX["rb_spread_coverage"]] == 0.0
    assert features[PATTERN_FEATURE_INDEX["flex_is_wr"]] == 1.0


def test_classic_feature_ablation_zeros_only_selected_group() -> None:
    lineup = [
        _player("qb", "QB", "DAL", "NYG", total=50.0, spread=-2.0),
        _player("rb1", "RB", "ATL", "NO", total=49.0, spread=4.0),
        _player("rb2", "RB", "PHI", "WAS", total=47.0, spread=-4.0),
        _player("wr1", "WR", "SEA", "SF", total=51.0, spread=1.0),
        _player("wr2", "WR", "TB", "CAR", total=44.0, spread=-3.0),
        _player("wr3", "WR", "MIA", "BUF", total=46.0, spread=2.0),
        _player("wr4", "WR", "LAR", "ARI", total=48.0, spread=3.0),
        _player("te", "TE", "DET", "GB", total=45.0, spread=-1.0),
        _player("dst", "DST", "NYJ", "NE", total=None, spread=None),
    ]
    service = LineupLearningService(session=None)  # type: ignore[arg-type]
    baseline = service._lineup_features(lineup)

    service.set_classic_feature_ablation_groups(["value_drivers"])
    ablated = service._lineup_features(lineup)

    disabled_indices = {
        PATTERN_FEATURE_INDEX[name]
        for name in CLASSIC_FEATURE_ABLATION_GROUPS["value_drivers"]
    }
    assert all(ablated[index] == 0.0 for index in disabled_indices)
    assert all(
        ablated[index] == baseline[index]
        for index in range(len(FEATURE_NAMES))
        if index not in disabled_indices
    )


def test_classic_feature_ablation_rejects_unknown_group() -> None:
    service = LineupLearningService(session=None)  # type: ignore[arg-type]

    with np.testing.assert_raises_regex(ValueError, "Unknown classic feature ablation group"):
        service.set_classic_feature_ablation_groups(["future_data"])
