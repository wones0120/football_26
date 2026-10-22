"""Research-only opportunity transport; no fantasy scoring or live eligibility changes."""
from __future__ import annotations
from math import isfinite


def allocate(current: list[dict], source: list[dict], actual: dict[str, float], channel: str) -> dict:
    """Transfer relative prior-share shocks, retaining all production in a residual.

    IDs are native stable identities within their own game; rank is a declared
    cross-game role analogy, never an identity join. Unknown prior counts fail
    explicitly rather than acquiring a zero. Eligibility exclusions are ignored.
    """
    if channel not in {"targets", "carries"}:
        raise ValueError("Unsupported opportunity channel")
    for rows in (current, source):
        ids = [p["id"] for p in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate canonical/native role identity")
        for p in rows:
            for c in ("targets", "carries"):
                v = p.get(c)
                if v is None or not isfinite(v) or v < 0:
                    raise ValueError("Unknown or invalid prior role")
    if any(v is None or not isfinite(v) or v < 0 for v in actual.values()):
        raise ValueError("Unknown or invalid observed source opportunity")
    budget = sum(actual.values())
    current_total = sum(p[channel] for p in current)
    source_total = sum(p[channel] for p in source)
    if current_total <= 0 or source_total <= 0:
        return {"counts": {}, "residual": budget, "budget": budget,
                "status": "missing_positive_prior_team_budget"}
    weights = {p["id"]: 0.0 for p in current}
    consumed = set()
    residual = 0.0
    for pos in ("WR", "TE", "RB"):
        key = lambda p: (-(p["targets"] + p["carries"] if pos == "RB" else p["targets"]), p["id"])
        cr = sorted([p for p in current if p["position"] == pos], key=key)
        sr = sorted([p for p in source if p["position"] == pos], key=key)
        for rank, sp in enumerate(sr):
            count = actual.get(sp["id"], 0.0)
            consumed.add(sp["id"])
            if rank >= len(cr) or sp[channel] <= 0:
                residual += count / budget if budget else 0.0
                continue
            # An expansion in the historical source is not evidence that an
            # unrelated zero-prior current role has expanded.
            cp = cr[rank]
            if cp[channel] <= 0:
                residual += count / budget if budget else 0.0
                continue
            weights[cp["id"]] += (cp[channel] / current_total) * (
                (count / budget if budget else 0.0) / (sp[channel] / source_total))
    residual += sum(v for k, v in actual.items() if k not in consumed) / budget if budget else 0.0
    total = sum(weights.values()) + residual
    if not budget:
        return {"counts": weights, "residual": 0.0, "budget": 0.0, "status": "observed_zero_budget"}
    if total <= 0:
        return {"counts": weights, "residual": budget, "budget": budget, "status": "unmapped_source_budget"}
    return {"counts": {k: budget * v / total for k, v in weights.items()},
            "residual": budget * residual / total, "budget": budget, "status": "allocated"}
