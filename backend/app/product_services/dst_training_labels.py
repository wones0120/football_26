"""Explicit, fail-closed selection of verified DST labels for candidate fitting.

This module is not called by live Prepare. Promotion requires a separate decision.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from Database.dst import normalize_team

SCORING_CONTRACT = "draftkings_classic_dst_event_scoring_v1"
TARGET = "label_dk_total_points"


def read_verified_correction(path: str | Path, *, expected_sha256: str) -> dict:
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("DST correction source checksum mismatch")
    dataset = json.loads(data)
    if dataset.get("contract_id") != SCORING_CONTRACT:
        raise ValueError("DST correction scoring contract mismatch")
    return dataset


def select_corrected_dst_labels(frame: pd.DataFrame, dataset: dict, *,
                                target_season: int, target_week: int) -> tuple[pd.DataFrame, dict]:
    """Replace only completed, pre-target DST targets; require exact source identity.

    Missing corrections never fall back to legacy values or zero. Verified zero
    scores are retained. Future placeholders and all non-DST rows are unchanged.
    Historical features deliberately remain frozen for the label-only experiment.
    """
    if dataset.get("contract_id") != SCORING_CONTRACT:
        raise ValueError("DST correction scoring contract mismatch")
    lookup = {}
    for row in dataset["rows"]:
        key = int(row["player_game_feature_matrix_id"])
        if key in lookup:
            raise ValueError(f"Duplicate DST correction matrix identity: {key}")
        lookup[key] = row
    result = frame.copy(deep=True)
    prior = (result.season < target_season) | ((result.season == target_season) & (result.week < target_week))
    selected = result.position.astype(str).str.upper().eq("DST") & prior
    changed = 0
    reconstructed_game_ids = 0
    for index, original in result.loc[selected].iterrows():
        key = int(original["player_game_feature_matrix_id"])
        corrected = lookup.get(key)
        if corrected is None:
            raise ValueError(f"Missing verified DST correction for matrix row {key}")
        for field in ("season", "week", "player_master_id", "team", "opponent", "source_system"):
            if str(original[field]) != str(corrected[field]):
                raise ValueError(f"DST correction identity mismatch: {key} {field}")
        game_id = corrected.get("game_id")
        parts = str(game_id).split("_")
        expected_teams = {normalize_team(original["team"]), normalize_team(original["opponent"])}
        if (len(parts) != 4 or parts[:2] != [str(int(original["season"])), f"{int(original['week']):02d}"]
                or {normalize_team(team) for team in parts[2:]} != expected_teams):
            raise ValueError(f"DST correction game identity mismatch: {key}")
        original_game = original.get("game_id")
        if pd.notna(original_game) and str(original_game).strip():
            if str(original_game) != str(game_id):
                raise ValueError(f"DST correction identity mismatch: {key} game_id")
        else:
            reconstructed_game_ids += 1
        if corrected.get("dst_scoring_contract") != SCORING_CONTRACT or not corrected.get("dst_source_sha256"):
            raise ValueError(f"Unverified DST scoring source: {key}")
        value = corrected.get("dk_points")
        if value is None or not math.isfinite(float(value)):
            raise ValueError(f"Missing finite verified DST score: {key}")
        changed += bool(original[TARGET] != float(value))
        result.at[index, TARGET] = float(value)
    return result, dict(scoring_contract=SCORING_CONTRACT, selected_rows=int(selected.sum()),
                        changed_rows=changed, original_missing_game_ids=reconstructed_game_ids, missing_policy="reject_no_legacy_fallback",
                        target_season=target_season, target_week=target_week,
                        features_policy="unchanged_frozen_pregame_features")
