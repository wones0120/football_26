"""Nonbinding two-entry diagnostics over the unchanged frozen AI universe.

No solver, current data source, outcome service or historical research is
imported here. The attention shortlist is navigation, never eligibility.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from itertools import combinations
from typing import Any, Mapping

from .ai_showdown_packet import digest

POLICY = "showdown_ai_selection_review_v1"
REVIEW_CONTRACT = "showdown_two_lineup_review_v1"
FINALIST = "DETERMINISTIC_FINALIST"
OUTSIDER = "RESEARCH_CEILING_OUTSIDER"
UNAVAILABLE = "UNAVAILABLE"
OUTCOME_FIELDS = {"entry_points", "field_rank", "winning_captain", "winning_lineup",
                  "final_score", "hindsight_label", "postgame_construction_frequencies"}


def reject_outcomes(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            name = str(key).lower()
            if name.startswith(("actual_", "postgame", "hindsight", "winning_")) or name in OUTCOME_FIELDS:
                raise ValueError(f"Postgame data is forbidden in prelock review: {key}")
            reject_outcomes(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            reject_outcomes(child)


def verify_packet(packet: Mapping[str, Any]) -> None:
    reject_outcomes(packet)
    if digest({k: v for k, v in packet.items() if k not in {"evidence_hash", "generated_at"}}) != packet.get("evidence_hash"):
        raise ValueError("Frozen packet hash mismatch")
    if packet.get("contract_id") != "ai_showdown_selection_packet_v1" or not packet.get("ai_review_universe"):
        raise ValueError("A complete frozen AI Review Universe is required")


def physical_roster(candidate: Mapping[str, Any]) -> dict[str, dict]:
    players = candidate.get("players") or []
    by_id = {str(p.get("player_id") or ""): p for p in players}
    if (len(players) != 6 or len(by_id) != 6 or "" in by_id
            or sum(p.get("slot") == "CPT" for p in players) != 1
            or sum(p.get("slot") == "FLEX" for p in players) != 5):
        raise ValueError("Six distinct canonical physical players and one Captain required")
    return by_id


def attention_shortlist(packet: Mapping[str, Any]) -> dict:
    """Use saved finalist membership and the audited ceiling ordering only."""
    eligible = packet["ai_review_universe"]["candidates"]
    finalists = [c["candidate_id"] for c in packet["finalists"]]
    outsider_rows = sorted((c for c in eligible if c["candidate_id"] not in set(finalists)),
                           key=lambda c: (-c["quality_eligibility"]["ceiling_fraction"],
                                          c["metrics"]["selector_rank"], c["candidate_id"]))[:10]
    outsiders = [c["candidate_id"] for c in outsider_rows]
    return {"finalist_candidate_ids": finalists, "ceiling_outsider_candidate_ids": outsiders,
            "rows": [{"candidate_id": cid, "attention_group": group}
                     for ids, group in ((finalists, FINALIST), (outsiders, OUTSIDER)) for cid in ids],
            "outsider_ordering": "ceiling_fraction DESC, selector_rank ASC, candidate_id ASC",
            "is_universe_filter": False, "maximum_candidates": len(finalists) + 10}


def _qb_count(construction: dict) -> str:
    return str(len(construction["pass_catchers_by_qb_team"]))


def construction_coverage(packet: Mapping[str, Any]) -> dict:
    generated = packet["pool_summary"]["candidate_assessments"]
    eligible = packet["ai_review_universe"]["candidates"]
    finalist_ids = {c["candidate_id"] for c in packet["finalists"]}
    dimensions = {
        "captain_position": lambda x: [x["captain_position"] or UNAVAILABLE],
        "captain_player": lambda x: [x["captain_player_id"]],
        "captain_side": lambda x: [x["captain_side"]],
        "qb_count": lambda x: [_qb_count(x)],
        "team_split": lambda x: [x["team_split"].split()[0]],
        "football_script": lambda x: x["football_scenarios"],
        "receiver_captain_own_qb": lambda x: (["paired" if x["captain_team"] in x["pass_catchers_by_qb_team"] else "unpaired"]
                                              if x["captain_position"] in {"WR", "TE"} else []),
    }
    defaults = {"captain_position": {"QB", "RB", "WR", "TE", "K", "DST"},
                "captain_side": {"favorite", "underdog"} if packet["game"].get("favorite") else set(),
                "qb_count": {"0", "1", "2"}, "team_split": {"3-3", "4-2", "5-1"},
                "receiver_captain_own_qb": {"paired", "unpaired"},
                "football_script": {"competitive_shootout", "balanced_competitive_game", "low_scoring_game",
                                    "defense_special_teams_game", "favorite_pass_win", "favorite_rush_win",
                                    "underdog_pass_win", "underdog_rush_win", "favorite_dominant_win", "underdog_upset",
                                    "favorite_trailing_comeback", "underdog_trailing_comeback"}}
    result = {}
    for dimension, labels in dimensions.items():
        def family_labels(c):
            if dimension == "qb_count":
                count = (sum(p["position"] == "QB" for p in c["players"]) if "players" in c else
                         c.get("qb_player_count", _qb_count(c["construction"])))
                return [str(count)]
            return labels(c["construction"])
        domains = defaults.get(dimension, set()) | {v for c in generated for v in family_labels(c)}
        rows = []
        for family in sorted(domains):
            gen = [c for c in generated if family in family_labels(c)]
            quality = [c for c in eligible if family in family_labels(c)]
            finalists = [c for c in quality if c["candidate_id"] in finalist_ids]
            missing = [c for c in quality if c["candidate_id"] not in finalist_ids]
            missing.sort(key=lambda c: (-c["quality_eligibility"]["ceiling_fraction"], c["metrics"]["selector_rank"], c["candidate_id"]))
            stage = ("NEVER_GENERATED" if not gen else "FAILED_QUALITY_ELIGIBILITY" if not quality else
                     "QUALITY_ELIGIBLE_NOT_FINALIST" if not finalists else "INCLUDED_IN_COMPLETE_UNIVERSE")
            x = gen[0]["construction"] if gen else {}
            rows.append({"family": family,
                         "label": x.get("captain_player_name", family) if dimension == "captain_player" else family,
                         "generated": len(gen), "quality_eligible": len(quality), "finalists": len(finalists),
                         "included_in_complete_universe": bool(quality), "absence_stage": stage,
                         "highest_ceiling_nonfinalist_id": missing[0]["candidate_id"] if missing else None,
                         "highest_ceiling_nonfinalist_fraction": missing[0]["quality_eligibility"]["ceiling_fraction"] if missing else None})
        result[dimension] = rows
    result["ownership_evidence"] = dict(Counter(c["ownership_availability"] for c in eligible))
    return result


def _ownership_sum(players: dict, ids: set[str]) -> float | None:
    if not ids:
        return None
    values = [players[pid].get("flex_ownership") for pid in ids]
    return sum(values) if all(v is not None for v in values) else None


def compare_pair(a: dict, b: dict) -> dict:
    reject_outcomes([a, b])
    pa, pb = physical_roster(a), physical_roster(b)
    ca, cb = a["construction"], b["construction"]
    shared = set(pa) & set(pb)
    flex_shared = {pid for pid in shared if pa[pid]["slot"] == pb[pid]["slot"] == "FLEX"}
    fractions = [c["quality_eligibility"][k] for c in (a, b) for k in ("mean_fraction", "ceiling_fraction")]
    n = len(shared)
    return {"candidate_ids": [a["candidate_id"], b["candidate_id"]], "shared_player_count": n,
            "overlap_message": f"{n}/6 physical players shared" + (" — concentrated player core" if n >= 5 else ""),
            "shared_player_ids": sorted(shared), "shared_player_names": [pa[pid]["name"] for pid in sorted(shared)],
            "unique_players_across_pair": 12 - n,
            "shared_flex_player_count": len(flex_shared), "shared_flex_player_ids": sorted(flex_shared),
            "same_captain": ca["captain_player_id"] == cb["captain_player_id"],
            "captains": [{k: c[k] for k in ("captain_player_id", "captain_player_name", "captain_position", "captain_team")} for c in (ca, cb)],
            "primary_scripts": [c["primary_football_scenario"] for c in (ca, cb)],
            "primary_theses": [c["primary_thesis_signature"] for c in (ca, cb)],
            "scenario_overlap": sorted(set(ca["football_scenarios"]) & set(cb["football_scenarios"])),
            "team_splits": [c["team_split"] for c in (ca, cb)], "qb_structures": [c["qb_structure"] for c in (ca, cb)],
            "salary_used": [c["metrics"]["salary_used"] for c in (a, b)],
            "means": [c["metrics"]["projected_mean"] for c in (a, b)],
            "p90_proxies": [c["metrics"]["summed_marginal_p90_proxy"] for c in (a, b)],
            "mean_fractions": [c["quality_eligibility"]["mean_fraction"] for c in (a, b)],
            "ceiling_fractions": [c["quality_eligibility"]["ceiling_fraction"] for c in (a, b)],
            "min_mean_fraction": min(c["quality_eligibility"]["mean_fraction"] for c in (a, b)),
            "min_ceiling_fraction": min(c["quality_eligibility"]["ceiling_fraction"] for c in (a, b)),
            "minimum_normalized_quality": min(fractions), "average_normalized_quality": sum(fractions) / 4,
            "market_compatibilities": [c["market_compatibility"] for c in (a, b)],
            "risk_flags": [c["risk_flags"] for c in (ca, cb)],
            "ownership_availability": [c.get("ownership_availability", UNAVAILABLE) for c in (a, b)],
            "projected_total_ownership": [c["metrics"].get("projected_total_ownership") for c in (a, b)],
            "shared_core_projected_flex_ownership": [_ownership_sum(p, shared) for p in (pa, pb)],
            "unique_player_ids_by_lineup": [sorted(set(pa) - shared), sorted(set(pb) - shared)],
            "informational_only": True}


def lower_overlap_alternatives(candidates: list[dict], proposed: dict) -> dict:
    """Fixed audit rule: joint minimum, average quality, exact IDs. No cap on selection."""
    rule = "minimum of both mean/ceiling fractions DESC, average of four fractions DESC, candidate IDs ASC"
    if proposed["shared_player_count"] < 5:
        return {"status": "NOT_NEEDED", "ordering": rule, "alternatives": [], "feasible_pair_count": None}
    reject_outcomes(candidates)
    eligible = sorted((c for c in candidates if c["quality_eligibility"]["eligible"]), key=lambda c: c["candidate_id"])
    rosters = {c["candidate_id"]: set(physical_roster(c)) for c in eligible}
    best = []
    count = 0
    for a, b in combinations(eligible, 2):
        if len(rosters[a["candidate_id"]] & rosters[b["candidate_id"]]) > 4:
            continue
        fractions = [c["quality_eligibility"][k] for c in (a, b) for k in ("mean_fraction", "ceiling_fraction")]
        key = (-min(fractions), -sum(fractions) / 4, (a["candidate_id"], b["candidate_id"]))
        count += 1
        best.append((key, a, b))
        best.sort(key=lambda entry: entry[0])
        del best[3:]
    best = [compare_pair(a, b) for _, a, b in best]
    by_id = {c["candidate_id"]: c for c in candidates}
    current_players = set().union(*(set(physical_roster(by_id[cid])) for cid in proposed["candidate_ids"]))
    names = {p["player_id"]: p["name"] for c in candidates for p in c["players"]}
    for pair in best:
        new_players = set().union(*(set(physical_roster(by_id[cid])) for cid in pair["candidate_ids"]))
        pair["quality_opportunity_cost"] = {
            key: {"current": proposed[key], "alternative": pair[key], "current_minus_alternative": proposed[key] - pair[key]}
            for key in ("min_mean_fraction", "min_ceiling_fraction", "minimum_normalized_quality")}
        pair["player_substitutions"] = {"removed": [{"player_id": pid, "name": names[pid]} for pid in sorted(current_players - new_players)],
                                        "added": [{"player_id": pid, "name": names[pid]} for pid in sorted(new_players - current_players)]}
        pair["scenario_substitutions"] = {"current": proposed["primary_scripts"], "alternative": pair["primary_scripts"]}
    return {"status": "AVAILABLE" if best else "NO_ELIGIBLE_LOWER_OVERLAP_PAIR", "ordering": rule,
            "feasible_pair_count": count, "alternatives": best, "automatic_selection": False}


def build_review(packet: Mapping[str, Any]) -> dict:
    verify_packet(packet)
    candidates = deepcopy(packet["ai_review_universe"]["candidates"])
    # Ownership requires the existing packet's fresh, source-backed provenance.
    provenance = (packet.get("prelock_review_checklist") or {}).get("ownership_provenance") or {}
    sourced = provenance.get("status") == "available"
    for c in candidates:
        physical_roster(c)
        c["ownership_availability"] = "AVAILABLE" if sourced and c["metrics"].get("projected_total_ownership") is not None else UNAVAILABLE
        if not sourced:
            for key in list(c["metrics"]):
                if "ownership" in key or key.startswith("players_below_"):
                    c["metrics"][key] = None
            for p in c["players"]:
                p["flex_ownership"] = p["captain_ownership"] = None
    safe_packet = {**packet, "ai_review_universe": {**packet["ai_review_universe"], "candidates": candidates}}
    shortlist = attention_shortlist(safe_packet)
    frozen_hash = packet["data_readiness"].get("evidence_sha256")
    identity = {**packet["run"], "game_id": packet["game"]["game_id"], "kickoff_at": packet["game"]["kickoff_at"],
                "evidence_cutoff": packet["run"]["data_cutoff_at"],
                "frozen_source_evidence_hash": frozen_hash or packet["evidence_hash"],
                "frozen_source_hash_basis": "generation_snapshot" if frozen_hash else "legacy_packet_evidence",
                "ai_packet_hash": packet["evidence_hash"], "ai_packet_version": packet["contract_id"],
                "ai_packet_finalist_policy_version": packet["finalist_policy_version"],
                "ai_packet_classifier_version": packet["classifier_version"],
                "review_policy_version": POLICY}
    return {"contract_id": REVIEW_CONTRACT, "protocol": POLICY, "nonbinding": True, "run_identity": identity,
            "data_readiness": packet["data_readiness"], "game": packet["game"],
            "quality_policy": packet["pool_summary"]["quality_policy"], "attention_shortlist": shortlist,
            "ai_review_instructions": "Recommend exactly two exact candidate IDs from the complete eligible universe. Review football scripts, canonical overlap and quality-preserving alternatives. Return explicitly considered IDs separately from displayed IDs, written reasoning, two theses, complementarity, rejected IDs with reasons, alternatives considered and any deliberate high-overlap exception. Use only this frozen prelock evidence; ownership gaps are UNAVAILABLE. This is a nonbinding recommendation, never user approval or proof of entry.",
            "candidates": candidates, "coverage": construction_coverage(safe_packet),
            "ownership_provenance": provenance or {"status": "unavailable"},
            "counts": {"quality_eligible": len(candidates), "finalists": len(shortlist["finalist_candidate_ids"]),
                       "ceiling_outsiders": len(shortlist["ceiling_outsider_candidate_ids"])},
            "control_candidate_ids": [c["candidate_id"] for c in packet["control_selection"]],
            "selection_status": "AI_SELECTION_UNKNOWN",
            "limitations": ["Different Captain labels do not establish independent football exposure.",
                            "Summed marginal P90 is a proxy, not a calibrated lineup P90.",
                            "Coverage absence is descriptive, not evidence of a generation defect.",
                            "Displayed candidates are not recorded as explicitly considered."]}


def review_comparison(review: Mapping[str, Any], candidate_ids: list[str]) -> dict:
    by_id = {c["candidate_id"]: c for c in review["candidates"]}
    if len(candidate_ids) != 2 or len(set(candidate_ids)) != 2 or not set(candidate_ids) <= by_id.keys():
        raise ValueError("Exactly two distinct candidate IDs from this frozen quality-eligible universe are required")
    pair = compare_pair(*(by_id[cid] for cid in candidate_ids))
    return {"proposed_pair": pair, "alternative_portfolio": lower_overlap_alternatives(review["candidates"], pair)}


def review_markdown(review: dict) -> str:
    lines = ["", "## AI Two-Lineup Selection Review (nonbinding)", "",
             f"Policy `{POLICY}` · complete eligible universe {review['counts']['quality_eligible']} · finalists {review['counts']['finalists']} · ceiling outsiders {review['counts']['ceiling_outsiders']}",
             "The shortlist is an attention aid. Recommend exactly two exact candidate IDs from the COMPLETE eligible universe. "
             "Return explicitly considered IDs separately from displayed IDs, rejected IDs with reasons, each football thesis, complementarity, "
             "alternatives considered and any accepted high-overlap exception. Do not claim consideration from rendering.",
             "Use canonical physical players regardless of Captain/FLEX slot; unique players = 12 - shared players. "
             "For 5+ shared players compare lower-overlap alternatives using minimum of both mean/ceiling fractions, average quality, then IDs. "
             "Report quality cost; no overlap cap or automatic selection applies. Missing ownership is UNAVAILABLE.", "",
             "| Group | Exact candidate ID | Selector rank | Mean | P90 proxy | Mean fraction | Ceiling fraction | Captain |",
             "|---|---|---:|---:|---:|---:|---:|---|"]
    by_id = {c["candidate_id"]: c for c in review["candidates"]}
    for item in review["attention_shortlist"]["rows"]:
        c = by_id[item["candidate_id"]]
        m, q, x = c["metrics"], c["quality_eligibility"], c["construction"]
        lines.append(f"| {item['attention_group']} | `{c['candidate_id']}` | {m['selector_rank']} | {m['projected_mean']} | {m['summed_marginal_p90_proxy']} | {q['mean_fraction']:.4f} | {q['ceiling_fraction']:.4f} | {x['captain_player_name']} |")
    lines += ["", "Companion JSON `two_lineup_selection_review` includes complete canonical rosters, coverage, ownership evidence and run hashes. "
              "In the app open AI Candidate Review, paste exact IDs/reasoning, mark explicitly considered candidates, compare alternatives, "
              "then append PROPOSED, SELECTED and USER_APPROVED decisions before kickoff. Download the immutable record. "
              "Confirm actual entries later from an imported, canonically resolved learning report; recommendation/export alone never proves entry.", ""]
    return "\n".join(lines)
