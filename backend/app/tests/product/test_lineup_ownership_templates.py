import unittest

from scripts.product.report_lineup_ownership_templates import (
    aggregate_by_contest_type,
    bucket_count_signature,
    ownership_bucket,
    slot_template,
)


class LineupOwnershipTemplateTests(unittest.TestCase):
    def test_ownership_bucket_thresholds(self):
        self.assertEqual(ownership_bucket(35), "mega_chalk")
        self.assertEqual(ownership_bucket(20), "chalk")
        self.assertEqual(ownership_bucket(15), "popular")
        self.assertEqual(ownership_bucket(10), "mid")
        self.assertEqual(ownership_bucket(5), "low")
        self.assertEqual(ownership_bucket(4.99), "dart")
        self.assertEqual(ownership_bucket(None), "unknown")

    def test_slot_template_numbers_duplicate_slots(self):
        players = [
            {"roster_position": "QB", "bucket": "chalk"},
            {"roster_position": "RB", "bucket": "low"},
            {"roster_position": "RB", "bucket": "mega_chalk"},
        ]

        self.assertEqual(slot_template(players), "QB:chalk|RB:low|RB2:mega_chalk")

    def test_bucket_count_signature_uses_bucket_order(self):
        players = [
            {"bucket": "low"},
            {"bucket": "mega_chalk"},
            {"bucket": "low"},
        ]

        self.assertEqual(bucket_count_signature(players), "mega_chalk=1,low=2")

    def test_aggregate_by_contest_type_splits_classic_and_showdown(self):
        grouped = aggregate_by_contest_type(
            [
                {
                    "contest_type": "classic",
                    "entries_analyzed": 10,
                    "avg_total_ownership": 100,
                    "avg_bucket_counts_per_lineup": {},
                    "slot_bucket_distribution": {},
                    "top_bucket_signatures": [],
                },
                {
                    "contest_type": "showdown",
                    "entries_analyzed": 5,
                    "avg_total_ownership": 200,
                    "avg_bucket_counts_per_lineup": {},
                    "slot_bucket_distribution": {},
                    "top_bucket_signatures": [],
                },
            ]
        )

        self.assertEqual(grouped["classic"]["lineups_analyzed"], 10)
        self.assertEqual(grouped["showdown"]["lineups_analyzed"], 5)


if __name__ == "__main__":
    unittest.main()
