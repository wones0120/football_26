"""Lightweight saved optimizer and durable queue history for one UI scope."""
from datetime import UTC, datetime

from sqlalchemy import JSON, column, func, select, table, text
from sqlalchemy.orm import load_only

from ..models import OperationalJob
from ..services.job_queue import OPTIMIZER_JOB


def _iso(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)).isoformat()


def list_optimizer_runs(engine, session, *, season, week, slate, contest_format, objective=None, limit=20):
    scope = dict(season=season, week=week, slate=slate.upper(), contest_format=contest_format)
    runs = table("optimizer_run", *[column(name) for name in (
        "optimizer_run_id", "season", "week", "slate_id", "contest_format", "objective",
        "strategy", "status", "message", "created_at", "updated_at", "projection_run_id")],
        column("constraint_config_json", JSON), schema="target")
    lineups = table("lineup", column("optimizer_run_id"), column("lineup_id"), schema="target")
    # Limit the scope before counting lineups or reading large JSON reports.
    recent = select(runs).where(
        runs.c.season == season, runs.c.week == week, func.upper(runs.c.slate_id) == slate.upper(),
        runs.c.contest_format == contest_format,
        *([runs.c.objective == objective] if objective is not None else []),
    ).order_by(runs.c.created_at.desc(), runs.c.optimizer_run_id.desc()).limit(limit).subquery()
    runs = recent
    counts = select(lineups.c.optimizer_run_id, func.count().label("lineup_count")).where(
        lineups.c.optimizer_run_id.in_(select(recent.c.optimizer_run_id))
    ).group_by(lineups.c.optimizer_run_id).subquery()
    query = select(
        runs.c.optimizer_run_id, runs.c.strategy, runs.c.status, runs.c.message, runs.c.objective,
        runs.c.created_at, runs.c.updated_at, runs.c.projection_run_id,
        func.coalesce(counts.c.lineup_count, 0).label("lineup_count"),
        runs.c.constraint_config_json["num_lineups"].as_integer().label("requested_lineups"),
        runs.c.constraint_config_json["classic_expanded_discovery"].as_boolean().label("expanded_discovery"),
        runs.c.constraint_config_json["analyst_optimization_intent"].as_string().label("optimization_intent"),
        runs.c.constraint_config_json["analyst_selection_policy"].as_string().label("analyst_selection_policy"),
        runs.c.constraint_config_json["classic_selection_objective"].as_string().label("classic_selection_objective"),
        runs.c.constraint_config_json["entry_readiness"]["entry_ready"].as_boolean().label("entry_ready"),
        runs.c.constraint_config_json["preliminary_report"].as_string().isnot(None).label("preliminary_export_blocked"),
        ((runs.c.constraint_config_json["gpp_recommendation"]["policy_id"].as_string().in_(("gpp_projection_first_recommendation_v1", "offensive_workload_recommendation_v1", "shared_world_anchor_recommendation_v1")))
         & (runs.c.constraint_config_json["gpp_recommendation"]["status"].as_string() == "provisional")
         & (runs.c.constraint_config_json["gpp_recommendation"]["optimizer_run_id"].as_string() == runs.c.optimizer_run_id)
        ).label("saved_recommendation_available"),
        runs.c.constraint_config_json["decision_snapshot"]["captured_at"].as_string().label("snapshot_captured_at"),
    ).select_from(runs.outerjoin(counts, counts.c.optimizer_run_id == runs.c.optimizer_run_id)).where(
        runs.c.season == season, runs.c.week == week, func.upper(runs.c.slate_id) == slate.upper(),
        runs.c.contest_format == contest_format,
        *([runs.c.objective == objective] if objective is not None else []),
    ).order_by(runs.c.created_at.desc(), runs.c.optimizer_run_id.desc()).limit(limit)
    with engine.connect() as connection:
        # jsonb_to_record expands each large stored report once. Repeated JSON
        # path expressions detoast the same multi-megabyte object for each field.
        if engine.dialect.name == "postgresql":
            saved = [dict(row) for row in connection.execute(text("""
                WITH recent AS MATERIALIZED (
                    SELECT * FROM target.optimizer_run
                    WHERE season=:season AND week=:week AND upper(slate_id)=:slate
                    AND contest_format=:format AND (CAST(:objective AS text) IS NULL OR objective=CAST(:objective AS text))
                    ORDER BY created_at DESC, optimizer_run_id DESC LIMIT :limit
                )
                SELECT r.optimizer_run_id, r.strategy, r.status, r.message, r.objective,
                    r.created_at, r.updated_at, r.projection_run_id,
                    (SELECT count(*) FROM target.lineup l WHERE l.optimizer_run_id=r.optimizer_run_id) AS lineup_count,
                    c.num_lineups AS requested_lineups, c.classic_expanded_discovery AS expanded_discovery,
                    c.analyst_optimization_intent AS optimization_intent, c.analyst_selection_policy, c.classic_selection_objective,
                    (c.entry_readiness->>'entry_ready')::boolean AS entry_ready,
                    c.preliminary_report IS NOT NULL AND c.preliminary_report <> 'null'::jsonb AS preliminary_export_blocked,
                    (c.gpp_recommendation->>'policy_id' IN ('gpp_projection_first_recommendation_v1','offensive_workload_recommendation_v1','shared_world_anchor_recommendation_v1')
                     AND c.gpp_recommendation->>'status'='provisional'
                     AND c.gpp_recommendation->>'optimizer_run_id'=r.optimizer_run_id::text) AS saved_recommendation_available,
                    c.decision_snapshot->>'captured_at' AS snapshot_captured_at
                FROM recent r LEFT JOIN LATERAL jsonb_to_record(r.constraint_config_json::jsonb) AS c(
                    num_lineups integer, classic_expanded_discovery boolean,
                    analyst_optimization_intent text, analyst_selection_policy text, classic_selection_objective text,
                    entry_readiness jsonb, preliminary_report jsonb, gpp_recommendation jsonb,
                    decision_snapshot jsonb
                ) ON true
                ORDER BY r.created_at DESC, r.optimizer_run_id DESC
            """), dict(season=season, week=week, slate=slate.upper(), format=contest_format,
                       objective=objective, limit=limit)).mappings()]
        else:
            saved = [dict(row) for row in connection.execute(query).mappings()]
    # Older optimizer timestamps were written as naive UTC into timezone-aware
    # columns. Prefer the immutable decision timestamp rather than guessing an offset.
    by_id = {str(row["optimizer_run_id"]): {**{k: v for k, v in row.items() if k != "snapshot_captured_at"}, **scope,
        "created_at": _iso(row.get("snapshot_captured_at") or row["created_at"]),
        "updated_at": _iso(row["updated_at"]), "operational_job_id": None, "saved_report_available": True,
        "started_at": None, "completed_at": None} for row in saved}
    request = OperationalJob.request_json
    queued = session.scalars(select(OperationalJob).options(load_only(
        OperationalJob.job_id, OperationalJob.run_id, OperationalJob.request_json,
        OperationalJob.status, OperationalJob.error_message, OperationalJob.progress_message,
        OperationalJob.created_at, OperationalJob.updated_at, OperationalJob.started_at,
        OperationalJob.completed_at,
    )).where(
        OperationalJob.job_type == OPTIMIZER_JOB,
        request["season"].as_integer() == season, request["week"].as_integer() == week,
        func.upper(request["slate"].as_string()) == slate.upper(),
        request["contest_format"].as_string() == contest_format,
        *([request["objective"].as_string() == objective] if objective is not None else []),
    ).order_by(OperationalJob.created_at.desc(), OperationalJob.job_id.desc()).limit(limit)).all()
    for job in queued:
        payload = job.request_json; params = payload.get("params") or {}
        row = by_id.get(job.run_id, {})
        by_id[job.run_id] = {**scope, "optimizer_run_id": job.run_id,
            "strategy": payload["strategy"], "objective": payload.get("objective"), "status": job.status,
            "message": job.error_message or job.progress_message,
            "created_at": _iso(job.created_at), "updated_at": _iso(job.updated_at),
            "projection_run_id": payload.get("projection_run_id"), "lineup_count": 0,
            "requested_lineups": params.get("num_lineups"), "saved_report_available": False,
            "expanded_discovery": bool(params.get("classic_expanded_discovery")), "optimization_intent": params.get("analyst_optimization_intent"), "analyst_selection_policy": params.get("analyst_selection_policy"), "classic_selection_objective": params.get("classic_selection_objective"), **row,
            "operational_job_id": job.job_id, "started_at": _iso(job.started_at),
            "completed_at": _iso(job.completed_at)}
        # A saved completed solve is recoverable even before its queue lease finishes.
        if row.get("status") != "completed":
            by_id[job.run_id].update(status=job.status, message=job.error_message or job.progress_message)
    return sorted(by_id.values(), key=lambda row: (row["created_at"], row["optimizer_run_id"]), reverse=True)[:limit]
