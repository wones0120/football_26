"""Pregame Classic experiment controls; no Week 3 outcome inputs."""

from datetime import UTC, datetime, timedelta

import pytest

from backend.app.product_services.classic_prospective import (
    classify_availability, core_classes, digest_payload, evaluate_postgame,
    freeze_classic_run_input, freeze_solver_snapshot, high_p90_low_exposure,
    guard_prelock_persistence, resolve_overrides, resolve_risk_policy, risk_exposure,
    run_prospective_experiment, slate_kickoff_evidence_pool,
    validate_classic_run_input, validate_solver_snapshot, viable_qbs,
)
from backend.app.product_services.classic_small_field import _select_global
from backend.app.product_services.gpp_optimizer import Player, SlateAnalysis, _build_lineup, build_large_gpp_config


NOW = datetime(2026, 10, 4, 16, tzinfo=UTC)


def _player(pid: str, position: str = "WR", *, mean: float = 12,
            p90: float = 22, ownership: float = 10) -> Player:
    return Player(player_id=pid, name=pid, team="AAA", opponent="BBB",
                  position=position, salary=5000, projection=mean, ceiling=p90,
                  ownership=ownership, game_id="AAA-BBB", game_total=50,
                  team_total=26, spread=-2)


def _candidate(rank: int, qb: str, extras: list[str], *, score: float,
               mean: float = 120) -> dict:
    ids = [qb, *extras]
    return {"rank": rank, "player_ids": ids,
            "roster": [{"player_id": pid, "name": pid} for pid in ids],
            "qb": {"player_id": qb, "name": qb},
            "stack": {"partner_count": 1, "bring_back_count": 0, "type": "QB+1"},
            "pass_catchers": {"flex_position": "WR"}, "primary_game": "AAA–BBB",
            "games_represented": ["AAA-BBB"], "mean": mean, "p90": mean + 90,
            "ownership_sum": 100, "leverage_sum": 1, "objective_score": score}


def test_frozen_solver_snapshot_is_complete_hashed_and_pregame_only() -> None:
    player = _player("qb", "QB")
    config = build_large_gpp_config(SlateAnalysis(1, 0, []), ownership_available=True)
    row = {"player_id": "qb", "name": "qb", "player_team": "AAA", "position": "QB",
           "salary": 5000, "projection": 12, "p90": 22, "ownership": 10,
           "salary_source_row_id": "salary-7", "salary_ingest_run_id": "ingest-1",
           "player_status": "Q", "injury_observed_at": NOW - timedelta(hours=1),
           "practice_participation": "LIMITED"}
    frozen = freeze_solver_snapshot(
        run_id="run-1", season=2026, week=4, slate="SUNDAY_MAIN",
        created_at=NOW, cutoff=NOW, projection_run_id="projection-1",
        strategy="classic_small_field_gpp", players=[player], pool_rows=[row],
        options={"starting_qb_ids": ["qb"], "seed": None}, resolved_config=config,
        policy_ids={"stack": "stack-v1"})
    validate_solver_snapshot(frozen)
    assert frozen["payload"]["metadata"]["optimizer_run_id"] == "run-1"
    assert frozen["payload"]["pool_rows"][0]["salary_source_row_id"] == "salary-7"
    assert frozen["payload"]["players"][0]["ceiling"] == 22
    frozen["payload"]["players"][0]["projection"] = 99
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_solver_snapshot(frozen)


def test_three_arm_freeze_requires_database_write_before_saved_kickoff() -> None:
    experiment = {"status": "prelock_frozen", "production": {},
                  "shadow_generation": {}, "shadow_portfolio": {}, "sha256": "digest"}
    kickoff = (NOW + timedelta(minutes=1)).isoformat()
    assert guard_prelock_persistence(experiment, kickoff, NOW, "snapshot") == experiment
    blocked = guard_prelock_persistence(experiment, kickoff, NOW + timedelta(minutes=1), "snapshot")
    assert blocked == {"status": "not_frozen_prelock",
                       "reason": "database_persistence_at_or_after_saved_kickoff",
                       "frozen_snapshot_sha256": "snapshot"}
    assert guard_prelock_persistence(experiment, None, NOW, "snapshot")["status"] == "not_frozen_prelock"


def test_prelock_gate_uses_first_game_in_full_slate_pool() -> None:
    from backend.app.product_services.optimizer_effectiveness import chronological_validation

    pool = slate_kickoff_evidence_pool([
        {"game_id": "AAA@BBB 10/04/2026 01:00PM ET"},
        {"game_id": "CCC@DDD 10/04/2026 04:25PM ET"},
    ])
    result = chronological_validation(
        {"data_cutoff_at": datetime(2026, 10, 4, 15, tzinfo=UTC),
         "optimizer_created_at": datetime(2026, 10, 4, 18, tzinfo=UTC)}, pool)
    assert result["status"] == "unavailable"
    assert result["first_saved_kickoff_at"] == "2026-10-04T13:00:00-04:00"


@pytest.mark.parametrize(("status", "practice", "workload", "bucket"), [
    ("OUT", None, None, "out"),
    ("DOUBTFUL", None, None, "doubtful"),
    ("QUESTIONABLE", "LIMITED", None, "questionable_elevated"),
    ("QUESTIONABLE", "FULL", None, "questionable_elevated"),
    ("QUESTIONABLE", "FULL", "NO_RESTRICTION", "questionable_full_role"),
    ("ACTIVE", None, None, "normal"),
])
def test_availability_classification_uses_saved_pregame_evidence(
    status: str, practice: str | None, workload: str | None, bucket: str,
) -> None:
    risk = classify_availability({"player_status": status,
                                  "injury_observed_at": NOW - timedelta(hours=1),
                                  "practice_participation": practice,
                                  "practice_observed_at": NOW - timedelta(hours=2) if workload else None,
                                  "expected_workload_status": workload,
                                  "expected_workload_observed_at": NOW - timedelta(hours=1) if workload else None}, NOW)
    assert risk["bucket"] == bucket


def test_availability_fails_closed_on_late_evidence_and_requires_reasoned_override() -> None:
    with pytest.raises(ValueError, match="later than"):
        classify_availability({"player_status": "QUESTIONABLE",
                               "injury_observed_at": NOW + timedelta(minutes=1),
                               "practice_participation": "FULL",
                               "expected_workload_status": "FULL"}, NOW)
    assert classify_availability({"player_status": "Q", "practice_participation": "FULL",
                                  "expected_workload_status": "FULL"}, NOW)["bucket"] == "questionable_elevated"
    with pytest.raises(ValueError, match="reason"):
        resolve_overrides({"player-1": {"allow_doubtful": True}}, {"player-1"})
    assert resolve_overrides({"player-1": {"allow_doubtful": True, "reason": "User accepts risk"}},
                             {"player-1"})["player-1"]["allow_doubtful"]


def test_risk_portfolio_caps_and_budget_are_hard_constraints() -> None:
    shared = [f"shared-{i}" for i in range(6)]
    rows = [
        _candidate(1, "qb-a", [*shared, "risky", "x"], score=10),
        _candidate(2, "qb-b", [*shared, "risky", "y"], score=9),
        _candidate(3, "qb-c", [*shared, "safe", "z"], score=8),
        _candidate(4, "qb-d", [*shared, "safe-2", "zz"], score=7),
        _candidate(5, "qb-e", [*shared, "safe-3", "zzz"], score=6),
    ]
    # Two risky lineups would be 40% of five, but the 20% risk budget binds.
    selected = _select_global(rows, 5, 1, set(), {"risky": .4}, {},
                              max_lineups_with_any_player_ids=({"risky"}, .2))
    assert selected == []  # all five cannot satisfy the independent budget
    selected = _select_global(rows, 3, 1, set(), {"risky": .4}, {},
                              max_lineups_with_any_player_ids=({"risky"}, 1 / 3))
    assert len(selected) == 3
    assert sum("risky" in rows[i]["player_ids"] for i in selected) <= 1
    locked_risk = _select_global(rows, 3, 1, {"risky"}, {"risky": .4}, {},
                                 enforce_maximum_for_locked_ids={"risky"})
    assert len(locked_risk) == 3
    assert sum("risky" in rows[i]["player_ids"] for i in locked_risk) <= 1


def test_structural_inputs_and_high_p90_diagnostic_are_pregame_only() -> None:
    players = [_player("qb-a", "QB", mean=20, p90=32),
               _player("qb-b", "QB", mean=19, p90=34),
               _player("wr-a", p90=40), _player("wr-b", p90=18)]
    risks = {p.player_id: {"bucket": "normal"} for p in players}
    policy = resolve_risk_policy()
    assert {p.player_id for p in viable_qbs(players, risks, policy, {"qb-a", "qb-b"})} == {"qb-a", "qb-b"}
    assert core_classes(players, risks)["wr-a"] in {"elite_high_confidence", "ordinary_core", "low_owned_value"}
    candidates = [{"player_ids": ["qb-a", "wr-b"]}] * 20
    flags = high_p90_low_exposure(players, candidates, risks, policy)
    assert {row["player_id"] for row in flags} >= {"qb-b", "wr-a"}
    exposure = risk_exposure([{"player_ids": ["q1", "q2"]}, {"player_ids": ["q1"]}],
                             {"q1": {"bucket": "questionable_elevated"},
                              "q2": {"bucket": "questionable_full_role"}})
    assert exposure["pct_with_at_least"] == {"1": 100, "2": 50, "3": 0}


def test_prospective_contract_separates_production_generation_and_overlap_shadow() -> None:
    players = [_player("qb-a", "QB"), _player("qb-b", "QB"), _player("qb-c", "QB"),
               *[_player(f"p-{i}") for i in range(24)]]
    source = [{"player_id": p.player_id, "player_status": "Q" if p.player_id == "p-0" else "ACTIVE",
               "injury_observed_at": NOW - timedelta(hours=1)} for p in players]
    config = build_large_gpp_config(SlateAnalysis(1, 0, []), ownership_available=True)
    snapshot = freeze_solver_snapshot(
        run_id="run-2", season=2026, week=4, slate="SUNDAY_MAIN",
        created_at=NOW, cutoff=NOW, projection_run_id="projection-2",
        strategy="classic_small_field_gpp", players=players, pool_rows=source,
        options={"starting_qb_ids": ["qb-a", "qb-b", "qb-c"]}, resolved_config=config)
    candidates = [
        _candidate(1, "qb-a", ["p-0", *[f"p-{i}" for i in range(1, 8)]], score=10, mean=130),
        _candidate(2, "qb-b", [f"p-{i}" for i in range(8, 16)], score=9, mean=125),
        _candidate(3, "qb-c", [f"p-{i}" for i in range(16, 24)], score=8, mean=120),
    ]
    experiment = run_prospective_experiment(
        snapshot=snapshot, production_candidates=candidates,
        production_selected_ranks=[1], players=players, source_rows=source,
        config=config, selected_count=1, max_exposure=1,
        locked_ids=set(), maximums={}, minimums={}, ownership_available=True,
        enforce_single_te=False, avoid_dst_opponents=False, solver_backend="bundled",
        risk_config={"min_qb_family_candidates": 0, "high_p90_low_exposure": 0,
                     "non_elite_candidate_cap": 1.0})
    assert experiment["production"]["selected_ranks"] == [1]
    assert experiment["shadow_portfolio"]["candidate_manifest_sha256"] == experiment["production"]["candidate_manifest_sha256"]
    assert experiment["shadow_portfolio"]["constraints"]["max_lineup_overlap"] == 6
    assert experiment["shadow_generation"]["candidate_manifest_sha256"] != experiment["production"]["candidate_manifest_sha256"]
    assert experiment["shadow_generation"]["pregame"]["risk"]["by_player"]["p-0"]["count"] == 0
    assert experiment["availability_risk"]["players"][0]["bucket"] == "questionable_elevated"
    assert experiment["postgame"]["status"] == "pending_actuals"
    actuals = {p.player_id: float(index) for index, p in enumerate(players, 1)}
    outcome = evaluate_postgame(experiment, actuals,
                                {"contest-1": {"top_20_percent": 90.0,
                                               "top_1_percent": 160.0}})
    assert outcome["status"] == "evaluated"
    assert outcome["arms"]["production"]["scoreable_count"] == 3
    assert outcome["arms"]["shadow_generation"]["scoreable_count"] == 2
    assert outcome["arms"]["shadow_portfolio"]["candidate_count"] == 3
    assert experiment["postgame"] == {"status": "pending_actuals"}
    experiment["production"]["selected_ranks"] = [2]
    with pytest.raises(ValueError, match="hash mismatch"):
        evaluate_postgame(experiment, actuals, {})


def test_snapshot_excludes_postgame_columns_and_has_deterministic_digest() -> None:
    player = _player("qb", "QB")
    config = build_large_gpp_config(SlateAnalysis(1, 0, []), ownership_available=True)
    kwargs = dict(run_id="run", season=2026, week=4, slate="SUNDAY_MAIN",
                  created_at=NOW, cutoff=NOW, projection_run_id="pr", strategy="classic_small_field_gpp",
                  players=[player], pool_rows=[{"player_id": "qb", "actual_points": 99}],
                  options={}, resolved_config=config)
    left = freeze_solver_snapshot(**kwargs)
    right = freeze_solver_snapshot(**kwargs)
    assert left["sha256"] == right["sha256"]
    assert digest_payload(left["payload"]) == left["sha256"]
    assert "actual_points" not in left["payload"]["pool_rows"][0]
    generic = freeze_classic_run_input(
        run_id="cash-run", season=2026, week=4, slate="SUNDAY_MAIN",
        created_at=NOW, cutoff=NOW, projection_run_id="pr", strategy="classic_cash",
        rows=[{"player_id": "qb", "projection": 12, "actual_points": 99}],
        params={"salary_cap": 50000, "strategy_runtime": {"later_report": {"actual_points": 99}}})
    validate_classic_run_input(generic)
    assert "actual_points" not in generic["payload"]["final_solver_rows"][0]
    assert "strategy_runtime" not in generic["payload"]["parameters"]


def test_shadow_discovers_bringback_and_no_bringback_qb_families(monkeypatch) -> None:
    from backend.app.product_services import classic_prospective, classic_small_field

    players = [_player("qb-a", "QB"), *[_player(f"p-{i}") for i in range(30)]]
    source = [{"player_id": p.player_id, "player_status": "ACTIVE"} for p in players]
    config = build_large_gpp_config(SlateAnalysis(1, 0, []), ownership_available=True)
    snapshot = freeze_solver_snapshot(
        run_id="coverage", season=2026, week=4, slate="SUNDAY_MAIN",
        created_at=NOW, cutoff=NOW, projection_run_id="pr", strategy="classic_small_field_gpp",
        players=players, pool_rows=source, options={"starting_qb_ids": ["qb-a"]},
        resolved_config=config)
    original = [_candidate(1, "qb-a", [f"p-{i}" for i in range(8)], score=10, mean=130)]
    requested = []
    current = {"family": None}
    def fake_solve(_players, _config, _exposure, _blocked, **kwargs):
        family = (kwargs["exact_pass_catchers"], kwargs["exact_bring_backs"])
        current["family"] = family
        requested.append(family)
        offset = {(1, 1): 8, (2, 0): 16, (2, 1): 22}[family]
        return [0, *range(offset + 1, offset + 9)]
    def fake_describe(roster, **_kwargs):
        family = current["family"]
        row = _candidate(0, "qb-a", [p.player_id for p in roster[1:]], score=9.5, mean=126)
        row["stack"].update(partner_count=family[0], bring_back_count=family[1])
        return row
    monkeypatch.setattr(classic_prospective, "_build_lineup", fake_solve)
    monkeypatch.setattr(classic_small_field, "describe_candidate", fake_describe)
    experiment = run_prospective_experiment(
        snapshot=snapshot, production_candidates=original, production_selected_ranks=[1],
        players=players, source_rows=source, config=config, selected_count=1,
        max_exposure=1, locked_ids=set(), maximums={}, minimums={},
        ownership_available=True, enforce_single_te=False, avoid_dst_opponents=False,
        solver_backend="bundled", risk_config={"min_qb_family_candidates": 1,
                                                "high_p90_low_exposure": 0,
                                                "non_elite_candidate_cap": 1})
    assert (1, 1) in requested and (2, 0) in requested and (2, 1) in requested
    assert len(experiment["shadow_generation"]["structural_discovery"]) == 3
    assert all(row["status"] == "new" for row in experiment["shadow_generation"]["structural_discovery"])
    assert {row["family"] for row in experiment["shadow_generation"]["family_requirements"]} == {
        "QB+1+0back", "QB+1+1back", "QB+2+0back", "QB+2+1back"}


def test_solver_maximum_risk_group_prevents_two_risky_players() -> None:
    players = [_player("qb", "QB"), _player("rb-a", "RB"), _player("rb-b", "RB"),
               _player("wr-a"), _player("wr-b"), _player("wr-c"),
               _player("te", "TE"), _player("wr-d"), _player("dst", "DST")]
    for index, player in enumerate(players):
        player.team = "AAA" if index in {0, 1, 3, 4} else "BBB" if index in {2, 5} else "CCC"
        player.opponent = "BBB" if player.team == "AAA" else "AAA"
    config = build_large_gpp_config(SlateAnalysis(1, 0, []), ownership_available=False)
    assert _build_lineup(players, config, None, []) is not None
    assert _build_lineup(players, config, None, [],
                         maximum_player_groups=[({"rb-a", "rb-b"}, 1)]) is None


def test_out_and_doubtful_are_excluded_until_reasoned_doubtful_override() -> None:
    players = ([_player(f"qb-{i}", "QB") for i in range(3)] +
               [_player(f"p-{i}") for i in range(24)])
    source = [{"player_id": p.player_id,
               "player_status": "OUT" if p.player_id == "p-0" else
                                "DOUBTFUL" if p.player_id == "p-8" else "ACTIVE",
               "salary_source_observed_at": NOW - timedelta(hours=1)} for p in players]
    config = build_large_gpp_config(SlateAnalysis(1, 0, []), ownership_available=True)
    snapshot = freeze_solver_snapshot(
        run_id="risk-exclusion", season=2026, week=4, slate="SUNDAY_MAIN",
        created_at=NOW, cutoff=NOW, projection_run_id="pr", strategy="classic_small_field_gpp",
        players=players, pool_rows=source, options={"starting_qb_ids": ["qb-0", "qb-1", "qb-2"]},
        resolved_config=config)
    originals = [_candidate(i + 1, f"qb-{i}", [f"p-{j}" for j in range(i * 8, (i + 1) * 8)],
                            score=10 - i) for i in range(3)]
    common = dict(snapshot=snapshot, production_candidates=originals,
                  production_selected_ranks=[1], players=players, source_rows=source,
                  config=config, selected_count=1, max_exposure=1,
                  locked_ids=set(), maximums={}, minimums={}, ownership_available=True,
                  enforce_single_te=False, avoid_dst_opponents=False, solver_backend="bundled",
                  risk_config={"min_qb_family_candidates": 0, "high_p90_low_exposure": 0,
                               "non_elite_candidate_cap": 1})
    default = run_prospective_experiment(**common)
    assert default["shadow_generation"]["selected"][0]["qb"]["player_id"] == "qb-2"
    assert all("p-0" not in row["player_ids"] and "p-8" not in row["player_ids"]
               for row in default["shadow_generation"]["candidates"])
    reason_only = run_prospective_experiment(
        **common, override_config={"p-8": {"reason": "Record the user's concern"}})
    assert all("p-8" not in row["player_ids"]
               for row in reason_only["shadow_generation"]["candidates"])
    overridden = run_prospective_experiment(
        **common, override_config={"p-8": {"reason": "User accepts pre-lock doubtful risk",
                                               "allow_doubtful": True, "candidate_cap": 1,
                                               "selected_cap": 1}})
    assert all("p-0" not in row["player_ids"] for row in overridden["shadow_generation"]["candidates"])
    assert any("p-8" in row["player_ids"] for row in overridden["shadow_generation"]["candidates"])
