"""Diagnostic football-role deficit scoring for persisted lineup candidates."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping

import numpy as np

SKILL_POSITIONS = {"RB", "WR", "TE"}
CORE_CLASSES = {
    "offensive centerpiece",
    "core receiving player",
    "core rushing player",
    "core offensive player",
}


def role_bucket(core: Mapping[str, Any] | None) -> str:
    core = core or {}
    if core.get("current_evidence_confidence") != "high_current":
        return "stale_or_unknown"
    classification = str(core.get("football_classification") or "")
    if classification in CORE_CLASSES or bool(core.get("overall_core")):
        return "strong_core"
    if classification == "meaningful secondary":
        return "meaningful_secondary"
    if classification == "complementary":
        return "complementary"
    if classification == "peripheral":
        return "peripheral"
    return "stale_or_unknown"


def player_deficit(core: Mapping[str, Any] | None) -> float:
    """Return a bounded weak-role penalty with no reward above core status."""
    bucket = role_bucket(core)
    if bucket in {"strong_core", "meaningful_secondary", "stale_or_unknown"}:
        return 0.0
    centrality = float((core or {}).get("overall_centrality") or 0.0)
    if bucket == "complementary":
        weakness = min(1.0, max(0.0, (0.45 - centrality) / 0.25))
        return 0.10 + 0.20 * weakness
    weakness = min(1.0, max(0.0, (0.20 - centrality) / 0.20))
    return 0.50 + 0.50 * weakness


def _comparable_core_alternative(
    player: Mapping[str, Any],
    team_pool: Iterable[Mapping[str, Any]],
    core_by_id: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    salary = player.get("salary")
    projection = player.get("projection")
    if salary is None or projection is None:
        return None
    salary = float(salary)
    projection = float(projection)
    alternatives = []
    for peer in team_pool:
        if str(peer.get("player_id")) == str(player.get("player_id")):
            continue
        if role_bucket(core_by_id.get(str(peer.get("player_id")))) != "strong_core":
            continue
        peer_salary, peer_projection = peer.get("salary"), peer.get("projection")
        if peer_salary is None or peer_projection is None:
            continue
        salary_window = max(1000.0, 0.20 * salary)
        if abs(float(peer_salary) - salary) <= salary_window and float(peer_projection) >= projection - 1.0:
            alternatives.append(peer)
    return max(alternatives, key=lambda row: float(row.get("projection") or 0), default=None)


def lineup_sanity_deficit(
    roster: Iterable[Mapping[str, Any]],
    *,
    core_by_id: Mapping[str, Mapping[str, Any]],
    player_pool: Iterable[Mapping[str, Any]] = (),
    showdown: bool = False,
) -> dict[str, Any]:
    """Score weak roles and team coverage without changing lineup legality."""
    skill = [
        dict(row) for row in roster
        if str(row.get("position") or "").upper() in SKILL_POSITIONS
    ]
    pool_by_team: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in player_pool:
        if str(row.get("position") or "").upper() in SKILL_POSITIONS:
            pool_by_team[str(row.get("team") or "")].append(row)
    buckets = Counter()
    player_rows = []
    team_members: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for player in skill:
        player_id = str(player.get("player_id"))
        core = core_by_id.get(player_id, {})
        bucket = role_bucket(core)
        deficit = player_deficit(core)
        buckets[bucket] += 1
        detail = {
            "player_id": player_id,
            "player": player.get("name") or core.get("player"),
            "team": player.get("team") or core.get("team"),
            "position": player.get("position") or core.get("position"),
            "bucket": bucket,
            "classification": core.get("football_classification"),
            "overall_centrality": core.get("overall_centrality"),
            "confidence": core.get("current_evidence_confidence", "unavailable"),
            "player_deficit": deficit,
        }
        player_rows.append(detail)
        team_members[str(detail["team"] or "")].append(detail)

    multi_skill_teams = sorted(team for team, rows in team_members.items() if len(rows) >= 2)
    multi_without_core = sorted(
        team for team in multi_skill_teams
        if not any(row["bucket"] == "strong_core" for row in team_members[team])
    )
    classic_team_deficit = 0.25 * len(multi_without_core)
    coverage_violations = []
    showdown_coverage_deficit = 0.0
    if showdown:
        for team, rows in sorted(team_members.items()):
            has_core = any(row["bucket"] == "strong_core" for row in rows)
            eligible_core = any(
                role_bucket(core_by_id.get(str(peer.get("player_id")))) == "strong_core"
                for peer in pool_by_team.get(team, [])
            )
            if rows and eligible_core and not has_core:
                amount = 0.50 + (0.50 if len(rows) >= 2 else 0.0)
                showdown_coverage_deficit += amount
                coverage_violations.append({
                    "team": team,
                    "selected_skill_count": len(rows),
                    "selected_players": [row["player"] for row in rows],
                    "deficit": amount,
                })

    comparable = []
    for player, detail in zip(skill, player_rows):
        if detail["bucket"] != "peripheral":
            continue
        alternative = _comparable_core_alternative(
            player, pool_by_team.get(str(detail["team"] or ""), []), core_by_id
        )
        if alternative:
            comparable.append({
                "peripheral_player": detail["player"],
                "core_alternative": alternative.get("name"),
                "team": detail["team"],
                "deficit": 0.15,
            })
    comparable_deficit = 0.15 * len(comparable)
    player_total = sum(row["player_deficit"] for row in player_rows)
    total = player_total + classic_team_deficit + comparable_deficit + showdown_coverage_deficit
    return {
        "skill_player_count": len(skill),
        "core_skill_count": buckets["strong_core"],
        "meaningful_secondary_count": buckets["meaningful_secondary"],
        "complementary_count": buckets["complementary"],
        "peripheral_count": buckets["peripheral"],
        "stale_count": buckets["stale_or_unknown"],
        "teams_with_multiple_skill_players": multi_skill_teams,
        "teams_with_multiple_skill_players_no_core": multi_without_core,
        "player_deficit": player_total,
        "classic_team_context_deficit": classic_team_deficit,
        "comparable_core_alternative_deficit": comparable_deficit,
        "showdown_team_coverage_deficit": showdown_coverage_deficit,
        "total_football_sanity_deficit": total,
        "players": player_rows,
        "comparable_core_alternatives": comparable,
        "team_coverage_violations": coverage_violations,
    }


def prepare_deficit_candidates(
    candidates: Iterable[Mapping[str, Any]],
    *,
    core_by_id: Mapping[str, Mapping[str, Any]],
    player_pool: Iterable[Mapping[str, Any]],
    roster_key: str = "roster",
    base_score_key: str = "objective_score",
    showdown: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    rows = []
    for index, source in enumerate(candidates, 1):
        row = dict(source)
        row["saved_rank"] = row.get("rank", index)
        row["base_objective"] = float(row[base_score_key])
        row["sanity"] = lineup_sanity_deficit(
            row.get(roster_key, []), core_by_id=core_by_id,
            player_pool=player_pool, showdown=showdown,
        )
        rows.append(row)
    values = np.array(
        [row["sanity"]["total_football_sanity_deficit"] for row in rows], dtype=float
    )
    std = float(values.std(ddof=0)) if len(values) else 0.0
    for row in rows:
        deficit = float(row["sanity"]["total_football_sanity_deficit"])
        # Scale by one pool standard deviation without mean-centering. A sound
        # zero-deficit lineup therefore receives exactly zero selector penalty.
        row["standardized_deficit"] = deficit / std if std > 0 else 0.0
    return rows, {
        "mean": float(values.mean()) if len(values) else 0.0,
        "std": std,
        "minimum": float(values.min()) if len(values) else 0.0,
        "maximum": float(values.max()) if len(values) else 0.0,
        "candidate_count": len(rows),
    }


def rank_with_deficit(candidates: Iterable[Mapping[str, Any]], weight: float) -> list[dict]:
    output = []
    for source in candidates:
        row = dict(source)
        row["lambda"] = float(weight)
        row["football_penalty"] = float(weight) * float(row["standardized_deficit"])
        row["shadow_objective"] = float(row["base_objective"]) - row["football_penalty"]
        output.append(row)
    return sorted(output, key=lambda row: (-row["shadow_objective"], row["saved_rank"]))


def deficit_crossover_points(
    candidates: list[Mapping[str, Any]], *, maximum_lambda: float = 100.0
) -> list[dict[str, Any]]:
    intersections = {0.0, float(maximum_lambda)}
    for left_index, left in enumerate(candidates):
        for right in candidates[left_index + 1:]:
            delta = float(left["standardized_deficit"]) - float(right["standardized_deficit"])
            if abs(delta) < 1e-12:
                continue
            point = (float(left["base_objective"]) - float(right["base_objective"])) / delta
            if 0.0 < point < maximum_lambda:
                intersections.add(point)
    ordered = sorted(intersections)
    changes = []
    previous = None
    for left, right in zip(ordered, ordered[1:]):
        winner = rank_with_deficit(candidates, (left + right) / 2.0)[0]
        if winner["saved_rank"] == previous:
            continue
        crossover = 0.0
        if previous is not None:
            prior = next(row for row in candidates if row["saved_rank"] == previous)
            deficit_delta = float(prior["standardized_deficit"]) - float(winner["standardized_deficit"])
            crossover = (
                (float(prior["base_objective"]) - float(winner["base_objective"]))
                / deficit_delta if deficit_delta > 0 else left
            )
        changes.append({"lambda": max(0.0, crossover), "candidate": winner})
        previous = winner["saved_rank"]
    return changes
