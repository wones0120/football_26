from scripts.audit_sunday_main_priority import (
    _distribution,
    _lineup_ownership,
    _report,
    _status_flags,
)


def test_report_finds_saved_and_reconstructed_shapes():
    expected = {"all_candidates": [], "role_exposure": []}
    assert _report({"report": expected}) is expected
    assert _report({"results": [[{"classic_small_field_report": expected}]]}) is expected


def test_distribution_reports_pool_range_and_quantiles():
    result = _distribution([1, 2, 3, 4])
    assert result["count"] == 4
    assert result["minimum"] == 1
    assert result["median"] == 2.5
    assert result["maximum"] == 4


def test_partial_ownership_stays_diagnostic_and_does_not_invent_lineup_sum():
    candidate = {
        "roster": [
            {"player_id": "qb", "name": "QB", "team": "A", "position": "QB"},
            {"player_id": "wr", "name": "WR", "team": "A", "position": "WR"},
        ]
    }
    result = _lineup_ownership(candidate, {
        "qb": {"ownership": 10}, "wr": {"ownership": None},
    })
    assert result["coverage"] == 1
    assert result["complete"] is False
    assert result["sum"] is None
    assert result["log_proxy"] is None


def test_status_flags_keep_stale_and_inactive_evidence_separate():
    flags = _status_flags(
        {"roster_status": "PS", "snap_share_trend": .20},
        {"current_evidence_confidence": "stale_2025_primary",
         "current_usage": {"week_1_snap_share": 0}},
    )
    assert "inactive_or_roster_uncertain" in flags
    assert "zero_week_1_snap_share" in flags
    assert "stale_or_unknown_role" in flags
    assert "material_snap_share_trend" in flags
