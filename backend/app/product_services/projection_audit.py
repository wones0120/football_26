"""Read-only projection explanations and append-only external benchmarks."""

from __future__ import annotations

from datetime import datetime
import json
import math
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text

from .model_artifacts import explain_player, load_run_artifact


def projection_audit(connection, projection_run_id: str) -> dict:
    run = connection.execute(text("""
        SELECT pr.projection_run_id, pr.season, pr.week, pr.slate_id, pr.data_cutoff_at,
               mr.model_run_id, mr.model_id, mr.params_json,
               COALESCE(a.model_version, rg.model_version) AS model_version,
               a.artifact_uri, a.artifact_sha256, a.training_dataset_sha256,
               a.git_revision, a.feature_schema_json, a.calibration_json
        FROM target.projection_run pr
        JOIN target.model_run mr ON mr.model_run_id = pr.model_run_id
        JOIN target.model_registry rg ON rg.model_id = mr.model_id
        LEFT JOIN target.model_artifact a ON a.model_run_id = mr.model_run_id
        WHERE pr.projection_run_id = :run_id
    """), {"run_id": projection_run_id}).mappings().first()
    if run is None:
        raise LookupError(f"Projection run {projection_run_id} does not exist")
    status = "available" if run["artifact_uri"] else "unavailable"
    reason = None
    if status == "available":
        try:
            load_run_artifact(connection, projection_run_id)
        except Exception as exc:  # noqa: BLE001 - expose failed reload, never substitute another model
            status = "reload_failed"
            reason = str(exc)
    else:
        reason = "This historical run saved model metadata but not fitted model bytes. No fallback model is used."
    out = {key: value for key, value in dict(run).items() if key != "calibration_json"}
    out["artifact_status"] = status
    out["artifact_warning"] = reason
    out["model_explanation_version"] = "tree-path-v1"
    return out


def player_why(connection, projection_run_id: str, player_id: str) -> dict:
    audit = projection_audit(connection, projection_run_id)
    projection = connection.execute(text("""
        SELECT p.player_id, d.full_name, d.primary_position AS position, p.mean,
               p.p90, p.calibration_method, p.calibration_role,
               f.feature_json
        FROM target.player_projection p
        JOIN target.dim_player d ON d.player_id = p.player_id
        JOIN target.model_run mr ON mr.model_run_id = p.model_run_id
        LEFT JOIN target.feature_player_game f
          ON f.feature_run_id = mr.feature_run_id AND f.game_id = p.game_id
         AND f.player_id = p.player_id AND f.season = p.season AND f.week = p.week
        WHERE p.projection_run_id = :run_id AND p.player_id = :player_id
    """), {"run_id": projection_run_id, "player_id": player_id}).mappings().first()
    if projection is None:
        raise LookupError(f"Player {player_id} is absent from projection run {projection_run_id}")
    result = dict(projection)
    result["model"] = {
        "model_id": audit["model_id"], "model_version": audit["model_version"],
        "artifact_status": audit["artifact_status"],
        "artifact_warning": audit["artifact_warning"],
    }
    if audit["artifact_status"] == "available":
        payload, _ = load_run_artifact(connection, projection_run_id)
        result["explanation"] = explain_player(payload, player_id)
        if "reloaded_model_mean" in result["explanation"]:
            difference = (
                result["explanation"]["reloaded_model_mean"] - float(result["mean"])
            )
            result["explanation"]["saved_mean_difference"] = difference
            result["explanation"]["projection_parity"] = (
                "verified" if abs(difference) <= 1e-6 else "failed"
            )
            if abs(difference) > 1e-6:
                result["explanation"]["counterfactuals"] = []
                result["explanation"]["validation_warning"] = (
                    "Reloaded mean differs from saved production mean; "
                    "counterfactuals suppressed. No fallback model was used."
                )
    else:
        result["explanation"] = None
    result["external_benchmarks"] = [dict(row) for row in connection.execute(text("""
        SELECT b.benchmark_id, b.source_name, b.source_url, b.captured_at,
               v.projection, v.value, v.classification
        FROM target.external_projection_benchmark b
        JOIN target.external_projection_value v ON v.benchmark_id = b.benchmark_id
        WHERE b.season = :season AND b.week = :week AND b.slate_id = :slate
          AND v.player_id = :player_id AND b.status = 'available'
        ORDER BY b.captured_at DESC
    """), {"season": audit["season"], "week": audit["week"],
             "slate": audit["slate_id"], "player_id": player_id}).mappings()]
    return result


def disagreement_rows(connection, projection_run_id: str) -> list[dict]:
    rows = [dict(row) for row in connection.execute(text("""
        SELECT p.player_id, d.full_name AS player, d.primary_position AS position,
               p.mean AS our_mean, b.source_name AS source, b.captured_at,
               b.benchmark_id, v.projection AS external_mean, v.value,
               v.classification
        FROM target.player_projection p
        JOIN target.projection_run pr ON pr.projection_run_id = p.projection_run_id
        JOIN target.dim_player d ON d.player_id = p.player_id
        JOIN target.external_projection_benchmark b
          ON b.season = pr.season AND b.week = pr.week
         AND b.slate_id = pr.slate_id AND b.status = 'available'
        JOIN target.external_projection_value v
          ON v.benchmark_id = b.benchmark_id AND v.player_id = p.player_id
        WHERE p.projection_run_id = :run_id AND v.projection IS NOT NULL
        ORDER BY b.source_name, p.player_id
    """), {"run_id": projection_run_id}).mappings()]
    for row in rows:
        row["delta"] = float(row["our_mean"]) - float(row["external_mean"])
        row["delta_pct"] = (row["delta"] / float(row["external_mean"]) * 100
                            if row["external_mean"] else None)
    for source_position in {(row["source"], row["position"]) for row in rows}:
        subset = sorted((row for row in rows if (row["source"], row["position"]) == source_position),
                        key=lambda row: abs(row["delta"]))
        denominator = max(len(subset) - 1, 1)
        for rank, row in enumerate(subset):
            row["position_relative_percentile"] = rank / denominator * 100
            row["large_disagreement"] = (
                len(subset) >= 5 and row["position_relative_percentile"] >= 90
                and abs(row["delta"]) >= 2.5
            )
    return sorted(rows, key=lambda row: abs(row["delta"]), reverse=True)


def capture_benchmark(connection, data: dict[str, Any]) -> str:
    """Capture canonical-ID rows only; unavailable captures contain no invented values."""
    required = ("source_name", "season", "week", "slate_id", "captured_at")
    if any(not data.get(key) for key in required):
        raise ValueError(f"External benchmark requires {', '.join(required)}")
    if not (data.get("source_url") or data.get("raw_snapshot_uri")):
        raise ValueError("External benchmark requires a source URL or raw snapshot reference")
    captured = data["captured_at"]
    if isinstance(captured, str):
        captured = datetime.fromisoformat(captured.replace("Z", "+00:00"))
    if not isinstance(captured, datetime) or captured.tzinfo is None:
        raise ValueError("captured_at must be a timezone-aware timestamp")
    rows = data.get("players") or []
    status = data.get("status", "available")
    if status not in {"available", "unavailable"}:
        raise ValueError("status must be available or unavailable")
    if status == "available" and not rows:
        raise ValueError("Available benchmark requires player rows")
    if status == "unavailable" and (rows or not data.get("unavailable_reason")):
        raise ValueError("Unavailable benchmark needs a reason and no player values")
    ids = [str(row.get("player_id") or "") for row in rows]
    if not all(ids) or len(set(ids)) != len(ids):
        raise ValueError("Benchmark players require distinct canonical player_id values")
    if rows:
        known = set(connection.execute(text("SELECT player_id FROM target.dim_player WHERE player_id = ANY(:ids)"),
                                       {"ids": ids}).scalars())
        if set(ids) != known:
            raise ValueError("All benchmark player IDs must resolve to target.dim_player")
    for row in rows:
        for key in ("projection", "value"):
            if row.get(key) is not None and not math.isfinite(float(row[key])):
                raise ValueError(f"Benchmark {key} must be finite")
    benchmark_id = str(uuid5(NAMESPACE_URL, json.dumps(data, sort_keys=True, default=str)))
    connection.execute(text("""
        INSERT INTO target.external_projection_benchmark
          (benchmark_id, source_name, source_url, season, week, slate_id,
           captured_at, raw_snapshot_uri, raw_snapshot_sha256, status, unavailable_reason)
        VALUES (:benchmark_id, :source_name, :source_url, :season, :week, :slate_id,
                :captured_at, :raw_snapshot_uri, :raw_snapshot_sha256, :status, :unavailable_reason)
        ON CONFLICT (benchmark_id) DO NOTHING
    """), {"benchmark_id": benchmark_id, "source_name": data["source_name"],
           "source_url": data.get("source_url"), "season": data["season"],
           "week": data["week"], "slate_id": data["slate_id"],
           "captured_at": captured,
           "raw_snapshot_uri": data.get("raw_snapshot_uri"),
           "raw_snapshot_sha256": data.get("raw_snapshot_sha256"),
           "status": status, "unavailable_reason": data.get("unavailable_reason")})
    if rows:
        connection.execute(text("""
            INSERT INTO target.external_projection_value
              (benchmark_id, player_id, source_player_id, projection, value, classification)
            VALUES (:benchmark_id, :player_id, :source_player_id,
                    :projection, :value, :classification)
            ON CONFLICT (benchmark_id, player_id) DO NOTHING
        """), [{"benchmark_id": benchmark_id, "player_id": str(row["player_id"]),
                 "source_player_id": row.get("source_player_id"),
                 "projection": row.get("projection"), "value": row.get("value"),
                 "classification": row.get("classification")} for row in rows])
    return benchmark_id
