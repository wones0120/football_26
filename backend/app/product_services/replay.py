"""Deterministic historical replay for classic cash stacking policies."""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
from contextlib import redirect_stdout
from datetime import datetime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import create_engine, inspect, text

from Database.config import get_connection_string
from .contest_evidence import (
    build_contest_field_evidence,
    public_field_evidence,
    score_lineup_against_contest,
)
from .optimizer import (
    CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID,
    CLASSIC_CASH_STACK_QB_PAIR_ID,
    CLASSIC_CASH_STACK_UNCONSTRAINED_ID,
    CASH_OBJECTIVE_ID,
    MIN_SALARY,
    SALARY_CAP,
    OptimizerService,
    build_classic_cash_objective,
    cash_objective_config,
    resolve_stacking_policy,
    summarize_classic_cash_lineup,
)


CLASSIC_CASH_STACK_REPLAY_ID = "classic_cash_stack_replay_v2"
DEFAULT_CASH_STACK_POLICY_IDS = (
    CLASSIC_CASH_STACK_UNCONSTRAINED_ID,
    CLASSIC_CASH_STACK_QB_PAIR_ID,
    CLASSIC_CASH_STACK_QB_PAIR_BRINGBACK_ID,
)
REPLAY_HASH_COLUMNS = (
    "player_id",
    "dk_player_id",
    "name",
    "position",
    "salary",
    "player_team",
    "opponent_team",
    "game_id",
    "salary_created_at",
    "projection",
    "predicted_p50",
    "predicted_p10",
    "predicted_p90",
    "projection_run_id",
)
_KICKOFF_PATTERN = re.compile(
    r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<time>\d{1,2}:\d{2}(?:AM|PM))\s+ET",
    re.IGNORECASE,
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
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
    if hasattr(value, "item"):
        return _json_safe(value.item())
    return str(value)


def canonical_hash(payload: Any) -> str:
    """Hash a JSON-safe payload with stable key and separator ordering."""
    encoded = json.dumps(
        _json_safe(payload),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evidence_cutoff(season: int, week: int) -> dict[str, int | None]:
    """Return the latest logical period allowed to train a target-week replay."""
    if week <= 1:
        return {"season": season - 1, "week": None}
    return {"season": season, "week": week - 1}


def parse_slate_lock(game_values: Iterable[object]) -> datetime | None:
    """Parse the earliest DraftKings game timestamp as the slate lock."""
    kickoffs: list[datetime] = []
    eastern = ZoneInfo("America/New_York")
    for value in game_values:
        match = _KICKOFF_PATTERN.search(str(value or ""))
        if not match:
            continue
        local = datetime.strptime(
            f"{match.group('date')} {match.group('time').upper()}",
            "%m/%d/%Y %I:%M%p",
        )
        kickoffs.append(local.replace(tzinfo=eastern))
    return min(kickoffs) if kickoffs else None


def _coerce_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime) and value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value if isinstance(value, datetime) else None


def assess_salary_snapshot(
    pool: pd.DataFrame,
    slate_lock_at: datetime | None,
) -> dict[str, Any]:
    """Report whether salary availability is proven at or before slate lock."""
    if "salary_created_at" not in pool.columns or pool["salary_created_at"].dropna().empty:
        return {
            "proven_prelock": False,
            "status": "availability_timestamp_missing",
            "latest_salary_created_at": None,
        }
    salary_times = [_coerce_datetime(value) for value in pool["salary_created_at"].dropna()]
    salary_times = [value for value in salary_times if value is not None]
    if not salary_times:
        return {
            "proven_prelock": False,
            "status": "availability_timestamp_unparseable",
            "latest_salary_created_at": None,
        }
    latest = max(salary_times)
    proven = slate_lock_at is not None and latest <= slate_lock_at
    return {
        "proven_prelock": proven,
        "status": "proven_prelock" if proven else "post_lock_ingestion_or_unknown_lock",
        "latest_salary_created_at": latest.isoformat(),
    }


def assess_cutoff_safety(
    manifest: dict[str, Any],
    *,
    season: int,
    week: int,
    slate_lock_at: datetime | None,
) -> dict[str, Any]:
    """Require explicit prior-period training lineage and reject post-lock runs."""
    source_versions = manifest.get("source_versions_json") or {}
    leakage_policy = str(source_versions.get("leakage_policy") or "").strip().lower()
    contract_safe = "strictly before" in leakage_policy or (
        "prior" in leakage_policy and "only" in leakage_policy
    )

    declared_season = source_versions.get("target_season")
    declared_week = source_versions.get("target_week")
    target_matches = (
        declared_season in (None, season, str(season))
        and declared_week in (None, week, str(week))
    )

    cutoff_value = _coerce_datetime(manifest.get("data_cutoff_at"))
    training_cutoff = _coerce_datetime(manifest.get("training_cutoff"))
    timestamp_values = [value for value in (cutoff_value, training_cutoff) if value is not None]
    latest_timestamp = max(timestamp_values) if timestamp_values else None
    post_lock = bool(
        latest_timestamp is not None
        and slate_lock_at is not None
        and latest_timestamp > slate_lock_at
    )

    reasons = []
    if not contract_safe:
        reasons.append("projection lineage does not declare prior-period-only training")
    if not target_matches:
        reasons.append("projection lineage target season/week does not match replay scope")
    if latest_timestamp is not None and slate_lock_at is None:
        reasons.append("timestamped projection lineage cannot be checked because slate lock is unavailable")
    if post_lock:
        reasons.append("projection or feature cutoff is after slate lock")

    safe = not reasons
    if safe and latest_timestamp is None:
        cutoff_basis = "logical_prior_period_contract"
    elif safe:
        cutoff_basis = "timestamp_and_prior_period_contract"
    else:
        cutoff_basis = "unproven"
    return {
        "safe": safe,
        "cutoff_basis": cutoff_basis,
        "logical_evidence_through": evidence_cutoff(season, week),
        "slate_lock_at": _json_safe(slate_lock_at),
        "data_cutoff_at": _json_safe(cutoff_value),
        "training_cutoff": _json_safe(training_cutoff),
        "leakage_policy": leakage_policy or None,
        "reasons": reasons,
    }


def score_lineup_outcomes(
    lineup: list[dict[str, Any]],
    actual_points: dict[str, float],
) -> dict[str, Any]:
    """Score only post-solve outcomes and make incomplete coverage explicit."""
    players = []
    observed_total = 0.0
    missing = []
    for row in sorted(lineup, key=lambda item: str(item.get("player_id") or "")):
        player_id = str(row.get("player_id") or "")
        observed = actual_points.get(player_id)
        player = {
            "player_id": player_id,
            "name": str(row.get("name") or row.get("player_name") or player_id),
            "position": str(row.get("position") or "").upper(),
            "salary": int(float(row.get("salary") or 0)),
            "actual_points": float(observed) if observed is not None else None,
        }
        players.append(player)
        if observed is None:
            missing.append(
                {
                    "player_id": player_id,
                    "name": player["name"],
                    "position": player["position"],
                }
            )
        else:
            observed_total += float(observed)

    complete = bool(players) and not missing
    return {
        "players": players,
        "actual_points": round(observed_total, 3) if complete else None,
        "observed_actual_points": round(observed_total, 3),
        "observed_players": len(players) - len(missing),
        "lineup_players": len(players),
        "coverage": round((len(players) - len(missing)) / len(players), 6) if players else 0.0,
        "complete": complete,
        "missing_actual_players": missing,
        "missing_actual_positions": sorted({row["position"] for row in missing}),
    }


def summarize_policy_replays(
    steps: list[dict[str, Any]],
    policy_ids: Iterable[str],
) -> dict[str, Any]:
    """Aggregate stable diagnostics without promoting incomplete outcomes."""
    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 3) if values else None

    def median(values: list[float]) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        midpoint = len(ordered) // 2
        value = (
            ordered[midpoint]
            if len(ordered) % 2
            else (ordered[midpoint - 1] + ordered[midpoint]) / 2
        )
        return round(value, 3)

    def quantile(values: list[float], probability: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        position = (len(ordered) - 1) * probability
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        weight = position - lower
        return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 3)

    def field_margin_downside(values: list[float]) -> dict[str, Any]:
        if not values:
            return {
                "sample_size": 0,
                "worst_margin": None,
                "p10_margin": None,
                "p25_margin": None,
                "median_margin": None,
                "lower_quartile_mean": None,
                "below_field_median_count": 0,
                "below_field_median_rate": None,
            }
        ordered = sorted(values)
        lower_tail_size = max(1, math.ceil(len(ordered) * 0.25))
        below_median_count = sum(value < 0 for value in ordered)
        return {
            "sample_size": len(ordered),
            "worst_margin": round(ordered[0], 3),
            "p10_margin": quantile(ordered, 0.10),
            "p25_margin": quantile(ordered, 0.25),
            "median_margin": median(ordered),
            "lower_quartile_mean": mean(ordered[:lower_tail_size]),
            "below_field_median_count": below_median_count,
            "below_field_median_rate": round(
                below_median_count / len(ordered),
                6,
            ),
        }

    summary: dict[str, Any] = {}
    baseline_id = CLASSIC_CASH_STACK_UNCONSTRAINED_ID
    for policy_id in policy_ids:
        rows = []
        for step in steps:
            policy = next(
                (
                    item
                    for item in step.get("policies", [])
                    if item.get("policy_id") == policy_id and item.get("status") == "completed"
                ),
                None,
            )
            if policy:
                rows.append(policy)
        observed_scores = [float(row["outcome"]["observed_actual_points"]) for row in rows]
        complete_scores = [
            float(row["outcome"]["actual_points"])
            for row in rows
            if row["outcome"].get("actual_points") is not None
        ]
        contest_results = [
            contest
            for row in rows
            for contest in row.get("contest_results", [])
            if contest.get("eligible")
        ]
        field_margins = [
            float(contest["margin_vs_median"])
            for contest in contest_results
            if contest.get("margin_vs_median") is not None
        ]
        cash_decisions = [
            contest for contest in contest_results if contest.get("cash_hit") is not None
        ]
        cash_tie_boundaries = [
            contest
            for contest in contest_results
            if contest.get("cash_status") == "tie_boundary"
        ]
        double_up_decisions = [
            contest for contest in contest_results if contest.get("double_up_hit") is not None
        ]
        exact_roi_results = [
            contest
            for contest in contest_results
            if contest.get("contest_type") == "cash"
            and contest.get("roi_exact") is not None
        ]
        total_fees = sum(float(contest["entry_fee"]) for contest in exact_roi_results)
        total_payout = sum(float(contest["payout_exact"]) for contest in exact_roi_results)
        summary[policy_id] = {
            "slates_completed": len(rows),
            "complete_outcome_slates": len(complete_scores),
            "mean_observed_actual_points": mean(observed_scores),
            "mean_complete_actual_points": mean(complete_scores),
            "normalized_field_evaluations": len(contest_results),
            "mean_margin_vs_field_median": mean(field_margins),
            "median_margin_vs_field_median": median(field_margins),
            "field_margin_downside": field_margin_downside(field_margins),
            "verified_cash_decisions": len(cash_decisions),
            "cash_hits": sum(contest["cash_hit"] is True for contest in cash_decisions),
            "cash_misses": sum(contest["cash_hit"] is False for contest in cash_decisions),
            "cash_tie_boundaries": len(cash_tie_boundaries),
            "cash_rate": (
                round(sum(contest["cash_hit"] is True for contest in cash_decisions) / len(cash_decisions), 6)
                if cash_decisions
                else None
            ),
            "win_rate": (
                round(sum(contest["cash_hit"] is True for contest in cash_decisions) / len(cash_decisions), 6)
                if cash_decisions
                else None
            ),
            "double_up_decisions": len(double_up_decisions),
            "double_up_hits": sum(
                contest["double_up_hit"] is True for contest in double_up_decisions
            ),
            "double_up_rate": (
                round(
                    sum(contest["double_up_hit"] is True for contest in double_up_decisions)
                    / len(double_up_decisions),
                    6,
                )
                if double_up_decisions
                else None
            ),
            "exact_roi_contests": len(exact_roi_results),
            "total_entry_fees": round(total_fees, 2) if exact_roi_results else None,
            "total_payout": round(total_payout, 2) if exact_roi_results else None,
            "roi": (
                round((total_payout - total_fees) / total_fees, 6)
                if total_fees > 0
                else None
            ),
            "performance_claim_eligible": bool(rows)
            and all(row.get("performance_claim_eligible") for row in rows),
            "cash_performance_claim_eligible": bool(rows)
            and all(row.get("cash_performance_claim_eligible") for row in rows),
        }

    baseline = summary.get(baseline_id, {})
    baseline_observed = baseline.get("mean_observed_actual_points")
    baseline_field_margin = baseline.get("mean_margin_vs_field_median")
    baseline_cash_rate = baseline.get("cash_rate")
    baseline_downside = baseline.get("field_margin_downside") or {}
    for policy in summary.values():
        observed = policy.get("mean_observed_actual_points")
        policy["diagnostic_observed_delta_vs_unconstrained"] = (
            round(float(observed) - float(baseline_observed), 3)
            if observed is not None and baseline_observed is not None
            else None
        )
        field_margin = policy.get("mean_margin_vs_field_median")
        policy["field_margin_delta_vs_unconstrained"] = (
            round(float(field_margin) - float(baseline_field_margin), 3)
            if field_margin is not None and baseline_field_margin is not None
            else None
        )
        cash_rate = policy.get("cash_rate")
        policy["cash_rate_delta_vs_unconstrained"] = (
            round(float(cash_rate) - float(baseline_cash_rate), 6)
            if cash_rate is not None and baseline_cash_rate is not None
            else None
        )
        downside = policy.get("field_margin_downside") or {}
        policy["p10_margin_delta_vs_unconstrained"] = (
            round(
                float(downside["p10_margin"])
                - float(baseline_downside["p10_margin"]),
                3,
            )
            if downside.get("p10_margin") is not None
            and baseline_downside.get("p10_margin") is not None
            else None
        )
        policy["lower_quartile_mean_delta_vs_unconstrained"] = (
            round(
                float(downside["lower_quartile_mean"])
                - float(baseline_downside["lower_quartile_mean"]),
                3,
            )
            if downside.get("lower_quartile_mean") is not None
            and baseline_downside.get("lower_quartile_mean") is not None
            else None
        )
    return summary


class ClassicCashStackReplayService:
    """Replay exact historical inputs through each DT-402 stacking policy."""

    def __init__(
        self,
        connection_string: str | None = None,
        optimizer: OptimizerService | None = None,
    ) -> None:
        self.connection_string = connection_string or get_connection_string()
        self.engine = create_engine(self.connection_string)
        self.optimizer = optimizer or OptimizerService(self.connection_string)

    def available_weeks(self, season: int, slate: str) -> list[int]:
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT DISTINCT salary.week
                    FROM target.snapshot_salary salary
                    WHERE salary.season = :season
                      AND UPPER(COALESCE(salary.slate, salary.slate_id)) = UPPER(:slate)
                    ORDER BY salary.week
                    """
                ),
                {"season": season, "slate": slate},
            ).fetchall()
        return [int(row.week) for row in rows]

    def _projection_manifests(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        projection_run_id: str | None,
    ) -> list[dict[str, Any]]:
        run_filter = "AND projection.projection_run_id = :projection_run_id" if projection_run_id else ""
        params: dict[str, Any] = {"season": season, "week": week, "slate": slate}
        if projection_run_id:
            params["projection_run_id"] = projection_run_id
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    f"""
                    SELECT
                        projection.projection_run_id,
                        projection.model_run_id,
                        COUNT(*) AS projection_rows,
                        MAX(COALESCE(projection.data_cutoff_at, model_run.data_cutoff_at))
                            AS data_cutoff_at,
                        model_run.params_json,
                        feature_run.training_cutoff,
                        feature_run.source_versions_json,
                        feature_run.feature_set_hash
                    FROM target.player_projection projection
                    JOIN target.model_run model_run
                      ON model_run.model_run_id = projection.model_run_id
                    LEFT JOIN target.feature_generation_run feature_run
                      ON feature_run.feature_run_id = model_run.feature_run_id
                    WHERE projection.season = :season
                      AND projection.week = :week
                      AND (projection.slate_id IS NULL OR UPPER(projection.slate_id) = UPPER(:slate))
                      {run_filter}
                    GROUP BY
                        projection.projection_run_id,
                        projection.model_run_id,
                        model_run.params_json,
                        feature_run.training_cutoff,
                        feature_run.source_versions_json,
                        feature_run.feature_set_hash
                    ORDER BY projection.projection_run_id
                    """
                ),
                params,
            ).mappings().all()
        return [dict(row) for row in rows]

    def resolve_projection_manifest(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        projection_run_id: str | None,
    ) -> dict[str, Any]:
        manifests = self._projection_manifests(
            season=season,
            week=week,
            slate=slate,
            projection_run_id=projection_run_id,
        )
        if not manifests:
            requested = f" {projection_run_id}" if projection_run_id else ""
            raise ValueError(f"No compatible projection run{requested} for {season} week {week} {slate}.")
        if len(manifests) > 1:
            choices = ", ".join(str(row["projection_run_id"]) for row in manifests)
            raise ValueError(
                "Historical replay requires an explicit projection_run_id when multiple runs exist: "
                + choices
            )
        return manifests[0]

    def load_player_pool(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        projection_run_id: str,
    ) -> pd.DataFrame:
        """Load a content-hashed salary snapshot and one exact projection run."""
        inspector = inspect(self.engine)
        if not inspector.has_table("curated_salary"):
            raise ValueError("Historical replay requires public.curated_salary for complete DK rosters.")
        with self.engine.begin() as connection:
            pool = pd.read_sql(
                text(
                    """
                    WITH salary AS (
                        SELECT DISTINCT ON (player_master_id)
                            player_master_id AS player_id,
                            source_player_key AS dk_player_id,
                            player_name AS name,
                            player_name,
                            CASE
                                WHEN UPPER(COALESCE(NULLIF(position, ''), roster_position)) IN ('D', 'DEF')
                                    THEN 'DST'
                                ELSE UPPER(COALESCE(NULLIF(position, ''), roster_position))
                            END AS position,
                            salary,
                            UPPER(team) AS player_team,
                            UPPER(opponent) AS opponent_team,
                            game_info AS game_id,
                            created_at AS salary_created_at
                        FROM public.curated_salary
                        WHERE season = :season AND week = :week
                          AND UPPER(slate) = UPPER(:slate)
                          AND player_master_id IS NOT NULL
                        ORDER BY
                            player_master_id,
                            created_at DESC,
                            source_player_key
                    ),
                    projection AS (
                        SELECT DISTINCT ON (player_id)
                            player_id,
                            projection_run_id,
                            mean,
                            median,
                            p10,
                            p90,
                            data_cutoff_at
                        FROM target.player_projection
                        WHERE season = :season AND week = :week
                          AND projection_run_id = :projection_run_id
                          AND (slate_id IS NULL OR UPPER(slate_id) = UPPER(:slate))
                        ORDER BY player_id, created_at DESC, game_id
                    )
                    SELECT
                        salary.*,
                        projection.projection_run_id,
                        projection.mean AS projection,
                        projection.median AS predicted_p50,
                        projection.p10 AS predicted_p10,
                        projection.p90 AS predicted_p90,
                        projection.p90,
                        projection.data_cutoff_at,
                        CASE
                            WHEN projection.player_id IS NULL THEN 'missing_projection'
                            ELSE 'exact_projection_run'
                        END AS replay_projection_status
                    FROM salary
                    LEFT JOIN projection ON projection.player_id = salary.player_id
                    ORDER BY salary.player_id
                    """
                ),
                connection,
                params={
                    "season": season,
                    "week": week,
                    "slate": slate,
                    "projection_run_id": projection_run_id,
                },
            )
        if pool.empty:
            raise ValueError(f"No salary rows found for {season} week {week} {slate}.")
        pool["salary"] = pd.to_numeric(pool["salary"], errors="coerce").fillna(0)
        pool = pool[pool["salary"] >= MIN_SALARY].copy()
        pool["projection"] = pd.to_numeric(pool["projection"], errors="coerce").fillna(0.0)
        for column in ("predicted_p50", "predicted_p10", "predicted_p90", "p90"):
            pool[column] = pd.to_numeric(pool[column], errors="coerce").fillna(pool["projection"])
        pool["calibration_role"] = "historical_replay"
        pool["calibration_sample_size"] = 0
        pool["calibration_method"] = "exact_projection_run"
        pool["calibration_position"] = pool["position"]
        pool["name_norm"] = pool["name"].fillna("").astype(str).str.lower().str.strip()
        pool["team_norm"] = pool["player_team"]
        return pool.sort_values(["position", "player_id"], kind="mergesort").reset_index(drop=True)

    def load_actual_points(self, *, season: int, week: int) -> dict[str, float]:
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT player_id, SUM(dk_points) AS actual_points
                    FROM target.fact_player_game_actual
                    WHERE season = :season AND week = :week AND dk_points IS NOT NULL
                    GROUP BY player_id
                    ORDER BY player_id
                    """
                ),
                {"season": season, "week": week},
            ).mappings().all()
        return {str(row["player_id"]): float(row["actual_points"] or 0.0) for row in rows}

    def load_field_proxy(self, *, season: int, week: int, slate: str) -> dict[str, Any]:
        inspector = inspect(self.engine)
        normalized_tables_available = (
            inspector.has_table("dfs_contest", schema="target")
            and inspector.has_table("dfs_contest_entry_result", schema="target")
        )
        if normalized_tables_available:
            contest_columns = {
                column["name"]
                for column in inspector.get_columns("dfs_contest", schema="target")
            }
            contest_type_select = (
                "contest.contest_type" if "contest_type" in contest_columns else "'unknown'::text"
            )
            with self.engine.begin() as connection:
                contest_rows = connection.execute(
                    text(
                        f"""
                        SELECT contest.contest_id, contest.source_file_id,
                               source.content_sha256, contest.contest_name,
                               contest.contest_format, {contest_type_select} AS contest_type,
                               contest.entry_fee, contest.field_size,
                               contest.max_entries_per_user, contest.prize_pool,
                               contest.metadata_json
                        FROM target.dfs_contest contest
                        LEFT JOIN target.source_file_import source
                          ON source.source_file_id = contest.source_file_id
                        WHERE contest.season = :season AND contest.week = :week
                          AND UPPER(contest.slate_id) = UPPER(:slate)
                          AND LOWER(contest.contest_format) = 'classic'
                        ORDER BY contest.contest_id
                        """
                    ),
                    {"season": season, "week": week, "slate": slate},
                ).mappings().all()
                contest_ids = [str(row["contest_id"]) for row in contest_rows]
                entry_rows = connection.execute(
                    text(
                        """
                        SELECT contest_id, entry_id, rank, entry_points
                        FROM target.dfs_contest_entry_result
                        WHERE contest_id = ANY(:contest_ids)
                          AND entry_points IS NOT NULL
                        ORDER BY contest_id, rank NULLS LAST, entry_id
                        """
                    ),
                    {"contest_ids": contest_ids},
                ).mappings().all() if contest_ids else []
                tier_rows = connection.execute(
                    text(
                        """
                        SELECT contest_id, min_rank, max_rank, payout, prize_description
                        FROM target.dfs_contest_payout_tier
                        WHERE contest_id = ANY(:contest_ids)
                        ORDER BY contest_id, min_rank, max_rank
                        """
                    ),
                    {"contest_ids": contest_ids},
                ).mappings().all() if (
                    contest_ids
                    and inspector.has_table("dfs_contest_payout_tier", schema="target")
                ) else []

            entries_by_contest: dict[str, list[dict[str, Any]]] = {}
            for row in entry_rows:
                entries_by_contest.setdefault(str(row["contest_id"]), []).append(dict(row))
            tiers_by_contest: dict[str, list[dict[str, Any]]] = {}
            for row in tier_rows:
                tiers_by_contest.setdefault(str(row["contest_id"]), []).append(dict(row))

            contests = []
            for row in contest_rows:
                contest = dict(row)
                metadata = contest.get("metadata_json") or {}
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except json.JSONDecodeError:
                        metadata = {}
                if str(contest.get("contest_type") or "unknown") == "unknown":
                    contest["contest_type"] = metadata.get("contest_type") or "unknown"
                contest_id = str(contest["contest_id"])
                contests.append(
                    build_contest_field_evidence(
                        contest,
                        entries_by_contest.get(contest_id, []),
                        tiers_by_contest.get(contest_id, []),
                    )
                )
            if contests:
                eligible_contests = [row for row in contests if row["field_proxy_eligible"]]
                verified_cash = [row for row in contests if row["cash_line_verified"]]
                return {
                    "available": bool(eligible_contests),
                    "normalized_contests": len(contests),
                    "eligible_field_contests": len(eligible_contests),
                    "verified_cash_contests": len(verified_cash),
                    "source": "target.dfs_contest_entry_result",
                    "evidence_status": (
                        "linked_normalized_contest_field"
                        if eligible_contests
                        else "linked_normalized_contest_incomplete"
                    ),
                    "contests": contests,
                }

        if not inspector.has_table("dk_contest_entries"):
            return {"available": False, "reason": "public.dk_contest_entries is unavailable"}
        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE entry_points IS NOT NULL) AS entries,
                        percentile_cont(0.5) WITHIN GROUP (ORDER BY entry_points)
                            FILTER (WHERE entry_points IS NOT NULL) AS median_points,
                        percentile_cont(0.75) WITHIN GROUP (ORDER BY entry_points)
                            FILTER (WHERE entry_points IS NOT NULL) AS p75_points,
                        MAX(entry_points) AS winning_points
                    FROM public.dk_contest_entries
                    WHERE season = :season AND week = :week
                      AND UPPER(slate) = UPPER(:slate)
                    """
                ),
                {"season": season, "week": week, "slate": slate},
            ).mappings().one()
        entries = int(row["entries"] or 0)
        return {
            "available": entries > 0,
            "entries": entries,
            "median_points": float(row["median_points"]) if row["median_points"] is not None else None,
            "p75_points": float(row["p75_points"]) if row["p75_points"] is not None else None,
            "winning_points": float(row["winning_points"]) if row["winning_points"] is not None else None,
            "source": "public.dk_contest_entries",
            "evidence_status": "unlinked_legacy_contest_proxy",
        }

    def _input_hash(
        self,
        pool: pd.DataFrame,
        actual_points: dict[str, float],
        manifest: dict[str, Any],
        field_proxy: dict[str, Any],
    ) -> str:
        columns = [column for column in REPLAY_HASH_COLUMNS if column in pool.columns]
        pool_rows = pool[columns].sort_values(["player_id"], kind="mergesort").to_dict(orient="records")
        relevant_actuals = {
            str(player_id): actual_points.get(str(player_id))
            for player_id in sorted(pool["player_id"].astype(str).unique())
        }
        return canonical_hash(
            {
                "pool": pool_rows,
                "actual_points": relevant_actuals,
                "projection_manifest": manifest,
                "field_proxy": public_field_evidence(field_proxy),
            }
        )

    def replay_from_frames(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        pool: pd.DataFrame,
        actual_points: dict[str, float],
        projection_manifest: dict[str, Any],
        cutoff_assessment: dict[str, Any],
        field_proxy: dict[str, Any] | None = None,
        policy_ids: Iterable[str] = DEFAULT_CASH_STACK_POLICY_IDS,
    ) -> dict[str, Any]:
        if "actual_points" in pool.columns:
            raise ValueError("Replay player pool must not contain postgame actual_points.")
        if not cutoff_assessment.get("safe"):
            raise ValueError(
                "Projection run is not replay-safe: "
                + "; ".join(cutoff_assessment.get("reasons") or ["unknown cutoff failure"])
            )
        policy_ids = tuple(policy_ids)
        if not policy_ids:
            raise ValueError("At least one classic cash replay policy is required.")
        unknown = [policy_id for policy_id in policy_ids if policy_id not in DEFAULT_CASH_STACK_POLICY_IDS]
        if unknown:
            raise ValueError("Unsupported classic cash replay policies: " + ", ".join(unknown))

        base_pool = pool.sort_values(["position", "player_id"], kind="mergesort").reset_index(drop=True)
        # The legacy optimizer emits diagnostic prints. Replay output is a JSON artifact,
        # so capture those messages rather than corrupting stdout for CLI/API consumers.
        with redirect_stdout(io.StringIO()):
            filtered_pool = self.optimizer._apply_pool_filters(
                base_pool.copy(), contest_type="cash"
            )
            scored_pool = build_classic_cash_objective(filtered_pool)
            policy_results = []
            for policy_id in policy_ids:
                policy = resolve_stacking_policy(
                    contest_format="classic",
                    objective="cash",
                    params={"stack_policy_id": policy_id},
                )
                lineup = self.optimizer._solve_lineup(
                    scored_pool.copy(),
                    score_col="cash_score",
                    contest_type="cash",
                    stack_params=policy,
                )
                if not lineup:
                    policy_results.append(
                        {"policy_id": policy_id, "policy": policy, "status": "no_lineup"}
                    )
                    continue
                valid, reason = self.optimizer._lineups_satisfy_stack([lineup], policy, "cash")
                if not valid:
                    policy_results.append(
                        {
                            "policy_id": policy_id,
                            "policy": policy,
                            "status": "invalid_lineup",
                            "reason": reason,
                        }
                    )
                    continue
                outcome = score_lineup_outcomes(lineup, actual_points)
                cash_summary = summarize_classic_cash_lineup(lineup)
                proxy = field_proxy or {"available": False}
                contest_results = [
                    score_lineup_against_contest(outcome.get("actual_points"), contest)
                    for contest in proxy.get("contests", [])
                ]
                eligible_contest_results = [
                    contest for contest in contest_results if contest.get("eligible")
                ]
                median_points = proxy.get("median_points")
                legacy_proxy_eligible = (
                    outcome["complete"]
                    and median_points is not None
                    and proxy.get("evidence_status") == "linked_cash_contest"
                )
                field_margins = [
                    float(contest["margin_vs_median"])
                    for contest in eligible_contest_results
                    if contest.get("margin_vs_median") is not None
                ]
                policy_results.append(
                    {
                        "policy_id": policy_id,
                        "policy": policy,
                        "status": "completed",
                        "lineup": outcome.pop("players"),
                        "cash_summary": cash_summary,
                        "outcome": outcome,
                        "contest_results": contest_results,
                        "field_proxy_result": {
                            "eligible": bool(eligible_contest_results) or legacy_proxy_eligible,
                            "contests_evaluated": len(eligible_contest_results),
                            "mean_margin_vs_median": (
                                round(sum(field_margins) / len(field_margins), 3)
                                if field_margins
                                else None
                            ),
                            "margin_vs_median": (
                                round(float(outcome["actual_points"]) - float(median_points), 3)
                                if legacy_proxy_eligible
                                else None
                            ),
                        },
                    }
                )

        input_hash = self._input_hash(
            pool=base_pool,
            actual_points=actual_points,
            manifest=projection_manifest,
            field_proxy=field_proxy or {"available": False},
        )
        specification = {
            "contract_id": CLASSIC_CASH_STACK_REPLAY_ID,
            "season": season,
            "week": week,
            "slate": slate.upper(),
            "contest_format": "classic",
            "objective": "cash",
            "objective_id": CASH_OBJECTIVE_ID,
            "objective_config": cash_objective_config(),
            "projection_run_id": projection_manifest.get("projection_run_id"),
            "policy_ids": list(policy_ids),
            "solver_contract": {
                "salary_cap": SALARY_CAP,
                "pool_filters": "classic_cash_pool_filters_v1",
                "enforce_single_te": False,
                "avoid_dst_opponents": False,
            },
        }
        replay_id = f"cash-stack-replay:{canonical_hash({'specification': specification, 'input_hash': input_hash})[:24]}"
        lineup_outcomes_complete = all(
            row.get("status") == "completed" and row.get("outcome", {}).get("complete")
            for row in policy_results
        )
        slate_lock_at = _coerce_datetime(cutoff_assessment.get("slate_lock_at"))
        salary_snapshot = assess_salary_snapshot(base_pool, slate_lock_at)
        proxy = field_proxy or {"available": False}
        normalized_field_complete = bool(
            proxy.get("evidence_status") == "linked_normalized_contest_field"
            and int(proxy.get("eligible_field_contests") or 0) > 0
        )
        verified_cash_field = bool(int(proxy.get("verified_cash_contests") or 0) > 0)
        complete = (
            lineup_outcomes_complete
            and salary_snapshot["proven_prelock"]
            and normalized_field_complete
        )
        cash_complete = complete and verified_cash_field
        for policy_result in policy_results:
            policy_result["performance_claim_eligible"] = bool(
                complete and policy_result.get("status") == "completed"
            )
            policy_result["cash_performance_claim_eligible"] = bool(
                cash_complete
                and policy_result.get("status") == "completed"
                and any(
                    contest.get("cash_hit") is not None
                    for contest in policy_result.get("contest_results", [])
                )
            )
        missing_positions = sorted(
            {
                position
                for row in policy_results
                for position in row.get("outcome", {}).get("missing_actual_positions", [])
            }
        )
        limitations = []
        if missing_positions:
            limitations.append(
                "Canonical actuals are missing selected lineup positions: "
                + ", ".join(missing_positions)
            )
        if not salary_snapshot["proven_prelock"]:
            limitations.append(
                "Salary content is hashed, but its availability at slate lock is not proven."
            )
        if proxy.get("evidence_status") == "unlinked_legacy_contest_proxy":
            limitations.append(
                "Field scores are not linked to normalized cash-contest metadata."
            )
        elif proxy.get("evidence_status") == "linked_normalized_contest_incomplete":
            limitations.append(
                "Normalized contest metadata is linked, but the observed field is incomplete."
            )
        elif not normalized_field_complete:
            limitations.append(
                "No complete normalized classic contest field is linked to this replay slate."
            )
        if normalized_field_complete and not verified_cash_field:
            limitations.append(
                "Normalized field-proxy comparison is available, but verified cash-line/ROI evidence requires a cash contest with payout tiers."
            )
        core = {
            "replay_id": replay_id,
            "specification": specification,
            "input_hash": input_hash,
            "projection_manifest": _json_safe(projection_manifest),
            "cutoff_assessment": cutoff_assessment,
            "field_proxy": public_field_evidence(proxy),
            "pool_rows": len(base_pool),
            "filtered_pool_rows": len(scored_pool),
            "policies": policy_results,
            "data_sources": {
                "salary": "public.curated_salary_content_hashed",
                "projection": "target.player_projection_exact_run",
                "actuals": "target.fact_player_game_actual_post_solve_only",
                "field": (
                    "target.dfs_contest_entry_result"
                    if normalized_field_complete
                    else "unavailable_or_unlinked"
                ),
            },
            "salary_snapshot_assessment": salary_snapshot,
            "limitations": limitations,
            "evidence_status": (
                "promotion_evidence_complete_cash_line"
                if cash_complete
                else "promotion_evidence_complete_field_proxy"
                if complete
                else "diagnostic_incomplete_inputs_or_outcomes"
            ),
            "performance_claim_eligible": complete,
            "cash_performance_claim_eligible": cash_complete,
        }
        core["artifact_hash"] = canonical_hash(core)
        return core

    def run_slate(
        self,
        *,
        season: int,
        week: int,
        slate: str,
        projection_run_id: str | None = None,
        policy_ids: Iterable[str] = DEFAULT_CASH_STACK_POLICY_IDS,
    ) -> dict[str, Any]:
        manifest = self.resolve_projection_manifest(
            season=season,
            week=week,
            slate=slate,
            projection_run_id=projection_run_id,
        )
        resolved_projection_run_id = str(manifest["projection_run_id"])
        pool = self.load_player_pool(
            season=season,
            week=week,
            slate=slate,
            projection_run_id=resolved_projection_run_id,
        )
        cutoff = assess_cutoff_safety(
            manifest,
            season=season,
            week=week,
            slate_lock_at=parse_slate_lock(pool["game_id"].tolist()),
        )
        actual_points = self.load_actual_points(season=season, week=week)
        field_proxy = self.load_field_proxy(season=season, week=week, slate=slate)
        return self.replay_from_frames(
            season=season,
            week=week,
            slate=slate,
            pool=pool,
            actual_points=actual_points,
            projection_manifest=manifest,
            cutoff_assessment=cutoff,
            field_proxy=field_proxy,
            policy_ids=policy_ids,
        )

    def run(
        self,
        *,
        season: int,
        week: int | None,
        slate: str,
        projection_run_id: str | None = None,
        policy_ids: Iterable[str] = DEFAULT_CASH_STACK_POLICY_IDS,
    ) -> dict[str, Any]:
        if projection_run_id and week is None:
            raise ValueError("projection_run_id requires an explicit replay week.")
        policy_ids = tuple(policy_ids)
        weeks = [week] if week is not None else self.available_weeks(season, slate)
        steps = []
        failures = []
        for target_week in weeks:
            try:
                steps.append(
                    self.run_slate(
                        season=season,
                        week=int(target_week),
                        slate=slate,
                        projection_run_id=projection_run_id,
                        policy_ids=policy_ids,
                    )
                )
            except ValueError as exc:
                if week is not None:
                    raise
                failures.append(
                    {
                        "season": season,
                        "week": int(target_week),
                        "slate": slate.upper(),
                        "error": str(exc),
                    }
                )

        aggregate = summarize_policy_replays(steps, policy_ids)
        performance_claim_eligible = bool(steps) and not failures and all(
            step.get("performance_claim_eligible") for step in steps
        )
        cash_performance_claim_eligible = bool(steps) and not failures and all(
            step.get("cash_performance_claim_eligible") for step in steps
        )
        core = {
            "contract_id": CLASSIC_CASH_STACK_REPLAY_ID,
            "season": season,
            "requested_week": week,
            "slate": slate.upper(),
            "policy_ids": list(policy_ids),
            "status": "completed" if steps and not failures else "partial" if steps else "failed",
            "weeks_requested": len(weeks),
            "weeks_completed": len(steps),
            "steps": steps,
            "failures": failures,
            "aggregate": aggregate,
            "performance_claim_eligible": performance_claim_eligible,
            "cash_performance_claim_eligible": cash_performance_claim_eligible,
            "evidence_status": (
                "verified_cash_performance_evidence"
                if cash_performance_claim_eligible
                else "normalized_field_performance_evidence"
                if performance_claim_eligible
                else "diagnostic_only"
            ),
        }
        core["artifact_hash"] = canonical_hash(core)
        return core
