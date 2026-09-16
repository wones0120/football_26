"""Read public DraftKings contest facts and rank single-entry opportunities."""

from __future__ import annotations

import json
import hashlib
import re
from itertools import chain, combinations
from math import ceil
from functools import lru_cache
from random import Random
from datetime import UTC, datetime
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


REQUIRED_FIELDS = ("name", "slate", "draft_group_id", "entry_fee", "capacity", "current_entries", "prize_pool", "paid_places", "payout_ladder", "lock_time", "maximum_entries")
_CONTEST_PATH = re.compile(r"^/draft/contest/(\d+)/?$")
SHARED_RANK_WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)
NEAR_TIE_THRESHOLD = 0.005  # Half a percentage point of the payout proxy.


def blended_profit_proxy(proxy: dict, shared_weight: float) -> float:
    return ((1 - shared_weight) * proxy["independent_rank_proxy"]
            + shared_weight * proxy["shared_percentile_proxy"])


class _DraftKingsRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # noqa: ANN001
        contest_id_from_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def contest_id_from_url(url: str) -> str:
    parsed = urlparse(url.strip())
    match = _CONTEST_PATH.fullmatch(parsed.path)
    if parsed.scheme != "https" or parsed.hostname not in {"draftkings.com", "www.draftkings.com"} or not match:
        raise ValueError(f"Expected a DraftKings https://www.draftkings.com/draft/contest/<id> URL: {url}")
    return match.group(1)


def _embedded_json(html: str, name: str) -> dict:
    marker = re.search(r"window\.mvcVars\." + name + r"\s*=\s*", html)
    if not marker:
        raise ValueError(f"Embedded {name} data unavailable")
    value, _ = json.JSONDecoder().raw_decode(html[marker.end():])
    return value


def _payout_at_rank(ladder: list[dict], rank: int) -> float:
    return next((float(tier["cash"]) for tier in ladder
                 if int(tier["from"]) <= rank <= int(tier["to"])), 0.0)


def _ladder_is_complete(row: dict) -> bool:
    ladder = row.get("payout_ladder") or []
    if not isinstance(ladder, list) or not ladder or any(not isinstance(tier, dict) or any(tier.get(key) is None for key in ("from", "to", "cash")) for tier in ladder):
        return False
    try:
        expected = 1
        for tier in sorted(ladder, key=lambda item: int(item["from"])):
            start, end, cash = int(tier["from"]), int(tier["to"]), float(tier["cash"])
            if start != expected or end < start or cash < 0:
                return False
            expected = end + 1
        if int(row.get("paid_places")) != expected - 1:
            return False
        cash_total = sum((int(tier["to"]) - int(tier["from"]) + 1) * float(tier["cash"]) for tier in ladder)
        return row.get("prize_pool") is not None and abs(cash_total - float(row["prize_pool"])) <= max(.01, cash_total * .00001)
    except (TypeError, ValueError, OverflowError):
        return False


def _unavailable_fields(row: dict) -> list[str]:
    missing = [field for field in REQUIRED_FIELDS if row.get(field) is None or row.get(field) == []]
    for field in ("entry_fee", "capacity", "current_entries", "prize_pool", "paid_places", "maximum_entries"):
        if field not in missing:
            try:
                float(row[field])
            except (TypeError, ValueError, OverflowError):
                missing.append(field)
    if "lock_time" not in missing:
        try:
            datetime.fromisoformat(str(row["lock_time"]).replace("Z", "+00:00"))
        except ValueError:
            missing.append("lock_time")
    ladder = row.get("payout_ladder") or []
    if ladder and not _ladder_is_complete(row):
        missing.append("payout_ladder")
    return sorted(set(missing))


def parse_contest_page(url: str, html: str, *, observed_at: str | None = None) -> dict:
    contest_id = contest_id_from_url(url)
    detail = _embedded_json(html, "contests").get("contestDetail") or {}
    if str(detail.get("contestKey")) != contest_id:
        raise ValueError("Contest ID in page data does not match URL")
    draft_group = (_embedded_json(html, "draftgroups").get("draftGroup") or {})
    ladder = []
    for tier in detail.get("payoutSummary") or []:
        cash = next((item.get("value") for item in tier.get("payoutDescriptions") or []
                     if item.get("payoutDescriptionType") == "Text" and isinstance(item.get("value"), (int, float))), None)
        ladder.append({"from": tier.get("minPosition"), "to": tier.get("maxPosition"), "cash": cash})
    games = draft_group.get("games") or []
    row = {
        "contest_id": contest_id, "url": url.strip(), "name": detail.get("name"),
        "slate": ", ".join(str(game.get("description")) for game in games if game.get("description")) or None,
        "draft_group_id": detail.get("draftGroupId"), "sport": detail.get("sport"),
        "entry_fee": detail.get("entryFee"), "capacity": detail.get("maximumEntries"),
        "current_entries": detail.get("entries"), "prize_pool": detail.get("totalPayouts"),
        "maximum_entries": detail.get("maximumEntriesPerUser"),
        "single_entry": detail.get("maximumEntriesPerUser") == 1,
        "guaranteed": detail.get("isGuaranteed"), "state": detail.get("contestState"),
        "lock_time": detail.get("contestStartTime"), "paid_places": max((tier.get("to") or 0 for tier in ladder), default=None),
        "payout_ladder": ladder, "observed_at": observed_at or datetime.now(UTC).isoformat(),
        "source": "draftkings_embedded_contest_detail", "error": None,
        "source_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "source_payload": {"contestDetail": detail, "draftGroup": draft_group},
    }
    row["unavailable_fields"] = _unavailable_fields(row)
    _add_economics(row)
    return row


def _add_economics(row: dict) -> None:
    ladder = row.get("payout_ladder") or []
    row.pop("economics", None)
    if not any(field in _unavailable_fields(row) for field in ("entry_fee", "capacity", "current_entries", "prize_pool", "paid_places")):
        capacity, entries, fee, pool = (float(row[field]) for field in ("capacity", "current_entries", "entry_fee", "prize_pool"))
        complete = _ladder_is_complete(row)
        paid = int(row["paid_places"])
        top_one_percent = max(1, ceil(capacity * .01))
        top_one_percent_prizes = sum(
            max(0, min(int(tier["to"]), top_one_percent) - int(tier["from"]) + 1) * float(tier["cash"])
            for tier in ladder
        ) if complete else None
        minimum_cash = min((float(tier["cash"]) for tier in ladder), default=None) if complete else None
        lock_time = row.get("lock_time")
        hours_to_lock = ((datetime.fromisoformat(str(lock_time).replace("Z", "+00:00")).astimezone(UTC)
                          - datetime.now(UTC)).total_seconds() / 3600) if lock_time and "lock_time" not in _unavailable_fields(row) else None
        near_lock = hours_to_lock is not None and 0 <= hours_to_lock <= 2
        row["economics"] = {
            "gross_fees_at_capacity": capacity * fee,
            "full_field_rake": 1 - pool / (capacity * fee) if capacity * fee else None,
            "paid_percentage": float(row["paid_places"]) / capacity if capacity else None,
            "minimum_cash": minimum_cash,
            "minimum_cash_multiple": minimum_cash / fee if minimum_cash is not None and fee else None,
            "payout_at_field_percentiles": {
                str(percent): _payout_at_rank(ladder, max(1, ceil(capacity * percent / 100)))
                for percent in (1, 5, 10, 20)
            } if complete else None,
            "median_paid_payout": (
                (_payout_at_rank(ladder, (paid + 1) // 2) + _payout_at_rank(ladder, (paid + 2) // 2)) / 2
            ) if paid and complete else None,
            "first_place_share": _payout_at_rank(ladder, 1) / pool if pool and complete else None,
            "top_10_share": sum(_payout_at_rank(ladder, rank) for rank in range(1, min(10, int(capacity)) + 1)) / pool if pool and complete else None,
            "top_one_percent_share": top_one_percent_prizes / pool if pool and complete else None,
            "payout_flatness": 1 - top_one_percent_prizes / pool if pool and complete else None,
            "unfilled_spots": max(0, int(capacity - entries)),
            "prize_pool_gap_at_current_entries": pool - entries * fee,
            "current_effective_rake": 1 - pool / (entries * fee) if near_lock and row.get("guaranteed") is True and entries * fee else None,
            "current_overlay": max(0.0, pool - entries * fee) if near_lock and row.get("guaranteed") is True else None,
            "effective_field_size_used": max(1, int(entries)) if near_lock and row.get("guaranteed") is True else int(capacity),
            "near_lock": near_lock,
            "cash_total_from_ladder": sum(
                (int(tier["to"]) - int(tier["from"]) + 1) * float(tier["cash"] or 0)
                for tier in ladder
            ) if complete else None,
        }


def fetch_contests(urls: list[str], *, manual: list[dict] | None = None) -> list[dict]:
    if len(urls) > 50:
        raise ValueError("At most 50 contest URLs are supported")
    overrides = {str(row.get("contest_id")): row for row in manual or []}
    rows = []
    seen = set()
    for url in urls:
        contest_id = contest_id_from_url(url)
        if contest_id in seen:
            raise ValueError(f"Duplicate contest URL: {contest_id}")
        seen.add(contest_id)
        try:
            request = Request(url.strip(), headers={"User-Agent": "Mozilla/5.0 (compatible; football26/1.0)"})
            with build_opener(_DraftKingsRedirect()).open(request, timeout=12) as response:
                html = response.read(2_000_001)
            if len(html) > 2_000_000:
                raise ValueError("Contest page exceeds 2 MB")
            row = parse_contest_page(url, html.decode("utf-8", "replace"))
        except Exception as exc:  # per-contest failure remains visible for manual correction
            row = {"contest_id": contest_id, "url": url.strip(), "source": "unavailable", "error": str(exc)}
        override = overrides.get(contest_id, {})
        row.update({key: value for key, value in override.items() if key not in {"contest_id", "url", "source", "observed_at"}})
        if row.get("single_entry") is None and row.get("maximum_entries") is not None:
            row["single_entry"] = int(row["maximum_entries"]) == 1
        row["manual_fields"] = sorted(key for key in override if key not in {"contest_id", "url"})
        row["unavailable_fields"] = _unavailable_fields(row)
        _add_economics(row)
        rows.append(row)
    return rows


def _payout_distribution(contest: dict) -> dict[int, float]:
    field = int(contest["economics"]["effective_field_size_used"])
    amounts: dict[int, float] = {}
    covered = 0
    for tier in contest["payout_ladder"]:
        count = max(0, min(field, int(tier["to"])) - int(tier["from"]) + 1)
        if count:
            cents = round(float(tier["cash"]) * 100)
            amounts[cents] = amounts.get(cents, 0.0) + count / field
            covered += count
    if covered < field:
        amounts[0] = amounts.get(0, 0.0) + (field - covered) / field
    return amounts


def _profit_proxy(subset: tuple[dict, ...]) -> dict:
    """Uniform-rank payout proxy; blend independent and shared-percentile finishes."""
    fees = round(sum(float(row["entry_fee"]) for row in subset) * 100)
    win = fees + 1
    distribution = {0: 1.0}
    for contest in subset:
        next_distribution: dict[int, float] = {}
        for subtotal, subtotal_probability in distribution.items():
            for payout, payout_probability in _payout_distribution(contest).items():
                total = min(win, subtotal + payout)
                next_distribution[total] = next_distribution.get(total, 0.0) + subtotal_probability * payout_probability
        distribution = next_distribution
    independent = distribution.get(win, 0.0)

    breakpoints = {0.0, 1.0}
    for contest in subset:
        field = int(contest["economics"]["effective_field_size_used"])
        breakpoints.update(min(1.0, int(tier["to"]) / field) for tier in contest["payout_ladder"])
    points = sorted(breakpoints)
    aligned = 0.0
    for left, right in zip(points, points[1:]):
        percentile = (left + right) / 2
        total = sum(
            _payout_at_rank(contest["payout_ladder"], max(1, ceil(percentile * int(contest["economics"]["effective_field_size_used"]))))
            for contest in subset
        )
        if round(total * 100) > fees:
            aligned += right - left
    return {"heuristic_value": (independent + aligned) / 2,
            "independent_rank_proxy": independent, "shared_percentile_proxy": aligned,
            "total_entry_fees": fees / 100, "calculation": "exact"}


def select_contests(contests: list[dict], *, mode: str = "auto", budget: float | None = None, maximum: int | None = None) -> tuple[list[dict], dict]:
    if mode not in {"auto", "enter_all"}:
        raise ValueError("contest_selection must be auto or enter_all")
    if budget is not None and budget <= 0:
        raise ValueError("maximum_total_entry_budget must be positive")
    if maximum is not None and maximum < 1:
        raise ValueError("maximum_contests_to_enter must be positive")
    scored = []
    for contest in contests:
        if contest.get("unavailable_fields") or contest.get("single_entry") is not True or not _ladder_is_complete(contest):
            raise ValueError(f"Contest {contest['contest_id']} needs verified single-entry economics; unavailable: {', '.join(contest.get('unavailable_fields', [])) or 'complete cash payout ladder or single-entry status'}")
        if contest.get("state") not in {None, "Upcoming"}:
            raise ValueError(f"Contest {contest['contest_id']} is no longer upcoming")
        fee, capacity, entries, pool = (float(contest[key]) for key in ("entry_fee", "capacity", "current_entries", "prize_pool"))
        if fee <= 0 or capacity <= 0 or entries < 0 or entries > capacity or pool <= 0:
            raise ValueError(f"Contest {contest['contest_id']} has invalid economics")
        row = dict(contest)
        _add_economics(row)
        row["contest_score"] = _profit_proxy((row,))["heuristic_value"]
        scored.append(row)
    scored.sort(key=lambda row: row["contest_id"])
    max_count = min(maximum or len(scored), len(scored))
    best_by_count: dict[int, tuple[tuple[int, ...], dict]] = {}
    sensitivity_candidates: dict[int, list[tuple[tuple[int, ...], dict]]] = {}
    beams: dict[int, list[tuple[tuple[int, ...], dict]]] = {}
    evaluated = 0
    exact = len(scored) <= 10
    samples = 2048
    sample_payouts = []
    for row in scored:
        field = int(row["economics"]["effective_field_size_used"])
        rng = Random(int(hashlib.sha256(row["contest_id"].encode()).hexdigest()[:16], 16))
        sample_payouts.append((
            [round(100 * _payout_at_rank(row["payout_ladder"], max(1, ceil(rng.random() * field)))) for _ in range(samples)],
            [round(100 * _payout_at_rank(row["payout_ladder"], max(1, ceil((index + .5) * field / samples)))) for index in range(samples)],
        ))

    @lru_cache(maxsize=5000)
    def sampled_vectors(indexes: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
        if not indexes:
            return (0,) * samples, (0,) * samples
        previous_independent, previous_aligned = sampled_vectors(indexes[:-1])
        added_independent, added_aligned = sample_payouts[indexes[-1]]
        return (tuple(a + b for a, b in zip(previous_independent, added_independent)),
                tuple(a + b for a, b in zip(previous_aligned, added_aligned)))

    def evaluate(indexes: tuple[int, ...], subset: tuple[dict, ...]) -> dict:
        if len(indexes) <= 3:
            return _profit_proxy(subset)
        fees = round(sum(float(row["entry_fee"]) for row in subset) * 100)
        independent, aligned = sampled_vectors(indexes)
        independent_value = sum(value > fees for value in independent) / samples
        aligned_value = sum(value > fees for value in aligned) / samples
        return {"heuristic_value": (independent_value + aligned_value) / 2,
                "independent_rank_proxy": independent_value, "shared_percentile_proxy": aligned_value,
                "total_entry_fees": fees / 100, "calculation": f"sampled_{samples}"}
    for count in range(1, max_count + 1):
        if exact or count <= 3:
            index_sets = combinations(range(len(scored)), count)
        else:
            cheapest = tuple(sorted(sorted(range(len(scored)), key=lambda index: (float(scored[index]["entry_fee"]), scored[index]["contest_id"]))[:count]))
            index_sets = chain((cheapest,),
                               (tuple(sorted((*prefix, index)))
                                for prefix, _ in beams[count - 1]
                                for index in range(prefix[-1] + 1, len(scored))))
        candidates = []
        seen = set()
        for indexes in index_sets:
            if indexes in seen:
                continue
            seen.add(indexes)
            subset = tuple(scored[index] for index in indexes)
            if budget is not None and sum(float(row["entry_fee"]) for row in subset) > budget + 1e-9:
                continue
            proxy = evaluate(indexes, subset)
            evaluated += 1
            candidates.append((indexes, proxy))
        if not candidates:
            if not exact:
                break
            continue
        candidates.sort(key=lambda item: (-item[1]["heuristic_value"], item[1]["total_entry_fees"], item[0]))
        best_by_count[count] = candidates[0]
        sensitivity_candidates[count] = candidates
        beams[count] = candidates[:40] if not exact else []
    if not best_by_count:
        raise ValueError("No contest fits the selection constraints")
    chosen_count = max(best_by_count) if mode == "enter_all" else max(
        best_by_count, key=lambda count: (best_by_count[count][1]["heuristic_value"], -count)
    )
    chosen_indexes, chosen_proxy = best_by_count[chosen_count]
    selected = [scored[index] for index in chosen_indexes]
    comparisons = [
        {"contest_count": count, "contest_ids": [scored[index]["contest_id"] for index in indexes],
         "contest_names": [scored[index]["name"] for index in indexes], **proxy}
        for count, (indexes, proxy) in sorted(best_by_count.items())
    ]
    def best_at_weight(count: int, weight: float) -> tuple[tuple[int, ...], dict, float]:
        indexes, proxy = min(sensitivity_candidates[count], key=lambda item: (
            -blended_profit_proxy(item[1], weight), item[1]["total_entry_fees"], item[0]
        ))
        return indexes, proxy, blended_profit_proxy(proxy, weight)

    def winner_at_weight(weight: float) -> int:
        return min(best_by_count, key=lambda count: (-best_at_weight(count, weight)[2], count))

    sensitivity = []
    for weight in SHARED_RANK_WEIGHTS:
        values = {count: best_at_weight(count, weight) for count in best_by_count}
        sensitivity.append({"shared_rank_weight": weight,
                            "by_count": [{"contest_count": count,
                                          "contest_ids": [scored[index]["contest_id"] for index in indexes],
                                          "profitability_proxy": value}
                                         for count, (indexes, _, value) in sorted(values.items())],
                            "recommended_count": winner_at_weight(weight)})
    # Bracket changes in the upper envelope; a 0.1% weight step is more precise
    # than the payout proxy itself and allows the best subset to vary by weight.
    crossovers = []
    previous_count = winner_at_weight(0.0)
    for step in range(1, 1001):
        weight = step / 1000
        count = winner_at_weight(weight)
        if count != previous_count:
            crossovers.append({"shared_rank_weight_approx": weight,
                               "from_count": previous_count, "to_count": count})
            previous_count = count
    baseline_values = sorted((row["heuristic_value"] for row in comparisons), reverse=True)
    baseline_gap = baseline_values[0] - baseline_values[1] if len(baseline_values) > 1 else None
    count_summary = "; ".join(
        f"{row['contest_count']} contest(s): {', '.join(row['contest_names'])} at {row['heuristic_value']:.2%}"
        for row in comparisons
    )
    status = ("ENTER ALL" if mode == "enter_all" else
              "NEAR TIE" if baseline_gap is not None and baseline_gap <= NEAR_TIE_THRESHOLD else
              "SENSITIVE" if any(row["recommended_count"] != chosen_count for row in sensitivity) else
              "ROBUST")
    if status == "ENTER ALL":
        status_reason = "Enter all follows the requested budget-feasible contest count; the sensitivity table shows the Auto preference."
    elif status == "NEAR TIE" and any(row["recommended_count"] != chosen_count for row in sensitivity):
        status_reason = "The default margin is within 0.5 percentage points and the preferred count changes across the tested rank assumptions."
    elif status == "NEAR TIE":
        status_reason = "The default margin is within 0.5 percentage points."
    elif status == "SENSITIVE":
        status_reason = "The preferred count changes across the tested rank assumptions."
    else:
        status_reason = "The same count leads across all five tested rank assumptions by more than 0.5 percentage points at the default weight."
    full_field_rows = []
    for row in scored:
        full = dict(row)
        full["economics"] = {**row["economics"], "effective_field_size_used": int(row["capacity"])}
        full_field_rows.append(full)
    full_field_values = {}
    if any(row["economics"]["near_lock"] for row in scored):
        full_samples = []
        for row in full_field_rows:
            field = int(row["capacity"])
            rng = Random(int(hashlib.sha256(row["contest_id"].encode()).hexdigest()[:16], 16))
            full_samples.append((
                [round(100 * _payout_at_rank(row["payout_ladder"], max(1, ceil(rng.random() * field)))) for _ in range(samples)],
                [round(100 * _payout_at_rank(row["payout_ladder"], max(1, ceil((index + .5) * field / samples)))) for index in range(samples)],
            ))

        def full_field_proxy(indexes: tuple[int, ...]) -> float:
            subset = tuple(full_field_rows[index] for index in indexes)
            if len(indexes) <= 3:
                return _profit_proxy(subset)["heuristic_value"]
            fees = round(sum(float(row["entry_fee"]) for row in subset) * 100)
            independent = sum(sum(full_samples[index][0][sample] for index in indexes) > fees for sample in range(samples)) / samples
            shared = sum(sum(full_samples[index][1][sample] for index in indexes) > fees for sample in range(samples)) / samples
            return (independent + shared) / 2

        full_field_values = {count: max(full_field_proxy(indexes) for indexes, _ in candidates)
                             for count, candidates in sensitivity_candidates.items()}
    full_field_count = max(full_field_values, key=lambda count: (full_field_values[count], -count)) if full_field_values else None
    report = {"method": "payout_ladder_profit_proxy_v2", "mode": mode,
              "search_method": "exhaustive_subsets" if exact else "exact_counts_1_to_3_then_beam_40",
              "evaluated_subsets": evaluated, "available_count": len(scored),
              "selected_count": chosen_count, "total_entry_fees": chosen_proxy["total_entry_fees"],
              "ranked_contests": sorted(scored, key=lambda row: (-row["contest_score"], row["contest_id"])),
              "selected_contest_ids": [row["contest_id"] for row in selected],
              "count_comparisons": comparisons, "selected_heuristic_value": chosen_proxy["heuristic_value"],
              "sensitivity": sensitivity, "crossovers": crossovers,
              "recommendation_status": status, "recommendation_status_reason": status_reason,
              "near_tie_threshold": NEAR_TIE_THRESHOLD,
              "full_field_reference_count": full_field_count,
              "overlay_changed_recommendation": (full_field_count != chosen_count if full_field_count is not None and any(row["economics"]["near_lock"] for row in scored) else False),
              "selection_reason": ("Enter all chose the largest budget-feasible count." if mode == "enter_all" else
                                   f"Auto chose {chosen_count} contest(s) because its {chosen_proxy['heuristic_value']:.2%} payout proxy led the feasible counts. {count_summary}."),
              "note": "Heuristic value blends equal-strength independent finishes and fully shared percentile finishes 50/50. Counts 1–3 use exact rank distributions; larger counts use 2,048 fixed rank scenarios. This is not a calibrated win probability; lineup skill, field behavior, and contest correlation await simulation. Near-lock guaranteed contests use current entries within two hours of lock."}
    return selected, report
