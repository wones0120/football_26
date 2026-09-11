import unittest
from unittest.mock import MagicMock

import pandas as pd

from backend.app.product_services.starters import StartingQBService


class StartingQBServiceTests(unittest.TestCase):
    def test_candidate_query_reuses_stored_confirmed_evidence(self):
        service = StartingQBService.__new__(StartingQBService)
        connection = MagicMock()
        transaction = MagicMock()
        transaction.__enter__.return_value = connection
        service.engine = MagicMock()
        service.engine.begin.return_value = transaction

        with unittest.mock.patch(
            "backend.app.product_services.starters.pd.read_sql",
            return_value=pd.DataFrame(),
        ) as read_sql:
            service._load_candidates(season=2026, week=1, slate="SUNDAY_MAIN")

        query = str(read_sql.call_args.args[0])
        self.assertIn("LEFT JOIN public.starting_qb_evidence starter", query)
        self.assertIn("AS is_starting_qb", query)
        self.assertIn("starting_qb_source_uri", query)

    def test_derive_starters_persists_one_canonical_qb_per_team(self):
        service = StartingQBService.__new__(StartingQBService)
        service._load_candidates = MagicMock(
            return_value=pd.DataFrame(
                [
                    {"player_id": "aaa-qb1", "name": "AAA One", "position": "QB", "player_team": "AAA", "salary": 10000},
                    {"player_id": "aaa-qb2", "name": "AAA Two", "position": "QB", "player_team": "AAA", "salary": 6000},
                    {"player_id": "bbb-qb1", "name": "BBB One", "position": "QB", "player_team": "BBB", "salary": 9800},
                    {"player_id": "bbb-qb2", "name": "BBB Two", "position": "QB", "player_team": "BBB", "salary": 5800},
                ]
            )
        )
        service._persist = MagicMock()

        result = service.derive_starters(
            season=2026,
            week=1,
            slate="WEDNESDAY_NIGHT",
        )

        self.assertEqual(result.rows_written, 2)
        self.assertIn("inferred from unique top DraftKings salary", result.message)
        persisted = service._persist.call_args.kwargs["starters"]
        self.assertEqual(set(persisted["player_id"]), {"aaa-qb1", "bbb-qb1"})

    def test_derive_starters_supports_multi_team_classic_slate(self):
        service = StartingQBService.__new__(StartingQBService)
        service._load_candidates = MagicMock(
            return_value=pd.DataFrame(
                [
                    {"player_id": "aaa-qb1", "name": "AAA One", "position": "QB", "player_team": "AAA", "salary": 10000},
                    {"player_id": "aaa-qb2", "name": "AAA Two", "position": "QB", "player_team": "AAA", "salary": 6000},
                    {"player_id": "bbb-qb1", "name": "BBB One", "position": "QB", "player_team": "BBB", "salary": 9800},
                    {"player_id": "ccc-qb1", "name": "CCC One", "position": "QB", "player_team": "CCC", "salary": 9600},
                    {"player_id": "ccc-qb2", "name": "CCC Two", "position": "QB", "player_team": "CCC", "salary": 5800},
                ]
            )
        )
        service._persist = MagicMock()

        result = service.derive_starters(
            season=2026,
            week=1,
            slate="SUNDAY_MAIN",
        )

        self.assertEqual(result.rows_written, 3)
        persisted = service._persist.call_args.kwargs["starters"]
        self.assertEqual(
            set(persisted["player_id"]),
            {"aaa-qb1", "bbb-qb1", "ccc-qb1"},
        )

    def test_confirmed_starters_require_complete_canonical_team_coverage(self):
        service = StartingQBService.__new__(StartingQBService)
        service._load_candidates = MagicMock(
            return_value=pd.DataFrame(
                [
                    {"player_id": "aaa-qb1", "name": "AAA One", "position": "QB", "player_team": "AAA", "salary": 10000},
                    {"player_id": "aaa-qb2", "name": "AAA Two", "position": "QB", "player_team": "AAA", "salary": 6000},
                    {"player_id": "bbb-qb1", "name": "BBB One", "position": "QB", "player_team": "BBB", "salary": 9800},
                    {"player_id": "bbb-qb2", "name": "BBB Two", "position": "QB", "player_team": "BBB", "salary": 5800},
                ]
            )
        )
        service._persist = MagicMock()
        observed_at = "2026-09-09T12:00:00Z"

        result = service.derive_starters(
            season=2026,
            week=1,
            slate="SUNDAY_MAIN",
            confirmed_starters=[
                {
                    "player_master_id": "aaa-qb2",
                    "team": "AAA",
                    "source": "official_team_announcement",
                    "source_uri": "https://example.com/aaa",
                    "observed_at": observed_at,
                },
                {
                    "player_master_id": "bbb-qb1",
                    "team": "BBB",
                    "source": "official_team_announcement",
                    "source_uri": "https://example.com/bbb",
                    "observed_at": observed_at,
                },
            ],
        )

        self.assertEqual(result.rows_written, 2)
        self.assertIn("confirmed by QB1 evidence", result.message)
        persisted = service._persist.call_args.kwargs
        self.assertEqual(
            set(persisted["starters"]["player_id"]),
            {"aaa-qb2", "bbb-qb1"},
        )
        selected = persisted["evidence"]["selected"]
        self.assertTrue(all(row["evidence_tier"] == "confirmed" for row in selected))
        self.assertEqual(selected[0]["observed_at"], observed_at)

        incomplete = service.derive_starters(
            season=2026,
            week=1,
            slate="SUNDAY_MAIN",
            confirmed_starters=[
                {
                    "player_master_id": "aaa-qb1",
                    "team": "AAA",
                    "source": "official_team_announcement",
                    "observed_at": observed_at,
                }
            ],
        )
        self.assertEqual(incomplete.rows_written, 0)
        self.assertIn("missing BBB", incomplete.message)

    def test_derive_starters_does_not_persist_ambiguous_evidence(self):
        service = StartingQBService.__new__(StartingQBService)
        service._load_candidates = MagicMock(
            return_value=pd.DataFrame(
                [
                    {"player_id": "aaa-qb1", "name": "AAA One", "position": "QB", "player_team": "AAA", "salary": 10000},
                    {"player_id": "aaa-qb2", "name": "AAA Two", "position": "QB", "player_team": "AAA", "salary": 10000},
                    {"player_id": "bbb-qb1", "name": "BBB One", "position": "QB", "player_team": "BBB", "salary": 9800},
                ]
            )
        )
        service._persist = MagicMock()

        result = service.derive_starters(
            season=2026,
            week=1,
            slate="WEDNESDAY_NIGHT",
        )

        self.assertEqual(result.rows_written, 0)
        self.assertIn("ambiguous for AAA", result.message)
        service._persist.assert_not_called()


if __name__ == "__main__":
    unittest.main()
