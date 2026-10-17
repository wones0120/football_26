"""Frozen-input Monday research. Run with python -m scripts.research_monday_game_simulation."""
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import argparse
import gzip
import hashlib
import html
import json

import numpy as np

from artifacts.all_games_captain_2026.backtest_lineups import dt, team, gamekey
from backend.app.product_services.captain_scenario_research import classify, metrics, lineup_scores, shortlist
from backend.app.product_services.research_game_simulation import (
    MODEL_ID, Assumptions, compare_lineups, enumerate_lineups, simulate_games,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts/captain_scenario_research"
HISTORY = ROOT / "artifacts/all_games_captain_2026/inputs"
DEFAULT_OUTPUT = ROOT / "artifacts/monday_game_simulation"


def read(path):
    return json.loads(gzip.open(path).read()) if path.suffix == ".gz" else json.loads(path.read_text())


def verify(folder):
    manifest = read(folder / "manifest.json")
    for name, digest in manifest["files_sha256"].items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Changed frozen source: {folder/name}")
    return manifest


def safe_time(value):
    # Existing captured PostgreSQL naive stat clocks are stored UTC.
    return dt(value).astimezone(timezone.utc)


def historical_weekly_eligible(row, schedule, *, cutoff, season, week):
    """Weekly source evidence after a past game's completion window, not stale score fields."""
    if not schedule or row['source_system'] != 'nflreadpy' or row['season'] != season or row['week'] >= week:
        return False
    if row['raw_row_json'].get('season_type') != 'REG' or schedule.get('game_type') != 'REG':
        return False
    raw = schedule['raw_row_json']
    if not raw.get('gameday') or not raw.get('gametime'):
        return False
    start = datetime.fromisoformat(f"{raw['gameday']}T{raw['gametime']}").replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)
    imported = safe_time(row['created_at'])
    return safe_time(schedule['created_at']) < cutoff and start+timedelta(hours=8) <= imported < cutoff


def assign_roles(eligible, universe):
    """Pregame opportunity roles; never inferred from simulation success or salary."""
    roles = {}
    for p in universe:
        members = [q for q in universe if q['team'] == p['team']]
        pos = p['position']
        if pos == 'QB':
            role = 'rushing QB' if p.get('carries', 0) >= 5 else 'pocket QB'
        elif pos == 'RB':
            rbs = sorted([q for q in members if q['position'] == 'RB'], key=lambda q: (-q.get('carries', 0), q['id']))
            lead = rbs and p['id'] == rbs[0]['id']
            role = ('lead' if lead else 'complementary') + (' receiving RB' if p.get('targets', 0) >= 2 else ' rushing RB')
        elif pos == 'WR':
            wrs = sorted([q for q in members if q['position'] == 'WR'], key=lambda q: (-q.get('targets', 0), q['id']))
            role = 'primary WR' if p in wrs[:2] and p.get('targets', 0) >= 3 else 'secondary WR' if p.get('targets', 0) >= 3 else 'low-volume WR'
        elif pos == 'TE':
            role = 'receiving TE' if p.get('targets', 0) >= 3 else 'low-volume TE'
        else:
            role = 'kicker' if pos == 'K' else 'defense'
        p['research_role'] = role
        roles[p['id']] = role
    for p in eligible:
        p['research_role'] = roles[p['id']]


def structure_key(players, lineup, *, roles=False):
    cap = next(p for p in players if p['id'] == lineup['captain_id'])
    counts = Counter()
    for i in lineup['indices']:
        p = players[i]
        if p['id'] == cap['id']:
            continue
        key = ('Captain team' if p['team'] == cap['team'] else 'Opponent', p['position'])
        if roles:
            key += (p.get('research_role', 'unclassified'),)
        counts[key] += 1
    return tuple(sorted((*k, n) for k, n in counts.items()))


def describe_structure(key):
    return '; '.join(f"{side}: " + ', '.join(f"{k[-1]} {k[1]}"+(f" ({k[2]})" if len(k) == 4 else '') for k in key if k[0] == side)
                     for side in ('Captain team', 'Opponent'))


def load_model():
    manifests = {str(p.relative_to(ROOT)): verify(p) for p in (
        SOURCE/"inputs", SOURCE/"feature_inputs_selected_v2", HISTORY)}
    snapshot = read(SOURCE/"inputs/monday.json")
    cutoff = safe_time(snapshot["projection_run"]["created_at"])
    kickoff = safe_time(snapshot["games"][0]["kickoff_at"])
    if cutoff >= kickoff:
        raise ValueError("Forecast cutoff must precede kickoff")
    for row in [snapshot["model"], *snapshot["projections"]]:
        for key in ("created_at", "data_cutoff_at", "training_cutoff"):
            if row.get(key) and safe_time(row[key]) > cutoff:
                raise ValueError("Future projection/model evidence")
    training_cutoff = snapshot["model"].get("params_json", {}).get("training_cutoff")
    if training_cutoff and safe_time(training_cutoff) > cutoff:
        raise ValueError("Future model training cutoff")
    features = {}
    for f in read(SOURCE/"feature_inputs_selected_v2/features.json.gz"):
        if f["feature_run_id"] != snapshot["model"]["feature_run_id"] or gamekey(f["game_id"]) != gamekey(snapshot["games"][0]["game_id"]):
            continue
        v = f["feature_json"]
        clocks = [f["created_at"], f.get("training_cutoff"), v.get("market_observed_at")]
        clocks += [value for key, value in v.items() if key.endswith("observed_at")]
        if any(value and safe_time(value) > cutoff for value in clocks):
            raise ValueError("Future feature evidence")
        if f["player_id"] in features:
            raise ValueError("Duplicate canonical feature row")
        features[f["player_id"]] = v
    aliases = defaultdict(set)
    for a in read(HISTORY/"aliases.json.gz"):
        aliases[(a["source_system"], str(a["source_key"]))].add(a["player_master_id"])
    schedules = {}
    for s in read(SOURCE/"inputs/schedule.json.gz"):
        if safe_time(s["created_at"]) < cutoff:
            schedules[gamekey(s["game_id"])] = s
    selected = {}
    rejected = Counter()
    for r in read(HISTORY/"stats.json.gz"):
        key = gamekey(r["game_id"])
        schedule = schedules.get(key)
        if not historical_weekly_eligible(r, schedule, cutoff=cutoff, season=snapshot['season'], week=snapshot['week']):
            rejected["outside_completed_pregame_window"] += 1
            continue
        ids = aliases[(r["source_system"], str(r["player_id"]))]
        if len(ids) != 1:
            rejected["unresolved_or_ambiguous_native_identity"] += 1
            continue
        pid = next(iter(ids))
        dedup = (key, pid)
        if dedup not in selected or safe_time(r["created_at"]) > safe_time(selected[dedup]["created_at"]):
            selected[dedup] = r
    histories = defaultdict(list)
    by_position = defaultdict(list)
    for (key, pid), row in selected.items():
        raw = row["raw_row_json"]
        histories[pid].append(raw)
        by_position[row["position"]].append(raw)

    def total(rows, key):
        return sum(float(r.get(key) or 0) for r in rows)

    def ratio(rows, numerator, denominator, fallback):
        denom = total(rows, denominator)
        return total(rows, numerator)/denom if denom else fallback

    # Shrink sparse individual rates toward observed 2026 position rates.
    def shrunk(pid, position, numerator, denominator, prior, fallback):
        base = ratio(by_position[position], numerator, denominator, fallback)
        rows = histories[pid]
        return (total(rows, numerator)+prior*base)/(total(rows, denominator)+prior)

    prices = {p["player_master_id"]: p["salary"] for p in snapshot["source_salaries"] if p["roster_position"] == "CPT"}
    ps, universe = [], []
    notes = []
    for p in snapshot["pool"]:
        pid, pos = p["player_id"], p["position"]
        if pid not in features:
            raise ValueError("Missing canonical pregame feature")
        v = features[pid]
        player = dict(id=pid, name=p["player_name"], team=team(p["team"]), position=pos,
                      salary=p["salary"], captain_salary=prices.get(pid, p["salary"]*1.5),
                      projected_mean=p["projection"], projected_p90=p["p90"],
                      captain_excluded=pid in snapshot["constraints"].get("flex_only_player_ids", []),
                      high_rushing=float(v.get("carries_mean_3") or 0) >= 5,
                      optimizer_eligible=bool(p["included"]), optimizer_exclusion_reasons=p.get("exclusion_reasons", []))
        if p["included"]:
            ps.append(deepcopy(player))
        # User preferences affect lineups only. Actual unavailable roles do not play.
        unavailable = str(v.get("availability_status") or p.get("pregame_injury_status") or "").upper() in ("OUT", "O", "IR", "PUP", "INACTIVE", "SUSPENDED") or v.get("model_availability_used") == 0
        starter = pid == v.get("team_starting_qb_player_id")
        if unavailable or pos == "QB" and not starter:
            continue
        def opportunity(primary, fallback):
            val = v.get(primary)
            if val is None:
                val = v.get(fallback)
            if val is None:
                notes.append(dict(player_id=pid, reason=f"Missing {primary}/{fallback}; zero opportunity assumed"))
                val = 0
            if not np.isfinite(val) or val < 0:
                raise ValueError("Invalid pregame opportunity")
            return float(val)
        player.update(targets=opportunity("projected_targets", "targets_mean_3") if pos in ("RB", "WR", "TE") else 0,
                      carries=opportunity("projected_carries", "carries_mean_3") if pos in ("QB", "RB", "WR", "TE") else 0,
                      catch_rate=float(np.clip(shrunk(pid, pos, "receptions", "targets", 20, .65), .3, .95)),
                      yards_per_catch=float(np.clip(shrunk(pid, pos, "receiving_yards", "receptions", 15, 10), 3, 22)),
                      yards_per_carry=float(np.clip(shrunk(pid, pos, "rushing_yards", "carries", 30, 4.3), 1, 8)),
                      goal_line_multiplier=1., is_starter=starter,
                      red_zone_target_multiplier=1.,
                      historical_games=len(histories[pid]), evidence=v)
        universe.append(player)
    home = next(p["team"] for p in universe if p["evidence"]["is_home"] == 1)
    teams = []
    for tm in (home, next(p["team"] for p in universe if p["team"] != home)):
        members = [p for p in universe if p["team"] == tm]
        qb = next(p for p in members if p["position"] == "QB" and p["is_starter"])
        qhist = histories[qb["id"]]
        qbbase = by_position["QB"]
        def qb_rate(num, denom, default):
            return shrunk(qb["id"], "QB", num, denom, 75, default)
        team_targets = float(qb["evidence"].get("team_targets_mean_3") or sum(p["targets"] for p in members))
        for role, amount in (("receiving", max(0, team_targets-sum(p["targets"] for p in members))),
                             ("rushing", max(0, float(qb["evidence"].get("team_carries_mean_3") or 0)-sum(p["carries"] for p in members)))):
            if amount > 0:
                bucket = dict(id=f"research_other_{tm}_{role}", name=f"Other {tm} {role}", team=tm, position="WR" if role == "receiving" else "RB",
                              targets=amount if role == "receiving" else 0, carries=amount if role == "rushing" else 0,
                              catch_rate=ratio(by_position["WR"], "receptions", "targets", .65),
                              yards_per_catch=ratio(by_position["WR"], "receiving_yards", "receptions", 10),
                              yards_per_carry=ratio(by_position["RB"], "rushing_yards", "carries", 4.3),
                              goal_line_multiplier=1., optimizer_eligible=False, aggregate_bucket=True)
                universe.append(bucket)
                members.append(bucket)
                notes.append(dict(team=tm, reason=f"Unallocated {role} opportunities preserved in a noneligible aggregate bucket", opportunities=amount))
        indices = {p["id"]: i for i, p in enumerate(universe)}
        receiver_ids = [indices[p["id"]] for p in members if p["targets"] > 0]
        runner_ids = [indices[p["id"]] for p in members if p["carries"] > 0]
        if not receiver_ids or not runner_ids:
            raise ValueError("Team needs receiving and rushing opportunities")
        kicker = next(p for p in members if p["position"] == "K")
        sack_base = total(qhist, "sacks_suffered")
        attempts = total(qhist, "attempts")
        league_sack = total(qbbase, "sacks_suffered")/max(1, total(qbbase, "attempts")+total(qbbase, "sacks_suffered"))
        sack_rate = (sack_base+75*league_sack)/(attempts+sack_base+75)
        total_carries = sum(p["carries"] for p in members)
        rush_fumbles = sum(total(by_position[pos], "rushing_fumbles_lost") for pos in ("RB", "QB", "WR", "TE"))
        rush_count = sum(total(by_position[pos], "carries") for pos in ("RB", "QB", "WR", "TE"))
        def_rows = [r["raw_row_json"] for r in selected.values() if team(r["team"]) == tm]
        turnovers = total(def_rows, "def_interceptions")+total(def_rows, "fumble_recovery_opp")
        league_pass_tds = total(by_position['QB'], 'passing_tds')
        league_rush_tds = sum(total(by_position[pos], 'rushing_tds') for pos in ('QB', 'RB', 'WR', 'TE', 'FB'))
        league_pass_share = league_pass_tds/max(1, league_pass_tds+league_rush_tds)
        team_pass_tds = total(def_rows, 'passing_tds')
        team_rush_tds = total(def_rows, 'rushing_tds')
        prior_tds = 4.
        target_pass_share = (team_pass_tds+prior_tds*league_pass_share)/(team_pass_tds+team_rush_tds+prior_tds)
        def scoring_shares(role_indices, volume_key, td_key):
            volumes = np.asarray([universe[i][volume_key] for i in role_indices])
            prior = volumes/volumes.sum()
            counts = np.asarray([total(histories[universe[i]['id']], td_key) for i in role_indices])
            # Only participating players get allocations; other-role buckets retain volume priors.
            return ((counts+prior_tds*prior)/(counts.sum()+prior_tds)).tolist()
        target_rush_shares = scoring_shares(runner_ids, 'carries', 'rushing_tds')
        target_receiving_shares = scoring_shares(receiver_ids, 'targets', 'receiving_tds')
        for inds, target_shares, weights, field in ((runner_ids, target_rush_shares, [universe[i]['carries'] for i in runner_ids], 'goal_line_multiplier'),
                                                   (receiver_ids, target_receiving_shares, [universe[i]['targets'] for i in receiver_ids], 'red_zone_target_multiplier')):
            base = np.asarray(weights)/sum(weights)
            for i, share, normal in zip(inds, target_shares, base):
                universe[i][field] = float(np.clip(share/normal, .05, 20))
        teams.append(dict(team=tm, qb=indices[qb["id"]], dst=indices[next(p["id"] for p in members if p["position"] == "DST")],
                          kicker=indices[kicker["id"]], receivers=receiver_ids, runners=runner_ids,
                          target_weights=[universe[i]["targets"] for i in receiver_ids], carry_weights=[universe[i]["carries"] for i in runner_ids],
                          pass_rate=team_targets/max(1, team_targets+total_carries),
                          completion_rate=qb_rate("completions", "attempts", .65), int_rate=float(np.clip(qb_rate("passing_interceptions", "attempts", .025), .003, .08)),
                          sack_rate=float(np.clip(sack_rate, .01, .15)), sack_yards=float(np.clip(abs(ratio(qhist, "sack_yards_lost", "sacks_suffered", 6.5)), 1, 15)),
                          fumble_rate=float(np.clip(rush_fumbles/max(1, rush_count), .002, .035)),
                          turnover_td_rate=float(np.clip(total(def_rows, "def_tds")/max(1, turnovers), 0, .2)),
                          pat_rate=shrunk(kicker["id"], "K", "pat_made", "pat_att", 10, .95),
                          fg_rate=shrunk(kicker["id"], "K", "fg_made", "fg_att", 10, .85),
                          punt_yards=float(np.clip(ratio(by_position["P"], "pt_yards", "pt_att", 45), 35, 55)),
                          implied_score=float(qb["evidence"]["team_implied_total"])))
        teams[-1].update(red_zone_pass_odds_multiplier=1., target_passing_td_share=float(target_pass_share),
                         target_rushing_td_shares=target_rush_shares, target_receiving_td_shares=target_receiving_shares,
                         touchdown_history=dict(passing_tds=team_pass_tds, rushing_tds=team_rush_tds, prior_tds=prior_tds,
                                                league_passing_td_share=league_pass_share))
    ps.sort(key=lambda p: p["id"])
    for p in ps:
        if p["id"] not in {u["id"] for u in universe}:
            raise ValueError("Eligible lineup player missing from simulated football universe")
    assign_roles(ps, universe)
    constraints = snapshot["constraints"]
    rules = dict(leader_ids=snapshot["leader_evidence"]["team_leader_preference"].get("required_player_ids", []),
                 single_te=constraints.get("enforce_single_te", False), no_two_qbs=constraints.get("no_two_qbs", False),
                 avoid_dst_opponents=constraints.get("avoid_dst_opponents", False), qb_correlations=True,
                 locked_ids=constraints.get("locked_player_ids", []))
    game = dict(game=snapshot["games"][0]["game_id"], home=home, cutoff=cutoff.isoformat(), kickoff=kickoff.isoformat(),
                players=ps, rules=rules, source_optimizer_run_id=snapshot["optimizer_run_id"], projection_run_id=snapshot["projection_run_id"])
    lineage = dict(manifests=manifests, history_rows=len(selected), history_games=len({k[0] for k in selected}),
                   history_max_imported_at=max(safe_time(r["created_at"]).isoformat() for r in selected.values()),
                   rejected_rows=dict(rejected), input_notes=notes, naive_stat_clock_basis="UTC, matching existing capture convention",
                   history_policy='Earlier-week REG nflreadpy weekly actuals imported after scheduled kickoff + 8h and before forecast cutoff; final-score fields not required',
                   history_by_player={pid:sorted({r['week'] for (key, p), r in selected.items() if p == pid}) for pid in histories},
                   history_keys_sha256=hashlib.sha256(json.dumps(sorted(str(k) for k in selected)).encode()).hexdigest())
    return game, dict(players=universe, teams=teams), lineage


def calibrate(model, assumptions, seed):
    efficiency = np.ones(2)
    target = np.asarray([t["implied_score"] for t in model["teams"]])
    history = []
    for iteration in range(assumptions.calibration_iterations):
        _, _, audit = simulate_games(model, draws=assumptions.calibration_draws, seed=seed,
                                     assumptions=assumptions, efficiency=efficiency)
        observed = np.asarray(audit["mean_scores"])
        stats = {s['player_id']:s for s in audit['player_mean_stats']}
        td_checks = []
        for t in model['teams']:
            def mean_td(i, field):return stats[model['players'][i]['id']][field]
            pass_tds = mean_td(t['qb'], 'passing_tds')
            rush_tds = sum(mean_td(i, 'rushing_tds') for i in t['runners'])
            share = pass_tds/max(.001, pass_tds+rush_tds)
            td_checks.append(dict(team=t['team'], passing_td_share=share, target=t['target_passing_td_share'],
                                  pass_odds_multiplier=t['red_zone_pass_odds_multiplier']))
            target_share = t['target_passing_td_share']
            odds_ratio = (target_share/(1-target_share))/(np.clip(share, .03, .97)/(1-np.clip(share, .03, .97)))
            t['red_zone_pass_odds_multiplier'] = float(np.clip(t['red_zone_pass_odds_multiplier']*odds_ratio**.8, .02, 20))
            for inds, desired, field, stat_key in ((t['runners'], t['target_rushing_td_shares'], 'goal_line_multiplier', 'rushing_tds'),
                                                   (t['receivers'], t['target_receiving_td_shares'], 'red_zone_target_multiplier', 'receiving_tds')):
                counts = np.asarray([mean_td(i, stat_key) for i in inds])
                # A small pilot pseudocount avoids explosive updates from rare zero-TD roles.
                counts = counts*assumptions.calibration_draws + np.asarray(desired)*5
                actual_shares = counts/counts.sum()
                for i, desired_share, actual_share in zip(inds, desired, actual_shares):
                    p = model['players'][i]
                    p[field] = float(np.clip(p[field]*(desired_share/max(.0001, actual_share))**.6, .02, 40))
        history.append(dict(iteration=iteration, efficiency=efficiency.tolist(), observed_scores=observed.tolist(), touchdown_checks=td_checks))
        efficiency = np.clip(efficiency*(target/np.maximum(observed, 1))**.5, .6, 1.8)
    return efficiency, dict(target_scores=target.tolist(), seed=seed, iterations=history,
                           method="Separate pilot fits market mean scores, shrunk historical team passing/rushing TD shares, and participating player scoring shares through red-zone play and role odds; no relabeled TDs or fantasy-point rescaling")


def research(*, draws=5000, seed=20261012, assumptions=Assumptions()):
    if draws < 200 or not 0 <= seed <= 2**32-4:
        raise ValueError("Use at least 200 draws and a valid seed")
    game, model, lineage = load_model()
    lineups = enumerate_lineups(game)
    efficiency, calibration = calibrate(model, assumptions, seed+2)
    index = {p["id"]: i for i, p in enumerate(model["players"])}
    columns = [index[p["id"]] for p in game["players"]]
    selection, _, sa = simulate_games(model, draws=draws, seed=seed, assumptions=assumptions, efficiency=efficiency)
    selection = selection[:, columns]
    rates, means, sel_threshold = compare_lineups(selection, game, lineups)
    # Freeze every winning index before generating evaluation outcomes.
    winners, baselines = {}, {}
    for cap in shortlist(game["players"]):
        family = [j for j, l in enumerate(lineups) if l["captain_id"] == cap]
        if family:
            winners[cap] = max(family, key=lambda j: (rates[j], means[j], -j))
            baselines[cap] = max(family, key=lambda j: sum(game["players"][i]["projected_mean"] for i in lineups[j]["indices"]))
    overall_winner = max(winners, key=lambda cap: (rates[winners[cap]], means[winners[cap]], -winners[cap]))
    first_rates, first_means, _ = compare_lineups(selection[:draws//2], game, lineups)
    second_rates, second_means, _ = compare_lineups(selection[draws//2:], game, lineups)
    evaluation, labels, ea = simulate_games(model, draws=draws, seed=seed+1, assumptions=assumptions, efficiency=efficiency)
    evaluation = evaluation[:, columns]
    eval_rates, eval_means, threshold = compare_lineups(evaluation, game, lineups)
    captain_reports = []
    def attach(j):
        l = deepcopy(lineups[j])
        l["selection_high_finish_rate"] = float(rates[j])
        l["evaluation"] = metrics(lineup_scores(evaluation, game["players"], l), labels, threshold)
        l["players"] = [dict(game["players"][i], slot="CPT" if game["players"][i]["id"] == l["captain_id"] else "FLEX") for i in l["indices"]]
        l["salary"] = sum(p["captain_salary"] if p["slot"] == "CPT" else p["salary"] for p in l["players"])
        return l
    for cap in shortlist(game["players"]):
        family = [j for j, l in enumerate(lineups) if l["captain_id"] == cap]
        name = next(p["name"] for p in game["players"] if p["id"] == cap)
        if not family:
            captain_reports.append(dict(captain_id=cap, name=name, feasible=False, legal_count=0))
            continue
        selected = winners[cap]
        baseline = baselines[cap]
        half_winners = [max(family, key=lambda j: (rs[j], ms[j], -j)) for rs, ms in ((first_rates, first_means), (second_rates, second_means))]
        chosen = attach(selected)
        structures = {}
        for label, use_roles in (('position_team', False), ('position_team_role', True)):
            grouped = defaultdict(list)
            for j in family:
                grouped[structure_key(game['players'], lineups[j], roles=use_roles)].append(j)
            entries = []
            for key, members in grouped.items():
                representative = max(members, key=lambda j: (rates[j], means[j], -j))
                entries.append(dict(structure=describe_structure(key), key=[list(k) for k in key], roster_count=len(members),
                                    selection_average_high_finish_rate=float(rates[members].mean()),
                                    evaluation_average_high_finish_rate=float(eval_rates[members].mean()),
                                    evaluation_high_finish_range=[float(eval_rates[members].min()), float(eval_rates[members].max())],
                                    evaluation_average_points=float(eval_means[members].mean()),
                                    representative=attach(representative), supported=len(members) >= 3))
            entries.sort(key=lambda s: (-s['selection_average_high_finish_rate'], -s['roster_count'], s['structure']))
            supported_structures = [s for s in entries if s['supported']]
            structures[label] = dict(all=entries, top=(supported_structures or entries)[:5],
                                     ranking='Selection-sample average high-finish rate across every legal roster in structure; prefer support of at least three rosters',
                                     selected_roster_structure=describe_structure(structure_key(game['players'], lineups[selected], roles=use_roles)))
        # Strongest scenario selected on SELECTION games only.
        sel_labels = classify(sa["scores"])
        sel_metrics = metrics(lineup_scores(selection, game["players"], chosen), sel_labels, sel_threshold)
        supported = [s for s in sel_metrics["scenarios"] if s["samples"] >= 50]
        strongest = max(supported, key=lambda s: (s["high_finish_rate"], s["samples"]))["scenario"] if supported else None
        captain_reports.append(dict(captain_id=cap, name=name, feasible=True, legal_count=len(family),
                                    selected=chosen, unrestricted_mean=attach(baseline),
                                    strongest_scenario_selected_on_training=strongest,
                                    selection_half_winners=[lineups[j] for j in half_winners],
                                    structures=structures,
                                    selection_halves_agree=half_winners[0] == half_winners[1]))
    diagnostics = [dict(player_id=p["id"], name=p["name"], projected_mean=p["projected_mean"],
                        simulated_mean=float(evaluation[:, i].mean()), simulated_p90=float(np.quantile(evaluation[:, i], .9)),
                        mean_gap=float(evaluation[:, i].mean()-p["projected_mean"])) for i, p in enumerate(game["players"])]
    return dict(model_id=MODEL_ID, game=game, parameters=dict(draws_per_sample=draws, seed=seed, assumptions=asdict(assumptions)),
                lineage=lineage, football_model=model, calibration=calibration, selection_audit=sa, evaluation_audit=ea,
                legal_lineup_count=len(lineups), legal_pool_sha256=hashlib.sha256(json.dumps(lineups, sort_keys=True).encode()).hexdigest(),
                structure_role_policy=dict(qb_rushing_carries_min=5, rb_receiving_targets_min=2, wr_primary='Top two team WRs with at least three projected targets',
                                           wr_secondary_targets_min=3, te_receiving_targets_min=3, rb_lead='Highest projected carries among team RBs', minimum_structure_rosters=3),
                selected_captain=overall_winner, captains=captain_reports, player_diagnostics=diagnostics,
                scenario_probabilities=metrics(np.zeros(draws), labels, np.ones(draws))["scenarios"],
                limitations=["Experimental, uncalibrated player/lineup probabilities; not probability of getting paid.",
                             "Weekly aggregates fit completion, yards and turnover rates; play clocks, score response, yard distribution, field position and workload variation are explicit research assumptions, not fitted play-by-play coefficients.",
                             "Simplified punts, touchbacks, fourth-down decisions, kneel-out and overtime; no penalties, timeouts, onside kicks, injuries during play, blocked kicks or special-teams return touchdowns.",
                             "Player football production is not forced to match saved fantasy mean/P90. Projection gaps are reported, not hidden by rescaling fantasy outcomes.",
                             "Questionable players participate under the saved available-role assumption even when excluded from lineups; availability uncertainty is not yet modeled.",
                             "Pilot aligns market score means and shrunk historical TD/role shares; no historical walk-forward validation of this model has been established.",
                             "Structure averages are uniform across legal rosters in this fixed pool, not causal position effects or a contest ownership distribution. Roles use pregame opportunity thresholds; groups with fewer than three rosters are marked sparse.",
                             "High finish means meeting the 95th-percentile score among ALL legal lineups within the retained player pool and four-captain shortlist, including ties; no ownership, field or payout model."])


def render(r):
    def table(headers, rows):
        return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'
    pct = lambda v: f"{100*v:.1f}%"
    body = '<h1>Monday night: football game simulation research</h1><p>BUF @ LAR · Frozen pregame inputs · Experimental research model</p><p><b>These are model comparisons, not calibrated forecasts or probabilities of getting paid.</b></p>'
    body += '<h2>How it works</h2><p>Simulate the game first: possessions, down, distance, field position, clock, passes, rushes, sacks, turnovers, touchdowns and kicks. Leading/trailing teams change play selection. A completed pass credits the same yards to the quarterback and receiver. Every player’s fantasy points come from those events.</p><p>Enumerate every legal FLEX combination for the top-four eligible P90 captains, including QBs. Compare all lineups on the same selection games, freeze one lineup per captain, then evaluate on separate games. Scenarios emerge from the final score; no future scenario is revealed when choosing a lineup.</p>'
    body += '<p>Six unique players, $50,000 cap, 4–2 team split, captain salary/points ×1.5, plus saved locks, season-leader, QB-stack, DST and optional TE/QB constraints. Portfolio quality floors and multi-entry exposures do not reject individual research lineups.</p>'
    body += f'<p>{r["legal_lineup_count"]:,} legal lineups · {r["parameters"]["draws_per_sample"]:,} selection games + the same number of independent evaluation games · {r["lineage"]["history_games"]} historical games supplying pregame rates.</p>'
    rows = []
    for c in r['captains']:
        if not c['feasible']:
            rows.append((c['name'], 0, 'Infeasible', 'Infeasible', '—', '—'))
            continue
        b, s = c['unrestricted_mean']['evaluation'], c['selected']['evaluation']
        rows.append((c['name'], c['legal_count'], pct(b['high_finish_rate']), pct(s['high_finish_rate']), f"{s['mean']:.2f}", c['selection_halves_agree']))
    body += '<h2>Independent evaluation: lineup chosen before outcomes</h2>'+table(['Captain', 'Legal FLEX combinations', 'Mean-FLEX high finish', 'Simulation-selected high finish', 'Selected simulated mean', 'Selection halves chose same roster'], rows)
    body += '<p>High finish = meeting the top-5% score threshold across the complete legal pool restricted to these captains, including ties. The baseline for each captain maximizes saved FLEX mean; the new method searches the entire same legal pool using simulated competitive performance.</p>'
    body += '<p>Role labels use pregame opportunities: rushing QB = 5+ carries; receiving RB = 2+ targets; lead RB = highest team RB carries; primary WR = top two team WRs with 3+ targets; secondary WR/receiving TE = 3+ targets. Roles are research classifications, not position mandates. DST avoidance combined with a 4–2 split leaves no legal DST-containing lineups here, so this run cannot evaluate RB–DST structures.</p>'
    body += '<h2>History and touchdown corrections</h2><p>Past-week weekly actuals are admitted only when the scheduled game and original import clocks precede the forecast cutoff, with an eight-hour post-kickoff completion window. Stale final-score fields no longer discard Week 4. A separate pilot fits red-zone pass/rush odds and scoring-role weights to historical touchdown shares shrunk toward league/volume priors. Scores and fantasy points still come from football events; saved projections are not forced into the simulation.</p>'
    audit_stats = {s['player_id']:s for s in r['evaluation_audit']['player_mean_stats']}
    td_rows = []
    for t in r['football_model']['teams']:
        qb = r['football_model']['players'][t['qb']]
        passing = audit_stats[qb['id']]['passing_tds']
        rushing = sum(audit_stats[r['football_model']['players'][i]['id']]['rushing_tds'] for i in t['runners'])
        td_rows.append((t['team'], ', '.join(str(w) for w in r['lineage']['history_by_player'][qb['id']]),
                        pct(t['target_passing_td_share']), pct(passing/(passing+rushing)), f"{passing:.2f}", f"{rushing:.2f}"))
    body += table(['Team', 'QB history weeks', 'Fitted target passing TD share', 'Evaluation passing TD share', 'Passing TD/game', 'Rushing TD/game'], td_rows)
    for c in r['captains']:
        if not c['feasible']:
            continue
        s = c['selected']
        body += '<h2>'+html.escape(c['name'])+' — lineup structures</h2><p>These structures were ranked on selection games by the average high-finish rate across every legal roster in the group. The tables show separate evaluation results. Groups with at least three rosters are preferred; a strong representative alone does not establish a strong structure.</p>'
        for kind, title in [('position_team', 'Position and team'), ('position_team_role', 'Position, team and pregame role')]:
            body += '<h3>'+title+'</h3>'+table(['FLEX structure', 'Legal rosters', 'Support', 'Selection group average', 'Evaluation group average', 'Fixed representative evaluation', 'Evaluation range across group'],
                  [(st['structure'], st['roster_count'], '3+ rosters' if st['supported'] else 'Sparse — cannot generalize', pct(st['selection_average_high_finish_rate']), pct(st['evaluation_average_high_finish_rate']), pct(st['representative']['evaluation']['high_finish_rate']), '–'.join(pct(v) for v in st['evaluation_high_finish_range'])) for st in c['structures'][kind]['top']])
        body += '<p>Structure of the selected individual lineup: '+html.escape(c['structures']['position_team_role']['selected_roster_structure'])+'</p>'
        body += '<h2>'+html.escape(c['name'])+' — selected lineup</h2><p>Salary $'+str(int(s['salary']))+' · Strongest scenario identified on selection games: '+html.escape(str(c['strongest_scenario_selected_on_training']))+'</p>'
        body += table(['Slot', 'Player', 'Team', 'Pregame role', 'Base mean', 'Base P90'], [(p['slot'], p['name'], p['team'], p['research_role'], f"{p['projected_mean']:.2f}", f"{p['projected_p90']:.2f}") for p in s['players']])
        body += table(['Scenario', 'Evaluation probability', 'Evaluation draws', 'Selected conditional high finish'], [(s['scenario'], pct(s['probability']), s['samples'], pct(s['high_finish_rate']) if s['samples'] else 'Insufficient samples') for s in c['selected']['evaluation']['scenarios']])
    body += '<h2>Football score and volume checks</h2>'+table(['Team', 'Saved market implied score', 'Evaluation mean score'], [(t['team'], f"{t['implied_score']:.2f}", f"{r['evaluation_audit']['mean_scores'][i]:.2f}") for i, t in enumerate(r['football_model']['teams'])])
    body += '<p>Mean offensive plays per game: '+f"{r['evaluation_audit']['mean_volumes'][0]:.1f}"+'. Passing yards, completions and touchdowns reconcile to receivers; team scores reconcile to scoring events in every generated game. These checks establish accounting consistency, not predictive accuracy.</p>'
    body += '<h2>Player calibration gaps</h2><p>Saved projections remain unchanged. Large gaps indicate football parameters needing validation before trusting the lineup ranking.</p>'+table(['Player', 'Saved projected mean', 'Simulated mean', 'Mean gap', 'Simulated P90'], [(d['name'], f"{d['projected_mean']:.2f}", f"{d['simulated_mean']:.2f}", f"{d['mean_gap']:+.2f}", f"{d['simulated_p90']:.2f}") for d in r['player_diagnostics']])
    mean_stats = {p['player_id']: p for p in r['evaluation_audit']['player_mean_stats']}
    body += '<h2>Simulated player football production</h2>'+table(['Player', 'Pass attempts', 'Pass yards', 'Pass TD', 'Targets', 'Catches', 'Receiving yards', 'Receiving TD', 'Carries', 'Rush yards', 'Rush TD'], [(p['name'], *[f"{mean_stats[p['id']][k]:.2f}" for k in ('attempts', 'passing_yards', 'passing_tds', 'targets', 'receptions', 'receiving_yards', 'receiving_tds', 'carries', 'rushing_yards', 'rushing_tds')]) for p in r['game']['players'] if p['position'] in ('QB', 'RB', 'WR', 'TE')])
    body += '<h2>Assumptions and limits</h2><ul>'+''.join('<li>'+html.escape(v)+'</li>' for v in r['limitations'])+'</ul><p>Frozen source hashes, canonical identities, seeds, assumptions, example game events, model inputs and lineup selections are retained in report.json. Production optimization is not called or modified.</p>'
    return '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Monday game simulation research</title><style>body{font:16px system-ui;background:#f4f6fa;color:#182336;max-width:1100px;margin:32px auto;padding:0 20px;line-height:1.55}h1,h2{line-height:1.2}table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;padding:10px;border-bottom:1px solid #dde3ec}th{background:#e3eaf5}.scroll{overflow:auto;margin:16px 0}</style></head><body>'+body+'</body></html>'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--draws', type=int, default=5000)
    parser.add_argument('--seed', type=int, default=20261012)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.draws < 200 or not 0 <= args.seed <= 2**32-4:
        parser.error('Use at least 200 draws and a valid seed')
    print('Building frozen-input football model and enumerating legal lineups', flush=True)
    r = research(draws=args.draws, seed=args.seed)
    r['code_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(), ROOT/'backend/app/product_services/research_game_simulation.py', ROOT/'backend/app/product_services/captain_scenario_research.py')}
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output/'report.json').exists() or (args.output/'report.html').exists():
        raise ValueError('Output exists; choose a fresh --output directory to preserve research runs')
    (args.output/'report.json').write_text(json.dumps(r, indent=2)+'\n')
    (args.output/'report.html').write_text(render(r))
    print(json.dumps(dict(output=str(args.output), legal_lineups=r['legal_lineup_count'], captains=[dict(name=c['name'], legal=c['legal_count'], baseline=c['unrestricted_mean']['evaluation']['high_finish_rate'], selected=c['selected']['evaluation']['high_finish_rate']) for c in r['captains'] if c['feasible']]), indent=2), flush=True)


if __name__ == '__main__':
    main()
