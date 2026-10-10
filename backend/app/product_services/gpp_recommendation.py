"""One frozen recommendation from a run's validated GPP candidates.

Without a calibrated field model, expected points is an explicit provisional
ranking surrogate, never a paid-finish probability. No cash selector, marginal
quantile summation as a lineup quantile, or payout/ROI fabrication is used.
"""
from __future__ import annotations

import hashlib
import json
import math

from .draftkings_export import DraftKingsExportService

POLICY_ID = "gpp_projection_first_recommendation_v1"


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def candidate_id(lineup):
    # Classic FLEX assignment is not a different lineup; Captain assignment is.
    slots = sorted((str(p.get("player_id") or ""),
                    str(p.get("roster_position") or "").upper() == "CPT") for p in lineup)
    return hashlib.sha256(json.dumps(slots, separators=(",", ":")).encode()).hexdigest()


def evaluate_candidates(lineups, *, run_id, season, week, slate, contest_format,
                        projection_run_id, data_cutoff_at):
    report = {
        "policy_id": POLICY_ID, "status": "unavailable", "optimizer_run_id": run_id,
        "scope": dict(season=season, week=week, slate=slate, contest_format=contest_format),
        "projection_run_id": projection_run_id, "data_cutoff_at": str(data_cutoff_at) if data_cutoff_at else None,
        "goal": "paid_gpp_finishes", "selection_basis": "projected_points_then_marginal_upside",
        "recommended": None, "candidates": [], "exceptions": [],
        "paid_finish_probability": None, "expected_return": None,
        "limitations": [
            "Provisional projection-first comparison of generated GPP candidates; not a validated paid-finish optimizer.",
            "Paid-finish probability and expected return unavailable: calibrated opponent field and payout evidence are missing.",
            "Upside is the sum of player P90s, not a lineup percentile or tournament win probability.",
            "Only this run's generated candidates were compared; no global optimality or final entry clearance is claimed.",
        ],
    }
    seen = set()
    for index, lineup in enumerate(lineups, 1):
        cid = candidate_id(lineup)
        try:
            DraftKingsExportService.build_lineup_download(contest_format=contest_format,
                lineups=[lineup], run_id=run_id)
            # Showdown discovery may attach scenario-conditioned values. Compare
            # all candidates on the same unconditioned forecast, never the most
            # favorable scenario for each candidate.
            means = [_number(p.get("baseline_projection", p.get("projection"))) for p in lineup]
            if any(v is None for v in means):
                raise ValueError("Missing or non-finite projected points")
            if cid in seen:
                report["exceptions"].append(dict(lineup_number=index, reason="Duplicate candidate"))
                continue
            seen.add(cid)
            upsides = [_number(p.get("baseline_p90", p.get("p90"))) for p in lineup]
            complete_upside = all(v is not None and v >= mean for v, mean in zip(upsides, means))
            risk_players = [dict(player_id=p["player_id"], name=p.get("name") or p.get("player_name"),
                designation=p.get("official_availability_status") or p.get("availability_status") or p.get("injury_status"))
                for p in lineup if str(p.get("official_availability_status") or p.get("availability_status")
                    or p.get("injury_status") or "").upper() in {"Q", "QUESTIONABLE", "D", "DOUBTFUL"}]
            report["candidates"].append(dict(candidate_id=cid, lineup_number=index,
                projected_points=sum(means), marginal_upside_sum=sum(upsides) if complete_upside else None,
                salary=sum(float(p["salary"]) for p in lineup), availability_exceptions=risk_players,
                paid_finish_probability=None, expected_return=None))
            if not complete_upside:
                report["exceptions"].append(dict(lineup_number=index, reason="Marginal upside unavailable or inconsistent"))
        except ValueError as exc:
            report["exceptions"].append(dict(lineup_number=index, reason=str(exc)))
    ranked = sorted(report["candidates"], key=lambda c: (-c["projected_points"],
        -(c["marginal_upside_sum"] if c["marginal_upside_sum"] is not None else -math.inf), c["candidate_id"]))
    for rank, candidate in enumerate(ranked, 1):
        candidate["rank"] = rank
    report["candidates"] = ranked
    if ranked:
        report["status"] = "provisional"
        report["recommended"] = dict(ranked[0])
        report["reason"] = "Highest projected points among the valid generated GPP candidates; marginal upside breaks exact ties, then canonical identity."
    else:
        report["reason"] = "No valid, scoreable GPP candidate is available."
    return report


def recommended_lineup(job):
    """Export only the frozen recommendation; never trust a client index."""
    report = (job.params or {}).get("gpp_recommendation") or {}
    if (job.status != "completed" or job.objective != "gpp" or report.get("policy_id") != POLICY_ID
            or report.get("optimizer_run_id") != job.job_id or report.get("status") != "provisional"):
        raise ValueError("This completed GPP run has no saved recommendation; run the optimizer again")
    scope = dict(season=job.season, week=job.week, slate=job.slate, contest_format=job.contest_format)
    if report.get("scope") != scope or report.get("projection_run_id") != job.projection_run_id:
        raise ValueError("Recommendation scope or projection does not match its saved run")
    selected = report.get("recommended") or {}
    index = selected.get("lineup_number")
    if type(index) is not int or not 1 <= index <= len(job.results or []):
        raise ValueError("Recommended candidate is missing")
    lineup = job.results[index - 1]
    if candidate_id(lineup) != selected.get("candidate_id"):
        raise ValueError("Recommended candidate identity no longer matches its saved lineup")
    return lineup
