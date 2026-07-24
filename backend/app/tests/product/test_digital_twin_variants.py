import json
import unittest
from datetime import datetime, timezone

from backend.app.product_services.digital_twin_variants import (
    artifact_hash,
    build_combined_artifact,
    build_variant_artifacts,
    compare_artifacts,
    verify_variant_artifacts,
)


def _approval(
    *,
    player_id: str,
    multiplier: float,
    decision_id: str,
    preview_id: str,
) -> dict:
    return {
        "decision_id": decision_id,
        "preview_id": preview_id,
        "belief_id": f"belief-{decision_id}",
        "belief_version_id": f"belief-version-{decision_id}",
        "policy_id": "belief_impact_v1",
        "target_player_id": player_id,
        "approved_modifier_json": {
            "modifier_type": "player_projection_multiplier",
            "policy_id": "belief_impact_v1",
            "player_id": player_id,
            "projection_multiplier": multiplier,
            "suggested_exposure_multiplier": multiplier,
        },
    }


class DigitalTwinVariantArtifactTests(unittest.TestCase):
    def setUp(self):
        self.cutoff = datetime(2025, 11, 16, 17, 0, tzinfo=timezone.utc)
        self.base_rows = [
            {
                "player_id": "player-1",
                "player_label": "Player One",
                "game_id": "game-1",
                "model_run_id": "model-run-1",
                "projection_mean": 20.0,
                "projection_p10": 10.0,
                "projection_p50": 19.0,
                "projection_p90": 32.0,
            },
            {
                "player_id": "player-2",
                "player_label": "Player Two",
                "game_id": "game-1",
                "model_run_id": "model-run-1",
                "projection_mean": 15.0,
                "projection_p10": 7.0,
                "projection_p50": 14.0,
                "projection_p90": 25.0,
            },
        ]

    def test_three_artifacts_keep_model_human_and_combined_inputs_separate(self):
        artifacts = build_variant_artifacts(
            projection_run_id="projection-run-1",
            base_rows=self.base_rows,
            approved_rows=[
                _approval(
                    player_id="player-1",
                    multiplier=1.1,
                    decision_id="decision-1",
                    preview_id="preview-1",
                ),
                _approval(
                    player_id="player-1",
                    multiplier=0.9,
                    decision_id="decision-2",
                    preview_id="preview-2",
                ),
                _approval(
                    player_id="not-in-run",
                    multiplier=1.12,
                    decision_id="decision-3",
                    preview_id="preview-3",
                ),
            ],
            decision_cutoff_at=self.cutoff,
        )

        self.assertEqual(set(artifacts), {"model_only", "human_only", "combined"})
        self.assertEqual(artifacts["model_only"]["players"][0]["projection_mean"], 20.0)
        self.assertEqual(len(artifacts["human_only"]["players"]), 1)
        self.assertEqual(
            artifacts["human_only"]["players"][0]["projection_multiplier"], 0.99
        )
        self.assertEqual(artifacts["combined"]["players"][0]["projection_mean"], 19.8)
        self.assertEqual(artifacts["combined"]["players"][1]["projection_mean"], 15.0)
        self.assertEqual(
            artifacts["combined"]["players"][0]["approved_decision_ids"],
            ["decision-1", "decision-2"],
        )

    def test_no_approved_human_inputs_leaves_combined_projection_unchanged(self):
        artifacts = build_variant_artifacts(
            projection_run_id="projection-run-1",
            base_rows=self.base_rows,
            approved_rows=[],
            decision_cutoff_at=self.cutoff,
        )

        self.assertEqual(artifacts["human_only"]["players"], [])
        self.assertEqual(
            [row["projection_mean"] for row in artifacts["combined"]["players"]],
            [20.0, 15.0],
        )
        self.assertEqual(compare_artifacts(artifacts)["players_with_human_input"], 0)

    def test_replay_recomputes_the_exact_combined_artifact_and_hash(self):
        artifacts = build_variant_artifacts(
            projection_run_id="projection-run-1",
            base_rows=self.base_rows,
            approved_rows=[
                _approval(
                    player_id="player-1",
                    multiplier=1.12,
                    decision_id="decision-1",
                    preview_id="preview-1",
                )
            ],
            decision_cutoff_at=self.cutoff,
        )
        persisted = json.loads(json.dumps(artifacts))
        replayed = build_combined_artifact(
            persisted["model_only"], persisted["human_only"]
        )

        self.assertEqual(replayed, persisted["combined"])
        self.assertEqual(artifact_hash(replayed), artifact_hash(persisted["combined"]))
        comparison = compare_artifacts(persisted)
        self.assertEqual(comparison["players_with_human_input"], 1)
        self.assertEqual(comparison["changed_players"][0]["projection_mean_delta"], 2.4)

    def test_replay_detects_tampered_stored_combined_artifact(self):
        artifacts = build_variant_artifacts(
            projection_run_id="projection-run-1",
            base_rows=self.base_rows,
            approved_rows=[],
            decision_cutoff_at=self.cutoff,
        )
        stored_hashes = {
            variant_type: artifact_hash(artifact)
            for variant_type, artifact in artifacts.items()
        }
        artifacts["combined"]["players"][0]["projection_mean"] = 999.0

        verification = verify_variant_artifacts(artifacts, stored_hashes)

        self.assertTrue(verification["checks"]["model_only"])
        self.assertTrue(verification["checks"]["human_only"])
        self.assertFalse(verification["checks"]["combined"])

    def test_rejects_modifier_whose_player_disagrees_with_preview(self):
        approval = _approval(
            player_id="player-1",
            multiplier=1.1,
            decision_id="decision-1",
            preview_id="preview-1",
        )
        approval["approved_modifier_json"]["player_id"] = "player-2"

        with self.assertRaisesRegex(ValueError, "does not match"):
            build_variant_artifacts(
                projection_run_id="projection-run-1",
                base_rows=self.base_rows,
                approved_rows=[approval],
                decision_cutoff_at=self.cutoff,
            )

    def test_rejects_duplicate_players_in_exact_projection_snapshot(self):
        with self.assertRaisesRegex(ValueError, "duplicate player projections"):
            build_variant_artifacts(
                projection_run_id="projection-run-1",
                base_rows=[self.base_rows[0], dict(self.base_rows[0])],
                approved_rows=[],
                decision_cutoff_at=self.cutoff,
            )


if __name__ == "__main__":
    unittest.main()
