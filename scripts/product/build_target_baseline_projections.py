#!/usr/bin/env python3
"""Build leakage-safe baseline target.player_projection rows from prior actuals."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.product.apply_target_schema_adapters import create_target_schema_sql, qident


MODEL_ID = "baseline_rolling_dk_v0"


@dataclass
class BuildResult:
    status: str
    feature_runs: int = 0
    feature_rows: int = 0
    model_runs: int = 0
    projection_rows: int = 0
    dst_projection_rows: int = 0
    message: str = ""


def build_connection_url(args: argparse.Namespace) -> URL:
    database = args.database or os.getenv("PGDATABASE")
    if not database:
        raise RuntimeError("Database is required. Pass --database or set PGDATABASE.")
    return URL.create(
        drivername="postgresql",
        username=args.user or os.getenv("PGUSER"),
        password=args.password or os.getenv("PGPASSWORD"),
        host=args.host or os.getenv("PGHOST", "localhost"),
        port=int(args.port or os.getenv("PGPORT", "5432")),
        database=database,
    )


def filters_sql(season: int | None, week: int | None, alias: str = "actual") -> tuple[str, dict[str, Any]]:
    clauses = []
    params: dict[str, Any] = {}
    if season is not None:
        clauses.append(f"{alias}.season = :season")
        params["season"] = season
    if week is not None:
        clauses.append(f"{alias}.week = :week")
        params["week"] = week
    return (" AND " + " AND ".join(clauses) if clauses else ""), params


def count_candidate_rows(conn, target_schema: str, season: int | None, week: int | None) -> int:
    extra_filter, params = filters_sql(season, week)
    return int(
        conn.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM {qident(target_schema)}.fact_player_game_actual actual
                WHERE actual.dk_points IS NOT NULL
                {extra_filter}
                """
            ),
            params,
        ).scalar()
        or 0
    )


def build_baseline_projections(
    engine,
    target_schema: str = "target",
    season: int | None = None,
    week: int | None = None,
    dry_run: bool = False,
) -> BuildResult:
    s = qident(target_schema)
    extra_filter, params = filters_sql(season, week)

    with engine.begin() as conn:
        for statement in create_target_schema_sql(target_schema):
            conn.execute(text(statement))
        candidate_rows = count_candidate_rows(conn, target_schema, season, week)
        if dry_run:
            return BuildResult(status="would_build", projection_rows=candidate_rows)

        conn.execute(
            text(
                f"""
                INSERT INTO {s}.model_registry
                (model_id, model_name, model_version, trained_on_start, trained_on_end, feature_set_hash, metrics_json, artifact_uri)
                VALUES
                (:model_id, 'Rolling DK baseline + DST context', 'v0+dst-v1', 'prior available games', 'current row excluded',
                 'rolling_player_position_history_v0+dst_context_v1', '{{}}'::jsonb, NULL)
                ON CONFLICT (model_id) DO UPDATE SET
                    model_name = EXCLUDED.model_name,
                    model_version = EXCLUDED.model_version,
                    metrics_json = EXCLUDED.metrics_json
                """
            ),
            {"model_id": MODEL_ID},
        )

        feature_runs = conn.execute(
            text(
                f"""
                WITH weeks AS (
                    SELECT DISTINCT season, week
                    FROM {s}.fact_player_game_actual actual
                    WHERE actual.dk_points IS NOT NULL
                    {extra_filter}
                )
                INSERT INTO {s}.feature_generation_run
                (feature_run_id, training_cutoff, source_versions_json, feature_set_hash, status)
                SELECT
                    :model_id || ':features:' || season::text || ':' || week::text,
                    NULL::timestamptz,
                    jsonb_build_object('source', 'target.fact_player_game_actual', 'leakage_policy', 'prior_games_only'),
                    'rolling_player_position_history_v0+dst_context_v1',
                    'completed'
                FROM weeks
                ON CONFLICT (feature_run_id) DO UPDATE SET
                    source_versions_json = EXCLUDED.source_versions_json,
                    feature_set_hash = EXCLUDED.feature_set_hash,
                    status = EXCLUDED.status
                """
            ),
            {**params, "model_id": MODEL_ID},
        ).rowcount or 0

        model_runs = conn.execute(
            text(
                f"""
                WITH weeks AS (
                    SELECT DISTINCT season, week
                    FROM {s}.fact_player_game_actual actual
                    WHERE actual.dk_points IS NOT NULL
                    {extra_filter}
                )
                INSERT INTO {s}.model_run
                (model_run_id, model_id, feature_run_id, data_cutoff_at, params_json, status)
                SELECT
                    :model_id || ':run:' || season::text || ':' || week::text,
                    :model_id,
                    :model_id || ':features:' || season::text || ':' || week::text,
                    NULL::timestamptz,
                    jsonb_build_object(
                        'method', 'prior_player_avg_fallback_prior_position_avg',
                        'dst_method', 'dst_context_v1',
                        'dst_inputs', jsonb_build_array(
                            'defense_recent_components', 'opponent_recent_allowed_components',
                            'vegas_opponent_implied_points', 'empirical_dst_ranges'
                        )
                    ),
                    'completed'
                FROM weeks
                ON CONFLICT (model_run_id) DO UPDATE SET
                    feature_run_id = EXCLUDED.feature_run_id,
                    params_json = EXCLUDED.params_json,
                    status = EXCLUDED.status
                """
            ),
            {**params, "model_id": MODEL_ID},
        ).rowcount or 0

        feature_rows = conn.execute(
            text(
                f"""
                WITH current_rows AS (
                    SELECT actual.*
                    FROM {s}.fact_player_game_actual actual
                    WHERE actual.dk_points IS NOT NULL
                    {extra_filter}
                )
                INSERT INTO {s}.feature_player_game
                (feature_run_id, season, week, game_id, player_id, feature_json)
                SELECT
                    :model_id || ':features:' || cur.season::text || ':' || cur.week::text,
                    cur.season,
                    cur.week,
                    cur.game_id,
                    cur.player_id,
                    jsonb_build_object(
                        'player_prior_games', COALESCE(player_hist.games, 0),
                        'player_prior_avg', player_hist.avg_points,
                        'position_prior_games', COALESCE(position_hist.games, 0),
                        'position_prior_avg', position_hist.avg_points,
                        'leakage_policy', 'history where season/week is strictly before target row'
                    )
                FROM current_rows cur
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS games, AVG(hist.dk_points) AS avg_points
                    FROM {s}.fact_player_game_actual hist
                    WHERE hist.player_id = cur.player_id
                      AND hist.dk_points IS NOT NULL
                      AND (hist.season < cur.season OR (hist.season = cur.season AND hist.week < cur.week))
                ) player_hist ON TRUE
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS games, AVG(hist.dk_points) AS avg_points
                    FROM {s}.fact_player_game_actual hist
                    WHERE hist.position = cur.position
                      AND hist.dk_points IS NOT NULL
                      AND (hist.season < cur.season OR (hist.season = cur.season AND hist.week < cur.week))
                ) position_hist ON TRUE
                ON CONFLICT (feature_run_id, season, week, game_id, player_id) DO UPDATE SET
                    feature_json = EXCLUDED.feature_json
                """
            ),
            {**params, "model_id": MODEL_ID},
        ).rowcount or 0

        conn.execute(
            text(
                f"""
                WITH current_dst AS (
                    SELECT actual.*
                    FROM {s}.fact_dst_game_actual actual
                    WHERE actual.dk_points IS NOT NULL
                    {extra_filter}
                ),
                enriched AS (
                    SELECT
                        cur.*,
                        defense_recent.games AS defense_recent_games,
                        defense_recent.avg_dk_points AS defense_recent_dk_points,
                        defense_recent.avg_sacks AS defense_recent_sacks,
                        defense_recent.avg_interceptions AS defense_recent_interceptions,
                        defense_recent.avg_fumble_recoveries AS defense_recent_fumble_recoveries,
                        defense_recent.avg_touchdowns AS defense_recent_touchdowns,
                        opponent_recent.games AS opponent_recent_games,
                        opponent_recent.avg_dk_points AS opponent_recent_dst_points_allowed,
                        opponent_recent.avg_sacks AS opponent_recent_sacks_allowed,
                        opponent_recent.avg_interceptions AS opponent_recent_interceptions_allowed,
                        opponent_recent.avg_fumble_recoveries AS opponent_recent_fumble_recoveries_allowed,
                        opponent_recent.avg_touchdowns AS opponent_recent_dst_touchdowns_allowed
                    FROM current_dst cur
                    LEFT JOIN LATERAL (
                        SELECT
                            COUNT(*) AS games,
                            AVG(recent.dk_points) AS avg_dk_points,
                            AVG(recent.sacks) AS avg_sacks,
                            AVG(recent.interceptions) AS avg_interceptions,
                            AVG(recent.fumble_recoveries) AS avg_fumble_recoveries,
                            AVG(
                                recent.interception_return_tds
                                + recent.fumble_return_tds
                                + recent.special_teams_tds
                            ) AS avg_touchdowns
                        FROM (
                            SELECT hist.*
                            FROM {s}.fact_dst_game_actual hist
                            WHERE hist.player_id = cur.player_id
                              AND (hist.season < cur.season OR (hist.season = cur.season AND hist.week < cur.week))
                            ORDER BY hist.season DESC, hist.week DESC
                            LIMIT 8
                        ) recent
                    ) defense_recent ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT
                            COUNT(*) AS games,
                            AVG(recent.dk_points) AS avg_dk_points,
                            AVG(recent.sacks) AS avg_sacks,
                            AVG(recent.interceptions) AS avg_interceptions,
                            AVG(recent.fumble_recoveries) AS avg_fumble_recoveries,
                            AVG(
                                recent.interception_return_tds
                                + recent.fumble_return_tds
                                + recent.special_teams_tds
                            ) AS avg_touchdowns
                        FROM (
                            SELECT hist.*
                            FROM {s}.fact_dst_game_actual hist
                            WHERE hist.opponent_team_id = cur.opponent_team_id
                              AND (hist.season < cur.season OR (hist.season = cur.season AND hist.week < cur.week))
                            ORDER BY hist.season DESC, hist.week DESC
                            LIMIT 8
                        ) recent
                    ) opponent_recent ON TRUE
                )
                UPDATE {s}.feature_player_game feature
                SET feature_json = feature.feature_json || jsonb_strip_nulls(jsonb_build_object(
                    'dst_model', 'dst_context_v1',
                    'training_window_games', 8,
                    'defense_recent_games', enriched.defense_recent_games,
                    'defense_recent_dk_points', enriched.defense_recent_dk_points,
                    'defense_recent_sacks', enriched.defense_recent_sacks,
                    'defense_recent_interceptions', enriched.defense_recent_interceptions,
                    'defense_recent_fumble_recoveries', enriched.defense_recent_fumble_recoveries,
                    'defense_recent_touchdowns', enriched.defense_recent_touchdowns,
                    'opponent_recent_games', enriched.opponent_recent_games,
                    'opponent_recent_dst_points_allowed', enriched.opponent_recent_dst_points_allowed,
                    'opponent_recent_sacks_allowed', enriched.opponent_recent_sacks_allowed,
                    'opponent_recent_interceptions_allowed', enriched.opponent_recent_interceptions_allowed,
                    'opponent_recent_fumble_recoveries_allowed', enriched.opponent_recent_fumble_recoveries_allowed,
                    'opponent_recent_dst_touchdowns_allowed', enriched.opponent_recent_dst_touchdowns_allowed,
                    'opponent_implied_points', enriched.opponent_implied_points,
                    'is_home', enriched.is_home,
                    'leakage_policy_dst', 'strictly prior games; current Vegas context only'
                ))
                FROM enriched
                WHERE feature.feature_run_id = :model_id || ':features:' || enriched.season::text || ':' || enriched.week::text
                  AND feature.season = enriched.season
                  AND feature.week = enriched.week
                  AND feature.game_id = enriched.game_id
                  AND feature.player_id = enriched.player_id
                """
            ),
            {**params, "model_id": MODEL_ID},
        )

        projection_rows = conn.execute(
            text(
                f"""
                WITH current_rows AS (
                    SELECT actual.*
                    FROM {s}.fact_player_game_actual actual
                    WHERE actual.dk_points IS NOT NULL
                    {extra_filter}
                )
                INSERT INTO {s}.player_projection
                (projection_run_id, model_run_id, season, week, game_id, slate_id, player_id,
                 mean, median, p10, p25, p75, p90, stddev, ceiling_prob, data_cutoff_at)
                SELECT
                    :model_id || ':projection:' || cur.season::text || ':' || cur.week::text,
                    :model_id || ':run:' || cur.season::text || ':' || cur.week::text,
                    cur.season,
                    cur.week,
                    cur.game_id,
                    NULL::text,
                    cur.player_id,
                    COALESCE(player_hist.avg_points, position_hist.avg_points, 0.0),
                    COALESCE(player_hist.p50, position_hist.p50, player_hist.avg_points, position_hist.avg_points, 0.0),
                    COALESCE(player_hist.p10, position_hist.p10, 0.0),
                    COALESCE(player_hist.p25, position_hist.p25, 0.0),
                    COALESCE(player_hist.p75, position_hist.p75, player_hist.avg_points, position_hist.avg_points, 0.0),
                    COALESCE(player_hist.p90, position_hist.p90, player_hist.avg_points, position_hist.avg_points, 0.0),
                    COALESCE(player_hist.stddev_points, position_hist.stddev_points, 0.0),
                    CASE
                        WHEN COALESCE(player_hist.p90, position_hist.p90, 0.0) >= 20.0 THEN 1.0
                        ELSE 0.0
                    END,
                    NULL::timestamptz
                FROM current_rows cur
                LEFT JOIN LATERAL (
                    SELECT
                        COUNT(*) AS games,
                        AVG(hist.dk_points) AS avg_points,
                        STDDEV_POP(hist.dk_points) AS stddev_points,
                        percentile_cont(0.10) WITHIN GROUP (ORDER BY hist.dk_points) AS p10,
                        percentile_cont(0.25) WITHIN GROUP (ORDER BY hist.dk_points) AS p25,
                        percentile_cont(0.50) WITHIN GROUP (ORDER BY hist.dk_points) AS p50,
                        percentile_cont(0.75) WITHIN GROUP (ORDER BY hist.dk_points) AS p75,
                        percentile_cont(0.90) WITHIN GROUP (ORDER BY hist.dk_points) AS p90
                    FROM {s}.fact_player_game_actual hist
                    WHERE hist.player_id = cur.player_id
                      AND hist.dk_points IS NOT NULL
                      AND (hist.season < cur.season OR (hist.season = cur.season AND hist.week < cur.week))
                ) player_hist ON TRUE
                LEFT JOIN LATERAL (
                    SELECT
                        COUNT(*) AS games,
                        AVG(hist.dk_points) AS avg_points,
                        STDDEV_POP(hist.dk_points) AS stddev_points,
                        percentile_cont(0.10) WITHIN GROUP (ORDER BY hist.dk_points) AS p10,
                        percentile_cont(0.25) WITHIN GROUP (ORDER BY hist.dk_points) AS p25,
                        percentile_cont(0.50) WITHIN GROUP (ORDER BY hist.dk_points) AS p50,
                        percentile_cont(0.75) WITHIN GROUP (ORDER BY hist.dk_points) AS p75,
                        percentile_cont(0.90) WITHIN GROUP (ORDER BY hist.dk_points) AS p90
                    FROM {s}.fact_player_game_actual hist
                    WHERE hist.position = cur.position
                      AND hist.dk_points IS NOT NULL
                      AND (hist.season < cur.season OR (hist.season = cur.season AND hist.week < cur.week))
                ) position_hist ON TRUE
                ON CONFLICT (projection_run_id, game_id, player_id) DO UPDATE SET
                    mean = EXCLUDED.mean,
                    median = EXCLUDED.median,
                    p10 = EXCLUDED.p10,
                    p25 = EXCLUDED.p25,
                    p75 = EXCLUDED.p75,
                    p90 = EXCLUDED.p90,
                    stddev = EXCLUDED.stddev,
                    ceiling_prob = EXCLUDED.ceiling_prob,
                    data_cutoff_at = EXCLUDED.data_cutoff_at
                """
            ),
            {**params, "model_id": MODEL_ID},
        ).rowcount or 0

        dst_projection_rows = conn.execute(
            text(
                f"""
                WITH current_dst AS (
                    SELECT actual.*
                    FROM {s}.fact_dst_game_actual actual
                    WHERE actual.dk_points IS NOT NULL
                    {extra_filter}
                ),
                enriched AS (
                    SELECT
                        cur.*,
                        defense_recent.games AS defense_games,
                        defense_recent.avg_points AS defense_avg_points,
                        defense_recent.stddev_points AS defense_stddev,
                        defense_recent.p10 AS defense_p10,
                        defense_recent.p25 AS defense_p25,
                        defense_recent.p75 AS defense_p75,
                        defense_recent.p90 AS defense_p90,
                        defense_recent.ceiling_rate AS defense_ceiling_rate,
                        defense_recent.avg_sacks AS defense_sacks,
                        defense_recent.avg_interceptions AS defense_interceptions,
                        defense_recent.avg_fumble_recoveries AS defense_fumble_recoveries,
                        defense_recent.avg_safeties AS defense_safeties,
                        defense_recent.avg_touchdowns AS defense_touchdowns,
                        defense_recent.avg_blocked_kicks AS defense_blocked_kicks,
                        defense_recent.avg_points_allowed_score AS defense_points_allowed_score,
                        opponent_recent.games AS opponent_games,
                        opponent_recent.avg_points AS opponent_avg_points,
                        opponent_recent.avg_sacks AS opponent_sacks_allowed,
                        opponent_recent.avg_interceptions AS opponent_interceptions_allowed,
                        opponent_recent.avg_fumble_recoveries AS opponent_fumble_recoveries_allowed,
                        opponent_recent.avg_safeties AS opponent_safeties_allowed,
                        opponent_recent.avg_touchdowns AS opponent_touchdowns_allowed,
                        opponent_recent.avg_blocked_kicks AS opponent_blocked_kicks_allowed,
                        opponent_recent.avg_points_allowed_score AS opponent_points_allowed_score,
                        opponent_recent.ceiling_rate AS opponent_ceiling_rate,
                        league_recent.avg_points AS league_avg_points,
                        league_recent.stddev_points AS league_stddev,
                        league_recent.p10 AS league_p10,
                        league_recent.p25 AS league_p25,
                        league_recent.p75 AS league_p75,
                        league_recent.p90 AS league_p90,
                        league_recent.ceiling_rate AS league_ceiling_rate,
                        league_recent.avg_sacks AS league_sacks,
                        league_recent.avg_interceptions AS league_interceptions,
                        league_recent.avg_fumble_recoveries AS league_fumble_recoveries,
                        league_recent.avg_safeties AS league_safeties,
                        league_recent.avg_touchdowns AS league_touchdowns,
                        league_recent.avg_blocked_kicks AS league_blocked_kicks,
                        league_recent.avg_points_allowed_score AS league_points_allowed_score
                    FROM current_dst cur
                    LEFT JOIN LATERAL (
                        SELECT
                            COUNT(*) AS games,
                            AVG(recent.dk_points) AS avg_points,
                            STDDEV_POP(recent.dk_points) AS stddev_points,
                            percentile_cont(0.10) WITHIN GROUP (ORDER BY recent.dk_points) AS p10,
                            percentile_cont(0.25) WITHIN GROUP (ORDER BY recent.dk_points) AS p25,
                            percentile_cont(0.75) WITHIN GROUP (ORDER BY recent.dk_points) AS p75,
                            percentile_cont(0.90) WITHIN GROUP (ORDER BY recent.dk_points) AS p90,
                            AVG(CASE WHEN recent.dk_points >= 10 THEN 1.0 ELSE 0.0 END) AS ceiling_rate,
                            AVG(recent.sacks) AS avg_sacks,
                            AVG(recent.interceptions) AS avg_interceptions,
                            AVG(recent.fumble_recoveries) AS avg_fumble_recoveries,
                            AVG(recent.safeties) AS avg_safeties,
                            AVG(recent.interception_return_tds + recent.fumble_return_tds + recent.special_teams_tds) AS avg_touchdowns,
                            AVG(recent.blocked_kicks) AS avg_blocked_kicks,
                            AVG(recent.points_allowed_score) AS avg_points_allowed_score
                        FROM (
                            SELECT hist.*
                            FROM {s}.fact_dst_game_actual hist
                            WHERE hist.player_id = cur.player_id
                              AND (hist.season < cur.season OR (hist.season = cur.season AND hist.week < cur.week))
                            ORDER BY hist.season DESC, hist.week DESC
                            LIMIT 8
                        ) recent
                    ) defense_recent ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT
                            COUNT(*) AS games,
                            AVG(recent.dk_points) AS avg_points,
                            AVG(CASE WHEN recent.dk_points >= 10 THEN 1.0 ELSE 0.0 END) AS ceiling_rate,
                            AVG(recent.sacks) AS avg_sacks,
                            AVG(recent.interceptions) AS avg_interceptions,
                            AVG(recent.fumble_recoveries) AS avg_fumble_recoveries,
                            AVG(recent.safeties) AS avg_safeties,
                            AVG(recent.interception_return_tds + recent.fumble_return_tds + recent.special_teams_tds) AS avg_touchdowns,
                            AVG(recent.blocked_kicks) AS avg_blocked_kicks,
                            AVG(recent.points_allowed_score) AS avg_points_allowed_score
                        FROM (
                            SELECT hist.*
                            FROM {s}.fact_dst_game_actual hist
                            WHERE hist.opponent_team_id = cur.opponent_team_id
                              AND (hist.season < cur.season OR (hist.season = cur.season AND hist.week < cur.week))
                            ORDER BY hist.season DESC, hist.week DESC
                            LIMIT 8
                        ) recent
                    ) opponent_recent ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT
                            AVG(recent.dk_points) AS avg_points,
                            STDDEV_POP(recent.dk_points) AS stddev_points,
                            percentile_cont(0.10) WITHIN GROUP (ORDER BY recent.dk_points) AS p10,
                            percentile_cont(0.25) WITHIN GROUP (ORDER BY recent.dk_points) AS p25,
                            percentile_cont(0.75) WITHIN GROUP (ORDER BY recent.dk_points) AS p75,
                            percentile_cont(0.90) WITHIN GROUP (ORDER BY recent.dk_points) AS p90,
                            AVG(CASE WHEN recent.dk_points >= 10 THEN 1.0 ELSE 0.0 END) AS ceiling_rate,
                            AVG(recent.sacks) AS avg_sacks,
                            AVG(recent.interceptions) AS avg_interceptions,
                            AVG(recent.fumble_recoveries) AS avg_fumble_recoveries,
                            AVG(recent.safeties) AS avg_safeties,
                            AVG(recent.interception_return_tds + recent.fumble_return_tds + recent.special_teams_tds) AS avg_touchdowns,
                            AVG(recent.blocked_kicks) AS avg_blocked_kicks,
                            AVG(recent.points_allowed_score) AS avg_points_allowed_score
                        FROM (
                            SELECT hist.*
                            FROM {s}.fact_dst_game_actual hist
                            WHERE hist.season < cur.season OR (hist.season = cur.season AND hist.week < cur.week)
                            ORDER BY hist.season DESC, hist.week DESC, hist.game_id, hist.player_id
                            LIMIT 256
                        ) recent
                    ) league_recent ON TRUE
                ),
                component_inputs AS (
                    SELECT *,
                        0.55 * COALESCE(defense_sacks, league_sacks, 0) + 0.45 * COALESCE(opponent_sacks_allowed, league_sacks, 0) AS expected_sacks,
                        0.55 * COALESCE(defense_interceptions, league_interceptions, 0) + 0.45 * COALESCE(opponent_interceptions_allowed, league_interceptions, 0) AS expected_interceptions,
                        0.55 * COALESCE(defense_fumble_recoveries, league_fumble_recoveries, 0) + 0.45 * COALESCE(opponent_fumble_recoveries_allowed, league_fumble_recoveries, 0) AS expected_fumble_recoveries,
                        0.55 * COALESCE(defense_safeties, league_safeties, 0) + 0.45 * COALESCE(opponent_safeties_allowed, league_safeties, 0) AS expected_safeties,
                        0.55 * COALESCE(defense_touchdowns, league_touchdowns, 0) + 0.45 * COALESCE(opponent_touchdowns_allowed, league_touchdowns, 0) AS expected_touchdowns,
                        0.55 * COALESCE(defense_blocked_kicks, league_blocked_kicks, 0) + 0.45 * COALESCE(opponent_blocked_kicks_allowed, league_blocked_kicks, 0) AS expected_blocked_kicks,
                        0.55 * COALESCE(defense_points_allowed_score, league_points_allowed_score, 0) + 0.45 * COALESCE(opponent_points_allowed_score, league_points_allowed_score, 0) AS expected_historical_pa_score,
                        CASE
                            WHEN opponent_implied_points IS NULL THEN COALESCE(league_points_allowed_score, 0)
                            WHEN opponent_implied_points <= 0 THEN 10
                            WHEN opponent_implied_points <= 6 THEN 7
                            WHEN opponent_implied_points <= 13 THEN 4
                            WHEN opponent_implied_points <= 20 THEN 1
                            WHEN opponent_implied_points <= 27 THEN 0
                            WHEN opponent_implied_points <= 34 THEN -1
                            ELSE -4
                        END AS market_pa_score,
                        COALESCE(defense_avg_points, opponent_avg_points, league_avg_points, 0) AS baseline_points,
                        COALESCE(defense_stddev, league_stddev, 0) AS range_stddev,
                        COALESCE(defense_p10, league_p10, 0) AS range_p10,
                        COALESCE(defense_p25, league_p25, 0) AS range_p25,
                        COALESCE(defense_p75, league_p75, 0) AS range_p75,
                        COALESCE(defense_p90, league_p90, 0) AS range_p90,
                        COALESCE(defense_ceiling_rate, opponent_ceiling_rate, league_ceiling_rate, 0) AS baseline_ceiling_rate
                    FROM enriched
                ),
                modeled AS (
                    SELECT *,
                        expected_sacks
                        + 2 * expected_interceptions
                        + 2 * expected_fumble_recoveries
                        + 2 * expected_safeties
                        + 6 * expected_touchdowns
                        + 2 * expected_blocked_kicks
                        + 0.65 * expected_historical_pa_score
                        + 0.35 * market_pa_score AS component_mean
                    FROM component_inputs
                ),
                centered AS (
                    SELECT *,
                        GREATEST(-2.0, LEAST(25.0, 0.70 * component_mean + 0.30 * baseline_points)) AS model_mean
                    FROM modeled
                )
                INSERT INTO {s}.player_projection
                (projection_run_id, model_run_id, season, week, game_id, slate_id, player_id,
                 mean, median, p10, p25, p75, p90, stddev, ceiling_prob, data_cutoff_at)
                SELECT
                    :model_id || ':projection:' || season::text || ':' || week::text,
                    :model_id || ':run:' || season::text || ':' || week::text,
                    season,
                    week,
                    game_id,
                    NULL::text,
                    player_id,
                    model_mean,
                    model_mean,
                    GREATEST(
                        -4.0,
                        model_mean - GREATEST(baseline_points - range_p10, 1.35 * range_stddev)
                    ),
                    GREATEST(
                        -4.0,
                        model_mean - GREATEST(baseline_points - range_p25, 0.70 * range_stddev)
                    ),
                    model_mean + GREATEST(range_p75 - baseline_points, 0.70 * range_stddev),
                    model_mean + GREATEST(range_p90 - baseline_points, 1.35 * range_stddev),
                    range_stddev,
                    LEAST(1.0, GREATEST(0.0, baseline_ceiling_rate + 0.03 * (model_mean - baseline_points))),
                    NULL::timestamptz
                FROM centered
                ON CONFLICT (projection_run_id, game_id, player_id) DO UPDATE SET
                    mean = EXCLUDED.mean,
                    median = EXCLUDED.median,
                    p10 = EXCLUDED.p10,
                    p25 = EXCLUDED.p25,
                    p75 = EXCLUDED.p75,
                    p90 = EXCLUDED.p90,
                    stddev = EXCLUDED.stddev,
                    ceiling_prob = EXCLUDED.ceiling_prob,
                    data_cutoff_at = EXCLUDED.data_cutoff_at
                """
            ),
            {**params, "model_id": MODEL_ID},
        ).rowcount or 0

        conn.execute(
            text(
                f"""
                DELETE FROM {s}.feature_player_game feature
                USING {s}.dim_player player
                WHERE feature.player_id = player.player_id
                  AND upper(trim(player.primary_position)) IN ('D', 'DEF', 'DST')
                  AND feature.feature_run_id = :model_id || ':features:' || feature.season::text || ':' || feature.week::text
                  AND NOT EXISTS (
                      SELECT 1
                      FROM {s}.fact_dst_game_actual actual
                      WHERE actual.season = feature.season
                        AND actual.week = feature.week
                        AND actual.game_id = feature.game_id
                        AND actual.player_id = feature.player_id
                  )
                  {extra_filter.replace('actual.', 'feature.')}
                """
            ),
            {**params, "model_id": MODEL_ID},
        )
        conn.execute(
            text(
                f"""
                DELETE FROM {s}.player_projection projection
                USING {s}.dim_player player
                WHERE projection.player_id = player.player_id
                  AND upper(trim(player.primary_position)) IN ('D', 'DEF', 'DST')
                  AND projection.projection_run_id = :model_id || ':projection:' || projection.season::text || ':' || projection.week::text
                  AND NOT EXISTS (
                      SELECT 1
                      FROM {s}.fact_dst_game_actual actual
                      WHERE actual.season = projection.season
                        AND actual.week = projection.week
                        AND actual.game_id = projection.game_id
                        AND actual.player_id = projection.player_id
                  )
                  {extra_filter.replace('actual.', 'projection.')}
                """
            ),
            {**params, "model_id": MODEL_ID},
        )

    return BuildResult(
        status="completed",
        feature_runs=int(feature_runs),
        feature_rows=int(feature_rows),
        model_runs=int(model_runs),
        projection_rows=int(projection_rows),
        dst_projection_rows=int(dst_projection_rows),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build target-native baseline player projections.")
    parser.add_argument("--database", help="Postgres database name. Defaults to PGDATABASE.")
    parser.add_argument("--host", help="Postgres host. Defaults to PGHOST or localhost.")
    parser.add_argument("--port", help="Postgres port. Defaults to PGPORT or 5432.")
    parser.add_argument("--user", help="Postgres user. Defaults to PGUSER.")
    parser.add_argument("--password", help="Postgres password. Defaults to PGPASSWORD.")
    parser.add_argument("--target-schema", default="target")
    parser.add_argument("--season", type=int)
    parser.add_argument("--week", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    if args.week is not None and args.season is None:
        parser.error("--week requires --season")

    engine = create_engine(build_connection_url(args))
    result = build_baseline_projections(
        engine=engine,
        target_schema=args.target_schema,
        season=args.season,
        week=args.week,
        dry_run=args.dry_run,
    )
    payload = {
        "database": args.database or os.getenv("PGDATABASE"),
        "target_schema": args.target_schema,
        "season": args.season,
        "week": args.week,
        "dry_run": args.dry_run,
        **asdict(result),
    }
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
