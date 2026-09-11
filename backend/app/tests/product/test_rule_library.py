from __future__ import annotations

import pytest

from backend.app.product_services.optimizer import (
    SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID,
    resolve_optimizer_strategy,
)
from backend.app.product_services.rule_library import (
    CLASSIC_HEAD_TO_HEAD_PROFILE_ID,
    CLASSIC_LARGE_GPP_PROFILE_ID,
    SHOWDOWN_HEAD_TO_HEAD_PROFILE_ID,
    SHOWDOWN_LARGE_GPP_PROFILE_ID,
    ConditionOperator,
    RuleCondition,
    RuleDefinition,
    RuleEngine,
    RuleLibrary,
    RuleOverride,
    RuleScope,
    RuleType,
    StrategyProfile,
    resolve_strategy_profile,
    strategy_profile_catalog,
)


def _test_library() -> RuleLibrary:
    return RuleLibrary(
        library_id="unit_test_football_rules",
        version="v1",
        rules=(
            RuleDefinition(
                rule_id="eligibility.active_player_v1",
                description="Only eligible players may enter a final lineup.",
                rule_type=RuleType.HARD_EXCLUSION,
                conditions=(
                    RuleCondition("player.eligible", ConditionOperator.EQ, False),
                ),
                reason_code="ineligible_player",
            ),
            RuleDefinition(
                rule_id="environment.high_team_total_v1",
                description="Reward strong implied scoring environments.",
                rule_type=RuleType.SOFT_BOOST,
                conditions=(
                    RuleCondition("game.implied_team_total", "gte", 26.0),
                ),
                reason_code="high_implied_team_total",
                weight=2.0,
            ),
            RuleDefinition(
                rule_id="role.uncertain_v1",
                description="Reduce confidence in uncertain roles.",
                rule_type=RuleType.SOFT_PENALTY,
                conditions=(RuleCondition("player.role_uncertain", "truthy"),),
                reason_code="uncertain_role",
                weight=3.0,
            ),
            RuleDefinition(
                rule_id="data.current_week_missing_v1",
                description="Call attention to missing current-week context.",
                rule_type=RuleType.WARNING,
                conditions=(RuleCondition("data.current_week_missing", "truthy"),),
                reason_code="current_week_context_missing",
            ),
        ),
    )


def test_rule_engine_returns_explainable_score_exclusion_and_warning() -> None:
    profile = resolve_strategy_profile(
        contest_format="classic",
        objective="gpp",
    )
    result = RuleEngine(_test_library()).evaluate(
        {
            "player": {"eligible": False, "role_uncertain": True},
            "game": {"implied_team_total": 27.5},
            "data": {"current_week_missing": True},
        },
        profile,
        objective_signals={"mean": 20.0, "ceiling": 10.0},
        candidate_id="lineup-1",
    )

    payload = result.to_dict()
    assert result.objective_score == pytest.approx(10.0)
    assert result.rule_adjustment == pytest.approx(-1.0)
    assert result.final_score == pytest.approx(9.0)
    assert result.excluded is True
    assert result.exclusion_reasons == ("ineligible_player",)
    assert result.warnings == ("current_week_context_missing",)
    assert payload["library_version"] == "v1"
    assert payload["profile_id"] == CLASSIC_LARGE_GPP_PROFILE_ID
    assert [trigger["rule_type"] for trigger in payload["triggered_rules"]] == [
        "hard_exclusion",
        "soft_boost",
        "soft_penalty",
        "warning",
    ]


def test_scope_and_profile_override_control_rule_behavior() -> None:
    rule = RuleDefinition(
        rule_id="classic.large_gpp.stack_v1",
        description="Reward a coherent Classic GPP stack.",
        rule_type=RuleType.HARD_EXCLUSION,
        conditions=(RuleCondition("lineup.coherent_stack", "falsy"),),
        reason_code="incoherent_stack",
        weight=5.0,
        scope=RuleScope(
            contest_formats=frozenset({"classic"}),
            contest_styles=frozenset({"large_gpp"}),
        ),
    )
    engine = RuleEngine(RuleLibrary("scope_rules", "v1", (rule,)))
    h2h = resolve_strategy_profile(contest_format="classic", objective="cash")

    skipped = engine.evaluate({"lineup": {"coherent_stack": False}}, h2h)
    assert skipped.triggered_rules == ()
    assert skipped.excluded is False

    reclassified_profile = StrategyProfile(
        profile_id="classic_large_gpp_test_v1",
        version="v1",
        contest_format="classic",
        contest_style="large_gpp",
        description="Test-only profile override.",
        objective_weights={"ceiling": 1.0},
        rule_overrides={
            rule.rule_id: RuleOverride(
                rule_type=RuleType.SOFT_PENALTY,
                weight=2.0,
            )
        },
    )
    result = engine.evaluate(
        {"lineup": {"coherent_stack": False}},
        reclassified_profile,
        objective_signals={"ceiling": 10.0},
    )

    assert result.excluded is False
    assert result.rule_adjustment == pytest.approx(-2.0)
    assert result.triggered_rules[0].rule_type is RuleType.SOFT_PENALTY


def test_four_profiles_are_versioned_and_resolve_by_format_and_objective() -> None:
    catalog = strategy_profile_catalog()

    assert {profile["profile_id"] for profile in catalog} == {
        CLASSIC_HEAD_TO_HEAD_PROFILE_ID,
        CLASSIC_LARGE_GPP_PROFILE_ID,
        SHOWDOWN_HEAD_TO_HEAD_PROFILE_ID,
        SHOWDOWN_LARGE_GPP_PROFILE_ID,
    }
    assert all(profile["version"] == "v1" for profile in catalog)
    assert all(
        set(profile["objective_weights"])
        == {
            "mean",
            "median",
            "floor",
            "ceiling",
            "correlation",
            "ownership",
            "leverage",
            "uniqueness",
        }
        for profile in catalog
    )
    with pytest.raises(ValueError, match="not valid for showdown"):
        resolve_strategy_profile(
            contest_format="showdown",
            objective="cash",
            profile_id=CLASSIC_HEAD_TO_HEAD_PROFILE_ID,
        )


def test_h2h_and_gpp_profiles_rank_the_same_candidates_differently() -> None:
    h2h = resolve_strategy_profile(contest_format="classic", objective="cash")
    gpp = resolve_strategy_profile(contest_format="classic", objective="gpp")
    candidates = {
        "stable": {
            "mean": 20.0,
            "median": 19.0,
            "floor": 16.0,
            "ceiling": 28.0,
            "correlation": 2.0,
            "ownership": 25.0,
            "leverage": 1.0,
            "uniqueness": 1.0,
        },
        "volatile": {
            "mean": 18.0,
            "median": 15.0,
            "floor": 5.0,
            "ceiling": 40.0,
            "correlation": 8.0,
            "ownership": 5.0,
            "leverage": 10.0,
            "uniqueness": 10.0,
        },
    }

    assert h2h.score_objective(candidates["stable"]) > h2h.score_objective(
        candidates["volatile"]
    )
    assert gpp.score_objective(candidates["volatile"]) > gpp.score_objective(
        candidates["stable"]
    )


def test_optimizer_strategy_metadata_includes_the_canonical_rule_profile() -> None:
    strategy = resolve_optimizer_strategy(
        contest_format="showdown",
        objective="gpp",
        strategy=SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID,
    )

    assert strategy["rule_profile_id"] == SHOWDOWN_LARGE_GPP_PROFILE_ID
    assert strategy["rule_profile"]["contest_format"] == "showdown"
    assert strategy["rule_profile"]["contest_style"] == "large_gpp"


def test_rule_library_rejects_duplicate_ids_and_invalid_condition_operator() -> None:
    rule = RuleDefinition(
        rule_id="duplicate_v1",
        description="Duplicate test rule.",
        rule_type="warning",
        conditions=(),
        reason_code="duplicate",
    )
    with pytest.raises(ValueError, match="duplicate rule IDs"):
        RuleLibrary("invalid", "v1", (rule, rule))
    with pytest.raises(ValueError, match="not a valid ConditionOperator"):
        RuleCondition("player.status", "approximately", "OUT")
