"""Football accounting and time-safe research selection contracts."""
from copy import deepcopy

import numpy as np
import pytest

from backend.app.product_services.research_game_simulation import (
    Assumptions, compare_lineups, dst_points, enumerate_lineups, fantasy_points,
    play_game, simulate_games,
)
from backend.app.product_services.captain_scenario_research import legal, lineup_scores


def football_model():
    players, teams = [], []
    for tm in ("HOME", "AWAY"):
        offset = len(players)
        for pos in ("QB", "RB", "WR", "K", "DST"):
            players.append(dict(id=f"{tm}_{pos}", team=tm, position=pos, catch_rate=.7,
                                yards_per_catch=12., yards_per_carry=4.5, goal_line_multiplier=1.))
        teams.append(dict(team=tm, qb=offset, runners=[offset, offset+1], receivers=[offset+2],
                          kicker=offset+3, dst=offset+4, target_weights=[1.], carry_weights=[.25, .75],
                          pass_rate=.6, completion_rate=.67, int_rate=.025, sack_rate=.06,
                          sack_yards=6., fumble_rate=.01, turnover_td_rate=.1, pat_rate=.95,
                          fg_rate=.85, punt_yards=45., implied_score=24.))
    return dict(players=players, teams=teams)


def test_games_conserve_passing_rushing_and_score_events():
    model = football_model()
    rng = np.random.default_rng(910)
    for _ in range(100):
        g = play_game(model, rng=rng, trace=True)
        assert g["plays"] > 0
        assert all(v >= 0 and int(v) == v for v in g["scores"])
        for t in model["teams"]:
            qb = g["stats"][t["qb"]]
            receiving = [g["stats"][i] for i in t["receivers"]]
            assert qb["passing_yards"] == sum(r["receiving_yards"] for r in receiving)
            assert qb["passing_tds"] == sum(r["receiving_tds"] for r in receiving)
            assert qb["completions"] == sum(r["receptions"] for r in receiving)
            assert qb["attempts"] >= qb["completions"] + qb["passing_interceptions"]
        assert all(e["clock"] > 0 for e in g["events"])


def test_seed_replay_and_independent_evaluation():
    model = football_model()
    a = simulate_games(model, draws=30, seed=88)
    b = simulate_games(model, draws=30, seed=88)
    c = simulate_games(model, draws=30, seed=89)
    assert np.array_equal(a[0], b[0])
    assert a[2]["draws_sha256"] == b[2]["draws_sha256"]
    assert a[2]["draws_sha256"] != c[2]["draws_sha256"]


def test_zero_opportunity_player_cannot_receive_a_target():
    model = football_model()
    absent = deepcopy(model["players"][2])
    absent["id"] = "zero_target_receiver"
    model["players"].append(absent)
    model["teams"][0]["receivers"].append(len(model["players"])-1)
    model["teams"][0]["target_weights"].append(0.)
    for seed in range(10):
        game = play_game(model, rng=np.random.default_rng(seed))
        assert game["stats"][-1]["targets"] == 0
        assert game["stats"][-1]["receptions"] == 0


def test_scoring_signed_outcomes_and_kicker_distances():
    from backend.app.product_services.research_game_simulation import STAT_KEYS
    row = dict.fromkeys(STAT_KEYS, 0)
    row.update(passing_yards=300, passing_tds=2, passing_interceptions=1,
               rushing_yards=100, rushing_tds=1, fumbles_lost=1)
    assert fantasy_points(dict(position="QB"), row) == 40
    empty = dict.fromkeys(STAT_KEYS, 0)
    empty["fumbles_lost"] = 1
    assert fantasy_points(dict(position="RB"), empty) == -1
    empty.update(fumbles_lost=0, fg_short=1, fg_medium=1, fg_long=1, pat_made=2)
    assert fantasy_points(dict(position="K"), empty) == 14
    empty.update(points_allowed=35, sacks=2, interceptions=1, recoveries=1, safeties=1, defensive_tds=1)
    assert dst_points(empty) == 10


def lineup_game():
    ps = []
    for i in range(8):
        ps.append(dict(id=str(i), name=f"Player {i}", team="H" if i < 4 else "A", position="QB" if i in (0, 4) else "WR",
                       salary=5000, captain_salary=7500, projected_mean=20-i, projected_p90=30-i))
    return dict(players=ps, rules={})


def test_exhaustive_legal_pool_captain_multiplier_and_batched_comparison():
    game = lineup_game()
    pool = enumerate_lineups(game)
    # For each of four home captains, exactly 3 home FLEX + 2 away FLEX (6)
    # or 1 home FLEX + 4 away FLEX (3) = nine distinct legal rosters.
    assert len(pool) == 36
    assert all(legal([game["players"][i] for i in l["indices"]], l["captain_id"], game["rules"]) for l in pool)
    outcomes = np.random.default_rng(20).normal(10, 5, (20, 8))
    values = np.column_stack([lineup_scores(outcomes, game["players"], l) for l in pool])
    threshold = np.quantile(values, .95, axis=1)
    rates, means, actual = compare_lineups(outcomes, game, pool, batch_size=3)
    assert np.allclose(actual, threshold)
    assert np.allclose(rates, (values >= threshold[:, None]).mean(axis=0))
    assert np.allclose(means, values.mean(axis=0))
    ones = np.ones((1, 8))
    assert lineup_scores(ones, game["players"], pool[0])[0] == 6.5


def test_locks_and_salary_can_make_specific_captain_infeasible():
    game = lineup_game()
    game["players"][0]["salary"] = 40000
    game["players"][0]["captain_salary"] = 60000
    pool = enumerate_lineups(game)
    assert not any(l["captain_id"] == "0" for l in pool)
    game["rules"]["locked_ids"] = ["0"]
    with pytest.raises(ValueError, match="No legal"):
        enumerate_lineups(game)


def test_invalid_simulation_parameters():
    with pytest.raises(ValueError):
        simulate_games(football_model(), draws=0, seed=1)


def test_pilot_improves_team_touchdown_mix_without_relabeling_scores():
    from scripts.research_monday_game_simulation import load_model, calibrate
    _, model, _ = load_model()
    assumptions = Assumptions(calibration_draws=200, calibration_iterations=3)
    _, audit = calibrate(model, assumptions, 20261014)
    first = audit['iterations'][0]['touchdown_checks']
    last = audit['iterations'][-1]['touchdown_checks']
    assert sum(abs(s['passing_td_share']-s['target']) for s in last) < sum(abs(s['passing_td_share']-s['target']) for s in first)
    assert all(t['red_zone_pass_odds_multiplier'] < 1 for t in model['teams'])


def test_frozen_monday_inputs_are_before_kickoff_and_preferences_do_not_erase_players():
    from scripts.research_monday_game_simulation import load_model
    game, model, lineage = load_model()
    assert game["cutoff"] < game["kickoff"]
    assert lineage["history_max_imported_at"] < game["cutoff"]
    assert {p["id"] for p in game["players"]}.issubset({p["id"] for p in model["players"]})
    assert any(not p["optimizer_eligible"] and p.get("targets", 0) > 0 and not p.get("aggregate_bucket") for p in model["players"])
    assert len([p for p in model["players"] if p["position"] == "QB"]) == 2
    assert [p["position"] for p in sorted(game["players"], key=lambda p: -p["projected_p90"])[:4]] == ["QB", "QB", "WR", "RB"]
    assert all(t["sack_yards"] > 0 for t in model["teams"])
    for p in model['players']:
        if p['position'] == 'QB':
            assert p['historical_games'] == 4
            assert lineage['history_by_player'][p['id']] == [1, 2, 3, 4]
    assert all(0 < t['target_passing_td_share'] < 1 for t in model['teams'])
    assert all(abs(sum(t['target_rushing_td_shares'])-1) < 1e-10 for t in model['teams'])


def test_weekly_history_uses_import_clocks_not_stale_final_score_fields():
    from scripts.research_monday_game_simulation import historical_weekly_eligible, safe_time
    row = dict(source_system='nflreadpy', season=2026, week=4, created_at='2026-10-06T12:00:00Z', raw_row_json=dict(season_type='REG'))
    schedule = dict(game_type='REG', created_at='2026-10-01T12:00:00Z', raw_row_json=dict(gameday='2026-10-04', gametime='13:00', home_score=None, away_score=None))
    args = dict(cutoff=safe_time('2026-10-12T10:00:00Z'), season=2026, week=5)
    assert historical_weekly_eligible(row, schedule, **args)
    for imported in ('2026-10-04T18:00:00Z', '2026-10-13T12:00:00Z'):
        assert not historical_weekly_eligible(dict(row, created_at=imported), schedule, **args)
    assert not historical_weekly_eligible(dict(row, week=5), schedule, **args)


def test_structures_ignore_player_identity_but_preserve_team_position_and_role():
    from scripts.research_monday_game_simulation import structure_key
    game = lineup_game()
    for p in game['players']:p['research_role'] = 'primary WR' if p['position'] == 'WR' else 'rushing QB'
    a = dict(captain_id='0', indices=[0,1,2,3,4,5])
    b = dict(captain_id='0', indices=[0,1,2,3,4,6])
    assert structure_key(game['players'], a, roles=True) == structure_key(game['players'], b, roles=True)
    game['players'][6]['research_role'] = 'low-volume WR'
    assert structure_key(game['players'], a, roles=False) == structure_key(game['players'], b, roles=False)
    assert structure_key(game['players'], a, roles=True) != structure_key(game['players'], b, roles=True)


def test_future_feature_and_projection_evidence_is_rejected(monkeypatch):
    from scripts import research_monday_game_simulation as script
    original = script.read
    def future_feature(path):
        value = original(path)
        if path.name == "features.json.gz":
            value = deepcopy(value)
            for row in value:
                row["feature_json"]["market_observed_at"] = "2027-01-01T00:00:00+00:00"
        return value
    monkeypatch.setattr(script, "read", future_feature)
    with pytest.raises(ValueError, match="Future feature"):
        script.load_model()
    def future_projection(path):
        value = original(path)
        if path.name == "monday.json":
            value = deepcopy(value)
            value["projections"][0]["created_at"] = "2027-01-01T00:00:00+00:00"
        return value
    monkeypatch.setattr(script, "read", future_projection)
    with pytest.raises(ValueError, match="Future projection"):
        script.load_model()


def test_evaluation_games_cannot_change_selected_captain_or_roster(monkeypatch):
    from scripts import research_monday_game_simulation as script
    game = lineup_game()
    model = dict(players=game["players"])
    monkeypatch.setattr(script, "load_model", lambda: (game, model, {}))
    monkeypatch.setattr(script, "calibrate", lambda *args: (np.ones(2), {}))
    def fake_simulate(model, *, draws, seed, **kwargs):
        points = np.ones((draws, 8))
        points[:, 0 if seed == 90 else 1] = 100
        scores = np.tile([28, 28], (draws, 1))
        return points, np.zeros(draws, dtype=int), dict(scores=scores.tolist())
    monkeypatch.setattr(script, "simulate_games", fake_simulate)
    result = script.research(draws=200, seed=90)
    assert result["selected_captain"] == "0"
    winner = next(c for c in result["captains"] if c["captain_id"] == "0")
    assert winner["selected"]["selection_high_finish_rate"] == 1
    assert winner["selected"]["evaluation"]["high_finish_rate"] == 0
    # Evaluation favors captain 1, but cannot retrospectively replace captain 0.
    rival = next(c for c in result["captains"] if c["captain_id"] == "1")
    assert rival["selected"]["evaluation"]["high_finish_rate"] == 1
