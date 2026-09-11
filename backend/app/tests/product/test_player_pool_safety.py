from datetime import UTC, datetime, timedelta

import pandas as pd

from backend.app.product_services.player_pool_safety import (
    ExclusionCategory,
    categorize_exclusion_reason,
    evaluate_player_pool_safety,
)
from backend.app.product_services.rule_library import resolve_strategy_profile


NOW = datetime(2026, 9, 10, 16, tzinfo=UTC)


def _row(player_id: str, **overrides) -> dict:
    row = {
        "player_id": player_id,
        "player_master_id": player_id,
        "name": player_id,
        "position": "WR",
        "player_team": "SEA",
        "opponent_team": "SF",
        "player_status": None,
        "roster_status": "ACT",
        "pregame_availability_probability": 1.0,
        "pregame_context_run_id": "context-current",
        "pregame_context_observed_at": NOW - timedelta(hours=2),
    }
    row.update(overrides)
    return row


def _evaluate(rows: list[dict], **kwargs):
    return evaluate_player_pool_safety(
        pd.DataFrame(rows),
        profile=resolve_strategy_profile(
            contest_format="classic",
            objective="gpp",
        ),
        expected_slate_teams={"SEA", "SF"},
        as_of=NOW,
        **kwargs,
    )


def test_hard_eligibility_and_identity_rules_fail_closed() -> None:
    result = _evaluate(
        [
            _row("eligible"),
            _row("site-id-only", player_master_id=None),
            _row("out", player_status="OUT"),
            _row("off-roster", roster_status="DEV"),
            _row("wrong-team", player_team="NE"),
            _row("unavailable", pregame_availability_probability=0.0),
            _row(
                "late-context",
                pregame_context_observed_at=NOW + timedelta(minutes=1),
            ),
        ],
        projection_cutoff=NOW,
    )

    assert result.eligible_pool["player_id"].tolist() == ["eligible"]
    reasons = {
        row["player_id"]: set(row["exclusion_reasons"])
        for row in result.audit_rows
    }
    assert reasons["site-id-only"] == {"unresolved_canonical_identity"}
    assert reasons["out"] == {"confirmed_unavailable"}
    assert reasons["off-roster"] == {"not_on_current_active_roster"}
    assert reasons["wrong-team"] == {"team_not_confirmed_on_selected_slate"}
    assert reasons["unavailable"] == {"pregame_availability_zero"}
    assert reasons["late-context"] == {"pregame_context_after_projection_cutoff"}
    assert result.summary["excluded_count"] == 6


def test_backup_qb_requires_starter_evidence_or_explicit_package_role() -> None:
    result = _evaluate(
        [
            _row(
                "starter",
                position="QB",
                pregame_start_probability=1.0,
                starting_qb_source="official-depth-chart",
            ),
            _row("backup", position="QB", pregame_start_probability=0.0),
            _row(
                "package-qb",
                position="QB",
                pregame_start_probability=0.0,
                pregame_expected_snaps=3.0,
            ),
        ]
    )

    assert set(result.eligible_pool["player_id"]) == {"starter", "package-qb"}
    backup = next(row for row in result.audit_rows if row["player_id"] == "backup")
    assert backup["exclusion_reasons"] == [
        "backup_qb_without_expected_package_role"
    ]
    package = next(
        row for row in result.audit_rows if row["player_id"] == "package-qb"
    )
    assert package["context"]["expected_snaps"] == 3.0


def test_context_freshness_and_role_uncertainty_are_visible_warnings() -> None:
    result = _evaluate(
        [
            _row(
                "uncertain",
                pregame_context_run_id=None,
                pregame_context_observed_at=NOW - timedelta(days=2),
                pregame_role_label="COMMITTEE",
                injury_status="QUESTIONABLE",
            )
        ]
    )

    assert result.eligible_pool["player_id"].tolist() == ["uncertain"]
    warning_codes = {
        warning["reason_code"] for warning in result.audit_rows[0]["warnings"]
    }
    assert warning_codes == {
        "current_week_context_missing",
        "current_week_context_stale",
        "current_role_uncertain",
        "injury_information_not_incorporated",
    }
    assert result.summary["status"] == "warn"


def test_user_exclusion_is_categorized_and_audited() -> None:
    result = _evaluate(
        [_row("keep"), _row("exclude")],
        user_excluded_player_ids={"exclude"},
    )

    excluded = next(row for row in result.audit_rows if row["player_id"] == "exclude")
    assert excluded["exclusion_reasons"] == ["user_excluded"]
    assert excluded["exclusion_details"][0]["category"] == "user"
    assert categorize_exclusion_reason("no positive projection") is ExclusionCategory.PROJECTION
    assert categorize_exclusion_reason("value threshold") is ExclusionCategory.STRATEGY
