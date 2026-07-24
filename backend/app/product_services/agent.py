"""News and matchup agent with table-driven symbolic rules."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import pandas as pd
from sqlalchemy import create_engine, text

from Database.config import get_connection_string
from .optimizer import _normalize_alias
from .target_schema import validate_target_schema

logger = logging.getLogger(__name__)


@dataclass
class AgentAdjustment:
    player_id: str
    reason: str
    projection_delta: float = 0.0
    ceiling_delta: float = 0.0
    ownership_delta: float = 0.0


@dataclass
class AgentTrace:
    rule_run_id: str
    player_id: str
    rule_id: str
    rule_name: str
    reason: str
    mean_before: float
    mean_after: float
    p90_before: float
    p90_after: float
    mean_multiplier: float
    p90_multiplier: float


@dataclass
class AgentConfig:
    rules_source: str = "symbolic_rules"
    rules_loaded: int = 0
    rule_run_id: str = ""
    projection_run_id: str | None = None
    target_persisted: bool = False
    max_chalk: int = 4
    min_leverage: int = 2
    max_total_ownership: float = 160.0


@dataclass
class SymbolicRule:
    rule_id: str
    rule_name: str
    rule_type: str
    enabled: bool
    priority: int
    version: int
    condition_json: Dict[str, Any]
    action_json: Dict[str, Any]


def _optional_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    normalized = str(value).strip()
    return normalized or None


def _safe_number(value: Any, default: float = 0.0) -> float:
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _empty_metrics() -> Dict[str, Any]:
    return {
        "rows": 0,
        "base_mae": 0.0,
        "adjusted_mae": 0.0,
        "mae_delta": 0.0,
        "base_rmse": 0.0,
        "adjusted_rmse": 0.0,
        "rmse_delta": 0.0,
        "base_bias": 0.0,
        "adjusted_bias": 0.0,
        "improved_rows": 0,
        "worse_rows": 0,
        "unchanged_rows": 0,
        "hit_rate": 0.0,
    }


def _metric_summary(df: pd.DataFrame, base_col: str, adjusted_col: str) -> Dict[str, Any]:
    if df.empty:
        return _empty_metrics()
    base_err = pd.to_numeric(df[base_col], errors="coerce") - pd.to_numeric(df["actual_points"], errors="coerce")
    adj_err = pd.to_numeric(df[adjusted_col], errors="coerce") - pd.to_numeric(df["actual_points"], errors="coerce")
    base_abs = base_err.abs()
    adj_abs = adj_err.abs()
    improved = int((adj_abs < base_abs).sum())
    worse = int((adj_abs > base_abs).sum())
    unchanged = int((adj_abs == base_abs).sum())
    rows = int(len(df))
    return {
        "rows": rows,
        "base_mae": float(base_abs.mean() or 0.0),
        "adjusted_mae": float(adj_abs.mean() or 0.0),
        "mae_delta": float((base_abs.mean() or 0.0) - (adj_abs.mean() or 0.0)),
        "base_rmse": float((base_err.pow(2).mean() or 0.0) ** 0.5),
        "adjusted_rmse": float((adj_err.pow(2).mean() or 0.0) ** 0.5),
        "rmse_delta": float(((base_err.pow(2).mean() or 0.0) ** 0.5) - ((adj_err.pow(2).mean() or 0.0) ** 0.5)),
        "base_bias": float(base_err.mean() or 0.0),
        "adjusted_bias": float(adj_err.mean() or 0.0),
        "improved_rows": improved,
        "worse_rows": worse,
        "unchanged_rows": unchanged,
        "hit_rate": float(improved / rows) if rows else 0.0,
    }


def _rule_recommendation(row: Dict[str, Any]) -> Dict[str, Any]:
    rows = int(row.get("rows", 0) or 0)
    mae_delta = float(row.get("mae_delta", 0.0) or 0.0)
    hit_rate = float(row.get("hit_rate", 0.0) or 0.0)
    rule_id = str(row.get("rule_id", "unknown"))
    if rows < 10:
        action = "collect_more_data"
        severity = "info"
        rationale = f"{rule_id} has only {rows} evaluated rows; keep collecting outcomes before changing it."
    elif mae_delta > 0 and hit_rate >= 0.55:
        action = "keep_or_increase_confidence"
        severity = "positive"
        rationale = f"{rule_id} improved MAE by {mae_delta:.2f} with a {hit_rate:.0%} row hit rate."
    elif mae_delta < 0 and hit_rate <= 0.45:
        action = "review_or_disable"
        severity = "warning"
        rationale = f"{rule_id} worsened MAE by {abs(mae_delta):.2f} with only a {hit_rate:.0%} row hit rate."
    elif mae_delta < 0:
        action = "retune"
        severity = "warning"
        rationale = f"{rule_id} worsened aggregate MAE by {abs(mae_delta):.2f}; inspect position/team splits before reuse."
    else:
        action = "monitor"
        severity = "neutral"
        rationale = f"{rule_id} is roughly neutral so far; keep it enabled only if it supports portfolio construction."
    return {
        "rule_id": rule_id,
        "action": action,
        "severity": severity,
        "rationale": rationale,
        "rows": rows,
        "mae_delta": mae_delta,
        "hit_rate": hit_rate,
    }


class NewsMatchupAgent:
    def __init__(self, engine=None, config: AgentConfig | None = None) -> None:
        self.engine = engine or create_engine(get_connection_string())
        self.config = config or AgentConfig()

    def _ensure_symbolic_schema(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS symbolic_rules (
            rule_id TEXT PRIMARY KEY,
            rule_name TEXT NOT NULL,
            rule_type TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            priority INT NOT NULL DEFAULT 100,
            version INT NOT NULL DEFAULT 1,
            condition_json JSONB NOT NULL,
            action_json JSONB NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS symbolic_adjustments (
            id BIGSERIAL PRIMARY KEY,
            rule_run_id TEXT,
            season INT NOT NULL,
            week INT NOT NULL,
            slate TEXT,
            player_id TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            rule_name TEXT NOT NULL,
            reason TEXT,
            mean_before DOUBLE PRECISION,
            mean_after DOUBLE PRECISION,
            p90_before DOUBLE PRECISION,
            p90_after DOUBLE PRECISION,
            delta_mean DOUBLE PRECISION,
            delta_p90 DOUBLE PRECISION,
            created_at TIMESTAMPTZ DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS symbolic_rule_runs (
            rule_run_id TEXT PRIMARY KEY,
            season INT NOT NULL,
            week INT NOT NULL,
            slate TEXT,
            rules_loaded INT NOT NULL DEFAULT 0,
            rules_applied INT NOT NULL DEFAULT 0,
            projections_seen INT NOT NULL DEFAULT 0,
            projections_adjusted INT NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'completed',
            created_at TIMESTAMPTZ DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS player_expected_points_adjusted (
            rule_run_id TEXT NOT NULL,
            season INT NOT NULL,
            week INT NOT NULL,
            slate TEXT,
            player_id TEXT NOT NULL,
            player_display_name TEXT,
            position TEXT,
            recent_team TEXT,
            opponent_team TEXT,
            base_predicted_mean DOUBLE PRECISION,
            base_predicted_p90 DOUBLE PRECISION,
            adjusted_mean DOUBLE PRECISION,
            adjusted_p90 DOUBLE PRECISION,
            reason TEXT,
            reasons JSONB DEFAULT '[]',
            created_at TIMESTAMPTZ DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS symbolic_projection_snapshots (
            snapshot_id BIGSERIAL PRIMARY KEY,
            rule_run_id TEXT NOT NULL,
            season INT NOT NULL,
            week INT NOT NULL,
            slate TEXT,
            game_id TEXT,
            player_id TEXT NOT NULL,
            model_version TEXT,
            rule_ids JSONB DEFAULT '[]',
            base_mean DOUBLE PRECISION,
            adjusted_mean DOUBLE PRECISION,
            base_p90 DOUBLE PRECISION,
            adjusted_p90 DOUBLE PRECISION,
            ownership_projection DOUBLE PRECISION,
            data_cutoff_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(rule_run_id, player_id)
        );

        CREATE TABLE IF NOT EXISTS symbolic_rule_evaluations (
            evaluation_id BIGSERIAL PRIMARY KEY,
            learning_run_id TEXT NOT NULL,
            rule_run_id TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            rule_version INT,
            season INT NOT NULL,
            week INT NOT NULL,
            slate TEXT,
            player_id TEXT NOT NULL,
            position TEXT,
            team TEXT,
            mean_before DOUBLE PRECISION,
            mean_after DOUBLE PRECISION,
            actual_points DOUBLE PRECISION,
            mae_before DOUBLE PRECISION,
            mae_after DOUBLE PRECISION,
            improved BOOLEAN,
            delta_mae DOUBLE PRECISION,
            reason TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS symbolic_learning_runs (
            learning_run_id TEXT PRIMARY KEY,
            season INT NOT NULL,
            week INT NOT NULL,
            slate TEXT,
            rule_run_id TEXT,
            status TEXT NOT NULL DEFAULT 'completed',
            projections_evaluated INT NOT NULL DEFAULT 0,
            rules_evaluated INT NOT NULL DEFAULT 0,
            rules_improved INT NOT NULL DEFAULT 0,
            rules_worsened INT NOT NULL DEFAULT 0,
            overall_base_mae DOUBLE PRECISION,
            overall_adjusted_mae DOUBLE PRECISION,
            overall_mae_delta DOUBLE PRECISION,
            overall_hit_rate DOUBLE PRECISION,
            recommendations_json JSONB DEFAULT '[]',
            created_at TIMESTAMPTZ DEFAULT now()
        );

        ALTER TABLE symbolic_adjustments ADD COLUMN IF NOT EXISTS rule_run_id TEXT;
        ALTER TABLE player_expected_points_adjusted ADD COLUMN IF NOT EXISTS reasons JSONB DEFAULT '[]';

        CREATE INDEX IF NOT EXISTS idx_symbolic_rules_enabled_priority
            ON symbolic_rules(enabled, priority, rule_id);
        CREATE INDEX IF NOT EXISTS idx_symbolic_adjustments_season_week
            ON symbolic_adjustments(season, week);
        CREATE INDEX IF NOT EXISTS idx_symbolic_adjustments_rule_run
            ON symbolic_adjustments(rule_run_id);
        CREATE INDEX IF NOT EXISTS idx_symbolic_rule_runs_lookup
            ON symbolic_rule_runs(season, week, slate, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_player_expected_points_adjusted_lookup
            ON player_expected_points_adjusted(season, week, slate, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_symbolic_projection_snapshots_lookup
            ON symbolic_projection_snapshots(season, week, slate, rule_run_id);
        CREATE INDEX IF NOT EXISTS idx_symbolic_rule_evaluations_lookup
            ON symbolic_rule_evaluations(season, week, slate, rule_id);
        CREATE INDEX IF NOT EXISTS idx_symbolic_learning_runs_lookup
            ON symbolic_learning_runs(season, week, slate, created_at DESC);
        """
        with self.engine.begin() as conn:
            conn.execute(text(ddl))

    def _seed_default_rules(self) -> None:
        defaults = [
            {
                "rule_id": "injury_negative",
                "rule_name": "Injury Downgrade",
                "rule_type": "injury",
                "enabled": True,
                "priority": 10,
                "version": 1,
                "condition_json": {"indicators": ["Q", "D", "O"], "match_mode": "prefix_or_exact"},
                "action_json": {"mean_multiplier": 0.92, "p90_multiplier": 0.92, "reason": "Injury downgrade"},
            },
            {
                "rule_id": "injury_positive",
                "rule_name": "Positive Injury Note",
                "rule_type": "injury",
                "enabled": True,
                "priority": 20,
                "version": 1,
                "condition_json": {"indicators": ["P", "ACTIVE"], "match_mode": "prefix_or_exact"},
                "action_json": {"mean_multiplier": 1.05, "p90_multiplier": 1.05, "reason": "Positive injury note"},
            },
            {
                "rule_id": "matchup_pass_boost",
                "rule_name": "Pass Funnel/Pace Boost",
                "rule_type": "matchup",
                "enabled": True,
                "priority": 30,
                "version": 1,
                "condition_json": {
                    "positions": ["QB", "WR", "TE"],
                    "pass_funnel_gt": 0.0,
                    "or_pace_gt": 120.0,
                },
                "action_json": {"mean_multiplier": 1.05, "p90_multiplier": 1.05, "reason": "Pass funnel or pace boost"},
            },
            {
                "rule_id": "matchup_slow_penalty",
                "rule_name": "Slow Pace Penalty",
                "rule_type": "matchup",
                "enabled": True,
                "priority": 40,
                "version": 1,
                "condition_json": {
                    "positions": ["WR", "TE"],
                    "pass_funnel_lt": 0.0,
                    "pace_lt": 110.0,
                },
                "action_json": {"mean_multiplier": 0.95, "p90_multiplier": 0.95, "reason": "Slow pace penalty"},
            },
        ]
        with self.engine.begin() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM symbolic_rules")).scalar_one()
            if count > 0:
                return
            for rule in defaults:
                conn.execute(
                    text(
                        """
                        INSERT INTO symbolic_rules
                        (rule_id, rule_name, rule_type, enabled, priority, version, condition_json, action_json)
                        VALUES
                        (:rule_id, :rule_name, :rule_type, :enabled, :priority, :version, CAST(:condition_json AS JSONB), CAST(:action_json AS JSONB))
                        ON CONFLICT (rule_id) DO UPDATE
                        SET
                            rule_name = EXCLUDED.rule_name,
                            rule_type = EXCLUDED.rule_type,
                            enabled = EXCLUDED.enabled,
                            priority = EXCLUDED.priority,
                            version = EXCLUDED.version,
                            condition_json = EXCLUDED.condition_json,
                            action_json = EXCLUDED.action_json,
                            updated_at = now()
                        """
                    ),
                    {
                        **rule,
                        "condition_json": json.dumps(rule["condition_json"]),
                        "action_json": json.dumps(rule["action_json"]),
                    },
                )

    def _as_dict(self, payload: Any) -> Dict[str, Any]:
        if payload is None:
            return {}
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    def _load_rules(self, enabled_only: bool = True) -> List[SymbolicRule]:
        self._ensure_symbolic_schema()
        self._seed_default_rules()
        where_clause = "WHERE enabled = TRUE" if enabled_only else ""
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT rule_id, rule_name, rule_type, enabled, priority, version, condition_json, action_json
                    FROM symbolic_rules
                    """
                    + where_clause
                    + """
                    ORDER BY priority ASC, rule_id ASC
                    """
                )
            ).fetchall()
        return [
            SymbolicRule(
                rule_id=row.rule_id,
                rule_name=row.rule_name,
                rule_type=str(row.rule_type).lower(),
                enabled=bool(row.enabled),
                priority=int(row.priority),
                version=int(row.version),
                condition_json=self._as_dict(row.condition_json),
                action_json=self._as_dict(row.action_json),
            )
            for row in rows
        ]

    def list_rules(self, include_disabled: bool = True) -> List[SymbolicRule]:
        return self._load_rules(enabled_only=not include_disabled)

    def upsert_rule(
        self,
        rule_id: str,
        rule_name: str,
        rule_type: str,
        enabled: bool,
        priority: int,
        version: int,
        condition_json: Dict[str, Any] | None,
        action_json: Dict[str, Any] | None,
    ) -> SymbolicRule:
        self._ensure_symbolic_schema()
        normalized_type = str(rule_type or "").lower().strip()
        if normalized_type not in {"injury", "matchup"}:
            raise ValueError("rule_type must be one of: injury, matchup")
        normalized_condition = condition_json if isinstance(condition_json, dict) else {}
        normalized_action = action_json if isinstance(action_json, dict) else {}
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO symbolic_rules
                    (rule_id, rule_name, rule_type, enabled, priority, version, condition_json, action_json)
                    VALUES
                    (:rule_id, :rule_name, :rule_type, :enabled, :priority, :version, CAST(:condition_json AS JSONB), CAST(:action_json AS JSONB))
                    ON CONFLICT (rule_id) DO UPDATE
                    SET
                        rule_name = EXCLUDED.rule_name,
                        rule_type = EXCLUDED.rule_type,
                        enabled = EXCLUDED.enabled,
                        priority = EXCLUDED.priority,
                        version = EXCLUDED.version,
                        condition_json = EXCLUDED.condition_json,
                        action_json = EXCLUDED.action_json,
                        updated_at = now()
                    """
                ),
                {
                    "rule_id": rule_id,
                    "rule_name": rule_name,
                    "rule_type": normalized_type,
                    "enabled": enabled,
                    "priority": int(priority),
                    "version": int(version),
                    "condition_json": json.dumps(normalized_condition),
                    "action_json": json.dumps(normalized_action),
                },
            )
        rows = self._load_rules(enabled_only=False)
        for row in rows:
            if row.rule_id == rule_id:
                return row
        raise RuntimeError(f"Failed to upsert rule {rule_id}")

    def set_rule_enabled(self, rule_id: str, enabled: bool) -> SymbolicRule | None:
        self._ensure_symbolic_schema()
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE symbolic_rules
                    SET enabled = :enabled, updated_at = now()
                    WHERE rule_id = :rule_id
                    """
                ),
                {"enabled": enabled, "rule_id": rule_id},
            )
        if result.rowcount == 0:
            return None
        rows = self._load_rules(enabled_only=False)
        for row in rows:
            if row.rule_id == rule_id:
                return row
        return None

    def backtest(
        self,
        season: int | None = None,
        week: int | None = None,
        rule_run_id: str | None = None,
        slate: str | None = None,
    ) -> Dict[str, Any]:
        self._ensure_symbolic_schema()
        where = []
        params: Dict[str, Any] = {}
        if season is not None:
            where.append("adj.season = :season")
            params["season"] = season
        if week is not None:
            where.append("adj.week = :week")
            params["week"] = week
        if rule_run_id:
            where.append("adj.rule_run_id = :rule_run_id")
            params["rule_run_id"] = rule_run_id
        if slate:
            where.append("(adj.slate = :slate OR adj.slate IS NULL)")
            params["slate"] = slate
        where_clause = " AND ".join(where) if where else "1 = 1"

        try:
            with self.engine.begin() as conn:
                projections = pd.read_sql(
                    text(
                        f"""
                        SELECT
                            adj.rule_run_id,
                            adj.season,
                            adj.week,
                            adj.slate,
                            adj.player_id,
                            adj.player_display_name,
                            adj.position,
                            adj.base_predicted_mean,
                            adj.adjusted_mean,
                            actual.dk_total_points AS actual_points
                        FROM player_expected_points_adjusted adj
                        JOIN nfl_weekly_data_with_scores actual
                          ON actual.season = adj.season
                         AND actual.week = adj.week
                         AND actual.player_id = adj.player_id
                        WHERE {where_clause}
                        """
                    ),
                    conn,
                    params=params,
                )
                rule_rows = pd.read_sql(
                    text(
                        f"""
                        SELECT
                            sa.rule_run_id,
                            sa.rule_id,
                            sa.rule_name,
                            sa.season,
                            sa.week,
                            sa.player_id,
                            sa.mean_before,
                            sa.mean_after,
                            actual.dk_total_points AS actual_points
                        FROM symbolic_adjustments sa
                        JOIN nfl_weekly_data_with_scores actual
                          ON actual.season = sa.season
                         AND actual.week = sa.week
                         AND actual.player_id = sa.player_id
                        JOIN player_expected_points_adjusted adj
                          ON adj.rule_run_id = sa.rule_run_id
                         AND adj.player_id = sa.player_id
                        WHERE {where_clause.replace("adj.", "sa.")}
                        """
                    ),
                    conn,
                    params=params,
                )
                runs = pd.read_sql(
                    text(
                        """
                        SELECT rule_run_id, season, week, slate, rules_loaded, rules_applied,
                               projections_seen, projections_adjusted, status, created_at
                        FROM symbolic_rule_runs
                        ORDER BY created_at DESC
                        LIMIT 25
                        """
                    ),
                    conn,
                )
        except Exception as exc:
            logger.warning("Could not backtest symbolic agent: %s", exc)
            return {
                "filters": {"season": season, "week": week, "rule_run_id": rule_run_id, "slate": slate},
                "overall": _metric_summary(pd.DataFrame(), "base_predicted_mean", "adjusted_mean"),
                "by_rule": [],
                "runs": [],
            }

        by_rule = []
        if not rule_rows.empty:
            for (rid, rname), group in rule_rows.groupby(["rule_id", "rule_name"], dropna=False):
                summary = _metric_summary(group, "mean_before", "mean_after")
                summary.update({"rule_id": str(rid), "rule_name": str(rname)})
                by_rule.append(summary)
            by_rule = sorted(by_rule, key=lambda row: row["mae_delta"], reverse=True)

        return {
            "filters": {"season": season, "week": week, "rule_run_id": rule_run_id, "slate": slate},
            "overall": _metric_summary(projections, "base_predicted_mean", "adjusted_mean"),
            "by_rule": by_rule,
            "runs": runs.to_dict(orient="records") if not runs.empty else [],
        }

    def evaluate_learning(
        self,
        season: int,
        week: int,
        rule_run_id: str | None = None,
        slate: str | None = None,
    ) -> Dict[str, Any]:
        """Persist rule and projection evaluation rows after actuals are available."""
        self._ensure_symbolic_schema()
        learning_run_id = str(uuid.uuid4())

        adj_where = ["adj.season = :season", "adj.week = :week"]
        sa_where = ["sa.season = :season", "sa.week = :week"]
        params: Dict[str, Any] = {"season": season, "week": week}
        if rule_run_id:
            adj_where.append("adj.rule_run_id = :rule_run_id")
            sa_where.append("sa.rule_run_id = :rule_run_id")
            params["rule_run_id"] = rule_run_id
        if slate:
            adj_where.append("(adj.slate = :slate OR adj.slate IS NULL)")
            sa_where.append("(sa.slate = :slate OR sa.slate IS NULL)")
            params["slate"] = slate

        adj_where_clause = " AND ".join(adj_where)
        sa_where_clause = " AND ".join(sa_where)

        try:
            with self.engine.begin() as conn:
                projections = pd.read_sql(
                    text(
                        f"""
                        SELECT
                            adj.rule_run_id,
                            adj.season,
                            adj.week,
                            adj.slate,
                            adj.player_id,
                            adj.player_display_name,
                            adj.position,
                            adj.recent_team,
                            adj.base_predicted_mean,
                            adj.base_predicted_p90,
                            adj.adjusted_mean,
                            adj.adjusted_p90,
                            rr.created_at AS data_cutoff_at,
                            actual.dk_total_points AS actual_points
                        FROM player_expected_points_adjusted adj
                        JOIN nfl_weekly_data_with_scores actual
                          ON actual.season = adj.season
                         AND actual.week = adj.week
                         AND actual.player_id = adj.player_id
                        LEFT JOIN symbolic_rule_runs rr
                          ON rr.rule_run_id = adj.rule_run_id
                        WHERE {adj_where_clause}
                        """
                    ),
                    conn,
                    params=params,
                )
                rule_rows = pd.read_sql(
                    text(
                        f"""
                        SELECT
                            sa.rule_run_id,
                            sa.rule_id,
                            sa.rule_name,
                            sr.version AS rule_version,
                            sa.season,
                            sa.week,
                            sa.slate,
                            sa.player_id,
                            adj.position,
                            adj.recent_team AS team,
                            sa.mean_before,
                            sa.mean_after,
                            sa.reason,
                            actual.dk_total_points AS actual_points
                        FROM symbolic_adjustments sa
                        JOIN nfl_weekly_data_with_scores actual
                          ON actual.season = sa.season
                         AND actual.week = sa.week
                         AND actual.player_id = sa.player_id
                        JOIN player_expected_points_adjusted adj
                          ON adj.rule_run_id = sa.rule_run_id
                         AND adj.player_id = sa.player_id
                        LEFT JOIN symbolic_rules sr
                          ON sr.rule_id = sa.rule_id
                        WHERE {sa_where_clause}
                        """
                    ),
                    conn,
                    params=params,
                )
        except Exception as exc:
            logger.warning("Could not evaluate symbolic learning run: %s", exc)
            return {
                "learning_run_id": learning_run_id,
                "status": "failed",
                "filters": {"season": season, "week": week, "rule_run_id": rule_run_id, "slate": slate},
                "overall": _empty_metrics(),
                "by_rule": [],
                "recommendations": [],
                "rows_written": {"projection_snapshots": 0, "rule_evaluations": 0, "learning_runs": 0},
                "message": f"Learning evaluation failed: {exc}",
            }

        overall = _metric_summary(projections, "base_predicted_mean", "adjusted_mean")
        by_rule: List[Dict[str, Any]] = []
        recommendations: List[Dict[str, Any]] = []
        if not rule_rows.empty:
            for (rid, rname), group in rule_rows.groupby(["rule_id", "rule_name"], dropna=False):
                summary = _metric_summary(group, "mean_before", "mean_after")
                summary.update({"rule_id": str(rid), "rule_name": str(rname)})
                by_rule.append(summary)
            by_rule = sorted(by_rule, key=lambda row: row["mae_delta"], reverse=True)
            recommendations = [_rule_recommendation(row) for row in by_rule]

        rules_improved = sum(1 for row in by_rule if float(row.get("mae_delta", 0.0) or 0.0) > 0)
        rules_worsened = sum(1 for row in by_rule if float(row.get("mae_delta", 0.0) or 0.0) < 0)
        snapshot_rows = 0
        eval_rows = 0
        learning_rows = 0

        rule_ids_by_snapshot: Dict[tuple[str, str], List[str]] = {}
        if not rule_rows.empty:
            for (run_id, player_id), group in rule_rows.groupby(["rule_run_id", "player_id"], dropna=False):
                rule_ids_by_snapshot[(str(run_id), str(player_id))] = [
                    str(rule_id) for rule_id in group["rule_id"].dropna().unique().tolist()
                ]

        with self.engine.begin() as conn:
            for _, row in projections.iterrows():
                run_id = str(row.get("rule_run_id"))
                player_id = str(row.get("player_id"))
                conn.execute(
                    text(
                        """
                        INSERT INTO symbolic_projection_snapshots
                        (rule_run_id, season, week, slate, game_id, player_id, model_version, rule_ids,
                         base_mean, adjusted_mean, base_p90, adjusted_p90, ownership_projection, data_cutoff_at)
                        VALUES
                        (:rule_run_id, :season, :week, :slate, :game_id, :player_id, :model_version, CAST(:rule_ids AS JSONB),
                         :base_mean, :adjusted_mean, :base_p90, :adjusted_p90, :ownership_projection, :data_cutoff_at)
                        ON CONFLICT (rule_run_id, player_id) DO UPDATE
                        SET
                            slate = EXCLUDED.slate,
                            rule_ids = EXCLUDED.rule_ids,
                            base_mean = EXCLUDED.base_mean,
                            adjusted_mean = EXCLUDED.adjusted_mean,
                            base_p90 = EXCLUDED.base_p90,
                            adjusted_p90 = EXCLUDED.adjusted_p90,
                            data_cutoff_at = EXCLUDED.data_cutoff_at
                        """
                    ),
                    {
                        "rule_run_id": run_id,
                        "season": int(row.get("season")),
                        "week": int(row.get("week")),
                        "slate": row.get("slate"),
                        "game_id": None,
                        "player_id": player_id,
                        "model_version": "player_expected_points",
                        "rule_ids": json.dumps(rule_ids_by_snapshot.get((run_id, player_id), [])),
                        "base_mean": float(row.get("base_predicted_mean") or 0.0),
                        "adjusted_mean": float(row.get("adjusted_mean") or 0.0),
                        "base_p90": float(row.get("base_predicted_p90") or 0.0),
                        "adjusted_p90": float(row.get("adjusted_p90") or 0.0),
                        "ownership_projection": None,
                        "data_cutoff_at": row.get("data_cutoff_at"),
                    },
                )
                snapshot_rows += 1

            for _, row in rule_rows.iterrows():
                mean_before = float(row.get("mean_before") or 0.0)
                mean_after = float(row.get("mean_after") or 0.0)
                actual_points = float(row.get("actual_points") or 0.0)
                mae_before = abs(mean_before - actual_points)
                mae_after = abs(mean_after - actual_points)
                conn.execute(
                    text(
                        """
                        INSERT INTO symbolic_rule_evaluations
                        (learning_run_id, rule_run_id, rule_id, rule_version, season, week, slate, player_id,
                         position, team, mean_before, mean_after, actual_points, mae_before, mae_after,
                         improved, delta_mae, reason)
                        VALUES
                        (:learning_run_id, :rule_run_id, :rule_id, :rule_version, :season, :week, :slate, :player_id,
                         :position, :team, :mean_before, :mean_after, :actual_points, :mae_before, :mae_after,
                         :improved, :delta_mae, :reason)
                        """
                    ),
                    {
                        "learning_run_id": learning_run_id,
                        "rule_run_id": str(row.get("rule_run_id")),
                        "rule_id": str(row.get("rule_id")),
                        "rule_version": int(row.get("rule_version") or 1),
                        "season": int(row.get("season")),
                        "week": int(row.get("week")),
                        "slate": row.get("slate"),
                        "player_id": str(row.get("player_id")),
                        "position": row.get("position"),
                        "team": row.get("team"),
                        "mean_before": mean_before,
                        "mean_after": mean_after,
                        "actual_points": actual_points,
                        "mae_before": mae_before,
                        "mae_after": mae_after,
                        "improved": mae_after < mae_before,
                        "delta_mae": mae_before - mae_after,
                        "reason": row.get("reason"),
                    },
                )
                eval_rows += 1

            conn.execute(
                text(
                    """
                    INSERT INTO symbolic_learning_runs
                    (learning_run_id, season, week, slate, rule_run_id, status, projections_evaluated,
                     rules_evaluated, rules_improved, rules_worsened, overall_base_mae,
                     overall_adjusted_mae, overall_mae_delta, overall_hit_rate, recommendations_json)
                    VALUES
                    (:learning_run_id, :season, :week, :slate, :rule_run_id, 'completed', :projections_evaluated,
                     :rules_evaluated, :rules_improved, :rules_worsened, :overall_base_mae,
                     :overall_adjusted_mae, :overall_mae_delta, :overall_hit_rate, CAST(:recommendations_json AS JSONB))
                    """
                ),
                {
                    "learning_run_id": learning_run_id,
                    "season": season,
                    "week": week,
                    "slate": slate,
                    "rule_run_id": rule_run_id,
                    "projections_evaluated": int(overall["rows"]),
                    "rules_evaluated": len(by_rule),
                    "rules_improved": rules_improved,
                    "rules_worsened": rules_worsened,
                    "overall_base_mae": float(overall["base_mae"]),
                    "overall_adjusted_mae": float(overall["adjusted_mae"]),
                    "overall_mae_delta": float(overall["mae_delta"]),
                    "overall_hit_rate": float(overall["hit_rate"]),
                    "recommendations_json": json.dumps(recommendations),
                },
            )
            learning_rows = 1

        return {
            "learning_run_id": learning_run_id,
            "status": "completed",
            "filters": {"season": season, "week": week, "rule_run_id": rule_run_id, "slate": slate},
            "overall": overall,
            "by_rule": by_rule,
            "recommendations": recommendations,
            "rows_written": {
                "projection_snapshots": snapshot_rows,
                "rule_evaluations": eval_rows,
                "learning_runs": learning_rows,
            },
            "message": (
                f"Evaluated {overall['rows']} projection snapshots and {eval_rows} rule applications "
                f"for season {season}, week {week}."
            ),
        }

    def _load_injuries(self, season: int, week: int) -> pd.DataFrame:
        try:
            with self.engine.begin() as conn:
                df = pd.read_sql(
                    text(
                        "SELECT player_id, first_name, last_name, injury_indicator, team "
                        "FROM weekly_injuries WHERE season = :season AND week = :week"
                    ),
                    conn,
                    params={"season": season, "week": week},
                )
        except Exception as exc:
            logger.warning("Could not load injuries for symbolic agent: %s", exc)
            return pd.DataFrame()
        if df.empty:
            return df
        df["player_id"] = df["player_id"].astype(str)
        df["name_norm"] = (
            (df["first_name"].astype(str) + " " + df["last_name"].astype(str))
            .str.lower()
            .str.strip()
            .map(_normalize_alias)
        )
        df["injury_indicator"] = df["injury_indicator"].fillna("").str.upper()
        return df

    def _load_matchups(self, season: int, week: int) -> pd.DataFrame:
        try:
            with self.engine.begin() as conn:
                df = pd.read_sql(
                    text(
                        "SELECT recent_team, opponent_team, pass_rate_neutral, proe_neutral, run_funnel, pass_funnel, "
                        "def_plays_allowed_per_g, off_plays_per_g "
                        "FROM predictive_features "
                        "WHERE season = :season AND week = :week"
                    ),
                    conn,
                    params={"season": season, "week": week},
                )
        except Exception as exc:
            logger.warning("Could not load matchups for symbolic agent: %s", exc)
            return pd.DataFrame()
        if df.empty:
            return df
        return df.drop_duplicates("recent_team")

    def _load_projections(
        self,
        season: int,
        week: int,
        slate: str | None = None,
        projection_run_id: str | None = None,
    ) -> pd.DataFrame:
        try:
            from .predictions import PredictionsService

            predictions_service = PredictionsService.__new__(PredictionsService)
            predictions_service.engine = self.engine
            df = pd.DataFrame(
                predictions_service.fetch_predictions(
                    season=season,
                    week=week,
                    limit=10000,
                    slate=slate,
                    projection_run_id=projection_run_id,
                )
            )
        except Exception as exc:
            logger.warning("Could not load projections for symbolic agent: %s", exc)
            return pd.DataFrame()
        if df.empty:
            return df
        df["player_id"] = df["player_id"].astype(str)
        df["name_norm"] = (
            df["player_display_name"].astype(str).str.lower().str.strip().map(_normalize_alias)
        )
        df["orig_mean"] = pd.to_numeric(df["predicted_mean"], errors="coerce").fillna(0.0)
        df["orig_p90"] = pd.to_numeric(df["predicted_p90"], errors="coerce").fillna(0.0)
        df["predicted_mean"] = df["orig_mean"]
        df["predicted_p90"] = df["orig_p90"]
        df["slate"] = slate
        return df

    def _indicator_matches(self, indicator: str, candidates: List[str], mode: str) -> bool:
        if not indicator:
            return False
        indicator = indicator.upper().strip()
        if not candidates:
            return False
        normalized = [str(token).upper().strip() for token in candidates]
        if mode == "exact":
            return indicator in normalized
        return any(indicator == token or indicator.startswith(token) for token in normalized)

    def _evaluate_injury_rule(
        self, rule: SymbolicRule, indicator: str
    ) -> Tuple[bool, float, float, str]:
        cond = rule.condition_json
        action = rule.action_json
        tokens = cond.get("indicators", [])
        mode = str(cond.get("match_mode", "prefix_or_exact")).lower()
        if not self._indicator_matches(indicator=indicator, candidates=tokens, mode=mode):
            return False, 1.0, 1.0, ""
        mean_mult = float(action.get("mean_multiplier", 1.0) or 1.0)
        p90_mult = float(action.get("p90_multiplier", mean_mult) or mean_mult)
        reason = str(action.get("reason", rule.rule_name))
        return True, mean_mult, p90_mult, reason

    def _evaluate_matchup_rule(
        self, rule: SymbolicRule, position: str, context: Dict[str, Any]
    ) -> Tuple[bool, float, float, str]:
        cond = rule.condition_json
        action = rule.action_json

        allowed_positions = [str(p).upper() for p in cond.get("positions", [])]
        pos = str(position or "").upper()
        if allowed_positions and pos not in allowed_positions:
            return False, 1.0, 1.0, ""

        pass_funnel = float(context.get("pass_funnel", 0) or 0)
        pace = float(context.get("off_plays_per_g", 0) or 0) + float(
            context.get("def_plays_allowed_per_g", 0) or 0
        )

        pass_funnel_gt = (
            float(cond["pass_funnel_gt"]) if "pass_funnel_gt" in cond else None
        )
        or_pace_gt = float(cond["or_pace_gt"]) if "or_pace_gt" in cond else None

        if pass_funnel_gt is not None and or_pace_gt is None and not (pass_funnel > pass_funnel_gt):
            return False, 1.0, 1.0, ""
        if "pass_funnel_lt" in cond and not (pass_funnel < float(cond["pass_funnel_lt"])):
            return False, 1.0, 1.0, ""
        if "pace_gt" in cond and not (pace > float(cond["pace_gt"])):
            return False, 1.0, 1.0, ""
        if "pace_lt" in cond and not (pace < float(cond["pace_lt"])):
            return False, 1.0, 1.0, ""
        if or_pace_gt is not None:
            pace_gt = pace > or_pace_gt
            funnel_gt = pass_funnel_gt is not None and pass_funnel > pass_funnel_gt
            if not (pace_gt or funnel_gt):
                return False, 1.0, 1.0, ""

        mean_mult = float(action.get("mean_multiplier", 1.0) or 1.0)
        p90_mult = float(action.get("p90_multiplier", mean_mult) or mean_mult)
        reason = str(action.get("reason", rule.rule_name))
        return True, mean_mult, p90_mult, reason

    def _persist_target_symbolic_run(
        self,
        *,
        rule_run_id: str,
        projection_run_id: str | None,
        season: int,
        week: int,
        slate: str | None,
        rules_loaded: int,
        rules_applied: int,
        traces: List[AgentTrace],
        proj: pd.DataFrame,
        adjust_reasons: Dict[str, List[str]],
        rule_versions: Dict[str, int],
    ) -> bool:
        if not projection_run_id:
            logger.warning("Skipping target symbolic lineage because projection_run_id is unavailable")
            return False
        validate_target_schema(
            self.engine,
            consumer=type(self).__name__,
            required_tables=(
                "symbolic_rule_run",
                "symbolic_rule_application",
                "symbolic_adjusted_projection",
            ),
        )
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO target.symbolic_rule_run
                            (rule_run_id, projection_run_id, rules_loaded, rules_applied, status)
                        VALUES
                            (:rule_run_id, :projection_run_id, :rules_loaded, :rules_applied, 'completed')
                        """
                    ),
                    {
                        "rule_run_id": rule_run_id,
                        "projection_run_id": projection_run_id,
                        "rules_loaded": rules_loaded,
                        "rules_applied": rules_applied,
                    },
                )

                proj_by_player = {
                    str(row.get("player_id")): row for _, row in proj.iterrows()
                }
                application_rows = []
                for trace in traces:
                    player = proj_by_player.get(str(trace.player_id), {})
                    application_rows.append(
                        {
                            "rule_run_id": rule_run_id,
                            "rule_id": trace.rule_id,
                            "rule_version": rule_versions.get(trace.rule_id),
                            "projection_run_id": projection_run_id,
                            "player_id": trace.player_id,
                            "condition_context_json": json.dumps(
                                {
                                    "season": season,
                                    "week": week,
                                    "slate": slate,
                                    "game_id": _optional_text(player.get("game_id")),
                                },
                                sort_keys=True,
                            ),
                            "mean_before": trace.mean_before,
                            "mean_after": trace.mean_after,
                            "p90_before": trace.p90_before,
                            "p90_after": trace.p90_after,
                            "delta_mean": trace.mean_after - trace.mean_before,
                            "delta_p90": trace.p90_after - trace.p90_before,
                            "reason": trace.reason,
                        }
                    )
                if application_rows:
                    conn.execute(
                        text(
                            """
                            INSERT INTO target.symbolic_rule_application
                                (rule_run_id, rule_id, rule_version, projection_run_id,
                                 player_id, condition_context_json, mean_before, mean_after,
                                 p90_before, p90_after, delta_mean, delta_p90, reason)
                            VALUES
                                (:rule_run_id, :rule_id, :rule_version, :projection_run_id,
                                 :player_id, CAST(:condition_context_json AS JSONB),
                                 :mean_before, :mean_after, :p90_before, :p90_after,
                                 :delta_mean, :delta_p90, :reason)
                            """
                        ),
                        application_rows,
                    )

                adjusted_rows = []
                for _, row in proj.iterrows():
                    player_id = str(row.get("player_id"))
                    game_id = _optional_text(row.get("game_id"))
                    if game_id is None:
                        game_id = f"{season}_{week:02d}_unknown_{player_id}"
                    reasons = list(dict.fromkeys(adjust_reasons.get(player_id, [])))
                    adjusted_rows.append(
                        {
                            "rule_run_id": rule_run_id,
                            "projection_run_id": projection_run_id,
                            "season": season,
                            "week": week,
                            "game_id": game_id,
                            "slate_id": slate or _optional_text(row.get("slate")),
                            "player_id": player_id,
                            "base_mean": _safe_number(row.get("orig_mean")),
                            "adjusted_mean": _safe_number(row.get("predicted_mean")),
                            "base_p90": _safe_number(row.get("orig_p90")),
                            "adjusted_p90": _safe_number(row.get("predicted_p90")),
                            "reason_json": json.dumps(reasons),
                        }
                    )
                if adjusted_rows:
                    conn.execute(
                        text(
                            """
                            INSERT INTO target.symbolic_adjusted_projection
                                (rule_run_id, projection_run_id, season, week, game_id,
                                 slate_id, player_id, base_mean, adjusted_mean, base_p90,
                                 adjusted_p90, reason_json)
                            VALUES
                                (:rule_run_id, :projection_run_id, :season, :week, :game_id,
                                 :slate_id, :player_id, :base_mean, :adjusted_mean, :base_p90,
                                 :adjusted_p90, CAST(:reason_json AS JSONB))
                            """
                        ),
                        adjusted_rows,
                    )
            return True
        except Exception as exc:  # noqa: BLE001 - retain legacy symbolic output if target persistence fails
            logger.warning("Failed to persist target symbolic lineage: %s", exc)
            return False

    def _persist_rule_run(
        self,
        rule_run_id: str,
        season: int,
        week: int,
        rules_loaded: int,
        projections_seen: int,
        projections_adjusted: int,
        traces: List[AgentTrace],
        proj: pd.DataFrame,
        adjust_reasons: Dict[str, List[str]],
        projection_run_id: str | None = None,
        slate: str | None = None,
        rule_versions: Dict[str, int] | None = None,
    ) -> bool:
        self._ensure_symbolic_schema()
        rules_applied = len({trace.rule_id for trace in traces})
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO symbolic_rule_runs
                    (rule_run_id, season, week, slate, rules_loaded, rules_applied, projections_seen, projections_adjusted, status)
                    VALUES
                    (:rule_run_id, :season, :week, :slate, :rules_loaded, :rules_applied, :projections_seen, :projections_adjusted, 'completed')
                    """
                ),
                {
                    "rule_run_id": rule_run_id,
                    "season": season,
                    "week": week,
                    "slate": slate,
                    "rules_loaded": rules_loaded,
                    "rules_applied": rules_applied,
                    "projections_seen": projections_seen,
                    "projections_adjusted": projections_adjusted,
                },
            )
            for trace in traces:
                conn.execute(
                    text(
                        """
                        INSERT INTO symbolic_adjustments
                        (rule_run_id, season, week, slate, player_id, rule_id, rule_name, reason, mean_before, mean_after, p90_before, p90_after, delta_mean, delta_p90)
                        VALUES
                        (:rule_run_id, :season, :week, :slate, :player_id, :rule_id, :rule_name, :reason, :mean_before, :mean_after, :p90_before, :p90_after, :delta_mean, :delta_p90)
                        """
                    ),
                    {
                        "rule_run_id": rule_run_id,
                        "season": season,
                        "week": week,
                        "slate": slate,
                        "player_id": trace.player_id,
                        "rule_id": trace.rule_id,
                        "rule_name": trace.rule_name,
                        "reason": trace.reason,
                        "mean_before": trace.mean_before,
                        "mean_after": trace.mean_after,
                        "p90_before": trace.p90_before,
                        "p90_after": trace.p90_after,
                        "delta_mean": trace.mean_after - trace.mean_before,
                        "delta_p90": trace.p90_after - trace.p90_before,
                    },
                )
            for _, row in proj.iterrows():
                pid = str(row["player_id"])
                orig_mean = float(row.get("orig_mean", 0.0) or 0.0)
                orig_p90 = float(row.get("orig_p90", 0.0) or 0.0)
                adjusted_mean = float(row.get("predicted_mean", 0.0) or 0.0)
                adjusted_p90 = float(row.get("predicted_p90", 0.0) or 0.0)
                reasons = list(dict.fromkeys(adjust_reasons.get(pid, [])))
                conn.execute(
                    text(
                        """
                        INSERT INTO player_expected_points_adjusted
                        (rule_run_id, season, week, slate, player_id, player_display_name, position, recent_team, opponent_team,
                         base_predicted_mean, base_predicted_p90, adjusted_mean, adjusted_p90, reason, reasons)
                        VALUES
                        (:rule_run_id, :season, :week, :slate, :player_id, :player_display_name, :position, :recent_team, :opponent_team,
                         :base_predicted_mean, :base_predicted_p90, :adjusted_mean, :adjusted_p90, :reason, CAST(:reasons AS JSONB))
                        """
                    ),
                    {
                        "rule_run_id": rule_run_id,
                        "season": season,
                        "week": week,
                        "slate": row.get("slate") if "slate" in proj.columns else None,
                        "player_id": pid,
                        "player_display_name": row.get("player_display_name"),
                        "position": row.get("position"),
                        "recent_team": row.get("recent_team"),
                        "opponent_team": row.get("opponent_team"),
                        "base_predicted_mean": orig_mean,
                        "base_predicted_p90": orig_p90,
                        "adjusted_mean": adjusted_mean,
                        "adjusted_p90": adjusted_p90,
                        "reason": "; ".join(reasons),
                        "reasons": json.dumps(reasons),
                    },
                )
        return self._persist_target_symbolic_run(
            rule_run_id=rule_run_id,
            projection_run_id=projection_run_id,
            season=season,
            week=week,
            slate=slate,
            rules_loaded=rules_loaded,
            rules_applied=rules_applied,
            traces=traces,
            proj=proj,
            adjust_reasons=adjust_reasons,
            rule_versions=rule_versions or {},
        )

    def run(
        self,
        season: int,
        week: int,
        slate: str | None = None,
        projection_run_id: str | None = None,
    ) -> Tuple[pd.DataFrame, List[AgentAdjustment], AgentConfig, List[AgentTrace]]:
        rules = self._load_rules()
        injuries = self._load_injuries(season, week)
        matchups = self._load_matchups(season, week)
        proj = self._load_projections(
            season,
            week,
            slate=slate,
            projection_run_id=projection_run_id,
        )
        if slate and not proj.empty and "slate" in proj.columns:
            proj = proj[(proj["slate"] == slate) | proj["slate"].isna()].copy()
        if projection_run_id is None and not proj.empty and "projection_run_id" in proj.columns:
            run_ids = proj["projection_run_id"].dropna().astype(str).unique().tolist()
            if run_ids:
                projection_run_id = run_ids[0]
        rule_run_id = str(uuid.uuid4())
        config = AgentConfig(
            rules_source=self.config.rules_source,
            rules_loaded=len(rules),
            rule_run_id=rule_run_id,
            projection_run_id=projection_run_id,
            max_chalk=self.config.max_chalk,
            min_leverage=self.config.min_leverage,
            max_total_ownership=self.config.max_total_ownership,
        )

        if proj.empty:
            return proj, [], config, []

        adjustments: List[AgentAdjustment] = []
        traces: List[AgentTrace] = []
        adjust_reasons: Dict[str, List[str]] = {}
        injury_map = (
            injuries.set_index("player_id")["injury_indicator"].to_dict()
            if not injuries.empty
            else {}
        )
        matchup_map = (
            matchups.set_index("recent_team").to_dict(orient="index")
            if not matchups.empty
            else {}
        )

        for idx, row in proj.iterrows():
            pid = str(row["player_id"])
            position = str(row.get("position", "") or "")
            team = row.get("recent_team")
            indicator = str(injury_map.get(pid, "") or "").upper()
            context = matchup_map.get(team, {}) if team else {}

            for rule in rules:
                apply = False
                mean_mult = 1.0
                p90_mult = 1.0
                reason = ""

                if rule.rule_type == "injury":
                    apply, mean_mult, p90_mult, reason = self._evaluate_injury_rule(
                        rule, indicator=indicator
                    )
                elif rule.rule_type == "matchup":
                    apply, mean_mult, p90_mult, reason = self._evaluate_matchup_rule(
                        rule, position=position, context=context
                    )

                if not apply:
                    continue

                mean_before = float(proj.at[idx, "predicted_mean"] or 0.0)
                p90_before = float(proj.at[idx, "predicted_p90"] or 0.0)
                mean_after = mean_before * mean_mult
                p90_after = p90_before * p90_mult
                proj.at[idx, "predicted_mean"] = mean_after
                proj.at[idx, "predicted_p90"] = p90_after

                adjust_reasons.setdefault(pid, []).append(reason)
                traces.append(
                    AgentTrace(
                        player_id=pid,
                        rule_run_id=rule_run_id,
                        rule_id=rule.rule_id,
                        rule_name=rule.rule_name,
                        reason=reason,
                        mean_before=mean_before,
                        mean_after=mean_after,
                        p90_before=p90_before,
                        p90_after=p90_after,
                        mean_multiplier=mean_mult,
                        p90_multiplier=p90_mult,
                    )
                )

        adjusted_player_ids = {
            str(row["player_id"])
            for _, row in proj.iterrows()
            if abs(float(row.get("predicted_mean", 0.0) or 0.0) - float(row.get("orig_mean", 0.0) or 0.0)) > 1e-9
            or abs(float(row.get("predicted_p90", 0.0) or 0.0) - float(row.get("orig_p90", 0.0) or 0.0)) > 1e-9
        }
        target_persisted = self._persist_rule_run(
            rule_run_id=rule_run_id,
            season=season,
            week=week,
            rules_loaded=len(rules),
            projections_seen=len(proj),
            projections_adjusted=len(adjusted_player_ids),
            traces=traces,
            proj=proj,
            adjust_reasons=adjust_reasons,
            projection_run_id=projection_run_id,
            slate=slate,
            rule_versions={rule.rule_id: rule.version for rule in rules},
        )
        config.target_persisted = bool(target_persisted)

        for _, row in proj.iterrows():
            pid = str(row["player_id"])
            orig_mean = float(row.get("orig_mean", 0.0) or 0.0)
            orig_p90 = float(row.get("orig_p90", 0.0) or 0.0)
            new_mean = float(row.get("predicted_mean", 0.0) or 0.0)
            new_p90 = float(row.get("predicted_p90", 0.0) or 0.0)
            changed = abs(new_mean - orig_mean) > 1e-9 or abs(new_p90 - orig_p90) > 1e-9
            if not changed:
                continue
            proj_delta = (new_mean - orig_mean) / orig_mean if orig_mean else new_mean
            ceil_delta = (new_p90 - orig_p90) / orig_p90 if orig_p90 else new_p90
            reasons = adjust_reasons.get(pid, [])
            reason = "; ".join(dict.fromkeys(reasons)) if reasons else "auto-adjust"
            adjustments.append(
                AgentAdjustment(
                    player_id=pid,
                    reason=reason,
                    projection_delta=proj_delta,
                    ceiling_delta=ceil_delta,
                )
            )

        return proj, adjustments, config, traces
