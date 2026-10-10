from backend.app.tests.product.prepared_optimizer_fixture import prepared_optimizer
from copy import deepcopy
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.app.product_schemas import OptimizerRunRequest
from backend.app.product_services.optimizer import OptimizerService, resolve_optimizer_strategy
from backend.app.product_services.single_lineup import (
    CAPTAIN_SINGLE_LINEUP_STRATEGY_ID as CAPTAIN, CLASSIC_SINGLE_LINEUP_STRATEGY_ID as CLASSIC,
    SINGLE_LINEUP_STRATEGIES, generate_candidates, lineup_diagnostics, select_single_lineup,
    contest_context,
)
from backend.app.product_services.optimizer_effectiveness import candidate_snapshot, extract_saved_pool


def roster(*, captain=False, mean=15, floor=8, ceiling=22, availability=1, prefix="a", concentrated=False):
    positions = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "WR", "DST"]
    if captain:
        positions = ["QB", "WR", "RB", "QB", "WR", "TE"]
    rows = []
    for index, position in enumerate(positions):
        slot = "CPT" if captain and index == 0 else "FLEX" if captain else position
        multiplier = 1.5 if slot == "CPT" else 1
        team = ("AAA" if index < 3 else "BBB") if captain else ("AAA" if concentrated else ["AAA", "BBB", "CCC"][index % 3])
        rows.append({"player_id": f"{prefix}-{index}", "name": f"Player {prefix} {index}",
                     "position": position, "roster_position": slot, "player_team": team,
                     "opponent_team": "BBB" if team == "AAA" else "AAA",
                     "salary": 5000 * multiplier, "projection": mean * multiplier,
                     "predicted_p10": floor, "p90": ceiling * multiplier,
                     "pregame_availability_probability": availability, "ownership": 30,
                     "showdown_qb_eligible": position == "QB", "is_starting_qb": position == "QB"})
    return rows


@pytest.mark.parametrize("strategy,format", SINGLE_LINEUP_STRATEGIES.items())
def test_new_objective_preserves_user_lineup_controls(strategy, format):
    request = OptimizerRunRequest(season=2026, week=1, slate="TEST", strategy=strategy,
        params={"num_lineups": 50, "max_exposure": .01, "max_lineup_overlap": 0,
                **({"max_lineups_per_primary_game": 1} if format == "classic" else {}), "soft_scenario_diversity": True,
                "exclude_player_ids": ["canonical-id"]})
    assert (request.contest_format, request.objective) == (format, "cash")
    assert request.params["num_lineups"] == 50 and request.params["max_exposure"] == .01
    assert request.params["max_lineup_overlap"] == 0
    assert "soft_scenario_diversity" not in request.params
    if format == "classic":
        assert request.params["max_lineups_per_primary_game"] == 1
    assert request.params["exclude_player_ids"] == ["canonical-id"]
    config = resolve_optimizer_strategy(contest_format=format, objective="cash", strategy=strategy)
    assert config["engine"] == "cash_oriented_single_lineup_selector"
    assert config["evidence_status"] == "transparent_proxy_unvalidated"


@pytest.mark.parametrize("params", [{"long_shot_mode": True}, {"allow_incomplete_evidence": True}])
def test_public_requests_cannot_override_objective_or_readiness(params):
    with pytest.raises(ValueError):
        OptimizerRunRequest(season=2026, week=1, slate="TEST", strategy=CLASSIC, params=params)
    with pytest.raises(ValueError, match="cash objective"):
        OptimizerRunRequest(season=2026, week=1, slate="TEST", strategy=CAPTAIN, objective="gpp")


@pytest.mark.parametrize("captain", [False, True])
def test_selection_can_reject_highest_mean_and_summed_p90(captain):
    stable = roster(captain=captain, mean=15, floor=12, ceiling=18, prefix="stable")
    fragile = roster(captain=captain, mean=16, floor=0, ceiling=45, availability=.8, prefix="fragile")
    source = deepcopy([fragile, stable])
    selected, report = select_single_lineup(source, strategy=CAPTAIN if captain else CLASSIC)
    assert len(selected) == 1 and selected[0][0]["player_id"].startswith("stable")
    assert report["recommended"]["expected_points"] < max(r["expected_points"] for r in report["all_candidates"])
    assert report["all_candidates"][0]["p90"] < report["all_candidates"][1]["p90"]
    assert report["cash_probability"] is None and report["calibration_status"] == "unvalidated"
    assert report["all_candidates"][1]["rejection_reason"]
    assert report["recommended"]["selection_score"] == pytest.approx(sum(report["recommended"]["objective_contributions"].values()))
    assert source == [fragile, stable]


def test_correlations_change_downside_and_selection_not_expected_points():
    independent = roster(prefix="spread")
    concentrated = roster(prefix="stack", concentrated=True)
    spread = lineup_diagnostics(independent)
    stack = lineup_diagnostics(concentrated)
    assert stack["expected_points"] == spread["expected_points"]
    assert stack["downside_spread"] > spread["downside_spread"]
    chosen, _ = select_single_lineup([concentrated, independent], strategy=CLASSIC)
    assert chosen[0][0]["player_id"].startswith("spread")


def test_captain_points_and_marginal_spread_apply_multiplier_once():
    rows = roster(captain=True)
    result = lineup_diagnostics(rows)
    assert result["expected_points"] == 15 * 6.5
    assert not result["missing_quantiles"]
    assert result["upside_diagnostic"] != sum(row["p90"] for row in rows)


def test_missing_evidence_does_not_become_a_probability_or_zero_ownership_advantage():
    rows = roster()
    rows[0].update(predicted_p10=None, pregame_availability_probability=None, ownership=None)
    diagnostic = lineup_diagnostics(rows)
    assert diagnostic["missing_quantiles"] == [rows[0]["name"]]
    assert diagnostic["cash_probability"] is None
    assert diagnostic["competition_risk_points"] is None
    with pytest.raises(ValueError, match="complete slot ownership"):
        lineup_diagnostics(rows, competition_supported=True)


def test_supported_popularity_affects_proxy_without_claiming_a_field_cutoff():
    popular, contrarian = roster(prefix="popular"), roster(prefix="contrarian")
    for row in popular: row["ownership"] = 70
    for row in contrarian: row["ownership"] = 3
    selected, report = select_single_lineup([contrarian, popular], strategy=CLASSIC, competition_supported=True)
    assert selected[0][0]["player_id"].startswith("popular")
    assert report["cash_probability"] is None
    assert report["competition_status"] == "supported_slot_popularity_proxy"


def test_ties_deduplicate_and_are_deterministic_and_manifest_is_complete():
    a, b = roster(prefix="a"), roster(prefix="b")
    selected, report = select_single_lineup([b, a, a], strategy=CLASSIC)
    assert selected[0][0]["player_id"] == "a-0" and report["candidate_count"] == 2
    params = {"strategy_runtime": {"single_lineup": report}}
    params["strategy_runtime"]["candidate_pool_manifest"] = candidate_snapshot(params, "classic")
    assert extract_saved_pool(params, "classic")["count"] == 2
    params["strategy_runtime"]["single_lineup"]["all_candidates"][0]["selection_score"] += 1
    assert extract_saved_pool(params, "classic")["reason"] == "candidate_pool_hash_mismatch"


@pytest.mark.parametrize("captain", [False, True])
def test_broad_legal_candidate_generation_and_final_one_roster(captain):
    base = roster(captain=captain)
    if captain:
        # Discovery consumes base-slot salary/projection, before the CPT solver.
        for key in ("salary", "projection", "p90"):
            base[0][key] /= 1.5
    # Add choices without changing canonical ID uniqueness or legal role counts.
    extras = deepcopy(base)
    for row in extras:
        row["player_id"] = row["player_id"] + "-alt"
        row["projection"] -= 1; row["p90"] += 3
    pool = pd.DataFrame(base + extras)
    service = OptimizerService.__new__(OptimizerService)
    fmt = "showdown" if captain else "classic"
    candidates = generate_candidates(pool, service._solve_lineup, contest_format=fmt, target=12,
        base_kwargs={"contest_type": "captain" if captain else "cash", "stack_params": {"enabled": False},
                     "locked_player_ids": {base[1]["player_id"]}, "flex_only_player_ids": set()})
    assert len(candidates) == 12
    selected, _ = select_single_lineup(candidates, strategy=CAPTAIN if captain else CLASSIC)
    valid, reason = (service._validate_showdown_lineups if captain else service._validate_classic_lineups)(
        selected, requested_lineups=1, max_exposure=1, locked_player_ids={base[1]["player_id"]},
        enforce_single_te=False, **({} if captain else {"avoid_dst_opponents": False}))
    assert valid, reason
    assert len(selected) == 1


def test_unverified_contest_metadata_cannot_assert_payout_or_cash_probability():
    params = {"contest_urls": ["https://www.draftkings.com/draft/contest/1"],
              "contest_metadata": [{"verified": True, "paid_places": 50}]}
    with patch("backend.app.product_services.showdown_contests.fetch_contests", return_value=[{"source": "unavailable", "error": "unavailable"}]):
        context = contest_context(params, [], contest_format="classic")
    assert context["status"] == "unverified_or_slate_match_unavailable"
    assert context["facts"]["paid_places"] is None
    assert "no_supported_field_model" in context["selection_effect"]


def test_classic_single_lineup_readiness_blocks_before_solver():
    from backend.app.tests.product.test_classic_data_readiness import fixture, service_fixture, refresh_result, NOW
    from backend.app.product_services import classic_data_readiness as gate
    rows, evidence = fixture()
    evidence["source_manifest"]["markets"] = []
    service = service_fixture(rows)
    with prepared_optimizer(service, return_value=refresh_result()), patch.object(gate, "read_evidence", return_value=evidence):
        with pytest.raises(gate.ClassicDataNotReady):
            service.run_job(season=NOW.year, week=1, slate="SUNDAY_MAIN", strategy=CLASSIC,
                            params={"num_lineups": 5}, contest_format="classic", objective="cash")
    service._solve_lineup.assert_not_called()
    failed = service._persist_optimizer_run.call_args.args[0]
    assert failed.status == "failed" and failed.results is None


def test_captain_single_lineup_readiness_blocks_before_solver():
    from datetime import UTC, datetime
    from backend.app.product_services import showdown_data_readiness as gate
    service = OptimizerService("sqlite://")
    service._load_player_pool = MagicMock(return_value=pd.DataFrame(roster(captain=True)))
    service._resolve_run_lineage = MagicMock(return_value=("projection", None, datetime.now(UTC)))
    service._persist_optimizer_run = MagicMock(return_value=True)
    service._solve_lineup = MagicMock(side_effect=AssertionError("Solver must not run"))
    refreshed = dict(projection_run_id="projection", data_cutoff_at=datetime.now(UTC), ownership_run_id=None, report={})
    with prepared_optimizer(service, return_value=refreshed):
        with pytest.raises(gate.ShowdownDataNotReady):
            service.run_job(season=datetime.now(UTC).year, week=1, slate="TEST", strategy=CAPTAIN, params={})
    service._solve_lineup.assert_not_called()


def test_captain_success_freezes_before_candidates_and_never_calls_portfolio_selector():
    from backend.app.tests.product.test_showdown_data_readiness import ready_rows, service_fixture, refresh_result, NOW
    from backend.app.product_services.showdown_data_readiness import validate_frozen_evidence
    service = service_fixture(ready_rows())
    service._attach_symbolic_explanations = MagicMock()
    def discover(pool, solve, **kwargs):
        assert validate_frozen_evidence(service._persist_optimizer_run.call_args.args[0].params["showdown_evidence_snapshot"])["status"] == "READY"
        return [solve(pool, **kwargs["base_kwargs"])]
    with prepared_optimizer(service, return_value=refresh_result()), \
         patch("backend.app.product_services.optimizer.generate_single_lineup_candidates", side_effect=discover), \
         patch("backend.app.product_services.optimizer.select_showdown_portfolio", side_effect=AssertionError("No portfolio objective")):
        job = service.run_job(season=NOW.year, week=1, slate="THURSDAY_NIGHT", strategy=CAPTAIN,
                              params={"num_lineups": 1, "soft_scenario_diversity": True})
    assert job.status == "completed", job.message
    assert len(job.results) == 1 and job.params["num_lineups"] == 1
    assert job.params["data_readiness"]["status"] == "READY"
    assert job.params["strategy_runtime"]["single_lineup"]["cash_probability"] is None


def test_classic_success_freezes_before_candidates_and_ignores_user_exclusions_for_model():
    from backend.app.tests.product.test_classic_data_readiness import fixture, service_fixture, refresh_result, NOW
    from backend.app.product_services import classic_data_readiness as gate
    rows, evidence = fixture()
    service = service_fixture(rows)
    service._attach_symbolic_explanations = MagicMock()
    excluded = rows[1]["player_id"]
    def discover(pool, solve, **kwargs):
        saved = service._persist_optimizer_run.call_args.args[0]
        assert gate.validate_frozen_evidence(saved.params["classic_evidence_snapshot"])["status"] == "READY"
        assert excluded in {r["player_id"] for r in saved.params["classic_evidence_snapshot"]["player_pool"]}
        assert excluded not in set(pool["player_id"])
        assert saved.params["classic_final_input_proof"]["frozen_before_candidate_generation"]
        lineup = OptimizerService._solve_lineup(service, pool, **{**kwargs["base_kwargs"], "include_control_comparison": False})
        return [lineup] if lineup else []
    with prepared_optimizer(service, return_value=refresh_result()), patch.object(gate, "read_evidence", return_value=evidence), \
         patch("backend.app.product_services.optimizer.generate_single_lineup_candidates", side_effect=discover):
        job = service.run_job(season=NOW.year, week=1, slate="SUNDAY_MAIN", strategy=CLASSIC,
            params={"num_lineups": 1, "exclude_player_ids": [excluded], "exclude_questionable": False})
    assert job.status == "completed", job.message
    assert len(job.results) == 1 and excluded not in {row["player_id"] for row in job.results[0]}
    assert job.params["entry_readiness"]["status"] == "ENTRY_CLEARANCE_PENDING"


def test_weekly_defaults_are_active_but_explicit_legacy_requests_are_preserved():
    from backend.app.weekly_schemas import WeeklyRunRequest
    for fmt, strategy in [("classic", "classic_large_gpp_v1"), ("showdown", "showdown_gpp_portfolio_v3")]:
        request = WeeklyRunRequest(season=2026, week=1, slate="TEST", contest_format=fmt)
        assert request.strategy == strategy and request.objective == "gpp"
        assert request.optimizer_params["num_lineups"] == 5
        cash = WeeklyRunRequest(season=2026, week=1, slate="TEST", contest_format=fmt, objective="cash")
        assert cash.objective == "cash" and cash.strategy == (CLASSIC if fmt == "classic" else CAPTAIN)
    old = WeeklyRunRequest(season=2026, week=1, slate="TEST", strategy="classic_large_gpp_v1")
    assert old.strategy == "classic_large_gpp_v1" and old.objective == "gpp"


def test_active_ai_packet_request_accepts_exactly_one():
    good = OptimizerRunRequest(season=2026, week=1, slate="TEST", strategy=CAPTAIN, params={"ai_requested_entries": 1})
    assert good.params["ai_requested_entries"] == 1
    with pytest.raises(ValueError, match="from 1 to 1"):
        OptimizerRunRequest(season=2026, week=1, slate="TEST", strategy=CAPTAIN, params={"ai_requested_entries": 2})


def test_captain_discovery_does_not_use_legacy_gpp_value_pruning():
    service = OptimizerService.__new__(OptimizerService)
    service._apply_pool_filters = MagicMock(side_effect=AssertionError("Legacy pruning must not run"))
    rows = roster(captain=True, mean=4, floor=1, ceiling=6)
    for r in rows: r['is_starting_qb'] = r['position'] == 'QB'
    selected, _ = service._select_strategy_candidates(pd.DataFrame(rows), strategy=CAPTAIN, contest_type='captain')
    assert len(selected) == len(rows)


@pytest.mark.parametrize('strategy,fmt', SINGLE_LINEUP_STRATEGIES.items())
def test_single_lineup_export_blocks_unverified_saved_evidence(strategy, fmt):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from backend.app.api.product_routes import download_optimizer_lineups
    service = MagicMock()
    service.get_job.return_value = SimpleNamespace(job_id='unverified', status='completed', strategy=strategy,
        contest_format=fmt, params={}, results=[roster(captain=fmt == 'showdown')])
    with pytest.raises(HTTPException) as failure:
        download_optimizer_lineups('unverified', service=service)
    assert failure.value.status_code == 422
    assert 'verified frozen' in failure.value.detail


def test_weekly_active_strategy_infers_format_and_preserves_lineup_count():
    from backend.app.weekly_schemas import WeeklyRunRequest
    request = WeeklyRunRequest(season=2026, week=1, slate='TEST', strategy=CAPTAIN,
        optimizer_params={'num_lineups': 5, 'max_lineup_overlap': 1})
    assert request.contest_format == 'showdown' and request.objective == 'cash'
    assert request.optimizer_params['num_lineups'] == 5
    assert request.optimizer_params['max_lineup_overlap'] == 1
    for change in ({'objective': 'gpp'}, {'contest_format': 'classic'}, {'optimizer_params': {'allow_incomplete_evidence': True}}):
        with pytest.raises(ValueError):
            WeeklyRunRequest(season=2026, week=1, slate='TEST', strategy=CAPTAIN, **change)


@pytest.mark.parametrize('captain', [False, True])
def test_multiple_outputs_follow_cash_rank_and_enforce_exposure_overlap(captain):
    from collections import Counter
    strategy = CAPTAIN if captain else CLASSIC
    best = roster(captain=captain, prefix='a', mean=18)
    similar = deepcopy(best)
    similar[-1] = roster(captain=captain, prefix='b', mean=17)[-1]
    other = roster(captain=captain, prefix='c', mean=16)
    selected, report = select_single_lineup([other, similar, best], strategy=strategy,
        controls={'num_lineups': 2, 'max_exposure': .5, 'max_lineup_overlap': 1})
    assert len(selected) == 2
    assert selected[0][0]['player_id'].startswith('a')
    assert selected[1][0]['player_id'].startswith('c')
    counts = Counter(p['player_id'] for lineup in selected for p in lineup)
    assert max(counts.values()) == 1
    assert report['recommended_count'] == 1 and report['selected_count'] == 2
    assert report['requested_count'] == 2 and report['cash_probability'] is None
    assert report['constraint_selection']['status'] == 'fulfilled'
    assert report['all_candidates'][1]['selected'] is False
    assert 'user limits' in report['all_candidates'][1]['rejection_reason']
    assert selected[1][0]['cash_lineup_selection']['primary'] is False


def test_count_feasibility_can_require_rejecting_top_candidate_without_greedy_underfill():
    best = roster(prefix='a', mean=18)
    left = roster(prefix='b', mean=17)
    right = roster(prefix='c', mean=16)
    left[0] = deepcopy(best[0])
    right[1] = deepcopy(best[1])
    # Best conflicts with either alternative; the two alternatives can coexist.
    selected, report = select_single_lineup([best, left, right], strategy=CLASSIC,
        controls={'num_lineups': 2, 'max_lineup_overlap': 0})
    assert len(selected) == 2
    assert report['recommended']['rank'] == 2
    assert report['constraint_selection']['status'] == 'fulfilled'
    assert report['all_candidates'][0]['selected'] is False
    assert report['all_candidates'][0]['rejection_reason']


def test_infeasible_requested_count_is_explicit_and_caps_never_relaxed():
    best = roster(prefix='a', mean=18)
    similar = deepcopy(best)
    similar[-1] = roster(prefix='b')[-1]
    selected, report = select_single_lineup([best, similar], strategy=CLASSIC,
        controls={'num_lineups': 2, 'max_exposure': .5})
    assert len(selected) == 1 and report['requested_count'] == 2
    assert report['constraint_selection']['status'] == 'underfilled'
    assert report['constraint_selection']['limits_relaxed'] is False
    assert report['cash_probability'] is None


def test_captain_and_elevated_risk_caps_use_correct_roles_and_rounding():
    a = roster(captain=True, prefix='a', mean=18)
    b = roster(captain=True, prefix='b', mean=17)
    b[0] = deepcopy(a[0])
    c = roster(captain=True, prefix='c', mean=16)
    selected, report = select_single_lineup([a, b, c], strategy=CAPTAIN,
        controls={'num_lineups': 2, 'captain_max_exposure': .5})
    assert report['selected_candidate_ids'] == ['cash-1', 'cash-3']
    a[1]['injury_status'] = 'Q'
    selected, report = select_single_lineup([a, b, c], strategy=CAPTAIN,
        controls={'num_lineups': 2, 'elevated_player_max_exposure': .4})
    assert all(p['player_id'] != a[1]['player_id'] for lineup in selected for p in lineup)
    assert report['selected_count'] == 2


def test_classic_primary_game_cap_and_per_lineup_team_game_limits():
    a = roster(prefix='a', mean=18)
    b = roster(prefix='b', mean=17)
    c = roster(prefix='c', mean=16)
    c[0].update(player_team='DDD', opponent_team='EEE')
    selected, report = select_single_lineup([a, b, c], strategy=CLASSIC,
        controls={'num_lineups': 2, 'max_lineups_per_primary_game': 1})
    assert report['selected_candidate_ids'] == ['cash-1', 'cash-3']
    selected, report = select_single_lineup([a, b, c], strategy=CLASSIC,
        controls={'max_players_per_team': 2})
    assert not selected and report['constraint_selection']['status'] == 'underfilled'
    selected, report = select_single_lineup([a, b, c], strategy=CLASSIC,
        controls={'max_players_per_game': 3})
    assert not selected


@pytest.mark.parametrize('captain', [False, True])
def test_real_discovery_returns_multiple_legal_outputs_with_user_constraints(captain):
    from collections import Counter
    base = roster(captain=captain)
    if captain:
        for key in ('salary', 'projection', 'p90'):
            base[0][key] /= 1.5
    extras = deepcopy(base)
    for row in extras:
        row['player_id'] += '-alt'
        row['projection'] -= 1
    service = OptimizerService.__new__(OptimizerService)
    controls = {'num_lineups': 3, 'max_exposure': .5, 'max_lineup_overlap': 5 if captain else 8,
        'max_players_per_team': 3, 'max_elevated_players_per_lineup': 0}
    candidates = generate_candidates(pd.DataFrame(base + extras), service._solve_lineup,
        contest_format='showdown' if captain else 'classic', target=30,
        base_kwargs={'contest_type': 'captain' if captain else 'cash', 'stack_params': {
            'enabled': False, 'max_players_per_team': 3, 'single_lineup_user_controls': controls}})
    selected, report = select_single_lineup(candidates, strategy=CAPTAIN if captain else CLASSIC, controls=controls)
    assert len(selected) == 3
    valid, reason = (service._validate_showdown_lineups if captain else service._validate_classic_lineups)(
        selected, requested_lineups=3, max_exposure=.5, enforce_single_te=False,
        **({'max_players_per_team': 3} if captain else {'avoid_dst_opponents': False, 'uniqueness_overlap': 8}))
    assert valid, reason
    for lineup in selected:
        assert max(Counter(p['player_team'] for p in lineup).values()) <= 3
    assert report['selected_count'] == 3 and report['cash_probability'] is None


@pytest.mark.parametrize('params', [{'num_lineups': 0}, {'num_lineups': 51}, {'num_lineups': True},
    {'num_lineups': 1.5}, {'max_exposure': float('nan')}, {'max_lineup_overlap': 7},
    {'max_players_per_team': 2}, {'captain_max_exposure': 101}, {'max_lineups_per_primary_game': 1}])
def test_invalid_captain_controls_fail_at_request_boundary(params):
    with pytest.raises(ValueError):
        OptimizerRunRequest(season=2026, week=1, slate='TEST', strategy=CAPTAIN, params=params)


@pytest.mark.parametrize('captain', [False, True])
def test_service_preserves_requested_count_and_freezes_before_multi_lineup_generation(captain):
    from contextlib import ExitStack
    if captain:
        from backend.app.tests.product.test_showdown_data_readiness import ready_rows, service_fixture, refresh_result, NOW
        from backend.app.product_services import showdown_data_readiness as gate
        rows, evidence = ready_rows(), None
    else:
        from backend.app.tests.product.test_classic_data_readiness import fixture, service_fixture, refresh_result, NOW
        from backend.app.product_services import classic_data_readiness as gate
        rows, evidence = fixture()
    service = service_fixture(rows)
    service._solve_lineup = OptimizerService._solve_lineup.__get__(service)
    service._attach_symbolic_explanations = MagicMock()
    def discover(pool, solve, **kwargs):
        saved = service._persist_optimizer_run.call_args.args[0]
        assert saved.params['num_lineups'] == 3
        assert gate.validate_frozen_evidence(saved.params['showdown_evidence_snapshot' if captain else 'classic_evidence_snapshot'])['status'] == 'READY'
        return generate_candidates(pool, solve, **{**kwargs, 'target': 12})
    with ExitStack() as stack:
        stack.enter_context(prepared_optimizer(service, return_value=refresh_result()))
        if evidence:
            stack.enter_context(patch.object(gate, 'read_evidence', return_value=evidence))
        stack.enter_context(patch('backend.app.product_services.optimizer.generate_single_lineup_candidates', side_effect=discover))
        stack.enter_context(patch('backend.app.product_services.optimizer.select_showdown_portfolio', side_effect=AssertionError('No legacy portfolio objective')))
        job = service.run_job(season=NOW.year, week=1, slate='THURSDAY_NIGHT' if captain else 'SUNDAY_MAIN',
            strategy=CAPTAIN if captain else CLASSIC,
            params={'num_lineups': 3, 'max_exposure': 1, 'max_players_per_team': 3,
                'max_lineup_overlap': 6 if captain else 8})
    assert job.status == 'completed', job.message
    assert len(job.results) == 3 and job.params['num_lineups'] == 3
    assert job.params['strategy_runtime']['single_lineup']['recommended_count'] == 1
    assert job.params['strategy_runtime']['single_lineup']['selected_count'] == 3
    assert job.params['strategy_runtime']['single_lineup']['cash_probability'] is None
    assert job.params['data_readiness']['status'] == 'READY'


@pytest.mark.parametrize('strategy,fmt', SINGLE_LINEUP_STRATEGIES.items())
def test_csv_export_preserves_verified_multi_lineup_count(strategy, fmt):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from backend.app.api.product_routes import download_optimizer_lineups
    from backend.app.product_services import classic_data_readiness, showdown_data_readiness
    from backend.app.product_services.draftkings_export import DraftKingsExportService
    service = MagicMock()
    frozen = {'optimizer_run_id': 'verified'}
    lineups = [roster(captain=fmt == 'showdown', prefix=str(i)) for i in range(3)]
    service.get_job.return_value = SimpleNamespace(job_id='verified', status='completed', strategy=strategy,
        contest_format=fmt, params={'num_lineups': 3,
            'showdown_evidence_snapshot' if fmt == 'showdown' else 'classic_evidence_snapshot': frozen}, results=lineups)
    gate = showdown_data_readiness if fmt == 'showdown' else classic_data_readiness
    with patch.object(gate, 'validate_frozen_evidence', return_value={'status': 'READY'}), \
         patch.object(DraftKingsExportService, 'build_lineup_download', return_value=('lineups.csv', 'text/csv', 'csv')) as export:
        response = download_optimizer_lineups('verified', service=service)
        assert response.status_code == 200
        assert export.call_args.kwargs['lineups'] == lineups
        gate.validate_frozen_evidence.assert_called_with(frozen)
        service.get_job.return_value.results = lineups[:2]
        with pytest.raises(HTTPException) as error:
            download_optimizer_lineups('verified', service=service)
        assert error.value.status_code == 422


def test_locks_override_ordinary_exposure_but_explicit_player_caps_remain_binding():
    a = roster(prefix='a', mean=18)
    b = roster(prefix='b', mean=17)
    b[0] = deepcopy(a[0])
    lock = a[0]['player_id']
    selected, _ = select_single_lineup([a, b], strategy=CLASSIC,
        controls={'num_lineups': 2, 'max_exposure': .5, 'locked_player_ids': [lock]})
    assert len(selected) == 2
    selected, report = select_single_lineup([a, b], strategy=CLASSIC,
        controls={'num_lineups': 2, 'max_exposure': .5, 'locked_player_ids': [lock], 'maximum_exposure_by_player': {lock: .5}})
    assert len(selected) == 1 and report['constraint_selection']['status'] == 'underfilled'
    unlocked = roster(prefix='c', mean=20)
    selected, report = select_single_lineup([unlocked, a], strategy=CLASSIC,
        controls={'locked_player_ids': [lock]})
    assert selected[0][0]['player_id'] == lock
    assert report['all_candidates'][0]['rejection_reason'] == 'Missing required locked player(s).'


def test_result_api_exposes_saved_constraints_when_no_candidate_fits():
    from backend.app.api.product_routes import get_optimizer_results
    from backend.app.product_services.optimizer import OptimizerJob
    from datetime import datetime
    _, report = select_single_lineup([roster()], strategy=CLASSIC, controls={'num_lineups': 3, 'max_exposure': 0})
    service = MagicMock()
    service.get_job.return_value = OptimizerJob(job_id='empty', season=2026, week=1, slate='TEST', status='failed', strategy=CLASSIC,
        created_at=datetime(2026, 10, 9), updated_at=datetime(2026, 10, 9), results=[],
        params={'strategy_runtime': {'single_lineup': report}}, contest_format='classic', objective='cash')
    response = get_optimizer_results('empty', service=service)
    assert response.single_lineup_selection['requested_count'] == 3
    assert response.single_lineup_selection['selected_count'] == 0
    assert response.single_lineup_selection['user_constraints']['max_exposure'] == 0


def test_exposure_rounding_does_not_add_an_appearance_for_float_artifacts():
    from backend.app.product_services.single_lineup import appearance_limit
    assert appearance_limit(50, .56) == 28
    assert appearance_limit(50, .58) == 29
    assert appearance_limit(3, .5) == 2
