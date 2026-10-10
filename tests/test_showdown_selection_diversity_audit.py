"""Time-safety/identity tests for the isolated research audit, not a selector."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts import audit_showdown_selection_diversity as audit


def candidate(cid, players, captain, objective=100, mean=.98, ceiling=.98, finalist=False):
    return {"candidate_id": cid, "players": [{"player_id": p, "slot": "CPT" if p == captain else "FLEX", "flex_ownership": 20} for p in players],
        "metrics": {"objective_score": objective, "selector_rank": int(cid), "projected_mean": mean*100, "summed_marginal_p90_proxy": ceiling*200},
        "quality_eligibility": {"eligible": True, "mean_fraction": mean, "ceiling_fraction": ceiling},
        "is_deterministic_finalist": finalist, "market_compatibility": "HIGH",
        "construction": {"captain_player_id": captain, "captain_position": "QB", "captain_archetype": "QB", "captain_side": "favorite",
            "football_scenarios": ["balanced"], "primary_football_scenario": "balanced", "primary_thesis_signature": "balanced|QB",
            "captain_script_combination": "favorite|QB", "team_counts": {"A": 3, "B": 3}, "qb_structure": "both_qbs", "risk_flags": []}}


@pytest.mark.parametrize("field", ["actual_points", "actual_fantasy_points", "actual_ownership", "contest_rank", "winning_lineup",
                                  "top_field_composition", "postgame_ownership", "hindsight_tags", "learning_report_fields", "final_score"])
def test_deep_outcome_poison_rejected(field):
    rows = [candidate("1", list("abcdef"), "a", finalist=True), candidate("2", list("abcdeg"), "b")]
    rows[1]["players"][0]["nested"] = {field: 999}
    with pytest.raises(ValueError, match="Postgame"):
        audit.attention_sets(rows)
    with pytest.raises(ValueError, match="Postgame"):
        audit.pair_features(*rows)


def test_captain_changes_do_not_disguise_shared_physical_players():
    pair = audit.pair_features(candidate("1", list("abcdef"), "a"), candidate("2", list("abcdeg"), "b"))
    assert pair["different_captain"] and pair["shared_player_count"] == 5
    assert pair["shared_flex_player_count"] == 3
    assert pair["unique_players_across_pair"] == 7
    assert pair["player_core_classification"] == "high_player_core_overlap"


def test_six_shared_different_captains_is_not_duplicate_lineup():
    pair = audit.pair_features(candidate("1", list("abcdef"), "a"), candidate("2", list("abcdef"), "b"))
    assert pair["identical_physical_roster"] and not pair["duplicate_lineup"]
    assert pair["unique_players_across_pair"] == 6


def test_quality_eligibility_is_preserved_even_with_great_ceiling():
    rows = [candidate("1", list("abcdef"), "a", finalist=True), candidate("2", list("abcdeg"), "b", ceiling=1)]
    rows[1]["quality_eligibility"]["eligible"] = False
    assert all(p["visible_candidate_ids"] == ["1"] for p in audit.attention_sets(rows).values())


def test_actual_scores_cannot_change_frozen_selections():
    rows = [candidate("1", list("abcdef"), "a", objective=120, finalist=True),
            candidate("2", list("abcdeg"), "b", objective=110), candidate("3", list("abghij"), "g", objective=100)]
    before = deepcopy(rows)
    attention = audit.attention_sets(rows)
    pairs = [audit.pair_features(rows[i], rows[j]) for i, j in [(0, 1), (0, 2), (1, 2)]]
    selected = audit.pair_selections(pairs)
    actuals = {p: 100 if p in "ghij" else -100 for p in "abcdefghij"}
    scores = {r["candidate_id"]: audit.score_candidate(r, actuals) for r in rows}
    audit.summarize_ids(attention["B_top3"]["counterfactual_prelock_policy_selection"], scores, {})
    assert rows == before and attention == audit.attention_sets(rows) and selected == audit.pair_selections(pairs)
    assert selected[0]["control"]["candidate_ids"] == ["1", "2"]


def test_missing_actuals_are_not_zero_imputed_and_cpt_scored_once():
    c = candidate("1", list("abcdef"), "a")
    assert audit.score_candidate(c, {p: 10 for p in "abcde"}) is None
    assert audit.score_candidate(c, {p: 10 for p in "abcdef"}) == 65


def test_duplicate_or_missing_canonical_identity_rejected():
    c = candidate("1", list("abcdee"), "a")
    with pytest.raises(ValueError):
        audit.signature(c["players"])


@pytest.mark.parametrize("created,cutoff,expected", [
    ("2026-10-04T22:08:00-04:00", "2026-10-04T18:07:00-04:00", False),
    ("2026-10-04T20:20:00-04:00", "2026-10-04T18:07:00-04:00", False),
    ("2026-10-04T19:00:00-04:00", "2026-10-04T18:07:00-04:00", True),
    ("2026-10-04T19:00:00", "2026-10-04T18:07:00-04:00", False),
    ("2026-10-04T17:00:00-04:00", "2026-10-04T18:07:00-04:00", False)])
def test_cutoff_alone_does_not_make_late_generation_safe(created, cutoff, expected):
    assert audit.chronology_safe(created, cutoff, "2026-10-04T20:20:00-04:00") is expected


def test_field_ties_use_competition_rank_and_percentile_interval():
    metric = audit.field_metric(90, [100, 90, 90, 80])
    assert metric["competition_rank"] == 2
    assert metric["percentile_strictly_below"] == 25 and metric["percentile_at_or_below"] == 75


def test_infeasible_overlap_does_not_relax_cap():
    pair = audit.pair_features(candidate("1", list("abcdef"), "a"), candidate("2", list("abcdeg"), "b"))
    choices, costs = audit.pair_selections([pair])
    assert choices["C_shared_le4"] is None and choices["D_shared_le3"] is None
    assert costs["4"]["feasible_pair_count"] == 0


def test_frozen_historical_inputs_complete_without_outcomes():
    for packet_path, source_path in zip(audit.PACKETS, audit.SOURCES):
        packet, source = audit.read(packet_path), audit.read(source_path)
        candidates = audit.candidates_from_saved(packet, source)
        assert len(candidates) == packet["pool_summary"]["distinct_rosters"]
        assert sum(c["quality_eligibility"]["eligible"] for c in candidates) == packet["pool_summary"]["quality_eligible_distinct"]
        assert all(c["quality_eligibility"]["eligible"] == c["visible_in_ai_review_universe"] for c in candidates)


def test_saved_source_hash_poison_rejected():
    packet, source = audit.read(audit.PACKETS[2]), audit.read(audit.SOURCES[2])
    source["params"]["strategy_runtime"]["showdown_portfolio_policy"]["candidate_selection"]["ranked_metrics"][0]["mean"] = 999
    with pytest.raises(ValueError, match="unavailable|hash"):
        audit.candidates_from_saved(packet, source)


def test_verify_freeze_checks_code_and_evidence(tmp_path, monkeypatch):
    # A minimal manifest must fail before any labels could be opened.
    monkeypatch.setattr(audit, "OUT", tmp_path)
    audit.write(tmp_path / "prelock_policy_freeze.json", {"selection_code_sha256": "tampered", "policy_definitions_hash": audit.digest(audit.POLICIES)})
    with pytest.raises(ValueError, match="changed after freeze"):
        audit.verify_freeze()


def test_reporting_normalizes_dk_float32_noise_without_changing_selection():
    from scripts.report_showdown_selection_diversity import field_metric, normalized_field_scores
    result = field_metric(106.73, normalized_field_scores([100,106.729996,106.74]))
    assert result["competition_rank"] == 2
    assert result["percentile_strictly_below"] == pytest.approx(100/3)


def test_actual_results_reconcile_and_all_selection_ids_match_freeze():
    path = audit.ROOT / "SHOWDOWN_SELECTION_REGRET_AND_PORTFOLIO_DIVERSITY_AUDIT.json"
    if not path.exists():
        pytest.skip("Run frozen audit evaluation first")
    result = audit.read(path)
    from scripts.replay_saved_showdown_selection_diversity import verify_saved_replay
    frozen = verify_saved_replay()
    for slate, original in zip(result["slates"], frozen["slates"]):
        assert slate["counts"] == original["counts"]
        for name,p in slate["attention_policy_results"].items():
            assert p["visible_candidate_ids"] == original["attention_policies"][name]["visible_candidate_ids"]
            assert p["counterfactual_prelock_policy_selection"] == original["attention_policies"][name]["counterfactual_prelock_policy_selection"]
        for name,p in slate["counterfactual_pair_policy_results"].items():
            assert p["prelock_pair"]["candidate_ids"] == original["counterfactual_pair_policies"][name]["candidate_ids"]
        assert slate["actual_recorded_ai_selection"]["selected_candidate_ids"] is None
        assert slate["stage_chain"]["best_considered"] is None
    assert result["slates"][2]["best_generated"]["best_actual"] == 120.84
    assert result["slates"][2]["historical_deterministic_selection"]["best_actual"] == 89.54
    assert not result["slates"][1]["attention_policy_results"]
    assert not result["slates"][1]["counterfactual_pair_policy_results"]


def test_pair_evaluation_keeps_prelock_features_and_correct_identity_order():
    import gzip
    path = audit.ROOT / "SHOWDOWN_SELECTION_REGRET_AND_PORTFOLIO_DIVERSITY_AUDIT.json"
    if not path.exists():
        pytest.skip("Run frozen audit evaluation first")
    for s in audit.read(path)["slates"]:
        with gzip.open(audit.ROOT / s["pair_artifact"],"rt") as f:
            before = json.load(f)
        evaluated_path = s.get("evaluated_pair_artifact")
        if not evaluated_path:
            pytest.skip("Run reporting enrichment first")
        with gzip.open(audit.ROOT / evaluated_path,"rt") as f:
            after = json.load(f)
        assert len(before) == len(after) == s["pair_count"]
        by_id = {c["candidate_id"]:c for c in s["candidates"]}
        for original,evaluated in zip(before,after):
            assert all(evaluated[k] == v for k,v in original.items())
            assert sorted(evaluated["lineup_feature_order_candidate_ids"]) == original["candidate_ids"]
            assert evaluated["means"] == [by_id[cid]["metrics"]["projected_mean"] for cid in evaluated["lineup_feature_order_candidate_ids"]]
            assert evaluated["unique_players_across_pair"] == 12-evaluated["shared_player_count"]


def test_week5_entered_pair_distinguishes_generated_from_selected_and_run_linked():
    result = audit.read(audit.ROOT / "SHOWDOWN_SELECTION_REGRET_AND_PORTFOLIO_DIVERSITY_AUDIT.json")
    if "actual_two_entry_portfolio_prelock_diagnostic" not in result["slates"][2]:
        pytest.skip("Run reporting enrichment first")
    slate = result["slates"][2]
    pair = slate["actual_two_entry_portfolio_prelock_diagnostic"]
    assert pair["different_captain"] and pair["primary_thesis_different"]
    assert pair["shared_player_count"] == 5 and pair["unique_players_across_pair"] == 7
    assert pair["team_split_different"] and not pair["qb_structure_different"]
    generated = {c["candidate_id"] for c in slate["candidates"]}
    assert set(pair["candidate_ids"]) <= generated
    selected = set(slate["historical_deterministic_selected_ids"])
    assert sum(cid in selected for cid in pair["candidate_ids"]) == 1
    assert any(e["candidate_id_if_generated"] in generated and e["linked_optimizer_run_id"] is None for e in slate["entry_execution"]["entries"])
    for policy in slate["counterfactual_pair_policy_results"].values():
        assert set(policy["prelock_pair"]["candidate_ids"]) <= generated


def test_field_context_stays_postgame_and_explicitly_counts_missing_salary():
    result = audit.read(audit.ROOT / "SHOWDOWN_SELECTION_REGRET_AND_PORTFOLIO_DIVERSITY_AUDIT.json")
    if "field_construction_context" not in result["slates"][2]:
        pytest.skip("Run reporting enrichment first")
    for s in result["slates"]:
        for field in s["field_construction_context"].values():
            assert field["status"] == "postgame_descriptive_only"
            for band in field["bands"].values():
                assert sum(band["team_split_frequencies"].values()) == band["identity_complete_entries"]
                assert sum(band["captain_frequencies"].values()) == band["identity_complete_entries"]
                assert band["salary_left"]["scoreable_count"] <= band["identity_complete_entries"]


def test_offline_verifier_uses_frozen_annotations_and_preserves_drift_guard(monkeypatch):
    from scripts.replay_saved_showdown_selection_diversity import verify_saved_replay
    file_hash = audit.file_hash
    def drift_hash(path):
        return "new-live-classifier" if str(path).endswith("backend/app/product_services/ai_showdown_packet.py") else file_hash(path)
    monkeypatch.setattr(audit,"file_hash",drift_hash)
    with pytest.raises(ValueError,match="Annotation code changed"):
        audit.verify_freeze()
    assert verify_saved_replay()["policy_definitions"] == audit.POLICIES


def test_offline_verifier_rejects_modified_frozen_decisions(monkeypatch):
    from scripts.replay_saved_showdown_selection_diversity import verify_saved_replay
    file_hash = audit.file_hash
    def drift_hash(path):
        return "changed-after-actuals" if str(path).endswith("prelock_policy_freeze.json") else file_hash(path)
    monkeypatch.setattr(audit,"file_hash",drift_hash)
    with pytest.raises(ValueError,match="after first outcome"):
        verify_saved_replay()
