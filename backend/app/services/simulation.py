from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import numpy as np
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from ..models import (
    CuratedSalary,
    PlayerAlias,
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
    PositionLearningRowResponse,
    SalaryBucketLearningRowResponse,
    SimulatedPlayerOutcomeResponse,
    SimulateWeekRequest,
    SimulateWeekResponse,
)
from .matching import normalize_position


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


class SimulationService:
    DEFAULT_LOW_SALARY_THRESHOLD = 4500
    DEFAULT_LOW_SALARY_HIT_POINTS = 15.0

    def __init__(self, session: Session) -> None:
        self.session = session

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
        low_hit_points: float | None = None,
    ) -> tuple[int, list[dict[str, Any]], dict[str, set[str]], list[str]]:
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

        rng = np.random.default_rng(random_seed)
        simulated_rows: list[dict[str, Any]] = []

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

            hit_points = (
                low_hit_points
                if isinstance(low_hit_points, (int, float)) and math.isfinite(float(low_hit_points))
                else self.DEFAULT_LOW_SALARY_HIT_POINTS
            )

            history_games = int(player_history.size)
            if history_games < min_history_games and prior.size == 0:
                continue

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

        return players_considered, simulated_rows, player_id_to_masters, tracked_player_ids

    def _new_run(self, request: SimulateWeekRequest) -> SimulationRun:
        run = SimulationRun(
            simulation_run_id=str(uuid.uuid4()),
            source_system=request.source_system,
            season=request.season,
            week=request.week,
            slate=request.slate,
            iterations=request.iterations,
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
        try:
            players_considered, simulated_calc_rows, _player_map, _tracked_ids = self._simulate_salary_slice(
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
            )

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
            )

    def _backtest_week_internal(
        self,
        request: BacktestWeekRequest,
        *,
        use_calibration: bool,
        persist_calibration: bool,
        include_rows: bool,
    ) -> BacktestWeekResponse:
        players_considered, simulated_rows, player_id_to_masters, tracked_player_ids = self._simulate_salary_slice(
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
