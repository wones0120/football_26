"""Immutable, run-scoped fitted projection artifacts and diagnostic rescoring."""

from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text


MODEL_VERSION = "v4.2-market-corrected"
EXPLANATION_VERSION = "tree-path-v1"


def training_fingerprint(frame: pd.DataFrame) -> str:
    """Hash all saved training cells, names, and dtypes in their fitted order."""
    digest = hashlib.sha256()
    digest.update(json.dumps([(str(name), str(dtype)) for name, dtype in frame.dtypes.items()]).encode())
    digest.update(pd.util.hash_pandas_object(frame.astype(str), index=False).values.tobytes())
    return digest.hexdigest()


def git_revision() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        check=False, timeout=5, cwd=Path(__file__).resolve().parents[3],
    )
    return result.stdout.strip() if result.returncode == 0 else None


def serialize_artifact(*, model: Any, train: pd.DataFrame, target: pd.DataFrame,
                       feature_columns: list[str], calibration: dict,
                       profiles: dict) -> tuple[bytes, str]:
    payload = {
        "model": model, "train": train, "target": target,
        "feature_columns": feature_columns, "calibration": calibration,
        "profiles": profiles, "explanation_version": EXPLANATION_VERSION,
        "raw_predictions": model.predict(
            target[feature_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        ),
    }
    buffer = BytesIO()
    joblib.dump(payload, buffer, compress=3)
    data = buffer.getvalue()
    return data, hashlib.sha256(data).hexdigest()


def deserialize_artifact(data: bytes, expected_sha256: str) -> dict:
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("Fitted model artifact checksum mismatch")
    payload = joblib.load(BytesIO(data))  # trusted bytes stored by this application
    if not isinstance(payload, dict) or "model" not in payload:
        raise ValueError("Fitted model artifact has an invalid payload")
    matrix = payload["target"][payload["feature_columns"]].apply(
        pd.to_numeric, errors="coerce"
    ).fillna(0.0)
    if not np.array_equal(payload["model"].predict(matrix), payload["raw_predictions"]):
        raise ValueError("Reloaded model no longer reproduces its saved raw predictions")
    return payload


def load_run_artifact(connection, projection_run_id: str) -> tuple[dict, dict]:
    row = connection.execute(text("""
        SELECT a.*, mr.model_id, mr.params_json, pr.projection_run_id
        FROM target.projection_run pr
        JOIN target.model_run mr ON mr.model_run_id = pr.model_run_id
        LEFT JOIN target.model_artifact a ON a.model_run_id = mr.model_run_id
        WHERE pr.projection_run_id = :run_id
    """), {"run_id": projection_run_id}).mappings().first()
    if row is None:
        raise LookupError(f"Projection run {projection_run_id} does not exist")
    if row["artifact_bytes"] is None:
        raise FileNotFoundError(
            f"Projection run {projection_run_id} names {row['model_id']} but has no fitted artifact"
        )
    params = row["params_json"] or {}
    if params.get("artifact_uri") != row["artifact_uri"] or params.get("artifact_sha256") != row["artifact_sha256"]:
        raise ValueError("Projection model lineage does not match its fitted artifact")
    data = bytes(row["artifact_bytes"])
    return deserialize_artifact(data, row["artifact_sha256"]), dict(row)


def tree_path_attributions(model: Any, features: pd.DataFrame) -> dict[str, float]:
    """Exact raw-tree path decomposition; this is not SHAP or causal attribution."""
    values = features.to_numpy(dtype=float)
    if len(values) != 1 or not hasattr(model, "estimators_"):
        return {}
    out = {name: 0.0 for name in features.columns}
    for estimator in model.estimators_.ravel():
        tree = estimator.tree_
        node = 0
        while tree.feature[node] >= 0:
            feature_index = int(tree.feature[node])
            child = (tree.children_left[node] if values[0, feature_index] <= tree.threshold[node]
                     else tree.children_right[node])
            out[features.columns[feature_index]] += (
                float(tree.value[child][0][0]) - float(tree.value[node][0][0])
            ) * model.learning_rate
            node = int(child)
    return out


def explain_player(payload: dict, player_id: str) -> dict:
    from .predictions import (  # avoid import cycle during projection training
        TARGET_COL, apply_opportunity_point_adjustment, blend_point_predictions,
    )

    target = payload["target"]
    matches = target.loc[target["player_id"].astype(str).eq(player_id)]
    if len(matches) != 1:
        raise LookupError(f"Player {player_id} is absent or ambiguous in fitted artifact")
    row = matches.iloc[[0]].copy().reset_index(drop=True)
    position = str(row.iloc[0].get("position") or "").upper()
    if position == "K":
        return {"player_id": player_id, "counterfactuals": [],
                "top_positive_model_drivers": [], "top_negative_model_drivers": [],
                "attribution_method": "Unavailable: kicker production means bypass the fitted tree",
                "explanation_version": payload["explanation_version"]}
    train = payload["train"]
    columns = payload["feature_columns"]
    model = payload["model"]

    def score(frame: pd.DataFrame) -> float:
        matrix = frame[columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        mean = blend_point_predictions(model.predict(matrix), train, frame)
        mean, _ = apply_opportunity_point_adjustment(mean, train, frame)
        participation = float(frame.iloc[0].get("pregame_availability_probability", 1) or 0)
        if str(frame.iloc[0].get("position")) == "QB":
            participation *= float(frame.iloc[0].get("pregame_start_probability", 1) or 0)
        return float(mean[0]) * participation

    baseline = score(row)
    probes: list[dict] = []
    for column, label, value in (
        ("team_spread_line", "Neutral spread", 0.0),
        ("team_implied_total", "League-average team implied total",
         float(pd.to_numeric(target.drop_duplicates(["recent_team"])["team_implied_total"], errors="coerce").mean())),
        ("game_total_line", "League-average game total",
         float(pd.to_numeric(target.assign(
             _game_key=target.apply(lambda item: tuple(sorted((str(item["recent_team"]),
                                                                str(item["opponent_team"])))), axis=1)
         ).drop_duplicates(["_game_key"])["game_total_line"], errors="coerce").mean())),
    ):
        if column in columns and np.isfinite(value):
            changed = row.copy()
            changed[column] = value
            result = score(changed)
            probes.append({"scenario": label, "feature": column, "input": value,
                           "mean": result, "delta": result - baseline})
    for column, increment in (("offensive_role_importance", 0.1),
                              ("snap_share_mean_3", 0.1)):
        if column not in columns or position not in {"RB", "WR", "TE"}:
            continue
        actual = pd.to_numeric(row.iloc[0].get(column), errors="coerce")
        if pd.isna(actual) or not np.isfinite(float(actual)):
            continue
        for direction in (-1, 1):
            value = float(np.clip(actual + direction * increment, 0, 1))
            changed = row.copy()
            changed[column] = value
            result = score(changed)
            probes.append({"scenario": f"{column} {direction * increment:+.1f}",
                           "feature": column, "input": value,
                           "mean": result, "delta": result - baseline})
    matrix = row[columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    attribution = tree_path_attributions(model, matrix)
    drivers = sorted(
        ({"feature": name, "raw_model_points": value,
          "blended_mean_points": value * 0.8} for name, value in attribution.items()
         if abs(value) > 1e-8),
        key=lambda item: item["blended_mean_points"], reverse=True,
    )
    return {
        "player_id": player_id, "actual_inputs": {
            name: float(matrix.iloc[0][name]) for name in columns
        }, "reloaded_model_mean": baseline, "counterfactuals": probes,
        "top_positive_model_drivers": [item for item in drivers if item["blended_mean_points"] > 0][:8],
        "top_negative_model_drivers": [item for item in reversed(drivers) if item["blended_mean_points"] < 0][:8],
        "attribution_method": "tree path contributions to raw model, scaled for 80% model blend; not SHAP or causal",
        "explanation_version": payload["explanation_version"],
    }
