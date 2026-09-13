"""Versioned, explainable player-level context preferences for optimizers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd

from .rule_library import (
    RuleCondition,
    RuleDefinition,
    RuleEngine,
    RuleEvaluation,
    RuleLibrary,
    RuleScope,
    RuleType,
    StrategyProfile,
)


PLAYER_CONTEXT_LIBRARY_ID = "optimizer_player_context"
PLAYER_CONTEXT_LIBRARY_VERSION = "v2"
OFFENSIVE_POSITIONS = frozenset({"QB", "RB", "WR", "TE"})
PASS_GAME_POSITIONS = frozenset({"QB", "WR", "TE"})
RED_ZONE_POSITIONS = frozenset({"RB", "WR", "TE"})


def _context_rule(
    rule_id: str,
    description: str,
    rule_type: RuleType,
    conditions: tuple[RuleCondition, ...],
    reason_code: str,
    *,
    weight: float = 0.0,
    magnitude_field: str | None = None,
    contest_styles: tuple[str, ...] = (),
) -> RuleDefinition:
    return RuleDefinition(
        rule_id=rule_id,
        description=description,
        rule_type=rule_type,
        conditions=conditions,
        reason_code=reason_code,
        weight=weight,
        magnitude_field=magnitude_field,
        scope=RuleScope(contest_styles=frozenset(contest_styles)),
        metadata={
            "policy_status": "initial_policy_unvalidated",
            "score_unit": "optimizer_points",
        },
    )


PLAYER_CONTEXT_LIBRARY = RuleLibrary(
    library_id=PLAYER_CONTEXT_LIBRARY_ID,
    version=PLAYER_CONTEXT_LIBRARY_VERSION,
    rules=(
        _context_rule(
            "environment.high_game_total_v1",
            "Prefer offensive players as the game total rises above the neutral range.",
            RuleType.SOFT_BOOST,
            (
                RuleCondition("player.is_offense", "truthy"),
                RuleCondition("signals.high_game_total", "gt", 0.0),
            ),
            "high_game_total",
            weight=0.45,
            magnitude_field="signals.high_game_total",
        ),
        _context_rule(
            "environment.high_team_total_v1",
            "Prefer offensive players as their implied team total rises.",
            RuleType.SOFT_BOOST,
            (
                RuleCondition("player.is_offense", "truthy"),
                RuleCondition("signals.high_team_total", "gt", 0.0),
            ),
            "high_implied_team_total",
            weight=0.65,
            magnitude_field="signals.high_team_total",
        ),
        _context_rule(
            "environment.low_team_total_v1",
            "Apply a modest penalty as an offense's implied team total falls.",
            RuleType.SOFT_PENALTY,
            (
                RuleCondition("player.is_offense", "truthy"),
                RuleCondition("signals.low_team_total", "gt", 0.0),
            ),
            "low_implied_team_total",
            weight=0.45,
            magnitude_field="signals.low_team_total",
        ),
        _context_rule(
            "environment.competitive_shootout_pass_game_v1",
            "Reward passing-game roles in high-total games with competitive spreads.",
            RuleType.SOFT_BOOST,
            (
                RuleCondition("player.pass_game_candidate", "truthy"),
                RuleCondition("signals.competitive_shootout", "gt", 0.0),
            ),
            "competitive_high_total_pass_environment",
            weight=0.40,
            magnitude_field="signals.competitive_shootout",
        ),
        _context_rule(
            "role.favorite_running_back_v1",
            "Increase running-back preference as the team becomes a meaningful favorite.",
            RuleType.SOFT_BOOST,
            (
                RuleCondition("player.position", "eq", "RB"),
                RuleCondition("signals.favorite", "gt", 0.0),
            ),
            "favorite_running_back",
            weight=0.55,
            magnitude_field="signals.favorite",
        ),
        _context_rule(
            "role.favorite_goal_line_back_v1",
            "Give favorite running backs an additional boost for source-backed goal-line work.",
            RuleType.SOFT_BOOST,
            (
                RuleCondition("player.position", "eq", "RB"),
                RuleCondition("signals.favorite_goal_line", "gt", 0.0),
            ),
            "favorite_goal_line_running_back",
            weight=0.45,
            magnitude_field="signals.favorite_goal_line",
        ),
        _context_rule(
            "role.underdog_receiving_volume_v1",
            "Prefer pass catchers as underdog game script raises expected passing volume.",
            RuleType.SOFT_BOOST,
            (
                RuleCondition("player.receiving_candidate", "truthy"),
                RuleCondition("signals.underdog_receiving", "gt", 0.0),
            ),
            "underdog_receiving_volume",
            weight=0.45,
            magnitude_field="signals.underdog_receiving",
        ),
        _context_rule(
            "role.underdog_early_down_back_v1",
            "Reduce early-down running-back preference as negative game script grows.",
            RuleType.SOFT_PENALTY,
            (
                RuleCondition("player.position", "eq", "RB"),
                RuleCondition("signals.underdog_early_down", "gt", 0.0),
            ),
            "underdog_early_down_running_back",
            weight=0.40,
            magnitude_field="signals.underdog_early_down",
        ),
        _context_rule(
            "role.extreme_favorite_passing_volume_v1",
            "Slightly reduce passing-volume preference for extreme favorites.",
            RuleType.SOFT_PENALTY,
            (
                RuleCondition("player.position", "in", PASS_GAME_POSITIONS),
                RuleCondition("signals.extreme_favorite", "gt", 0.0),
            ),
            "extreme_favorite_passing_volume",
            weight=0.35,
            magnitude_field="signals.extreme_favorite",
        ),
        _context_rule(
            "role.red_zone_involvement_v1",
            "Prefer players with source-backed red-zone involvement.",
            RuleType.SOFT_BOOST,
            (
                RuleCondition("player.position", "in", RED_ZONE_POSITIONS),
                RuleCondition("signals.red_zone_role", "gt", 0.0),
            ),
            "strong_red_zone_involvement",
            weight=0.35,
            magnitude_field="signals.red_zone_role",
        ),
        _context_rule(
            "role.stable_volume_h2h_v1",
            "Prefer source-backed stable volume in Head-to-Head contests.",
            RuleType.SOFT_BOOST,
            (RuleCondition("signals.stable_volume", "gt", 0.0),),
            "stable_projected_volume",
            weight=0.80,
            magnitude_field="signals.stable_volume",
            contest_styles=("head_to_head",),
        ),
        _context_rule(
            "role.stable_volume_gpp_v1",
            "Use stable volume as a modest supporting signal in large-field GPPs.",
            RuleType.SOFT_BOOST,
            (RuleCondition("signals.stable_volume", "gt", 0.0),),
            "stable_projected_volume",
            weight=0.30,
            magnitude_field="signals.stable_volume",
            contest_styles=("large_gpp",),
        ),
        _context_rule(
            "role.uncertainty_h2h_v1",
            "Penalize explicit role uncertainty more strongly in Head-to-Head contests.",
            RuleType.SOFT_PENALTY,
            (RuleCondition("signals.role_uncertainty", "gt", 0.0),),
            "uncertain_current_role",
            weight=1.00,
            magnitude_field="signals.role_uncertainty",
            contest_styles=("head_to_head",),
        ),
        _context_rule(
            "role.uncertainty_gpp_v1",
            "Apply only a modest role-uncertainty penalty in large-field GPPs.",
            RuleType.SOFT_PENALTY,
            (RuleCondition("signals.role_uncertainty", "gt", 0.0),),
            "uncertain_current_role",
            weight=0.40,
            magnitude_field="signals.role_uncertainty",
            contest_styles=("large_gpp",),
        ),
        _context_rule(
            "context.market_missing_v1",
            "No source-backed game total, team total, and spread are available for scoring.",
            RuleType.WARNING,
            (RuleCondition("data.market_missing", "truthy"),),
            "game_environment_missing",
        ),
        _context_rule(
            "context.opportunity_missing_v1",
            "No source-backed current opportunity field is available for this offensive player.",
            RuleType.WARNING,
            (RuleCondition("data.opportunity_missing", "truthy"),),
            "current_opportunity_missing",
        ),
    ),
)


@dataclass
class PlayerContextScoringResult:
    scored_pool: pd.DataFrame
    evaluations: dict[str, RuleEvaluation]
    audit_rows: list[dict[str, Any]]
    summary: dict[str, Any]


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().upper() in {"", "<NA>", "NAN", "NONE", "NULL"}
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _number(row: Mapping[str, Any], *fields: str) -> float | None:
    for field in fields:
        value = row.get(field)
        if _missing(value):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if pd.notna(number):
            return number
    return None


def _text(row: Mapping[str, Any], *fields: str) -> str:
    for field in fields:
        value = row.get(field)
        if not _missing(value):
            return str(value).strip()
    return ""


def _bool(row: Mapping[str, Any], *fields: str) -> bool:
    for field in fields:
        value = row.get(field)
        if _missing(value):
            continue
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}
    return False


def _bounded(value: float | None) -> float:
    if value is None:
        return 0.0
    return min(1.0, max(0.0, float(value)))


def _scaled_above(value: float | None, floor: float, width: float) -> float:
    if value is None or width <= 0:
        return 0.0
    return _bounded((value - floor) / width)


def _scaled_below(value: float | None, ceiling: float, width: float) -> float:
    if value is None or width <= 0:
        return 0.0
    return _bounded((ceiling - value) / width)


def _player_context(row: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    position = _text(row, "position", "roster_position").upper()
    game_total = _number(row, "game_total_line", "game_total")
    team_spread = _number(row, "team_spread_line", "spread")
    team_total = _number(row, "team_implied_total", "team_total")
    market_lineage_safe = _bool(row, "market_context_point_in_time_safe")
    market_available = bool(
        market_lineage_safe
        and game_total is not None
        and game_total > 0
        and team_total is not None
        and team_total > 0
        and team_spread is not None
    )

    target_share = _number(row, "pregame_target_share")
    carry_share = _number(row, "pregame_carry_share")
    expected_snaps = _number(row, "pregame_expected_snaps")
    expected_routes = _number(row, "pregame_expected_routes")
    expected_carries = _number(row, "pregame_expected_carries")
    expected_targets = _number(row, "pregame_expected_targets")
    red_zone_share = _number(row, "pregame_red_zone_share")
    goal_line_share = _number(row, "pregame_goal_line_share")
    start_probability = _number(row, "pregame_start_probability")
    opportunity_values = (
        target_share,
        carry_share,
        expected_snaps,
        expected_routes,
        expected_carries,
        expected_targets,
        red_zone_share,
        goal_line_share,
        start_probability,
    )
    opportunity_available = any(value is not None for value in opportunity_values)

    receiving_strength = max(
        _scaled_above(target_share, 0.0, 0.28),
        _scaled_above(expected_targets, 0.0, 8.0),
        _scaled_above(expected_routes, 0.0, 32.0),
    )
    rushing_strength = max(
        _scaled_above(carry_share, 0.0, 0.65),
        _scaled_above(expected_carries, 0.0, 18.0),
    )
    if position == "QB":
        volume_strength = max(
            _bounded(start_probability),
            1.0 if _bool(row, "is_starting_qb") else 0.0,
        )
    elif position == "RB":
        volume_strength = max(rushing_strength, receiving_strength)
    elif position in {"WR", "TE"}:
        volume_strength = receiving_strength
    else:
        volume_strength = 0.0
    if expected_snaps is not None:
        volume_strength = max(volume_strength, _scaled_above(expected_snaps, 0.0, 55.0))

    role_label = _text(row, "pregame_role_label", "role_label").upper()
    role_uncertain = _bool(row, "pregame_role_uncertain", "role_uncertain") or role_label in {
        "COMMITTEE",
        "ROTATION",
    }
    depth_chart_conflict = _bool(
        row, "pregame_depth_chart_conflict", "depth_chart_conflict"
    )
    newly_assigned_role = _bool(
        row, "pregame_newly_assigned_role", "newly_assigned_role"
    )
    role_uncertainty = 1.0 if role_uncertain or depth_chart_conflict else 0.0
    if newly_assigned_role:
        role_uncertainty = max(role_uncertainty, 0.5)
    context_present = bool(_text(row, "pregame_context_run_id", "context_run_id"))
    role_confidence = 1.0 if context_present else 0.0
    role_confidence *= 1.0 - (0.75 * role_uncertainty)
    stable_volume = _bounded(volume_strength * max(0.0, role_confidence))

    high_game_total = _scaled_above(game_total, 44.0, 10.0) if market_available else 0.0
    high_team_total = _scaled_above(team_total, 22.0, 8.0) if market_available else 0.0
    low_team_total = _scaled_below(team_total, 20.0, 8.0) if market_available else 0.0
    favorite = _scaled_below(team_spread, -3.0, 10.0) if market_available else 0.0
    underdog = _scaled_above(team_spread, 3.0, 10.0) if market_available else 0.0
    competitive = (
        _bounded(1.0 - (abs(team_spread) / 7.0)) if market_available else 0.0
    )
    extreme_favorite = (
        _scaled_below(team_spread, -9.0, 7.0) if market_available else 0.0
    )
    pass_game_candidate = position in PASS_GAME_POSITIONS or (
        position == "RB" and receiving_strength > 0.0
    )
    receiving_candidate = position in {"WR", "TE"} or (
        position == "RB" and receiving_strength > 0.0
    )
    receiving_multiplier = 1.0 if position in {"WR", "TE"} else receiving_strength
    goal_line_strength = _scaled_above(goal_line_share, 0.0, 0.60)
    red_zone_strength = _scaled_above(red_zone_share, 0.0, 0.35)

    signals = {
        "high_game_total": high_game_total,
        "high_team_total": high_team_total,
        "low_team_total": low_team_total,
        "competitive_shootout": high_game_total * competitive,
        "favorite": favorite,
        "favorite_goal_line": favorite * goal_line_strength,
        "underdog_receiving": underdog * receiving_multiplier,
        "underdog_early_down": underdog * rushing_strength,
        "extreme_favorite": extreme_favorite,
        "red_zone_role": red_zone_strength,
        "stable_volume": stable_volume,
        "role_uncertainty": role_uncertainty,
    }
    context = {
        "player": {
            "position": position,
            "is_offense": position in OFFENSIVE_POSITIONS,
            "pass_game_candidate": pass_game_candidate,
            "receiving_candidate": receiving_candidate,
        },
        "signals": signals,
        "data": {
            "market_missing": position in OFFENSIVE_POSITIONS and not market_available,
            "opportunity_missing": position in OFFENSIVE_POSITIONS and not opportunity_available,
        },
    }
    evidence = {
        "game_total": game_total,
        "team_spread": team_spread,
        "team_implied_total": team_total,
        "point_in_time_safe": market_lineage_safe,
        "market_available": market_available,
        "opportunity_available": opportunity_available,
        "role_label": role_label or None,
        "receiving_strength": receiving_strength,
        "rushing_strength": rushing_strength,
        "goal_line_strength": goal_line_strength,
        "red_zone_strength": red_zone_strength,
        "signals": signals,
    }
    return context, evidence


def score_player_context(
    pool: pd.DataFrame,
    *,
    profile: StrategyProfile,
) -> PlayerContextScoringResult:
    """Apply Phase 3 soft preferences without changing raw projections."""

    frame = pool.copy().reset_index(drop=True)
    if frame.empty:
        return PlayerContextScoringResult(
            scored_pool=frame,
            evaluations={},
            audit_rows=[],
            summary={
                "library_id": PLAYER_CONTEXT_LIBRARY_ID,
                "library_version": PLAYER_CONTEXT_LIBRARY_VERSION,
                "profile_id": profile.profile_id,
                "profile_version": profile.version,
                "processed_count": 0,
                "scored_count": 0,
                "context_evaluable_count": 0,
                "offensive_player_count": 0,
                "market_context_count": 0,
                "opportunity_context_count": 0,
                "fully_contextualized_count": 0,
                "adjusted_count": 0,
                "gpp_context_warning": None,
                "status": "empty",
            },
        )

    engine = RuleEngine(PLAYER_CONTEXT_LIBRARY)
    evaluations: dict[str, RuleEvaluation] = {}
    audit_rows: list[dict[str, Any]] = []
    adjustments: list[float] = []
    evaluation_payloads: list[dict[str, Any]] = []
    reason_codes: list[list[str]] = []
    receiving_role_strengths: list[float] = []
    rushing_role_strengths: list[float] = []
    trigger_counts: dict[str, int] = {}
    offensive_player_count = 0
    context_evaluable_count = 0
    market_context_count = 0
    opportunity_context_count = 0
    fully_contextualized_count = 0

    for index, row in enumerate(frame.to_dict(orient="records")):
        player_id = _text(row, "player_id", "player_master_id")
        audit_key = player_id or f"unresolved-row-{index + 1}"
        context, evidence = _player_context(row)
        evaluation = engine.evaluate(context, profile, candidate_id=audit_key)
        is_offense = bool(context["player"]["is_offense"])
        market_available = bool(evidence["market_available"])
        opportunity_available = bool(evidence["opportunity_available"])
        if is_offense:
            offensive_player_count += 1
            market_context_count += int(market_available)
            opportunity_context_count += int(opportunity_available)
            fully_contextualized_count += int(
                market_available and opportunity_available
            )
            context_evaluable_count += int(
                market_available or opportunity_available
            )
        payload = evaluation.to_dict()
        codes = [trigger.reason_code for trigger in evaluation.triggered_rules]
        warnings = [
            trigger.to_dict()
            for trigger in evaluation.triggered_rules
            if trigger.rule_type is RuleType.WARNING
        ]
        for code in codes:
            trigger_counts[code] = trigger_counts.get(code, 0) + 1
        evaluations[audit_key] = evaluation
        adjustments.append(evaluation.rule_adjustment)
        evaluation_payloads.append(payload)
        reason_codes.append(codes)
        receiving_role_strengths.append(float(evidence["receiving_strength"]))
        rushing_role_strengths.append(float(evidence["rushing_strength"]))
        audit_rows.append(
            {
                "player_id": player_id,
                "player_name": _text(row, "name", "player_name", "player_display_name"),
                "position": context["player"]["position"],
                "adjustment": evaluation.rule_adjustment,
                "reason_codes": codes,
                "warnings": warnings,
                "evidence": evidence,
                "rule_evaluation": payload,
            }
        )

    frame["optimizer_context_adjustment"] = adjustments
    mean_source = (
        frame["projection"]
        if "projection" in frame
        else frame["predicted_mean"]
        if "predicted_mean" in frame
        else pd.Series(0.0, index=frame.index)
    )
    mean = pd.to_numeric(mean_source, errors="coerce").fillna(0.0)
    ceiling_source = (
        frame["p90"]
        if "p90" in frame
        else frame["predicted_p90"]
        if "predicted_p90" in frame
        else mean
    )
    ceiling = pd.to_numeric(ceiling_source, errors="coerce").fillna(mean)
    frame["optimizer_context_mean_score"] = mean + frame["optimizer_context_adjustment"]
    frame["optimizer_context_ceiling_score"] = (
        ceiling + frame["optimizer_context_adjustment"]
    )
    frame["optimizer_context_rule_codes"] = reason_codes
    frame["optimizer_context_rule_evaluation"] = evaluation_payloads
    frame["optimizer_receiving_role_strength"] = receiving_role_strengths
    frame["optimizer_rushing_role_strength"] = rushing_role_strengths

    positive = sum(adjustment > 0 for adjustment in adjustments)
    negative = sum(adjustment < 0 for adjustment in adjustments)
    warning_count = sum(bool(row["warnings"]) for row in audit_rows)
    gpp_context_warning = None
    if (
        profile.contest_style == "large_gpp"
        and offensive_player_count > 0
        and market_context_count == 0
    ):
        gpp_context_warning = {
            "reason_code": "gpp_game_context_unavailable",
            "message": (
                "GPP context scoring unavailable — cutoff-safe Vegas and "
                "game-environment adjustments were not applied."
            ),
        }
    summary = {
        "library_id": PLAYER_CONTEXT_LIBRARY_ID,
        "library_version": PLAYER_CONTEXT_LIBRARY_VERSION,
        "profile_id": profile.profile_id,
        "profile_version": profile.version,
        "processed_count": len(frame),
        "scored_count": context_evaluable_count,
        "context_evaluable_count": context_evaluable_count,
        "offensive_player_count": offensive_player_count,
        "market_context_count": market_context_count,
        "opportunity_context_count": opportunity_context_count,
        "fully_contextualized_count": fully_contextualized_count,
        "adjusted_count": positive + negative,
        "positive_adjustment_count": positive,
        "negative_adjustment_count": negative,
        "unchanged_count": len(frame) - positive - negative,
        "warning_player_count": warning_count,
        "max_absolute_adjustment": max(
            (abs(adjustment) for adjustment in adjustments), default=0.0
        ),
        "trigger_counts": dict(sorted(trigger_counts.items())),
        "gpp_context_warning": gpp_context_warning,
        "evidence_status": "initial_policy_unvalidated",
        "status": (
            "degraded"
            if gpp_context_warning is not None
            else "warn"
            if warning_count
            else "scored"
        ),
    }
    return PlayerContextScoringResult(
        scored_pool=frame,
        evaluations=evaluations,
        audit_rows=audit_rows,
        summary=summary,
    )
