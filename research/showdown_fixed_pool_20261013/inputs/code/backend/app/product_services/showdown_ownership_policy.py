"""Separate ownership coverage from explicit Showdown selector promotion."""
from __future__ import annotations


def showdown_ownership_policy(headers: list[dict], run_ids: list[str]) -> dict:
    """Global validation and diagnostic estimates are not slot-specific approval.

    This consumes an explicit saved promotion decision, not new thresholds or
    fitted weights. Missing evidence fails closed and raw estimates remain
    available in diagnostics.
    """
    approved = bool(run_ids) and len(headers) == len(set(run_ids))
    for header in headers:
        metrics = header.get("metrics_json") or {}
        approval = (metrics.get("selector_approval_by_format") or {}).get("showdown") or {}
        approved = approved and approval.get("status") == "approved"
    return {
        "policy_id": "showdown_explicit_slot_promotion_v1",
        "eligible": bool(approved), "run_ids": sorted(set(run_ids)),
        "reason": "explicit Showdown selector approval" if approved else
                  "Showdown slot estimates remain diagnostic until explicit selector approval",
        "raw_estimates_retained": True,
    }
