from backend.app.tests.product.prepared_optimizer_fixture import prepared_optimizer
"""Sourced pool dispositions, independent clocks and canonical market joins."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from backend.app.product_services.showdown_player_context import (
    CONTEXT_CONTRACT, compose_player_contexts, attach_context_fields, player_pool_diagnostic,
)
from backend.app.product_services.market_snapshots import attach_pool_market_context
from backend.app.product_services.showdown_data_readiness import freeze_evidence, ShowdownDataNotReady
from backend.app.tests.product.test_showdown_data_readiness import (
    NOW, AT, ready_rows, assess, service_fixture, run, refresh_result,
)


def salary(pid="p", position="WR"):
    return dict(player_id=pid, team="TB", position=position, salary_source_row_id="native-1")


def fact(status="ACT", *, kind="roster_status", at=NOW, pid="p", **kwargs):
    return dict(player_id=pid, team="TB", position="WR", kind=kind, status=status,
                source="official", source_ids=["source-1"], source_uri="https://example.test/source",
                observed_at=at.isoformat(), received_at=at.isoformat(), **kwargs)


def merged(facts, salaries=None):
    return compose_player_contexts([salary()] if salaries is None else salaries, facts, cutoff=NOW, max_age_hours=24)


def canonical_rows():
    rows = ready_rows()
    for r in rows:
        r.update(canonical_context_contract=CONTEXT_CONTRACT, availability_state="AVAILABLE",
                 availability_status="ACT", availability_source="official", availability_observed_at=AT,
                 availability_source_ids=["roster-1"], canonical_role="expected_starter", role_source="official-chart",
                 role_observed_at=AT, role_source_ids=["depth-1"], canonical_context_reason_codes=[],
                 feature_inputs_complete=True, projection_inputs_complete=True)
    return rows


def extra_unavailable(status="OUT"):
    rows = canonical_rows()
    excluded = deepcopy(rows[1]); excluded.update(player_id="unavailable", availability_state="UNAVAILABLE",
        availability_status=status, projection_run_id=None, projection=None, p90=None, projection_inputs_complete=False,
        feature_inputs_complete=False, canonical_role=None, role_source=None, role_source_ids=[], role_observed_at=None,
        team_spread_line=None, game_total_line=None, team_implied_total=None, market_observed_at=None)
    return rows + [excluded]


@pytest.mark.parametrize("status", ["OUT", "INACTIVE", "IR", "SUSPENDED", "PS"])
def test_unavailable_removed_before_projection_and_market_completeness(status):
    rows = extra_unavailable(status)
    readiness = assess(rows)
    assert readiness["status"] == "READY", readiness["reason_codes"]
    assert readiness["player_pool_readiness"]["summary"]["explicitly_unavailable"] == 1
    frozen = freeze_evidence(rows, readiness, optimizer_run_id="new")
    assert len(frozen["native_player_pool"]) == 7 and len(frozen["player_pool"]) == 6
    assert "unavailable" not in {r["player_id"] for r in frozen["player_pool"]}


def test_active_source_remains_eligible_and_absence_is_unknown():
    active = merged([fact(), fact(kind="role", role="expected_starter")])[0]
    assert active["evidence_json"]["availability_state"] == "AVAILABLE"
    unknown = merged([fact(kind="role", role="expected_starter")])[0]
    assert unknown["evidence_json"]["availability_state"] == "UNKNOWN"
    assert unknown["availability_probability"] is None


def test_current_out_overrides_generic_roster_presence():
    result = merged([fact("OUT", kind="injury_status", at=NOW-timedelta(hours=1)), fact()])[0]
    assert result["evidence_json"]["availability_status"] == "OUT"
    assert result["evidence_json"]["availability_state"] == "UNAVAILABLE"


def test_newer_game_status_supersedes_old_matching_semantics():
    result = merged([fact("OUT", kind="game_status", at=NOW-timedelta(hours=1)),
                     fact("ACTIVE", kind="game_status")])[0]
    assert result["evidence_json"]["availability_state"] == "AVAILABLE"


def test_equal_clock_conflict_is_deterministic_unknown():
    facts = [fact("OUT", kind="game_status"), fact("ACTIVE", kind="game_status")]
    a, b = merged(facts)[0], merged(list(reversed(facts)))[0]
    assert a["evidence_json"]["availability_state"] == b["evidence_json"]["availability_state"] == "UNKNOWN"
    assert "player_status_conflict" in a["evidence_json"]["canonical_context_reason_codes"]


def test_stale_status_cannot_be_laundered_by_new_role_clock():
    ctx = merged([fact(at=NOW-timedelta(days=2)), fact(kind="role",role="expected_starter")])[0]
    assert ctx["observed_at"] == NOW
    assert ctx["evidence_json"]["availability_state"] == "UNKNOWN"
    assert "player_status_stale" in ctx["evidence_json"]["canonical_context_reason_codes"]
    rows = canonical_rows(); rows[1]["availability_observed_at"] = (NOW-timedelta(days=2)).isoformat()
    result = assess(rows)
    assert "player_status_stale" in result["reason_codes"]
    assert result["player_pool_readiness"]["players"][1]["disposition"] == "unknown_availability"


def test_future_receipt_and_wrong_identity_cannot_establish_status():
    f = fact(); f["received_at"] = (NOW+timedelta(seconds=1)).isoformat()
    assert merged([f])[0]["evidence_json"]["availability_state"] == "UNKNOWN"
    assert merged([fact(pid="another-canonical-id")])[0]["evidence_json"]["availability_state"] == "UNKNOWN"
    f = fact(); f["team"] = "DAL"
    assert merged([f])[0]["evidence_json"]["availability_state"] == "UNKNOWN"


@pytest.mark.parametrize("field,code", [("projection_inputs_complete","projection_missing"),
                                       ("feature_inputs_complete","feature_missing")])
def test_eligible_missing_projection_or_feature_blocks(field, code):
    rows = canonical_rows(); rows[1][field] = False
    assert code in assess(rows)["reason_codes"]


def test_every_native_player_has_a_disposition_and_unknown_blocks_solver():
    rows = extra_unavailable(); unknown = deepcopy(rows[1]); unknown.update(player_id="unknown",availability_state="UNKNOWN")
    rows.append(unknown)
    invalid = deepcopy(rows[1]); invalid.update(player_id="invalid",identity_resolved=False,salary=-1)
    rows.append(invalid)
    result = assess(rows); diagnostic = result["player_pool_readiness"]
    assert len(diagnostic["players"]) == len(rows)
    assert {r["disposition"] for r in diagnostic["players"]} == {
        "generation_eligible", "explicitly_unavailable", "unknown_availability", "invalid_salary_or_identity"}
    service = service_fixture(rows)
    with prepared_optimizer(service, return_value=refresh_result()):
        with pytest.raises(ShowdownDataNotReady): run(service)
    service._solve_lineup.assert_not_called()


def test_missing_role_does_not_change_qb_readiness_and_ownership_contract():
    rows = canonical_rows(); rows[1].update(canonical_role=None, role_source=None)
    result = assess(rows)
    assert result["required_sources"]["starting_qb"]["status"] == "READY"
    assert result["ownership"]["status"] == "OPTIONAL_MISSING"
    assert "player_role_missing" in result["reason_codes"]
    assert "ownership_missing_required" in assess(rows,ownership_required=True)["reason_codes"]


def test_canonical_context_attaches_even_without_projection():
    row = dict(player_id="p",projection_run_id=None,player_team="TB")
    ctx = merged([fact("OUT",kind="game_status")])[0]; ctx["context_run_id"] = "canonical-run"
    frame = attach_context_fields(pd.DataFrame([row]),[ctx])
    assert frame.iloc[0]["availability_state"] == "UNAVAILABLE"
    assert frame.iloc[0]["pregame_context_run_id"] == "canonical-run"


def test_market_association_is_independent_of_player_projection_join():
    from backend.app.product_services.replay import parse_slate_lock
    rows = pd.DataFrame([dict(player_id="good",player_team="TB",opponent_team="DAL",game_id=ready_rows()[0]["game_id"]),
                         dict(player_id="no-projection",player_team="DAL",opponent_team="TB",game_id=ready_rows()[0]["game_id"],projection_run_id=None),
                         dict(player_id="bad-team",player_team="NYJ",opponent_team="BUF",game_id=ready_rows()[0]["game_id"])])
    observation = dict(season=NOW.year,week=5,game_id="canonical-game",home_team="DAL",away_team="TB",
        kickoff_at=parse_slate_lock(rows["game_id"]),game_total=47.5,home_spread=-9.5,
        observed_at=NOW,ingested_at=NOW,source="nflverse_schedules",market_snapshot_id="market-1",source_snapshot_id="source-1")
    result = attach_pool_market_context(rows,[observation],season=NOW.year,week=5,cutoff=NOW)
    assert result.iloc[0]["team_spread_line"] == 9.5
    assert result.iloc[1]["team_spread_line"] == -9.5
    assert result.iloc[1]["canonical_game_id"] == "canonical-game"
    assert result.iloc[:2]["game_total_line"].tolist() == [47.5,47.5]
    assert pd.isna(result.iloc[2]["game_total_line"])
    assert not result.iloc[2]["market_context_point_in_time_safe"]


def test_market_after_cutoff_never_populates_pool():
    rows = pd.DataFrame([dict(player_id="p",player_team="TB",opponent_team="DAL",game_id=ready_rows()[0]["game_id"])])
    from backend.app.product_services.replay import parse_slate_lock
    quote = dict(season=NOW.year,week=5,game_id="game",home_team="DAL",away_team="TB",kickoff_at=parse_slate_lock(rows["game_id"]),
        game_total=47.5,home_spread=-9.5,observed_at=NOW+timedelta(seconds=1),ingested_at=NOW,source="nflverse",market_snapshot_id="m")
    result = attach_pool_market_context(rows,[quote],season=NOW.year,week=5,cutoff=NOW)
    assert not result.iloc[0]["market_context_point_in_time_safe"]


def test_feature_and_projection_inputs_use_exact_canonical_eligible_set():
    from backend.app.tests.product.test_canonical_projection_inputs import inputs, prepare, CUTOFF
    matrix, salaries = inputs()
    excluded = salaries.copy(); excluded["player_master_id"] = "canonical-unavailable"
    excluded["curated_salary_id"] += 10
    excluded["source_player_key"] = ["out-flex", "out-cpt"]
    # No feature scaffold exists for this unavailable player. It must never be
    # looked up in the model target or filled with a synthetic zero projection.
    contexts = pd.DataFrame([
        dict(player_master_id="canonical-1", source="canonical", observed_at=CUTOFF,received_at=CUTOFF,
             injury_status="ACT", evidence_json=dict(canonical_context_contract=CONTEXT_CONTRACT,
             availability_state="AVAILABLE", availability_status="ACT",availability_source="official",
             availability_source_ids=["r1"],availability_observed_at=CUTOFF.isoformat())),
        dict(player_master_id="canonical-unavailable", source="canonical", observed_at=CUTOFF,received_at=CUTOFF,
             injury_status="PS", evidence_json=dict(canonical_context_contract=CONTEXT_CONTRACT,
             availability_state="UNAVAILABLE",availability_status="PS",availability_source="official",
             availability_source_ids=["r2"],availability_observed_at=CUTOFF.isoformat())),
    ])
    _, target, metadata = prepare(matrix,pd.concat([salaries,excluded],ignore_index=True),pregame_context=contexts)
    assert target["player_id"].tolist() == ["canonical-1"]
    assert metadata["canonical_player_pool"]["scoring_player_ids"] == ["canonical-1"]
    assert metadata["canonical_player_pool"]["generation_eligible_player_ids"] == ["canonical-1"]
    assert metadata["canonical_player_pool"]["explicitly_unavailable_player_ids"] == ["canonical-unavailable"]
    contexts.at[0,"evidence_json"] = {**contexts.at[0,"evidence_json"],"availability_state":"UNKNOWN"}
    from backend.app.product_services.showdown_player_context import PlayerContextUnresolved
    with pytest.raises(PlayerContextUnresolved):
        prepare(matrix,salaries,pregame_context=contexts)


def test_solver_receives_only_frozen_eligible_rows():
    rows = extra_unavailable(); service = service_fixture(rows)
    with prepared_optimizer(service, return_value=refresh_result()):
        job = run(service)
    assert job.status == "completed", job.message
    assert "unavailable" not in set(service._solve_lineup.call_args.args[0]["player_id"])
    assert len(job.params["showdown_evidence_snapshot"]["native_player_pool"]) == 7


def test_live_canonical_requirement_fails_closed_on_legacy_context():
    from backend.app.product_services.showdown_data_readiness import evaluate_readiness, freshness_rules
    from backend.app.config import get_settings
    from backend.app.tests.product.test_showdown_data_readiness import PROJECTION
    readiness = evaluate_readiness(ready_rows(),season=NOW.year,week=5,slate="THURSDAY_NIGHT",projection_run_id=PROJECTION,
        evidence_cutoff=NOW,evaluated_at=NOW,rules=freshness_rules(get_settings()),require_canonical_context=True)
    assert "canonical_player_context_missing" in readiness["reason_codes"]


def test_role_resolver_preserves_structured_source_lineage():
    from backend.app.product_services.player_roles import resolve_player_roles
    row = pd.DataFrame([dict(player_id="p",position="WR",player_team="TB")])
    context = merged([fact(),fact(kind="role",role="expected_starter")])[0]
    resolved,_ = resolve_player_roles(row,contexts=[context])
    assert resolved.iloc[0]["role_starter_evidence"]["source_ids"] == ["source-1"]


def test_generic_active_roster_does_not_clear_stale_game_specific_out():
    context = merged([fact("OUT",kind="game_status",at=NOW-timedelta(days=2)),fact()])[0]
    assert context["evidence_json"]["availability_state"] == "UNKNOWN"
    assert "player_status_stale" in context["evidence_json"]["canonical_context_reason_codes"]


def test_native_gsis_identity_precedes_position_but_never_uses_names():
    from backend.app.product_services.showdown_player_context import match_source_player
    salaries = {"canonical-id":dict(team="TB",position="TE",player_name="Same Name")}
    row = dict(team="TB",position="LS",player_name="Another Spelling")
    assert match_source_player(row,"gsis-1",{"gsis-1":{"canonical-id"}},salaries) == "canonical-id"
    assert match_source_player(row,"missing-native-id",{},salaries) is None
    salaries["duplicate-id"] = dict(team="TB",position="TE")
    assert match_source_player(row,"gsis-1",{"gsis-1":set(salaries)},salaries) is None


def test_known_availability_does_not_clear_role_position_conflict():
    context = merged([fact(),fact(kind="role_position_conflict",role="expected_starter",source_position="LS")])[0]
    assert context["evidence_json"]["availability_state"] == "AVAILABLE"
    assert "player_role_position_conflict" in context["evidence_json"]["canonical_context_reason_codes"]
    rows = canonical_rows();rows[1].update(canonical_role=None,role_source=None,role_source_ids=[],
        canonical_context_reason_codes=context["evidence_json"]["canonical_context_reason_codes"])
    assert "player_role_position_conflict" in assess(rows)["reason_codes"]


def test_completed_training_labels_refresh_before_live_cutoff_only():
    from unittest.mock import MagicMock
    from backend.app.product_services.showdown_data_readiness import refresh_training_labels
    from backend.app.product_services.canonical_projection_inputs import StaleTrainingOutcomeError
    engine = MagicMock()
    with patch("backend.app.product_services.canonical_projection_inputs.load_inputs",side_effect=StaleTrainingOutcomeError([(2026,4)])), \
         patch("backend.app.services.lineup_learning.LineupLearningService") as learning:
        learning.return_value.rebuild_player_game_feature_matrix.return_value = dict(slates_total=1,slates_failed=0,rows_written=100)
        result = refresh_training_labels(engine,season=2026,week=5,slate="THURSDAY_NIGHT")
    assert result == dict(periods=[dict(season=2026,week=4)],rows_written=100)
    assert learning.return_value.rebuild_player_game_feature_matrix.call_args.kwargs["weeks"] == [4]
    with patch("backend.app.product_services.canonical_projection_inputs.load_inputs",side_effect=StaleTrainingOutcomeError([(2026,5)])):
        with pytest.raises(ValueError,match="precede the target"):
            refresh_training_labels(engine,season=2026,week=5,slate="THURSDAY_NIGHT")


def test_existing_football_position_aliases_preserve_fullback_role():
    from Database.player_identity import normalize_position
    assert normalize_position("FB") == normalize_position("RB")
    assert normalize_position("LS") != normalize_position("TE")


def test_manual_source_context_retains_json_safe_original_clocks():
    import json
    from backend.app.product_services.showdown_player_context import retained_workload_context
    observed, received = NOW-timedelta(hours=2), NOW-timedelta(hours=1)
    original = dict(observed_at=observed, received_at=received, target_share=.2,
                    evidence_json={"source_snapshot_id":"official-snapshot"})
    retained = retained_workload_context(original)
    assert retained["observed_at"] == observed.isoformat()
    assert retained["received_at"] == received.isoformat()
    assert retained["target_share"] == .2
    assert json.loads(json.dumps(retained))["evidence_json"]["source_snapshot_id"] == "official-snapshot"
    assert original["observed_at"] == observed
    retained["evidence_json"]["source_snapshot_id"] = "changed-copy"
    assert original["evidence_json"]["source_snapshot_id"] == "official-snapshot"


def test_new_official_out_can_precede_latest_derived_role_clock():
    result = merged([fact(), fact("OUT",kind="game_status",at=NOW-timedelta(hours=12)),
        fact(kind="role",role="expected_starter",at=NOW-timedelta(hours=6))])[0]
    assert result["evidence_json"]["availability_state"] == "UNAVAILABLE"
    assert result["evidence_json"]["availability_observed_at"] == (NOW-timedelta(hours=12)).isoformat()
