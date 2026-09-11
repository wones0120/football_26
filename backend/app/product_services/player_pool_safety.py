"""Explainable, identity-safe eligibility gate for optimizer player pools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Iterable, Mapping

import pandas as pd

from .rule_library import (
    RuleCondition,
    RuleDefinition,
    RuleEngine,
    RuleEvaluation,
    RuleLibrary,
    RuleType,
    StrategyProfile,
)
from .salary_eligibility import is_salary_status_eligible, normalize_salary_status


PLAYER_POOL_SAFETY_LIBRARY_ID = "optimizer_player_pool_safety"
PLAYER_POOL_SAFETY_LIBRARY_VERSION = "v1"
DEFAULT_CONTEXT_MAX_AGE = timedelta(hours=24)


class ExclusionCategory(str, Enum):
    ELIGIBILITY = "eligibility"
    PROJECTION = "projection"
    STRATEGY = "strategy"
    USER = "user"


def _safety_rule(
    rule_id: str,
    description: str,
    rule_type: RuleType,
    field: str,
    reason_code: str,
    *,
    category: ExclusionCategory | None = None,
) -> RuleDefinition:
    metadata = {"exclusion_category": category.value} if category else {}
    return RuleDefinition(
        rule_id=rule_id,
        description=description,
        rule_type=rule_type,
        conditions=(RuleCondition(field, "truthy"),),
        reason_code=reason_code,
        metadata=metadata,
    )


PLAYER_POOL_SAFETY_LIBRARY = RuleLibrary(
    library_id=PLAYER_POOL_SAFETY_LIBRARY_ID,
    version=PLAYER_POOL_SAFETY_LIBRARY_VERSION,
    rules=(
        _safety_rule(
            "eligibility.canonical_identity_missing_v1",
            "A final lineup requires a resolved canonical player identity.",
            RuleType.HARD_EXCLUSION,
            "identity.unresolved",
            "unresolved_canonical_identity",
            category=ExclusionCategory.ELIGIBILITY,
        ),
        _safety_rule(
            "eligibility.duplicate_canonical_identity_v1",
            "A canonical player may appear only once in the optimizer pool.",
            RuleType.HARD_EXCLUSION,
            "identity.duplicate",
            "duplicate_canonical_identity",
            category=ExclusionCategory.ELIGIBILITY,
        ),
        _safety_rule(
            "eligibility.confirmed_unavailable_v1",
            "Confirmed unavailable salary or injury statuses are ineligible.",
            RuleType.HARD_EXCLUSION,
            "eligibility.confirmed_unavailable",
            "confirmed_unavailable",
            category=ExclusionCategory.ELIGIBILITY,
        ),
        _safety_rule(
            "eligibility.current_roster_inactive_v1",
            "Current active-roster evidence overrides stale historical membership.",
            RuleType.HARD_EXCLUSION,
            "eligibility.current_roster_inactive",
            "not_on_current_active_roster",
            category=ExclusionCategory.ELIGIBILITY,
        ),
        _safety_rule(
            "eligibility.slate_team_invalid_v1",
            "The current team and any supplied opponent must match the selected slate.",
            RuleType.HARD_EXCLUSION,
            "eligibility.slate_team_invalid",
            "team_not_confirmed_on_selected_slate",
            category=ExclusionCategory.ELIGIBILITY,
        ),
        _safety_rule(
            "eligibility.zero_availability_v1",
            "A player with zero cutoff-safe availability cannot enter the optimizer.",
            RuleType.HARD_EXCLUSION,
            "eligibility.zero_availability",
            "pregame_availability_zero",
            category=ExclusionCategory.ELIGIBILITY,
        ),
        _safety_rule(
            "eligibility.backup_qb_without_package_v1",
            "A confirmed backup quarterback needs an explicit package role to remain eligible.",
            RuleType.HARD_EXCLUSION,
            "eligibility.backup_qb_without_package",
            "backup_qb_without_expected_package_role",
            category=ExclusionCategory.ELIGIBILITY,
        ),
        _safety_rule(
            "eligibility.context_after_projection_cutoff_v1",
            "Pregame evidence observed after the projection cutoff is not time-safe.",
            RuleType.HARD_EXCLUSION,
            "eligibility.context_after_projection_cutoff",
            "pregame_context_after_projection_cutoff",
            category=ExclusionCategory.ELIGIBILITY,
        ),
        _safety_rule(
            "user.player_exclusion_v1",
            "The user explicitly excluded this canonical player.",
            RuleType.HARD_EXCLUSION,
            "user.excluded",
            "user_excluded",
            category=ExclusionCategory.USER,
        ),
        _safety_rule(
            "context.current_week_missing_v1",
            "Current-week role and availability evidence is missing.",
            RuleType.WARNING,
            "warnings.current_week_context_missing",
            "current_week_context_missing",
        ),
        _safety_rule(
            "context.current_week_stale_v1",
            "Current-week context is older than the configured freshness window.",
            RuleType.WARNING,
            "warnings.current_week_context_stale",
            "current_week_context_stale",
        ),
        _safety_rule(
            "context.team_missing_v1",
            "Current team data is blank.",
            RuleType.WARNING,
            "warnings.current_team_missing",
            "current_team_missing",
        ),
        _safety_rule(
            "context.opponent_missing_v1",
            "Current opponent data is blank.",
            RuleType.WARNING,
            "warnings.current_opponent_missing",
            "current_opponent_missing",
        ),
        _safety_rule(
            "context.role_uncertain_v1",
            "The current role is explicitly uncertain or shared.",
            RuleType.WARNING,
            "warnings.role_uncertain",
            "current_role_uncertain",
        ),
        _safety_rule(
            "context.new_role_v1",
            "The projection depends on a newly assigned role.",
            RuleType.WARNING,
            "warnings.newly_assigned_role",
            "newly_assigned_role",
        ),
        _safety_rule(
            "context.depth_chart_conflict_v1",
            "Current depth-chart evidence conflicts with the modeled role.",
            RuleType.WARNING,
            "warnings.depth_chart_conflict",
            "depth_chart_role_conflict",
        ),
        _safety_rule(
            "context.injury_not_incorporated_v1",
            "A current injury designation is not linked to projection context.",
            RuleType.WARNING,
            "warnings.injury_not_incorporated",
            "injury_information_not_incorporated",
        ),
    ),
)


@dataclass
class PlayerPoolSafetyResult:
    eligible_pool: pd.DataFrame
    evaluations: dict[str, RuleEvaluation]
    audit_rows: list[dict[str, Any]]
    summary: dict[str, Any]


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().upper() in {"", "<NA>", "NAN", "NONE", "NULL"}
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    try:
        return bool(missing)
    except (TypeError, ValueError):
        return False


def _text(value: Any) -> str:
    return "" if _is_missing(value) else str(value).strip()


def _first(row: Mapping[str, Any], *fields: str) -> Any:
    for field in fields:
        value = row.get(field)
        if not _is_missing(value):
            return value
    return None


def _bool(value: Any, default: bool = False) -> bool:
    if _is_missing(value):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def _number(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if pd.notna(result) else None


def _datetime(value: Any) -> datetime | None:
    if _is_missing(value):
        return None
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(timestamp):
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(UTC)
    else:
        timestamp = timestamp.tz_convert(UTC)
    return timestamp.to_pydatetime()


def _canonical_player_id(row: Mapping[str, Any]) -> str:
    return _text(_first(row, "player_master_id", "player_id"))


def _position(row: Mapping[str, Any]) -> str:
    value = _text(_first(row, "position", "primary_position")).upper()
    return "DST" if value in {"D", "DEF", "D/ST"} else value


def _team(row: Mapping[str, Any]) -> str:
    return _text(_first(row, "player_team", "team", "recent_team")).upper()


def _opponent(row: Mapping[str, Any]) -> str:
    return _text(_first(row, "opponent_team", "opponent")).upper()


def has_explicit_specialty_role(row: Mapping[str, Any]) -> bool:
    """Return whether current evidence gives a QB a real non-starter package."""
    if any(
        _bool(row.get(field))
        for field in ("has_specialty_role", "expected_package_role")
    ):
        return True
    specialty_role = _text(row.get("specialty_role")).upper()
    if specialty_role in {"WILDCAT", "GOAL_LINE", "PACKAGE", "SPECIALTY"}:
        return True
    for field in (
        "expected_package_snaps",
        "expected_snaps",
        "pregame_expected_snaps",
    ):
        value = _number(row.get(field))
        if value is not None and value > 0:
            return True
    tags = row.get("tags")
    if isinstance(tags, (set, frozenset, list, tuple)):
        normalized = {str(tag).strip().lower() for tag in tags}
        return bool(normalized & {"wildcat", "goal_line_qb", "specialty_role"})
    return False


def _identity_resolved(row: Mapping[str, Any], player_id: str) -> bool:
    if "identity_resolved" in row and not _is_missing(row.get("identity_resolved")):
        return _bool(row.get("identity_resolved")) and bool(player_id)
    if "player_master_id" in row:
        return bool(_text(row.get("player_master_id")))
    return bool(player_id)


def _role_label(row: Mapping[str, Any]) -> str:
    return _text(_first(row, "pregame_role_label", "role_label")).upper()


def _context_run_id(row: Mapping[str, Any]) -> str:
    return _text(_first(row, "pregame_context_run_id", "context_run_id"))


def _context_observed_at(row: Mapping[str, Any]) -> datetime | None:
    return _datetime(_first(row, "pregame_context_observed_at", "context_observed_at"))


def _rule_detail(
    evaluation: RuleEvaluation,
    rule_by_id: Mapping[str, RuleDefinition],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    exclusions: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for trigger in evaluation.triggered_rules:
        rule = rule_by_id[trigger.rule_id]
        detail = {
            "rule_id": trigger.rule_id,
            "reason_code": trigger.reason_code,
            "description": trigger.description,
        }
        if trigger.rule_type is RuleType.HARD_EXCLUSION:
            detail["category"] = str(
                rule.metadata.get(
                    "exclusion_category", ExclusionCategory.ELIGIBILITY.value
                )
            )
            exclusions.append(detail)
        elif trigger.rule_type is RuleType.WARNING:
            warnings.append(detail)
    return exclusions, warnings


def categorize_exclusion_reason(reason: str) -> ExclusionCategory:
    """Classify legacy and strategy reasons for the common player-pool audit."""

    normalized = str(reason).strip().lower()
    if normalized.startswith("user_") or "user excluded" in normalized:
        return ExclusionCategory.USER
    if "projection" in normalized or "no positive" in normalized:
        return ExclusionCategory.PROJECTION
    if any(
        token in normalized
        for token in (
            "strategy",
            "candidate",
            "ceiling threshold",
            "value threshold",
            "positional candidate cap",
            "team candidate cap",
        )
    ):
        return ExclusionCategory.STRATEGY
    return ExclusionCategory.ELIGIBILITY


def normalize_canonical_player_ids(values: Any, *, field_name: str) -> set[str]:
    """Normalize a request list while rejecting display-name-like blank inputs."""

    if values is None:
        return set()
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Iterable):
        raise ValueError(f"{field_name} must be a list of canonical player IDs")
    normalized = {_text(value) for value in values}
    normalized.discard("")
    return normalized


def evaluate_player_pool_safety(
    pool: pd.DataFrame,
    *,
    profile: StrategyProfile,
    expected_slate_teams: Iterable[str] | None = None,
    as_of: datetime | None = None,
    projection_cutoff: datetime | None = None,
    context_max_age: timedelta = DEFAULT_CONTEXT_MAX_AGE,
    user_excluded_player_ids: Iterable[str] = (),
) -> PlayerPoolSafetyResult:
    """Apply all Phase 2 hard gates and retain warning/explanation evidence."""

    frame = pool.copy().reset_index(drop=True)
    if frame.empty:
        return PlayerPoolSafetyResult(
            eligible_pool=frame,
            evaluations={},
            audit_rows=[],
            summary={
                "library_id": PLAYER_POOL_SAFETY_LIBRARY.library_id,
                "library_version": PLAYER_POOL_SAFETY_LIBRARY.version,
                "profile_id": profile.profile_id,
                "initial_count": 0,
                "eligible_count": 0,
                "excluded_count": 0,
                "warning_player_count": 0,
                "status": "failed",
                "reason": "empty_player_pool",
            },
        )

    evaluated_at = as_of or datetime.now(UTC)
    if evaluated_at.tzinfo is None:
        evaluated_at = evaluated_at.replace(tzinfo=UTC)
    else:
        evaluated_at = evaluated_at.astimezone(UTC)
    cutoff = projection_cutoff
    if cutoff is not None:
        cutoff = cutoff.replace(tzinfo=UTC) if cutoff.tzinfo is None else cutoff.astimezone(UTC)
    max_age_seconds = context_max_age.total_seconds()
    if max_age_seconds < 0:
        raise ValueError("context_max_age cannot be negative")

    expected_teams = {
        str(team).strip().upper()
        for team in (expected_slate_teams or ())
        if str(team).strip()
    }
    excluded_ids = {str(player_id).strip() for player_id in user_excluded_player_ids}
    rows = frame.to_dict(orient="records")
    canonical_ids = [_canonical_player_id(row) for row in rows]
    duplicate_ids = {
        player_id
        for player_id in canonical_ids
        if player_id and canonical_ids.count(player_id) > 1
    }
    roster_evidence_available = any(
        _bool(row.get("roster_evidence_available"))
        or bool(_text(row.get("roster_status")))
        for row in rows
        if _position(row) != "DST"
    )
    starting_qb_teams = {
        _team(row)
        for row in rows
        if _position(row) == "QB"
        and (
            _bool(row.get("is_starting_qb"))
            or (_number(row.get("pregame_start_probability")) or 0.0) >= 0.5
            or bool(_text(row.get("starting_qb_source")))
            or bool(_text(row.get("starting_qb_evidence_tier")))
        )
    }

    rule_by_id = {rule.rule_id: rule for rule in PLAYER_POOL_SAFETY_LIBRARY.rules}
    engine = RuleEngine(PLAYER_POOL_SAFETY_LIBRARY)
    evaluations: dict[str, RuleEvaluation] = {}
    audit_rows: list[dict[str, Any]] = []
    eligible_indexes: list[int] = []
    trigger_counts: dict[str, int] = {}

    for index, row in enumerate(rows):
        player_id = canonical_ids[index]
        audit_key = player_id or f"unresolved-row-{index + 1}"
        team = _team(row)
        opponent = _opponent(row)
        position = _position(row)
        identity_resolved = _identity_resolved(row, player_id)
        salary_status = normalize_salary_status(row.get("player_status"))
        injury_status = normalize_salary_status(
            _first(row, "pregame_injury_status", "injury_status")
        )
        confirmed_unavailable = not is_salary_status_eligible(salary_status)
        if injury_status:
            confirmed_unavailable = confirmed_unavailable or not is_salary_status_eligible(
                injury_status
            )
        availability = _number(row.get("pregame_availability_probability"))
        start_probability = _number(row.get("pregame_start_probability"))
        context_run_id = _context_run_id(row)
        context_observed_at = _context_observed_at(row)
        context_age_seconds = (
            (evaluated_at - context_observed_at).total_seconds()
            if context_observed_at is not None
            else None
        )
        context_missing = position != "DST" and not context_run_id
        context_stale = (
            context_age_seconds is not None and context_age_seconds > max_age_seconds
        )
        context_after_cutoff = bool(
            cutoff is not None
            and context_observed_at is not None
            and context_observed_at > cutoff
        )
        role_label = _role_label(row)
        is_starting_qb = _bool(row.get("is_starting_qb")) or (
            start_probability is not None and start_probability >= 0.5
        )
        backup_qb = (
            position == "QB"
            and team in starting_qb_teams
            and not is_starting_qb
            and not has_explicit_specialty_role(row)
        )
        roster_status = _text(row.get("roster_status")).upper()
        current_roster_inactive = (
            roster_evidence_available
            and position != "DST"
            and roster_status != "ACT"
        )
        team_valid = (
            bool(team)
            and (not opponent or team != opponent)
            and (not expected_teams or team in expected_teams)
            and (not expected_teams or not opponent or opponent in expected_teams)
        )
        depth_chart_conflict = _bool(
            _first(row, "pregame_depth_chart_conflict", "depth_chart_conflict")
        ) or (
            position == "QB"
            and ((is_starting_qb and role_label == "BACKUP") or (backup_qb and role_label == "STARTER"))
        )
        role_uncertain = _bool(
            _first(row, "pregame_role_uncertain", "role_uncertain")
        ) or role_label in {
            "COMMITTEE",
            "ROTATION",
        }
        newly_assigned_role = _bool(
            _first(row, "pregame_newly_assigned_role", "newly_assigned_role")
        )
        salary_injury_designation = salary_status in {
            "Q",
            "QUESTIONABLE",
            "D",
            "DOUBTFUL",
        }
        injury_not_incorporated = (
            bool(injury_status) or salary_injury_designation
        ) and not context_run_id

        context = {
            "identity": {
                "unresolved": not identity_resolved,
                "duplicate": bool(player_id and player_id in duplicate_ids),
            },
            "eligibility": {
                "confirmed_unavailable": confirmed_unavailable,
                "current_roster_inactive": current_roster_inactive,
                "slate_team_invalid": not team_valid,
                "zero_availability": availability is not None and availability <= 0.0,
                "backup_qb_without_package": backup_qb,
                "context_after_projection_cutoff": context_after_cutoff,
            },
            "user": {"excluded": bool(player_id and player_id in excluded_ids)},
            "warnings": {
                "current_week_context_missing": context_missing,
                "current_week_context_stale": context_stale,
                "current_team_missing": not bool(team),
                "current_opponent_missing": not bool(opponent),
                "role_uncertain": role_uncertain,
                "newly_assigned_role": newly_assigned_role,
                "depth_chart_conflict": depth_chart_conflict,
                "injury_not_incorporated": injury_not_incorporated,
            },
        }
        evaluation = engine.evaluate(context, profile, candidate_id=audit_key)
        evaluations[audit_key] = evaluation
        exclusions, warnings = _rule_detail(evaluation, rule_by_id)
        for trigger in evaluation.triggered_rules:
            trigger_counts[trigger.reason_code] = trigger_counts.get(trigger.reason_code, 0) + 1
        if not evaluation.excluded:
            eligible_indexes.append(index)
        audit_rows.append(
            {
                "audit_key": audit_key,
                "player_id": player_id,
                "player_name": _text(
                    _first(row, "player_display_name", "player_name", "name")
                ),
                "position": position,
                "team": team,
                "opponent_team": opponent,
                "identity_resolved": identity_resolved,
                "included": not evaluation.excluded,
                "exclusion_reasons": list(evaluation.exclusion_reasons),
                "exclusion_details": exclusions,
                "warnings": warnings,
                "context": {
                    "run_id": context_run_id or None,
                    "observed_at": (
                        context_observed_at.isoformat()
                        if context_observed_at is not None
                        else None
                    ),
                    "age_hours": (
                        round(context_age_seconds / 3600.0, 3)
                        if context_age_seconds is not None
                        else None
                    ),
                    "max_age_hours": round(max_age_seconds / 3600.0, 3),
                    "role_label": role_label or None,
                    "injury_status": injury_status or None,
                    "availability_probability": availability,
                    "start_probability": start_probability,
                    "carry_share": _number(row.get("pregame_carry_share")),
                    "target_share": _number(row.get("pregame_target_share")),
                    "expected_snaps": _number(row.get("pregame_expected_snaps")),
                    "expected_routes": _number(row.get("pregame_expected_routes")),
                    "expected_carries": _number(row.get("pregame_expected_carries")),
                    "expected_targets": _number(row.get("pregame_expected_targets")),
                    "red_zone_share": _number(row.get("pregame_red_zone_share")),
                    "goal_line_share": _number(row.get("pregame_goal_line_share")),
                },
                "rule_evaluation": evaluation.to_dict(),
            }
        )

    eligible_pool = frame.loc[eligible_indexes].copy().reset_index(drop=True)
    audit_by_key = {row["audit_key"]: row for row in audit_rows}
    if not eligible_pool.empty:
        eligible_pool["player_pool_safety_evaluation"] = [
            audit_by_key[_canonical_player_id(row)]["rule_evaluation"]
            for row in eligible_pool.to_dict(orient="records")
        ]
        eligible_pool["player_pool_safety_warnings"] = [
            audit_by_key[_canonical_player_id(row)]["warnings"]
            for row in eligible_pool.to_dict(orient="records")
        ]

    warning_player_count = sum(bool(row["warnings"]) for row in audit_rows)
    excluded_count = len(frame) - len(eligible_pool)
    status = "failed" if eligible_pool.empty else "warn" if warning_player_count else "pass"
    summary = {
        "library_id": PLAYER_POOL_SAFETY_LIBRARY.library_id,
        "library_version": PLAYER_POOL_SAFETY_LIBRARY.version,
        "profile_id": profile.profile_id,
        "profile_version": profile.version,
        "evaluated_at": evaluated_at.isoformat(),
        "projection_cutoff": cutoff.isoformat() if cutoff is not None else None,
        "context_max_age_hours": round(max_age_seconds / 3600.0, 3),
        "expected_slate_teams": sorted(expected_teams),
        "roster_evidence_available": roster_evidence_available,
        "initial_count": len(frame),
        "eligible_count": len(eligible_pool),
        "excluded_count": excluded_count,
        "warning_player_count": warning_player_count,
        "trigger_counts": dict(sorted(trigger_counts.items())),
        "status": status,
    }
    return PlayerPoolSafetyResult(
        eligible_pool=eligible_pool,
        evaluations=evaluations,
        audit_rows=audit_rows,
        summary=summary,
    )
