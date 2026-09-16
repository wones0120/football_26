import json
from datetime import UTC, datetime, timedelta

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
        "maximumEntries": 100, "entries": 90, "totalPayouts": 482,
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
    economics = row["economics"]
    assert economics["paid_percentage"] == .25
    assert economics["minimum_cash"] == 18
    assert economics["minimum_cash_multiple"] == 3.6
    assert economics["payout_at_field_percentiles"] == {"1": 50, "5": 18, "10": 18, "20": 18}
    assert economics["median_paid_payout"] == 18
    assert economics["first_place_share"] == pytest.approx(50 / 482)
    assert economics["top_10_share"] == pytest.approx((50 + 9 * 18) / 482)
    assert economics["full_field_rake"] == pytest.approx(1 - 482 / 500)
    assert economics["current_effective_rake"] is None
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
    assert [row["contest_count"] for row in report["count_comparisons"]] == [1, 2]


def test_auto_compares_all_counts_and_can_choose_one_with_budget_remaining():
    rows = [contest(str(index), pool=150) for index in range(3)]
    for row in rows:
        row["payout_ladder"][0]["cash"] = 6
    selected, report = select_contests(rows, mode="auto", budget=15)
    assert len(selected) == 1
    assert [row["contest_count"] for row in report["count_comparisons"]] == [1, 2, 3]
    assert report["count_comparisons"][0]["heuristic_value"] > report["count_comparisons"][1]["heuristic_value"]
    assert report["selected_heuristic_value"] == report["count_comparisons"][0]["heuristic_value"]
    assert [row["shared_rank_weight"] for row in report["sensitivity"]] == [0, .25, .5, .75, 1]
    assert all(len(row["by_count"]) == 3 for row in report["sensitivity"])
    assert report["recommendation_status"] in {"ROBUST", "SENSITIVE", "NEAR TIE"}
    for row in report["sensitivity"]:
        assert row["recommended_count"] == min(
            row["by_count"], key=lambda value: (-value["profitability_proxy"], value["contest_count"])
        )["contest_count"]


def test_incomplete_payout_ladder_is_explicitly_rejected():
    row = contest(pool=500)
    with pytest.raises(ValueError, match="payout ladder"):
        select_contests([row])


def test_near_lock_guarantee_reports_current_effective_rake_and_overlay():
    row = contest(pool=500)
    row["payout_ladder"][0]["cash"] = 20
    row["guaranteed"] = True
    row["lock_time"] = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    selected, report = select_contests([row])
    economics = selected[0]["economics"]
    assert economics["current_overlay"] == 50
    assert economics["current_effective_rake"] == pytest.approx(1 - 500 / 450)
    assert economics["effective_field_size_used"] == 90
    assert report["full_field_reference_count"] == 1
    assert report["overlay_changed_recommendation"] is False


def test_even_paid_field_uses_middle_two_payouts_for_median():
    row = contest(pool=216)
    row["paid_places"] = 24
    row["payout_ladder"] = [
        {"from": 1, "to": 12, "cash": 10},
        {"from": 13, "to": 24, "cash": 8},
    ]
    selected, _ = select_contests([row])
    assert selected[0]["economics"]["median_paid_payout"] == 9


def test_large_pool_reports_approximate_subset_search():
    rows = [contest(str(index), pool=150) for index in range(12)]
    for row in rows:
        row["payout_ladder"][0]["cash"] = 6
    _, report = select_contests(rows, maximum=12)
    assert report["search_method"] == "exact_counts_1_to_3_then_beam_40"
    assert [row["contest_count"] for row in report["count_comparisons"]] == list(range(1, 13))


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
