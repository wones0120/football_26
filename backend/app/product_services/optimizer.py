"""Lineup optimizer using PuLP ILP."""

from __future__ import annotations

from ..injury_scope import injury_slate_sql
from .classic_favored_preferences import favored_positions, is_favored

import uuid
import math
import json
import hashlib
import itertools
from copy import deepcopy
from functools import cached_property
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional
import logging
import os
import re
from threading import RLock
from time import monotonic

import pandas as pd
import numpy as np
import pulp
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import ProgrammingError, ResourceClosedError, SQLAlchemyError

from Database.config import get_connection_string
from Database.dst import canonical_team_sql, normalize_team
from Database.operations import ensure_table_columns
from ..config import get_settings
from .gpp_optimizer import run_gpp_pipeline, Player as GPPPlayer, GPPOptimizerResult, tag_players
from .optimizer_control import solve_control, build_comparison
from .point_in_time import injury_snapshot_cutoff_sql
from .player_pool_safety import (
    ExclusionCategory,
    categorize_exclusion_reason,
    evaluate_player_pool_safety,
    has_explicit_specialty_role,
    normalize_canonical_player_ids,
    validate_player_pool_evidence_consistency,
)
from .player_context_scoring import score_player_context
from .lineup_correlation_scoring import (
    LINEUP_CORRELATION_LIBRARY_ID,
    LINEUP_CORRELATION_LIBRARY_VERSION,
    add_format_specific_objective,
    add_lineup_correlation_objective,
    build_format_specific_terms,
    build_lineup_correlation_terms,
    score_lineup_correlations,
)
from .rule_library import CLASSIC_LARGE_GPP_PROFILE_ID, StrategyProfile, resolve_strategy_profile
from .salary_eligibility import INELIGIBLE_SALARY_STATUSES_SQL
from .simulations import SimulationService
from .showdown_portfolio_selection import (
    candidate_metrics, captain_family_summaries, select_showdown_portfolio, signature as showdown_signature,
)
from .showdown_game_scenarios import (
    DEFAULT_DECISIVE_MARGIN, condition_player_pool, define_game_scenarios,
)
from .showdown_captain_optimality import (
    add_shadow_qb_family_ranks, current_qb_analysis, load_current_qb_prior_features,
)
from .target_schema import validate_target_schema
from .optimizer_effectiveness import candidate_snapshot
from .workload_evidence import FEATURE_FIELDS, build_workload_evidence, workload_evidence_reference
from .showdown_qb_preferences import (
    validate_showdown_qb_preferences, showdown_qb_preference_report,
)
from .showdown_team_constraints import showdown_team_limit, team_constraint_report
from .single_lineup import (
    CAPTAIN_SINGLE_LINEUP_STRATEGY_ID, CLASSIC_SINGLE_LINEUP_STRATEGY_ID,
    SINGLE_LINEUP_STRATEGIES, normalize_single_lineup_params, number,
    generate_candidates as generate_single_lineup_candidates, select_single_lineup,
)
from .showdown_captain_shortlist import build_captain_shortlist, POLICY_ID as CAPTAIN_SHORTLIST_POLICY_ID
from .showdown_captain_preferences import (
    allowed_captain_positions, validate_showdown_captain_preferences,
    captain_preference_report, captain_preference_exclusions, named_preference_ids,
)


VALID_CONTEST_FORMATS = {"classic", "showdown"}
VALID_OPTIMIZER_OBJECTIVES = {"cash", "gpp"}
CASH_OBJECTIVE_ID = "classic_cash_v1"
CLASSIC_CASH_STACK_UNCONSTRAINED_ID = "classic_cash_unconstrained_v1"
CLASSIC_CASH_STACK_QB_PAIR_ID = "classic_cash_qb_pair_v1"
CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID = "classic_cash_qb_pair_bringback_v1"
CLASSIC_GPP_STACK_LEGACY_ID = "classic_gpp_double_bringback_v1"
CLASSIC_GPP_BASELINE_STRATEGY_ID = "classic_gpp_baseline_v1"
CLASSIC_GPP_ADVANCED_STRATEGY_ID = "classic_gpp_slate_aware_v1"
CLASSIC_HEAD_TO_HEAD_STRATEGY_ID = "classic_head_to_head_v1"
CLASSIC_LARGE_GPP_STRATEGY_ID = "classic_large_gpp_v1"
CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID = "classic_small_field_gpp"
SHOWDOWN_CASH_BASELINE_STRATEGY_ID = "showdown_cash_baseline_v1"
SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID = (
    "showdown_cash_qb_captain_stack_v1"
)
SHOWDOWN_GPP_BASELINE_STRATEGY_ID = "showdown_gpp_baseline_v1"
SHOWDOWN_GPP_CAPTAIN_INFORMED_V1_STRATEGY_ID = (
    "showdown_gpp_captain_informed_v1"
)
SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID = (
    "showdown_gpp_portfolio_v3"
)
SHOWDOWN_GPP_CAPTAIN_INFORMED_V2_STRATEGY_ID = "showdown_gpp_captain_informed_v2"
SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID = "showdown_single_entry_gpp"
SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID = "showdown_single_entry_portfolio"
SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID = "showdown_3max_gpp"
SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID = "showdown_small_max_gpp"
SHOWDOWN_SINGLE_ENTRY_STRATEGY_IDS = frozenset({
    SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID,
    SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID,
})
SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID = (
    "showdown_qb_captain_same_team_wr_te_v1"
)
SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_IDS = frozenset(
    {
        SHOWDOWN_GPP_CAPTAIN_INFORMED_V1_STRATEGY_ID,
        SHOWDOWN_GPP_CAPTAIN_INFORMED_V2_STRATEGY_ID,
        SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID,
        *SHOWDOWN_SINGLE_ENTRY_STRATEGY_IDS,
        SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID,
        SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID,
    }
)
USER_OPPONENT_PREFERENCE_RULE_ID = "user.preference.opponent_exclusion_v1"


@dataclass(frozen=True)
class CashObjectiveConfig:
    objective_id: str = CASH_OBJECTIVE_ID
    mean_weight: float = 0.25
    median_weight: float = 0.35
    floor_weight: float = 0.40
    role_certainty_bonus: float = 1.25
    fragility_penalty: float = 3.0
    full_role_sample_size: int = 250


DEFAULT_CASH_OBJECTIVE = CashObjectiveConfig()


@dataclass(frozen=True)
class HeadToHeadObjectiveConfig:
    objective_id: str = CLASSIC_HEAD_TO_HEAD_STRATEGY_ID
    mean_weight: float = 0.75
    ceiling_weight: float = 0.20
    floor_weight: float = 0.05
    fragile_punt_salary: int = 3500
    fragile_punt_mean: float = 5.0
    fragile_punt_penalty: float = 0.5
    correlation_bonus: float = 0.05


DEFAULT_HEAD_TO_HEAD_OBJECTIVE = HeadToHeadObjectiveConfig()


@dataclass(frozen=True)
class OptimizerStrategyConfig:
    strategy_id: str
    version: str
    contest_format: str
    objective: str
    engine: str
    evidence_status: str
    description: str


OPTIMIZER_STRATEGIES = {
    **{strategy_id: OptimizerStrategyConfig(
        strategy_id=strategy_id, version="v1", contest_format=contest_format,
        objective="cash", engine="cash_oriented_single_lineup_selector",
        evidence_status="transparent_proxy_unvalidated",
        description="One primary cash-oriented recommendation, plus any additional requested lineups under user limits, from broad legal candidates using correlated downside, bounded upside, availability and supported competition diagnostics.",
    ) for strategy_id, contest_format in SINGLE_LINEUP_STRATEGIES.items()},
    CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID,
        version="v1",
        contest_format="classic",
        objective="gpp",
        engine="small_field_candidate_selector",
        evidence_status="diagnostic_baseline",
        description=(
            "Classic small-field GPP: broad legal candidate pool, existing Classic "
            "GPP scoring, global lineup selection, and construction diagnostics."
        ),
    ),
    CLASSIC_HEAD_TO_HEAD_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=CLASSIC_HEAD_TO_HEAD_STRATEGY_ID,
        version="v1",
        contest_format="classic",
        objective="cash",
        engine="head_to_head_ilp",
        evidence_status="explicit_contest_strategy",
        description=(
            "Head-to-Head: broad eligible pool with a mean-dominant objective, "
            "secondary ceiling/floor value, and no required game stack."
        ),
    ),
    CLASSIC_LARGE_GPP_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=CLASSIC_LARGE_GPP_STRATEGY_ID,
        version="v1",
        contest_format="classic",
        objective="gpp",
        engine="large_gpp_portfolio",
        evidence_status="explicit_contest_strategy",
        description=(
            "Large GPP: ceiling-weighted portfolio optimization with flexible "
            "QB stacks, optional bring-backs, uniqueness, and exposure controls."
        ),
    ),
    CLASSIC_GPP_BASELINE_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=CLASSIC_GPP_BASELINE_STRATEGY_ID,
        version="v1",
        contest_format="classic",
        objective="gpp",
        engine="legacy_ilp",
        evidence_status="production_baseline",
        description="Current classic GPP P90/leverage ILP with the legacy double-stack policy.",
    ),
    CLASSIC_GPP_ADVANCED_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=CLASSIC_GPP_ADVANCED_STRATEGY_ID,
        version="v1",
        contest_format="classic",
        objective="gpp",
        engine="slate_aware_gpp",
        evidence_status="explicit_candidate",
        description=(
            "Slate-aware classic GPP portfolio optimizer with ownership templates, "
            "correlation bonuses, leverage, uniqueness, and exposure controls."
        ),
    ),
    SHOWDOWN_CASH_BASELINE_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=SHOWDOWN_CASH_BASELINE_STRATEGY_ID,
        version="v1",
        contest_format="showdown",
        objective="cash",
        engine="captain_ilp",
        evidence_status="initial_policy_unvalidated",
        description=(
            "Persistent Showdown cash contract using the basic one-captain, "
            "five-flex mean/stability solver using the Showdown cash profile."
        ),
    ),
    SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID,
        version="v1",
        contest_format="showdown",
        objective="cash",
        engine="captain_ilp",
        evidence_status="user_required",
        description=(
            "Showdown cash mean/stability solver requiring a same-team WR or TE in FLEX "
            "whenever the captain is a quarterback."
        ),
    ),
    SHOWDOWN_GPP_BASELINE_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=SHOWDOWN_GPP_BASELINE_STRATEGY_ID,
        version="v1",
        contest_format="showdown",
        objective="gpp",
        engine="captain_ilp",
        evidence_status="basic_p90_baseline",
        description=(
            "Persistent Showdown GPP contract using the basic one-captain, "
            "five-flex P90 solver pending DT-605 objective research."
        ),
    ),
    SHOWDOWN_GPP_CAPTAIN_INFORMED_V1_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=SHOWDOWN_GPP_CAPTAIN_INFORMED_V1_STRATEGY_ID,
        version="v1",
        contest_format="showdown",
        objective="gpp",
        engine="captain_informed_ilp",
        evidence_status="production_validated",
        description=(
            "Showdown GPP P90 solver with starter-QB eligibility and the validated "
            "captain-position prior (0.35 strength; 39-slate paired evaluation)."
        ),
    ),
    SHOWDOWN_GPP_CAPTAIN_INFORMED_V2_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=SHOWDOWN_GPP_CAPTAIN_INFORMED_V2_STRATEGY_ID,
        version="v2",
        contest_format="showdown",
        objective="gpp",
        engine="captain_informed_ilp",
        evidence_status="production_validated_plus_user_rule",
        description=(
            "Showdown GPP P90 solver with starter-QB eligibility, the validated "
            "captain-position prior, and a same-team WR/TE requirement for QB captains."
        ),
    ),
    SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID,
        version="v3",
        contest_format="showdown",
        objective="gpp",
        engine="captain_informed_ilp",
        evidence_status="user_required_portfolio_policy",
        description=(
            "Five-entry Showdown GPP portfolio solver with role-specific exposure, "
            "hard quarterback correlations, opportunity eligibility, quality floors, "
            "role-specific ownership, and intentional game-script diversity."
        ),
    ),
    **{
        strategy_id: OptimizerStrategyConfig(
            strategy_id=strategy_id,
            version="v1",
            contest_format="showdown",
            objective="gpp",
            engine="single_entry_candidate_selector",
            evidence_status="heuristic_unvalidated",
            description="Showdown single-entry GPP candidate selection without cross-contest exposure limits.",
        )
        for strategy_id in SHOWDOWN_SINGLE_ENTRY_STRATEGY_IDS
    },
    SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID,
        version="v1", contest_format="showdown", objective="gpp",
        engine="global_small_max_candidate_selector",
        evidence_status="heuristic_unvalidated",
        description="Showdown small-max GPP lineup selection with optional contest-backed entry-count heuristic.",
    ),
    SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID: OptimizerStrategyConfig(
        strategy_id=SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID,
        version="v1", contest_format="showdown", objective="gpp",
        engine="global_three_max_candidate_selector",
        evidence_status="heuristic_unvalidated",
        description="One-contest Showdown 3-max GPP global lineup portfolio and entry-count heuristic.",
    ),
}


def showdown_optimizer_rules(strategy: str) -> list[dict]:
    """Return hard Showdown construction rules owned by one strategy version."""
    if strategy not in {
        CAPTAIN_SINGLE_LINEUP_STRATEGY_ID,
        SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID,
        SHOWDOWN_GPP_CAPTAIN_INFORMED_V2_STRATEGY_ID,
        SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID,
        *SHOWDOWN_SINGLE_ENTRY_STRATEGY_IDS,
        SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID,
        SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID,
    }:
        return []
    rules = [] if strategy in ({CAPTAIN_SINGLE_LINEUP_STRATEGY_ID, SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID, SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID, SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID} | SHOWDOWN_SINGLE_ENTRY_STRATEGY_IDS) else [
        {
            "rule_id": SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID,
            "rule_type": "hard_constraint",
            "trigger": {"captain_position": "QB"},
            "requirement": {
                "minimum": 1,
                "roster_position": "FLEX",
                "same_team": True,
                "positions": ["WR", "TE"],
            },
            "source": "user_required",
        }
    ]
    if strategy in {CAPTAIN_SINGLE_LINEUP_STRATEGY_ID, SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID, SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID, SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID} or strategy in SHOWDOWN_SINGLE_ENTRY_STRATEGY_IDS:
        rules.extend(
            [
                {"rule_id": "showdown_require_starting_qb_v2", "rule_type": "hard_constraint", "trigger": {"portfolio_size_max": 5, "captain_position_not": "RB"}, "requirement": {"minimum_starting_qbs": 1}, "source": "user_required"},
                {"rule_id": "showdown_pass_catcher_captain_qb_v1", "rule_type": "hard_constraint", "trigger": {"captain_positions": ["WR", "TE"]}, "requirement": {"same_team_starting_qb": True}, "source": "user_required"},
                {"rule_id": "showdown_multi_pass_catcher_qb_v2", "rule_type": "hard_constraint", "trigger": {"same_team_wr_te_minimum": 2, "captain_position_not": "RB"}, "requirement": {"same_team_starting_qb": True}, "source": "user_required"},
                {"rule_id": "showdown_qb_captain_role_stack_v1", "rule_type": "hard_constraint", "trigger": {"captain_position": "QB"}, "requirement": {"pocket_qb_wr_te": 2, "high_rushing_qb_wr_te": 1}, "source": "user_required"},
                {"rule_id": "showdown_low_opportunity_skill_gate_v2", "rule_type": "hard_exclusion", "trigger": {"positions": ["RB", "WR", "TE"], "legacy_salary_max": 1000, "legacy_projection_below": 3, "legacy_p90_below": 10, "fallback_salary_max": 2000, "fallback_projection_below": 2, "fallback_p90_below": 8, "opportunity_path": False}, "source": "user_required"},
            ]
        )
    return rules


def resolve_optimizer_strategy(
    *,
    contest_format: str,
    objective: str,
    strategy: str,
) -> dict:
    """Resolve an explicit, versioned engine selection for the requested mode."""
    requested = str(strategy or "").strip().lower()
    if not requested:
        raise ValueError("strategy must be a non-empty optimizer strategy ID")

    rule_profile = resolve_strategy_profile(
        contest_format=contest_format,
        objective=objective,
    )

    def with_rule_profile(payload: dict) -> dict:
        payload["lifecycle"] = "active" if payload["strategy_id"] in SINGLE_LINEUP_STRATEGIES else "historical_research"
        payload["rule_profile_id"] = rule_profile.profile_id
        payload["rule_profile"] = rule_profile.to_dict()
        if payload["strategy_id"] == CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID:
            if rule_profile.profile_id != CLASSIC_LARGE_GPP_PROFILE_ID:
                raise ValueError("Classic small-field strategy has an unexpected correlation policy")
            payload["policy_alignment"] = {
                "status": "borrowed_unvalidated",
                "requested_strategy": CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID,
                "applied_profile_id": rule_profile.profile_id,
                "warning": "Small-field strategy borrows the Classic large-GPP correlation policy; no small-field-specific policy has passed chronological validation.",
            }
        else:
            payload["policy_alignment"] = {
                "status": "aligned", "requested_strategy": payload["strategy_id"],
                "applied_profile_id": rule_profile.profile_id,
            }
        return payload

    if contest_format == "classic" and objective in {"cash", "gpp"}:
        source = "explicit"
        if objective == "cash" and requested in {"baseline", "gpp"}:
            return with_rule_profile(
                {
                    "strategy_id": requested,
                    "version": "legacy",
                    "contest_format": contest_format,
                    "objective": objective,
                    "engine": "legacy_ilp",
                    "evidence_status": "legacy_mode_contract",
                    "description": "Historical classic cash optimizer contract.",
                    "source": "legacy_alias",
                }
            )
        if objective == "cash" and requested in {"cash", "h2h", "head_to_head"}:
            requested = CLASSIC_HEAD_TO_HEAD_STRATEGY_ID
            source = "legacy_alias"
        elif objective == "gpp" and requested in {"gpp", "baseline"}:
            requested = CLASSIC_GPP_BASELINE_STRATEGY_ID
            source = "legacy_alias"
        config = OPTIMIZER_STRATEGIES.get(requested)
        if (
            config is None
            or config.contest_format != contest_format
            or config.objective != objective
        ):
            raise ValueError(
                "strategy must be one of: "
                + ", ".join(
                    sorted(
                        strategy_id
                        for strategy_id, strategy_config in OPTIMIZER_STRATEGIES.items()
                        if strategy_config.contest_format == contest_format
                        and strategy_config.objective == objective
                    )
                )
                + f" for classic {objective}"
            )
        resolved = asdict(config)
        resolved["source"] = source
        return with_rule_profile(resolved)

    if contest_format == "showdown":
        source = "explicit"
        if requested == "baseline":
            requested = (
                SHOWDOWN_CASH_BASELINE_STRATEGY_ID
                if objective == "cash"
                else SHOWDOWN_GPP_BASELINE_STRATEGY_ID
            )
            source = "legacy_alias"
        elif requested in {"gpp", "captain"}:
            requested = (
                SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID
                if objective == "cash"
                else SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID
            )
            source = "legacy_alias"
        config = OPTIMIZER_STRATEGIES.get(requested)
        if (
            config is None
            or config.contest_format != contest_format
            or config.objective != objective
        ):
            valid_strategies = sorted(
                strategy_id
                for strategy_id, candidate in OPTIMIZER_STRATEGIES.items()
                if candidate.contest_format == contest_format
                and candidate.objective == objective
            )
            raise ValueError(
                "strategy must be one of: "
                + ", ".join(valid_strategies)
                + f" for showdown {objective}"
            )
        resolved = asdict(config)
        resolved["source"] = source
        return with_rule_profile(resolved)

    if requested in OPTIMIZER_STRATEGIES:
        raise ValueError(
            f"strategy {requested} is not valid for {contest_format} {objective}"
        )
    return with_rule_profile(
        {
            "strategy_id": requested,
            "version": "legacy",
            "contest_format": contest_format,
            "objective": objective,
            "engine": "legacy_ilp",
            "evidence_status": "legacy_mode_contract",
            "description": "Existing optimizer engine for this format/objective mode.",
            "source": "request",
        }
    )


@dataclass(frozen=True)
class StackPolicyConfig:
    policy_id: str
    contest_format: str
    objective: str
    enabled: bool
    stack_min: int
    stack_max: int | None
    bringback: bool
    include_rb_in_stack: bool = False
    bringback_positions: tuple[str, ...] = ("WR", "TE")
    evidence_status: str = "candidate_unvalidated"
    description: str = ""


STACKING_POLICIES = {
    CLASSIC_CASH_STACK_UNCONSTRAINED_ID: StackPolicyConfig(
        policy_id=CLASSIC_CASH_STACK_UNCONSTRAINED_ID,
        contest_format="classic",
        objective="cash",
        enabled=False,
        stack_min=0,
        stack_max=None,
        bringback=False,
        evidence_status="replay_baseline",
        description="No QB pairing or opponent bring-back constraint.",
    ),
    CLASSIC_CASH_STACK_QB_PAIR_ID: StackPolicyConfig(
        policy_id=CLASSIC_CASH_STACK_QB_PAIR_ID,
        contest_format="classic",
        objective="cash",
        enabled=True,
        stack_min=1,
        stack_max=None,
        bringback=False,
        description="Require at least one same-team QB pass catcher.",
    ),
    CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID: StackPolicyConfig(
        policy_id=CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID,
        contest_format="classic",
        objective="cash",
        enabled=True,
        stack_min=1,
        stack_max=None,
        bringback=True,
        description="Require a QB pass catcher and one opposing WR/TE bring-back.",
    ),
    CLASSIC_GPP_STACK_LEGACY_ID: StackPolicyConfig(
        policy_id=CLASSIC_GPP_STACK_LEGACY_ID,
        contest_format="classic",
        objective="gpp",
        enabled=True,
        stack_min=2,
        stack_max=None,
        bringback=True,
        evidence_status="legacy_default",
        description="Preserve the current classic GPP double-stack and bring-back contract.",
    ),
}


def stacking_policy_config(config: StackPolicyConfig) -> dict:
    """Return a JSON-safe, versioned stacking policy configuration."""
    return {
        "policy_id": config.policy_id,
        "contest_format": config.contest_format,
        "objective": config.objective,
        "enabled": config.enabled,
        "stack_min": config.stack_min,
        "stack_max": config.stack_max,
        "bringback": config.bringback,
        "include_rb_in_stack": config.include_rb_in_stack,
        "bringback_positions": list(config.bringback_positions),
        "evidence_status": config.evidence_status,
        "description": config.description,
        "source": "registry",
    }


def resolve_stacking_policy(
    *,
    contest_format: str,
    objective: str,
    params: dict | None = None,
) -> dict:
    """Resolve a versioned policy while retaining explicit legacy overrides."""
    values = params or {}
    if contest_format != "classic":
        return {
            "policy_id": "showdown_classic_stack_not_applicable_v1",
            "contest_format": contest_format,
            "objective": objective,
            "enabled": False,
            "stack_min": 0,
            "stack_max": None,
            "bringback": False,
            "include_rb_in_stack": False,
            "bringback_positions": [],
            "evidence_status": "not_applicable",
            "description": "Classic QB stacking policies do not apply to showdown.",
            "source": "format_contract",
        }

    requested_policy_id = str(values.get("stack_policy_id") or "").strip()
    legacy_fields = {
        field
        for field in (
            "stack_min",
            "stack_max",
            "bringback",
            "include_rb_in_stack",
            "bringback_positions",
        )
        if field in values
    }
    if requested_policy_id and legacy_fields:
        raise ValueError(
            "stack_policy_id cannot be combined with legacy stack overrides: "
            + ", ".join(sorted(legacy_fields))
        )

    if requested_policy_id:
        policy = STACKING_POLICIES.get(requested_policy_id)
        if policy is None:
            raise ValueError(
                "stack_policy_id must be one of: "
                + ", ".join(sorted(STACKING_POLICIES))
            )
        if policy.contest_format != contest_format or policy.objective != objective:
            raise ValueError(
                f"stack_policy_id {requested_policy_id} is not valid for "
                f"{contest_format} {objective}"
            )
        resolved = stacking_policy_config(policy)
        resolved["source"] = "explicit"
        return resolved

    if not legacy_fields:
        default_policy_id = (
            CLASSIC_CASH_STACK_UNCONSTRAINED_ID
            if objective == "cash"
            else CLASSIC_GPP_STACK_LEGACY_ID
        )
        resolved = stacking_policy_config(STACKING_POLICIES[default_policy_id])
        resolved["source"] = "default"
        return resolved

    legacy_base_id = (
        CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID
        if objective == "cash"
        else CLASSIC_GPP_STACK_LEGACY_ID
    )
    resolved = stacking_policy_config(STACKING_POLICIES[legacy_base_id])
    resolved.update(
        {
            "policy_id": f"classic_{objective}_custom_v1",
            "base_policy_id": legacy_base_id,
            "evidence_status": "legacy_override_unvalidated",
            "source": "legacy_params",
        }
    )
    if "stack_min" in values:
        resolved["stack_min"] = int(values["stack_min"])
    if resolved["stack_min"] < 0:
        raise ValueError("stack_min must be at least 0")
    if "stack_max" in values:
        raw_stack_max = values["stack_max"]
        resolved["stack_max"] = (
            None if raw_stack_max in (None, "", False) else int(raw_stack_max)
        )
    if resolved["stack_max"] is not None and resolved["stack_max"] < resolved["stack_min"]:
        raise ValueError("stack_max must be greater than or equal to stack_min")
    if "bringback" in values:
        resolved["bringback"] = bool(values["bringback"])
    if "include_rb_in_stack" in values:
        resolved["include_rb_in_stack"] = bool(values["include_rb_in_stack"])
    if "bringback_positions" in values:
        raw_positions = values["bringback_positions"]
        if raw_positions is None:
            raw_positions = []
        if isinstance(raw_positions, str):
            raw_positions = [raw_positions]
        resolved["bringback_positions"] = sorted(
            {str(position).strip().upper() for position in raw_positions if str(position).strip()}
        )
    resolved["enabled"] = bool(
        resolved["stack_min"] > 0
        or resolved["stack_max"] is not None
        or resolved["bringback"]
    )
    return resolved


def cash_objective_config(config: CashObjectiveConfig = DEFAULT_CASH_OBJECTIVE) -> dict:
    """Return the exact versioned configuration persisted with classic cash runs."""
    return {
        "objective_id": config.objective_id,
        "mean_weight": config.mean_weight,
        "median_weight": config.median_weight,
        "floor_weight": config.floor_weight,
        "role_certainty_bonus": config.role_certainty_bonus,
        "fragility_penalty": config.fragility_penalty,
        "full_role_sample_size": config.full_role_sample_size,
    }


def build_showdown_cash_objective(pool: pd.DataFrame) -> pd.DataFrame:
    """Apply the declared cash profile to player distributions before CPT scaling."""
    frame = pool.copy()
    weights = resolve_strategy_profile(contest_format="showdown", objective="cash").objective_weights
    mean = pd.to_numeric(frame["projection"], errors="coerce").fillna(0.0)
    score = mean * 0.0
    components = {}
    for component, column in (("mean", "projection"), ("median", "predicted_p50"),
                              ("floor", "predicted_p10"), ("ceiling", "p90")):
        values = pd.to_numeric(frame[column], errors="coerce").fillna(mean) if column in frame else mean
        components[component] = values * weights.get(component, 0.0)
        score += components[component]
    context = pd.to_numeric(frame.get("optimizer_context_adjustment", mean * 0.0), errors="coerce").fillna(0.0)
    frame["showdown_cash_score"] = score + context
    frame["showdown_cash_objective_explanation"] = [
        {"objective_id": "showdown_cash_distribution_v1", "weights": dict(weights),
         "components": {key: float(value.loc[index]) for key, value in components.items()},
         "context_adjustment": float(context.loc[index]), "score": float(frame.loc[index, "showdown_cash_score"])}
        for index in frame.index
    ]
    return frame


def build_classic_cash_objective(
    pool: pd.DataFrame,
    config: CashObjectiveConfig = DEFAULT_CASH_OBJECTIVE,
) -> pd.DataFrame:
    """Add explainable cash-stability terms while preserving projection-only fallback."""
    if pool.empty:
        return pool.copy()
    frame = pool.copy()
    mean_source = frame["projection"] if "projection" in frame.columns else pd.Series(0.0, index=frame.index)
    mean = pd.to_numeric(mean_source, errors="coerce").fillna(0.0)
    median_source = frame["predicted_p50"] if "predicted_p50" in frame.columns else mean
    floor_source = frame["predicted_p10"] if "predicted_p10" in frame.columns else mean
    median_observed = (
        pd.to_numeric(frame["predicted_p50"], errors="coerce").notna()
        if "predicted_p50" in frame.columns
        else pd.Series(False, index=frame.index)
    )
    floor_observed = (
        pd.to_numeric(frame["predicted_p10"], errors="coerce").notna()
        if "predicted_p10" in frame.columns
        else pd.Series(False, index=frame.index)
    )
    median = pd.to_numeric(median_source, errors="coerce").fillna(mean)
    floor = pd.to_numeric(floor_source, errors="coerce").fillna(median)
    sample_source = frame["calibration_sample_size"] if "calibration_sample_size" in frame.columns else pd.Series(0.0, index=frame.index)
    sample_size = pd.to_numeric(sample_source, errors="coerce").fillna(0.0).clip(lower=0.0)
    role_source = frame["calibration_role"] if "calibration_role" in frame.columns else pd.Series("", index=frame.index)
    known_role = ~role_source.fillna("").astype(str).str.lower().isin({"", "unknown", "global", "fallback"})
    role_certainty = (sample_size / float(config.full_role_sample_size)).clip(upper=1.0)
    role_certainty = role_certainty * np.where(known_role, 1.0, 0.5)
    downside_gap = (median - floor).clip(lower=0.0)
    fragility = (downside_gap / median.abs().clip(lower=1.0)).clip(upper=2.0)

    frame["cash_objective_id"] = config.objective_id
    frame["cash_evidence_status"] = np.select(
        [mean <= 0.0, median_observed & floor_observed],
        ["missing_projection", "calibrated_distribution"],
        default="projection_only",
    )
    frame["cash_mean"] = mean
    frame["cash_median"] = median
    frame["cash_floor"] = floor
    frame["cash_role_certainty"] = role_certainty.astype(float)
    frame["cash_fragility"] = fragility.astype(float)
    frame["cash_mean_component"] = mean * config.mean_weight
    frame["cash_median_component"] = median * config.median_weight
    frame["cash_floor_component"] = floor * config.floor_weight
    frame["cash_role_bonus"] = frame["cash_role_certainty"] * config.role_certainty_bonus
    frame["cash_fragility_penalty"] = frame["cash_fragility"] * config.fragility_penalty
    frame["cash_score"] = (
        frame["cash_mean_component"]
        + frame["cash_median_component"]
        + frame["cash_floor_component"]
        + frame["cash_role_bonus"]
        - frame["cash_fragility_penalty"]
    )
    frame["cash_objective_explanation"] = frame.apply(
        lambda row: {
            "objective_id": config.objective_id,
            "evidence_status": str(row["cash_evidence_status"]),
            "mean": float(row["cash_mean"]),
            "median": float(row["cash_median"]),
            "floor_p10": float(row["cash_floor"]),
            "role_certainty": float(row["cash_role_certainty"]),
            "fragility": float(row["cash_fragility"]),
            "mean_component": float(row["cash_mean_component"]),
            "median_component": float(row["cash_median_component"]),
            "floor_component": float(row["cash_floor_component"]),
            "role_bonus": float(row["cash_role_bonus"]),
            "fragility_penalty": float(row["cash_fragility_penalty"]),
            "cash_score": float(row["cash_score"]),
        },
        axis=1,
    )
    return frame


def summarize_classic_cash_lineup(lineup: list[dict]) -> dict:
    """Aggregate player-level cash terms into an inspectable lineup explanation."""
    if not lineup:
        return {}
    missing_projection_players = [
        {
            "player_id": str(row.get("player_id") or ""),
            "name": str(row.get("name") or row.get("player_name") or ""),
            "position": str(row.get("position") or row.get("roster_position") or ""),
        }
        for row in lineup
        if row.get("cash_evidence_status") == "missing_projection"
        or _safe_float(row.get("cash_mean", row.get("projection"))) <= 0.0
    ]
    return {
        "objective_id": CASH_OBJECTIVE_ID,
        "player_count": len(lineup),
        "projected_mean": sum(_safe_float(row.get("cash_mean", row.get("projection"))) for row in lineup),
        "projected_median": sum(_safe_float(row.get("cash_median", row.get("predicted_p50", row.get("projection")))) for row in lineup),
        "projected_floor_p10": sum(_safe_float(row.get("cash_floor", row.get("predicted_p10", row.get("projection")))) for row in lineup),
        "objective_score": sum(_safe_float(row.get("cash_score", row.get("projection"))) for row in lineup),
        "average_role_certainty": sum(_safe_float(row.get("cash_role_certainty")) for row in lineup) / len(lineup),
        "total_fragility_penalty": sum(_safe_float(row.get("cash_fragility_penalty")) for row in lineup),
        "evidence_complete": not missing_projection_players,
        "missing_projection_players": missing_projection_players,
    }


def head_to_head_objective_config(
    config: HeadToHeadObjectiveConfig = DEFAULT_HEAD_TO_HEAD_OBJECTIVE,
) -> dict:
    """Return the persisted, versioned Head-to-Head objective contract."""
    return asdict(config)


def build_head_to_head_objective(
    pool: pd.DataFrame,
    config: HeadToHeadObjectiveConfig = DEFAULT_HEAD_TO_HEAD_OBJECTIVE,
) -> pd.DataFrame:
    """Add a mean-dominant H2H score without hard-pruning legitimate starters."""
    if pool.empty:
        return pool.copy()
    frame = pool.copy()
    mean = pd.to_numeric(frame.get("projection", 0.0), errors="coerce").fillna(0.0)
    ceiling = pd.to_numeric(
        frame.get("p90", frame.get("predicted_p90", mean)), errors="coerce"
    ).fillna(mean)
    floor = pd.to_numeric(
        frame.get("predicted_p10", mean), errors="coerce"
    ).fillna(mean)
    salary = pd.to_numeric(frame.get("salary", 0), errors="coerce").fillna(0.0)
    role = frame.get(
        "calibration_role", pd.Series("", index=frame.index)
    ).fillna("").astype(str).str.upper()
    fragile_punt = (
        (salary <= config.fragile_punt_salary)
        & (mean < config.fragile_punt_mean)
        & role.isin({"", "UNKNOWN", "GLOBAL", "FALLBACK", "ROTATION", "BACKUP"})
    )
    frame["h2h_objective_id"] = config.objective_id
    frame["h2h_mean"] = mean
    frame["h2h_ceiling"] = ceiling
    frame["h2h_floor"] = floor
    frame["h2h_risk"] = (mean - floor).clip(lower=0.0)
    frame["h2h_fragile_punt"] = fragile_punt.astype(bool)
    frame["h2h_fragile_punt_penalty"] = (
        fragile_punt.astype(float) * config.fragile_punt_penalty
    )
    frame["h2h_score"] = (
        config.mean_weight * mean
        + config.ceiling_weight * ceiling
        + config.floor_weight * floor
        - frame["h2h_fragile_punt_penalty"]
    )
    frame["h2h_objective_explanation"] = frame.apply(
        lambda row: {
            "objective_id": config.objective_id,
            "mean": float(row["h2h_mean"]),
            "ceiling_p90": float(row["h2h_ceiling"]),
            "floor_p10": float(row["h2h_floor"]),
            "risk": float(row["h2h_risk"]),
            "fragile_punt": bool(row["h2h_fragile_punt"]),
            "fragile_punt_penalty": float(row["h2h_fragile_punt_penalty"]),
            "h2h_score": float(row["h2h_score"]),
        },
        axis=1,
    )
    return frame


def summarize_head_to_head_lineup(lineup: list[dict]) -> dict:
    """Aggregate H2H mean, ceiling, floor, and risk for UI/persistence."""
    if not lineup:
        return {}
    projected_mean = sum(
        _safe_float(row.get("h2h_mean", row.get("projection"))) for row in lineup
    )
    projected_floor = sum(
        _safe_float(row.get("h2h_floor", row.get("predicted_p10", row.get("projection"))))
        for row in lineup
    )
    individual_ceiling_sum = sum(
        _safe_float(row.get("h2h_ceiling", row.get("p90", row.get("projection"))))
        for row in lineup
    )
    return {
        "objective_id": CLASSIC_HEAD_TO_HEAD_STRATEGY_ID,
        "player_count": len(lineup),
        "projected_mean": projected_mean,
        # Compatibility alias: this is a sum of marginal player P90 values, not a
        # jointly simulated lineup quantile.
        "projected_p90": individual_ceiling_sum,
        "projected_p90_is_joint_quantile": False,
        "individual_ceiling_sum": individual_ceiling_sum,
        "projected_floor_p10": projected_floor,
        "downside_risk": max(0.0, projected_mean - projected_floor),
        "objective_score": sum(
            _safe_float(row.get("h2h_score", row.get("projection"))) for row in lineup
        ),
        "fragile_punt_count": sum(bool(row.get("h2h_fragile_punt")) for row in lineup),
    }


def summarize_individual_ceiling_sum(lineup: list[dict]) -> dict:
    """Describe a summed player ceiling without calling it a lineup quantile."""

    return {
        "metric_id": "individual_ceiling_sum_v1",
        "label": "Individual Ceiling Sum",
        "value": sum(
            _safe_float(row.get("p90", row.get("predicted_p90", row.get("projection"))))
            for row in lineup
        ),
        "source_metric": "player_p90",
        "is_joint_quantile": False,
        "note": "Sum of player-level P90 values; not a simulated lineup P90.",
    }


def classify_showdown_game_script(lineup: list[dict]) -> dict:
    """Classify a completed Showdown lineup from its actual construction."""
    team_rows: dict[str, list[dict]] = {}
    for row in lineup:
        team = str(row.get("player_team") or row.get("team") or "").upper()
        if team:
            team_rows.setdefault(team, []).append(row)

    def _team_summary(team: str, rows: list[dict]) -> dict:
        positions = [str(row.get("position") or "").upper() for row in rows]
        pass_catchers = sum(position in {"WR", "TE"} for position in positions)
        meaningful_rbs = sum(
            position == "RB"
            and (
                _safe_float(row.get("base_projection", row.get("projection"))) >= 3
                or _safe_float(row.get("base_p90", row.get("p90"))) >= 10
                or _safe_float(row.get("base_salary", row.get("salary"))) > 1000
            )
            for row, position in zip(rows, positions)
        )
        return {
            "team": team,
            "players": len(rows),
            "quarterbacks": positions.count("QB"),
            "pass_catchers": pass_catchers,
            "meaningful_rbs": meaningful_rbs,
            "kickers": positions.count("K"),
            "defenses": sum(position in {"DST", "D", "DEF"} for position in positions),
        }

    summaries = {
        team: _team_summary(team, rows) for team, rows in sorted(team_rows.items())
    }
    material_pass_teams = [
        summary for summary in summaries.values()
        if summary["quarterbacks"] >= 1 and summary["pass_catchers"] >= 1
    ]
    if len(material_pass_teams) >= 2:
        return {
            "script_id": "shootout",
            "kind": "shootout",
            "structure_family_id": "two_sided_pass_stack",
            "label": "Two-sided pass stack",
            "reason_codes": ["both_teams_qb_pass_catcher"],
            "team_summaries": summaries,
            "explanation": "The lineup includes a quarterback and pass catcher from each team; this does not classify the game environment.",
        }

    pass_led = [
        summary for summary in summaries.values()
        if summary["quarterbacks"] >= 1
        and summary["pass_catchers"] >= 2
        and summary["pass_catchers"] > summary["meaningful_rbs"]
    ]
    if pass_led:
        leader = max(
            pass_led,
            key=lambda row: (row["pass_catchers"], row["players"], row["team"]),
        )
        team = str(leader["team"])
        return {
            "script_id": f"{team}_pass_led",
            "kind": "pass_led",
            "team": team,
            "label": f"{team} pass-led",
            "reason_codes": ["starting_qb", "multiple_pass_catchers", "pass_over_run_concentration"],
            "team_summaries": summaries,
            "explanation": (
                f"{team} includes its quarterback and {leader['pass_catchers']} WR/TE, "
                f"exceeding its {leader['meaningful_rbs']} meaningful RB selections."
            ),
        }

    run_control = [
        summary for summary in summaries.values()
        if summary["players"] >= 4
        and summary["meaningful_rbs"] >= 1
        and (
            summary["meaningful_rbs"] >= 2
            or summary["kickers"] >= 1
            or summary["defenses"] >= 1
        )
    ]
    if run_control:
        leader = max(
            run_control,
            key=lambda row: (
                row["meaningful_rbs"], row["kickers"] + row["defenses"],
                row["players"], row["team"],
            ),
        )
        team = str(leader["team"])
        return {
            "script_id": f"{team}_run_control",
            "kind": "run_control",
            "team": team,
            "label": f"{team} run-control",
            "reason_codes": ["meaningful_running_back", "control_support"],
            "team_summaries": summaries,
            "explanation": (
                f"{team} has {leader['meaningful_rbs']} meaningful RB selection(s) "
                "with kicker, defense, or additional rushing support."
            ),
        }

    leader = max(
        summaries.values(), key=lambda row: (row["players"], row["team"]),
        default={"team": "UNKNOWN"},
    )
    team = str(leader["team"])
    return {
        "script_id": f"{team}_contrarian",
        "kind": "contrarian",
        "team": team,
        "label": f"Contrarian {team} script",
        "reason_codes": ["no_primary_script_match"],
        "team_summaries": summaries,
        "explanation": "The lineup does not meet the deterministic shootout, pass-led, or run-control definitions.",
    }


def summarize_showdown_game_environment(lineup: list[dict]) -> dict:
    """Preserve the team's market context beside the selected game script."""
    teams: dict[str, dict] = {}
    for row in lineup:
        team = str(row.get("player_team") or row.get("team") or "").upper()
        if not team:
            continue
        summary = teams.setdefault(team, {
            "team": team, "players": 0, "projected_mean": 0.0,
            "selector_contribution": 0.0, "spread": None,
            "implied_total": None, "conditioned_spread": None,
            "conditioned_implied_total": None,
        })
        summary["players"] += 1
        summary["projected_mean"] += _safe_float(row.get("projection"))
        summary["selector_contribution"] += _safe_float(row.get("objective_score"))
        for field, output in (("team_spread_line", "spread"),
                              ("team_implied_total", "implied_total")):
            value = row.get(f"baseline_{field}", row.get(field))
            if value is not None and pd.notna(value):
                summary[output] = float(value)
            conditioned = row.get(field)
            if conditioned is not None and pd.notna(conditioned):
                summary[f"conditioned_{output}"] = float(conditioned)
    ordered = sorted(teams.values(), key=lambda item: (-item["players"], item["team"]))
    underdog_heavy = any(
        row["players"] >= 4 and row["spread"] is not None and row["spread"] > 0
        for row in ordered
    )
    game_totals = [
        float(row["game_total_line"]) for row in lineup
        if row.get("game_total_line") is not None and pd.notna(row["game_total_line"])
    ]
    return {
        "team_counts": " / ".join(f"{row['team']} {row['players']}" for row in ordered),
        "teams": ordered,
        "game_total": game_totals[0] if game_totals else None,
        "market_source": next((row.get("market_source_system") for row in lineup
                               if row.get("market_source_system")), None),
        "market_observed_at": next((row.get("market_observed_at") for row in lineup
                                    if row.get("market_observed_at")), None),
        "underdog_heavy": underdog_heavy,
        "explanation": (
            "Underdog-heavy lineup: selected player projections, salary fit, and "
            "scored stack/context terms outweighed the market underdog signal. "
            "Review the per-team mean and selector contributions below."
            if underdog_heavy else
            "Team count and market context describe the selected lineup; "
            "they are not additional optimizer rewards."
        ),
    }


def summarize_showdown_portfolio_exposure(
    lineups: list[list[dict]],
    *,
    requested_lineups: int,
    exposure_rates: dict[str, float],
) -> dict:
    """Report requested-count caps alongside realized under-filled exposure."""
    generated_lineups = len(lineups)
    player_rows: dict[str, dict] = {}
    player_counts: dict[str, int] = {}
    captain_counts: dict[str, int] = {}
    for lineup in lineups:
        for row in lineup:
            player_id = str(row.get("player_id") or row.get("dk_player_id") or "")
            if not player_id:
                continue
            player_rows[player_id] = row
            player_counts[player_id] = player_counts.get(player_id, 0) + 1
            if str(row.get("roster_position") or "").upper() == "CPT":
                captain_counts[player_id] = captain_counts.get(player_id, 0) + 1

    def _report_row(player_id: str, count: int, exposure_class: str, rate: float, scope: str) -> dict:
        row = player_rows[player_id]
        maximum = max(1, int(math.ceil(max(1, requested_lineups) * rate)))
        realized = count / generated_lineups if generated_lineups else 0.0
        underfill_warning = generated_lineups < requested_lineups and realized > rate + 1e-8
        return {
            "player_id": player_id,
            "player_name": str(row.get("player_name") or row.get("name") or player_id),
            "scope": scope,
            "exposure_class": exposure_class,
            "configured_cap": rate,
            "requested_lineups": requested_lineups,
            "maximum_allowed_appearances": maximum,
            "generated_lineups": generated_lineups,
            "actual_appearances": count,
            "final_generated_portfolio_exposure": (
                count / generated_lineups if generated_lineups else 0.0
            ),
            "cap_respected": count <= maximum,
            "cap_status": "PASS" if count <= maximum else "FAIL",
            "underfill_realized_exceeds_configured": underfill_warning,
            "realized_exposure_warning": (
                "UNDERFILLED PORTFOLIO — requested-count cap passed, but realized final exposure exceeds configured percentage."
                if underfill_warning and count <= maximum else None
            ),
        }

    rows: list[dict] = []
    for player_id, count in sorted(
        player_counts.items(), key=lambda item: (-item[1], str(player_rows[item[0]].get("player_name") or ""))
    ):
        row = player_rows[player_id]
        exposure_class = "core"
        rate = float(exposure_rates.get("core", 0.80))
        if str(row.get("position") or "").upper() == "QB" and bool(row.get("showdown_qb_eligible")):
            exposure_class = "starting_qb"
            rate = float(exposure_rates.get("starting_qb", 1.00))
        elif _safe_float(row.get("base_salary", row.get("salary"))) <= 1000:
            exposure_class = "cheap_punt"
            rate = float(exposure_rates.get("cheap_punt", 0.40))
        rows.append(_report_row(player_id, count, exposure_class, rate, "player"))
    for player_id, count in sorted(captain_counts.items()):
        rows.append(
            _report_row(
                player_id, count, "captain",
                float(exposure_rates.get("captain", 0.60)), "captain",
            )
        )
    return {
        "policy_id": "requested_lineup_denominator_exposure_report_v1",
        "requested_lineups": requested_lineups,
        "generated_lineups": generated_lineups,
        "underfilled": generated_lineups < requested_lineups,
        "cap_denominator": requested_lineups,
        "realized_exposure_denominator": generated_lineups,
        "configured_captain_cap": float(exposure_rates.get("captain", 0.60)),
        "captain_maximum_appearances": max(
            1,
            int(math.ceil(
                max(1, requested_lineups) * float(exposure_rates.get("captain", 0.60))
            )),
        ),
        "rows": rows,
    }


def add_showdown_lineup_chalk_metrics(lineups: list[list[dict]]) -> list[dict]:
    """Attach slot-aware ownership products for relative lineup comparison."""
    summaries: list[dict] = []
    available_logs: list[float] = []
    for lineup in lineups:
        ownership = [row.get("ownership") for row in lineup]
        available = len(ownership) == len(lineup) and all(
            value is not None and 0 < _safe_float(value) <= 100 for value in ownership
        )
        log_probability = (
            sum(math.log(min(1.0, _safe_float(value) / 100.0)) for value in ownership)
            if available else None
        )
        if log_probability is not None:
            available_logs.append(log_probability)
        summaries.append({
            "metric_id": "slot_ownership_log_product_v1",
            "ownership_available": available,
            "salary_left_unused": SALARY_CAP - sum(_safe_float(row.get("salary")) for row in lineup),
            "captain_ownership": next(
                (row.get("ownership") for row in lineup if row.get("roster_position") == "CPT"), None
            ),
            "flex_ownership_sum": (
                sum(_safe_float(row.get("ownership")) for row in lineup
                    if row.get("roster_position") == "FLEX") if available else None
            ),
            "very_low_owned_count": (
                sum(_safe_float(value) < 5.0 for value in ownership) if available else None
            ),
            "missing_ownership_players": [
                str(row.get("name") or row.get("player_name") or row.get("player_id"))
                for row in lineup if row.get("ownership") is None
            ],
            "log_probability": log_probability,
            "probability_product": math.exp(log_probability) if log_probability is not None else None,
            "relative_chalk_score": None,
            "optimization_weight": 0.0,
            "structurally_common": "unavailable_without_field_lineup_model",
            "interpretation": "Ownership product is a relative chalk signal, not a duplication probability or predicted duplicate count.",
        })
    chalkiest_log = max(available_logs, default=None)
    for lineup, summary in zip(lineups, summaries):
        if chalkiest_log is not None and summary["log_probability"] is not None:
            summary["relative_chalk_score"] = 100.0 * math.exp(
                float(summary["log_probability"]) - chalkiest_log
            )
        if lineup:
            lineup[0]["lineup_duplication_risk"] = summary
    return summaries


def place_small_max_metadata_on_captain(lineup: list[dict]) -> None:
    """Keep lineup-level diagnostics on the Captain row after roster sorting."""
    if not lineup or str(lineup[0].get("roster_position")).upper() != "CPT":
        return
    for key in ("lineup_duplication_risk", "small_max_report", "three_max_report"):
        value = next((row.pop(key) for row in lineup if key in row), None)
        if value is not None:
            lineup[0][key] = value


def plan_showdown_captain_diversification(
    qualifying_candidates: list[dict],
    *,
    minimum_distinct: int = 3,
) -> list[str]:
    """Choose strong qualifying Captains while ensuring both teams when possible."""
    ordered = sorted(
        qualifying_candidates,
        key=lambda row: (-_safe_float(row.get("objective_score")), str(row.get("player_id"))),
    )
    target_count = min(minimum_distinct, len(ordered))
    planned = [str(row["player_id"]) for row in ordered[:target_count]]
    qualifying_teams = {str(row.get("team") or "") for row in ordered if row.get("team")}
    planned_teams = {
        str(row.get("team") or "") for row in ordered
        if str(row.get("player_id")) in planned
    }
    if len(qualifying_teams) >= 2 and len(planned_teams) < 2 and planned:
        first_team = str(ordered[0].get("team") or "")
        other_team_candidate = next(
            (row for row in ordered if str(row.get("team") or "") != first_team),
            None,
        )
        if other_team_candidate is not None:
            planned[-1] = str(other_team_candidate["player_id"])
    return planned


def summarize_classic_stack(lineup: list[dict]) -> dict:
    """Describe the realized QB stack instead of only the configured policy."""
    quarterbacks = [
        row for row in lineup if str(row.get("position") or "").upper() == "QB"
    ]
    if not quarterbacks:
        return {"label": "No QB", "pass_catchers": 0, "bring_backs": 0}
    qb = quarterbacks[0]
    qb_team = str(qb.get("player_team") or qb.get("team") or "").upper()
    opponent = str(qb.get("opponent_team") or "").upper()
    pass_catchers = sum(
        str(row.get("player_team") or row.get("team") or "").upper() == qb_team
        and str(row.get("position") or "").upper() in {"WR", "TE"}
        and row is not qb
        for row in lineup
    )
    bring_backs = sum(
        bool(opponent)
        and str(row.get("player_team") or row.get("team") or "").upper() == opponent
        and str(row.get("position") or "").upper() in {"RB", "WR", "TE"}
        for row in lineup
    )
    return {
        "quarterback": str(qb.get("name") or qb.get("player_name") or qb.get("player_id")),
        "quarterback_team": qb_team,
        "pass_catchers": int(pass_catchers),
        "bring_backs": int(bring_backs),
        "label": f"QB + {pass_catchers}; {bring_backs} bring-back",
    }


def resolve_optimizer_mode(
    *,
    contest_format: str | None,
    objective: str | None,
    params: dict | None = None,
) -> tuple[str, str, str]:
    """Resolve the explicit format/objective contract and legacy solver mode."""
    legacy_type = str((params or {}).get("contest_type", "")).strip().lower()

    if contest_format is None:
        contest_format = "showdown" if legacy_type == "captain" else "classic"
    if objective is None:
        objective = "cash" if legacy_type == "cash" else "gpp"

    normalized_format = str(contest_format).strip().lower()
    normalized_objective = str(objective).strip().lower()
    if normalized_format not in VALID_CONTEST_FORMATS:
        raise ValueError(
            f"contest_format must be one of: {', '.join(sorted(VALID_CONTEST_FORMATS))}"
        )
    if normalized_objective not in VALID_OPTIMIZER_OBJECTIVES:
        raise ValueError(
            f"objective must be one of: {', '.join(sorted(VALID_OPTIMIZER_OBJECTIVES))}"
        )

    if normalized_format == "showdown":
        solver_mode = "captain"
    elif normalized_objective == "cash":
        solver_mode = "cash"
    else:
        solver_mode = "tournament"
    return normalized_format, normalized_objective, solver_mode


@dataclass
class OptimizerJob:
    job_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    season: int
    week: int
    slate: str
    strategy: str
    contest_format: str
    objective: str
    params: dict
    projection_run_id: str | None = None
    rule_run_id: str | None = None
    data_cutoff_at: datetime | None = None
    lineage_persisted: bool = False
    results: Optional[list] = None
    message: Optional[str] = None


SALARY_CAP = 50000
TEAM_LIMIT = 4
MIN_SALARY = 2000
logger = logging.getLogger(__name__)


def _json_safe(value):
    """Convert dataframe/numpy values into strict JSON-compatible values."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, datetime):
        # pandas.NaT is also a datetime; serialize missingness before isoformat
        # can turn it into the non-date string "NaT" in source evidence clocks.
        return None if pd.isna(value) else value.isoformat()
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def _safe_float(value) -> float:
    """Normalize optional dataframe scalars for persisted lineup summaries."""
    try:
        if value is None or pd.isna(value):
            return 0.0
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _optional_market_float(value) -> float | None:
    """Keep absent market evidence distinct from a real numeric zero."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_exposure_rate(value, *, default: float) -> float:
    """Accept either a 0-1 rate or UI-style percentage and persist a rate."""
    try:
        rate = float(value)
    except (TypeError, ValueError):
        rate = default
    if not math.isfinite(rate):
        rate = default
    if rate > 1.0:
        rate /= 100.0
    return max(0.01, min(1.0, rate))


def _has_current_opportunity(row: pd.Series | dict) -> bool:
    fields = (
        "pregame_expected_snaps", "pregame_expected_routes",
        "pregame_expected_carries", "pregame_expected_targets",
        "pregame_target_share", "pregame_carry_share",
        "pregame_red_zone_share", "pregame_goal_line_share",
    )
    if any(_safe_float(row.get(field)) > 0 for field in fields):
        return True
    newly_assigned = row.get("pregame_newly_assigned_role")
    if newly_assigned is True or str(newly_assigned).strip().lower() in {"1", "true", "yes"}:
        return True
    role = str(row.get("pregame_role_label") or "").strip().upper()
    return role not in {"", "UNKNOWN", "BACKUP", "ROTATION", "GENERIC"}


def showdown_opportunity_diagnostic(row: pd.Series | dict) -> dict:
    """Explain the existing hard gate without changing its thresholds."""
    salary = _safe_float(row.get("salary"))
    mean = _safe_float(row.get("projection"))
    p90 = _safe_float(row.get("p90"))
    position = str(row.get("position") or "").upper()
    explicit = _has_current_opportunity(row)
    legacy = salary <= 1000 and mean < 3 and p90 < 10
    fallback = salary <= 2000 and mean < 2 and p90 < 8
    excluded = position in {"RB", "WR", "TE"} and not explicit and (legacy or fallback)
    return {
        "roster_status": _json_safe(row.get("roster_status")),
        "player_status": _json_safe(row.get("player_status")),
        "expected_active_probability": _json_safe(row.get("pregame_availability_probability")),
        "expected_start_probability": _json_safe(row.get("pregame_start_probability")),
        "depth_chart_role": _json_safe(row.get("depth_chart_position")),
        "role_label": _json_safe(row.get("pregame_role_label")),
        "expected_snaps": _json_safe(row.get("pregame_expected_snaps")),
        "expected_routes": _json_safe(row.get("pregame_expected_routes")),
        "expected_carries": _json_safe(row.get("pregame_expected_carries")),
        "expected_targets": _json_safe(row.get("pregame_expected_targets")),
        "recent_snap_share_mean_3": _json_safe(row.get("snap_share_mean_3")),
        "recent_carries_mean_3": _json_safe(row.get("carries_mean_3")),
        "recent_targets_mean_3": _json_safe(row.get("targets_mean_3")),
        "carry_share": _json_safe(row.get("pregame_carry_share")),
        "target_share": _json_safe(row.get("pregame_target_share")),
        "red_zone_share": _json_safe(row.get("pregame_red_zone_share")),
        "goal_line_share": _json_safe(row.get("pregame_goal_line_share")),
        "explicit_role_signal": explicit,
        "newly_assigned_role": str(row.get("pregame_newly_assigned_role")).strip().lower() in {"1", "true", "yes"},
        "injury_created_opportunity": _json_safe(row.get("pregame_injury_created_opportunity")),
        "legacy_punt_threshold_met": legacy,
        "low_salary_fallback_threshold_met": fallback,
        "excluded_by_gate": excluded,
        "retention_reason": (
            "explicit_opportunity_signal" if explicit else
            "above_low_salary_fallback_threshold" if salary <= 2000 and not excluded else
            "outside_low_salary_gate" if not excluded else "excluded"
        ),
    }


def apply_showdown_opportunity_gate(pool: pd.DataFrame) -> tuple[pd.DataFrame, set[str]]:
    """Exclude low-opportunity RB/WR/TE values using role evidence first."""
    if pool.empty:
        return pool.copy(), set()
    frame = pool.copy()
    salary = pd.to_numeric(frame.get("salary", 0), errors="coerce").fillna(0)
    mean = pd.to_numeric(frame.get("projection", 0), errors="coerce").fillna(0)
    p90 = pd.to_numeric(frame.get("p90", mean), errors="coerce").fillna(mean)
    positions = frame.get("position", pd.Series("", index=frame.index)).astype(str).str.upper()
    no_opportunity = ~frame.apply(_has_current_opportunity, axis=1)
    skill_player = positions.isin({"RB", "WR", "TE"})
    legacy_punt = (salary <= 1000) & (mean < 3) & (p90 < 10)
    low_salary_fallback = (salary <= 2000) & (mean < 2) & (p90 < 8)
    excluded_mask = skill_player & no_opportunity & (legacy_punt | low_salary_fallback)
    excluded = set(frame.loc[excluded_mask, "player_id"].astype(str))
    return frame.loc[~excluded_mask].reset_index(drop=True), excluded


def _is_high_rushing_qb(row: pd.Series | dict) -> bool:
    role = str(row.get("pregame_role_label") or "").upper()
    return (
        any(token in role for token in ("RUSH", "MOBILE", "DUAL"))
        or _safe_float(row.get("pregame_expected_carries")) >= 5
        or _safe_float(row.get("pregame_carry_share")) >= 0.20
        or _safe_float(row.get("carries_mean_3")) >= 5
    )


def _showdown_qb_correlation_multipliers(pool: pd.DataFrame) -> dict[str, float]:
    """Scale stack rewards to the QB's own pregame projection in this game.

    This changes correlation rewards only. It never changes a player projection
    or assumes that an inferred starter is a poor passer.
    """
    qbs = pool.loc[pool["position"].astype(str).str.upper().eq("QB")]
    projected = pd.to_numeric(qbs.get("base_projection", qbs["projection"]), errors="coerce")
    reference = float(projected.max()) if not projected.empty else 0.0
    if not math.isfinite(reference) or reference <= 0:
        return {str(row["player_id"]): 1.0 for _, row in qbs.iterrows()}
    return {
        str(row["player_id"]): max(0.4, min(1.0, _safe_float(value) / reference))
        for (_, row), value in zip(qbs.iterrows(), projected, strict=True)
    }


def _scale_showdown_qb_bonus_terms(pool: pd.DataFrame, terms: list) -> list:
    """Reduce positive QB-linked soft rewards without weakening penalties."""
    multipliers = _showdown_qb_correlation_multipliers(pool)
    adjusted = []
    for term in terms:
        indexes = set(getattr(term, "required_indexes", ()))
        indexes.update(getattr(term, "captain_indexes", ()))
        if hasattr(term, "left_index"):
            indexes.update((term.left_index, term.right_index))
        qb_values = [
            multipliers[str(pool.loc[index, "player_id"])]
            for index in indexes
            if str(pool.loc[index, "player_id"]) in multipliers
        ]
        factor = min(qb_values) if qb_values and term.adjustment > 0 else 1.0
        adjusted.append(replace(term, adjustment=term.adjustment * factor))
    return adjusted


_SATURATED_SHOWDOWN_RULE_IDS = {
    "correlation.qb_pass_catcher_v2",
    "correlation.shootout_bring_back_v1",
    "correlation.opposing_pass_catchers_v1",
    "captain.qb_pass_catcher_v2",
    "captain.pass_catcher_qb_v2",
}


def _add_saturated_showdown_correlation_objective(
    model: pulp.LpProblem,
    pool: pd.DataFrame,
    selected_vars: dict[int, object],
) -> pulp.LpAffineExpression:
    """Reward stack depth with diminishing returns and one bring-back per QB team."""
    terms: list = []
    teams = pool["player_team"].astype(str).str.upper()
    positions = pool["position"].astype(str).str.upper()
    qb_multipliers = _showdown_qb_correlation_multipliers(pool)
    for qb_index in [i for i in pool.index if positions.iloc[i] == "QB"]:
        team = teams.iloc[qb_index]
        multiplier = qb_multipliers.get(str(pool.loc[qb_index, "player_id"]), 1.0)
        opponent = str(pool.loc[qb_index].get("opponent_team") or "").upper()
        pass_catchers = [
            i for i in pool.index
            if teams.iloc[i] == team and positions.iloc[i] in {"WR", "TE"}
        ]
        count = pulp.lpSum(selected_vars[i] for i in pass_catchers)
        for threshold, bonus in ((1, 0.60), (2, 0.30), (3, 0.10)):
            if len(pass_catchers) < threshold:
                continue
            active = pulp.LpVariable(
                f"saturated_qb_stack_{qb_index}_{threshold}", 0, 1, cat="Binary"
            )
            model += active <= selected_vars[qb_index]
            model += count >= threshold * active
            model += count <= (threshold - 1) + len(pass_catchers) * active + len(pass_catchers) * (1 - selected_vars[qb_index])
            terms.append(bonus * multiplier * active)
        opponent_catchers = [
            i for i in pool.index
            if teams.iloc[i] == opponent and positions.iloc[i] in {"WR", "TE"}
        ]
        if opponent_catchers:
            opponent_count = pulp.lpSum(selected_vars[i] for i in opponent_catchers)
            bring_back = pulp.LpVariable(
                f"saturated_bring_back_{qb_index}", 0, 1, cat="Binary"
            )
            model += bring_back <= selected_vars[qb_index]
            model += bring_back <= opponent_count
            model += opponent_count <= len(opponent_catchers) * bring_back + len(opponent_catchers) * (1 - selected_vars[qb_index])
            terms.append(0.45 * multiplier * bring_back)
    return pulp.lpSum(terms)


def _saturated_showdown_correlation_summary(
    lineup: list[dict], summary: dict
) -> dict:
    kept = [
        dict(row) for row in summary.get("triggered_rules", [])
        if row.get("rule_id") not in _SATURATED_SHOWDOWN_RULE_IDS
        and row.get("construction_kind") != "showdown_fragile_punt"
    ]
    selected_qb_multipliers = {
        str(row.get("player_id")): _safe_float(row.get("qb_correlation_multiplier")) or 1.0
        for row in lineup if str(row.get("position") or "").upper() == "QB"
    }
    for trigger in kept:
        qb_values = [
            selected_qb_multipliers[str(player.get("player_id"))]
            for player in (trigger.get("players") or [])
            if str(player.get("player_id")) in selected_qb_multipliers
        ]
        if not qb_values or _safe_float(trigger.get("objective_contribution")) <= 0:
            continue
        factor = min(qb_values)
        trigger["objective_contribution"] = _safe_float(trigger["objective_contribution"]) * factor
        trigger["score_contribution"] = _safe_float(trigger.get("score_contribution")) * factor
        trigger["evidence"] = {
            **(trigger.get("evidence") or {}), "qb_quality_multiplier": factor,
        }
    custom: list[dict] = []
    for qb in [row for row in lineup if str(row.get("position") or "").upper() == "QB"]:
        multiplier = _safe_float(qb.get("qb_correlation_multiplier")) or 1.0
        team = str(qb.get("player_team") or qb.get("team") or "").upper()
        opponent = str(qb.get("opponent_team") or "").upper()
        catchers = [
            row for row in lineup
            if str(row.get("player_team") or row.get("team") or "").upper() == team
            and str(row.get("position") or "").upper() in {"WR", "TE"}
        ]
        for threshold, contribution in ((1, 0.60), (2, 0.30), (3, 0.10)):
            if len(catchers) >= threshold:
                custom.append({
                    "rule_id": f"correlation.qb_pass_catcher_saturated_{threshold}_v1",
                    "reason_code": f"qb_pass_catcher_{threshold}",
                    "score_contribution": contribution * multiplier,
                    "objective_contribution": contribution * multiplier,
                    "term_kind": "saturated_team_threshold",
                    "players": [{"player_id": str(qb.get("player_id")), "player_name": qb.get("name"), "team": team, "position": "QB"}],
                    "evidence": {"pass_catcher_count": len(catchers), "threshold": threshold, "qb_quality_multiplier": multiplier},
                })
        if any(
            str(row.get("player_team") or row.get("team") or "").upper() == opponent
            and str(row.get("position") or "").upper() in {"WR", "TE"}
            for row in lineup
        ):
            custom.append({
                "rule_id": "correlation.shootout_bring_back_team_once_v1",
                "reason_code": "shootout_bring_back_once",
                "score_contribution": 0.45 * multiplier,
                "objective_contribution": 0.45 * multiplier,
                "term_kind": "saturated_team_threshold",
                "players": [{"player_id": str(qb.get("player_id")), "player_name": qb.get("name"), "team": team, "position": "QB"}],
                "evidence": {"opponent": opponent, "qb_quality_multiplier": multiplier},
            })
    triggers = kept + custom
    total = sum(_safe_float(row.get("objective_contribution")) for row in triggers)
    if any(row.get("solver_scoring_policy") == CAPTAIN_SHORTLIST_POLICY_ID for row in lineup):
        for trigger in triggers:
            trigger["objective_contribution"] = 0.0
        return {
            **summary, "total_rule_adjustment": total, "total_adjustment": 0.0,
            "triggered_rules": triggers, "objective_multiplier": 0.0,
            "correlation_saturation_policy": "diagnostic_only_under_top_four_p90",
        }
    return {
        **summary,
        "total_rule_adjustment": total,
        "total_adjustment": total,
        "triggered_rules": triggers,
        "correlation_saturation_policy": "qb_stack_diminishing_60_30_10_bringback_once_v1",
    }


def _safe_text(*values: object) -> str:
    """Return the first non-missing scalar without evaluating pandas NA as bool."""
    for value in values:
        normalized = _json_safe(value)
        if normalized is not None and str(normalized).strip():
            return str(normalized).strip()
    return ""


def apply_user_opponent_preferences(
    pool: pd.DataFrame,
    excluded_opponent_teams: set[str],
) -> pd.DataFrame:
    """Apply optimizer-only opponent preferences without changing model evidence."""
    if pool.empty or not excluded_opponent_teams:
        return pool.copy()
    if (
        "opponent_team" not in pool.columns
        or pool["opponent_team"].isna().any()
        or pool["opponent_team"].astype(str).str.strip().eq("").any()
    ):
        raise ValueError("Opponent-team exclusion requires an opponent team for every player")
    excluded = {team.strip().upper() for team in excluded_opponent_teams}
    opponents = pool["opponent_team"].astype(str).str.strip().str.upper()
    return pool.loc[~opponents.isin(excluded)].copy().reset_index(drop=True)


def validate_saved_salary_identity(pool_rows: list[dict], salary_rows: list[dict]) -> dict:
    """Verify the exact saved DraftKings row behind each optimizer-eligible player."""
    salary_by_id = {str(row["curated_salary_id"]): row for row in salary_rows}
    violations = []
    for row in pool_rows:
        source_id = str(row.get("salary_source_row_id") or "")
        salary = salary_by_id.get(source_id)
        if salary is None:
            violations.append({"player_id": str(row.get("player_id")),
                               "reason": "saved_salary_row_missing", "source_row_id": source_id})
            continue
        checks = (
            ("player_id", str(row.get("player_id")), str(salary.get("player_master_id"))),
            ("team", normalize_team(str(row.get("player_team") or "")),
             normalize_team(str(salary.get("team") or ""))),
            ("opponent", normalize_team(str(row.get("opponent_team") or "")),
             normalize_team(str(salary.get("opponent") or ""))),
            ("salary", int(row.get("salary") or 0), int(salary.get("salary") or 0)),
        )
        for field, actual, expected in checks:
            if actual != expected:
                violations.append({"player_id": str(row.get("player_id")),
                                   "reason": f"salary_{field}_mismatch",
                                   "actual": actual, "saved": expected,
                                   "source_row_id": source_id})
    return {"status": "PASS" if not violations else "BLOCKER",
            "checked": len(pool_rows), "violations": violations}


def restrict_pool_to_pregame_available(
    pool: pd.DataFrame,
) -> tuple[pd.DataFrame, set[str]]:
    """Exclude players whose selected projection has zero availability."""
    if pool.empty or "pregame_availability_probability" not in pool.columns:
        return pool.copy(), set()
    availability = pd.to_numeric(
        pool["pregame_availability_probability"], errors="coerce"
    )
    unavailable = availability.notna() & availability.le(0.0)
    excluded_ids = set(pool.loc[unavailable, "player_id"].astype(str))
    return pool.loc[~unavailable].copy(), excluded_ids


def restrict_showdown_pool_to_starting_qbs(
    pool: pd.DataFrame,
    *,
    require_exactly_two_teams: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Keep one evidence-backed QB per slate team and describe the decision.

    Explicit QB1 evidence wins. Salary never establishes a starting role. Missing
    football evidence and incomplete team coverage fail closed. Showdown
    callers retain the default two-team requirement; the starter-loading workflow can
    validate a multi-game Classic slate by disabling that format-specific guard.
    """
    if pool.empty:
        raise ValueError("Starter-QB validation has no player pool.")

    frame = pool.copy()
    frame["position"] = frame.get("position", "").fillna("").astype(str).str.upper()
    frame["player_team"] = (
        frame.get("player_team", "").fillna("").astype(str).str.upper()
    )
    teams = sorted(team for team in frame["player_team"].unique() if team)
    if require_exactly_two_teams and len(teams) != 2:
        raise ValueError(
            "Showdown starter-QB validation requires exactly two slate teams; "
            f"found {len(teams)} ({', '.join(teams) or 'none'})."
        )
    if not require_exactly_two_teams and len(teams) < 2:
        raise ValueError(
            "Starter-QB validation requires at least two slate teams; "
            f"found {len(teams)} ({', '.join(teams) or 'none'})."
        )

    qb_pool = frame[frame["position"] == "QB"].copy()
    frame["showdown_qb_eligible"] = frame["position"] != "QB"
    frame["starter_qb_source"] = None
    frame["starter_qb_evidence_tier"] = None
    selected_ids: set[str] = set()
    selections: list[dict] = []
    for team in teams:
        team_qbs = qb_pool[qb_pool["player_team"] == team].copy()
        if team_qbs.empty:
            raise ValueError(
                f"Showdown starter-QB evidence is missing for {team}: no QB is in the slate pool."
            )

        explicit_mask = pd.Series(False, index=team_qbs.index)
        if "is_starting_qb" in team_qbs.columns:
            stored_starter_mask = team_qbs["is_starting_qb"].map(
                lambda value: (
                    bool(value)
                    if isinstance(value, (bool, np.bool_))
                    else str(value).strip().lower() in {"1", "true", "yes"}
                )
            )
            if "starting_qb_evidence_tier" in team_qbs.columns:
                inferred = team_qbs["starting_qb_evidence_tier"].fillna("confirmed").astype(str).str.lower().eq("inferred")
                provisional = team_qbs.get("starting_qb_source", pd.Series("", index=team_qbs.index)).fillna("").astype(str).str.startswith("provisional_")
                stored_starter_mask &= ~inferred | provisional
            explicit_mask |= stored_starter_mask
        if "depth_chart_position" in team_qbs.columns:
            explicit_mask |= (
                team_qbs["depth_chart_position"]
                .fillna("")
                .astype(str)
                .str.upper()
                .isin({"QB1", "STARTER", "STARTING"})
            )
        if "expected_depth_role" in team_qbs.columns:
            explicit_mask |= team_qbs["expected_depth_role"].eq("expected_starter")
        explicit = team_qbs[explicit_mask]
        if len(explicit) > 1:
            raise ValueError(
                f"Showdown starter-QB evidence is ambiguous for {team}: "
                f"{len(explicit)} quarterbacks are marked as starters."
            )

        if len(explicit) == 1:
            selected = explicit.iloc[0]
            source = str(
                selected.get("starting_qb_source") or "explicit_depth_chart_qb1"
            )
            evidence_tier = str(
                selected.get("starting_qb_evidence_tier") or "confirmed"
            ).lower()
            if evidence_tier not in {"confirmed", "inferred"}:
                evidence_tier = "confirmed"
        else:
            raise ValueError(
                f"Showdown starter-QB evidence is ambiguous for {team}: "
                "no sourced QB1; salary cannot establish a starting role."
            )

        player_id = str(selected.get("player_id") or "").strip()
        if not player_id:
            raise ValueError(
                f"Showdown starter-QB evidence for {team} has no canonical player ID."
            )
        selected_ids.add(player_id)
        selected_mask = frame["player_id"].astype(str) == player_id
        frame.loc[selected_mask, "showdown_qb_eligible"] = True
        frame.loc[selected_mask, "starter_qb_source"] = source
        frame.loc[selected_mask, "starter_qb_evidence_tier"] = evidence_tier
        selections.append(
            {
                "team": team,
                "player_id": player_id,
                "player_name": str(
                    selected.get("name") or selected.get("player_name") or player_id
                ),
                "salary": _safe_float(selected.get("salary")),
                "source": source,
                "evidence_tier": evidence_tier,
                **(
                    {"source_uri": str(selected.get("starting_qb_source_uri"))}
                    if str(selected.get("starting_qb_source_uri") or "").strip()
                    else {}
                ),
                **(
                    {"observed_at": str(selected.get("starting_qb_observed_at"))}
                    if str(selected.get("starting_qb_observed_at") or "").strip()
                    else {}
                ),
                **(
                    {"note": str(selected.get("starting_qb_note"))}
                    if str(selected.get("starting_qb_note") or "").strip()
                    else {}
                ),
            }
        )

    specialty_ids = {
        str(row.get("player_id"))
        for row in qb_pool.to_dict(orient="records")
        if str(row.get("player_id") or "").strip()
        and has_explicit_specialty_role(row)
    }
    specialty_ids -= selected_ids
    if specialty_ids:
        specialty_mask = frame["player_id"].astype(str).isin(specialty_ids)
        frame.loc[specialty_mask, "showdown_qb_eligible"] = True
        frame.loc[specialty_mask, "starter_qb_source"] = "explicit_specialty_role"
        frame.loc[specialty_mask, "starter_qb_evidence_tier"] = "confirmed"

    qb_ids = set(qb_pool["player_id"].astype(str))
    eligible_qb_ids = selected_ids | specialty_ids
    filtered = frame[
        (frame["position"] != "QB")
        | frame["player_id"].astype(str).isin(eligible_qb_ids)
    ].copy()
    metadata = {
        "status": "passed",
        "required_starters": len(teams),
        "candidate_qb_count": len(qb_pool),
        "selected_qb_count": len(selected_ids),
        "specialty_qb_count": len(specialty_ids),
        "specialty_qb_ids": sorted(specialty_ids),
        "excluded_qb_count": len(qb_ids - eligible_qb_ids),
        "selected": selections,
        "evidence_status": (
            "confirmed" if all(row["evidence_tier"] == "confirmed" for row in selections)
            else "provisional" if any(
                str(row.get("source") or "").startswith("provisional_")
                for row in selections
            ) else "salary_inferred"
        ),
    }
    return filtered.reset_index(drop=True), metadata


def build_showdown_captain_prior(
    pool: pd.DataFrame,
    *,
    model_path: str,
    strength: float,
) -> tuple[pd.DataFrame, dict]:
    """Apply the validated captain-position model to CPT objective weights."""
    configured_path = Path(model_path).expanduser()
    resolved_path = (
        configured_path
        if configured_path.is_absolute()
        else Path(__file__).resolve().parents[3] / configured_path
    ).resolve()
    if not resolved_path.exists():
        raise ValueError(f"Showdown captain model not found: {resolved_path}")
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    model = payload.get("model") or {}
    classes = [str(value).upper() for value in model.get("classes", [])]
    feature_names = [str(value) for value in model.get("feature_names", [])]
    weights = np.asarray(model.get("weights"), dtype=float)
    bias = np.asarray(model.get("bias"), dtype=float)
    x_mean = np.asarray(model.get("x_mean"), dtype=float)
    x_std = np.asarray(model.get("x_std"), dtype=float)
    if (
        not classes
        or not feature_names
        or weights.shape != (len(feature_names), len(classes))
        or bias.shape != (len(classes),)
        or x_mean.shape != (len(feature_names),)
        or x_std.shape != (len(feature_names),)
    ):
        raise ValueError("Invalid showdown captain model artifact.")

    frame = pool.copy()
    frame["position"] = frame.get("position", "").fillna("").astype(str).str.upper()
    frame["player_team"] = (
        frame.get("player_team", "").fillna("").astype(str).str.upper()
    )

    def numeric_values(column: str, *, absolute: bool = False) -> list[float]:
        if column not in frame.columns:
            return []
        values = pd.to_numeric(frame[column], errors="coerce").dropna().astype(float)
        if absolute:
            values = values.abs()
        return [float(value) for value in values if math.isfinite(float(value))]

    def median_or_zero(values: list[float]) -> float:
        return float(np.median(values)) if values else 0.0

    team_counts = sorted(
        [
            int(count)
            for count in frame[frame["player_team"] != ""]
            .groupby("player_team")
            .size()
            .tolist()
        ],
        reverse=True,
    )
    team_implied_values: list[float] = []
    if "team_implied_total" in frame.columns:
        for _, rows in frame.groupby("player_team"):
            values = pd.to_numeric(
                rows["team_implied_total"], errors="coerce"
            ).dropna()
            if not values.empty:
                team_implied_values.append(float(values.median()))
    features = {
        "game_total_line": median_or_zero(numeric_values("game_total_line")),
        "game_spread_abs": median_or_zero(
            numeric_values("team_spread_line", absolute=True)
        ),
        "max_team_implied_total": max(team_implied_values, default=0.0),
        "min_team_implied_total": min(team_implied_values, default=0.0),
        "implied_total_diff": (
            max(team_implied_values) - min(team_implied_values)
            if team_implied_values
            else 0.0
        ),
        "has_vegas_line": float(
            bool(numeric_values("game_total_line"))
            and bool(numeric_values("team_spread_line"))
        ),
        "pool_size": float(len(frame)),
        "team_count": float(frame["player_team"].replace("", np.nan).nunique()),
        "team1_player_count": float(team_counts[0]) if team_counts else 0.0,
        "team2_player_count": float(team_counts[1]) if len(team_counts) > 1 else 0.0,
    }
    for position in ("QB", "RB", "WR", "TE", "K", "DST"):
        rows = frame[frame["position"] == position]
        projection_values = (
            pd.to_numeric(rows.get("projection", pd.Series(dtype=float)), errors="coerce")
            .dropna()
            .tolist()
        )
        salary_values = (
            pd.to_numeric(rows.get("salary", pd.Series(dtype=float)), errors="coerce")
            .dropna()
            .tolist()
        )
        features[f"{position.lower()}_count"] = float(len(rows))
        features[f"top_{position.lower()}_proj_mean"] = float(
            max(projection_values, default=0.0)
        )
        features[f"top_{position.lower()}_salary"] = float(
            max(salary_values, default=0.0)
        )

    feature_vector = np.asarray(
        [float(features.get(name, 0.0)) for name in feature_names], dtype=float
    )
    safe_std = np.where(x_std < 1e-6, 1.0, x_std)
    standardized = (feature_vector - x_mean) / safe_std
    logits = standardized @ weights + bias
    shifted = logits - np.max(logits)
    probabilities = np.exp(shifted)
    probabilities = probabilities / np.sum(probabilities)
    model_position_probs = {
        classes[index]: float(probabilities[index]) for index in range(len(classes))
    }
    out_of_distribution_features = [
        {
            "feature": feature_names[index],
            "standard_deviations": float(standardized[index]),
        }
        for index in range(len(feature_names))
        if abs(float(standardized[index])) > 5.0
    ]
    historical_probs = {
        str(position).upper(): float(probability)
        for position, probability in (
            payload.get("summary", {}).get(
                "historical_captain_position_probabilities", {}
            )
            or {}
        ).items()
    }
    if out_of_distribution_features and historical_probs:
        probability_source = "historical_position_mix_fallback"
        position_probs = {
            position: historical_probs.get(position, 0.0) for position in classes
        }
    else:
        probability_source = "matchup_model"
        position_probs = model_position_probs
    probability_total = float(sum(position_probs.values()))
    if probability_total <= 0:
        raise ValueError("Showdown captain model produced no usable probabilities.")
    position_probs = {
        position: probability / probability_total
        for position, probability in position_probs.items()
    }

    prior_strength = float(min(max(strength, 0.0), 1.0))
    class_scale = float(max(len(position_probs), 1))
    frame["captain_position_probability"] = frame["position"].map(
        lambda position: float(position_probs.get(str(position).upper(), 0.0))
    )
    frame["captain_objective_multiplier"] = frame[
        "captain_position_probability"
    ].map(
        lambda probability: (1.0 - prior_strength)
        + (prior_strength * max(0.05, float(probability) * class_scale))
    )
    metadata = {
        "model_path": str(model_path),
        "prior_strength": prior_strength,
        "probability_source": probability_source,
        "position_probabilities": position_probs,
        "raw_model_position_probabilities": model_position_probs,
        "out_of_distribution_features": out_of_distribution_features,
        "context_features": {
            name: float(features.get(name, 0.0)) for name in feature_names
        },
        "evaluation": payload.get("summary", {}),
    }
    return frame, metadata


def _merge_simulation_evidence(
    pool: pd.DataFrame,
    simulation_rows: List[dict],
) -> pd.DataFrame:
    """Merge DT-502 evidence without discarding existing ownership coverage."""
    simulation_frame = pd.DataFrame(simulation_rows).rename(
        columns={"field_ownership": "simulation_field_ownership"}
    )
    evidence_columns = (
        "optimal_lineup_probability",
        "simulation_field_ownership",
        "leverage_score",
    )
    for column in evidence_columns:
        if column not in simulation_frame.columns:
            simulation_frame[column] = np.nan
    merged = pool.copy()
    merged["player_id"] = merged["player_id"].astype(str)
    if simulation_frame.empty:
        for column in evidence_columns:
            merged[column] = np.nan
    else:
        simulation_frame["player_id"] = simulation_frame["player_id"].astype(str)
        merged = merged.merge(
            simulation_frame[["player_id", *evidence_columns]],
            on="player_id",
            how="left",
        )
    existing_ownership = (
        pd.to_numeric(merged["ownership"], errors="coerce")
        if "ownership" in merged.columns
        else pd.Series(np.nan, index=merged.index, dtype=float)
    )
    simulation_ownership = pd.to_numeric(
        merged["simulation_field_ownership"], errors="coerce"
    )
    merged["ownership"] = simulation_ownership.combine_first(existing_ownership)
    merged["leverage"] = pd.to_numeric(merged["leverage_score"], errors="coerce")
    return merged


def _normalize_alias(name: str) -> str:
    """Map common aliases to canonical forms (e.g., Hollywood Brown -> Marquise Brown)."""
    key = " ".join(name.lower().replace("'", " ").split())
    if "hollywood brown" in key or ("hollywood" in key and "brown" in key):
        return "marquise brown"
    if key == "marquise brown":
        return "marquise brown"
    return key


def _resolve_player_control_names(
    pool: pd.DataFrame,
    values: object,
    *,
    field_name: str,
) -> tuple[set[str], set[str]]:
    """Resolve user-facing names to unambiguous canonical IDs in this slate."""

    if values is None:
        return set(), set()
    if isinstance(values, str):
        raw_values = [values]
    else:
        try:
            raw_values = list(values)  # type: ignore[arg-type]
        except TypeError as exc:
            raise ValueError(f"{field_name} must be a list of player names") from exc
    requested_names = {
        str(name).strip()
        for value in raw_values
        for name in str(value).split(",")
        if str(name).strip()
    }
    if not requested_names:
        return set(), set()

    ids_by_name: dict[str, set[str]] = {}
    for row in pool.to_dict(orient="records"):
        player_id = str(row.get("player_id") or "").strip()
        if not player_id:
            continue
        player_name = next(
            (
                str(row.get(column) or "").strip()
                for column in ("player_display_name", "player_name", "name")
                if str(row.get(column) or "").strip()
            ),
            "",
        )
        if player_name:
            ids_by_name.setdefault(_normalize_alias(player_name), set()).add(
                player_id
            )

    resolved_ids: set[str] = set()
    for requested_name in sorted(requested_names):
        matches = ids_by_name.get(_normalize_alias(requested_name), set())
        if not matches:
            raise ValueError(
                f"{field_name} player was not found in the selected slate: "
                f"{requested_name}"
            )
        if len(matches) > 1:
            raise ValueError(
                f"{field_name} player name is ambiguous; use a canonical player ID: "
                f"{requested_name}"
            )
        resolved_ids.update(matches)
    return resolved_ids, requested_names


def _log_pool_stats(df: pd.DataFrame, label: str) -> None:
    """Debug helper: print projection/ceiling diagnostics."""
    if df.empty:
        print(f"[pool:{label}] empty")
        return
    if "position" not in df.columns:
        print(f"[pool:{label}] missing position column; cols={list(df.columns)}")
        return

    def _stats(series: pd.Series) -> tuple[float, float, float]:
        series = pd.to_numeric(series, errors="coerce")
        return (float(series.min()), float(series.median()), float(series.max()))

    proj_min, proj_med, proj_max = _stats(df.get("projection", pd.Series()))
    p90_min, p90_med, p90_max = _stats(df.get("p90", pd.Series()))
    print(f"[pool:{label}] rows={len(df)} proj min/med/max={proj_min:.2f}/{proj_med:.2f}/{proj_max:.2f} "
          f"p90 min/med/max={p90_min:.2f}/{p90_med:.2f}/{p90_max:.2f}")
    for pos, group in df.groupby("position"):
        g_proj_min, g_proj_med, g_proj_max = _stats(group.get("projection", pd.Series()))
        g_p90_min, g_p90_med, g_p90_max = _stats(group.get("p90", pd.Series()))
        print(f"[pool:{label}] {pos} count={len(group)} proj {g_proj_min:.2f}/{g_proj_med:.2f}/{g_proj_max:.2f} "
              f"p90 {g_p90_min:.2f}/{g_p90_med:.2f}/{g_p90_max:.2f}")
    proj_nan = df["projection"].isna().sum() if "projection" in df else 0
    p90_nan = df["p90"].isna().sum() if "p90" in df else 0
    proj_zero = (df["projection"] == 0).sum() if "projection" in df else 0
    p90_zero = (df["p90"] == 0).sum() if "p90" in df else 0
    print(f"[pool:{label}] NaNs proj={proj_nan} p90={p90_nan} zeros proj={proj_zero} p90={p90_zero}")
    cols = ["name", "position", "player_team", "salary", "projection", "p90"]
    top_proj = df.sort_values("projection", ascending=False).head(10)[cols] if "projection" in df else pd.DataFrame()
    top_p90 = df.sort_values("p90", ascending=False).head(10)[cols] if "p90" in df else pd.DataFrame()
    print(f"[pool:{label}] top proj:\n{top_proj.to_string(index=False)}")
    print(f"[pool:{label}] top p90:\n{top_p90.to_string(index=False)}")


class OptimizerService:
    """ILP-based optimizer that maximizes projected points under DK constraints."""

    def __init__(self, connection_string: str | None = None) -> None:
        self._jobs: Dict[str, OptimizerJob] = {}
        self._cache_access: dict[str, float] = {}
        self._cache_lock = RLock()
        self.connection_string = connection_string or get_connection_string()
        self.engine = create_engine(self.connection_string)

    @cached_property
    def _cache_lock(self):
        return RLock()

    @cached_property
    def _cache_access(self) -> dict[str, float]:
        return {}

    def _prune_result_cache(self) -> None:
        settings = get_settings()
        now = monotonic()
        terminal = [job_id for job_id, job in self._jobs.items()
                    if job.lineage_persisted and job.status in {"completed", "failed"}]
        expired = [job_id for job_id in terminal
                   if now - self._cache_access.get(job_id, 0) >= settings.optimizer_result_cache_ttl_seconds]
        for job_id in expired:
            self._jobs.pop(job_id, None)
            self._cache_access.pop(job_id, None)
        remaining = sorted((job_id for job_id in terminal if job_id in self._jobs),
                           key=lambda job_id: self._cache_access.get(job_id, 0))
        for job_id in remaining[:max(0, len(remaining) - settings.optimizer_result_cache_max_entries)]:
            self._jobs.pop(job_id, None)
            self._cache_access.pop(job_id, None)

    def _cache_job(self, job: OptimizerJob) -> None:
        with self._cache_lock:
            self._jobs[job.job_id] = job
            self._cache_access[job.job_id] = monotonic()
            self._prune_result_cache()

    def cache_status(self) -> dict:
        with self._cache_lock:
            self._prune_result_cache()
            settings = get_settings()
            return {"entries": len(self._jobs), "max_completed_entries": settings.optimizer_result_cache_max_entries,
                    "ttl_seconds": settings.optimizer_result_cache_ttl_seconds}

    def list_completed_projection_runs(self, *, season: int, week: int, slate: str) -> list[dict]:
        """Available optimizer projection choices, newest completed first."""
        with self.engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT r.projection_run_id, r.created_at, r.row_count, r.data_cutoff_at,
                       CASE WHEN artifact.model_run_id IS NULL THEN 'missing'
                            ELSE 'stored' END AS model_artifact_status
                FROM target.projection_run r
                LEFT JOIN target.model_artifact artifact ON artifact.model_run_id = r.model_run_id
                WHERE r.season = :season AND r.week = :week
                  AND UPPER(r.slate_id) = UPPER(:slate)
                  AND r.status = 'completed' AND r.row_count > 0
                  AND EXISTS (
                      SELECT 1 FROM target.player_projection p
                      WHERE p.projection_run_id = r.projection_run_id
                  )
                ORDER BY r.created_at DESC, r.projection_run_id DESC
                LIMIT 100
            """), {"season": season, "week": week, "slate": slate}).mappings().all()
        return [dict(row) for row in rows]

    def _resolve_run_lineage(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        projection_run_id: str | None,
        rule_run_id: str | None,
        data_cutoff_at: datetime | None,
    ) -> tuple[str | None, str | None, datetime | None]:
        """Best-effort lookup of the latest completed or explicitly selected projection."""
        try:
            with self.engine.begin() as connection:
                if projection_run_id is None or data_cutoff_at is None:
                    projection_query = (
                        "SELECT p.projection_run_id, p.data_cutoff_at "
                        "FROM target.player_projection p "
                        "JOIN target.projection_run r ON r.projection_run_id = p.projection_run_id "
                        "WHERE p.season = :season AND p.week = :week "
                        "AND UPPER(r.slate_id) = UPPER(:slate) "
                        "AND r.status = 'completed' AND r.row_count > 0 "
                    )
                    projection_params = {
                        "season": season,
                        "week": week,
                        "slate": slate,
                    }
                    if projection_run_id is not None:
                        projection_query += "AND p.projection_run_id = :projection_run_id "
                        projection_params["projection_run_id"] = projection_run_id
                    projection_query += "ORDER BY r.created_at DESC, p.created_at DESC LIMIT 1"
                    projection_row = connection.execute(
                        text(projection_query),
                        projection_params,
                    ).mappings().first()
                    if projection_row:
                        projection_run_id = str(projection_row["projection_run_id"])
                        data_cutoff_at = data_cutoff_at or projection_row.get("data_cutoff_at")

                if rule_run_id is None:
                    rule_query = (
                        "SELECT rule_run_id FROM target.symbolic_adjusted_projection "
                        "WHERE season = :season AND week = :week "
                        "AND (slate_id = :slate OR slate_id IS NULL) "
                    )
                    rule_params = {"season": season, "week": week, "slate": slate}
                    if projection_run_id is not None:
                        rule_query += "AND projection_run_id = :projection_run_id "
                        rule_params["projection_run_id"] = projection_run_id
                    rule_query += "ORDER BY created_at DESC LIMIT 1"
                    rule_row = connection.execute(
                        text(rule_query),
                        rule_params,
                    ).mappings().first()
                    if rule_row:
                        rule_run_id = str(rule_row["rule_run_id"])
        except Exception as exc:  # noqa: BLE001 - legacy databases may not have target lineage tables yet
            logger.info("Optimizer lineage lookup unavailable: %s", exc)
        return projection_run_id, rule_run_id, data_cutoff_at

    def _persist_optimizer_run(self, job: OptimizerJob) -> bool:
        """Persist one optimizer execution even when it produced no lineups."""
        decision_context = job.params.get("decision_context")
        decision_context = decision_context if isinstance(decision_context, dict) else {}
        runtime = job.params.setdefault("strategy_runtime", {})
        runtime["candidate_pool_manifest"] = candidate_snapshot(
            job.params, job.contest_format
        )
        selected_rows = [row for lineup in job.results or [] for row in lineup]
        pool_rows = (runtime.get("player_pool") or {}).get("rows") or []
        availability_overrides = [
            {"player_id": row.get("player_id"), "availability_override": row.get("availability_override"),
             "reason": row.get("exclusion_reasons")}
            for row in pool_rows if row.get("availability_override") not in {None, "default"}
        ]
        def first_selected(key):
            return next((row.get(key) for row in selected_rows if row.get(key) is not None), None)
        decision_snapshot = {
            "captured_at": job.updated_at.isoformat(),
            "data_cutoff_at": job.data_cutoff_at.isoformat() if job.data_cutoff_at else None,
            "nfl_state_snapshot": decision_context.get("nfl_state_snapshot"),
            "injury_redistribution_state": decision_context.get("injury_redistribution_state"),
            "projection_run_id": job.projection_run_id,
            "projection_model_artifact": {"status": "unavailable", "reason": "No projection run selected"},
            "projection_market_snapshot": [],
            "optimizer_run_id": job.job_id,
            "single_lineup_selection": deepcopy(runtime.get("single_lineup", {}).get("recommended")),
            "single_lineup_policy": (runtime.get("single_lineup") or {}).get("contract_id"),
            "showdown_evidence_snapshot": deepcopy(job.params.get("showdown_evidence_snapshot")),
            "data_readiness": deepcopy(job.params.get("data_readiness")),
            "major_hypotheses": decision_context.get("major_hypotheses", []),
            "availability_assumptions": decision_context.get("availability_assumptions", []) + availability_overrides,
            "injury_scenarios": decision_context.get("injury_scenarios", []),
            "user_lineup_exclusions": (
                [] if decision_context.get("analytic_control")
                else job.params.get("exclude_player_ids", [])
            ),
            "analytic_control": decision_context.get("analytic_control"),
            "captain_prior_strength": (job.params.get("objective_config") or {}).get("captain_prior_strength"),
            "captain_prior_source": runtime.get("captain_position_model"),
            "correlation_context_policy": decision_context.get("correlation_context_policy") or {
                "correlation": first_selected("lineup_correlation_summary"),
                "context": first_selected("lineup_context_summary"),
            },
            "correlation_policy": decision_context.get("correlation_policy"),
            "context_policy": decision_context.get("context_policy"),
            "ownership_source": decision_context.get("ownership_source") or first_selected("ownership_run_id"),
            "ownership_observed_at": decision_context.get("ownership_observed_at") or first_selected("ownership_observed_at"),
            "game_market_inputs": decision_context.get("game_market_inputs") or [
                {"player_id": row.get("player_id"), "game_total_line": row.get("game_total_line"),
                 "team_spread_line": row.get("team_spread_line"), "team_implied_total": row.get("team_implied_total")}
                for row in selected_rows if row.get("game_total_line") is not None
            ],
            "market_snapshot": [
                {key: row.get(key) for key in (
                    "player_id", "game_total_line", "team_spread_line",
                    "team_implied_total", "market_context_point_in_time_safe",
                )} for row in selected_rows
            ],
            "injury_availability_snapshot": [
                {key: row.get(key) for key in (
                    "player_id", "official_availability_status", "availability_override",
                    "model_availability_used", "pregame_availability_probability",
                    "pregame_start_probability", "pregame_injury_status", "player_status",
                )} for row in pool_rows
            ],
            "selected_ownership_snapshot": [
                {key: row.get(key) for key in (
                    "player_id", "ownership", "projected_ownership",
                    "ownership_projection", "ownership_run_id", "ownership_observed_at",
                )} for row in selected_rows
            ],
            "portfolio_constraints": job.params.get("portfolio_constraints"),
            "user_preference_constraints": {
                key: job.params.get(key) for key in (
                    "exclude_player_ids", "lock_player_ids", "exclude_players",
                    "exclude_questionable",
                    "locked_players", "max_exposure", "min_exposure",
                    "max_lineups_per_primary_game", "max_lineup_overlap",
                    "elevated_player_max_exposure", "max_elevated_players_per_lineup",
                ) if key in job.params
            },
            "model_explanation_version": "tree-path-v1",
            "selected_lineups": [
                [{"player_id": row.get("player_id"), "roster_position": row.get("roster_position")}
                 for row in lineup] for lineup in job.results or []
            ],
            "primary_lineup": decision_context.get("primary_lineup") or (
                [{"player_id": row.get("player_id"), "roster_position": row.get("roster_position")}
                 for row in job.results[0]] if job.results else None
            ),
            "play_decision": decision_context.get("play_decision"),
            "important_alternatives": decision_context.get("important_alternatives") or (
                (runtime.get("single_entry") or {}).get("all_candidates", [])[1:16]
            ),
            "reason_selected": decision_context.get("reason_selected") or job.message,
            "ablation_results": [
                {key: value for key, value in row["lineup_control_comparison"].items() if key != "replay"}
                for lineup in job.results or []
                for row in lineup if row.get("lineup_control_comparison")
            ] + decision_context.get("shadow_results", []),
        }
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=(
                "optimizer_run",
                "lineup",
                "lineup_player",
                "lineup_constraint_explanation",
                "classic_prospective_experiment",
                "evaluation_record",
            ),
        )
        try:
            with self.engine.begin() as connection:
                if job.projection_run_id:
                    artifact_row = connection.execute(text("""
                        SELECT a.artifact_uri, a.artifact_sha256, a.model_version,
                               a.training_dataset_sha256, a.code_hash
                        FROM target.projection_run pr
                        LEFT JOIN target.model_artifact a ON a.model_run_id = pr.model_run_id
                        WHERE pr.projection_run_id = :projection_run_id
                    """), {"projection_run_id": job.projection_run_id}).mappings().first()
                    decision_snapshot["projection_model_artifact"] = (
                        dict(artifact_row) if artifact_row and artifact_row["artifact_uri"] else
                        {"status": "unavailable", "reason": "Fitted artifact absent from selected projection run"}
                    )
                    projection_market = connection.execute(text("""
                        SELECT p.player_id, p.game_id,
                               f.feature_json ->> 'game_total_line' AS game_total_line,
                               f.feature_json ->> 'team_spread_line' AS team_spread_line,
                               f.feature_json ->> 'team_implied_total' AS team_implied_total,
                               f.feature_json ->> 'opponent_implied_total' AS opponent_implied_total
                        FROM target.player_projection p
                        JOIN target.model_run mr ON mr.model_run_id = p.model_run_id
                        LEFT JOIN target.feature_player_game f
                          ON f.feature_run_id = mr.feature_run_id
                         AND f.player_id = p.player_id AND f.game_id = p.game_id
                         AND f.season = p.season AND f.week = p.week
                        WHERE p.projection_run_id = :projection_run_id
                    """), {"projection_run_id": job.projection_run_id}).mappings()
                    decision_snapshot["projection_market_snapshot"] = [dict(row) for row in projection_market]
                ownership_run_id = job.params.get("ownership_run_id") or first_selected("ownership_run_id")
                if ownership_run_id:
                    ownership_rows = connection.execute(text("""
                        SELECT ownership_run_id::TEXT, player_id, roster_position,
                               projected_ownership, data_cutoff_at, feature_json
                        FROM target.ownership_projection
                        WHERE ownership_run_id::TEXT = :ownership_run_id
                          AND season = :season AND week = :week
                          AND UPPER(slate_id) = UPPER(:slate)
                    """), {"ownership_run_id": str(ownership_run_id),
                             "season": job.season, "week": job.week,
                             "slate": job.slate}).mappings()
                    decision_snapshot["ownership_snapshot"] = [dict(row) for row in ownership_rows]
                else:
                    decision_snapshot["ownership_snapshot"] = []
                benchmarks = connection.execute(text("""
                    SELECT benchmark_id, source_name, source_url, captured_at,
                           raw_snapshot_uri, raw_snapshot_sha256, status
                    FROM target.external_projection_benchmark
                    WHERE season = :season AND week = :week AND slate_id = :slate
                      AND captured_at <= :captured_at
                    ORDER BY captured_at, benchmark_id
                """), {"season": job.season, "week": job.week,
                         "slate": job.slate, "captured_at": job.updated_at}).mappings()
                decision_snapshot["external_benchmark_snapshots"] = [dict(row) for row in benchmarks]
                connection.execute(
                    text(
                        """
                        INSERT INTO target.optimizer_run
                            (optimizer_run_id, projection_run_id, rule_run_id, slate_id,
                             season, week, contest_format, objective, strategy,
                             objective_config_json, constraint_config_json, data_cutoff_at,
                             created_at, updated_at, status, message)
                        VALUES
                            (:optimizer_run_id, :projection_run_id, :rule_run_id, :slate_id,
                             :season, :week, :contest_format, :objective, :strategy,
                             CAST(:objective_config_json AS JSONB), CAST(:constraint_config_json AS JSONB),
                             :data_cutoff_at, :created_at, :updated_at, :status, :message)
                        ON CONFLICT (optimizer_run_id) DO UPDATE SET
                            updated_at = EXCLUDED.updated_at,
                            status = EXCLUDED.status,
                            message = EXCLUDED.message,
                            objective_config_json = EXCLUDED.objective_config_json,
                            constraint_config_json = EXCLUDED.constraint_config_json
                        """
                    ),
                    {
                        "optimizer_run_id": job.job_id,
                        "projection_run_id": job.projection_run_id,
                        "rule_run_id": job.rule_run_id,
                        "slate_id": job.slate,
                        "season": job.season,
                        "week": job.week,
                        "contest_format": job.contest_format,
                        "objective": job.objective,
                        "strategy": job.strategy,
                        "objective_config_json": json.dumps(
                            _json_safe({
                                "objective": job.objective,
                                "strategy": job.strategy,
                                **(
                                    job.params.get("objective_config", {})
                                    if isinstance(job.params.get("objective_config"), dict)
                                    else {}
                                ),
                            }),
                            sort_keys=True, allow_nan=False,
                        ),
                        "constraint_config_json": json.dumps(
                            _json_safe({**job.params, "decision_snapshot": decision_snapshot}),
                            sort_keys=True, allow_nan=False,
                        ),
                        "data_cutoff_at": job.data_cutoff_at,
                        "created_at": job.created_at.replace(tzinfo=job.created_at.tzinfo or timezone.utc),
                        "updated_at": job.updated_at.replace(tzinfo=job.updated_at.tzinfo or timezone.utc),
                        "status": job.status,
                        "message": job.message,
                    },
                )
                connection.execute(
                    text(
                        "DELETE FROM target.lineup WHERE optimizer_run_id = :optimizer_run_id"
                    ),
                    {"optimizer_run_id": job.job_id},
                )
                classic_report = runtime.get("classic_small_field") or {}
                frozen = classic_report.get("frozen_solver_snapshot") or runtime.get("classic_run_input_snapshot")
                experiment = classic_report.get("prospective_experiment")
                if frozen:
                    submitted_experiment = experiment
                    from .classic_prospective import (
                        guard_prelock_persistence, validate_classic_run_input,
                        validate_solver_snapshot,
                    )

                    if frozen["contract"] == "classic_solver_snapshot_v2":
                        validate_solver_snapshot(frozen)
                    else:
                        validate_classic_run_input(frozen)
                    persisted_experiment = guard_prelock_persistence(
                        experiment,
                        (classic_report.get("prelock_timing") or {}).get("first_saved_kickoff_at"),
                        connection.execute(text("SELECT clock_timestamp()")).scalar_one(),
                        frozen["sha256"],
                    )
                    if persisted_experiment != experiment:
                        classic_report["prospective_experiment"] = persisted_experiment
                        experiment = persisted_experiment
                        connection.execute(text("""
                            UPDATE target.optimizer_run
                            SET constraint_config_json = CAST(:constraint_config_json AS JSONB)
                            WHERE optimizer_run_id = :run_id
                        """), {"run_id": job.job_id,
                               "constraint_config_json": json.dumps(
                                   _json_safe({**job.params, "decision_snapshot": decision_snapshot}),
                                   sort_keys=True, allow_nan=False)})
                    connection.execute(text("""
                        INSERT INTO target.classic_prospective_experiment
                            (optimizer_run_id, solver_snapshot_sha256, solver_snapshot_json,
                             experiment_sha256, prelock_experiment_json)
                        VALUES (:run_id, :snapshot_sha256, CAST(:snapshot AS JSONB),
                                :experiment_sha256, CAST(:experiment AS JSONB))
                        ON CONFLICT (optimizer_run_id) DO NOTHING
                    """), {"run_id": job.job_id, "snapshot_sha256": frozen["sha256"],
                           "snapshot": json.dumps(frozen, sort_keys=True, allow_nan=False),
                           "experiment_sha256": experiment.get("sha256") if experiment else None,
                           "experiment": json.dumps(experiment, sort_keys=True, allow_nan=False)
                           if experiment else None})
                    stored = connection.execute(text("""
                        SELECT solver_snapshot_sha256, experiment_sha256
                        FROM target.classic_prospective_experiment
                        WHERE optimizer_run_id = :run_id
                    """), {"run_id": job.job_id}).mappings().one()
                    if (persisted_experiment != submitted_experiment and
                            submitted_experiment and
                            stored["solver_snapshot_sha256"] == frozen["sha256"] and
                            stored["experiment_sha256"] == submitted_experiment.get("sha256")):
                        # A retry after kickoff retains the three arms frozen on the first write.
                        classic_report["prospective_experiment"] = submitted_experiment
                        experiment = submitted_experiment
                        connection.execute(text("""
                            UPDATE target.optimizer_run
                            SET constraint_config_json = CAST(:constraint_config_json AS JSONB)
                            WHERE optimizer_run_id = :run_id
                        """), {"run_id": job.job_id,
                               "constraint_config_json": json.dumps(
                                   _json_safe({**job.params, "decision_snapshot": decision_snapshot}),
                                   sort_keys=True, allow_nan=False)})
                    if (stored["solver_snapshot_sha256"] != frozen["sha256"] or
                            stored["experiment_sha256"] != (experiment.get("sha256") if experiment else None)):
                        raise ValueError("Classic pre-lock snapshot differs from already frozen run")
                for lineup_number, lineup in enumerate(job.results or [], start=1):
                    lineup_id = f"{job.job_id}:{lineup_number}"
                    cash_summary = {}
                    if job.strategy == CLASSIC_HEAD_TO_HEAD_STRATEGY_ID:
                        cash_summary = summarize_head_to_head_lineup(lineup)
                    elif job.contest_format == "classic" and job.objective == "cash":
                        cash_summary = summarize_classic_cash_lineup(lineup)
                    salary_used = sum(_safe_float(row.get("salary")) for row in lineup)
                    projected_mean = sum(
                        _safe_float(row.get("projection", row.get("predicted_mean")))
                        for row in lineup
                    )
                    projected_p90 = sum(
                        _safe_float(row.get("p90", row.get("predicted_p90")))
                        for row in lineup
                    )
                    ownership_sum = sum(
                        _safe_float(row.get("ownership", row.get("projected_ownership")))
                        for row in lineup
                    )
                    leverage_score = sum(_safe_float(row.get("leverage")) for row in lineup)
                    if job.contest_format == "showdown" and any(
                        row.get("ownership") is None for row in lineup
                    ):
                        ownership_sum = None
                        leverage_score = None
                    objective_score = cash_summary.get("objective_score")
                    if job.contest_format == "showdown":
                        objective_score = sum(
                            _safe_float(row.get("objective_score")) for row in lineup
                        )
                    connection.execute(
                        text(
                            """
                            INSERT INTO target.lineup
                                (lineup_id, optimizer_run_id, lineup_number, salary_used,
                                 projected_mean, projected_median, projected_floor, projected_p90,
                                 objective_score, average_role_certainty, fragility_penalty,
                                 ownership_sum, leverage_score, created_at)
                            VALUES
                                (:lineup_id, :optimizer_run_id, :lineup_number, :salary_used,
                                 :projected_mean, :projected_median, :projected_floor, :projected_p90,
                                 :objective_score, :average_role_certainty, :fragility_penalty,
                                 :ownership_sum, :leverage_score, :created_at)
                            """
                        ),
                        {
                            "lineup_id": lineup_id,
                            "optimizer_run_id": job.job_id,
                            "lineup_number": lineup_number,
                            "salary_used": salary_used,
                            "projected_mean": projected_mean,
                            "projected_median": cash_summary.get("projected_median"),
                            "projected_floor": cash_summary.get("projected_floor_p10"),
                            "projected_p90": projected_p90,
                            "objective_score": objective_score,
                            "average_role_certainty": cash_summary.get("average_role_certainty"),
                            "fragility_penalty": cash_summary.get("total_fragility_penalty"),
                            "ownership_sum": ownership_sum,
                            "leverage_score": leverage_score,
                            "created_at": job.created_at,
                        },
                    )
                    player_rows = []
                    for slot_index, row in enumerate(lineup):
                        roster_position = str(
                            row.get("roster_position") or row.get("position") or ""
                        ).upper()
                        player_payload = dict(row)
                        player_payload["lineup_slot_index"] = slot_index
                        player_payload["roster_position"] = roster_position
                        player_rows.append(
                            {
                                "lineup_id": lineup_id,
                                "slot_index": slot_index,
                                "player_id": str(row.get("player_id") or row.get("dk_player_id") or ""),
                                "roster_position": roster_position,
                                "salary": _safe_float(row.get("salary")),
                                "projection": _safe_float(
                                    row.get("projection", row.get("predicted_mean"))
                                ),
                                "projected_p90": _safe_float(
                                    row.get("p90", row.get("predicted_p90"))
                                ),
                                "ownership_projection": (
                                    None if job.contest_format == "showdown" and row.get("ownership") is None
                                    else _safe_float(row.get("ownership", row.get("projected_ownership")))
                                ),
                                "player_json": json.dumps(
                                    _json_safe(player_payload),
                                    sort_keys=True,
                                    allow_nan=False,
                                ),
                            }
                        )
                    if player_rows:
                        connection.execute(
                            text(
                                """
                                INSERT INTO target.lineup_player
                                    (lineup_id, slot_index, player_id, roster_position, salary,
                                     projection, projected_p90, ownership_projection, player_json)
                                VALUES
                                    (:lineup_id, :slot_index, :player_id, :roster_position, :salary,
                                     :projection, :projected_p90, :ownership_projection,
                                     CAST(:player_json AS JSONB))
                                """
                            ),
                            player_rows,
                        )
                    connection.execute(
                        text(
                            """
                            INSERT INTO target.lineup_constraint_explanation
                                (lineup_id, constraint_name, constraint_status, explanation_json)
                            VALUES
                                (:lineup_id, 'optimizer_configuration', 'applied',
                                 CAST(:explanation_json AS JSONB))
                            """
                        ),
                        {
                            "lineup_id": lineup_id,
                            "explanation_json": json.dumps(
                                _json_safe(
                                    {
                                        "contest_format": job.contest_format,
                                        "objective": job.objective,
                                        "strategy": job.strategy,
                                        "params": job.params,
                                    }
                                ),
                                sort_keys=True,
                                allow_nan=False,
                            ),
                        },
                    )
                    strategy_config = job.params.get("strategy_config")
                    if isinstance(strategy_config, dict):
                        connection.execute(
                            text(
                                """
                                INSERT INTO target.lineup_constraint_explanation
                                    (lineup_id, constraint_name, constraint_status, explanation_json)
                                VALUES
                                    (:lineup_id, 'optimizer_strategy', 'applied',
                                     CAST(:explanation_json AS JSONB))
                                """
                            ),
                            {
                                "lineup_id": lineup_id,
                                "explanation_json": json.dumps(
                                    _json_safe(
                                        {
                                            "config": strategy_config,
                                            "runtime": job.params.get(
                                                "strategy_runtime", {}
                                            ),
                                        }
                                    ),
                                    sort_keys=True,
                                    allow_nan=False,
                                ),
                            },
                        )
                    stack_policy = job.params.get("stack_policy")
                    if isinstance(stack_policy, dict):
                        connection.execute(
                            text(
                                """
                                INSERT INTO target.lineup_constraint_explanation
                                    (lineup_id, constraint_name, constraint_status, explanation_json)
                                VALUES
                                    (:lineup_id, 'stack_policy', :constraint_status,
                                     CAST(:explanation_json AS JSONB))
                                """
                            ),
                            {
                                "lineup_id": lineup_id,
                                "constraint_status": (
                                    "applied" if stack_policy.get("enabled") else "baseline"
                                ),
                                "explanation_json": json.dumps(
                                    _json_safe(stack_policy),
                                    sort_keys=True,
                                    allow_nan=False,
                                ),
                            },
                        )
                    if cash_summary:
                        connection.execute(
                            text(
                                """
                                INSERT INTO target.lineup_constraint_explanation
                                    (lineup_id, constraint_name, constraint_status, explanation_json)
                                VALUES
                                    (:lineup_id, 'cash_objective', 'applied',
                                     CAST(:explanation_json AS JSONB))
                                """
                            ),
                            {
                                "lineup_id": lineup_id,
                                "explanation_json": json.dumps(
                                    _json_safe(
                                        {
                                            "config": job.params.get("objective_config", {}),
                                            "summary": cash_summary,
                                        }
                                    ),
                                    sort_keys=True,
                                    allow_nan=False,
                                ),
                            },
                        )
                if job.status == "completed":
                    from .evaluation_record import capture_run
                    capture_run(connection, job.job_id)
            return True
        except Exception as exc:  # noqa: BLE001 - report optimization even if lineage persistence is unavailable
            logger.warning("Failed to persist target optimizer run %s: %s", job.job_id, exc)
            return False

    def _load_persisted_job(self, job_id: str) -> OptimizerJob | None:
        """Reload a completed or failed optimizer execution after process restart."""
        try:
            with self.engine.begin() as connection:
                run_row = connection.execute(
                    text(
                        "SELECT * FROM target.optimizer_run "
                        "WHERE optimizer_run_id = :optimizer_run_id"
                    ),
                    {"optimizer_run_id": job_id},
                ).mappings().first()
                if not run_row:
                    return None
                lineup_rows = connection.execute(
                    text(
                        "SELECT lineup_id, lineup_number FROM target.lineup "
                        "WHERE optimizer_run_id = :optimizer_run_id ORDER BY lineup_number"
                    ),
                    {"optimizer_run_id": job_id},
                ).mappings().all()
                results: list[list[dict]] = []
                for lineup_row in lineup_rows:
                    player_rows = connection.execute(
                        text(
                            "SELECT slot_index, roster_position, player_json "
                            "FROM target.lineup_player "
                            "WHERE lineup_id = :lineup_id ORDER BY slot_index"
                        ),
                        {"lineup_id": lineup_row["lineup_id"]},
                    ).mappings().all()
                    lineup = []
                    for player_row in player_rows:
                        payload = player_row.get("player_json") or {}
                        if isinstance(payload, str):
                            payload = json.loads(payload)
                        player = dict(payload)
                        player["lineup_slot_index"] = int(
                            player_row.get("slot_index") or 0
                        )
                        if player_row.get("roster_position"):
                            player["roster_position"] = str(
                                player_row["roster_position"]
                            ).upper()
                        lineup.append(player)
                    results.append(lineup)

            params = run_row.get("constraint_config_json") or {}
            if isinstance(params, str):
                params = json.loads(params)
            job = OptimizerJob(
                job_id=str(run_row["optimizer_run_id"]),
                status=str(run_row["status"]),
                created_at=run_row["created_at"],
                updated_at=run_row["updated_at"],
                season=int(run_row["season"]),
                week=int(run_row["week"]),
                slate=str(run_row.get("slate_id") or ""),
                strategy=str(run_row["strategy"]),
                contest_format=str(run_row["contest_format"]),
                objective=str(run_row["objective"]),
                params=dict(params),
                projection_run_id=run_row.get("projection_run_id"),
                rule_run_id=run_row.get("rule_run_id"),
                data_cutoff_at=run_row.get("data_cutoff_at"),
                lineage_persisted=True,
                results=results if str(run_row["status"]) == "completed" else None,
                message=run_row.get("message"),
            )
            self._cache_job(job)
            return job
        except Exception as exc:  # noqa: BLE001 - older databases may not have target optimizer tables
            logger.info("Persisted optimizer run %s is unavailable: %s", job_id, exc)
            return None

    @staticmethod
    def _gpp_player_to_dict(player: GPPPlayer) -> dict:
        return {
            "player_id": player.player_id,
            "name": player.name,
            "player_name": player.name,
            "player_display_name": player.name,
            "team": player.team,
            "player_team": player.team,
            "opponent_team": player.opponent,
            "roster_position": player.position,
            "position": player.position,
            "salary": player.salary,
            "projection": player.projection,
            "predicted_mean": player.projection,
            "predicted_p90": player.ceiling,
            "p90": player.ceiling,
            "ownership": player.ownership,
            "optimal_lineup_probability": player.optimal_lineup_probability,
            "leverage": player.leverage,
            "optimizer_context_adjustment": player.optimizer_context_adjustment,
            "optimizer_context_rule_evaluation": (
                player.optimizer_context_rule_evaluation
            ),
            "game_id": player.game_id,
            "game_total_line": player.game_total,
            "team_spread_line": player.spread,
            "team_implied_total": player.team_total,
            "market_context_point_in_time_safe": (
                player.market_context_point_in_time_safe
            ),
            "optimizer_receiving_role_strength": (
                player.optimizer_receiving_role_strength
            ),
            "optimizer_rushing_role_strength": (
                player.optimizer_rushing_role_strength
            ),
            "tags": list(player.tags),
        }

    @staticmethod
    def _gpp_players_from_pool(pool: pd.DataFrame) -> list[GPPPlayer]:
        """Adapt the exact live optimizer pool without reloading or rematching players."""
        players: list[GPPPlayer] = []
        for row in pool.to_dict(orient="records"):
            projection = _safe_float(row.get("projection", row.get("predicted_mean")))
            ceiling = _safe_float(
                row.get("p90", row.get("predicted_p90", projection))
            )
            optimal_raw = row.get("optimal_lineup_probability")
            optimal_probability = (
                None
                if optimal_raw is None or pd.isna(optimal_raw)
                else _safe_float(optimal_raw)
            )
            market_context_raw = row.get("market_context_point_in_time_safe")
            market_context_safe = (
                None
                if market_context_raw is None or pd.isna(market_context_raw)
                else (
                    market_context_raw
                    if isinstance(market_context_raw, bool)
                    else str(market_context_raw).strip().lower()
                    in {"1", "true", "t", "yes", "y"}
                )
            )
            players.append(
                GPPPlayer(
                    player_id=str(row.get("player_id") or ""),
                    name=str(
                        row.get("name")
                        or row.get("player_name")
                        or row.get("player_display_name")
                        or row.get("player_id")
                        or ""
                    ),
                    team=str(
                        row.get("player_team") or row.get("team") or ""
                    ).upper(),
                    opponent=str(
                        row.get("opponent_team") or row.get("opponent") or ""
                    ).upper(),
                    position=str(
                        row.get("position") or row.get("roster_position") or ""
                    ).upper(),
                    salary=int(_safe_float(row.get("salary"))),
                    projection=projection,
                    ceiling=ceiling,
                    ownership=(
                        None if pd.isna(row.get("ownership", row.get("projected_ownership")))
                        else _safe_float(row.get("ownership", row.get("projected_ownership")))
                    ),
                    optimal_lineup_probability=optimal_probability,
                    game_id=(
                        str(row.get("game_id") or row.get("game_info"))
                        if row.get("game_id") or row.get("game_info")
                        else None
                    ),
                    spread=(_optional_market_float(row.get("team_spread_line", row.get("spread")))
                            if market_context_safe is True else None),
                    game_total=(_optional_market_float(row.get("game_total_line", row.get("game_total")))
                                if market_context_safe is True else None),
                    team_total=(_optional_market_float(row.get("team_implied_total", row.get("team_total")))
                                if market_context_safe is True else None),
                    market_context_point_in_time_safe=market_context_safe,
                    optimizer_context_adjustment=_safe_float(
                        row.get("optimizer_context_adjustment")
                    ),
                    optimizer_context_rule_evaluation=(
                        row.get("optimizer_context_rule_evaluation")
                        if isinstance(
                            row.get("optimizer_context_rule_evaluation"), dict
                        )
                        else None
                    ),
                    optimizer_receiving_role_strength=_safe_float(
                        row.get("optimizer_receiving_role_strength")
                    ),
                    optimizer_rushing_role_strength=_safe_float(
                        row.get("optimizer_rushing_role_strength")
                    ),
                )
            )
        return players

    def _load_symbolic_explanations(self, season: int, week: int, slate: str) -> dict[str, list[dict]]:
        """Return recent symbolic adjustment traces keyed by player_id."""
        try:
            with self.engine.begin() as connection:
                rows = pd.read_sql(
                    text(
                        """
                        SELECT DISTINCT ON (sa.player_id, sa.rule_id)
                            sa.player_id,
                            sa.rule_run_id,
                            sa.rule_id,
                            sa.rule_name,
                            sa.reason,
                            sa.mean_before,
                            sa.mean_after,
                            sa.p90_before,
                            sa.p90_after,
                            sa.delta_mean,
                            sa.delta_p90,
                            rr.created_at
                        FROM symbolic_adjustments sa
                        LEFT JOIN symbolic_rule_runs rr
                            ON rr.rule_run_id = sa.rule_run_id
                        WHERE sa.season = :season
                          AND sa.week = :week
                          AND (sa.slate = :slate OR sa.slate IS NULL)
                        ORDER BY sa.player_id, sa.rule_id, rr.created_at DESC NULLS LAST
                        """
                    ),
                    connection,
                    params={"season": season, "week": week, "slate": slate},
                )
        except Exception:
            return {}

        explanations: dict[str, list[dict]] = {}
        for row in rows.to_dict(orient="records"):
            player_id = str(row.get("player_id"))
            explanations.setdefault(player_id, []).append(
                {
                    "rule_run_id": row.get("rule_run_id"),
                    "rule_id": row.get("rule_id"),
                    "rule_name": row.get("rule_name"),
                    "reason": row.get("reason"),
                    "mean_before": row.get("mean_before"),
                    "mean_after": row.get("mean_after"),
                    "p90_before": row.get("p90_before"),
                    "p90_after": row.get("p90_after"),
                    "delta_mean": row.get("delta_mean"),
                    "delta_p90": row.get("delta_p90"),
                }
            )
        return explanations

    def _attach_symbolic_explanations(
        self,
        lineups: list[list[dict]],
        season: int,
        week: int,
        slate: str,
    ) -> None:
        explanation_map = self._load_symbolic_explanations(season=season, week=week, slate=slate)
        if not explanation_map:
            return
        for lineup in lineups:
            for row in lineup:
                player_id = str(row.get("player_id"))
                notes = explanation_map.get(player_id, [])
                row["symbolic_explanations"] = notes
                row["symbolic_adjusted"] = bool(notes)
                if notes:
                    row["symbolic_rule_summary"] = ", ".join(
                        str(note.get("rule_id")) for note in notes if note.get("rule_id")
                    )

    @staticmethod
    def _parse_game_info_opponent(game_info: str, player_team: str | None) -> str | None:
        """
        Extract opponent from DK game_info (e.g., 'GB@DET' or 'GB @ DET').
        """
        if not game_info:
            return None
        cleaned = game_info.replace(" ", "").upper()
        if "@" not in cleaned:
            return None
        left, right = cleaned.split("@", 1)
        player_team = (player_team or "").upper()
        if player_team == left:
            return right
        if player_team == right:
            return left
        # Fallback: return right side
        return right

    def _load_target_player_pool(
        self,
        season: int,
        week: int,
        slate: str,
        projection_run_id: str | None = None,
        ownership_run_id: str | None = None,
        evidence_cutoff_at: datetime | None = None,
        require_explicit_runs: bool = False,
    ) -> pd.DataFrame:
        """Load one exact target-schema salary/projection contract."""
        inspector = inspect(self.engine)
        has_curated_salary = inspector.has_table("curated_salary")
        has_target_salary = inspector.has_table("snapshot_salary", schema="target")
        if not (
            (has_curated_salary or has_target_salary)
            and inspector.has_table("player_projection", schema="target")
            and inspector.has_table("dim_player", schema="target")
        ):
            return pd.DataFrame()
        identity_join = ""
        identity_resolved = "d.player_id IS NOT NULL"
        if (has_curated_salary and evidence_cutoff_at is not None
                and inspector.has_table("player_master", schema="public")):
            # A missing derived dimension is not an unresolved canonical UUID.
            # Validate the source-of-truth entity directly for live evidence.
            identity_join = "LEFT JOIN public.player_master canonical_player ON canonical_player.player_master_id::TEXT = s.player_id"
            identity_resolved = "canonical_player.player_master_id IS NOT NULL"
        if has_curated_salary:
            salary_snapshot_join = ""
            salary_clock = "salary.created_at AT TIME ZONE 'UTC'"
            salary_snapshot_id = "NULL::TEXT"
            if inspector.has_table("source_snapshot", schema="public") and inspector.has_table("source_snapshot_ingest_run", schema="public"):
                salary_snapshot_join = """
                    LEFT JOIN LATERAL (
                        SELECT evidence.snapshot_id, evidence.observed_at
                        FROM public.source_snapshot_ingest_run link
                        JOIN public.source_snapshot evidence ON evidence.snapshot_id = link.snapshot_id
                        WHERE link.ingest_run_id = salary.ingest_run_id
                          AND evidence.content_sha256 = ingest.source_checksum
                        ORDER BY evidence.captured_at, evidence.snapshot_id
                        LIMIT 1
                    ) salary_snapshot ON TRUE
                """
                salary_clock = "COALESCE(salary_snapshot.observed_at, salary.created_at AT TIME ZONE 'UTC')"
                salary_snapshot_id = "salary_snapshot.snapshot_id::TEXT"
            native_key = "salary.player_master_id" if evidence_cutoff_at is None else "COALESCE(salary.player_master_id, 'unresolved:' || COALESCE(salary.source_player_key, salary.curated_salary_id::TEXT))"
            resolved_filter = "AND salary.player_master_id IS NOT NULL" if evidence_cutoff_at is None else "AND salary.source_system='draftkings' AND salary.created_at AT TIME ZONE 'UTC' <= :evidence_cutoff_at"
            salary_cte = f"""
                latest_salary AS (
                    SELECT DISTINCT ON ({native_key})
                        salary.player_master_id AS player_id,
                        salary.source_player_key AS site_player_id,
                        captain.source_player_key AS captain_site_player_id,
                        salary.player_name AS salary_name,
                        salary.curated_salary_id::TEXT AS salary_source_row_id,
                        salary.ingest_run_id::TEXT AS salary_ingest_run_id,
                        salary.source_system AS salary_source_system,
                        ingest.source_path AS salary_source_path,
                        ingest.source_checksum AS salary_source_checksum,
                        {salary_clock} AS salary_source_observed_at,
                        {salary_snapshot_id} AS salary_source_snapshot_id,
                        salary.salary,
                        COALESCE(
                            NULLIF(salary.position, ''),
                            salary.roster_position
                        ) AS salary_position,
                        salary.player_status,
                        salary.team AS team_id,
                        salary.opponent AS opponent_team_id,
                        salary.game_info AS game_id
                    FROM public.curated_salary salary
                    LEFT JOIN public.ingest_run ingest ON ingest.ingest_run_id = salary.ingest_run_id
                    {salary_snapshot_join}
                    LEFT JOIN LATERAL (
                        SELECT role.source_player_key
                        FROM public.curated_salary role
                        WHERE role.season = salary.season
                          AND role.week = salary.week
                          AND UPPER(role.slate) = UPPER(salary.slate)
                          AND role.player_master_id = salary.player_master_id
                          AND UPPER(role.roster_position) = 'CPT'
                        ORDER BY role.created_at DESC, role.curated_salary_id DESC
                        LIMIT 1
                    ) captain ON TRUE
                    WHERE salary.season = :season AND salary.week = :week
                      AND UPPER(salary.slate) = UPPER(:slate)
                      {resolved_filter}
                    ORDER BY {native_key},
                        CASE WHEN UPPER(salary.roster_position) = 'FLEX' THEN 0 ELSE 1 END,
                        salary.created_at DESC,
                        salary.curated_salary_id DESC
                )
            """
        else:
            salary_cte = f"""
                latest_salary AS (
                    SELECT DISTINCT ON (salary.player_id)
                        salary.player_id,
                        salary.site_player_id,
                        captain.site_player_id AS captain_site_player_id,
                        NULL::TEXT AS salary_name,
                        salary.snapshot_salary_id::TEXT AS salary_source_row_id,
                        NULL::TEXT AS salary_ingest_run_id,
                        salary.source AS salary_source_system,
                        NULL::TEXT AS salary_source_path,
                        NULL::TEXT AS salary_source_checksum,
                        salary.as_of AS salary_source_observed_at,
                        NULL::TEXT AS salary_source_snapshot_id,
                        salary.salary,
                        salary.roster_position AS salary_position,
                        salary.player_status,
                        salary.team_id,
                        salary.opponent_team_id,
                        salary.game_id
                    FROM target.snapshot_salary salary
                    LEFT JOIN LATERAL (
                        SELECT role.site_player_id
                        FROM target.snapshot_salary role
                        WHERE role.season = salary.season
                          AND role.week = salary.week
                          AND UPPER(COALESCE(role.slate, role.slate_id)) =
                              UPPER(COALESCE(salary.slate, salary.slate_id))
                          AND role.player_id = salary.player_id
                          AND UPPER(role.roster_position) = 'CPT'
                        ORDER BY role.as_of DESC, role.snapshot_salary_id DESC
                        LIMIT 1
                    ) captain ON TRUE
                    WHERE salary.season = :season AND salary.week = :week
                      AND UPPER(COALESCE(salary.slate, salary.slate_id)) = UPPER(:slate)
                    ORDER BY salary.player_id,
                        CASE WHEN UPPER(salary.roster_position) = 'FLEX' THEN 0 ELSE 1 END,
                        salary.as_of DESC,
                        salary.snapshot_salary_id DESC
                )
            """
        projection_columns = {
            column["name"]
            for column in inspector.get_columns("player_projection", schema="target")
        }
        calibration_select = {
            "calibration_method": "p.calibration_method" if "calibration_method" in projection_columns else "'target_projection_fallback'",
            "calibration_position": "p.calibration_position" if "calibration_position" in projection_columns else "d.primary_position",
            "calibration_role": "p.calibration_role" if "calibration_role" in projection_columns else "'unknown'",
            "calibration_sample_size": "p.calibration_sample_size" if "calibration_sample_size" in projection_columns else "0",
        }
        has_injuries = inspector.has_table("snapshot_injury_status", schema="target")
        has_roster_participation = inspector.has_table(
            "curated_player_game_participation",
            schema="public",
        )
        has_feature_matrix = inspector.has_table(
            "player_game_feature_matrix",
            schema="public",
        )
        has_starting_qbs = inspector.has_table(
            "starting_qb_evidence", schema="public"
        )
        has_projection_features = inspector.has_table(
            "feature_player_game", schema="target"
        ) and inspector.has_table("model_run", schema="target")
        has_ownership = inspector.has_table("ownership_projection", schema="target")
        position_source = (
            "COALESCE("
            "NULLIF(CASE WHEN UPPER(COALESCE(s.salary_position, '')) "
            "IN ('FLEX', 'CPT') THEN '' ELSE s.salary_position END, ''), "
            "d.primary_position)"
        )
        injury_join = ""
        injury_status_select = "NULL::TEXT AS injury_status, NULL::TIMESTAMPTZ AS injury_observed_at"
        filters: list[str] = []
        if has_injuries:
            cutoff_predicate = injury_snapshot_cutoff_sql(
                injury_alias="injury",
                projection_alias="p",
            )
            injury_join = f"""
                LEFT JOIN LATERAL (
                    SELECT injury.injury_status, injury.as_of
                    FROM target.snapshot_injury_status injury
                    WHERE injury.season = :season AND injury.week = :week
                      AND injury.player_id = s.player_id
                      AND (injury.slate IS NULL OR {injury_slate_sql('injury.slate')})
                      AND {cutoff_predicate}
                    ORDER BY injury.as_of DESC
                    LIMIT 1
                ) i ON TRUE
            """
            injury_status_select = "i.injury_status, i.as_of AS injury_observed_at"
        roster_join = ""
        roster_status_select = "NULL::TEXT AS roster_status"
        roster_evidence_select = "FALSE AS roster_evidence_available"
        depth_chart_join = ""
        depth_chart_select = "NULL::TEXT AS depth_chart_position"
        if inspector.has_table("raw_nfl_weekly_roster", schema="public") and inspector.has_table("player_alias", schema="public"):
            depth_chart_select = "roster_depth.depth_chart_position AS depth_chart_position"
            depth_chart_join = f"""
                LEFT JOIN LATERAL (
                    SELECT raw_roster.depth_chart_position
                    FROM public.player_alias alias
                    JOIN public.raw_nfl_weekly_roster raw_roster
                      ON raw_roster.gsis_id = alias.source_key
                     AND raw_roster.source_system = alias.source_system
                    WHERE alias.player_master_id = s.player_id
                      AND alias.source_system = 'nflreadpy'
                      AND raw_roster.season = :season
                      AND raw_roster.week = :week
                      AND {canonical_team_sql('raw_roster.team')} =
                          {canonical_team_sql('s.team_id')}
                      AND (p.data_cutoff_at IS NULL OR raw_roster.created_at <= p.data_cutoff_at)
                    ORDER BY raw_roster.created_at DESC, raw_roster.raw_nfl_weekly_roster_id DESC
                    LIMIT 1
                ) roster_depth ON TRUE
            """
        if has_roster_participation:
            roster_status_select = "participation.roster_status"
            roster_evidence_select = f"""
                EXISTS (
                    SELECT 1
                    FROM public.curated_player_game_participation roster_evidence
                    WHERE roster_evidence.season = :season
                      AND roster_evidence.week = :week
                      AND {canonical_team_sql('roster_evidence.team')} =
                          {canonical_team_sql('s.team_id')}
                      AND (
                          p.data_cutoff_at IS NULL
                          OR roster_evidence.created_at AT TIME ZONE 'UTC' <= p.data_cutoff_at
                      )
                ) AS roster_evidence_available
            """
            roster_join = f"""
                LEFT JOIN LATERAL (
                    SELECT roster_row.roster_status
                    FROM public.curated_player_game_participation roster_row
                    WHERE roster_row.season = :season
                      AND roster_row.week = :week
                      AND roster_row.player_master_id = s.player_id
                      AND {canonical_team_sql('roster_row.team')} =
                          {canonical_team_sql('s.team_id')}
                      AND (
                          p.data_cutoff_at IS NULL
                          OR roster_row.created_at AT TIME ZONE 'UTC' <= p.data_cutoff_at
                      )
                    ORDER BY roster_row.created_at DESC,
                        roster_row.curated_player_game_participation_id DESC
                    LIMIT 1
                ) participation ON TRUE
            """
        feature_join = ""
        feature_select = """
                NULL::DOUBLE PRECISION AS game_total_line,
                NULL::DOUBLE PRECISION AS team_spread_line,
                NULL::DOUBLE PRECISION AS team_implied_total,
                FALSE AS market_context_point_in_time_safe,
        """
        if has_feature_matrix:
            feature_select = """
                feature.game_total_line,
                feature.team_spread_line,
                feature.team_implied_total,
                FALSE AS market_context_point_in_time_safe,
            """
            feature_join = """
                LEFT JOIN LATERAL (
                    SELECT
                        matrix.game_total_line,
                        matrix.team_spread_line,
                        matrix.team_implied_total
                    FROM public.player_game_feature_matrix matrix
                    WHERE matrix.season = :season
                      AND matrix.week = :week
                      AND matrix.player_master_id = s.player_id
                      AND (
                          matrix.slate IS NULL
                          OR UPPER(matrix.slate) = UPPER(:slate)
                      )
                    ORDER BY matrix.created_at DESC,
                        matrix.player_game_feature_matrix_id DESC
                    LIMIT 1
                ) feature ON TRUE
            """
        starter_join = ""
        starter_select = """
                FALSE AS is_starting_qb,
                NULL::TEXT AS starting_qb_source,
                NULL::TEXT AS starting_qb_evidence_tier,
                NULL::TIMESTAMPTZ AS starting_qb_observed_at,
        """
        if has_starting_qbs:
            starter_select = """
                (starter.player_master_id IS NOT NULL) AS is_starting_qb,
                starter.source AS starting_qb_source,
                starter.evidence_tier AS starting_qb_evidence_tier,
                NULLIF(starter.evidence_json ->> 'observed_at', '')::TIMESTAMPTZ AS starting_qb_observed_at,
            """
            starter_join = f"""
                LEFT JOIN public.starting_qb_evidence starter
                  ON starter.season = :season
                 AND starter.week = :week
                 AND UPPER(starter.slate) = UPPER(:slate)
                 AND starter.player_master_id = s.player_id
                 AND {canonical_team_sql('starter.team')} =
                     {canonical_team_sql('s.team_id')}
                 AND UPPER(starter.status) = 'ACTIVE'
            """
        pregame_select = """
                NULL::DOUBLE PRECISION AS pregame_availability_probability,
                NULL::DOUBLE PRECISION AS pregame_start_probability,
                NULL::DOUBLE PRECISION AS pregame_carry_share,
                NULL::DOUBLE PRECISION AS pregame_target_share,
                NULL::TEXT AS pregame_role_label,
                NULL::TEXT AS pregame_injury_status,
                NULL::TEXT AS practice_participation,
                NULL::TEXT AS practice_trend,
                NULL::TIMESTAMPTZ AS practice_observed_at,
                NULL::TEXT AS expected_workload_status,
                NULL::TIMESTAMPTZ AS expected_workload_observed_at,
                NULL::TEXT AS pregame_context_run_id,
                NULL::TEXT AS pregame_context_source,
                NULL::TIMESTAMPTZ AS pregame_context_observed_at,
                NULL::DOUBLE PRECISION AS pregame_expected_snaps,
                NULL::DOUBLE PRECISION AS pregame_expected_routes,
                NULL::DOUBLE PRECISION AS pregame_expected_carries,
                NULL::DOUBLE PRECISION AS pregame_expected_targets,
                NULL::DOUBLE PRECISION AS pregame_red_zone_share,
                NULL::DOUBLE PRECISION AS pregame_goal_line_share,
                NULL::DOUBLE PRECISION AS carries_mean_3,
                NULL::DOUBLE PRECISION AS targets_mean_3,
                NULL::DOUBLE PRECISION AS snap_share_mean_3,
                NULL::DOUBLE PRECISION AS target_share_mean_3,
                NULL::DOUBLE PRECISION AS team_targets_mean_3,
                NULL::BOOLEAN AS team_targets_mean_3_available,
                NULL::DOUBLE PRECISION AS team_carries_mean_3,
                NULL::BOOLEAN AS team_carries_mean_3_available,
                NULL::DOUBLE PRECISION AS carry_share_mean_3,
                NULL::DOUBLE PRECISION AS projected_targets,
                NULL::DOUBLE PRECISION AS projected_carries,
                NULL::DOUBLE PRECISION AS offensive_role_importance,
                NULL::DOUBLE PRECISION AS offensive_role_completeness,
                NULL::TEXT AS offensive_role_class,
                NULL::TEXT AS offensive_role_confidence,
                NULL::TEXT AS offensive_role_reason,
                NULL::TEXT AS offensive_role_source,
                NULL::JSONB AS role_counterfactual_grid,
                NULL::JSONB AS historical_role_calibration,
                NULL::TEXT AS projection_model_version,
                NULL::TEXT AS projected_opportunity_source,
                NULL::BOOLEAN AS pregame_opportunity_context_applied,
                NULL::DOUBLE PRECISION AS player_roll3_mean,
                NULL::DOUBLE PRECISION AS snap_share_last,
                NULL::DOUBLE PRECISION AS snap_share_prior3,
                NULL::DOUBLE PRECISION AS snap_share_trend,
                NULL::DOUBLE PRECISION AS target_share_last,
                NULL::DOUBLE PRECISION AS target_share_prior3,
                NULL::DOUBLE PRECISION AS target_share_trend,
                NULL::DOUBLE PRECISION AS rush_share_last,
                NULL::DOUBLE PRECISION AS rush_share_prior3,
                NULL::DOUBLE PRECISION AS rush_share_trend,
                NULL::DOUBLE PRECISION AS receptions_mean_3,
                NULL::DOUBLE PRECISION AS receiving_yards_mean_3,
                FALSE AS pregame_role_uncertain,
                FALSE AS pregame_newly_assigned_role,
                FALSE AS pregame_depth_chart_conflict,
                NULL::TEXT AS official_availability_status,
                'default'::TEXT AS availability_override,
                NULL::DOUBLE PRECISION AS model_availability_used,
                FALSE AS opportunity_redistributed,
                NULL::DOUBLE PRECISION AS projection_before_scenario,
                NULL::DOUBLE PRECISION AS projection_after_scenario,
                NULL::TEXT AS market_source_system,
                NULL::TEXT AS market_observed_at,
                NULL::TEXT AS market_snapshot_row_id,
                NULL::TEXT AS team_starting_qb_name,
                NULL::TEXT AS team_starting_qb_player_id,
        """
        pregame_join = ""
        if has_projection_features:
            feature_select = """
                CASE WHEN projection_feature.feature_json ->> 'market_observed_at' IS NOT NULL
                          AND projection_feature.feature_json ->> 'market_source_system' IS NOT NULL
                     THEN NULLIF(projection_feature.feature_json ->> 'game_total_line', '')::DOUBLE PRECISION
                     ELSE NULL END AS game_total_line,
                CASE WHEN projection_feature.feature_json ->> 'market_observed_at' IS NOT NULL
                          AND projection_feature.feature_json ->> 'market_source_system' IS NOT NULL
                     THEN NULLIF(projection_feature.feature_json ->> 'team_spread_line', '')::DOUBLE PRECISION
                     ELSE NULL END AS team_spread_line,
                CASE WHEN projection_feature.feature_json ->> 'market_observed_at' IS NOT NULL
                          AND projection_feature.feature_json ->> 'market_source_system' IS NOT NULL
                     THEN NULLIF(projection_feature.feature_json ->> 'team_implied_total', '')::DOUBLE PRECISION
                     ELSE NULL END AS team_implied_total,
                (projection_feature.feature_json ->> 'market_observed_at' IS NOT NULL
                 AND projection_feature.feature_json ->> 'market_source_system' IS NOT NULL
                 AND NULLIF(projection_feature.feature_json ->> 'game_total_line', '')::DOUBLE PRECISION > 0
                 AND projection_feature.feature_json ->> 'team_spread_line' IS NOT NULL)
                    AS market_context_point_in_time_safe,
            """
            feature_join = ""
            pregame_select = """
                NULLIF(
                    projection_feature.feature_json
                        ->> 'pregame_availability_probability',
                    ''
                )::DOUBLE PRECISION AS pregame_availability_probability,
                NULLIF(projection_feature.feature_json ->> 'pregame_start_probability', '')::DOUBLE PRECISION
                    AS pregame_start_probability,
                NULLIF(projection_feature.feature_json ->> 'pregame_carry_share', '')::DOUBLE PRECISION
                    AS pregame_carry_share,
                NULLIF(projection_feature.feature_json ->> 'pregame_target_share', '')::DOUBLE PRECISION
                    AS pregame_target_share,
                projection_feature.feature_json ->> 'pregame_role_label'
                    AS pregame_role_label,
                projection_feature.feature_json ->> 'pregame_injury_status'
                    AS pregame_injury_status,
                projection_feature.feature_json ->> 'practice_participation'
                    AS practice_participation,
                projection_feature.feature_json ->> 'practice_trend'
                    AS practice_trend,
                NULLIF(projection_feature.feature_json ->> 'practice_observed_at', '')::TIMESTAMPTZ
                    AS practice_observed_at,
                projection_feature.feature_json ->> 'expected_workload_status'
                    AS expected_workload_status,
                NULLIF(projection_feature.feature_json ->> 'expected_workload_observed_at', '')::TIMESTAMPTZ
                    AS expected_workload_observed_at,
                projection_feature.feature_json ->> 'market_source_system'
                    AS market_source_system,
                projection_feature.feature_json ->> 'market_observed_at'
                    AS market_observed_at,
                projection_feature.feature_json ->> 'market_snapshot_row_id'
                    AS market_snapshot_row_id,
                projection_feature.feature_json ->> 'team_starting_qb_name'
                    AS team_starting_qb_name,
                projection_feature.feature_json ->> 'team_starting_qb_player_id'
                    AS team_starting_qb_player_id,
                projection_feature.feature_json
                    ->> 'pregame_context_run_id' AS pregame_context_run_id,
                projection_feature.feature_json
                    ->> 'pregame_context_source' AS pregame_context_source,
                NULLIF(projection_feature.feature_json ->> 'pregame_context_observed_at', '')::TIMESTAMPTZ
                    AS pregame_context_observed_at,
                NULLIF(projection_feature.feature_json ->> 'pregame_expected_snaps', '')::DOUBLE PRECISION
                    AS pregame_expected_snaps,
                NULLIF(projection_feature.feature_json ->> 'pregame_expected_routes', '')::DOUBLE PRECISION
                    AS pregame_expected_routes,
                NULLIF(projection_feature.feature_json ->> 'pregame_expected_carries', '')::DOUBLE PRECISION
                    AS pregame_expected_carries,
                NULLIF(projection_feature.feature_json ->> 'pregame_expected_targets', '')::DOUBLE PRECISION
                    AS pregame_expected_targets,
                NULLIF(projection_feature.feature_json ->> 'pregame_red_zone_share', '')::DOUBLE PRECISION
                    AS pregame_red_zone_share,
                NULLIF(projection_feature.feature_json ->> 'pregame_goal_line_share', '')::DOUBLE PRECISION
                    AS pregame_goal_line_share,
                NULLIF(projection_feature.feature_json ->> 'carries_mean_3', '')::DOUBLE PRECISION
                    AS carries_mean_3,
                NULLIF(projection_feature.feature_json ->> 'targets_mean_3', '')::DOUBLE PRECISION
                    AS targets_mean_3,
                NULLIF(projection_feature.feature_json ->> 'snap_share_mean_3', '')::DOUBLE PRECISION
                    AS snap_share_mean_3,
                NULLIF(projection_feature.feature_json ->> 'target_share_mean_3', '')::DOUBLE PRECISION
                    AS target_share_mean_3,
                NULLIF(projection_feature.feature_json ->> 'team_targets_mean_3', '')::DOUBLE PRECISION
                    AS team_targets_mean_3,
                (projection_feature.feature_json ->> 'team_targets_mean_3_available')::BOOLEAN AS team_targets_mean_3_available,
                NULLIF(projection_feature.feature_json ->> 'team_carries_mean_3', '')::DOUBLE PRECISION
                    AS team_carries_mean_3,
                (projection_feature.feature_json ->> 'team_carries_mean_3_available')::BOOLEAN AS team_carries_mean_3_available,
                NULLIF(projection_feature.feature_json ->> 'carry_share_mean_3', '')::DOUBLE PRECISION
                    AS carry_share_mean_3,
                NULLIF(projection_feature.feature_json ->> 'projected_targets', '')::DOUBLE PRECISION
                    AS projected_targets,
                NULLIF(projection_feature.feature_json ->> 'projected_carries', '')::DOUBLE PRECISION
                    AS projected_carries,
                NULLIF(projection_feature.feature_json ->> 'offensive_role_importance', '')::DOUBLE PRECISION
                    AS offensive_role_importance,
                NULLIF(projection_feature.feature_json ->> 'offensive_role_completeness', '')::DOUBLE PRECISION
                    AS offensive_role_completeness,
                projection_feature.feature_json ->> 'offensive_role_class'
                    AS offensive_role_class,
                projection_feature.feature_json ->> 'offensive_role_confidence'
                    AS offensive_role_confidence,
                projection_feature.feature_json ->> 'offensive_role_reason'
                    AS offensive_role_reason,
                projection_feature.feature_json ->> 'offensive_role_source'
                    AS offensive_role_source,
                projection_feature.feature_json -> 'role_counterfactual_grid'
                    AS role_counterfactual_grid,
                projection_model_run.params_json -> 'calibration' -> 'historical_role_calibration'
                    AS historical_role_calibration,
                projection_registry.model_version AS projection_model_version,
                projection_feature.feature_json ->> 'projected_opportunity_source'
                    AS projected_opportunity_source,
                NULLIF(projection_feature.feature_json ->> 'pregame_opportunity_context_applied', '')::BOOLEAN
                    AS pregame_opportunity_context_applied,
                NULLIF(projection_feature.feature_json ->> 'player_roll3_mean', '')::DOUBLE PRECISION
                    AS player_roll3_mean,
                NULLIF(projection_feature.feature_json ->> 'snap_share_last', '')::DOUBLE PRECISION
                    AS snap_share_last,
                NULLIF(projection_feature.feature_json ->> 'snap_share_prior3', '')::DOUBLE PRECISION
                    AS snap_share_prior3,
                NULLIF(projection_feature.feature_json ->> 'snap_share_trend', '')::DOUBLE PRECISION
                    AS snap_share_trend,
                NULLIF(projection_feature.feature_json ->> 'target_share_last', '')::DOUBLE PRECISION
                    AS target_share_last,
                NULLIF(projection_feature.feature_json ->> 'target_share_prior3', '')::DOUBLE PRECISION
                    AS target_share_prior3,
                NULLIF(projection_feature.feature_json ->> 'target_share_trend', '')::DOUBLE PRECISION
                    AS target_share_trend,
                NULLIF(projection_feature.feature_json ->> 'rush_share_last', '')::DOUBLE PRECISION
                    AS rush_share_last,
                NULLIF(projection_feature.feature_json ->> 'rush_share_prior3', '')::DOUBLE PRECISION
                    AS rush_share_prior3,
                NULLIF(projection_feature.feature_json ->> 'rush_share_trend', '')::DOUBLE PRECISION
                    AS rush_share_trend,
                NULLIF(projection_feature.feature_json ->> 'receptions_mean_3', '')::DOUBLE PRECISION
                    AS receptions_mean_3,
                NULLIF(projection_feature.feature_json ->> 'receiving_yards_mean_3', '')::DOUBLE PRECISION
                    AS receiving_yards_mean_3,
                COALESCE(NULLIF(projection_feature.feature_json ->> 'pregame_role_uncertain', '')::BOOLEAN, FALSE)
                    AS pregame_role_uncertain,
                COALESCE(NULLIF(projection_feature.feature_json ->> 'pregame_newly_assigned_role', '')::BOOLEAN, FALSE)
                    AS pregame_newly_assigned_role,
                COALESCE(NULLIF(projection_feature.feature_json ->> 'pregame_depth_chart_conflict', '')::BOOLEAN, FALSE)
                    AS pregame_depth_chart_conflict,
                projection_feature.feature_json ->> 'official_availability_status'
                    AS official_availability_status,
                COALESCE(projection_feature.feature_json ->> 'availability_override', 'default')
                    AS availability_override,
                NULLIF(projection_feature.feature_json ->> 'model_availability_used', '')::DOUBLE PRECISION
                    AS model_availability_used,
                COALESCE(NULLIF(projection_feature.feature_json ->> 'opportunity_redistributed', '')::BOOLEAN, FALSE)
                    AS opportunity_redistributed,
                NULLIF(projection_feature.feature_json ->> 'projection_before_scenario', '')::DOUBLE PRECISION
                    AS projection_before_scenario,
                NULLIF(projection_feature.feature_json ->> 'projection_after_scenario', '')::DOUBLE PRECISION
                    AS projection_after_scenario,
            """
            pregame_join = """
                LEFT JOIN target.model_run projection_model_run
                  ON projection_model_run.model_run_id = p.model_run_id
                LEFT JOIN target.model_registry projection_registry
                  ON projection_registry.model_id = projection_model_run.model_id
                LEFT JOIN target.feature_player_game projection_feature
                  ON projection_feature.feature_run_id =
                        projection_model_run.feature_run_id
                 AND projection_feature.season = p.season
                 AND projection_feature.week = p.week
                 AND projection_feature.game_id = p.game_id
                 AND projection_feature.player_id = p.player_id
            """
            pregame_select += "(projection_feature.feature_run_id IS NOT NULL) AS feature_inputs_complete,\n"
            workload_keys_sql = ", ".join("'" + key + "'" for key in FEATURE_FIELDS)
            pregame_select += f"""
                (SELECT jsonb_object_agg(key, value)
                 FROM jsonb_each(projection_feature.feature_json::jsonb)
                 WHERE key IN ({workload_keys_sql})) AS workload_feature_evidence,
                projection_feature.feature_run_id::TEXT AS workload_feature_run_id,
                projection_model_run.data_cutoff_at AS workload_feature_cutoff_at,
            """
            if not has_starting_qbs:
                starter_select = """
                    COALESCE(
                        NULLIF(
                            projection_feature.feature_json
                                ->> 'pregame_start_probability',
                            ''
                        )::DOUBLE PRECISION >= 0.5,
                        FALSE
                    ) AS is_starting_qb,
                    projection_feature.feature_json
                        ->> 'starting_qb_source' AS starting_qb_source,
                    projection_feature.feature_json
                        ->> 'starting_qb_evidence_tier'
                        AS starting_qb_evidence_tier,
                    NULLIF(projection_feature.feature_json ->> 'team_starting_qb_observed_at', '')::TIMESTAMPTZ
                        AS starting_qb_observed_at,
                """
        ownership_select = """
                NULL::DOUBLE PRECISION AS captain_ownership,
                NULL::DOUBLE PRECISION AS flex_ownership,
                NULL::DOUBLE PRECISION AS ownership,
                NULL::TEXT AS ownership_run_id,
                NULL::TEXT AS ownership_source,
                NULL::TIMESTAMPTZ AS ownership_observed_at,
        """
        ownership_join = ""
        if has_ownership:
            ownership_select = """
                ownership.captain_ownership,
                ownership.flex_ownership,
                ownership.player_ownership AS ownership,
                ownership.ownership_run_id,
                ownership.ownership_source,
                ownership.ownership_observed_at,
            """
            ownership_join = """
                LEFT JOIN LATERAL (
                    SELECT
                        MAX(ownership_row.projected_ownership) FILTER (
                            WHERE UPPER(ownership_row.roster_position) = 'CPT'
                        ) AS captain_ownership,
                        MAX(ownership_row.projected_ownership) FILTER (
                            WHERE UPPER(ownership_row.roster_position) = 'FLEX'
                        ) AS flex_ownership,
                        SUM(ownership_row.projected_ownership) FILTER (
                            WHERE UPPER(ownership_row.roster_position) <> 'CPT'
                        ) AS player_ownership,
                        MAX(ownership_row.ownership_run_id::TEXT) AS ownership_run_id,
                        MAX(ownership_model.model_id) AS ownership_source,
                        MIN(ownership_row.data_cutoff_at) AS ownership_observed_at
                    FROM target.ownership_projection ownership_row
                    JOIN target.ownership_model_run ownership_model
                      ON ownership_model.ownership_run_id = ownership_row.ownership_run_id
                    WHERE ownership_row.season = :season
                      AND ownership_row.week = :week
                      AND UPPER(ownership_row.slate_id) = UPPER(:slate)
                      AND ownership_row.player_id = s.player_id
                      AND (:allow_saved_input_fallback OR CAST(:ownership_run_id AS TEXT) IS NOT NULL)
                      AND ownership_row.ownership_run_id::TEXT = COALESCE(
                          :ownership_run_id,
                          (
                          SELECT latest.ownership_run_id::TEXT
                          FROM target.ownership_model_run latest
                          WHERE latest.season = :season
                            AND latest.week = :week
                            AND UPPER(latest.slate_id) = UPPER(:slate)
                          ORDER BY latest.data_cutoff_at DESC NULLS LAST,
                                   latest.created_at DESC,
                                   latest.ownership_run_id DESC
                          LIMIT 1
                          )
                      )
                ) ownership ON TRUE
            """
        row_filter = "WHERE " + " AND ".join(filters) if filters else ""

        query = text(
            f"""
            WITH {salary_cte},
            latest_projection AS (
                SELECT DISTINCT ON (player_id) *
                FROM target.player_projection
                WHERE season = :season AND week = :week
                  AND (:allow_saved_input_fallback OR CAST(:projection_run_id AS TEXT) IS NOT NULL)
                  AND (slate_id IS NULL OR UPPER(slate_id) = UPPER(:slate))
                  AND projection_run_id = COALESCE(
                      :projection_run_id,
                      (
                          SELECT projection_run_id
                          FROM target.active_projection_run
                          WHERE season = :season AND week = :week
                            AND (UPPER(slate_id) = UPPER(:slate) OR slate_id = 'DEFAULT')
                          ORDER BY CASE WHEN UPPER(slate_id) = UPPER(:slate)
                              THEN 0 ELSE 1 END, selected_at DESC
                          LIMIT 1
                      ),
                      (
                          SELECT projection_run_id
                          FROM target.player_projection
                          WHERE season = :season AND week = :week
                            AND (slate_id IS NULL OR UPPER(slate_id) = UPPER(:slate))
                          ORDER BY created_at DESC, projection_run_id
                          LIMIT 1
                      )
                  )
                ORDER BY player_id, created_at DESC
            )
            SELECT
                s.player_id,
                ({identity_resolved}) AS identity_resolved,
                s.site_player_id AS dk_player_id,
                s.captain_site_player_id AS dk_captain_id,
                COALESCE(NULLIF(s.salary_name, ''), NULLIF(d.full_name, ''), s.player_id) AS name,
                COALESCE(NULLIF(s.salary_name, ''), NULLIF(d.full_name, ''), s.player_id) AS player_name,
                CASE
                    WHEN UPPER({position_source}) IN ('D', 'DEF') THEN 'DST'
                    ELSE UPPER({position_source})
                END AS position,
                s.salary,
                s.salary_source_row_id,
                s.salary_ingest_run_id,
                s.salary_source_system,
                s.salary_source_path,
                s.salary_source_checksum,
                s.salary_source_observed_at,
                s.salary_source_snapshot_id,
                s.player_status,
                UPPER(TRIM(COALESCE(s.player_status, ''))) NOT IN (
                    {INELIGIBLE_SALARY_STATUSES_SQL}
                ) AS salary_status_eligible,
                s.team_id AS player_team,
                s.opponent_team_id AS opponent_team,
                s.game_id,
                p.mean AS projection,
                p.median AS predicted_p50,
                p.p10 AS predicted_p10,
                p.p90 AS predicted_p90,
                p.p90,
                p.projection_run_id,
                (p.mean IS NOT NULL AND p.p90 IS NOT NULL) AS projection_inputs_complete,
                p.data_cutoff_at AS projection_observed_at,
                p.created_at AS projection_created_at,
                p.data_cutoff_at,
                {ownership_select}
                {pregame_select}
                {feature_select}
                {starter_select}
                {roster_status_select},
                {depth_chart_select},
                {roster_evidence_select},
                {injury_status_select},
                {calibration_select['calibration_method']} AS calibration_method,
                {calibration_select['calibration_position']} AS calibration_position,
                {calibration_select['calibration_role']} AS calibration_role,
                {calibration_select['calibration_sample_size']} AS calibration_sample_size
            FROM latest_salary s
            LEFT JOIN latest_projection p ON p.player_id = s.player_id
            LEFT JOIN target.dim_player d ON d.player_id = s.player_id
            {identity_join}
            {injury_join}
            {roster_join}
            {depth_chart_join}
            {feature_join}
            {starter_join}
            {pregame_join}
            {ownership_join}
            {row_filter}
            ORDER BY s.player_id
            """
        )
        with self.engine.begin() as connection:
            pool = pd.read_sql(
                query,
                connection,
                params={
                    "season": season,
                    "week": week,
                    "slate": slate,
                    "projection_run_id": projection_run_id,
                    "ownership_run_id": ownership_run_id,
                    "evidence_cutoff_at": evidence_cutoff_at,
                    "allow_saved_input_fallback": not require_explicit_runs,
                },
            )
        if pool.empty:
            return pool
        pool["player_id"] = pool["player_id"].astype(str)
        pool["salary"] = pd.to_numeric(pool["salary"], errors="coerce").fillna(0)
        pool["projection"] = pd.to_numeric(pool["projection"], errors="coerce")
        if not require_explicit_runs:
            pool["projection"] = pool["projection"].fillna(0.0)
        for column, fallback in (
            ("predicted_p50", pool["projection"]),
            ("predicted_p10", pool["projection"]),
            ("predicted_p90", pool["projection"]),
            ("p90", pool["projection"]),
        ):
            pool[column] = pd.to_numeric(pool[column], errors="coerce")
            if not require_explicit_runs:
                pool[column] = pool[column].fillna(fallback)
        pool["position"] = pool["position"].fillna("").astype(str).str.upper()
        pool["player_team"] = pool["player_team"].fillna("").astype(str).str.upper()
        pool["opponent_team"] = pool["opponent_team"].fillna("").astype(str).str.upper()
        pool["name_norm"] = pool["name"].astype(str).str.lower().str.strip().map(_normalize_alias)
        pool["team_norm"] = pool["player_team"]
        from .pregame_context import load_current_pregame_context
        cutoffs = pd.to_datetime(pool["data_cutoff_at"], utc=True, errors="coerce")
        cutoff = evidence_cutoff_at or (cutoffs.min().to_pydatetime() if cutoffs.notna().any() else None)
        if cutoff is not None and self.engine.dialect.name == "postgresql":
            with self.engine.connect() as connection:
                current_role_context = load_current_pregame_context(
                    connection, season=season, week=week, slate=slate,
                    cutoff=cutoff)
                if inspector.has_table("market_snapshot", schema="target"):
                    from .market_snapshots import load_current_markets, attach_pool_market_context
                    markets = load_current_markets(connection,season=season,week=week,cutoff=cutoff)
                    if evidence_cutoff_at is not None or markets:
                        pool = attach_pool_market_context(pool,markets,season=season,week=week,cutoff=cutoff)
            from .showdown_player_context import attach_context_fields
            pool = attach_context_fields(pool,current_role_context)
        if pool["position"].eq("K").any():
            from .kicker_roles import load_kicker_evidence
            cutoffs = pd.to_datetime(pool["data_cutoff_at"], utc=True, errors="coerce")
            if cutoffs.notna().any():
                pool.attrs["kicker_evidence"] = load_kicker_evidence(
                    self.engine, season=season, week=week, slate=slate,
                    cutoff=cutoffs.min().to_pydatetime(),
                )
        return pool

    def _showdown_ownership_selector_policy(self, pool: pd.DataFrame) -> dict:
        from .showdown_ownership_policy import showdown_ownership_policy

        run_ids = sorted(set(pool.get("ownership_run_id", pd.Series(dtype=str)).dropna().astype(str)))
        headers = []
        if run_ids:
            try:
                with self.engine.connect() as connection:
                    headers = [dict(row) for row in connection.execute(text("""
                        SELECT ownership_run_id::TEXT, metrics_json
                        FROM target.ownership_model_run
                        WHERE ownership_run_id::TEXT = ANY(:run_ids)
                    """), {"run_ids": run_ids}).mappings()]
            except SQLAlchemyError:
                # Older databases or frozen offline runs have no promotion
                # evidence. Do not silently treat coverage as approval.
                headers = []
        return showdown_ownership_policy(headers, run_ids)

    def _load_player_pool(
        self,
        season: int,
        week: int,
        slate: str,
        projection_run_id: str | None = None,
        ownership_run_id: str | None = None,
        evidence_cutoff_at: datetime | None = None,
        require_explicit_runs: bool = False,
    ) -> pd.DataFrame:
        """Join salaries with projections for the slate."""
        inspector = inspect(self.engine)
        if (
            inspector.has_table("player_projection", schema="target")
            and (
                inspector.has_table("curated_salary")
                or inspector.has_table("snapshot_salary", schema="target")
            )
        ):
            return self._load_target_player_pool(
                season,
                week,
                slate,
                projection_run_id=projection_run_id,
                ownership_run_id=ownership_run_id,
                evidence_cutoff_at=evidence_cutoff_at,
                require_explicit_runs=require_explicit_runs,
            )
        if not (
            inspector.has_table("curated_salaries")
            and inspector.has_table("player_expected_points")
        ):
            return self._load_target_player_pool(
                season,
                week,
                slate,
                projection_run_id=projection_run_id,
                ownership_run_id=ownership_run_id,
                evidence_cutoff_at=evidence_cutoff_at,
                require_explicit_runs=require_explicit_runs,
            )
        try:
            with self.engine.begin() as connection:
                salaries = pd.read_sql(
                    text(
                        "SELECT * FROM curated_salaries WHERE season = :season AND week = :week AND slate = :slate"
                    ),
                    connection,
                    params={"season": season, "week": week, "slate": slate},
                )
                if "player_id" not in salaries.columns and "ID" in salaries.columns:
                    salaries["player_id"] = salaries["ID"]
                projections = pd.read_sql(
                    text(
                        "SELECT * FROM player_expected_points "
                        "WHERE season = :season AND week = :week AND (slate = :slate OR slate IS NULL)"
                    ),
                    connection,
                    params={"season": season, "week": week, "slate": slate},
                )
                try:
                    adjusted = pd.read_sql(
                        text(
                            "SELECT DISTINCT ON (player_id) player_id, rule_run_id, adjusted_mean, adjusted_p90, reason "
                            "FROM player_expected_points_adjusted "
                            "WHERE season = :season AND week = :week AND (slate = :slate OR slate IS NULL) "
                            "ORDER BY player_id, created_at DESC"
                        ),
                        connection,
                        params={"season": season, "week": week, "slate": slate},
                    )
                except Exception:
                    adjusted = pd.DataFrame()
                if not projections.empty and not adjusted.empty:
                    projections = projections.merge(adjusted, on="player_id", how="left")
                    projections["adj_mean_final"] = projections["adjusted_mean"].fillna(
                        projections.get("adj_mean_final", projections.get("predicted_mean"))
                    )
                    projections["predicted_p90"] = projections["adjusted_p90"].fillna(
                        projections.get("predicted_p90")
                    )
                injuries = pd.read_sql(
                    text(
                        "SELECT player_id, injury_indicator, first_name, last_name, nickname, team "
                        "FROM weekly_injuries "
                        "WHERE season = :season AND week = :week "
                        "AND (slate = :slate OR slate IS NULL)"
                    ),
                    connection,
                    params={"season": season, "week": week, "slate": slate},
                )
                try:
                    starters_df = pd.read_sql(
                        text(
                            "SELECT player_id, player_master_id FROM starting_qbs "
                            "WHERE season = :season AND week = :week AND (slate = :slate OR slate IS NULL)"
                        ),
                        connection,
                        params={"season": season, "week": week, "slate": slate},
                    )
                except Exception:
                    starters_df = pd.DataFrame()
        except ResourceClosedError:
            # Recreate engine if previous connection was closed
            self.engine = create_engine(self.connection_string)
            return self._load_player_pool(
                season,
                week,
                slate,
                projection_run_id=projection_run_id,
            )
        if salaries.empty:
            return pd.DataFrame()
        # Slate sanity counts before projections
        pos_counts = salaries.get("Position", salaries.get("position", pd.Series([], dtype=object))).astype(str).str.upper().value_counts()
        print(f"[slate-check] counts by position: {pos_counts.to_dict()}")
        expected_ranges = {
            "DST": (12, 16),
            "QB": (10, 18),
            "RB": (30, 60),
            "WR": (60, 120),
            "TE": (20, 50),
        }
        for pos, (lo, hi) in expected_ranges.items():
            cnt = pos_counts.get(pos, 0)
            if cnt < lo or cnt > hi:
                print(f"[slate-check] WARNING: {pos} count {cnt} outside expected range {lo}-{hi}")
        # First filter: restrict QBs to starters if available
        if not starters_df.empty:
            starter_ids = {str(pid) for pid in starters_df.get("player_id", []) if pd.notna(pid)}
            starter_pm_ids = {str(pid) for pid in starters_df.get("player_master_id", []) if pd.notna(pid)}
            qb_mask = salaries.get("Position", salaries.get("position", pd.Series([], dtype=object))).astype(str).str.upper() == "QB"
            before_qb = qb_mask.sum()
            if before_qb:
                id_series = salaries["player_id"].astype(str) if "player_id" in salaries.columns else pd.Series([], dtype=str)
                pm_series = salaries.get("player_master_id", pd.Series([], dtype=str)).astype(str)
                keep_qb = qb_mask & (
                    id_series.isin(starter_ids) | pm_series.isin(starter_pm_ids)
                )
                salaries = pd.concat([salaries[~qb_mask], salaries[keep_qb]], ignore_index=True)
                after_qb = keep_qb.sum()
                print(f"[slate-check] QB starters filter (pre-merge): before={before_qb} after={after_qb} starters={len(starter_ids)}")
        if projections.empty:
            salaries["projection"] = salaries.get("average_points_per_game", 0)
            salaries["p90"] = salaries["projection"]
            return salaries

        # Preserve DK id and align merge key to player_master_id when present
        if "dk_player_id" not in salaries.columns:
            if "ID" in salaries.columns:
                salaries["dk_player_id"] = salaries["ID"]
            else:
                salaries["dk_player_id"] = salaries.get("player_id", "")
        if "player_master_id" in salaries.columns:
            salaries["player_id"] = salaries["player_master_id"].fillna(salaries["player_id"])
        # Normalize salary numeric column
        if "salary" not in salaries.columns:
            if "Salary" in salaries.columns:
                salaries["salary"] = pd.to_numeric(salaries["Salary"], errors="coerce")
            else:
                salaries["salary"] = 0
        else:
            salaries["salary"] = pd.to_numeric(salaries["salary"], errors="coerce")

        # Normalize key types before merging
            salaries["player_id"] = salaries["player_id"].astype(str)
            projections["player_id"] = projections["player_id"].astype(str)
            injuries["player_id"] = injuries.get("player_id", pd.Series([], dtype=str)).astype(str)
            if not projections.empty:
                projections = projections.sort_values(by=["adj_mean_final", "predicted_mean"], ascending=False)
                projections = projections.drop_duplicates(subset=["player_id"], keep="first")
            if "name" in salaries.columns:
                salaries["name_norm"] = salaries["name"].astype(str).str.lower().str.strip().map(_normalize_alias)
            if "player_name" in salaries.columns and "name_norm" not in salaries.columns:
                salaries["name_norm"] = salaries["player_name"].astype(str).str.lower().str.strip().map(_normalize_alias)
        if not injuries.empty:
            injuries = injuries.copy()
            for col in ["first_name", "last_name", "nickname", "player_name", "name"]:
                if col in injuries.columns:
                    injuries[col] = injuries[col].astype(str)
            injuries["name_norm"] = injuries.apply(
                lambda row: " ".join(
                    [
                        str(row.get("first_name", "")).strip(),
                        str(row.get("last_name", "")).strip(),
                    ]
                ).lower().strip(),
                axis=1,
            )
            # fallback to nickname/player_name if name missing
            if "nickname" in injuries.columns:
                injuries.loc[injuries["name_norm"] == "", "name_norm"] = (
                    injuries["nickname"].astype(str).str.lower().str.strip()
                )
            if "player_name" in injuries.columns:
                injuries.loc[injuries["name_norm"] == "", "name_norm"] = (
                    injuries["player_name"].astype(str).str.lower().str.strip()
                )
            injuries["name_norm"] = injuries["name_norm"].map(_normalize_alias)

        # Use adjusted mean when available; fall back to model mean
        if "adj_mean_final" in projections.columns:
            projections = projections.rename(columns={"adj_mean_final": "projection"})
        elif "adj_mean" in projections.columns:
            projections = projections.rename(columns={"adj_mean": "projection"})
        else:
            projections = projections.rename(columns={"predicted_mean": "projection"})
        projection_defaults = {
            "predicted_p50": projections.get("projection", 0.0),
            "predicted_p10": projections.get("predicted_p50", projections.get("projection", 0.0)),
            "calibration_role": "unknown",
            "calibration_sample_size": 0,
            "calibration_method": "projection_fallback",
        }
        for column, default in projection_defaults.items():
            if column not in projections.columns:
                projections[column] = default
        merged = salaries.merge(
            projections[
                [
                    "player_id",
                    "projection",
                    "predicted_p90",
                    "predicted_p50",
                    "predicted_p10",
                    "calibration_role",
                    "calibration_sample_size",
                    "calibration_method",
                    "opponent_team",
                    "recent_team",
                    "position",
                ]
            ],
            on="player_id",
            how="left",
        )
        # Fill projection from averages if model outputs are missing
        avg_col = "average_points_per_game" if "average_points_per_game" in merged.columns else None
        if not avg_col and "AvgPointsPerGame" in merged.columns:
            avg_col = "AvgPointsPerGame"
        if avg_col:
            merged["projection"] = merged["projection"].fillna(merged[avg_col])
        merged["p90"] = merged["predicted_p90"].fillna(merged["projection"])

        # Fallback: try name-based match to projections when ids don't align
        projections = projections.copy()
        projections["name_norm"] = projections.get("player_display_name", "").astype(str).str.lower().str.strip().map(_normalize_alias)
        merged_name_norm = merged.get("name_norm")
        if "projection" in merged.columns and merged["projection"].isna().any() and merged_name_norm is not None:
            proj_map = dict(zip(projections["name_norm"], projections["projection"]))
            p90_map = dict(zip(projections["name_norm"], projections.get("predicted_p90", projections["projection"])))
            missing_mask = merged["projection"].isna()
            merged.loc[missing_mask, "projection"] = merged.loc[missing_mask, "name_norm"].map(proj_map)
            merged.loc[missing_mask, "p90"] = merged.loc[missing_mask, "name_norm"].map(p90_map)

        # Ensure a ceiling uplift exists; if p90 ~= projection, scale up modestly to avoid degenerate ceilings.
        def _ceiling_with_uplift(row: pd.Series) -> float:
            proj_val = float(row.get("projection", 0) or 0)
            p90_val = float(row.get("p90", 0) or 0)
            if proj_val <= 0:
                return p90_val
            pos = str(row.get("position", "")).upper()
            floor_mult = 1.05 if pos in {"DST", "D", "DEF"} else 1.10
            if p90_val <= proj_val * floor_mult:
                # Modest uplift to avoid degenerate ceilings; DST smaller bump.
                bump = 1.08 if pos in {"DST", "D", "DEF"} else 1.18
                return proj_val * bump
            return p90_val

        merged["p90"] = merged.apply(_ceiling_with_uplift, axis=1)

        # Prefer readable names for downstream display
        if "player_display_name" in merged.columns:
            merged["name"] = merged["player_display_name"]
            merged["player_name"] = merged["player_display_name"]
        elif "name" not in merged.columns and "player_name" in merged.columns:
            merged["name"] = merged["player_name"]
        # Normalize positions (prefer projection/salary position over showdown CPT/FLEX tags)
        if "position_y" in merged.columns:
            merged["position"] = merged["position_y"]
        elif "position_x" in merged.columns:
            merged["position"] = merged["position_x"]
        elif "position" not in merged.columns:
            merged["position"] = merged.get("roster_position", "")
        merged["position"] = (
            merged["position"]
            .fillna(merged.get("position_x", merged.get("roster_position", "")))
            .astype(str)
            .str.upper()
            .str.split("/")
            .str[0]
        )
        # Filter QBs to starters if starting_qbs table is available
        if 'position' in merged.columns and not locals().get("starters_df", pd.DataFrame()).empty:
            starter_ids = {str(pid) for pid in starters_df.get("player_id", []) if pd.notna(pid)}
            starter_pm_ids = {str(pid) for pid in starters_df.get("player_master_id", []) if pd.notna(pid)}
            before_qb = len(merged[merged["position"] == "QB"])
            merged = merged[
                (merged["position"] != "QB")
                | merged["player_id"].astype(str).isin(starter_ids)
                | merged.get("player_master_id", pd.Series([], dtype=str)).astype(str).isin(starter_pm_ids)
            ]
            after_qb = len(merged[merged["position"] == "QB"])
            print(f"[slate-check] QB starters filter: before={before_qb} after={after_qb} starters={len(starter_ids)}")
        # Normalize team/opponent for correlation rules
        team_series = (
            merged["player_team"]
            if "player_team" in merged.columns
            else merged["recent_team"]
            if "recent_team" in merged.columns
            else pd.Series("", index=merged.index)
        )
        merged["player_team"] = team_series.astype(str).str.upper()
        if "opponent_team" in merged.columns:
            merged["opponent_team"] = merged["opponent_team"].astype(str).str.upper()
        # Fill missing opponent from game_info for DST and any rows missing it
        if "game_info" in merged.columns:
            merged["game_info"] = merged["game_info"].astype(str)
            missing_mask = merged["opponent_team"].isna() if "opponent_team" in merged.columns else pd.Series([True] * len(merged))
            merged.loc[missing_mask, "opponent_team"] = merged.loc[missing_mask].apply(
                lambda row: self._parse_game_info_opponent(row.get("game_info"), row.get("player_team")),
                axis=1,
            )

        # Normalize salary names/teams for later matching
        base_name = (
            merged["name_norm"]
            if "name_norm" in merged.columns
            else merged["name"]
            if "name" in merged.columns
            else merged["player_name"]
            if "player_name" in merged.columns
            else pd.Series("", index=merged.index)
        )
        merged["name_norm"] = base_name.astype(str).str.lower().str.strip().map(_normalize_alias)
        merged_team_series = (
            merged["player_team"]
            if "player_team" in merged.columns
            else (merged["team"] if "team" in merged.columns else pd.Series("", index=merged.index))
        )
        merged["team_norm"] = merged_team_series.astype(str).str.upper().str.strip()

        # Drop injured/IR/Out players using salary-like matching rules
        if not injuries.empty:
            inj = injuries.copy()
            inj["injury_indicator"] = inj["injury_indicator"].fillna("").astype(str).str.upper()
            block_tokens = ("OUT", "IR", "PUP", "NFI", "RESERVE")
            inj = inj[inj["injury_indicator"].str.contains("|".join(block_tokens))]
            inj["team_norm"] = (
                inj["team"] if "team" in inj.columns else (inj["player_team"] if "player_team" in inj.columns else "")
            )
            inj["team_norm"] = inj["team_norm"].astype(str).str.upper().str.strip()

            def _norm_injury_name(row):
                nick = str(row.get("nickname", "")).lower().strip()
                full = f"{str(row.get('first_name', '')).strip()} {str(row.get('last_name', '')).strip()}".strip().lower()
                if nick:
                    return nick
                return full

            inj["name_norm"] = [_norm_injury_name(r) for r in inj.to_dict(orient="records")]
            inj["last_norm"] = inj.get("last_name", "").astype(str).str.lower().str.strip() if "last_name" in inj.columns else ""
            bad_ids = set(inj["player_id"].astype(str))
            bad_name_team = {(r.name_norm, r.team_norm) for r in inj.itertuples() if r.name_norm}
            bad_names = {r.name_norm for r in inj.itertuples() if r.name_norm}
            bad_last_team = {(str(r.last_norm).lower().strip(), r.team_norm) for r in inj.itertuples() if getattr(r, "last_norm", "")}
            bad_last = {str(r.last_norm).lower().strip() for r in inj.itertuples() if getattr(r, "last_norm", "")}

            def _salary_last(row) -> str:
                name = str(row.get("name_norm", "")).strip()
                if " " in name:
                    return name.split(" ")[-1]
                return name

            def _is_injured(row) -> bool:
                pid = str(row.get("player_id"))
                n = str(row.get("name_norm", "")).lower().strip()
                t = str(row.get("team_norm", "")).upper().strip()
                ln = _salary_last(row).lower().strip()
                if pid in bad_ids:
                    return True
                if (n, t) in bad_name_team:
                    return True
                if n in bad_names:
                    return True
                if (ln, t) in bad_last_team:
                    return True
                if ln in bad_last:
                    return True
                return False

            merged = merged[~merged.apply(_is_injured, axis=1)]

        proj_series = pd.to_numeric(merged.get("projection"), errors="coerce")
        valid_mask = proj_series.notna() & (proj_series > 0)
        fallback_mask = proj_series.notna() & (proj_series <= 0)
        nan_count = proj_series.isna().sum()
        print(
            f"[pool:pre-filter] projection counts: valid>0={valid_mask.sum()} fallback<=0={fallback_mask.sum()} nan={nan_count}"
        )
        _log_pool_stats(merged, "pre-filter")
        proj_med = float(pd.to_numeric(merged.get("projection", pd.Series()), errors="coerce").median())
        p90_med = float(pd.to_numeric(merged.get("p90", pd.Series()), errors="coerce").median())
        qb_med = float(pd.to_numeric(merged.loc[merged["position"] == "QB", "projection"], errors="coerce").median()) if not merged.empty else 0
        dst_med = float(pd.to_numeric(merged.loc[merged["position"].isin(["DST", "D", "DEF"]), "projection"], errors="coerce").median()) if not merged.empty else 0
        if (qb_med and qb_med < 12) or (dst_med and dst_med < 3) or (proj_med and proj_med < 6):
            # Attempt auto-fix by switching to predicted_p50/p90 if available
            if "predicted_p50" in merged.columns:
                merged["projection"] = pd.to_numeric(merged["predicted_p50"], errors="coerce")
            if "predicted_p90" in merged.columns:
                merged["p90"] = pd.to_numeric(merged["predicted_p90"], errors="coerce")
            _log_pool_stats(merged, "pre-filter-refit")
            proj_med = float(pd.to_numeric(merged.get("projection", pd.Series()), errors="coerce").median())
            p90_med = float(pd.to_numeric(merged.get("p90", pd.Series()), errors="coerce").median())
            qb_med = float(pd.to_numeric(merged.loc[merged["position"] == "QB", "projection"], errors="coerce").median()) if not merged.empty else 0
            dst_med = float(pd.to_numeric(merged.loc[merged["position"].isin(["DST", "D", "DEF"]), "projection"], errors="coerce").median()) if not merged.empty else 0
            if (qb_med and qb_med < 12) or (dst_med and dst_med < 3) or (proj_med and proj_med < 6):
                logger.warning(
                    "Projection scale still low after refit: qb_med=%.2f dst_med=%.2f proj_med=%.2f; continuing",
                    qb_med,
                    dst_med,
                    proj_med,
                )
        if proj_med and p90_med and p90_med / max(proj_med, 1e-6) > 3:
            logger.warning("Ceiling scale mismatch: p90/mean median ratio=%.2f", p90_med / max(proj_med, 1e-6))
        return merged

    @staticmethod
    def _position_mask(df: pd.DataFrame, positions: List[str]) -> List[str]:
        return df.index[df["position"].isin(positions)].tolist()

    def add_qb_stacking_constraints(
        self,
        model: pulp.LpProblem,
        x: dict,
        pool: pd.DataFrame,
        stack_cfg: dict,
    ) -> dict:
        """
        Add QB stacking constraints with optional bring-backs.
        Returns metadata per QB for post-solve validation.
        """
        if pool.empty:
            return {}

        include_rb = bool(stack_cfg.get("include_rb_in_stack", False))
        pass_positions = {"WR", "TE"}
        if include_rb:
            pass_positions.add("RB")

        bringback_enabled = bool(stack_cfg.get("bringback", False))
        bringback_positions = {p.upper() for p in stack_cfg.get("bringback_positions", {"WR", "TE"})}
        stack_min_default = int(stack_cfg.get("stack_min", 1))
        stack_max = stack_cfg.get("stack_max")
        stack_max_val = None
        if stack_max not in (None, "", False):
            try:
                stack_max_val = int(stack_max)
            except Exception:
                stack_max_val = None

        team_field = "player_team" if "player_team" in pool.columns else "team"
        pool[team_field] = pool[team_field].astype(str).str.upper()
        pool["opponent_team"] = pool.get("opponent_team", "").astype(str).str.upper()

        team_pos_to_idx: dict[tuple[str, str], list[int]] = {}
        for i in pool.index:
            team = str(pool.loc[i, team_field]).upper()
            pos = str(pool.loc[i, "position"]).upper()
            team_pos_to_idx.setdefault((team, pos), []).append(i)

        qb_idx = pool.index[pool["position"] == "QB"].tolist()
        metadata: dict[str, dict] = {}

        for q_idx in qb_idx:
            team = str(pool.loc[q_idx, team_field]).upper()
            opp = str(pool.loc[q_idx, "opponent_team"]).upper()
            qb_id = str(pool.loc[q_idx, "player_id"])

            team_stack_idxs: list[int] = []
            for pos in pass_positions:
                team_stack_idxs.extend(team_pos_to_idx.get((team, pos), []))
            team_stack_idxs = [i for i in team_stack_idxs if i != q_idx]

            if len(team_stack_idxs) < stack_min_default:
                # Exclude this QB (insufficient stack partners after filtering)
                model += x[q_idx] == 0
                metadata[qb_id] = {
                    "qb_idx": q_idx,
                    "team": team,
                    "opp": opp,
                    "stack_min": stack_min_default,
                    "stack_max": stack_max_val,
                    "team_stack_ids": set(),
                    "bringback_ids": set(),
                    "bringback_required": False,
                    "include_rb": include_rb,
                    "bringback_positions": bringback_positions,
                }
                continue

            model += pulp.lpSum(x[i] for i in team_stack_idxs) >= stack_min_default * x[q_idx]
            if stack_max_val is not None:
                big_m = len(team_stack_idxs)
                model += pulp.lpSum(x[i] for i in team_stack_idxs) <= stack_max_val * x[q_idx] + big_m * (1 - x[q_idx])

            bringback_idxs: list[int] = []
            bringback_required = False
            if bringback_enabled and not opp:
                # Exclude this QB due to missing opponent
                model += x[q_idx] == 0
                metadata[qb_id] = {
                    "qb_idx": q_idx,
                    "team": team,
                    "opp": opp,
                    "stack_min": stack_min_default,
                    "stack_max": stack_max_val,
                    "team_stack_ids": set(),
                    "bringback_ids": set(),
                    "bringback_required": False,
                    "include_rb": include_rb,
                    "bringback_positions": bringback_positions,
                }
                continue
            if bringback_enabled and opp:
                for pos in bringback_positions:
                    bringback_idxs.extend(team_pos_to_idx.get((opp, pos), []))
                bringback_idxs = [i for i in bringback_idxs if i != q_idx]
                if bringback_idxs:
                    model += pulp.lpSum(x[i] for i in bringback_idxs) >= 1 * x[q_idx]
                    bringback_required = True
                else:
                    # Exclude this QB if no bring-back available
                    model += x[q_idx] == 0
                    metadata[qb_id] = {
                        "qb_idx": q_idx,
                        "team": team,
                        "opp": opp,
                        "stack_min": stack_min_default,
                        "stack_max": stack_max_val,
                        "team_stack_ids": set(),
                        "bringback_ids": set(),
                        "bringback_required": False,
                        "include_rb": include_rb,
                        "bringback_positions": bringback_positions,
                    }
                    continue

            metadata[qb_id] = {
                "qb_idx": q_idx,
                "team": team,
                "opp": opp,
                "stack_min": stack_min_default,
                "stack_max": stack_max_val,
                "team_stack_ids": {str(pool.loc[i, "player_id"]) for i in team_stack_idxs},
                "bringback_ids": {str(pool.loc[i, "player_id"]) for i in bringback_idxs},
                "bringback_required": bringback_required,
                "include_rb": include_rb,
                "bringback_positions": bringback_positions,
            }

        return metadata

    @staticmethod
    def _validate_stack_solution(
        lineup_rows: List[dict],
        stack_meta: dict,
    ) -> None:
        if not lineup_rows:
            return
        qb_rows = [r for r in lineup_rows if str(r.get("position", "")).upper() == "QB"]
        if len(qb_rows) != 1:
            raise ValueError(f"Expected exactly 1 QB in lineup for validation, found {len(qb_rows)}")
        qb_row = qb_rows[0]
        qb_id = str(qb_row.get("player_id"))
        meta = stack_meta.get(qb_id)
        if not meta:
            raise ValueError(f"No stack metadata found for QB {qb_id}")

        selected_ids = {str(r.get("player_id")) for r in lineup_rows}
        team_stack_selected = len(meta["team_stack_ids"].intersection(selected_ids))
        if team_stack_selected < meta["stack_min"]:
            raise ValueError(
                f"Stack validation failed for QB {qb_id}: selected {team_stack_selected} stack pieces, "
                f"required min {meta['stack_min']}"
            )
        if meta["stack_max"] is not None and team_stack_selected > meta["stack_max"]:
            raise ValueError(
                f"Stack validation failed for QB {qb_id}: selected {team_stack_selected} stack pieces, "
                f"exceeds max {meta['stack_max']}"
            )
        if meta["bringback_required"] and not meta["bringback_ids"].intersection(selected_ids):
            raise ValueError(f"Bring-back validation failed for QB {qb_id}: none selected")

    @staticmethod
    def _validate_classic_lineups(
        lineups: List[List[dict]],
        *,
        requested_lineups: int,
        max_exposure: float,
        enforce_single_te: bool,
        avoid_dst_opponents: bool,
        uniqueness_overlap: int | None = None,
        locked_player_ids: set[str] | None = None,
        excluded_player_ids: set[str] | None = None,
        excluded_opponent_teams: set[str] | None = None,
        minimum_player_salary: int | None = None,
        season_ppg_eligible_ids: dict[str, set[str]] | None = None,
        favored_team_positions: set[str] | None = None,
        minimum_qb_salary: int | None = None,
        minimum_rb_salary: int | None = None,
    ) -> tuple[bool, str]:
        """Validate finalized classic lineups independently of either solver."""
        exposure_counts: dict[str, int] = {}
        signatures: list[set[str]] = []
        exposure_limit = max(
            1, int(math.ceil(max(1, requested_lineups) * max_exposure))
        )

        for lineup_number, lineup in enumerate(lineups, start=1):
            if len(lineup) != 9:
                return False, f"Lineup {lineup_number} has {len(lineup)} players; expected 9"

            player_ids = [
                str(row.get("player_id") or row.get("dk_player_id") or "").strip()
                for row in lineup
            ]
            if any(not player_id for player_id in player_ids):
                return False, f"Lineup {lineup_number} has a missing canonical player ID"
            if len(set(player_ids)) != len(player_ids):
                return False, f"Lineup {lineup_number} contains a duplicate player ID"
            excluded_players = set(player_ids) & (excluded_player_ids or set())
            if excluded_players:
                return False, (
                    f"Lineup {lineup_number} contains excluded player(s): "
                    + ", ".join(sorted(excluded_players))
                )
            if excluded_opponent_teams:
                for row, player_id in zip(lineup, player_ids):
                    opponent = str(row.get("opponent_team") or row.get("opponent") or "").strip().upper()
                    if not opponent:
                        return False, f"Lineup {lineup_number} player {player_id} is missing opponent team"
                    if opponent in excluded_opponent_teams:
                        return False, f"Lineup {lineup_number} player {player_id} faces excluded opponent {opponent}"
            missing_locks = (locked_player_ids or set()) - set(player_ids)
            if missing_locks:
                return False, (
                    f"Lineup {lineup_number} is missing locked player(s): "
                    + ", ".join(sorted(missing_locks))
                )

            positions = [
                str(row.get("position") or row.get("roster_position") or "").upper()
                for row in lineup
            ]
            if positions.count("QB") != 1:
                return False, f"Lineup {lineup_number} must contain exactly one QB"
            if sum(position in {"DST", "D", "DEF"} for position in positions) != 1:
                return False, f"Lineup {lineup_number} must contain exactly one DST"
            if positions.count("RB") < 2:
                return False, f"Lineup {lineup_number} must contain at least two RBs"
            if positions.count("WR") < 3:
                return False, f"Lineup {lineup_number} must contain at least three WRs"
            if positions.count("TE") < 1:
                return False, f"Lineup {lineup_number} must contain at least one TE"
            if enforce_single_te and positions.count("TE") > 1:
                return False, f"Lineup {lineup_number} violates the single-TE control"

            for row in lineup:
                position = str(row.get("position", "")).upper()
                if position in (favored_team_positions or set()) and not is_favored(row):
                    return False, f"Lineup {lineup_number} violates user favored-team {position} requirement"
                if season_ppg_eligible_ids is not None and position in season_ppg_eligible_ids and str(row.get("player_id")) not in season_ppg_eligible_ids[position]:
                    return False, f"Lineup {lineup_number} violates user season-average {position} rank limit"
            for position, minimum in (("QB", minimum_qb_salary), ("RB", minimum_rb_salary)):
                if minimum is not None and any(str(row.get("position", "")).upper() == position and _safe_float(row.get("salary")) < minimum for row in lineup):
                    return False, f"Lineup {lineup_number} violates user minimum {position} salary ${minimum}"
            if minimum_player_salary is not None and any(
                str(row.get("position") or "").upper() not in {"DST", "D", "DEF"}
                and _safe_float(row.get("salary")) < minimum_player_salary for row in lineup
            ):
                return False, f"Lineup {lineup_number} violates user minimum offensive salary ${minimum_player_salary}"
            salary = sum(_safe_float(row.get("salary")) for row in lineup)
            if salary > SALARY_CAP:
                return False, (
                    f"Lineup {lineup_number} salary {salary:.0f} exceeds "
                    f"the {SALARY_CAP} cap"
                )

            team_counts: dict[str, int] = {}
            for row, player_id in zip(lineup, player_ids):
                team = str(
                    row.get("player_team") or row.get("team") or ""
                ).upper()
                if not team:
                    return False, f"Lineup {lineup_number} player {player_id} is missing team"
                team_counts[team] = team_counts.get(team, 0) + 1
                exposure_counts[player_id] = exposure_counts.get(player_id, 0) + 1
            if max(team_counts.values(), default=0) > TEAM_LIMIT:
                return False, (
                    f"Lineup {lineup_number} exceeds the {TEAM_LIMIT}-player "
                    "classic team limit"
                )

            if avoid_dst_opponents:
                dst = next(
                    row
                    for row, position in zip(lineup, positions)
                    if position in {"DST", "D", "DEF"}
                )
                dst_opponent = str(
                    dst.get("opponent_team") or dst.get("opponent") or ""
                ).upper()
                if dst_opponent:
                    conflicting = [
                        row
                        for row, position in zip(lineup, positions)
                        if position not in {"DST", "D", "DEF"}
                        and str(
                            row.get("player_team") or row.get("team") or ""
                        ).upper()
                        == dst_opponent
                    ]
                    if conflicting:
                        return False, (
                            f"Lineup {lineup_number} contains offense against "
                            f"its selected DST ({dst_opponent})"
                        )
            signatures.append(set(player_ids))

        over_exposed = sorted(
            player_id
            for player_id, count in exposure_counts.items()
            if count > exposure_limit
            and player_id not in (locked_player_ids or set())
        )
        if over_exposed:
            return False, (
                f"Player exposure exceeds {exposure_limit}/{requested_lineups}: "
                + ", ".join(over_exposed[:5])
            )

        if uniqueness_overlap is not None:
            for left_index, left in enumerate(signatures):
                for right_index, right in enumerate(
                    signatures[left_index + 1 :],
                    start=left_index + 1,
                ):
                    shared = len(left & right)
                    if shared > uniqueness_overlap:
                        return False, (
                            f"Lineups {left_index + 1} and {right_index + 1} "
                            f"share {shared} players; maximum is {uniqueness_overlap}"
                        )
        return True, ""

    @staticmethod
    def _validate_showdown_lineups(
        lineups: List[List[dict]],
        *,
        requested_lineups: int,
        max_exposure: float,
        enforce_single_te: bool = False,
        require_qb_captain_receiver: bool = False,
        portfolio_policy: bool = False,
        strategy_stack_rules: bool = True,
        allow_duplicate_lineups: bool = False,
        portfolio_exposure_rates: dict[str, float] | None = None,
        locked_players_override_exposure: bool = False,
        locked_player_ids: set[str] | None = None,
        flex_only_player_ids: set[str] | None = None,
        excluded_opponent_teams: set[str] | None = None,
        no_qb_captain: bool = False,
        no_two_qbs: bool = False,
        no_qbs: bool = False,
        captain_positions: list[str] | None = None,
        captain_position_exception_ids: set[str] | None = None,
        captain_shortlist_ids: set[str] | None = None,
        minimum_player_salary: int | None = None,
        required_team_leader_ids: set[str] | None = None,
        max_players_per_team: int = 5,
    ) -> tuple[bool, str]:
        """Validate the persisted one-CPT/five-FLEX contract independently."""
        exposure_counts: dict[str, int] = {}
        captain_counts: dict[str, int] = {}
        player_rows: dict[str, dict] = {}
        signatures: set[tuple[tuple[str, str], ...]] = set()
        exposure_limit = max(
            1, int(math.ceil(max(1, requested_lineups) * max_exposure))
        )

        for lineup_number, lineup in enumerate(lineups, start=1):
            if len(lineup) != 6:
                return (
                    False,
                    f"Lineup {lineup_number} has {len(lineup)} players; expected 6",
                )

            player_ids = [
                str(row.get("player_id") or row.get("dk_player_id") or "").strip()
                for row in lineup
            ]
            if any(not player_id for player_id in player_ids):
                return False, f"Lineup {lineup_number} has a missing canonical player ID"
            if len(set(player_ids)) != len(player_ids):
                return False, f"Lineup {lineup_number} contains a duplicate player ID"
            if excluded_opponent_teams:
                for row, player_id in zip(lineup, player_ids):
                    opponent = str(row.get("opponent_team") or row.get("opponent") or "").strip().upper()
                    if not opponent:
                        return False, f"Lineup {lineup_number} player {player_id} is missing opponent team"
                    if opponent in excluded_opponent_teams:
                        return False, f"Lineup {lineup_number} player {player_id} faces excluded opponent {opponent}"
            missing_locks = (locked_player_ids or set()) - set(player_ids)
            if missing_locks:
                return False, (
                    f"Lineup {lineup_number} is missing locked player(s): "
                    + ", ".join(sorted(missing_locks))
                )

            roster_positions = [
                str(row.get("roster_position") or "").strip().upper()
                for row in lineup
            ]
            if roster_positions.count("CPT") != 1:
                return False, f"Lineup {lineup_number} must contain exactly one CPT"
            if roster_positions.count("FLEX") != 5:
                return False, f"Lineup {lineup_number} must contain exactly five FLEX slots"
            if any(position not in {"CPT", "FLEX"} for position in roster_positions):
                return False, f"Lineup {lineup_number} contains an invalid showdown slot"
            if required_team_leader_ids and not required_team_leader_ids.intersection(player_ids):
                return False, f"Lineup {lineup_number} violates required season-average team leader preference"
            captain_index = roster_positions.index("CPT")
            if captain_shortlist_ids is not None and player_ids[captain_index] not in captain_shortlist_ids:
                return False, f"Lineup {lineup_number} Captain is outside the top-four eligible pregame P90 shortlist"
            if player_ids[captain_index] in (flex_only_player_ids or set()):
                return False, (
                    f"Lineup {lineup_number} uses FLEX-only player "
                    f"{player_ids[captain_index]} at CPT"
                )

            natural_positions = [
                str(row.get("position") or "").strip().upper() for row in lineup
            ]
            quarterback_rows = [
                row
                for row, position in zip(lineup, natural_positions)
                if position == "QB"
            ]
            if no_qbs and quarterback_rows:
                return False, f"Lineup {lineup_number} violates user preference: No QBs in the lineup"
            if no_qb_captain and natural_positions[captain_index] == "QB":
                return False, f"Lineup {lineup_number} violates user preference: No QB Captain"
            if captain_positions and natural_positions[captain_index] not in captain_positions and player_ids[captain_index] not in (captain_position_exception_ids or set()):
                return False, f"Lineup {lineup_number} violates user preference: Captain position restricted to {', '.join(captain_positions)}"
            if no_two_qbs and len(quarterback_rows) > 1:
                return False, f"Lineup {lineup_number} violates user preference: No 2 QBs in the lineup"
            regular_quarterbacks = [
                row
                for row in quarterback_rows
                if not has_explicit_specialty_role(row)
            ]
            if len(regular_quarterbacks) > 2:
                return False, (
                    f"Lineup {lineup_number} contains more than two non-specialty "
                    "quarterbacks"
                )
            ineligible_qbs = [
                player_id
                for row, player_id, position in zip(
                    lineup, player_ids, natural_positions
                )
                if position == "QB"
                and row.get("showdown_qb_eligible") is not True
            ]
            if ineligible_qbs:
                return False, (
                    f"Lineup {lineup_number} contains QB(s) without starter evidence: "
                    + ", ".join(ineligible_qbs)
                )

            if require_qb_captain_receiver:
                if natural_positions[captain_index] == "QB":
                    captain_team = str(
                        lineup[captain_index].get("player_team")
                        or lineup[captain_index].get("team")
                        or ""
                    ).strip().upper()
                    has_same_team_receiver = any(
                        roster_position == "FLEX"
                        and natural_position in {"WR", "TE"}
                        and str(
                            row.get("player_team") or row.get("team") or ""
                        ).strip().upper()
                        == captain_team
                        for row, roster_position, natural_position in zip(
                            lineup, roster_positions, natural_positions
                        )
                    )
                    if not has_same_team_receiver:
                        return False, (
                            f"Lineup {lineup_number} has QB CPT "
                            f"{player_ids[captain_index]} without a same-team "
                            "WR or TE in FLEX"
                        )

            if portfolio_policy and strategy_stack_rules and not no_qbs:
                starter_qbs = [
                    row for row, position in zip(lineup, natural_positions)
                    if position == "QB" and bool(row.get("showdown_qb_eligible"))
                ]
                if not starter_qbs and natural_positions[captain_index] != "RB":
                    return False, f"Lineup {lineup_number} has no starting quarterback"
                for team in {
                    str(row.get("player_team") or row.get("team") or "").upper()
                    for row in lineup
                }:
                    team_qbs = [
                        row for row in starter_qbs
                        if str(row.get("player_team") or row.get("team") or "").upper() == team
                    ]
                    team_catchers = [
                        row for row in lineup
                        if str(row.get("player_team") or row.get("team") or "").upper() == team
                        and str(row.get("position") or "").upper() in {"WR", "TE"}
                    ]
                    if natural_positions[captain_index] != "RB" and len(team_catchers) >= 2 and not team_qbs:
                        return False, f"Lineup {lineup_number} has two {team} pass catchers without their QB"
                captain = lineup[captain_index]
                captain_team = str(captain.get("player_team") or captain.get("team") or "").upper()
                captain_position = natural_positions[captain_index]
                own_qbs = [
                    row for row in starter_qbs
                    if str(row.get("player_team") or row.get("team") or "").upper() == captain_team
                ]
                own_catchers = [
                    row for row in lineup
                    if str(row.get("player_team") or row.get("team") or "").upper() == captain_team
                    and str(row.get("position") or "").upper() in {"WR", "TE"}
                ]
                if captain_position in {"WR", "TE"} and not own_qbs:
                    return False, f"Lineup {lineup_number} has pass-catcher CPT without same-team QB"
                if captain_position == "QB":
                    minimum = 1 if _is_high_rushing_qb(captain) else 2
                    if len(own_catchers) < minimum:
                        return False, f"Lineup {lineup_number} QB CPT requires {minimum} same-team WR/TE"

            if minimum_player_salary is not None:
                for row in lineup:
                    base = row.get("base_salary")
                    if base is None:
                        base = _safe_float(row.get("salary")) / (1.5 if row.get("roster_position") == "CPT" else 1)
                    if _safe_float(base) < minimum_player_salary:
                        return False, f"Lineup {lineup_number} violates user minimum base salary ${minimum_player_salary}"
            salary = sum(_safe_float(row.get("salary")) for row in lineup)
            if salary > SALARY_CAP:
                return False, (
                    f"Lineup {lineup_number} salary {salary:.0f} exceeds "
                    f"the {SALARY_CAP} cap"
                )

            team_counts: dict[str, int] = {}
            for row, player_id in zip(lineup, player_ids):
                team = str(
                    row.get("player_team") or row.get("team") or ""
                ).strip().upper()
                if not team:
                    return (
                        False,
                        f"Lineup {lineup_number} player {player_id} is missing team",
                    )
                team_counts[team] = team_counts.get(team, 0) + 1
                exposure_counts[player_id] = exposure_counts.get(player_id, 0) + 1
                player_rows[player_id] = row
                if str(row.get("roster_position") or "").upper() == "CPT":
                    captain_counts[player_id] = captain_counts.get(player_id, 0) + 1
            if max(team_counts.values(), default=0) > max_players_per_team:
                return (
                    False,
                    f"Lineup {lineup_number} exceeds the {max_players_per_team}-player showdown team limit",
                )

            signature = tuple(sorted(zip(player_ids, roster_positions)))
            if signature in signatures and not allow_duplicate_lineups:
                return False, f"Lineup {lineup_number} duplicates an earlier showdown lineup"
            signatures.add(signature)

        over_exposed = sorted(
            player_id
            for player_id, count in exposure_counts.items()
            if count > exposure_limit
            and player_id not in (locked_player_ids or set())
        )
        if over_exposed:
            return False, (
                f"Player exposure exceeds {exposure_limit}/{requested_lineups}: "
                + ", ".join(over_exposed[:5])
            )
        if portfolio_policy and not allow_duplicate_lineups:
            rates = portfolio_exposure_rates or {}
            captain_rate = float(rates.get("captain", 0.60))
            captain_limit = max(1, int(math.ceil(requested_lineups * captain_rate)))
            over_captain = [pid for pid, count in captain_counts.items() if count > captain_limit]
            if over_captain:
                return False, f"Captain exposure exceeds {captain_rate:.0%}: " + ", ".join(over_captain)
            for player_id, count in exposure_counts.items():
                if locked_players_override_exposure and player_id in (locked_player_ids or set()):
                    continue
                row = player_rows[player_id]
                rate = float(rates.get("core", 0.80))
                if str(row.get("position") or "").upper() == "QB" and bool(row.get("showdown_qb_eligible")):
                    rate = float(rates.get("starting_qb", 1.00))
                elif _safe_float(row.get("base_salary", row.get("salary"))) <= 1000:
                    rate = float(rates.get("cheap_punt", 0.40))
                if count > max(1, int(math.ceil(requested_lineups * rate))):
                    return False, f"Player {player_id} exceeds {rate:.0%} portfolio exposure"
        return True, ""

    @staticmethod
    def _lineups_satisfy_stack(lineups: List[List[dict]], stack_cfg: dict, contest_type: str) -> tuple[bool, str]:
        """Lightweight validation for finalized lineups (baseline or GPP pipeline)."""
        if contest_type == "captain" or not bool(stack_cfg.get("enabled", True)):
            return True, ""
        include_rb = bool(stack_cfg.get("include_rb_in_stack", False))
        pass_positions = {"WR", "TE"}
        if include_rb:
            pass_positions.add("RB")
        bringback_positions = {p.upper() for p in stack_cfg.get("bringback_positions", {"WR", "TE"})}
        stack_min = int(stack_cfg.get("stack_min", 1))
        stack_max = stack_cfg.get("stack_max")
        stack_max_val = None
        if stack_max not in (None, "", False):
            try:
                stack_max_val = int(stack_max)
            except Exception:
                stack_max_val = None
        bringback_required = bool(stack_cfg.get("bringback", False))

        def _team(row: dict) -> str:
            return str(
                row.get("player_team")
                or row.get("team")
                or row.get("team_norm")
                or ""
            ).upper()

        def _opp(row: dict) -> str:
            return str(
                row.get("opponent_team")
                or row.get("opp")
                or row.get("opponent")
                or ""
            ).upper()

        for idx, lineup in enumerate(lineups, start=1):
            qb_rows = [r for r in lineup if str(r.get("position", "")).upper() == "QB"]
            if len(qb_rows) != 1:
                return False, f"Lineup {idx} has {len(qb_rows)} QBs"
            qb = qb_rows[0]
            qb_team = _team(qb)
            qb_opp = _opp(qb)
            if not qb_team:
                return False, f"Lineup {idx} QB missing team"
            same_team = [r for r in lineup if _team(r) == qb_team and str(r.get("position", "")).upper() in pass_positions and r is not qb]
            if len(same_team) < stack_min:
                return False, f"Lineup {idx} stack failed: {len(same_team)} < {stack_min}"
            if stack_max_val is not None and len(same_team) > stack_max_val:
                return False, f"Lineup {idx} stack exceeded max {stack_max_val}"
            if bringback_required:
                if not qb_opp:
                    return False, f"Lineup {idx} QB missing opponent for bring-back"
                bringbacks = [r for r in lineup if _team(r) == qb_opp and str(r.get("position", "")).upper() in bringback_positions]
                if not bringbacks:
                    return False, f"Lineup {idx} missing bring-back vs {qb_opp}"
        return True, ""

    def _apply_pool_filters(self, pool: pd.DataFrame, contest_type: str) -> pd.DataFrame:
        """Prune the candidate pool with projection/ceiling rules while keeping stack pieces."""
        if pool.empty:
            return pool
        if "position" not in pool.columns:
            raise ValueError(f"Player pool missing 'position' column; columns={list(pool.columns)}")

        mode = "cash" if (contest_type or "tournament").lower() == "cash" else "gpp"
        df = pool.copy()
        df["salary"] = pd.to_numeric(df.get("salary", 0), errors="coerce").fillna(0)
        df["projection"] = pd.to_numeric(df.get("projection", 0), errors="coerce").fillna(0)
        df["p90"] = pd.to_numeric(df.get("p90", df["projection"]), errors="coerce").fillna(df["projection"])
        df["strategy_projection_score"] = pd.to_numeric(
            df.get("optimizer_context_mean_score", df["projection"]),
            errors="coerce",
        ).fillna(df["projection"])
        df["strategy_p90_score"] = pd.to_numeric(
            df.get("optimizer_context_ceiling_score", df["p90"]),
            errors="coerce",
        ).fillna(df["p90"])
        salary_k = (df["salary"] / 1000).replace(0, pd.NA)
        df["ceil_per_k"] = (df["strategy_p90_score"] / salary_k).fillna(0)

        # Drop only the worst DSTs; always keep the top few to preserve feasibility
        dst_mask = df["position"].isin(["DST", "D", "DEF"])
        if dst_mask.any():
            dst_sorted = df[dst_mask].sort_values(
                "strategy_projection_score", ascending=False
            )
            keep_dst = dst_sorted.head(max(6, len(dst_sorted)))
            df = pd.concat([df[~dst_mask], keep_dst])

        team_field = "player_team" if "player_team" in df.columns else "team"
        df[team_field] = df[team_field].astype(str).str.upper()
        df["opponent_team"] = df.get("opponent_team", "").astype(str).str.upper()
        df["player_id"] = df["player_id"].astype(str)

        cash_cfg = {
            "score_field": "strategy_projection_score",
            "value_floor": {"default": 2.6, "WR": 2.8, "TE": 2.8, "DST": 0.0},
            "team_caps": {"WR": 3, "TE": 3, "RB": 3},
            "positions": {
                "QB": {"top": 10, "min_score": 14.0, "min_value": 2.6},
                "RB": {"top": 18, "min_score": 8.5, "min_value": 3.0},
                "WR": {"top": 28, "min_score": 7.0, "min_value": 3.3},
                "TE": {"top": 14, "min_score": 6.0, "min_value": 3.1},
                "DST": {"top": 10, "min_score": 5.0, "min_value": 0.0},
            },
        }
        from .classic_candidate_policy import LARGE_GPP_CANDIDATE_POLICY
        gpp_cfg = LARGE_GPP_CANDIDATE_POLICY
        cfg = cash_cfg if mode == "cash" else gpp_cfg
        sort_field = cfg["score_field"]

        filtered_parts = []
        for pos, group in df.groupby("position"):
            pos_cfg = cfg["positions"].get(pos)
            if not pos_cfg:
                filtered_parts.append(group)
                continue
            base = group.sort_values(sort_field, ascending=False).head(pos_cfg["top"])
            threshold = pos_cfg["min_score"]
            value_floor = cfg["value_floor"].get(pos, cfg["value_floor"]["default"])
            if mode == "cash":
                base = base[(base[sort_field] >= threshold) | (base["ceil_per_k"] >= pos_cfg["min_value"])]
            else:
                base = base[(base[sort_field] >= threshold) | (base["ceil_per_k"] >= pos_cfg["min_value"])]
                if pos in {"WR", "TE"}:
                    darts = group[
                        (group["salary"] <= 4500)
                        & (group["ceil_per_k"] >= 3.4)
                    ]
                    if not darts.empty:
                        base = pd.concat([base, darts])
            base = base[base["ceil_per_k"] >= value_floor]
            filtered_parts.append(base)

        filtered = pd.concat(filtered_parts).drop_duplicates(subset=["player_id"])

        # Team caps per position
        def _cap_team(group: pd.DataFrame, cap: int) -> pd.DataFrame:
            return (
                group.sort_values("strategy_p90_score", ascending=False)
                .groupby(team_field)
                .head(cap)
            )

        for pos, cap in cfg["team_caps"].items():
            mask = filtered["position"] == pos
            filtered = pd.concat([_cap_team(filtered[mask], cap), filtered[~mask]])

        # Stack safety: ensure QBs, pass-catchers, bring-backs, and one cheap relief piece survive filters
        rows_to_add: list[pd.DataFrame] = []
        for team, team_df in df.groupby(team_field):
            team_qb = team_df[team_df["position"] == "QB"].sort_values(
                "strategy_p90_score", ascending=False
            )
            if not team_qb.empty and filtered[(filtered["position"] == "QB") & (filtered[team_field] == team)].empty:
                rows_to_add.append(team_qb.head(1))

            pass_catchers = (
                team_df[team_df["position"].isin(["WR", "TE"])]
                .sort_values("strategy_p90_score", ascending=False)
                .head(2)
            )
            if not pass_catchers.empty:
                rows_to_add.append(pass_catchers)

            opp_team = str(team_df["opponent_team"].dropna().iloc[0]) if not team_df["opponent_team"].dropna().empty else ""
            if opp_team:
                opp_pool = df[
                    (df[team_field] == opp_team)
                    & (df["position"].isin(["WR", "TE", "RB"]))
                ].sort_values("strategy_p90_score", ascending=False)
                if not opp_pool.empty:
                    rows_to_add.append(opp_pool.head(1))

            cheap_pc = (
                team_df[
                    team_df["position"].isin(["WR", "TE"]) & (team_df["salary"] <= 4000)
                ]
                .sort_values("strategy_p90_score", ascending=False)
                .head(1)
            )
            if not cheap_pc.empty:
                rows_to_add.append(cheap_pc)

        if rows_to_add:
            filtered = pd.concat([filtered] + rows_to_add)

        filtered = filtered.drop_duplicates(subset=["player_id"]).reset_index(drop=True)
        _log_pool_stats(filtered, "post-filter")
        dst_list = filtered[filtered["position"].isin(["DST", "D", "DEF"])]
        if not dst_list.empty:
            print("[pool:post-filter] DST candidates:\n", dst_list[["name", "player_team", "salary", "projection", "p90"]].to_string(index=False))
        return filtered

    def _select_strategy_candidates(
        self,
        pool: pd.DataFrame,
        *,
        strategy: str,
        contest_type: str,
    ) -> tuple[pd.DataFrame, dict[str, list[str]]]:
        """Apply post-eligibility candidate policy with player-level audit reasons."""
        if pool.empty:
            return pool.copy(), {}
        frame = pool.copy()
        frame["player_id"] = frame["player_id"].astype(str)
        frame["position"] = frame["position"].fillna("").astype(str).str.upper()
        frame["projection"] = pd.to_numeric(
            frame.get("projection", 0.0), errors="coerce"
        ).fillna(0.0)
        frame["p90"] = pd.to_numeric(
            frame.get("p90", frame["projection"]), errors="coerce"
        ).fillna(frame["projection"])
        frame["salary"] = pd.to_numeric(
            frame.get("salary", 0), errors="coerce"
        ).fillna(0.0)
        reasons: dict[str, list[str]] = {}

        def exclude(mask: pd.Series, reason: str) -> None:
            for player_id in frame.loc[mask, "player_id"]:
                reasons.setdefault(str(player_id), []).append(reason)

        if strategy in {CAPTAIN_SINGLE_LINEUP_STRATEGY_ID, CLASSIC_SINGLE_LINEUP_STRATEGY_ID, CLASSIC_HEAD_TO_HEAD_STRATEGY_ID, CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID}:
            positive_projection = (frame["projection"] > 0) & (frame["p90"] > 0)
            exclude(~positive_projection, "no positive projection")
            keep = positive_projection.copy()
            if "is_starting_qb" in frame.columns:
                is_starting = frame["is_starting_qb"].map(
                    lambda value: value is True
                    or str(value).strip().lower() in {"1", "true", "t", "yes"}
                )
                specialty_role = frame.apply(
                    lambda row: has_explicit_specialty_role(row.to_dict()),
                    axis=1,
                )
                backup_qb = (
                    (frame["position"] == "QB")
                    & ~is_starting
                    & ~specialty_role
                )
                exclude(backup_qb, "backup QB / zero expected snaps")
                keep &= ~backup_qb
            if strategy in {CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID, CLASSIC_SINGLE_LINEUP_STRATEGY_ID}:
                eligible, opportunity_excluded = apply_showdown_opportunity_gate(frame.loc[keep])
                for player_id in opportunity_excluded:
                    reasons.setdefault(str(player_id), []).append(
                        "low-opportunity skill player under existing generalized gate"
                    )
                keep &= frame["player_id"].isin(set(eligible["player_id"].astype(str)))
            return frame.loc[keep].reset_index(drop=True), reasons

        if strategy == CLASSIC_LARGE_GPP_STRATEGY_ID:
            working = frame.copy()
            if "is_starting_qb" in working.columns:
                is_starting = working["is_starting_qb"].map(
                    lambda value: value is True
                    or str(value).strip().lower() in {"1", "true", "t", "yes"}
                )
                specialty_role = working.apply(
                    lambda row: has_explicit_specialty_role(row.to_dict()),
                    axis=1,
                )
                backup_qb = (
                    (working["position"] == "QB")
                    & ~is_starting
                    & ~specialty_role
                )
                exclude(backup_qb, "backup QB / zero expected snaps")
                working = working.loc[~backup_qb].copy()
            no_projection = (working["projection"] <= 0) | (working["p90"] <= 0)
            for player_id in working.loc[no_projection, "player_id"]:
                reasons.setdefault(str(player_id), []).append("no positive projection")
            working = working.loc[~no_projection].copy()
            filtered = self._apply_pool_filters(working, contest_type="tournament")
            included_ids = set(filtered["player_id"].astype(str))
            salary_k = (working["salary"] / 1000.0).replace(0, pd.NA)
            working["strategy_p90_score"] = pd.to_numeric(
                working.get("optimizer_context_ceiling_score", working["p90"]),
                errors="coerce",
            ).fillna(working["p90"])
            working["ceil_per_k"] = (
                working["strategy_p90_score"] / salary_k
            ).fillna(0.0)
            from .classic_candidate_policy import LARGE_GPP_CANDIDATE_POLICY
            config = {position: {**values, "value": LARGE_GPP_CANDIDATE_POLICY["value_floor"].get(
                position, LARGE_GPP_CANDIDATE_POLICY["value_floor"]["default"])}
                for position, values in LARGE_GPP_CANDIDATE_POLICY["positions"].items()}
            team_caps = LARGE_GPP_CANDIDATE_POLICY["team_caps"]
            team_field = "player_team" if "player_team" in working.columns else "team"
            working[team_field] = working[team_field].fillna("").astype(str).str.upper()
            for position, group in working.groupby("position"):
                position_config = config.get(position)
                if position_config is None:
                    continue
                ordered = group.sort_values("strategy_p90_score", ascending=False)
                position_rank = {
                    str(player_id): rank
                    for rank, player_id in enumerate(ordered["player_id"], start=1)
                }
                team_rank: dict[str, int] = {}
                for _team, team_group in group.groupby(team_field):
                    for rank, player_id in enumerate(
                        team_group.sort_values(
                            "strategy_p90_score", ascending=False
                        )["player_id"],
                        start=1,
                    ):
                        team_rank[str(player_id)] = rank
                for row in group.to_dict(orient="records"):
                    player_id = str(row["player_id"])
                    if player_id in included_ids:
                        continue
                    player_reasons = reasons.setdefault(player_id, [])
                    if float(row["ceil_per_k"]) < position_config["value"]:
                        player_reasons.append(
                            f"below GPP {position} value threshold"
                        )
                    if (
                        float(row["strategy_p90_score"])
                        < position_config["min_score"]
                        and float(row["ceil_per_k"]) < position_config["min_value"]
                    ):
                        player_reasons.append(
                            f"below GPP {position} ceiling threshold"
                        )
                    if position_rank[player_id] > position_config["top"]:
                        player_reasons.append("outside positional candidate cap")
                    if (
                        position in team_caps
                        and team_rank.get(player_id, 0) > team_caps[position]
                    ):
                        player_reasons.append("team candidate cap")
                    if not player_reasons:
                        player_reasons.append("not selected by Large GPP candidate ranking")
            return filtered.reset_index(drop=True), reasons

        filtered = self._apply_pool_filters(frame, contest_type=contest_type)
        included_ids = set(filtered["player_id"].astype(str))
        for player_id in set(frame["player_id"]) - included_ids:
            reasons[str(player_id)] = ["legacy strategy candidate filter"]
        return filtered.reset_index(drop=True), reasons

    def _solve_lineup(
        self,
        pool: pd.DataFrame,
        score_col: str = "p90",
        exposure_remaining: dict | None = None,
        captain_exposure_remaining: dict | None = None,
        exclude_lineups: List[set] | None = None,
        exclude_signatures: List[list[tuple[str, str | None]]] | None = None,
        enforce_single_te: bool = False,
        avoid_dst_opponents: bool = False,
        contest_type: str = "classic",
        stack_params: dict | None = None,
        locked_player_ids: set[str] | None = None,
        flex_only_player_ids: set[str] | None = None,
        rule_profile: StrategyProfile | None = None,
        quality_floor: dict[str, float] | None = None,
        portfolio_script: dict | None = None,
        locked_captain_player_id: str | None = None,
        include_control_comparison: bool = True,
        infeasibility_diagnostics: dict | None = None,
        additional_constraints: Callable | None = None,
    ) -> Optional[List[dict]]:
        if pool.empty:
            return None

        # Pool is pre-filtered for min salary and exclusions upstream
        if score_col not in pool.columns:
            score_col = "projection"
        print(f"[solve] objective column={score_col}")
        pool = pool.copy()
        if contest_type != "captain":
            pool[score_col] = pd.to_numeric(pool[score_col], errors="coerce").fillna(0)
        pool["salary"] = pd.to_numeric(pool.get("salary", 0), errors="coerce").fillna(0)
        pool = pool.reset_index(drop=True)
        if contest_type == "captain":
            qb_multipliers = _showdown_qb_correlation_multipliers(pool)
            pool["qb_correlation_multiplier"] = pool["player_id"].astype(str).map(
                qb_multipliers
            ).fillna(1.0)
        print(f"[solve] sample objective values:\n{pool[[score_col,'name','position','salary']].head(5).to_string(index=False)}")

        context_score_columns = {
            "cash_score", "h2h_score", "showdown_cash_score",
            "optimizer_context_ceiling_score", "gpp_score",
        }
        context_multiplier = 1.0 if score_col in context_score_columns else 0.0

        # Drop QBs that cannot meet stack/bring-back requirements to keep model feasible
        if contest_type != "captain" and bool((stack_params or {}).get("enabled", True)):
            stack_min = int(stack_params.get("stack_min", 1))
            bringback_flag = bool(stack_params.get("bringback", False))
            include_rb = bool(stack_params.get("include_rb_in_stack", False))
            pass_positions = {"WR", "TE"}
            if include_rb:
                pass_positions.add("RB")
            bringback_positions = {p.upper() for p in stack_params.get("bringback_positions", {"WR", "TE"})}
            team_field = "player_team" if "player_team" in pool.columns else "team"
            pool[team_field] = pool[team_field].astype(str).str.upper()
            pool["opponent_team"] = pool.get("opponent_team", "").astype(str).str.upper()
            keep_idxs = []
            for i in pool.index:
                if pool.loc[i, "position"] != "QB":
                    keep_idxs.append(i)
                    continue
                team = str(pool.loc[i, team_field]).upper()
                opp = str(pool.loc[i, "opponent_team"]).upper()
                team_stack = pool[(pool[team_field] == team) & (pool["position"].isin(pass_positions)) & (pool.index != i)]
                if len(team_stack) < stack_min:
                    continue
                if bringback_flag:
                    if not opp:
                        continue
                    bb = pool[(pool[team_field] == opp) & (pool["position"].isin(bringback_positions))]
                    if bb.empty:
                        continue
                keep_idxs.append(i)
            pool = pool.loc[keep_idxs].reset_index(drop=True)

        locked_ids = {str(player_id) for player_id in (locked_player_ids or set())}
        flex_only_ids = {
            str(player_id) for player_id in (flex_only_player_ids or set())
        }
        candidate_ids = set(pool["player_id"].astype(str))
        if locked_ids - candidate_ids:
            return None
        locked_captain_id = str(locked_captain_player_id or "").strip()
        if locked_captain_id and (
            locked_captain_id not in candidate_ids or locked_captain_id in flex_only_ids
        ):
            return None
        index_range = range(len(pool))
        contest_type = (contest_type or "classic").lower()
        params = stack_params or {}

        # Captain mode (Showdown): 1 CPT (1.5x points + salary) + 5 Flex
        if contest_type == "captain":
            if "showdown_captain_shortlisted" not in pool.columns:
                pool, _ = build_captain_shortlist(pool, params=params, flex_only_ids=flex_only_ids)
            cap_vars = pulp.LpVariable.dicts("captain", index_range, lowBound=0, upBound=1, cat="Binary")
            flex_vars = pulp.LpVariable.dicts("flex", index_range, lowBound=0, upBound=1, cat="Binary")
            model = pulp.LpProblem("DK_Captain", pulp.LpMaximize)
            workload_objective = score_col == "workload_utility" or (bool((stack_params or {}).get('bounded_scenario_comparison')) and not (stack_params or {}).get('scenario_incumbent_control'))
            objective_expression = pulp.lpSum(
                1.5 * _safe_float(pool.loc[i, score_col if workload_objective else "showdown_captain_p90"]) * cap_vars[i]
                + _safe_float(pool.loc[i, score_col if workload_objective else "showdown_flex_mean"]) * flex_vars[i]
                for i in index_range
            )
            control_objective = objective_expression
            context_multiplier = 0.0
            model += objective_expression

            # Salary cap (captain costs 1.5x)
            model += pulp.lpSum(
                1.5 * pool.loc[i, "salary"] * cap_vars[i] + pool.loc[i, "salary"] * flex_vars[i] for i in index_range
            ) <= SALARY_CAP, "salary_cap"

            # Roster size: 1 CPT + 5 Flex = 6
            model += pulp.lpSum(cap_vars[i] for i in index_range) == 1, "one_captain"
            model += pulp.lpSum(flex_vars[i] for i in index_range) == 5, "five_flex"

            # A player can only appear once (either CPT or Flex)
            for i in index_range:
                model += cap_vars[i] + flex_vars[i] <= 1, f"unique_player_{i}"
                if not bool(pool.loc[i, "showdown_captain_shortlisted"]):
                    model += cap_vars[i] == 0, f"outside_captain_shortlist_{i}"
                if str(pool.loc[i, "player_id"]) in flex_only_ids:
                    model += cap_vars[i] == 0, f"flex_only_{i}"
                if str(pool.loc[i, "player_id"]) in locked_ids:
                    model += cap_vars[i] + flex_vars[i] == 1, f"locked_player_{i}"
            if locked_captain_id:
                model += pulp.lpSum(
                    cap_vars[i]
                    for i in index_range
                    if str(pool.loc[i, "player_id"]) == locked_captain_id
                ) == 1, "locked_captain"

            team_field = "player_team" if "player_team" in pool.columns else "team"
            normalized_teams = pool[team_field].astype(str).str.strip().str.upper()
            normalized_positions = pool["position"].astype(str).str.strip().str.upper()
            selected = {i: cap_vars[i] + flex_vars[i] for i in index_range}
            if params.get("required_team_leader_ids"):
                required = set(params["required_team_leader_ids"])
                model += pulp.lpSum(selected[i] for i in index_range if str(pool.loc[i, "player_id"]) in required) >= 1, "user_season_average_team_leader"

            captain_positions = allowed_captain_positions(params)
            if captain_positions:
                for i in index_range:
                    if normalized_positions.iloc[i] not in captain_positions and str(pool.loc[i, "player_id"]) not in named_preference_ids(params, "captain_position_exception_ids"):
                        model += cap_vars[i] == 0, f"user_captain_positions_{i}"

            qb_indexes = [i for i in index_range if normalized_positions.iloc[i] == "QB"]
            if params.get("no_qbs", False):
                for i in qb_indexes:
                    model += selected[i] == 0, f"user_no_qbs_{i}"
            if params.get("no_qb_captain", False):
                for i in qb_indexes:
                    model += cap_vars[i] == 0, f"user_no_qb_captain_{i}"
            if params.get("no_two_qbs", False):
                model += pulp.lpSum(selected[i] for i in qb_indexes) <= 1, "user_no_two_qbs"

            rb_captain_selected = pulp.lpSum(cap_vars[i] for i in index_range if normalized_positions.iloc[i] == "RB")
            if bool(params.get("require_starting_qb", False)) and not params.get("no_qbs", False):
                starter_qbs = [
                    i for i in index_range
                    if normalized_positions.iloc[i] == "QB"
                    and bool(pool.loc[i].get("showdown_qb_eligible"))
                ]
                model += pulp.lpSum(selected[i] for i in starter_qbs) >= 1 - rb_captain_selected

            if bool(params.get("hard_qb_correlations", False)) and not params.get("no_qbs", False):
                for team in sorted(set(normalized_teams)):
                    qbs = [
                        i for i in index_range
                        if normalized_teams.iloc[i] == team
                        and normalized_positions.iloc[i] == "QB"
                        and bool(pool.loc[i].get("showdown_qb_eligible"))
                    ]
                    pass_catchers = [
                        i for i in index_range
                        if normalized_teams.iloc[i] == team
                        and normalized_positions.iloc[i] in {"WR", "TE"}
                    ]
                    qb_selected = pulp.lpSum(selected[i] for i in qbs)
                    if pass_catchers:
                        # Except with RB Captain, two same-team pass catchers require their QB.
                        model += pulp.lpSum(selected[i] for i in pass_catchers) <= (
                            1 + max(1, len(pass_catchers) - 1) * (qb_selected + rb_captain_selected)
                        )
                    for receiver_index in pass_catchers:
                        if qbs:
                            model += cap_vars[receiver_index] <= qb_selected
                        else:
                            model += cap_vars[receiver_index] == 0
                    for qb_index in qbs:
                        minimum = 1 if _is_high_rushing_qb(pool.loc[qb_index]) else 2
                        if len(pass_catchers) >= minimum:
                            model += pulp.lpSum(selected[i] for i in pass_catchers) >= (
                                minimum * cap_vars[qb_index]
                            )
                        else:
                            model += cap_vars[qb_index] == 0

            script = dict(portfolio_script or {})
            script_kind = str(script.get("kind") or "")
            script_team = str(script.get("team") or "").upper()
            teams = sorted(team for team in set(normalized_teams) if team)
            if script_kind == "shootout" and len(teams) == 2:
                for team in teams:
                    team_indexes = [i for i in index_range if normalized_teams.iloc[i] == team]
                    team_qbs = [i for i in team_indexes if normalized_positions.iloc[i] == "QB"]
                    model += pulp.lpSum(selected[i] for i in team_indexes) >= 2
                    if team_qbs:
                        model += pulp.lpSum(selected[i] for i in team_qbs) >= 1
            elif script_kind in {"pass_led", "run_control"} and script_team:
                team_indexes = [i for i in index_range if normalized_teams.iloc[i] == script_team]
                model += pulp.lpSum(selected[i] for i in team_indexes) >= 4
                model += pulp.lpSum(cap_vars[i] for i in team_indexes) == 1
            elif script_kind == "contrarian" and script_team:
                team_indexes = [i for i in index_range if normalized_teams.iloc[i] == script_team]
                model += pulp.lpSum(selected[i] for i in team_indexes) >= 4
                model += pulp.lpSum(cap_vars[i] for i in team_indexes) == 1
                if "captain_ownership" in pool.columns:
                    team_ownership = pd.to_numeric(
                        pool.loc[team_indexes, "captain_ownership"], errors="coerce"
                    ).dropna()
                    if not team_ownership.empty:
                        median_ownership = float(team_ownership.median())
                        for i in team_indexes:
                            ownership = pd.to_numeric(
                                pd.Series([pool.loc[i, "captain_ownership"]]), errors="coerce"
                            ).iloc[0]
                            if pd.notna(ownership) and float(ownership) > median_ownership:
                                model += cap_vars[i] == 0
            elif script_kind == "team_control" and script_team:
                team_indexes = [i for i in index_range if normalized_teams.iloc[i] == script_team]
                model += pulp.lpSum(selected[i] for i in team_indexes) >= int(
                    script.get("minimum_team_players", 4)
                )
                model += pulp.lpSum(cap_vars[i] for i in team_indexes) == 1
                for required_position in script.get("required_positions", []):
                    required_indexes = [
                        i for i in team_indexes
                        if normalized_positions.iloc[i] == required_position
                        or (required_position == "DST" and normalized_positions.iloc[i] in {"D", "DEF"})
                    ]
                    model += pulp.lpSum(selected[i] for i in required_indexes) >= 1
            elif script_kind == "scenario_construction" and script_team:
                team_indexes = [i for i in index_range if normalized_teams.iloc[i] == script_team]
                if script.get("team_players") is not None:
                    model += pulp.lpSum(selected[i] for i in team_indexes) == int(script["team_players"])
                for required_position in script.get("required_positions", []):
                    required_indexes = [
                        i for i in team_indexes
                        if normalized_positions.iloc[i] == required_position
                        or (required_position == "DST" and normalized_positions.iloc[i] in {"D", "DEF"})
                    ]
                    model += pulp.lpSum(selected[i] for i in required_indexes) >= 1

            if quality_floor:
                mean_expression = pulp.lpSum(
                    pool.loc[i, "projection"] * (1.5 * cap_vars[i] + flex_vars[i])
                    for i in index_range
                )
                p90_expression = pulp.lpSum(
                    pool.loc[i, "p90"] * (1.5 * cap_vars[i] + flex_vars[i])
                    for i in index_range
                )
                model += mean_expression >= float(quality_floor["mean"])
                model += p90_expression >= float(quality_floor["p90"])

            # Team exposure limit (DK rule allows up to 5 from one team in Showdown)
            for team, team_df in pool.groupby("player_team"):
                idx = team_df.index.tolist()
                model += pulp.lpSum(cap_vars[i] + flex_vars[i] for i in idx) <= showdown_team_limit(params), f"team_limit_{team}"

            # Prevent duplicate player selections if multiple rows exist for same player_id or name+team
            by_pid = {}
            for i, pid in enumerate(pool["player_id"].astype(str)):
                by_pid.setdefault(pid, []).append(i)
            for pid, idxs in by_pid.items():
                if len(idxs) > 1:
                    model += pulp.lpSum(cap_vars[i] + flex_vars[i] for i in idxs) <= 1
            by_name_team = {}
            for i in index_range:
                key = (
                    str(pool.loc[i].get("name_norm") or pool.loc[i].get("name") or pool.loc[i].get("player_name", ""))
                    .lower()
                    .strip(),
                    str(pool.loc[i].get("player_team") or pool.loc[i].get("team", "")).upper().strip(),
                )
                by_name_team.setdefault(key, []).append(i)
            for key, idxs in by_name_team.items():
                if len(idxs) > 1:
                    model += pulp.lpSum(cap_vars[i] + flex_vars[i] for i in idxs) <= 1

            if bool(params.get("require_qb_captain_receiver", False)):
                team_field = (
                    "player_team" if "player_team" in pool.columns else "team"
                )
                normalized_teams = pool[team_field].astype(str).str.strip().str.upper()
                normalized_positions = pool["position"].astype(str).str.strip().str.upper()
                for quarterback_index in [
                    i for i in index_range if normalized_positions.iloc[i] == "QB"
                ]:
                    quarterback_team = normalized_teams.iloc[quarterback_index]
                    receiver_indexes = [
                        i
                        for i in index_range
                        if i != quarterback_index
                        and normalized_teams.iloc[i] == quarterback_team
                        and normalized_positions.iloc[i] in {"WR", "TE"}
                    ]
                    if receiver_indexes:
                        model += (
                            pulp.lpSum(flex_vars[i] for i in receiver_indexes)
                            >= cap_vars[quarterback_index]
                        )
                    else:
                        model += cap_vars[quarterback_index] == 0

            # Avoid offensive players vs selected DST
            if avoid_dst_opponents:
                dst_idx = self._position_mask(pool, ["DST", "D", "DEF"])
                for d_idx in dst_idx:
                    dst_team = str(pool.loc[d_idx, "player_team"]).upper()
                    dst_opp = str(pool.loc[d_idx].get("opponent_team", "")).upper()
                    if not dst_opp:
                        continue
                    for i in index_range:
                        if i == d_idx:
                            continue
                        pos = str(pool.loc[i, "position"] if "position" in pool.columns else "").upper()
                        if pos in ("DST", "D", "DEF"):
                            continue
                        player_team = str(pool.loc[i, "player_team"]).upper()
                        if player_team == dst_opp:
                            model += cap_vars[i] + flex_vars[i] + cap_vars[d_idx] + flex_vars[d_idx] <= 1

            # Exposure caps (remaining count across multi-lineup generation)
            if exposure_remaining:
                for i in index_range:
                    pid = str(pool.loc[i, "player_id"])
                    remaining = exposure_remaining.get(pid)
                    if (
                        pid not in locked_ids
                        and remaining is not None
                        and remaining <= 0
                    ):
                        model += cap_vars[i] == 0
                        model += flex_vars[i] == 0
            if captain_exposure_remaining:
                for i in index_range:
                    pid = str(pool.loc[i, "player_id"])
                    if captain_exposure_remaining.get(pid, 1) <= 0:
                        model += cap_vars[i] == 0

            if params.get("single_lineup_user_controls"):
                from .single_lineup import apply_lineup_constraints
                apply_lineup_constraints(model, pool, {i: cap_vars[i] + flex_vars[i] for i in index_range},
                    params["single_lineup_user_controls"], cutoff=params.get("single_lineup_cutoff"))

            # Avoid duplicate lineups
            if exclude_lineups:
                valid_idx = set(index_range)
                for lineup_indices in exclude_lineups:
                    idxs = [i for i in lineup_indices if i in valid_idx]
                    if not idxs:
                        continue
                    model += pulp.lpSum(cap_vars[i] + flex_vars[i] for i in idxs) <= len(idxs) - 1
            if exclude_signatures:
                pid_to_idx = {}
                for i, pid in enumerate(pool["player_id"].astype(str)):
                    pid_to_idx.setdefault(pid, []).append(i)
                for signature in exclude_signatures:
                    vars_in_sig = []
                    target_len = len(signature)
                    for pid, role in signature:
                        idxs = pid_to_idx.get(str(pid), [])
                        if not idxs:
                            continue
                        if role == "CPT":
                            vars_in_sig.extend([cap_vars[i] for i in idxs])
                        else:
                            vars_in_sig.extend([flex_vars[i] for i in idxs])
                    if vars_in_sig:
                        model += pulp.lpSum(vars_in_sig) <= max(0, target_len - 1)

            if additional_constraints is not None:
                additional_constraints(model, pool, selected)
            solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=10, threads=0 if params.get("scenario_serial_solver") else 1, options=["randomSeed 1"]) if workload_objective or (stack_params or {}).get('bounded_scenario_comparison') else pulp.PULP_CBC_CMD(msg=False)
            status = model.solve(solver)
            if isinstance(params.get('learned_opportunity_audit'),dict):
                from .evaluation_record import digest
                snapshot=_json_safe(dict(model=model.toDict(),players=pool[[c for c in (
                    'player_id','position','player_team','salary','workload_utility','showdown_captain_shortlisted') if c in pool]].to_dict('records'))
                )
                # JSONB erases the sign of zero solver duals. Canonicalize this
                # non-selection diagnostic before hashing the persisted model.
                for constraint in snapshot['model']['constraints']:
                    if constraint.get('pi') == 0:constraint['pi']=0.0
                params['learned_opportunity_audit'].update(solver_status=pulp.LpStatus[status],
                    objective=pulp.value(model.objective),input_snapshot=snapshot,input_sha256=digest(snapshot),
                    points_in_objective=False,points_in_qualification=False)
            if status != pulp.LpStatusOptimal:
                if infeasibility_diagnostics is not None:
                    infeasibility_diagnostics["solver_status"] = pulp.LpStatus[status]
                    if status == pulp.LpStatusInfeasible:
                        # Find an irreducible conflict, including interacting constraints.
                        for name in list(model.constraints):
                            constraint = model.constraints.pop(name)
                            if model.solve(solver) != pulp.LpStatusInfeasible:
                                model.constraints[name] = constraint
                        conflicts = []
                        for name, constraint in model.constraints.items():
                            expression = str(constraint)
                            for i in reversed(list(index_range)):
                                for role in ("captain", "flex"):
                                    expression = re.sub(
                                        rf"\b{role}_{i}\b",
                                        lambda match, i=i, role=role: f"{role}[{pool.loc[i, 'player_id']}]",
                                        expression,
                                    )
                            conflicts.append({"constraint": name, "expression": expression})
                        infeasibility_diagnostics["conflicting_constraints"] = conflicts
                        infeasibility_diagnostics["reason"] = "Conflicting hard constraints: " + "; ".join(
                            f"{item['constraint']}: {item['expression']}" for item in conflicts
                        )
                    else:
                        infeasibility_diagnostics["reason"] = "Solver did not establish an optimum: " + pulp.LpStatus[status]
                return None

            scored_objective_value = float(pulp.value(model.objective) or 0.0)
            scored_values = {v.name: v.value() for v in model.variables()}
            replay = solve_control(model, control_objective) if include_control_comparison else None
            if replay is not None:
                replay["variable_players"] = {
                    variable.name: {"player_id": str(pool.loc[i, "player_id"]), "roster_position": slot}
                    for slot, variables in (("CPT", cap_vars), ("FLEX", flex_vars))
                    for i, variable in variables.items()
                }
            paired_rows = []
            value_sets = [scored_values]
            if replay is not None:
                value_sets.append(replay["values"])
            for values in value_sets:
                lineup_rows = []
                for i in index_range:
                    selected_cap = values.get(cap_vars[i].name, 0) >= 0.9
                    selected_flex = values.get(flex_vars[i].name, 0) >= 0.9
                    if selected_cap or selected_flex:
                        row = pool.loc[i].to_dict()
                        base_salary = _safe_float(row.get("salary"))
                        base_projection = _safe_float(row.get("projection"))
                        base_p90 = _safe_float(row.get("p90", base_projection))
                        if "baseline_projection" in row:
                            row["baseline_projection"] = _safe_float(row["baseline_projection"]) * (1.5 if selected_cap else 1.0)
                        if "baseline_p90" in row:
                            row["baseline_p90"] = _safe_float(row["baseline_p90"]) * (1.5 if selected_cap else 1.0)
                        if selected_cap and isinstance(row.get("showdown_scenario_adjustment"), dict):
                            adjustment = dict(row["showdown_scenario_adjustment"])
                            for field in ("baseline_mean", "scenario_mean", "baseline_p90", "scenario_p90", "delta_mean", "delta_p90"):
                                if adjustment.get(field) is not None:
                                    adjustment[field] = _safe_float(adjustment[field]) * 1.5
                            row["showdown_scenario_adjustment"] = adjustment
                        base_objective = _safe_float(row.get(
                            score_col if workload_objective else ("showdown_captain_p90" if selected_cap else "showdown_flex_mean")
                        ))
                        row["base_salary"] = base_salary
                        row["base_projection"] = base_projection
                        row["base_p90"] = base_p90
                        row["is_captain"] = bool(selected_cap)
                        if selected_cap:
                            captain_site_id = row.get("dk_captain_id")
                            if captain_site_id is not None and not pd.isna(captain_site_id):
                                captain_site_id = str(captain_site_id).strip()
                                if captain_site_id:
                                    row["dk_player_id"] = captain_site_id
                            row["salary"] = base_salary * 1.5
                            row["projection"] = base_projection * 1.5
                            row["p90"] = base_p90 * 1.5
                            row["objective_score"] = (
                                base_objective * 1.5
                            )
                            row["roster_position"] = "CPT"
                            row["ownership"] = (
                                _safe_float(row.get("captain_ownership"))
                                if pd.notna(row.get("captain_ownership")) else None
                            )
                        else:
                            row["salary"] = base_salary
                            row["projection"] = base_projection
                            row["p90"] = base_p90
                            row["objective_score"] = base_objective
                            row["roster_position"] = "FLEX"
                            row["ownership"] = (
                                _safe_float(row.get("flex_ownership"))
                                if pd.notna(row.get("flex_ownership")) else None
                            )
                        row["ownership_roster_position"] = row["roster_position"]
                        row["ownership_input_status"] = (
                            "available" if row.get("ownership") is not None else "unavailable"
                        )
                        lineup_rows.append(row)
                paired_rows.append(lineup_rows)
            lineup_rows = paired_rows[0]
            lineup_rows[0]["solver_objective_value"] = scored_objective_value
            lineup_rows[0]["solver_ownership_weight"] = 0.0
            lineup_rows[0]["solver_scoring_policy"] = CAPTAIN_SHORTLIST_POLICY_ID
            if replay is not None:
                lineup_rows[0]["lineup_control_comparison"] = build_comparison(
                    lineup_rows, paired_rows[1], replay, profile=rule_profile,
                    context_multiplier=context_multiplier,
                )
            return lineup_rows

        # Decision variables
        x = pulp.LpVariable.dicts("player", index_range, lowBound=0, upBound=1, cat="Binary")

        model = pulp.LpProblem("DK_Lineup", pulp.LpMaximize)
        objective_expression = pulp.lpSum(
            pool.loc[i, score_col] * x[i] for i in index_range
        )
        control_objective = pulp.lpSum(
            (pool.loc[i, score_col] - context_multiplier * _safe_float(pool.loc[i].get("optimizer_context_adjustment"))) * x[i]
            for i in index_range
        )
        if rule_profile is not None:
            rule_players = pool.to_dict(orient="records")
            correlation_terms = build_lineup_correlation_terms(
                rule_players, profile=rule_profile
            )
            objective_expression += add_lineup_correlation_objective(
                model,
                correlation_terms,
                selected_vars=x,
                prefix="classic_rule_correlation",
            )
            objective_expression += add_format_specific_objective(
                model,
                build_format_specific_terms(
                    rule_players, profile=rule_profile
                ),
                selected_vars=x,
                prefix="classic_format_rule",
            )
        else:
            correlation_bonus = float(
                params.get("correlation_bonus", 0.0) or 0.0
            )
        if rule_profile is None and correlation_bonus > 0:
            team_field = "player_team" if "player_team" in pool.columns else "team"
            for qb_index in [
                i for i in index_range if str(pool.loc[i, "position"]).upper() == "QB"
            ]:
                quarterback_team = str(pool.loc[qb_index, team_field]).upper()
                for receiver_index in [
                    i
                    for i in index_range
                    if i != qb_index
                    and str(pool.loc[i, team_field]).upper() == quarterback_team
                    and str(pool.loc[i, "position"]).upper() in {"WR", "TE"}
                ]:
                    pair = pulp.LpVariable(
                        f"soft_stack_{qb_index}_{receiver_index}",
                        lowBound=0,
                        upBound=1,
                        cat="Binary",
                    )
                    model += pair <= x[qb_index]
                    model += pair <= x[receiver_index]
                    model += pair >= x[qb_index] + x[receiver_index] - 1
                    objective_expression += correlation_bonus * pair
        model += objective_expression

        # Salary cap
        model += pulp.lpSum(pool.loc[i, "salary"] * x[i] for i in index_range) <= SALARY_CAP

        # Roster size
        model += pulp.lpSum(x[i] for i in index_range) == 9

        # Position constraints
        qb_idx = self._position_mask(pool, ["QB"])
        rb_idx = self._position_mask(pool, ["RB"])
        wr_idx = self._position_mask(pool, ["WR"])
        te_idx = self._position_mask(pool, ["TE"])
        dst_idx = self._position_mask(pool, ["DST", "D", "DEF"])

        model += pulp.lpSum(x[i] for i in qb_idx) == 1
        model += pulp.lpSum(x[i] for i in dst_idx) == 1
        model += pulp.lpSum(x[i] for i in rb_idx) >= 2
        model += pulp.lpSum(x[i] for i in wr_idx) >= 3
        model += pulp.lpSum(x[i] for i in te_idx) >= 1
        if enforce_single_te:
            model += pulp.lpSum(x[i] for i in te_idx) <= 1

        if params.get("single_lineup_user_controls"):
            from .single_lineup import apply_lineup_constraints
            apply_lineup_constraints(model, pool, x, params["single_lineup_user_controls"],
                cutoff=params.get("single_lineup_cutoff"))

        # Team exposure limit
        for team, team_df in pool.groupby("player_team"):
            idx = team_df.index.tolist()
            model += pulp.lpSum(x[i] for i in idx) <= TEAM_LIMIT

        # Avoid offensive players vs selected DST
        if avoid_dst_opponents and dst_idx:
            for d_idx in dst_idx:
                dst_team = str(pool.loc[d_idx, "player_team"]).upper()
                dst_opp = str(pool.loc[d_idx].get("opponent_team", "")).upper()
                if not dst_opp:
                    continue
                for i in index_range:
                    if i == d_idx:
                        continue
                    pos = str(pool.loc[i, "position"] if "position" in pool.columns else "").upper()
                    if pos in ("DST", "D", "DEF"):
                        continue
                    player_team = str(pool.loc[i, "player_team"]).upper()
                    if player_team == dst_opp:
                        model += x[i] + x[d_idx] <= 1

        # Prevent duplicate player selections if multiple rows with same id
        for pid, pid_df in pool.groupby("player_id"):
            idx = pid_df.index.tolist()
            model += pulp.lpSum(x[i] for i in idx) <= 1

        for i in index_range:
            if str(pool.loc[i, "player_id"]) in locked_ids:
                model += x[i] == 1

        # Exposure caps (remaining count for each player across multi-lineup generation)
        if exposure_remaining:
            for i in index_range:
                pid = str(pool.loc[i, "player_id"])
                remaining = exposure_remaining.get(pid)
                if (
                    pid not in locked_ids
                    and remaining is not None
                    and remaining <= 0
                ):
                    model += x[i] == 0

        # Avoid duplicate lineups
        if exclude_lineups:
            valid_idx = set(index_range)
            for lineup_indices in exclude_lineups:
                idxs = [i for i in lineup_indices if i in valid_idx]
                if not idxs:
                    continue
                model += pulp.lpSum(x[i] for i in idxs) <= len(idxs) - 1
        if exclude_signatures:
            pid_to_idx = {}
            for i, pid in enumerate(pool["player_id"].astype(str)):
                pid_to_idx.setdefault(pid, []).append(i)
            for signature in exclude_signatures:
                idxs = []
                target_len = len(signature)
                for pid, _role in signature:
                    idxs.extend(pid_to_idx.get(str(pid), []))
                if idxs:
                    model += pulp.lpSum(x[i] for i in idxs) <= max(0, target_len - 1)

        stack_mode = "cash" if contest_type == "cash" else "gpp"
        stack_cfg = {
            "mode": stack_mode,
            "stack_min": 1 if stack_mode == "cash" else 2,
            "stack_max": None,
            "bringback": True,
            "include_rb_in_stack": False,
            "bringback_positions": ["WR", "TE"],
            **params,
        }
        stack_meta = (
            self.add_qb_stacking_constraints(model, x, pool, stack_cfg)
            if bool(stack_cfg.get("enabled", True))
            else {}
        )

        if additional_constraints is not None:
            additional_constraints(model, pool, x)
        solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=10, threads=1, options=["randomSeed 1"]) if score_col == "workload_utility" or (stack_params or {}).get('bounded_scenario_comparison') else pulp.PULP_CBC_CMD(msg=False)
        status = model.solve(solver)
        if status != pulp.LpStatusOptimal:
            return None

        lineup_rows = []
        for i in index_range:
            if pulp.value(x[i]) >= 0.9:
                row = pool.loc[i].to_dict()
                lineup_rows.append(row)
        if include_control_comparison:
            replay = solve_control(model, control_objective)
            replay["variable_players"] = {
                variable.name: {"player_id": str(pool.loc[i, "player_id"]), "roster_position": str(pool.loc[i, "position"])}
                for i, variable in x.items()
            }
            control_rows = [pool.loc[i].to_dict() for i in index_range if replay["values"].get(x[i].name, 0) >= 0.9]
            lineup_rows[0]["lineup_control_comparison"] = build_comparison(
                lineup_rows, control_rows, replay, profile=rule_profile,
                context_multiplier=context_multiplier,
            )
        if stack_meta:
            self._validate_stack_solution(lineup_rows, stack_meta)
        if lineup_rows:
            total_salary = sum(float(r.get("salary", 0) or 0) for r in lineup_rows)
            total_obj = sum(float(r.get(score_col, 0) or 0) for r in lineup_rows)
            print(f"[solve] total salary used={total_salary}, total {score_col}={total_obj}")
            print("[solve] selected players:")
            for r in lineup_rows:
                print(f"  {r.get('name')} {r.get('position')} team={r.get('player_team')} opp={r.get('opponent_team')} "
                      f"salary={r.get('salary')} proj={r.get('projection')} p90={r.get('p90')}")
            qb_rows = [r for r in lineup_rows if str(r.get("position", "")).upper() == "QB"]
            if qb_rows:
                qb = qb_rows[0]
                qb_team = str(qb.get("player_team", "")).upper()
                qb_opp = str(qb.get("opponent_team", "")).upper()
                include_rb = bool(params.get("include_rb_in_stack", False))
                pass_positions = {"WR", "TE"}
                if include_rb:
                    pass_positions.add("RB")
                same_team = [r for r in lineup_rows if str(r.get("player_team", "")).upper() == qb_team and str(r.get("position", "")).upper() in pass_positions and r is not qb]
                bringback_positions = {p.upper() for p in params.get("bringback_positions", {"WR", "TE"})}
                bringbacks = [r for r in lineup_rows if str(r.get("player_team", "")).upper() == qb_opp and str(r.get("position", "")).upper() in bringback_positions]
                print(f"[solve] QB={qb.get('name')} team={qb_team} opp={qb_opp} stack_count={len(same_team)} bringbacks={len(bringbacks)}")
        return lineup_rows

    def run_job(
        self,
        season: int,
        week: int,
        slate: str,
        strategy: str,
        params: dict,
        contest_format: str | None = None,
        objective: str | None = None,
        projection_run_id: str | None = None,
        rule_run_id: str | None = None,
        data_cutoff_at: datetime | None = None,
        optimizer_run_id: str | None = None,
        *,
        allow_incomplete_evidence: bool = False,
        progress=None,
    ) -> OptimizerJob:
        job_id = optimizer_run_id or str(uuid.uuid4())
        if optimizer_run_id:
            existing = self.get_job(optimizer_run_id)
            if existing is not None and existing.status == "completed":
                return existing
            if existing is not None and existing.params.get("showdown_evidence_snapshot"):
                raise ValueError("This optimizer run already has frozen Showdown evidence; start a new run")
            if existing is not None and existing.params.get("classic_evidence_snapshot"):
                raise ValueError("This optimizer run already has frozen Classic evidence; start a new run")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        params = dict(params or {})
        from .classic_highest_projection import normalize_request as normalize_highest_projection
        showdown_scenario = bool(params.get('scenario_mode')) and contest_format == 'showdown'
        if showdown_scenario:
            from .optimizer_scenario_mode import normalize_showdown_request
            if strategy != SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID or objective != 'gpp':
                raise ValueError('Showdown scenario comparison requires Captain GPP')
            normalize_showdown_request(params)
        highest_projection = False if showdown_scenario else normalize_highest_projection(params, contest_format=contest_format, strategy=strategy)
        if params.get("scenario_mode") and (not (highest_projection or showdown_scenario) or not params.get("prepared_input_job_id")):
            raise ValueError("Scenario mode requires its prepared Classic one-lineup comparison")
        if params.get("scenario_mode") and params.get("workload_comparison"):
            raise ValueError("Scenario mode cannot be combined with a different scoring comparison")
        params.pop("analyst_handoff_applied", None)  # Only a verified saved handoff may assert application.
        if params.get("prepared_input_job_id"):
            from sqlalchemy.orm import Session
            from .analyst_preparation import bind_saved_preparation
            with Session(self.engine) as analyst_preparation_session:
                handoff_payload = {"season": season, "week": week, "slate": slate,
                    "contest_format": contest_format, "objective": objective, "params": params}
                bind_saved_preparation(analyst_preparation_session, handoff_payload)
        merged_analyst = params.get("analyst_strategy") == "MERGED_SCENARIOS"
        from .shared_world_selection import POLICY as SHARED_WORLD_POLICY
        shared_world_mode = params.get("analyst_selection_policy") == SHARED_WORLD_POLICY
        if shared_world_mode and (not merged_analyst or highest_projection or not params.get("prepared_input_job_id")):
            raise ValueError("Shared-world optimization requires its explicit prepared automatic Analyst workflow")
        if params.get("analyst_strategy", "CONSTRUCTION") not in {"CONSTRUCTION", "MERGED_SCENARIOS"}:
            raise ValueError("Unknown Analyst strategy")
        if merged_analyst and not params.get("analyst_packet_sha256") and not params.get("workload_comparison"):
            raise ValueError("Merged Analyst strategy requires an imported scenario packet")
        single_lineup = strategy in SINGLE_LINEUP_STRATEGIES
        if single_lineup:
            expected_format = SINGLE_LINEUP_STRATEGIES[strategy]
            if contest_format not in {None, expected_format} or objective not in {None, "cash"}:
                raise ValueError("Single-lineup strategy requires its matching format and cash objective")
            contest_format, objective = expected_format, "cash"
            normalize_single_lineup_params(params, contest_format=expected_format)
        from .showdown_data_readiness import (
            evaluate_readiness, freshness_rules, freeze_evidence,
            requires_ownership, is_live_slate, ShowdownDataNotReady,
        )
        if type(allow_incomplete_evidence) is not bool:
            raise ValueError("allow_incomplete_evidence must be an explicit boolean")
        # Readiness and frozen evidence are server-owned. Request JSON cannot
        # bypass the gate or assert that another run's evidence was consumed.
        params.pop("preliminary_report", None)  # Server-owned research classification cannot be forged.
        params.pop("data_readiness", None)
        params.pop("showdown_evidence_snapshot", None)
        params.pop("classic_evidence_snapshot", None)
        params.pop("classic_final_input_proof", None)
        if "allow_incomplete_evidence" in params:
            raise ValueError("Incomplete evidence override is available only to internal/offline callers")
        params.pop("prepared_input_evidence", None)  # Only verified server lineage may claim preparation.
        if params.get("prepared_input_job_id"):
            from sqlalchemy.orm import Session
            from .slate_preparation import validate_prepared_optimizer
            with Session(self.engine) as preparation_session:
                params["prepared_input_evidence"] = validate_prepared_optimizer(preparation_session, {
                    "season": season, "week": week, "slate": slate,
                    "contest_format": contest_format, "objective": objective, "strategy": strategy,
                    "projection_run_id": projection_run_id, "params": params})
        if "exclude_questionable" in params and type(params["exclude_questionable"]) is not bool:
            raise ValueError("params.exclude_questionable must be an explicit boolean")

        contest_format, objective, contest_type = resolve_optimizer_mode(
            contest_format=contest_format,
            objective=objective,
            params=params,
        )
        validate_showdown_qb_preferences(params, showdown=contest_format == "showdown")
        validate_showdown_captain_preferences(params, showdown=contest_format == "showdown")
        if contest_format == "showdown":
            params["captain_positions"] = allowed_captain_positions(params)
            params["max_players_per_team"] = showdown_team_limit(params)
        strategy_config = resolve_optimizer_strategy(
            contest_format=contest_format,
            objective=objective,
            strategy=strategy,
        )
        strategy = str(strategy_config["strategy_id"])
        if params.get("workload_comparison"):
            if contest_format != "showdown" or objective != "gpp" or strategy != SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID:
                raise ValueError("Workload optimization currently requires the normal Captain GPP workflow")
            if params.get("classic_selection_mode") == "HIGHEST_PROJECTION":
                raise ValueError("Choose one comparison objective")
            if params['workload_comparison'] in {'learned_counts','learned_yards','scenario_first'} and (params.get('require_team_leader') or params.get('require_home_team_leader')):
                raise ValueError('Learned opportunities cannot use points-based team leader requirements')
        if merged_analyst and objective != "gpp":
            raise ValueError("Merged Analyst scenarios require a GPP strategy")
        from .classic_portfolio_controls import validate_large_gpp_controls
        validate_large_gpp_controls(params, strategy)
        from .classic_primary_game import resolve_primary_game_cap
        primary_game_cap = resolve_primary_game_cap(params.get("max_lineups_per_primary_game"))
        if strategy == CLASSIC_LARGE_GPP_STRATEGY_ID and params.get("classic_expanded_discovery"):
            raise ValueError("Expanded Large-GPP discovery requires an explicitly labelled RESEARCH_SHADOW; use the offline research command")
        if primary_game_cap is not None and (strategy not in {CLASSIC_LARGE_GPP_STRATEGY_ID, CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID, CLASSIC_SINGLE_LINEUP_STRATEGY_ID}):
            raise ValueError("Max lineups per primary game requires Classic")
        if strategy == CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID and "max_lineups_per_primary_game" in params:
            portfolio_constraints = dict(params.get("portfolio_constraints") or {})
            if portfolio_constraints.get("canonical_game_cap") is not None and portfolio_constraints["canonical_game_cap"] != primary_game_cap:
                raise ValueError("Conflicting primary-game concentration constraints")
            portfolio_constraints["canonical_game_cap"] = primary_game_cap
            params["portfolio_constraints"] = portfolio_constraints
        if "long_shot_mode" in params and type(params["long_shot_mode"]) is not bool:
            raise ValueError("params.long_shot_mode must be an explicit boolean")
        long_shot_mode = bool(params.get("long_shot_mode", False))
        if long_shot_mode and objective != "gpp":
            raise ValueError("Long-shot mode is available only for GPP optimization")
        if long_shot_mode:
            params["num_lineups"] = 1
        if contest_format == "showdown":
            # The legacy request field is accepted for saved-run compatibility;
            # Showdown legality now permits any number of tight ends.
            params["enforce_single_te"] = False
            margin = float(params.get("showdown_decisive_margin", DEFAULT_DECISIVE_MARGIN))
            if not math.isfinite(margin) or margin < 7 or margin > 35:
                raise ValueError("showdown_decisive_margin must be between 7 and 35")
            params["showdown_decisive_margin"] = margin
            if type(params.get("require_scenario_diversity", False)) is not bool:
                raise ValueError("require_scenario_diversity must be an explicit boolean")
            params["require_scenario_diversity"] = bool(params.get("require_scenario_diversity", False))
            if type(params.get("soft_scenario_diversity", False)) is not bool:
                raise ValueError("soft_scenario_diversity must be an explicit boolean")
            params["soft_scenario_diversity"] = params.get("soft_scenario_diversity", False)
            if params["soft_scenario_diversity"] and params["require_scenario_diversity"]:
                raise ValueError("Legacy required coverage and soft scenario diversity are mutually exclusive")
        params["strategy_config"] = strategy_config
        optimizer_rules = (
            showdown_optimizer_rules(strategy)
            if contest_format == "showdown"
            else []
        )
        if shared_world_mode:
            from .shared_world_runtime import LEGACY_STACK_RULES
            params["shared_world_omitted_strategy_rules"] = [r for r in optimizer_rules if r["rule_id"] in LEGACY_STACK_RULES]
            optimizer_rules = [r for r in optimizer_rules if r["rule_id"] not in LEGACY_STACK_RULES]
        params["optimizer_rules"] = optimizer_rules
        require_qb_captain_receiver = any(
            rule.get("rule_id") == SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID
            for rule in optimizer_rules
        )
        if strategy == CLASSIC_GPP_ADVANCED_STRATEGY_ID:
            unsupported_stack_fields = {
                field
                for field in (
                    "stack_policy_id",
                    "stack_min",
                    "stack_max",
                    "bringback",
                    "include_rb_in_stack",
                    "bringback_positions",
                )
                if field in params
            }
            if unsupported_stack_fields:
                raise ValueError(
                    f"{CLASSIC_GPP_ADVANCED_STRATEGY_ID} owns its slate-aware "
                    "stack policy and cannot be combined with: "
                    + ", ".join(sorted(unsupported_stack_fields))
                )
        if single_lineup:
            from .single_lineup import POLICY_ID, WEIGHTS
            params["objective_config"] = {"objective_id": strategy, "selection_policy": POLICY_ID,
                "objective_weights": dict(WEIGHTS), "evidence_status": "transparent_proxy_unvalidated"}
        elif strategy == CLASSIC_HEAD_TO_HEAD_STRATEGY_ID:
            params["objective_config"] = head_to_head_objective_config()
        elif contest_format == "classic" and objective == "cash":
            params["objective_config"] = cash_objective_config()
        if contest_format == "showdown" and not single_lineup:
            informed_showdown = (
                strategy in SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_IDS
            )
            settings = get_settings()
            params["objective_config"] = {
                "objective_id": strategy,
                "score_column": "showdown_cash_score" if objective == "cash" else "optimizer_context_ceiling_score",
                "scoring_version": "showdown_cash_distribution_v1" if objective == "cash" else "context_ceiling_v1",
                "captain_multiplier": 1.5,
                "captain_slots": 1,
                "flex_slots": 5,
                "salary_cap": SALARY_CAP,
                "max_players_per_team": params["max_players_per_team"],
                "starter_qb_policy": "one_per_team_evidence_hierarchy_v1",
                "optimizer_rules": optimizer_rules,
                "evidence_status": strategy_config["evidence_status"],
            }
            if informed_showdown:
                params["objective_config"].update(
                    {
                        "captain_model_path": settings.showdown_captain_model_path,
                        "captain_prior_strength": settings.showdown_captain_prior_strength,
                        "captain_evaluation_slates": 39,
                    }
                )
        if highest_projection:
            from .classic_highest_projection import stack_policy as highest_projection_stack_policy
            stack_policy = highest_projection_stack_policy()
            params["objective_config"] = {
                "objective_id": "baseline_mean", "score_column": "projection",
                "objective_weights": {"mean": 1.0}, "conditional_adjustments": False,
                "description": "Highest unchanged baseline projection; stacks and bringbacks optional; no player locks.",
            }
        elif strategy == CLASSIC_GPP_ADVANCED_STRATEGY_ID:
            stack_policy = {
                "policy_id": "classic_gpp_slate_aware_stack_v1",
                "contest_format": "classic",
                "objective": "gpp",
                "enabled": True,
                "stack_min": 1,
                "stack_max": None,
                "bringback": True,
                "include_rb_in_stack": True,
                "bringback_positions": ["RB", "WR", "TE"],
                "evidence_status": "resolved_at_runtime",
                "description": (
                    "The selected strategy resolves the exact stack minimum "
                    "from slate size at runtime."
                ),
                "source": "optimizer_strategy",
            }
        elif single_lineup:
            stack_policy = {
                "policy_id": "single_lineup_optional_stack_v1", "contest_format": contest_format,
                "objective": "cash", "enabled": False, "stack_min": 0, "stack_max": None,
                "bringback": False, "include_rb_in_stack": False, "bringback_positions": [],
                "source": "optimizer_strategy", "evidence_status": "transparent_proxy_unvalidated",
                "description": "Optional stacks; shared-outcome risk is assessed by the selector.",
            }
        elif strategy == CLASSIC_HEAD_TO_HEAD_STRATEGY_ID:
            stack_policy = {
                "policy_id": "classic_head_to_head_optional_stack_unconstrained_v1",
                "contest_format": "classic",
                "objective": "cash",
                "enabled": False,
                "stack_min": 0,
                "stack_max": None,
                "bringback": False,
                "include_rb_in_stack": False,
                "bringback_positions": [],
                "correlation_bonus": DEFAULT_HEAD_TO_HEAD_OBJECTIVE.correlation_bonus,
                "evidence_status": "explicit_contest_strategy",
                "description": "Correlation is rewarded softly; no stack or bring-back is required.",
                "source": "optimizer_strategy",
            }
        elif strategy == CLASSIC_LARGE_GPP_STRATEGY_ID:
            stack_policy = {
                "policy_id": "classic_large_gpp_flexible_stacks_v1",
                "contest_format": "classic",
                "objective": "gpp",
                "enabled": True,
                "stack_min": 1,
                "stack_max": None,
                "bringback": False,
                "include_rb_in_stack": True,
                "bringback_positions": ["RB", "WR", "TE"],
                "stack_templates": params.get(
                    "stack_templates", [[1, 0], [1, 1], [2, 0], [2, 1]]
                ),
                "evidence_status": "explicit_contest_strategy",
                "description": "Portfolio cycles QB+1/QB+2 with optional bring-backs.",
                "source": "optimizer_strategy",
            }
        else:
            stack_policy = resolve_stacking_policy(
                contest_format=contest_format,
                objective=objective,
                params=params,
            )
        params["stack_policy_id"] = stack_policy["policy_id"]
        params["stack_policy"] = stack_policy
        live_showdown = contest_format == "showdown" and is_live_slate(self, season=season, week=week, slate=slate)
        classic_readiness_strategy = strategy in {CLASSIC_LARGE_GPP_STRATEGY_ID, CLASSIC_SINGLE_LINEUP_STRATEGY_ID}
        live_classic = classic_readiness_strategy and is_live_slate(self, season=season, week=week, slate=slate)
        if (classic_readiness_strategy and not live_classic or single_lineup and not (live_classic or live_showdown)) and not allow_incomplete_evidence:
            raise ValueError("Historical generation requires an explicit internal preview or frozen strategy-contract replay; it cannot assert live READY")
        source_refresh = {}
        if (live_showdown or live_classic) and not allow_incomplete_evidence:
            prepared = params.get("prepared_input_evidence") or {}
            if prepared.get("action") != "prepare":
                raise ValueError("Prepare slate for optimization first. Source repair and projection builds run in slate preparation.")
            data_cutoff_at = datetime.fromisoformat(str(prepared["data_cutoff_at"]).replace("Z", "+00:00"))
            rule_run_id = None
            params["ownership_run_id"] = prepared["ownership_run_id"]
            source_refresh = prepared["source_refresh"]
        # A live build with no new projection must stay empty. Resolving None
        # through the ordinary saved-input selector would silently pick an old
        # active projection and contaminate the blocked run's coverage report.
        if not ((live_classic or live_showdown) and not allow_incomplete_evidence and projection_run_id is None):
            projection_run_id, rule_run_id, data_cutoff_at = self._resolve_run_lineage(
                season=season,
                week=week,
                slate=slate,
                projection_run_id=projection_run_id,
                rule_run_id=rule_run_id,
                data_cutoff_at=data_cutoff_at,
            )
        if projection_run_id is None and not (live_showdown or live_classic) and not allow_incomplete_evidence:
            raise ValueError(f"No completed projection is available for {season} Week {week} {slate}")

        projection_market_audit: dict = {}
        historical_captain_report: dict = {}
        historical_qb_pool: list[dict] = []
        if contest_format == "showdown":
            historical_path = (Path(__file__).resolve().parents[3]
                               / "docs/showdown_captain_optimality_2024_2026.json")
            try:
                candidate_report = json.loads(historical_path.read_text(encoding="utf-8"))
                latest = candidate_report.get("latest_completed_period") or []
                if len(latest) == 2 and (int(latest[0]), int(latest[1])) < (season, week):
                    historical_captain_report = candidate_report
                    params.setdefault("strategy_runtime", {})[
                        "historical_captain_optimality"
                    ] = {"status": "available", "source_sha256": candidate_report.get("source_sha256"),
                         "slate_count": candidate_report.get("slate_count"),
                         "prior_application": candidate_report.get("prior_application")}
                else:
                    historical_captain_report = {"status": "unavailable_future_or_same_period_artifact"}
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                historical_captain_report = {"status": "unavailable", "reason": str(exc)}
        if contest_format == "showdown" and self.engine.dialect.name == "postgresql":
            with self.engine.connect() as connection:
                market_row = connection.execute(text("""
                    SELECT mr.params_json -> 'calibration' -> 'market_context' AS market_context
                    FROM target.projection_run pr
                    JOIN target.model_run mr ON mr.model_run_id = pr.model_run_id
                    WHERE pr.projection_run_id = :run_id
                """), {"run_id": projection_run_id}).scalar_one_or_none()
            if isinstance(market_row, dict):
                projection_market_audit = market_row
                params.setdefault("strategy_runtime", {})["projection_market_audit"] = market_row

        pool = self._load_player_pool(
            season,
            week,
            slate,
            projection_run_id=projection_run_id,
            ownership_run_id=(
                str(params.get("ownership_run_id"))
                if params.get("ownership_run_id")
                else None
            ),
            **({"evidence_cutoff_at": data_cutoff_at or now} if live_showdown or live_classic else {}),
            require_explicit_runs=bool((live_showdown or live_classic) and not allow_incomplete_evidence),
        )
        from .kicker_roles import assign_kicker_roles
        pool, kicker_runtime = assign_kicker_roles(pool)
        params.setdefault("strategy_runtime", {})["kicker_role_gate"] = kicker_runtime
        from .player_roles import resolve_player_roles
        pool, role_runtime = resolve_player_roles(pool)
        params.setdefault("strategy_runtime", {})["current_slate_role_availability_audit"] = role_runtime
        # Roles are resolved above; keep bulky source facts out of pandas copies
        # for both normal Classic and frozen preliminary research. The original
        # preliminary snapshot retains its exact full metadata and checksum.
        classic_role_context = pool.attrs.pop("role_context", []) if contest_format == "classic" else []
        if live_classic and not allow_incomplete_evidence:
            from . import classic_data_readiness as classic_gate
            # Keep full source facts in the durable evidence envelope, rather
            # than copying them on every pandas column/row operation.
            cutoff = data_cutoff_at or datetime.now(timezone.utc)
            evaluated = datetime.now(timezone.utc)
            try:
                evidence = classic_gate.read_evidence(self, season=season, week=week, slate=slate,
                    projection_run_id=projection_run_id, cutoff=cutoff)
            except Exception as exc:
                logger.exception("Classic canonical evidence read failed")
                evidence = {"read_error": f"{type(exc).__name__}: {str(exc)[:1000]}"}
            readiness = classic_gate.evaluate_readiness(_json_safe(pool.to_dict("records")),
                season=season, week=week, slate=slate, projection_run_id=projection_run_id,
                evidence_cutoff=cutoff, evaluated_at=evaluated,
                rules=classic_gate.freshness_rules(get_settings()), evidence=_json_safe(evidence),
                refresh=_json_safe(source_refresh))
            readiness.update(solver_called=False, override_used=False)
            params["data_readiness"] = readiness
            frozen_job = OptimizerJob(job_id=job_id, status="running" if readiness["status"] == "READY" else "failed",
                created_at=now, updated_at=now, season=season, week=week, slate=slate, strategy=strategy,
                contest_format=contest_format, objective=objective, params=params, projection_run_id=projection_run_id,
                rule_run_id=rule_run_id, data_cutoff_at=cutoff, message="Validating Classic inputs")
            if readiness["status"] != "READY":
                frozen_job.message = str(classic_gate.ClassicDataNotReady(readiness))
                frozen_job.lineage_persisted = self._persist_optimizer_run(frozen_job)
                self._cache_job(frozen_job)
                raise classic_gate.ClassicDataNotReady(readiness)
            frozen = classic_gate.freeze_evidence(_json_safe(pool.to_dict("records")), readiness,
                optimizer_run_id=job_id, evidence=_json_safe(evidence),
                role_context=_json_safe(classic_role_context))
            params["classic_evidence_snapshot"] = frozen
            readiness.update(frozen_at=frozen["frozen_at"], snapshot_id=job_id, snapshot_sha256=frozen["sha256"])
            frozen_job.message = "Classic evidence frozen before generation"
            if not self._persist_optimizer_run(frozen_job):
                raise ValueError("Classic evidence freeze could not be persisted; candidate generation blocked")
            pool = pd.DataFrame(deepcopy(frozen["player_pool"]))
            if progress:
                progress("evidence_frozen", 1, 1, frozen_job.message)
        elif classic_readiness_strategy and allow_incomplete_evidence:
            from . import classic_data_readiness as classic_gate
            cutoff = data_cutoff_at or datetime.now(timezone.utc)
            try:
                evidence = classic_gate.read_evidence(self, season=season, week=week, slate=slate,
                    projection_run_id=projection_run_id, cutoff=cutoff)
            except Exception as exc:
                evidence = {"read_error": f"{type(exc).__name__}: {str(exc)[:1000]}"}
            readiness = classic_gate.evaluate_readiness(_json_safe(pool.to_dict("records")),
                season=season, week=week, slate=slate, projection_run_id=projection_run_id,
                evidence_cutoff=cutoff, evaluated_at=datetime.now(timezone.utc),
                rules=classic_gate.freshness_rules(get_settings()), evidence=_json_safe(evidence))
            readiness.update(source_status=readiness["status"], status="DEVELOPMENT_PREVIEW",
                non_production_override=True, override_used=True, solver_called=False)
            readiness["reason_codes"].append("explicit_internal_incomplete_evidence_preview")
            params["data_readiness"] = readiness
        if live_showdown or (allow_incomplete_evidence and contest_format == "showdown"):
            # The projection contract defaults availability probability to 1.
            # Only an explicitly supplied sourced fact can establish readiness.
            contexts = {str(r.get("player_master_id")): r for r in pool.attrs.get("role_context", [])}
            pool["player_status_evidence_present"] = [bool(
                (context := contexts.get(str(row.get("player_id")), {})).get("source")
                and (context.get("injury_status") or
                     (context.get("evidence_json") or {}).get("roster_status") or
                     type((context.get("evidence_json") or {}).get("game_active")) is bool))
                for row in pool.to_dict("records")]
            if progress:
                progress("data_readiness", 0, 1, "Validating the refreshed Showdown inputs before generation.")
            cutoff = data_cutoff_at or now
            readiness = evaluate_readiness(_json_safe(pool.to_dict("records")), season=season, week=week,
                slate=slate, projection_run_id=projection_run_id, evidence_cutoff=cutoff, evaluated_at=now,
                rules=freshness_rules(get_settings()), ownership_required=requires_ownership(params),
                ownership_attempted="ownership" in source_refresh, refresh=_json_safe(source_refresh),
                require_canonical_context="canonical_player_context" in source_refresh,
                minimum_player_salary=params.get("minimum_player_salary"))
            if live_showdown and source_refresh.get("projection", {}).get("status") == "ERROR":
                readiness["status"] = "ERROR"
                readiness["reason_codes"] = sorted(set(readiness["reason_codes"] + ["projection_refresh_failed"]))
                readiness["required_sources"]["projection"]["status"] = "NOT_READY"
                readiness["required_sources"]["projection"]["reason_codes"].append("projection_refresh_failed")
            if live_showdown and source_refresh.get("projection", {}).get("status") == "blocked":
                readiness["status"] = "NOT_READY"
                readiness["reason_codes"] = sorted(set(readiness["reason_codes"] + ["player_context_unresolved"]))
                readiness["required_sources"]["projection"]["status"] = "NOT_READY"
                readiness["required_sources"]["projection"]["reason_codes"].append("player_context_unresolved")
            readiness["player_pool_readiness"]["status"] = readiness["status"]
            readiness["player_pool_readiness"]["readiness_blockers"] = readiness["reason_codes"]
            params["data_readiness"] = readiness
            params["player_pool_readiness"] = readiness["player_pool_readiness"]
            frozen_job = OptimizerJob(job_id=job_id, status="running" if readiness["status"] == "READY" or allow_incomplete_evidence else "failed",
                created_at=now, updated_at=now, season=season, week=week, slate=slate, strategy=strategy,
                contest_format=contest_format, objective=objective, params=params, projection_run_id=projection_run_id,
                rule_run_id=rule_run_id, data_cutoff_at=cutoff, message="Validating Showdown inputs")
            if readiness["status"] != "READY" and not allow_incomplete_evidence:
                frozen_job.message = str(ShowdownDataNotReady(readiness))
                frozen_job.lineage_persisted = self._persist_optimizer_run(frozen_job)
                self._cache_job(frozen_job)
                raise ShowdownDataNotReady(readiness)
            # Ignore unavailable/stale optional ownership in every downstream
            # score and classification; retain the assessment and source IDs.
            if not readiness["ownership"]["ownership_fresh"]:
                for column in ("ownership", "captain_ownership", "flex_ownership"):
                    pool[column] = None
            frozen = freeze_evidence(_json_safe(pool.to_dict("records")), readiness, optimizer_run_id=job_id,
                role_context=_json_safe(pool.attrs.get("role_context", [])),
                allow_incomplete_evidence=allow_incomplete_evidence)
            params["showdown_evidence_snapshot"] = frozen
            frozen_job.message = "NON-PRODUCTION incomplete-evidence override" if allow_incomplete_evidence else "Showdown evidence frozen before generation"
            if not self._persist_optimizer_run(frozen_job):
                raise ValueError("Showdown evidence freeze could not be persisted; candidate generation blocked")
            # Generation receives an independent copy of precisely the saved
            # rows; no subsequent source read can replace these inputs.
            pool = pd.DataFrame(frozen["player_pool"])
            pool.attrs["role_context"] = deepcopy(frozen["role_context"])
            if progress:
                progress("evidence_frozen", 1, 1, frozen_job.message)
        initial_pool = pool.copy()
        from .showdown_team_leader_preferences import leader_preference
        team_leader_preference = leader_preference(initial_pool, params, engine=self.engine, season=season, week=week) if contest_format == "showdown" else {"enabled": False, "required_player_ids": []}
        params.setdefault("strategy_runtime", {})["team_leader_preference"] = team_leader_preference
        from .classic_season_rank_preferences import preference as season_rank_preference
        season_rank_report = season_rank_preference(self.engine, params, season=season, week=week) if contest_format == "classic" else {"enabled": False, "eligible_ids": {}}
        params.setdefault("strategy_runtime", {})["season_ppg_rank_preference"] = season_rank_report
        season_ppg_eligible_ids = {pos: set(ids) for pos, ids in season_rank_report["eligible_ids"].items()}
        if season_rank_report["enabled"] or team_leader_preference["enabled"]:
            rank_job = OptimizerJob(job_id=job_id, status="running", created_at=now, updated_at=now,
                season=season, week=week, slate=slate, strategy=strategy, contest_format=contest_format,
                objective=objective, params=params, projection_run_id=projection_run_id, rule_run_id=rule_run_id,
                data_cutoff_at=data_cutoff_at, message="Season-average preference evidence frozen before selection")
            if not self._persist_optimizer_run(rank_job):
                raise ValueError("Season-average preference evidence could not be persisted; candidate generation blocked")
        eligible_pool_ids: set[str] = set()
        exclusion_reasons: dict[str, list[str]] = {}
        exclusion_details: dict[str, list[dict]] = {}
        player_warnings: dict[str, list[dict]] = {}
        for row in pool.to_dict("records"):
            if row.get("kicker_role_warning"):
                player_warnings[str(row["player_id"])] = [{
                    "reason_code": "kicker_primary_uncertain",
                    "description": row["kicker_role_warning"],
                }]
        safety_audit_by_player: dict[str, dict] = {}
        context_audit_by_player: dict[str, dict] = {}
        flex_only_ids = normalize_canonical_player_ids(
            params.get("flex_only_player_ids"),
            field_name="flex_only_player_ids",
        )
        resolved_flex_ids, flex_only_names = _resolve_player_control_names(
            initial_pool,
            params.get("flex_only_players"),
            field_name="FLEX-only",
        )
        flex_only_ids.update(resolved_flex_ids)
        if flex_only_ids and contest_format != "showdown":
            raise ValueError("FLEX-only player controls require Showdown format")
        initial_player_ids = (
            set(initial_pool["player_id"].astype(str))
            if not initial_pool.empty and "player_id" in initial_pool
            else set()
        )
        missing_flex_only_ids = flex_only_ids - initial_player_ids
        if missing_flex_only_ids:
            raise ValueError(
                "FLEX-only canonical player IDs were not found in the selected slate: "
                + ", ".join(sorted(missing_flex_only_ids))
            )
        requested_captain_id = str(params.get("locked_captain_player_id") or "").strip()
        if requested_captain_id and requested_captain_id not in initial_player_ids:
            raise ValueError("Locked Captain player ID was not found in the selected slate")
        if requested_captain_id and requested_captain_id in flex_only_ids:
            raise ValueError("Locked Captain cannot also be FLEX-only")
        qb_player_ids = set(
            initial_pool.loc[
                initial_pool["position"].astype(str).str.strip().str.upper() == "QB", "player_id"
            ].astype(str)
        ) if not initial_pool.empty else set()
        if params.get("no_qb_captain", False) and requested_captain_id in qb_player_ids:
            raise ValueError("Locked QB Captain conflicts with user preference: No QB Captain")
        captain_positions = allowed_captain_positions(params)
        captain_excluded_ids = set(
            initial_pool.loc[~initial_pool["position"].astype(str).str.strip().str.upper().isin(captain_positions), "player_id"].astype(str)
        ) if captain_positions and not initial_pool.empty else set()
        for key in ("captain_position_exception_ids", "questionable_eligible_player_ids"):
            unknown = named_preference_ids(params, key) - set(initial_pool["player_id"].astype(str))
            if unknown:
                raise ValueError(f"{key} contains players outside the prepared slate: " + ", ".join(sorted(unknown)))
        captain_excluded_ids -= named_preference_ids(params, "captain_position_exception_ids")
        if requested_captain_id and requested_captain_id in captain_excluded_ids:
            raise ValueError("Locked Captain conflicts with user preference: Captain position restricted to " + ", ".join(captain_positions))
        params["flex_only_player_ids"] = sorted(flex_only_ids)
        params["flex_only_players"] = sorted(flex_only_names)
        exclude_ids = normalize_canonical_player_ids(
            params.get("exclude_player_ids"),
            field_name="exclude_player_ids",
        )
        resolved_exclude_ids, excluded_player_names = _resolve_player_control_names(
            initial_pool,
            params.get("exclude_players"),
            field_name="Excluded",
        )
        exclude_ids.update(resolved_exclude_ids)
        params["exclude_player_ids"] = sorted(exclude_ids)
        params["exclude_players"] = sorted(excluded_player_names)
        opponent_values = params.get("exclude_opponent_teams") or []
        if isinstance(opponent_values, str):
            opponent_values = opponent_values.split(",")
        if not isinstance(opponent_values, (list, tuple, set)):
            raise ValueError("exclude_opponent_teams must be a list of team codes")
        excluded_opponent_teams = {
            str(value).strip().upper() for value in opponent_values if str(value).strip()
        }
        if any(not re.fullmatch(r"[A-Z]{2,3}", team) for team in excluded_opponent_teams):
            raise ValueError("exclude_opponent_teams must contain NFL team codes such as DEN")
        params["exclude_opponent_teams"] = sorted(excluded_opponent_teams)
        lock_values: list = []
        for lock_field in ("lock_player_ids", "locked_player_ids"):
            field_values = params.get(lock_field)
            if field_values is None:
                continue
            if isinstance(field_values, str):
                lock_values.append(field_values)
            else:
                lock_values.extend(field_values)
        locked_ids = normalize_canonical_player_ids(
            lock_values,
            field_name="locked_player_ids",
        )
        resolved_locked_ids, locked_player_names = _resolve_player_control_names(
            initial_pool,
            params.get("locked_players"),
            field_name="Locked",
        )
        locked_ids.update(resolved_locked_ids)
        if params.get("no_qbs", False) and (locked_ids | {requested_captain_id}) & qb_player_ids:
            raise ValueError("Locked QB conflicts with user preference: No QBs in the lineup")
        if contest_format == "showdown":
            locked_teams = initial_pool.loc[
                initial_pool["player_id"].astype(str).isin(locked_ids | {requested_captain_id}),
                "player_team",
            ].value_counts()
            if not locked_teams.empty and int(locked_teams.max()) > params["max_players_per_team"]:
                raise ValueError("Locked players conflict with Max players per team")
        if params.get("no_two_qbs", False) and len((locked_ids | {requested_captain_id}) & qb_player_ids) > 1:
            raise ValueError("Locked QBs conflict with user preference: No 2 QBs in the lineup")
        requested_exclude_names = set(excluded_player_names)
        conflicting_lock_names = {
            _normalize_alias(name) for name in locked_player_names
        } & {_normalize_alias(name) for name in requested_exclude_names}
        if conflicting_lock_names:
            raise ValueError(
                "Players cannot be both locked and excluded: "
                + ", ".join(sorted(conflicting_lock_names))
            )
        conflicting_controls = exclude_ids & locked_ids
        if conflicting_controls:
            raise ValueError(
                "Players cannot be both locked and excluded: "
                + ", ".join(sorted(conflicting_controls))
            )
        conflicting_flex_exclusions = exclude_ids & flex_only_ids
        if conflicting_flex_exclusions:
            raise ValueError(
                "Players cannot be both FLEX-only and excluded: "
                + ", ".join(sorted(conflicting_flex_exclusions))
            )
        roster_size = 6 if contest_format == "showdown" else 9
        if len(locked_ids) > roster_size:
            raise ValueError(
                f"At most {roster_size} canonical players can be locked for "
                f"{contest_format}"
            )
        params["locked_player_ids"] = sorted(locked_ids)
        params["locked_players"] = sorted(locked_player_names)

        rule_profile = resolve_strategy_profile(
            contest_format=contest_format,
            objective=objective,
        )
        if contest_format == "showdown" and objective == "cash" and not single_lineup:
            params["objective_config"]["objective_weights"] = dict(rule_profile.objective_weights)
        params.setdefault("strategy_runtime", {})["lineup_correlation"] = {
            "library_id": LINEUP_CORRELATION_LIBRARY_ID,
            "library_version": LINEUP_CORRELATION_LIBRARY_VERSION,
            "profile_id": rule_profile.profile_id,
            "profile_version": rule_profile.version,
            "objective_multiplier": 0.0 if contest_format == "showdown" else 1.0,
            "evidence_status": "initial_policy_unvalidated",
            "policy_alignment": strategy_config["policy_alignment"],
        }
        validate_player_pool_evidence_consistency(pool)
        safety_result = evaluate_player_pool_safety(
            pool,
            profile=rule_profile,
            expected_slate_teams=params.get("slate_teams"),
            as_of=datetime.now(timezone.utc),
            projection_cutoff=data_cutoff_at,
            user_excluded_player_ids=exclude_ids,
            exclude_questionable=params.get("exclude_questionable", False),
            questionable_eligible_player_ids=named_preference_ids(params, "questionable_eligible_player_ids"),
        )
        pool = safety_result.eligible_pool
        params.setdefault("strategy_runtime", {})["player_pool_safety"] = (
            safety_result.summary
        )
        for audit_row in safety_result.audit_rows:
            player_id = str(audit_row.get("player_id") or "")
            if not player_id:
                continue
            safety_audit_by_player[player_id] = audit_row
            exclusion_reasons[player_id] = list(
                audit_row.get("exclusion_reasons") or []
            )
            exclusion_details[player_id] = list(
                audit_row.get("exclusion_details") or []
            )
            player_warnings.setdefault(player_id, []).extend(audit_row.get("warnings") or [])

        context_result = score_player_context(pool, profile=rule_profile)
        pool = context_result.scored_pool
        raw_pool_ids = (
            set(pool["player_id"].astype(str))
            if not pool.empty and "player_id" in pool else set()
        )
        opportunity_eligible_ids = set(raw_pool_ids)
        params.setdefault("strategy_runtime", {})["context_scoring"] = (
            context_result.summary
        )
        for audit_row in context_result.audit_rows:
            player_id = str(audit_row.get("player_id") or "")
            if not player_id:
                continue
            context_audit_by_player[player_id] = audit_row
            warnings = player_warnings.setdefault(player_id, [])
            for warning in audit_row.get("warnings") or []:
                if not any(
                    existing.get("reason_code") == warning.get("reason_code")
                    for existing in warnings
                ):
                    warnings.append(warning)

        if not merged_analyst and not params.get("workload_comparison") and (strategy in {CAPTAIN_SINGLE_LINEUP_STRATEGY_ID, SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID, SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID, SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID} or strategy in SHOWDOWN_SINGLE_ENTRY_STRATEGY_IDS):
            pool, opportunity_excluded = apply_showdown_opportunity_gate(pool)
            opportunity_eligible_ids = set(pool["player_id"].astype(str))
            for player_id in opportunity_excluded:
                reason = "showdown_low_opportunity_skill_player"
                exclusion_reasons.setdefault(player_id, []).append(reason)
                exclusion_details.setdefault(player_id, []).append(
                    {
                        "rule_id": "showdown_low_opportunity_skill_gate_v2",
                        "reason_code": reason,
                        "description": (
                            "RB/WR/TE has no identified current opportunity path and "
                            "falls below the applicable low-salary mean and P90 thresholds."
                        ),
                        "category": ExclusionCategory.STRATEGY.value,
                    }
                )
            params.setdefault("strategy_runtime", {})["opportunity_gate"] = {
                "rule_id": "showdown_low_opportunity_skill_gate_v2",
                "excluded_player_ids": sorted(opportunity_excluded),
                "positions": ["RB", "WR", "TE"],
                "thresholds": {
                    "legacy_punt": {"salary_max": 1000, "mean_max": 3, "p90_max": 10},
                    "low_salary_fallback": {"salary_max": 2000, "mean_max": 2, "p90_max": 8},
                },
            }

        def record_pool_exclusions(
            before: pd.DataFrame,
            after: pd.DataFrame,
            reason: str,
            category: ExclusionCategory | None = None,
        ) -> None:
            if before.empty or "player_id" not in before:
                return
            after_ids = (
                set(after["player_id"].astype(str))
                if not after.empty and "player_id" in after
                else set()
            )
            for player_id in set(before["player_id"].astype(str)) - after_ids:
                reasons = exclusion_reasons.setdefault(player_id, [])
                if reason not in reasons:
                    reasons.append(reason)
                detail = {
                    "rule_id": None,
                    "reason_code": reason,
                    "description": reason.replace("_", " "),
                    "category": (
                        category or categorize_exclusion_reason(reason)
                    ).value,
                }
                details = exclusion_details.setdefault(player_id, [])
                if not any(
                    row.get("reason_code") == reason for row in details
                ):
                    details.append(detail)

        before_kicker_filter = pool.copy()
        pool = pool.loc[pool["kicker_role_eligible"].eq(True)].copy()
        record_pool_exclusions(before_kicker_filter, pool, "kicker_role_not_eligible")
        for row in before_kicker_filter.to_dict("records"):
            if not row.get("kicker_role_eligible", True):
                pid = str(row["player_id"])
                exclusion_reasons.setdefault(pid, []).append(row["kicker_role_reason"])
                exclusion_details.setdefault(pid, []).append({
                    "rule_id": "kicker_role_gate_v1", "reason_code": row["kicker_role_reason"],
                    "description": "No expected kicking duties supported by canonical pregame role evidence.",
                    "category": ExclusionCategory.STRATEGY.value,
                })
        before_role_filter = pool.copy()
        pool = pool.loc[pool["role_optimizer_eligible"].eq(True)].copy()
        record_pool_exclusions(before_role_filter, pool, "football_role_unavailable")
        before_availability_filter = pool.copy()
        pool, _ = restrict_pool_to_pregame_available(pool)
        record_pool_exclusions(
            before_availability_filter,
            pool,
            "pregame_unavailable",
        )

        pool_failure_message: str | None = None
        if contest_format == "showdown" and not pool.empty:
            try:
                if strategy in SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_IDS:
                    settings = get_settings()
                    pool, captain_runtime = build_showdown_captain_prior(
                        pool,
                        model_path=settings.showdown_captain_model_path,
                        strength=settings.showdown_captain_prior_strength,
                    )
                    params.setdefault("strategy_runtime", {})[
                        "captain_position_model"
                    ] = captain_runtime
                before_starter_filter = pool.copy()
                pool, starter_runtime = restrict_showdown_pool_to_starting_qbs(pool)
                record_pool_exclusions(
                    before_starter_filter,
                    pool,
                    "not_selected_starting_qb",
                )
                params.setdefault("strategy_runtime", {})[
                    "starter_qb_filter"
                ] = starter_runtime
                historical_qb_pool = pool.loc[
                    pool["position"].astype(str).str.upper().eq("QB")
                ].to_dict(orient="records")
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                lineage = f"projection run {projection_run_id or 'unresolved'}"
                if data_cutoff_at is not None:
                    lineage += f" (cutoff {data_cutoff_at.isoformat()})"
                pool_failure_message = (
                    f"Showdown optimizer blocked: {exc} Selected {lineage}; "
                    "review the projection selection and source snapshots."
                )
                record_pool_exclusions(pool, pd.DataFrame(), "starter_validation_failed")
                pool = pd.DataFrame()
        simulation_result = None
        if contest_format == "classic" and objective == "gpp" and not pool.empty:
            try:
                simulation_result = SimulationService(engine=self.engine).fetch_latest(
                    season=season,
                    week=week,
                    slate=slate,
                    contest_format="classic",
                    projection_run_id=projection_run_id,
                )
            except Exception as exc:  # noqa: BLE001 - simulation is optional optimizer evidence
                logger.info("DT-502 simulation lookup unavailable: %s", exc)
            if simulation_result is not None:
                pool = _merge_simulation_evidence(pool, simulation_result.rows)
                params["simulation_run_id"] = simulation_result.simulation_run_id
                params["simulation_model_id"] = simulation_result.simulation_model_id
                params["simulation_seed"] = simulation_result.seed
        # Classic removes deep punt rows; Showdown permits every positive salary.
        if not pool.empty:
            before_salary_filter = pool.copy()
            pool = pool.copy()
            pool["salary"] = pd.to_numeric(pool.get("salary", 0), errors="coerce")
            minimum_salary = MIN_SALARY if contest_format == "classic" else 1
            pool = pool[pool["salary"] >= minimum_salary]
            pool = pool.reset_index(drop=True)
            record_pool_exclusions(
                before_salary_filter,
                pool,
                "below_minimum_salary",
            )
        eligible_pool_ids = (
            set(pool["player_id"].astype(str))
            if not pool.empty and "player_id" in pool
            else set()
        )
        if excluded_opponent_teams and not pool.empty:
            before_opponent_exclusions = pool.copy()
            pool = apply_user_opponent_preferences(pool, excluded_opponent_teams)
            record_pool_exclusions(
                before_opponent_exclusions, pool, "excluded_opponent_team", ExclusionCategory.USER,
            )
            retained_ids = set(pool["player_id"].astype(str))
            for excluded_row in before_opponent_exclusions.loc[
                ~before_opponent_exclusions["player_id"].astype(str).isin(retained_ids)
            ].to_dict(orient="records"):
                player_id = _safe_text(excluded_row.get("player_id"))
                opponent = _safe_text(excluded_row.get("opponent_team")).upper()
                for detail in exclusion_details.get(player_id, []):
                    if detail.get("reason_code") == "excluded_opponent_team":
                        detail["rule_id"] = USER_OPPONENT_PREFERENCE_RULE_ID
                        detail["description"] = f"User preference — opponent {opponent}"
        # Optional hard exclusions by player name/id passed in params
        exclude_names = {
            str(name).lower().strip(): str(name).lower().strip()
            for name in params.get("exclude_players", [])
            if str(name).strip()
        }
        conflicting_flex_names = {
            _normalize_alias(name) for name in flex_only_names
        } & {_normalize_alias(name) for name in exclude_names}
        if conflicting_flex_names:
            raise ValueError(
                "Players cannot be both FLEX-only and excluded: "
                + ", ".join(sorted(conflicting_flex_names))
            )
        exclusions_present = bool(exclude_names or exclude_ids)
        if not pool.empty and exclusions_present:
            before_user_exclusions = pool.copy()
            pool = pool.copy()
            if "name_norm" not in pool.columns:
                if "name" in pool.columns:
                    pool["name_norm"] = pool["name"].astype(str).str.lower().str.strip().map(_normalize_alias)
                elif "player_name" in pool.columns:
                    pool["name_norm"] = pool["player_name"].astype(str).str.lower().str.strip().map(_normalize_alias)
            pool["player_id"] = pool["player_id"].astype(str)
            name_block = {_normalize_alias(n) for n in exclude_names}
            if name_block:
                pool = pool[~pool["name_norm"].isin(name_block)]
            if exclude_ids:
                pool = pool[~pool["player_id"].isin(exclude_ids)]
            record_pool_exclusions(
                before_user_exclusions,
                pool,
                "user_excluded",
                ExclusionCategory.USER,
            )

        if params.get("minimum_player_salary") is not None and not pool.empty:
            before_user_salary = pool.copy()
            base_salary = pd.to_numeric(pool["base_salary"], errors="coerce") if "base_salary" in pool else pd.to_numeric(pool["salary"], errors="coerce")
            if "base_salary" in pool:
                base_salary = base_salary.fillna(pd.to_numeric(pool["salary"], errors="coerce"))
            salary_eligible = base_salary >= params["minimum_player_salary"]
            if contest_format == "classic":
                salary_eligible = (pd.to_numeric(pool["salary"], errors="coerce") >= params["minimum_player_salary"]) | pool["position"].astype(str).str.upper().isin({"DST", "D", "DEF"})
            pool = pool.loc[salary_eligible].copy().reset_index(drop=True)
            record_pool_exclusions(before_user_salary, pool, "user_minimum_player_salary", ExclusionCategory.USER)
            if requested_captain_id and requested_captain_id not in set(pool["player_id"].astype(str)):
                raise ValueError("Locked Captain conflicts with minimum player salary or other eligibility constraints")

        if contest_format == "classic":
            for position, key in (("QB", "minimum_qb_salary"), ("RB", "minimum_rb_salary")):
                minimum = params.get(key)
                if minimum is None or pool.empty:
                    continue
                before_position_salary = pool.copy()
                eligible = (pool["position"].astype(str).str.upper() != position) | (pd.to_numeric(pool["salary"], errors="coerce") >= minimum)
                pool = pool.loc[eligible].copy().reset_index(drop=True)
                record_pool_exclusions(before_position_salary, pool, f"user_{key}", ExclusionCategory.USER)

        favored_team_positions = favored_positions(params) if contest_format == "classic" else set()
        for position in sorted(favored_team_positions):
            if pool.empty:
                break
            before_favored = pool.copy()
            eligible = (pool["position"].astype(str).str.upper() != position) | pool.apply(is_favored, axis=1)
            pool = pool.loc[eligible].copy().reset_index(drop=True)
            record_pool_exclusions(before_favored, pool, f"user_favored_team_{position.lower()}", ExclusionCategory.USER)

        for position, eligible_ids in season_ppg_eligible_ids.items():
            if pool.empty:
                break
            before_season_rank = pool.copy()
            eligible = (pool["position"].astype(str).str.upper() != position) | pool["player_id"].astype(str).isin(eligible_ids)
            pool = pool.loc[eligible].copy().reset_index(drop=True)
            record_pool_exclusions(before_season_rank, pool, f"user_season_ppg_rank_{position.lower()}", ExclusionCategory.USER)

        if team_leader_preference["enabled"] and not set(team_leader_preference["required_player_ids"]).intersection(set(pool["player_id"].astype(str)) if "player_id" in pool else set()):
            raise ValueError("Required season-average team leader is unavailable under the current exclusions or salary minimum; change those preferences")

        candidate_ids_before_strategy = (
            set(pool["player_id"].astype(str))
            if not pool.empty and "player_id" in pool
            else set()
        )
        unavailable_locks = locked_ids - candidate_ids_before_strategy
        if unavailable_locks:
            details = []
            for player_id in sorted(unavailable_locks):
                reasons = exclusion_reasons.get(player_id) or [
                    "not_found_in_selected_slate"
                ]
                details.append(f"{player_id} ({', '.join(reasons)})")
            raise ValueError(
                "Locked players must pass identity and eligibility checks: "
                + "; ".join(details)
            )

        if not pool.empty and contest_type != "captain" and not merged_analyst and not highest_projection:
            pre_strategy_pool = pool.copy()
            pool, strategy_exclusions = self._select_strategy_candidates(
                pool,
                strategy=strategy,
                contest_type=contest_type,
            )
            for player_id, player_reasons in strategy_exclusions.items():
                if player_id in locked_ids:
                    continue
                for reason in player_reasons:
                    reasons = exclusion_reasons.setdefault(player_id, [])
                    if reason not in reasons:
                        reasons.append(reason)
                    details = exclusion_details.setdefault(player_id, [])
                    if not any(
                        row.get("reason_code") == reason for row in details
                    ):
                        details.append(
                            {
                                "rule_id": None,
                                "reason_code": reason,
                                "description": reason,
                                "category": categorize_exclusion_reason(
                                    reason
                                ).value,
                            }
                        )
            selected_ids = set(pool["player_id"].astype(str))
            restore_ids = locked_ids - selected_ids
            if restore_ids:
                locked_rows = pre_strategy_pool.loc[
                    pre_strategy_pool["player_id"].astype(str).isin(restore_ids)
                ]
                pool = pd.concat([pool, locked_rows], ignore_index=True)
        if not pool.empty and contest_format == "showdown" and objective == "cash" and not single_lineup:
            pool = build_showdown_cash_objective(pool)
        if not pool.empty and strategy == CLASSIC_HEAD_TO_HEAD_STRATEGY_ID:
            pool = build_head_to_head_objective(pool)
            pool["h2h_score_before_context"] = pool["h2h_score"]
            pool["h2h_score"] += pd.to_numeric(
                pool.get("optimizer_context_adjustment", 0.0), errors="coerce"
            ).fillna(0.0)
            pool["h2h_objective_explanation"] = pool.apply(
                lambda row: {
                    **dict(row["h2h_objective_explanation"]),
                    "context_adjustment": float(
                        row["optimizer_context_adjustment"]
                    ),
                    "h2h_score_before_context": float(
                        row["h2h_score_before_context"]
                    ),
                    "h2h_score": float(row["h2h_score"]),
                },
                axis=1,
            )
        elif not pool.empty and contest_format == "classic" and objective == "cash" and not single_lineup:
            pool = build_classic_cash_objective(pool)
            pool["cash_score_before_context"] = pool["cash_score"]
            pool["cash_score"] += pd.to_numeric(
                pool.get("optimizer_context_adjustment", 0.0), errors="coerce"
            ).fillna(0.0)
            pool["cash_objective_explanation"] = pool.apply(
                lambda row: {
                    **dict(row["cash_objective_explanation"]),
                    "context_adjustment": float(
                        row["optimizer_context_adjustment"]
                    ),
                    "cash_score_before_context": float(
                        row["cash_score_before_context"]
                    ),
                    "cash_score": float(row["cash_score"]),
                },
                axis=1,
            )
        if contest_format == "showdown":
            pool, shortlist_report = build_captain_shortlist(
                pool, params=params, flex_only_ids=flex_only_ids
            )
            params.setdefault("strategy_runtime", {})["showdown_captain_shortlist"] = shortlist_report
            if requested_captain_id and requested_captain_id not in {
                row["player_id"] for row in shortlist_report["shortlist"]
            }:
                raise ValueError("Locked Captain is outside the top-four eligible pregame P90 shortlist")
            params["objective_config"].update({
                "scoring_version": CAPTAIN_SHORTLIST_POLICY_ID,
                "score_column": "role_specific",
                "captain_score_column": "p90", "flex_score_column": "projection",
                "captain_multiplier": 1.5, "captain_salary_multiplier": 1.5,
                "captain_shortlist_size": 4,
                "objective_weights": {"captain_p90": 1.5, "flex_mean": 1.0},
                "captain_prior_applied": False,
            })
            if params.get("workload_comparison"):
                params["objective_config"] = {
                    "scoring_version": "offensive_workload_optimizer_v1",
                    "objective_id": params["workload_comparison"], "score_column": "workload_utility",
                    "captain_score_column": "weighted_projected_yards" if params["workload_comparison"] == "learned_yards" else "normalized_count_utility" if params["workload_comparison"] != "offensive_mean_control" else "supported_domain_FP_mean",
                    "flex_score_column": "weighted_projected_yards" if params["workload_comparison"] == "learned_yards" else "normalized_count_utility" if params["workload_comparison"] != "offensive_mean_control" else "supported_domain_FP_mean",
                    "captain_multiplier": 1.5, "captain_salary_multiplier": 1.5,
                    "physical_count_multiplier": 1.0, "captain_shortlist_size": len(shortlist_report["shortlist"]),
                    "captain_eligibility_policy": shortlist_report["policy_id"],
                    "p90_use": "display only; no qualification/objective/tie-break" if params["workload_comparison"] in {"learned_counts","learned_yards","scenario_first"} else "qualification/display only, never workload objective or tie-break",
                    "Analyst_scenarios": "inactive_for_explicit_workload_comparison"}
        if params.get('workload_comparison')=='scenario_first':
            params['objective_config'].update(objective_id='whole_lineup_case_coverage',
                scoring_version='captain_shared_scoring_cases_v6',captain_score_column='shared_case_DK_score',
                flex_score_column='shared_case_DK_score',incumbent_projection_consumed=False,
                scenario_likelihood='unknown',construction_policy='explicit_3-3',
                selection_policy='market_primary_complete_roster_case_coverage_then_mean_capture',
                alternative_scripts_consumed=False,
                capture_target=params.get('scenario_capture_target',.9))
        if params.get("no_qb_captain", False):
            flex_only_ids.update(qb_player_ids)
        flex_only_ids.update(captain_excluded_ids)
        if contest_format == "showdown":
            params.setdefault("strategy_runtime", {})["showdown_qb_preferences"] = (
                showdown_qb_preference_report(params, qb_player_ids=qb_player_ids)
            )
            params["strategy_runtime"]["showdown_team_constraints"] = team_constraint_report(params)
            params["strategy_runtime"]["showdown_captain_preferences"] = captain_preference_report(params)
        params.setdefault("strategy_runtime", {})["player_controls"] = {
            "locked_player_ids": sorted(locked_ids),
            "excluded_player_ids": sorted(exclude_ids),
            "excluded_player_names": sorted(exclude_names),
            "excluded_opponent_teams": sorted(excluded_opponent_teams),
            "exclude_questionable": params.get("exclude_questionable", False),
            "flex_only_player_ids": sorted(flex_only_ids),
            "flex_only_player_names": sorted(flex_only_names),
        }

        if pool.empty:
            lineup_results: List[List[dict]] = []
            status = "failed"
            message = pool_failure_message or "Optimizer failed: no salaries found for this slate."
        else:
            pool = pool.reset_index(drop=True)
            id_to_index = {str(pool.loc[i, "player_id"]): i for i in pool.index}
            num_lineups = max(1, int(params.get("num_lineups", 1)))
            params["num_lineups"] = num_lineups
            max_exposure_raw = params.get("max_exposure", 1.0)
            try:
                max_exposure = float(max_exposure_raw)
            except Exception:  # noqa: BLE001
                max_exposure = 1.0
            if max_exposure > 1.0:
                max_exposure = max_exposure / 100.0
            max_exposure = max(0.01, min(1.0, max_exposure))
            score_col = {
                "cash": "cash_score",
                "tournament": "optimizer_context_ceiling_score",
                "captain": "optimizer_context_ceiling_score",
            }.get(contest_type, "optimizer_context_ceiling_score")
            if strategy == CLASSIC_HEAD_TO_HEAD_STRATEGY_ID:
                score_col = "h2h_score"
            if contest_format == "showdown" and objective == "cash":
                score_col = "showdown_cash_score"
            if contest_format == "classic" and objective == "gpp":
                pool["gpp_score"] = pd.to_numeric(
                    pool["optimizer_context_ceiling_score"], errors="coerce"
                ).fillna(0.0)
                if simulation_result is not None:
                    leverage_weight = float(params.get("leverage_weight", 0.25))
                    pool["gpp_score"] += leverage_weight * pd.to_numeric(
                        pool["leverage_score"], errors="coerce"
                    ).fillna(0.0)
                    params["leverage_weight"] = leverage_weight
                score_col = "gpp_score"
            enforce_single_te = False if contest_format == "showdown" else bool(params.get("enforce_single_te", False))
            avoid_dst_opponents = bool(params.get("avoid_dst_opponents", False))
            stack_cfg = dict(stack_policy)
            if contest_format == "showdown":
                stack_cfg.update({
                    "required_team_leader_ids": team_leader_preference["required_player_ids"],
                    "captain_positions": captain_positions,
                    "captain_position_exception_ids": sorted(named_preference_ids(params, "captain_position_exception_ids")),
                    "no_qb_captain": params.get("no_qb_captain", False),
                    "no_two_qbs": params.get("no_two_qbs", False),
                    "no_qbs": params.get("no_qbs", False),
                    "max_players_per_team": params["max_players_per_team"],
                })
            stack_cfg["require_qb_captain_receiver"] = (
                require_qb_captain_receiver
            )
            workload_comparison = params.get("workload_comparison")
            portfolio_v3 = strategy == SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID and not long_shot_mode and not workload_comparison
            single_entry = strategy in SHOWDOWN_SINGLE_ENTRY_STRATEGY_IDS and not long_shot_mode
            three_max = strategy == SHOWDOWN_THREE_MAX_GPP_STRATEGY_ID and not long_shot_mode
            small_max = strategy == SHOWDOWN_SMALL_MAX_GPP_STRATEGY_ID and not long_shot_mode
            if contest_format == "showdown" and (params.get("require_scenario_diversity") or params.get("soft_scenario_diversity")) and (
                not portfolio_v3 or num_lineups > 5 or requested_captain_id
            ):
                raise ValueError(
                    "Scenario diversity selection is available for showdown_gpp_portfolio_v3 with up to five lineups and no locked Captain"
                )
            portfolio_contest = None
            if portfolio_v3 and params.get("contest_urls"):
                from .showdown_contests import fetch_contests, validate_entry_limit_contest
                urls = params["contest_urls"]
                if not isinstance(urls, list) or len(urls) != 1:
                    raise ValueError("Five-entry Showdown GPP requires exactly one contest URL")
                if num_lineups != 5:
                    raise ValueError("A 5-max contest URL requires exactly five requested lineups")
                fetched = fetch_contests(urls, manual=params.get("manual_contest_metadata"))
                from .saved_contests import record_saved_observations
                record_saved_observations(self.engine, fetched, reason="optimizer")
                portfolio_contest = validate_entry_limit_contest(fetched[0], maximum_entries=5)
            if portfolio_v3 or single_entry or three_max or small_max or long_shot_mode:
                ownership_selector_policy = self._showdown_ownership_selector_policy(pool)
                params.setdefault("strategy_runtime", {})["showdown_ownership_selector_policy"] = ownership_selector_policy
                showdown_ownership_complete = bool(
                    {"captain_ownership", "flex_ownership"} <= set(pool.columns)
                    and pd.to_numeric(pool["captain_ownership"], errors="coerce").notna().all()
                    and pd.to_numeric(pool["flex_ownership"], errors="coerce").notna().all()
                    and ownership_selector_policy["eligible"]
                )
                if not showdown_ownership_complete:
                    for field in ("ownership", "captain_ownership", "flex_ownership"):
                        if field in pool:
                            if "diagnostic_" + field not in pool:
                                pool["diagnostic_" + field] = pool[field]
                            pool[field] = None
                stack_cfg.update(
                    {
                        "require_starting_qb": not params.get("no_qbs", False) and (single_entry or three_max or num_lineups <= 5),
                        "hard_qb_correlations": not params.get("no_qbs", False),
                        "opportunity_gate": True,
                        "saturate_correlations": True,
                        # A partial pool must not give missing players a zero-
                        # ownership advantage in the linear objective.
                        "use_role_ownership": showdown_ownership_complete,
                        "ownership_weight": float(
                            params.get("long_shot_ownership_weight", 0.35)
                            if long_shot_mode else params.get("ownership_weight", 0.08)
                        ),
                    }
                )

            def _run_baseline() -> tuple[list[list[dict]], str, str]:
                exposure_limit = max(1, int(math.ceil(num_lineups * max_exposure)))
                used_counts: dict[str, int] = {}
                captain_counts: dict[str, int] = {}
                exclude_lineups: List[set] = []
                exclude_signatures: List[list[tuple[str, str | None]]] = []
                lineup_results_local: List[List[dict]] = []

                captain_rate = normalize_exposure_rate(
                    params.get("captain_max_exposure"), default=0.60
                )
                core_rate = normalize_exposure_rate(
                    params.get("core_player_max_exposure"), default=0.80
                )
                qb_rate = normalize_exposure_rate(
                    params.get("starting_qb_max_exposure"), default=1.00
                )
                punt_rate = normalize_exposure_rate(
                    params.get("cheap_punt_max_exposure"), default=0.40
                )
                params.update({
                    "captain_max_exposure": captain_rate,
                    "core_player_max_exposure": core_rate,
                    "starting_qb_max_exposure": qb_rate,
                    "cheap_punt_max_exposure": punt_rate,
                })
                captain_limit = max(1, int(math.ceil(num_lineups * captain_rate)))
                player_limits: dict[str, int] = {}
                for _, row in pool.iterrows():
                    pid = str(row["player_id"])
                    rate = core_rate
                    if str(row.get("position") or "").upper() == "QB" and bool(
                        row.get("showdown_qb_eligible")
                    ):
                        rate = qb_rate
                    elif _safe_float(row.get("salary")) <= 1000:
                        rate = punt_rate
                    player_limits[pid] = max(1, int(math.ceil(num_lineups * rate)))

                team_implied: dict[str, float] = {}
                if portfolio_v3 or long_shot_mode:
                    for team, team_rows in pool.groupby("player_team"):
                        raw_values = (
                            team_rows["team_implied_total"]
                            if "team_implied_total" in team_rows.columns
                            else pd.Series(np.nan, index=team_rows.index)
                        )
                        values = pd.to_numeric(raw_values, errors="coerce").dropna()
                        team_implied[str(team).upper()] = float(values.max()) if not values.empty else 0.0
                ordered_teams = sorted(team_implied, key=lambda team: (-team_implied[team], team))
                scripts: list[dict] = []
                control_discovery_scripts: list[dict] = []
                if portfolio_v3 and ordered_teams:
                    favorite = ordered_teams[0]
                    for minimum, required in (
                        (4, []), (5, []), (4, ["RB"]),
                        (4, ["DST"]), (4, ["RB", "DST"]),
                    ):
                        suffix = "_".join(required).lower() or "open"
                        control_discovery_scripts.append({
                            "script_id": f"{favorite}_{minimum}_{6-minimum}_control_{suffix}",
                            "kind": "team_control", "team": favorite,
                            "minimum_team_players": minimum,
                            "required_positions": required,
                            "label": f"{favorite} {minimum}-{6-minimum} control {suffix}",
                        })
                if portfolio_v3 and num_lineups == 5 and len(ordered_teams) >= 2:
                    scripts = [
                        {"script_id": "shootout_1", "kind": "shootout", "label": "Two-sided pass stack"},
                        {"script_id": "shootout_2", "kind": "shootout", "label": "Two-sided pass stack"},
                        {"script_id": f"{ordered_teams[0]}_run_control", "kind": "run_control", "team": ordered_teams[0], "label": f"{ordered_teams[0]} run-control"},
                        {"script_id": f"{ordered_teams[1]}_pass_led", "kind": "pass_led", "team": ordered_teams[1], "label": f"{ordered_teams[1]} pass-led"},
                        {"script_id": f"{ordered_teams[1]}_contrarian", "kind": "contrarian", "team": ordered_teams[1], "label": f"Contrarian {ordered_teams[1]} script"},
                    ]
                elif long_shot_mode and len(ordered_teams) >= 2:
                    scripts = [{
                        "script_id": f"{ordered_teams[1]}_long_shot",
                        "kind": "contrarian",
                        "team": ordered_teams[1],
                        "label": f"Long-shot {ordered_teams[1]} script",
                    }]
                if params.get("no_two_qbs", False) or params.get("no_qbs", False):
                    skipped_scripts = []
                    for script in scripts:
                        if script.get("kind") == "shootout":
                            skipped_scripts.append({**script, "reason_code": "user_no_qbs" if params.get("no_qbs", False) else "user_no_two_qbs"})
                            script.update({"script_id": "best_available", "kind": "",
                                           "label": "Best available under user QB preferences"})
                    params["strategy_runtime"]["showdown_qb_preferences"]["excluded_scripts"] = skipped_scripts
                quality_floor: dict[str, float] | None = None
                captain_diversification: dict = {
                    "enabled": portfolio_v3 and num_lineups >= 10,
                    "minimum_distinct_target": 0,
                    "both_teams_target": False,
                    "qualifying_captain_candidates": [],
                    "quality_rejected_captain_candidates": [],
                    "other_rejected_captain_candidates": [],
                    "planned_captain_player_ids": [],
                    "final_captain_exposures": [],
                    "targets_achieved": True,
                    "limitations": [],
                }
                forced_captain_ids: list[str] = []
                if portfolio_v3:
                    reference_lineup = self._solve_lineup(
                        pool,
                        score_col=score_col,
                        enforce_single_te=enforce_single_te,
                        avoid_dst_opponents=avoid_dst_opponents,
                        contest_type=contest_type,
                        stack_params=stack_cfg,
                        locked_player_ids=locked_ids,
                        flex_only_player_ids=flex_only_ids,
                        rule_profile=rule_profile,
                    )
                    if reference_lineup:
                        quality_floor = {
                            "mean": 0.85 * sum(_safe_float(row.get("projection")) for row in reference_lineup),
                            "p90": 0.90 * sum(_safe_float(row.get("p90")) for row in reference_lineup),
                        }
                    params.setdefault("strategy_runtime", {})["showdown_portfolio_policy"] = {
                        "policy_id": "showdown_five_entry_portfolio_v3",
                        "exposure_rates": {
                            "captain": captain_rate,
                            "core": core_rate,
                            "starting_qb": qb_rate,
                            "cheap_punt": punt_rate,
                        },
                        "quality_floor": dict(quality_floor or {}),
                        "game_scripts": [dict(script) for script in scripts],
                        "control_discovery_scripts": [dict(script) for script in control_discovery_scripts],
                        "ownership_status": (
                            "cpt_flex_available" if stack_cfg["use_role_ownership"] else "unavailable"
                        ),
                        "correlation_policy": "qb_stack_diminishing_60_30_10_bringback_once_v1",
                    }
                    if num_lineups <= 5 and not requested_captain_id:
                        base_kwargs = {
                            "enforce_single_te": enforce_single_te,
                            "avoid_dst_opponents": avoid_dst_opponents,
                            "contest_type": contest_type,
                            "stack_params": stack_cfg,
                            "locked_player_ids": locked_ids,
                            "flex_only_player_ids": flex_only_ids,
                            "rule_profile": rule_profile,
                            "include_control_comparison": False,
                        }
                        candidates: list[list[dict]] = []
                        sources: dict[tuple[str, tuple[str, tuple[str, ...]]], set[str]] = {}
                        scenario_definitions = define_game_scenarios(
                            pool, params["showdown_decisive_margin"]
                        )
                        scenario_audits = [item.audit() for item in scenario_definitions]

                        def add_candidate(lineup: list[dict] | None, source: str, scenario: dict | None = None) -> None:
                            if not lineup:
                                return
                            scenario_audit = scenario or scenario_audits[0]
                            if scenario_audit["scenario_id"] != "baseline":
                                from .showdown_candidate_comparison import baseline_rescore_discovery

                                lineup = baseline_rescore_discovery(lineup, lambda ids, captain: self._solve_lineup(
                                    pool, score_col=score_col, locked_player_ids=ids,
                                    locked_captain_player_id=captain,
                                    **{key: value for key, value in base_kwargs.items() if key != "locked_player_ids"},
                                ))
                            for player in lineup:
                                player["showdown_scenario_id"] = scenario_audit["scenario_id"]
                                player["showdown_scenario"] = dict(scenario_audit)
                                player["showdown_candidate_source"] = source
                                player.setdefault("baseline_projection", player.get("projection"))
                                player.setdefault("baseline_p90", player.get("p90"))
                                player.setdefault("showdown_scenario_adjustment", {
                                    "reason": "market baseline", "baseline_mean": player.get("projection"),
                                    "scenario_mean": player.get("projection"),
                                    "baseline_p90": player.get("p90"), "scenario_p90": player.get("p90"),
                                    "delta_mean": 0.0, "delta_p90": 0.0,
                                })
                            correlation = score_lineup_correlations(lineup, profile=rule_profile)
                            lineup[0]["lineup_correlation_summary"] = (
                                _saturated_showdown_correlation_summary(lineup, correlation)
                            )
                            candidates.append(lineup)
                            sources.setdefault((scenario_audit["scenario_id"], showdown_signature(lineup)), set()).add(source)

                        normal_signatures: list[list[tuple[str, str]]] = []
                        for _ in range(max(20, num_lineups * 6)):
                            lineup = self._solve_lineup(
                                pool, score_col=score_col,
                                exclude_signatures=normal_signatures,
                                **base_kwargs,
                            )
                            if not lineup:
                                break
                            normal_signatures.append([
                                (str(row["player_id"]), str(row["roster_position"]))
                                for row in lineup
                            ])
                            add_candidate(lineup, "normal")
                        sequential_used: dict[str, int] = {}
                        sequential_captains: dict[str, int] = {}
                        sequential_signatures: list[list[tuple[str, str]]] = []
                        for lineup_index in range(num_lineups):
                            lineup = self._solve_lineup(
                                pool, score_col=score_col,
                                exposure_remaining={
                                    pid: limit - sequential_used.get(pid, 0)
                                    for pid, limit in player_limits.items()
                                },
                                captain_exposure_remaining={
                                    pid: captain_limit - sequential_captains.get(pid, 0)
                                    for pid in player_limits
                                },
                                exclude_signatures=sequential_signatures,
                                quality_floor=quality_floor,
                                portfolio_script=(scripts[lineup_index]
                                                  if lineup_index < len(scripts) else None),
                                **base_kwargs,
                            )
                            if not lineup:
                                break
                            add_candidate(lineup, "prior_sequential")
                            sequential_signatures.append([
                                (str(row["player_id"]), str(row["roster_position"]))
                                for row in lineup
                            ])
                            for row in lineup:
                                pid = str(row["player_id"])
                                sequential_used[pid] = sequential_used.get(pid, 0) + 1
                                if row["roster_position"] == "CPT":
                                    sequential_captains[pid] = sequential_captains.get(pid, 0) + 1
                        for script in [*scripts, *control_discovery_scripts]:
                            add_candidate(self._solve_lineup(
                                pool, score_col=score_col, portfolio_script=script,
                                **base_kwargs,
                            ), f"script:{script['script_id']}")
                        raw_pool = pool.copy()
                        raw_pool["captain_objective_multiplier"] = 1.0
                        raw_kwargs = {
                            **base_kwargs,
                            "rule_profile": None,
                            "stack_params": {**stack_cfg, "use_role_ownership": False},
                        }
                        for raw_score, label in (("projection", "highest_mean"), ("p90", "highest_p90")):
                            raw = self._solve_lineup(raw_pool, score_col=raw_score, **raw_kwargs)
                            if raw:
                                # Re-evaluate this exact roster under the production
                                # selector so all candidates have comparable scores.
                                selected_ids = {str(row["player_id"]) for row in raw}
                                captain_id = showdown_signature(raw)[0]
                                rescored = self._solve_lineup(
                                    pool, score_col=score_col,
                                    locked_player_ids=selected_ids,
                                    locked_captain_player_id=captain_id,
                                    **{key: value for key, value in base_kwargs.items()
                                       if key != "locked_player_ids"},
                                )
                                add_candidate(rescored, label)
                        family_lineups: dict[str, list[dict]] = {}
                        for _, player in pool.iterrows():
                            player_id = str(player.get("player_id") or "")
                            if not player_id or player_id in flex_only_ids or player_id in family_lineups:
                                continue
                            lineup = self._solve_lineup(
                                pool, score_col=score_col,
                                locked_captain_player_id=player_id,
                                **base_kwargs,
                            )
                            if lineup:
                                family_lineups[player_id] = lineup
                                add_candidate(lineup, "captain_family")
                                family_exclusions = [[
                                    (str(row["player_id"]), str(row["roster_position"]))
                                    for row in lineup
                                ]]
                                for _ in range(2):
                                    alternative = self._solve_lineup(
                                        pool, score_col=score_col,
                                        locked_captain_player_id=player_id,
                                        exclude_signatures=family_exclusions,
                                        **base_kwargs,
                                    )
                                    if not alternative:
                                        break
                                    add_candidate(alternative, "captain_family_alternative")
                                    family_exclusions.append([
                                        (str(row["player_id"]), str(row["roster_position"]))
                                        for row in alternative
                                    ])
                                for raw_score, label in (("projection", "mean"), ("p90", "p90")):
                                    raw_family = self._solve_lineup(
                                        raw_pool, score_col=raw_score,
                                        locked_captain_player_id=player_id,
                                        **raw_kwargs,
                                    )
                                    if not raw_family:
                                        continue
                                    rescored = self._solve_lineup(
                                        pool, score_col=score_col,
                                        locked_player_ids={str(row["player_id"]) for row in raw_family},
                                        locked_captain_player_id=player_id,
                                        **{key: value for key, value in base_kwargs.items()
                                           if key != "locked_player_ids"},
                                    )
                                    add_candidate(rescored, f"captain_family_raw_{label}")
                        params.setdefault("strategy_runtime", {}).setdefault(
                            "showdown_portfolio_policy", {}
                        )["game_script_scenarios"] = {
                            "definitions": scenario_audits,
                            "status": "complete" if len(scenario_definitions) == 3 else "decisive_scenarios_unavailable_without_consistent_cutoff_safe_market",
                            "require_scenario_diversity": params["require_scenario_diversity"],
                            "soft_scenario_diversity": params["soft_scenario_diversity"],
                        }
                        for scenario in scenario_definitions[1:]:
                            conditioned_pool = condition_player_pool(pool, scenario)
                            raw_conditioned_pool = conditioned_pool.copy()
                            raw_conditioned_pool["captain_objective_multiplier"] = 1.0
                            audit = scenario.audit()
                            scenario_kwargs = {**base_kwargs}
                            add_candidate(self._solve_lineup(
                                conditioned_pool, score_col=score_col, **scenario_kwargs,
                            ), "highest_gpp_objective", audit)
                            for raw_score, label in (("projection", "highest_mean"), ("p90", "highest_p90")):
                                raw = self._solve_lineup(
                                    raw_conditioned_pool, score_col=raw_score,
                                    **{**scenario_kwargs, "rule_profile": None,
                                       "stack_params": {**stack_cfg, "use_role_ownership": False}},
                                )
                                if raw:
                                    rescored = self._solve_lineup(
                                        conditioned_pool, score_col=score_col,
                                        locked_player_ids={str(row["player_id"]) for row in raw},
                                        locked_captain_player_id=showdown_signature(raw)[0],
                                        **{key: value for key, value in scenario_kwargs.items()
                                           if key != "locked_player_ids"},
                                    )
                                    add_candidate(rescored, label, audit)
                            for _, player in conditioned_pool.iterrows():
                                player_id = str(player.get("player_id") or "")
                                if not player_id or player_id in flex_only_ids:
                                    continue
                                add_candidate(self._solve_lineup(
                                    conditioned_pool, score_col=score_col,
                                    locked_captain_player_id=player_id, **scenario_kwargs,
                                ), "captain_family", audit)
                            for count in (5, 4, 3):
                                add_candidate(self._solve_lineup(
                                    conditioned_pool, score_col=score_col,
                                    portfolio_script={"kind": "scenario_construction", "team": scenario.winner,
                                                      "team_players": count}, **scenario_kwargs,
                                ), f"team_split_{count}_{6-count}", audit)
                            for required in (["RB"], ["DST"], ["RB", "DST"]):
                                add_candidate(self._solve_lineup(
                                    conditioned_pool, score_col=score_col,
                                    portfolio_script={"kind": "scenario_construction", "team": scenario.winner,
                                                      "required_positions": required}, **scenario_kwargs,
                                ), "control_" + "_".join(required).lower(), audit)
                        if not candidates:
                            return [], "failed", "No legal Showdown candidate was found"
                        # Probe a small set of commonly shared one-offs before
                        # declaring an exposure-driven underfill. These temporary
                        # discovery exclusions never alter slate eligibility.
                        if params.get("analyst_packet_sha256"):
                            from .analyst_generation import generate_showdown, merge_showdown
                            analyst_candidates, analyst_report = generate_showdown(
                                self, pool, params=params, season=season, week=week, slate=slate,
                                solve_kwargs={"score_col": score_col, **base_kwargs},
                            )
                            baseline_signatures = {showdown_signature(lineup) for lineup in candidates}
                            for lineup in analyst_candidates:
                                add_candidate(lineup, "football_analyst")
                            candidates = merge_showdown(candidates, analyst_candidates, preserve_variants=True)
                            analyst_report["comparison"].update(
                                baseline_distinct=len(baseline_signatures),
                                shadow_new_distinct=len({showdown_signature(lineup) for lineup in analyst_candidates}-baseline_signatures))
                            analyst_report["merged_distinct_candidate_count"] = len({
                                (str(lineup[0].get("showdown_scenario_id") or "baseline"), showdown_signature(lineup))
                                for lineup in candidates})
                            analyst_report["merged_distinct_canonical_roster_count"] = len({showdown_signature(lineup) for lineup in candidates})
                            analyst_report["baseline_scenario_variants_preserved"] = True
                            params.setdefault("strategy_runtime", {})["football_analyst"] = analyst_report
                        unique_candidates = {
                            showdown_signature(lineup): lineup for lineup in candidates
                        }
                        discovery_mean = max(candidate_metrics(lineup)["baseline_mean"]
                                             for lineup in unique_candidates.values())
                        discovery_p90 = max(candidate_metrics(lineup)["baseline_p90"]
                                            for lineup in unique_candidates.values())
                        discovery_floor = {
                            "mean": 0.95 * discovery_mean,
                            "p90": 0.95 * discovery_p90,
                        }
                        frequency: dict[str, int] = {}
                        for lineup in unique_candidates.values():
                            metrics = candidate_metrics(lineup)
                            if (metrics["baseline_mean"] < discovery_floor["mean"]
                                    or metrics["baseline_p90"] < discovery_floor["p90"]):
                                continue
                            for row in lineup:
                                pid = str(row["player_id"])
                                if (str(row.get("position") or "").upper() != "QB"
                                        and pid not in locked_ids):
                                    frequency[pid] = frequency.get(pid, 0) + 1
                        common_ids = sorted(frequency, key=lambda pid: (-frequency[pid], pid))[:6]
                        for size in (1, 2):
                            for removed_ids in itertools.combinations(common_ids, size):
                                reduced_pool = pool.loc[
                                    ~pool["player_id"].astype(str).isin(removed_ids)
                                ].reset_index(drop=True)
                                add_candidate(self._solve_lineup(
                                    reduced_pool, score_col=score_col,
                                    quality_floor=discovery_floor,
                                    **base_kwargs,
                                ), "exposure_coverage")
                        selected, selection_report = select_showdown_portfolio(
                            candidates,
                            requested=num_lineups,
                            player_limits=player_limits,
                            captain_limit=captain_limit,
                            require_scenario_diversity=params["require_scenario_diversity"],
                            soft_scenario_diversity=params["soft_scenario_diversity"],
                        )
                        if params.get("analyst_packet_sha256"):
                            from .analyst_generation import annotate_showdown_selection
                            annotate_showdown_selection(analyst_report, selected, selection_report)
                        selection_report["scenario_definitions"] = scenario_audits
                        selection_report["scenario_generation_status"] = (
                            "complete" if len(scenario_definitions) == 3
                            else "Decisive scenarios unavailable: consistent cutoff-safe market total and implied totals are required"
                        )
                        selection_report["family_rows"] = captain_family_summaries(selection_report)
                        selection_report["source_coverage"] = {
                            source: sum(source in names for names in sources.values())
                            for source in sorted({name for names in sources.values() for name in names})
                        }
                        selection_report["ownership_selection_status"] = (
                            "complete slate role ownership used in selector"
                            if showdown_ownership_complete else
                            "role ownership diagnostic only: incomplete or not explicitly approved for Showdown; selector term disabled uniformly"
                        )
                        runtime = params.setdefault("strategy_runtime", {}).setdefault(
                            "showdown_portfolio_policy", {}
                        )
                        runtime["candidate_selection"] = selection_report
                        runtime["underfill_diagnostics"] = selection_report["underfill_diagnostics"]
                        runtime["quality_floor"] = {
                            "mean": 0.95 * selection_report["best_mean"],
                            "p90": 0.95 * selection_report["best_p90"],
                        }
                        if selected:
                            next(row for row in selected[0] if row["roster_position"] == "CPT")[
                                "captain_family_coverage_report"
                            ] = selection_report
                        status_local = "completed" if selected else "failed"
                        message_local = (
                            f"Selected {len(selected)} of {num_lineups} Showdown lineups from "
                            f"{selection_report['candidate_count']} distinct candidates; "
                            "joint mean/P90 floor=95% of common baseline raw maxima; "
                            f"{selection_report['ownership_selection_status']}"
                        )
                        return selected, status_local, message_local
                    if num_lineups >= 10 and quality_floor:
                        qualifying: list[dict] = []
                        quality_rejected: list[dict] = []
                        other_rejected: list[dict] = []
                        for _, candidate in pool.iterrows():
                            player_id = str(candidate.get("player_id") or "")
                            if not player_id or player_id in flex_only_ids:
                                continue
                            base_kwargs = {
                                "score_col": score_col,
                                "enforce_single_te": enforce_single_te,
                                "avoid_dst_opponents": avoid_dst_opponents,
                                "contest_type": contest_type,
                                "stack_params": stack_cfg,
                                "locked_player_ids": locked_ids,
                                "flex_only_player_ids": flex_only_ids,
                                "rule_profile": rule_profile,
                                "portfolio_script": None,
                                "locked_captain_player_id": player_id,
                                "include_control_comparison": False,
                            }
                            candidate_lineup = self._solve_lineup(
                                pool, quality_floor=quality_floor, **base_kwargs
                            )
                            candidate_summary = {
                                "player_id": player_id,
                                "player_name": str(candidate.get("name") or candidate.get("player_name") or player_id),
                                "team": str(candidate.get("player_team") or candidate.get("team") or "").upper(),
                                "position": str(candidate.get("position") or "").upper(),
                            }
                            if candidate_lineup:
                                candidate_summary.update({
                                    "lineup_mean": sum(_safe_float(row.get("projection")) for row in candidate_lineup),
                                    "lineup_p90": sum(_safe_float(row.get("p90")) for row in candidate_lineup),
                                    "objective_score": sum(_safe_float(row.get("objective_score")) for row in candidate_lineup),
                                    "solver_objective_value": _safe_float(
                                        candidate_lineup[0].get("solver_objective_value")
                                    ),
                                    "best_lineup_players": [
                                        {
                                            "player_id": str(row.get("player_id") or ""),
                                            "player_name": str(row.get("player_name") or row.get("name") or row.get("player_id") or ""),
                                            "roster_position": str(row.get("roster_position") or ""),
                                        }
                                        for row in candidate_lineup
                                    ],
                                })
                                qualifying.append(candidate_summary)
                                continue
                            relaxed_lineup = self._solve_lineup(
                                pool, quality_floor=None, **base_kwargs
                            )
                            if relaxed_lineup:
                                lineup_mean = sum(_safe_float(row.get("projection")) for row in relaxed_lineup)
                                lineup_p90 = sum(_safe_float(row.get("p90")) for row in relaxed_lineup)
                                candidate_summary.update({
                                    "lineup_mean": lineup_mean,
                                    "lineup_p90": lineup_p90,
                                    "failed_mean_floor": lineup_mean < quality_floor["mean"],
                                    "failed_p90_floor": lineup_p90 < quality_floor["p90"],
                                })
                                quality_rejected.append(candidate_summary)
                            else:
                                candidate_summary["reason"] = "no_valid_construction_before_quality_floors"
                                other_rejected.append(candidate_summary)

                        qualifying.sort(
                            key=lambda row: (-_safe_float(row.get("objective_score")), str(row.get("player_id")))
                        )
                        minimum_distinct = min(3, len(qualifying))
                        forced_captain_ids = plan_showdown_captain_diversification(
                            qualifying, minimum_distinct=3
                        )
                        qualifying_teams = sorted({
                            str(row.get("team") or "") for row in qualifying if row.get("team")
                        })
                        both_teams_target = len(qualifying_teams) >= 2
                        captain_diversification.update({
                            "minimum_distinct_target": minimum_distinct,
                            "both_teams_target": both_teams_target,
                            "qualifying_captain_candidates": qualifying,
                            "quality_rejected_captain_candidates": quality_rejected,
                            "other_rejected_captain_candidates": other_rejected,
                            "planned_captain_player_ids": forced_captain_ids,
                        })
                        if len(qualifying) < 3:
                            captain_diversification["limitations"].append(
                                f"Only {len(qualifying)} Captain candidates passed all quality and construction constraints."
                            )
                        params.setdefault("strategy_runtime", {}).setdefault(
                            "showdown_portfolio_policy", {}
                        )["captain_diversification"] = captain_diversification

                underfill_diagnostics: dict = {
                    "attempted_lineup_number": None,
                    "reason_counts": {},
                    "counts_may_overlap": True,
                    "quality_floors_relaxed": False,
                }
                captain_choice_snapshots: list[dict] = []

                def _record_underfill_diagnostics(
                    lineup_number: int,
                    *,
                    exposure_remaining: dict,
                    captain_remaining: dict | None,
                    script: dict | None,
                    locked_captain_id: str | None,
                ) -> None:
                    if not portfolio_v3:
                        return
                    checks: list[tuple[str, dict]] = []
                    if quality_floor:
                        checks.extend([
                            ("failed_mean_floor", {"quality_floor": {"mean": 0.0, "p90": quality_floor["p90"]}}),
                            ("failed_p90_floor", {"quality_floor": {"mean": quality_floor["mean"], "p90": 0.0}}),
                        ])
                    checks.extend([
                        ("exposure_constraint", {"exposure_remaining": None, "captain_exposure_remaining": None}),
                        ("duplicate_lineup", {"exclude_lineups": None, "exclude_signatures": None}),
                        ("portfolio_script_diversification", {"portfolio_script": None}),
                        ("captain_diversification_constraint", {"locked_captain_player_id": None}),
                        (
                            "hard_correlation_constraint",
                            {"stack_params": {**stack_cfg, "require_starting_qb": False, "hard_qb_correlations": False}},
                        ),
                    ])
                    base = {
                        "score_col": score_col,
                        "exposure_remaining": exposure_remaining,
                        "captain_exposure_remaining": captain_remaining,
                        "exclude_lineups": exclude_lineups,
                        "exclude_signatures": exclude_signatures,
                        "enforce_single_te": enforce_single_te,
                        "avoid_dst_opponents": avoid_dst_opponents,
                        "contest_type": contest_type,
                        "stack_params": stack_cfg,
                        "locked_player_ids": locked_ids,
                        "flex_only_player_ids": flex_only_ids,
                        "rule_profile": rule_profile,
                        "quality_floor": quality_floor,
                        "portfolio_script": script,
                        "locked_captain_player_id": locked_captain_id,
                        "include_control_comparison": False,
                    }
                    reasons: list[str] = []
                    for reason, overrides in checks:
                        if self._solve_lineup(pool, **{**base, **overrides}):
                            reasons.append(reason)
                    if not reasons:
                        reasons = ["other_constraint"]
                    underfill_diagnostics["attempted_lineup_number"] = lineup_number
                    underfill_diagnostics["reason_counts"] = {
                        reason: reasons.count(reason) for reason in sorted(set(reasons))
                    }

                for lineup_index in range(num_lineups):
                    remaining = {
                        pid: (player_limits.get(pid, exposure_limit) if portfolio_v3 else exposure_limit)
                        - used_counts.get(pid, 0)
                        for pid in pool["player_id"].astype(str)
                    }
                    captain_remaining = {
                        pid: captain_limit - captain_counts.get(pid, 0)
                        for pid in pool["player_id"].astype(str)
                    } if portfolio_v3 else None
                    if captain_diversification["enabled"]:
                        captain_choice_snapshots.append({
                            "lineup_number": lineup_index + 1,
                            "exposure_remaining": dict(remaining),
                            "captain_exposure_remaining": dict(captain_remaining or {}),
                            "exclude_lineups": [set(values) for values in exclude_lineups],
                            "exclude_signatures": [list(values) for values in exclude_signatures],
                            "portfolio_script": (
                                dict(scripts[lineup_index])
                                if lineup_index < len(scripts) else None
                            ),
                            "forced_captain_player_id": (
                                forced_captain_ids[lineup_index]
                                if lineup_index < len(forced_captain_ids) else None
                            ),
                        })
                    lineup = self._solve_lineup(
                        pool,
                        score_col=score_col,
                        exposure_remaining=remaining,
                        captain_exposure_remaining=captain_remaining,
                        exclude_lineups=exclude_lineups,
                        exclude_signatures=exclude_signatures,
                        enforce_single_te=enforce_single_te,
                        avoid_dst_opponents=avoid_dst_opponents,
                        contest_type=contest_type,
                        stack_params=stack_cfg,
                        locked_player_ids=locked_ids,
                        flex_only_player_ids=flex_only_ids,
                        rule_profile=rule_profile,
                        quality_floor=quality_floor,
                        portfolio_script=(scripts[lineup_index] if lineup_index < len(scripts) else None),
                        locked_captain_player_id=(
                            requested_captain_id
                            or (forced_captain_ids[lineup_index]
                                if lineup_index < len(forced_captain_ids) else None)
                        ),
                    )
                    if not lineup:
                        _record_underfill_diagnostics(
                            lineup_index + 1,
                            exposure_remaining=remaining,
                            captain_remaining=captain_remaining,
                            script=(scripts[lineup_index] if lineup_index < len(scripts) else None),
                            locked_captain_id=(
                                forced_captain_ids[lineup_index]
                                if lineup_index < len(forced_captain_ids) else None
                            ),
                        )
                        break
                    lineup_indices = {id_to_index[str(row.get("player_id"))] for row in lineup if str(row.get("player_id")) in id_to_index}
                    # Update counts and exclusion set
                    for row in lineup:
                        pid = str(row.get("player_id"))
                        used_counts[pid] = used_counts.get(pid, 0) + 1
                        if str(row.get("roster_position") or "").upper() == "CPT":
                            captain_counts[pid] = captain_counts.get(pid, 0) + 1
                    signature = []
                    for row in lineup:
                        pid = str(row.get("player_id"))
                        role = str(row.get("roster_position") or "").upper() if contest_type == "captain" else None
                        signature.append((pid, role))
                    lineup_results_local.append(lineup)
                    if portfolio_v3 or long_shot_mode:
                        script = scripts[lineup_index] if lineup_index < len(scripts) else {"script_id": "best_available", "label": "Best available"}
                        for row in lineup:
                            row["portfolio_script_target"] = dict(script)
                        if quality_floor is None:
                            best_mean = sum(_safe_float(row.get("projection")) for row in lineup)
                            best_p90 = sum(_safe_float(row.get("p90")) for row in lineup)
                            quality_floor = {"mean": 0.85 * best_mean, "p90": 0.90 * best_p90}
                    if lineup_indices:
                        exclude_lineups.append(lineup_indices)
                    if signature:
                        exclude_signatures.append(signature)

                if captain_diversification["enabled"]:
                    captain_rows: dict[str, dict] = {}
                    selected_captain_quality: dict[str, list[dict]] = {}
                    for lineup_number, lineup in enumerate(lineup_results_local, start=1):
                        captain = next(
                            (row for row in lineup if str(row.get("roster_position") or "").upper() == "CPT"),
                            None,
                        )
                        if captain is None:
                            continue
                        player_id = str(captain.get("player_id") or "")
                        current = captain_rows.setdefault(player_id, {
                            "player_id": player_id,
                            "player_name": str(captain.get("player_name") or captain.get("name") or player_id),
                            "team": str(captain.get("player_team") or captain.get("team") or "").upper(),
                            "appearances": 0,
                        })
                        current["appearances"] += 1
                        selected_captain_quality.setdefault(player_id, []).append({
                            "lineup_number": lineup_number,
                            "lineup_mean": sum(
                                _safe_float(row.get("projection")) for row in lineup
                            ),
                            "lineup_p90": sum(
                                _safe_float(row.get("p90")) for row in lineup
                            ),
                            "solver_objective_value": _safe_float(
                                lineup[0].get("solver_objective_value")
                            ),
                        })
                    final_exposures = sorted(
                        captain_rows.values(), key=lambda row: (-int(row["appearances"]), str(row["player_name"]))
                    )
                    for row in final_exposures:
                        row["exposure"] = row["appearances"] / len(lineup_results_local) if lineup_results_local else 0.0
                    final_teams = {str(row.get("team") or "") for row in final_exposures}
                    distinct_achieved = len(final_exposures) >= int(captain_diversification["minimum_distinct_target"])
                    both_teams_achieved = (
                        not captain_diversification["both_teams_target"] or len(final_teams) >= 2
                    )
                    captain_diversification.update({
                        "final_captain_exposures": final_exposures,
                        "distinct_target_achieved": distinct_achieved,
                        "both_teams_target_achieved": both_teams_achieved,
                        "targets_achieved": distinct_achieved and both_teams_achieved,
                    })

                    qualifying_by_id = {
                        str(row.get("player_id") or ""): row
                        for row in captain_diversification["qualifying_captain_candidates"]
                    }
                    selected_quality_report: list[dict] = []
                    for player_id, selections in selected_captain_quality.items():
                        standalone = qualifying_by_id.get(player_id, {})
                        first = selections[0]
                        enriched_selections = []
                        for selection_number, selection in enumerate(selections, start=1):
                            snapshot = captain_choice_snapshots[
                                int(selection["lineup_number"]) - 1
                            ]
                            standalone_exposure_blockers = []
                            for standalone_player in standalone.get(
                                "best_lineup_players", []
                            ):
                                standalone_player_id = str(
                                    standalone_player.get("player_id") or ""
                                )
                                if _safe_float(
                                    snapshot["exposure_remaining"].get(
                                        standalone_player_id
                                    )
                                ) <= 0:
                                    standalone_exposure_blockers.append({
                                        "player_id": standalone_player_id,
                                        "player_name": str(
                                            standalone_player.get("player_name")
                                            or standalone_player_id
                                        ),
                                    })
                            enriched_selections.append({
                                **selection,
                                "selection_number": selection_number,
                                "mean_delta_from_first_selected": (
                                    selection["lineup_mean"] - first["lineup_mean"]
                                ),
                                "p90_delta_from_first_selected": (
                                    selection["lineup_p90"] - first["lineup_p90"]
                                ),
                                "mean_delta_from_standalone_best": (
                                    selection["lineup_mean"]
                                    - _safe_float(standalone.get("lineup_mean"))
                                ),
                                "p90_delta_from_standalone_best": (
                                    selection["lineup_p90"]
                                    - _safe_float(standalone.get("lineup_p90"))
                                ),
                                "standalone_best_exposure_blockers": (
                                    standalone_exposure_blockers
                                ),
                            })
                        selected_quality_report.append({
                            "player_id": player_id,
                            "player_name": str(
                                standalone.get("player_name")
                                or captain_rows[player_id]["player_name"]
                            ),
                            "team": str(
                                standalone.get("team") or captain_rows[player_id]["team"]
                            ),
                            "standalone_best": {
                                "lineup_mean": _safe_float(standalone.get("lineup_mean")),
                                "lineup_p90": _safe_float(standalone.get("lineup_p90")),
                                "solver_objective_value": _safe_float(
                                    standalone.get("solver_objective_value")
                                ),
                            },
                            "selected_lineups": enriched_selections,
                        })

                    unselected_reports: list[dict] = []
                    for player_id, candidate in qualifying_by_id.items():
                        if player_id in captain_rows:
                            continue
                        step_results: list[dict] = []
                        for snapshot in captain_choice_snapshots[:len(lineup_results_local)]:
                            lineup_number = int(snapshot["lineup_number"])
                            forced_id = str(
                                snapshot.get("forced_captain_player_id") or ""
                            )
                            if forced_id and forced_id != player_id:
                                step_results.append({
                                    "lineup_number": lineup_number,
                                    "status": "captain_diversity_reserved_slot",
                                    "reserved_for_player_id": forced_id,
                                    "reserved_for_player_name": str(
                                        qualifying_by_id.get(forced_id, {}).get(
                                            "player_name", forced_id
                                        )
                                    ),
                                })
                                continue

                            base = {
                                "score_col": score_col,
                                "exposure_remaining": snapshot["exposure_remaining"],
                                "captain_exposure_remaining": snapshot["captain_exposure_remaining"],
                                "exclude_lineups": snapshot["exclude_lineups"],
                                "exclude_signatures": snapshot["exclude_signatures"],
                                "enforce_single_te": enforce_single_te,
                                "avoid_dst_opponents": avoid_dst_opponents,
                                "contest_type": contest_type,
                                "stack_params": stack_cfg,
                                "locked_player_ids": locked_ids,
                                "flex_only_player_ids": flex_only_ids,
                                "rule_profile": rule_profile,
                                "quality_floor": quality_floor,
                                "portfolio_script": snapshot["portfolio_script"],
                                "locked_captain_player_id": player_id,
                                "include_control_comparison": False,
                            }
                            candidate_lineup = self._solve_lineup(pool, **base)
                            actual_lineup = lineup_results_local[lineup_number - 1]
                            actual_captain = next(
                                row for row in actual_lineup
                                if str(row.get("roster_position") or "").upper() == "CPT"
                            )
                            if candidate_lineup:
                                candidate_objective = _safe_float(
                                    candidate_lineup[0].get("solver_objective_value")
                                )
                                selected_objective = _safe_float(
                                    actual_lineup[0].get("solver_objective_value")
                                )
                                step_results.append({
                                    "lineup_number": lineup_number,
                                    "status": "available_lower_sequential_objective",
                                    "lineup_mean": sum(
                                        _safe_float(row.get("projection"))
                                        for row in candidate_lineup
                                    ),
                                    "lineup_p90": sum(
                                        _safe_float(row.get("p90"))
                                        for row in candidate_lineup
                                    ),
                                    "solver_objective_value": candidate_objective,
                                    "selected_captain_player_id": str(
                                        actual_captain.get("player_id") or ""
                                    ),
                                    "selected_captain_player_name": str(
                                        actual_captain.get("player_name")
                                        or actual_captain.get("name")
                                        or actual_captain.get("player_id")
                                        or ""
                                    ),
                                    "selected_solver_objective_value": selected_objective,
                                    "solver_objective_deficit": (
                                        candidate_objective - selected_objective
                                    ),
                                })
                                continue

                            reasons: list[str] = []
                            blocking_players: list[dict] = []
                            if _safe_float(
                                snapshot["captain_exposure_remaining"].get(player_id)
                            ) <= 0:
                                reasons.append("captain_exposure")
                            exposure_relaxed = self._solve_lineup(
                                pool,
                                **{
                                    **base,
                                    "exposure_remaining": None,
                                    "captain_exposure_remaining": None,
                                },
                            )
                            if exposure_relaxed:
                                reasons.append("player_exposure")
                                for row in exposure_relaxed:
                                    blocker_id = str(row.get("player_id") or "")
                                    if _safe_float(
                                        snapshot["exposure_remaining"].get(blocker_id)
                                    ) > 0:
                                        continue
                                    blocker_class = "core_player_exposure"
                                    if (
                                        str(row.get("position") or "").upper() == "QB"
                                        and bool(row.get("showdown_qb_eligible"))
                                    ):
                                        blocker_class = "starting_qb_exposure"
                                    elif _safe_float(
                                        row.get("base_salary", row.get("salary"))
                                    ) <= 1000:
                                        blocker_class = "cheap_punt_exposure"
                                    blocking_players.append({
                                        "player_id": blocker_id,
                                        "player_name": str(
                                            row.get("player_name")
                                            or row.get("name")
                                            or blocker_id
                                        ),
                                        "exposure_class": blocker_class,
                                    })
                            duplicate_relaxed = self._solve_lineup(
                                pool,
                                **{
                                    **base,
                                    "exclude_lineups": None,
                                    "exclude_signatures": None,
                                },
                            )
                            if duplicate_relaxed:
                                reasons.append("exact_duplicate_or_overlap")
                            if quality_floor and self._solve_lineup(
                                pool, **{**base, "quality_floor": None}
                            ):
                                reasons.append("quality_floor_after_prior_constraints")
                            if not reasons and self._solve_lineup(
                                pool,
                                **{
                                    **base,
                                    "exposure_remaining": None,
                                    "captain_exposure_remaining": None,
                                    "exclude_lineups": None,
                                    "exclude_signatures": None,
                                },
                            ):
                                reasons.append("exposure_duplicate_interaction")
                            step_results.append({
                                "lineup_number": lineup_number,
                                "status": "blocked",
                                "reasons": reasons or ["other_specific_constraint"],
                                "blocking_players": blocking_players,
                            })

                        available_steps = [
                            row for row in step_results
                            if row.get("status") == "available_lower_sequential_objective"
                        ]
                        blocked_steps = [
                            row for row in step_results if row.get("status") == "blocked"
                        ]
                        if available_steps:
                            primary_reason = "lower_solver_objective_at_available_sequential_step"
                            best_available = max(
                                available_steps,
                                key=lambda row: _safe_float(
                                    row.get("solver_objective_value")
                                ),
                            )
                        else:
                            reason_counts: dict[str, int] = {}
                            for row in blocked_steps:
                                for reason in row.get("reasons", []):
                                    reason_counts[str(reason)] = (
                                        reason_counts.get(str(reason), 0) + 1
                                    )
                            primary_reason = (
                                max(
                                    reason_counts,
                                    key=lambda reason: (reason_counts[reason], reason),
                                )
                                if reason_counts
                                else "captain_diversity_reserved_slots"
                            )
                            best_available = None
                        unselected_reports.append({
                            "player_id": player_id,
                            "player_name": str(candidate.get("player_name") or player_id),
                            "team": str(candidate.get("team") or ""),
                            "position": str(candidate.get("position") or ""),
                            "standalone_best": {
                                "lineup_mean": _safe_float(candidate.get("lineup_mean")),
                                "lineup_p90": _safe_float(candidate.get("lineup_p90")),
                                "solver_objective_value": _safe_float(
                                    candidate.get("solver_objective_value")
                                ),
                            },
                            "primary_reason": primary_reason,
                            "best_available_sequential_step": best_available,
                            "step_results": step_results,
                        })

                    captain_diversification["selection_diagnostics"] = {
                        "construction_mode": "sequential_greedy",
                        "is_joint_portfolio_optimization": False,
                        "explanation": (
                            "The optimizer solves one lineup at a time. Earlier lineups "
                            "consume player and Captain exposure and become duplicate exclusions, "
                            "so lineup order changes the feasible choices available later."
                        ),
                        "selected_captain_quality": sorted(
                            selected_quality_report,
                            key=lambda row: str(row.get("player_name") or ""),
                        ),
                        "unselected_qualifying_captains": unselected_reports,
                    }
                    if not distinct_achieved:
                        captain_diversification["limitations"].append("Distinct-Captain target was not achieved.")
                    if not both_teams_achieved:
                        captain_diversification["limitations"].append("Both-team Captain representation was not achieved.")
                    params.setdefault("strategy_runtime", {}).setdefault(
                        "showdown_portfolio_policy", {}
                    )["captain_diversification"] = captain_diversification

                status_local = "completed" if lineup_results_local else "failed"
                if status_local == "completed":
                    message_local = (
                        f"Optimizer completed: {len(lineup_results_local)} lineup(s) "
                        f"generated (mode={contest_type})"
                    )
                    if not portfolio_v3:
                        message_local += f"; max exposure={max_exposure:.2f}"
                    if portfolio_v3:
                        message_local += (
                            f"; CPT/core/QB/punt exposure={captain_rate:.2f}/"
                            f"{core_rate:.2f}/{qb_rate:.2f}/{punt_rate:.2f}"
                            "; hard QB correlations=enabled; quality floors=85% mean and 90% P90"
                        )
                        if stack_cfg["use_role_ownership"]:
                            message_local += "; CPT/FLEX ownership=enabled"
                        else:
                            message_local += "; GPP ownership unavailable — optimizing ceiling/correlation only"
                        if len(lineup_results_local) < num_lineups:
                            reason_counts = underfill_diagnostics.get("reason_counts") or {}
                            reason_text = ", ".join(
                                f"{reason.replace('_', ' ')} ({count})"
                                for reason, count in sorted(reason_counts.items())
                            ) or "other constraint (1)"
                            message_local += (
                                f"; generated {len(lineup_results_local)} of {num_lineups} requested "
                                "because the remaining candidates did not satisfy all portfolio "
                                f"constraints; rejection diagnostics (counts may overlap): {reason_text}; "
                                "quality floors were not relaxed"
                            )
                            params.setdefault("strategy_runtime", {}).setdefault(
                                "showdown_portfolio_policy", {}
                            )["underfill_diagnostics"] = dict(underfill_diagnostics)
                        if captain_diversification["enabled"]:
                            message_local += (
                                "; Captain diversity="
                                f"{len(captain_diversification['final_captain_exposures'])} distinct, "
                                f"both teams={'yes' if captain_diversification.get('both_teams_target_achieved') else 'no'}, "
                                f"target status={'PASS' if captain_diversification['targets_achieved'] else 'LIMITED'}"
                            )
                    if strategy == CLASSIC_HEAD_TO_HEAD_STRATEGY_ID:
                        message_local += f" using {CLASSIC_HEAD_TO_HEAD_STRATEGY_ID}"
                    elif contest_format == "classic" and objective == "cash":
                        message_local += f" using {CASH_OBJECTIVE_ID}"
                    message_local += f"; stack policy={stack_policy['policy_id']}"
                    if contest_format == "showdown":
                        starter_runtime = params.get("strategy_runtime", {}).get(
                            "starter_qb_filter", {}
                        )
                        message_local += (
                            "; starter QB filter="
                            f"{starter_runtime.get('evidence_status', 'unavailable')}"
                        )
                        if strategy in SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_IDS:
                            message_local += (
                                "; diagnostic captain position prior (not scored)="
                                f"{params['objective_config']['captain_prior_strength']:.2f}"
                            )
                        if require_qb_captain_receiver:
                            message_local += (
                                f"; rule={SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID}"
                            )
                else:
                    if portfolio_v3:
                        params.setdefault("strategy_runtime", {}).setdefault(
                            "showdown_portfolio_policy", {}
                        )["underfill_diagnostics"] = dict(underfill_diagnostics)
                        message_local = (
                            f"Optimizer generated 0 of {num_lineups} requested lineups because "
                            "no candidate satisfied all portfolio constraints; quality floors "
                            "were not relaxed."
                        )
                    else:
                        message_local = "Optimizer failed to find lineup (check salaries/projections)."
                    if require_qb_captain_receiver:
                        message_local += (
                            f" Enforced rule: {SHOWDOWN_QB_CAPTAIN_RECEIVER_RULE_ID}."
                        )
                return lineup_results_local, status_local, message_local

            lineup_results: List[List[dict]] = []
            status: str
            message: str
            uniqueness_overlap: int | None = None
            correlation_objective_multiplier = 0.0 if contest_format == "showdown" else 1.0

            if contest_format == "classic":
                from .classic_prospective import freeze_classic_run_input

                params.setdefault("strategy_runtime", {})["classic_run_input_snapshot"] = freeze_classic_run_input(
                    run_id=job_id, season=season, week=week, slate=slate,
                    created_at=now, cutoff=data_cutoff_at,
                    projection_run_id=projection_run_id, strategy=strategy,
                    rows=pool.to_dict("records"), params=params,
                )
                if live_classic and not allow_incomplete_evidence:
                    from .classic_data_readiness import validate_frozen_evidence
                    ready = validate_frozen_evidence(params["classic_evidence_snapshot"])
                    if not set(pool["player_id"].astype(str)) <= set(ready["generation_eligible_player_ids"]):
                        raise ValueError("Classic final solver pool contains a player outside the ready evidence")
                    params["classic_final_input_proof"] = {
                        "source_evidence_sha256": params["classic_evidence_snapshot"]["sha256"],
                        "solver_input_sha256": params["strategy_runtime"]["classic_run_input_snapshot"]["sha256"],
                        "required_projection_rows": len(pool),
                        "complete_projection_rows": int(pool["projection_inputs_complete"].eq(True).sum()),
                        "projection_run_id": projection_run_id,
                        "frozen_before_candidate_generation": True,
                    }
                    # Persist the final adapter rows as well as their original
                    # sources before the first candidate/solver invocation.
                    frozen_job.params = params
                    if not self._persist_optimizer_run(frozen_job):
                        raise ValueError("Classic final input freeze could not be persisted; generation blocked")
            use_gpp = (
                strategy_config["engine"] in {"slate_aware_gpp", "large_gpp_portfolio", "small_field_candidate_selector"}
                and contest_format == "classic"
                and objective == "gpp"
            )
            captain_coverage = (
                contest_format == "showdown" and num_lineups == 4
                and normalize_exposure_rate(params.get("captain_max_exposure"), default=0.60) == 0.25
            )
            if showdown_scenario:
                from .optimizer_scenario_mode import solve as solve_scenario
                lineup_results, scenario_audit, scenario_report = solve_scenario(self, pool, params=params,
                    cutoff=data_cutoff_at, contest_format='showdown', stack_params=stack_cfg, flex_only_ids=flex_only_ids)
                params.setdefault('strategy_runtime', {})['scenario_mode'] = scenario_report
                params['strategy_runtime']['highest_projection'] = scenario_audit
                if scenario_report['prepared'].get('new_model_primary'):
                    old_shortlist=params['strategy_runtime']['showdown_captain_shortlist']
                    params['strategy_runtime']['scenario_incumbent_captain_shortlist']=old_shortlist
                    supported={p['player_master_id'] for p in scenario_report['prepared']['players'] if p['conditional_mean'] is not None}
                    candidates=[dict(player_id=str(r['player_id']),name=r.get('name'),position=r['position'],team=r.get('player_team'))
                        for r in pool.to_dict('records') if str(r['player_id']) in supported and str(r['player_id']) not in flex_only_ids
                        and not captain_preference_exclusions(params,r['position'],str(r['player_id']))]
                    params['strategy_runtime']['showdown_captain_shortlist']=dict(policy_id='new_model_primary_covered_captains_v1',
                        shortlist=candidates,exclusions=[],ranking='new-model score supported; factual/user constraints remain binding',
                        parent_incumbent_policy=old_shortlist['policy_id'])
                params['objective_config'].update(objective_id='conditional_mean', score_column='scenario_mean',
                    captain_score_column='conditional_mean', flex_score_column='conditional_mean',
                    conditional_adjustments=True, scoring_version='prepared_optimizer_scenario_v1')
                if scenario_report['prepared'].get('new_model_primary'):
                    params['objective_config'].update(objective_id='new_model_primary',scoring_version='new_model_primary_v1',
                        incumbent_projection_consumed_for_primary=False,incumbent_p90_shortlist_consumed_for_primary=False,
                        objective_weights={'new_model_captain_score':1.5,'new_model_flex_score':1.0},
                        captain_shortlist_size=len(candidates),captain_eligibility_policy='new_model_primary_covered_captains_v1')
                status = 'completed' if lineup_results else 'failed'
                message = 'Experimental scenario mean; matched Captain baseline; ' + scenario_audit['solver_status']
            elif workload_comparison:
                from .workload_optimizer import solve as solve_workload
                lineup_results, workload_report = solve_workload(self, pool, params=params,
                    contest_type=contest_type, stack_params=stack_cfg, locked_ids=locked_ids,
                    flex_only_ids=flex_only_ids, avoid_dst_opponents=avoid_dst_opponents,
                    enforce_single_te=enforce_single_te, requested_captain_id=requested_captain_id)
                params.setdefault("strategy_runtime", {})["workload_comparison"] = workload_report
                status = "completed" if lineup_results else "failed"
                message = "Offensive workload comparison; " + workload_report["status"]
            elif highest_projection:
                from .classic_highest_projection import solve as solve_highest_projection
                if params.get("scenario_mode"):
                    from .optimizer_scenario_mode import solve as solve_scenario
                    lineup_results,projection_report,scenario_report=solve_scenario(self,pool,params=params,cutoff=data_cutoff_at)
                    params.setdefault("strategy_runtime", {})["scenario_mode"]=scenario_report
                    params['objective_config'].update(objective_id='conditional_mean',score_column='scenario_mean',scoring_version='prepared_optimizer_scenario_v1')
                else:
                    lineup_results, projection_report = solve_highest_projection(self, pool, params=params, cutoff=data_cutoff_at)
                params.setdefault("strategy_runtime", {})["highest_projection"] = projection_report
                status = "completed" if lineup_results else "failed"
                message = projection_report["objective_label"] + "; optional stacks/bringbacks; " + str(projection_report["solver_status"])
            elif merged_analyst:
                from .analyst_packets import load_packet
                from .analyst_scenarios import run_merged
                if contest_format == "showdown":
                    role_defaults = {"captain_max_exposure": .60, "core_player_max_exposure": .80,
                        "starting_qb_max_exposure": 1.0, "cheap_punt_max_exposure": .40} if portfolio_v3 else {
                        "captain_max_exposure": 1.0, "core_player_max_exposure": 1.0,
                        "starting_qb_max_exposure": 1.0, "cheap_punt_max_exposure": 1.0}
                    for key, default in role_defaults.items():
                        params[key] = normalize_exposure_rate(params.get(key), default=default)
                    # Merged generation bypasses legacy selector branches; their
                    # final shared validation still needs the same hard rates.
                    exposure_rates = {role: params[key] for role, key in {
                        "captain": "captain_max_exposure", "core": "core_player_max_exposure",
                        "starting_qb": "starting_qb_max_exposure", "cheap_punt": "cheap_punt_max_exposure"}.items()}
                merged_stack = {**stack_cfg,
                    "single_lineup_user_controls": {key: params[key] for key in
                        ("max_players_per_team", "max_players_per_game", "max_elevated_players_per_lineup")
                        if params.get(key) is not None}, "single_lineup_cutoff": data_cutoff_at}
                lineup_results, analyst_report = run_merged(self, pool,
                    params={**params, "max_exposure": max_exposure},
                    packet=load_packet(params["analyst_packet_sha256"]),
                    fmt=contest_format.upper(), season=season, week=week, slate=slate,
                    requested=num_lineups, progress=progress, source_pool_rows=_json_safe(initial_pool.to_dict("records")), solve_kwargs={"score_col": score_col,
                        "contest_type": contest_type, "stack_params": merged_stack,
                        "locked_player_ids": locked_ids, "flex_only_player_ids": flex_only_ids,
                        "rule_profile": rule_profile, "locked_captain_player_id": requested_captain_id,
                        "enforce_single_te": enforce_single_te, "avoid_dst_opponents": avoid_dst_opponents})
                params.setdefault("strategy_runtime", {})["football_analyst"] = analyst_report
                if shared_world_mode:
                    params["objective_config"] = {"objective_id": SHARED_WORLD_POLICY,
                        "score_column": "common_world_conditional_mean", "captain_score_column": "conditional_mean",
                        "flex_score_column": "conditional_mean", "captain_multiplier": 1.5,
                        "captain_salary_multiplier": 1.5, "marginal_p90_scored": False, "ownership_scored": False,
                        "captain_shortlist_size": len(params.get("strategy_runtime", {}).get("showdown_captain_shortlist", {}).get("shortlist", [])),
                        "anchor_world_id": analyst_report["shared_world_selection"].get("anchor_world_id"),
                        "portfolio_objective": "Expected-anchor conditional mean first, then incremental common-world point coverage"}
                    params["strategy_config"] = {**params["strategy_config"], "selection_policy": SHARED_WORLD_POLICY,
                        "description": "Expected anchor and supported shared-world full-roster coverage; static strategy stacks omitted; explicit user controls retained."}
                if contest_format == "showdown":
                    analyst_report["captain_workload_policy"] = params["strategy_runtime"]["showdown_captain_shortlist"]
                params.setdefault("objective_config", {})["analyst_strategy"] = "MERGED_SCENARIOS"
                status = "completed" if len(lineup_results) == num_lineups else "partial" if lineup_results else "failed"
                message = f"Merged Analyst scenarios selected {len(lineup_results)}/{num_lineups}; quality screen=none"
                if contest_format == "showdown" and len(lineup_results) < num_lineups:
                    qualified = params["strategy_runtime"]["showdown_captain_shortlist"]["shortlist"]
                    message += (f"; {len(qualified)} supported Captain roles after user preferences; "
                                "Captain exposure is checked against the achieved portfolio; no constraints relaxed")
            elif captain_coverage:
                from .showdown_captain_coverage import solve_captain_coverage
                exposure_rates = None
                if portfolio_v3 or single_entry or three_max or small_max or single_lineup:
                    defaults = {"core": .80, "starting_qb": 1.0, "cheap_punt": .40} if portfolio_v3 else {
                        "core": 1.0, "starting_qb": 1.0, "cheap_punt": 1.0}
                    keys = {"core": "core_player_max_exposure", "starting_qb": "starting_qb_max_exposure",
                            "cheap_punt": "cheap_punt_max_exposure"}
                    exposure_rates = {role: normalize_exposure_rate(params.get(keys[role]), default=default)
                                      for role, default in defaults.items()}
                    for role, key in keys.items():
                        params[key] = exposure_rates[role]
                    exposure_rates["captain"] = .25
                params["captain_max_exposure"] = .25
                if single_lineup:
                    stack_cfg.update({"require_starting_qb": not params.get("no_qbs", False),
                                      "hard_qb_correlations": not params.get("no_qbs", False)})
                lineup_results, coverage_report = solve_captain_coverage(
                    pool, solve=self._solve_lineup,
                    solve_kwargs={"score_col": score_col, "contest_type": contest_type,
                        "stack_params": stack_cfg, "locked_player_ids": locked_ids,
                        "flex_only_player_ids": flex_only_ids, "rule_profile": rule_profile,
                        "enforce_single_te": enforce_single_te, "avoid_dst_opponents": avoid_dst_opponents,
                        "include_control_comparison": False},
                    shortlist=params["strategy_runtime"]["showdown_captain_shortlist"]["shortlist"],
                    exposure_rates=exposure_rates, max_exposure=max_exposure,
                    requested_captain_id=requested_captain_id,
                    single_lineup_controls=params if single_lineup else None, cutoff=data_cutoff_at,
                )
                params["strategy_runtime"]["showdown_captain_coverage"] = coverage_report
                status = "completed" if lineup_results else "failed"
                message = f"Generated {len(lineup_results)}/4 captain coverage lineups; underfill={coverage_report['underfill']}"
                warning_count = sum(bool(row.get("quality_floor_warnings")) for row in coverage_report["captains"])
                message += f"; lineups with quality-floor warnings={warning_count}"
                if coverage_report["missing_eligible_captains"]:
                    message += f"; only {4 - coverage_report['missing_eligible_captains']} eligible captains"
                if coverage_report["underfill"]:
                    reasons = [row["reason"] for row in coverage_report["captains"] if row["status"] != "selected"]
                    if reasons:
                        message += "; " + "; ".join(reasons)
            elif single_lineup:
                from .single_lineup import contest_context
                contest = contest_context(params, pool.to_dict("records"), contest_format=contest_format)
                candidate_target = max(60 if contest_format == "showdown" else 120, num_lineups * 6)
                single_stack = {**stack_cfg, "use_role_ownership": False,
                    "require_starting_qb": contest_format == "showdown" and not params.get("no_qbs", False),
                    "hard_qb_correlations": contest_format == "showdown" and not params.get("no_qbs", False),
                    "saturate_correlations": contest_format == "showdown",
                    "single_lineup_user_controls": {k: params[k] for k in ("max_players_per_team", "max_players_per_game",
                        "max_elevated_players_per_lineup") if params.get(k) is not None},
                    "single_lineup_cutoff": data_cutoff_at}
                candidates = generate_single_lineup_candidates(pool, self._solve_lineup,
                    contest_format=contest_format, target=candidate_target,
                    requested_captain_id=requested_captain_id,
                    base_kwargs={"contest_type": contest_type, "stack_params": single_stack,
                        "enforce_single_te": enforce_single_te, "avoid_dst_opponents": avoid_dst_opponents,
                        "locked_player_ids": locked_ids, "flex_only_player_ids": flex_only_ids,
                        "rule_profile": rule_profile})
                competition_supported = params.get("data_readiness", {}).get("status") == "READY"
                if contest_format == "showdown":
                    competition_supported = competition_supported and bool(
                        params["data_readiness"].get("ownership", {}).get("ownership_fresh")
                        and self._showdown_ownership_selector_policy(pool)["eligible"])
                competition_supported = competition_supported and all(
                    (value := number(row.get("ownership"))) is not None and 0 <= value <= 100
                    for lineup in candidates for row in lineup)
                lineup_results, single_report = select_single_lineup(candidates, strategy=strategy,
                    competition_supported=competition_supported, contest=contest,
                    controls={**params, "locked_player_ids": sorted(locked_ids)}, cutoff=data_cutoff_at)
                single_report["generation"] = {"target": candidate_target, "generated": len(candidates),
                    "method": "legal_ilp_risk_views_and_captain_or_qb_families",
                    "ignored_portfolio_controls": params.get("ignored_portfolio_controls", [])}
                params.setdefault("strategy_runtime", {})["single_lineup"] = single_report
                params["objective_config"] = {"objective_id": strategy, "selection_policy": single_report["contract_id"],
                    "objective_weights": single_report["objective_weights"], "evidence_status": "transparent_proxy_unvalidated"}
                if contest_format == "showdown":
                    params["objective_config"].update({
                        "scoring_version": CAPTAIN_SHORTLIST_POLICY_ID,
                        "captain_score_column": "p90", "flex_score_column": "projection",
                        "captain_multiplier": 1.5, "captain_salary_multiplier": 1.5,
                        "captain_shortlist_size": 4,
                    })
                stack_cfg = single_stack
                if params.get("data_readiness"):
                    params["data_readiness"]["solver_called"] = True
                status = "completed" if len(lineup_results) == num_lineups else "failed"
                message = (f"Selected {len(lineup_results)} of {num_lineups} requested cash-oriented lineup(s) from {len(candidates)} candidates; "
                    "unvalidated proxy, cash probability unavailable" +
                    ("; requested count cannot be met within the candidate pool and user limits; no limits relaxed" if status == "failed" else ""))
                uniqueness_overlap = single_report["constraint_selection"].get("effective_overlap")
            elif use_gpp:
                try:
                    small_field = strategy == CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID
                    solver_backend = "bundled"
                    discovery_workers = 1
                    parallel_fallback_reason = None
                    if small_field:
                        from .cbc_solver import resolve_cbc_backend

                        solver_backend = resolve_cbc_backend(
                            str(params.get("classic_solver_backend", "bundled"))
                        )
                        raw_workers = params.get("classic_candidate_workers", 1)
                        if isinstance(raw_workers, bool) or not isinstance(raw_workers, int) or not 1 <= raw_workers <= 4:
                            raise ValueError("classic_candidate_workers must be an integer between 1 and 4")
                        discovery_workers = raw_workers
                        if discovery_workers > 1 and os.environ.get("PYTHONHASHSEED") != "0":
                            discovery_workers = 1
                            parallel_fallback_reason = (
                                "Parallel discovery requires PYTHONHASHSEED=0 at process start; "
                                "used one worker for deterministic results"
                            )
                    candidate_target = (
                        1
                        if long_shot_mode
                        else max(100, min(250, int(params.get("classic_candidate_pool_size", 120))))
                        if small_field
                        else num_lineups
                    )
                    expanded_discovery = params.get("classic_expanded_discovery", False) if small_field else False
                    if type(expanded_discovery) is not bool:
                        raise ValueError("classic_expanded_discovery must be a boolean")
                    production_candidate_target = candidate_target
                    if small_field:
                        raw_production_target = params.get("classic_production_candidate_pool_size", candidate_target)
                        if isinstance(raw_production_target, bool) or not isinstance(raw_production_target, int) or not candidate_target <= raw_production_target <= 250:
                            raise ValueError("classic_production_candidate_pool_size must be an integer from the seed target through 250")
                        production_candidate_target = raw_production_target
                    maximum_exposure_by_player = dict(
                        params.get("maximum_exposure_by_player") or {}
                    )
                    minimum_exposure_by_player = dict(
                        params.get("minimum_exposure_by_player") or {}
                    )
                    conflicting_lock_caps = {
                        player_id
                        for player_id in locked_ids
                        if player_id in maximum_exposure_by_player
                        and float(maximum_exposure_by_player[player_id]) < 1.0
                    }
                    if conflicting_lock_caps:
                        raise ValueError(
                            "Locked players require 100% maximum exposure: "
                            + ", ".join(sorted(conflicting_lock_caps))
                        )
                    for player_id in locked_ids:
                        maximum_exposure_by_player[player_id] = 1.0
                        minimum_exposure_by_player[player_id] = 1.0
                    risk_controls = None
                    candidate_caps: dict[str, float] = {}
                    elevated_ids: set[str] = set()
                    if small_field:
                        from .classic_prospective import (
                            classify_pool, core_classes, resolve_overrides, resolve_risk_policy,
                        )

                        risk_mode = params.get("availability_risk_mode", "conservative")
                        if risk_mode not in {"conservative", "off"}:
                            raise ValueError("availability_risk_mode must be conservative or off")
                        params["availability_risk_mode"] = risk_mode
                        if risk_mode == "conservative":
                            risk_policy = resolve_risk_policy(params.get("classic_availability_risk_policy"))
                            risks = classify_pool(pool.to_dict("records"), now)
                            overrides = resolve_overrides(
                                params.get("classic_availability_overrides"), set(risks),
                            )
                            risk_players = self._gpp_players_from_pool(pool)
                            core = core_classes(risk_players, risks)
                            for player in risk_players:
                                pid = player.player_id
                                bucket = risks[pid]["bucket"]
                                override = overrides.get(pid, {})
                                if bucket == "out" or bucket == "doubtful" and not override.get("allow_doubtful"):
                                    candidate_caps[pid] = 0.0
                                else:
                                    candidate_caps[pid] = float(override.get("candidate_cap", {
                                        "questionable_elevated": risk_policy["elevated_candidate_cap"],
                                        "questionable_full_role": risk_policy["full_role_candidate_cap"],
                                    }.get(bucket, risk_policy["elite_candidate_cap"] if core[pid] == "elite_high_confidence"
                                          else risk_policy["non_elite_candidate_cap"])))
                                selected_cap = override.get("selected_cap", {
                                    "questionable_elevated": risk_policy["elevated_selected_cap"],
                                    "questionable_full_role": risk_policy["full_role_selected_cap"],
                                }.get(bucket))
                                if selected_cap is not None:
                                    maximum_exposure_by_player[pid] = min(
                                        maximum_exposure_by_player.get(pid, 1.0), float(selected_cap),
                                    )
                                if bucket == "questionable_elevated":
                                    elevated_ids.add(pid)
                                if pid in locked_ids and bucket == "normal":
                                    candidate_caps[pid] = 1.0
                                if pid in locked_ids and candidate_caps[pid] < 1.0:
                                    raise ValueError(f"Locked risk player {pid} requires a reasoned candidate-cap override")
                            allowed = {pid for pid, cap in candidate_caps.items() if cap > 0}
                            pool = pool.loc[pool["player_id"].astype(str).isin(allowed)].copy()
                            risk_controls = {"mode": risk_mode, "policy": risk_policy,
                                             "classifications": risks, "core_classes": core,
                                             "overrides": overrides, "candidate_caps": candidate_caps,
                                             "locked_ids": sorted(locked_ids)}
                    salary_identity = {"status": "UNAVAILABLE", "checked": 0, "violations": []}
                    if small_field and self.engine.dialect.name == "postgresql":
                        source_ids = [int(value) for value in pool["salary_source_row_id"].dropna()]
                        with self.engine.connect() as connection:
                            saved_salaries = [dict(row) for row in connection.execute(text("""
                                SELECT curated_salary_id, player_master_id, team, opponent, salary
                                FROM public.curated_salary
                                WHERE curated_salary_id = ANY(:source_ids)
                            """), {"source_ids": source_ids}).mappings()]
                        salary_identity = validate_saved_salary_identity(
                            pool.to_dict("records"), saved_salaries,
                        )
                        if salary_identity["violations"]:
                            raise ValueError("Saved salary identity mismatch: " +
                                             str(salary_identity["violations"][:5]))
                    ownership_values = (
                        pd.to_numeric(pool["ownership"], errors="coerce")
                        if "ownership" in pool.columns else pd.Series(dtype=float)
                    )
                    ownership_covered = int(ownership_values.notna().sum())
                    ownership_available = bool(len(pool) and ownership_covered == len(pool))
                    ownership_evidence = {
                        "status": ("available" if ownership_available else
                                   "partial" if ownership_covered else "unavailable"),
                        "source": "target.ownership_projection",
                        "covered_players": ownership_covered,
                        "eligible_players": len(pool),
                        "ownership_run_ids": sorted({str(value) for value in pool.get("ownership_run_id", pd.Series(dtype=str)).dropna()}),
                        "missing_reason": None if ownership_available else (
                            "No current-slate ownership projections" if ownership_covered == 0
                            else "Partial player coverage; evaluate ownership by candidate"
                        ),
                    }
                    generation_players = self._gpp_players_from_pool(pool)
                    seed_starting_qb_ids = {
                        str(row["player_id"]) for row in pool.to_dict("records")
                        if row.get("position") == "QB" and row.get("is_starting_qb") in (True, 1)
                    } if small_field else set()
                    parallel_seeds = (
                        small_field and discovery_workers > 1 and candidate_target > 1
                        and len(seed_starting_qb_ids) >= discovery_workers
                        and not locked_ids
                    )
                    if small_field and discovery_workers > 1 and not parallel_seeds:
                        parallel_fallback_reason = (
                            parallel_fallback_reason or
                            "Parallel seed generation requires one starting QB per worker "
                            "and no locked players; used sequential seeds"
                        )
                    frozen_generation_inputs = None
                    if small_field:
                        frozen_rows = [
                            _json_safe({**asdict(player), "tags": sorted(player.tags)})
                            for player in generation_players
                        ]
                        frozen_options = _json_safe({
                            "candidate_target": candidate_target,
                            "production_candidate_target": production_candidate_target,
                            "seed_generation_method": "parallel_qb_shards" if parallel_seeds else "sequential",
                            "seed_generation_workers": discovery_workers if parallel_seeds else 1,
                            "generation_max_exposure": 1.0,
                            "ownership_available": ownership_available,
                            "candidate_aware_ownership": True,
                            "long_shot_mode": long_shot_mode,
                            "large_gpp": strategy in {CLASSIC_LARGE_GPP_STRATEGY_ID, CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID},
                            "minimum_uniqueness": int(params.get("minimum_uniqueness", 2)),
                            "max_players_per_team": params.get("max_players_per_team"),
                            "max_players_per_game": params.get("max_players_per_game"),
                            "stack_templates": params.get("stack_templates"),
                            "enforce_single_te": enforce_single_te,
                            "avoid_dst_opponents": avoid_dst_opponents,
                            "locked_player_ids": sorted(locked_ids),
                            "starting_qb_ids": sorted(
                                str(row["player_id"]) for row in pool.to_dict("records")
                                if row.get("position") == "QB" and row.get("is_starting_qb") in (True, 1)
                            ),
                            "solver_backend": solver_backend,
                        })
                        frozen_payload = {"players": frozen_rows, "options": frozen_options}
                        frozen_generation_inputs = {
                            "contract": "classic_frozen_generation_inputs_v1",
                            "captured_stage": "after_eligibility_context_and_ownership_before_candidate_generation",
                            "sha256": hashlib.sha256(json.dumps(
                                frozen_payload, sort_keys=True, separators=(",", ":"),
                                allow_nan=False,
                            ).encode()).hexdigest(),
                            **frozen_payload,
                        }
                    generation_request = dict(
                        season=season,
                        week=week,
                        slate=slate,
                        num_lineups=1 if parallel_seeds else candidate_target,
                        engine=self.engine,
                        players=generation_players,
                        ownership_available=ownership_available,
                        max_exposure=1.0 if small_field else max_exposure,
                        enforce_single_te=enforce_single_te,
                        avoid_dst_opponents=avoid_dst_opponents,
                        large_gpp=(strategy in {CLASSIC_LARGE_GPP_STRATEGY_ID, CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID}),
                        minimum_uniqueness=int(params.get("minimum_uniqueness", 2)),
                        max_from_team=params.get("max_players_per_team"),
                        max_from_game=params.get("max_players_per_game"),
                        stack_templates=params.get("stack_templates"),
                        maximum_exposure_by_player=(
                            {} if parallel_seeds else
                            {pid: cap for pid, cap in candidate_caps.items() if cap > 0}
                            if small_field else maximum_exposure_by_player
                        ),
                        minimum_exposure_by_player=(
                            {} if parallel_seeds else
                            {player_id: 1.0 for player_id in locked_ids}
                            if small_field else minimum_exposure_by_player
                        ),
                        include_control_comparisons=not small_field,
                        long_shot_mode=long_shot_mode,
                        candidate_aware_ownership=small_field,
                        solver_backend=solver_backend,
                        precompute_correlation_terms=small_field,
                        maximum_player_groups=(
                            [(elevated_ids, risk_policy["max_elevated_per_lineup"])]
                            if small_field and risk_controls and elevated_ids else None
                        ),
                    )
                    if params.get("analyst_packet_sha256"):
                        from .analyst_packets import load_packet
                        generation_request["analyst_packet"] = load_packet(params["analyst_packet_sha256"])
                        generation_request["analyst_candidates_per_thesis"] = int(params.get("analyst_candidates_per_thesis", 2))
                    generation_request["max_lineups_per_primary_game"] = params.get("max_lineups_per_primary_game") if not small_field else None
                    if strategy == CLASSIC_LARGE_GPP_STRATEGY_ID:
                        from .classic_strategy_contract import build_strategy_contract, execute_strategy_contract, portfolio_audit
                        from .classic_prospective import classify_pool
                        from .classic_portfolio_controls import LARGE_GPP_CONTROL_KEYS, validate_requested_overlap
                        generation_request.update({key: params[key] for key in LARGE_GPP_CONTROL_KEYS if params.get(key) is not None})
                        contract = build_strategy_contract(players=generation_players,
                            pipeline_options=generation_request, requested=params,
                            risk_classifications=classify_pool(pool.to_dict("records"), data_cutoff_at or now),
                            metadata={"optimizer_run_id": job_id, "projection_run_id": projection_run_id,
                                      "input_snapshot_sha256": params["strategy_runtime"]["classic_run_input_snapshot"]["sha256"]})
                        validate_requested_overlap(params, contract)
                        params["effective_strategy_contract"] = contract
                        if live_classic and not allow_incomplete_evidence:
                            params["classic_final_input_proof"]["strategy_sha256"] = contract["sha256"]
                            frozen_job.params = params
                            if not self._persist_optimizer_run(frozen_job):
                                raise ValueError("Classic strategy freeze could not be persisted; generation blocked")
                        params.setdefault("data_readiness", {})["solver_called"] = True
                        try:
                            gpp_result = execute_strategy_contract(contract, engine=self.engine)
                        except ValueError as exc:
                            report = portfolio_audit(contract, [])
                            report["validation"]["violations"].append("conflicting_constraints")
                            report["feasibility"]["explanation"] = str(exc)
                            params["portfolio_controls_report"] = report
                            params["strategy_runtime"]["strategy_contract_audit"] = report
                            raise
                        params["strategy_runtime"]["strategy_contract_audit"] = portfolio_audit(
                            contract, gpp_result.lineups, trace=gpp_result.selection_trace)
                        params["portfolio_controls_report"] = params["strategy_runtime"]["strategy_contract_audit"]
                        if params["portfolio_controls_report"]["validation"]["status"] != "verified":
                            gpp_result.status = "failed"
                            gpp_result.message += "; independent portfolio validation failed: " + ", ".join(params["portfolio_controls_report"]["validation"]["violations"])
                    else:
                        gpp_result = run_gpp_pipeline(**generation_request)
                    if params.get("analyst_packet_sha256"):
                        analyst_steps = [row["football_analyst"] for row in gpp_result.selection_trace if row.get("football_analyst")]
                        params.setdefault("strategy_runtime", {})["football_analyst"] = {
                            "mode": "ANALYST_CONSTRUCTION", "packet_sha256": params["analyst_packet_sha256"],
                            "steps": analyst_steps, "selection": "unchanged exact sequential objective and caps",
                            "selected_thesis_ids_by_step": [row.get("analyst_thesis_ids", []) for row in gpp_result.selection_trace],
                        }
                    small_field_report = None
                    if small_field:
                        from .classic_small_field import analyze_small_field, expand_candidate_discovery, generate_parallel_seeds
                        from .classic_prospective import (
                            freeze_solver_snapshot, run_prospective_experiment,
                            slate_kickoff_evidence_pool,
                        )
                        all_players = self._gpp_players_from_pool(pool)
                        tag_players(all_players, gpp_result.config.tag_thresholds)
                        if parallel_seeds:
                            gpp_result = generate_parallel_seeds(
                                gpp_result, all_players, count=candidate_target,
                                max_workers=discovery_workers,
                                starting_qb_ids=seed_starting_qb_ids,
                                candidate_caps=candidate_caps,
                                elevated_ids=elevated_ids,
                                max_elevated=risk_policy["max_elevated_per_lineup"] if risk_controls else 9,
                                enforce_single_te=enforce_single_te,
                                avoid_dst_opponents=avoid_dst_opponents,
                                solver_backend=solver_backend,
                            )
                        starting_qb_ids = {
                            str(row["player_id"]) for row in pool.to_dict("records")
                            if row.get("position") == "QB" and row.get("is_starting_qb") in (True, 1)
                        }
                        gpp_result.lineups, discovery_diagnostics = expand_candidate_discovery(
                            gpp_result, all_players,
                            enforce_single_te=enforce_single_te,
                            avoid_dst_opponents=avoid_dst_opponents,
                            locked_player_ids=locked_ids,
                            starting_qb_ids=starting_qb_ids or None,
                            max_workers=discovery_workers,
                            solver_backend=solver_backend,
                        )
                        source_rows = pool.to_dict("records")
                        for source_row in source_rows:
                            if (source_row.get("position") in {"RB", "WR", "TE"}
                                    and float(source_row.get("salary") or 0) <= 4500):
                                source_row["opportunity_diagnostic"] = showdown_opportunity_diagnostic(source_row)
                        source_by_id = {str(row["player_id"]): row for row in source_rows}
                        if expanded_discovery:
                            from .classic_expanded_discovery import expand_reviewed_discovery
                            gpp_result.lineups, discovery_diagnostics = expand_reviewed_discovery(
                                gpp_result, all_players, source_rows, risk_controls,
                                {**frozen_options,"exclude_player_ids":sorted(exclude_ids)},
                                workers=discovery_workers,
                            )
                        if params.get("analyst_packet_sha256"):
                            by_id = {player.player_id: player for player in all_players}
                            signatures = {tuple(sorted(player.player_id for player in lineup)) for lineup in gpp_result.lineups}
                            for step in gpp_result.selection_trace:
                                for candidate in (step.get("football_analyst") or {}).get("shadow", []):
                                    signature = tuple(sorted(row["player_master_id"] for row in candidate["roster"]))
                                    if candidate["eligibility_outcome"] != "DIAGNOSTIC_ONLY" and signature not in signatures:
                                        gpp_result.lineups.append([by_id[pid] for pid in signature])
                                        signatures.add(signature)
                            params["strategy_runtime"]["football_analyst"]["merged_distinct_candidate_count"] = len(gpp_result.lineups)
                            params["strategy_runtime"]["football_analyst"]["selection"] = "existing small-field quality screen and constrained portfolio selector"
                        for candidate in gpp_result.lineups:
                            legal, reason = self._validate_classic_lineups(
                                [[self._gpp_player_to_dict(player) for player in candidate]],
                                requested_lineups=1, max_exposure=1.0,
                                enforce_single_te=enforce_single_te,
                                avoid_dst_opponents=avoid_dst_opponents,
                                locked_player_ids=locked_ids,
                                excluded_player_ids=exclude_ids,
                                excluded_opponent_teams=excluded_opponent_teams,
                                minimum_player_salary=params.get("minimum_player_salary"),
                                season_ppg_eligible_ids=season_ppg_eligible_ids,
                                favored_team_positions=favored_team_positions,
                                minimum_qb_salary=params.get("minimum_qb_salary"),
                                minimum_rb_salary=params.get("minimum_rb_salary"),
                            )
                            if not legal:
                                raise ValueError(f"Candidate failed Classic legality: {reason}")
                        selected, small_field_report = analyze_small_field(
                            gpp_result,
                            pool_rows=[{**source_by_id[player.player_id], "gpp_player": player} for player in all_players],
                            count=num_lineups, max_exposure=max_exposure,
                            ownership_available=ownership_available,
                            locked_player_ids=locked_ids,
                            maximum_exposure_by_player=maximum_exposure_by_player,
                            minimum_exposure_by_player=minimum_exposure_by_player,
                            requested_candidate_count=production_candidate_target,
                            strict_candidate_target="classic_production_candidate_pool_size" in params,
                            ownership_evidence=ownership_evidence,
                            candidate_aware_ownership=True,
                            discovery_diagnostics=discovery_diagnostics,
                            enforce_single_te=enforce_single_te,
                            avoid_dst_opponents=avoid_dst_opponents,
                            solver_backend=solver_backend,
                            refill_workers=discovery_workers,
                            portfolio_constraints=params.get("portfolio_constraints"),
                            production_controls=risk_controls,
                            full_reference_selection=expanded_discovery,
                            run_qb_family_diagnostics=(
                                False if long_shot_mode
                                else bool(params.get("classic_qb_family_diagnostics", True))
                            ),
                        )
                        prospective_options = {
                            **frozen_options,
                            "requested_lineups": num_lineups,
                            "selection_max_exposure": max_exposure,
                            "maximum_exposure_by_player": maximum_exposure_by_player,
                            "minimum_exposure_by_player": minimum_exposure_by_player,
                            "exclude_player_ids": sorted(exclude_ids),
                            "locked_player_ids": sorted(locked_ids),
                            "policy_contract": small_field_report["policy_contract"],
                            "portfolio_constraints": params.get("portfolio_constraints") or {},
                            "risk_policy": params.get("classic_availability_risk_policy") or {},
                            "risk_overrides": params.get("classic_availability_overrides") or {},
                            "candidate_discovery": {"max_workers": discovery_workers,
                                                    "solver_backend": solver_backend},
                            "pruning": {"post_expansion_pruning": "none",
                                        "deduplication": "canonical_player_id_roster",
                                        "post_expansion_candidate_cap": None},
                            "deterministic_seed": params.get("seed"),
                        }
                        solver_snapshot = freeze_solver_snapshot(
                            run_id=job_id, season=season, week=week, slate=slate,
                            created_at=now, cutoff=data_cutoff_at,
                            projection_run_id=projection_run_id, strategy=strategy,
                            players=all_players, pool_rows=source_rows,
                            source_pool_rows=initial_pool.to_dict("records"),
                            options=prospective_options, resolved_config=gpp_result.config,
                            policy_ids={"stack": params.get("stack_policy_id"),
                                        "correlation_context": strategy_config.get("policy_alignment"),
                                        "correlation_profile": {
                                            "id": resolve_strategy_profile(contest_format="classic", objective="gpp").profile_id,
                                            "version": resolve_strategy_profile(contest_format="classic", objective="gpp").version,
                                        },
                                        "correlation_policy": (params.get("decision_context") or {}).get("correlation_policy"),
                                        "context_policy": (params.get("decision_context") or {}).get("context_policy"),
                                        "ownership_policy": ownership_evidence.get("source"),
                                        "rule_run_id": rule_run_id},
                        )
                        small_field_report["frozen_solver_snapshot"] = solver_snapshot
                        small_field_report["salary_identity"] = salary_identity
                        small_field_report["generation_funnel"] = {
                            **(gpp_result.generation_funnel or {}),
                            "production_admission": small_field_report.get("production_funnel"),
                        }
                        from .optimizer_effectiveness import chronological_validation

                        kickoff_evidence = slate_kickoff_evidence_pool(initial_pool.to_dict("records"))
                        prelock_timing = chronological_validation(
                            {"data_cutoff_at": (data_cutoff_at.replace(tzinfo=data_cutoff_at.tzinfo or timezone.utc)
                                                if data_cutoff_at else None),
                             "optimizer_created_at": now.replace(tzinfo=timezone.utc)},
                            kickoff_evidence,
                        )
                        small_field_report["prelock_timing"] = prelock_timing
                        from .classic_small_field import classic_entry_readiness
                        small_field_report["entry_readiness"] = classic_entry_readiness(
                            players=all_players, selected=selected,
                            candidates=small_field_report["all_candidates"],
                            source=source_by_id, salary_identity=salary_identity,
                            production_funnel=small_field_report.get("production_funnel"),
                            controls=risk_controls,
                            first_kickoff_at=prelock_timing.get("first_saved_kickoff_at"),
                            decision_at=now, requested_count=num_lineups,
                            market_fresh_hours=float(params.get("market_fresh_hours", 6)),
                            market_stale_hours=float(params.get("market_stale_hours", 24)),
                            market_stale_policy=str(params.get("market_stale_policy", "warning")),
                        )
                        if params.get("classic_prospective_experiment", True) and prelock_timing["status"] == "predecision":
                            try:
                                small_field_report["prospective_experiment"] = run_prospective_experiment(
                                    snapshot=solver_snapshot,
                                    production_candidates=small_field_report["all_candidates"],
                                    production_selected_ranks=small_field_report["selected_ranks"],
                                    players=all_players, source_rows=source_rows,
                                    config=gpp_result.config, selected_count=num_lineups,
                                    max_exposure=max_exposure, locked_ids=locked_ids,
                                    maximums=maximum_exposure_by_player,
                                    minimums=minimum_exposure_by_player,
                                    ownership_available=ownership_available,
                                    enforce_single_te=enforce_single_te,
                                    avoid_dst_opponents=avoid_dst_opponents,
                                    solver_backend=solver_backend,
                                    risk_config=params.get("classic_availability_risk_policy"),
                                    override_config=params.get("classic_availability_overrides"),
                                )
                                completion_timing = chronological_validation(
                                    {"data_cutoff_at": data_cutoff_at,
                                     "optimizer_created_at": datetime.now(timezone.utc)},
                                    kickoff_evidence,
                                )
                                if completion_timing["status"] != "predecision":
                                    small_field_report["prospective_experiment"] = {
                                        "status": "not_frozen_prelock",
                                        "reason": "shadow_completed_at_or_after_saved_kickoff",
                                        "frozen_snapshot_sha256": solver_snapshot["sha256"],
                                    }
                            except ValueError as exc:
                                small_field_report["prospective_experiment"] = {
                                    "status": "blocked_invalid_or_late_pregame_evidence",
                                    "reason": str(exc),
                                    "frozen_snapshot_sha256": solver_snapshot["sha256"],
                                }
                        elif params.get("classic_prospective_experiment", True):
                            small_field_report["prospective_experiment"] = {
                                "status": "not_frozen_prelock", "reason": prelock_timing["reason"],
                                "frozen_snapshot_sha256": solver_snapshot["sha256"],
                            }
                        small_field_report["frozen_generation_inputs"] = frozen_generation_inputs
                        small_field_report["strategy_policy_alignment"] = strategy_config["policy_alignment"]
                        small_field_report["contest_intent"] = params.get("contest_intent") or {
                            "assignment_status": "UNASSIGNED", "intended_entry_count": None,
                            "technical_strategy": strategy, "intended_profile": "unspecified",
                            "warning": "User entry count does not establish contest field size."}
                        params["effective_policy_contract"] = small_field_report["policy_contract"]
                        params["portfolio_constraints"] = small_field_report["selected_portfolio"]["constraints"]
                        if len(selected) != num_lineups:
                            raise ValueError(
                                f"Global selection found {len(selected)}/{num_lineups} lineups "
                                f"from {len(gpp_result.lineups)} legal candidates"
                            )
                        gpp_result.lineups = selected
                    lineup_results = [
                        [self._gpp_player_to_dict(p) for p in lineup] for lineup in gpp_result.lineups
                    ]
                    if params.get("analyst_packet_sha256"):
                        attributions = {}
                        for step in gpp_result.selection_trace:
                            for candidate in (step.get("football_analyst") or {}).get("shadow", []):
                                key = tuple(sorted(row["player_master_id"] for row in candidate["roster"]))
                                attributions.setdefault(key, set()).update(candidate["thesis_ids"])
                        for lineup in lineup_results:
                            key = tuple(sorted(str(row["player_id"]) for row in lineup))
                            if key in attributions:
                                lineup[0]["analyst_thesis_ids"] = sorted(attributions[key])
                                lineup[0]["analyst_packet_sha256"] = params["analyst_packet_sha256"]
                                lineup[0]["analyst_construction_only"] = True
                    from .classic_primary_game import primary_game_exposure
                    effective_game_cap = (params.get("portfolio_constraints") or {}).get("canonical_game_cap") if small_field else primary_game_cap
                    achieved_games = primary_game_exposure(gpp_result.lineups)
                    params["primary_game_constraint"] = {
                        "requested": params.get("max_lineups_per_primary_game"),
                        "effective": effective_game_cap,
                        "source": "request" if "max_lineups_per_primary_game" in params else "legacy_portfolio_request" if effective_game_cap is not None else "strategy_default_no_limit",
                        "achieved_game_exposure": achieved_games,
                        "validation": "verified" if effective_game_cap is None or max(achieved_games.values(), default=0) <= effective_game_cap else "failed",
                    }
                    if small_field:
                        for lineup in lineup_results:
                            complete = all(player["ownership"] is not None for player in lineup)
                            for player in lineup:
                                player["ownership_status"] = "available" if complete else "unavailable"
                                if not complete or player["optimal_lineup_probability"] is None:
                                    player["leverage"] = None
                    if small_field_report and lineup_results:
                        lineup_results[0][0]["classic_small_field_report"] = small_field_report
                        urls = params.get("contest_urls") or []
                        if urls:
                            from .classic_small_field import contest_reporting_snapshot
                            small_field_report["contest"] = contest_reporting_snapshot(
                                urls, manual=params.get("manual_contest_metadata"),
                            )
                    for lineup, comparison in zip(lineup_results, gpp_result.control_comparisons):
                        lineup[0]["lineup_control_comparison"] = comparison
                    if strategy == CLASSIC_LARGE_GPP_STRATEGY_ID:
                        by_roster = {frozenset(step["player_ids"]): step["objective_components"]
                            for step in gpp_result.selection_trace if step.get("objective_components")}
                        for lineup in lineup_results:
                            components = by_roster.get(frozenset(str(p["player_id"]) for p in lineup))
                            if components is not None:
                                lineup[0]["lineup_objective_components"] = components
                    site_ids = {str(row["player_id"]): row.get("dk_player_id")
                                for row in pool.to_dict("records")}
                    for lineup in lineup_results:
                        for player in lineup:
                            player["dk_player_id"] = site_ids.get(str(player["player_id"]))
                    status = "completed" if small_field and len(lineup_results) == num_lineups else gpp_result.status
                    uniqueness_overlap = gpp_result.config.uniqueness_overlap
                    correlation_objective_multiplier = (
                        gpp_result.config.objective_weights.correlation
                        * gpp_result.config.correlation_bonus
                    )
                    params["strategy_runtime"]["lineup_correlation"][
                        "objective_multiplier"
                    ] = correlation_objective_multiplier
                    message = (
                        f"{gpp_result.message}; strategy={strategy}; "
                        f"validation=slate-aware-config"
                    )
                    if small_field_report:
                        message += (
                            f"; {small_field_report['candidate_count']}/{candidate_target} legal candidates; "
                            f"globally selected {len(lineup_results)}"
                        )
                    stack_policy = {
                        "policy_id": (
                            "classic_large_gpp_flexible_stacks_v1"
                            if strategy in {CLASSIC_LARGE_GPP_STRATEGY_ID, CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID}
                            else "classic_gpp_slate_aware_stack_v1"
                        ),
                        "contest_format": "classic",
                        "objective": "gpp",
                        "enabled": True,
                        "stack_min": gpp_result.config.stack_rules.min_pass_catchers,
                        "stack_max": None,
                        "bringback": (
                            gpp_result.config.stack_rules.min_bring_backs > 0
                        ),
                        "include_rb_in_stack": True,
                        "bringback_positions": ["RB", "WR", "TE"],
                        "max_from_team": gpp_result.config.stack_rules.max_from_team,
                        "evidence_status": "strategy_runtime",
                        "description": (
                            "Flexible portfolio stack policy resolved by the selected "
                            "GPP strategy."
                        ),
                        "source": "optimizer_strategy",
                    }
                    stack_cfg = dict(stack_policy)
                    params["stack_policy_id"] = stack_policy["policy_id"]
                    params["stack_policy"] = stack_policy
                    params.setdefault("strategy_runtime", {}).update({
                        "iterations": gpp_result.iterations,
                        "analysis": asdict(gpp_result.analysis),
                        "config": asdict(gpp_result.config),
                        "portfolio": (
                            {"candidate_pool_portfolio": asdict(gpp_result.portfolio),
                             "selected_lineup_ranks": small_field_report["selected_ranks"]}
                            if small_field_report else asdict(gpp_result.portfolio)
                        ),
                    })
                    if small_field_report:
                        params["strategy_runtime"]["classic_small_field"] = small_field_report
                        params["strategy_runtime"]["classic_solver"] = {
                            "backend": solver_backend,
                            "requested_candidate_workers": params.get("classic_candidate_workers", 1),
                            "candidate_workers": discovery_workers,
                            "parallel_fallback_reason": parallel_fallback_reason,
                            "correlation_terms_cached": True,
                        }
                    if strategy == CLASSIC_LARGE_GPP_STRATEGY_ID:
                        from .classic_large_gpp_readiness import assess_large_gpp_saved_inputs, saved_salary_identity
                        from .runtime_code import LOADED
                        params["execution_runtime"] = LOADED
                        snapshot = params["strategy_runtime"]["classic_run_input_snapshot"]
                        try:
                            params["entry_readiness"] = assess_large_gpp_saved_inputs(
                                contract=params["effective_strategy_contract"], snapshot=snapshot,
                                lineups=lineup_results,
                                salary_identity=saved_salary_identity(self.engine, snapshot["payload"]["final_solver_rows"]),
                            )
                        except Exception as readiness_error:  # Reporting must not change selection or lose legal results.
                            params["entry_readiness"] = {
                                "status": "DEVELOPMENT_PREVIEW", "entry_ready": False,
                                "checks": {"Readiness evaluation": {"status": "UNAVAILABLE", "reason": str(readiness_error)}},
                                "reasons": [str(readiness_error)],
                                "assessed_at": datetime.now(timezone.utc).isoformat(),
                                "scope": "saved decision; readiness evaluation unavailable",
                            }
                        if live_classic and not allow_incomplete_evidence:
                            from .classic_data_readiness import annotate_entry_report
                            params["entry_readiness"] = annotate_entry_report(params["entry_readiness"], params["data_readiness"])
                except Exception as exc:  # noqa: BLE001
                    lineup_results = []
                    status = "failed"
                    message = f"{strategy} failed: {exc}"
            elif single_entry or three_max or small_max:
                from .showdown_single_entry import select_single_entry_lineups
                from .showdown_contests import fetch_contests, select_contests

                contest_metadata = params.get("contest_metadata")
                contest_selection_report = None
                if three_max or small_max:
                    from .showdown_three_max import (
                        select_generic_small_max_lineups, select_small_max_lineups, select_three_max_lineups,
                        validate_small_max_contest, validate_three_max_contest,
                    )
                    urls = params.get("contest_urls") or []
                    if urls or three_max:
                        if len(urls) != 1:
                            raise ValueError("Small-max requires exactly one DraftKings contest URL when a contest is supplied")
                        available = fetch_contests(urls, manual=params.get("manual_contest_metadata"))
                        from .saved_contests import record_saved_observations
                        record_saved_observations(self.engine, available, reason="optimizer")
                        contest_metadata = [validate_three_max_contest(available[0]) if three_max else validate_small_max_contest(available[0])]
                    else:
                        contest_metadata = None
                        try:
                            generic_entry_limit = int(params.get("small_max_maximum_entries", 5))
                        except (TypeError, ValueError) as exc:
                            raise ValueError("Generic small-max entry limit must be 2 through 5") from exc
                        if not 2 <= generic_entry_limit <= 5:
                            raise ValueError("Generic small-max entry limit must be 2 through 5")
                elif strategy == SHOWDOWN_SINGLE_ENTRY_PORTFOLIO_STRATEGY_ID and params.get("contest_urls"):
                    available = fetch_contests(
                        params["contest_urls"], manual=params.get("manual_contest_metadata"),
                    )
                    from .saved_contests import record_saved_observations, recover_saved_contest_snapshots
                    record_saved_observations(self.engine, available, reason="optimizer")
                    available = recover_saved_contest_snapshots(
                        self.engine, available, season=season, week=week, slate=slate,
                    )
                    draft_groups = {row.get("draft_group_id") for row in available if row.get("draft_group_id") is not None}
                    if len(draft_groups) > 1:
                        raise ValueError("All pasted contests must belong to the same DraftKings draft group")
                    contest_metadata, contest_selection_report = select_contests(
                        available, mode=params.get("contest_selection", "auto"),
                        budget=params.get("maximum_total_entry_budget"),
                        maximum=params.get("maximum_contests_to_enter"),
                    )
                    snapshots = [row for row in available if row.get("source") == "saved_snapshot"]
                    if snapshots:
                        contest_selection_report["snapshot_fallbacks"] = [
                            {"contest_id": row["contest_id"], "observed_at": row["snapshot_observed_at"]}
                            for row in snapshots
                        ]
                        contest_selection_report["note"] += (
                            " Saved contest snapshots supplied unavailable live facts; "
                            "their entry counts were not used for near-lock overlay."
                        )
                num_contests = (
                    int(contest_metadata[0]["maximum_entries"]) if (three_max or small_max) and contest_metadata else
                    generic_entry_limit if small_max else 1 if strategy == SHOWDOWN_SINGLE_ENTRY_GPP_STRATEGY_ID
                    else len(contest_metadata) if contest_metadata is not None
                    else int(params.get("num_single_entry_contests", 3))
                )
                if num_contests < 1 or num_contests > 50:
                    raise ValueError("Single-entry portfolio must contain 1 to 50 contests")
                params["num_single_entry_contests"] = num_contests
                params["num_lineups"] = num_contests
                num_lineups = num_contests
                candidates = []
                excluded = []
                candidate_limit = max(30 if three_max or small_max else 10, min(50, int(params.get("single_entry_candidate_pool_size", 40 if three_max or small_max else 30))))
                broad_count = max(10, int(candidate_limit * 0.6))
                forced_count = (candidate_limit - broad_count) // 2
                forced_captains = [
                    str(player_id) for player_id in pool.sort_values(score_col, ascending=False)["player_id"]
                    if str(player_id) not in flex_only_ids
                ]
                teams = sorted(str(team) for team in pool["player_team"].dropna().unique())
                script_targets = [
                    {"script_id": f"single_entry_{kind}_{team}", "kind": kind, "team": team}
                    for kind in ("run_control", "pass_led", "contrarian")
                    for team in teams
                ]
                for candidate_index in range(candidate_limit):
                    forced_captain = requested_captain_id or (
                        forced_captains[candidate_index - broad_count]
                        if broad_count <= candidate_index < broad_count + forced_count
                        and candidate_index - broad_count < len(forced_captains)
                        else None
                    )
                    script_index = candidate_index - broad_count - forced_count
                    script_target = (
                        script_targets[script_index]
                        if script_index >= 0 and script_index < len(script_targets)
                        else None
                    )
                    lineup = self._solve_lineup(
                        pool, score_col=score_col, exclude_signatures=excluded,
                        enforce_single_te=enforce_single_te,
                        contest_type=contest_type, stack_params=stack_cfg,
                        locked_player_ids=locked_ids, flex_only_player_ids=flex_only_ids,
                        rule_profile=rule_profile, include_control_comparison=False,
                        locked_captain_player_id=forced_captain,
                        portfolio_script=script_target,
                    )
                    if not lineup:
                        if forced_captain or script_target:
                            continue
                        break
                    excluded.append([(str(row["player_id"]), str(row["roster_position"])) for row in lineup])
                    correlation = score_lineup_correlations(lineup, profile=rule_profile)
                    lineup[0]["lineup_correlation_summary"] = _saturated_showdown_correlation_summary(lineup, correlation)
                    candidates.append(lineup)
                if params.get("analyst_packet_sha256"):
                    from .analyst_generation import generate_showdown, merge_showdown
                    analyst_candidates, analyst_report = generate_showdown(
                        self, pool, params=params, season=season, week=week, slate=slate,
                        solve_kwargs={"score_col": score_col, "enforce_single_te": enforce_single_te,
                            "avoid_dst_opponents": avoid_dst_opponents, "contest_type": contest_type, "stack_params": stack_cfg,
                            "locked_player_ids": locked_ids, "flex_only_player_ids": flex_only_ids,
                            "rule_profile": rule_profile, "locked_captain_player_id": requested_captain_id,
                            "include_control_comparison": False},
                    )
                    for lineup in analyst_candidates:
                        correlation = score_lineup_correlations(lineup, profile=rule_profile)
                        lineup[0]["lineup_correlation_summary"] = _saturated_showdown_correlation_summary(lineup, correlation)
                    baseline_signatures = {tuple(sorted((str(row["player_id"]), row["roster_position"]) for row in lineup)) for lineup in candidates}
                    analyst_signatures = {tuple(sorted((str(row["player_id"]), row["roster_position"]) for row in lineup)) for lineup in analyst_candidates}
                    candidates = merge_showdown(candidates, analyst_candidates)
                    analyst_report["comparison"].update(baseline_distinct=len(baseline_signatures), shadow_new_distinct=len(analyst_signatures-baseline_signatures))
                    analyst_report["merged_distinct_candidate_count"] = len(candidates)
                    params.setdefault("strategy_runtime", {})["football_analyst"] = analyst_report
                if three_max or small_max:
                    exposure_rates = {
                        "captain": params.get("captain_max_exposure", 1.0),
                        "core": params.get("core_player_max_exposure", 1.0),
                        "starting_qb": params.get("starting_qb_max_exposure", 1.0),
                        "cheap_punt": params.get("cheap_punt_max_exposure", 1.0),
                    }
                    selection_kwargs = {
                        "entries_to_use": params.get("entries_to_use", "auto"),
                        "exposure_rates": exposure_rates,
                        "weights": params.get("single_entry_objective_weights"),
                    }
                    if small_max and contest_metadata is None:
                        lineup_results, three_max_report = select_generic_small_max_lineups(
                            candidates, maximum_entries=num_contests, **selection_kwargs,
                        )
                    else:
                        lineup_results, three_max_report = (select_three_max_lineups if three_max else select_small_max_lineups)(
                            candidates, contest=contest_metadata[0], **selection_kwargs,
                        )
                    three_max_report["enforce_single_te"] = enforce_single_te
                    params.setdefault("strategy_runtime", {})["three_max" if three_max else "small_max"] = three_max_report
                    status = "completed" if lineup_results else "failed"
                    message = f"Selected {len(lineup_results)} unique small-max lineup(s) from {len(candidates)} candidates"
                else:
                    lineup_results, single_entry_report = select_single_entry_lineups(
                    candidates, num_contests=num_contests,
                    weights=params.get("single_entry_objective_weights"),
                    contest_metadata=contest_metadata,
                    contest_proxy=(next((row for row in contest_selection_report["count_comparisons"]
                                         if row["contest_count"] == num_contests), None)
                                   if contest_selection_report else None),
                )
                    if contest_selection_report:
                        single_entry_report["contest_selection"] = contest_selection_report
                    single_entry_report["enforce_single_te"] = enforce_single_te
                    params.setdefault("strategy_runtime", {})["single_entry"] = single_entry_report
                    status = "completed" if lineup_results else "failed"
                    message = f"Selected {len(lineup_results)} single-entry contest lineup(s) from {len(candidates)} candidates"
            else:
                lineup_results, status, message = _run_baseline()
                message += f"; strategy={strategy}"

            if (
                lineup_results
                and contest_format == "classic"
                and (
                    objective == "gpp"
                    or strategy == CLASSIC_HEAD_TO_HEAD_STRATEGY_ID
                    or single_lineup
                )
            ):
                ok, reason = self._validate_classic_lineups(
                    lineup_results,
                    requested_lineups=num_lineups,
                    max_exposure=max_exposure,
                    enforce_single_te=enforce_single_te,
                    avoid_dst_opponents=avoid_dst_opponents,
                    uniqueness_overlap=uniqueness_overlap,
                    locked_player_ids=locked_ids,
                    excluded_player_ids=exclude_ids,
                    excluded_opponent_teams=excluded_opponent_teams,
                    minimum_player_salary=params.get("minimum_player_salary"),
                    season_ppg_eligible_ids=season_ppg_eligible_ids,
                    favored_team_positions=favored_team_positions,
                    minimum_qb_salary=params.get("minimum_qb_salary"),
                    minimum_rb_salary=params.get("minimum_rb_salary"),
                )
                if not ok:
                    status = "failed"
                    message = f"{strategy} lineup validation failed: {reason}"
                    lineup_results = []

            if lineup_results and contest_format == "showdown":
                for lineup in lineup_results:
                    control_comparison = lineup[0].pop("lineup_control_comparison", None)
                    if portfolio_v3 and isinstance(control_comparison, dict):
                        control_comparison["rule_contributions"] = [
                            row for row in control_comparison.get("rule_contributions", [])
                            if not any(rule_id in str(row.get("rule_id") or "") for rule_id in _SATURATED_SHOWDOWN_RULE_IDS)
                            and "showdown_fragile_punt" not in str(row.get("rule_id") or "")
                        ]
                        control_comparison["correlation_policy"] = (
                            "qb_stack_diminishing_60_30_10_bringback_once_v1"
                        )
                    lineup.sort(
                        key=lambda row: (
                            0
                            if str(row.get("roster_position") or "").upper()
                            == "CPT"
                            else 1,
                            str(row.get("player_id") or row.get("dk_player_id") or ""),
                        )
                    )
                    if control_comparison is not None:
                        lineup[0]["lineup_control_comparison"] = control_comparison
                    if small_max or three_max:
                        place_small_max_metadata_on_captain(lineup)
                    if portfolio_v3 or single_entry or three_max or small_max:
                        actual_script = classify_showdown_game_script(lineup)
                        game_environment = summarize_showdown_game_environment(lineup)
                        for row in lineup:
                            row["portfolio_game_script"] = dict(actual_script)
                            row["showdown_game_environment"] = dict(game_environment)
                    for slot_index, row in enumerate(lineup):
                        row["lineup_slot_index"] = slot_index
                        row["roster_position"] = str(
                            row.get("roster_position") or ""
                        ).upper()
                if portfolio_v3:
                    exposure_rates = {
                        "captain": float(params.get("captain_max_exposure", 0.60)),
                        "core": float(params.get("core_player_max_exposure", 0.80)),
                        "starting_qb": float(params.get("starting_qb_max_exposure", 1.00)),
                        "cheap_punt": float(params.get("cheap_punt_max_exposure", 0.40)),
                    }
                    exposure_report = summarize_showdown_portfolio_exposure(
                        lineup_results,
                        requested_lineups=num_lineups,
                        exposure_rates=exposure_rates,
                    )
                    chalk_metrics = add_showdown_lineup_chalk_metrics(lineup_results)
                    strategy_runtime = params.setdefault("strategy_runtime", {})
                    portfolio_runtime = strategy_runtime.setdefault(
                        "showdown_portfolio_policy", {}
                    )
                    portfolio_runtime["exposure_report"] = exposure_report
                    portfolio_runtime["lineup_duplication_risk"] = chalk_metrics
                    if lineup_results and lineup_results[0]:
                        lineup_results[0][0]["portfolio_exposure_report"] = exposure_report
                        underfill = portfolio_runtime.get("underfill_diagnostics")
                        if isinstance(underfill, dict) and underfill.get("reason_counts"):
                            lineup_results[0][0]["portfolio_underfill_diagnostics"] = dict(
                                underfill
                            )
                        captain_diversity = portfolio_runtime.get("captain_diversification")
                        if isinstance(captain_diversity, dict) and captain_diversity.get("enabled"):
                            lineup_results[0][0]["captain_diversification_report"] = dict(
                                captain_diversity
                            )
                ok, reason = self._validate_showdown_lineups(
                    lineup_results,
                    requested_lineups=num_lineups,
                    max_exposure=(1.0 if portfolio_v3 or single_entry or three_max or small_max else max_exposure),
                    enforce_single_te=enforce_single_te,
                    require_qb_captain_receiver=require_qb_captain_receiver,
                    portfolio_policy=portfolio_v3 or single_entry or three_max or small_max or single_lineup,
                    strategy_stack_rules=not shared_world_mode,
                    locked_players_override_exposure=single_lineup,
                    allow_duplicate_lineups=single_entry,
                    portfolio_exposure_rates=({"captain": params.get("captain_max_exposure", 1.0),
                        "core": params.get("core_player_max_exposure", 1.0),
                        "starting_qb": params.get("starting_qb_max_exposure", 1.0),
                        "cheap_punt": params.get("cheap_punt_max_exposure", 1.0)} if single_lineup else
                        exposure_rates if portfolio_v3 or three_max or small_max else None),
                    locked_player_ids=locked_ids,
                    flex_only_player_ids=flex_only_ids,
                    excluded_opponent_teams=excluded_opponent_teams,
                    no_qb_captain=params.get("no_qb_captain", False),
                    no_two_qbs=params.get("no_two_qbs", False),
                    no_qbs=params.get("no_qbs", False),
                    captain_positions=captain_positions,
                    captain_position_exception_ids=named_preference_ids(params, "captain_position_exception_ids"),
                    captain_shortlist_ids={
                        row["player_id"] for row in params["strategy_runtime"]["showdown_captain_shortlist"]["shortlist"]
                    },
                    required_team_leader_ids=set(team_leader_preference["required_player_ids"]),
                    minimum_player_salary=params.get("minimum_player_salary"),
                    max_players_per_team=params["max_players_per_team"],
                )
                if not ok:
                    params.setdefault("strategy_runtime", {})["validation"] = {
                        "status": "failed",
                        "rejection_reason": reason,
                        "optimizer_rule_ids": [
                            str(rule["rule_id"]) for rule in optimizer_rules
                        ],
                        "qb_captain_same_team_wr_te": (
                            require_qb_captain_receiver
                        ),
                        "flex_only_player_ids": sorted(flex_only_ids),
                    }
                    status = "failed"
                    message = f"{strategy} lineup validation failed: {reason}"
                    lineup_results = []
                else:
                    strategy_runtime = params.setdefault("strategy_runtime", {})
                    strategy_runtime["validation"] = {
                        "status": "passed",
                        "lineup_count": len(lineup_results),
                        "salary_cap": SALARY_CAP,
                        "requested_lineups": num_lineups,
                        "max_exposure": max_exposure,
                        "captain_slots": 1,
                        "flex_slots": 5,
                        "enforce_single_te": enforce_single_te,
                        "max_players_per_team": params["max_players_per_team"],
                        "optimizer_rule_ids": [
                            str(rule["rule_id"]) for rule in optimizer_rules
                        ],
                        "qb_captain_same_team_wr_te": (
                            require_qb_captain_receiver
                        ),
                        "flex_only_player_ids": sorted(flex_only_ids),
                        "no_qb_captain": params.get("no_qb_captain", False),
                        "no_two_qbs": params.get("no_two_qbs", False),
                        "no_qbs": params.get("no_qbs", False),
                        "captain_positions": captain_positions,
                        "captain_position_exception_ids": sorted(named_preference_ids(params, "captain_position_exception_ids")),
                    }
                    if portfolio_v3 and portfolio_contest:
                        contest_report = {
                            key: portfolio_contest.get(key) for key in (
                                "contest_id", "url", "name", "slate", "entry_fee", "capacity",
                                "current_entries", "prize_pool", "paid_places", "maximum_entries",
                                "lock_time", "guaranteed", "observed_at", "source", "payout_ladder",
                                "economics",
                            )
                        }
                        contest_report["requested_entries"] = 5
                        contest_report["generated_entries"] = len(lineup_results)
                        contest_report["requested_entry_cost"] = 5 * float(portfolio_contest["entry_fee"])
                        contest_report["generated_entry_cost"] = len(lineup_results) * float(portfolio_contest["entry_fee"])
                        lineup_results[0][0]["portfolio_contest_report"] = contest_report
                        strategy_runtime["showdown_portfolio_policy"]["contest"] = contest_report
                    message += "; showdown lineup validation=passed"

            # Validate stacks/bring-backs for any lineups produced
            if lineup_results:
                ok, reason = self._lineups_satisfy_stack(lineup_results, stack_cfg, contest_type)
                if not ok:
                    status = "failed"
                    message = (
                        f"{strategy} stack/bring-back validation failed: {reason}"
                    )
                    lineup_results = []

            if status == "completed" and lineup_results:
                if contest_format == "showdown":
                    for lineup in lineup_results:
                        lineup[0]["showdown_qb_preferences"] = showdown_qb_preference_report(params, qb_player_ids=qb_player_ids)
                        lineup[0]["showdown_team_constraints"] = team_constraint_report(params)
                        lineup[0]["showdown_captain_preferences"] = captain_preference_report(params)
                        lineup[0]["showdown_captain_shortlist"] = params["strategy_runtime"]["showdown_captain_shortlist"]
                if contest_format == "classic":
                    strategy_runtime = params.setdefault("strategy_runtime", {})
                    strategy_runtime["validation"] = {
                        "status": "passed",
                        "lineup_count": len(lineup_results),
                        "salary_cap": SALARY_CAP,
                        "team_limit": TEAM_LIMIT,
                        "requested_lineups": num_lineups,
                        "max_exposure": max_exposure,
                        "enforce_single_te": enforce_single_te,
                        "avoid_dst_opponents": avoid_dst_opponents,
                        "uniqueness_overlap": uniqueness_overlap,
                    }
                    message += "; lineup validation=passed"
                if long_shot_mode:
                    ownership_values = [
                        row.get("ownership")
                        for row in lineup_results[0]
                        if row.get("ownership") is not None
                        and pd.notna(row.get("ownership"))
                    ]
                    ownership_status = (
                        "available"
                        if len(ownership_values) == len(lineup_results[0])
                        else "partial"
                        if ownership_values
                        else "unavailable"
                    )
                    config_weights = (
                        params.get("strategy_runtime", {})
                        .get("config", {})
                        .get("objective_weights", {})
                    )
                    long_shot_report = {
                        "enabled": True,
                        "lineup_count": 1,
                        "ownership_status": ownership_status,
                        "ownership_sum": (
                            float(sum(float(value) for value in ownership_values))
                            if ownership_status == "available" else None
                        ),
                        "method": (
                            "showdown_role_ownership_penalty_and_contrarian_script"
                            if contest_format == "showdown" and ownership_status == "available"
                            else "classic_low_ownership_leverage_objective"
                            if contest_format == "classic" and ownership_status == "available"
                            else "structural_contrarian_only"
                            if contest_format == "showdown"
                            else "contrarian_evidence_unavailable"
                        ),
                        "objective_weights": config_weights,
                        "showdown_ownership_weight": (
                            float(stack_cfg.get("ownership_weight", 0.0))
                            if contest_format == "showdown" else None
                        ),
                        "note": (
                            "Football projections are unchanged. The lineup is selected with a stronger low-ownership objective."
                            if ownership_status == "available"
                            else "Ownership is incomplete, so contrarian confidence is unavailable; football projections remain unchanged and missing ownership is not scored as zero."
                        ),
                    }
                    for row in lineup_results[0]:
                        row["lineup_variant"] = "long_shot"
                        row["long_shot_report"] = dict(long_shot_report)
                    params.setdefault("strategy_runtime", {})["long_shot"] = dict(long_shot_report)
                    message += "; standalone long-shot lineup generated"
                for lineup in lineup_results:
                    lineup[0]["lineup_controls"] = {
                        "enforce_single_te": enforce_single_te,
                    }
                    stack_summary = (
                        summarize_classic_stack(lineup)
                        if contest_format == "classic"
                        else {}
                    )
                    ceiling_summary = summarize_individual_ceiling_sum(lineup)
                    correlation_summary = score_lineup_correlations(
                        lineup,
                        profile=rule_profile,
                        objective_multiplier=correlation_objective_multiplier,
                    )
                    if (portfolio_v3 or single_entry or three_max or small_max) and contest_format == "showdown":
                        correlation_summary = _saturated_showdown_correlation_summary(
                            lineup, correlation_summary
                        )
                        script = lineup[0].get("portfolio_game_script")
                        if isinstance(script, dict):
                            correlation_summary["implied_game_script"] = {
                                "script_id": script.get("script_id"),
                                "label": script.get("label"),
                                "evidence": {
                                    "classification": "actual_lineup_construction_v1",
                                    **script,
                                    "portfolio_target": lineup[0].get("portfolio_script_target"),
                                },
                            }
                    context_rule_counts: dict[str, int] = {}
                    for lineup_row in lineup:
                        evaluation = lineup_row.get(
                            "optimizer_context_rule_evaluation"
                        )
                        if not isinstance(evaluation, dict):
                            continue
                        for trigger in evaluation.get("triggered_rules") or []:
                            reason_code = str(trigger.get("reason_code") or "")
                            if reason_code:
                                context_rule_counts[reason_code] = (
                                    context_rule_counts.get(reason_code, 0) + 1
                                )
                    context_summary = {
                        "library_id": context_result.summary["library_id"],
                        "library_version": context_result.summary[
                            "library_version"
                        ],
                        "total_adjustment": sum(
                            _safe_float(
                                lineup_row.get("optimizer_context_adjustment")
                            )
                            * (
                                1.5
                                if str(
                                    lineup_row.get("roster_position") or ""
                                ).upper()
                                == "CPT"
                                else 1.0
                            )
                            for lineup_row in lineup
                        ),
                        "trigger_counts": dict(sorted(context_rule_counts.items())),
                    }
                    for row in lineup:
                        row["lineup_stack_policy"] = dict(stack_policy)
                        if stack_summary:
                            row["lineup_stack_summary"] = stack_summary
                        row["lineup_optimizer_strategy"] = dict(strategy_config)
                        row["lineup_optimizer_rules"] = [
                            dict(rule) for rule in optimizer_rules
                        ]
                        row["lineup_context_summary"] = context_summary
                        row["lineup_correlation_summary"] = correlation_summary
                        row["lineup_ceiling_summary"] = ceiling_summary
                if strategy == CLASSIC_HEAD_TO_HEAD_STRATEGY_ID:
                    for lineup in lineup_results:
                        lineup_summary = summarize_head_to_head_lineup(lineup)
                        for row in lineup:
                            row["lineup_h2h_summary"] = lineup_summary
                elif contest_format == "classic" and objective == "cash" and not single_lineup:
                    missing_projection_count = 0
                    for lineup in lineup_results:
                        lineup_summary = summarize_classic_cash_lineup(lineup)
                        missing_projection_count += len(
                            lineup_summary.get("missing_projection_players", [])
                        )
                        for row in lineup:
                            row["lineup_cash_summary"] = lineup_summary
                    if missing_projection_count:
                        message += (
                            f"; {missing_projection_count} selected player input(s) "
                            "have no projection evidence"
                        )
                if single_lineup and contest_format == "classic":
                    from .classic_data_readiness import annotate_entry_report
                    readiness = params.get("data_readiness") or {}
                    if readiness.get("required_sources"):
                        params["entry_readiness"] = annotate_entry_report(
                            {"checks": {"Legal single lineup": {"status": "PASS", "reason": "One roster passed independent final validation."}}}, readiness)
                self._attach_symbolic_explanations(
                    lineups=lineup_results,
                    season=season,
                    week=week,
                    slate=slate,
                )

        final_pool_ids = (
            set(pool["player_id"].astype(str))
            if not pool.empty and "player_id" in pool
            else set()
        )
        if params.get("no_qbs", False):
            final_pool_ids.difference_update(qb_player_ids)
            for player_id in qb_player_ids:
                exclusion_reasons.setdefault(player_id, []).append("user_no_qbs")
                exclusion_details.setdefault(player_id, []).append({
                    "reason_code": "user_no_qbs", "reason": "No QBs in the lineup",
                    "category": ExclusionCategory.USER.value, "scope": "lineup",
                })
        player_pool_rows: list[dict] = []
        if params.get("analyst_packet_sha256"):
            analyst_runtime = params.setdefault("strategy_runtime", {}).setdefault("football_analyst", {
                "status": "unsupported_strategy", "reasons": ["This strategy does not yet accept Analyst constructions"],
                "mode": "ANALYST_CONSTRUCTION", "packet_sha256": params["analyst_packet_sha256"],
            })
            if params.get("analyst_handoff_applied"):
                analyst_runtime["prepared_research"] = params["analyst_handoff_applied"]
                analyst_runtime["preparation_compatibility"] = (params.get("prepared_input_evidence") or {}).get("analyst_handoff")
            from .analyst_generation import summarize_report
            if not merged_analyst:
                summarize_report(analyst_runtime, lineup_results)
                from .analyst_generation import annotate_original_construction_comparison
                annotate_original_construction_comparison(analyst_runtime, params=params, lineups=lineup_results,
                    coverage=params.get("strategy_runtime", {}).get("showdown_captain_coverage"))
        role_audit = params.get("strategy_runtime", {}).get("current_slate_role_availability_audit", {})
        role_source_rows = {str(r["player_id"]): r for r in initial_pool.to_dict("records")}
        for assessment in role_audit.get("players", []):
            pid = assessment["player_id"]
            source = role_source_rows.get(pid, {})
            assessment.update(optimizer_eligible=pid in final_pool_ids,
                projection=_json_safe(source.get("projection")), p90=_json_safe(source.get("p90")),
                projection_change=_json_safe(source.get("projection_after_scenario")),
                projection_before=_json_safe(source.get("projection_before_scenario")))
        unresolved_safety_audits = [
            row
            for row in safety_result.audit_rows
            if not str(row.get("player_id") or "").strip()
        ]
        if not initial_pool.empty and "player_id" in initial_pool:
            for row in initial_pool.drop_duplicates("player_id").to_dict(
                orient="records"
            ):
                player_id = _safe_text(row.get("player_id"))
                safety_audit = safety_audit_by_player.get(player_id, {})
                context_audit = context_audit_by_player.get(player_id, {})
                if not player_id and unresolved_safety_audits:
                    safety_audit = unresolved_safety_audits.pop(0)
                safety_context = safety_audit.get("context") or {}
                context_observed_at = _json_safe(
                    row.get("pregame_context_observed_at")
                )
                role_label = _json_safe(row.get("pregame_role_label"))
                effective_role_label = (
                    role_label
                    if role_label is not None
                    else _json_safe(safety_context.get("role_label"))
                )
                injury_status = _json_safe(row.get("pregame_injury_status"))
                projection = _safe_float(
                    row.get("projection", row.get("predicted_mean"))
                )
                p90 = _safe_float(row.get("p90", row.get("predicted_p90")))
                player_exclusion_details = exclusion_details.get(player_id, [])
                user_preference_exclusions = [
                    detail
                    for detail in player_exclusion_details
                    if detail.get("category") == ExclusionCategory.USER.value
                ]
                player_pool_rows.append(
                    {
                        "player_id": player_id,
                        "player_name": _safe_text(
                            row.get("player_display_name"),
                            row.get("player_name"),
                            row.get("name"),
                            player_id,
                        ),
                        "position": _safe_text(row.get("position")),
                        "workload_evidence": build_workload_evidence(
                            row, projection_run_id=projection_run_id, cutoff=data_cutoff_at or now
                        ),
                        **{key: _json_safe(row.get(key)) for key in (
                            "role_availability", "expected_depth_role", "role_starter_evidence",
                            "role_change", "role_optimizer_eligible", "role_confidence",
                            "role_resolution_warning", "role_rostered", "role_active")},
                        "kicker_role": _json_safe(row.get("kicker_role")),
                        "kicker_role_eligible": _json_safe(row.get("kicker_role_eligible")),
                        "kicker_role_reason": _json_safe(row.get("kicker_role_reason")),
                        "kicker_role_evidence": _json_safe(row.get("kicker_role_evidence")),
                        "team": _safe_text(
                            row.get("player_team"), row.get("team")
                        ),
                        "opponent_team": _safe_text(row.get("opponent_team")),
                        "salary": int(_safe_float(row.get("salary"))),
                        "projection": projection,
                        "p90": p90,
                        "optimizer_context_adjustment": (
                            _safe_float(context_audit.get("adjustment"))
                            if context_audit
                            else None
                        ),
                        "optimizer_context_reason_codes": list(
                            context_audit.get("reason_codes") or []
                        ),
                        "player_status": _json_safe(row.get("player_status")),
                        "questionable_eligibility_assumption": safety_audit.get("eligibility_assumption"),
                        "pregame_availability_probability": _json_safe(
                            row.get("pregame_availability_probability")
                        ),
                        "pregame_start_probability": _json_safe(
                            row.get("pregame_start_probability")
                        ),
                        "pregame_carry_share": _json_safe(
                            row.get("pregame_carry_share")
                        ),
                        "pregame_target_share": _json_safe(
                            row.get("pregame_target_share")
                        ),
                        "pregame_expected_snaps": _json_safe(
                            row.get("pregame_expected_snaps")
                        ),
                        "pregame_expected_routes": _json_safe(
                            row.get("pregame_expected_routes")
                        ),
                        "pregame_expected_carries": _json_safe(
                            row.get("pregame_expected_carries")
                        ),
                        "pregame_expected_targets": _json_safe(
                            row.get("pregame_expected_targets")
                        ),
                        "pregame_red_zone_share": _json_safe(
                            row.get("pregame_red_zone_share")
                        ),
                        "pregame_goal_line_share": _json_safe(
                            row.get("pregame_goal_line_share")
                        ),
                        "opportunity_diagnostic": (
                            showdown_opportunity_diagnostic(row)
                            if contest_format == "showdown"
                            and _safe_text(row.get("position")).upper() in {"RB", "WR", "TE"}
                            and _safe_float(row.get("salary")) <= 2000
                            else None
                        ),
                        "pregame_context_run_id": _json_safe(
                            row.get("pregame_context_run_id")
                        ),
                        "pregame_context_source": _json_safe(
                            row.get("pregame_context_source")
                        ),
                        "pregame_context_observed_at": _json_safe(
                            context_observed_at
                            if context_observed_at is not None
                            else safety_context.get("observed_at")
                        ),
                        "pregame_role_label": _json_safe(
                            effective_role_label
                        ),
                        "pregame_injury_status": _json_safe(
                            injury_status
                            if injury_status is not None
                            else safety_context.get("injury_status")
                        ),
                        "official_availability_status": _json_safe(
                            row.get("official_availability_status")
                            or injury_status
                        ),
                        "designation_resolution": _json_safe(row.get("designation_resolution")),
                        "availability_override": _json_safe(
                            row.get("availability_override") or "default"
                        ),
                        "model_availability_used": _json_safe(
                            row.get("model_availability_used")
                        ),
                        "projection_before_scenario": _json_safe(
                            row.get("projection_before_scenario")
                        ),
                        "projection_after_scenario": _json_safe(
                            row.get("projection_after_scenario")
                        ),
                        "opportunity_redistributed": bool(
                            row.get("opportunity_redistributed", False)
                        ),
                        "identity_resolved": safety_audit.get(
                            "identity_resolved", bool(player_id)
                        ),
                        "flex_only": player_id in flex_only_ids,
                        "captain_shortlist_exclusions": next((entry["exclusions"] for entry in
                            params.get("strategy_runtime", {}).get("showdown_captain_shortlist", {}).get("exclusions", [])
                            if entry["player_id"] == player_id), []),
                        "captain_workload_assessment": next((entry.get("captain_workload") for entry in
                            [*params.get("strategy_runtime", {}).get("showdown_captain_shortlist", {}).get("shortlist", []),
                             *params.get("strategy_runtime", {}).get("showdown_captain_shortlist", {}).get("exclusions", [])]
                            if entry["player_id"] == player_id), None),
                        "captain_user_preference_exclusions": ([{
                            "reason_code": "user_no_qb_captain",
                            "reason": "No QB Captain; FLEX remains eligible",
                            "category": ExclusionCategory.USER.value,
                        }] if params.get("no_qb_captain", False) and player_id in qb_player_ids else []) + captain_preference_exclusions(params, str(row.get("position") or ""), player_id),
                        "included": player_id in final_pool_ids,
                        "optimizer_eligibility": (
                            "excluded_by_user_preference"
                            if user_preference_exclusions
                            else "eligible"
                            if player_id in final_pool_ids
                            else "excluded"
                        ),
                        "model_assessment": {
                            "projection": projection,
                            "p90": p90,
                            "role_label": effective_role_label,
                            "context_adjustment": (
                                _safe_float(context_audit.get("adjustment"))
                                if context_audit
                                else None
                            ),
                        },
                        "user_preference_exclusions": user_preference_exclusions,
                        "removal_stage": (
                            "pre_opportunity_eligibility"
                            if player_id not in raw_pool_ids
                            else "opportunity_gate"
                            if player_id not in opportunity_eligible_ids
                            else "optimizer_filter"
                            if player_id not in final_pool_ids
                            else None
                        ),
                        "exclusion_reasons": exclusion_reasons.get(player_id, []),
                        "exclusion_details": player_exclusion_details,
                        "warnings": player_warnings.get(player_id, []),
                        "rule_evaluation": safety_audit.get("rule_evaluation"),
                        "context_rule_evaluation": context_audit.get(
                            "rule_evaluation"
                        ),
                    }
                )
        removal_reason_counts: dict[str, int] = {}
        prior_eligibility_reason_counts: dict[str, int] = {}
        for row in player_pool_rows:
            if row["included"]:
                continue
            target = (
                removal_reason_counts
                if row.get("removal_stage") == "opportunity_gate"
                else prior_eligibility_reason_counts
            )
            for reason in row.get("exclusion_reasons") or ["unspecified"]:
                target[reason] = target.get(reason, 0) + 1
        params.setdefault("strategy_runtime", {})["player_pool"] = {
            "projection_run_id": projection_run_id,
            "initial_count": len(player_pool_rows),
            "source_pool_count": len(player_pool_rows),
            "raw_pool_count": len(raw_pool_ids),
            "opportunity_eligible_count": len(opportunity_eligible_ids),
            "optimizer_eligible_count": len(final_pool_ids),
            "eligible_count": len(eligible_pool_ids),
            "included_count": sum(row["included"] for row in player_pool_rows),
            "excluded_count": sum(not row["included"] for row in player_pool_rows),
            "candidate_excluded_count": len(eligible_pool_ids - final_pool_ids),
            "ineligible_count": len(
                set(row["player_id"] for row in player_pool_rows)
                - eligible_pool_ids
            ),
            "warning_player_count": sum(
                bool(row.get("warnings")) for row in player_pool_rows
            ),
            "removal_reason_counts": dict(sorted(removal_reason_counts.items())),
            "prior_eligibility_removal_reason_counts": dict(
                sorted(prior_eligibility_reason_counts.items())
            ),
            "safety": safety_result.summary,
            "context_scoring": context_result.summary,
            "rows": player_pool_rows,
        }

        if lineup_results and projection_market_audit:
            lineup_results[0][0]["projection_market_audit"] = projection_market_audit
        if lineup_results and historical_captain_report:
            report = dict(historical_captain_report)
            if report.get("slate_count") and historical_qb_pool:
                family_report = lineup_results[0][0].get("captain_family_coverage_report") or {}
                try:
                    qb_history = load_current_qb_prior_features(
                        self.engine, historical_qb_pool, season=season, week=week,
                    )
                    for qb_row in historical_qb_pool:
                        qb_row.update(qb_history.get(str(qb_row.get("player_master_id") or qb_row.get("player_id")), {}))
                    report["current_qb_feature_status"] = "prior_games_only"
                except SQLAlchemyError as exc:
                    report["current_qb_feature_status"] = f"unavailable: {type(exc).__name__}"
                report["current_qbs"] = current_qb_analysis(
                    historical_qb_pool, report, family_report.get("family_rows") or [],
                )
                report["shadow_qb_captain"] = add_shadow_qb_family_ranks(
                    family_report, report,
                    prior_strength=get_settings().showdown_captain_prior_strength,
                )
                shadow_families = {row["captain_name"]: row for row in family_report.get("family_rows") or []}
                for qb_row in report["current_qbs"]:
                    family = shadow_families.get(qb_row["qb"], {})
                    qb_row.update({key: family.get(key) for key in (
                        "shadow_qb_cpt_adjustment", "hypothetical_selector", "shadow_rank")})
                position_by_id = {
                    str(row.get("player_id")): str(row.get("position") or "").upper()
                    for row in pool.to_dict(orient="records")
                }
                position_rates = {row["label"]: row for row in report.get("positions", [])}
                qb_rates = {row["qb"]: row for row in report["current_qbs"]}
                for family in family_report.get("family_rows") or []:
                    position = position_by_id.get(str(family.get("captain_player_id")), "")
                    family["captain_position"] = position
                    family["historical_position_optimal_share"] = (
                        position_rates.get(position) or {}
                    ).get("slate_optimal_share")
                    qb_evidence = qb_rates.get(str(family.get("captain_name")), {})
                    family["captain_archetype"] = qb_evidence.get("archetype")
                    family["historical_archetype_optimal_rate"] = qb_evidence.get(
                        "historical_archetype_rate"
                    )
                    family["archetype_prior_adjustment"] = 0.0
            lineup_results[0][0]["historical_captain_optimality"] = report

        if params.get("prepared_input_job_id") and status == "completed":
            from sqlalchemy.orm import Session
            from .slate_preparation import validate_prepared_optimizer
            try:
                with Session(self.engine) as preparation_session:
                    validate_prepared_optimizer(preparation_session, {"season": season, "week": week,
                        "slate": slate, "contest_format": contest_format, "objective": objective, "strategy": strategy,
                        "projection_run_id": projection_run_id, "params": params})
            except ValueError as preparation_error:
                status = "failed"
                message = f"Prepared inputs changed or lock passed during optimization: {preparation_error}"

        if strategy in {SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID, CAPTAIN_SINGLE_LINEUP_STRATEGY_ID} and lineup_results:
            from .showdown_readiness import assess_showdown_inputs
            try:
                params["entry_readiness"] = assess_showdown_inputs(lineup_results, params, now)
            except (ValueError, TypeError) as readiness_error:
                params["entry_readiness"] = {"entry_ready": False, "status": "DEVELOPMENT_PREVIEW",
                    "checks": {"Consumed input assessment": {"status": "UNAVAILABLE", "reason": str(readiness_error)}},
                    "reasons": [str(readiness_error)]}

        # Freeze the comparison only after generation and readiness validation.
        # This does not change the GPP generator, user constraints, or candidates.
        params.pop("gpp_recommendation", None)
        if status == "completed" and objective == "gpp" and lineup_results and not highest_projection and not params.get('scenario_mode'):
            if params.get('workload_comparison') in {'learned_counts','learned_yards','scenario_first'}:
                from .workload_optimizer import learned_recommendation
                params['gpp_recommendation']=learned_recommendation(lineup_results,mode=params['workload_comparison'],
                    run_id=job_id,season=season,week=week,slate=slate,contest_format=contest_format,
                    projection_run_id=projection_run_id,data_cutoff_at=data_cutoff_at)
            else:
                from .gpp_recommendation import evaluate_candidates
                params["gpp_recommendation"] = evaluate_candidates(lineup_results,
                    run_id=job_id, season=season, week=week, slate=slate,
                    contest_format=contest_format, projection_run_id=projection_run_id,
                    data_cutoff_at=data_cutoff_at)
            if params.get("workload_comparison") and params['workload_comparison'] not in {'learned_counts','learned_yards','scenario_first'}:
                from .workload_optimizer import recommendation
                params["gpp_recommendation"] = recommendation(params["gpp_recommendation"],
                    lineup_results, params["workload_comparison"])
            elif shared_world_mode:
                from .shared_world_runtime import recommendation
                params["gpp_recommendation"] = recommendation(params["gpp_recommendation"], lineup_results,
                    params["strategy_runtime"]["football_analyst"]["shared_world_selection"])

        # Canonical references reuse the once-per-player evidence envelope. Add
        # them after selection so no solver/scoring consumer sees this contract.
        for lineup in lineup_results:
            for selected_player in lineup:
                selected_player["workload_evidence_ref"] = workload_evidence_reference(
                    selected_player.get("player_id")
                )

        job = OptimizerJob(
            job_id=job_id,
            status=status,
            created_at=now,
            updated_at=now,
            season=season,
            week=week,
            slate=slate,
            strategy=strategy,
            contest_format=contest_format,
            objective=objective,
            params=params,
            projection_run_id=projection_run_id,
            rule_run_id=rule_run_id,
            data_cutoff_at=data_cutoff_at,
            results=lineup_results if status == "completed" else None,
            message=message,
        )
        if params.get("showdown_evidence_snapshot", {}).get("non_production_override"):
            job.message = f"NON-PRODUCTION incomplete-evidence override; {job.message}"
        job.lineage_persisted = self._persist_optimizer_run(job)
        if status == "completed" and not job.lineage_persisted:
            job.status = "failed"
            job.message = "Optimizer decision snapshot and lineup lineage could not be persisted"
            job.results = None
            self._cache_job(job)
            return job

        # Persist results if found (skip captain showdown to avoid schema churn). Disabled by default to avoid
        # schema mismatches; set params.persist_results=True to enable.
        persist_results = bool(params.get("persist_results", False))
        if persist_results and lineup_results and contest_type != "captain":
            try:
                all_rows = []
                for idx, lineup in enumerate(lineup_results, start=1):
                    for row in lineup:
                        row["lineup_number"] = idx
                        all_rows.append(row)
                df = pd.DataFrame(all_rows)
                df["job_id"] = job_id
                with self.engine.begin() as connection:
                    ensure_table_columns(self.engine, "dk_optimizer", df)
                    try:
                        connection.execute(
                            text("DELETE FROM dk_optimizer WHERE job_id = :job_id"),
                            {"job_id": job_id},
                        )
                    except ProgrammingError:
                        # Column may not exist yet; proceed after schema ensured
                        pass
                    df.to_sql("dk_optimizer", connection, if_exists="append", index=False)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to persist optimizer results: %s", exc)
        self._cache_job(job)
        return job

    def get_job(self, job_id: str) -> OptimizerJob | None:
        with self._cache_lock:
            self._prune_result_cache()
            job = self._jobs.get(job_id)
            if job is not None:
                self._cache_access[job_id] = monotonic()
                if not job.lineage_persisted or job.status in {"completed", "failed"}:
                    return job
        # A durable worker can finish after this API process cached its
        # pre-generation snapshot. Nonterminal persisted state is not final.
        return self._load_persisted_job(job_id) or job


def toy_slate_test() -> dict:
    """
    Tiny slate harness to exercise stacking constraints for cash vs. gpp.
    Returns a dict with solved lineups for inspection.
    """
    players = [
        # Team AAA (vs BBB)
        {"player_id": "QB_AAA", "name": "QB AAA", "position": "QB", "player_team": "AAA", "opponent_team": "BBB", "salary": 7000, "projection": 20, "p90": 22},
        {"player_id": "RB_AAA", "name": "RB AAA", "position": "RB", "player_team": "AAA", "opponent_team": "BBB", "salary": 6000, "projection": 15, "p90": 17},
        {"player_id": "WR_AAA1", "name": "WR AAA1", "position": "WR", "player_team": "AAA", "opponent_team": "BBB", "salary": 5500, "projection": 14, "p90": 17},
        {"player_id": "WR_AAA2", "name": "WR AAA2", "position": "WR", "player_team": "AAA", "opponent_team": "BBB", "salary": 5000, "projection": 13, "p90": 15},
        {"player_id": "TE_AAA", "name": "TE AAA", "position": "TE", "player_team": "AAA", "opponent_team": "BBB", "salary": 4000, "projection": 9, "p90": 11},
        # Team BBB (vs AAA) - bring-backs
        {"player_id": "RB_BBB", "name": "RB BBB", "position": "RB", "player_team": "BBB", "opponent_team": "AAA", "salary": 5200, "projection": 12, "p90": 14},
        {"player_id": "WR_BBB1", "name": "WR BBB1", "position": "WR", "player_team": "BBB", "opponent_team": "AAA", "salary": 5200, "projection": 13, "p90": 15},
        {"player_id": "WR_BBB2", "name": "WR BBB2", "position": "WR", "player_team": "BBB", "opponent_team": "AAA", "salary": 4200, "projection": 10, "p90": 12},
        {"player_id": "TE_BBB", "name": "TE BBB", "position": "TE", "player_team": "BBB", "opponent_team": "AAA", "salary": 3800, "projection": 8, "p90": 10},
        # DST options
        {"player_id": "DST_AAA", "name": "DST AAA", "position": "DST", "player_team": "AAA", "opponent_team": "BBB", "salary": 3000, "projection": 7, "p90": 7},
        {"player_id": "DST_BBB", "name": "DST BBB", "position": "DST", "player_team": "BBB", "opponent_team": "AAA", "salary": 3000, "projection": 7, "p90": 7},
    ]
    pool = pd.DataFrame(players)
    svc = OptimizerService(connection_string="sqlite:///:memory:")

    cash_lineup = svc._solve_lineup(
        pool,
        score_col="projection",
        contest_type="cash",
        stack_params={"stack_min": 1, "stack_max": None, "bringback": False, "include_rb_in_stack": False, "bringback_positions": ["WR", "TE"]},
    )
    gpp_lineup = svc._solve_lineup(
        pool,
        score_col="p90",
        contest_type="tournament",
        stack_params={"stack_min": 2, "stack_max": None, "bringback": True, "include_rb_in_stack": False, "bringback_positions": ["WR", "TE"]},
    )
    return {"cash": cash_lineup, "gpp": gpp_lineup}
