import json
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone

from backend.app.product_services.belief_impacts import (
    BeliefImpactService,
    build_impact_payload,
    projection_adjustment_pct,
)


class _MappingsResult:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.rowcount = len(self.rows)

    def mappings(self):
        return self

    def one(self):
        return self.rows[0]

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class _ImpactConnection:
    def __init__(self):
        self.previews = []
        self.decisions = {}

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        if "INSERT INTO target.belief_impact_preview" in sql:
            row = dict(params)
            row["baseline_json"] = json.loads(row["baseline_json"])
            row["proposed_json"] = json.loads(row["proposed_json"])
            row["delta_json"] = json.loads(row["delta_json"])
            row["modifier_json"] = json.loads(row["modifier_json"])
            row["lineage_json"] = json.loads(row["lineage_json"])
            row["notices_json"] = json.loads(row["notices_json"])
            row["created_at"] = datetime.now(timezone.utc)
            self.previews.append(row)
            return _MappingsResult([row])
        if "INSERT INTO target.belief_impact_decision" in sql:
            self.decisions[params["preview_id"]] = {
                "decision_id": params["decision_id"],
                "decision": params["decision"],
                "note_text": params["note_text"],
                "approved_modifier_json": json.loads(params["approved_modifier_json"]),
                "decided_at": datetime.now(timezone.utc),
            }
            return _MappingsResult([{}])
        if "FROM target.belief_impact_preview p" in sql:
            rows = []
            for preview in reversed(self.previews):
                row = dict(preview)
                row.update(
                    self.decisions.get(
                        preview["preview_id"],
                        {
                            "decision_id": None,
                            "decision": None,
                            "note_text": None,
                            "approved_modifier_json": {},
                            "decided_at": None,
                        },
                    )
                )
                rows.append(row)
            return _MappingsResult(rows[: params["limit"]])
        raise AssertionError(f"Unexpected SQL in test: {sql}")


class _ImpactEngine:
    def __init__(self):
        self.url = "postgresql://test"
        self.connection = _ImpactConnection()

    @contextmanager
    def begin(self):
        yield self.connection


class _ExposureConnection:
    def __init__(self):
        self.query = ""

    def execute(self, statement, _params=None):
        sql = str(statement)
        if sql.startswith("SET LOCAL"):
            return _MappingsResult()
        self.query = sql
        return _MappingsResult(
            [{"optimizer_run_id": "optimizer-run-1", "lineup_count": 4, "player_lineup_count": 2}]
        )


class _ExposureEngine:
    def __init__(self):
        self.url = "postgresql://test"
        self.connection = _ExposureConnection()

    @contextmanager
    def begin(self):
        yield self.connection


class _Beliefs:
    belief_version_id = "belief-version-1"

    def get_current(self, belief_id):
        return {
            "belief_version_id": self.belief_version_id,
            "belief_id": belief_id,
            "status": "active",
            "is_expired": False,
            "scope_type": "player",
            "subject_label": "Test Runner",
            "subject_id": "player-1",
            "season": 2025,
            "week": 11,
            "slate": "SUNDAY_MAIN",
            "contest_format": "classic",
            "objective": "gpp",
            "direction": "boost",
            "strength": 5,
            "confidence": 100,
        }


class _Predictions:
    def fetch_predictions(self, **_kwargs):
        return [
            {
                "player_id": "player-1",
                "player_display_name": "Test Runner",
                "predicted_mean": 20.0,
                "predicted_p10": 10.0,
                "predicted_p50": 19.0,
                "predicted_p90": 32.0,
                "projection_run_id": "projection-run-1",
                "model_run_id": "model-run-1",
                "feature_run_id": "feature-run-1",
            }
        ]


class _Ownership:
    def fetch_projected_ownership(self, **_kwargs):
        return [
            {
                "player_id": "player-1",
                "projected_ownership": 18.5,
                "ownership_run_id": "ownership-run-1",
            }
        ]


class _Simulations:
    def estimate_player_modifier(self, **_kwargs):
        return {
            "simulation_run_id": "simulation-run-1",
            "simulation_model_id": "independent_quantile_lineup_v1",
            "baseline_optimal_lineup_probability": 22.0,
            "proposed_optimal_lineup_probability": 28.0,
            "num_simulations": 1000,
            "seed": 502,
        }


class _TestImpactService(BeliefImpactService):
    def _ensure_schema(self):
        return None

    def _fetch_exposure(self, **_kwargs):
        return 25.0, "optimizer-run-1"


class BeliefImpactPolicyTests(unittest.TestCase):
    def test_adjustment_is_bounded_and_posture_weighted(self):
        self.assertEqual(projection_adjustment_pct("boost", 5, 100), 0.12)
        self.assertEqual(projection_adjustment_pct("fade", 5, 100), -0.12)
        self.assertEqual(projection_adjustment_pct("prefer", 5, 100), 0.078)
        self.assertEqual(projection_adjustment_pct("monitor", 5, 100), 0.0)

    def test_payload_preserves_field_forecast_and_uses_simulated_probability(self):
        impact = build_impact_payload(
            belief={"direction": "prefer", "strength": 5, "confidence": 100},
            prediction={
                "player_id": "player-1",
                "predicted_mean": 20,
                "predicted_p10": 10,
                "predicted_p50": 18,
                "predicted_p90": 30,
            },
            ownership={"projected_ownership": 17.5},
            exposure_pct=25,
            baseline_optimal_lineup_probability=22.0,
            proposed_optimal_lineup_probability=28.0,
        )

        self.assertEqual(impact["proposed"]["projection_mean"], 21.56)
        self.assertEqual(impact["baseline"]["field_ownership_pct"], 17.5)
        self.assertEqual(impact["proposed"]["field_ownership_pct"], 17.5)
        self.assertEqual(impact["proposed"]["portfolio_exposure_pct"], 26.95)
        self.assertEqual(impact["baseline"]["optimal_lineup_probability"], 22.0)
        self.assertEqual(impact["proposed"]["optimal_lineup_probability"], 28.0)
        self.assertEqual(impact["delta"]["optimal_lineup_probability"], 6.0)
        self.assertEqual(impact["modifier"]["field_ownership_multiplier"], 1.0)

    def test_exposure_uses_latest_persisted_optimizer_portfolio(self):
        engine = _ExposureEngine()
        service = BeliefImpactService(
            engine=engine,
            belief_service=_Beliefs(),
            predictions_service=_Predictions(),
            ownership_service=_Ownership(),
            simulation_service=_Simulations(),
        )

        exposure, optimizer_run_id = service._fetch_exposure(
            season=2025,
            week=11,
            slate="SUNDAY_MAIN",
            contest_format="classic",
            objective="gpp",
            player_id="player-1",
        )

        self.assertEqual(exposure, 50.0)
        self.assertEqual(optimizer_run_id, "optimizer-run-1")
        self.assertEqual(engine.connection.query.count("WITH latest_run AS"), 1)

    def test_preview_and_decision_are_separate_immutable_records(self):
        engine = _ImpactEngine()
        service = _TestImpactService(
            engine=engine,
            belief_service=_Beliefs(),
            predictions_service=_Predictions(),
            ownership_service=_Ownership(),
            simulation_service=_Simulations(),
        )

        preview = service.create_preview(
            "belief-1",
            {
                "target_player_id": "player-1",
                "season": 2025,
                "week": 11,
                "slate": "SUNDAY_MAIN",
                "contest_format": "classic",
                "objective": "gpp",
            },
        )
        approved = service.decide(preview["preview_id"], "approved", "Matches my intended view")

        self.assertEqual(preview["status"], "pending")
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["approved_modifier"], preview["modifier"])
        self.assertEqual(len(engine.connection.previews), 1)
        self.assertEqual(len(engine.connection.decisions), 1)
        with self.assertRaisesRegex(ValueError, "already has a final decision"):
            service.decide(preview["preview_id"], "rejected")

    def test_old_belief_version_cannot_be_approved(self):
        engine = _ImpactEngine()
        beliefs = _Beliefs()
        service = _TestImpactService(
            engine=engine,
            belief_service=beliefs,
            predictions_service=_Predictions(),
            ownership_service=_Ownership(),
            simulation_service=_Simulations(),
        )
        preview = service.create_preview(
            "belief-1",
            {"target_player_id": "player-1", "season": 2025, "week": 11},
        )
        beliefs.belief_version_id = "belief-version-2"

        with self.assertRaisesRegex(ValueError, "older belief version"):
            service.decide(preview["preview_id"], "approved")


if __name__ == "__main__":
    unittest.main()
