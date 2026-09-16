import csv
import io
import unittest
import zipfile
from types import SimpleNamespace
from fastapi import HTTPException
from backend.app.api.product_routes import download_optimizer_lineups

from backend.app.product_services.draftkings_export import DraftKingsExportService


def player(site_id: str, position: str, roster_position: str | None = None) -> dict:
    return {
        "player_id": f"internal-{site_id}",
        "roster_position": roster_position or position,
        "salary": 5000,
        "player_json": {"dk_player_id": site_id, "position": position},
    }


class DraftKingsExportTests(unittest.TestCase):
    @staticmethod
    def raw_showdown(offset=0):
        return [{"player_id": f"canonical-{offset + i}", "dk_player_id": str(1000 + offset + i),
                 "dk_captain_id": str(900000 + offset + i), "position": "WR",
                 "roster_position": "CPT" if i == 0 else "FLEX", "salary": 5000}
                for i in range(6)]

    def test_direct_showdown_export_uses_captain_id_and_all_lineups(self):
        filename, mime, content = DraftKingsExportService.build_lineup_download(
            contest_format="showdown", run_id="run", lineups=[self.raw_showdown(), self.raw_showdown(10)])
        rows = list(csv.reader(io.StringIO(content.decode())))
        self.assertEqual((filename, mime), ("draftkings_showdown_run.csv", "text/csv"))
        self.assertEqual(rows[0], ["CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"])
        self.assertEqual(rows[1], ["900000", "1001", "1002", "1003", "1004", "1005"])
        self.assertEqual(len(rows), 3)

    def test_separate_single_entry_contests_can_export_repeated_lineup(self):
        repeated = [self.raw_showdown() for _ in range(3)]
        with self.assertRaises(ValueError):
            DraftKingsExportService.build_lineup_download(
                contest_format="showdown", run_id="run", lineups=repeated,
            )
        _, _, content = DraftKingsExportService.build_lineup_download(
            contest_format="showdown", run_id="run", lineups=repeated,
            allow_duplicate_lineups=True,
        )
        rows = list(csv.reader(io.StringIO(content.decode())))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[1], rows[2])

        players = [player(str(100 + i), "WR", "CPT" if i == 0 else "FLEX") for i in range(6)]
        columns = ["Entry ID", "Contest ID", "CPT", "FLEX", "FLEX.1", "FLEX.2", "FLEX.3", "FLEX.4"]
        assignments = [
            {"entry_id": f"entry-{i}", "contest_id": contest_id, "players": players}
            for i, contest_id in enumerate(("contest-a", "contest-b"), 1)
        ]
        permitted = DraftKingsExportService.validate_rows(
            portfolio_id="portfolio", contest_format="showdown", template_columns=columns,
            rows=assignments, expected_entry_count=2, allow_duplicate_lineups=True,
        )
        self.assertEqual(permitted.status, "passed")
        assignments[1]["contest_id"] = "contest-a"
        rejected = DraftKingsExportService.validate_rows(
            portfolio_id="portfolio", contest_format="showdown", template_columns=columns,
            rows=assignments, expected_entry_count=2, allow_duplicate_lineups=True,
        )
        self.assertIn("duplicate_lineup", {issue.code for issue in rejected.errors})

    def test_direct_classic_export_orders_slots_without_entries(self):
        positions = ["WR", "QB", "RB", "WR", "TE", "DST", "RB", "WR", "TE"]
        lineup = [{"player_id": f"canonical-{i}", "dk_player_id": str(100 + i),
                   "position": position, "salary": 5000} for i, position in enumerate(positions)]
        _, _, content = DraftKingsExportService.build_lineup_download(
            contest_format="classic", run_id="run", lineups=[lineup])
        rows = list(csv.reader(io.StringIO(content.decode())))
        self.assertEqual(rows[1], ["101", "102", "106", "100", "103", "107", "104", "108", "105"])

    def test_direct_export_splits_at_500_without_losing_lineups(self):
        filename, mime, content = DraftKingsExportService.build_lineup_download(
            contest_format="showdown", run_id="run", lineups=[self.raw_showdown(i * 10) for i in range(501)])
        self.assertTrue(filename.endswith(".zip"))
        self.assertEqual(mime, "application/zip")
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertEqual([len(list(csv.reader(io.StringIO(archive.read(name).decode())))) - 1
                              for name in archive.namelist()], [500, 1])

    def test_direct_export_rejects_missing_captain_id_duplicate_identity_and_over_cap(self):
        for failure in ("captain", "identity", "salary", "site"):
            lineup = self.raw_showdown()
            if failure == "captain":
                del lineup[0]["dk_captain_id"]
            elif failure == "identity":
                lineup[1]["player_id"] = lineup[0]["player_id"]
            elif failure == "salary":
                lineup[0]["salary"] = 40000
            else:
                del lineup[1]["dk_player_id"]
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                DraftKingsExportService.build_lineup_download(contest_format="showdown", run_id="run", lineups=[lineup])

    def test_download_route_uses_saved_run_and_handles_unavailable_runs(self):
        job = SimpleNamespace(status="completed", contest_format="showdown", job_id="saved", results=[self.raw_showdown()])
        response = download_optimizer_lineups("saved", service=SimpleNamespace(get_job=lambda _: job))
        self.assertEqual(response.status_code, 200)
        self.assertIn("saved.csv", response.headers["content-disposition"])
        for value, status in [(None, 404), (SimpleNamespace(status="running"), 409)]:
            with self.assertRaises(HTTPException) as error:
                download_optimizer_lineups("saved", service=SimpleNamespace(get_job=lambda _: value))
            self.assertEqual(error.exception.status_code, status)

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
