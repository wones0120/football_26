import pandas as pd

from scripts.audit_ownership_calibration import calibration_report


def test_calibration_audit_reports_tail_misses_and_contest_slices() -> None:
    rows = pd.DataFrame([
        {"season": 2026, "week": 2, "slate": "SUNDAY_MAIN", "contest_id": "a",
         "player_id": "p1", "position": "RB", "salary": 7400,
         "projected_ownership": 4.0, "actual_ownership": 35.0,
         "contest_format": "classic", "contest_type": "gpp", "field_size_tier": "1001-10000"},
        {"season": 2026, "week": 2, "slate": "SUNDAY_MAIN", "contest_id": "a",
         "player_id": "p2", "position": "WR", "salary": 4500,
         "projected_ownership": 20.0, "actual_ownership": 10.0,
         "contest_format": "classic", "contest_type": "gpp", "field_size_tier": "1001-10000"},
    ])
    result = calibration_report(rows)
    assert result["overall"]["mae"] == 20.5
    assert result["overall"]["bias"] == -10.5
    assert result["projected_under_5_actual_over"]["30"]["count"] == 1
    assert result["by_position"]["RB"]["bias"] == -31.0
    assert result["by_contest_format"]["classic"]["rows"] == 2
    assert result["top_10_projected_per_contest"]["rows"] == 2
