from copy import deepcopy

import pandas as pd
import pytest

from backend.app.product_services.opportunity_history_evidence import (
    VERSION, build_history_evidence, source_history,
)
from backend.app.product_services.workload_count_forecast import forecast
from backend.app.tests.product.test_workload_count_forecast import MODEL, actors, history


def test_count_receipt_consumes_shared_history_without_relabeling_proxy():
    h = history()
    h["projected_targets"] = 900  # ignored allocated proxy, never original count
    a = actors(); a[1]["user_excluded"] = True
    result = forecast(h, a, before_period=202509, starters={"A": "Aq"}, model=MODEL)
    evidence = result["history_evidence"]
    assert evidence["version"] == VERSION
    assert evidence["source_actor_game_rows"] == len(h)
    rb = evidence["actors"][1]
    assert [r["targets"] for r in rb["observed_games"]] == [5, 5, 5]
    assert rb["allocated_proxy"] is None and rb["forecast"] is None
    assert rb["observed_kind"] == "original_source_counts"
    assert result["players"][1]["counts"]["targets"] > 0


def test_unmapped_actor_known_zero_and_missing_component_are_distinct():
    h = history()
    h.loc[h.player_master_id.eq("Aw"), "player_master_id"] = None
    h.loc[h.player_master_id.eq("Ar") & h.period.eq(202508), "targets"] = None
    result = build_history_evidence(h, actors()[:2], before_period=202509)
    latest = result["teams"]["A"]["coverage"][-1]
    assert latest["unmapped_source_actor_rows"] == 1
    assert latest["unmapped_observed_counts"]["targets"] == 20
    assert latest["missing_component_rows"]["targets"] == 1
    assert result["teams"]["A"]["recent_observed_games"][-1]["targets"] is None
    assert result["actors"][0]["observed_games"][-1]["targets"] == 0
    assert result["actors"][1]["observed_games"][-1]["targets"] is None


def test_fullback_source_actor_is_normalized_without_losing_work():
    h = history(); h.loc[h.player_master_id.eq("Ar"), "position"] = "FB"
    result = build_history_evidence(h, actors(), before_period=202509)
    assert result["actors"][1]["position"] == "RB"
    assert result["teams"]["A"]["recent_observed_games"][-1]["rush_attempts"] == 20


def test_native_duplicate_and_canonical_duplicate_rejected():
    h = history(); h["source_player_id"] = h.player_master_id
    duplicate = h.iloc[[0]].copy(); duplicate["player_master_id"] = None
    with pytest.raises(ValueError, match="Duplicate native"):
        source_history(pd.concat([h, duplicate]), before_period=202509)
    with pytest.raises(ValueError, match="Duplicate canonical"):
        source_history(pd.concat([h, h.iloc[[0]]]), before_period=202509)


def test_present_import_cutoff_is_not_historical_pregame_proof():
    h = history(); h["imported_at"] = "2025-03-01T00:00:00Z"
    with pytest.raises(ValueError, match="after decision cutoff"):
        build_history_evidence(h, actors(), before_period=202509, cutoff="2025-02-01T00:00:00Z")
    result = build_history_evidence(h, actors(), before_period=202509, cutoff="2025-04-01T00:00:00Z")
    assert "not original pregame proof" in result["chronology"]
    assert result["actors"][0]["observed_games"][0]["imported_at"] == "2025-03-01T00:00:00Z"


def test_future_target_rows_do_not_change_frozen_evidence():
    h = history(); extra = h.iloc[[0]].copy(); extra["period"] = 202509
    expected = build_history_evidence(h, actors(), before_period=202509)
    assert build_history_evidence(pd.concat([h, extra]), actors(), before_period=202509) == expected
    assert build_history_evidence(h.sample(frac=1, random_state=3), actors(), before_period=202509) == expected


def test_verified_gap_is_not_an_observed_zero_and_unknown_gap_abstains():
    h = history().loc[lambda r: ~(r.player_master_id.eq("Aq") & r.period.eq(202507))]
    a = actors(); a[0]["current_role_evidence"] = dict(source_ids=[1], source_uri="native://current-role")
    unknown = build_history_evidence(h, a, before_period=202509)
    assert unknown["actors"][0]["role_window"]["status"] == "unknown"
    proof = dict(kind="official_gamebook_not_active_v1", player_master_id="Aq", team="A", period=202507)
    confirmed = build_history_evidence(h, a, before_period=202509, verified_gaps=[proof])
    q = confirmed["actors"][0]
    assert q["role_window"]["verified_inactive_gaps"] == [proof]
    assert q["role_window"]["missing_periods"] == [202507]
    assert [r["period"] for r in q["observed_games"]] == [202505, 202506, 202508]
    assert all(r["pass_attempts"] == 30 for r in q["observed_games"])
    wrong = build_history_evidence(h, a, before_period=202509, verified_gaps=[{**proof, "team": "B"}])
    assert wrong["actors"][0]["role_window"]["status"] == "unknown"


def test_trade_cannot_transplant_history_and_no_current_role_no_gap_bridge():
    h = history(); h.loc[h.player_master_id.eq("Aq") & h.period.eq(202508), "team"] = "B"
    result = build_history_evidence(h, actors(), before_period=202509)
    assert result["actors"][0]["role_window"]["status"] == "unknown"
    assert "same-team" in result["actors"][0]["role_window"]["reason"]
    h = history().loc[lambda r: ~(r.player_master_id.eq("Aq") & r.period.eq(202507))]
    proof = dict(kind="official_gamebook_not_active_v1", player_master_id="Aq", team="A", period=202507)
    result = build_history_evidence(h, actors(), before_period=202509, verified_gaps=[proof])
    assert result["actors"][0]["role_window"]["status"] == "unknown"


def test_negative_or_non_numeric_count_rejected_without_changing_source():
    h = history(); original = deepcopy(h)
    for value in (-1, float("inf"), "not measured"):
        changed = h.copy(); changed["targets"] = changed.targets.astype(object)
        changed.loc[0, "targets"] = value
        with pytest.raises(ValueError, match="Invalid original count"):
            source_history(changed, before_period=202509)
    pd.testing.assert_frame_equal(h, original)
