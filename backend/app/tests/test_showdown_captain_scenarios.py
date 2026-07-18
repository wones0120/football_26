from collections import Counter

from scripts.analyze_showdown_captain_scenarios import (
    _role_bucket,
    _scenario_key,
    _smoothed_priors,
)


def test_role_bucket_uses_position_relative_salary() -> None:
    assert _role_bucket(15000, 10000) == "premium"
    assert _role_bucket(12000, 10000) == "core"
    assert _role_bucket(9000, 10000) == "value"
    assert _role_bucket(9000, 0) == "unknown"


def test_scenario_key_uses_future_safe_total_and_spread() -> None:
    assert _scenario_key(50.0, 2.5) == "high_total__close"
    assert _scenario_key(45.0, 5.0) == "mid_total__moderate"
    assert _scenario_key(40.0, 8.0) == "low_total__wide"


def test_smoothed_priors_include_unseen_archetypes() -> None:
    priors = _smoothed_priors(
        Counter({"WR:premium": 2}),
        ["RB:core", "WR:premium"],
        alpha=1.0,
    )

    assert priors["WR:premium"] == 0.75
    assert priors["RB:core"] == 0.25
    assert sum(priors.values()) == 1.0
