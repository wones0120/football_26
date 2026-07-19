from __future__ import annotations

import hashlib
import json
import math
import subprocess
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from ..models import (
    CuratedSalary,
    PlayerAlias,
    ProjectionResidualSnapshot,
    RawNflSchedule,
    RawNflWeeklyStat,
    SimulatedPlayerOutcome,
    SimulationCalibrationFactor,
    SimulationRun,
)
from ..schemas import (
    BacktestRangeABRequest,
    BacktestRangeABResponse,
    BacktestRangeSliceABRowResponse,
    BacktestPlayerRowResponse,
    BacktestWeekABResponse,
    BacktestWeekRequest,
    BacktestWeekResponse,
    PointInTimeShockImpactResponse,
    PointInTimeShockRequest,
    PositionLearningRowResponse,
    ResidualAdjustmentImpactResponse,
    ResidualSnapshotBuildRequest,
    ResidualSnapshotResponse,
    RoleShockImpactResponse,
    RoleShockRequest,
    SalaryBucketLearningRowResponse,
    SimulatedPlayerOutcomeResponse,
    SimulateWeekRequest,
    SimulateWeekResponse,
)
from .matching import normalize_position
from .residual_learning import (
    DEFAULT_HISTORY_WINDOW_SLICES,
    DEFAULT_MAX_ABS_ADJUSTMENT,
    DEFAULT_MIN_TRAINING_SLICES,
    DEFAULT_PRIOR_STRENGTH,
    ELIGIBLE_POSITIONS,
    FEATURE_SET_HASH,
    ResidualModel,
    ResidualObservation,
    fit_residual_model,
    game_context_by_team,
    team_key,
)


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _num(data: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = data.get(key)
        if value in (None, ""):
            continue
        try:
            number = float(value)
            if math.isfinite(number):
                return number
        except (TypeError, ValueError):
            continue
    return 0.0


def calculate_dk_points(raw_row: dict[str, Any]) -> float:
    passing_yards = _num(raw_row, "passing_yards")
    passing_tds = _num(raw_row, "passing_tds")
    interceptions = _num(raw_row, "passing_interceptions", "interceptions")

    rushing_yards = _num(raw_row, "rushing_yards")
    rushing_tds = _num(raw_row, "rushing_tds")

    receptions = _num(raw_row, "receptions")
    receiving_yards = _num(raw_row, "receiving_yards")
    receiving_tds = _num(raw_row, "receiving_tds")

    passing_2pt = _num(raw_row, "passing_2pt_conversions")
    rushing_2pt = _num(raw_row, "rushing_2pt_conversions")
    receiving_2pt = _num(raw_row, "receiving_2pt_conversions")

    return_tds = _num(raw_row, "kickoff_return_tds") + _num(raw_row, "punt_return_tds")

    fumbles_lost = _num(raw_row, "fumbles_lost")
    if fumbles_lost == 0.0:
        fumbles_lost = (
            _num(raw_row, "rushing_fumbles_lost")
            + _num(raw_row, "receiving_fumbles_lost")
            + _num(raw_row, "sack_fumbles_lost")
        )

    points = (
        (passing_yards * 0.04)
        + (passing_tds * 4.0)
        - (interceptions * 1.0)
        + (rushing_yards * 0.1)
        + (rushing_tds * 6.0)
        + receptions
        + (receiving_yards * 0.1)
        + (receiving_tds * 6.0)
        + ((passing_2pt + rushing_2pt + receiving_2pt) * 2.0)
        + (return_tds * 6.0)
        - (fumbles_lost * 1.0)
    )

    if passing_yards >= 300:
        points += 3.0
    if rushing_yards >= 100:
        points += 3.0
    if receiving_yards >= 100:
        points += 3.0

    return max(points, 0.0)


def _season_week_ordinal(season: int, week: int) -> int:
    return (season * 25) + week


def _salary_bucket_for_salary(salary: int | None) -> str | None:
    if not isinstance(salary, int):
        return None
    if salary <= 4000:
        return "<=4k"
    if salary <= 5500:
        return "4k-5.5k"
    if salary <= 7000:
        return "5.5k-7k"
    return ">7k"


def _clip_multiplier(value: float, *, low: float = 0.8, high: float = 1.2) -> float:
    if not math.isfinite(value) or value <= 0:
        return 1.0
    return float(max(low, min(high, value)))


def _lift_pct(before: float, after: float, *, lower_is_better: bool) -> float | None:
    if not math.isfinite(before) or before <= 0 or not math.isfinite(after):
        return None
    if lower_is_better:
        return ((before - after) / before) * 100.0
    return ((after - before) / before) * 100.0


def _low_salary_group_key(position: str | None, salary: int | None) -> str | None:
    pos = normalize_position(position) or "UNK"
    bucket = _salary_bucket_for_salary(salary)
    if not bucket:
        return None
    return f"{pos}|{bucket}"


def _team_key(team: str | None) -> str:
    return (team or "").strip().upper()


def _role_shock_projection_multiplier(
    opportunity_multiplier: float,
    shock_roles: set[str],
) -> float:
    if "target" in shock_roles:
        return max(0.0, float(opportunity_multiplier))
    return max(0.0, 1.0 + (0.65 * (float(opportunity_multiplier) - 1.0)))


def _apply_point_in_time_shock(
    draws: np.ndarray,
    *,
    mean_multiplier: float,
    volatility_multiplier: float,
) -> np.ndarray:
    if draws.size == 0:
        return draws.copy()
    baseline_mean = float(np.mean(draws))
    shifted_mean = baseline_mean * float(mean_multiplier)
    centered = draws - baseline_mean
    return np.clip(
        shifted_mean + (centered * float(volatility_multiplier)),
        0.0,
        None,
    )


def _current_code_version() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parents[3],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"


def _snapshot_parameters(request: ResidualSnapshotBuildRequest) -> dict[str, Any]:
    return request.model_dump(mode="json")


def _snapshot_parameters_hash(parameters: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            parameters,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class SimulationService:
    DEFAULT_LOW_SALARY_THRESHOLD = 4500
    DEFAULT_LOW_SALARY_HIT_POINTS = 15.0

    def __init__(self, session: Session) -> None:
        self.session = session

    def _load_residual_model(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
    ) -> tuple[ResidualModel | None, int, list[str]]:
        if source_system != "draftkings":
            return (
                None,
                0,
                [
                    "online residual learning is currently available only for draftkings"
                ],
            )

        try:
            snapshots = self.session.execute(
                select(ProjectionResidualSnapshot)
                .where(
                    and_(
                        ProjectionResidualSnapshot.source_system
                        == source_system,
                        ProjectionResidualSnapshot.slate == slate,
                        ProjectionResidualSnapshot.status == "completed",
                        ProjectionResidualSnapshot.feature_set_hash
                        == FEATURE_SET_HASH,
                        or_(
                            ProjectionResidualSnapshot.season < season,
                            and_(
                                ProjectionResidualSnapshot.season == season,
                                ProjectionResidualSnapshot.week < week,
                            ),
                        ),
                    )
                )
                .order_by(
                    ProjectionResidualSnapshot.season.desc(),
                    ProjectionResidualSnapshot.week.desc(),
                )
                .limit(DEFAULT_HISTORY_WINDOW_SLICES)
            ).scalars().all()
        except ProgrammingError:
            self.session.rollback()
            return (
                None,
                0,
                [
                    "online residual learning is unavailable until migration "
                    "0009_projection_residual_snapshots.sql is applied"
                ],
            )
        snapshots = list(reversed(snapshots))
        if len(snapshots) < DEFAULT_MIN_TRAINING_SLICES:
            return (
                None,
                len(snapshots),
                [
                    "online residual learning requested but only "
                    f"{len(snapshots)}/{DEFAULT_MIN_TRAINING_SLICES} required "
                    "prior snapshots are available; baseline projections were used"
                ],
            )

        observations: list[ResidualObservation] = []
        valid_snapshots = 0
        warnings: list[str] = []
        for snapshot in snapshots:
            try:
                snapshot_observations = [
                    ResidualObservation.from_dict(row)
                    for row in list(snapshot.observations_json or [])
                ]
            except (KeyError, TypeError, ValueError) as exc:
                warnings.append(
                    "ignored invalid residual snapshot "
                    f"{snapshot.projection_residual_snapshot_id}: {exc}"
                )
                continue
            if not snapshot_observations:
                warnings.append(
                    "ignored empty residual snapshot "
                    f"{snapshot.projection_residual_snapshot_id}"
                )
                continue
            observations.extend(snapshot_observations)
            valid_snapshots += 1

        if valid_snapshots < DEFAULT_MIN_TRAINING_SLICES:
            warnings.append(
                "online residual learning had fewer than "
                f"{DEFAULT_MIN_TRAINING_SLICES} valid prior snapshots; "
                "baseline projections were used"
            )
            return None, valid_snapshots, warnings

        model = fit_residual_model(
            observations,
            prior_strength=DEFAULT_PRIOR_STRENGTH,
            max_abs_adjustment=DEFAULT_MAX_ABS_ADJUSTMENT,
        )
        if model.trained_through >= (season, week):
            raise AssertionError(
                "Residual snapshot selection included the target or a future week."
            )
        return model, valid_snapshots, warnings

    def _actual_points_by_master(
        self,
        *,
        season: int,
        week: int,
        tracked_player_ids: list[str],
        player_id_to_masters: dict[str, set[str]],
    ) -> dict[str, float]:
        if not tracked_player_ids:
            return {}
        rows = self.session.execute(
            select(RawNflWeeklyStat).where(
                and_(
                    RawNflWeeklyStat.source_system == "nflreadpy",
                    RawNflWeeklyStat.season == season,
                    RawNflWeeklyStat.week == week,
                    RawNflWeeklyStat.player_id.in_(tracked_player_ids),
                )
            )
        ).scalars().all()
        points_by_master: dict[str, float] = {}
        for row in rows:
            if not row.player_id:
                continue
            points = calculate_dk_points(row.raw_row_json or {})
            if not math.isfinite(points):
                continue
            for master_id in player_id_to_masters.get(row.player_id, set()):
                points_by_master[str(master_id)] = max(
                    points_by_master.get(str(master_id), 0.0),
                    float(points),
                )
        return points_by_master

    def build_residual_snapshot(
        self,
        request: ResidualSnapshotBuildRequest,
    ) -> ResidualSnapshotResponse:
        parameters = _snapshot_parameters(request)
        parameters_hash = _snapshot_parameters_hash(parameters)
        existing = self.session.execute(
            select(ProjectionResidualSnapshot).where(
                and_(
                    ProjectionResidualSnapshot.source_system
                    == request.source_system,
                    ProjectionResidualSnapshot.season == request.season,
                    ProjectionResidualSnapshot.week == request.week,
                    ProjectionResidualSnapshot.slate == request.slate,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.parameters_hash != parameters_hash:
                raise ValueError(
                    "An immutable residual snapshot already exists for "
                    f"{request.source_system} {request.season}-W{request.week:02d} "
                    f"{request.slate} with different parameters."
                )
            return ResidualSnapshotResponse(
                projection_residual_snapshot_id=(
                    existing.projection_residual_snapshot_id
                ),
                source_system=existing.source_system,
                season=existing.season,
                week=existing.week,
                slate=existing.slate,
                parameters_hash=existing.parameters_hash,
                feature_set_hash=existing.feature_set_hash,
                code_version=existing.code_version,
                observations_count=existing.observations_count,
                status=existing.status,
                created_at=existing.created_at,
                created=False,
            )

        (
            _players_considered,
            simulated_rows,
            player_id_to_masters,
            tracked_player_ids,
            _role_shock_impacts,
            _point_in_time_shock_impacts,
            _residual_adjustment_impacts,
            _residual_snapshot_count,
            _scenario_warnings,
        ) = self._simulate_salary_slice(
            source_system=request.source_system,
            season=request.season,
            week=request.week,
            slate=request.slate,
            iterations=request.iterations,
            min_history_games=request.min_history_games,
            prior_weight=request.prior_weight,
            noise_scale=request.noise_scale,
            random_seed=request.random_seed,
            use_calibration=True,
            role_shocks=[],
        )
        actual_by_master = self._actual_points_by_master(
            season=request.season,
            week=request.week,
            tracked_player_ids=tracked_player_ids,
            player_id_to_masters=player_id_to_masters,
        )
        salary_rows = self.session.execute(
            select(CuratedSalary).where(
                and_(
                    CuratedSalary.source_system == request.source_system,
                    CuratedSalary.season == request.season,
                    CuratedSalary.week == request.week,
                    CuratedSalary.slate == request.slate,
                )
            )
        ).scalars().all()
        salary_by_master = {
            str(row.player_master_id): row
            for row in salary_rows
            if row.player_master_id
        }
        salary_by_source = {
            str(row.source_player_key): row
            for row in salary_rows
            if row.source_player_key
        }
        schedule_rows = self.session.execute(
            select(RawNflSchedule).where(
                and_(
                    RawNflSchedule.source_system == "nflreadpy",
                    RawNflSchedule.season == request.season,
                    RawNflSchedule.week == request.week,
                )
            )
        ).scalars().all()
        context_by_team = game_context_by_team(schedule_rows)

        observations_by_identity: dict[str, ResidualObservation] = {}
        for row in simulated_rows:
            position = normalize_position(row.get("position"))
            if position not in ELIGIBLE_POSITIONS:
                continue
            master_id = (
                str(row["player_master_id"])
                if row.get("player_master_id")
                else None
            )
            source_key = (
                str(row["source_player_key"])
                if row.get("source_player_key")
                else None
            )
            if not master_id and not source_key:
                continue
            actual_points = actual_by_master.get(master_id or "")
            if actual_points is None:
                continue
            salary_row = (
                salary_by_master.get(master_id or "")
                or salary_by_source.get(source_key or "")
            )
            team = team_key(
                (salary_row.team if salary_row is not None else None)
                or row.get("team")
            )
            context = context_by_team.get(team, {})
            identity = (
                f"master:{master_id}"
                if master_id
                else f"source:{source_key}"
            )
            observations_by_identity[identity] = ResidualObservation(
                season=request.season,
                week=request.week,
                player_master_id=master_id,
                source_player_key=source_key,
                team=team or None,
                opponent=(
                    team_key(salary_row.opponent) or None
                    if salary_row is not None
                    else None
                ),
                position=position,
                salary=(
                    int(salary_row.salary)
                    if salary_row is not None
                    and salary_row.salary is not None
                    else (
                        int(row["salary"])
                        if row.get("salary") is not None
                        else None
                    )
                ),
                game_total_line=(
                    float(context["game_total_line"])
                    if context.get("game_total_line") is not None
                    else None
                ),
                team_spread_line=(
                    float(context["team_spread_line"])
                    if context.get("team_spread_line") is not None
                    else None
                ),
                baseline_points=float(row["mean_points"]),
                actual_points=float(actual_points),
            )
        observations = sorted(
            observations_by_identity.values(),
            key=lambda row: (
                row.position,
                row.identity_key or "",
            ),
        )
        if not observations:
            raise ValueError(
                "Residual snapshot produced no canonical observations with actuals."
            )

        snapshot = ProjectionResidualSnapshot(
            projection_residual_snapshot_id=str(uuid.uuid4()),
            source_system=request.source_system,
            season=request.season,
            week=request.week,
            slate=request.slate,
            parameters_hash=parameters_hash,
            parameters_json=parameters,
            feature_set_hash=FEATURE_SET_HASH,
            code_version=_current_code_version(),
            observations_json=[row.to_dict() for row in observations],
            observations_count=len(observations),
            status="completed",
            created_at=utcnow_naive(),
        )
        self.session.add(snapshot)
        self.session.commit()
        self.session.refresh(snapshot)
        return ResidualSnapshotResponse(
            projection_residual_snapshot_id=(
                snapshot.projection_residual_snapshot_id
            ),
            source_system=snapshot.source_system,
            season=snapshot.season,
            week=snapshot.week,
            slate=snapshot.slate,
            parameters_hash=snapshot.parameters_hash,
            feature_set_hash=snapshot.feature_set_hash,
            code_version=snapshot.code_version,
            observations_count=snapshot.observations_count,
            status=snapshot.status,
            created_at=snapshot.created_at,
            created=True,
        )

    def _recent_opportunity_by_master(
        self,
        *,
        history_rows: list[RawNflWeeklyStat],
        player_id_to_masters: dict[str, set[str]],
        salary_rows: list[CuratedSalary],
        history_weeks: int = 4,
    ) -> dict[str, float]:
        team_by_master = {
            str(row.player_master_id): _team_key(row.team)
            for row in salary_rows
            if row.player_master_id and _team_key(row.team)
        }
        rows_by_team_slice: dict[
            str,
            dict[tuple[int, int], list[RawNflWeeklyStat]],
        ] = defaultdict(lambda: defaultdict(list))
        for row in history_rows:
            team = _team_key(row.team)
            if team:
                rows_by_team_slice[team][(int(row.season), int(row.week))].append(row)

        opportunity_by_master: dict[str, float] = defaultdict(float)
        for team, slices in rows_by_team_slice.items():
            recent_keys = sorted(slices, reverse=True)[: max(1, history_weeks)]
            for slice_key in recent_keys:
                for row in slices[slice_key]:
                    if not row.player_id:
                        continue
                    opportunity = max(
                        0.0,
                        _num(row.raw_row_json or {}, "carries")
                        + _num(row.raw_row_json or {}, "targets"),
                    )
                    for master_id in player_id_to_masters.get(row.player_id, set()):
                        if team_by_master.get(str(master_id)) == team:
                            opportunity_by_master[str(master_id)] += opportunity
        return dict(opportunity_by_master)

    def _role_shock_multipliers(
        self,
        *,
        salary_rows: list[CuratedSalary],
        opportunity_by_master: dict[str, float],
        role_shocks: list[RoleShockRequest],
    ) -> tuple[dict[str, float], dict[str, set[str]], list[str]]:
        unique_rows_by_master: dict[str, CuratedSalary] = {}
        rows_by_source_key: dict[str, CuratedSalary] = {}
        for row in salary_rows:
            if row.player_master_id:
                unique_rows_by_master.setdefault(str(row.player_master_id), row)
            if row.source_player_key:
                rows_by_source_key.setdefault(str(row.source_player_key), row)

        multipliers: dict[str, float] = {
            master_id: 1.0 for master_id in unique_rows_by_master
        }
        roles_by_master: dict[str, set[str]] = defaultdict(set)
        warnings: list[str] = []
        seen_targets: set[str] = set()

        for index, shock in enumerate(role_shocks, start=1):
            target_row: CuratedSalary | None = None
            if shock.player_master_id:
                target_row = unique_rows_by_master.get(str(shock.player_master_id))
            if target_row is None and shock.source_player_key:
                target_row = rows_by_source_key.get(str(shock.source_player_key))
            if target_row is None or not target_row.player_master_id:
                warnings.append(
                    f"role_shock[{index}] target was not found in the selected salary slice"
                )
                continue

            target_master = str(target_row.player_master_id)
            if target_master in seen_targets:
                warnings.append(
                    f"role_shock[{index}] duplicates target {target_master}; ignored"
                )
                continue
            seen_targets.add(target_master)
            target_position = normalize_position(target_row.position)
            if target_position not in {"RB", "WR", "TE"}:
                warnings.append(
                    f"role_shock[{index}] target {target_row.player_name} has unsupported "
                    f"position {target_position or 'unknown'}"
                )
                continue

            target_team = _team_key(target_row.team)
            recipients = [
                row
                for master_id, row in unique_rows_by_master.items()
                if master_id != target_master
                and _team_key(row.team) == target_team
                and (
                    normalize_position(row.position) == target_position
                    if shock.reallocation_scope == "same_position"
                    else normalize_position(row.position) in {"RB", "WR", "TE"}
                )
            ]
            roles_by_master[target_master].add("target")
            multipliers[target_master] *= float(shock.retained_opportunity_share)

            if not recipients or shock.retained_opportunity_share >= 1.0:
                if not recipients and shock.retained_opportunity_share < 1.0:
                    warnings.append(
                        f"role_shock[{index}] found no eligible recipients for "
                        f"{target_row.player_name}"
                    )
                continue

            recipient_opportunities = {
                str(row.player_master_id): float(
                    opportunity_by_master.get(str(row.player_master_id), 0.0)
                )
                for row in recipients
                if row.player_master_id
                and float(
                    opportunity_by_master.get(str(row.player_master_id), 0.0)
                )
                > 0.0
            }
            if not recipient_opportunities:
                recipient_opportunities = {
                    str(row.player_master_id): 1.0
                    for row in recipients
                    if row.player_master_id
                }
                warnings.append(
                    f"role_shock[{index}] inferred recipient opportunity for "
                    f"{target_row.player_name}"
                )
            target_opportunity = float(opportunity_by_master.get(target_master, 0.0))
            if target_opportunity <= 0.0:
                target_opportunity = float(
                    np.median(list(recipient_opportunities.values()))
                )
                warnings.append(
                    f"role_shock[{index}] inferred recent opportunity for "
                    f"{target_row.player_name}"
                )
            removed_opportunity = target_opportunity * (
                1.0 - float(shock.retained_opportunity_share)
            )
            recipient_total = float(sum(recipient_opportunities.values()))
            if removed_opportunity <= 0.0 or recipient_total <= 0.0:
                continue

            for recipient_master, recipient_opportunity in recipient_opportunities.items():
                allocated = removed_opportunity * (
                    recipient_opportunity / recipient_total
                )
                recipient_boost = min(
                    float(shock.max_recipient_multiplier),
                    1.0 + (allocated / recipient_opportunity),
                )
                multipliers[recipient_master] = min(
                    float(shock.max_recipient_multiplier),
                    multipliers.get(recipient_master, 1.0) * recipient_boost,
                )
                roles_by_master[recipient_master].add("recipient")

        return multipliers, dict(roles_by_master), warnings

    def _point_in_time_shock_targets(
        self,
        *,
        salary_rows: list[CuratedSalary],
        shocks: list[PointInTimeShockRequest],
    ) -> dict[str, list[tuple[int, PointInTimeShockRequest]]]:
        unique_rows_by_master: dict[str, CuratedSalary] = {}
        masters_by_source_key: dict[str, set[str]] = defaultdict(set)
        for row in salary_rows:
            if not row.player_master_id:
                continue
            master_id = str(row.player_master_id)
            unique_rows_by_master.setdefault(master_id, row)
            if row.source_player_key:
                masters_by_source_key[str(row.source_player_key)].add(master_id)

        shocks_by_master: dict[
            str,
            list[tuple[int, PointInTimeShockRequest]],
        ] = defaultdict(list)
        for index, shock in enumerate(shocks, start=1):
            target_masters: set[str] = set()
            master_ids = {
                str(value).strip()
                for value in shock.player_master_ids
                if str(value).strip()
            }
            source_keys = {
                str(value).strip()
                for value in shock.source_player_keys
                if str(value).strip()
            }
            if master_ids or source_keys:
                missing_master_ids = sorted(
                    master_ids - set(unique_rows_by_master)
                )
                if missing_master_ids:
                    raise ValueError(
                        f"point_in_time_shocks[{index}] canonical player IDs "
                        "were not found in the selected salary slice: "
                        f"{', '.join(missing_master_ids)}"
                    )
                target_masters.update(master_ids)
                for source_key in sorted(source_keys):
                    source_masters = masters_by_source_key.get(source_key, set())
                    if not source_masters:
                        raise ValueError(
                            f"point_in_time_shocks[{index}] source-native player "
                            "ID was not found in the selected salary slice: "
                            f"{source_key}"
                        )
                    if len(source_masters) > 1:
                        raise ValueError(
                            f"point_in_time_shocks[{index}] source-native player "
                            f"ID is ambiguous: {source_key}"
                        )
                    target_masters.update(source_masters)
            else:
                teams = {
                    _team_key(team)
                    for team in shock.teams
                    if _team_key(team)
                }
                positions = {
                    normalize_position(position)
                    for position in shock.positions
                    if normalize_position(position)
                }
                pool_teams = {
                    _team_key(row.team)
                    for row in unique_rows_by_master.values()
                    if _team_key(row.team)
                }
                missing_teams = sorted(teams - pool_teams)
                if missing_teams:
                    raise ValueError(
                        f"point_in_time_shocks[{index}] teams were not found in "
                        "the selected mapped salary slice: "
                        f"{', '.join(missing_teams)}"
                    )
                target_masters = {
                    master_id
                    for master_id, row in unique_rows_by_master.items()
                    if _team_key(row.team) in teams
                    and normalize_position(row.position) in positions
                }
                if not target_masters:
                    raise ValueError(
                        f"point_in_time_shocks[{index}] matched no mapped players "
                        "for the selected teams and positions"
                    )

            for master_id in sorted(target_masters):
                shocks_by_master[master_id].append((index, shock))

        return dict(shocks_by_master)

    def _load_calibration_multipliers(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
    ) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
        history_filter = or_(
            SimulationCalibrationFactor.calibrated_season < season,
            and_(
                SimulationCalibrationFactor.calibrated_season == season,
                SimulationCalibrationFactor.calibrated_week < week,
            ),
        )
        try:
            rows = self.session.execute(
                select(SimulationCalibrationFactor).where(
                    and_(
                        SimulationCalibrationFactor.source_system == source_system,
                        SimulationCalibrationFactor.slate == slate,
                        history_filter,
                    )
                )
            ).scalars().all()
            if not rows:
                rows = self.session.execute(
                    select(SimulationCalibrationFactor).where(
                        and_(
                            SimulationCalibrationFactor.source_system == source_system,
                            history_filter,
                        )
                    )
                ).scalars().all()
        except ProgrammingError:
            self.session.rollback()
            return {}, {}, {}

        target_ord = _season_week_ordinal(season, week)
        position_acc: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        salary_acc: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        low_salary_group_acc: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for row in rows:
            factor_ord = _season_week_ordinal(row.calibrated_season, row.calibrated_week)
            weeks_ago = max(0, target_ord - factor_ord)
            recency_weight = 0.92 ** min(weeks_ago, 80)
            sample_weight = max(1.0, float(row.sample_size))
            cross_slate_discount = 1.0 if row.slate == slate else 0.7
            weight = recency_weight * sample_weight * cross_slate_discount
            if weight <= 0:
                continue

            if row.scope == "position":
                acc = position_acc[row.scope_key]
            elif row.scope == "salary_bucket":
                acc = salary_acc[row.scope_key]
            elif row.scope == "low_salary_group":
                if (
                    row.low_salary_threshold != self.DEFAULT_LOW_SALARY_THRESHOLD
                    or row.low_salary_hit_points is None
                    or not math.isclose(row.low_salary_hit_points, self.DEFAULT_LOW_SALARY_HIT_POINTS, rel_tol=0.0, abs_tol=1e-9)
                ):
                    continue
                acc = low_salary_group_acc[row.scope_key]
            else:
                continue
            acc[0] += weight * row.multiplier
            acc[1] += weight

        position_multipliers: dict[str, float] = {}
        salary_bucket_multipliers: dict[str, float] = {}
        low_salary_group_multipliers: dict[str, float] = {}
        for key, (weighted_sum, total_weight) in position_acc.items():
            if total_weight > 0:
                position_multipliers[key] = _clip_multiplier(weighted_sum / total_weight, low=0.85, high=1.15)
        for key, (weighted_sum, total_weight) in salary_acc.items():
            if total_weight > 0:
                salary_bucket_multipliers[key] = _clip_multiplier(
                    weighted_sum / total_weight,
                    low=0.85,
                    high=1.15,
                )
        for key, (weighted_sum, total_weight) in low_salary_group_acc.items():
            if total_weight > 0:
                low_salary_group_multipliers[key] = _clip_multiplier(
                    weighted_sum / total_weight,
                    low=0.75,
                    high=1.35,
                )

        return position_multipliers, salary_bucket_multipliers, low_salary_group_multipliers

    def _persist_calibration_factors(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
        position_learning: list[PositionLearningRowResponse],
        salary_bucket_learning: list[SalaryBucketLearningRowResponse],
        with_actuals: list[BacktestPlayerRowResponse],
        low_salary_threshold: int,
        low_salary_hit_points: float,
    ) -> tuple[int, int, int]:
        now = utcnow_naive()
        rows: list[SimulationCalibrationFactor] = []

        for row in position_learning:
            if row.players < 8:
                continue
            rows.append(
                SimulationCalibrationFactor(
                    source_system=source_system,
                    slate=slate,
                    scope="position",
                    scope_key=row.position,
                    calibrated_season=season,
                    calibrated_week=week,
                    sample_size=row.players,
                    multiplier=_clip_multiplier(row.adjustment_multiplier),
                    low_salary_threshold=None,
                    low_salary_hit_points=None,
                    created_at=now,
                )
            )

        for row in salary_bucket_learning:
            if row.players < 12:
                continue
            raw_multiplier = (row.mean_actual / row.mean_prediction) if row.mean_prediction > 0 else 1.0
            rows.append(
                SimulationCalibrationFactor(
                    source_system=source_system,
                    slate=slate,
                    scope="salary_bucket",
                    scope_key=row.bucket,
                    calibrated_season=season,
                    calibrated_week=week,
                    sample_size=row.players,
                    multiplier=_clip_multiplier(raw_multiplier),
                    low_salary_threshold=None,
                    low_salary_hit_points=None,
                    created_at=now,
                )
            )

        low_groups: dict[str, list[BacktestPlayerRowResponse]] = defaultdict(list)
        for row in with_actuals:
            if not isinstance(row.salary, int) or row.salary > low_salary_threshold:
                continue
            key = _low_salary_group_key(row.position, row.salary)
            if not key:
                continue
            low_groups[key].append(row)

        for key, grouped_rows in low_groups.items():
            if len(grouped_rows) < 16:
                continue
            actual_hit_rate = float(
                np.mean([1.0 if row.actual_points >= low_salary_hit_points else 0.0 for row in grouped_rows])
            )
            predicted_hit_rate = float(
                np.mean([float(row.predicted_low_hit_prob or 0.0) for row in grouped_rows])
            )
            if predicted_hit_rate <= 0.01:
                continue
            rows.append(
                SimulationCalibrationFactor(
                    source_system=source_system,
                    slate=slate,
                    scope="low_salary_group",
                    scope_key=key,
                    calibrated_season=season,
                    calibrated_week=week,
                    sample_size=len(grouped_rows),
                    multiplier=_clip_multiplier(actual_hit_rate / predicted_hit_rate, low=0.7, high=1.4),
                    low_salary_threshold=low_salary_threshold,
                    low_salary_hit_points=low_salary_hit_points,
                    created_at=now,
                )
            )

        if not rows:
            return 0, 0, 0

        self.session.add_all(rows)
        self.session.commit()
        position_rows = sum(1 for row in rows if row.scope == "position")
        salary_rows = sum(1 for row in rows if row.scope == "salary_bucket")
        low_rows = sum(1 for row in rows if row.scope == "low_salary_group")
        return position_rows, salary_rows, low_rows

    def _simulate_salary_slice(
        self,
        *,
        source_system: str,
        season: int,
        week: int,
        slate: str,
        iterations: int,
        min_history_games: int,
        prior_weight: float,
        noise_scale: float,
        random_seed: int | None,
        use_calibration: bool = True,
        use_residual_learning: bool = False,
        low_hit_points: float | None = None,
        role_shocks: list[RoleShockRequest] | None = None,
        point_in_time_shocks: list[PointInTimeShockRequest] | None = None,
    ) -> tuple[
        int,
        list[dict[str, Any]],
        dict[str, set[str]],
        list[str],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        int,
        list[str],
    ]:
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

        players_considered = len(salary_rows)
        if not salary_rows:
            raise ValueError(
                f"No curated salary rows found for {source_system} {season} week {week} slate={slate}."
            )

        rows_with_master = [row for row in salary_rows if row.player_master_id]
        if not rows_with_master:
            raise ValueError(
                "No player_master_id mappings found in selected salary slice. Resolve identities first."
            )

        master_ids = sorted({row.player_master_id for row in rows_with_master if row.player_master_id})
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
            if not source_key:
                continue
            player_id_to_masters[source_key].add(player_master_id)

        tracked_player_ids = sorted(player_id_to_masters.keys())
        if not tracked_player_ids:
            raise ValueError("No nflreadpy aliases found for salary player_master_id records.")

        history_filter = or_(
            RawNflWeeklyStat.season < season,
            and_(
                RawNflWeeklyStat.season == season,
                RawNflWeeklyStat.week < week,
            ),
        )

        history_rows = self.session.execute(
            select(RawNflWeeklyStat).where(
                and_(
                    RawNflWeeklyStat.source_system == "nflreadpy",
                    RawNflWeeklyStat.player_id.in_(tracked_player_ids),
                    history_filter,
                )
            )
        ).scalars().all()

        history_points_by_master: dict[str, list[float]] = defaultdict(list)
        position_prior_points: dict[str, list[float]] = defaultdict(list)
        for row in history_rows:
            raw = row.raw_row_json or {}
            points = calculate_dk_points(raw)
            if not math.isfinite(points):
                continue
            position = normalize_position(row.position)
            if position:
                position_prior_points[position].append(points)
            if row.player_id:
                for master in player_id_to_masters.get(row.player_id, set()):
                    history_points_by_master[master].append(points)

        salary_positions = {
            normalize_position(row.position)
            for row in rows_with_master
            if normalize_position(row.position)
        }
        missing_positions = {p for p in salary_positions if p not in position_prior_points}
        if missing_positions:
            prior_rows = self.session.execute(
                select(RawNflWeeklyStat).where(
                    and_(
                        RawNflWeeklyStat.source_system == "nflreadpy",
                        RawNflWeeklyStat.position.in_(sorted(missing_positions)),
                        history_filter,
                    )
                )
            ).scalars().all()
            for row in prior_rows:
                raw = row.raw_row_json or {}
                points = calculate_dk_points(raw)
                if not math.isfinite(points):
                    continue
                position = normalize_position(row.position)
                if position:
                    position_prior_points[position].append(points)

        global_prior: list[float] = []
        for values in position_prior_points.values():
            global_prior.extend(values)

        opportunity_by_master = self._recent_opportunity_by_master(
            history_rows=history_rows,
            player_id_to_masters=player_id_to_masters,
            salary_rows=rows_with_master,
        )
        (
            role_shock_multipliers,
            role_shock_roles,
            scenario_warnings,
        ) = self._role_shock_multipliers(
            salary_rows=rows_with_master,
            opportunity_by_master=opportunity_by_master,
            role_shocks=list(role_shocks or []),
        )
        point_in_time_shocks_by_master = self._point_in_time_shock_targets(
            salary_rows=rows_with_master,
            shocks=list(point_in_time_shocks or []),
        )

        if use_calibration:
            (
                position_multipliers,
                salary_bucket_multipliers,
                low_salary_group_multipliers,
            ) = self._load_calibration_multipliers(
                source_system=source_system,
                season=season,
                week=week,
                slate=slate,
            )
        else:
            position_multipliers, salary_bucket_multipliers, low_salary_group_multipliers = {}, {}, {}

        residual_model: ResidualModel | None = None
        residual_snapshot_count = 0
        residual_context_by_team: dict[str, dict[str, float]] = {}
        if use_residual_learning:
            (
                residual_model,
                residual_snapshot_count,
                residual_warnings,
            ) = self._load_residual_model(
                source_system=source_system,
                season=season,
                week=week,
                slate=slate,
            )
            scenario_warnings.extend(residual_warnings)
            if residual_model is not None:
                schedule_rows = self.session.execute(
                    select(RawNflSchedule).where(
                        and_(
                            RawNflSchedule.source_system == "nflreadpy",
                            RawNflSchedule.season == season,
                            RawNflSchedule.week == week,
                        )
                    )
                ).scalars().all()
                residual_context_by_team = game_context_by_team(schedule_rows)

        rng = np.random.default_rng(random_seed)
        simulated_rows: list[dict[str, Any]] = []
        role_shock_impacts: list[dict[str, Any]] = []
        point_in_time_shock_impacts: list[dict[str, Any]] = []
        residual_adjustment_impacts: list[dict[str, Any]] = []
        impacted_masters_simulated: set[str] = set()
        point_in_time_masters_simulated: set[str] = set()

        for salary_row in rows_with_master:
            if not salary_row.player_master_id:
                continue
            player_history = np.asarray(
                history_points_by_master.get(salary_row.player_master_id, []),
                dtype=float,
            )

            pos = normalize_position(salary_row.position)
            position_prior = np.asarray(position_prior_points.get(pos or "", []), dtype=float)
            fallback_prior = np.asarray(global_prior, dtype=float)

            prior = position_prior if position_prior.size > 0 else fallback_prior
            if player_history.size == 0 and prior.size == 0:
                continue

            if player_history.size > 0 and prior.size > 0:
                mix_weight = min(0.92, player_history.size / (player_history.size + prior_weight))
                choose_player = rng.random(iterations) < mix_weight
                draws = np.where(
                    choose_player,
                    rng.choice(player_history, size=iterations, replace=True),
                    rng.choice(prior, size=iterations, replace=True),
                )
                base_std = float(np.std(player_history)) if player_history.size > 1 else float(np.std(prior))
            elif player_history.size > 0:
                draws = rng.choice(player_history, size=iterations, replace=True)
                base_std = float(np.std(player_history)) if player_history.size > 1 else 2.0
            else:
                draws = rng.choice(prior, size=iterations, replace=True)
                base_std = float(np.std(prior)) if prior.size > 1 else 2.0

            if noise_scale > 0:
                draws = draws + rng.normal(
                    loc=0.0,
                    scale=max(base_std, 1.0) * noise_scale,
                    size=iterations,
                )
            combined_multiplier = 1.0
            if pos:
                combined_multiplier *= position_multipliers.get(pos, 1.0)
            salary_bucket = _salary_bucket_for_salary(salary_row.salary)
            if salary_bucket:
                combined_multiplier *= salary_bucket_multipliers.get(salary_bucket, 1.0)
                if isinstance(salary_row.salary, int) and salary_row.salary <= self.DEFAULT_LOW_SALARY_THRESHOLD:
                    low_group_key = _low_salary_group_key(salary_row.position, salary_row.salary)
                    if low_group_key:
                        combined_multiplier *= low_salary_group_multipliers.get(low_group_key, 1.0)
            combined_multiplier = _clip_multiplier(combined_multiplier, low=0.75, high=1.3)
            draws = np.clip(draws * combined_multiplier, 0.0, None)
            if residual_model is not None and pos in ELIGIBLE_POSITIONS:
                residual_baseline_draws = draws
                residual_baseline_mean = float(np.mean(residual_baseline_draws))
                residual_baseline_p90 = float(
                    np.percentile(residual_baseline_draws, 90)
                )
                team = team_key(salary_row.team)
                residual_context = residual_context_by_team.get(team, {})
                residual_observation = ResidualObservation(
                    season=season,
                    week=week,
                    player_master_id=salary_row.player_master_id,
                    source_player_key=salary_row.source_player_key,
                    team=team or None,
                    opponent=team_key(salary_row.opponent) or None,
                    position=pos,
                    salary=salary_row.salary,
                    game_total_line=(
                        float(residual_context["game_total_line"])
                        if residual_context.get("game_total_line") is not None
                        else None
                    ),
                    team_spread_line=(
                        float(residual_context["team_spread_line"])
                        if residual_context.get("team_spread_line") is not None
                        else None
                    ),
                    baseline_points=residual_baseline_mean,
                    actual_points=0.0,
                )
                residual_adjustment, scopes_used = (
                    residual_model.adjustment_for(residual_observation)
                )
                draws = np.clip(
                    residual_baseline_draws + residual_adjustment,
                    0.0,
                    None,
                )
                residual_adjustment_impacts.append(
                    {
                        "player_master_id": salary_row.player_master_id,
                        "source_player_key": salary_row.source_player_key,
                        "player_name": salary_row.player_name,
                        "team": salary_row.team,
                        "position": salary_row.position,
                        "adjustment_points": residual_adjustment,
                        "scopes_used": scopes_used,
                        "baseline_mean_points": residual_baseline_mean,
                        "adjusted_mean_points": float(np.mean(draws)),
                        "baseline_p90_points": residual_baseline_p90,
                        "adjusted_p90_points": float(
                            np.percentile(draws, 90)
                        ),
                    }
                )
            baseline_draws = draws
            opportunity_multiplier = float(
                role_shock_multipliers.get(str(salary_row.player_master_id), 1.0)
            )
            shock_roles = role_shock_roles.get(
                str(salary_row.player_master_id),
                set(),
            )
            projection_multiplier = _role_shock_projection_multiplier(
                opportunity_multiplier,
                shock_roles,
            )
            draws = np.clip(baseline_draws * projection_multiplier, 0.0, None)
            point_in_time_shocks_for_player = (
                point_in_time_shocks_by_master.get(
                    str(salary_row.player_master_id),
                    [],
                )
            )
            for shock_index, point_in_time_shock in point_in_time_shocks_for_player:
                point_in_time_masters_simulated.add(
                    str(salary_row.player_master_id)
                )
                shock_baseline_draws = draws
                shock_baseline_mean = float(np.mean(shock_baseline_draws))
                shock_baseline_p90 = float(
                    np.percentile(shock_baseline_draws, 90)
                )
                draws = _apply_point_in_time_shock(
                    shock_baseline_draws,
                    mean_multiplier=point_in_time_shock.mean_multiplier,
                    volatility_multiplier=(
                        point_in_time_shock.volatility_multiplier
                    ),
                )
                shock_scenario_mean = float(np.mean(draws))
                shock_scenario_p90 = float(np.percentile(draws, 90))
                point_in_time_shock_impacts.append(
                    {
                        "shock_index": shock_index,
                        "shock_type": point_in_time_shock.shock_type,
                        "label": point_in_time_shock.label,
                        "observed_at": point_in_time_shock.observed_at,
                        "player_master_id": salary_row.player_master_id,
                        "source_player_key": salary_row.source_player_key,
                        "player_name": salary_row.player_name,
                        "team": salary_row.team,
                        "position": salary_row.position,
                        "mean_multiplier": (
                            point_in_time_shock.mean_multiplier
                        ),
                        "volatility_multiplier": (
                            point_in_time_shock.volatility_multiplier
                        ),
                        "baseline_mean_points": shock_baseline_mean,
                        "scenario_mean_points": shock_scenario_mean,
                        "mean_points_delta": (
                            shock_scenario_mean - shock_baseline_mean
                        ),
                        "baseline_p90_points": shock_baseline_p90,
                        "scenario_p90_points": shock_scenario_p90,
                        "p90_points_delta": (
                            shock_scenario_p90 - shock_baseline_p90
                        ),
                    }
                )

            hit_points = (
                low_hit_points
                if isinstance(low_hit_points, (int, float)) and math.isfinite(float(low_hit_points))
                else self.DEFAULT_LOW_SALARY_HIT_POINTS
            )

            history_games = int(player_history.size)
            if history_games < min_history_games and prior.size == 0:
                continue

            if shock_roles:
                impacted_masters_simulated.add(str(salary_row.player_master_id))
                baseline_mean = float(np.mean(baseline_draws))
                baseline_p90 = float(np.percentile(baseline_draws, 90))
                scenario_mean = float(np.mean(draws))
                scenario_p90 = float(np.percentile(draws, 90))
                shock_role = (
                    "target_and_recipient"
                    if shock_roles == {"target", "recipient"}
                    else next(iter(shock_roles))
                )
                role_shock_impacts.append(
                    {
                        "player_master_id": salary_row.player_master_id,
                        "source_player_key": salary_row.source_player_key,
                        "player_name": salary_row.player_name,
                        "team": salary_row.team,
                        "position": salary_row.position,
                        "shock_role": shock_role,
                        "opportunity_multiplier": opportunity_multiplier,
                        "projection_multiplier": projection_multiplier,
                        "baseline_mean_points": baseline_mean,
                        "scenario_mean_points": scenario_mean,
                        "mean_points_delta": scenario_mean - baseline_mean,
                        "baseline_p90_points": baseline_p90,
                        "scenario_p90_points": scenario_p90,
                        "p90_points_delta": scenario_p90 - baseline_p90,
                    }
                )

            simulated_rows.append(
                {
                    "player_master_id": salary_row.player_master_id,
                    "source_player_key": salary_row.source_player_key,
                    "player_name": salary_row.player_name,
                    "team": salary_row.team,
                    "position": salary_row.position,
                    "salary": salary_row.salary,
                    "history_games": history_games,
                    "mean_points": float(np.mean(draws)),
                    "median_points": float(np.percentile(draws, 50)),
                    "p75_points": float(np.percentile(draws, 75)),
                    "p90_points": float(np.percentile(draws, 90)),
                    "p95_points": float(np.percentile(draws, 95)),
                    "ceiling_prob_20": float(np.mean(draws >= 20.0)),
                    "ceiling_prob_25": float(np.mean(draws >= 25.0)),
                    "low_hit_prob": float(np.mean(draws >= float(hit_points))),
                }
            )

        if not simulated_rows:
            raise ValueError(
                "Simulation produced no rows. Ensure salary slice has mapped player_master_id values with historical stats."
            )

        for master_id in sorted(role_shock_roles):
            if master_id not in impacted_masters_simulated:
                scenario_warnings.append(
                    f"role shock player {master_id} had no simulated outcome"
                )
        for master_id in sorted(point_in_time_shocks_by_master):
            if master_id not in point_in_time_masters_simulated:
                scenario_warnings.append(
                    f"point-in-time shock player {master_id} had no simulated outcome"
                )

        return (
            players_considered,
            simulated_rows,
            player_id_to_masters,
            tracked_player_ids,
            role_shock_impacts,
            point_in_time_shock_impacts,
            residual_adjustment_impacts,
            residual_snapshot_count,
            scenario_warnings,
        )

    def _new_run(self, request: SimulateWeekRequest) -> SimulationRun:
        run = SimulationRun(
            simulation_run_id=str(uuid.uuid4()),
            source_system=request.source_system,
            season=request.season,
            week=request.week,
            slate=request.slate,
            iterations=request.iterations,
            random_seed=request.random_seed,
            parameters_json=request.model_dump(mode="json"),
            players_considered=0,
            players_simulated=0,
            status="running",
            started_at=utcnow_naive(),
        )
        self.session.add(run)
        self.session.commit()
        return run

    def _complete_run(
        self,
        run_id: str,
        status: str,
        players_considered: int,
        players_simulated: int,
        error_message: str | None = None,
    ) -> SimulationRun:
        run = self.session.get(SimulationRun, run_id)
        if run is None:
            raise RuntimeError(f"Simulation run not found: {run_id}")
        run.status = status
        run.players_considered = players_considered
        run.players_simulated = players_simulated
        run.error_message = error_message
        run.completed_at = utcnow_naive()
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)
        return run

    def simulate_week(self, request: SimulateWeekRequest) -> SimulateWeekResponse:
        run = self._new_run(request)
        players_considered = 0
        players_simulated = 0
        top_rows: list[SimulatedPlayerOutcomeResponse] = []
        role_shock_impacts: list[RoleShockImpactResponse] = []
        point_in_time_shock_impacts: list[
            PointInTimeShockImpactResponse
        ] = []
        residual_adjustment_impacts: list[
            ResidualAdjustmentImpactResponse
        ] = []
        residual_snapshot_count = 0
        scenario_warnings: list[str] = []
        try:
            (
                players_considered,
                simulated_calc_rows,
                _player_map,
                _tracked_ids,
                role_shock_calc_rows,
                point_in_time_shock_calc_rows,
                residual_adjustment_calc_rows,
                residual_snapshot_count,
                scenario_warnings,
            ) = self._simulate_salary_slice(
                source_system=request.source_system,
                season=request.season,
                week=request.week,
                slate=request.slate,
                iterations=request.iterations,
                min_history_games=request.min_history_games,
                prior_weight=request.prior_weight,
                noise_scale=request.noise_scale,
                random_seed=request.random_seed,
                use_calibration=True,
                use_residual_learning=request.use_residual_learning,
                role_shocks=request.role_shocks,
                point_in_time_shocks=request.point_in_time_shocks,
            )
            role_shock_impacts = [
                RoleShockImpactResponse(**row)
                for row in role_shock_calc_rows
            ]
            point_in_time_shock_impacts = [
                PointInTimeShockImpactResponse(**row)
                for row in point_in_time_shock_calc_rows
            ]
            residual_adjustment_impacts = [
                ResidualAdjustmentImpactResponse(**row)
                for row in residual_adjustment_calc_rows
            ]

            simulated_rows = [
                SimulatedPlayerOutcome(
                    simulation_run_id=run.simulation_run_id,
                    player_master_id=row["player_master_id"],
                    source_player_key=row["source_player_key"],
                    player_name=row["player_name"],
                    team=row["team"],
                    position=row["position"],
                    salary=row["salary"],
                    history_games=row["history_games"],
                    mean_points=row["mean_points"],
                    median_points=row["median_points"],
                    p75_points=row["p75_points"],
                    p90_points=row["p90_points"],
                    p95_points=row["p95_points"],
                    ceiling_prob_20=row["ceiling_prob_20"],
                    ceiling_prob_25=row["ceiling_prob_25"],
                    created_at=utcnow_naive(),
                )
                for row in simulated_calc_rows
            ]

            self.session.add_all(simulated_rows)
            self.session.commit()

            players_simulated = len(simulated_rows)
            run = self._complete_run(
                run_id=run.simulation_run_id,
                status="completed",
                players_considered=players_considered,
                players_simulated=players_simulated,
            )

            sorted_outcomes = sorted(simulated_rows, key=lambda row: row.p90_points, reverse=True)
            for row in sorted_outcomes[: request.top_n]:
                top_rows.append(
                    SimulatedPlayerOutcomeResponse(
                        player_master_id=row.player_master_id,
                        source_player_key=row.source_player_key,
                        player_name=row.player_name,
                        team=row.team,
                        position=row.position,
                        salary=row.salary,
                        history_games=row.history_games,
                        mean_points=row.mean_points,
                        median_points=row.median_points,
                        p75_points=row.p75_points,
                        p90_points=row.p90_points,
                        p95_points=row.p95_points,
                        ceiling_prob_20=row.ceiling_prob_20,
                        ceiling_prob_25=row.ceiling_prob_25,
                    )
                )

            return SimulateWeekResponse(
                simulation_run_id=run.simulation_run_id,
                source_system=run.source_system,
                season=run.season,
                week=run.week,
                slate=run.slate,
                iterations=run.iterations,
                players_considered=run.players_considered,
                players_simulated=run.players_simulated,
                status=run.status,
                error_message=run.error_message,
                started_at=run.started_at,
                completed_at=run.completed_at,
                top_rows=top_rows,
                role_shock_impacts=role_shock_impacts,
                scenario_as_of=request.scenario_as_of,
                point_in_time_shock_impacts=point_in_time_shock_impacts,
                residual_learning_applied=bool(
                    residual_adjustment_impacts
                ),
                residual_snapshot_count=residual_snapshot_count,
                residual_adjustment_impacts=residual_adjustment_impacts,
                scenario_warnings=scenario_warnings,
            )
        except Exception as exc:  # noqa: BLE001
            self.session.rollback()
            run = self._complete_run(
                run_id=run.simulation_run_id,
                status="failed",
                players_considered=players_considered,
                players_simulated=players_simulated,
                error_message=str(exc),
            )
            return SimulateWeekResponse(
                simulation_run_id=run.simulation_run_id,
                source_system=run.source_system,
                season=run.season,
                week=run.week,
                slate=run.slate,
                iterations=run.iterations,
                players_considered=run.players_considered,
                players_simulated=run.players_simulated,
                status=run.status,
                error_message=run.error_message,
                started_at=run.started_at,
                completed_at=run.completed_at,
                top_rows=[],
                role_shock_impacts=[],
                scenario_as_of=request.scenario_as_of,
                point_in_time_shock_impacts=[],
                residual_learning_applied=False,
                residual_snapshot_count=0,
                residual_adjustment_impacts=[],
                scenario_warnings=scenario_warnings,
            )

    def _backtest_week_internal(
        self,
        request: BacktestWeekRequest,
        *,
        use_calibration: bool,
        persist_calibration: bool,
        include_rows: bool,
    ) -> BacktestWeekResponse:
        (
            players_considered,
            simulated_rows,
            player_id_to_masters,
            tracked_player_ids,
            _role_shock_impacts,
            _point_in_time_shock_impacts,
            _residual_adjustment_impacts,
            _residual_snapshot_count,
            _scenario_warnings,
        ) = self._simulate_salary_slice(
            source_system=request.source_system,
            season=request.season,
            week=request.week,
            slate=request.slate,
            iterations=request.iterations,
            min_history_games=request.min_history_games,
            prior_weight=request.prior_weight,
            noise_scale=request.noise_scale,
            random_seed=request.random_seed,
            use_calibration=use_calibration,
            low_hit_points=self.DEFAULT_LOW_SALARY_HIT_POINTS,
        )

        actual_rows = self.session.execute(
            select(RawNflWeeklyStat).where(
                and_(
                    RawNflWeeklyStat.season == request.season,
                    RawNflWeeklyStat.week == request.week,
                    RawNflWeeklyStat.player_id.in_(tracked_player_ids),
                )
            )
        ).scalars().all()

        actual_points_by_master: dict[str, list[float]] = defaultdict(list)
        for row in actual_rows:
            if not row.player_id:
                continue
            points = calculate_dk_points(row.raw_row_json or {})
            if not math.isfinite(points):
                continue
            for master_id in player_id_to_masters.get(row.player_id, set()):
                actual_points_by_master[master_id].append(points)

        with_actuals: list[BacktestPlayerRowResponse] = []
        for row in simulated_rows:
            master_id = row["player_master_id"]
            if not master_id:
                continue
            actual_values = actual_points_by_master.get(master_id)
            if not actual_values:
                continue
            actual_points = float(max(actual_values))
            predicted_mean = float(row["mean_points"])
            error = predicted_mean - actual_points
            salary = row["salary"]
            salary_value_actual = None
            if isinstance(salary, int) and salary > 0:
                salary_value_actual = actual_points / (salary / 1000.0)
            with_actuals.append(
                BacktestPlayerRowResponse(
                    player_master_id=master_id,
                    source_player_key=row["source_player_key"],
                    player_name=row["player_name"],
                    team=row["team"],
                    position=row["position"],
                    salary=salary,
                    history_games=int(row["history_games"]),
                    predicted_mean_points=predicted_mean,
                    predicted_p75_points=float(row["p75_points"]),
                    predicted_p90_points=float(row["p90_points"]),
                    predicted_p95_points=float(row["p95_points"]),
                    predicted_ceiling_prob_25=float(row["ceiling_prob_25"]),
                    predicted_low_hit_prob=float(row.get("low_hit_prob") or 0.0),
                    actual_points=actual_points,
                    error=error,
                    abs_error=abs(error),
                    salary_value_actual=salary_value_actual,
                )
            )

        if not with_actuals:
            raise ValueError(
                "Backtest failed: no actual rows matched salary slice player mappings for the selected week."
            )

        actual_values = np.asarray([row.actual_points for row in with_actuals], dtype=float)
        prediction_values = np.asarray([row.predicted_mean_points for row in with_actuals], dtype=float)
        errors = prediction_values - actual_values

        mae = float(np.mean(np.abs(errors)))
        rmse = float(np.sqrt(np.mean(np.square(errors))))
        mean_error = float(np.mean(errors))
        correlation: float | None = None
        if len(with_actuals) >= 2 and np.std(prediction_values) > 0 and np.std(actual_values) > 0:
            correlation = float(np.corrcoef(prediction_values, actual_values)[0, 1])

        predicted_ranked = sorted(with_actuals, key=lambda row: row.predicted_p90_points, reverse=True)
        eval_rows = predicted_ranked[: request.evaluation_top_n]
        top_n_hits = sum(1 for row in eval_rows if row.actual_points >= 20.0)

        low_salary_rows = [
            row for row in with_actuals if isinstance(row.salary, int) and row.salary <= request.low_salary_threshold
        ]
        low_salary_eval_n = min(len(low_salary_rows), max(5, request.evaluation_top_n // 3))
        low_salary_selected = sorted(
            low_salary_rows,
            key=lambda row: (row.predicted_p90_points, row.predicted_mean_points),
            reverse=True,
        )[:low_salary_eval_n]
        low_salary_hits = sum(1 for row in low_salary_selected if row.actual_points >= request.low_salary_hit_points)
        low_salary_hit_rate = (low_salary_hits / len(low_salary_selected)) if low_salary_selected else 0.0

        by_position: dict[str, list[BacktestPlayerRowResponse]] = defaultdict(list)
        for row in with_actuals:
            position = normalize_position(row.position) or "UNK"
            by_position[position].append(row)
        position_learning: list[PositionLearningRowResponse] = []
        for position, rows in sorted(by_position.items(), key=lambda item: (-len(item[1]), item[0])):
            pred = float(np.mean([row.predicted_mean_points for row in rows]))
            actual = float(np.mean([row.actual_points for row in rows]))
            mean_err = pred - actual
            position_learning.append(
                PositionLearningRowResponse(
                    position=position,
                    players=len(rows),
                    mean_prediction=pred,
                    mean_actual=actual,
                    mean_error=mean_err,
                    adjustment_multiplier=(actual / pred) if pred > 0 else 1.0,
                )
            )

        salary_bucket_edges = [
            ("<=4k", 0, 4000),
            ("4k-5.5k", 4001, 5500),
            ("5.5k-7k", 5501, 7000),
            (">7k", 7001, 100000),
        ]
        salary_bucket_learning: list[SalaryBucketLearningRowResponse] = []
        for label, low, high in salary_bucket_edges:
            bucket_rows = [
                row
                for row in with_actuals
                if isinstance(row.salary, int) and row.salary >= low and row.salary <= high
            ]
            if not bucket_rows:
                continue
            pred = float(np.mean([row.predicted_mean_points for row in bucket_rows]))
            actual = float(np.mean([row.actual_points for row in bucket_rows]))
            salary_bucket_learning.append(
                SalaryBucketLearningRowResponse(
                    bucket=label,
                    players=len(bucket_rows),
                    mean_prediction=pred,
                    mean_actual=actual,
                    mean_error=pred - actual,
                )
            )

        learning_notes: list[str] = []
        learning_notes.append(
            f"Top {request.evaluation_top_n} predicted players hit 20+ DK points {top_n_hits} times."
        )
        learning_notes.append(
            f"Low-salary (<= {request.low_salary_threshold}) hit rate at {request.low_salary_hit_points}+ DK points: "
            f"{low_salary_hits}/{len(low_salary_selected)} ({low_salary_hit_rate:.1%})."
        )
        if position_learning:
            largest_bias = max(position_learning, key=lambda row: abs(row.mean_error))
            direction = "overpredicting" if largest_bias.mean_error > 0 else "underpredicting"
            learning_notes.append(
                f"Largest position bias: {largest_bias.position} ({direction} by {abs(largest_bias.mean_error):.2f} points on average)."
            )
        if correlation is not None:
            learning_notes.append(f"Prediction-to-actual correlation this slate: {correlation:.3f}.")

        if persist_calibration:
            try:
                position_saved, salary_saved, low_salary_saved = self._persist_calibration_factors(
                    source_system=request.source_system,
                    season=request.season,
                    week=request.week,
                    slate=request.slate,
                    position_learning=position_learning,
                    salary_bucket_learning=salary_bucket_learning,
                    with_actuals=with_actuals,
                    low_salary_threshold=self.DEFAULT_LOW_SALARY_THRESHOLD,
                    low_salary_hit_points=self.DEFAULT_LOW_SALARY_HIT_POINTS,
                )
                learning_notes.append(
                    "Saved calibration factors: "
                    f"position={position_saved}, salary_bucket={salary_saved}, low_salary_group={low_salary_saved}."
                )
            except Exception:  # noqa: BLE001
                self.session.rollback()
                learning_notes.append("Calibration factor persistence failed; simulation used existing factors only.")

        rows = sorted(with_actuals, key=lambda row: row.predicted_p90_points, reverse=True)
        return BacktestWeekResponse(
            source_system=request.source_system,
            season=request.season,
            week=request.week,
            slate=request.slate,
            iterations=request.iterations,
            players_considered=players_considered,
            players_simulated=len(simulated_rows),
            players_with_actuals=len(with_actuals),
            mae=mae,
            rmse=rmse,
            mean_error=mean_error,
            correlation=correlation,
            evaluation_top_n=request.evaluation_top_n,
            top_n_hits=top_n_hits,
            low_salary_threshold=request.low_salary_threshold,
            low_salary_candidates=len(low_salary_selected),
            low_salary_hits=low_salary_hits,
            low_salary_hit_rate=low_salary_hit_rate,
            learning_notes=learning_notes,
            position_learning=position_learning,
            salary_bucket_learning=salary_bucket_learning,
            rows=(rows[:200] if include_rows else []),
        )

    def backtest_week(self, request: BacktestWeekRequest) -> BacktestWeekResponse:
        return self._backtest_week_internal(
            request,
            use_calibration=True,
            persist_calibration=True,
            include_rows=True,
        )

    def backtest_week_ab(self, request: BacktestWeekRequest) -> BacktestWeekABResponse:
        baseline = self._backtest_week_internal(
            request,
            use_calibration=False,
            persist_calibration=False,
            include_rows=False,
        )
        calibrated = self._backtest_week_internal(
            request,
            use_calibration=True,
            persist_calibration=False,
            include_rows=False,
        )

        top_n_baseline = baseline.top_n_hits / baseline.evaluation_top_n if baseline.evaluation_top_n > 0 else 0.0
        top_n_calibrated = (
            calibrated.top_n_hits / calibrated.evaluation_top_n if calibrated.evaluation_top_n > 0 else 0.0
        )

        return BacktestWeekABResponse(
            source_system=request.source_system,
            season=request.season,
            week=request.week,
            slate=request.slate,
            baseline=baseline,
            calibrated=calibrated,
            mae_lift_pct=_lift_pct(baseline.mae, calibrated.mae, lower_is_better=True) or 0.0,
            rmse_lift_pct=_lift_pct(baseline.rmse, calibrated.rmse, lower_is_better=True) or 0.0,
            top_n_hit_rate_baseline=top_n_baseline,
            top_n_hit_rate_calibrated=top_n_calibrated,
            top_n_hit_rate_lift_pct=_lift_pct(top_n_baseline, top_n_calibrated, lower_is_better=False) or 0.0,
            low_salary_hit_rate_baseline=baseline.low_salary_hit_rate,
            low_salary_hit_rate_calibrated=calibrated.low_salary_hit_rate,
            low_salary_hit_rate_lift_pct=(
                _lift_pct(
                    baseline.low_salary_hit_rate,
                    calibrated.low_salary_hit_rate,
                    lower_is_better=False,
                )
                or 0.0
            ),
        )

    def backtest_range_ab(self, request: BacktestRangeABRequest) -> BacktestRangeABResponse:
        season_start = min(request.season_start, request.season_end)
        season_end = max(request.season_start, request.season_end)

        filters = [
            CuratedSalary.source_system == request.source_system,
            CuratedSalary.season >= season_start,
            CuratedSalary.season <= season_end,
        ]
        if request.slate:
            filters.append(CuratedSalary.slate == request.slate)

        if request.reset_existing_calibration:
            delete_filters = [
                SimulationCalibrationFactor.source_system == request.source_system,
                SimulationCalibrationFactor.calibrated_season >= season_start,
                SimulationCalibrationFactor.calibrated_season <= season_end,
            ]
            if request.slate:
                delete_filters.append(SimulationCalibrationFactor.slate == request.slate)
            for row in self.session.execute(
                select(SimulationCalibrationFactor).where(and_(*delete_filters))
            ).scalars():
                self.session.delete(row)
            self.session.commit()

        slices = self.session.execute(
            select(
                CuratedSalary.season,
                CuratedSalary.week,
                CuratedSalary.slate,
            )
            .where(and_(*filters))
            .group_by(CuratedSalary.season, CuratedSalary.week, CuratedSalary.slate)
            .order_by(CuratedSalary.season, CuratedSalary.week, CuratedSalary.slate)
        ).all()
        if not slices:
            raise ValueError(
                f"No curated salary slices found for {request.source_system} seasons {season_start}-{season_end}."
            )

        rows: list[BacktestRangeSliceABRowResponse] = []

        mae_base_weighted = 0.0
        mae_cal_weighted = 0.0
        rmse_base_weighted = 0.0
        rmse_cal_weighted = 0.0
        corr_weight_base = 0
        top_hits_base = 0
        top_hits_cal = 0
        top_n_total = 0
        low_hits_base = 0
        low_hits_cal = 0
        low_candidates_total = 0
        players_total = 0
        slates_evaluated = 0

        for season, week, slate in slices:
            week_request = BacktestWeekRequest(
                source_system=request.source_system,
                season=int(season),
                week=int(week),
                slate=str(slate),
                iterations=request.iterations,
                min_history_games=request.min_history_games,
                prior_weight=request.prior_weight,
                noise_scale=request.noise_scale,
                random_seed=request.random_seed,
                evaluation_top_n=request.evaluation_top_n,
                low_salary_threshold=request.low_salary_threshold,
                low_salary_hit_points=request.low_salary_hit_points,
            )
            try:
                baseline = self._backtest_week_internal(
                    week_request,
                    use_calibration=False,
                    persist_calibration=False,
                    include_rows=False,
                )
                calibrated = self._backtest_week_internal(
                    week_request,
                    use_calibration=True,
                    persist_calibration=request.persist_calibration,
                    include_rows=False,
                )
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    BacktestRangeSliceABRowResponse(
                        season=int(season),
                        week=int(week),
                        slate=str(slate),
                        error_message=str(exc),
                    )
                )
                continue

            slates_evaluated += 1
            players = baseline.players_with_actuals
            players_total += players
            mae_base_weighted += baseline.mae * players
            mae_cal_weighted += calibrated.mae * players
            rmse_base_weighted += baseline.rmse * players
            rmse_cal_weighted += calibrated.rmse * players
            corr_weight_base += players

            top_hits_base += baseline.top_n_hits
            top_hits_cal += calibrated.top_n_hits
            top_n_total += max(0, baseline.evaluation_top_n)

            low_hits_base += baseline.low_salary_hits
            low_hits_cal += calibrated.low_salary_hits
            low_candidates_total += baseline.low_salary_candidates

            top_rate_base = baseline.top_n_hits / baseline.evaluation_top_n if baseline.evaluation_top_n > 0 else 0.0
            top_rate_cal = (
                calibrated.top_n_hits / calibrated.evaluation_top_n if calibrated.evaluation_top_n > 0 else 0.0
            )
            rows.append(
                BacktestRangeSliceABRowResponse(
                    season=int(season),
                    week=int(week),
                    slate=str(slate),
                    players_with_actuals=players,
                    baseline_mae=baseline.mae,
                    calibrated_mae=calibrated.mae,
                    baseline_rmse=baseline.rmse,
                    calibrated_rmse=calibrated.rmse,
                    baseline_top_n_hit_rate=top_rate_base,
                    calibrated_top_n_hit_rate=top_rate_cal,
                    baseline_low_salary_hit_rate=baseline.low_salary_hit_rate,
                    calibrated_low_salary_hit_rate=calibrated.low_salary_hit_rate,
                    mae_lift_pct=_lift_pct(baseline.mae, calibrated.mae, lower_is_better=True),
                    rmse_lift_pct=_lift_pct(baseline.rmse, calibrated.rmse, lower_is_better=True),
                    top_n_hit_rate_lift_pct=_lift_pct(top_rate_base, top_rate_cal, lower_is_better=False),
                    low_salary_hit_rate_lift_pct=_lift_pct(
                        baseline.low_salary_hit_rate,
                        calibrated.low_salary_hit_rate,
                        lower_is_better=False,
                    ),
                )
            )

        baseline_mae = (mae_base_weighted / corr_weight_base) if corr_weight_base > 0 else None
        calibrated_mae = (mae_cal_weighted / corr_weight_base) if corr_weight_base > 0 else None
        baseline_rmse = (rmse_base_weighted / corr_weight_base) if corr_weight_base > 0 else None
        calibrated_rmse = (rmse_cal_weighted / corr_weight_base) if corr_weight_base > 0 else None
        baseline_top_n_hit_rate = (top_hits_base / top_n_total) if top_n_total > 0 else None
        calibrated_top_n_hit_rate = (top_hits_cal / top_n_total) if top_n_total > 0 else None
        baseline_low_salary_hit_rate = (
            (low_hits_base / low_candidates_total) if low_candidates_total > 0 else None
        )
        calibrated_low_salary_hit_rate = (
            (low_hits_cal / low_candidates_total) if low_candidates_total > 0 else None
        )

        return BacktestRangeABResponse(
            source_system=request.source_system,
            season_start=season_start,
            season_end=season_end,
            slate=request.slate,
            total_slates=len(slices),
            slates_evaluated=slates_evaluated,
            slates_failed=len(slices) - slates_evaluated,
            players_with_actuals_total=players_total,
            baseline_mae=baseline_mae,
            calibrated_mae=calibrated_mae,
            mae_lift_pct=(
                _lift_pct(baseline_mae, calibrated_mae, lower_is_better=True)
                if baseline_mae is not None and calibrated_mae is not None
                else None
            ),
            baseline_rmse=baseline_rmse,
            calibrated_rmse=calibrated_rmse,
            rmse_lift_pct=(
                _lift_pct(baseline_rmse, calibrated_rmse, lower_is_better=True)
                if baseline_rmse is not None and calibrated_rmse is not None
                else None
            ),
            baseline_top_n_hit_rate=baseline_top_n_hit_rate,
            calibrated_top_n_hit_rate=calibrated_top_n_hit_rate,
            top_n_hit_rate_lift_pct=(
                _lift_pct(baseline_top_n_hit_rate, calibrated_top_n_hit_rate, lower_is_better=False)
                if baseline_top_n_hit_rate is not None and calibrated_top_n_hit_rate is not None
                else None
            ),
            baseline_low_salary_hit_rate=baseline_low_salary_hit_rate,
            calibrated_low_salary_hit_rate=calibrated_low_salary_hit_rate,
            low_salary_hit_rate_lift_pct=(
                _lift_pct(baseline_low_salary_hit_rate, calibrated_low_salary_hit_rate, lower_is_better=False)
                if baseline_low_salary_hit_rate is not None and calibrated_low_salary_hit_rate is not None
                else None
            ),
            rows=rows,
        )
