import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

from backend.app.product_services.ownership import OwnershipService


class OwnershipServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = OwnershipService(connection_string="sqlite:///:memory")

    def test_normalizes_dk_contest_standings_columns(self):
        df = pd.DataFrame(
            [
                {
                    "Rank": 1,
                    "EntryId": 100,
                    "EntryName": "sharp_user",
                    "Points": 220.5,
                    "Lineup": "QB Player A RB Player B",
                    "Player": "Player A",
                    "Roster Position": "QB",
                    "%Drafted": "12.50%",
                    "FPTS": 31.2,
                }
            ]
        )

        rows = self.service._normalize_standings(
            df,
            season=2025,
            week=10,
            slate="SUNDAY_MAIN",
            source_path=Path("contest.csv"),
        )

        self.assertEqual(rows.iloc[0]["season"], 2025)
        self.assertEqual(rows.iloc[0]["week"], 10)
        self.assertEqual(rows.iloc[0]["slate"], "SUNDAY_MAIN")
        self.assertEqual(rows.iloc[0]["player_display_name"], "Player A")
        self.assertEqual(rows.iloc[0]["pct_drafted"], 12.5)
        self.assertEqual(rows.iloc[0]["fpts"], 31.2)

    def test_builds_one_ownership_row_per_player(self):
        rows = pd.DataFrame(
            [
                {
                    "season": 2025,
                    "week": 10,
                    "slate": "SUNDAY_MAIN",
                    "entry_id": "1",
                    "player_id": "p1",
                    "player_master_id": "p1",
                    "player_display_name": "Player A",
                    "roster_position": "QB",
                    "pct_drafted": 20.0,
                },
                {
                    "season": 2025,
                    "week": 10,
                    "slate": "SUNDAY_MAIN",
                    "entry_id": "2",
                    "player_id": "p1",
                    "player_master_id": "p1",
                    "player_display_name": "Player A",
                    "roster_position": "QB",
                    "pct_drafted": 20.0,
                },
            ]
        )

        ownership = self.service._build_ownership(rows)

        self.assertEqual(len(ownership), 1)
        self.assertEqual(ownership.iloc[0]["projected_ownership"], 20.0)
        self.assertEqual(ownership.iloc[0]["entries_seen"], 2)
        self.assertEqual(ownership.iloc[0]["source"], "contest_standings")

    def test_parses_full_lineup_text_for_top_lineup_exposure(self):
        parsed = self.service._parse_lineup(
            "DST Seahawks  FLEX Tez Johnson QB Jaxson Dart RB De'Von Achane "
            "RB TreVeyon Henderson TE Trey McBride WR Emeka Egbuka WR Wan'Dale Robinson WR Jameson Williams"
        )

        self.assertEqual(len(parsed), 9)
        self.assertEqual(parsed[0], {"roster_position": "DST", "player_display_name": "Seahawks"})
        self.assertEqual(parsed[2], {"roster_position": "QB", "player_display_name": "Jaxson Dart"})
        self.assertEqual(parsed[-1], {"roster_position": "WR", "player_display_name": "Jameson Williams"})

    def test_reads_csv_with_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "contest.csv"
            path.write_text(
                "\ufeffRank,EntryId,EntryName,Points,Lineup,Player,Roster Position,%Drafted,FPTS\n"
                "1,100,user,200,QB Player A,Player A,QB,10.00%,25.1\n",
                encoding="utf-8",
            )

            source_path, df = self.service._read_standings(str(path))

        self.assertEqual(source_path.name, "contest.csv")
        self.assertIn("Rank", df.columns)
        self.assertEqual(df.iloc[0]["Player"], "Player A")

    def test_source_and_contest_ids_are_stable_across_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            first_path = Path(tmpdir) / "first.csv"
            second_path = Path(tmpdir) / "second.csv"
            content = b"Rank,EntryId\n1,100\n"
            first_path.write_bytes(content)
            second_path.write_bytes(content)

            first_source = self.service._source_file_info(first_path)
            second_source = self.service._source_file_info(second_path)
            first_contest = self.service._resolve_contest_id(
                None,
                season=2025,
                week=10,
                slate="SUNDAY_MAIN",
                content_sha256=first_source["content_sha256"],
            )
            second_contest = self.service._resolve_contest_id(
                None,
                season=2025,
                week=10,
                slate="SUNDAY_MAIN",
                content_sha256=second_source["content_sha256"],
            )

        self.assertEqual(first_source["source_file_id"], second_source["source_file_id"])
        self.assertEqual(first_contest, second_contest)

    def test_detects_showdown_and_validates_payout_tiers(self):
        contest_format = self.service._resolve_contest_format(
            None,
            slate="THURSDAY_NIGHT",
            roster_positions=pd.Series(["CPT", "FLEX"]),
        )
        tiers = self.service._normalize_payout_tiers(
            [
                {"min_rank": 1, "max_rank": 1, "payout": 1000},
                {"min_rank": 2, "max_rank": 10, "payout": 100},
            ],
            field_size=100,
        )

        self.assertEqual(contest_format, "showdown")
        self.assertEqual(tiers[1]["max_rank"], 10)
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.service._normalize_payout_tiers(
                [
                    {"min_rank": 1, "max_rank": 5, "payout": 100},
                    {"min_rank": 5, "max_rank": 10, "payout": 50},
                ],
                field_size=100,
            )

    def test_target_contest_persistence_writes_metadata_and_tiers(self):
        service = OwnershipService.__new__(OwnershipService)
        service.engine = MagicMock()
        connection = service.engine.begin.return_value.__enter__.return_value
        source_info = {
            "source_file_id": "source-1",
            "content_sha256": "abc123",
            "original_path": "/tmp/contest.csv",
            "file_name": "contest.csv",
            "file_size_bytes": 100,
        }

        persisted = service._persist_target_contest(
            contest_id="contest-1",
            source_info=source_info,
            season=2025,
            week=10,
            slate="SUNDAY_MAIN",
            contest_name="Millionaire Maker",
            contest_format="classic",
            contest_type="gpp",
            contest_type_source="explicit",
            cash_game_type=None,
            entry_fee=20.0,
            field_size=1000,
            max_entries_per_user=150,
            prize_pool=1_000_000.0,
            payout_tiers=[
                {
                    "min_rank": 1,
                    "max_rank": 1,
                    "payout": 200_000.0,
                    "prize_description": None,
                }
            ],
            entries=pd.DataFrame(
                [
                    {
                        "entry_id": "entry-1",
                        "entry_name": "Test Entry",
                        "rank": 1,
                        "entry_points": 200.0,
                        "lineup_text": "QB Example",
                        "ingested_at": datetime(2025, 1, 1, tzinfo=UTC),
                    }
                ]
            ),
        )

        self.assertTrue(persisted)
        contest_payload = next(
            call.args[1]
            for call in connection.execute.call_args_list
            if len(call.args) > 1
            and isinstance(call.args[1], dict)
            and call.args[1].get("contest_id") == "contest-1"
            and "field_size" in call.args[1]
        )
        tier_payload = next(
            call.args[1]
            for call in connection.execute.call_args_list
            if len(call.args) > 1
            and isinstance(call.args[1], list)
            and call.args[1]
            and "min_rank" in call.args[1][0]
        )
        self.assertEqual(contest_payload["max_entries_per_user"], 150)
        self.assertEqual(contest_payload["contest_type"], "gpp")
        self.assertEqual(tier_payload[0]["payout"], 200_000.0)
        entry_payload = next(
            call.args[1]
            for call in connection.execute.call_args_list
            if len(call.args) > 1
            and isinstance(call.args[1], list)
            and call.args[1]
            and "entry_points" in call.args[1][0]
        )
        self.assertEqual(entry_payload[0]["entry_id"], "entry-1")


if __name__ == "__main__":
    unittest.main()
