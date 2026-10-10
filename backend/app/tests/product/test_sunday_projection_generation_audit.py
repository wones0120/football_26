from copy import deepcopy
from datetime import datetime, timezone

import pytest

from scripts.audit_sunday_projection_generation import audit_rows, shadow_contract
from backend.app.product_services.classic_strategy_contract import digest


def test_unknown_role_fields_do_not_become_zero_or_complete_evidence():
    report = audit_rows([dict(player_id="canonical", position="RB", projection=10, p90=20)],
                        {"canonical"}, datetime(2026, 10, 10, tzinfo=timezone.utc))
    player = report["players"][0]
    assert player["in_recommended_lineup"]
    assert len(player["missing_explicit_role_fields"]) == 6
    assert report["field_coverage"]["pregame_expected_snaps"] == 0
    assert set(player["warnings"]) == {"missing_projected_carries", "missing_projected_targets"}


def test_quantiles_and_evidence_cutoff_are_checked():
    row = dict(player_id="canonical", position="QB", projection=30, p90=20,
               predicted_p10=10, predicted_p50=25,
               role_observed_at="2026-10-11T00:00:00+00:00",
               market_observed_at="2026-10-09T00:00:00", practice_observed_at="NaT")
    warnings = audit_rows([row], set(), datetime(2026, 10, 10, tzinfo=timezone.utc))["players"][0]["warnings"]
    assert set(warnings) == {"missing_or_inconsistent_mean_p90", "unordered_quantiles",
                            "evidence_after_cutoff:role_observed_at", "ambiguous_clock:market_observed_at"}


@pytest.mark.parametrize("arm", ["mean_led", "template_rotation"])
def test_shadow_changes_only_declared_effective_setting_and_preserves_source(arm):
    source = dict(strategy_id="classic", execution_mode="PRODUCTION", effective=dict(
        players=[{"player_id": "canonical", "projection": 10}],
        pipeline_options={"num_lineups": 5, "max_lineup_overlap": 5},
        resolved_config=dict(stack_templates=[[1, 0], [1, 1]], objective_weights=dict(
            projection=.35, ceiling=.45, leverage=.05, correlation=.15))))
    source["effective_sha256"] = digest(source["effective"])
    source["sha256"] = digest(source)
    before = deepcopy(source)
    result = shadow_contract(source, arm)
    assert source == before
    assert result["execution_mode"] == "RESEARCH_SHADOW"
    assert result["effective_sha256"] == digest(result["effective"])
    unsigned = deepcopy(result)
    unsigned.pop("sha256")
    assert result["sha256"] == digest(unsigned)
    expected = deepcopy(before["effective"])
    if arm == "mean_led":
        expected["resolved_config"]["objective_weights"].update(projection=.35 + .20, ceiling=.45 - .20)
    else:
        expected["resolved_config"]["stack_templates"].reverse()
    assert result["effective"] == expected
