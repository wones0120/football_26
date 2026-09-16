import json

import pytest

from backend.app.product_services.showdown_contests import (
    contest_id_from_url, parse_contest_page, select_contests,
)


def contest(contest_id="123", fee=5, capacity=100, entries=90, pool=450):
    return {
        "contest_id": contest_id, "name": contest_id, "entry_fee": fee,
        "capacity": capacity, "current_entries": entries, "prize_pool": pool,
        "paid_places": 25, "payout_ladder": [{"from": 1, "to": 25, "cash": 18}],
        "lock_time": "2026-09-18T00:15:00Z", "maximum_entries": 1,
        "single_entry": True, "unavailable_fields": [],
    }


def test_parse_embedded_draftkings_details_and_payouts():
    detail = {"contestDetail": {
        "contestKey": "123", "name": "Test [Single Entry]", "entryFee": 5,
        "maximumEntries": 100, "entries": 90, "totalPayouts": 450,
        "draftGroupId": 7,
        "maximumEntriesPerUser": 1, "isGuaranteed": True,
        "contestStartTime": "2026-09-18T00:15:00Z", "payoutSummary": [
            {"minPosition": 1, "maxPosition": 1, "payoutDescriptions": [{"payoutDescriptionType": "Text", "value": 50}]},
            {"minPosition": 2, "maxPosition": 25, "payoutDescriptions": [{"payoutDescriptionType": "Text", "value": 18}]},
        ],
    }}
    group = {"draftGroup": {"games": [{"description": "DET @ BUF"}]}}
    html = f"<script>window.mvcVars.contests = {json.dumps(detail)}; window.mvcVars.draftgroups = {json.dumps(group)};</script>"
    row = parse_contest_page("https://www.draftkings.com/draft/contest/123", html)
    assert row["single_entry"] is True
    assert row["slate"] == "DET @ BUF"
    assert row["paid_places"] == 25
    assert row["payout_ladder"][-1] == {"from": 2, "to": 25, "cash": 18}
    assert row["unavailable_fields"] == []
    assert row["source_payload"]["contestDetail"]["contestKey"] == "123"
    assert len(row["source_sha256"]) == 64


def test_url_allowlist_and_identity():
    assert contest_id_from_url("https://www.draftkings.com/draft/contest/123") == "123"
    with pytest.raises(ValueError):
        contest_id_from_url("https://draftkings.com.evil.example/draft/contest/123")


def test_auto_and_enter_all_obey_budget_and_maximum():
    rows = [contest("1"), contest("2"), contest("3")]
    selected, report = select_contests(rows, mode="enter_all", budget=10)
    assert len(selected) == 2
    assert report["total_entry_fees"] == 10
    selected, _ = select_contests(rows, mode="auto", maximum=1)
    assert len(selected) == 1


def test_missing_or_multi_entry_economics_are_rejected():
    row = contest()
    row["single_entry"] = False
    with pytest.raises(ValueError, match="single-entry"):
        select_contests([row])


def test_preview_route_returns_fetched_contest(monkeypatch):
    from backend.app.api.product_routes import preview_optimizer_contests
    from backend.app.product_schemas import ContestPreviewRequest
    from backend.app.product_services import showdown_contests

    monkeypatch.setattr(showdown_contests, "fetch_contests", lambda urls, manual: [contest("123")])
    result = preview_optimizer_contests(ContestPreviewRequest(urls=["https://www.draftkings.com/draft/contest/123"]))
    assert result["contests"][0]["contest_id"] == "123"
    assert result["refreshed_at"]
