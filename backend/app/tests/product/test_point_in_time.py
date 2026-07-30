import unittest
from datetime import datetime, timezone

from backend.app.product_services.point_in_time import (
    POINT_IN_TIME_CUTOFF_CONTRACT_ID,
    injury_snapshot_cutoff_sql,
    snapshot_visible_at_cutoff,
)


class PointInTimeCutoffTests(unittest.TestCase):
    def test_snapshot_visibility_excludes_post_cutoff_and_unknown_timestamps(self) -> None:
        cutoff = datetime(2025, 11, 16, 18, 0, tzinfo=timezone.utc)

        self.assertTrue(
            snapshot_visible_at_cutoff(
                datetime(2025, 11, 16, 17, 59, tzinfo=timezone.utc),
                cutoff,
            )
        )
        self.assertTrue(snapshot_visible_at_cutoff(cutoff, cutoff))
        self.assertFalse(
            snapshot_visible_at_cutoff(
                datetime(2025, 11, 16, 18, 1, tzinfo=timezone.utc),
                cutoff,
            )
        )
        self.assertFalse(snapshot_visible_at_cutoff(None, cutoff))
        self.assertFalse(snapshot_visible_at_cutoff(cutoff, None))

    def test_sql_contract_requires_observation_and_projection_cutoff(self) -> None:
        predicate = injury_snapshot_cutoff_sql(
            injury_alias="snapshot",
            projection_alias="projection",
        )

        self.assertEqual(POINT_IN_TIME_CUTOFF_CONTRACT_ID, "point_in_time_cutoff_v1")
        self.assertIn("snapshot.as_of IS NOT NULL", predicate)
        self.assertIn("projection.data_cutoff_at IS NOT NULL", predicate)
        self.assertIn("snapshot.as_of <= projection.data_cutoff_at", predicate)


if __name__ == "__main__":
    unittest.main()
