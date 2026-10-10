from backend.app.tests.product.prepared_optimizer_fixture import prepared_optimizer
"""Research stays outside production; checklist summarizes saved prelock facts."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from backend.app.api.product_routes import get_showdown_research_notes as research_endpoint
from backend.app.product_services import showdown_research_notes as research
from backend.app.product_services.ai_showdown_packet import (
    _classify, _quality, _similarity, build_packet, build_retrospective_packet, render_markdown,
)
from backend.app.product_services.showdown_portfolio_selection import select_showdown_portfolio, signature
from backend.app.product_services.showdown_review_checklist import build_prelock_checklist
from backend.app.tests.product.test_ai_showdown_packet import saved, synthetic_candidate
from backend.app.tests.product.test_showdown_data_readiness import ready_rows, refresh_result, run, service_fixture
from backend.app.tests.product.test_showdown_portfolio_selection import lineup


ROOT = Path(__file__).resolve().parents[4]


def test_research_contract_has_period_baseline_and_limitations_per_finding():
    notes = research_endpoint()
    assert notes["contract_id"] == "showdown_research_notes_v1"
    assert len(notes["findings"]) == 5
    for finding in notes["findings"]:
        assert finding["label"] == "RESEARCH_ONLY / OBSERVATIONAL / NOT PRODUCTION VALIDATED"
        assert all(finding[field] for field in ("sample_period", "comparison_baseline", "limitations"))
    path = ROOT / notes["source"]["path"]
    if path.exists():
        assert sha256(path.read_bytes()).hexdigest() == notes["source"]["sha256"]
        study = json.loads(path.read_text())
        assert notes["sample"]["games"] == study["games"] == 10
        assert notes["sample"]["unresolved_entries"] == study["unresolved_entries"]


def test_changed_research_metadata_cannot_change_production_solver_inputs(tmp_path, monkeypatch):
    notes = research.get_showdown_research_notes()
    rows = ready_rows()
    captures = []
    signatures = []
    for payload in (notes, {"weights": {"QB": 999999}, "salary_left_target": 400,
                            "historical_account_rankings": ["pretend_winner"], "findings": []}):
        path = tmp_path / "notes.json"
        path.write_text(json.dumps(payload))
        monkeypatch.setattr(research, "NOTES_PATH", path)
        assert research_endpoint() == payload
        service = service_fixture(deepcopy(rows))
        with patch.object(research, "get_showdown_research_notes", side_effect=AssertionError("Production read research")), \
                prepared_optimizer(service, return_value=refresh_result()):
            job = run(service)
        assert job.status == "completed", job.message
        call = service._solve_lineup.call_args
        # StrategyProfile contains an immutable mappingproxy; retain that
        # profile and copy the remaining solver arguments independently.
        captures.append((call.args[0].copy(deep=True), {
            k: v if k == "rule_profile" else deepcopy(v) for k, v in call.kwargs.items()}))
        signatures.append([signature(c) for c in job.results])
    pd.testing.assert_frame_equal(captures[0][0], captures[1][0])
    assert captures[0][1] == captures[1][1]
    assert signatures[0] == signatures[1]


def test_research_tags_cannot_change_gpp_portfolio_selection():
    candidates = [lineup("c1", ["core", "a", "b", "c", "d"], 80, 140, 100),
                  lineup("c2", ["core", "e", "f", "g", "h"], 79, 139, 99),
                  lineup("c3", ["i", "j", "k", "l", "m"], 78, 138, 98)]
    limits = {p["player_id"]: 2 for c in candidates for p in c}
    limits["core"] = 1
    expected, before = select_showdown_portfolio(deepcopy(candidates), requested=2, player_limits=limits, captain_limit=2)
    for c in candidates:
        for p in c:
            p["research_metadata"] = {**research.get_showdown_research_notes(), "promote": p["player_id"] == "c2"}
    actual, after = select_showdown_portfolio(candidates, requested=2, player_limits=limits, captain_limit=2)
    assert [signature(c) for c in expected] == [signature(c) for c in actual]
    assert before == after


def test_research_is_not_copied_into_ai_scoring_or_checklist():
    source = saved("thursday")
    before = build_packet(source)
    source["research_notes"] = research.get_showdown_research_notes()
    source["historical_account_rankings"] = ["future winner"]
    for lineup_rows in source["results"]:
        for p in lineup_rows:
            p["research_metadata"] = {"promote": True, "field_outcome": 999999}
    after = build_packet(source)
    assert before["evidence_hash"] == after["evidence_hash"]
    assert before["finalists"] == after["finalists"]
    assert before["control_selection"] == after["control_selection"]
    assert before["ai_review_universe"] == after["ai_review_universe"]
    text = json.dumps(after)
    assert "future winner" not in text and "RESEARCH_ONLY" not in text


def checklist_fixture():
    good = synthetic_candidate(1)
    weak = synthetic_candidate(50, mean=10, ceiling=20)
    # Generated one-QB family fails existing quality; zero-QB family was never generated.
    weak["players"][3]["position"] = "WR"
    weak["construction"] = _classify(weak["players"], {"favorite": "AAA", "underdog": "BBB"}, 49600, None)
    other = deepcopy(good)
    other["candidate_id"] = "captain-swap"
    other["players"][0]["slot"], other["players"][1]["slot"] = "FLEX", "CPT"
    other["construction"] = _classify(other["players"], {"favorite": "AAA", "underdog": "BBB"}, 49500, 90)
    for c in (good, weak, other):
        c["metrics"]["projected_total_ownership"] = 90
    _quality([good, weak, other])
    return [good, weak, other], [good, other]


def make_checklist(candidates, control, *, readiness=None):
    return build_prelock_checklist(candidates, control, control,
        run={"data_cutoff_at": "2026-10-01T20:00:00+00:00"},
        readiness=readiness or {}, player_lookup={},
        overlap=_similarity(*control) if len(control) == 2 else None)


def test_checklist_distinguishes_generation_quality_and_counts_physical_overlap():
    candidates, control = checklist_fixture()
    before = deepcopy(candidates)
    checklist = make_checklist(candidates, control)
    families = {f["family"]: f for f in checklist["qb_families"]}
    assert families["zero_qbs"]["absence_stage"] == "generation"
    assert families["zero_qbs"]["reason_codes"] == ["not_present_in_saved_generated_pool", "generation_reason_unavailable"]
    assert families["one_qb:AAA"]["absence_stage"] == "quality_filtering"
    assert families["one_qb:AAA"]["reason_codes"] == ["outside_multidimensional_quality_range"]
    assert checklist["scopes"]["generated"]["qb_counts"] == {"0": 0, "1": 1, "2": 2}
    assert checklist["scopes"]["quality_eligible"]["receiver_captain_pairings"] == {"with_own_qb": 1, "without_own_qb": 0}
    assert checklist["proposed_pair"]["physical_player_overlap"] == 6  # CPT/FLEX swap is the same physical roster.
    assert candidates == before  # Display construction is pure.
    assert checklist["nonbinding"] is True


@pytest.mark.parametrize("fresh,source,expected", [(False, True, None), (True, False, None), (True, True, 90)])
def test_checklist_never_zero_fills_or_invents_ownership_provenance(fresh, source, expected):
    candidates, control = checklist_fixture()
    readiness = {"ownership": {"ownership_fresh": fresh, "ownership_source": ["frozen-provider"] if source else [],
                              "source_ids": ["ownership-run-1"], "ownership_observed_at": "2026-10-01T19:00:00+00:00"}}
    checklist = make_checklist(candidates, control, readiness=readiness)
    assert {row["projected_total_ownership"] for row in checklist["candidate_details"]} == {expected}
    assert checklist["ownership_provenance"]["source_ids"] == ["ownership-run-1"]


def test_missing_pair_and_retrospective_cutoff_remain_explicit():
    candidates, control = checklist_fixture()
    checklist = make_checklist(candidates, control[:1])
    assert checklist["proposed_pair"]["physical_player_overlap"] is None
    assert checklist["proposed_pair"]["unavailable_reason"] == "saved_proposal_is_not_exactly_two_entries"
    source = saved("thursday")
    source["data_cutoff_at"] = "2026-10-02T03:00:00+00:00"
    with pytest.raises(ValueError, match="at or after kickoff"):
        build_packet(source)


def test_future_ownership_clock_cannot_appear_as_sourced_prelock_ownership():
    candidates, control = checklist_fixture()
    checklist = make_checklist(candidates, control, readiness={"ownership": {
        "ownership_fresh": True, "ownership_source": ["provider"], "source_ids": ["run"],
        "ownership_observed_at": "2026-10-02T20:00:00+00:00"}})
    assert checklist["ownership_provenance"]["status"] == "unavailable"
    assert checklist["ownership_provenance"]["observed_at"] is None
    assert checklist["ownership_provenance"]["source_ids"] == []
    assert all(c["projected_total_ownership"] is None for c in checklist["candidate_details"])


def test_after_kickoff_generation_cannot_receive_a_prelock_checklist():
    packet = build_retrospective_packet(saved("sunday"))
    assert "prelock_review_checklist" not in packet
    assert "Prelock review checklist unavailable" in render_markdown(packet)


def test_packet_export_renders_compact_checklist_and_preserves_policy():
    packet = build_packet(saved("thursday"))
    assert packet["finalist_policy_version"] == "ai_showdown_finalists_v2"
    assert "Nonbinding prelock review checklist" in render_markdown(packet)
    schema = json.loads((ROOT / "docs/product/ai_showdown_selection_packet_v1.schema.json").read_text())
    assert "prelock_review_checklist" in schema["properties"]
