"""Pregame-only coverage diagnostics and read-only frozen-pool selector shadows."""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
import hashlib
import json
from statistics import mean, median
from typing import Any, Mapping, Sequence

from .classic_small_field import _select_global
from .optimizer_effectiveness import _pearson, _ranks, candidate_signature, score_signature


def validate_generation_input_snapshot(snapshot: Mapping[str, Any] | None) -> dict[str, str]:
    """Gate future generator replays on an immutable pregame input hash."""
    if not snapshot or snapshot.get("contract") != "classic_frozen_generation_inputs_v1":
        return {"status": "unavailable", "reason": "complete_frozen_generation_inputs_absent"}
    players, options = snapshot.get("players"), snapshot.get("options")
    if not isinstance(players, list) or not players or not isinstance(options, dict):
        return {"status": "unavailable", "reason": "frozen_generation_input_shape_invalid"}
    forbidden = {"actual_points", "actual_score", "actual_rank", "postgame"}
    required = {"player_id", "team", "opponent", "position", "salary", "projection", "ceiling", "ownership"}
    if any(not isinstance(row, dict) or not required.issubset(row) or forbidden.intersection(row)
           for row in players):
        return {"status": "unavailable", "reason": "frozen_generation_input_player_invalid"}
    payload = {"players": players, "options": options}
    try:
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                           allow_nan=False).encode()).hexdigest()
    except (TypeError, ValueError):
        return {"status": "unavailable", "reason": "frozen_generation_input_not_json_safe"}
    if snapshot.get("sha256") != digest:
        return {"status": "unavailable", "reason": "frozen_generation_input_hash_mismatch"}
    return {"status": "frozen_pregame_inputs", "reason": "hash_verified"}


def stack_family(candidate: Mapping[str, Any]) -> str:
    stack = candidate.get("stack") or {}
    partners = int(stack.get("partner_count") or 0)
    backs = int(stack.get("bring_back_count") or 0)
    return f"QB+{partners}" + (f"+{backs} bring-back" if backs else "")


def lineup_diversity(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Count exact rosters and football theses without using outcomes."""
    rosters = [set(str(pid) for pid in row["player_ids"]) for row in candidates]
    overlaps = Counter(len(left & right) for left, right in combinations(rosters, 2))
    family_counts = Counter((str(row["qb"]["player_id"]), str(row.get("primary_game")),
                             stack_family(row)) for row in candidates)
    n = len(candidates)
    pairs = sum(overlaps.values())
    player_counts = Counter(pid for roster in rosters for pid in roster)
    return {
        "candidate_count": n,
        "unique_roster_count": len({tuple(sorted(roster)) for roster in rosters}),
        "average_pairwise_overlap": sum(k * v for k, v in overlaps.items()) / pairs if pairs else None,
        "overlap_distribution": dict(sorted(overlaps.items())),
        "pair_count": pairs,
        "shared_at_least": {str(k): sum(v for overlap, v in overlaps.items() if overlap >= k) / pairs
                            if pairs else None for k in (5, 6, 7, 8)},
        "qb_count": len({row["qb"]["player_id"] for row in candidates}),
        "construction_family_count": len(family_counts),
        "effective_family_count": (n * n / sum(count * count for count in family_counts.values())) if n else 0,
        "largest_families": [{"qb_id": qb, "game": game, "family": family, "count": count}
                             for (qb, game, family), count in family_counts.most_common(15)],
        "core_player_counts": player_counts.most_common(20),
    }


def pregame_coverage(candidates: Sequence[Mapping[str, Any]], selected_ranks: Sequence[int],
                     eligible_players: Sequence[Mapping[str, Any]] = (),
                     ownership_by_player: Mapping[str, float] | None = None) -> dict[str, Any]:
    """Summarize the frozen candidate universe; all inputs must be pregame."""
    selected = [row for row in candidates if int(row["rank"]) in set(selected_ranks)]
    n, m = len(candidates), len(selected)
    qb_rows = []
    qbs = {str(row["qb"]["player_id"]): row for row in candidates}
    pool = {str(row["player_id"]): row for row in eligible_players if row.get("included", True)}
    for qb_id, example in sorted(qbs.items(), key=lambda item: item[1]["qb"]["name"]):
        rows = [row for row in candidates if str(row["qb"]["player_id"]) == qb_id]
        picked = [row for row in selected if str(row["qb"]["player_id"]) == qb_id]
        player = pool.get(qb_id, {})
        env = example.get("game_environment") or {}
        qb_rows.append({
            "player_id": qb_id, "name": example["qb"]["name"], "team": example["qb"].get("team"),
            "salary": player.get("salary"), "mean": player.get("projection"), "p90": player.get("p90"),
            "ownership": example["qb"].get("ownership"),
            "game_total": env.get("game_total") if env.get("market_safe") else None,
            "team_total": env.get("team_total") if env.get("market_safe") else None,
            "spread": env.get("team_spread") if env.get("market_safe") else None,
            "candidate_count": len(rows), "candidate_pct": 100 * len(rows) / n if n else 0,
            "selected_count": len(picked), "selected_pct": 100 * len(picked) / m if m else 0,
            "families": dict(Counter(stack_family(row) for row in rows)),
            "best_selector_rank": min(int(row["rank"]) for row in rows),
            "best_selector_score": max(float(row["objective_score"]) for row in rows),
            "sequential_count": sum("sequential" in row.get("discovery_sources", []) for row in rows),
        })
    for key, field in (("mean_rank", "mean"), ("p90_rank", "p90"),
                       ("ownership_rank", "ownership"), ("game_total_rank", "game_total")):
        ranked = sorted((row for row in qb_rows if row[field] is not None),
                        key=lambda row: (-float(row[field]), row["player_id"]))
        for rank, row in enumerate(ranked, 1):
            row[key] = rank
    candidates_by_player = Counter(str(pid) for row in candidates for pid in row["player_ids"])
    selected_by_player = Counter(str(pid) for row in selected for pid in row["player_ids"])
    saved_ownership = {str(player["player_id"]): player.get("ownership")
                       for row in candidates for player in row.get("roster", [])}
    saved_ownership.update(ownership_by_player or {})
    team_by_player = {str(player["player_id"]): player.get("team")
                      for row in candidates for player in row.get("roster", [])}
    position_by_player = {str(player["player_id"]): player.get("position")
                          for row in candidates for player in row.get("roster", [])}
    market_by_team = {row["team"]: {key: row[key] for key in ("game_total", "team_total", "spread")}
                      for row in qb_rows if row.get("team")}
    players = []
    for pid, row in pool.items():
        salary = row.get("salary") or 0
        team = row.get("team") or team_by_player.get(pid)
        players.append({"player_id": pid, "name": row.get("player_name"),
                        "position": row.get("position") or position_by_player.get(pid), "team": team,
                        "salary": salary, "mean": row.get("projection"), "p90": row.get("p90"),
                        "ownership": saved_ownership.get(pid, row.get("ownership")),
                        "value": float(row["projection"]) / (salary / 1000) if salary and row.get("projection") is not None else None,
                        "game_environment": market_by_team.get(team),
                        "candidate_count": candidates_by_player[pid], "candidate_pct": 100 * candidates_by_player[pid] / n if n else 0,
                        "selected_count": selected_by_player[pid], "selected_pct": 100 * selected_by_player[pid] / m if m else 0})
    for field in ("mean", "p90"):
        ordered = sorted((float(row[field]) for row in players if row[field] is not None))
        for row in players:
            row[f"{field}_percentile"] = (100 * sum(value <= float(row[field]) for value in ordered) / len(ordered)
                                                if row[field] is not None and ordered else None)
    games = defaultdict(lambda: Counter())
    game_teams = {}
    for row in qb_rows:
        team = row.get("team")
        game = next((candidate.get("primary_game") for candidate in candidates
                     if candidate["qb"]["player_id"] == row["player_id"]), None)
        if team and game and "–" in game:
            opponent = game.split("–", 1)[1]
            key = "–".join(sorted((team, opponent)))
            game_teams[team] = key
            game_teams[opponent] = key
    market_by_game = {}
    for row in qb_rows:
        game = game_teams.get(row.get("team"))
        if game:
            market_by_game.setdefault(game, {"game_total": row.get("game_total"), "team_totals": {}})
            market_by_game[game]["team_totals"][row["team"]] = row.get("team_total")
    for row in candidates:
        qb = row["qb"]
        game = game_teams.get(qb.get("team"), "unknown")
        games[game]["qb"] += 1
        games[game]["bring_back"] += int((row.get("stack") or {}).get("bring_back_count") or 0) > 0
        games[game]["full_stack"] += int((row.get("stack") or {}).get("partner_count") or 0) >= 2 and int((row.get("stack") or {}).get("bring_back_count") or 0) > 0
        per_game = defaultdict(set)
        for player in row.get("roster", []):
            player_game = game_teams.get(player.get("team"))
            if not player_game:
                continue
            position = player.get("position")
            if position in {"WR", "TE"}: per_game[player_game].add("pass_catcher")
            if position == "RB": per_game[player_game].add("rb")
            if position == "DST": per_game[player_game].add("dst")
        for player_game, roles in per_game.items():
            for role in roles: games[player_game][role] += 1
    return {"qb": qb_rows, "players": players,
            "games": [{"game": key, **market_by_game.get(key, {}), **dict(value)}
                      for key, value in sorted(games.items())],
            "stack_families": dict(Counter(stack_family(row) for row in candidates)),
            "selected_stack_families": dict(Counter(stack_family(row) for row in selected)),
            "bring_back_distribution": dict(Counter(int((row.get("stack") or {}).get("bring_back_count") or 0)
                                                    for row in candidates)),
            "selected_bring_back_distribution": dict(Counter(int((row.get("stack") or {}).get("bring_back_count") or 0)
                                                             for row in selected)),
            "diversity": lineup_diversity(candidates)}


def selector_scores(candidates: Sequence[Mapping[str, Any]]) -> dict[str, list[float]]:
    """Predeclared ranking policies, evaluated without editing candidate records."""
    means = [float(row["mean"]) for row in candidates]
    ceilings = [float(row["p90"]) for row in candidates]
    def normalized(values: list[float]) -> list[float]:
        low, high = min(values), max(values)
        return [(value - low) / (high - low) if high > low else 0.5 for value in values]
    nm, nc = normalized(means), normalized(ceilings)
    scores = {
        "A_existing": [float(row["objective_score"]) for row in candidates],
        "B_mean": means, "C_ceiling": ceilings,
        "E_without_context_correlation": [float(row["objective_score"])
                                           - float((row.get("components") or {}).get("context") or 0)
                                           - float((row.get("components") or {}).get("correlation") or 0)
                                           for row in candidates],
    }
    for mean_weight in (0.5, 0.35, 0.65):
        scores[f"D_mean_{mean_weight:.2f}_ceiling_{1-mean_weight:.2f}"] = [
            mean_weight * a + (1 - mean_weight) * b for a, b in zip(nm, nc)]
    return scores


def evaluate_selector(candidates: Sequence[Mapping[str, Any]], scores: Sequence[float],
                      actuals: Mapping[str, float], thresholds: Mapping[str, Mapping[str, float]]) -> dict[str, Any]:
    order = sorted(range(len(candidates)), key=lambda i: (-scores[i], -float(candidates[i]["mean"]), i))
    actual = [score_signature(candidate_signature(row, "classic"), actuals)[0] for row in candidates]
    scored = [i for i, value in enumerate(actual) if value is not None]
    best_pool = max((actual[i] for i in scored), default=None)
    actual_rank = {i: 1 + sum(actual[j] > actual[i] + .005 for j in scored) for i in scored}
    top = {}
    for k in (1, 3, 5, 10, 20):
        subset = [actual[i] for i in order[:k] if actual[i] is not None]
        top[str(k)] = {"best_actual": max(subset, default=None), "scoreable": len(subset), "requested": k}
    top5 = [actual[i] for i in order[:5] if actual[i] is not None]
    pairs = [(scores[i], actual[i]) for i in scored]
    x, y = [v[0] for v in pairs], [v[1] for v in pairs]
    best5 = max(top5, default=None)
    attainment = {contest: {label: (best5 is not None and best5 >= value - .005)
                            for label, value in lines.items()}
                  for contest, lines in thresholds.items()}
    return {"top_k": top, "top5_average": mean(top5) if top5 else None,
            "top5_median": median(top5) if top5 else None,
            "top5_scoreable": len(top5), "pearson": _pearson(x, y),
            "spearman": _pearson(_ranks(x), _ranks(y)) if len(x) >= 3 else None,
            "pregame_1_actual_rank_bounds": [actual_rank[order[0]], actual_rank[order[0]] + len(candidates) - len(scored)]
            if order and order[0] in actual_rank else None,
            "pregame_top5_actual_rank_bounds": [[actual_rank[i], actual_rank[i] + len(candidates) - len(scored)]
                                                if i in actual_rank else None for i in order[:5]],
            "top5_candidate_ranks": [int(candidates[i]["rank"]) for i in order[:5]],
            "selection_regret_lower_bound": best_pool - best5 if best_pool is not None and best5 is not None else None,
            "field_attainment_top5": attainment,
            "scored_candidates": len(scored), "candidate_count": len(candidates)}


def portfolio_grid(candidates: Sequence[Mapping[str, Any]], actuals: Mapping[str, float],
                   *, count: int, max_exposure: float, original_selected_ranks: Sequence[int],
                   thresholds: Mapping[str, Mapping[str, float]] | None = None) -> list[dict[str, Any]]:
    """40 fixed pregame configurations; record infeasibility exactly."""
    baseline = [row for row in candidates if int(row["rank"]) in set(original_selected_ranks)]
    baseline_mean = sum(float(row["mean"]) for row in baseline)
    baseline_ceiling = sum(float(row["p90"]) for row in baseline)
    all_known = [score_signature(candidate_signature(row, "classic"), actuals)[0]
                 for row in candidates]
    best_pool = max((value for value in all_known if value is not None), default=None)
    output = []
    for overlap in (None, 8, 7, 6, 5):
        for distinct in (False, True):
            for loss in (None, .05, .10, .20):
                indexes = _select_global(list(candidates), count, max_exposure, set(), {}, {},
                                         max_lineup_overlap=overlap, distinct_qb_paths=distinct,
                                         max_objective_loss=loss)
                rows = [candidates[i] for i in indexes]
                values = [score_signature(candidate_signature(row, "classic"), actuals)[0] for row in rows]
                known = [value for value in values if value is not None]
                best = max(known, default=None)
                output.append({"source_label": "original_pool_shadow_selection",
                               "max_overlap": overlap, "distinct_qb_paths": distinct,
                               "max_objective_loss": loss,
                               "status": "feasible" if len(rows) == count else "infeasible",
                               "ranks": [int(row["rank"]) for row in rows],
                               "best_scoreable_actual": best,
                               "average_scoreable_actual": mean(known) if known else None,
                               "median_scoreable_actual": median(known) if known else None,
                               "selection_regret_lower_bound": best_pool - best
                               if best_pool is not None and best is not None else None,
                               "best_actual_in_selected_top_k": {
                                   str(k): max((value for value in values[:k] if value is not None), default=None)
                                   for k in (1, 3, 5)},
                               "field_attainment_top5": {
                                   contest: {label: best is not None and best >= threshold - .005
                                             for label, threshold in lines.items()}
                                   for contest, lines in (thresholds or {}).items()},
                               "scoreable_count": len(known),
                               "mean_sacrifice": baseline_mean - sum(float(row["mean"]) for row in rows) if rows else None,
                               "ceiling_sacrifice": baseline_ceiling - sum(float(row["p90"]) for row in rows) if rows else None,
                               "qb_count": len({row["qb"]["player_id"] for row in rows}),
                               "family_count": len({(row["qb"]["player_id"], stack_family(row)) for row in rows}),
                               "family_exposure": dict(Counter(stack_family(row) for row in rows)),
                               "qb_exposure": dict(Counter(row["qb"]["name"] for row in rows)),
                               "game_exposure": dict(Counter(row["primary_game"] for row in rows)),
                               "player_exposure": dict(Counter(pid for row in rows for pid in row["player_ids"])),
                               "overlap_matrix": [[len(set(a["player_ids"]) & set(b["player_ids"]))
                                                   for b in rows] for a in rows]})
    return output
