"""Offline, outcome-blind Captain/FLEX comparison on explicit frozen archives."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import platform
from zoneinfo import ZoneInfo

import pulp

from backend.app.product_services.captain_flex_research import compare, digest, number
from backend.app.product_services.showdown_portfolio_selection import signature

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    data = json.loads(path.read_text())
    if isinstance(data, dict) and "payload" in data:
        if digest(data["payload"]) != data["sha256"]:
            raise ValueError(f"Source checksum mismatch: {path}")
        return data["payload"]
    return data


def clock(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timezone-aware source clocks required")
    return result


def find_report(saved, key):
    return next(p[key] for lineup in saved["results"] for p in lineup if p.get(key))


def load_slate(spec):
    source_paths = [ROOT / spec["source"]]
    saved = read(source_paths[0])
    if spec["kind"] == "common_universe":
        source_paths.extend([ROOT/spec["pool"], ROOT/spec["job"]])
        freeze, job = (read(p) for p in source_paths[1:])
        if saved["input_sha256"] != digest(freeze):
            raise ValueError("Universe does not match its frozen pool")
        raw_pool = freeze["player_pool"]
        candidates = [deepcopy(r["worlds"]["baseline"]) for r in saved["records"]]
        projection_id = freeze["projection_run_id"]
        if job["projection_run_id"] != projection_id:
            raise ValueError("Job/projection mismatch")
    elif spec["kind"] == "saved_report":
        job = saved
        raw_pool = saved["player_pool"]["rows"]
        projection_id = saved["projection_run_id"]
        report = find_report(saved, "captain_family_coverage_report")
        if report.get("quality_basis") != "common_baseline":
            raise ValueError("Archive lacks comparable common-baseline selector scores")
        pool = {p["player_id"]: p for p in raw_pool}
        candidates = []
        for record in report["ranked_metrics"]:
            lineup = []
            for p in record["players"]:
                a, base = p["adjustment"], pool[p["player_id"]]
                mult = 1.5 if p["slot"] == "CPT" else 1.
                lineup.append({"player_id": p["player_id"], "name": p["name"],
                    "roster_position": p["slot"], "player_team": p["team"],
                    "position": base["position"], "salary": mult*float(base["salary"]),
                    "projection": a["baseline_mean"], "p90": a["baseline_p90"]})
            if not math.isclose(sum(p["salary"] for p in lineup), record["salary"], abs_tol=.01):
                raise ValueError("Frozen roster salary does not reconstruct")
            lineup[0]["solver_objective_value"] = record["selector"]
            candidates.append(lineup)
    else:
        raise ValueError("Unknown archive adapter")
    # Same physical roster may have multiple discovery labels. Keep its best
    # saved baseline selector, using canonical identity for deterministic order.
    unique = {}
    for lineup in candidates:
        for p in lineup:
            p["projection"] = p.get("baseline_projection", p["projection"])
            p["p90"] = p.get("baseline_p90", p["p90"])
        lineup[0]["showdown_scenario_id"] = "baseline"
        sig = signature(lineup)
        if sig not in unique or lineup[0]["solver_objective_value"] > unique[sig][0]["solver_objective_value"]:
            unique[sig] = lineup
    candidates = [[{k: p[k] for k in ("player_id", "name", "roster_position", "player_team",
        "position", "salary", "projection", "p90", "solver_objective_value", "showdown_scenario_id") if k in p}
        for p in unique[s]] for s in sorted(unique)]
    ids = {p["player_id"] for l in candidates for p in l}
    players = []
    for raw in raw_pool:
        if raw["player_id"] not in ids:
            continue
        players.append({k: raw.get(k) for k in (
            "player_id", "position", "pregame_expected_carries", "pregame_expected_targets",
            "projected_carries", "projected_targets", "carries_mean_3", "targets_mean_3",
            "opportunity_diagnostic")} | {
            "name": raw.get("name") or raw["player_name"],
            "team": raw.get("player_team") or raw["team"],
            "mean": float(raw["projection"]), "p90": float(raw["p90"]),
            "salary": float(raw["salary"])})
    pool = {p["player_id"]: p for p in players}
    if ids != pool.keys():
        raise ValueError("Candidate identity missing in frozen pool")
    for lineup in candidates:
        if len(lineup) != 6 or len({p["player_id"] for p in lineup}) != 6:
            raise ValueError("Invalid physical roster")
        if sum(float(p["salary"]) for p in lineup) > 50000.01:
            raise ValueError("Illegal salary")
        if len({p["player_team"] for p in lineup}) != 2:
            raise ValueError("Both teams required")
        for p in lineup:
            base = pool[p["player_id"]]
            mult = 1.5 if p["roster_position"] == "CPT" else 1.
            if p["player_team"] != base["team"] or any(not math.isclose(
                float(p[k]), mult*base[b], abs_tol=1e-6) for k,b in
                (("projection", "mean"), ("p90", "p90"), ("salary", "salary"))):
                raise ValueError("Candidate does not match canonical baseline forecast/salary")
    exposure = find_report(job, "portfolio_exposure_report")
    selection_report = find_report(job, "captain_family_coverage_report")
    rates = {r["exposure_class"]: r["configured_cap"] for r in exposure["rows"]}
    # Classes not represented in the selected roster use explicit saved runtime
    # controls, or the v3 contract recorded in this experiment's manifest.
    rates = {**spec["exposure_rates"], **rates}
    requested = exposure["requested_lineups"]
    limits = {p["player_id"]: max(1, math.ceil(requested*rates[
        "starting_qb" if p["position"] == "QB" else "cheap_punt" if p["salary"] <= 1000 else "core"]))
        for p in players}
    kickoff = clock(spec["kickoff"])
    # Verify the manifest kickoff against the native game schedule in the source.
    game = job["results"][0][0]["game_id"]
    native_time = datetime.strptime(game.split(" ",1)[1], "%m/%d/%Y %I:%M%p ET").replace(tzinfo=ZoneInfo("America/New_York"))
    if kickoff != native_time:
        raise ValueError("Manifest kickoff differs from frozen native schedule")
    clocks = {"job_created_at": job["created_at"], "data_cutoff_at": job["data_cutoff_at"]}
    prelock = all(clock(v) < kickoff for v in clocks.values())
    return players, candidates, {"requested": requested, "player_limits": limits,
        "captain_limit": max(1, math.ceil(requested*exposure["configured_captain_cap"])),
        "quality_fraction": float(selection_report["quality_fraction"])}, {
        "projection_run_id": projection_id, "source_job_id": job["job_id"],
        "source_files": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
        "clocks": clocks, "kickoff": spec["kickoff"],
        "pregame_clock_eligible": prelock,
        "timing_note": "Recorded forecast/job clocks checked; filesystem copy time is not prelock proof. Research policy was created after outcomes.",
        "saved_selected_ids": [digest(signature(l)) for l in job["results"]]}


def actual_map(payload, spec):
    if (payload["season"], payload["week"], payload["slate"]) != (spec["season"], spec["week"], spec["slate"]):
        raise ValueError("Actual-score slate scope mismatch")
    observations = payload.get("observations")
    if observations is None:
        observations = [p for e in payload["entries"] if e.get("identity_complete")
                        for p in e["players"]]
    values = defaultdict(set)
    for p in observations:
        if p.get("resolution_status", "resolved") != "resolved" or not p.get("player_id"):
            continue
        if p.get("roster_position") not in {"CPT", "FLEX"}:
            raise ValueError("Actual scoring requires explicit CPT/FLEX slots")
        score = number(p.get("actual_points"))
        if score is not None:
            values[p["player_id"]].add(round(score/(1.5 if p["roster_position"] == "CPT" else 1), 6))
    conflicts = sorted(pid for pid, points in values.items() if len(points) != 1)
    return {pid: next(iter(points)) for pid, points in values.items() if len(points) == 1}, conflicts


def attach_actuals(report, candidates, actuals):
    """Post-selection evaluation only; missing/conflicting labels never become 0."""
    scores, missing = {}, {}
    for lineup in candidates:
        key = digest(signature(lineup))
        missing[key] = sorted({p["player_id"] for p in lineup}-actuals.keys())
        scores[key] = None if missing[key] else sum(actuals[p["player_id"]]*(1.5 if p["roster_position"] == "CPT" else 1) for p in lineup)
    complete = all(v is not None for v in scores.values())
    best = max((v for v in scores.values() if v is not None), default=None)
    for variant in report["variants"].values():
        selected = variant["selected_ids"]
        actual = [scores[i] for i in selected]
        scored = [v for v in actual if v is not None]
        variant["actual_evaluation"] = {"scores": actual, "scored_count": len(scored),
            "missing_player_ids": sorted({pid for i in selected for pid in missing[i]}),
            "mean": sum(scored)/len(scored) if scored and len(scored)==len(selected) else None,
            "best": max(scored) if scored and len(scored)==len(selected) else None,
            "retained_candidate_regret": best-max(scored) if complete and scored and len(scored)==len(selected) else None}
    report["actual_coverage"] = {"complete_candidate_labels": complete,
        "scored_candidates": sum(v is not None for v in scores.values()), "candidate_count": len(scores),
        "best_scoreable_retained_candidate": best, "candidate_scores": scores}


def render(result):
    lines = ["# Captain ceiling and conditional FLEX research", "",
        "Offline retrospective experiment; production defaults unchanged. Scores are uncalibrated conditional-upside proxies, not payout estimates.", "",
        "| Slate | Recorded pregame clocks | Candidates | Actual labels | Arm | Captains | Actual mean | Actual best | Retained-candidate regret |",
        "|---|---|---:|---|---|---|---:|---:|---:|"]
    for slate in result["slates"]:
        coverage = slate["actual_coverage"]
        for arm in ("saved_selector", "ceiling_only", "captain_flex"):
            v = slate["variants"][arm]; a=v["actual_evaluation"]
            fmt = lambda n: "unavailable" if n is None else f"{n:.2f}"
            lines.append(f"| {slate['label']} | {slate['lineage']['pregame_clock_eligible']} | {len(slate['rows'])} | {coverage['scored_candidates']}/{coverage['candidate_count']} | {arm} | {', '.join(v['captains'])} | {fmt(a['mean'])} | {fmt(a['best'])} | {fmt(a['retained_candidate_regret'])} |")
    for slate in result["slates"]:
        lines.extend(["", f"## {slate['label']}: selected conditional explanations", ""])
        by_id = {r["candidate_id"]: r for r in slate["rows"]}
        for key in slate["variants"]["captain_flex"]["selected_ids"]:
            r=by_id[key]
            lines.extend([f"- **{r['captain']} CPT**: captain P90 {r['captain_p90_points']:.2f}; conditional captain contribution {r['captain_tail_mean_points_proxy']:.2f}; FLEX lift {r['flex_conditional_lift']:+.2f}; total proxy {r['captain_flex']:.2f}.",
                "  " + "; ".join(f"{p['name']} {p['conditional_lift']:+.2f}" for p in r['flex'])])
        baseline = set(slate["variants"]["captain_flex"]["selected_ids"])
        lines.extend(["", "Sensitivity: " + "; ".join(f"{arm}: {len(baseline.symmetric_difference(set(v['selected_ids'])))//2} roster replacements" for arm,v in slate["variants"].items() if arm in {"half_dependence","unknown_roles_low","unknown_roles_high","no_competition"}),
            f"Missing workload evidence: {len(slate['unknown_role_player_ids'])} QB/RB players. Full canonical-ID evidence and factor contributions are in the JSON.", ""])
    lines.extend(["## Interpretation", "", "Do not promote this policy. The sample is small, priors are unfitted, role evidence is incomplete, and post-kickoff archives are excluded from pregame conclusions. Regret is against retained candidates only, not the full legal universe. No field, payout, duplication or calibrated bust model is evaluated.", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT/"docs/research/captain_flex_manifest.json")
    parser.add_argument("--output", type=Path, default=ROOT/"artifacts/captain_flex_research")
    args = parser.parse_args()
    manifest = read(args.manifest)
    result = {"manifest": manifest, "production_defaults_changed": False, "slates": []}
    # No outcome files are opened until every arm on every slate is selected.
    prepared = []
    for spec in manifest["slates"]:
        players, candidates, controls, lineage = load_slate(spec)
        report = compare(players, candidates, **controls)
        report.update(label=spec["label"], lineage=lineage,
                      frozen_replay_inputs={"players": players, "candidates": candidates, "controls": controls})
        report["saved_selector_reproduces_original_portfolio"] = (set(lineage["saved_selected_ids"])
            == set(report["variants"]["saved_selector"]["selected_ids"]))
        if spec["kind"] == "saved_report" and not report["saved_selector_reproduces_original_portfolio"]:
            raise ValueError("Baseline replay does not reproduce saved physical portfolio")
        report["selection_sha256"] = digest(report["variants"])
        prepared.append((spec, candidates, report))
    for spec, candidates, report in prepared:
        actual_path = ROOT/spec["actuals"]
        actuals, conflicts = actual_map(read(actual_path), spec)
        attach_actuals(report, candidates, actuals)
        report["actual_source_sha256"] = hashlib.sha256(actual_path.read_bytes()).hexdigest()
        report["conflicting_actual_player_ids"] = conflicts
        report["historical_outcome_comparison_eligible"] = (report["lineage"]["pregame_clock_eligible"]
            and report["actual_coverage"]["complete_candidate_labels"])
        result["slates"].append(report)
    result["implementation_sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
        (Path(__file__), ROOT/"backend/app/product_services/captain_flex_research.py",
         ROOT/"backend/app/product_services/showdown_portfolio_selection.py",
         ROOT/"backend/app/product_services/showdown_scenario_value.py")}
    result["runtime"] = {"python": platform.python_version(), "pulp": pulp.__version__,
        "cbc_sha256": hashlib.sha256(Path(pulp.PULP_CBC_CMD.pulp_cbc_path).read_bytes()).hexdigest()}
    result["experiment_id"] = digest(result)
    args.output.mkdir(parents=True, exist_ok=True)
    for suffix, content in (("json", json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+"\n"), ("md", render(result))):
        path = args.output/f"{result['experiment_id']}.{suffix}"
        if path.exists():
            if path.read_text() != content:
                raise ValueError("Immutable experiment content differs")
        else:
            with path.open("x") as handle:
                handle.write(content)
        print(path)


if __name__ == "__main__":
    main()
