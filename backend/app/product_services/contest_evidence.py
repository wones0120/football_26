"""Normalized contest-field evidence and conservative counterfactual scoring."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping


_CASH_NAME_MARKERS = {
    "double_up": ("double up", "double-up"),
    "fifty_fifty": ("50/50", "50-50", "fifty fifty"),
    "head_to_head": ("head to head", "head-to-head", "h2h"),
    "triple_up": ("triple up", "triple-up"),
    "multiplier": ("quintuple up", "quintuple-up", "5x", "10x multiplier", "multiplier"),
    "other_cash": ("cash game",),
}
_GPP_NAME_MARKERS = (
    "millionaire",
    "tournament",
    "gpp",
    "play-action",
    "play action",
    "fair catch",
)


def _float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def classify_contest_type(
    contest_name: object,
    declared_type: object = None,
) -> dict[str, str | None]:
    """Classify cash/GPP only from an explicit value or unambiguous name marker."""
    declared = str(declared_type or "").strip().lower()
    if declared and declared not in {"cash", "gpp", "unknown"}:
        raise ValueError("contest_type must be 'cash', 'gpp', or omitted")

    name = " ".join(str(contest_name or "").lower().split())
    cash_game_type = next(
        (
            game_type
            for game_type, markers in _CASH_NAME_MARKERS.items()
            if any(marker in name for marker in markers)
        ),
        None,
    )
    if declared in {"cash", "gpp"}:
        return {
            "contest_type": declared,
            "contest_type_source": "explicit",
            "cash_game_type": cash_game_type if declared == "cash" else None,
        }
    if cash_game_type:
        return {
            "contest_type": "cash",
            "contest_type_source": "contest_name",
            "cash_game_type": cash_game_type,
        }
    if any(marker in name for marker in _GPP_NAME_MARKERS):
        return {
            "contest_type": "gpp",
            "contest_type_source": "contest_name",
            "cash_game_type": None,
        }
    return {
        "contest_type": "unknown",
        "contest_type_source": "unclassified",
        "cash_game_type": None,
    }


def _quantile(sorted_values: list[float], probability: float) -> float | None:
    if not sorted_values:
        return None
    position = (len(sorted_values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _score_hash(rows: list[tuple[str, int | None, float]]) -> str:
    encoded = json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_contest_field_evidence(
    contest: Mapping[str, Any],
    entries: Iterable[Mapping[str, Any]],
    payout_tiers: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build a compact, content-hashed field summary from normalized entry results."""
    unique_entries: dict[str, dict[str, Any]] = {}
    for ordinal, entry in enumerate(entries):
        points = _float(entry.get("entry_points"))
        if points is None:
            continue
        entry_id = str(entry.get("entry_id") or f"row-{ordinal}")
        unique_entries[entry_id] = {
            "entry_id": entry_id,
            "rank": _int(entry.get("rank")),
            "entry_points": points,
        }

    rows = sorted(
        unique_entries.values(),
        key=lambda row: (
            row["rank"] if row["rank"] is not None else 10**12,
            -row["entry_points"],
            row["entry_id"],
        ),
    )
    scores_desc = sorted((row["entry_points"] for row in rows), reverse=True)
    scores_asc = list(reversed(scores_desc))
    field_size = _int(contest.get("field_size")) or 0
    observed_entries = len(rows)
    field_complete = field_size > 0 and observed_entries == field_size

    classification = classify_contest_type(
        contest.get("contest_name"),
        contest.get("contest_type"),
    )
    tiers = []
    for tier in payout_tiers:
        min_rank = _int(tier.get("min_rank"))
        max_rank = _int(tier.get("max_rank"))
        if min_rank is None or max_rank is None:
            continue
        tiers.append(
            {
                "min_rank": min_rank,
                "max_rank": max_rank,
                "payout": _float(tier.get("payout")),
                "prize_description": str(tier.get("prize_description") or "").strip() or None,
            }
        )
    tiers.sort(key=lambda tier: (tier["min_rank"], tier["max_rank"]))

    paid_ranks = [tier["max_rank"] for tier in tiers if (tier["payout"] or 0) > 0]
    paid_max_rank = max(paid_ranks) if paid_ranks else None
    cash_line_points = None
    if paid_max_rank and field_complete:
        ranked_paid_scores = [
            row["entry_points"]
            for row in rows
            if row["rank"] is not None and row["rank"] <= paid_max_rank
        ]
        if ranked_paid_scores:
            cash_line_points = min(ranked_paid_scores)
        elif len(scores_desc) >= paid_max_rank:
            cash_line_points = scores_desc[paid_max_rank - 1]

    verified_cash_line = bool(
        classification["contest_type"] == "cash"
        and field_complete
        and paid_max_rank
        and cash_line_points is not None
    )
    hash_rows = [
        (str(row["entry_id"]), row["rank"], float(row["entry_points"]))
        for row in rows
    ]
    return {
        "contest_id": str(contest.get("contest_id") or ""),
        "contest_name": str(contest.get("contest_name") or ""),
        "contest_format": str(contest.get("contest_format") or "").lower(),
        **classification,
        "entry_fee": _float(contest.get("entry_fee")),
        "field_size": field_size,
        "observed_entries": observed_entries,
        "field_complete": field_complete,
        "field_proxy_eligible": field_complete and observed_entries > 0,
        "median_points": _quantile(scores_asc, 0.5),
        "p25_points": _quantile(scores_asc, 0.25),
        "p75_points": _quantile(scores_asc, 0.75),
        "winning_points": scores_desc[0] if scores_desc else None,
        "paid_max_rank": paid_max_rank,
        "cash_line_points": cash_line_points,
        "cash_line_verified": verified_cash_line,
        "cash_line_evidence_status": (
            "exact_ranked_payout_threshold" if verified_cash_line else "unavailable"
        ),
        "payout_tiers": tiers,
        "source_file_id": contest.get("source_file_id"),
        "source_content_sha256": contest.get("content_sha256"),
        "entry_points_hash": _score_hash(hash_rows),
        "_entry_scores": scores_desc,
    }


def _payout_at_rank(rank: int, tiers: Iterable[Mapping[str, Any]]) -> float | None:
    for tier in tiers:
        if int(tier["min_rank"]) <= rank <= int(tier["max_rank"]):
            return _float(tier.get("payout"))
    return 0.0


def score_lineup_against_contest(
    actual_points: float | None,
    contest: Mapping[str, Any],
) -> dict[str, Any]:
    """Score a synthetic entry conservatively, preserving tie-boundary uncertainty."""
    scores = [float(value) for value in contest.get("_entry_scores", [])]
    eligible = bool(
        actual_points is not None
        and contest.get("field_proxy_eligible")
        and scores
    )
    result = {
        "contest_id": contest.get("contest_id"),
        "contest_name": contest.get("contest_name"),
        "contest_type": contest.get("contest_type"),
        "cash_game_type": contest.get("cash_game_type"),
        "entry_fee": contest.get("entry_fee"),
        "eligible": eligible,
        "field_complete": bool(contest.get("field_complete")),
        "margin_vs_median": None,
        "field_percentile": None,
        "synthetic_rank_best": None,
        "synthetic_rank_worst": None,
        "cash_line_points": contest.get("cash_line_points"),
        "margin_vs_cash_line": None,
        "cash_status": "unavailable",
        "cash_hit": None,
        "double_up_hit": None,
        "payout_min": None,
        "payout_max": None,
        "payout_exact": None,
        "roi_exact": None,
    }
    if not eligible:
        return result

    score = float(actual_points)
    best_rank = 1 + sum(field_score > score for field_score in scores)
    worst_rank = 1 + sum(field_score >= score for field_score in scores)
    result.update(
        {
            "margin_vs_median": round(score - float(contest["median_points"]), 3),
            "field_percentile": round(sum(field_score < score for field_score in scores) / len(scores), 6),
            "synthetic_rank_best": best_rank,
            "synthetic_rank_worst": worst_rank,
        }
    )

    paid_max_rank = _int(contest.get("paid_max_rank"))
    cash_line = _float(contest.get("cash_line_points"))
    if contest.get("cash_line_verified") and paid_max_rank and cash_line is not None:
        if worst_rank <= paid_max_rank:
            cash_status = "cashed"
            cash_hit: bool | None = True
        elif best_rank > paid_max_rank:
            cash_status = "missed"
            cash_hit = False
        else:
            cash_status = "tie_boundary"
            cash_hit = None
        result.update(
            {
                "margin_vs_cash_line": round(score - cash_line, 3),
                "cash_status": cash_status,
                "cash_hit": cash_hit,
                "double_up_hit": (
                    cash_hit if contest.get("cash_game_type") == "double_up" else None
                ),
            }
        )

    tiers = contest.get("payout_tiers") or []
    entry_fee = _float(contest.get("entry_fee"))
    if tiers and entry_fee is not None and entry_fee > 0:
        best_payout = _payout_at_rank(best_rank, tiers)
        worst_payout = _payout_at_rank(worst_rank, tiers)
        known = [value for value in (best_payout, worst_payout) if value is not None]
        if len(known) == 2:
            payout_min = min(known)
            payout_max = max(known)
            payout_exact = payout_min if payout_min == payout_max else None
            result.update(
                {
                    "payout_min": payout_min,
                    "payout_max": payout_max,
                    "payout_exact": payout_exact,
                    "roi_exact": (
                        round((payout_exact - entry_fee) / entry_fee, 6)
                        if payout_exact is not None
                        else None
                    ),
                }
            )
    return result


def public_field_evidence(field_evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Remove private score arrays while retaining their deterministic content hash."""
    public = dict(field_evidence)
    public["contests"] = [
        {key: value for key, value in dict(contest).items() if not str(key).startswith("_")}
        for contest in field_evidence.get("contests", [])
    ]
    return public
