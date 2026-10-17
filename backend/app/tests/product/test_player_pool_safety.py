from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from backend.app.product_services.player_pool_safety import (
    ExclusionCategory,
    categorize_exclusion_reason,
    evaluate_player_pool_safety,
    validate_player_pool_evidence_consistency,
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


def test_roster_evidence_is_scoped_to_the_players_team() -> None:
    result = _evaluate(
        [
            _row("matched-active", roster_status="ACT", roster_evidence_available=True),
            _row(
                "unmatched-alias",
                player_team="SF",
                opponent_team="SEA",
                roster_status=None,
                roster_evidence_available=False,
            ),
        ]
    )

    assert set(result.eligible_pool["player_id"]) == {
        "matched-active",
        "unmatched-alias",
    }
    unmatched = next(
        row for row in result.audit_rows if row["player_id"] == "unmatched-alias"
    )
    assert "not_on_current_active_roster" not in unmatched["exclusion_reasons"]


def test_starting_qb_and_roster_conflict_fails_before_filtering() -> None:
    with pytest.raises(ValueError, match="starter evidence conflicts with roster status MISSING"):
        validate_player_pool_evidence_consistency(
            pd.DataFrame(
                [
                    _row(
                        "starter",
                        name="Starting Quarterback",
                        position="QB",
                        is_starting_qb=True,
                        roster_status=None,
                        roster_evidence_available=True,
                    )
                ]
            )
        )


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


@pytest.mark.parametrize("contest_format", ["classic", "showdown"])
@pytest.mark.parametrize("objective", ["cash", "gpp"])
@pytest.mark.parametrize("enabled", [False, True])
def test_questionable_preference_applies_to_every_profile(
    contest_format: str, objective: str, enabled: bool,
) -> None:
    pool = pd.DataFrame([
        _row("salary-q", player_status=" q ", projection=18.4, p90=31.2),
        _row("injury-q", injury_status="Questionable"),
        _row("context-q", pregame_injury_status="Q"),
        _row("cleared", injury_status="Q", pregame_injury_status="ACTIVE"),
        _row("doubtful", player_status="D"),
        _row("healthy"),
        _row("out", player_status="OUT"),
    ])
    original = pool.copy(deep=True)
    result = evaluate_player_pool_safety(
        pool,
        profile=resolve_strategy_profile(contest_format=contest_format, objective=objective),
        as_of=NOW,
        exclude_questionable=enabled,
    )
    expected = {"cleared", "doubtful", "healthy"}
    if not enabled:
        expected |= {"salary-q", "injury-q", "context-q"}
    assert set(result.eligible_pool["player_id"]) == expected
    pd.testing.assert_frame_equal(pool, original)
    audit = next(row for row in result.audit_rows if row["player_id"] == "salary-q")
    assert audit["exclusion_reasons"] == (["user_excluded_questionable"] if enabled else [])
    if enabled:
        assert audit["exclusion_details"][0]["category"] == "user"
        assert audit["exclusion_details"][0]["rule_id"] == "user.preference.questionable_exclusion_v1"


def test_named_questionable_research_eligibility_preserves_truth_and_unavailable_gate():
    rows = [_row('allowed', player_status='Q'), _row('other', player_status='Q'), _row('out', player_status='OUT')]
    result = _evaluate(rows, exclude_questionable=True, questionable_eligible_player_ids=['allowed','out'])
    assert set(result.eligible_pool.player_id)=={'allowed'}
    assert rows[0]['player_status']=='Q'
    audit = {r['player_id']:r for r in result.audit_rows}
    assert audit['allowed']['eligibility_assumption']['source_status_unchanged']
    assert 'user_excluded_questionable' in audit['other']['exclusion_reasons']
    assert audit['out']['included'] is False
