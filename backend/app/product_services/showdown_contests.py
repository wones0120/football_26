"""Read public DraftKings contest facts and rank single-entry opportunities."""

from __future__ import annotations

import json
import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


REQUIRED_FIELDS = ("name", "slate", "draft_group_id", "entry_fee", "capacity", "current_entries", "prize_pool", "paid_places", "payout_ladder", "lock_time", "maximum_entries")
_CONTEST_PATH = re.compile(r"^/draft/contest/(\d+)/?$")


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


def _unavailable_fields(row: dict) -> list[str]:
    missing = [field for field in REQUIRED_FIELDS if row.get(field) is None or row.get(field) == []]
    ladder = row.get("payout_ladder") or []
    if ladder and any(tier.get("from") is None or tier.get("to") is None or tier.get("cash") is None for tier in ladder):
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
    if all(row.get(field) is not None for field in ("entry_fee", "capacity", "current_entries", "prize_pool", "paid_places")):
        capacity, entries, fee, pool = (float(row[field]) for field in ("capacity", "current_entries", "entry_fee", "prize_pool"))
        row["economics"] = {
            "gross_fees_at_capacity": capacity * fee,
            "implied_rake_fraction": 1 - pool / (capacity * fee) if capacity * fee else None,
            "paid_percentage": float(row["paid_places"]) / capacity if capacity else None,
            "unfilled_spots": max(0, int(capacity - entries)),
            "prize_pool_gap_at_current_entries": pool - entries * fee,
            "cash_total_from_ladder": sum(
                (int(tier["to"]) - int(tier["from"]) + 1) * float(tier["cash"] or 0)
                for tier in ladder
            ) if "payout_ladder" not in _unavailable_fields(row) else None,
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


def select_contests(contests: list[dict], *, mode: str = "auto", budget: float | None = None, maximum: int | None = None) -> tuple[list[dict], dict]:
    if mode not in {"auto", "enter_all"}:
        raise ValueError("contest_selection must be auto or enter_all")
    if budget is not None and budget <= 0:
        raise ValueError("maximum_total_entry_budget must be positive")
    if maximum is not None and maximum < 1:
        raise ValueError("maximum_contests_to_enter must be positive")
    scored = []
    for contest in contests:
        if contest.get("unavailable_fields") or contest.get("single_entry") is not True:
            raise ValueError(f"Contest {contest['contest_id']} needs verified single-entry economics; unavailable: {', '.join(contest.get('unavailable_fields', [])) or 'single-entry status'}")
        if contest.get("state") not in {None, "Upcoming"}:
            raise ValueError(f"Contest {contest['contest_id']} is no longer upcoming")
        fee, capacity, entries, pool = (float(contest[key]) for key in ("entry_fee", "capacity", "current_entries", "prize_pool"))
        if fee <= 0 or capacity <= 0 or entries < 0 or entries > capacity or pool <= 0:
            raise ValueError(f"Contest {contest['contest_id']} has invalid economics")
        ladder = contest["payout_ladder"]
        top_one_percent = max(1, int(capacity * .01))
        prize_outside_top = sum(
            max(0, int(tier["to"]) - max(int(tier["from"]) - 1, top_one_percent)) * float(tier["cash"] or 0)
            for tier in ladder
        )
        flatness = min(1.0, prize_outside_top / pool)
        lock_time = str(contest["lock_time"]).replace("Z", "+00:00")
        hours_to_lock = (datetime.fromisoformat(lock_time).astimezone(UTC) - datetime.now(UTC)).total_seconds() / 3600
        overlay = max(0.0, min(1.0, (pool - fee * entries) / pool)) if contest.get("guaranteed") is True else 0.0
        components = {
            "rake_score": max(0.0, min(1.0, pool / (fee * capacity))),
            "potential_overlay": overlay,
            "overlay_score": overlay if hours_to_lock <= 2 else 0.0,
            "field_size_score": 1 / (1 + capacity / 1000),
            "payout_percentage": min(1.0, float(contest["paid_places"]) / capacity),
            "payout_flatness": flatness,
            "entry_fee_score": 1 / (1 + fee / 10),
        }
        score = (.30 * components["rake_score"] + .15 * components["overlay_score"]
                 + .15 * components["field_size_score"] + .15 * components["payout_percentage"]
                 + .15 * components["payout_flatness"] + .10 * components["entry_fee_score"])
        scored.append({**contest, "contest_score": score, "contest_score_components": components})
    scored.sort(key=lambda row: (-row["contest_score"], row["contest_id"]))
    selected = []
    total_fee = 0.0
    for row in scored:
        fee = float(row["entry_fee"])
        if maximum is not None and len(selected) >= maximum:
            break
        if budget is not None and total_fee + fee > budget + 1e-9:
            continue
        # This is a contest-quality cutoff, not an estimated return or probability.
        if mode == "auto" and selected and row["contest_score"] < 0.50:
            continue
        selected.append(row)
        total_fee += fee
    if not selected:
        raise ValueError("No contest fits the selection constraints")
    report = {"method": "transparent_contest_heuristic_v1", "mode": mode,
              "score_weights": {"rake_score": .30, "overlay_score": .15, "field_size_score": .15,
                                "payout_percentage": .15, "payout_flatness": .15, "entry_fee_score": .10},
              "auto_score_cutoff_after_first": .50, "available_count": len(scored),
              "selected_count": len(selected), "total_entry_fees": total_fee,
              "ranked_contests": scored, "selected_contest_ids": [row["contest_id"] for row in selected],
              "note": "Potential overlay is a live upper bound, not projected ROI. It enters the score only within two hours of lock."}
    return selected, report
