"""Packet contract and chronology tests using saved Week 4 reference evidence."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.product_services.ai_showdown_packet import (
    _classify, _game, _players, _similarity, build_packet, render_markdown,
    validate_manual_selection,
)


ROOT = Path(__file__).resolve().parents[4]


def saved(name: str) -> dict:
    path = ROOT / "artifacts/showdown_scenario_selection/reference" / f"{name}-week4.json"
    if not path.exists(): pytest.skip("Historical reference artifact is not installed")
    value = json.loads(path.read_text())
    value.update(season=2026, week=4, slate=name.upper())
    return value


def test_thursday_frozen_packet_contract_and_determinism() -> None:
    source = saved("thursday")
    a = build_packet(source, generated_at="2026-10-01T20:00:00+00:00")
    b = build_packet(source, generated_at="2026-10-02T20:00:00+00:00")
    assert a["contract_id"] == "ai_showdown_selection_packet_v1"
    assert a["evidence_hash"] == b["evidence_hash"]
    assert a["pool_summary"]["candidate_variants"] == 149
    assert a["pool_summary"]["distinct_rosters"] == 117
    assert len(a["finalists"]) == 20
    assert len({c["candidate_id"] for c in a["finalists"]}) == 20
    assert all(c["inclusion_reasons"] for c in a["finalists"])
    assert len(a["similarity"]) == 190
    assert "Summed marginal P90 proxy" in render_markdown(a)
    assert "actual_points" not in json.dumps(a)
    schema = json.loads((ROOT / "docs/product/ai_showdown_selection_packet_v1.schema.json").read_text())
    assert schema["$id"] == a["contract_id"]
    assert set(schema["required"]) <= set(a)


def test_sunday_reference_is_after_kickoff() -> None:
    with pytest.raises(ValueError, match="at or after kickoff"):
        build_packet(saved("sunday"))


def test_sunday_structure_fixture_without_export() -> None:
    source = saved("sunday")
    cutoff = datetime.fromisoformat(source["data_cutoff_at"])
    game = _game(source["results"][0], cutoff)
    lookup = {p["player_id"]: p for p in source["player_pool"]["rows"]}
    candidate = next(r["captain_family_coverage_report"]["ranked_metrics"] for lineup in source["results"]
                     for r in lineup if r.get("captain_family_coverage_report"))[0]
    players = _players(candidate, lookup, cutoff)
    construction = _classify(players, game, candidate["salary"], None)
    assert len(players) == 6
    assert construction["captain_player_id"] == candidate["captain_player_id"]
    assert construction["team_split"]


@pytest.mark.parametrize("scope", ["candidate", "player"])
def test_postgame_fields_rejected(scope: str) -> None:
    source = saved("thursday")
    candidate = next(r["captain_family_coverage_report"]["ranked_metrics"] for lineup in source["results"]
                     for r in lineup if r.get("captain_family_coverage_report"))[0]
    target = candidate if scope == "candidate" else candidate["players"][0]
    target["actual_points"] = 9999
    with pytest.raises(ValueError, match="postgame"):
        build_packet(source)


def test_future_selected_evidence_rejected() -> None:
    source = saved("thursday")
    source["results"][0][0]["market_observed_at"] = "2026-10-02T00:00:00+00:00"
    with pytest.raises(ValueError, match="after the run cutoff"):
        build_packet(source)


def test_future_scenario_market_rejected() -> None:
    source = saved("thursday")
    report = next(r["captain_family_coverage_report"] for lineup in source["results"]
                  for r in lineup if r.get("captain_family_coverage_report"))
    report["scenario_definitions"][0]["market_observed_at"] = "2026-10-02T00:00:00+00:00"
    with pytest.raises(ValueError, match="scenario market"):
        build_packet(source)


def test_irrelevant_postgame_text_does_not_enter_packet() -> None:
    source = saved("thursday")
    before = build_packet(source)["evidence_hash"]
    source["results"][0][0]["postgame_commentary"] = "Future result"
    packet = build_packet(source)
    assert "Future result" not in json.dumps(packet)
    assert packet["evidence_hash"] == before


def test_candidate_input_order_does_not_change_finalists() -> None:
    source = saved("thursday")
    first = build_packet(source)
    report = next(r["captain_family_coverage_report"] for lineup in source["results"]
                  for r in lineup if r.get("captain_family_coverage_report"))
    report["ranked_metrics"].reverse()
    second = build_packet(source)
    assert {c["candidate_id"] for c in first["finalists"]} == {c["candidate_id"] for c in second["finalists"]}


def test_manual_selection_contract() -> None:
    packet = build_packet(saved("thursday"), requested_entries=2)
    selection = {"contract_id": "ai_showdown_manual_selection_v1", "packet_hash": packet["evidence_hash"],
                 "selected_at": "2026-10-01T20:00:00+00:00",
                 "selected_candidate_ids": [c["candidate_id"] for c in packet["finalists"][:2]],
                 "model_name": "manual", "reasoning": "Two complementary constructions"}
    assert validate_manual_selection(selection, packet)["timing_status"] == "prelock"
    selection["selected_at"] = "2026-10-02T02:00:00+00:00"
    assert validate_manual_selection(selection, packet)["timing_status"] == "retrospective"
    with pytest.raises(ValueError, match="Unknown fields"):
        validate_manual_selection({**selection, "actual_points": 100}, packet)
    selection["selected_candidate_ids"][1] = selection["selected_candidate_ids"][0]
    with pytest.raises(ValueError, match="unique"):
        validate_manual_selection(selection, packet)


def test_classification_and_similarity_rules() -> None:
    game = {"favorite": "AAA", "underdog": "BBB"}
    players = [{"player_id": f"a{i}", "name": f"A{i}", "slot": "CPT" if i == 0 else "FLEX",
                "team": "AAA" if i < 4 else "BBB", "position": "RB" if i == 0 else "QB" if i == 1 or i == 4 else "WR",
                "salary": 7000, "injury_status": None, "role_uncertain": False} for i in range(6)]
    c = _classify(players, game, 49500, None)
    assert c["team_split"] == "4-2 AAA"
    assert c["qb_structure"] == "both_qbs"
    assert c["salary_bucket"] == "101-500"
    assert c["scenario_reason_codes"]["favorite_rush_win"] == ["team_majority", "team_rb_captain"]
    assert c["ownership_bucket"] is None
    a = {"candidate_id": "a", "players": players, "construction": c}
    b = {"candidate_id": "b", "players": deepcopy(players), "construction": c}
    assert _similarity(a, b)["thesis_similarity"] == "HIGH"


def test_request_bounds() -> None:
    source = saved("thursday")
    with pytest.raises(ValueError, match="15–30"): build_packet(source, finalist_count=14)
    with pytest.raises(ValueError, match="2–5"): build_packet(source, requested_entries=1)


def test_download_api_uses_saved_run_without_solver() -> None:
    from backend.app.api.product_routes import download_ai_showdown_packet
    from fastapi import HTTPException

    value = saved("thursday")
    job = SimpleNamespace(job_id=value["job_id"], status=value["status"], season=2026, week=4,
                          slate="THURSDAY_NIGHT", strategy=value["strategy"],
                          contest_format=value["contest_format"], created_at=value["created_at"],
                          data_cutoff_at=value["data_cutoff_at"], projection_run_id=value["projection_run_id"],
                          params={}, results=value["results"])
    class FakeService:
        def get_job(self, job_id: str):
            assert job_id == job.job_id
            return job
    response = download_ai_showdown_packet(job.job_id, format="json", finalists=20,
                                           entries=None, service=FakeService())
    assert response.media_type == "application/json"
    assert json.loads(response.body)["pool_summary"]["distinct_rosters"] == 117
    assert len(json.loads(response.body)["ai_review_universe"]["candidates"]) == 93
    markdown = download_ai_showdown_packet(job.job_id, format="md", finalists=20,
                                           entries=None, service=FakeService())
    assert "# AI Review Universe" in markdown.body.decode()
    late = saved("sunday")
    job.job_id = late["job_id"]
    job.results = late["results"]
    job.created_at = late["created_at"]
    job.data_cutoff_at = late["data_cutoff_at"]
    job.projection_run_id = late["projection_run_id"]
    with pytest.raises(HTTPException) as error:
        download_ai_showdown_packet(job.job_id, format="md", finalists=20, entries=5, service=FakeService())
    assert error.value.status_code == 422


def synthetic_candidate(rank: int, mean: float = 100, ceiling: float = 200, *, thesis: int = 0) -> dict:
    players = [{"player_id": f"p{i}", "name": str(i), "slot": "CPT" if i == 0 else "FLEX",
                "team": "AAA" if i < 3 else "BBB", "position": "QB" if i in {0, 3} else "WR",
                "salary": 7000, "injury_status": None, "role_uncertain": False} for i in range(6)]
    x = _classify(players, {"favorite": "AAA", "underdog": "BBB"}, 49000, None)
    if thesis:
        x['primary_thesis_signature'] += f'|synthetic-{thesis}'
        x['captain_script_combination'] += f'|synthetic-{thesis}'
    return {"candidate_id": f"candidate-{rank:03}", "players": players, "construction": x,
            "metrics": {"selector_rank": rank, "objective_score": 300-rank, "projected_mean": mean,
                        "summed_marginal_p90_proxy": ceiling, "projection_rank": rank, "ceiling_proxy_rank": rank},
            "market_compatibility": "MEDIUM"}


def test_quality_or_rule_and_configurable_safety_floor() -> None:
    from backend.app.product_services.ai_showdown_packet import _quality
    rows = [synthetic_candidate(1), synthetic_candidate(50, 82, 196), synthetic_candidate(51, 97, 164),
            synthetic_candidate(52, 79, 200), synthetic_candidate(53, 81, 162), synthetic_candidate(2, 81, 162)]
    _quality(rows)
    assert [r['quality_eligibility']['eligible'] for r in rows] == [True, True, True, False, False, True]
    _quality(rows, {'minimum_fraction': .85})
    assert not rows[1]['quality_eligibility']['eligible']
    with pytest.raises(ValueError, match='Quality fractions'):
        _quality(rows, {'minimum_fraction': .95, 'strong_fraction': .90})
    rows[0]['metrics']['projected_mean'] = None
    _quality(rows)
    assert not rows[0]['quality_eligibility']['eligible']


def test_independent_quality_seeds_and_deep_structural_outliers() -> None:
    from backend.app.product_services.ai_showdown_packet import _finalists, _quality, coverage_metrics
    rows = [synthetic_candidate(i, 95, 190) for i in range(1, 61)]
    # High on one metric and acceptable on the other; no postgame labels.
    rows[39]['metrics']['projected_mean'] = 110
    rows[39]['metrics']['summed_marginal_p90_proxy'] = 165
    rows[49]['metrics']['projected_mean'] = 90
    rows[49]['metrics']['summed_marginal_p90_proxy'] = 205
    for i in range(20, 35):
        x = rows[i]['construction']
        x['primary_thesis_signature'] += f'|synthetic-{i}'
        x['captain_script_combination'] += f'|synthetic-{i}'
    _quality(rows)
    finalists = _finalists(rows, 20)
    assert len(finalists) == 20
    assert all(rows[i]['candidate_id'] in {r['candidate_id'] for r in finalists} for i in (0, 1, 2, 39, 49))
    assert 'mean_preservation' in next(r for r in finalists if r['candidate_id'] == rows[39]['candidate_id'])['inclusion_reasons']
    assert 'ceiling_preservation' in next(r for r in finalists if r['candidate_id'] == rows[49]['candidate_id'])['inclusion_reasons']
    assert sum(r['inclusion_origin'] == 'outlier_preservation' for r in finalists) == 3
    coverage = coverage_metrics(finalists)
    assert sum(coverage['inclusion_origin_counts'].values()) == len(finalists)
    assert sum(coverage['market_compatibility_counts'].values()) == len(finalists)


def test_small_pool_underfill_never_forces_bad_bucket() -> None:
    from backend.app.product_services.ai_showdown_packet import _finalists, _quality
    rows = [synthetic_candidate(1), synthetic_candidate(50, 50, 100, thesis=1)]
    _quality(rows)
    result = _finalists(rows, 20)
    assert [r['candidate_id'] for r in result] == [rows[0]['candidate_id']]


def test_theses_separate_construction_and_captain_scripts() -> None:
    a = synthetic_candidate(1)
    x = a['construction']
    assert 'non_qb_captain' not in x['football_scenarios']
    assert x['primary_thesis_signature'] == 'competitive_shootout|QB|3-3|both_qbs'
    assert len(x['thesis_signatures']) == 2
    players = deepcopy(a['players'])
    players[0]['position'] = 'WR'
    players[1]['position'] = 'QB'
    y = _classify(players, {'favorite': 'AAA', 'underdog': 'BBB'}, 49000, 60)
    assert y['primary_thesis_signature'] == 'competitive_shootout|WR|3-3|both_qbs'
    assert 'non_qb_captain' in y['construction_attributes']
    assert 'ownership_bucket:contrarian' in y['construction_attributes']
    assert 'non_qb_captain' not in y['scenario_tags']
    assert set(y['thesis_reason_codes']) == set(y['thesis_signatures'])


def test_similarity_preserves_meaningful_differences_with_shared_players() -> None:
    a = synthetic_candidate(1)
    for change in ('captain', 'scenario', 'qb'):
        b = deepcopy(a)
        b['candidate_id'] = change
        x = b['construction']
        if change == 'captain': x['captain_player_id'] = 'different-captain'
        if change == 'scenario': x['primary_football_scenario'] = 'low_scoring_game'
        if change == 'qb': x['qb_structure'] = 'favorite_qb_only'
        pair = _similarity(a, b)
        assert pair['player_overlap_count'] == 6
        assert pair['thesis_similarity'] != 'HIGH'
    identical = _similarity(a, deepcopy(a))
    assert identical['thesis_similarity'] == 'HIGH'
    assert identical['thesis_similarity_score'] == 1


def test_baseline_market_precedes_conditioned_selected_row_market() -> None:
    from backend.app.product_services.ai_showdown_packet import _market_compatibility
    packet = build_packet(saved('thursday'))
    assert packet['game']['market_by_team']['PIT']['spread'] == -2.5
    assert packet['game']['market_basis'] == 'saved_baseline'
    market = {'favorite': 'AAA', 'underdog': 'BBB', 'total': 38.5,
              'market_by_team': {'AAA': {'spread': -14, 'implied_total': 26.25}}}
    x = synthetic_candidate(1)['construction']
    assert _market_compatibility(x, market)['market_compatibility'] == 'LOW'
    x['primary_football_scenario'] = 'favorite_dominant_win'
    assert _market_compatibility(x, market)['market_compatibility'] == 'HIGH'
    x['primary_football_scenario'] = 'underdog_upset'
    assert _market_compatibility(x, market)['market_compatibility'] == 'LOW'
    assert _market_compatibility(x, {})['market_compatibility_reason_codes'] == ['saved_baseline_market_incomplete']


def test_retrospective_path_preserves_real_clock_and_source_guards() -> None:
    from backend.app.product_services.ai_showdown_packet import build_retrospective_packet
    source = saved('sunday')
    packet = build_retrospective_packet(source)
    assert packet['run']['created_at'] == source['created_at']
    assert packet['run']['timing_status'] == 'retrospective_unverified_generation'
    assert 'RETROSPECTIVE DIAGNOSTIC' in render_markdown(packet)
    source['results'][0][0]['market_observed_at'] = '2026-10-05T00:30:00+00:00'
    with pytest.raises(ValueError, match='after the run cutoff'):
        build_retrospective_packet(source)


def test_reordering_preserves_decisions_but_changes_raw_evidence_hash() -> None:
    source = saved('thursday')
    first = build_packet(source)
    for lineup in source['results']:
        for row in lineup:
            report = row.get('captain_family_coverage_report')
            if report: report['ranked_metrics'].reverse()
    second = build_packet(source)
    assert second['finalists'] == first['finalists']
    assert second['pool_summary']['finalist_coverage'] == first['pool_summary']['finalist_coverage']
    assert second['run']['candidate_pool_hash'] != first['run']['candidate_pool_hash']


def test_v2_schema_required_extensions_match_packet_and_keep_v1_properties() -> None:
    schema = json.loads((ROOT / 'docs/product/ai_showdown_selection_packet_v1.schema.json').read_text())
    packet = build_packet(saved('thursday'))
    extension = schema['allOf'][0]['then']['properties']
    assert set(extension['run']['required']) <= packet['run'].keys()
    assert set(extension['pool_summary']['required']) <= packet['pool_summary'].keys()
    for row in packet['finalists']:
        contract = extension['finalists']['items']
        assert set(contract['required']) <= row.keys()
        assert set(contract['properties']['construction']['required']) <= row['construction'].keys()
    assert all(set(extension['similarity']['items']['required']) <= pair.keys() for pair in packet['similarity'])
    assert schema['properties']['contract_id']['const'] == 'ai_showdown_selection_packet_v1'


def universe_source() -> dict:
    """Saved prelock pool with opposite captain sides and incomplete ownership."""
    candidates = []
    for rank in range(1, 41):
        captain_index = 0 if rank % 2 else 3
        players = [{"player_id": f"p{i}" if i < 5 else f"flex-{rank}",
                    "name": "Captain | Alpha\nQB" if i == 0 else f"Player {i}" if i < 5 else f"Flex {rank}",
                    "slot": "CPT" if i == captain_index else "FLEX", "team": "AAA" if i < 3 else "BBB",
                    "position": "QB" if i in {0, 3} else "WR", "salary": 10500 if i == captain_index else 7000,
                    "projection": 15, "p90": 30} for i in range(6)]
        candidates.append({"rank": rank, "players": players, "salary": 45500,
                           "mean": 50 if rank == 40 else 100, "p90": 100 if rank == 40 else 200,
                           "selector": 300 - rank, "lineup_ownership": 80 + rank,
                           "ownership_complete": rank % 3 == 0})
    selected = deepcopy(candidates[0]["players"])
    for row in selected:
        row.update(game_id="AAA@BBB 10/08/2026 08:15PM ET", player_team=row["team"],
                   team_spread_line=-3 if row["team"] == "AAA" else 3,
                   game_total_line=50, market_observed_at="2026-10-08T18:00:00+00:00")
    selected[0]["captain_family_coverage_report"] = {"ranked_metrics": candidates}
    return {"job_id": "universe-test", "status": "completed", "contest_format": "showdown",
            "season": 2026, "week": 5, "slate": "THURSDAY_NIGHT", "projection_run_id": "saved-projections",
            "created_at": "2026-10-08T20:00:00+00:00", "data_cutoff_at": "2026-10-08T19:00:00+00:00",
            "results": [selected]}


def test_review_universe_has_all_eligible_distinct_rosters_and_full_rows() -> None:
    source = universe_source()
    before = deepcopy(source)
    # A second variant of a roster does not add a universe row.
    pool = source["results"][0][0]["captain_family_coverage_report"]["ranked_metrics"]
    duplicate = deepcopy(pool[0])
    duplicate["rank"] = 100
    pool.append(duplicate)
    packet = build_packet(source, allow_incomplete_evidence=True)
    universe = packet["ai_review_universe"]
    eligible_ids = {c["candidate_id"] for c in packet["pool_summary"]["candidate_assessments"] if c["quality_eligibility"]["eligible"]}
    rows = universe["candidates"]
    assert len(rows) == len(eligible_ids) == 39
    assert {c["candidate_id"] for c in rows} == eligible_ids
    assert universe["summary"]["generated_distinct_candidates"] == 40
    assert universe["summary"]["excluded_by_quality_count"] == 1
    assert packet["pool_summary"]["candidate_variants"] == 41
    finalists = {c["candidate_id"]: c for c in packet["finalists"]}
    assert len(finalists) == universe["summary"]["deterministic_finalists"] == 20
    for row in rows:
        assert len(row["flex_player_names"]) == 5
        assert all(not name.startswith("flex-") for name in row["flex_player_names"])
        assert row["construction"]["captain_player_name"]
        assert row["construction"]["salary_remaining"] == 4500
        assert row["is_deterministic_finalist"] == (row["candidate_id"] in finalists)
        assert row["deterministic_finalist_inclusion_origin"] == finalists.get(row["candidate_id"], {}).get("inclusion_origin")
        if row["metrics"]["selector_rank"] % 3:
            assert row["metrics"]["projected_total_ownership"] is None
    pool.pop()
    assert source == before
    assert len(packet["similarity"]) == 190


def test_review_family_membership_order_and_summaries() -> None:
    packet = build_packet(universe_source(), allow_incomplete_evidence=True)
    universe = packet["ai_review_universe"]
    rows = universe["candidates"]
    fields = {"primary_thesis": "primary_thesis_signature", "captain_script_combination": "captain_script_combination",
              "football_scenario": "football_scenarios", "captain_archetype": "captain_archetype",
              "team_split": "normalized_team_split", "qb_structure": "qb_structure"}
    assert set(universe["family_indexes"]) == set(fields)
    assert len(universe["family_indexes"]["primary_thesis"]) == 1
    assert set(universe["family_indexes"]["captain_script_combination"]) == {"favorite|QB|3-3|both_qbs", "underdog|QB|3-3|both_qbs"}
    assert all(c["metrics"]["selector_rank"] <= 39 for c in rows)
    for dimension, field in fields.items():
        groups = universe["family_indexes"][dimension]
        assert universe["summary"]["family_counts"][dimension] == len(groups)
        for name, ids in groups.items():
            members = [c for c in rows if name in c["construction"][field]] if dimension == "football_scenario" else [c for c in rows if name == c["construction"][field]]
            assert ids == [c["candidate_id"] for c in members]
            assert len(ids) == len(set(ids))
            summary = universe["family_summaries"][dimension][name]
            assert summary["top_candidate_ids"] == ids[:3]
            assert summary["candidate_count"] == len(ids)
            assert sum(summary["captain_side_distribution"].values()) == len(ids)
            assert sum(summary["market_compatibility_distribution"].values()) == len(ids)
            assert summary["deterministic_finalist_count"] == sum(c["is_deterministic_finalist"] for c in members)
            own = [c["metrics"]["projected_total_ownership"] for c in members if c["metrics"]["projected_total_ownership"] is not None]
            assert summary["projected_ownership_range"] == {"min": min(own), "max": max(own), "available_count": len(own), "unavailable_count": len(ids) - len(own)}
            assert summary["projected_mean_range"]["min"] == summary["projected_mean_range"]["max"] == 100
            assert summary["ceiling_proxy_range"]["min"] == summary["ceiling_proxy_range"]["max"] == 200
            assert summary["objective_range"]["min"] == min(c["metrics"]["objective_score"] for c in members)
            assert summary["distinct_team_splits"] == ["3-3"]
            assert summary["risk_flag_counts"] == {}


def test_review_universe_is_stable_and_included_in_frozen_hash() -> None:
    from backend.app.product_services.ai_showdown_packet import digest
    source = universe_source()
    first = build_packet(source, allow_incomplete_evidence=True, generated_at="2026-10-08T21:00:00+00:00")
    repeated = build_packet(source, allow_incomplete_evidence=True, generated_at="2026-10-08T22:00:00+00:00")
    assert first["evidence_hash"] == repeated["evidence_hash"]
    source["results"][0][0]["captain_family_coverage_report"]["ranked_metrics"].reverse()
    reversed_packet = build_packet(source, allow_incomplete_evidence=True)
    assert first["ai_review_universe"] == reversed_packet["ai_review_universe"]
    assert first["finalists"] == reversed_packet["finalists"]
    first["ai_review_universe"]["candidates"].pop()
    assert digest({k: v for k, v in first.items() if k not in {"evidence_hash", "generated_at"}}) != first["evidence_hash"]


def test_review_universe_markdown_is_compact_and_escapes_thesis_pipes() -> None:
    packet = build_packet(universe_source(), allow_incomplete_evidence=True)
    md = render_markdown(packet)
    section = md.split("# AI Review Universe\n", 1)[1].split("## Deterministic finalists", 1)[0]
    assert "## Universe summary" in section
    assert "## Candidate family index" in section
    table = section.split("## Quality-eligible candidate table\n", 1)[1]
    candidate_lines = [line for line in table.splitlines() if line.startswith("| universe-test:")]
    assert len(candidate_lines) == 39
    assert "### `universe-test:" not in section
    assert "competitive_shootout\\|QB\\|3-3\\|both_qbs" in section
    assert "Captain \\| Alpha QB" in table
    assert "Select 5 entries from the complete AI Review Universe" in md
    assert "deterministic finalists are a reference/control" in md
    assert "Summed marginal P90 is a ceiling proxy" in section


def test_review_universe_order_is_prelock_quality_without_market_screen() -> None:
    source = universe_source()
    candidates = source["results"][0][0]["captain_family_coverage_report"]["ranked_metrics"]
    # A deep selector-ranked candidate leads on prelock multidimensional quality.
    candidates[34]["mean"] = 105
    candidates[34]["p90"] = 210
    for row in source["results"][0]:
        row["game_total_line"] = 40
    packet = build_packet(source, allow_incomplete_evidence=True)
    rows = packet["ai_review_universe"]["candidates"]
    assert rows[0]["metrics"]["selector_rank"] == 35
    assert len(rows) == 39
    assert all(row["market_compatibility"] == "LOW" for row in rows)
    assert all(ids[0] == rows[0]["candidate_id"] for groups in packet["ai_review_universe"]["family_indexes"].values()
               for ids in groups.values() if rows[0]["candidate_id"] in ids)


def test_review_universe_underfill_keeps_unavailable_ownership_and_risk_counts() -> None:
    source = universe_source()
    pool = source["results"][0][0]["captain_family_coverage_report"]["ranked_metrics"]
    pool[:] = [pool[0], pool[-1]]
    # Saved risk evidence is descriptive and does not exclude an eligible row.
    source["results"][0][1]["pregame_role_uncertain"] = True
    packet = build_packet(source, allow_incomplete_evidence=True)
    universe = packet["ai_review_universe"]
    assert len(universe["candidates"]) == len(packet["finalists"]) == 1
    assert universe["summary"]["excluded_by_quality_count"] == 1
    for groups in universe["family_summaries"].values():
        for group in groups.values():
            assert group["projected_ownership_range"] == {"min": None, "max": None, "available_count": 0, "unavailable_count": 1}
            assert group["risk_flag_counts"] == {"uncertain_role": 1}
    assert "| — |" in render_markdown(packet)


def test_review_universe_requires_saved_human_names() -> None:
    source = universe_source()
    pool = source["results"][0][0]["captain_family_coverage_report"]["ranked_metrics"]
    del pool[30]["players"][-1]["name"]
    with pytest.raises(ValueError, match="saved human-readable names"):
        build_packet(source, allow_incomplete_evidence=True)


def test_missing_baseline_market_is_explicitly_unavailable_and_exportable() -> None:
    source = universe_source()
    source["results"][0][0]["captain_family_coverage_report"]["scenario_definitions"] = [{
        "scenario_id": "baseline", "market_spread_by_team": {}, "market_implied_by_team": {},
        "market_total": None, "market_source": None, "market_observed_at": None}]
    packet = build_packet(source, allow_incomplete_evidence=True)
    game = packet["game"]
    assert game["market_by_team"] == {}  # Do not use selected/conditioned quote fallback.
    assert game["favorite"] is game["underdog"] is game["total"] is None
    assert game["market_unavailable_reason"] == "saved_baseline_market_missing"
    assert len(packet["ai_review_universe"]["candidates"]) == 39
    for row in packet["ai_review_universe"]["candidates"]:
        assert row["market_compatibility"] == "MEDIUM"
        assert row["market_compatibility_reason_codes"] == ["saved_baseline_market_incomplete"]
        assert row["construction"]["captain_side"] in {"AAA", "BBB"}
        assert not any(tag.startswith(("favorite_", "underdog_")) for tag in row["construction"]["football_scenarios"])
    assert "**Market unavailable:**" in render_markdown(packet)


@pytest.mark.parametrize("observed", [None, "2026-10-08T23:00:00+00:00"])
def test_existing_baseline_quote_still_requires_cutoff_safe_timestamp(observed: str | None) -> None:
    source = universe_source()
    source["results"][0][0]["captain_family_coverage_report"]["scenario_definitions"] = [{
        "scenario_id": "baseline", "market_spread_by_team": {"AAA": -3, "BBB": 3},
        "market_total": 50, "market_observed_at": observed}]
    with pytest.raises(ValueError, match="baseline scenario market is missing or after"):
        build_packet(source, allow_incomplete_evidence=True)


def test_review_universe_schema_contract_is_additive_and_covers_full_rows() -> None:
    schema = json.loads((ROOT / "docs/product/ai_showdown_selection_packet_v1.schema.json").read_text())
    assert "ai_review_universe" not in schema["required"]  # Archived v1/v2 packets remain readable.
    contract = schema["properties"]["ai_review_universe"]
    universe = build_packet(universe_source(), allow_incomplete_evidence=True)["ai_review_universe"]
    assert set(contract["required"]) <= universe.keys()
    assert universe["contract_id"] == contract["properties"]["contract_id"]["const"]
    assert set(contract["properties"]["summary"]["required"]) <= universe["summary"].keys()
    row_contract = schema["$defs"]["review_candidate"]
    for row in universe["candidates"]:
        assert set(row_contract["required"]) <= row.keys()
        assert set(row_contract["properties"]["metrics"]["required"]) <= row["metrics"].keys()
        assert set(row_contract["properties"]["construction"]["required"]) <= row["construction"].keys()
        assert row["quality_eligibility"]["eligible"] is True
    for groups in universe["family_summaries"].values():
        for group in groups.values():
            assert set(schema["$defs"]["review_family_summary"]["required"]) <= group.keys()


def test_review_universe_preserves_existing_finalist_audit_and_frozen_hash_guard() -> None:
    from backend.app.product_services.ai_showdown_finalist_audit import audit_finalist_set
    from backend.app.product_services.ai_showdown_packet import digest
    source = universe_source()
    packet = build_packet(source, allow_incomplete_evidence=True)
    pool = source["results"][0][0]["captain_family_coverage_report"]["ranked_metrics"]
    actuals = {p["player_id"]: 10 for c in pool for p in c["players"]}
    current_audit = audit_finalist_set(packet, source, actuals)
    legacy = deepcopy(packet)
    del legacy["ai_review_universe"]
    legacy["evidence_hash"] = digest({k: v for k, v in legacy.items() if k not in {"evidence_hash", "generated_at"}})
    legacy_audit = audit_finalist_set(legacy, source, actuals)
    assert {k: v for k, v in current_audit.items() if k != "packet_hash"} == {
        k: v for k, v in legacy_audit.items() if k != "packet_hash"}
    packet["ai_review_universe"]["family_indexes"]["qb_structure"]["both_qbs"].pop()
    with pytest.raises(ValueError, match="Frozen packet hash"):
        audit_finalist_set(packet, source, actuals)


def test_manual_selection_accepts_nonfinalist_universe_candidate_and_keeps_legacy_rules() -> None:
    packet = build_packet(universe_source(), requested_entries=2, allow_incomplete_evidence=True)
    finalists = {c["candidate_id"] for c in packet["finalists"]}
    nonfinalist = next(c["candidate_id"] for c in packet["ai_review_universe"]["candidates"] if c["candidate_id"] not in finalists)
    selection = {"contract_id": "ai_showdown_manual_selection_v1", "packet_hash": packet["evidence_hash"],
                 "selected_at": "2026-10-08T21:00:00+00:00", "selected_candidate_ids": [nonfinalist, packet["finalists"][0]["candidate_id"]]}
    assert validate_manual_selection(selection, packet)["timing_status"] == "prelock"
    ineligible = next(c["candidate_id"] for c in packet["pool_summary"]["candidate_assessments"] if not c["quality_eligibility"]["eligible"])
    for excluded in (ineligible, "not-in-saved-pool"):
        selection["selected_candidate_ids"][0] = excluded
        with pytest.raises(ValueError, match="outside the packet review universe"):
            validate_manual_selection(selection, packet)
    selection["selected_candidate_ids"][0] = nonfinalist
    del packet["ai_review_universe"]
    with pytest.raises(ValueError, match="legacy packets: finalists"):
        validate_manual_selection(selection, packet)
    selection["selected_candidate_ids"] = [c["candidate_id"] for c in packet["finalists"][:2]]
    assert validate_manual_selection(selection, packet)["timing_status"] == "prelock"


@pytest.mark.parametrize("name,eligible_count", [("thursday", 93), ("sunday", 110)])
def test_historical_review_universes_cover_all_eligible_candidates(name: str, eligible_count: int) -> None:
    from backend.app.product_services.ai_showdown_packet import build_retrospective_packet
    builder = build_packet if name == "thursday" else build_retrospective_packet
    packet = builder(saved(name))
    universe = packet["ai_review_universe"]
    assert len(universe["candidates"]) == eligible_count
    assert {c["candidate_id"] for c in universe["candidates"]} == {
        c["candidate_id"] for c in packet["pool_summary"]["candidate_assessments"] if c["quality_eligibility"]["eligible"]}
    assert len(packet["finalists"]) == 20
    assert "actual_points" not in json.dumps(universe)
    assert universe["summary"]["deterministic_finalists"] == 20


@pytest.mark.parametrize("requested_count", [1, 3])
def test_active_captain_packet_preserves_one_recommendation_and_proxy_policy(requested_count):
    from backend.app.product_services.ai_showdown_packet import _saved_candidates
    from backend.app.product_services.single_lineup import select_single_lineup, CAPTAIN_SINGLE_LINEUP_STRATEGY_ID
    from backend.app.product_services.optimizer_effectiveness import candidate_snapshot
    source = saved('thursday')  # Frozen pregame evidence; no realized outcomes are consumed.
    original, _ = _saved_candidates(source)
    lookup = {p['player_id']: p for p in source['player_pool']['rows']}
    candidates = []
    for candidate in original:
        players = _players(candidate, lookup, datetime.fromisoformat(source['data_cutoff_at']))
        candidates.append([{**p, 'roster_position': p['slot'], 'player_team': p['team']} for p in players])
    selected, report = select_single_lineup(candidates, strategy=CAPTAIN_SINGLE_LINEUP_STRATEGY_ID, controls={"num_lineups": requested_count})
    # Preserve the original game/source metadata needed by the prelock guard.
    game_metadata = source['results'][0][0]
    assert len(selected) == requested_count
    for p in (p for lineup in selected for p in lineup):
        for key in ('game_id', 'game_total_line', 'team_spread_line', 'market_observed_at', 'market_source'):
            p[key] = game_metadata.get(key)
    source.update(strategy=CAPTAIN_SINGLE_LINEUP_STRATEGY_ID, objective='cash', results=selected,
                  params={'num_lineups': requested_count, 'strategy_runtime': {'single_lineup': report}})
    source['params']['strategy_runtime']['candidate_pool_manifest'] = candidate_snapshot(source['params'], 'showdown')
    packet = build_packet(source)
    assert packet['pool_summary']['requested_entries'] == 1
    assert len(packet['control_selection']) == 1
    assert packet['single_lineup_objective']['cash_probability'] is None
    assert packet['single_lineup_objective']['contract_id'] == report['contract_id']
    assert 'proxy' in render_markdown(packet).lower()
    with pytest.raises(ValueError, match='exactly one'):
        build_packet(source, requested_entries=2)
