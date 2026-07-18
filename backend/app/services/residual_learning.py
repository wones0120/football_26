from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Iterable

import numpy as np


ELIGIBLE_POSITIONS = {"QB", "RB", "WR", "TE"}
DEFAULT_PRIOR_STRENGTH = 5.0
DEFAULT_HISTORY_WINDOW_SLICES = 12
DEFAULT_MIN_TRAINING_SLICES = 4
DEFAULT_MAX_ABS_ADJUSTMENT = 6.0
SCOPE_PRIOR_MULTIPLIERS = {
    "player": 0.50,
    "team_position": 1.00,
    "opponent_position": 1.00,
    "salary_position": 1.50,
    "value_position": 1.50,
    "regime_position": 1.50,
}
FEATURE_SET_HASH = hashlib.sha256(
    "\n".join(
        [
            "canonical_player_identity",
            "position",
            "team_position",
            "opponent_position",
            "salary_position",
            "projected_value_position",
            "pregame_total_spread_regime",
            "sample_size_shrinkage",
        ]
    ).encode("utf-8")
).hexdigest()


def team_key(value: str | None) -> str:
    return (value or "").strip().upper()


def slice_key(season: int, week: int) -> tuple[int, int]:
    return int(season), int(week)


@dataclass(frozen=True)
class ResidualObservation:
    season: int
    week: int
    player_master_id: str | None
    source_player_key: str | None
    team: str | None
    opponent: str | None
    position: str
    salary: int | None
    game_total_line: float | None
    team_spread_line: float | None
    baseline_points: float
    actual_points: float

    @property
    def slice_key(self) -> tuple[int, int]:
        return slice_key(self.season, self.week)

    @property
    def identity_key(self) -> str | None:
        if self.player_master_id:
            return f"master:{self.player_master_id}"
        if self.source_player_key:
            return f"source:{self.source_player_key}"
        return None

    @property
    def residual(self) -> float:
        return float(self.actual_points - self.baseline_points)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ResidualObservation:
        return cls(
            season=int(payload["season"]),
            week=int(payload["week"]),
            player_master_id=payload.get("player_master_id"),
            source_player_key=payload.get("source_player_key"),
            team=payload.get("team"),
            opponent=payload.get("opponent"),
            position=str(payload["position"]),
            salary=(
                int(payload["salary"])
                if payload.get("salary") is not None
                else None
            ),
            game_total_line=(
                float(payload["game_total_line"])
                if payload.get("game_total_line") is not None
                else None
            ),
            team_spread_line=(
                float(payload["team_spread_line"])
                if payload.get("team_spread_line") is not None
                else None
            ),
            baseline_points=float(payload["baseline_points"]),
            actual_points=float(payload["actual_points"]),
        )


@dataclass(frozen=True)
class GroupSummary:
    count: int
    mean_residual: float


@dataclass
class ResidualModel:
    prior_strength: float
    max_abs_adjustment: float
    training_rows: int
    training_slices: int
    trained_through: tuple[int, int]
    global_summary: GroupSummary
    position_summaries: dict[str, GroupSummary]
    scope_summaries: dict[str, dict[str, GroupSummary]]

    def adjustment_for(
        self,
        observation: ResidualObservation,
    ) -> tuple[float, int]:
        numerator = float(self.global_summary.mean_residual)
        denominator = 1.0
        scopes_used = 0

        position_summary = self.position_summaries.get(observation.position)
        if position_summary is not None:
            reliability = position_summary.count / (
                position_summary.count + self.prior_strength
            )
            numerator += reliability * position_summary.mean_residual
            denominator += reliability
            scopes_used += 1

        for scope, prior_multiplier in SCOPE_PRIOR_MULTIPLIERS.items():
            key = scope_key(scope, observation)
            if key is None:
                continue
            summary = self.scope_summaries.get(scope, {}).get(key)
            if summary is None:
                continue
            scope_prior = self.prior_strength * prior_multiplier
            reliability = summary.count / (summary.count + scope_prior)
            numerator += reliability * summary.mean_residual
            denominator += reliability
            scopes_used += 1

        adjustment = numerator / denominator
        adjustment = float(
            np.clip(
                adjustment,
                -self.max_abs_adjustment,
                self.max_abs_adjustment,
            )
        )
        return adjustment, scopes_used


def salary_bucket(salary: int | None) -> str:
    if salary is None or salary <= 0:
        return "unknown"
    if salary <= 4500:
        return "value"
    if salary <= 6000:
        return "mid"
    if salary <= 7500:
        return "upper"
    return "premium"


def value_bucket(*, salary: int | None, baseline_points: float) -> str:
    if salary is None or salary <= 0:
        return "unknown"
    points_per_thousand = float(baseline_points) / (float(salary) / 1000.0)
    if points_per_thousand < 2.0:
        return "under_2x"
    if points_per_thousand < 3.0:
        return "2x_to_3x"
    if points_per_thousand < 4.0:
        return "3x_to_4x"
    return "4x_plus"


def game_regime(
    *,
    game_total_line: float | None,
    team_spread_line: float | None,
) -> str:
    if game_total_line is None or not math.isfinite(game_total_line):
        return "unknown"
    spread = (
        float(team_spread_line)
        if team_spread_line is not None and math.isfinite(team_spread_line)
        else 0.0
    )
    if game_total_line >= 48.0 and abs(spread) <= 3.5:
        return "high_total_close"
    if game_total_line >= 48.0:
        return "high_total"
    if game_total_line <= 42.0 and spread <= -3.5:
        return "low_total_favorite"
    if game_total_line <= 42.0 and spread >= 3.5:
        return "low_total_underdog"
    if game_total_line <= 42.0:
        return "low_total_close"
    if abs(spread) <= 3.5:
        return "mid_total_close"
    return "mid_total_favorite" if spread < 0.0 else "mid_total_underdog"


def scope_key(
    scope: str,
    observation: ResidualObservation,
) -> str | None:
    if scope == "player":
        return observation.identity_key
    if scope == "team_position":
        team = team_key(observation.team)
        return f"{team}|{observation.position}" if team else None
    if scope == "opponent_position":
        opponent = team_key(observation.opponent)
        return f"{opponent}|{observation.position}" if opponent else None
    if scope == "salary_position":
        return f"{salary_bucket(observation.salary)}|{observation.position}"
    if scope == "value_position":
        bucket = value_bucket(
            salary=observation.salary,
            baseline_points=observation.baseline_points,
        )
        return f"{bucket}|{observation.position}"
    if scope == "regime_position":
        regime = game_regime(
            game_total_line=observation.game_total_line,
            team_spread_line=observation.team_spread_line,
        )
        return f"{regime}|{observation.position}"
    raise ValueError(f"Unsupported residual scope: {scope}")


def _summaries_by_key(
    observations: Iterable[ResidualObservation],
    *,
    key_fn: Any,
) -> dict[str, GroupSummary]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for observation in observations:
        key = key_fn(observation)
        if key is not None:
            grouped[str(key)].append(observation.residual)
    return {
        key: GroupSummary(
            count=len(values),
            mean_residual=float(np.mean(values)),
        )
        for key, values in grouped.items()
    }


def fit_residual_model(
    observations: list[ResidualObservation],
    *,
    prior_strength: float,
    max_abs_adjustment: float,
) -> ResidualModel:
    if not observations:
        raise ValueError(
            "Residual learning requires at least one historical observation."
        )
    if prior_strength <= 0.0:
        raise ValueError("prior_strength must be positive.")
    if max_abs_adjustment <= 0.0:
        raise ValueError("max_abs_adjustment must be positive.")

    ordered = sorted(observations, key=lambda row: row.slice_key)
    global_summary = GroupSummary(
        count=len(ordered),
        mean_residual=float(np.mean([row.residual for row in ordered])),
    )
    position_summaries = _summaries_by_key(
        ordered,
        key_fn=lambda row: row.position,
    )
    scope_summaries = {
        scope: _summaries_by_key(
            ordered,
            key_fn=lambda row, current_scope=scope: scope_key(
                current_scope,
                row,
            ),
        )
        for scope in SCOPE_PRIOR_MULTIPLIERS
    }
    return ResidualModel(
        prior_strength=float(prior_strength),
        max_abs_adjustment=float(max_abs_adjustment),
        training_rows=len(ordered),
        training_slices=len({row.slice_key for row in ordered}),
        trained_through=ordered[-1].slice_key,
        global_summary=global_summary,
        position_summaries=position_summaries,
        scope_summaries=scope_summaries,
    )


def game_context_by_team(schedule_rows: Iterable[Any]) -> dict[str, dict[str, float]]:
    context: dict[str, dict[str, float]] = {}
    for row in schedule_rows:
        payload = row.raw_row_json or {}
        home_team = team_key(row.home_team or payload.get("home_team"))
        away_team = team_key(row.away_team or payload.get("away_team"))
        if not home_team or not away_team:
            continue
        total_value = payload.get("total_line", payload.get("total"))
        spread_value = payload.get("spread_line")
        try:
            total_line = (
                float(total_value)
                if total_value is not None and math.isfinite(float(total_value))
                else None
            )
        except (TypeError, ValueError):
            total_line = None
        try:
            home_spread = (
                float(spread_value)
                if spread_value is not None
                and math.isfinite(float(spread_value))
                else None
            )
        except (TypeError, ValueError):
            home_spread = None
        home_context: dict[str, float] = {}
        away_context: dict[str, float] = {}
        if total_line is not None:
            home_context["game_total_line"] = total_line
            away_context["game_total_line"] = total_line
        if home_spread is not None:
            home_context["team_spread_line"] = home_spread
            away_context["team_spread_line"] = -home_spread
        context[home_team] = home_context
        context[away_team] = away_context
    return context
