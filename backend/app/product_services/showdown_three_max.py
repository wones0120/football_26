"""Global, heuristic selection of unique entries for one small-max Showdown contest."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from itertools import combinations
from math import ceil

from .showdown_contests import _profit_proxy, validate_entry_limit_contest
from .showdown_single_entry import _pair_similarity, select_single_entry_lineups


DEFAULT_EXPOSURES = {"captain": 1.0, "core": 1.0, "starting_qb": 1.0, "cheap_punt": 1.0}
QUALITY_FLOORS = {"mean": .85, "p90": .90}


def validate_three_max_contest(contest: dict) -> dict:
    return validate_entry_limit_contest(contest, maximum_entries=3)


def validate_small_max_contest(contest: dict) -> dict:
    limit = contest.get("maximum_entries")
    if limit is None:
        raise ValueError(f"Contest {contest.get('contest_id')} has no verified per-user entry limit")
    try:
        maximum = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Contest {contest.get('contest_id')} has an invalid per-user entry limit") from exc
    if maximum < 2 or maximum > 5:
        raise ValueError(f"Small-max GPP supports contests allowing 2 through 5 entries; this contest allows {maximum}")
    return validate_entry_limit_contest(contest, maximum_entries=maximum)


def _rate(value: float | int, name: str) -> float:
    rate = float(value)
    if rate > 1:
        rate /= 100
    if not 0 < rate <= 1:
        raise ValueError(f"{name} must be in (0, 1] or a percentage in (0, 100]")
    return rate


def _portfolio_exposure_ok(rows: tuple[dict, ...], lineups_by_signature: dict, rates: dict[str, float]) -> bool:
    count = len(rows)
    if count == 1:
        return True
    captains = Counter(row["captain_id"] for row in rows)
    if max(captains.values()) > ceil(count * rates["captain"]):
        return False
    players = Counter(player_id for row in rows for player_id, _ in row["signature"])
    for player_id, appearances in players.items():
        player = next(player for row in rows for player in lineups_by_signature[row["signature"]] if str(player["player_id"]) == player_id)
        rate = rates["core"]
        if str(player.get("position", "")).upper() == "QB" and player.get("showdown_qb_eligible") is True:
            rate = rates["starting_qb"]
        elif float(player.get("base_salary") or player.get("salary") or 0) <= 1000:
            rate = rates["cheap_punt"]
        if appearances > ceil(count * rate):
            return False
    return True


def _summary(rows: tuple[dict, ...], contest: dict, proxy: dict, reference_score: float) -> dict:
    pairs = []
    for left, right in combinations(rows, 2):
        pair = _pair_similarity(left, right)
        left_punts = {p["player_id"] for p in left["players"] if p["position"] in {"RB", "WR", "TE"} and p["salary"] <= 2000}
        right_punts = {p["player_id"] for p in right["players"] if p["position"] in {"RB", "WR", "TE"} and p["salary"] <= 2000}
        pair["same_value_player_ids"] = sorted(left_punts & right_punts)
        pair["relative_chalk_difference"] = abs(float(left["relative_chalk"] or 0) - float(right["relative_chalk"] or 0))
        pair["repeated_captain_materially_different"] = bool(pair["same_captain"] and pair["shared_players"] <= 4)
        pairs.append(pair)
    similarity = sum(pair["lineup_correlation_proxy"] for pair in pairs) / len(pairs) if pairs else 0.0
    # The existing uniform-rank payout proxy is a heuristic, not a calibrated probability.
    shared_weight = .25 + .75 * similarity if pairs else .5
    payout_proxy = ((1 - shared_weight) * proxy["independent_rank_proxy"]
                    + shared_weight * proxy["shared_percentile_proxy"])
    average_quality = sum(row["single_entry_score"] for row in rows) / len(rows)
    diversification = sum(1 - pair["lineup_correlation_proxy"] for pair in pairs) / len(pairs) if pairs else 0.0
    normalized_quality = average_quality / max(abs(reference_score), .001)
    lineup_selection_score = normalized_quality + .03 * diversification
    lineup_score = .03 * normalized_quality
    diversity_score = .01 * diversification
    total = payout_proxy + lineup_score + diversity_score
    player_counts = Counter(player["name"] for row in rows for player in row["players"])
    captain_counts = Counter(row["captain"] for row in rows)
    return {
        "candidate_ranks": [row["rank"] for row in rows],
        "captains": [row["captain"] for row in rows],
        "scripts": [row["game_script"]["label"] for row in rows],
        "total_entry_fees": len(rows) * float(contest["entry_fee"]),
        "portfolio_objective": total,
        "lineup_selection_score": lineup_selection_score,
        "payout_proxy": payout_proxy,
        "independent_rank_proxy": proxy["independent_rank_proxy"],
        "shared_percentile_proxy": proxy["shared_percentile_proxy"],
        "shared_rank_weight": shared_weight,
        "lineup_quality_contribution": lineup_score,
        "diversification_contribution": diversity_score,
        "average_mean": sum(row["mean"] for row in rows) / len(rows),
        "minimum_mean": min(row["mean"] for row in rows),
        "average_p90": sum(row["p90"] for row in rows) / len(rows),
        "minimum_p90": min(row["p90"] for row in rows),
        "average_relative_chalk": sum(float(row["relative_chalk"] or 0) for row in rows) / len(rows),
        "unique_captains": len(captain_counts),
        "captain_exposures": {name: count / len(rows) for name, count in captain_counts.items()},
        "player_exposures": {name: count / len(rows) for name, count in player_counts.items()},
        "script_diversity": len({row["game_script"]["script_id"] for row in rows}),
        "pairwise": pairs,
    }


def select_generic_small_max_lineups(
    lineups: list[list[dict]], *, maximum_entries: int = 5,
    entries_to_use: str | int = "auto",
    exposure_rates: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
) -> tuple[list[list[dict]], dict]:
    """Select quality-first Showdown entries without inventing contest payouts."""
    try:
        maximum = int(maximum_entries)
    except (TypeError, ValueError) as exc:
        raise ValueError("Generic small-max entry limit must be 2 through 5") from exc
    if not 2 <= maximum <= 5:
        raise ValueError("Generic small-max entry limit must be 2 through 5")
    requested = str(entries_to_use).lower()
    if requested != "auto" and (not requested.isdigit() or not 1 <= int(requested) <= maximum):
        raise ValueError(f"entries_to_use must be auto or an integer from 1 through {maximum}")
    rates = {key: _rate((exposure_rates or {}).get(key, default), key)
             for key, default in DEFAULT_EXPOSURES.items()}
    _, ranked = select_single_entry_lineups(
        lineups, num_contests=1, weights=weights, report_candidate_limit=None,
    )
    records = ranked["candidates"]
    if not records:
        return [], {"method": "generic_small_max_quality_v1", "contest_mode": "generic",
                    "count_comparisons": [], "selected_count": 0}
    by_signature = {
        tuple(sorted((str(p["player_id"]), str(p["roster_position"])) for p in lineup)): lineup
        for lineup in lineups if lineup
    }
    best_mean = max(row["mean"] for row in records)
    best_p90 = max(row["p90"] for row in records)
    qualifying = [row for row in records if row["mean"] >= QUALITY_FLOORS["mean"] * best_mean
                  and row["p90"] >= QUALITY_FLOORS["p90"] * best_p90]
    searched = qualifying[:20]
    reference = max(abs(records[0]["single_entry_score"]), .001)
    best_by_count: dict[int, dict] = {}
    for count in range(1, maximum + 1):
        for rows in combinations(searched, count):
            if not _portfolio_exposure_ok(rows, by_signature, rates):
                continue
            pairs = [_pair_similarity(left, right) for left, right in combinations(rows, 2)]
            diversity = (sum(1 - pair["lineup_correlation_proxy"] for pair in pairs) / len(pairs)
                         if pairs else 0.0)
            quality = sum(row["single_entry_score"] for row in rows) / count / reference
            score = quality + .03 * diversity
            captain_counts = Counter(row["captain_id"] for row in rows)
            captain_names = {row["captain_id"]: row["captain"] for row in rows}
            repeated_captain_names = Counter(captain_names.values())
            player_counts = Counter(str(player["player_id"]) for row in rows for player in row["players"])
            player_names = {str(player["player_id"]): player["name"] for row in rows for player in row["players"]}
            repeated_names = Counter(player_names.values())
            summary = {
                "candidate_ranks": [row["rank"] for row in rows],
                "captains": [row["captain"] for row in rows],
                "scripts": [row["game_script"]["label"] for row in rows],
                "portfolio_objective": score,
                "lineup_selection_score": score,
                "lineup_quality_contribution": quality,
                "diversification_contribution": .03 * diversity,
                "average_mean": sum(row["mean"] for row in rows) / count,
                "minimum_mean": min(row["mean"] for row in rows),
                "average_p90": sum(row["p90"] for row in rows) / count,
                "minimum_p90": min(row["p90"] for row in rows),
                "average_relative_chalk": (sum(float(row["relative_chalk"]) for row in rows) / count
                                           if all(row["relative_chalk"] is not None for row in rows) else None),
                "unique_captains": len(captain_counts),
                "captain_exposures": {
                    (f"{captain_names[player_id]} ({player_id})" if repeated_captain_names[captain_names[player_id]] > 1
                     else captain_names[player_id]): appearances / count
                    for player_id, appearances in captain_counts.items()
                },
                "player_exposures": {
                    (f"{player_names[player_id]} ({player_id})" if repeated_names[player_names[player_id]] > 1
                     else player_names[player_id]): appearances / count
                    for player_id, appearances in player_counts.items()
                },
                "script_diversity": len({row["game_script"]["script_id"] for row in rows}),
                "pairwise": pairs,
            }
            previous = best_by_count.get(count)
            if previous is None or (score, tuple(-rank for rank in summary["candidate_ranks"])) > (
                previous["portfolio_objective"],
                tuple(-rank for rank in previous["candidate_ranks"]),
            ):
                best_by_count[count] = summary
    by_rank = {row["rank"]: row for row in records}
    for summary in best_by_count.values():
        summary["lineups"] = [
            {"rank": rank, "captain": by_rank[rank]["captain"],
             "mean": by_rank[rank]["mean"], "p90": by_rank[rank]["p90"],
             "relative_chalk": by_rank[rank]["relative_chalk"],
             "script": by_rank[rank]["game_script"]["label"],
             "players": by_rank[rank]["players"]}
            for rank in summary["candidate_ranks"]
        ]
    # Contest-free Auto answers the lineup question. Entry-count economics need
    # a real contest, so additional entries require an explicit count.
    selected_count = (1 if requested == "auto" else max(
        (count for count in best_by_count if count <= int(requested)), default=0
    ))
    selected = best_by_count.get(selected_count)
    output = [deepcopy(by_signature[by_rank[rank]["signature"]])
              for rank in selected["candidate_ranks"]] if selected else []
    report = {
        "method": "generic_small_max_quality_v1",
        "contest_mode": "generic",
        "contest": None,
        "maximum_entries": maximum,
        "entries_to_use": requested,
        "selection_mode": "auto" if requested == "auto" else "configured",
        "configured_entry_count": None if requested == "auto" else int(requested),
        "auto_recommended_count": 1 if best_by_count.get(1) else 0,
        "selected_count": len(output),
        "selected": selected,
        "count_comparisons": [best_by_count.get(count) for count in range(1, maximum + 1)],
        "candidate_count": len(records),
        "qualifying_candidate_count": len(qualifying),
        "searched_candidate_count": len(searched),
        "quality_floors": QUALITY_FLOORS,
        "exposure_rates": rates,
        "note": "Generic small-max lineup selection uses mean, summed P90, solver, correlation, context and available chalk evidence. Auto returns one strongest lineup. Additional entries require a configured count. No contest payout, entry-fee, field-size or ROI estimate is made.",
    }
    if output:
        output[0][0]["small_max_report"] = report
    return output, report


def select_small_max_lineups(
    lineups: list[list[dict]], *, contest: dict, entries_to_use: str | int = "auto",
    exposure_rates: dict[str, float] | None = None, weights: dict[str, float] | None = None,
) -> tuple[list[list[dict]], dict]:
    contest = validate_small_max_contest(contest)
    maximum = int(contest["maximum_entries"])
    requested = str(entries_to_use).lower()
    if requested != "auto" and (not requested.isdigit() or not 1 <= int(requested) <= maximum):
        raise ValueError(f"entries_to_use must be auto or an integer from 1 through {maximum}")
    rates = {key: _rate((exposure_rates or {}).get(key, default), key)
             for key, default in DEFAULT_EXPOSURES.items()}
    _, ranked = select_single_entry_lineups(lineups, num_contests=1, weights=weights, report_candidate_limit=None)
    records = ranked["candidates"]
    if not records:
        return [], {"method": "global_small_max_heuristic_v1", "count_comparisons": []}
    by_signature = {tuple(sorted((str(p["player_id"]), str(p["roster_position"])) for p in lineup)): lineup for lineup in lineups if lineup}
    best_mean = max(row["mean"] for row in records)
    best_p90 = max(row["p90"] for row in records)
    qualifying = [row for row in records if row["mean"] >= QUALITY_FLOORS["mean"] * best_mean
                  and row["p90"] >= QUALITY_FLOORS["p90"] * best_p90]
    # Exhaustive global search remains tractable through five entries after a
    # quality-ranked shortlist. The full candidate and qualifying counts stay visible.
    searched = qualifying[:20]
    best_by_count = {}
    finalists = {}
    best_by_captain_count = {}
    for count in range(1, maximum + 1):
        valid = []
        count_proxy = _profit_proxy((contest,) * count)
        for rows in combinations(searched, count):
            if not _portfolio_exposure_ok(rows, by_signature, rates):
                continue
            summary = _summary(rows, contest, count_proxy, records[0]["single_entry_score"])
            summary["structure"] = " / ".join(f"#{row['rank']}" for row in rows)
            if count == 3:
                captain_count = summary["unique_captains"]
                previous = best_by_captain_count.get(captain_count)
                if previous is None or summary["lineup_selection_score"] > previous["lineup_selection_score"]:
                    best_by_captain_count[captain_count] = summary
            valid.append(summary)
            if len(valid) > 5:
                valid.sort(key=lambda row: (-row["portfolio_objective"], row["candidate_ranks"]))
                valid.pop()
        valid.sort(key=lambda row: (-row["portfolio_objective"], row["candidate_ranks"]))
        if valid:
            best_by_count[count] = valid[0]
            finalists[count] = valid[:5]
    by_rank = {row["rank"]: row for row in records}
    for summary in [*best_by_count.values(), *best_by_captain_count.values()]:
        summary["lineups"] = [
            {"rank": rank, "captain": by_rank[rank]["captain"],
             "mean": by_rank[rank]["mean"], "p90": by_rank[rank]["p90"],
             "relative_chalk": by_rank[rank]["relative_chalk"],
             "script": by_rank[rank]["game_script"]["label"],
             "players": by_rank[rank]["players"]}
            for rank in summary["candidate_ranks"]
        ]
    count_marginals = []
    for count in range(1, maximum + 1):
        current, prior = best_by_count.get(count), best_by_count.get(count - 1)
        if current:
            added = sorted(set(current["candidate_ranks"]) - set(prior["candidate_ranks"] if prior else []))
            removed = sorted(set(prior["candidate_ranks"]) - set(current["candidate_ranks"])) if prior else []
            count_marginals.append({
                "from_count": count - 1, "entry_count": count,
                "objective_change": current["portfolio_objective"] - prior["portfolio_objective"] if prior else None,
                "payout_proxy_change": current["payout_proxy"] - prior["payout_proxy"] if prior else None,
                "lineup_quality_change": current["lineup_quality_contribution"] - prior["lineup_quality_contribution"] if prior else None,
                "diversification_change": current["diversification_contribution"] - prior["diversification_contribution"] if prior else None,
                "added_candidate_ranks": added, "removed_candidate_ranks": removed,
                "added_lineups": [row for row in current["lineups"] if row["rank"] in added],
                "fee_delta": current["total_entry_fees"] - prior["total_entry_fees"] if prior else current["total_entry_fees"],
            })
    auto_recommended = max(best_by_count.values(), key=lambda row: (row["portfolio_objective"], -len(row["candidate_ranks"])), default=None)
    if requested == "auto":
        selected = auto_recommended
    else:
        feasible_counts = [count for count in best_by_count if count <= int(requested)]
        fallback_count = max(feasible_counts, default=0)
        selected = best_by_count.get(fallback_count)
    selected_rows = [records[rank - 1] for rank in selected["candidate_ranks"]] if selected else []
    output = [deepcopy(by_signature[row["signature"]]) for row in selected_rows]
    if output:
        leave_one_out = []
        for removed in selected_rows:
            remaining = tuple(row for row in selected_rows if row["rank"] != removed["rank"])
            without = (_summary(remaining, contest, _profit_proxy((contest,) * len(remaining)), records[0]["single_entry_score"])
                       if remaining else {"portfolio_objective": 0.0})
            leave_one_out.append({
                "candidate_rank": removed["rank"], "captain": removed["captain"],
                "mean": removed["mean"], "p90": removed["p90"],
                "relative_chalk": removed["relative_chalk"],
                "remaining_candidate_ranks": [row["rank"] for row in remaining],
                "objective_without_lineup": without["portfolio_objective"],
                "objective_change_if_removed": without["portfolio_objective"] - selected["portfolio_objective"],
                "contribution_to_selected_objective": selected["portfolio_objective"] - without["portfolio_objective"],
            })
        report = {
            "method": "global_small_max_heuristic_v1", "contest": contest, "entries_to_use": requested,
            "selection_mode": "auto" if requested == "auto" else "configured",
            "configured_entry_count": None if requested == "auto" else int(requested),
            "auto_recommended_count": len(auto_recommended["candidate_ranks"]) if auto_recommended else 0,
            "selected_count": len(output), "selected": selected,
            "count_comparisons": [best_by_count.get(count) for count in range(1, maximum + 1)],
            "finalists_by_count": finalists, "candidate_count": len(records),
            "all_candidates": records, "serialized_candidate_count": len(records),
            "qualifying_candidate_count": len(qualifying), "quality_floors": QUALITY_FLOORS,
            "searched_candidate_count": len(searched),
            "exposure_rates": rates, "leave_one_out": leave_one_out,
            "count_marginals": count_marginals,
            "structure_comparisons": {
                structure: best_by_captain_count.get(captain_count)
                for structure, captain_count in (("one_captain", 1), ("two_captains", 2), ("three_captains", 3))
            },
            "note": "For each entry count, the best unique set maximizes the same portfolio heuristic used to compare counts. The search is exhaustive within the top 20 quality-qualified candidates. Uniform-rank payout proxies are uncalibrated; no actual payout or ROI probabilities are estimated.",
        }
        output[0][0]["small_max_report"] = report
    else:
        report = {"method": "global_small_max_heuristic_v1", "contest": contest,
                  "entries_to_use": requested,
                  "selection_mode": "auto" if requested == "auto" else "configured",
                  "configured_entry_count": None if requested == "auto" else int(requested),
                  "auto_recommended_count": len(auto_recommended["candidate_ranks"]) if auto_recommended else 0,
                  "selected_count": 0,
                  "count_comparisons": [best_by_count.get(count) for count in range(1, maximum + 1)],
                  "candidate_count": len(records), "all_candidates": records,
                  "serialized_candidate_count": len(records),
                  "qualifying_candidate_count": len(qualifying),
                  "reason": "No requested entry count satisfies lineup quality and exposure constraints"}
    return output, report


def select_three_max_lineups(
    lineups: list[list[dict]], *, contest: dict, entries_to_use: str | int = "auto",
    exposure_rates: dict[str, float] | None = None, weights: dict[str, float] | None = None,
) -> tuple[list[list[dict]], dict]:
    """Compatibility entrypoint for saved 3-max requests."""
    validated = validate_three_max_contest(contest)
    selected, report = select_small_max_lineups(
        lineups, contest=validated, entries_to_use=entries_to_use,
        exposure_rates=exposure_rates, weights=weights,
    )
    if selected:
        selected[0][0]["three_max_report"] = report
    return selected, report
