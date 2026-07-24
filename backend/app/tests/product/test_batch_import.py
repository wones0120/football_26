import tempfile
import unittest
from pathlib import Path

from backend.app.product_services.batch_import import DraftKingsBatchImportService


class DraftKingsBatchImportTests(unittest.TestCase):
    def test_classifies_supported_draftkings_files_and_skips_unrelated_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            standings = root / "contest.csv"
            standings.write_text(
                "Rank,EntryId,Player,Roster Position,%Drafted\n1,10,Player A,QB,10%\n",
                encoding="utf-8",
            )
            salaries = root / "salaries.csv"
            salaries.write_text(
                "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev\n"
                "QB,Player A (1),Player A,1,QB,6000,A@B,A\n",
                encoding="utf-8",
            )
            entries = root / "entries.csv"
            entries.write_text(
                "Entry ID,Contest Name,Contest ID,Entry Fee,QB,RB\n1,Test,99,$20,,\n",
                encoding="utf-8",
            )
            unrelated = root / "bank.csv"
            unrelated.write_text("Date,Amount\n2026-01-01,10\n", encoding="utf-8")

            self.assertEqual(DraftKingsBatchImportService.classify_file(standings), "contest_standings")
            self.assertEqual(DraftKingsBatchImportService.classify_file(salaries), "salary")
            self.assertEqual(DraftKingsBatchImportService.classify_file(entries), "entry_template")
            self.assertEqual(DraftKingsBatchImportService.classify_file(unrelated), "unrecognized")

    def test_infers_scope_from_filename_with_request_fallback(self):
        inferred = DraftKingsBatchImportService.infer_scope(
            Path("contest-standings-2025-13-THURSDAY-NIGHT-CAPTAIN.csv"),
            season=2026,
            week=1,
            slate="DEFAULT",
        )
        fallback = DraftKingsBatchImportService.infer_scope(
            Path("contest-standings-184088297.zip"),
            season=2025,
            week=7,
            slate="SUNDAY_MAIN",
        )

        self.assertEqual(inferred, (2025, 13, "THURSDAY_NIGHT_CAPTAIN"))
        self.assertEqual(fallback, (2025, 7, "SUNDAY_MAIN"))

    def test_entry_template_id_is_deterministic_for_source_scope(self):
        first = DraftKingsBatchImportService.entry_template_id(
            "source-1", 2025, 11, "SUNDAY_MAIN"
        )
        second = DraftKingsBatchImportService.entry_template_id(
            "source-1", 2025, 11, "SUNDAY_MAIN"
        )

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("template_"))


if __name__ == "__main__":
    unittest.main()
