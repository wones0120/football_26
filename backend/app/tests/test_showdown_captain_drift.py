from scripts.analyze_showdown_captain_drift import (
    _compare_segments,
    _distribution,
    _season_segment,
)


def test_season_segment_boundaries() -> None:
    assert _season_segment(1) == "early"
    assert _season_segment(6) == "early"
    assert _season_segment(7) == "mid"
    assert _season_segment(12) == "mid"
    assert _season_segment(13) == "late"


def test_drift_alert_uses_total_variation_and_minimum_samples() -> None:
    left_rows = [{"captain_position": "QB"}] * 5
    right_rows = [{"captain_position": "WR"}] * 5
    left = {
        "segment_id": "2024_early",
        "slates": len(left_rows),
        "distribution": _distribution(left_rows),
    }
    right = {
        "segment_id": "2024_mid",
        "slates": len(right_rows),
        "distribution": _distribution(right_rows),
    }

    comparison = _compare_segments(
        left,
        right,
        alert_threshold=0.25,
        min_segment_slates=5,
    )

    assert comparison["total_variation_distance"] == 1.0
    assert comparison["largest_position_shift"] in {"QB", "WR"}
    assert comparison["alert"] is True

    comparison["from_slates"] = 4
    left["slates"] = 4
    low_sample = _compare_segments(
        left,
        right,
        alert_threshold=0.25,
        min_segment_slates=5,
    )
    assert low_sample["alert"] is False
