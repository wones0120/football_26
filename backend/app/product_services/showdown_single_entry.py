"""Transparent heuristic selection for separate Showdown single-entry contests."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from itertools import combinations, combinations_with_replacement


DEFAULT_WEIGHTS = {
    "mean": 0.35,
    "p90": 0.30,
    "solver": 0.20,
    "correlation": 0.10,
    "context": 0.05,
    "chalk_penalty": 0.03,
}
FIRST_ALTERNATE_BENEFIT_WEIGHT = 0.03
MATERIAL_PLAYER_CHANGE_MINIMUM = 2


def _signature(lineup: list[dict]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(row["player_id"]), str(row["roster_position"])) for row in lineup))


def _diversity(left: dict, right: dict) -> tuple[float, list[str]]:
    reasons = []
    benefit = 0.0
    if left["captain_id"] != right["captain_id"]:
        benefit += 0.35
        reasons.append("different Captain")
    if left["game_script"]["script_id"] != right["game_script"]["script_id"]:
        benefit += 0.25
        reasons.append("different game script")
    if left["team_emphasis"] != right["team_emphasis"]:
        benefit += 0.15
        reasons.append("different team emphasis")
    left_ids = {player_id for player_id, _ in left["signature"]}
    right_ids = {player_id for player_id, _ in right["signature"]}
    changed = 6 - len(left_ids & right_ids)
    benefit += 0.25 * min(1.0, changed / 3.0)
    if changed >= 2:
        reasons.append(f"{changed} different players")
    return benefit, reasons


def _portfolio_comparison(best: dict, alternatives: tuple[dict, ...]) -> dict:
    """Score a three-entry assignment relative to repeating A in every contest."""
    distinct = {row["signature"]: row for row in alternatives if row["signature"] != best["signature"]}
    ranked_benefits = sorted(
        ((FIRST_ALTERNATE_BENEFIT_WEIGHT * row["diversity_score_vs_a"], row["rank"]) for row in distinct.values()),
        reverse=True,
    )
    diversification_credit = sum(value / (index + 1) for index, (value, _) in enumerate(ranked_benefits))
    quality_loss = sum(row["quality_loss_vs_a"] for row in alternatives)
    ranks = [1, *(row["rank"] for row in alternatives)]
    if len(alternatives) == 2 and ranks.count(1) == 2:
        alternate_rank = next(rank for rank in ranks if rank != 1)
        ranks = [1, alternate_rank, 1]
    elif len(alternatives) == 2 and len({row["signature"] for row in alternatives}) == 2:
        ranked = sorted(alternatives, key=lambda row: (-row["diversification_benefit_vs_a"], row["rank"]))
        ranks = [1, *(row["rank"] for row in ranked)]
    labels: dict[int, str] = {1: "A"}
    for rank in ranks[1:]:
        if rank not in labels:
            labels[rank] = chr(ord("A") + len(labels))
    return {
        "structure": " / ".join(labels[rank] for rank in ranks),
        "candidate_ranks": ranks,
        "quality_loss_total": quality_loss,
        "diversification_credit_total": diversification_credit,
        "heuristic_delta_vs_aaa": diversification_credit - quality_loss,
    }


def select_single_entry_lineups(
    lineups: list[list[dict]],
    *,
    num_contests: int,
    weights: dict[str, float] | None = None,
    contest_metadata: list[dict] | None = None,
) -> tuple[list[list[dict]], dict]:
    """Rank unique candidates and assign repeatable entries without exposure caps.

    This is a heuristic. It deliberately does not estimate contest payouts.
    """
    if num_contests < 1:
        raise ValueError("num_single_entry_contests must be positive")
    if contest_metadata is not None and len(contest_metadata) != num_contests:
        raise ValueError("contest_metadata must have one item per single-entry contest")
    for contest in contest_metadata or []:
        if contest.get("single_entry") is False or int(contest.get("maximum_entries", 1)) != 1:
            raise ValueError("Every contest must allow exactly one entry per entrant")
    configured = {**DEFAULT_WEIGHTS, **(weights or {})}
    if any(value < 0 for value in configured.values()):
        raise ValueError("single-entry objective weights must be nonnegative")
    unique = {_signature(lineup): lineup for lineup in lineups if lineup}
    if not unique:
        return [], {"candidates": [], "assignments": [], "method": "heuristic_v1"}
    from .optimizer import classify_showdown_game_script, _safe_float
    from .optimizer import add_showdown_lineup_chalk_metrics

    candidates = list(unique.values())
    add_showdown_lineup_chalk_metrics(candidates)
    records = []
    for lineup in candidates:
        captain = next(row for row in lineup if row["roster_position"] == "CPT")
        script = classify_showdown_game_script(lineup)
        team_counts = Counter(str(row.get("player_team") or row.get("team") or "") for row in lineup)
        emphasis = max(sorted(team_counts), key=lambda team: team_counts[team])
        chalk = lineup[0]["lineup_duplication_risk"]
        records.append({
            "signature": _signature(lineup),
            "captain_id": str(captain["player_id"]),
            "captain": str(captain.get("player_name") or captain.get("name") or captain["player_id"]),
            "players": [
                {"player_id": str(row["player_id"]), "name": str(row.get("player_name") or row.get("name") or row["player_id"]), "slot": str(row["roster_position"])}
                for row in lineup
            ],
            "game_script": script,
            "team_emphasis": emphasis,
            "mean": sum(_safe_float(row.get("projection")) for row in lineup),
            "p90": sum(_safe_float(row.get("p90")) for row in lineup),
            "solver_objective": _safe_float(lineup[0].get("solver_objective_value")),
            "ownership_sum": sum(_safe_float(row.get("ownership")) for row in lineup),
            "relative_chalk": chalk["relative_chalk_score"],
            "correlation_score": _safe_float(lineup[0].get("lineup_correlation_summary", {}).get("total_adjustment")),
            "context_score": sum(_safe_float(row.get("optimizer_context_adjustment")) * (1.5 if row["roster_position"] == "CPT" else 1) for row in lineup),
        })
    maxima = {field: max(abs(row[field]) for row in records) or 1.0 for field in ("mean", "p90", "solver_objective", "correlation_score", "context_score")}
    for row in records:
        components = {field: row[field] / maxima[field] for field in maxima}
        chalk_fraction = (row["relative_chalk"] or 0.0) / 100.0
        row["score_components"] = components
        weight_fields = {
            "mean": "mean", "p90": "p90", "solver_objective": "solver",
            "correlation_score": "correlation", "context_score": "context",
        }
        row["single_entry_score"] = sum(configured[weight_fields[field]] * components[field] for field in components) - configured["chalk_penalty"] * chalk_fraction
    records.sort(key=lambda row: (-row["single_entry_score"], -row["mean"], row["signature"]))
    best = records[0]
    best_player_ids = {player_id for player_id, _ in best["signature"]}
    for rank, row in enumerate(records, 1):
        row["rank"] = rank
        row["quality_loss_vs_a"] = best["single_entry_score"] - row["single_entry_score"]
        player_ids = {player_id for player_id, _ in row["signature"]}
        shared = len(best_player_ids & player_ids)
        diversity, reasons = _diversity(best, row)
        row["shared_players_with_a"] = shared
        row["player_changes_vs_a"] = 6 - shared
        row["overlap_percentage_vs_a"] = 100.0 * shared / 6.0
        row["jaccard_similarity_vs_a"] = shared / (12 - shared)
        row["diversity_score_vs_a"] = diversity
        row["diversification_benefit_vs_a"] = FIRST_ALTERNATE_BENEFIT_WEIGHT * diversity
        row["diversity_reasons_vs_a"] = reasons

    alternatives = records[1:]
    alternate_examples = {
        "different_captain_only": next((row for row in alternatives if row["captain_id"] != best["captain_id"] and row["player_changes_vs_a"] == 0), None),
        "different_captain_material_players": next((row for row in alternatives if row["captain_id"] != best["captain_id"] and row["player_changes_vs_a"] >= MATERIAL_PLAYER_CHANGE_MINIMUM), None),
        "different_game_script": next((row for row in alternatives if row["game_script"]["script_id"] != best["game_script"]["script_id"]), None),
    }
    if num_contests == 3:
        comparisons = [
            _portfolio_comparison(best, pair)
            for pair in combinations_with_replacement(records, 2)
        ]
        comparison_by_ranks = {tuple(row["candidate_ranks"]): row for row in comparisons}
        selected_comparison = max(
            comparisons,
            key=lambda row: (
                row["heuristic_delta_vs_aaa"],
                -row["quality_loss_total"],
                -len(set(row["candidate_ranks"])),
                tuple(-rank for rank in row["candidate_ranks"]),
            ),
        )
        aaa = comparison_by_ranks[(1, 1, 1)]
        best_one_alternate = max(
            (row for row in comparisons if len(set(row["candidate_ranks"])) == 2 and row["candidate_ranks"].count(1) == 2),
            key=lambda row: row["heuristic_delta_vs_aaa"],
            default=None,
        )
        best_two_alternates = max(
            (row for row in comparisons if len(set(row["candidate_ranks"])) == 3),
            key=lambda row: row["heuristic_delta_vs_aaa"],
            default=None,
        )
        best_repeated_alternate = max(
            (row for row in comparisons if len(set(row["candidate_ranks"])) == 2 and row["candidate_ranks"].count(1) == 1),
            key=lambda row: row["heuristic_delta_vs_aaa"],
            default=None,
        )
        portfolio_comparisons = {
            "aaa": aaa,
            "best_one_alternate": best_one_alternate,
            "best_repeated_alternate": best_repeated_alternate,
            "best_two_alternates": best_two_alternates,
        }
        evaluated_portfolio_count = len(comparisons)
        selected = [records[rank - 1] for rank in selected_comparison["candidate_ranks"]]
    elif num_contests > 3:
        selected = [best]
        # Marginal diversity falls as distinct alternatives are added. Repetition is allowed.
        while len(selected) < num_contests:
            used = {row["signature"] for row in selected}
            distinct_count = max(0, len(used) - 1)
            choice = max(records, key=lambda row: (
                (0.0 if row["signature"] in used else row["diversification_benefit_vs_a"] / (distinct_count + 1))
                - row["quality_loss_vs_a"], -row["rank"]
            ))
            selected.append(choice)
        ranks = [row["rank"] for row in selected]
        labels = {rank: chr(ord("A") + index) for index, rank in enumerate(dict.fromkeys(ranks))}
        selected_comparison = {
            "structure": " / ".join(labels[rank] for rank in ranks), "candidate_ranks": ranks,
            "quality_loss_total": sum(row["quality_loss_vs_a"] for row in selected),
            "diversification_credit_total": sum(
                row["diversification_benefit_vs_a"] / (index + 1)
                for index, row in enumerate(row for row in dict((item["signature"], item) for item in selected[1:]).values() if row["rank"] != 1)
            ),
        }
        selected_comparison["heuristic_delta_vs_aaa"] = selected_comparison["diversification_credit_total"] - selected_comparison["quality_loss_total"]
        portfolio_comparisons = {}
        evaluated_portfolio_count = 0
    else:
        selected = [best]
        if num_contests == 2:
            options = [_portfolio_comparison(best, (row,)) for row in records]
            selected_comparison = max(options, key=lambda row: row["heuristic_delta_vs_aaa"])
            selected = [records[rank - 1] for rank in selected_comparison["candidate_ranks"]]
        else:
            selected_comparison = {"structure": "A", "candidate_ranks": [1], "quality_loss_total": 0.0, "diversification_credit_total": 0.0, "heuristic_delta_vs_aaa": 0.0}
        portfolio_comparisons = {}
        evaluated_portfolio_count = 0

    assignments = []
    for contest_number, row in enumerate(selected, 1):
        if contest_number == 1:
            reason = "Strongest overall single-entry construction"
        elif row is best:
            reason = "No additional distinct candidate improved the portfolio heuristic enough to replace A"
        else:
            reason = (
                f"Diversification credit {row['diversification_benefit_vs_a']:.3f} versus A "
                f"and quality loss {row['quality_loss_vs_a']:.3f}; "
                + ", ".join(row["diversity_reasons_vs_a"])
            )
        contest = (contest_metadata or [])[contest_number - 1] if contest_metadata else {}
        assignments.append({"contest": contest_number, "contest_id": contest.get("contest_id"),
                            "contest_name": contest.get("name"), "candidate_rank": row["rank"], "reason": reason})
    by_signature = {_signature(lineup): lineup for lineup in candidates}
    output = [deepcopy(by_signature[row["signature"]]) for row in selected]
    for lineup, assignment in zip(output, assignments):
        captain = next(row for row in lineup if row["roster_position"] == "CPT")
        captain["solver_objective_value"] = lineup[0].get("solver_objective_value")
        captain["lineup_duplication_risk"] = lineup[0].get("lineup_duplication_risk")
        captain["single_entry_assignment"] = assignment
    report = {
        "method": "heuristic_v1",
        "material_player_change_minimum": MATERIAL_PLAYER_CHANGE_MINIMUM,
        "first_alternate_benefit_weight": FIRST_ALTERNATE_BENEFIT_WEIGHT,
        "objective_weights": configured,
        "payout_metrics_status": "unavailable_without_field_and_payout_simulation",
        "primary_future_metric": "P(total payouts > total entry fees)",
        "contest_metadata": contest_metadata or [],
        "candidates": records[:10],
        "selected_candidates": list({row["rank"]: row for row in selected}.values()),
        "top_alternates": alternate_examples,
        "assignments": assignments,
        "recommended_structure": selected_comparison["structure"],
        "selected_portfolio_comparison": selected_comparison,
        "portfolio_comparisons": portfolio_comparisons,
        "evaluated_portfolio_count": evaluated_portfolio_count,
        "unique_lineups": len({row["signature"] for row in selected}),
        "unique_captains": len({row["captain_id"] for row in selected}),
        "pairwise_player_overlap": [len({pid for pid, _ in left["signature"]} & {pid for pid, _ in right["signature"]}) for left, right in combinations(selected, 2)],
    }
    next(row for row in output[0] if row["roster_position"] == "CPT")["single_entry_report"] = report
    return output, report
