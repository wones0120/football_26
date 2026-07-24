"""Deterministic slate simulation and optimal-lineup probability contracts."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from Database.config import get_connection_string

from .target_schema import validate_target_schema


SIMULATION_MODEL_ID = "independent_quantile_lineup_v1"
VALID_CLASSIC_POSITIONS = {"QB", "RB", "WR", "TE", "DST"}
MIN_CLASSIC_SALARY = 2_000


@dataclass(frozen=True)
class SimulationResult:
    simulation_run_id: str
    simulation_model_id: str
    season: int
    week: int
    slate: str
    contest_format: str
    projection_run_id: str
    ownership_run_id: str | None
    num_simulations: int
    successful_simulations: int
    seed: int
    salary_cap: int
    status: str
    message: str
    data_cutoff_at: datetime | None
    created_at: datetime
    rows: list[dict[str, Any]]


def _normalize_position(value: Any) -> str:
    position = str(value or "").upper().split("/")[0].strip()
    return "DST" if position in {"D", "DEF"} else position


def _monotone_quantiles(row: pd.Series) -> np.ndarray:
    """Return a non-negative, monotone P10/P25/P50/P75/P90 vector."""
    mean = max(0.0, float(row.get("projection_mean") or 0.0))
    values = []
    fallback = mean
    for column in ("projection_p10", "projection_p25", "projection_p50", "projection_p75", "projection_p90"):
        raw = row.get(column)
        value = fallback if raw is None or pd.isna(raw) else max(0.0, float(raw))
        values.append(value)
        fallback = value
    return np.maximum.accumulate(np.asarray(values, dtype=float))


def sample_independent_outcomes(pool: pd.DataFrame, *, num_simulations: int, seed: int) -> np.ndarray:
    """Sample each player's calibrated marginal distribution with a fixed seed.

    DT-502 intentionally samples players independently. Shared game states and
    player correlations belong to DT-503.
    """
    rng = np.random.default_rng(seed)
    uniforms = rng.random((num_simulations, len(pool)))
    outcomes = np.zeros_like(uniforms)
    probabilities = np.asarray([0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 1.0])
    for index, (_, row) in enumerate(pool.iterrows()):
        p10, p25, p50, p75, p90 = _monotone_quantiles(row)
        lower = max(0.0, p10 - (p25 - p10) * (2.0 / 3.0))
        upper = max(p90, p90 + (p90 - p75) * (2.0 / 3.0))
        values = np.asarray([lower, p10, p25, p50, p75, p90, upper])
        outcomes[:, index] = np.interp(uniforms[:, index], probabilities, values)
    return outcomes


def _classic_constraints(pool: pd.DataFrame, salary_cap: int) -> LinearConstraint:
    positions = pool["position"].astype(str).to_numpy()
    rows = [
        np.ones(len(pool), dtype=float),
        pool["salary"].to_numpy(dtype=float),
        (positions == "QB").astype(float),
        (positions == "DST").astype(float),
        (positions == "RB").astype(float),
        (positions == "WR").astype(float),
        (positions == "TE").astype(float),
    ]
    lower = np.asarray([9, 0, 1, 1, 2, 3, 1], dtype=float)
    upper = np.asarray([9, salary_cap, 1, 1, 3, 4, 2], dtype=float)
    return LinearConstraint(np.vstack(rows), lower, upper)


def simulate_optimal_lineups(
    pool: pd.DataFrame,
    *,
    num_simulations: int,
    seed: int,
    salary_cap: int = 50_000,
) -> tuple[np.ndarray, int]:
    """Return per-player optimal lineup counts for classic DraftKings rosters."""
    if pool.empty:
        raise ValueError("Slate simulation requires at least one eligible player.")
    required_counts = {position: int((pool["position"] == position).sum()) for position in VALID_CLASSIC_POSITIONS}
    minimums = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}
    missing = [position for position, minimum in minimums.items() if required_counts[position] < minimum]
    if missing:
        raise ValueError("Slate simulation cannot form a legal classic lineup; missing " + ", ".join(missing))

    outcomes = sample_independent_outcomes(pool, num_simulations=num_simulations, seed=seed)
    constraints = _classic_constraints(pool, salary_cap)
    bounds = Bounds(np.zeros(len(pool)), np.ones(len(pool)))
    integrality = np.ones(len(pool), dtype=int)
    counts = np.zeros(len(pool), dtype=int)
    successful = 0
    # A stable, negligible tie-breaker makes exact-score ties deterministic.
    tie_breaker = np.arange(len(pool), 0, -1, dtype=float) * 1e-9
    for outcome in outcomes:
        result = milp(
            c=-(outcome + tie_breaker),
            integrality=integrality,
            bounds=bounds,
            constraints=constraints,
            options={"presolve": True},
        )
        if not result.success or result.x is None:
            continue
        selected = np.flatnonzero(result.x >= 0.5)
        if len(selected) != 9:
            continue
        counts[selected] += 1
        successful += 1
    return counts, successful


def build_simulation_rows(
    pool: pd.DataFrame,
    counts: np.ndarray,
    *,
    successful_simulations: int,
) -> list[dict[str, Any]]:
    """Build player results with probability and ownership in percentage units."""
    rows: list[dict[str, Any]] = []
    denominator = max(1, successful_simulations)
    for sampling_index, (count, (_, player)) in enumerate(zip(counts, pool.iterrows())):
        probability = round(float(count) / denominator * 100.0, 6)
        ownership_raw = player.get("field_ownership")
        ownership = None if ownership_raw is None or pd.isna(ownership_raw) else float(ownership_raw)
        leverage = None if ownership is None else round(probability - ownership, 6)
        rows.append(
            {
                "player_id": str(player["player_id"]),
                "player_display_name": str(player.get("player_display_name") or player["player_id"]),
                "position": str(player["position"]),
                "salary": int(player["salary"]),
                "projection_mean": float(player["projection_mean"]),
                "projection_p10": float(player["projection_p10"]),
                "projection_p25": float(player["projection_p25"]),
                "projection_p50": float(player["projection_p50"]),
                "projection_p75": float(player["projection_p75"]),
                "projection_p90": float(player["projection_p90"]),
                "team_id": str(player.get("team_id") or ""),
                "opponent_team_id": str(player.get("opponent_team_id") or ""),
                "game_id": str(player.get("game_id") or ""),
                "sampling_index": sampling_index,
                "optimal_lineup_count": int(count),
                "optimal_lineup_probability": probability,
                "field_ownership": ownership,
                "leverage_score": leverage,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -row["optimal_lineup_probability"],
            -row["projection_mean"],
            row["player_display_name"],
        ),
    )


class SimulationService:
    """Run and persist one immutable independent-marginal slate simulation."""

    def __init__(self, connection_string: str | None = None, engine: Engine | None = None) -> None:
        self.connection_string = connection_string or (
            str(engine.url) if engine is not None else get_connection_string()
        )
        self.engine = engine or create_engine(self.connection_string)

    def _ensure_schema(self) -> None:
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=("simulation_run", "player_simulation"),
        )

    def _resolve_projection_run(
        self,
        connection: Any,
        *,
        season: int,
        week: int,
        slate: str,
        projection_run_id: str | None,
    ) -> str:
        params = {"season": season, "week": week, "slate": slate}
        if projection_run_id:
            row = connection.execute(
                text(
                    """
                    SELECT projection_run_id
                    FROM target.player_projection
                    WHERE season = :season AND week = :week
                      AND projection_run_id = :projection_run_id
                      AND (slate_id IS NULL OR UPPER(slate_id) IN (UPPER(:slate), 'DEFAULT'))
                    LIMIT 1
                    """
                ),
                {**params, "projection_run_id": projection_run_id},
            ).mappings().first()
            if not row:
                raise ValueError(f"Projection run not found for this slate: {projection_run_id}")
            return str(row["projection_run_id"])

        inspector = inspect(connection)
        if inspector.has_table("active_projection_run", schema="target"):
            row = connection.execute(
                text(
                    """
                    SELECT projection_run_id
                    FROM target.active_projection_run
                    WHERE season = :season AND week = :week
                      AND (UPPER(slate_id) = UPPER(:slate) OR slate_id = 'DEFAULT')
                    ORDER BY CASE WHEN UPPER(slate_id) = UPPER(:slate) THEN 0 ELSE 1 END,
                             selected_at DESC
                    LIMIT 1
                    """
                ),
                params,
            ).mappings().first()
            if row:
                return str(row["projection_run_id"])
        row = connection.execute(
            text(
                """
                SELECT projection_run_id
                FROM target.player_projection
                WHERE season = :season AND week = :week
                  AND (slate_id IS NULL OR UPPER(slate_id) IN (UPPER(:slate), 'DEFAULT'))
                ORDER BY created_at DESC, projection_run_id
                LIMIT 1
                """
            ),
            params,
        ).mappings().first()
        if not row:
            raise ValueError("Slate simulation requires a completed projection run.")
        return str(row["projection_run_id"])

    def _load_pool(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        projection_run_id: str | None,
        ownership_run_id: str | None,
    ) -> tuple[pd.DataFrame, str, str | None, datetime | None]:
        inspector = inspect(self.engine)
        required = (
            inspector.has_table("player_projection", schema="target")
            and inspector.has_table("snapshot_salary", schema="target")
        )
        if not required:
            raise ValueError("Slate simulation requires target player_projection and snapshot_salary tables.")

        with self.engine.begin() as connection:
            selected_projection_run_id = self._resolve_projection_run(
                connection,
                season=season,
                week=week,
                slate=slate,
                projection_run_id=projection_run_id,
            )
            has_player = inspector.has_table("dim_player", schema="target")
            name_expression = "COALESCE(NULLIF(d.full_name, ''), p.player_id)" if has_player else "p.player_id"
            player_join = "LEFT JOIN target.dim_player d ON d.player_id = p.player_id" if has_player else ""
            has_injuries = inspector.has_table("snapshot_injury_status", schema="target")
            injury_cte = ""
            injury_join = ""
            injury_filter = ""
            if has_injuries:
                injury_cte = """,
                    latest_injury AS (
                        SELECT DISTINCT ON (player_id)
                            player_id, injury_status
                        FROM target.snapshot_injury_status
                        WHERE season = :season AND week = :week
                          AND (slate IS NULL OR UPPER(slate) = UPPER(:slate))
                        ORDER BY player_id, as_of DESC
                    )
                """
                injury_join = "LEFT JOIN latest_injury i ON i.player_id = p.player_id"
                injury_filter = (
                    "WHERE COALESCE(i.injury_status, '') !~* "
                    "'(OUT|IR|PUP|NFI|RESERVE)'"
                )
            pool = pd.read_sql(
                text(
                    f"""
                    WITH latest_salary AS (
                        SELECT DISTINCT ON (player_id)
                            player_id, salary, roster_position, team_id,
                            opponent_team_id, game_id
                        FROM target.snapshot_salary
                        WHERE season = :season AND week = :week
                          AND UPPER(COALESCE(slate, slate_id)) = UPPER(:slate)
                        ORDER BY player_id, as_of DESC
                    ),
                    latest_projection AS (
                        SELECT DISTINCT ON (player_id) *
                        FROM target.player_projection
                        WHERE season = :season AND week = :week
                          AND projection_run_id = :projection_run_id
                          AND (slate_id IS NULL OR UPPER(slate_id) IN (UPPER(:slate), 'DEFAULT'))
                        ORDER BY player_id, created_at DESC
                    )
                    {injury_cte}
                    SELECT
                        p.player_id,
                        {name_expression} AS player_display_name,
                        s.roster_position AS position,
                        s.salary,
                        s.team_id,
                        s.opponent_team_id,
                        s.game_id,
                        p.mean AS projection_mean,
                        p.p10 AS projection_p10,
                        p.p25 AS projection_p25,
                        p.median AS projection_p50,
                        p.p75 AS projection_p75,
                        p.p90 AS projection_p90,
                        p.data_cutoff_at
                    FROM latest_salary s
                    JOIN latest_projection p ON p.player_id = s.player_id
                    {player_join}
                    {injury_join}
                    {injury_filter}
                    """
                ),
                connection,
                params={
                    "season": season,
                    "week": week,
                    "slate": slate,
                    "projection_run_id": selected_projection_run_id,
                },
            )
            selected_ownership_run_id, ownership = self._load_ownership(
                connection,
                season=season,
                week=week,
                slate=slate,
                ownership_run_id=ownership_run_id,
            )

        if pool.empty:
            raise ValueError("No salary rows matched the selected projection run for this slate.")
        pool["player_id"] = pool["player_id"].astype(str)
        pool["position"] = pool["position"].map(_normalize_position)
        pool["salary"] = pd.to_numeric(pool["salary"], errors="coerce")
        for column in (
            "projection_mean",
            "projection_p10",
            "projection_p25",
            "projection_p50",
            "projection_p75",
            "projection_p90",
        ):
            pool[column] = pd.to_numeric(pool[column], errors="coerce")
        pool = pool[
            pool["position"].isin(VALID_CLASSIC_POSITIONS)
            & pool["salary"].ge(MIN_CLASSIC_SALARY)
            & pool["projection_mean"].gt(0)
        ].drop_duplicates("player_id").copy()
        if not ownership.empty:
            ownership = ownership.copy()
            ownership["player_id"] = ownership["player_id"].astype(str)
            pool = pool.merge(ownership, on="player_id", how="left")
        else:
            pool["field_ownership"] = np.nan
        cutoff_values = pd.to_datetime(pool["data_cutoff_at"], errors="coerce", utc=True).dropna()
        data_cutoff_at = cutoff_values.max().to_pydatetime() if not cutoff_values.empty else None
        return pool.reset_index(drop=True), selected_projection_run_id, selected_ownership_run_id, data_cutoff_at

    def _load_ownership(
        self,
        connection: Any,
        *,
        season: int,
        week: int,
        slate: str,
        ownership_run_id: str | None,
    ) -> tuple[str | None, pd.DataFrame]:
        inspector = inspect(connection)
        if inspector.has_table("ownership_projection", schema="target"):
            conditions = ["season = :season", "week = :week", "UPPER(slate_id) = UPPER(:slate)"]
            params: dict[str, Any] = {"season": season, "week": week, "slate": slate}
            if ownership_run_id:
                conditions.append("ownership_run_id = :ownership_run_id")
                params["ownership_run_id"] = ownership_run_id
            run = connection.execute(
                text(
                    f"""
                    SELECT ownership_run_id
                    FROM target.ownership_projection
                    WHERE {' AND '.join(conditions)}
                    GROUP BY ownership_run_id
                    ORDER BY MAX(created_at) DESC, ownership_run_id
                    LIMIT 1
                    """
                ),
                params,
            ).mappings().first()
            if run:
                selected = str(run["ownership_run_id"])
                frame = pd.read_sql(
                    text(
                        """
                        SELECT DISTINCT ON (player_id)
                            player_id, projected_ownership AS field_ownership
                        FROM target.ownership_projection
                        WHERE ownership_run_id = :ownership_run_id
                        ORDER BY player_id, created_at DESC
                        """
                    ),
                    connection,
                    params={"ownership_run_id": selected},
                )
                return selected, frame
        if ownership_run_id:
            raise ValueError(f"Ownership run not found for this slate: {ownership_run_id}")
        if inspector.has_table("dk_ownership"):
            frame = pd.read_sql(
                text(
                    """
                    SELECT DISTINCT ON (player_id)
                        player_id, projected_ownership AS field_ownership,
                        ownership_run_id
                    FROM dk_ownership
                    WHERE season = :season AND week = :week
                      AND UPPER(slate) = UPPER(:slate)
                    ORDER BY player_id, updated_at DESC NULLS LAST
                    """
                ),
                connection,
                params={"season": season, "week": week, "slate": slate},
            )
            run_ids = frame.get("ownership_run_id", pd.Series(dtype=object)).dropna().astype(str).unique()
            selected = str(run_ids[0]) if len(run_ids) == 1 else None
            return selected, frame[["player_id", "field_ownership"]] if not frame.empty else frame
        return None, pd.DataFrame(columns=["player_id", "field_ownership"])

    def _persist(self, result: SimulationResult, *, salary_cap: int) -> None:
        self._ensure_schema()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO target.simulation_run
                        (simulation_run_id, simulation_model_id, projection_run_id,
                         ownership_run_id, season, week, slate_id, contest_format,
                         num_simulations, successful_simulations, seed, salary_cap,
                         roster_size, params_json, data_cutoff_at, created_at, status, message)
                    VALUES
                        (:simulation_run_id, :simulation_model_id, :projection_run_id,
                         :ownership_run_id, :season, :week, :slate_id, :contest_format,
                         :num_simulations, :successful_simulations, :seed, :salary_cap,
                         9, CAST(:params_json AS JSONB), :data_cutoff_at, :created_at,
                         :status, :message)
                    """
                ),
                {
                    "simulation_run_id": result.simulation_run_id,
                    "simulation_model_id": result.simulation_model_id,
                    "projection_run_id": result.projection_run_id,
                    "ownership_run_id": result.ownership_run_id,
                    "season": result.season,
                    "week": result.week,
                    "slate_id": result.slate,
                    "contest_format": result.contest_format,
                    "num_simulations": result.num_simulations,
                    "successful_simulations": result.successful_simulations,
                    "seed": result.seed,
                    "salary_cap": salary_cap,
                    "params_json": json.dumps(
                        {
                            "marginal_sampling": "piecewise_linear_calibrated_quantiles",
                            "correlation": "independent_dt_502",
                            "roster_contract": "draftkings_classic_v1",
                        },
                        sort_keys=True,
                    ),
                    "data_cutoff_at": result.data_cutoff_at,
                    "created_at": result.created_at,
                    "status": result.status,
                    "message": result.message,
                },
            )
            payload = []
            for row in result.rows:
                payload.append(
                    {
                        "simulation_run_id": result.simulation_run_id,
                        **row,
                        "result_json": json.dumps(
                            {
                                "probability_unit": "percent",
                                "leverage_unit": "percentage_points",
                                "projection_distribution": {
                                    "mean": row["projection_mean"],
                                    "p10": row["projection_p10"],
                                    "p25": row["projection_p25"],
                                    "p50": row["projection_p50"],
                                    "p75": row["projection_p75"],
                                    "p90": row["projection_p90"],
                                },
                                "team_id": row["team_id"],
                                "opponent_team_id": row["opponent_team_id"],
                                "game_id": row["game_id"],
                                "sampling_index": row["sampling_index"],
                            },
                            sort_keys=True,
                        ),
                    }
                )
            if payload:
                connection.execute(
                    text(
                        """
                        INSERT INTO target.player_simulation
                            (simulation_run_id, player_id, player_display_name, position,
                             salary, projection_mean, optimal_lineup_count,
                             optimal_lineup_probability, field_ownership, leverage_score,
                             result_json)
                        VALUES
                            (:simulation_run_id, :player_id, :player_display_name, :position,
                             :salary, :projection_mean, :optimal_lineup_count,
                             :optimal_lineup_probability, :field_ownership, :leverage_score,
                             CAST(:result_json AS JSONB))
                        """
                    ),
                    payload,
                )

    def run(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        contest_format: str = "classic",
        num_simulations: int = 1_000,
        seed: int = 502,
        salary_cap: int = 50_000,
        projection_run_id: str | None = None,
        ownership_run_id: str | None = None,
    ) -> SimulationResult:
        if contest_format != "classic":
            raise ValueError("DT-502 supports classic slates; showdown simulation is tracked by DT-603.")
        if not 1 <= int(num_simulations) <= 20_000:
            raise ValueError("num_simulations must be between 1 and 20000.")
        if not slate.strip():
            raise ValueError("slate is required.")
        pool, selected_projection_run_id, selected_ownership_run_id, cutoff = self._load_pool(
            season=season,
            week=week,
            slate=slate,
            projection_run_id=projection_run_id,
            ownership_run_id=ownership_run_id,
        )
        counts, successful = simulate_optimal_lineups(
            pool,
            num_simulations=int(num_simulations),
            seed=int(seed),
            salary_cap=int(salary_cap),
        )
        if successful == 0:
            raise RuntimeError("Slate simulation did not produce a legal lineup in any iteration.")
        rows = build_simulation_rows(pool, counts, successful_simulations=successful)
        created_at = datetime.now(timezone.utc)
        result = SimulationResult(
            simulation_run_id=str(uuid.uuid4()),
            simulation_model_id=SIMULATION_MODEL_ID,
            season=season,
            week=week,
            slate=slate,
            contest_format=contest_format,
            projection_run_id=selected_projection_run_id,
            ownership_run_id=selected_ownership_run_id,
            num_simulations=int(num_simulations),
            successful_simulations=successful,
            seed=int(seed),
            salary_cap=int(salary_cap),
            status="completed",
            message=(
                f"Completed {successful} deterministic classic slate simulations "
                f"for {len(rows)} players"
            ),
            data_cutoff_at=cutoff,
            created_at=created_at,
            rows=rows,
        )
        self._persist(result, salary_cap=int(salary_cap))
        return result

    def fetch_latest(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        contest_format: str = "classic",
        projection_run_id: str | None = None,
    ) -> SimulationResult | None:
        inspector = inspect(self.engine)
        if not (
            inspector.has_table("simulation_run", schema="target")
            and inspector.has_table("player_simulation", schema="target")
        ):
            return None
        conditions = [
            "season = :season",
            "week = :week",
            "UPPER(slate_id) = UPPER(:slate)",
            "contest_format = :contest_format",
            "status = 'completed'",
        ]
        params: dict[str, Any] = {
            "season": season,
            "week": week,
            "slate": slate,
            "contest_format": contest_format,
        }
        if projection_run_id:
            conditions.append("projection_run_id = :projection_run_id")
            params["projection_run_id"] = projection_run_id
        with self.engine.begin() as connection:
            run = connection.execute(
                text(
                    f"""
                    SELECT * FROM target.simulation_run
                    WHERE {' AND '.join(conditions)}
                    ORDER BY created_at DESC, simulation_run_id
                    LIMIT 1
                    """
                ),
                params,
            ).mappings().first()
            if not run:
                return None
            rows = connection.execute(
                text(
                    """
                    SELECT player_id, player_display_name, position, salary,
                           projection_mean, optimal_lineup_count,
                           optimal_lineup_probability, field_ownership, leverage_score
                    FROM target.player_simulation
                    WHERE simulation_run_id = :simulation_run_id
                    ORDER BY optimal_lineup_probability DESC, projection_mean DESC,
                             player_display_name
                    """
                ),
                {"simulation_run_id": run["simulation_run_id"]},
            ).mappings().all()
        return SimulationResult(
            simulation_run_id=str(run["simulation_run_id"]),
            simulation_model_id=str(run["simulation_model_id"]),
            season=int(run["season"]),
            week=int(run["week"]),
            slate=str(run["slate_id"]),
            contest_format=str(run["contest_format"]),
            projection_run_id=str(run["projection_run_id"]),
            ownership_run_id=str(run["ownership_run_id"]) if run.get("ownership_run_id") else None,
            num_simulations=int(run["num_simulations"]),
            successful_simulations=int(run["successful_simulations"]),
            seed=int(run["seed"]),
            salary_cap=int(run["salary_cap"]),
            status=str(run["status"]),
            message=str(run.get("message") or ""),
            data_cutoff_at=run.get("data_cutoff_at"),
            created_at=run["created_at"],
            rows=[dict(row) for row in rows],
        )

    def fetch_player_result(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        player_id: str,
        projection_run_id: str | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        result = self.fetch_latest(
            season=season,
            week=week,
            slate=slate,
            projection_run_id=projection_run_id,
        )
        if result is None:
            return None, None
        row = next((row for row in result.rows if str(row["player_id"]) == str(player_id)), None)
        return row, result.simulation_run_id

    def estimate_player_modifier(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        player_id: str,
        projection_multiplier: float,
        projection_run_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Replay the latest run's exact draws with one player's distribution changed."""
        result = self.fetch_latest(
            season=season,
            week=week,
            slate=slate,
            projection_run_id=projection_run_id,
        )
        if result is None:
            return None
        baseline = next(
            (row for row in result.rows if str(row["player_id"]) == str(player_id)),
            None,
        )
        if baseline is None:
            return None
        pool = self._load_persisted_pool(result.simulation_run_id)
        target = pool["player_id"].astype(str) == str(player_id)
        if int(target.sum()) != 1:
            return None
        for column in (
            "projection_mean",
            "projection_p10",
            "projection_p25",
            "projection_p50",
            "projection_p75",
            "projection_p90",
        ):
            pool.loc[target, column] = (
                pd.to_numeric(pool.loc[target, column], errors="coerce")
                * float(projection_multiplier)
            ).clip(lower=0.0)
        counts, successful = simulate_optimal_lineups(
            pool,
            num_simulations=result.num_simulations,
            seed=result.seed,
            salary_cap=result.salary_cap,
        )
        if successful == 0:
            return None
        target_index = int(np.flatnonzero(target.to_numpy())[0])
        proposed_probability = round(float(counts[target_index]) / successful * 100.0, 6)
        return {
            "simulation_run_id": result.simulation_run_id,
            "simulation_model_id": result.simulation_model_id,
            "baseline_optimal_lineup_probability": float(
                baseline["optimal_lineup_probability"]
            ),
            "proposed_optimal_lineup_probability": proposed_probability,
            "num_simulations": result.num_simulations,
            "successful_simulations": successful,
            "seed": result.seed,
        }

    def _load_persisted_pool(self, simulation_run_id: str) -> pd.DataFrame:
        """Reconstruct the exact immutable player distributions used by a run."""
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT player_id, player_display_name, position, salary,
                           projection_mean, field_ownership, result_json
                    FROM target.player_simulation
                    WHERE simulation_run_id = :simulation_run_id
                    ORDER BY player_id
                    """
                ),
                {"simulation_run_id": simulation_run_id},
            ).mappings().all()
        pool_rows: list[dict[str, Any]] = []
        for row in rows:
            details = row.get("result_json") or {}
            if isinstance(details, str):
                details = json.loads(details)
            distribution = details.get("projection_distribution") or {}
            required = ("p10", "p25", "p50", "p75", "p90")
            if any(distribution.get(key) is None for key in required):
                raise ValueError(
                    "Simulation run predates immutable distribution replay; run DT-502 again."
                )
            pool_rows.append(
                {
                    "player_id": str(row["player_id"]),
                    "player_display_name": str(row["player_display_name"]),
                    "position": str(row["position"]),
                    "salary": int(row["salary"]),
                    "projection_mean": float(distribution.get("mean", row["projection_mean"])),
                    "projection_p10": float(distribution["p10"]),
                    "projection_p25": float(distribution["p25"]),
                    "projection_p50": float(distribution["p50"]),
                    "projection_p75": float(distribution["p75"]),
                    "projection_p90": float(distribution["p90"]),
                    "field_ownership": row.get("field_ownership"),
                    "team_id": str(details.get("team_id") or ""),
                    "opponent_team_id": str(details.get("opponent_team_id") or ""),
                    "game_id": str(details.get("game_id") or ""),
                    "sampling_index": int(details.get("sampling_index", -1)),
                }
            )
        if not pool_rows:
            raise ValueError(f"Simulation run has no player results: {simulation_run_id}")
        pool_rows.sort(key=lambda row: row["sampling_index"])
        return pd.DataFrame(pool_rows)
