import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

from backend.app.api.product_routes import import_weekly_contest_folder
from backend.app.product_schemas import (
    SelectedWeeklyContestFile as SelectedWeeklyContestFileRequest,
    WeeklyContestFolderImportRequest,
)
from backend.app.product_services.batch_import import (
    BatchFileResult, BatchImportResult, DraftKingsBatchImportService,
    SelectedWeeklyContestFile,
)


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

    def test_weekly_import_uses_saved_contest_slate_and_folder_hint(self):
        service = object.__new__(DraftKingsBatchImportService)
        service.engine = MagicMock()
        rows = service.engine.connect.return_value.__enter__.return_value.execute.return_value.mappings.return_value.all
        rows.side_effect = [[], [{"season": 2026, "week": 2, "slate": "SUNDAY_MAIN"}]]
        with patch("backend.app.product_services.batch_import.inspect") as inspect_engine:
            inspect_engine.return_value.has_table.return_value = True
            resolved = service._weekly_contest_scope(
                Path("/tmp/NFL/contest-standings-193391018.zip"),
                root=Path("/tmp/NFL"), season=2026, week=2,
                source_file_id="dk_file_123",
            )
        self.assertEqual(resolved, (2026, 2, "SUNDAY_MAIN", "193391018"))

        rows.side_effect = [[]]
        with patch("backend.app.product_services.batch_import.inspect") as inspect_engine:
            inspect_engine.return_value.has_table.return_value = False
            resolved = service._weekly_contest_scope(
                Path("/tmp/NFL/SUNDAY_NIGHT/contest-standings-123.zip"),
                root=Path("/tmp/NFL"), season=2026, week=2,
                source_file_id="dk_file_456",
            )
        self.assertEqual(resolved, (2026, 2, "SUNDAY_NIGHT", "123"))

    def test_salary_player_pool_identifies_unique_slate_from_zip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            players = [f"Player {index}" for index in range(12)]
            contest = root / "contest-standings-123.zip"
            with ZipFile(contest, "w") as archive:
                archive.writestr(
                    "contest-standings-123.csv",
                    "Player\n" + "\n".join(players) + "\n",
                )
            (root / "DKSalaries_2026_3_SUNDAY_MAIN.csv").write_text(
                "Name\n" + "\n".join(players + ["Another Player"]) + "\n",
                encoding="utf-8",
            )
            (root / "DKSalaries_2026_3_THURSDAY_NIGHT.csv").write_text(
                "Name\n" + "\n".join(players[:5]) + "\n",
                encoding="utf-8",
            )

            slate, evidence = DraftKingsBatchImportService._salary_slate_evidence(
                contest, root, season=2026, week=3,
            )

            self.assertEqual(slate, "SUNDAY_MAIN")
            self.assertIn("all 12 contest players", evidence)
            self.assertIn("DKSalaries_2026_3_SUNDAY_MAIN.csv", evidence)

            (root / "DKSalaries_2026_3_THURSDAY_NIGHT.csv").write_text(
                "Name\n" + "\n".join(players) + "\n",
                encoding="utf-8",
            )
            ambiguous_slate, reason = DraftKingsBatchImportService._salary_slate_evidence(
                contest, root, season=2026, week=3,
            )
            self.assertIsNone(ambiguous_slate)
            self.assertIn("multiple salary slates", reason)

    def test_weekly_preview_uses_unique_salary_slate_without_manual_assignment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "contest-standings-123.csv"
            source.write_text(
                "Rank,EntryId,Player,Roster Position,%Drafted\n1,10,Player A,QB,10%\n",
                encoding="utf-8",
            )
            service = object.__new__(DraftKingsBatchImportService)
            service.engine = MagicMock()
            service.ownership = MagicMock()
            service._ensure_schema = MagicMock()
            service.get_batch_result = MagicMock(return_value=None)
            service._weekly_contest_scope = MagicMock(return_value=(None, None, None, "123"))
            service._salary_slate_evidence = MagicMock(return_value=(
                "SUNDAY_MAIN", "Matched all 12 contest players to salaries",
            ))
            service._already_imported = MagicMock(return_value=False)
            service.ownership._source_file_info.return_value = {"source_file_id": "dk_file_123"}

            result = service.import_directory(
                str(root), season=2026, week=3, slate="UNRESOLVED", recursive=True,
                dry_run=True, weekly_contests_only=True,
            )

            self.assertEqual(result.files[0].status, "would_import")
            self.assertEqual((result.files[0].season, result.files[0].week, result.files[0].slate),
                             (2026, 3, "SUNDAY_MAIN"))
            self.assertEqual(result.files[0].contest_id, "123")
            self.assertIn("Matched all 12", result.files[0].message)

    def test_weekly_import_uses_saved_week_even_when_ui_has_another_week(self):
        service = object.__new__(DraftKingsBatchImportService)
        service.engine = MagicMock()
        rows = service.engine.connect.return_value.__enter__.return_value.execute.return_value.mappings.return_value.all
        rows.side_effect = [[{"season": 2026, "week": 1, "slate": "SUNDAY_MAIN"}]]
        with patch("backend.app.product_services.batch_import.inspect") as inspect_engine:
            inspect_engine.return_value.has_table.return_value = False
            resolved = service._weekly_contest_scope(
                Path("/tmp/NFL/SUNDAY_MAIN/contest-standings-123.zip"),
                root=Path("/tmp/NFL"), season=2026, week=2,
                source_file_id="dk_file_123",
            )
        self.assertEqual(resolved, (2026, 1, "SUNDAY_MAIN", "123"))

    def test_weekly_import_rejects_conflicting_filename_and_saved_week(self):
        service = object.__new__(DraftKingsBatchImportService)
        service.engine = MagicMock()
        rows = service.engine.connect.return_value.__enter__.return_value.execute.return_value.mappings.return_value.all
        rows.return_value = [{"season": 2026, "week": 1, "slate": "SUNDAY_MAIN"}]
        with patch("backend.app.product_services.batch_import.inspect") as inspect_engine:
            inspect_engine.return_value.has_table.return_value = False
            with self.assertRaisesRegex(ValueError, "Conflicting season/week evidence"):
                service._weekly_contest_scope(
                    Path("/tmp/NFL/SUNDAY_MAIN/contest-standings-2026-02-123.zip"),
                    root=Path("/tmp/NFL"), season=2026, week=2,
                    source_file_id="dk_file_123",
                )

    def test_selected_weekly_import_only_loads_checked_file_with_explicit_slate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            selected_path = root / "contest-standings-123.csv"
            other_path = root / "contest-standings-456.csv"
            content = "Rank,EntryId,Player,Roster Position,%Drafted\n1,10,Player A,QB,10%\n"
            selected_path.write_text(content, encoding="utf-8")
            other_path.write_text(content, encoding="utf-8")
            service = object.__new__(DraftKingsBatchImportService)
            service.engine = MagicMock()
            service.ownership = MagicMock()
            service._ensure_schema = MagicMock()
            service.get_batch_result = MagicMock(return_value=None)
            service._already_imported = MagicMock(return_value=False)
            service._register_source_file = MagicMock()
            service._mark_staged_contest_resolved = MagicMock()
            service._weekly_contest_scope = MagicMock(return_value=(2026, 3, "SUNDAY_MAIN", "123"))
            service.ownership._source_file_info.return_value = {"source_file_id": "dk_file_123"}
            service.ownership.load_contest_standings.return_value = MagicMock(
                target_persisted=True, rows_written=1, contest_id="123", message="Loaded contest"
            )

            result = service.import_directory(
                str(root), season=2026, week=3, slate="UNRESOLVED", recursive=True,
                weekly_contests_only=True, selected_files=[SelectedWeeklyContestFile(
                    str(selected_path), "dk_file_123", 2026, 3, "SUNDAY_MAIN",
                )],
            )

            self.assertEqual(result.discovered, 1)
            self.assertEqual(result.imported, 1)
            service._weekly_contest_scope.assert_called_once_with(
                selected_path, root=root, season=2026, week=3,
                source_file_id="dk_file_123", selected_slate="SUNDAY_MAIN",
            )
            self.assertTrue(other_path.exists())
            self.assertFalse(selected_path.exists())

    def test_selected_weekly_import_rejects_changed_or_outside_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            selected_path = root / "contest-standings-123.csv"
            selected_path.write_text(
                "Rank,EntryId,Player,Roster Position,%Drafted\n1,10,Player A,QB,10%\n",
                encoding="utf-8",
            )
            service = object.__new__(DraftKingsBatchImportService)
            service.engine = MagicMock()
            service.ownership = MagicMock()
            service._ensure_schema = MagicMock()
            service.get_batch_result = MagicMock(return_value=None)
            service.ownership._source_file_info.return_value = {"source_file_id": "changed"}
            with self.assertRaisesRegex(ValueError, "outside the contest folder"):
                service.import_directory(
                    str(root), season=2026, week=3, slate="UNRESOLVED",
                    weekly_contests_only=True, selected_files=[SelectedWeeklyContestFile(
                        "/tmp/outside.csv", "old", 2026, 3, "SUNDAY_MAIN",
                    )],
                )
            result = service.import_directory(
                str(root), season=2026, week=3, slate="UNRESOLVED",
                weekly_contests_only=True, selected_files=[SelectedWeeklyContestFile(
                    str(selected_path), "old", 2026, 3, "SUNDAY_MAIN",
                )],
            )
            self.assertEqual(result.failed, 1)
            self.assertIn("changed since preview", result.files[0].message)
            service.ownership.load_contest_standings.assert_not_called()
            self.assertTrue(selected_path.exists())

    def test_selected_slate_cannot_conflict_with_salary_player_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "contest-standings-123.csv"
            source.write_text(
                "Rank,EntryId,Player,Roster Position,%Drafted\n1,10,Player A,QB,10%\n",
                encoding="utf-8",
            )
            service = object.__new__(DraftKingsBatchImportService)
            service.engine = MagicMock()
            service.ownership = MagicMock()
            service._ensure_schema = MagicMock()
            service.get_batch_result = MagicMock(return_value=None)
            service._weekly_contest_scope = MagicMock(return_value=(2026, 3, "SUNDAY_MAIN", "123"))
            service._salary_slate_evidence = MagicMock(return_value=(
                "THURSDAY_NIGHT", "Matched all players to Thursday salaries",
            ))
            service.ownership._source_file_info.return_value = {"source_file_id": "dk_file_123"}

            result = service.import_directory(
                str(root), season=2026, week=3, slate="UNRESOLVED",
                weekly_contests_only=True, selected_files=[SelectedWeeklyContestFile(
                    str(source), "dk_file_123", 2026, 3, "SUNDAY_MAIN",
                )],
            )

            self.assertEqual(result.failed, 1)
            self.assertIn("conflicts with salary-player evidence", result.files[0].message)
            service.ownership.load_contest_standings.assert_not_called()

    def test_selected_scope_cannot_override_saved_contest_week(self):
        service = object.__new__(DraftKingsBatchImportService)
        service.engine = MagicMock()
        rows = service.engine.connect.return_value.__enter__.return_value.execute.return_value.mappings.return_value.all
        rows.return_value = [{"season": 2026, "week": 2, "slate": "SUNDAY_MAIN"}]
        with patch("backend.app.product_services.batch_import.inspect") as inspect_engine:
            inspect_engine.return_value.has_table.return_value = False
            with self.assertRaisesRegex(ValueError, "Selected season/week conflicts"):
                service._weekly_contest_scope(
                    Path("/tmp/NFL/contest-standings-123.zip"), root=Path("/tmp/NFL"),
                    season=2026, week=3, source_file_id="dk_file_123",
                    selected_slate="SUNDAY_MAIN",
                )

        rows.return_value = [{"season": 2026, "week": 3, "slate": "THURSDAY_NIGHT"}]
        with patch("backend.app.product_services.batch_import.inspect") as inspect_engine:
            inspect_engine.return_value.has_table.return_value = False
            with self.assertRaisesRegex(ValueError, "Conflicting slate labels"):
                service._weekly_contest_scope(
                    Path("/tmp/NFL/contest-standings-123.zip"), root=Path("/tmp/NFL"),
                    season=2026, week=3, source_file_id="dk_file_123",
                    selected_slate="SUNDAY_MAIN",
                )

    def test_archive_weekly_contest_preserves_slate_folder_and_existing_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "SUNDAY_MAIN"
            source_dir.mkdir()
            source = source_dir / "contest-standings-123.csv"
            source.write_text("new download", encoding="utf-8")
            existing = root / "Processed" / "SUNDAY_MAIN" / source.name
            existing.parent.mkdir(parents=True)
            existing.write_text("older download", encoding="utf-8")

            archived = DraftKingsBatchImportService._archive_weekly_contest(source, root)

            self.assertEqual(archived.name, "contest-standings-123__2.csv")
            self.assertEqual(archived.read_text(encoding="utf-8"), "new download")
            self.assertEqual(existing.read_text(encoding="utf-8"), "older download")
            self.assertFalse(source.exists())

    def test_weekly_import_moves_only_loaded_files_and_skips_processed_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            standings = "Rank,EntryId,Player,Roster Position,%Drafted\n1,10,Player A,QB,10%\n"
            (root / "SUNDAY_MAIN").mkdir()
            (root / "Processed").mkdir()
            first = root / "SUNDAY_MAIN" / "contest-standings-123.csv"
            first.write_text(standings, encoding="utf-8")
            (root / "Processed" / "old-contest.csv").write_text(standings, encoding="utf-8")
            unresolved = root / "contest-standings-456.csv"
            unresolved.write_text(standings, encoding="utf-8")

            service = object.__new__(DraftKingsBatchImportService)
            service.engine = MagicMock()
            service.ownership = MagicMock()
            service._ensure_schema = MagicMock()
            service.get_batch_result = MagicMock(return_value=None)
            service._already_imported = MagicMock(return_value=False)
            service._register_source_file = MagicMock()
            service._weekly_contest_scope = MagicMock(
                side_effect=lambda path, **kwargs: (
                    (2026, 2, "SUNDAY_MAIN", "123") if path == first else (None, None, None, "456")
                )
            )
            service._stage_weekly_contest = MagicMock()
            service._mark_staged_contest_resolved = MagicMock()
            service.ownership._source_file_info.return_value = {"source_file_id": "dk_file_123"}
            service.ownership.load_contest_standings.return_value = MagicMock(
                target_persisted=True, rows_written=1, contest_id="123", message="Loaded contest"
            )

            preview = service.import_directory(
                str(root), season=2026, week=2, slate="UNRESOLVED",
                recursive=True, dry_run=True, weekly_contests_only=True,
            )
            self.assertEqual(preview.discovered, 2)
            self.assertTrue(first.exists())
            loaded = service.import_directory(
                str(root), season=2026, week=2, slate="UNRESOLVED",
                recursive=True, dry_run=False, weekly_contests_only=True,
            )
            self.assertEqual(loaded.discovered, 2)
            self.assertEqual(loaded.imported, 1)
            self.assertEqual(loaded.staged, 1)
            self.assertIn("Moved to", loaded.files[0].message)
            self.assertTrue((root / "Processed" / "SUNDAY_MAIN" / first.name).exists())
            self.assertFalse(first.exists())
            self.assertTrue(unresolved.exists())
            service._stage_weekly_contest.assert_called_once()

    def test_weekly_import_archives_confirmed_duplicate_without_reloading(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "SUNDAY_MAIN" / "contest-standings-123.csv"
            source.parent.mkdir()
            source.write_text(
                "Rank,EntryId,Player,Roster Position,%Drafted\n1,10,Player A,QB,10%\n",
                encoding="utf-8",
            )
            service = object.__new__(DraftKingsBatchImportService)
            service.engine = MagicMock()
            service.ownership = MagicMock()
            service._ensure_schema = MagicMock()
            service.get_batch_result = MagicMock(return_value=None)
            service._already_imported = MagicMock(return_value=True)
            service._weekly_contest_scope = MagicMock(return_value=(2026, 2, "SUNDAY_MAIN", "123"))
            service._mark_staged_contest_resolved = MagicMock()
            service.ownership._source_file_info.return_value = {"source_file_id": "dk_file_123"}

            result = service.import_directory(
                str(root), season=2026, week=2, slate="UNRESOLVED",
                recursive=True, dry_run=False, weekly_contests_only=True,
            )

            self.assertEqual(result.deduplicated, 1)
            self.assertIn("Moved to", result.files[0].message)
            self.assertTrue((root / "Processed" / "SUNDAY_MAIN" / source.name).exists())
            self.assertFalse(source.exists())
            service.ownership.load_contest_standings.assert_not_called()

    def test_unresolved_contest_stages_exact_raw_download(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "contest-standings-123.csv"
            content = b"Rank,EntryId,Player,Roster Position,%Drafted\n1,10,Player A,QB,10%\n"
            source.write_bytes(content)
            service = object.__new__(DraftKingsBatchImportService)
            service.engine = MagicMock()
            service._register_source_file = MagicMock()

            service._stage_weekly_contest(source, {"source_file_id": "dk_file_123"}, "123")

            service._register_source_file.assert_called_once()
            calls = service.engine.begin.return_value.__enter__.return_value.execute.call_args_list
            self.assertEqual(calls[0].args[1]["raw_file"], content)
            self.assertEqual(calls[0].args[1]["contest_id"], "123")

    def test_weekly_import_loads_verified_contest_from_another_week(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "contest-standings-123.csv"
            source.write_text(
                "Rank,EntryId,Player,Roster Position,%Drafted\n1,10,Player A,QB,10%\n",
                encoding="utf-8",
            )
            service = object.__new__(DraftKingsBatchImportService)
            service.engine = MagicMock()
            service.ownership = MagicMock()
            service._ensure_schema = MagicMock()
            service.get_batch_result = MagicMock(return_value=None)
            service._already_imported = MagicMock(return_value=False)
            service._register_source_file = MagicMock()
            service._mark_staged_contest_resolved = MagicMock()
            service._weekly_contest_scope = MagicMock(return_value=(2026, 1, "SUNDAY_MAIN", "123"))
            service.ownership._source_file_info.return_value = {"source_file_id": "dk_file_123"}
            service.ownership.load_contest_standings.return_value = MagicMock(
                target_persisted=True, rows_written=1, contest_id="123", message="Loaded contest"
            )

            result = service.import_directory(
                str(root), season=2026, week=2, slate="UNRESOLVED",
                recursive=True, dry_run=False, weekly_contests_only=True,
            )

            self.assertEqual(result.imported, 1)
            self.assertEqual((result.files[0].season, result.files[0].week), (2026, 1))
            service.ownership.load_contest_standings.assert_called_once_with(
                2026, 1, "SUNDAY_MAIN", str(source), contest_id="123",
            )
            self.assertTrue((root / "Processed" / source.name).exists())

    def test_weekly_folder_route_uses_week_scope_and_returns_file_ledger(self):
        service = MagicMock()
        service.import_directory.return_value = BatchImportResult(
            batch_id="batch-1", directory="/Users/wones/NFL", discovered=1,
            imported=0, deduplicated=1, skipped=0, failed=0, dry_run=True,
            files=[BatchFileResult(
                path="/Users/wones/NFL/contest-standings-123.zip",
                file_type="contest_standings", status="deduplicated",
                season=2026, week=2, slate="SUNDAY_NIGHT",
                source_file_id="dk_file_123", contest_id="123",
            )],
        )
        with patch("backend.app.api.product_routes._record_load_quality"):
            response = import_weekly_contest_folder(
                WeeklyContestFolderImportRequest(
                    directory="~/NFL", season=2026, week=2, dry_run=True,
                ),
                service, MagicMock(),
            )
        service.import_directory.assert_called_once_with(
            "~/NFL", season=2026, week=2, slate="UNRESOLVED", recursive=True,
            dry_run=True, weekly_contests_only=True,
        )
        self.assertEqual(response.files[0].status, "deduplicated")

    def test_weekly_folder_route_passes_selected_file_scope(self):
        service = MagicMock()
        service.import_directory.return_value = BatchImportResult(
            batch_id="batch-1", directory="/tmp/NFL", discovered=1,
            imported=1, deduplicated=0, skipped=0, failed=0, dry_run=False,
            files=[BatchFileResult(
                path="/tmp/NFL/contest-standings-123.zip",
                file_type="contest_standings", status="imported",
                season=2026, week=3, slate="SUNDAY_MAIN",
            )],
        )
        selection = SelectedWeeklyContestFileRequest(
            path="/tmp/NFL/contest-standings-123.zip", source_file_id="dk_file_123",
            season=2026, week=3, slate="SUNDAY_MAIN",
        )
        with patch("backend.app.api.product_routes._record_load_quality"):
            response = import_weekly_contest_folder(
                WeeklyContestFolderImportRequest(
                    directory="/tmp/NFL", season=2026, week=3,
                    dry_run=False, selected_files=[selection],
                ),
                service, MagicMock(),
            )
        self.assertEqual(response.imported, 1)
        service.import_directory.assert_called_once_with(
            "/tmp/NFL", season=2026, week=3, slate="UNRESOLVED",
            recursive=True, dry_run=False, weekly_contests_only=True,
            selected_files=[SelectedWeeklyContestFile(
                "/tmp/NFL/contest-standings-123.zip", "dk_file_123",
                2026, 3, "SUNDAY_MAIN",
            )],
        )


if __name__ == "__main__":
    unittest.main()
