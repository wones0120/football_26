from __future__ import annotations

import json
import math
import statistics
from itertools import combinations
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

try:
    from pulp import LpBinary, LpMaximize, LpProblem, LpStatus, LpVariable, PULP_CBC_CMD, lpSum, value

    HAS_PULP = True
except Exception:  # noqa: BLE001
    HAS_PULP = False

from ..models import (
    ActualTopLineup,
    ActualTopLineupPlayer,
    CuratedInjury,
    CuratedSalary,
    PlayerAlias,
    PlayerGameFeatureMatrix,
    RawNflSchedule,
    RawNflWeeklyStat,
)
from ..schemas import (
    ActualTopLineupBuildRequest,
    ActualTopLineupBuildResponse,
    ActualTopLineupBuildSliceResponse,
    ActualTopLineupLearningRequest,
    ActualTopLineupLearningResponse,
    ActualTopLineupLearningSlateRowResponse,
    LineupLearningFeatureInsightRowResponse,
    LineupLearningRequest,
    LineupLearningResponse,
    LineupLearningSlateResultRowResponse,
    OptimalVsPredictedBacktestRequest,
    OptimalVsPredictedBacktestResponse,
    OptimalVsPredictedBacktestRowResponse,
    UltimateLineupExposureRowResponse,
    UltimateLineupPlayerRowResponse,
    UltimateLineupRequest,
    UltimateLineupResponse,
    UltimateLineupRowResponse,
)
from .matching import normalize_position
from .simulation import calculate_dk_points


DK_SALARY_CAP = 50000
CLASSIC_VALUE_DRIVER_FEATURE_NAMES = [
    "lineup_projected_value",
    "high_total_offense_share",
    "offense_vegas_coverage",
    "rb_avg_team_spread",
    "rb_underdog_share",
    "rb_spread_coverage",
    "flex_is_rb",
    "flex_is_wr",
    "flex_is_te",
]
FEATURE_NAMES = [
    "salary_used",
    "salary_left",
    "avg_salary",
    "qb_team_receivers",
    "qb_team_skill_players",
    "qb_opponent_players",
    "game_stack_size",
    "max_players_same_team",
    "unique_teams",
    "cheap_count",
    "value_count",
    "stud_count",
    "double_stack_flag",
    "bringback_flag",
    "lineup_projected_mean",
    "lineup_projected_p90",
    "qb_game_total_line",
    "qb_game_spread_abs",
    "qb_team_implied_total",
    "qb_opp_implied_total",
    "qb_has_vegas_line",
    "double_stack_x_total_line",
    "bringback_x_total_line",
    "game_stack_x_total_line",
    "double_stack_x_close_spread",
    "bringback_x_close_spread",
    *CLASSIC_VALUE_DRIVER_FEATURE_NAMES,
]

PATTERN_FEATURE_INDEX = {name: idx for idx, name in enumerate(FEATURE_NAMES)}
CLASSIC_FEATURE_ABLATION_GROUPS = {
    "value_drivers": tuple(CLASSIC_VALUE_DRIVER_FEATURE_NAMES),
    "game_environment": (
        "qb_game_total_line",
        "qb_game_spread_abs",
        "qb_team_implied_total",
        "qb_opp_implied_total",
        "qb_has_vegas_line",
        "double_stack_x_total_line",
        "bringback_x_total_line",
        "game_stack_x_total_line",
        "double_stack_x_close_spread",
        "bringback_x_close_spread",
    ),
}
TOP_TARGET_PERCENTILE = 98.0
CEILING_TARGET_PERCENTILE = 90.0
BUST_TARGET_PERCENTILE = 35.0
SHOWDOWN_ROSTER_TAGS = {"CPT", "CAPTAIN", "MVP", "STAR", "PRO"}
CLASSIC_ROSTER_TAGS = {"QB", "RB", "WR", "TE", "FLEX", "DST", "D/ST"}
SHOWDOWN_SALARY_CAP = 50000
SHOWDOWN_MIN_SALARY_FLOOR = 42000
SHOWDOWN_TOP_TARGET_PERCENTILE = 98.0
SHOWDOWN_FEATURE_NAMES = [
    "salary_used",
    "salary_left",
    "captain_salary",
    "captain_is_qb",
    "captain_is_rb",
    "captain_is_wr",
    "captain_is_te",
    "captain_is_k",
    "captain_is_dst",
    "flex_qb_count",
    "flex_rb_count",
    "flex_wr_count",
    "flex_te_count",
    "flex_k_count",
    "flex_dst_count",
    "same_team_as_captain_count",
    "opponent_team_count",
    "unique_teams",
    "lineup_projected_mean",
    "lineup_projected_p90",
    "captain_projected_mean",
    "captain_projected_p90",
    "captain_value",
    "game_total_line",
    "game_spread_abs",
    "captain_team_implied_total",
    "captain_opp_implied_total",
    "captain_has_vegas_line",
]
SHOWDOWN_FEATURE_INDEX = {name: idx for idx, name in enumerate(SHOWDOWN_FEATURE_NAMES)}
SHOWDOWN_CAPTAIN_BASE_FEATURE_NAMES = [
    "game_total_line",
    "game_spread_abs",
    "max_team_implied_total",
    "min_team_implied_total",
    "implied_total_diff",
    "has_vegas_line",
    "pool_size",
    "team_count",
    "team1_player_count",
    "team2_player_count",
    "qb_count",
    "rb_count",
    "wr_count",
    "te_count",
    "k_count",
    "dst_count",
    "top_qb_proj_mean",
    "top_rb_proj_mean",
    "top_wr_proj_mean",
    "top_te_proj_mean",
    "top_k_proj_mean",
    "top_dst_proj_mean",
    "top_qb_salary",
    "top_rb_salary",
    "top_wr_salary",
    "top_te_salary",
    "top_k_salary",
    "top_dst_salary",
]
SHOWDOWN_CAPTAIN_AVAILABILITY_FEATURE_NAMES = [
    "max_team_skill_out_count",
    "team_skill_out_count_diff",
    "max_team_position_out_count",
    "injury_report_coverage",
    "questionable_or_worse_count",
    "rb_position_out_max",
    "wr_position_out_max",
    "te_position_out_max",
    "max_team_available_skill_count",
    "team_available_skill_count_diff",
]
SHOWDOWN_CAPTAIN_CONTEXT_FEATURE_NAMES = [
    *SHOWDOWN_CAPTAIN_BASE_FEATURE_NAMES,
    *SHOWDOWN_CAPTAIN_AVAILABILITY_FEATURE_NAMES,
]
SHOWDOWN_CAPTAIN_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DST"}
CLASSIC_VALUE_DRIVER_POSITIONS = ("QB", "RB", "WR", "TE", "DST")
PLAYER_MATCHUP_MODEL_FEATURE_NAMES = [
    "salary_k",
    "is_home",
    "game_total_line",
    "team_spread_line",
    "team_implied_total",
    "opponent_implied_total",
    "player_games_history",
    "player_roll3_mean",
    "player_roll8_mean",
    "player_roll8_std",
    "player_vs_opp_roll4",
    "defense_pos_allowed_roll3",
    "defense_pos_allowed_roll8",
    "defense_pos_allowed_p90_roll8",
    "injury_status_score",
    "team_skill_out_count",
    "team_position_out_count",
    "kickoff_early",
    "kickoff_late",
    "kickoff_prime",
    "kickoff_unknown",
]

TEAM_ALIASES = {
    "JAX": "JAC",
    "WSH": "WAS",
    "WFT": "WAS",
    "LA": "LAR",
    "STL": "LAR",
    "SD": "LAC",
    "OAK": "LV",
}


@dataclass
class PlayerPoolRow:
    uid: str
    name: str
    team: str | None
    opponent: str | None
    position: str
    salary: int
    actual_points: float
    projected_mean_points: float = 0.0
    projected_p90_points: float = 0.0
    game_total_line: float | None = None
    team_spread_line: float | None = None
    team_implied_total: float | None = None
    opponent_implied_total: float | None = None
    player_master_id: str | None = None
    source_player_key: str | None = None


@dataclass
class ShowdownPlayerPoolRow:
    uid: str
    name: str
    team: str | None
    opponent: str | None
    position: str
    flex_salary: int
    captain_salary: int
    actual_points: float
    projected_mean_points: float = 0.0
    projected_p90_points: float = 0.0
    game_total_line: float | None = None
    team_spread_line: float | None = None
    team_implied_total: float | None = None
    opponent_implied_total: float | None = None
    player_injury_status: str = "unknown"
    team_skill_out_count: int = 0
    team_position_out_count: int = 0
    player_master_id: str | None = None
    source_player_key: str | None = None


@dataclass
class ShowdownLineup:
    captain: ShowdownPlayerPoolRow
    flex_players: list[ShowdownPlayerPoolRow]


@dataclass
class ShowdownCaptainArchetypeModel:
    classes: list[str]
    feature_names: list[str]
    x_mean: np.ndarray
    x_std: np.ndarray
    weights: np.ndarray
    bias: np.ndarray


@dataclass
class ClassicValueDriverModel:
    position_multipliers: dict[str, float]
    rb_spread_role_multipliers: dict[str, float]
    flex_position_multipliers: dict[str, float]
    high_total_threshold: float
    high_total_player_boost: float
    high_total_baseline_share: float


@dataclass
class MatchupOutcomeIntelligenceModel:
    position_hit4x_rate: dict[str, float]
    total_spread_lifts: dict[tuple[str, str, str], float]
    salary_teammate_lifts: dict[tuple[str, str, str], float]
    matchup_cell_lifts: dict[tuple[str, str, str], float]


@dataclass
class MatchupPriorGateRule:
    bucket_name: str
    bucket_value: str
    weight: float


@dataclass
class MatchupPriorGateModel:
    threshold: float
    base_prior_strength: float
    rules: list[MatchupPriorGateRule]


@dataclass
class LogisticTargetModel:
    weights: np.ndarray
    bias: float
    mean: np.ndarray
    std: np.ndarray
    positive_rate: float
    training_rows: int
    has_signal: bool


@dataclass
class PlayerMatchupProjectionModel:
    feature_names: list[str]
    weights: np.ndarray
    bias: float
    x_mean: np.ndarray
    x_std: np.ndarray
    y_mean: float
    y_std: float
    residual_std: float
    training_rows: int
    mae_model: float
    mae_baseline: float
    blend_weight: float
    enabled: bool


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _zscore(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return np.asarray([], dtype=float)
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std < 1e-9:
        return np.zeros(len(values), dtype=float)
    return (values - mean) / std


def _softmax_vector(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return np.asarray([], dtype=float)
    shifted = values - float(np.max(values))
    exp = np.exp(shifted)
    denom = float(np.sum(exp))
    if denom <= 0:
        return np.ones(values.shape[0], dtype=float) / max(values.shape[0], 1)
    return exp / denom


def _safe_median(values: list[float], default: float = 0.0) -> float:
    clean = [value for value in values if math.isfinite(value)]
    if not clean:
        return float(default)
    return float(statistics.median(clean))


def _max_or_zero(values: list[float]) -> float:
    clean = [value for value in values if math.isfinite(value)]
    if not clean:
        return 0.0
    return float(max(clean))


def _clamp(value: float, lower: float, upper: float) -> float:
    return float(max(lower, min(upper, value)))


def _spread_role_bucket(spread: float | None) -> str:
    if spread is None or not math.isfinite(float(spread)):
        return "unknown"
    spread_value = float(spread)
    if spread_value <= -7:
        return "big_favorite"
    if spread_value <= -3:
        return "favorite"
    if spread_value < 3:
        return "close"
    if spread_value < 7:
        return "underdog"
    return "big_underdog"


def _total_band_bucket(total: float | None) -> str:
    if total is None or not math.isfinite(float(total)):
        return "unknown"
    total_value = float(total)
    if total_value < 42.0:
        return "<42"
    if total_value < 47.0:
        return "42-46.9"
    if total_value < 51.0:
        return "47-50.9"
    return "51+"


def _salary_tier_bucket(position: str | None, salary: int | None) -> str:
    pos = (position or "").strip().upper()
    salary_value = int(salary or 0)
    if salary_value <= 0:
        return "unknown"
    if pos == "QB":
        if salary_value < 5800:
            return "cheap"
        if salary_value < 7200:
            return "mid"
        return "premium"
    if pos in {"RB", "WR", "TE"}:
        if salary_value < 5000:
            return "cheap"
        if salary_value < 7000:
            return "mid"
        return "premium"
    if pos == "DST":
        if salary_value < 2800:
            return "cheap"
        if salary_value < 3400:
            return "mid"
        return "premium"
    return "unknown"


def _teammate_out_bucket(value: int | None) -> str:
    count = int(value or 0)
    if count <= 0:
        return "0"
    if count == 1:
        return "1"
    if count == 2:
        return "2"
    return "3+"


def _normalize_pool_position(raw_position: str | None) -> str | None:
    if raw_position is None:
        return None
    cleaned = raw_position.strip().upper()
    if cleaned in {"D/ST", "DST", "DEF", "D"}:
        return "DST"

    normalized = normalize_position(raw_position)
    if not normalized:
        return None
    if normalized in {"QB", "RB", "WR", "TE", "K"}:
        return normalized
    if normalized in {"DST", "DEF"}:
        return "DST"
    return None


def _canonical_team(team: str | None) -> str | None:
    if team is None:
        return None
    cleaned = team.strip().upper()
    if not cleaned:
        return None
    return TEAM_ALIASES.get(cleaned, cleaned)


def _slice_ordinal(season: int, week: int) -> int:
    return (season * 25) + week


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return float(number)


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _kickoff_bucket(kickoff: str | None) -> str:
    if kickoff is None:
        return "unknown"
    text = kickoff.strip()
    if not text:
        return "unknown"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        hour = int(parsed.hour)
        if hour >= 19:
            return "prime"
        if hour >= 16:
            return "late"
        return "early"
    except ValueError:
        lowered = text.lower()
        if "night" in lowered or "primetime" in lowered:
            return "prime"
        if "late" in lowered:
            return "late"
        if "early" in lowered:
            return "early"
    return "unknown"


def _injury_status_bucket(status: str | None) -> str:
    if status is None:
        return "unknown"
    normalized = status.strip().lower()
    if not normalized:
        return "unknown"
    if any(token in normalized for token in ("out", "injured reserve", "ir", "suspended")):
        return "out"
    if "doubt" in normalized:
        return "doubtful"
    if any(token in normalized for token in ("question", "q")):
        return "questionable"
    if "probable" in normalized:
        return "probable"
    return "active"


def _injury_multiplier(status: str | None) -> float:
    bucket = _injury_status_bucket(status)
    if bucket == "out":
        return 0.35
    if bucket == "doubtful":
        return 0.60
    if bucket == "questionable":
        return 0.86
    if bucket == "probable":
        return 0.97
    return 1.0


def _injury_status_score(status: str | None) -> float:
    bucket = _injury_status_bucket(status)
    if bucket == "out":
        return 1.0
    if bucket == "doubtful":
        return 0.8
    if bucket == "questionable":
        return 0.5
    if bucket == "probable":
        return 0.2
    return 0.0


def _kickoff_bucket_flags(bucket: str | None) -> tuple[float, float, float, float]:
    normalized = (bucket or "unknown").strip().lower()
    return (
        1.0 if normalized == "early" else 0.0,
        1.0 if normalized == "late" else 0.0,
        1.0 if normalized == "prime" else 0.0,
        1.0 if normalized not in {"early", "late", "prime"} else 0.0,
    )


def _classic_lineup_rule_violations(lineup: list[PlayerPoolRow]) -> list[str]:
    violations: list[str] = []
    if len(lineup) != 9:
        violations.append(f"roster_size={len(lineup)} expected=9")
    if len({row.uid for row in lineup}) != 9:
        violations.append("duplicate_player")

    counts: dict[str, int] = defaultdict(int)
    for row in lineup:
        counts[row.position] += 1

    if counts.get("QB", 0) != 1:
        violations.append(f"qb_count={counts.get('QB', 0)} expected=1")
    if counts.get("DST", 0) != 1:
        violations.append(f"dst_count={counts.get('DST', 0)} expected=1")
    if counts.get("RB", 0) < 2:
        violations.append(f"rb_count={counts.get('RB', 0)} minimum=2")
    if counts.get("WR", 0) < 3:
        violations.append(f"wr_count={counts.get('WR', 0)} minimum=3")
    if counts.get("TE", 0) < 1:
        violations.append(f"te_count={counts.get('TE', 0)} minimum=1")
    if counts.get("RB", 0) + counts.get("WR", 0) + counts.get("TE", 0) != 7:
        violations.append(
            "skill_count="
            f"{counts.get('RB', 0) + counts.get('WR', 0) + counts.get('TE', 0)} expected=7"
        )

    salary_used = int(sum(row.salary for row in lineup))
    if salary_used > DK_SALARY_CAP:
        violations.append(f"salary_used={salary_used} cap={DK_SALARY_CAP}")

    dst = next((row for row in lineup if row.position == "DST"), None)
    if dst is None:
        return violations
    dst_team = dst.team
    dst_opponent = dst.opponent
    if dst_team is None and dst_opponent is None:
        return violations

    for row in lineup:
        if row.position == "DST":
            continue
        # Do not roster offensive players against the selected defense.
        if dst_team and row.opponent and row.opponent == dst_team:
            violations.append(f"offense_against_dst={row.uid}")
        if dst_opponent and row.team and row.team == dst_opponent:
            violations.append(f"offense_against_dst={row.uid}")
    return sorted(set(violations))


def _lineup_satisfies_roster_rules(lineup: list[PlayerPoolRow]) -> bool:
    return not _classic_lineup_rule_violations(lineup)


def _validate_classic_lineup_batch(
    lineups: list[list[PlayerPoolRow]],
    *,
    context: str,
) -> None:
    invalid: list[str] = []
    for index, lineup in enumerate(lineups):
        violations = _classic_lineup_rule_violations(lineup)
        if violations:
            invalid.append(f"lineup={index} violations={','.join(violations)}")
            if len(invalid) >= 10:
                break
    if invalid:
        raise ValueError(
            f"Classic lineup validation failed ({context}): "
            + "; ".join(invalid)
        )


def _showdown_lineup_satisfies_rules(lineup: ShowdownLineup) -> bool:
    if len(lineup.flex_players) != 5:
        return False
    all_ids = [lineup.captain.uid, *[player.uid for player in lineup.flex_players]]
    if len(all_ids) != 6 or len(set(all_ids)) != 6:
        return False

    salary_used = int(lineup.captain.captain_salary + sum(player.flex_salary for player in lineup.flex_players))
    if salary_used > SHOWDOWN_SALARY_CAP:
        return False

    team_counts: dict[str, int] = defaultdict(int)
    for player in [lineup.captain, *lineup.flex_players]:
        if player.team:
            team_counts[player.team] += 1
    if team_counts and max(team_counts.values()) > 5:
        return False
    return True


def _points_allowed_bonus(points_allowed: float) -> float:
    if points_allowed <= 0:
        return 10.0
    if points_allowed <= 6:
        return 7.0
    if points_allowed <= 13:
        return 4.0
    if points_allowed <= 20:
        return 1.0
    if points_allowed <= 27:
        return 0.0
    if points_allowed <= 34:
        return -1.0
    return -4.0


def _calculate_dk_player_points(raw_row: dict[str, Any], position: str | None) -> float:
    points = calculate_dk_points(raw_row)
    normalized = (position or "").strip().upper()
    if normalized == "K":
        fg_0_39 = (
            _safe_float(raw_row.get("fg_made_0_19")) or 0.0
        ) + ((_safe_float(raw_row.get("fg_made_20_29")) or 0.0)) + ((_safe_float(raw_row.get("fg_made_30_39")) or 0.0))
        fg_40_49 = _safe_float(raw_row.get("fg_made_40_49")) or 0.0
        fg_50_59 = _safe_float(raw_row.get("fg_made_50_59")) or 0.0
        fg_60_plus = _safe_float(raw_row.get("fg_made_60_")) or 0.0
        pat_made = _safe_float(raw_row.get("pat_made")) or 0.0
        fg_missed = _safe_float(raw_row.get("fg_missed")) or 0.0
        points += (
            (3.0 * fg_0_39)
            + (4.0 * fg_40_49)
            + (5.0 * (fg_50_59 + fg_60_plus))
            + pat_made
            - fg_missed
        )
    return float(max(points, 0.0))


class LineupLearningService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._game_context_cache: dict[tuple[int, int], dict[str, dict[str, float]]] = {}
        self._dst_actual_cache: dict[tuple[int, int], dict[str, float]] = {}
        self._dst_projection_cache: dict[tuple[int, int], dict[str, tuple[float, float]]] = {}
        self._player_projection_cache: dict[
            tuple[str, int, int, str],
            tuple[dict[str, tuple[float, float]], dict[str, tuple[float, float]]],
        ] = {}
        self._slate_type_cache: dict[tuple[str, int, int, str], str] = {}
        self._classic_value_model_cache: dict[str, ClassicValueDriverModel] = {}
        self._matchup_outcome_model_cache: dict[str, MatchupOutcomeIntelligenceModel] = {}
        self._matchup_prior_gate_cache: dict[str, MatchupPriorGateModel] = {}
        self._projection_feature_cache: dict[tuple[str, int, int, str], dict[str, dict[str, Any]]] = {}
        self._matchup_model_cache: dict[tuple[str, int, int, str], dict[str, PlayerMatchupProjectionModel]] = {}
        self._use_matrix_matchup_model = True
        self._disabled_classic_feature_indices: tuple[int, ...] = ()

    def set_matchup_matrix_projection_enabled(self, enabled: bool) -> None:
        self._use_matrix_matchup_model = bool(enabled)
        self._player_projection_cache.clear()

    def set_classic_feature_ablation_groups(self, groups: list[str] | tuple[str, ...]) -> None:
        unknown = sorted(set(groups) - set(CLASSIC_FEATURE_ABLATION_GROUPS))
        if unknown:
            raise ValueError(
                "Unknown classic feature ablation group(s): "
                f"{', '.join(unknown)}. Available: {', '.join(sorted(CLASSIC_FEATURE_ABLATION_GROUPS))}."
            )
        disabled_names = {
            feature_name
            for group in groups
            for feature_name in CLASSIC_FEATURE_ABLATION_GROUPS[group]
        }
        self._disabled_classic_feature_indices = tuple(
            PATTERN_FEATURE_INDEX[feature_name]
            for feature_name in FEATURE_NAMES
            if feature_name in disabled_names
        )

    def _game_context_by_team(self, *, season: int, week: int) -> dict[str, dict[str, float]]:
        cache_key = (season, week)
        cached = self._game_context_cache.get(cache_key)
        if cached is not None:
            return cached

        rows = self.session.execute(
            select(RawNflSchedule).where(
                and_(
                    RawNflSchedule.season == season,
                    RawNflSchedule.week == week,
                )
            )
        ).scalars().all()

        context: dict[str, dict[str, float]] = {}
        for row in rows:
            payload = row.raw_row_json or {}
            home_team = _canonical_team(row.home_team or payload.get("home_team"))
            away_team = _canonical_team(row.away_team or payload.get("away_team"))
            if not home_team or not away_team:
                continue

            total_line = _safe_float(payload.get("total_line"))
            if total_line is None:
                total_line = _safe_float(payload.get("total"))
            spread_line = _safe_float(payload.get("spread_line"))

            home_implied: float | None = None
            away_implied: float | None = None
            if total_line is not None and spread_line is not None:
                # `spread_line` is home-team spread from nflverse schedules.
                home_implied = (total_line / 2.0) - (spread_line / 2.0)
                away_implied = (total_line / 2.0) + (spread_line / 2.0)

            home_ctx: dict[str, float] = {"has_vegas_line": 0.0}
            away_ctx: dict[str, float] = {"has_vegas_line": 0.0}
            if total_line is not None:
                home_ctx["game_total_line"] = total_line
                away_ctx["game_total_line"] = total_line
            if spread_line is not None:
                home_ctx["team_spread_line"] = spread_line
                away_ctx["team_spread_line"] = -spread_line
            if home_implied is not None and away_implied is not None:
                home_ctx["team_implied_total"] = home_implied
                home_ctx["opponent_implied_total"] = away_implied
                away_ctx["team_implied_total"] = away_implied
                away_ctx["opponent_implied_total"] = home_implied
            if total_line is not None and spread_line is not None:
                home_ctx["has_vegas_line"] = 1.0
                away_ctx["has_vegas_line"] = 1.0

            context[home_team] = home_ctx
            context[away_team] = away_ctx

        self._game_context_cache[cache_key] = context
        return context

    def _fetch_available_slate_slices(
        self,
        *,
        source_system: str,
        season_start: int,
        season_end: int,
        slate_filter: str | None,
    ) -> list[tuple[int, int, str]]:
        filters = [
            CuratedSalary.source_system == source_system,
            CuratedSalary.season >= season_start,
            CuratedSalary.season <= season_end,
        ]
        if slate_filter:
            filters.append(CuratedSalary.slate == slate_filter)

        rows = self.session.execute(
            select(CuratedSalary.season, CuratedSalary.week, CuratedSalary.slate)
            .where(and_(*filters))
            .group_by(CuratedSalary.season, CuratedSalary.week, CuratedSalary.slate)
            .order_by(CuratedSalary.season, CuratedSalary.week, CuratedSalary.slate)
        ).all()
        return [(int(season), int(week), str(slate)) for season, week, slate in rows]

    def _classify_slate_type(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
    ) -> str:
        cache_key = (source_system, season, week, slate)
        cached = self._slate_type_cache.get(cache_key)
        if cached is not None:
            return cached

        rows = self.session.execute(
            select(CuratedSalary.roster_position, CuratedSalary.position, CuratedSalary.team).where(
                and_(
                    CuratedSalary.source_system == source_system,
                    CuratedSalary.season == season,
                    CuratedSalary.week == week,
                    CuratedSalary.slate == slate,
                )
            )
        ).all()
        if not rows:
            self._slate_type_cache[cache_key] = "unknown"
            return "unknown"

        roster_positions: set[str] = set()
        base_positions: set[str] = set()
        teams: set[str] = set()
        for roster_position, position, team in rows:
            rp = (roster_position or "").strip().upper()
            if rp:
                roster_positions.add(rp)
            bp = _normalize_pool_position(position)
            if bp:
                base_positions.add(bp)
            canonical_team = _canonical_team(team)
            if canonical_team:
                teams.add(canonical_team)

        if roster_positions & SHOWDOWN_ROSTER_TAGS:
            slate_type = "showdown"
        elif len(teams) <= 2 and "DST" not in base_positions:
            slate_type = "showdown"
        elif (roster_positions & CLASSIC_ROSTER_TAGS) or "DST" in base_positions:
            slate_type = "classic"
        elif len(teams) >= 4:
            slate_type = "classic"
        else:
            slate_type = "showdown"

        self._slate_type_cache[cache_key] = slate_type
        return slate_type

    def _filter_slices_by_slate_type(
        self,
        *,
        source_system: str,
        slices: list[tuple[int, int, str]],
        slate_type: str,
    ) -> list[tuple[int, int, str]]:
        normalized = slate_type.strip().lower()
        if normalized in {"all", ""}:
            return slices
        if normalized not in {"classic", "showdown"}:
            raise ValueError(f"Unsupported slate_type: {slate_type}")

        filtered: list[tuple[int, int, str]] = []
        for season, week, slate in slices:
            current_type = self._classify_slate_type(
                source_system=source_system,
                season=season,
                week=week,
                slate=slate,
            )
            if current_type == normalized:
                filtered.append((season, week, slate))
        return filtered

    def _compute_dst_actual_points(self, *, season: int, week: int) -> dict[str, float]:
        cache_key = (season, week)
        cached = self._dst_actual_cache.get(cache_key)
        if cached is not None:
            return cached

        schedule_rows = self.session.execute(
            select(RawNflSchedule).where(
                and_(
                    RawNflSchedule.season == season,
                    RawNflSchedule.week == week,
                )
            )
        ).scalars().all()
        points_allowed_by_team: dict[str, float] = {}
        opponent_by_team: dict[str, str] = {}
        for row in schedule_rows:
            home_team = _canonical_team(row.home_team)
            away_team = _canonical_team(row.away_team)
            payload = row.raw_row_json or {}
            home_score = payload.get("home_score")
            away_score = payload.get("away_score")
            try:
                home_score_num = float(home_score)
                away_score_num = float(away_score)
            except (TypeError, ValueError):
                continue
            if home_team and away_team:
                points_allowed_by_team[home_team] = away_score_num
                points_allowed_by_team[away_team] = home_score_num
                opponent_by_team[home_team] = away_team
                opponent_by_team[away_team] = home_team

        offense_agg_rows = self.session.execute(
            select(
                RawNflWeeklyStat.team,
                RawNflWeeklyStat.raw_row_json,
            ).where(
                and_(
                    RawNflWeeklyStat.season == season,
                    RawNflWeeklyStat.week == week,
                )
            )
        ).all()

        sacks_allowed_by_team: dict[str, float] = defaultdict(float)
        interceptions_thrown_by_team: dict[str, float] = defaultdict(float)
        fumbles_lost_by_team: dict[str, float] = defaultdict(float)
        dst_tds_by_team: dict[str, float] = defaultdict(float)

        for team, payload in offense_agg_rows:
            team_key = _canonical_team(team)
            if not team_key:
                continue
            raw = payload or {}
            def num(key: str) -> float:
                value = raw.get(key)
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return 0.0

            sacks_allowed_by_team[team_key] += num("sacks_suffered")
            interceptions_thrown_by_team[team_key] += num("passing_interceptions")
            fumbles_lost_by_team[team_key] += (
                num("fumbles_lost")
                + num("rushing_fumbles_lost")
                + num("receiving_fumbles_lost")
                + num("sack_fumbles_lost")
            )
            # `def_tds` and `special_teams_tds` appear on player rows and can be aggregated by team.
            dst_tds_by_team[team_key] += (num("def_tds") + num("special_teams_tds"))

        dst_points: dict[str, float] = {}
        for defense_team, opponent_team in opponent_by_team.items():
            points_allowed = points_allowed_by_team.get(defense_team)
            if points_allowed is None:
                continue
            sacks = sacks_allowed_by_team.get(opponent_team, 0.0)
            interceptions = interceptions_thrown_by_team.get(opponent_team, 0.0)
            fumbles_lost = fumbles_lost_by_team.get(opponent_team, 0.0)
            dst_tds = dst_tds_by_team.get(defense_team, 0.0)
            total = (
                _points_allowed_bonus(points_allowed)
                + sacks
                + (2.0 * interceptions)
                + (2.0 * fumbles_lost)
                + (6.0 * dst_tds)
            )
            dst_points[defense_team] = max(total, -10.0)

        self._dst_actual_cache[cache_key] = dst_points
        return dst_points

    def _fetch_slate_player_pool(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
        projection_lookup: dict[str, tuple[float, float]] | None = None,
        dst_projection_lookup: dict[str, tuple[float, float]] | None = None,
    ) -> list[PlayerPoolRow]:
        salary_rows = self.session.execute(
            select(CuratedSalary).where(
                and_(
                    CuratedSalary.source_system == source_system,
                    CuratedSalary.season == season,
                    CuratedSalary.week == week,
                    CuratedSalary.slate == slate,
                )
            )
        ).scalars().all()
        if not salary_rows:
            return []

        dst_points_by_team = self._compute_dst_actual_points(season=season, week=week)
        game_context_by_team = self._game_context_by_team(season=season, week=week)

        actual_points_by_master: dict[str, float] = {}
        master_ids = sorted({row.player_master_id for row in salary_rows if row.player_master_id})
        if master_ids:
            alias_rows = self.session.execute(
                select(PlayerAlias.player_master_id, PlayerAlias.source_key).where(
                    and_(
                        PlayerAlias.source_system == "nflreadpy",
                        PlayerAlias.player_master_id.in_(master_ids),
                    )
                )
            ).all()
            player_id_to_masters: dict[str, set[str]] = defaultdict(set)
            for player_master_id, source_key in alias_rows:
                if source_key:
                    player_id_to_masters[source_key].add(player_master_id)
            tracked_player_ids = sorted(player_id_to_masters.keys())

            if tracked_player_ids:
                stats_rows = self.session.execute(
                    select(RawNflWeeklyStat).where(
                        and_(
                            RawNflWeeklyStat.season == season,
                            RawNflWeeklyStat.week == week,
                            RawNflWeeklyStat.player_id.in_(tracked_player_ids),
                        )
                    )
                ).scalars().all()

                for row in stats_rows:
                    if not row.player_id:
                        continue
                    points = _calculate_dk_player_points(row.raw_row_json or {}, row.position)
                    if not math.isfinite(points):
                        continue
                    for master_id in player_id_to_masters.get(row.player_id, set()):
                        actual_points_by_master[master_id] = max(
                            actual_points_by_master.get(master_id, 0.0),
                            points,
                        )

        pool: list[PlayerPoolRow] = []
        for row in salary_rows:
            normalized_position = _normalize_pool_position(row.position)
            if not normalized_position:
                continue
            salary_value = int(row.salary or 0)
            if salary_value <= 0:
                continue
            uid = row.player_master_id or row.source_player_key or f"{row.normalized_name}:{row.team}:{row.position}"
            if not uid:
                continue
            team_key = _canonical_team(row.team)
            opponent_key = _canonical_team(row.opponent)
            context = game_context_by_team.get(team_key or "", {})
            points = actual_points_by_master.get(row.player_master_id or "", 0.0)
            projected_mean = 0.0
            projected_p90 = 0.0
            key_candidates = [row.player_master_id, row.source_player_key]
            for key in key_candidates:
                if not key or projection_lookup is None:
                    continue
                if key in projection_lookup:
                    projected_mean, projected_p90 = projection_lookup[key]
                    break
            if normalized_position == "DST":
                points = dst_points_by_team.get(team_key or "", 0.0)
                if dst_projection_lookup and team_key and team_key in dst_projection_lookup:
                    projected_mean, projected_p90 = dst_projection_lookup[team_key]
            pool.append(
                PlayerPoolRow(
                    uid=uid,
                    name=row.player_name,
                    team=team_key,
                    opponent=opponent_key,
                    position=normalized_position,
                    salary=salary_value,
                    actual_points=float(points),
                    projected_mean_points=float(projected_mean),
                    projected_p90_points=float(projected_p90),
                    game_total_line=_safe_float(context.get("game_total_line")),
                    team_spread_line=_safe_float(context.get("team_spread_line")),
                    team_implied_total=_safe_float(context.get("team_implied_total")),
                    opponent_implied_total=_safe_float(context.get("opponent_implied_total")),
                    player_master_id=row.player_master_id,
                    source_player_key=row.source_player_key,
                )
            )

        # Keep one entry per player uid, retaining the highest salary variant if duplicates exist.
        deduped: dict[str, PlayerPoolRow] = {}
        for row in pool:
            existing = deduped.get(row.uid)
            if existing is None or row.salary > existing.salary:
                deduped[row.uid] = row
        return list(deduped.values())

    def _normalize_showdown_position(self, raw_position: str | None) -> str:
        normalized = _normalize_pool_position(raw_position)
        if normalized:
            return normalized
        fallback = (normalize_position(raw_position) or "UNK").strip().upper()
        if fallback in {"DEF", "D/ST", "D"}:
            return "DST"
        return fallback or "UNK"

    def _showdown_lineup_key(self, lineup: ShowdownLineup) -> str:
        flex_ids = sorted(player.uid for player in lineup.flex_players)
        return f"CPT:{lineup.captain.uid}|FLEX:{'|'.join(flex_ids)}"

    def _showdown_salary_used(self, lineup: ShowdownLineup) -> int:
        return int(lineup.captain.captain_salary + sum(player.flex_salary for player in lineup.flex_players))

    def _showdown_actual_points(self, lineup: ShowdownLineup) -> float:
        return float((1.5 * lineup.captain.actual_points) + sum(player.actual_points for player in lineup.flex_players))

    def _showdown_projected_mean(self, lineup: ShowdownLineup) -> float:
        return float(
            (1.5 * lineup.captain.projected_mean_points)
            + sum(player.projected_mean_points for player in lineup.flex_players)
        )

    def _showdown_projected_p90(self, lineup: ShowdownLineup) -> float:
        return float(
            (1.5 * lineup.captain.projected_p90_points)
            + sum(player.projected_p90_points for player in lineup.flex_players)
        )

    def _showdown_captain_context_features(
        self,
        players: list[ShowdownPlayerPoolRow],
    ) -> dict[str, float]:
        by_team: dict[str, list[ShowdownPlayerPoolRow]] = {}
        for row in players:
            if row.team:
                by_team.setdefault(row.team, []).append(row)

        team_counts = sorted([len(rows) for rows in by_team.values()], reverse=True)
        team1_count = float(team_counts[0]) if len(team_counts) >= 1 else 0.0
        team2_count = float(team_counts[1]) if len(team_counts) >= 2 else 0.0

        team_implied_values: list[float] = []
        for rows in by_team.values():
            values = [float(row.team_implied_total) for row in rows if row.team_implied_total is not None]
            if values:
                team_implied_values.append(_safe_median(values))

        game_totals = [float(row.game_total_line) for row in players if row.game_total_line is not None]
        spread_abs_values = [
            abs(float(row.team_spread_line))
            for row in players
            if row.team_spread_line is not None and math.isfinite(float(row.team_spread_line))
        ]
        has_vegas_line = 1.0 if game_totals and spread_abs_values else 0.0
        team_skill_out_values = [
            max(int(row.team_skill_out_count) for row in rows)
            for rows in by_team.values()
            if rows
        ]
        team_position_out_values = [
            int(row.team_position_out_count)
            for row in players
            if row.position in {"QB", "RB", "WR", "TE"}
        ]
        injury_report_rows = [
            row
            for row in players
            if (row.player_injury_status or "unknown").strip().lower() != "unknown"
        ]
        questionable_or_worse_count = sum(
            1
            for row in players
            if _injury_status_score(row.player_injury_status) >= 0.5
        )
        team_available_skill_counts = [
            sum(
                1
                for row in rows
                if row.position in {"QB", "RB", "WR", "TE"}
                and _injury_status_score(row.player_injury_status) < 0.8
            )
            for rows in by_team.values()
        ]

        features = {
            "game_total_line": _safe_median(game_totals),
            "game_spread_abs": _safe_median(spread_abs_values),
            "max_team_implied_total": _max_or_zero(team_implied_values),
            "min_team_implied_total": min(team_implied_values) if team_implied_values else 0.0,
            "implied_total_diff": (
                (_max_or_zero(team_implied_values) - min(team_implied_values))
                if team_implied_values
                else 0.0
            ),
            "has_vegas_line": has_vegas_line,
            "pool_size": float(len(players)),
            "team_count": float(len(by_team)),
            "team1_player_count": team1_count,
            "team2_player_count": team2_count,
            "max_team_skill_out_count": _max_or_zero(
                [float(value) for value in team_skill_out_values]
            ),
            "team_skill_out_count_diff": (
                float(max(team_skill_out_values) - min(team_skill_out_values))
                if team_skill_out_values
                else 0.0
            ),
            "max_team_position_out_count": _max_or_zero(
                [float(value) for value in team_position_out_values]
            ),
            "injury_report_coverage": (
                float(len(injury_report_rows) / len(players))
                if players
                else 0.0
            ),
            "questionable_or_worse_count": float(questionable_or_worse_count),
            "max_team_available_skill_count": _max_or_zero(
                [float(value) for value in team_available_skill_counts]
            ),
            "team_available_skill_count_diff": (
                float(max(team_available_skill_counts) - min(team_available_skill_counts))
                if team_available_skill_counts
                else 0.0
            ),
        }

        for position in ("QB", "RB", "WR", "TE", "K", "DST"):
            rows = [row for row in players if row.position == position]
            features[f"{position.lower()}_count"] = float(len(rows))
            features[f"top_{position.lower()}_proj_mean"] = _max_or_zero(
                [float(row.projected_mean_points) for row in rows]
            )
            features[f"top_{position.lower()}_salary"] = _max_or_zero(
                [float(row.flex_salary) for row in rows]
            )
        for position in ("RB", "WR", "TE"):
            features[f"{position.lower()}_position_out_max"] = _max_or_zero(
                [
                    float(row.team_position_out_count)
                    for row in players
                    if row.position == position
                ]
            )
        return features

    def _load_showdown_captain_archetype_model(self, model_path: str) -> ShowdownCaptainArchetypeModel:
        resolved_path = Path(model_path).expanduser().resolve()
        if not resolved_path.exists():
            raise ValueError(f"Showdown captain model not found: {resolved_path}")
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        model = payload.get("model", {})
        classes = [str(value) for value in model.get("classes", []) if str(value)]
        feature_names = [str(value) for value in model.get("feature_names", []) if str(value)]
        if not classes or not feature_names:
            raise ValueError("Invalid showdown captain model: missing classes or feature_names.")
        weights = np.asarray(model.get("weights"), dtype=float)
        bias = np.asarray(model.get("bias"), dtype=float)
        x_mean = np.asarray(model.get("x_mean"), dtype=float)
        x_std = np.asarray(model.get("x_std"), dtype=float)
        if weights.ndim != 2:
            raise ValueError("Invalid showdown captain model: weights must be 2D.")
        if weights.shape[0] != len(feature_names) or weights.shape[1] != len(classes):
            raise ValueError("Invalid showdown captain model: weights shape mismatch.")
        if bias.shape[0] != len(classes):
            raise ValueError("Invalid showdown captain model: bias shape mismatch.")
        if x_mean.shape[0] != len(feature_names) or x_std.shape[0] != len(feature_names):
            raise ValueError("Invalid showdown captain model: normalization vector mismatch.")
        x_std = np.where(x_std < 1e-6, 1.0, x_std)
        return ShowdownCaptainArchetypeModel(
            classes=classes,
            feature_names=feature_names,
            x_mean=x_mean,
            x_std=x_std,
            weights=weights,
            bias=bias,
        )

    def _predict_showdown_captain_position_probs(
        self,
        players: list[ShowdownPlayerPoolRow],
        model: ShowdownCaptainArchetypeModel,
    ) -> dict[str, float]:
        features = self._showdown_captain_context_features(players)
        row = np.asarray([float(features.get(name, 0.0)) for name in model.feature_names], dtype=float)
        logits = ((row - model.x_mean) / model.x_std) @ model.weights + model.bias
        probs = _softmax_vector(np.asarray(logits, dtype=float))
        out = {
            model.classes[index].upper(): float(probs[index])
            for index in range(len(model.classes))
            if model.classes[index].upper() in SHOWDOWN_CAPTAIN_POSITIONS
        }
        if not out:
            return {}
        total = float(sum(out.values()))
        if total <= 0:
            return {}
        return {key: value / total for key, value in out.items()}

    def _load_classic_value_driver_model(self, model_path: str) -> ClassicValueDriverModel:
        resolved_path = Path(model_path).expanduser().resolve()
        cache_key = str(resolved_path)
        cached = self._classic_value_model_cache.get(cache_key)
        if cached is not None:
            return cached
        if not resolved_path.exists():
            raise ValueError(f"Classic value-driver model not found: {resolved_path}")

        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        position_rows = payload.get("position_value_summary", [])
        position_avg_value: dict[str, float] = {}
        for row in position_rows:
            position = str(row.get("name", "")).upper().strip()
            avg_value = _safe_float(row.get("avg_value"))
            if not position or avg_value is None or avg_value <= 0:
                continue
            if position in CLASSIC_VALUE_DRIVER_POSITIONS:
                position_avg_value[position] = float(avg_value)

        skill_positions = [pos for pos in ("QB", "RB", "WR", "TE") if pos in position_avg_value]
        skill_mean_value = float(
            statistics.mean([position_avg_value[pos] for pos in skill_positions])
        ) if skill_positions else 1.0
        position_multipliers: dict[str, float] = {}
        for position in CLASSIC_VALUE_DRIVER_POSITIONS:
            if position not in position_avg_value:
                position_multipliers[position] = 1.0
                continue
            if position == "DST":
                # DST slot is fixed to 1 spot, so avoid aggressive weighting.
                position_multipliers[position] = 1.0
            else:
                position_multipliers[position] = _clamp(
                    float(position_avg_value[position] / max(skill_mean_value, 1e-6)),
                    0.85,
                    1.20,
                )

        high_total_payload = payload.get("high_point_total_analysis", {})
        high_total_threshold = _safe_float(high_total_payload.get("high_total_threshold")) or 48.0
        high_total_share_lift = _safe_float(high_total_payload.get("high_total_share_lift")) or 1.0
        high_total_baseline_share = _safe_float(high_total_payload.get("baseline_high_total_share")) or 0.0
        high_total_player_boost = _clamp(
            1.0 + (0.55 * max(0.0, high_total_share_lift - 1.0)),
            1.0,
            1.35,
        )

        rb_payload = payload.get("rb_spread_analysis", {})
        rb_rows = rb_payload.get("rb_by_spread_role", []) or []
        rb_avg_value_overall = position_avg_value.get("RB")
        if rb_avg_value_overall is None or rb_avg_value_overall <= 0:
            rb_values = [
                _safe_float(row.get("avg_value"))
                for row in rb_rows
                if _safe_float(row.get("avg_value")) is not None
            ]
            rb_avg_value_overall = float(statistics.mean(rb_values)) if rb_values else 1.0

        rb_spread_role_multipliers: dict[str, float] = {}
        for row in rb_rows:
            name = str(row.get("name", "")).strip()
            avg_value = _safe_float(row.get("avg_value"))
            if not name or avg_value is None:
                continue
            rb_spread_role_multipliers[name] = _clamp(
                float(avg_value / max(rb_avg_value_overall, 1e-6)),
                0.80,
                1.25,
            )

        flex_payload = payload.get("optimal_main_lineup_mix", {})
        flex_rows = flex_payload.get("flex_position_mix", []) or []
        flex_shares: dict[str, float] = {}
        for row in flex_rows:
            position = str(row.get("position", "")).upper().strip()
            share = _safe_float(row.get("share"))
            if position in {"RB", "WR", "TE"} and share is not None and share >= 0:
                flex_shares[position] = float(share)
        baseline_share = 1.0 / 3.0
        flex_position_multipliers = {
            position: _clamp(flex_shares.get(position, baseline_share) / baseline_share, 0.75, 1.40)
            for position in ("RB", "WR", "TE")
        }

        model = ClassicValueDriverModel(
            position_multipliers=position_multipliers,
            rb_spread_role_multipliers=rb_spread_role_multipliers,
            flex_position_multipliers=flex_position_multipliers,
            high_total_threshold=float(high_total_threshold),
            high_total_player_boost=float(high_total_player_boost),
            high_total_baseline_share=float(max(0.0, min(1.0, high_total_baseline_share))),
        )
        self._classic_value_model_cache[cache_key] = model
        return model

    def _load_matchup_outcome_model(self, model_path: str) -> MatchupOutcomeIntelligenceModel:
        resolved_path = Path(model_path).expanduser().resolve()
        cache_key = str(resolved_path)
        cached = self._matchup_outcome_model_cache.get(cache_key)
        if cached is not None:
            return cached
        if not resolved_path.exists():
            raise ValueError(f"Matchup outcome model not found: {resolved_path}")

        payload = json.loads(resolved_path.read_text(encoding="utf-8"))

        position_hit4x_rate: dict[str, float] = {}
        for row in payload.get("position_baselines", []) or []:
            position = str(row.get("position", "")).upper().strip()
            hit4x_rate = _safe_float(row.get("hit4x_rate"))
            if position and hit4x_rate is not None:
                position_hit4x_rate[position] = float(hit4x_rate)

        total_spread_lifts: dict[tuple[str, str, str], float] = {}
        total_spread_payload = (
            payload.get("top_context_signals", {})
            .get("position_x_total_band_x_spread_role", {})
        )
        for section in ("positive", "negative"):
            for row in total_spread_payload.get(section, []) or []:
                key_values = row.get("key_values", {}) or {}
                position = str(key_values.get("position", "")).upper().strip()
                total_band = str(key_values.get("total_band", "")).strip()
                spread_role = str(key_values.get("spread_role", "")).strip()
                lift = _safe_float(row.get("adjusted_hit4x_lift"))
                if position and total_band and spread_role and lift is not None:
                    total_spread_lifts[(position, total_band, spread_role)] = float(lift)

        salary_teammate_lifts: dict[tuple[str, str, str], float] = {}
        salary_teammate_payload = (
            payload.get("top_context_signals", {})
            .get("position_x_salary_tier_x_teammate_out_band", {})
        )
        for section in ("positive", "negative"):
            for row in salary_teammate_payload.get(section, []) or []:
                key_values = row.get("key_values", {}) or {}
                position = str(key_values.get("position", "")).upper().strip()
                salary_tier = str(key_values.get("salary_tier", "")).strip()
                teammate_band = str(key_values.get("teammate_out_band", "")).strip()
                lift = _safe_float(row.get("adjusted_hit4x_lift"))
                if position and salary_tier and teammate_band and lift is not None:
                    salary_teammate_lifts[(position, salary_tier, teammate_band)] = float(lift)

        matchup_cell_lifts: dict[tuple[str, str, str], float] = {}
        matchup_payload = payload.get("matchup_cells", {}) or {}
        for section in ("positive", "negative"):
            for row in matchup_payload.get(section, []) or []:
                position = str(row.get("position", "")).upper().strip()
                team = _canonical_team(_safe_str(row.get("team")))
                opponent = _canonical_team(_safe_str(row.get("opponent")))
                lift = _safe_float(row.get("adjusted_hit4x_lift"))
                if position and team and opponent and lift is not None:
                    matchup_cell_lifts[(position, team, opponent)] = float(lift)

        model = MatchupOutcomeIntelligenceModel(
            position_hit4x_rate=position_hit4x_rate,
            total_spread_lifts=total_spread_lifts,
            salary_teammate_lifts=salary_teammate_lifts,
            matchup_cell_lifts=matchup_cell_lifts,
        )
        self._matchup_outcome_model_cache[cache_key] = model
        return model

    def _load_matchup_prior_gate_model(self, model_path: str) -> MatchupPriorGateModel:
        resolved_path = Path(model_path).expanduser().resolve()
        cache_key = str(resolved_path)
        cached = self._matchup_prior_gate_cache.get(cache_key)
        if cached is not None:
            return cached
        if not resolved_path.exists():
            raise ValueError(f"Matchup prior gate model not found: {resolved_path}")

        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        rules: list[MatchupPriorGateRule] = []
        for row in payload.get("rules", []) or []:
            bucket_name = str(row.get("bucket_name", "")).strip()
            bucket_value = str(row.get("bucket_value", "")).strip()
            weight = _safe_float(row.get("weight"))
            if bucket_name and bucket_value and weight is not None:
                rules.append(
                    MatchupPriorGateRule(
                        bucket_name=bucket_name,
                        bucket_value=bucket_value,
                        weight=float(weight),
                    )
                )
        model = MatchupPriorGateModel(
            threshold=float(_safe_float(payload.get("selected_threshold")) or 0.0),
            base_prior_strength=float(_safe_float(payload.get("base_prior_strength")) or 0.0),
            rules=rules,
        )
        self._matchup_prior_gate_cache[cache_key] = model
        return model

    @staticmethod
    def _gate_total_bucket(value: float | None) -> str:
        if value is None or not math.isfinite(float(value)):
            return "unknown_total"
        total = float(value)
        if total < 42.0:
            return "low_total"
        if total < 47.0:
            return "mid_total"
        if total < 51.0:
            return "high_total"
        return "shootout_total"

    @staticmethod
    def _gate_implied_bucket(value: float | None) -> str:
        if value is None or not math.isfinite(float(value)):
            return "unknown_implied"
        implied = float(value)
        if implied < 21.0:
            return "low_implied"
        if implied < 24.0:
            return "mid_implied"
        if implied < 27.0:
            return "high_implied"
        return "elite_implied"

    @staticmethod
    def _gate_share_bucket(value: float | None, prefix: str) -> str:
        if value is None or not math.isfinite(float(value)):
            return f"{prefix}_unknown"
        share = float(value)
        if share < 0.25:
            return f"{prefix}_low"
        if share < 0.50:
            return f"{prefix}_medium"
        if share < 0.75:
            return f"{prefix}_high"
        return f"{prefix}_very_high"

    def _matchup_prior_gate_buckets(
        self,
        *,
        slate: str,
        players: list[PlayerPoolRow],
    ) -> dict[str, str]:
        skill_positions = {"QB", "RB", "WR", "TE"}
        skill_players = [player for player in players if player.position in skill_positions]
        totals = [
            float(player.game_total_line)
            for player in players
            if player.game_total_line is not None and math.isfinite(float(player.game_total_line))
        ]
        implied = [
            float(player.team_implied_total)
            for player in players
            if player.team_implied_total is not None and math.isfinite(float(player.team_implied_total))
        ]
        close_spread_players = [
            player
            for player in players
            if player.team_spread_line is not None
            and math.isfinite(float(player.team_spread_line))
            and abs(float(player.team_spread_line)) < 3.0
        ]
        high_total_skill = [
            player
            for player in skill_players
            if player.game_total_line is not None
            and math.isfinite(float(player.game_total_line))
            and float(player.game_total_line) >= 48.0
        ]
        favorite_skill = [
            player
            for player in skill_players
            if player.team_spread_line is not None
            and math.isfinite(float(player.team_spread_line))
            and float(player.team_spread_line) <= -3.0
        ]
        low_salary_skill = [
            player
            for player in skill_players
            if player.salary <= 4500
        ]

        player_count = max(len(players), 1)
        skill_count = max(len(skill_players), 1)
        close_spread_share = len(close_spread_players) / player_count
        high_total_skill_share = len(high_total_skill) / skill_count
        favorite_skill_share = len(favorite_skill) / skill_count
        low_salary_skill_share = len(low_salary_skill) / skill_count

        return {
            "slate": str(slate),
            "max_total_bucket": self._gate_total_bucket(max(totals) if totals else None),
            "max_implied_bucket": self._gate_implied_bucket(max(implied) if implied else None),
            "high_total_skill_share_bucket": self._gate_share_bucket(
                high_total_skill_share,
                "high_total_skill",
            ),
            "close_spread_share_bucket": self._gate_share_bucket(
                close_spread_share,
                "close_spread",
            ),
            "favorite_skill_share_bucket": self._gate_share_bucket(
                favorite_skill_share,
                "favorite_skill",
            ),
            "low_salary_skill_share_bucket": self._gate_share_bucket(
                low_salary_skill_share,
                "low_salary_skill",
            ),
        }

    def _effective_matchup_prior_strength(
        self,
        *,
        requested_strength: float,
        gate_model: MatchupPriorGateModel | None,
        slate: str,
        players: list[PlayerPoolRow],
    ) -> tuple[float, float | None, bool | None]:
        strength = _clamp(float(requested_strength), 0.0, 1.0)
        if strength <= 0.0 or gate_model is None:
            return strength, None, None
        buckets = self._matchup_prior_gate_buckets(slate=slate, players=players)
        score = 0.0
        for rule in gate_model.rules:
            if buckets.get(rule.bucket_name) == rule.bucket_value:
                score += float(rule.weight)
        active = score >= float(gate_model.threshold)
        return (strength if active else 0.0), float(score), bool(active)

    def _classic_player_prior_raw(
        self,
        player: PlayerPoolRow,
        model: ClassicValueDriverModel,
    ) -> float:
        raw = float(model.position_multipliers.get(player.position, 1.0))
        if player.position == "RB":
            spread_bucket = _spread_role_bucket(player.team_spread_line)
            raw *= float(model.rb_spread_role_multipliers.get(spread_bucket, 1.0))
        if (
            player.game_total_line is not None
            and math.isfinite(float(player.game_total_line))
            and float(player.game_total_line) >= model.high_total_threshold
        ):
            raw *= float(model.high_total_player_boost)
        return _clamp(raw, 0.55, 1.85)

    def _classic_player_sampling_multipliers(
        self,
        *,
        players: list[PlayerPoolRow],
        model: ClassicValueDriverModel | None,
        prior_strength: float,
    ) -> dict[str, float] | None:
        if model is None:
            return None
        strength = _clamp(float(prior_strength), 0.0, 1.0)
        if strength <= 0.0:
            return None
        multipliers: dict[str, float] = {}
        for player in players:
            raw = self._classic_player_prior_raw(player, model)
            multipliers[player.uid] = _clamp((1.0 - strength) + (strength * raw), 0.40, 2.40)
        return multipliers

    def _projection_feature_payload_for_player(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
        player: PlayerPoolRow,
    ) -> dict[str, Any]:
        feature_key = (source_system, season, week, slate)
        feature_cache = self._projection_feature_cache.get(feature_key, {})
        feature = (
            feature_cache.get(player.player_master_id or "")
            or feature_cache.get(player.source_player_key or "")
        )
        if feature is not None:
            return feature
        return {
            "position": player.position,
            "team": _canonical_team(player.team),
            "opponent": _canonical_team(player.opponent),
            "salary": int(player.salary),
            "game_total_line": player.game_total_line,
            "team_spread_line": player.team_spread_line,
            "team_skill_out_count": 0,
        }

    def _matchup_outcome_player_prior_raw(
        self,
        *,
        player: PlayerPoolRow,
        model: MatchupOutcomeIntelligenceModel,
        feature: dict[str, Any],
    ) -> float:
        position = (player.position or "").strip().upper()
        team = _canonical_team(player.team)
        opponent = _canonical_team(player.opponent)
        total_band = _total_band_bucket(_safe_float(feature.get("game_total_line")))
        spread_role = _spread_role_bucket(_safe_float(feature.get("team_spread_line")))
        salary_tier = _salary_tier_bucket(position, int(player.salary))
        teammate_band = _teammate_out_bucket(int(feature.get("team_skill_out_count") or 0))

        total_spread_lift = float(model.total_spread_lifts.get((position, total_band, spread_role), 0.0))
        salary_teammate_lift = float(model.salary_teammate_lifts.get((position, salary_tier, teammate_band), 0.0))
        matchup_cell_lift = 0.0
        if team and opponent:
            matchup_cell_lift = float(model.matchup_cell_lifts.get((position, team, opponent), 0.0))

        combined_lift = (
            (0.30 * total_spread_lift)
            + (0.25 * salary_teammate_lift)
            + (0.55 * matchup_cell_lift)
        )
        return _clamp(1.0 + (4.0 * combined_lift), 0.70, 1.40)

    def _matchup_outcome_player_raw_map(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
        players: list[PlayerPoolRow],
        model: MatchupOutcomeIntelligenceModel | None,
    ) -> dict[str, float] | None:
        if model is None or not players:
            return None
        raw_map: dict[str, float] = {}
        for player in players:
            feature = self._projection_feature_payload_for_player(
                source_system=source_system,
                season=season,
                week=week,
                slate=slate,
                player=player,
            )
            raw_map[player.uid] = self._matchup_outcome_player_prior_raw(
                player=player,
                model=model,
                feature=feature,
            )
        return raw_map

    def _sampling_multipliers_from_raw_map(
        self,
        *,
        raw_map: dict[str, float] | None,
        strength: float,
    ) -> dict[str, float] | None:
        if raw_map is None:
            return None
        bounded_strength = _clamp(float(strength), 0.0, 1.0)
        if bounded_strength <= 0.0:
            return None
        return {
            uid: _clamp((1.0 - bounded_strength) + (bounded_strength * raw), 0.40, 2.40)
            for uid, raw in raw_map.items()
        }

    def _merge_sampling_multipliers(
        self,
        *maps: dict[str, float] | None,
    ) -> dict[str, float] | None:
        merged: dict[str, float] = {}
        for values in maps:
            if values is None:
                continue
            for uid, multiplier in values.items():
                existing = merged.get(uid, 1.0)
                merged[uid] = _clamp(existing * float(multiplier), 0.30, 3.00)
        return merged or None

    def _classic_lineup_prior_score(
        self,
        *,
        lineup: list[PlayerPoolRow],
        model: ClassicValueDriverModel,
    ) -> float:
        if not lineup:
            return 1.0
        player_raw = [self._classic_player_prior_raw(player, model) for player in lineup]
        player_factor = float(np.mean(player_raw)) if player_raw else 1.0

        offense = [player for player in lineup if player.position != "DST"]
        high_total_count = sum(
            1
            for player in offense
            if (
                player.game_total_line is not None
                and math.isfinite(float(player.game_total_line))
                and float(player.game_total_line) >= model.high_total_threshold
            )
        )
        high_total_ratio = float(high_total_count / len(offense)) if offense else 0.0
        high_total_factor = 1.0 + (0.80 * (high_total_ratio - model.high_total_baseline_share))
        high_total_factor = _clamp(high_total_factor, 0.70, 1.40)

        counts = Counter(player.position for player in lineup)
        flex_position = "TE"
        if counts.get("RB", 0) > 2:
            flex_position = "RB"
        elif counts.get("WR", 0) > 3:
            flex_position = "WR"
        elif counts.get("TE", 0) > 1:
            flex_position = "TE"
        flex_factor = float(model.flex_position_multipliers.get(flex_position, 1.0))

        return _clamp(player_factor * high_total_factor * flex_factor, 0.25, 3.0)

    def _classic_lineup_prior_scores(
        self,
        *,
        lineups: list[list[PlayerPoolRow]],
        model: ClassicValueDriverModel | None,
    ) -> np.ndarray | None:
        if model is None or not lineups:
            return None
        return np.asarray(
            [self._classic_lineup_prior_score(lineup=lineup, model=model) for lineup in lineups],
            dtype=float,
        )

    def _apply_classic_prior_to_composite(
        self,
        *,
        composite_scores: np.ndarray,
        prior_scores: np.ndarray | None,
        prior_strength: float,
    ) -> np.ndarray:
        if prior_scores is None:
            return composite_scores
        strength = _clamp(float(prior_strength), 0.0, 1.0)
        if strength <= 0.0:
            return composite_scores
        if prior_scores.shape[0] != composite_scores.shape[0]:
            return composite_scores
        weight = 0.22 * strength
        return composite_scores + (weight * _zscore(prior_scores))

    def _matchup_outcome_lineup_prior_scores(
        self,
        *,
        lineups: list[list[PlayerPoolRow]],
        raw_map: dict[str, float] | None,
    ) -> np.ndarray | None:
        if raw_map is None or not lineups:
            return None
        values: list[float] = []
        for lineup in lineups:
            player_raw = [float(raw_map.get(player.uid, 1.0)) for player in lineup]
            values.append(float(np.mean(player_raw)) if player_raw else 1.0)
        return np.asarray(values, dtype=float)

    def _apply_matchup_outcome_prior_to_composite(
        self,
        *,
        composite_scores: np.ndarray,
        prior_scores: np.ndarray | None,
        prior_strength: float,
    ) -> np.ndarray:
        if prior_scores is None:
            return composite_scores
        strength = _clamp(float(prior_strength), 0.0, 1.0)
        if strength <= 0.0:
            return composite_scores
        if prior_scores.shape[0] != composite_scores.shape[0]:
            return composite_scores
        weight = 0.18 * strength
        return composite_scores + (weight * _zscore(prior_scores))

    def _showdown_lineup_features(self, lineup: ShowdownLineup) -> np.ndarray:
        captain = lineup.captain
        flex = lineup.flex_players
        salary_used = float(self._showdown_salary_used(lineup))
        salary_left = float(SHOWDOWN_SALARY_CAP - salary_used)
        captain_salary = float(captain.captain_salary)

        flex_counts: dict[str, int] = defaultdict(int)
        team_counts: dict[str, int] = defaultdict(int)
        for player in [captain, *flex]:
            if player.team:
                team_counts[player.team] += 1
        for player in flex:
            flex_counts[player.position] += 1

        same_team_as_captain = float(sum(1 for player in flex if captain.team and player.team == captain.team))
        opponent_team_count = float(sum(1 for player in flex if captain.opponent and player.team == captain.opponent))
        unique_teams = float(len(team_counts))

        captain_value = float(
            captain.projected_mean_points / max(1.0, captain.captain_salary / 1000.0)
        )
        game_total_line = float(captain.game_total_line or 0.0)
        game_spread_abs = float(abs(captain.team_spread_line or 0.0))
        captain_team_implied_total = float(captain.team_implied_total or 0.0)
        captain_opp_implied_total = float(captain.opponent_implied_total or 0.0)
        captain_has_vegas_line = 1.0 if captain.game_total_line is not None and captain.team_spread_line is not None else 0.0

        return np.asarray(
            [
                salary_used,
                salary_left,
                captain_salary,
                1.0 if captain.position == "QB" else 0.0,
                1.0 if captain.position == "RB" else 0.0,
                1.0 if captain.position == "WR" else 0.0,
                1.0 if captain.position == "TE" else 0.0,
                1.0 if captain.position == "K" else 0.0,
                1.0 if captain.position == "DST" else 0.0,
                float(flex_counts.get("QB", 0)),
                float(flex_counts.get("RB", 0)),
                float(flex_counts.get("WR", 0)),
                float(flex_counts.get("TE", 0)),
                float(flex_counts.get("K", 0)),
                float(flex_counts.get("DST", 0)),
                same_team_as_captain,
                opponent_team_count,
                unique_teams,
                self._showdown_projected_mean(lineup),
                self._showdown_projected_p90(lineup),
                float(captain.projected_mean_points),
                float(captain.projected_p90_points),
                captain_value,
                game_total_line,
                game_spread_abs,
                captain_team_implied_total,
                captain_opp_implied_total,
                captain_has_vegas_line,
            ],
            dtype=float,
        )

    def _fetch_showdown_player_pool(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
        projection_lookup: dict[str, tuple[float, float]] | None = None,
        dst_projection_lookup: dict[str, tuple[float, float]] | None = None,
    ) -> list[ShowdownPlayerPoolRow]:
        salary_rows = self.session.execute(
            select(CuratedSalary).where(
                and_(
                    CuratedSalary.source_system == source_system,
                    CuratedSalary.season == season,
                    CuratedSalary.week == week,
                    CuratedSalary.slate == slate,
                )
            )
        ).scalars().all()
        if not salary_rows:
            return []

        dst_points_by_team = self._compute_dst_actual_points(season=season, week=week)
        game_context_by_team = self._game_context_by_team(season=season, week=week)
        projection_feature_cache = self._projection_feature_cache.get(
            (source_system, season, week, slate),
            {},
        )

        actual_points_by_master: dict[str, float] = {}
        master_ids = sorted({row.player_master_id for row in salary_rows if row.player_master_id})
        if master_ids:
            alias_rows = self.session.execute(
                select(PlayerAlias.player_master_id, PlayerAlias.source_key).where(
                    and_(
                        PlayerAlias.source_system == "nflreadpy",
                        PlayerAlias.player_master_id.in_(master_ids),
                    )
                )
            ).all()
            player_id_to_masters: dict[str, set[str]] = defaultdict(set)
            for player_master_id, source_key in alias_rows:
                if source_key:
                    player_id_to_masters[source_key].add(player_master_id)
            tracked_player_ids = sorted(player_id_to_masters.keys())

            if tracked_player_ids:
                stats_rows = self.session.execute(
                    select(RawNflWeeklyStat).where(
                        and_(
                            RawNflWeeklyStat.season == season,
                            RawNflWeeklyStat.week == week,
                            RawNflWeeklyStat.player_id.in_(tracked_player_ids),
                        )
                    )
                ).scalars().all()
                for stat_row in stats_rows:
                    if not stat_row.player_id:
                        continue
                    points = _calculate_dk_player_points(stat_row.raw_row_json or {}, stat_row.position)
                    if not math.isfinite(points):
                        continue
                    for master_id in player_id_to_masters.get(stat_row.player_id, set()):
                        actual_points_by_master[master_id] = max(actual_points_by_master.get(master_id, 0.0), points)

        grouped: dict[str, dict[str, CuratedSalary]] = {}
        for row in salary_rows:
            salary_value = int(row.salary or 0)
            if salary_value <= 0:
                continue
            uid = row.player_master_id or row.source_player_key or f"{row.normalized_name}:{row.team}:{row.position}"
            if not uid:
                continue
            slot = (row.roster_position or "").strip().upper()
            slot_key = "cpt" if slot in SHOWDOWN_ROSTER_TAGS else "flex"
            bucket = grouped.setdefault(uid, {})
            existing = bucket.get(slot_key)
            if existing is None or int(existing.salary or 0) < salary_value:
                bucket[slot_key] = row

        pool: list[ShowdownPlayerPoolRow] = []
        for uid, bucket in grouped.items():
            flex_row = bucket.get("flex")
            captain_row = bucket.get("cpt")
            if flex_row is None:
                continue

            flex_salary = int(flex_row.salary or 0)
            captain_salary = int(captain_row.salary or 0) if captain_row is not None else int(round(flex_salary * 1.5))
            if flex_salary <= 0 or captain_salary <= 0:
                continue

            position = self._normalize_showdown_position(flex_row.position)
            team_key = _canonical_team(flex_row.team)
            opponent_key = _canonical_team(flex_row.opponent)
            context = game_context_by_team.get(team_key or "", {})

            points = actual_points_by_master.get(flex_row.player_master_id or "", 0.0)
            projected_mean = 0.0
            projected_p90 = 0.0
            for key in [flex_row.player_master_id, flex_row.source_player_key]:
                if not key or projection_lookup is None:
                    continue
                if key in projection_lookup:
                    projected_mean, projected_p90 = projection_lookup[key]
                    break
            if position == "DST":
                points = dst_points_by_team.get(team_key or "", 0.0)
                if dst_projection_lookup and team_key and team_key in dst_projection_lookup:
                    projected_mean, projected_p90 = dst_projection_lookup[team_key]
            projection_feature = (
                projection_feature_cache.get(flex_row.player_master_id or "")
                or projection_feature_cache.get(flex_row.source_player_key or "")
                or {}
            )

            pool.append(
                ShowdownPlayerPoolRow(
                    uid=uid,
                    name=flex_row.player_name,
                    team=team_key,
                    opponent=opponent_key,
                    position=position,
                    flex_salary=flex_salary,
                    captain_salary=captain_salary,
                    actual_points=float(points),
                    projected_mean_points=float(projected_mean),
                    projected_p90_points=float(projected_p90),
                    game_total_line=_safe_float(context.get("game_total_line")),
                    team_spread_line=_safe_float(context.get("team_spread_line")),
                    team_implied_total=_safe_float(context.get("team_implied_total")),
                    opponent_implied_total=_safe_float(context.get("opponent_implied_total")),
                    player_injury_status=str(
                        projection_feature.get("player_injury_status") or "unknown"
                    ),
                    team_skill_out_count=int(
                        projection_feature.get("team_skill_out_count") or 0
                    ),
                    team_position_out_count=int(
                        projection_feature.get("team_position_out_count") or 0
                    ),
                    player_master_id=flex_row.player_master_id,
                    source_player_key=flex_row.source_player_key,
                )
            )
        return pool

    def _showdown_lineup_satisfies_rules(self, lineup: ShowdownLineup) -> bool:
        return _showdown_lineup_satisfies_rules(lineup)

    def optimize_actual_showdown_lineup(
        self,
        *,
        players: list[ShowdownPlayerPoolRow],
    ) -> tuple[ShowdownLineup, float, int] | None:
        if len(players) < 6:
            return None

        if HAS_PULP:
            captain_vars: dict[int, LpVariable] = {
                idx: LpVariable(f"cpt_{idx}", lowBound=0, upBound=1, cat=LpBinary)
                for idx in range(len(players))
            }
            flex_vars: dict[int, LpVariable] = {
                idx: LpVariable(f"flex_{idx}", lowBound=0, upBound=1, cat=LpBinary)
                for idx in range(len(players))
            }
            model = LpProblem("optimal_actual_showdown_lineup", LpMaximize)
            model += lpSum(
                (1.5 * float(players[idx].actual_points) * captain_vars[idx])
                + (float(players[idx].actual_points) * flex_vars[idx])
                for idx in range(len(players))
            )
            model += lpSum(captain_vars[idx] for idx in range(len(players))) == 1
            model += lpSum(flex_vars[idx] for idx in range(len(players))) == 5
            for idx in range(len(players)):
                model += captain_vars[idx] + flex_vars[idx] <= 1
            model += lpSum(
                (int(players[idx].captain_salary) * captain_vars[idx])
                + (int(players[idx].flex_salary) * flex_vars[idx])
                for idx in range(len(players))
            ) <= SHOWDOWN_SALARY_CAP

            team_map: dict[str, list[int]] = defaultdict(list)
            for idx, row in enumerate(players):
                if row.team:
                    team_map[row.team].append(idx)
            for team_indices in team_map.values():
                model += lpSum(captain_vars[idx] + flex_vars[idx] for idx in team_indices) <= 5

            status = model.solve(PULP_CBC_CMD(msg=False))
            if LpStatus.get(status) != "Optimal":
                return None

            captain_idx = next(
                (idx for idx in range(len(players)) if value(captain_vars[idx]) and value(captain_vars[idx]) > 0.5),
                None,
            )
            flex_idx = [
                idx
                for idx in range(len(players))
                if value(flex_vars[idx]) and value(flex_vars[idx]) > 0.5
            ]
            if captain_idx is None or len(flex_idx) != 5:
                return None
            lineup = ShowdownLineup(
                captain=players[captain_idx],
                flex_players=[players[idx] for idx in flex_idx],
            )
            if not self._showdown_lineup_satisfies_rules(lineup):
                return None
            return lineup, self._showdown_actual_points(lineup), self._showdown_salary_used(lineup)

        sorted_players = sorted(players, key=lambda row: row.actual_points, reverse=True)
        if len(sorted_players) < 6:
            return None
        captain = sorted_players[0]
        flex = sorted_players[1:6]
        lineup = ShowdownLineup(captain=captain, flex_players=flex)
        if not self._showdown_lineup_satisfies_rules(lineup):
            return None
        return lineup, self._showdown_actual_points(lineup), self._showdown_salary_used(lineup)

    def _generate_showdown_lineups_for_slate(
        self,
        *,
        players: list[ShowdownPlayerPoolRow],
        lineups_target: int,
        rng: np.random.Generator,
        captain_position_probs: dict[str, float] | None = None,
        captain_prior_strength: float = 0.0,
    ) -> tuple[np.ndarray, np.ndarray, list[ShowdownLineup]]:
        if len(players) < 6:
            raise ValueError("Insufficient showdown player pool for lineup construction.")

        weights = np.asarray(
            [
                max(0.5, row.projected_p90_points + (0.5 * row.projected_mean_points))
                for row in players
            ],
            dtype=float,
        )
        if captain_position_probs and captain_prior_strength > 0:
            strength = float(min(max(captain_prior_strength, 0.0), 1.0))
            class_scale = float(max(len(captain_position_probs), 1))
            captain_bias_factors = np.asarray(
                [
                    max(
                        0.05,
                        float(captain_position_probs.get(str(row.position).upper(), 0.0)) * class_scale,
                    )
                    for row in players
                ],
                dtype=float,
            )
            weights = weights * ((1.0 - strength) + (strength * captain_bias_factors))
        if float(np.sum(weights)) <= 0:
            weights = np.ones(len(players), dtype=float)
        weights = weights / np.sum(weights)

        feature_rows: list[np.ndarray] = []
        point_rows: list[float] = []
        generated_lineups: list[ShowdownLineup] = []
        seen_keys: set[str] = set()
        attempts = 0
        max_attempts = max(lineups_target * 30, 25000)
        min_salary_floor = SHOWDOWN_MIN_SALARY_FLOOR

        while len(feature_rows) < lineups_target and attempts < max_attempts:
            attempts += 1
            cpt_idx = int(rng.choice(len(players), p=weights))
            captain = players[cpt_idx]
            flex_candidates = [row for row in players if row.uid != captain.uid]
            if len(flex_candidates) < 5:
                continue
            flex_weights = np.asarray(
                [max(0.5, row.projected_p90_points + (0.4 * row.projected_mean_points)) for row in flex_candidates],
                dtype=float,
            )
            if float(np.sum(flex_weights)) <= 0:
                flex_weights = np.ones(len(flex_candidates), dtype=float)
            flex_weights = flex_weights / np.sum(flex_weights)
            flex_idx = rng.choice(len(flex_candidates), size=5, replace=False, p=flex_weights)
            flex_players = [flex_candidates[int(idx)] for idx in flex_idx]
            lineup = ShowdownLineup(captain=captain, flex_players=flex_players)
            if not self._showdown_lineup_satisfies_rules(lineup):
                continue

            salary_used = self._showdown_salary_used(lineup)
            if salary_used < min_salary_floor:
                continue
            key = self._showdown_lineup_key(lineup)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            feature_rows.append(self._showdown_lineup_features(lineup))
            point_rows.append(self._showdown_actual_points(lineup))
            generated_lineups.append(lineup)

        if len(feature_rows) < 120 and min_salary_floor > 0:
            min_salary_floor = 0
            while len(feature_rows) < lineups_target and attempts < (max_attempts * 2):
                attempts += 1
                cpt_idx = int(rng.choice(len(players), p=weights))
                captain = players[cpt_idx]
                flex_candidates = [row for row in players if row.uid != captain.uid]
                if len(flex_candidates) < 5:
                    continue
                flex_weights = np.asarray(
                    [max(0.5, row.projected_p90_points + (0.4 * row.projected_mean_points)) for row in flex_candidates],
                    dtype=float,
                )
                if float(np.sum(flex_weights)) <= 0:
                    flex_weights = np.ones(len(flex_candidates), dtype=float)
                flex_weights = flex_weights / np.sum(flex_weights)
                flex_idx = rng.choice(len(flex_candidates), size=5, replace=False, p=flex_weights)
                flex_players = [flex_candidates[int(idx)] for idx in flex_idx]
                lineup = ShowdownLineup(captain=captain, flex_players=flex_players)
                if not self._showdown_lineup_satisfies_rules(lineup):
                    continue
                key = self._showdown_lineup_key(lineup)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                feature_rows.append(self._showdown_lineup_features(lineup))
                point_rows.append(self._showdown_actual_points(lineup))
                generated_lineups.append(lineup)

        if len(feature_rows) < 120:
            raise ValueError("No valid showdown lineups generated for this slate.")
        return np.vstack(feature_rows), np.asarray(point_rows, dtype=float), generated_lineups

    def _sample_weighted_unique(
        self,
        rows: list[PlayerPoolRow],
        count: int,
        selected: set[str],
        rng: np.random.Generator,
        weight_multipliers: dict[str, float] | None = None,
    ) -> list[PlayerPoolRow] | None:
        eligible = [row for row in rows if row.uid not in selected]
        if len(eligible) < count:
            return None
        weights = np.asarray([max(1000, row.salary) ** 0.6 for row in eligible], dtype=float)
        if weight_multipliers:
            weights = weights * np.asarray(
                [max(0.05, float(weight_multipliers.get(row.uid, 1.0))) for row in eligible],
                dtype=float,
            )
        weights = weights / np.sum(weights)
        idxs = rng.choice(len(eligible), size=count, replace=False, p=weights)
        return [eligible[int(idx)] for idx in idxs]

    def _lineup_features(self, lineup: list[PlayerPoolRow]) -> np.ndarray:
        qb = next(row for row in lineup if row.position == "QB")
        offense = [row for row in lineup if row.position != "DST"]
        skill = [row for row in offense if row.position != "QB"]
        salary_used = float(sum(row.salary for row in lineup))
        salary_left = float(DK_SALARY_CAP - salary_used)
        avg_salary = salary_used / len(lineup)
        lineup_projected_mean = float(sum(row.projected_mean_points for row in lineup))
        lineup_projected_p90 = float(sum(row.projected_p90_points for row in lineup))
        qb_team = qb.team
        qb_opp = qb.opponent
        qb_team_skill = [row for row in skill if qb_team and row.team == qb_team]
        qb_team_receivers = [row for row in qb_team_skill if row.position in {"WR", "TE"}]
        qb_opp_players = [row for row in skill if qb_opp and row.team == qb_opp]
        game_stack_size = sum(
            1
            for row in offense
            if (qb_team and row.team == qb_team) or (qb_opp and row.team == qb_opp)
        )
        team_counts: dict[str, int] = defaultdict(int)
        for row in offense:
            if row.team:
                team_counts[row.team] += 1
        max_team = float(max(team_counts.values())) if team_counts else 0.0
        unique_teams = float(len(team_counts))
        cheap_count = float(sum(1 for row in lineup if row.salary <= 4500))
        value_count = float(sum(1 for row in lineup if 4500 < row.salary <= 6500))
        stud_count = float(sum(1 for row in lineup if row.salary >= 7000))
        double_stack = 1.0 if len(qb_team_receivers) >= 2 else 0.0
        bringback = 1.0 if len(qb_opp_players) >= 1 else 0.0
        qb_total_line = float(qb.game_total_line or 0.0)
        qb_spread_abs = float(abs(qb.team_spread_line or 0.0))
        qb_team_implied_total = float(qb.team_implied_total or 0.0)
        qb_opp_implied_total = float(qb.opponent_implied_total or 0.0)
        qb_has_vegas_line = 1.0 if qb.game_total_line is not None and qb.team_spread_line is not None else 0.0
        close_spread_strength = 1.0 / (1.0 + qb_spread_abs)
        lineup_projected_value = lineup_projected_mean / max(salary_used / 1000.0, 1.0)
        offense_with_total = [
            row
            for row in offense
            if row.game_total_line is not None and math.isfinite(float(row.game_total_line))
        ]
        high_total_offense = [
            row for row in offense_with_total if float(row.game_total_line) >= 48.0
        ]
        high_total_offense_share = float(len(high_total_offense) / len(offense)) if offense else 0.0
        offense_vegas_coverage = float(len(offense_with_total) / len(offense)) if offense else 0.0
        running_backs = [row for row in lineup if row.position == "RB"]
        running_backs_with_spread = [
            row
            for row in running_backs
            if row.team_spread_line is not None and math.isfinite(float(row.team_spread_line))
        ]
        rb_avg_team_spread = (
            float(np.mean([float(row.team_spread_line) for row in running_backs_with_spread]))
            if running_backs_with_spread
            else 0.0
        )
        rb_underdog_share = (
            float(
                sum(1 for row in running_backs_with_spread if float(row.team_spread_line) >= 3.0)
                / len(running_backs_with_spread)
            )
            if running_backs_with_spread
            else 0.0
        )
        rb_spread_coverage = (
            float(len(running_backs_with_spread) / len(running_backs))
            if running_backs
            else 0.0
        )
        position_counts = Counter(row.position for row in lineup)
        flex_position = "TE"
        if position_counts.get("RB", 0) > 2:
            flex_position = "RB"
        elif position_counts.get("WR", 0) > 3:
            flex_position = "WR"

        features = np.asarray(
            [
                salary_used,
                salary_left,
                avg_salary,
                float(len(qb_team_receivers)),
                float(len(qb_team_skill)),
                float(len(qb_opp_players)),
                float(game_stack_size),
                max_team,
                unique_teams,
                cheap_count,
                value_count,
                stud_count,
                double_stack,
                bringback,
                lineup_projected_mean,
                lineup_projected_p90,
                qb_total_line,
                qb_spread_abs,
                qb_team_implied_total,
                qb_opp_implied_total,
                qb_has_vegas_line,
                double_stack * qb_total_line,
                bringback * qb_total_line,
                float(game_stack_size) * qb_total_line,
                double_stack * close_spread_strength,
                bringback * close_spread_strength,
                lineup_projected_value,
                high_total_offense_share,
                offense_vegas_coverage,
                rb_avg_team_spread,
                rb_underdog_share,
                rb_spread_coverage,
                1.0 if flex_position == "RB" else 0.0,
                1.0 if flex_position == "WR" else 0.0,
                1.0 if flex_position == "TE" else 0.0,
            ],
            dtype=float,
        )
        if self._disabled_classic_feature_indices:
            features[list(self._disabled_classic_feature_indices)] = 0.0
        return features

    def _qb_game_stack_archetype(self, lineup: list[PlayerPoolRow]) -> tuple[str, str | None]:
        qb = next((row for row in lineup if row.position == "QB"), None)
        if qb is None:
            return "unknown", None
        skill = [row for row in lineup if row.position in {"RB", "WR", "TE"}]
        qb_team_receivers = sum(
            1 for row in skill if qb.team and row.team == qb.team and row.position in {"WR", "TE"}
        )
        bringback = 1 if any(qb.opponent and row.team == qb.opponent for row in skill) else 0
        if qb_team_receivers >= 2 and bringback:
            archetype = "double_with_bringback"
        elif qb_team_receivers >= 2:
            archetype = "double_no_bringback"
        elif qb_team_receivers == 1 and bringback:
            archetype = "single_with_bringback"
        elif qb_team_receivers == 1:
            archetype = "single_no_bringback"
        else:
            archetype = "naked_qb"
        if qb.team and qb.opponent:
            matchup_key = "@".join(sorted([qb.team, qb.opponent]))
        else:
            matchup_key = None
        return archetype, matchup_key

    def _summarize_matchup_stack_rules(
        self,
        *,
        candidate_lineups: list[list[PlayerPoolRow]],
        ranking_scores: np.ndarray,
    ) -> list[str]:
        by_matchup: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for idx, lineup in enumerate(candidate_lineups):
            archetype, matchup_key = self._qb_game_stack_archetype(lineup)
            if matchup_key is None:
                continue
            by_matchup[matchup_key][archetype].append(float(ranking_scores[idx]))

        min_samples = max(40, len(candidate_lineups) // 2000)
        rules: list[tuple[str, str, float, int]] = []
        for matchup_key, archetype_map in by_matchup.items():
            best_name: str | None = None
            best_mean = -1.0
            best_n = 0
            for archetype, values in archetype_map.items():
                n = len(values)
                if n < min_samples:
                    continue
                mean_score = float(np.mean(values))
                if mean_score > best_mean:
                    best_name = archetype
                    best_mean = mean_score
                    best_n = n
            if best_name is not None:
                rules.append((matchup_key, best_name, best_mean, best_n))

        rules.sort(key=lambda row: row[2], reverse=True)
        summary: list[str] = []
        for matchup_key, archetype, mean_score, sample_n in rules[:8]:
            summary.append(
                f"Matchup stack rule ({matchup_key}): {archetype} (learned score {mean_score:.4f}, n={sample_n})."
            )
        return summary

    def _player_conflicts_with_dst(self, player: PlayerPoolRow, dst: PlayerPoolRow) -> bool:
        if player.position == "DST":
            return False
        if dst.team and player.opponent and player.opponent == dst.team:
            return True
        if dst.opponent and player.team and player.team == dst.opponent:
            return True
        return False

    def _pareto_filter_players(self, players: list[PlayerPoolRow]) -> list[PlayerPoolRow]:
        if not players:
            return []
        ordered = sorted(players, key=lambda row: (int(row.salary), -float(row.actual_points)))
        kept: list[PlayerPoolRow] = []
        best_points = -1e18
        for row in ordered:
            points = float(row.actual_points)
            if points > (best_points + 1e-9):
                kept.append(row)
                best_points = max(best_points, points)
        return kept

    def _position_dp_exact(
        self,
        *,
        players: list[PlayerPoolRow],
        max_pick: int,
        budget_units: int,
        salary_step: int,
    ) -> tuple[list[list[float]], list[list[tuple[PlayerPoolRow, ...] | None]]]:
        neg_inf = -1e18
        points: list[list[float]] = [
            [neg_inf for _ in range(budget_units + 1)]
            for _ in range(max_pick + 1)
        ]
        choices: list[list[tuple[PlayerPoolRow, ...] | None]] = [
            [None for _ in range(budget_units + 1)]
            for _ in range(max_pick + 1)
        ]
        points[0][0] = 0.0
        choices[0][0] = ()

        for player in players:
            cost = int(player.salary // salary_step)
            gain = float(player.actual_points)
            if cost < 0 or cost > budget_units:
                continue
            for pick_count in range(max_pick - 1, -1, -1):
                cur_points_row = points[pick_count]
                nxt_points_row = points[pick_count + 1]
                cur_choice_row = choices[pick_count]
                nxt_choice_row = choices[pick_count + 1]
                for salary_units in range(budget_units - cost, -1, -1):
                    base = cur_points_row[salary_units]
                    if base <= neg_inf / 2:
                        continue
                    base_choice = cur_choice_row[salary_units]
                    if base_choice is None:
                        continue
                    next_salary = salary_units + cost
                    next_points = base + gain
                    if next_points > nxt_points_row[next_salary]:
                        nxt_points_row[next_salary] = next_points
                        nxt_choice_row[next_salary] = base_choice + (player,)

        return points, choices

    def optimize_actual_lineup(
        self,
        *,
        players: list[PlayerPoolRow],
    ) -> tuple[list[PlayerPoolRow], float, int] | None:
        if not players:
            return None

        if HAS_PULP:
            variables: dict[int, LpVariable] = {
                idx: LpVariable(f"p_{idx}", lowBound=0, upBound=1, cat=LpBinary)
                for idx in range(len(players))
            }
            model = LpProblem("optimal_actual_lineup", LpMaximize)
            model += lpSum(
                float(players[idx].actual_points) * variables[idx]
                for idx in range(len(players))
            )

            qb_idx = [idx for idx, row in enumerate(players) if row.position == "QB"]
            rb_idx = [idx for idx, row in enumerate(players) if row.position == "RB"]
            wr_idx = [idx for idx, row in enumerate(players) if row.position == "WR"]
            te_idx = [idx for idx, row in enumerate(players) if row.position == "TE"]
            dst_idx = [idx for idx, row in enumerate(players) if row.position == "DST"]
            skill_idx = rb_idx + wr_idx + te_idx
            offense_idx = qb_idx + skill_idx

            if not qb_idx or len(rb_idx) < 2 or len(wr_idx) < 3 or not te_idx or not dst_idx:
                return None

            model += lpSum(variables[idx] for idx in qb_idx) == 1
            model += lpSum(variables[idx] for idx in dst_idx) == 1
            model += lpSum(variables[idx] for idx in rb_idx) >= 2
            model += lpSum(variables[idx] for idx in wr_idx) >= 3
            model += lpSum(variables[idx] for idx in te_idx) >= 1
            model += lpSum(variables[idx] for idx in skill_idx) == 7
            model += lpSum(variables[idx] for idx in range(len(players))) == 9
            model += lpSum(int(players[idx].salary) * variables[idx] for idx in range(len(players))) <= DK_SALARY_CAP

            for offense_i in offense_idx:
                offense_player = players[offense_i]
                for dst_i in dst_idx:
                    dst_player = players[dst_i]
                    if self._player_conflicts_with_dst(offense_player, dst_player):
                        model += variables[offense_i] + variables[dst_i] <= 1

            status = model.solve(PULP_CBC_CMD(msg=False))
            status_name = LpStatus.get(status, "")
            if status_name in {"Optimal", "Integer Feasible"}:
                lineup = [
                    players[idx]
                    for idx in range(len(players))
                    if value(variables[idx]) is not None and value(variables[idx]) > 0.5
                ]
                if len(lineup) == 9 and _lineup_satisfies_roster_rules(lineup):
                    points = float(sum(float(row.actual_points) for row in lineup))
                    salary = int(sum(int(row.salary) for row in lineup))
                    return lineup, points, salary

        return self._optimize_actual_lineup_dp(players=players)

    def _optimize_actual_lineup_dp(
        self,
        *,
        players: list[PlayerPoolRow],
    ) -> tuple[list[PlayerPoolRow], float, int] | None:
        if not players:
            return None

        salaries = [int(row.salary) for row in players if int(row.salary) > 0]
        if not salaries:
            return None
        salary_step = 0
        for salary in salaries:
            salary_step = salary if salary_step == 0 else math.gcd(salary_step, salary)
        if salary_step <= 0:
            salary_step = 1
        cap_units = DK_SALARY_CAP // salary_step

        dst_pool = [row for row in players if row.position == "DST"]
        if not dst_pool:
            return None

        best_lineup: list[PlayerPoolRow] | None = None
        best_points = -1e18
        best_salary_used = 0

        for dst in dst_pool:
            dst_cost = int(dst.salary // salary_step)
            if dst_cost > cap_units:
                continue
            remaining_after_dst = cap_units - dst_cost

            qb_pool = [
                row for row in players
                if row.position == "QB" and not self._player_conflicts_with_dst(row, dst)
            ]
            rb_pool = [
                row for row in players
                if row.position == "RB" and not self._player_conflicts_with_dst(row, dst)
            ]
            wr_pool = [
                row for row in players
                if row.position == "WR" and not self._player_conflicts_with_dst(row, dst)
            ]
            te_pool = [
                row for row in players
                if row.position == "TE" and not self._player_conflicts_with_dst(row, dst)
            ]
            if len(qb_pool) < 1 or len(rb_pool) < 2 or len(wr_pool) < 3 or len(te_pool) < 1:
                continue

            rb_pool = self._pareto_filter_players(rb_pool)
            wr_pool = self._pareto_filter_players(wr_pool)
            te_pool = self._pareto_filter_players(te_pool)
            if len(rb_pool) < 2 or len(wr_pool) < 3 or len(te_pool) < 1:
                continue

            rb_points, rb_choices = self._position_dp_exact(
                players=rb_pool,
                max_pick=3,
                budget_units=remaining_after_dst,
                salary_step=salary_step,
            )
            wr_points, wr_choices = self._position_dp_exact(
                players=wr_pool,
                max_pick=4,
                budget_units=remaining_after_dst,
                salary_step=salary_step,
            )
            te_points, te_choices = self._position_dp_exact(
                players=te_pool,
                max_pick=2,
                budget_units=remaining_after_dst,
                salary_step=salary_step,
            )

            skill_exact_points = [-1e18 for _ in range(remaining_after_dst + 1)]
            skill_exact_choices: list[tuple[PlayerPoolRow, ...] | None] = [None for _ in range(remaining_after_dst + 1)]
            structures = [(2, 3, 2), (2, 4, 1), (3, 3, 1)]
            for rb_need, wr_need, te_need in structures:
                rw_points = [-1e18 for _ in range(remaining_after_dst + 1)]
                rw_choices: list[tuple[PlayerPoolRow, ...] | None] = [None for _ in range(remaining_after_dst + 1)]
                for rb_salary in range(remaining_after_dst + 1):
                    rb_val = rb_points[rb_need][rb_salary]
                    if rb_val <= -1e17:
                        continue
                    rb_choice = rb_choices[rb_need][rb_salary]
                    if rb_choice is None:
                        continue
                    max_wr_salary = remaining_after_dst - rb_salary
                    for wr_salary in range(max_wr_salary + 1):
                        wr_val = wr_points[wr_need][wr_salary]
                        if wr_val <= -1e17:
                            continue
                        wr_choice = wr_choices[wr_need][wr_salary]
                        if wr_choice is None:
                            continue
                        total_rw_salary = rb_salary + wr_salary
                        total_rw_points = rb_val + wr_val
                        if total_rw_points > rw_points[total_rw_salary]:
                            rw_points[total_rw_salary] = total_rw_points
                            rw_choices[total_rw_salary] = rb_choice + wr_choice

                te_prefix_points = [-1e18 for _ in range(remaining_after_dst + 1)]
                te_prefix_choices: list[tuple[PlayerPoolRow, ...] | None] = [None for _ in range(remaining_after_dst + 1)]
                running_te_points = -1e18
                running_te_choice: tuple[PlayerPoolRow, ...] | None = None
                for budget in range(remaining_after_dst + 1):
                    val = te_points[te_need][budget]
                    if val > running_te_points:
                        running_te_points = val
                        running_te_choice = te_choices[te_need][budget]
                    te_prefix_points[budget] = running_te_points
                    te_prefix_choices[budget] = running_te_choice

                for budget in range(remaining_after_dst + 1):
                    best_val = skill_exact_points[budget]
                    best_choice = skill_exact_choices[budget]
                    for rw_salary in range(budget + 1):
                        rw_val = rw_points[rw_salary]
                        if rw_val <= -1e17:
                            continue
                        te_val = te_prefix_points[budget - rw_salary]
                        if te_val <= -1e17:
                            continue
                        rw_choice = rw_choices[rw_salary]
                        te_choice = te_prefix_choices[budget - rw_salary]
                        if rw_choice is None or te_choice is None:
                            continue
                        total_val = rw_val + te_val
                        if total_val > best_val:
                            best_val = total_val
                            best_choice = rw_choice + te_choice
                    skill_exact_points[budget] = best_val
                    skill_exact_choices[budget] = best_choice

            skill_prefix_points = [-1e18 for _ in range(remaining_after_dst + 1)]
            skill_prefix_choices: list[tuple[PlayerPoolRow, ...] | None] = [None for _ in range(remaining_after_dst + 1)]
            running_points = -1e18
            running_choice: tuple[PlayerPoolRow, ...] | None = None
            for budget in range(remaining_after_dst + 1):
                val = skill_exact_points[budget]
                if val > running_points:
                    running_points = val
                    running_choice = skill_exact_choices[budget]
                skill_prefix_points[budget] = running_points
                skill_prefix_choices[budget] = running_choice

            for qb in qb_pool:
                qb_cost = int(qb.salary // salary_step)
                remaining_for_skills = remaining_after_dst - qb_cost
                if remaining_for_skills < 0:
                    continue
                skill_points = skill_prefix_points[remaining_for_skills]
                skill_choice = skill_prefix_choices[remaining_for_skills]
                if skill_points <= -1e17 or skill_choice is None:
                    continue
                lineup = [qb, *list(skill_choice), dst]
                if not _lineup_satisfies_roster_rules(lineup):
                    continue
                lineup_points = float(qb.actual_points + dst.actual_points + skill_points)
                lineup_salary_used = int(sum(row.salary for row in lineup))
                if lineup_salary_used > DK_SALARY_CAP:
                    continue
                if (
                    lineup_points > best_points
                    or (
                        abs(lineup_points - best_points) <= 1e-9
                        and lineup_salary_used > best_salary_used
                    )
                ):
                    best_points = lineup_points
                    best_salary_used = lineup_salary_used
                    best_lineup = lineup

        if best_lineup is None:
            return None
        return best_lineup, float(best_points), int(best_salary_used)

    def _generate_lineups_for_slate(
        self,
        *,
        players: list[PlayerPoolRow],
        lineups_target: int,
        rng: np.random.Generator,
        player_sampling_multipliers: dict[str, float] | None = None,
    ) -> tuple[np.ndarray, np.ndarray, list[list[PlayerPoolRow]]]:
        by_pos: dict[str, list[PlayerPoolRow]] = defaultdict(list)
        for player in players:
            by_pos[player.position].append(player)

        skill_pool_count = len(by_pos["RB"]) + len(by_pos["WR"]) + len(by_pos["TE"])
        if (
            len(by_pos["QB"]) < 1
            or len(by_pos["RB"]) < 2
            or len(by_pos["WR"]) < 3
            or len(by_pos["TE"]) < 1
            or len(by_pos["DST"]) < 1
            or skill_pool_count < 7
        ):
            raise ValueError("Insufficient position coverage for lineup generation.")

        feature_rows: list[np.ndarray] = []
        point_rows: list[float] = []
        generated_lineups: list[list[PlayerPoolRow]] = []
        lineup_keys: set[tuple[str, ...]] = set()
        max_attempts = max(lineups_target * 20, 8000)
        min_salary_floor = 43000
        attempts = 0
        while len(feature_rows) < lineups_target and attempts < max_attempts:
            attempts += 1
            selected: set[str] = set()
            qb_pick = self._sample_weighted_unique(
                by_pos["QB"],
                1,
                selected,
                rng,
                weight_multipliers=player_sampling_multipliers,
            )
            if qb_pick is None:
                continue
            selected.update(row.uid for row in qb_pick)
            rb_picks = self._sample_weighted_unique(
                by_pos["RB"],
                2,
                selected,
                rng,
                weight_multipliers=player_sampling_multipliers,
            )
            if rb_picks is None:
                continue
            selected.update(row.uid for row in rb_picks)
            wr_picks = self._sample_weighted_unique(
                by_pos["WR"],
                3,
                selected,
                rng,
                weight_multipliers=player_sampling_multipliers,
            )
            if wr_picks is None:
                continue
            selected.update(row.uid for row in wr_picks)
            te_pick = self._sample_weighted_unique(
                by_pos["TE"],
                1,
                selected,
                rng,
                weight_multipliers=player_sampling_multipliers,
            )
            if te_pick is None:
                continue
            selected.update(row.uid for row in te_pick)
            flex_pool = by_pos["RB"] + by_pos["WR"] + by_pos["TE"]
            flex_pick = self._sample_weighted_unique(
                flex_pool,
                1,
                selected,
                rng,
                weight_multipliers=player_sampling_multipliers,
            )
            if flex_pick is None:
                continue
            selected.update(row.uid for row in flex_pick)
            dst_pick = self._sample_weighted_unique(
                by_pos["DST"],
                1,
                selected,
                rng,
                weight_multipliers=player_sampling_multipliers,
            )
            if dst_pick is None:
                continue

            lineup = qb_pick + rb_picks + wr_picks + te_pick + flex_pick + dst_pick
            if not _lineup_satisfies_roster_rules(lineup):
                continue
            salary_total = sum(row.salary for row in lineup)
            if salary_total > DK_SALARY_CAP or salary_total < min_salary_floor:
                continue

            key = tuple(sorted(row.uid for row in lineup))
            if key in lineup_keys:
                continue
            lineup_keys.add(key)

            feature_rows.append(self._lineup_features(lineup))
            point_rows.append(float(sum(row.actual_points for row in lineup)))
            generated_lineups.append(lineup)

        # Add a small MILP projected-optimal seed only when random generation is sparse.
        if len(feature_rows) < max(120, lineups_target // 3):
            seed_count = max(20, min(lineups_target // 10, 60))
            seeded = self._optimize_top_projected_lineups(players=players, top_k=seed_count)
            for lineup, _obj, _salary in seeded:
                key = tuple(sorted(row.uid for row in lineup))
                if key in lineup_keys:
                    continue
                lineup_keys.add(key)
                feature_rows.append(self._lineup_features(lineup))
                point_rows.append(float(sum(row.actual_points for row in lineup)))
                generated_lineups.append(lineup)
                if len(feature_rows) >= lineups_target:
                    break

        # Final recovery path: use adaptive candidate generation to avoid false negatives.
        if len(feature_rows) < 120:
            try:
                adaptive = self._generate_candidate_lineups_adaptive(
                    players=players,
                    requested_lineups=max(240, lineups_target),
                    min_salary_floor=min_salary_floor,
                    rng=rng,
                    player_sampling_multipliers=player_sampling_multipliers,
                )
            except Exception:  # noqa: BLE001
                adaptive = []
            for lineup in adaptive:
                key = tuple(sorted(row.uid for row in lineup))
                if key in lineup_keys:
                    continue
                lineup_keys.add(key)
                feature_rows.append(self._lineup_features(lineup))
                point_rows.append(float(sum(row.actual_points for row in lineup)))
                generated_lineups.append(lineup)
                if len(feature_rows) >= lineups_target:
                    break

        if len(feature_rows) < 120:
            raise ValueError("No valid lineups generated for this slate.")

        return np.vstack(feature_rows), np.asarray(point_rows, dtype=float), generated_lineups

    def _compute_dst_projection_lookup(
        self,
        *,
        season: int,
        week: int,
    ) -> dict[str, tuple[float, float]]:
        cache_key = (season, week)
        cached = self._dst_projection_cache.get(cache_key)
        if cached is not None:
            return cached

        week_rows = self.session.execute(
            select(RawNflSchedule.season, RawNflSchedule.week)
            .where(
                or_(
                    RawNflSchedule.season < season,
                    and_(
                        RawNflSchedule.season == season,
                        RawNflSchedule.week < week,
                    ),
                )
            )
            .group_by(RawNflSchedule.season, RawNflSchedule.week)
        ).all()
        by_team: dict[str, list[float]] = defaultdict(list)
        for prior_season, prior_week in week_rows:
            if prior_week is None:
                continue
            try:
                points_map = self._compute_dst_actual_points(
                    season=int(prior_season),
                    week=int(prior_week),
                )
            except Exception:  # noqa: BLE001
                continue
            for team, points in points_map.items():
                by_team[team].append(float(points))

        lookup: dict[str, tuple[float, float]] = {}
        for team, values in by_team.items():
            if not values:
                continue
            arr = np.asarray(values, dtype=float)
            lookup[team] = (float(np.mean(arr)), float(np.percentile(arr, 90)))
        self._dst_projection_cache[cache_key] = lookup
        return lookup

    def _player_matchup_feature_vector_from_values(
        self,
        *,
        salary: int | None,
        is_home: bool | None,
        game_total_line: float | None,
        team_spread_line: float | None,
        team_implied_total: float | None,
        opponent_implied_total: float | None,
        player_games_history: int,
        player_roll3_mean: float | None,
        player_roll8_mean: float | None,
        player_roll8_std: float | None,
        player_vs_opp_roll4: float | None,
        defense_pos_allowed_roll3: float | None,
        defense_pos_allowed_roll8: float | None,
        defense_pos_allowed_p90_roll8: float | None,
        player_injury_status: str | None,
        team_skill_out_count: int,
        team_position_out_count: int,
        kickoff_bucket: str | None,
    ) -> np.ndarray:
        kickoff_early, kickoff_late, kickoff_prime, kickoff_unknown = _kickoff_bucket_flags(kickoff_bucket)
        vector = np.asarray(
            [
                float((salary or 0) / 1000.0),
                1.0 if bool(is_home) else 0.0,
                float(game_total_line if game_total_line is not None else 45.0),
                float(team_spread_line if team_spread_line is not None else 0.0),
                float(team_implied_total if team_implied_total is not None else 22.0),
                float(opponent_implied_total if opponent_implied_total is not None else 22.0),
                float(max(0, player_games_history)),
                float(player_roll3_mean if player_roll3_mean is not None else 0.0),
                float(player_roll8_mean if player_roll8_mean is not None else 0.0),
                float(player_roll8_std if player_roll8_std is not None else 0.0),
                float(player_vs_opp_roll4 if player_vs_opp_roll4 is not None else 0.0),
                float(defense_pos_allowed_roll3 if defense_pos_allowed_roll3 is not None else 0.0),
                float(defense_pos_allowed_roll8 if defense_pos_allowed_roll8 is not None else 0.0),
                float(defense_pos_allowed_p90_roll8 if defense_pos_allowed_p90_roll8 is not None else 0.0),
                float(_injury_status_score(player_injury_status)),
                float(max(0, team_skill_out_count)),
                float(max(0, team_position_out_count)),
                float(kickoff_early),
                float(kickoff_late),
                float(kickoff_prime),
                float(kickoff_unknown),
            ],
            dtype=float,
        )
        vector = np.where(np.isfinite(vector), vector, 0.0)
        return vector

    def _player_matchup_feature_vector_from_matrix_row(self, row: PlayerGameFeatureMatrix) -> np.ndarray:
        return self._player_matchup_feature_vector_from_values(
            salary=row.salary,
            is_home=row.is_home,
            game_total_line=row.game_total_line,
            team_spread_line=row.team_spread_line,
            team_implied_total=row.team_implied_total,
            opponent_implied_total=row.opponent_implied_total,
            player_games_history=row.player_games_history,
            player_roll3_mean=row.player_roll3_mean,
            player_roll8_mean=row.player_roll8_mean,
            player_roll8_std=row.player_roll8_std,
            player_vs_opp_roll4=row.player_vs_opp_roll4,
            defense_pos_allowed_roll3=row.defense_pos_allowed_roll3,
            defense_pos_allowed_roll8=row.defense_pos_allowed_roll8,
            defense_pos_allowed_p90_roll8=row.defense_pos_allowed_p90_roll8,
            player_injury_status=row.player_injury_status,
            team_skill_out_count=row.team_skill_out_count,
            team_position_out_count=row.team_position_out_count,
            kickoff_bucket=row.kickoff_bucket,
        )

    def _fit_player_matchup_models_from_matrix(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
    ) -> dict[str, PlayerMatchupProjectionModel]:
        cache_key = (source_system, season, week, slate)
        cached = self._matchup_model_cache.get(cache_key)
        if cached is not None:
            return cached

        time_filters = or_(
            PlayerGameFeatureMatrix.season < season,
            and_(
                PlayerGameFeatureMatrix.season == season,
                PlayerGameFeatureMatrix.week < week,
            ),
        )
        base_filters = [
            PlayerGameFeatureMatrix.source_system == source_system,
            PlayerGameFeatureMatrix.position.in_(["QB", "RB", "WR", "TE", "DST"]),
            time_filters,
        ]

        rows = self.session.execute(
            select(PlayerGameFeatureMatrix).where(and_(*base_filters, PlayerGameFeatureMatrix.slate == slate))
        ).scalars().all()
        if len(rows) < 1200:
            rows = self.session.execute(
                select(PlayerGameFeatureMatrix).where(and_(*base_filters))
            ).scalars().all()

        grouped_samples: dict[str, list[tuple[np.ndarray, float, int]]] = defaultdict(list)
        for row in rows:
            dk_points = _safe_float(row.dk_points)
            if dk_points is None:
                continue
            position = (row.position or "").strip().upper()
            if position not in {"QB", "RB", "WR", "TE", "DST"}:
                continue
            sample_ord = _slice_ordinal(int(row.season), int(row.week))
            grouped_samples[position].append(
                (
                    self._player_matchup_feature_vector_from_matrix_row(row),
                    float(dk_points),
                    sample_ord,
                )
            )

        models: dict[str, PlayerMatchupProjectionModel] = {}
        roll8_idx = PLAYER_MATCHUP_MODEL_FEATURE_NAMES.index("player_roll8_mean")
        for position, samples in grouped_samples.items():
            if len(samples) < 160:
                continue

            samples_sorted = sorted(samples, key=lambda item: item[2])
            split_idx = int(len(samples_sorted) * 0.8)
            split_idx = max(120, split_idx)
            split_idx = min(split_idx, len(samples_sorted) - 30)
            if split_idx < 120 or (len(samples_sorted) - split_idx) < 20:
                continue

            train_samples = samples_sorted[:split_idx]
            valid_samples = samples_sorted[split_idx:]

            x_train = np.vstack([item[0] for item in train_samples]).astype(float)
            y_train = np.asarray([item[1] for item in train_samples], dtype=float)
            x_valid = np.vstack([item[0] for item in valid_samples]).astype(float)
            y_valid = np.asarray([item[1] for item in valid_samples], dtype=float)

            x_mean = np.mean(x_train, axis=0)
            x_std = np.std(x_train, axis=0)
            x_std = np.where(x_std < 1e-6, 1.0, x_std)
            xs_train = (x_train - x_mean) / x_std
            xs_valid = (x_valid - x_mean) / x_std

            y_mean = float(np.mean(y_train))
            y_std = float(np.std(y_train))
            if y_std < 1e-6:
                continue
            ys_train = (y_train - y_mean) / y_std

            design = np.column_stack([xs_train, np.ones(xs_train.shape[0], dtype=float)])
            reg = 0.20
            gram = design.T @ design
            for idx in range(xs_train.shape[1]):
                gram[idx, idx] += reg
            rhs = design.T @ ys_train
            try:
                coeff = np.linalg.solve(gram, rhs)
            except np.linalg.LinAlgError:
                coeff = np.linalg.pinv(gram) @ rhs

            weights = coeff[: xs_train.shape[1]].astype(float)
            bias = float(coeff[xs_train.shape[1]])
            pred_norm_train = xs_train @ weights + bias
            pred_train = y_mean + (y_std * pred_norm_train)
            pred_norm_valid = xs_valid @ weights + bias
            pred_valid = y_mean + (y_std * pred_norm_valid)

            residual_std = float(np.std(y_valid - pred_valid))
            if not math.isfinite(residual_std) or residual_std < 1e-6:
                residual_std = float(np.std(y_train - pred_train))
            residual_std = max(2.5, residual_std)
            if not math.isfinite(residual_std):
                residual_std = 4.0

            baseline_valid = np.where(
                x_valid[:, roll8_idx] > 0,
                x_valid[:, roll8_idx],
                y_mean,
            )
            mae_model = float(np.mean(np.abs(y_valid - pred_valid)))
            mae_baseline = float(np.mean(np.abs(y_valid - baseline_valid)))
            improvement = 0.0
            if mae_baseline > 1e-6:
                improvement = (mae_baseline - mae_model) / mae_baseline
            enabled = bool(improvement > 0.005)
            blend_weight = 0.0
            if enabled:
                if improvement >= 0.12:
                    blend_weight = 0.75
                elif improvement >= 0.08:
                    blend_weight = 0.65
                elif improvement >= 0.04:
                    blend_weight = 0.5
                elif improvement >= 0.02:
                    blend_weight = 0.35
                else:
                    blend_weight = 0.2

            models[position] = PlayerMatchupProjectionModel(
                feature_names=list(PLAYER_MATCHUP_MODEL_FEATURE_NAMES),
                weights=weights,
                bias=bias,
                x_mean=x_mean,
                x_std=x_std,
                y_mean=y_mean,
                y_std=y_std,
                residual_std=residual_std,
                training_rows=int(len(y_train)),
                mae_model=mae_model,
                mae_baseline=mae_baseline,
                blend_weight=blend_weight,
                enabled=enabled,
            )

        self._matchup_model_cache[cache_key] = models
        return models

    def _predict_player_matchup_points(
        self,
        *,
        model: PlayerMatchupProjectionModel,
        feature_vector: np.ndarray,
    ) -> tuple[float, float]:
        xs = (feature_vector - model.x_mean) / model.x_std
        pred_norm = float(xs @ model.weights + model.bias)
        mean_points = float(model.y_mean + (model.y_std * pred_norm))
        p90_points = float(mean_points + (1.2815515655446004 * model.residual_std))
        return mean_points, p90_points

    def _compute_player_projection_lookup(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
    ) -> tuple[dict[str, tuple[float, float]], dict[str, tuple[float, float]]]:
        cache_key = (source_system, season, week, slate)
        cached = self._player_projection_cache.get(cache_key)
        if cached is not None:
            return cached

        salary_rows = self.session.execute(
            select(CuratedSalary).where(
                and_(
                    CuratedSalary.source_system == source_system,
                    CuratedSalary.season == season,
                    CuratedSalary.week == week,
                    CuratedSalary.slate == slate,
                )
            )
        ).scalars().all()
        if not salary_rows:
            empty = ({}, {})
            self._player_projection_cache[cache_key] = empty
            return empty

        target_ord = _slice_ordinal(season, week)
        target_context_by_team = self._game_context_by_team(season=season, week=week)
        target_schedule_rows = self.session.execute(
            select(RawNflSchedule).where(
                and_(
                    RawNflSchedule.season == season,
                    RawNflSchedule.week == week,
                )
            )
        ).scalars().all()
        target_home_away_by_team: dict[str, str] = {}
        target_kickoff_bucket_by_team: dict[str, str] = {}
        target_game_id_by_team: dict[str, str] = {}
        for sched_row in target_schedule_rows:
            payload = sched_row.raw_row_json or {}
            home_team = _canonical_team(sched_row.home_team or payload.get("home_team"))
            away_team = _canonical_team(sched_row.away_team or payload.get("away_team"))
            game_id = _safe_str(sched_row.game_id or payload.get("game_id"))
            kickoff_value = sched_row.kickoff or payload.get("kickoff") or payload.get("gameday")
            kickoff_bucket = _kickoff_bucket(str(kickoff_value) if kickoff_value is not None else None)
            if home_team:
                target_home_away_by_team[home_team] = "home"
                target_kickoff_bucket_by_team[home_team] = kickoff_bucket
                if game_id:
                    target_game_id_by_team[home_team] = game_id
            if away_team:
                target_home_away_by_team[away_team] = "away"
                target_kickoff_bucket_by_team[away_team] = kickoff_bucket
                if game_id:
                    target_game_id_by_team[away_team] = game_id

        target_teams = sorted({_canonical_team(row.team) for row in salary_rows if _canonical_team(row.team)})
        target_opponents = sorted(
            {_canonical_team(row.opponent) for row in salary_rows if _canonical_team(row.opponent)}
        )

        master_ids = sorted({row.player_master_id for row in salary_rows if row.player_master_id})
        alias_rows = []
        if master_ids:
            alias_rows = self.session.execute(
                select(PlayerAlias.player_master_id, PlayerAlias.source_key).where(
                    and_(
                        PlayerAlias.source_system == "nflreadpy",
                        PlayerAlias.player_master_id.in_(master_ids),
                    )
                )
            ).all()

        master_to_player_ids: dict[str, set[str]] = defaultdict(set)
        player_id_to_masters: dict[str, set[str]] = defaultdict(set)
        for player_master_id, source_key in alias_rows:
            if source_key and player_master_id:
                master_to_player_ids[player_master_id].add(source_key)
                player_id_to_masters[source_key].add(player_master_id)

        tracked_player_ids = sorted(player_id_to_masters.keys())
        player_history_rows = []
        if tracked_player_ids:
            player_history_rows = self.session.execute(
                select(RawNflWeeklyStat).where(
                    and_(
                        RawNflWeeklyStat.source_system == "nflreadpy",
                        RawNflWeeklyStat.player_id.in_(tracked_player_ids),
                        or_(
                            RawNflWeeklyStat.season < season,
                            and_(RawNflWeeklyStat.season == season, RawNflWeeklyStat.week < week),
                        ),
                    )
                )
            ).scalars().all()

        defense_history_rows = []
        if target_opponents:
            defense_history_rows = self.session.execute(
                select(RawNflWeeklyStat).where(
                    and_(
                        RawNflWeeklyStat.source_system == "nflreadpy",
                        RawNflWeeklyStat.opponent.in_(target_opponents),
                        or_(
                            RawNflWeeklyStat.season < season,
                            and_(RawNflWeeklyStat.season == season, RawNflWeeklyStat.week < week),
                        ),
                    )
                )
            ).scalars().all()

        game_ids = sorted(
            {
                stat_row.game_id
                for stat_row in [*player_history_rows, *defense_history_rows]
                if stat_row.game_id
            }
        )
        game_meta_by_id: dict[str, tuple[str | None, str | None, str]] = {}
        if game_ids:
            schedule_rows = self.session.execute(
                select(RawNflSchedule).where(RawNflSchedule.game_id.in_(game_ids))
            ).scalars().all()
            for sched_row in schedule_rows:
                payload = sched_row.raw_row_json or {}
                game_id = sched_row.game_id or _safe_str(payload.get("game_id"))
                if not game_id:
                    continue
                home_team = _canonical_team(sched_row.home_team or payload.get("home_team"))
                away_team = _canonical_team(sched_row.away_team or payload.get("away_team"))
                kickoff_value = sched_row.kickoff or payload.get("kickoff") or payload.get("gameday")
                game_meta_by_id[game_id] = (
                    home_team,
                    away_team,
                    _kickoff_bucket(str(kickoff_value) if kickoff_value is not None else None),
                )

        points_by_master: dict[str, list[tuple[float, int, str | None, str, str]]] = defaultdict(list)
        points_by_position: dict[str, list[float]] = defaultdict(list)
        for stat in player_history_rows:
            points = _calculate_dk_player_points(stat.raw_row_json or {}, stat.position)
            if not math.isfinite(points):
                continue
            position = _normalize_pool_position(stat.position)
            if not position or position == "DST":
                continue
            points_by_position[position].append(float(points))
            if stat.player_id:
                team_key = _canonical_team(stat.team)
                opponent_key = _canonical_team(stat.opponent)
                home_away = "unknown"
                kickoff_bucket = "unknown"
                if stat.game_id and stat.game_id in game_meta_by_id and team_key:
                    home_team, away_team, kickoff_bucket = game_meta_by_id[stat.game_id]
                    if home_team and team_key == home_team:
                        home_away = "home"
                    elif away_team and team_key == away_team:
                        home_away = "away"
                for master_id in player_id_to_masters.get(stat.player_id, set()):
                    points_by_master[master_id].append(
                        (
                            float(points),
                            _slice_ordinal(stat.season, stat.week),
                            opponent_key,
                            home_away,
                            kickoff_bucket,
                        )
                    )

        defense_points_by_team_pos: dict[tuple[str, str], list[tuple[float, int]]] = defaultdict(list)
        league_points_allowed_by_pos: dict[str, list[float]] = defaultdict(list)
        for stat in defense_history_rows:
            points = _calculate_dk_player_points(stat.raw_row_json or {}, stat.position)
            if not math.isfinite(points):
                continue
            position = _normalize_pool_position(stat.position)
            if not position or position == "DST":
                continue
            defense_team = _canonical_team(stat.opponent)
            if not defense_team:
                continue
            row_ord = _slice_ordinal(stat.season, stat.week)
            defense_points_by_team_pos[(defense_team, position)].append((float(points), row_ord))
            league_points_allowed_by_pos[position].append(float(points))

        global_points: list[float] = []
        for values in points_by_position.values():
            global_points.extend(values)
        if not global_points:
            global_points = [8.0]

        source_keys = sorted({row.source_player_key for row in salary_rows if row.source_player_key})
        injury_by_master: dict[str, str | None] = {}
        injury_by_source_key: dict[str, str | None] = {}
        injury_severity_rank = {
            "unknown": 0,
            "active": 1,
            "probable": 2,
            "questionable": 3,
            "doubtful": 4,
            "out": 5,
        }
        team_skill_out_counts: dict[str, int] = defaultdict(int)
        team_position_out_counts: dict[tuple[str, str], int] = defaultdict(int)
        injury_filters = []
        if master_ids:
            injury_filters.append(CuratedInjury.player_master_id.in_(master_ids))
        if source_keys:
            injury_filters.append(CuratedInjury.source_player_key.in_(source_keys))
        if target_teams:
            injury_filters.append(CuratedInjury.team.in_(target_teams))
        if injury_filters:
            injury_rows = self.session.execute(
                select(CuratedInjury).where(
                    and_(
                        CuratedInjury.source_system == source_system,
                        CuratedInjury.season == season,
                        CuratedInjury.week == week,
                        CuratedInjury.slate == slate,
                        or_(*injury_filters),
                    )
                )
            ).scalars().all()
            for injury_row in injury_rows:
                status = injury_row.injury_status
                bucket = _injury_status_bucket(status)
                position = _normalize_pool_position(injury_row.position)
                team_key = _canonical_team(injury_row.team)

                if injury_row.player_master_id:
                    existing = injury_by_master.get(injury_row.player_master_id)
                    if (
                        existing is None
                        or injury_severity_rank[_injury_status_bucket(status)]
                        > injury_severity_rank[_injury_status_bucket(existing)]
                    ):
                        injury_by_master[injury_row.player_master_id] = status
                if injury_row.source_player_key:
                    existing = injury_by_source_key.get(injury_row.source_player_key)
                    if (
                        existing is None
                        or injury_severity_rank[_injury_status_bucket(status)]
                        > injury_severity_rank[_injury_status_bucket(existing)]
                    ):
                        injury_by_source_key[injury_row.source_player_key] = status

                if (
                    team_key
                    and position in {"QB", "RB", "WR", "TE"}
                    and bucket in {"out", "doubtful"}
                ):
                    team_skill_out_counts[team_key] += 1
                    team_position_out_counts[(team_key, position)] += 1

        matchup_models: dict[str, PlayerMatchupProjectionModel] = {}
        if self._use_matrix_matchup_model:
            matchup_models = self._fit_player_matchup_models_from_matrix(
                source_system=source_system,
                season=season,
                week=week,
                slate=slate,
            )

        lookup: dict[str, tuple[float, float]] = {}
        projection_feature_rows: dict[str, dict[str, Any]] = {}
        for row in salary_rows:
            position = _normalize_pool_position(row.position)
            if position == "DST":
                continue

            team_key = _canonical_team(row.team)
            opponent_key = _canonical_team(row.opponent)
            target_home_away = target_home_away_by_team.get(team_key or "", "unknown")
            target_kickoff_bucket = target_kickoff_bucket_by_team.get(team_key or "", "unknown")
            context = target_context_by_team.get(team_key or "", {})

            player_records = points_by_master.get(row.player_master_id or "", [])
            player_points = [entry[0] for entry in player_records]
            player_records_desc = sorted(player_records, key=lambda item: item[1], reverse=True)
            player_roll3_mean: float | None = None
            player_roll8_mean: float | None = None
            player_roll8_std: float | None = None
            if player_points:
                recency_weights = [
                    1.0 / (1.0 + (0.12 * max(1, target_ord - entry[1])))
                    for entry in player_records
                ]
                recency_sum = float(sum(recency_weights))
                weighted_player_mean = (
                    float(sum(point * weight for point, weight in zip(player_points, recency_weights)) / recency_sum)
                    if recency_sum > 0
                    else float(np.mean(player_points))
                )
                recent_points = [entry[0] for entry in player_records_desc[:6]]
                recent3_points = [entry[0] for entry in player_records_desc[:3]]
                recent8_points = [entry[0] for entry in player_records_desc[:8]]
                overall_mean = float(np.mean(player_points))
                base_mean = (0.65 * weighted_player_mean) + (0.35 * overall_mean)
                base_p90 = float(np.percentile(player_points, 90))
                if recent_points:
                    base_p90 = max(base_p90, float(np.percentile(recent_points, 80)))
                if recent3_points:
                    player_roll3_mean = float(np.mean(recent3_points))
                if recent8_points:
                    player_roll8_mean = float(np.mean(recent8_points))
                    player_roll8_std = float(np.std(recent8_points))
            else:
                pos_points = points_by_position.get(position or "", [])
                series = pos_points if pos_points else global_points
                arr = np.asarray(series, dtype=float)
                base_mean = float(np.mean(arr))
                base_p90 = float(np.percentile(arr, 90))

            vs_opp_points = [entry[0] for entry in player_records if opponent_key and entry[2] == opponent_key]
            vs_opp_recent_points = [entry[0] for entry in player_records_desc if opponent_key and entry[2] == opponent_key]
            player_vs_opp_roll4: float | None = None
            if vs_opp_recent_points:
                player_vs_opp_roll4 = float(np.mean(vs_opp_recent_points[:4]))
            vs_opp_factor = 1.0
            if vs_opp_points and base_mean > 0:
                ratio = float(np.mean(vs_opp_points)) / max(base_mean, 1e-6)
                shrink = min(1.0, len(vs_opp_points) / 4.0)
                vs_opp_factor = _clamp(1.0 + ((ratio - 1.0) * 0.65 * shrink), 0.75, 1.30)

            split_points = [entry[0] for entry in player_records if entry[3] == target_home_away]
            home_away_factor = 1.0
            if split_points and base_mean > 0:
                ratio = float(np.mean(split_points)) / max(base_mean, 1e-6)
                shrink = min(1.0, len(split_points) / 6.0)
                home_away_factor = _clamp(1.0 + ((ratio - 1.0) * 0.35 * shrink), 0.88, 1.14)

            bucket_points = [entry[0] for entry in player_records if entry[4] == target_kickoff_bucket]
            kickoff_factor = 1.0
            if bucket_points and base_mean > 0:
                ratio = float(np.mean(bucket_points)) / max(base_mean, 1e-6)
                shrink = min(1.0, len(bucket_points) / 6.0)
                kickoff_factor = _clamp(1.0 + ((ratio - 1.0) * 0.25 * shrink), 0.90, 1.12)

            defense_factor = 1.0
            defense_pos_allowed_roll3: float | None = None
            defense_pos_allowed_roll8: float | None = None
            defense_pos_allowed_p90_roll8: float | None = None
            if opponent_key and position:
                opp_series = defense_points_by_team_pos.get((opponent_key, position), [])
                opp_points = [value for value, _ord in opp_series]
                opp_series_desc = sorted(opp_series, key=lambda item: item[1], reverse=True)
                recent3_allowed = [value for value, _ord in opp_series_desc[:3]]
                recent8_allowed = [value for value, _ord in opp_series_desc[:8]]
                if recent3_allowed:
                    defense_pos_allowed_roll3 = float(np.mean(recent3_allowed))
                if recent8_allowed:
                    defense_pos_allowed_roll8 = float(np.mean(recent8_allowed))
                    defense_pos_allowed_p90_roll8 = float(np.percentile(recent8_allowed, 90))
                league_points = league_points_allowed_by_pos.get(position, [])
                if opp_points and league_points:
                    opp_weights = [
                        1.0 / (1.0 + (0.10 * max(1, target_ord - row_ord)))
                        for _value, row_ord in opp_series
                    ]
                    denom = float(sum(opp_weights))
                    opp_mean = (
                        float(sum(v * w for v, w in zip(opp_points, opp_weights)) / denom)
                        if denom > 0
                        else float(np.mean(opp_points))
                    )
                    league_mean = float(np.mean(league_points))
                    ratio = opp_mean / max(league_mean, 1e-6)
                    shrink = min(1.0, len(opp_points) / 30.0)
                    defense_factor = _clamp(1.0 + ((ratio - 1.0) * shrink), 0.72, 1.32)

            vegas_factor = 1.0
            implied_total = _safe_float(context.get("team_implied_total"))
            opponent_implied_total = _safe_float(context.get("opponent_implied_total"))
            game_total_line = _safe_float(context.get("game_total_line"))
            spread_line = _safe_float(context.get("team_spread_line"))
            if implied_total is not None:
                vegas_factor *= _clamp(1.0 + (((implied_total - 22.0) / 22.0) * 0.30), 0.85, 1.20)
            if game_total_line is not None:
                vegas_factor *= _clamp(1.0 + (((game_total_line - 45.0) / 45.0) * 0.12), 0.90, 1.15)
            if spread_line is not None:
                if position == "RB":
                    vegas_factor *= _clamp(1.0 + (((-spread_line) / 14.0) * 0.12), 0.90, 1.12)
                elif position in {"WR", "TE"}:
                    vegas_factor *= _clamp(1.0 + ((spread_line / 14.0) * 0.08), 0.90, 1.12)
                elif position == "QB":
                    vegas_factor *= _clamp(1.0 + (((game_total_line or 45.0) - 45.0) / 45.0 * 0.08), 0.92, 1.10)

            injury_status = injury_by_master.get(row.player_master_id or "")
            if injury_status is None and row.source_player_key:
                injury_status = injury_by_source_key.get(row.source_player_key)
            injury_factor = _injury_multiplier(injury_status)

            teammate_factor = 1.0
            if team_key and position:
                skill_out = float(team_skill_out_counts.get(team_key, 0))
                same_pos_out = float(team_position_out_counts.get((team_key, position), 0))
                if position == "RB":
                    teammate_factor = _clamp(1.0 + (0.05 * same_pos_out) + (0.02 * skill_out), 0.90, 1.18)
                elif position in {"WR", "TE"}:
                    teammate_factor = _clamp(1.0 + (0.04 * same_pos_out) + (0.015 * skill_out), 0.90, 1.18)
                elif position == "QB":
                    pass_out = float(team_position_out_counts.get((team_key, "WR"), 0)) + float(
                        team_position_out_counts.get((team_key, "TE"), 0)
                    )
                    teammate_factor = _clamp(1.0 - (0.03 * pass_out), 0.82, 1.05)

            combined_factor = (
                defense_factor
                * vs_opp_factor
                * home_away_factor
                * kickoff_factor
                * vegas_factor
                * injury_factor
                * teammate_factor
            )
            projected_mean = max(1.0, float(base_mean * combined_factor))
            volatility = float(np.std(player_points)) if len(player_points) >= 2 else max(3.5, projected_mean * 0.28)
            projected_p90 = max(
                projected_mean * 1.10,
                float(base_p90 * combined_factor * 0.95),
                projected_mean + (1.15 * volatility),
            )

            feature_vector = self._player_matchup_feature_vector_from_values(
                salary=int(row.salary or 0),
                is_home=(target_home_away == "home"),
                game_total_line=game_total_line,
                team_spread_line=spread_line,
                team_implied_total=implied_total,
                opponent_implied_total=opponent_implied_total,
                player_games_history=len(player_points),
                player_roll3_mean=player_roll3_mean,
                player_roll8_mean=player_roll8_mean,
                player_roll8_std=player_roll8_std,
                player_vs_opp_roll4=player_vs_opp_roll4,
                defense_pos_allowed_roll3=defense_pos_allowed_roll3,
                defense_pos_allowed_roll8=defense_pos_allowed_roll8,
                defense_pos_allowed_p90_roll8=defense_pos_allowed_p90_roll8,
                player_injury_status=injury_status,
                team_skill_out_count=int(team_skill_out_counts.get(team_key or "", 0)),
                team_position_out_count=int(team_position_out_counts.get((team_key or "", position), 0)),
                kickoff_bucket=target_kickoff_bucket,
            )
            matchup_model = matchup_models.get(position or "")
            if matchup_model is not None and matchup_model.enabled and matchup_model.blend_weight > 0.0:
                model_mean, model_p90 = self._predict_player_matchup_points(
                    model=matchup_model,
                    feature_vector=feature_vector,
                )
                blend_weight = float(matchup_model.blend_weight)
                if len(player_points) <= 1:
                    blend_weight = max(blend_weight, 0.5)
                projected_mean = ((1.0 - blend_weight) * projected_mean) + (blend_weight * model_mean)
                projected_p90 = ((1.0 - blend_weight) * projected_p90) + (blend_weight * model_p90)

            mean_val = _clamp(projected_mean, 1.0, 55.0)
            p90_val = _clamp(projected_p90, mean_val + 0.5, 70.0)

            team_position_out = int(team_position_out_counts.get((team_key or "", position), 0))
            candidate_player_ids = sorted(master_to_player_ids.get(row.player_master_id or "", set()))
            model_player_id = candidate_player_ids[0] if candidate_player_ids else (
                row.source_player_key or row.player_master_id or row.normalized_name
            )
            feature_payload: dict[str, Any] = {
                "source_system": source_system,
                "season": season,
                "week": week,
                "slate": slate,
                "game_id": target_game_id_by_team.get(team_key or ""),
                "player_id": model_player_id,
                "player_master_id": row.player_master_id,
                "source_player_key": row.source_player_key,
                "player_name": row.player_name,
                "team": team_key,
                "opponent": opponent_key,
                "position": position,
                "salary": int(row.salary or 0),
                "is_home": (target_home_away == "home"),
                "kickoff_bucket": target_kickoff_bucket,
                "game_total_line": game_total_line,
                "team_spread_line": spread_line,
                "team_implied_total": implied_total,
                "opponent_implied_total": opponent_implied_total,
                "player_games_history": int(len(player_points)),
                "player_roll3_mean": player_roll3_mean,
                "player_roll8_mean": player_roll8_mean,
                "player_roll8_std": player_roll8_std,
                "player_vs_opp_roll4": player_vs_opp_roll4,
                "defense_pos_allowed_roll3": defense_pos_allowed_roll3,
                "defense_pos_allowed_roll8": defense_pos_allowed_roll8,
                "defense_pos_allowed_p90_roll8": defense_pos_allowed_p90_roll8,
                "player_injury_status": _injury_status_bucket(injury_status),
                "team_skill_out_count": int(team_skill_out_counts.get(team_key or "", 0)),
                "team_position_out_count": team_position_out,
                "projected_mean_points": mean_val,
                "projected_p90_points": p90_val,
            }

            for key in [row.player_master_id, row.source_player_key]:
                if key:
                    lookup[key] = (mean_val, p90_val)
                    projection_feature_rows[key] = feature_payload

        dst_lookup = self._compute_dst_projection_lookup(season=season, week=week)
        result = (lookup, dst_lookup)
        self._player_projection_cache[cache_key] = result
        self._projection_feature_cache[cache_key] = projection_feature_rows
        return result

    def rebuild_player_game_feature_matrix(
        self,
        *,
        source_system: str,
        season_start: int,
        season_end: int,
        slate: str | None = None,
        progress_hook: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        start = min(season_start, season_end)
        end = max(season_start, season_end)
        slices = self._fetch_available_slate_slices(
            source_system=source_system,
            season_start=start,
            season_end=end,
            slate_filter=slate,
        )
        if not slices:
            return {
                "source_system": source_system,
                "season_start": start,
                "season_end": end,
                "slate": slate,
                "slates_total": 0,
                "slates_completed": 0,
                "slates_failed": 0,
                "rows_written": 0,
                "rows": [],
            }

        rows: list[dict[str, Any]] = []
        rows_written = 0
        slates_completed = 0

        for index, (season, week, current_slate) in enumerate(slices, start=1):
            try:
                projection_lookup, dst_projection_lookup = self._compute_player_projection_lookup(
                    source_system=source_system,
                    season=season,
                    week=week,
                    slate=current_slate,
                )
                pool = self._fetch_slate_player_pool(
                    source_system=source_system,
                    season=season,
                    week=week,
                    slate=current_slate,
                    projection_lookup=projection_lookup,
                    dst_projection_lookup=dst_projection_lookup,
                )
                feature_key = (source_system, season, week, current_slate)
                feature_cache = self._projection_feature_cache.get(feature_key, {})
                if not feature_cache:
                    raise ValueError("No projection feature cache found for target slice.")

                slice_rows: list[dict[str, Any]] = []
                for player in pool:
                    if player.position not in {"QB", "RB", "WR", "TE", "DST"}:
                        continue
                    if player.position == "DST":
                        player_key = player.team or player.uid
                        feature = {
                            "source_system": source_system,
                            "season": season,
                            "week": week,
                            "game_id": None,
                            "player_id": player_key,
                            "player_master_id": player.player_master_id,
                            "source_player_key": player.source_player_key,
                            "player_name": player.name,
                            "team": player.team,
                            "opponent": player.opponent,
                            "position": "DST",
                            "salary": int(player.salary),
                            "slate": current_slate,
                            "is_home": None,
                            "kickoff_bucket": None,
                            "game_total_line": player.game_total_line,
                            "team_spread_line": player.team_spread_line,
                            "team_implied_total": player.team_implied_total,
                            "opponent_implied_total": player.opponent_implied_total,
                            "player_games_history": 0,
                            "player_roll3_mean": None,
                            "player_roll8_mean": None,
                            "player_roll8_std": None,
                            "player_vs_opp_roll4": None,
                            "defense_pos_allowed_roll3": None,
                            "defense_pos_allowed_roll8": None,
                            "defense_pos_allowed_p90_roll8": None,
                            "player_injury_status": "unknown",
                            "team_skill_out_count": 0,
                            "team_position_out_count": 0,
                        }
                    else:
                        feature = (
                            feature_cache.get(player.player_master_id or "")
                            or feature_cache.get(player.source_player_key or "")
                        )
                        if feature is None:
                            continue

                    player_id = _safe_str(feature.get("player_id"))
                    if not player_id:
                        continue
                    position = _safe_str(feature.get("position"))
                    if not position:
                        continue

                    slice_rows.append(
                        {
                            "source_system": source_system,
                            "season": int(season),
                            "week": int(week),
                            "game_id": _safe_str(feature.get("game_id")),
                            "player_id": player_id,
                            "player_master_id": _safe_str(feature.get("player_master_id")),
                            "source_player_key": _safe_str(feature.get("source_player_key")),
                            "player_name": _safe_str(feature.get("player_name")),
                            "team": _safe_str(feature.get("team")),
                            "opponent": _safe_str(feature.get("opponent")),
                            "position": position,
                            "dk_points": float(player.actual_points),
                            "salary": int(player.salary),
                            "slate": current_slate,
                            "is_home": feature.get("is_home"),
                            "kickoff_bucket": _safe_str(feature.get("kickoff_bucket")),
                            "game_total_line": _safe_float(feature.get("game_total_line")),
                            "team_spread_line": _safe_float(feature.get("team_spread_line")),
                            "team_implied_total": _safe_float(feature.get("team_implied_total")),
                            "opponent_implied_total": _safe_float(feature.get("opponent_implied_total")),
                            "player_games_history": int(feature.get("player_games_history") or 0),
                            "player_roll3_mean": _safe_float(feature.get("player_roll3_mean")),
                            "player_roll8_mean": _safe_float(feature.get("player_roll8_mean")),
                            "player_roll8_std": _safe_float(feature.get("player_roll8_std")),
                            "player_vs_opp_roll4": _safe_float(feature.get("player_vs_opp_roll4")),
                            "defense_pos_allowed_roll3": _safe_float(feature.get("defense_pos_allowed_roll3")),
                            "defense_pos_allowed_roll8": _safe_float(feature.get("defense_pos_allowed_roll8")),
                            "defense_pos_allowed_p90_roll8": _safe_float(feature.get("defense_pos_allowed_p90_roll8")),
                            "player_injury_status": _safe_str(feature.get("player_injury_status")) or "unknown",
                            "team_skill_out_count": int(feature.get("team_skill_out_count") or 0),
                            "team_position_out_count": int(feature.get("team_position_out_count") or 0),
                            "created_at": utcnow_naive(),
                        }
                    )

                unique_rows: dict[tuple[str, int, int, str | None, str, str], dict[str, Any]] = {}
                for payload in slice_rows:
                    key = (
                        str(payload["source_system"]),
                        int(payload["season"]),
                        int(payload["week"]),
                        _safe_str(payload.get("game_id")),
                        str(payload["player_id"]),
                        str(payload["position"]),
                    )
                    unique_rows[key] = payload
                payload_rows = list(unique_rows.values())

                self.session.execute(
                    delete(PlayerGameFeatureMatrix).where(
                        and_(
                            PlayerGameFeatureMatrix.source_system == source_system,
                            PlayerGameFeatureMatrix.season == season,
                            PlayerGameFeatureMatrix.week == week,
                            PlayerGameFeatureMatrix.slate == current_slate,
                        )
                    )
                )

                existing_rows = self.session.execute(
                    select(
                        PlayerGameFeatureMatrix.game_id,
                        PlayerGameFeatureMatrix.player_id,
                        PlayerGameFeatureMatrix.position,
                    ).where(
                        and_(
                            PlayerGameFeatureMatrix.source_system == source_system,
                            PlayerGameFeatureMatrix.season == season,
                            PlayerGameFeatureMatrix.week == week,
                        )
                    )
                ).all()
                existing_keys = {
                    (_safe_str(game_id), str(player_id), str(position))
                    for game_id, player_id, position in existing_rows
                    if player_id and position
                }
                insert_rows = [
                    payload
                    for payload in payload_rows
                    if (
                        _safe_str(payload.get("game_id")),
                        str(payload.get("player_id")),
                        str(payload.get("position")),
                    )
                    not in existing_keys
                ]
                if insert_rows:
                    self.session.bulk_insert_mappings(PlayerGameFeatureMatrix, insert_rows)
                self.session.commit()

                slates_completed += 1
                rows_written += len(insert_rows)
                row_summary = {
                    "season": season,
                    "week": week,
                    "slate": current_slate,
                    "status": "ok",
                    "rows_written": len(insert_rows),
                }
                rows.append(row_summary)
                if progress_hook is not None:
                    progress_hook(
                        f"[feature_matrix] {index}/{len(slices)} {season} W{week:02d} {current_slate} "
                        f"status=ok rows={len(payload_rows)}"
                    )
            except Exception as exc:  # noqa: BLE001
                self.session.rollback()
                row_summary = {
                    "season": season,
                    "week": week,
                    "slate": current_slate,
                    "status": "failed",
                    "rows_written": 0,
                    "error_message": str(exc),
                }
                rows.append(row_summary)
                if progress_hook is not None:
                    progress_hook(
                        f"[feature_matrix] {index}/{len(slices)} {season} W{week:02d} {current_slate} "
                        f"status=failed error={exc}"
                    )

        self._matchup_model_cache.clear()
        self._player_projection_cache.clear()

        return {
            "source_system": source_system,
            "season_start": start,
            "season_end": end,
            "slate": slate,
            "slates_total": len(slices),
            "slates_completed": slates_completed,
            "slates_failed": len(slices) - slates_completed,
            "rows_written": rows_written,
            "rows": rows,
        }

    def _collect_training_lineup_chunks(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        training_start_season: int,
        training_window_slates: int,
        training_lineups_per_slate: int,
        rng: np.random.Generator,
        classic_value_model: ClassicValueDriverModel | None = None,
        classic_value_prior_strength: float = 0.0,
        matchup_outcome_model: MatchupOutcomeIntelligenceModel | None = None,
        matchup_outcome_prior_strength: float = 0.0,
        matchup_prior_gate_model: MatchupPriorGateModel | None = None,
    ) -> tuple[list[np.ndarray], list[np.ndarray], int, int]:
        target_ord = _slice_ordinal(season, week)
        slices = self._fetch_available_slate_slices(
            source_system=source_system,
            season_start=training_start_season,
            season_end=season,
            slate_filter=None,
        )
        historical = [item for item in slices if _slice_ordinal(item[0], item[1]) < target_ord]

        x_chunks_recent: list[np.ndarray] = []
        points_chunks_recent: list[np.ndarray] = []
        slates_used = 0
        for hist_season, hist_week, hist_slate in reversed(historical):
            try:
                projection_lookup, dst_projection_lookup = self._compute_player_projection_lookup(
                    source_system=source_system,
                    season=hist_season,
                    week=hist_week,
                    slate=hist_slate,
                )
                pool = self._fetch_slate_player_pool(
                    source_system=source_system,
                    season=hist_season,
                    week=hist_week,
                    slate=hist_slate,
                    projection_lookup=projection_lookup,
                    dst_projection_lookup=dst_projection_lookup,
                )
                classic_sampling_multipliers = self._classic_player_sampling_multipliers(
                    players=pool,
                    model=classic_value_model,
                    prior_strength=classic_value_prior_strength,
                )
                effective_matchup_prior_strength, _gate_score, _gate_active = self._effective_matchup_prior_strength(
                    requested_strength=matchup_outcome_prior_strength,
                    gate_model=matchup_prior_gate_model,
                    slate=hist_slate,
                    players=pool,
                )
                matchup_raw_map = self._matchup_outcome_player_raw_map(
                    source_system=source_system,
                    season=hist_season,
                    week=hist_week,
                    slate=hist_slate,
                    players=pool,
                    model=matchup_outcome_model,
                )
                matchup_sampling_multipliers = self._sampling_multipliers_from_raw_map(
                    raw_map=matchup_raw_map,
                    strength=effective_matchup_prior_strength,
                )
                x_slate, points_slate, _ = self._generate_lineups_for_slate(
                    players=pool,
                    lineups_target=training_lineups_per_slate,
                    rng=rng,
                    player_sampling_multipliers=self._merge_sampling_multipliers(
                        classic_sampling_multipliers,
                        matchup_sampling_multipliers,
                    ),
                )
            except Exception:  # noqa: BLE001
                continue
            if float(np.max(points_slate)) <= 0.0:
                continue
            if float(np.std(points_slate)) < 1e-9:
                continue
            x_chunks_recent.append(x_slate)
            points_chunks_recent.append(points_slate)
            slates_used += 1
            if slates_used >= training_window_slates:
                break

        # Keep chronological order for any time-aware downstream analysis.
        x_chunks = list(reversed(x_chunks_recent))
        points_chunks = list(reversed(points_chunks_recent))
        total_rows = int(sum(chunk.shape[0] for chunk in x_chunks))
        return x_chunks, points_chunks, slates_used, total_rows

    def _fit_percentile_model(
        self,
        *,
        x_chunks: list[np.ndarray],
        points_chunks: list[np.ndarray],
        percentile: float,
        tail: str,
    ) -> LogisticTargetModel:
        x_parts: list[np.ndarray] = []
        y_parts: list[np.ndarray] = []
        for x_slate, points_slate in zip(x_chunks, points_chunks):
            threshold = float(np.percentile(points_slate, percentile))
            if not math.isfinite(threshold):
                continue
            if tail == "upper":
                y_slate = (points_slate >= threshold).astype(float)
            else:
                y_slate = (points_slate <= threshold).astype(float)
            pos_rate = float(np.mean(y_slate))
            if pos_rate <= 0.0 or pos_rate >= 1.0:
                continue
            x_parts.append(x_slate)
            y_parts.append(y_slate)

        if not x_parts:
            dim = len(FEATURE_NAMES)
            return LogisticTargetModel(
                weights=np.zeros(dim, dtype=float),
                bias=0.0,
                mean=np.zeros(dim, dtype=float),
                std=np.ones(dim, dtype=float),
                positive_rate=0.0,
                training_rows=0,
                has_signal=False,
            )

        x_train = np.vstack(x_parts)
        y_train = np.concatenate(y_parts)
        weights, bias, mean, std = self._fit_logistic(x_train, y_train)
        has_signal = float(np.max(np.abs(weights))) > 1e-8
        return LogisticTargetModel(
            weights=weights,
            bias=float(bias),
            mean=mean,
            std=std,
            positive_rate=float(np.mean(y_train)),
            training_rows=int(len(y_train)),
            has_signal=has_signal,
        )

    def _predict_target_model(self, model: LogisticTargetModel, x_rows: np.ndarray) -> np.ndarray:
        if x_rows.size == 0:
            return np.asarray([], dtype=float)
        x_norm = (x_rows - model.mean) / model.std
        return _sigmoid(x_norm @ model.weights + model.bias)

    def _fit_blend_weights(
        self,
        *,
        points_train: np.ndarray,
        policy_scores: np.ndarray,
        ceiling_scores: np.ndarray,
        quality_scores: np.ndarray,
    ) -> tuple[np.ndarray, float]:
        if len(points_train) < 400:
            return np.asarray([1.0, 0.0, 0.0], dtype=float), 0.0

        points_arr = np.asarray(points_train, dtype=float)
        x_all = np.column_stack(
            [
                np.asarray(policy_scores, dtype=float),
                np.asarray(ceiling_scores, dtype=float),
                np.asarray(quality_scores, dtype=float),
            ]
        )
        if points_arr.ndim != 1 or x_all.shape[0] != points_arr.shape[0]:
            return np.asarray([1.0, 0.0, 0.0], dtype=float), 0.0
        if not np.isfinite(points_arr).all() or not np.isfinite(x_all).all():
            return np.asarray([1.0, 0.0, 0.0], dtype=float), 0.0

        split_idx = int(points_arr.shape[0] * 0.8)
        split_idx = max(240, split_idx)
        split_idx = min(split_idx, points_arr.shape[0] - 80)
        if split_idx < 240 or (points_arr.shape[0] - split_idx) < 60:
            return np.asarray([1.0, 0.0, 0.0], dtype=float), 0.0

        x_train = x_all[:split_idx]
        y_train = points_arr[:split_idx]
        x_valid = x_all[split_idx:]
        y_valid = points_arr[split_idx:]

        y_mean = float(np.mean(y_train))
        y_std = float(np.std(y_train))
        if y_std < 1e-9:
            return np.asarray([1.0, 0.0, 0.0], dtype=float), 0.0
        y_train_norm = (y_train - y_mean) / y_std

        x_mean = np.mean(x_train, axis=0)
        x_std = np.std(x_train, axis=0)
        x_std = np.where(x_std < 1e-6, 1.0, x_std)
        xs_train = (x_train - x_mean) / x_std
        xs_valid = (x_valid - x_mean) / x_std

        def _fit_ridge(design_x: np.ndarray, y: np.ndarray, ridge: float) -> tuple[np.ndarray, float]:
            design = np.column_stack([design_x, np.ones(design_x.shape[0], dtype=float)])
            gram = design.T @ design
            for idx in range(design_x.shape[1]):
                gram[idx, idx] += ridge
            rhs = design.T @ y
            try:
                coeff = np.linalg.solve(gram, rhs)
            except np.linalg.LinAlgError:
                coeff = np.linalg.pinv(gram) @ rhs
            return coeff[: design_x.shape[1]].astype(float), float(coeff[design_x.shape[1]])

        def _rank(values: np.ndarray) -> np.ndarray:
            order = np.argsort(values, kind="mergesort")
            ranks = np.empty(values.shape[0], dtype=float)
            ranks[order] = np.arange(values.shape[0], dtype=float)
            return ranks

        def _spearman(a: np.ndarray, b: np.ndarray) -> float:
            if a.shape[0] < 8:
                return 0.0
            ra = _rank(a)
            rb = _rank(b)
            sa = float(np.std(ra))
            sb = float(np.std(rb))
            if sa < 1e-9 or sb < 1e-9:
                return 0.0
            corr = float(np.corrcoef(ra, rb)[0, 1])
            if not math.isfinite(corr):
                return 0.0
            return corr

        full_w_scaled, full_b_scaled = _fit_ridge(xs_train, y_train_norm, ridge=0.08)
        policy_w_scaled, policy_b_scaled = _fit_ridge(xs_train[:, [0]], y_train_norm, ridge=0.08)

        full_w = full_w_scaled / x_std
        full_b = full_b_scaled - float(np.dot(full_w, x_mean))
        policy_w = float(policy_w_scaled[0] / x_std[0])
        policy_b = float(policy_b_scaled - (policy_w * x_mean[0]))

        full_valid_score = (x_valid @ full_w) + full_b
        policy_valid_score = (x_valid[:, 0] * policy_w) + policy_b

        corr_full = _spearman(full_valid_score, y_valid)
        corr_policy = _spearman(policy_valid_score, y_valid)
        corr_lift = corr_full - corr_policy
        if not math.isfinite(corr_lift) or corr_lift <= 0.005:
            return np.asarray([1.0, 0.0, 0.0], dtype=float), 0.0

        positive_weights = np.maximum(full_w, 0.0)
        weight_sum = float(np.sum(positive_weights))
        if weight_sum <= 1e-9:
            return np.asarray([1.0, 0.0, 0.0], dtype=float), 0.0
        normalized_weights = positive_weights / weight_sum

        lift_alpha = _clamp(corr_lift / 0.08, 0.0, 1.0)
        blended_weights = ((1.0 - lift_alpha) * np.asarray([1.0, 0.0, 0.0], dtype=float)) + (
            lift_alpha * normalized_weights
        )
        blended_weights = blended_weights / max(1e-9, float(np.sum(blended_weights)))
        return blended_weights.astype(float), 0.0

    def _lineup_key(self, lineup: list[PlayerPoolRow]) -> str:
        return "|".join(sorted(row.uid for row in lineup))

    def _canonical_slot_order(self, lineup: list[PlayerPoolRow]) -> list[tuple[int, str, PlayerPoolRow]]:
        qb_rows = [row for row in lineup if row.position == "QB"]
        dst_rows = [row for row in lineup if row.position == "DST"]
        rb_rows = sorted([row for row in lineup if row.position == "RB"], key=lambda row: row.salary, reverse=True)
        wr_rows = sorted([row for row in lineup if row.position == "WR"], key=lambda row: row.salary, reverse=True)
        te_rows = sorted([row for row in lineup if row.position == "TE"], key=lambda row: row.salary, reverse=True)

        ordered: list[tuple[int, str, PlayerPoolRow]] = []
        if qb_rows:
            ordered.append((0, "QB", qb_rows[0]))
        if len(rb_rows) >= 1:
            ordered.append((1, "RB1", rb_rows[0]))
        if len(rb_rows) >= 2:
            ordered.append((2, "RB2", rb_rows[1]))
        if len(wr_rows) >= 1:
            ordered.append((3, "WR1", wr_rows[0]))
        if len(wr_rows) >= 2:
            ordered.append((4, "WR2", wr_rows[1]))
        if len(wr_rows) >= 3:
            ordered.append((5, "WR3", wr_rows[2]))
        if te_rows:
            ordered.append((6, "TE", te_rows[0]))

        used_ids = {id(row) for _idx, _slot, row in ordered}
        flex_candidates = [row for row in lineup if row.position in {"RB", "WR", "TE"} and id(row) not in used_ids]
        if flex_candidates:
            flex_row = sorted(flex_candidates, key=lambda row: row.salary, reverse=True)[0]
            ordered.append((7, "FLEX", flex_row))
        if dst_rows:
            ordered.append((8, "DST", dst_rows[0]))
        ordered.sort(key=lambda row: row[0])
        return ordered

    def _optimize_top_actual_lineups(
        self,
        *,
        players: list[PlayerPoolRow],
        top_k: int,
    ) -> list[tuple[list[PlayerPoolRow], float, int]]:
        if top_k <= 0 or not players:
            return []
        objective_scores = np.asarray([float(row.actual_points) for row in players], dtype=float)
        results = self._optimize_top_lineups_by_linear_scores(
            players=players,
            objective_scores=objective_scores,
            top_k=top_k,
            solver_name="top_actual_lineups",
        )
        if results:
            return results
        if not HAS_PULP:
            best = self.optimize_actual_lineup(players=players)
            if best is None:
                return []
            return [best]
        return []

    def _optimize_top_projected_lineups(
        self,
        *,
        players: list[PlayerPoolRow],
        top_k: int,
    ) -> list[tuple[list[PlayerPoolRow], float, int]]:
        if top_k <= 0 or not players:
            return []
        objective_scores = np.asarray(
            [
                (0.65 * float(max(0.0, row.projected_mean_points)))
                + (0.35 * float(max(0.0, row.projected_p90_points)))
                for row in players
            ],
            dtype=float,
        )
        return self._optimize_top_lineups_by_linear_scores(
            players=players,
            objective_scores=objective_scores,
            top_k=top_k,
            solver_name="top_projected_lineups",
        )

    def _optimize_top_lineups_by_linear_scores(
        self,
        *,
        players: list[PlayerPoolRow],
        objective_scores: np.ndarray,
        top_k: int,
        solver_name: str,
    ) -> list[tuple[list[PlayerPoolRow], float, int]]:
        if not HAS_PULP:
            return []
        if len(objective_scores) != len(players):
            return []

        variables: dict[int, LpVariable] = {
            idx: LpVariable(f"p_{idx}", lowBound=0, upBound=1, cat=LpBinary)
            for idx in range(len(players))
        }
        model = LpProblem(solver_name, LpMaximize)
        model += lpSum(float(objective_scores[idx]) * variables[idx] for idx in range(len(players)))

        qb_idx = [idx for idx, row in enumerate(players) if row.position == "QB"]
        rb_idx = [idx for idx, row in enumerate(players) if row.position == "RB"]
        wr_idx = [idx for idx, row in enumerate(players) if row.position == "WR"]
        te_idx = [idx for idx, row in enumerate(players) if row.position == "TE"]
        dst_idx = [idx for idx, row in enumerate(players) if row.position == "DST"]
        skill_idx = rb_idx + wr_idx + te_idx
        offense_idx = qb_idx + skill_idx

        if not qb_idx or len(rb_idx) < 2 or len(wr_idx) < 3 or not te_idx or not dst_idx:
            return []

        model += lpSum(variables[idx] for idx in qb_idx) == 1
        model += lpSum(variables[idx] for idx in dst_idx) == 1
        model += lpSum(variables[idx] for idx in rb_idx) >= 2
        model += lpSum(variables[idx] for idx in wr_idx) >= 3
        model += lpSum(variables[idx] for idx in te_idx) >= 1
        model += lpSum(variables[idx] for idx in skill_idx) == 7
        model += lpSum(variables[idx] for idx in range(len(players))) == 9
        model += lpSum(int(players[idx].salary) * variables[idx] for idx in range(len(players))) <= DK_SALARY_CAP

        for offense_i in offense_idx:
            offense_player = players[offense_i]
            for dst_i in dst_idx:
                dst_player = players[dst_i]
                if self._player_conflicts_with_dst(offense_player, dst_player):
                    model += variables[offense_i] + variables[dst_i] <= 1

        results: list[tuple[list[PlayerPoolRow], float, int]] = []
        seen_keys: set[str] = set()
        for _rank in range(top_k):
            status = model.solve(PULP_CBC_CMD(msg=False))
            status_name = LpStatus.get(status, "")
            if status_name not in {"Optimal", "Integer Feasible"}:
                break

            lineup_idx = [
                idx
                for idx in range(len(players))
                if value(variables[idx]) is not None and value(variables[idx]) > 0.5
            ]
            lineup = [players[idx] for idx in lineup_idx]
            if len(lineup) != 9 or not _lineup_satisfies_roster_rules(lineup):
                break

            lineup_key = self._lineup_key(lineup)
            if lineup_key in seen_keys:
                break
            seen_keys.add(lineup_key)

            points = float(sum(float(row.actual_points) for row in lineup))
            salary = int(sum(int(row.salary) for row in lineup))
            results.append((lineup, points, salary))

            # No-good cut: prevent selecting this exact lineup again.
            model += lpSum(variables[idx] for idx in lineup_idx) <= 8

        return results

    def _clear_actual_top_lineups_for_slice(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
    ) -> None:
        lineup_ids = self.session.execute(
            select(ActualTopLineup.actual_top_lineup_id).where(
                and_(
                    ActualTopLineup.source_system == source_system,
                    ActualTopLineup.season == season,
                    ActualTopLineup.week == week,
                    ActualTopLineup.slate == slate,
                )
            )
        ).scalars().all()
        if lineup_ids:
            self.session.query(ActualTopLineupPlayer).filter(
                ActualTopLineupPlayer.actual_top_lineup_id.in_(lineup_ids)
            ).delete(synchronize_session=False)
            self.session.query(ActualTopLineup).filter(
                ActualTopLineup.actual_top_lineup_id.in_(lineup_ids)
            ).delete(synchronize_session=False)

    def _load_top_lineup_keys_for_slice(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
        top_k: int,
    ) -> set[str]:
        rows = self.session.execute(
            select(ActualTopLineup.lineup_key).where(
                and_(
                    ActualTopLineup.source_system == source_system,
                    ActualTopLineup.season == season,
                    ActualTopLineup.week == week,
                    ActualTopLineup.slate == slate,
                    ActualTopLineup.lineup_rank <= top_k,
                )
            )
        ).scalars().all()
        return {str(row) for row in rows if row}

    def _load_stored_top_lineups_for_slice(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
        top_k: int,
        pool: list[PlayerPoolRow],
    ) -> list[list[PlayerPoolRow]]:
        headers = self.session.execute(
            select(ActualTopLineup).where(
                and_(
                    ActualTopLineup.source_system == source_system,
                    ActualTopLineup.season == season,
                    ActualTopLineup.week == week,
                    ActualTopLineup.slate == slate,
                    ActualTopLineup.lineup_rank <= top_k,
                )
            ).order_by(ActualTopLineup.lineup_rank)
        ).scalars().all()
        if not headers:
            return []

        lineup_ids = [row.actual_top_lineup_id for row in headers]
        players_rows = self.session.execute(
            select(ActualTopLineupPlayer).where(
                ActualTopLineupPlayer.actual_top_lineup_id.in_(lineup_ids)
            )
        ).scalars().all()
        by_lineup: dict[int, list[ActualTopLineupPlayer]] = defaultdict(list)
        for row in players_rows:
            by_lineup[row.actual_top_lineup_id].append(row)

        by_master: dict[str, PlayerPoolRow] = {}
        by_source: dict[str, PlayerPoolRow] = {}
        by_tuple: dict[tuple[str, str | None, str, int], PlayerPoolRow] = {}
        for row in pool:
            if row.player_master_id and row.player_master_id not in by_master:
                by_master[row.player_master_id] = row
            if row.source_player_key and row.source_player_key not in by_source:
                by_source[row.source_player_key] = row
            key = (row.name, row.team, row.position, int(row.salary))
            if key not in by_tuple:
                by_tuple[key] = row

        resolved: list[list[PlayerPoolRow]] = []
        for header in headers:
            slot_rows = sorted(
                by_lineup.get(header.actual_top_lineup_id, []),
                key=lambda row: row.slot_index,
            )
            if len(slot_rows) != 9:
                continue
            lineup: list[PlayerPoolRow] = []
            used_ids: set[str] = set()
            failed = False
            for slot in slot_rows:
                candidate: PlayerPoolRow | None = None
                if slot.player_master_id:
                    candidate = by_master.get(slot.player_master_id)
                if candidate is None and slot.source_player_key:
                    candidate = by_source.get(slot.source_player_key)
                if candidate is None:
                    candidate = by_tuple.get(
                        (slot.player_name, _canonical_team(slot.team), slot.position, int(slot.salary))
                    )
                if candidate is None or candidate.uid in used_ids:
                    failed = True
                    break
                lineup.append(candidate)
                used_ids.add(candidate.uid)
            if failed or not _lineup_satisfies_roster_rules(lineup):
                continue
            resolved.append(lineup)

        return resolved

    def build_actual_top_lineups(
        self,
        request: ActualTopLineupBuildRequest,
        progress_hook: Callable[[str], None] | None = None,
    ) -> ActualTopLineupBuildResponse:
        season_start = min(request.season_start, request.season_end)
        season_end = max(request.season_start, request.season_end)
        slices = self._fetch_available_slate_slices(
            source_system=request.source_system,
            season_start=season_start,
            season_end=season_end,
            slate_filter=request.slate,
        )
        if request.limit_slates > 0:
            slices = slices[: request.limit_slates]

        rows: list[ActualTopLineupBuildSliceResponse] = []
        rows_written = 0
        slates_completed = 0
        if progress_hook is not None:
            progress_hook(
                f"[build_actual_top] start source={request.source_system} "
                f"seasons={season_start}-{season_end} slates={len(slices)} top_k={request.top_k}"
            )
        for index, (season, week, slate) in enumerate(slices, start=1):
            try:
                existing_count = self.session.execute(
                    select(ActualTopLineup.actual_top_lineup_id).where(
                        and_(
                            ActualTopLineup.source_system == request.source_system,
                            ActualTopLineup.season == season,
                            ActualTopLineup.week == week,
                            ActualTopLineup.slate == slate,
                        )
                    )
                ).all()
                if len(existing_count) >= request.top_k and not request.overwrite_existing:
                    rows.append(
                        ActualTopLineupBuildSliceResponse(
                            source_system=request.source_system,
                            season=season,
                            week=week,
                            slate=slate,
                            status="skipped_existing",
                            rows_written=0,
                        )
                    )
                    if progress_hook is not None:
                        progress_hook(
                            f"[build_actual_top] {index}/{len(slices)} {season} W{week:02d} {slate} "
                            "status=skipped_existing rows=0"
                        )
                    continue

                if request.overwrite_existing or len(existing_count) > 0:
                    self._clear_actual_top_lineups_for_slice(
                        source_system=request.source_system,
                        season=season,
                        week=week,
                        slate=slate,
                    )

                projection_lookup, dst_projection_lookup = self._compute_player_projection_lookup(
                    source_system=request.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                )
                pool = self._fetch_slate_player_pool(
                    source_system=request.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                    projection_lookup=projection_lookup,
                    dst_projection_lookup=dst_projection_lookup,
                )
                top_lineups = self._optimize_top_actual_lineups(players=pool, top_k=request.top_k)
                if not top_lineups:
                    rows.append(
                        ActualTopLineupBuildSliceResponse(
                            source_system=request.source_system,
                            season=season,
                            week=week,
                            slate=slate,
                            status="failed",
                            rows_written=0,
                            error_message="No feasible top actual lineups found.",
                        )
                    )
                    self.session.rollback()
                    continue

                for rank, (lineup, points, salary_used) in enumerate(top_lineups, start=1):
                    header = ActualTopLineup(
                        source_system=request.source_system,
                        season=season,
                        week=week,
                        slate=slate,
                        lineup_rank=rank,
                        actual_points=float(points),
                        salary_used=int(salary_used),
                        lineup_key=self._lineup_key(lineup),
                        created_at=utcnow_naive(),
                    )
                    self.session.add(header)
                    self.session.flush()

                    for slot_index, roster_slot, player in self._canonical_slot_order(lineup):
                        self.session.add(
                            ActualTopLineupPlayer(
                                actual_top_lineup_id=header.actual_top_lineup_id,
                                slot_index=int(slot_index),
                                roster_slot=roster_slot,
                                position=player.position,
                                player_master_id=player.player_master_id,
                                source_player_key=player.source_player_key,
                                player_name=player.name,
                                team=player.team,
                                salary=int(player.salary),
                                actual_points=float(player.actual_points),
                                created_at=utcnow_naive(),
                            )
                        )

                self.session.commit()
                wrote = len(top_lineups)
                rows_written += wrote
                slates_completed += 1
                rows.append(
                    ActualTopLineupBuildSliceResponse(
                        source_system=request.source_system,
                        season=season,
                        week=week,
                        slate=slate,
                        status="ok",
                        rows_written=wrote,
                    )
                )
                if progress_hook is not None:
                    progress_hook(
                        f"[build_actual_top] {index}/{len(slices)} {season} W{week:02d} {slate} "
                        f"status=ok rows={wrote} total_rows={rows_written}"
                    )
            except Exception as exc:  # noqa: BLE001
                self.session.rollback()
                rows.append(
                    ActualTopLineupBuildSliceResponse(
                        source_system=request.source_system,
                        season=season,
                        week=week,
                        slate=slate,
                        status="failed",
                        rows_written=0,
                        error_message=str(exc),
                    )
                )
                if progress_hook is not None:
                    progress_hook(
                        f"[build_actual_top] {index}/{len(slices)} {season} W{week:02d} {slate} "
                        f"status=failed error={exc}"
                    )

        if progress_hook is not None:
            progress_hook(
                f"[build_actual_top] done slates_completed={slates_completed}/{len(slices)} "
                f"rows_written={rows_written}"
            )

        return ActualTopLineupBuildResponse(
            source_system=request.source_system,
            season_start=season_start,
            season_end=season_end,
            slate=request.slate,
            top_k=request.top_k,
            slates_total=len(slices),
            slates_completed=slates_completed,
            slates_failed=len(slices) - slates_completed,
            rows_written=rows_written,
            rows=rows,
        )

    def run_actual_top_lineup_learning(
        self,
        request: ActualTopLineupLearningRequest,
        progress_hook: Callable[[str], None] | None = None,
    ) -> ActualTopLineupLearningResponse:
        season_start = min(request.season_start, request.season_end)
        season_end = max(request.season_start, request.season_end)
        slices = self._fetch_available_slate_slices(
            source_system=request.source_system,
            season_start=season_start,
            season_end=season_end,
            slate_filter=request.slate,
        )
        rng = np.random.default_rng(request.random_seed)
        history_x: list[np.ndarray] = []
        history_y: list[np.ndarray] = []
        history_points: list[np.ndarray] = []
        rows: list[ActualTopLineupLearningSlateRowResponse] = []
        selected_points_total = 0.0
        random_points_total = 0.0
        slates_evaluated = 0
        last_weights: np.ndarray | None = None

        if progress_hook is not None:
            progress_hook(
                f"[learn_actual_top] start source={request.source_system} "
                f"seasons={season_start}-{season_end} slates={len(slices)} "
                f"top_k_label={request.top_k_label} candidates_per_slate={request.candidate_lineups_per_slate}"
            )
        for index, (season, week, slate) in enumerate(slices, start=1):
            try:
                top_keys = self._load_top_lineup_keys_for_slice(
                    source_system=request.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                    top_k=request.top_k_label,
                )
                if not top_keys:
                    msg = "No stored top actual lineups for this slate."
                    rows.append(
                        ActualTopLineupLearningSlateRowResponse(
                            season=season,
                            week=week,
                            slate=slate,
                            generated_lineups=0,
                            positives_in_pool=0,
                            selected_lineups=0,
                            selected_mean_actual_points=None,
                            random_mean_actual_points=None,
                            uplift_points=None,
                            error_message=msg,
                        )
                    )
                    if progress_hook is not None:
                        progress_hook(
                            f"[learn_actual_top] {index}/{len(slices)} {season} W{week:02d} {slate} "
                            f"status=skipped reason={msg} eval={slates_evaluated}"
                        )
                    continue

                projection_lookup, dst_projection_lookup = self._compute_player_projection_lookup(
                    source_system=request.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                )
                pool = self._fetch_slate_player_pool(
                    source_system=request.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                    projection_lookup=projection_lookup,
                    dst_projection_lookup=dst_projection_lookup,
                )
                candidate_lineups = self._generate_candidate_lineups_adaptive(
                    players=pool,
                    requested_lineups=request.candidate_lineups_per_slate,
                    min_salary_floor=36000,
                    rng=rng,
                )
                stored_top_lineups = self._load_stored_top_lineups_for_slice(
                    source_system=request.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                    top_k=request.top_k_label,
                    pool=pool,
                )
                if stored_top_lineups:
                    seen_candidate_keys = {self._lineup_key(lineup) for lineup in candidate_lineups}
                    for top_lineup in stored_top_lineups:
                        key = self._lineup_key(top_lineup)
                        if key not in seen_candidate_keys:
                            candidate_lineups.append(top_lineup)
                            seen_candidate_keys.add(key)

                x_slate = np.vstack([self._lineup_features(lineup) for lineup in candidate_lineups])
                points_slate = np.asarray(
                    [sum(player.actual_points for player in lineup) for lineup in candidate_lineups],
                    dtype=float,
                )
                y_slate = np.asarray(
                    [1.0 if self._lineup_key(lineup) in top_keys else 0.0 for lineup in candidate_lineups],
                    dtype=float,
                )
                positives = int(np.sum(y_slate))
                if positives <= 0 or positives >= len(y_slate):
                    msg = "No usable positive labels in generated candidate pool."
                    rows.append(
                        ActualTopLineupLearningSlateRowResponse(
                            season=season,
                            week=week,
                            slate=slate,
                            generated_lineups=len(candidate_lineups),
                            positives_in_pool=positives,
                            selected_lineups=0,
                            selected_mean_actual_points=None,
                            random_mean_actual_points=None,
                            uplift_points=None,
                            error_message=msg,
                        )
                    )
                    if progress_hook is not None:
                        progress_hook(
                            f"[learn_actual_top] {index}/{len(slices)} {season} W{week:02d} {slate} "
                            f"status=skipped gen={len(candidate_lineups)} pos={positives} reason={msg}"
                        )
                    continue

                train_rows = int(sum(chunk.shape[0] for chunk in history_x))
                selected_n = min(request.selection_size, len(candidate_lineups))
                if len(history_x) >= request.min_training_slates and train_rows >= request.min_training_rows:
                    x_train = np.vstack(history_x)
                    y_train = np.concatenate(history_y)
                    points_train = np.concatenate(history_points)
                    weights, bias, mean, std = self._fit_logistic(x_train, y_train)
                    last_weights = weights
                    probs = _sigmoid(((x_slate - mean) / std) @ weights + bias)
                    (
                        points_weights,
                        points_bias,
                        points_x_mean,
                        points_x_std,
                        points_y_mean,
                        points_y_std,
                        has_point_signal,
                    ) = self._fit_point_regression(x_train, points_train)
                    has_policy_signal = float(np.max(np.abs(weights))) > 1e-8
                    if not (has_policy_signal or has_point_signal):
                        msg = "No learned signal for this slate after warm-up."
                        rows.append(
                            ActualTopLineupLearningSlateRowResponse(
                                season=season,
                                week=week,
                                slate=slate,
                                generated_lineups=len(candidate_lineups),
                                positives_in_pool=positives,
                                selected_lineups=0,
                                selected_mean_actual_points=None,
                                random_mean_actual_points=None,
                                uplift_points=None,
                                error_message=msg,
                            )
                        )
                        if progress_hook is not None:
                            progress_hook(
                                f"[learn_actual_top] {index}/{len(slices)} {season} W{week:02d} {slate} "
                                f"status=skipped gen={len(candidate_lineups)} pos={positives} reason={msg}"
                            )
                        history_x.append(x_slate)
                        history_y.append(y_slate)
                        history_points.append(points_slate)
                        while len(history_x) > request.training_window_slates:
                            history_x.pop(0)
                            history_y.pop(0)
                            history_points.pop(0)
                        continue

                    expected_points = self._predict_point_regression(
                        x_rows=x_slate,
                        weights=points_weights,
                        bias=points_bias,
                        x_mean=points_x_mean,
                        x_std=points_x_std,
                        y_mean=points_y_mean,
                        y_std=points_y_std,
                    )
                    projected_mean = x_slate[:, PATTERN_FEATURE_INDEX["lineup_projected_mean"]]
                    projected_p90 = x_slate[:, PATTERN_FEATURE_INDEX["lineup_projected_p90"]]
                    composite_scores = self._composite_lineup_selection_scores(
                        policy_scores=probs,
                        expected_points=expected_points,
                        projected_mean=projected_mean,
                        projected_p90=projected_p90,
                    )
                    selected_idx = np.argsort(-composite_scores)[:selected_n]

                    random_runs = 5
                    random_means: list[float] = []
                    for _ in range(random_runs):
                        random_idx = rng.choice(len(points_slate), size=selected_n, replace=False)
                        random_means.append(float(np.mean(points_slate[random_idx])))
                    selected_mean = float(np.mean(points_slate[selected_idx]))
                    random_mean = float(np.mean(random_means))
                    uplift = selected_mean - random_mean
                    selected_points_total += selected_mean
                    random_points_total += random_mean
                    slates_evaluated += 1
                    rows.append(
                        ActualTopLineupLearningSlateRowResponse(
                            season=season,
                            week=week,
                            slate=slate,
                            generated_lineups=len(candidate_lineups),
                            positives_in_pool=positives,
                            selected_lineups=selected_n,
                            selected_mean_actual_points=selected_mean,
                            random_mean_actual_points=random_mean,
                            uplift_points=uplift,
                            error_message=None,
                        )
                    )
                    if progress_hook is not None:
                        progress_hook(
                            f"[learn_actual_top] {index}/{len(slices)} {season} W{week:02d} {slate} "
                            f"status=evaluated gen={len(candidate_lineups)} pos={positives} "
                            f"uplift={uplift:.2f} eval={slates_evaluated}"
                        )
                else:
                    msg = "Warm-up slate used for training only."
                    rows.append(
                        ActualTopLineupLearningSlateRowResponse(
                            season=season,
                            week=week,
                            slate=slate,
                            generated_lineups=len(candidate_lineups),
                            positives_in_pool=positives,
                            selected_lineups=0,
                            selected_mean_actual_points=None,
                            random_mean_actual_points=None,
                            uplift_points=None,
                            error_message=msg,
                        )
                    )
                    if progress_hook is not None:
                        progress_hook(
                            f"[learn_actual_top] {index}/{len(slices)} {season} W{week:02d} {slate} "
                            f"status=warmup gen={len(candidate_lineups)} pos={positives} "
                            f"train_rows={train_rows}"
                        )

                history_x.append(x_slate)
                history_y.append(y_slate)
                history_points.append(points_slate)
                while len(history_x) > request.training_window_slates:
                    history_x.pop(0)
                    history_y.pop(0)
                    history_points.pop(0)
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    ActualTopLineupLearningSlateRowResponse(
                        season=season,
                        week=week,
                        slate=slate,
                        generated_lineups=0,
                        positives_in_pool=0,
                        selected_lineups=0,
                        selected_mean_actual_points=None,
                        random_mean_actual_points=None,
                        uplift_points=None,
                        error_message=str(exc),
                    )
                )
                if progress_hook is not None:
                    progress_hook(
                        f"[learn_actual_top] {index}/{len(slices)} {season} W{week:02d} {slate} "
                        f"status=failed error={exc}"
                    )

        mean_selected = (selected_points_total / slates_evaluated) if slates_evaluated > 0 else None
        mean_random = (random_points_total / slates_evaluated) if slates_evaluated > 0 else None
        insights: list[LineupLearningFeatureInsightRowResponse] = []
        if last_weights is not None:
            ranked = sorted(
                enumerate(last_weights),
                key=lambda pair: abs(float(pair[1])),
                reverse=True,
            )
            for index, weight in ranked[:8]:
                insights.append(
                    LineupLearningFeatureInsightRowResponse(
                        feature_name=FEATURE_NAMES[index],
                        weight=float(weight),
                        direction="positive" if weight > 0 else "negative",
                    )
                )

        discovered_patterns = [
            f"Top-lineup label source: stored historical top-{request.top_k_label} actual lineups per slate.",
            f"Walk-forward evaluated slates: {slates_evaluated}/{len(slices)}.",
        ]
        if mean_selected is not None and mean_random is not None:
            discovered_patterns.append(
                f"Average selected vs random actual points: {mean_selected:.2f} vs {mean_random:.2f} (uplift {(mean_selected - mean_random):.2f})."
            )
        if insights:
            discovered_patterns.append(
                f"Strongest learned signal: {insights[0].feature_name} ({insights[0].weight:.3f})."
            )

        if progress_hook is not None:
            progress_hook(
                f"[learn_actual_top] done evaluated={slates_evaluated}/{len(slices)} "
                f"mean_selected={mean_selected if mean_selected is not None else 'NA'} "
                f"mean_random={mean_random if mean_random is not None else 'NA'}"
            )

        return ActualTopLineupLearningResponse(
            source_system=request.source_system,
            season_start=season_start,
            season_end=season_end,
            slate=request.slate,
            top_k_label=request.top_k_label,
            candidate_lineups_per_slate=request.candidate_lineups_per_slate,
            slates_total=len(slices),
            slates_evaluated=slates_evaluated,
            slates_warmup_or_failed=len(slices) - slates_evaluated,
            mean_selected_points=mean_selected,
            mean_random_points=mean_random,
            points_uplift=(mean_selected - mean_random) if mean_selected is not None and mean_random is not None else None,
            discovered_patterns=discovered_patterns,
            feature_insights=insights,
            rows=rows,
        )

    def _fit_policy_for_target(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        training_start_season: int,
        training_window_slates: int,
        training_lineups_per_slate: int,
        min_training_slates: int,
        min_training_rows: int,
        rng: np.random.Generator,
    ) -> tuple[np.ndarray, float, np.ndarray, np.ndarray, int, int, float]:
        target_ord = _slice_ordinal(season, week)
        slices = self._fetch_available_slate_slices(
            source_system=source_system,
            season_start=training_start_season,
            season_end=season,
            slate_filter=None,
        )
        historical = [
            item
            for item in slices
            if _slice_ordinal(item[0], item[1]) < target_ord
        ]

        x_chunks: list[np.ndarray] = []
        y_chunks: list[np.ndarray] = []
        slates_used = 0
        for hist_season, hist_week, hist_slate in reversed(historical):
            try:
                projection_lookup, dst_projection_lookup = self._compute_player_projection_lookup(
                    source_system=source_system,
                    season=hist_season,
                    week=hist_week,
                    slate=hist_slate,
                )
                pool = self._fetch_slate_player_pool(
                    source_system=source_system,
                    season=hist_season,
                    week=hist_week,
                    slate=hist_slate,
                    projection_lookup=projection_lookup,
                    dst_projection_lookup=dst_projection_lookup,
                )
                x_slate, points_slate, _ = self._generate_lineups_for_slate(
                    players=pool,
                    lineups_target=training_lineups_per_slate,
                    rng=rng,
                )
            except Exception:  # noqa: BLE001
                continue
            if float(np.max(points_slate)) <= 0.0:
                continue
            if float(np.std(points_slate)) < 1e-9:
                continue
            threshold = float(np.percentile(points_slate, TOP_TARGET_PERCENTILE))
            if not math.isfinite(threshold) or threshold <= 0.0:
                continue
            y_slate = (points_slate >= threshold).astype(float)
            positive_rate = float(np.mean(y_slate))
            if positive_rate <= 0.0 or positive_rate >= 1.0:
                continue
            x_chunks.append(x_slate)
            y_chunks.append(y_slate)
            slates_used += 1
            if slates_used >= training_window_slates:
                break

        total_rows = int(sum(chunk.shape[0] for chunk in x_chunks))
        if slates_used < min_training_slates or total_rows < min_training_rows:
            zero_weights = np.zeros(len(FEATURE_NAMES), dtype=float)
            return zero_weights, 0.0, np.zeros(len(FEATURE_NAMES)), np.ones(len(FEATURE_NAMES)), slates_used, total_rows, 0.0

        x_train = np.vstack(list(reversed(x_chunks)))
        y_train = np.concatenate(list(reversed(y_chunks)))
        weights, bias, mean, std = self._fit_logistic(x_train, y_train)
        return weights, bias, mean, std, slates_used, total_rows, float(np.mean(y_train))

    def _generate_candidate_lineups(
        self,
        *,
        players: list[PlayerPoolRow],
        candidate_lineups: int,
        min_salary_floor: int,
        rng: np.random.Generator,
        min_required_lineups: int | None = None,
        max_attempts_multiplier: int = 6,
        player_sampling_multipliers: dict[str, float] | None = None,
    ) -> list[list[PlayerPoolRow]]:
        by_pos: dict[str, list[PlayerPoolRow]] = defaultdict(list)
        for player in players:
            by_pos[player.position].append(player)
        if (
            len(by_pos["QB"]) < 1
            or len(by_pos["RB"]) < 2
            or len(by_pos["WR"]) < 3
            or len(by_pos["TE"]) < 1
            or len(by_pos["DST"]) < 1
        ):
            raise ValueError("Insufficient player pool for lineup construction.")

        def weighted_pick(rows: list[PlayerPoolRow], count: int, selected: set[str]) -> list[PlayerPoolRow] | None:
            eligible = [row for row in rows if row.uid not in selected]
            if len(eligible) < count:
                return None
            weights = np.asarray(
                [
                    max(0.5, row.projected_p90_points + 0.4 * row.projected_mean_points)
                    * (6000.0 / max(2000.0, float(row.salary))) ** 0.2
                    for row in eligible
                ],
                dtype=float,
            )
            if player_sampling_multipliers:
                weights = weights * np.asarray(
                    [max(0.05, float(player_sampling_multipliers.get(row.uid, 1.0))) for row in eligible],
                    dtype=float,
                )
            if float(np.sum(weights)) <= 0:
                weights = np.ones(len(eligible), dtype=float)
            weights = weights / np.sum(weights)
            idx = rng.choice(len(eligible), size=count, replace=False, p=weights)
            return [eligible[int(i)] for i in idx]

        lineups: list[list[PlayerPoolRow]] = []
        seen_keys: set[tuple[str, ...]] = set()
        attempts = 0
        max_attempts = max(candidate_lineups * max_attempts_multiplier, 12000)
        while len(lineups) < candidate_lineups and attempts < max_attempts:
            attempts += 1
            selected: set[str] = set()
            qb = weighted_pick(by_pos["QB"], 1, selected)
            if qb is None:
                continue
            selected.update(row.uid for row in qb)
            rb = weighted_pick(by_pos["RB"], 2, selected)
            if rb is None:
                continue
            selected.update(row.uid for row in rb)
            wr = weighted_pick(by_pos["WR"], 3, selected)
            if wr is None:
                continue
            selected.update(row.uid for row in wr)
            te = weighted_pick(by_pos["TE"], 1, selected)
            if te is None:
                continue
            selected.update(row.uid for row in te)
            flex_pool = by_pos["RB"] + by_pos["WR"] + by_pos["TE"]
            flex = weighted_pick(flex_pool, 1, selected)
            if flex is None:
                continue
            selected.update(row.uid for row in flex)
            dst = weighted_pick(by_pos["DST"], 1, selected)
            if dst is None:
                continue

            lineup = qb + rb + wr + te + flex + dst
            if not _lineup_satisfies_roster_rules(lineup):
                continue
            salary = int(sum(row.salary for row in lineup))
            if salary > DK_SALARY_CAP or salary < min_salary_floor:
                continue
            key = tuple(sorted(row.uid for row in lineup))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            lineups.append(lineup)

        min_required = min_required_lineups
        if min_required is None:
            min_required = min(candidate_lineups, max(200, candidate_lineups // 30))
        min_required = max(1, int(min_required))
        if len(lineups) < min_required:
            raise ValueError(
                f"Could not generate enough valid candidate lineups ({len(lineups)}). "
                "Try lower min_salary_floor or a larger player pool."
            )
        return lineups

    def _enumerate_candidate_lineups_small_pool(
        self,
        *,
        players: list[PlayerPoolRow],
        limit: int,
        min_salary_floor: int,
    ) -> list[list[PlayerPoolRow]]:
        by_pos: dict[str, list[PlayerPoolRow]] = defaultdict(list)
        for player in players:
            by_pos[player.position].append(player)
        if (
            len(by_pos["QB"]) < 1
            or len(by_pos["RB"]) < 2
            or len(by_pos["WR"]) < 3
            or len(by_pos["TE"]) < 1
            or len(by_pos["DST"]) < 1
        ):
            return []

        n_qb = len(by_pos["QB"])
        n_rb = len(by_pos["RB"])
        n_wr = len(by_pos["WR"])
        n_te = len(by_pos["TE"])
        n_dst = len(by_pos["DST"])
        skill_count = n_rb + n_wr + n_te
        if skill_count < 7:
            return []

        try:
            approx = (
                n_qb
                * math.comb(n_rb, 2)
                * math.comb(n_wr, 3)
                * n_te
                * (skill_count - 6)
                * n_dst
            )
        except ValueError:
            return []
        if approx > 3_000_000:
            # Not a tiny slate; enumeration would be too expensive.
            return []

        lineups: list[list[PlayerPoolRow]] = []
        seen_keys: set[tuple[str, ...]] = set()
        target = max(1, int(limit))
        salary_floor = max(0, int(min_salary_floor))
        rb_rows = by_pos["RB"]
        wr_rows = by_pos["WR"]
        te_rows = by_pos["TE"]
        dst_rows = by_pos["DST"]
        for qb in by_pos["QB"]:
            for rb_pair in combinations(rb_rows, 2):
                rb_ids = {row.uid for row in rb_pair}
                for wr_triplet in combinations(wr_rows, 3):
                    wr_ids = {row.uid for row in wr_triplet}
                    for te in te_rows:
                        if te.uid in rb_ids or te.uid in wr_ids:
                            continue
                        used_ids = {qb.uid, te.uid, *rb_ids, *wr_ids}
                        flex_pool = [
                            row
                            for row in (rb_rows + wr_rows + te_rows)
                            if row.uid not in used_ids
                        ]
                        if not flex_pool:
                            continue
                        for flex in flex_pool:
                            if flex.uid in used_ids:
                                continue
                            for dst in dst_rows:
                                if dst.uid in used_ids or dst.uid == flex.uid:
                                    continue
                                lineup = [qb, *list(rb_pair), *list(wr_triplet), te, flex, dst]
                                if not _lineup_satisfies_roster_rules(lineup):
                                    continue
                                salary = int(sum(row.salary for row in lineup))
                                if salary > DK_SALARY_CAP or salary < salary_floor:
                                    continue
                                key = tuple(sorted(row.uid for row in lineup))
                                if key in seen_keys:
                                    continue
                                seen_keys.add(key)
                                lineups.append(lineup)
                                if len(lineups) >= target:
                                    return lineups
        return lineups

    def _generate_candidate_lineups_adaptive(
        self,
        *,
        players: list[PlayerPoolRow],
        requested_lineups: int,
        min_salary_floor: int,
        rng: np.random.Generator,
        player_sampling_multipliers: dict[str, float] | None = None,
    ) -> list[list[PlayerPoolRow]]:
        target = max(100, int(requested_lineups))
        base_floor = max(0, int(min_salary_floor))
        attempts_plan: list[tuple[int, int, int, int]] = [
            (target, base_floor, min(target, max(200, target // 30)), 6),
            (min(target, 2200), max(28000, base_floor - 3000), 120, 8),
            (min(target, 1600), 24000, 100, 10),
            (min(target, 1200), 20000, 80, 12),
            (min(target, 900), 12000, 60, 14),
            (min(target, 700), 0, 40, 18),
            (min(target, 500), 0, 25, 24),
        ]
        seen_plan: set[tuple[int, int, int, int]] = set()
        plan: list[tuple[int, int, int, int]] = []
        for item in attempts_plan:
            normalized = (
                max(100, int(item[0])),
                max(0, int(item[1])),
                max(1, int(item[2])),
                max(1, int(item[3])),
            )
            if normalized not in seen_plan:
                seen_plan.add(normalized)
                plan.append(normalized)

        last_error: Exception | None = None
        for candidate_count, floor_value, min_required, attempts_multiplier in plan:
            try:
                return self._generate_candidate_lineups(
                    players=players,
                    candidate_lineups=candidate_count,
                    min_salary_floor=floor_value,
                    rng=rng,
                    min_required_lineups=min_required,
                    max_attempts_multiplier=attempts_multiplier,
                    player_sampling_multipliers=player_sampling_multipliers,
                )
            except ValueError as exc:
                last_error = exc
                continue

        enum_target = max(120, min(requested_lineups, 600))
        enumerated = self._enumerate_candidate_lineups_small_pool(
            players=players,
            limit=enum_target,
            min_salary_floor=0,
        )
        if len(enumerated) >= 20:
            return enumerated

        solver_target = max(120, min(requested_lineups, 200))
        projected_candidates = self._optimize_top_projected_lineups(
            players=players,
            top_k=solver_target,
        )
        if projected_candidates:
            projected_lineups = [lineup for lineup, _obj, _salary in projected_candidates]
            if len(projected_lineups) >= 20:
                return projected_lineups
            last_error = ValueError(
                "Projected MILP fallback produced too few candidate lineups "
                f"({len(projected_lineups)})."
            )

        if last_error is not None:
            raise ValueError(
                f"Adaptive candidate generation failed after {len(plan)} strategies: {last_error}"
            ) from last_error
        raise ValueError("Adaptive candidate generation failed with unknown error.")

    def _fit_logistic(self, x_train: np.ndarray, y_train: np.ndarray) -> tuple[np.ndarray, float, np.ndarray, np.ndarray]:
        mean = np.mean(x_train, axis=0)
        std = np.std(x_train, axis=0)
        std = np.where(std < 1e-6, 1.0, std)
        xs = (x_train - mean) / std

        pos_rate = float(np.mean(y_train))
        if pos_rate <= 0 or pos_rate >= 1:
            return np.zeros(xs.shape[1], dtype=float), 0.0, mean, std

        bias = math.log(pos_rate / (1.0 - pos_rate))
        weights = np.zeros(xs.shape[1], dtype=float)
        lr = 0.06
        l2 = 0.0002
        for _ in range(360):
            logits = xs @ weights + bias
            probs = _sigmoid(logits)
            error = probs - y_train
            grad_w = (xs.T @ error) / len(xs) + (l2 * weights)
            grad_b = float(np.mean(error))
            weights -= lr * grad_w
            bias -= lr * grad_b
        return weights, bias, mean, std

    def _fit_point_regression(
        self,
        x_train: np.ndarray,
        points_train: np.ndarray,
    ) -> tuple[np.ndarray, float, np.ndarray, np.ndarray, float, float, bool]:
        if len(x_train) < 200 or len(points_train) < 200:
            dim = x_train.shape[1] if x_train.ndim == 2 else len(FEATURE_NAMES)
            return (
                np.zeros(dim, dtype=float),
                0.0,
                np.zeros(dim, dtype=float),
                np.ones(dim, dtype=float),
                0.0,
                1.0,
                False,
            )

        x_mean = np.mean(x_train, axis=0)
        x_std = np.std(x_train, axis=0)
        x_std = np.where(x_std < 1e-6, 1.0, x_std)
        xs = (x_train - x_mean) / x_std

        y_mean = float(np.mean(points_train))
        y_std = float(np.std(points_train))
        if y_std < 1e-9:
            dim = x_train.shape[1]
            return (
                np.zeros(dim, dtype=float),
                0.0,
                x_mean,
                x_std,
                y_mean,
                1.0,
                False,
            )
        ys = (points_train - y_mean) / y_std

        design = np.column_stack([xs, np.ones(len(xs), dtype=float)])
        reg = 0.08
        gram = design.T @ design
        for idx in range(xs.shape[1]):
            gram[idx, idx] += reg
        rhs = design.T @ ys
        try:
            coeff = np.linalg.solve(gram, rhs)
        except np.linalg.LinAlgError:
            coeff = np.linalg.pinv(gram) @ rhs

        weights = coeff[: xs.shape[1]].astype(float)
        bias = float(coeff[xs.shape[1]])
        has_signal = float(np.max(np.abs(weights))) > 1e-8
        return weights, bias, x_mean, x_std, y_mean, y_std, has_signal

    def _predict_point_regression(
        self,
        *,
        x_rows: np.ndarray,
        weights: np.ndarray,
        bias: float,
        x_mean: np.ndarray,
        x_std: np.ndarray,
        y_mean: float,
        y_std: float,
    ) -> np.ndarray:
        if x_rows.size == 0:
            return np.asarray([], dtype=float)
        xs = (x_rows - x_mean) / x_std
        y_norm = xs @ weights + bias
        return y_mean + (y_std * y_norm)

    def _composite_lineup_selection_scores(
        self,
        *,
        policy_scores: np.ndarray,
        expected_points: np.ndarray,
        projected_mean: np.ndarray,
        projected_p90: np.ndarray,
        blend_weights: np.ndarray | None = None,
    ) -> np.ndarray:
        if blend_weights is None:
            blend_weights = np.asarray([0.58, 0.27, 0.10, 0.05], dtype=float)
        blend = np.asarray(blend_weights, dtype=float)
        if blend.shape[0] != 4 or not np.isfinite(blend).all():
            blend = np.asarray([0.58, 0.27, 0.10, 0.05], dtype=float)
        blend_sum = float(np.sum(blend))
        if blend_sum <= 1e-9:
            blend = np.asarray([0.58, 0.27, 0.10, 0.05], dtype=float)
            blend_sum = float(np.sum(blend))
        blend = blend / blend_sum
        return (
            (float(blend[0]) * _zscore(expected_points))
            + (float(blend[1]) * _zscore(policy_scores))
            + (float(blend[2]) * _zscore(projected_p90))
            + (float(blend[3]) * _zscore(projected_mean))
        )

    def _score_rank_correlation(self, score_values: np.ndarray, points_values: np.ndarray) -> float:
        score_arr = np.asarray(score_values, dtype=float)
        points_arr = np.asarray(points_values, dtype=float)
        if score_arr.shape[0] < 8 or points_arr.shape[0] != score_arr.shape[0]:
            return 0.0
        if not np.isfinite(score_arr).all() or not np.isfinite(points_arr).all():
            return 0.0

        order_score = np.argsort(score_arr, kind="mergesort")
        order_points = np.argsort(points_arr, kind="mergesort")
        rank_score = np.empty(score_arr.shape[0], dtype=float)
        rank_points = np.empty(points_arr.shape[0], dtype=float)
        rank_score[order_score] = np.arange(score_arr.shape[0], dtype=float)
        rank_points[order_points] = np.arange(points_arr.shape[0], dtype=float)

        score_std = float(np.std(rank_score))
        points_std = float(np.std(rank_points))
        if score_std < 1e-9 or points_std < 1e-9:
            return 0.0
        corr = float(np.corrcoef(rank_score, rank_points)[0, 1])
        if not math.isfinite(corr):
            return 0.0
        return corr

    def _fit_backtest_composite_blend(
        self,
        *,
        history_x: list[np.ndarray],
        history_points: list[np.ndarray],
        policy_weights: np.ndarray,
        policy_bias: float,
        policy_mean: np.ndarray,
        policy_std: np.ndarray,
        point_weights: np.ndarray,
        point_bias: float,
        point_x_mean: np.ndarray,
        point_x_std: np.ndarray,
        point_y_mean: float,
        point_y_std: float,
        projected_mean_idx: int,
        projected_p90_idx: int,
    ) -> np.ndarray:
        default_blend = np.asarray([0.58, 0.27, 0.10, 0.05], dtype=float)
        if len(history_x) < 8:
            return default_blend

        split_idx = int(len(history_x) * 0.8)
        split_idx = max(4, split_idx)
        split_idx = min(split_idx, len(history_x) - 2)
        if split_idx < 4 or (len(history_x) - split_idx) < 2:
            return default_blend

        train_rows: list[np.ndarray] = []
        train_points: list[np.ndarray] = []
        valid_rows: list[np.ndarray] = []
        valid_points: list[np.ndarray] = []

        for idx, (x_chunk, points_chunk) in enumerate(zip(history_x, history_points)):
            if x_chunk.size == 0 or points_chunk.size == 0:
                continue
            policy_chunk = _sigmoid(((x_chunk - policy_mean) / policy_std) @ policy_weights + policy_bias)
            expected_chunk = self._predict_point_regression(
                x_rows=x_chunk,
                weights=point_weights,
                bias=point_bias,
                x_mean=point_x_mean,
                x_std=point_x_std,
                y_mean=point_y_mean,
                y_std=point_y_std,
            )
            features_chunk = np.column_stack(
                [
                    _zscore(expected_chunk),
                    _zscore(policy_chunk),
                    _zscore(x_chunk[:, projected_p90_idx]),
                    _zscore(x_chunk[:, projected_mean_idx]),
                ]
            )
            if idx < split_idx:
                train_rows.append(features_chunk)
                train_points.append(np.asarray(points_chunk, dtype=float))
            else:
                valid_rows.append(features_chunk)
                valid_points.append(np.asarray(points_chunk, dtype=float))

        if not train_rows or not valid_rows:
            return default_blend

        x_train = np.vstack(train_rows)
        y_train = np.concatenate(train_points)
        x_valid = np.vstack(valid_rows)
        y_valid = np.concatenate(valid_points)
        if x_train.shape[0] < 400 or x_valid.shape[0] < 120:
            return default_blend

        y_mean = float(np.mean(y_train))
        y_std = float(np.std(y_train))
        if y_std < 1e-9:
            return default_blend
        y_norm = (y_train - y_mean) / y_std

        design = np.column_stack([x_train, np.ones(x_train.shape[0], dtype=float)])
        gram = design.T @ design
        ridge = 0.10
        for j in range(x_train.shape[1]):
            gram[j, j] += ridge
        rhs = design.T @ y_norm
        try:
            coeff = np.linalg.solve(gram, rhs)
        except np.linalg.LinAlgError:
            coeff = np.linalg.pinv(gram) @ rhs

        learned_weights = np.maximum(coeff[:4].astype(float), 0.0)
        learned_sum = float(np.sum(learned_weights))
        if learned_sum <= 1e-9:
            return default_blend
        learned_weights = learned_weights / learned_sum

        learned_valid_scores = x_valid @ learned_weights
        baseline_valid_scores = x_valid @ default_blend
        corr_lift = self._score_rank_correlation(learned_valid_scores, y_valid) - self._score_rank_correlation(
            baseline_valid_scores, y_valid
        )
        if not math.isfinite(corr_lift) or corr_lift <= 0.003:
            return default_blend

        alpha = _clamp(corr_lift / 0.05, 0.0, 1.0)
        blended = ((1.0 - alpha) * default_blend) + (alpha * learned_weights)
        blended = blended / max(1e-9, float(np.sum(blended)))
        return blended

    def run_walk_forward_learning(self, request: LineupLearningRequest) -> LineupLearningResponse:
        season_start = min(request.season_start, request.season_end)
        season_end = max(request.season_start, request.season_end)
        slices = self._fetch_available_slate_slices(
            source_system=request.source_system,
            season_start=season_start,
            season_end=season_end,
            slate_filter=request.slate,
        )
        if not slices:
            raise ValueError(
                f"No curated salary slices found for {request.source_system} seasons {season_start}-{season_end}."
            )

        rng = np.random.default_rng(request.random_seed)
        history_x: list[np.ndarray] = []
        history_y: list[np.ndarray] = []
        slate_rows: list[LineupLearningSlateResultRowResponse] = []
        pattern_counts: dict[str, int] = defaultdict(int)
        pattern_success_counts: dict[str, float] = defaultdict(float)
        global_success_total = 0.0
        global_row_total = 0

        selected_points_total = 0.0
        random_points_total = 0.0
        selected_top_rate_total = 0.0
        random_top_rate_total = 0.0
        evaluated_slates = 0
        discovered_weights: np.ndarray | None = None

        for season, week, slate in slices:
            try:
                projection_lookup, dst_projection_lookup = self._compute_player_projection_lookup(
                    source_system=request.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                )
                pool = self._fetch_slate_player_pool(
                    source_system=request.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                    projection_lookup=projection_lookup,
                    dst_projection_lookup=dst_projection_lookup,
                )
                x_slate, points_slate, _ = self._generate_lineups_for_slate(
                    players=pool,
                    lineups_target=request.lineups_per_slate,
                    rng=rng,
                )
            except Exception as exc:  # noqa: BLE001
                slate_rows.append(
                    LineupLearningSlateResultRowResponse(
                        season=season,
                        week=week,
                        slate=slate,
                        generated_lineups=0,
                        selected_lineups=0,
                        mean_selected_points=None,
                        mean_random_points=None,
                        selected_top1pct_rate=None,
                        random_top1pct_rate=None,
                        uplift_points=None,
                        uplift_top1pct_rate=None,
                        error_message=str(exc),
                    )
                )
                continue

            top_threshold = float(np.percentile(points_slate, 98.0))
            y_slate = (points_slate >= top_threshold).astype(float)
            global_success_total += float(np.sum(y_slate))
            global_row_total += int(len(y_slate))
            double_stack_mask = x_slate[:, PATTERN_FEATURE_INDEX["double_stack_flag"]] >= 0.5
            bringback_mask = x_slate[:, PATTERN_FEATURE_INDEX["bringback_flag"]] >= 0.5
            cheap_two_mask = x_slate[:, PATTERN_FEATURE_INDEX["cheap_count"]] >= 2.0
            no_bringback_mask = x_slate[:, PATTERN_FEATURE_INDEX["qb_opponent_players"]] <= 0.0
            pattern_masks = {
                "double_stack": double_stack_mask,
                "bringback": bringback_mask,
                "double_stack_with_bringback": np.logical_and(double_stack_mask, bringback_mask),
                "cheap_count_ge_2": cheap_two_mask,
                "no_qb_bringback": no_bringback_mask,
            }
            for name, mask in pattern_masks.items():
                count = int(np.sum(mask))
                if count <= 0:
                    continue
                pattern_counts[name] += count
                pattern_success_counts[name] += float(np.sum(y_slate[mask]))

            selected_n = min(request.selection_size, len(points_slate))
            if selected_n < 1:
                selected_n = max(1, len(points_slate) // 20)

            train_rows = int(sum(chunk.shape[0] for chunk in history_x))
            if len(history_x) >= request.min_training_slates and train_rows >= request.min_training_rows:
                x_train = np.vstack(history_x)
                y_train = np.concatenate(history_y)
                weights, bias, mean, std = self._fit_logistic(x_train, y_train)
                discovered_weights = weights
                x_norm = (x_slate - mean) / std
                probs = _sigmoid(x_norm @ weights + bias)
                selected_idx = np.argsort(-probs)[:selected_n]

                random_runs = 7
                random_means: list[float] = []
                random_top_rates: list[float] = []
                top1_threshold = float(np.percentile(points_slate, 99.0))
                for _ in range(random_runs):
                    random_idx = rng.choice(len(points_slate), size=selected_n, replace=False)
                    random_points = points_slate[random_idx]
                    random_means.append(float(np.mean(random_points)))
                    random_top_rates.append(float(np.mean(random_points >= top1_threshold)))

                selected_points = points_slate[selected_idx]
                selected_mean = float(np.mean(selected_points))
                selected_top_rate = float(np.mean(selected_points >= top1_threshold))
                random_mean = float(np.mean(random_means))
                random_top_rate = float(np.mean(random_top_rates))

                selected_points_total += selected_mean
                random_points_total += random_mean
                selected_top_rate_total += selected_top_rate
                random_top_rate_total += random_top_rate
                evaluated_slates += 1

                slate_rows.append(
                    LineupLearningSlateResultRowResponse(
                        season=season,
                        week=week,
                        slate=slate,
                        generated_lineups=len(points_slate),
                        selected_lineups=selected_n,
                        mean_selected_points=selected_mean,
                        mean_random_points=random_mean,
                        selected_top1pct_rate=selected_top_rate,
                        random_top1pct_rate=random_top_rate,
                        uplift_points=selected_mean - random_mean,
                        uplift_top1pct_rate=selected_top_rate - random_top_rate,
                        error_message=None,
                    )
                )
            else:
                slate_rows.append(
                    LineupLearningSlateResultRowResponse(
                        season=season,
                        week=week,
                        slate=slate,
                        generated_lineups=len(points_slate),
                        selected_lineups=0,
                        mean_selected_points=None,
                        mean_random_points=None,
                        selected_top1pct_rate=None,
                        random_top1pct_rate=None,
                        uplift_points=None,
                        uplift_top1pct_rate=None,
                        error_message="Warm-up slate used for training only.",
                    )
                )

            history_x.append(x_slate)
            history_y.append(y_slate)
            while len(history_x) > request.training_window_slates:
                history_x.pop(0)
                history_y.pop(0)

        mean_selected_points = (
            (selected_points_total / evaluated_slates) if evaluated_slates > 0 else None
        )
        mean_random_points = (random_points_total / evaluated_slates) if evaluated_slates > 0 else None
        mean_selected_top = (selected_top_rate_total / evaluated_slates) if evaluated_slates > 0 else None
        mean_random_top = (random_top_rate_total / evaluated_slates) if evaluated_slates > 0 else None

        feature_insights: list[LineupLearningFeatureInsightRowResponse] = []
        if discovered_weights is not None:
            ranked = sorted(
                enumerate(discovered_weights),
                key=lambda pair: abs(float(pair[1])),
                reverse=True,
            )
            for index, weight in ranked[:8]:
                direction = "positive" if weight > 0 else "negative"
                feature_insights.append(
                    LineupLearningFeatureInsightRowResponse(
                        feature_name=FEATURE_NAMES[index],
                        weight=float(weight),
                        direction=direction,
                    )
                )

        discovered_patterns: list[str] = []
        global_success_rate = (global_success_total / global_row_total) if global_row_total > 0 else 0.0
        if feature_insights:
            discovered_patterns.append(
                "Top learned features ranked by predictive weight are included below."
            )
            best_positive = next((row for row in feature_insights if row.weight > 0), None)
            best_negative = next((row for row in feature_insights if row.weight < 0), None)
            if best_positive:
                discovered_patterns.append(
                    f"Most positive signal: {best_positive.feature_name} (weight {best_positive.weight:.3f})."
                )
            if best_negative:
                discovered_patterns.append(
                    f"Most negative signal: {best_negative.feature_name} (weight {best_negative.weight:.3f})."
                )
        if mean_selected_points is not None and mean_random_points is not None:
            discovered_patterns.append(
                f"Walk-forward average lineup points uplift: {(mean_selected_points - mean_random_points):.2f}."
            )
        if mean_selected_top is not None and mean_random_top is not None:
            discovered_patterns.append(
                "Walk-forward top-1% lineup hit-rate uplift: "
                f"{(mean_selected_top - mean_random_top) * 100:.2f} percentage points."
            )
        if global_success_rate > 0:
            lifts: list[tuple[str, float, int, float]] = []
            for name, count in pattern_counts.items():
                if count < 5000:
                    continue
                success_rate = pattern_success_counts[name] / count
                lift = (success_rate - global_success_rate) / global_success_rate
                lifts.append((name, lift, count, success_rate))
            lifts.sort(key=lambda row: row[1], reverse=True)
            for name, lift, count, success_rate in lifts[:3]:
                discovered_patterns.append(
                    f"Pattern lift: {name} success_rate={success_rate:.2%} over baseline {global_success_rate:.2%} "
                    f"(lift {lift * 100:.1f}%, n={count})."
                )

        return LineupLearningResponse(
            source_system=request.source_system,
            season_start=season_start,
            season_end=season_end,
            slate=request.slate,
            lineups_per_slate=request.lineups_per_slate,
            slates_total=len(slices),
            slates_evaluated=evaluated_slates,
            slates_warmup_or_failed=len(slices) - evaluated_slates,
            mean_selected_points=mean_selected_points,
            mean_random_points=mean_random_points,
            points_uplift=(mean_selected_points - mean_random_points)
            if mean_selected_points is not None and mean_random_points is not None
            else None,
            mean_selected_top1pct_rate=mean_selected_top,
            mean_random_top1pct_rate=mean_random_top,
            top1pct_rate_uplift=(mean_selected_top - mean_random_top)
            if mean_selected_top is not None and mean_random_top is not None
            else None,
            discovered_patterns=discovered_patterns,
            feature_insights=feature_insights,
            rows=slate_rows,
        )

    def run_optimal_vs_predicted_backtest(
        self,
        request: OptimalVsPredictedBacktestRequest,
        progress_hook: Callable[[str], None] | None = None,
    ) -> OptimalVsPredictedBacktestResponse:
        season_start = min(request.season_start, request.season_end)
        season_end = max(request.season_start, request.season_end)
        rng = np.random.default_rng(request.random_seed)

        slices = self._fetch_available_slate_slices(
            source_system=request.source_system,
            season_start=season_start,
            season_end=season_end,
            slate_filter=request.slate,
        )
        slices = self._filter_slices_by_slate_type(
            source_system=request.source_system,
            slices=slices,
            slate_type=request.slate_type,
        )
        if request.limit_slates > 0:
            slices = slices[: request.limit_slates]

        rows: list[OptimalVsPredictedBacktestRowResponse] = []
        gaps: list[float] = []
        history_x: list[np.ndarray] = []
        history_y: list[np.ndarray] = []
        history_points: list[np.ndarray] = []
        last_logged_composite_blend: np.ndarray | None = None
        captain_model: ShowdownCaptainArchetypeModel | None = None
        captain_prior_strength = float(getattr(request, "showdown_captain_prior_strength", 0.0) or 0.0)
        captain_model_path = getattr(request, "showdown_captain_model_path", None)
        classic_value_model: ClassicValueDriverModel | None = None
        classic_value_prior_strength = float(getattr(request, "classic_value_driver_prior_strength", 0.0) or 0.0)
        classic_value_model_path = getattr(request, "classic_value_driver_model_path", None)
        matchup_outcome_model: MatchupOutcomeIntelligenceModel | None = None
        matchup_outcome_prior_strength = float(getattr(request, "matchup_outcome_prior_strength", 0.0) or 0.0)
        matchup_outcome_model_path = getattr(request, "matchup_outcome_model_path", None)
        matchup_prior_gate_model: MatchupPriorGateModel | None = None
        matchup_prior_gate_model_path = getattr(request, "matchup_prior_gate_model_path", None)
        if (
            request.slate_type == "showdown"
            and captain_prior_strength > 0.0
            and captain_model_path
        ):
            captain_model = self._load_showdown_captain_archetype_model(captain_model_path)
        if (
            request.slate_type == "classic"
            and classic_value_prior_strength > 0.0
            and classic_value_model_path
        ):
            classic_value_model = self._load_classic_value_driver_model(classic_value_model_path)
        if (
            request.slate_type == "classic"
            and matchup_outcome_prior_strength > 0.0
            and matchup_outcome_model_path
        ):
            matchup_outcome_model = self._load_matchup_outcome_model(matchup_outcome_model_path)
            if matchup_prior_gate_model_path:
                matchup_prior_gate_model = self._load_matchup_prior_gate_model(matchup_prior_gate_model_path)

        if progress_hook is not None:
            progress_hook(
                f"[optimal_vs_predicted] start source={request.source_system} "
                f"seasons={season_start}-{season_end} type={request.slate_type} slates={len(slices)} "
                f"lineups_per_slate={request.lineups_per_slate}"
            )

        for index, (season, week, slate) in enumerate(slices, start=1):
            try:
                projection_lookup, dst_projection_lookup = self._compute_player_projection_lookup(
                    source_system=request.source_system,
                    season=season,
                    week=week,
                    slate=slate,
                )

                if request.slate_type == "showdown":
                    showdown_pool = self._fetch_showdown_player_pool(
                        source_system=request.source_system,
                        season=season,
                        week=week,
                        slate=slate,
                        projection_lookup=projection_lookup,
                        dst_projection_lookup=dst_projection_lookup,
                    )
                    optimal_showdown = self.optimize_actual_showdown_lineup(players=showdown_pool)
                    if optimal_showdown is None:
                        rows.append(
                            OptimalVsPredictedBacktestRowResponse(
                                season=season,
                                week=week,
                                slate=slate,
                                slate_type="showdown",
                                status="skipped",
                                error_message="No feasible actual-optimal showdown lineup.",
                            )
                        )
                        if progress_hook is not None:
                            progress_hook(
                                f"[optimal_vs_predicted] {index}/{len(slices)} {season} W{week:02d} {slate} "
                                "type=showdown status=skipped"
                            )
                        continue

                    optimal_lineup, optimal_points, optimal_salary = optimal_showdown
                    captain_position_probs: dict[str, float] | None = None
                    if captain_model is not None:
                        captain_position_probs = self._predict_showdown_captain_position_probs(
                            showdown_pool,
                            captain_model,
                        )
                    x_slate, points_slate, generated_showdown = self._generate_showdown_lineups_for_slate(
                        players=showdown_pool,
                        lineups_target=request.lineups_per_slate,
                        rng=rng,
                        captain_position_probs=captain_position_probs,
                        captain_prior_strength=captain_prior_strength,
                    )
                    if len(generated_showdown) == 0:
                        rows.append(
                            OptimalVsPredictedBacktestRowResponse(
                                season=season,
                                week=week,
                                slate=slate,
                                slate_type="showdown",
                                status="failed",
                                error_message="No generated showdown candidate lineups.",
                            )
                        )
                        if progress_hook is not None:
                            progress_hook(
                                f"[optimal_vs_predicted] {index}/{len(slices)} {season} W{week:02d} {slate} "
                                "type=showdown status=failed error=no_candidates"
                            )
                        continue
                    projected_mean = x_slate[:, SHOWDOWN_FEATURE_INDEX["lineup_projected_mean"]]
                    projected_p90 = x_slate[:, SHOWDOWN_FEATURE_INDEX["lineup_projected_p90"]]
                    projected_mean_idx = SHOWDOWN_FEATURE_INDEX["lineup_projected_mean"]
                    projected_p90_idx = SHOWDOWN_FEATURE_INDEX["lineup_projected_p90"]
                    threshold_percentile = SHOWDOWN_TOP_TARGET_PERCENTILE
                    classic_prior_scores: np.ndarray | None = None
                else:
                    classic_pool = self._fetch_slate_player_pool(
                        source_system=request.source_system,
                        season=season,
                        week=week,
                        slate=slate,
                        projection_lookup=projection_lookup,
                        dst_projection_lookup=dst_projection_lookup,
                    )
                    optimal_classic = self.optimize_actual_lineup(players=classic_pool)
                    if optimal_classic is None:
                        rows.append(
                            OptimalVsPredictedBacktestRowResponse(
                                season=season,
                                week=week,
                                slate=slate,
                                slate_type="classic",
                                status="skipped",
                                error_message="No feasible actual-optimal lineup.",
                            )
                        )
                        if progress_hook is not None:
                            progress_hook(
                                f"[optimal_vs_predicted] {index}/{len(slices)} {season} W{week:02d} {slate} "
                                "type=classic status=skipped"
                            )
                        continue

                    optimal_lineup, optimal_points, optimal_salary = optimal_classic
                    effective_matchup_prior_strength, gate_score, gate_active = self._effective_matchup_prior_strength(
                        requested_strength=matchup_outcome_prior_strength,
                        gate_model=matchup_prior_gate_model,
                        slate=slate,
                        players=classic_pool,
                    )
                    if (
                        progress_hook is not None
                        and matchup_prior_gate_model is not None
                    ):
                        progress_hook(
                            f"[optimal_vs_predicted] gate {season} W{week:02d} {slate} "
                            f"score={gate_score:.3f} active={gate_active}"
                        )
                    classic_sampling_multipliers = self._classic_player_sampling_multipliers(
                        players=classic_pool,
                        model=classic_value_model,
                        prior_strength=classic_value_prior_strength,
                    )
                    matchup_raw_map = self._matchup_outcome_player_raw_map(
                        source_system=request.source_system,
                        season=season,
                        week=week,
                        slate=slate,
                        players=classic_pool,
                        model=matchup_outcome_model,
                    )
                    matchup_sampling_multipliers = self._sampling_multipliers_from_raw_map(
                        raw_map=matchup_raw_map,
                        strength=effective_matchup_prior_strength,
                    )
                    x_slate, points_slate, generated_classic = self._generate_lineups_for_slate(
                        players=classic_pool,
                        lineups_target=request.lineups_per_slate,
                        rng=rng,
                        player_sampling_multipliers=self._merge_sampling_multipliers(
                            classic_sampling_multipliers,
                            matchup_sampling_multipliers,
                        ),
                    )
                    if len(generated_classic) == 0:
                        rows.append(
                            OptimalVsPredictedBacktestRowResponse(
                                season=season,
                                week=week,
                                slate=slate,
                                slate_type="classic",
                                status="failed",
                                error_message="No generated candidate lineups.",
                            )
                        )
                        if progress_hook is not None:
                            progress_hook(
                                f"[optimal_vs_predicted] {index}/{len(slices)} {season} W{week:02d} {slate} "
                                "type=classic status=failed error=no_candidates"
                            )
                        continue
                    projected_mean = x_slate[:, PATTERN_FEATURE_INDEX["lineup_projected_mean"]]
                    projected_p90 = x_slate[:, PATTERN_FEATURE_INDEX["lineup_projected_p90"]]
                    projected_mean_idx = PATTERN_FEATURE_INDEX["lineup_projected_mean"]
                    projected_p90_idx = PATTERN_FEATURE_INDEX["lineup_projected_p90"]
                    threshold_percentile = float(request.classic_top_target_percentile)
                    classic_prior_scores = self._classic_lineup_prior_scores(
                        lineups=generated_classic,
                        model=classic_value_model,
                    )
                    matchup_prior_scores = self._matchup_outcome_lineup_prior_scores(
                        lineups=generated_classic,
                        raw_map=matchup_raw_map,
                    )

                train_rows = int(sum(chunk.shape[0] for chunk in history_x))
                predicted_idx: int | None = None
                policy_score: float | None = None

                if len(history_x) >= request.min_training_slates and train_rows >= request.min_training_rows:
                    x_train = np.vstack(history_x)
                    y_train = np.concatenate(history_y)
                    points_train = np.concatenate(history_points)
                    weights, bias, mean, std = self._fit_logistic(x_train, y_train)
                    probs = _sigmoid(((x_slate - mean) / std) @ weights + bias)
                    (
                        points_weights,
                        points_bias,
                        points_x_mean,
                        points_x_std,
                        points_y_mean,
                        points_y_std,
                        has_point_signal,
                    ) = self._fit_point_regression(x_train, points_train)
                    has_policy_signal = float(np.max(np.abs(weights))) > 1e-8
                    has_learned_signal = has_policy_signal or has_point_signal
                    if has_learned_signal:
                        composite_blend = self._fit_backtest_composite_blend(
                            history_x=history_x,
                            history_points=history_points,
                            policy_weights=weights,
                            policy_bias=bias,
                            policy_mean=mean,
                            policy_std=std,
                            point_weights=points_weights,
                            point_bias=points_bias,
                            point_x_mean=points_x_mean,
                            point_x_std=points_x_std,
                            point_y_mean=points_y_mean,
                            point_y_std=points_y_std,
                            projected_mean_idx=projected_mean_idx,
                            projected_p90_idx=projected_p90_idx,
                        )
                        if progress_hook is not None:
                            if last_logged_composite_blend is None or (
                                float(np.max(np.abs(composite_blend - last_logged_composite_blend))) >= 0.03
                            ):
                                progress_hook(
                                    "[optimal_vs_predicted] blend "
                                    f"exp={composite_blend[0]:.3f} policy={composite_blend[1]:.3f} "
                                    f"p90={composite_blend[2]:.3f} mean={composite_blend[3]:.3f}"
                                )
                                last_logged_composite_blend = np.asarray(composite_blend, dtype=float)
                        expected_points = self._predict_point_regression(
                            x_rows=x_slate,
                            weights=points_weights,
                            bias=points_bias,
                            x_mean=points_x_mean,
                            x_std=points_x_std,
                            y_mean=points_y_mean,
                            y_std=points_y_std,
                        )
                        composite = self._composite_lineup_selection_scores(
                            policy_scores=probs,
                            expected_points=expected_points,
                            projected_mean=projected_mean,
                            projected_p90=projected_p90,
                            blend_weights=composite_blend,
                        )
                        if request.slate_type == "classic":
                            composite = self._apply_classic_prior_to_composite(
                                composite_scores=composite,
                                prior_scores=classic_prior_scores,
                                prior_strength=classic_value_prior_strength,
                            )
                            composite = self._apply_matchup_outcome_prior_to_composite(
                                composite_scores=composite,
                                prior_scores=matchup_prior_scores,
                                prior_strength=effective_matchup_prior_strength,
                            )
                        predicted_idx = int(np.argmax(composite))
                        policy_score = float(probs[predicted_idx])
                    elif not request.learned_only:
                        heuristic_scores = projected_mean
                        if request.slate_type == "classic":
                            heuristic_scores = self._apply_classic_prior_to_composite(
                                composite_scores=heuristic_scores,
                                prior_scores=classic_prior_scores,
                                prior_strength=classic_value_prior_strength,
                            )
                            heuristic_scores = self._apply_matchup_outcome_prior_to_composite(
                                composite_scores=heuristic_scores,
                                prior_scores=matchup_prior_scores,
                                prior_strength=effective_matchup_prior_strength,
                            )
                        predicted_idx = int(np.argmax(heuristic_scores))
                elif not request.learned_only:
                    heuristic_scores = projected_mean
                    if request.slate_type == "classic":
                        heuristic_scores = self._apply_classic_prior_to_composite(
                            composite_scores=heuristic_scores,
                            prior_scores=classic_prior_scores,
                            prior_strength=classic_value_prior_strength,
                        )
                        heuristic_scores = self._apply_matchup_outcome_prior_to_composite(
                            composite_scores=heuristic_scores,
                            prior_scores=matchup_prior_scores,
                            prior_strength=effective_matchup_prior_strength,
                        )
                    predicted_idx = int(np.argmax(heuristic_scores))

                if predicted_idx is None:
                    rows.append(
                        OptimalVsPredictedBacktestRowResponse(
                            season=season,
                            week=week,
                            slate=slate,
                            slate_type=request.slate_type,
                            status="warmup_or_no_signal",
                            error_message=(
                                "Insufficient learned history for learned-only mode."
                                if request.learned_only
                                else "Could not produce predicted lineup."
                            ),
                        )
                    )
                else:
                    if request.slate_type == "showdown":
                        predicted_lineup = generated_showdown[predicted_idx]
                        predicted_actual_points = self._showdown_actual_points(predicted_lineup)
                        predicted_salary = self._showdown_salary_used(predicted_lineup)
                        predicted_proj_mean = self._showdown_projected_mean(predicted_lineup)
                        predicted_proj_p90 = self._showdown_projected_p90(predicted_lineup)
                    else:
                        predicted_lineup = generated_classic[predicted_idx]
                        predicted_actual_points = float(sum(player.actual_points for player in predicted_lineup))
                        predicted_salary = int(sum(player.salary for player in predicted_lineup))
                        predicted_proj_mean = float(sum(player.projected_mean_points for player in predicted_lineup))
                        predicted_proj_p90 = float(sum(player.projected_p90_points for player in predicted_lineup))

                    gap = float(optimal_points - predicted_actual_points)
                    gaps.append(gap)
                    rows.append(
                        OptimalVsPredictedBacktestRowResponse(
                            season=season,
                            week=week,
                            slate=slate,
                            slate_type=request.slate_type,
                            status="ok",
                            optimal_actual_points=float(optimal_points),
                            predicted_actual_points=float(predicted_actual_points),
                            gap_points=gap,
                            optimal_salary_used=int(optimal_salary),
                            predicted_salary_used=int(predicted_salary),
                            predicted_projected_mean_points=float(predicted_proj_mean),
                            predicted_projected_p90_points=float(predicted_proj_p90),
                            predicted_policy_score=policy_score,
                            error_message=None,
                        )
                    )

                threshold = float(np.percentile(points_slate, threshold_percentile))
                if np.isfinite(threshold) and float(np.std(points_slate)) > 1e-9:
                    y_slate = (points_slate >= threshold).astype(float)
                    pos_rate = float(np.mean(y_slate))
                    if 0.0 < pos_rate < 1.0:
                        history_x.append(x_slate)
                        history_y.append(y_slate)
                        history_points.append(points_slate)
                while len(history_x) > request.training_window_slates:
                    history_x.pop(0)
                    history_y.pop(0)
                    history_points.pop(0)

                if progress_hook is not None:
                    progress_hook(
                        f"[optimal_vs_predicted] {index}/{len(slices)} {season} W{week:02d} {slate} "
                        f"type={request.slate_type} status={rows[-1].status}"
                    )
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    OptimalVsPredictedBacktestRowResponse(
                        season=season,
                        week=week,
                        slate=slate,
                        slate_type=request.slate_type,
                        status="failed",
                        error_message=str(exc),
                    )
                )
                if progress_hook is not None:
                    progress_hook(
                        f"[optimal_vs_predicted] {index}/{len(slices)} {season} W{week:02d} {slate} "
                        f"type={request.slate_type} status=failed error={exc}"
                    )

        completed_rows = [row for row in rows if row.status == "ok" and row.gap_points is not None]
        mean_gap = float(statistics.mean(gaps)) if gaps else None
        median_gap = float(statistics.median(gaps)) if gaps else None
        best_gap = float(min(gaps)) if gaps else None
        worst_gap = float(max(gaps)) if gaps else None

        if progress_hook is not None:
            progress_hook(
                f"[optimal_vs_predicted] done type={request.slate_type} "
                f"completed={len(completed_rows)}/{len(rows)} "
                f"mean_gap={mean_gap if mean_gap is not None else 'NA'}"
            )

        return OptimalVsPredictedBacktestResponse(
            source_system=request.source_system,
            season_start=season_start,
            season_end=season_end,
            slate_filter=request.slate,
            slate_type=request.slate_type,
            lineups_per_slate=request.lineups_per_slate,
            training_window_slates=request.training_window_slates,
            min_training_slates=request.min_training_slates,
            min_training_rows=request.min_training_rows,
            classic_top_target_percentile=float(request.classic_top_target_percentile),
            learned_only=request.learned_only,
            showdown_captain_model_path=captain_model_path,
            showdown_captain_prior_strength=captain_prior_strength,
            classic_value_driver_model_path=classic_value_model_path,
            classic_value_driver_prior_strength=classic_value_prior_strength,
            matchup_outcome_model_path=matchup_outcome_model_path,
            matchup_outcome_prior_strength=matchup_outcome_prior_strength,
            matchup_prior_gate_model_path=matchup_prior_gate_model_path,
            slates_total=len(rows),
            slates_completed=len(completed_rows),
            slates_failed_or_skipped=len(rows) - len(completed_rows),
            mean_gap_points=mean_gap,
            median_gap_points=median_gap,
            best_case_gap_points=best_gap,
            worst_case_gap_points=worst_gap,
            rows=rows,
        )

    def build_ultimate_lineups(self, request: UltimateLineupRequest) -> UltimateLineupResponse:
        rng = np.random.default_rng(request.random_seed)
        classic_value_prior_strength = float(
            getattr(request, "classic_value_driver_prior_strength", 0.0) or 0.0
        )
        classic_value_model_path = getattr(request, "classic_value_driver_model_path", None)
        classic_value_model: ClassicValueDriverModel | None = None
        if classic_value_prior_strength > 0.0 and classic_value_model_path:
            classic_value_model = self._load_classic_value_driver_model(classic_value_model_path)
        matchup_outcome_prior_strength = float(
            getattr(request, "matchup_outcome_prior_strength", 0.0) or 0.0
        )
        matchup_outcome_model_path = getattr(request, "matchup_outcome_model_path", None)
        matchup_outcome_model: MatchupOutcomeIntelligenceModel | None = None
        matchup_prior_gate_model_path = getattr(request, "matchup_prior_gate_model_path", None)
        matchup_prior_gate_model: MatchupPriorGateModel | None = None
        if matchup_outcome_prior_strength > 0.0 and matchup_outcome_model_path:
            matchup_outcome_model = self._load_matchup_outcome_model(matchup_outcome_model_path)
            if matchup_prior_gate_model_path:
                matchup_prior_gate_model = self._load_matchup_prior_gate_model(matchup_prior_gate_model_path)
        x_history_chunks, points_history_chunks, training_slates_used, training_rows_used = self._collect_training_lineup_chunks(
            source_system=request.source_system,
            season=request.season,
            week=request.week,
            training_start_season=request.training_start_season,
            training_window_slates=request.training_window_slates,
            training_lineups_per_slate=request.training_lineups_per_slate,
            rng=rng,
            classic_value_model=classic_value_model,
            classic_value_prior_strength=classic_value_prior_strength,
            matchup_outcome_model=matchup_outcome_model,
            matchup_outcome_prior_strength=matchup_outcome_prior_strength,
            matchup_prior_gate_model=matchup_prior_gate_model,
        )
        history_ready = (
            training_slates_used >= request.min_training_slates
            and training_rows_used >= request.min_training_rows
        )
        dim = len(FEATURE_NAMES)
        zero_model = LogisticTargetModel(
            weights=np.zeros(dim, dtype=float),
            bias=0.0,
            mean=np.zeros(dim, dtype=float),
            std=np.ones(dim, dtype=float),
            positive_rate=0.0,
            training_rows=0,
            has_signal=False,
        )
        policy_model = zero_model
        ceiling_model = zero_model
        bust_model = zero_model
        blend_weights = np.asarray([1.0, 0.0, 0.0], dtype=float)
        blend_intercept = 0.0

        if history_ready:
            policy_model = self._fit_percentile_model(
                x_chunks=x_history_chunks,
                points_chunks=points_history_chunks,
                percentile=TOP_TARGET_PERCENTILE,
                tail="upper",
            )
            ceiling_model = self._fit_percentile_model(
                x_chunks=x_history_chunks,
                points_chunks=points_history_chunks,
                percentile=CEILING_TARGET_PERCENTILE,
                tail="upper",
            )
            bust_model = self._fit_percentile_model(
                x_chunks=x_history_chunks,
                points_chunks=points_history_chunks,
                percentile=BUST_TARGET_PERCENTILE,
                tail="lower",
            )

            x_history = np.vstack(x_history_chunks)
            points_history = np.concatenate(points_history_chunks)
            policy_history_scores = self._predict_target_model(policy_model, x_history)
            ceiling_history_scores = self._predict_target_model(ceiling_model, x_history)
            bust_history_scores = self._predict_target_model(bust_model, x_history)
            quality_history_scores = 1.0 - bust_history_scores
            blend_weights, blend_intercept = self._fit_blend_weights(
                points_train=points_history,
                policy_scores=policy_history_scores,
                ceiling_scores=ceiling_history_scores,
                quality_scores=quality_history_scores,
            )

        training_positive_rate = float(policy_model.positive_rate)

        player_projection_lookup, dst_projection_lookup = self._compute_player_projection_lookup(
            source_system=request.source_system,
            season=request.season,
            week=request.week,
            slate=request.slate,
        )
        target_pool = self._fetch_slate_player_pool(
            source_system=request.source_system,
            season=request.season,
            week=request.week,
            slate=request.slate,
            projection_lookup=player_projection_lookup,
            dst_projection_lookup=dst_projection_lookup,
        )
        if not target_pool:
            raise ValueError(
                f"No salary player pool available for {request.source_system} {request.season} week {request.week} slate={request.slate}."
            )

        projected_by_position: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for player in target_pool:
            if player.projected_mean_points > 0 and player.projected_p90_points > 0:
                projected_by_position[player.position].append(
                    (player.projected_mean_points, player.projected_p90_points)
                )
        global_mean = float(
            np.mean([pair[0] for values in projected_by_position.values() for pair in values] or [8.0])
        )
        global_p90 = float(
            np.mean([pair[1] for values in projected_by_position.values() for pair in values] or [14.0])
        )
        for player in target_pool:
            if player.projected_mean_points > 0 and player.projected_p90_points > 0:
                continue
            pos_values = projected_by_position.get(player.position, [])
            if pos_values:
                player.projected_mean_points = float(np.mean([pair[0] for pair in pos_values]))
                player.projected_p90_points = float(np.mean([pair[1] for pair in pos_values]))
            else:
                player.projected_mean_points = global_mean
                player.projected_p90_points = global_p90

        classic_sampling_multipliers = self._classic_player_sampling_multipliers(
            players=target_pool,
            model=classic_value_model,
            prior_strength=classic_value_prior_strength,
        )
        effective_matchup_prior_strength, gate_score, gate_active = self._effective_matchup_prior_strength(
            requested_strength=matchup_outcome_prior_strength,
            gate_model=matchup_prior_gate_model,
            slate=request.slate,
            players=target_pool,
        )
        matchup_raw_map = self._matchup_outcome_player_raw_map(
            source_system=request.source_system,
            season=request.season,
            week=request.week,
            slate=request.slate,
            players=target_pool,
            model=matchup_outcome_model,
        )
        matchup_sampling_multipliers = self._sampling_multipliers_from_raw_map(
            raw_map=matchup_raw_map,
            strength=effective_matchup_prior_strength,
        )
        candidate_lineups = self._generate_candidate_lineups_adaptive(
            players=target_pool,
            requested_lineups=request.candidate_lineups,
            min_salary_floor=request.min_salary_floor,
            rng=rng,
            player_sampling_multipliers=self._merge_sampling_multipliers(
                classic_sampling_multipliers,
                matchup_sampling_multipliers,
            ),
        )
        _validate_classic_lineup_batch(
            candidate_lineups,
            context=(
                f"{request.source_system} {request.season}-W{request.week:02d} "
                f"slate={request.slate} candidates"
            ),
        )
        x_candidates = np.vstack([self._lineup_features(lineup) for lineup in candidate_lineups])
        mean_points = np.asarray(
            [sum(player.projected_mean_points for player in lineup) for lineup in candidate_lineups],
            dtype=float,
        )
        p90_points = np.asarray(
            [sum(player.projected_p90_points for player in lineup) for lineup in candidate_lineups],
            dtype=float,
        )

        has_learned_signal = history_ready and (policy_model.has_signal or ceiling_model.has_signal or bust_model.has_signal)
        learned_only = bool(getattr(request, "learned_only", True))
        if not has_learned_signal and learned_only:
            raise ValueError(
                "No learnable signal found for this target slate. "
                "Widen training window or lower minimum training thresholds."
            )

        if has_learned_signal:
            policy_scores = self._predict_target_model(policy_model, x_candidates)
            ceiling_scores = self._predict_target_model(ceiling_model, x_candidates)
            bust_scores = self._predict_target_model(bust_model, x_candidates)
            quality_scores = 1.0 - bust_scores
            composite = (
                blend_intercept
                + (blend_weights[0] * policy_scores)
                + (blend_weights[1] * ceiling_scores)
                + (blend_weights[2] * quality_scores)
            )
            classic_prior_scores = self._classic_lineup_prior_scores(
                lineups=candidate_lineups,
                model=classic_value_model,
            )
            composite = self._apply_classic_prior_to_composite(
                composite_scores=composite,
                prior_scores=classic_prior_scores,
                prior_strength=classic_value_prior_strength,
            )
            matchup_prior_scores = self._matchup_outcome_lineup_prior_scores(
                lineups=candidate_lineups,
                raw_map=matchup_raw_map,
            )
            composite = self._apply_matchup_outcome_prior_to_composite(
                composite_scores=composite,
                prior_scores=matchup_prior_scores,
                prior_strength=effective_matchup_prior_strength,
            )
        else:
            # Optional heuristic fallback is only used when learned_only=False.
            policy_scores = np.full(len(candidate_lineups), 0.5, dtype=float)
            ceiling_scores = np.full(len(candidate_lineups), 0.5, dtype=float)
            bust_scores = np.full(len(candidate_lineups), 0.5, dtype=float)
            mean_std = float(np.std(mean_points))
            p90_std = float(np.std(p90_points))
            mean_norm = (
                (mean_points - float(np.mean(mean_points))) / (mean_std if mean_std > 1e-9 else 1.0)
            )
            p90_norm = (
                (p90_points - float(np.mean(p90_points))) / (p90_std if p90_std > 1e-9 else 1.0)
            )
            composite = (0.6 * mean_norm) + (0.4 * p90_norm)
            classic_prior_scores = self._classic_lineup_prior_scores(
                lineups=candidate_lineups,
                model=classic_value_model,
            )
            composite = self._apply_classic_prior_to_composite(
                composite_scores=composite,
                prior_scores=classic_prior_scores,
                prior_strength=classic_value_prior_strength,
            )
            matchup_prior_scores = self._matchup_outcome_lineup_prior_scores(
                lineups=candidate_lineups,
                raw_map=matchup_raw_map,
            )
            composite = self._apply_matchup_outcome_prior_to_composite(
                composite_scores=composite,
                prior_scores=matchup_prior_scores,
                prior_strength=effective_matchup_prior_strength,
            )

        matchup_stack_rules = self._summarize_matchup_stack_rules(
            candidate_lineups=candidate_lineups,
            ranking_scores=composite,
        )

        ranked_idx = np.argsort(-composite)
        keep = min(request.output_lineups, len(ranked_idx))

        base_player_cap = min(keep, max(1, int(math.floor(keep * request.max_player_exposure))))
        base_qb_cap = min(keep, max(1, int(math.floor(keep * request.max_qb_exposure))))
        base_dst_cap = min(keep, max(1, int(math.floor(keep * request.max_dst_exposure))))

        def select_with_caps(multiplier: float) -> tuple[list[int], int, int, int]:
            player_cap = min(keep, max(1, int(math.floor(base_player_cap * multiplier))))
            qb_cap = min(keep, max(1, int(math.floor(base_qb_cap * multiplier))))
            dst_cap = min(keep, max(1, int(math.floor(base_dst_cap * multiplier))))

            selected: list[int] = []
            player_counts: dict[str, int] = defaultdict(int)
            qb_counts: dict[str, int] = defaultdict(int)
            dst_counts: dict[str, int] = defaultdict(int)

            for raw_idx in ranked_idx:
                idx = int(raw_idx)
                lineup = candidate_lineups[idx]
                if not _lineup_satisfies_roster_rules(lineup):
                    continue

                blocked = False
                qb_uid: str | None = None
                dst_uid: str | None = None
                for player in lineup:
                    if player_counts[player.uid] >= player_cap:
                        blocked = True
                        break
                    if player.position == "QB":
                        qb_uid = player.uid
                    elif player.position == "DST":
                        dst_uid = player.uid
                if blocked:
                    continue
                if qb_uid is not None and qb_counts[qb_uid] >= qb_cap:
                    continue
                if dst_uid is not None and dst_counts[dst_uid] >= dst_cap:
                    continue

                selected.append(idx)
                for player in lineup:
                    player_counts[player.uid] += 1
                if qb_uid is not None:
                    qb_counts[qb_uid] += 1
                if dst_uid is not None:
                    dst_counts[dst_uid] += 1
                if len(selected) >= keep:
                    break

            return selected, player_cap, qb_cap, dst_cap

        selected_idx: list[int] = []
        effective_player_cap = base_player_cap
        effective_qb_cap = base_qb_cap
        effective_dst_cap = base_dst_cap
        cap_multiplier_used = 1.0
        for multiplier in (1.0, 1.25, 1.5, 2.0, 3.0, 6.0):
            chosen, player_cap, qb_cap, dst_cap = select_with_caps(multiplier)
            selected_idx = chosen
            effective_player_cap = player_cap
            effective_qb_cap = qb_cap
            effective_dst_cap = dst_cap
            cap_multiplier_used = multiplier
            if len(selected_idx) >= keep:
                break

        # Guaranteed fill for output volume if caps are still too strict for this slate.
        if len(selected_idx) < keep:
            selected_set = set(selected_idx)
            for raw_idx in ranked_idx:
                idx = int(raw_idx)
                if idx in selected_set:
                    continue
                if not _lineup_satisfies_roster_rules(candidate_lineups[idx]):
                    continue
                selected_idx.append(idx)
                selected_set.add(idx)
                if len(selected_idx) >= keep:
                    break

        top_idx = np.asarray(selected_idx[:keep], dtype=int)
        keep = int(len(top_idx))
        _validate_classic_lineup_batch(
            [candidate_lineups[int(idx)] for idx in top_idx],
            context=(
                f"{request.source_system} {request.season}-W{request.week:02d} "
                f"slate={request.slate} selected"
            ),
        )

        rows: list[UltimateLineupRowResponse] = []
        exposure_counts: dict[str, tuple[PlayerPoolRow, int]] = {}
        for rank, idx in enumerate(top_idx.tolist(), start=1):
            lineup = candidate_lineups[idx]
            salary_used = int(sum(player.salary for player in lineup))
            salary_left = int(DK_SALARY_CAP - salary_used)
            lineup_players: list[UltimateLineupPlayerRowResponse] = []
            for player in lineup:
                lineup_players.append(
                    UltimateLineupPlayerRowResponse(
                        player_name=player.name,
                        team=player.team,
                        position=player.position,
                        salary=int(player.salary),
                        projected_mean_points=float(player.projected_mean_points),
                        projected_p90_points=float(player.projected_p90_points),
                    )
                )
                existing = exposure_counts.get(player.uid)
                if existing is None:
                    exposure_counts[player.uid] = (player, 1)
                else:
                    exposure_counts[player.uid] = (existing[0], existing[1] + 1)
            rows.append(
                UltimateLineupRowResponse(
                    rank=rank,
                    salary_used=salary_used,
                    salary_left=salary_left,
                    projected_mean_points=float(mean_points[idx]),
                    projected_p90_points=float(p90_points[idx]),
                    policy_score=float(policy_scores[idx]),
                    composite_score=float(composite[idx]),
                    players=lineup_players,
                )
            )

        exposures: list[UltimateLineupExposureRowResponse] = []
        for player, count in sorted(
            [value for value in exposure_counts.values()],
            key=lambda item: item[1],
            reverse=True,
        ):
            exposures.append(
                UltimateLineupExposureRowResponse(
                    player_name=player.name,
                    team=player.team,
                    position=player.position,
                    salary=int(player.salary),
                    exposure_count=int(count),
                    exposure_rate=(count / keep) if keep > 0 else 0.0,
                )
            )

        top_feature_weights = sorted(
            enumerate(policy_model.weights),
            key=lambda item: abs(float(item[1])),
            reverse=True,
        )[:5]
        selected_policy_mean = float(np.mean(policy_scores[top_idx])) if keep > 0 else 0.0
        selected_ceiling_mean = float(np.mean(ceiling_scores[top_idx])) if keep > 0 else 0.0
        selected_bust_mean = float(np.mean(bust_scores[top_idx])) if keep > 0 else 0.0
        discovered_patterns = [
            f"Models trained on {training_slates_used} slates and {training_rows_used} historical lineups.",
            (
                "Historical label rates: "
                f"top-{100 - TOP_TARGET_PERCENTILE:.0f}%={policy_model.positive_rate:.2%}, "
                f"ceiling(top-{100 - CEILING_TARGET_PERCENTILE:.0f}%)={ceiling_model.positive_rate:.2%}, "
                f"bust(bottom-{BUST_TARGET_PERCENTILE:.0f}%)={bust_model.positive_rate:.2%}."
            ),
            (
                "Ranking mode: "
                + (
                    "learned blended score (policy + ceiling + quality)."
                    if has_learned_signal
                    else "heuristic fallback (no learned signal)."
                )
            ),
            (
                "Diversification targets: "
                f"player<={request.max_player_exposure:.0%}, "
                f"QB<={request.max_qb_exposure:.0%}, DST<={request.max_dst_exposure:.0%}."
            ),
            (
                "Effective exposure caps (count): "
                f"player<={effective_player_cap}, QB<={effective_qb_cap}, DST<={effective_dst_cap}."
            ),
        ]
        if cap_multiplier_used > 1.0:
            discovered_patterns.append(
                f"Exposure caps auto-relaxed by x{cap_multiplier_used:.2f} to fill {keep} lineups."
            )
        if has_learned_signal:
            discovered_patterns.append(
                "Learned blend weights: "
                f"policy={blend_weights[0]:.3f}, "
                f"ceiling={blend_weights[1]:.3f}, "
                f"quality(1-bust)={blend_weights[2]:.3f}, "
                f"intercept={blend_intercept:.3f}."
            )
            discovered_patterns.append(
                "Selected lineup average risk profile: "
                f"policy={selected_policy_mean:.3f}, "
                f"ceiling={selected_ceiling_mean:.3f}, "
                f"bust={selected_bust_mean:.3f}."
            )
            for idx, weight in top_feature_weights:
                direction = "positive" if weight > 0 else "negative"
                discovered_patterns.append(
                    f"Policy signal: {FEATURE_NAMES[idx]} has {direction} weight {float(weight):.3f}."
                )
        if classic_value_model is not None and classic_value_prior_strength > 0.0:
            discovered_patterns.append(
                "Classic value-driver prior applied: "
                f"path={classic_value_model_path}, strength={classic_value_prior_strength:.2f}."
            )
        if matchup_outcome_model is not None and matchup_outcome_prior_strength > 0.0:
            discovered_patterns.append(
                "Matchup outcome prior applied: "
                f"path={matchup_outcome_model_path}, strength={matchup_outcome_prior_strength:.2f}."
            )
        if matchup_prior_gate_model is not None and gate_score is not None and gate_active is not None:
            discovered_patterns.append(
                "Matchup prior gate applied: "
                f"path={matchup_prior_gate_model_path}, score={gate_score:.3f}, "
                f"active={gate_active}, effective_strength={effective_matchup_prior_strength:.2f}."
            )
        discovered_patterns.extend(matchup_stack_rules)
        if rows:
            discovered_patterns.append(
                f"Top lineup projection mean/p90 = {rows[0].projected_mean_points:.2f}/{rows[0].projected_p90_points:.2f}."
            )

        return UltimateLineupResponse(
            source_system=request.source_system,
            season=request.season,
            week=request.week,
            slate=request.slate,
            candidate_lineups_requested=request.candidate_lineups,
            generated_candidate_lineups=len(candidate_lineups),
            output_lineups=keep,
            training_slates_used=training_slates_used,
            training_rows_used=training_rows_used,
            training_positive_rate=training_positive_rate,
            classic_value_driver_model_path=classic_value_model_path,
            classic_value_driver_prior_strength=classic_value_prior_strength,
            matchup_outcome_model_path=matchup_outcome_model_path,
            matchup_outcome_prior_strength=matchup_outcome_prior_strength,
            matchup_prior_gate_model_path=matchup_prior_gate_model_path,
            discovered_patterns=discovered_patterns,
            rows=rows,
            exposures=exposures,
        )
