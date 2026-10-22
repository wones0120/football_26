import pandas as pd
import pytest

from backend.app.product_services.workload_count_forecast import forecast, team_games, utility


def history():
    rows = []
    for team in ("A", "B"):
        for week in range(1, 9):
            for pid, pos, passes, rushes, targets in (("q", "QB", 30, 5, 0), ("r", "RB", 0, 15, 5), ("w", "WR", 0, 0, 20)):
                rows.append(dict(player_master_id=team+pid, team=team, position=pos,
                    period=202500+week, pass_attempts=passes, rush_attempts=rushes, targets=targets, source_id=team+pid+str(week)))
    return pd.DataFrame(rows)


MODEL = dict(training_max_period=202501, center=[0]*4, scale=[1]*4,
             coefficients=[[0]*4, [0]*4], intercept=[40, 25])


def actors():
    return [dict(player_master_id="A"+p, team="A", position=pos) for p, pos in (("q", "QB"), ("r", "RB"), ("w", "WR"))]


def test_explicit_forecasts_differ_from_history_and_conserve():
    result = forecast(history(), actors(), before_period=202509, starters={"A": "Aq"}, model=MODEL)
    q, r, w = result["players"]
    assert q["counts"]["pass_attempts"] == 40
    assert q["raw_history"]["pass_attempts"]["mean"] == 30
    assert q["counts"]["rush_attempts"] == 6.25
    assert r["counts"]["targets"] == pytest.approx(40*25/30*.2)
    for channel in ("targets", "rush_attempts", "pass_attempts"):
        assert result["teams"]["A"]["reconciliation"][channel]["unallocated"] >= 0


def test_unknown_and_excluded_actor_does_not_donate_volume():
    base = forecast(history(), actors(), before_period=202509, starters={"A": "Aq"}, model=MODEL)
    changed = forecast(history(), actors()[:2]+[dict(player_master_id="unknown", team="A", position="WR")], before_period=202509, starters={"A": "Aq"}, model=MODEL)
    assert changed["players"][1]["counts"]["targets"] == pytest.approx(base["players"][1]["counts"]["targets"])
    assert changed["players"][1]["counts"]["rush_attempts"] == base["players"][1]["counts"]["rush_attempts"]
    assert changed["players"][2]["counts"]["targets"] is None
    assert changed["teams"]["A"]["reconciliation"]["targets"]["unallocated"] > 0


def test_missing_participant_and_unverified_starter_abstain():
    h = history(); h = h.loc[~(h.player_master_id.eq("Ar") & h.period.eq(202508))]
    result = forecast(h, actors(), before_period=202509, model=MODEL)
    assert result["players"][0]["counts"]["pass_attempts"] is None
    assert result["players"][1]["counts"]["targets"] is None
    assert "missing participant" in result["players"][1]["reasons"][0]


def test_all_null_team_passes_not_zero_and_future_model_rejected():
    h = history(); h.loc[h.position.eq("QB"), "pass_attempts"] = float("nan")
    assert team_games(h).pass_attempts.isna().all()
    with pytest.raises(ValueError, match="future"):
        forecast(history(), actors(), before_period=202501, model=MODEL)


def test_fp_independent_utility_missing_not_zero_and_unsupported():
    row = dict(position="WR", counts=dict(targets=5, rush_attempts=0), projection=999)
    scales = {"WR": dict(targets=5, rush_attempts=1)}
    assert utility(row, scales) == .5
    row["projection"] = -999
    assert utility(row, scales) == .5
    row["counts"]["targets"] = None
    assert utility(row, scales) is None
    assert utility(dict(position="K", counts={}), scales) is None


def test_duplicate_canonical_actors_rejected():
    with pytest.raises(ValueError, match="Duplicate canonical forecast"):
        forecast(history(), actors()+actors(), before_period=202509, model=MODEL)


def test_non_qb_passes_remain_in_physical_team_budget():
    h = history(); h.loc[h.player_master_id.eq("Aw"), "pass_attempts"] = 1
    assert team_games(h).loc[lambda x:x.team.eq("A"), "pass_attempts"].eq(31).all()


def test_unmapped_source_actors_retain_budget_without_fabricated_canonical_id():
    h = history(); h.loc[h.player_master_id.eq("Aw"), "player_master_id"] = None
    result = forecast(h, actors()[:2], before_period=202509, starters={"A": "Aq"}, model=MODEL)
    assert result["teams"]["A"]["targets"] == pytest.approx(40*25/30)
    assert result["teams"]["A"]["reconciliation"]["targets"]["unallocated"] > 20


def test_fullback_canonical_position_and_workload_are_retained():
    h = history()
    fullback = h.loc[h.player_master_id.eq("Ar")].copy()
    fullback["player_master_id"] = "Afb"; fullback["position"] = "FB"
    fullback["rush_attempts"] = 2; fullback["targets"] = 1
    h = pd.concat([h,fullback],ignore_index=True)
    a = actors()+[dict(player_master_id="Afb",team="A",position="FB")]
    result = forecast(h,a,before_period=202509,starters={"A":"Aq"},model=MODEL)
    assert team_games(h).loc[lambda x:x.team.eq("A"),"rush_attempts"].eq(22).all()
    assert result["players"][-1]["position"] == "RB"
    assert result["players"][-1]["counts"]["rush_attempts"] > 0


def test_target_rate_accounting_clamp_is_explicit():
    h = history(); h.loc[h.player_master_id.eq("Aw"),"targets"] = 40
    result = forecast(h,actors(),before_period=202509,starters={"A":"Aq"},model=MODEL)
    assert result["teams"]["A"]["targets"] <= result["teams"]["A"]["pass_attempts"]
    assert result["teams"]["A"]["accounting_flags"]


def test_workload_captain_objective_does_not_use_fp_and_preserves_reported_fp():
    from backend.app.product_services.optimizer import OptimizerService
    pool = pd.DataFrame([dict(player_id=f"id-{i}", name=f"P{i}", position="WR",
        player_team="AAA" if i%2 else "BBB", opponent_team="BBB" if i%2 else "AAA",
        salary=5000, projection=100-i, p90=500-i,
        showdown_captain_shortlisted=True, showdown_captain_p90=500-i,
        showdown_flex_mean=100-i, workload_utility=i+1) for i in range(8)])
    service = OptimizerService.__new__(OptimizerService)
    kwargs = dict(contest_type="captain", score_col="workload_utility", include_control_comparison=False)
    first = service._solve_lineup(pool, **kwargs)
    assert next(r for r in first if r["roster_position"] == "CPT")["player_id"] == "id-7"
    assert {r["player_id"] for r in first} == {f"id-{i}" for i in range(2,8)}
    assert sum(r["projection"] for r in first) == pytest.approx(sum(100-i for i in range(2,8))+93*.5)
    changed = pool.copy(); changed["projection"] *= -20; changed["p90"] = 9999
    changed["showdown_captain_p90"] = list(range(8)); changed["showdown_flex_mean"] = 0
    second = service._solve_lineup(changed, **kwargs)
    assert {(r["player_id"],r["roster_position"]) for r in first} == {(r["player_id"],r["roster_position"]) for r in second}


def test_workload_portfolio_preserves_four_entries_captain_cap_and_receipt():
    import hashlib, json
    from backend.app.product_services.optimizer import OptimizerService
    from backend.app.product_services.workload_optimizer import solve
    from backend.app.product_services.workload_count_forecast import VERSION
    pool = pd.DataFrame([dict(player_id=f"id-{i}", name=f"P{i}", position="WR",
        player_team="AAA" if i%2 else "BBB", opponent_team="BBB" if i%2 else "AAA",
        salary=5000, projection=100-i, p90=500-i, showdown_captain_shortlisted=True,
        showdown_captain_p90=500-i, showdown_flex_mean=100-i) for i in range(8)])
    receipt = dict(version=VERSION, source_cutoff_at="2025-01-01T00:00:00Z", domain="offensive only",
        objective="normalized counts", players=[dict(player_master_id=f"id-{i}", utility=i+1,
            counts=dict(targets=i+1,rush_attempts=0), reasons=[]) for i in range(8)])
    receipt["sha256"] = hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    params = dict(workload_comparison="normalized_counts", num_lineups=4, max_exposure=1,
        captain_max_exposure=.5, prepared_input_evidence=dict(workload_forecast=receipt))
    kwargs = dict(params=params, contest_type="captain", stack_params=dict(captain_positions=["WR"], max_players_per_team=4),
        locked_ids=set(), flex_only_ids=set(), avoid_dst_opponents=True,
        enforce_single_te=False, requested_captain_id=None)
    lineups, report = solve(OptimizerService.__new__(OptimizerService), pool, **kwargs)
    assert len(lineups) == 4 and max(report["captain_counts"].values()) == 2
    assert all(len({r["player_id"] for r in lineup}) == 6 for lineup in lineups)
    assert all(sum(r["salary"] for r in lineup) <= 50000 for lineup in lineups)
    assert all(r["workload_forecast_sha256"] == receipt["sha256"] for lineup in lineups for r in lineup)
    receipt["players"][0]["utility"] = 999
    with pytest.raises(ValueError, match="checksum"):
        solve(OptimizerService.__new__(OptimizerService), pool, **kwargs)


def test_count_recommendation_never_falls_back_to_fp_tie_break():
    from backend.app.product_services.workload_optimizer import recommendation
    report = dict(candidates=[dict(lineup_number=1, candidate_id="b", projected_points=999),
                              dict(lineup_number=2, candidate_id="a", projected_points=1)], limitations=[])
    lineups = [[dict(workload_forecast=dict(utility=2),roster_position="FLEX")],
               [dict(workload_forecast=dict(utility=2),roster_position="FLEX")]]
    output = recommendation(report,lineups,"normalized_counts")
    assert output["recommended"]["lineup_number"] == 2


def test_count_and_mean_control_share_broad_captain_workload_qualification(monkeypatch):
    import backend.app.product_services.showdown_captain_shortlist as shortlist
    monkeypatch.setattr(shortlist,"assess_captain_workload",lambda row:dict(eligible=True))
    pool = pd.DataFrame([dict(player_id=f"p{i}",name=f"P{i}",position="WR",player_team="AAA",
        p90=30-i,projection=10-i/10) for i in range(7)])
    a,ra=shortlist.build_captain_shortlist(pool,params=dict(workload_comparison="normalized_counts"),flex_only_ids=set())
    b,rb=shortlist.build_captain_shortlist(pool,params=dict(workload_comparison="offensive_mean_control"),flex_only_ids=set())
    assert a.showdown_captain_shortlisted.all() and b.showdown_captain_shortlisted.all()
    assert len(ra["shortlist"]) == len(rb["shortlist"]) == 7
    assert ra["captain_score"] == "1.5 * normalized_count_utility"
    assert rb["captain_score"] == "1.5 * supported_domain_FP_mean"
    pd.testing.assert_series_equal(a.projection,pool.projection)


def test_workload_binds_count_receipt_without_unavailable_analyst_but_standard_rejects():
    from backend.app.product_services.analyst_preparation import bind_handoff
    from backend.app.product_services.analyst_shadow import digest
    handoff = dict(scope=dict(season=2026,week=6,slate="MONDAY_NIGHT",format="SHOWDOWN"),
        mode="AUTO",checked_packet_sha256=None,optimization_intent="MIXED")
    handoff["compatibility_sha256"] = digest(handoff)
    result = dict(analyst_handoff=handoff,workload_forecast=dict(sha256="a"*64))
    payload = dict(season=2026,week=6,slate="MONDAY_NIGHT",contest_format="showdown",
        params=dict(workload_comparison="normalized_counts",analyst_packet_sha256="expired"))
    bind_handoff(payload,result)
    assert payload["params"]["analyst_handoff_applied"]["status"] == "inactive"
    assert "analyst_packet_sha256" not in payload["params"]
    payload["params"] = dict(analyst_handoff_mode="AUTO")
    with pytest.raises(ValueError,match="research unavailable"):
        bind_handoff(payload,result)


def test_partial_workload_portfolio_cannot_be_downloadable_and_controls_not_ignored():
    # Existing real solver test establishes exact requested-size cap enforcement.
    # This fixture isolates unsupported controls before any solver is called.
    from backend.app.product_services.workload_optimizer import solve
    import hashlib,json
    receipt = dict(version="offensive_count_forecast_v1",players=[])
    receipt["sha256"] = hashlib.sha256(json.dumps(receipt,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    kwargs = dict(params=dict(workload_comparison="normalized_counts",max_lineup_overlap=4,
        prepared_input_evidence=dict(workload_forecast=receipt)),contest_type="captain",stack_params={},
        locked_ids=set(),flex_only_ids=set(),avoid_dst_opponents=False,enforce_single_te=False,requested_captain_id=None)
    with pytest.raises(ValueError,match="overlap"):
        solve(None,pd.DataFrame(),**kwargs)
    from backend.app.product_services.optimizer import OptimizerService
    pool = pd.DataFrame([dict(player_id=f"p{i}",name=f"P{i}",position="WR",
        player_team="AAA" if i%2 else "BBB",opponent_team="BBB" if i%2 else "AAA",
        salary=5000,projection=10,p90=20,showdown_captain_shortlisted=i==0,
        showdown_captain_p90=20,showdown_flex_mean=10) for i in range(6)])
    receipt = dict(version="offensive_count_forecast_v1",source_cutoff_at="2025-01-01",domain="offense",objective="counts",
        players=[dict(player_master_id=f"p{i}",utility=1,counts={},reasons=[]) for i in range(6)])
    receipt["sha256"] = hashlib.sha256(json.dumps(receipt,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    kwargs["params"] = dict(workload_comparison="normalized_counts",num_lineups=4,captain_max_exposure=.5,
        prepared_input_evidence=dict(workload_forecast=receipt))
    lineups,report = solve(OptimizerService.__new__(OptimizerService),pool,**kwargs)
    assert lineups == [] and report["achieved"] == 1 and report["attempted_portfolio"]
    assert report["status"].startswith("failed")
