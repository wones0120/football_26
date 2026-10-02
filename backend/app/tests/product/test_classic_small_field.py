"""The diagnostic Classic strategy keeps legality and selection separate."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.app.product_services.cbc_solver import make_cbc_solver, resolve_cbc_backend
from backend.app.product_services.classic_small_field import (
    _admit_candidate_caps, _bring_back_evaluation, _concentration_rows, _football_sanity,
    _game_environment, _receiving_role, classic_entry_readiness,
    _role_projection_anomalies, _select_global, _solve_seed_shard,
    analyze_small_field, contest_reporting_snapshot,
    expand_candidate_discovery, portfolio_summary,
)
from backend.app.product_services.gpp_optimizer import (
    GPPOptimizerResult, Player, PortfolioStats, SlateAnalysis, StackRules, _build_lineup,
    build_large_gpp_config,
    tag_players,
)
from backend.app.product_services.optimizer import (
    CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID, OptimizerService,
    resolve_optimizer_strategy, validate_saved_salary_identity,
)


def test_market_label_requires_captured_evidence() -> None:
    qb = _player("QB", "AAA", "BBB", "QB", 5000, 20, 30)
    qb.game_total = 0.0
    qb.spread = 0.0
    qb.market_context_point_in_time_safe = True
    assert _game_environment(qb, [0.0])["label"] == "market environment unavailable"
    qb.game_total = 50.0
    qb.market_context_point_in_time_safe = False
    assert _game_environment(qb, [50.0])["label"] == "market environment unavailable"


def test_saved_salary_identity_checks_team_opponent_and_source_row() -> None:
    pool = [{"player_id": "p", "salary_source_row_id": 7, "player_team": "SF",
             "opponent_team": "DEN", "salary": 5000}]
    saved = [{"curated_salary_id": 7, "player_master_id": "p", "team": "SF",
              "opponent": "DEN", "salary": 5000}]
    assert validate_saved_salary_identity(pool, saved)["status"] == "PASS"
    assert validate_saved_salary_identity(pool, [{**saved[0], "opponent": "KC"}])["violations"][0]["reason"] == "salary_opponent_mismatch"


def test_candidate_admission_does_not_relax_questionable_or_core_caps() -> None:
    rows = [{"player_ids": ["risky", f"other-{i}"], "objective_score": 10 - i}
            for i in range(8)] + [{"player_ids": [f"safe-{i}"], "objective_score": 1}
                                  for i in range(2)]
    admitted, _, funnel = _admit_candidate_caps(rows, [[] for _ in rows],
                                                {"risky": .25}, {"risky"}, 10, 1)
    assert funnel["status"] == "CANDIDATE_POOL_UNDERFILLED"
    assert funnel["rejected_by_player_cap"] > 0
    assert funnel["duplicate"] == 0
    assert funnel["rejected_by_family_constraint"] == 0
    assert sum("risky" in row["player_ids"] for row in admitted) <= int(.25 * len(admitted))


def test_joint_admission_keeps_balanced_candidates_without_sequential_refill() -> None:
    rows = [
        {"player_ids": ["x", "y", "shared-1"], "objective_score": 10},
        {"player_ids": ["x", "y", "shared-2"], "objective_score": 9},
        {"player_ids": ["x", "z"], "objective_score": 8},
        {"player_ids": ["y", "w"], "objective_score": 7},
        {"player_ids": ["z", "w"], "objective_score": 6},
    ]
    admitted, _, funnel = _admit_candidate_caps(
        rows, [[] for _ in rows], {"x": .4, "y": .4}, set(), 5, 1,
    )
    assert len(admitted) == 3
    assert funnel["admission_method"] == "joint_max_count_then_selector_score"
    for player_id in ("x", "y"):
        assert sum(player_id in row["player_ids"] for row in admitted) <= int(.4 * len(admitted))
    assert {tuple(row["player_ids"]) for row in admitted} == {
        ("x", "z"), ("y", "w"), ("z", "w"),
    }
    repeated, _, _ = _admit_candidate_caps(
        rows, [[] for _ in rows], {"x": .4, "y": .4}, set(), 5, 1,
    )
    assert [row["player_ids"] for row in admitted] == [row["player_ids"] for row in repeated]


def test_parallel_seed_shard_honors_player_cap_and_keeps_legal_rosters() -> None:
    players = [
        _player("QB", "AAA", "BBB", "QB", 6000, 20, 30),
        _player("RB One", "CCC", "DDD", "RB", 5500, 18, 28),
        _player("RB Two", "CCC", "DDD", "RB", 5400, 16, 25),
        _player("RB Three", "DDD", "CCC", "RB", 5300, 15, 24),
        _player("RB Four", "BBB", "AAA", "RB", 4800, 12, 20),
        _player("WR Stack", "AAA", "BBB", "WR", 5200, 14, 23),
        _player("WR Two", "BBB", "AAA", "WR", 5000, 13, 22),
        _player("WR Three", "CCC", "DDD", "WR", 4800, 12, 21),
        _player("WR Four", "DDD", "CCC", "WR", 4700, 11, 20),
        _player("WR Five", "AAA", "BBB", "WR", 4600, 10, 19),
        _player("TE", "BBB", "AAA", "TE", 4000, 10, 18),
        _player("DST", "DDD", "CCC", "DST", 2500, 8, 12),
    ]
    config = build_large_gpp_config(
        SlateAnalysis(game_count=2, chalk_concentration=0, feature_games=[]),
        ownership_available=False,
    )
    tag_players(players, config.tag_thresholds)
    context = dict(players=players, config=config, enforce_single_te=False,
                   avoid_dst_opponents=False, solver_backend="bundled",
                   candidate_caps={players[1].player_id: .5},
                   elevated_ids=set(), max_elevated=0)
    first = _solve_seed_shard((0, 2, (players[0].player_id,), 1), context)
    second = _solve_seed_shard((0, 2, (players[0].player_id,), 1), context)
    assert first == second
    assert len(first["lineups"]) == 2
    assert sum(players[1].player_id in lineup for lineup in first["lineups"]) <= 1
    by_id = {player.player_id: player for player in players}
    for ids in first["lineups"]:
        lineup = [OptimizerService._gpp_player_to_dict(by_id[player_id]) for player_id in ids]
        assert OptimizerService._validate_classic_lineups(
            [lineup], requested_lineups=1, max_exposure=1.0,
            enforce_single_te=False, avoid_dst_opponents=False,
        )[0]


def test_entry_readiness_distinguishes_preview_blocker_and_ready() -> None:
    players = [_player(f"Player {i}", "AAA", "BBB", "QB" if i == 0 else "WR",
                       5000, 10, 20) for i in range(100)]
    for player in players:
        player.market_context_point_in_time_safe = True
    selected = [players[:9]]
    candidates = [{"player_ids": [p.player_id for p in selected[0]]} for _ in range(100)]
    source = {p.player_id: {"market_observed_at": "2026-09-29T10:00:00+00:00",
                            "ownership": p.ownership} for p in players}
    kwargs = dict(players=players, selected=selected, candidates=candidates, source=source,
                  salary_identity={"status": "PASS"}, production_funnel=None, controls=None,
                  first_kickoff_at="2026-10-04T17:00:00+00:00",
                  decision_at="2026-09-30T00:00:00+00:00", requested_count=1)
    ready = classic_entry_readiness(**kwargs)
    assert ready["status"] == "ENTRY_READY"
    assert ready["market_coverage"]["games"] == [{
        "game_id": "AAA-BBB", "player_count": 100, "source": None,
        "observed_at": "2026-09-29T10:00:00+00:00", "age_hours": 14.0,
        "status": "aging",
    }]
    players[0].market_context_point_in_time_safe = False
    assert classic_entry_readiness(**kwargs)["status"] == "DEVELOPMENT_PREVIEW"
    players[0].market_context_point_in_time_safe = True
    original_total = players[0].game_total
    players[0].game_total = 0.0
    assert classic_entry_readiness(**kwargs)["status"] == "BLOCKED"
    players[0].game_total = original_total
    stale = {pid: {**row, "market_observed_at": "2026-09-28T10:00:00+00:00"}
             for pid, row in source.items()}
    warning = classic_entry_readiness(**{**kwargs, "source": stale})
    assert warning["checks"]["Market/game environment"]["status"] == "WARNING"
    blocked = classic_entry_readiness(**{**kwargs, "source": stale,
                                        "market_stale_policy": "blocker"})
    assert blocked["checks"]["Market/game environment"]["status"] == "BLOCKER"


@pytest.mark.parametrize("position,approval", [("RB", True), ("WR", True),
                                                ("TE", True), ("DST", False)])
def test_full_skill_exposure_requires_approval_but_dst_does_not(position, approval):
    players = [_player(f"Player {i}", "AAA", "BBB", "WR", 5000, 10, 20)
               for i in range(100)]
    players[0].position = "QB"
    players[9].position = "QB"
    players[1].position = position
    for player in players:
        player.market_context_point_in_time_safe = True
    selected = [players[:9], [players[9], players[1], *players[10:17]]]
    candidates = [{"player_ids": [p.player_id for p in selected[0]]} for _ in range(100)]
    source = {p.player_id: {"market_observed_at": "2026-09-29T23:00:00+00:00",
                            "ownership": p.ownership} for p in players}
    result = classic_entry_readiness(
        players=players, selected=selected, candidates=candidates, source=source,
        salary_identity={"status": "PASS"}, production_funnel=None,
        controls={"core_classes": {p.player_id: "elite_high_confidence" for p in selected[0]},
                  "classifications": {}, "candidate_caps": {}, "overrides": {}, "locked_ids": []},
        first_kickoff_at="2026-10-04T17:00:00+00:00",
        decision_at="2026-09-30T00:00:00+00:00", requested_count=2,
    )
    assert result["market_coverage"]["sourced_games"] == 1
    assert bool(result["skill_approval_player_ids"]) is approval
    assert result["status"] == ("ENTRY_READY_WITH_APPROVAL_REQUIRED" if approval else "ENTRY_READY")


def test_invalid_optional_contest_context_does_not_invalidate_lineups() -> None:
    urls = [
        "https://www.draftkings.com/draft/contest/196088393",
        "https://www.draftkings.com/draft/contest/195921990",
    ]
    report = contest_reporting_snapshot(urls)
    assert report is not None
    assert report["source"] == "unavailable"
    assert "one DraftKings contest URL" in report["error"]


def test_solver_backend_requires_explicit_native_binary(monkeypatch) -> None:
    from backend.app.product_services import cbc_solver

    monkeypatch.setattr(cbc_solver.shutil, "which", lambda _: None)
    assert resolve_cbc_backend("auto") == "bundled"
    assert make_cbc_solver("bundled").path
    with pytest.raises(ValueError, match="no cbc executable"):
        resolve_cbc_backend("native")
    with pytest.raises(ValueError, match="no cbc executable"):
        make_cbc_solver("native")
    with pytest.raises(ValueError, match="must be bundled, native, or auto"):
        resolve_cbc_backend("other")


def _player(name: str, team: str, opponent: str, position: str, salary: int,
            mean: float, p90: float, ownership: float = 15.0) -> Player:
    return Player(
        player_id=name.lower().replace(" ", "-"), name=name, team=team,
        opponent=opponent, position=position, salary=salary,
        projection=mean, ceiling=p90, ownership=ownership,
        game_id="AAA-BBB" if team in {"AAA", "BBB"} else "CCC-DDD",
        game_total=50.0, spread=-2.0 if team == "AAA" else 2.0,
        team_total=26.0, optimizer_rushing_role_strength=0.7 if name == "QB One" else 0.0,
    )


def test_small_field_strategy_resolves_without_changing_showdown() -> None:
    resolved = resolve_optimizer_strategy(
        contest_format="classic", objective="gpp", strategy=CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID,
    )
    assert resolved["engine"] == "small_field_candidate_selector"
    assert resolved["contest_format"] == "classic"
    assert resolved["policy_alignment"]["status"] == "borrowed_unvalidated"
    assert resolved["policy_alignment"]["applied_profile_id"] == "classic_large_gpp_v1"


def test_portfolio_overlap_and_qb_paths_are_explicit_controls() -> None:
    core = [f"core-{i}" for i in range(6)]
    candidates = [
        {"player_ids": core + ["qb-a", "a", "b"], "qb": {"player_id": "qb-a"},
         "objective_score": 10.0},
        {"player_ids": core + ["qb-b", "c", "d"], "qb": {"player_id": "qb-b"},
         "objective_score": 9.9},
        {"player_ids": ["qb-c", *[f"other-{i}" for i in range(8)]],
         "qb": {"player_id": "qb-c"}, "objective_score": 9.8},
    ]
    default = _select_global(candidates, 2, 1.0, set(), {}, {})
    assert set(default) == {0, 1}
    diverse = _select_global(candidates, 2, 1.0, set(), {}, {},
                             max_lineup_overlap=5, distinct_qb_paths=True)
    assert set(diverse) == {0, 2}
    assert _select_global(candidates, 2, 1.0, set(), {}, {},
                          max_lineup_overlap=5, max_objective_loss=0.15) == []
    with pytest.raises(ValueError, match="max_lineup_overlap"):
        _select_global(candidates, 2, 1.0, set(), {}, {}, max_lineup_overlap=9)


def test_selection_requires_distinct_paths_and_can_include_alternative_family() -> None:
    rows = [
        {"player_ids": [f"p-{i}-{j}" for j in range(9)],
         "qb": {"player_id": "qb-a" if i < 2 else "qb-b" if i == 2 else "qb-c"},
         "stack": {"type": "QB+1" if i < 3 else "QB+1+bring-back"},
         "objective_score": 10 - i * .05} for i in range(4)
    ]
    selected = _select_global(rows, 3, 1.0, set(), {}, {},
                              minimum_qb_paths=3, minimum_stack_families=2)
    assert set(selected) == {0, 2, 3}


def test_selected_portfolio_report_exposes_overlap_and_core() -> None:
    rows = []
    for rank, qb_id in enumerate(("qb-a", "qb-b"), 1):
        roster = [{"player_id": "shared", "name": "Shared"},
                  {"player_id": qb_id, "name": qb_id}]
        rows.append({"rank": rank, "player_ids": [p["player_id"] for p in roster],
                     "roster": roster, "qb": {"name": qb_id},
                     "stack": {"type": "QB+1"}, "primary_game": f"game-{rank}",
                     "pass_catchers": {"flex_position": "WR"},
                     "mean": 100, "p90": 160, "ownership_sum": 25,
                     "leverage_sum": 1, "objective_score": 5,
                     "games_represented": [f"game-{rank}"]})
    report = portfolio_summary(rows, candidate_count=10,
                               constraints={"max_lineup_overlap": 1})
    assert report["overlap_matrix"] == [[2, 1], [1, 2]]
    assert report["core_players"] == ["Shared"]
    assert report["player_exposure"][0]["percent"] == 100
    assert len(report["primary_game_exposure"]) == 2
    assert report["lineups"][0]["unique_players"][0]["name"] == "qb-a"


def test_shadow_correlation_controls_are_neutral_by_default() -> None:
    players = [
        _player("QB", "AAA", "BBB", "QB", 6000, 20, 30),
        _player("RB One", "CCC", "DDD", "RB", 5600, 16, 25),
        _player("RB Two", "DDD", "CCC", "RB", 5400, 15, 24),
        _player("WR Stack", "AAA", "BBB", "WR", 5200, 14, 23),
        _player("WR Two", "CCC", "DDD", "WR", 5000, 13, 22),
        _player("WR Three", "DDD", "CCC", "WR", 4800, 12, 21),
        _player("TE", "CCC", "DDD", "TE", 4000, 10, 18),
        _player("Flex", "CCC", "DDD", "RB", 5000, 12, 20),
        _player("DST", "CCC", "DDD", "DST", 2500, 8, 12),
    ]
    config = build_large_gpp_config(
        SlateAnalysis(game_count=2, chalk_concentration=0, feature_games=[]),
        ownership_available=False,
    )
    rules = StackRules(**{**config.stack_rules.__dict__, "min_bring_backs": 0})
    default = _build_lineup(players, config, None, [], stack_rules=rules)
    explicit_neutral = _build_lineup(
        players, config, None, [], stack_rules=rules,
        correlation_rule_multipliers={}, extra_qb_pass_catcher_multiplier=1.0,
    )
    assert default == explicit_neutral


def test_diagnostic_minimum_player_group_respects_exact_legal_roster() -> None:
    players = [
        _player("QB", "AAA", "BBB", "QB", 6000, 20, 30),
        _player("RB One", "CCC", "DDD", "RB", 5600, 16, 25),
        _player("RB Two", "DDD", "CCC", "RB", 5400, 15, 24),
        _player("WR Stack", "AAA", "BBB", "WR", 5200, 14, 23),
        _player("WR Two", "CCC", "DDD", "WR", 5000, 13, 22),
        _player("WR Three", "DDD", "CCC", "WR", 4800, 12, 21),
        _player("TE", "CCC", "DDD", "TE", 4000, 10, 18),
        _player("Flex", "CCC", "DDD", "RB", 5000, 12, 20),
        _player("DST", "AAA", "BBB", "DST", 2500, 8, 12),
    ]
    config = build_large_gpp_config(
        SlateAnalysis(game_count=2, chalk_concentration=0, feature_games=[]),
        ownership_available=False,
    )
    rules = StackRules(**{**config.stack_rules.__dict__, "min_bring_backs": 0})
    group = {players[0].player_id, players[3].player_id}
    assert _build_lineup(players, config, None, [], stack_rules=rules,
                         minimum_player_groups=[(group, 2)]) is not None
    assert _build_lineup(players, config, None, [], stack_rules=rules,
                         minimum_player_groups=[(group, 3)]) is None


def test_classic_final_validation_rejects_player_facing_excluded_team() -> None:
    positions = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "WR", "DST"]
    teams = ["JAX", "BAL", "MIA", "CAR", "CHI", "ARI", "MIN", "HOU", "SF"]
    lineup = [
        {"player_id": str(index), "position": position, "player_team": team,
         "opponent_team": "DEN" if team == "JAX" else "OTHER", "salary": 5000}
        for index, (position, team) in enumerate(zip(positions, teams))
    ]
    valid, reason = OptimizerService._validate_classic_lineups(
        [lineup], requested_lineups=1, max_exposure=1.0,
        enforce_single_te=True, avoid_dst_opponents=False,
        excluded_opponent_teams={"DEN"},
    )
    assert not valid
    assert "faces excluded opponent DEN" in reason


def test_classic_final_validation_rejects_excluded_player_id() -> None:
    positions = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "WR", "DST"]
    lineup = [
        {
            "player_id": str(index),
            "position": position,
            "player_team": f"T{index}",
            "opponent_team": f"O{index}",
            "salary": 5000,
        }
        for index, position in enumerate(positions)
    ]
    valid, reason = OptimizerService._validate_classic_lineups(
        [lineup],
        requested_lineups=1,
        max_exposure=1.0,
        enforce_single_te=True,
        avoid_dst_opponents=False,
        excluded_player_ids={"1"},
    )
    assert not valid
    assert "contains excluded player(s): 1" in reason


def test_showdown_final_validation_rejects_player_facing_excluded_team() -> None:
    lineup = [
        {"player_id": str(index), "position": "WR", "roster_position": "CPT" if index == 0 else "FLEX",
         "player_team": "JAX" if index == 0 else "DEN",
         "opponent_team": "DEN" if index == 0 else "JAX", "salary": 5000}
        for index in range(6)
    ]
    valid, reason = OptimizerService._validate_showdown_lineups(
        [lineup], requested_lineups=1, max_exposure=1.0,
        excluded_opponent_teams={"DEN"},
    )
    assert not valid
    assert "faces excluded opponent DEN" in reason


def test_small_field_reuses_existing_low_opportunity_gate() -> None:
    pool = pd.DataFrame([
        {"player_id": "role", "position": "TE", "salary": 1500, "projection": 1.5,
         "p90": 5.0, "pregame_expected_routes": 15},
        {"player_id": "no-role", "position": "TE", "salary": 1500,
         "projection": 1.5, "p90": 5.0},
        {"player_id": "above-gate", "position": "TE", "salary": 1500,
         "projection": 2.5, "p90": 5.0},
    ])
    service = object.__new__(OptimizerService)
    included, reasons = service._select_strategy_candidates(
        pool, strategy=CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID, contest_type="tournament",
    )
    assert set(included["player_id"]) == {"role", "above-gate"}
    assert "low-opportunity" in reasons["no-role"][0]


def test_small_field_scores_legal_candidates_and_selects_globally() -> None:
    core = [
        _player("QB One", "AAA", "BBB", "QB", 6000, 20, 30),
        _player("RB One", "CCC", "DDD", "RB", 6000, 17, 25),
        _player("RB Two", "DDD", "CCC", "RB", 5600, 15, 22),
        _player("WR One", "AAA", "BBB", "WR", 6200, 17, 26),
        _player("WR Two", "BBB", "AAA", "WR", 5300, 14, 23),
        _player("WR Three", "CCC", "DDD", "WR", 5100, 12, 19),
        _player("TE One", "DDD", "CCC", "TE", 4000, 10, 16),
        _player("WR Flex", "AAA", "BBB", "WR", 5500, 13, 22),
        _player("DST One", "CCC", "DDD", "DST", 2500, 8, 12),
    ]
    alternate = [*core[:-2],
        _player("WR Alt", "BBB", "AAA", "WR", 5200, 11, 18, 4),
        _player("DST Alt", "DDD", "CCC", "DST", 2500, 7, 11)]
    analysis = SlateAnalysis(game_count=2, chalk_concentration=0, feature_games=[])
    config = build_large_gpp_config(analysis, ownership_available=True)
    result = GPPOptimizerResult(
        job_id="fixture", status="completed", message="fixture",
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        lineups=[alternate, core], config=config, analysis=analysis,
        portfolio=PortfolioStats(exposures={}, tag_counts={}, avg_total_ownership=0, stack_summary={}),
        iterations=1,
    )
    pool = [{"player_id": p.player_id, "gpp_player": p, "pregame_expected_carries": 6 if p.name == "QB One" else None,
             "offensive_role_importance": 0.55 if p.name == "RB One" else None,
             "offensive_role_class": "offensive centerpiece" if p.name == "RB One" else None}
        for p in {p.player_id: p for lineup in result.lineups for p in lineup}.values()]
    for lineup in result.lineups:
        valid, reason = OptimizerService._validate_classic_lineups(
            [[OptimizerService._gpp_player_to_dict(p) for p in lineup]],
            requested_lineups=1, max_exposure=1, enforce_single_te=True,
            avoid_dst_opponents=False,
        )
        assert valid, reason
    selected, report = analyze_small_field(
        result, pool_rows=pool, count=1, max_exposure=1,
        ownership_available=True, requested_candidate_count=100,
    )
    assert len(selected) == 1
    assert len(report["top_20"]) == 2
    assert report["candidate_count"] == report["serialized_candidate_count"] == 2
    assert len(report["all_candidates"]) == report["candidate_count"]
    assert report["generation_funnel"]["expanded_unique"] == 2
    assert report["generation_funnel"]["theoretical_legal_count"] is None
    assert report["pregame_coverage"]["diversity"]["unique_roster_count"] == 2
    first = report["top_20"][0]
    assert first["stack"]["type"] == "QB+2+bring-back"
    assert first["qb"]["label"] == "high-rushing-upside QB"
    assert abs(sum(first["components"].values()) - first["objective_score"]) < 1e-9
    assert first["components"]["ownership_chalk"] == 0
    assert first["relative_chalk"] is not None
    assert report["selected_ranks"] == [1]
    role_row = next(row for row in report["role_exposure"] if row["name"] == "RB One")
    assert role_row["importance"] == 0.55
    assert role_row["candidate_count"] == 2
    assert role_row["selected_count"] == 1
    sanity = first["football_sanity"]
    assert sanity["diagnostic_only"] is True
    assert "AAA passing" in sanity["script"]
    assert report["selected_football_sanity"] == [sanity]
    _, missing_report = analyze_small_field(
        result, pool_rows=pool, count=1, max_exposure=1,
        ownership_available=False, requested_candidate_count=100,
        ownership_evidence={"status": "unavailable", "covered_players": 0},
    )
    missing_candidate = missing_report["top_20"][0]
    assert missing_candidate["roster"][0]["ownership"] is None
    assert missing_candidate["ownership_sum"] is None
    assert missing_candidate["relative_chalk"] is None
    assert missing_candidate["stack"]["game_stack_ownership"] is None


def test_candidate_ownership_uses_lineup_coverage_without_changing_football_weights() -> None:
    core = [
        _player("QB", "AAA", "BBB", "QB", 6000, 20, 30),
        _player("RB1", "CCC", "DDD", "RB", 6000, 17, 25),
        _player("RB2", "DDD", "CCC", "RB", 5600, 15, 22),
        _player("WR1", "AAA", "BBB", "WR", 6200, 17, 26),
        _player("WR2", "BBB", "AAA", "WR", 5300, 14, 23),
        _player("WR3", "CCC", "DDD", "WR", 5100, 12, 19),
        _player("TE", "DDD", "CCC", "TE", 4000, 10, 16),
        _player("WR4", "AAA", "BBB", "WR", 5500, 13, 22),
        _player("DST", "CCC", "DDD", "DST", 2500, 8, 12),
    ]
    alternate = _player("Missing Alt", "AAA", "BBB", "WR", 5000, 12, 20)
    alternate.ownership = None
    analysis = SlateAnalysis(game_count=2, chalk_concentration=0, feature_games=[])
    complete_config = build_large_gpp_config(analysis, ownership_available=True,
                                              candidate_aware_ownership=True)
    partial_config = build_large_gpp_config(analysis, ownership_available=False,
                                             candidate_aware_ownership=True)
    assert complete_config.objective_weights == partial_config.objective_weights
    result = GPPOptimizerResult(
        job_id="coverage", status="completed", message="coverage",
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        lineups=[core, [*core[:-2], alternate, core[-1]]], config=partial_config,
        analysis=analysis,
        portfolio=PortfolioStats(exposures={}, tag_counts={}, avg_total_ownership=None,
                                 stack_summary={}), iterations=1,
    )
    pool = [{"player_id": p.player_id, "gpp_player": p}
            for p in {p.player_id: p for lineup in result.lineups for p in lineup}.values()]
    _, report = analyze_small_field(result, pool_rows=pool, count=1, max_exposure=1,
                                    ownership_available=False, candidate_aware_ownership=True)
    complete = next(row for row in report["all_candidates"] if alternate.player_id not in row["player_ids"])
    incomplete = next(row for row in report["all_candidates"] if alternate.player_id in row["player_ids"])
    assert complete["ownership_sum"] is not None
    assert complete["relative_chalk"] is not None
    assert complete["ownership_derived_terms"]["status"] == "available"
    assert incomplete["ownership_sum"] is None
    assert incomplete["relative_chalk"] is None
    assert incomplete["ownership_derived_terms"]["ownership_chalk"] is None
    assert incomplete["ownership_derived_terms"]["duplication"] is None
    assert incomplete["roster"][-2]["ownership"] is None
    assert "mean_within_4" in report["quality_guard_frontier"]


def test_expanded_discovery_injects_other_qb_family_and_deduplicates_ids() -> None:
    lineup = [
        _player("QB One", "AAA", "BBB", "QB", 6000, 20, 30),
        _player("RB1", "CCC", "DDD", "RB", 6000, 17, 25),
        _player("RB2", "DDD", "CCC", "RB", 5600, 15, 22),
        _player("WR1", "AAA", "BBB", "WR", 6200, 17, 26),
        _player("WR2", "BBB", "AAA", "WR", 5300, 14, 23),
        _player("WR3", "CCC", "DDD", "WR", 5100, 12, 19),
        _player("TE", "DDD", "CCC", "TE", 4000, 10, 16),
        _player("WR4", "AAA", "BBB", "WR", 5500, 13, 22),
        _player("DST", "CCC", "DDD", "DST", 2500, 8, 12),
    ]
    second_qb = _player("QB Two", "BBB", "AAA", "QB", 6100, 19, 29)
    players = [*lineup, second_qb]
    config = build_large_gpp_config(
        SlateAnalysis(game_count=2, chalk_concentration=0, feature_games=[]),
        ownership_available=False, candidate_aware_ownership=True)
    tag_players(players, config.tag_thresholds)
    discovered, audit = expand_candidate_discovery(
        SimpleNamespace(lineups=[lineup], config=config), players,
        enforce_single_te=True)
    keys = [tuple(sorted(player.player_id for player in row)) for row in discovered]
    assert len(keys) == len(set(keys))
    assert audit["sequential_count"] == 1
    assert any(row["source"] == f"qb_family:{second_qb.player_id}"
               and row["status"] == "legal" for row in audit["injections"])
    assert any(second_qb.player_id in key for key in keys)


def test_missing_receiving_usage_is_not_reported_as_measured_zero() -> None:
    missing = _receiving_role({})
    assert missing["strength"] is None
    assert missing["source"] == "unavailable"
    assert missing["receptions_mean_3"] is None
    measured = _receiving_role({"targets_mean_3": 0.0, "target_share_mean_3": 0.0})
    assert measured["strength"] == 0.0
    assert measured["source"] == "lagged_three_game"
    assert _receiving_role({"targets_mean_3": 4.0})["strength"] == 0.5


def test_football_sanity_surfaces_unsupported_cheap_role_and_central_omission() -> None:
    qb = _player("QB", "AAA", "BBB", "QB", 6000, 20, 30)
    cheap = _player("Cheap", "AAA", "BBB", "WR", 3000, 8, 14)
    central = _player("Central", "AAA", "BBB", "WR", 8000, 19, 28)
    candidate = {"player_ids": [qb.player_id, cheap.player_id],
                 "qb": {"team": "AAA"}, "stack": {"partner_count": 1, "bring_back_count": 0},
                 "game_environment": {"label": "high-total competitive"}}
    source = {
        qb.player_id: {}, cheap.player_id: {"opportunity_diagnostic": {"retention_reason": "fallback threshold"}},
        central.player_id: {"offensive_role_importance": 0.6,
                            "offensive_role_class": "offensive centerpiece",
                            "offensive_role_confidence": "high"},
    }
    from collections import Counter
    sanity = _football_sanity(candidate, players=[qb, cheap, central], source=source,
        candidate_counts=Counter({central.player_id: 2}), selected_counts=Counter(),
        candidate_total=10, selected_total=1)
    assert sanity["flags"] == ["cheap_role_evidence_missing", "role_evidence_missing"]
    assert sanity["missing_role_evidence"][0]["name"] == "Cheap"
    assert sanity["cheap_players"][0]["evidence_class"] == "insufficient_role_data"
    assert sanity["omitted_central_players"][0]["candidate_count"] == 2
    assert "No generated candidate" in sanity["omitted_central_players"][0]["explanation"]
    assert "position value rank" in sanity["omitted_central_players"][0]["salary_value_reason"]


def test_role_anomalies_cover_absent_offenses_and_low_exposure() -> None:
    from collections import Counter
    centerpiece = _player("Centerpiece", "AAA", "BBB", "RB", 7800, 12, 23)
    secondary = _player("Secondary", "AAA", "BBB", "WR", 4300, 13, 22)
    rows = _role_projection_anomalies(
        [centerpiece, secondary],
        {centerpiece.player_id: {"offensive_role_importance": 0.73,
                                  "offensive_role_class": "offensive centerpiece",
                                  "offensive_role_confidence": "high",
                                  "targets_mean_3": 3.0, "projected_targets": 2.5}},
        Counter(), 120,
    )
    assert rows[0]["name"] == "Centerpiece"
    assert rows[0]["candidate_count"] == 0
    assert rows[0]["team_role_rank"] == 1
    assert rows[0]["team_mean_rank"] == 2
    assert rows[0]["possible_drivers"]["allocated_volume_proxy"]["projected_targets"] == 2.5


def test_football_sanity_flags_measured_role_projection_disagreement() -> None:
    qb = _player("QB", "AAA", "BBB", "QB", 6000, 20, 30)
    central = _player("Central", "AAA", "BBB", "WR", 7000, 4, 7)
    others = [_player(f"Other {index}", "AAA", "BBB", "WR", 5000,
                      15 - index, 25 - index) for index in range(4)]
    source = {central.player_id: {"offensive_role_importance": 0.65,
        "offensive_role_class": "offensive centerpiece", "offensive_role_confidence": "high"}}
    source.update({p.player_id: {"offensive_role_importance": 0.1,
        "offensive_role_class": "rotational contributor", "offensive_role_confidence": "high"} for p in others})
    candidate = {"player_ids": [qb.player_id, central.player_id], "qb": {"team": "AAA"},
        "stack": {"partner_count": 1, "bring_back_count": 0},
        "game_environment": {"label": "other"}}
    from collections import Counter
    sanity = _football_sanity(candidate, players=[qb, central, *others], source=source,
        candidate_counts=Counter(), selected_counts=Counter(), candidate_total=1, selected_total=1)
    assert "role_projection_disagreement" in sanity["flags"]
    assert sanity["role_projection_disagreements"][0]["player_id"] == central.player_id


def test_rb_receiving_summary_preserves_missing_evidence() -> None:
    from backend.app.product_services.classic_small_field import describe_candidate
    lineup = [
        _player("QB", "AAA", "BBB", "QB", 6000, 20, 30),
        _player("RB One", "AAA", "BBB", "RB", 6000, 16, 25),
        _player("RB Two", "BBB", "AAA", "RB", 6000, 15, 24),
        *[_player(f"WR {i}", "AAA", "BBB", "WR", 5000, 10, 18) for i in range(4)],
        _player("TE", "BBB", "AAA", "TE", 4000, 9, 16),
        _player("DST", "AAA", "BBB", "DST", 3000, 7, 12),
    ]
    config = build_large_gpp_config(SlateAnalysis(game_count=1, chalk_concentration=0, feature_games=[]),
                                    ownership_available=False)
    row = describe_candidate(lineup, all_players=lineup, config=config,
        pool_by_id={p.player_id: {} for p in lineup}, ownership_available=False,
        game_totals=[50])
    assert all(rb["receiving_role_strength"] is None for rb in row["rbs"])


def test_team_reconciliation_keeps_attempt_forecasts_unavailable() -> None:
    from backend.app.product_services.classic_small_field import _team_reconciliation
    rb = _player("RB", "AAA", "BBB", "RB", 5000, 10, 18)
    wr = _player("WR", "AAA", "BBB", "WR", 5000, 10, 18)
    teams = _team_reconciliation([rb, wr], {
        rb.player_id: {"projected_carries": 12, "offensive_role_importance": .5,
                       "offensive_role_class": "primary option", "offensive_role_confidence": "high",
                       "team_carries_mean_3": 22},
        wr.player_id: {"projected_targets": 7, "team_targets_mean_3": 30},
    })
    assert teams[0]["expected_pass_attempts"] is None
    assert teams[0]["expected_rush_attempts"] is None
    assert teams[0]["lagged_team_targets_proxy"] == 30
    assert teams[0]["carry_distribution"][0]["name"] == "RB"
    assert teams[0]["missing_role_players"] == ["WR"]


def test_qb_family_diagnostic_reports_all_four_exact_families(monkeypatch) -> None:
    from backend.app.product_services import classic_small_field
    qb = _player("QB", "AAA", "BBB", "QB", 6000, 20, 30)
    players = [qb, _player("WR One", "AAA", "BBB", "WR", 5000, 10, 18),
               _player("WR Two", "AAA", "BBB", "WR", 5000, 10, 18),
               _player("Opponent", "BBB", "AAA", "WR", 5000, 10, 18)]
    monkeypatch.setattr(classic_small_field, "_build_lineup", lambda *args, **kwargs: None)
    config = build_large_gpp_config(SlateAnalysis(game_count=1, chalk_concentration=0, feature_games=[]),
                                    ownership_available=False)
    rows = classic_small_field._qb_family_coverage(players, config, {}, False, [], True, False)
    assert [row["family"] for row in rows[0]["families"]] == [
        "QB+1", "QB+2", "QB+1+bring-back", "QB+2+bring-back",
    ]


def test_concentration_counts_frequency_and_salary_pressure_without_forcing_exposure() -> None:
    qb = _player("QB One", "AAA", "BBB", "QB", 6000, 20, 30)
    receiver = _player("WR One", "CCC", "DDD", "WR", 5000, 12, 20)
    rows = [{"player_ids": [qb.player_id, receiver.player_id], "qb": {"team": "AAA", "player_id": qb.player_id},
             "roster": [{"team": "AAA", "position": "QB"}, {"team": "CCC", "position": "WR"}],
             "salary": 11000, "generation_template": [1, 0]}]
    concentration = _concentration_rows(rows, [qb, receiver])
    receiver_row = next(row for row in concentration if row["player_id"] == receiver.player_id)
    assert receiver_row["frequency"] == 1
    assert receiver_row["one_off_count"] == 1
    assert receiver_row["candidate_generation_exposure_cap"] == 1.0
    assert receiver_row["mean_rank"] == 1


def test_bring_back_diagnostic_distinguishes_inactive_rule_and_missing_market() -> None:
    qb = _player("QB One", "AAA", "BBB", "QB", 6000, 20, 30)
    back = _player("RB One", "BBB", "AAA", "RB", 6000, 15, 24)
    qb.market_context_point_in_time_safe = True
    measured = _bring_back_evaluation(qb, back, [], 0.1, False)
    assert measured["rule_fired"] is False
    assert measured["raw_rule_value"] == 0
    assert measured["ownership"] is None
    assert measured["reason"] == "RB receiving role not established"
    qb.market_context_point_in_time_safe = None
    assert _bring_back_evaluation(qb, back, [], 0.1, False)["raw_rule_value"] is None
