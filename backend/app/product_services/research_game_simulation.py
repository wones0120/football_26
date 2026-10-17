"""Offline event-driven football research; never called by production optimization."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import combinations
import hashlib

import numpy as np

from backend.app.product_services.captain_scenario_research import classify, legal, shortlist
from backend.app.services.simulation import calculate_dk_points

MODEL_ID = "research_possession_play_v2"
STAT_KEYS = ("attempts", "completions", "passing_yards", "passing_tds",
             "passing_interceptions", "targets", "receptions", "receiving_yards",
             "receiving_tds", "carries", "rushing_yards", "rushing_tds", "fumbles_lost",
             "sacks", "interceptions", "recoveries", "defensive_tds", "safeties",
             "fg_short", "fg_medium", "fg_long", "pat_made", "points_allowed")


@dataclass(frozen=True)
class Assumptions:
    """Explicit research assumptions, not fitted play-by-play estimates."""
    completion_seconds: float = 35
    incomplete_seconds: float = 12
    hurry_seconds: float = 18
    hurry_window: int = 600
    lead_pass_adjustment: float = .006
    trailing_hurry_adjustment: float = .08
    game_efficiency_sigma: float = .14
    game_pace_sigma: float = .08
    workload_concentration: float = 80
    yard_gamma_shape: float = 1.2
    negative_rush_probability: float = .14
    negative_catch_probability: float = .04
    overtime_seconds: int = 600
    calibration_draws: int = 800
    calibration_iterations: int = 5


def _choose(rng, weights):
    u = rng.random() * sum(weights)
    for i, w in enumerate(weights):
        if w <= 0:
            continue
        u -= w
        if u <= 0:
            return i
    return len(weights) - 1


def _shares(rng, weights, concentration):
    weights = np.asarray(weights, dtype=float)
    if not np.isfinite(weights).all() or (weights < 0).any() or weights.sum() <= 0:
        raise ValueError("Opportunity weights need positive finite total")
    positive = weights > 0
    out = np.zeros(len(weights))
    out[positive] = rng.dirichlet(weights[positive] / weights.sum() * concentration)
    return out.tolist()


def dst_points(row):
    pa = row["points_allowed"]
    bonus = 10 if pa == 0 else 7 if pa <= 6 else 4 if pa <= 13 else 1 if pa <= 20 else 0 if pa <= 27 else -1 if pa <= 34 else -4
    return row["sacks"] + 2 * (row["interceptions"] + row["recoveries"] + row["safeties"]) + 6 * row["defensive_tds"] + bonus


def fantasy_points(player, row):
    if player["position"] == "DST":
        return float(dst_points(row))
    return calculate_dk_points(row, floor_at_zero=False) + 3 * row["fg_short"] + 4 * row["fg_medium"] + 5 * row["fg_long"] + row["pat_made"]


def play_game(model, *, rng, assumptions=Assumptions(), efficiency=(1., 1.), trace=False):
    """One clock/down/distance game; paired passing/receiving statistics by event."""
    players = model["players"]
    stats = [{k: 0 for k in STAT_KEYS} for _ in players]
    teams = model["teams"]
    score = [0, 0]
    events = []
    shared_pace = float(rng.lognormal(-assumptions.game_pace_sigma**2/2, assumptions.game_pace_sigma))
    strengths = rng.lognormal(-assumptions.game_efficiency_sigma**2/2, assumptions.game_efficiency_sigma, 2) * efficiency
    target_weights = [_shares(rng, t["target_weights"], assumptions.workload_concentration) for t in teams]
    carry_weights = [_shares(rng, t["carry_weights"], assumptions.workload_concentration) for t in teams]
    first = int(rng.integers(2))
    total_plays = 0
    possessions = [0, 0]
    safety_count = [0, 0]

    def add_points(side, points, *, offensive=True):
        score[side] += points
        if offensive:
            stats[teams[1-side]["dst"]]["points_allowed"] += points

    def conversion(side, clock):
        kicker = teams[side]["kicker"]
        # Late deficits of 2/5/8 points trigger a two-point try.
        if clock < 600 and score[side]-score[1-side] in (-2, -5, -8):
            if rng.random() < .48:
                if rng.random() < teams[side]["pass_rate"]:
                    receiver = teams[side]["receivers"][_choose(rng, target_weights[side])]
                    for i, key in ((teams[side]["qb"], "passing_2pt_conversions"), (receiver, "receiving_2pt_conversions")):
                        stats[i][key] = stats[i].get(key, 0) + 1
                else:
                    runner = teams[side]["runners"][_choose(rng, carry_weights[side])]
                    stats[runner]["rushing_2pt_conversions"] = stats[runner].get("rushing_2pt_conversions", 0) + 1
                add_points(side, 2)
        elif rng.random() < teams[side]["pat_rate"]:
            stats[kicker]["pat_made"] += 1
            add_points(side, 1)

    def period(side, seconds, *, overtime=False):
        nonlocal total_plays
        clock, pos, down, distance = float(seconds), 30, 1, 10
        ot_possessions = [0, 0]
        possessions[side] += 1
        while clock > 0:
            own, defense = teams[side], teams[1-side]
            qb, dst = own["qb"], defense["dst"]
            lead = score[side] - score[1-side]
            # Simplified kneel-out assumes no remaining defensive timeouts.
            if not overtime and seconds == 1800 and lead > 0 and clock <= 35 and halftime == 1:
                break
            hurry = lead < 0 and clock < assumptions.hurry_window
            # A fourth down can end a drive without an offensive stat play.
            kick_now = down == 4 and pos >= 60 and not (hurry and clock < 180 and lead <= -4)
            punt_now = down == 4 and not kick_now and not (hurry and clock < 180 or distance <= 2 and pos >= 45)
            end = None
            turnover_kind = None
            gain = 0
            kind = ""
            actor, receiver = None, None
            start_pos, start_down, start_distance = pos, down, distance
            consumed = assumptions.completion_seconds
            if kick_now:
                kind = "field_goal"
                actor = own["kicker"]
                kick_distance = 117 - pos
                base = own["fg_rate"]
                probability = float(np.clip(base - .012 * max(0, kick_distance-40), .25, .99))
                if rng.random() < probability:
                    stats[own["kicker"]]["fg_short" if kick_distance < 40 else "fg_medium" if kick_distance < 50 else "fg_long"] += 1
                    add_points(side, 3)
                    end = (1-side, 30)
                else:
                    end = (1-side, max(20, 108-pos))
                consumed = 5
            elif punt_now:
                kind = "punt"
                landing = pos + int(np.clip(rng.normal(own["punt_yards"], 8), 20, 70))
                end = (1-side, 20 if landing >= 100 else 100-landing)
                consumed = 8
            else:
                total_plays += 1
                pass_probability = float(np.clip(own["pass_rate"] - assumptions.lead_pass_adjustment*lead + (assumptions.trailing_hurry_adjustment if hurry else 0) + (.16 if down >= 3 and distance >= 6 else 0), .15, .9))
                if pos >= 80:
                    odds = pass_probability/(1-pass_probability) * own.get("red_zone_pass_odds_multiplier", 1.)
                    pass_probability = float(np.clip(odds/(1+odds), .02, .95))
                passing = rng.random() < pass_probability
                if passing:
                    actor = qb
                    if rng.random() < own["sack_rate"]:
                        kind = "sack"
                        gain = -int(np.clip(rng.gamma(2, own["sack_yards"]/2), 1, 20))
                        stats[dst]["sacks"] += 1
                    else:
                        stats[qb]["attempts"] += 1
                        receiving_weights = target_weights[side]
                        if pos >= 80:
                            receiving_weights = [w * players[i].get("red_zone_target_multiplier", 1.) for i, w in zip(own["receivers"], receiving_weights)]
                        receiver = own["receivers"][_choose(rng, receiving_weights)]
                        stats[receiver]["targets"] += 1
                        if rng.random() < own["int_rate"]:
                            kind = "interception"
                            stats[qb]["passing_interceptions"] += 1
                            stats[dst]["interceptions"] += 1
                            turnover_kind = "interception"
                        elif rng.random() < np.clip((players[receiver]["catch_rate"] + own["completion_rate"])/2, .3, .95):
                            kind = "completion"
                            gain = int(round(rng.gamma(assumptions.yard_gamma_shape, players[receiver]["yards_per_catch"] * strengths[side]/assumptions.yard_gamma_shape)))
                            if rng.random() < assumptions.negative_catch_probability:
                                gain = -int(rng.integers(1, 4))
                            gain = min(gain, 100-pos)
                            stats[qb]["completions"] += 1
                            stats[qb]["passing_yards"] += gain
                            stats[receiver]["receptions"] += 1
                            stats[receiver]["receiving_yards"] += gain
                            if pos+gain >= 100:
                                stats[qb]["passing_tds"] += 1
                                stats[receiver]["receiving_tds"] += 1
                            elif rng.random() < own["fumble_rate"]:
                                stats[receiver]["fumbles_lost"] += 1
                                stats[dst]["recoveries"] += 1
                                turnover_kind = "fumble"
                        else:
                            kind = "incomplete"
                            consumed = assumptions.incomplete_seconds
                else:
                    kind = "rush"
                    weights = carry_weights[side]
                    if pos >= 90:
                        weights = [w * players[i]["goal_line_multiplier"] for i, w in zip(own["runners"], weights)]
                    runner = own["runners"][_choose(rng, weights)]
                    actor = runner
                    gain = int(round(rng.gamma(assumptions.yard_gamma_shape, players[runner]["yards_per_carry"] * strengths[side]/assumptions.yard_gamma_shape)))
                    if rng.random() < assumptions.negative_rush_probability:
                        gain = -int(rng.integers(1, 4))
                    gain = min(gain, 100-pos)
                    stats[runner]["carries"] += 1
                    stats[runner]["rushing_yards"] += gain
                    if pos+gain >= 100:
                        stats[runner]["rushing_tds"] += 1
                    elif rng.random() < own["fumble_rate"]:
                        stats[runner]["fumbles_lost"] += 1
                        stats[dst]["recoveries"] += 1
                        turnover_kind = "fumble"
                if pos+gain >= 100:
                    add_points(side, 6)
                    conversion(side, clock)
                    end = (1-side, 30)
                elif pos+gain <= 0:
                    # Safeties are points surrendered by the offense, not DST PA.
                    add_points(1-side, 2, offensive=False)
                    safety_count[1-side] += 1
                    stats[dst]["safeties"] += 1
                    end = (1-side, 30)
                elif turnover_kind:
                    if rng.random() < defense["turnover_td_rate"]:
                        stats[dst]["defensive_tds"] += 1
                        add_points(1-side, 6, offensive=False)
                        # Conversion after defensive TD is also excluded from PA.
                        if rng.random() < defense["pat_rate"]:
                            stats[defense["kicker"]]["pat_made"] += 1
                            add_points(1-side, 1, offensive=False)
                        end = (side, 30)
                    else:
                        end = (1-side, int(np.clip(100-pos-gain, 1, 99)))
                else:
                    pos += gain
                    if gain >= distance:
                        down, distance = 1, min(10, 100-pos)
                    else:
                        down += 1
                        distance -= gain
                    if down == 5:
                        end = (1-side, 100-pos)
                if hurry and kind != "incomplete":
                    consumed = assumptions.hurry_seconds
            if trace:
                events.append(dict(side=side, half=halftime+1 if not overtime else "OT", clock=clock,
                                   field_position=start_pos, down=start_down, distance=start_distance,
                                   kind=kind, actor_id=players[actor]["id"] if actor is not None else None,
                                   receiver_id=players[receiver]["id"] if receiver is not None else None,
                                   gain=gain, score=score.copy()))
            clock -= consumed/shared_pace
            if end:
                ot_possessions[side] += 1
                if overtime and min(ot_possessions) >= 1 and score[0] != score[1]:
                    break
                side, pos = end
                down, distance = 1, min(10, 100-pos)
                possessions[side] += 1
        return side

    for halftime in range(2):
        period(first if halftime == 0 else 1-first, 1800)
    overtime = score[0] == score[1]
    if overtime:
        period(int(rng.integers(2)), assumptions.overtime_seconds, overtime=True)
    outcomes = [fantasy_points(p, row) for p, row in zip(players, stats)]
    # Every completed pass and touchdown has one receiver, including noneligible buckets.
    for side, own in enumerate(teams):
        qb = stats[own["qb"]]
        assert qb["passing_yards"] == sum(stats[i]["receiving_yards"] for i in own["receivers"])
        assert qb["passing_tds"] == sum(stats[i]["receiving_tds"] for i in own["receivers"])
        assert qb["completions"] == sum(stats[i]["receptions"] for i in own["receivers"])
        offensive_tds = qb["passing_tds"] + sum(stats[i]["rushing_tds"] for i in own["runners"])
        own_dst = stats[own["dst"]]
        kicking = stats[own["kicker"]]
        twos = sum(stats[i].get("rushing_2pt_conversions", 0)+stats[i].get("receiving_2pt_conversions", 0) for i in set(own["runners"]+own["receivers"]))
        assert score[side] == 6*(offensive_tds+own_dst["defensive_tds"]) + 3*sum(kicking[k] for k in ("fg_short", "fg_medium", "fg_long")) + kicking["pat_made"] + 2*(twos+safety_count[side])
    return dict(points=outcomes, scores=score, stats=stats, plays=total_plays,
                possessions=possessions, overtime=overtime, events=events)


def simulate_games(model, *, draws, seed, assumptions=Assumptions(), efficiency=(1., 1.)):
    if draws < 1 or not 0 <= seed < 2**32:
        raise ValueError("Invalid draw count or seed")
    rng = np.random.default_rng(seed)
    points, scores, volumes = [], [], []
    stat_totals = [dict() for _ in model["players"]]
    sample = None
    for n in range(draws):
        g = play_game(model, rng=rng, assumptions=assumptions, efficiency=efficiency, trace=n == 0)
        points.append(g["points"])
        scores.append(g["scores"])
        volumes.append([g["plays"], *g["possessions"], int(g["overtime"])])
        for i, row in enumerate(g["stats"]):
            for k, v in row.items():
                stat_totals[i][k] = stat_totals[i].get(k, 0) + v
        if n == 0:
            sample = g
    points, scores = np.asarray(points), np.asarray(scores)
    return points, classify(scores), dict(scores=scores.tolist(), seed=seed, draws=draws,
        assumptions=asdict(assumptions), efficiency=list(efficiency),
        mean_scores=scores.mean(axis=0).tolist(), mean_volumes=np.mean(volumes, axis=0).tolist(),
        player_mean_stats=[dict(player_id=p["id"], **{k: v/draws for k, v in stat_totals[i].items()}) for i, p in enumerate(model["players"])],
        sample_game=sample, draws_sha256=hashlib.sha256(points.tobytes()+scores.tobytes()).hexdigest())


def enumerate_lineups(game):
    """Exhaustive legal FLEX search, independent of all simulated outcomes."""
    ps = game["players"]
    found = []
    for cap in shortlist(ps):
        ci = next(i for i, p in enumerate(ps) if p["id"] == cap)
        for flex in combinations([i for i in range(len(ps)) if i != ci], 5):
            indices = sorted((ci, *flex))
            if legal([ps[i] for i in indices], cap, game["rules"]):
                found.append(dict(captain_id=cap, indices=indices))
    if not found:
        raise ValueError("No legal shortlisted captain lineups")
    return found


def compare_lineups(outcomes, game, lineups, *, batch_size=128):
    """Top-5% threshold against ALL eligible legal lineups, including ties."""
    weights = np.zeros((len(lineups), len(game["players"])))
    for j, lineup in enumerate(lineups):
        weights[j, lineup["indices"]] = 1
        ci = next(i for i, p in enumerate(game["players"]) if p["id"] == lineup["captain_id"])
        weights[j, ci] = 1.5
    hits = np.zeros(len(lineups))
    sums = np.zeros(len(lineups))
    thresholds = []
    for start in range(0, len(outcomes), batch_size):
        values = outcomes[start:start+batch_size] @ weights.T
        threshold = np.quantile(values, .95, axis=1)
        hits += (values >= threshold[:, None]).sum(axis=0)
        sums += values.sum(axis=0)
        thresholds.extend(threshold.tolist())
    return hits/len(outcomes), sums/len(outcomes), np.asarray(thresholds)
