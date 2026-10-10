"""Retrospective finalist filtering diagnostics; never imported by the builder."""
from __future__ import annotations

from math import ceil
from typing import Any, Mapping

from .ai_showdown_packet import _number, _saved_candidates, digest, rank_distribution
from .optimizer_effectiveness import candidate_signature, score_signature, field_rank


def audit_finalist_set(packet: Mapping[str, Any], source: Mapping[str, Any],
                       actual_points_by_player: Mapping[str, float], *,
                       universe_best_actual_score: float | None = None,
                       selected_candidate_ids: list[str] | None = None,
                       contest_fields: Mapping[str, Any] | None = None) -> dict:
    """Score a previously frozen packet against canonical base (FLEX) DK points.

    Top tails are percentages of scoreable distinct generated rosters, including
    all ties at ceil(N * pct / 100). They are not contest-field percentiles.
    Missing player scores remain missing, never zero. No candidate selection or
    packet regeneration occurs here.
    """
    body = {k: v for k, v in packet.items() if k not in {"generated_at", "evidence_hash"}}
    if packet.get("contract_id") != "ai_showdown_selection_packet_v1" or digest(body) != packet.get("evidence_hash"):
        raise ValueError("Frozen packet hash or contract mismatch")
    run_id = str(source.get("job_id") or source.get("optimizer_run_id") or "")
    if run_id != packet["run"]["optimizer_run_id"]:
        raise ValueError("Audit source optimizer run mismatch")
    pool, manifest = _saved_candidates(source)
    if manifest["sha256"] != packet["run"]["candidate_pool_hash"]:
        raise ValueError("Audit source candidate pool hash mismatch")
    actuals = {str(pid): _number(points) for pid, points in actual_points_by_player.items()}
    if any(points is None for points in actuals.values()):
        raise ValueError("Actual scores must be finite canonical base points")
    unique = {}
    for index, c in enumerate(pool, 1):
        signature = candidate_signature(c, "showdown")
        if signature is None: raise ValueError("Audit candidate lacks canonical roster")
        cid = f"{run_id}:{digest(signature)[:16]}"
        rank = int(c.get("rank") or index)
        if cid not in unique or rank < unique[cid]["selector_rank"]:
            score, missing = score_signature(signature, actuals)
            unique[cid] = {"candidate_id": cid, "selector_rank": rank,
                           "actual_score": score, "missing_player_ids": missing}
    finalist_ids = {c["candidate_id"] for c in packet["finalists"]}
    if not finalist_ids <= set(unique): raise ValueError("Frozen finalist missing from saved pool")
    scored = sorted((r for r in unique.values() if r["actual_score"] is not None),
                    key=lambda r: (-r["actual_score"], r["selector_rank"], r["candidate_id"]))
    for r in scored:
        r["actual_rank"] = 1 + sum(s["actual_score"] > r["actual_score"] for s in scored)
        r["is_finalist"] = r["candidate_id"] in finalist_ids
    finalists = [r for r in scored if r["is_finalist"]]
    best = scored[0] if scored else None
    best_finalist = finalists[0] if finalists else None
    tied_best = [r for r in scored if best and r["actual_score"] == best["actual_score"]]
    tails = {}
    for pct in (1, 5, 10):
        threshold = scored[ceil(len(scored) * pct / 100) - 1]["actual_score"] if scored else None
        tail = [r for r in scored if r["actual_score"] >= threshold] if scored else []
        retained = sum(r["is_finalist"] for r in tail)
        tails[f"top_{pct}_percent"] = {"score_threshold": threshold, "generated_count": len(tail),
                                      "finalist_count": retained, "retention_rate": retained / len(tail) if tail else None,
                                      "retained_selector_ranks": sorted(r["selector_rank"] for r in tail if r["is_finalist"])}
    selected = list(selected_candidate_ids) if selected_candidate_ids is not None else None
    if selected is not None and (len(selected) != packet["pool_summary"]["requested_entries"] or
                                 len(set(selected)) != len(selected) or not set(selected) <= finalist_ids):
        raise ValueError("Manual selection must contain the requested number of unique frozen finalists")
    selected_rows = [unique[cid] for cid in selected] if selected is not None else []
    selected_best = max(r["actual_score"] for r in selected_rows) if selected_rows and all(r["actual_score"] is not None for r in selected_rows) else None
    universe = _number(universe_best_actual_score)
    if universe_best_actual_score is not None and (universe is None or best and universe < best["actual_score"]):
        raise ValueError("Universe benchmark must be finite and at least the generated best score")
    field_tails = {}
    for contest_id, field in sorted((contest_fields or {}).items()):
        size = field.get("reported_field_size")
        points = [_number(v) for v in field.get("entry_points", [])]
        if not size or len(points) != size or any(v is None for v in points):
            field_tails[contest_id] = {"status": "unavailable", "reason": "complete_scored_contest_field_required",
                                      "reported_field_size": size, "loaded_entries": len(points)}
            continue
        ordered = sorted(points, reverse=True)
        ranks = {r["candidate_id"]: field_rank(r["actual_score"], ordered) for r in scored}
        tails_by_pct = {}
        for pct in (1, 5, 10):
            ids = {cid for cid, rank in ranks.items() if rank["top_percent_conservative"] <= pct}
            retained = ids & finalist_ids
            tails_by_pct[f"top_{pct}_percent"] = {"generated_count": len(ids), "finalist_count": len(retained),
                                                   "retention_rate": len(retained) / len(ids) if ids else None,
                                                   "retained_selector_ranks": sorted(unique[cid]["selector_rank"] for cid in retained)}
        field_tails[contest_id] = {"status": "complete", "field_size": size, "field_winner_score": ordered[0],
                                  "denominator": "complete_contest_field_worst_tied_rank_percentile",
                                  "top_tails": tails_by_pct,
                                  "finalist_field_rank_distribution": rank_distribution([ranks[cid]["worst_rank"] for cid in sorted(finalist_ids & set(ranks))])}
    return {"contract_id": "ai_showdown_finalist_set_audit_v1", "packet_hash": packet["evidence_hash"],
            "data_readiness": packet.get("data_readiness"),
            "generation_evidence_sha256": (packet.get("data_readiness") or {}).get("evidence_sha256"),
            "optimizer_run_id": run_id, "finalist_policy_version": packet["finalist_policy_version"],
            "timing_status": packet["run"].get("timing_status", "prelock_saved_run"),
            "status": "complete" if len(scored) == len(unique) else "partial_actual_coverage",
            "actuals_hash": digest(actuals), "distinct_generated_count": len(unique), "scoreable_generated_count": len(scored),
            "finalist_count": len(finalist_ids), "scoreable_finalist_count": len(finalists),
            "top_tail_denominator": "scoreable_distinct_generated_rosters_with_cutoff_ties",
            "best_generated_actual_score": best["actual_score"] if best else None,
            "best_finalist_actual_score": best_finalist["actual_score"] if best_finalist else None,
            "finalist_selection_regret": round(best["actual_score"] - best_finalist["actual_score"], 2) if best and best_finalist else None,
            "eventual_best_generated_candidate_included": any(r["is_finalist"] for r in tied_best) if best else None,
            "all_tied_best_generated_candidates_included": all(r["is_finalist"] for r in tied_best) if best else None,
            "best_generated_selector_rank": best["selector_rank"] if best else None,
            "best_generated_candidates": tied_best,
            "selector_rank_of_best_finalist": best_finalist["selector_rank"] if best_finalist else None,
            "actual_rank_distribution": rank_distribution([r["actual_rank"] for r in finalists]), "top_tails": tails,
            "contest_field_top_tails": field_tails,
            "regret_decomposition": {
                "candidate_generation_regret": round(universe - best["actual_score"], 2) if universe is not None and best else None,
                "candidate_generation_reason": None if universe is not None else "complete_physical_universe_benchmark_not_supplied",
                "finalist_filtering_regret": round(best["actual_score"] - best_finalist["actual_score"], 2) if best and best_finalist else None,
                "ai_manual_selection_regret": round(best_finalist["actual_score"] - selected_best, 2) if best_finalist and selected_best is not None else None,
                "ai_manual_selection_reason": None if selected is not None else "no_frozen_ai_manual_selection_supplied"},
            "finalist_actuals": finalists,
            "unscored_candidates": [r for r in unique.values() if r["actual_score"] is None]}


def render_audit_markdown(audit: Mapping[str, Any]) -> str:
    lines = ["# Post-slate finalist-set audit", "", "Retrospective diagnostic; never used for packet generation.", "",
             f"Run `{audit['optimizer_run_id']}` · packet `{audit['packet_hash']}` · timing {audit['timing_status']}",
             f"Actual coverage: {audit['status']} · {audit['scoreable_generated_count']}/{audit['distinct_generated_count']} generated; {audit['scoreable_finalist_count']}/{audit['finalist_count']} finalists.",
             f"Best generated {audit['best_generated_actual_score']} · best finalist {audit['best_finalist_actual_score']} · filtering regret {audit['finalist_selection_regret']}",
             f"Generated best included: {audit['eventual_best_generated_candidate_included']} · best generated selector rank {audit['best_generated_selector_rank']} · best finalist selector rank {audit['selector_rank_of_best_finalist']}",
             "", "Top tails use scoreable distinct generated candidates and include cutoff ties; these are not field percentiles.", "",
             "| Generated tail | Generated count | Finalist count | Retention |", "|---|---:|---:|---:|"]
    for label, tail in audit["top_tails"].items():
        lines.append(f"| {label} | {tail['generated_count']} | {tail['finalist_count']} | {tail['retention_rate']} |")
    lines += ["", f"Actual rank distribution: {audit['actual_rank_distribution']}",
              f"Complete contest-field tail retention: {audit.get('contest_field_top_tails', {})}",
              f"Regret decomposition: {audit['regret_decomposition']}", ""]
    return "\n".join(lines)
