"""Versioned, explainable lineup-level correlation preferences."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Mapping, Sequence

import pulp

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


LINEUP_CORRELATION_LIBRARY_ID = "optimizer_lineup_correlation"
LINEUP_CORRELATION_LIBRARY_VERSION = "v3"
PASS_CATCHER_POSITIONS = frozenset({"WR", "TE"})
OFFENSIVE_POSITIONS = frozenset({"QB", "RB", "WR", "TE", "K"})
DST_POSITIONS = frozenset({"DST", "D", "DEF"})


def _rule(
    rule_id: str,
    description: str,
    rule_type: RuleType,
    conditions: tuple[RuleCondition, ...],
    reason_code: str,
    *,
    weight: float,
    magnitude_field: str | None = None,
    contest_formats: tuple[str, ...] = (),
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
        scope=RuleScope(
            contest_formats=frozenset(contest_formats),
            contest_styles=frozenset(contest_styles),
        ),
        metadata={
            "policy_status": "initial_policy_unvalidated",
            "score_unit": "lineup_correlation_points",
        },
    )


LINEUP_CORRELATION_LIBRARY = RuleLibrary(
    library_id=LINEUP_CORRELATION_LIBRARY_ID,
    version=LINEUP_CORRELATION_LIBRARY_VERSION,
    rules=(
        _rule(
            "correlation.qb_pass_catcher_v2",
            (
                "Reward a quarterback paired with a same-team wide receiver or tight "
                "end in proportion to the cutoff-safe stack environment."
            ),
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "pair"),
                RuleCondition("pair.same_team_qb_pass_catcher", "truthy"),
                RuleCondition("signals.stack_environment", "gt", 0.0),
            ),
            "qb_same_team_pass_catcher",
            weight=0.80,
            magnitude_field="signals.stack_environment",
        ),
        _rule(
            "correlation.qb_receiving_back_v2",
            (
                "Reward a quarterback paired with a source-backed receiving running "
                "back in proportion to the cutoff-safe stack environment."
            ),
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "pair"),
                RuleCondition("pair.same_team_qb_receiving_back", "truthy"),
                RuleCondition("signals.receiving_stack_quality", "gt", 0.0),
            ),
            "qb_same_team_receiving_back",
            weight=0.35,
            magnitude_field="signals.receiving_stack_quality",
        ),
        _rule(
            "correlation.shootout_bring_back_v1",
            (
                "Reward a quarterback with an opposing pass-game bring-back in a "
                "competitive high-total game."
            ),
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "pair"),
                RuleCondition("pair.qb_opposing_receiving_option", "truthy"),
                RuleCondition("signals.competitive_shootout", "gt", 0.0),
            ),
            "competitive_shootout_bring_back",
            weight=0.45,
            magnitude_field="signals.competitive_shootout",
            contest_styles=("large_gpp",),
        ),
        _rule(
            "correlation.rb_dst_v2",
            (
                "Reward a running back paired with his own defense as favorable "
                "game script strengthens."
            ),
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "pair"),
                RuleCondition("pair.same_team_rb_dst", "truthy"),
                RuleCondition("signals.rb_dst_game_script", "gt", 0.0),
            ),
            "same_team_running_back_dst",
            weight=0.55,
            magnitude_field="signals.rb_dst_game_script",
            contest_formats=("classic",),
        ),
        _rule(
            "correlation.qb_opposing_dst_v1",
            "Strongly penalize a quarterback paired with the opposing defense.",
            RuleType.SOFT_PENALTY,
            (
                RuleCondition("evaluation.kind", "eq", "pair"),
                RuleCondition("pair.qb_opposing_dst", "truthy"),
            ),
            "quarterback_opposing_dst",
            weight=1.50,
        ),
        _rule(
            "correlation.dst_opposing_pass_catcher_v1",
            (
                "Penalize a defense paired with an opposing wide receiver or tight "
                "end without banning it."
            ),
            RuleType.SOFT_PENALTY,
            (
                RuleCondition("evaluation.kind", "eq", "pair"),
                RuleCondition("pair.dst_opposing_pass_catcher", "truthy"),
            ),
            "dst_opposing_pass_catcher",
            weight=0.40,
        ),
        _rule(
            "correlation.dst_opposing_early_down_back_v1",
            "Penalize a defense paired with an opposing rushing-dependent running back.",
            RuleType.SOFT_PENALTY,
            (
                RuleCondition("evaluation.kind", "eq", "pair"),
                RuleCondition("pair.dst_opposing_running_back", "truthy"),
            ),
            "dst_opposing_early_down_back",
            weight=0.60,
            magnitude_field="signals.early_down_role",
        ),
        _rule(
            "correlation.opposing_pass_catchers_v1",
            "Reward opposing pass catchers as a secondary mini-correlation in shootouts.",
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "pair"),
                RuleCondition("pair.opposing_pass_catchers", "truthy"),
                RuleCondition("signals.competitive_shootout", "gt", 0.0),
            ),
            "opposing_pass_catcher_mini_correlation",
            weight=0.30,
            magnitude_field="signals.competitive_shootout",
            contest_styles=("large_gpp",),
        ),
        _rule(
            "correlation.two_showdown_dsts_v1",
            "Strongly penalize two Showdown defenses, with less penalty in very low totals.",
            RuleType.SOFT_PENALTY,
            (
                RuleCondition("evaluation.kind", "eq", "pair"),
                RuleCondition("pair.two_dsts", "truthy"),
            ),
            "two_showdown_defenses",
            weight=1.20,
            magnitude_field="signals.two_dst_penalty",
            contest_formats=("showdown",),
        ),
        _rule(
            "correlation.two_showdown_kickers_v1",
            "Give two Showdown kickers a modest boost only in low-total competitive games.",
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "pair"),
                RuleCondition("pair.two_kickers", "truthy"),
                RuleCondition("signals.low_total_competitive", "gt", 0.0),
            ),
            "two_kickers_low_total_competitive",
            weight=0.25,
            magnitude_field="signals.low_total_competitive",
            contest_formats=("showdown",),
        ),
        _rule(
            "captain.high_total_offense_v1",
            "Increase offensive Captain appeal as the game total rises.",
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "captain_unary"),
                RuleCondition("captain.is_offense", "truthy"),
                RuleCondition("signals.high_game_total", "gt", 0.0),
            ),
            "high_total_offensive_captain",
            weight=0.35,
            magnitude_field="signals.high_game_total",
            contest_formats=("showdown",),
        ),
        _rule(
            "captain.qb_pass_catcher_v2",
            (
                "Give a quarterback Captain a context-weighted bonus for a same-team "
                "pass catcher."
            ),
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "captain_pair"),
                RuleCondition("captain.position", "eq", "QB"),
                RuleCondition("captain.partner_is_own_pass_catcher", "truthy"),
                RuleCondition("signals.captain_stack_environment", "gt", 0.0),
            ),
            "qb_captain_pass_catcher",
            weight=0.55,
            magnitude_field="signals.captain_stack_environment",
            contest_formats=("showdown",),
        ),
        _rule(
            "captain.pass_catcher_qb_v2",
            (
                "Give a wide receiver or tight end Captain a strong bonus for "
                "including his quarterback."
            ),
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "captain_pair"),
                RuleCondition("captain.position", "in", PASS_CATCHER_POSITIONS),
                RuleCondition("captain.partner_is_own_qb", "truthy"),
                RuleCondition("signals.captain_stack_environment", "gt", 0.0),
            ),
            "pass_catcher_captain_with_qb",
            weight=0.85,
            magnitude_field="signals.captain_stack_environment",
            contest_formats=("showdown",),
        ),
        _rule(
            "captain.receiving_back_qb_v2",
            (
                "Reward a receiving running back Captain paired with his quarterback "
                "when role and cutoff-safe stack environment both support it."
            ),
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "captain_pair"),
                RuleCondition("captain.position", "eq", "RB"),
                RuleCondition("captain.partner_is_own_qb", "truthy"),
                RuleCondition("signals.captain_receiving_stack_quality", "gt", 0.0),
            ),
            "receiving_back_captain_with_qb",
            weight=0.30,
            magnitude_field="signals.captain_receiving_stack_quality",
            contest_formats=("showdown",),
        ),
        _rule(
            "captain.dst_own_running_back_v2",
            (
                "Reward a defense Captain paired with its own running back only when "
                "cutoff-safe game script supports the construction."
            ),
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "captain_pair"),
                RuleCondition("captain.is_dst", "truthy"),
                RuleCondition("captain.partner_is_own_rb", "truthy"),
                RuleCondition("signals.captain_dst_game_script", "gt", 0.0),
            ),
            "dst_captain_own_running_back",
            weight=0.60,
            magnitude_field="signals.captain_dst_game_script",
            contest_formats=("showdown",),
        ),
        _rule(
            "captain.dst_own_kicker_v2",
            (
                "Reward a defense Captain paired with its own kicker only when "
                "cutoff-safe game script supports the construction."
            ),
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "captain_pair"),
                RuleCondition("captain.is_dst", "truthy"),
                RuleCondition("captain.partner_is_own_kicker", "truthy"),
                RuleCondition("signals.captain_dst_game_script", "gt", 0.0),
            ),
            "dst_captain_own_kicker",
            weight=0.40,
            magnitude_field="signals.captain_dst_game_script",
            contest_formats=("showdown",),
        ),
        _rule(
            "captain.dst_opposing_qb_v1",
            (
                "Apply an additional penalty when a defense Captain is paired with "
                "the opposing quarterback."
            ),
            RuleType.SOFT_PENALTY,
            (
                RuleCondition("evaluation.kind", "eq", "captain_pair"),
                RuleCondition("captain.is_dst", "truthy"),
                RuleCondition("captain.partner_is_opposing_qb", "truthy"),
            ),
            "dst_captain_opposing_quarterback",
            weight=0.75,
            contest_formats=("showdown",),
        ),
        _rule(
            "captain.kicker_low_total_v1",
            "Reserve a kicker Captain preference for lower-total games.",
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "captain_unary"),
                RuleCondition("captain.position", "eq", "K"),
                RuleCondition("signals.low_game_total", "gt", 0.0),
            ),
            "kicker_captain_low_total",
            weight=0.25,
            magnitude_field="signals.low_game_total",
            contest_formats=("showdown",),
        ),
        _rule(
            "construction.classic_naked_pocket_qb_v1",
            (
                "Penalize a GPP quarterback without a same-team pass catcher in "
                "proportion to his dependence on passing production."
            ),
            RuleType.SOFT_PENALTY,
            (
                RuleCondition("evaluation.kind", "eq", "classic_naked_qb"),
                RuleCondition("signals.pocket_dependency", "gt", 0.0),
            ),
            "naked_pocket_quarterback",
            weight=1.10,
            magnitude_field="signals.pocket_dependency",
            contest_formats=("classic",),
            contest_styles=("large_gpp",),
        ),
        _rule(
            "construction.classic_qb_double_stack_v2",
            (
                "Reward a GPP quarterback with at least two same-team pass catchers "
                "in proportion to the cutoff-safe stack environment."
            ),
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "classic_qb_double_stack"),
                RuleCondition("signals.stack_environment", "gt", 0.0),
            ),
            "quarterback_double_stack",
            weight=0.65,
            magnitude_field="signals.stack_environment",
            contest_formats=("classic",),
            contest_styles=("large_gpp",),
        ),
        _rule(
            "construction.classic_skill_cluster_without_qb_v1",
            (
                "Penalize three or more same-team skill players when the lineup "
                "does not include that team's quarterback."
            ),
            RuleType.SOFT_PENALTY,
            (
                RuleCondition(
                    "evaluation.kind", "eq", "classic_skill_cluster_without_qb"
                ),
            ),
            "same_team_skill_cluster_without_quarterback",
            weight=0.75,
            contest_formats=("classic",),
        ),
        _rule(
            "construction.classic_competitive_game_stack_v1",
            (
                "Reward four-player offensive game stacks when a cutoff-safe total "
                "and spread support a competitive shootout."
            ),
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "classic_game_stack"),
                RuleCondition("signals.competitive_shootout", "gt", 0.0),
            ),
            "competitive_full_game_stack",
            weight=0.55,
            magnitude_field="signals.competitive_shootout",
            contest_formats=("classic",),
            contest_styles=("large_gpp",),
        ),
        _rule(
            "construction.classic_contradictory_favorite_rb_script_v1",
            (
                "Penalize a lineup that combines a favorite early-down back, the "
                "opposing defense, and multiple pass catchers from that underdog."
            ),
            RuleType.SOFT_PENALTY,
            (
                RuleCondition(
                    "evaluation.kind", "eq", "classic_contradictory_script"
                ),
                RuleCondition("signals.favorite_early_down", "gt", 0.0),
            ),
            "contradictory_favorite_rb_underdog_stack",
            weight=0.90,
            magnitude_field="signals.favorite_early_down",
            contest_formats=("classic",),
        ),
        _rule(
            "construction.showdown_qb_captain_double_stack_v2",
            (
                "Reward a quarterback Captain with at least two same-team wide "
                "receivers or tight ends."
            ),
            RuleType.SOFT_BOOST,
            (
                RuleCondition(
                    "evaluation.kind", "eq", "showdown_qb_captain_double_stack"
                ),
                RuleCondition("signals.stack_environment", "gt", 0.0),
            ),
            "quarterback_captain_double_stack",
            weight=0.90,
            magnitude_field="signals.stack_environment",
            contest_formats=("showdown",),
        ),
        _rule(
            "construction.showdown_pass_catcher_captain_without_qb_v1",
            (
                "Penalize a wide receiver or tight end Captain without his "
                "quarterback instead of banning the construction."
            ),
            RuleType.SOFT_PENALTY,
            (
                RuleCondition(
                    "evaluation.kind",
                    "eq",
                    "showdown_pass_catcher_captain_without_qb",
                ),
            ),
            "pass_catcher_captain_without_quarterback",
            weight=0.80,
            contest_formats=("showdown",),
        ),
        _rule(
            "construction.showdown_favorite_five_one_v1",
            "Reward a 5-1 build led by a meaningful favorite in large-field GPPs.",
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "showdown_five_one"),
                RuleCondition("signals.favorite_script", "gt", 0.0),
            ),
            "favorite_five_one_construction",
            weight=0.60,
            magnitude_field="signals.favorite_script",
            contest_formats=("showdown",),
            contest_styles=("large_gpp",),
        ),
        _rule(
            "construction.showdown_underdog_five_one_v1",
            (
                "Penalize a 5-1 build led by a meaningful underdog without making "
                "the upset construction impossible."
            ),
            RuleType.SOFT_PENALTY,
            (
                RuleCondition("evaluation.kind", "eq", "showdown_five_one"),
                RuleCondition("signals.underdog_script", "gt", 0.0),
            ),
            "underdog_five_one_construction",
            weight=1.10,
            magnitude_field="signals.underdog_script",
            contest_formats=("showdown",),
        ),
        _rule(
            "construction.showdown_competitive_three_three_v1",
            "Reward a balanced 3-3 Showdown build as the spread becomes competitive.",
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "showdown_three_three"),
                RuleCondition("signals.competitive_game", "gt", 0.0),
            ),
            "competitive_three_three_construction",
            weight=0.35,
            magnitude_field="signals.competitive_game",
            contest_formats=("showdown",),
        ),
        _rule(
            "construction.showdown_competitive_four_two_v1",
            "Give a modest boost to 4-2 Showdown builds in competitive games.",
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "showdown_four_two"),
                RuleCondition("signals.competitive_game", "gt", 0.0),
            ),
            "competitive_four_two_construction",
            weight=0.20,
            magnitude_field="signals.competitive_game",
            contest_formats=("showdown",),
        ),
        _rule(
            "construction.showdown_favorite_rb_captain_v1",
            (
                "Reward a favorite running back Captain when current rushing role "
                "evidence supports a run-closing script."
            ),
            RuleType.SOFT_BOOST,
            (
                RuleCondition("evaluation.kind", "eq", "showdown_rb_captain"),
                RuleCondition("signals.favorite_rb_role", "gt", 0.0),
            ),
            "favorite_running_back_captain",
            weight=0.65,
            magnitude_field="signals.favorite_rb_role",
            contest_formats=("showdown",),
        ),
        _rule(
            "construction.showdown_fragile_punt_h2h_v1",
            (
                "Penalize a sub-$1,000 Showdown skill player without an identifiable "
                "current snaps, routes, carries, or targets path."
            ),
            RuleType.SOFT_PENALTY,
            (
                RuleCondition("evaluation.kind", "eq", "showdown_fragile_punt"),
            ),
            "fragile_showdown_punt_without_role",
            weight=0.90,
            contest_formats=("showdown",),
            contest_styles=("head_to_head",),
        ),
        _rule(
            "construction.showdown_fragile_punt_gpp_v1",
            (
                "Apply a modest GPP penalty to a sub-$1,000 Showdown skill player "
                "without an identifiable current opportunity path."
            ),
            RuleType.SOFT_PENALTY,
            (
                RuleCondition("evaluation.kind", "eq", "showdown_fragile_punt"),
            ),
            "fragile_showdown_punt_without_role",
            weight=0.35,
            contest_formats=("showdown",),
            contest_styles=("large_gpp",),
        ),
    ),
)


@dataclass(frozen=True)
class LineupCorrelationTerm:
    left_index: int
    right_index: int
    kind: str
    adjustment: float
    evaluation: RuleEvaluation
    evidence: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class LineupConstructionTerm:
    kind: str
    adjustment: float
    evaluation: RuleEvaluation
    required_indexes: tuple[int, ...] = ()
    captain_indexes: tuple[int, ...] = ()
    count_conditions: tuple[tuple[tuple[int, ...], int, int | None], ...] = ()
    absent_indexes: tuple[int, ...] = ()
    evidence_indexes: tuple[int, ...] = ()
    evidence: Mapping[str, Any] | None = None


def _value(player: Any, field: str, default: Any = None) -> Any:
    if isinstance(player, Mapping):
        return player.get(field, default)
    return getattr(player, field, default)


def _text(player: Any, *fields: str) -> str:
    for field in fields:
        value = _value(player, field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _number(player: Any, *fields: str) -> float | None:
    for field in fields:
        value = _value(player, field)
        if value is None or str(value).strip() == "":
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            return number
    return None


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


def _position(player: Any) -> str:
    return _text(player, "position", "roster_position").upper()


def _team(player: Any) -> str:
    return _text(player, "player_team", "team").upper()


def _opponent(player: Any) -> str:
    return _text(player, "opponent_team", "opponent").upper()


def _player_id(player: Any) -> str:
    return _text(player, "player_id", "player_master_id")


def _market_is_safe(player: Any) -> bool:
    value = _value(player, "market_context_point_in_time_safe")
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def _receiving_strength(player: Any) -> float:
    explicit = _number(player, "optimizer_receiving_role_strength")
    if explicit is not None:
        return _bounded(explicit)
    return max(
        _scaled_above(_number(player, "pregame_target_share"), 0.0, 0.28),
        _scaled_above(_number(player, "pregame_expected_targets"), 0.0, 8.0),
        _scaled_above(_number(player, "pregame_expected_routes"), 0.0, 32.0),
    )


def _rushing_strength(player: Any) -> float:
    explicit = _number(player, "optimizer_rushing_role_strength")
    if explicit is not None:
        return _bounded(explicit)
    return max(
        _scaled_above(_number(player, "pregame_carry_share"), 0.0, 0.65),
        _scaled_above(_number(player, "pregame_expected_carries"), 0.0, 18.0),
    )


def _truthy(player: Any, *fields: str) -> bool:
    for field in fields:
        value = _value(player, field)
        if value is None:
            continue
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}
    return False


def _has_identifiable_opportunity(player: Any) -> bool:
    opportunity_fields = (
        "pregame_expected_snaps",
        "pregame_expected_routes",
        "pregame_expected_carries",
        "pregame_expected_targets",
        "pregame_target_share",
        "pregame_carry_share",
        "pregame_red_zone_share",
        "pregame_goal_line_share",
    )
    if any((_number(player, field) or 0.0) > 0.0 for field in opportunity_fields):
        return True
    if _truthy(player, "has_specialty_role", "expected_package_role"):
        return True
    specialty_role = _text(player, "specialty_role").upper()
    if specialty_role in {"WILDCAT", "GOAL_LINE", "PACKAGE", "SPECIALTY"}:
        return True
    role = _text(player, "pregame_role_label", "role_label").upper()
    return role not in {"", "UNKNOWN", "BACKUP", "ROTATION", "GENERIC"}


def _game_key(player: Any) -> str:
    game_id = _text(player, "game_id")
    if game_id:
        return game_id
    teams = sorted(team for team in {_team(player), _opponent(player)} if team)
    return "|".join(teams)


def _safe_game_environment(players: Sequence[Any]) -> tuple[float | None, float | None]:
    for player in players:
        if not _market_is_safe(player):
            continue
        game_total = _number(player, "game_total_line", "game_total")
        spread = _number(player, "team_spread_line", "spread")
        if game_total is not None and game_total > 0 and spread is not None:
            return game_total, spread
    return None, None


def _safe_team_spread(players: Sequence[Any], team: str) -> float | None:
    for player in players:
        if _team(player) != team or not _market_is_safe(player):
            continue
        spread = _number(player, "team_spread_line", "spread")
        if spread is not None:
            return spread
    return None


def _stack_environment(player: Any) -> tuple[float, dict[str, Any]]:
    """Return a zero-to-one stack score from cutoff-safe market context only."""

    game_total = _number(player, "game_total_line", "game_total")
    team_total = _number(
        player,
        "team_implied_total",
        "team_total_line",
        "team_total",
    )
    spread = _number(player, "team_spread_line", "spread")
    available = bool(
        _market_is_safe(player)
        and game_total is not None
        and game_total > 0
        and team_total is not None
        and team_total >= 0
        and spread is not None
    )
    if not available:
        return 0.0, {
            "available": False,
            "point_in_time_safe": _market_is_safe(player),
            "game_total": game_total,
            "team_implied_total": team_total,
            "team_spread": spread,
            "stack_environment": 0.0,
        }

    opponent_total = max(0.0, float(game_total) - float(team_total))
    total_quality = _scaled_above(game_total, 36.0, 20.0)
    team_quality = _scaled_above(team_total, 18.0, 14.0)
    competitive = _bounded(1.0 - (abs(float(spread)) / 14.0))
    opponent_push = _scaled_above(opponent_total, 16.0, 14.0)
    blowout_risk = _scaled_above(abs(float(spread)), 7.0, 7.0)
    base_score = (
        (0.35 * total_quality)
        + (0.35 * team_quality)
        + (0.20 * competitive)
        + (0.10 * opponent_push)
    )
    score = _bounded(base_score * (1.0 - (0.35 * blowout_risk)))
    return score, {
        "available": True,
        "point_in_time_safe": True,
        "game_total": game_total,
        "team_implied_total": team_total,
        "opponent_implied_total": opponent_total,
        "team_spread": spread,
        "total_quality": total_quality,
        "team_quality": team_quality,
        "competitive_game": competitive,
        "opponent_push": opponent_push,
        "blowout_risk": blowout_risk,
        "stack_environment": score,
    }


def _dst_game_script(player: Any) -> tuple[float, dict[str, Any]]:
    """Score defense-led correlation only from safe favorite/low-total evidence."""

    game_total = _number(player, "game_total_line", "game_total")
    spread = _number(player, "team_spread_line", "spread")
    available = bool(
        _market_is_safe(player)
        and game_total is not None
        and game_total > 0
        and spread is not None
    )
    if not available:
        return 0.0, {
            "available": False,
            "point_in_time_safe": _market_is_safe(player),
            "game_total": game_total,
            "team_spread": spread,
            "dst_game_script": 0.0,
        }
    favorite = _scaled_below(spread, -3.0, 10.0)
    low_total = _scaled_below(game_total, 48.0, 16.0)
    score = favorite * (0.50 + (0.50 * low_total))
    return score, {
        "available": True,
        "point_in_time_safe": True,
        "game_total": game_total,
        "team_spread": spread,
        "favorite_strength": favorite,
        "low_total_strength": low_total,
        "dst_game_script": score,
    }


def _construction_term(
    engine: RuleEngine,
    profile: StrategyProfile,
    *,
    kind: str,
    candidate_id: str,
    signals: Mapping[str, float] | None = None,
    required_indexes: Sequence[int] = (),
    captain_indexes: Sequence[int] = (),
    count_conditions: Sequence[tuple[Sequence[int], int, int | None]] = (),
    absent_indexes: Sequence[int] = (),
    evidence_indexes: Sequence[int] = (),
    evidence: Mapping[str, Any] | None = None,
) -> LineupConstructionTerm | None:
    evaluation = engine.evaluate(
        {
            "evaluation": {"kind": kind},
            "signals": dict(signals or {}),
        },
        profile,
        candidate_id=candidate_id,
    )
    if not evaluation.rule_adjustment:
        return None
    return LineupConstructionTerm(
        kind=kind,
        adjustment=evaluation.rule_adjustment,
        evaluation=evaluation,
        required_indexes=tuple(required_indexes),
        captain_indexes=tuple(captain_indexes),
        count_conditions=tuple(
            (tuple(indexes), int(minimum), maximum)
            for indexes, minimum, maximum in count_conditions
        ),
        absent_indexes=tuple(absent_indexes),
        evidence_indexes=tuple(evidence_indexes),
        evidence=dict(evidence or {}),
    )


def build_format_specific_terms(
    players: Sequence[Any],
    *,
    profile: StrategyProfile,
) -> list[LineupConstructionTerm]:
    """Build Phase 5 soft terms whose activation depends on lineup structure."""

    engine = RuleEngine(LINEUP_CORRELATION_LIBRARY)
    terms: list[LineupConstructionTerm] = []
    team_indexes: dict[str, list[int]] = {}
    game_indexes: dict[str, list[int]] = {}
    for index, player in enumerate(players):
        team = _team(player)
        if team:
            team_indexes.setdefault(team, []).append(index)
        game_key = _game_key(player)
        if game_key:
            game_indexes.setdefault(game_key, []).append(index)

    def append(term: LineupConstructionTerm | None) -> None:
        if term is not None:
            terms.append(term)

    if profile.contest_format == "classic":
        for qb_index, quarterback in enumerate(players):
            if _position(quarterback) != "QB":
                continue
            team = _team(quarterback)
            pass_catcher_indexes = [
                index
                for index, player in enumerate(players)
                if index != qb_index
                and _team(player) == team
                and _position(player) in PASS_CATCHER_POSITIONS
            ]
            pocket_dependency = 1.0 - _rushing_strength(quarterback)
            append(
                _construction_term(
                    engine,
                    profile,
                    kind="classic_naked_qb",
                    candidate_id=f"classic_naked_qb:{_player_id(quarterback)}",
                    signals={"pocket_dependency": pocket_dependency},
                    required_indexes=(qb_index,),
                    absent_indexes=pass_catcher_indexes,
                    evidence_indexes=(qb_index,),
                    evidence={
                        "quarterback_team": team,
                        "rushing_role_strength": _rushing_strength(quarterback),
                    },
                )
            )
            stack_environment, stack_evidence = _stack_environment(quarterback)
            append(
                _construction_term(
                    engine,
                    profile,
                    kind="classic_qb_double_stack",
                    candidate_id=(
                        f"classic_qb_double_stack:{_player_id(quarterback)}"
                    ),
                    signals={"stack_environment": stack_environment},
                    required_indexes=(qb_index,),
                    count_conditions=((pass_catcher_indexes, 2, None),),
                    evidence_indexes=(qb_index, *pass_catcher_indexes),
                    evidence={
                        "quarterback_team": team,
                        "stack_environment": stack_evidence,
                    },
                )
            )

        for team, indexes in sorted(team_indexes.items()):
            skill_indexes = [
                index
                for index in indexes
                if _position(players[index]) in {"RB", "WR", "TE"}
            ]
            quarterback_indexes = [
                index for index in indexes if _position(players[index]) == "QB"
            ]
            append(
                _construction_term(
                    engine,
                    profile,
                    kind="classic_skill_cluster_without_qb",
                    candidate_id=f"classic_skill_cluster_without_qb:{team}",
                    count_conditions=((skill_indexes, 3, None),),
                    absent_indexes=quarterback_indexes,
                    evidence_indexes=skill_indexes,
                    evidence={"team": team},
                )
            )

        for rb_index, running_back in enumerate(players):
            if _position(running_back) != "RB":
                continue
            opponent = _opponent(running_back)
            if not opponent:
                continue
            spread = (
                _number(running_back, "team_spread_line", "spread")
                if _market_is_safe(running_back)
                else None
            )
            favorite = _scaled_below(spread, -3.0, 10.0)
            early_down = _rushing_strength(running_back) * (
                1.0 - 0.50 * _receiving_strength(running_back)
            )
            opponent_dst_indexes = [
                index
                for index, player in enumerate(players)
                if _team(player) == opponent
                and _position(player) in DST_POSITIONS
            ]
            opponent_pass_catchers = [
                index
                for index, player in enumerate(players)
                if _team(player) == opponent
                and _position(player) in PASS_CATCHER_POSITIONS
            ]
            for dst_index in opponent_dst_indexes:
                append(
                    _construction_term(
                        engine,
                        profile,
                        kind="classic_contradictory_script",
                        candidate_id=(
                            "classic_contradictory_script:"
                            f"{_player_id(running_back)}|"
                            f"{_player_id(players[dst_index])}"
                        ),
                        signals={
                            "favorite_early_down": favorite * early_down
                        },
                        required_indexes=(rb_index, dst_index),
                        count_conditions=(
                            (opponent_pass_catchers, 2, None),
                        ),
                        evidence_indexes=(
                            rb_index,
                            dst_index,
                            *opponent_pass_catchers,
                        ),
                        evidence={
                            "favorite_team": _team(running_back),
                            "underdog_team": opponent,
                            "favorite_team_spread": spread,
                        },
                    )
                )

        for game_key, indexes in sorted(game_indexes.items()):
            offense_indexes = [
                index
                for index in indexes
                if _position(players[index]) in {"QB", "RB", "WR", "TE"}
            ]
            teams = sorted({_team(players[index]) for index in indexes if _team(players[index])})
            if len(teams) != 2:
                continue
            team_conditions = tuple(
                (
                    tuple(
                        index
                        for index in offense_indexes
                        if _team(players[index]) == team
                    ),
                    1,
                    None,
                )
                for team in teams
            )
            game_players = [players[index] for index in indexes]
            game_total, spread = _safe_game_environment(game_players)
            competitive = (
                _bounded(1.0 - abs(spread) / 7.0) if spread is not None else 0.0
            )
            competitive_shootout = _scaled_above(
                game_total, 44.0, 10.0
            ) * competitive
            append(
                _construction_term(
                    engine,
                    profile,
                    kind="classic_game_stack",
                    candidate_id=f"classic_game_stack:{game_key}",
                    signals={"competitive_shootout": competitive_shootout},
                    count_conditions=(
                        (offense_indexes, 4, None),
                        *team_conditions,
                    ),
                    evidence_indexes=offense_indexes,
                    evidence={
                        "game_id": game_key,
                        "game_total": game_total,
                        "spread": spread,
                    },
                )
            )
        return terms

    for captain_index, captain in enumerate(players):
        position = _position(captain)
        team = _team(captain)
        if position == "QB":
            stack_environment, stack_evidence = _stack_environment(captain)
            pass_catcher_indexes = [
                index
                for index, player in enumerate(players)
                if index != captain_index
                and _team(player) == team
                and _position(player) in PASS_CATCHER_POSITIONS
            ]
            append(
                _construction_term(
                    engine,
                    profile,
                    kind="showdown_qb_captain_double_stack",
                    candidate_id=(
                        "showdown_qb_captain_double_stack:"
                        f"{_player_id(captain)}"
                    ),
                    signals={"stack_environment": stack_environment},
                    captain_indexes=(captain_index,),
                    count_conditions=((pass_catcher_indexes, 2, None),),
                    evidence_indexes=(captain_index, *pass_catcher_indexes),
                    evidence={
                        "captain_team": team,
                        "stack_environment": stack_evidence,
                    },
                )
            )
        elif position in PASS_CATCHER_POSITIONS:
            own_qb_indexes = [
                index
                for index, player in enumerate(players)
                if _team(player) == team and _position(player) == "QB"
            ]
            append(
                _construction_term(
                    engine,
                    profile,
                    kind="showdown_pass_catcher_captain_without_qb",
                    candidate_id=(
                        "showdown_pass_catcher_captain_without_qb:"
                        f"{_player_id(captain)}"
                    ),
                    captain_indexes=(captain_index,),
                    absent_indexes=own_qb_indexes,
                    evidence_indexes=(captain_index,),
                    evidence={"captain_team": team},
                )
            )
        elif position == "RB":
            spread = _safe_team_spread(players, team)
            favorite = _scaled_below(spread, -3.0, 10.0)
            favorite_rb_role = favorite * _rushing_strength(captain)
            append(
                _construction_term(
                    engine,
                    profile,
                    kind="showdown_rb_captain",
                    candidate_id=f"showdown_rb_captain:{_player_id(captain)}",
                    signals={"favorite_rb_role": favorite_rb_role},
                    captain_indexes=(captain_index,),
                    evidence_indexes=(captain_index,),
                    evidence={
                        "captain_team": team,
                        "team_spread": spread,
                        "rushing_role_strength": _rushing_strength(captain),
                    },
                )
            )

        salary = _number(captain, "base_salary", "salary")
        if (
            position in {"RB", "WR", "TE"}
            and salary is not None
            and salary <= 1000.0
            and not _has_identifiable_opportunity(captain)
        ):
            append(
                _construction_term(
                    engine,
                    profile,
                    kind="showdown_fragile_punt",
                    candidate_id=f"showdown_fragile_punt:{_player_id(captain)}",
                    required_indexes=(captain_index,),
                    evidence_indexes=(captain_index,),
                    evidence={"salary": salary, "identifiable_opportunity": False},
                )
            )

    teams = sorted(team_indexes)
    if len(teams) == 2:
        game_total, game_spread = _safe_game_environment(players)
        competitive = (
            _bounded(1.0 - abs(game_spread) / 7.0)
            if game_spread is not None
            else 0.0
        )
        first_team_indexes = team_indexes[teams[0]]
        append(
            _construction_term(
                engine,
                profile,
                kind="showdown_three_three",
                candidate_id=f"showdown_three_three:{'|'.join(teams)}",
                signals={"competitive_game": competitive},
                count_conditions=((first_team_indexes, 3, 3),),
                evidence_indexes=tuple(range(len(players))),
                evidence={
                    "teams": teams,
                    "game_total": game_total,
                    "spread": game_spread,
                },
            )
        )
        for team in teams:
            indexes = team_indexes[team]
            team_spread = _safe_team_spread(players, team)
            append(
                _construction_term(
                    engine,
                    profile,
                    kind="showdown_four_two",
                    candidate_id=f"showdown_four_two:{team}",
                    signals={"competitive_game": competitive},
                    count_conditions=((indexes, 4, 4),),
                    evidence_indexes=indexes,
                    evidence={"dominant_team": team, "team_spread": team_spread},
                )
            )
            append(
                _construction_term(
                    engine,
                    profile,
                    kind="showdown_five_one",
                    candidate_id=f"showdown_five_one:{team}",
                    signals={
                        "favorite_script": _scaled_below(
                            team_spread, -3.0, 10.0
                        ),
                        "underdog_script": _scaled_above(
                            team_spread, 3.0, 10.0
                        ),
                    },
                    count_conditions=((indexes, 5, 5),),
                    evidence_indexes=indexes,
                    evidence={"dominant_team": team, "team_spread": team_spread},
                )
            )
    return terms


def _pair_context(
    left: Any,
    right: Any,
    *,
    kind: str,
    captain: Any | None = None,
) -> dict[str, Any]:
    left_position = _position(left)
    right_position = _position(right)
    left_team = _team(left)
    right_team = _team(right)
    left_opponent = _opponent(left)
    right_opponent = _opponent(right)
    same_team = bool(left_team and left_team == right_team)
    opponents = bool(
        left_team
        and right_team
        and (left_opponent == right_team or right_opponent == left_team)
    )

    qb = left if left_position == "QB" else right if right_position == "QB" else None
    partner = right if qb is left else left if qb is right else None
    dst = (
        left
        if left_position in DST_POSITIONS
        else right
        if right_position in DST_POSITIONS
        else None
    )
    dst_partner = right if dst is left else left if dst is right else None
    rb = left if left_position == "RB" else right if right_position == "RB" else None
    rb_receiving = _receiving_strength(rb) if rb is not None else 0.0
    rb_rushing = _rushing_strength(rb) if rb is not None else 0.0
    stack_environment, stack_evidence = (
        _stack_environment(qb) if qb is not None else (0.0, {"available": False})
    )
    rb_dst_game_script, rb_dst_evidence = (
        _dst_game_script(rb) if rb is not None else (0.0, {"available": False})
    )

    safe_market_players = [player for player in (left, right) if _market_is_safe(player)]
    game_total = next(
        (
            value
            for player in safe_market_players
            if (value := _number(player, "game_total_line", "game_total")) is not None
            and value > 0
        ),
        None,
    )
    spread = None
    for player in safe_market_players:
        value = _number(player, "team_spread_line", "spread")
        if value is not None:
            spread = value
            break
    high_total = _scaled_above(game_total, 44.0, 10.0)
    low_total = _scaled_below(game_total, 44.0, 12.0)
    competitive = _bounded(1.0 - (abs(spread) / 7.0)) if spread is not None else 0.0
    captain_position = _position(captain) if captain is not None else ""
    captain_team = _team(captain) if captain is not None else ""
    captain_partner = right if captain is left else left if captain is right else None
    captain_partner_position = _position(captain_partner) if captain_partner is not None else ""
    captain_receiving = _receiving_strength(captain) if captain is not None else 0.0
    captain_stack_environment, captain_stack_evidence = (
        _stack_environment(captain)
        if captain is not None
        else (0.0, {"available": False})
    )
    captain_dst_game_script, captain_dst_evidence = (
        _dst_game_script(captain)
        if captain is not None
        else (0.0, {"available": False})
    )

    return {
        "evaluation": {"kind": kind},
        "pair": {
            "same_team_qb_pass_catcher": bool(
                same_team
                and qb is not None
                and _position(partner) in PASS_CATCHER_POSITIONS
            ),
            "same_team_qb_receiving_back": bool(
                same_team and qb is not None and _position(partner) == "RB"
            ),
            "qb_opposing_receiving_option": bool(
                opponents
                and qb is not None
                and (
                    _position(partner) in PASS_CATCHER_POSITIONS
                    or (_position(partner) == "RB" and _receiving_strength(partner) > 0)
                )
            ),
            "same_team_rb_dst": bool(same_team and rb is not None and dst is not None),
            "qb_opposing_dst": bool(opponents and qb is not None and dst is not None),
            "dst_opposing_pass_catcher": bool(
                opponents
                and dst is not None
                and _position(dst_partner) in PASS_CATCHER_POSITIONS
            ),
            "dst_opposing_running_back": bool(
                opponents and dst is not None and _position(dst_partner) == "RB"
            ),
            "opposing_pass_catchers": bool(
                opponents
                and left_position in PASS_CATCHER_POSITIONS
                and right_position in PASS_CATCHER_POSITIONS
            ),
            "two_dsts": left_position in DST_POSITIONS and right_position in DST_POSITIONS,
            "two_kickers": left_position == "K" and right_position == "K",
        },
        "captain": {
            "position": captain_position,
            "is_offense": captain_position in OFFENSIVE_POSITIONS,
            "is_dst": captain_position in DST_POSITIONS,
            "partner_is_own_pass_catcher": bool(
                captain_position == "QB"
                and captain_team
                and captain_team == _team(captain_partner)
                and captain_partner_position in PASS_CATCHER_POSITIONS
            ),
            "partner_is_own_qb": bool(
                captain_position in PASS_CATCHER_POSITIONS | {"RB"}
                and captain_team
                and captain_team == _team(captain_partner)
                and captain_partner_position == "QB"
            ),
            "partner_is_own_rb": bool(
                captain_position in DST_POSITIONS
                and captain_team
                and captain_team == _team(captain_partner)
                and captain_partner_position == "RB"
            ),
            "partner_is_own_kicker": bool(
                captain_position in DST_POSITIONS
                and captain_team
                and captain_team == _team(captain_partner)
                and captain_partner_position == "K"
            ),
            "partner_is_opposing_qb": bool(
                captain_position in DST_POSITIONS
                and captain_partner_position == "QB"
                and _opponent(captain) == _team(captain_partner)
            ),
        },
        "signals": {
            "receiving_role": rb_receiving,
            "stack_environment": stack_environment,
            "receiving_stack_quality": rb_receiving * stack_environment,
            "early_down_role": max(0.25, rb_rushing * (1.0 - 0.5 * rb_receiving)),
            "rb_dst_game_script": rb_dst_game_script,
            "high_game_total": high_total,
            "low_game_total": low_total,
            "competitive_shootout": high_total * competitive,
            "low_total_competitive": low_total * competitive,
            "two_dst_penalty": 1.0 - (0.75 * low_total),
            "captain_receiving_role": captain_receiving,
            "captain_stack_environment": captain_stack_environment,
            "captain_receiving_stack_quality": (
                captain_receiving * captain_stack_environment
            ),
            "captain_dst_game_script": captain_dst_game_script,
        },
        "evidence": {
            "stack_environment": stack_evidence,
            "rb_dst_game_script": rb_dst_evidence,
            "captain_stack_environment": captain_stack_evidence,
            "captain_dst_game_script": captain_dst_evidence,
        },
    }


def build_lineup_correlation_terms(
    players: Sequence[Any],
    *,
    profile: StrategyProfile,
) -> list[LineupCorrelationTerm]:
    """Evaluate every relevant pair without adding solver constraints."""

    engine = RuleEngine(LINEUP_CORRELATION_LIBRARY)
    terms: list[LineupCorrelationTerm] = []
    if profile.contest_format == "showdown":
        for captain_index, captain in enumerate(players):
            context = _pair_context(
                captain,
                {},
                kind="captain_unary",
                captain=captain,
            )
            evaluation = engine.evaluate(
                context,
                profile,
                candidate_id=f"captain:{_player_id(captain)}",
            )
            if evaluation.rule_adjustment:
                terms.append(
                    LineupCorrelationTerm(
                        left_index=captain_index,
                        right_index=captain_index,
                        kind="captain_unary",
                        adjustment=evaluation.rule_adjustment,
                        evaluation=evaluation,
                        evidence=context.get("evidence"),
                    )
                )
    for left_index, right_index in combinations(range(len(players)), 2):
        left = players[left_index]
        right = players[right_index]
        pair_id = f"{_player_id(left)}|{_player_id(right)}"
        pair_context = _pair_context(left, right, kind="pair")
        pair_evaluation = engine.evaluate(
            pair_context,
            profile,
            candidate_id=f"pair:{pair_id}",
        )
        if pair_evaluation.rule_adjustment:
            terms.append(
                LineupCorrelationTerm(
                    left_index=left_index,
                    right_index=right_index,
                    kind="pair",
                    adjustment=pair_evaluation.rule_adjustment,
                    evaluation=pair_evaluation,
                    evidence=pair_context.get("evidence"),
                )
            )
        if profile.contest_format != "showdown":
            continue
        for captain_index, kind in (
            (left_index, "captain_left"),
            (right_index, "captain_right"),
        ):
            captain = players[captain_index]
            context = _pair_context(
                left, right, kind="captain_pair", captain=captain
            )
            evaluation = engine.evaluate(
                context,
                profile,
                candidate_id=f"{kind}:{pair_id}",
            )
            if evaluation.rule_adjustment:
                terms.append(
                    LineupCorrelationTerm(
                        left_index=left_index,
                        right_index=right_index,
                        kind=kind,
                        adjustment=evaluation.rule_adjustment,
                        evaluation=evaluation,
                        evidence=context.get("evidence"),
                    )
                )
    return terms


def add_lineup_correlation_objective(
    model: pulp.LpProblem,
    terms: Sequence[LineupCorrelationTerm],
    *,
    selected_vars: Mapping[int, Any],
    captain_vars: Mapping[int, Any] | None = None,
    prefix: str = "correlation",
) -> pulp.LpAffineExpression:
    """Linearize pair selections and return their complete soft adjustment."""

    objective_terms: list[pulp.LpAffineExpression] = []
    for sequence, term in enumerate(terms):
        if term.kind == "captain_unary":
            if captain_vars is not None:
                objective_terms.append(
                    term.adjustment * captain_vars[term.left_index]
                )
            continue
        left_var = selected_vars[term.left_index]
        right_var = selected_vars[term.right_index]
        if term.kind == "captain_left":
            if captain_vars is None:
                continue
            left_var = captain_vars[term.left_index]
        elif term.kind == "captain_right":
            if captain_vars is None:
                continue
            right_var = captain_vars[term.right_index]
        pair_var = pulp.LpVariable(
            f"{prefix}_{sequence}", lowBound=0, upBound=1, cat="Binary"
        )
        model += pair_var <= left_var
        model += pair_var <= right_var
        model += pair_var >= left_var + right_var - 1
        objective_terms.append(term.adjustment * pair_var)
    return pulp.lpSum(objective_terms)


def _threshold_flag(
    model: pulp.LpProblem,
    expression: pulp.LpAffineExpression,
    *,
    item_count: int,
    minimum: int,
    maximum: int | None,
    prefix: str,
) -> list[Any] | None:
    conditions: list[Any] = []
    if minimum > item_count or (maximum is not None and maximum < minimum):
        return None
    if minimum > 0:
        minimum_flag = pulp.LpVariable(
            f"{prefix}_minimum", lowBound=0, upBound=1, cat="Binary"
        )
        model += expression >= minimum * minimum_flag
        model += expression <= (minimum - 1) + item_count * minimum_flag
        conditions.append(minimum_flag)
    if maximum is not None and maximum < item_count:
        maximum_flag = pulp.LpVariable(
            f"{prefix}_maximum", lowBound=0, upBound=1, cat="Binary"
        )
        model += expression <= maximum + item_count * (1 - maximum_flag)
        model += expression >= (maximum + 1) * (1 - maximum_flag)
        conditions.append(maximum_flag)
    return conditions


def add_format_specific_objective(
    model: pulp.LpProblem,
    terms: Sequence[LineupConstructionTerm],
    *,
    selected_vars: Mapping[int, Any],
    captain_vars: Mapping[int, Any] | None = None,
    prefix: str = "format_rule",
) -> pulp.LpAffineExpression:
    """Linearize higher-order Phase 5 construction terms exactly."""

    objective_terms: list[pulp.LpAffineExpression] = []
    for sequence, term in enumerate(terms):
        term_prefix = f"{prefix}_{sequence}"
        conditions: list[Any] = [
            selected_vars[index] for index in term.required_indexes
        ]
        if term.captain_indexes:
            if captain_vars is None:
                continue
            conditions.extend(captain_vars[index] for index in term.captain_indexes)

        impossible = False
        for count_sequence, (indexes, minimum, maximum) in enumerate(
            term.count_conditions
        ):
            expression = pulp.lpSum(selected_vars[index] for index in indexes)
            threshold_conditions = _threshold_flag(
                model,
                expression,
                item_count=len(indexes),
                minimum=minimum,
                maximum=maximum,
                prefix=f"{term_prefix}_count_{count_sequence}",
            )
            if threshold_conditions is None:
                impossible = True
                break
            conditions.extend(threshold_conditions)
        if impossible:
            continue

        if term.absent_indexes:
            absent_expression = pulp.lpSum(
                selected_vars[index] for index in term.absent_indexes
            )
            absence_flag = pulp.LpVariable(
                f"{term_prefix}_absence", lowBound=0, upBound=1, cat="Binary"
            )
            model += absent_expression <= len(term.absent_indexes) * (
                1 - absence_flag
            )
            model += absent_expression >= 1 - absence_flag
            conditions.append(absence_flag)

        if not conditions:
            objective_terms.append(term.adjustment)
            continue
        active_var = pulp.LpVariable(
            f"{term_prefix}_active", lowBound=0, upBound=1, cat="Binary"
        )
        for condition in conditions:
            model += active_var <= condition
        model += active_var >= pulp.lpSum(conditions) - (len(conditions) - 1)
        objective_terms.append(term.adjustment * active_var)
    return pulp.lpSum(objective_terms)


def active_format_specific_terms(
    terms: Sequence[LineupConstructionTerm],
    *,
    selected_indexes: set[int],
    captain_indexes: set[int],
) -> list[LineupConstructionTerm]:
    """Return the exact Phase 5 terms active for a completed lineup."""

    active: list[LineupConstructionTerm] = []
    for term in terms:
        if not set(term.required_indexes) <= selected_indexes:
            continue
        if not set(term.captain_indexes) <= captain_indexes:
            continue
        if set(term.absent_indexes) & selected_indexes:
            continue
        if any(
            sum(index in selected_indexes for index in indexes) < minimum
            or (
                maximum is not None
                and sum(index in selected_indexes for index in indexes) > maximum
            )
            for indexes, minimum, maximum in term.count_conditions
        ):
            continue
        active.append(term)
    return active


def _is_captain(player: Any) -> bool:
    roster_position = _text(player, "roster_position").upper()
    raw = _value(player, "is_captain", False)
    return roster_position == "CPT" or bool(raw)


def _construction_label(lineup: Sequence[Any], profile: StrategyProfile) -> str:
    if profile.contest_format == "showdown":
        counts: dict[str, int] = {}
        for player in lineup:
            team = _team(player)
            if team:
                counts[team] = counts.get(team, 0) + 1
        ordered_counts = sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )
        split = "-".join(str(count) for _team_id, count in ordered_counts)
        captain = next((player for player in lineup if _is_captain(player)), None)
        captain_label = _text(captain, "name", "player_name", "player_id") if captain else "Unknown"
        return f"{split} · {captain_label} Captain" if split else f"{captain_label} Captain"

    quarterback = next((player for player in lineup if _position(player) == "QB"), None)
    if quarterback is None:
        return "No quarterback stack"
    same_team = sum(
        _team(player) == _team(quarterback)
        and _position(player) in PASS_CATCHER_POSITIONS | {"RB"}
        for player in lineup
        if player is not quarterback
    )
    bring_backs = sum(
        _team(player) == _opponent(quarterback)
        and _position(player) in {"RB", "WR", "TE"}
        for player in lineup
    )
    return f"QB + {same_team} · {bring_backs} bring-back"


def _showdown_game_script(lineup: Sequence[Any]) -> dict[str, Any] | None:
    captain = next((player for player in lineup if _is_captain(player)), None)
    if captain is None:
        return None
    teams: dict[str, int] = {}
    for player in lineup:
        team = _team(player)
        if team:
            teams[team] = teams.get(team, 0) + 1
    game_total = (
        _number(captain, "game_total_line", "game_total")
        if _market_is_safe(captain)
        else None
    )
    spread = (
        _number(captain, "team_spread_line", "spread")
        if _market_is_safe(captain)
        else None
    )
    captain_position = _position(captain)
    dominant_team = max(teams, key=teams.get) if teams else ""
    dominant_count = teams.get(dominant_team, 0)

    script_id = "balanced_game"
    label = "Balanced game"
    if dominant_count >= 5:
        dominant_player = next(
            (player for player in lineup if _team(player) == dominant_team),
            None,
        )
        dominant_spread = (
            _number(dominant_player, "team_spread_line", "spread")
            if dominant_player is not None and _market_is_safe(dominant_player)
            else None
        )
        if dominant_spread is None:
            script_id = "one_sided_build"
            label = "One-sided 5-1 build"
        elif dominant_spread > 0:
            script_id = "underdog_upset"
            label = "Underdog upset"
        elif dominant_spread < 0:
            script_id = "favorite_dominates"
            label = "Favorite dominates"
        else:
            script_id = "one_sided_build"
            label = "One-sided 5-1 build"
    elif captain_position == "RB" and spread is not None and spread < -3:
        script_id = "favorite_leads_rb_closes"
        label = "Favorite leads early / RB closes"
    elif captain_position == "QB" and spread is not None and spread > 3:
        script_id = "underdog_trails_qb_volume"
        label = "Underdog trails / QB throws heavily"
    elif game_total is not None and game_total >= 50 and (spread is None or abs(spread) <= 7):
        script_id = "high_scoring_shootout"
        label = "High-scoring shootout"
    elif game_total is not None and game_total <= 40:
        script_id = "low_scoring_defensive_game"
        label = "Low-scoring defensive game"
    return {
        "script_id": script_id,
        "label": label,
        "evidence": {
            "captain_team": _team(captain),
            "captain_position": captain_position,
            "captain_team_spread": spread,
            "game_total": game_total,
            "team_counts": dict(sorted(teams.items())),
        },
    }


def score_lineup_correlations(
    lineup: Sequence[Any],
    *,
    profile: StrategyProfile,
    objective_multiplier: float = 1.0,
) -> dict[str, Any]:
    """Explain the soft terms that affected one completed lineup."""

    terms = build_lineup_correlation_terms(lineup, profile=profile)
    selected_indexes = set(range(len(lineup)))
    captain_indexes = {
        index for index, player in enumerate(lineup) if _is_captain(player)
    }
    selected_terms = [
        term
        for term in terms
        if term.kind == "pair"
        or (term.kind == "captain_unary" and term.left_index in captain_indexes)
        or (term.kind == "captain_left" and term.left_index in captain_indexes)
        or (term.kind == "captain_right" and term.right_index in captain_indexes)
    ]
    selected_format_terms = active_format_specific_terms(
        build_format_specific_terms(lineup, profile=profile),
        selected_indexes=selected_indexes,
        captain_indexes=captain_indexes,
    )
    resolved_multiplier = float(objective_multiplier)
    if not math.isfinite(resolved_multiplier) or resolved_multiplier < 0:
        raise ValueError("objective_multiplier must be a finite non-negative number")
    trigger_rows: list[dict[str, Any]] = []
    for term in selected_terms:
        left = lineup[term.left_index]
        right = lineup[term.right_index]
        for trigger in term.evaluation.triggered_rules:
            players = [
                {
                    "player_id": _player_id(left),
                    "player_name": _text(left, "name", "player_name", "player_id"),
                    "team": _team(left),
                    "position": _position(left),
                }
            ]
            if term.kind != "captain_unary":
                players.append(
                    {
                        "player_id": _player_id(right),
                        "player_name": _text(right, "name", "player_name", "player_id"),
                        "team": _team(right),
                        "position": _position(right),
                    }
                )
            trigger_rows.append(
                {
                    **trigger.to_dict(),
                    "term_kind": term.kind,
                    "objective_contribution": (
                        trigger.score_contribution * resolved_multiplier
                    ),
                    "players": players,
                    "evidence": dict(term.evidence or {}),
                }
            )
    for term in selected_format_terms:
        players = [
            {
                "player_id": _player_id(lineup[index]),
                "player_name": _text(
                    lineup[index], "name", "player_name", "player_id"
                ),
                "team": _team(lineup[index]),
                "position": _position(lineup[index]),
            }
            for index in dict.fromkeys(term.evidence_indexes)
        ]
        for trigger in term.evaluation.triggered_rules:
            trigger_rows.append(
                {
                    **trigger.to_dict(),
                    "term_kind": "format_specific",
                    "construction_kind": term.kind,
                    "objective_contribution": (
                        trigger.score_contribution * resolved_multiplier
                    ),
                    "players": players,
                    "evidence": dict(term.evidence or {}),
                }
            )
    total_rule_adjustment = sum(
        term.adjustment for term in selected_terms
    ) + sum(term.adjustment for term in selected_format_terms)
    total_adjustment = total_rule_adjustment * resolved_multiplier
    positive_codes = sorted(
        {
            row["reason_code"]
            for row in trigger_rows
            if row["score_contribution"] > 0
        }
    )
    negative_codes = sorted(
        {
            row["reason_code"]
            for row in trigger_rows
            if row["score_contribution"] < 0
        }
    )
    return {
        "library_id": LINEUP_CORRELATION_LIBRARY_ID,
        "library_version": LINEUP_CORRELATION_LIBRARY_VERSION,
        "profile_id": profile.profile_id,
        "profile_version": profile.version,
        "total_rule_adjustment": total_rule_adjustment,
        "objective_multiplier": resolved_multiplier,
        "total_adjustment": total_adjustment,
        "positive_reason_codes": positive_codes,
        "negative_reason_codes": negative_codes,
        "triggered_rules": trigger_rows,
        "format_specific_rule_count": sum(
            len(term.evaluation.triggered_rules)
            for term in selected_format_terms
        ),
        "construction_label": _construction_label(lineup, profile),
        "implied_game_script": (
            _showdown_game_script(lineup)
            if profile.contest_format == "showdown"
            else None
        ),
        "evidence_status": "initial_policy_unvalidated",
    }
