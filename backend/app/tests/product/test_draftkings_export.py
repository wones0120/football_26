import csv
import io
import unittest

from backend.app.product_services.draftkings_export import DraftKingsExportService


def player(site_id: str, position: str, roster_position: str | None = None) -> dict:
    return {
        "player_id": f"internal-{site_id}",
        "roster_position": roster_position or position,
        "salary": 5000,
        "player_json": {"dk_player_id": site_id, "position": position},
    }


class DraftKingsExportTests(unittest.TestCase):
    def test_builds_classic_csv_preserving_entry_metadata_and_duplicate_headers(self):
        columns = [
            "Entry ID", "Contest Name", "Contest ID", "Entry Fee",
            "QB", "RB", "RB.1", "WR", "WR.1", "WR.2", "TE", "FLEX", "DST",
        ]
        players = [
            player("101", "WR"), player("102", "QB"), player("103", "RB"),
            player("104", "WR"), player("105", "TE"), player("106", "DST"),
            player("107", "RB"), player("108", "WR"), player("109", "TE"),
        ]

        content = DraftKingsExportService.build_csv(
            contest_format="classic",
            template_columns=columns,
            rows=[{
                "row_json": {
                    "Entry ID": "3001", "Contest Name": "Test Contest",
                    "Contest ID": "4001", "Entry Fee": "$20",
                },
                "players": players,
            }],
        )
        rows = list(csv.reader(io.StringIO(content)))

        self.assertEqual(rows[0], [
            "Entry ID", "Contest Name", "Contest ID", "Entry Fee",
            "QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST",
        ])
        self.assertEqual(rows[1][:4], ["3001", "Test Contest", "4001", "$20"])
        self.assertEqual(rows[1][4:], ["102", "103", "107", "101", "104", "108", "105", "109", "106"])

    def test_builds_showdown_csv_with_captain_first(self):
        columns = ["Entry ID", "Contest ID", "CPT", "FLEX", "FLEX.1", "FLEX.2", "FLEX.3", "FLEX.4"]
        players = [
            player("201", "QB", "FLEX"),
            player("202", "WR", "CPT"),
            player("203", "RB", "FLEX"),
            player("204", "TE", "FLEX"),
            player("205", "DST", "FLEX"),
            player("206", "K", "FLEX"),
        ]

        content = DraftKingsExportService.build_csv(
            contest_format="showdown",
            template_columns=columns,
            rows=[{"row_json": {"Entry ID": "1", "Contest ID": "2"}, "players": players}],
        )
        rows = list(csv.reader(io.StringIO(content)))

        self.assertEqual(rows[0], ["Entry ID", "Contest ID", "CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"])
        self.assertEqual(rows[1][2:], ["202", "201", "203", "204", "205", "206"])

    def test_rejects_internal_ids_and_wrong_template_shape(self):
        with self.assertRaisesRegex(ValueError, "no DraftKings site ID"):
            DraftKingsExportService._site_player_id(
                {"player_id": "internal-player", "player_json": {"position": "QB"}}
            )
        with self.assertRaisesRegex(ValueError, "do not match"):
            DraftKingsExportService.build_csv(
                contest_format="classic",
                template_columns=["Entry ID", "QB", "RB"],
                rows=[],
            )

    def test_validation_passes_complete_classic_portfolio(self):
        columns = [
            "Entry ID", "Contest ID", "QB", "RB", "RB.1", "WR", "WR.1",
            "WR.2", "TE", "FLEX", "DST",
        ]
        players = [
            player("1", "QB"), player("2", "RB"), player("3", "RB"),
            player("4", "WR"), player("5", "WR"), player("6", "WR"),
            player("7", "TE"), player("8", "TE"), player("9", "DST"),
        ]

        result = DraftKingsExportService.validate_rows(
            portfolio_id="portfolio-1",
            contest_format="classic",
            template_columns=columns,
            rows=[{"entry_id": "entry-1", "contest_id": "contest-1", "players": players}],
            expected_entry_count=1,
            max_exposure=1.0,
        )

        self.assertEqual(result.status, "passed")
        self.assertEqual(result.errors, [])

    def test_validation_reports_salary_duplicates_exposure_and_mapping(self):
        columns = [
            "Entry ID", "Contest ID", "QB", "RB", "RB.1", "WR", "WR.1",
            "WR.2", "TE", "FLEX", "DST",
        ]
        first = [
            player("1", "QB"), player("2", "RB"), player("2", "RB"),
            player("4", "WR"), player("5", "WR"), player("6", "WR"),
            player("7", "TE"), player("8", "TE"), player("9", "DST"),
        ]
        for row in first:
            row["salary"] = 6000
        second = [dict(row) for row in first]

        result = DraftKingsExportService.validate_rows(
            portfolio_id="portfolio-1",
            contest_format="classic",
            template_columns=columns,
            rows=[
                {"entry_id": "", "contest_id": "contest-1", "players": first},
                {"entry_id": "entry-2", "contest_id": "contest-1", "players": second},
            ],
            expected_entry_count=2,
            max_exposure=0.4,
        )
        codes = {issue.code for issue in result.errors}

        self.assertEqual(result.status, "failed")
        self.assertTrue({
            "entry_mapping", "duplicate_player", "duplicate_lineup",
            "salary_cap", "exposure_limit",
        }.issubset(codes))

    def test_showdown_captain_swap_is_not_a_duplicate_lineup(self):
        columns = [
            "Entry ID", "Contest ID", "CPT", "FLEX", "FLEX.1", "FLEX.2",
            "FLEX.3", "FLEX.4",
        ]
        first = [
            player("1", "QB", "CPT"), player("2", "WR", "FLEX"),
            player("3", "RB", "FLEX"), player("4", "TE", "FLEX"),
            player("5", "DST", "FLEX"), player("6", "K", "FLEX"),
        ]
        second = [
            player("1", "QB", "FLEX"), player("2", "WR", "CPT"),
            player("3", "RB", "FLEX"), player("4", "TE", "FLEX"),
            player("5", "DST", "FLEX"), player("6", "K", "FLEX"),
        ]

        result = DraftKingsExportService.validate_rows(
            portfolio_id="portfolio-1",
            contest_format="showdown",
            template_columns=columns,
            rows=[
                {"entry_id": "entry-1", "contest_id": "contest-1", "players": first},
                {"entry_id": "entry-2", "contest_id": "contest-1", "players": second},
            ],
            expected_entry_count=2,
            max_exposure=1.0,
        )

        self.assertNotIn("duplicate_lineup", {issue.code for issue in result.errors})


if __name__ == "__main__":
    unittest.main()
