"""Research-only, two-phase Showdown audit. Never imported by production.

freeze reads saved inputs only and persists ALL policy IDs/pairs. evaluate cannot
select anything: it verifies the freeze, then attaches separate outcome evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/showdown_selection_diversity_audit"
RUNS = ["ffb8acf8-2e31-414e-81da-417d6d82c584",
        "dc21b3ab-c330-487c-bb88-766f9a71f04c",
        "3a41af88-a28c-41b1-888c-462ddcd7d74d"]
SOURCES = [ROOT / f"artifacts/ai_showdown_selection_packet/policy_v2/{r}-source.json"
           for r in RUNS[:2]] + [OUT / f"{RUNS[2]}-source.json"]
PACKETS = [next((ROOT / f"artifacts/ai_showdown_selection_packet/review_universe_v1/{day}").glob("*.json"))
           for day in ("thursday", "sunday")] + [OUT / "week5_packet.json"]
POLICIES = {
    "status": "research_only_no_promotion_no_outcome_fitting",
    "attention": {
        "A_finalists": "Saved v2 packet finalists only; not the actual optimizer selected set.",
        "B_top_ceiling_outsiders": {"N": [3, 5, 8, 10], "ordering": "ceiling_fraction desc, selector_rank asc, candidate_id asc"},
        "C_ceiling_band": {"thresholds": [.95, .97, .99], "rule": "finalists UNION eligible nonfinalists with ceiling_fraction >= threshold"},
        "D_ceiling_market": {"thresholds": [.95, .97, .99], "rule": "C outsiders AND saved compatibility in MEDIUM,HIGH"},
        "E_ceiling_differentiated": {"threshold": .95, "max_added": 5, "underrepresented_max_finalists": 1,
            "rule": "B ordering; captain_script_combination has <=1 finalist OR primary_thesis_signature has <=1 finalist"},
        "selection_from_attention_set": "Top two eligible by saved objective_score; ties selector_rank asc, candidate_id asc. Proxy only, never reconstructed AI judgment.",
    },
    "pair": {
        "universe": "all distinct packet-quality-eligible canonical rosters; no new quality screen",
        "control": "Maximum saved objective_score sum; ties sorted candidate IDs ascending; proxy has no historical exposure constraints",
        "A_different_captains": "Control constrained to different canonical CPT player IDs",
        "B_different_archetypes": "Control constrained to different saved captain_archetype",
        "B_different_scripts": "Control constrained to different primary_football_scenario (not merely different full thesis strings)",
        "C_shared_le4": "Control constrained to shared physical-player count <=4",
        "D_shared_le3": "Control constrained to shared physical-player count <=3",
        "E_complementarity": {"lambda": [0, .01, .05, .10],
            "individual_quality": "average of both lineups' mean_fraction and ceiling_fraction (four values)",
            "complementarity": "unweighted average of (6-shared)/6, different captain, different primary thesis, 1-scenario Jaccard similarity; empty scenarios contribute 0",
            "score": "individual_quality + lambda * complementarity; same ID tie break"},
        "quality_cost": {"overlap_caps": [5, 4, 3, 2], "joint_quality_bands": [.95, .90],
            "rule": "Among feasible pairs maximize minimum of all four mean/ceiling fractions; ties average quality desc, IDs asc. Also freeze best objective pair in each joint band.",
            "additional_question": "For caps 4,3 find maximum minimum ceiling; retain candidate minima and joint-quality optima without outcome selection."},
    },
    "evaluation": {"actuals": "canonical base DK scores; CPT multiplied once by 1.5; missing/conflicting scores never imputed",
        "field_rank": "competition rank = 1 + number strictly greater; percentile interval from number below and at-or-below; top bands include boundary ties",
        "aggregation": "Only prelock_saved_run enters cross-slate counterfactual summary; late-generated slate has no replay selections"},
}


def read(path):
    return json.loads(Path(path).read_text())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def reject_outcomes(value):
    """Fail closed even for deeply nested, unknown postgame fields."""
    if isinstance(value, dict):
        for key, child in value.items():
            k = key.lower()
            if (k.startswith(("actual", "postgame", "hindsight", "top_field", "winning_lineup", "learning_report"))
                    or k in {"contest_rank", "contest_result", "field_rank", "entry_points", "outcome_tag", "final_score"}):
                raise ValueError(f"Postgame field in prelock selection inputs: {key}")
            reject_outcomes(child)
    elif isinstance(value, list):
        for child in value:
            reject_outcomes(child)


def signature(players):
    ids = [p["player_id"] for p in players]
    caps = [p["player_id"] for p in players if p.get("slot", p.get("roster_position")) == "CPT"]
    if len(ids) != 6 or len(set(ids)) != 6 or len(caps) != 1 or not all(ids):
        raise ValueError("Six distinct canonical physical players and one captain required")
    return caps[0], tuple(sorted(ids))


def chronology_safe(created_at, cutoff_at, kickoff_at):
    times = [datetime.fromisoformat(s) for s in (created_at, cutoff_at, kickoff_at)]
    if any(t.tzinfo is None for t in times):
        return False
    created, cutoff, kickoff = times
    return cutoff <= created < kickoff


def candidates_from_saved(packet, source):
    from backend.app.product_services.ai_showdown_packet import _saved_candidates, _players, _date
    raw, manifest = _saved_candidates(source)
    reject_outcomes(raw)
    if manifest["sha256"] != packet["run"]["candidate_pool_hash"]:
        raise ValueError("Saved source and frozen packet pool hashes differ")
    frozen = source["params"].get("showdown_evidence_snapshot") or {}
    pool = frozen.get("player_pool") or (source.get("player_pool") or {}).get("rows", [])
    lookup = {p["player_id"]: p for p in pool}
    # Selected rows are saved in this same run; never consult current player data.
    for lineup in source["results"]:
        for p in lineup:
            lookup[p["player_id"]] = {**p, **lookup.get(p["player_id"], {})}
    by_rank = {r["rank"]: r for r in raw}
    variants = defaultdict(list)
    for v in packet["pool_summary"]["variant_to_candidate"]:
        variants[v["candidate_id"]].append(v["rank"])
    finalists = {c["candidate_id"]: c for c in packet["finalists"]}
    review = {c["candidate_id"] for c in packet["ai_review_universe"]["candidates"]}
    result = []
    for assessment in packet["pool_summary"]["candidate_assessments"]:
        reject_outcomes(assessment)
        rank = assessment["metrics"]["selector_rank"]
        players = _players(by_rank[rank], lookup, _date(source["data_cutoff_at"]))
        # Ownership uses the same frozen readiness semantics as the saved packet.
        if frozen and not packet.get("data_readiness", {}).get("ownership", {}).get("ownership_fresh"):
            for p in players:
                p["flex_ownership"] = p["captain_ownership"] = None
        cid = assessment["candidate_id"]
        sig = signature(players)
        if any(signature(by_rank[r]["players"]) != sig for r in variants[cid]):
            raise ValueError("Variant mapping changes canonical roster identity")
        c = {**assessment, "players": players, "variant_ranks": sorted(variants[cid]),
             "candidate_rank_alias": f"{source['job_id']}:{rank}",
             "is_deterministic_finalist": cid in finalists,
             "finalist_inclusion_origin": finalists.get(cid, {}).get("inclusion_origin"),
             "finalist_inclusion_reasons": finalists.get(cid, {}).get("inclusion_reasons", []),
             "visible_in_ai_review_universe": cid in review,
             "saved_production_variant_quality_flags": [{"rank": r, "eligible": by_rank[r].get("quality_eligible")} for r in variants[cid]],
             "saved_generation_scenarios": sorted({by_rank[r].get("scenario_id", "unknown") for r in variants[cid]})}
        result.append(c)
    if len({signature(c["players"]) for c in result}) != len(result):
        raise ValueError("Duplicate distinct-roster identity")
    reject_outcomes(result)
    return sorted(result, key=lambda c: c["metrics"]["selector_rank"])


def quality(c):
    return (c["quality_eligibility"]["mean_fraction"] + c["quality_eligibility"]["ceiling_fraction"]) / 2


def preferred(c):
    return (-c["metrics"]["objective_score"], c["metrics"]["selector_rank"], c["candidate_id"])


def attention_sets(candidates):
    reject_outcomes(candidates)
    eligible = [c for c in candidates if c["quality_eligibility"]["eligible"]]
    finalists = [c for c in eligible if c["is_deterministic_finalist"]]
    outsiders = sorted((c for c in eligible if not c["is_deterministic_finalist"]),
                       key=lambda c: (-c["quality_eligibility"]["ceiling_fraction"], c["metrics"]["selector_rank"], c["candidate_id"]))
    sets = {"A_finalists": finalists}
    for n in POLICIES["attention"]["B_top_ceiling_outsiders"]["N"]:
        sets[f"B_top{n}"] = finalists + outsiders[:n]
    for threshold in POLICIES["attention"]["C_ceiling_band"]["thresholds"]:
        strong = [c for c in outsiders if c["quality_eligibility"]["ceiling_fraction"] >= threshold]
        sets[f"C_{threshold:.2f}"] = finalists + strong
        sets[f"D_{threshold:.2f}"] = finalists + [c for c in strong if c["market_compatibility"] in {"MEDIUM", "HIGH"}]
    cc = Counter(c["construction"]["captain_script_combination"] for c in finalists)
    tc = Counter(c["construction"]["primary_thesis_signature"] for c in finalists)
    sets["E_differentiated_top5"] = finalists + [c for c in outsiders if c["quality_eligibility"]["ceiling_fraction"] >= .95
        and (cc[c["construction"]["captain_script_combination"]] <= 1 or tc[c["construction"]["primary_thesis_signature"]] <= 1)][:5]
    result = {}
    finalist_ids = {c["candidate_id"] for c in finalists}
    for name, rows in sets.items():
        result[name] = {"visible_candidate_ids": [c["candidate_id"] for c in rows],
                        "added_candidate_ids": [c["candidate_id"] for c in rows if c["candidate_id"] not in finalist_ids],
                        "counterfactual_prelock_policy_selection": [c["candidate_id"] for c in sorted(rows, key=preferred)[:2]]}
    return result


def ownership_sum(players, ids):
    values = [players[pid].get("flex_ownership") for pid in ids]
    return sum(values) if all(x is not None for x in values) else None


def pair_features(a, b):
    reject_outcomes([a, b])
    pa, pb = {p["player_id"]: p for p in a["players"]}, {p["player_id"]: p for p in b["players"]}
    ca, cb = a["construction"], b["construction"]
    shared = set(pa) & set(pb)
    flexa = {pid for pid, p in pa.items() if p["slot"] == "FLEX"}
    flexb = {pid for pid, p in pb.items() if p["slot"] == "FLEX"}
    sa, sb = set(ca["football_scenarios"]), set(cb["football_scenarios"])
    scenario_distance = 1 - len(sa & sb) / len(sa | sb) if sa | sb else 0
    n = len(shared)
    different_captain = ca["captain_player_id"] != cb["captain_player_id"]
    thesis_diff = ca["primary_thesis_signature"] != cb["primary_thesis_signature"]
    vals = [c["quality_eligibility"][k] for c in (a, b) for k in ("mean_fraction", "ceiling_fraction")]
    return {"candidate_ids": sorted([a["candidate_id"], b["candidate_id"]]),
        "shared_player_count": n, "player_core_overlap": n / 6,
        "player_core_classification": "high_player_core_overlap" if n >= 5 else "lower_player_core_overlap",
        "unique_players_across_pair": 12 - n, "shared_player_ids": sorted(shared),
        "shared_flex_player_count": len(flexa & flexb), "shared_flex_player_ids": sorted(flexa & flexb),
        "identical_physical_roster": n == 6, "duplicate_lineup": signature(a["players"]) == signature(b["players"]),
        "overlap_bucket": "0-2" if n <= 2 else str(n) if n < 6 else "6_same_physical_roster",
        "same_captain": not different_captain, "different_captain": different_captain,
        "captain_positions": [ca["captain_position"], cb["captain_position"]],
        "captain_archetypes_differ": ca["captain_archetype"] != cb["captain_archetype"],
        "captain_sides": [ca["captain_side"], cb["captain_side"]],
        "primary_thesis_different": thesis_diff, "primary_theses": [ca["primary_thesis_signature"], cb["primary_thesis_signature"]],
        "primary_script_different": ca["primary_football_scenario"] != cb["primary_football_scenario"],
        "football_scenario_overlap": sorted(sa & sb), "scenario_distance": scenario_distance,
        "team_split_different": ca["team_counts"] != cb["team_counts"], "team_splits": [ca["team_counts"], cb["team_counts"]],
        "qb_structure_different": ca["qb_structure"] != cb["qb_structure"], "qb_structures": [ca["qb_structure"], cb["qb_structure"]],
        "common_player_projected_flex_ownership_by_lineup": [ownership_sum(pa, shared), ownership_sum(pb, shared)],
        "unique_player_projected_flex_ownership_by_lineup": [ownership_sum(pa, set(pa)-shared), ownership_sum(pb, set(pb)-shared)],
        "ownership_basis": "FLEX projected ownership for physical exposure, never postgame ownership; role-specific candidate metrics retained separately",
        "means": [c["metrics"]["projected_mean"] for c in (a, b)],
        "p90_proxies": [c["metrics"]["summed_marginal_p90_proxy"] for c in (a, b)],
        "min_mean_fraction": min(c["quality_eligibility"]["mean_fraction"] for c in (a, b)),
        "min_p90_fraction": min(c["quality_eligibility"]["ceiling_fraction"] for c in (a, b)),
        "minimum_normalized_quality": min(vals), "average_normalized_quality": sum(vals)/4,
        "combined_normalized_quality": sum(vals)/2,
        "objective_sum": sum(c["metrics"]["objective_score"] for c in (a, b)),
        "market_compatibilities": [c["market_compatibility"] for c in (a, b)],
        "risk_flags": [ca["risk_flags"], cb["risk_flags"]],
        "complementarity": ((6-n)/6 + different_captain + thesis_diff + scenario_distance)/4}


def best_pair(pairs, score):
    return min(pairs, key=lambda p: (-score(p), tuple(p["candidate_ids"]))) if pairs else None


def pair_selections(pairs):
    reject_outcomes(pairs)
    control = best_pair(pairs, lambda p: p["objective_sum"])
    results = {"control": control}
    for name, predicate in {
        "A_different_captains": lambda p: p["different_captain"],
        "B_different_archetypes": lambda p: p["captain_archetypes_differ"],
        "B_different_scripts": lambda p: p["primary_script_different"],
        "C_shared_le4": lambda p: p["shared_player_count"] <= 4,
        "D_shared_le3": lambda p: p["shared_player_count"] <= 3,
    }.items():
        results[name] = best_pair([p for p in pairs if predicate(p)], lambda p: p["objective_sum"])
    for weight in POLICIES["pair"]["E_complementarity"]["lambda"]:
        results[f"E_lambda_{weight:.2f}"] = best_pair(pairs, lambda p: p["average_normalized_quality"] + weight*p["complementarity"])
    costs = {}
    for cap in POLICIES["pair"]["quality_cost"]["overlap_caps"]:
        feasible = [p for p in pairs if p["shared_player_count"] <= cap]
        balanced = min(feasible, key=lambda p: (-p["minimum_normalized_quality"], -p["average_normalized_quality"], p["candidate_ids"])) if feasible else None
        costs[str(cap)] = {"feasible_pair_count": len(feasible), "best_joint_quality_pair": balanced,
            "best_minimum_ceiling_pair": best_pair(feasible, lambda p: p["min_p90_fraction"]),
            "joint_band_pairs": {f"{t:.2f}": {"feasible_pair_count": sum(p["minimum_normalized_quality"] >= t for p in feasible),
                "selected_pair": best_pair([p for p in feasible if p["minimum_normalized_quality"] >= t], lambda p: p["objective_sum"])}
                for t in POLICIES["pair"]["quality_cost"]["joint_quality_bands"]}}
    return results, costs


def freeze():
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "prelock_policy_freeze.json"
    if target.exists():
        raise ValueError("Existing freeze is immutable; use a new audit directory for a changed experiment")
    slates = []
    for source_path, packet_path in zip(SOURCES, PACKETS):
        source, packet = read(source_path), read(packet_path)
        candidates = candidates_from_saved(packet, source)
        eligible = [c for c in candidates if c["quality_eligibility"]["eligible"]]
        safe = chronology_safe(packet["run"]["created_at"], packet["run"]["data_cutoff_at"], packet["game"]["kickoff_at"])
        if safe != (packet["run"]["timing_status"] == "prelock_saved_run"):
            raise ValueError("Packet chronology status contradicts saved timestamps")
        pairs = [pair_features(a, b) for a, b in combinations(eligible, 2)]
        selected, costs = pair_selections(pairs) if safe else ({}, {})
        selected_signatures = [signature(rows) for rows in source["results"]]
        candidate_by_sig = {signature(c["players"]): c["candidate_id"] for c in candidates}
        if any(s not in candidate_by_sig for s in selected_signatures):
            raise ValueError("Historical deterministic selection missing from frozen universe")
        historical = [candidate_by_sig[s] for s in selected_signatures]
        pair_path = OUT / f"{source['job_id']}-prelock-pairs.json.gz"
        # Fixed gzip timestamp makes this artifact reproducible across reruns.
        with pair_path.open("wb") as f:
            with gzip.GzipFile(fileobj=f, mode="wb", mtime=0, filename="") as g:
                g.write(json.dumps(pairs, sort_keys=True, separators=(",", ":")).encode())
        slates.append({"run_id": source["job_id"], "week": source["week"], "slate": source["slate"],
            "source_path": str(source_path.relative_to(ROOT)), "source_sha256": file_hash(source_path),
            "packet_path": str(packet_path.relative_to(ROOT)), "packet_sha256": file_hash(packet_path),
            "evidence_hash": packet["evidence_hash"], "candidate_pool_hash": packet["run"]["candidate_pool_hash"],
            "chronology": {"status": packet["run"]["timing_status"], "run_created_at": packet["run"]["created_at"],
                "data_cutoff_at": packet["run"]["data_cutoff_at"], "kickoff_at": packet["game"]["kickoff_at"],
                "packet_generated_at": packet["generated_at"], "prelock_replay_available": safe,
                "annotation_caveat": "Packet/classifier annotations were serialized after kickoff. Prelock saved generation is checked separately; no historical AI judgment or contemporaneous packet-download record is certified.",
                "manifest_status": packet["run"].get("candidate_manifest_status")},
            "counts": {"saved_variants": packet["pool_summary"]["candidate_variants"], "distinct_rosters": len(candidates),
                "quality_eligible": len(eligible), "deterministic_packet_finalists": sum(c["is_deterministic_finalist"] for c in candidates),
                "complete_ai_review_universe": sum(c["visible_in_ai_review_universe"] for c in candidates)},
            "quality_policy": packet["pool_summary"]["quality_policy"],
            "candidates": candidates, "historical_deterministic_selected_ids": historical,
            "actual_recorded_ai_selection": {"status": "unknown_no_immutable_record_found", "considered_candidate_ids": None, "selected_candidate_ids": None},
            "attention_policies": attention_sets(candidates) if safe else {},
            "counterfactual_pair_policies": selected, "quality_cost_of_diversification": costs,
            "pair_artifact": str(pair_path.relative_to(ROOT)), "pair_artifact_sha256": file_hash(pair_path),
            "pairwise_overlap_distribution": dict(Counter(p["overlap_bucket"] for p in pairs)),
            "pair_count": len(pairs), "different_captain_with_5_shared_count": sum(p["different_captain"] and p["shared_player_count"] == 5 for p in pairs)})
    value = {"contract_id": "showdown_selection_diversity_prelock_freeze_v1", "frozen_at": datetime.now(timezone.utc).isoformat(),
        "postgame_labels_loaded_by_replay": False,
        "known_prior_outcomes": "User supplied Week5 score/rank and earlier post-slate research already exists. This retrospective experiment cannot claim outcome-blind policy invention. The generic parameter grid is fixed before this replay's outcome joins; no adaptive tuning.",
        "policy_definitions": POLICIES, "policy_definitions_hash": digest(POLICIES),
        "selection_code_sha256": file_hash(__file__),
        "annotation_code_sha256": file_hash(ROOT / "backend/app/product_services/ai_showdown_packet.py"),
        "slates": slates}
    write(target, value)
    print(json.dumps({"freeze_sha256": file_hash(target), "slates": [{"run": s["run_id"], "counts": s["counts"], "safe": s["chronology"]["prelock_replay_available"]} for s in slates]}))


def verify_freeze():
    f = read(OUT / "prelock_policy_freeze.json")
    if f["selection_code_sha256"] != file_hash(__file__) or f["policy_definitions_hash"] != digest(POLICIES):
        raise ValueError("Selection code or definitions changed after freeze")
    if f["annotation_code_sha256"] != file_hash(ROOT / "backend/app/product_services/ai_showdown_packet.py"):
        raise ValueError("Annotation code changed after freeze")
    for s in f["slates"]:
        for prefix in ("source", "packet", "pair_artifact"):
            path = s.get(prefix + "_path", s.get(prefix))
            if file_hash(ROOT / path) != s[prefix + "_sha256"]:
                raise ValueError(f"Frozen {prefix} evidence mutated")
    return f


def export_outcomes():
    """Local database SELECTs only; called exclusively after a verified freeze."""
    frozen = verify_freeze()
    from backend.app.db import engine
    from sqlalchemy import text
    event = {"read_started_at": datetime.now(timezone.utc).isoformat(), "freeze_sha256": file_hash(OUT / "prelock_policy_freeze.json")}
    write(OUT / "postgame_read_manifest.json", event)
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        for s in frozen["slates"]:
            params = {"season": 2026, "week": s["week"], "slate": s["slate"]}
            def rows(query, p=params):
                return [dict(r) for r in connection.execute(text(query), p).mappings()]
            observations = rows("""SELECT o.* FROM target.contest_ownership_observation o JOIN target.dfs_contest c USING(contest_id)
                WHERE c.season=:season AND c.week=:week AND upper(c.slate_id)=:slate""")
            contests = rows("SELECT * FROM target.dfs_contest WHERE season=:season AND week=:week AND upper(slate_id)=:slate")
            entries = rows("""SELECT e.* FROM target.dfs_contest_entry_result e JOIN target.dfs_contest c USING(contest_id)
                WHERE c.season=:season AND c.week=:week AND upper(c.slate_id)=:slate""")
            assignments = rows("""SELECT a.*,p.optimizer_run_id FROM target.contest_entry_assignment a
                JOIN target.lineup_portfolio p USING(portfolio_id)
                WHERE p.season=:season AND p.week=:week AND upper(p.slate_id)=:slate""")
            # Saved reports provide exact entered canonical rosters and residuals.
            reports = rows("""SELECT report_id,created_at,report_json FROM target.slate_learning_report
                WHERE season=:season AND week=:week AND upper(slate)=:slate ORDER BY created_at DESC""")
            payload = {"observations": observations, "contests": contests, "field_entries": entries,
                       "assignments": assignments, "saved_learning_reports": reports}
            path = OUT / f"{s['run_id']}-outcomes.json.gz"
            with gzip.open(path, "wt") as stream:
                json.dump(payload, stream, default=str)
            print(s["run_id"], "observations", len(observations), "field entries", len(entries), "reports", len(reports))
    verify_freeze()


def score_candidate(candidate, actuals):
    if any(p["player_id"] not in actuals for p in candidate["players"]):
        return None
    return round(sum(actuals[p["player_id"]]*(1.5 if p["slot"] == "CPT" else 1) for p in candidate["players"]), 5)


def field_metric(score, scores):
    if score is None or not scores:
        return None
    n = len(scores)
    greater = sum(x > score + 1e-7 for x in scores)
    below = sum(x < score - 1e-7 for x in scores)
    return {"competition_rank": greater + 1, "scored_entries": n,
        "percentile_strictly_below": 100*below/n, "percentile_at_or_below": 100*(n-greater)/n,
        "top1pct": greater < math.ceil(n*.01), "top5pct": greater < math.ceil(n*.05), "top10pct": greater < math.ceil(n*.10)}


def summarize_ids(ids, outcomes, fields, best_eligible=None, best_generated=None):
    scored = [(cid, outcomes.get(cid)) for cid in ids if outcomes.get(cid) is not None]
    if not scored:
        return {"candidate_count": len(ids), "scoreable_count": 0, "best_actual": None}
    best_id, best = min(scored, key=lambda item: (-item[1], item[0]))
    return {"candidate_count": len(ids), "scoreable_count": len(scored), "best_candidate_id": best_id,
        "best_actual": best, "max_actual": best, "average_actual": sum(v for _, v in scored)/len(scored),
        "selection_regret_vs_eligible": None if best_eligible is None else best_eligible-best,
        "selection_regret_vs_generated": None if best_generated is None else best_generated-best,
        "field_metrics": {fid: field_metric(best, values) for fid, values in fields.items()}}


def evaluate():
    frozen = verify_freeze()
    from backend.app.product_services.optimizer_effectiveness import actual_points_by_player
    audit = {"contract_id": "showdown_selection_regret_and_portfolio_diversity_audit_v1", "research_only": True,
        "freeze_sha256": file_hash(OUT / "prelock_policy_freeze.json"), "policy_definitions": frozen["policy_definitions"],
        "known_prior_outcomes_caveat": frozen["known_prior_outcomes"], "slates": []}
    for s in frozen["slates"]:
        path = OUT / f"{s['run_id']}-outcomes.json.gz"
        with gzip.open(path, "rt") as stream:
            labels = json.load(stream)
        actuals = actual_points_by_player(labels["observations"], "showdown")
        candidates = s["candidates"]
        outcomes = {c["candidate_id"]: score_candidate(c, actuals) for c in candidates}
        fields, field_availability = {}, {}
        for contest in labels["contests"]:
            fid = str(contest["contest_id"])
            es = [e for e in labels["field_entries"] if str(e["contest_id"]) == fid]
            vals = [float(e["entry_points"]) for e in es if e["entry_points"] is not None]
            complete = len(es) == contest["field_size"] and len(vals) == len(es)
            field_availability[fid] = {"reported_field_size": contest["field_size"], "loaded_entries": len(es), "scored_entries": len(vals), "complete": complete}
            if complete:
                fields[fid] = vals
        all_ids = list(outcomes)
        eligible = [c["candidate_id"] for c in candidates if c["quality_eligibility"]["eligible"]]
        generated = summarize_ids(all_ids, outcomes, fields)
        elig = summarize_ids(eligible, outcomes, fields)
        bg, be = generated["best_actual"], elig["best_actual"]
        groups = {
            "deterministic_packet_finalists": [c["candidate_id"] for c in candidates if c["is_deterministic_finalist"]],
            "nonfinalist_quality_eligible": [c["candidate_id"] for c in candidates if c["quality_eligibility"]["eligible"] and not c["is_deterministic_finalist"]],
            "selector_top10": [c["candidate_id"] for c in candidates if c["metrics"]["selector_pool_rank"] <= 10],
            "selector_top20": [c["candidate_id"] for c in candidates if c["metrics"]["selector_pool_rank"] <= 20],
            "highest_mean": [candidates[min(range(len(candidates)), key=lambda i: (-candidates[i]["metrics"]["projected_mean"], candidates[i]["candidate_id"]))]["candidate_id"]],
            "highest_p90": [candidates[min(range(len(candidates)), key=lambda i: (-candidates[i]["metrics"]["summed_marginal_p90_proxy"], candidates[i]["candidate_id"]))]["candidate_id"]],
            "HIGH_market": [c["candidate_id"] for c in candidates if c["quality_eligibility"]["eligible"] and c["market_compatibility"] == "HIGH"],
            "high_ceiling_nonfinalists_095": [c["candidate_id"] for c in candidates if c["quality_eligibility"]["eligible"] and not c["is_deterministic_finalist"] and c["quality_eligibility"]["ceiling_fraction"] >= .95],
            "complete_ai_review_universe": [c["candidate_id"] for c in candidates if c["visible_in_ai_review_universe"]]}
        best = next(c for c in candidates if c["candidate_id"] == generated["best_candidate_id"])
        attention = {}
        for name, p in s["attention_policies"].items():
            visibility = summarize_ids(p["visible_candidate_ids"], outcomes, fields, be, bg)
            selection = summarize_ids(p["counterfactual_prelock_policy_selection"], outcomes, fields, be, bg)
            attention[name] = {**p, "added_count": len(p["added_candidate_ids"]), "eventual_best_visible": best["candidate_id"] in p["visible_candidate_ids"],
                "coverage_evaluation": visibility, "proxy_selection_evaluation": selection}
        pair_policies = {}
        control = s["counterfactual_pair_policies"].get("control")
        for name, p in s["counterfactual_pair_policies"].items():
            pair_policies[name] = {"prelock_pair": p, "evaluation": summarize_ids(p["candidate_ids"], outcomes, fields, be, bg) if p else None,
                "opportunity_cost_vs_control": {"objective_sum_loss": control["objective_sum"]-p["objective_sum"],
                    "average_quality_loss": control["average_normalized_quality"]-p["average_normalized_quality"]} if p and control else None}
        costs = json.loads(json.dumps(s["quality_cost_of_diversification"]))
        for cost in costs.values():
            for key in ["best_joint_quality_pair", "best_minimum_ceiling_pair"]:
                p = cost[key]
                cost[key + "_evaluation"] = summarize_ids(p["candidate_ids"], outcomes, fields, be, bg) if p else None
            for band in cost["joint_band_pairs"].values():
                p = band["selected_pair"]
                band["evaluation"] = summarize_ids(p["candidate_ids"], outcomes, fields, be, bg) if p else None
        selected = summarize_ids(s["historical_deterministic_selected_ids"], outcomes, fields, be, bg)
        generation_fields = {}
        for fid, vals in fields.items():
            descending = sorted(vals, reverse=True)
            cut = {pct: descending[math.ceil(len(vals)*pct/100)-1] for pct in [1, 5, 10]}
            generation_fields[fid] = {"winner_score": descending[0], "cutoff_scores": cut,
                "gap_to_winner": descending[0]-bg, "gap_to_top1pct": cut[1]-bg, "gap_to_top5pct": cut[5]-bg,
                "generated_top10pct_count": sum(v is not None and v >= cut[10]-1e-7 for v in outcomes.values()),
                "generated_top10pct_rate": sum(v is not None and v >= cut[10]-1e-7 for v in outcomes.values())/generated["scoreable_count"]}
        result = {**{k: v for k, v in s.items() if k not in {"attention_policies", "counterfactual_pair_policies", "quality_cost_of_diversification"}},
            "outcome_evidence_sha256": file_hash(path), "outcome_artifact": str(path.relative_to(ROOT)),
            "actual_points_by_canonical_player": actuals, "candidate_actuals": outcomes,
            "best_generated": generated, "best_eligible": elig, "historical_deterministic_selection": selected,
            "attention_groups": {name: summarize_ids(ids, outcomes, fields, be, bg) for name, ids in groups.items()},
            "eventual_best": {"candidate_id": best["candidate_id"], "selector_rank": best["metrics"]["selector_rank"],
                "quality_eligible": best["quality_eligibility"]["eligible"], "deterministic_packet_finalist": best["is_deterministic_finalist"],
                "visible_in_complete_ai_review_universe": best["visible_in_ai_review_universe"]},
            "stage_chain": {"best_generated": bg, "best_eligible": be, "best_considered": None,
                "best_selected_deterministic": selected["best_actual"], "best_selected_recorded_ai": None, "best_entered": None},
            "regret_metrics": {"quality_eligibility_loss": bg-be, "packet_finalist_coverage_loss": be-summarize_ids(groups["deterministic_packet_finalists"], outcomes, fields)["best_actual"],
                "deterministic_selection_regret_vs_generated": bg-selected["best_actual"], "deterministic_selection_regret_vs_eligible": be-selected["best_actual"],
                "ai_selection_regret": None, "entry_execution_regret": None},
            "attention_policy_results": attention, "counterfactual_pair_policy_results": pair_policies,
            "quality_cost_of_diversification": costs, "field_availability": field_availability, "generation_field_metrics": generation_fields,
            "leakage_validation": {"freeze_verified_before_outcomes": True, "selection_ids_persisted_before_outcome_read": True,
                "outcomes_never_passed_to_policy_functions": True, "late_generated_slate_replay_blocked": not s["chronology"]["prelock_replay_available"],
                "missing_actuals_not_imputed": True},
            "saved_report_evidence": [{"report_id": r["report_id"], "created_at": r["created_at"]} for r in labels["saved_learning_reports"]]}
        audit["slates"].append(result)
    write(ROOT / "SHOWDOWN_SELECTION_REGRET_AND_PORTFOLIO_DIVERSITY_AUDIT.json", audit)
    verify_freeze()
    print(json.dumps({"slates": [{"run": s["run_id"], "best_generated": s["best_generated"]["best_actual"], "best_selected": s["historical_deterministic_selection"]["best_actual"]} for s in audit["slates"]]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["freeze", "export-outcomes", "evaluate"])
    args = parser.parse_args()
    {"freeze": freeze, "export-outcomes": export_outcomes, "evaluate": evaluate}[args.phase]()


if __name__ == "__main__":
    main()
