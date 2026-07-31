#!/usr/bin/env python3
"""Run locked MODEL-001 opportunity/efficiency and DST feature ablations.

The selection phase compares declared feature groups on a validation window and
writes a content-addressed lock. The holdout phase verifies that lock before it
reads or reports holdout metrics. This is research evidence only: the source
salary cohort does not preserve historical observation timestamps, so this
script never changes the active production model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from sqlalchemy import and_, select, text

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.db import SessionLocal
from backend.app.models import PlayerGameFeatureMatrix, RawNflWeeklyStat
from backend.app.services.lineup_learning import _calculate_dk_player_points
from scripts.compare_projection_model_families import _fit_ridge, regression_metrics


CONTRACT_ID = "model_001_opportunity_efficiency_ablation_v1"
SUPPORTED_POSITIONS = ("QB", "RB", "WR", "TE", "DST")
OFFENSE_POSITIONS = ("QB", "RB", "WR", "TE")
TRAIN_END = (2025, 7)
VALIDATION_START = (2025, 8)
VALIDATION_END = (2025, 11)
HOLDOUT_START = (2025, 12)
HOLDOUT_END = (2025, 18)
RIDGE_ALPHA = 1.0
MIN_VALIDATION_IMPROVEMENT = 0.005

OFFENSE_BASELINE_FEATURES = (
    "player_games_history",
    "player_roll3_mean",
    "player_roll8_mean",
    "player_roll8_std",
)
OPPORTUNITY_FEATURES = (
    "opportunity_roll3",
    "opportunity_roll8",
    "opportunity_share_roll3",
    "opportunity_share_roll8",
    "opportunity_trend",
    "attempts_roll3",
    "carries_roll3",
    "targets_roll3",
    "carry_share_roll3",
    "target_share_roll3",
)
EFFICIENCY_FEATURES = (
    "efficiency_roll3",
    "efficiency_roll8",
    "efficiency_trend",
)
MATCHUP_FEATURES = (
    "defense_pos_allowed_roll3",
    "defense_pos_allowed_roll8",
    "defense_pos_allowed_p90_roll8",
)
DST_BASELINE_FEATURES = ("dst_points_roll8",)
DST_DEFENSE_FEATURES = (
    "dst_sacks_roll8",
    "dst_takeaways_roll8",
    "dst_touchdowns_roll8",
    "dst_points_allowed_score_roll8",
)
DST_OPPONENT_FEATURES = (
    "opponent_dst_points_allowed_roll8",
    "opponent_sacks_allowed_roll8",
    "opponent_takeaways_allowed_roll8",
    "opponent_dst_touchdowns_allowed_roll8",
)

OFFENSE_CANDIDATES: dict[str, tuple[str, ...]] = {
    "history_baseline": OFFENSE_BASELINE_FEATURES,
    "history_plus_opportunity": OFFENSE_BASELINE_FEATURES + OPPORTUNITY_FEATURES,
    "history_plus_efficiency": OFFENSE_BASELINE_FEATURES + EFFICIENCY_FEATURES,
    "opportunity_efficiency": (
        OFFENSE_BASELINE_FEATURES + OPPORTUNITY_FEATURES + EFFICIENCY_FEATURES
    ),
    "full_internal_context": (
        OFFENSE_BASELINE_FEATURES
        + OPPORTUNITY_FEATURES
        + EFFICIENCY_FEATURES
        + MATCHUP_FEATURES
    ),
}
DST_CANDIDATES: dict[str, tuple[str, ...]] = {
    "dst_history_baseline": DST_BASELINE_FEATURES,
    "dst_defense_form": DST_BASELINE_FEATURES + DST_DEFENSE_FEATURES,
    "dst_opponent_allowed": DST_BASELINE_FEATURES + DST_OPPONENT_FEATURES,
    "dst_full_internal_context": (
        DST_BASELINE_FEATURES + DST_DEFENSE_FEATURES + DST_OPPONENT_FEATURES
    ),
}


@dataclass(frozen=True)
class UsageRecord:
    season: int
    week: int
    player_id: str
    team: str
    position: str
    dk_points: float
    attempts: float
    carries: float
    targets: float
    opportunity: float
    opportunity_share: float
    carry_share: float
    target_share: float

    @property
    def slice_key(self) -> tuple[int, int]:
        return self.season, self.week


@dataclass(frozen=True)
class DstRecord:
    season: int
    week: int
    team: str
    opponent: str
    dk_points: float
    sacks: float
    interceptions: float
    fumble_recoveries: float
    touchdowns: float
    points_allowed_score: float

    @property
    def slice_key(self) -> tuple[int, int]:
        return self.season, self.week


@dataclass(frozen=True)
class ResearchRow:
    season: int
    week: int
    player_id: str
    position: str
    role: str
    actual_points: float
    features: Mapping[str, float]

    @property
    def slice_key(self) -> tuple[int, int]:
        return self.season, self.week


@dataclass(frozen=True)
class FittedRidge:
    feature_names: tuple[str, ...]
    x_mean: np.ndarray
    x_std: np.ndarray
    weights: np.ndarray
    bias: float
    residual_quantiles: Mapping[str, float]


def _number(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _canonical_team(value: Any) -> str:
    team = str(value or "").strip().upper()
    aliases = {"JAX": "JAC", "WSH": "WAS", "WFT": "WAS", "LA": "LAR"}
    return aliases.get(team, team)


def _mean(records: Sequence[Any], field: str) -> float:
    if not records:
        return 0.0
    return float(np.mean([_number(getattr(row, field, 0.0)) for row in records]))


def _ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator > 0.0 else 0.0


def _window_before(
    records: Sequence[Any],
    target: tuple[int, int],
    size: int,
) -> list[Any]:
    eligible = [row for row in records if row.slice_key < target]
    return eligible[-size:]


def _offense_role(position: str, recent: Sequence[UsageRecord]) -> str:
    if not recent:
        return "UNKNOWN"
    if position == "QB":
        return "MOBILE" if _mean(recent, "carries") >= 4.0 else "POCKET"
    if position == "RB":
        carry_share = _mean(recent, "carry_share")
        carries = _mean(recent, "carries")
        target_share = _mean(recent, "target_share")
        if carry_share >= 0.55 or carries >= 14.0:
            return "LEAD"
        if target_share >= 0.12:
            return "RECEIVING"
        return "COMMITTEE"
    target_share = _mean(recent, "target_share")
    targets = _mean(recent, "targets")
    if target_share >= 0.22 or targets >= 7.0:
        return "PRIMARY"
    if target_share < 0.10:
        return "ROTATION"
    return "SECONDARY"


def build_usage_records(raw_rows: Iterable[Any]) -> dict[str, list[UsageRecord]]:
    """Build canonical-ID usage histories and team shares from weekly rows."""
    deduplicated: dict[tuple[int, int, str], tuple[str, str, Mapping[str, Any]]] = {}
    for row in raw_rows:
        player_id = str(getattr(row, "player_id", "") or "").strip()
        position = str(getattr(row, "position", "") or "").strip().upper()
        team = _canonical_team(getattr(row, "team", ""))
        if not player_id or position not in OFFENSE_POSITIONS or not team:
            continue
        payload = getattr(row, "raw_row_json", None) or {}
        deduplicated[(int(row.season), int(row.week), player_id)] = (
            team,
            position,
            payload,
        )

    parsed: list[dict[str, Any]] = []
    team_qb_opportunities: dict[tuple[int, int, str], float] = defaultdict(float)
    team_skill_opportunities: dict[tuple[int, int, str], float] = defaultdict(float)
    team_rb_carries: dict[tuple[int, int, str], float] = defaultdict(float)
    team_skill_targets: dict[tuple[int, int, str], float] = defaultdict(float)
    for (season, week, player_id), (team, position, payload) in deduplicated.items():
        attempts = max(0.0, _number(payload.get("attempts")))
        carries = max(0.0, _number(payload.get("carries")))
        targets = max(0.0, _number(payload.get("targets")))
        opportunity = attempts + carries if position == "QB" else carries + targets
        key = (season, week, team)
        if position == "QB":
            team_qb_opportunities[key] += opportunity
        else:
            team_skill_opportunities[key] += opportunity
            team_skill_targets[key] += targets
        if position == "RB":
            team_rb_carries[key] += carries
        parsed.append(
            {
                "season": season,
                "week": week,
                "player_id": player_id,
                "team": team,
                "position": position,
                "payload": payload,
                "attempts": attempts,
                "carries": carries,
                "targets": targets,
                "opportunity": opportunity,
            }
        )

    by_player: dict[str, list[UsageRecord]] = defaultdict(list)
    for row in parsed:
        key = (row["season"], row["week"], row["team"])
        position = str(row["position"])
        team_opportunity = (
            team_qb_opportunities[key]
            if position == "QB"
            else team_skill_opportunities[key]
        )
        points = _calculate_dk_player_points(row["payload"], position)
        by_player[row["player_id"]].append(
            UsageRecord(
                season=int(row["season"]),
                week=int(row["week"]),
                player_id=str(row["player_id"]),
                team=str(row["team"]),
                position=position,
                dk_points=float(points),
                attempts=float(row["attempts"]),
                carries=float(row["carries"]),
                targets=float(row["targets"]),
                opportunity=float(row["opportunity"]),
                opportunity_share=_ratio(float(row["opportunity"]), team_opportunity),
                carry_share=(
                    _ratio(float(row["carries"]), team_rb_carries[key])
                    if position == "RB"
                    else 0.0
                ),
                target_share=(
                    _ratio(float(row["targets"]), team_skill_targets[key])
                    if position in {"RB", "WR", "TE"}
                    else 0.0
                ),
            )
        )
    for rows in by_player.values():
        rows.sort(key=lambda item: item.slice_key)
    return dict(by_player)


def build_dst_records(rows: Iterable[Mapping[str, Any]]) -> list[DstRecord]:
    records = [
        DstRecord(
            season=int(row["season"]),
            week=int(row["week"]),
            team=_canonical_team(row["team_id"]),
            opponent=_canonical_team(row["opponent_team_id"]),
            dk_points=_number(row["dk_points"]),
            sacks=_number(row["sacks"]),
            interceptions=_number(row["interceptions"]),
            fumble_recoveries=_number(row["fumble_recoveries"]),
            touchdowns=(
                _number(row["interception_return_tds"])
                + _number(row["fumble_return_tds"])
                + _number(row["special_teams_tds"])
            ),
            points_allowed_score=_number(row["points_allowed_score"]),
        )
        for row in rows
        if row.get("team_id") and row.get("opponent_team_id")
    ]
    return sorted(records, key=lambda item: item.slice_key)


def _offense_features(
    matrix_row: PlayerGameFeatureMatrix,
    usage_history: Sequence[UsageRecord],
) -> tuple[dict[str, float], str]:
    target = (int(matrix_row.season), int(matrix_row.week))
    recent3 = _window_before(usage_history, target, 3)
    recent8 = _window_before(usage_history, target, 8)
    opportunity_roll3 = _mean(recent3, "opportunity")
    opportunity_roll8 = _mean(recent8, "opportunity")
    efficiency_roll3 = _ratio(
        sum(row.dk_points for row in recent3),
        sum(row.opportunity for row in recent3),
    )
    efficiency_roll8 = _ratio(
        sum(row.dk_points for row in recent8),
        sum(row.opportunity for row in recent8),
    )
    features = {
        "player_games_history": float(matrix_row.player_games_history or 0),
        "player_roll3_mean": _number(matrix_row.player_roll3_mean),
        "player_roll8_mean": _number(matrix_row.player_roll8_mean),
        "player_roll8_std": _number(matrix_row.player_roll8_std),
        "opportunity_roll3": opportunity_roll3,
        "opportunity_roll8": opportunity_roll8,
        "opportunity_share_roll3": _mean(recent3, "opportunity_share"),
        "opportunity_share_roll8": _mean(recent8, "opportunity_share"),
        "opportunity_trend": opportunity_roll3 - opportunity_roll8,
        "attempts_roll3": _mean(recent3, "attempts"),
        "carries_roll3": _mean(recent3, "carries"),
        "targets_roll3": _mean(recent3, "targets"),
        "carry_share_roll3": _mean(recent3, "carry_share"),
        "target_share_roll3": _mean(recent3, "target_share"),
        "efficiency_roll3": efficiency_roll3,
        "efficiency_roll8": efficiency_roll8,
        "efficiency_trend": efficiency_roll3 - efficiency_roll8,
        "defense_pos_allowed_roll3": _number(matrix_row.defense_pos_allowed_roll3),
        "defense_pos_allowed_roll8": _number(matrix_row.defense_pos_allowed_roll8),
        "defense_pos_allowed_p90_roll8": _number(
            matrix_row.defense_pos_allowed_p90_roll8
        ),
    }
    return features, _offense_role(str(matrix_row.position).upper(), recent3)


def _dst_features(
    matrix_row: PlayerGameFeatureMatrix,
    dst_records: Sequence[DstRecord],
) -> dict[str, float]:
    target = (int(matrix_row.season), int(matrix_row.week))
    team = _canonical_team(matrix_row.team)
    opponent = _canonical_team(matrix_row.opponent)
    own = _window_before([row for row in dst_records if row.team == team], target, 8)
    allowed = _window_before(
        [row for row in dst_records if row.opponent == opponent],
        target,
        8,
    )
    return {
        "dst_points_roll8": _mean(own, "dk_points"),
        "dst_sacks_roll8": _mean(own, "sacks"),
        "dst_takeaways_roll8": _mean(own, "interceptions")
        + _mean(own, "fumble_recoveries"),
        "dst_touchdowns_roll8": _mean(own, "touchdowns"),
        "dst_points_allowed_score_roll8": _mean(own, "points_allowed_score"),
        "opponent_dst_points_allowed_roll8": _mean(allowed, "dk_points"),
        "opponent_sacks_allowed_roll8": _mean(allowed, "sacks"),
        "opponent_takeaways_allowed_roll8": _mean(allowed, "interceptions")
        + _mean(allowed, "fumble_recoveries"),
        "opponent_dst_touchdowns_allowed_roll8": _mean(allowed, "touchdowns"),
    }


def assemble_research_rows(
    matrix_rows: Iterable[PlayerGameFeatureMatrix],
    usage_by_player: Mapping[str, Sequence[UsageRecord]],
    dst_records: Sequence[DstRecord],
) -> list[ResearchRow]:
    rows: list[ResearchRow] = []
    for matrix_row in matrix_rows:
        position = str(matrix_row.position or "").strip().upper()
        if position not in SUPPORTED_POSITIONS:
            continue
        if position == "DST":
            features = _dst_features(matrix_row, dst_records)
            role = "DEFENSE"
        else:
            features, role = _offense_features(
                matrix_row,
                usage_by_player.get(str(matrix_row.player_id), ()),
            )
        rows.append(
            ResearchRow(
                season=int(matrix_row.season),
                week=int(matrix_row.week),
                player_id=str(matrix_row.player_id),
                position=position,
                role=role,
                actual_points=float(matrix_row.dk_points),
                features=features,
            )
        )
    return rows


def _feature_matrix(
    rows: Sequence[ResearchRow],
    feature_names: Sequence[str],
) -> np.ndarray:
    return np.asarray(
        [[_number(row.features.get(name)) for name in feature_names] for row in rows],
        dtype=float,
    )


def fit_ridge_model(
    rows: Sequence[ResearchRow],
    feature_names: Sequence[str],
    *,
    alpha: float = RIDGE_ALPHA,
) -> FittedRidge:
    if not rows:
        raise ValueError("At least one training row is required.")
    names = tuple(feature_names)
    x_rows = _feature_matrix(rows, names)
    y_rows = np.asarray([row.actual_points for row in rows], dtype=float)
    x_mean = np.mean(x_rows, axis=0)
    x_std = np.where(np.std(x_rows, axis=0) < 1e-6, 1.0, np.std(x_rows, axis=0))
    standardized = (x_rows - x_mean) / x_std
    weights, bias = _fit_ridge(standardized, y_rows, alpha=alpha)
    fitted = standardized @ weights + bias
    residuals = y_rows - fitted
    return FittedRidge(
        feature_names=names,
        x_mean=x_mean,
        x_std=x_std,
        weights=weights,
        bias=bias,
        residual_quantiles={
            "p10": float(np.quantile(residuals, 0.10)),
            "p25": float(np.quantile(residuals, 0.25)),
            "p75": float(np.quantile(residuals, 0.75)),
            "p90": float(np.quantile(residuals, 0.90)),
        },
    )


def predict(model: FittedRidge, rows: Sequence[ResearchRow]) -> np.ndarray:
    x_rows = _feature_matrix(rows, model.feature_names)
    return ((x_rows - model.x_mean) / model.x_std) @ model.weights + model.bias


def evaluate_model(model: FittedRidge, rows: Sequence[ResearchRow]) -> dict[str, Any]:
    actual = np.asarray([row.actual_points for row in rows], dtype=float)
    predicted = predict(model, rows)
    metrics = regression_metrics(actual, predicted)
    q = model.residual_quantiles
    metrics.update(
        {
            "p10_p90_coverage": float(
                np.mean((actual >= predicted + q["p10"]) & (actual <= predicted + q["p90"]))
            ),
            "p25_p75_coverage": float(
                np.mean((actual >= predicted + q["p25"]) & (actual <= predicted + q["p75"]))
            ),
        }
    )
    return metrics


def _rows_between(
    rows: Sequence[ResearchRow],
    start: tuple[int, int] | None,
    end: tuple[int, int],
) -> list[ResearchRow]:
    return [
        row
        for row in rows
        if (start is None or row.slice_key >= start) and row.slice_key <= end
    ]


def _window_metadata(rows: Sequence[ResearchRow]) -> dict[str, Any]:
    slices = sorted({row.slice_key for row in rows})
    return {
        "rows": len(rows),
        "slices": len(slices),
        "start": list(slices[0]) if slices else None,
        "end": list(slices[-1]) if slices else None,
    }


def _candidate_map(position: str) -> Mapping[str, tuple[str, ...]]:
    return DST_CANDIDATES if position == "DST" else OFFENSE_CANDIDATES


def _baseline_name(position: str) -> str:
    return "dst_history_baseline" if position == "DST" else "history_baseline"


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def lock_hash(payload: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "lock_hash"}
    return hashlib.sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest()


def select_candidates(
    rows: Sequence[ResearchRow],
    *,
    source_system: str = "draftkings",
) -> dict[str, Any]:
    train = _rows_between(rows, None, TRAIN_END)
    validation = _rows_between(rows, VALIDATION_START, VALIDATION_END)
    selections: dict[str, Any] = {}
    for position in SUPPORTED_POSITIONS:
        train_rows = [row for row in train if row.position == position]
        validation_rows = [row for row in validation if row.position == position]
        if len(train_rows) < 100 or len(validation_rows) < 20:
            raise ValueError(f"Insufficient {position} rows for selection.")
        candidates: dict[str, Any] = {}
        for name, feature_names in _candidate_map(position).items():
            model = fit_ridge_model(train_rows, feature_names)
            candidates[name] = {
                "feature_names": list(feature_names),
                "validation": evaluate_model(model, validation_rows),
            }
        baseline_name = _baseline_name(position)
        minimum_mae = min(
            float(details["validation"]["mae"])
            for details in candidates.values()
        )
        numerically_tied = [
            name
            for name, details in candidates.items()
            if float(details["validation"]["mae"]) <= minimum_mae + 1e-9
        ]
        best_name = min(
            numerically_tied,
            key=lambda name: (len(candidates[name]["feature_names"]), name),
        )
        baseline_mae = float(candidates[baseline_name]["validation"]["mae"])
        best_mae = float(candidates[best_name]["validation"]["mae"])
        improvement = _ratio(baseline_mae - best_mae, baseline_mae)
        selected_name = (
            best_name
            if best_name != baseline_name and improvement >= MIN_VALIDATION_IMPROVEMENT
            else baseline_name
        )
        selections[position] = {
            "baseline": baseline_name,
            "selected": selected_name,
            "validation_improvement_vs_baseline": improvement,
            "candidates": candidates,
        }

    payload: dict[str, Any] = {
        "contract_id": CONTRACT_ID,
        "source_system": source_system,
        "windows": {
            "train": _window_metadata(train),
            "validation": _window_metadata(validation),
            "holdout": {
                "start": list(HOLDOUT_START),
                "end": list(HOLDOUT_END),
                "metrics_read_during_selection": False,
            },
        },
        "ridge_alpha": RIDGE_ALPHA,
        "minimum_validation_improvement": MIN_VALIDATION_IMPROVEMENT,
        "excluded_unproven_features": [
            "historical_salary",
            "injury_status",
            "team_injury_counts",
            "game_total_line",
            "spread_line",
            "implied_team_totals",
        ],
        "selections": selections,
        "production_model_changed": False,
    }
    payload["lock_hash"] = lock_hash(payload)
    return payload


def verify_lock(payload: Mapping[str, Any]) -> None:
    if payload.get("contract_id") != CONTRACT_ID:
        raise ValueError("Candidate lock uses an incompatible contract.")
    actual = str(payload.get("lock_hash") or "")
    expected = lock_hash(payload)
    if not actual or actual != expected:
        raise ValueError("Candidate lock hash does not match its contents.")


def _role_metrics(
    model: FittedRidge,
    rows: Sequence[ResearchRow],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for role in sorted({row.role for row in rows}):
        role_rows = [row for row in rows if row.role == role]
        if len(role_rows) < 5:
            continue
        output[role] = evaluate_model(model, role_rows)
    return output


def evaluate_holdout(
    rows: Sequence[ResearchRow],
    candidate_lock: Mapping[str, Any],
) -> dict[str, Any]:
    verify_lock(candidate_lock)
    pre_holdout = _rows_between(rows, None, VALIDATION_END)
    holdout = _rows_between(rows, HOLDOUT_START, HOLDOUT_END)
    positions: dict[str, Any] = {}
    candidate_actual: list[float] = []
    candidate_predicted: list[float] = []
    baseline_actual: list[float] = []
    baseline_predicted: list[float] = []

    for position in SUPPORTED_POSITIONS:
        train_rows = [row for row in pre_holdout if row.position == position]
        holdout_rows = [row for row in holdout if row.position == position]
        selection = candidate_lock["selections"][position]
        selected_name = str(selection["selected"])
        baseline_name = str(selection["baseline"])
        candidates = _candidate_map(position)
        candidate_model = fit_ridge_model(train_rows, candidates[selected_name])
        baseline_model = fit_ridge_model(train_rows, candidates[baseline_name])
        candidate_metrics = evaluate_model(candidate_model, holdout_rows)
        baseline_metrics = evaluate_model(baseline_model, holdout_rows)
        candidate_predictions = predict(candidate_model, holdout_rows)
        baseline_predictions = predict(baseline_model, holdout_rows)
        actual = [row.actual_points for row in holdout_rows]
        candidate_actual.extend(actual)
        candidate_predicted.extend(candidate_predictions.tolist())
        baseline_actual.extend(actual)
        baseline_predicted.extend(baseline_predictions.tolist())
        positions[position] = {
            "selected": selected_name,
            "baseline": baseline_name,
            "candidate": candidate_metrics,
            "baseline_metrics": baseline_metrics,
            "mae_improvement_vs_baseline": _ratio(
                float(baseline_metrics["mae"]) - float(candidate_metrics["mae"]),
                float(baseline_metrics["mae"]),
            ),
            "roles": _role_metrics(candidate_model, holdout_rows),
        }

    candidate_overall = regression_metrics(
        np.asarray(candidate_actual), np.asarray(candidate_predicted)
    )
    baseline_overall = regression_metrics(
        np.asarray(baseline_actual), np.asarray(baseline_predicted)
    )
    position_regressions = {
        position: float(details["mae_improvement_vs_baseline"])
        for position, details in positions.items()
    }
    gates = {
        "overall_mae_non_regression": (
            float(candidate_overall["mae"]) <= float(baseline_overall["mae"])
        ),
        "dst_mae_non_regression": position_regressions["DST"] >= 0.0,
        "no_position_regresses_more_than_2pct": min(position_regressions.values()) >= -0.02,
        "role_metrics_reported": all(bool(positions[pos]["roles"]) for pos in OFFENSE_POSITIONS),
    }
    return {
        "contract_id": CONTRACT_ID,
        "lock_hash": candidate_lock["lock_hash"],
        "holdout": _window_metadata(holdout),
        "overall": {
            "candidate": candidate_overall,
            "baseline": baseline_overall,
            "mae_improvement_vs_baseline": _ratio(
                float(baseline_overall["mae"]) - float(candidate_overall["mae"]),
                float(baseline_overall["mae"]),
            ),
        },
        "positions": positions,
        "gates": gates,
        "status": "accepted" if all(gates.values()) else "rejected",
        "production_model_changed": False,
        "promotion_eligible": False,
        "promotion_blocker": (
            "Historical salary membership lacks preserved pre-lock observation timestamps; "
            "use a prospectively captured 2026 holdout before promotion."
        ),
    }


def _selection_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# MODEL-001 Candidate Lock",
        "",
        f"- Contract: `{payload['contract_id']}`",
        f"- Lock hash: `{payload['lock_hash']}`",
        "- Production model changed: `no`",
        "- Holdout metrics read during selection: `no`",
        "",
        "| Position | Baseline | Selected | Validation MAE lift |",
        "| --- | --- | --- | ---: |",
    ]
    for position in SUPPORTED_POSITIONS:
        row = payload["selections"][position]
        lines.append(
            f"| {position} | {row['baseline']} | {row['selected']} | "
            f"{100.0 * float(row['validation_improvement_vs_baseline']):+.2f}% |"
        )
    lines.extend(["", "## Validation Ablations", ""])
    for position in SUPPORTED_POSITIONS:
        selection = payload["selections"][position]
        baseline_mae = float(
            selection["candidates"][selection["baseline"]]["validation"]["mae"]
        )
        lines.extend(
            [
                f"### {position}",
                "",
                "| Candidate | Features | Validation MAE | Lift vs baseline |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for name, details in selection["candidates"].items():
            mae = float(details["validation"]["mae"])
            lift = _ratio(baseline_mae - mae, baseline_mae)
            lines.append(
                f"| {name} | {len(details['feature_names'])} | {mae:.3f} | "
                f"{100.0 * lift:+.2f}% |"
            )
        lines.append("")
    lines.extend(
        [
            "The lock was selected only from data through 2025 W11. Injury, market, and salary "
            "features are excluded because their historical observation time is not proven.",
        ]
    )
    return "\n".join(lines) + "\n"


def _holdout_markdown(payload: Mapping[str, Any]) -> str:
    overall = payload["overall"]
    lines = [
        "# MODEL-001 Locked Holdout Evaluation",
        "",
        f"- Status: `{payload['status']}`",
        f"- Candidate lock: `{payload['lock_hash']}`",
        f"- Candidate MAE: `{overall['candidate']['mae']:.3f}`",
        f"- Baseline MAE: `{overall['baseline']['mae']:.3f}`",
        f"- MAE lift: `{100.0 * float(overall['mae_improvement_vs_baseline']):+.2f}%`",
        "- Production model changed: `no`",
        "- Promotion eligible: `no`",
        "",
        "## Position Results",
        "",
        "| Position | Selected contract | Rows | Candidate MAE | Baseline MAE | Lift | P10-P90 | P25-P75 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for position in SUPPORTED_POSITIONS:
        row = payload["positions"][position]
        candidate = row["candidate"]
        baseline = row["baseline_metrics"]
        lines.append(
            f"| {position} | {row['selected']} | {candidate['rows']} | "
            f"{candidate['mae']:.3f} | {baseline['mae']:.3f} | "
            f"{100.0 * float(row['mae_improvement_vs_baseline']):+.2f}% | "
            f"{100.0 * candidate['p10_p90_coverage']:.1f}% | "
            f"{100.0 * candidate['p25_p75_coverage']:.1f}% |"
        )
    lines.extend(
        [
            "",
            "## Role Results",
            "",
            "| Position | Role | Rows | MAE | RMSE | P10-P90 | P25-P75 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for position in SUPPORTED_POSITIONS:
        for role, metrics in payload["positions"][position]["roles"].items():
            lines.append(
                f"| {position} | {role} | {metrics['rows']} | {metrics['mae']:.3f} | "
                f"{metrics['rmse']:.3f} | {100.0 * metrics['p10_p90_coverage']:.1f}% | "
                f"{100.0 * metrics['p25_p75_coverage']:.1f}% |"
            )
    lines.extend(["", "## Holdout Gates", ""])
    for name, passed in payload["gates"].items():
        lines.append(f"- `{name}`: `{'pass' if passed else 'fail'}`")
    lines.extend(
        [
            "",
            "## Promotion Decision",
            "",
            str(payload["promotion_blocker"]),
            "The evidence may accept or reject the feature decomposition, but it cannot change the "
            "active model. A prospective 2026 holdout must pass through MODEL-002 governance.",
        ]
    )
    return "\n".join(lines) + "\n"


def load_research_rows(
    *,
    source_system: str,
    season_start: int,
    season_end: int,
) -> list[ResearchRow]:
    with SessionLocal() as session:
        matrix_rows = session.execute(
            select(PlayerGameFeatureMatrix).where(
                and_(
                    PlayerGameFeatureMatrix.source_system == source_system,
                    PlayerGameFeatureMatrix.season >= season_start,
                    PlayerGameFeatureMatrix.season <= season_end,
                    PlayerGameFeatureMatrix.position.in_(SUPPORTED_POSITIONS),
                )
            )
        ).scalars().all()
        raw_rows = session.execute(
            select(RawNflWeeklyStat).where(
                and_(
                    RawNflWeeklyStat.season >= season_start - 1,
                    RawNflWeeklyStat.season <= season_end,
                    RawNflWeeklyStat.position.in_(OFFENSE_POSITIONS),
                )
            )
        ).scalars().all()
        dst_rows = session.execute(
            text(
                """
                SELECT season, week, team_id, opponent_team_id, dk_points, sacks,
                       interceptions, fumble_recoveries, interception_return_tds,
                       fumble_return_tds, special_teams_tds, points_allowed_score
                FROM target.fact_dst_game_actual
                WHERE season BETWEEN :history_start AND :season_end
                ORDER BY season, week, team_id
                """
            ),
            {"history_start": season_start - 1, "season_end": season_end},
        ).mappings().all()
    if not matrix_rows:
        raise ValueError("No player_game_feature_matrix rows were found.")
    return assemble_research_rows(
        matrix_rows,
        build_usage_records(raw_rows),
        build_dst_records(dst_rows),
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=("select", "holdout", "render"))
    parser.add_argument("--source-system", default="draftkings")
    parser.add_argument("--season-start", type=int, default=2024)
    parser.add_argument("--season-end", type=int, default=2025)
    parser.add_argument(
        "--lock-json",
        default="docs/MODEL-001_CANDIDATE_LOCK.json",
    )
    parser.add_argument(
        "--lock-report",
        default="docs/MODEL-001_CANDIDATE_LOCK.md",
    )
    parser.add_argument(
        "--holdout-json",
        default="docs/MODEL-001_HOLDOUT_EVIDENCE.json",
    )
    parser.add_argument(
        "--holdout-report",
        default="docs/MODEL-001_HOLDOUT_EVIDENCE.md",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    lock_path = Path(args.lock_json).expanduser().resolve()
    if args.phase == "render":
        holdout_path = Path(args.holdout_json).expanduser().resolve()
        if not lock_path.exists() or not holdout_path.exists():
            raise ValueError("Both candidate-lock and holdout JSON artifacts are required.")
        candidate_lock = json.loads(lock_path.read_text(encoding="utf-8"))
        verify_lock(candidate_lock)
        holdout_payload = json.loads(holdout_path.read_text(encoding="utf-8"))
        Path(args.lock_report).expanduser().resolve().write_text(
            _selection_markdown(candidate_lock),
            encoding="utf-8",
        )
        Path(args.holdout_report).expanduser().resolve().write_text(
            _holdout_markdown(holdout_payload),
            encoding="utf-8",
        )
        print(json.dumps({"phase": "render", "lock_hash": candidate_lock["lock_hash"]}, indent=2))
        return 0

    rows = load_research_rows(
        source_system=args.source_system,
        season_start=min(args.season_start, args.season_end),
        season_end=max(args.season_start, args.season_end),
    )
    if args.phase == "select":
        payload = select_candidates(rows, source_system=args.source_system)
        _write_json(lock_path, payload)
        report_path = Path(args.lock_report).expanduser().resolve()
        report_path.write_text(_selection_markdown(payload), encoding="utf-8")
        print(json.dumps({"phase": "select", "lock_hash": payload["lock_hash"]}, indent=2))
        return 0

    if not lock_path.exists():
        raise ValueError(f"Candidate lock does not exist: {lock_path}")
    candidate_lock = json.loads(lock_path.read_text(encoding="utf-8"))
    payload = evaluate_holdout(rows, candidate_lock)
    _write_json(Path(args.holdout_json).expanduser().resolve(), payload)
    Path(args.holdout_report).expanduser().resolve().write_text(
        _holdout_markdown(payload),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "phase": "holdout",
                "status": payload["status"],
                "candidate_mae": payload["overall"]["candidate"]["mae"],
                "baseline_mae": payload["overall"]["baseline"]["mae"],
                "production_model_changed": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
