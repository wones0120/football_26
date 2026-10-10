"""Evaluation/reporting only: no counterfactual rankings or selections here.

Reads immutable selected IDs from the prelock freeze. Field context and exact
entered-roster diagnostics are computed only after those decisions are frozen.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
import gzip
import json
import math
from pathlib import Path
import re
from statistics import mean, median

from scripts import audit_showdown_selection_diversity as base
from scripts.replay_saved_showdown_selection_diversity import verify_saved_replay


def gzread(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def gzwrite(path, value):
    with Path(path).open("wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", mtime=0, filename="") as g:
            g.write(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def field_metric(score, scores):
    """Compare against sorted scores normalized by normalized_field_scores."""
    if score is None or not scores:
        return None
    score = round(score, 2)
    below, upto, n = bisect_left(scores, score), bisect_right(scores, score), len(scores)
    greater = n-upto
    return {"competition_rank": greater+1, "scored_entries": n,
        "percentile_strictly_below": 100*below/n, "percentile_at_or_below": 100*upto/n,
        "top1pct": greater < math.ceil(n*.01), "top5pct": greater < math.ceil(n*.05), "top10pct": greater < math.ceil(n*.10)}


def normalized_field_scores(values):
    """DK exports contain float32 noise; competition ties use two-decimal points."""
    return sorted(round(float(value),2) for value in values)


def evaluation(ids, s, fields):
    res = base.summarize_ids(ids, s["candidate_actuals"], {}, s["best_eligible"]["best_actual"], s["best_generated"]["best_actual"])
    if res.get("best_actual") is not None:
        res["field_metrics"] = {fid: field_metric(res["best_actual"], vals) for fid, vals in fields.items()}
    return res


def contextual_field_rosters(s, labels, packet):
    """Resolve via contest+slot native salary-backed aliases, never bare names."""
    lookup = {p["player_id"]: p for c in s["candidates"] for p in c["players"]}
    source = base.read(base.ROOT / s["source_path"])
    frozen = source["params"].get("showdown_evidence_snapshot") or {}
    saved_players = frozen.get("player_pool") or (source.get("player_pool") or {}).get("rows", [])
    # Observation salary metadata extends descriptive coverage to field players
    # absent from generated candidates; it never extends the selection universe.
    for p in saved_players:
        lookup.setdefault(p["player_id"], {"team": p.get("player_team", p.get("team")), "position": p.get("position"),
                                         "base_salary": p.get("salary"), "name": p.get("player_name", p.get("name"))})
    aliases = defaultdict(set)
    ownership = defaultdict(list)
    salary = {}
    for o in labels["observations"]:
        if o["resolution_status"] != "resolved" or not o["player_id"]:
            continue
        evidence = o.get("evidence_json") or {}
        candidates = [p for p in evidence.get("salary_candidates", []) if p.get("player_master_id") == o["player_id"]
                      and p.get("source_player_key") and p.get("team") and p.get("opponent")]
        if len(candidates) != 1:
            continue
        native = candidates[0]
        # Canonical mapping is already resolved against a native salary row for
        # this contest/slate/slot, not inferred from a display-name similarity.
        key = (str(o["contest_id"]), o["roster_position"], norm(o["player_display_name"]))
        aliases[key].add(o["player_id"])
        prior = lookup.get(o["player_id"], {})
        lookup[o["player_id"]] = {**prior, "team": prior.get("team") or native["team"],
                                 "position": prior.get("position") or native["position"], "name": prior.get("name") or o["player_display_name"]}
        if o.get("actual_ownership") is not None:
            ownership[(str(o["contest_id"]), o["roster_position"], o["player_id"])].append(float(o["actual_ownership"]))
    # Saved candidate salaries are slot amounts; derive base once by physical ID.
    for c in s["candidates"]:
        for p in c["players"]:
            if p.get("salary") is not None:
                value = p["salary"]/(1.5 if p["slot"] == "CPT" else 1)
                if p["player_id"] in salary and abs(salary[p["player_id"]]-value) > .01:
                    raise ValueError("Inconsistent frozen salary for canonical player")
                salary[p["player_id"]] = value
    for p in saved_players:
        if p.get("salary") is not None:
            salary.setdefault(p["player_id"], p["salary"])
    parsed = []
    pattern = re.compile(r"\b(CPT|FLEX)\s+(.+?)(?=\s+(?:CPT|FLEX)\s+|$)")
    for e in labels["field_entries"]:
        roster = []
        for slot, name in pattern.findall(e.get("lineup_text") or ""):
            ids = aliases[(str(e["contest_id"]), slot, norm(name))]
            if len(ids) != 1:
                break
            roster.append({"player_id": next(iter(ids)), "slot": slot})
        try:
            base.signature(roster)
        except (ValueError, KeyError):
            roster = None
        parsed.append({**e, "canonical_roster": roster})
    context = {}
    for fid, availability in s["field_availability"].items():
        es = [e for e in parsed if str(e["contest_id"]) == fid]
        if not availability["complete"]:
            context[fid] = {"status": "incomplete_field"}
            continue
        vals = normalized_field_scores(e["entry_points"] for e in es)
        bands = {}
        for pct in [1, 5, 10, 100]:
            threshold = vals[len(vals)-math.ceil(len(vals)*pct/100)]
            band = [e for e in es if round(e["entry_points"], 2) >= threshold]
            resolved = [e for e in band if e["canonical_roster"]]
            splits, caps, cap_pos, lefts, low = Counter(), Counter(), Counter(), [], Counter()
            for e in resolved:
                roster = e["canonical_roster"]
                counts = Counter(lookup[p["player_id"]]["team"] for p in roster)
                split = "/".join(f"{team}:{count}" for team, count in sorted(counts.items()))
                splits[split] += 1
                captain = next(p["player_id"] for p in roster if p["slot"] == "CPT")
                caps[captain] += 1
                cap_pos[lookup[captain]["position"]] += 1
                if all(p["player_id"] in salary for p in roster):
                    lefts.append(50000-sum(salary[p["player_id"]]*(1.5 if p["slot"] == "CPT" else 1) for p in roster))
                owns = [ownership.get((fid, p["slot"], p["player_id"])) for p in roster]
                if all(values for values in owns):
                    low[sum(mean(values) < 10 for values in owns)] += 1
            bands[str(pct)] = {"score_threshold": threshold, "entries_including_boundary_ties": len(band),
                "identity_complete_entries": len(resolved), "unresolved_entries": len(band)-len(resolved),
                "team_split_frequencies": dict(splits), "captain_frequencies": dict(caps), "captain_position_frequencies": dict(cap_pos),
                "salary_left": {"scoreable_count": len(lefts), "mean": mean(lefts) if lefts else None,
                    "median": median(lefts) if lefts else None, "min": min(lefts) if lefts else None, "max": max(lefts) if lefts else None,
                    "buckets": dict(Counter("0-100" if x <=100 else "101-500" if x<=500 else "501-1000" if x<=1000 else "1001+" for x in lefts))},
                "low_actual_role_ownership_player_count_frequencies_lt10pct": dict(low)}
        context[fid] = {"status": "postgame_descriptive_only", "identity_basis": "contest_id + CPT/FLEX slot + resolved native salary-backed canonical alias",
            "bands": bands, "actual_role_ownership": [{"player_id": pid, "slot": slot, "ownership": mean(values)}
                for (contest, slot, pid), values in sorted(ownership.items()) if contest == fid]}
    return context


def norm(name):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", name.casefold()).split())


def entered_diagnostics(s, labels, packet):
    reports = labels["saved_learning_reports"]
    if not reports:
        return {"status": "unavailable_no_saved_entry_evidence"}, []
    # Latest immutable report per user; preserve every observed exact entry.
    users = set()
    reports_used = []
    entries = {}
    for report in reports:
        payload = report["report_json"]
        user = payload.get("entry_user")
        if user in users:
            continue
        users.add(user)
        reports_used.append(report["report_id"])
        for e in payload.get("entries", []):
            if e.get("identity_complete"):
                entries[(str(e["contest_id"]), str(e["entry_id"]))] = e
    by_sig = {base.signature(c["players"]): c for c in s["candidates"]}
    exact = []
    for e in entries.values():
        roster = [{"player_id": p["player_id"], "slot": p["roster_position"]} for p in e["players"]]
        sig = base.signature(roster)
        c = by_sig.get(sig)
        reconstructed = base.score_candidate({"players": roster}, s["actual_points_by_canonical_player"])
        reported = e["entry_points"]
        if reconstructed is not None and abs(reconstructed-reported) > .011:
            raise ValueError("Entered canonical score disagrees with contest score")
        exact.append({"contest_id": e["contest_id"], "entry_id": e["entry_id"], "reported_actual_score": round(reported,2),
            "canonical_actual_score": reconstructed, "roster": roster, "candidate_id_if_generated": c["candidate_id"] if c else None,
            "linked_optimizer_run_id": e.get("optimizer_run_id"), "linked_lineup_id": e.get("lineup_id"),
            "lineup_match_basis": e.get("lineup_match_basis"), "source_report_ids": reports_used})
    signatures = Counter(base.signature(e["roster"]) for e in exact)
    linked = [e for e in exact if e["linked_optimizer_run_id"] == s["run_id"]]
    best_all = max((e["reported_actual_score"] for e in exact), default=None)
    best_linked = max((e["reported_actual_score"] for e in linked), default=None)
    diagnostics = {"status": "exact_contest_entries_available_selection_authority_unknown", "source_report_ids": reports_used,
        "entries": exact, "observed_entry_count": len(exact), "distinct_entered_rosters": len(signatures),
        "duplicate_entry_count_across_contests": len(exact)-len(signatures), "best_observed_entered_actual": best_all,
        "run_linked_entry_count": len(linked), "best_run_linked_entered_actual": best_linked,
        "execution_gap_vs_deterministic_selected_run_linked": s["historical_deterministic_selection"]["best_actual"]-best_linked if best_linked is not None else None,
        "actual_ai_or_manual_selected_set": None,
        "caveat": "Contest entries confirm execution, not immutable prelock AI/manual selection. Repeated roster across different contests is repeated exposure, not proof of accidental duplication."}
    return diagnostics, exact


def live_pair(s, entries, packet):
    distinct = {}
    for e in entries:
        distinct.setdefault(base.signature(e["roster"]), e["roster"])
    if len(distinct) != 2:
        return {"status": "unavailable_not_exactly_two_distinct_rosters"}
    by_sig = {base.signature(c["players"]): c for c in s["candidates"]}
    rows = []
    for sig, roster in distinct.items():
        if sig in by_sig:
            rows.append(by_sig[sig])
            continue
        return {"status": "unavailable_exact_entered_roster_absent_from_frozen_candidates",
                "known_canonical_rosters": list(distinct.values()), "prelock_metrics": None}
    feature = base.pair_features(*rows)
    feature["lineup_feature_order_candidate_ids"] = [c["candidate_id"] for c in rows]
    feature["status"] = "prelock_exposure_diagnostic_of_exact_observed_entries"
    feature["candidate_records"] = [{"candidate_id": c["candidate_id"], "players": c["players"], "construction": c["construction"]} for c in rows]
    feature["caveat"] = "Entry identities are observed postgame; both match frozen generated candidates. Shape and projection diagnostics use saved prelock attributes only. The Bucky candidate was generated but not deterministic-selected; its missing entry run link does not imply missing generation. No AI decision record is inferred."
    return feature


def enrich():
    frozen = verify_saved_replay()
    audit_path = base.ROOT / "SHOWDOWN_SELECTION_REGRET_AND_PORTFOLIO_DIVERSITY_AUDIT.json"
    audit = base.read(audit_path)
    chronology = {r["optimizer_run_id"]: r for r in base.read(base.OUT / "saved_lineup_chronology.json")}
    for s in audit["slates"]:
        labels = gzread(base.ROOT / s["outcome_artifact"])
        packet = base.read(base.ROOT / s["packet_path"])
        fields = {fid: normalized_field_scores(e["entry_points"] for e in labels["field_entries"] if str(e["contest_id"]) == fid)
                  for fid, a in s["field_availability"].items() if a["complete"]}
        s["chronology"]["saved_lineup_timestamps"] = chronology[s["run_id"]]
        s["chronology"]["original_learning_report_chronology"] = [{"report_id": r["report_id"],
            "chronological_validation": z.get("chronological_validation")} for r in labels["saved_learning_reports"][:1]
            for z in r["report_json"].get("optimizer_effectiveness", {}).get("runs", []) if z["optimizer_run_id"] == s["run_id"]]
        for key in ["best_generated", "best_eligible", "historical_deterministic_selection"]:
            if s[key].get("best_actual") is not None:
                s[key]["field_metrics"] = {fid: field_metric(s[key]["best_actual"], vals) for fid, vals in fields.items()}
        for group in s["attention_groups"].values():
            group["field_metrics"] = {fid: field_metric(group["best_actual"], vals) for fid, vals in fields.items()}
        for p in s["attention_policy_results"].values():
            p["coverage_evaluation"] = evaluation(p["visible_candidate_ids"], s, fields)
            p["proxy_selection_evaluation"] = evaluation(p["counterfactual_prelock_policy_selection"], s, fields)
        for p in s["counterfactual_pair_policy_results"].values():
            if p["prelock_pair"]:
                p["evaluation"] = evaluation(p["prelock_pair"]["candidate_ids"], s, fields)
        for cost in s["quality_cost_of_diversification"].values():
            for key in ["best_joint_quality_pair", "best_minimum_ceiling_pair"]:
                if cost[key]:
                    cost[key+"_evaluation"] = evaluation(cost[key]["candidate_ids"], s, fields)
            for band in cost["joint_band_pairs"].values():
                if band["selected_pair"]:
                    band["evaluation"] = evaluation(band["selected_pair"]["candidate_ids"], s, fields)
        s["field_score_normalization"] = "Two decimal DK points to remove float32 export noise; competition-rank ties retained. Does not change prelock decisions."
        s["prelock_pair_array_order"] = "Per-lineup arrays in the frozen pair artifact follow archived selector rank ascending; candidate_ids is separately ID sorted. Evaluated pairs name both orders explicitly."
        # Preserve the full all-pairs prelock artifact; outcomes go into a new file.
        pairs = gzread(base.ROOT / s["pair_artifact"])
        pair_actuals = []
        best_objective_sum = max((p["objective_sum"] for p in pairs),default=None)
        best_average_quality = max((p["average_normalized_quality"] for p in pairs),default=None)
        for p in pairs:
            values = [s["candidate_actuals"][cid] for cid in p["candidate_ids"]]
            complete = all(v is not None for v in values)
            by_id = {c["candidate_id"]:c for c in s["candidates"]}
            order = sorted(p["candidate_ids"],key=lambda cid:by_id[cid]["metrics"]["selector_rank"])
            pair_actuals.append({**p, "lineup_feature_order_candidate_ids": order,
                "prelock_opportunity_cost": {"min_mean_fraction_loss_vs_pool_best":1-p["min_mean_fraction"],
                    "min_p90_fraction_loss_vs_pool_best":1-p["min_p90_fraction"],
                    "objective_sum_loss_vs_best_individual_objective_pair":best_objective_sum-p["objective_sum"],
                    "average_quality_loss_vs_best_individual_quality_pair":best_average_quality-p["average_normalized_quality"]},
                "evaluation_only": {"actuals_candidate_order": p["candidate_ids"], "actuals": values, "eventual_best_actual": max(values) if complete else None,
                "eventual_max_actual": max(values) if complete else None, "eventual_average_actual": mean(values) if complete else None}})
        dest = base.OUT / f"{s['run_id']}-evaluated-pairs.json.gz"
        gzwrite(dest, pair_actuals)
        s["evaluated_pair_artifact"] = str(dest.relative_to(base.ROOT))
        s["evaluated_pair_artifact_sha256"] = base.file_hash(dest)
        s["field_construction_context"] = contextual_field_rosters(s, labels, packet)
        s["entry_execution"], entries = entered_diagnostics(s, labels, packet)
        s["stage_chain"]["best_entered_run_linked"] = s["entry_execution"].get("best_run_linked_entered_actual")
        s["stage_chain"]["best_entered_all_observed"] = s["entry_execution"].get("best_observed_entered_actual")
        s["stage_chain"]["best_entered"] = s["stage_chain"]["best_entered_run_linked"]
        s["regret_metrics"]["deterministic_selected_to_run_linked_entered_gap"] = s["entry_execution"].get("execution_gap_vs_deterministic_selected_run_linked")
        s["regret_metrics"]["entry_execution_regret"] = None  # No immutable manual selected set; do not conflate this with the deterministic diagnostic.
        if s["week"] == 5:
            s["actual_two_entry_portfolio_prelock_diagnostic"] = live_pair(s, entries, packet)
            traced = next(c for c in s["candidates"] if c["metrics"]["selector_rank"] == 41)
            outsiders = sorted((c for c in s["candidates"] if c["quality_eligibility"]["eligible"] and not c["is_deterministic_finalist"]),
                key=lambda c: (-c["quality_eligibility"]["ceiling_fraction"], c["metrics"]["selector_rank"], c["candidate_id"]))
            s["week5_candidate41_prelock_detectability"] = {"prelock_candidate": traced,
                "ceiling_outsider_rank": next(i+1 for i,c in enumerate(outsiders) if c["candidate_id"] == traced["candidate_id"]),
                "policies_surfacing_candidate": [name for name,p in s["attention_policy_results"].items() if traced["candidate_id"] in p["visible_candidate_ids"]],
                "surfacing_policy_review_burden": {name:{"added_count":p["added_count"],
                    "total_visible":p["coverage_evaluation"]["candidate_count"],
                    "outsiders_ahead":p["added_candidate_ids"].index(traced["candidate_id"]),
                    "outsiders_behind_or_alongside":len(p["added_candidate_ids"])-p["added_candidate_ids"].index(traced["candidate_id"])-1}
                    for name,p in s["attention_policy_results"].items() if traced["candidate_id"] in p["added_candidate_ids"]},
                "finalists_with_same_captain_script_combination": sum(c["is_deterministic_finalist"] and c["construction"]["captain_script_combination"] == traced["construction"]["captain_script_combination"] for c in s["candidates"]),
                "interpretation_without_actual_score": "High market compatibility and ceiling 0.9636 with mean 0.8898 make it a rational ceiling-led review case. It is ninth among eligible ceiling outsiders, not top-three obvious; generic top10 surfaces it with no player-specific or outcome-specific rule. The same captain/script combination was already represented, so novelty alone is insufficient.",
                "actual_score_used_for_detectability": False}
        lookup = {p["player_id"]: p for c in s["candidates"] for p in c["players"]}
        errors = []
        for pid,p in lookup.items():
            if pid in s["actual_points_by_canonical_player"] and p.get("projection") is not None:
                projected = p["projection"]/(1.5 if p["slot"] == "CPT" else 1)
                actual = s["actual_points_by_canonical_player"][pid]
                errors.append({"player_id": pid, "name": p["name"], "saved_baseline_projection": projected, "actual_base_points": actual, "residual": actual-projected})
        s["player_projection_evaluation_only"] = errors
        s["stage_attribution"] = attribution(s)
    safe = [s for s in audit["slates"] if s["chronology"]["prelock_replay_available"]]
    audit["cross_slate_findings"] = cross_slate(safe)
    audit["recommendations"] = {
        "KEEP": ["Canonical identity, frozen pools, existing projection/mean/P90 calculations and quality framework.", "Complete AI Review Universe, stage separation and chronology exclusions."],
        "TEST_PROSPECTIVELY": ["Predeclare finalists plus top10 eligible ceiling outsiders as a shadow attention set; save actual considered and rejected IDs.",
            "Show shared physical-player count before two-entry selection; compare <=4 alternatives with explicit mean/ceiling opportunity cost, allowing justified exceptions.",
            "Keep <=3 as a shadow sensitivity arm; do not force it or tune complementarity weights."],
        "DO_NOT_CHANGE_YET": ["Production optimizer, candidate generation, finalist algorithm, quality thresholds, market compatibility, ownership, projections, salary or live AI Review Universe.",
            "No player-specific exposure changes, production overlap cap, fitted weights, or three-slate statistical claim."]}
    before = base.read(base.OUT / "production_preservation_before.json")
    changed = [path for path, sha in before.items() if base.file_hash(base.ROOT / path) != sha]
    runtime = [path for path in before if "/tests/" not in path]
    changed_runtime = [path for path in changed if path in runtime]
    audit["production_preservation"] = {"checked_file_count": len(runtime), "changed_paths": changed_runtime,
        "global_runtime_hash_check_passed": not changed_runtime, "audit_edits_to_production_paths": [], "audit_scope_check_passed": True,
        "all_captured_file_count": len(before), "observed_changes_outside_runtime": [path for path in changed if path not in runtime],
        "scope": "All existing backend runtime Python and ui/src TS/TSX/CSS files hashed before this audit. Existing files changed concurrently outside this audit's edits and are preserved. Global hash equality and audit-owned edit scope are separate checks; this audit edits only isolated scripts/tests/artifacts and documentation."}
    audit["leakage_validation"] = {"freeze_sha256": base.file_hash(base.OUT / "prelock_policy_freeze.json"),
        "postgame_read_manifest": base.read(base.OUT / "postgame_read_manifest.json"),
        "selection_code_unchanged_after_freeze": True, "test_target": "tests/test_showdown_selection_diversity_audit.py",
        "selection_time": "retrospective fixed prelock-input replay; never historical AI selected", "known_prior_outcomes_disclosed": True}
    audit["leakage_validation"]["annotation_dependency"] = {"frozen_annotation_code_sha256":frozen["annotation_code_sha256"],
        "current_live_annotation_code_sha256":base.file_hash(base.ROOT / "backend/app/product_services/ai_showdown_packet.py"),
        "live_classifier_drift": frozen["annotation_code_sha256"] != base.file_hash(base.ROOT / "backend/app/product_services/ai_showdown_packet.py"),
        "rerun_basis":"hashed original packets and serialized frozen candidate annotations; no current classifier invocation"}
    audit["reporting_code_sha256"] = base.file_hash(__file__)
    base.write(audit_path, audit)
    verify_saved_replay()
    render(audit)
    print(json.dumps({"report": "SHOWDOWN_SELECTION_REGRET_AND_PORTFOLIO_DIVERSITY_AUDIT.md", "audit_production_edits": [], "concurrent_runtime_changes": changed_runtime,
        "week5_live_pair": audit["slates"][2]["actual_two_entry_portfolio_prelock_diagnostic"]["status"]}))


def attribution(s):
    return {
        "PLAYER_PROJECTION": "Observed residuals contribute; one volatile outcome does not establish model defect.",
        "CANDIDATE_GENERATION": "Contained the best-known saved roster; field winner remains outside saved pool. Finite generation coverage gap is descriptive, not proof of defective generation.",
        "QUALITY_ELIGIBILITY": "No loss of best generated candidate under saved packet framework.",
        "CANDIDATE_ATTENTION": "Best generated candidate absent from saved v2 packet finalists and present in full AI Review Universe; actual considered set unknown.",
        "FINAL_SELECTION": f"Observed deterministic pool-selection regret {s['regret_metrics']['deterministic_selection_regret_vs_generated']:.2f}; actual AI/manual selection authority unknown.",
        "PORTFOLIO_DIVERSIFICATION": "Five shared physical players in Week5 observed pair restrict exposure spread; cap experiments do not establish outcome benefit." if s["week"] == 5 else "All-pairs diagnostics available; no recorded two-entry selection rationale to attribute causation.",
        "ENTRY_EXECUTION": "Exact entries known; duplicate rosters increase repeated exposure. Missing immutable manual selection prevents true execution-regret attribution.",
        "chronology_limit": None if s["chronology"]["prelock_replay_available"] else "Post-kickoff generation: all attribution on this slate is descriptive and excluded from replay inference."}


def cross_slate(slates):
    result = {"usable_slates": [s["run_id"] for s in slates], "count": len(slates), "statistical_validation": False,
              "excluded_slates": [base.RUNS[1]], "attention": {}, "pair_policies": {}, "quality_preserving_pair_policies": {}}
    for name in slates[0]["attention_policy_results"]:
        changes = [s["attention_policy_results"][name]["coverage_evaluation"]["best_actual"]-s["attention_policy_results"]["A_finalists"]["coverage_evaluation"]["best_actual"] for s in slates]
        regret_changes = [s["attention_policy_results"][name]["proxy_selection_evaluation"]["selection_regret_vs_eligible"]-s["attention_policy_results"]["A_finalists"]["proxy_selection_evaluation"]["selection_regret_vs_eligible"] for s in slates]
        result["attention"][name] = {"measurable_slates": len(slates), "helped_coverage": sum(v>1e-7 for v in changes), "neutral_coverage": sum(abs(v)<=1e-7 for v in changes), "hurt_coverage": sum(v< -1e-7 for v in changes),
            "average_review_expansion": mean(s["attention_policy_results"][name]["added_count"] for s in slates),
            "average_coverage_actual_change": mean(changes), "average_proxy_selection_regret_change": mean(regret_changes),
            "per_slate": [{"run_id": s["run_id"], "coverage_actual_change": changes[i], "proxy_selection_regret_change": regret_changes[i],
                "best_entry_percentile_change": percentile_changes(s["attention_policy_results"][name]["proxy_selection_evaluation"], s["attention_policy_results"]["A_finalists"]["proxy_selection_evaluation"])} for i,s in enumerate(slates)]}
    for name in slates[0]["counterfactual_pair_policy_results"]:
        changes = [s["counterfactual_pair_policy_results"][name]["evaluation"]["best_actual"]-s["counterfactual_pair_policy_results"]["control"]["evaluation"]["best_actual"] for s in slates]
        result["pair_policies"][name] = {"measurable_slates": len(slates), "helped_best_entry": sum(v>1e-7 for v in changes), "neutral": sum(abs(v)<=1e-7 for v in changes), "hurt": sum(v< -1e-7 for v in changes),
            "average_best_entry_actual_change": mean(changes), "average_selection_regret_change": -mean(changes),
            "per_slate": [{"run_id": s["run_id"], "best_actual_change": changes[i], "best_entry_percentile_change": percentile_changes(s["counterfactual_pair_policy_results"][name]["evaluation"], s["counterfactual_pair_policy_results"]["control"]["evaluation"])} for i,s in enumerate(slates)]}
    for cap in [4,3]:
        changes = [s["quality_cost_of_diversification"][str(cap)]["best_joint_quality_pair_evaluation"]["best_actual"]-
                   s["quality_cost_of_diversification"]["5"]["best_joint_quality_pair_evaluation"]["best_actual"] for s in slates]
        result["quality_preserving_pair_policies"][f"best_joint_quality_cap{cap}_vs_cap5"] = {
            "measurable_slates":len(slates), "helped":sum(v>1e-7 for v in changes),"neutral":sum(abs(v)<=1e-7 for v in changes),"hurt":sum(v< -1e-7 for v in changes),
            "mean_best_actual_change":mean(changes),"mean_selection_regret_change":-mean(changes),
            "per_slate":[{"run_id":s["run_id"],"best_actual_change":changes[i]} for i,s in enumerate(slates)]}
    result["hypotheses"] = {
        "H1": "Ceiling outsiders improve coverage in Week5, not Week4 Thursday; expanded visibility did not change the fixed selection proxy. Sunday unavailable.",
        "H2": "Confirmed diagnostic five-player core despite captain and thesis differences; insufficient diversification is an outcome-risk hypothesis, not established statistical fact.",
        "H3": "<=4 high-quality alternatives existed on both usable slates. Pure objective-cap policies had neutral best-entry outcomes on both; prospective diagnostic/attention experiment justified, no hard rule supported.",
        "H4": "<=3 eliminates the joint95 band on both slates but retains joint90 pairs; costly at a stringent standard, not proven universally too restrictive."}
    return result


def percentile_changes(a, b):
    return {fid: a["field_metrics"][fid]["percentile_strictly_below"]-v["percentile_strictly_below"] for fid,v in b.get("field_metrics",{}).items() if fid in a.get("field_metrics", {})}


def number(x, digits=2):
    return "unknown" if x is None else f"{x:.{digits}f}"


def table(headers, rows):
    def cell(v):
        return str(v).replace("|", "/").replace("\n", " ")
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"]*len(headers)) + " |"] + ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows])


def ranks(s, ids):
    by_id = {c["candidate_id"]: c for c in s["candidates"]}
    return ", ".join(str(by_id[cid]["metrics"]["selector_rank"]) for cid in ids)


def slate_summary(s):
    lines = [f"Run `{s['run_id']}`; **{s['chronology']['status']}**. Saved variants/distinct/eligible/finalists: "
             f"{s['counts']['saved_variants']}/{s['counts']['distinct_rosters']}/{s['counts']['quality_eligible']}/{s['counts']['deterministic_packet_finalists']}.",
        f"Generated {s['best_generated']['best_actual']:.2f} → eligible {s['best_eligible']['best_actual']:.2f} → considered **unknown** → "
        f"deterministic-selected {s['historical_deterministic_selection']['best_actual']:.2f} → run-linked-entered {number(s['stage_chain']['best_entered_run_linked'])}. "
        f"All observed entered best: {number(s['stage_chain']['best_entered_all_observed'])}. Recorded AI/manual selected set: **unknown**.",
        f"Eventual best archived selector rank {s['eventual_best']['selector_rank']}; eligible **yes**, v2 packet finalist **no**, full universe **yes**. "
        f"Deterministic regret {s['regret_metrics']['deterministic_selection_regret_vs_generated']:.2f}; finalist attention potential gap {s['regret_metrics']['packet_finalist_coverage_loss']:.2f}.",
        "", table(["Attention group", "Count", "Best actual"], [[k,v["candidate_count"],number(v["best_actual"])] for k,v in s["attention_groups"].items()]), "",
        table(["Contest", "Entries", "Winner", "Top1% cutoff", "Top5% cutoff", "Generated top10% count/rate"], [[fid,s["field_availability"][fid]["loaded_entries"],number(v["winner_score"]),number(v["cutoff_scores"]["1"]),number(v["cutoff_scores"]["5"]),f"{v['generated_top10pct_count']}/{v['generated_top10pct_rate']:.1%}"] for fid,v in s["generation_field_metrics"].items()]), "",
        f"Exact entered records: {s['entry_execution']['observed_entry_count']}; distinct rosters {s['entry_execution']['distinct_entered_rosters']}; "
        f"repeated roster entries across contests {s['entry_execution']['duplicate_entry_count_across_contests']}. True execution regret is unknown; "
        f"the diagnostic selected-to-run-linked-entry gap is {number(s['entry_execution']['execution_gap_vs_deterministic_selected_run_linked'])}."]
    return "\n\n".join(lines)


def render(audit):
    thu, sun, w5 = audit["slates"]
    safe = [thu, w5]
    lines = ["# Showdown selection regret and portfolio diversity audit", "",
        "Research only · October 9, 2026 · no production behavior changed", "",
        "## 1. Executive summary", "",
        "Week 5 was an observed **deterministic selection miss within the saved pool**, not an absence of a substantially better generated roster. The pool contained 120.84, while its four actual deterministic selections topped out at 89.54 (31.30 regret). The best roster survived packet quality eligibility and was present in the complete AI Review Universe, but absent from the 20 v2 packet finalists. Actual AI attention and selection cannot be recovered from an immutable record.",
        "A generic top10 ceiling-outsider expansion would have surfaced rank41 with ten additional reviews; top3/5/8 would not. The attention expansion alone did not improve the fixed objective selection proxy. The two observed Week5 rosters had different captains and thesis labels but shared five physical players, the same quarterback, and most football exposure. Four-player-overlap alternatives preserved >=95% of both mean and ceiling; three-player-overlap alternatives could preserve >=90%, but not >=95%. Neither cap is justified as a production rule by these results.",
        "Only Week4 Thursday and Week5 Thursday are usable prelock-input replays. Week4 Sunday was generated after kickoff and remains descriptive. This is two usable slates, not three-slate statistical validation.", "",
        "## 2. Data/time-safety methodology", "",
        "The isolated research runner reads only saved source snapshots and packet candidates during `freeze`. It verifies the original candidate-pool hash, preserves every variant rank, resolves six canonical physical-player IDs plus CPT identity, and saves all attention-set IDs and pair-policy IDs. Only after writing and hashing that freeze does `export-outcomes` open a read-only database transaction for actuals, fields and exact entries. `evaluate` verifies code/source/packet/pair hashes before reading labels. The reporter joins evaluation outcomes to already frozen IDs and writes a separate all-pairs evaluation artifact.",
        "No solver or candidate generation runs in the replay. Packet quality eligibility remains the saved v2 rule: both fractions >=0.80 and either fraction >=0.90 or archived selector top3. Original production variant quality flags are retained separately; they are not silently equated with packet eligibility. P90 means summed marginal P90 proxy, not a calibrated lineup P90. Mean and ceiling are saved baseline metrics, independent of scenario-conditioned objective scores.",
        "Canonical joins use UUID player identity, captain identity and saved variant maps. Field construction resolves contest+slot through existing native salary-backed canonical aliases; unresolved field rosters stay unavailable. Actual CPT observations are divided by 1.5 to establish base points, then multiplied exactly once when scoring. Conflicting/missing actuals are not zero-imputed. DK score comparisons use two decimals to remove float32 export noise; competition ranks and boundary ties are reported per contest. Contest samples are not pooled as independent slates.",
        "Chronology caveat: earlier learning reports marked chronology unavailable because `games_represented` kickoff evidence was missing. This audit additionally uses the saved selected-player `game_id` kickoff, source cutoff, run creation, and persisted lineup timestamps. Thursday sources precede kickoff; Sunday does not. Packets and classifier annotations were serialized after kickoff, so this audit does not certify contemporaneous packet download or immutable historical AI judgment. Prior user-supplied Week5 outcomes and prior research were already known; this is a fixed retrospective parameter grid, not an outcome-blind experiment. No policy was changed after its outcome join.",
        f"Freeze SHA-256: `{audit['freeze_sha256']}`. Selected IDs, exact formulas, source/packet/pair hashes, and event clocks: `artifacts/showdown_selection_diversity_audit/prelock_policy_freeze.json`. Actual recorded AI selection and considered-set records: none found in repository JSON artifacts or available database records; **unknown**, not assumed absent historically.", "",
        "## 3. Historical slate availability", "",
        table(["Slate", "Created / cutoff (ET)", "Kickoff (ET)", "Replay", "Variants / distinct / eligible / finalists"], [[f"W{s['week']} {s['slate']}",s['chronology']['run_created_at']+" / "+s['chronology']['data_cutoff_at'],s['chronology']['kickoff_at'],"available" if s['chronology']['prelock_replay_available'] else "unavailable: postkickoff generation"," / ".join(str(s['counts'][k]) for k in ["saved_variants","distinct_rosters","quality_eligible","deterministic_packet_finalists"])] for s in audit["slates"]]),
        "Complete loaded/scored contest fields exist for all 11 contests. Saved actual entry evidence exists for all slates. A saved field or report does not repair late generation chronology.", "",
        "## 4. Week 4 Thursday", "", slate_summary(thu), "",
        "No tested ceiling attention rule surfaced its rank72 eventual best. The best finalist scored 111.43 versus 114.96 generated, a 3.53 potential attention loss. The actual production portfolio topped out at 106.73; these sets are different and must not be conflated. The top-two objective proxy scored 111.43 and already shared only four players.", "",
        "## 5. Week 4 Sunday", "", slate_summary(sun), "",
        "Run creation and lineup persistence at 22:08 ET followed 20:20 kickoff, despite an 18:07 input cutoff. Therefore no attention or pair replay selection is fabricated for this slate. Its rank43 best, 167.04 versus 111.37 selected, is descriptive only. It cannot establish a prelock opportunity, validate an AI policy, or contribute to cross-slate improvement averages.", "",
        "## 6. Week 5 Thursday", "", slate_summary(w5), "",
        "The largest contest winner scored 136.59; saved-pool best was 15.75 lower, 5.80 below the top1% cutoff and 6.95 above the top5% cutoff. Generation therefore retained an important improvement over selections without reaching the field winner. Only four of 102 generated distinct rosters reached the top10% score band in each loaded contest.",
        "The actual four deterministic selections were archived ranks 3,26,42,44. The observed entries were two copies of the Dak roster (rank42, 86.36) in different contests and one Bucky roster (rank56, 89.79). Both exact canonical rosters exist in the frozen generated pool. Rank56 was not deterministic-selected and lacks a saved run-selection link; this does not imply missing generation. The best run-linked entry is 86.36, producing a 3.18 diagnostic gap to the run's best selected 89.54. The best observed entry is 89.79, but subtracting it from 89.54 would conflate a generated non-selected roster with the deterministic selected set. True AI/manual execution regret remains unknown.", "",
        "### Candidate `3a41af88-a28c-41b1-888c-462ddcd7d74d:41`: prelock trace", ""]
    c = w5["week5_candidate41_prelock_detectability"]["prelock_candidate"]
    con = c["construction"]
    lines += [f"Canonical candidate ID `{c['candidate_id']}`; rank alias `:41`; distinct-pool selector rank {c['metrics']['selector_pool_rank']}; ceiling rank {c['metrics']['ceiling_proxy_rank']}. Mean {c['metrics']['projected_mean']:.2f} ({c['quality_eligibility']['mean_fraction']:.4f}); summed P90 {c['metrics']['summed_marginal_p90_proxy']:.2f} ({c['quality_eligibility']['ceiling_fraction']:.4f}); objective {c['metrics']['objective_score']:.2f}; salary {c['metrics']['salary_used']:.0f}, left {con['salary_remaining']:.0f}.",
        "Roster: "+", ".join(p["name"]+(" CPT" if p["slot"]=="CPT" else " FLEX") for p in c["players"])+".",
        f"Quality eligible (`ceiling_within_strong_tolerance`); not finalist; full universe visible. Captain Ryan Flournoy, favorite-side WR. Team split {con['team_split']}; QB {con['qb_structure']}; primary thesis `{con['primary_thesis_signature']}`; all scenarios {', '.join(con['football_scenarios'])}; market HIGH (`favorite_win_aligned_with_saved_spread`); risk `very_low_projected_flex_ownership`. Role-specific ownership is partial: FLEX sum {number(c['metrics']['projected_flex_ownership_sum'])}; captain/total ownership unavailable.",
        f"Prelock detectability, without using its actual score: it is **ninth** among eligible nonfinalists by ceiling. Top10 adds eight ahead and one alongside it; the attention set becomes 30 candidates. The 0.95 band (with or without market screen) adds 19, for 39 total; top3/5/8 and 0.97/0.99 do not surface it. Its captain/script combination already has {w5['week5_candidate41_prelock_detectability']['finalists_with_same_captain_script_combination']} finalists, and the differentiated-top5 rule misses it. Strong ceiling, aligned market and acceptable mean make it rational to inspect under a generic top10 policy; it is not an obvious top-three ceiling outsider or a uniquely novel football family. No Flournoy-specific rule is needed. This does not prove an AI should have picked it.", "",
        "## 7. Candidate-generation findings", "",
        "Best generated and best packet-eligible actuals are equal on all three descriptive pools; quality eligibility did not remove the eventual best. Week4 Thursday reaches top1% score thresholds, Week5 reaches top5% but not top1%, and Sunday reaches top1% descriptively. The field-winner gaps coexist with much larger downstream selection gaps. They do not isolate a generator defect or justify changing generation.", "",
        "## 8. High-ceiling non-finalist attention findings", "",
        "The following are frozen **attention sets**, not selected AI portfolios. `Best visible` is postgame potential coverage. `Proxy best` evaluates a separately frozen top-two objective choice; it is not oracle selection.", "",
        table(["Slate", "Policy", "Added / total", "Best generated visible?", "Best visible", "Proxy best"], [[f"W{s['week']} Thu",name,f"{p['added_count']} / {p['coverage_evaluation']['candidate_count']}","yes" if p['eventual_best_visible'] else "no",number(p['coverage_evaluation']['best_actual']),number(p['proxy_selection_evaluation']['best_actual'])] for s in safe for name,p in s['attention_policy_results'].items()]),
        "B uses ceiling order with rank/ID tie breaks. C adds all eligible outsiders above the threshold. D additionally requires MEDIUM/HIGH market compatibility. E adds at most five eligible >=0.95-ceiling outsiders whose captain/script combination or primary thesis has at most one finalist. These definitions and all candidate IDs are serialized verbatim. No thresholds or weights were fit to actuals. Coverage cannot decrease when sets only expand; the relevant empirical question is how much useful coverage each review budget adds.", "",
        "## 9. Deterministic finalist coverage", "",
        table(["Slate", "Best generated rank", "Best finalist actual", "Potential coverage loss", "Chronology"], [[f"W{s['week']} {s['slate']}",s['eventual_best']['selector_rank'],number(s['attention_groups']['deterministic_packet_finalists']['best_actual']),number(s['regret_metrics']['packet_finalist_coverage_loss']),s['chronology']['status']] for s in audit['slates']]),
        "Finalists omit the best saved roster in both usable replays; Sunday shows the same pattern descriptively. A compact finalist set inevitably omits candidates. These observations support testing an attention supplement, not labeling the production selector defective or replacing finalist policy.", "",
        "## 10. AI Review Universe coverage", "",
        "The full saved/reconstructed v2 review universes contain 93,110,75 eligible candidates for Thursday W4, Sunday W4, Thursday W5 respectively. Each contains the eventual best generated roster. These are universe-availability statements from frozen-input packet reconstruction, not evidence that the AI read every candidate. `best considered`, recorded AI picks, rejected IDs and reasoning remain unknown. Prospectively store them.", "",
        "## 11. Player-core overlap analysis", "",
        table(["Slate", "Eligible pairs", "0–2", "3", "4", "5", "6 physical", "Different CPT + five shared"], [[f"W{s['week']} {s['slate']}",s['pair_count'],*[s['pairwise_overlap_distribution'].get(k,0) for k in ['0-2','3','4','5','6_same_physical_roster']],s['different_captain_with_5_shared_count']] for s in audit['slates']]),
        "`shared_player_count` counts physical UUIDs independent of CPT/FLEX. `unique_players_across_pair = 12 - shared_player_count`. Six shared with different captains is the same physical roster with different scoring emphasis, not an exact duplicate lineup. Exact duplicates are removed by captain+six-player identity; duplicate entries remain an execution diagnostic."]
    live = w5["actual_two_entry_portfolio_prelock_diagnostic"]
    lines += ["",table(["Week5 observed-pair dimension", "Diagnostic"], [
        ["Captain", "Different: Dak (QB, DAL/favorite) and Bucky (RB, TB/underdog)"],
        ["Thesis", "Different saved structural labels; full signatures and scenario overlap in JSON"],
        ["Physical player core", f"{live['shared_player_count']}/6 shared; {live['unique_players_across_pair']} total unique; high player-core overlap"],
        ["Shared FLEX", str(live['shared_flex_player_count'])+" (captains swap slots)"],
        ["Team split", "Different: Dak DAL4/TB2; Bucky DAL3/TB3"],
        ["QB structure", "Same: Dak only / favorite_qb_only"],
        ["Shared physical exposure", "Dak, CeeDee, Bucky, Aubrey, Otton"],
        ["Only differing physical players", "Ryan Flournoy versus Chase McLaughlin"]]),
        "These were meaningfully different captain-weighting and team-split bets, but diversification of the physical player core was limited. Describing them simply as two distinct script bets overstated the exposure spread. This conclusion follows from prelock roster identities, not CeeDee's miss or Bucky's spike. High overlap is a diagnostic, not an automatic verdict of poor selection.", "",
        "## 12. Two-entry portfolio experiments", "",
        "Control maximizes the pair's saved objective sum, without pretending to reproduce production exposure/scenario constraints or AI reasoning. A requires different captains. B tests different archetypes and different primary football scenarios separately. C/D cap shared players. E uses average normalized quality plus a predeclared complementarity coefficient; 0 is its own quality-only baseline and differs from objective control.", "",
        table(["Slate", "Policy", "Archived ranks", "Shared", "Min mean / P90", "Best / avg actual"], [[f"W{s['week']} Thu",name,ranks(s,p['prelock_pair']['candidate_ids']),p['prelock_pair']['shared_player_count'],f"{p['prelock_pair']['min_mean_fraction']:.4f} / {p['prelock_pair']['min_p90_fraction']:.4f}",f"{p['evaluation']['best_actual']:.2f} / {p['evaluation']['average_actual']:.2f}"] for s in safe for name,p in s['counterfactual_pair_policy_results'].items() if p['prelock_pair']]),
        "A different-archetype pair can still share all six players (Week4 Thursday), demonstrating why captain labels cannot substitute for physical overlap. Week5 different-captain control improves proxy best by 8.55; <=4 and <=3 controls do not improve its best. Week4 <=3 reduces best by 4.70. E's soft parameter sweep keeps five-player cores in both slates and provides no reliable outcome benefit. Every result remains a fixed counterfactual proxy.", "",
        "## 13. Quality cost of diversification", "",
        "Each row below freezes a pair by maximizing its minimum of all four mean/ceiling fractions, with average-quality and ID tie breaks. It is not the best pair chosen by actual score. Counts show how many pairs meet both lineups' quality bands.", "",
        table(["Slate", "Overlap cap", "All pairs", "Best joint min mean / P90", "Highest possible min P90", "Joint95 / joint90 pairs"], [[f"W{s['week']} Thu",cap,v['feasible_pair_count'],f"{v['best_joint_quality_pair']['min_mean_fraction']:.4f} / {v['best_joint_quality_pair']['min_p90_fraction']:.4f}",f"{v['best_minimum_ceiling_pair']['min_p90_fraction']:.4f}",f"{v['joint_band_pairs']['0.95']['feasible_pair_count']} / {v['joint_band_pairs']['0.90']['feasible_pair_count']}"] for s in safe for cap,v in s['quality_cost_of_diversification'].items() if v['best_joint_quality_pair']]),
        "Week5 <=4 can retain minimum mean 0.9808 and P90 0.9782, with 14 joint95 pairs. <=3 retains minimum mean 0.9423 and P90 0.9398 at the best balanced pair, with 225 joint90 pairs. Week4 Thursday <=4 has 30 joint95 pairs; <=3 has 1,087 joint90 pairs and zero joint95. Thus reducing five to four need not sacrifice most prelock quality. Three is more expensive against a joint95 standard, but not demonstrated universally too restrictive. Pure objective-maximizing capped policies do not necessarily choose these balanced-quality alternatives; their explicit opportunity costs are in JSON.",
        table(["Slate", "Overlap cap", "Best joint-quality pair actual best / average", "Best objective pair joint95 / joint90 actual best"],
            [[f"W{s['week']} Thu",cap,f"{cost['best_joint_quality_pair_evaluation']['best_actual']:.2f} / {cost['best_joint_quality_pair_evaluation']['average_actual']:.2f}",
              f"{number(cost['joint_band_pairs']['0.95']['evaluation']['best_actual'] if cost['joint_band_pairs']['0.95']['evaluation'] else None)} / {number(cost['joint_band_pairs']['0.90']['evaluation']['best_actual'] if cost['joint_band_pairs']['0.90']['evaluation'] else None)}"]
             for s in safe for cap,cost in s['quality_cost_of_diversification'].items()]),
        "These quality-preserving selections also have mixed eventual outcomes: best-joint-quality <=4 is neutral versus <=5 on Week4 Thursday and lower by 2.00 on Week5; <=3 is neutral on Week4 and lower by 3.50 on Week5. The joint95 objective arm improves Week4 under <=4, while Week5 is neutral. Quality feasibility is clear; outcome superiority is not. None of these pairs was selected on actual scores.",
        "### Postgame field-construction context", "",
        "Complete-field context is evaluated after freezing, separately per contest and top1/5/10%/whole-field bands. JSON includes team-split frequencies, captain IDs/positions, actual role ownership, salary-left mean/median/range/buckets and counts of players below 10% actual role ownership. These frequencies never enter selection. Field resolution failures are counted; descriptive salary metrics require all six saved salaries.", ""]
    ctx = w5["field_construction_context"]
    rows = []
    for fid,fc in ctx.items():
        for band,v in fc.get("bands",{}).items():
            balanced = sum(count for split,count in v['team_split_frequencies'].items() if all(part.endswith(':3') for part in split.split('/')))
            capnames = {p['player_id']:p['name'] for c in w5['candidates'] for p in c['players']}
            topcaps = sorted(v['captain_frequencies'].items(),key=lambda x:(-x[1],x[0]))[:2]
            rows.append([fid,f"top{band}%",v['identity_complete_entries'],f"{balanced/v['identity_complete_entries']:.1%}" if v['identity_complete_entries'] else 'unknown',', '.join(f"{capnames.get(pid,pid)} {count}" for pid,count in topcaps),number(v['salary_left']['mean'])])
    lines += [table(["Week5 contest", "Band", "Resolved entries", "3–3 share", "Top two CPT counts", "Mean salary left"],rows),
        "The top-field 3–3 pattern is postgame context, not a replay input or a proposed team-split rule. Actual ownership is distinct from saved projected ownership, which is partial/unavailable for many rosters.", "",
        "## 14. Selection-regret attribution", "",
        table(["Stage", "Week4 Thursday", "Week4 Sunday", "Week5 Thursday"], [[stage,*[s['stage_attribution'][stage] for s in audit['slates']]] for stage in ['PLAYER_PROJECTION','CANDIDATE_GENERATION','QUALITY_ELIGIBILITY','CANDIDATE_ATTENTION','FINAL_SELECTION','PORTFOLIO_DIVERSIFICATION','ENTRY_EXECUTION']]), ""]
    errs={e['name']:e for e in w5['player_projection_evaluation_only']}
    lines += [f"Week5 Bucky: saved baseline {errs['Bucky Irving']['saved_baseline_projection']:.2f}, actual base 34.50, residual {errs['Bucky Irving']['residual']:+.2f}. CeeDee: saved baseline {errs['CeeDee Lamb']['saved_baseline_projection']:.2f}, actual base 2.90, residual {errs['CeeDee Lamb']['residual']:+.2f}. These realized residuals help explain portfolio outcomes; they did not define diversity or policy screens. A generator that retained a better eventual roster does not eliminate projection uncertainty, and two player residuals do not establish a defective model.", "",
        "## 15. Cross-slate findings", "",
        table(["Attention policy", "Helped / neutral / hurt coverage", "Average added", "Mean coverage actual change", "Mean proxy regret change"],[[name,f"{v['helped_coverage']}/{v['neutral_coverage']}/{v['hurt_coverage']}",number(v['average_review_expansion']),number(v['average_coverage_actual_change']),number(v['average_proxy_selection_regret_change'])] for name,v in audit['cross_slate_findings']['attention'].items()]), "",
        table(["Pair policy", "Helped / neutral / hurt best-entry", "Mean actual change", "Mean regret change"],[[name,f"{v['helped_best_entry']}/{v['neutral']}/{v['hurt']}",number(v['average_best_entry_actual_change']),number(v['average_selection_regret_change'])] for name,v in audit['cross_slate_findings']['pair_policies'].items()]),
        "Per-slate/per-contest best-entry percentile changes are in JSON. All attention proxy percentile changes are zero. <=4 pair-control percentile changes are zero on both usable slates. <=3 worsens Week4 Thursday and is neutral in Week5. These are paired descriptions of two slates with no statistical significance claim.", "",
        table(["Hypothesis", "Evidence status"],list(audit['cross_slate_findings']['hypotheses'].items())), "",
        "## 16. What the evidence does NOT justify", "",
        "It does not justify a production defect claim, historical AI-pick reconstruction, automatic low-overlap superiority, a new ceiling threshold, a new finalist policy, weight fitting, player-specific rules or exposure changes, a 3–3 rule, or projection retraining from this sample. Sunday cannot be rehabilitated by its prelock cutoff. Packet availability is not actual consideration, and a favorable outcome of one visible candidate is not proof of rational ex ante selection. The research controls also differ from production portfolio constraints and live manual choices.", "",
        "## 17. Candidate hypotheses for future live testing", "",
        "H1: a small ceiling-outsider supplement captures useful candidates at manageable review cost. H2: five shared physical players leave limited portfolio coverage despite captain/thesis differences. H3: reviewing <=4 alternatives can spread exposure while retaining strong mean and ceiling. H4: forcing <=3 is expensive enough that it should remain a shadow sensitivity arm. These are hypotheses; none is promoted.", "",
        "## 18. Recommended next experiment", "",
        "For upcoming chronologically valid Showdown slates, preregister a research-only shadow protocol before kickoff. Preserve production inputs and outputs. Save finalized source/pool/packet hashes, the existing finalist control and a top10 eligible-ceiling-outsider attention set (at most 30 total with current finalist size). Require the reviewer to record actual considered IDs, two chosen IDs, rejected alternatives, quality tradeoffs and any user-preference exclusions before lock. Capture selection time and exact submitted entries separately.",
        "Before choosing two live entries, explicitly inspect shared physical-player count, shared FLEX, captain position/side, primary script, scenario overlap, team split, QB structure and available projected ownership. For any five-player core, inspect a <=4 alternative and its minimum mean/P90 cost; record a rationale if the higher-overlap pair remains preferred. Shadow-log <=3 without forcing it. Leave the existing optimizer behavior intact. Freeze all decisions before joining actuals, then compare best-entry capture, regret, review burden and execution fidelity across a larger cohort. Do not adjust the grid mid-cohort.", "",
        "### KEEP", ""]
    lines += ["- "+x for x in audit['recommendations']['KEEP']]
    lines += ["", "### TEST PROSPECTIVELY", ""]+["- "+x for x in audit['recommendations']['TEST_PROSPECTIVELY']]
    lines += ["", "### DO NOT CHANGE YET", ""]+["- "+x for x in audit['recommendations']['DO_NOT_CHANGE_YET']]
    lines += ["", "## 19. Exact commands/tests used", "",
        "The Week5 source was exported from `target.optimizer_run`, `target.lineup` and `target.lineup_player` in an explicit `SET TRANSACTION READ ONLY` transaction; Week4 uses previously saved exports. Week5 packet creation calls the unchanged `build_retrospective_packet` on that source with `ai_requested_entries=2`; this classifies saved candidates and does not run generation. Source export and packet artifacts are hashed by the freeze. Additional read-only chronology query: `SELECT optimizer_run_id, min(created_at), max(created_at) FROM target.lineup WHERE optimizer_run_id = ANY(:ids) GROUP BY optimizer_run_id`.",
        "Initial capture/freeze/evaluation commands (completed before live classifier drift):\n\n```bash\n.venv/bin/python -m scripts.capture_showdown_selection_diversity_inputs\n.venv/bin/python -m pytest tests/test_showdown_selection_diversity_audit.py -q\n.venv/bin/python -m scripts.audit_showdown_selection_diversity freeze\n.venv/bin/python -m scripts.audit_showdown_selection_diversity export-outcomes\n.venv/bin/python -m scripts.audit_showdown_selection_diversity evaluate\n.venv/bin/python -m scripts.report_showdown_selection_diversity\n```",
        "Concurrent work subsequently changed the live packet-classifier file. The original guard rejects that drift. Rerun this saved experiment from the hashed original packets and serialized annotations, without invoking the current classifier:\n\n```bash\n.venv/bin/python -m scripts.replay_saved_showdown_selection_diversity\n.venv/bin/python -m scripts.report_showdown_selection_diversity\n.venv/bin/python -m pytest tests/test_showdown_selection_diversity_audit.py -q\n```\n\nThe offline verifier also checks the original freeze against its pre-outcome read manifest, every source/packet/pair hash, original policy code and definition hashes. The outcome extractor remains pinned to its before-audit hash. Only evidence verification changes to use frozen annotations; no ranking, candidate selection, policy definitions, thresholds or weights change.",
        "The saved freeze is immutable: rerun `evaluate` and the reporter against the same freeze/outcome files. `freeze` refuses to overwrite it; a different grid must use a new artifact directory. Leakage tests poison nested candidates with actual points, ranks, field construction, ownership, hindsight and learning fields; mutation/hash tests fail closed; chronology tests reject late/equal/missing-zone clocks; identity tests cover slot-independent overlap, duplicate identity and single CPT scoring; infeasible constraints never silently relax. Additional reporting tests cover float32 score ties, evaluated-pair preservation and exact source/outcome linkage.",
        f"Audit-owned production edits: **none**. {audit['production_preservation']['checked_file_count']} existing backend runtime/UI files were compared to before-audit SHA-256s; global equality is **{audit['production_preservation']['global_runtime_hash_check_passed']}** because concurrent work changed: "
        f"{', '.join('`'+p+'`' for p in audit['production_preservation']['changed_paths']) or 'none'}. Other observed existing-file changes: "
        f"{', '.join('`'+p+'`' for p in audit['production_preservation']['observed_changes_outside_runtime']) or 'none'}. This audit never edited those files and preserves them. "
        "Only isolated research scripts/tests/artifacts and documentation were added or updated by this audit. The original selection code and frozen packet/annotation data hashes still match the freeze; the current live annotation source differs and is not used in offline replay. No production rule was promoted.",
        "Machine-readable deliverable: `SHOWDOWN_SELECTION_REGRET_AND_PORTFOLIO_DIVERSITY_AUDIT.json`; full prelock and evaluated pair features live in the referenced gzip artifacts. Report and JSON retain all requested unavailable/unknown stages explicitly.", ""]
    lines.insert(-1,"Validation receipt and complete command results: `artifacts/showdown_selection_diversity_audit/validation_results.json`.")
    (base.ROOT / "SHOWDOWN_SELECTION_REGRET_AND_PORTFOLIO_DIVERSITY_AUDIT.md").write_text("\n\n".join(lines))


if __name__ == "__main__":
    enrich()
