import unittest
from unittest.mock import MagicMock

from backend.app.product_services.portfolio import PortfolioService


class PortfolioServiceTests(unittest.TestCase):
    def test_builds_one_assignment_per_entry_in_order(self):
        assignments = PortfolioService._build_assignment_plan(
            portfolio_id="portfolio-1",
            template_id="template-1",
            template_rows=[
                {"row_number": 1, "entry_id": "entry-1", "contest_id": "contest-1"},
                {"row_number": 2, "entry_id": "entry-2", "contest_id": "contest-1"},
            ],
            lineup_ids=["lineup-1", "lineup-2"],
        )

        self.assertEqual(len(assignments), 2)
        self.assertEqual(assignments[0].entry_id, "entry-1")
        self.assertEqual(assignments[0].lineup_id, "lineup-1")
        self.assertEqual(assignments[1].portfolio_lineup_number, 2)

    def test_rejects_count_mismatch_and_duplicate_lineups(self):
        rows = [
            {"row_number": 1, "entry_id": "entry-1", "contest_id": "contest-1"},
            {"row_number": 2, "entry_id": "entry-2", "contest_id": "contest-1"},
        ]
        with self.assertRaisesRegex(ValueError, "1 lineups for 2 entries"):
            PortfolioService._build_assignment_plan(
                portfolio_id="portfolio-1",
                template_id="template-1",
                template_rows=rows,
                lineup_ids=["lineup-1"],
            )
        with self.assertRaisesRegex(ValueError, "unique"):
            PortfolioService._build_assignment_plan(
                portfolio_id="portfolio-1",
                template_id="template-1",
                template_rows=rows,
                lineup_ids=["lineup-1", "lineup-1"],
            )

    def test_requires_entry_and_contest_ids(self):
        with self.assertRaisesRegex(ValueError, "entry_id"):
            PortfolioService._build_assignment_plan(
                portfolio_id="portfolio-1",
                template_id="template-1",
                template_rows=[{"row_number": 1, "entry_id": None, "contest_id": "contest-1"}],
                lineup_ids=["lineup-1"],
            )
        assignments = PortfolioService._build_assignment_plan(
            portfolio_id="portfolio-1",
            template_id="template-1",
            template_rows=[{"row_number": 1, "entry_id": "entry-1", "contest_id": None}],
            lineup_ids=["lineup-1"],
            default_contest_id="contest-fallback",
        )
        self.assertEqual(assignments[0].contest_id, "contest-fallback")

    def test_rejects_duplicate_paid_entry_ids(self):
        with self.assertRaisesRegex(ValueError, "duplicate entry_id"):
            PortfolioService._build_assignment_plan(
                portfolio_id="portfolio-1",
                template_id="template-1",
                template_rows=[
                    {"row_number": 1, "entry_id": "entry-1", "contest_id": "contest-1"},
                    {"row_number": 2, "entry_id": "entry-1", "contest_id": "contest-1"},
                ],
                lineup_ids=["lineup-1", "lineup-2"],
            )

    def test_reloads_persisted_portfolio_assignments(self):
        service = PortfolioService.__new__(PortfolioService)
        service.engine = MagicMock()
        service._ensure_schema = MagicMock()
        connection = service.engine.begin.return_value.__enter__.return_value
        portfolio_result = MagicMock()
        portfolio_result.mappings.return_value.first.return_value = {
            "portfolio_id": "portfolio-1",
            "portfolio_name": "Main GPP",
            "optimizer_run_id": "optimizer-1",
            "template_id": "template-1",
            "season": 2025,
            "week": 11,
            "slate_id": "SUNDAY_MAIN",
            "contest_format": "classic",
            "objective": "gpp",
            "status": "assigned",
        }
        assignment_result = MagicMock()
        assignment_result.mappings.return_value.all.return_value = [
            {
                "assignment_id": "assignment-1",
                "portfolio_id": "portfolio-1",
                "template_id": "template-1",
                "template_row_number": 1,
                "entry_id": "entry-1",
                "contest_id": "contest-1",
                "lineup_id": "lineup-1",
                "portfolio_lineup_number": 1,
            }
        ]
        connection.execute.side_effect = [portfolio_result, assignment_result]

        portfolio = service.get_portfolio("portfolio-1")

        self.assertIsNotNone(portfolio)
        self.assertEqual(portfolio.assignment_count, 1)
        self.assertEqual(portfolio.assignments[0].entry_id, "entry-1")


if __name__ == "__main__":
    unittest.main()
