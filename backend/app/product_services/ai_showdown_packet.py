"""Read-only, point-in-time Showdown candidate packet construction.

Only named fields are copied from saved optimizer evidence. This module never
queries a current player, market, projection, or postgame source.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .optimizer_effectiveness import candidate_signature, extract_saved_pool

CONTRACT = "ai_showdown_selection_packet_v1"
POLICY = "ai_showdown_finalists_v2"
CLASSIFIER = "ai_showdown_construction_v2"
REVIEW_UNIVERSE = "ai_showdown_review_universe_v1"
QUALITY_DEFAULTS = {"minimum_fraction": 0.80, "strong_fraction": 0.90}
CAP = 50000
_GAME_TIME = re.compile(r"(\d{2}/\d{2}/\d{4} \d{2}:\d{2}[AP]M) ET")
_BANNED = {"actual_points", "actual_score", "actual_rank", "actual_ownership", "postgame", "final_score", "winning_lineup"}


def digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _date(value: Any) -> datetime | None:
    try:
        result = datetime.fromisoformat(_iso(value).replace("Z", "+00:00"))
        return result if result.tzinfo else None
    except (ValueError, AttributeError):
        return None


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if result == result and abs(result) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _game(rows: list[dict], cutoff: datetime) -> dict:
    first = rows[0] if rows else {}
    game_id = str(first.get("game_id") or "")
    match = _GAME_TIME.search(game_id)
    if not match:
        raise ValueError("Saved game kickoff is missing; replay-safe export unavailable")
    kickoff = datetime.strptime(match.group(1), "%m/%d/%Y %I:%M%p").replace(tzinfo=ZoneInfo("America/New_York"))
    if cutoff >= kickoff:
        raise ValueError("Saved data cutoff is at or after kickoff")
    # Selected scenario lineups can carry conditioned markets. Prefer the
    # original saved BASELINE quote, never a scenario's hypothetical spread.
    baselines = [s for r in rows for s in (r.get("captain_family_coverage_report") or {}).get("scenario_definitions", [])
                 if s.get("scenario_id") == "baseline"]
    market_source = "saved_selected_rows"
    market_unavailable_reason = None
    if baselines:
        baseline = baselines[0]
        fields = ("market_spread_by_team", "market_implied_by_team", "market_total", "market_observed_at", "market_source")
        if any(any(s.get(k) != baseline.get(k) for k in fields) for s in baselines):
            raise ValueError("Conflicting saved baseline market quotes")
        if all(baseline.get(k) in (None, "", {}) for k in fields):
            # The generator emits an empty baseline definition when market
            # inputs are unavailable. Preserve that absence; never substitute
            # a selected scenario's conditioned quote or a current market.
            market_rows = []
            market_source = None
            market_unavailable_reason = "saved_baseline_market_missing"
        else:
            observed = _date(baseline.get("market_observed_at"))
            if observed is None or observed > cutoff:
                raise ValueError("Saved baseline scenario market is missing or after the run cutoff")
            market_rows = [{"player_team": team, "team_spread_line": spread,
                            "team_implied_total": (baseline.get("market_implied_by_team") or {}).get(team),
                            "market_observed_at": observed.isoformat(), "game_total_line": baseline.get("market_total")}
                           for team, spread in sorted((baseline.get("market_spread_by_team") or {}).items())]
            market_source = baseline.get("market_source") or "saved_baseline_scenario"
    else:
        market_rows = [r for r in rows if r.get("team_spread_line") is not None]
    market = {}
    for row in market_rows:
        observed = _date(row.get("market_observed_at"))
        if observed is None or observed > cutoff:
            continue
        team = str(row.get("player_team") or "")
        if team and team not in market:
            market[team] = {"spread": _number(row.get("team_spread_line")),
                            "implied_total": _number(row.get("team_implied_total")),
                            "observed_at": observed.isoformat()}
    favorite = next((team for team, value in sorted(market.items()) if value["spread"] is not None and value["spread"] < 0), None)
    underdog = next((team for team, value in sorted(market.items()) if value["spread"] is not None and value["spread"] > 0), None)
    result = {"matchup": game_id.split(" ")[0], "game_id": game_id, "kickoff_at": kickoff.isoformat(),
            "favorite": favorite, "underdog": underdog, "market_by_team": market,
            "pickem": len(market) == 2 and all(value["spread"] == 0 for value in market.values()),
            "market_source": market_source, "market_basis": "saved_baseline" if baselines else "saved_selected_rows",
            "total": _number(market_rows[0].get("game_total_line")) if market and market_rows else None}
    if market_unavailable_reason:
        result["market_unavailable_reason"] = market_unavailable_reason
    return result


def _saved_candidates(source: Mapping[str, Any]) -> tuple[list[dict], dict]:
    config = source.get("params") or source.get("constraint_config_json")
    if config:
        pool = extract_saved_pool(config, "showdown")
        if pool.get("status") != "original_candidate_pool":
            raise ValueError(f"Original saved candidate pool unavailable: {pool.get('reason')}")
        return pool["candidates"], {k: v for k, v in pool.items() if k != "candidates"}
    # Exported optimizer-result reference artifacts retain the same ranked
    # report but not the private saved constraint configuration/manifest.
    reports = [r["captain_family_coverage_report"] for lineup in source.get("results") or []
               for r in lineup if isinstance(r, dict) and isinstance(r.get("captain_family_coverage_report"), dict)]
    if not reports or not isinstance(reports[0].get("ranked_metrics"), list):
        raise ValueError("Original saved candidate pool unavailable")
    candidates = reports[0]["ranked_metrics"]
    if not candidates:
        raise ValueError("Saved candidate pool is empty")
    return candidates, {"status": "original_candidate_pool", "source_path": "results.captain_family_coverage_report.ranked_metrics",
                        "sha256": digest(candidates), "count": len(candidates),
                        "manifest_status": "exported_result_without_persisted_manifest"}


def _players(candidate: dict, lookup: dict[str, dict], cutoff: datetime) -> list[dict]:
    raw = candidate.get("players") or candidate.get("roster")
    if not isinstance(raw, list):
        raise ValueError("Candidate has no saved canonical roster")
    result = []
    for item in raw:
        pid = str(item.get("player_id") or "")
        base = lookup.get(pid, {})
        slot = str(item.get("slot") or item.get("roster_position") or "").upper()
        observed = _date(base.get("pregame_context_observed_at"))
        context_ok = observed is None or observed <= cutoff
        status_observed = _date(base.get("injury_observed_at"))
        status_ok = status_observed is None or status_observed <= cutoff
        adjustment = item.get("adjustment") if isinstance(item.get("adjustment"), dict) else {}
        result.append({"player_id": pid, "name": item.get("name") or item.get("player_name") or base.get("player_name") or base.get("name") or pid,
                       "slot": slot, "team": item.get("team") or item.get("player_team") or base.get("team") or base.get("player_team"),
                       "position": item.get("position") or base.get("position"),
                       "salary": _number(item.get("salary") if item.get("salary") is not None else
                                         base["salary"] * (1.5 if slot == "CPT" else 1) if base.get("salary") is not None else None),
                       "projection": _number(adjustment.get("baseline_mean") if adjustment.get("baseline_mean") is not None else
                                             item.get("projection") if item.get("projection") is not None else
                                             base["projection"] * (1.5 if slot == "CPT" else 1) if base.get("projection") is not None else None),
                       "p90": _number(adjustment.get("baseline_p90") if adjustment.get("baseline_p90") is not None else
                                      item.get("p90") if item.get("p90") is not None else
                                      base["p90"] * (1.5 if slot == "CPT" else 1) if base.get("p90") is not None else None),
                       "flex_ownership": _number(item.get("flex_ownership") if item.get("flex_ownership") is not None else base.get("flex_ownership")),
                       "captain_ownership": _number(item.get("captain_ownership") if item.get("captain_ownership") is not None else base.get("captain_ownership")),
                       "injury_status": (base.get("pregame_injury_status") or base.get("injury_status")) if status_ok else None,
                       "role_label": base.get("pregame_role_label") if context_ok else None,
                       "role_uncertain": bool(base.get("pregame_role_uncertain")) if context_ok else None})
    if candidate_signature({"players": result}, "showdown") is None:
        raise ValueError("Candidate has invalid canonical Showdown roster")
    return result


def _classify(players: list[dict], game: dict, salary: float | None, ownership: float | None) -> dict:
    captain = next(p for p in players if p["slot"] == "CPT")
    counts = Counter(p["team"] for p in players)
    if len(counts) != 2 or None in counts or max(counts.values()) > 5:
        raise ValueError("Saved candidate has invalid two-team construction")
    favorite, underdog = game["favorite"], game["underdog"]
    split = "3-3" if sorted(counts.values()) == [3, 3] else f"{max(counts.values())}-{min(counts.values())} {max(counts, key=counts.get)}"
    qbs = {p["team"] for p in players if p["position"] == "QB"}
    if favorite and underdog:
        qb_structure = "both_qbs" if {favorite, underdog} <= qbs else "favorite_qb_only" if favorite in qbs else "underdog_qb_only" if underdog in qbs else "no_qb"
    else:
        qb_structure = "two_qbs" if len(qbs) == 2 else "one_qb" if qbs else "no_qb"
    archetype = captain["position"] or "other"
    if archetype in {"RB", "WR", "TE"} and (captain["salary"] or CAP) <= 1500:
        archetype = "punt_skill"
    tags: dict[str, list[str]] = {}
    def tag(name: str, *reasons: str) -> None:
        tags[name] = list(reasons)
    if captain["position"] in {"K", "DST"}: tag("defense_special_teams_game", "k_or_dst_captain")
    if len(qbs) == 2 and split == "3-3": tag("competitive_shootout", "both_qbs", "balanced_team_split")
    if split == "3-3": tag("balanced_competitive_game", "balanced_team_split")
    if sum(p["position"] in {"DST", "K"} for p in players) >= 2:
        tag("low_scoring_game", "multiple_defense_or_kicker_slots")
    if favorite and underdog:
        for side, team in (("favorite", favorite), ("underdog", underdog)):
            if counts[team] >= 4:
                if captain["team"] == team and captain["position"] in {"QB", "WR", "TE"} and team in qbs:
                    tag(f"{side}_pass_win", "team_majority", "team_qb_captain" if captain["position"] == "QB" else "team_receiving_captain_with_qb")
                if captain["team"] == team and captain["position"] == "RB": tag(f"{side}_rush_win", "team_majority", "team_rb_captain")
                if counts[team] == 5: tag("favorite_dominant_win" if side == "favorite" else "underdog_upset", "five_player_team_stack")
            if counts[team] <= 2 and captain["team"] == team and captain["position"] in {"QB", "WR", "TE"} and team in qbs:
                tag(f"{side}_trailing_comeback", "minority_team_receiving_or_qb_captain", "team_qb_present")
    if not tags:
        # Weak construction evidence gets an explicit fallback, not an invented
        # winning team. These are hypotheses, never estimated probabilities.
        tag("balanced_competitive_game", "no_directional_script_evidence")
    priority = ["defense_special_teams_game", "low_scoring_game", "favorite_dominant_win", "underdog_upset",
                "favorite_trailing_comeback", "underdog_trailing_comeback", "favorite_pass_win", "favorite_rush_win",
                "underdog_pass_win", "underdog_rush_win", "competitive_shootout", "balanced_competitive_game"]
    primary = next(t for t in priority if t in tags)
    majority = max(counts, key=lambda t: (counts[t], t))
    side = "favorite" if captain["team"] == favorite else "underdog" if captain["team"] == underdog else captain["team"]
    normalized_split = "3-3" if split == "3-3" else f"{max(counts.values())}-{min(counts.values())}_" + (
        "favorite" if majority == favorite else "underdog" if majority == underdog else majority)
    signatures = {t: f"{t}|{archetype}|{normalized_split}|{qb_structure}" for t in sorted(tags)}
    attributes = ["qb_captain" if captain["position"] == "QB" else "non_qb_captain", qb_structure, normalized_split]
    attribute_reasons = {attributes[0]: ["captain_position"], qb_structure: ["saved_qb_team_membership"],
                         normalized_split: ["saved_team_counts"]}
    if archetype == "punt_skill":
        attributes.append("punt_captain")
        attribute_reasons["punt_captain"] = ["captain_low_salary_skill"]
    if captain["position"] in {"K", "DST"}:
        label = "kicker_captain" if captain["position"] == "K" else "dst_captain"
        attributes.append(label)
        attribute_reasons[label] = ["captain_position"]
    risk = []
    if any(str(p.get("injury_status") or "").lower() in {"questionable", "doubtful", "game-time decision"} for p in players): risk.append("uncertain_injury_status")
    if any(p.get("role_uncertain") for p in players): risk.append("uncertain_role")
    if any((p["salary"] or CAP) <= 1000 and p["position"] in {"RB", "WR", "TE"} for p in players): risk.append("low_salary_skill_punt")
    if any(p.get("flex_ownership") is not None and p["flex_ownership"] < 5 for p in players): risk.append("very_low_projected_flex_ownership")
    if any(p.get("projection") is not None and p["projection"] < 2 for p in players): risk.append("very_low_projected_points")
    if any(p["position"] == "QB" and any(q["position"] == "DST" and q["team"] != p["team"] for q in players) for p in players): risk.append("qb_opposing_dst")
    if not qbs: risk.append("no_qb_construction")
    if max(counts.values()) == 5: risk.append("five_one_construction")
    remaining = CAP - salary if salary is not None else None
    bucket = None if remaining is None else "0-100" if remaining <= 100 else "101-500" if remaining <= 500 else "501-1000" if remaining <= 1000 else "1001+"
    ownership_bucket = None if ownership is None else "contrarian" if ownership < 70 else "chalk" if ownership > 120 else "balanced"
    for label, value in (("salary_left_bucket", bucket), ("ownership_bucket", ownership_bucket)):
        if value is not None:
            attribute = f"{label}:{value}"
            attributes.append(attribute)
            attribute_reasons[attribute] = ["saved_salary" if label == "salary_left_bucket" else "saved_complete_projected_ownership"]
    return {"team_split": split, "team_counts": dict(sorted(counts.items())), "captain_team": captain["team"],
            "captain_position": captain["position"], "captain_player_id": captain["player_id"],
            "captain_player_name": captain["name"], "captain_archetype": archetype,
            "qb_structure": qb_structure, "qb_captain": captain["position"] == "QB",
            "favorite_players": counts.get(favorite) if favorite else None,
            "underdog_players": counts.get(underdog) if underdog else None,
            "pass_catchers_by_qb_team": {team: sum(p["team"] == team and p["position"] in {"WR", "TE"} for p in players) for team in sorted(qbs)},
            "opposing_bring_backs": sum(p["team"] != captain["team"] for p in players),
            "rb_dst_pair": any(p["position"] == "RB" and any(q["position"] == "DST" and q["team"] == p["team"] for q in players) for p in players),
            "qb_opposing_dst": "qb_opposing_dst" in risk,
            "same_team_rb_opposing_qb": any(p["position"] == "RB" and any(q["position"] == "QB" and q["team"] != p["team"] for q in players) for p in players),
            "kicker_count": sum(p["position"] == "K" for p in players), "dst_count": sum(p["position"] == "DST" for p in players),
            "salary_remaining": remaining, "salary_bucket": bucket,
            "ownership_bucket": ownership_bucket,
            "normalized_team_split": normalized_split, "captain_side": side,
            "captain_script_combination": f"{side}|{archetype}|{normalized_split}|{qb_structure}",
            "construction_attributes": sorted(attributes), "construction_reason_codes": attribute_reasons,
            "football_scenarios": sorted(tags), "primary_football_scenario": primary,
            "primary_thesis_signature": signatures[primary], "thesis_signatures": sorted(signatures.values()),
            "thesis_reason_codes": {signatures[t]: tags[t] for t in sorted(tags)},
            "scenario_tags": sorted(tags), "scenario_reason_codes": tags, "risk_flags": sorted(risk)}


def _market_compatibility(construction: dict, game: dict) -> dict:
    market = game.get("market_by_team") or {}
    spread = _number((market.get(game.get("favorite")) or {}).get("spread"))
    if game.get("pickem"):
        spread = 0.0
    total = _number(game.get("total"))
    scenario = construction["primary_football_scenario"]
    reasons = []
    level = "MEDIUM"
    if spread is None or total is None:
        reasons.append("saved_baseline_market_incomplete")
    elif scenario in {"low_scoring_game", "defense_special_teams_game"}:
        level = "HIGH" if total <= 42 else "LOW" if total >= 48 else "MEDIUM"
        reasons.append("low_total_supports_defensive_script" if total <= 42 else "high_total_opposes_defensive_script" if total >= 48 else "mid_total_defensive_script")
    elif scenario in {"competitive_shootout", "balanced_competitive_game"}:
        if abs(spread) >= 10 or scenario == "competitive_shootout" and total <= 42:
            level = "LOW"
            reasons.append("wide_spread_opposes_competitive_script" if abs(spread) >= 10 else "low_total_opposes_shootout")
        elif abs(spread) < 7 and (scenario == "balanced_competitive_game" or total >= 48):
            level = "HIGH"
            reasons.append("close_spread_supports_competitive_script")
        else:
            reasons.append("moderate_competitive_script_fit")
    elif scenario.startswith("underdog_") and "comeback" not in scenario:
        level = "LOW" if abs(spread) >= 7 else "MEDIUM"
        reasons.append("large_favorite_opposes_underdog_win" if abs(spread) >= 7 else "close_market_allows_contrarian_underdog_win")
    elif "trailing_comeback" in scenario:
        reasons.append("comeback_path_is_contrarian_to_central_market")
    elif scenario == "favorite_dominant_win":
        level = "HIGH" if abs(spread) >= 7 else "MEDIUM"
        reasons.append("large_favorite_supports_dominant_win" if abs(spread) >= 7 else "close_spread_dominant_win_is_contrarian")
    elif scenario.startswith("favorite_"):
        level = "HIGH"
        reasons.append("favorite_win_aligned_with_saved_spread")
    return {"market_compatibility": level, "market_compatibility_reason_codes": reasons,
            "market_compatibility_basis": scenario}


def _similarity(a: dict, b: dict) -> dict:
    x, y = a["construction"], b["construction"]
    shared = len({p["player_id"] for p in a["players"]} & {p["player_id"] for p in b["players"]})
    same_captain = x["captain_player_id"] == y["captain_player_id"]
    overlap = sorted(set(x["scenario_tags"]) & set(y["scenario_tags"]))
    scenario_match = x["primary_football_scenario"] == y["primary_football_scenario"]
    split_match = x["normalized_team_split"] == y["normalized_team_split"]
    qb_match = x["qb_structure"] == y["qb_structure"]
    thesis_match = x["primary_thesis_signature"] == y["primary_thesis_signature"]
    score = round(.30 * shared / 6 + .25 * same_captain + .20 * scenario_match +
                  .10 * split_match + .10 * qb_match + .05 * thesis_match, 6)
    high = shared >= 5 and same_captain and scenario_match and split_match and qb_match
    medium = shared >= 4 or same_captain and bool(overlap)
    return {"candidate_a": a["candidate_id"], "candidate_b": b["candidate_id"],
            "shared_players": shared, "same_captain": same_captain,
            "same_team_split": x["team_split"] == y["team_split"],
            "same_qb_configuration": x["qb_structure"] == y["qb_structure"],
            "player_overlap_count": shared, "captain_match": same_captain,
            "primary_scenario_match": scenario_match, "team_split_match": split_match,
            "qb_structure_match": qb_match, "thesis_signature_match": thesis_match,
            "thesis_similarity_score": score,
            "scenario_overlap": overlap, "thesis_similarity": "HIGH" if high else "MEDIUM" if medium else "LOW"}


def _quality(candidates: list[dict], policy: Mapping[str, float] | None = None) -> dict:
    settings = {**QUALITY_DEFAULTS, **(policy or {})}
    if set(settings) != set(QUALITY_DEFAULTS) or not 0 < settings["minimum_fraction"] <= settings["strong_fraction"] <= 1:
        raise ValueError("Quality fractions must satisfy 0 < minimum <= strong <= 1")
    best_mean = max((c["metrics"]["projected_mean"] or 0) for c in candidates)
    best_ceiling = max((c["metrics"]["summed_marginal_p90_proxy"] or 0) for c in candidates)
    if best_mean <= 0 or best_ceiling <= 0:
        raise ValueError("Positive saved mean and ceiling maxima are required")
    for c in candidates:
        m = c["metrics"]
        mean = m["projected_mean"] / best_mean if m["projected_mean"] is not None else None
        ceiling = m["summed_marginal_p90_proxy"] / best_ceiling if m["summed_marginal_p90_proxy"] is not None else None
        safe = mean is not None and ceiling is not None and min(mean, ceiling) >= settings["minimum_fraction"]
        reasons = []
        if safe:
            if mean >= settings["strong_fraction"]: reasons.append("mean_within_strong_tolerance")
            if ceiling >= settings["strong_fraction"]: reasons.append("ceiling_within_strong_tolerance")
            if m["selector_rank"] <= 3: reasons.append("selector_top_three_within_safety_floor")
        c["quality_eligibility"] = {"eligible": safe and bool(reasons), "mean_fraction": mean,
                                     "ceiling_fraction": ceiling, "reason_codes": reasons or ["outside_multidimensional_quality_range"]}
    return {"rule": "both_safety_floor_and_either_strong_dimension_or_selector_top_three",
            **settings, "selector_exception_ranks": 3, "best_mean": best_mean, "best_ceiling_proxy": best_ceiling}


def _representative_key(c: dict) -> tuple:
    q, m = c["quality_eligibility"], c["metrics"]
    return (-(q["mean_fraction"] + q["ceiling_fraction"]) / 2,
            -max(q["mean_fraction"], q["ceiling_fraction"]), m["selector_rank"], c["candidate_id"])


def _finalists(candidates: list[dict], count: int) -> list[dict]:
    eligible = [c for c in candidates if c["quality_eligibility"]["eligible"]]
    if not eligible:
        raise ValueError("No candidates meet the multidimensional quality floor")
    chosen: dict[str, dict] = {}
    def add(candidate: dict, reason: str, detail: str | None = None) -> None:
        row = chosen.setdefault(candidate["candidate_id"], candidate)
        row.setdefault("inclusion_origin", reason)
        row.setdefault("inclusion_reasons", [])
        if reason not in row["inclusion_reasons"]: row["inclusion_reasons"].append(reason)
        if detail and detail not in row["inclusion_reasons"]: row["inclusion_reasons"].append(detail)
    rank = sorted(eligible, key=lambda c: (c["metrics"]["selector_rank"], c["candidate_id"]))
    by_mean = sorted(eligible, key=lambda c: (-(c["metrics"]["projected_mean"] or -1), c["candidate_id"]))
    by_ceiling = sorted(eligible, key=lambda c: (-(c["metrics"]["summed_marginal_p90_proxy"] or -1), c["candidate_id"]))
    for key, rows in (("selector_quality_preservation", rank[:3]), ("mean_preservation", by_mean[:3]), ("ceiling_preservation", by_ceiling[:3])):
        for row in rows: add(row, key)
    # Nominate independently by thesis and by captain side/script combination.
    representatives = {}
    for field in ("primary_thesis_signature", "captain_script_combination"):
        for c in sorted(eligible, key=_representative_key):
            representatives.setdefault((field, c["construction"][field]), c)
    nominees = {c["candidate_id"]: c for c in representatives.values()}

    def novelty(c: dict) -> tuple:
        x = c["construction"]
        thesis = x["primary_thesis_signature"] not in {s["construction"]["primary_thesis_signature"] for s in chosen.values()}
        combination = x["captain_script_combination"] not in {s["construction"]["captain_script_combination"] for s in chosen.values()}
        scenarios = len(set(x["football_scenarios"]) - {t for s in chosen.values() for t in s["construction"]["football_scenarios"]})
        return thesis, combination, scenarios

    def coverage_key(c: dict) -> tuple:
        thesis, combination, scenarios = novelty(c)
        highs = sum(_similarity(c, s)["thesis_similarity"] == "HIGH" for s in chosen.values())
        # Reward joint identity before extra alternate-scenario labels. Salary
        # and ownership buckets never create a separate football thesis.
        return (-(4 * thesis + 3 * combination), highs, -scenarios, *_representative_key(c))

    target = min(count, len(eligible))
    outlier_slots = min(3, target - len(chosen))
    while len(chosen) < target - outlier_slots:
        remaining = [c for cid, c in nominees.items() if cid not in chosen and any(novelty(c)[:2])]
        if not remaining: break
        row = min(remaining, key=coverage_key)
        add(row, "thesis_coverage", "representative:" + row["construction"]["primary_thesis_signature"])
    # No selector-rank screen is applied to thesis representatives. Reserved
    # outliers reach below the top quarter of distinct candidates.
    cutoff = max(10, (len(candidates) + 3) // 4)
    for _ in range(outlier_slots):
        remaining = [c for c in eligible if c["candidate_id"] not in chosen
                     and c["metrics"].get("selector_pool_rank", c["metrics"]["selector_rank"]) > cutoff and any(novelty(c)[:2])]
        if not remaining: break
        row = min(remaining, key=coverage_key)
        add(row, "outlier_preservation", "outside_selector_top_quarter_with_new_thesis_or_captain_combination")
    while len(chosen) < target:
        remaining = [c for c in eligible if c["candidate_id"] not in chosen]
        row = min(remaining, key=coverage_key)
        add(row, "thesis_coverage" if any(novelty(row)[:2]) else "quality_coverage_fill")
    return sorted(chosen.values(), key=lambda c: (c["metrics"]["selector_rank"], c["candidate_id"]))


def rank_distribution(values: list[int]) -> dict:
    ordered = sorted(values)
    n = len(ordered)
    return {"values": ordered, "min": ordered[0] if n else None, "max": ordered[-1] if n else None,
            "median": (ordered[(n-1)//2] + ordered[n//2]) / 2 if n else None,
            "buckets": {"1-10": sum(v <= 10 for v in values), "11-40": sum(10 < v <= 40 for v in values),
                        "41-100": sum(40 < v <= 100 for v in values), "101+": sum(v > 100 for v in values)}}


def coverage_metrics(finalists: list[dict]) -> dict:
    result = {"finalist_count": len(finalists)}
    for label, field in (("primary_thesis_signatures", "primary_thesis_signature"), ("captain_archetypes", "captain_archetype"),
                         ("team_splits", "normalized_team_split"), ("qb_structures", "qb_structure"),
                         ("captain_script_combinations", "captain_script_combination")):
        counts = Counter(c["construction"][field] for c in finalists)
        result[label] = dict(sorted(counts.items()))
        result["distinct_" + label] = len(counts)
    scenarios = Counter(t for c in finalists for t in c["construction"]["football_scenarios"])
    result.update(football_scenarios=dict(sorted(scenarios.items())), distinct_football_scenarios=len(scenarios))
    market = Counter(c["market_compatibility"] for c in finalists)
    result["market_compatibility_counts"] = {k: market[k] for k in ("HIGH", "MEDIUM", "LOW")}
    for label, field in (("selector_rank", "selector_rank"), ("mean_rank", "projection_rank"), ("ceiling_rank", "ceiling_proxy_rank")):
        result[label + "_distribution"] = rank_distribution([c["metrics"][field] for c in finalists])
    stages = ("selector_quality_preservation", "mean_preservation", "ceiling_preservation", "thesis_coverage", "outlier_preservation", "quality_coverage_fill")
    result["inclusion_reason_counts"] = {k: sum(k in c["inclusion_reasons"] for c in finalists) for k in stages}
    result["inclusion_origin_counts"] = {k: sum(k == c["inclusion_origin"] for c in finalists) for k in stages}
    return result


def _review_universe(candidates: list[dict], finalists: list[dict]) -> dict:
    """Expose every eligible distinct roster without another selection screen."""
    eligible = sorted((c for c in candidates if c["quality_eligibility"]["eligible"]), key=_representative_key)
    if any(not isinstance(p["name"], str) or not p["name"].strip() or p["name"] == p["player_id"]
           for c in eligible for p in c["players"]):
        raise ValueError("AI Review Universe requires saved human-readable names for every eligible player")
    finalist_ids = {c["candidate_id"] for c in finalists}
    rows = [{"candidate_id": c["candidate_id"], "metrics": c["metrics"], "construction": c["construction"],
             "players": c["players"], "variant_ranks": c["variant_ranks"],
             "flex_player_names": [p["name"] for p in sorted(c["players"], key=lambda p: p["player_id"]) if p["slot"] == "FLEX"],
             "quality_eligibility": c["quality_eligibility"],
             "market_compatibility": c["market_compatibility"],
             "market_compatibility_reason_codes": c["market_compatibility_reason_codes"],
             "market_compatibility_basis": c["market_compatibility_basis"],
             "is_deterministic_finalist": c["candidate_id"] in finalist_ids,
             "deterministic_finalist_inclusion_origin": c.get("inclusion_origin") if c["candidate_id"] in finalist_ids else None}
            for c in eligible]
    dimensions = {"primary_thesis": "primary_thesis_signature", "captain_script_combination": "captain_script_combination",
                  "football_scenario": "football_scenarios", "captain_archetype": "captain_archetype",
                  "team_split": "normalized_team_split", "qb_structure": "qb_structure"}
    indexes, summaries = {}, {}
    for dimension, field in dimensions.items():
        groups: dict[str, list[dict]] = {}
        for c in rows:
            values = c["construction"][field]
            for value in values if isinstance(values, list) else [values]:
                groups.setdefault(value, []).append(c)
        indexes[dimension], summaries[dimension] = {}, {}
        for name, members in sorted(groups.items()):
            ids = [c["candidate_id"] for c in members]
            indexes[dimension][name] = ids
            def distribution(field: str) -> dict:
                return dict(sorted(Counter(c["construction"][field] for c in members).items()))
            def span(field: str) -> dict:
                values = [c["metrics"][field] for c in members if c["metrics"][field] is not None]
                return {"min": min(values) if values else None, "max": max(values) if values else None,
                        "available_count": len(values), "unavailable_count": len(members) - len(values)}
            summaries[dimension][name] = {
                "candidate_count": len(members), "top_candidate_ids": ids[:3],
                "captain_side_distribution": distribution("captain_side"),
                "projected_mean_range": span("projected_mean"),
                "ceiling_proxy_range": span("summed_marginal_p90_proxy"),
                "objective_range": span("objective_score"),
                "projected_ownership_range": span("projected_total_ownership"),
                "market_compatibility_distribution": dict(sorted(Counter(c["market_compatibility"] for c in members).items())),
                "deterministic_finalist_count": sum(c["is_deterministic_finalist"] for c in members),
                "distinct_captain_names": sorted({c["construction"]["captain_player_name"] for c in members}),
                "distinct_team_splits": sorted({c["construction"]["normalized_team_split"] for c in members}),
                "risk_flag_counts": dict(sorted(Counter(flag for c in members for flag in c["construction"]["risk_flags"]).items())),
            }
    return {"contract_id": REVIEW_UNIVERSE,
            "ordering": "average_normalized_mean_and_ceiling_desc_then_best_fraction_desc_then_selector_rank_then_candidate_id",
            "summary": {"generated_distinct_candidates": len(candidates), "quality_eligible_candidates": len(rows),
                        "deterministic_finalists": len(finalists), "excluded_by_quality_count": len(candidates) - len(rows),
                        "family_counts": {dimension: len(groups) for dimension, groups in indexes.items()}},
            "candidates": rows, "family_indexes": indexes, "family_summaries": summaries}


def build_packet(source: Mapping[str, Any], *, finalist_count: int = 20, requested_entries: int | None = None,
                 ai_requested_entries: int | None = None, allow_incomplete_evidence: bool = False,
                 generated_at: str | None = None, quality_policy: Mapping[str, float] | None = None) -> dict:
    """Build from one completed saved run or a frozen result export.

    Run creation must precede kickoff. A cutoff alone cannot establish that
    candidates were available before lock.
    """
    return _build_packet(source, finalist_count=finalist_count,
                         requested_entries=_requested_entries(source, requested_entries, ai_requested_entries),
                         generated_at=generated_at, quality_policy=quality_policy, retrospective=False,
                         allow_incomplete_evidence=allow_incomplete_evidence)


def build_retrospective_packet(source: Mapping[str, Any], *, finalist_count: int = 20, requested_entries: int | None = None,
                               ai_requested_entries: int | None = None,
                               generated_at: str | None = None, quality_policy: Mapping[str, float] | None = None) -> dict:
    """Diagnostic only: saved prelock inputs do not prove prelock generation.

    This entry point is deliberately absent from the download API. It retains
    the real creation clock and all source/cutoff checks, and labels the output.
    """
    return _build_packet(source, finalist_count=finalist_count,
                         requested_entries=_requested_entries(source, requested_entries, ai_requested_entries),
                         generated_at=generated_at, quality_policy=quality_policy, retrospective=True,
                         allow_incomplete_evidence=True)


def _requested_entries(source, requested_entries, ai_requested_entries):
    if ai_requested_entries is not None and requested_entries is not None and ai_requested_entries != requested_entries:
        raise ValueError("Conflicting AI requested entry counts")
    if source.get("strategy") == "captain_single_lineup_v1":
        if ai_requested_entries not in {None, 1} or requested_entries not in {None, 1}:
            raise ValueError("Captain single-lineup review requests exactly one entry")
        return 1
    value = ai_requested_entries if ai_requested_entries is not None else requested_entries
    return value if value is not None else (source.get("params") or {}).get("ai_requested_entries", 5)


def _build_packet(source: Mapping[str, Any], *, finalist_count: int, requested_entries: int,
                  generated_at: str | None, quality_policy: Mapping[str, float] | None, retrospective: bool,
                  allow_incomplete_evidence: bool) -> dict:
    if not 15 <= finalist_count <= 30: raise ValueError("Finalist count must be 15–30")
    minimum = 1 if source.get("strategy") == "captain_single_lineup_v1" else 2
    if type(requested_entries) is not int or not minimum <= requested_entries <= 5:
        raise ValueError(f"Requested entries must be {minimum}–5")
    if source.get("status") != "completed" or source.get("contest_format") != "showdown":
        raise ValueError("A completed Showdown run is required")
    if any(source.get(key) is None for key in ("season", "week", "slate", "projection_run_id")):
        raise ValueError("Season, week, slate, and projection run lineage are required")
    run_id = str(source.get("job_id") or source.get("optimizer_run_id") or "")
    cutoff, created = _date(source.get("data_cutoff_at")), _date(source.get("created_at"))
    if not run_id or cutoff is None or created is None:
        raise ValueError("Optimizer run ID, timezone-aware cutoff and creation time are required")
    rows = source.get("results") or []
    flat = [p for lineup in rows for p in lineup]
    if not flat: raise ValueError("Saved selected lineups are unavailable")
    game = _game(flat, cutoff)
    kickoff = _date(game["kickoff_at"])
    if created >= kickoff and not retrospective: raise ValueError("Run was created at or after kickoff; replay-safe export unavailable")
    if created < cutoff: raise ValueError("Run creation precedes its data cutoff")
    from .showdown_data_readiness import validate_frozen_evidence
    frozen = (source.get("params") or {}).get("showdown_evidence_snapshot")
    if frozen:
        readiness = validate_frozen_evidence(frozen)
        if frozen.get("optimizer_run_id") != run_id or _date(frozen.get("evidence_cutoff")) != cutoff:
            raise ValueError("Frozen Showdown evidence belongs to another run or cutoff")
        incomplete = frozen.get("non_production_override") or readiness.get("status") != "READY"
        if incomplete and not allow_incomplete_evidence:
            raise ValueError("AI Review Universe requires a data-ready live run; incomplete evidence is diagnostic only")
        if not incomplete:
            game = _game(frozen["player_pool"], cutoff)
            game["market_basis"] = "frozen_generation_baseline"
            if len(game["market_by_team"]) != 2 or game["total"] is None:
                raise ValueError("Frozen live baseline market is incomplete; AI Review Universe export blocked")
    else:
        readiness = {"contract_id": "showdown_data_readiness_v1", "status": "NOT_READY",
                     "reason_codes": ["frozen_readiness_missing"], "required_sources": {},
                     "optional_sources": {}, "historical_evidence_unverified": True}
        incomplete = True
        if kickoff > datetime.now(ZoneInfo("UTC")) and not allow_incomplete_evidence:
            raise ValueError("AI Review Universe requires a data-ready live run: frozen_readiness_missing")
    for row in flat:
        report = row.get("captain_family_coverage_report") or {}
        for scenario in report.get("scenario_definitions") or []:
            observed = _date(scenario.get("market_observed_at"))
            if observed and observed > cutoff:
                raise ValueError("Saved candidate scenario market is after the run cutoff")
    for row in flat:
        if row.get("projection_run_id") and str(row["projection_run_id"]) != str(source.get("projection_run_id")):
            raise ValueError("Saved selected player uses another projection run")
        for field in ("data_cutoff_at", "market_observed_at", "injury_observed_at",
                      "practice_observed_at", "pregame_context_observed_at", "expected_workload_observed_at"):
            observed = _date(row.get(field))
            if observed and observed > cutoff:
                raise ValueError(f"Saved selected player {field} is after the run cutoff")
    pool, manifest = _saved_candidates(source)
    for candidate in pool:
        if not isinstance(candidate, dict) or _BANNED & set(candidate):
            raise ValueError("Saved candidate pool contains postgame or invalid rows")
        for player in candidate.get("players") or candidate.get("roster") or []:
            if _BANNED & set(player): raise ValueError("Saved candidate player contains postgame fields")
    player_rows = ((frozen or {}).get("player_pool") or (source.get("player_pool") or {}).get("rows") or
                   ((source.get("params") or {}).get("strategy_runtime") or {}).get("player_pool", {}).get("rows") or [])
    for row in player_rows:
        for field in ("pregame_context_observed_at", "injury_observed_at", "market_observed_at"):
            observed = _date(row.get(field))
            if observed and observed > cutoff:
                raise ValueError(f"Saved player pool {field} is after the run cutoff")
    lookup = {str(p["player_id"]): p for p in player_rows if isinstance(p, dict) and p.get("player_id")}
    frozen_ids = set(lookup) if frozen else set()
    for row in flat:
        pid = str(row.get("player_id") or "")
        if frozen:
            if not incomplete and pid not in frozen_ids:
                raise ValueError("Saved selected player is outside the frozen generation pool")
            continue
        if pid:
            prior = lookup.get(pid, {})
            lookup[pid] = {**row, **prior, **{field: row[field] for field in
                           ("flex_ownership", "captain_ownership", "injury_observed_at")
                           if prior.get(field) is None and row.get(field) is not None}}
    unique: dict[tuple, dict] = {}
    variants = []
    for index, candidate in enumerate(pool, 1):
        players = _players(candidate, lookup, cutoff)
        if frozen and not readiness.get("ownership", {}).get("ownership_fresh"):
            for player in players:
                player["flex_ownership"] = player["captain_ownership"] = None
        if frozen and not incomplete and any(p["player_id"] not in frozen_ids for p in players):
            raise ValueError("Saved candidate contains a player outside the frozen generation pool")
        signature = candidate_signature({"players": players}, "showdown")
        sig_hash = digest(signature)[:16]
        candidate_id = f"{run_id}:{sig_hash}"
        selector_rank = int(candidate.get("rank") or index)
        salary = _number(candidate.get("salary"))
        if salary is None and all(p["salary"] is not None for p in players): salary = sum(p["salary"] for p in players)
        if salary is not None and not 0 <= salary <= CAP:
            raise ValueError("Saved candidate salary is outside the Showdown cap")
        mean = _number(candidate.get("baseline_mean") if candidate.get("baseline_mean") is not None else candidate.get("mean"))
        ceiling = _number(candidate.get("baseline_p90") if candidate.get("baseline_p90") is not None else candidate.get("p90"))
        if mean is None and all(p["projection"] is not None for p in players): mean = sum(p["projection"] for p in players)
        if ceiling is None and all(p["p90"] is not None for p in players): ceiling = sum(p["p90"] for p in players)
        ownership = _number(candidate.get("lineup_ownership")) if candidate.get("ownership_complete") else None
        if frozen and not readiness.get("ownership", {}).get("ownership_fresh"):
            ownership = None
        flex_values = [p["flex_ownership"] for p in players if p["slot"] == "FLEX"]
        complete_flex = len(flex_values) == 5 and all(value is not None for value in flex_values)
        construction = _classify(players, game, salary, ownership)
        row = {"candidate_id": candidate_id, "variant_ranks": [selector_rank], "players": players,
               "metrics": {"selector_rank": selector_rank, "objective_score": _number(candidate.get("selector") or candidate.get("objective_score")),
                           "projected_mean": mean, "summed_marginal_p90_proxy": ceiling,
                           "salary_used": salary, "projected_total_ownership": ownership,
                           "projected_captain_ownership": _number(candidate.get("captain_ownership")) if candidate.get("ownership_complete") else None,
                           "projected_flex_ownership_sum": sum(flex_values) if complete_flex else None,
                           "players_below_10pct_flex": sum(value < 10 for value in flex_values) if complete_flex else None,
                           "players_below_5pct_flex": sum(value < 5 for value in flex_values) if complete_flex else None},
               "construction": construction, **_market_compatibility(construction, game)}
        prior = unique.get(signature)
        if prior is None or selector_rank < prior["metrics"]["selector_rank"]:
            if prior: row["variant_ranks"] += prior["variant_ranks"]
            unique[signature] = row
        else:
            prior["variant_ranks"].append(selector_rank)
        variants.append({"rank": selector_rank, "candidate_id": candidate_id})
    candidates = list(unique.values())
    candidates.sort(key=lambda c: (c["metrics"]["selector_rank"], c["candidate_id"]))
    for rank, c in enumerate(candidates, 1):
        c["variant_ranks"].sort()
        c["metrics"]["selector_pool_rank"] = rank
    variants.sort(key=lambda v: (v["rank"], v["candidate_id"]))
    for field, rank_field in (("projected_mean", "projection_rank"),
                              ("summed_marginal_p90_proxy", "ceiling_proxy_rank")):
        for rank, candidate in enumerate(sorted(candidates, key=lambda c: (-(c["metrics"][field] or -1), c["candidate_id"])), 1):
            candidate["metrics"][rank_field] = rank
    quality = _quality(candidates, quality_policy)
    finalists = _finalists(candidates, finalist_count)
    quality_eligible = [c for c in candidates if c["quality_eligibility"]["eligible"]]
    review_rows = rows[:1] if source.get("strategy") == "captain_single_lineup_v1" else rows
    selected = {candidate_signature({"players": lineup}, "showdown") for lineup in review_rows}
    control = [c for sig, c in unique.items() if sig in selected]
    control.sort(key=lambda c: c["metrics"]["selector_rank"])
    if len(control) != len(selected): raise ValueError("Control selection is absent from original candidate pool")
    similarity = [_similarity(a, b) for i, a in enumerate(finalists) for b in finalists[i+1:]]
    run = {"season": source.get("season"), "week": source.get("week"), "slate": source.get("slate"),
           "optimizer_run_id": run_id, "projection_run_id": source.get("projection_run_id"),
           "strategy": source.get("strategy"), "data_cutoff_at": cutoff.isoformat(),
           "created_at": created.isoformat(), "configuration_hash": digest(source.get("params") or source.get("strategy_config") or {}),
           "candidate_pool_hash": manifest["sha256"], "candidate_source": manifest["source_path"],
           "candidate_manifest_status": manifest.get("manifest_status", "verified_saved_manifest"),
           "timing_status": "retrospective_unverified_generation" if created >= kickoff else "prelock_saved_run",
           "retrospective_diagnostic": retrospective}
    run["source_snapshot_ids"] = {
        field: sorted({str(row[field]) for row in flat if row.get(field)})
        for field in ("salary_ingest_run_id", "pregame_context_run_id", "ownership_run_id")
    }
    def span(field: str) -> dict:
        values = [c["metrics"][field] for c in candidates if c["metrics"][field] is not None]
        return {"min": min(values), "max": max(values)} if values else {"min": None, "max": None}
    packet = {"contract_id": CONTRACT, "classifier_version": CLASSIFIER, "finalist_policy_version": POLICY,
              "data_readiness": {**readiness, "frozen_at": (frozen or {}).get("frozen_at"),
                                 "evidence_sha256": (frozen or {}).get("sha256"),
                                 "non_production_override": bool((frozen or {}).get("non_production_override") or
                                                                 (allow_incomplete_evidence and not retrospective)),
                                 "incomplete_evidence": bool(incomplete)},
              "run": run, "game": game, "pool_summary": {"candidate_variants": len(pool), "distinct_rosters": len(unique),
                  "requested_entries": requested_entries, "requested_finalists": finalist_count, "finalist_count": len(finalists),
                  "ai_requested_entries": requested_entries,
                  "quality_eligible_distinct": len(quality_eligible),
                  "quality_floor_fraction": quality["minimum_fraction"], "quality_policy": quality,
                  "finalist_coverage": coverage_metrics(finalists),
                  "finalist_algorithm": {"independent_quality_seeds_per_dimension": 3, "reserved_outlier_slots": 3,
                                         "outlier_selector_rank_cutoff": max(10, (len(candidates) + 3) // 4),
                                         "representative_metric": "average_normalized_mean_and_ceiling",
                                         "market_compatibility_is_exclusion": False},
                  "uncovered_eligible_primary_theses": sorted({c["construction"]["primary_thesis_signature"] for c in quality_eligible}
                                                             - {c["construction"]["primary_thesis_signature"] for c in finalists}),
                  "candidate_assessments": [{"candidate_id": c["candidate_id"], "metrics": c["metrics"],
                                             "qb_player_count": sum(p["position"] == "QB" for p in c["players"]),
                                             "construction": c["construction"], "quality_eligibility": c["quality_eligibility"],
                                             "market_compatibility": c["market_compatibility"],
                                             "market_compatibility_reason_codes": c["market_compatibility_reason_codes"]} for c in candidates],
                  "uncovered_eligible_scenarios": sorted({tag for c in quality_eligible for tag in c["construction"]["scenario_tags"]}
                                                         - {tag for c in finalists for tag in c["construction"]["scenario_tags"]}),
                  "projected_mean_range": span("projected_mean"),
                  "ceiling_proxy_range": span("summed_marginal_p90_proxy"),
                  "ownership_range": span("projected_total_ownership"),
                  "data_availability": {
                      "projected_total_ownership_rosters": sum(c["metrics"]["projected_total_ownership"] is not None for c in candidates),
                      "complete_flex_ownership_rosters": sum(c["metrics"]["projected_flex_ownership_sum"] is not None for c in candidates),
                      "market_teams": len(game["market_by_team"]),
                  },
                  "captain_positions": dict(Counter(c["construction"]["captain_position"] or "unknown" for c in candidates)),
                  "team_splits": dict(Counter(c["construction"]["team_split"] for c in candidates)),
                  "scenario_tags": dict(Counter(tag for c in candidates for tag in c["construction"]["scenario_tags"])),
                  "variant_to_candidate": variants},
              "control_selection": [{"candidate_id": c["candidate_id"], "selector_rank": c["metrics"]["selector_rank"],
                                     "objective_score": c["metrics"]["objective_score"],
                                     "projected_mean": c["metrics"]["projected_mean"],
                                     "summed_marginal_p90_proxy": c["metrics"]["summed_marginal_p90_proxy"],
                                     "scenario_tags": c["construction"]["scenario_tags"]} for c in control],
              "baselines": {"projection_only": max(candidates, key=lambda c: ((c["metrics"]["projected_mean"] or -1), c["candidate_id"]))["candidate_id"],
                            "ceiling_only": max(candidates, key=lambda c: ((c["metrics"]["summed_marginal_p90_proxy"] or -1), c["candidate_id"]))["candidate_id"]},
              "finalists": finalists, "similarity": similarity,
              "ai_review_universe": _review_universe(candidates, finalists)}
    from .showdown_review_checklist import build_prelock_checklist
    if run["timing_status"] == "prelock_saved_run":
        packet["prelock_review_checklist"] = build_prelock_checklist(
            candidates, finalists, control, run=run, readiness=packet["data_readiness"], player_lookup=lookup,
            overlap=_similarity(*control) if len(control) == 2 else None)
    if source.get("strategy") == "captain_single_lineup_v1":
        selection = ((source.get("params") or {}).get("strategy_runtime") or {}).get("single_lineup") or {}
        packet["single_lineup_objective"] = {k: selection.get(k) for k in ("contract_id", "objective_weights", "recommended", "why_preferred", "limitations", "cash_probability")}
        packet["single_lineup_objective"]["review_note"] = "Review one lineup for paid-position likelihood. Legacy finalist quality screens and pair similarity are research displays only, not the active proxy objective."
    packet["evidence_hash"] = digest(packet)
    packet["generated_at"] = generated_at or datetime.now(ZoneInfo("UTC")).isoformat()
    return packet


def validate_manual_selection(value: Mapping[str, Any], packet: Mapping[str, Any]) -> dict:
    allowed = {"contract_id", "packet_hash", "selected_at", "selected_candidate_ids", "timing_status",
               "model_name", "reasoning", "football_theses", "rejected_candidates"}
    if set(value) - allowed: raise ValueError("Unknown fields in manual selection contract")
    if value.get("contract_id") != "ai_showdown_manual_selection_v1": raise ValueError("Unknown selection contract")
    if value.get("packet_hash") != packet.get("evidence_hash"): raise ValueError("Packet hash mismatch")
    ids = value.get("selected_candidate_ids") or []
    if len(ids) != packet["pool_summary"]["requested_entries"] or len(set(ids)) != len(ids):
        raise ValueError("Selected candidate IDs must be unique and match requested portfolio size")
    universe = packet.get("ai_review_universe")
    review_candidates = universe["candidates"] if universe is not None else packet["finalists"]
    if not set(ids) <= {row["candidate_id"] for row in review_candidates}:
        raise ValueError("Selection contains a candidate outside the packet review universe (legacy packets: finalists)")
    selected_at = _date(value.get("selected_at"))
    if selected_at is None: raise ValueError("Timezone-aware selection timestamp required")
    if selected_at < _date(packet["run"]["created_at"]):
        raise ValueError("Selection timestamp precedes optimizer run")
    return {**value, "timing_status": "prelock" if selected_at < _date(packet["game"]["kickoff_at"]) else "retrospective"}


def _review_universe_markdown(universe: Mapping[str, Any]) -> list[str]:
    def cell(value: Any) -> str:
        return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    def number(value: Any) -> str:
        return "—" if value is None else f"{value:.2f}"
    def span(value: dict) -> str:
        return "—" if value["min"] is None else f"{number(value['min'])}–{number(value['max'])}"
    summary = universe["summary"]
    lines = ["", "# AI Review Universe", "", "## Universe summary", "",
             f"Generated distinct candidates: {summary['generated_distinct_candidates']} · quality eligible: {summary['quality_eligible_candidates']} · deterministic finalists: {summary['deterministic_finalists']} · excluded by quality: {summary['excluded_by_quality_count']}",
             "Family counts: " + " · ".join(f"{cell(name)}: {count}" for name, count in summary["family_counts"].items()),
             "All quality-eligible distinct rosters are available; there is no additional rank cutoff. Families and rows use average normalized mean/ceiling, then best fraction, selector rank and candidate ID. Top IDs are navigation examples; complete family membership is in JSON.",
             "Summed marginal P90 is a ceiling proxy. Own uses complete projected total ownership; unavailable values are —. Scenario families include every assigned football scenario, so membership overlaps.",
             "", "## Candidate family index", ""]
    for dimension, groups in universe["family_summaries"].items():
        lines += [f"### {cell(dimension.replace('_', ' ').title())}", "",
                  "| Family | Count | Top IDs | Mean range | P90 range | Own range | Market H/M/L | Finalists |",
                  "|---|---:|---|---:|---:|---:|---|---:|"]
        for name, group in groups.items():
            market = group["market_compatibility_distribution"]
            lines.append("| " + " | ".join([cell(name), str(group["candidate_count"]),
                         cell(", ".join(group["top_candidate_ids"])), span(group["projected_mean_range"]),
                         span(group["ceiling_proxy_range"]), span(group["projected_ownership_range"]),
                         "/".join(str(market.get(level, 0)) for level in ("HIGH", "MEDIUM", "LOW")),
                         str(group["deterministic_finalist_count"])]) + " |")
        lines.append("")
    lines += ["## Quality-eligible candidate table", "",
              "| ID | CPT | Split | QB | Primary thesis | Captain script | Mean | P90 | Own | Market | Sel rank | Finalist |",
              "|---|---|---|---|---|---|---:|---:|---:|---|---:|---|"]
    for c in universe["candidates"]:
        m, x = c["metrics"], c["construction"]
        values = [c["candidate_id"], f"{x['captain_player_name']} ({x['captain_team']} {x['captain_archetype']})",
                  x["normalized_team_split"], x["qb_structure"], x["primary_thesis_signature"],
                  x["captain_script_combination"], number(m["projected_mean"]), number(m["summed_marginal_p90_proxy"]),
                  number(m["projected_total_ownership"]), c["market_compatibility"], m["selector_rank"],
                  "yes" if c["is_deterministic_finalist"] else "no"]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    lines += ["", "Companion JSON contains FLEX names, full metrics/ranks, construction attributes and reasons, all scenarios/theses, quality fractions/reasons, risk flags, market reasons and finalist inclusion origin.", ""]
    return lines


def render_markdown(packet: Mapping[str, Any]) -> str:
    run, game, summary = packet["run"], packet["game"], packet["pool_summary"]
    readiness = packet.get("data_readiness") or {}
    checks = {**readiness.get("required_sources", {}), **readiness.get("optional_sources", {})}
    lines = ["# AI Showdown Selection Packet", "",
             "**RETROSPECTIVE DIAGNOSTIC — prelock candidate generation is unverified.**" if run.get("retrospective_diagnostic") else "Frozen prelock evidence; regenerated policy review.",
             "", "## Run identity", "",
             f"Run `{run['optimizer_run_id']}` · {run['season']} Week {run['week']} {run['slate']}",
             f"Strategy `{run['strategy']}` · projection `{run['projection_run_id']}`",
             f"Cutoff {run['data_cutoff_at']} · run created {run['created_at']} · generated {packet['generated_at']}",
             f"Evidence hash `{packet['evidence_hash']}` · original pool hash `{run['candidate_pool_hash']}`",
             "", "## Data readiness", "",
             f"Data readiness: **{readiness.get('status', 'NOT_READY')}**",
             *(["**INCOMPLETE EVIDENCE — historical/debug/non-production diagnostic; required live readiness did not pass.**"]
               if readiness.get("incomplete_evidence") else []),
             *[f"{label}: {checks.get(key, {}).get('status', 'UNVERIFIED')}" for key, label in (
                 ("market", "Market"), ("projection", "Projections"), ("player_status", "Player availability"),
                 ("starting_qb", "Starting QBs"), ("ownership", "Ownership"))],
             f"Frozen at: {readiness.get('frozen_at') or 'unverified'}",
             "", "## Game overview", "", f"{game['matchup']} · kickoff {game['kickoff_at']}",
             (f"Pick'em: equal implied team totals · total {game['total']}" if game.get("pickem") else
              f"Favorite {game['favorite'] or 'unknown'} · underdog {game['underdog'] or 'unknown'} · total {game['total']}"),
             f"Saved team markets: {game['market_by_team']}",
             f"Market source: {game.get('market_source')} · basis: {game.get('market_basis')} (baseline quotes, before scenario conditioning)",
             *(["**Market unavailable:** no baseline quote was saved. Favorite, underdog and total are unknown; market compatibility is descriptive MEDIUM with incomplete-market reasons."] if game.get("market_unavailable_reason") else []),
             "", "## Candidate pool overview", "",
             f"{summary['candidate_variants']} archived variants; {summary['distinct_rosters']} distinct physical rosters; {summary['finalist_count']} finalists.",
             f"Captain positions: {summary['captain_positions']}", f"Team splits: {summary['team_splits']}",
             f"Scenario tags: {summary['scenario_tags']}",
             f"Mean range: {summary['projected_mean_range']} · summed marginal P90 proxy range: {summary['ceiling_proxy_range']} · projected ownership range: {summary['ownership_range']}",
             f"Saved evidence availability: {summary['data_availability']} (missing values are shown as None)",
             f"Control candidate IDs: {', '.join(c['candidate_id'] for c in packet['control_selection'])}",
             "", "## AI review instructions", "",
             (f"Reason about the football game first, identify relevant families/theses, then inspect candidates in those families. Select {summary['requested_entries']} entries from the complete AI Review Universe. The deterministic finalists are a reference/control. "
              if packet.get("ai_review_universe") is not None else f"Select {summary['requested_entries']} entries from the finalists. ") +
             "Treat each as a wager on a plausible football game script. Favor tournament upside and a complementary portfolio. Consider projection, summed marginal P90 ceiling proxy, ownership, salary, captain, correlation, scenario fit, and fragility. Do not invent information absent from this packet. Return candidate IDs and explain each football thesis, winning path, principal failure mode, portfolio fit, and notable strong rejections.",
             "", "## Existing selector control", "", "| Candidate | Rank | Objective | Mean | Summed marginal P90 proxy | Scenario tags |", "|---|---:|---:|---:|---:|---|"]
    for c in packet["control_selection"]:
        lines.append(f"| `{c['candidate_id']}` | {c['selector_rank']} | {c['objective_score']} | {c['projected_mean']} | {c['summed_marginal_p90_proxy']} | {', '.join(c['scenario_tags'])} |")
    if packet.get("single_lineup_objective"):
        lines.extend(["", "## Single-lineup cash-oriented objective", "",
            "One recommendation. Transparent unvalidated proxy; cash probability unavailable. "
            "Evaluate expected points, correlated downside, bounded upside, availability and supported popularity risk. "
            "Do not optimize first place, portfolio diversification or summed P90.",
            json.dumps(packet["single_lineup_objective"], indent=2), ""])
    if packet.get("prelock_review_checklist"):
        from .showdown_review_checklist import checklist_markdown
        lines.extend(checklist_markdown(packet["prelock_review_checklist"]))
    elif run.get("timing_status") == "retrospective_unverified_generation":
        lines.extend(["", "Prelock review checklist unavailable: this run was created after kickoff; prelock generation is unverified.", ""])
    if packet.get("ai_review_universe") is not None:
        lines.extend(_review_universe_markdown(packet["ai_review_universe"]))
    lines.extend(["", "## Deterministic finalists (reference/control)", ""])
    if summary.get("finalist_coverage"):
        coverage = summary["finalist_coverage"]
        lines.extend([f"Policy `{packet['finalist_policy_version']}` · quality rule {summary['quality_policy']}",
                      f"Coverage: {coverage['distinct_primary_thesis_signatures']} primary theses; {coverage['distinct_football_scenarios']} football scenarios; {coverage['distinct_captain_archetypes']} captain archetypes; {coverage['distinct_team_splits']} splits; {coverage['distinct_qb_structures']} QB structures.",
                      f"Market compatibility: {coverage['market_compatibility_counts']}",
                      f"Selection origins: {coverage['inclusion_origin_counts']} · overlapping reasons: {coverage['inclusion_reason_counts']}",
                      f"Selector ranks: {coverage['selector_rank_distribution']} · mean ranks: {coverage['mean_rank_distribution']} · ceiling ranks: {coverage['ceiling_rank_distribution']}", ""])
    for c in packet["finalists"]:
        m, x = c["metrics"], c["construction"]
        lines += [f"### `{c['candidate_id']}` — rank {m['selector_rank']}", "",
                  " · ".join(f"{p['slot']} {p['name']} ({p['team']} {p['position']}, ${p['salary']}, mean {p['projection']}, P90 {p['p90']}, FLEX own {p['flex_ownership']}, status {p['injury_status']}, role {p['role_label']})" for p in c["players"]), "",
                  f"Mean {m['projected_mean']} · summed marginal P90 proxy {m['summed_marginal_p90_proxy']} · objective {m['objective_score']} · salary ${m['salary_used']} · left ${x['salary_remaining']} ({x['salary_bucket']}) · projected ownership {m['projected_total_ownership']}",
                  f"Split {x['team_split']} · QB {x['qb_structure']} · captain {x['captain_archetype']} · tags {', '.join(x['scenario_tags']) or 'none'} · risks {', '.join(x['risk_flags']) or 'none'}",
                  f"Tag reasons {x['scenario_reason_codes']} · included for {', '.join(c['inclusion_reasons'])}", ""]
        if x.get("primary_thesis_signature"):
            lines.extend([f"Primary thesis `{x['primary_thesis_signature']}` · captain side {x['captain_side']}",
                          f"All theses: {x['thesis_signatures']} · reasons: {x['thesis_reason_codes']}",
                          f"Construction attributes: {x['construction_attributes']} · attribute reasons: {x['construction_reason_codes']}",
                          f"Market compatibility **{c['market_compatibility']}**: {c['market_compatibility_reason_codes']}",
                          f"Quality eligibility: {c['quality_eligibility']}", ""])
    lines += ["## Pairwise thesis similarity", "", "These pairs compare the deterministic finalist control. HIGH pairs require 5+ shared players, identical captain, primary scenario, team split and QB structure:", ""]
    for pair in packet["similarity"]:
        if pair["thesis_similarity"] == "HIGH":
            lines.append(f"- `{pair['candidate_a']}` / `{pair['candidate_b']}`: {pair['shared_players']}, {pair['same_captain']}, {pair['same_team_split']}, {', '.join(pair['scenario_overlap']) or 'none'}")
    lines += ["", "## Machine-readable appendix", "", "The companion JSON export uses `ai_showdown_selection_packet_v1` and the evidence hash above.", ""]
    return "\n".join(lines)
