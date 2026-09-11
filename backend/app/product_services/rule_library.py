"""Versioned, explainable football rule evaluation and strategy profiles.

The library is deliberately independent from any one optimizer implementation.  It
turns normalized candidate context into auditable bonuses, penalties, exclusions,
and warnings.  Solver adapters can consume the resulting score and hard-exclusion
flag without embedding football policy directly in ILP construction code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Mapping


class RuleType(str, Enum):
    HARD_EXCLUSION = "hard_exclusion"
    SOFT_BOOST = "soft_boost"
    SOFT_PENALTY = "soft_penalty"
    WARNING = "warning"


class ConditionOperator(str, Enum):
    EQ = "eq"
    NE = "ne"
    IN = "in"
    NOT_IN = "not_in"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    CONTAINS = "contains"
    EXISTS = "exists"
    TRUTHY = "truthy"
    FALSY = "falsy"


CONTEST_FORMATS = frozenset({"classic", "showdown"})
CONTEST_STYLES = frozenset({"head_to_head", "large_gpp"})
OBJECTIVE_SIGNAL_NAMES = (
    "mean",
    "median",
    "floor",
    "ceiling",
    "correlation",
    "ownership",
    "leverage",
    "uniqueness",
)

CLASSIC_HEAD_TO_HEAD_PROFILE_ID = "classic_head_to_head_v1"
CLASSIC_LARGE_GPP_PROFILE_ID = "classic_large_gpp_v1"
SHOWDOWN_HEAD_TO_HEAD_PROFILE_ID = "showdown_head_to_head_v1"
SHOWDOWN_LARGE_GPP_PROFILE_ID = "showdown_large_gpp_v1"


_MISSING = object()


def _normalized_values(values: Iterable[str]) -> frozenset[str]:
    return frozenset(str(value).strip().lower() for value in values if str(value).strip())


def _frozen_mapping(values: Mapping[Any, Any]) -> Mapping[Any, Any]:
    return MappingProxyType(dict(values))


def _condition_value(value: Any) -> Any:
    if isinstance(value, (frozenset, set)):
        return sorted(value, key=str)
    if isinstance(value, tuple):
        return list(value)
    return value


@dataclass(frozen=True)
class RuleCondition:
    """One predicate over a dotted path in candidate context."""

    field: str
    operator: ConditionOperator | str
    value: Any = None

    def __post_init__(self) -> None:
        normalized_field = str(self.field).strip()
        if not normalized_field:
            raise ValueError("rule condition field must be non-empty")
        object.__setattr__(self, "field", normalized_field)
        object.__setattr__(self, "operator", ConditionOperator(self.operator))

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "operator": self.operator.value,
            "value": _condition_value(self.value),
        }


@dataclass(frozen=True)
class RuleScope:
    """Optional format, strategy-style, and exact-profile restrictions."""

    contest_formats: frozenset[str] = field(default_factory=frozenset)
    contest_styles: frozenset[str] = field(default_factory=frozenset)
    profile_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        formats = _normalized_values(self.contest_formats)
        styles = _normalized_values(self.contest_styles)
        profiles = _normalized_values(self.profile_ids)
        unknown_formats = formats - CONTEST_FORMATS
        unknown_styles = styles - CONTEST_STYLES
        if unknown_formats:
            raise ValueError(
                "unknown contest formats: " + ", ".join(sorted(unknown_formats))
            )
        if unknown_styles:
            raise ValueError(
                "unknown contest styles: " + ", ".join(sorted(unknown_styles))
            )
        object.__setattr__(self, "contest_formats", formats)
        object.__setattr__(self, "contest_styles", styles)
        object.__setattr__(self, "profile_ids", profiles)

    def applies_to(self, profile: StrategyProfile) -> bool:
        return (
            (not self.contest_formats or profile.contest_format in self.contest_formats)
            and (not self.contest_styles or profile.contest_style in self.contest_styles)
            and (not self.profile_ids or profile.profile_id in self.profile_ids)
        )

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "contest_formats": sorted(self.contest_formats),
            "contest_styles": sorted(self.contest_styles),
            "profile_ids": sorted(self.profile_ids),
        }


@dataclass(frozen=True)
class RuleDefinition:
    """A declarative rule owned by a versioned library."""

    rule_id: str
    description: str
    rule_type: RuleType | str
    conditions: tuple[RuleCondition, ...]
    reason_code: str
    weight: float = 0.0
    scope: RuleScope = field(default_factory=RuleScope)
    enabled: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        rule_id = str(self.rule_id).strip()
        description = str(self.description).strip()
        reason_code = str(self.reason_code).strip()
        if not rule_id or not description or not reason_code:
            raise ValueError("rule_id, description, and reason_code must be non-empty")
        weight = float(self.weight)
        if not math.isfinite(weight) or weight < 0:
            raise ValueError("rule weight must be a finite non-negative number")
        object.__setattr__(self, "rule_id", rule_id)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "reason_code", reason_code)
        object.__setattr__(self, "rule_type", RuleType(self.rule_type))
        conditions = tuple(
            condition
            if isinstance(condition, RuleCondition)
            else RuleCondition(**condition)
            for condition in self.conditions
        )
        object.__setattr__(self, "conditions", conditions)
        object.__setattr__(self, "weight", weight)
        object.__setattr__(self, "metadata", _frozen_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "description": self.description,
            "rule_type": self.rule_type.value,
            "conditions": [condition.to_dict() for condition in self.conditions],
            "reason_code": self.reason_code,
            "weight": self.weight,
            "scope": self.scope.to_dict(),
            "enabled": self.enabled,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RuleOverride:
    """Profile-owned change to one library rule without mutating the rule."""

    enabled: bool | None = None
    rule_type: RuleType | str | None = None
    weight: float | None = None
    weight_multiplier: float = 1.0

    def __post_init__(self) -> None:
        normalized_type = None if self.rule_type is None else RuleType(self.rule_type)
        normalized_weight = None if self.weight is None else float(self.weight)
        multiplier = float(self.weight_multiplier)
        if normalized_weight is not None and (
            not math.isfinite(normalized_weight) or normalized_weight < 0
        ):
            raise ValueError("rule override weight must be finite and non-negative")
        if not math.isfinite(multiplier) or multiplier < 0:
            raise ValueError("rule weight multiplier must be finite and non-negative")
        object.__setattr__(self, "rule_type", normalized_type)
        object.__setattr__(self, "weight", normalized_weight)
        object.__setattr__(self, "weight_multiplier", multiplier)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "rule_type": self.rule_type.value if self.rule_type is not None else None,
            "weight": self.weight,
            "weight_multiplier": self.weight_multiplier,
        }


@dataclass(frozen=True)
class StrategyProfile:
    """Versioned objective and rule weighting for one format/contest style."""

    profile_id: str
    version: str
    contest_format: str
    contest_style: str
    description: str
    objective_weights: Mapping[str, float]
    rule_type_multipliers: Mapping[str, float] = field(default_factory=dict)
    rule_overrides: Mapping[str, RuleOverride] = field(default_factory=dict)
    evidence_status: str = "initial_policy_unvalidated"

    def __post_init__(self) -> None:
        profile_id = str(self.profile_id).strip().lower()
        version = str(self.version).strip().lower()
        contest_format = str(self.contest_format).strip().lower()
        contest_style = str(self.contest_style).strip().lower()
        if not profile_id or not version or not str(self.description).strip():
            raise ValueError("profile_id, version, and description must be non-empty")
        if contest_format not in CONTEST_FORMATS:
            raise ValueError(f"unknown contest format: {contest_format}")
        if contest_style not in CONTEST_STYLES:
            raise ValueError(f"unknown contest style: {contest_style}")

        unknown_signals = set(self.objective_weights) - set(OBJECTIVE_SIGNAL_NAMES)
        if unknown_signals:
            raise ValueError(
                "unknown objective signals: " + ", ".join(sorted(unknown_signals))
            )
        objective_weights = {
            signal: float(self.objective_weights.get(signal, 0.0))
            for signal in OBJECTIVE_SIGNAL_NAMES
        }
        if any(not math.isfinite(weight) for weight in objective_weights.values()):
            raise ValueError("objective weights must be finite")

        default_multipliers = {rule_type.value: 1.0 for rule_type in RuleType}
        normalized_type_multipliers = {
            (
                rule_type.value
                if isinstance(rule_type, RuleType)
                else str(rule_type)
            ): float(multiplier)
            for rule_type, multiplier in self.rule_type_multipliers.items()
        }
        unknown_types = set(normalized_type_multipliers) - set(default_multipliers)
        if unknown_types:
            raise ValueError(
                "unknown rule type multipliers: " + ", ".join(sorted(unknown_types))
            )
        default_multipliers.update(normalized_type_multipliers)
        if any(
            not math.isfinite(multiplier) or multiplier < 0
            for multiplier in default_multipliers.values()
        ):
            raise ValueError("rule type multipliers must be finite and non-negative")
        overrides = {
            str(rule_id).strip(): (
                override if isinstance(override, RuleOverride) else RuleOverride(**override)
            )
            for rule_id, override in self.rule_overrides.items()
        }
        if any(not rule_id for rule_id in overrides):
            raise ValueError("rule override IDs must be non-empty")

        object.__setattr__(self, "profile_id", profile_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "contest_format", contest_format)
        object.__setattr__(self, "contest_style", contest_style)
        object.__setattr__(self, "description", str(self.description).strip())
        object.__setattr__(self, "objective_weights", _frozen_mapping(objective_weights))
        object.__setattr__(self, "rule_type_multipliers", _frozen_mapping(default_multipliers))
        object.__setattr__(self, "rule_overrides", _frozen_mapping(overrides))

    def score_objective(self, signals: Mapping[str, Any]) -> float:
        unknown_signals = set(signals) - set(OBJECTIVE_SIGNAL_NAMES)
        if unknown_signals:
            raise ValueError(
                "unknown objective signals: " + ", ".join(sorted(unknown_signals))
            )
        score = 0.0
        for signal, weight in self.objective_weights.items():
            raw_value = signals.get(signal, 0.0)
            value = 0.0 if raw_value is None else float(raw_value)
            if not math.isfinite(value):
                raise ValueError(f"objective signal {signal} must be finite")
            score += weight * value
        return score

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "version": self.version,
            "contest_format": self.contest_format,
            "contest_style": self.contest_style,
            "description": self.description,
            "objective_weights": dict(self.objective_weights),
            "rule_type_multipliers": dict(self.rule_type_multipliers),
            "rule_overrides": {
                rule_id: override.to_dict()
                for rule_id, override in sorted(self.rule_overrides.items())
            },
            "evidence_status": self.evidence_status,
        }


@dataclass(frozen=True)
class RuleLibrary:
    library_id: str
    version: str
    rules: tuple[RuleDefinition, ...]

    def __post_init__(self) -> None:
        library_id = str(self.library_id).strip()
        version = str(self.version).strip().lower()
        if not library_id or not version:
            raise ValueError("library_id and version must be non-empty")
        rules = tuple(self.rules)
        rule_ids = [rule.rule_id for rule in rules]
        duplicate_ids = sorted(
            rule_id for rule_id in set(rule_ids) if rule_ids.count(rule_id) > 1
        )
        if duplicate_ids:
            raise ValueError("duplicate rule IDs: " + ", ".join(duplicate_ids))
        object.__setattr__(self, "library_id", library_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "rules", rules)

    def to_dict(self) -> dict[str, Any]:
        return {
            "library_id": self.library_id,
            "version": self.version,
            "rules": [rule.to_dict() for rule in self.rules],
        }


@dataclass(frozen=True)
class RuleTrigger:
    rule_id: str
    rule_type: RuleType
    reason_code: str
    description: str
    configured_weight: float
    effective_weight: float
    score_contribution: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_type": self.rule_type.value,
            "reason_code": self.reason_code,
            "description": self.description,
            "configured_weight": self.configured_weight,
            "effective_weight": self.effective_weight,
            "score_contribution": self.score_contribution,
        }


@dataclass(frozen=True)
class RuleEvaluation:
    candidate_id: str | None
    library_id: str
    library_version: str
    profile_id: str
    profile_version: str
    objective_score: float
    rule_adjustment: float
    final_score: float
    excluded: bool
    triggered_rules: tuple[RuleTrigger, ...]

    @property
    def exclusion_reasons(self) -> tuple[str, ...]:
        return tuple(
            trigger.reason_code
            for trigger in self.triggered_rules
            if trigger.rule_type is RuleType.HARD_EXCLUSION
        )

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(
            trigger.reason_code
            for trigger in self.triggered_rules
            if trigger.rule_type is RuleType.WARNING
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "library_id": self.library_id,
            "library_version": self.library_version,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "objective_score": self.objective_score,
            "rule_adjustment": self.rule_adjustment,
            "final_score": self.final_score,
            "excluded": self.excluded,
            "exclusion_reasons": list(self.exclusion_reasons),
            "warnings": list(self.warnings),
            "triggered_rules": [trigger.to_dict() for trigger in self.triggered_rules],
        }


def _lookup(context: Mapping[str, Any], dotted_field: str) -> Any:
    value: Any = context
    for part in dotted_field.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _condition_matches(condition: RuleCondition, context: Mapping[str, Any]) -> bool:
    actual = _lookup(context, condition.field)
    operator = condition.operator
    expected = condition.value
    if operator is ConditionOperator.EXISTS:
        return actual is not _MISSING and actual is not None
    if actual is _MISSING:
        return False
    if operator is ConditionOperator.TRUTHY:
        return bool(actual)
    if operator is ConditionOperator.FALSY:
        return not bool(actual)
    if operator is ConditionOperator.EQ:
        return actual == expected
    if operator is ConditionOperator.NE:
        return actual != expected
    if operator is ConditionOperator.IN:
        try:
            return actual in expected
        except TypeError:
            return False
    if operator is ConditionOperator.NOT_IN:
        try:
            return actual not in expected
        except TypeError:
            return False
    if operator is ConditionOperator.CONTAINS:
        try:
            return expected in actual
        except TypeError:
            return False
    try:
        if operator is ConditionOperator.GT:
            return actual > expected
        if operator is ConditionOperator.GTE:
            return actual >= expected
        if operator is ConditionOperator.LT:
            return actual < expected
        if operator is ConditionOperator.LTE:
            return actual <= expected
    except TypeError:
        return False
    raise ValueError(f"unsupported condition operator: {operator}")


class RuleEngine:
    """Evaluate one immutable rule-library version against candidate context."""

    def __init__(self, library: RuleLibrary) -> None:
        self.library = library

    def evaluate(
        self,
        context: Mapping[str, Any],
        profile: StrategyProfile,
        *,
        objective_signals: Mapping[str, Any] | None = None,
        candidate_id: str | None = None,
    ) -> RuleEvaluation:
        objective_score = profile.score_objective(objective_signals or {})
        triggers: list[RuleTrigger] = []
        adjustment = 0.0
        excluded = False

        for rule in self.library.rules:
            if not rule.scope.applies_to(profile):
                continue
            override = profile.rule_overrides.get(rule.rule_id)
            enabled = (
                rule.enabled
                if override is None or override.enabled is None
                else override.enabled
            )
            if not enabled or not all(
                _condition_matches(condition, context) for condition in rule.conditions
            ):
                continue

            resolved_type = (
                rule.rule_type
                if override is None or override.rule_type is None
                else override.rule_type
            )
            configured_weight = (
                rule.weight
                if override is None or override.weight is None
                else override.weight
            )
            override_multiplier = 1.0 if override is None else override.weight_multiplier
            effective_weight = (
                configured_weight
                * override_multiplier
                * profile.rule_type_multipliers[resolved_type.value]
            )
            contribution = 0.0
            if resolved_type is RuleType.SOFT_BOOST:
                contribution = effective_weight
            elif resolved_type is RuleType.SOFT_PENALTY:
                contribution = -effective_weight
            elif resolved_type is RuleType.HARD_EXCLUSION:
                excluded = True
            adjustment += contribution
            triggers.append(
                RuleTrigger(
                    rule_id=rule.rule_id,
                    rule_type=resolved_type,
                    reason_code=rule.reason_code,
                    description=rule.description,
                    configured_weight=configured_weight,
                    effective_weight=effective_weight,
                    score_contribution=contribution,
                )
            )

        return RuleEvaluation(
            candidate_id=candidate_id,
            library_id=self.library.library_id,
            library_version=self.library.version,
            profile_id=profile.profile_id,
            profile_version=profile.version,
            objective_score=objective_score,
            rule_adjustment=adjustment,
            final_score=objective_score + adjustment,
            excluded=excluded,
            triggered_rules=tuple(triggers),
        )


_HEAD_TO_HEAD_RULE_MULTIPLIERS = {
    RuleType.SOFT_BOOST.value: 0.50,
    RuleType.SOFT_PENALTY.value: 0.65,
}


STRATEGY_PROFILES: Mapping[str, StrategyProfile] = MappingProxyType(
    {
        SHOWDOWN_HEAD_TO_HEAD_PROFILE_ID: StrategyProfile(
            profile_id=SHOWDOWN_HEAD_TO_HEAD_PROFILE_ID,
            version="v1",
            contest_format="showdown",
            contest_style="head_to_head",
            description=(
                "Mean- and stability-led Showdown scoring with ownership and "
                "uniqueness disabled."
            ),
            objective_weights={
                "mean": 0.50,
                "median": 0.25,
                "floor": 0.15,
                "ceiling": 0.05,
                "correlation": 0.05,
            },
            rule_type_multipliers=_HEAD_TO_HEAD_RULE_MULTIPLIERS,
        ),
        SHOWDOWN_LARGE_GPP_PROFILE_ID: StrategyProfile(
            profile_id=SHOWDOWN_LARGE_GPP_PROFILE_ID,
            version="v1",
            contest_format="showdown",
            contest_style="large_gpp",
            description=(
                "Ceiling- and correlation-led Showdown scoring with modest "
                "ownership, leverage, and uniqueness terms."
            ),
            objective_weights={
                "mean": 0.20,
                "ceiling": 0.40,
                "correlation": 0.25,
                "ownership": -0.05,
                "leverage": 0.10,
                "uniqueness": 0.05,
            },
        ),
        CLASSIC_HEAD_TO_HEAD_PROFILE_ID: StrategyProfile(
            profile_id=CLASSIC_HEAD_TO_HEAD_PROFILE_ID,
            version="v1",
            contest_format="classic",
            contest_style="head_to_head",
            description=(
                "Mean-dominant Classic scoring with floor and role stability ahead "
                "of correlation."
            ),
            objective_weights={
                "mean": 0.60,
                "median": 0.15,
                "floor": 0.15,
                "ceiling": 0.05,
                "correlation": 0.05,
            },
            rule_type_multipliers=_HEAD_TO_HEAD_RULE_MULTIPLIERS,
        ),
        CLASSIC_LARGE_GPP_PROFILE_ID: StrategyProfile(
            profile_id=CLASSIC_LARGE_GPP_PROFILE_ID,
            version="v1",
            contest_format="classic",
            contest_style="large_gpp",
            description=(
                "Ceiling-led Classic scoring with correlation, leverage, and "
                "portfolio uniqueness."
            ),
            objective_weights={
                "mean": 0.30,
                "ceiling": 0.40,
                "correlation": 0.15,
                "ownership": -0.05,
                "leverage": 0.10,
                "uniqueness": 0.05,
            },
        ),
    }
)


def resolve_strategy_profile(
    *,
    contest_format: str,
    objective: str,
    profile_id: str | None = None,
) -> StrategyProfile:
    """Resolve one of the four canonical profiles and reject scope mismatches."""

    normalized_format = str(contest_format).strip().lower()
    normalized_objective = str(objective).strip().lower()
    style_aliases = {
        "cash": "head_to_head",
        "h2h": "head_to_head",
        "head_to_head": "head_to_head",
        "gpp": "large_gpp",
        "large_gpp": "large_gpp",
    }
    if normalized_format not in CONTEST_FORMATS:
        raise ValueError(
            "contest_format must be one of: " + ", ".join(sorted(CONTEST_FORMATS))
        )
    if normalized_objective not in style_aliases:
        raise ValueError(
            "objective must be one of: cash, gpp, h2h, head_to_head, large_gpp"
        )
    contest_style = style_aliases[normalized_objective]
    requested_id = str(profile_id or "").strip().lower()
    if not requested_id:
        requested_id = {
            ("classic", "head_to_head"): CLASSIC_HEAD_TO_HEAD_PROFILE_ID,
            ("classic", "large_gpp"): CLASSIC_LARGE_GPP_PROFILE_ID,
            ("showdown", "head_to_head"): SHOWDOWN_HEAD_TO_HEAD_PROFILE_ID,
            ("showdown", "large_gpp"): SHOWDOWN_LARGE_GPP_PROFILE_ID,
        }[(normalized_format, contest_style)]
    profile = STRATEGY_PROFILES.get(requested_id)
    if profile is None:
        raise ValueError(
            "profile_id must be one of: " + ", ".join(sorted(STRATEGY_PROFILES))
        )
    if (
        profile.contest_format != normalized_format
        or profile.contest_style != contest_style
    ):
        raise ValueError(
            f"profile {requested_id} is not valid for "
            f"{normalized_format} {contest_style}"
        )
    return profile


def strategy_profile_catalog() -> list[dict[str, Any]]:
    """Return a stable JSON-safe catalog for APIs, run lineage, and UI clients."""

    return [
        STRATEGY_PROFILES[profile_id].to_dict()
        for profile_id in sorted(STRATEGY_PROFILES)
    ]
