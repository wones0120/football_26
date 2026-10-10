from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import GradientBoostingRegressor

from backend.app.product_services.model_artifacts import (
    deserialize_artifact, explain_player, serialize_artifact,
    training_fingerprint, tree_path_attributions,
)


def _fitted_payload():
    train = pd.DataFrame({
        "player_id": [f"p{i}" for i in range(12)],
        "position": ["RB"] * 12,
        "salary": [4000 + i * 200 for i in range(12)],
        "team_spread_line": [-7 + i for i in range(12)],
        "team_implied_total": [18 + i for i in range(12)],
        "game_total_line": [40 + i for i in range(12)],
        "offensive_role_importance": [0.25 + i * .04 for i in range(12)],
        "snap_share_mean_3": [0.3 + i * .04 for i in range(12)],
        "player_games_history": [4] * 12,
        "player_roll3_mean": [7 + i for i in range(12)],
        "player_roll8_mean": [7 + i for i in range(12)],
        "carries_mean_3": [5 + i for i in range(12)],
        "targets_mean_3": [1 + i * .2 for i in range(12)],
        "label_dk_total_points": [8 + i * 1.5 for i in range(12)],
    })
    columns = ["salary", "team_spread_line", "team_implied_total", "game_total_line",
               "offensive_role_importance", "snap_share_mean_3"]
    model = GradientBoostingRegressor(random_state=42).fit(train[columns], train["label_dk_total_points"])
    target = train.iloc[[3, 8]].copy().reset_index(drop=True)
    target["recent_team"] = ["MIA", "BUF"]
    target["opponent_team"] = ["KC", "LAC"]
    target["pregame_availability_probability"] = 1.0
    target["pregame_opportunity_context_applied"] = False
    return model, train, target, columns


def test_artifact_round_trip_checksum_and_exact_raw_predictions():
    model, train, target, columns = _fitted_payload()
    data, checksum = serialize_artifact(
        model=model, train=train, target=target, feature_columns=columns,
        calibration={"p90": "walk-forward"}, profiles={},
    )
    loaded = deserialize_artifact(data, checksum)
    np.testing.assert_array_equal(model.predict(target[columns]),
                                  loaded["model"].predict(target[columns]))
    assert loaded["calibration"] == {"p90": "walk-forward"}
    assert training_fingerprint(train) != training_fingerprint(train.assign(salary=train.salary + 1))
    with pytest.raises(ValueError, match="checksum"):
        deserialize_artifact(data, "0" * 64)


def test_tree_paths_and_player_probes_are_reloadable_and_diagnostic_only():
    model, train, target, columns = _fitted_payload()
    data, checksum = serialize_artifact(
        model=model, train=train, target=target, feature_columns=columns,
        calibration={}, profiles={},
    )
    payload = deserialize_artifact(data, checksum)
    row = target.iloc[[0]][columns]
    terms = tree_path_attributions(payload["model"], row)
    raw_delta = model.predict(row)[0] - model.init_.predict(row)[0]
    assert sum(terms.values()) == pytest.approx(raw_delta)
    explanation = explain_player(payload, str(target.iloc[0]["player_id"]))
    assert explanation["counterfactuals"]
    assert any(item["scenario"] == "Neutral spread" for item in explanation["counterfactuals"])
    assert any(item["scenario"] == "League-average team implied total" for item in explanation["counterfactuals"])
    assert explanation["top_positive_model_drivers"] or explanation["top_negative_model_drivers"]
    assert "not SHAP or causal" in explanation["attribution_method"]


@pytest.mark.parametrize('market_adjustment', [3.25, -100.0, float('nan')])
def test_explanation_replays_market_correction_floor_and_participation(market_adjustment):
    from backend.app.product_services.predictions import blend_point_predictions
    model, train, target, columns = _fitted_payload()
    target.attrs = {'source_audit': [{'team': 'MIA', 'volume': 20}]}
    target['market_team_point_adjustment'] = market_adjustment
    target['pregame_availability_probability'] = .5
    data, checksum = serialize_artifact(model=model, train=train, target=target,
        feature_columns=columns, calibration={}, profiles={})
    payload = deserialize_artifact(data, checksum)
    original = payload['target'].copy(deep=True)
    explanation = explain_player(payload, str(target.iloc[0].player_id))
    base = blend_point_predictions(model.predict(target[columns]), train, target)[0]
    adjustment = 0. if pd.isna(market_adjustment) else market_adjustment
    assert explanation['reloaded_model_mean'] == pytest.approx(max(0., base + adjustment)*.5)
    assert explanation['opportunity_assessment']['pregame_opportunity_point_reason'] == 'no_current_opportunity_context'
    assert explanation['opportunity_assessment']['pregame_opportunity_point_anchor'] is None
    pd.testing.assert_frame_equal(payload['target'], original)
    assert payload['target'].attrs == original.attrs
