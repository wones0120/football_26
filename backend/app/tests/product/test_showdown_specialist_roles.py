from backend.app.tests.product.prepared_optimizer_fixture import prepared_optimizer
"""DFS roster positions do not reinterpret affirmative specialist role facts."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from Database.player_identity import normalize_position
from backend.app.product_services.showdown_player_context import (
    CONTEXT_CONTRACT, compose_player_contexts, sourced_depth_role,
)
from backend.app.product_services.showdown_data_readiness import freeze_evidence, ShowdownDataNotReady
from backend.app.tests.product.test_showdown_upstream_data import canonical_rows
from backend.app.tests.product.test_showdown_data_readiness import (
    NOW, AT, assess, service_fixture, run, refresh_result,
)


def specialist_context(pid="specialist", name="Any Native Identity", cutoff=NOW):
    kind, role = sourced_depth_role("LS", "TE", 1)
    salary = dict(player_id=pid, player_name=name, team="AAA", position="TE", salary_source_row_id="native-specialist")
    base = dict(player_id=pid, team="AAA", position="TE", source="official-depth",
                source_ids=["snapshot-1", "gsis-specialist"], observed_at=cutoff.isoformat(), received_at=cutoff.isoformat())
    return compose_player_contexts([salary], [dict(base, kind="roster_status", status="ACT"),
        dict(base, kind=kind, role=role, source_position="LS")], cutoff=cutoff, max_age_hours=24)[0]


def specialist_rows():
    rows = canonical_rows()
    specialist = deepcopy(rows[1])
    specialist.update(specialist_context()["evidence_json"])
    specialist.update(player_id="specialist", name="Any Native Identity", position="TE",
        salary_source_row_id="native-specialist", projection_run_id=None, projection=None, p90=None,
        projection_observed_at=None, projection_model_version=None, feature_inputs_complete=False,
        projection_inputs_complete=False, captain_ownership=None, flex_ownership=None,
        ownership_run_id=None, ownership_source=None, ownership_observed_at=None)
    return rows + [specialist]


@pytest.mark.parametrize("name", ["Evan Deckers", "Unrelated Name", ""])
def test_dfs_te_and_sourced_ls_preserve_distinct_roles_without_name_rules(name):
    context = specialist_context(name=name)
    assert context["position"] == context["evidence_json"]["dfs_position"] == "TE"
    evidence = context["evidence_json"]
    assert evidence["canonical_role"] == "long_snapper"
    assert evidence["role_source_position"] == "LS"
    assert evidence["canonical_context_reason_codes"] == []
    assert evidence["role_source_ids"] == ["snapshot-1", "gsis-specialist"]
    assert evidence["role_observed_at"] == AT
    assert normalize_position("LS") != normalize_position("TE")


def test_specialist_native_audit_and_frozen_pool_without_projection_or_ownership():
    rows = specialist_rows()
    # All consumed players have required ownership; the specialist has none.
    for row in rows[:-1]:
        row.update(captain_ownership=10, flex_ownership=20, ownership_source="model",
                   ownership_run_id="ownership-1", ownership_observed_at=AT)
    readiness = assess(rows, ownership_required=True)
    assert readiness["status"] == "READY", readiness["reason_codes"]
    diagnostic = readiness["player_pool_readiness"]
    assert diagnostic["summary"]["native_salary_players"] == 7
    assert diagnostic["summary"]["generation_eligible"] == diagnostic["summary"]["projection_rows_required"] == 6
    assert diagnostic["summary"]["explicitly_excluded_specialist"] == 1
    assert diagnostic["summary"]["explicitly_unavailable"] == diagnostic["summary"]["unknown_availability"] == 0
    player = diagnostic["players"][-1]
    assert player["availability_state"] == "AVAILABLE"
    assert player["disposition"] == "explicitly_excluded_specialist"
    assert player["exclusion_reason"] == "unsupported_non_scoring_specialist_role"
    assert player["dfs_position"] == "TE" and player["canonical_role"] == "long_snapper"
    assert player["role_source_position"] == "LS"
    assert player["salary_row_id"] == "native-specialist" and player["blockers"] == []
    assert player["generation_eligible"] is False and player["projection_ready"] is False
    frozen = freeze_evidence(rows, readiness, optimizer_run_id="new")
    assert len(frozen["native_player_pool"]) == 7 and len(frozen["player_pool"]) == 6
    assert frozen["native_player_pool"][-1]["canonical_role"] == "long_snapper"
    assert "specialist" not in readiness["generation_eligible_player_ids"]


@pytest.mark.parametrize("field,value", [
    ("role_source", None), ("role_source_ids", []), ("role_observed_at", None),
    ("role_source_position", None), ("canonical_role", None),
    ("role_observed_at", (NOW-timedelta(days=10)).isoformat()),
    ("role_observed_at", (NOW+timedelta(hours=1)).isoformat()),
    ("canonical_context_reason_codes", ["player_role_conflict"]),
    ("pregame_role_uncertain", True), ("role_uncertain", True),
])
def test_specialist_exclusion_requires_current_affirmative_unambiguous_evidence(field, value):
    rows = specialist_rows(); rows[-1][field] = value
    result = assess(rows)
    assert result["status"] == "NOT_READY"
    assert result["player_pool_readiness"]["summary"]["explicitly_excluded_specialist"] == 0
    assert any(code.startswith("player_role") for code in result["reason_codes"])


@pytest.mark.parametrize("state,disposition", [("UNKNOWN", "unknown_availability"), ("UNAVAILABLE", "explicitly_unavailable")])
def test_specialist_role_does_not_replace_availability_disposition(state, disposition):
    rows = specialist_rows(); rows[-1]["availability_state"] = state
    assert assess(rows)["player_pool_readiness"]["players"][-1]["disposition"] == disposition


@pytest.mark.parametrize("source,dfs", [("TE", "TE"), ("FB", "RB"), ("HB", "RB"), ("FL", "WR"), ("SE", "WR")])
def test_offensive_role_compatible_mappings_remain_eligible(source, dfs):
    kind, role = sourced_depth_role(source, dfs, 2)
    assert kind == "role" and role == "expected_backup"
    rows = canonical_rows(); rows[1].update(position=dfs, dfs_position=dfs, role_source_position=source, canonical_role=role)
    result = assess(rows)
    assert result["status"] == "READY"
    assert result["player_pool_readiness"]["players"][1]["generation_eligible"] is True


def test_unknown_and_incompatible_roles_still_block():
    assert sourced_depth_role("UNKNOWN", "TE", 1)[0] == "role_position_conflict"
    assert sourced_depth_role("LB", "TE", 1)[0] == "role_position_conflict"
    rows = specialist_rows(); rows[-1].update(canonical_role=None, role_source=None,
        canonical_context_reason_codes=["player_role_position_conflict", "player_role_missing"])
    assert "player_role_position_conflict" in assess(rows)["reason_codes"]


def test_low_projection_and_salary_do_not_establish_specialist_status():
    rows = canonical_rows(); rows[1].update(position="TE", projection=0, p90=0, salary=200,
        canonical_role="expected_backup", role_source_position="TE")
    result = assess(rows)
    assert result["status"] == "READY"
    assert result["player_pool_readiness"]["players"][1]["generation_eligible"] is True


def test_invalid_native_identity_cannot_receive_specialist_disposition():
    rows = specialist_rows(); rows[-1]["identity_resolved"] = False
    result = assess(rows)
    assert result["status"] == "NOT_READY" and "salary_pool_missing" in result["reason_codes"]
    assert result["player_pool_readiness"]["players"][-1]["disposition"] == "invalid_salary_or_identity"


def test_future_role_receipt_and_equal_clock_role_conflict_fail_closed():
    context = specialist_context(); facts = context["evidence_json"]["source_facts"]
    salaries = [dict(player_id="specialist", team="AAA", position="TE")]
    future = deepcopy(facts); future[1]["received_at"] = (NOW+timedelta(seconds=1)).isoformat()
    result = compose_player_contexts(salaries, future, cutoff=NOW, max_age_hours=24)[0]
    assert result["evidence_json"]["canonical_role"] is None
    assert "player_role_missing" in result["evidence_json"]["canonical_context_reason_codes"]
    conflicting = [*facts, dict(facts[1], role="expected_starter", source_position="TE")]
    result = compose_player_contexts(salaries, conflicting, cutoff=NOW, max_age_hours=24)[0]
    assert result["evidence_json"]["canonical_role"] is None
    assert "player_role_conflict" in result["evidence_json"]["canonical_context_reason_codes"]


@pytest.mark.parametrize("field", ["projection", "role_source", "game_total_line", "is_starting_qb"])
def test_specialist_exclusion_never_bypasses_other_blockers_or_calls_solver(field):
    rows = specialist_rows(); rows[0][field] = None
    service = service_fixture(rows)
    with prepared_optimizer(service, return_value=refresh_result()):
        with pytest.raises(ShowdownDataNotReady):
            run(service)
    service._solve_lineup.assert_not_called()


def test_solver_receives_only_remaining_ready_pool():
    service = service_fixture(specialist_rows())
    with prepared_optimizer(service, return_value=refresh_result()):
        job = run(service)
    assert job.status == "completed", job.message
    assert "specialist" not in set(service._solve_lineup.call_args.args[0]["player_id"])
    assert job.params["data_readiness"]["status"] == "READY"


def test_projection_builder_excludes_specialist_before_feature_lookup_and_preserves_metadata():
    from backend.app.tests.product.test_canonical_projection_inputs import inputs, prepare, CUTOFF
    matrix, salaries = inputs()
    specialist = salaries.copy(); specialist["player_master_id"] = "specialist"
    specialist["position"] = "TE"; specialist["curated_salary_id"] += 10
    specialist["source_player_key"] = ["specialist-flex", "specialist-cpt"]
    evidence = dict(canonical_context_contract=CONTEXT_CONTRACT, availability_state="AVAILABLE",
        availability_status="ACT", availability_source="official", availability_source_ids=["roster-1"],
        availability_observed_at=CUTOFF.isoformat())
    contexts = pd.DataFrame([
        dict(player_master_id="canonical-1", source="canonical", observed_at=CUTOFF, received_at=CUTOFF,
             injury_status="ACT", evidence_json=evidence),
        dict(specialist_context(cutoff=CUTOFF), player_master_id="specialist", received_at=CUTOFF),
    ])
    _, target, metadata = prepare(matrix, pd.concat([salaries,specialist],ignore_index=True), pregame_context=contexts)
    assert target["player_id"].tolist() == ["canonical-1"]
    pool = metadata["canonical_player_pool"]
    assert pool["generation_eligible_player_ids"] == ["canonical-1"]
    assert pool["explicitly_unavailable_player_ids"] == []
    assert pool["explicitly_excluded_specialist_player_ids"] == ["specialist"]
    assert pool["specialist_exclusion_reason"] == "unsupported_non_scoring_specialist_role"
    assert metadata["salary_status_policy"]["excluded_player_count"] == 0
