import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd

from backend.app.product_services.starters import StartingQBService


class StartingQBServiceTests(unittest.TestCase):
    def test_out_qb1_uses_unique_next_depth_rank_only_when_top_salary_agrees(self):
        service = StartingQBService.__new__(StartingQBService)
        service.engine = MagicMock()
        service._load_out_salary_qbs = MagicMock(return_value={
            "baker-gsis": {"gsis_id": "baker-gsis", "team": "TB", "status": "OUT"},
        })
        candidates = pd.DataFrame([
            {"player_id": "jalon", "name": "Jalon Daniels", "position": "QB",
             "player_team": "TB", "salary": 4400, "gsis_id": "jalon-gsis",
             "game_info": "GB@TB 10/04/2026 01:00PM ET"},
            {"player_id": "easton", "name": "Easton Stick", "position": "QB",
             "player_team": "TB", "salary": 4000, "gsis_id": "easton-gsis",
             "game_info": "GB@TB 10/04/2026 01:00PM ET"},
        ])
        observed_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        depth = pd.DataFrame([
            {"dt": observed_at, "team": "TB", "gsis_id": "baker-gsis",
             "pos_abb": "QB", "pos_rank": 1},
            {"dt": observed_at, "team": "TB", "gsis_id": "jalon-gsis",
             "pos_abb": "QB", "pos_rank": 2},
        ])
        with patch("backend.app.services.source_capture.fetch_nflreadpy_dataset",
                   return_value=(depth, "test-version")), \
             patch("backend.app.services.source_capture.SourceCaptureService") as capture, \
             patch("backend.app.product_services.starters.Session"), \
             patch("backend.app.product_services.starters.parse_slate_lock",
                   return_value=datetime.now(timezone.utc) + timedelta(days=1)):
            capture.return_value.capture_dataframe.return_value.snapshot.snapshot_id = "saved-snapshot"
            selected, conflicts, _ = service._depth_chart_selections(
                candidates=candidates, season=2026, week=4, slate="SUNDAY_MAIN")
            self.assertEqual(conflicts, [])
            self.assertEqual(selected[0]["player_master_id"], "jalon")
            self.assertEqual(selected[0]["source"], "provisional_nflverse_depth_chart_next_active_qb")
            self.assertEqual(selected[0]["evidence_tier"], "inferred")
            self.assertIn("salary status OUT", selected[0]["note"])

            service._load_out_salary_qbs.return_value = {}
            selected, conflicts, _ = service._depth_chart_selections(
                candidates=candidates, season=2026, week=4, slate="SUNDAY_MAIN")
            self.assertEqual(selected, [])
            self.assertEqual(conflicts, ["TB"])

            service._load_out_salary_qbs.return_value = {
                "baker-gsis": {"gsis_id": "baker-gsis", "team": "TB", "status": "OUT"}}
            mismatched_salary = candidates.copy()
            mismatched_salary.loc[mismatched_salary.player_id.eq("easton"), "salary"] = 4500
            selected, conflicts, _ = service._depth_chart_selections(
                candidates=mismatched_salary, season=2026, week=4, slate="SUNDAY_MAIN")
            self.assertEqual(selected, [])
            self.assertEqual(conflicts, ["TB"])

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
        self.assertIn("UPPER(alias.position) = 'QB'", query)
        self.assertIn("CASE UPPER(TRIM(alias.team))", query)
        self.assertIn("salary.player_status", query)
        self.assertIn("'OUT', 'O', 'IR'", query)

    def test_candidate_query_normalizes_cross_source_team_aliases(self):
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
            service._load_candidates(season=2026, week=2, slate="MONDAY_NIGHT")

        query = str(read_sql.call_args.args[0])
        self.assertIn("CASE UPPER(TRIM(raw.team))", query)
        self.assertIn("CASE UPPER(TRIM(participation_row.team))", query)
        self.assertEqual(query.count("WHEN 'LA' THEN 'LAR'"), 3)

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

    def test_confirmed_starters_allow_partial_canonical_team_coverage(self):
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

        partial = service.derive_starters(
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
        self.assertEqual(partial.rows_written, 2)
        partial_starters = service._persist.call_args.kwargs["starters"]
        self.assertEqual(set(partial_starters["player_id"]), {"aaa-qb1", "bbb-qb1"})

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
        self.assertEqual(
            {row["player_master_id"] for row in result.candidates},
            {"aaa-qb1", "aaa-qb2"},
        )
        service._persist.assert_not_called()

    def test_provisional_override_beats_salary_without_claiming_confirmation(self):
        service = StartingQBService.__new__(StartingQBService)
        service._load_candidates = MagicMock(return_value=pd.DataFrame([
            {"player_id": "atl-one", "name": "ATL One", "position": "QB", "player_team": "ATL", "salary": 4700},
            {"player_id": "atl-two", "name": "ATL Two", "position": "QB", "player_team": "ATL", "salary": 4700},
            {"player_id": "sea-high", "name": "SEA High", "position": "QB", "player_team": "SEA", "salary": 5400},
            {"player_id": "sea-start", "name": "SEA Starter", "position": "QB", "player_team": "SEA", "salary": 4900},
        ]))
        service._persist = MagicMock()
        result = service.derive_starters(2026, 2, "SUNDAY_MAIN", confirmed_starters=[
            {"team": "ATL", "player_master_id": "atl-two", "source": "provisional_team_report",
             "source_uri": "https://example.com/atl", "observed_at": "2026-09-17T20:00:00Z",
             "evidence_tier": "inferred", "note": "Week 1 starter; Week 2 undecided"},
            {"team": "SEA", "player_master_id": "sea-start", "source": "official_team_announcement",
             "source_uri": "https://example.com/sea", "observed_at": "2026-09-17T20:00:00Z",
             "evidence_tier": "confirmed"},
        ])
        self.assertEqual(result.rows_written, 2)
        self.assertIn("1 provisional choices", result.message)
        evidence = service._persist.call_args.kwargs["evidence"]
        self.assertEqual(evidence["evidence_status"], "provisional")
        selected = {row["team"]: row for row in evidence["selected"]}
        self.assertEqual(selected["ATL"]["player_id"], "atl-two")
        self.assertEqual(selected["ATL"]["evidence_tier"], "inferred")
        self.assertEqual(selected["SEA"]["player_id"], "sea-start")
        self.assertEqual(selected["SEA"]["evidence_tier"], "confirmed")

        invalid = service.derive_starters(2026, 2, "SUNDAY_MAIN", confirmed_starters=[
            {"team": "ATL", "player_master_id": "atl-two", "source": "provisional_team_report",
             "source_uri": "https://example.com/atl", "observed_at": "2026-09-17T20:00:00Z"},
            {"team": "SEA", "player_master_id": "sea-start", "source": "official_team_announcement",
             "observed_at": "2026-09-17T20:00:00Z"},
        ])
        self.assertEqual(invalid.rows_written, 0)
        self.assertIn("must be inferred", invalid.message)

        non_top = service.derive_starters(2026, 2, "SUNDAY_MAIN", confirmed_starters=[
            {"team": "ATL", "player_master_id": "atl-two", "source": "draftkings_unique_top_salary",
             "evidence_tier": "inferred", "observed_at": "2026-09-17T20:00:00Z"},
            {"team": "SEA", "player_master_id": "sea-start", "source": "draftkings_unique_top_salary",
             "evidence_tier": "inferred", "observed_at": "2026-09-17T20:00:00Z"},
        ])
        self.assertEqual(non_top.rows_written, 0)
        self.assertIn("unique top salary", non_top.message)

    def test_partial_provisional_override_resolves_only_the_ambiguous_team(self):
        service = StartingQBService.__new__(StartingQBService)
        service._load_candidates = MagicMock(return_value=pd.DataFrame([
            {"player_id": "atl-one", "name": "ATL One", "position": "QB", "player_team": "ATL", "salary": 4700},
            {"player_id": "atl-two", "name": "ATL Two", "position": "QB", "player_team": "ATL", "salary": 4700},
            {"player_id": "gb-high", "name": "GB High", "position": "QB", "player_team": "GB", "salary": 5400},
            {"player_id": "gb-backup", "name": "GB Backup", "position": "QB", "player_team": "GB", "salary": 4900},
        ]))
        service._persist = MagicMock()

        result = service.derive_starters(2026, 2, "SUNDAY_MAIN", confirmed_starters=[
            {"team": "ATL", "player_master_id": "atl-two", "source": "provisional_operator_report",
             "source_uri": "https://example.com/atl", "observed_at": "2026-09-17T20:00:00Z",
             "evidence_tier": "inferred"},
        ])

        self.assertEqual(result.rows_written, 2)
        persisted = service._persist.call_args.kwargs["starters"]
        self.assertEqual(set(persisted["player_id"]), {"atl-two", "gb-high"})

    def test_depth_chart_qb1_beats_salary_and_operator_evidence_beats_depth(self):
        service = StartingQBService.__new__(StartingQBService)
        service._load_candidates = MagicMock(return_value=pd.DataFrame([
            {"player_id": "nyg-high", "name": "NYG High", "position": "QB", "player_team": "NYG", "salary": 5900},
            {"player_id": "nyg-qb1", "name": "NYG QB1", "position": "QB", "player_team": "NYG", "salary": 4000},
            {"player_id": "phi-qb1", "name": "PHI QB1", "position": "QB", "player_team": "PHI", "salary": 6000},
        ]))
        service._depth_chart_selections = MagicMock(return_value=([{
            "team": "NYG", "player_master_id": "nyg-qb1",
            "source": "provisional_nflverse_depth_chart_qb1",
            "source_uri": "nflreadpy://depth_charts/2026",
            "observed_at": "2026-09-25T06:00:00Z", "evidence_tier": "inferred",
        }, {
            "team": "PHI", "player_master_id": "phi-qb1",
            "source": "provisional_nflverse_depth_chart_qb1",
            "source_uri": "nflreadpy://depth_charts/2026",
            "observed_at": "2026-09-25T06:00:00Z", "evidence_tier": "inferred",
        }], [], "depth chart captured"))
        service._persist = MagicMock()

        result = service.derive_starters(2026, 3, "SUNDAY_MAIN")
        self.assertEqual(result.rows_written, 2)
        self.assertIn("nyg-qb1", set(service._persist.call_args.kwargs["starters"]["player_id"]))

        result = service.derive_starters(2026, 3, "SUNDAY_MAIN", confirmed_starters=[{
            "team": "NYG", "player_master_id": "nyg-high",
            "source": "official_team_announcement",
            "observed_at": "2026-09-25T12:00:00Z",
        }])
        self.assertEqual(result.rows_written, 2)
        self.assertIn("nyg-high", set(service._persist.call_args.kwargs["starters"]["player_id"]))

    def test_sourced_provisional_starter_survives_stale_depth_chart(self):
        service = StartingQBService.__new__(StartingQBService)
        service._load_candidates = MagicMock(return_value=pd.DataFrame([
            {"player_id": "chi-keenum", "name": "Case Keenum", "position": "QB",
             "player_team": "CHI", "salary": 8400, "is_starting_qb": True,
             "starting_qb_source": "provisional_fox_sports_report",
             "starting_qb_evidence_tier": "inferred",
             "starting_qb_source_uri": "https://example.com/report"},
            {"player_id": "chi-bagent", "name": "Tyson Bagent", "position": "QB",
             "player_team": "CHI", "salary": 8800, "is_starting_qb": False},
            {"player_id": "phi-hurts", "name": "Jalen Hurts", "position": "QB",
             "player_team": "PHI", "salary": 10800},
        ]))
        service._depth_chart_selections = MagicMock(return_value=([{
            "team": "PHI", "player_master_id": "phi-hurts",
            "source": "provisional_nflverse_depth_chart_qb1",
            "source_uri": "nflreadpy://depth_charts/2026",
            "observed_at": "2026-09-27T12:56:55Z", "evidence_tier": "inferred",
        }], ["CHI"], "depth chart captured"))
        service._persist = MagicMock()

        result = service.derive_starters(2026, 3, "MONDAY_NIGHT")

        self.assertEqual(result.rows_written, 2)
        self.assertEqual(
            set(service._persist.call_args.kwargs["starters"]["player_id"]),
            {"chi-keenum", "phi-hurts"},
        )

    def test_old_automatic_depth_chart_selection_does_not_mask_conflict(self):
        service = StartingQBService.__new__(StartingQBService)
        service._load_candidates = MagicMock(return_value=pd.DataFrame([
            {"player_id": "chi-old", "name": "Old QB1", "position": "QB",
             "player_team": "CHI", "salary": 10400, "is_starting_qb": True,
             "starting_qb_source": "provisional_nflverse_depth_chart_qb1",
             "starting_qb_evidence_tier": "inferred",
             "starting_qb_source_uri": "nflreadpy://depth_charts/2026"},
            {"player_id": "phi-qb", "name": "PHI QB", "position": "QB",
             "player_team": "PHI", "salary": 10800},
        ]))
        service._depth_chart_selections = MagicMock(return_value=([], ["CHI"], ""))
        service._persist = MagicMock()

        result = service.derive_starters(2026, 3, "MONDAY_NIGHT")

        self.assertEqual(result.rows_written, 0)
        self.assertIn("CHI", result.message)
        service._persist.assert_not_called()


if __name__ == "__main__":
    unittest.main()
